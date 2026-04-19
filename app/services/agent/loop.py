"""
AgentLoop · 主调度循环。

契约：
1. 初始 messages = [system, user(query)]
2. 每轮调一次 LLM：
   - 若返回 tool_calls → 逐个执行 handler，把 result 作为 tool 消息 append 回 messages，继续下一轮
   - 若返回纯 content → 视为 final，结束
3. 步数上限 MAX_STEPS；工具连续失败上限 MAX_CONSECUTIVE_ERRORS
4. 任何 handler 抛错都变成 observation 里的 {"error": "..."} 让 LLM 自我修复

Loop 本身不做任何 I/O、不打日志到 stdout（除 logger），便于被 API / 脚本 / 单测复用。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from .registry import ToolRegistry
from .schemas import AgentStep, AgentTrajectory, ToolCall, ToolResult

logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = """你是一名"舆镜 YuJing"舆情分析助手。
你的任务是根据用户的问题，**自主决定**调用哪些工具来收集证据，再给出简洁、带引用的回答。

可用工具由运行时注入，调用规则：
- 优先调用语义/关键词检索定位相关事件，再调用详情工具拿证据。
- 每次调用前自问"现有信息是否足够回答"，够了就直接给 final answer，不要为调用而调用。
- 单次对话总步数不超过 6 步，尽量在 3-4 步内收敛。

回答要求：
- 中文输出，先给事实再给研判。
- 引用具体 `event#<id>` / `article#<id>`，不要编造 id。
- 如果工具返回空，诚实告知"当前数据未覆盖"，不要编造。
"""

MAX_STEPS = 6
MAX_CONSECUTIVE_ERRORS = 2


class AgentLoop:
    """同步 Agent 主循环。

    - `llm_caller` 默认用 `llm_adapter.call_llm`，单测时注入 fake 可完全离线
    - `system_prompt` 可被调用方覆盖，便于不同场景（早报 / 对比 / 深度）用不同提示
    """

    def __init__(
        self,
        registry: ToolRegistry,
        llm_caller: Optional[Callable[..., Any]] = None,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_steps: int = MAX_STEPS,
        max_consecutive_errors: int = MAX_CONSECUTIVE_ERRORS,
    ) -> None:
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.max_consecutive_errors = max_consecutive_errors
        if llm_caller is None:
            from .llm_adapter import call_llm
            self._llm_caller = call_llm
        else:
            self._llm_caller = llm_caller

    def run(self, query: str) -> AgentTrajectory:
        """跑一个 query 到结束，返回完整 trajectory。"""
        trajectory = AgentTrajectory(query=query)
        t0 = time.time()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query},
        ]
        consecutive_errors = 0

        for step_idx in range(self.max_steps):
            try:
                resp = self._llm_caller(
                    messages=messages,
                    tools_openai_format=self.registry.to_openai_functions(),
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("[agent.loop] LLM 调用失败 @ step %d", step_idx)
                trajectory.steps.append(AgentStep(
                    index=step_idx,
                    kind="error",
                    assistant_content=f"LLM 调用失败: {exc}",
                ))
                trajectory.terminated_reason = "error"
                break

            if resp.tool_calls:
                step = AgentStep(
                    index=step_idx,
                    kind="tool_call",
                    tool_calls=list(resp.tool_calls),
                    assistant_content=resp.content or "",
                )
                # 同步 assistant 消息到 messages（含 tool_calls）
                messages.append({
                    "role": "assistant",
                    "content": resp.content or "",
                    "tool_calls": [
                        {
                            "call_id": tc.call_id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                        }
                        for tc in resp.tool_calls
                    ],
                })

                # 执行每个 tool_call，把 observation append 到 messages
                had_error = False
                for tc in resp.tool_calls:
                    result = self._dispatch_tool(tc)
                    step.tool_results.append(result)
                    if result.error:
                        had_error = True
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.call_id,
                        "content": self._serialize_observation(result),
                    })

                trajectory.steps.append(step)
                consecutive_errors = consecutive_errors + 1 if had_error else 0
                if consecutive_errors > self.max_consecutive_errors:
                    trajectory.terminated_reason = "too_many_errors"
                    break
                continue

            # 无 tool_calls → final
            trajectory.steps.append(AgentStep(
                index=step_idx,
                kind="final",
                assistant_content=resp.content or "",
            ))
            trajectory.final_answer = resp.content or ""
            trajectory.finished = True
            trajectory.terminated_reason = "final"
            break
        else:
            trajectory.terminated_reason = "max_steps"

        trajectory.total_latency_ms = int((time.time() - t0) * 1000)
        return trajectory

    # ---- 内部辅助 ---------------------------------------------------------

    def _dispatch_tool(self, tc: ToolCall) -> ToolResult:
        """执行单个 tool_call。任何异常都被捕获转为 ToolResult.error。"""
        t0 = time.time()
        spec = self.registry.get(tc.name)
        if spec is None:
            return ToolResult(
                call_id=tc.call_id,
                name=tc.name,
                output=None,
                error=f"unknown tool: {tc.name!r}",
                latency_ms=int((time.time() - t0) * 1000),
            )
        try:
            output = spec.handler(**(tc.arguments or {}))
        except TypeError as exc:
            return ToolResult(
                call_id=tc.call_id,
                name=tc.name,
                output=None,
                error=f"invalid args: {exc}",
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[agent.loop] 工具 %s 执行失败", tc.name)
            return ToolResult(
                call_id=tc.call_id,
                name=tc.name,
                output=None,
                error=f"tool error: {exc}",
                latency_ms=int((time.time() - t0) * 1000),
            )
        return ToolResult(
            call_id=tc.call_id,
            name=tc.name,
            output=output,
            latency_ms=int((time.time() - t0) * 1000),
        )

    @staticmethod
    def _serialize_observation(result: ToolResult) -> str:
        """把 ToolResult 转成塞进 tool 消息的字符串。

        错误场景优先呈现 error 字段，方便 LLM 读到后自修复。
        复杂对象 `default=str` 兜底，防止 datetime / numpy 类型导致 TypeError。
        """
        if result.error:
            payload: Dict[str, Any] = {"error": result.error}
        else:
            payload = {"output": result.output}
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            return json.dumps(
                {"error": f"observation serialization failed: {exc}"},
                ensure_ascii=False,
            )

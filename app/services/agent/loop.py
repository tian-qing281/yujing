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
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

from .registry import ToolRegistry
from .schemas import AgentStep, AgentTrajectory, ToolCall, ToolResult

logger = logging.getLogger(__name__)


DEFAULT_SYSTEM_PROMPT = """你是一名"舆镜 YuJing"舆情分析助手。
你的任务是根据用户的问题，**自主决定**调用哪些工具来收集证据，再给出简洁、带引用的回答。

**范围判断（最先执行）**：
- 你只处理与新闻、舆情、热搜、事件、社会热点相关的问题。
- 如果用户的问题明显与舆情/新闻无关（如数学题、编程题、闲聊等），**不要调用任何工具**，直接回复："我是舆情分析助手，只能回答与新闻热点、舆论动态相关的问题。请换一个舆情相关的问题，例如'今天有什么热搜'或'最近有什么值得关注的事件'。"
- 如果用户的问题过于模糊（如只说一个词），礼貌地要求用户说得更具体一些。

可用工具由运行时注入，调用规则：
- 优先调用语义/关键词检索定位相关事件，再调用详情工具拿证据。
- 每次调用前自问"现有信息是否足够回答"，够了就直接给 final answer，不要为调用而调用。
- **并发调用优化**（重要）：当一个问题涉及多个独立对象时，**请在同一轮里返回多个 tool_calls** 让后端并行执行，而不是一次一个串行等结果。典型场景：
  · 对比两三个事件 → 同一轮发起 `get_event_detail(A)` + `get_event_detail(B)` + `get_event_detail(C)`
  · 分析多个事件情绪 → 同一轮发起多次 `analyze_event_sentiment`
  · 一次检索得到候选后，如需同时看详情与情绪 → 并发发起
- **聚合优先**：遇到"情绪最负面/最热门/排名 TopN"类问题，**优先调用 `rank_events_by_*` 聚合工具一步拿结果**，不要用"逐事件详查再人工比较"的 O(N) 做法。
- **聚焦策略**：锁定 1-2 个最相关事件深入分析即可，不要对多个事件重复调用同一个工具；若用户问的是概览性问题，从 search 结果里直接总结而非逐个详查。
- 单次对话总步数不超过 8 步，绝大多数问题应在 3-5 步内收敛。
- 一旦已有足够信息（通常是 1 次检索 + 1-2 次细节 + 可选 1 次情绪/对比），立即给出 final answer。

回答要求：
- 中文输出，先给事实再给研判。
- 引用具体 `event#<id>` / `article#<id>`，不要编造 id。
- 如果工具返回空，诚实告知"当前数据未覆盖"，不要编造。
"""

MAX_STEPS = 8
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

    def run(
        self,
        query: str,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> AgentTrajectory:
        """跑一个 query 到结束，返回完整 trajectory。

        Args:
            query: 用户问题
            on_event: 可选回调，每个关键节点会被调用一次，参数为 dict：
                - {"type":"llm_thinking","step":i}                在每次 LLM 调用前
                - {"type":"tool_call","step":i,"name":...,"args":...}
                - {"type":"tool_result","step":i,"name":...,"ok":bool,
                   "output":..., "error":..., "latency_ms":int}
                - {"type":"final","text":...}
                - {"type":"error","message":...,"terminated_reason":...}
                - {"type":"done","terminated_reason":...,"total_latency_ms":int}
            回调异常不会影响主循环；SSE 场景下回调会把事件塞进 asyncio.Queue。
        """
        def _emit(event: Dict[str, Any]) -> None:
            if on_event is None:
                return
            try:
                on_event(event)
            except Exception:  # noqa: BLE001
                logger.exception("[agent.loop] on_event 回调失败，已忽略")

        trajectory = AgentTrajectory(query=query)
        t0 = time.time()
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query},
        ]
        consecutive_errors = 0

        for step_idx in range(self.max_steps):
            _emit({"type": "llm_thinking", "step": step_idx})
            t_llm = time.time()
            llm_kwargs: Dict[str, Any] = {
                "messages": messages,
                "tools_openai_format": self.registry.to_openai_functions(),
            }
            if on_event is not None:
                llm_kwargs["on_delta"] = lambda text: _emit({
                    "type": "llm_thinking_delta", "step": step_idx, "text": text,
                })
            try:
                resp = self._llm_caller(**llm_kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[agent.loop] LLM 调用失败 @ step %d", step_idx)
                trajectory.steps.append(AgentStep(
                    index=step_idx,
                    kind="error",
                    assistant_content=f"LLM 调用失败: {exc}",
                ))
                trajectory.terminated_reason = "error"
                _emit({"type": "error", "message": f"LLM 调用失败: {exc}", "terminated_reason": "error"})
                break
            llm_latency_ms = int((time.time() - t_llm) * 1000)
            _emit({
                "type": "llm_done",
                "step": step_idx,
                "llm_latency_ms": llm_latency_ms,
                "content": resp.content or "",
            })

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

                # 执行每个 tool_call。并发策略：
                # 1. 先顺序 emit 全部 `tool_call` 事件（前端 timeline 一次性呈现"多线出发"）
                # 2. n>1 时用 ThreadPoolExecutor 并行执行 handler（各 tool 内部是同步 DB / HTTP 调用）
                # 3. 按原始 call 顺序 emit `tool_result`，保证 LLM / 前端观测稳定
                # n==1 时不起 executor（避免 ~1ms 线程切换开销 + 保持单测 happy path 行为不变）
                tool_calls = list(resp.tool_calls)
                for tc in tool_calls:
                    _emit({
                        "type": "tool_call",
                        "step": step_idx,
                        "name": tc.name,
                        "args": tc.arguments or {},
                    })

                if len(tool_calls) > 1:
                    with ThreadPoolExecutor(
                        max_workers=min(len(tool_calls), 4),
                        thread_name_prefix="agent-tool",
                    ) as pool:
                        results = list(pool.map(self._dispatch_tool, tool_calls))
                else:
                    results = [self._dispatch_tool(tool_calls[0])]

                had_error = False
                for tc, result in zip(tool_calls, results):
                    step.tool_results.append(result)
                    if result.error:
                        had_error = True
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.call_id,
                        "content": self._serialize_observation(result),
                    })
                    _emit({
                        "type": "tool_result",
                        "step": step_idx,
                        "name": tc.name,
                        "ok": result.error is None,
                        "output": result.output,
                        "error": result.error,
                        "latency_ms": result.latency_ms,
                    })

                trajectory.steps.append(step)
                consecutive_errors = consecutive_errors + 1 if had_error else 0
                if consecutive_errors > self.max_consecutive_errors:
                    trajectory.terminated_reason = "too_many_errors"
                    _emit({
                        "type": "error",
                        "message": "连续工具调用失败过多",
                        "terminated_reason": "too_many_errors",
                    })
                    break
                continue

            # 无 tool_calls → final
            final_text = resp.content or ""
            trajectory.steps.append(AgentStep(
                index=step_idx,
                kind="final",
                assistant_content=final_text,
            ))
            trajectory.final_answer = final_text
            trajectory.finished = True
            trajectory.terminated_reason = "final"
            # 打字机式推送：把 final 分片逐段 emit 为 final_delta，前端累积渲染。
            # 技术权衡：DeepSeek 非流式调用，content 已完整返回；这里人为切片是为了
            # 获得与 ChatGPT 类似的 UX（视觉流式）。总耗时额外增加 ~1-2s，但用户
            # 感知从"等了 5s 一次性闪出"变成"边生成边打字"，体验显著改善。
            # 只在有 on_event（流式请求）时切片，非流式/单测路径跳过。
            if on_event is not None and final_text:
                chunk_size = 12
                delta_sleep = 0.05
                for i in range(0, len(final_text), chunk_size):
                    piece = final_text[i:i + chunk_size]
                    _emit({"type": "final_delta", "text": piece})
                    time.sleep(delta_sleep)
            _emit({"type": "final", "text": final_text})
            break
        else:
            trajectory.terminated_reason = "max_steps"
            fallback = "已达最大分析步数上限，未能收敛出结论。请尝试更具体的问题。"
            trajectory.final_answer = fallback
            _emit({"type": "final", "text": fallback})
            _emit({
                "type": "error",
                "message": "已达最大步数上限，未收敛",
                "terminated_reason": "max_steps",
            })

        trajectory.total_latency_ms = int((time.time() - t0) * 1000)
        _emit({
            "type": "done",
            "terminated_reason": trajectory.terminated_reason,
            "total_latency_ms": trajectory.total_latency_ms,
        })
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

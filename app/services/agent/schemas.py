"""
Agent 引擎数据类。

只定义形状，不含业务逻辑。所有字段序列化友好（`to_dict` 可用），
便于 M3 的 SSE 流式输出和 M5 的 trajectory 落库评测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


# ---- 工具声明 ---------------------------------------------------------------

@dataclass(frozen=True)
class ToolSpec:
    """一个 Agent 工具的完整声明。

    - `name`：全局唯一，LLM 看到的就是这个
    - `description`：LLM 用来判断"何时该调这个工具"的依据，要用行为式描述
    - `input_schema`：JSON Schema（draft-07），字段全部 `required`（除非真的是可选）
    - `handler`：纯函数，接受 `**kwargs`，返回 dict。抛异常由 Loop 捕获并变成
      observation 让 LLM 自我修复，不要在 handler 内部 try-except 静默吞错
    """

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Dict[str, Any]]

    def to_openai_function(self) -> Dict[str, Any]:
        """转成 OpenAI function-calling 格式，供 LLM bind_tools 用。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


# ---- 执行过程数据 -----------------------------------------------------------

@dataclass
class ToolCall:
    """LLM 在某一步发出的工具调用请求。"""

    call_id: str
    name: str
    arguments: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"call_id": self.call_id, "name": self.name, "arguments": dict(self.arguments)}


@dataclass
class ToolResult:
    """工具执行完的结构化结果。

    `error` 非空时，`output` 必须为 None；Loop 会把错误描述回传给 LLM 让其修正。
    """

    call_id: str
    name: str
    output: Optional[Any]
    error: Optional[str] = None
    latency_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "output": self.output,
            "error": self.error,
            "latency_ms": self.latency_ms,
        }


@dataclass
class AgentStep:
    """Agent 在一轮 LLM 交互里产生的全部信息。

    `kind` 枚举：
      - "tool_call"：LLM 发出了 tool_calls（见 `tool_calls` / `tool_results`）
      - "final"   ：LLM 输出了最终回答（见 `assistant_content`）
      - "error"   ：LLM 调用本身失败（网络 / 超时 / 配置），见 `assistant_content`
    """

    index: int
    kind: str
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    assistant_content: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "tool_results": [tr.to_dict() for tr in self.tool_results],
            "assistant_content": self.assistant_content,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AgentTrajectory:
    """一次完整的 Agent 对话轨迹。

    `terminated_reason` 枚举：
      - "final"           ：正常给出 final answer
      - "max_steps"       ：达到步数上限强制终止
      - "too_many_errors" ：连续工具错误超过阈值
      - "error"           ：LLM 调用本身失败
      - ""                ：运行中（未终止）
    """

    query: str
    steps: List[AgentStep] = field(default_factory=list)
    final_answer: str = ""
    finished: bool = False
    terminated_reason: str = ""
    total_latency_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "steps": [s.to_dict() for s in self.steps],
            "final_answer": self.final_answer,
            "finished": self.finished,
            "terminated_reason": self.terminated_reason,
            "total_latency_ms": self.total_latency_ms,
        }

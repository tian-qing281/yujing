"""
LLM Tool-Calling Agent 子包（W4 新增）。

本包只负责 Agent 引擎本身：
- `schemas`：ToolSpec / ToolCall / ToolResult / AgentStep / AgentTrajectory 数据类
- `registry`：工具注册表 ToolRegistry
- `llm_adapter`：LLM 调用抽象（当前走 LangChain + DeepSeek function calling）
- `loop`：AgentLoop 主循环（LLM ↔ tool 多轮调度）

8 个具体工具的实现放在 M2 阶段，文件命名为 `tool_*.py`，
通过 `default_registry.register(...)` 注册到全局。

设计原则：
- MVP 同步接口，流式输出在 M3 的 API 层再加
- 不依赖 LangChain Agent 相关高阶封装，自己控制循环便于可视化 / 评测 / 复盘
- 测试可通过注入 `llm_caller` 绕过真实 LLM 调用，完全离线跑单测
"""

from .schemas import (
    AgentStep,
    AgentTrajectory,
    ToolCall,
    ToolResult,
    ToolSpec,
)
from .registry import ToolRegistry, default_registry
from .loop import AgentLoop, DEFAULT_SYSTEM_PROMPT, MAX_STEPS

__all__ = [
    "AgentLoop",
    "AgentStep",
    "AgentTrajectory",
    "DEFAULT_SYSTEM_PROMPT",
    "MAX_STEPS",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "default_registry",
]

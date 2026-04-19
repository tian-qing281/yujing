"""
LLM 调用抽象层。

把 "给一组 OpenAI-style messages + tools，返回 tool_calls 或 final answer"
封装成同步函数 `call_llm(...)`。Loop 完全不感知 LangChain / DeepSeek，只看
`LLMResponse` 数据类。

这样做的好处：
- 切换 provider 只改本文件
- 单测完全不依赖网络（Loop 接受注入的 `llm_caller`）
- 后续 M3 加流式时，可在本文件增加 `call_llm_stream` 不污染其它代码
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .schemas import ToolCall

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """一次 LLM 调用的结果。

    - `tool_calls` 非空 → Loop 应执行工具并下一轮继续
    - `tool_calls` 为空 → Loop 把 `content` 作为 final answer 返回
    """

    content: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    raw: Any = None


def _messages_to_langchain(messages: List[Dict[str, Any]]) -> List[Any]:
    """把统一 dict 格式的 messages 转成 LangChain 消息对象。

    支持的 role:
      - "system"    →  SystemMessage
      - "user"      →  HumanMessage
      - "assistant" →  AIMessage（可附带 tool_calls，OpenAI 格式）
      - "tool"      →  ToolMessage（必须带 tool_call_id）
    """
    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )

    lc_messages: List[Any] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "") or ""
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            raw_tool_calls = m.get("tool_calls") or []
            if raw_tool_calls:
                # LangChain 标准 tool_calls 结构：list[{"name","args","id"}]
                normalized = []
                for tc in raw_tool_calls:
                    args = tc.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"_raw": args}
                    normalized.append({
                        "name": tc.get("name", ""),
                        "args": args,
                        "id": tc.get("call_id", ""),
                    })
                lc_messages.append(AIMessage(content=content, tool_calls=normalized))
            else:
                lc_messages.append(AIMessage(content=content))
        elif role == "tool":
            lc_messages.append(ToolMessage(
                content=content,
                tool_call_id=m.get("tool_call_id", ""),
            ))
        else:
            logger.warning("[agent.llm_adapter] 未知 role %r，已忽略", role)
    return lc_messages


def call_llm(
    messages: List[Dict[str, Any]],
    tools_openai_format: List[Dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> LLMResponse:
    """调 LLM 一次，返回 tool_calls 或 final content。

    - 首次调用时会懒加载 ChatOpenAI + 复用 `app.llm._get_llm_settings()`
    - `tools_openai_format` 空列表时自动走纯 chat 模式
    """
    from langchain_openai import ChatOpenAI
    from app.llm import _get_llm_settings

    settings = _get_llm_settings()
    llm = ChatOpenAI(
        model=settings["model"],
        openai_api_key=settings["api_key"],
        openai_api_base=settings["api_base"],
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=2,
    )
    bound = llm.bind_tools(tools_openai_format) if tools_openai_format else llm

    lc_messages = _messages_to_langchain(messages)
    ai_msg = bound.invoke(lc_messages)

    tool_calls: List[ToolCall] = []
    for tc in (getattr(ai_msg, "tool_calls", None) or []):
        tool_calls.append(ToolCall(
            call_id=tc.get("id") or "",
            name=tc.get("name") or "",
            arguments=tc.get("args") or {},
        ))

    content = ai_msg.content if isinstance(ai_msg.content, str) else str(ai_msg.content or "")
    return LLMResponse(content=content, tool_calls=tool_calls, raw=ai_msg)

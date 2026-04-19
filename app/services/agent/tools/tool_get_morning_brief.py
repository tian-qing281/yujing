"""
Agent 工具 · get_morning_brief

返回当天已生成的舆情早报内容。本工具只读 cache，**不触发**早报生成——
生成是独立的后台任务，由 `/api/ai/morning_brief/trigger` 启动。

这样设计是为了：
1. Agent 的 tool 必须秒级返回，不可以在 LLM 对话里 hold 住 30s+ 跑 LLM 早报
2. cache miss 时，LLM 读到 `has_content=false` 可以告诉用户"今日早报尚未生成，
   请通过首页按钮触发"，是一种合理的降级路径

cache 结构：`{"date": "YYYY-MM-DD", "content": str, "generating": bool}`。
直接 import routes 模块的 `_morning_brief_cache` 变量是有意的——当前项目没有
独立的 cache service 层，这个字典就是事实上的单例。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "get_morning_brief"
MAX_CONTENT_CHARS_IN_OBSERVATION = 2000


def _handler(**_ignored: Any) -> Dict[str, Any]:
    """返回当天早报缓存内容。"""
    # 延迟 import，避免循环依赖（routes.py 在启动早期才完成挂载）
    from app.api.routes import _morning_brief_cache

    today = datetime.now().strftime("%Y-%m-%d")
    cached_date = _morning_brief_cache.get("date") or ""
    content = _morning_brief_cache.get("content") or ""
    generating = bool(_morning_brief_cache.get("generating"))

    if cached_date == today and content:
        return {
            "_type": "morning_brief",
            "has_content": True,
            "date": today,
            "content": content[:MAX_CONTENT_CHARS_IN_OBSERVATION],
            "truncated": len(content) > MAX_CONTENT_CHARS_IN_OBSERVATION,
            "generating": generating,
        }

    return {
        "_type": "morning_brief",
        "has_content": False,
        "date": today,
        "cached_date": cached_date,
        "generating": generating,
        "hint": (
            "当前没有今日早报缓存。可建议用户前往首页点击『生成早报』按钮触发，"
            "或调用其他工具（search_events / list_hot_platforms）回答问题。"
        ),
    }


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "读取当天已缓存的舆情早报全文。**不触发**生成——生成是耗时后台任务，"
        "cache miss 时返回 has_content=false 并附提示。适合回答"
        "「今天的舆情早报讲了什么」这类概览问题。"
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
    handler=_handler,
)

default_registry.register(SPEC)

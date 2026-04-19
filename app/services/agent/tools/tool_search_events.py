"""
Agent 工具 · search_events

按关键词 / 时间范围 / 平台筛事件，返回精简 list 供 LLM 挑 event_id 继续调详情。

设计要点：
- 复用 `app.services.events.search_events` service 层函数，不走 HTTP 内调
- 每条结果带 `_id / _type / _title` 元字段，便于 LLM 在 final answer 里引用
- 只返回摘要字段，不返回 related_articles / keywords list 等重对象，节省 token
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "search_events"
DEFAULT_LIMIT = 5
MAX_LIMIT = 10
DEFAULT_TIME_RANGE_HOURS = 168  # 7 天


def _parse_keywords(raw: Optional[str]) -> List[str]:
    """events.keywords 存的是 JSON list string，兜底返回 []"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(k) for k in parsed][:6]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _marshal_event(event) -> Dict[str, Any]:
    """LLM 友好的精简视图。只留 final answer 需要的字段。"""
    return {
        "_id": event.id,
        "_type": "event",
        "_title": event.title,
        "article_count": event.article_count or 0,
        "platform_count": event.platform_count or 0,
        "heat_score": round(float(event.heat_score or 0.0), 2),
        "sentiment": event.sentiment or "neutral",
        "latest_article_time": event.latest_article_time.isoformat() if event.latest_article_time else None,
        "primary_source_id": event.primary_source_id or "",
        "keywords": _parse_keywords(event.keywords),
    }


def _handler(
    q: str = "",
    time_range_hours: int = DEFAULT_TIME_RANGE_HOURS,
    source_id: str = "",
    limit: int = DEFAULT_LIMIT,
    **_ignored: Any,
) -> Dict[str, Any]:
    """查事件。

    参数：
      q               关键词，可空（空串表示只按时间/平台筛选按热度排序）
      time_range_hours 回看窗口（小时），默认 168
      source_id       平台代号（如 "weibo_hot"），空串表示不过滤
      limit           返回条数上限，默认 5，最大 10
    """
    from app.database import SessionLocal
    from app.services.events import search_events as _svc_search_events

    query = (q or "").strip()
    try:
        tr = int(time_range_hours) if time_range_hours else DEFAULT_TIME_RANGE_HOURS
    except (TypeError, ValueError):
        tr = DEFAULT_TIME_RANGE_HOURS
    tr = max(1, min(tr, 720))

    try:
        lim = int(limit) if limit else DEFAULT_LIMIT
    except (TypeError, ValueError):
        lim = DEFAULT_LIMIT
    lim = max(1, min(lim, MAX_LIMIT))

    db = SessionLocal()
    try:
        events = _svc_search_events(
            db,
            query=query,
            limit=lim,
            time_range=tr,
            source_id=(source_id or None),
        )
        items = [_marshal_event(e) for e in events]
        return {
            "query": query,
            "time_range_hours": tr,
            "source_id": source_id or None,
            "total": len(items),
            "events": items,
        }
    finally:
        db.close()


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "按关键词、时间范围、平台筛选事件。用于定位用户问题涉及的具体事件 ID，"
        "之后可以调 get_event_detail 拿详情。`q` 留空则按热度列最近热门事件。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "关键词，例如 '伊朗' / '苹果发布会' / '高考'；留空则按热度排列最新事件",
            },
            "time_range_hours": {
                "type": "integer",
                "description": "回看窗口（小时）。1 ≤ 值 ≤ 720。默认 168（7 天）",
                "minimum": 1,
                "maximum": 720,
            },
            "source_id": {
                "type": "string",
                "description": "平台过滤，如 'weibo_hot' / 'zhihu_hot'；留空表示跨平台",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数，1 ≤ 值 ≤ 10，默认 5",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": [],
    },
    handler=_handler,
)

default_registry.register(SPEC)

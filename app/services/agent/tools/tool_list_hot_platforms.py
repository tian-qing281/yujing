"""
Agent 工具 · list_hot_platforms

各平台的热度快照：按 `articles.source_id` 分组，统计近 N 小时内条目数 +
代表事件。用户问"哪个平台最激烈 / 各平台对比"时使用。

实现思路：
1. 取窗口内 articles 按 source_id 做 COUNT
2. 对每个平台，关联出 top_k 代表事件（按 event.heat_score 取前 k 条该平台为
   primary_source_id 的事件）
3. 输出按 article_count 降序，每平台 3 个代表事件

故意不引入新的 service 函数——临时 SQL 就在工具内。后续若多处复用再抽提。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import func

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "list_hot_platforms"
DEFAULT_TIME_RANGE_HOURS = 24
DEFAULT_TOP_EVENTS_PER_PLATFORM = 3
MAX_TOP_EVENTS_PER_PLATFORM = 6


def _marshal_event_brief(event) -> Dict[str, Any]:
    return {
        "_id": event.id,
        "_type": "event",
        "_title": event.title,
        "article_count": event.article_count or 0,
        "heat_score": round(float(event.heat_score or 0.0), 2),
        "sentiment": event.sentiment or "neutral",
    }


def _handler(
    time_range_hours: int = DEFAULT_TIME_RANGE_HOURS,
    top_events_per_platform: int = DEFAULT_TOP_EVENTS_PER_PLATFORM,
    **_ignored: Any,
) -> Dict[str, Any]:
    from app.database import Article, Event, SessionLocal, utcnow

    try:
        tr = int(time_range_hours) if time_range_hours else DEFAULT_TIME_RANGE_HOURS
    except (TypeError, ValueError):
        tr = DEFAULT_TIME_RANGE_HOURS
    tr = max(1, min(tr, 720))

    try:
        top_n = int(top_events_per_platform) if top_events_per_platform else DEFAULT_TOP_EVENTS_PER_PLATFORM
    except (TypeError, ValueError):
        top_n = DEFAULT_TOP_EVENTS_PER_PLATFORM
    top_n = max(1, min(top_n, MAX_TOP_EVENTS_PER_PLATFORM))

    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(hours=tr)

        platform_rows = (
            db.query(
                Article.source_id,
                func.count(Article.id).label("article_count"),
            )
            .filter(Article.fetch_time >= cutoff)
            .filter(Article.source_id.isnot(None))
            .group_by(Article.source_id)
            .order_by(func.count(Article.id).desc())
            .all()
        )

        platforms: List[Dict[str, Any]] = []
        total_articles = 0
        for source_id, article_count in platform_rows:
            if not source_id:
                continue
            total_articles += article_count
            top_events = (
                db.query(Event)
                .filter(Event.primary_source_id == source_id)
                .filter(Event.latest_article_time >= cutoff)
                .order_by(
                    Event.heat_score.desc(),
                    Event.latest_article_time.desc(),
                )
                .limit(top_n)
                .all()
            )
            platforms.append({
                "source_id": source_id,
                "article_count": int(article_count),
                "top_events": [_marshal_event_brief(e) for e in top_events],
            })

        return {
            "_type": "platforms_snapshot",
            "time_range_hours": tr,
            "total_articles": total_articles,
            "platform_count": len(platforms),
            "platforms": platforms,
        }
    finally:
        db.close()


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "查看各平台（微博 / 知乎 / 头条 / 哔哩哔哩 等）在指定时间窗内的热度快照："
        "文章数 + 每平台 top 事件。用于回答「哪个平台最激烈 / 各平台热点对比 / "
        "某事件哪个平台讨论最多」之类问题。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "time_range_hours": {
                "type": "integer",
                "description": "回看窗口（小时），1 ≤ 值 ≤ 720，默认 24",
                "minimum": 1,
                "maximum": 720,
            },
            "top_events_per_platform": {
                "type": "integer",
                "description": "每个平台返回的代表事件数，1 ≤ 值 ≤ 6，默认 3",
                "minimum": 1,
                "maximum": 6,
            },
        },
        "required": [],
    },
    handler=_handler,
)

default_registry.register(SPEC)

"""
Agent 工具 · get_event_detail

拿单个事件的完整上下文：主字段 + 前 N 篇代表文章。LLM 通常在 search_events 之后
挑一个 event_id 调本工具取证据。

设计要点：
- 不触发任何写入（不跑 BERT 补全 / 不写 cache），纯读取
- 默认取前 5 篇代表文章，按 is_primary / relation_score 排序（即现有主路径）
- 返回字段命名尽量贴近前端 EventModal，便于 LLM 理解语义
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "get_event_detail"
DEFAULT_TOP_ARTICLES = 5
MAX_TOP_ARTICLES = 15


def _parse_keywords(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(k) for k in parsed][:10]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _marshal_article(article, importance: float) -> Dict[str, Any]:
    return {
        "_id": article.id,
        "_type": "article",
        "_title": article.title,
        "source_id": article.source_id or "",
        "url": article.url or "",
        "pub_date": article.pub_date.isoformat() if article.pub_date else None,
        "ai_sentiment": article.ai_sentiment or "",
        "ai_summary": (article.ai_summary or "")[:200] or None,
        "importance_score": round(float(importance or 0.0), 4),
    }


def _handler(
    event_id: int = 0,
    top_articles: int = DEFAULT_TOP_ARTICLES,
    **_ignored: Any,
) -> Dict[str, Any]:
    """取事件详情 + 前 top_articles 篇代表文章。"""
    from app.database import Article, Event, EventArticle, SessionLocal

    try:
        eid = int(event_id)
    except (TypeError, ValueError):
        raise ValueError(f"event_id 必须是整数，收到 {event_id!r}")
    if eid <= 0:
        raise ValueError("event_id 必须 > 0")

    try:
        top_n = int(top_articles) if top_articles else DEFAULT_TOP_ARTICLES
    except (TypeError, ValueError):
        top_n = DEFAULT_TOP_ARTICLES
    top_n = max(1, min(top_n, MAX_TOP_ARTICLES))

    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == eid).first()
        if event is None:
            return {
                "_id": eid,
                "_type": "event",
                "found": False,
                "message": f"事件 #{eid} 不存在",
            }

        link_rows = (
            db.query(EventArticle)
            .filter(EventArticle.event_id == eid)
            .order_by(
                EventArticle.is_primary.desc(),
                EventArticle.relation_score.desc(),
            )
            .limit(top_n)
            .all()
        )
        article_ids = [row.article_id for row in link_rows]
        importance_map = {row.article_id: row.importance_score or 0.0 for row in link_rows}

        articles_map: Dict[int, Article] = {}
        if article_ids:
            for a in db.query(Article).filter(Article.id.in_(article_ids)).all():
                articles_map[a.id] = a
        top_articles_payload = [
            _marshal_article(articles_map[aid], importance_map.get(aid, 0.0))
            for aid in article_ids
            if aid in articles_map
        ]

        return {
            "_id": event.id,
            "_type": "event",
            "_title": event.title,
            "found": True,
            "summary": event.summary or "",
            "sentiment": event.sentiment or "neutral",
            "article_count": event.article_count or 0,
            "platform_count": event.platform_count or 0,
            "heat_score": round(float(event.heat_score or 0.0), 2),
            "latest_article_time": event.latest_article_time.isoformat() if event.latest_article_time else None,
            "primary_source_id": event.primary_source_id or "",
            "keywords": _parse_keywords(event.keywords),
            "top_articles": top_articles_payload,
        }
    finally:
        db.close()


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "取单个事件的详情，包含摘要、关键词、情绪标签、前若干篇代表文章。"
        "必须传 event_id（整数）。用于在 search_events 之后深入单事件取证据。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "integer",
                "description": "事件 ID，通常来自 search_events 的返回",
                "minimum": 1,
            },
            "top_articles": {
                "type": "integer",
                "description": "返回的代表文章数，1 ≤ 值 ≤ 15，默认 5",
                "minimum": 1,
                "maximum": 15,
            },
        },
        "required": ["event_id"],
    },
    handler=_handler,
)

default_registry.register(SPEC)

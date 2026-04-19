"""
Agent 工具 · search_articles

用 MeiliSearch 做全文搜，返回文章精简视图。和 `search_events` 的差别：
- 本工具在**文章粒度**，适合回答"X 在微博上都说了什么" / "X 的原帖证据"
- 如果 Meili 未启用，自动降级为 ILIKE title 模糊匹配，不会丢失功能

设计要点：
- 时间窗默认 168 h（7 天），上限 720 h（30 天）
- limit 默认 8，上限 15 —— 防止 observation 过长撑爆 LLM 上下文
- 返回字段：_id / _type / _title / source_id / url / pub_date / ai_sentiment / ai_summary 前 160 字
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "search_articles"
DEFAULT_LIMIT = 8
MAX_LIMIT = 15
DEFAULT_TIME_RANGE_HOURS = 168


def _marshal_article(article) -> Dict[str, Any]:
    return {
        "_id": article.id,
        "_type": "article",
        "_title": article.title,
        "source_id": article.source_id or "",
        "url": article.url or "",
        "pub_date": article.pub_date.isoformat() if article.pub_date else None,
        "ai_sentiment": article.ai_sentiment or "",
        "ai_summary": (article.ai_summary or "")[:160] or None,
    }


def _handler(
    q: str = "",
    time_range_hours: int = DEFAULT_TIME_RANGE_HOURS,
    source_id: str = "",
    limit: int = DEFAULT_LIMIT,
    **_ignored: Any,
) -> Dict[str, Any]:
    from app.database import Article, SessionLocal
    from app.services.search_engine import meili

    query = (q or "").strip()
    if not query:
        return {
            "query": "",
            "total": 0,
            "articles": [],
            "hint": "关键词 q 不能为空。请提供搜索词，例如 '伊朗'、'高考'。",
        }

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
        hit_ids: List[int] = []
        meili_used = False
        if meili.enabled:
            try:
                hit_ids = meili.search_articles(
                    query,
                    limit=lim,
                    time_range=tr,
                    source_id=(source_id or ""),
                )
                meili_used = True
            except Exception:
                hit_ids = []

        if hit_ids:
            rows = db.query(Article).filter(Article.id.in_(hit_ids)).all()
            lookup = {a.id: a for a in rows}
            articles = [lookup[aid] for aid in hit_ids if aid in lookup]
        else:
            # Fallback：DB 直查 title ILIKE（SQLite 不区分大小写用 LIKE 即可）
            q_obj = db.query(Article).filter(Article.title.like(f"%{query}%"))
            if source_id:
                q_obj = q_obj.filter(Article.source_id == source_id)
            articles = q_obj.order_by(Article.pub_date.desc()).limit(lim).all()

        items = [_marshal_article(a) for a in articles]
        return {
            "query": query,
            "time_range_hours": tr,
            "source_id": source_id or None,
            "total": len(items),
            "meili_used": meili_used and bool(hit_ids),
            "articles": items,
        }
    finally:
        db.close()


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "按关键词全文搜文章（优先 MeiliSearch，不可用时降级到 DB LIKE）。"
        "用于拿原始文章证据，例如"
        "「伊朗相关微博原帖」「苹果发布会头条报道」。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "q": {
                "type": "string",
                "description": "关键词，不能为空",
            },
            "time_range_hours": {
                "type": "integer",
                "description": "回看窗口（小时），1 ≤ 值 ≤ 720，默认 168",
                "minimum": 1,
                "maximum": 720,
            },
            "source_id": {
                "type": "string",
                "description": "平台过滤，如 'weibo_hot' / 'zhihu_hot'；留空表示跨平台",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数，1 ≤ 值 ≤ 15，默认 8",
                "minimum": 1,
                "maximum": 15,
            },
        },
        "required": ["q"],
    },
    handler=_handler,
)

default_registry.register(SPEC)

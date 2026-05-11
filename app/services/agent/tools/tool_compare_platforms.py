"""
Agent 工具 · compare_platforms

对比两个平台（微博 / 知乎 / 头条 / ...）的舆情概况：情报规模、覆盖情绪、24h
变化、关联事件、时间轴。用于场景：

- "对比微博和知乎"
- "微博和头条对伊朗事件的看法有什么差异"

输出直接可被前端 CompareDashboard 渲染（`{a: metrics, b: metrics}`）。
内部复用 `app.api.routes._build_compare_metrics` + `_resolve_compare_source`，
和 `/api/ai/compare` 保持指标口径完全一致；不走 LLM，一次 SQL 聚合返回。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "compare_platforms"
MAX_ARTICLES_PER_SIDE = 40
MAX_EVENTS_PER_SIDE = 5


def _gather_side(db, name: str, topic: str):
    """
    复制 /api/ai/compare 里的 `gather()` 逻辑，产出 (articles, events) 供
    `_build_compare_metrics` 使用。保持两个入口口径一致。
    """
    from app.api.routes import _resolve_compare_source
    from app.database import Article
    from app.services.events import search_events

    source_id = _resolve_compare_source(name)
    q = db.query(Article)
    if source_id:
        q = q.filter(Article.source_id == source_id)
        if topic:
            q = q.filter(Article.title.like(f"%{topic}%"))
    else:
        q = q.filter(Article.title.like(f"%{name}%"))
        if topic:
            q = q.filter(Article.title.like(f"%{topic}%"))
    items = q.order_by(Article.fetch_time.desc()).limit(MAX_ARTICLES_PER_SIDE).all()

    search_query = topic if (source_id and topic) else name
    evts = search_events(db, search_query, limit=MAX_EVENTS_PER_SIDE) if search_query else []
    return items, evts, source_id


def _handler(
    platform_a: Any = None,
    platform_b: Any = None,
    topic: Any = "",
    **_ignored: Any,
) -> Dict[str, Any]:
    from app.api.routes import _build_compare_metrics
    from app.database import SessionLocal

    name_a = (platform_a or "").strip() if isinstance(platform_a, str) else ""
    name_b = (platform_b or "").strip() if isinstance(platform_b, str) else ""
    topic_str = (topic or "").strip() if isinstance(topic, str) else ""

    if not name_a or not name_b:
        raise ValueError("platform_a 和 platform_b 不能为空")
    if name_a == name_b:
        raise ValueError("platform_a 和 platform_b 不能相同")

    db = SessionLocal()
    try:
        a_articles, a_events, a_source_id = _gather_side(db, name_a, topic_str)
        b_articles, b_events, b_source_id = _gather_side(db, name_b, topic_str)

        metrics_a = _build_compare_metrics(name_a, a_articles, a_events)
        metrics_b = _build_compare_metrics(name_b, b_articles, b_events)

        # 对比摘要：把前端仪表盘最常问的 3 个问题预先算出来，降低 LLM 做数值
        # 比较时的出错率。
        winner_by_articles: Optional[str] = None
        if metrics_a["article_count"] != metrics_b["article_count"]:
            winner_by_articles = "a" if metrics_a["article_count"] > metrics_b["article_count"] else "b"

        def _sentiment_leader(bucket: str) -> Optional[str]:
            va = metrics_a["sentiment"].get(bucket, 0)
            vb = metrics_b["sentiment"].get(bucket, 0)
            if va == vb:
                return None
            return "a" if va > vb else "b"

        comparison_summary: Dict[str, Any] = {
            "winner_by_articles": winner_by_articles,
            "more_positive": _sentiment_leader("positive"),
            "more_negative": _sentiment_leader("negative"),
            "topic": topic_str or None,
        }

        return {
            "_type": "platform_comparison",
            "a": metrics_a,
            "b": metrics_b,
            "a_source_id": a_source_id,
            "b_source_id": b_source_id,
            "comparison_summary": comparison_summary,
        }
    finally:
        db.close()


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "对比两个平台的舆情概况：情报规模、情绪分布、24h 变化、覆盖平台、代表情报。"
        "必选 platform_a / platform_b（如：微博、知乎、头条、百度、B 站、财联社、澎湃）。"
        "可选 topic 作主题过滤（如：伊朗事件 / AI 模型）。"
        "适用于 '对比微博和知乎' / '微博和头条对 X 的看法' 这类问题，"
        "输出可直接作为对比仪表盘的数据源。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "platform_a": {
                "type": "string",
                "description": "平台 A 名称，如 微博 / 知乎 / 头条 / 百度 / B站",
            },
            "platform_b": {
                "type": "string",
                "description": "平台 B 名称，如 微博 / 知乎 / 头条 / 百度 / B站",
            },
            "topic": {
                "type": "string",
                "description": "（可选）主题过滤词，对比某平台对该主题的舆情",
                "default": "",
            },
        },
        "required": ["platform_a", "platform_b"],
    },
    handler=_handler,
)

default_registry.register(SPEC)

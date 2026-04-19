"""
Agent 工具 · analyze_event_sentiment

给单个 event_id，返回：
1. 情绪分布（positive / negative / neutral / surprise 等各自占比）
2. 按时间桶（6/12/24 h）分组的情绪时序，显示情绪演化曲线

数据来源：`event_articles` 表关联出的 articles + 它们的 `ai_sentiment` 字段。
**只读**，不触发任何 BERT / LLM 生成，纯统计。

设计要点：
- 空数据（文章未打情绪标签）时返回 `labelled_count=0` 和 hint
- 时间桶从事件最早到最晚文章之间等距切，不是固定绝对时间
- LLM 读到时序数组后可以描述"情绪从 neutral 转向 negative 发生在第 3 个桶"
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "analyze_event_sentiment"
DEFAULT_BUCKET_HOURS = 12
ALLOWED_BUCKET_HOURS = {6, 12, 24}


def _bucket_index(t: datetime, t0: datetime, bucket_hours: int) -> int:
    delta_hours = (t - t0).total_seconds() / 3600.0
    return max(0, int(delta_hours // bucket_hours))


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _handler(
    event_id: int = 0,
    bucket_hours: int = DEFAULT_BUCKET_HOURS,
    **_ignored: Any,
) -> Dict[str, Any]:
    from app.database import Article, Event, EventArticle, SessionLocal

    try:
        eid = int(event_id)
    except (TypeError, ValueError):
        raise ValueError(f"event_id 必须是整数，收到 {event_id!r}")
    if eid <= 0:
        raise ValueError("event_id 必须 > 0")

    try:
        bucket = int(bucket_hours) if bucket_hours else DEFAULT_BUCKET_HOURS
    except (TypeError, ValueError):
        bucket = DEFAULT_BUCKET_HOURS
    if bucket not in ALLOWED_BUCKET_HOURS:
        bucket = DEFAULT_BUCKET_HOURS

    db = SessionLocal()
    try:
        event = db.query(Event).filter(Event.id == eid).first()
        if event is None:
            return {
                "_id": eid,
                "_type": "event_sentiment",
                "found": False,
                "message": f"事件 #{eid} 不存在",
            }

        link_rows = (
            db.query(EventArticle)
            .filter(EventArticle.event_id == eid)
            .all()
        )
        article_ids = [row.article_id for row in link_rows]
        if not article_ids:
            return {
                "_id": eid,
                "_type": "event_sentiment",
                "_title": event.title,
                "found": True,
                "article_count": 0,
                "labelled_count": 0,
                "hint": "事件下无关联文章。",
            }

        articles = db.query(Article).filter(Article.id.in_(article_ids)).all()
        # 计时基准：取最早 pub_date / fetch_time 作为 t0
        timestamps: List[datetime] = []
        for a in articles:
            t = _ensure_aware(a.pub_date) or _ensure_aware(a.fetch_time)
            if t:
                timestamps.append(t)
        if not timestamps:
            return {
                "_id": eid,
                "_type": "event_sentiment",
                "_title": event.title,
                "found": True,
                "article_count": len(articles),
                "labelled_count": 0,
                "hint": "关联文章均无有效时间戳。",
            }
        t0 = min(timestamps)
        t_latest = max(timestamps)

        # 总分布
        labelled_sentiments = [
            (a.ai_sentiment or "").strip().lower()
            for a in articles
            if a.ai_sentiment
        ]
        distribution = dict(Counter(labelled_sentiments))
        labelled = sum(distribution.values())

        # 时序
        bucket_counts: Dict[int, Counter] = defaultdict(Counter)
        for a in articles:
            t = _ensure_aware(a.pub_date) or _ensure_aware(a.fetch_time)
            if not t:
                continue
            sentiment = (a.ai_sentiment or "").strip().lower()
            if not sentiment:
                continue
            idx = _bucket_index(t, t0, bucket)
            bucket_counts[idx][sentiment] += 1

        timeline = []
        if bucket_counts:
            max_idx = max(bucket_counts.keys())
            for i in range(max_idx + 1):
                counter = bucket_counts.get(i, Counter())
                timeline.append({
                    "bucket_index": i,
                    "bucket_start": (t0.timestamp() + i * bucket * 3600),
                    "total": sum(counter.values()),
                    "distribution": dict(counter),
                })

        return {
            "_id": eid,
            "_type": "event_sentiment",
            "_title": event.title,
            "found": True,
            "article_count": len(articles),
            "labelled_count": labelled,
            "bucket_hours": bucket,
            "time_range": {
                "start": t0.isoformat(),
                "end": t_latest.isoformat(),
            },
            "overall_distribution": distribution,
            "timeline": timeline,
        }
    finally:
        db.close()


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "分析单个事件下所有关联文章的情绪分布 + 时序演化。"
        "返回总分布（各标签占比）和按 6/12/24 小时桶划分的情绪时序。"
        "用于回答「事件 X 的舆情倾向」「情绪随时间有没有转折」。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "event_id": {
                "type": "integer",
                "description": "事件 ID",
                "minimum": 1,
            },
            "bucket_hours": {
                "type": "integer",
                "description": "时序桶大小（小时），允许 6/12/24，默认 12",
                "enum": [6, 12, 24],
            },
        },
        "required": ["event_id"],
    },
    handler=_handler,
)

default_registry.register(SPEC)

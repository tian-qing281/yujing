"""
Agent 工具 · rank_events_by_sentiment

按"指定情绪占比"给时间窗口内的事件排序，一步拿 Top-K。

为什么存在：
  M5 评测发现 T4 "近两周情绪最负面的热点事件是哪个" 需要 LLM
  对 N 个候选事件逐一 `get_event_detail` + `analyze_event_sentiment` + 人工比较，
  在 MAX_STEPS=8 内无法收敛。本工具把 O(N) 多跳聚合降为 1 步。

输入：
  window_hours     回看窗口（小时），1 ≤ 值 ≤ 720，默认 336（14 天）
  sentiment        情绪类别。支持：
                     · 聚合类： "negative"（= anger + sadness + disgust + doubt + concern）
                                "positive"（= joy）
                     · 具体标签： neutral / joy / anger / sadness / surprise /
                                 disgust / concern / doubt
                   默认 "negative"
  limit            返回条数，1 ≤ 值 ≤ 20，默认 5
  min_labelled     事件至少需有多少篇已打情绪标签的文章才参与排序，默认 3

输出：
  {
    "window_hours": 336,
    "sentiment": "negative",
    "sentiment_labels": ["anger", "sadness", ...],   # 实际匹配的底层标签
    "total_events_in_window": 57,
    "ranked_count": 5,
    "events": [
      {
        "_id": 12, "_type": "event", "_title": "...",
        "sentiment_share": 0.74, "target_count": 28, "labelled_count": 38,
        "article_count": 41, "heat_score": 89.2,
        "latest_article_time": "2026-04-18T12:00:00"
      }, ...
    ]
  }

性能：一次 JOIN SQL 聚合，无 N+1。5500 event 库下单次调用 < 150ms。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from sqlalchemy import func

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "rank_events_by_sentiment"

DEFAULT_WINDOW_HOURS = 336      # 14 天
DEFAULT_LIMIT = 5
MAX_LIMIT = 20
DEFAULT_MIN_LABELLED = 3
MAX_CANDIDATE_EVENTS = 200      # 先按 heat 取前 200 个候选，避免全表扫

# 与 app.api.routes._EMOTION_LABEL_MAP 对齐的 8 个底层标签
_ALL_LABELS = {"neutral", "concern", "joy", "anger", "sadness", "doubt", "surprise", "disgust"}

# 语义聚合桶。"negative" 囊括负面光谱，供 T4 类 query 直接命中
_SENTIMENT_BUCKETS: Dict[str, List[str]] = {
    "negative": ["anger", "sadness", "disgust", "doubt", "concern"],
    "positive": ["joy"],
    "neutral": ["neutral", "surprise"],
}


def _resolve_labels(sentiment: str) -> List[str]:
    key = (sentiment or "").strip().lower()
    if not key:
        return _SENTIMENT_BUCKETS["negative"]
    if key in _SENTIMENT_BUCKETS:
        return list(_SENTIMENT_BUCKETS[key])
    if key in _ALL_LABELS:
        return [key]
    # 未知值兜底 negative（LLM 偶尔写成中文或拼错时也能拿到合理结果，不浪费一步 self-repair）
    return _SENTIMENT_BUCKETS["negative"]


def _handler(
    window_hours: int = DEFAULT_WINDOW_HOURS,
    sentiment: str = "negative",
    limit: int = DEFAULT_LIMIT,
    min_labelled: int = DEFAULT_MIN_LABELLED,
    **_ignored: Any,
) -> Dict[str, Any]:
    from app.database import Article, Event, EventArticle, SessionLocal, utcnow

    try:
        win = int(window_hours) if window_hours else DEFAULT_WINDOW_HOURS
    except (TypeError, ValueError):
        win = DEFAULT_WINDOW_HOURS
    win = max(1, min(win, 720))

    try:
        lim = int(limit) if limit else DEFAULT_LIMIT
    except (TypeError, ValueError):
        lim = DEFAULT_LIMIT
    lim = max(1, min(lim, MAX_LIMIT))

    try:
        min_lab = int(min_labelled) if min_labelled else DEFAULT_MIN_LABELLED
    except (TypeError, ValueError):
        min_lab = DEFAULT_MIN_LABELLED
    min_lab = max(1, min(min_lab, 50))

    target_labels = _resolve_labels(sentiment)

    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(hours=win)

        candidate_events = (
            db.query(Event)
            .filter(Event.latest_article_time >= cutoff)
            .order_by(Event.heat_score.desc())
            .limit(MAX_CANDIDATE_EVENTS)
            .all()
        )
        total_in_window = len(candidate_events)
        if not candidate_events:
            return {
                "window_hours": win,
                "sentiment": sentiment,
                "sentiment_labels": target_labels,
                "total_events_in_window": 0,
                "ranked_count": 0,
                "events": [],
                "hint": "窗口内无事件。可尝试放大 window_hours。",
            }

        event_ids = [e.id for e in candidate_events]
        event_map = {e.id: e for e in candidate_events}

        # 一次 JOIN 聚合：event_id × ai_sentiment → count
        rows = (
            db.query(
                EventArticle.event_id,
                Article.ai_sentiment,
                func.count(Article.id).label("cnt"),
            )
            .join(Article, Article.id == EventArticle.article_id)
            .filter(EventArticle.event_id.in_(event_ids))
            .filter(Article.ai_sentiment.isnot(None))
            .filter(Article.ai_sentiment != "")
            .group_by(EventArticle.event_id, Article.ai_sentiment)
            .all()
        )

        # 按事件聚合：labelled 总数 + 命中目标标签数
        target_set = set(target_labels)
        per_event: Dict[int, Dict[str, int]] = {}
        for eid, label, cnt in rows:
            norm = (label or "").strip().lower()
            slot = per_event.setdefault(eid, {"labelled": 0, "target": 0})
            slot["labelled"] += int(cnt)
            if norm in target_set:
                slot["target"] += int(cnt)

        ranked: List[Dict[str, Any]] = []
        for eid, stat in per_event.items():
            if stat["labelled"] < min_lab:
                continue
            share = stat["target"] / stat["labelled"] if stat["labelled"] else 0.0
            if share <= 0:
                # 无目标情绪，跳过（top-K 场景没价值）
                continue
            ev = event_map[eid]
            ranked.append({
                "_id": ev.id,
                "_type": "event",
                "_title": ev.title,
                "sentiment_share": round(share, 3),
                "target_count": stat["target"],
                "labelled_count": stat["labelled"],
                "article_count": ev.article_count or 0,
                "heat_score": round(float(ev.heat_score or 0.0), 2),
                "latest_article_time": ev.latest_article_time.isoformat() if ev.latest_article_time else None,
            })

        # 双键排序：情绪占比 desc，平手时按热度 desc 断舍
        ranked.sort(key=lambda x: (-x["sentiment_share"], -x["heat_score"]))
        top = ranked[:lim]

        result: Dict[str, Any] = {
            "window_hours": win,
            "sentiment": sentiment,
            "sentiment_labels": target_labels,
            "total_events_in_window": total_in_window,
            "ranked_count": len(top),
            "events": top,
        }
        if not top:
            result["hint"] = (
                f"窗口内 {total_in_window} 个事件均未达 min_labelled={min_lab} 或无目标情绪。"
                " 可放宽 min_labelled 或检查 ai_sentiment 是否已补全。"
            )
        return result
    finally:
        db.close()


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "按『指定情绪占比』对时间窗口内的事件排序，一步拿 Top-K。"
        "专门解决『最负面/最正面/最让人担忧的热点是哪个』这类聚合 query，"
        "避免 LLM 对 N 个事件逐一 get_event_detail + analyze_event_sentiment 的 O(N) 多跳做法。"
        "sentiment 支持聚合类 negative/positive/neutral，或具体标签 "
        "anger/sadness/joy/disgust/doubt/concern/surprise/neutral。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "window_hours": {
                "type": "integer",
                "description": "回看窗口（小时），1 ≤ 值 ≤ 720，默认 336（14 天）",
                "minimum": 1,
                "maximum": 720,
            },
            "sentiment": {
                "type": "string",
                "description": (
                    "情绪类别。聚合类：negative / positive / neutral；"
                    "具体标签：anger / sadness / disgust / doubt / concern / joy / surprise / neutral。"
                    "默认 'negative'。"
                ),
                "enum": [
                    "negative", "positive", "neutral",
                    "anger", "sadness", "disgust", "doubt", "concern",
                    "joy", "surprise",
                ],
            },
            "limit": {
                "type": "integer",
                "description": "返回条数，1 ≤ 值 ≤ 20，默认 5",
                "minimum": 1,
                "maximum": 20,
            },
            "min_labelled": {
                "type": "integer",
                "description": "事件至少需要多少篇打标文章才参与排序，默认 3（过滤噪声）",
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": [],
    },
    handler=_handler,
)

default_registry.register(SPEC)

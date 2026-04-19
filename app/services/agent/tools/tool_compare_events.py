"""
Agent 工具 · compare_events

给 2-4 个 event_id，并排输出对比指标：规模（article_count / platform_count）、
热度（heat_score）、情绪、关键词、时间窗、主要平台。

用于场景：
- "苹果 vs 华为发布会哪个讨论更多"
- "两次极端天气事件舆情强度对比"
- "伊朗 / 以色列 / 沙特三个相关事件的平台分布差异"

输出里包含 `comparison_summary`：关键词并集 / 交集、最大 article_count 事件、
最正向 / 负向事件，降低 LLM 做数字比较的出错率。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "compare_events"
MIN_EVENTS = 2
MAX_EVENTS = 4


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


def _marshal_event(event) -> Dict[str, Any]:
    return {
        "_id": event.id,
        "_type": "event",
        "_title": event.title,
        "article_count": event.article_count or 0,
        "platform_count": event.platform_count or 0,
        "heat_score": round(float(event.heat_score or 0.0), 2),
        "sentiment": event.sentiment or "neutral",
        "primary_source_id": event.primary_source_id or "",
        "latest_article_time": event.latest_article_time.isoformat() if event.latest_article_time else None,
        "keywords": _parse_keywords(event.keywords),
    }


def _handler(event_ids: Any = None, **_ignored: Any) -> Dict[str, Any]:
    from app.database import Event, SessionLocal

    # event_ids 可能来自 LLM 的各种格式：list / tuple / JSON string / 单值
    raw_ids: List[int] = []
    if isinstance(event_ids, (list, tuple)):
        for x in event_ids:
            try:
                raw_ids.append(int(x))
            except (TypeError, ValueError):
                continue
    elif isinstance(event_ids, str):
        try:
            parsed = json.loads(event_ids)
            if isinstance(parsed, list):
                for x in parsed:
                    try:
                        raw_ids.append(int(x))
                    except (TypeError, ValueError):
                        continue
        except json.JSONDecodeError:
            raise ValueError(
                f"event_ids 必须是整数数组或 JSON 数组字符串，收到 {event_ids!r}"
            )
    elif isinstance(event_ids, int):
        raw_ids.append(event_ids)

    # 去重保序
    seen: set = set()
    deduped: List[int] = []
    for i in raw_ids:
        if i > 0 and i not in seen:
            seen.add(i)
            deduped.append(i)

    if len(deduped) < MIN_EVENTS:
        raise ValueError(
            f"event_ids 至少需要 {MIN_EVENTS} 个（去重后仅 {len(deduped)} 个）"
        )
    if len(deduped) > MAX_EVENTS:
        deduped = deduped[:MAX_EVENTS]

    db = SessionLocal()
    try:
        events = db.query(Event).filter(Event.id.in_(deduped)).all()
        found_map = {e.id: e for e in events}
        missing = [i for i in deduped if i not in found_map]
        ordered = [found_map[i] for i in deduped if i in found_map]

        marshaled = [_marshal_event(e) for e in ordered]

        # 对比摘要
        comparison: Dict[str, Any] = {}
        if marshaled:
            # 关键词交集 / 并集
            keyword_sets = [set(item["keywords"]) for item in marshaled]
            intersect = set.intersection(*keyword_sets) if keyword_sets else set()
            union = set.union(*keyword_sets) if keyword_sets else set()

            max_article = max(marshaled, key=lambda x: x["article_count"])
            max_heat = max(marshaled, key=lambda x: x["heat_score"])

            comparison = {
                "events_compared": len(marshaled),
                "keyword_intersection": sorted(intersect),
                "keyword_union": sorted(union),
                "max_article_count": {
                    "_id": max_article["_id"],
                    "_title": max_article["_title"],
                    "value": max_article["article_count"],
                },
                "max_heat": {
                    "_id": max_heat["_id"],
                    "_title": max_heat["_title"],
                    "value": max_heat["heat_score"],
                },
                "sentiment_distribution": {
                    item["sentiment"]: sum(
                        1 for x in marshaled if x["sentiment"] == item["sentiment"]
                    )
                    for item in marshaled
                },
            }

        return {
            "_type": "event_comparison",
            "requested_ids": deduped,
            "missing_ids": missing,
            "events": marshaled,
            "comparison_summary": comparison,
        }
    finally:
        db.close()


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "并排对比 2-4 个事件的规模、热度、情绪、关键词。"
        "传入 event_ids（整数数组）。"
        "输出还会包含关键词交/并集、最大热度事件等摘要，方便直接回答对比问题。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "event_ids": {
                "type": "array",
                "description": "要对比的事件 ID 数组（2-4 个）",
                "items": {"type": "integer", "minimum": 1},
                "minItems": MIN_EVENTS,
                "maxItems": MAX_EVENTS,
            },
        },
        "required": ["event_ids"],
    },
    handler=_handler,
)

default_registry.register(SPEC)

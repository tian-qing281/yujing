"""
Agent 工具 · compare_platforms_radar （F5 N 平台雷达图）

把任意 N 个平台（2~6 个）按 5 个维度归一化到 0~100 分，输出可被
前端 CompareDashboard 直接渲染为 ECharts 雷达图：

5 个维度（向用户讲故事的"舆情画像"轴）：
  1. 情报量      —— article_count（log10 归一，FULL=5000 篇 ≈ 满分）
  2. 事件覆盖   —— event_count（线性归一，FULL=8 个 = 满分）
  3. 情绪鲜明度 —— (positive+negative+surprise) / total × 1000（cap 100）
                  反映"被 AI 情绪标注且非中性"的占比，能拉开未做情绪标注 vs 已标注的平台
  4. 24h 时效   —— c_0_24 / max(sample, 1) × 100（cap 100）
                  反映该平台过去 24h 新增热点占样本比例（越高越活跃）
  5. 单事件规模 —— log10(articles/events + 1) / log10(101) × 100，events=0 → 0
                  反映平台单个事件平均报道量（越高越聚焦）

输出 schema（前端 CompareDashboard 兼容新分支 `_type === "platform_radar"`）：
  {
    "_type": "platform_radar",
    "dimensions": ["情报量", "事件覆盖", "正向情绪", "24h增长", "代表事件密度"],
    "platforms": [
      {"label": "微博", "source_id": "weibo_hot_search",
       "raw": {...原 metrics...},
       "scores": [85, 60, 35, 70, 55]},
      ...
    ],
    "topic": "...",
    "leader": {"dim_index": 0, "label": "微博"}   # 各维度领跑者
  }

不走 LLM；一次 SQL 聚合返回。复用 _build_compare_metrics + _resolve_compare_source。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from app.services.agent.registry import default_registry
from app.services.agent.schemas import ToolSpec


TOOL_NAME = "compare_platforms_radar"
# 情报量上限要远大于"满分阈值"，让真实差异在雷达上看得见；
# 否则各平台都拉到上限会同时触顶导致维度退化。
MAX_ARTICLES_PER_SIDE = 300
MAX_EVENTS_PER_SIDE = 8
FULL_SCORE_ARTICLE = 5000  # 真实总文章数 5000 ≈ 满分（log 归一）
FULL_SCORE_EVENT = MAX_EVENTS_PER_SIDE
MAX_PLATFORMS = 6
MIN_PLATFORMS = 2

DIMENSIONS = ["情报量", "事件覆盖", "情绪鲜明度", "24h时效", "单事件规模"]


def _gather_side(db, name: str, topic: str):
    """复用 compare_platforms 的取数策略，保持指标口径一致。

    返回 (items, total_count, events, source_id)：
      - items: 最近 MAX_ARTICLES_PER_SIDE 条用于情绪/24h 等明细统计
      - total_count: 该平台真实总文章数（用于雷达情报量维度，避免被采样上限截顶）
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
    total_count = q.count()
    items = q.order_by(Article.fetch_time.desc()).limit(MAX_ARTICLES_PER_SIDE).all()

    search_query = topic if (source_id and topic) else name
    evts = search_events(db, search_query, limit=MAX_EVENTS_PER_SIDE) if search_query else []
    return items, total_count, evts, source_id


def _score_dimensions(metrics: Dict[str, Any], total_count: int) -> List[float]:
    """把单平台 metrics 折算为 5 维 0~100 评分。total_count = 该平台真实文章总数。"""
    article_count = max(int(total_count or 0), int(metrics.get("article_count") or 0))
    sample_count = int(metrics.get("article_count") or 0)  # 取样本数（最多 MAX_ARTICLES_PER_SIDE）
    event_count = int(metrics.get("event_count") or 0)
    sentiment = metrics.get("sentiment") or {}
    pos = int(sentiment.get("positive") or 0)
    neg = int(sentiment.get("negative") or 0)
    sur = int(sentiment.get("surprise") or 0)
    total_sent = sum(int(v) for v in sentiment.values()) or 1
    trend = metrics.get("trend_24h") or {}
    c_0_24 = int(trend.get("current") or 0)

    # 1. 情报量：log10 归一，FULL_SCORE_ARTICLE 篇 ≈ 满分
    s1 = min(100.0, math.log10(article_count + 1) / math.log10(FULL_SCORE_ARTICLE + 1) * 100.0)
    # 2. 事件覆盖：FULL_SCORE_EVENT 个事件 = 满分
    s2 = min(100.0, event_count / FULL_SCORE_EVENT * 100.0)
    # 3. 情绪鲜明度：非中性占比 × 25 倍率（当前数据集情绪标注极稀疏，常规 ×1 几乎全 0）
    s3 = min(100.0, (pos + neg + sur) / max(sample_count, 1) * 100.0 * 25.0)
    # 4. 24h 时效：过去 24h 新增 / 样本数（越高越活跃）
    s4 = min(100.0, c_0_24 / max(sample_count, 1) * 100.0)
    # 5. 单事件规模：log10(articles/events + 1)/log10(2001) × 100，events=0 → 0
    if event_count > 0:
        per_event = article_count / event_count
        s5 = min(100.0, math.log10(per_event + 1) / math.log10(2001) * 100.0)
    else:
        s5 = 0.0

    return [round(s1, 1), round(s2, 1), round(s3, 1), round(s4, 1), round(s5, 1)]


def _handler(
    platforms: Any = None,
    topic: Any = "",
    **_ignored: Any,
) -> Dict[str, Any]:
    from app.api.routes import _build_compare_metrics
    from app.database import SessionLocal

    if not isinstance(platforms, list):
        raise ValueError("platforms 必须是字符串数组（2~6 个平台名）")
    names = [str(p).strip() for p in platforms if isinstance(p, (str, int)) and str(p).strip()]
    # 去重保持顺序
    seen = set()
    uniq = []
    for n in names:
        if n not in seen:
            seen.add(n)
            uniq.append(n)
    if len(uniq) < MIN_PLATFORMS:
        raise ValueError(f"至少需要 {MIN_PLATFORMS} 个平台，去重后只有 {len(uniq)} 个")
    if len(uniq) > MAX_PLATFORMS:
        uniq = uniq[:MAX_PLATFORMS]

    topic_str = (topic or "").strip() if isinstance(topic, str) else ""

    db = SessionLocal()
    try:
        result_platforms: List[Dict[str, Any]] = []
        for name in uniq:
            articles, total_count, events, source_id = _gather_side(db, name, topic_str)
            metrics = _build_compare_metrics(name, articles, events)
            scores = _score_dimensions(metrics, total_count)
            result_platforms.append({
                "label": name,
                "source_id": source_id,
                "scores": scores,
                "raw": {
                    "article_count": total_count,
                    "sample_count": metrics["article_count"],
                    "event_count": metrics["event_count"],
                    "sentiment": metrics["sentiment"],
                    "trend_24h": metrics["trend_24h"],
                },
            })

        # 各维度领跑者：方便 LLM 直接讲"X 平台在 Y 维度领先"
        leaders: List[Dict[str, Any]] = []
        for i, dim_name in enumerate(DIMENSIONS):
            best_idx = max(range(len(result_platforms)), key=lambda k: result_platforms[k]["scores"][i])
            leaders.append({
                "dim_index": i,
                "dim_name": dim_name,
                "label": result_platforms[best_idx]["label"],
                "score": result_platforms[best_idx]["scores"][i],
            })

        return {
            "_type": "platform_radar",
            "dimensions": DIMENSIONS,
            "platforms": result_platforms,
            "topic": topic_str or None,
            "leaders": leaders,
        }
    finally:
        db.close()


SPEC = ToolSpec(
    name=TOOL_NAME,
    description=(
        "用 5 维雷达图对比 2~6 个平台的舆情画像（情报量 / 事件覆盖 / 情绪鲜明度 / "
        "24h 时效 / 单事件规模）。每个维度归一化到 0~100 分。"
        "输出可直接被前端雷达图渲染。"
        "适用于 '画一张多平台对比雷达图' / '对比微博 知乎 头条 三个平台' / "
        "'各平台对 X 主题的舆情画像差异' 这类问题。"
        "若只需对比 2 个平台并需要时间轴 / 代表情报详情，请改用 compare_platforms。"
    ),
    input_schema={
        "type": "object",
        "properties": {
            "platforms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "平台名数组，2~6 个。如 ['微博','知乎','头条','百度','B站']",
                "minItems": 2,
                "maxItems": 6,
            },
            "topic": {
                "type": "string",
                "description": "（可选）主题过滤词，对比各平台对该主题的舆情画像",
                "default": "",
            },
        },
        "required": ["platforms"],
    },
    handler=_handler,
)

default_registry.register(SPEC)

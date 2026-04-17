import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import case, or_, text
from sqlalchemy.orm import Session

from app.crawler.reader import (
    check_credential_exists,
    extract_article_content,
    save_cookie_credential,
)
from app.crawler.sources.baidu import BaiduHotSearch
from app.crawler.sources.bilibili import BilibiliHotVideo
from app.crawler.sources.cls import ClsTelegraph
from app.crawler.sources.thepaper import ThePaperHotNews
from app.crawler.sources.toutiao import ToutiaoHotBoard
from app.crawler.sources.weibo import WeiboHotSearch
from app.crawler.sources.wallstreetcn import WallstreetcnNews
from app.crawler.sources.zhihu import ZhihuHotQuestion
from app.database import Article, Event, EventArticle, SessionLocal, Topic, TopicEvent
from app.schemas import (
    ArticleResponse,
    ChatRequest,
    ChatResponse,
    CompareRequest,
    EventDetailResponse,
    EventResponse,
    TopicDetailResponse,
    TopicResponse,
)
from app.services.emotion import emotion_engine
from app.services.events import classify_event_confidence, ensure_events, rebuild_events, search_events
from app.services.search_engine import meili
from app.services.topics import ensure_topics, rebuild_topics, search_topics


router = APIRouter()

SOURCE_IDS = [
    "weibo_hot_search",
    "baidu_hot",
    "toutiao_hot",
    "bilibili_hot_video",
    "zhihu_hot_question",
    "thepaper_hot",
    "wallstreetcn_news",
    "cls_telegraph",
]

SOURCE_NAME_MAP = {
    "weibo_hot_search": "微博热搜榜",
    "baidu_hot": "百度热搜榜",
    "toutiao_hot": "头条实时榜",
    "bilibili_hot_video": "哔哩哔哩榜",
    "zhihu_hot_question": "知乎全站榜",
    "thepaper_hot": "澎湃热榜",
    "wallstreetcn_news": "华尔街见闻热榜",
    "cls_telegraph": "财联社热榜",
}

COOKIE_SOURCE_IDS = [
    "weibo_hot_search",
    "baidu_hot",
    "toutiao_hot",
    "bilibili_hot_video",
    "zhihu_hot_question",
]

PUBLIC_SOURCE_IDS = [
    "thepaper_hot",
    "wallstreetcn_news",
    "cls_telegraph",
]

PLATFORM_MAP = {
    "微博": "weibo_hot_search",
    "百度": "baidu_hot",
    "头条": "toutiao_hot",
    "今日头条": "toutiao_hot",
    "bilibili": "bilibili_hot_video",
    "B站": "bilibili_hot_video",
    "b站": "bilibili_hot_video",
    "哔哩哔哩": "bilibili_hot_video",
    "知乎": "zhihu_hot_question",
    "澎湃": "thepaper_hot",
    "澎湃热点": "thepaper_hot",
    "澎湃热榜": "thepaper_hot",
    "华尔街": "wallstreetcn_news",
    "华尔街见闻": "wallstreetcn_news",
    "华尔街见闻热榜": "wallstreetcn_news",
    "财联社": "cls_telegraph",
    "财联社热榜": "cls_telegraph",
}

swr_cache = {
    "articles": [],
    "last_fetch": 0.0,
    "fetching": False,
    "events": [],
    "events_last_fetch": 0.0,
    "topics": [],
    "topics_last_fetch": 0.0,
}
swr_state_lock = asyncio.Lock()
event_hub_refresh_lock = threading.Lock()
_shutting_down = threading.Event()

# 极致优化：全景看板端点缓存，针对空查询的高频维度切换提供 60s 内存屏障
unified_search_cache = {}

analysis_cache = {}

# -- analyze 并发控制 --------------------------------------------------------
# 全局并发上限：同时最多 3 篇在跑深度分析（抓取+BERT+LLM），保护线程池与下游 API
_analyze_global_semaphore = asyncio.Semaphore(3)
# article_id -> asyncio.Event，相同文章二次请求等首次完成后直接读缓存
_analyze_inflight: dict[int, asyncio.Event] = {}
_analyze_inflight_lock = asyncio.Lock()


def _invalidate_event_hub_cache():
    swr_cache["events"] = []
    swr_cache["events_last_fetch"] = 0.0
    swr_cache["topics"] = []
    swr_cache["topics_last_fetch"] = 0.0


def _update_event_hub_cache(events_payload, topics_payload, *, allow_empty: bool = False):
    if events_payload or allow_empty:
        swr_cache["events"] = events_payload
        swr_cache["events_last_fetch"] = time.time()
    if topics_payload or allow_empty:
        swr_cache["topics"] = topics_payload
        swr_cache["topics_last_fetch"] = time.time()


def _cache_stale_against_model(db: Session, model, cache_ts: float) -> bool:
    if cache_ts <= 0:
        return True
    latest_row = db.query(model).order_by(model.updated_at.desc()).first()
    if not latest_row or not getattr(latest_row, "updated_at", None):
        return False
    return latest_row.updated_at.timestamp() > cache_ts


def _clip_log_text(value: str, limit: int = 1600) -> str:
    if not value:
        return ""
    return str(value).replace("\r", "")[:limit]


def _print_analysis_debug(article: Article, markdown_content: str):
    extra_info_raw = article.extra_info or ""
    try:
        extra_info = json.loads(extra_info_raw) if extra_info_raw else {}
    except Exception:
        extra_info = {"raw": _clip_log_text(extra_info_raw, 600)}

    debug_meta = {
        "article_id": article.id,
        "title": article.title,
        "url": article.url,
        "source_id": article.source_id,
        "rank": article.rank,
        "extra_info": extra_info,
    }
    print("--- ANALYZE ARTICLE META START ---")
    print(json.dumps(debug_meta, ensure_ascii=False, indent=2))
    print("--- ANALYZE ARTICLE META END ---")

    if isinstance(markdown_content, str) and markdown_content.startswith("JSON_STREAM_LIST:"):
        try:
            stream = json.loads(markdown_content.replace("JSON_STREAM_LIST:", "", 1))
            print("--- ANALYZE CRAWLED JSON START ---")
            print(json.dumps(stream[:8], ensure_ascii=False, indent=2))
            print("--- ANALYZE CRAWLED JSON END ---")
            return
        except Exception as exc:
            print(f"[ANALYZE_DEBUG] structured parse failed: {exc}")

    print("--- ANALYZE RAW MATERIAL START ---")
    print(_clip_log_text(markdown_content, 3000))
    print("--- ANALYZE RAW MATERIAL END ---")


def _is_invalid_cached_content(content: str) -> bool:
    if not content:
        return True

    normalized = str(content).strip()
    lowered = normalized.lower()

    markers = [
        "❌",
        "鉂",
        "[凭据失效]",
        "[抓取失败]",
        "您需要允许该网站执行 JavaScript",
        "返回了前端壳资源",
        "安全验证 - 知乎",
        "系统监测到您的网络环境存在异常风险",
        "核心标题:",
        "扩展信息:",
        "原始链接抓取受限",
        "当前基于基础情报进行分析",
    ]
    if any(marker in normalized for marker in markers):
        return True

    if normalized.startswith("核心标题") or normalized.startswith("????"):
        return True

    if '"hot_value"' in lowered and ("扩展信息" in normalized or normalized.count("?") > 8):
        return True

    return False


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _build_article_match_reasons(query: str, title: str = "", summary: str = "", source_name: str = "") -> List[str]:
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return []

    terms = [normalized_query.strip('"')]
    terms.extend([part for part in normalized_query.split() if part])
    terms = [term for term in terms if term]

    def contains(value: str) -> bool:
        haystack = (value or "").lower()
        return any(_term_matches_haystack(term, haystack) for term in terms)

    reasons = []
    if contains(title):
        reasons.append("标题命中")
    if contains(summary):
        reasons.append("摘要命中")
    if contains(source_name):
        reasons.append("来源命中")
    return reasons


def _normalize_article_extra_info(source_id: str, extra_info: str = "{}") -> str:
    try:
        parsed = json.loads(extra_info or "{}")
    except Exception:
        return extra_info or "{}"

    if source_id in {"thepaper_hot", "wallstreetcn_news"}:
        # These APIs expose ranking, not a stable numeric heat value. Strip old fallback scores.
        parsed.pop("hot_value", None)
        parsed.pop("hot_score", None)

    if source_id == "cls_telegraph":
        hot_value = parsed.get("hot_value")
        try:
            numeric_hot = int(float(str(hot_value).replace(",", ""))) if hot_value not in (None, "") else 0
        except Exception:
            numeric_hot = 0
        if numeric_hot and numeric_hot <= 30:
            parsed.pop("hot_value", None)

    return json.dumps(parsed, ensure_ascii=False)


def marshal_article(art, query: str = "", search_hit: dict | None = None):
    if hasattr(art, "__table__"):
        data = {column.name: getattr(art, column.name) for column in art.__table__.columns}
    else:
        data = dict(art._mapping if hasattr(art, "_mapping") else art)

    extra_info = _normalize_article_extra_info(data.get("source_id"), data.get("extra_info", "{}"))
    source_name = ""
    try:
        parsed_extra = json.loads(extra_info or "{}")
        source_name = str(parsed_extra.get("author") or parsed_extra.get("source") or "")
    except Exception:
        parsed_extra = {}

    highlighted_title = ""
    highlighted_excerpt = ""
    if search_hit:
        formatted = search_hit.get("_formatted") or {}
        highlighted_title = formatted.get("title") or ""
        highlighted_excerpt = (
            formatted.get("ai_summary")
            or formatted.get("excerpt")
            or ""
        )

    return {
        "id": data.get("id"),
        "source_id": data.get("source_id"),
        "item_id": data.get("item_id"),
        "rank": data.get("rank", 99),
        "title": data.get("title", "无标题情报"),
        "url": data.get("url", ""),
        "pub_date": data.get("pub_date").isoformat() if data.get("pub_date") else None,
        "extra_info": extra_info,
        "ai_summary": data.get("ai_summary", ""),
        "ai_sentiment": data.get("ai_sentiment", "neutral"),
        "content": data.get("content", ""),
        "fetch_time": data.get("fetch_time").isoformat() if data.get("fetch_time") else None,
        "search_match_reasons": _build_article_match_reasons(
            query,
            title=data.get("title", ""),
            summary=data.get("ai_summary", "") or parsed_extra.get("excerpt", "") or parsed_extra.get("desc", ""),
            source_name=source_name,
        ),
        "search_highlight_title": highlighted_title,
        "search_highlight_excerpt": highlighted_excerpt,
    }


def _build_match_reasons(query: str, title: str = "", summary: str = "", keywords: List[str] = None) -> List[str]:
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return []

    tokens = [normalized_query.strip('"')]
    tokens.extend([part for part in normalized_query.split() if part])
    tokens = [token for token in tokens if token]

    def contains(value: str) -> bool:
        text = (value or "").lower()
        return any(_term_matches_haystack(token, text) for token in tokens)

    reasons = []
    if contains(title):
        reasons.append("标题命中")
    if contains(summary):
        reasons.append("摘要命中")
    if any(contains(str(keyword)) for keyword in (keywords or [])):
        reasons.append("关键词命中")
    return reasons


def _merge_facet_counts(*facet_maps) -> Dict[str, int]:
    merged: Dict[str, int] = {}
    for facet_map in facet_maps:
        if not isinstance(facet_map, dict):
            continue
        for key, value in facet_map.items():
            if not key:
                continue
            merged[key] = merged.get(key, 0) + int(value or 0)
    return merged


def _top_named_buckets(bucket_map: Dict[str, int], limit: int = 8) -> List[Dict]:
    rows = [{"value": key, "count": count} for key, count in bucket_map.items() if key]
    rows.sort(key=lambda item: (item["count"], len(item["value"])), reverse=True)
    return rows[:limit]


def _normalize_axis_term(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    value = re.sub(r"进入第\s*\d+\s*天", "", value, flags=re.IGNORECASE)
    value = re.sub(r"第\s*\d+\s*天", "", value, flags=re.IGNORECASE)
    value = re.sub(r"第\s*\d+\s*小时", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\d+\s*(分钟|小时|天)前", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[【】\[\]（）()“”\"'：:、,，。.？?！!…/|·\-_]+", "", value)
    value = value.strip()
    alias_map = {
        "伊方": "伊朗",
        "伊军": "伊朗",
        "伊媒": "伊朗",
        "美方": "美国",
        "美军": "美国",
        "白宫": "美国",
        "以方": "以色列",
        "以军": "以色列",
        "apple": "苹果",
        "iphone": "苹果",
        "ios": "苹果",
        "ipad": "苹果",
        "su7": "小米",
    }
    lowered = value.lower()
    return alias_map.get(lowered, alias_map.get(value, value))


def _normalize_axis_query(raw: str) -> str:
    value = str(raw or "").lower().strip()
    value = re.sub(r"[【】\[\]（）()“”\"'：:、,，。.？?！!…/|·\-_]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _query_terms(raw: str) -> List[str]:
    normalized = _normalize_axis_query(raw or "")
    if not normalized:
        return []
    terms = [normalized]
    terms.extend(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", normalized))
    seen = set()
    ordered = []
    for term in terms:
        token = str(term or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return ordered


def _term_matches_haystack(term: str, haystack: str) -> bool:
    token = str(term or "").strip().lower()
    text = str(haystack or "").strip().lower()
    if not token or not text:
        return False
    if token.isdigit():
        return re.search(rf"(?<!\d){re.escape(token)}(?!\d)", text) is not None
    return token in text


def _row_matches_query(query: str, title: str = "", summary: str = "", keywords: List[str] = None, highlights: List[str] = None) -> bool:
    terms = _query_terms(query)
    if not terms:
        return True
    if all(str(term).isdigit() for term in terms):
        haystacks = [
            _normalize_axis_query(title),
            _normalize_axis_query(summary),
            *[_normalize_axis_query(value) for value in (highlights or [])],
        ]
        return any(_term_matches_haystack(term, haystack) for term in terms for haystack in haystacks if haystack)
    haystacks = [
        _normalize_axis_query(title),
        _normalize_axis_query(summary),
        *[_normalize_axis_query(keyword) for keyword in (keywords or [])],
        *[_normalize_axis_query(value) for value in (highlights or [])],
    ]
    return any(_term_matches_haystack(term, haystack) for term in terms for haystack in haystacks if haystack)


def _filter_query_matched_rows(rows: List[Dict], query: str, row_type: str = "event") -> List[Dict]:
    if not query:
        return rows

    numeric_only_query = all(str(term).isdigit() for term in _query_terms(query))
    filtered = []
    for row in rows:
        reasons = [] if numeric_only_query else (row.get("match_reasons") or row.get("search_match_reasons") or [])
        highlights = [
            row.get("search_highlight_title") or "",
            row.get("search_highlight_summary") or "",
            row.get("search_highlight_excerpt") or "",
        ]
        if reasons or _row_matches_query(
            query=query,
            title=row.get("title", ""),
            summary=row.get("summary", "") or row.get("ai_summary", "") or "",
            keywords=row.get("keywords") or [],
            highlights=highlights,
        ):
            filtered.append(row)
            continue

        if row_type == "topic" and _row_matches_query(
            query=query,
            title=row.get("title", ""),
            summary=row.get("summary", ""),
            keywords=row.get("keywords") or [],
            highlights=highlights,
        ):
            filtered.append(row)

    return filtered


def _platform_rows_from_payload(*payload_groups: List[Dict], limit: int = 6) -> List[Dict]:
    counter: Dict[str, int] = {}
    for rows in payload_groups:
        for row in rows or []:
            source_id = str(row.get("primary_source_id") or row.get("source_id") or "").strip()
            if not source_id:
                continue
            counter[source_id] = counter.get(source_id, 0) + 1
    return _top_named_buckets(counter, limit=limit)


def _clean_axis_buckets(bucket_map: Dict[str, int], limit: int = 8) -> List[Dict]:
    blocked_fragments = {
        "当前局势",
        "值得关注",
        "如何",
        "哪些",
        "进入第",
        "小时",
        "分钟",
        "最新",
        "回应",
        "现场画面",
        "完整版",
        "实时追踪",
        "继续更新",
    }
    blocked_exact = {
        "ai",
        "vs",
        "up",
        "mv",
        "bgm",
        "cp",
        "dna",
        "ip",
        "hot",
        "news",
        "视频",
        "直播",
        "热搜",
        "话题",
        "全文",
        "军方",
        "战争",
        "战事",
        "局势",
    }
    trusted_terms = {"伊朗", "美国", "以色列", "苹果", "小米", "nba", "oppo", "openai", "deepseek", "停火", "谈判"}
    merged: Dict[str, int] = {}
    for key, value in bucket_map.items():
        cleaned = _normalize_axis_term(key)
        if not cleaned:
            continue
        if cleaned.lower() in blocked_exact:
            continue
        if re.fullmatch(r"[a-z0-9]+", cleaned.lower()) and cleaned.lower() not in trusted_terms:
            continue
        if len(cleaned) < 2 or len(cleaned) > 8:
            continue
        if re.fullmatch(r"\d+", cleaned):
            continue
        if any(fragment in cleaned for fragment in blocked_fragments):
            continue
        merged[cleaned] = merged.get(cleaned, 0) + int(value or 0)
    merged = {key: value for key, value in merged.items() if value >= 2 or key in trusted_terms}
    rows = _top_named_buckets(merged, limit=limit)
    for row in rows:
        row["type"] = _classify_axis_term(row["value"])
    return rows


def _classify_axis_term(term: str) -> str:
    raw = str(term or "").strip()
    value = raw.lower()
    if not value:
        return "topic"

    country_terms = {
        "伊朗", "美国", "以色列", "俄罗斯", "乌克兰", "中国", "日本", "韩国", "越南", "巴勒斯坦",
    }
    brand_terms = {
        "iphone", "apple", "ipad", "ios", "苹果", "小米", "华为", "特斯拉", "英伟达", "nba",
    }
    person_terms = {
        "特朗普", "拜登", "雷军", "库克", "马斯克", "周劼", "华晨宇", "黎巴嫩", "苏林",
    }
    topic_fragments = {
        "停火", "关税", "外交部", "论文", "救援", "撞脸", "民宿", "电话", "拍深山", "救流浪女", "谈判", "房贷", "利率",
        "战争", "战事", "局势", "冲突", "军方", "军援", "导弹", "常规赛", "季后赛", "比赛", "总决赛",
        "冰淇淋", "食堂", "雪糕", "午餐", "晚餐", "餐厅", "价格", "产品", "服务", "通知", "咖啡", "奶茶", "外卖",
    }

    if value in {item.lower() for item in country_terms}:
        return "country"
    if value in {item.lower() for item in brand_terms}:
        return "brand"
    if value in {item.lower() for item in topic_fragments} or any(fragment in raw for fragment in topic_fragments):
        return "topic"
    if value in {item.lower() for item in person_terms}:
        return "person"

    if any(token in raw for token in ["国", "方", "军", "政府", "外交部", "总统", "总理", "大使"]):
        return "country"
    if any(token in value for token in ["iphone", "apple", "ios", "su7", "ipad", "华为", "小米", "英伟达", "特斯拉"]):
        return "brand"
    
    # Heuristic for Chinese Names: 2-3 characters, avoiding common topic suffix/prefix
    if len(raw) <= 3 and re.fullmatch(r"[\u4e00-\u9fff]{2,3}", raw):
        # Additional guard: don't classify common item suffixes as people (like '场', '馆', '厅')
        if not any(suffix in raw for suffix in ["场", "馆", "厅", "室", "店", "车", "房", "费"]):
            return "person"
            
    return "topic"


def _derive_axes_from_payload(events_payload: List[Dict], topics_payload: List[Dict], limit: int = 8, query: str = "") -> List[Dict]:
    counter: Dict[str, int] = {}
    normalized_query = _normalize_axis_query(query or "")
    terms = [normalized_query] if normalized_query else []
    if normalized_query:
        terms.extend([part for part in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", normalized_query) if part])
    for row in [*topics_payload, *events_payload]:
        haystack = " ".join(
            [
                _normalize_axis_query(row.get("title", "")),
                _normalize_axis_query(row.get("summary", "")),
                " ".join(_normalize_axis_query(keyword) for keyword in (row.get("keywords") or [])),
            ]
        )
        if terms and not any(term and term in haystack for term in terms):
            continue
        for keyword in (row.get("keywords") or [])[:4]:
            cleaned = _normalize_axis_term(keyword)
            if not cleaned:
                continue
            counter[cleaned] = counter.get(cleaned, 0) + 1
    return _clean_axis_buckets(counter, limit=limit)


def _merge_axis_rows(facet_axes: List[Dict], payload_axes: List[Dict], limit: int = 8, query: str = "") -> List[Dict]:
    normalized_query = _normalize_axis_query(query or "")
    query_terms = {normalized_query} if normalized_query else set()
    if normalized_query:
        query_terms.update(part for part in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", normalized_query) if part)
    merged: Dict[str, Dict] = {}
    for row in payload_axes:
        value = row.get("value")
        if not value:
            continue
        merged[value] = {
            "value": value,
            "count": int(row.get("count") or 0) + 3,
            "type": row.get("type") or "topic",
        }
    payload_values = set(merged.keys())
    for row in facet_axes:
        value = row.get("value")
        if not value:
            continue
        normalized_value = _normalize_axis_query(value)
        if query_terms and value not in payload_values and normalized_value not in query_terms:
            continue
        current = merged.get(value)
        if current:
            current["count"] += int(row.get("count") or 0)
            current["type"] = current.get("type") or row.get("type") or "topic"
        else:
            merged[value] = {
                "value": value,
                "count": int(row.get("count") or 0),
                "type": row.get("type") or "topic",
            }
    rows = list(merged.values())
    rows.sort(key=lambda item: (item["count"], len(item["value"])), reverse=True)
    return rows[:limit]


def _article_result_score(row: Dict) -> float:
    reasons = row.get("search_match_reasons") or []
    fetch_time = row.get("fetch_time") or ""
    recency = 0.0
    try:
        if fetch_time:
            recency = datetime.fromisoformat(fetch_time).timestamp()
    except Exception:
        recency = 0.0
    return (
        len(reasons) * 60
        + (20 if row.get("search_highlight_title") else 0)
        + (14 if row.get("search_highlight_excerpt") else 0)
        + (12 if row.get("ai_summary") else 0)
        + (8 if row.get("content") else 0)
        + max(0, 120 - min(int(row.get("rank") or 99), 120))
        + recency / 100000000
    )


def _dedupe_payload_by_title(rows: List[Dict], title_key: str = "title") -> List[Dict]:
    deduped: Dict[str, Dict] = {}
    for row in rows:
        title = str(row.get(title_key) or "").strip()
        if not title:
            continue
        key = re.sub(r"\s+", "", title.lower())
        current = deduped.get(key)
        if not current:
            deduped[key] = row
            continue
        current_score = (
            (current.get("article_count") or 0) * 10
            + (current.get("platform_count") or 0) * 6
            + (current.get("event_count") or 0) * 8
        )
        next_score = (
            (row.get("article_count") or 0) * 10
            + (row.get("platform_count") or 0) * 6
            + (row.get("event_count") or 0) * 8
        )
        if next_score > current_score:
            deduped[key] = row
    return list(deduped.values())


def _meili_total(result: dict) -> int:
    if not isinstance(result, dict):
        return 0
    total = result.get("estimatedTotalHits")
    if total is None:
        total = result.get("totalHits")
    if total is None:
        total = len(result.get("hits") or [])
    try:
        return int(total or 0)
    except Exception:
        return 0


def collect_event_source_ids(db: Session | None, event: Event) -> List[str]:
    if not event:
        return []
    source_ids: List[str] = []
    if db and event.id:
        rows = (
            db.query(Article.source_id)
            .join(EventArticle, EventArticle.article_id == Article.id)
            .filter(EventArticle.event_id == event.id)
            .distinct()
            .all()
        )
        source_ids = [row[0] for row in rows if row and row[0]]
    if event.primary_source_id and event.primary_source_id not in source_ids:
        source_ids.insert(0, event.primary_source_id)
    return source_ids


def batch_collect_event_source_ids(db: Session, event_ids: List[int]) -> Dict[int, List[str]]:
    """Single JOIN query to get source_ids for ALL events at once — eliminates N+1."""
    if not event_ids:
        return {}
    rows = (
        db.query(EventArticle.event_id, Article.source_id)
        .join(Article, Article.id == EventArticle.article_id)
        .filter(EventArticle.event_id.in_(event_ids))
        .distinct()
        .all()
    )
    result: Dict[int, List[str]] = {eid: [] for eid in event_ids}
    for event_id, source_id in rows:
        if source_id and source_id not in result.get(event_id, []):
            result.setdefault(event_id, []).append(source_id)
    return result


# Short-lived cache for search_events to avoid duplicate expensive calls within a request cycle
_search_events_cache: Dict[str, tuple] = {}  # key -> (result_list_or_count, timestamp)
_SEARCH_EVENTS_CACHE_TTL = 8  # seconds


def _cached_search_events_count(db: Session, query: str, *, time_range=None, source_id=None) -> int:
    cache_key = f"se_count:{query}:{time_range}:{source_id}"
    now = time.time()
    if cache_key in _search_events_cache:
        cached_val, ts = _search_events_cache[cache_key]
        if now - ts < _SEARCH_EVENTS_CACHE_TTL:
            return cached_val
    count = len(search_events(db, query, limit=2000, time_range=time_range, source_id=source_id or None))
    _search_events_cache[cache_key] = (count, now)
    # Evict stale entries periodically
    if len(_search_events_cache) > 50:
        stale = [k for k, (_, ts) in _search_events_cache.items() if now - ts > _SEARCH_EVENTS_CACHE_TTL * 2]
        for k in stale:
            _search_events_cache.pop(k, None)
    return count

def marshal_event(event: Event, query: str = "", search_hit: dict | None = None, db: Session | None = None, _source_ids_override: List[str] | None = None):
    keywords = []
    if event.keywords:
        try:
            keywords = json.loads(event.keywords)
        except Exception:
            keywords = []

    confidence, confidence_label = classify_event_confidence(event.article_count or 0, event.platform_count or 0)

    return {
        "id": event.id,
        "title": event.title,
        "summary": event.summary,
        "keywords": keywords,
        "sentiment": event.sentiment or "neutral",
        "article_count": event.article_count or 0,
        "platform_count": event.platform_count or 0,
        "latest_article_time": event.latest_article_time.isoformat() if event.latest_article_time else None,
        "representative_article_id": event.representative_article_id,
        "primary_source_id": event.primary_source_id,
        "source_ids": _source_ids_override if _source_ids_override is not None else collect_event_source_ids(db, event),
        "confidence": confidence,
        "confidence_label": confidence_label,
        "match_reasons": _build_match_reasons(query, event.title, event.summary, keywords),
        "search_highlight_title": ((search_hit or {}).get("_formatted") or {}).get("title") or "",
        "search_highlight_summary": ((search_hit or {}).get("_formatted") or {}).get("summary") or "",
        "created_at": event.created_at.isoformat() if event.created_at else None,
        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
    }


def marshal_topic(topic: Topic, query: str = "", search_hit: dict | None = None):
    keywords = []
    if topic.keywords:
        try:
            keywords = json.loads(topic.keywords)
        except Exception:
            keywords = []

    if (topic.event_count or 0) >= 6 or (topic.article_count or 0) >= 18:
        confidence = "stable"
        confidence_label = "重点脉络"
    elif (topic.event_count or 0) >= 5:
        confidence = "emerging"
        confidence_label = "观察中"
    else:
        confidence = "weak"
        confidence_label = "弱脉络"

    return {
        "id": topic.id,
        "title": topic.title,
        "summary": topic.summary,
        "keywords": keywords,
        "sentiment": topic.sentiment or "neutral",
        "event_count": topic.event_count or 0,
        "article_count": topic.article_count or 0,
        "platform_count": topic.platform_count or 0,
        "latest_event_time": topic.latest_event_time.isoformat() if topic.latest_event_time else None,
        "representative_event_id": topic.representative_event_id,
        "primary_source_id": topic.primary_source_id,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "match_reasons": _build_match_reasons(query, topic.title, topic.summary, keywords),
        "search_highlight_title": ((search_hit or {}).get("_formatted") or {}).get("title") or "",
        "search_highlight_summary": ((search_hit or {}).get("_formatted") or {}).get("summary") or "",
        "created_at": topic.created_at.isoformat() if topic.created_at else None,
        "updated_at": topic.updated_at.isoformat() if topic.updated_at else None,
    }


async def sync_trigger_crawlers():
    crawlers = [
        WeiboHotSearch(),
        BaiduHotSearch(),
        ToutiaoHotBoard(),
        BilibiliHotVideo(),
        ZhihuHotQuestion(),
        ThePaperHotNews(),
        WallstreetcnNews(),
        ClsTelegraph(),
    ]
    async def run_with_delay(c):
        import random
        await asyncio.sleep(random.uniform(0.01, 0.5)) # 随机延迟 10~500ms 削峰
        return await c.run_and_save()

    await asyncio.gather(*(run_with_delay(crawler) for crawler in crawlers), return_exceptions=True)


async def _run_refresh_job():
    try:
        if _shutting_down.is_set():
            return
        await sync_trigger_crawlers()
        if _shutting_down.is_set():
            return
        await asyncio.to_thread(_refresh_events_cache)
    finally:
        async with swr_state_lock:
            swr_cache["fetching"] = False
            swr_cache["last_fetch"] = time.time()


async def run_startup_refresh():
    if _has_recent_event_hub_data():
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [启动] 已检测到最近数据，跳过启动重抓")
        async with swr_state_lock:
            swr_cache["fetching"] = False
            swr_cache["last_fetch"] = time.time()
        return False

    async with swr_state_lock:
        if swr_cache["fetching"]:
            return False
        swr_cache["fetching"] = True
        swr_cache["last_fetch"] = time.time()


    await _run_refresh_job()
    return True


async def _schedule_refresh(background_tasks: BackgroundTasks):
    async with swr_state_lock:
        if swr_cache["fetching"]:
            return False
        swr_cache["fetching"] = True

    background_tasks.add_task(_run_refresh_job)
    return True


async def warmup_runtime_dependencies():
    """
    启动预热：只做必须立即就绪、且低成本的组件。
    - jieba 分词（<1s, 后续分析请求立即可用）
    - emotion_engine 后台异步加载 BERT（不阻塞）
    - LLM 客户端改为首次调用时 lazy 加载（其 import 开销 ~30s，启动时付出不划算）
    - 数据清理：不再自动执行；调用 POST /api/admin/cleanup_articles 按需触发
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [预热] 正在初始化 NLP 引擎与 AI 组件...")
    start_time = time.time()

    # 并行预热：jieba + emotion（后台线程，立即返回）
    async def _warm_jieba():
        try:
            await asyncio.to_thread(get_word_frequencies, "启动预热", "启动预热文本，用于预热 jieba 分词。")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [预热] 分词组件已就绪")
        except Exception as exc:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [预热] 分词组件跳过: {exc}")

    try:
        emotion_engine._start_background_load()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [预热] 情绪引擎后台加载已启动")
    except Exception as exc:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [预热] 情绪引擎跳过: {exc}")

    await _warm_jieba()

    duration = time.time() - start_time
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [预热] 全系统预热完成 (耗时: {duration:.1f}秒; LLM 客户端将在首次使用时 lazy 加载)")


@router.get("/sync/status")
async def get_sync_status():
    async with swr_state_lock:
        return {
            "fetching": swr_cache["fetching"],
            "last_fetch": swr_cache["last_fetch"]
        }


def _fetch_balanced_articles(session: Session):
    balanced_list = []
    for source_id in SOURCE_IDS:
        items = (
            session.query(Article)
            .filter(Article.source_id == source_id)
            .order_by(Article.rank.asc())
            .limit(100)
            .all()
        )
        balanced_list.extend(items)
    return balanced_list


def _refresh_events_cache():
    if _shutting_down.is_set():
        return
    with event_hub_refresh_lock:
        db = SessionLocal()
        try:
            if _shutting_down.is_set():
                return
            recent_cutoff = datetime.utcnow() - timedelta(hours=168)
            meili.sync_articles(db.query(Article).filter(Article.fetch_time >= recent_cutoff).all())
            if _shutting_down.is_set():
                return
            rebuild_events(db, lookback_hours=168)
            if _shutting_down.is_set():
                return
            rebuild_topics(db)
            events = db.query(Event).order_by(Event.latest_article_time.desc(), Event.article_count.desc()).all()
            topics = db.query(Topic).order_by(Topic.latest_event_time.desc(), Topic.event_count.desc()).all()
            batch_sids = batch_collect_event_source_ids(db, [e.id for e in events])
            events_payload = [marshal_event(e, db=db, _source_ids_override=batch_sids.get(e.id, [])) for e in events]
            topics_payload = [marshal_topic(topic) for topic in topics]
            allow_empty = db.query(Article).count() == 0
            _update_event_hub_cache(events_payload, topics_payload, allow_empty=allow_empty)
        finally:
            db.close()


def cleanup_stale_articles(days: int = 7, dry_run: bool = False):
    """
    清理"已掉出热榜（rank=999）、从未被 AI 分析（content 为空）、fetch_time > days 天"
    **且未被任何 Event 聚合引用**的历史条目。
    - 强制保护：被 EventArticle 引用的 Article 永远不删（避免产生孤儿，这是历史教训）
    - dry_run=True 时只统计不删
    - 破坏性操作前自动做一次 DB 快照到 runtime/db/yujing.db.cleanup_bak_{ts}
    """
    import shutil
    from pathlib import Path

    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        # 被事件引用的 article_id 集合（保护名单）
        referenced_ids = {
            r[0] for r in db.query(EventArticle.article_id).distinct().all()
        }

        candidate_query = db.query(Article).filter(
            Article.rank == 999,
            (Article.content == None) | (Article.content == ""),
            Article.fetch_time < cutoff,
        )
        candidates = candidate_query.all()
        # 过滤掉被引用的
        to_delete = [a for a in candidates if a.id not in referenced_ids]
        protected = len(candidates) - len(to_delete)

        if dry_run:
            print(
                f"[数据清理][dry-run] 候选 {len(candidates)} 条, "
                f"保护 {protected} 条（被事件引用）, 将删 {len(to_delete)} 条"
            )
            return len(to_delete)

        if not to_delete:
            print("[数据清理] 无可删除条目")
            return 0

        # 破坏性操作前做一次快照
        try:
            # 用 DATABASE_PATH 环境变量 / database.py 的 DATABASE_PATH 作为权威来源，
            # 避免硬编码在项目改名时再次失联。
            from app.database import DATABASE_PATH
            db_path = Path(DATABASE_PATH)
            if db_path.exists():
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                bak = db_path.parent / f"{db_path.name}.cleanup_bak_{ts}"
                shutil.copy2(db_path, bak)
                print(f"[数据清理] 已创建快照: {bak}")
        except Exception as exc:
            print(f"[数据清理] 快照失败（但继续执行）: {exc}")

        ids_to_delete = [a.id for a in to_delete]
        deleted = db.query(Article).filter(Article.id.in_(ids_to_delete)).delete(
            synchronize_session=False
        )
        db.commit()
        print(
            f"[数据清理] 已删除 {deleted} 条 (rank=999, 无内容, >{days}天); "
            f"保护了 {protected} 条被事件引用的条目"
        )
        return int(deleted or 0)
    except Exception as exc:
        db.rollback()
        print(f"[数据清理] 失败: {exc}")
        return 0
    finally:
        db.close()


@router.post("/admin/cleanup_articles")
def admin_cleanup_articles(days: int = 7, dry_run: bool = False):
    """
    手动触发历史脏数据清理。
    - days: 删除 fetch_time 早于 N 天前的 rank=999 无内容记录（默认 7）
    - dry_run: 只统计不删（默认 False）
    - 自动保护被 EventArticle 引用的条目
    - 破坏性操作前自动做 DB 快照到 runtime/db/yujing.db.cleanup_bak_<ts>
    """
    removed = cleanup_stale_articles(days=days, dry_run=dry_run)
    return {"ok": True, "removed": removed, "days": days, "dry_run": dry_run}


def _has_recent_event_hub_data(window_minutes: int = 20) -> bool:
    db = SessionLocal()
    try:
        latest_article = db.query(Article).order_by(Article.fetch_time.desc()).first()
        if not latest_article or not latest_article.fetch_time:
            return False
        if latest_article.fetch_time < datetime.utcnow() - timedelta(minutes=window_minutes):
            return False
        return db.query(Event).count() > 0
    finally:
        db.close()


def _ensure_event_hub_data(force_refresh: bool = False, refresh_topics: bool = False):
    with event_hub_refresh_lock:
        db = SessionLocal()
        try:
            if force_refresh:
                meili.sync_articles(db.query(Article).all())
                rebuild_events(db, lookback_hours=168)
                rebuild_topics(db)
            else:
                if db.query(Event).count() == 0:
                    ensure_events(db)
                if refresh_topics and db.query(Topic).count() == 0:
                    ensure_topics(db)

            events = db.query(Event).order_by(Event.latest_article_time.desc(), Event.article_count.desc()).all()
            topics = db.query(Topic).order_by(Topic.latest_event_time.desc(), Topic.event_count.desc()).all()
            batch_sids = batch_collect_event_source_ids(db, [e.id for e in events])
            events_payload = [marshal_event(e, db=db, _source_ids_override=batch_sids.get(e.id, [])) for e in events]
            topics_payload = [marshal_topic(topic) for topic in topics]
            allow_empty = db.query(Article).count() == 0
            _update_event_hub_cache(events_payload, topics_payload, allow_empty=allow_empty)
            return {
                "events": swr_cache["events"],
                "topics": swr_cache["topics"],
            }
        finally:
            db.close()


@router.get("/articles", response_model=List[ArticleResponse])
async def get_articles(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    force_refresh: bool = False,
):
    if force_refresh:
        async with swr_state_lock:
            if not swr_cache["fetching"]:
                swr_cache["fetching"] = True
                background_tasks.add_task(_run_refresh_job)

    current_time = time.time()
    if not force_refresh and (current_time - swr_cache["last_fetch"] < 60) and swr_cache["articles"]:
        return swr_cache["articles"]

    fresh_articles = _fetch_balanced_articles(db)

    # 超过60秒静默触发更新，不再 await schedule_refresh
    if current_time - swr_cache["last_fetch"] > 60:
        background_tasks.add_task(_run_refresh_job)

    swr_cache["articles"] = fresh_articles
    return fresh_articles


@router.get("/articles/search", response_model=List[ArticleResponse])
async def search_articles_endpoint(
    db: Session = Depends(get_db),
    q: str = "",
    time_range: int = None,
    source_id: str = "",
    limit: int = 30,
):
    query = (q or "").strip()
    if not query:
        return []

    if meili.enabled:
        try:
            stats = meili.client.index("articles").get_stats()
            if getattr(stats, "number_of_documents", 0) == 0:
                meili.sync_articles(db.query(Article).all())
        except Exception:
            meili.sync_articles(db.query(Article).all())

        hits = meili.search_articles_hits(query, limit=limit, time_range=time_range, source_id=source_id or "")
        if hits:
            hit_ids = [int(hit["id"]) for hit in hits if "id" in hit]
            rows = db.query(Article).filter(Article.id.in_(hit_ids)).all()
            lookup = {row.id: row for row in rows}
            hit_lookup = {int(hit["id"]): hit for hit in hits if "id" in hit}
            return [
                marshal_article(lookup[article_id], query=query, search_hit=hit_lookup.get(article_id))
                for article_id in hit_ids
                if article_id in lookup
            ]

    q_obj = db.query(Article)
    if time_range is not None:
        cutoff = datetime.now() - timedelta(hours=time_range)
        q_obj = q_obj.filter(Article.fetch_time >= cutoff)
    if source_id:
        q_obj = q_obj.filter(Article.source_id == source_id)

    rows = (
        q_obj.filter(
            (Article.title.contains(query))
            | (Article.ai_summary.contains(query))
            | (Article.extra_info.contains(query))
        )
        .order_by(Article.fetch_time.desc(), Article.rank.asc())
        .limit(limit)
        .all()
    )
    return [marshal_article(row, query=query) for row in rows]


@router.get("/articles/search_page")
async def search_articles_page_endpoint(
    db: Session = Depends(get_db),
    q: str = "",
    time_range: int = None,
    source_id: str = "",
    limit: int = 24,
    offset: int = 0,
):
    query = (q or "").strip()
    limit = max(1, min(int(limit or 24), 60))
    offset = max(0, int(offset or 0))
    if not query:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    if meili.enabled:
        try:
            # 工业级优化：禁止在 API 请求主循环中执行耗时的数据库全表同步
            stats = meili.client.index("articles").get_stats()
            if getattr(stats, "number_of_documents", 0) == 0:
                # 如果索引为空，直接返回空（依靠后台静默同步机制），不执行 Article.all()
                return {"items": [], "total": 0, "limit": limit, "offset": offset}
        except Exception:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}

        result = meili.search_articles_result(
            query,
            limit=limit,
            offset=offset,
            time_range=time_range,
            source_id=source_id or "",
        )
        hits = result.get("hits", []) or []
        hit_ids = [int(hit["id"]) for hit in hits if "id" in hit]
        total = int(result.get("estimatedTotalHits") or result.get("totalHits") or len(hits))
        if not hit_ids:
            return {"items": [], "total": total, "limit": limit, "offset": offset}
        
        rows = db.query(Article).filter(Article.id.in_(hit_ids)).all()
        lookup = {row.id: row for row in rows}
        hit_lookup = {int(hit["id"]): hit for hit in hits if "id" in hit}
        items = [
            marshal_article(lookup[article_id], query=query, search_hit=hit_lookup.get(article_id))
            for article_id in hit_ids
            if article_id in lookup
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    q_obj = db.query(Article)
    if time_range is not None:
        cutoff = datetime.now() - timedelta(hours=time_range)
        q_obj = q_obj.filter(Article.fetch_time >= cutoff)
    if source_id:
        q_obj = q_obj.filter(Article.source_id == source_id)

    q_obj = q_obj.filter(
        (Article.title.contains(query))
        | (Article.ai_summary.contains(query))
        | (Article.extra_info.contains(query))
    )
    total = q_obj.count()
    rows = (
        q_obj.order_by(Article.fetch_time.desc(), Article.rank.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": [marshal_article(row, query=query) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/search/unified")
async def unified_search_endpoint(
    db: Session = Depends(get_db),
    q: str = "",
    time_range: int = None,
    source_id: str = "",
    page: int = Query(1, ge=1),
):
    query = (q or "").strip()
    normalized_source = (source_id or "").strip()
    limit = 9
    offset = (page - 1) * limit
    
    # 全量拦截：支持搜索与默认过滤的高频切换极速响应 (增加 page 维度)
    cache_key = f"{query}:{time_range}:{normalized_source}:{page}"
    if cache_key in unified_search_cache:
        cached_data, timestamp = unified_search_cache[cache_key]
        if time.time() - timestamp < 60:
            return cached_data

    if not query:
        # 联动统计逻辑：即使空查询也支持时间过滤
        q_events = db.query(Event)
        q_articles = db.query(Article)
        
        is_all_range = (time_range is None)
        if not is_all_range:
            cutoff = datetime.utcnow() - timedelta(hours=int(time_range))
            q_events = q_events.filter(Event.latest_article_time >= cutoff)
            q_articles = q_articles.filter(Article.fetch_time >= cutoff)

        is_high_heat_mode = is_all_range or (time_range is not None and int(time_range) > 24)
        
        if is_high_heat_mode:
            e_list = q_events.order_by(Event.article_count.desc(), Event.latest_article_time.desc()).limit(limit).offset(offset).all()
        else:
            e_list = q_events.order_by(Event.latest_article_time.desc(), Event.article_count.desc()).limit(limit).offset(offset).all()
            
        a_list = q_articles.order_by(Article.fetch_time.desc()).limit(limit).offset(offset).all()

        batch_sids = batch_collect_event_source_ids(db, [e.id for e in e_list])
        res_payload = {
            "query": "",
            "events": [marshal_event(e, query="", db=db, _source_ids_override=batch_sids.get(e.id, [])) for e in e_list],
            "topics": [],
            "articles": [marshal_article(a) for a in a_list],
            "platforms": [],
            "summary": {
                "events": q_events.count(),
                "topics": db.query(Topic).count(),
                "articles": q_articles.count()
            },
        }
        unified_search_cache[cache_key] = (res_payload, time.time())
        return res_payload

    # 带词搜索路径
    event_total = 0
    topic_total = 0
    article_total = 0
    
    if meili.enabled:
        try:
            event_result = meili.search_events_result(
                query,
                limit=limit,
                offset=offset,
                time_range=time_range,
                source_id=normalized_source,
            )
            topic_result = meili.search_topics_hits(
                query,
                limit=5,
                time_range=time_range,
                source_id=normalized_source,
            )
            article_result = meili.search_articles_result(
                query,
                limit=limit,
                offset=offset,
                time_range=time_range,
                source_id=normalized_source,
            )

            event_hits = event_result.get("hits") or []
            topic_hits = topic_result.get("hits") or []
            article_hits = article_result.get("hits") or []

            event_ids = [int(hit["id"]) for hit in event_hits if "id" in hit]
            topic_ids = [int(hit["id"]) for hit in topic_hits if "id" in hit]
            article_ids = [int(hit["id"]) for hit in article_hits if "id" in hit]

            event_lookup = {item.id: item for item in db.query(Event).filter(Event.id.in_(event_ids)).all()} if event_ids else {}
            topic_lookup = {item.id: item for item in db.query(Topic).filter(Topic.id.in_(topic_ids)).all()} if topic_ids else {}
            article_lookup = {item.id: item for item in db.query(Article).filter(Article.id.in_(article_ids)).all()} if article_ids else {}

            event_hit_lookup = {int(hit["id"]): hit for hit in event_hits if "id" in hit}
            topic_hit_lookup = {int(hit["id"]): hit for hit in topic_hits if "id" in hit}
            article_hit_lookup = {int(hit["id"]): hit for hit in article_hits if "id" in hit}

            meili_batch_sids = batch_collect_event_source_ids(db, list(event_lookup.keys())) if event_lookup else {}
            events_payload = [
                marshal_event(event_lookup[item_id], query=query, search_hit=event_hit_lookup.get(item_id), db=db, _source_ids_override=meili_batch_sids.get(item_id, []))
                for item_id in event_ids
                if item_id in event_lookup
            ]
            topics_payload = [
                marshal_topic(topic_lookup[item_id], query=query, search_hit=topic_hit_lookup.get(item_id))
                for item_id in topic_ids
                if item_id in topic_lookup
            ]
            articles_payload = [
                marshal_article(article_lookup[item_id], query=query, search_hit=article_hit_lookup.get(item_id))
                for item_id in article_ids
                if item_id in article_lookup
            ]

            events_payload = _filter_query_matched_rows(events_payload, query=query, row_type="event")
            topics_payload = _filter_query_matched_rows(topics_payload, query=query, row_type="topic")
            articles_payload = _filter_query_matched_rows(articles_payload, query=query, row_type="article")

            # 精确统计：用 SQL title.contains 代替 MeiliSearch estimatedTotalHits
            sql_article_total = db.query(Article).filter(Article.title.contains(query))
            sql_event_total = _cached_search_events_count(db, query, time_range=time_range, source_id=normalized_source or None)
            if time_range is not None:
                cutoff = datetime.utcnow() - timedelta(hours=int(time_range))
                sql_article_total = sql_article_total.filter(Article.fetch_time >= cutoff)
            if normalized_source:
                sql_article_total = sql_article_total.filter(Article.source_id == normalized_source)
            event_total = sql_event_total
            topic_total = _meili_total(topic_result)
            article_total = sql_article_total.count()

            # 事件按包含热搜卡片数排序
            events_payload.sort(key=lambda e: (e.get("article_count") or 0), reverse=True)

            if events_payload or topics_payload or articles_payload or event_total or topic_total or article_total:
                return {
                    "query": query,
                    "page": page,
                    "limit": limit,
                    "events": events_payload,
                    "topics": topics_payload,
                    "articles": articles_payload,
                    "summary": {
                        "events": event_total,
                        "topics": topic_total,
                        "articles": article_total
                    },
                }
        except Exception:
            pass

    # 极简 SQL Fallback (MS 未命中时)
    fallback_events_query = db.query(Event).filter(Event.title.contains(query))
    fallback_topics_query = db.query(Topic).filter(Topic.title.contains(query))
    fallback_articles_query = db.query(Article).filter(Article.title.contains(query))

    if time_range is not None:
        cutoff = datetime.utcnow() - timedelta(hours=int(time_range))
        fallback_events_query = fallback_events_query.filter(Event.latest_article_time >= cutoff)
        fallback_topics_query = fallback_topics_query.filter(Topic.latest_event_time >= cutoff)
        fallback_articles_query = fallback_articles_query.filter(Article.fetch_time >= cutoff)

    if normalized_source:
        fallback_events_query = fallback_events_query.filter(Event.primary_source_id == normalized_source)
        fallback_topics_query = fallback_topics_query.filter(Topic.primary_source_id == normalized_source)
        fallback_articles_query = fallback_articles_query.filter(Article.source_id == normalized_source)

    if not event_total:
        event_total = _cached_search_events_count(db, query, time_range=time_range, source_id=normalized_source or None)
    topic_total = fallback_topics_query.count() if not topic_total else topic_total
    article_total = fallback_articles_query.count() if not article_total else article_total

    fallback_events = fallback_events_query.order_by(Event.article_count.desc(), Event.latest_article_time.desc()).limit(limit).offset(offset).all()
    fallback_topics = fallback_topics_query.limit(5).all()
    fallback_articles = fallback_articles_query.order_by(Article.fetch_time.desc()).limit(limit).offset(offset).all()
    
    fb_batch_sids = batch_collect_event_source_ids(db, [e.id for e in fallback_events]) if fallback_events else {}
    events_payload = _filter_query_matched_rows(
        [marshal_event(item, query=query, db=db, _source_ids_override=fb_batch_sids.get(item.id, [])) for item in fallback_events],
        query=query,
        row_type="event",
    )
    events_payload.sort(key=lambda e: (e.get("article_count") or 0), reverse=True)
    topics_payload = _filter_query_matched_rows(
        [marshal_topic(item, query=query) for item in fallback_topics],
        query=query,
        row_type="topic",
    )
    articles_payload = _filter_query_matched_rows(
        [marshal_article(a, query=query) for a in fallback_articles],
        query=query,
        row_type="article",
    )

    return {
        "query": query,
        "page": page,
        "limit": limit,
        "events": events_payload,
        "topics": topics_payload,
        "articles": articles_payload,
        "summary": {
            "events": event_total,
            "topics": topic_total,
            "articles": article_total,
        },
    }


@router.get("/events")
async def get_events(response: Response, db: Session = Depends(get_db), force_refresh: bool = False, q: str = "", time_range: int = None, source_id: str = ""):
    current_time = time.time()
    query = (q or "").strip()
    normalized_source = (source_id or "").strip()
    
    q_obj = db.query(Event)
    
    is_all_range = (time_range is None or int(time_range) >= 720)
    if not is_all_range:
        cutoff = datetime.utcnow() - timedelta(hours=int(time_range))
        q_obj = q_obj.filter(Event.latest_article_time >= cutoff)

    if normalized_source:
        q_obj = q_obj.filter(Event.primary_source_id == normalized_source)
    
    total = q_obj.count()
    events = q_obj.order_by(Event.article_count.desc(), Event.latest_article_time.desc()).limit(9).all()
    batch_sids = batch_collect_event_source_ids(db, [e.id for e in events])
    payload = [marshal_event(e, query=query, db=db, _source_ids_override=batch_sids.get(e.id, [])) for e in events]
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return payload


def _get_filtered_event_page(
    db: Session,
    query: str,
    *,
    time_range: int = None,
    source_id: str = "",
    limit: int = 18,
    offset: int = 0,
):
    # 统一走 SQL 评分排序，保证相关性过滤一致；过滤后按 article_count 降序
    all_events = search_events(
        db, query, limit=2000, time_range=time_range, source_id=source_id or None
    )
    all_events.sort(key=lambda e: (e.article_count or 0), reverse=True)
    total = len(all_events)
    page_events = all_events[offset: offset + limit]
    batch_sids = batch_collect_event_source_ids(db, [e.id for e in page_events])
    items = [marshal_event(e, query=query, db=db, _source_ids_override=batch_sids.get(e.id, [])) for e in page_events]
    return items, total


@router.get("/events/search_page")
async def search_events_page_endpoint(
    db: Session = Depends(get_db),
    q: str = "",
    time_range: int = None,
    source_id: str = "",
    limit: int = 18,
    offset: int = 0,
):
    query = (q or "").strip()
    normalized_source = (source_id or "").strip()
    limit = max(1, min(int(limit or 18), 60))
    offset = max(0, int(offset or 0))
    is_all_range = (time_range is None or int(time_range) >= 720)

    if query:
        items, total = _get_filtered_event_page(
            db,
            query,
            time_range=time_range,
            source_id=normalized_source,
            limit=limit,
            offset=offset,
        )
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    q_obj = db.query(Event)
    if time_range is not None:
        cutoff = datetime.utcnow() - timedelta(hours=time_range)
        q_obj = q_obj.filter(Event.latest_article_time >= cutoff)
    if normalized_source:
        q_obj = q_obj.filter(Event.primary_source_id == normalized_source)
    total = q_obj.count()
    
    # 逻辑分流：限时模式看新鲜度，全部模式看总热度
    if is_all_range:
        q_obj = q_obj.order_by(Event.article_count.desc(), Event.latest_article_time.desc())
    else:
        q_obj = q_obj.order_by(Event.latest_article_time.desc(), Event.article_count.desc())

    rows = q_obj.offset(offset).limit(limit).all()
    sp_batch_sids = batch_collect_event_source_ids(db, [r.id for r in rows])
    return {"items": [marshal_event(r, query=query, db=db, _source_ids_override=sp_batch_sids.get(r.id, [])) for r in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/events/{event_id}", response_model=EventDetailResponse)
async def get_event_detail(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="未找到事件")

    link_rows = (
        db.query(EventArticle)
        .filter(EventArticle.event_id == event_id)
        .order_by(EventArticle.is_primary.desc(), EventArticle.relation_score.desc())
        .all()
    )
    article_ids = [row.article_id for row in link_rows]
    db_articles = db.query(Article).filter(Article.id.in_(article_ids)).all()

    # 情绪补全：**绝不**在请求链路上同步跑 BERT（会把 CPU 打满 → 饿死其他请求）。
    # 两层策略：
    #   1. 请求链路内用 emotion_engine._fallback_analyze（纯字符串关键词匹配，
    #      几十篇标题总耗时 <50ms），仅覆盖到响应 dict，**不写库**，保证
    #      舆情倾向饼图当场就有数据，不会再出现全中性。
    #   2. 同时调度后台单线程 BERT 精细补全；下次请求同一事件时读到 BERT 结果，
    #      更精准。
    pending_ids = [a.id for a in db_articles if (not a.ai_sentiment) and a.title]
    if pending_ids:
        _schedule_event_emotion_backfill(event_id, pending_ids)

    fallback_sentiment: dict[int, str] = {}
    for art in db_articles:
        if art.ai_sentiment or not art.title:
            continue
        try:
            results = emotion_engine._fallback_analyze(art.title)
            if results:
                fallback_sentiment[art.id] = _EMOTION_LABEL_MAP.get(
                    results[0]["label"], "neutral"
                )
        except Exception:
            continue

    article_lookup = {}
    for article in db_articles:
        marshaled = marshal_article(article)
        # 响应级兜底：不改 ORM 对象、不触发 commit
        if not marshaled.get("ai_sentiment") and article.id in fallback_sentiment:
            marshaled["ai_sentiment"] = fallback_sentiment[article.id]
        article_lookup[article.id] = marshaled
    related_articles = [article_lookup[article_id] for article_id in article_ids if article_id in article_lookup]
    related_articles.sort(key=lambda a: a.get("fetch_time") or "", reverse=True)

    payload = marshal_event(event, db=db)
    payload["related_articles"] = related_articles
    return payload


@router.get("/topics", response_model=List[TopicResponse])
async def get_topics(db: Session = Depends(get_db), force_refresh: bool = False, q: str = "", time_range: int = None, source_id: str = ""):
    current_time = time.time()
    query = (q or "").strip()
    normalized_source = (source_id or "").strip()
    topic_count_db = db.query(Topic).count()
    if (
        not query
        and not time_range
        and not normalized_source
        and not force_refresh
        and (current_time - swr_cache["topics_last_fetch"] < 120)
        and swr_cache["topics"]
        and not _cache_stale_against_model(db, Topic, swr_cache["topics_last_fetch"])
    ):
        return swr_cache["topics"]

    if force_refresh:
        await asyncio.to_thread(_ensure_event_hub_data, True, True)
        db.expire_all()
    elif topic_count_db == 0:
        await asyncio.to_thread(_ensure_event_hub_data, False, True)
        db.expire_all()

    if query or time_range or normalized_source:
        topics = search_topics(db, query, time_range=time_range, source_id=normalized_source)
    else:
        topics = db.query(Topic).order_by(Topic.latest_event_time.desc(), Topic.event_count.desc()).all()
    payload = [marshal_topic(topic, query=query) for topic in topics]
    if not query and not time_range and not normalized_source and not payload and swr_cache["topics"]:
        return swr_cache["topics"]
    if not query and not time_range and not normalized_source:
        _update_event_hub_cache(swr_cache["events"], payload, allow_empty=db.query(Article).count() == 0)
    return payload


@router.get("/topics/{topic_id}", response_model=TopicDetailResponse)
async def get_topic_detail(topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="未找到主题")

    link_rows = (
        db.query(TopicEvent)
        .filter(TopicEvent.topic_id == topic_id)
        .order_by(TopicEvent.is_primary.desc(), TopicEvent.relation_score.desc())
        .all()
    )
    event_ids = [row.event_id for row in link_rows]
    event_lookup = {
        event.id: marshal_event(event, db=db)
        for event in db.query(Event).filter(Event.id.in_(event_ids)).all()
    }
    related_events = [event_lookup[event_id] for event_id in event_ids if event_id in event_lookup]
    related_events.sort(key=lambda e: e.get("latest_article_time") or "", reverse=True)

    payload = marshal_topic(topic)
    payload["related_events"] = related_events
    return payload


@router.get("/topics/{topic_id}/analyze")
async def analyze_topic_macro(topic_id: int, db: Session = Depends(get_db)):
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise HTTPException(status_code=404, detail="未找到主题记录")

    link_rows = (
        db.query(TopicEvent)
        .filter(TopicEvent.topic_id == topic_id)
        .order_by(TopicEvent.is_primary.desc(), TopicEvent.relation_score.desc())
        .all()
    )
    event_ids = [row.event_id for row in link_rows]
    event_lookup = {
        event.id: marshal_event(event, db=db) for event in db.query(Event).filter(Event.id.in_(event_ids)).all()
    }
    related_events = [event_lookup[event_id] for event_id in event_ids if event_id in event_lookup]

    async def event_generator():
        yield f"data: {json.dumps({'type': 'status', 'msg': '正在聚合全景事件情报并生成研判专题...'}, ensure_ascii=False)}\n\n"

        try:
            from app.llm import analyze_topic_macro_stream

            yield f"data: {json.dumps({'type': 'content_start'}, ensure_ascii=False)}\n\n"

            async for chunk in analyze_topic_macro_stream(topic.title, related_events):
                yield f"data: {json.dumps({'type': 'content', 'text': chunk}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'type': 'content_end'}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'msg': f'全景研判中断: {exc}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 事件情绪后台补全（单线程队列 + 并发去重）
# ---------------------------------------------------------------------------
# 关键设计：
# - 专用 max_workers=1 executor，保证同一时刻只跑 1 个 BERT 推理批次，
#   避免 torch 多核 inference 把整机 CPU 打满饿死其他请求。
# - in-flight set 去重：同一 event_id 已经排队/运行中就不再入队。
# - 任务内部独立开 SessionLocal() 写回，避免与请求 session 生命周期耦合。
from concurrent.futures import ThreadPoolExecutor as _EmoThreadPool

_emotion_backfill_executor = _EmoThreadPool(
    max_workers=1,
    thread_name_prefix="emotion-backfill",
)
_emotion_backfill_inflight: set = set()
_emotion_backfill_lock = threading.Lock()

_EMOTION_LABEL_MAP = {
    "中性": "neutral", "关注": "concern", "喜悦": "joy",
    "愤怒": "anger", "悲伤": "sadness", "质疑": "doubt",
    "惊讶": "surprise", "厌恶": "disgust",
}


def _run_emotion_backfill(event_id: int, article_ids: list[int]):
    """在专属单线程 executor 中运行；独立 Session，写完即 commit。"""
    session = SessionLocal()
    try:
        articles = session.query(Article).filter(Article.id.in_(article_ids)).all()
        dirty = False
        for art in articles:
            if art.ai_sentiment or not art.title:
                continue
            try:
                results = emotion_engine.analyze(art.title)
                if results:
                    art.ai_sentiment = _EMOTION_LABEL_MAP.get(
                        results[0]["label"], results[0]["label"]
                    )
                    dirty = True
            except Exception as exc:
                print(f"[emotion-backfill] article={art.id} 失败: {exc}")
        if dirty:
            try:
                session.commit()
            except Exception as exc:
                session.rollback()
                print(f"[emotion-backfill] commit 失败: {exc}")
    finally:
        session.close()
        with _emotion_backfill_lock:
            _emotion_backfill_inflight.discard(event_id)


def _schedule_event_emotion_backfill(event_id: int, pending_ids: list[int]):
    """请求链路上调用；幂等、非阻塞，立即返回。"""
    if not pending_ids:
        return
    with _emotion_backfill_lock:
        if event_id in _emotion_backfill_inflight:
            return
        _emotion_backfill_inflight.add(event_id)
    try:
        _emotion_backfill_executor.submit(
            _run_emotion_backfill, event_id, list(pending_ids)
        )
    except Exception as exc:
        with _emotion_backfill_lock:
            _emotion_backfill_inflight.discard(event_id)
        print(f"[emotion-backfill] 调度失败: {exc}")


# ---------------------------------------------------------------------------
# 定时早报
# ---------------------------------------------------------------------------
_morning_brief_cache: dict = {"date": "", "content": "", "generating": False}


@router.get("/ai/morning_brief/status")
def morning_brief_status():
    today = datetime.now().strftime("%Y-%m-%d")
    has_brief = _morning_brief_cache["date"] == today and _morning_brief_cache["content"]
    return {
        "has_brief": bool(has_brief),
        "date": _morning_brief_cache["date"],
        "generating": _morning_brief_cache["generating"],
    }


@router.get("/ai/morning_brief/content")
def morning_brief_content():
    """直接返回缓存的早报内容，不触发生成。"""
    today = datetime.now().strftime("%Y-%m-%d")
    if _morning_brief_cache["date"] == today and _morning_brief_cache["content"]:
        return {"ok": True, "content": _morning_brief_cache["content"], "date": _morning_brief_cache["date"]}
    return {"ok": False, "content": "", "date": ""}


def _build_morning_brief_prompt(db: Session) -> str:
    """构造早报 system prompt，供 SSE 和后台触发共享。"""
    cutoff = datetime.utcnow() - timedelta(hours=24)
    events = (
        db.query(Event)
        .filter(Event.latest_article_time >= cutoff)
        .order_by(Event.article_count.desc())
        .limit(15)
        .all()
    )
    articles = (
        db.query(Article)
        .filter(Article.fetch_time >= cutoff)
        .order_by(Article.fetch_time.desc())
        .limit(40)
        .all()
    )

    platform_counts: dict = {}
    for a in articles:
        name = SOURCE_NAME_MAP.get(a.source_id, a.source_id)
        platform_counts[name] = platform_counts.get(name, 0) + 1

    ctx_lines = [f"过去24小时聚合事件 TOP{len(events)}"]
    for e in events:
        kw = ""
        if e.keywords:
            try:
                kw = "、".join(json.loads(e.keywords)[:3])
            except Exception:
                pass
        ctx_lines.append(f"- {e.title}（{e.platform_count}个平台，{e.article_count}条）{f'  关键词:{kw}' if kw else ''}")
    ctx_lines.append("\n平台覆盖统计：")
    for name, count in sorted(platform_counts.items(), key=lambda x: -x[1]):
        ctx_lines.append(f"- {name}: {count}条")
    ctx_lines.append(f"\n最新热搜摘要 {min(len(articles), 30)} 条")
    for a in articles[:30]:
        ctx_lines.append(f"[{SOURCE_NAME_MAP.get(a.source_id, a.source_id)}] {a.title}")

    return (
        "你是舆镜AI早报生成器。根据下方数据生成一份结构化的每日舆情早报。\n"
        "格式要求：\n"
        "1. 【今日概览】用2-3句话总结过去24小时的整体舆论态势和情绪基调\n"
        "2. 【重点事件 TOP5】列出5个最值得关注的事件，每个事件：标题 + 一句话概括 + 涉及平台数\n"
        "3. 【平台动态】简述各平台的热点差异（1-2句）\n"
        "4. 【趋势研判】给出1-2条舆情走势预判和建议关注点\n"
        "中文输出，不使用Markdown表格，保持紧凑专业。\n\n"
        f"数据：\n" + "\n".join(ctx_lines)
    )


async def _run_morning_brief_background():
    """在 asyncio.create_task 中运行；独立 Session，drain LLM 流 → 写 cache。
    全部异常都被捕获 —— 这是 fire-and-forget task，千万不能把异常泄露给事件循环。"""
    from app.llm import chat_with_news_stream

    today = datetime.now().strftime("%Y-%m-%d")
    pieces: list[str] = []
    try:
        # 构造 prompt 用独立 session，用完即 close；LLM 阶段不占用 DB 连接
        session = SessionLocal()
        try:
            system_prompt = _build_morning_brief_prompt(session)
        finally:
            session.close()

        async for chunk in chat_with_news_stream(system_prompt, [], "请生成今日舆情早报"):
            pieces.append(chunk)
    except Exception as exc:
        print(f"[早报-后台] 生成失败: {exc}")
    finally:
        full_text = "".join(pieces).strip()
        if full_text:
            _morning_brief_cache["date"] = today
            _morning_brief_cache["content"] = full_text
            print(f"[早报-后台] 已缓存今日早报（{len(full_text)} chars）")
        _morning_brief_cache["generating"] = False


@router.post("/ai/morning_brief/trigger")
async def trigger_morning_brief():
    """工业级触发端点：立即返回，不 hold 连接。
    状态机：
      - has_brief=True  → 'ready'  （前端停止轮询）
      - generating=True → 'running'（前端继续每 3s 轮询 /status）
      - 其他            → 启动后台任务 → 'started'（同上）
    这是整个早报生成链路的唯一入口，替代老的"前端 drain SSE"方案。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    if _morning_brief_cache["date"] == today and _morning_brief_cache["content"]:
        return {"status": "ready", "date": today}
    if _morning_brief_cache.get("generating"):
        return {"status": "running"}
    # 入队前先占位，防止并发两个 trigger 同时起任务
    _morning_brief_cache["generating"] = True
    asyncio.create_task(_run_morning_brief_background())
    return {"status": "started"}


@router.get("/ai/morning_brief")
async def get_morning_brief(db: Session = Depends(get_db)):
    """保留原 SSE 入口（定时任务 / 调试用途）。优先返回缓存。"""
    from app.llm import chat_with_news_stream

    today = datetime.now().strftime("%Y-%m-%d")

    # 命中缓存：直接返回已生成的早报
    if _morning_brief_cache["date"] == today and _morning_brief_cache["content"]:
        cached = _morning_brief_cache["content"]

        async def cached_gen():
            yield f"data: {json.dumps({'type': 'content_start'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'content', 'text': cached}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'content_end'}, ensure_ascii=False)}\n\n"

        return StreamingResponse(cached_gen(), media_type="text/event-stream")

    system_prompt = _build_morning_brief_prompt(db)
    _morning_brief_cache["generating"] = True

    async def brief_generator():
        pieces = []
        yield f"data: {json.dumps({'type': 'content_start'}, ensure_ascii=False)}\n\n"
        try:
            async for chunk in chat_with_news_stream(system_prompt, [], "请生成今日舆情早报"):
                yield f"data: {json.dumps({'type': 'content', 'text': chunk}, ensure_ascii=False)}\n\n"
                pieces.append(chunk)
            yield f"data: {json.dumps({'type': 'content_end'}, ensure_ascii=False)}\n\n"
        finally:
            full_text = "".join(pieces).strip()
            if full_text:
                _morning_brief_cache["date"] = today
                _morning_brief_cache["content"] = full_text
            _morning_brief_cache["generating"] = False

    return StreamingResponse(brief_generator(), media_type="text/event-stream")


def get_word_frequencies(title: str, markdown_content: str) -> List[List]:
    import jieba
    import jieba.analyse

    try:
        text_content = re.sub(r"<[^>]+>", "", f"{title} {markdown_content}")
        stopwords = {
            "已经",
            "我们",
            "甚至",
            "现在",
            "展开",
            "转发",
            "评论",
            "点赞",
            "回复",
            "图片",
            "视频",
            "网页",
            "链接",
            "微博",
            "知乎",
            "百度",
        }

        tags_tfidf = jieba.analyse.extract_tags(text_content, topK=40, withWeight=True)
        tags_rank = jieba.analyse.textrank(text_content, topK=40, withWeight=True)

        unique_map = {}
        for word, weight in tags_tfidf + tags_rank:
            if len(word) < 2 or word in stopwords:
                continue
            unique_map[word] = max(unique_map.get(word, 0), weight)

        if not unique_map:
            raise ValueError("no valid keywords")

        max_weight = max(unique_map.values())
        wordcloud = [[word, int((weight / max_weight) * 60 + 20)] for word, weight in unique_map.items()]
        wordcloud.sort(key=lambda item: item[1], reverse=True)

        return wordcloud[:30]
    except Exception:
        raw_words = [word for word in jieba.lcut(title) if len(word) > 1]
        return [[word, 50] for word in dict.fromkeys(raw_words)][:25]


@router.get("/articles/{article_id}/analyze")
async def analyze_article(article_id: int, force_refresh: bool = False, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return {"error": "未找到记录"}

    if force_refresh:
        analysis_cache.pop(article_id, None)
        article.ai_summary = ""
        article.ai_sentiment = None
        db.commit()

    async def _analyze_core():
        """实际的分析流程（原 event_generator 的 body）。为支持外层去重/限流，抽成独立生成器。"""
        started_at = time.perf_counter()
        can_use_cached_content = bool(article.content) and not _is_invalid_cached_content(article.content) and not force_refresh

        if not can_use_cached_content:
            if article.content and _is_invalid_cached_content(article.content):
                article.content = ""
                article.ai_summary = ""
                article.ai_sentiment = None
                db.commit()

            yield f"data: {json.dumps({'type': 'status', 'msg': '正在抓取正文与结构化数据...'}, ensure_ascii=False)}\n\n"
            fetch_started_at = time.perf_counter()
            try:
                markdown_content = await extract_article_content(article.url)
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'msg': f'采集异常: {exc}'}, ensure_ascii=False)}\n\n"
                return
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"[ANALYZE] article={article_id} fetch={time.perf_counter() - fetch_started_at:.2f}s"
            )
        else:
            markdown_content = article.content

        _print_analysis_debug(article, markdown_content)

        # 视频事件识别：reader 返回以 🎬 开头 → 说明此热点主体为视频/微头条
        # → 级联删除（article + event_articles；事件若因此 article_count=0 也删）
        if isinstance(markdown_content, str) and markdown_content.startswith("🎬"):
            try:
                ea_rows = db.query(EventArticle).filter(EventArticle.article_id == article.id).all()
                affected_event_ids = {r.event_id for r in ea_rows}
                for r in ea_rows:
                    db.delete(r)
                db.delete(article)
                db.commit()
                # 清理因此而变空的事件
                for eid in affected_event_ids:
                    remaining = db.query(EventArticle).filter(EventArticle.event_id == eid).count()
                    if remaining == 0:
                        ev = db.query(Event).filter(Event.id == eid).first()
                        if ev:
                            db.delete(ev)
                    else:
                        # 仍有其他文章 → 同步更新 article_count
                        ev = db.query(Event).filter(Event.id == eid).first()
                        if ev:
                            ev.article_count = remaining
                db.commit()
            except Exception as exc:
                db.rollback()
                print(f"[视频清理] 失败: {exc}")
            yield f"data: {json.dumps({'type': 'skip_video', 'msg': '此热点为视频内容，已从榜单移除'}, ensure_ascii=False)}\n\n"
            return

        if isinstance(markdown_content, str) and (markdown_content.startswith("❌") or markdown_content.startswith("鉂")):
            try:
                fallback_wc = get_word_frequencies(article.title, "")
                fallback_emo = emotion_engine.analyze(article.title or "")
                yield f"data: {json.dumps({'type': 'metadata', 'wordcloud': fallback_wc, 'emotions': fallback_emo}, ensure_ascii=False)}\n\n"
            except Exception:
                pass
            yield f"data: {json.dumps({'type': 'error', 'msg': markdown_content}, ensure_ascii=False)}\n\n"
            return

        if article_id in analysis_cache and not force_refresh:
            cached_data = analysis_cache[article_id]
            cached_summary = cached_data.get("summary") or (article.ai_summary if article.ai_summary else "")
            if cached_summary:
                yield f"data: {json.dumps({'type': 'metadata', 'wordcloud': cached_data.get('wordcloud'), 'emotions': cached_data.get('emotions')}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'raw_content', 'text': article.content or markdown_content}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content_start'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content', 'text': cached_summary}, ensure_ascii=False)}\n\n"
                yield "data: {\"type\": \"content_end\"}\n\n"
                return

        try:
            from app.llm import analyze_article_content_stream
            
            # 使用 Queue 编排并行任务，实现“双轨并行”推送
            event_queue = asyncio.Queue()

            async def feature_producer():
                try:
                    # 并行执行本地 NLP 特征提取（不阻塞 LLM 启动）
                    feature_started_at = time.perf_counter()
                    wordcloud, emotions = await asyncio.gather(
                        asyncio.to_thread(get_word_frequencies, article.title, markdown_content[:6000]),
                        asyncio.to_thread(emotion_engine.analyze, markdown_content[:4000])
                    )
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] [ANALYZE] article={article_id} features_ready={time.perf_counter() - feature_started_at:.2f}s")
                    await event_queue.put({"type": "metadata", "wordcloud": wordcloud, "emotions": emotions})
                except Exception as e:
                    print(f"Feature extraction failed: {e}")

            async def llm_producer():
                try:
                    full_text = ""
                    await event_queue.put({"type": "status", "msg": "正在启动决策模型，深度内容生成中..."})
                    await event_queue.put({"type": "content_start"})
                    
                    async for chunk in analyze_article_content_stream(article.title, article.extra_info or "", markdown_content):
                        full_text += chunk
                        await event_queue.put({"type": "content", "text": chunk})
                    
                    await event_queue.put({"type": "content_end"})
                    # 保存到缓存与数据库
                    analysis_cache[article_id] = {"summary": full_text} # 稍后补充 metadata
                    return full_text
                except Exception as e:
                    await event_queue.put({"type": "error", "msg": f"LLM 研判失败: {e}"})
                    return ""

            # 启动两个生产任务
            f_task = asyncio.create_task(feature_producer())
            l_task = asyncio.create_task(llm_producer())
            
            # 消费队列直至 LLM 完成
            while not l_task.done() or not event_queue.empty():
                try:
                    # 使用 wait_for 防止死等导致 generator 泄露
                    msg = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                    if msg.get("type") == "metadata":
                        # 同步到缓存
                        if article_id in analysis_cache:
                           analysis_cache[article_id].update({"wordcloud": msg["wordcloud"], "emotions": msg["emotions"]})
                        else:
                           analysis_cache[article_id] = {"wordcloud": msg["wordcloud"], "emotions": msg["emotions"]}
                except asyncio.TimeoutError:
                    if l_task.done() and event_queue.empty(): break
                    continue

            # 最后持久化并同步数据
            final_summary = await l_task
            await f_task # 确保特性任务也结束了
            
            cached = analysis_cache.get(article_id, {})
            cached["summary"] = final_summary
            analysis_cache[article_id] = cached
            if not can_use_cached_content:
                article.content = markdown_content
            article.ai_summary = final_summary
            article.ai_sentiment = cached.get("emotions", [{"label": "neutral"}])[0]["label"] if cached.get("emotions") else "neutral"
            db.commit()

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'msg': f'研判中断: {exc}'}, ensure_ascii=False)}\n\n"

            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"[ANALYZE] article={article_id} total={time.perf_counter() - started_at:.2f}s"
            )
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'msg': f'研判链路中断: {exc}'}, ensure_ascii=False)}\n\n"

    async def event_generator():
        """
        外层去重 + 限流包装：
        - 相同 article_id 并发请求只跑一次，其余等待后读缓存
        - 全局同时最多 3 个分析任务在跑，保护线程池 / LLM / 下游抓取
        """
        # 1) Dedup：注册或复用 inflight
        inflight_event = None
        is_leader = False
        async with _analyze_inflight_lock:
            existing = _analyze_inflight.get(article_id)
            if existing and not force_refresh:
                inflight_event = existing
            else:
                inflight_event = asyncio.Event()
                _analyze_inflight[article_id] = inflight_event
                is_leader = True

        if not is_leader:
            yield f"data: {json.dumps({'type': 'status', 'msg': '检测到相同分析在进行中，等待复用结果...'}, ensure_ascii=False)}\n\n"
            try:
                await asyncio.wait_for(inflight_event.wait(), timeout=180.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'error', 'msg': '等待上游分析超时'}, ensure_ascii=False)}\n\n"
                return
            cached_data = analysis_cache.get(article_id)
            summary = (cached_data or {}).get("summary")
            if summary:
                yield f"data: {json.dumps({'type': 'metadata', 'wordcloud': cached_data.get('wordcloud'), 'emotions': cached_data.get('emotions')}, ensure_ascii=False)}\n\n"
                if article.content:
                    yield f"data: {json.dumps({'type': 'raw_content', 'text': article.content}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content_start'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'content', 'text': summary}, ensure_ascii=False)}\n\n"
                yield "data: {\"type\": \"content_end\"}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'msg': '上游分析未产出可用结果'}, ensure_ascii=False)}\n\n"
            return

        # 2) Leader：等待全局并发令牌（同时最多 3 篇）
        sem_acquired = False
        try:
            # 告知客户端排队情况
            try:
                waiting = _analyze_global_semaphore._value <= 0
            except Exception:
                waiting = False
            if waiting:
                yield f"data: {json.dumps({'type': 'status', 'msg': '系统负载较高，已进入队列等待...'}, ensure_ascii=False)}\n\n"
            await _analyze_global_semaphore.acquire()
            sem_acquired = True

            async for chunk in _analyze_core():
                yield chunk
        finally:
            if sem_acquired:
                _analyze_global_semaphore.release()
            # 唤醒等待者，清除 inflight 注册
            inflight_event.set()
            async with _analyze_inflight_lock:
                if _analyze_inflight.get(article_id) is inflight_event:
                    _analyze_inflight.pop(article_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/articles/{article_id}/chat")
async def chat_with_article(article_id: int, req: ChatRequest, db: Session = Depends(get_db)):
    from app.llm import chat_with_news

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return {"error": "文章未找到"}

    context = (
        f"文章标题: {article.title}\n"
        f"内容摘要: {article.ai_summary or '暂无'}\n"
        f"正文参考: {article.content[:2000] if article.content else '暂无'}"
    )
    custom_query = f"基于以下背景信息，请回答我的问题：\n\n【背景】\n{context}\n\n【追问】\n{req.query}"
    # chat_with_news 是同步 httpx 调用（可能 5~30s），不能直接在 async 路由里阻塞事件循环。
    answer = await asyncio.to_thread(chat_with_news, custom_query)
    return {"answer": answer}


@router.post("/ai/chat", response_model=ChatResponse)
def chat_news(req: ChatRequest):
    from app.llm import chat_with_news

    return ChatResponse(answer=chat_with_news(req.query))


@router.post("/credentials/{source_id}")
async def save_credentials(source_id: str, data: Dict):
    if source_id in PUBLIC_SOURCE_IDS:
        return {"message": f"{SOURCE_NAME_MAP.get(source_id, source_id)} 使用公开正文接口，无需 Cookie。"}

    raw_cookie = data.get("cookie", "")
    if not raw_cookie:
        return {"error": "Cookie 不能为空"}

    success = save_cookie_credential(source_id, raw_cookie)
    if success:
        return {"message": f"{source_id} 凭据更新成功，物理爬虫已就绪。"}
    return {"error": "凭据保存失败"}


@router.get("/credentials/status")
def get_all_credentials_status():
    status = {}
    for source_id in COOKIE_SOURCE_IDS:
        status[source_id] = check_credential_exists(source_id)
    for source_id in PUBLIC_SOURCE_IDS:
        status[source_id] = True
    return status


def _detect_platform(query: str):
    lowered = query.lower()
    for keyword, source_id in PLATFORM_MAP.items():
        if keyword in lowered:
            return source_id
    return None


INTENT_KEYWORD_MAP = {
    "炒股": ["股票", "A股", "股市", "牛股", "涨停", "跌停", "收购", "上市", "股价", "大盘"],
    "投资": ["理财", "基金", "债券", "收益", "资产", "投资", "融资", "并购", "IPO"],
    "房价": ["楼市", "房价", "地产", "恒大", "碧桂园", "楼盘", "房贷", "买房"],
    "科技": ["AI", "人工智能", "芯片", "半导体", "5G", "机器人", "大模型"],
    "国际": ["伊朗", "美国", "俄罗斯", "中东", "关税", "制裁", "战争", "外交"],
    "教育": ["高考", "考研", "招生", "学校", "教育", "教师"],
    "医疗": ["医院", "药品", "疫情", "医保", "手术", "癌症"],
}


def _expand_intent_keywords(query: str) -> list:
    expanded = [query]
    for intent, keywords in INTENT_KEYWORD_MAP.items():
        if intent in query:
            expanded.extend(keywords)
    return expanded


def _mcp_search(query: str, db: Session):
    query = (query or "").strip()
    platform = _detect_platform(query)
    
    events_found = search_events(db, query, limit=3) if query else []
    topics_found = search_topics(db, query, limit=2) if query else []
    
    if platform:
        items = (
            db.query(Article)
            .filter(Article.source_id == platform)
            .order_by(case((Article.rank.is_(None), 1), else_=0), Article.rank.asc(), Article.pub_date.desc())
            .limit(30)
            .all()
        )
        return {"articles": [marshal_article(item) for item in items], "events": [], "topics": []}

    if query:
        keywords = _expand_intent_keywords(query)
        filters = []
        for kw in keywords:
            filters.append(Article.title.like(f"%{kw}%"))
            filters.append(Article.ai_summary.like(f"%{kw}%"))
            filters.append(Article.extra_info.like(f"%{kw}%"))
        items = (
            db.query(Article)
            .filter(or_(*filters))
            .order_by(case((Article.rank.is_(None), 1), else_=0), Article.rank.asc(), Article.pub_date.desc())
            .limit(30)
            .all()
        )
        return {
            "articles": [marshal_article(item) for item in items],
            "events": [marshal_event(e, db=db) for e in events_found],
            "topics": [marshal_topic(t) for t in topics_found]
        }
    
    return {"articles": [], "events": [], "topics": []}


async def _mcp_stats_report(query: str, history: list, db: Session):
    from app.llm import chat_with_news_stream
    from sqlalchemy import func as sa_func

    source_counts = (
        db.query(Article.source_id, sa_func.count(Article.id))
        .group_by(Article.source_id)
        .all()
    )
    top_events = (
        db.query(Event)
        .order_by(Event.article_count.desc())
        .limit(10)
        .all()
    )
    sentiment_counts = (
        db.query(Article.ai_sentiment, sa_func.count(Article.id))
        .filter(Article.ai_sentiment != None)
        .group_by(Article.ai_sentiment)
        .all()
    )
    total_articles = db.query(Article).count()
    total_events = db.query(Event).count()
    total_topics = db.query(Topic).count()

    stats_lines = [
        f"数据库总览: {total_articles}条热搜, {total_events}个事件, {total_topics}个主题",
        "",
        "各平台热搜数量:",
    ]
    for sid, cnt in sorted(source_counts, key=lambda x: -x[1]):
        stats_lines.append(f"  {SOURCE_NAME_MAP.get(sid, sid)}: {cnt}条")

    stats_lines.append("")
    stats_lines.append("今日最热事件TOP10:")
    for i, e in enumerate(top_events, 1):
        stats_lines.append(f"  {i}. {e.title} ({e.article_count}条热搜, {e.platform_count}个平台)")

    if sentiment_counts:
        stats_lines.append("")
        stats_lines.append("舆情情绪分布:")
        for senti, cnt in sorted(sentiment_counts, key=lambda x: -x[1]):
            stats_lines.append(f"  {senti or '未知'}: {cnt}条")

    stats_text = "\n".join(stats_lines)

    system_prompt = (
        "你是舆镜数据分析师。根据下方真实统计数据，生成一份简洁的统计分析报告。\n"
        "要求：\n"
        "- 先给出总览结论\n"
        "- 各平台热搜数量排名和占比\n"
        "- 最热事件TOP5简要分析\n"
        "- 舆情情绪总结\n"
        "- 保留具体数字，中文回复，紧凑输出\n\n"
        f"统计数据：\n{stats_text}"
    )

    async def gen():
        yield f"data: {json.dumps({'type': 'content_start'}, ensure_ascii=False)}\n\n"
        async for chunk in chat_with_news_stream(system_prompt, history, query):
            yield f"data: {json.dumps({'type': 'content', 'text': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'content_end'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


async def _generate_follow_up_suggestions(user_query: str, assistant_reply: str) -> list[str]:
    """基于用户提问和AI回复，生成3条追问建议。"""
    from app.llm import get_llm

    try:
        llm = get_llm()
    except Exception:
        return []

    prompt_text = (
        "基于以下对话，生成3条简短的追问建议（每条不超过15字），帮助用户深入了解相关舆情。\n"
        "只输出3行纯文本，每行一条，不加序号和标点。\n\n"
        f"用户提问：{user_query[:200]}\n"
        f"AI回复：{assistant_reply[:500]}"
    )

    try:
        result = await llm.ainvoke(prompt_text)
        lines = [line.strip() for line in result.content.strip().splitlines() if line.strip()]
        # 清理序号前缀
        cleaned = []
        for line in lines[:3]:
            cleaned.append(re.sub(r"^[\d.、\-\)）]+\s*", "", line))
        return [s for s in cleaned if 2 <= len(s) <= 30]
    except Exception:
        return []


@router.post("/mcp/ask")
async def mcp_query_engine(req: ChatRequest, db: Session = Depends(get_db)):
    from app.llm import chat_with_news_stream
    import re as _re

    query = req.query

    # 智能路由：检测日报/周报/对比指令
    q_lower = query.strip()
    # 预清洗口语化前缀：把"对比一下"、"比较一下"等中文助词剥离，保证后续正则稳定
    q_lower = _re.sub(r"(对比|比较)\s*一下\s*", r"\1 ", q_lower)
    if _re.search(r"日报|今日[总汇报]|今天[总汇报]", q_lower):
        return await ai_report(report_type="daily", db=db)
    if _re.search(r"周报|本周[总汇报]|这周[总汇报]", q_lower):
        return await ai_report(report_type="weekly", db=db)
    # 对比意图识别：先尝试三元模式"对比 A 和 B 对 Z 的看法/态度/评论..."
    topic_pattern = _re.search(
        r"对比\s*[「「]?(.+?)[」」]?\s*[和与]\s*[「「]?(.+?)[」」]?\s*对\s*[「「]?(.+?)[」」]?\s*的\s*(?:看法|评论|态度|反应|观点|声音|报道|立场|讨论|情绪|情感|报导|评价)",
        q_lower,
    )
    if topic_pattern:
        compare_req = CompareRequest(
            a=topic_pattern.group(1).strip(),
            b=topic_pattern.group(2).strip(),
            topic=topic_pattern.group(3).strip(),
            history=req.history,
        )
        return await ai_compare(compare_req, db=db)
    compare_match = _re.search(r"对比\s*[「「]?(.+?)[」」]?\s*[和与vs]\s*[「「]?(.+?)[」」]?\s*$", q_lower)
    if compare_match:
        compare_req = CompareRequest(
            a=compare_match.group(1).strip(),
            b=compare_match.group(2).strip(),
            history=req.history,
        )
        return await ai_compare(compare_req, db=db)

    if _re.search(r"统计[分报]|数据报告|平台.*对比.*数量|TOP\s*\d|情绪分布", q_lower):
        return await _mcp_stats_report(query, req.history or [], db)

    search_data = _mcp_search(query, db)
    
    relevant_articles = search_data.get("articles", [])
    relevant_events = search_data.get("events", [])
    relevant_topics = search_data.get("topics", [])

    has_keyword_match = len(relevant_articles) > 0 or len(relevant_events) > 0 or len(relevant_topics) > 0

    if not has_keyword_match:
        items = db.query(Article).order_by(Article.pub_date.desc()).limit(30).all()
        relevant_articles = [marshal_article(item) for item in items]

    ctx_lines = []
    if relevant_topics:
        ctx_lines.append(f"【最新宏观主题】")
        for t in relevant_topics:
            ctx_lines.append(f"- 话题: {t['title']} | 热度:{t.get('article_count',0)}条新闻 | 概要: {t['summary']}")
    if relevant_events:
        ctx_lines.append(f"【最新重大事件】")
        for e in relevant_events:
            ctx_lines.append(f"- 事件: {e['title']} | 平台数:{e.get('platform_count',0)} | 概要: {e['summary']}")
    
    ctx_lines.append(f"【平台具体热搜新闻】")
    for a in relevant_articles[:20]:
        source_name = SOURCE_NAME_MAP.get(a["source_id"], a["source_id"])
        ctx_lines.append(f"[{source_name}] {a['title']}")
        
    ctx = "\n".join(ctx_lines)

    recent_history = req.history[-4:] if req.history else []
    history_context = "\n".join(
        [
            f"{'用户' if item.get('role') == 'user' else '助手'}: {item.get('content', '')[:200]}"
            for item in recent_history
        ]
    )

    system_prompt = (
        "你是舆镜舆情研判助手。你的能力：\n"
        "- 基于本地数据库检索结果回答用户问题\n"
        "- 对舆情趋势做分析和研判（基于数据推理，不编造）\n"
        "- 总结某平台/话题的舆论态势\n"
        "- 用户可以说「日报」生成今日简报，「对比 X 和 Y」做对比分析\n\n"
        "规则：\n"
        "- 优先基于下方数据回答，数据不足时可做合理推理但需标明\n"
        "- 如果用户点名平台（微博、知乎、头条、百度、B站、澎湃、华尔街见闻、财联社），优先概括该平台\n"
        "- 输出紧凑：结论先行，必要时 3-5 条要点\n"
        "- 保留具体主题名和数字\n"
        "- 不用嵌套列表、Markdown 表格\n"
        "- 中文回复\n\n"
        f"最近对话：\n{history_context or '无'}\n\n"
        f"本地数据库（{len(relevant_articles)} 条情报）：\n{ctx}"
    )

    async def event_generator():
        yield f"data: {json.dumps({'type': 'content_start'}, ensure_ascii=False)}\n\n"

        content_pieces = []
        async for chunk in chat_with_news_stream(system_prompt, req.history or [], query):
            yield f"data: {json.dumps({'type': 'content', 'text': chunk}, ensure_ascii=False)}\n\n"
            content_pieces.append(chunk)

        if has_keyword_match:
            yield f"data: {json.dumps({'type': 'summoned_items', 'items': relevant_articles[:5]}, ensure_ascii=False)}\n\n"

        # 生成追问式推荐
        try:
            suggestions = await _generate_follow_up_suggestions(query, "".join(content_pieces))
            if suggestions:
                yield f"data: {json.dumps({'type': 'suggestions', 'items': suggestions}, ensure_ascii=False)}\n\n"
        except Exception:
            pass

        yield f"data: {json.dumps({'type': 'content_end'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# AI 日报 / 周报
# ---------------------------------------------------------------------------
@router.get("/ai/report")
async def ai_report(report_type: str = "daily", db: Session = Depends(get_db)):
    from app.llm import chat_with_news_stream

    hours = 24 if report_type == "daily" else 168
    label = "日报" if report_type == "daily" else "周报"
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    events = (
        db.query(Event)
        .filter(Event.latest_article_time >= cutoff)
        .order_by(Event.article_count.desc())
        .limit(20)
        .all()
    )
    articles = (
        db.query(Article)
        .filter(Article.fetch_time >= cutoff)
        .order_by(Article.fetch_time.desc())
        .limit(40)
        .all()
    )

    ctx_lines = [f"过去 {hours} 小时聚合事件 TOP{len(events)}"]
    for e in events:
        ctx_lines.append(f"- {e.title}（{e.platform_count}个平台，{e.article_count}条热点）")
    ctx_lines.append(f"\n平台热搜摘要 {len(articles)} 条")
    for a in articles[:30]:
        ctx_lines.append(f"[{SOURCE_NAME_MAP.get(a.source_id, a.source_id)}] {a.title}")

    system_prompt = (
        f"你是舆镜舆情{label}生成器。根据下方本地数据库数据，生成一份结构清晰的{label}。\n"
        "格式要求：\n"
        f"1. 开头用一段话总结过去{'24小时' if report_type == 'daily' else '一周'}的整体舆论态势\n"
        "2. 分板块列出 3-5 个重点事件，每个事件：标题 + 一句话概括 + 涉及平台\n"
        "3. 结尾给出 1-2 条舆情走势研判\n"
        "使用中文，不要使用 Markdown 表格。保持紧凑。\n\n"
        f"数据：\n" + "\n".join(ctx_lines)
    )

    async def report_event_generator():
        yield f"data: {json.dumps({'type': 'content_start'}, ensure_ascii=False)}\n\n"
        async for chunk in chat_with_news_stream(system_prompt, [], f"请生成{label}"):
            yield f"data: {json.dumps({'type': 'content', 'text': chunk}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'content_end'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(report_event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# AI 对比分析
# ---------------------------------------------------------------------------
def _build_compare_metrics(label: str, articles: list, events: list) -> dict:
    """把 articles/events 聚合为前端仪表盘所需的结构化对比数据。"""
    from collections import Counter

    now = datetime.utcnow()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_48h = now - timedelta(hours=48)

    # 情绪分布
    sentiment_counter = Counter()
    platform_counter = Counter()
    for a in articles:
        sent = (a.ai_sentiment or "neutral").lower()
        # 归一化到 5 类
        if sent in ("positive", "joy", "喜悦", "positive_low", "anticipation", "trust"):
            bucket = "positive"
        elif sent in ("negative", "anger", "愤怒", "sadness", "悲伤", "fear", "恐惧", "disgust", "厌恶"):
            bucket = "negative"
        elif sent in ("surprise", "惊讶"):
            bucket = "surprise"
        else:
            bucket = "neutral"
        sentiment_counter[bucket] += 1
        platform_counter[SOURCE_NAME_MAP.get(a.source_id, a.source_id)] += 1

    # 7 天时间轴（逐日文章数）
    timeline_counts = Counter()
    for a in articles:
        t = a.pub_date or a.fetch_time
        if not t:
            continue
        key = t.strftime("%m-%d")
        timeline_counts[key] += 1
    # 最近 7 天从新到旧展示；若不足 7 天只展示实际天数
    days = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).strftime("%m-%d")
        days.append({"date": day, "count": timeline_counts.get(day, 0)})

    # 24h 变化：0-24h 文章数 vs 24-48h 文章数
    c_0_24 = sum(1 for a in articles if (a.pub_date or a.fetch_time or datetime.min) >= cutoff_24h)
    c_24_48 = sum(1 for a in articles if cutoff_48h <= (a.pub_date or a.fetch_time or datetime.min) < cutoff_24h)
    if c_24_48 > 0:
        trend_pct = round((c_0_24 - c_24_48) / c_24_48 * 100, 1)
    else:
        trend_pct = None

    # 代表情报 top3
    rep = [marshal_article(a) for a in articles[:3]]

    return {
        "label": label,
        "article_count": len(articles),
        "event_count": len(events),
        "platform_count": len(platform_counter),
        "platforms": [{"name": k, "count": v} for k, v in platform_counter.most_common(6)],
        "sentiment": dict(sentiment_counter),
        "timeline": days,
        "trend_24h": {"current": c_0_24, "previous": c_24_48, "pct": trend_pct},
        "representative_articles": rep,
        "events": [
            {"id": e.id, "title": e.title, "article_count": e.article_count, "platform_count": e.platform_count}
            for e in events
        ],
    }


_PLATFORM_NAME_TO_SOURCE_ID = {
    "微博": "weibo_hot_search",
    "知乎": "zhihu_hot_question",
    "头条": "toutiao_hot",
    "今日头条": "toutiao_hot",
    "百度": "baidu_hot",
    "百度热搜": "baidu_hot",
    "澎湃": "thepaper_hot",
    "澎湃新闻": "thepaper_hot",
    "哔哩哔哩": "bilibili_hot_video",
    "b站": "bilibili_hot_video",
    "B站": "bilibili_hot_video",
    "财联社": "cls_hot",
    "华尔街": "wallstreetcn_hot",
    "华尔街见闻": "wallstreetcn_hot",
    "36氪": "36kr_quick",
    "少数派": "sspai_hot",
    "虎扑": "hupu_bxj",
}


def _resolve_compare_source(name: str) -> Optional[str]:
    """把用户输入的平台别名归一化到 source_id；非平台名返回 None。"""
    key = (name or "").strip().lower()
    for alias, sid in _PLATFORM_NAME_TO_SOURCE_ID.items():
        if alias.lower() == key:
            return sid
    return None


@router.post("/ai/compare")
async def ai_compare(req: CompareRequest, db: Session = Depends(get_db)):
    from app.llm import chat_with_news_stream

    topic = (req.topic or "").strip()

    def gather(name: str):
        """根据输入解析查询条件：
        - 若 name 是已知平台别名（微博/知乎/...）→ 按 source_id 过滤 + topic LIKE（如有）
        - 否则 → 按 name LIKE（原行为）；若 topic 提供也叠加 LIKE topic
        """
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
        items = q.order_by(Article.fetch_time.desc()).limit(40).all()

        # 事件搜索：平台模式下用 topic 当查询词，否则用 name
        search_query = topic if (source_id and topic) else name
        evts = search_events(db, search_query, limit=5) if search_query else []
        return items, evts

    a_articles, a_events = gather(req.a)
    b_articles, b_events = gather(req.b)

    metrics_a = _build_compare_metrics(req.a, a_articles, a_events)
    metrics_b = _build_compare_metrics(req.b, b_articles, b_events)

    def fmt_block(label, arts, evts):
        lines = [f"【{label}】"]
        for e in evts:
            lines.append(f"- 事件: {e.title}（{e.platform_count}平台，{e.article_count}条）")
        for a in arts[:15]:
            lines.append(f"[{SOURCE_NAME_MAP.get(a.source_id, a.source_id)}] {a.title}")
        return "\n".join(lines)

    ctx = fmt_block(req.a, a_articles, a_events) + "\n\n" + fmt_block(req.b, b_articles, b_events)

    # 用数值 metrics 明确注入 prompt，让 LLM 总结基于量化数据而非"盲猜"
    quant_a = f"{req.a}: {metrics_a['article_count']}条 / {metrics_a['platform_count']}平台 / 情绪{metrics_a['sentiment']}"
    quant_b = f"{req.b}: {metrics_b['article_count']}条 / {metrics_b['platform_count']}平台 / 情绪{metrics_b['sentiment']}"

    system_prompt = (
        "你是舆镜舆情对比分析引擎。用户已经在界面看到量化数据卡片（热度/情绪/平台/趋势），\n"
        "你负责在卡片下方给出专业研判文字，**无需重复数值指标**，聚焦定性分析：\n"
        "1. 关键差异点：两个话题最显著的叙事/立场/议题分歧\n"
        "2. 平台差异：哪些平台更关注哪一方\n"
        "3. 风险与建议：给出一句最有价值的研判结论\n"
        "中文、紧凑、不用 Markdown 表格。\n\n"
        f"量化摘要：\n{quant_a}\n{quant_b}\n\n"
        f"原始内容：\n{ctx}"
    )

    async def compare_event_generator():
        # 先推送结构化 metrics（前端据此渲染仪表盘）
        payload = {"type": "compare_metrics", "a": metrics_a, "b": metrics_b}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

        yield f"data: {json.dumps({'type': 'content_start'}, ensure_ascii=False)}\n\n"
        async for chunk in chat_with_news_stream(system_prompt, req.history or [], f"对比 {req.a} 和 {req.b}"):
            yield f"data: {json.dumps({'type': 'content', 'text': chunk}, ensure_ascii=False)}\n\n"
        summoned = [marshal_article(a) for a in (a_articles[:3] + b_articles[:3])]
        if summoned:
            yield f"data: {json.dumps({'type': 'summoned_items', 'items': summoned}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'content_end'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(compare_event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# PDF 报告导出
# ---------------------------------------------------------------------------
def _render_markdown_line_with_bold(pdf, line: str, base_size: int, line_h: float = 6):
    """
    手动处理行内 `**xxx**` 粗体（fpdf2 的 markdown=True 与中文字体存在渲染异常）。
    将一行拆为 [普通, 粗体, 普通, ...] 片段，逐段以 write() 输出以保留行内粗体，
    遇到超宽自动折行。
    """
    # 孤立的 ** 不渲染
    if line.count("**") % 2 != 0:
        line = line.replace("**", "")

    import re as _re
    segments = _re.split(r"\*\*(.+?)\*\*", line)
    for idx, seg in enumerate(segments):
        if not seg:
            continue
        style = "B" if idx % 2 == 1 else ""
        pdf.set_font("msyh", style, base_size)
        # write() 自动换行、保持光标在行内；最后 ln() 结束
        pdf.write(line_h, seg)
    pdf.ln(line_h)


def _normalize_pdf_body(body: str) -> str:
    """
    清洗 LLM 输出的常见排版噪声：
    1. "\\n3.\\n2026年..." 这种数字/中文序号独占一行 → 合并到下一行，防止 PDF 出现孤立序号
    2. 连续 3 个以上空行 → 压缩为 2 个
    3. 行尾空白清除
    """
    import re as _re
    if not body:
        return body

    # 把 "\n<序号>\n<正文>" 合并为 "\n<序号> <正文>"
    # 序号：数字+. / 数字、/ 一二三+. / 一二三、
    pat = _re.compile(r"\n([0-9]+[\.、]|[一二三四五六七八九十]+[\.、])\s*\n[ \t]*(?=\S)")
    prev = None
    while prev != body:
        prev = body
        body = pat.sub(r"\n\1 ", body)

    # 多余空行压缩
    body = _re.sub(r"\n{3,}", "\n\n", body)
    # 行尾空白
    body = _re.sub(r"[ \t]+\n", "\n", body)
    return body


def _render_markdown_body(pdf, body: str, base_size: int = 10):
    """把 body 按行扫描，渲染 Markdown 标题 / 粗体等常见语法到 PDF。"""
    if not body:
        return

    body = _normalize_pdf_body(body)

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        stripped = line.lstrip()

        if not stripped:
            pdf.ln(3)
            continue

        # 标题：#/##/###（去掉 # 和可能残留的 *）
        if stripped.startswith("### "):
            pdf.set_font("msyh", "B", base_size + 1)
            pdf.multi_cell(0, 7, stripped[4:].strip(" *"))
            continue
        if stripped.startswith("## "):
            pdf.set_font("msyh", "B", base_size + 3)
            pdf.multi_cell(0, 9, stripped[3:].strip(" *"))
            pdf.ln(1)
            continue
        if stripped.startswith("# "):
            pdf.set_font("msyh", "B", base_size + 5)
            pdf.multi_cell(0, 10, stripped[2:].strip(" *"))
            pdf.ln(2)
            continue

        # 普通行：行内 `**xxx**` 渲染为粗体
        _render_markdown_line_with_bold(pdf, line, base_size, line_h=6)


def _build_pdf(title: str, sections: list[dict], images: Optional[list[str]] = None) -> bytes:
    """
    生成 PDF 文档。
    sections: [{"heading": str, "body": str}, ...]
    images: 可选的 base64 PNG dataURL 列表，按序插入正文之前，用于承载前端截图（如对比仪表盘）。
    body 支持基础 Markdown 语法（标题、粗体）。
    """
    from fpdf import FPDF
    import base64
    import io
    import logging as _logging
    # 压制 fontTools 的 "MERG NOT subset; don't know how to subset; dropped" 警告
    # 这是中文字体子集化时的已知噪声，不影响 PDF 生成
    _logging.getLogger("fontTools.subset").setLevel(_logging.ERROR)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # 注册中文字体（微软雅黑）。同时注册 I/BI 变体（复用常规/粗体字重），
    # 否则启用 markdown=True 时 fpdf2 切换到未注册字体会抛 FPDFException。
    font_path = "C:/Windows/Fonts/msyh.ttc"
    bold_path = "C:/Windows/Fonts/msyhbd.ttc"
    pdf.add_font("msyh", "", font_path)
    pdf.add_font("msyh", "B", bold_path)
    pdf.add_font("msyh", "I", font_path)
    pdf.add_font("msyh", "BI", bold_path)
    pdf.set_font("msyh", "", 10)

    # 标题
    pdf.set_font("msyh", "B", 18)
    pdf.cell(0, 14, title, new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("msyh", "", 9)
    pdf.set_text_color(130, 130, 130)
    pdf.cell(0, 8, f"舆镜 YuJing · {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    # 先插入截图（若有）：让可视化在文字研判之前，读者更容易抓住重点
    if images:
        page_width = pdf.w - pdf.l_margin - pdf.r_margin
        for data_url in images:
            try:
                # 支持形如 "data:image/png;base64,xxxxx" 或裸 base64
                if "," in data_url:
                    b64_part = data_url.split(",", 1)[1]
                else:
                    b64_part = data_url
                raw = base64.b64decode(b64_part)
                pdf.image(io.BytesIO(raw), w=page_width)
                pdf.ln(4)
            except Exception as exc:
                print(f"[PDF] 嵌入截图失败（忽略）: {exc}")

    for section in sections:
        if section.get("heading"):
            pdf.set_font("msyh", "B", 13)
            pdf.cell(0, 10, section["heading"], new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
        if section.get("body"):
            _render_markdown_body(pdf, section["body"], base_size=10)
            pdf.ln(4)

    return bytes(pdf.output())


def _pdf_disposition(name: str) -> dict:
    """生成兼容中文的 Content-Disposition header。"""
    from urllib.parse import quote
    # ASCII-only fallback (\w 含中文，需用 re.ASCII)
    ascii_name = re.sub(r'[^\w.\-]', '_', name, flags=re.ASCII)
    utf8_name = quote(name, safe='')
    return {"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"}


@router.get("/articles/{article_id}/export_pdf")
def export_article_pdf(article_id: int, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return Response(content="文章不存在", status_code=404)

    source_name = SOURCE_NAME_MAP.get(article.source_id, article.source_id)
    sections = [
        {"heading": "基本信息", "body": f"来源: {source_name}\n发布时间: {article.pub_date or '未知'}\n链接: {article.url or '无'}"},
    ]
    if article.ai_summary:
        sections.append({"heading": "AI 分析摘要", "body": article.ai_summary})
    if article.content:
        sections.append({"heading": "正文内容", "body": article.content[:5000]})

    pdf_bytes = _build_pdf(article.title or "文章报告", sections)
    fname = re.sub(r'[\\/:*?"<>|]', '_', (article.title or "article")[:40]) + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_pdf_disposition(fname),
    )


@router.get("/events/{event_id}/export_pdf")
def export_event_pdf(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return Response(content="事件不存在", status_code=404)

    sections = [
        {"heading": "事件概要", "body": event.summary or "暂无概要"},
    ]

    # 关键词
    if event.keywords:
        try:
            kw_list = json.loads(event.keywords)
            sections.append({"heading": "关键词", "body": "、".join(kw_list[:15])})
        except Exception:
            pass

    # 统计
    sections.append({"heading": "统计", "body": f"关联文章: {event.article_count} 条\n覆盖平台: {event.platform_count} 个\n情感倾向: {event.sentiment or '未分析'}"})

    # 关联文章
    assoc = db.query(EventArticle).filter(EventArticle.event_id == event_id).limit(20).all()
    if assoc:
        article_ids = [a.article_id for a in assoc]
        articles = db.query(Article).filter(Article.id.in_(article_ids)).all()
        article_lines = []
        for a in articles:
            src = SOURCE_NAME_MAP.get(a.source_id, a.source_id)
            article_lines.append(f"[{src}] {a.title}")
        sections.append({"heading": "关联文章", "body": "\n".join(article_lines)})

    pdf_bytes = _build_pdf(event.title or "事件报告", sections)
    fname = re.sub(r'[\\/:*?"<>|]', '_', (event.title or "event")[:40]) + ".pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_pdf_disposition(fname),
    )


@router.get("/ai/morning_brief/pdf")
def export_morning_brief_pdf():
    if not _morning_brief_cache.get("content"):
        return Response(content="暂无早报内容，请先生成早报", status_code=404)

    sections = [{"heading": "", "body": _morning_brief_cache["content"]}]
    date_str = _morning_brief_cache.get("date", datetime.now().strftime("%Y-%m-%d"))
    pdf_bytes = _build_pdf(f"舆情早报 {date_str}", sections)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_pdf_disposition(f"舆情早报_{date_str}.pdf"),
    )


# ---------------------------------------------------------------------------
# 舆情异动告警
# ---------------------------------------------------------------------------
_alert_cache: dict = {"alerts": [], "last_scan": "", "seen_ids": set()}
_ALERT_DEBUG = os.getenv("ALERT_DEBUG", "").strip() in ("1", "true", "yes")
_ALERT_THRESHOLD = 1 if _ALERT_DEBUG else int(os.getenv("ALERT_THRESHOLD", "3"))
_ALERT_WINDOW_HOURS = int(os.getenv("ALERT_WINDOW_HOURS", "2"))

_alert_log = logging.getLogger("alerts")


def _scan_alerts(db: Session) -> list:
    """扫描最近窗口内更新的高热事件, 返回新异动列表。"""
    if _ALERT_DEBUG:
        # 调试模式：不限时间窗口，取所有事件中 article_count 最多的
        hot_events = (
            db.query(Event)
            .filter(Event.article_count >= _ALERT_THRESHOLD)
            .order_by(Event.article_count.desc())
            .limit(10)
            .all()
        )
        _alert_log.info(f"[告警调试] 扫描到 {len(hot_events)} 个事件 (阈值={_ALERT_THRESHOLD})")
    else:
        cutoff = datetime.now() - timedelta(hours=_ALERT_WINDOW_HOURS)
        hot_events = (
            db.query(Event)
            .filter(Event.updated_at >= cutoff, Event.article_count >= _ALERT_THRESHOLD)
            .order_by(Event.article_count.desc())
            .limit(20)
            .all()
        )

    new_alerts = []
    for ev in hot_events:
        if not _ALERT_DEBUG and ev.id in _alert_cache["seen_ids"]:
            continue
        _alert_cache["seen_ids"].add(ev.id)
        level = "critical" if ev.article_count >= _ALERT_THRESHOLD * 3 else (
            "warning" if ev.article_count >= _ALERT_THRESHOLD * 2 else "info"
        )
        new_alerts.append({
            "id": ev.id,
            "title": ev.title,
            "article_count": ev.article_count,
            "platform_count": ev.platform_count,
            "sentiment": ev.sentiment or "neutral",
            "level": level,
            "time": ev.updated_at.strftime("%Y-%m-%d %H:%M") if ev.updated_at else "",
        })

    if _ALERT_DEBUG:
        # 调试模式：每次覆盖，始终展示
        _alert_cache["alerts"] = new_alerts[:10]
    elif new_alerts:
        _alert_cache["alerts"] = new_alerts + _alert_cache["alerts"]
        _alert_cache["alerts"] = _alert_cache["alerts"][:50]
    _alert_cache["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return new_alerts


@router.get("/ai/alerts")
def get_alerts(db: Session = Depends(get_db)):
    _scan_alerts(db)
    return {
        "alerts": _alert_cache["alerts"],
        "last_scan": _alert_cache["last_scan"],
    }


@router.post("/ai/alerts/dismiss")
def dismiss_alert(alert_id: int = Query(...)):
    _alert_cache["alerts"] = [a for a in _alert_cache["alerts"] if a["id"] != alert_id]
    return {"ok": True}


@router.post("/ai/alerts/clear")
def clear_alerts():
    _alert_cache["alerts"] = []
    return {"ok": True}


class ExportChatPdfRequest(BaseModel):
    title: str = "AI 对话报告"
    content: str
    images: Optional[List[str]] = None  # base64 dataURL 列表，用于嵌入前端截图（对比仪表盘等）


@router.post("/ai/export_pdf")
def export_chat_pdf(req: ExportChatPdfRequest):
    if not req.content.strip() and not req.images:
        return Response(content="内容为空", status_code=400)

    sections = [{"heading": "", "body": req.content}] if req.content.strip() else []
    pdf_bytes = _build_pdf(req.title, sections, images=req.images)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    fname = re.sub(r'[\\/:*?"<>|]', '_', req.title[:30]) + f"_{ts}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=_pdf_disposition(fname),
    )

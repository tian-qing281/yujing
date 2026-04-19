import json
import logging
import math
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from sqlalchemy.orm import Session

from app.database import Article, Event, EventArticle, utcnow
from app.keyword_extraction import extract_tags, pseg
from app.services.search_engine import meili

logger = logging.getLogger(__name__)

# v0.10: Sentence-BERT 聚类升级开关（默认关闭，保持旧行为）。
# 可通过 .env 的 SEMANTIC_CLUSTER=1 启用，或调用 admin 接口时传 semantic=1 临时启用。
SEMANTIC_CLUSTER_ENABLED = os.getenv("SEMANTIC_CLUSTER", "0").strip() in ("1", "true", "True", "yes")


# IDF 加权共享 token 相似度：替代纯 Jaccard 抑制"美国/伊朗"等高频 token 的虚高权重
# rebuild_events 在聚类前预计算全语料 IDF 并赋值给 _CURRENT_IDF_MAP；未预计算时退化为纯 Jaccard。
_CURRENT_IDF_MAP: Dict[str, float] = {}


def _compute_idf_map(tokens_per_doc: List[List[str]]) -> Dict[str, float]:
    """计算每个 token 的逆文档频率：idf(t) = log((N+1)/(df(t)+1)) + 1。

    平滑项避免除零；+1 让单文档出现的词也有正值。
    """
    N = len(tokens_per_doc)
    if N == 0:
        return {}
    df: Counter = Counter()
    for tokens in tokens_per_doc:
        for t in set(tokens):
            df[t] += 1
    return {t: math.log((N + 1) / (c + 1)) + 1.0 for t, c in df.items()}


def _idf_weighted_jaccard(set_a: set, set_b: set) -> float:
    """IDF 加权 Jaccard：共享 token 的 IDF 权重和 / 并集 IDF 权重和。

    当 `_CURRENT_IDF_MAP` 为空时退化为普通 Jaccard，保证向后兼容。
    """
    if not set_a and not set_b:
        return 0.0
    shared = set_a & set_b
    union = set_a | set_b
    if not union:
        return 0.0
    if not _CURRENT_IDF_MAP:
        return len(shared) / len(union)
    w_shared = sum(_CURRENT_IDF_MAP.get(t, 1.0) for t in shared)
    w_union = sum(_CURRENT_IDF_MAP.get(t, 1.0) for t in union)
    if w_union <= 0:
        return 0.0
    return w_shared / w_union


STOPWORDS = {
    "什么",
    "怎么",
    "为什么",
    "一个",
    "这个",
    "那个",
    "今天",
    "刚刚",
    "最新",
    "回应",
    "热搜",
    "话题",
    "视频",
    "直播",
    "曝光",
    "表示",
    "宣布",
    "官方",
    "网友",
    "相关",
    "消息",
    "事件",
    "平台",
    "再次",
    "已经",
    "开始",
    "进入",
}

LOW_VALUE_TOKENS = {
    "综合",
    "小时",
    "分钟",
    "今日",
    "今天",
    "刚刚",
    "最新",
    "回应",
    "表示",
    "事件",
    "平台",
    "热搜",
    "话题",
    "视频",
    "直播",
    "消息",
    "相关",
    "再次",
    "已经",
    "开始",
    "进入",
}

ENTITY_ALIASES = {
    "伊朗": ["伊朗", "伊方", "伊媒", "伊军", "伊官员", "波斯"],
    "美国": ["美国", "美方", "美媒", "美军", "白宫", "拜登"],
    "以色列": ["以色列", "以方", "以军", "以媒", "内塔尼亚胡"],
    "俄罗斯": ["俄罗斯", "俄方", "俄军", "普京", "莫斯科"],
    "乌克兰": ["乌克兰", "乌方", "乌军", "泽连斯基", "基辅"],
    "苹果": ["苹果", "apple", "iphone", "ipad", "库克"],
    "小米": ["小米", "雷军", "su7", "小米汽车"],
}

DISPLAY_KEYWORD_BLOCKLIST = LOW_VALUE_TOKENS | {
    "一名",
    "一夜",
    "因为",
    "目前",
    "当地时间",
    "哪些信息值得关注",
    "当前局势如何",
    "父亲拿棍",
}

DISPLAY_KEYWORD_FRAGMENTS = {
    "如何",
    "为什么",
    "值得关注",
    "当前局势",
    "继续",
    "开始",
    "引发",
    "发动",
    "准备",
    "叠加",
    "出手",
    "不要",
    "拿棍",
}

EVENT_STABLE_MIN_ARTICLES = 2
EVENT_STABLE_MIN_PLATFORMS = 1
EVENT_EMERGING_MIN_ARTICLES = 1
# 聚合相似度阈值（2026-04-17 收紧）
# 原 0.14 偏低，容易把共享"美国/中国"等高频 token 的无关事件合到一起
EVENT_CLUSTER_SCORE_THRESHOLD = 0.18
EVENT_CLUSTER_ENTITY_THRESHOLD = 0.14
EVENT_CLUSTER_SHARED_TOKEN_THRESHOLD = 0.14
EVENT_CLUSTER_MERGE_THRESHOLD = 0.26


def _safe_json_loads(value: Optional[str]) -> Dict:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _normalize_title(title: str) -> str:
    if not title:
        return ""
    text = re.sub(r"#.*?#", " ", str(title))
    text = re.sub(r"[【】\[\]（）()“”\"'：:、,，。.？?！!…\-—_/|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _canonicalize_title(title: str) -> str:
    text = _normalize_title(title)
    if not text:
        return ""
    patterns = [
        r"进入第\s*\d+\s*天",
        r"第\s*\d+\s*天",
        r"第\s*\d+\s*小时",
        r"\d+\s*小时前",
        r"\d+\s*分钟前",
        r"\d+\s*天前",
        r"\d+\s*人",
        r"\d+\s*名",
        r"\d+\s*条",
        r"\d+",
    ]
    for pattern in patterns:
        text = re.sub(pattern, " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_entities(text: str, tokens: List[str]) -> set:
    haystack = f"{text or ''} {' '.join(tokens or [])}".lower()
    found = set()
    for entity, aliases in ENTITY_ALIASES.items():
        if any(alias.lower() in haystack for alias in aliases):
            found.add(entity)
    return found


def _extract_query_terms(query: str) -> List[str]:
    normalized = _normalize_title(query)
    if not normalized:
        return []
    terms = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", normalized)
    results = []
    seen = set()
    if len(normalized) >= 2:
        seen.add(normalized)
        results.append(normalized)
    for term in terms:
        if term in STOPWORDS or term in seen:
            continue
        seen.add(term)
        results.append(term)
    return results[:12]


def _is_strict_phrase_query(query: str) -> bool:
    normalized = _normalize_title(query)
    if not normalized or " " in normalized:
        return False
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", normalized):
        return True
    if re.fullmatch(r"[a-z0-9_-]{2,24}", normalized):
        return True
    return False


def _extract_tokens(article: Article) -> List[str]:
    title = _normalize_title(article.title)
    extra = _safe_json_loads(article.extra_info)
    seed = " ".join(
        str(extra.get(key, ""))
        for key in ("excerpt", "desc", "author")
        if extra.get(key)
    )
    combined = f"{article.title or ''} {seed}".strip()
    normalized_combined = _normalize_title(combined)
    tokens = []
    seen = set()

    def push(token: str):
        token = _normalize_title(token)
        if not token or token in seen or len(token) < 2:
            return
        if token in STOPWORDS or token in LOW_VALUE_TOKENS:
            return
        if re.fullmatch(r"\d+", token):
            return
        if re.fullmatch(r"\d+(小时|分钟|天|年|月|周|万|亿)", token):
            return
        if re.fullmatch(r"[a-z]{1,2}", token):
            return
        if len(token) > 18:
            return
        seen.add(token)
        tokens.append(token)

    if 4 <= len(title) <= 18:
        push(title)

    for tag in extract_tags(combined, topK=12):
        push(tag)

    raw_tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", normalized_combined)
    for token in raw_tokens:
        push(token)

    cleaned = []
    for token in tokens:
        if any(token != other and token in other for other in tokens if len(other) > len(token)):
            continue
        cleaned.append(token)

    return cleaned[:6]


def _extract_display_keywords(articles: List[Article]) -> List[str]:
    counter = Counter()

    def push(token: str, weight: int = 1):
        normalized = _normalize_title(token)
        normalized = re.sub(r"\s+", "", normalized)
        if not normalized:
            return
        if normalized in DISPLAY_KEYWORD_BLOCKLIST or normalized in STOPWORDS:
            return
        if len(normalized) < 2:
            return
        if re.fullmatch(r"[\u4e00-\u9fff]+", normalized) and len(normalized) > 6:
            return
        if re.fullmatch(r"[a-z0-9%]+", normalized) and len(normalized) > 12:
            return
        if re.fullmatch(r"\d+", normalized):
            return
        if re.fullmatch(r"\d+%", normalized):
            return
        if re.fullmatch(r"[\u4e00-\u9fff]{1}", normalized):
            return
        if re.search(r"\d", normalized) and re.search(r"[\u4e00-\u9fff]", normalized):
            return
        if re.search(r"(如何|什么|为什么|是不是|能否|怎样|是否|有何|真的|的吗)", normalized):
            return
        if "当前局势" in normalized or "值得关注" in normalized:
            return
        if any(fragment in normalized for fragment in DISPLAY_KEYWORD_FRAGMENTS):
            return
        counter[normalized] += weight

    def push_entities(text: str, weight: int = 4):
        lowered = (text or "").lower()
        for entity, aliases in ENTITY_ALIASES.items():
            if any(alias.lower() in lowered for alias in aliases):
                push(entity, weight)

    def push_quoted_phrases(text: str):
        for phrase in re.findall(r"[“\"【《](.*?)[”\"】》]", text or ""):
            push(phrase, 5)

    for article in articles:
        title = article.title or ""
        extra = _safe_json_loads(article.extra_info)
        seed = " ".join(str(extra.get(key, "")) for key in ("excerpt", "desc") if extra.get(key))
        push_entities(title)
        push_quoted_phrases(title)
        for tag in extract_tags(title, topK=6):
            push(tag, 5)
        for tag in extract_tags(seed, topK=4):
            push(tag, 2)

        for word, flag in pseg.cut(title):
            token = (word or "").strip()
            if not token:
                continue
            normalized = _normalize_title(token)
            if not normalized:
                continue
            if flag.startswith(("n", "nr", "ns", "nt", "nz")) or flag in {"eng", "vn"}:
                push(token, 4)

        for word, flag in pseg.cut(seed):
            token = (word or "").strip()
            if not token:
                continue
            if flag.startswith(("n", "nr", "ns", "nt", "nz")) or flag in {"eng", "vn"}:
                push(token, 2)

    cleaned = []
    seen = set()
    for token, _ in counter.most_common(16):
        if token in seen:
            continue
        if any(token != other and token in other for other, _ in counter.most_common(12) if len(other) > len(token)):
            continue
        seen.add(token)
        cleaned.append(token)
        if len(cleaned) >= 3:
            break
    return cleaned


def classify_event_confidence(article_count: int, platform_count: int) -> tuple[str, str]:
    article_count = article_count or 0
    platform_count = platform_count or 0

    if article_count >= EVENT_STABLE_MIN_ARTICLES or (platform_count >= EVENT_STABLE_MIN_PLATFORMS and article_count >= 2):
        return "stable", "确成态势"
    if article_count >= EVENT_EMERGING_MIN_ARTICLES:
        return "emerging", "态势演化"
    return "signal", "情报线索"


def is_stable_event(article_count: int, platform_count: int) -> bool:
    confidence, _ = classify_event_confidence(article_count, platform_count)
    return confidence == "stable"


def _extract_heat(article: Article) -> float:
    extra = _safe_json_loads(article.extra_info)
    value = extra.get("hot_value") or extra.get("hot_score") or extra.get("view") or extra.get("hot_metric") or 0
    if isinstance(value, str):
        try:
            value = float(re.sub(r"[^\d.]", "", value) or 0)
        except Exception:
            value = 0
    return float(value or 0)


def _article_time(article: Article) -> datetime:
    return article.pub_date or article.fetch_time or utcnow()


def _score_article(article: Article) -> float:
    rank_bonus = max(0, 120 - (article.rank or 99))
    heat = _extract_heat(article)
    heat_bonus = min(heat / 10000, 160)
    source_bonus = 20 if article.source_id in {"weibo_hot_search", "zhihu_hot_question"} else 0
    return rank_bonus + heat_bonus + source_bonus


def _expand_with_synonyms(tokens: List[str]) -> set:
    expanded = set(tokens)
    for token in tokens:
        lowered = token.lower()
        for entity, aliases in ENTITY_ALIASES.items():
            if any(alias.lower() == lowered for alias in aliases) or lowered == entity.lower():
                expanded.add(entity.lower())
                break
    return expanded


def _cluster_similarity(tokens_a: List[str], tokens_b: List[str], title_a: str, title_b: str) -> float:
    if not tokens_a and not tokens_b and not title_a and not title_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    shared = set_a & set_b

    exp_a = _expand_with_synonyms(tokens_a)
    exp_b = _expand_with_synonyms(tokens_b)
    syn_shared = exp_a & exp_b

    # IDF 加权 Jaccard：比纯 Jaccard 更严谨，降低"美国/伊朗"等高频 token 的贡献
    jaccard_raw = _idf_weighted_jaccard(set_a, set_b) if (set_a or set_b) else 0.0
    jaccard_syn = _idf_weighted_jaccard(exp_a, exp_b) if (exp_a or exp_b) else 0.0
    jaccard = max(jaccard_raw, jaccard_syn)

    bonus = 0.0
    canonical_a = _canonicalize_title(title_a)
    canonical_b = _canonicalize_title(title_b)

    if canonical_a and canonical_b and canonical_a == canonical_b:
        bonus += 0.42
    elif canonical_a and canonical_b and (canonical_a in canonical_b or canonical_b in canonical_a):
        bonus += 0.28
    elif title_a and title_b and (title_a in title_b or title_b in title_a):
        bonus += 0.25

    meaningful_shared = [token for token in (shared | (syn_shared - set_a - set_b)) if len(token) >= 3 and token not in LOW_VALUE_TOKENS]
    if len(shared) >= 3:
        bonus += 0.15
    if len(meaningful_shared) >= 2:
        bonus += 0.12
    if len(syn_shared) > len(shared):
        bonus += 0.08

    entities_a = _extract_entities(title_a, tokens_a)
    entities_b = _extract_entities(title_b, tokens_b)
    if entities_a and entities_b:
        if entities_a & entities_b:
            bonus += 0.1
        else:
            bonus -= 0.08

    score = jaccard + bonus
    if not shared and not syn_shared and score < 0.28:
        return 0.0
    return score


def _should_attach_to_cluster(tokens: List[str], title: str, cluster: Dict, score: float) -> bool:
    cluster_tokens = cluster["tokens"]
    cluster_title = cluster["title_norm"]
    shared = set(tokens) & set(cluster_tokens)
    canonical_a = _canonicalize_title(title)
    canonical_b = _canonicalize_title(cluster_title)

    # 硬约束 0：canonical title 完全相同 → 必定合并（同一事件不同表述）
    if canonical_a and canonical_b and canonical_a == canonical_b:
        return True

    entities_a = _extract_entities(title, tokens)
    entities_b = _extract_entities(cluster_title, cluster_tokens)

    # 硬约束 1：两边都识别到实体但无交集 → 直接拒绝（防"美伊谈判"与"美以冲突"被共享美国 token 聚到一起）
    if entities_a and entities_b and not (entities_a & entities_b):
        return False

    if score >= EVENT_CLUSTER_SCORE_THRESHOLD:
        return True

    if entities_a and entities_b and (entities_a & entities_b) and len(shared) >= 1 and score >= EVENT_CLUSTER_ENTITY_THRESHOLD:
        return True

    if len(shared) >= 2 and score >= EVENT_CLUSTER_SHARED_TOKEN_THRESHOLD:
        return True

    meaningful = [t for t in shared if len(t) >= 4 and t not in LOW_VALUE_TOKENS]
    if meaningful and score >= EVENT_CLUSTER_SHARED_TOKEN_THRESHOLD:
        return True

    return False


def _build_event_summary(articles: List[Article], tokens: List[str]) -> str:
    top_articles = sorted(articles, key=_score_article, reverse=True)[:3]
    titles = []
    source_names = []
    seen_titles = set()
    seen_sources = set()
    for article in top_articles:
        title = (article.title or "").strip()
        canonical = _canonicalize_title(title)
        if title and canonical not in seen_titles:
            seen_titles.add(canonical)
            titles.append(title)

        source_id = (article.source_id or "").strip()
        if source_id and source_id not in seen_sources:
            seen_sources.add(source_id)
            source_names.append(source_id)

    focus = "、".join(tokens[:2]) if tokens else "关联事件"
    source_text = " / ".join(source_names[:3]) if source_names else "多源"
    sample_titles = "；".join(titles[:2]) if titles else "查看代表情报卡获取详情"
    return f"{focus} · {len(articles)}条情报 · {source_text}。{sample_titles}"


def _pick_sentiment(articles: List[Article]) -> str:
    counter = Counter(article.ai_sentiment for article in articles if article.ai_sentiment)
    if not counter:
        return "neutral"
    return counter.most_common(1)[0][0]


def _build_cluster_payload(articles: List[Article]) -> Dict:
    keywords = _extract_display_keywords(articles)
    representative = max(articles, key=_score_article)
    latest_time = max(_article_time(article) for article in articles)
    primary_source = Counter(article.source_id for article in articles).most_common(1)[0][0]
    # 事件热度评分：综合文章热度 + 跨平台覆盖 + 数量
    article_scores = sorted([_score_article(a) for a in articles], reverse=True)
    # 取 top-3 文章热度均值（避免长尾噪声拉高）
    top_scores = article_scores[:3]
    avg_top_heat = sum(top_scores) / len(top_scores) if top_scores else 0
    platform_count = len({article.source_id for article in articles})
    # heat = 文章热度(0-300) + 跨平台奖励(每多一个平台+30, 上限150) + 数量奖励(log)
    heat_score = round(
        avg_top_heat
        + min((platform_count - 1) * 30, 150)
        + math.log2(max(len(articles), 1)) * 15,
        2,
    )

    return {
        "title": representative.title,
        "summary": _build_event_summary(articles, keywords),
        "keywords": keywords,
        "sentiment": _pick_sentiment(articles),
        "article_count": len(articles),
        "platform_count": platform_count,
        "heat_score": heat_score,
        "latest_article_time": latest_time,
        "representative_article_id": representative.id,
        "primary_source_id": primary_source,
    }


def _merge_cluster_into(target: Dict, incoming: Dict) -> Dict:
    existing_ids = {article.id for article in target["articles"]}
    for article in incoming["articles"]:
        if article.id not in existing_ids:
            target["articles"].append(article)
    target["tokens"] = list(dict.fromkeys(target["tokens"] + incoming["tokens"]))[:16]
    if _score_article(incoming["representative"]) > _score_article(target["representative"]):
        target["representative"] = incoming["representative"]
        target["title_norm"] = incoming["title_norm"]
    return target


def _merge_near_duplicate_clusters(clusters: List[Dict]) -> List[Dict]:
    merged: List[Dict] = []
    ordered = sorted(
        clusters,
        key=lambda cluster: (
            len(cluster["articles"]),
            _score_article(cluster["representative"]),
        ),
        reverse=True,
    )

    for cluster in ordered:
        best_cluster = None
        best_score = 0.0
        cluster_title = cluster["representative"].title or ""
        cluster_tokens = cluster["tokens"]
        cluster_entities = _extract_entities(cluster_title, cluster_tokens)
        cluster_canonical = _canonicalize_title(cluster_title)

        for existing in merged:
            existing_title = existing["representative"].title or ""
            existing_tokens = existing["tokens"]
            existing_entities = _extract_entities(existing_title, existing_tokens)
            existing_canonical = _canonicalize_title(existing_title)

            if cluster_entities and existing_entities and not (cluster_entities & existing_entities):
                continue

            score = _cluster_similarity(cluster_tokens, existing_tokens, cluster_title, existing_title)
            if cluster_canonical and existing_canonical and cluster_canonical == existing_canonical:
                score += 0.35

            if score > best_score:
                best_score = score
                best_cluster = existing

        if best_cluster and best_score >= EVENT_CLUSTER_MERGE_THRESHOLD:
            _merge_cluster_into(best_cluster, cluster)
        else:
            merged.append(cluster)

    return merged


def _cluster_articles(articles: List[Article]) -> List[Dict]:
    clusters: List[Dict] = []
    for article in articles:
        tokens = _extract_tokens(article)
        title = _normalize_title(article.title)
        best_cluster = None
        best_score = 0.0

        for cluster in clusters:
            score = _cluster_similarity(tokens, cluster["tokens"], title, cluster["title_norm"])
            if score > best_score:
                best_score = score
                best_cluster = cluster

        if best_cluster and _should_attach_to_cluster(tokens, title, best_cluster, best_score):
            best_cluster["articles"].append(article)
            best_cluster["tokens"] = list(dict.fromkeys(best_cluster["tokens"] + tokens))[:12]
            if _score_article(article) > _score_article(best_cluster["representative"]):
                best_cluster["representative"] = article
                best_cluster["title_norm"] = title
        else:
            clusters.append(
                {
                    "articles": [article],
                    "tokens": tokens,
                    "title_norm": title,
                    "representative": article,
                }
            )

    return clusters


def rebuild_events(db: Session, lookback_hours: int = 720, use_semantic: Optional[bool] = None) -> int:
    """
    重建事件聚合。

    use_semantic:
      - None (默认)  ：按 `SEMANTIC_CLUSTER_ENABLED` 决定路径
      - True        ：强制走 Sentence-BERT 语义聚类（失败自动 fallback 回 Jaccard）
      - False       ：强制走旧 IDF 加权 Jaccard 聚类
    """
    cutoff = utcnow() - timedelta(hours=lookback_hours)
    articles = (
        db.query(Article)
        .filter(Article.fetch_time >= cutoff)
        .order_by(Article.fetch_time.desc(), Article.rank.asc())
        .all()
    )

    if not articles:
        db.query(EventArticle).delete()
        db.query(Event).delete()
        db.commit()
        meili.clear_index("events")
        return 0

    # 预计算全语料 IDF，用于本轮聚类的加权 Jaccard 相似度
    global _CURRENT_IDF_MAP
    try:
        tokens_per_doc = [_extract_tokens(a) for a in articles]
        _CURRENT_IDF_MAP = _compute_idf_map(tokens_per_doc)
    except Exception:
        _CURRENT_IDF_MAP = {}

    # 路径选择：显式参数 > 环境变量；任何异常自动回落到 Jaccard，保证不破坏线上功能。
    want_semantic = SEMANTIC_CLUSTER_ENABLED if use_semantic is None else bool(use_semantic)
    clusters = None
    semantic_meta = None
    if want_semantic:
        try:
            from app.services.semantic_index import cluster_articles_semantic_faiss
            clusters, semantic_meta = cluster_articles_semantic_faiss(db, articles)
            logger.info(
                "[rebuild_events] 使用 FAISS 语义聚类，初始簇=%s threshold=%s nlist=%s nprobe=%s",
                len(clusters),
                semantic_meta.get("threshold") if semantic_meta else None,
                semantic_meta.get("nlist") if semantic_meta else None,
                semantic_meta.get("nprobe") if semantic_meta else None,
            )
        except Exception:
            logger.exception("[rebuild_events] 语义聚类失败，回退到 Jaccard 路径")
            clusters = None
            semantic_meta = None

    if clusters is None:
        clusters = _cluster_articles(articles)
        # Jaccard 路径需要二次合并来弥补贪心单遍扫描的不足
        clusters = _merge_near_duplicate_clusters(clusters)
    # 语义路径已通过 Union-Find 全局聚类，不再做 Jaccard 二次合并，避免干扰语义精度

    event_count = 0

    try:
        db.query(EventArticle).delete()
        db.query(Event).delete()

        for cluster in clusters:
            payload = _build_cluster_payload(cluster["articles"])
            event = Event(
                title=payload["title"],
                summary=payload["summary"],
                keywords=json.dumps(payload["keywords"], ensure_ascii=False),
                sentiment=payload["sentiment"],
                article_count=payload["article_count"],
                platform_count=payload["platform_count"],
                heat_score=payload.get("heat_score", 0.0),
                latest_article_time=payload["latest_article_time"],
                representative_article_id=payload["representative_article_id"],
                primary_source_id=payload["primary_source_id"],
            )
            db.add(event)
            db.flush()

            representative_id = payload["representative_article_id"]
            cluster_tokens = _extract_tokens(cluster["representative"])
            cluster_title = _normalize_title(cluster["representative"].title)
            cluster_relation_scores = cluster.get("relation_scores") or {}
            cluster_importance_scores = cluster.get("importance_scores") or {}

            for article in cluster["articles"]:
                if cluster_relation_scores and article.id in cluster_relation_scores:
                    relation_score = float(cluster_relation_scores[article.id])
                else:
                    relation_score = _cluster_similarity(
                        _extract_tokens(article),
                        cluster_tokens,
                        _normalize_title(article.title),
                        cluster_title,
                    )
                db.add(
                    EventArticle(
                        event_id=event.id,
                        article_id=article.id,
                        relation_score=round(relation_score, 4),
                        importance_score=cluster_importance_scores.get(article.id, 0.0),
                        is_primary=article.id == representative_id,
                    )
                )

            event_count += 1

        db.commit()
    except Exception:
        db.rollback()
        raise

    meili.clear_index("events")
    meili.sync_events(db, db.query(Event).all())
    if semantic_meta:
        logger.info(
            "[rebuild_events] 语义聚类落库完成 event_count=%s threshold=%s pairs=%s",
            event_count,
            semantic_meta.get("threshold"),
            semantic_meta.get("candidate_pairs"),
        )
    # 清理本轮 IDF，避免被后续非聚类调用意外复用
    _CURRENT_IDF_MAP = {}
    return event_count


def ensure_events(db: Session, stale_minutes: int = 15) -> int:
    latest_event = db.query(Event).order_by(Event.updated_at.desc()).first()
    # 如果库里一个事件都没有，或者数据太旧，或者数据量明显不对，执行重构
    if latest_event and latest_event.updated_at and latest_event.updated_at >= utcnow() - timedelta(minutes=stale_minutes):
        return db.query(Event).count()
    return rebuild_events(db, lookback_hours=720)


def search_events(db: Session, query: str, limit: int = 80, time_range: int = None, source_id: str = None, return_total_only: bool = False) -> Union[List[Event], int]:
    from datetime import datetime, timedelta
    query = (query or "").strip()
    
    q_obj = db.query(Event)
    if time_range is not None:
        cutoff = datetime.now() - timedelta(hours=time_range)
        q_obj = q_obj.filter(Event.latest_article_time >= cutoff)
    if source_id:
        q_obj = q_obj.filter(Event.primary_source_id == source_id)

    if return_total_only:
        return q_obj.count()

    if not query:
        return (
            q_obj
            .order_by(Event.latest_article_time.desc(), Event.article_count.desc())
            .limit(limit)
            .all()
        )

    candidate_ids = []
    if meili.enabled:
        candidate_ids = meili.search_events(query, limit=max(limit * 3, 60), time_range=time_range, source_id=source_id or "")

    if candidate_ids:
        events_lookup = {event.id: event for event in q_obj.filter(Event.id.in_(candidate_ids)).all()}
        events = [events_lookup[event_id] for event_id in candidate_ids if event_id in events_lookup]
    else:
        events = q_obj.all()
    if not events:
        return []

    terms = _extract_query_terms(query)
    normalized_query = _normalize_title(query)
    strict_phrase_query = _is_strict_phrase_query(query)
    if not terms and not normalized_query:
        return (
            db.query(Event)
            .order_by(Event.latest_article_time.desc(), Event.article_count.desc())
            .limit(limit)
            .all()
        )

    candidate_event_ids = [e.id for e in events]
    ea_query = (
        db.query(EventArticle.event_id, Article.title, Article.ai_summary, Article.extra_info)
        .join(Article, Article.id == EventArticle.article_id)
    )
    if candidate_event_ids:
        ea_query = ea_query.filter(EventArticle.event_id.in_(candidate_event_ids))
    rows = ea_query.all()
    related_titles: Dict[int, List[str]] = {}
    related_blobs: Dict[int, List[str]] = {}
    for event_id, title, ai_summary, extra_info in rows:
        normalized_title = _normalize_title(title)
        related_titles.setdefault(event_id, []).append(normalized_title)

        extra = _safe_json_loads(extra_info)
        blob_parts = [
            normalized_title,
            _normalize_title(ai_summary or ""),
            _normalize_title(extra.get("excerpt", "")),
            _normalize_title(extra.get("desc", "")),
            _normalize_title(extra.get("author", "")),
            _normalize_title(extra.get("hot_metric", "")),
        ]
        blob = " ".join([part for part in blob_parts if part]).strip()
        if blob:
            related_blobs.setdefault(event_id, []).append(blob)

    def score_event(event: Event) -> float:
        score = 0.0
        title = _normalize_title(event.title or "")
        summary = _normalize_title(event.summary or "")
        keywords = []
        if event.keywords:
            try:
                keywords = [str(item).lower() for item in json.loads(event.keywords)]
            except Exception:
                keywords = []
        related = related_titles.get(event.id, [])[:10]
        related_blob = " ".join(related_blobs.get(event.id, [])[:12])

        direct_match = False
        strict_core_match = False

        if normalized_query:
            if normalized_query in title:
                score += 12.0
                direct_match = True
                strict_core_match = True
            if normalized_query in summary:
                score += 6.5
                direct_match = True
            if any(normalized_query in keyword for keyword in keywords):
                score += 8.0
                direct_match = True
                strict_core_match = True
            if any(normalized_query in row for row in related):
                score += 6.0
                direct_match = True
                strict_core_match = True
            if normalized_query in related_blob:
                score += 5.0
                direct_match = True

        if strict_phrase_query and normalized_query and not strict_core_match:
            return 0.0

        for term in terms:
            if term in title:
                score += 3.6
            if term in summary:
                score += 2.2
            if any(term in keyword for keyword in keywords):
                score += 3.1
            if any(term in row for row in related):
                score += 2.0
            if term in related_blob:
                score += 1.5

        if not strict_phrase_query and normalized_query and score > 0 and not direct_match:
            score *= 0.55

        confidence, _ = classify_event_confidence(event.article_count or 0, event.platform_count or 0)
        if confidence == "stable":
            score += 2.8
        elif confidence == "emerging":
            score += 0.8

        score += min((event.article_count or 0) * 0.08, 1.6)
        score += min((event.platform_count or 0) * 0.1, 0.6)
        return score

    ranked = [(event, score_event(event)) for event in events]
    ranked = [row for row in ranked if row[1] > 0]
    ranked.sort(
        key=lambda item: (
            item[1],
            item[0].latest_article_time or datetime.min,
            item[0].article_count or 0,
        ),
        reverse=True,
    )

    if not ranked:
        return []

    return [event for event, _ in ranked[:limit]]

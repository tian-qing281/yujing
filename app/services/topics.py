import json
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import jieba.analyse
from sqlalchemy.orm import Session

from app.database import Article, Event, EventArticle, Topic, TopicEvent
from app.services.events import (
    LOW_VALUE_TOKENS,
    STOPWORDS,
    _extract_query_terms,
    _is_strict_phrase_query,
    classify_event_confidence,
    is_stable_event,
)
from app.services.search_engine import meili


SUPER_ENTITIES = {
    "伊朗": ["伊朗", "伊方", "伊媒", "伊军", "德黑兰", "波斯"],
    "美国": ["美国", "美方", "美媒", "美军", "白宫", "特朗普", "拜登"],
    "以色列": ["以色列", "以方", "以媒", "以军", "内塔尼亚胡"],
    "巴勒斯坦": ["巴勒斯坦", "巴方", "哈马斯", "加沙"],
    "俄罗斯": ["俄罗斯", "俄方", "俄媒", "俄军", "普京", "莫斯科"],
    "乌克兰": ["乌克兰", "乌方", "乌军", "泽连斯基", "基辅"],
    "苹果": ["苹果", "apple", "iphone", "ipad", "ios", "库克"],
    "小米": ["小米", "雷军", "su7", "小米汽车"],
}

TOPIC_STOPWORDS = STOPWORDS | LOW_VALUE_TOKENS | {
    "局势",
    "相关",
    "动态",
    "话题",
    "事件",
    "讨论",
    "舆情",
    "平台",
    "当前",
    "汇聚",
    "热点",
    "集中",
    "近期",
    "代表",
    "包括",
    "新闻",
}

TOPIC_LOOKBACK_HOURS = 168
TOPIC_MIN_STABLE_EVENT_COUNT = 4
TOPIC_MIN_STABLE_PLATFORM_COUNT = 3
TOPIC_MIN_INCLUDED_EVENT_COUNT = 6
TOPIC_MIN_ARTICLE_COUNT = 12


def _safe_json_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except Exception:
        pass
    return []


def _normalize(value: Optional[str]) -> str:
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"#.*?#", " ", text)
    text = re.sub(r"[【】\[\]（）()“”\"'：:、,，。.？?！!…\-—_/|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _is_low_value_token(token: str) -> bool:
    if not token:
        return True
    if token in TOPIC_STOPWORDS:
        return True
    if len(token) < 2:
        return True
    if re.fullmatch(r"\d+", token):
        return True
    if re.fullmatch(r"\d+(小时|分钟|天|年|月|日|号)", token):
        return True
    return False


def _extract_event_tokens(event: Event) -> List[str]:
    payload = " ".join([event.title or "", " ".join(_safe_json_list(event.keywords))]).strip()
    normalized = _normalize(payload)
    seen = set()
    tokens: List[str] = []

    def push(token: str):
        candidate = _normalize(token).replace(" ", "")
        if _is_low_value_token(candidate):
            return
        if len(candidate) > 18 or candidate in seen:
            return
        seen.add(candidate)
        tokens.append(candidate)

    title_norm = _normalize(event.title).replace(" ", "")
    if 2 <= len(title_norm) <= 20:
        push(title_norm)

    for tag in jieba.analyse.extract_tags(payload, topK=10):
        push(tag)

    for token in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}", normalized):
        push(token)

    cleaned = []
    for token in tokens:
        if any(token != other and token in other for other in tokens if len(other) > len(token)):
            continue
        cleaned.append(token)
    return cleaned[:8]


def _event_score(event: Event) -> float:
    article_bonus = min((event.article_count or 0) * 0.45, 16)
    platform_bonus = min((event.platform_count or 0) * 1.2, 8)
    freshness_bonus = 0.0
    latest = event.latest_article_time
    if latest:
        age_hours = max((datetime.utcnow() - latest).total_seconds() / 3600, 0)
        freshness_bonus = max(0.0, 16 - min(age_hours, 16))
    return article_bonus + platform_bonus + freshness_bonus


def _get_super_entity(title: str, tokens: List[str]) -> Optional[str]:
    haystack = f"{title or ''} {' '.join(tokens or [])}".lower()
    scored: Dict[str, int] = {}
    for entity, aliases in SUPER_ENTITIES.items():
        score = 0
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower in haystack:
                score += 3 if alias_lower in (title or "").lower() else 1
        if score:
            scored[entity] = score
    if not scored:
        return None
    return max(scored, key=scored.get)


def _topic_similarity(tokens_a: List[str], tokens_b: List[str], title_a: str, title_b: str) -> float:
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    if not set_a and not set_b:
        return 0.0
    shared = set_a & set_b
    if not shared:
        return 0.0

    score = len(shared) / max(1, len(set_a | set_b))
    if title_a and title_b and (title_a in title_b or title_b in title_a):
        score += 0.24
    if len(shared) >= 2:
        score += 0.14
    if any(len(token) >= 3 for token in shared):
        score += 0.12
    return score


def _cluster_events(events: List[Event]) -> List[Dict]:
    entity_clusters: Dict[str, Dict] = {}

    for event in events:
        tokens = _extract_event_tokens(event)
        entity = _get_super_entity(event.title or "", tokens)
        if not entity:
            continue

        cluster = entity_clusters.setdefault(
            entity,
            {
                "super_entity": entity,
                "events": [],
                "tokens": [],
                "representative": event,
            },
        )
        cluster["events"].append(event)
        cluster["tokens"] = list(dict.fromkeys(cluster["tokens"] + tokens))[:20]
        if _event_score(event) > _event_score(cluster["representative"]):
            cluster["representative"] = event

    for cluster in entity_clusters.values():
        deduped = {event.id: event for event in cluster["events"]}
        cluster["events"] = sorted(
            deduped.values(),
            key=lambda item: (_event_score(item), item.latest_article_time or datetime.min),
            reverse=True,
        )

    return list(entity_clusters.values())


def _event_confidence(event: Event) -> str:
    confidence, _ = classify_event_confidence(event.article_count or 0, event.platform_count or 0)
    return confidence


def _topic_keywords(events: List[Event], entity: str) -> List[str]:
    counter = Counter()
    alias_set = {alias.lower() for alias in SUPER_ENTITIES.get(entity, [])}
    for event in events:
        for token in _extract_event_tokens(event):
            if token.lower() in alias_set:
                continue
            counter[token] += 1

    keywords = [entity]
    for token, _ in counter.most_common(6):
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= 5:
            break
    return keywords


def _collect_topic_stats(events: List[Event], event_articles: Dict[int, List[Article]]) -> Dict:
    article_ids = set()
    platforms = set()
    for event in events:
        if event.primary_source_id:
            platforms.add(event.primary_source_id)
        for article in event_articles.get(event.id, []):
            article_ids.add(article.id)
            if article.source_id:
                platforms.add(article.source_id)
    return {
        "event_count": len(events),
        "article_count": len(article_ids),
        "platform_count": len(platforms),
    }


def _build_topic_title(entity: str) -> str:
    return f"[{entity}] 宏观脉络"


def _build_topic_summary(entity: str, events: List[Event], stable_events: List[Event]) -> str:
    stable_titles = [event.title for event in stable_events[:2] if event.title]
    if stable_titles:
        sample = "；".join(stable_titles)
        return f"{entity}相关舆情已形成 {len(events)} 个关联事件，当前主轴：{sample}"
    titles = [event.title for event in events[:2] if event.title]
    sample = "；".join(titles) if titles else "查看事件链获取详情"
    return f"{entity}相关舆情已形成 {len(events)} 个关联事件，当前主轴：{sample}"


def _pick_topic_sentiment(events: List[Event]) -> str:
    counter = Counter((event.sentiment or "").strip() for event in events if (event.sentiment or "").strip())
    return counter.most_common(1)[0][0] if counter else "neutral"


def _build_topic_payload(cluster: Dict, included_events: List[Event], stable_events: List[Event], event_articles: Dict[int, List[Article]]) -> Dict:
    entity = cluster["super_entity"]
    stats = _collect_topic_stats(included_events, event_articles)
    representative = max(stable_events or included_events, key=_event_score)
    latest_time = max((event.latest_article_time or datetime.utcnow()) for event in included_events)
    keywords = _topic_keywords(included_events, entity)
    return {
        "title": _build_topic_title(entity),
        "summary": _build_topic_summary(entity, included_events, stable_events),
        "keywords": keywords,
        "sentiment": _pick_topic_sentiment(included_events),
        "event_count": stats["event_count"],
        "article_count": stats["article_count"],
        "platform_count": stats["platform_count"],
        "latest_event_time": latest_time,
        "representative_event_id": representative.id,
        "primary_source_id": representative.primary_source_id,
    }


def rebuild_topics(db: Session, lookback_hours: int = TOPIC_LOOKBACK_HOURS) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
    events = (
        db.query(Event)
        .filter(Event.latest_article_time >= cutoff)
        .order_by(Event.latest_article_time.desc(), Event.article_count.desc())
        .all()
    )

    if not events:
        db.query(TopicEvent).delete()
        db.query(Topic).delete()
        db.commit()
        meili.clear_index("topics")
        return 0

    event_articles: Dict[int, List[Article]] = {}
    rows = (
        db.query(EventArticle.event_id, Article)
        .join(Article, Article.id == EventArticle.article_id)
        .all()
    )
    for event_id, article in rows:
        event_articles.setdefault(event_id, []).append(article)

    candidate_events = [event for event in events if _event_confidence(event) in {"stable", "emerging"}]
    clusters = _cluster_events(candidate_events)
    topic_count = 0

    try:
        db.query(TopicEvent).delete()
        db.query(Topic).delete()

        for cluster in clusters:
            stable_events = [event for event in cluster["events"] if is_stable_event(event.article_count or 0, event.platform_count or 0)]
            if len(stable_events) < TOPIC_MIN_STABLE_EVENT_COUNT:
                continue

            stable_stats = _collect_topic_stats(stable_events, event_articles)
            if stable_stats["platform_count"] < TOPIC_MIN_STABLE_PLATFORM_COUNT:
                continue

            included_events = cluster["events"]
            payload = _build_topic_payload(cluster, included_events, stable_events, event_articles)
            if payload["event_count"] < TOPIC_MIN_INCLUDED_EVENT_COUNT:
                continue
            if payload["article_count"] < TOPIC_MIN_ARTICLE_COUNT:
                continue

            topic = Topic(
                title=payload["title"],
                summary=payload["summary"],
                keywords=json.dumps(payload["keywords"], ensure_ascii=False),
                sentiment=payload["sentiment"],
                event_count=payload["event_count"],
                article_count=payload["article_count"],
                platform_count=payload["platform_count"],
                latest_event_time=payload["latest_event_time"],
                representative_event_id=payload["representative_event_id"],
                primary_source_id=payload["primary_source_id"],
            )
            db.add(topic)
            db.flush()

            representative_id = payload["representative_event_id"]
            cluster_tokens = cluster["tokens"]
            cluster_title = _normalize(payload["title"])

            for event in included_events:
                relation_score = _topic_similarity(
                    _extract_event_tokens(event),
                    cluster_tokens,
                    _normalize(event.title),
                    cluster_title,
                )
                db.add(
                    TopicEvent(
                        topic_id=topic.id,
                        event_id=event.id,
                        relation_score=round(relation_score, 4),
                        is_primary=event.id == representative_id,
                    )
                )
            topic_count += 1

        db.commit()
    except Exception:
        db.rollback()
        raise

    meili.clear_index("topics")
    meili.sync_topics(db, db.query(Topic).all())
    return topic_count


def ensure_topics(db: Session, stale_minutes: int = 20) -> int:
    latest_topic = db.query(Topic).order_by(Topic.updated_at.desc()).first()
    if latest_topic and latest_topic.updated_at and latest_topic.updated_at >= datetime.utcnow() - timedelta(minutes=stale_minutes):
        return db.query(Topic).count()
    return rebuild_topics(db)


def search_topics(db: Session, query: str, limit: int = 24, time_range: int = None, source_id: str = None) -> List[Topic]:
    query = (query or "").strip()

    q_obj = db.query(Topic)
    if time_range is not None:
        cutoff = datetime.utcnow() - timedelta(hours=time_range)
        q_obj = q_obj.filter(Topic.latest_event_time >= cutoff)
    if source_id:
        q_obj = q_obj.filter(Topic.primary_source_id == source_id)

    if not query:
        return (
            q_obj.order_by(Topic.latest_event_time.desc(), Topic.event_count.desc()).limit(limit).all()
        )

    candidate_ids = []
    if meili.enabled:
        candidate_ids = meili.search_topics(query, limit=max(limit * 3, 48), time_range=time_range, source_id=source_id or "")

    if candidate_ids:
        topics_lookup = {topic.id: topic for topic in q_obj.filter(Topic.id.in_(candidate_ids)).all()}
        topics = [topics_lookup[topic_id] for topic_id in candidate_ids if topic_id in topics_lookup]
    else:
        topics = q_obj.all()

    if not topics:
        return []

    rows = (
        db.query(TopicEvent.topic_id, Event.title, Event.summary, Event.keywords)
        .join(Event, Event.id == TopicEvent.event_id)
        .all()
    )
    related_titles: Dict[int, List[str]] = {}
    related_blobs: Dict[int, List[str]] = {}
    for topic_id, title, summary, keywords in rows:
        normalized_title = _normalize(title)
        related_titles.setdefault(topic_id, []).append(normalized_title)
        keyword_list = _safe_json_list(keywords)
        blob = " ".join(
            [normalized_title, _normalize(summary or ""), _normalize(" ".join(keyword_list))]
        ).strip()
        if blob:
            related_blobs.setdefault(topic_id, []).append(blob)

    terms = _extract_query_terms(query)
    normalized_query = _normalize(query)
    strict_phrase_query = _is_strict_phrase_query(query)
    if not terms and not normalized_query:
        return []

    def score_topic(topic: Topic) -> float:
        score = 0.0
        title = _normalize(topic.title or "")
        summary = _normalize(topic.summary or "")
        keywords = [item.lower() for item in _safe_json_list(topic.keywords)]
        related = related_titles.get(topic.id, [])[:12]
        related_blob = " ".join(related_blobs.get(topic.id, [])[:16])

        direct_match = False
        strict_core_match = False

        if normalized_query:
            if normalized_query in title:
                score += 14.0
                direct_match = True
                strict_core_match = True
            if normalized_query in summary:
                score += 6.0
                direct_match = True
            if any(normalized_query in keyword for keyword in keywords):
                score += 9.0
                direct_match = True
                strict_core_match = True
            if any(normalized_query in row for row in related):
                score += 8.0
                direct_match = True
                strict_core_match = True
            if normalized_query in related_blob:
                score += 5.0
                direct_match = True

        if strict_phrase_query and normalized_query and not strict_core_match:
            return 0.0

        for term in terms:
            if term in title:
                score += 4.0
            if term in summary:
                score += 2.4
            if any(term in keyword for keyword in keywords):
                score += 3.2
            if any(term in row for row in related):
                score += 2.8
            if term in related_blob:
                score += 1.6

        if not strict_phrase_query and normalized_query and score > 0 and not direct_match:
            score *= 0.55

        score += min((topic.event_count or 0) * 0.18, 3.2)
        score += min((topic.platform_count or 0) * 0.15, 1.4)
        return score

    ranked = [(topic, score_topic(topic)) for topic in topics]
    ranked = [row for row in ranked if row[1] > 0]
    ranked.sort(
        key=lambda item: (
            item[1],
            item[0].latest_event_time or datetime.min,
            item[0].event_count or 0,
        ),
        reverse=True,
    )
    return [topic for topic, _ in ranked[:limit]]

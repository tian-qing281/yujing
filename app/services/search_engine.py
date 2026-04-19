import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import meilisearch

from app.database import Article, Event, EventArticle, Topic, TopicEvent, utcnow

logger = logging.getLogger(__name__)


MEILI_SYNONYMS = {
    "伊朗": ["伊方", "伊媒", "伊军", "德黑兰", "波斯"],
    "美国": ["美方", "美媒", "美军", "白宫", "拜登"],
    "以色列": ["以方", "以军", "以媒", "内塔尼亚胡"],
    "巴勒斯坦": ["巴方", "哈马斯", "加沙"],
    "俄罗斯": ["俄方", "俄军", "普京", "莫斯科"],
    "乌克兰": ["乌方", "乌军", "泽连斯基", "基辅"],
    "苹果": ["apple", "iphone", "ipad", "ios", "库克"],
    "小米": ["雷军", "su7", "小米汽车"],
}

MEILI_STOPWORDS = [
    "什么",
    "怎么",
    "为什么",
    "这个",
    "那个",
    "最新",
    "回应",
    "视频",
    "消息",
    "相关",
    "事件",
    "平台",
]


def _extract_axis_terms(title: str, keywords: List[str]) -> List[str]:
    terms: List[str] = []
    seen = set()
    for candidate in [title, *(keywords or [])]:
        value = _canonicalize_title(candidate or "").replace(" ", "")
        if not value or value in seen or len(value) < 2 or len(value) > 8:
            continue
        seen.add(value)
        terms.append(value)
        if len(terms) >= 4:
            break
    return terms


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


def _clip(value: Optional[str], limit: int = 500) -> str:
    if not value:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ")[:limit]


def _canonicalize_title(title: str) -> str:
    text = str(title or "").lower()
    text = re.sub(r"#.*?#", " ", text)
    text = re.sub(r"[【】\[\]（）()“”\"'：:、,，。.？?！!…\-—_/|]+", " ", text)
    text = re.sub(r"进入第\s*\d+\s*天", " ", text)
    text = re.sub(r"第\s*\d+\s*天", " ", text)
    text = re.sub(r"第\s*\d+\s*小时", " ", text)
    text = re.sub(r"\d+\s*小时前", " ", text)
    text = re.sub(r"\d+\s*分钟前", " ", text)
    text = re.sub(r"\d+\s*天前", " ", text)
    text = re.sub(r"\d+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _to_ts(value: Optional[datetime]) -> int:
    if not value:
        return 0
    return int(value.timestamp())


def _build_filter(source_id: str = "", time_field: str = "", time_range: Optional[int] = None) -> Optional[str]:
    filters: List[str] = []
    if source_id:
        filters.append(f'{time_field and ""}primary_source_id = "{source_id}"')
    if time_range is not None and time_field:
        cutoff = int((utcnow() - timedelta(hours=time_range)).timestamp())
        filters.append(f"{time_field} >= {cutoff}")
    if not filters:
        return None
    return " AND ".join(filters)


class MeiliSearchClient:
    def __init__(self):
        host = os.getenv("MEILI_HOST", "http://localhost:7700")
        key = os.getenv("MEILI_MASTER_KEY", "yujing-master-secret-key-123456")
        self.client = meilisearch.Client(host, key)
        self.enabled = False
        self._check_health()

    def _check_health(self):
        try:
            if self.client.health().get("status") == "available":
                self.enabled = True
                self.ensure_indices()
                logger.info("已连接到 MeiliSearch。")
                return True
        except Exception:
            pass
        self.enabled = False
        return False

    def ensure_indices(self):
        if not self.enabled:
            return

        index_settings = {
                "articles": {
                    "primaryKey": "id",
                    "searchableAttributes": ["title", "excerpt", "content", "ai_summary", "keywords", "source_name", "source_id"],
                    "filterableAttributes": ["source_id", "fetch_ts"],
                    "sortableAttributes": ["fetch_ts", "rank"],
                },
                "events": {
                    "primaryKey": "id",
                    "searchableAttributes": [
                    "title",
                    "keywords",
                    "summary",
                    "entities",
                    "related_titles",
                        "related_text",
                        "canonical_title",
                    ],
                    "filterableAttributes": ["primary_source_id", "platform_count", "article_count", "latest_article_ts", "axis_terms", "canonical_title"],
                    "sortableAttributes": ["latest_article_ts", "article_count", "platform_count"],
                    "distinctAttribute": "canonical_title",
                },
                "topics": {
                    "primaryKey": "id",
                    "searchableAttributes": [
                    "title",
                    "keywords",
                    "summary",
                        "entities",
                        "related_titles",
                        "canonical_title",
                    ],
                    "filterableAttributes": ["primary_source_id", "platform_count", "event_count", "article_count", "latest_event_ts", "axis_terms", "canonical_title"],
                    "sortableAttributes": ["latest_event_ts", "event_count", "article_count", "platform_count"],
                    "distinctAttribute": "canonical_title",
                },
            }

        try:
            for uid, settings in index_settings.items():
                try:
                    index = self.client.get_index(uid)
                    if not getattr(index, "primary_key", None):
                        delete_task = self.client.delete_index(uid)
                        self._wait_for_task(delete_task)
                        create_task = self.client.create_index(uid, {"primaryKey": settings["primaryKey"]})
                        self._wait_for_task(create_task)
                except Exception:
                    create_task = self.client.create_index(uid, {"primaryKey": settings["primaryKey"]})
                    self._wait_for_task(create_task)
                task = self.client.index(uid).update_settings(
                    {
                        "searchableAttributes": settings["searchableAttributes"],
                        "filterableAttributes": settings["filterableAttributes"],
                        "sortableAttributes": settings["sortableAttributes"],
                        "rankingRules": ["words", "typo", "proximity", "attribute", "sort", "exactness"],
                        "synonyms": MEILI_SYNONYMS,
                        "stopWords": MEILI_STOPWORDS,
                        "distinctAttribute": settings.get("distinctAttribute"),
                        "pagination": {"maxTotalHits": 5000},
                    }
                )
                self._wait_for_task(task)
        except Exception as exc:
            logger.error(f"MeiliSearch 索引初始化失败: {exc}")

    def _wait_for_task(self, task):
        if not task:
            return
        try:
            task_uid = getattr(task, "task_uid", None)
            if task_uid is None and isinstance(task, dict):
                task_uid = task.get("taskUid") or task.get("uid")
            if task_uid is None:
                return
            self.client.wait_for_task(task_uid, timeout_in_ms=30000, interval_in_ms=200)
        except Exception as exc:
            logger.warning(f"Meili 任务等待跳过: {exc}")

    def clear_index(self, index_uid: str):
        if not self.enabled:
            return
        try:
            task = self.client.index(index_uid).delete_all_documents()
            self._wait_for_task(task)
        except Exception as exc:
            logger.error(f"Meili 清空索引 {index_uid} 失败: {exc}")

    def sync_articles(self, articles: List[Article]):
        if not self.enabled:
            self._check_health()
        if not self.enabled or not articles:
            return

        docs = []
        for article in articles:
            extra = {}
            try:
                extra = json.loads(article.extra_info or "{}")
            except Exception:
                extra = {}
            docs.append(
                {
                    "id": article.id,
                    "title": _clip(article.title, 160),
                    "excerpt": _clip(extra.get("excerpt") or extra.get("desc") or "", 280),
                    "content": _clip(article.content or "", 900),
                    "ai_summary": _clip(article.ai_summary or "", 320),
                    "keywords": _extract_axis_terms(article.title or "", []),
                    "source_id": article.source_id or "",
                    "source_name": _clip(extra.get("author") or "", 80),
                    "rank": article.rank or 99,
                    "fetch_ts": _to_ts(article.fetch_time or article.pub_date),
                }
            )
        try:
            task = self.client.index("articles").add_documents(docs)
            self._wait_for_task(task)
        except Exception as exc:
            logger.error(f"Meili 同步 articles 失败: {exc}")

    def sync_events(self, db, events: List[Event]):
        if not self.enabled:
            self._check_health()
        if not self.enabled or not events:
            return

        event_ids = [event.id for event in events]
        related_rows = (
            db.query(EventArticle.event_id, Article.title, Article.ai_summary)
            .join(Article, Article.id == EventArticle.article_id)
            .filter(EventArticle.event_id.in_(event_ids))
            .all()
        )
        related_titles: Dict[int, List[str]] = {}
        related_text: Dict[int, List[str]] = {}
        for event_id, title, ai_summary in related_rows:
            if title:
                related_titles.setdefault(event_id, []).append(title)
            if title or ai_summary:
                related_text.setdefault(event_id, []).append(" ".join([title or "", ai_summary or ""]).strip())

        docs = []
        for event in events:
            keywords = _safe_json_list(event.keywords)
            docs.append(
                {
                    "id": event.id,
                    "title": event.title or "",
                    "canonical_title": _canonicalize_title(event.title or ""),
                    "summary": event.summary or "",
                    "keywords": keywords,
                    "entities": [word for word in keywords if len(word) <= 4],
                    "related_titles": related_titles.get(event.id, [])[:10],
                    "related_text": related_text.get(event.id, [])[:10],
                    "axis_terms": _extract_axis_terms(event.title or "", keywords),
                    "article_count": event.article_count or 0,
                    "platform_count": event.platform_count or 0,
                    "primary_source_id": event.primary_source_id or "",
                    "latest_article_ts": _to_ts(event.latest_article_time),
                }
            )
        try:
            task = self.client.index("events").add_documents(docs)
            self._wait_for_task(task)
        except Exception as exc:
            logger.error(f"Meili 同步 events 失败: {exc}")

    def sync_topics(self, db, topics: List[Topic]):
        if not self.enabled:
            self._check_health()
        if not self.enabled or not topics:
            return

        topic_ids = [topic.id for topic in topics]
        related_rows = (
            db.query(TopicEvent.topic_id, Event.title, Event.summary)
            .join(Event, Event.id == TopicEvent.event_id)
            .filter(TopicEvent.topic_id.in_(topic_ids))
            .all()
        )
        related_titles: Dict[int, List[str]] = {}
        for topic_id, title, summary in related_rows:
            row = " ".join(part for part in [title or "", summary or ""] if part).strip()
            if row:
                related_titles.setdefault(topic_id, []).append(row)

        docs = []
        for topic in topics:
            keywords = _safe_json_list(topic.keywords)
            docs.append(
                {
                    "id": topic.id,
                    "title": topic.title or "",
                    "canonical_title": _canonicalize_title(topic.title or ""),
                    "summary": topic.summary or "",
                    "keywords": keywords,
                    "entities": [word for word in keywords if len(word) <= 4],
                    "related_titles": related_titles.get(topic.id, [])[:12],
                    "axis_terms": _extract_axis_terms(topic.title or "", keywords),
                    "event_count": topic.event_count or 0,
                    "article_count": topic.article_count or 0,
                    "platform_count": topic.platform_count or 0,
                    "primary_source_id": topic.primary_source_id or "",
                    "latest_event_ts": _to_ts(topic.latest_event_time),
                }
            )
        try:
            task = self.client.index("topics").add_documents(docs)
            self._wait_for_task(task)
        except Exception as exc:
            logger.error(f"Meili 同步 topics 失败: {exc}")

    def search(
        self,
        index_uid: str,
        query: str,
        limit: int = 40,
        offset: int = 0,
        filter_expr: Optional[str] = None,
        sort: Optional[List[str]] = None,
        facets: Optional[List[str]] = None,
    ) -> dict:
        if not self.enabled:
            self._check_health()
        if not self.enabled or not query.strip():
            return {"hits": [], "facetDistribution": {}}
        try:
            options = {
                "limit": limit,
                "offset": max(0, offset),
                "attributesToHighlight": ["title", "summary", "keywords", "related_titles"],
            }
            # 短查询(<=3字符)：禁用typo容错，严格匹配所有词
            stripped_query = query.strip()
            if len(stripped_query) <= 3:
                options["typoTolerance"] = {"enabled": False}
                options["matchingStrategy"] = "all"
            if filter_expr:
                options["filter"] = filter_expr
            if sort:
                options["sort"] = sort
            if facets:
                options["facets"] = facets
            results = self.client.index(index_uid).search(query, options)
            return results or {"hits": [], "facetDistribution": {}}
        except Exception as exc:
            logger.error(f"Meili 搜索 {index_uid} 失败: {exc}")
            return {"hits": [], "facetDistribution": {}}

    def search_events(self, query: str, limit: int = 80, time_range: Optional[int] = None, source_id: str = "") -> List[int]:
        filter_expr = _build_filter(source_id=source_id, time_field="latest_article_ts", time_range=time_range)
        hits = self.search("events", query, limit=limit, filter_expr=filter_expr).get("hits", [])
        return [int(hit["id"]) for hit in hits if "id" in hit]

    def search_events_result(self, query: str, limit: int = 80, offset: int = 0, time_range: Optional[int] = None, source_id: str = "") -> dict:
        filter_expr = _build_filter(source_id=source_id, time_field="latest_article_ts", time_range=time_range)
        return self.search(
            "events",
            query,
            limit=limit,
            offset=offset,
            filter_expr=filter_expr,
            facets=["axis_terms", "primary_source_id"],
        )

    def search_articles(self, query: str, limit: int = 40, time_range: Optional[int] = None, source_id: str = "") -> List[int]:
        return [
            int(hit["id"])
            for hit in self.search_articles_hits(query, limit=limit, time_range=time_range, source_id=source_id)
            if "id" in hit
        ]

    def search_articles_result(self, query: str, limit: int = 40, offset: int = 0, time_range: Optional[int] = None, source_id: str = "") -> dict:
        filter_expr = []
        if source_id:
            filter_expr.append(f'source_id = "{source_id}"')
        if time_range is not None:
            cutoff = int((utcnow() - timedelta(hours=time_range)).timestamp())
            filter_expr.append(f"fetch_ts >= {cutoff}")
        return self.search(
            "articles",
            query,
            limit=limit,
            offset=offset,
            filter_expr=" AND ".join(filter_expr) if filter_expr else None,
        )

    def search_articles_hits(self, query: str, limit: int = 40, offset: int = 0, time_range: Optional[int] = None, source_id: str = "") -> List[dict]:
        return self.search_articles_result(
            query,
            limit=limit,
            offset=offset,
            time_range=time_range,
            source_id=source_id,
        ).get("hits", [])

    def search_topics(self, query: str, limit: int = 24, time_range: Optional[int] = None, source_id: str = "") -> List[int]:
        filter_expr = _build_filter(source_id=source_id, time_field="latest_event_ts", time_range=time_range)
        hits = self.search("topics", query, limit=limit, filter_expr=filter_expr).get("hits", [])
        return [int(hit["id"]) for hit in hits if "id" in hit]

    def search_events_hits(self, query: str, limit: int = 18, time_range: Optional[int] = None, source_id: str = "") -> dict:
        return self.search_events_result(query, limit=limit, time_range=time_range, source_id=source_id)

    def search_topics_hits(self, query: str, limit: int = 8, time_range: Optional[int] = None, source_id: str = "") -> dict:
        filter_expr = _build_filter(source_id=source_id, time_field="latest_event_ts", time_range=time_range)
        return self.search(
            "topics",
            query,
            limit=limit,
            filter_expr=filter_expr,
            facets=["axis_terms", "primary_source_id"],
        )


meili = MeiliSearchClient()

"""
Agent 工具单测 · M2 第一批（4 个简单工具）。

策略：
- 每个 handler 都在内部 `from ... import SessionLocal`；测试时用
  `unittest.mock.patch` 替换成 fake session，完全离线
- 对每个工具至少覆盖：正路径 + 边界（空输入 / 非法参数）+ 输出 schema 必需字段

依赖：app.database / app.services.events 会被 import，需要保证模块可导入
（测试环境 Python 路径已包含项目根）。
"""

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from app.services.agent.tools import (
    tool_analyze_event_sentiment,
    tool_compare_events,
    tool_get_event_detail,
    tool_get_morning_brief,
    tool_list_hot_platforms,
    tool_search_articles,
    tool_search_events,
    tool_semantic_search_articles,
)


def _fake_event(
    *,
    id: int,
    title: str,
    article_count: int = 3,
    platform_count: int = 2,
    heat_score: float = 42.0,
    sentiment: str = "neutral",
    primary_source_id: str = "weibo_hot",
    keywords: str | None = '["伊朗","霍尔木兹"]',
    summary: str = "",
    latest: datetime | None = None,
):
    return SimpleNamespace(
        id=id,
        title=title,
        article_count=article_count,
        platform_count=platform_count,
        heat_score=heat_score,
        sentiment=sentiment,
        primary_source_id=primary_source_id,
        keywords=keywords,
        summary=summary,
        latest_article_time=latest or datetime(2026, 4, 19, 10, 0, tzinfo=timezone.utc),
    )


def _fake_article(
    *,
    id: int,
    title: str,
    source_id: str = "weibo_hot",
    url: str = "https://example.com/a",
    pub_date: datetime | None = None,
    ai_sentiment: str = "neutral",
    ai_summary: str = "",
):
    return SimpleNamespace(
        id=id,
        title=title,
        source_id=source_id,
        url=url,
        pub_date=pub_date or datetime(2026, 4, 19, 9, 0, tzinfo=timezone.utc),
        ai_sentiment=ai_sentiment,
        ai_summary=ai_summary,
    )


# =============================================================================
# search_events
# =============================================================================
class SearchEventsToolTestCase(unittest.TestCase):
    def test_spec_registered(self):
        self.assertEqual(tool_search_events.SPEC.name, "search_events")
        self.assertIn("q", tool_search_events.SPEC.input_schema["properties"])

    def test_handler_returns_marshaled_items(self):
        fake_events = [
            _fake_event(id=10, title="伊朗霍尔木兹", article_count=41, platform_count=6),
            _fake_event(id=11, title="美伊谈判", heat_score=20.0, keywords=None),
        ]
        fake_session = mock.MagicMock()
        with mock.patch(
            "app.database.SessionLocal",
            return_value=fake_session,
        ), mock.patch(
            "app.services.events.search_events",
            return_value=fake_events,
        ) as svc:
            out = tool_search_events._handler(q="伊朗", time_range_hours=168, limit=5)

        # 调 service 层时参数正确转换
        svc.assert_called_once()
        call_kwargs = svc.call_args.kwargs
        self.assertEqual(call_kwargs["query"], "伊朗")
        self.assertEqual(call_kwargs["limit"], 5)
        self.assertEqual(call_kwargs["time_range"], 168)
        self.assertIsNone(call_kwargs["source_id"])

        # 输出结构
        self.assertEqual(out["query"], "伊朗")
        self.assertEqual(out["total"], 2)
        self.assertEqual(out["events"][0]["_id"], 10)
        self.assertEqual(out["events"][0]["_type"], "event")
        self.assertEqual(out["events"][0]["article_count"], 41)
        self.assertEqual(out["events"][0]["keywords"], ["伊朗", "霍尔木兹"])
        # 关闭 session
        fake_session.close.assert_called_once()

    def test_handler_clamps_limit_and_time_range(self):
        fake_session = mock.MagicMock()
        with mock.patch(
            "app.database.SessionLocal",
            return_value=fake_session,
        ), mock.patch(
            "app.services.events.search_events",
            return_value=[],
        ) as svc:
            tool_search_events._handler(limit=999, time_range_hours=10000)
        kwargs = svc.call_args.kwargs
        self.assertLessEqual(kwargs["limit"], tool_search_events.MAX_LIMIT)
        self.assertLessEqual(kwargs["time_range"], 720)


# =============================================================================
# get_event_detail
# =============================================================================
class GetEventDetailToolTestCase(unittest.TestCase):
    def test_spec_registered_and_required(self):
        self.assertEqual(tool_get_event_detail.SPEC.name, "get_event_detail")
        self.assertIn("event_id", tool_get_event_detail.SPEC.input_schema["required"])

    def test_handler_returns_event_and_top_articles(self):
        fake_event = _fake_event(id=170, title="伊朗总统感谢中国", article_count=3, platform_count=3)
        link_rows = [
            SimpleNamespace(article_id=9970, importance_score=0.9, relation_score=1.0, is_primary=True),
            SimpleNamespace(article_id=10071, importance_score=0.7, relation_score=0.85, is_primary=False),
        ]
        fake_articles = [
            _fake_article(id=9970, title="伊朗总统感谢中国 - 微博"),
            _fake_article(id=10071, title="伊朗总统感谢中国 - 知乎", source_id="zhihu_hot"),
        ]

        fake_db = mock.MagicMock()
        q_event = mock.MagicMock()
        q_event.filter.return_value.first.return_value = fake_event
        q_ea = mock.MagicMock()
        q_ea.filter.return_value.order_by.return_value.limit.return_value.all.return_value = link_rows
        q_art = mock.MagicMock()
        q_art.filter.return_value.all.return_value = fake_articles

        def _query_side_effect(model):
            from app.database import Article, Event, EventArticle
            return {Event: q_event, EventArticle: q_ea, Article: q_art}[model]

        fake_db.query.side_effect = _query_side_effect

        with mock.patch(
            "app.database.SessionLocal",
            return_value=fake_db,
        ):
            out = tool_get_event_detail._handler(event_id=170)

        self.assertTrue(out["found"])
        self.assertEqual(out["_id"], 170)
        self.assertEqual(out["_title"], "伊朗总统感谢中国")
        self.assertEqual(out["article_count"], 3)
        self.assertEqual(len(out["top_articles"]), 2)
        # 顺序按 link_rows（is_primary desc -> relation_score desc）
        self.assertEqual(out["top_articles"][0]["_id"], 9970)
        self.assertEqual(out["top_articles"][1]["_id"], 10071)

    def test_handler_returns_not_found_for_missing(self):
        fake_db = mock.MagicMock()
        fake_db.query.return_value.filter.return_value.first.return_value = None
        with mock.patch(
            "app.database.SessionLocal",
            return_value=fake_db,
        ):
            out = tool_get_event_detail._handler(event_id=999999)
        self.assertFalse(out["found"])
        self.assertEqual(out["_id"], 999999)
        self.assertIn("不存在", out["message"])

    def test_handler_raises_on_invalid_event_id(self):
        with self.assertRaises(ValueError):
            tool_get_event_detail._handler(event_id=0)
        with self.assertRaises(ValueError):
            tool_get_event_detail._handler(event_id="not-an-int")


# =============================================================================
# get_morning_brief
# =============================================================================
class GetMorningBriefToolTestCase(unittest.TestCase):
    def test_spec_registered(self):
        self.assertEqual(tool_get_morning_brief.SPEC.name, "get_morning_brief")

    def test_cache_hit_today_returns_content(self):
        today = datetime.now().strftime("%Y-%m-%d")
        fake_cache = {"date": today, "content": "今日要闻：……" * 3, "generating": False}
        with mock.patch.dict(
            "app.api.routes._morning_brief_cache", fake_cache, clear=True
        ):
            out = tool_get_morning_brief._handler()
        self.assertTrue(out["has_content"])
        self.assertEqual(out["date"], today)
        self.assertIn("今日要闻", out["content"])
        self.assertFalse(out["truncated"])

    def test_cache_miss_returns_hint(self):
        with mock.patch.dict(
            "app.api.routes._morning_brief_cache",
            {"date": "2020-01-01", "content": "", "generating": False},
            clear=True,
        ):
            out = tool_get_morning_brief._handler()
        self.assertFalse(out["has_content"])
        self.assertIn("hint", out)
        self.assertEqual(out["cached_date"], "2020-01-01")

    def test_long_content_is_truncated(self):
        today = datetime.now().strftime("%Y-%m-%d")
        long_content = "A" * (tool_get_morning_brief.MAX_CONTENT_CHARS_IN_OBSERVATION + 500)
        with mock.patch.dict(
            "app.api.routes._morning_brief_cache",
            {"date": today, "content": long_content, "generating": False},
            clear=True,
        ):
            out = tool_get_morning_brief._handler()
        self.assertTrue(out["truncated"])
        self.assertEqual(
            len(out["content"]),
            tool_get_morning_brief.MAX_CONTENT_CHARS_IN_OBSERVATION,
        )


# =============================================================================
# list_hot_platforms
# =============================================================================
class ListHotPlatformsToolTestCase(unittest.TestCase):
    def test_spec_registered(self):
        self.assertEqual(tool_list_hot_platforms.SPEC.name, "list_hot_platforms")

    def test_handler_groups_platforms_and_attaches_top_events(self):
        # mock 查询链条：一次 platform 分组查询 + 每平台一次 top_events 查询
        platform_rows = [
            ("weibo_hot", 150),
            ("zhihu_hot", 80),
            ("bilibili_hot", 30),
        ]
        # 每个平台分别返回不同数量的 event
        events_by_platform = {
            "weibo_hot": [
                _fake_event(id=1, title="A", heat_score=99.0),
                _fake_event(id=2, title="B", heat_score=80.0),
                _fake_event(id=3, title="C", heat_score=70.0),
            ],
            "zhihu_hot": [_fake_event(id=10, title="Z1", heat_score=55.0)],
            "bilibili_hot": [],
        }

        fake_db = mock.MagicMock()

        # 模拟 query(...) 返回的链式 mock：需要区分两种 query 模式
        platform_query_mock = mock.MagicMock()
        platform_query_mock.filter.return_value.filter.return_value.group_by.return_value.order_by.return_value.all.return_value = platform_rows

        def _query_side_effect(*args):
            from app.database import Article, Event
            # args 是 (Article.source_id, func.count(...)) 或 (Event,)
            # 用传入个数区分
            if len(args) == 1 and args[0] is Event:
                evq = mock.MagicMock()
                # filter().filter().order_by().limit().all()
                # 我们让每次调用根据当前 filter 值决定——简化：逐个 pop
                return evq
            return platform_query_mock

        fake_db.query.side_effect = _query_side_effect

        # 由于 Event 查询会被调多次，让每次返回对应平台的事件列表
        call_counter = {"i": 0}

        def _event_filter_chain(*a, **k):
            # 每次 query(Event) 返回一个新 mock，其 filter().filter().order_by().limit().all()
            # 按顺序返回 events_by_platform 的值
            evq = mock.MagicMock()
            idx = call_counter["i"]
            sid = platform_rows[idx][0] if idx < len(platform_rows) else ""
            evq.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = events_by_platform.get(sid, [])
            call_counter["i"] += 1
            return evq

        def _query_side_effect_v2(*args):
            from app.database import Event
            if len(args) == 1 and args[0] is Event:
                return _event_filter_chain()
            return platform_query_mock

        fake_db.query.side_effect = _query_side_effect_v2

        with mock.patch(
            "app.database.SessionLocal",
            return_value=fake_db,
        ), mock.patch(
            "app.database.utcnow",
            return_value=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        ):
            out = tool_list_hot_platforms._handler(time_range_hours=24)

        self.assertEqual(out["_type"], "platforms_snapshot")
        self.assertEqual(out["platform_count"], 3)
        self.assertEqual(out["total_articles"], 260)
        self.assertEqual(out["platforms"][0]["source_id"], "weibo_hot")
        self.assertEqual(out["platforms"][0]["article_count"], 150)
        self.assertEqual(len(out["platforms"][0]["top_events"]), 3)
        self.assertEqual(out["platforms"][0]["top_events"][0]["_id"], 1)

    def test_handler_clamps_params(self):
        fake_db = mock.MagicMock()
        fake_db.query.return_value.filter.return_value.filter.return_value.group_by.return_value.order_by.return_value.all.return_value = []
        with mock.patch(
            "app.database.SessionLocal",
            return_value=fake_db,
        ), mock.patch(
            "app.database.utcnow",
            return_value=datetime(2026, 4, 19, 12, 0, tzinfo=timezone.utc),
        ):
            out = tool_list_hot_platforms._handler(
                time_range_hours=99999,
                top_events_per_platform=99,
            )
        self.assertLessEqual(out["time_range_hours"], 720)


# =============================================================================
# search_articles
# =============================================================================
class SearchArticlesToolTestCase(unittest.TestCase):
    def test_spec_registered(self):
        self.assertEqual(tool_search_articles.SPEC.name, "search_articles")
        self.assertIn("q", tool_search_articles.SPEC.input_schema["required"])

    def test_empty_query_returns_hint(self):
        out = tool_search_articles._handler(q="")
        self.assertEqual(out["total"], 0)
        self.assertIn("hint", out)

    def test_meili_hit_path(self):
        fake_articles = [
            _fake_article(id=100, title="伊朗外长声明"),
            _fake_article(id=101, title="伊朗总统讲话", source_id="zhihu_hot"),
        ]
        fake_db = mock.MagicMock()
        fake_db.query.return_value.filter.return_value.all.return_value = fake_articles
        fake_meili = mock.MagicMock()
        fake_meili.enabled = True
        fake_meili.search_articles.return_value = [100, 101]

        with mock.patch(
            "app.database.SessionLocal",
            return_value=fake_db,
        ), mock.patch(
            "app.services.search_engine.meili",
            fake_meili,
        ):
            out = tool_search_articles._handler(q="伊朗", limit=5)

        self.assertTrue(out["meili_used"])
        self.assertEqual(out["total"], 2)
        self.assertEqual(out["articles"][0]["_id"], 100)
        fake_meili.search_articles.assert_called_once()

    def test_fallback_to_db_like_when_meili_empty(self):
        fake_articles = [_fake_article(id=200, title="fallback 命中")]
        fake_db = mock.MagicMock()
        # 两种分支都要 mock：Meili path 的 filter(in_) 和 fallback 的 filter(like)
        fake_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = fake_articles
        fake_meili = mock.MagicMock()
        fake_meili.enabled = True
        fake_meili.search_articles.return_value = []

        with mock.patch(
            "app.database.SessionLocal",
            return_value=fake_db,
        ), mock.patch(
            "app.services.search_engine.meili",
            fake_meili,
        ):
            out = tool_search_articles._handler(q="fallback")

        self.assertFalse(out["meili_used"])
        self.assertEqual(out["articles"][0]["_id"], 200)


# =============================================================================
# semantic_search_articles
# =============================================================================
class SemanticSearchArticlesToolTestCase(unittest.TestCase):
    def test_spec_registered(self):
        self.assertEqual(
            tool_semantic_search_articles.SPEC.name, "semantic_search_articles"
        )

    def test_index_not_ready_returns_hint(self):
        with mock.patch(
            "app.services.semantic_index.get_semantic_index_status",
            return_value={"ready": False},
        ):
            out = tool_semantic_search_articles._handler(q="伊朗")
        self.assertFalse(out["semantic_index_ready"])
        self.assertIn("search_articles", out["hint"])

    def test_no_seed_article_returns_hint(self):
        fake_db = mock.MagicMock()
        fake_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        fake_meili = mock.MagicMock()
        fake_meili.enabled = True
        fake_meili.search_articles.return_value = []

        with mock.patch(
            "app.services.semantic_index.get_semantic_index_status",
            return_value={"ready": True},
        ), mock.patch(
            "app.database.SessionLocal",
            return_value=fake_db,
        ), mock.patch(
            "app.services.search_engine.meili",
            fake_meili,
        ):
            out = tool_semantic_search_articles._handler(q="不存在的词")
        self.assertEqual(out["neighbors"], [])
        self.assertIn("hint", out)

    def test_returns_neighbors_when_seed_found(self):
        fake_neighbors_payload = {
            "source": {
                "article_id": 100,
                "title": "伊朗外长声明",
                "source_id": "weibo_hot",
                "pub_date": "2026-04-19T10:00:00+00:00",
            },
            "threshold": 0.62,
            "neighbors": [
                {
                    "article_id": 101,
                    "title": "伊朗总统讲话",
                    "source_id": "zhihu_hot",
                    "pub_date": "2026-04-19T11:00:00+00:00",
                    "cosine": 0.88,
                    "composite": 0.75,
                    "above_threshold": True,
                },
                {
                    "article_id": 102,
                    "title": "中东局势",
                    "source_id": "toutiao_hot",
                    "pub_date": "2026-04-19T09:00:00+00:00",
                    "cosine": 0.71,
                    "composite": 0.60,
                    "above_threshold": False,
                },
            ],
        }
        fake_meili = mock.MagicMock()
        fake_meili.enabled = True
        fake_meili.search_articles.return_value = [100]

        with mock.patch(
            "app.services.semantic_index.get_semantic_index_status",
            return_value={"ready": True},
        ), mock.patch(
            "app.services.semantic_index.get_semantic_neighbors",
            return_value=fake_neighbors_payload,
        ), mock.patch(
            "app.database.SessionLocal",
            return_value=mock.MagicMock(),
        ), mock.patch(
            "app.services.search_engine.meili",
            fake_meili,
        ):
            out = tool_semantic_search_articles._handler(q="伊朗", limit=5)

        self.assertTrue(out["semantic_index_ready"])
        self.assertEqual(out["seed"]["_id"], 100)
        self.assertEqual(out["total"], 2)
        self.assertEqual(out["neighbors"][0]["_id"], 101)
        self.assertTrue(out["neighbors"][0]["above_threshold"])


# =============================================================================
# analyze_event_sentiment
# =============================================================================
class AnalyzeEventSentimentToolTestCase(unittest.TestCase):
    def test_spec_registered(self):
        self.assertEqual(
            tool_analyze_event_sentiment.SPEC.name, "analyze_event_sentiment"
        )

    def test_handler_raises_on_invalid_event_id(self):
        with self.assertRaises(ValueError):
            tool_analyze_event_sentiment._handler(event_id=0)

    def test_event_not_found(self):
        fake_db = mock.MagicMock()
        fake_db.query.return_value.filter.return_value.first.return_value = None
        with mock.patch("app.database.SessionLocal", return_value=fake_db):
            out = tool_analyze_event_sentiment._handler(event_id=999)
        self.assertFalse(out["found"])

    def test_computes_distribution_and_timeline(self):
        fake_event = _fake_event(id=170, title="伊朗事件", article_count=4)
        t0 = datetime(2026, 4, 19, 0, 0, tzinfo=timezone.utc)
        # 4 篇文章分布在 bucket 0, 0, 1, 2（bucket_hours=12）
        fake_articles = [
            SimpleNamespace(
                id=1, title="A", source_id="w", url="", ai_sentiment="negative",
                ai_summary="", pub_date=t0, fetch_time=t0,
            ),
            SimpleNamespace(
                id=2, title="B", source_id="w", url="", ai_sentiment="negative",
                ai_summary="", pub_date=datetime(2026, 4, 19, 6, 0, tzinfo=timezone.utc),
                fetch_time=t0,
            ),
            SimpleNamespace(
                id=3, title="C", source_id="w", url="", ai_sentiment="positive",
                ai_summary="", pub_date=datetime(2026, 4, 19, 18, 0, tzinfo=timezone.utc),
                fetch_time=t0,
            ),
            SimpleNamespace(
                id=4, title="D", source_id="w", url="", ai_sentiment="neutral",
                ai_summary="", pub_date=datetime(2026, 4, 20, 6, 0, tzinfo=timezone.utc),
                fetch_time=t0,
            ),
        ]
        link_rows = [SimpleNamespace(article_id=a.id) for a in fake_articles]

        fake_db = mock.MagicMock()
        q_event = mock.MagicMock()
        q_event.filter.return_value.first.return_value = fake_event
        q_ea = mock.MagicMock()
        q_ea.filter.return_value.all.return_value = link_rows
        q_art = mock.MagicMock()
        q_art.filter.return_value.all.return_value = fake_articles

        def _query_side(model):
            from app.database import Article, Event, EventArticle
            return {Event: q_event, EventArticle: q_ea, Article: q_art}[model]

        fake_db.query.side_effect = _query_side

        with mock.patch("app.database.SessionLocal", return_value=fake_db):
            out = tool_analyze_event_sentiment._handler(
                event_id=170, bucket_hours=12
            )

        self.assertTrue(out["found"])
        self.assertEqual(out["article_count"], 4)
        self.assertEqual(out["labelled_count"], 4)
        self.assertEqual(out["overall_distribution"]["negative"], 2)
        self.assertEqual(out["overall_distribution"]["positive"], 1)
        self.assertEqual(out["overall_distribution"]["neutral"], 1)
        # bucket 0 应有 2 条 negative
        self.assertEqual(out["timeline"][0]["distribution"]["negative"], 2)
        self.assertEqual(out["timeline"][1]["distribution"]["positive"], 1)

    def test_bucket_hours_clamped_to_allowed(self):
        """非法 bucket_hours 回退到默认"""
        fake_db = mock.MagicMock()
        fake_db.query.return_value.filter.return_value.first.return_value = None
        with mock.patch("app.database.SessionLocal", return_value=fake_db):
            out = tool_analyze_event_sentiment._handler(event_id=1, bucket_hours=99)
        # 只要不抛异常 + 返回 found=False 就 OK（默认 bucket 被应用到不存在的事件不会产生 timeline）
        self.assertFalse(out["found"])


# =============================================================================
# compare_events
# =============================================================================
class CompareEventsToolTestCase(unittest.TestCase):
    def test_spec_registered(self):
        self.assertEqual(tool_compare_events.SPEC.name, "compare_events")

    def test_requires_at_least_two(self):
        with self.assertRaises(ValueError):
            tool_compare_events._handler(event_ids=[10])

    def test_parses_json_string_input(self):
        fake_events = [
            _fake_event(id=1, title="A", article_count=10, heat_score=50.0, keywords='["x","y"]'),
            _fake_event(id=2, title="B", article_count=30, heat_score=90.0, keywords='["y","z"]'),
        ]
        fake_db = mock.MagicMock()
        fake_db.query.return_value.filter.return_value.all.return_value = fake_events

        with mock.patch("app.database.SessionLocal", return_value=fake_db):
            out = tool_compare_events._handler(event_ids="[1, 2]")

        self.assertEqual(len(out["events"]), 2)
        self.assertEqual(out["requested_ids"], [1, 2])
        self.assertEqual(
            out["comparison_summary"]["max_article_count"]["_id"], 2
        )
        self.assertEqual(
            out["comparison_summary"]["keyword_intersection"], ["y"]
        )

    def test_truncates_to_max_events(self):
        fake_events = [_fake_event(id=i, title=f"E{i}") for i in range(1, 5)]
        fake_db = mock.MagicMock()
        fake_db.query.return_value.filter.return_value.all.return_value = fake_events
        with mock.patch("app.database.SessionLocal", return_value=fake_db):
            out = tool_compare_events._handler(event_ids=[1, 2, 3, 4, 5, 6])
        self.assertLessEqual(len(out["requested_ids"]), tool_compare_events.MAX_EVENTS)

    def test_reports_missing_events(self):
        fake_events = [_fake_event(id=1, title="A")]  # 只找到 1，没找到 2
        fake_db = mock.MagicMock()
        fake_db.query.return_value.filter.return_value.all.return_value = fake_events
        with mock.patch("app.database.SessionLocal", return_value=fake_db):
            out = tool_compare_events._handler(event_ids=[1, 2])
        self.assertEqual(out["missing_ids"], [2])


if __name__ == "__main__":
    unittest.main()

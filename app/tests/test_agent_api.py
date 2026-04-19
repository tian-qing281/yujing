"""
Agent HTTP 接口 · M3 集成测试

策略：
- 用 FastAPI TestClient 直接打 `/api/agent/chat`
- monkeypatch `agent_routes._build_loop` 返回注入 FakeLLM 的 Loop
- 用独立 `ToolRegistry` 注册 2 个 mock 工具，不碰真的 8 个工具
  （避免触发 DB/Meili/semantic_index，保持测试完全离线）

覆盖：
- 非流式 happy path：search → detail → final
- 流式 happy path：验证 SSE 事件类型顺序
- 工具失败的场景：LLM 通过 observation 自修复
- 参数校验：message 空串返 422
"""

import json
import unittest
from typing import Any, Dict, List
from unittest import mock

from fastapi.testclient import TestClient

from app.services.agent import AgentLoop, ToolRegistry, ToolSpec
from app.services.agent.llm_adapter import LLMResponse
from app.services.agent.schemas import ToolCall


# -----------------------------------------------------------------------------
# FakeLLM 和 mock registry 辅助（和 test_agent_loop.py 保持一致的风格）
# -----------------------------------------------------------------------------
class FakeLLM:
    def __init__(self, scripted_responses: List[LLMResponse]):
        self.scripted = list(scripted_responses)

    def __call__(self, messages, tools_openai_format, **_):
        if not self.scripted:
            raise AssertionError("FakeLLM 脚本已用完")
        return self.scripted.pop(0)


def _tc(name: str, args: Dict[str, Any], cid: str) -> ToolCall:
    return ToolCall(call_id=cid, name=name, arguments=args)


def _make_mock_registry() -> ToolRegistry:
    reg = ToolRegistry()

    def _search_events(**kwargs):
        return {
            "query": kwargs.get("q", ""),
            "total": 1,
            "events": [{"_id": 10, "_type": "event", "_title": "霍尔木兹海峡开放",
                        "article_count": 43, "heat_score": 398.0}],
        }

    def _get_event_detail(**kwargs):
        return {
            "_id": kwargs.get("event_id"),
            "_type": "event",
            "_title": "霍尔木兹海峡开放",
            "found": True,
            "article_count": 43,
            "summary": "伊朗声明恢复海峡通行...",
        }

    reg.register(ToolSpec(
        name="search_events",
        description="按关键词查事件",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}},
                      "required": ["q"]},
        handler=_search_events,
    ))
    reg.register(ToolSpec(
        name="get_event_detail",
        description="取事件详情",
        input_schema={"type": "object",
                      "properties": {"event_id": {"type": "integer"}},
                      "required": ["event_id"]},
        handler=_get_event_detail,
    ))
    return reg


def _build_app():
    """构造一个只挂 agent_routes 的最小 FastAPI app，避免全量 main.py 启动副作用
    （爬虫调度、DB 初始化、MeiliSearch 健康检查等）。"""
    from fastapi import FastAPI
    from app.api import agent_routes

    app = FastAPI()
    app.include_router(agent_routes.router, prefix="/api")
    return app


def _patched_build_loop(fake_llm: FakeLLM, registry: ToolRegistry):
    """返回一个 `_build_loop` 替身，签名匹配 agent_routes._build_loop。"""
    def _builder(max_steps=None):
        kwargs: Dict[str, Any] = {"registry": registry, "llm_caller": fake_llm}
        if max_steps is not None:
            kwargs["max_steps"] = max_steps
        return AgentLoop(**kwargs)
    return _builder


# =============================================================================
# /agent/chat · 非流式
# =============================================================================
class AgentChatBlockingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = _build_app()
        self.client = TestClient(self.app)
        self.registry = _make_mock_registry()

    def test_happy_path_returns_full_trajectory(self):
        fake = FakeLLM([
            LLMResponse(content="", tool_calls=[_tc("search_events", {"q": "霍尔木兹"}, "c1")]),
            LLMResponse(content="", tool_calls=[_tc("get_event_detail", {"event_id": 10}, "c2")]),
            LLMResponse(content="事件#10 共 43 篇报道。", tool_calls=[]),
        ])

        with mock.patch(
            "app.api.agent_routes._build_loop",
            _patched_build_loop(fake, self.registry),
        ), mock.patch(
            "app.api.agent_routes._ensure_tools_registered",
            lambda: None,
        ):
            resp = self.client.post(
                "/api/agent/chat",
                json={"message": "霍尔木兹的情况怎么样？", "stream": False},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["finished"])
        self.assertEqual(data["terminated_reason"], "final")
        self.assertIn("事件#10", data["final"])
        # 3 步 trajectory（2 tool_call + 1 final）
        self.assertEqual(len(data["trajectory"]["steps"]), 3)
        self.assertEqual(data["trajectory"]["steps"][0]["kind"], "tool_call")
        self.assertEqual(data["trajectory"]["steps"][-1]["kind"], "final")

    def test_empty_message_returns_422(self):
        resp = self.client.post("/api/agent/chat", json={"message": "", "stream": False})
        self.assertEqual(resp.status_code, 422)

    def test_tool_error_recovered_by_llm(self):
        """工具抛错 → observation 带 error → LLM 换工具继续 → 收敛。"""
        fake = FakeLLM([
            # 第 1 轮：调不存在的工具
            LLMResponse(content="", tool_calls=[_tc("does_not_exist", {}, "c1")]),
            # 第 2 轮：读到 error observation，换正确工具
            LLMResponse(content="", tool_calls=[_tc("search_events", {"q": "test"}, "c2")]),
            # 第 3 轮：final
            LLMResponse(content="结果已汇总。", tool_calls=[]),
        ])

        with mock.patch(
            "app.api.agent_routes._build_loop",
            _patched_build_loop(fake, self.registry),
        ), mock.patch(
            "app.api.agent_routes._ensure_tools_registered",
            lambda: None,
        ):
            resp = self.client.post(
                "/api/agent/chat",
                json={"message": "test", "stream": False},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["finished"])
        # 第 1 步的 tool_result 应带 error
        step0_results = data["trajectory"]["steps"][0]["tool_results"]
        self.assertIsNotNone(step0_results[0]["error"])


# =============================================================================
# /agent/chat · 流式
# =============================================================================
class AgentChatStreamingTestCase(unittest.TestCase):
    def setUp(self):
        self.app = _build_app()
        self.client = TestClient(self.app)
        self.registry = _make_mock_registry()

    def _collect_sse_events(self, response_text: str) -> List[Dict[str, Any]]:
        events = []
        for line in response_text.splitlines():
            if line.startswith("data: "):
                payload = line[len("data: "):].strip()
                if payload:
                    events.append(json.loads(payload))
        return events

    def test_streaming_emits_expected_event_types(self):
        fake = FakeLLM([
            LLMResponse(content="", tool_calls=[_tc("search_events", {"q": "霍尔木兹"}, "c1")]),
            LLMResponse(content="总结:事件#10 共 43 篇。", tool_calls=[]),
        ])

        with mock.patch(
            "app.api.agent_routes._build_loop",
            _patched_build_loop(fake, self.registry),
        ), mock.patch(
            "app.api.agent_routes._ensure_tools_registered",
            lambda: None,
        ):
            with self.client.stream(
                "POST",
                "/api/agent/chat",
                json={"message": "霍尔木兹怎么样？", "stream": True},
            ) as resp:
                self.assertEqual(resp.status_code, 200)
                self.assertIn("text/event-stream", resp.headers["content-type"])
                body = "".join(chunk for chunk in resp.iter_text())

        events = self._collect_sse_events(body)
        types = [e["type"] for e in events]

        # 应该至少包含：两次 llm_thinking，一次 tool_call/tool_result，一次 final，一次 done
        self.assertIn("llm_thinking", types)
        self.assertIn("tool_call", types)
        self.assertIn("tool_result", types)
        self.assertIn("final", types)
        self.assertIn("done", types)
        # done 必须是最后一个事件
        self.assertEqual(types[-1], "done")

        # tool_call 和 tool_result 的 name 必须一致
        tc_events = [e for e in events if e["type"] == "tool_call"]
        tr_events = [e for e in events if e["type"] == "tool_result"]
        self.assertEqual(tc_events[0]["name"], "search_events")
        self.assertEqual(tr_events[0]["name"], "search_events")
        self.assertTrue(tr_events[0]["ok"])


# =============================================================================
# /agent/tools
# =============================================================================
class AgentListToolsTestCase(unittest.TestCase):
    def setUp(self):
        self.app = _build_app()
        self.client = TestClient(self.app)

    def test_list_tools_returns_registered_specs(self):
        # 真的 bootstrap 一次（注册 8 个工具），只读不副作用
        from app.services.agent import tools as _tools_pkg  # noqa: F401
        resp = self.client.get("/api/agent/tools")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data["count"], 8)
        names = [t["name"] for t in data["tools"]]
        self.assertIn("search_events", names)
        self.assertIn("get_event_detail", names)
        self.assertIn("compare_events", names)


if __name__ == "__main__":
    unittest.main()

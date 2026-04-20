"""
Agent Loop 的离线单测。

不依赖 LLM 实际调用：通过 `llm_caller` 注入 `FakeLLM` 控制每轮返回，
验证 Loop 在典型场景下的行为正确性。
"""

import unittest
from typing import Any, Dict, List

from app.services.agent import AgentLoop, ToolRegistry, ToolSpec
from app.services.agent.llm_adapter import LLMResponse
from app.services.agent.schemas import ToolCall


class FakeLLM:
    """可脚本化的假 LLM：按调用次数逐个返回预设 response。"""

    def __init__(self, scripted_responses: List[LLMResponse]):
        self.scripted = list(scripted_responses)
        self.received_messages: List[List[Dict[str, Any]]] = []

    def __call__(self, messages, tools_openai_format, **_):
        self.received_messages.append(list(messages))
        if not self.scripted:
            raise AssertionError("FakeLLM 脚本已用完，但 Loop 还在调用")
        return self.scripted.pop(0)


def _tool_call(name: str, args: Dict[str, Any], call_id: str) -> ToolCall:
    return ToolCall(call_id=call_id, name=name, arguments=args)


class AgentLoopTestCase(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.call_log: List[Dict[str, Any]] = []

        def _handler_search_events(**kwargs):
            self.call_log.append({"tool": "search_events", "args": kwargs})
            return {"events": [{"_id": 10, "_title": "伊朗霍尔木兹"}]}

        def _handler_get_detail(**kwargs):
            self.call_log.append({"tool": "get_event_detail", "args": kwargs})
            return {"_id": kwargs.get("event_id"), "article_count": 41}

        def _handler_buggy(**kwargs):
            self.call_log.append({"tool": "buggy", "args": kwargs})
            raise RuntimeError("boom")

        self.registry.register(ToolSpec(
            name="search_events",
            description="按关键词查事件",
            input_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
            handler=_handler_search_events,
        ))
        self.registry.register(ToolSpec(
            name="get_event_detail",
            description="取事件详情",
            input_schema={
                "type": "object",
                "properties": {"event_id": {"type": "integer"}},
                "required": ["event_id"],
            },
            handler=_handler_get_detail,
        ))
        self.registry.register(ToolSpec(
            name="buggy",
            description="故意失败的工具",
            input_schema={"type": "object", "properties": {}},
            handler=_handler_buggy,
        ))

    def test_three_step_tool_chain_then_final(self):
        """典型正路径：search → detail → final answer"""
        fake = FakeLLM([
            LLMResponse(content="", tool_calls=[_tool_call(
                "search_events", {"q": "霍尔木兹"}, "call_1"
            )]),
            LLMResponse(content="", tool_calls=[_tool_call(
                "get_event_detail", {"event_id": 10}, "call_2"
            )]),
            LLMResponse(content="事件#10 共 41 篇报道", tool_calls=[]),
        ])
        loop = AgentLoop(registry=self.registry, llm_caller=fake)

        traj = loop.run("最近伊朗霍尔木兹相关舆情")

        self.assertTrue(traj.finished)
        self.assertEqual(traj.terminated_reason, "final")
        self.assertEqual(len(traj.steps), 3)
        self.assertEqual(traj.steps[0].kind, "tool_call")
        self.assertEqual(traj.steps[0].tool_calls[0].name, "search_events")
        self.assertEqual(traj.steps[1].kind, "tool_call")
        self.assertEqual(traj.steps[1].tool_calls[0].name, "get_event_detail")
        self.assertEqual(traj.steps[2].kind, "final")
        self.assertIn("41 篇", traj.final_answer)
        # handler 都被真实调到
        self.assertEqual([c["tool"] for c in self.call_log],
                         ["search_events", "get_event_detail"])

    def test_unknown_tool_becomes_observation_error_then_recovers(self):
        """LLM 调了一个未注册的工具 → observation 带 error，下一轮能 final"""
        fake = FakeLLM([
            LLMResponse(content="", tool_calls=[_tool_call(
                "non_existent_tool", {"x": 1}, "call_1"
            )]),
            LLMResponse(content="抱歉数据不足", tool_calls=[]),
        ])
        loop = AgentLoop(registry=self.registry, llm_caller=fake)

        traj = loop.run("demo query")

        self.assertTrue(traj.finished)
        self.assertEqual(traj.terminated_reason, "final")
        self.assertEqual(len(traj.steps), 2)
        # 第一步 tool_call 有 error
        err_result = traj.steps[0].tool_results[0]
        self.assertIsNotNone(err_result.error)
        self.assertIn("unknown tool", err_result.error)
        # 第二轮 LLM 收到的 messages 里有 role=tool 的错误 observation
        msgs_sent_to_llm_round2 = fake.received_messages[1]
        tool_msgs = [m for m in msgs_sent_to_llm_round2 if m["role"] == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertIn("unknown tool", tool_msgs[0]["content"])

    def test_handler_exception_wrapped_as_error(self):
        """handler 抛异常 → 被捕获成 ToolResult.error，Loop 不崩"""
        fake = FakeLLM([
            LLMResponse(content="", tool_calls=[_tool_call(
                "buggy", {}, "call_1"
            )]),
            LLMResponse(content="工具异常已记录", tool_calls=[]),
        ])
        loop = AgentLoop(registry=self.registry, llm_caller=fake)

        traj = loop.run("trigger buggy")

        self.assertTrue(traj.finished)
        self.assertEqual(traj.steps[0].tool_results[0].error, "tool error: boom")

    def test_max_steps_terminates_gracefully(self):
        """LLM 一直调 tool 不给 final → max_steps 后强制终止"""
        # 准备 10 个连续 tool_call 的脚本，Loop max_steps=3
        scripted = [
            LLMResponse(content="", tool_calls=[_tool_call(
                "search_events", {"q": f"q{i}"}, f"call_{i}"
            )])
            for i in range(10)
        ]
        fake = FakeLLM(scripted)
        loop = AgentLoop(registry=self.registry, llm_caller=fake, max_steps=3)

        traj = loop.run("stuck in loop")

        self.assertFalse(traj.finished)
        self.assertEqual(traj.terminated_reason, "max_steps")
        self.assertEqual(len(traj.steps), 3)

    def test_llm_call_exception_captured(self):
        """LLM 调用本身抛错 → trajectory 记录 error 并终止"""

        def _raising_caller(messages, tools_openai_format, **_):
            raise ConnectionError("deepseek down")

        loop = AgentLoop(registry=self.registry, llm_caller=_raising_caller)
        traj = loop.run("anything")

        self.assertFalse(traj.finished)
        self.assertEqual(traj.terminated_reason, "error")
        self.assertEqual(traj.steps[0].kind, "error")
        self.assertIn("deepseek down", traj.steps[0].assistant_content)

    def test_parallel_tool_calls_preserve_order_and_run_concurrently(self):
        """同一轮 LLM 返回 >1 tool_calls → 并发执行 + 结果按原顺序回注 messages。

        手段：两个 handler 各 sleep 0.2s，串行应 > 0.4s，并发应 < 0.35s。
        """
        import time

        self.registry = ToolRegistry()

        def _slow_a(**kwargs):
            time.sleep(0.2)
            return {"who": "A", "arg": kwargs.get("x")}

        def _slow_b(**kwargs):
            time.sleep(0.2)
            return {"who": "B", "arg": kwargs.get("x")}

        self.registry.register(ToolSpec(
            name="slow_a", description="slow tool A",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            handler=_slow_a,
        ))
        self.registry.register(ToolSpec(
            name="slow_b", description="slow tool B",
            input_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
            handler=_slow_b,
        ))

        fake = FakeLLM([
            LLMResponse(content="", tool_calls=[
                _tool_call("slow_a", {"x": 1}, "call_1"),
                _tool_call("slow_b", {"x": 2}, "call_2"),
            ]),
            LLMResponse(content="done", tool_calls=[]),
        ])
        loop = AgentLoop(registry=self.registry, llm_caller=fake)

        t0 = time.time()
        traj = loop.run("parallel query")
        elapsed = time.time() - t0

        self.assertTrue(traj.finished)
        self.assertLess(elapsed, 0.35, f"并发未生效，elapsed={elapsed:.3f}s（串行下限 0.4s）")
        # 结果顺序必须等于 tool_calls 下达顺序（call_1 → call_2）
        results = traj.steps[0].tool_results
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].call_id, "call_1")
        self.assertEqual(results[0].output["who"], "A")
        self.assertEqual(results[1].call_id, "call_2")
        self.assertEqual(results[1].output["who"], "B")
        # 第二轮 LLM 收到的 messages 里，tool observation 顺序应为 A、B
        tool_msgs = [m for m in fake.received_messages[1] if m["role"] == "tool"]
        self.assertEqual(len(tool_msgs), 2)
        self.assertIn('"A"', tool_msgs[0]["content"])
        self.assertIn('"B"', tool_msgs[1]["content"])

    def test_trajectory_to_dict_is_json_serializable(self):
        """to_dict() 结果必须能 json.dumps，M3 的 SSE 流需要"""
        import json as _json
        fake = FakeLLM([
            LLMResponse(content="", tool_calls=[_tool_call(
                "search_events", {"q": "x"}, "call_1"
            )]),
            LLMResponse(content="done", tool_calls=[]),
        ])
        traj = AgentLoop(registry=self.registry, llm_caller=fake).run("x")

        payload = traj.to_dict()
        dumped = _json.dumps(payload, ensure_ascii=False)
        self.assertIn("search_events", dumped)
        self.assertIn("done", dumped)


if __name__ == "__main__":
    unittest.main()

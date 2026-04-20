"""
Agent HTTP 接口 · M3

核心端点：`POST /agent/chat`，支持两种模式：
- `stream=true`（默认）：SSE 流式推送每个 agent 事件
- `stream=false`：非流式，阻塞到跑完返回完整 trajectory JSON

SSE 事件格式（每条 `data: <json>\n\n`）：
  {"type":"llm_thinking","step":0}
  {"type":"tool_call","step":0,"name":"search_events","args":{...}}
  {"type":"tool_result","step":0,"name":"search_events","ok":true,
   "output":{...},"error":null,"latency_ms":42}
  {"type":"final","text":"..."}
  {"type":"done","terminated_reason":"final","total_latency_ms":1234}

实现要点：
1. `AgentLoop.run()` 是同步阻塞的（内部要调 LLM + DB）
   → 在 `asyncio.to_thread` 里跑，主事件循环不被卡
2. 用 `asyncio.Queue` 做桥接：Loop 线程往 queue 塞事件，
   SSE generator 从 queue 里取并 yield
3. 工具注册 lazy bootstrap：首次请求时 `import app.services.agent.tools`
   触发 8 个 `register(SPEC)` 副作用（side-effect import 注册模式）
4. 输出序列化：`tool_result.output` 可能含 datetime，统一 `default=str`
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

_TOOLS_BOOTSTRAPPED = False


def _ensure_tools_registered() -> None:
    """首次调用时触发 tools 包的模块级 register 副作用。幂等。"""
    global _TOOLS_BOOTSTRAPPED
    if _TOOLS_BOOTSTRAPPED:
        return
    from app.services.agent import tools  # noqa: F401
    _TOOLS_BOOTSTRAPPED = True
    from app.services.agent.registry import default_registry
    logger.info("[agent] tools bootstrap done · %d tools registered", len(default_registry))


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="用户问题")
    stream: bool = Field(True, description="是否走 SSE 流式返回")
    conversation_id: Optional[str] = Field(None, description="预留多轮用，MVP 不使用")
    max_steps: Optional[int] = Field(None, ge=1, le=12, description="覆盖默认 step 上限（默认 8）")


def _sse_format(event: Dict[str, Any]) -> str:
    """把 event dict 编成一条 SSE 消息。datetime / 其它非常规对象兜底为 str。"""
    try:
        payload = json.dumps(event, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        payload = json.dumps(
            {"type": "error", "message": f"event serialization failed: {exc}"},
            ensure_ascii=False,
        )
    return f"data: {payload}\n\n"


def _build_loop(max_steps: Optional[int] = None):
    """构造一个默认配置的 AgentLoop。独立函数便于单测 monkeypatch。"""
    from app.services.agent.loop import AgentLoop
    from app.services.agent.registry import default_registry

    kwargs: Dict[str, Any] = {"registry": default_registry}
    if max_steps is not None:
        kwargs["max_steps"] = max_steps
    return AgentLoop(**kwargs)


@router.post("/agent/chat")
async def agent_chat(req: ChatRequest):
    _ensure_tools_registered()

    if req.stream:
        return await _stream_chat(req)
    return await _blocking_chat(req)


async def _stream_chat(req: ChatRequest) -> StreamingResponse:
    """SSE 流式返回。

    在独立 thread 里跑同步 AgentLoop；主协程从 asyncio.Queue 取事件 yield。
    生产者用 loop.call_soon_threadsafe + queue.put_nowait 保证跨线程安全。
    """
    loop_asyncio = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _on_event(event: Dict[str, Any]) -> None:
        loop_asyncio.call_soon_threadsafe(queue.put_nowait, event)

    async def _runner() -> None:
        """在 thread 里跑 AgentLoop.run()，完成后塞一个 sentinel。"""
        agent_loop = _build_loop(max_steps=req.max_steps)
        try:
            await asyncio.wait_for(
                asyncio.to_thread(agent_loop.run, req.message, _on_event),
                timeout=90,
            )
        except asyncio.TimeoutError:
            logger.warning("[agent.api] Agent 总超时 90s，强制结束")
            loop_asyncio.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": "分析超时，请缩小问题范围后重试", "terminated_reason": "timeout"},
            )
            loop_asyncio.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "done", "terminated_reason": "timeout", "total_latency_ms": 90000},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[agent.api] run 抛出未捕获异常")
            loop_asyncio.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": f"agent 内部错误: {exc}"},
            )
        finally:
            loop_asyncio.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    async def _event_stream():
        task = asyncio.create_task(_runner())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if event is None:  # sentinel
                    break
                yield _sse_format(event)
        finally:
            # 客户端断开时取消 task，避免线程泄漏
            if not task.done():
                task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁止 nginx buffer
        },
    )


async def _blocking_chat(req: ChatRequest) -> JSONResponse:
    """非流式：跑完再一次性返回完整 trajectory + final。"""
    agent_loop = _build_loop(max_steps=req.max_steps)

    try:
        trajectory = await asyncio.to_thread(agent_loop.run, req.message)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[agent.api] blocking run 失败")
        raise HTTPException(status_code=500, detail=f"agent 内部错误: {exc}")

    return JSONResponse(
        content={
            "query": trajectory.query,
            "finished": trajectory.finished,
            "terminated_reason": trajectory.terminated_reason,
            "total_latency_ms": trajectory.total_latency_ms,
            "final": trajectory.final_answer,
            "trajectory": trajectory.to_dict(),
        },
    )


@router.get("/agent/tools")
def list_tools():
    """暴露已注册工具的 schema，便于前端展示 / 调试 / 文档。"""
    _ensure_tools_registered()
    from app.services.agent.registry import default_registry

    return {
        "count": len(default_registry),
        "tools": [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
            }
            for spec in default_registry.list_all()
        ],
    }

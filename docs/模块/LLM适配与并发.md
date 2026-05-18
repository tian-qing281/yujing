# 模块 · LLM 适配与并发

> 最后更新 2026-05-18 · 主入口 [app/services/llm.py](../../app/services/llm.py) · Agent 路径 [app/services/agent/llm_adapter.py](../../app/services/agent/llm_adapter.py)

## 1. 三个 LLM 调用路径

| 路径 | 入口 | 协议 | 用途 |
|------|------|------|------|
| **普通文本生成** | `llm.chat_with_news()` | Chat Completions | 摘要 / ABSA / 早报模板 |
| **Agent 工具调用** | `agent/llm_adapter.py` | tools / tool_calls | 11 工具循环 |
| **流式回答** | Agent loop | SSE | `/api/ai/chat` |

## 2. 配置

环境变量：

| 名称 | 默认 | 说明 |
|------|------|------|
| `LLM_PROVIDER` | `deepseek` | 或 `openai` |
| `DEEPSEEK_API_KEY` | - | 必填（默认 provider）|
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | |
| `OPENAI_API_KEY` | - | provider=openai 时必填 |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | |
| `LLM_MODEL` | `deepseek-chat` | 或 `gpt-4o-mini` |
| `LLM_TIMEOUT` | 30 | 秒 |
| `LLM_MAX_RETRIES` | 2 | 失败重试 |

## 3. 普通调用（llm.py）

```python
def chat_with_news(prompt: str,
                   max_tokens: int = 800,
                   temperature: float = 0.35) -> str:
    """同步调用，返回纯文本。失败重试 2 次后抛异常。"""
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            resp = _client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=LLM_TIMEOUT,
            )
            return resp.choices[0].message.content
        except Exception as e:
            if attempt < LLM_MAX_RETRIES:
                time.sleep(2 ** attempt)  # 1s / 2s 指数退避
            else:
                raise
```

调用方：
- [aspect_analysis.py](../../app/services/aspect_analysis.py)（ABSA 抽取）
- [routes.py /api/articles/{id}/analyze](../../app/api/routes.py)（全文 LLM 摘要）
- [routes.py /api/ai/morning_brief](../../app/api/routes.py)（早报模板）

## 4. Agent 工具调用（agent/llm_adapter.py）

走 OpenAI **tools / tool_calls** 协议：

```python
class BaseLLMClient:
    async def chat_with_tools(self, messages, tools, **kwargs) -> Response: ...

class DeepSeekClient(BaseLLMClient): ...
class OpenAIClient(BaseLLMClient): ...
```

工厂：

```python
def get_llm_client() -> BaseLLMClient:
    return {"deepseek": DeepSeekClient, "openai": OpenAIClient}[LLM_PROVIDER]()
```

工具 schema：

```python
tools_spec = [
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "...",
            "parameters": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }
    },
    ...
]
```

## 5. 流式（SSE）

```python
async def chat_stream(messages):
    async with client.chat.completions.stream(
        model=LLM_MODEL,
        messages=messages,
        ...
    ) as stream:
        async for event in stream:
            if event.type == "content.delta":
                yield event.delta
```

前端 `EventSource('/api/ai/chat')` 接收 token / step / tool_result 三类事件。

## 6. 并发控制

| 资源 | 上限 | 实现 |
|------|------|------|
| `/api/articles/{id}/analyze` 全文分析 | 3 | `_analyze_global_semaphore = asyncio.Semaphore(3)` |
| 同文章重复分析 | 1 | `_analyze_inflight: dict[int, asyncio.Event]` |
| Agent 单轮 LLM 调用 | 无显式限制 | 受 LLM 服务端 RPS |

防雪崩例子：

```python
async def analyze_article(article_id):
    async with _analyze_global_semaphore:           # 全局并发 ≤ 3
        if article_id in _analyze_inflight:         # 同文章去重
            await _analyze_inflight[article_id].wait()
            return cached_result
        _analyze_inflight[article_id] = asyncio.Event()
        try:
            result = await do_analyze(article_id)
            return result
        finally:
            _analyze_inflight.pop(article_id).set()
```

## 7. 错误处理

| 错误 | 兜底 |
|------|------|
| 网络超时 | 重试 2 次，仍失败抛异常 |
| 401 / 403 | 抛 `LLMAuthError`，路由层返回 503 |
| 429 限流 | 重试 + 退避，仍失败返回模板答复 |
| 5xx | 同上 |
| JSON 解析失败（ABSA）| 返回空数组 `[]` |
| 上下文超长 | 截断历史 / 文章正文，重试 |

## 8. 日志

每次 LLM 调用写 `runtime/logs/llm/{date}.jsonl`：

```json
{
  "ts": "2026-05-18T10:23:45",
  "provider": "deepseek",
  "model": "deepseek-chat",
  "tokens_prompt": 1820,
  "tokens_completion": 412,
  "latency_ms": 1340,
  "error": null
}
```

Agent 路径额外写 `runtime/logs/agent/{date}.jsonl`：包含 messages / tool_calls / response 全链。

## 9. 成本估算

DeepSeek-chat（2026 价格）：
- 输入 0.0014 元 / 千 tokens
- 输出 0.0028 元 / 千 tokens

单次调用平均：
| 场景 | tokens (in+out) | 单次成本 |
|------|---------------|---------|
| ABSA 抽取 | 1500 + 400 | ≈ 0.003 元 |
| 早报生成 | 4000 + 1500 | ≈ 0.010 元 |
| Agent 单轮 | 3000 + 600 | ≈ 0.006 元 |
| 全文 LLM 摘要 | 2500 + 300 | ≈ 0.004 元 |

日均（5w 文章 × 不全分析，仅高热门触发 ABSA）：≈ 30 元。

## 10. 已知限制

1. **同步阻塞 API**：`chat_with_news` 是同步的，路由层用 `run_in_threadpool` 包
2. **无 token 预算控制**：单次 prompt 超长会被截断但未做余额监控
3. **provider 切换不平滑**：环境变量改后需重启
4. **无缓存层**：相同 prompt 不会命中（ABSA 路径除外，有文件缓存）

# Agent 算法文档

> 最后更新 2026-05-18 · 对齐代码版本 · 主入口 [app/services/agent/loop.py](../../app/services/agent/loop.py) · 工具集 [app/services/agent/tools/](../../app/services/agent/tools/)

## 1. 设计目标

让用户用自然语言对全网热点数据做「**查 → 分析 → 对比 → 总结**」，要求：

1. **数据真实**：所有结论必须由工具返回的结构化数据驱动，不允许 LLM 凭空生成事件
2. **过程可见**：每一步「调了哪个工具、参数是什么、返回了什么」前端可见
3. **可中断 / 可重试**：单工具失败不应让整轮对话崩
4. **流式输出**：用户感受 < 1s 出第一字

## 2. 整体架构

```
用户输入
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│ Agent Loop (最多 MAX_STEPS = 8 步)                       │
│                                                          │
│   while step < 8:                                        │
│      llm_response = llm.chat(messages + tool_specs)      │
│      if llm 想调工具:                                    │
│          result = tools[name](**args)                    │
│          append(messages, tool_result)                   │
│          continue                                        │
│      else:                                               │
│          stream final answer                             │
│          break                                           │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
                SSE 流给前端
```

## 3. 主循环（loop.py）

### 3.1 关键参数

| 名称 | 默认 | 含义 |
|------|------|------|
| `MAX_STEPS` | 8 | 最大工具调用轮 |
| `MAX_CONSECUTIVE_ERRORS` | 2 | 连续工具失败上限 |
| `temperature` | 0.35 | 平衡确定性与表达力 |
| `max_tokens` | 800 | 单轮 LLM 输出上限 |

### 3.2 LLM 协议

我们走 OpenAI **tools / tool_calls** 协议（DeepSeek 兼容）：

```python
response = llm.chat.completions.create(
    model="deepseek-chat",
    messages=[system_prompt, *history, user],
    tools=[t.to_openai_spec() for t in TOOLS],
    tool_choice="auto",
    temperature=0.35,
    max_tokens=800,
)
```

每个工具有：`name / description / parameters (JSON schema)`。

### 3.3 工具调用循环（简化）

```python
for step in range(MAX_STEPS):
    msg = await call_llm(messages)
    if not msg.tool_calls:
        yield from stream_final(msg.content)
        return
    for call in msg.tool_calls:
        try:
            result = await TOOLS[call.name].run(**json.loads(call.arguments))
            consecutive_errors = 0
        except Exception as e:
            result = {"error": str(e)}
            consecutive_errors += 1
        messages.append(tool_message(call.id, result))
    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        yield "工具连续失败，已停止"
        return
yield "已达最大步数"
```

### 3.4 系统 Prompt 核心约束（节选）

- 仅基于工具返回数据回答；如工具返回为空，必须明说「无相关数据」
- 涉及具体数字（热度、占比）必须引用工具返回
- 输出用 Markdown，关键事实加粗
- 列举事件时附事件 ID 方便用户跳转

## 4. 工具集（11 个）

详见 [app/services/agent/tools/](../../app/services/agent/tools/)。每个工具一个文件、单一职责。

| # | 工具 | 用途 |
|---|------|------|
| 1 | `search_events` | 全文检索事件（Meili 优先） |
| 2 | `search_articles` | 全文检索文章 |
| 3 | `get_event_detail` | 事件详情（含代表文章 / 时序 / 情感分布）|
| 4 | `list_hot_platforms` | 各平台热度 TopN 汇总 |
| 5 | `rank_events_by_sentiment` | 按 negative ratio 排序 |
| 6 | `compare_platforms` | 两平台综合对比 |
| 7 | `analyze_event_sentiment` | 单事件情绪 + 时序桶 |
| 8 | `compare_events` | 多事件对比（最多 5 个）|
| 9 | `get_morning_brief` | 生成今日早报 |
| 10 | `semantic_search_articles` | 向量召回（与 Meili 互补）|
| 11 | `compare_platforms_radar` | 雷达图多维对比 |

工具基类 [tool_base.py](../../app/services/agent/tools/tool_base.py) 提供：参数 schema 校验、超时（10s 默认）、统一异常包装。

## 5. 流式输出（SSE）

`GET/POST /api/ai/chat` 走 Server-Sent Events：

```
event: step
data: {"step": 1, "tool": "search_events", "args": {...}}

event: tool_result
data: {"step": 1, "result": {...}}

event: token
data: "今日"

event: token
data: "热点"

event: done
data: {"total_steps": 3}
```

前端组件 [ChatPanel.vue](../../yujing-ui/src/components/ChatPanel.vue) 按 event 类型分通道渲染：步骤进度条 + 流式回答。

## 6. LLM 适配

文件 [app/services/agent/llm_adapter.py](../../app/services/agent/llm_adapter.py)。

- 抽象 `BaseLLMClient` → DeepSeek / OpenAI 通过环境变量切换
- 失败重试 2 次（指数退避 1s / 2s）
- 超时 30s
- 日志：每轮 LLM 调用写 `logs/agent/{date}.jsonl`

## 7. 早报子流程

`GET /api/ai/morning_brief` 走单工具直通路径：

1. 跳过 LLM 决策，直接调 `get_morning_brief(top_events=5)`
2. 工具拉「过去 24h 综合热度 TopN 事件」+ 各事件情感分布
3. 用模板渲染 Markdown
4. 缓存当日结果（`runtime/cache/morning_brief/{date}.md`）
5. 缓存命中：`GET /api/ai/morning_brief/cached` 直返

## 8. 已知限制

1. **MAX_STEPS=8**：复杂多事件比较可能用尽（实际 P99 ≈ 5 步）
2. **温度 0.35**：偶发措辞抖动，但保留表达多样
3. **无长记忆**：不跨会话存储用户偏好，每次都是从 system prompt 重启

---

<details>
<summary><b>面试问答</b></summary>

**Q1：为什么不用 LangChain / LlamaIndex？**
A：（1）这俩抽象层厚、调试难，出错时栈难定位；（2）我们工具数有限（11 个），手写 loop 200 行覆盖全部需求，可读性高；（3）原生 OpenAI tool_call 协议已经够好，不需要再包一层。

**Q2：MAX_STEPS=8 怎么定的？**
A：观察生产 100 轮对话，P95=5 P99=7，留 1 步缓冲设 8。再高 LLM 容易陷入「调工具 → 反思 → 再调同工具」死循环。

**Q3：怎么防止 LLM 编事件？**
A：System Prompt 强约束 + 工具返回会带 `event_id`，回答里要求引用 ID。线下 sanity check：扫描 LLM 答案中所有「事件 N」字样，对比是否在工具返回里出现过，未出现的标 hallucination。

**Q4：流式输出怎么保证工具结果不漏？**
A：SSE 三类事件分别有序：step → tool_result → token。前端用 step.id 关联 tool_result 显示。最后一个 done 事件包含 total_steps 校验。

**Q5：工具失败怎么办？**
A：单工具失败 → 把 error 作为 tool_message 返回给 LLM，让 LLM 决定换工具还是直接告诉用户。连续 2 次失败强行停止避免雪崩。

**Q6：DeepSeek vs OpenAI 怎么选？**
A：默认 DeepSeek-chat（中文场景便宜 + 速度快），生产可一键切 OpenAI。`llm_adapter.py` 用环境变量 `LLM_PROVIDER` 切换。

**Q7：工具 schema 怎么维护？**
A：每工具继承 `ToolBase`，类属性 `name / description / parameters_schema` 集中定义。新增工具只需写一个文件 + 在 `tools/__init__.py` 注册。

**Q8：怎么调试 Agent？**
A：（1）`logs/agent/{date}.jsonl` 每步完整记录 messages / tool_calls / response；（2）前端 step 流可见；（3）单工具可独立 unit test（每个 tool 文件都有对应 test）。

</details>

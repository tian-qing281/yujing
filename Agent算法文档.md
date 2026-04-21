# 舆镜（YuJing）Tool-Calling Agent 算法文档

> 本文与《聚类算法文档》《核心原理文档》平行，属论文级技术文档。读者对象：评委 / 合作者 / 自己两周后回来接坑。

---

## 一、算法概述

舆镜 Tool-Calling Agent 解决的问题：**把"自然语言提问"转化为"带溯源引用的结构化舆情研判"**。

与传统 RAG（检索-拼接-生成）相比，本系统的差异：

| 维度 | 传统 RAG | 本系统 Tool-Calling Agent |
|:---|:---|:---|
| 能力边界 | 固定：retrieve → stuff → generate | 开放：9 个原子工具任意组合 |
| 调用轮数 | 1 轮 LLM | 2-8 轮（自主决定） |
| 可解释性 | 黑盒拼接 | 每步 JSON 可审计（`llm_thinking / tool_call / tool_result`） |
| 防幻觉 | 仅提示 "based on context" | Tool 结果附 `_id` / `_type`，final 必须 `event#N` 绑定 |
| 新能力增加 | 改 prompt / retriever | 注册一个新 `ToolSpec`，Loop 无需改动 |

算法流水线：

```
自然语言 query
   ↓ build system_prompt + user_message
DeepSeek V3 (function calling)
   ├── tool_calls 非空 → 执行 handler → append ToolResult 观测 → 下一轮
   └── tool_calls 为空 → content 作为 final_answer → 打字机式切片 emit → 结束
```

**不使用任何硬编码阈值决定是否调工具**，完全由 LLM 的 function-calling 判断。

---

## 二、工具注册表（ToolRegistry）

### 2.1 数据模型

```python
@dataclass
class ToolSpec:
    name: str                          # 函数名，OpenAI spec 唯一 id
    description: str                   # 工具能力自然语言描述（供 LLM 选择）
    input_schema: dict                 # JSON Schema（参数结构）
    handler: Callable[[dict], Any]     # Python 可调用对象，返回可序列化结果
```

`ToolRegistry.register(spec)` 幂等注册；`to_openai_functions()` 自动把 `ToolSpec` 列表编译为 OpenAI `tools=[...]` 数组格式交给 DeepSeek。

### 2.2 当前 9 个原子工具

| 工具名 | 语义能力 | 关键参数 | 底层实现 |
|:---|:---|:---|:---|
| `search_events` | 关键词 + 时间窗口检索事件 | `q / time_range_hours / source_id / limit` | `services.events.search_events` |
| `get_event_detail` | 事件详情 + TopK 关联文章 | `event_id / top_articles` | 直读 `/api/events/{id}` 的 DB 查询，**只读不触 BERT 补全** |
| `compare_events` | 2-4 事件并列指标对比 | `event_ids` | 关键词交并集 + max heat 摘要 |
| `analyze_event_sentiment` | 事件情绪时间桶序列 | `event_id / bucket_hours ∈ {6,12,24}` | Counter 聚合 + 时间桶切片 |
| `search_articles` | 关键词文章搜索 | `q / time_range_hours / source_id / limit` | Meili 优先 / DB LIKE 降级 |
| `semantic_search_articles` | 向量语义搜索 | `q / limit / source_id` | 双阶段 Meili seed → BGE kNN |
| `list_hot_platforms` | 多平台热榜快照 | `time_range_hours / top_events_per_platform` | `source_id` group by + per-platform top |
| `get_morning_brief` | 当日早报内容直取 | 无 | 只读缓存，cache miss 返回 hint |
| `rank_events_by_sentiment` | 按情绪占比排序 Top-K 事件 | `event_ids / top_k / sentiment_type` | Counter 聚合 + 多事件情绪比较排序 |

### 2.3 工具设计约束（所有工具必守）

1. **handler 输出每个 item 必带元字段** `_id / _type / _title`：final answer 的 `event#N` / `article#N` 引用靠这三个字段拼装。
2. **超参数自动 clamp 不拒绝**：LLM 偶尔给出 `limit=50`（超上限 20）时 clamp 到 20 并继续执行，不浪费一整步让 LLM 自修复。
3. **handler 内部不崩**：所有异常由 Loop 捕获成 `ToolResult(error=...)`，作为 observation 给 LLM 看；同一工具连续两次 error 才会触 `too_many_errors` 终止。
4. **延迟 import 外部依赖**：`SessionLocal` / `meili` 在 handler 内部引用，避免启动期 import 污染 + 单测 `patch('app.database.SessionLocal')` 从源头生效。

---

## 三、Agent Loop 主循环

单文件 `app/services/agent/loop.py`，总代码 **~270 行**，核心 ~70 行：

```python
for step_idx in range(self.max_steps):
    _emit({"type": "llm_thinking", "step": step_idx})

    resp = self._llm_caller(
        messages=messages,
        tools_openai_format=self.registry.to_openai_functions(),
    )

    if resp.tool_calls:
        # 1) 把 assistant tool_calls 消息 append 回 messages
        messages.append(_assistant_tool_call_msg(resp.tool_calls, resp.content))

        # 2) 逐个执行 tool
        had_error = False
        for tc in resp.tool_calls:
            _emit({"type": "tool_call", ...})
            result = self._execute_tool(tc)           # 捕获所有异常成 result.error
            messages.append({"role": "tool",
                             "tool_call_id": tc.call_id,
                             "content": self._serialize_observation(result)})
            _emit({"type": "tool_result", ...})
            had_error = had_error or bool(result.error)

        # 3) 连续错误超阈值终止
        consecutive_errors = consecutive_errors + 1 if had_error else 0
        if consecutive_errors > self.max_consecutive_errors:
            trajectory.terminated_reason = "too_many_errors"; break
        continue

    # 无 tool_calls → final
    final_text = resp.content or ""
    trajectory.final_answer = final_text
    trajectory.terminated_reason = "final"
    # 打字机式推送
    if on_event and final_text:
        for i in range(0, len(final_text), CHUNK_SIZE):
            _emit({"type": "final_delta", "text": final_text[i:i+CHUNK_SIZE]})
            time.sleep(DELTA_SLEEP)
    _emit({"type": "final", "text": final_text})
    break
else:
    trajectory.terminated_reason = "max_steps"
```

### 3.1 关键常量

| 常量 | 值 | 作用 |
|:---|:---:|:---|
| `MAX_STEPS` | 8 | 总步数硬上限（从 M4 的 6 提到 8） |
| `MAX_CONSECUTIVE_ERRORS` | 2 | 连续 tool error 超此数终止 |
| `CHUNK_SIZE` | 12 | final_delta 切片字符数（打字机） |
| `DELTA_SLEEP` | 0.05 s | 切片间 sleep |

### 3.2 System Prompt 设计

```
你是一名"舆镜 YuJing"舆情分析助手。
你的任务是根据用户的问题，**自主决定**调用哪些工具来收集证据，再给出简洁、带引用的回答。

可用工具由运行时注入，调用规则：
- 优先调用语义/关键词检索定位相关事件，再调用详情工具拿证据。
- 每次调用前自问"现有信息是否足够回答"，够了就直接给 final answer，不要为调用而调用。
- **聚焦策略**：锁定 1-2 个最相关事件深入分析即可，不要对多个事件重复调用同一个工具；
  若用户问的是概览性问题，从 search 结果里直接总结而非逐个详查。
- 单次对话总步数不超过 8 步，绝大多数问题应在 3-5 步内收敛。
- 一旦已有足够信息（通常是 1 次检索 + 1-2 次细节 + 可选 1 次情绪/对比），立即给出 final answer。

回答要求：
- 中文输出，先给事实再给研判。
- 引用具体 `event#<id>` / `article#<id>`，不要编造 id。
- 如果工具返回空，诚实告知"当前数据未覆盖"，不要编造。
```

**"聚焦策略" 条款**是 M4 末根据 T4 类失败案例专门增加的：早期 prompt 未约束时 LLM 倾向于对每个 search 结果依次 `get_event_detail` + `analyze_sentiment`，导致发散触 max_steps。加入后平均步数从 >6 降到 4.9。

---

## 四、LLM Adapter

### 4.1 为什么有这一层

隔离 Loop 与具体 LLM provider（当前 DeepSeek V3，未来可能接 Qwen / GPT-4o / Claude）。Loop 只依赖以下简单协议：

```python
def call_llm(
    messages: list[dict],
    tools_openai_format: list[dict],
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> LLMResponse:
    ...

@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
```

### 4.2 OpenAI ↔ LangChain 消息转换

DeepSeek 兼容 OpenAI API，但项目统一通过 LangChain 走。需要 role 转换：

| dict role | LangChain | 备注 |
|:---|:---|:---|
| `system` | `SystemMessage` | |
| `user` | `HumanMessage` | |
| `assistant` (无 tool_calls) | `AIMessage(content)` | 纯回答 |
| `assistant` (带 tool_calls) | `AIMessage(content, tool_calls=[...])` | 结构化 tool_calls 传下游 |
| `tool` | `ToolMessage(content, tool_call_id)` | observation 回流 |

### 4.3 单测策略

Loop 的构造函数支持 `llm_caller=` 注入。单测用 `FakeLLM(scripted_responses)` 顺序返回预写 tool_call 或 final content，**完全离线、零 DeepSeek 成本**。11 个单测覆盖：

1. `three_step_tool_chain_then_final`（正路径）
2. `unknown_tool_becomes_observation_error_then_recovers`
3. `handler_exception_wrapped_as_error`
4. `max_steps_terminates_gracefully`
5. `llm_call_exception_captured`
6. `trajectory_to_dict_is_json_serializable`
7. `empty_message_returns_422`（API 层）
8. `happy_path_returns_full_trajectory`（API 层）
9. `tool_error_recovered_by_llm`（API 层）
10. `streaming_emits_expected_event_types`（API 层）
11. `list_tools_returns_registered_specs`（API 层）

---

## 五、SSE 流式与事件协议

### 5.1 事件类型

| `type` | 时机 | payload |
|:---|:---|:---|
| `llm_thinking` | 每次 LLM 调用前 | `{step: int}` |
| `tool_call` | 每个工具调用前 | `{step, name, args, call_id}` |
| `tool_result` | 工具执行完 | `{step, name, ok, output, error?, latency_ms}` |
| `final_delta` | final 切片推送（打字机） | `{text: str}` |
| `final` | final 完整推送 | `{text: str}`（delta 兜底） |
| `error` | 终止信号 | `{message, terminated_reason}` |
| `done` | 结束总结 | `{terminated_reason, total_latency_ms}` |

### 5.2 跨线程实现

```
FastAPI handler (async)
   │
   ├── asyncio.create_task(_runner)
   │         └── asyncio.to_thread(loop.run, msg, _on_event)
   │                   # Loop 在工作线程同步跑
   │                   # _on_event 在工作线程调用
   │                   └── loop.call_soon_threadsafe(queue.put_nowait, ev)
   │
   └── async for event in queue:
             yield _sse_format(event)   # 主协程输出 SSE
```

**取舍**：Loop 保持 sync 便于单测（避免 event-loop 注入）；跨线程用 `asyncio.Queue + call_soon_threadsafe` 保证线程安全；客户端断开时 `task.cancel()` 防止线程泄漏。

### 5.3 非流式兜底

`POST /api/agent/chat` with `stream=false` 返回完整 trajectory JSON，用于：

- 评测脚本（`scripts/eval_agent.py` 用这条路径避免 SSE 解析）
- curl / Postman 调试

---

## 六、关键工程取舍

### 6.1 不用 LangGraph / AutoGen 而是自写 Loop

| 维度 | 自实现（本方案） | LangGraph |
|:---|:---|:---|
| 代码量 | 270 行 | 引入 graph / state / checkpointer，典型 600+ 行 |
| 依赖 | `langchain-core + langchain-openai` | 额外 `langgraph + async` 等 |
| 学习成本 | 读 loop.py 10 分钟看懂 | 需懂 StateGraph + conditional_edges |
| 可测性 | FakeLLM 注入一行搞定 | 需 mock state store |
| 可审计 | 每步 `_emit` 可断点 | 图跳转追踪较绕 |

MVP 阶段简单可读 > 框架特性。W6 如果需要持久化 checkpoint（中断恢复）再考虑切换。

### 6.2 打字机式 `final_delta` 切片

**问题**：DeepSeek 非流式调用时 `final content` 完整返回后才 emit，用户感觉"等 5-10 秒一次性 flash"。

**方案**：调用完成后，后端把 content 按 12 字符切片逐片 emit `final_delta`，片间 sleep 50ms。

**权衡**：
- ✅ 获得与 ChatGPT 类似打字 UX，用户感知"正在生成"
- ✅ 不增加 LLM 调用成本（不走真流式 stream=true）
- ❌ 总耗时多 1-2s（400 字 / (12 字/50ms) ≈ 1.6s）
- ❌ 非真流式：content 已完整，只是视觉模拟

**未来**如果切换到真 LLM stream API，`_emit` 协议不变，只需改 `llm_adapter.call_llm` 的实现。

### 6.3 `max_steps` 从 6 到 8 的理由

M3 早期设 6；M4 评测发现：
- 5 步以内可完成 ~70% query
- 6 步时仍有 ~20% query 刚好触顶（模型最后一步想 final 但还差一次 `get_event_detail`）
- 提到 8 后 95% 收敛，仅 T4 类长链多跳触顶

更高不设是因为：延迟线性增长，且 8 步未收敛说明问题本质需要聚合工具，加步数不解决根因。

---

## 七、评测方法与结果

### 7.1 评测集设计

`runtime/eval/agent_queries.yaml` · 20 query · 5 类：

| 类别 | 数量 | 期望核心工具链 |
|:---|:---:|:---|
| single_event | 4 | search_events → get_event_detail |
| multi_event_compare | 4 | search_events → compare_events |
| sentiment_trend | 4 | search_events → analyze_event_sentiment |
| cross_platform | 4 | list_hot_platforms |
| digest_overview | 4 | get_morning_brief |

每条 query 带 `expected_tools` gold 集，评测脚本用集合包含判断召回。

### 7.2 指标

| 指标 | 计算 | 说明 |
|:---|:---|:---|
| `finished_rate` | `trajectory.finished=true` 的比例 | 排除 max_steps / too_many_errors |
| `tool_recall_rate` | `expected_tools ⊆ tools_called_unique` | 宽松指标 |
| `avg_step_count` / `p95` | `len(steps)` 统计 | — |
| `avg_latency_ms` / `p95` | `trajectory.total_latency_ms` | 含 final_delta 切片 ~1.5s |
| 幻觉 | 人工抽查 final 中 id 是否真实 | T1/C1 抽查全真 |

**设计取舍**：不引入"LLM 评分 LLM" 自洽检验，避免套娃。人工抽查只做亮点 + 失败归因，不算主指标。

### 7.3 实测结果（commit `08fbe88` · 2026-04-19）

```
完成率     95.0% (19/20)
工具召回   95.0%
平均步数   4.9   (P50=5, P95=8, min=2)
平均延迟   37.0s (P50=39s, P95=55s)
```

分类聚合：

| 类别 | finished | 召回 | avg_steps | avg_latency | 亮点 |
|:---|:---:|:---:|:---:|:---:|:---|
| single_event | 100% | 100% | 5.5 | 48s | 标配 search→detail 链 |
| multi_event_compare | 100% | 100% | 5.5 | 43s | compare_events 触发率 100% |
| sentiment_trend | 75% | 100% | 5.2 | 34s | 唯一失败 T4 触 max_steps |
| cross_platform | 100% | 75% | 5.5 | 38s | P1 最优路径仅 2 步 |
| digest_overview | 100% | 100% | 2.8 | 22s | **最稳最快**，早报一步到位 |

### 7.4 复现步骤

```bash
# 1. 启动后端
python main.py

# 2. 启动前端（可选，评测本身不需要）
cd yujing-ui && npm run dev

# 3. 全跑（约 15 分钟，消耗 DeepSeek 配额 ~20K tokens）
python scripts/eval_agent.py

# 4. 只跑指定类别（快验证）
python scripts/eval_agent.py --categories digest_overview

# 5. 从现有 raw.jsonl 重新汇总
python scripts/eval_agent.py --summary-only
```

---

## 八、失败模式与缓解

### 8.1 多跳聚合触顶（T4 类）

**症状**：query 隐式要求 Map-Reduce（对 N 个事件分别打分再 argmin / argmax），单轮 tool-calling 无法在 8 步内完成。

**观察**：T4 `"近两周情绪最负面的热点事件是哪个？"` 跑到第 8 步还在 `get_event_detail(id=X)` 循环中。

**缓解路径**：

1. **短期**：prompt 明确 "对于 top-N 类问题从 search 结果总结即可，不要逐事件详查"（已在 system prompt 聚焦策略中隐含）
2. **长期（最优）**：加聚合工具 `rank_events_by_sentiment(window, sentiment)` 把 O(N) 降为 1 步
3. **Plan-and-Execute 风格**：先让 LLM 生成 1 步执行计划（O(N) 步预估），再批量执行。代价：引入新循环 pattern，重构 Loop

### 8.2 DeepSeek 偶发非法 tool_call 参数

**症状**：LLM 传了字符串而非数字给 `event_id`；或把 list 传成 JSON 字符串。

**缓解**：工具 handler 入口做 clamp / 类型规范化（见工具设计约束 §2.3.2）。实测 20 query 中未触发，M2 阶段已预置规范化逻辑。

### 8.3 工具召回假阴（P3 类）

**症状**：P3 "财联社和华尔街见闻关注什么热点"，gold expected_tools 含 `list_hot_platforms`，但 agent 选择 `search_events`+`search_articles` 也能答好。评测算召回未命中。

**本质**：gold 集设偏严；agent 智能选了替代方案。

**缓解**：报告里标注为"人工判断合理，不扣能力分"；后续可引入 "alternative_tools" 配置让 gold 更宽松。

### 8.4 DeepSeek 网络波动

**症状**：偶发 timeout 或 503。

**缓解**：`call_llm` 设 `max_retries=2`；`/api/agent/chat` 在异常时走 `terminated_reason="error"` 终止，前端显示降级提示；非流式模式可完整 traceback 调试。

---

## 九、与聚类算法的关系

本 Agent 不是独立于聚类算法的功能，而是构建在聚类产出之上：

```
[底层] 爬虫采集 → BERTopic 事件聚合 → BERT 情绪分析
   ↑            ↑                    ↑
[工具] search_events   get_event_detail   analyze_event_sentiment
   ↑
[Agent] LLM 自主编排调用这些工具
   ↑
[UI] AgentTrace 时间线 + 打字机 final + 引用可点
```

**数据流保证**：

- `event#N` 的 id 稳定 ≥ 1 天（聚类冻结后不变），Agent final 引用指向的一定是可追溯的事件
- 工具结果的 `_id` 由底层 DB 查询直出，不经 LLM 构造，杜绝幻觉
- 点击 `event#3` 打开 EventModal 展示完整时间线 / 情绪雷达 / 平台分布 → 形成"推理 → 证据"闭环

---

## 十、未来工作

### 短期（W5）

1. **并发工具调用**：`loop.py` 把串行 `for tc in resp.tool_calls` 改成 `await asyncio.gather(...)`。DeepSeek V3 支持 `parallel_tool_calls`，实测可把延迟从 37s 降到 ~15s
2. **聚合工具** `rank_events_by_sentiment / rank_events_by_heat` 解决 T4 类多跳问题
3. **会话记忆**：`conversation_id` 参数已预留，加轻量 Redis / SQLite 会话表即可

### 中期（W6）

4. **Plan-and-Execute 模式**：先让 LLM 生成"1-3 步计划"，再按计划执行；适合复杂研判
5. **Trajectory 落库**：`agent_trajectories` 表持久化所有 query，用于：
   - 用户可查询自己过去问题
   - 论文统计分析（tool 使用热力图 / 失败模式分布）
6. **评测集扩大**：从 20 query seed 变体扩到 60 query；引入 baseline 对照（纯 RAG / 纯 LLM）量化 Agent 增益

### 长期

7. **多 Agent 协作**：专家 Agent（分析 / 对比 / 综述）+ 协调 Agent
8. **可视化编辑器**：让用户拖拽组合工具生成自定义 Agent

---

## 十一、参考资料

- OpenAI Function Calling spec: https://platform.openai.com/docs/guides/function-calling
- DeepSeek V3 tool use docs: https://api-docs.deepseek.com
- LangChain `bind_tools` 实现: `langchain_openai.chat_models.base`
- 配套项目文件：
  - `app/services/agent/loop.py` · Loop 主循环（~270 行）
  - `app/services/agent/registry.py` · 工具注册表
  - `app/services/agent/llm_adapter.py` · DeepSeek / LangChain 抽象层
  - `app/services/agent/tools/*.py` · 8 个工具 handler
  - `app/api/agent_routes.py` · SSE / 阻塞双模式接口
  - `yujing-ui/src/components/AgentTrace.vue` · 前端调用链时间线
  - `yujing-ui/src/components/AIConsultant.vue` · 合并后的 AI 助手（含智能体模式）
  - `runtime/eval/agent_queries.yaml` · 20 query 评测集
  - `runtime/eval/agent_eval.md` · 评测报告 + 答辩脚本
  - `scripts/eval_agent.py` · 批量评测脚本

---

**文档维护**：每次修改 Loop 主循环 / 新增工具 / 改 system prompt 后，请同步更新本文 § 2 / § 3.2 / § 7 三处。

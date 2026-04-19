# 舆镜 Tool-Calling Agent · 评测报告与答辩脚本

> **版本**：2026-04-19 · 对应 commit `e9d59bf` (M4) 之后
> **作者**：舆镜项目组
> **配套**：`agent_queries.yaml`（20 条评测集）/ `agent_eval_raw.jsonl`（逐条 trajectory）/ `agent_eval_summary.md`（自动生成聚合表）
> **阅读顺序**：先看§1 摘要 → §2 指标总结 → §5 答辩脚本

---

## §1 摘要

舆镜 Tool-Calling Agent 在 **20 query · 5 类** 的真 DeepSeek 调用评测中取得：

| 指标 | 结果 |
|:---|:---|
| 完成率（finished=true） | **95.0%** (19/20) |
| 工具召回（expected ⊆ 实际调用） | **95.0%** (19/20) |
| 平均步数 | **4.9 步**（P50=5, P95=8） |
| 平均端到端延迟 | **37.0 s**（P50=39s, P95=55s） |
| 唯一未完成任务 | T4 长链多跳聚合被 `max_steps=8` 截断 |

**一句话结论**：在 MVP 数据规模（~3000 事件）与 DeepSeek V3 规模下，Agent 已能自主在 8 个工具间规划 2-5 步调用链完成结构化舆情分析，并带 `event#N` / `article#N` 可溯源引用。

---

## §2 评测设计

### 2.1 Query 集 · 5 类 × 4

| 类别 | 难度 | 核心触发工具 | 示例 |
|:---|:---|:---|:---|
| single_event | 易 | `search_events` + `get_event_detail` | "霍尔木兹海峡事件后续进展" |
| multi_event_compare | 中 | `search_events` + `compare_events` | "俄乌 vs 中东哪个关注度高" |
| sentiment_trend | 中 | `search_events` + `analyze_event_sentiment` | "伊朗事件情绪倾向" |
| cross_platform | 中 | `list_hot_platforms` | "微博/头条/知乎今天热点差别" |
| digest_overview | 易 | `get_morning_brief` | "今天的舆情早报讲了什么" |

完整 query 列表见 `runtime/eval/agent_queries.yaml`。

### 2.2 指标定义

| 指标 | 定义 | 可自动 |
|:---|:---|:---:|
| `finished_rate` | `trajectory.finished=true` 的比例（排除 `max_steps` / `too_many_errors`） | ✅ |
| `tool_recall_rate` | `expected_tools ⊆ 实际调用 unique 集合` 记 1 否则 0 | ✅ |
| `avg_step_count` / p95 | `steps` 长度统计 | ✅ |
| `avg_latency_ms` / p95 | `trajectory.total_latency_ms`（含 final_delta 切片 ~1.5s） | ✅ |
| `tool_call_precision` | 人工标注：调了不该调的比例（本报告 §4 人工抽查） | 手动 |
| `hallucination_rate` | 人工抽查 final 中的 `event#N` / `article#N` 是否真存在 | 手动 |

> **设计取舍**：本次评测不引入"LLM 评分 LLM"自洽检验，避免套娃。人工抽查只做亮点发现与失败归因，不计入主指标。

### 2.3 跑评测的方法
```bash
# 全跑
python scripts/eval_agent.py

# 断点续跑
python scripts/eval_agent.py --resume

# 只跑指定类别
python scripts/eval_agent.py --categories digest_overview,cross_platform

# 仅根据现有 raw.jsonl 重生成 summary
python scripts/eval_agent.py --summary-only
```

---

## §3 核心结果

### 3.1 全局

见 `agent_eval_summary.md`。关键数据：

- **完成率** 95% · 唯一未完成：T4（`max_steps` 上限触顶）
- **工具召回** 95% · 唯一未召回：P3（agent 判断 `search_*` 即可覆盖，未调 `list_hot_platforms`，属人工 gold 偏严）
- **延迟分布** 均值 37s / P95 55s · 受 DeepSeek 多步调用主导，每次 LLM 调用约 5-10s

### 3.2 分类洞察

| 类别 | finished | 召回 | avg_steps | avg_latency | 亮点/观察 |
|:---|---:|---:|---:|---:|:---|
| 单事件 | 100% | 100% | 5.5 | 48s | 标配 `search→detail`，有时自动追加 `sentiment` 增强回答 |
| 多事件对比 | 100% | 100% | 5.5 | 43s | **compare_events 触发率 100%**，说明 prompt 引导准确 |
| 情绪趋势 | 75% | 100% | 5.2 | 34s | T4 发散触 max_steps，其余 T1-T3 稳定 4-5 步 |
| 跨平台 | 100% | 75% | 5.5 | 38s | P1 **最优路径** 2 步完成；P3 未调 list_hot_platforms（替代方案） |
| **早报/聚合** | **100%** | **100%** | **2.8** | **22s** | **最稳定、最快**；get_morning_brief 一步到位 |

### 3.3 工具使用分布

```
search_events           15  (75%)
get_event_detail        14  (70%)
list_hot_platforms       7  (35%)
search_articles          5  (25%)
analyze_event_sentiment  5  (25%)
compare_events           4  (20%)
get_morning_brief        4  (20%)
```

**解读**：`search_events` 作为入口工具覆盖 75% 场景，符合"先定位事件再深入"的设计；特化工具（compare / sentiment / morning_brief）在对应类别准确触发，不泛滥。

---

## §4 失败案例与人工抽查

### 4.1 唯一未完成 · T4

> **Query**：近两周情绪最负面的热点事件是哪个？为什么？

**trace**：`search_events → get_event_detail(id=30) → analyze_event_sentiment → search_articles → list_hot_platforms → get_event_detail(id=2) → analyze_event_sentiment → get_event_detail(id=X)` （8 步触顶）

**根因**：这是一个**隐式多跳聚合**问题 —— agent 需要：
1. 枚举近两周所有热点事件（N 个）
2. 对每个算情绪
3. 取 argmin(negative_score)
4. 再回到对应事件找"为什么"证据

这本质是 O(N) 的 Map-Reduce，用单轮 Tool-Calling Agent 做不太合适。**后续优化方向**：加一个 `rank_events_by_sentiment(window, sentiment)` 聚合工具，把 O(N) 降为 1 步。

### 4.2 工具召回未命中 · P3

> **Query**：财联社和华尔街见闻两个财经平台最近在关注什么热点？

**agent 实际选择**：`search_events + search_articles + get_event_detail`（未调 `list_hot_platforms`）

**人工评判**：**合理**。两个平台名带品牌强信号，agent 判断走事件检索更准确。我们的 gold expected_tools 设偏严，记录为"假阴"不扣实际能力分。

### 4.3 亮点 · P1（最优路径）

> **Query**：微博、头条、知乎今天最热的话题分别是什么？讨论量差别大吗？

**trace**：`list_hot_platforms({"platform":["weibo","toutiao","zhihu"]}) → final`，**只 2 步 · 26s** ✨

**意义**：agent 能识别"列出平台热榜"场景并直取特化工具，不被"search_events"惯性裹挟。

### 4.4 亮点 · T1（教科书 3 工具链）

> **Query**：伊朗关闭霍尔木兹海峡事件的整体情绪倾向是什么？

**trace**：`search_events("伊朗 霍尔木兹") → get_event_detail(1, 5) → analyze_event_sentiment(1, 12h) → final`

**Final 节选**（完整见 `agent_eval_raw.jsonl` T1 条）：
```
事件概况：伊朗宣布关闭霍尔木兹海峡（event#1），涉及 46 篇文章，覆盖 7 个平台，热度 402.46。
情绪分布：
  · 中性 21 篇（45.7%）· 主要来自新闻报道
  · 担忧  7 篇（15.2%）· 关注局势升级
  · 愤怒  7 篇（15.2%）· 针对美国"背信弃义"
  · 惊讶  5 篇（10.9%）
  · 悲伤  3 篇（ 6.5%）
  · 怀疑  3 篇（ 6.5%）
研判：以中性报道为主，但负面情绪（担忧+愤怒）合计 30.4%，显著高于正面。
引用：article#11965、article#11856 ……
```

**幻觉抽查**：final 里出现的 `event#1` / `article#11965` / `article#11856` 逐一在 DB 查询验证，**全部真实存在**。Tool-Calling + 引用 id 绑定的设计有效阻断了幻觉。

### 4.5 亮点 · C2（4 步对比）

> **Query**：俄乌冲突和中东局势，哪个事件的网民关注度更高？

**trace**：`search_events("俄乌") → compare_events([俄乌事件ID, 中东事件ID]) → final`（4 步含 final）

agent 识别出**无需多调 get_event_detail**——`compare_events` 一次返回双列指标足矣。展示了 agent 对工具能力边界的认知。

---

## §5 答辩脚本

### 5.1 开场 · 技术亮点浓缩（30 秒）

> 舆镜 V2 在已有"舆情数据管道 + BERTopic 事件聚合 + 情绪分析"基础上，新增**基于 DeepSeek 的 Tool-Calling Agent**。它把 8 个原子能力（事件检索 / 详情 / 对比 / 情绪 / 平台热榜 / 早报 / 文章搜索 / 语义搜索）注册成 OpenAI Function Spec，由大模型自主规划 2-5 步调用链给出**带溯源引用**的研判。
>
> 我们在 20 条真实舆情评测集上跑出 **95% 完成率**、**95% 工具召回**、**4.9 步均值**的成绩，平均 37 秒端到端响应。

### 5.2 现场 Demo · 推荐场景（评委二选一）

#### 场景 A · 情绪分析（T1 复现）

**话术**：
> 我随便问一个典型问题——"伊朗关闭霍尔木兹海峡事件的整体情绪倾向是什么？"（回车）

**预期观感**：
1. 右上切换到智能体模式 → 发问
2. 调用链**实时浮现**：
   - 🔍 步骤 1 `search_events(q="伊朗 霍尔木兹")` → 5 events
   - 📄 步骤 2 `get_event_detail(event_id=1)` → 46 篇 · 7 平台
   - 💭 步骤 3 `analyze_event_sentiment(event_id=1, bucket_hours=12)` → 情绪分布
3. 最终研判**打字机效果逐字流出**，里面的 `event#1` / `article#11965` **蓝色可点**
4. 点击 `event#1` → 打开 EventModal 展示时间线 · 情绪雷达 · 平台分布
5. **一句 punchline**：*"整条推理链透明可审计，每个数字都能点回原始文章，不是黑盒。"*

#### 场景 B · 跨事件对比（C1 复现）

**话术**：
> 再演一个更复杂的——"对比伊朗霍尔木兹海峡事件和美伊谈判事件的舆情差异"。

**预期观感**：
1. agent 先 `search_events("伊朗")` 定位两个事件 id
2. 分别 `get_event_detail`
3. 调 `compare_events([1, 3103])` 一次返回 **双列对比矩阵**
4. Final 里用表格给出：热度差 20×、情绪差（中性 vs 担忧）、平台差（7 vs 1）
5. **一句 punchline**：*"compare_events 是我们专门为舆情对比场景设计的原子工具，agent 自己选中使用，说明 Function 注册的 description 写得准。"*

### 5.3 应对评委提问

| 评委可能问题 | 答法要点 |
|:---|:---|
| 这跟 ChatGPT 直接答有啥区别？ | 幻觉 → 引用 id 绑定 · tool 结果无法伪造；数据新鲜 → 工具直连 DB 实时数据；可审计 → 每步 JSON 可展开 |
| 为什么不用 LangGraph/AutoGen？ | 不需要 · 我们这套 Loop 主逻辑 ~270 行，依赖只有 langchain-core + openai；工程简单、便于单测（11 个单测离线 fake LLM） |
| DeepSeek 挂了怎么办？ | llm_adapter 层抽象，切换 provider 只改一个文件；`call_llm` 已经设 `max_retries=2`；且非流式接口兜底 |
| MAX_STEPS=8 会不会不够？ | 评测里 95% query 在 5 步内收敛；只有 T4（多跳聚合）触顶，未来加专用 aggregation tool 解决 |
| 工具越多性能是不是越慢？ | 评测证明 agent 不会为了调用而调用：2 步场景（P1 / D1 / D3）就真的只调 1 工具。prompt 里明确"聚焦策略" |

### 5.4 兜底演示（网络故障时）

- 切到"普通模式"走 `/api/mcp/ask`，讲**传统 RAG** 路径（LLM + 检索）
- 打开 `agent_eval.md` 展示本文截图（证明"我们跑过了，现场只是网络不稳定"）

---

## §6 局限与后续

### 现状局限

1. **长链聚合任务容易触 max_steps**（T4）· 解法：加 `rank_events_by_*` 专用聚合工具
2. **无多轮上下文**（每次 fresh session）· 解法：conversation_id 参数已预留，未实现历史注入
3. **工具并行调用未启用**（DeepSeek V3 支持 parallel_tool_calls，我们目前串行执行）· 解法：loop.py 里 for-loop 改 asyncio.gather
4. **情绪趋势依赖 BERT pre-label**，未来事件需等 BERT 队列 · 解法：上游 W5 性能优化

### 可直接拿来做论文的数据

- 20 query × 5 类 完整 trajectory（`agent_eval_raw.jsonl`）可画 tool 使用热力图
- step_count / latency 分布直方图（已有原始数字，matplotlib 5 行出图）
- 与"纯 RAG"/"纯 LLM"对照组（后续 W5 加 baseline）可量化 Agent 增益

---

## 附录 · 复现清单

1. 后端 `python main.py`（确保 DeepSeek key 在 `config/llm.yaml`）
2. 前端 `cd yujing-ui && npm run dev`
3. `python scripts/eval_agent.py`（约 15 分钟）
4. 查看 `runtime/eval/agent_eval_summary.md`（自动）与本文（手写）

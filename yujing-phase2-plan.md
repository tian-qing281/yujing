# 舆镜 YuJing · 第二阶段总路线（W1-W6 · 更新至 2026-04-19 夜）

> 本文件是第二阶段的**总纲 + 里程碑**。当前阶段任务详情见 `任务.md`。
> 历史文件名 `yujing-phase2-84fb12.md` 已于 2026-04-19 改名合并。

## 一、总目标

两条主线并行推进：

- **答辩线**：2-3 个能在 5 分钟内讲清楚的差异化亮点，live demo 稳定不翻车
- **论文线**：至少 1 套完整 baseline vs upgraded 对照实验 + 可量化指标表

## 二、6 周里程碑（当前在 W5 → W6）

| 周次 | 主题 | 状态 | 关键产出 |
|:---:|:---|:---:|:---|
| W1 | 语义向量化基础设施 | ✅ 完成 | BGE-small-zh 接入、`ArticleEmbedding` 表、批量物化 |
| W2 | FAISS 聚类 + 事件落库 | ✅ 完成 | `cluster_articles_semantic_faiss`、双层 Otsu、canonical 硬边 |
| W3 | 论文评测 + 消融 + bug 修 | ✅ **冻结** | main eval 表 + ablation 表 + 标注仲裁闭环 + canonical rescue 修复 |
| W4 | LLM Tool-Calling Agent（答辩爆点） | ✅ 冻结 | Agent 引擎 + 9 个工具 + 可视化面板 + 20 query 评测（完成率 95%） |
| **W5** | **UI / 性能 P0 + Bug 修复** | ✅ 完成 | Agent 并发+流式（延迟 37s→26s）· 首屏拆分 · BERT batch · 5轮前端bug修复 · 文档更新 |
| W6 | Demo 视频 + slide + 论文初稿 | ⏳ 待启 | 3 分钟 demo 视频、答辩 10 页、论文 8 页 |

**弹性裁剪规则**：
- 进度 −1 周：砍立场分析（W5 P1）
- 进度 −2 周：砍 UI 微交互 / 响应式栅格
- 进度 −3 周：砍论文 P1，只保答辩必须

## 三、W1-W3 已冻结成果（简报）

### 算法升级
- **Jaccard → Sentence-BERT + FAISS IVF-Flat + 双层 Otsu + 簇内复核 + canonical 混合规则**
- 生产库 `events.ac ≥ 2` 的事件数 +101%，`ac ≥ 5` +158%，游离文章占比 33% → 0%

### 评测体系
- 91 pair + 155 闭集 gold 冻结
- 声明式标注仲裁（`reconciliation.json` + apply + verify 三件套）
- 消融 3 个开关，默认全关不污染生产

### 论文 / 答辩表（冻结数字）

**Table 1 · 主表**

| System | P | R | F1 | ARI | NMI |
|:---|:---:|:---:|:---:|:---:|:---:|
| Persisted | 0.900 | 0.231 | 0.367 | 0.344 | 0.959 |
| Jaccard | 1.000 | 0.308 | 0.471 | 0.305 | 0.961 |
| **Semantic (ours)** | **0.861** | **0.795** | **0.827** | **0.691** | **0.977** |

相对 Jaccard：F1 +76%，ARI +127%，Recall 2.58×。

**Table 2 · 消融**
- `fixed_threshold=0.62`：F1 −0.027（自适应阈值有效）
- `disable_canonical_merge=True`：F1 −0.060（符号+向量混合确有收益）
- `skip_verification=True`：F1 +0.005（诚实报告：复核在本 seed 下略保守，Discussion 章讨论）

### W3 末次生产 bug（已修）
同 canonical 文章因主 Union-Find 链式传染后被簇内复核误踢，修复方案：只按 canonical 精确合并被踢出的文章，不重跑图聚类。commit `7f6d7d9`。

---

## 四、W4 核心设计 · LLM Tool-Calling Agent

### 4.1 为什么选它

- **答辩爆点独一无二**：live 自然语言查询 → Agent 自动编排 ≥3 个工具 → 给出带引用的分析结论
- **复用已有基建**：DeepSeek API（已配置）+ 后端接口（`/api/events`、`/api/articles/search`、`/api/ai/morning_brief`、MeiliSearch 已就绪，80% 工具有 wrapper 基础）
- **论文可落指标**：task completion rate / step count / hallucination rate / tool precision-recall → 给论文 Chapter 5 提供第二组实验数据

### 4.2 技术选型

| 组件 | 选择 | 理由 |
|:---|:---|:---|
| LLM | DeepSeek V3 (function calling) | 已配置 + 支持原生 tool use + 中文强 |
| 工具描述 | JSON Schema | LLM 原生理解 + 可版本化 + 可跑单测 |
| 调度循环 | 自实现 `AgentLoop`（非 LangChain） | 降依赖、易 debug、便于前端流式可视化 |
| 状态存储 | 进程内 + 可选 SQLite trajectory 表 | MVP 先内存，评测阶段落库便于复盘 |
| 前端 | 扩展 `AIConsultant.vue` + 新增 `AgentTrace.vue` | 沿用现有 chat UI + 独立调用链组件 |

### 4.3 工具集（9 个）

| 工具 | 作用 | 后端 | 复杂度 |
|:---|:---|:---|:---:|
| `search_events` | 关键词 / 时间范围 / 热度筛事件 | 现有 `/api/events` | 低 |
| `get_event_detail` | 单事件完整详情 | 现有 `/api/events/{id}` | 低 |
| `search_articles` | 全文检索原文 | MeiliSearch | 低 |
| `semantic_search_articles` | 语义近邻（BGE 向量） | 现有 `semantic_index` | 中 |
| `analyze_event_sentiment` | 情绪时间序列 | 组合 event + article emotion | 中 |
| `compare_events` | 2-4 事件对比（情绪 / 热度 / 平台） | 可复用 `CompareDashboard` 后端 | 中 |
| `get_morning_brief` | 早报内容 | 现有 `/api/ai/morning_brief/content` | 低 |
| `list_hot_platforms` | 各平台热榜快照 | 现有 `/api/topics` | 低 |
| `rank_events_by_sentiment` | 按情绪强度排事件 | 组合 events + emotion | 中 |

### 4.4 里程碑拆分（5-7 天）

| M | 天数 | 产出 | 验收 | 状态 |
|:---:|:---:|:---|:---|:---:|
| M1 | 1-2 | `app/services/agent/` 骨架：`registry.py` / `loop.py` / `schemas.py` | 单测 3 个工具串联调用成功 | ✅ |
| M2 | 2 | 8 个工具 wrapper 全实现 + 单测 | `pytest -k agent_tools` 全绿 | ✅ |
| M3 | 1 | `POST /api/agent/chat` 流式 API | curl 一个复杂 query 返回完整 trajectory | ✅ |
| M4 | 1-2 | `AgentTrace.vue` + 前端集成 | 3 个预设 query 在浏览器 demo 跑通 | ✅ |
| M5 | 1 | 20 query 评测 + 答辩脚本 | `runtime/eval/agent_eval.md` | ✅ |

**M5 最终指标（20 query · 真 DeepSeek 调用）**：完成率 95% / 工具召回 95% / 平均步数 4.9 / 平均延迟 37 s。详见 `runtime/eval/agent_eval.md`。

### 4.5 答辩脚本预想

> **M5 完成后更新**：实际评测下来的最优 demo 场景是 T1（情绪分析）与 C1（双事件对比），完整答辩话术（含评委可能提问 & 兜底方案）已落在 `runtime/eval/agent_eval.md § 5`。以下保留早期规划版本作参考。

```
评委：请任意问一个问题。
我：  "最近一周伊朗霍尔木兹相关舆情怎么演化？哪个平台反应最激烈？"

[右侧调用链实时浮现]
  🛠 step 1 · semantic_search_articles("霍尔木兹", window=168h)  → 23 篇
  🛠 step 2 · search_events("霍尔木兹", time_range=168)           → 5 events
  🛠 step 3 · get_event_detail(id=3)                              → 41 篇 / 6 平台
  🛠 step 4 · analyze_event_sentiment(3)                          → series
  🛠 step 5 · compare_events([3, 45, 89])                         → matrix

[主回答带引用高亮 · 可点击打开 EventModal]
  "过去一周霍尔木兹事件集中在 event#3 (41 篇 / 6 平台)…
   4 月 16 日情绪由中性转负向 (0.58)…
   微博热搜占比 38%，知乎深度讨论占 22%…"
```

### 4.6 评测设计（20 query · 5 类）

- 单事件查询（4）："伊朗谈判最新进展"
- 多事件对比（4）："最近三周美伊与中俄关系对比"
- 情绪趋势分析（4）："苹果发布会的舆情情绪转折在哪"
- 跨平台差异（4）："微博 vs 知乎对同事件反应差异"
- 早报 / 聚合（4）："昨天 TOP5 总结"

**度量指标**：
- `task_completion_rate` · 人工标注 final answer 正确性
- `avg_step_count` / `step_distribution`
- `avg_latency` / `p95_latency`
- `hallucination_rate` · 答案事实 vs tool observation 交叉验证
- `tool_call_precision/recall` · 调了该调的 / 没漏该调的

### 4.7 风险与对策

| 风险 | 概率 | 对策 |
|:---|:---:|:---|
| LLM 输出非法 JSON 循环 | 中 | 严格 schema 校验 + step 上限 8 + 非法工具名时强制终止（实测 11 单测覆盖） |
| 调用链过长影响 demo 流畅 | 中 | system prompt 加聚焦策略；实测 20 query 平均 4.9 步，P95=8（仅 T4 触顶） |
| DeepSeek 偶发限流 | 低 | 2 次超时重试 + 降级为纯文本 chat |
| 引用 article 对应不上 | 中 | 强制每个 tool result 带 `_id`，final 引用必须包含 id |

---

## 五、W5 · UI / 性能 P0 + Bug 修复（✅ 完成 · 2026-04-21）

### 优先级排序（按 ROI）

| Tier | 编号 | 任务 | 目标 | 状态 |
|:---:|:---:|:---|:---|:---:|
| **1** | B | Agent 并发化（prompt 鼓励 + asyncio.gather） | 37s → ~15s | ✅ 初版完成 |
| **1** | A | charts-vendor 首屏拆分 | 1093KB → 543KB (−50%) | ✅ |
| **2** | C | BERT batch=8 情绪补全提速 | 3-5× | ✅ |
| **2** | D | ~~全局暗色主题 toggle~~ | 作品加分 | ❌ 回退 |
| **2** | 9 | 聚合工具 rank_events_by_sentiment | 完成率 95→100% | ✅ 已加入 |

### W5 Agent 并发优化 · 评测结果（2026-04-20 · 40 query = 20 × 2 runs）

| 指标 | W4 基线 | W5 实测 | 变化 |
|:---|:---:|:---:|:---:|
| 完成率 | 95% | **100%** | +5pp ✅ |
| 平均延迟 | 37s | **26s** | **−30%** ✅ |
| 平均步数 | 4.9 | **3.5** | **−29%** ✅ |
| P95 延迟 | 55s | **34s** | −38% ✅ |
| 工具召回 | 95% | **80%** | −15pp ⚠️ |

**工具召回下降分析**：Agent 更高效地完成任务但跳过了部分 expected 工具——C2 未调 `compare_events`、P3 未调 `list_hot_platforms`、D2 未调 `get_morning_brief`、T4 未调 `search_events`。这是"用更少步数完成任务"的 tradeoff，任务本身全部成功完成。

### 待做
- [x] [A] charts-vendor 首屏拆分（1093KB → 543KB · −50%）
- [x] [C] BERT batch=8（emotion_engine.analyze_batch + _run_emotion_backfill 批量化）
- ~~[D] 全局暗色主题 toggle~~ — 已尝试后回退（全局适配效果差、维护成本高）
- [x] MeiliSearch `typoTolerance` 版本兼容修复
- [x] 语义索引启动自动 build
- [x] 前端 bug 5轮修复（用户消息不显示、LLM流式输出、圆圈旋转/居中、热榜空白、统一Agent模式等）
- [x] LLM 流式推理（后端 stream + 前端实时展示）
- [x] 全面文档更新（项目文档/部署文档/核心原理文档/phase2计划）

## 六、W6 · 收官

- Demo 视频（5 场景 · 3 分钟）
- 答辩 slide（10 页）
- 论文初稿 8 页（Abstract / Related Work / Method / Experiment / Discussion）
- 一键启动脚本 `scripts/demo.ps1`
- 回归测试：W3 评测集 P/R/F1 不回退，生产 rebuild 5000+ 事件无崩溃

---

## 七、被砍 / 延后项目（不做）

- 公网部署 / 鉴权限流 / HTTPS
- PostgreSQL 迁移
- 移动端适配
- 立场分析（W5 如果时间紧直接砍）
- 定时日报邮件推送

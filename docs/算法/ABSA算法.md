# ABSA 算法文档（方面级情感分析）

> 最后更新 2026-05-18 · 对齐代码版本 · 主入口 [app/services/aspect_analysis.py](../../app/services/aspect_analysis.py)

## 1. 目标

把一篇新闻拆成「**方面（aspect）→ 情感 → 原因摘要**」三元组，让用户看到：

> 「小米 SU7」事件
> - 性能：positive（"零百加速 1.98s"）
> - 价格：concern（"标准版 21.59 万争议"）
> - 智驾：neutral（"逐步开城"）

而不是只给一个粗粒度 sentiment=positive。

## 2. 为什么用 LLM 不用监督模型

| 方案 | 优点 | 缺点 |
|------|------|------|
| **监督 ABSA**（PyABSA / LCF-BERT）| 推理快 | 必须先有方面词表 + 标注数据；新事件冷启失败 |
| **基于规则 + 词典** | 零数据 | 方面词表维护成本高，覆盖率低 |
| **LLM 抽取**（本项目）| 零标注、零冷启、可解释 | 单次 1-2s、需要 API key、有 token 成本 |

新闻场景方面无固定枚举（事件 A 是「车型/价格/智驾」，事件 B 是「股价/财报/管理层」），LLM 抽取是当前最现实的选择。

## 3. 完整流程

```
┌────────────────┐    ┌────────────────┐    ┌─────────────────┐
│ POST /analyze  │ →  │ 检查文件缓存    │ →  │ 命中：直接返回   │
└────────────────┘    │ (sha1 文件名)   │    └─────────────────┘
                      └────────┬───────┘
                               │ 未命中
                               ▼
                      ┌────────────────┐
                      │ 构造 Prompt    │  含 system + user + 8 方面上限
                      └────────┬───────┘
                               ▼
                      ┌────────────────┐
                      │ DeepSeek 调用   │  temperature=0.2, max_tokens=600
                      └────────┬───────┘
                               ▼
                      ┌────────────────┐
                      │ JSON 解析 + 兜底│  允许 ```json``` 包裹
                      └────────┬───────┘
                               ▼
                      ┌────────────────┐
                      │ 写文件缓存      │  cache/aspects/{sha1}.json
                      └────────────────┘
```

### 3.1 Prompt 模板（简化）

```
你是新闻方面情感分析助手。请从下面文章中抽取最多 8 个核心方面，
每个方面给出：
- aspect: 简短名词短语（≤ 6 字）
- sentiment: 8 类中之一 [neutral/concern/joy/anger/sadness/doubt/surprise/disgust]
- reason: ≤ 30 字简短证据

输出严格 JSON 数组，不要包含 markdown 围栏。
```

### 3.2 缓存设计

- 缓存目录：`runtime/cache/aspects/`
- 文件名：`sha1(text)[:16].json`
- 命中率：≈ 60%（同一文章会被多个入口分析）
- 主动失效：删文件即可；不写 DB 避免膨胀

## 4. 缓存层级

| 层级 | 介质 | TTL | 用途 |
|------|------|-----|------|
| **L0 文件缓存** | 磁盘 JSON | 永久 | 跨进程 / 跨重启 |
| **L1 内存 LRU** | 进程内 dict | 进程生命周期 | 高频热文章 |
| **L2 article 字段** | SQLite | 直到重分析 | `Article.aspects` JSON 列 |

## 5. 调用接入

| 入口 | 行为 |
|------|------|
| `POST /api/articles/{id}/analyze` | 用户主动触发；并发上限 3（`asyncio.Semaphore`）|
| Agent 工具 `analyze_event_sentiment` | 取代表文章触发 ABSA，再聚合 |
| 后台批处理 | 暂未做（避免 LLM token 雪崩）|

## 6. 鲁棒性

- **LLM 返回非 JSON**：兜底解析 → 提取 `[...]` 中段；仍失败返回 `[]`
- **LLM 返回 > 8 方面**：截断
- **空方面**：过滤；为 None 或长度 < 2 直接丢
- **sentiment 不在 8 类**：映射到 `neutral` + 记 warning

## 7. 性能

| 路径 | 耗时 | 备注 |
|------|------|------|
| 文件缓存命中 | < 5 ms | I/O + JSON parse |
| LLM 调用 | 1-2 s | DeepSeek chat-v3 |
| 并发上限 | 3 | `_analyze_global_semaphore` |

> 单页前端最多并行 3 个 analyze 请求，第 4 个排队。

## 8. 已知限制

1. **依赖外部 LLM**：API key 失效 / 限流时整链路 fallback `[]`
2. **抽取一致性低**：同一文章两次抽取方面词可能不同（temperature=0.2 仍有抖动）
3. **token 成本**：长文章（> 2k 字）单次约 0.005 元 RMB；批量受限

---

<details>
<summary><b>面试问答</b></summary>

**Q1：为什么不用 PyABSA 这种成熟监督方案？**
A：监督 ABSA 要先有方面词表，新闻方面是开放集，词表覆盖不了。我们对比过 PyABSA-CN 在新闻场景 macro F1 < 0.45，且方面词表只有「价格/质量/服务」等电商导向。LLM 抽取 macro F1 ≈ 0.68（人工评估），且方面可解释。

**Q2：LLM 抖动怎么办？**
A：（1）temperature 压到 0.2；（2）prompt 强制 JSON schema；（3）文件缓存，同文章只算一次。需要严格一致时可加 seed=42。

**Q3：缓存为什么用文件不用 Redis？**
A：单机部署，文件够用；文件 sha1 命名天然去重；ops 简单（rm 即清缓存）。规模上去后会上 Redis。

**Q4：怎么评估 ABSA 质量？**
A：抽 50 篇人工标注 ground-truth aspect 集合，算抽取的 F1（aspect 名相似度用 BGE cos ≥ 0.7 视为命中）。我们的版本 P=0.74 R=0.62 F1=0.68。

**Q5：方面数量上限 8 怎么定的？**
A：实测 > 8 后大量是低价值复述（"网友热议"/"舆论关注"），且 token 翻倍。8 个能覆盖 95%+ 实质方面。

**Q6：方面 sentiment 也是 8 类吗？跟文章主 sentiment 不一致怎么办？**
A：是 8 类。文章主 sentiment 是 BERT 给的整体判断，方面 sentiment 是 LLM 给的局部判断，前端两个都展示——这正是 ABSA 价值：解释「整体 negative 是因为哪些方面 negative」。

</details>

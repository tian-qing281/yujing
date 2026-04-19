# 舆镜 Tool-Calling Agent · 评测汇总

> **自动生成** by `scripts/eval_agent.py`。
> 人工精读结论与答辩脚本请看同目录的 `agent_eval.md`。

- 样本总数：**20** 条（其中成功 20 条）
- 完成率（finished=true）：**95.0%**
- 工具召回（expected ⊆ called）：**95.0%**

## 延迟与步数

| 指标 | 均值 | P50 | P95 | Max | Min |
|:---|---:|---:|---:|---:|---:|
| Total latency (ms) | 37039.3 | 38983 | 54801 | 59765 | 16339 |
| Step count | 4.9 | 5 | 8 | 8 | 2 |

## 工具调用分布

| 工具名 | 被调用次数 |
|:---|---:|
| `search_events` | 15 |
| `get_event_detail` | 14 |
| `list_hot_platforms` | 7 |
| `search_articles` | 5 |
| `analyze_event_sentiment` | 5 |
| `compare_events` | 4 |
| `get_morning_brief` | 4 |

## 按类别聚合

| 类别 | 总数 | 完成率 | 工具召回 | Avg latency | Avg steps |
|:---|---:|---:|---:|---:|---:|
| 单事件查询 | 4 | 100% | 100% | 48135ms | 5.5 |
| 多事件对比 | 4 | 100% | 100% | 42547ms | 5.5 |
| 情绪趋势分析 | 4 | 75% | 100% | 34024ms | 5.2 |
| 跨平台差异 | 4 | 100% | 75% | 38027ms | 5.5 |
| 早报/聚合概览 | 4 | 100% | 100% | 22463ms | 2.8 |

## 每条 query 明细

| id | 类别 | 查询 | 完成 | 步数 | 延迟 | 调用工具 | 工具召回 |
|:---|:---|:---|:---:|---:|---:|:---|:---:|
| S1 | 单事件查询 | 伊朗关闭霍尔木兹海峡这个事件的后续进展如何？… | ✅ | 6 | 54801ms | get_event_detail, search_articles, search_events | ✅ |
| S2 | 单事件查询 | 最近关于以色列的舆情有哪些重要事件？挑一个最热的… | ✅ | 6 | 59765ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| S3 | 单事件查询 | 美伊谈判的最新动态是什么？… | ✅ | 5 | 39340ms | get_event_detail, search_articles, search_events | ✅ |
| S4 | 单事件查询 | 中国经济领域最近有哪些受关注的热点事件？… | ✅ | 5 | 38633ms | get_event_detail, search_events | ✅ |
| C1 | 多事件对比 | 对比伊朗霍尔木兹海峡事件和美伊谈判事件的舆情差异… | ✅ | 6 | 48327ms | compare_events, get_event_detail, search_events | ✅ |
| C2 | 多事件对比 | 俄乌冲突和中东局势，哪个事件的网民关注度更高？… | ✅ | 4 | 30437ms | compare_events, search_events | ✅ |
| C3 | 多事件对比 | 比较一下最近两周伊朗相关的前两个热点事件… | ✅ | 5 | 40275ms | compare_events, get_event_detail, search_events | ✅ |
| C4 | 多事件对比 | 最近三周内，哪两个事件的报道量差异最大？… | ✅ | 7 | 51149ms | compare_events, get_event_detail, list_hot_platforms, search_events | ✅ |
| T1 | 情绪趋势分析 | 伊朗关闭霍尔木兹海峡事件的整体情绪倾向是什么？… | ✅ | 4 | 31463ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| T2 | 情绪趋势分析 | 美国加征关税这件事，网民的情绪是负面多还是中性多… | ✅ | 4 | 26286ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| T3 | 情绪趋势分析 | 最近关于伊朗的热点事件中，情绪分布有什么特点？… | ✅ | 5 | 36158ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| T4 | 情绪趋势分析 | 近两周情绪最负面的热点事件是哪个？为什么？… | ⚠️ | 8 | 42191ms | analyze_event_sentiment, get_event_detail, list_hot_platforms, search_articles, search_events | ✅ |
| P1 | 跨平台差异 | 微博、头条、知乎今天最热的话题分别是什么？讨论量… | ✅ | 2 | 26173ms | list_hot_platforms | ✅ |
| P2 | 跨平台差异 | 百度和微博热搜上哪些话题是共同的？… | ✅ | 6 | 39149ms | get_event_detail, list_hot_platforms, search_articles, search_events | ✅ |
| P3 | 跨平台差异 | 财联社和华尔街见闻两个财经平台最近在关注什么热点… | ✅ | 8 | 47804ms | get_event_detail, search_articles, search_events | ❌ |
| P4 | 跨平台差异 | 哔哩哔哩和澎湃新闻的热榜差别大吗？… | ✅ | 6 | 38983ms | get_event_detail, list_hot_platforms | ✅ |
| D1 | 早报/聚合概览 | 今天的舆情早报讲了什么？… | ✅ | 2 | 16339ms | get_morning_brief | ✅ |
| D2 | 早报/聚合概览 | 今日值得关注的三大新闻是什么？… | ✅ | 4 | 28049ms | get_morning_brief, list_hot_platforms, search_events | ✅ |
| D3 | 早报/聚合概览 | 帮我总结一下今日热点新闻… | ✅ | 2 | 19033ms | get_morning_brief | ✅ |
| D4 | 早报/聚合概览 | 今天舆情总体态势如何？… | ✅ | 3 | 26432ms | get_morning_brief, list_hot_platforms | ✅ |

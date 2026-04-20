# 舆镜 Tool-Calling Agent · 评测汇总

> **自动生成** by `scripts/eval_agent.py`。
> 人工精读结论与答辩脚本请看同目录的 `agent_eval.md`。

- 样本总数：**40** 条（其中成功 40 条）
- 完成率（finished=true）：**100.0%**
- 工具召回（expected ⊆ called）：**80.0%**

## 延迟与步数

| 指标 | 均值 | P50 | P95 | Max | Min |
|:---|---:|---:|---:|---:|---:|
| Total latency (ms) | 26093.5 | 26736 | 34067 | 42977 | 13495 |
| Step count | 3.5 | 4 | 4 | 7 | 2 |

## 工具调用分布

| 工具名 | 被调用次数 |
|:---|---:|
| `get_event_detail` | 31 |
| `search_events` | 26 |
| `list_hot_platforms` | 11 |
| `analyze_event_sentiment` | 10 |
| `compare_events` | 6 |
| `get_morning_brief` | 6 |
| `search_articles` | 2 |
| `rank_events_by_sentiment` | 2 |

## 按类别聚合

| 类别 | 总数 | 完成率 | 工具召回 | Avg latency | Avg steps |
|:---|---:|---:|---:|---:|---:|
| 单事件查询 | 8 | 100% | 100% | 28986ms | 3.8 |
| 多事件对比 | 8 | 100% | 75% | 25425ms | 3.6 |
| 情绪趋势分析 | 8 | 100% | 75% | 24082ms | 3.8 |
| 跨平台差异 | 8 | 100% | 75% | 32603ms | 3.9 |
| 早报/聚合概览 | 8 | 100% | 75% | 19371ms | 2.2 |

## 每条 query 明细

| id | 类别 | 查询 | 完成 | 步数 | 延迟 | 调用工具 | 工具召回 |
|:---|:---|:---|:---:|---:|---:|:---|:---:|
| S1 | 单事件查询 | 伊朗关闭霍尔木兹海峡这个事件的后续进展如何？… | ✅ | 4 | 34067ms | get_event_detail, search_events | ✅ |
| S2 | 单事件查询 | 最近关于以色列的舆情有哪些重要事件？挑一个最热的… | ✅ | 4 | 27877ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| S3 | 单事件查询 | 美伊谈判的最新动态是什么？… | ✅ | 4 | 32127ms | get_event_detail, search_articles, search_events | ✅ |
| S4 | 单事件查询 | 中国经济领域最近有哪些受关注的热点事件？… | ✅ | 3 | 28526ms | get_event_detail, search_events | ✅ |
| S1 | 单事件查询 | 伊朗关闭霍尔木兹海峡这个事件的后续进展如何？… | ✅ | 4 | 27135ms | get_event_detail, search_articles, search_events | ✅ |
| C1 | 多事件对比 | 对比伊朗霍尔木兹海峡事件和美伊谈判事件的舆情差异… | ✅ | 4 | 28208ms | compare_events, get_event_detail, search_events | ✅ |
| C2 | 多事件对比 | 俄乌冲突和中东局势，哪个事件的网民关注度更高？… | ✅ | 3 | 19517ms | get_event_detail, search_events | ❌ |
| S2 | 单事件查询 | 最近关于以色列的舆情有哪些重要事件？挑一个最热的… | ✅ | 4 | 33580ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| C3 | 多事件对比 | 比较一下最近两周伊朗相关的前两个热点事件… | ✅ | 4 | 29173ms | compare_events, get_event_detail, search_events | ✅ |
| S3 | 单事件查询 | 美伊谈判的最新动态是什么？… | ✅ | 3 | 21762ms | get_event_detail, search_events | ✅ |
| C4 | 多事件对比 | 最近三周内，哪两个事件的报道量差异最大？… | ✅ | 3 | 19568ms | compare_events, search_events | ✅ |
| S4 | 单事件查询 | 中国经济领域最近有哪些受关注的热点事件？… | ✅ | 4 | 26814ms | get_event_detail, search_events | ✅ |
| T1 | 情绪趋势分析 | 伊朗关闭霍尔木兹海峡事件的整体情绪倾向是什么？… | ✅ | 4 | 23903ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| C1 | 多事件对比 | 对比伊朗霍尔木兹海峡事件和美伊谈判事件的舆情差异… | ✅ | 4 | 31822ms | compare_events, get_event_detail, search_events | ✅ |
| T2 | 情绪趋势分析 | 美国加征关税这件事，网民的情绪是负面多还是中性多… | ✅ | 4 | 21978ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| C2 | 多事件对比 | 俄乌冲突和中东局势，哪个事件的网民关注度更高？… | ✅ | 3 | 20083ms | get_event_detail, search_events | ❌ |
| T3 | 情绪趋势分析 | 最近关于伊朗的热点事件中，情绪分布有什么特点？… | ✅ | 3 | 22428ms | analyze_event_sentiment, search_events | ✅ |
| C3 | 多事件对比 | 比较一下最近两周伊朗相关的前两个热点事件… | ✅ | 4 | 31609ms | compare_events, get_event_detail, search_events | ✅ |
| T4 | 情绪趋势分析 | 近两周情绪最负面的热点事件是哪个？为什么？… | ✅ | 4 | 26736ms | analyze_event_sentiment, get_event_detail, rank_events_by_sentiment | ❌ |
| C4 | 多事件对比 | 最近三周内，哪两个事件的报道量差异最大？… | ✅ | 4 | 23418ms | compare_events, get_event_detail, search_events | ✅ |
| P1 | 跨平台差异 | 微博、头条、知乎今天最热的话题分别是什么？讨论量… | ✅ | 3 | 29479ms | get_event_detail, list_hot_platforms | ✅ |
| T1 | 情绪趋势分析 | 伊朗关闭霍尔木兹海峡事件的整体情绪倾向是什么？… | ✅ | 4 | 25023ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| T2 | 情绪趋势分析 | 美国加征关税这件事，网民的情绪是负面多还是中性多… | ✅ | 4 | 21329ms | analyze_event_sentiment, get_event_detail, search_events | ✅ |
| P2 | 跨平台差异 | 百度和微博热搜上哪些话题是共同的？… | ✅ | 7 | 42977ms | get_event_detail, list_hot_platforms, search_events | ✅ |
| T3 | 情绪趋势分析 | 最近关于伊朗的热点事件中，情绪分布有什么特点？… | ✅ | 3 | 23156ms | analyze_event_sentiment, search_events | ✅ |
| P3 | 跨平台差异 | 财联社和华尔街见闻两个财经平台最近在关注什么热点… | ✅ | 3 | 25732ms | get_event_detail, search_events | ❌ |
| T4 | 情绪趋势分析 | 近两周情绪最负面的热点事件是哪个？为什么？… | ✅ | 4 | 28103ms | analyze_event_sentiment, get_event_detail, rank_events_by_sentiment | ❌ |
| P4 | 跨平台差异 | 哔哩哔哩和澎湃新闻的热榜差别大吗？… | ✅ | 4 | 33282ms | get_event_detail, list_hot_platforms | ✅ |
| D1 | 早报/聚合概览 | 今天的舆情早报讲了什么？… | ✅ | 2 | 13495ms | get_morning_brief | ✅ |
| P1 | 跨平台差异 | 微博、头条、知乎今天最热的话题分别是什么？讨论量… | ✅ | 3 | 28722ms | get_event_detail, list_hot_platforms | ✅ |
| D2 | 早报/聚合概览 | 今日值得关注的三大新闻是什么？… | ✅ | 3 | 23476ms | get_event_detail, list_hot_platforms | ❌ |
| P2 | 跨平台差异 | 百度和微博热搜上哪些话题是共同的？… | ✅ | 4 | 37805ms | get_event_detail, list_hot_platforms, search_events | ✅ |
| D3 | 早报/聚合概览 | 帮我总结一下今日热点新闻… | ✅ | 2 | 22980ms | get_morning_brief, list_hot_platforms | ✅ |
| D4 | 早报/聚合概览 | 今天舆情总体态势如何？… | ✅ | 2 | 19448ms | get_morning_brief, list_hot_platforms | ✅ |
| P3 | 跨平台差异 | 财联社和华尔街见闻两个财经平台最近在关注什么热点… | ✅ | 4 | 32892ms | get_event_detail, search_events | ❌ |
| P4 | 跨平台差异 | 哔哩哔哩和澎湃新闻的热榜差别大吗？… | ✅ | 3 | 29938ms | get_event_detail, list_hot_platforms | ✅ |
| D1 | 早报/聚合概览 | 今天的舆情早报讲了什么？… | ✅ | 2 | 14398ms | get_morning_brief | ✅ |
| D2 | 早报/聚合概览 | 今日值得关注的三大新闻是什么？… | ✅ | 3 | 24950ms | get_event_detail, list_hot_platforms | ❌ |
| D3 | 早报/聚合概览 | 帮我总结一下今日热点新闻… | ✅ | 2 | 14131ms | get_morning_brief | ✅ |
| D4 | 早报/聚合概览 | 今天舆情总体态势如何？… | ✅ | 2 | 22092ms | get_morning_brief, list_hot_platforms | ✅ |

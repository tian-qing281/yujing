# 舆镜 YuJing · 第二阶段规划（答辩 + 论文双目标，3-6 周）

围绕"计算机设计大赛答辩亮点 + 论文可量化数据"双线推进，性能/UI/功能三轴都服务于这两个目标；优先落 1 个高价值算法创新（事件聚类升级）作论文主贡献，再以 LLM Tool-Calling Agent 作答辩 Demo 爆点，其余做配套支撑。

---

## 一、定位与取舍

- **目标 1（答辩/评审）**：2-3 个能在 5 分钟 Demo 里讲清楚的差异化亮点，稳定可演示
- **目标 2（论文/深度报告）**：至少 1 套完整 baseline vs upgraded 对照实验 + 可量化指标表
- **被砍项**：公网部署、鉴权限流、PostgreSQL 迁移、移动端适配 —— 延后到第三阶段
- **时间口径**：6 周切成三段，每段 2 周；允许裁剪但保住 P0

---

## 二、功能轴（创新点落地，最核心）

### P0 · 创新点 A：事件聚类 Sentence-BERT + 层次聚类（论文主贡献）
**现状**：`app/services/events.py` 用 Canonical Title + Jaccard 分词相似度（阈值 0.22），对同主题异表述（"苹果发布新机" vs "iPhone 17 首发评测"）召回不稳。
**升级方案**：
- 嵌入模型：`BAAI/bge-small-zh-v1.5`（约 100 MB，CPU 可跑，中文 MTEB 榜前列）
- 索引：SQLite 存向量 + 内存 FAISS IVF-Flat，每次聚类 ANN 召回 top-K=20 再精排
- 相似度：`0.6 * cosine + 0.25 * time_decay + 0.15 * platform_diversity`
- 阈值自适应：按历史 P95 分位数动态调整
- 兜底：若 BERT 进程未就绪，自动回落到现有 Jaccard
**工程量**：约 2 周
**论文抓手**：事件合并召回率 / 准确率、ARI、NMI、V-measure、消融（去掉时间衰减、去掉多样性）

### P0 · 创新点 B：LLM Tool-Calling Agent（答辩 Demo 爆点）
**现状**：`app/llm.py` 所有上下文塞 prompt，多事件对比、追问溯源力不从心。
**升级方案**：
- LangChain Tool-Calling：`search_events(q)` / `get_event_detail(id)` / `get_timeseries(event_id)` / `compare_events(ids)` / `list_alerts()`
- Plan-and-Execute：LLM 先产 task plan，再分步调工具，前端流式渲染每一步
- 前端 `AIConsultant.vue` 升级："思考中 → 调用工具 X → 得到结果 → 下一步"可视化链
- Demo 脚本候选："生成今日简报 + 对比微博与头条的热度走势 + 导出 PDF"
**工程量**：约 2 周
**答辩抓手**："舆情智能助理"一句话演示 + 工具调用链路可视化

### P1 · 创新点 C：情感多标签 + 立场分析（弹性扩展）
- 保留 8 维概率分布到 `ai_sentiment_dist`（JSON）
- 接入 `IDEA-CCNL/Erlangshen-Roberta-110M-Sentiment` 或现有 BERT 的分布输出
- 立场模型做二元（pro/con）或三元（pro/neutral/con）
- 前端新图：情感-立场二维散点图（每篇文章一个点）
**工程量**：约 5 天；时间紧可丢弃

### P2 · 答辩配套新功能
- **事件演化时间线**：单事件的热度/情感/信源随时间的 sparkline
- **对比看板 v2**：已有 `CompareDashboard.vue`，扩展为任意 2-4 事件矩阵
- **定时日报邮件推送**（可选，看投入）

---

## 三、性能轴（保住答辩稳定性）

### P0 · 答辩前必做
- **首屏 chunk 拆分**：`charts-vendor-D7ZqY3YE.js` 1.1 MB → ECharts 按图表类型 dynamic import，首屏控制在 400 KB 以内
- **早报 cache 持久化**：当前进程内 dict，重启丢。落到 `runtime/cache/morning_brief_<date>.json` 或 SQLite 新表，重启自动恢复
- **告警持久化**：同上，`runtime/cache/alerts.json`，配合 `dismissed_at` 字段
- **BERT 任务队列持久化**：目前 in-flight set 在内存，进程重启会丢补全队列。落到 DB 的 `ai_sentiment_pending` 字段标记，启动时自动续跑

### P1 · 论文稳定性需要
- **同步 DB 查询异步化**：`get_events` / `get_topics` 里的 `db.query(...)` 包 `asyncio.to_thread`，跑对照实验时能并发跑
- **BERT 批处理**：连续 pending 文章合并为 batch=8 单次前向，推理吞吐 ~3x
- **MeiliSearch 索引冷启动守护**：新索引未完成时 fallback 到 DB LIKE 查询

### P2 · 锦上添花
- 事件向量检索索引（FAISS）懒加载 + 磁盘缓存
- 统一 `logging` 替代 `print`，按模块 logger 分级

---

## 四、UI 轴（答辩看得好）

### P0 · 答辩前必做
- **暗色模式 + 主题切换按钮**：DaisyUI 再加一个 `yujing-dark` 主题；投影仪/大屏场景下护眼
- **事件详情 `EventModal.vue` 视觉重做**：当前是 tab 式，改为左情绪雷达 + 中时间线 + 右关键词云的三栏布局；信息密度 +50%
- **顶部统一通知中心**：早报/告警/PDF 导出状态统一走右上角 drawer，替代当前 banner + 浮层散点
- **Agent 思考链路可视化**：配合创新点 B，展示 "Plan → Tool Call → Tool Result → Next" 逐步动画

### P1 · 提升质感
- **微交互**：卡片 hover、模态开关、图表切换加 `transition`（用 vueuse/motion）
- **响应式栅格**：9 宫格 → 依屏宽 auto-fit，支持大屏 3-4 列扩展
- **骨架屏**：加载态用 skeleton 替代 spinner，感知首屏速度提升

### P2 · 设计系统沉淀
- 梳理 `hs-panel / hs-pill / hs-command-button` tokens 归档到 `yujing-ui/src/styles/design-tokens.css`
- 补组件说明文档 `yujing-ui/COMPONENTS.md`

---

## 五、论文/答辩产出物

### P0 · 必交付
- **评测集**：手工标注 300-500 对 article-pair（同事件 / 不同事件）作为聚类 ground truth
- **对比实验表格**：Jaccard vs Sentence-BERT + Hierarchical，指标：ARI / NMI / V-measure / 召回率@K
- **消融实验**：去掉时间衰减、去掉平台多样性、改变阈值
- **Demo 视频脚本**（3 分钟版）：5 个场景（热榜 → 事件详情 → 对比看板 → AI Agent 工具调用 → PDF 导出）
- **答辩话术**（10 页 slide 级别）：问题背景 / 系统架构 / 创新点 / 实验结果 / 落地价值

### P1 · 加分项
- 论文初稿 8 页（中文系统类期刊/会议风格）：abstract / 相关工作 / 方法 / 实验 / 讨论
- 复现包 README：一键启动脚本 `scripts/demo.ps1`，5 分钟从 clone 到跑起

---

## 六、6 周排期建议

| 周次 | 主线任务 | 交付物 |
|:---:|:---|:---|
| W1 | 创新点 A：bge-small-zh 向量化 + FAISS 索引基础 | 可生成向量，ANN 召回跑通 |
| W2 | 创新点 A：层次聚类 + 复合相似度 + 接入 `events.py` | 新聚类算法上线，旧方案保留为对照 |
| W3 | 论文评测集标注 + 对比实验 + 消融 | 指标表 v1 |
| W4 | 创新点 B：Tool-Calling Agent 骨架 + 工具函数 + 前端可视化 | Agent MVP |
| W5 | UI 三件套（暗色主题 / 事件详情重做 / 通知中心）+ 性能 P0（chunk 拆分 / 持久化）| 答辩级稳定性 |
| W6 | Demo 视频 + 答辩 slide + 论文初稿 + 回归测试 | 完整交付包 |

**弹性裁剪规则**：
- 进度 -1 周：砍创新点 C（立场分析）
- 进度 -2 周：砍 UI P1（微交互/响应式）
- 进度 -3 周：砍论文 P1，只保答辩必须

---

## 七、风险与对策

| 风险 | 对策 |
|:---|:---|
| bge 模型 CPU 推理慢 | 预计算向量并持久化，只对增量文章调用；批处理 batch=8 |
| FAISS Windows 安装失败 | 回退 `scikit-learn` NearestNeighbors 或纯 numpy cosine topK |
| LLM Tool-Calling 格式不稳 | 加严格 JSON Schema 校验 + 最大重试 3 次 + 工具链路兜底 |
| 标注集质量不够 | 先自动对齐（同 canonical_title 为正样本）+ 人工抽样校验 10% |
| 答辩前重构引入回归 | W6 只做调试和视频录制，W5 末尾冻结代码 |

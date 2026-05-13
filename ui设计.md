# 舆镜 YuJing · UI 设计文档

> 面向计算机设计大赛评审与团队协作的产品视觉/交互总览。
> 本文档记录"从糖果蓝紫 AI 风 → editorial 报刊感"的完整重塑过程，包含设计哲学、Token 体系、组件改造对照与升级路线图。

---

## 一、为什么要重做 UI

舆镜 v1.6 之前的界面是典型的"AI SaaS 模板"：

- 主色饱和糖果蓝（`#3b82f6`）+ 紫粉渐变 hero
- 大量浅色 glassmorphism 卡片 + 大圆角 + 多层阴影
- 早报 banner、提示卡、按钮各自一套配色，缺乏统一语言
- 数据图表用赛博虹色（蓝/紫/青/粉/绿），分类语义被"颜值竞争"淹没

这种"AI 模板感"和我们的产品定位 — **新闻/舆情聚合 + 多源对照 + 严肃分析** — 严重脱节。
评审第一眼看到的应该是**编辑部的纸感**，而不是 ChatGPT 的玻璃感。

> 用户原话："我只是让你有一点设计感，你怎么全黑这样子呢"
> "去 AI 味，有自己的创意创新什么的，而不是看到蓝紫色就一定要去掉"

设计目标因此被定为：**The Economist / NYT / Monocle 三家共有的视觉气质**。

---

## 二、设计哲学

### 1. Editorial First：先当报纸，再当 App

- **主标题用衬线体**（Noto Serif SC），副标题与正文 sans
- **Kicker 体系**：每个 hero / 卡 / 模态顶部都有一行
  `letter-spacing: 0.18em; text-transform: uppercase` 的小赤陶红 chip，
  类似 NYT 文章顶部的 SECTION TAG
- **Hairline 优先于阴影**：`1px var(--color-border)` 替代多层 box-shadow
- **顶部 3px 赤陶红条**：作为"版面规格条"出现在重要 hero / 模态顶部，
  类似 The Economist 内文章首的红条

### 2. 克制与节制的色彩

- 全局**只有 2 种主色**：墨石板黑 `#0F172A`（brand，主作之色） + 赤陶红 `#B45309`（accent，唯一情感色）
- 数据图表全部走**单色梯度**，分类信息靠**位置/排序/标签**而非"色相蹦迪"
- 语义色保留但弱化：红 = 警示、绿 = 正面、深蓝 = 中性数据，
  不再是糖果饱和度，而是**深、低饱和、报刊感**版本
  （`#B91C1C` 警示红 / `#15803D` 信号绿 / `#1E40AF` 数据蓝）

### 3. 排序而非装饰

- 榜单数字 01/02/03 不再用"红橙绿"红绿灯式糖果，而是
  **赤陶红（最重）→ 深赤陶红 → 墨石板 → 暖灰**的"逐渐退入背景"梯度，
  保留排序语义，去掉"AI 五彩"
- 火焰、星标等热度图标统一赤陶红，前 3 名突出，第 4 起暖灰

### 4. 留白即设计

- Hero 不再用大色块顶满，改为**纸白 + 巨号衬线 + 一笔 hairline**
- 一个屏幕只允许**一个强主作**（黑底按钮 / 黑底 chip 二选一）
- 卡片间距 24px+，不挤

---

## 三、Token 体系

所有 token 在 `yujing-ui/src/style.css` 顶部以 CSS 变量声明，
全站 100+ 处颜色写作 `var(--color-*)`，便于一键改主题。

### 颜色

| Token | 值 | 用途 |
|---|---|---|
| `--color-bg` | `#FAFAF7` | 页面底色（米白纸） |
| `--color-surface` | `#FFFFFF` | 卡片/模态主面 |
| `--color-surface-2` | `#F5F5F2` | 嵌套面/hover/chip 弱底 |
| `--color-text` | `#1C1917` | 主文本（接近墨黑而非纯黑） |
| `--color-text-2` | `#57534E` | 次文本/暖灰副标 |
| `--color-text-3` | `#A8A29E` | 第三级文本/失焦 |
| `--color-border` | `#E5E5DD` | 全局 hairline |
| `--color-brand` | `#0F172A` | 近墨石板黑，主作之色 |
| `--color-accent` | `#B45309` | 赤陶红，唯一情感色 |
| `--color-data` | `#1E40AF` | 中性数据深蓝（图表柱条主色） |
| `--color-critical` | `#B91C1C` | 警示红（告警/error） |
| `--color-warning` | `#D97706` | 警告橙（次级警示/info） |
| `--color-info` | `#1E40AF` | 信息蓝 |
| `--color-success` | `#15803D` | 成功绿（弱化版本） |

### 字体

| Token | 值 | 用途 |
|---|---|---|
| `--font-display` | `"Noto Serif SC", serif` | 衬线主标题 / hero / 戳记 |
| `--font-body` | `"PingFang SC", "Microsoft YaHei", sans-serif` | 正文与组件 |

### 圆角

- 卡片 / 模态：`4px`（去掉之前的 16-24px 大圆角）
- 按钮：`4px`
- chip / pill：`3-4px`，仅极少数计数 badge 保留 `999px`

### 数据可视化调色板

ECharts 全部图表统一使用 5 阶单色梯度：

```
['#0F172A', '#1C1917', '#57534E', '#92400E', '#B45309']
```

从近墨黑 → 暖灰 → 深赤陶 → 赤陶红，"重要的数据用墨色，强调的数据用赤陶红"。

情感分类的 8 色保留语义但全部映射到 editorial 调色：

```
愤怒 #B91C1C / 厌恶 #7F1D1D / 悲伤 #57534E / 喜悦 #15803D
关注 #1E40AF / 惊讶 #D97706 / 质疑 #B45309 / 中性 #A8A29E
```

---

## 四、组件改造对照（按 commit 时间线）

> 本轮共 12 个 commit，从 `7e2cc40` 至 `19b9bd6`，覆盖全站 16 个核心组件。

### Batch A · Token 落地（commit `7e2cc40`）

- `style.css`：全部 editorial token 写入 `:root`
- `AIConsultant`：prompt-chip / rail-label / msg-text 全部去糖果蓝
- 告警卡 `alert-critical/warning/info`：粉/黄/蓝糖果渐变 → 纯白底 + 强左条 + 弱图标 chip

### Batch B · 全局色彩（commit `b53fa09`）

- `AppHeader` / `AppSidebar` / 全局 `.eh-pill-btn`
- 亮蓝 `#3b82f6` → `var(--color-accent)` rgba 弱底
- 退蓝紫 AI 味，统一为赤陶红高亮

### Batch E + Fix · EventModal 全图（commits `42c0676`, `ce49ef7`）

- 4 个图表（sentiment / 时间趋势 / 平台 / 演变）全部改为单色梯度
- 修复全黑柱子的"压重感"，改为暖灰 + 单色梯度

### 全 ECharts 图表统一（commit `e8176c8`）

- `SourcePulse` / `CompareDashboard` / `SearchInsightChart` / `AnalysisModal`
- WordCloud 5 阶 editorial 梯度
- keywordRadar / aspectRadar 单色赤陶红

### 情感色保留语义（commit `316fe30`）

- 8 类情感色（愤怒/厌恶/悲伤/喜悦/关注/惊讶/质疑/中性）保留语义，但全部映射到 editorial 调色
- ABSA badge：紫粉渐变 → 米白 + 赤陶红 chip

### 4 处残留扫尾（commit `2126a79`）

- 侧栏 logo / 时间过滤器 / AI 快捷入口 / 告警卡

### Logo Lockup 居中（commit `b17583c`）

- 侧栏顶部 brand-box：左对齐 → 居中
- "YU JING" kicker（11px 赤陶红 letter-spacing 0.32em）
- "舆镜" 主名（38px 衬线纸白），形成报纸刊头感

### SubscriptionPanel 全面 editorial（commits `746d273` + `f6923fc`）

- Hero：紫粉蓝糖果渐变 → 黑底 → **再迭代**为纸白 + 顶部 3px 赤陶红 hairline + 巨号衬线（评审建议"全黑太压"，再去黑）
- 关键词 chip：糖果紫渐变 → 米白 + 1px hairline
- 推荐解释 6 色 chip：所有底色统一米白，仅文字色区分语义
- "匹配 X.XXX"分数 chip：黑底赤陶字 → 米白 + 1px 赤陶 hairline + 衬线赤陶字（"分数戳记"感）

### NewsCard 残留扫尾（commit `a622ad5`）

- 主背双层蓝渐变 + 右上蓝光晕 → 纸白 + 1px hairline + 软 shadow
- hover overlay 蓝青糖果 → 暖橙 radial
- `:deep(mark)` 黄底高亮 → 透明上半 + 赤陶红下半（如报刊重点圈存）
- "已采集" badge：糖果蓝 → token 米白 + 赤陶红边

### 全站走查（commit `19b9bd6`）

- **NewsCard 排序色**：`['#ef4444', '#f59e0b', '#10b981']` 红橙绿糖果
  → `['#B45309', '#92400E', '#1C1917']` 赤陶红/深赤陶/墨石板梯度（保留排序语义）
- **火焰图标**：糖果红 → token accent
- **全景事件 metric 卡**：糖果蓝 hover/icon → 赤陶红
- **CredentialModal**：9 处糖果蓝/紫渐变 → token；"已配置"绿色 success 信号保留但弱化

---

## 五、走查完成度

| 页面 | 状态 | 主要变化 |
|---|---|---|
| 微博热搜榜 | ✅ | NewsCard 排序色 + 火焰 + cached badge |
| 百度热搜榜 | ✅ | 同上 |
| 头条实时榜 | ✅ | 同上 |
| 哔哩哔哩榜 | ✅ | 同上 |
| 知乎全站榜 | ✅ | 同上 |
| 澎湃热榜 | ✅ | 同上 |
| 华尔街见闻热榜 | ✅ | 同上 |
| 财联社热榜 | ✅ | 同上 |
| 全景事件聚合 | ✅ | metric 卡 + 时间过滤器 + EventCard |
| AI 助手 | ✅ | 早报 banner + 告警卡 + 快速操作 + 会话列表 |
| 我的订阅 | ✅ | hero（两轮迭代）+ 关键词 + 6 色解释 + 匹配分 chip |
| 凭据资产配置（模态） | ✅ | 顶部 hairline + 盾牌图标 + status 卡 + 主按钮 |
| EventModal（事件深度） | ✅ | 4 张图表全部 editorial 单色梯度 |
| AnalysisModal（分析弹窗） | ✅ | WordCloud + 雷达 + 情感柱条 |
| CompareDashboard（对照） | ✅ | 单色梯度图表 |

---

## 六、升级路线图

> 本轮聚焦"视觉语言统一"。下一轮将进入"信息架构与交互细节"。

### Batch F · 榜单页卡片重排（待开始）

**问题**：当前榜单页采用 2 列大卡片，每张卡只显示标题 + 排名 + 影响指数 chip，
信息密度太低，一屏只能看 6 条。

**方案**：参考 NYT/FT 的"杂志条目"排版：

- **第 1 名**：保留大卡（衬线大标题 + 摘要 + 底部 meta line）
- **第 2-5 名**：中卡，单列，标题 + 1 行摘要
- **第 6+ 名**：紧凑列表，仅排名 + 标题 + 热度小数字
- 顶部增加"今日重点"区，从订阅推荐排序拉前 3 高分事件

**收益**：单屏信息从 6 条 → 15+ 条，符合"严肃新闻聚合"的密度感。

### Batch G · 暗模式（Dark Editorial）

- 在 `:root` 旁补 `[data-theme="dark"]`
- 底色：`#1C1917`（warm dark）而非纯黑
- accent 不变，data 调亮一档
- 所有 hairline 改为 `#2C2826`

### Batch H · 微动效

- 卡 hover：`translateY(-1px)` + border 加深，不要 scale 放大
- 数字滚动：`<NumberFlow>`，类似 Stripe Dashboard
- 图表入场：单条曲线 200ms ease-out 描出，不要群体颤抖

### Batch I · 主题切换器

- 提供"刊物风"切换：`Economist 红` / `NYT 黑` / `Monocle 卡其`
- 三套预设全部基于现有 token，仅需替换 5 个值

### Batch J · 排版微调

- 主标题字号梯度：`30 → 24 → 18 → 14`（当前部分组件还在用 28/26）
- 行高统一：标题 `1.2`、正文 `1.7`
- 中文断词：全站加 `word-break: keep-all` 避免标题被切

### Batch K · 移动端

- 当前是桌面优先，移动端布局尚未走查
- 侧栏改为底部 tab bar
- 大卡 hero 改为单列，衬线字号下降

---

## 七、技术约束与决策记录

### ADR-1：为什么不用 Tailwind/UnoCSS 默认色板？

Tailwind 默认调色板（`blue-500`、`emerald-500` 等）是为通用 SaaS 设计的，
饱和度高、视觉等级一致，正好是我们要避免的"AI 模板感"。
本项目所有颜色全部 hardcode 到 CSS 变量，**禁止**新代码出现 `text-blue-500` 之类的直写类。

### ADR-2：为什么衬线主标题选 Noto Serif SC？

- 免费可商用 + Google Fonts CDN
- 中英文字形协调，西文回退到 `serif`
- 比思源宋体（Source Han Serif）字重选项更细分

### ADR-3：为什么不去除全部圆角？

完全锐角会过于工业/政府感，4px 圆角保留"软"但接近"刊物排版块"。
仅极少数 chip 保留 999px 用于"计数徽章"语义。

### ADR-4：为什么保留绿色 success？

色彩是无障碍信息，强行去除"已配置/采集成功"的绿色会损害可识别性。
保留语义色，但改用低饱和、深暗版本（`#15803D` 而非 `#22c55e`）。

---

## 八、参考

- The Economist 数字版：https://www.economist.com
- NYT The Daily：https://www.nytimes.com
- Monocle：https://monocle.com
- IBM Carbon Design - Type styles
- 设计系统底层参考：design-system/舆镜-yujing/MASTER.md

---

> 文档版本 v1.0 · 最后更新：2026-05-13
> 对应 commit 区间：`7e2cc40` → `19b9bd6`（共 12 次提交）

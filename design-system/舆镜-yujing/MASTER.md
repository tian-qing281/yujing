# 舆镜 YuJing 设计系统主文件（Master）

> **优先级**：实现具体页面前先看 `design-system/舆镜-yujing/pages/<页面>.md`；存在则覆盖本文件，否则严格遵循本文件。

---

- **项目**：舆镜 YuJing — AI 舆情监测与早报平台
- **更新**：2026-05-13（人工矫正后）
- **风格主张**：Editorial Dashboard · 编辑部式仪表盘
- **气质关键词**：克制 · 留白 · 内容为王 · 中文衬线点缀 · 近墨主色 · 一抹赤陶红
- **明确避雷**：蓝紫渐变、glassmorphism、neumorphism、emoji 当 icon、过度跳动 hover、AI 紫红 hero

---

## 1. 调色板

### 1.1 中性 / 背景

| 角色 | Hex | CSS 变量 | 说明 |
|------|-----|----------|------|
| 纸白底 | `#FAFAF7` | `--color-bg` | 全局背景，带极轻暖色不刺眼 |
| 卡片底 | `#FFFFFF` | `--color-surface` | 卡片、Modal、面板 |
| 次级面 | `#F5F5F2` | `--color-surface-2` | 嵌套区域、悬浮态 |
| 暖灰描边 | `#E5E5DD` | `--color-border` | 卡片描边、分割线 |
| 浅描边 | `#EFEFEA` | `--color-border-soft` | 表格行分割、内嵌容器 |

### 1.2 文字

| 角色 | Hex | CSS 变量 | 用途 |
|------|-----|----------|------|
| 主文 | `#1C1917` | `--color-text` | 标题、正文，近黑非纯黑 |
| 次文 | `#57534E` | `--color-text-2` | 副标、meta、辅助说明 |
| 弱文 | `#A8A29E` | `--color-text-3` | placeholder、disabled、时间戳 |
| 反白 | `#FAFAF7` | `--color-text-on-dark` | 深色背景上的文字 |

### 1.3 品牌 / 强调

| 角色 | Hex | CSS 变量 | 用途 |
|------|-----|----------|------|
| 品牌主色 | `#0F172A` | `--color-brand` | sidebar 深色块、logo、品牌一致性元素，**不在按钮主色用** |
| 强调点缀 | `#B45309` | `--color-accent` | logo 装饰、关键 CTA、选中态、品牌点缀，全站克制使用 |
| 强调浅 | `#FEF3C7` | `--color-accent-soft` | 强调态背景（badge、subtle 高亮） |
| 数据蓝 | `#1E40AF` | `--color-data` | 图表主色、链接 hover、数据强调，**不做主色** |

### 1.4 状态色（沿用 U2 落地的告警三级 + 通用）

| 角色 | Hex | CSS 变量 | 用途 |
|------|-----|----------|------|
| 严重 critical | `#DC2626` | `--color-critical` | 高优告警、错误 |
| 警告 warning | `#D97706` | `--color-warning` | 中优告警、警示 |
| 信息 info | `#2563EB` | `--color-info` | 一般通知 |
| 成功 success | `#15803D` | `--color-success` | 任务完成、积极情绪 |
| 中性 neutral | `#57534E` | `--color-neutral` | 中性情绪、灰态 |

### 1.5 情绪色（事件情感分析专用）

| 情感 | Hex | 用途 |
|------|-----|------|
| 正面 positive | `#15803D` | 标签、情感分布饼图 |
| 中性 neutral | `#A8A29E` | 同上 |
| 负面 negative | `#B91C1C` | 同上 |

---

## 2. 字体系统

### 2.1 字体栈

| 角色 | CSS 变量 | font-family |
|------|----------|-------------|
| 中文标题（衬线，文气） | `--font-display` | `"Source Han Serif SC", "Songti SC", "Noto Serif SC", serif` |
| 中文正文（无衬线） | `--font-body` | `"PingFang SC", "Microsoft YaHei", "Source Han Sans SC", "Noto Sans SC", system-ui, sans-serif` |
| 英文 / 数字 | `--font-latin` | `"Inter", system-ui, -apple-system, "Helvetica Neue", sans-serif` |
| 等宽（数据/JSON） | `--font-mono` | `"JetBrains Mono", "Fira Code", "SF Mono", Menlo, Consolas, monospace` |

> 衬线字体仅用于 **品牌 logo / 模块大标题 / hero title**，正文不用衬线避免阅读疲劳。

### 2.2 字号节奏（rem，1rem=16px）

| Token | rem | px | 用途 |
|-------|-----|----|----- |
| `--text-xs` | 0.75 | 12 | meta、tag、时间戳 |
| `--text-sm` | 0.8125 | 13 | 副标、按钮、卡片副信息 |
| `--text-base` | 0.875 | 14 | 正文、列表项 |
| `--text-md` | 1 | 16 | 强调正文、表单输入 |
| `--text-lg` | 1.125 | 18 | 卡片标题 |
| `--text-xl` | 1.375 | 22 | 模块标题（衬线） |
| `--text-2xl` | 1.75 | 28 | 页面主标题（衬线） |
| `--text-3xl` | 2.25 | 36 | hero 大标题（衬线） |

### 2.3 行高 / 字重

- 中文正文：`line-height: 1.7`，字重 `400`
- 中文标题（衬线）：`line-height: 1.35`，字重 `500`
- 英数 meta：`line-height: 1.5`，字重 `500`，常配 `letter-spacing: 0.02em`
- 等宽：`line-height: 1.55`，字重 `400`

---

## 3. 间距 / 圆角 / 阴影

### 3.1 间距（4px 网格）

| Token | px | rem | 典型用途 |
|-------|----|-----|----------|
| `--space-1` | 4 | 0.25 | icon 与文字 |
| `--space-2` | 8 | 0.5 | 内联元素 |
| `--space-3` | 12 | 0.75 | 紧凑 padding |
| `--space-4` | 16 | 1 | 标准 padding |
| `--space-5` | 20 | 1.25 | 卡片内 padding |
| `--space-6` | 24 | 1.5 | section padding |
| `--space-8` | 32 | 2 | section 间隔 |
| `--space-10` | 40 | 2.5 | 大模块间隔 |
| `--space-12` | 48 | 3 | 页面级间隔 |

### 3.2 圆角

| Token | px | 用途 |
|-------|----|------|
| `--radius-sm` | 4 | tag、badge、紧凑控件 |
| `--radius-md` | 8 | 按钮、输入、小卡片 |
| `--radius-lg` | 12 | 卡片、面板 |
| `--radius-xl` | 16 | Modal、大面板 |
| `--radius-full` | 999 | 头像、pill |

### 3.3 阴影（极克制，仅 2 层 + hover）

| Token | 值 | 用途 |
|-------|----|----- |
| `--shadow-1` | `0 1px 0 rgba(0, 0, 0, 0.04)` | 卡片描边补充（与 border 叠加） |
| `--shadow-2` | `0 4px 12px rgba(20, 16, 8, 0.05)` | 悬浮卡片、hover 态 |
| `--shadow-modal` | `0 20px 48px rgba(20, 16, 8, 0.12)` | Modal 唯一深阴影 |

> **不要**多层重叠阴影、彩色阴影、带颜色的发光（避免 AI 味）。

### 3.4 动效

| Token | 值 | 用途 |
|-------|----|----- |
| `--duration-fast` | 120ms | 微反馈（按钮按下） |
| `--duration-base` | 180ms | 标准 hover / focus |
| `--duration-slow` | 280ms | 折叠展开、tab 切换 |
| `--ease` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | 通用缓动 |

> hover **优先用底色 / border / 阴影变化**，不用 `transform: translateY`/`scale` 跳动（破坏稳定感）。

---

## 4. 组件规范

### 4.1 按钮（btn）

```css
/* 主按钮：近墨底 + 反白文 */
.btn-primary {
  background: var(--color-brand);
  color: var(--color-text-on-dark);
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-md);
  font: 500 var(--text-sm)/1 var(--font-body);
  letter-spacing: 0.02em;
  border: 1px solid var(--color-brand);
  cursor: pointer;
  transition: background var(--duration-base) var(--ease);
}
.btn-primary:hover { background: #1F2937; }
.btn-primary:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }

/* 次按钮：白底 + 描边 + 主文 */
.btn-secondary {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-md);
  font: 500 var(--text-sm)/1 var(--font-body);
  cursor: pointer;
  transition: background var(--duration-base) var(--ease), border-color var(--duration-base) var(--ease);
}
.btn-secondary:hover { background: var(--color-surface-2); border-color: var(--color-text-2); }

/* 强调按钮：赤陶红，全站极少出现，仅"立即查看早报"等关键 CTA */
.btn-accent {
  background: var(--color-accent);
  color: #FFFFFF;
  border: 1px solid var(--color-accent);
  padding: 0.625rem 1.25rem;
  border-radius: var(--radius-md);
  font: 500 var(--text-sm)/1 var(--font-body);
  cursor: pointer;
  transition: background var(--duration-base) var(--ease);
}
.btn-accent:hover { background: #92400E; }

/* 文字按钮 */
.btn-ghost {
  background: transparent;
  color: var(--color-text-2);
  border: none;
  padding: 0.5rem 0.75rem;
  font: 500 var(--text-sm)/1 var(--font-body);
  cursor: pointer;
  transition: color var(--duration-base) var(--ease), background var(--duration-base) var(--ease);
}
.btn-ghost:hover { color: var(--color-text); background: var(--color-surface-2); }
```

### 4.2 卡片（card）

```css
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  transition: border-color var(--duration-base) var(--ease), box-shadow var(--duration-base) var(--ease);
}
.card:hover { border-color: var(--color-text-3); box-shadow: var(--shadow-2); }
.card--flat { box-shadow: none; }   /* 无 hover 抬起 */
.card--inset { background: var(--color-surface-2); }   /* 嵌套区 */
```

### 4.3 输入（input / textarea）

```css
.input {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 0.625rem 0.875rem;
  font: 400 var(--text-md)/1.4 var(--font-body);
  color: var(--color-text);
  transition: border-color var(--duration-base) var(--ease), box-shadow var(--duration-base) var(--ease);
}
.input::placeholder { color: var(--color-text-3); }
.input:hover { border-color: var(--color-text-3); }
.input:focus-visible {
  outline: none;
  border-color: var(--color-brand);
  box-shadow: 0 0 0 3px rgba(15, 23, 42, 0.08);
}
```

### 4.4 标签（badge / tag）

```css
.badge {
  display: inline-flex; align-items: center; gap: 0.25rem;
  background: var(--color-surface-2);
  color: var(--color-text-2);
  border: 1px solid var(--color-border);
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-sm);
  font: 500 var(--text-xs)/1 var(--font-body);
  letter-spacing: 0.02em;
}
.badge--accent { background: var(--color-accent-soft); color: var(--color-accent); border-color: rgba(180, 83, 9, 0.2); }
.badge--critical { background: #FEF2F2; color: var(--color-critical); border-color: rgba(220, 38, 38, 0.2); }
.badge--warning  { background: #FFFBEB; color: var(--color-warning);  border-color: rgba(217, 119, 6, 0.2); }
.badge--info     { background: #EFF6FF; color: var(--color-info);     border-color: rgba(37, 99, 235, 0.2); }
```

### 4.5 Modal

```css
.modal-overlay {
  background: rgba(28, 25, 23, 0.4);
  backdrop-filter: blur(2px);
}
.modal {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-modal);
  padding: var(--space-8);
}
```

### 4.6 链接

```css
a { color: var(--color-data); text-decoration: none; transition: color var(--duration-base) var(--ease); }
a:hover { color: var(--color-brand); text-decoration: underline; text-underline-offset: 2px; }
a:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; border-radius: 2px; }
```

---

## 5. Pattern：Editorial Dashboard

- **结构**：左侧深色 sidebar（已就位）+ 主区浅色三栏（导航 / 内容流 / 详情）
- **主角**：内容（标题、热度数字、情感）；UI 元素（按钮、tab）退到中性灰
- **节奏**：大量留白（卡片间距 24px+）、行高宽松（1.7）
- **品牌识别**：仅在 logo / 模块衬线大标题 / 关键 CTA 上出现赤陶红，全站不超过 5 处
- **不要**：满屏 hero、首屏 CTA 大色块、glassmorphism 玻璃面、AI 紫红渐变

---

## 6. Anti-Patterns（明确避雷）

- ❌ **蓝紫渐变 / AI 紫色调** — 产生廉价 SaaS landing 感
- ❌ **Glassmorphism / Neumorphism** — 与编辑感冲突
- ❌ **Emoji 当 icon** — 一律用 [Remix Icon](https://remixicon.com/) (`iconify-icon` 已集成)
- ❌ **彩色 / 多层阴影 + 发光** — 仅用 `--shadow-1/2/modal` 三档
- ❌ **缺 cursor:pointer** — 所有可点元素必须有
- ❌ **scale/translateY hover 跳动** — 仅用底色 / border / 阴影变化
- ❌ **低对比度文字** — 正文 ≥ 4.5:1，meta ≥ 3:1
- ❌ **无过渡的瞬变** — 使用 `--duration-base` (180ms)
- ❌ **不可见 focus 态** — `:focus-visible` 必须有 outline 或 box-shadow

---

## 7. Pre-Delivery Checklist

每次提交 UI 改动前自检：

- [ ] 无 emoji 当 icon（统一用 iconify-icon + Remix Icon）
- [ ] 所有可点元素有 `cursor: pointer`
- [ ] hover/focus/active 三态齐全，过渡 150-300ms
- [ ] 文字对比度：正文 ≥ 4.5:1（用浏览器 devtools 验）
- [ ] `:focus-visible` 在键盘 Tab 时可见
- [ ] `@media (prefers-reduced-motion: reduce)` 关闭非必要动画
- [ ] 响应式断点：375 / 768 / 1024 / 1440 px 不破版
- [ ] 顶部固定 navbar 不遮内容（main 已加 padding-top）
- [ ] 移动端无横向滚动条
- [ ] 不出现蓝紫渐变 / glassmorphism / 多层彩色阴影
- [ ] 衬线字体仅在标题级别使用，正文必为无衬线

---

## 8. CSS 变量总表（直接复制到 :root）

```css
:root {
  /* 背景 / 表面 */
  --color-bg:          #FAFAF7;
  --color-surface:     #FFFFFF;
  --color-surface-2:   #F5F5F2;
  --color-border:      #E5E5DD;
  --color-border-soft: #EFEFEA;

  /* 文字 */
  --color-text:        #1C1917;
  --color-text-2:      #57534E;
  --color-text-3:      #A8A29E;
  --color-text-on-dark:#FAFAF7;

  /* 品牌 */
  --color-brand:       #0F172A;
  --color-accent:      #B45309;
  --color-accent-soft: #FEF3C7;
  --color-data:        #1E40AF;

  /* 状态 */
  --color-critical:    #DC2626;
  --color-warning:     #D97706;
  --color-info:        #2563EB;
  --color-success:     #15803D;
  --color-neutral:     #57534E;

  /* 字体 */
  --font-display: "Source Han Serif SC", "Songti SC", "Noto Serif SC", serif;
  --font-body:    "PingFang SC", "Microsoft YaHei", "Source Han Sans SC", "Noto Sans SC", system-ui, sans-serif;
  --font-latin:   "Inter", system-ui, -apple-system, "Helvetica Neue", sans-serif;
  --font-mono:    "JetBrains Mono", "Fira Code", "SF Mono", Menlo, Consolas, monospace;

  /* 字号 */
  --text-xs: 0.75rem;
  --text-sm: 0.8125rem;
  --text-base: 0.875rem;
  --text-md: 1rem;
  --text-lg: 1.125rem;
  --text-xl: 1.375rem;
  --text-2xl: 1.75rem;
  --text-3xl: 2.25rem;

  /* 间距 */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.25rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-10: 2.5rem;
  --space-12: 3rem;

  /* 圆角 */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 999px;

  /* 阴影 */
  --shadow-1: 0 1px 0 rgba(0, 0, 0, 0.04);
  --shadow-2: 0 4px 12px rgba(20, 16, 8, 0.05);
  --shadow-modal: 0 20px 48px rgba(20, 16, 8, 0.12);

  /* 动效 */
  --duration-fast: 120ms;
  --duration-base: 180ms;
  --duration-slow: 280ms;
  --ease: cubic-bezier(0.2, 0.8, 0.2, 1);
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

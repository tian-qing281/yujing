# 页面覆盖：榜单 / 订阅 / 全景事件 (Dashboard)

> 适用范围：微博/百度/头条/B站/知乎/澎湃/华尔街见闻/财联社 各热榜页 + 全景事件页 + 我的订阅页。
> 本文件 **覆盖** MASTER.md 中冲突的规则；未覆盖的部分严格遵循 MASTER。

---

## 1. 信息密度

榜单类是高密度信息列表，节奏比 MASTER 默认更紧凑：

- 列表行高：`1.5`（MASTER 默认 `1.7`）
- 卡片间距：`var(--space-3)` (12px)（MASTER 默认 `--space-5` 20px）
- 卡片内 padding：`var(--space-4) var(--space-5)` (16/20)
- 表格 / 列表项分隔线：`1px solid var(--color-border-soft)`，不用阴影分隔

## 2. 排名 / 热度数字

排名数字是榜单视觉锚点，用 **等宽字体 + 大字号 + 弱化色**：

```css
.rank-num {
  font: 500 var(--text-xl)/1 var(--font-mono);
  color: var(--color-text-3);   /* 默认弱化 */
  letter-spacing: 0;
  min-width: 2ch;
  text-align: right;
}
.rank-num--top3 { color: var(--color-accent); }   /* 前 3 名用赤陶红 */
```

热度数字：

```css
.hot-num {
  font: 600 var(--text-base)/1 var(--font-mono);
  color: var(--color-text);
  font-variant-numeric: tabular-nums;   /* 等宽数字 */
}
.hot-num__unit { color: var(--color-text-3); margin-left: 2px; font-weight: 400; }
```

## 3. 平台图标

每条榜单项的平台 icon 用 `iconify-icon`，色彩遵循平台真实色但**降饱和到灰**，避免抢戏：

| 平台 | icon | 默认色 | hover 色 |
|------|------|--------|----------|
| 微博 | `ri:weibo-fill` | `#A8A29E` | `#E6162D` |
| 百度 | `ri:baidu-fill` | `#A8A29E` | `#2932E1` |
| B站  | `ri:bilibili-fill` | `#A8A29E` | `#FB7299` |
| 知乎 | `ri:zhihu-fill` | `#A8A29E` | `#0066FF` |

## 4. 订阅页 chips（已在 A1 落地）

保留现有 chip 组件，仅做色彩对齐：
- 背景：`var(--color-surface-2)`
- 描边：`var(--color-border)`
- 选中态：背景 `var(--color-accent-soft)`，文字 `var(--color-accent)`，描边 `rgba(180,83,9,0.2)`

## 5. 全景事件 (Event Cards)

事件卡是页面主角，单独放大并加情绪色 left-border：

```css
.event-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-text-3);   /* 默认中性 */
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  transition: border-color var(--duration-base) var(--ease), box-shadow var(--duration-base) var(--ease);
}
.event-card:hover { box-shadow: var(--shadow-2); }
.event-card--positive { border-left-color: var(--color-success); }
.event-card--negative { border-left-color: var(--color-critical); }
.event-card--neutral  { border-left-color: var(--color-text-3); }

.event-card__title {
  font: 500 var(--text-lg)/1.4 var(--font-body);
  color: var(--color-text);
  margin-bottom: var(--space-2);
}
.event-card__meta {
  display: flex; gap: var(--space-3);
  font: 400 var(--text-xs)/1.4 var(--font-body);
  color: var(--color-text-2);
}
```

## 6. 排行榜专属反 pattern

- ❌ 列表项 hover 整行填充亮色（用 `--color-surface-2` 即可）
- ❌ 排名数字加圆形/方形背景色块（保持简洁数字）
- ❌ 平台 icon 默认显示彩色（仅 hover 显示，否则降为 #A8A29E）

## 7. 检查清单（专属）

- [ ] 列表至少在 1024 / 1440 两个断点测过
- [ ] 长标题溢出用 `text-overflow: ellipsis` + `white-space: nowrap`
- [ ] 数字一律用 `font-variant-numeric: tabular-nums` 防跳动
- [ ] 卡片间距统一 `var(--space-3)`

# 页面覆盖：事件详情 (EventModal)

> 适用范围：事件详情弹窗 (EventModal.vue)，含标题/演变时间轴/平台分布/相关文章列表/情感分布。
> **覆盖** MASTER.md 中冲突的规则。

---

## 1. Modal 容器

弹窗是聚焦阅读环境，需要更大尺寸 + 更安静的背景：

```css
.modal-overlay {
  background: rgba(28, 25, 23, 0.5);             /* 比 MASTER 略深，强化聚焦 */
  backdrop-filter: blur(3px);
}
.modal {
  background: var(--color-bg);                    /* 用纸白底，不是纯白，气质柔和 */
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-modal);
  max-width: 1080px;                              /* 宽屏布局：左侧主内容 + 右侧侧栏 */
  max-height: 88vh;
  padding: 0;                                     /* 内部章节自管 padding */
  overflow: hidden;
}
.modal-header {
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  padding: var(--space-5) var(--space-6);
}
.modal-body {
  padding: var(--space-6);
  overflow-y: auto;
}
```

## 2. 标题与 meta

```css
.modal-title {
  font: 500 var(--text-2xl)/1.3 var(--font-display);   /* 衬线大标题 */
  color: var(--color-text);
  margin-bottom: var(--space-2);
}
.modal-meta {
  display: flex; gap: var(--space-4);
  font: 400 var(--text-sm)/1 var(--font-body);
  color: var(--color-text-2);
}
.modal-meta__item iconify-icon { color: var(--color-text-3); margin-right: 4px; }
.modal-meta__sentiment--positive { color: var(--color-success); }
.modal-meta__sentiment--negative { color: var(--color-critical); }
.modal-meta__sentiment--neutral  { color: var(--color-text-2); }
```

## 3. F1 时间轴（演变时间线）

```css
.f1-timeline { position: relative; padding-left: var(--space-6); }
.f1-timeline::before {
  content: ""; position: absolute; left: 8px; top: 0; bottom: 0;
  width: 1px; background: var(--color-border);
}
.f1-step {
  position: relative; padding-bottom: var(--space-5);
}
.f1-step__marker {
  position: absolute; left: -24px; top: 4px;
  width: 17px; height: 17px; border-radius: 999px;
  background: var(--color-surface); border: 2px solid var(--color-border);
}
.f1-step__marker--peak {
  background: var(--color-accent); border-color: var(--color-accent);
}
.f1-step__time {
  font: 500 var(--text-xs)/1 var(--font-mono);
  color: var(--color-text-3); letter-spacing: 0.04em;
}
.f1-step__title {
  font: 500 var(--text-md)/1.4 var(--font-body);
  color: var(--color-text); margin: var(--space-1) 0;
}
.f1-step__desc {
  font: 400 var(--text-sm)/1.6 var(--font-body);
  color: var(--color-text-2);
}
```

## 4. 平台分布 / 情感分布饼图

ECharts 主题色变量（不要让饼图带 AI 蓝紫感）：

```js
// 在 EventModal.vue 的 echarts setOption 中使用
const platformColors = [
  '#1E40AF',  // 数据蓝
  '#B45309',  // 赤陶红
  '#15803D',  // 绿
  '#A8A29E',  // 暖灰
  '#57534E',  // 暖灰深
  '#D97706',  // 橙
];
const sentimentColors = {
  positive: '#15803D',
  neutral:  '#A8A29E',
  negative: '#B91C1C',
};
```

图表通用配置：
- `textStyle.fontFamily`: `var(--font-body)`
- 不用 area 渐变，仅用纯色 + `1px` 描边
- legend 字号 `12px`，色 `var(--color-text-2)`

## 5. 相关文章列表

```css
.article-row {
  display: flex; gap: var(--space-3);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border-soft);
  transition: background var(--duration-base) var(--ease);
}
.article-row:last-child { border-bottom: 0; }
.article-row:hover { background: var(--color-surface-2); }
.article-row__platform-icon {
  width: 18px; height: 18px;
  color: var(--color-text-3);
  flex-shrink: 0;
}
.article-row__title {
  flex: 1; min-width: 0;
  font: 400 var(--text-base)/1.5 var(--font-body);
  color: var(--color-text);
}
.article-row__title a { color: inherit; }
.article-row__title a:hover { color: var(--color-data); }
.article-row__meta {
  font: 400 var(--text-xs)/1 var(--font-body);
  color: var(--color-text-3);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
```

## 6. 关闭按钮

```css
.modal-close {
  position: absolute; top: var(--space-4); right: var(--space-4);
  width: 32px; height: 32px;
  background: transparent; border: 1px solid transparent;
  border-radius: var(--radius-md);
  color: var(--color-text-3);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  transition: background var(--duration-base) var(--ease), color var(--duration-base) var(--ease);
}
.modal-close:hover { background: var(--color-surface-2); color: var(--color-text); }
.modal-close:focus-visible { outline: 2px solid var(--color-accent); outline-offset: 2px; }
```

## 7. 反 pattern（专属）

- ❌ 弹窗背景全白（用 `--color-bg` 纸白底气质柔和）
- ❌ 标题用无衬线（弹窗主标题必衬线，强化"深度阅读"感）
- ❌ ECharts 默认蓝紫调（必须替换为 `platformColors` / `sentimentColors`）
- ❌ 文章列表加交错斑马底（用 `--color-border-soft` 1px 分隔即可）
- ❌ 关闭按钮用红色或大号 X

## 8. 检查清单（专属）

- [ ] 标题字体为衬线 `var(--font-display)`
- [ ] 时间数字用等宽 `var(--font-mono)` + tabular-nums
- [ ] ECharts 主题色已替换为本文件 platform/sentiment 调色板
- [ ] 文章 hover 用底色变化不用 transform
- [ ] 关闭按钮 focus-visible 有可见 outline
- [ ] 移动端 modal 全屏 + body 内容可滚动

# 页面覆盖：AI 助手 (AIConsultant)

> 适用范围：AI 助手主面板，含早报 banner、推送中心、Agent 对话、思考链 (AgentTrace)。
> **覆盖** MASTER.md 中冲突的规则。

---

## 1. 三个区域的视觉层级

AI 助手是"信息漏斗"，从上到下层级要明确：

| 区 | 视觉权重 | token 选择 |
|---|---|---|
| 早报 banner | 强（限时/今日要事） | `--color-accent-soft` 暖底 + `--color-accent` 边/icon |
| 推送中心 (alerts) | 中（按 critical/warning/info 三级） | 沿用 U2 的浅色填充 + 左 border |
| Agent 对话 | 弱（中性背景，让对话内容当主角） | `--color-surface` 卡片 + `--color-border` 描边 |

## 2. 早报 banner（沿用 + 校准）

现状已用 `linear-gradient(135deg, #fef3c7, #fde68a)` 暖橙渐变，与 MASTER 颜色一致，**保留**。仅调整：
- 主按钮"查看早报"改为 `.btn-accent`（赤陶红）保持品牌一致
- "导出 PDF"小按钮改为 `.btn-secondary`（白底描边），不要红色描边

## 3. 推送中心 (alerts) — U2 已落地，做色彩对齐

| level | 现状 | 与 MASTER 一致性 |
|---|---|---|
| critical | 浅红 + 红描边 + ⚠️ icon | ✅ `--color-critical` |
| warning | 浅橙 + 橙描边 + ⚡ icon | ✅ `--color-warning` |
| info | 浅蓝 + 蓝描边 + 🔔 icon | ✅ `--color-info` |

**保留**所有 U2/U3 实现，无需重做。

## 4. Agent 对话气泡

去掉 daisyUI 默认蓝色 primary，改用近墨主色：

```css
/* 用户消息：右侧，近墨色块 + 反白文 */
.msg-user-text {
  background: var(--color-brand);
  color: var(--color-text-on-dark);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  border-top-right-radius: var(--radius-sm);   /* 微差异表明方向 */
  font: 400 var(--text-base)/1.6 var(--font-body);
  max-width: 80%;
}

/* AI 消息：左侧，白底 + 描边，让内容主角 */
.message-block.bg-base-100 {
  background: var(--color-surface) !important;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  border-top-left-radius: var(--radius-sm);
  padding: var(--space-4) var(--space-5);
  font: 400 var(--text-base)/1.7 var(--font-body);
}

/* Agent meta chip：弱化，避免抢戏 */
.agent-meta-chip {
  background: transparent;
  color: var(--color-text-2);
  padding: 0;
  font: 500 var(--text-xs)/1 var(--font-body);
  letter-spacing: 0.04em;
}
.agent-meta-chip iconify-icon { color: var(--color-accent); }   /* 仅 icon 用赤陶红 */
```

## 5. AgentTrace 思考链 — U1 已落地，做色彩对齐

折叠摘要条 (`trace-collapsed-bar`) 现用绿+蓝渐变，与编辑感冲突，改为：

```css
.trace-collapsed-bar {
  background: var(--color-surface-2);            /* 中性次级面，去渐变 */
  border: 1px solid var(--color-border);
  color: var(--color-text);
}
.trace-collapsed-bar:hover {
  background: var(--color-surface);
  border-color: var(--color-text-3);
}
.trace-collapsed-icon { color: var(--color-success); }   /* 完成 = 成功色 */
.trace-collapsed-label { color: var(--color-text); }     /* 不再绿色加粗 */
.trace-collapsed-tools { color: var(--color-text-2); font: 500 var(--text-xs)/1 var(--font-mono); }
.trace-collapsed-time { color: var(--color-text-3); }
.trace-collapsed-expand { color: var(--color-data); }
```

展开态时间线 (`trace-timeline`)：
- 步骤左侧时间轴 line：`1px solid var(--color-border)`
- 步骤序号 marker：白底 + `--color-border` 描边 + 主文色数字
- 完成态 marker：底色 `--color-success`，反白数字
- "展开 LLM 推理"按钮：`.btn-ghost` 样式

## 6. 最终回答卡 (agent-final-card)

最终结论是 AI 助手页的 **payoff**，给一点品牌识别（左 border 用赤陶红）：

```css
.agent-final-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-accent);    /* 品牌识别 */
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  margin-top: var(--space-4);
}
.agent-final-head {
  display: flex; align-items: center; gap: var(--space-2);
  font: 500 var(--text-md)/1 var(--font-display);   /* 衬线小标题 */
  color: var(--color-text);
  margin-bottom: var(--space-3);
}
.agent-final-head iconify-icon { color: var(--color-accent); }
.agent-final-body {
  font: 400 var(--text-base)/1.75 var(--font-body);
  color: var(--color-text);
}
.agent-final-body :is(strong, b) { color: var(--color-text); font-weight: 600; }
.agent-final-body :is(h1, h2, h3) {
  font-family: var(--font-display);
  font-weight: 500;
  color: var(--color-text);
}
```

## 7. 输入框

```css
/* 让输入区像编辑器：贴底、白底、近墨边框 focus */
.composer-input { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.composer-input:focus-within { border-color: var(--color-brand); box-shadow: 0 0 0 3px rgba(15,23,42,0.06); }

/* 发送按钮 */
.composer-send { background: var(--color-brand); color: var(--color-text-on-dark); }
.composer-send:hover { background: #1F2937; }
.composer-send:disabled { background: var(--color-surface-2); color: var(--color-text-3); cursor: not-allowed; }
```

## 8. 反 pattern（专属）

- ❌ 用户气泡用蓝色 primary（改近墨）
- ❌ 思考链折叠条绿+蓝渐变（改中性）
- ❌ 追问建议 chip 用蓝色描边（改 `var(--color-border)` + hover `var(--color-accent-soft)`）
- ❌ 最终回答卡满屏紫红渐变背景（改白底 + 赤陶红 left border）

## 9. 检查清单（专属）

- [ ] 早报 / 推送 / 对话 三层视觉权重清晰
- [ ] AgentTrace 折叠条无渐变
- [ ] 用户气泡近墨 + 反白
- [ ] 最终回答卡用衬线小标题
- [ ] 等宽字体只用于：trace 工具名 / JSON 参数显示

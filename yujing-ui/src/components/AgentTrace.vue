<template>
  <div class="agent-trace">
    <div v-if="!steps.length && !isRunning" class="trace-empty">
      <iconify-icon icon="ri:compass-3-line" class="empty-icon" />
      <span>智能体尚未开始工作。提交一个问题或点击预设 query。</span>
    </div>

    <ol v-else class="trace-timeline">
      <li
        v-for="(step, idx) in steps"
        :key="`${step.stepIndex}-${step.toolName}-${idx}`"
        :class="['trace-step', `trace-step--${step.status}`]"
      >
        <div class="step-marker">
          <iconify-icon :icon="stepIcon(step)" />
        </div>
        <div class="step-body">
          <div class="step-head">
            <span class="step-label">步骤 {{ step.stepIndex + 1 }}</span>
            <code class="step-tool">{{ step.toolName }}</code>
            <span v-if="step.status === 'running'" class="step-status step-status--running">
              <span class="status-dot"></span>执行中…
            </span>
            <span v-else-if="step.status === 'done'" class="step-status step-status--done">
              <iconify-icon icon="ri:check-line" /> 完成 · {{ step.latencyMs }}ms
            </span>
            <span v-else-if="step.status === 'error'" class="step-status step-status--error">
              <iconify-icon icon="ri:error-warning-line" /> 失败 · {{ step.latencyMs }}ms
            </span>
          </div>

          <div class="step-args" v-if="step.args && Object.keys(step.args).length">
            <span class="args-label">参数</span>
            <code>{{ formatArgs(step.args) }}</code>
          </div>

          <div v-if="step.status === 'done'" class="step-output">
            <button
              class="output-toggle"
              type="button"
              @click="toggleStep(idx)"
            >
              <iconify-icon :icon="step.expanded ? 'ri:arrow-down-s-line' : 'ri:arrow-right-s-line'" />
              <span>{{ step.expanded ? '收起' : '展开' }}结果</span>
              <span class="output-summary">{{ outputSummary(step.output) }}</span>
            </button>
            <pre v-if="step.expanded" class="output-json">{{ formatOutput(step.output) }}</pre>
          </div>

          <div v-else-if="step.status === 'error'" class="step-error">
            <iconify-icon icon="ri:alert-line" />
            <span>{{ step.error }}</span>
          </div>
        </div>
      </li>

      <li v-if="thinkingActive" class="trace-step trace-step--thinking">
        <div class="step-marker">
          <iconify-icon icon="ri:loader-4-line" class="spin" />
        </div>
        <div class="step-body">
          <div class="step-head">
            <span class="step-label">思考中</span>
            <span class="step-status">LLM 正在分析下一步操作…</span>
          </div>
        </div>
      </li>
    </ol>

    <div v-if="terminated && !terminatedOK" class="trace-terminated">
      <iconify-icon icon="ri:alert-line" />
      <span>{{ terminatedMessage }}</span>
    </div>
  </div>
</template>

<script setup>
/**
 * AgentTrace · Agent 调用链时间线
 *
 * Props:
 *   - events: Array<Object>  来自 /api/agent/chat SSE 的原始事件流
 *   - isRunning: Boolean     是否正在流式接收中
 *
 * 本组件只负责**展示**。不发起网络请求，不存 state。
 * 由父组件（AgentConsole）负责 SSE 订阅，把事件列表以 prop 形式注入。
 *
 * 内部 computed `steps`:
 *   聚合 tool_call + tool_result 为单个 step entry，按 stepIndex 顺序。
 *   其它事件类型（llm_thinking/final/error/done）用于控制整体状态显示。
 */

import { computed, ref, watch } from "vue";

const props = defineProps({
  events: {
    type: Array,
    required: true,
  },
  isRunning: {
    type: Boolean,
    default: false,
  },
});

// 维护每个 step 的 expanded 状态（索引级别），避免 computed 重建丢失
const expandedMap = ref(new Map());

const steps = computed(() => {
  const list = [];
  for (const ev of props.events) {
    if (ev.type === "tool_call") {
      list.push({
        stepIndex: ev.step,
        toolName: ev.name,
        args: ev.args || {},
        status: "running",
        latencyMs: 0,
        output: null,
        error: null,
        expanded: false,
      });
    } else if (ev.type === "tool_result") {
      // 找最后一个同 step + 同 name 且 status=running 的条目更新
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const entry = list[i];
        if (entry.stepIndex === ev.step && entry.toolName === ev.name && entry.status === "running") {
          entry.status = ev.ok ? "done" : "error";
          entry.latencyMs = ev.latency_ms || 0;
          entry.output = ev.output;
          entry.error = ev.error;
          break;
        }
      }
    }
  }
  // 合并 expanded 状态
  return list.map((step, idx) => ({
    ...step,
    expanded: expandedMap.value.get(idx) || false,
  }));
});

const thinkingActive = computed(() => {
  if (!props.isRunning) return false;
  // 找最后一个 event：如果是 llm_thinking 则显示思考中
  const last = props.events[props.events.length - 1];
  return last && last.type === "llm_thinking";
});

const terminated = computed(() => {
  return props.events.some((e) => e.type === "done");
});

const terminatedOK = computed(() => {
  const done = props.events.find((e) => e.type === "done");
  return done && done.terminated_reason === "final";
});

const terminatedMessage = computed(() => {
  const done = props.events.find((e) => e.type === "done");
  if (!done) return "";
  const reason = done.terminated_reason || "";
  if (reason === "max_steps") return "已达最大步数限制，未能给出最终答案。";
  if (reason === "too_many_errors") return "工具连续失败过多，智能体终止。";
  if (reason === "error") return "调用出现致命错误。";
  return `终止原因：${reason}`;
});

function toggleStep(idx) {
  const next = new Map(expandedMap.value);
  next.set(idx, !(next.get(idx) || false));
  expandedMap.value = next;
}

function stepIcon(step) {
  if (step.status === "running") return "ri:loader-4-line";
  if (step.status === "error") return "ri:error-warning-line";
  // done：根据工具名给不同图标
  const iconMap = {
    search_events: "ri:search-2-line",
    search_articles: "ri:file-search-line",
    semantic_search_articles: "ri:brain-line",
    get_event_detail: "ri:file-list-3-line",
    get_morning_brief: "ri:sun-line",
    list_hot_platforms: "ri:bar-chart-box-line",
    analyze_event_sentiment: "ri:emotion-line",
    compare_events: "ri:scales-3-line",
  };
  return iconMap[step.toolName] || "ri:tools-line";
}

function formatArgs(args) {
  try {
    const entries = Object.entries(args)
      .filter(([, v]) => v !== null && v !== "" && v !== undefined)
      .map(([k, v]) => {
        const vs = typeof v === "string" ? `"${v}"` : JSON.stringify(v);
        return `${k}=${vs}`;
      });
    const joined = entries.join(", ");
    return joined.length > 120 ? joined.slice(0, 117) + "..." : joined;
  } catch {
    return JSON.stringify(args);
  }
}

function outputSummary(output) {
  if (!output) return "";
  if (typeof output !== "object") return String(output).slice(0, 80);
  // 各工具特定字段
  if (output.total !== undefined && output.events) {
    return `${output.total} 个事件 · top: ${output.events?.[0]?._title || ""}`.slice(0, 80);
  }
  if (output.total !== undefined && output.articles) {
    return `${output.total} 篇文章`;
  }
  if (output._title && output.article_count !== undefined) {
    return `${output._title} · ${output.article_count} 篇`;
  }
  if (output.overall_distribution) {
    const total = output.labelled_count || 0;
    const top = Object.entries(output.overall_distribution)
      .sort((a, b) => b[1] - a[1])[0];
    return top ? `${total} 篇打标 · 主情绪 ${top[0]} (${top[1]})` : `${total} 篇打标`;
  }
  if (output.platform_count !== undefined && output.platforms) {
    return `${output.platform_count} 个平台`;
  }
  if (output.events && output.comparison_summary) {
    return `对比 ${output.events.length} 个事件`;
  }
  if (output.has_content !== undefined) {
    return output.has_content ? "今日早报已缓存" : "今日早报未就绪";
  }
  return JSON.stringify(output).slice(0, 80);
}

function formatOutput(output) {
  try {
    return JSON.stringify(output, null, 2);
  } catch {
    return String(output);
  }
}

// 事件追加时自动展开最新步骤（可选 UX）
watch(
  () => props.events.length,
  () => {
    // noop，保留钩子便于未来加"自动滚到底部"之类行为
  },
);
</script>

<style scoped>
/**
 * 主题兼容策略：
 *  - 不硬编码具体 #hex 背景色，用 `currentColor` 继承父容器，或 `rgba(0,0,0,0.03-0.08)`
 *    这种透明灰叠加色（浅色主题下柔和，深色主题下也能看清）。
 *  - 状态色（success/error/info/warning）用固定的中性明度色值（#16a34a 等），
 *    这些在浅色+深色主题都有足够对比度。
 *  - 文字色用 `color: inherit`，让 daisyUI 的 text-base-content 流下来。
 */

.agent-trace {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  color: inherit;
}

.trace-empty {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 1.25rem 1.5rem;
  background: rgba(37, 99, 235, 0.06);
  border: 1px dashed rgba(148, 163, 184, 0.35);
  border-radius: 12px;
  color: inherit;
  opacity: 0.8;
  font-size: 0.9rem;
}
.empty-icon {
  font-size: 1.4rem;
  color: #2563eb;
}

.trace-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  position: relative;
}
.trace-timeline::before {
  content: "";
  position: absolute;
  left: 17px;
  top: 16px;
  bottom: 16px;
  width: 2px;
  background: linear-gradient(to bottom, rgba(37, 99, 235, 0.3), rgba(148, 163, 184, 0.15));
}

.trace-step {
  position: relative;
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 0.75rem;
  padding: 0.75rem 0.9rem 0.75rem 0;
  background: rgba(0, 0, 0, 0.025);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  transition: border-color 0.15s, background 0.15s;
}
.trace-step--running {
  border-color: rgba(37, 99, 235, 0.4);
  background: rgba(37, 99, 235, 0.06);
}
.trace-step--done {
  border-color: rgba(22, 163, 74, 0.25);
  background: rgba(22, 163, 74, 0.04);
}
.trace-step--error {
  border-color: rgba(220, 38, 38, 0.45);
  background: rgba(220, 38, 38, 0.05);
}
.trace-step--thinking {
  border-color: rgba(147, 51, 234, 0.4);
  background: rgba(147, 51, 234, 0.05);
}

.step-marker {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid rgba(37, 99, 235, 0.4);
  color: #2563eb;
  font-size: 1.1rem;
  flex-shrink: 0;
  margin-left: -1px;
  z-index: 1;
  box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.02);
}
.trace-step--running .step-marker {
  border-color: #2563eb;
  color: #2563eb;
}
.trace-step--done .step-marker {
  border-color: #16a34a;
  color: #16a34a;
}
.trace-step--error .step-marker {
  border-color: #dc2626;
  color: #dc2626;
}
.trace-step--thinking .step-marker {
  border-color: #9333ea;
  color: #9333ea;
}

.step-body {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  min-width: 0;
}

.step-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.step-label {
  font-size: 0.75rem;
  color: inherit;
  opacity: 0.65;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.step-tool {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.86rem;
  color: inherit;
  background: rgba(0, 0, 0, 0.06);
  padding: 0.15rem 0.5rem;
  border-radius: 6px;
  font-weight: 600;
}
.step-status {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.78rem;
  padding: 0.1rem 0.55rem;
  border-radius: 999px;
}
.step-status--running {
  color: #2563eb;
  background: rgba(37, 99, 235, 0.12);
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2563eb;
  animation: pulse 1.2s ease-in-out infinite;
}
.step-status--done {
  color: #16a34a;
  background: rgba(22, 163, 74, 0.12);
}
.step-status--error {
  color: #dc2626;
  background: rgba(220, 38, 38, 0.12);
}

.step-args {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  font-size: 0.82rem;
  color: inherit;
  opacity: 0.85;
}
.args-label {
  opacity: 0.65;
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.step-args code {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  color: inherit;
  background: transparent;
}

.step-output {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.output-toggle {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.6rem;
  border: 1px solid rgba(0, 0, 0, 0.1);
  background: rgba(0, 0, 0, 0.03);
  border-radius: 8px;
  color: inherit;
  font-size: 0.82rem;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  text-align: left;
  width: 100%;
}
.output-toggle:hover {
  background: rgba(37, 99, 235, 0.06);
  border-color: rgba(37, 99, 235, 0.35);
}
.output-summary {
  opacity: 0.65;
  margin-left: 0.5rem;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.78rem;
}

.output-json {
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 0.76rem;
  line-height: 1.55;
  color: inherit;
  background: rgba(0, 0, 0, 0.04);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  padding: 0.7rem 0.9rem;
  max-height: 320px;
  overflow: auto;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.step-error {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  color: #dc2626;
  font-size: 0.85rem;
  padding: 0.4rem 0.6rem;
  background: rgba(220, 38, 38, 0.08);
  border-radius: 6px;
}

.trace-terminated {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 0.9rem;
  background: rgba(220, 38, 38, 0.08);
  border: 1px solid rgba(220, 38, 38, 0.3);
  border-radius: 10px;
  color: #dc2626;
  font-size: 0.88rem;
}

.spin {
  animation: spin 1s linear infinite;
  display: inline-block;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
@keyframes pulse {
  0%, 100% { opacity: 0.4; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.2); }
}

/* 深色主题自适应：如果外层 daisyUI data-theme=dark，用浅色覆盖 */
:global([data-theme="dark"]) .step-marker {
  background: #1e293b;
}
:global([data-theme="dark"]) .trace-step {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.08);
}
:global([data-theme="dark"]) .step-tool {
  background: rgba(255, 255, 255, 0.08);
}
:global([data-theme="dark"]) .output-toggle {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
}
:global([data-theme="dark"]) .output-json {
  background: rgba(0, 0, 0, 0.3);
  border-color: rgba(255, 255, 255, 0.1);
}
</style>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // sources: [{ source_id, name, latest_fetch_at(UTC ISO+Z), in_top_count, status: active|stale|missing }]
  sources: { type: Array, default: () => [] },
  // meta: { cross_platform_events, top_event_spread, new_24h }
  meta: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['select-source'])

// 北京时间 HH:MM 格式化（后端给 UTC ISO+Z，前端按 Asia/Shanghai 渲染）
const formatTime = (iso) => {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
      timeZone: 'Asia/Shanghai',
    })
  } catch {
    return '—'
  }
}

// 整体 "上次同步" = 8 源中最新一次（北京时间 HH:MM）
const overallLastSync = computed(() => {
  let latest = 0
  for (const s of props.sources) {
    if (s.latest_fetch_at) {
      const t = new Date(s.latest_fetch_at).getTime()
      if (t > latest) latest = t
    }
  }
  return latest > 0 ? formatTime(new Date(latest).toISOString()) : '—'
})

const activeCount = computed(() => props.sources.filter((s) => s.status === 'active').length)
const totalCount = computed(() => props.sources.length || 8)
</script>

<template>
  <div class="platform-status-bar" role="region" aria-label="平台同步状态">
    <!-- 左：8 平台状态点 -->
    <div class="status-dots">
      <button
        v-for="s in sources"
        :key="s.source_id"
        type="button"
        class="dot-btn"
        :class="['status-' + s.status]"
        :title="`${s.name} · ${s.status === 'missing' ? '尚无数据' : formatTime(s.latest_fetch_at) + ' 同步'} · 在榜 ${s.in_top_count} 条`"
        @click="emit('select-source', s.source_id)"
      >
        <span class="dot" />
      </button>
      <span class="dots-summary mono">{{ activeCount }}/{{ totalCount }}</span>
    </div>

    <!-- 中：分隔 -->
    <span class="bar-divider" />

    <!-- 右：3 个有意义的全局指标（mono 数字 + 暖灰中文标签） -->
    <div class="status-metrics">
      <div class="metric">
        <span class="metric-num mono">{{ meta.cross_platform_events ?? 0 }}</span>
        <span class="metric-label">跨平台事件</span>
      </div>
      <div class="metric">
        <span class="metric-num mono">{{ meta.top_event_spread ?? 0 }}</span>
        <span class="metric-label">最广覆盖（平台）</span>
      </div>
      <div class="metric">
        <span class="metric-num mono">{{ meta.new_24h ?? 0 }}</span>
        <span class="metric-label">24h 新增条目</span>
      </div>
      <span class="bar-divider hide-narrow" />
      <div class="metric metric-time">
        <span class="metric-label">上次同步</span>
        <span class="metric-num mono">{{ overallLastSync }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.platform-status-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  padding: 10px 32px;
  background: var(--color-surface-2, #F5F5F2);
  border-bottom: 1px solid var(--color-border-soft, #EFEFEA);
  font-size: 12px;
  color: var(--color-text-3, #A8A29E);
}

.status-dots {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dot-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
}
.dot {
  display: block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-text-3, #A8A29E);
  transition: background 200ms ease;
}
.status-active .dot {
  background: var(--color-accent, #B45309);
}
.status-stale .dot {
  background: var(--color-text-3, #A8A29E);
  opacity: 0.55;
}
.status-missing .dot {
  background: transparent;
  border: 1px dashed var(--color-text-3, #A8A29E);
  width: 7px;
  height: 7px;
  box-sizing: border-box;
}

.dots-summary {
  margin-left: 6px;
  font-size: 11px;
  color: var(--color-text-3, #A8A29E);
  letter-spacing: 0.04em;
}

.bar-divider {
  flex: 0 0 1px;
  align-self: stretch;
  background: var(--color-border-soft, #EFEFEA);
  min-height: 14px;
  margin: 0 4px;
}

.status-metrics {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}
.metric {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
}
.metric-time { gap: 8px; }
.metric-num {
  font-size: 14px;
  font-weight: 700;
  color: #1c1917;
  letter-spacing: 0;
}
.metric-label {
  font-size: 11px;
  color: var(--color-text-3, #A8A29E);
  letter-spacing: 0.02em;
}

.mono {
  font-family: var(--font-mono, "JetBrains Mono", "SFMono-Regular", Menlo, Consolas, monospace);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 900px) {
  .platform-status-bar { padding: 10px 16px; gap: 12px; }
  .status-metrics { gap: 14px; }
  .hide-narrow { display: none; }
}
</style>

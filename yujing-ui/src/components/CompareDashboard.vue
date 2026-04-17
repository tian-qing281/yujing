<template>
  <section v-if="metrics" class="compare-dashboard">
    <header class="cmp-head">
      <span class="cmp-head-icon">
        <iconify-icon icon="mdi:scale-balance" />
      </span>
      <h3>{{ metrics.a.label }} <em>vs</em> {{ metrics.b.label }}</h3>
    </header>

    <!-- 双列对比卡片 -->
    <div class="cmp-grid">
      <article
        v-for="side in ['a', 'b']"
        :key="side"
        class="cmp-col"
        :class="side === winnerSide ? 'is-leading' : ''"
      >
        <div class="cmp-col-head">
          <span class="cmp-side-tag">{{ side === 'a' ? '左侧' : '右侧' }}</span>
          <h4>{{ metrics[side].label }}</h4>
          <span v-if="side === winnerSide" class="cmp-badge">热度领先</span>
        </div>

        <!-- 指标方阵 -->
        <dl class="cmp-metrics">
          <div class="cmp-metric">
            <dt>相关情报</dt>
            <dd>
              <strong>{{ metrics[side].article_count }}</strong>
              <span class="cmp-unit">条</span>
            </dd>
          </div>
          <div class="cmp-metric">
            <dt>覆盖平台</dt>
            <dd>
              <strong>{{ metrics[side].platform_count }}</strong>
              <span class="cmp-unit">个</span>
            </dd>
          </div>
          <div class="cmp-metric">
            <dt>24h 变化</dt>
            <dd>
              <strong
                :class="trendClass(metrics[side].trend_24h.pct)"
              >
                {{ formatTrend(metrics[side].trend_24h) }}
              </strong>
            </dd>
          </div>
          <div class="cmp-metric">
            <dt>关联事件</dt>
            <dd>
              <strong>{{ metrics[side].event_count }}</strong>
              <span class="cmp-unit">个</span>
            </dd>
          </div>
        </dl>

        <!-- 情绪分布 bar -->
        <div class="cmp-sentiment">
          <div class="cmp-sub-title">情绪分布</div>
          <div class="cmp-sent-bar">
            <span
              v-for="bucket in sentimentBuckets(metrics[side].sentiment)"
              :key="bucket.key"
              class="cmp-sent-seg"
              :style="{
                flex: bucket.pct,
                background: bucket.color,
              }"
              :title="`${bucket.label}: ${bucket.count} 条`"
            ></span>
          </div>
          <div class="cmp-sent-legend">
            <span
              v-for="bucket in sentimentBuckets(metrics[side].sentiment)"
              :key="bucket.key"
              class="cmp-sent-chip"
            >
              <span class="cmp-sent-dot" :style="{ background: bucket.color }"></span>
              {{ bucket.label }} {{ bucket.count }}
            </span>
          </div>
        </div>

        <!-- 代表情报 -->
        <div class="cmp-reps" v-if="metrics[side].representative_articles?.length">
          <div class="cmp-sub-title">代表情报</div>
          <ul>
            <li
              v-for="rep in metrics[side].representative_articles.slice(0, 3)"
              :key="rep.id"
              @click="$emit('open-article', rep)"
            >
              <span class="cmp-rep-src">{{ rep.source_name || rep.source_id }}</span>
              <span class="cmp-rep-title">{{ rep.title }}</span>
            </li>
          </ul>
        </div>
      </article>
    </div>

    <!-- 7 日双曲线图 -->
    <div class="cmp-chart-wrap">
      <div class="cmp-sub-title">近 7 日热度演化</div>
      <div ref="chartRef" class="cmp-chart"></div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from "vue";

const props = defineProps({
  metrics: { type: Object, default: null },
});

defineEmits(["open-article"]);

const chartRef = ref(null);
let chartInst = null;

const winnerSide = computed(() => {
  if (!props.metrics) return "";
  const a = props.metrics.a.article_count || 0;
  const b = props.metrics.b.article_count || 0;
  if (a === b) return "";
  return a > b ? "a" : "b";
});

const SENT_META = {
  positive: { label: "正向", color: "#22c55e" },
  neutral: { label: "中性", color: "#94a3b8" },
  negative: { label: "负向", color: "#ef4444" },
  surprise: { label: "惊讶", color: "#f59e0b" },
};

const sentimentBuckets = (obj) => {
  const entries = Object.entries(obj || {});
  const total = entries.reduce((sum, [, v]) => sum + v, 0) || 1;
  const order = ["positive", "neutral", "surprise", "negative"];
  return order
    .filter((k) => (obj?.[k] || 0) > 0)
    .map((k) => ({
      key: k,
      count: obj[k],
      pct: Math.max(obj[k] / total, 0.04),
      label: SENT_META[k]?.label || k,
      color: SENT_META[k]?.color || "#94a3b8",
    }));
};

const formatTrend = (trend) => {
  if (!trend || trend.pct === null || trend.pct === undefined) {
    return trend?.current ? `+${trend.current}` : "—";
  }
  if (trend.pct > 0) return `↑ ${trend.pct}%`;
  if (trend.pct < 0) return `↓ ${Math.abs(trend.pct)}%`;
  return "持平";
};

const trendClass = (pct) => {
  if (pct === null || pct === undefined) return "";
  if (pct > 5) return "trend-up";
  if (pct < -5) return "trend-down";
  return "";
};

const renderChart = async () => {
  if (!props.metrics || !chartRef.value) return;
  if (!window.echarts) {
    // 兜底：若 echarts 尚未加载，延迟一次
    await new Promise((r) => setTimeout(r, 200));
    if (!window.echarts) return;
  }
  if (!chartInst) {
    chartInst = window.echarts.init(chartRef.value, null, { renderer: "canvas" });
  }
  const a = props.metrics.a.timeline || [];
  const b = props.metrics.b.timeline || [];
  const xAxis = a.map((d) => d.date);

  chartInst.setOption({
    animation: true,
    animationDuration: 900,
    animationEasing: "cubicOut",
    animationDelay: (i) => i * 60,
    grid: { top: 28, right: 18, bottom: 30, left: 36 },
    legend: {
      top: 0,
      right: 0,
      textStyle: { color: "#475569", fontSize: 12 },
      icon: "roundRect",
    },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: xAxis,
      axisLabel: { color: "#94a3b8", fontSize: 11 },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#94a3b8", fontSize: 11 },
      splitLine: { lineStyle: { color: "#f1f5f9" } },
    },
    series: [
      {
        name: props.metrics.a.label,
        type: "line",
        smooth: true,
        data: a.map((d) => d.count),
        itemStyle: { color: "#3b82f6" },
        areaStyle: { color: "rgba(59, 130, 246, 0.12)" },
        symbolSize: 6,
      },
      {
        name: props.metrics.b.label,
        type: "line",
        smooth: true,
        data: b.map((d) => d.count),
        itemStyle: { color: "#a855f7" },
        areaStyle: { color: "rgba(168, 85, 247, 0.12)" },
        symbolSize: 6,
      },
    ],
  });
};

onMounted(async () => {
  await nextTick();
  renderChart();
});

watch(
  () => props.metrics,
  async () => {
    await nextTick();
    renderChart();
  },
  { deep: true }
);

onBeforeUnmount(() => {
  if (chartInst) {
    chartInst.dispose();
    chartInst = null;
  }
});
</script>

<style scoped>
.compare-dashboard {
  border: 1px solid rgba(99, 102, 241, 0.18);
  border-radius: 14px;
  padding: 16px 18px 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f8faff 100%);
  margin: 12px 0;
  animation: cmp-fade-in 0.5s ease-out;
}

@keyframes cmp-fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.cmp-col {
  animation: cmp-slide-in 0.5s ease-out backwards;
}
.cmp-col:nth-child(1) { animation-delay: 0.1s; }
.cmp-col:nth-child(2) { animation-delay: 0.2s; }

@keyframes cmp-slide-in {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

.cmp-metric {
  animation: cmp-metric-pop 0.4s ease-out backwards;
}
.cmp-col .cmp-metric:nth-child(1) { animation-delay: 0.25s; }
.cmp-col .cmp-metric:nth-child(2) { animation-delay: 0.3s; }
.cmp-col .cmp-metric:nth-child(3) { animation-delay: 0.35s; }
.cmp-col .cmp-metric:nth-child(4) { animation-delay: 0.4s; }

@keyframes cmp-metric-pop {
  from { opacity: 0; transform: scale(0.92); }
  to { opacity: 1; transform: scale(1); }
}

.cmp-chart-wrap {
  animation: cmp-fade-in 0.5s ease-out 0.45s backwards;
}
.cmp-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
}
.cmp-head h3 {
  font-size: 15px;
  font-weight: 800;
  color: #1e293b;
  margin: 0;
  letter-spacing: 0.2px;
}
.cmp-head em { font-style: normal; color: #7c3aed; margin: 0 6px; font-weight: 700; }
.cmp-head-icon {
  width: 28px; height: 28px; border-radius: 8px;
  display: inline-flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #3b82f6, #a855f7); color: #fff; font-size: 18px;
}

.cmp-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
@media (max-width: 720px) {
  .cmp-grid { grid-template-columns: 1fr; }
}

.cmp-col {
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  padding: 14px;
  background: #fff;
  position: relative;
  transition: border-color 0.15s ease;
}
.cmp-col.is-leading { border-color: rgba(59, 130, 246, 0.45); box-shadow: 0 6px 18px rgba(59, 130, 246, 0.1); }

.cmp-col-head {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px;
}
.cmp-col-head h4 {
  font-size: 14px; font-weight: 800; color: #0f172a; margin: 0; flex: 1;
}
.cmp-side-tag {
  font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px;
  background: #f1f5f9; color: #64748b; letter-spacing: 0.5px;
}
.cmp-badge {
  font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 999px;
  background: linear-gradient(135deg, #3b82f6, #a855f7); color: #fff;
}

.cmp-metrics {
  display: grid; grid-template-columns: repeat(2, 1fr);
  gap: 10px; margin: 0 0 14px; padding: 0;
}
.cmp-metric {
  background: #f8fafc; border-radius: 8px; padding: 10px 12px;
}
.cmp-metric dt {
  font-size: 11px; color: #94a3b8; font-weight: 700; margin-bottom: 4px;
  letter-spacing: 0.3px;
}
.cmp-metric dd {
  margin: 0; display: flex; align-items: baseline; gap: 4px;
}
.cmp-metric dd strong {
  font-size: 20px; font-weight: 800; color: #0f172a;
}
.cmp-metric dd strong.trend-up { color: #16a34a; }
.cmp-metric dd strong.trend-down { color: #dc2626; }
.cmp-unit { font-size: 11px; color: #94a3b8; font-weight: 600; }

.cmp-sub-title {
  font-size: 11px; font-weight: 700; color: #64748b;
  letter-spacing: 0.4px; margin-bottom: 6px;
}

.cmp-sentiment { margin-bottom: 12px; }
.cmp-sent-bar {
  display: flex; height: 8px; border-radius: 999px; overflow: hidden;
  background: #f1f5f9;
}
.cmp-sent-seg { transition: flex 0.3s ease; }
.cmp-sent-legend {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px;
}
.cmp-sent-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: #475569; font-weight: 600;
}
.cmp-sent-dot {
  width: 8px; height: 8px; border-radius: 999px;
}

.cmp-reps ul { list-style: none; padding: 0; margin: 6px 0 0; }
.cmp-reps li {
  display: flex; gap: 8px; padding: 6px 8px;
  border-radius: 6px; cursor: pointer;
  transition: background 0.15s ease;
  font-size: 12px; line-height: 1.5;
}
.cmp-reps li:hover { background: #eff6ff; }
.cmp-rep-src {
  flex-shrink: 0; font-weight: 700; color: #3b82f6; font-size: 11px;
}
.cmp-rep-title { color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.cmp-chart-wrap {
  margin-top: 14px; padding: 12px; border-radius: 10px;
  background: #fff; border: 1px solid rgba(148, 163, 184, 0.2);
}
.cmp-chart { height: 200px; }
</style>

<template>
  <!-- 分支 1：N 平台雷达图（_type === 'platform_radar'） -->
  <section v-if="isRadar" class="compare-dashboard radar-mode">
    <header class="cmp-head">
      <span class="cmp-head-icon">
        <iconify-icon icon="mdi:radar" />
      </span>
      <h3>
        多平台舆情画像
        <em v-if="metrics.topic">· {{ metrics.topic }}</em>
      </h3>
    </header>

    <div class="radar-layout">
      <div ref="chartRef" class="cmp-chart radar-chart"></div>

      <div class="radar-side">
        <div class="leader-block">
          <div class="cmp-sub-title">各维度领先平台</div>
          <ul class="leader-list">
            <li v-for="(l, i) in metrics.leaders" :key="i">
              <span class="leader-dim">{{ l.dim_name }}</span>
              <span class="leader-name">{{ l.label }}</span>
              <span class="leader-score">{{ l.score }}</span>
            </li>
          </ul>
        </div>

        <div class="raw-block">
          <div class="cmp-sub-title">原始数据</div>
          <table class="radar-raw">
            <thead>
              <tr><th>平台</th><th>情报</th><th>事件</th><th>正向</th></tr>
            </thead>
            <tbody>
              <tr v-for="p in metrics.platforms" :key="p.label">
                <td>{{ p.label }}</td>
                <td>{{ p.raw.article_count }}</td>
                <td>{{ p.raw.event_count }}</td>
                <td>{{ p.raw.sentiment.positive || 0 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </section>

  <!-- 分支 2：双平台对比（兼容旧 schema） -->
  <section v-else-if="metrics" class="compare-dashboard">
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
              <strong><NumberFlow :value="Number(metrics[side].article_count) || 0" /></strong>
              <span class="cmp-unit">条</span>
            </dd>
          </div>
          <div class="cmp-metric">
            <dt>覆盖平台</dt>
            <dd>
              <strong><NumberFlow :value="Number(metrics[side].platform_count) || 0" /></strong>
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
              <strong><NumberFlow :value="Number(metrics[side].event_count) || 0" /></strong>
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
import NumberFlow from "@number-flow/vue";

const props = defineProps({
  metrics: { type: Object, default: null },
});

defineEmits(["open-article"]);

const chartRef = ref(null);
let chartInst = null;

// 新 schema（N 平台雷达）：metrics._type === 'platform_radar'
// 旧 schema（双平台对比）：metrics.a / metrics.b
const isRadar = computed(() => props.metrics?._type === "platform_radar");

const winnerSide = computed(() => {
  if (!props.metrics || isRadar.value) return "";
  const a = props.metrics.a?.article_count || 0;
  const b = props.metrics.b?.article_count || 0;
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
    await new Promise((r) => setTimeout(r, 200));
    if (!window.echarts) return;
  }
  // 若 chartInst 之前绑的 DOM 因 v-if 切换已经不是当前 chartRef.value，重建一次。
  if (chartInst && chartInst.getDom && chartInst.getDom() !== chartRef.value) {
    chartInst.dispose();
    chartInst = null;
  }
  if (!chartInst) {
    chartInst = window.echarts.init(chartRef.value, null, { renderer: "canvas" });
  }

  // 雷达分支：N 平台 5 维
  if (isRadar.value) {
    const palette = ["#B45309", "#0EA5E9", "#22C55E", "#A855F7", "#EAB308", "#EC4899"];
    const indicators = (props.metrics.dimensions || []).map((d) => ({
      name: d,
      max: 100,
    }));
    const series = (props.metrics.platforms || []).map((p, i) => ({
      name: p.label,
      type: "radar",
      data: [{ value: p.scores, name: p.label }],
      itemStyle: { color: palette[i % palette.length] },
      lineStyle: { color: palette[i % palette.length], width: 2 },
      areaStyle: { color: palette[i % palette.length], opacity: 0.12 },
      symbolSize: 5,
    }));
    chartInst.setOption(
      {
        animation: true,
        animationDuration: 900,
        animationEasing: "cubicOut",
        legend: {
          top: 0,
          left: "center",
          textStyle: { color: "#475569", fontSize: 12 },
          icon: "roundRect",
        },
        tooltip: { trigger: "item" },
        radar: {
          indicator: indicators,
          shape: "polygon",
          splitNumber: 4,
          center: ["50%", "55%"],
          radius: "65%",
          axisName: { color: "#475569", fontSize: 12 },
          splitLine: { lineStyle: { color: "#e2e8f0" } },
          splitArea: { areaStyle: { color: ["#fafbfc", "#ffffff"] } },
          axisLine: { lineStyle: { color: "#e2e8f0" } },
        },
        series,
      },
      true /* notMerge：切换 schema 时清空旧 option */
    );
    // 双 raf 兜底：容器在 v-if 切换后宽度通常需 1-2 帧才稳定
    requestAnimationFrame(() => requestAnimationFrame(() => chartInst && chartInst.resize()));
    return;
  }

  // 旧分支：双平台 7 日时间轴
  const a = props.metrics.a.timeline || [];
  const b = props.metrics.b.timeline || [];
  const xAxis = a.map((d) => d.date);

  chartInst.setOption(
    {
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
          itemStyle: { color: "#B45309" },
          lineStyle: { color: "#B45309", width: 2 },
          areaStyle: { color: "rgba(180, 83, 9, 0.10)" },
          symbolSize: 6,
        },
        {
          name: props.metrics.b.label,
          type: "line",
          smooth: true,
          data: b.map((d) => d.count),
          itemStyle: { color: "#78716C" },
          lineStyle: { color: "#78716C", width: 2, type: "dashed" },
          areaStyle: { color: "rgba(120, 113, 108, 0.08)" },
          symbolSize: 6,
        },
      ],
    },
    true
  );
};

let resizeObs = null;

onMounted(async () => {
  await nextTick();
  renderChart();
  // ResizeObserver 兜底：父气泡布局（agent_trace 折叠 / 图片懒加载等）会异步改变
  // chart 容器尺寸；监听容器尺寸变化时主动 resize，防止雷达图被压扁。
  if (chartRef.value && typeof ResizeObserver !== "undefined") {
    resizeObs = new ResizeObserver(() => {
      if (chartInst) chartInst.resize();
    });
    resizeObs.observe(chartRef.value);
  }
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
  if (resizeObs) {
    resizeObs.disconnect();
    resizeObs = null;
  }
  if (chartInst) {
    chartInst.dispose();
    chartInst = null;
  }
});
</script>

<style scoped>
.compare-dashboard {
  border: 1px solid var(--color-border, #E5E5DD);
  border-radius: 0;
  border-top: 3px solid var(--color-accent);
  padding: 16px 18px 18px;
  background: var(--color-surface, #fff);
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
  color: var(--color-text-1, #1c1917);
  margin: 0;
  letter-spacing: -0.01em;
  font-family: var(--font-display, "Noto Serif SC", serif);
}
.cmp-head em { font-style: normal; color: var(--color-accent); margin: 0 6px; font-weight: 700; }
.cmp-head-icon {
  width: 28px; height: 28px; border-radius: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: transparent; color: var(--color-accent); border: 1px solid var(--color-accent); font-size: 18px;
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
  border: 1px solid var(--color-border, #E5E5DD);
  border-radius: 0;
  padding: 14px;
  background: var(--color-surface, #fff);
  position: relative;
  transition: border-color 0.18s ease;
  min-width: 0;
  overflow: hidden;
}
.cmp-col.is-leading { border-color: var(--color-accent); box-shadow: none; }
.cmp-col.is-leading::before {
  content: "";
  position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--color-accent);
}

.cmp-col-head {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px;
}
.cmp-col-head h4 {
  font-size: 14px; font-weight: 800; color: var(--color-text-1, #1c1917); margin: 0; flex: 1;
  font-family: var(--font-display, "Noto Serif SC", serif);
}
.cmp-side-tag {
  font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 0;
  background: transparent; color: var(--color-text-3, #78716c); letter-spacing: 0.22em;
  text-transform: uppercase; border: 1px solid var(--color-border, #E5E5DD);
  font-family: var(--font-display, "Noto Serif SC", serif);
}
.cmp-badge {
  font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 0;
  background: transparent; color: var(--color-accent); border: 1px solid var(--color-accent);
  letter-spacing: 0.22em; text-transform: uppercase;
  font-family: var(--font-display, "Noto Serif SC", serif);
}

.cmp-metrics {
  display: grid; grid-template-columns: repeat(2, 1fr);
  gap: 10px; margin: 0 0 14px; padding: 0;
}
.cmp-metric {
  background: var(--color-surface-2, #F5F5F2); border-radius: 0;
  border: 1px solid var(--color-border, #E5E5DD);
  padding: 10px 12px;
}
.cmp-metric dt {
  font-size: 10px; color: var(--color-accent, #B45309); font-weight: 700; margin-bottom: 4px;
  letter-spacing: 0.22em; text-transform: uppercase;
  font-family: var(--font-display, "Noto Serif SC", serif);
}
.cmp-metric dd {
  margin: 0; display: flex; align-items: baseline; gap: 4px;
}
.cmp-metric dd strong {
  font-size: 20px; font-weight: 800; color: var(--color-text-1, #1c1917);
  font-variant-numeric: tabular-nums;
  font-family: var(--font-display, "Noto Serif SC", serif);
}
.cmp-metric dd strong.trend-up { color: #047857; }
.cmp-metric dd strong.trend-down { color: #b91c1c; }
.cmp-unit { font-size: 11px; color: var(--color-text-3, #78716c); font-weight: 600; }

.cmp-sub-title {
  font-size: 10px; font-weight: 700; color: var(--color-accent, #B45309);
  letter-spacing: 0.22em; text-transform: uppercase; margin-bottom: 8px;
  font-family: var(--font-display, "Noto Serif SC", serif);
}

.cmp-sentiment { margin-bottom: 12px; }
.cmp-sent-bar {
  display: flex; height: 6px; border-radius: 0; overflow: hidden;
  background: var(--color-surface-2, #F5F5F2);
  border: 1px solid var(--color-border, #E5E5DD);
}
.cmp-sent-seg { transition: flex 0.3s ease; }
.cmp-sent-legend {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px;
}
.cmp-sent-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: var(--color-text-2, #475569); font-weight: 600;
}
.cmp-sent-dot {
  width: 8px; height: 8px; border-radius: 0;
}

.cmp-reps ul { list-style: none; padding: 0; margin: 6px 0 0; }
.cmp-reps li {
  display: flex; gap: 8px; padding: 6px 8px;
  border-radius: 0; cursor: pointer;
  border-left: 2px solid transparent;
  transition: background 0.15s ease, border-color 0.15s ease;
  font-size: 12px; line-height: 1.5;
  min-width: 0;
}
.cmp-reps li:hover { background: var(--color-surface-2); border-left-color: var(--color-accent); }
.cmp-rep-src {
  flex-shrink: 0; font-weight: 700; color: var(--color-accent); font-size: 10px;
  letter-spacing: 0.18em; text-transform: uppercase;
  font-family: var(--font-display, "Noto Serif SC", serif);
}
.cmp-rep-title {
  flex: 1; min-width: 0;
  color: var(--color-text-1, #1c1917);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.cmp-chart-wrap {
  margin-top: 14px; padding: 12px; border-radius: 0;
  background: var(--color-surface, #fff); border: 1px solid var(--color-border, #E5E5DD);
}
.cmp-chart { height: 200px; }

/* === N 平台雷达图模式 === */
.compare-dashboard.radar-mode { padding: 16px 18px; }
.radar-layout {
  /* 上下布局：雷达图在上方占满宽度，leader / 原始数据在下方
     之前用 grid 双列在窄气泡里会塌成 0 宽导致 ECharts canvas 不可见 */
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 12px;
}
.radar-chart {
  width: 100%;
  min-width: 0;
  height: 380px;
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #E5E5DD);
  border-radius: 0;
  padding: 8px;
  box-sizing: border-box;
}
.radar-side {
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border, #E5E5DD);
  border-radius: 0;
  padding: 12px 14px;
  font-size: 12px;
  /* UI-18 修复（2026-05-19）：原 2 列 grid 在 AI 助手对话流深处（消息气泡 ~600px、雷达图占一半后侧栏仅 ~250px）会被挤压成两个 125px 窄列，
     导致 leader-list 行内 dim/name/score flex 撑爆、radar-raw 4 列表头被拆成单字竖排。改为单列垂直排，leader-block 在上 / raw-block 在下。 */
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.radar-side > .leader-block { min-width: 0; }
.radar-side > .raw-block { min-width: 0; }
.leader-list {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.leader-list li {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px;
  border-radius: 0;
  border-left: 2px solid var(--color-accent);
  background: var(--color-surface-2, #F5F5F2);
}
.leader-dim { color: var(--color-text-3, #78716c); min-width: 76px; font-size: 11px; letter-spacing: 0.08em; }
.leader-name { color: var(--color-accent, #B45309); font-weight: 700; flex: 1; }
.leader-score {
  color: var(--color-text-1, #1c1917); font-variant-numeric: tabular-nums;
  background: var(--color-surface, #fff); border: 1px solid var(--color-border, #E5E5DD);
  padding: 1px 6px; border-radius: 0;
}
.radar-raw {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-top: 6px;
}
.radar-raw th, .radar-raw td {
  text-align: left;
  padding: 4px 6px;
  border-bottom: 1px solid var(--color-border, #E5E5DD);
}
.radar-raw th { color: var(--color-accent, #B45309); font-weight: 700; font-size: 10px; letter-spacing: 0.22em; text-transform: uppercase; font-family: var(--font-display, "Noto Serif SC", serif); }
.radar-raw td { color: var(--color-text-1, #1c1917); font-variant-numeric: tabular-nums; }
</style>

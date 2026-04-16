<template>
  <section v-if="hasData" class="search-insight card bg-base-100">
    <div class="card-body search-insight-body">
      <div class="insight-copy">
        <span class="badge badge-primary badge-outline">检索态势</span>
        <strong>{{ query }} 的全景分布</strong>
        <p>{{ leadText }}</p>
      </div>

      <div class="platform-strip" aria-label="命中平台">
        <span v-for="item in platformRows" :key="item.name" class="badge badge-outline badge-lg platform-pill">
          {{ item.name }} · {{ item.value }}
        </span>
      </div>

      <div class="chart-shell">
        <div class="chart-copy">
          <div class="mini-stats">
            <div class="mini-stat card bg-base-100">
              <div class="card-body">
                <span>热搜</span>
                <strong>{{ articleCount }}</strong>
              </div>
            </div>
            <div class="mini-stat card bg-base-100">
              <div class="card-body">
                <span>事件</span>
                <strong>{{ eventCount }}</strong>
              </div>
            </div>
            <div class="mini-stat card bg-base-100">
              <div class="card-body">
                <span>平台</span>
                <strong>{{ platformRows.length }}</strong>
              </div>
            </div>
            <div class="mini-stat card bg-base-100">
              <div class="card-body">
                <span>时间脉冲</span>
                <strong>{{ pulseCount }}</strong>
              </div>
            </div>
          </div>
          <div class="chart-copy-note">
            平台分布用于判断信息来自哪里，时间脉冲用于判断这批结果是在什么时候集中冒出来的。
          </div>
        </div>
        <div ref="chartRef" class="insight-chart" aria-label="搜索结果可视化"></div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { init, use } from "echarts/core";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps({
  query: { type: String, default: "" },
  summary: { type: Object, default: () => ({}) },
  platforms: { type: Array, default: () => [] },
  timeline: { type: Array, default: () => [] },
});

const chartRef = ref(null);
let chart = null;
let resizeObserver = null;
let renderFrame = null;

const normalizeCount = (value) => {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number : 0;
};

const eventCount = computed(() => normalizeCount(props.summary?.events));
const articleCount = computed(() => normalizeCount(props.summary?.articles));
const topicCount = computed(() => normalizeCount(props.summary?.topics));

const platformRows = computed(() =>
  props.platforms
    .map((item) => ({ name: item.label || item.value || "未知平台", value: normalizeCount(item.count) }))
    .filter((item) => item.value > 0)
    .slice(0, 6)
);

const timelineRows = computed(() =>
  props.timeline
    .map((item) => ({ name: item.label || item.name || "", value: normalizeCount(item.count || item.value) }))
    .filter((item) => item.name && item.value > 0)
    .slice(-10)
);

const hasData = computed(
  () => articleCount.value > 0 || eventCount.value > 0 || topicCount.value > 0 || platformRows.value.length || timelineRows.value.length
);

const platformLeadText = computed(() => platformRows.value.map((item) => item.name).slice(0, 3).join(" / "));
const pulseCount = computed(() => timelineRows.value.reduce((sum, item) => sum + item.value, 0));

const leadText = computed(() => {
  const platformCount = platformRows.value.length;
  const platformText = platformLeadText.value ? `主要平台：${platformLeadText.value}` : "当前暂无明显平台倾斜";
  return `命中 ${articleCount.value} 张情报卡、${eventCount.value} 个事件、${topicCount.value} 个专题，覆盖 ${platformCount} 个主要平台；${platformText}。`;
});

const getOption = () => ({
  backgroundColor: "transparent",
  animationDuration: 220,
  animationDurationUpdate: 160,
  color: ["#2563eb", "#06b6d4"],
  tooltip: {
    trigger: "axis",
    backgroundColor: "rgba(15, 23, 42, 0.94)",
    borderWidth: 0,
    textStyle: { color: "#f8fafc", fontSize: 12 },
  },
  grid: [
    { left: 90, right: 22, top: 20, height: 150, containLabel: true },
    { left: 44, right: 22, bottom: 18, height: 120, containLabel: true },
  ],
  xAxis: [
    { type: "value", show: false },
    {
      type: "category",
      gridIndex: 1,
      boundaryGap: false,
      data: timelineRows.value.map((item) => item.name),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "rgba(148, 163, 184, 0.2)" } },
      axisLabel: { color: "#94a3b8", fontSize: 10, fontWeight: 700 },
    },
  ],
  yAxis: [
    {
      type: "category",
      inverse: true,
      data: platformRows.value.map((item) => item.name),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: "#64748b", fontSize: 11, fontWeight: 700, width: 110, overflow: "truncate" },
    },
    {
      type: "value",
      gridIndex: 1,
      minInterval: 1,
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.12)" } },
      axisLabel: { color: "#94a3b8", fontSize: 10, fontWeight: 700 },
    },
  ],
  series: [
    {
      name: "平台分布",
      type: "bar",
      data: platformRows.value.map((item) => item.value),
      barWidth: 14,
      itemStyle: {
        borderRadius: 999,
        color: {
          type: "linear",
          x: 0,
          y: 0,
          x2: 1,
          y2: 0,
          colorStops: [
            { offset: 0, color: "#60a5fa" },
            { offset: 1, color: "#2563eb" },
          ],
        },
      },
      label: { show: true, position: "right", color: "#64748b", fontSize: 11, fontWeight: 800 },
    },
    {
      name: "时间脉冲",
      type: "line",
      xAxisIndex: 1,
      yAxisIndex: 1,
      data: timelineRows.value.map((item) => item.value),
      smooth: true,
      symbol: "circle",
      symbolSize: 7,
      lineStyle: { width: 3, color: "#06b6d4" },
      itemStyle: { color: "#06b6d4", borderWidth: 2, borderColor: "#ffffff" },
      areaStyle: { color: "rgba(6, 182, 212, 0.12)" },
    },
  ],
});

const ensureChart = async () => {
  if (!chartRef.value || !hasData.value) return;
  if (!chart) {
    chart = init(chartRef.value);
    resizeObserver = new ResizeObserver(() => chart?.resize());
    resizeObserver.observe(chartRef.value);
  }
  chart?.setOption(getOption(), { notMerge: true, lazyUpdate: true });
};

const scheduleRender = async () => {
  if (!hasData.value) {
    chart?.clear();
    return;
  }
  await nextTick();
  if (renderFrame) cancelAnimationFrame(renderFrame);
  renderFrame = requestAnimationFrame(() => {
    renderFrame = null;
    ensureChart();
  });
};

watch(() => [props.query, props.summary, props.platforms, props.timeline], scheduleRender, {
  deep: true,
  immediate: true,
});

onBeforeUnmount(() => {
  if (renderFrame) cancelAnimationFrame(renderFrame);
  resizeObserver?.disconnect();
  chart?.dispose();
  chart = null;
});
</script>

<style scoped>
.search-insight {
  margin: 18px 0 0;
  border: 1px solid rgba(191, 219, 254, 0.72);
  border-radius: 28px;
  background:
    radial-gradient(circle at 12% 18%, rgba(37, 99, 235, 0.1), transparent 24%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(239, 246, 255, 0.88));
  box-shadow: 0 14px 36px rgba(15, 23, 42, 0.05);
}

.search-insight-body {
  gap: 16px;
  padding: 22px 24px;
}

.insight-copy {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}

.insight-copy strong {
  color: #0f172a;
  font-size: 24px;
  line-height: 1.15;
  letter-spacing: -0.04em;
}

.insight-copy p {
  flex-basis: 100%;
  color: #64748b;
  font-size: 14px;
  line-height: 1.7;
}

.platform-strip {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.platform-pill {
  min-height: 38px;
  padding-inline: 14px;
  color: #475569;
  border-color: rgba(203, 213, 225, 0.92);
  background: rgba(255, 255, 255, 0.88);
}

.chart-shell {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 18px;
  border-radius: 22px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.88));
  padding: 18px;
}

.chart-copy {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 14px;
}

.mini-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.mini-stat {
  border-radius: 18px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.88);
}

.mini-stat .card-body {
  gap: 6px;
  padding: 14px;
}

.mini-stat span {
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.mini-stat strong {
  color: #0f172a;
  font-size: 24px;
  font-weight: 900;
  letter-spacing: -0.04em;
}

.chart-copy-note {
  color: #64748b;
  font-size: 13px;
  line-height: 1.7;
}

.insight-chart {
  width: 100%;
  min-width: 0;
  height: 336px;
}

@media (max-width: 1100px) {
  .chart-shell {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .search-insight-body {
    padding: 18px;
  }

  .insight-copy strong {
    font-size: 20px;
  }

  .mini-stats {
    grid-template-columns: 1fr 1fr;
  }

  .insight-chart {
    height: 280px;
  }
}
</style>

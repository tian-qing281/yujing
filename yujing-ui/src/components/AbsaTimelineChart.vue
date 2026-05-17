<template>
  <section class="absa-timeline-section card bg-base-100">
    <div class="absa-timeline-head">
      <div class="absa-timeline-title">
        <iconify-icon icon="mdi:chart-multiline" />
        <span>维度时间漂移</span>
        <span class="absa-timeline-badge">ABSA</span>
      </div>
      <div v-if="payload && payload.absa_covered_articles > 0" class="absa-timeline-meta">
        <span>{{ payload.absa_covered_articles }}/{{ payload.total_articles }} 篇命中</span>
        <span class="absa-timeline-sep">·</span>
        <span>覆盖率 {{ (payload.coverage_ratio * 100).toFixed(0) }}%</span>
        <span class="absa-timeline-sep">·</span>
        <span>{{ payload.bucket_hours }}h 桶</span>
      </div>
    </div>

    <div v-if="loading" class="absa-timeline-state">
      <span class="loading loading-spinner loading-sm"></span>
      <span>加载 ABSA 时间序列…</span>
    </div>

    <div v-else-if="error" class="absa-timeline-state absa-timeline-state--error">
      <iconify-icon icon="mdi:alert-circle-outline" />
      <span>{{ error }}</span>
    </div>

    <div v-else-if="!payload || payload.absa_covered_articles === 0" class="absa-timeline-empty">
      <iconify-icon icon="mdi:gauge-empty" />
      <p class="absa-timeline-empty-title">暂无方面级时间漂移数据</p>
      <p class="absa-timeline-empty-hint">
        {{ payload?.hint || '该事件下文章尚未触发 ABSA 抽取。' }}
        点击下方任一文章卡片 → AI 分析，即可在数秒内生成该篇的方面级情感缓存；事件下命中文章 ≥ 3 篇即可出现趋势曲线。
      </p>
    </div>

    <div v-else-if="payload.buckets.length < 2" class="absa-timeline-empty">
      <iconify-icon icon="mdi:timeline-alert-outline" />
      <p class="absa-timeline-empty-title">命中文章时间跨度不足</p>
      <p class="absa-timeline-empty-hint">
        已命中 {{ payload.absa_covered_articles }} 篇 ABSA 缓存，但全部落在同一时间桶内（{{ payload.bucket_hours }}h），无法绘制漂移曲线。
      </p>
    </div>

    <div v-else>
      <div ref="chartRef" class="absa-timeline-viewport"></div>
      <div class="absa-timeline-legend-hint">
        <iconify-icon icon="mdi:information-outline" />
        <span>纵轴：方面情感极性均值（+1 正面 / 0 中性 / -1 负面）；曲线越往上越正面，越往下越负面；点大小≈该桶证据数</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { buildApiUrl } from "../config/api";
import { ANIM } from "../utils/chartAnimation";

const props = defineProps({
  eventId: { type: [Number, String], default: null },
  bucketHours: { type: Number, default: 12 },
  topKAspects: { type: Number, default: 5 },
});

const chartRef = ref(null);
const payload = ref(null);
const loading = ref(false);
const error = ref("");
let chart = null;

// 6 色循环（与项目主色调和）
const ASPECT_COLORS = ["#3b82f6", "#10b981", "#f97316", "#a855f7", "#ec4899", "#14b8a6"];

const polarityColor = (v) => {
  if (v == null) return "#94a3b8";
  if (v >= 0.34) return "#10b981";
  if (v <= -0.34) return "#ef4444";
  return "#94a3b8";
};

const fetchData = async () => {
  if (!props.eventId) return;
  loading.value = true;
  error.value = "";
  payload.value = null;
  try {
    const url = buildApiUrl(
      `/api/events/${props.eventId}/absa_timeline?bucket_hours=${props.bucketHours}&top_k_aspects=${props.topKAspects}`
    );
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    payload.value = data;
    loading.value = false;          // 先关掉 loading，让 v-else 块渲染出 chartRef
    await nextTick();
    renderChart();
  } catch (e) {
    error.value = `加载失败：${e.message || e}`;
    loading.value = false;
  }
};

const renderChart = () => {
  if (!chartRef.value || !payload.value) return;
  const aspects = payload.value.aspects || [];
  const buckets = payload.value.buckets || [];
  if (aspects.length === 0 || buckets.length < 2) return;
  if (!window.echarts) return;

  if (!chart) {
    chart = window.echarts.init(chartRef.value);
  }

  const series = aspects.map((asp, i) => ({
    name: asp.name,
    type: "line",
    smooth: 0.3,
    showSymbol: true,
    symbolSize: (val, params) => {
      const cnt = (asp.counts || [])[params.dataIndex] || 0;
      // 6-18px 之间根据 count 缩放
      return Math.min(18, 6 + Math.sqrt(cnt) * 3);
    },
    connectNulls: false,
    data: asp.series.map((v, idx) => ({
      value: v,
      itemStyle: { color: polarityColor(v) },
      // 用 tooltip extra 携带 count
      _count: (asp.counts || [])[idx] || 0,
    })),
    lineStyle: { width: 2.2, color: ASPECT_COLORS[i % ASPECT_COLORS.length] },
    itemStyle: { color: ASPECT_COLORS[i % ASPECT_COLORS.length], borderWidth: 0 },
    emphasis: { focus: "series", lineStyle: { width: 3.4 } },
  }));

  const option = {
    grid: { left: 56, right: 24, top: 50, bottom: 40, containLabel: false },
    legend: {
      top: 4,
      left: "center",
      icon: "roundRect",
      itemWidth: 12,
      itemHeight: 6,
      textStyle: { color: "#475569", fontSize: 12 },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(15,23,42,0.92)",
      borderWidth: 0,
      textStyle: { color: "#f1f5f9", fontSize: 12 },
      formatter: (params) => {
        if (!params || !params.length) return "";
        const head = `<div style="margin-bottom:6px;font-weight:600;">${params[0].axisValue}</div>`;
        const lines = params
          .filter((p) => p.value != null)
          .map((p) => {
            const cnt = p.data?._count ?? 0;
            const v = typeof p.value === "number" ? p.value.toFixed(2) : p.value;
            const dotColor = polarityColor(p.value);
            return `<div style="display:flex;align-items:center;gap:8px;line-height:1.6;">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};"></span>
              <span style="flex:1;">${p.seriesName}</span>
              <span style="color:${dotColor};font-weight:600;">${v}</span>
              <span style="color:#94a3b8;font-size:11px;">·${cnt}条</span>
            </div>`;
          })
          .join("");
        return head + (lines || '<span style="color:#94a3b8;">该时段无数据</span>');
      },
    },
    xAxis: {
      type: "category",
      data: buckets,
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: { color: "#64748b", fontSize: 11 },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      min: -1,
      max: 1,
      interval: 0.5,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "#f1f5f9" } },
      axisLabel: {
        color: "#64748b",
        fontSize: 11,
        formatter: (v) => {
          if (v === 1) return "+1 正面";
          if (v === 0) return "0 中性";
          if (v === -1) return "-1 负面";
          return v;
        },
      },
    },
    series,
    animationDuration: ANIM?.duration ?? 600,
    animationEasing: ANIM?.easing ?? "cubicOut",
  };

  chart.setOption(option, true);
  chart.resize();
};

const handleResize = () => {
  if (chart) chart.resize();
};

watch(
  () => [props.eventId, props.bucketHours, props.topKAspects],
  () => fetchData(),
  { immediate: false }
);

onMounted(() => {
  fetchData();
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  if (chart) {
    chart.dispose();
    chart = null;
  }
});
</script>

<style scoped>
.absa-timeline-section {
  padding: 18px 20px 16px;
  border-radius: 14px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04), 0 4px 12px rgba(15, 23, 42, 0.04);
}

.absa-timeline-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  gap: 12px;
  flex-wrap: wrap;
}

.absa-timeline-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 14px;
  color: #1e293b;
}
.absa-timeline-title iconify-icon {
  color: #3b82f6;
  font-size: 18px;
}

.absa-timeline-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 6px;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
  letter-spacing: 0.04em;
  font-weight: 600;
}

.absa-timeline-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 12px;
}
.absa-timeline-sep {
  color: #cbd5e1;
}

.absa-timeline-viewport {
  width: 100%;
  height: 320px;
}

.absa-timeline-legend-hint {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.5;
}
.absa-timeline-legend-hint iconify-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.absa-timeline-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px 0;
  color: #64748b;
  font-size: 13px;
}
.absa-timeline-state--error {
  color: #ef4444;
}
.absa-timeline-state iconify-icon {
  font-size: 18px;
}

.absa-timeline-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 28px 24px;
  text-align: center;
  color: #94a3b8;
}
.absa-timeline-empty iconify-icon {
  font-size: 32px;
  color: #cbd5e1;
}
.absa-timeline-empty-title {
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  margin: 0;
}
.absa-timeline-empty-hint {
  font-size: 12px;
  line-height: 1.6;
  color: #94a3b8;
  margin: 0;
  max-width: 480px;
}
</style>

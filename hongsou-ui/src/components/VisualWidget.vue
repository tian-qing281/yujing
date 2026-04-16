<template>
  <article class="visual-widget-container" @click="$emit('select', item)">
    <div class="widget-header">
      <div class="source-tag">{{ sourceName }}</div>
      <a :href="item.url" target="_blank" class="source-link" @click.stop>
        访问原文
      </a>
    </div>

    <div v-if="showWordcloud" ref="canvasBox" class="widget-canvas-box">
      <canvas ref="wordcloudCanvas" class="widget-canvas"></canvas>
    </div>
    <div v-else class="widget-preview-box">
      <p class="summary-text">{{ previewText }}</p>
    </div>

    <div class="widget-footer">
      <div class="rank-badge">RANK #{{ item.rank || "??" }}</div>
      <div class="title-preview">{{ item.title }}</div>
    </div>
  </article>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

const props = defineProps({
  item: { type: Object, required: true },
  sourceName: { type: String, default: "数据源" },
});

defineEmits(["select"]);

const wordcloudCanvas = ref(null);
const canvasBox = ref(null);
let resizeObserver = null;

const getHashColor = (str) => {
  let hash = 0;
  for (let i = 0; i < str.length; i += 1) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = ["#3b82f6", "#60a5fa", "#93c5fd", "#f8fafc", "#94a3b8", "#cbd5e1", "#2563eb", "#1d4ed8"];
  return colors[Math.abs(hash) % colors.length];
};

const previewText = computed(() => {
  if (props.item.ai_summary) return props.item.ai_summary;

  try {
    const extra = JSON.parse(props.item.extra_info || "{}");
    return (
      extra.desc ||
      extra.excerpt ||
      extra.hot_metric ||
      extra.hot_score ||
      extra.author ||
      "该卡片当前只有基础热榜数据，进入详情后会继续拉取正文并生成完整研判。"
    );
  } catch (error) {
    return "该卡片当前只有基础热榜数据，进入详情后会继续拉取正文并生成完整研判。";
  }
});

const showWordcloud = computed(
  () => !props.item.ai_summary && props.item.wordcloud && props.item.wordcloud.length
);

const renderCloud = () => {
  if (!wordcloudCanvas.value || !showWordcloud.value || !props.item.wordcloud?.length) return;

  const canvas = wordcloudCanvas.value;
  const box = canvasBox.value;
  canvas.width = box.clientWidth;
  canvas.height = 180;

  try {
    if (window.WordCloud) {
      window.WordCloud(canvas, {
        list: props.item.wordcloud,
        fontFamily: "'Inter', sans-serif",
        fontWeight: 800,
        color: (word) => getHashColor(word),
        rotateRatio: 0,
        backgroundColor: "transparent",
        gridSize: 8,
        weightFactor: (size) => size * (canvas.width / 400),
        shuffle: false,
      });
    }
  } catch (error) {
    console.error("[WIDGET_VIS_ERROR]", error);
  }
};

onMounted(() => {
  nextTick(() => renderCloud());

  resizeObserver = new ResizeObserver(() => renderCloud());
  if (canvasBox.value) resizeObserver.observe(canvasBox.value);
});

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect();
});

watch(
  () => [props.item.id, props.item.wordcloud?.length || 0, props.item.ai_summary],
  async () => {
    await nextTick();
    renderCloud();
  },
  { deep: false }
);
</script>

<style scoped>
.visual-widget-container {
  display: block; text-decoration: none; margin: 0;
  background: #fff; border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px; overflow: hidden;
  cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
}
.visual-widget-container:hover {
  transform: translateY(-2px); border-color: #3b82f6;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.1);
}
.widget-header {
  padding: 10px 14px; background: #fafafa;
  display: flex; justify-content: space-between; align-items: center;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}
.source-tag { font-size: 10px; font-weight: 900; color: #64748b; letter-spacing: 0.5px; text-transform: uppercase; }
.source-link { font-size: 10px; color: #3b82f6; text-decoration: none; font-weight: 700; }

.widget-canvas-box { width: 100%; height: 160px; background: #fff; position: relative; }
.widget-canvas { width: 100%; height: 100%; }
.widget-preview-box { padding: 14px; min-height: 160px; background: #fff; }
.summary-text { font-size: 13px; color: #475569; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 6; -webkit-box-orient: vertical; overflow: hidden; }

.widget-footer {
  padding: 12px 14px; background: #fff;
  display: flex; align-items: center; gap: 10px;
  border-top: 1px solid rgba(0,0,0,0.03);
}
.rank-badge {
  background: #3b82f6; color: #fff; border-radius: 4px;
  padding: 2px 6px; font-size: 9px; font-weight: 900; line-height: 1;
}
.title-preview { font-size: 13px; font-weight: 700; color: #1e293b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>

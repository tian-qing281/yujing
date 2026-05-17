<template>
  <article
    class="event-card glass-panel"
    :class="{ 'event-card--lead': variant === 'lead' }"
    @click="$emit('click')"
  >
    <div class="card-body event-card-body">
      <div class="event-main">
        <span v-if="variant === 'lead'" class="event-kicker">TOP EVENT · 跨平台焦点</span>
        <h3 class="event-title" v-html="highlight(item.title)"></h3>
        <p
          class="event-preview"
          v-html="highlight(truncate(prettifySummary(item.summary) || '该事件已被热搜引擎捕获并完成多维聚合。'))"
        ></p>
      </div>

      <div class="event-footer">
        <div class="event-count-group">
          <iconify-icon icon="mdi:fire" class="event-fire-icon" />
          <span><NumberFlow :value="Number(item.article_count) || 0" /> 个热搜</span>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from "vue";
import NumberFlow from "@number-flow/vue";

const props = defineProps({
  item: { type: Object, required: true },
  query: { type: String, default: "" },
  // UI-8: 'lead' 变体为首屏顶条（8 仪式感），加 6px accent 顶条 + TOP EVENT kicker
  variant: { type: String, default: "default" },
});

defineEmits(["click"]);

const SOURCE_LABEL_MAP = {
  weibo_hot_search: "微博热搜榜",
  baidu_hot: "百度热搜榜",
  toutiao_hot: "头条实时榜",
  bilibili_hot_video: "哔哩哔哩榜",
  zhihu_hot_question: "知乎全站榜",
  thepaper_hot: "澎湃热榜",
  wallstreetcn_news: "华尔街见闻热榜",
  cls_telegraph: "财联社热榜",
};

const keywordPreview = computed(() => {
  const raw = Array.isArray(props.item.keywords) ? props.item.keywords : [];
  return raw
    .filter((keyword) => keyword && keyword.length > 1 && !/^(https?|com|www|net|org|cn)$/i.test(keyword))
    .slice(0, 3);
});

const truncate = (value) => {
  if (!value) return "";
  return value.length > 55 ? `${value.slice(0, 52)}...` : value;
};

const escapeHtml = (value) =>
  String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");

const escapeRegex = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const highlight = (value) => {
  const text = escapeHtml(value || "");
  const query = (props.query || "").trim();
  if (!query) return text;

  const tokens = Array.from(
    new Set(
      [query, ...query.split(/\s+/)]
        .map((item) => item.trim())
        .filter((item) => item.length >= 1)
        .sort((a, b) => b.length - a.length)
    )
  );

  if (!tokens.length) return text;
  const pattern = new RegExp(`(${tokens.map(escapeRegex).join("|")})`, "gi");
  return text.replace(pattern, '<mark class="event-hit">$1</mark>');
};

const prettifySummary = (value) => {
  let text = String(value || "");
  for (const [sourceId, label] of Object.entries(SOURCE_LABEL_MAP)) {
    text = text.replaceAll(sourceId, label);
  }
  return text;
};
</script>

<style scoped>
.event-card {
  background: var(--color-surface);
  border-radius: 6px;
  border: 1px solid var(--color-border);
  box-shadow: none;
  display: flex;
  flex-direction: column;
  cursor: pointer;
  /* Batch H：仅 transform + border-color 平滑过渡，不再 all */
  transition: transform 200ms ease-out, border-color 200ms ease-out, box-shadow 200ms ease-out;
  min-height: 180px;
  overflow: hidden;
  position: relative;
}

.event-card:hover {
  /* Batch H：克制位移 1px + 暖灰 border 加深，不再 scale */
  transform: translateY(-1px);
  border-color: var(--color-text-3);
  box-shadow: 0 4px 12px -4px rgba(28, 25, 23, 0.08);
}

.event-card-body {
  padding: 22px 24px;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.event-main {
  flex: 1;
  margin-bottom: 16px;
}

.event-title {
  font-size: clamp(16px, 1.1vw, 19px);
  font-weight: 700;
  font-family: var(--font-display, "Noto Serif SC", serif);
  color: var(--color-text);
  line-height: 1.4;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.event-preview {
  font-size: 13px;
  color: var(--color-text-2);
  line-height: 1.6;
  font-weight: 400;
}

.event-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.event-keywords {
  display: flex;
  gap: 8px;
}

.event-tag {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-3);
}

.event-count-group {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-accent); /* 赤陶红替代糖果橙 */
  letter-spacing: 0.02em;
}

.event-fire-icon {
  font-size: 14px;
}

:deep(.event-hit) {
  background: rgba(180, 83, 9, 0.12);
  color: var(--color-accent);
  padding: 0 4px;
  border-radius: 2px;
  font-weight: 600;
}

/* UI-8 顶条仪式感：6px accent 顶条 + TOP EVENT 衰线 kicker + 更大标题，与 NewsCard lead 同源 */
.event-card--lead {
  border-top: 6px solid var(--color-accent);
  border-radius: 0;
  min-height: 220px;
}

.event-card--lead .event-card-body {
  padding: 26px 28px;
}

.event-kicker {
  display: inline-block;
  font-family: var(--font-display, "Noto Serif SC", serif);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--color-accent);
  margin-bottom: 10px;
}

.event-card--lead .event-title {
  font-size: clamp(22px, 1.8vw, 28px);
  line-height: 1.25;
  letter-spacing: -0.01em;
  -webkit-line-clamp: 3;
}

.event-card--lead .event-preview {
  font-size: 14px;
  line-height: 1.7;
}
</style>

<template>
  <article class="event-card glass-panel" @click="$emit('click')">
    <div class="card-body event-card-body">
      <div class="event-main">
        <h3 class="event-title" v-html="highlight(item.title)"></h3>
        <p
          class="event-preview"
          v-html="highlight(truncate(prettifySummary(item.summary) || '该事件已被热搜引擎捕获并完成多维聚合。'))"
        ></p>
      </div>

      <div class="event-footer">
        <div class="event-count-group">
          <iconify-icon icon="mdi:fire" class="event-fire-icon" />
          <span>{{ item.article_count }} 个热搜</span>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  item: { type: Object, required: true },
  query: { type: String, default: "" },
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
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(12px);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.5);
  box-shadow:
    0 10px 15px -3px rgba(0, 0, 0, 0.05),
    0 4px 6px -2px rgba(0, 0, 0, 0.02),
    inset 0 0 0 1px rgba(255, 255, 255, 0.4);
  display: flex;
  flex-direction: column;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  min-height: 180px;
  overflow: hidden;
  position: relative;
}

.event-card:hover {
  transform: translateY(-4px) scale(1.01);
  background: rgba(255, 255, 255, 0.9);
  border-color: rgba(59, 130, 246, 0.3);
  box-shadow:
    0 20px 25px -5px rgba(15, 23, 42, 0.08),
    0 10px 10px -5px rgba(15, 23, 42, 0.04);
}

.event-card-body {
  padding: 24px;
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
  font-weight: 900;
  color: #0f172a;
  line-height: 1.4;
  margin-bottom: 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.event-preview {
  font-size: 13px;
  color: #64748b;
  line-height: 1.6;
  font-weight: 500;
}

.event-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid rgba(226, 232, 240, 0.5);
}

.event-keywords {
  display: flex;
  gap: 8px;
}

.event-tag {
  font-size: 11px;
  font-weight: 800;
  color: #3b82f6;
  opacity: 0.8;
}

.event-count-group {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 800;
  color: #f97316; /* 切换为富有热度感的橙色 */
}

.event-fire-icon {
  font-size: 14px;
}

:deep(.event-hit) {
  background: linear-gradient(120deg, rgba(59, 130, 246, 0.15) 0%, rgba(59, 130, 246, 0.05) 100%);
  color: #2563eb;
  padding: 0 4px;
  border-radius: 4px;
  font-weight: 700;
}
</style>

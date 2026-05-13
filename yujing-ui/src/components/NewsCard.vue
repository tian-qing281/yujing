<template>
  <div class="news-card card bg-base-100" @click="$emit('click')">
    <div class="card-body news-card-body">
      <div class="card-kicker">
        <div class="card-rank-box" :style="rankStyle">
          {{ (index + 1).toString().padStart(2, "0") }}
        </div>
        <div class="card-badges">
          <span v-if="sourceLabel && !hideSource" class="badge badge-outline source">{{ sourceLabel }}</span>
          <span v-if="heatLabel" class="badge badge-outline heat" :style="heatStyle">
            <iconify-icon icon="mdi:fire"></iconify-icon>
            {{ heatLabel }}
          </span>
          <span v-if="item.content && !item.content.startsWith('❌') && item.content.length >= 50" class="badge badge-outline cached">已采集</span>
        </div>
      </div>

      <div class="card-main">
        <h3 class="card-title" v-html="displayTitle"></h3>
        <p v-if="displayExcerpt" class="card-excerpt" v-html="displayExcerpt"></p>
        <div v-if="searchReasons.length" class="card-search-meta">
          <span v-for="reason in searchReasons" :key="reason" class="search-chip badge badge-soft badge-primary">{{ reason }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

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

const props = defineProps({
  item: Object,
  index: Number,
  hideSource: { type: Boolean, default: false },
});

defineEmits(["click"]);

const prettifySourceIds = (value) => {
  if (!value || typeof value !== "string") return value || "";
  let normalized = value;
  Object.entries(SOURCE_LABEL_MAP).forEach(([sourceId, label]) => {
    normalized = normalized.replaceAll(sourceId, label);
  });
  return normalized;
};

const rankStyle = computed(() => ({
  color: ["#ef4444", "#f59e0b", "#10b981"][props.index] || "#94a3b8",
}));

const parseExtraInfo = (value) => {
  if (!value) return {};
  if (typeof value === "object") return value;
  if (typeof value !== "string") return {};
  try {
    return JSON.parse(value);
  } catch (error) {
    return {};
  }
};

const formatNumberHeat = (value) => {
  const number = Number(String(value).replace(/[^\d.]/g, ""));
  if (!Number.isFinite(number) || number <= 0) return "";
  if (number < 1000) return "";
  if (number >= 100000000) return `${(number / 100000000).toFixed(number >= 1000000000 ? 1 : 2).replace(/\.0+$/, "")}亿`;
  if (number >= 10000) return `${(number / 10000).toFixed(number >= 100000 ? 0 : 1).replace(/\.0$/, "")}万`;
  return `${Math.round(number)}`;
};

const isRankOnlyHeat = (value) => {
  const text = String(value || "").trim();
  if (!text) return true;
  return /(?:热榜|热搜|榜单|第)\s*\d+\s*(?:位|名)?/.test(text) && !/[万亿]|阅读|讨论|热度|指数/.test(text);
};

const heatLabel = computed(() => {
  // 优先显示 HDS 统一后的影响指数
  if (props.item?.impactScore) {
    return `${props.item.impactScore} 影响指数`;
  }

  const extra = parseExtraInfo(props.item?.extra_info);
  const sourceId = props.item?.source_id || "";
  const candidates = [
    { value: extra.hot_metric, label: "热度" },
    { value: extra.hot_value, label: "热度" },
    { value: extra.hot_score, label: "热度" },
    { value: extra.view_count, label: sourceId === "bilibili_hot_video" ? "播放" : "热度" },
    { value: extra.views, label: sourceId === "bilibili_hot_video" ? "播放" : "热度" },
    { value: extra.view, label: "播放" },
    { value: extra.play, label: "播放" },
    { value: extra.read_count, label: "热度" },
  ];
  const selected = candidates.find((item) => item.value && !isRankOnlyHeat(item.value));

  if (!selected) return "";
  const raw = selected.value;

  const rawText = String(raw).trim();
  if (/[万亿]|阅读|讨论|热度|指数/.test(rawText)) return rawText.slice(0, 14);

  const formatted = formatNumberHeat(rawText);
  if (!formatted) return "";
  return `${formatted} ${selected.label}`;
});

const heatStyle = computed(() => ({
  color: props.index < 3 ? "#ef4444" : "#64748b",
}));

const sourceLabel = computed(() => SOURCE_LABEL_MAP[props.item?.source_id] || props.item?.source_id || "");

const displayTitle = computed(() =>
  prettifySourceIds(props.item.search_highlight_title || props.item.title || ""),
);
const displayExcerpt = computed(() =>
  prettifySourceIds(props.item.search_highlight_excerpt || ""),
);
const searchReasons = computed(() =>
  Array.isArray(props.item.search_match_reasons) ? props.item.search_match_reasons.slice(0, 3) : [],
);
</script>

<style scoped>
.news-card {
  /* editorial: 去右上蓝光晕，纯纸白底 + 1px hairline + 软 shadow */
  background: var(--color-surface);
  border-radius: 4px;
  padding: 28px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  cursor: pointer;
  transition: 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  border: 1px solid var(--color-border);
  gap: 20px;
  position: relative;
  min-height: 140px;
  min-width: 0;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(28, 25, 23, 0.04);
  isolation: isolate;
  will-change: transform, box-shadow;
}

.news-card-body {
  gap: 24px;
  padding: 28px;
}

.news-card::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  border-radius: inherit;
  /* editorial: hover overlay 改为暑色阳光 */
  background: radial-gradient(circle at 96% 8%, rgba(180, 83, 9, 0.06), transparent 60%);
  opacity: 0;
  transition: opacity 0.22s ease;
}

.news-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(28, 25, 23, 0.08);
  border-color: var(--color-accent);
}

.news-card:hover::before {
  opacity: 1;
}

.card-kicker {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 48px;
}

.card-rank-box {
  font-size: 32px;
  font-weight: 900;
  font-family: "Fira Code", ui-monospace, monospace;
  min-width: 42px;
  letter-spacing: -0.06em;
  opacity: 0.88;
  line-height: 1;
}

.card-main {
  flex: 1;
  text-align: left;
  padding-right: 24px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}

.card-title {
  font-size: 20px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.45;
  letter-spacing: -0.01em;
  max-width: 96%;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.card-excerpt {
  color: #64748b;
  font-size: 14px;
  line-height: 1.75;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.card-search-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.search-chip {
  font-size: 11px;
  font-weight: 800;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  min-height: auto;
}

:deep(mark) {
  /* editorial: 黄底 → 赤陶红下划线，如报刊重点圈存 */
  background: linear-gradient(180deg, transparent 60%, rgba(180, 83, 9, 0.22) 60%);
  color: var(--color-text);
  border-radius: 0;
  padding: 0 2px;
  font-weight: 700;
}

.card-badges {
  display: flex;
  gap: 10px;
  font-size: 11px;
  font-weight: 800;
  color: #94a3b8;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.badge {
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(226, 232, 240, 0.72);
  min-height: auto;
  height: auto;
}

.badge.heat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #f8fafc;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge.source {
  background: var(--color-surface-2);
  color: var(--color-text-2);
  border: 1px solid var(--color-border);
}

.badge.cached {
  /* editorial: 已采集 = 已入库的中性状态提示，用暑色阳光不争主 */
  background: rgba(180, 83, 9, 0.08);
  color: var(--color-accent);
  border: 1px solid rgba(180, 83, 9, 0.20);
  font-weight: 800;
  letter-spacing: 0.04em;
}

@media (max-width: 960px) {
  .news-card {
    min-height: 120px;
    padding: 18px 18px 20px;
  }

  .card-kicker {
    flex-direction: column;
    align-items: flex-start;
  }

  .card-badges {
    justify-content: flex-start;
  }

  .card-title {
    font-size: 18px;
    max-width: 100%;
    -webkit-line-clamp: 3;
  }
}
</style>

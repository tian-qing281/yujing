<template>
  <div class="news-card card bg-base-100" @click="$emit('click')">
    <div class="card-body news-card-body">
      <div class="card-kicker">
        <div class="card-rank-box" :style="rankStyle">
          {{ (index + 1).toString().padStart(2, "0") }}
        </div>
        <div class="card-badges">
          <span v-if="sourceLabel" class="badge badge-outline source">{{ sourceLabel }}</span>
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
  background:
    linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(248,250,252,0.88) 100%),
    radial-gradient(circle at 96% 8%, rgba(59,130,246,0.12), transparent 15rem);
  border-radius: var(--hs-radius-xl, 24px);
  padding: 28px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  cursor: pointer;
  transition: 0.28s cubic-bezier(0.16, 1, 0.3, 1);
  border: 1px solid rgba(148, 163, 184, 0.2);
  gap: 20px;
  position: relative;
  min-height: 178px;
  min-width: 0;
  overflow: hidden;
  box-shadow: 0 18px 55px rgba(15, 23, 42, 0.07);
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
  background: linear-gradient(135deg, rgba(59,130,246,0.16), transparent 28%, rgba(6,182,212,0.12));
  opacity: 0;
  transition: opacity 0.28s ease;
}

.news-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.12);
  border-color: rgba(59, 130, 246, 0.32);
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
  background: linear-gradient(180deg, rgba(254, 240, 138, 0.18) 0%, rgba(253, 224, 71, 0.36) 100%);
  color: #92400e;
  border-radius: 6px;
  padding: 0 2px;
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
  background: rgba(239, 246, 255, 0.9);
  color: #2563eb;
}

.badge.cached {
  background: rgba(59, 130, 246, 0.12);
  color: #60a5fa;
  border: 1px solid rgba(59, 130, 246, 0.25);
  backdrop-filter: blur(4px);
  font-weight: 800;
  letter-spacing: 0.02em;
}

@media (max-width: 960px) {
  .news-card {
    min-height: 150px;
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

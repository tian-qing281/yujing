<template>
  <div class="news-card card bg-base-100" :class="`news-card--${props.variant}`" @click="$emit('click')">
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
  // editorial Batch F: 卡片密度变体
  // major → 大卡（前 5 名）、row → 紧凑行（第 6+ 名）
  variant: { type: String, default: "major" },
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

// editorial：榜单前3排序色 - 赤陶红主调，第1重(粗赤陶红)、第2中(深赤陶红)、第3轻(墨石板)，
// 第4起统一用浅暖灰（如报纸榜单逐渐"退入背景"）
const rankStyle = computed(() => ({
  color: ["#B45309", "#92400E", "#1C1917"][props.index] || "#A8A29E",
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

// editorial：前3名火焰用赤陶红（保留"热"语义但走 token），其余暖灰
const heatStyle = computed(() => ({
  color: props.index < 3 ? "var(--color-accent)" : "var(--color-text-3)",
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
  /* editorial Batch F.1: 6px 圆角更柔，padding 略缩 */
  background: var(--color-surface);
  border-radius: 6px;
  padding: 22px 24px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  cursor: pointer;
  transition: 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  border: 1px solid var(--color-border);
  gap: 14px;
  position: relative;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(28, 25, 23, 0.04);
  isolation: isolate;
  will-change: transform, box-shadow;
}

.news-card-body {
  gap: 14px;
  padding: 0;
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
  /* editorial Batch F.1: hover 仅微抬升 + 边色加深，不再切换为强赤陶红 */
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(28, 25, 23, 0.06);
  border-color: var(--color-text-3);
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
  gap: 0.4em;
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

/* === Batch F.1: lead variant - 通栏头条 === */
/* 第 1 名跨 2 列，更厚 padding + 更大字号 + 衬线标题 */
.news-card--lead {
  padding: 32px 36px;
  gap: 18px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  /* 顶部一条赤陶红规格条，强化"今日头条"仪式感 */
  border-top: 3px solid var(--color-accent);
}

.news-card--lead .card-rank-box {
  font-size: 44px;
  font-family: var(--font-display, "Noto Serif SC", serif);
}

.news-card--lead .card-title {
  font-size: 26px;
  font-weight: 800;
  line-height: 1.32;
  font-family: var(--font-display, "Noto Serif SC", serif);
  letter-spacing: -0.005em;
  -webkit-line-clamp: 2;
}

/* === Batch F: row variant - 紧凑列表行 === */
/* 第 6+ 名走"杂志条目"密度，单行排版，仅排名 + 标题 + 热度 */
.news-card--row {
  padding: 14px 22px;
  min-height: 0;
  gap: 0;
  border-radius: 0;
  border-left: none;
  border-right: none;
  border-top: none;
  /* 仅留底部 1px hairline，连成报纸条目列表 */
  border-bottom: 1px solid var(--color-border);
  background: transparent;
  box-shadow: none;
}

.news-card--row:hover {
  transform: none;
  box-shadow: none;
  background: var(--color-surface-2);
  border-color: var(--color-border);
  border-bottom-color: var(--color-accent);
}

.news-card--row:hover::before {
  opacity: 0;
}

.news-card--row .news-card-body {
  padding: 0;
  gap: 16px;
  display: flex;
  flex-direction: row;
  align-items: center;
}

.news-card--row .card-kicker {
  flex: 0 0 auto;
  min-height: 0;
  width: auto;
  gap: 12px;
}

.news-card--row .card-rank-box {
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.02em;
  font-family: var(--font-display, "Noto Serif SC", serif);
  min-width: 32px;
}

.news-card--row .card-badges {
  display: none;
}

.news-card--row .card-main {
  flex: 1;
  min-width: 0;
  padding-right: 0;
  flex-direction: row;
  align-items: center;
  gap: 12px;
}

.news-card--row .card-title {
  font-size: 15px;
  font-weight: 600;
  -webkit-line-clamp: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  flex: 1;
  min-width: 0;
  line-height: 1.4;
}

.news-card--row .card-excerpt,
.news-card--row .card-search-meta {
  display: none;
}

/* row 行末尾追加热度小字（如果之后想接热度，可在 NewsCard template 内挂 row-meta） */
</style>

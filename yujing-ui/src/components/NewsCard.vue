<template>
  <div
    class="news-card card bg-base-100"
    :class="`news-card--${props.variant}`"
    :style="majorTopBarStyle"
    @click="$emit('click')"
  >
    <div class="card-body news-card-body">
      <div class="card-kicker">
        <div class="card-rank-box" :style="rankStyle">
          {{ (index + 1).toString().padStart(2, "0") }}
        </div>
        <div class="card-badges">
          <span v-if="sourceLabel && !hideSource" class="badge badge-outline source">{{ sourceLabel }}</span>
          <span v-if="heatLabel" class="badge badge-outline heat" :style="heatStyle" :title="impactExplain">
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

      <!-- editorial Q: lead 卡右侧加前 5 名影响指数对比 mini bar -->
      <div v-if="variant === 'lead' && leadStats?.length" class="lead-sparkline" aria-hidden="true">
        <div class="lead-sparkline-title">前 5 影响指数</div>
        <div class="lead-sparkline-bars">
          <div
            v-for="(score, i) in leadStats"
            :key="i"
            class="lsb-col"
            :class="{ 'lsb-self': i === 0 }"
          >
            <div class="lsb-bar-track">
              <div
                class="lsb-bar-fill"
                :style="{ height: barPct(score) + '%', background: barColor(i) }"
              ></div>
            </div>
            <div class="lsb-score">{{ score }}</div>
            <div class="lsb-label">{{ String(i + 1).padStart(2, "0") }}</div>
          </div>
        </div>
      </div>

      <!-- Batch VIII：row 变体在右侧显示影响指数小数字，与序号/标题同 baseline -->
      <span v-if="variant === 'row' && item?.impactScore" class="row-impact" :title="impactExplain">{{ item.impactScore }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { explainImpact } from "../utils/dataAdapter";

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
  variant: { type: String, default: "major" },  // editorial Q: lead 卡右侧 mini bar 所需 — 传入前 5 名的 impactScore 数组
  leadStats: { type: Array, default: () => [] },});

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

// F7：影响指数可解释 tooltip — hover heat badge / row 数字时显示拆解
const impactExplain = computed(() => {
  if (!props.item?.impactScore) return "";
  return explainImpact(props.item, props.index);
});

const displayTitle = computed(() =>
  prettifySourceIds(props.item.search_highlight_title || props.item.title || ""),
);
const displayExcerpt = computed(() =>
  prettifySourceIds(props.item.search_highlight_excerpt || ""),
);
const searchReasons = computed(() =>
  Array.isArray(props.item.search_match_reasons) ? props.item.search_match_reasons.slice(0, 3) : [],
);

// editorial Q: lead sparkline 辅助 — 用相对差（min-max 归一化）放大 bar 高度对比
// 避免 93/91/90 这种小差距渲染出几乎等高的柱子
const leadMax = computed(() => {
  const arr = (props.leadStats || []).filter((v) => Number(v) > 0);
  return arr.length ? Math.max(...arr) : 1;
});
const leadMin = computed(() => {
  const arr = (props.leadStats || []).filter((v) => Number(v) > 0);
  return arr.length ? Math.min(...arr) : 0;
});
const barPct = (score) => {
  const v = Number(score) || 0;
  if (v <= 0) return 4;
  const range = leadMax.value - leadMin.value;
  if (range <= 0) return 100;
  // 18% 保底（最低柱仍可见）+ 82% 区间归一化
  const norm = (v - leadMin.value) / range;
  return Math.round(18 + norm * 82);
};
const BAR_COLORS = ["#B45309", "#C77B2A", "#D9A471", "#C9BFA8", "#A8A29E"];
const barColor = (i) => BAR_COLORS[i] || "#A8A29E";

// editorial Q+R: major 卡（#02-#05）顶部色阶条，与序号色阶呼应
// 5 档完整色阶：#02 深赤陶红 / #03 中暖橙 / #04 浅暖橙 / #05 暖灰
// 从 3px 加到 5px，避免浏览器 sub-pixel 还原后看不清
const majorTopBarStyle = computed(() => {
  if (props.variant !== "major") return {};
  const colors = {
    1: "#92400E", // #02
    2: "#C77B2A", // #03
    3: "#D9A471", // #04
    4: "#C9BFA8", // #05
  };
  const c = colors[props.index];
  return c ? { borderTop: `5px solid ${c}` } : {};
});
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
  /* Batch VII：与 EventCard / TopicCard 统一 200ms ease-out，起伏一致 */
  transition: transform 200ms ease-out, box-shadow 200ms ease-out, border-color 200ms ease-out;
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
  /* editorial R：major 卡也用衰线（与 lead 序号呼应）；mono 仅留给 row 小字号 */
  font-family: var(--font-display, "Noto Serif SC", "Source Han Serif SC", serif);
  min-width: 42px;
  letter-spacing: -0.04em;
  opacity: 0.92;
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
  /* UI-3：让标题换行更平衡（02-05 卡 2 行时不会出现"末行只剩 1-2 字"的孤行） */
  text-wrap: balance;
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

/* === Batch F.1 / V: lead variant - 通栏头条 === */
/* 第 1 名跨 2 列，更厚 padding + 更大字号 + 衬线标题。
   Batch V 微调：用户反馈 01 太大与 02-05 落差太突兀，
   padding/字号/序号都缩一档，整体更接近 NYT 头版的克制比例。 */
.news-card--lead {
  padding: 24px 28px 22px;
  gap: 14px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  /* 顶部赤陶红规格条：3px → 6px，强化今日头条仪式感 */
  border-top: 6px solid var(--color-accent);
}

/* lead 头条加一个小 kicker：TOP STORY · 今日头条，位于序号右侧 */
.news-card--lead .card-rank-box::after {
  content: "TOP STORY · 今日头条";
  display: inline-block;
  margin-left: 14px;
  vertical-align: middle;
  font-family: var(--font-display, "Noto Serif SC", serif);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.22em;
  color: var(--color-accent, #B45309);
  text-transform: uppercase;
  position: relative;
  top: -6px;
}

.news-card--lead .card-rank-box {
  font-size: 34px;
  font-family: var(--font-display, "Noto Serif SC", serif);
}

.news-card--lead .card-title {
  font-size: 22px;
  font-weight: 800;
  line-height: 1.32;
  font-family: var(--font-display, "Noto Serif SC", serif);
  letter-spacing: -0.005em;
  -webkit-line-clamp: 2;
}

/* lead 卡布局：grid 让 kicker 跨满，main 与右侧 sparkline 横向并排 */
.news-card--lead .news-card-body {
  display: grid;
  grid-template-columns: 1fr 220px;
  grid-template-rows: auto 1fr;
  gap: 14px 28px;
}
.news-card--lead .card-kicker { grid-column: 1 / -1; }
.news-card--lead .card-main { grid-column: 1; grid-row: 2; }
.news-card--lead .lead-sparkline { grid-column: 2; grid-row: 2; }

/* === editorial Q: lead mini bar 影响指数对比 === */
.lead-sparkline {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px 10px;
  background: var(--color-surface-2, #F5F5F2);
  border: 1px solid var(--color-border-soft, #EFEFEA);
  border-radius: 8px;
  min-width: 0;
}
.lead-sparkline-title {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--color-text-3, #A8A29E);
  font-family: var(--font-display, "Noto Serif SC", serif);
}
.lead-sparkline-bars {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 6px;
  height: 78px;
}
.lsb-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  height: 100%;
  min-width: 0;
}
.lsb-bar-track {
  width: 100%;
  flex: 1;
  background: rgba(180, 83, 9, 0.04);
  border-radius: 2px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  overflow: hidden;
}
.lsb-bar-fill {
  width: 100%;
  border-radius: 2px 2px 0 0;
  min-height: 3px;
  transition: height 320ms cubic-bezier(0.2, 0.8, 0.2, 1);
}
.lsb-score {
  font-size: 10px;
  font-weight: 700;
  color: var(--color-text-2, #57534E);
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.lsb-label {
  font-size: 9px;
  font-weight: 600;
  color: var(--color-text-3, #A8A29E);
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  letter-spacing: 0.04em;
  line-height: 1;
}
.lsb-self .lsb-score { color: var(--color-accent, #B45309); }
.lsb-self .lsb-label { color: var(--color-accent, #B45309); }

/* 窄屏：sparkline 隐藏，main 占满 */
@media (max-width: 768px) {
  .news-card--lead .news-card-body {
    grid-template-columns: 1fr;
  }
  .news-card--lead .lead-sparkline { display: none; }
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

/* Batch VIII：row 右侧影响指数小数字，与序号、标题同 baseline。
   使用 tabular-nums 保证三位数宽度一致，避免 91/9 宽度抽动。 */
.news-card--row .row-impact {
  flex: 0 0 auto;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-muted, #94a3b8);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  margin-left: 12px;
}

/* row 行末尾追加热度小字（如果之后想接热度，可在 NewsCard template 内挂 row-meta） */
</style>

<template>
  <Transition name="modal-fade">
    <div v-if="item" class="modal-mask" @click.self="$emit('close')">
      <section class="event-modal modal-box">
        <div class="event-modal-head">
          <div class="head-copy">
            <h2>{{ item.title }}</h2>
          </div>
          <div class="head-actions">
            <button class="btn-close btn btn-circle btn-ghost" type="button" @click="$emit('close')">
              <iconify-icon icon="mdi:close"></iconify-icon>
            </button>
          </div>
        </div>

        <div class="capsule-scroll-body">
          <section v-if="representativeArticle" class="summary-hero card bg-base-100">
            <div class="panel-head">
              <span>核心事件</span>
            </div>
            <div class="summary-hero-body">
              <button type="button" class="lead-article-card" @click="openRepresentativeArticle">
                <div class="lead-article-top">
                  <span>{{ getSourceName(representativeArticle.source_id) }}</span>
                  <span>{{ formatTime(representativeArticle.fetch_time) }}</span>
                </div>
                <strong>{{ representativeArticle.title }}</strong>
                <p>{{ representativeArticlePreview }}</p>
              </button>

              <div class="core-summary-card">
                <div class="core-summary-kicker">AI 总结</div>
                <div class="core-summary-body">
                  <span v-if="aiSummaryLoading" class="core-summary-loading">
                    <span class="loading loading-spinner loading-xs"></span>
                    AI 正在分析中…
                  </span>
                  <template v-else>{{ coreEventSummary }}</template>
                </div>
              </div>
            </div>
          </section>

          <section v-if="allArticles.length" class="chart-section">
            <div class="section-heading">
              <span>数据分析</span>
              <span>{{ allArticles.length }} 条情报</span>
            </div>
            <div class="event-intel-dash">
              <section class="intel-card card bg-base-100">
                <div class="intel-card-head">
                  <iconify-icon icon="mdi:chart-timeline-variant" />
                  <span>时间趋势</span>
                </div>
                <div ref="timeTrendChartRef" class="chart-viewport"></div>
              </section>

              <section class="intel-card card bg-base-100">
                <div class="intel-card-head">
                  <iconify-icon icon="mdi:view-grid-outline" />
                  <span>平台分布</span>
                </div>
                <div ref="platformBarRef" class="chart-viewport"></div>
              </section>

              <section class="intel-card card bg-base-100">
                <div class="intel-card-head">
                  <iconify-icon icon="mdi:fire" />
                  <span>关键词热度</span>
                </div>
                <div ref="keywordBarRef" class="chart-viewport"></div>
              </section>

              <section class="intel-card card bg-base-100">
                <div class="intel-card-head">
                  <iconify-icon icon="mdi:gauge" />
                  <span>舆情倾向</span>
                </div>
                <div ref="sentimentRingRef" class="chart-viewport"></div>
              </section>

              <section v-if="hasSentimentTrend" class="intel-card intel-card--wide card bg-base-100">
                <div class="intel-card-head">
                  <iconify-icon icon="mdi:chart-areaspline" />
                  <span>情感演变</span>
                  <span class="intel-badge">时间轴</span>
                </div>
                <div ref="sentimentTrendRef" class="chart-viewport"></div>
              </section>
            </div>
          </section>

          <section class="full-width-panel card bg-base-100">
            <div class="panel-head">
              <span>事件脉络</span>
              <span class="panel-head-right">
                <span class="timeline-count">{{ displayedArticles.length }} 条</span>
                <span class="eh-sort-toggle">
                  <button class="eh-sort-btn" :class="{ active: timelineMode === 'time' }" @click="timelineMode = 'time'">
                    <iconify-icon icon="mdi:clock-outline" />时间演化
                  </button>
                  <button class="eh-sort-btn" :class="{ active: timelineMode === 'heat' }" @click="timelineMode = 'heat'">
                    <iconify-icon icon="mdi:chart-bar" />相关性
                  </button>
                </span>
              </span>
            </div>
            <div
              v-if="displayedArticles.length >= 3"
              class="article-timeline-wrap"
            >
              <div class="article-timeline-caption">
                <iconify-icon icon="mdi:chart-timeline-variant" />
                <span>全部 {{ displayedArticles.length }} 篇情报的“时间 × 平台”分布</span>
              </div>
              <div ref="articleTimelineRef" class="article-timeline-viewport"></div>
            </div>
            <div class="timeline-list timeline-list--rail">
              <article
                v-for="(article, idx) in displayedArticles"
                :key="article.id"
                class="timeline-row tl-card"
                @click="$emit('open-article', article)"
              >
                <div class="tl-axis">
                  <div
                    v-if="formatDatePill(timelineTimeOf(article))"
                    class="tl-date-pill"
                  >
                    <span class="tl-date-year">{{ formatDatePill(timelineTimeOf(article)).year }}</span>
                    <span class="tl-date-md">{{ formatDatePill(timelineTimeOf(article)).monthDay }}</span>
                    <span class="tl-date-time">{{ formatDatePill(timelineTimeOf(article)).time }}</span>
                  </div>
                  <div
                    class="timeline-dot tl-dot-large"
                    :style="{ background: getSentimentColor(article.ai_sentiment), boxShadow: `0 0 0 5px ${getSentimentColor(article.ai_sentiment)}22, 0 0 0 9px ${getSentimentColor(article.ai_sentiment)}11` }"
                    :title="getSentimentLabel(article.ai_sentiment)"
                  ></div>
                </div>
                <div class="timeline-copy tl-card-body">
                  <div
                    v-if="timelineMode === 'time' && idx > 0 && formatTimeGap(timelineTimeOf(displayedArticles[0]), timelineTimeOf(article))"
                    class="timeline-gap"
                  >
                    <iconify-icon icon="mdi:clock-outline" />
                    <span>起点 {{ formatTimeGap(timelineTimeOf(displayedArticles[0]), timelineTimeOf(article)) }}</span>
                  </div>
                  <div class="timeline-meta">
                    <span class="timeline-platform">
                      <iconify-icon :icon="getSourceIcon(article.source_id)" />
                      {{ getSourceName(article.source_id) }}
                    </span>
                    <span
                      v-if="getSentimentLabel(article.ai_sentiment)"
                      class="timeline-sentiment-chip"
                      :style="{ color: getSentimentColor(article.ai_sentiment), borderColor: `${getSentimentColor(article.ai_sentiment)}55` }"
                    >
                      {{ getSentimentLabel(article.ai_sentiment) }}
                    </span>
                  </div>
                  <h4>{{ article.title }}</h4>
                  <p>{{ getArticlePreview(article) }}</p>
                </div>
              </article>
            </div>
          </section>
        </div>
      </section>
    </div>
  </Transition>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { buildApiUrl } from "../config/api";

const props = defineProps({
  item: { type: Object, default: null },
  sourceRegistry: { type: Array, default: () => [] },
});

const emit = defineEmits(["close", "open-article"]);

const timeTrendChartRef = ref(null);
const platformBarRef = ref(null);
const keywordBarRef = ref(null);
const sentimentRingRef = ref(null);
const sentimentTrendRef = ref(null);
const articleTimelineRef = ref(null);
const aiSummaryLoading = ref(false);
const aiSummaryText = ref("");
const timelineMode = ref("time"); // 'time' | 'heat'
let aiSummaryAbort = null;

let timeTrendChart = null;
let platformChart = null;
let keywordChart = null;
let sentimentChart = null;
let sentimentTrendChart = null;
let articleTimelineChart = null;

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

const KEYWORD_STOPWORDS = new Set([
  "核心事件", "深度研判", "AI总结", "ai总结", "代表情报",
  "微博热搜榜", "百度热搜榜", "头条实时榜", "哔哩哔哩榜",
  "知乎全站榜", "澎湃热榜", "华尔街见闻热榜", "财联社热榜",
  "平台", "热点", "事件", "总结", "官方", "回应", "部分",
  "进行中", "热搜", "全站榜", "早报", "直播", "改名", "假警",
  "radio", "fm", "如何", "什么", "怎么", "为什么", "哪些",
  "可以", "已经", "这个", "那个", "一个", "目前", "表示",
  "相关", "最新", "消息", "新闻", "报道", "今天", "昨天",
  "据悉", "以及", "还是", "就是", "一直", "之后", "之前",
  "现在", "情况", "发现", "开始", "可能", "实际", "方面",
  "认为", "问题", "声明", "通报", "显示", "最近", "关于",
  "评论", "网友", "围观", "来源", "此前", "正在", "其中",
  "总台记者", "记者", "编辑", "责编", "作者", "全文", "详情",
  "原标题", "转载", "图片", "视频", "专题", "综合",
  "随时准备", "准备开火", "不排除", "有可能",
  "即刻起", "笑飞了", "小时", "乌方",
]);


const allArticles = computed(() =>
  [...(props.item?.related_articles || [])].sort(
    (a, b) => new Date(b.fetch_time || b.pub_date || 0) - new Date(a.fetch_time || a.pub_date || 0)
  )
);

const representativeArticle = computed(() => {
  const representativeId = props.item?.representative_article_id;
  if (representativeId) {
    const matched = allArticles.value.find((article) => article.id === representativeId);
    if (matched) return matched;
  }
  return allArticles.value[0] || null;
});

const representativeArticlePreview = computed(() => getArticlePreview(representativeArticle.value));

const coreEventSummary = computed(() => {
  if (aiSummaryText.value) {
    const cleaned = aiSummaryText.value
      .replace(/\r/g, "")
      .split("\n")
      .map((line) => line.replace(/^#+\s*/, "").replace(/^\d+\.\s*/, "").trim())
      .filter(Boolean)
      .join(" ");
    const sentences = cleaned.split(/(?<=[。！？])/).filter(Boolean);
    return sentences.slice(0, 2).join("").trim() || cleaned;
  }
  const aiSummary = String(representativeArticle.value?.ai_summary || "").trim();
  if (aiSummary) {
    const cleaned = aiSummary
      .replace(/\r/g, "")
      .split("\n")
      .map((line) => line.replace(/^#+\s*/, "").replace(/^\d+\.\s*/, "").trim())
      .filter(Boolean)
      .join(" ");
    const sentences2 = cleaned.split(/(?<=[。！？])/).filter(Boolean);
    return sentences2.slice(0, 2).join("").trim() || cleaned;
  }
  if (aiSummaryLoading.value) return "";
  const preview = representativeArticlePreview.value;
  if (preview) return preview;
  return "暂无AI总结";
});

const abortAiSummary = () => {
  if (aiSummaryAbort) {
    // 回写已收到的部分文本，避免弹窗关闭后丢失
    if (aiSummaryText.value) {
      const article = representativeArticle.value;
      if (article && !article.ai_summary) {
        article.ai_summary = aiSummaryText.value;
      }
    }
    aiSummaryAbort.abort();
    aiSummaryAbort = null;
  }
};

const fetchAiSummary = async () => {
  abortAiSummary();
  const article = representativeArticle.value;
  if (!article?.id) return;
  if (article.ai_summary) {
    aiSummaryText.value = article.ai_summary;
    return;
  }
  aiSummaryLoading.value = true;
  const controller = new AbortController();
  aiSummaryAbort = controller;
  try {
    const res = await fetch(buildApiUrl(`/api/articles/${article.id}/analyze`), { signal: controller.signal });
    if (!res.ok || !res.body) return;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (controller.signal.aborted) break;
      buf += decoder.decode(value, { stream: true });
      const chunks = buf.split("\n\n");
      buf = chunks.pop() || "";
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        try {
          const payload = JSON.parse(line.slice(6));
          if (payload.type === "content") {
            aiSummaryText.value += payload.text || "";
          } else if (payload.type === "skip_video") {
            // 代表文章被识别为视频 → 后端已删除 event/article，关闭本 modal 让父级刷新
            aiSummaryText.value = "此事件为视频内容，已从榜单移除。";
            emit("close");
            return;
          }
        } catch { /* skip */ }
      }
    }
    // 回写到 article 对象，避免 AnalysisModal 重复请求
    if (aiSummaryText.value && article) {
      article.ai_summary = aiSummaryText.value;
    }
  } catch (err) {
    if (err?.name !== 'AbortError') console.warn('[EventModal] AI summary error:', err);
  } finally {
    aiSummaryLoading.value = false;
    aiSummaryAbort = null;
  }
};


const getSourceName = (id) => {
  const hit = props.sourceRegistry.find((item) => item.id === id);
  return hit ? hit.name : SOURCE_LABEL_MAP[id] || "未知来源";
};

const SOURCE_ICON_MAP = {
  weibo_hot_search: "ri:weibo-fill",
  baidu_hot: "ri:baidu-fill",
  toutiao_hot: "mdi:newspaper-variant",
  bilibili_hot_video: "ri:bilibili-fill",
  zhihu_hot_question: "ri:zhihu-fill",
  thepaper_hot: "mdi:newspaper",
  wallstreetcn_news: "mdi:finance",
  cls_telegraph: "mdi:chart-line",
};

const getSourceIcon = (id) => SOURCE_ICON_MAP[id] || "mdi:web";

const SENTIMENT_COLOR_MAP = {
  neutral: "#64748b",
  中性: "#64748b",
  concern: "#3b82f6",
  关注: "#3b82f6",
  joy: "#10b981",
  喜悦: "#10b981",
  anger: "#ef4444",
  愤怒: "#ef4444",
  sadness: "#8b5cf6",
  悲伤: "#8b5cf6",
  doubt: "#f59e0b",
  质疑: "#f59e0b",
  surprise: "#eab308",
  惊讶: "#eab308",
  disgust: "#991b1b",
  厌恶: "#991b1b",
};

const getSentimentColor = (sentiment) =>
  SENTIMENT_COLOR_MAP[String(sentiment || "").trim()] || "#94a3b8";

const SENTIMENT_LABEL_MAP = {
  neutral: "中性", concern: "关注", joy: "喜悦", anger: "愤怒",
  sadness: "悲伤", doubt: "质疑", surprise: "惊讶", disgust: "厌恶",
};

const getSentimentLabel = (sentiment) => {
  const raw = String(sentiment || "").trim();
  if (!raw) return "";
  return SENTIMENT_LABEL_MAP[raw] || raw;
};

// 事件脉络：按时间升序（旧→新），讲述事件演化过程
// 排序优先级：pub_date（真实发布时间） > fetch_time（平台抓取时间）
// 两者都缺失的条目固定排到末尾，避免 new Date(0) 把空值顶到开头造成乱序
const _timelineTs = (article) => {
  const raw = article?.pub_date || article?.fetch_time;
  if (!raw) return null;
  const t = new Date(raw).getTime();
  return Number.isFinite(t) ? t : null;
};

const timelineArticles = computed(() => {
  const arr = [...(props.item?.related_articles || [])];
  return arr.sort((a, b) => {
    const ta = _timelineTs(a);
    const tb = _timelineTs(b);
    if (ta === null && tb === null) return 0;
    if (ta === null) return 1;   // 无时间的排到后面
    if (tb === null) return -1;
    if (ta !== tb) return ta - tb;
    return (a.id || 0) - (b.id || 0);  // 稳定排序：时间相同按 id
  });
});

const heatArticles = computed(() => {
  const arr = [...(props.item?.related_articles || [])];
  return arr.sort((a, b) => (b.importance_score || 0) - (a.importance_score || 0));
});

const displayedArticles = computed(() =>
  timelineMode.value === "heat" ? heatArticles.value : timelineArticles.value
);

// 显示用：pub_date > fetch_time 的优先级保持和排序 key 一致，避免时间与顺序脱节
const timelineTimeOf = (article) => article?.pub_date || article?.fetch_time || "";

// 距事件第一条（起点）的时间差提示。> 1 天时同时展示小时，体现时间跨度
const formatTimeGap = (prevIso, curIso) => {
  if (!prevIso || !curIso) return "";
  const diff = new Date(curIso).getTime() - new Date(prevIso).getTime();
  if (!Number.isFinite(diff) || diff < 60 * 1000) return "";
  const totalMinutes = Math.floor(diff / 60000);
  if (totalMinutes < 60) return `${totalMinutes} 分钟后`;
  const totalHours = Math.floor(totalMinutes / 60);
  if (totalHours < 24) return `${totalHours} 小时后`;
  const days = Math.floor(totalHours / 24);
  const remainingHours = totalHours - days * 24;
  return remainingHours > 0 ? `${days} 天 ${remainingHours} 小时后` : `${days} 天后`;
};

const prettifySourceIds = (value) => {
  let text = String(value || "");
  for (const [sourceId, label] of Object.entries(SOURCE_LABEL_MAP)) {
    text = text.replaceAll(sourceId, label);
  }
  return text;
};

const formatTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hour = `${date.getHours()}`.padStart(2, "0");
  const minute = `${date.getMinutes()}`.padStart(2, "0");
  return `${month}-${day} ${hour}:${minute}`;
};

// 年表卡片左侧日期胶囊：YYYY · MM-DD
const formatDatePill = (value) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return {
    year: String(date.getFullYear()),
    monthDay: `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`,
    time: `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`,
  };
};

const safeParse = (value) => {
  try {
    return JSON.parse(value || "{}");
  } catch {
    return {};
  }
};

const getArticlePreview = (article) => {
  if (!article) return "";
  if (article.ai_summary) return prettifySourceIds(article.ai_summary);
  if (typeof article.extra_info === "string") {
    try {
      const extra = JSON.parse(article.extra_info);
      return prettifySourceIds(extra.excerpt || extra.desc || extra.author || "");
    } catch {
      return prettifySourceIds(article.extra_info.slice(0, 120));
    }
  }
  return "";
};

const openRepresentativeArticle = () => {
  if (!representativeArticle.value) return;
  emit("open-article", representativeArticle.value);
};

// 不同平台 extra_info.hot_value 量纲差异极大（微博百万级 / 财联社常缺失），
// 用"平均值"会让单条微博把其他平台全淹没。改为：平台权重 × log10(hot+1) 累加，
// 并对未填 hot 的平台按权重给一个保底代表分，保证条数多时热度也能随之上升。
const PLATFORM_HEAT_WEIGHT = {
  weibo_hot: 0.5,
  zhihu_hot: 0.3,
  baidu_hot: 0.3,
  toutiao_hot: 0.25,
  bilibili_hot_video: 0.2,
  thepaper_hot: 0.15,
  wallstreetcn_news: 0.1,
  cls_telegraph: 0.1,
};
const DEFAULT_HEAT_WEIGHT = 0.1;

const heatContribution = (article) => {
  const extra = typeof article.extra_info === "string" ? safeParse(article.extra_info) : (article.extra_info || {});
  const rawHot = Number(extra.hot_value || extra.hot_score || extra.view || 0);
  const weight = PLATFORM_HEAT_WEIGHT[article.source_id] ?? DEFAULT_HEAT_WEIGHT;
  // 有 hot 值 → log10 压缩（微博 7M → ~7，避免一条爼骤）
  // 没 hot 值 → 按权重给个代表分（财联社 ~10，微博 ~50），维持"多条=更高热度"的单调性
  const base = rawHot > 0 ? Math.log10(rawHot + 1) * 100 : 100;
  return base * weight;
};

const timeSeries = computed(() => {
  const buckets = new Map();
  for (const article of allArticles.value) {
    const date = new Date(article.fetch_time || article.pub_date || 0);
    if (Number.isNaN(date.getTime())) continue;
    date.setHours(date.getHours(), 0, 0, 0);
    const key = date.getTime();
    const current = buckets.get(key) || { count: 0, heat: 0 };
    current.count += 1;
    current.heat += heatContribution(article);
    buckets.set(key, current);
  }
  return [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .slice(-12)
    .map(([time, value]) => {
      const date = new Date(time);
      return {
        label: `${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:00`,
        count: value.count,
        heat: Number(value.heat.toFixed(1)),
      };
    });
});

const sourceBreakdown = computed(() => {
  const counter = new Map();
  for (const article of allArticles.value) {
    const label = getSourceName(article.source_id);
    counter.set(label, (counter.get(label) || 0) + 1);
  }
  return [...counter.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);
});

// 关键词热度只取后端已清洗过的 event.keywords（后端 _extract_display_keywords
// 里有完整的 blocklist + 停用词 + 片段过滤）。前端早先那段"按标点硬切 title +
// preview"的土法分词会漏掉大量没有标点的长片段（"第7个行政区""推动国家重建"
// "如今以"都是这样进来的），彻底弃用。
// 权重按后端给的排序衰减，保证图表高度分布自然。
const keywordBreakdown = computed(() => {
  const raw = props.item?.keywords || [];
  const seen = new Set();
  const cleaned = [];
  for (const kw of raw) {
    const text = String(kw || "").trim();
    if (!text) continue;
    if (seen.has(text)) continue;
    if (KEYWORD_STOPWORDS.has(text)) continue;
    seen.add(text);
    cleaned.push(text);
  }
  // 后端默认已按重要度排序；用 (N - i) 当"热度值"让条形图阶梯清晰
  const total = cleaned.length;
  return cleaned.slice(0, 6).map((label, i) => ({ label, value: total - i }));
});


const emotionBreakdown = computed(() => {
  const buckets = [
    { label: "中性", key: "neutral", value: 0 },
    { label: "关注", key: "concern", value: 0 },
    { label: "悲伤", key: "sadness", value: 0 },
    { label: "厌恶", key: "disgust", value: 0 },
    { label: "愤怒", key: "anger", value: 0 },
    { label: "质疑", key: "doubt", value: 0 },
    { label: "惊讶", key: "surprise", value: 0 },
    { label: "喜悦", key: "joy", value: 0 },
  ];

  const idx = Object.fromEntries(buckets.map((item, index) => [item.key, index]));
  for (const article of allArticles.value) {
    const key = String(article.ai_sentiment || "neutral").toLowerCase();
    if (idx[key] !== undefined) {
      buckets[idx[key]].value += 1;
    } else {
      buckets[idx.neutral].value += 1;
    }
  }
  return buckets.filter((item) => item.value > 0);
});
//  AI 辅助生成：DeepSeek-V3, 2026-04-02
const sentimentSummary = computed(() => {
  const totals = {
    positive: 0,
    neutral: 0,
    negative: 0,
    concern: 0,
  };
  for (const item of emotionBreakdown.value) {
    if (["喜悦"].includes(item.label)) totals.positive += item.value;
    else if (["愤怒", "厌恶", "悲伤"].includes(item.label)) totals.negative += item.value;
    else if (["关注", "质疑", "惊讶"].includes(item.label)) totals.concern += item.value;
    else totals.neutral += item.value;
  }
  return [
    { label: "正面", value: totals.positive, color: "#10b981" },
    { label: "中性", value: totals.neutral, color: "#64748b" },
    { label: "负面", value: totals.negative, color: "#ef4444" },
    { label: "关注", value: totals.concern, color: "#3b82f6" },
  ].filter((item) => item.value > 0);
});


const sentimentTrendData = computed(() => Array.isArray(props.item?.sentiment_trend) ? props.item.sentiment_trend : []);
const hasSentimentTrend = computed(() => sentimentTrendData.value.length >= 2);

const ensureChart = (instanceRef, existingChart) => {
  if (!window.echarts || !instanceRef.value) return existingChart;
  if (existingChart) existingChart.dispose();
  return window.echarts.init(instanceRef.value);
};

const renderCharts = () => {
  if (!window.echarts || !props.item || !allArticles.value.length) return;

  timeTrendChart = ensureChart(timeTrendChartRef, timeTrendChart);
  platformChart = ensureChart(platformBarRef, platformChart);
  keywordChart = ensureChart(keywordBarRef, keywordChart);
  sentimentChart = ensureChart(sentimentRingRef, sentimentChart);

  const timeline = timeSeries.value;
  const sources = sourceBreakdown.value;
  const keywords = keywordBreakdown.value;
  const sentiment = sentimentSummary.value;

  // 1. 时间趋势 — 柱状(数量) + 折线(热度) 双轴
  timeTrendChart?.setOption({
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e2e8f0",
      textStyle: { color: "#334155", fontSize: 12 },
    },
    legend: {
      data: ["情报数", "热度指数"],
      top: 4,
      left: "center",
      textStyle: { color: "#94a3b8", fontSize: 11, fontWeight: 700 },
      itemWidth: 14,
      itemHeight: 8,
      itemGap: 20,
    },
    grid: { top: 40, right: 68, bottom: 56, left: 44 },
    xAxis: {
      type: "category",
      data: timeline.map((d) => d.label),
      axisLabel: { color: "#94a3b8", fontSize: 10, rotate: 35, interval: 0 },
      axisLine: { lineStyle: { color: "#e2e8f0" } },
      axisTick: { show: false },
    },
    yAxis: [
      {
        type: "value",
        name: "条数",
        nameTextStyle: { color: "#94a3b8", fontSize: 10 },
        splitLine: { lineStyle: { color: "rgba(148,163,184,0.1)" } },
        axisLabel: { color: "#94a3b8", fontSize: 10 },
      },
      {
        type: "value",
        name: "热度分",
        nameTextStyle: { color: "#94a3b8", fontSize: 10 },
        splitLine: { show: false },
        axisLabel: {
          color: "#94a3b8", fontSize: 10,
          formatter: (v) => v >= 1000 ? (v / 1000).toFixed(1) + "k" : Math.round(v),
        },
      },
    ],
    series: [
      {
        name: "情报数",
        type: "bar",
        yAxisIndex: 0,
        data: timeline.map((d) => d.count),
        barWidth: timeline.length <= 3 ? 32 : "38%",
        itemStyle: {
          color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "#818cf8" },
            { offset: 1, color: "#6366f1" },
          ]),
          borderRadius: [6, 6, 0, 0],
        },
      },
      {
        name: "热度指数",
        type: "line",
        yAxisIndex: 1,
        data: timeline.map((d) => d.heat),
        smooth: true,
        symbol: "circle",
        symbolSize: 7,
        lineStyle: { color: "#f97316", width: 2.5 },
        itemStyle: { color: "#f97316", borderColor: "#fff", borderWidth: 2 },
        areaStyle: {
          color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(249,115,22,0.18)" },
            { offset: 1, color: "rgba(249,115,22,0)" },
          ]),
        },
      },
    ],
  });

  // 2. 平台分布 — 水平条形图
  const platformColors = ["#6366f1", "#3b82f6", "#0ea5e9", "#14b8a6", "#10b981", "#84cc16", "#eab308", "#f97316"];
  platformChart?.setOption({
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e2e8f0",
      textStyle: { color: "#334155", fontSize: 12 },
    },
    grid: { top: 12, right: 48, bottom: 12, left: 96 },
    xAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.1)" } },
      axisLabel: { color: "#94a3b8", fontSize: 10 },
    },
    yAxis: {
      type: "category",
      data: sources.map((s) => s.label),
      inverse: true,
      axisLabel: { color: "#334155", fontSize: 11, fontWeight: 700 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [{
      type: "bar",
      data: sources.map((s, i) => ({
        value: s.value,
        itemStyle: { color: platformColors[i % platformColors.length] },
      })),
      barWidth: sources.length <= 2 ? 22 : 16,
      itemStyle: { borderRadius: [0, 999, 999, 0] },
      label: {
        show: true,
        position: "right",
        color: "#64748b",
        fontSize: 11,
        fontWeight: 800,
        formatter: "{c} 条",
      },
    }],
  });

  // 3. 关键词热度 — 水平条形图 暖色渐变
  const kwReversed = [...keywords].reverse();
  keywordChart?.setOption({
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e2e8f0",
      textStyle: { color: "#334155", fontSize: 12 },
    },
    grid: { top: 12, right: 48, bottom: 12, left: 100 },
    xAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.1)" } },
      axisLabel: { color: "#94a3b8", fontSize: 10 },
    },
    yAxis: {
      type: "category",
      data: kwReversed.map((k) => k.label),
      axisLabel: { color: "#334155", fontSize: 11, fontWeight: 700 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [{
      type: "bar",
      data: kwReversed.map((k) => k.value),
      barWidth: keywords.length <= 3 ? 22 : 14,
      itemStyle: {
        color: new window.echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: "#f97316" },
          { offset: 1, color: "#fb923c" },
        ]),
        borderRadius: [0, 999, 999, 0],
      },
      label: {
        show: true,
        position: "right",
        color: "#64748b",
        fontSize: 11,
        fontWeight: 800,
      },
    }],
  });

  // 4. 舆情倾向 — 环形图
  sentimentChart?.setOption({
    tooltip: {
      trigger: "item",
      backgroundColor: "rgba(255,255,255,0.96)",
      borderColor: "#e2e8f0",
      textStyle: { color: "#334155", fontSize: 12 },
      formatter: (p) => `${p.marker} ${p.name}：${p.value} 条（${p.percent}%）`,
    },
    series: [{
      type: "pie",
      radius: ["46%", "72%"],
      center: ["50%", "50%"],
      padAngle: 4,
      label: {
        show: true,
        formatter: "{b}\n{d}%",
        color: "#334155",
        fontSize: 11,
        fontWeight: 800,
        lineHeight: 16,
      },
      itemStyle: {
        borderRadius: 10,
        borderColor: "#fff",
        borderWidth: 3,
      },
      emphasis: {
        scaleSize: 8,
        itemStyle: { shadowBlur: 12, shadowColor: "rgba(0,0,0,0.1)" },
      },
      data: sentiment.map((s) => ({
        value: s.value,
        name: s.label,
        itemStyle: { color: s.color },
      })),
    }],
  });

  // 5. 情感演变 — 时间序列堆叠面积图（升级 3：事件时间轴）
  if (hasSentimentTrend.value && sentimentTrendRef.value) {
    sentimentTrendChart = ensureChart(sentimentTrendRef, sentimentTrendChart);
    const trend = sentimentTrendData.value;
    const fmt = (iso) => {
      try {
        const d = new Date(iso);
        const pad = (n) => String(n).padStart(2, "0");
        return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:00`;
      } catch (e) { return iso; }
    };
    sentimentTrendChart?.setOption({
      tooltip: {
        trigger: "axis",
        axisPointer: {
          type: "line",
          lineStyle: { color: "#6366f1", type: "dashed", width: 1.2 },
        },
        backgroundColor: "rgba(255,255,255,0.98)",
        borderColor: "rgba(99,102,241,0.25)",
        borderWidth: 1,
        padding: [10, 14],
        textStyle: { color: "#0f172a", fontSize: 12, fontWeight: 600 },
        extraCssText:
          "box-shadow: 0 10px 24px -10px rgba(15,23,42,0.18); border-radius: 10px;",
        // P5：tooltip 增加桶粒度说明，让用户理解时间轴是聚合而非原始时间点
        formatter: (params) => {
          if (!Array.isArray(params) || !params.length) return ''
          const bh = trend[0]?.bucket_hours
          const tag = bh === 1 ? '1 小时桶' : bh === 6 ? '6 小时桶' : bh === 24 ? '1 天桶' : '聚合桶'
          const head = `<div style="font-weight:800;color:#0f172a;margin-bottom:4px;">${params[0].axisValueLabel} <span style="color:#94a3b8;font-size:10px;font-weight:700;margin-left:4px;">(${tag})</span></div>`
          const body = params.map(p => {
            return `<div style="display:flex;align-items:center;gap:6px;line-height:1.7;">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${p.color};"></span>
              <span style="color:#475569;font-weight:700;">${p.seriesName}</span>
              <span style="color:#0f172a;font-weight:900;margin-left:auto;">${p.value} 篇</span>
            </div>`
          }).join('')
          return head + body
        },
      },
      legend: {
        data: [
          { name: "正面", icon: "roundRect" },
          { name: "中性", icon: "roundRect" },
          { name: "负面", icon: "roundRect" },
        ],
        top: 6,
        right: 16,
        textStyle: { color: "#475569", fontSize: 11, fontWeight: 700 },
        itemWidth: 14,
        itemHeight: 8,
        itemGap: 16,
      },
      grid: { top: 42, right: 26, bottom: 50, left: 52, containLabel: false },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: trend.map((d) => fmt(d.time)),
        axisLabel: {
          color: "#64748b",
          fontSize: 10,
          fontWeight: 600,
          rotate: 28,
          interval: "auto",
          margin: 10,
        },
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        name: "情报数",
        nameTextStyle: {
          color: "#94a3b8",
          fontSize: 10,
          fontWeight: 700,
          padding: [0, 0, 8, 0],
        },
        splitLine: {
          lineStyle: {
            color: "rgba(148,163,184,0.18)",
            type: "dashed",
          },
        },
        axisLabel: { color: "#94a3b8", fontSize: 10, fontWeight: 600 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          name: "正面",
          type: "line",
          stack: "total",
          smooth: 0.4,
          symbol: "circle",
          symbolSize: 6,
          showSymbol: false,
          emphasis: { focus: "series", scale: 1.6 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(16,185,129,0.6)" },
                { offset: 1, color: "rgba(16,185,129,0.08)" },
              ],
            },
          },
          lineStyle: { color: "#10b981", width: 2 },
          itemStyle: { color: "#10b981", borderColor: "#fff", borderWidth: 2 },
          data: trend.map((d) => d.positive || 0),
        },
        {
          name: "中性",
          type: "line",
          stack: "total",
          smooth: 0.4,
          symbol: "circle",
          symbolSize: 6,
          showSymbol: false,
          emphasis: { focus: "series", scale: 1.6 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(148,163,184,0.55)" },
                { offset: 1, color: "rgba(148,163,184,0.08)" },
              ],
            },
          },
          lineStyle: { color: "#94a3b8", width: 2 },
          itemStyle: { color: "#94a3b8", borderColor: "#fff", borderWidth: 2 },
          data: trend.map((d) => d.neutral || 0),
        },
        {
          name: "负面",
          type: "line",
          stack: "total",
          smooth: 0.4,
          symbol: "circle",
          symbolSize: 6,
          showSymbol: false,
          emphasis: { focus: "series", scale: 1.6 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(239,68,68,0.6)" },
                { offset: 1, color: "rgba(239,68,68,0.08)" },
              ],
            },
          },
          lineStyle: { color: "#ef4444", width: 2 },
          itemStyle: { color: "#ef4444", borderColor: "#fff", borderWidth: 2 },
          data: trend.map((d) => d.negative || 0),
        },
      ],
    });
  }

  // 6. 文章时间轴（F1：单节点级横向时间轴，区别于 #5 的桶聚合面积图）
  if (displayedArticles.value.length >= 3 && articleTimelineRef.value) {
    articleTimelineChart = ensureChart(articleTimelineRef, articleTimelineChart);
    const items = displayedArticles.value
      .map((a) => {
        const ts = _timelineTs(a);
        if (ts === null) return null;
        return {
          name: a.title,
          value: [ts, getSourceName(a.source_id) || a.source_id || "未知源"],
          symbolSize: Math.max(11, Math.min(26, 11 + (Number(a.importance_score) || 0) * 1.6)),
          itemStyle: {
            color: getSentimentColor(a.ai_sentiment),
            borderColor: "#fff",
            borderWidth: 2,
            opacity: 0.82,
            shadowBlur: 6,
            shadowColor: "rgba(15,23,42,0.18)",
          },
          _article: a,
        };
      })
      .filter(Boolean);
    const yCats = Array.from(new Set(items.map((i) => i.value[1])));
    articleTimelineChart?.setOption({
      tooltip: {
        trigger: "item",
        backgroundColor: "rgba(255,255,255,0.98)",
        borderColor: "rgba(99,102,241,0.25)",
        borderWidth: 1,
        padding: [10, 14],
        textStyle: { color: "#0f172a", fontSize: 12, fontWeight: 600 },
        extraCssText:
          "box-shadow: 0 12px 28px -10px rgba(15,23,42,0.18); border-radius: 10px; max-width: 320px; white-space: normal; word-break: break-word; overflow-wrap: anywhere;",
        formatter: (p) => {
          const a = p.data?._article || {};
          const ts = new Date(p.value[0]);
          const pad = (n) => String(n).padStart(2, "0");
          const tStr = `${ts.getFullYear()}-${pad(ts.getMonth() + 1)}-${pad(ts.getDate())} ${pad(ts.getHours())}:${pad(ts.getMinutes())}`;
          const senti = getSentimentLabel(a.ai_sentiment);
          const src = getSourceName(a.source_id) || a.source_id || "";
          const preview = (a.ai_summary || a.content || "").toString().slice(0, 60).replace(/\s+/g, " ");
          const wrap = "white-space:normal;word-break:break-word;overflow-wrap:anywhere;";
          return `<div style="font-weight:800;color:#0f172a;line-height:1.4;margin-bottom:6px;${wrap}">${a.title || "(无标题)"}</div>
            <div style="color:#64748b;font-size:11px;font-weight:700;margin-bottom:4px;${wrap}">${src} · ${tStr}${senti ? ` · <span style='color:${getSentimentColor(a.ai_sentiment)};'>${senti}</span>` : ""}</div>
            ${preview ? `<div style="color:#475569;font-size:11px;line-height:1.5;${wrap}">${preview}…</div>` : ""}
            <div style="color:#6366f1;font-size:10px;font-weight:800;margin-top:6px;">点击查看详情 →</div>`;
        },
      },
      grid: { top: 18, right: 22, bottom: 56, left: 96, containLabel: false },
      xAxis: {
        type: "time",
        axisLabel: {
          color: "#64748b",
          fontSize: 10,
          fontWeight: 600,
          hideOverlap: true,
          formatter: (v) => {
            const d = new Date(v);
            const pad = (n) => String(n).padStart(2, "0");
            return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
          },
        },
        axisLine: { lineStyle: { color: "#cbd5e1" } },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: "rgba(148,163,184,0.18)", type: "dashed" } },
      },
      yAxis: {
        type: "category",
        data: yCats,
        axisLabel: { color: "#334155", fontSize: 11, fontWeight: 700 },
        axisLine: { lineStyle: { color: "#e2e8f0" } },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      dataZoom: [
        { type: "inside", xAxisIndex: 0, filterMode: "filter", zoomOnMouseWheel: true, moveOnMouseMove: true },
        {
          type: "slider", xAxisIndex: 0, height: 14, bottom: 6,
          backgroundColor: "rgba(241,245,249,0.6)",
          fillerColor: "rgba(99,102,241,0.18)",
          borderColor: "transparent",
          handleStyle: { color: "#6366f1", borderColor: "#fff", borderWidth: 2 },
          moveHandleStyle: { color: "#6366f1" },
          textStyle: { color: "#94a3b8", fontSize: 10 },
          showDetail: false,
        },
      ],
      series: [
        {
          type: "scatter",
          data: items,
          emphasis: { scale: 1.3, itemStyle: { opacity: 1 } },
        },
      ],
    });
    if (articleTimelineChart && !articleTimelineChart.__yj_click_bound) {
      articleTimelineChart.on("click", (params) => {
        const a = params?.data?._article;
        if (a) emit("open-article", a);
      });
      articleTimelineChart.__yj_click_bound = true;
    }
  }
};

const resizeCharts = () => {
  timeTrendChart?.resize();
  platformChart?.resize();
  keywordChart?.resize();
  sentimentChart?.resize();
  sentimentTrendChart?.resize();
  articleTimelineChart?.resize();
};

watch(
  () => props.item?.id,
  async (newId) => {
    abortAiSummary();
    if (!newId) return;
    aiSummaryText.value = "";
    timelineMode.value = "time";
    await nextTick();
    setTimeout(renderCharts, 80);
    fetchAiSummary();
  }
);

// 当 sentiment_trend 异步到达时（同一事件 id 但 detail 后注入），重绘演变图
watch(
  () => sentimentTrendData.value.length,
  async () => {
    await nextTick();
    setTimeout(renderCharts, 60);
  }
);

onMounted(async () => {
  await nextTick();
  setTimeout(renderCharts, 120);
  window.addEventListener("resize", resizeCharts);
  fetchAiSummary();
});

onUnmounted(() => {
  abortAiSummary();
  window.removeEventListener("resize", resizeCharts);
  timeTrendChart?.dispose();
  platformChart?.dispose();
  keywordChart?.dispose();
  sentimentChart?.dispose();
  sentimentTrendChart?.dispose();
  articleTimelineChart?.dispose();
});
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 1900;
  background: rgba(15, 23, 42, 0.22);
  backdrop-filter: blur(10px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  overflow-y: auto;
}

.event-modal {
  width: min(1420px, 100%);
  max-height: calc(100vh - 48px);
  background: linear-gradient(180deg, #fbfdff 0%, #f4f7fb 100%);
  border-radius: 28px;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(226, 232, 240, 0.95);
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.18);
  padding-bottom: 28px;
}

.event-modal.modal-box {
  max-width: 1420px;
  padding: 0 0 28px;
}

.event-modal-head {
  padding: 30px 30px 20px;
  display: flex;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  position: relative;
}

.head-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.btn-export-pdf { display: flex; align-items: center; gap: 5px; font-weight: 700; font-size: 12px; border-radius: 10px; min-height: auto; height: 36px; text-transform: none; color: #dc2626; border-color: rgba(220, 38, 38, 0.2); }
.btn-export-pdf:hover { background: #dc2626; color: #fff; border-color: #dc2626; }

.head-copy {
  max-width: 980px;
  margin: 0 auto;
  text-align: center;
  flex: 1;
}

.head-copy h2 {
  font-size: 34px;
  line-height: 1.08;
  letter-spacing: -0.05em;
  color: #0f172a;
  margin: 0;
}


.btn-close {
  width: 44px;
  height: 44px;
  position: absolute;
  top: 28px;
  right: 30px;
}

.capsule-scroll-body {
  padding: 22px 30px 0;
}

.summary-hero {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 24px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

.summary-hero-body {
  padding: 18px;
  display: grid;
  gap: 14px;
}

.chart-section {
  margin-top: 18px;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 0 0 12px;
  padding: 0 4px;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.event-intel-dash {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.intel-card {
  min-height: 286px;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 24px;
  padding: 18px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.04);
}

.intel-card--wide {
  grid-column: 1 / -1;
}

.intel-badge {
  margin-left: auto;
  padding: 2px 10px;
  border-radius: 999px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.intel-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
  margin-bottom: 16px;
}

.chart-viewport {
  width: 100%;
  height: 220px;
}

/* F1 文章时间轴：单节点级横向时间轴（区别于桶聚合面积图） */
.article-timeline-wrap {
  margin: 6px 0 16px;
  padding: 10px 12px 12px;
  background: linear-gradient(180deg, rgba(238, 242, 255, 0.55) 0%, rgba(255, 255, 255, 0) 70%);
  border: 1px solid rgba(199, 210, 254, 0.55);
  border-radius: 16px;
}
.article-timeline-caption {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 800;
  color: #4338ca;
  letter-spacing: 0.02em;
  margin-bottom: 6px;
  padding-left: 4px;
}
.article-timeline-caption iconify-icon {
  font-size: 16px;
  color: #6366f1;
}
.article-timeline-viewport {
  width: 100%;
  height: 260px;
  cursor: pointer;
}
@media (max-width: 768px) {
  .article-timeline-viewport { height: 320px; }
}


.full-width-panel {
  margin-top: 18px;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 24px;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.04);
  overflow: hidden;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.panel-head-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.timeline-count {
  white-space: nowrap;
}

.eh-sort-toggle {
  display: inline-flex;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(100, 116, 139, 0.15);
}
.eh-sort-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 10px;
  font-size: 0.78rem;
  font-weight: 500;
  background: transparent;
  color: rgba(100, 116, 139, 0.5);
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}
.eh-sort-btn:hover {
  background: rgba(100, 116, 139, 0.06);
}
.eh-sort-btn.active {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
  font-weight: 600;
}

.timeline-window-hint {
  font-weight: 600;
  color: #94a3b8;
  margin-left: 4px;
}

.lead-article-card,
.core-summary-card {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 18px;
  background: #ffffff;
}

.lead-article-card {
  padding: 16px;
  text-align: left;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.lead-article-card:hover {
  transform: translateY(-2px);
  border-color: #93c5fd;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
}

.lead-article-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.lead-article-card strong {
  display: block;
  margin-top: 10px;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.5;
}

.lead-article-card p {
  margin: 10px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.75;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.core-summary-card {
  padding: 18px;
}

.core-summary-kicker {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 800;
}

.core-summary-body {
  margin-top: 14px;
  color: #0f172a;
  font-size: 15px;
  line-height: 1.85;
  white-space: pre-wrap;
}
.core-summary-loading {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: #3b82f6;
  font-style: italic;
}

.timeline-list {
  padding: 18px 12px 12px;
  max-height: 620px;
  overflow-y: auto;
}

.timeline-list--rail {
  position: relative;
}

.timeline-list--rail::before {
  content: "";
  position: absolute;
  top: 30px;
  bottom: 30px;
  left: 96px;
  width: 2px;
  background: linear-gradient(to bottom, #c7d2fe 0%, #a5b4fc 50%, #c7d2fe 100%);
  border-radius: 2px;
  pointer-events: none;
}

/* === 年表卡片样式 === */
.timeline-row.tl-card {
  display: grid;
  grid-template-columns: 84px 24px minmax(0, 1fr);
  gap: 14px;
  padding: 12px 12px 12px 0;
  border-radius: 16px;
  cursor: pointer;
  position: relative;
  transition: transform 0.18s ease;
  align-items: flex-start;
}

.timeline-row.tl-card:hover {
  background: transparent;
  transform: translateX(2px);
}

.tl-axis {
  display: flex;
  align-items: center;
  gap: 6px;
  grid-column: 1 / span 2;
  position: relative;
  min-height: 56px;
}

.tl-date-pill {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 78px;
  padding: 8px 6px;
  background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
  color: #fff;
  border-radius: 12px;
  box-shadow: 0 6px 14px -8px rgba(15, 23, 42, 0.45);
  font-family: "Fira Code", "Cascadia Code", monospace;
}
.tl-date-year {
  font-size: 10px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.6);
  letter-spacing: 0.08em;
}
.tl-date-md {
  font-size: 14px;
  font-weight: 900;
  color: #fff;
  letter-spacing: 0.02em;
}
.tl-date-time {
  font-size: 10px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.7);
  letter-spacing: 0.05em;
}

.tl-dot-large {
  width: 16px !important;
  height: 16px !important;
  border: 3px solid #ffffff !important;
  margin: 0 !important;
  flex-shrink: 0;
  z-index: 2;
}

.tl-card-body {
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  padding: 12px 16px 14px;
  box-shadow: 0 4px 12px -8px rgba(15, 23, 42, 0.12);
  transition: box-shadow 0.18s ease, border-color 0.18s ease;
}

.timeline-row.tl-card:hover .tl-card-body {
  box-shadow: 0 12px 26px -12px rgba(59, 130, 246, 0.32);
  border-color: rgba(59, 130, 246, 0.35);
}

.timeline-row {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 12px;
  padding: 12px;
  border-radius: 16px;
  cursor: pointer;
  position: relative;
  transition: background 0.15s ease;
}

.timeline-row:hover {
  background: #f8fbff;
}

.timeline-dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #3b82f6;
  margin-top: 8px;
  margin-left: 2px;
  position: relative;
  z-index: 1;
  border: 2px solid #ffffff;
  transition: transform 0.15s ease;
}

.timeline-row:hover .timeline-dot {
  transform: scale(1.25);
}

.timeline-gap {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  margin-bottom: 6px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
}

.timeline-gap iconify-icon {
  font-size: 12px;
}

.timeline-platform {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.timeline-platform iconify-icon {
  font-size: 14px;
  color: #475569;
}

.timeline-sentiment-chip {
  padding: 1px 8px;
  border: 1px solid;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  background: #ffffff;
}

.timeline-meta {
  display: flex;
  gap: 10px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.timeline-copy h4 {
  margin: 8px 0 0;
  color: #0f172a;
  font-size: 16px;
  line-height: 1.5;
  overflow-wrap: break-word;
  word-break: break-word;
}

.timeline-copy p {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.75;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.24s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

@media (max-width: 960px) {
  .modal-mask {
    padding: 12px;
    align-items: stretch;
  }

  .capsule-scroll-body {
    padding: 18px;
  }

  .head-copy h2 {
    font-size: 28px;
  }

  .event-intel-dash {
    grid-template-columns: 1fr;
  }
}
</style>

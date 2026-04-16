<template>
  <Transition name="modal-fade">
    <div v-if="item" class="modal-mask" @click.self="$emit('close')">
      <section class="event-modal modal-box">
        <div class="event-modal-head">
          <div class="head-copy">
            <h2>{{ item.title }}</h2>
          </div>
          <div class="head-actions">
            <button class="btn-export-pdf btn btn-outline btn-sm" type="button" @click="exportPdf" title="导出PDF">
              <iconify-icon icon="ri:file-pdf-2-line" />
              <span>导出PDF</span>
            </button>
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
                <div class="core-summary-body">{{ coreEventSummary }}</div>
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
            </div>
          </section>

          <section class="full-width-panel card bg-base-100">
            <div class="panel-head">
              <span>全部情报卡</span>
              <span>{{ allArticles.length }} 条</span>
            </div>
            <div class="timeline-list">
              <article
                v-for="article in allArticles"
                :key="article.id"
                class="timeline-row"
                @click="$emit('open-article', article)"
              >
                <div class="timeline-dot"></div>
                <div class="timeline-copy">
                  <div class="timeline-meta">
                    <span>{{ getSourceName(article.source_id) }}</span>
                    <span v-if="formatTime(article.fetch_time)">{{ formatTime(article.fetch_time) }}</span>
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

const props = defineProps({
  item: { type: Object, default: null },
  sourceRegistry: { type: Array, default: () => [] },
});

const emit = defineEmits(["close", "open-article"]);

const timeTrendChartRef = ref(null);
const platformBarRef = ref(null);
const keywordBarRef = ref(null);
const sentimentRingRef = ref(null);
const aiSummaryLoading = ref(false);
const aiSummaryText = ref("");
let aiSummaryAbort = null;

let timeTrendChart = null;
let platformChart = null;
let keywordChart = null;
let sentimentChart = null;

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
  if (aiSummaryLoading.value) return "AI 正在分析中…";
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
    const res = await fetch(`http://localhost:8000/api/articles/${article.id}/analyze`, { signal: controller.signal });
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

const exportPdf = () => {
  if (!props.item?.id) return;
  window.open(`http://localhost:8000/api/events/${props.item.id}/export_pdf`, '_blank');
};

const openRepresentativeArticle = () => {
  if (!representativeArticle.value) return;
  emit("open-article", representativeArticle.value);
};

const timeSeries = computed(() => {
  const buckets = new Map();
  for (const article of allArticles.value) {
    const date = new Date(article.fetch_time || article.pub_date || 0);
    if (Number.isNaN(date.getTime())) continue;
    date.setHours(date.getHours(), 0, 0, 0);
    const key = date.getTime();
    const extra = typeof article.extra_info === "string" ? safeParse(article.extra_info) : {};
    const rawHot = Number(extra.hot_value || extra.hot_score || extra.view || 1);
    const hot = Number.isFinite(rawHot) && rawHot > 0 ? rawHot : 1;
    const current = buckets.get(key) || { count: 0, heat: 0 };
    current.count += 1;
    current.heat += hot;
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
        heat: Number((value.heat / value.count).toFixed(1)),
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

const keywordBreakdown = computed(() => {
  const counter = new Map();
  const pushKeyword = (keyword, weight = 1) => {
    const text = String(keyword || "").trim();
    if (!text || text.length < 2 || text.length > 6) return;
    if (KEYWORD_STOPWORDS.has(text)) return;
    if (/^\d+$/.test(text)) return;
    if (/[()[\]【】{}（）《》〈〉??？!！#…]/.test(text)) return;
    if (/^[a-zA-Z]+$/.test(text)) return;
    if (/^[0-9A-Za-z-]+$/.test(text) && text.length > 4) return;
    if (/\d{1,2}月|\d{1,2}日|\d{4}年/.test(text)) return;
    if (/^(hot|search|weibo|baidu|toutiao|zhihu|cls|bilibili)/i.test(text)) return;
    if (text.includes("核心") || text.includes("研判") || text.includes("时间") || text.includes("条情报")) return;
    if (text.includes("表示") || text.includes("跟进") || text.includes("指出") || text.includes("透露")) return;
    if (/[称说道曰指出认为表示透露了的吗呢吧啊哦呀么过起来去着]$/.test(text)) return;
    if (/^(该|这|那|据|从|在|对|向|把|被|让|给|为|因|但|又|也|再)/.test(text) && text.length <= 3) return;
    counter.set(text, (counter.get(text) || 0) + weight);
  };

  for (const keyword of props.item?.keywords || []) {
    pushKeyword(keyword, 3);
  }

  for (const article of allArticles.value) {
    const seed = `${article.title || ""} ${getArticlePreview(article)}`;
    for (const token of seed.split(/[，。、“”‘’；：:、\s/|?？!！…《》【】#]+/)) {
      pushKeyword(token, 1);
    }
  }

  return [...counter.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);
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
        name: "热度",
        nameTextStyle: { color: "#94a3b8", fontSize: 10 },
        splitLine: { show: false },
        axisLabel: {
          color: "#94a3b8", fontSize: 10,
          formatter: (v) => v >= 1e6 ? (v / 1e6).toFixed(0) + "M" : v >= 1e4 ? (v / 1e4).toFixed(0) + "w" : v,
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
};

const resizeCharts = () => {
  timeTrendChart?.resize();
  platformChart?.resize();
  keywordChart?.resize();
  sentimentChart?.resize();
};

watch(
  () => props.item?.id,
  async (newId) => {
    abortAiSummary();
    if (!newId) return;
    aiSummaryText.value = "";
    await nextTick();
    setTimeout(renderCharts, 80);
    fetchAiSummary();
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

.timeline-list {
  padding: 12px;
  max-height: 560px;
  overflow-y: auto;
}

.timeline-row {
  display: grid;
  grid-template-columns: 20px minmax(0, 1fr);
  gap: 12px;
  padding: 12px;
  border-radius: 16px;
  cursor: pointer;
}

.timeline-row:hover {
  background: #f8fbff;
}

.timeline-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #3b82f6;
  margin-top: 6px;
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

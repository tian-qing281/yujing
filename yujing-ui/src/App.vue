<script setup>
import { computed, defineAsyncComponent, nextTick, onMounted, ref, watch } from "vue";
import { transformToHDS } from "./utils/dataAdapter";
import AIConsultant from "./components/AIConsultant.vue";
import AnalysisModal from "./components/AnalysisModal.vue";
import AppHeader from "./components/AppHeader.vue";
import AppSidebar from "./components/AppSidebar.vue";
import CredentialModal from "./components/CredentialModal.vue";
import EventCard from "./components/EventCard.vue";
import EventModal from "./components/EventModal.vue";
import NewsCard from "./components/NewsCard.vue";
import TopicModal from "./components/TopicModal.vue";

const loadSearchInsightChart = () => import("./components/SearchInsightChart.vue");
const SearchInsightChart = defineAsyncComponent(loadSearchInsightChart);
const EVENT_HUB_REFRESH_TTL = 90 * 1000;

// 缓存容器定义，修复 ReferenceError
const unifiedDataCache = new Map();
let unifiedSearchController = null;
let unifiedSearchRequestId = 0;

let searchInsightPreloadPromise = null;
const preloadSearchInsightChart = () => {
  if (!searchInsightPreloadPromise) {
    searchInsightPreloadPromise = loadSearchInsightChart().catch((error) => {
      searchInsightPreloadPromise = null;
      throw error;
    });
  }
  return searchInsightPreloadPromise;
};

const scheduleSearchInsightPreload = () => {
  if (typeof window === "undefined") return;
  const preload = () => preloadSearchInsightChart().catch(() => {});
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(preload, { timeout: 1200 });
    return;
  }
  window.setTimeout(preload, 300);
};

const SOURCE_LABEL_MAP = {
  weibo_hot_search: "微博热搜榜",
  baidu_hot: "百度热搜榜",
  toutiao_hot: "头条实时榜",
  bilibili_hot_video: "哔哩哔哩榜",
  zhihu_hot_question: "知乎全站榜",
  thepaper_hot: "澎湃热榜",
  wallstreetcn_news: "华尔街热榜",
  cls_telegraph: "财联社热榜",
};

const articles = ref([]);
const events = ref([]);
const searchedEventTotal = ref(0);
const topics = ref([]);
const searchedArticles = ref([]);
const searchedArticleTotal = ref(0);
const unifiedAxes = ref([]);
const unifiedPlatforms = ref([]);
const unifiedSummary = ref({ events: 0, topics: 0, articles: 0 });
const eventQuery = ref("");
const topicQuery = ref("");
const activeEventQuery = ref("");
const activeTopicQuery = ref("");
const eventViewMode = ref("all");
const activeSourceFilter = ref("");
const signalPage = ref(1);
const aggregatedPage = ref(1);
const articlePage = ref(1);

const activeTimeRange = ref(null);
const setTimeRange = (range) => {
  if (activeTimeRange.value === range) return;
  activeTimeRange.value = range;
  signalPage.value = 1;
  aggregatedPage.value = 1;
  articlePage.value = 1;
  unifiedDataCache.clear();
  fetchUnifiedSearch(eventQuery.value, range);
};
const activePlatform = ref("weibo_hot_search");
const isLoadingArticles = ref(false);
const isLoadingEvents = ref(false);
const isLoadingTopics = ref(false);
const isLoadingArticleSearch = ref(false);
const isPaginating = ref(false);
const eventHubLastLoadedAt = ref(0);
const detailItem = ref(null);
const eventDetail = ref(null);
const topicDetail = ref(null);
const overlayStack = ref([]);
const activeTab = ref("visual");
const statusMsg = ref("系统就绪");
const isCredOpen = ref(false);
const isGlobalSyncing = ref(false);
const lastSyncTime = ref("正在对齐节点...");
const lastSyncAt = ref(null);
const aiConsultantRef = ref(null);
const credentialStatus = ref({});
const isCredSubmitting = ref(false);
const credentialFeedback = ref({ type: "", text: "" });
const isChartsReady = ref(false);
const chartsEngine = ref(null);

const preloadChartsEngine = () => {
  if (typeof window === "undefined") return;
  
  // 缓存检测：如果已经挂载或就绪，则静默跳过，不再提示
  if (window.echarts && isChartsReady.value) return;

  const preload = async () => {
    try {
      // 如果 window.echarts 已经存在（浏览器缓存），import 会瞬间完成
      const echarts = await import("echarts");
      window.echarts = echarts;
      
      const wasReady = isChartsReady.value;
      isChartsReady.value = true;
      
      // 仅在首次启动或缓存未命中时提示，避免刷新干扰
      if (!wasReady) {
        const now = new Date().toLocaleTimeString("zh-CN", { hour12: false });
        statusMsg.value = `[${now}] [预热] 核心可视化引擎已就绪`;
        console.log(`%c [预热] ECharts Engine Preloaded at ${now} `, 'background: #2563eb; color: #fff');
      }
    } catch (e) {
      console.error("Charts preheat failed:", e);
    }
  };

  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(preload, { timeout: 3000 });
  } else {
    setTimeout(preload, 2000);
  }
};

const sidebarItems = [
  { id: "weibo_hot_search", name: "微博热搜榜", icon: "ri:weibo-fill" },
  { id: "baidu_hot", name: "百度热搜榜", icon: "ri:baidu-fill" },
  { id: "toutiao_hot", name: "头条实时榜", icon: "ri:fire-line" },
  { id: "bilibili_hot_video", name: "哔哩哔哩榜", icon: "ri:bilibili-fill" },
  { id: "zhihu_hot_question", name: "知乎全站榜", icon: "ri:zhihu-fill" },
  { id: "thepaper_hot", name: "澎湃热榜", icon: "ri:newspaper-line" },
  { id: "wallstreetcn_news", name: "华尔街见闻热榜", icon: "ri:line-chart-line" },
  { id: "cls_telegraph", name: "财联社热榜", icon: "ri:flashlight-line" },
  { id: "event_hub", name: "全景事件", icon: "ri:node-tree" },
  { id: "ai_consultant", name: "AI 助手", icon: "ri:robot-line" },
];

const sourceRegistry = sidebarItems;

const prettifySourceIds = (value) => {
  if (!value || typeof value !== "string") return value || "";
  let normalized = value;
  Object.entries(SOURCE_LABEL_MAP).forEach(([sourceId, label]) => {
    normalized = normalized.replaceAll(sourceId, label);
  });
  return normalized;
};

let currentFetchId = 0;

const fetchArticles = async (force = false) => {
  if (activePlatform.value === "ai_consultant" || activePlatform.value === "event_hub") return;

  const fetchId = ++currentFetchId;
  isLoadingArticles.value = true;
  if (force || articles.value.length === 0) {
    articles.value = [];
  }

  try {
    const url = `http://localhost:8000/api/articles${force ? "?force_refresh=true" : ""}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (fetchId !== currentFetchId) return;

    const data = await res.json();
    const rawRows = Array.isArray(data) ? data : [];
    
    if (rawRows.length > 0) {
      const CHUNK_SIZE = 25;
      let currentIndex = 0;

      const processChunk = () => {
        if (fetchId !== currentFetchId) return;

        const chunk = rawRows.slice(currentIndex, currentIndex + CHUNK_SIZE);
        const transformed = chunk.map(item => transformToHDS(item));
        
        articles.value = [...articles.value, ...transformed];
        
        currentIndex += CHUNK_SIZE;
        
        if (currentIndex < rawRows.length) {
          // 首屏优先：处理完第一批立即关闭 Loading
          if (currentIndex === CHUNK_SIZE) isLoadingArticles.value = false;
          requestAnimationFrame(processChunk);
        } else {
          isLoadingArticles.value = false;
        }
      };
      processChunk();
    } else {
      isLoadingArticles.value = false;
    }

    // 更新同步时间逻辑 (基于已处理或当前首批数据)
    nextTick(() => {
      const fetchTimes = articles.value
        .map((item) => item.fetch_time)
        .filter(Boolean)
        .map((value) => new Date(value).getTime())
        .filter((value) => !Number.isNaN(value));
      const latestTime = fetchTimes.length ? Math.max(...fetchTimes) : Date.now();
      lastSyncAt.value = latestTime;
      lastSyncTime.value = new Date(latestTime).toLocaleTimeString("zh-CN", { hour12: false });
    });
  } catch (error) {
    if (fetchId === currentFetchId) isLoadingArticles.value = false;
  }
};

let eventSearchTimer = null;

const fetchEvents = async (force = false, query = eventQuery.value) => {
  isLoadingEvents.value = true;
  const requestQuery = (query || "").trim();
  try {
    const params = new URLSearchParams();
    if (force) params.set("force_refresh", "true");
    if (requestQuery) params.set("q", requestQuery);
    if (activeTimeRange.value) params.set("time_range", activeTimeRange.value);
    if (activeSourceFilter.value) params.set("source_id", activeSourceFilter.value);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const url = `http://localhost:8000/api/events${suffix}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const totalCount = parseInt(res.headers.get("X-Total-Count") || "0", 10);
    const data = await res.json();
    const nextRows = Array.isArray(data) ? data : [];
    if (nextRows.length > 0 || force || events.value.length === 0) {
      events.value = nextRows;
    }
    unifiedSummary.value = { ...unifiedSummary.value, events: totalCount || nextRows.length };
    eventHubLastLoadedAt.value = Date.now();
    activeEventQuery.value = requestQuery;
    aggregatedPage.value = 1;
    articlePage.value = 1;
  } catch (error) {
    activeEventQuery.value = requestQuery;
  } finally {
    isLoadingEvents.value = false;
  }
};

let topicSearchTimer = null;

const fetchTopics = async (force = false, query = topicQuery.value) => {
  isLoadingTopics.value = true;
  const requestQuery = (query || "").trim();
  try {
    const params = new URLSearchParams();
    if (force) params.set("force_refresh", "true");
    if (requestQuery) params.set("q", requestQuery);
    if (activeTimeRange.value) params.set("time_range", activeTimeRange.value);
    if (activeSourceFilter.value) params.set("source_id", activeSourceFilter.value);
    const suffix = params.toString() ? `?${params.toString()}` : "";
    const url = `http://localhost:8000/api/topics${suffix}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const nextRows = Array.isArray(data) ? data : [];
    if (nextRows.length > 0 || force || topics.value.length === 0) {
      topics.value = nextRows;
    }
    eventHubLastLoadedAt.value = Date.now();
    activeTopicQuery.value = requestQuery;
  } catch (error) {
    activeTopicQuery.value = requestQuery;
  } finally {
    isLoadingTopics.value = false;
  }
};

const fetchArticleSearch = async (query = eventQuery.value, page = articlePage.value, resetPage = false, allowEmptyPageRetry = true) => {
  const requestQuery = (query || "").trim();
  if (!requestQuery) {
    searchedArticles.value = [];
    searchedEventTotal.value = 0;
    searchedArticleTotal.value = 0;
    articlePage.value = 1;
    isLoadingArticleSearch.value = false;
    return;
  }

  if (resetPage) articlePage.value = 1;
  const pageSize = eventViewMode.value === "all" ? 9 : 24;
  const safePage = Math.max(1, page || 1);
  const isPageFlip = !resetPage && safePage !== 1;
  if (isPageFlip) {
    isPaginating.value = true;
  } else {
    isLoadingArticleSearch.value = true;
  }
  try {
    const params = new URLSearchParams();
    params.set("q", requestQuery);
    if (activeTimeRange.value) params.set("time_range", activeTimeRange.value);
    if (activeSourceFilter.value) params.set("source_id", activeSourceFilter.value);
    params.set("limit", String(pageSize));
    params.set("offset", String((safePage - 1) * pageSize));
    const res = await fetch(`http://localhost:8000/api/articles/search_page?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const rawItems = Array.isArray(data?.items) ? data.items : [];
    const nextItems = rawItems.map(item => transformToHDS(item));
    const nextTotal = Number(data?.total || nextItems.length || 0);
    if (!nextItems.length && nextTotal > 0 && safePage > 1 && allowEmptyPageRetry) {
      searchedArticleTotal.value = Math.min(nextTotal, (safePage - 1) * pageSize);
      return fetchArticleSearch(requestQuery, safePage - 1, false, false);
    }
    searchedArticles.value = nextItems;
    searchedArticleTotal.value = nextTotal;
    articlePage.value = safePage;
    return searchedArticleTotal.value;
  } catch (error) {
    if (!searchedArticles.value.length) {
      searchedArticles.value = [];
      searchedArticleTotal.value = 0;
    }
  } finally {
    isLoadingArticleSearch.value = false;
    isPaginating.value = false;
  }
  return searchedArticleTotal.value;
};

const fetchEventSearchPage = async (query = eventQuery.value, page = aggregatedPage.value, resetPage = false, allowEmptyPageRetry = true) => {
  const requestQuery = (query || "").trim();
  if (!requestQuery) {
    searchedEventTotal.value = 0;
    return 0;
  }
  if (resetPage) aggregatedPage.value = 1;
  const pageSize = aggregatedPageSize.value;
  const safePage = Math.max(1, page || 1);
  const isPageFlip = !resetPage && safePage !== 1;
  if (isPageFlip) {
    isPaginating.value = true;
  } else {
    isLoadingEvents.value = true;
  }
  try {
    const params = new URLSearchParams();
    params.set("q", requestQuery);
    if (activeTimeRange.value) params.set("time_range", activeTimeRange.value);
    if (activeSourceFilter.value) params.set("source_id", activeSourceFilter.value);
    params.set("limit", String(pageSize));
    params.set("offset", String((safePage - 1) * pageSize));
    const res = await fetch(`http://localhost:8000/api/events/search_page?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const nextItems = Array.isArray(data?.items) ? data.items : [];
    const nextTotal = Number(data?.total || nextItems.length || 0);
    if (!nextItems.length && nextTotal > 0 && safePage > 1 && allowEmptyPageRetry) {
      searchedEventTotal.value = Math.min(nextTotal, (safePage - 1) * pageSize);
      return fetchEventSearchPage(requestQuery, safePage - 1, false, false);
    }
    events.value = nextItems;
    searchedEventTotal.value = nextTotal;
    aggregatedPage.value = safePage;
    return searchedEventTotal.value;
  } catch (error) {
    if (!events.value.length) searchedEventTotal.value = 0;
  } finally {
    isLoadingEvents.value = false;
    isPaginating.value = false;
  }
  return searchedEventTotal.value;
};

const fetchUnifiedSearch = async (query = eventQuery.value, timeOverride = undefined, page = 1) => {
  const requestQuery = (query || "").trim();
  const effectTimeRange = timeOverride !== undefined ? timeOverride : activeTimeRange.value;
  const cacheKey = `${requestQuery}:${effectTimeRange}:${activeSourceFilter.value}:${page}`;
  const requestId = ++unifiedSearchRequestId;

  // 1. SWR 阶段：尝试从内存瞬间恢复上次视图 (包括分页结果)
  if (unifiedDataCache.has(cacheKey)) {
    const cached = unifiedDataCache.get(cacheKey);
    events.value = cached.events;
    topics.value = cached.topics;
    searchedArticles.value = cached.articles;
    unifiedSummary.value = cached.summary;
    unifiedAxes.value = cached.axes;
    unifiedPlatforms.value = cached.platforms;
    
    // 命中缓存时立即让 UI 显得已就位
    isLoadingEvents.value = false;
    isLoadingTopics.value = false;
    isLoadingArticleSearch.value = false;
    
    // 如果是显式翻页请求，且非静默模式，可在此处滚动至顶部
    window.scrollTo({ top: 0, behavior: 'smooth' });
  } else {
    isLoadingEvents.value = true;
    isLoadingTopics.value = true;
    isLoadingArticleSearch.value = true;
  }

  try {
    if (unifiedSearchController) {
      unifiedSearchController.abort();
    }
    unifiedSearchController = new AbortController();

    const params = new URLSearchParams();
    params.set("q", requestQuery);
    if (effectTimeRange !== null && effectTimeRange !== undefined) params.set("time_range", String(effectTimeRange));
    if (activeSourceFilter.value) params.set("source_id", activeSourceFilter.value);
    params.set("page", String(page));

    const response = await fetch(`http://localhost:8000/api/search/unified?${params.toString()}`, {
      signal: unifiedSearchController.signal,
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (requestId !== unifiedSearchRequestId) return;

    const freshEvents = Array.isArray(data?.events) ? data.events : [];
    const freshTopics = Array.isArray(data?.topics) ? data.topics : [];
    const rawArticles = Array.isArray(data?.articles) ? data.articles : [];
    const freshArticles = rawArticles.map(item => transformToHDS(item));
    const freshSummary = data?.summary || { events: 0, topics: 0, articles: 0 };
    const freshAxes = Array.isArray(data?.axes) ? data.axes : [];
    const freshPlatforms = Array.isArray(data?.platforms) ? data.platforms : [];

    topics.value = freshTopics;
    searchedArticles.value = freshArticles;
    unifiedSummary.value = freshSummary;
    unifiedAxes.value = freshAxes;
    unifiedPlatforms.value = freshPlatforms;
    searchedArticleTotal.value = Number(freshSummary.articles || 0);

    if (requestQuery) {
      const actualEventTotal = await fetchEventSearchPage(requestQuery, page, false, true, false);
      unifiedSummary.value = {
        ...freshSummary,
        events: Number(actualEventTotal || 0),
      };
    }

    unifiedDataCache.set(cacheKey, {
      events: events.value,
      topics: freshTopics,
      articles: freshArticles,
      summary: unifiedSummary.value,
      axes: freshAxes,
      platforms: freshPlatforms,
      timestamp: Date.now()
    });

    eventHubLastLoadedAt.value = Date.now();
    activeEventQuery.value = requestQuery;
    aggregatedPage.value = page; // 同步当前页码
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (requestId !== unifiedSearchRequestId) return;
    console.error("Unified search paging sync failed:", error);
  } finally {
    if (requestId === unifiedSearchRequestId) {
      isLoadingEvents.value = false;
      isLoadingTopics.value = false;
      isLoadingArticleSearch.value = false;
    }
  }
};

const fetchCredentialStatus = async () => {
  try {
    const response = await fetch("http://localhost:8000/api/credentials/status");
    const data = await response.json();
    credentialStatus.value = data && typeof data === "object" ? data : {};
  } catch (error) {
    credentialStatus.value = {};
  }
};

const shouldRefreshEventHub = () => {
  const now = Date.now();
  const isExpired = now - eventHubLastLoadedAt.value > EVENT_HUB_REFRESH_TTL;
  if (eventQuery.value.trim()) {
    return (
      isExpired ||
      (!events.value.length && !searchedArticles.value.length && !topics.value.length)
    );
  }
  return isExpired || (!events.value.length && !topics.value.length);
};

const scheduleEventHubHydration = (force = false) => {
  if (typeof window === "undefined") return;
  window.requestAnimationFrame(() => {
    if (!force && !shouldRefreshEventHub()) return;
    if (eventQuery.value.trim()) {
      fetchUnifiedSearch(eventQuery.value);
      return;
    }
    fetchEvents(force, eventQuery.value);
    if (!activeSourceFilter.value) {
      fetchTopics(force, eventQuery.value);
    }
  });
};

const handleCredentialSubmit = async (payload) => {
  const sourceId = payload?.source_id;
  const cookie = payload?.cookie?.trim?.() || "";

  if (!sourceId || !cookie) {
    credentialFeedback.value = { type: "error", text: "请选择采集源并粘贴有效登录凭据。" };
    return;
  }

  isCredSubmitting.value = true;
  credentialFeedback.value = { type: "", text: "" };

  try {
    const response = await fetch(`http://localhost:8000/api/credentials/${sourceId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ cookie }),
    });
    const data = await response.json();

    if (!response.ok || data?.error) {
      credentialFeedback.value = { type: "error", text: data?.error || "凭据保存失败。" };
      return;
    }

    credentialFeedback.value = {
      type: "success",
      text: data?.message || "凭据已更新。",
    };
    await fetchCredentialStatus();
  } catch (error) {
    credentialFeedback.value = { type: "error", text: "无法连接后端，凭据未保存。" };
  } finally {
    isCredSubmitting.value = false;
  }
};

onMounted(() => {
  // 优先级 1：核心业务数据
  fetchArticles();
  
  // 优先级 2：性能优化预热
  scheduleSearchInsightPreload();
  preloadChartsEngine();
  
  // 优先级 3：非核心后台数据（延迟加载，避免并发冲突）
  setTimeout(() => {
    fetchCredentialStatus();
  }, 2500);

  // 启动即检查同步状态
  pollSyncStatus();

  // 模拟对齐动画
  setTimeout(() => {
    lastSyncTime.value = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  }, 1000);
});

watch(activePlatform, (value) => {
  if (value === "event_hub") {
    scheduleSearchInsightPreload();
    scheduleEventHubHydration(false);
  }
});

watch(eventQuery, (value) => {
  if (activePlatform.value !== "event_hub") return;
  clearTimeout(eventSearchTimer);
  if (!value.trim()) {
    activeEventQuery.value = "";
    activeTopicQuery.value = "";
    eventViewMode.value = "all";
    searchedArticles.value = [];
    searchedEventTotal.value = 0;
    unifiedAxes.value = [];
    unifiedPlatforms.value = [];
    unifiedSummary.value = { events: 0, topics: 0, articles: 0 };
    signalPage.value = 1;
    aggregatedPage.value = 1;
    articlePage.value = 1;
  }
  eventSearchTimer = setTimeout(() => {
    if (value.trim()) {
      preloadSearchInsightChart().catch(() => {});
      fetchUnifiedSearch(value);
    } else {
      fetchEvents(false, value);
      if (activeSourceFilter.value) {
        topics.value = [];
        activeTopicQuery.value = "";
        return;
      }
      fetchTopics(false, value);
    }
  }, 450);
});

watch(isCredOpen, (opened) => {
  if (!opened) return;
  credentialFeedback.value = { type: "", text: "" };
  fetchCredentialStatus();
});

watch(activeSourceFilter, () => {
  if (activePlatform.value !== "event_hub") return;
  signalPage.value = 1;
  aggregatedPage.value = 1;
  articlePage.value = 1;
  if (activeSourceFilter.value) {
    if (eventViewMode.value === "topics") {
      eventViewMode.value = "all";
    }
    topics.value = [];
    activeTopicQuery.value = "";
  }
  if (eventQuery.value.trim()) {
    fetchUnifiedSearch(eventQuery.value);
  } else {
    fetchEvents(false, eventQuery.value);
    if (!activeSourceFilter.value) {
      fetchTopics(false, eventQuery.value);
    }
  }
});

let syncPollCount = 0;
const SYNC_POLL_MAX = 90;
const pollSyncStatus = async () => {
  if (!isGlobalSyncing.value) return;
  syncPollCount++;
  if (syncPollCount > SYNC_POLL_MAX) {
    isGlobalSyncing.value = false;
    syncPollCount = 0;
    fetchArticles(false);
    fetchEvents(false);
    return;
  }
  try {
    const res = await fetch("http://localhost:8000/api/sync/status");
    if (!res.ok) throw new Error("Status API failure");
    const data = await res.json();
    
    const stillFetching = !!data.fetching;
    isGlobalSyncing.value = stillFetching;
    
    if (stillFetching) {
      setTimeout(pollSyncStatus, 2000);
    } else {
      syncPollCount = 0;
      fetchArticles(false);
      fetchEvents(false);
    }
  } catch (e) {
    isGlobalSyncing.value = false;
    syncPollCount = 0;
  }
};

const handleRefresh = async () => {
  if (isGlobalSyncing.value) return;
  
  if (activePlatform.value === "event_hub") {
    if (eventQuery.value.trim()) {
      fetchUnifiedSearch(eventQuery.value);
    } else {
      fetchEvents(true);
      if (activeSourceFilter.value) {
        topics.value = [];
        activeTopicQuery.value = "";
      } else {
        fetchTopics(true, eventQuery.value);
      }
    }
    return;
  }
  
  // 启动同步并进入轮询
  isGlobalSyncing.value = true;
  await fetchArticles(true);
  pollSyncStatus();
};

const filteredArticles = computed(() => articles.value.filter((item) => item.source_id === activePlatform.value));
const canonicalizeEventTitle = (value) =>
  String(value || "")
    .toLowerCase()
    .replace(/进入第\s*\d+\s*天/g, "")
    .replace(/第\s*\d+\s*天/g, "")
    .replace(/第\s*\d+\s*小时/g, "")
    .replace(/\d+\s*小时前/g, "")
    .replace(/\d+\s*分钟前/g, "")
    .replace(/[【】[\]（）()“”"'：:、,，。.？?！!…\-\s_/|]/g, "");

const dedupedEvents = computed(() => {
  const bucket = new Map();
  for (const item of events.value) {
    const key = canonicalizeEventTitle(item.title);
    const existing = bucket.get(key);
    if (!existing) {
      bucket.set(key, item);
      continue;
    }
    const existingScore = (existing.article_count || 0) * 10 + (existing.platform_count || 0) * 4;
    const nextScore = (item.article_count || 0) * 10 + (item.platform_count || 0) * 4;
    if (nextScore > existingScore) {
      bucket.set(key, item);
    }
  }
  return Array.from(bucket.values());
});
const isReadyEvent = (item) =>
  item?.confidence === "stable" || (item?.article_count || 0) >= 2 || (item?.platform_count || 0) >= 2;
const aggregatedEvents = computed(() => dedupedEvents.value.filter((item) => isReadyEvent(item)));
const crossPlatformAggregatedEvents = computed(() => aggregatedEvents.value);
const platformHotEvents = computed(() =>
  aggregatedEvents.value.filter((item) => (item.platform_count || 0) < 2),
);
const pendingEvents = computed(() => dedupedEvents.value.filter((item) => !isReadyEvent(item) && item.confidence === "emerging"));
const singleSignalEvents = computed(() =>
  dedupedEvents.value.filter((item) => !isReadyEvent(item) && item.confidence !== "emerging"),
);
const signalEvents = computed(() => [...pendingEvents.value, ...singleSignalEvents.value]);
const activeSourceLabel = computed(
  () => sourceRegistry.find((item) => item.id === activeSourceFilter.value)?.name || ""
);
const getSourceLabel = (sourceId) =>
  sourceRegistry.find((item) => item.id === sourceId)?.name || SOURCE_LABEL_MAP[sourceId] || sourceId || "未知来源";
const eventStrength = (item) => {
  const articleWeight = (item?.article_count || 0) * 4;
  const platformWeight = (item?.platform_count || 0) * 6;
  const latest = item?.latest_article_time ? new Date(item.latest_article_time).getTime() : 0;
  const freshnessHours = latest ? Math.max(0, (Date.now() - latest) / 3600000) : 999;
  const freshnessWeight = Math.max(0, 24 - Math.min(freshnessHours, 24));
  return articleWeight + platformWeight + freshnessWeight;
};
const sortedAggregatedEvents = computed(() =>
  [...crossPlatformAggregatedEvents.value].sort((a, b) => eventStrength(b) - eventStrength(a))
);
const sortedSignalEvents = computed(() =>
  [...signalEvents.value].sort((a, b) => eventStrength(b) - eventStrength(a))
);
const aggregatedPageSize = computed(() => 9);
const aggregatedTotalCount = computed(() =>
  Math.max(activeEventQuery.value ? searchedEventTotal.value || 0 : 0, sortedAggregatedEvents.value.length)
);
const aggregatedPageCount = computed(() => Math.max(1, Math.ceil(aggregatedTotalCount.value / aggregatedPageSize.value)));
const visibleAggregatedPages = computed(() => {
  const total = aggregatedPageCount.value;
  const current = aggregatedPage.value;
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = [1];
  let start = Math.max(2, current - 1);
  let end = Math.min(total - 1, current + 1);
  if (current <= 3) { start = 2; end = 5; }
  if (current >= total - 2) { start = total - 4; end = total - 1; }
  if (start > 2) pages.push("...");
  for (let i = start; i <= end; i++) pages.push(i);
  if (end < total - 1) pages.push("...");
  pages.push(total);
  return pages;
});
const pagedAggregatedEvents = computed(() => {
  if (activeEventQuery.value) {
    return events.value;
  }
  const start = (aggregatedPage.value - 1) * aggregatedPageSize.value;
  return sortedAggregatedEvents.value.slice(start, start + aggregatedPageSize.value);
});
const signalPageSize = computed(() => (eventViewMode.value === "all" ? 12 : activeEventQuery.value ? 18 : 24));
const signalPageCount = computed(() => Math.max(1, Math.ceil(sortedSignalEvents.value.length / signalPageSize.value)));
const pagedSignalEvents = computed(() => {
  const start = (signalPage.value - 1) * signalPageSize.value;
  return sortedSignalEvents.value.slice(start, start + signalPageSize.value);
});
const visibleAggregatedEvents = computed(() => {
  if (eventViewMode.value === "signals" || eventViewMode.value === "articles") return [];
  return pagedAggregatedEvents.value;
});
const visibleSignalEvents = computed(() => {
  if (eventViewMode.value === "clusters" || eventViewMode.value === "articles") return [];
  return pagedSignalEvents.value;
});
const visibleArticleResults = computed(() => {
  if (!activeEventQuery.value) return [];
  if (eventViewMode.value === "clusters" || eventViewMode.value === "signals") return [];
  return searchedArticles.value;
});
const articlePageSize = computed(() => (eventViewMode.value === "all" ? 9 : 24));
const articleTotalCount = computed(() => Math.max(searchedArticleTotal.value || 0, visibleArticleResults.value.length));
const articlePageCount = computed(() => Math.max(1, Math.ceil(articleTotalCount.value / articlePageSize.value)));
const leadArticleResults = computed(() => {
  if (activeEventQuery.value) {
    return visibleArticleResults.value;
  }
  return visibleArticleResults.value.slice(0, articlePageSize.value);
});
const aggregatedSectionTitle = computed(() => "事件");
const articleSectionTitle = computed(() => (activeEventQuery.value ? "代表情报" : "情报卡直达"));
const signalSectionTitle = computed(() => "单条热搜");
const aggregatedVisibleHint = computed(() => {
  if (!activeEventQuery.value) return "";
  const total = aggregatedTotalCount.value;
  if (!total) return "";
  const start = total ? (aggregatedPage.value - 1) * aggregatedPageSize.value + 1 : 0;
  const end = Math.min(aggregatedPage.value * aggregatedPageSize.value, total);
  if (total <= aggregatedPageSize.value) {
    return `共 ${total} 条结果`;
  }
  return `显示 ${start}-${end} 条，共 ${total} 条`;
});


const signalVisibleHint = computed(() => {
  const visible = visibleSignalEvents.value.length;
  const total = signalEvents.value.length;
  if (!total) return "";
  const start = total ? (signalPage.value - 1) * signalPageSize.value + 1 : 0;
  const end = Math.min(signalPage.value * signalPageSize.value, total);
  return `${start}-${end} / ${total}`;
});
const signalMeta = (item) => {
  const parts = [];
  if (item?.primary_source_id) parts.push(getSourceLabel(item.primary_source_id));
  if (item?.latest_article_time) {
    const date = new Date(item.latest_article_time);
    if (!Number.isNaN(date.getTime())) {
      const month = `${date.getMonth() + 1}`.padStart(2, "0");
      const day = `${date.getDate()}`.padStart(2, "0");
      const hour = `${date.getHours()}`.padStart(2, "0");
      const minute = `${date.getMinutes()}`.padStart(2, "0");
      parts.push(`${month}-${day} ${hour}:${minute}`);
    }
  }
  return parts.join(" · ");
};
const signalStageLabel = (item) => {
  if (item?.confidence === "emerging") return "平台热议";
  if (item?.confidence === "stable" && (item?.platform_count || 0) < 2) return "平台热议";
  return "单条热搜";
};
const signalCountLabel = (item) => ((item?.article_count || 0) <= 1 ? "单条" : `${item.article_count} 条`);
const summarizeSignal = (value) => {
  const text = prettifySourceIds(value || "");
  if (text.length <= 72) return text;
  return `${text.slice(0, 72).trim()}…`;
};
const signalKeywords = (item) => (Array.isArray(item?.keywords) ? item.keywords.slice(0, 2) : []);
const totalVisibleResults = computed(
  () =>
    visibleAggregatedEvents.value.length +
    visibleSignalEvents.value.length +
    leadArticleResults.value.length
);
const resultSnapshotLabel = computed(() => "");
const searchAxisPills = computed(() => unifiedAxes.value.slice(0, 6));
const searchPlatformPills = computed(() => unifiedPlatforms.value.slice(0, 5));
const searchInsightSummary = computed(() => ({
  events: unifiedSummary.value.events || aggregatedTotalCount.value || 0,
  articles: unifiedSummary.value.articles || articleTotalCount.value || 0,
  topics: unifiedSummary.value.topics || topics.value.length || 0,
}));
const searchInsightPlatforms = computed(() =>
  unifiedPlatforms.value
    .map((item) => ({
      ...item,
      label: getSourceLabel(item.value),
    }))
    .slice(0, 8)
);
const searchInsightAxes = computed(() => unifiedAxes.value.slice(0, 8));
const searchInsightTimeline = computed(() => {
  const rows = [...searchedArticles.value, ...visibleAggregatedEvents.value, ...visibleSignalEvents.value];
  const buckets = new Map();

  rows.forEach((item) => {
    const rawTime = item?.fetch_time || item?.pub_date || item?.latest_article_time || item?.latest_event_time;
    const date = new Date(rawTime || 0);
    if (Number.isNaN(date.getTime()) || date.getTime() <= 0) return;
    date.setMinutes(0, 0, 0);
    const key = date.getTime();
    buckets.set(key, (buckets.get(key) || 0) + 1);
  });

  return [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .slice(-10)
    .map(([time, count]) => {
      const date = new Date(time);
      const month = `${date.getMonth() + 1}`.padStart(2, "0");
      const day = `${date.getDate()}`.padStart(2, "0");
      const hour = `${date.getHours()}`.padStart(2, "0");
      return { label: `${month}-${day} ${hour}:00`, count };
    });
});
const axisTypeLabel = (type) => {
  if (type === "country") return "国家";
  if (type === "brand") return "品牌";
  if (type === "person") return "人物";
  return "议题";
};
const groupedSearchAxes = computed(() => {
  const groups = [];
  for (const type of ["country", "person", "brand", "topic"]) {
    const items = searchAxisPills.value.filter((item) => item.type === type).slice(0, 3);
    if (items.length) {
      groups.push({ type, label: axisTypeLabel(type), items });
    }
  }
  return groups;
});
const activeAxisValue = computed(() => (activeEventQuery.value || eventQuery.value || "").trim());
const activePlatformFacet = computed(() => activeSourceFilter.value || "");
const eventPlatforms = computed(() =>
  sourceRegistry.filter((item) =>
    [
      "weibo_hot_search",
      "baidu_hot",
      "toutiao_hot",
      "bilibili_hot_video",
      "zhihu_hot_question",
      "thepaper_hot",
      "wallstreetcn_news",
      "cls_telegraph",
    ].includes(item.id)
  )
);
const latestEventTouchedAt = computed(() => {
  const rows = [...events.value, ...topics.value];
  const timestamps = rows
    .map((item) => new Date(item.latest_article_time || item.latest_event_time || 0).getTime())
    .filter((value) => !Number.isNaN(value) && value > 0);
  if (!timestamps.length) return "";
  return new Date(Math.max(...timestamps)).toLocaleString("zh-CN", { hour12: false });
});
const overviewMetrics = computed(() => [
  { 
    label: "事件", 
    value: unifiedSummary.value.events || (activeEventQuery.value ? 0 : events.value.length) 
  },
  { 
    label: "热搜", 
    value: unifiedSummary.value.articles || (activeEventQuery.value ? 0 : articles.value.length) 
  },
]);
const eventHubSummaryLine = computed(() => {
  if (activeEventQuery.value) {
    const eventCount = unifiedSummary.value.events || crossPlatformAggregatedEvents.value.length;
    const articleCount = unifiedSummary.value.articles || searchedArticles.value.length;
    const scope = activeSourceLabel.value ? `，当前平台：${activeSourceLabel.value}` : "";
    return `检索 ${activeEventQuery.value}，命中 ${eventCount} 个事件、${articleCount} 张情报卡${scope}`;
  }
  return "";
});

watch([signalPageCount, aggregatedPageCount, articlePageCount, eventViewMode], () => {
  if (signalPage.value > signalPageCount.value) {
    signalPage.value = signalPageCount.value;
  }
  if (signalPage.value < 1) {
    signalPage.value = 1;
  }
  if (aggregatedPage.value > aggregatedPageCount.value) {
    aggregatedPage.value = aggregatedPageCount.value;
  }
  if (aggregatedPage.value < 1) {
    aggregatedPage.value = 1;
  }
  if (articlePage.value > articlePageCount.value) {
    articlePage.value = articlePageCount.value;
  }
  if (articlePage.value < 1) {
    articlePage.value = 1;
  }
});

const clearOverlayStack = () => {
  overlayStack.value = [];
};

const pushOverlay = (type, payload) => {
  overlayStack.value.push({ type, payload });
};

const restorePreviousOverlay = () => {
  if (!overlayStack.value.length) return false;
  const previous = overlayStack.value.pop();
  if (previous.type === "event") {
    eventDetail.value = previous.payload;
  } else if (previous.type === "topic") {
    topicDetail.value = previous.payload;
  }
  return true;
};

const applyAxis = (value) => {
  eventQuery.value = value;
  eventViewMode.value = "all";
  signalPage.value = 1;
  aggregatedPage.value = 1;
  articlePage.value = 1;
};

const applyPlatformFacet = (sourceId) => {
  activeSourceFilter.value = activeSourceFilter.value === sourceId ? "" : sourceId;
  eventViewMode.value = "all";
  signalPage.value = 1;
  aggregatedPage.value = 1;
  articlePage.value = 1;
};

const goToArticlePage = (page) => {
  const nextPage = Math.min(Math.max(1, page), articlePageCount.value);
  if (nextPage === articlePage.value && searchedArticles.value.length) return;
  if (activeEventQuery.value) {
    fetchArticleSearch(activeEventQuery.value, nextPage);
    return;
  }
  articlePage.value = nextPage;
};

const goToAggregatedPage = (page) => {
  const nextPage = Math.min(Math.max(1, page), aggregatedPageCount.value);
  if (nextPage === aggregatedPage.value && visibleAggregatedEvents.value.length) return;

  if (activeEventQuery.value) {
    fetchEventSearchPage(activeEventQuery.value, nextPage);
    return;
  }

  if (eventQuery.value.trim()) {
    fetchEventSearchPage(eventQuery.value.trim(), nextPage);
    return;
  }

  aggregatedPage.value = nextPage;
};

const openDetail = (item, options = {}) => {
  if (!options.preserveStack) {
    clearOverlayStack();
  }

  const article = articles.value.find((entry) => entry.id === item.id) || item;
  detailItem.value = article;
  activeTab.value = "report";

  nextTick(() => {
    const hasVisual = article.wordcloud && article.wordcloud.length > 0;
    const hasSummary = article.ai_summary && article.ai_summary.length > 0;
    if (!hasVisual && !hasSummary && !article.isAnalyzing) {
      triggerAI();
    }
  });
};

const openEventDetail = async (item, options = {}) => {
  if (!options.preserveStack) {
    clearOverlayStack();
  }

  try {
    const response = await fetch(`http://localhost:8000/api/events/${item.id}`);
    const data = await response.json();
    
    eventDetail.value = data?.id ? data : null;
  } catch (error) {
    eventDetail.value = null;
  }
};

const openTopicDetail = async (item, options = {}) => {
  if (!options.preserveStack) {
    clearOverlayStack();
  }

  try {
    const response = await fetch(`http://localhost:8000/api/topics/${item.id}`);
    const data = await response.json();
    
    // Simplification: skip TopicModal if there's only 1 target Event
    if (data?.related_events?.length === 1) {
      openEventDetail(data.related_events[0], { preserveStack: options.preserveStack });
      return;
    }

    topicDetail.value = data?.id ? data : null;
  } catch (error) {
    topicDetail.value = null;
  }
};

const openArticleFromEvent = (article) => {
  if (eventDetail.value?.id) {
    pushOverlay("event", eventDetail.value);
  }
  eventDetail.value = null;
  openDetail(article, { preserveStack: true });
};

const openEventFromTopic = (eventRow) => {
  if (topicDetail.value?.id) {
    pushOverlay("topic", topicDetail.value);
  }
  topicDetail.value = null;
  openEventDetail(eventRow, { preserveStack: true });
};

const openArticleFromTopic = (article) => {
  if (topicDetail.value?.id) {
    pushOverlay("topic", topicDetail.value);
  }
  topicDetail.value = null;
  openDetail(article, { preserveStack: true });
};

const closeDetailModal = () => {
  const restored = restorePreviousOverlay();
  if (restored) {
    requestAnimationFrame(() => {
      detailItem.value = null;
    });
    return;
  }
  detailItem.value = null;
};

const closeEventModal = () => {
  const previous = overlayStack.value[overlayStack.value.length - 1];
  if (previous?.type === "topic") {
    topicDetail.value = previous.payload;
    overlayStack.value.pop();
    requestAnimationFrame(() => {
      eventDetail.value = null;
    });
    return;
  }
  eventDetail.value = null;
};

const closeTopicModal = () => {
  topicDetail.value = null;
};

const syncArticleState = (patch) => {
  const id = patch.id;
  if (!id) return;
  if (detailItem.value && detailItem.value.id === id) {
    Object.assign(detailItem.value, patch);
  }
  const idx = articles.value.findIndex((a) => a.id === id);
  if (idx !== -1) {
    Object.assign(articles.value[idx], patch);
  }
  const sIdx = searchedArticles.value.findIndex((a) => a.id === id);
  if (sIdx !== -1) {
    Object.assign(searchedArticles.value[sIdx], patch);
  }
};

const triggerAI = async (force = false) => {
  if (!detailItem.value) return;
  const item = detailItem.value;
  if (item.isAnalyzing) return;
  const articleId = item.id;
  let summaryBuffer = force ? "" : item.ai_summary || "";
  let sseBuffer = "";

  const baseState = {
    id: articleId,
    isAnalyzing: true,
    ai_summary: summaryBuffer,
    raw_content: force ? "" : item.raw_content || "",
    wordcloud: force ? [] : item.wordcloud || [],
    emotions: force ? [] : item.emotions || [],
  };
  syncArticleState(baseState);
  statusMsg.value = "正在从全站镜像同步分析数据...";

  try {
    const url = `http://localhost:8000/api/articles/${articleId}/analyze${force ? "?force_refresh=true" : ""}`;
    const response = await fetch(url);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      sseBuffer += decoder.decode(value, { stream: true });
      const lines = sseBuffer.split("\n");
      sseBuffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === "status") {
            statusMsg.value = data.msg;
          } else if (data.type === "content_start") {
            summaryBuffer = "";
            syncArticleState({ id: articleId, ai_summary: "" });
          } else if (data.type === "metadata") {
            syncArticleState({ id: articleId, wordcloud: data.wordcloud, emotions: data.emotions });
          } else if (data.type === "raw_content") {
            syncArticleState({ id: articleId, raw_content: data.text });
          } else if (data.type === "content") {
            summaryBuffer += data.text;
            syncArticleState({ id: articleId, ai_summary: summaryBuffer });
          } else if (data.type === "content_end") {
            syncArticleState({ id: articleId, isAnalyzing: false });
          } else if (data.type === "skip_video") {
            // 后端已识别为视频并从库中移除 → 关闭 modal + 刷新列表
            syncArticleState({ id: articleId, isAnalyzing: false });
            activeItem.value = null;
            statusMsg.value = data.msg || "此热点为视频内容，已从榜单移除";
            await fetchUnifiedSearch(eventQuery.value, activeTimeRange.value === null ? 720 : activeTimeRange.value);
            return;
          }
        } catch (error) {
        }
      }
    }
    if (sseBuffer.startsWith("data: ")) {
      try {
        const data = JSON.parse(sseBuffer.slice(6));
        if (data.type === "content") {
          summaryBuffer += data.text;
          syncArticleState({ id: articleId, ai_summary: summaryBuffer });
        } else if (data.type === "content_end") {
          syncArticleState({ id: articleId, isAnalyzing: false });
        }
      } catch (error) {
      }
    }
    const now = Date.now();
    lastSyncAt.value = now;
    lastSyncTime.value = new Date(now).toLocaleTimeString("zh-CN", {
      hour12: false,
    });
  } catch (error) {
    syncArticleState({ id: articleId, isAnalyzing: false });
  } finally {
    syncArticleState({ id: articleId, isAnalyzing: false });
  }
};

onMounted(() => {
  // 核心修复：移除 redundant 调用，数据加载由统一入口 fetchUnifiedSearch 负责
  fetchUnifiedSearch(eventQuery.value, activeTimeRange.value === null ? 720 : activeTimeRange.value);
  scheduleSearchInsightPreload();
  preloadChartsEngine();
  
  // 模拟对齐动画
  setTimeout(() => {
    lastSyncTime.value = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  }, 1000);
});
</script>

<template>
  <div class="app-container">
    <AppSidebar
      :sourceRegistry="sourceRegistry"
      :currentSource="activePlatform"
      :syncTime="lastSyncTime"
      :syncAt="lastSyncAt"
      @switch="activePlatform = $event"
      @open-cred="isCredOpen = true"
    />

    <main class="main-content">
        <!-- 呼吸式反馈：顶部极窄进度条 -->
        <div class="hs-top-loader" :class="{ active: isLoadingEvents || isLoadingTopics || isLoadingArticleSearch }"></div>
        
        <AIConsultant
          v-if="activePlatform === 'ai_consultant'"
          key="ai_consultant"
          ref="aiConsultantRef"
          :sourceRegistry="sourceRegistry"
          @open-item="openDetail"
        />
        <div v-else-if="activePlatform === 'event_hub'" key="event_workspace" class="article-workspace">
          <AppHeader
            currentSourceName="全景事件聚合"
            :currentSourceIcon="sidebarItems.find((item) => item.id === 'event_hub')?.icon"
            modeLabel=""
            :loading="isLoadingEvents || isLoadingTopics || isLoadingArticleSearch"
            @refresh="handleRefresh"
          />
          <div class="content-scroll">
            <div class="event-hub-header hs-panel card bg-base-100 overflow-visible">
              <div class="eh-header-grid">
                <div class="eh-search-core">
                  <div class="eh-search-bar-group">
                    <div class="eh-search-input-wrap">
                      <iconify-icon icon="mdi:magnify" class="eh-search-icon" />
                      <input
                        v-model="eventQuery"
                        class="eh-main-input"
                        placeholder="请输入关键词进行全网谱系扫描..."
                                              />
                    </div>
                    
                  </div>
                  <div class="eh-search-meta">
                    <template v-if="activeEventQuery"></template>
                    <template v-else>{{ eventHubSummaryLine }}</template>
                  </div>
                </div>

                <div class="eh-metrics-grid">
                  <div v-for="metric in overviewMetrics" :key="metric.label" class="eh-metric-card">
                    <div class="eh-metric-info">
                      <span class="eh-metric-label">{{ metric.label }}</span>
                      <strong class="eh-metric-value">{{ metric.value }}</strong>
                    </div>
                    <div class="eh-metric-icon-sw">
                      <iconify-icon :icon="metric.label.includes('事件') ? 'mdi:folder-star' : 'mdi:rss'" />
                    </div>
                  </div>
                </div>
              </div>

              <div class="eh-command-bar">
                <div class="join eh-btn-group">
                  <button class="join-item eh-pill-btn" :class="activeTimeRange === null ? 'active' : ''" @click="setTimeRange(null)">全部</button>
                  <button class="join-item eh-pill-btn" :class="activeTimeRange === 24 ? 'active' : ''" @click="setTimeRange(24)">24小时</button>
                  <button class="join-item eh-pill-btn" :class="activeTimeRange === 168 ? 'active' : ''" @click="setTimeRange(168)">7天</button>
                  <button class="join-item eh-pill-btn" :class="activeTimeRange === 720 ? 'active' : ''" @click="setTimeRange(720)">30天</button>
                </div>
              </div>

              

              <!-- SearchInsightChart 暂时禁用 -->
            </div>


            <!-- loading feedback handled by top-loader bar -->
            
            <div v-if="activeEventQuery && !isLoadingEvents && totalVisibleResults === 0" class="event-empty card bg-base-100">
              <span class="event-empty-kicker badge badge-primary badge-outline">暂无结果</span>
              <h3>
                {{ activeSourceLabel || "当前视角" }} 暂未找到“{{ activeEventQuery }}”相关的重点事件或结果
              </h3>
            </div>



            <div v-if="events.length === 0 && !isLoadingEvents" class="eh-empty-state">
              <div class="eh-empty-box bg-base-100/50 backdrop-blur-xl border border-dashed border-base-content/20 rounded-3xl p-12 text-center">
                <iconify-icon icon="mdi:magnify-close" class="text-6xl text-base-content/20 mb-4" />
                <h3 class="text-xl font-bold mb-2">未找到"{{ eventQuery }}"相关事件</h3>
                <p class="text-base-content/60">试试换个关键词</p>
              </div>
            </div>

            <div v-if="events.length > 0" class="eh-workspace-section">
              <div class="section-head">
                <h4 class="section-title">{{ aggregatedSectionTitle }}</h4>
                <div class="section-head-meta">
                    <span class="section-note badge badge-ghost">{{ aggregatedVisibleHint }}</span>
                </div>
              </div>
              <div v-if="activeEventQuery" class="article-grid event-grid" :class="{ 'is-paginating': isPaginating }">
                <EventCard
                  v-for="(item, idx) in events"
                  :key="item.id"
                  :item="item"
                  :query="activeEventQuery"
                  :sourceRegistry="sourceRegistry"
                  :style="{ '--item-index': idx }"
                  @click="openEventDetail(item)"
                />
              </div>
              <TransitionGroup v-else name="list" tag="div" class="article-grid event-grid">
                <EventCard
                  v-for="(item, idx) in events"
                  :key="item.id"
                  :item="item"
                  :query="activeEventQuery"
                  :sourceRegistry="sourceRegistry"
                  :style="{ '--item-index': idx }"
                  @click="openEventDetail(item)"
                />
              </TransitionGroup>

              <div v-if="activeEventQuery && aggregatedPageCount > 1" class="eh-pagination-wrapper">
                <button
                  class="eh-page-btn eh-page-arrow"
                  :disabled="aggregatedPage <= 1"
                  @click="goToAggregatedPage(aggregatedPage - 1)"
                >
                  <iconify-icon icon="mdi:chevron-left" />
                </button>

                <template v-for="(p, idx) in visibleAggregatedPages" :key="idx">
                  <span v-if="p === '...'" class="eh-page-ellipsis">…</span>
                  <button
                    v-else
                    class="eh-page-btn"
                    :class="{ 'eh-page-active': aggregatedPage === p }"
                    @click="goToAggregatedPage(p)"
                  >
                    {{ p }}
                  </button>
                </template>

                <button
                  class="eh-page-btn eh-page-arrow"
                  :disabled="aggregatedPage >= aggregatedPageCount"
                  @click="goToAggregatedPage(aggregatedPage + 1)"
                >
                  <iconify-icon icon="mdi:chevron-right" />
                </button>

                <span v-if="isPaginating" class="eh-page-loading">
                  <span class="loading loading-spinner loading-xs"></span>
                </span>

              </div>
            </div>
          </div>
        </div>

        <div v-else key="article_workspace" class="article-workspace">
        <AppHeader
          :currentSourceName="sidebarItems.find((item) => item.id === activePlatform)?.name"
          :currentSourceIcon="sidebarItems.find((item) => item.id === activePlatform)?.icon"
          :loading="isLoadingArticles || isGlobalSyncing"
          @refresh="handleRefresh"
        />

        <div class="content-scroll">
          <TransitionGroup name="list" tag="div" class="article-grid">
            <NewsCard
              v-for="(item, idx) in filteredArticles"
              :key="item.id"
              :item="item"
              :index="idx"
              @click="openDetail(item)"
            />
          </TransitionGroup>
        </div>
        </div>
    </main>

    <AnalysisModal
      :item="detailItem"
      :sourceName="sourceRegistry.find((item) => item.id === detailItem?.source_id)?.name || '未知源'"
      :statusMsg="statusMsg"
      v-model:activeTab="activeTab"
      @close="closeDetailModal"
      @trigger-ai="triggerAI"
    />

    <CredentialModal
      v-if="isCredOpen"
      :sourceRegistry="sourceRegistry"
      :submitting="isCredSubmitting"
      :credentialStatus="credentialStatus"
      :feedback="credentialFeedback"
      @close="isCredOpen = false"
      @submit="handleCredentialSubmit"
    />

    <EventModal
      :item="eventDetail"
      :sourceRegistry="sourceRegistry"
      @close="closeEventModal"
      @open-article="openArticleFromEvent"
    />

    <TopicModal
      :item="topicDetail"
      :sourceRegistry="sourceRegistry"
      @close="closeTopicModal"
      @open-event="openEventFromTopic"
      @open-article="openArticleFromTopic"
    />
  </div>
</template>

<style>
@import url("https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@400;500;600;700;800;900&display=swap");

html, body { margin: 0 !important; padding: 0 !important; width: 100% !important; height: 100% !important; overflow: hidden; }

:root {
  --bg-main: var(--hs-bg, #f5f8fc);
  --bg-sidebar: #09111f;
  --accent: var(--hs-primary-2, #3b82f6);
  --text-main: var(--hs-ink, #07111f);
}

* { margin: 0; padding: 0; box-sizing: border-box; outline: none; }
body { font-family: "Fira Sans", "PingFang SC", "Microsoft YaHei", sans-serif; background: var(--bg-main); color: var(--text-main); -webkit-font-smoothing: antialiased; }

.app-container {
  position: fixed;
  inset: 0;
  display: flex !important;
  align-items: stretch !important;
  justify-content: flex-start !important;
}
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  background:
    linear-gradient(90deg, rgba(255,255,255,0.62), rgba(255,255,255,0.16)),
    radial-gradient(circle at 72% 12%, rgba(30, 64, 175, 0.08), transparent 28rem);
  min-width: 0;
}

/* 呼吸式加载条样式 */
.hs-top-loader {
  position: absolute;
  top: 0;
  left: 0;
  width: 0%;
  height: 2px;
  background: linear-gradient(90deg, #3b82f6 0%, #60a5fa 100%);
  z-index: 2000;
  transition: width 0.4s cubic-bezier(0.1, 0, 0, 1), opacity 0.3s ease;
  opacity: 0;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.4);
}
.hs-top-loader.active {
  width: 100%;
  opacity: 1;
}

.article-workspace { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.content-scroll { flex: 1; overflow-y: auto; padding: 32px 40px 64px; background: transparent; }

.content-scroll::before {
  content: "";
  display: block;
  width: min(1560px, 100%);
  height: 12px;
  margin: 0 auto 16px;
  border-top: 1px solid rgba(226, 232, 240, 0.94);
  opacity: 0.92;
}

.article-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 28px; max-width: 1560px; margin: 0 auto; align-content: start; }
.event-grid { grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); }
.signal-grid { grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); }

.event-toolbar-shell {
  max-width: 1560px;
  margin: 0 auto 18px;
  display: grid;
  gap: 12px;
}

.compact-summary-strip {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 14px 16px;
  border-radius: 24px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  background: linear-gradient(180deg, rgba(255,255,255,0.94) 0%, rgba(248,250,252,0.86) 100%);
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.04);
}

.event-hub-header {
  margin-bottom: 28px;
  padding: 24px;
}

.eh-header-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  align-items: center;
  gap: 24px;
}

.eh-branding-core {
  display: flex;
  flex-direction: column;
}

.eh-kicker-pro {
  font-size: 9px;
  font-weight: 900;
  letter-spacing: 0.15em;
  padding-inline: 4px;
  height: 18px;
}

.eh-title-pro {
  font-size: 26px;
  font-weight: 900;
  letter-spacing: -0.01em;
  color: #0f172a;
}

.eh-status-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
  margin-top: 4px;
}

.eh-search-core {
  min-width: 0;
  width: min(100%, 920px);
  justify-self: end;
}

.eh-search-bar-group {
  display: flex;
  align-items: center;
  background: white;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 100px;
  padding: 8px 18px 8px 20px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
  transition: all 0.3s ease;
}

.eh-search-bar-group:focus-within {
  border-color: #3b82f6;
  box-shadow: 0 10px 28px rgba(37, 99, 235, 0.12);
}

.eh-search-input-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}

.eh-search-icon {
  font-size: 18px;
  color: #94a3b8;
}

.eh-main-input {
  width: 100%;
  border: none;
  background: transparent;
  padding: 10px 0;
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  outline: none;
}

.eh-main-input::placeholder {
  color: #a0aec0;
  font-weight: 600;
}

.eh-search-meta {
  margin-top: 10px;
  padding-left: 20px;
  font-size: 12px;
  font-weight: 700;
  color: #94a3b8;
  display: flex;
  align-items: center;
  gap: 8px;
}

.eh-metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.eh-metric-card {
  background: rgba(248, 250, 252, 0.8);
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 16px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  transition: all 0.2s ease;
}

.eh-metric-card:hover {
  background: white;
  border-color: #3b82f6;
}

.eh-metric-info {
  display: flex;
  flex-direction: column;
}

.eh-metric-label {
  font-size: 10px;
  font-weight: 800;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.eh-metric-value {
  font-size: 18px;
  font-weight: 900;
  color: #0f172a;
  line-height: 1;
  margin-top: 2px;
}

.eh-metric-icon-sw {
  font-size: 20px;
  color: #3b82f6;
  opacity: 0.8;
}

.eh-command-bar {
  display: flex;
  align-items: center;
  gap: 40px;
  flex-wrap: wrap;
  padding: 14px 24px;
  background: rgba(248, 250, 252, 0.5);
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.eh-filter-cluster {
  display: flex;
  align-items: center;
  gap: 14px;
}

.eh-cluster-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 800;
  color: #94a3b8;
}

.eh-btn-group {
  background: rgba(255, 255, 255, 0.8);
  padding: 3px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.1);
}

.eh-pill-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.eh-pill-btn {
  border: none !important;
  background: transparent !important;
  border-radius: 9px !important;
  font-size: 11px !important;
  font-weight: 800 !important;
  height: 28px !important;
  min-height: 28px !important;
  padding-inline: 14px !important;
  color: #64748b;
  transition: all 0.2s ease;
}

.eh-pill-btn.active {
  background: #3b82f6 !important;
  color: white !important;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
}

.eh-pill-btn.active-neutral {
  background: #0f172a !important;
  color: white !important;
}

.eh-pill-btn:hover:not(.active):not(.active-neutral) {
  background: rgba(0, 0, 0, 0.05) !important;
}

.eh-facets {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 24px;
  background: rgba(0, 0, 0, 0.01);
  border-radius: 16px;
  border-top: none;
}

.eh-facet-row {
  display: flex;
  align-items: center;
  gap: 20px;
}

.eh-facet-label {
  font-size: 11px;
  font-weight: 900;
  color: #cbd5e1;
  text-transform: uppercase;
  min-width: 50px;
  padding-top: 0;
}

.toolbar-status {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.workspace-section {
  max-width: 1560px;
  margin: 0 auto 24px;
}

.topic-section {
  padding-bottom: 24px;
  border-bottom: 1px dashed rgba(203, 213, 225, 0.6);
}

.signal-section {
  padding-top: 4px;
}

.signal-wall {
  display: grid;
  gap: 16px;
}

.signal-row {
  appearance: none;
  width: 100%;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: rgba(255,255,255,0.88);
  border-radius: 18px;
  padding: 16px 18px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: center;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
  animation: item-rise 0.48s cubic-bezier(0.16, 1, 0.3, 1) both;
  animation-delay: calc(min(var(--item-index, 0), 8) * 38ms);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
}

.signal-row:hover {
  border-color: rgba(148, 163, 184, 0.38);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.06);
  transform: translateY(-2px);
}

.signal-row-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.signal-row-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.signal-row-kicker {
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.signal-row-meta {
  color: #94a3b8;
  font-size: 12px;
  font-weight: 700;
}

.signal-row-title {
  color: #0f172a;
  font-size: 17px;
  line-height: 1.35;
  font-weight: 800;
}

.signal-row-summary {
  color: #64748b;
  font-size: 13px;
  line-height: 1.65;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.signal-row-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.signal-row-count {
  color: #0f172a;
  font-size: 14px;
  font-weight: 800;
}

.signal-row-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.signal-row-tag {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
}

.section-title {
  margin-bottom: 0;
  color: #0f172a;
  font-size: 20px;
  font-weight: 900;
  letter-spacing: -0.03em;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px 24px;
  border-radius: 20px;
  background: var(--bg-surface, rgba(255, 255, 255, 0.6));
  border: 1px solid rgba(0, 0, 0, 0.04);
}

.section-note {
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
}

.section-head-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.pager-inline {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.88);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.95);
}

.pager-inline-text {
  color: #94a3b8;
  font-size: 12px;
  font-weight: 800;
}

.section-link {
  color: #334155 !important;
  font-size: 12px;
  font-weight: 800;
  text-transform: none;
}

.section-link:not(:disabled):hover {
  background: #eff6ff;
  color: #1d4ed8 !important;
}

.section-link:disabled {
  color: #cbd5e1 !important;
  cursor: not-allowed;
}

.event-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 20px;
  align-items: center;
  padding: 22px 24px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 28px;
  background:
    linear-gradient(135deg, rgba(255,255,255,0.97) 0%, rgba(248,250,252,0.92) 100%);
  box-shadow: var(--hs-shadow, 0 18px 55px rgba(15, 23, 42, 0.08));
  position: relative;
  overflow: hidden;
  animation: panel-rise 0.52s cubic-bezier(0.16, 1, 0.3, 1) both;
}

.event-toolbar::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(circle at 16% 10%, rgba(59,130,246,0.09), transparent 18rem);
  opacity: 0.82;
}

@keyframes panel-rise {
  from { opacity: 0; transform: translateY(18px) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

@keyframes item-rise {
  from { opacity: 0; transform: translateY(18px) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.event-toolbar-copy {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.toolbar-kicker {
  color: #2563eb;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  width: fit-content;
  text-transform: none;
}

.event-toolbar-copy h3 {
  font-size: 20px;
  line-height: 1.15;
  letter-spacing: -0.04em;
  color: #0f172a;
}

.event-toolbar-copy p {
  margin-top: 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.6;
}

.toolbar-meta {
  margin-left: 10px;
}

.event-mode-strip {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.toolbar-filter-panel {
  margin-top: 2px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  padding: 14px;
  border-radius: 28px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  background: linear-gradient(180deg, rgba(255,255,255,0.92) 0%, rgba(248,250,252,0.84) 100%);
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.05);
}

.toolbar-filter-cluster {
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 14px;
  border-radius: 20px;
  border: 1px solid rgba(226, 232, 240, 0.84);
  background: rgba(255, 255, 255, 0.92);
}

.toolbar-group-label {
  width: fit-content;
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.toolbar-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-start;
}

.toolbar-choice {
  min-height: 38px;
  padding-inline: 16px;
  font-size: 13px;
  font-weight: 800;
  border-width: 1px;
  border-radius: 999px;
  text-transform: none;
  transition: all 0.18s ease;
}

.toolbar-choice--idle {
  background: rgba(255, 255, 255, 0.92);
  border-color: rgba(203, 213, 225, 0.92);
  color: #475569;
}

.toolbar-choice--idle:hover {
  border-color: rgba(96, 165, 250, 0.42);
  background: #eff6ff;
  color: #1d4ed8;
}

.toolbar-choice--active {
  background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
  border-color: #2563eb;
  color: #ffffff;
  box-shadow: 0 12px 26px rgba(37, 99, 235, 0.22);
}

.toolbar-choice--active span {
  color: rgba(255, 255, 255, 0.82);
}

.toolbar-choice--mode-active {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  border-color: #0f172a;
}

.source-filter-note {
  margin-top: 10px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.source-pill {
  color: #475569;
  font-size: 12px;
  font-weight: 800;
  transition: all 0.2s ease;
  min-height: auto;
  height: 36px;
  text-transform: none;
}

.mode-pill {
  color: #475569;
  font-size: 12px;
  font-weight: 800;
  transition: all 0.2s ease;
  min-height: auto;
  height: 36px;
  text-transform: none;
}

.event-search {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 54px;
  padding: 0 18px;
  border-radius: 18px;
  border: 1px solid rgba(203, 213, 225, 0.95);
  background: #ffffff;
  color: #64748b;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);
  width: 100%;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.event-search:focus-within {
  border-color: rgba(37, 99, 235, 0.55);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.12), inset 0 1px 0 rgba(255,255,255,0.8);
  transform: translateY(-1px);
}

.event-search input {
  flex: 1;
  border: 0;
  background: transparent;
  color: #0f172a;
  font: inherit;
  font-size: 14px;
}

.event-search input::placeholder {
  color: #94a3b8;
}

.event-search input:focus {
  outline: none;
}

.time-btn {
  color: #64748b;
  font-size: 13px;
  font-weight: 800;
  transition: all 0.2s ease;
  height: 36px;
  text-transform: none;
}

.event-empty {
  max-width: 1560px;
  margin: 0 auto 20px;
  padding: 26px 28px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(248,250,252,0.88) 100%);
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.04);
  animation: panel-rise 0.42s cubic-bezier(0.16, 1, 0.3, 1) both;
}

.event-loading-state {
  margin: 14px auto 20px;
  max-width: 1560px;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 24px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(59, 130, 246, 0.12);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.06), 0 0 15px rgba(59, 130, 246, 0.05);
  color: #1e40af;
  font-size: 13px;
  font-weight: 800;
  animation: panel-rise 0.3s ease-out;
}
.event-loading-state .loading { color: #3b82f6; }

.loading-line {
  height: 10px;
  min-height: 10px;
  border-radius: 999px;
}

.event-empty-kicker {
  color: #2563eb;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.event-empty h3 {
  margin-top: 10px;
  font-size: 24px;
  line-height: 1.15;
  letter-spacing: -0.04em;
  color: #0f172a;
}

.event-empty p {
  margin-top: 10px;
  color: #64748b;
  font-size: 14px;
  line-height: 1.7;
}

.eh-pagination-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 36px auto 64px;
}

.eh-page-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  height: 40px;
  padding: 0 6px;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.88);
  color: #334155;
  font-size: 13px;
  font-weight: 700;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.2s ease;
  backdrop-filter: blur(8px);
  user-select: none;
}

.eh-page-btn:hover:not(:disabled) {
  border-color: rgba(59, 130, 246, 0.4);
  background: rgba(239, 246, 255, 0.9);
  color: #1e40af;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
}

.eh-page-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.eh-page-btn.eh-page-active {
  border-color: #1e40af;
  background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%);
  color: #fff;
  box-shadow: 0 4px 14px rgba(30, 64, 175, 0.3);
  font-weight: 800;
}

.eh-page-arrow {
  font-size: 16px;
}

.eh-page-ellipsis {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  color: #94a3b8;
  font-size: 14px;
  letter-spacing: 2px;
  user-select: none;
}

.eh-page-loading {
  margin-left: 8px;
  color: #3b82f6;
}

.event-grid.is-paginating {
  opacity: 0.45;
  transition: opacity 0.12s ease-out;
  pointer-events: none;
}

@media (max-width: 960px) {
  .axis-group {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .axis-group-label {
    padding-top: 0;
  }

  .content-scroll {
    padding: 18px 20px 28px;
  }

  .article-grid {
    grid-template-columns: 1fr;
    gap: 18px;
  }

  .event-toolbar {
    grid-template-columns: 1fr;
    padding: 18px;
  }

  .overview-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .toolbar-filter-panel {
    grid-template-columns: 1fr;
  }

  .toolbar-pill-row {
    gap: 10px;
  }

  .event-toolbar-copy h3 {
    font-size: 18px;
  }

  .signal-row {
    grid-template-columns: 1fr;
  }

  .signal-row-side {
    align-items: flex-start;
  }

  .signal-row-tags {
    justify-content: flex-start;
  }

  .eh-pagination-wrapper {
    margin: 24px auto 40px;
    gap: 4px;
  }

  .eh-page-btn {
    min-width: 36px;
    height: 36px;
    border-radius: 10px;
    font-size: 12px;
  }
}

@media (max-width: 640px) {
  .overview-stats {
    grid-template-columns: 1fr;
  }

  .event-toolbar {
    padding: 16px;
  }

  .toolbar-filter-panel,
  .toolbar-filter-cluster {
    padding: 12px;
  }
}

.list-enter-active, .list-leave-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.list-enter-from, .list-leave-to { opacity: 0; transform: translateY(8px); }
.list-move { transition: transform 0.18s ease; }

@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.anim-spin { animation: spin 1s infinite linear; }

iconify-icon { display: inline-block; width: 1.2em; height: 1.2em; }
</style>


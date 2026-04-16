<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { marked } from "marked";

const topicAnalysisStore = new Map();

const getTopicAnalysisRecord = (topicId) => {
  if (!topicAnalysisStore.has(topicId)) {
    topicAnalysisStore.set(topicId, {
      text: "",
      status: "",
      analyzing: false,
      completed: false,
      eventSource: null,
      listeners: new Set(),
    });
  }
  return topicAnalysisStore.get(topicId);
};

const emitTopicAnalysis = (topicId) => {
  const record = getTopicAnalysisRecord(topicId);
  const snapshot = {
    text: record.text,
    status: record.status,
    analyzing: record.analyzing,
    completed: record.completed,
  };
  record.listeners.forEach((listener) => listener(snapshot));
};

const patchTopicAnalysis = (topicId, patch = {}) => {
  const record = getTopicAnalysisRecord(topicId);
  Object.assign(record, patch);
  emitTopicAnalysis(topicId);
  return record;
};

const subscribeTopicAnalysis = (topicId, listener) => {
  const record = getTopicAnalysisRecord(topicId);
  record.listeners.add(listener);
  listener({
    text: record.text,
    status: record.status,
    analyzing: record.analyzing,
    completed: record.completed,
  });
  return () => {
    record.listeners.delete(listener);
  };
};

const closeTopicAnalysisStream = (topicId) => {
  const record = topicAnalysisStore.get(topicId);
  if (!record?.eventSource) return;
  record.eventSource.close();
  record.eventSource = null;
};

const ensureTopicAnalysis = (topicId) => {
  if (!topicId) return;
  const record = getTopicAnalysisRecord(topicId);
  if (record.analyzing || (record.completed && record.text)) {
    emitTopicAnalysis(topicId);
    return;
  }

  patchTopicAnalysis(topicId, {
    text: record.completed ? record.text : "",
    status: "已启动研判指令...",
    analyzing: true,
    completed: false,
  });

  closeTopicAnalysisStream(topicId);
  const apiUrl = `http://localhost:8000/api/topics/${topicId}/analyze`;
  const eventSource = new EventSource(apiUrl);
  record.eventSource = eventSource;

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === "status") {
        patchTopicAnalysis(topicId, { status: data.msg });
      } else if (data.type === "content_start") {
        patchTopicAnalysis(topicId, { text: "", status: "" });
      } else if (data.type === "content") {
        const current = getTopicAnalysisRecord(topicId);
        patchTopicAnalysis(topicId, { text: `${current.text}${data.text}`, status: "" });
      } else if (data.type === "content_end") {
        patchTopicAnalysis(topicId, { analyzing: false, completed: true, status: "" });
        closeTopicAnalysisStream(topicId);
      } else if (data.type === "error") {
        patchTopicAnalysis(topicId, {
          status: `研判中断: ${data.msg}`,
          analyzing: false,
          completed: false,
        });
        closeTopicAnalysisStream(topicId);
      }
    } catch (e) {
      console.error("SSE Parse Error", e);
    }
  };

  eventSource.onerror = () => {
    patchTopicAnalysis(topicId, {
      analyzing: false,
      completed: false,
      status: getTopicAnalysisRecord(topicId).status || "研判链路异常",
    });
    closeTopicAnalysisStream(topicId);
  };
};

const props = defineProps({
  item: { type: Object, default: null },
  sourceRegistry: { type: Array, default: () => [] },
});

const emit = defineEmits(["close", "open-event", "open-article"]);

const analysisText = ref("");
const analysisStatus = ref("");
const analyzing = ref(false);
let unsubscribeAnalysis = null;

// Pagination & Interaction
const displayLimit = ref(10);
const expandedEventId = ref(null);
const eventArticlesCache = ref({});
const isFetchingSub = ref(null);

const visibleEvents = computed(() => {
  return props.item?.related_events?.slice(0, displayLimit.value) || [];
});

const quickEntryEvents = computed(() => visibleEvents.value.slice(0, 4));

const loadMore = () => {
  displayLimit.value += 12;
};

const sentimentLabel = computed(() => {
  const map = { positive: "正面回馈", negative: "负向舆情", neutral: "中性态态势" };
  return map[props.item?.sentiment] || "中性态势";
});

const getSourceName = (id) => {
  const hit = props.sourceRegistry.find((item) => item.id === id);
  return hit ? hit.name : "情报源";
};

const formatTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  const m = (date.getMonth() + 1).toString().padStart(2, "0");
  const d = date.getDate().toString().padStart(2, "0");
  const hh = date.getHours().toString().padStart(2, "0");
  const mm = date.getMinutes().toString().padStart(2, "0");
  return `${m}-${d} ${hh}:${mm}`;
};

const renderMarkdown = (text) => {
  return marked.parse(text || "");
};

const isSingleArticleEvent = (event) => Number(event?.article_count || 0) <= 1;

const ensureEventArticles = async (event) => {
  if (eventArticlesCache.value[event.id]) {
    return eventArticlesCache.value[event.id];
  }

  isFetchingSub.value = event.id;
  try {
    const res = await fetch(`http://localhost:8000/api/events/${event.id}`);
    const data = await res.json();
    eventArticlesCache.value[event.id] = data.related_articles || [];
  } catch (e) {
    console.error(e);
    eventArticlesCache.value[event.id] = [];
  } finally {
    isFetchingSub.value = null;
  }

  return eventArticlesCache.value[event.id];
};

const openSingleEventArticle = async (event) => {
  const articles = await ensureEventArticles(event);
  if (articles.length > 0) {
    emit("open-article", articles[0]);
    return;
  }
  emit("open-event", event);
};

const handleCardClick = async (event) => {
  if (isSingleArticleEvent(event)) {
    await openSingleEventArticle(event);
    return;
  }

  if (expandedEventId.value === event.id) {
    expandedEventId.value = null;
    return;
  }

  expandedEventId.value = event.id;
  await ensureEventArticles(event);
};

const handleTitleClick = async (event) => {
  if (isSingleArticleEvent(event)) {
    await openSingleEventArticle(event);
    return;
  }

  emit("open-event", event);
};

const openRepresentativeArticle = async (event) => {
  const articles = await ensureEventArticles(event);
  if (articles.length > 0) {
    emit("open-article", articles[0]);
    return;
  }
  emit("open-event", event);
};

const bindTopicAnalysis = (topicId) => {
  if (unsubscribeAnalysis) {
    unsubscribeAnalysis();
    unsubscribeAnalysis = null;
  }
  if (!topicId) {
    analysisText.value = "";
    analysisStatus.value = "";
    analyzing.value = false;
    return;
  }
  unsubscribeAnalysis = subscribeTopicAnalysis(topicId, (snapshot) => {
    analysisText.value = snapshot.text;
    analysisStatus.value = snapshot.status;
    analyzing.value = snapshot.analyzing;
  });
  ensureTopicAnalysis(topicId);
};

onMounted(() => {
  bindTopicAnalysis(props.item?.id);
});

onUnmounted(() => {
  if (unsubscribeAnalysis) {
    unsubscribeAnalysis();
    unsubscribeAnalysis = null;
  }
});

watch(
  () => props.item?.id,
  (topicId) => {
    bindTopicAnalysis(topicId);
    if (topicId && props.item) {
      displayLimit.value = 10;
      expandedEventId.value = null;
    }
  }
);
</script>

<template>
  <Transition name="modal-fade">
    <div v-if="item" class="modal-mask" @click.self="$emit('close')">
      <section class="topic-modal modal-box hs-panel">
        <!-- TOP STICKY HEADER -->
        <header class="topic-header">
          <div class="header-inner">
            <div class="topic-branding">
              <span class="badge badge-primary badge-outline">专题视图</span>
              <span class="topic-id">ID: {{ item.id }}</span>
            </div>
            <div class="topic-main-title">
              <h1>{{ item.title }}</h1>
              <div class="topic-meta">
                <span class="meta-pill badge badge-ghost">{{ item.platform_count }} 平台聚合</span>
                <span class="meta-pill badge badge-ghost">{{ item.event_count }} 关联事件集群</span>
                <span class="meta-pill sentiment badge" :class="item.sentiment">{{ sentimentLabel }}</span>
              </div>
            </div>
            <button class="btn-close btn btn-circle btn-ghost" @click="$emit('close')">
              <iconify-icon icon="mdi:close"></iconify-icon>
            </button>
          </div>
        </header>

        <div class="topic-layout-container">
          <!-- LEFT: EVENT PIPELINE (THE SUB-EVENTS) -->
          <main class="pipeline-column">
            <div v-if="quickEntryEvents.length" class="quick-entry-shell">
              <div class="quick-entry-head">
                <span>快速进入</span>
                <span>直接跳到事件卡 / 情报卡</span>
              </div>
              <div class="quick-entry-grid">
                <button
                  v-for="event in quickEntryEvents"
                  :key="`quick-${event.id}`"
                  type="button"
                  class="quick-entry-card card bg-base-100"
                  @click="isSingleArticleEvent(event) ? openSingleEventArticle(event) : emit('open-event', event)"
                >
                  <span class="quick-entry-kicker badge badge-outline badge-primary">
                    {{ isSingleArticleEvent(event) ? "单条情报" : "事件卡片" }}
                  </span>
                  <strong>{{ event.title }}</strong>
                  <span class="quick-entry-meta">
                    {{ event.platform_count }} 平台 · {{ event.article_count }} 条
                  </span>
                </button>
              </div>
            </div>
            <div class="column-label badge badge-ghost">关联原生事件管线 ({{ item.related_events?.length || 0 }})</div>
            <div class="pipeline-scroll">
              <!-- Event Pipeline Cards -->
              <div
                v-for="event in visibleEvents"
                :key="event.id"
                class="pipeline-card card bg-base-100"
                :class="{ expanded: expandedEventId === event.id, single: isSingleArticleEvent(event) }"
              >
                <!-- Card Header/Summary Area -->
                <div class="card-main-area" @click="handleCardClick(event)">
                  <div class="pipeline-meta">
                    <span class="platform-name">{{ getSourceName(event.primary_source_id) }}</span>
                    <span class="time-stamp">{{ formatTime(event.latest_article_time) }}</span>
                  </div>
                  <h3 class="pipeline-title" @click.stop="handleTitleClick(event)">
                    {{ event.title }}
                  </h3>
                  <p class="pipeline-summary">{{ event.summary || "聚合条目的深度分析摘要可用。" }}</p>
                  <div class="pipeline-footer">
                    <span v-if="event.article_count">
                      {{ isSingleArticleEvent(event) ? "直达单条情报" : `${event.article_count} 条情报追踪` }}
                    </span>
                    <iconify-icon
                      :icon="isSingleArticleEvent(event) ? 'mdi:arrow-right-thin' : (expandedEventId === event.id ? 'mdi:chevron-up' : 'mdi:chevron-down')"
                    ></iconify-icon>
                  </div>
                  <div class="pipeline-actions">
                    <button
                      v-if="!isSingleArticleEvent(event)"
                      type="button"
                      class="pipeline-action btn btn-outline btn-sm"
                      @click.stop="emit('open-event', event)"
                    >
                      进入事件卡
                    </button>
                    <button
                      type="button"
                      class="pipeline-action primary btn btn-neutral btn-sm"
                      @click.stop="openRepresentativeArticle(event)"
                    >
                      打开情报卡
                    </button>
                  </div>
                </div>

                <!-- Card Expanded Body (Sub-Articles) -->
                <Transition name="expand">
                  <div v-if="expandedEventId === event.id" class="expand-detail">
                    <div v-if="isFetchingSub === event.id" class="sub-loader">
                      <div class="loading-spin"></div>
                      <span>情报流水对齐中...</span>
                    </div>
                    <div v-else class="sub-article-grid">
                      <div
                        v-for="art in eventArticlesCache[event.id]?.slice(0, 5)"
                        :key="art.id"
                        class="sub-art-link card bg-base-100"
                        @click.stop="$emit('open-article', art)"
                      >
                        <span class="art-source badge badge-ghost">{{ getSourceName(art.source_id) }}</span>
                        <span class="art-title">{{ art.title }}</span>
                        <iconify-icon icon="mdi:arrow-right-thin"></iconify-icon>
                      </div>
                    </div>
                  </div>
                </Transition>
              </div>

              <!-- Load More Button -->
              <div
                v-if="item.related_events?.length > displayLimit"
                class="load-more-box"
                @click="loadMore"
              >
                <span>展开更多 {{ item.related_events.length - displayLimit }} 个事件节点</span>
                <iconify-icon icon="mdi:dots-horizontal"></iconify-icon>
              </div>
            </div>
          </main>

          <!-- RIGHT: INTELLIGENCE SIDEBAR -->
          <aside class="insight-sidebar">
            <div class="sidebar-tabs solo">
              <div class="tab-item active btn btn-neutral">智能研判</div>
            </div>

            <section class="insight-card ai-analysis card bg-base-100">
              <div class="card-head">
                <iconify-icon icon="mdi:robot-confused-outline"></iconify-icon>
                <span>AI 宏观态势研判报告</span>
                <div v-if="analyzing" class="loading loading-spinner loading-xs text-primary"></div>
              </div>
              <div class="analysis-body" :class="{ empty: !analysisText && !analyzing }">
                <div v-if="analysisStatus" class="status-tip">{{ analysisStatus }}</div>
                <div
                  v-if="analysisText"
                  class="markdown-view"
                  v-html="renderMarkdown(analysisText)"
                ></div>
                <div v-else-if="!analyzing" class="empty-hint">暂无研判快照，请等待生成...</div>
              </div>
            </section>
          </aside>
        </div>
      </section>
    </div>
  </Transition>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(15, 23, 42, 0.4);
  backdrop-filter: blur(12px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 3vh 3vw;
}

.topic-modal {
  width: min(1560px, 98vw);
  height: 94vh;
  background: #fff;
  border-radius: 28px;
  border: 1px solid rgba(226, 232, 240, 0.95);
  box-shadow: 0 40px 120px rgba(15, 23, 42, 0.3);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.topic-header {
  padding: 24px 32px;
  background: linear-gradient(180deg, #fff 0%, #f8fafc 100%);
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
}

.header-inner {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 32px;
}

.topic-branding {
  display: flex;
  flex-direction: column;
}
.badge {
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.04em;
  text-transform: none;
}
.topic-id {
  color: #94a3b8;
  font-size: 10px;
}

.topic-main-title h1 {
  font-size: 26px;
  font-weight: 900;
  letter-spacing: -0.04em;
  color: #0f172a;
  margin: 0;
}
.topic-meta {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.meta-pill {
  font-size: 11px;
  font-weight: 800;
  text-transform: none;
}
.meta-pill.sentiment {
  color: #1d4ed8;
}
.meta-pill.sentiment.negative {
  color: #dc2626;
  background: #fef2f2;
  border-color: rgba(248, 113, 113, 0.2);
}

.btn-close {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  transition: all 0.2s;
}

.topic-layout-container {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 480px;
  min-height: 0;
}

.quick-entry-shell {
  padding: 20px 32px 18px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.6);
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.9) 0%, rgba(255, 255, 255, 0.96) 100%);
}

.quick-entry-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #64748b;
  font-size: 11px;
  font-weight: 900;
  letter-spacing: 0.06em;
  margin-bottom: 12px;
}

.quick-entry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.quick-entry-card {
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 16px;
  padding: 14px 16px;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.quick-entry-card:hover {
  border-color: #93c5fd;
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
  transform: translateY(-2px);
}

.quick-entry-kicker {
  font-size: 10px;
  font-weight: 900;
  letter-spacing: 0.04em;
  text-transform: none;
  width: fit-content;
}

.quick-entry-card strong {
  color: #0f172a;
  font-size: 14px;
  line-height: 1.45;
  font-weight: 800;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.quick-entry-meta {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.pipeline-column {
  display: flex;
  flex-direction: column;
  background: #fff;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.column-label {
  margin: 16px 32px 0;
  width: fit-content;
  font-size: 11px;
  font-weight: 900;
  color: #94a3b8;
  letter-spacing: 0.04em;
}
.pipeline-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 32px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.pipeline-card {
  padding: 24px;
  border-radius: 18px;
  border: 1px solid #f1f5f9;
  cursor: pointer;
  transition: all 0.25s;
  box-shadow: 0 12px 30px rgba(15, 23, 42, 0.04);
}
.pipeline-card:hover {
  border-color: #3b82f6;
  box-shadow: 0 12px 30px rgba(37, 99, 235, 0.08);
  transform: translateX(6px);
}
.pipeline-card.single:hover {
  transform: translateX(4px);
}
.pipeline-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
}
.platform-name {
  color: #3b82f6;
  font-size: 11px;
  font-weight: 900;
}
.time-stamp {
  color: #94a3b8;
  font-size: 11px;
  font-weight: 700;
}
.pipeline-title {
  font-size: 19px;
  font-weight: 900;
  color: #0f172a;
  line-height: 1.4;
  margin: 0;
  transition: color 0.2s;
}
.pipeline-title:hover {
  text-decoration: underline;
  color: #2563eb;
}

.pipeline-summary {
  margin: 12px 0 16px;
  color: #64748b;
  font-size: 14px;
  line-height: 1.7;
}
.pipeline-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #94a3b8;
  font-size: 11px;
  font-weight: 800;
}

.pipeline-actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.pipeline-action {
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 800;
  text-transform: none;
}

.pipeline-action.primary {
  color: #fff;
}

.insight-sidebar {
  background: #f8fafc;
  border-left: 1px solid rgba(226, 232, 240, 0.9);
  padding: 0 24px 24px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.sidebar-tabs {
  position: sticky;
  top: 0;
  z-index: 10;
  background: #f8fafc;
  padding: 24px 0 16px;
  display: flex;
  gap: 10px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.4);
  margin-bottom: 24px;
}
.sidebar-tabs.solo {
  display: block;
}

.tab-item {
  width: 100%;
  font-size: 12px;
  font-weight: 900;
  text-transform: none;
}

.tab-item.active {
  box-shadow: 0 8px 16px rgba(15, 23, 42, 0.15);
}

.insight-card {
  padding: 24px;
  border-radius: 20px;
  border: 1px solid #f1f5f9;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.02);
}

.card-head {
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid #f1f5f9;
  font-size: 12px;
  font-weight: 900;
  color: #475569;
  display: flex;
  align-items: center;
  gap: 8px;
}
.loading-spin {
  color: #3b82f6;
}
@keyframes spin { to { transform: rotate(360deg); } }

.analysis-body {
  font-size: 14px;
  line-height: 1.8;
  color: #334155;
}
.status-tip {
  color: #3b82f6;
  font-style: italic;
  font-weight: 700;
}
.empty-hint {
  color: #94a3b8;
  text-align: center;
  padding: 40px 0;
}
.markdown-view :deep(h1), .markdown-view :deep(h2), .markdown-view :deep(h3) {
  font-size: 16px; font-weight: 900; margin: 20px 0 10px; color: #0f172a;
}
.markdown-view :deep(p) { margin-bottom: 12px; }

.load-more-box {
  padding: 16px;
  background: #f8fafc;
  border: 1px dashed #e2e8f0;
  border-radius: 12px;
  text-align: center;
  cursor: pointer;
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 16px 0;
}
.load-more-box:hover {
  background: #f1f5f9;
  color: #3b82f6;
  border-color: #3b82f6;
}

.expand-detail {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #f1f5f9;
}
.sub-loader {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 0;
  color: #94a3b8;
  font-size: 12px;
  justify-content: center;
}
.sub-article-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sub-art-link {
  display: grid;
  grid-template-columns: 80px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.sub-art-link:hover {
  background: #eff6ff;
  transform: translateX(4px);
  color: #2563eb;
}
.art-source {
  font-weight: 900;
  font-size: 10px;
  color: #94a3b8;
  text-transform: none;
  width: fit-content;
}
.art-title {
  color: #334155;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  max-height: 800px;
  overflow: hidden;
}
.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
  transform: translateY(-10px);
}

@media (max-width: 1200px) {
  .topic-layout-container { grid-template-columns: 1fr; }
  .insight-sidebar { border-left: none; border-top: 1px solid #e2e8f0; }
}
</style>

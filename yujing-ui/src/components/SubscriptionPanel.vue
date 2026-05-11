<template>
  <section class="sub-panel">
    <header class="sub-hero">
      <div class="sub-hero-bg"></div>
      <div class="sub-hero-content">
        <div class="sub-hero-left">
          <div class="sub-kicker">
            <iconify-icon icon="mdi:account-star" />
            <span>个性化订阅</span>
          </div>
          <h2 class="sub-title">我的订阅 · 智能推荐</h2>
          <p class="sub-sub">基于关注关键词、屏蔽词与浏览画像，为你过滤并排序当日热点。</p>
        </div>
        <button class="sub-refresh-btn" type="button" @click="loadAll" :disabled="loading">
          <iconify-icon icon="mdi:refresh" :class="{ 'animate-spin': loading }" />
          <span>刷新</span>
        </button>
      </div>
    </header>

    <div class="sub-grid">
      <!-- 左：订阅词 -->
      <section class="card bg-base-100 sub-card">
        <div class="sub-card-head">
          <iconify-icon icon="mdi:tag-heart" />
          <span>关注关键词 / 事件</span>
          <span class="sub-count">{{ subscriptions.length }}</span>
        </div>
        <div class="sub-form">
          <select v-model="newSubKind" class="sub-select">
            <option value="keyword">关键词</option>
            <option value="event">事件</option>
            <option value="source">数据源</option>
          </select>
          <input
            v-model.trim="newSubValue"
            class="sub-input"
            placeholder="例如：伊朗 / 央行 / 微博热搜"
            @keydown.enter="addSubscription"
          />
          <button class="sub-btn sub-btn--primary" type="button" :disabled="!newSubValue" @click="addSubscription">
            <iconify-icon icon="mdi:plus" /><span>添加</span>
          </button>
        </div>
        <ul class="sub-list">
          <li v-for="s in subscriptions" :key="s.id" class="sub-chip">
            <span class="sub-chip-kind">{{ KIND_LABEL[s.kind] || s.kind }}</span>
            <span class="sub-chip-value">{{ s.value }}</span>
            <button class="btn btn-ghost btn-xs btn-circle" type="button" @click="removeSubscription(s.id)">
              <iconify-icon icon="mdi:close" />
            </button>
          </li>
          <li v-if="!subscriptions.length" class="sub-empty">还没有任何订阅，快添加你关心的关键词或事件。</li>
        </ul>
      </section>

      <!-- 中：屏蔽词 -->
      <section class="card bg-base-100 sub-card">
        <div class="sub-card-head">
          <iconify-icon icon="mdi:eye-off" />
          <span>屏蔽词</span>
          <span class="sub-count">{{ blocklist.length }}</span>
        </div>
        <div class="sub-form">
          <input
            v-model.trim="newBlockTerm"
            class="sub-input"
            placeholder="标题命中即过滤，例如：广告 / 八卦"
            @keydown.enter="addBlock"
          />
          <button class="sub-btn sub-btn--danger" type="button" :disabled="!newBlockTerm" @click="addBlock">
            <iconify-icon icon="mdi:plus" /><span>屏蔽</span>
          </button>
        </div>
        <ul class="sub-list">
          <li v-for="b in blocklist" :key="b.id" class="sub-chip sub-chip--block">
            <span class="sub-chip-kind">屏蔽</span>
            <span class="sub-chip-value">{{ b.term }}</span>
            <button class="btn btn-ghost btn-xs btn-circle" type="button" @click="removeBlock(b.id)">
              <iconify-icon icon="mdi:close" />
            </button>
          </li>
          <li v-if="!blocklist.length" class="sub-empty">尚未屏蔽任何词。</li>
        </ul>
      </section>

      <!-- 右：用户画像 -->
      <section class="card bg-base-100 sub-card">
        <div class="sub-card-head">
          <iconify-icon icon="mdi:chart-pie" />
          <span>用户画像</span>
          <span class="sub-count">浏览 {{ profile.history_count || 0 }} 次</span>
        </div>
        <div class="sub-profile-block">
          <div class="sub-profile-label">常看数据源 TOP</div>
          <div class="sub-tag-cloud">
            <span v-for="s in profile.top_sources || []" :key="s.source_id" class="sub-tag">
              {{ SOURCE_LABEL[s.source_id] || s.source_id }}
              <strong>{{ s.weight }}</strong>
            </span>
            <span v-if="!profile.top_sources?.length" class="sub-empty-inline">画像数据为空（点开几篇文章即可生成）</span>
          </div>
        </div>
        <div class="sub-profile-block">
          <div class="sub-profile-label">兴趣标签 TOP</div>
          <div class="sub-tag-cloud">
            <span v-for="t in profile.top_tags || []" :key="t.tag" class="sub-tag sub-tag--accent">
              {{ t.tag }}
              <strong>{{ t.weight }}</strong>
            </span>
            <span v-if="!profile.top_tags?.length" class="sub-empty-inline">暂无标签数据</span>
          </div>
        </div>
      </section>
    </div>

    <!-- 推荐结果 -->
    <section class="sub-recommend card bg-base-100">
      <div class="sub-card-head">
        <iconify-icon icon="mdi:sparkles" />
        <span>为你推荐 · 实时打分</span>
        <span class="sub-count">
          候选 {{ candidatesCount }} · 命中 {{ matchedCount }} · 共 {{ totalCount }} 条
        </span>
        <label class="sub-fallback-toggle" :title="'未命中订阅时，按热度返回 TOP 兜底'">
          <input type="checkbox" v-model="useFallback" @change="reloadRecommend(0)" />
          <span>无命中时按热度兜底</span>
        </label>
      </div>
      <div v-if="loading && !recommendations.length" class="sub-empty sub-empty--big">
        <iconify-icon icon="mdi:loading" class="text-3xl opacity-60 animate-spin" />
        <p>加载中…</p>
      </div>
      <div v-else-if="!recommendations.length" class="sub-empty sub-empty--big">
        <iconify-icon icon="mdi:lightbulb-on-outline" class="text-3xl opacity-50" />
        <p v-if="subscriptions.length === 0">还没有订阅，添加 1-2 个关键词试试。</p>
        <p v-else>没有匹配的事件。可勾选「按热度兜底」或换一个更宽泛的关键词（命中规则：标题包含子串）。</p>
      </div>
      <ol v-else class="sub-rec-list">
        <li
          v-for="(item, idx) in recommendations"
          :key="item.id"
          class="sub-rec-item"
          :class="{ 'sub-rec-item--fallback': item._fallback }"
          @click="$emit('open-event', item)"
        >
          <span class="sub-rec-rank">{{ offset + idx + 1 }}</span>
          <div class="sub-rec-body">
            <strong>{{ item.title }}</strong>
            <div class="sub-rec-meta">
              <span class="sub-rec-score" v-if="!item._fallback">
                <iconify-icon icon="mdi:fire" />匹配 {{ item._recommend_score }}
              </span>
              <span class="sub-rec-score sub-rec-score--fb" v-else>
                <iconify-icon icon="mdi:thermometer" />热度兜底
              </span>
              <span v-for="r in item._recommend_reasons || []" :key="r" class="sub-rec-reason">{{ r }}</span>
              <span class="sub-rec-platform">{{ SOURCE_LABEL[item.primary_source_id] || item.primary_source_id }} · {{ item.article_count }} 条</span>
            </div>
          </div>
          <iconify-icon icon="mdi:chevron-right" class="sub-rec-arrow" />
        </li>
      </ol>
      <div v-if="totalCount > pageSize" class="sub-pager">
        <button class="sub-btn" :disabled="offset === 0 || loading" @click="reloadRecommend(offset - pageSize)">
          <iconify-icon icon="mdi:chevron-left" /><span>上一页</span>
        </button>
        <span class="sub-pager-info">第 {{ currentPage }} / {{ totalPages }} 页</span>
        <button class="sub-btn" :disabled="offset + pageSize >= totalCount || loading" @click="reloadRecommend(offset + pageSize)">
          <span>下一页</span><iconify-icon icon="mdi:chevron-right" />
        </button>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { buildApiUrl } from "../config/api";

defineEmits(["open-event"]);

const KIND_LABEL = { keyword: "关键词", event: "事件", source: "数据源" };
const SOURCE_LABEL = {
  weibo_hot_search: "微博热搜",
  baidu_hot: "百度热搜",
  toutiao_hot: "今日头条",
  bilibili_hot_video: "哔哩哔哩",
  zhihu_hot_question: "知乎全站",
  thepaper_hot: "澎湃热榜",
  wallstreetcn_news: "华尔街见闻",
  cls_telegraph: "财联社",
};

const loading = ref(false);
const subscriptions = ref([]);
const blocklist = ref([]);
const profile = ref({});
const recommendations = ref([]);
const candidatesCount = ref(0);
const matchedCount = ref(0);
const totalCount = ref(0);
const offset = ref(0);
const pageSize = ref(15);
const useFallback = ref(true);
const currentPage = computed(() => Math.floor(offset.value / pageSize.value) + 1);
const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize.value)));

const newSubKind = ref("keyword");
const newSubValue = ref("");
const newBlockTerm = ref("");

const fetchJSON = async (path, init) => {
  const res = await fetch(buildApiUrl(path), init);
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
};

const fetchRecommend = async (newOffset = offset.value) => {
  const params = new URLSearchParams({
    limit: String(pageSize.value),
    offset: String(newOffset),
    fallback: useFallback.value ? "true" : "false",
  });
  const rec = await fetchJSON(`/api/recommendations?${params}`);
  recommendations.value = rec.items || [];
  candidatesCount.value = rec.candidates || 0;
  matchedCount.value = rec.matched ?? rec.items?.length ?? 0;
  totalCount.value = rec.total ?? rec.items?.length ?? 0;
  offset.value = rec.offset ?? newOffset;
};

const reloadRecommend = async (newOffset = 0) => {
  loading.value = true;
  try {
    await fetchRecommend(Math.max(0, newOffset));
  } catch (e) {
    console.error("[SubscriptionPanel] reload recommend failed", e);
  } finally {
    loading.value = false;
  }
};

const loadAll = async () => {
  loading.value = true;
  try {
    const [subs, blocks, prof] = await Promise.all([
      fetchJSON("/api/subscriptions"),
      fetchJSON("/api/blocklist"),
      fetchJSON("/api/profile"),
    ]);
    subscriptions.value = subs;
    blocklist.value = blocks;
    profile.value = prof;
    await fetchRecommend(0);
    offset.value = 0;
  } catch (e) {
    console.error("[SubscriptionPanel] load failed", e);
  } finally {
    loading.value = false;
  }
};

const addSubscription = async () => {
  if (!newSubValue.value) return;
  await fetchJSON("/api/subscriptions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: newSubKind.value, value: newSubValue.value }),
  });
  newSubValue.value = "";
  await loadAll();
};

const removeSubscription = async (id) => {
  await fetch(buildApiUrl(`/api/subscriptions/${id}`), { method: "DELETE" });
  await loadAll();
};

const addBlock = async () => {
  if (!newBlockTerm.value) return;
  await fetchJSON("/api/blocklist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ term: newBlockTerm.value }),
  });
  newBlockTerm.value = "";
  await loadAll();
};

const removeBlock = async (id) => {
  await fetch(buildApiUrl(`/api/blocklist/${id}`), { method: "DELETE" });
  await loadAll();
};

onMounted(loadAll);
</script>

<style scoped>
.sub-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 24px 32px 48px;
  overflow-y: auto;
  height: 100%;
  box-sizing: border-box;
}

/* === Hero 标题 === */
.sub-hero {
  position: relative;
  border-radius: 22px;
  overflow: hidden;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 55%, #ec4899 100%);
  box-shadow: 0 18px 40px -18px rgba(99, 102, 241, 0.55);
  padding: 22px 26px;
  color: #fff;
  min-height: 132px;
  flex-shrink: 0;
}

.sub-hero-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background:
    radial-gradient(circle at 10% 20%, rgba(255, 255, 255, 0.18), transparent 40%),
    radial-gradient(circle at 90% 80%, rgba(255, 255, 255, 0.12), transparent 50%);
}

.sub-hero-content {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.sub-hero-left { flex: 1; min-width: 240px; }

.sub-kicker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  border-radius: 999px;
  backdrop-filter: blur(8px);
}

.sub-title {
  display: block !important;
  font-size: 26px !important;
  font-weight: 900 !important;
  margin: 10px 0 6px !important;
  letter-spacing: 0.5px;
  color: #ffffff !important;
  line-height: 1.3 !important;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.sub-sub {
  display: block !important;
  font-size: 13px !important;
  color: rgba(255, 255, 255, 0.92) !important;
  line-height: 1.6 !important;
  margin: 0 !important;
  max-width: 540px;
}

.sub-refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  background: rgba(255, 255, 255, 0.95);
  color: #6366f1;
  font-weight: 700;
  border: none;
  border-radius: 12px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.18s ease;
  box-shadow: 0 6px 20px -8px rgba(0, 0, 0, 0.3);
}

.sub-refresh-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 10px 28px -10px rgba(0, 0, 0, 0.35);
}

.sub-refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.animate-spin { animation: spin 1.2s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.sub-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.sub-card {
  padding: 18px;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sub-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 800;
  color: #475569;
}

.sub-count {
  margin-left: auto;
  background: #f1f5f9;
  color: #64748b;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.sub-form {
  display: flex;
  gap: 8px;
  align-items: stretch;
}

/* 自定义表单控件：避免依赖 daisyUI 主题在不同上下文下错位 */
.sub-select,
.sub-input {
  height: 36px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 0 12px;
  font-size: 13px;
  color: #1e293b;
  background: #fff;
  outline: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
  box-sizing: border-box;
}

.sub-select { min-width: 92px; }
.sub-input { flex: 1; min-width: 0; }

.sub-select:focus,
.sub-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.18);
}

.sub-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 36px;
  padding: 0 14px;
  border: none;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  cursor: pointer;
  transition: all 0.18s ease;
  white-space: nowrap;
}

.sub-btn iconify-icon { font-size: 16px; }

.sub-btn--primary {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  box-shadow: 0 6px 16px -8px rgba(99, 102, 241, 0.6);
}

.sub-btn--primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 10px 22px -10px rgba(99, 102, 241, 0.7);
}

.sub-btn--danger {
  background: linear-gradient(135deg, #ef4444, #f97316);
  box-shadow: 0 6px 16px -8px rgba(239, 68, 68, 0.55);
}

.sub-btn--danger:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 10px 22px -10px rgba(239, 68, 68, 0.65);
}

.sub-btn:disabled {
  background: #e2e8f0;
  color: #94a3b8;
  box-shadow: none;
  cursor: not-allowed;
}

.sub-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  list-style: none;
  padding: 0;
  max-height: 220px;
  overflow-y: auto;
}

.sub-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(139, 92, 246, 0.08));
  border-radius: 12px;
  font-size: 13px;
}

.sub-chip--block {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.08), rgba(248, 113, 113, 0.08));
}

.sub-chip-kind {
  font-size: 11px;
  font-weight: 700;
  color: #6366f1;
  background: #eef2ff;
  padding: 2px 6px;
  border-radius: 6px;
}

.sub-chip--block .sub-chip-kind {
  color: #ef4444;
  background: #fee2e2;
}

.sub-chip-value {
  flex: 1;
  color: #1e293b;
  font-weight: 600;
}

.sub-empty,
.sub-empty-inline {
  color: #94a3b8;
  font-size: 12px;
  text-align: center;
  padding: 12px;
}

.sub-empty-inline {
  padding: 0;
  text-align: left;
}

.sub-profile-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sub-profile-label {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.sub-tag-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.sub-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: #f1f5f9;
  color: #475569;
  border-radius: 999px;
  font-size: 12px;
}

.sub-tag strong {
  color: #6366f1;
  font-weight: 800;
}

.sub-tag--accent {
  background: #fef3c7;
  color: #92400e;
}

.sub-tag--accent strong {
  color: #f59e0b;
}

.sub-recommend {
  padding: 18px;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 20px;
}

.sub-empty--big {
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 32px;
  display: flex;
}

.sub-rec-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  list-style: none;
  padding: 0;
  margin-top: 12px;
}

.sub-rec-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border: 1px solid rgba(226, 232, 240, 0.7);
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.sub-rec-item:hover {
  border-color: #6366f1;
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.12);
  transform: translateY(-1px);
}

.sub-rec-rank {
  font-size: 18px;
  font-weight: 800;
  color: #6366f1;
  min-width: 28px;
}

.sub-rec-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sub-rec-body strong {
  font-size: 14px;
  color: #0f172a;
  font-weight: 700;
}

.sub-rec-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.sub-rec-score {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  background: linear-gradient(135deg, #f97316, #f59e0b);
  color: #fff;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.sub-rec-reason {
  padding: 2px 8px;
  background: #eef2ff;
  color: #6366f1;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.sub-rec-platform {
  color: #94a3b8;
  font-size: 11px;
}

.sub-rec-arrow {
  color: #cbd5e1;
  font-size: 20px;
}

/* === 分页器与兜底开关 === */
.sub-fallback-toggle {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #64748b;
  cursor: pointer;
  user-select: none;
}
.sub-fallback-toggle input { accent-color: #6366f1; }

.sub-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 14px 0 6px;
}
.sub-pager-info {
  font-size: 12px;
  color: #64748b;
  font-family: "Fira Code", monospace;
}
.sub-pager .sub-btn[disabled] {
  opacity: 0.4;
  cursor: not-allowed;
}

.sub-rec-item--fallback {
  background: rgba(148, 163, 184, 0.06);
}
.sub-rec-score--fb {
  background: #f1f5f9 !important;
  color: #64748b !important;
}

@media (max-width: 1100px) {
  .sub-grid {
    grid-template-columns: 1fr;
  }
}
</style>

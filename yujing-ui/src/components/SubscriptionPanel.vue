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
          <span class="sub-count"><NumberFlow :value="subscriptions.length" /></span>
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
          <span class="sub-count"><NumberFlow :value="blocklist.length" /></span>
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
          <span class="sub-count">浏览 <NumberFlow :value="Number(profile.history_count) || 0" /> 次</span>
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
        <div class="sub-profile-block" v-if="(profile.inferred_tags || []).length">
          <div class="sub-profile-label">
            <iconify-icon icon="mdi:vector-link" />
            兴趣标签
            <span class="sub-profile-hint">（embedding 邻近召回 · 30 min 缓存）</span>
          </div>
          <div class="sub-tag-cloud">
            <span
              v-for="t in profile.inferred_tags"
              :key="'inf-' + t.tag"
              class="sub-tag sub-tag--inferred"
              :title="`embedding 邻近 cosine 累加分 ${t.score}`"
            >
              {{ t.tag }}
              <strong>{{ t.score }}</strong>
            </span>
          </div>
        </div>
        <div class="sub-profile-block" v-else>
          <div class="sub-profile-label">兴趣标签</div>
          <span class="sub-empty-inline">浏览满 5 篇即可生成 embedding 推断兴趣</span>
        </div>
      </section>
    </div>

    <!-- 推荐结果 -->
    <section class="sub-recommend card bg-base-100">
      <div class="sub-card-head">
        <iconify-icon icon="mdi:sparkles" />
        <span>为你推荐 · 实时打分</span>
        <span class="sub-count">
          候选 <NumberFlow :value="Number(candidatesCount) || 0" /> · 命中 <NumberFlow :value="Number(matchedCount) || 0" /> · 共 <NumberFlow :value="Number(totalCount) || 0" /> 条
        </span>
        <span v-if="dismissedIds.size > 0" class="sub-dismiss-info">
          已忽略 <NumberFlow :value="dismissedIds.size" /> 条
          <button type="button" class="sub-dismiss-restore" @click="restoreDismissed">撤销</button>
        </span>
        <button
          type="button"
          class="sub-weights-toggle"
          :class="{ 'is-open': weightsOpen }"
          @click="weightsOpen = !weightsOpen"
          title="调整推荐打分权重"
        >
          <iconify-icon icon="mdi:tune-vertical" />
          <span>权重</span>
        </button>
        <label class="sub-fallback-toggle" :title="'未命中订阅时，按热度返回 TOP 兜底'">
          <input type="checkbox" v-model="useFallback" @change="reloadRecommend(0)" />
          <span>无命中时按热度兜底</span>
        </label>
      </div>

      <transition name="slide-fade">
        <div v-if="weightsOpen" class="sub-weights-panel">
          <div class="sub-weights-grid">
            <div class="sub-weight-row">
              <span class="sub-weight-label">订阅词命中</span>
              <input type="range" min="0" max="10" step="0.5" v-model.number="weights.keyword" @input="onWeightsChange" />
              <span class="sub-weight-value">{{ weights.keyword.toFixed(1) }}</span>
            </div>
            <div class="sub-weight-row">
              <span class="sub-weight-label">订阅源命中</span>
              <input type="range" min="0" max="10" step="0.5" v-model.number="weights.source" @input="onWeightsChange" />
              <span class="sub-weight-value">{{ weights.source.toFixed(1) }}</span>
            </div>
            <div class="sub-weight-row">
              <span class="sub-weight-label">画像·常看源</span>
              <input type="range" min="0" max="10" step="0.5" v-model.number="weights.profile_source" @input="onWeightsChange" />
              <span class="sub-weight-value">{{ weights.profile_source.toFixed(1) }}</span>
            </div>
            <div class="sub-weight-row">
              <span class="sub-weight-label">画像·兴趣词</span>
              <input type="range" min="0" max="10" step="0.5" v-model.number="weights.profile_tag" @input="onWeightsChange" />
              <span class="sub-weight-value">{{ weights.profile_tag.toFixed(1) }}</span>
            </div>
          </div>
          <div class="sub-weights-foot">
            <span class="sub-weights-hint">调整后自动重新打分（已持久化到本地）</span>
            <button type="button" class="sub-weights-reset" @click="resetWeights">恢复默认</button>
          </div>
        </div>
      </transition>

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
          v-for="(item, idx) in visibleRecommendations"
          :key="item.id"
          class="sub-rec-item"
          :class="{ 'sub-rec-item--fallback': item._fallback, 'sub-rec-item--read': readIds.has(item.id) }"
          @click="handleOpen(item)"
        >
          <span class="sub-rec-rank">{{ offset + idx + 1 }}</span>
          <div class="sub-rec-body">
            <strong>
              {{ item.title }}
              <span v-if="readIds.has(item.id)" class="sub-rec-readtag">已读</span>
            </strong>
            <div class="sub-rec-meta">
              <span class="sub-rec-score" v-if="!item._fallback">
                <iconify-icon icon="mdi:fire" />匹配 <NumberFlow :value="Number(item._recommend_score) || 0" />
              </span>
              <span class="sub-rec-score sub-rec-score--fb" v-else>
                <iconify-icon icon="mdi:thermometer" />热度兜底
              </span>
              <!-- A1: 结构化推荐解释徽章 4 色（订阅词/订阅源/画像源/画像兴趣/语义/兜底） -->
              <template v-if="(item._recommend_chips || []).length">
                <span
                  v-for="(c, ci) in item._recommend_chips"
                  :key="'chip-' + ci"
                  class="sub-rec-chip"
                  :class="`sub-rec-chip--${c.type}`"
                  :title="chipTooltip(c)"
                >
                  <iconify-icon :icon="CHIP_ICON[c.type] || 'mdi:tag'" />
                  <span class="sub-rec-chip-label">{{ CHIP_LABEL[c.type] || c.type }}</span>
                  <span class="sub-rec-chip-text">{{ c.text }}</span>
                  <strong v-if="c.score != null">{{ c.score }}</strong>
                  <strong v-else-if="c.weight != null">+{{ c.weight }}</strong>
                </span>
              </template>
              <!-- 旧字段兜底（后端没返回 chips 时） -->
              <template v-else>
                <span v-for="r in item._recommend_reasons || []" :key="r" class="sub-rec-reason">{{ r }}</span>
              </template>
              <span class="sub-rec-platform">{{ SOURCE_LABEL[item.primary_source_id] || item.primary_source_id }} · {{ item.article_count }} 条</span>
            </div>
          </div>
          <button
            type="button"
            class="sub-rec-dismiss"
            title="忽略该推荐"
            @click.stop="dismissItem(item.id)"
          >
            <iconify-icon icon="mdi:close" />
          </button>
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
import { computed, onMounted, ref, watch } from "vue";
import NumberFlow from "@number-flow/vue";
import { buildApiUrl } from "../config/api";

const emit = defineEmits(["open-event"]);

/* A2: 已读 / 已忽略持久化键 */
const LS_READ_KEY = "yujing.sub.readIds";
const LS_DISMISS_KEY = "yujing.sub.dismissedIds";
const loadIdSet = (key) => {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return new Set();
    const arr = JSON.parse(raw);
    return new Set(Array.isArray(arr) ? arr : []);
  } catch {
    return new Set();
  }
};
const saveIdSet = (key, set) => {
  try {
    localStorage.setItem(key, JSON.stringify(Array.from(set)));
  } catch {
    /* 全局静默：陰私/限额场景可能写入失败 */
  }
};
const readIds = ref(loadIdSet(LS_READ_KEY));
const dismissedIds = ref(loadIdSet(LS_DISMISS_KEY));
watch(readIds, (v) => saveIdSet(LS_READ_KEY, v), { deep: true });
watch(dismissedIds, (v) => saveIdSet(LS_DISMISS_KEY, v), { deep: true });

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

/* A1：推荐解释徽章配置 */
const CHIP_LABEL = {
  keyword: "订阅词",
  sub_source: "订阅源",
  profile_source: "常看",
  profile_tag: "兴趣",
  semantic: "语义",
  fallback: "兜底",
};
const CHIP_ICON = {
  keyword: "mdi:bookmark-check",
  sub_source: "mdi:rss",
  profile_source: "mdi:account-eye",
  profile_tag: "mdi:account-heart",
  semantic: "mdi:vector-link",
  fallback: "mdi:thermometer",
};
function chipTooltip(c) {
  const src = SOURCE_LABEL[c.text] || c.text;
  switch (c.type) {
    case "keyword":
      return `订阅关键词「${c.text}」字面命中标题（+${c.weight}）`;
    case "sub_source":
      return `订阅数据源「${src}」命中（+${c.weight}）`;
    case "profile_source":
      return `你常看「${src}」（+${c.weight}）`;
    case "profile_tag":
      return `画像兴趣命中：${c.text}（+${c.weight}）`;
    case "semantic":
      return `订阅词「${c.text}」与标题语义余弦 ${c.score}（+${c.weight}）`;
    case "fallback":
      return `没有任何命中，按热度兜底返回`;
    default:
      return c.text;
  }
}

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

/* A1: 打分权重（可调 + 持久化） */
const LS_WEIGHTS_KEY = "yujing.sub.weights";
const DEFAULT_WEIGHTS = { keyword: 5.0, source: 3.0, profile_source: 3.0, profile_tag: 3.0 };
const loadWeights = () => {
  try {
    const raw = localStorage.getItem(LS_WEIGHTS_KEY);
    if (!raw) return { ...DEFAULT_WEIGHTS };
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_WEIGHTS, ...parsed };
  } catch {
    return { ...DEFAULT_WEIGHTS };
  }
};
const weights = ref(loadWeights());
const weightsOpen = ref(false);
let weightsDebounce = null;
const onWeightsChange = () => {
  try {
    localStorage.setItem(LS_WEIGHTS_KEY, JSON.stringify(weights.value));
  } catch {
    /* 静默 */
  }
  if (weightsDebounce) clearTimeout(weightsDebounce);
  weightsDebounce = setTimeout(() => reloadRecommend(0), 220);
};
const resetWeights = () => {
  weights.value = { ...DEFAULT_WEIGHTS };
  onWeightsChange();
};
const currentPage = computed(() => Math.floor(offset.value / pageSize.value) + 1);
const totalPages = computed(() => Math.max(1, Math.ceil(totalCount.value / pageSize.value)));

/* A2: 过滤已忽略条目；已读仍然展示但连同样式决定 */
const visibleRecommendations = computed(() =>
  recommendations.value.filter((it) => !dismissedIds.value.has(it.id))
);

const handleOpen = (item) => {
  if (!readIds.value.has(item.id)) {
    const next = new Set(readIds.value);
    next.add(item.id);
    readIds.value = next;
  }
  emit("open-event", item);
};

const dismissItem = (id) => {
  const next = new Set(dismissedIds.value);
  next.add(id);
  dismissedIds.value = next;
};

const restoreDismissed = () => {
  dismissedIds.value = new Set();
};

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
    w_keyword: String(weights.value.keyword),
    w_source: String(weights.value.source),
    w_profile_source: String(weights.value.profile_source),
    w_profile_tag: String(weights.value.profile_tag),
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
  border-radius: 4px;
  overflow: hidden;
  /* editorial: 去黑，改为报纸头版”纸白 + 顽赤陶红 kicker + 衰宋体标题“
     仅保留上下 1px hairline 作为“版面划颗” */
  background: var(--color-surface);
  box-shadow: none;
  padding: 28px 28px 26px;
  color: var(--color-text);
  min-height: 132px;
  flex-shrink: 0;
  border: 1px solid var(--color-border);
  border-top: 3px solid var(--color-accent);
}

.sub-hero-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  /* 右上软赤陶红阳光，作为暑调点缀 */
  background:
    radial-gradient(circle at 92% 12%, rgba(180, 83, 9, 0.06), transparent 55%);
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
  padding: 3px 10px;
  /* editorial: 赤陶红 chip走报纸 kicker */
  background: rgba(180, 83, 9, 0.10);
  color: var(--color-accent);
  font-size: 11px;
  font-weight: 800;
  border-radius: 3px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.sub-title {
  display: block !important;
  font-size: 30px !important;
  font-weight: 800 !important;
  margin: 14px 0 6px !important;
  letter-spacing: 0.02em;
  /* editorial: 衰宋体作报纸头版标题 */
  font-family: var(--font-display, "Noto Serif SC", serif);
  color: var(--color-text) !important;
  line-height: 1.2 !important;
  text-shadow: none;
}

.sub-sub {
  display: block !important;
  font-size: 13px !important;
  color: var(--color-text-2) !important;
  line-height: 1.6 !important;
  margin: 0 !important;
  max-width: 540px;
}

.sub-refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 18px;
  /* editorial: 近墨石板实色作“主动作”，仅此一黑 */
  background: var(--color-brand);
  color: #FAFAF7;
  font-weight: 700;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.18s ease;
  box-shadow: 0 1px 2px rgba(28, 25, 23, 0.08);
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
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(180, 83, 9, 0.10);
}

.sub-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 36px;
  padding: 0 14px;
  border: none;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  cursor: pointer;
  transition: all 0.18s ease;
  white-space: nowrap;
}

.sub-btn iconify-icon { font-size: 16px; }

.sub-btn--primary {
  /* editorial: 去紫蓝渐变，近墨石板实色 */
  background: var(--color-brand);
  box-shadow: none;
}

.sub-btn--primary:hover:not(:disabled) {
  background: #1E293B;
  transform: translateY(-1px);
}

.sub-btn--danger {
  /* editorial: 警示仍需红，一色深红 token critical */
  background: #B91C1C;
  box-shadow: none;
}

.sub-btn--danger:hover:not(:disabled) {
  background: #991B1B;
  transform: translateY(-1px);
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
  /* editorial: 去紫调渐变，米白底 + 赤陶红 kind chip */
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 13px;
}

.sub-chip--block {
  background: rgba(185, 28, 28, 0.05);
  border-color: rgba(185, 28, 28, 0.18);
}

.sub-chip-kind {
  font-size: 10px;
  font-weight: 800;
  color: var(--color-accent);
  background: rgba(180, 83, 9, 0.10);
  padding: 2px 6px;
  border-radius: 3px;
  letter-spacing: 0.06em;
}

.sub-chip--block .sub-chip-kind {
  color: #B91C1C;
  background: rgba(185, 28, 28, 0.10);
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
  /* editorial: 赤陶红重音 */
  color: var(--color-accent);
  font-weight: 800;
}

.sub-tag--accent {
  background: rgba(217, 119, 6, 0.08);
  color: #92400E;
}

.sub-tag--accent strong {
  color: #D97706;
}

/* V2：embedding 推断 tag，与 literal tag 视觉区分 */
.sub-tag--inferred {
  /* editorial: 青青渐变 → 衰宋金色虚线边，用文本差异表达“推断而非命中” */
  background: var(--color-surface-2);
  color: var(--color-text-2);
  border: 1px dashed var(--color-accent);
  cursor: help;
}

.sub-tag--inferred strong {
  color: var(--color-accent);
}

.sub-profile-hint {
  font-size: 10px;
  color: #cbd5e1;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  margin-left: 4px;
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
  /* editorial: 赤陶红边 + 暑色阳光 shadow */
  border-color: var(--color-accent);
  box-shadow: 0 4px 14px rgba(180, 83, 9, 0.10);
  transform: translateY(-1px);
}

.sub-rec-rank {
  font-size: 18px;
  font-weight: 800;
  /* editorial: 衰宋体赤陶红排名 */
  font-family: var(--font-display, "Noto Serif SC", serif);
  color: var(--color-accent);
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
  padding: 2px 9px;
  /* editorial: 去全黑坍，改为“米白底 + 赤陶红 hairline + 衰宋体赤陶红打分”的分数戳记感 */
  background: var(--color-surface);
  color: var(--color-accent);
  border: 1px solid var(--color-accent);
  border-radius: 3px;
  font-size: 11px;
  font-weight: 800;
  font-family: var(--font-display, "Noto Serif SC", serif);
  letter-spacing: 0.04em;
}

.sub-rec-reason {
  padding: 2px 8px;
  background: var(--color-surface-2);
  color: var(--color-accent);
  border: 1px solid var(--color-border);
  border-radius: 3px;
  font-size: 11px;
  font-weight: 700;
}

/* A1: 结构化推荐解释徽章 6 色，统一基础样式 */
.sub-rec-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px 2px 5px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid transparent;
  cursor: help;
  line-height: 1.4;
}
.sub-rec-chip > iconify-icon { font-size: 12px; }
.sub-rec-chip-label {
  font-weight: 700;
  opacity: 0.85;
  margin-right: 2px;
}
.sub-rec-chip-text { font-weight: 600; }
.sub-rec-chip strong {
  margin-left: 4px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
/* 6 色配色：每色对应一种打分维度 —— editorial: 统一米白底，仅用文字色 + 左边色区分语义 */
.sub-rec-chip--keyword {
  background: var(--color-surface-2); color: #1E40AF; border-color: rgba(30, 64, 175, 0.30);
}
.sub-rec-chip--sub_source {
  background: var(--color-surface-2); color: var(--color-brand); border-color: rgba(15, 23, 42, 0.30);
}
.sub-rec-chip--profile_source {
  background: var(--color-surface-2); color: #92400E; border-color: rgba(180, 83, 9, 0.30);
}
.sub-rec-chip--profile_tag {
  background: var(--color-surface-2); color: #B91C1C; border-color: rgba(185, 28, 28, 0.25);
}
.sub-rec-chip--semantic {
  background: var(--color-surface-2);
  color: #15803D; border-color: rgba(21, 128, 61, 0.30);
}
.sub-rec-chip--fallback {
  background: var(--color-surface-2); color: var(--color-text-3); border-color: var(--color-border);
}

/* S1.2：语义命中徽章（与字面命中区分，使用暑绿/赤陶红调）*/
.sub-rec-semantic {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 8px;
  background: var(--color-surface-2);
  color: var(--color-accent);
  border-radius: 3px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid var(--color-accent);
  cursor: help;
}
.sub-rec-semantic > iconify-icon {
  font-size: 12px;
}

.sub-rec-platform {
  color: #94a3b8;
  font-size: 11px;
}

/* 卡片右侧 → 箭头：原 #cbd5e1 在白底几乎不可见，加深到 slate-400 */
.sub-rec-arrow {
  color: #64748b;
  font-size: 20px;
  opacity: 0.85;
}
.sub-rec-item:hover .sub-rec-arrow { color: var(--color-accent); opacity: 1; }

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
.sub-fallback-toggle input { accent-color: var(--color-accent); }

.sub-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 14px 0 6px;
}
.sub-pager-info {
  font-size: 13px;
  color: #334155;
  font-weight: 700;
  font-family: "Fira Code", monospace;
}
/* 翻页按钮：editorial 近墨石板实色 */
.sub-pager .sub-btn {
  background: var(--color-brand);
  color: #FAFAF7;
  box-shadow: none;
}
.sub-pager .sub-btn:hover:not([disabled]) {
  background: #1E293B;
  transform: translateY(-1px);
}
.sub-pager .sub-btn[disabled] {
  background: var(--color-surface-2);
  color: var(--color-text-3);
  box-shadow: none;
  opacity: 1;
  cursor: not-allowed;
}

.sub-rec-item--fallback {
  background: rgba(148, 163, 184, 0.06);
}
.sub-rec-score--fb {
  background: #f1f5f9 !important;
  color: #64748b !important;
}

/* A2: 已读 / 已忽略相关样式 */
.sub-rec-item--read {
  opacity: 0.62;
}
.sub-rec-item--read .sub-rec-body strong {
  color: #64748b;
  font-weight: 600;
}
.sub-rec-readtag {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  background: #e2e8f0;
  color: #64748b;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 700;
  vertical-align: middle;
}
.sub-rec-dismiss {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #64748b;
  cursor: pointer;
  transition: all 0.18s ease;
}
.sub-rec-dismiss:hover {
  border-color: #fca5a5;
  background: #fef2f2;
  color: #ef4444;
}
.sub-dismiss-info {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: 8px;
  padding: 2px 10px;
  background: #fff7ed;
  color: #c2410c;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}
.sub-dismiss-restore {
  background: transparent;
  border: 1px solid #fdba74;
  color: #c2410c;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 10px;
  cursor: pointer;
  transition: all 0.18s ease;
}
.sub-dismiss-restore:hover {
  background: #fed7aa;
}

/* A1: 权重调节面板 — editorial 赤陶红 chip */
.sub-weights-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
  padding: 3px 10px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-accent);
  border-radius: 3px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.18s ease;
}
.sub-weights-toggle:hover {
  background: rgba(180, 83, 9, 0.06);
  border-color: var(--color-accent);
}
.sub-weights-toggle.is-open {
  background: var(--color-accent);
  color: #FAFAF7;
  border-color: var(--color-accent);
}
.sub-weights-panel {
  margin: 12px 0 4px;
  padding: 14px 18px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-accent);
  border-radius: 4px;
}
.sub-weights-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px 24px;
}
.sub-weight-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.sub-weight-label {
  flex-shrink: 0;
  width: 80px;
  font-size: 12px;
  font-weight: 700;
  color: #475569;
}
.sub-weight-row input[type="range"] {
  flex: 1;
  accent-color: var(--color-accent);
  cursor: pointer;
}
.sub-weight-value {
  flex-shrink: 0;
  min-width: 32px;
  text-align: right;
  font-family: "Fira Code", monospace;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-accent);
}
.sub-weights-foot {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}
.sub-weights-hint {
  font-size: 11px;
  color: #64748b;
}
.sub-weights-reset {
  padding: 3px 12px;
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-accent);
  border-radius: 3px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.18s ease;
}
.sub-weights-reset:hover {
  background: rgba(180, 83, 9, 0.06);
  border-color: var(--color-accent);
}
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.22s ease;
}
.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

@media (max-width: 1100px) {
  .sub-grid {
    grid-template-columns: 1fr;
  }
}
</style>

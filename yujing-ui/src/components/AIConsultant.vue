<template>
  <section class="ai-shell">
    <header class="workspace-header">
      <div class="workspace-kicker badge badge-primary badge-outline">
        <span class="live-dot"></span>
        <span>AI 助手</span>
      </div>
      <label class="agent-mode-toggle" :class="{ active: agentMode }">
        <iconify-icon :icon="agentMode ? 'ri:brain-fill' : 'ri:brain-line'"></iconify-icon>
        <span>智能体模式</span>
        <input type="checkbox" v-model="agentMode" :disabled="isActivePending" />
        <span class="toggle-track"><span class="toggle-knob"></span></span>
      </label>
      <div class="workspace-meta badge badge-ghost">
        <span>{{ sessions.length }} 个会话</span>
        <span v-if="activeSession">{{ formatSessionMeta(activeSession) }}</span>
      </div>
    </header>

    <div class="workspace-layout">
      <aside class="session-rail">
        <div class="rail-block rail-head card bg-base-100">
          <div class="rail-copy">
            <span class="rail-label">会话</span>
            <strong>本地历史</strong>
          </div>
          <button class="session-create btn btn-primary btn-sm" type="button" @click="createSession(true)">
            <iconify-icon icon="mdi:plus"></iconify-icon>
            新建
          </button>
        </div>

        <div class="session-list rail-block menu bg-base-100" aria-label="会话列表">
          <article
            v-for="session in sessions"
            :key="session.id"
            :class="['session-card', { active: activeSessionId === session.id }]"
          >
            <button class="session-main btn btn-ghost" type="button" @click="setActiveSession(session.id)">
              <span class="session-title">{{ session.title }}</span>
              <span class="session-meta">{{ formatSessionMeta(session) }}</span>
            </button>

            <button
              v-if="sessions.length > 1"
              class="session-delete btn btn-ghost btn-xs btn-circle"
              type="button"
              aria-label="删除会话"
              @click.stop="deleteSession(session.id)"
            >
              <iconify-icon icon="mdi:close" class="text-[12px]"></iconify-icon>
            </button>
          </article>
        </div>
      </aside>

      <div ref="chatScroll" class="workspace-body">
        <div v-if="!agentMode" class="quick-actions">
          <button class="quick-action-btn" type="button" @click="runPreset('生成今日日报')" :disabled="isActivePending">
            <iconify-icon icon="ri:file-text-line"></iconify-icon>
            今日日报
          </button>
          <button class="quick-action-btn" type="button" @click="runPreset('生成本周周报')" :disabled="isActivePending">
            <iconify-icon icon="ri:calendar-line"></iconify-icon>
            本周周报
          </button>
          <button class="quick-action-btn" type="button" @click="runPreset('当前有什么值得关注的热点')" :disabled="isActivePending">
            <iconify-icon icon="ri:fire-line"></iconify-icon>
            热点速览
          </button>
          <button class="quick-action-btn" type="button" @click="runPreset('统计分析：各平台热搜数量对比、今日最热事件TOP5、舆情情绪分布')" :disabled="isActivePending">
            <iconify-icon icon="ri:bar-chart-2-line"></iconify-icon>
            统计报告
          </button>
        </div>

        <div v-else class="agent-preset-strip">
          <div class="agent-preset-head">
            <iconify-icon icon="ri:sparkling-2-fill"></iconify-icon>
            <span><strong>Tool-Calling Agent</strong> 已启用 · 自主规划 2-4 步工具调用，给出带引用的结构化结论</span>
          </div>
          <div class="agent-preset-grid">
            <button
              v-for="(p, idx) in AGENT_PRESETS"
              :key="idx"
              class="agent-preset-card"
              type="button"
              :disabled="isActivePending"
              @click="runPreset(p.query)"
            >
              <div class="agent-preset-icon"><iconify-icon :icon="p.icon"></iconify-icon></div>
              <div class="agent-preset-body">
                <strong>{{ p.title }}</strong>
                <span>{{ p.hint }}</span>
              </div>
            </button>
          </div>
        </div>

        <div
          v-if="briefStatus !== 'loading'"
          class="brief-banner"
          :class="`brief-banner--${briefStatus}`"
        >
          <div class="brief-banner-icon">
            <iconify-icon
              :icon="briefStatus === 'ready' ? 'ri:sun-line' : 'ri:loader-4-line'"
              :class="briefStatus !== 'ready' ? 'brief-icon-spin' : ''"
            />
          </div>
          <div class="brief-banner-text">
            <strong v-if="briefStatus === 'ready'">今日舆情早报已就绪</strong>
            <strong v-else>今日早报正在生成…</strong>
            <span>{{ briefDate || todayLabel }}</span>
          </div>
          <template v-if="briefStatus === 'ready'">
            <button class="brief-banner-btn" type="button" :disabled="isActivePending" @click="openBrief">
              查看早报
            </button>
            <button class="brief-banner-pdf" type="button" @click="exportBriefPdf" title="导出PDF">
              <iconify-icon icon="ri:file-pdf-2-line" />
            </button>
          </template>
        </div>

        <div v-if="alerts.length" class="alerts-panel">
          <div class="alerts-header">
            <iconify-icon icon="ri:alarm-warning-line" />
            <span>舆情异动告警</span>
            <span class="alerts-count">{{ alerts.length }}</span>
            <button class="alerts-clear" type="button" @click="clearAlerts">全部忽略</button>
          </div>
          <div
            v-for="alert in alerts"
            :key="alert.id"
            :class="['alert-card', `alert-${alert.level}`]"
          >
            <div class="alert-indicator"></div>
            <div class="alert-body">
              <strong>{{ alert.title }}</strong>
              <span class="alert-meta">{{ alert.article_count }} 篇报道 · {{ alert.platform_count }} 个平台 · {{ alert.time }}</span>
            </div>
            <button class="alert-action" type="button" @click="openAlertDetail(alert)">查看</button>
            <button class="alert-dismiss" type="button" @click="dismissAlert(alert.id)">
              <iconify-icon icon="mdi:close" />
            </button>
          </div>
        </div>

        <section v-if="showWelcome" class="welcome-stage">
          <div class="welcome-copy">
            <span class="welcome-label badge badge-outline badge-primary">AI 助手</span>
            <h2>检索、分析、生成报告。</h2>
            <p>输入“日报”生成每日简报，“对比 X 和 Y”做舆情对比，或直接搜索平台、话题、事件。</p>
          </div>

          <div class="prompt-strip">
            <button
              v-for="(preset, idx) in presets"
              :key="preset"
              class="prompt-chip btn btn-ghost"
              type="button"
              @click="runPreset(preset)"
            >
              <iconify-icon :icon="['ri:file-text-line', 'ri:scales-3-line', 'ri:fire-line', 'ri:weibo-line'][idx] || 'ri:chat-smile-2-line'"></iconify-icon>
              {{ preset }}
            </button>
          </div>
        </section>

        <div
          v-for="(msg, index) in history"
          :key="`${activeSessionId}-${index}`"
          :class="['message-row', msg.role]"
          :data-msg-index="index"
        >
          <article class="message-block card" :class="msg.role === 'assistant' ? 'bg-base-100' : 'bg-primary text-primary-content'">
            <div class="message-meta badge badge-ghost" v-if="msg.role === 'assistant' && !msg.agent_events">AI 回复</div>
            <div class="message-meta agent-meta-chip" v-else-if="msg.role === 'assistant' && msg.agent_events">
              <iconify-icon icon="ri:sparkling-2-fill"></iconify-icon>
              <span>LLM 智能体</span>
              <span v-if="msg.agent_running" class="agent-meta-elapsed">进行中…</span>
            </div>

            <!-- 对比仪表盘：当消息携带 compare_metrics 时，在正文之上渲染双列对比卡 -->
            <CompareDashboard
              v-if="msg.role === 'assistant' && msg.compare_metrics"
              :metrics="msg.compare_metrics"
              @open-article="$emit('open-item', $event)"
            />

            <!-- 智能体模式：展示调用链 + final answer（带 event#N/article#N 引用高亮） -->
            <template v-if="msg.role === 'assistant' && msg.agent_events">
              <AgentTrace :events="msg.agent_events" :isRunning="!!msg.agent_running" />
              <div v-if="msg.agent_final" class="agent-final-card">
                <div class="agent-final-head">
                  <iconify-icon icon="ri:sparkling-2-fill"></iconify-icon>
                  <strong>最终研判</strong>
                </div>
                <div class="agent-final-body" v-html="formatAgentFinal(msg.agent_final)"></div>
              </div>
              <div v-if="msg.agent_error" class="agent-final-abort">
                <iconify-icon icon="ri:alert-line"></iconify-icon>
                <span>{{ msg.agent_error }}</span>
              </div>
            </template>

            <div v-else class="msg-text" v-html="formatMessage(msg.content)"></div>

            <div v-if="msg.role === 'assistant' && msg.content && !isActivePending" class="msg-actions">
              <button class="msg-action-btn" type="button" @click="exportMessagePdf(msg, index)" title="导出PDF">
                <iconify-icon icon="ri:file-pdf-2-line" />
                <span>导出PDF</span>
              </button>
            </div>

            <div v-if="msg.role === 'assistant' && msg.summoned_items?.length" class="summon-area">
              <div class="summon-header">
                <span>关联情报</span>
                <span class="summon-count">{{ msg.summoned_items.length }} 条</span>
              </div>

              <div class="summon-list">
                <button
                  v-for="item in msg.summoned_items"
                  :key="item.id"
                  class="summon-item"
                  type="button"
                  @click="$emit('open-item', item)"
                >
                  <span class="summon-source">{{ getSourceName(item.source_id) }}</span>
                  <span class="summon-title">{{ item.title }}</span>
                  <iconify-icon icon="mdi:chevron-right" class="summon-arrow" />
                </button>
              </div>
            </div>

            <div v-if="msg.role === 'assistant' && msg.suggestions?.length" class="suggest-area">
              <div class="suggest-header">
                <iconify-icon icon="ri:lightbulb-line" />
                <span>继续追问</span>
              </div>
              <div class="suggest-list">
                <button
                  v-for="(sug, sIdx) in msg.suggestions"
                  :key="sIdx"
                  class="suggest-pill"
                  type="button"
                  :disabled="isActivePending"
                  @click="runPreset(sug)"
                >
                  <iconify-icon icon="ri:arrow-right-up-line" />
                  {{ sug }}
                </button>
              </div>
            </div>
          </article>
        </div>

        <div v-if="showLoadingIndicator" class="loading-row">
          <div class="loading-spinner loading loading-spinner loading-sm"></div>
          <div class="loading-copy">正在整理本地检索结果...</div>
        </div>
      </div>
    </div>

    <footer class="composer-shell">
      <div class="composer-container">
        <form class="composer-panel" @submit.prevent="sendMessage()">
          <!-- 移除了冗余的提示标签，保持界面纯净 -->
          
          <div class="composer-field">
            <textarea
              id="mcp-query"
              class="mcp-input-area"
              v-model="inputQuery"
              :disabled="isActivePending"
              :placeholder="agentMode ? '智能体将自主规划工具调用。例：最近两周伊朗相关的舆情消息中，哪些事件最热？情绪是什么倾向？' : '例如：我要微博的数据；最近争议最大的是哪个；继续分析刚才那条'"
              @keydown.enter.exact.prevent="sendMessage()"
            ></textarea>

            <button
              class="btn-send-capsule"
              type="submit"
              :disabled="!inputQuery.trim() || isActivePending"
            >
              <iconify-icon icon="ri:send-plane-2-fill"></iconify-icon>
              <span>发送</span>
            </button>
          </div>
        </form>
      </div>
    </footer>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import html2canvas from "html2canvas";
import AgentTrace from "./AgentTrace.vue";
import CompareDashboard from "./CompareDashboard.vue";

// 迁移说明：老 key 为 hongsou_mcp_sessions_v1。这里改为 yujing_ 前缀后首次加载
// 时会出现一次"空会话"列表，属于预期；旧历史如需保留，可手动 localStorage
// 改名。考虑到这是本地开发痕迹，不做运行时迁移以降低代码复杂度。
const STORAGE_KEY = "yujing_mcp_sessions_v1";
const API_URL = "http://localhost:8000/api/mcp/ask";
const AGENT_API_URL = "http://localhost:8000/api/agent/chat";

const props = defineProps({
  sourceRegistry: { type: Array, default: () => [] },
});

const emit = defineEmits(["open-item", "open-event"]);

const presets = ["生成今日日报", "最近争议最大的是哪个", "微博热搜概况", "统计分析各平台热度"];

// 智能体模式开关。开启后 sendMessage 走 /api/agent/chat（Tool-Calling Agent），
// 关闭则保持现有 /api/mcp/ask 流程。两条链路互不干扰。
const agentMode = ref(false);
const AGENT_PRESETS = [
  {
    title: "伊朗局势舆情",
    hint: "四步调用链：检索 → 详情 → 情绪 × 2",
    query: "最近两周伊朗相关的舆情消息中，哪些事件最热？情绪是什么倾向？",
    icon: "ri:global-line",
  },
  {
    title: "平台热度对比",
    hint: "list_hot_platforms + 跨平台比较",
    query: "微博、头条、知乎三个平台今天最热的事件分别是什么？讨论量有什么差异？",
    icon: "ri:bar-chart-2-line",
  },
  {
    title: "今日舆情早报",
    hint: "get_morning_brief 一步取今日要闻",
    query: "今天的舆情早报讲了什么？哪些事件值得关注？",
    icon: "ri:sun-line",
  },
];

const sessions = ref([]);
const activeSessionId = ref("");
const pendingSessionIds = ref([]);
const chatScroll = ref(null);
const inputQuery = ref("");
// 早报 banner 三态：
//   'loading'    前端首次轮询尚未返回（banner 不渲染，避免闪烁）
//   'ready'      后端 cache 命中今日早报，banner 显示"查看早报"+PDF
//   'generating' 后端仍在跑生成，banner 显示占位"生成中…"
// 合并掉了旧 briefDismissed 逻辑：用户要求"显示在上面"本来就意味着常驻。
const briefStatus = ref("loading");
const briefDate = ref("");
const todayLabel = new Date().toISOString().slice(0, 10);

let briefPollTimer = null;
const BRIEF_POLL_INTERVAL_MS = 3000; // 工业级轮询频率

// 工业级流程：POST trigger → 立即拿状态；后端若 started/running 就继续每 3s
// GET /status 轮询，直到 has_brief=true。全程不 hold 长连接，不 push 任何东西。
const triggerMorningBrief = async () => {
  try {
    const resp = await fetch("http://localhost:8000/api/ai/morning_brief/trigger", {
      method: "POST",
    });
    if (!resp.ok) return { status: "error" };
    return await resp.json(); // { status: 'ready' | 'running' | 'started' }
  } catch {
    return { status: "error" };
  }
};

const checkMorningBrief = async () => {
  try {
    const res = await fetch("http://localhost:8000/api/ai/morning_brief/status");
    const data = await res.json();
    if (data.has_brief) {
      briefStatus.value = "ready";
      briefDate.value = data.date;
      if (briefPollTimer) { clearInterval(briefPollTimer); briefPollTimer = null; }
    } else if (data.generating) {
      briefStatus.value = "generating";
    }
  } catch {
    // 网络抖动：保持当前态，不清空 banner
  }
};

const startBriefPolling = async () => {
  // 第一跳：用 trigger 把状态一次性搞清楚
  const first = await triggerMorningBrief();
  if (first.status === "ready") {
    briefStatus.value = "ready";
    briefDate.value = first.date || todayLabel;
    return;
  }
  // started / running / error → 进入 3s 轮询直至 ready
  briefStatus.value = "generating";
  if (briefPollTimer) clearInterval(briefPollTimer);
  briefPollTimer = setInterval(() => {
    if (briefStatus.value === "ready") {
      clearInterval(briefPollTimer);
      briefPollTimer = null;
      return;
    }
    checkMorningBrief();
  }, BRIEF_POLL_INTERVAL_MS);
};

// --- 舆情异动告警 ---
const alerts = ref([]);
let alertPollTimer = null;

const fetchAlerts = async () => {
  try {
    const res = await fetch("http://localhost:8000/api/ai/alerts");
    const data = await res.json();
    alerts.value = data.alerts || [];
  } catch {
    // 静默
  }
};

const dismissAlert = async (id) => {
  alerts.value = alerts.value.filter(a => a.id !== id);
  try { await fetch(`http://localhost:8000/api/ai/alerts/dismiss?alert_id=${id}`, { method: "POST" }); } catch {}
};

const clearAlerts = async () => {
  alerts.value = [];
  try { await fetch("http://localhost:8000/api/ai/alerts/clear", { method: "POST" }); } catch {}
};

const openAlertDetail = (alert) => {
  sendMessage(`分析舆情异动事件「${alert.title}」的详细情况`);
};

const startAlertPolling = () => {
  fetchAlerts();
  alertPollTimer = setInterval(fetchAlerts, 60000); // 每60秒
};

// 调 `/api/ai/morning_brief` SSE 端点，把 chunk 流式填入 session。
// 全局统一路径：openBrief 的 fallback 和 onMounted 的 fallback 都走这里，
// 避免出现"把'查看今日舆情早报'当用户问题塞给普通 chat"的提示词回显 bug。
const generateBriefViaSSE = async (session) => {
  if (!session) return;
  const assistantMsg = { role: "assistant", content: "", streaming: true };
  session.messages.push(assistantMsg);
  await nextTick();
  scrollToBottom();

  try {
    const resp = await fetch("http://localhost:8000/api/ai/morning_brief");
    if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sepIdx;
      while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, sepIdx).trim();
        buffer = buffer.slice(sepIdx + 2);
        if (!raw.startsWith("data:")) continue;
        try {
          const payload = JSON.parse(raw.slice(5).trim());
          if (payload.type === "content" && payload.text) {
            assistantMsg.content += payload.text;
            scrollToBottom(false); // 柔性滚动：允许用户上滑阅读
          }
        } catch {}
      }
    }
  } catch (err) {
    assistantMsg.content = assistantMsg.content || `早报生成失败: ${err?.message || err}`;
  } finally {
    assistantMsg.streaming = false;
    session.title = session.title || `舆情早报 ${new Date().toISOString().slice(0, 10)}`;
    saveSessions();
    await nextTick();
    scrollToBottom();
    // 流结束后后端已写缓存 → 刷新 banner 状态
    try { await checkMorningBrief(); } catch {}
  }
};

const openBrief = async () => {
  ensureSession();
  const session = activeSession.value;
  if (!session) return;

  // 1) 先读缓存（避免重复 LLM 请求）
  try {
    const res = await fetch("http://localhost:8000/api/ai/morning_brief/content");
    const data = await res.json();
    if (data.ok && data.content) {
      session.messages.push({ role: "user", content: "查看今日舆情早报" });
      session.messages.push({ role: "assistant", content: data.content });
      session.title = session.title || `舆情早报 ${data.date}`;
      saveSessions();
      await nextTick();
      scrollToBottom();
      return;
    }
  } catch {}

  // 2) 缓存为空 → 调用正确的早报生成 SSE 端点
  session.messages.push({ role: "user", content: "查看今日舆情早报" });
  await generateBriefViaSSE(session);
};

const exportBriefPdf = () => {
  window.open("http://localhost:8000/api/ai/morning_brief/pdf", "_blank");
};

// 对含可视化（如对比仪表盘）的消息，用 html2canvas 截取 DOM 并嵌入 PDF
// 关键坑：CompareDashboard 内部 .cmp-col / .cmp-metric / .cmp-chart-wrap
// 都是 animation-fill-mode: backwards 的渐入动画；html2canvas 克隆 DOM 后
// 会让动画"从头重放"，截图瞬间这些元素都处在 opacity:0 的初始帧 → 结果就是
// PDF 里只剩 header 能看见，中间全是白的。用 onclone 在克隆树上关掉所有动画
// 并强制"终态可见"即可彻底修好。
const captureDashboardImage = async (msgIndex) => {
  try {
    const row = document.querySelector(`[data-msg-index="${msgIndex}"]`);
    if (!row) return null;
    const target = row.querySelector(".compare-dashboard");
    if (!target) return null;
    // 确保 ECharts 这类异步渲染器已出完第一帧
    await nextTick();
    await new Promise((r) => requestAnimationFrame(() => r()));

    const canvas = await html2canvas(target, {
      backgroundColor: "#ffffff",
      scale: 2,
      useCORS: true,
      logging: false,
      // clone 时注入 CSS：禁用所有动画、过渡，强制终态显示
      onclone: (clonedDoc) => {
        const style = clonedDoc.createElement("style");
        style.textContent = `
          .compare-dashboard, .compare-dashboard * {
            animation: none !important;
            transition: none !important;
            opacity: 1 !important;
            transform: none !important;
          }
        `;
        clonedDoc.head.appendChild(style);
      },
    });
    return canvas.toDataURL("image/png");
  } catch (err) {
    console.warn("[PDF] dashboard 截图失败:", err);
    return null;
  }
};

const exportMessagePdf = async (msg, msgIndex) => {
  if (!msg.content && !msg.compare_metrics) return;
  try {
    const images = [];
    if (msg.compare_metrics) {
      const dataUrl = await captureDashboardImage(msgIndex);
      if (dataUrl) images.push(dataUrl);
    }
    const res = await fetch("http://localhost:8000/api/ai/export_pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: activeSession.value?.title || "AI 对话报告",
        content: msg.content || "",
        images: images.length ? images : undefined,
      }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (activeSession.value?.title || "report") + ".pdf";
    a.click();
    URL.revokeObjectURL(url);
  } catch {
    // 静默失败
  }
};

const activeSession = computed(
  () => sessions.value.find((session) => session.id === activeSessionId.value) || null
);
const history = computed(() => activeSession.value?.messages || []);
const isActivePending = computed(() => pendingSessionIds.value.includes(activeSessionId.value));
const showWelcome = computed(() => history.value.length === 0 && !isActivePending.value);
const showLoadingIndicator = computed(() => {
  if (!isActivePending.value) return false;
  const last = history.value[history.value.length - 1];
  return !(last?.role === "assistant" && last.content);
});

const generateSessionId = () => {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `session_${Date.now()}_${Math.random().toString(16).slice(2)}`;
};

const buildSession = (title = "新会话") => ({
  id: generateSessionId(),
  title,
  createdAt: Date.now(),
  updatedAt: Date.now(),
  messages: [],
  draft: "",
});

const getSessionById = (sessionId) =>
  sessions.value.find((session) => session.id === sessionId) || null;

const sortSessions = () => {
  sessions.value = [...sessions.value].sort((a, b) => b.updatedAt - a.updatedAt);
};

// saveSessions 是代码中的历史别名，实际实现走 persistSessions。
// 下方 watch(sessions, persistSessions, deep: true) 也会自动兜底持久化。
const saveSessions = () => persistSessions();

const persistSessions = () => {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      sessions: sessions.value,
      activeSessionId: activeSessionId.value,
    })
  );
};

const hydrateSessions = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed.sessions) || parsed.sessions.length === 0) return false;
    sessions.value = parsed.sessions.map((session) => ({
      ...session,
      messages: Array.isArray(session.messages) ? session.messages : [],
      draft: typeof session.draft === "string" ? session.draft : "",
    }));
    activeSessionId.value = parsed.activeSessionId || parsed.sessions[0].id;
    return true;
  } catch {
    return false;
  }
};

const ensureSession = () => {
  if (!sessions.value.length) {
    const session = buildSession();
    sessions.value = [session];
    activeSessionId.value = session.id;
    return session;
  }
  if (!activeSession.value) {
    activeSessionId.value = sessions.value[0].id;
  }
  return activeSession.value;
};

const updateSessionById = (sessionId, updater) => {
  const session = getSessionById(sessionId);
  if (!session) return;
  updater(session);
  session.updatedAt = Date.now();
  sortSessions();
};

const pushMessage = (sessionId, message) => {
  let insertedIndex = -1;
  updateSessionById(sessionId, (session) => {
    insertedIndex = session.messages.push(message) - 1;
    if (message.role === "user" && session.messages.filter((item) => item.role === "user").length === 1) {
      session.title = getSessionTitleFromQuery(message.content);
    }
  });
  return insertedIndex;
};

const patchMessage = (sessionId, index, patch) => {
  updateSessionById(sessionId, (session) => {
    if (!session.messages[index]) return;
    Object.assign(session.messages[index], patch);
  });
};

const getSessionTitleFromQuery = (query) => {
  const compact = query.replace(/\s+/g, " ").trim();
  if (!compact) return "新会话";
  return compact.length > 16 ? `${compact.slice(0, 16)}...` : compact;
};

const setSessionDraft = (sessionId, draft) => {
  const session = getSessionById(sessionId);
  if (!session) return;
  session.draft = draft;
};

// force=true: 用户主动操作（发送、切换会话）必须贴底
// force=false: 流式输出时仅在用户已贴近底部时才滚；否则保持当前位置，允许用户上翻阅读历史
const NEAR_BOTTOM_THRESHOLD = 120;
const scrollToBottom = async (force = true) => {
  await nextTick();
  const el = chatScroll.value;
  if (!el) return;
  if (!force) {
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distance > NEAR_BOTTOM_THRESHOLD) return; // 用户已上翻：不打断
  }
  el.scrollTop = el.scrollHeight;
};

const createSession = async (activate = true) => {
  const session = buildSession();
  sessions.value = [session, ...sessions.value];
  if (activate) {
    activeSessionId.value = session.id;
  }
  await nextTick();
  persistSessions();
};

const setActiveSession = async (sessionId) => {
  activeSessionId.value = sessionId;
  await scrollToBottom();
};

const deleteSession = async (sessionId) => {
  const nextSessions = sessions.value.filter((session) => session.id !== sessionId);
  sessions.value = nextSessions.length ? nextSessions : [buildSession()];
  if (!sessions.value.some((session) => session.id === activeSessionId.value)) {
    const firstNonEmpty = sessions.value.find((session) => session.messages?.length);
    activeSessionId.value = (firstNonEmpty || sessions.value[0]).id;
  }
  await nextTick();
  persistSessions();
};

const getSourceName = (id) => {
  const source = props.sourceRegistry.find((item) => item.id === id);
  return source ? source.name : "未知来源";
};

const formatMessage = (text) => {
  if (!text) return "";
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
};

const formatSessionMeta = (session) => {
  const count = session.messages?.length || 0;
  const time = new Date(session.updatedAt).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${count} 条 · ${time}`;
};

const syncItemState = (payload) => {
  if (!payload?.id) return;

  sessions.value.forEach((session) => {
    session.messages.forEach((message) => {
      if (!message.summoned_items?.length) return;
      const target = message.summoned_items.find((item) => item.id === payload.id);
      if (target) {
        Object.assign(target, payload);
        session.updatedAt = Date.now();
      }
    });
  });

  sortSessions();
};

defineExpose({ syncItemState });

// --- 智能体模式 · /api/agent/chat SSE 客户端 ---
// 独立于原 sendMessage 流程；把 SSE 事件累积到 assistant 消息的 agent_events，
// final 事件的 text 放到 agent_final（不污染 msg.content，保留 Markdown 渲染）。
const escapeHtmlForAgent = (raw) =>
  String(raw).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const formatAgentFinal = (text) => {
  if (!text) return "";
  const escaped = escapeHtmlForAgent(text);
  // 引用识别：中英文双支持
  //   英文：event#123 / article#456 （LLM system prompt 约定）
  //   中文：事件#123 / 文章#456 / 事件 # 123 / 事件＃123（DeepSeek 中文回答常见写法）
  // 归一化成 data-kind=event|article，让 click delegate 统一 emit。
  const withRefs = escaped.replace(
    /(event|article|事件|文章)\s*[#＃]\s*(\d+)/gi,
    (_m, kind, id) => {
      const lower = kind.toLowerCase();
      const dataKind = (lower === "event" || kind === "事件") ? "event" : "article";
      return `<a href="#" class="agent-ref" data-kind="${dataKind}" data-id="${id}">${kind}#${id}</a>`;
    },
  );
  const lines = withRefs.split("\n");
  const parts = [];
  let inList = false;
  for (const raw of lines) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    if (/^\s*####?\s+/.test(line)) {
      if (inList) { parts.push("</ul>"); inList = false; }
      parts.push(`<h4>${line.replace(/^\s*####?\s+/, "")}</h4>`);
    } else if (/^\s*###?\s+/.test(line)) {
      if (inList) { parts.push("</ul>"); inList = false; }
      parts.push(`<h3>${line.replace(/^\s*###?\s+/, "")}</h3>`);
    } else if (/^\s*[-•]\s+/.test(line)) {
      if (!inList) { parts.push("<ul>"); inList = true; }
      parts.push(`<li>${line.replace(/^\s*[-•]\s+/, "")}</li>`);
    } else if (!line.trim()) {
      if (inList) { parts.push("</ul>"); inList = false; }
      parts.push("");
    } else {
      if (inList) { parts.push("</ul>"); inList = false; }
      parts.push(`<p>${line}</p>`);
    }
  }
  if (inList) parts.push("</ul>");
  return parts.join("\n");
};

const sendAgentMessage = async (sessionId, outgoing) => {
  pushMessage(sessionId, { role: "user", content: outgoing });
  inputQuery.value = "";
  setSessionDraft(sessionId, "");
  pendingSessionIds.value = [...pendingSessionIds.value, sessionId];
  await scrollToBottom();

  const assistantIndex = pushMessage(sessionId, {
    role: "assistant",
    content: "",
    agent_events: [],
    agent_running: true,
    agent_final: "",
    agent_error: "",
  });

  try {
    const res = await fetch(AGENT_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ message: outgoing, stream: true }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    const accumulated = [];
    // final_delta 累积缓冲：后端把最终答案分片推送，前端边收边追加渲染（打字机效果）。
    let finalBuffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";
      for (const chunk of chunks) {
        const line = chunk.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        try {
          const ev = JSON.parse(line.slice(6));
          accumulated.push(ev);
          const patch = { agent_events: [...accumulated] };
          if (ev.type === "final_delta") {
            finalBuffer += ev.text || "";
            patch.agent_final = finalBuffer;
          }
          if (ev.type === "final") {
            // final 事件兜底：把 finalBuffer 校准为完整文本（防 delta 丢包）
            finalBuffer = ev.text || finalBuffer;
            patch.agent_final = finalBuffer;
          }
          if (ev.type === "error") {
            // loop 内部终止信号（max_steps / too_many_errors）已由 AgentTrace 的
            // trace-terminated 卡片显示，气泡级 agent_error 只保留"硬错误"（LLM 调用失败等无 terminated_reason）。
            if (!ev.terminated_reason) {
              patch.agent_error = ev.message || "智能体出错";
            }
          }
          if (ev.type === "done") patch.agent_running = false;
          patchMessage(sessionId, assistantIndex, patch);
        } catch (err) {
          console.error("[agent] SSE parse error", err, chunk);
        }
      }
      await scrollToBottom(false);
    }
  } catch (error) {
    patchMessage(sessionId, assistantIndex, {
      agent_running: false,
      agent_error: `请求失败：${error.message || error}`,
    });
  } finally {
    patchMessage(sessionId, assistantIndex, { agent_running: false });
    pendingSessionIds.value = pendingSessionIds.value.filter((id) => id !== sessionId);
    await scrollToBottom();
  }
};

// 委托点击事件：捕获 v-html 内部 `.agent-ref` 链接，emit 给父组件打开对应 modal
const handleAgentRefClick = (evt) => {
  const el = evt.target;
  if (!el || el.tagName !== "A" || !el.classList.contains("agent-ref")) return;
  evt.preventDefault();
  const kind = el.dataset.kind;
  const id = parseInt(el.dataset.id || "0", 10);
  if (!id) return;
  if (kind === "event") emit("open-event", { id });
  else if (kind === "article") emit("open-item", { id });
};

const sendMessage = async (presetText = null) => {
  ensureSession();
  const sessionId = activeSessionId.value;
  const outgoing = (presetText ?? inputQuery.value).trim();
  if (!outgoing || pendingSessionIds.value.includes(sessionId)) return;

  // 分支：智能体模式走独立链路
  if (agentMode.value) {
    return sendAgentMessage(sessionId, outgoing);
  }

  const session = getSessionById(sessionId);
  const contextHistory = (session?.messages || []).map((msg) => ({
    role: msg.role,
    content: msg.content,
  }));

  pushMessage(sessionId, { role: "user", content: outgoing });
  inputQuery.value = "";
  setSessionDraft(sessionId, "");
  pendingSessionIds.value = [...pendingSessionIds.value, sessionId];
  await scrollToBottom();

  let assistantIndex = -1;
  let contentBuffer = "";
  let itemsBuffer = [];

  const ensureAssistantMessage = () => {
    if (assistantIndex >= 0) return assistantIndex;
    assistantIndex = pushMessage(sessionId, {
      role: "assistant",
      content: contentBuffer,
      summoned_items: itemsBuffer,
    });
    return assistantIndex;
  };

  try {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ query: outgoing, history: contextHistory }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body?.getReader();
    if (!reader) throw new Error("stream unavailable");

    const decoder = new TextDecoder();
    let streamBuffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      streamBuffer += decoder.decode(value, { stream: true });
      const chunks = streamBuffer.split("\n\n");
      streamBuffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const line = chunk
          .split("\n")
          .find((entry) => entry.startsWith("data: "));
        if (!line) continue;

        const payload = JSON.parse(line.slice(6));
        if (payload.type === "content_start") {
          contentBuffer = "";
          itemsBuffer = [];
          continue;
        }

        if (payload.type === "content") {
          contentBuffer += payload.text || "";
          const index = ensureAssistantMessage();
          patchMessage(sessionId, index, { content: contentBuffer, summoned_items: itemsBuffer });
        }

        if (payload.type === "summoned_items") {
          itemsBuffer = payload.items || [];
          const index = ensureAssistantMessage();
          patchMessage(sessionId, index, { content: contentBuffer, summoned_items: itemsBuffer });
        }

        if (payload.type === "compare_metrics") {
          // 挂载对比仪表盘数据到当前消息，前端用 CompareDashboard 渲染
          const index = ensureAssistantMessage();
          patchMessage(sessionId, index, { compare_metrics: { a: payload.a, b: payload.b } });
        }

        if (payload.type === "suggestions") {
          const index = ensureAssistantMessage();
          patchMessage(sessionId, index, { suggestions: payload.items || [] });
        }
      }

      await scrollToBottom(false); // 流式期间柔性滚动
    }

    if (assistantIndex < 0) {
      pushMessage(sessionId, {
        role: "assistant",
        content: "没有检索到可展示的结果。",
        summoned_items: [],
      });
    }
  } catch (error) {
    pushMessage(sessionId, {
      role: "assistant",
      content: "指挥链路中断，请检查后端运行状态后再试。",
      summoned_items: [],
    });
  } finally {
    pendingSessionIds.value = pendingSessionIds.value.filter((id) => id !== sessionId);
    await scrollToBottom();
  }
};

const runPreset = async (text) => {
  await sendMessage(text);
};

const startCompare = () => {
  inputQuery.value = "对比 ";
  nextTick(() => {
    const textarea = document.getElementById("mcp-query");
    if (textarea) textarea.focus();
  });
};

watch(
  sessions,
  () => {
    persistSessions();
  },
  { deep: true }
);

watch(activeSessionId, async (sessionId) => {
  inputQuery.value = getSessionById(sessionId)?.draft || "";
  await scrollToBottom();
});

watch(inputQuery, (value) => {
  if (!activeSessionId.value) return;
  setSessionDraft(activeSessionId.value, value);
});

onMounted(async () => {
  const restored = hydrateSessions();
  if (!restored) {
    await createSession(true);
  } else {
    ensureSession();
    if (!activeSession.value?.messages?.length) {
      const firstNonEmpty = sessions.value.find((session) => session.messages?.length);
      if (firstNonEmpty) {
        activeSessionId.value = firstNonEmpty.id;
      }
    }
  }

  inputQuery.value = activeSession.value?.draft || "";
  await scrollToBottom();

  // 早报不自动灌到会话里：只启动轮询 → 出 banner → 用户点击"查看早报"才加载。
  // 这正是用户"显示在上面但不自动发送"的要求。
  startBriefPolling();
  startAlertPolling();
  document.addEventListener("click", handleAgentRefClick);
});

onUnmounted(() => {
  if (briefPollTimer) { clearInterval(briefPollTimer); briefPollTimer = null; }
  if (alertPollTimer) { clearInterval(alertPollTimer); alertPollTimer = null; }
  document.removeEventListener("click", handleAgentRefClick);
});
</script>

<style scoped>
.ai-shell {
  height: 100%; display: grid; grid-template-rows: auto 1fr auto;
  background: #f1f4f9; color: #1e293b;
  font-family: 'Inter', system-ui, sans-serif;
}
.workspace-header {
  padding: 14px 40px; background: rgba(255, 255, 255, 0.9); backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  display: flex; justify-content: space-between; align-items: center;
  z-index: 10;
}
.workspace-kicker { font-weight: 800; letter-spacing: 0.5px; border-radius: 6px; }
.workspace-layout { min-height: 0; display: grid; grid-template-columns: 280px 1fr; gap: 0; }

.session-rail {
  background: #f8fafc;
  border-right: 1px solid rgba(0, 0, 0, 0.05);
  padding: 32px 24px; display: flex; flex-direction: column; gap: 24px;
}
.rail-head {
  padding: 20px; background: #fff; border: 1px solid rgba(59, 130, 246, 0.12);
  border-radius: 16px; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.04);
  display: flex; flex-direction: column; gap: 16px;
}
.rail-label { font-size: 11px; font-weight: 950; color: #3b82f6; text-transform: uppercase; letter-spacing: 1.5px; opacity: 0.8; }
.rail-copy strong { display: block; font-size: 18px; color: #0f172a; font-weight: 900; }

.session-create {
  width: 100%; height: 44px; background: #0f172a; color: #fff; border-radius: 12px;
  font-weight: 800; display: flex; align-items: center; justify-content: center; gap: 8px;
  transition: 0.2s cubic-bezier(0.4, 0, 0.2, 1); border: none; font-size: 14px;
}
.session-create:hover { background: #2563eb; transform: translateY(-2px); box-shadow: 0 10px 20px rgba(37, 99, 235, 0.2); }

.session-list { display: flex; flex-direction: column; gap: 6px; overflow-y: auto; padding-right: 4px; }
.session-card {
  position: relative; border-radius: 12px; border: 1px solid transparent; transition: 0.2s;
  background: transparent; cursor: pointer;
}
.session-card:hover { background: rgba(59, 130, 246, 0.04); }
.session-card.active {
  background: #fff; border-color: rgba(59, 130, 246, 0.2);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
}
.session-card.active::before {
  content: ""; position: absolute; left: 0; top: 12px; bottom: 12px; width: 3px;
  background: #3b82f6; border-radius: 0 4px 4px 0;
}
.session-card:hover .session-delete { opacity: 1; transform: scale(1); }

.session-main { 
  flex: 1; text-align: left; padding: 12px 16px; display: flex; flex-direction: column; gap: 2px;
  background: transparent; border: none; width: 100%;
}
.session-title { font-size: 14px; font-weight: 700; color: #334155; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 20px; }
.session-meta { font-size: 11px; color: #94a3b8; font-weight: 500; }

.session-delete {
  position: absolute; right: 8px; top: 8px; 
  opacity: 0; transform: scale(0.85); transition: 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  background: rgba(241, 245, 249, 0.8) !important; color: #64748b;
  z-index: 10; border: none; min-height: 24px; width: 24px !important; height: 24px !important;
}
.session-delete:hover { background: #fee2e2 !important; color: #ef4444 !important; }

.workspace-body {
  min-height: 0; overflow-y: auto; padding: 40px; display: flex; flex-direction: column; gap: 24px;
  background: #ffffff;
}
.welcome-stage { max-width: 720px; margin-top: 40px; }
.welcome-copy h2 { font-size: 40px; font-weight: 900; color: #0f172a; line-height: 1.1; margin: 12px 0 20px; letter-spacing: -1px; }
.welcome-copy p { font-size: 16px; color: #64748b; line-height: 1.6; }

.prompt-strip { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 32px; }
.prompt-chip {
  background: #f8fbff; border: 1px solid rgba(59, 130, 246, 0.1); border-radius: 8px;
  padding: 8px 16px; font-size: 13px; font-weight: 700; color: #3b82f6;
  display: flex; align-items: center; gap: 8px; transition: 0.2s;
}
.prompt-chip:hover { background: #2563eb; color: #fff; transform: translateY(-2px); box-shadow: 0 8px 20px rgba(37, 99, 235, 0.15); }

.message-row { display: flex; width: 100%; margin-bottom: 24px; }
.user { justify-content: flex-end; }
.assistant { justify-content: flex-start; }

.message-block {
  padding: 24px; border-radius: 16px; position: relative; max-width: 85%;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02);
}
.user .message-block {
  background: #0f172a; color: #fff; border-bottom-right-radius: 4px;
}
.assistant .message-block {
  background: #fff; border: 1px solid rgba(0, 0, 0, 0.05); color: #334155;
  border-bottom-left-radius: 4px;
}
.msg-text { font-size: 15px; line-height: 1.75; text-align: left; }

.composer-shell {
  padding: 32px 40px; background: rgba(255, 255, 255, 0.8); backdrop-filter: blur(20px);
  border-top: 1px solid rgba(0, 0, 0, 0.04);
}
.composer-panel {
  background: #fff; border: 1px solid rgba(59, 130, 246, 0.08); border-radius: 24px;
  padding: 28px; box-shadow: 0 30px 60px rgba(15, 23, 42, 0.1);
  width: 100%; margin: 0 auto;
}
.composer-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.composer-label { display: flex; align-items: center; gap: 8px; color: #2563eb; font-size: 11px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px; }
.composer-meta { font-size: 11px; color: #94a3b8; }

.composer-field { display: flex; gap: 16px; align-items: flex-end; }
.mcp-input-area {
  flex: 1; background: #f8fafc; border: 1px solid rgba(226, 232, 240, 0.8); border-radius: 12px;
  padding: 16px; font-size: 15px; resize: none; min-height: 56px; outline: none; border: 1px solid transparent;
  transition: all 0.2s;
}
.mcp-input-area:focus { border-color: #3b82f6; background: #fff; box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.05); }

.btn-send-capsule {
  background: #2563eb; color: #fff; border: none; border-radius: 12px; height: 56px; padding: 0 24px;
  display: flex; align-items: center; gap: 10px; font-weight: 800; cursor: pointer; transition: 0.2s;
}
.btn-send-capsule:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(37, 99, 235, 0.2); }

.summon-area { margin-top: 24px; border-top: 1px solid rgba(0,0,0,0.04); padding-top: 16px; }
.summon-header { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #64748b; font-weight: 700; margin-bottom: 8px; }
.summon-count { font-size: 11px; color: #94a3b8; font-weight: 600; }
.summon-list { display: flex; flex-direction: column; gap: 2px; }
.summon-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 10px 12px; border-radius: 8px; border: none; background: transparent;
  cursor: pointer; transition: background 0.15s; text-align: left;
}
.summon-item:hover { background: rgba(59, 130, 246, 0.05); }
.summon-source {
  flex-shrink: 0; font-size: 10px; font-weight: 800; color: #3b82f6;
  background: rgba(59, 130, 246, 0.08); padding: 2px 8px; border-radius: 4px;
  white-space: nowrap;
}
.summon-title { flex: 1; font-size: 13px; font-weight: 600; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.summon-arrow { flex-shrink: 0; font-size: 16px; color: #cbd5e1; }
.quick-actions {
  display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px;
}
.quick-action-btn {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 20px; border-radius: 12px;
  font-size: 14px; font-weight: 800; cursor: pointer;
  border: 1.5px solid rgba(59, 130, 246, 0.15);
  background: linear-gradient(135deg, #eff6ff 0%, #f8fbff 100%);
  color: #2563eb; transition: all 0.2s;
}
.quick-action-btn:hover:not(:disabled) {
  background: #2563eb; color: #fff;
  transform: translateY(-2px); box-shadow: 0 8px 20px rgba(37, 99, 235, 0.2);
}
.quick-action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.quick-action-compare {
  border-color: rgba(168, 85, 247, 0.15);
  background: linear-gradient(135deg, #faf5ff 0%, #f8fbff 100%);
  color: #7c3aed;
}
.quick-action-compare:hover:not(:disabled) {
  background: #7c3aed; color: #fff;
  box-shadow: 0 8px 20px rgba(124, 58, 237, 0.2);
}

.brief-banner {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 20px; border-radius: 14px;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  border: 1.5px solid rgba(245, 158, 11, 0.2);
  animation: briefSlideIn 0.3s ease-out;
}
.brief-banner-icon {
  font-size: 22px; color: #f59e0b;
  display: flex; align-items: center;
}
.brief-banner-text {
  flex: 1; display: flex; flex-direction: column; gap: 2px;
}
.brief-banner-text strong { font-size: 14px; font-weight: 800; color: #92400e; }
.brief-banner-text span { font-size: 12px; color: #b45309; }
.brief-banner-btn {
  padding: 8px 20px; border-radius: 10px; border: none;
  background: #f59e0b; color: #fff; font-weight: 800; font-size: 13px;
  cursor: pointer; transition: 0.2s; white-space: nowrap;
}
.brief-banner-btn:hover:not(:disabled) {
  background: #d97706; transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(217, 119, 6, 0.3);
}
.brief-banner-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.brief-banner-pdf {
  width: 36px; height: 36px; border-radius: 8px; border: 1.5px solid rgba(220, 38, 38, 0.2);
  background: rgba(255,255,255,0.7); color: #dc2626; font-size: 16px;
  display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.2s;
}
.brief-banner-pdf:hover { background: #dc2626; color: #fff; border-color: #dc2626; }
.brief-banner-close {
  background: none; border: none; cursor: pointer;
  color: #92400e; opacity: 0.5; font-size: 16px;
  display: flex; align-items: center; transition: 0.2s;
}
.brief-banner-close:hover { opacity: 1; }
/* 生成中态：降饱和色调，避免占"已就绪"的视觉强调 */
.brief-banner--generating {
  background: linear-gradient(135deg, #e0f2fe 0%, #bae6fd 100%);
  border-color: rgba(14, 165, 233, 0.25);
}
.brief-banner--generating .brief-banner-icon { color: #0284c7; }
.brief-banner--generating .brief-banner-text strong { color: #0c4a6e; }
.brief-banner--generating .brief-banner-text span { color: #075985; }
.brief-icon-spin { animation: briefSpin 1.1s linear infinite; }
@keyframes briefSpin {
  to { transform: rotate(360deg); }
}
@keyframes briefSlideIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.msg-actions {
  display: flex; gap: 8px; margin-top: 10px; padding-top: 8px;
  border-top: 1px solid rgba(0,0,0,0.04);
}
.msg-action-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.08);
  background: transparent; color: #64748b; font-size: 12px; font-weight: 600;
  cursor: pointer; transition: 0.2s;
}
.msg-action-btn:hover {
  background: #dc2626; color: #fff; border-color: #dc2626;
}

.suggest-area {
  margin-top: 16px; border-top: 1px solid rgba(0,0,0,0.04); padding-top: 12px;
}
.suggest-header {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 700; color: #f59e0b; margin-bottom: 10px;
}
.suggest-list { display: flex; flex-wrap: wrap; gap: 8px; }
.suggest-pill {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: 20px;
  font-size: 13px; font-weight: 700; cursor: pointer;
  border: 1.5px solid rgba(245, 158, 11, 0.2);
  background: linear-gradient(135deg, #fffbeb 0%, #fefce8 100%);
  color: #b45309; transition: all 0.2s;
}
.suggest-pill:hover:not(:disabled) {
  background: #f59e0b; color: #fff; border-color: #f59e0b;
  transform: translateY(-1px); box-shadow: 0 4px 12px rgba(245, 158, 11, 0.25);
}
.suggest-pill:disabled { opacity: 0.5; cursor: not-allowed; }

/* 告警面板 */
.alerts-panel { margin: 0 40px 12px; animation: briefSlideIn 0.3s ease; }
.alerts-header {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 800; color: #dc2626; margin-bottom: 8px;
}
.alerts-count {
  background: #dc2626; color: #fff; font-size: 11px; font-weight: 800;
  padding: 1px 8px; border-radius: 99px; min-width: 20px; text-align: center;
}
.alerts-clear {
  margin-left: auto; background: none; border: 1px solid rgba(220,38,38,0.2);
  color: #dc2626; font-size: 11px; font-weight: 700; padding: 4px 12px;
  border-radius: 8px; cursor: pointer; transition: 0.2s;
}
.alerts-clear:hover { background: #dc2626; color: #fff; }
.alert-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; border-radius: 12px; margin-bottom: 6px;
  background: #fff; border: 1px solid rgba(0,0,0,0.06);
  transition: 0.2s; animation: briefSlideIn 0.25s ease;
}
.alert-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.06); }
.alert-indicator { width: 4px; height: 28px; border-radius: 4px; flex-shrink: 0; }
.alert-critical .alert-indicator { background: #dc2626; }
.alert-warning .alert-indicator { background: #f59e0b; }
.alert-info .alert-indicator { background: #3b82f6; }
.alert-body { flex: 1; min-width: 0; }
.alert-body strong { display: block; font-size: 13px; font-weight: 700; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.alert-meta { font-size: 11px; color: #94a3b8; }
.alert-action {
  padding: 5px 14px; border-radius: 8px; border: 1px solid rgba(59,130,246,0.2);
  background: transparent; color: #3b82f6; font-size: 12px; font-weight: 700;
  cursor: pointer; transition: 0.2s; white-space: nowrap;
}
.alert-action:hover { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.alert-dismiss {
  background: none; border: none; color: #94a3b8; cursor: pointer;
  font-size: 14px; display: flex; align-items: center; transition: 0.2s;
}
.alert-dismiss:hover { color: #ef4444; }

@keyframes spin { to { transform: rotate(360deg); } }

/* =========================================================================
 * 智能体模式 · 顶部 toggle + 预设条 + 消息气泡中的 AgentTrace/final-card
 * ========================================================================= */
.agent-mode-toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.3rem 0.75rem 0.3rem 0.6rem;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(99, 102, 241, 0.25);
  color: #4338ca;
  font-size: 0.82rem;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s, border-color 0.15s;
  margin-left: auto;
  margin-right: 0.75rem;
}
.agent-mode-toggle:hover { background: rgba(99, 102, 241, 0.14); }
.agent-mode-toggle.active {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.18), rgba(168, 85, 247, 0.14));
  border-color: rgba(99, 102, 241, 0.55);
  color: #4c1d95;
}
.agent-mode-toggle input[type="checkbox"] { display: none; }
.agent-mode-toggle .toggle-track {
  position: relative;
  width: 30px;
  height: 16px;
  background: rgba(99, 102, 241, 0.25);
  border-radius: 999px;
  transition: background 0.15s;
}
.agent-mode-toggle.active .toggle-track { background: #6366f1; }
.agent-mode-toggle .toggle-knob {
  position: absolute;
  left: 2px;
  top: 2px;
  width: 12px;
  height: 12px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}
.agent-mode-toggle.active .toggle-knob { transform: translateX(14px); }

.agent-preset-strip {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  padding: 0.85rem 1rem;
  background: linear-gradient(135deg, #ede9fe, #e0e7ff);
  border: 1px solid rgba(99, 102, 241, 0.28);
  border-radius: 12px;
  margin-bottom: 0.5rem;
  /* sticky 顶部：滚动聊天历史时，智能体预设条始终可见。
     用完全不透明背景，避免滚动时与下方 brief-banner 透叠产生视觉"遮挡"错觉。 */
  position: sticky;
  top: 0;
  z-index: 5;
  box-shadow: 0 4px 12px -4px rgba(99, 102, 241, 0.28), 0 1px 0 rgba(99, 102, 241, 0.12);
}
.agent-preset-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #4c1d95;
  font-size: 0.85rem;
}
.agent-preset-head iconify-icon { color: #7c3aed; font-size: 1.05rem; }
.agent-preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.65rem;
}
.agent-preset-card {
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 0.6rem;
  padding: 0.65rem 0.8rem;
  background: #fff;
  border: 1px solid rgba(99, 102, 241, 0.25);
  border-radius: 10px;
  color: #1e293b;
  text-align: left;
  cursor: pointer;
  transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
}
.agent-preset-card:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: #6366f1;
  box-shadow: 0 4px 14px -6px rgba(99, 102, 241, 0.4);
}
.agent-preset-card:disabled { opacity: 0.55; cursor: not-allowed; }
.agent-preset-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  border-radius: 8px;
  font-size: 1.15rem;
}
.agent-preset-body { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
.agent-preset-body strong { font-size: 0.9rem; color: #1e293b; }
.agent-preset-body span { font-size: 0.72rem; color: #64748b; }

.agent-meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.12rem 0.6rem;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.14), rgba(168, 85, 247, 0.1));
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 999px;
  color: #4c1d95;
  font-size: 0.72rem;
  align-self: flex-start;
}
.agent-meta-elapsed {
  color: #6366f1;
  font-size: 0.7rem;
  padding-left: 0.3rem;
  border-left: 1px solid rgba(99, 102, 241, 0.3);
  margin-left: 0.2rem;
}

.agent-final-card {
  margin-top: 0.65rem;
  padding: 0.85rem 1rem;
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.06), rgba(59, 130, 246, 0.05));
  border: 1px solid rgba(34, 197, 94, 0.3);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.agent-final-head {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: #15803d;
  font-size: 0.82rem;
}
.agent-final-body {
  color: #1e293b;
  font-size: 0.92rem;
  line-height: 1.65;
}
.agent-final-body :deep(h3) { margin: 0.55rem 0 0.25rem; font-size: 1.02rem; }
.agent-final-body :deep(h4) { margin: 0.45rem 0 0.2rem; font-size: 0.94rem; }
.agent-final-body :deep(p)  { margin: 0.2rem 0; }
.agent-final-body :deep(ul) { margin: 0.3rem 0 0.3rem 1.2rem; padding: 0; }
.agent-final-body :deep(li) { list-style: disc; margin: 0.12rem 0; }
.agent-final-body :deep(strong) { color: #111827; }
.agent-final-body :deep(.agent-ref) {
  color: #2563eb;
  text-decoration: none;
  font-family: "JetBrains Mono", ui-monospace, monospace;
  font-size: 0.86em;
  padding: 0.05rem 0.35rem;
  background: rgba(37, 99, 235, 0.1);
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.agent-final-body :deep(.agent-ref:hover) {
  background: rgba(37, 99, 235, 0.22);
  text-decoration: underline;
}

.agent-final-abort {
  margin-top: 0.6rem;
  padding: 0.55rem 0.8rem;
  background: rgba(220, 38, 38, 0.08);
  border: 1px solid rgba(220, 38, 38, 0.3);
  border-radius: 8px;
  color: #b91c1c;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
</style>

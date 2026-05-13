<template>
  <section class="ai-shell">
    <header class="workspace-header">
      <div class="header-left">
        <div class="workspace-kicker badge badge-primary badge-outline">
          <span class="live-dot"></span>
          <span>AI 助手</span>
        </div>
        <div class="agent-badge">
          <iconify-icon icon="ri:brain-fill"></iconify-icon>
          <span>Tool-Calling Agent</span>
        </div>
      </div>
      <div class="workspace-meta">
        <span>{{ sessions.length }}个会话</span>
        <span v-if="activeSession" class="meta-sep">·</span>
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
        <!-- 预设卡片：新对话时显示，有历史时折叠为紧凑条 -->
        <div class="agent-preset-strip" :class="{ 'agent-preset-compact': history.length > 0 }">
          <div class="agent-preset-head">
            <iconify-icon icon="ri:sparkling-2-fill"></iconify-icon>
            <span><strong>Tool-Calling Agent</strong> 自主规划工具调用，给出带引用的结构化结论</span>
          </div>
          <div v-if="!history.length" class="agent-preset-grid">
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

        <!-- 早报横幅：两种模式都显示 -->
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
          <div class="alerts-header" :class="`alerts-header-${alertsTopLevel}`">
            <iconify-icon :icon="alertLevelIcon(alertsTopLevel)" />
            <span>舆情推送中心</span>
            <span class="alerts-count">{{ alerts.length }}</span>
            <button class="alerts-clear" type="button" @click="clearAlerts">全部忽略</button>
          </div>
          <div
            v-for="alert in sortedAlerts"
            :key="alert.id"
            :class="['alert-card', `alert-${alert.level}`]"
          >
            <div class="alert-icon">
              <iconify-icon :icon="alertLevelIcon(alert.level)" />
            </div>
            <div class="alert-body">
              <strong>{{ alert.title }}</strong>
              <span class="alert-meta">
                {{ alert.article_count }} 篇报道 · {{ alert.platform_count }} 个平台 ·
                <span class="alert-time" :title="alert.time">{{ formatRelativeTime(alert.time) }}</span>
              </span>
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
            <p>用自然语言提问即可：智能体会自动调用 10 余个数据工具完成跨平台检索、热度对比、情绪研判与早报生成。</p>
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
            <!-- 用户消息 -->
            <div v-if="msg.role === 'user'" class="msg-user-text">{{ msg.content }}</div>
            <div class="message-meta agent-meta-chip" v-if="msg.role === 'assistant'">
              <iconify-icon icon="ri:sparkling-2-fill"></iconify-icon>
              <span>Agent 研判</span>
              <span v-if="msg.agent_running" class="agent-meta-elapsed">进行中…</span>
            </div>

            <!-- 智能体调用链 + 对比仪表盘 + final answer
                 顺序：AgentTrace (思考链) → CompareDashboard (tool 结果可视化) → 最终研判 (LLM 文字)
                 之前把 CompareDashboard 放最前会让用户感到"结果突然弹出、下方 trace 像断层"，
                 现在改为 trace 后、final 前，形成"思考 → 数据 → 结论"的自然阅读流。 -->
            <template v-if="msg.role === 'assistant' && msg.agent_events">
              <AgentTrace
                :events="msg.agent_events"
                :isRunning="!!msg.agent_running"
                :collapsed="!!msg.trace_collapsed"
                @toggle-collapse="toggleTraceCollapse(index)"
              />
              <CompareDashboard
                v-if="msg.compare_metrics"
                :metrics="msg.compare_metrics"
                @open-article="$emit('open-item', $event)"
              />
              <div
                v-if="msg.agent_final"
                class="agent-final-card"
                :ref="el => bindFinalRef(el, index)"
              >
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

            <!-- 兜底：旧消息可能无 agent_events -->
            <div v-else-if="msg.role === 'assistant' && msg.content" class="msg-text" v-html="formatMessage(msg.content)"></div>

            <!-- 导出 PDF：agent_final 或 content 非空均可导出 -->
            <div v-if="msg.role === 'assistant' && (msg.agent_final || msg.content) && !msg.agent_running && !isActivePending" class="msg-actions">
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
              :placeholder="'智能体将自主规划工具调用。例：最近两周伊朗相关的舆情消息中，哪些事件最热？情绪是什么倾向？'"
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

    <!-- 早报独立弹窗：与对话流解耦，不再 echo prompt -->
    <BriefModal
      :visible="briefModalVisible"
      :content="briefModalContent"
      :brief-date="briefModalDate"
      :loading="briefModalLoading"
      @close="briefModalVisible = false"
      @regenerate="regenerateBrief"
      @ask-followup="askFollowupFromBrief"
    />
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { marked } from "marked";
import { renderMarkdown } from "@/utils/markdown";
import { buildApiUrl } from "../config/api";
import html2canvas from "html2canvas";
import AgentTrace from "./AgentTrace.vue";
import CompareDashboard from "./CompareDashboard.vue";
import BriefModal from "./BriefModal.vue";

// 迁移说明：老 key 为 hongsou_mcp_sessions_v1。这里改为 yujing_ 前缀后首次加载
// 时会出现一次"空会话"列表，属于预期；旧历史如需保留，可手动 localStorage
// 改名。考虑到这是本地开发痕迹，不做运行时迁移以降低代码复杂度。
const STORAGE_KEY = "yujing_mcp_sessions_v1";
const API_URL = buildApiUrl("/api/mcp/ask");
const AGENT_API_URL = buildApiUrl("/api/agent/chat");

const props = defineProps({
  sourceRegistry: { type: Array, default: () => [] },
});

const emit = defineEmits(["open-item", "open-event"]);

const presets = ["生成今日日报", "最近争议最大的是哪个", "微博热搜概况", "统计分析各平台热度"];

// 智能体模式开关。开启后 sendMessage 走 /api/agent/chat（Tool-Calling Agent），
// 关闭则保持现有 /api/mcp/ask 流程。两条链路互不干扰。
const agentMode = ref(true);  // 始终启用智能体模式
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

// 早报独立弹窗状态（替代原来"早报塞进对话流"做法）
const briefModalVisible = ref(false);
const briefModalContent = ref("");
const briefModalDate = ref("");
const briefModalLoading = ref(false);
const briefDate = ref("");
const todayLabel = new Date().toISOString().slice(0, 10);

let briefPollTimer = null;
const BRIEF_POLL_INTERVAL_MS = 3000; // 工业级轮询频率

// 工业级流程：POST trigger → 立即拿状态；后端若 started/running 就继续每 3s
// GET /status 轮询，直到 has_brief=true。全程不 hold 长连接，不 push 任何东西。
const triggerMorningBrief = async () => {
  try {
    const resp = await fetch(buildApiUrl("/api/ai/morning_brief/trigger"), {
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
    const res = await fetch(buildApiUrl("/api/ai/morning_brief/status"));
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

// --- 舆情推送中心 ---
const alerts = ref([]);
let alertPollTimer = null;

const fetchAlerts = async () => {
  try {
    const res = await fetch(buildApiUrl("/api/ai/alerts"));
    const data = await res.json();
    alerts.value = data.alerts || [];
  } catch {
    // 静默
  }
};

const dismissAlert = async (id) => {
  alerts.value = alerts.value.filter(a => a.id !== id);
  try { await fetch(buildApiUrl(`/api/ai/alerts/dismiss?alert_id=${id}`), { method: "POST" }); } catch {}
};

const clearAlerts = async () => {
  alerts.value = [];
  try { await fetch(buildApiUrl("/api/ai/alerts/clear"), { method: "POST" }); } catch {}
};

// U2: 告警分级 icon + 排序（critical → warning → info, 同级按 article_count desc）
const ALERT_LEVEL_ORDER = { critical: 0, warning: 1, info: 2 };
const ALERT_LEVEL_ICON = {
  critical: "ri:alarm-warning-fill",
  warning: "ri:flashlight-fill",
  info: "ri:notification-3-line",
};
const alertLevelIcon = (level) => ALERT_LEVEL_ICON[level] || ALERT_LEVEL_ICON.info;
const sortedAlerts = computed(() => {
  const arr = [...alerts.value];
  arr.sort((a, b) => {
    const la = ALERT_LEVEL_ORDER[a.level] ?? 9;
    const lb = ALERT_LEVEL_ORDER[b.level] ?? 9;
    if (la !== lb) return la - lb;
    return (b.article_count || 0) - (a.article_count || 0);
  });
  return arr;
});
// 头部颜色取列表中最严重的等级
const alertsTopLevel = computed(() => {
  for (const lvl of ["critical", "warning", "info"]) {
    if (alerts.value.some((a) => a.level === lvl)) return lvl;
  }
  return "info";
});

// U3: 后端返回 "YYYY-MM-DD HH:MM"（北京时区无 TZ 标记，直接 new Date 在 Chrome 视为本地时区）
//   < 60s → 刚刚 / < 60min → N 分钟前 / < 24h → N 小时前 / < 7d → N 天前 / 否则 MM-DD HH:MM
const formatRelativeTime = (timeStr) => {
  if (!timeStr) return "";
  // 兼容 "YYYY-MM-DD HH:MM" 与 ISO 字符串
  const normalized = typeof timeStr === "string" ? timeStr.replace(" ", "T") : timeStr;
  const t = new Date(normalized).getTime();
  if (!Number.isFinite(t)) return timeStr;
  const diff = Date.now() - t;
  if (diff < 0) return timeStr; // 未来时间（如 mock 数据）回退绝对值
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "刚刚";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day} 天前`;
  return timeStr;
};

const openAlertDetail = (alert) => {
  // 推送 alert.id 与 event.id 一一对应（见后端 _scan_alerts 的 ev.id）
  // 之前会把"分析此条舆情推送…"作为用户消息塞进对话流再走 LLM，造成
  //   ① prompt 回显观感差 ② 多消耗一次 LLM 额度
  // 改为直接 emit('open-event')，复用现成的 EventModal 弹窗（带文章/情感/演变图）
  if (alert?.id) {
    emit("open-event", { id: alert.id });
  }
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
    const resp = await fetch(buildApiUrl("/api/ai/morning_brief"));
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
  // 改造：早报不再以"假装的用户消息+助手消息"形式塞进对话流（避免 prompt
  // 回显观感差），而是直接打开独立的 BriefModal 弹窗（带 PDF 导出 + 追问按钮）
  briefModalLoading.value = true;
  briefModalVisible.value = true;
  try {
    const res = await fetch(buildApiUrl("/api/ai/morning_brief/content"));
    const data = await res.json();
    if (data.ok && data.content) {
      briefModalContent.value = data.content;
      briefModalDate.value = data.date || new Date().toISOString().slice(0, 10);
    } else {
      briefModalContent.value = "";
      briefModalDate.value = new Date().toISOString().slice(0, 10);
    }
  } catch (err) {
    console.warn("[早报] 拉取失败:", err);
    briefModalContent.value = "";
  } finally {
    briefModalLoading.value = false;
  }
};

// "立即生成"按钮：调用 SSE 端点重新生成
const regenerateBrief = async () => {
  briefModalLoading.value = true;
  try {
    // 触发后端生成；完成后刷新 content
    await fetch(buildApiUrl("/api/ai/morning_brief/trigger"), { method: "POST" });
    // 简单轮询 status，最多等待 60 秒
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      const sres = await fetch(buildApiUrl("/api/ai/morning_brief/status"));
      const sdata = await sres.json();
      if (sdata.status === "completed" || sdata.has_content) break;
    }
    const cres = await fetch(buildApiUrl("/api/ai/morning_brief/content"));
    const cdata = await cres.json();
    if (cdata.ok && cdata.content) {
      briefModalContent.value = cdata.content;
      briefModalDate.value = cdata.date || new Date().toISOString().slice(0, 10);
    }
  } catch (err) {
    console.warn("[早报] 重新生成失败:", err);
  } finally {
    briefModalLoading.value = false;
  }
};

// 在弹窗里点"基于此早报追问"→ 关闭弹窗 + 在对话流里发起追问
const askFollowupFromBrief = ({ content }) => {
  briefModalVisible.value = false;
  ensureSession();
  // 把早报内容作为上下文系统消息塞入，再发问
  const session = activeSession.value;
  if (!session) return;
  session.messages.push({
    role: "system",
    content: `[早报上下文]\n${(content || "").slice(0, 2000)}`,
  });
  saveSessions();
  // 让用户自己输入问题
  inputQuery.value = "请基于今日早报，为我分析…";
  nextTick(() => {
    const ta = document.querySelector(".ai-input textarea");
    if (ta) ta.focus();
  });
};

// P6：不跳页下载——fetch + blob + a.download。
const downloadBlobAs = async (url, filename) => {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`download failed: ${res.status}`);
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(objUrl), 4000);
    return true;
  } catch (err) {
    console.warn('[PDF] 下载失败:', err);
    return false;
  }
};

const exportBriefPdf = async () => {
  // P6：原 window.open 会跳转到新标签页中间页，现改为静默下载
  const today = new Date().toISOString().slice(0, 10);
  await downloadBlobAs(buildApiUrl('/api/ai/morning_brief/pdf'), `舆情早报_${today}.pdf`);
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

// 检测一条消息是否本质上是"早报"内容：
// 1) trace 里调用过 get_morning_brief 工具
// 2) 或会话标题/用户问句里包含"早报""日报"关键词
const isMorningBriefMessage = (msg) => {
  try {
    const events = msg?.agent_events || [];
    if (events.some((ev) => (ev?.tool || ev?.name || "") === "get_morning_brief")) return true;
  } catch {}
  const sessionTitle = activeSession.value?.title || "";
  const userQuery = msg?.user_query || "";
  return /早报|日报/.test(sessionTitle) || /早报|日报/.test(userQuery);
};

// P7：基于"会话 + 当前消息"派生 PDF 报告标题
// 优先级：用户手改过的 session.title（≠"新会话"等）> 当前消息 user_query 前 24 字 + " · AI 分析报告"
//   > 会话首条 user 消息前 24 字 > "舆镜对话报告 yyyy-mm-dd"
// 设计目标：导出文件名 / PDF 内嵌封面标题 看上去像产品输出，而不是默认空标题
const _DEFAULT_TITLES = new Set(["新会话", "新对话", "AI 舆情分析报告", ""]);
const _truncate = (s, n) => {
  const t = (s || "").replace(/\s+/g, " ").trim();
  return t.length > n ? t.slice(0, n) + "…" : t;
};
const getReportTitle = (session, msg) => {
  const today = new Date().toISOString().slice(0, 10);
  const sessTitle = (session?.title || "").trim();
  if (sessTitle && !_DEFAULT_TITLES.has(sessTitle)) {
    return sessTitle;
  }
  const currentQuery = (msg?.user_query || "").trim();
  if (currentQuery) {
    return `${_truncate(currentQuery, 24)} · AI 分析报告`;
  }
  const firstUser = (session?.messages || []).find((m) => m.role === "user");
  if (firstUser?.content) {
    return `${_truncate(firstUser.content, 24)} · AI 分析报告`;
  }
  return `舆镜对话报告 ${today}`;
};

const exportMessagePdf = async (msg, msgIndex) => {
  const textContent = msg.agent_final || msg.content;
  if (!textContent && !msg.compare_metrics) return;

  // 早报内容直接复用后端早报 PDF 端点，文件名/标题统一"舆情早报_YYYY-MM-DD.pdf"
  if (isMorningBriefMessage(msg)) {
    // P6：静默下载，不再跳页
    const today = new Date().toISOString().slice(0, 10);
    await downloadBlobAs(buildApiUrl('/api/ai/morning_brief/pdf'), `舆情早报_${today}.pdf`);
    return;
  }

  try {
    const images = [];
    if (msg.compare_metrics) {
      const dataUrl = await captureDashboardImage(msgIndex);
      if (dataUrl) images.push(dataUrl);
    }
    // P7：标题优先级策略 ——让推送出去的 PDF 看上去像产品输出而不是原始贴回
    // 1. 用户手改过的会话标题（非"新会话"）优先级最高
    // 2. 退化到首条用户输入文本前 24 字 + “ · AI 分析报告”
    // 3. 完全拿不到 → “舆镜对话报告 yyyy-mm-dd”
    const reportTitle = getReportTitle(activeSession.value, msg);
    const res = await fetch(buildApiUrl("/api/ai/export_pdf"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: reportTitle,
        content: textContent || "",
        images: images.length ? images : undefined,
      }),
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = reportTitle + ".pdf";
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

// U1: trace 折叠 state 由消息持有；用户可手动展开/收起
const toggleTraceCollapse = (index) => {
  const session = activeSession.value;
  if (!session?.messages?.[index]) return;
  const cur = !!session.messages[index].trace_collapsed;
  patchMessage(session.id, index, { trace_collapsed: !cur });
};

// U1: 收集每条 assistant 消息的 final-card DOM ref，agent done 后自动滚入视野
const finalRefMap = new Map();
const bindFinalRef = (el, index) => {
  if (el) finalRefMap.set(index, el);
  else finalRefMap.delete(index);
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
  // P8：对话气泡与早报统一走 markdown 渲染（DOMPurify 清洗，防 XSS）
  // 之前只做 `**` + `\n` 替换，早报中的 【重点事件 TOP5】/表格/列表都裸输出，观感像 prompt
  // 现在 # / ## / - / 1. / | 表格 都能正确渲染
  return renderMarkdown(text);
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

// 用 marked 完整渲染（支持表格/代码块/引用块/有序无序列表），再做引用替换。
// gfm + breaks 确保 LLM 输出的 GitHub 风格 Markdown（含表格）正确转 HTML。
marked.setOptions({ gfm: true, breaks: true });

const formatAgentFinal = (text) => {
  if (!text) return "";
  let html;
  try {
    html = marked.parse(String(text));
  } catch {
    // 解析失败时退回纯文本（HTML 转义 + 换行）
    html = escapeHtmlForAgent(text).replace(/\n/g, "<br>");
  }
  // 引用识别：中英文双支持
  //   英文：event#123 / article#456
  //   中文：事件#123 / 文章#456 / 事件 # 123 / 事件＃123
  // 归一化成 data-kind=event|article，让 click delegate 统一 emit。
  // 注意：marked 已把 #N 形式的字符以 HTML 实体输出（# 不会被转义，仍保留）。
  return html.replace(
    /(event|article|事件|文章)\s*[#＃]\s*(\d+)/gi,
    (_m, kind, id) => {
      const lower = kind.toLowerCase();
      const dataKind = (lower === "event" || kind === "事件") ? "event" : "article";
      const icon = dataKind === "event" ? "🔗" : "📰";
      return `<a href="#" class="agent-ref agent-ref--${dataKind}" data-kind="${dataKind}" data-id="${id}">${icon}</a>`;
    },
  );
};

const sendAgentMessage = async (sessionId, outgoing) => {
  pushMessage(sessionId, { role: "user", content: outgoing });
  inputQuery.value = "";
  setSessionDraft(sessionId, "");
  pendingSessionIds.value = [...pendingSessionIds.value, sessionId];
  await scrollToBottom();

  // 构建多轮历史（只传 user/assistant 的文字，不传 tool 调用细节）
  const session = getSessionById(sessionId);
  const chatHistory = [];
  if (session) {
    // 排除刚 push 的 user 消息和即将 push 的 assistant 占位
    for (const m of session.messages) {
      if (m.role === "user" && m.content) {
        chatHistory.push({ role: "user", content: m.content });
      } else if (m.role === "assistant" && (m.agent_final || m.content)) {
        chatHistory.push({ role: "assistant", content: m.agent_final || m.content });
      }
    }
    // 去掉最后一条（就是本次 outgoing，已在 message 字段发送）
    if (chatHistory.length && chatHistory[chatHistory.length - 1].role === "user") {
      chatHistory.pop();
    }
  }

  const assistantIndex = pushMessage(sessionId, {
    role: "assistant",
    content: "",
    agent_events: [],
    agent_running: true,
    agent_final: "",
    agent_error: "",
  });
  await scrollToBottom();

  const accumulated = [];
  let finalBuffer = "";

  try {
    const reqBody = { message: outgoing, stream: true };
    if (chatHistory.length > 0) {
      // 限制历史长度，避免上下文过大（保留最近 6 轮 = 12 条）
      reqBody.history = chatHistory.slice(-12);
    }
    const res = await fetch(AGENT_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(reqBody),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

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
          // 检测到平台对比工具输出时，提取 {a, b} 喂给 CompareDashboard。
          // output 结构由 tool_compare_platforms._handler 定义，含 _type / a / b / a_source_id / b_source_id。
          if (ev.type === "tool_result" && ev.name === "compare_platforms" && ev.ok && ev.output?.a && ev.output?.b) {
            patch.compare_metrics = { a: ev.output.a, b: ev.output.b };
          }
          if (ev.type === "error") {
            // loop 内部终止信号（max_steps / too_many_errors）已由 AgentTrace 的
            // trace-terminated 卡片显示，气泡级 agent_error 只保留"硬错误"（LLM 调用失败等无 terminated_reason）。
            if (!ev.terminated_reason) {
              patch.agent_error = ev.message || "智能体出错";
            }
          }
          if (ev.type === "done") {
            patch.agent_running = false;
            // 如果结束时仍无最终结论，给用户一个友好提示
            if (!finalBuffer && ev.terminated_reason && ev.terminated_reason !== "final") {
              patch.agent_error = "智能体未能给出结论，请尝试换个问法。";
            }
            // U1: 完成时默认折叠 trace，让最终回答抢占视野
            if (finalBuffer) {
              patch.trace_collapsed = true;
            }
          }
          patchMessage(sessionId, assistantIndex, patch);
          // U1: done 后等 DOM 更新完，把最终回答卡片滚入视野顶部
          if (ev.type === "done" && finalBuffer) {
            nextTick(() => {
              const finalEl = finalRefMap.get(assistantIndex);
              if (finalEl?.scrollIntoView) {
                finalEl.scrollIntoView({ behavior: "smooth", block: "start" });
              }
            });
          }
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
    // 生成追问建议：基于工具调用情况
    if (finalBuffer) {
      const suggestions = generateFollowUpSuggestions(accumulated);
      if (suggestions.length) {
        patchMessage(sessionId, assistantIndex, { suggestions });
      }
    }
    pendingSessionIds.value = pendingSessionIds.value.filter((id) => id !== sessionId);
    await scrollToBottom();
  }
};

// 根据 Agent 调用的工具生成追问建议
const TOOL_FOLLOW_UPS = {
  search_events: ["这些事件中哪个传播最广？", "对比这几个事件的情绪倾向"],
  get_event_detail: ["分析该事件的情绪走势", "该事件是否有后续发展？"],
  analyze_event_sentiment: ["哪些平台的负面情绪最多？", "和上周相比情绪有变化吗？"],
  compare_events: ["这些事件有什么共性？", "哪个事件后续影响更大？"],
  compare_platforms: ["两个平台的主要分歧是什么？", "再补上头条一起对比"],
  rank_events_by_sentiment: ["最愤怒的事件有什么共性？", "哪些事件的情绪最复杂"],
  search_articles: ["帮我总结这些文章的核心观点", "有哪些不同的立场？"],
  semantic_search_articles: ["有没有相关但被忽略的冷门事件？", "这些内容的主要分歧在哪？"],
  list_hot_platforms: ["各平台热点有什么差异？", "哪些热点只在单一平台出现？"],
  get_morning_brief: ["今天有什么值得深入分析的事件？", "帮我对比昨天和今天的热点变化"],
};

function generateFollowUpSuggestions(events) {
  const toolNames = new Set();
  for (const ev of events) {
    if (ev.type === "tool_call" && ev.name) toolNames.add(ev.name);
  }
  const pool = [];
  for (const name of toolNames) {
    const candidates = TOOL_FOLLOW_UPS[name];
    if (candidates) pool.push(...candidates);
  }
  // 去重后取前 3 个
  return [...new Set(pool)].slice(0, 3);
}

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

  // 统一走智能体链路：平台对比由 agent 工具 `compare_platforms` 接管，
  // SSE tool_result 事件会直接填 msg.compare_metrics 触发仪表盘。
  return sendAgentMessage(sessionId, outgoing);
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
  padding: 10px 28px; background: rgba(255, 255, 255, 0.9); backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  display: flex; justify-content: space-between; align-items: center;
  z-index: 10;
}
.header-left { display: flex; align-items: center; gap: 0.6rem; }
.workspace-kicker { font-weight: 700; letter-spacing: 0.3px; border-radius: 6px; font-size: 0.82rem; }
.workspace-meta { display: flex; align-items: center; gap: 0.25rem; font-size: 0.78rem; color: #64748b; }
.meta-sep { color: #94a3b8; }
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
/* P8：早报 / 长回复 markdown 渲染样式（与 AnalysisModal 保持视觉一致） */
.msg-text :deep(h1),
.msg-text :deep(h2),
.msg-text :deep(h3),
.msg-text :deep(h4) { font-weight: 900; color: #0f172a; margin: 14px 0 6px; line-height: 1.4; letter-spacing: -0.01em; }
.msg-text :deep(h1) { font-size: 19px; }
.msg-text :deep(h2) { font-size: 17px; padding-bottom: 5px; border-bottom: 2px solid rgba(59, 130, 246, 0.18); }
.msg-text :deep(h3) { font-size: 15.5px; color: #1d4ed8; }
.msg-text :deep(h4) { font-size: 14.5px; color: #334155; }
.msg-text :deep(p) { margin: 6px 0; }
.msg-text :deep(ul),
.msg-text :deep(ol) { margin: 6px 0 6px 4px; padding-left: 22px; }
.msg-text :deep(li) { margin: 3px 0; line-height: 1.7; }
.msg-text :deep(li::marker) { color: #3b82f6; font-weight: 800; }
.msg-text :deep(strong) { color: #0f172a; font-weight: 900; }
.msg-text :deep(em) { color: #475569; font-style: normal; background: linear-gradient(180deg, transparent 60%, rgba(250, 204, 21, 0.45) 60%); padding: 0 2px; }
.msg-text :deep(blockquote) { margin: 10px 0; padding: 8px 12px; border-left: 4px solid #3b82f6; background: rgba(59, 130, 246, 0.06); border-radius: 0 8px 8px 0; color: #334155; font-size: 14px; }
.msg-text :deep(code) { background: rgba(15, 23, 42, 0.06); padding: 1px 5px; border-radius: 4px; font-family: 'Fira Code', monospace; font-size: 12.5px; color: #be185d; }
.msg-text :deep(pre) { background: #0f172a; color: #e2e8f0; padding: 12px 14px; border-radius: 10px; overflow-x: auto; margin: 10px 0; }
.msg-text :deep(pre code) { background: transparent; color: inherit; padding: 0; }
.msg-text :deep(hr) { border: none; border-top: 1px dashed rgba(148, 163, 184, 0.4); margin: 12px 0; }
.msg-text :deep(table) { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 13.5px; }
.msg-text :deep(th),
.msg-text :deep(td) { border: 1px solid rgba(148, 163, 184, 0.28); padding: 6px 9px; }
.msg-text :deep(th) { background: rgba(59, 130, 246, 0.08); font-weight: 800; color: #1d4ed8; }
.msg-text :deep(a) { color: #1d4ed8; text-decoration: underline; }

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
.mcp-input-area:focus { border-color: var(--color-accent, #B45309); background: #fff; box-shadow: 0 0 0 3px rgba(180, 83, 9, 0.08); }

.btn-send-capsule {
  /* 发送按钮：近墨石板底 + 暖白文字，与 header"全站同步"主按钮一致 */
  background: var(--color-brand, #0F172A); color: #fff; border: none; border-radius: 12px; height: 56px; padding: 0 24px;
  display: flex; align-items: center; gap: 10px; font-weight: 800; cursor: pointer; transition: 0.2s;
}
.btn-send-capsule:hover { transform: translateY(-2px); box-shadow: 0 8px 18px rgba(20, 16, 8, 0.12); }

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
/* 生成中态：去蓝改中性暖灰，不与抖起的 accent 争主 */
.brief-banner--generating {
  background: var(--color-surface-2, #F5F5F2);
  border-color: var(--color-border, #E5E5DD);
}
.brief-banner--generating .brief-banner-icon { color: var(--color-text-2, #57534E); }
.brief-banner--generating .brief-banner-text strong { color: var(--color-text, #1C1917); }
.brief-banner--generating .brief-banner-text span { color: var(--color-text-2, #57534E); }
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
  transition: color 0.2s;
}
/* U2: 头部颜色随最高 level 联动 */
.alerts-header-critical { color: #dc2626; }
.alerts-header-warning  { color: #d97706; }
.alerts-header-info     { color: #2563eb; }
.alerts-header-warning .alerts-count { background: #d97706; }
.alerts-header-info .alerts-count    { background: #2563eb; }
.alerts-header-warning .alerts-clear { border-color: rgba(217,119,6,0.25); color: #d97706; }
.alerts-header-warning .alerts-clear:hover { background: #d97706; color: #fff; }
.alerts-header-info .alerts-clear { border-color: rgba(37,99,235,0.25); color: #2563eb; }
.alerts-header-info .alerts-clear:hover { background: #2563eb; color: #fff; }
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
  display: flex; align-items: center; gap: 12px;
  padding: 12px 14px; border-radius: 12px; margin-bottom: 6px;
  background: #fff; border: 1px solid rgba(0,0,0,0.06);
  transition: 0.2s; animation: briefSlideIn 0.25s ease;
  border-left: 4px solid transparent;
}
.alert-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.08); transform: translateX(2px); }
/* U2: 三级色块（背景 + 左描边 + icon 颜色）*/
.alert-icon {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.alert-critical {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-color: rgba(220,38,38,0.18);
  border-left-color: #dc2626;
}
.alert-critical .alert-icon { background: rgba(220,38,38,0.15); color: #dc2626; }
.alert-critical .alert-body strong { color: #7f1d1d; }
.alert-warning {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-color: rgba(217,119,6,0.18);
  border-left-color: #d97706;
}
.alert-warning .alert-icon { background: rgba(217,119,6,0.15); color: #d97706; }
.alert-warning .alert-body strong { color: #78350f; }
.alert-info {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-color: rgba(37,99,235,0.18);
  border-left-color: #2563eb;
}
.alert-info .alert-icon { background: rgba(37,99,235,0.15); color: #2563eb; }
.alert-info .alert-body strong { color: #1e3a8a; }
.alert-body { flex: 1; min-width: 0; }
.alert-body strong { display: block; font-size: 13px; font-weight: 700; color: #0f172a; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.alert-meta { font-size: 11px; color: #64748b; }
.alert-time { font-weight: 600; color: #475569; cursor: help; }
.alert-action {
  padding: 5px 14px; border-radius: 8px; border: 1px solid rgba(0,0,0,0.08);
  background: rgba(255,255,255,0.6); color: #475569; font-size: 12px; font-weight: 700;
  cursor: pointer; transition: 0.2s; white-space: nowrap;
}
.alert-critical .alert-action { color: #dc2626; border-color: rgba(220,38,38,0.25); }
.alert-critical .alert-action:hover { background: #dc2626; color: #fff; border-color: #dc2626; }
.alert-warning .alert-action { color: #d97706; border-color: rgba(217,119,6,0.25); }
.alert-warning .alert-action:hover { background: #d97706; color: #fff; border-color: #d97706; }
.alert-info .alert-action { color: #2563eb; border-color: rgba(37,99,235,0.25); }
.alert-info .alert-action:hover { background: #2563eb; color: #fff; border-color: #2563eb; }
.alert-dismiss {
  background: none; border: none; color: #94a3b8; cursor: pointer;
  font-size: 14px; display: flex; align-items: center; transition: 0.2s;
}
.alert-dismiss:hover { color: #ef4444; }

@keyframes spin { to { transform: rotate(360deg); } }

.loading-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 1rem 0;
}
.loading-copy {
  font-size: 0.85rem;
  color: #64748b;
}

/* =========================================================================
 * 智能体模式 · 顶部标记 + 预设条 + 消息气泡中的 AgentTrace/final-card
 * ========================================================================= */
.agent-badge {
  /* Tool-Calling chip：去紫色渐变，暖白底 + 赤陶红描边/字 */
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.2rem 0.6rem 0.2rem 0.5rem;
  border-radius: 999px;
  background: var(--color-surface-2, #F5F5F2);
  border: 1px solid var(--color-border, #E5E5DD);
  color: var(--color-accent, #B45309);
  font-size: 0.72rem;
  font-weight: 600;
}

.agent-preset-strip {
  /* 智能体说明条：去紫渐变，改纸白底 + 暖灰描边 + 赤陶红左 border */
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  padding: 0.85rem 1rem;
  background: var(--color-surface, #FFFFFF);
  border: 1px solid var(--color-border, #E5E5DD);
  border-left: 3px solid var(--color-accent, #B45309);
  border-radius: 8px;
  margin-bottom: 0.5rem;
  box-shadow: var(--shadow-1, 0 1px 0 rgba(0, 0, 0, 0.04));
}
/* 有对话历史时：折叠为紧凑状态条 */
.agent-preset-strip.agent-preset-compact {
  padding: 0.5rem 0.85rem;
  gap: 0;
}
.agent-preset-strip.agent-preset-compact .agent-preset-head {
  font-size: 0.78rem;
}
.agent-preset-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--color-text, #1C1917);
  font-family: var(--font-display, "Noto Serif SC", serif);
  font-size: 0.85rem;
  font-weight: 600;
}
.agent-preset-head iconify-icon { color: var(--color-accent, #B45309); font-size: 1.05rem; }
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
  border: 1px solid var(--color-border, #E5E5DD);
  border-radius: 8px;
  color: var(--color-text, #1C1917);
  text-align: left;
  cursor: pointer;
  transition: transform 0.15s, border-color 0.15s, box-shadow 0.15s;
}
.agent-preset-card:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: var(--color-accent, #B45309);
  box-shadow: 0 2px 8px rgba(20, 16, 8, 0.06);
}
.agent-preset-card:disabled { opacity: 0.55; cursor: not-allowed; }
.agent-preset-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--color-surface-2, #F5F5F2);
  color: var(--color-accent, #B45309);
  border-radius: 8px;
  font-size: 1.15rem;
  line-height: 1;
}
.agent-preset-body { display: flex; flex-direction: column; gap: 0.15rem; min-width: 0; }
.agent-preset-body strong { font-size: 0.9rem; color: var(--color-text, #1C1917); }
.agent-preset-body span { font-size: 0.72rem; color: var(--color-text-2, #57534E); }

.agent-meta-chip {
  /* 智能体 meta chip：去紫渐变，中性底 + 赤陶红边 */
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.12rem 0.6rem;
  background: var(--color-surface-2, #F5F5F2);
  border: 1px solid var(--color-border, #E5E5DD);
  border-radius: 999px;
  color: var(--color-accent, #B45309);
  font-size: 0.72rem;
  align-self: flex-start;
}
.agent-meta-elapsed {
  color: var(--color-text-2, #57534E);
  font-size: 0.7rem;
  padding-left: 0.3rem;
  border-left: 1px solid var(--color-border, #E5E5DD);
  margin-left: 0.2rem;
}

/* Batch D: 最终回答卡 = AI 助手页的 payoff，按编辑感主张重写：
   去原绿+蓝渐变与紫色 blockquote → 白底 + 暖灰描边 + 赤陶红 left border + 衬线小标题 */
.agent-final-card {
  margin-top: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-accent);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.agent-final-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text);
  font-family: var(--font-display);
  font-weight: 500;
  font-size: var(--text-md);
  letter-spacing: 0.01em;
}
.agent-final-head iconify-icon { color: var(--color-accent); }
.agent-final-body {
  color: var(--color-text);
  font-size: var(--text-base);
  line-height: 1.75;
}
.agent-final-body :deep(h3) { margin: 0.55rem 0 0.25rem; font-size: 1.02rem; font-family: var(--font-display); font-weight: 500; color: var(--color-text); }
.agent-final-body :deep(h4) { margin: 0.45rem 0 0.2rem; font-size: 0.94rem; font-weight: 600; color: var(--color-text); }
.agent-final-body :deep(p)  { margin: 0.2rem 0; }
.agent-final-body :deep(ul) { margin: 0.3rem 0 0.3rem 1.2rem; padding: 0; }
.agent-final-body :deep(ol) { margin: 0.3rem 0 0.3rem 1.4rem; padding: 0; }
.agent-final-body :deep(li) { list-style: disc; margin: 0.12rem 0; }
.agent-final-body :deep(ol li) { list-style: decimal; }
.agent-final-body :deep(strong) { color: var(--color-text); font-weight: 600; }
.agent-final-body :deep(code) {
  background: var(--color-surface-2); color: var(--color-accent);
  padding: 1px 6px; border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 0.86em;
}
.agent-final-body :deep(pre) {
  background: var(--color-brand); color: var(--color-text-on-dark);
  padding: 0.6rem 0.8rem; border-radius: var(--radius-md);
  overflow-x: auto; font-size: 0.85em; margin: 0.4rem 0;
  font-family: var(--font-mono);
}
.agent-final-body :deep(pre code) {
  background: transparent; color: inherit; padding: 0;
}
.agent-final-body :deep(blockquote) {
  margin: 0.4rem 0; padding: 0.4rem 0.8rem;
  border-left: 3px solid var(--color-border);
  background: var(--color-surface-2); color: var(--color-text-2);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
}
.agent-final-body :deep(hr) {
  border: 0; border-top: 1px dashed var(--color-border); margin: 0.6rem 0;
}
/* GFM 表格：保持视觉一致的紧凑卡片样式 */
.agent-final-body :deep(table) {
  border-collapse: collapse;
  margin: 0.5rem 0; width: 100%;
  font-size: 0.88rem;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md); overflow: hidden;
}
.agent-final-body :deep(thead) { background: var(--color-surface-2); }
.agent-final-body :deep(th),
.agent-final-body :deep(td) {
  padding: 0.4rem 0.7rem;
  border-bottom: 1px solid var(--color-border-soft);
  text-align: left; vertical-align: top;
}
.agent-final-body :deep(th) { color: var(--color-text); font-weight: 600; }
.agent-final-body :deep(tbody tr:last-child td) { border-bottom: 0; }
.agent-final-body :deep(tbody tr:hover) { background: #fafafa; }
.agent-final-body :deep(.agent-ref) {
  display: inline-flex; align-items: center;
  text-decoration: none;
  font-size: 12px; font-weight: 600;
  padding: 2px 9px; border-radius: 999px;
  vertical-align: middle; white-space: nowrap;
  cursor: pointer; transition: opacity 0.15s;
}
.agent-final-body :deep(.agent-ref:hover) { opacity: 0.72; text-decoration: none; }
.agent-final-body :deep(.agent-ref--event) {
  background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0;
}
.agent-final-body :deep(.agent-ref--article) {
  background: #eff6ff; color: #2563eb; border: 1px solid #bfdbfe;
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

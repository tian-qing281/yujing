<template>
  <Transition name="fade">
    <div class="modal-overlay" @click="$emit('close')">
      <div class="credential-box modal-box hs-panel" @click.stop>
        <header class="cred-header">
          <div class="header-main">
            <div class="title-icon avatar placeholder">
              <iconify-icon icon="mdi:shield-key-outline" />
            </div>
            <div>
              <h3>Cookie 配置</h3>
              <p>只保存在本地采集环境，用于需要登录态的平台抓取。</p>
            </div>
          </div>

          <button class="btn btn-circle btn-ghost btn-close" type="button" @click="$emit('close')">
            <iconify-icon icon="mdi:close" />
          </button>
        </header>

        <div class="cred-body">
          <div class="source-grid">
            <label class="field">
              <span class="field-label label-text">采集源</span>
              <div class="select-wrap form-control">
                <select v-model="form.source_id" class="cred-select select select-bordered" aria-label="选择采集源">
                  <option v-for="item in selectableSources" :key="item.id" :value="item.id">
                    {{ item.name }}
                  </option>
                </select>
              </div>
            </label>

            <div class="status-card card bg-base-100" :class="{ active: currentConfigured || currentPublicSource }">
              <span class="field-label label-text">当前状态</span>
              <div class="status-row">
                <span class="status-dot" />
                <strong>{{ currentPublicSource ? "无需配置" : currentConfigured ? "已配置" : "未配置" }}</strong>
              </div>
              <p>{{ currentStatusText }}</p>
            </div>
          </div>

          <label class="field field-block">
            <span class="field-label label-text">Cookie 内容</span>
            <textarea
              v-model="form.cookie"
              class="textarea textarea-bordered credential-textarea"
              :disabled="currentPublicSource"
              spellcheck="false"
              :placeholder="currentPublicSource ? '该来源走公开正文接口，不需要 Cookie。' : '粘贴从浏览器复制的完整 Cookie 字符串。'"
            />
          </label>

          <div v-if="feedback?.text" class="feedback alert" :class="feedback.type || 'info'">
            {{ feedback.text }}
          </div>

          <div class="modal-actions">
            <button class="btn btn-ghost btn-secondary" type="button" @click="$emit('close')">关闭</button>
            <button class="btn btn-primary" type="button" :disabled="submitting || currentPublicSource" @click="emitSubmit">
              <iconify-icon :icon="submitting ? 'mdi:loading' : 'mdi:content-save-outline'" :class="{ spinning: submitting }" />
              <span>{{ submitting ? "保存中..." : "保存 Cookie" }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  submitting: Boolean,
  sourceRegistry: {
    type: Array,
    default: () => [],
  },
  credentialStatus: {
    type: Object,
    default: () => ({}),
  },
  feedback: {
    type: Object,
    default: () => ({ type: "", text: "" }),
  },
});

const emit = defineEmits(["close", "submit"]);

const crawlerSourceIds = new Set([
  "weibo_hot_search",
  "baidu_hot",
  "toutiao_hot",
  "bilibili_hot_video",
  "zhihu_hot_question",
  "thepaper_hot",
  "wallstreetcn_news",
  "cls_telegraph",
]);

const publicSourceIds = new Set(["thepaper_hot", "wallstreetcn_news", "cls_telegraph"]);

const selectableSources = computed(() =>
  (props.sourceRegistry || []).filter((item) => item.id && crawlerSourceIds.has(item.id))
);

const form = ref({
  source_id: "weibo_hot_search",
  cookie: "",
});

watch(
  selectableSources,
  (sources) => {
    if (!sources.length) return;
    const exists = sources.some((item) => item.id === form.value.source_id);
    if (!exists) {
      form.value.source_id = sources[0].id;
    }
  },
  { immediate: true }
);

const currentConfigured = computed(() => Boolean(props.credentialStatus?.[form.value.source_id]));
const currentPublicSource = computed(() => publicSourceIds.has(form.value.source_id));
const currentStatusText = computed(() => {
  if (currentPublicSource.value) return "公开正文源，已纳入全网同步，不需要本地 Cookie。";
  return currentConfigured.value ? "本地已存在可用 Cookie 文件。" : "保存后会写入本地 Cookie 目录。";
});

const emitSubmit = () => {
  if (currentPublicSource.value) return;
  emit("submit", {
    source_id: form.value.source_id,
    cookie: form.value.cookie,
  });
};
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(28, 25, 23, 0.42);
}

.credential-box {
  width: min(720px, 100%);
  border-radius: 4px;
  overflow: hidden;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-top: 3px solid var(--color-accent);
  box-shadow: 0 18px 48px rgba(28, 25, 23, 0.12);
  color: var(--color-text);
  text-align: left;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
  color-scheme: light;
}

.credential-box *,
.credential-box *::before,
.credential-box *::after {
  box-sizing: border-box;
}

.cred-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 28px 30px 24px;
  border-bottom: 1px solid var(--color-border, #E5E5DD);
}

.header-main {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  flex: 1;
}

.title-icon {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 0;
  background: transparent;
  color: var(--color-accent);
  font-size: 22px;
  border: 1px solid var(--color-accent);
}

.title-icon :deep(span) {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
}

.header-main h3 {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.01em;
  font-family: var(--font-display, "Noto Serif SC", serif);
  color: var(--color-text-1, #1c1917);
}

.header-main p {
  margin: 0;
  max-width: 420px;
  color: var(--color-text-3, #78716c);
  font-size: 13px;
  line-height: 1.6;
}

.btn-close {
  color: var(--color-text-3);
  transition: color 0.18s ease;
  font-size: 20px;
}

.btn-close:hover {
  color: var(--color-accent);
}

.cred-body {
  padding: 30px;
}

.source-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(220px, 0.75fr);
  gap: 18px;
  margin-bottom: 22px;
}

.field-block {
  margin-bottom: 18px;
}

.field-label {
  display: block;
  margin-bottom: 10px;
  color: var(--color-accent, #B45309);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  font-family: var(--font-display, "Noto Serif SC", serif);
}

.cred-select,
.credential-textarea {
  width: 100%;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

.credential-textarea:disabled {
  background: var(--color-surface-2, #F5F5F2);
  color: var(--color-text-3, #94a3b8);
  cursor: not-allowed;
}

.cred-select {
  display: block;
  min-height: 54px;
  color: var(--color-text);
  font-size: 15px;
  font-weight: 700;
  border-radius: 0;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  box-shadow: none;
}

.cred-select:focus,
.credential-textarea:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(180, 83, 9, 0.16);
}

.status-card {
  min-height: 54px;
  padding: 14px 16px;
  border-radius: 0;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  box-shadow: none;
}

.status-card.active {
  border-color: rgba(21, 128, 61, 0.35);
  background: transparent;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--color-text-3, #94a3b8);
}

.status-card.active .status-dot {
  background: var(--color-success, #15803D);
  box-shadow: 0 0 0 4px rgba(21, 128, 61, 0.10);
}

.status-card p {
  margin: 8px 0 0;
  color: var(--color-text-3, #78716c);
  font-size: 12px;
  line-height: 1.5;
}

.credential-textarea {
  min-height: 210px;
  resize: vertical;
  border-radius: 0;
  padding: 16px 18px;
  font-size: 14px;
  line-height: 1.65;
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  caret-color: var(--color-accent);
}

.credential-textarea::placeholder {
  color: var(--color-text-3, #94a3b8);
  opacity: 1;
}

.feedback {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 0;
  font-size: 13px;
  line-height: 1.5;
  border-width: 1px;
  justify-content: flex-start;
}

.feedback.success {
  color: var(--color-success, #15803D);
  background: transparent;
  border: 1px solid rgba(21, 128, 61, 0.35);
  border-left: 3px solid var(--color-success, #15803D);
}

.feedback.error {
  color: var(--color-critical, #B91C1C);
  background: transparent;
  border: 1px solid rgba(185, 28, 28, 0.35);
  border-left: 3px solid var(--color-critical, #B91C1C);
}

.feedback.info {
  color: var(--color-text-2);
  background: transparent;
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-accent);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.btn-secondary,
.btn-primary {
  border-radius: 0;
  height: 44px;
  padding: 0 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-family: var(--font-display, "Noto Serif SC", serif);
  cursor: pointer;
  transition: background 0.18s, color 0.18s, border-color 0.18s;
}

.btn-secondary {
  color: var(--color-text-2);
  background: transparent;
  border: 1px solid var(--color-border);
}
.btn-secondary:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.btn-primary {
  background: var(--color-text-1, #1c1917);
  color: #FAFAF7;
  min-width: 148px;
  border: 1px solid var(--color-text-1, #1c1917);
}
.btn-primary:hover:not(:disabled) {
  background: var(--color-accent);
  border-color: var(--color-accent);
}

.btn-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.spinning {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 720px) {
  .credential-box {
    width: 100%;
    border-radius: 0;
  }

  .cred-header,
  .cred-body {
    padding-left: 20px;
    padding-right: 20px;
  }

  .source-grid {
    grid-template-columns: 1fr;
  }

  .modal-actions {
    flex-direction: column-reverse;
  }

  .btn-secondary,
  .btn-primary {
    width: 100%;
  }
}
</style>

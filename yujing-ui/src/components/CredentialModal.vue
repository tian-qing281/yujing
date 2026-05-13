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
              <h3>登录凭据配置</h3>
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
            <span class="field-label label-text">登录凭据内容</span>
            <textarea
              v-model="form.cookie"
              class="textarea textarea-bordered credential-textarea"
              :disabled="currentPublicSource"
              spellcheck="false"
              :placeholder="currentPublicSource ? '该来源走公开正文接口，不需要登录凭据。' : '粘贴浏览器中复制的完整登录凭据字符串。'"
            />
          </label>

          <div v-if="feedback?.text" class="feedback alert" :class="feedback.type || 'info'">
            {{ feedback.text }}
          </div>

          <div class="modal-actions">
            <button class="btn btn-ghost btn-secondary" type="button" @click="$emit('close')">关闭</button>
            <button class="btn btn-primary" type="button" :disabled="submitting || currentPublicSource" @click="emitSubmit">
              <iconify-icon :icon="submitting ? 'mdi:loading' : 'mdi:content-save-outline'" :class="{ spinning: submitting }" />
              <span>{{ submitting ? "保存中..." : "保存登录凭据" }}</span>
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
  if (currentPublicSource.value) return "公开正文源，已纳入全网同步，不需要本地登录凭据。";
  return currentConfigured.value ? "本地已存在可用登录凭据文件。" : "保存后会写入本地凭据目录。";
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
  background: rgba(15, 23, 42, 0.72);
  backdrop-filter: blur(16px);
}

.credential-box {
  width: min(720px, 100%);
  /* editorial: 去渐变 + 大圆角，走报纸严谨面 */
  border-radius: 6px;
  overflow: hidden;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-top: 3px solid var(--color-accent);
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.14);
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
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
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
  /* editorial: 糖果蓝 → 米白 + 赤陶红 */
  border-radius: 4px;
  background: var(--color-surface-2);
  color: var(--color-accent);
  font-size: 22px;
  border: 1px solid var(--color-border);
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
  letter-spacing: -0.02em;
}

.header-main p {
  margin: 0;
  max-width: 420px;
  color: #64748b;
  font-size: 14px;
  line-height: 1.6;
}

.btn-close {
  color: #94a3b8;
  transition: color 0.2s ease, transform 0.2s ease, background 0.2s ease;
  font-size: 20px;
}

.btn-close:hover {
  color: #0f172a;
  transform: scale(1.04);
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
  color: #475569;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.cred-select,
.credential-textarea {
  width: 100%;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
  font-family: "PingFang SC", "Microsoft YaHei", sans-serif;
}

.credential-textarea:disabled {
  background: #f8fafc;
  color: #94a3b8;
  cursor: not-allowed;
}

.cred-select {
  display: block;
  min-height: 54px;
  color: var(--color-text);
  font-size: 15px;
  font-weight: 700;
  /* editorial: 去圆额 */
  border-radius: 4px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  box-shadow: none;
}

.cred-select:focus,
.credential-textarea:focus {
  outline: none;
  /* editorial: 蓝 focus ring → 赤陶红 */
  border-color: var(--color-accent);
  box-shadow: 0 0 0 3px rgba(180, 83, 9, 0.16);
}

.status-card {
  min-height: 54px;
  padding: 14px 16px;
  /* editorial: 去圆额 + 走 token */
  border-radius: 4px;
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  box-shadow: none;
}

.status-card.active {
  /* 保留绿作为 success 语义，但去糖果渐变 */
  border-color: rgba(21, 128, 61, 0.25);
  background: rgba(21, 128, 61, 0.04);
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
  background: #94a3b8;
}

.status-card.active .status-dot {
  /* editorial: 保留信号绿但用 token success */
  background: var(--color-success, #15803D);
  box-shadow: 0 0 0 4px rgba(21, 128, 61, 0.10);
}

.status-card p {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
}

.credential-textarea {
  min-height: 210px;
  resize: vertical;
  /* editorial: 去圆额 */
  border-radius: 4px;
  padding: 16px 18px;
  font-size: 14px;
  line-height: 1.65;
  background: var(--color-surface);
  color: var(--color-text);
  caret-color: var(--color-accent);
}

.credential-textarea::placeholder {
  color: #64748b;
  opacity: 1;
}

.feedback {
  margin-bottom: 16px;
  padding: 12px 14px;
  /* editorial: 去圆额 */
  border-radius: 4px;
  font-size: 14px;
  line-height: 1.5;
  border-width: 1px;
  justify-content: flex-start;
}

.feedback.success {
  color: var(--color-success, #15803D);
  background: rgba(21, 128, 61, 0.06);
  border: 1px solid rgba(21, 128, 61, 0.20);
}

.feedback.error {
  color: var(--color-critical, #B91C1C);
  background: rgba(185, 28, 28, 0.05);
  border: 1px solid rgba(185, 28, 28, 0.18);
}

.feedback.info {
  /* editorial: 糖果蓝 → 赤陶红中性 info */
  color: var(--color-text-2);
  background: var(--color-surface-2);
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
  /* editorial: 去圆额 */
  border-radius: 4px;
  height: 46px;
  padding: 0 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.2s ease, background 0.2s ease, opacity 0.2s ease;
}

.btn-secondary {
  color: var(--color-text-2);
  background: transparent;
  border: 1px solid var(--color-border);
  text-transform: none;
}

.btn-primary {
  /* editorial: 糖果蓝 → 近墨石板主动作 */
  background: var(--color-brand);
  color: #FAFAF7;
  min-width: 148px;
  text-transform: none;
  border: none;
}

.btn-primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn-secondary:hover,
.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
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
    border-radius: 22px;
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

<!-- 早报独立弹窗
   - 与 AIConsultant 解耦：点"查看早报"直接打开此弹窗，不再把"查看今日舆情早报"作为
     用户消息塞进对话流（避免 prompt 回显观感差 + 多消耗一次 LLM 额度）
   - 内容用 marked + DOMPurify 渲染，与 AnalysisModal 视觉规范一致
   - 自带"导出 PDF"按钮（fetch+blob 不跳页）
   - 支持"基于此早报追问 →"二级动作：emit 'ask-followup' 把内容回传给父组件
-->
<template>
  <Transition name="brief-fade">
    <div v-if="visible" class="brief-overlay" @click.self="$emit('close')">
      <div class="brief-modal">
        <header class="brief-header">
          <div class="brief-header-left">
            <iconify-icon icon="ri:sun-line" class="brief-header-icon" />
            <div>
              <div class="brief-eyebrow">YuJing · Morning Brief</div>
              <h1 class="brief-title">今日舆情早报</h1>
              <p class="brief-meta">{{ briefDate || todayLabel }} · 智能体自动汇编</p>
            </div>
          </div>
          <button class="brief-close" type="button" @click="$emit('close')">
            <iconify-icon icon="ri:close-line" />
          </button>
        </header>

        <div class="brief-body">
          <div v-if="loading" class="brief-loading">
            <iconify-icon icon="ri:loader-4-line" class="brief-loading-icon" />
            <p>正在生成今日早报…</p>
          </div>
          <div
            v-else-if="renderedHtml"
            class="brief-content markdown-body"
            v-html="renderedHtml"
          ></div>
          <div v-else class="brief-empty">
            <iconify-icon icon="ri:file-warning-line" />
            <p>尚未生成今日早报</p>
            <button class="brief-empty-btn" type="button" @click="$emit('regenerate')">
              立即生成
            </button>
          </div>
        </div>

        <footer v-if="!loading && renderedHtml" class="brief-footer">
          <button class="brief-action brief-action-secondary" type="button" @click="onAskFollowup">
            <iconify-icon icon="ri:question-answer-line" />
            <span>基于此早报追问</span>
          </button>
          <button class="brief-action brief-action-primary" type="button" @click="onExportPdf('pdf')">
            <iconify-icon icon="ri:file-pdf-line" />
            <span>导出 PDF</span>
          </button>
          <button class="brief-action brief-action-primary" type="button" @click="onExportPdf('docx')">
            <iconify-icon icon="ri:file-word-2-line" />
            <span>导出 Word</span>
          </button>
          <button class="brief-action brief-action-primary" type="button" @click="onExportPdf('pptx')">
            <iconify-icon icon="ri:file-ppt-2-line" />
            <span>导出 PPT</span>
          </button>
        </footer>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from "vue";
import { renderMarkdown } from "@/utils/markdown";
import { buildApiUrl } from "../config/api";

const props = defineProps({
  visible: { type: Boolean, default: false },
  content: { type: String, default: "" },
  briefDate: { type: String, default: "" },
  loading: { type: Boolean, default: false },
});

const emit = defineEmits(["close", "regenerate", "ask-followup"]);

const todayLabel = new Date().toISOString().slice(0, 10);

const renderedHtml = computed(() => renderMarkdown(props.content || ""));

// PDF / Word / PPT：fetch + blob + a.download，不跳页
const onExportPdf = async (format = 'pdf') => {
  try {
    const ext = ['docx', 'pptx'].includes(format) ? format : 'pdf';
    const url = buildApiUrl(`/api/ai/morning_brief/pdf?format=${ext}`);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`报告下载失败 ${res.status}`);
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objUrl;
    a.download = `舆情早报_${props.briefDate || todayLabel}.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(objUrl), 4000);
  } catch (err) {
    console.warn("[BriefModal] 报告下载失败:", err);
  }
};

const onAskFollowup = () => {
  emit("ask-followup", { content: props.content, date: props.briefDate });
};
</script>

<style scoped>
.brief-overlay {
  position: fixed;
  inset: 0;
  background: rgba(28, 25, 23, 0.42);
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
}
.brief-modal {
  width: min(960px, 100%);
  max-height: calc(100vh - 64px);
  background: var(--color-surface, #ffffff);
  border-radius: 4px;
  border: 1px solid var(--color-border, #E5E5DD);
  box-shadow: 0 18px 48px rgba(28, 25, 23, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.brief-header {
  padding: 28px 32px 20px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  background: transparent;
  border-bottom: 1px solid var(--color-border, #E5E5DD);
  position: relative;
}
.brief-header-left { display: flex; align-items: flex-start; gap: 16px; }
.brief-header-icon {
  font-size: 32px;
  color: var(--color-accent, #B45309);
  background: transparent;
  border: 1px solid var(--color-accent, #B45309);
  border-radius: 0;
  padding: 6px;
  box-shadow: none;
  flex-shrink: 0;
}
.brief-eyebrow {
  font-size: 11px;
  letter-spacing: 0.22em;
  font-weight: 700;
  color: var(--color-accent, #B45309);
  text-transform: uppercase;
  margin-bottom: 4px;
  font-family: var(--font-display, "Noto Serif SC", serif);
}
.brief-title {
  font-size: 26px;
  font-weight: 900;
  color: var(--color-text-1, #1c1917);
  margin: 0 0 4px;
  letter-spacing: -0.01em;
  font-family: var(--font-display, "Noto Serif SC", serif);
}
.brief-meta { font-size: 12px; color: var(--color-text-3, #78716c); font-weight: 600; margin: 0; letter-spacing: 0.06em; }
.brief-close {
  background: transparent;
  border: 1px solid var(--color-border, #E5E5DD);
  border-radius: 0;
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  color: var(--color-text-2, #475569);
  transition: border-color 0.18s, color 0.18s;
  flex-shrink: 0;
}
.brief-close:hover { border-color: var(--color-accent, #B45309); color: var(--color-accent, #B45309); }
.brief-close iconify-icon { font-size: 20px; }

.brief-body {
  flex: 1;
  overflow-y: auto;
  padding: 28px 36px;
  scroll-behavior: smooth;
}
.brief-loading {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80px 0; gap: 16px; color: var(--color-text-3, #78716c);
}
.brief-loading-icon { font-size: 48px; color: var(--color-accent, #B45309); animation: brief-spin 1.4s linear infinite; }
@keyframes brief-spin { to { transform: rotate(360deg); } }
.brief-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80px 0; gap: 12px; color: var(--color-text-3, #94a3b8);
}
.brief-empty iconify-icon { font-size: 56px; color: var(--color-text-3, #cbd5e1); }
.brief-empty p { font-size: 15px; font-weight: 700; margin: 0; }
.brief-empty-btn {
  margin-top: 8px;
  background: var(--color-text-1, #1c1917); color: #ffffff;
  border: none; border-radius: 0;
  padding: 10px 22px; font-size: 12px; font-weight: 700;
  letter-spacing: 0.18em; text-transform: uppercase;
  font-family: var(--font-display, "Noto Serif SC", serif);
  cursor: pointer; transition: background 0.18s;
}
.brief-empty-btn:hover { background: var(--color-accent, #B45309); }

.brief-content { font-size: 15px; line-height: 1.85; color: var(--color-text-1, #1e293b); }

/* markdown 样式（编辑部规范，去渐变） */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) { font-weight: 800; color: var(--color-text-1, #1c1917); margin: 18px 0 8px; line-height: 1.4; letter-spacing: -0.01em; font-family: var(--font-display, "Noto Serif SC", serif); }
.markdown-body :deep(h1) { font-size: 22px; }
.markdown-body :deep(h2) { font-size: 19px; padding-bottom: 6px; border-bottom: 1px solid var(--color-border, #E5E5DD); }
.markdown-body :deep(h3) { font-size: 17px; color: var(--color-accent, #B45309); }
.markdown-body :deep(h4) { font-size: 15px; color: var(--color-text-2, #334155); }
.markdown-body :deep(p) { margin: 8px 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 8px 0 8px 4px; padding-left: 22px; }
.markdown-body :deep(li) { margin: 4px 0; line-height: 1.75; }
.markdown-body :deep(li::marker) { color: var(--color-accent, #B45309); font-weight: 800; }
.markdown-body :deep(strong) { color: var(--color-text-1, #0f172a); font-weight: 800; }
.markdown-body :deep(em) { color: var(--color-text-1, #1c1917); font-style: normal; background: transparent; border-bottom: 2px solid var(--color-accent, #B45309); padding: 0; }
.markdown-body :deep(blockquote) { margin: 12px 0; padding: 8px 14px; border-left: 3px solid var(--color-accent, #B45309); background: transparent; border-radius: 0; color: var(--color-text-2, #334155); }
.markdown-body :deep(hr) { border: none; border-top: 1px solid var(--color-border, #E5E5DD); margin: 16px 0; }
.markdown-body :deep(code) { background: var(--color-surface-2, #F5F5F2); padding: 2px 6px; border-radius: 0; font-family: 'Fira Code', monospace; font-size: 13px; color: var(--color-accent, #B45309); border: 1px solid var(--color-border, #E5E5DD); }
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13.5px; }
.markdown-body :deep(th),
.markdown-body :deep(td) { border: 1px solid var(--color-border, #E5E5DD); padding: 7px 10px; }
.markdown-body :deep(th) { background: var(--color-surface-2, #F5F5F2); font-weight: 800; color: var(--color-text-1, #1c1917); text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px; }

.brief-footer {
  padding: 18px 32px 24px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  background: var(--color-surface, #ffffff);
  border-top: 1px solid var(--color-border, #E5E5DD);
}
.brief-action {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 10px 20px;
  font-size: 12px; font-weight: 700;
  letter-spacing: 0.18em; text-transform: uppercase;
  font-family: var(--font-display, "Noto Serif SC", serif);
  border-radius: 0;
  cursor: pointer; transition: background 0.18s, color 0.18s, border-color 0.18s;
  border: 1px solid var(--color-border, #E5E5DD);
}
.brief-action iconify-icon { font-size: 16px; }
.brief-action-secondary {
  background: transparent; color: var(--color-text-2, #475569);
}
.brief-action-secondary:hover { border-color: var(--color-accent, #B45309); color: var(--color-accent, #B45309); }
.brief-action-primary {
  background: var(--color-text-1, #1c1917);
  color: #ffffff;
  border-color: var(--color-text-1, #1c1917);
  box-shadow: none;
}
.brief-action-primary:hover { background: var(--color-accent, #B45309); border-color: var(--color-accent, #B45309); transform: none; box-shadow: none; }

.brief-fade-enter-active,
.brief-fade-leave-active { transition: opacity 0.22s ease; }
.brief-fade-enter-from,
.brief-fade-leave-to { opacity: 0; }
.brief-fade-enter-active .brief-modal,
.brief-fade-leave-active .brief-modal { transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1); }
.brief-fade-enter-from .brief-modal { transform: translateY(20px) scale(0.98); }
</style>

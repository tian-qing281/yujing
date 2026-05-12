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
          <button class="brief-action brief-action-primary" type="button" @click="onExportPdf">
            <iconify-icon icon="ri:file-pdf-line" />
            <span>导出 PDF</span>
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

// PDF：fetch + blob + a.download，不跳页
const onExportPdf = async () => {
  try {
    const url = buildApiUrl("/api/ai/morning_brief/pdf");
    const res = await fetch(url);
    if (!res.ok) throw new Error(`PDF 下载失败 ${res.status}`);
    const blob = await res.blob();
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objUrl;
    a.download = `舆情早报_${props.briefDate || todayLabel}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(objUrl), 4000);
  } catch (err) {
    console.warn("[BriefModal] PDF 下载失败:", err);
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
  background: rgba(15, 23, 42, 0.42);
  backdrop-filter: blur(6px);
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
}
.brief-modal {
  width: min(960px, 100%);
  max-height: calc(100vh - 64px);
  background: #ffffff;
  border-radius: 28px;
  box-shadow: 0 30px 80px -20px rgba(15, 23, 42, 0.4);
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
  background: linear-gradient(135deg, #fef3c7 0%, #fed7aa 50%, #fee2e2 100%);
  position: relative;
}
.brief-header::after {
  content: "";
  position: absolute;
  left: 32px; right: 32px; bottom: 0;
  height: 1px;
  background: rgba(15, 23, 42, 0.08);
}
.brief-header-left { display: flex; align-items: flex-start; gap: 16px; }
.brief-header-icon {
  font-size: 38px;
  color: #ea580c;
  background: #ffffff;
  border-radius: 12px;
  padding: 8px;
  box-shadow: 0 4px 12px rgba(234, 88, 12, 0.18);
  flex-shrink: 0;
}
.brief-eyebrow {
  font-size: 11px;
  letter-spacing: 0.18em;
  font-weight: 800;
  color: rgba(120, 53, 15, 0.7);
  text-transform: uppercase;
  margin-bottom: 4px;
}
.brief-title {
  font-size: 26px;
  font-weight: 900;
  color: #0f172a;
  margin: 0 0 4px;
  letter-spacing: -0.02em;
}
.brief-meta { font-size: 13px; color: #78716c; font-weight: 700; margin: 0; }
.brief-close {
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 10px;
  width: 36px; height: 36px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  color: #475569;
  transition: 0.2s;
  flex-shrink: 0;
}
.brief-close:hover { background: #ffffff; color: #0f172a; transform: rotate(90deg); }
.brief-close iconify-icon { font-size: 20px; }

.brief-body {
  flex: 1;
  overflow-y: auto;
  padding: 28px 36px;
  scroll-behavior: smooth;
}
.brief-loading {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80px 0; gap: 16px; color: #78716c;
}
.brief-loading-icon { font-size: 48px; color: #ea580c; animation: brief-spin 1.4s linear infinite; }
@keyframes brief-spin { to { transform: rotate(360deg); } }
.brief-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80px 0; gap: 12px; color: #94a3b8;
}
.brief-empty iconify-icon { font-size: 56px; color: #cbd5e1; }
.brief-empty p { font-size: 15px; font-weight: 700; margin: 0; }
.brief-empty-btn {
  margin-top: 8px;
  background: #ea580c; color: #ffffff;
  border: none; border-radius: 12px;
  padding: 10px 20px; font-size: 13px; font-weight: 800;
  cursor: pointer; transition: 0.2s;
}
.brief-empty-btn:hover { background: #c2410c; transform: translateY(-1px); }

.brief-content { font-size: 15px; line-height: 1.85; color: #1e293b; }

/* markdown 样式（与 AnalysisModal / AIConsultant 一致） */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) { font-weight: 900; color: #0f172a; margin: 18px 0 8px; line-height: 1.4; letter-spacing: -0.01em; }
.markdown-body :deep(h1) { font-size: 22px; }
.markdown-body :deep(h2) { font-size: 19px; padding-bottom: 6px; border-bottom: 2px solid rgba(234, 88, 12, 0.25); }
.markdown-body :deep(h3) { font-size: 17px; color: #c2410c; }
.markdown-body :deep(h4) { font-size: 15px; color: #334155; }
.markdown-body :deep(p) { margin: 8px 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 8px 0 8px 4px; padding-left: 22px; }
.markdown-body :deep(li) { margin: 4px 0; line-height: 1.75; }
.markdown-body :deep(li::marker) { color: #ea580c; font-weight: 800; }
.markdown-body :deep(strong) { color: #0f172a; font-weight: 900; }
.markdown-body :deep(em) { color: #475569; font-style: normal; background: linear-gradient(180deg, transparent 60%, rgba(254, 215, 170, 0.6) 60%); padding: 0 2px; }
.markdown-body :deep(blockquote) { margin: 12px 0; padding: 10px 14px; border-left: 4px solid #ea580c; background: rgba(234, 88, 12, 0.05); border-radius: 0 10px 10px 0; color: #334155; }
.markdown-body :deep(hr) { border: none; border-top: 1px dashed rgba(148, 163, 184, 0.4); margin: 16px 0; }
.markdown-body :deep(code) { background: rgba(15, 23, 42, 0.06); padding: 2px 6px; border-radius: 4px; font-family: 'Fira Code', monospace; font-size: 13px; color: #be185d; }
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 13.5px; }
.markdown-body :deep(th),
.markdown-body :deep(td) { border: 1px solid rgba(148, 163, 184, 0.28); padding: 7px 10px; }
.markdown-body :deep(th) { background: rgba(234, 88, 12, 0.08); font-weight: 800; color: #c2410c; }

.brief-footer {
  padding: 18px 32px 24px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  background: #ffffff;
  border-top: 1px solid rgba(15, 23, 42, 0.06);
}
.brief-action {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 10px 18px;
  font-size: 13px; font-weight: 800;
  border-radius: 12px;
  cursor: pointer; transition: 0.2s;
  border: 1px solid transparent;
}
.brief-action iconify-icon { font-size: 16px; }
.brief-action-secondary {
  background: #f1f5f9; color: #475569; border-color: rgba(148, 163, 184, 0.2);
}
.brief-action-secondary:hover { background: #e2e8f0; color: #0f172a; }
.brief-action-primary {
  background: linear-gradient(135deg, #ea580c, #dc2626);
  color: #ffffff;
  box-shadow: 0 6px 18px -6px rgba(234, 88, 12, 0.5);
}
.brief-action-primary:hover { transform: translateY(-1px); box-shadow: 0 10px 22px -8px rgba(234, 88, 12, 0.6); }

.brief-fade-enter-active,
.brief-fade-leave-active { transition: opacity 0.22s ease; }
.brief-fade-enter-from,
.brief-fade-leave-to { opacity: 0; }
.brief-fade-enter-active .brief-modal,
.brief-fade-leave-active .brief-modal { transition: transform 0.28s cubic-bezier(0.16, 1, 0.3, 1); }
.brief-fade-enter-from .brief-modal { transform: translateY(20px) scale(0.96); }
</style>

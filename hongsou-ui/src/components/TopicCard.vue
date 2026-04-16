<template>
  <article class="topic-card" @click="$emit('click')">
    <div class="topic-head">
      <div class="topic-head-main">
        <span class="topic-kicker">{{ item.confidence === "stable" ? "重点脉络" : "观察脉络" }}</span>
        <span class="topic-confidence" :class="item.confidence">{{ item.confidence_label }}</span>
      </div>
      <span class="topic-meta">{{ item.platform_count }} 平台 · {{ item.event_count }} 事件</span>
    </div>

    <div class="topic-main">
      <h3 class="topic-title" v-html="highlight(item.title)"></h3>
      <p class="topic-summary" v-html="highlight(item.summary || '查看关联事件。')"></p>
    </div>

    <div v-if="traceLabel" class="topic-trace">
      <span class="trace-dot"></span>
      <span>{{ traceLabel }}</span>
    </div>

    <div v-if="matchReasons.length" class="topic-reasons">
      <span class="reason-label">命中原因</span>
      <span v-for="reason in matchReasons" :key="reason" class="reason-chip">{{ reason }}</span>
    </div>

  </article>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  item: { type: Object, required: true },
  query: { type: String, default: "" },
});

defineEmits(["click"]);

const keywordPreview = computed(() => (Array.isArray(props.item.keywords) ? props.item.keywords.slice(0, 3) : []));

const traceLabel = computed(() => {
  const time = formatTime(props.item.latest_event_time);
  return time ? `最近主题更新 · ${time}` : "";
});
const matchReasons = computed(() => Array.isArray(props.item.match_reasons) ? props.item.match_reasons.slice(0, 3) : []);

const escapeHtml = (value) =>
  String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");

const escapeRegex = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const formatTime = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hour = `${date.getHours()}`.padStart(2, "0");
  const minute = `${date.getMinutes()}`.padStart(2, "0");
  return `${month}-${day} ${hour}:${minute}`;
};

const highlight = (value) => {
  const text = escapeHtml(value || "");
  const query = (props.query || "").trim();
  if (!query) return text;

  const tokens = Array.from(
    new Set(
      [query, ...query.split(/\s+/)]
        .map((item) => item.trim())
        .filter((item) => item && item.length >= 1)
        .sort((a, b) => b.length - a.length)
    )
  );

  if (!tokens.length) return text;
  const pattern = new RegExp(`(${tokens.map(escapeRegex).join("|")})`, "gi");
  return text.replace(pattern, '<mark class="topic-hit">$1</mark>');
};
</script>

<style scoped>
.topic-card {
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border-radius: 24px;
  padding: 24px;
  border: 1px solid rgba(226, 232, 240, 0.95);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.05);
  display: flex;
  flex-direction: column;
  gap: 18px;
  cursor: pointer;
  transition: transform 0.24s ease, box-shadow 0.24s ease, border-color 0.24s ease;
  min-height: 228px;
}

.topic-card:hover {
  transform: translateY(-4px);
  border-color: rgba(148, 163, 184, 0.36);
  box-shadow: 0 22px 46px rgba(15, 23, 42, 0.09);
}

.topic-head,
.topic-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.topic-head-main {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.topic-kicker {
  color: #2563eb;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.topic-meta {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.topic-confidence {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  background: #f8fafc;
  color: #475569;
}

.topic-confidence.weak {
  background: #fff7ed;
  color: #c2410c;
}

.topic-confidence.emerging {
  background: #eff6ff;
  color: #1d4ed8;
}

.topic-confidence.stable {
  background: #ecfdf5;
  color: #047857;
}

.topic-main {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.topic-title {
  font-size: 24px;
  line-height: 1.18;
  letter-spacing: -0.04em;
  font-weight: 900;
  color: #0f172a;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.topic-summary {
  color: #475569;
  font-size: 14px;
  line-height: 1.75;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.topic-foot {
  justify-content: flex-start;
}

.topic-trace {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.trace-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #93c5fd;
}

.topic-reasons {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.reason-label {
  color: #94a3b8;
  font-size: 11px;
  font-weight: 800;
}

.reason-chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
}

.topic-chip {
  display: inline-flex;
  align-items: center;
  padding: 7px 11px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
}

:deep(.topic-hit) {
  background: linear-gradient(180deg, rgba(254, 240, 138, 0.18) 0%, rgba(253, 224, 71, 0.36) 100%);
  color: #92400e;
  border-radius: 6px;
  padding: 0 2px;
}

@media (max-width: 960px) {
  .topic-card {
    min-height: 200px;
    padding: 20px;
  }

  .topic-title {
    font-size: 21px;
  }
}
</style>

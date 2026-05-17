<script setup>
defineProps({
  currentSourceName: String,
  currentSourceIcon: String,
  loading: Boolean,
  modeLabel: {
    type: String,
    default: "实时热榜",
  },
})
defineEmits(['refresh'])
</script>

<template>
  <header class="app-header navbar hs-panel">
    <div class="header-left">
      <div class="header-copy">
        <span v-if="modeLabel && modeLabel !== '实时热榜'" class="header-kicker badge badge-ghost">{{ modeLabel }}</span>
        <div class="breadcrumb">
          <iconify-icon v-if="currentSourceIcon" :icon="currentSourceIcon" class="breadcrumb-icon" />
          <span class="root-node">{{ currentSourceName || '数据加载中' }}</span>
        </div>
      </div>
    </div>
    
    <div class="header-right">
      <button class="btn btn-primary btn-sm rounded-full btn-sync-all" @click="$emit('refresh')" :disabled="loading">
        <iconify-icon icon="mdi:reload" :class="{ 'anim-spin': loading }" />
        <span>{{ loading ? '数据同步中' : '全站同步' }}</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.app-header { 
  height: 80px;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between; 
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(24px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  position: sticky; top: 0; z-index: 100;
  border-radius: 0;
}

.app-header::after {
  content: "";
  position: absolute;
  left: 40px;
  right: 40px;
  bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, rgba(148, 163, 184, 0) 0%, rgba(203, 213, 225, 0.9) 12%, rgba(203, 213, 225, 0.9) 88%, rgba(148, 163, 184, 0) 100%);
}

.header-left { display: flex; align-items: center; gap: 24px; min-width: 0; flex: 1 1 auto; overflow: hidden; }
.header-copy { display: flex; flex-direction: column; gap: 0; min-width: 0; }
.header-kicker { font-size: 11px; font-weight: 800; letter-spacing: 0.04em; transform: scale(0.9); transform-origin: left; color: #64748b; background: transparent; border: none; margin-bottom: -2px; white-space: nowrap; }
.breadcrumb { display: flex; align-items: center; gap: 12px; font-size: 22px; font-weight: 900; color: #0f172a; letter-spacing: -0.02em; min-width: 0; overflow: hidden; }
.breadcrumb-icon { font-size: 24px; color: var(--color-accent, #B45309); display: flex; align-items: center; flex-shrink: 0; }
.root-node { color: #020617; line-height: 1; display: flex; align-items: center; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.header-right { display: flex; align-items: center; gap: 24px; flex-shrink: 0; }
.btn-sync-all { 
  /* 主按钮：近墨石板底 + 暖白文字，去蓝阴影 */
  background: var(--color-brand, #0F172A);
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.06);
  height: 48px;
  padding: 0 24px; 
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  display: flex; 
  align-items: center; gap: 12px; cursor: pointer; transition: 0.2s;
  box-shadow: 0 4px 12px rgba(20, 16, 8, 0.08);
  text-transform: none;
}
.btn-sync-all:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 20px rgba(20, 16, 8, 0.12); }
.btn-sync-all:disabled { opacity: 0.5; cursor: not-allowed; }

@media (max-width: 960px) {
  .app-header {
    height: 76px;
    padding: 0 20px;
  }

  .breadcrumb {
    font-size: 18px;
  }
}

/* 窄屏：让"全站同步"按钮收缩为图标态，避免与左侧标题重叠 */
@media (max-width: 768px) {
  .header-left { gap: 12px; }
  .header-right { gap: 12px; }
  .btn-sync-all {
    height: 40px;
    padding: 0 14px;
    font-size: 12px;
    gap: 6px;
  }
  .btn-sync-all span { display: none; }
}

.anim-spin { animation: spin 1s infinite linear; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>

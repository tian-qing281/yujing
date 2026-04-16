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

.header-left { display: flex; align-items: center; gap: 24px; }
.header-copy { display: flex; flex-direction: column; gap: 0; }
.header-kicker { font-size: 11px; font-weight: 800; letter-spacing: 0.04em; transform: scale(0.9); transform-origin: left; color: #64748b; background: transparent; border: none; margin-bottom: -2px; }
.breadcrumb { display: flex; align-items: center; gap: 12px; font-size: 22px; font-weight: 900; color: #0f172a; letter-spacing: -0.02em; }
.breadcrumb-icon { font-size: 24px; color: var(--hs-primary, #1e40af); display: flex; align-items: center; }
.root-node { color: #020617; line-height: 1; display: flex; align-items: center; }

.header-right { display: flex; align-items: center; gap: 24px; }
.btn-sync-all { 
  background: var(--hs-primary, #2563eb);
  color: #ffffff;
  border: 1px solid rgba(255, 255, 255, 0.1);
  height: 48px;
  padding: 0 24px; 
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  display: flex; 
  align-items: center; gap: 12px; cursor: pointer; transition: 0.2s;
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.2);
  text-transform: none;
}
.btn-sync-all:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 12px 32px rgba(37, 99, 235, 0.3); }
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

.anim-spin { animation: spin 1s infinite linear; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
</style>

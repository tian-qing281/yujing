<template>
  <aside :class="['app-sidebar', 'drawer-side', { collapsed: isCollapsed }]">
    <div class="sidebar-top">
      <button
        class="sidebar-toggle btn btn-ghost"
        type="button"
        @click="isCollapsed = !isCollapsed"
        :aria-label="isCollapsed ? '展开侧栏' : '收起侧栏'"
      >
        <iconify-icon :icon="isCollapsed ? 'mdi:chevron-right' : 'mdi:chevron-left'"></iconify-icon>
      </button>

      <div class="brand-box">
        <span v-if="!isCollapsed" class="brand-kicker">YU JING</span>
        <h1 class="logo">舆镜</h1>
      </div>
    </div>

    <nav class="sidebar-nav" aria-label="数据源导航">
      <ul class="menu menu-lg sidebar-menu">
        <li v-for="source in sourceRegistry" :key="source.id">
          <button
            type="button"
            class="nav-item btn btn-ghost"
            :class="{ active: currentSource === source.id }"
            :title="source.name"
            @click="$emit('switch', source.id)"
          >
            <span class="nav-mark"></span>
            <iconify-icon :icon="source.icon" class="nav-icon"></iconify-icon>
            <span v-if="!isCollapsed" class="nav-label">{{ source.name }}</span>
          </button>
        </li>
      </ul>
    </nav>

    <div class="sidebar-footer">
      <button class="btn-sidebar-asset btn btn-outline btn-primary" type="button" @click="$emit('open-cred')">
        <iconify-icon icon="mdi:shield-key-outline"></iconify-icon>
        <span v-if="!isCollapsed">凭据资产配置</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  sourceRegistry: { type: Array, default: () => [] },
  currentSource: { type: String, default: "" },
  syncTime: { type: String, default: "" },
  syncAt: { type: [Number, String, Date, null], default: null },
});

const isCollapsed = ref(false);

defineEmits(["switch", "open-cred"]);
</script>

<style scoped>
.app-sidebar {
  width: 300px;
  height: 100vh;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  font-family: "Fira Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg-sidebar, #0f172a);
  color: #ffffff;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  transition: width 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

.app-sidebar::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.04) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.88), transparent 86%);
}

.app-sidebar.collapsed {
  width: 80px;
}

.sidebar-top {
  padding: 20px 20px 10px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.sidebar-toggle {
  width: 40px;
  height: 40px;
  min-height: 40px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  color: #f8fbff;
}

.sidebar-toggle:hover {
  background: rgba(59, 130, 246, 0.14);
  border-color: rgba(147, 197, 253, 0.28);
  transform: translateY(-1px);
}

.brand-box {
  padding: 4px 2px;
}

.app-sidebar.collapsed .brand-box {
  max-width: none;
  display: flex;
  justify-content: center;
}

.brand-kicker {
  display: inline-block;
  font-size: 20px;
  font-weight: 800;
  letter-spacing: 0.18em;
  color: #7dd3fc;
}

.logo {
  margin: 6px 0 0;
  font-size: 42px;
  line-height: 1;
  font-weight: 900;
  letter-spacing: 0.02em;
  color: #f8fbff;
  filter: drop-shadow(0 4px 12px rgba(59, 130, 246, 0.12));
}

.app-sidebar.collapsed .logo {
  margin: 0;
  font-size: 30px;
}

.sidebar-nav {
  flex: 1;
  padding: 16px 16px 0;
  position: relative;
  z-index: 1;
  overflow-y: auto;
}

.app-sidebar.collapsed .sidebar-nav {
  padding-left: 12px;
  padding-right: 12px;
}

.sidebar-menu {
  width: 100%;
  gap: 8px;
  padding: 0;
  background: transparent;
}

.sidebar-menu li {
  width: 100%;
}

.nav-item {
  width: 100%;
  min-height: 52px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 16px;
  padding: 10px 18px;
  border-radius: 14px;
  color: #94a3b8;
  text-align: left;
  line-height: 1;
  text-transform: none;
  transition: all 0.2s ease;
}

.app-sidebar.collapsed .nav-item {
  justify-content: center;
  padding: 10px;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #ffffff;
}

.nav-item.active {
  background: var(--hs-primary, #2563eb);
  color: #ffffff;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.25);
}

.nav-mark {
  width: 4px;
  height: 18px;
  border-radius: 999px;
  background: transparent;
  transition: background 0.2s ease;
}

.app-sidebar.collapsed .nav-mark {
  display: none;
}

.nav-item.active .nav-mark {
  background: #ffffff;
}

.nav-icon {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
  opacity: 0.98;
}

.nav-label {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.sidebar-footer {
  position: relative;
  z-index: 1;
  margin-top: auto;
  padding: 18px 20px 22px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.app-sidebar.collapsed .sidebar-footer {
  padding-left: 12px;
  padding-right: 12px;
}

.btn-sidebar-asset {
  width: 100%;
  height: 44px;
  min-height: 44px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 700;
  text-transform: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  letter-spacing: 0.08em;
  padding: 0 16px;
}

.btn-sidebar-asset:hover {
  background: rgba(37, 99, 235, 0.18);
  border-color: rgba(147, 197, 253, 0.34);
  transform: translateY(-1px);
}

.app-sidebar.collapsed .btn-sidebar-asset {
  justify-content: center;
}

.sidebar-nav::-webkit-scrollbar {
  width: 6px;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.18);
  border-radius: 999px;
}
</style>

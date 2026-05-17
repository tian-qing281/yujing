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
      <!-- 平台热榜分组：可折叠（仅在侧栏未收起时显示分组头） -->
      <div class="nav-group" :class="{ open: hotOpen || isCollapsed }">
        <button
          v-if="!isCollapsed"
          type="button"
          class="nav-group-header"
          :aria-expanded="hotOpen"
          @click="hotOpen = !hotOpen"
        >
          <iconify-icon icon="ri:fire-fill" class="nav-group-icon"></iconify-icon>
          <span class="nav-group-label">平台热榜</span>
          <span class="nav-group-count">{{ hotSources.length }}</span>
          <iconify-icon
            icon="mdi:chevron-right"
            class="nav-group-chevron"
            :class="{ rotated: hotOpen }"
          ></iconify-icon>
        </button>

        <div class="nav-group-body" :class="{ collapsed: !hotOpen && !isCollapsed }">
          <ul class="menu menu-lg sidebar-menu">
            <li v-for="source in hotSources" :key="source.id">
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
        </div>
      </div>

      <!-- 工具入口：常驻可见，不折叠 -->
      <ul class="menu menu-lg sidebar-menu sidebar-menu-tools">
        <li v-for="source in toolSources" :key="source.id">
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
import { ref, computed, watch } from "vue";

const props = defineProps({
  sourceRegistry: { type: Array, default: () => [] },
  currentSource: { type: String, default: "" },
  syncTime: { type: String, default: "" },
  syncAt: { type: [Number, String, Date, null], default: null },
});

const isCollapsed = ref(false);

// 工具入口 ID 白名单：这些常驻可见，不计入"平台热榜"分组
const TOOL_IDS = new Set(["event_hub", "ai_consultant", "my_subscriptions"]);

const hotSources = computed(() =>
  props.sourceRegistry.filter((s) => !TOOL_IDS.has(s.id))
);
const toolSources = computed(() =>
  props.sourceRegistry.filter((s) => TOOL_IDS.has(s.id))
);

// 默认折叠平台热榜分组（每次进入页面保持收起状态，更清爽）
// 仅当用户切到其他源后又切回热榜时，才自动展开，避免初次访问的视觉拥挤
const isHotActive = computed(() =>
  hotSources.value.some((s) => s.id === props.currentSource)
);
const hotOpen = ref(false);
watch(isHotActive, (active) => {
  if (active) hotOpen.value = true;
});

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
  /* editorial: kicker + 主名整体居中，呈刊头规整感 */
  text-align: center;
}

.app-sidebar.collapsed .brand-box {
  max-width: none;
  display: flex;
  justify-content: center;
}

.brand-kicker {
  display: inline-block;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.32em;
  /* editorial: 赤陶红 kicker 者，取代亮蓝 */
  color: var(--color-accent);
  text-transform: uppercase;
}

.logo {
  margin: 8px 0 0;
  font-size: 38px;
  line-height: 1;
  font-weight: 800;
  letter-spacing: 0.04em;
  /* editorial: 使用衰宋作刷头，去揉蓝光晕 */
  font-family: var(--font-display, "Noto Serif SC", serif);
  color: #FAFAF7;
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
  /* Batch VI · 选中态视觉强化：
     - 底色加重到 0.12（与 hover 0.08 拉开层级）
     - 左侧 3px 实线 accent + 描边 1px accent 30% 不透明（细勾边突出选中）
     - 文字加粗到 600，与未选中 400 形成字重对比
     - letter-spacing 收紧 -0.01em，匹配 Batch III 全局排版基线 */
  background: rgba(255, 255, 255, 0.12);
  color: #ffffff;
  font-weight: 600;
  letter-spacing: -0.01em;
  box-shadow:
    inset 3px 0 0 var(--color-accent, #B45309),
    inset 0 0 0 1px rgba(180, 83, 9, 0.3);
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
  background: var(--color-accent, #B45309);
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

/* === 分组折叠（平台热榜） === */
.nav-group {
  margin-bottom: 12px;
}

.nav-group-header {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px 8px 12px;
  background: transparent;
  border: 0;
  border-radius: 10px;
  color: rgba(226, 232, 240, 0.7);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav-group-header:hover {
  background: rgba(255, 255, 255, 0.04);
  color: #ffffff;
}

.nav-group-icon {
  font-size: 14px;
  color: var(--color-accent, #b45309);
  flex-shrink: 0;
}

.nav-group-label {
  flex: 1;
  text-align: left;
}

.nav-group-count {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
  color: rgba(226, 232, 240, 0.55);
  background: rgba(255, 255, 255, 0.06);
  border-radius: 999px;
  padding: 1px 8px;
  min-width: 22px;
  text-align: center;
}

.nav-group-chevron {
  font-size: 16px;
  color: rgba(226, 232, 240, 0.55);
  transform: rotate(0deg);
  transform-origin: center;
  transition: transform 280ms cubic-bezier(0.2, 0.8, 0.2, 1),
              color 180ms ease;
}

.nav-group-chevron.rotated {
  transform: rotate(90deg);
  color: rgba(226, 232, 240, 0.85);
}

.nav-group-body {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows 280ms cubic-bezier(0.2, 0.8, 0.2, 1),
              opacity 220ms cubic-bezier(0.2, 0.8, 0.2, 1);
  opacity: 1;
  overflow: hidden;
  will-change: grid-template-rows, opacity;
}

.nav-group-body.collapsed {
  grid-template-rows: 0fr;
  opacity: 0;
  pointer-events: none;
}

.nav-group-body > .sidebar-menu {
  min-height: 0;
  overflow: hidden;
}

/* 收起态：隐藏分组头，菜单恢复直挂 */
.app-sidebar.collapsed .nav-group-header {
  display: none;
}

.app-sidebar.collapsed .nav-group {
  margin-bottom: 8px;
}

.sidebar-menu-tools {
  margin-top: 6px;
  padding-top: 10px;
  border-top: 1px dashed rgba(255, 255, 255, 0.06);
}
</style>

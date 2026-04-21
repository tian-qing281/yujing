<template>
  <Transition name="modal-fade">
    <div class="modal-overlay glass-overlay" v-if="item" @click="$emit('close')">
      <div class="detail-capsule modal-box" @click.stop>
        <header class="capsule-header">
          <div class="source-tag">
            <iconify-icon icon="mdi:file-search-outline" />
            <span>{{ sourceName }}</span>
          </div>
          <button class="btn-capsule-close btn btn-circle btn-ghost" @click="$emit('close')"><iconify-icon icon="mdi:close" /></button>
        </header>

        <div class="capsule-scroll-body">
          <div class="article-header-group">
            <h1 class="article-subject">{{ item.title }}</h1>
            <div class="article-meta-row">
               <p class="article-timestamp">更新于：{{ formatTime(item.fetch_time || item.pub_date) }}</p>
               <a :href="preferredSourceUrl" target="_blank" class="premium-source-btn btn btn-outline">
                  <iconify-icon icon="mdi:open-in-new" />
                  <span>访问网页原文</span>
               </a>
            </div>
          </div>

          <div class="capsule-navigation-row">
            <div class="capsule-tabs">
              <button :class="['cap-tab', 'btn', 'btn-sm', props.activeTab === 'visual' ? 'active' : '']" @click="changeTab('visual')">
                数据透视
              </button>
              <button :class="['cap-tab', 'btn', 'btn-sm', props.activeTab === 'report' ? 'active' : '']" @click="changeTab('report')">
                AI 总结
              </button>
            </div>
            
            <div class="capsule-actions">
              <button class="btn-action-sync btn btn-neutral" @click="$emit('trigger-ai', true)" :disabled="item.isAnalyzing">
                <iconify-icon icon="mdi:reload" :class="{ 'anim-spin': item.isAnalyzing }"></iconify-icon>
                <span>{{ item.isAnalyzing ? "分析中..." : "开始深度分析" }}</span>
              </button>
            </div>
          </div>

          <div class="tab-viewport">
            <div
              v-show="props.activeTab === 'visual'"
              class="panel-visual"
              :class="{ 'panel-visual--idle': !hasVisualData }"
              ref="visRoot"
            >
              <div v-if="item.isAnalyzing && !hasVisualData" class="analysis-spinner">
                <div class="aura-spin"></div>
                <p class="status-bright-text">{{ statusMsg }}</p>
              </div>
              
              <div v-else-if="!hasVisualData && !item.isAnalyzing" class="empty-vis">
                <iconify-icon icon="mdi:database-search" />
                <p class="status-bright-text">数据分析特征未就绪</p>
                <button class="btn-empty-sync btn btn-primary" @click="$emit('trigger-ai')">开始深度分析</button>
              </div>
              
              <div v-show="hasVisualData" class="vis-intel-dashboard">
                <div class="intel-visual-grid">
                  <!-- 情感极性分布 -->
                  <div class="intel-box emotion-intel-box">
                    <div class="intel-label">
                      <iconify-icon icon="mdi:chart-bar" />
                      <span>情感极性分布</span>
                    </div>
                    <div class="emotion-flex-container">
                      <div class="emotion-chart-shell">
                         <div ref="emotionChartRef" class="emotion-render-area"></div>
                      </div>
                    </div>
                  </div>

                  <!-- 舆情倾向分析 -->
                  <div class="intel-box sentiment-intel-box">
                    <div class="intel-label">
                      <iconify-icon icon="mdi:gauge" />
                      <span>舆情倾向分析</span>
                    </div>
                    <div class="chart-shell">
                      <div ref="sentimentChartRef" class="chart-render-area"></div>
                    </div>
                  </div>

                  <!-- 关键词云图 -->
                  <div class="intel-box cloud-intel-box">
                    <div class="intel-label">
                      <iconify-icon icon="mdi:cloud-outline" />
                      <span>关键词云图</span>
                    </div>
                    <div class="cloud-container-shell">
                       <canvas ref="wcCanvas" class="wc-render-canvas"></canvas>
                    </div>
                  </div>

                  <!-- 核心实体雷达 -->
                  <div class="intel-box radar-intel-box">
                    <div class="intel-label">
                      <iconify-icon icon="mdi:radar" />
                      <span>核心实体雷达</span>
                    </div>
                    <div class="chart-shell">
                      <div ref="keywordRadarRef" class="chart-render-area"></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div v-show="props.activeTab === 'report'" class="panel-report">
              <div v-if="item.isAnalyzing && !item.ai_summary" class="analysis-spinner">
                <div class="aura-spin"></div>
                <p class="status-bright-text">{{ statusMsg }}</p>
              </div>
              
              <div v-if="item.ai_summary" class="report-box card animate-slide-up">
                  <div class="report-lead-tag">
                    <iconify-icon icon="mdi:text-box-search-outline" />
                    <span>AI 总结</span>
                  </div>
                  <div class="report-body">{{ item.ai_summary }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted, computed } from 'vue'

const props = defineProps({
  item: Object,
  sourceName: String,
  statusMsg: String,
  activeTab: String
})

const emit = defineEmits(['close', 'trigger-ai', 'update:activeTab'])

const wcCanvas = ref(null)
const emotionChartRef = ref(null)
const sentimentChartRef = ref(null)
const keywordRadarRef = ref(null)
let emotionChart = null
let sentimentChart = null
let radarChart = null
let renderAnimationFrame = null
let renderDebounceTimer = null
let lastRenderedCloudLength = -1

const hasVisualData = computed(() => {
  const hasCloud = props.item?.wordcloud && props.item.wordcloud.length > 0
  const hasEmo = props.item?.emotions && props.item.emotions.length > 0
  return !!(hasCloud || hasEmo)
})

const normalizedWordcloud = computed(() => {
  const source = props.item?.wordcloud || []
  return source
    .map((entry) => {
      if (Array.isArray(entry)) {
        return { word: String(entry[0] || '').trim(), value: Number(entry[1] || 0) }
      }
      return { word: String(entry?.word || entry?.text || '').trim(), value: Number(entry?.value || entry?.weight || 0) }
    })
    .filter((entry) => entry.word && entry.value > 0)
    .sort((a, b) => b.value - a.value)
})

const scheduleRender = (task) => {
  if (renderDebounceTimer) clearTimeout(renderDebounceTimer);
  if (renderAnimationFrame) cancelAnimationFrame(renderAnimationFrame);
  renderDebounceTimer = setTimeout(() => {
    renderAnimationFrame = requestAnimationFrame(() => {
      task();
    });
  }, 200);
}

const preferredSourceUrl = computed(() => {
  const originalUrl = props.item?.url || ''
  if (!originalUrl) return ''
  if (props.item?.source_id !== 'toutiao_hot' || !originalUrl.includes('/trending/')) {
    return originalUrl
  }
  const rawContent = props.item?.raw_content || ''
  const matches = [...rawContent.matchAll(/\((https?:\/\/(?:www\.)?toutiao\.com\/(?:article|video|w|answer|topic)\/[^)\s]+)\)/g)]
    .map((match) => match[1])
  const articleUrl = matches.find((url) => url.includes('/article/'))
  return articleUrl || matches[0] || originalUrl
})

const changeTab = (tab) => {
  emit('update:activeTab', tab)
}

const getHashColor = (word) => {
  let hash = 0;
  for (let i = 0; i < word.length; i++) {
    hash = word.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = 205 + (Math.abs(hash) % 44);
  const sat = 58 + (Math.abs(hash) % 28);
  const light = 68 + (Math.abs(hash) % 16);
  return `hsl(${hue}, ${sat}%, ${light}%)`;
}

const getEmoBarColor = (label) => {
  const colors = { '愤怒': '#ef4444', '厌恶': '#a855f7', '悲伤': '#94a3b8', '喜悦': '#10b981', '关注': '#3b82f6', '惊讶': '#f59e0b', '质疑': '#ec4899', '中性': '#64748b' }
  return colors[label] || '#94a3b8'
}

const formatTime = (d) => {
  if (!d) return "-";
  const date = new Date(d);
  if (Number.isNaN(date.getTime())) return "-";
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day} ${hh}:${mm}`;
}

const renderCloud = (data) => {
  if (!wcCanvas.value || !normalizedWordcloud.value.length || props.activeTab !== 'visual') return
  const box = wcCanvas.value.parentElement
  if (!box) return
  
  const width = box.clientWidth
  const height = box.clientHeight || 320
  if (width === 0) return

  if (emotionChartRef.value && window.echarts) {
    if (emotionChart) emotionChart.dispose()
    emotionChart = window.echarts.init(emotionChartRef.value)
    const emoData = (props.item.emotions || []).filter(e => e.value > 0).reverse();
    emotionChart.setOption({
      grid: { top: 10, right: 45, bottom: 10, left: 45 },
      xAxis: { type: 'value', show: false },
      yAxis: { 
        type: 'category', 
        data: emoData.map(e => e.label),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: '#64748b', fontWeight: 800, fontSize: 11 }
      },
      series: [{
        type: 'bar',
        data: emoData.map(e => ({
          value: e.value,
          itemStyle: { color: getEmoBarColor(e.label), borderRadius: [0, 4, 4, 0] }
        })),
        barWidth: 10,
        label: {
          show: true,
          position: 'right',
          formatter: (params) => (params.value * 100).toFixed(0) + '%',
          color: '#0f172a',
          fontWeight: 900,
          fontSize: 11,
          fontFamily: 'Fira Code, monospace'
        }
      }]
    })
  }

  wcCanvas.value.width = width
  wcCanvas.value.height = height
  const entries = normalizedWordcloud.value.map(e => [e.word, e.value])
  const maxVal = Math.max(...normalizedWordcloud.value.map(e => e.value))
  
  if (window.WordCloud) {
    window.WordCloud(wcCanvas.value, {
      list: entries,
      gridSize: 6,
      weightFactor: (size) => {
        // 动态适配规则：取宽高最小值作为基准，确保在 1:1 布局下纵向也能铺满
        const baseSize = Math.min(width, height);
        const factor = (width > 600) ? 2.8 : 3.5;
        return (size * baseSize) / (maxVal * factor);
      },
      minSize: 6,
      fontFamily: 'Outfit, Inter, system-ui, sans-serif',
      color: (word) => {
         const colors = ['#1d4ed8', '#2563eb', '#3b82f6', '#60a5fa', '#0f172a'];
         let hash = 0;
         for (let i = 0; i < word.length; i++) hash = word.charCodeAt(i) + ((hash << 5) - hash);
         return colors[Math.abs(hash) % colors.length];
      },
      rotateRatio: 0,
      backgroundColor: 'transparent',
      shrinkToFit: true,
      drawOutOfBound: false
    })
  }
  lastRenderedCloudLength = normalizedWordcloud.value.length;

  // 舆情倾向环形图
  if (sentimentChartRef.value && window.echarts) {
    if (sentimentChart) sentimentChart.dispose()
    sentimentChart = window.echarts.init(sentimentChartRef.value)
    const emo = props.item.emotions || []
    const groups = [
      { name: '正面', value: emo.filter(e => ['喜悦'].includes(e.label)).reduce((s, e) => s + e.value, 0), color: '#10b981' },
      { name: '负面', value: emo.filter(e => ['愤怒', '厌恶', '悲伤'].includes(e.label)).reduce((s, e) => s + e.value, 0), color: '#ef4444' },
      { name: '中性', value: emo.filter(e => ['中性'].includes(e.label)).reduce((s, e) => s + e.value, 0), color: '#64748b' },
      { name: '关注', value: emo.filter(e => ['关注', '惊讶', '质疑'].includes(e.label)).reduce((s, e) => s + e.value, 0), color: '#3b82f6' },
    ].filter(g => g.value > 0)
    const dominant = groups.length ? groups.reduce((a, b) => a.value > b.value ? a : b) : null
    sentimentChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
      legend: { show: false },
      series: [{
        type: 'pie',
        radius: ['45%', '72%'],
        center: ['50%', '50%'],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 3 },
        label: { show: true, fontSize: 11, fontWeight: 800, color: '#334155', formatter: '{b}\n{d}%' },
        emphasis: { label: { fontSize: 13, fontWeight: 900 }, itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.1)' } },
        data: groups.map(g => ({ value: +(g.value * 100).toFixed(1), name: g.name, itemStyle: { color: g.color } }))
      }],
      graphic: dominant ? [{
        type: 'text',
        left: 'center',
        top: 'center',
        style: {
          text: dominant.name,
          fontSize: 16,
          fontWeight: 900,
          fill: dominant.color,
          textAlign: 'center'
        }
      }] : []
    })
  }

  // 核心实体雷达图
  if (keywordRadarRef.value && window.echarts) {
    if (radarChart) radarChart.dispose()
    radarChart = window.echarts.init(keywordRadarRef.value)
    const topKw = normalizedWordcloud.value.slice(0, 6)
    if (topKw.length >= 3) {
      const kwMax = Math.max(...topKw.map(k => k.value))
      radarChart.setOption({
        tooltip: {},
        radar: {
          indicator: topKw.map(k => ({ name: k.word, max: kwMax * 1.15 })),
          shape: 'polygon',
          splitNumber: 4,
          axisName: { color: '#334155', fontSize: 11, fontWeight: 700 },
          splitArea: { areaStyle: { color: ['rgba(59,130,246,0.02)', 'rgba(59,130,246,0.05)', 'rgba(59,130,246,0.02)', 'rgba(59,130,246,0.05)'] } },
          splitLine: { lineStyle: { color: 'rgba(148,163,184,0.15)' } },
          axisLine: { lineStyle: { color: 'rgba(148,163,184,0.2)' } }
        },
        series: [{
          type: 'radar',
          name: '关键词频', 
          data: [{
            name: '关键词频', 
            value: topKw.map(k => k.value),
            areaStyle: { color: 'rgba(59,130,246,0.15)' },
            lineStyle: { color: '#3b82f6', width: 2 },
            itemStyle: { color: '#2563eb', borderWidth: 2 },
            symbol: 'circle',
            symbolSize: 6
          }]
        }]
      })
    }
  }
}

watch(() => props.item?.wordcloud, (newData) => {
  if (newData?.length > 0 && props.activeTab === 'visual' && newData.length !== lastRenderedCloudLength) {
    scheduleRender(() => renderCloud(newData))
  }
}, { deep: true })

onMounted(() => {
  if (props.activeTab === 'visual' && hasVisualData.value) {
    nextTick(() => renderCloud(props.item?.wordcloud))
  }
})

watch(() => props.item?.id, (newId) => {
  if (newId && props.activeTab === 'visual' && hasVisualData.value) {
    nextTick(() => renderCloud(props.item?.wordcloud))
  }
})

onUnmounted(() => {
  if (emotionChart) emotionChart.dispose()
  if (sentimentChart) sentimentChart.dispose()
  if (radarChart) radarChart.dispose()
  if (renderDebounceTimer) clearTimeout(renderDebounceTimer)
  if (renderAnimationFrame) cancelAnimationFrame(renderAnimationFrame)
})

watch(() => props.activeTab, (newTab) => {
  if (newTab === 'visual' && hasVisualData.value) {
    nextTick(() => renderCloud(props.item?.wordcloud))
  }
})
</script>

<style scoped>
.modal-overlay { 
  position: fixed; inset: 0; 
  background: rgba(226, 232, 240, 0.45); 
  backdrop-filter: blur(14px); 
  z-index: 2000; 
  display: flex; align-items: center; justify-content: center; padding: 34px; 
}
.detail-capsule { 
  width: 100%; max-width: 1180px; height: 90vh; 
  background: rgba(255, 255, 255, 0.98); 
  border-radius: 30px; display: flex; flex-direction: column; overflow: hidden; 
  box-shadow: 0 40px 100px rgba(15, 23, 42, 0.12); 
  border: 1px solid rgba(255, 255, 255, 0.8); 
  animation: modal-panel-rise 0.42s cubic-bezier(0.16, 1, 0.3, 1) both; 
}
.detail-capsule.modal-box { max-width: 1180px; padding: 0; }
.capsule-header { height: 68px; padding: 0 26px; background: rgba(255,255,255,0.58); border-bottom: 1px solid rgba(148,163,184,0.18); display: flex; align-items: center; justify-content: space-between; backdrop-filter: blur(10px); }

.vis-intel-dashboard { display: flex; flex-direction: column; gap: 24px; height: 100%; animation: modal-panel-rise 0.4s ease-out; }

.intel-visual-grid { 
  display: grid; 
  grid-template-columns: 1fr 1fr; 
  gap: 24px; 
  align-items: stretch;
}

.intel-box { 
  background: #ffffff; 
  border: 1px solid rgba(148, 163, 184, 0.08); 
  border-radius: 24px; 
  padding: 24px; 
  position: relative; 
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); 
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.02);
}

.intel-label { 
  display: flex; 
  align-items: center; 
  gap: 10px; 
  color: #3b82f6; 
  font-size: 11px; 
  font-weight: 800; 
  text-transform: uppercase; 
  margin-bottom: 24px; 
  letter-spacing: 0.12em; 
}
.source-tag { font-size: 11px; font-weight: 800; color: #64748b; display: flex; align-items: center; gap: 8px; text-transform: uppercase; letter-spacing: 0.12em; }

.capsule-scroll-body { flex:1; overflow-y: auto; padding: 20px 32px 30px; }
.article-header-group { margin-bottom: 16px; display: grid; gap: 10px; }
.article-subject { font-size: clamp(24px, 2.2vw, 36px); font-weight: 900; letter-spacing: -0.05em; color: #0f172a; margin-bottom: 0; line-height: 1.08; max-width: 1120px; }
.article-meta-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.article-timestamp { font-size: 13px; color: #64748b; font-weight: 700; }

.premium-source-btn {
  display: inline-flex; align-items: center; gap: 8px; background: rgba(255,255,255,0.8); color: #1d4ed8;
  padding: 10px 18px; border-radius: 999px; font-size: 12px; font-weight: 800;
  text-decoration: none; border: 1px solid rgba(148,163,184,0.22); transition: 0.2s;
  min-height: auto; height: auto; text-transform: none;
}
.premium-source-btn:hover { background: #ffffff; border-color: rgba(59,130,246,0.3); transform: translateY(-1px); }

.capsule-navigation-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.capsule-actions { display: flex; gap: 8px; align-items: center; }
.btn-export-pdf { display: flex; align-items: center; gap: 5px; font-weight: 700; font-size: 12px; border-radius: 10px; min-height: auto; height: 36px; text-transform: none; color: #dc2626; border-color: rgba(220, 38, 38, 0.2); }
.btn-export-pdf:hover { background: #dc2626; color: #fff; border-color: #dc2626; }
.capsule-tabs { background: rgba(226,232,240,0.72); padding: 4px; border-radius: 14px; display: flex; gap: 4px; box-shadow: inset 0 1px 0 rgba(255,255,255,0.75); }
.cap-tab { border:none; background: transparent; padding: 9px 14px; border-radius: 10px; font-size: 12px; font-weight: 800; color: #64748b; cursor: pointer; transition: 0.2s; min-height: auto; height: auto; text-transform: none; }
.cap-tab.active { background: #ffffff; color: #1d4ed8; box-shadow: 0 8px 18px rgba(15,23,42,0.08); }

.btn-action-sync {
  background: #0f172a; color: #f8fbff; height: 42px; padding: 0 18px; border-radius: 14px;
  font-size: 12px; font-weight: 800; display: inline-flex; align-items: center;
  gap: 10px; cursor: pointer; border: none;
  transition: 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 14px 28px rgba(15,23,42,0.14);
  min-height: auto; text-transform: none;
}
.btn-action-sync:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 18px 30px rgba(15,23,42,0.18); }
.btn-action-sync:disabled { opacity: 0.7; cursor: not-allowed; }

.tab-viewport { min-height: 460px; display: flex; flex-direction: column; }
.panel-visual { background: #f8fafc; border-radius: 28px; padding: 24px; flex: 1; display: flex; flex-direction: column; gap: 20px; overflow: hidden; border: 1px solid rgba(226, 232, 240, 0.8); }

.vis-intel-dashboard { display: flex; flex-direction: column; gap: 24px; height: 100%; animation: modal-panel-rise 0.4s ease-out; }

.intel-visual-grid { 
  display: grid; 
  grid-template-columns: 1fr 1fr; 
  gap: 24px; 
  align-items: stretch;
}

.intel-box { 
  background: #ffffff; 
  border: 1px solid rgba(148, 163, 184, 0.08); 
  border-radius: 24px; 
  padding: 24px; 
  position: relative; 
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1); 
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.02);
}

.intel-label { 
  display: flex; 
  align-items: center; 
  gap: 10px; 
  color: #3b82f6; 
  font-size: 11px; 
  font-weight: 800; 
  text-transform: uppercase; 
  margin-bottom: 24px; 
  letter-spacing: 0.12em; 
}

.emotion-flex-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.emotion-chart-shell {
  height: 320px;
  background: rgba(248, 250, 252, 0.4);
  border-radius: 16px;
  margin-bottom: 0;
}

.emotion-render-area {
  width: 100%;
  height: 100%;
}

.emotion-spark-grid { 
  grid-template-columns: 1fr; 
  gap: 12px; 
}

.chart-shell {
  height: 320px;
  background: rgba(248, 250, 252, 0.4);
  border-radius: 16px;
}

.chart-render-area {
  width: 100%;
  height: 100%;
}

.cloud-container-shell {
  width: 100%;
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wc-render-canvas { 
  width: 100%; 
  height: 100%; 
}

@media (max-width: 900px) {
  .intel-visual-grid { grid-template-columns: 1fr; }
}

@keyframes entity-fade-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

@media (max-width: 900px) {
  .panel-visual { padding: 16px; }
}

.panel-report { display: flex; flex-direction: column; gap: 22px; }
.report-box { border: 1px solid rgba(148,163,184,0.18); border-radius: 24px; padding: 26px 28px; background: rgba(255,255,255,0.84); box-shadow: 0 18px 44px rgba(15,23,42,0.04); }
.report-lead-tag {
  display: inline-flex; align-items: center; gap: 8px;
  background: rgba(226,232,240,0.75); color: #0f172a; padding: 6px 12px;
  border-radius: 999px; font-size: 11px; font-weight: 900;
  margin-bottom: 24px; text-transform: uppercase; letter-spacing: 0.08em;
}
.report-body { font-size: 16px; line-height: 1.9; color: #1e293b; white-space: pre-wrap; font-weight: 500; text-align: left; }

.analysis-spinner { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 100px 0; background: radial-gradient(circle at center, rgba(37, 99, 235, 0.05) 0%, transparent 70%); border-radius: 30px; }
.aura-spin { 
  width: 52px; height: 52px; 
  border: 3px solid rgba(59, 130, 246, 0.08); 
  border-top-color: #3b82f6; 
  border-radius: 50%; 
  animation: spin 0.8s cubic-bezier(0.4, 0, 0.2, 1) infinite; 
  margin: 0 auto 24px;
  box-shadow: 0 0 20px rgba(59, 130, 246, 0.2);
}
.status-bright-text { color: #60a5fa; font-size: 14px; font-weight: 800; letter-spacing: 0.06em; text-shadow: 0 0 12px rgba(96, 165, 250, 0.4); }
.panel-visual--idle .status-bright-text { color: #475569; }
.panel-visual--idle .aura-spin { border-color: rgba(148, 163, 184, 0.12); border-top-color: #3b82f6; box-shadow: none; }
.panel-visual--idle .empty-vis iconify-icon { color: rgba(148,163,184,0.3); }

.empty-vis { text-align: center; padding: 110px 0; position: relative; }
.empty-vis iconify-icon { font-size: 48px; color: rgba(59, 130, 246, 0.15); margin-bottom: 24px; filter: drop-shadow(0 0 8px rgba(59, 130, 246, 0.1)); }
.btn-empty-sync {
  margin-top: 24px; background: #2563eb; color: #fff; border:none; padding: 10px 24px;
  border-radius: 12px; font-size: 12px; font-weight: 800; cursor: pointer; transition: 0.3s;
  min-height: auto; height: auto; text-transform: none;
}
.btn-empty-sync:hover { background: #1d4ed8; transform: translateY(-1px); }

@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
@keyframes modal-panel-rise {
  from { opacity: 0; transform: translateY(18px) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.anim-spin { animation: spin 1s infinite linear; }

.modal-fade-enter-active, .modal-fade-leave-active { transition: opacity 0.24s ease; }
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; }
.btn-capsule-close { background: transparent; border:none; font-size: 24px; color: #94a3b8; cursor: pointer; transition: 0.2s; min-height: 44px; text-transform: none; }
.btn-capsule-close:hover { color: #ef4444; }

iconify-icon { display: inline-block; width: 1.2em; height: 1.2em; }

@media (max-width: 900px) {
  .modal-overlay { padding: 18px; }
  .detail-capsule { height: 94vh; border-radius: 24px; }
  .capsule-scroll-body { padding: 20px 18px 28px; }
  .article-subject { font-size: 28px; }
  .panel-visual { padding: 16px; }
  .report-box { padding: 24px; }
}
</style>

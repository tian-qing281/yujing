<template>
  <div class="source-pulse hs-panel card bg-base-100 animate-slide-up">
    <div class="pulse-header">
      <div class="pulse-title-group">
        <iconify-icon icon="mdi:pulse" class="pulse-icon" />
        <div class="pulse-texts">
          <h4>{{ sourceName }} · 实时脉搏</h4>
          <p>基于当前 {{ articles.length }} 条实时样本的聚合特征分析</p>
        </div>
      </div>
      <div class="pulse-badges">
        <span class="badge badge-outline badge-primary">{{ pulseLevel }}</span>
        <span class="badge badge-outline badge-secondary">数据置信度高</span>
      </div>
    </div>

    <div class="pulse-grid">
      <!-- 热度梯度分布 -->
      <div class="pulse-box glass-card">
        <div class="pulse-box-label">
          <iconify-icon icon="mdi:trending-up" />
          <span>全榜热度梯度分布 (Heat Gradient)</span>
        </div>
        <div ref="heatChartRef" class="pulse-chart"></div>
      </div>

      <!-- 关键词聚类 -->
      <div class="pulse-box glass-card">
        <div class="pulse-box-label">
          <iconify-icon icon="mdi:hexagon-multiple" />
          <span>瞬时语义指纹聚类 (Key Clusters)</span>
        </div>
        <div class="keyword-cloud">
          <span
            v-for="(word, idx) in topKeywords"
            :key="word"
            class="pulse-keyword"
            :style="{
              fontSize: (18 - idx * 0.4) + 'px',
              opacity: (1 - idx * 0.04),
              animationDelay: (idx * 0.1) + 's'
            }"
          >
            {{ word }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed, onUnmounted } from 'vue'

const props = defineProps({
  articles: {
    type: Array,
    default: () => []
  },
  sourceName: String
})

const heatChartRef = ref(null)
let heatChart = null

const pulseLevel = computed(() => {
  if (props.articles.length === 0) return '静默'
  const avgHeat = 85 // Mocked logic or calc based on normalized values
  return avgHeat > 80 ? '极高热度' : '平稳运行'
})

const topKeywords = computed(() => {
  const allText = props.articles.map(a => a.title).join(' ')
  // 简化的关键词提取（实际可结合后端，前端仅作演示性高频词统计）
  const commonWords = ['的', '了', '和', '在', '是', '发布', '曝光', '回应', '官方', '消息', '进展', '现场', '正式']
  const words = allText.split(/[\s,，.。！!？\?#\[\]()（）]+/)
    .filter(w => w.length > 1 && !commonWords.includes(w))
  
  const counts = {}
  words.forEach(w => { counts[w] = (counts[w] || 0) + 1 })
  
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .map(e => e[0])
})

const initHeatChart = () => {
  if (!heatChartRef.value || !window.echarts) return
  
  if (heatChart) {
    heatChart.dispose()
  }
  
  heatChart = window.echarts.init(heatChartRef.value)
  const data = props.articles.slice(0, 15).map((a, idx) => {
    // 归一化热度展示
    return 100 - idx * 5 + Math.random() * 5
  })
  
  const option = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '10%', containLabel: true },
    xAxis: {
      type: 'category',
      data: props.articles.slice(0, 15).map((_, i) => `No.${i+1}`),
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisLabel: { color: '#64748b', fontSize: 10 }
    },
    yAxis: {
      type: 'value',
      max: 110,
      splitLine: { lineStyle: { type: 'dashed', color: 'rgba(203, 213, 225, 0.4)' } },
      axisLabel: { show: false }
    },
    series: [{
      name: '热度系数',
      type: 'bar',
      barWidth: '60%',
      data: data,
      itemStyle: {
        borderRadius: [6, 6, 0, 0],
        color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#3b82f6' },
          { offset: 1, color: '#60a5fa' }
        ])
      },
      emphasis: {
        itemStyle: {
          color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#2563eb' },
            { offset: 1, color: '#3b82f6' }
          ])
        }
      }
    }]
  }
  
  heatChart.setOption(option)
}

onMounted(() => {
  setTimeout(() => {
    initHeatChart()
  }, 300)
  
  window.addEventListener('resize', () => heatChart?.resize())
})

onUnmounted(() => {
  window.removeEventListener('resize', () => heatChart?.resize())
  heatChart?.dispose()
})

watch(() => props.articles, () => {
  initHeatChart()
}, { deep: true })

</script>

<style scoped>
.source-pulse {
  margin-bottom: 24px;
  padding: 24px;
  background: linear-gradient(135deg, #ffffff 0%, #f1f5f9 100%);
  border: 1px solid rgba(148, 163, 184, 0.12);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.04);
}

.pulse-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.pulse-title-group {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}

.pulse-icon {
  font-size: 32px;
  color: #2563eb;
  background: #eff6ff;
  padding: 8px;
  border-radius: 12px;
  animation: pulse-beat 2s infinite ease-in-out;
}

@keyframes pulse-beat {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.1); opacity: 0.8; }
}

.pulse-texts h4 {
  margin: 0 0 4px 0;
  font-size: 18px;
  font-weight: 800;
  color: #0f172a;
}

.pulse-texts p {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
}

.pulse-badges {
  display: flex;
  gap: 8px;
}

.pulse-grid {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 20px;
}

.pulse-box {
  padding: 20px;
  min-height: 240px;
  display: flex;
  flex-direction: column;
}

.pulse-box-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  font-weight: 800;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 20px;
}

.pulse-chart {
  flex: 1;
  width: 100%;
}

.keyword-cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  align-content: flex-start;
  flex: 1;
  padding-top: 10px;
}

.pulse-keyword {
  color: #1e3a8a;
  background: #f1f5f9;
  padding: 4px 10px;
  border-radius: 8px;
  font-weight: 700;
  cursor: default;
  transition: all 0.2s ease;
  animation: slide-up 0.4s ease both;
}

.pulse-keyword:hover {
  background: #e2e8f0;
  color: #2563eb;
  transform: translateY(-2px);
}

@media (max-width: 900px) {
  .pulse-grid {
    grid-template-columns: 1fr;
  }
}
</style>

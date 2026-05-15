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
               <a
                  v-if="preferredSourceUrl"
                  :href="preferredSourceUrl"
                  target="_blank"
                  class="premium-source-btn btn btn-outline"
               >
                  <iconify-icon icon="mdi:open-in-new" />
                  <span>访问网页原文</span>
               </a>
               <button
                  v-else
                  type="button"
                  class="premium-source-btn btn btn-outline"
                  disabled
                  title="该文章没有原文链接"
               >
                  <iconify-icon icon="mdi:link-off" />
                  <span>暂无原文链接</span>
               </button>
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

              <div v-else-if="item.analyze_error && !hasVisualData" class="empty-vis empty-vis--error">
                <iconify-icon icon="mdi:alert-circle-outline" style="color:#ef4444" />
                <p class="status-bright-text" style="color:#ef4444">采集或分析失败</p>
                <p class="err-detail">{{ item.analyze_error }}</p>
                <p class="err-hint" v-if="/凭据|登录|cookie|Cookie|验证/.test(item.analyze_error)">
                  该站点需要有效登录态，请在左侧「凭据资产配置」重新填入 Cookie 后重试。
                </p>
                <p class="err-hint" v-else-if="/JavaScript|前端壳|热点聚合页/.test(item.analyze_error)">
                  原站为纯 JS 渲染页面（或热搜跳转页），无法直接抽取文本。请点击上方「访问网页原文」查看原始内容。
                </p>
                <button class="btn-empty-sync btn btn-primary" @click="$emit('trigger-ai', true)">重新分析</button>
              </div>

              <div v-else-if="!hasVisualData && !item.isAnalyzing" class="empty-vis">
                <iconify-icon icon="mdi:database-search" />
                <p class="status-bright-text">数据分析特征未就绪</p>
                <button class="btn-empty-sync btn btn-primary" @click="$emit('trigger-ai', true)">开始深度分析</button>
              </div>
              
              <div v-show="hasVisualData" class="vis-intel-dashboard">
                <div v-if="item.analyze_error" class="vis-error-banner">
                  <iconify-icon icon="mdi:alert-circle-outline" />
                  <div class="vis-error-banner__body">
                    <strong>原文采集受限：</strong>{{ item.analyze_error }}
                    <span v-if="/凭据|登录|cookie|Cookie|验证/.test(item.analyze_error)">（请更新左侧「凭据资产配置」中的 Cookie 后重试）</span>
                  </div>
                  <button class="vis-error-banner__retry btn btn-xs" @click="$emit('trigger-ai', true)">重试</button>
                </div>
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

                  <!-- 舆情倾向分析 / 方面级情感（ABSA） -->
                  <div class="intel-box sentiment-intel-box">
                    <div class="intel-label">
                      <iconify-icon icon="mdi:gauge" />
                      <span>{{ hasAspects ? '方面级情感（ABSA）' : '舆情倾向分析' }}</span>
                      <span v-if="hasAspects" class="absa-badge">LLM</span>
                      <span v-else-if="absaLoading" class="absa-badge absa-badge--loading">分析中</span>
                    </div>

                    <!-- 1) ABSA 命中：卡片列表 -->
                    <div v-if="hasAspects" class="absa-list">
                      <div
                        v-for="(asp, idx) in normalizedAspects"
                        :key="idx"
                        class="absa-card"
                        :class="`absa-card--${asp.sentiment}`"
                      >
                        <div class="absa-card-head">
                          <span class="absa-aspect">{{ asp.aspect }}</span>
                          <span class="absa-chip" :class="`absa-chip--${asp.sentiment}`">
                            <iconify-icon :icon="asp.icon" />
                            <span>{{ asp.label }}</span>
                          </span>
                        </div>
                        <div v-if="asp.evidence" class="absa-evidence">
                          <iconify-icon icon="mdi:format-quote-open" />
                          <span>{{ asp.evidence }}</span>
                        </div>
                      </div>
                      <p class="absa-source-tip">
                        <iconify-icon icon="mdi:information-outline" />
                        基于 LLM 对正文抽取的 5-8 个核心方面（人物 / 机构 / 议题），每条配证据句。
                      </p>
                    </div>

                    <!-- 2) ABSA 加载中 -->
                    <div v-else-if="absaLoading" class="absa-loading">
                      <div class="absa-skeleton" v-for="n in 3" :key="n">
                        <div class="sk-bar sk-bar-aspect"></div>
                        <div class="sk-bar sk-bar-evi"></div>
                      </div>
                      <p class="absa-loading-text">LLM 正在抽取方面与证据，通常 3-8 秒…</p>
                    </div>

                    <!-- 3) ABSA 不可用但有 emotions：旧的三色环兜底 -->
                    <div v-else-if="hasEmotionFallback" class="chart-shell">
                      <div ref="sentimentChartRef" class="chart-render-area"></div>
                    </div>

                    <!-- 4) 完全无数据 -->
                    <div v-else class="absa-empty">
                      <iconify-icon icon="mdi:database-off-outline" />
                      <p class="absa-empty-title">暂无方面级情感数据</p>
                      <p class="absa-empty-hint">
                        ABSA 由 LLM 在完成 AI 总结后自动触发；若原文采集失败或正文过短（≤ 60 字），将无法抽取方面。
                      </p>
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

                  <!-- 核心实体雷达 / ABSA 维度雷达（B5：当抽取到 aspects 时优先显示语义雷达） -->
                  <div class="intel-box radar-intel-box">
                    <div class="intel-label">
                      <iconify-icon :icon="hasAspects ? 'mdi:hexagon-multiple-outline' : 'mdi:radar'" />
                      <span>{{ hasAspects ? 'ABSA 维度雷达' : '核心实体雷达' }}</span>
                      <span v-if="hasAspects" class="absa-badge">情感</span>
                    </div>
                    <div class="chart-shell">
                      <div v-show="!hasAspects" ref="keywordRadarRef" class="chart-render-area"></div>
                      <div v-show="hasAspects" ref="aspectRadarRef" class="chart-render-area"></div>
                    </div>
                  </div>

                  <!-- B6: B 站评论 + 弹幕情绪聚合（仅哔哩哔哩榜文章）
                       拆成两张独立 intel-box，让 .intel-visual-grid (1fr 1fr) 自然左右铺开 -->
                  <div v-if="isBilibiliArticle" class="intel-box bili-sent-box">
                    <div class="intel-label">
                      <iconify-icon icon="mdi:comment-text-multiple-outline" />
                      <span>B 站评论情绪</span>
                      <span v-if="biliSent?.data_source" class="absa-badge">{{ biliSent.data_source === 'local' ? '本地' : '实时' }}</span>
                      <span v-if="biliSentLoading" class="absa-badge absa-badge--loading">加载中</span>
                      <span v-if="biliSent" class="bili-sent-count">{{ biliSent.total_comments }} 条</span>
                    </div>
                    <div v-if="biliSentLoading" class="bili-sent-loading">
                      <div class="absa-skeleton" v-for="n in 2" :key="n">
                        <div class="sk-bar sk-bar-aspect"></div>
                        <div class="sk-bar sk-bar-evi"></div>
                      </div>
                    </div>
                    <div v-else-if="biliSentError" class="absa-empty">
                      <iconify-icon icon="mdi:database-off-outline" />
                      <p class="absa-empty-title">{{ biliSentError }}</p>
                    </div>
                    <div v-else-if="biliSent" class="bili-sent-single">
                      <div ref="biliCommentChartRef" class="bili-sent-pie"></div>
                      <ul v-if="biliSent.top_comments?.length" class="bili-sent-top">
                        <li v-for="(c, i) in biliSent.top_comments.slice(0, 6)" :key="i">
                          <span class="bili-sent-likes">♥ {{ c.likes }}</span>
                          <span class="bili-sent-text">{{ c.content }}</span>
                        </li>
                      </ul>
                    </div>
                  </div>

                  <div v-if="isBilibiliArticle" class="intel-box bili-sent-box">
                    <div class="intel-label">
                      <iconify-icon icon="mdi:subtitles-outline" />
                      <span>B 站弹幕情绪</span>
                      <span v-if="biliSent?.data_source" class="absa-badge">{{ biliSent.data_source === 'local' ? '本地' : '实时' }}</span>
                      <span v-if="biliSentLoading" class="absa-badge absa-badge--loading">加载中</span>
                      <span v-if="biliSent" class="bili-sent-count">{{ biliSent.total_danmaku }} 条</span>
                    </div>
                    <div v-if="biliSentLoading" class="bili-sent-loading">
                      <div class="absa-skeleton" v-for="n in 2" :key="n">
                        <div class="sk-bar sk-bar-aspect"></div>
                        <div class="sk-bar sk-bar-evi"></div>
                      </div>
                    </div>
                    <div v-else-if="biliSentError" class="absa-empty">
                      <iconify-icon icon="mdi:database-off-outline" />
                      <p class="absa-empty-title">{{ biliSentError }}</p>
                    </div>
                    <div v-else-if="biliSent" class="bili-sent-single">
                      <div ref="biliDanmakuChartRef" class="bili-sent-pie"></div>
                      <ul v-if="biliSent.top_danmaku?.length" class="bili-sent-top">
                        <li v-for="(d, i) in biliSent.top_danmaku.slice(0, 6)" :key="i">
                          <span class="bili-sent-time">{{ Math.floor((d.progress_ms || 0) / 1000) }}s</span>
                          <span class="bili-sent-text">{{ d.content }}</span>
                        </li>
                      </ul>
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
              
              <div v-if="item.ai_summary && !isCredentialError" class="report-box card animate-slide-up">
                  <div class="report-lead-tag">
                    <iconify-icon icon="mdi:text-box-search-outline" />
                    <span>AI 总结</span>
                  </div>
                  <div class="report-body markdown-body" v-html="renderedSummary"></div>
              </div>

              <!-- 凭据失效专用提示（后端返回以 ❌ 开头的错误信息） -->
              <div v-else-if="isCredentialError" class="report-credential-error">
                <iconify-icon icon="mdi:key-alert-outline" />
                <p class="empty-title">目标平台凭据失效</p>
                <p class="empty-hint">{{ credentialErrorMessage }}</p>
                <p class="empty-hint">请前往侧边栏 <strong>「凭据资产配置」</strong> 更新对应平台的 Cookie 后重试。</p>
              </div>

              <!-- 空态：未触发分析时引导用户点击右上角"开始深度分析" -->
              <div v-if="!item.ai_summary && !item.isAnalyzing" class="report-empty">
                <iconify-icon icon="mdi:robot-outline" />
                <p class="empty-title">尚未生成 AI 总结</p>
                <p class="empty-hint">点击右上角 <strong>「开始深度分析」</strong> 生成本篇情报的 AI 研判与摘要。</p>
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
import { renderMarkdown } from '@/utils/markdown'
import { ANIM } from '@/utils/chartAnimation'

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
const aspectRadarRef = ref(null)
const biliCommentChartRef = ref(null)
const biliDanmakuChartRef = ref(null)
let emotionChart = null
let sentimentChart = null
let radarChart = null
let aspectRadarChart = null
let biliCommentChart = null
let biliDanmakuChart = null
let renderAnimationFrame = null
let renderDebounceTimer = null
let lastRenderedCloudLength = -1

// B6: B 站评论 / 弹幕情绪聚合
const biliSent = ref(null)
const biliSentLoading = ref(false)
const biliSentError = ref('')
const isBilibiliArticle = computed(() => {
  const it = props.item
  if (!it) return false
  return it.source_id === 'bilibili_hot_video' || /^BV[\w]{8,}$/.test(String(it.item_id || it.itemId || ''))
})

async function fetchBiliSentiment(bvid) {
  if (!bvid) return
  biliSentLoading.value = true
  biliSentError.value = ''
  biliSent.value = null
  try {
    const r = await fetch(`/api/bili-sentiment/${bvid}`)
    const j = await r.json()
    if (j.error) {
      biliSentError.value = '该视频暂无评论/弹幕数据'
    } else {
      biliSent.value = j
      nextTick(() => renderBiliSentCharts())
    }
  } catch (e) {
    biliSentError.value = '加载失败：' + (e?.message || e)
  } finally {
    biliSentLoading.value = false
  }
}

const EMO_COLORS = { '愤怒': '#ef4444', '厌恶': '#a855f7', '悲伤': '#94a3b8', '喜悦': '#10b981', '关注': '#3b82f6', '惊讶': '#f59e0b', '质疑': '#ec4899', '中性': '#64748b' }

function renderEmoPie(domRef, instRef, data) {
  if (!domRef?.value || !window.echarts) return null
  if (instRef) instRef.dispose()
  const inst = window.echarts.init(domRef.value)
  const arr = (data || []).filter(e => e.value > 0)
  if (!arr.length) {
    inst.setOption({
      graphic: [{ type: 'text', left: 'center', top: 'middle', style: { text: '暂无数据', fill: '#94a3b8', fontSize: 12, fontWeight: 700 } }]
    })
    return inst
  }
  inst.setOption({
    ...ANIM.pie,
    tooltip: { trigger: 'item', formatter: '{b}: {d}%' },
    legend: {
      orient: 'horizontal',
      bottom: 0,
      left: 'center',
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 8,
      icon: 'circle',
      textStyle: { fontSize: 10, color: '#475569' }
    },
    series: [{
      type: 'pie',
      radius: ['46%', '70%'],
      center: ['50%', '42%'],
      avoidLabelOverlap: true,
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      labelLine: { show: false },
      data: arr.map(e => ({ value: +(e.value * 100).toFixed(1), name: e.label, itemStyle: { color: EMO_COLORS[e.label] || '#94a3b8' } }))
    }]
  })
  return inst
}

function renderBiliSentCharts() {
  if (!biliSent.value) return
  biliCommentChart = renderEmoPie(biliCommentChartRef, biliCommentChart, biliSent.value.comment_emotions)
  biliDanmakuChart = renderEmoPie(biliDanmakuChartRef, biliDanmakuChart, biliSent.value.danmaku_emotions)
}

// 凭据失效识别：后端 ai_summary 字段以 ❌ 开头或包含「凭据失效」字样时，认定为凭据错误
const isCredentialError = computed(() => {
  const txt = props.item?.ai_summary || ''
  return typeof txt === 'string' && (txt.startsWith('❌') || txt.includes('凭据失效'))
})
const credentialErrorMessage = computed(() => {
  const raw = (props.item?.ai_summary || '').replace(/^❌\s*\[?[^\]]*\]?\s*/, '').trim()
  return raw || '后端尝试抓取正文时被目标站点拦截，常见原因为登录态过期。'
})

// P3：AI 总结渲染为 markdown HTML（已经过 DOMPurify 清洗）
const renderedSummary = computed(() => {
  const raw = props.item?.ai_summary || ''
  if (!raw || isCredentialError.value) return ''
  return renderMarkdown(raw)
})

const hasVisualData = computed(() => {
  const hasCloud = props.item?.wordcloud && props.item.wordcloud.length > 0
  const hasEmo = props.item?.emotions && props.item.emotions.length > 0
  return !!(hasCloud || hasEmo)
})

const hasAspects = computed(() => {
  const list = props.item?.aspects
  return Array.isArray(list) && list.length > 0
})

// ABSA 卡片渲染所需：情感标签 / 图标
const _ABSA_META = {
  positive: { label: '正面', icon: 'mdi:emoticon-happy-outline' },
  neutral:  { label: '中性', icon: 'mdi:emoticon-neutral-outline' },
  negative: { label: '负面', icon: 'mdi:emoticon-sad-outline' },
}
const normalizedAspects = computed(() => {
  const list = Array.isArray(props.item?.aspects) ? props.item.aspects : []
  return list
    .filter(a => a && a.aspect)
    .map(a => {
      const sent = ['positive', 'neutral', 'negative'].includes(a.sentiment) ? a.sentiment : 'neutral'
      const meta = _ABSA_META[sent]
      return {
        aspect: String(a.aspect),
        sentiment: sent,
        evidence: a.evidence ? String(a.evidence) : '',
        label: meta.label,
        icon: meta.icon,
      }
    })
})

// 加载态：分析中且尚未拿到 aspects（aspects 通常在 AI 总结之后才到达）
const absaLoading = computed(() => !!props.item?.isAnalyzing && !hasAspects.value)

// 兜底环图条件：有 emotions 但无 aspects
const hasEmotionFallback = computed(() => {
  const emo = props.item?.emotions
  return Array.isArray(emo) && emo.length > 0 && !hasAspects.value
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
  // editorial: 情感色保留语义（正/负/中可辨），但抹去糖果色，统一到 MASTER token 范围
  // 红=愤怒/厌恶（深浅区分）、暖灰=悲伤/中性、暗绿=喜悦、深蓝=关注、琥珀=惊讶、赤陶红=质疑
  const colors = {
    '愤怒': '#B91C1C',   // critical 暗红
    '厌恶': '#7F1D1D',   // 更深的暗红，区分愤怒
    '悲伤': '#57534E',   // text-2 石板灰
    '喜悦': '#15803D',   // success 暗绿
    '关注': '#1E40AF',   // data 深蓝
    '惊讶': '#D97706',   // warning 琥珀
    '质疑': '#B45309',   // accent 赤陶红
    '中性': '#A8A29E'    // text-3 暖灰
  }
  return colors[label] || '#A8A29E'
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

const renderSentimentChart = () => {
  if (!sentimentChartRef.value || !window.echarts) return
  if (sentimentChart) sentimentChart.dispose()
  sentimentChart = window.echarts.init(sentimentChartRef.value)

  // ABSA 命中时模板已切换为 HTML 卡片列表，sentimentChartRef 不会挂载；
  // 这里仅渲染兜底的整体三色环。
  const aspects = (props.item?.aspects || []).filter(a => a && a.aspect)
  if (aspects.length > 0) return

  // 兜底：旧的整体三色环（仅当 ABSA 不可用时）
  const _colorMap = { '正面': '#10b981', '中性': '#64748b', '负面': '#ef4444' }
  // 从 8 类 emotions 聚合为正/中/负 3 类
  // 关注/惊讶→中性（围观类，无明确倾向）；质疑→负面（舆情语境下多为负光谱）
  const emo = props.item?.emotions || []
  const groups = [
    { name: '正面', value: emo.filter(e => e.label === '喜悦').reduce((s, e) => s + e.value, 0), color: _colorMap['正面'] },
    { name: '中性', value: emo.filter(e => ['中性', '关注', '惊讶'].includes(e.label)).reduce((s, e) => s + e.value, 0), color: _colorMap['中性'] },
    { name: '负面', value: emo.filter(e => ['愤怒', '厌恶', '悲伤', '质疑'].includes(e.label)).reduce((s, e) => s + e.value, 0), color: _colorMap['负面'] },
  ].filter(g => g.value > 0)
  if (!groups.length) return
  const dominant = groups.reduce((a, b) => a.value > b.value ? a : b)
  sentimentChart.setOption({
    ...ANIM.pie,
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
    graphic: [{
      type: 'text', left: 'center', top: 'center',
      style: { text: dominant.name, fontSize: 16, fontWeight: 900, fill: dominant.color, textAlign: 'center' }
    }]
  })
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
      ...ANIM.bar,
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
          const baseSize = Math.min(width, height);
          const factor = (width > 600) ? 2.8 : 3.5;
          return (size * baseSize) / (maxVal * factor);
        },
        minSize: 6,
        fontFamily: 'Outfit, Inter, system-ui, sans-serif',
        // editorial: 赤陶红 → 近墨石板梯度，应拍主调
        color: (word) => {
           const colors = ['#0F172A', '#1C1917', '#57534E', '#92400E', '#B45309'];
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
  renderSentimentChart()

  // 核心实体雷达图
  if (keywordRadarRef.value && window.echarts) {
    if (radarChart) radarChart.dispose()
    radarChart = window.echarts.init(keywordRadarRef.value)
    const topKw = normalizedWordcloud.value.slice(0, 6)
    if (topKw.length >= 3) {
      const kwMax = Math.max(...topKw.map(k => k.value))
      radarChart.setOption({
        ...ANIM.radar,
        tooltip: {},
        radar: {
          indicator: topKw.map(k => ({ name: k.word, max: kwMax * 1.15 })),
          shape: 'polygon',
          splitNumber: 4,
          axisName: { color: '#334155', fontSize: 11, fontWeight: 700 },
          splitArea: { areaStyle: { color: ['rgba(180,83,9,0.03)', 'rgba(180,83,9,0.06)', 'rgba(180,83,9,0.03)', 'rgba(180,83,9,0.06)'] } },
          splitLine: { lineStyle: { color: 'rgba(168,162,158,0.18)' } },
          axisLine: { lineStyle: { color: 'rgba(168,162,158,0.22)' } }
        },
        series: [{
          type: 'radar',
          name: '关键词频', 
          data: [{
            name: '关键词频', 
            value: topKw.map(k => k.value),
            // editorial: 赤陶红单色雷达
            areaStyle: { color: 'rgba(180,83,9,0.15)' },
            lineStyle: { color: '#B45309', width: 2 },
            itemStyle: { color: '#92400E', borderWidth: 2 },
            symbol: 'circle',
            symbolSize: 6
          }]
        }]
      })
    }
  }

  // B5: ABSA 维度雷达图，轴 = aspect，值 = 情感极性映射（0=负 / 1=中性 / 2=正）
  renderAspectRadar()
}

function renderAspectRadar() {
  if (!aspectRadarRef.value || !window.echarts) return
  const aspects = (props.item?.aspects || []).filter(a => a && a.aspect)
  if (aspects.length < 3) {
    if (aspectRadarChart) { aspectRadarChart.dispose(); aspectRadarChart = null; }
    return
  }
  if (aspectRadarChart) aspectRadarChart.dispose()
  aspectRadarChart = window.echarts.init(aspectRadarRef.value)
  // Batch IV · ABSA 雷达修复
  // 旧映射 negative=0 会让"负面"轴塌到原点，多个负面 aspect 同时存在时连线会"穿心"。
  // 新映射 negative=1 / neutral=2 / positive=3，所有顶点都至少占 1/3 半径，杜绝塌陷。
  // 同时按情感色染顶点，单看点位也能读出情感分布。
  const polarityScore = (s) => (s === 'positive' ? 3 : s === 'negative' ? 1 : 2)
  const polarityLabel = (s) => (s === 'positive' ? '正面' : s === 'negative' ? '负面' : '中性')
  const axisColor = (s) => (s === 'positive' ? '#16a34a' : s === 'negative' ? '#dc2626' : '#94a3b8')
  aspectRadarChart.setOption({
    ...ANIM.radar,
    tooltip: {
      formatter: () => {
        const items = aspects.map((a) => `<div style="display:flex;justify-content:space-between;gap:12px"><span>${a.aspect}</span><strong style="color:${axisColor(a.sentiment)}">${polarityLabel(a.sentiment)}</strong></div>`).join('')
        return `<div style="font-weight:700;margin-bottom:6px">方面情感极性</div>${items}`
      }
    },
    radar: {
      indicator: aspects.map(a => ({ name: a.aspect, max: 3 })),
      shape: 'polygon',
      splitNumber: 3,
      axisName: {
        formatter: (name) => {
          const a = aspects.find(x => x.aspect === name)
          return `{c|${name}}\n{p|${polarityLabel(a?.sentiment)}}`
        },
        rich: {
          c: { color: '#0f172a', fontSize: 11, fontWeight: 800, padding: [0, 0, 2, 0] },
          p: { color: '#94a3b8', fontSize: 9, fontWeight: 700 }
        }
      },
      splitArea: { areaStyle: { color: ['rgba(168,162,158,0.04)', 'rgba(168,162,158,0.08)'] } },
      splitLine: { lineStyle: { color: 'rgba(168,162,158,0.18)' } },
      axisLine: { lineStyle: { color: 'rgba(168,162,158,0.22)' } }
    },
    series: [{
      type: 'radar',
      name: 'ABSA 极性',
      data: [{
        value: aspects.map(a => polarityScore(a.sentiment)),
        // editorial: 赤陶红单色面 + 情感色顶点
        areaStyle: { color: 'rgba(180,83,9,0.15)' },
        lineStyle: { color: '#B45309', width: 2 },
        symbol: 'circle',
        symbolSize: 9,
        // 顶点按情感染色（红=负 / 灰=中 / 绿=正）
        itemStyle: {
          borderWidth: 2,
          borderColor: '#fff',
          color: (params) => {
            const idx = params?.dataIndex ?? 0
            return axisColor(aspects[idx]?.sentiment)
          }
        }
      }]
    }]
  })
}

watch(() => props.item?.wordcloud, (newData) => {
  if (newData?.length > 0 && props.activeTab === 'visual' && newData.length !== lastRenderedCloudLength) {
    scheduleRender(() => renderCloud(newData))
  }
}, { deep: true })

// 监听 emotions 变化，单独重绘舆情倾向饼图（不依赖词云）
watch(() => props.item?.emotions, (newData) => {
  if (newData?.length > 0 && props.activeTab === 'visual') {
    nextTick(() => renderSentimentChart())
  }
}, { deep: true })

// 监听 ABSA 方面变化，重绘为方面级条形图
watch(() => props.item?.aspects, (newData) => {
  if (Array.isArray(newData) && newData.length > 0 && props.activeTab === 'visual') {
    nextTick(() => {
      renderSentimentChart()
      renderAspectRadar()
    })
  }
}, { deep: true })

onMounted(() => {
  if (props.activeTab === 'visual' && hasVisualData.value) {
    nextTick(() => renderCloud(props.item?.wordcloud))
  }
  // B6: 首次挂载时若已是 B 站文章则触发拉取
  if (isBilibiliArticle.value) {
    const bv = props.item?.item_id || props.item?.itemId
    if (bv && /^BV[\w]{8,}$/.test(bv)) fetchBiliSentiment(bv)
  }
})

watch(() => props.item?.id, (newId) => {
  // 切换文章时立即销毁旧图表实例，避免新文章数据未到位前渲染上一篇旧图
  if (emotionChart) { emotionChart.dispose(); emotionChart = null; }
  if (sentimentChart) { sentimentChart.dispose(); sentimentChart = null; }
  if (radarChart) { radarChart.dispose(); radarChart = null; }
  if (aspectRadarChart) { aspectRadarChart.dispose(); aspectRadarChart = null; }
  if (biliCommentChart) { biliCommentChart.dispose(); biliCommentChart = null; }
  if (biliDanmakuChart) { biliDanmakuChart.dispose(); biliDanmakuChart = null; }
  biliSent.value = null
  biliSentError.value = ''
  // 清空词云画布
  if (wcCanvas.value) {
    const ctx = wcCanvas.value.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, wcCanvas.value.width, wcCanvas.value.height);
  }
  lastRenderedCloudLength = 0;
  if (newId && props.activeTab === 'visual' && hasVisualData.value) {
    nextTick(() => renderCloud(props.item?.wordcloud))
  }
  // B6: B 站文章自动加载评论/弹幕情绪
  if (newId && isBilibiliArticle.value) {
    const bv = props.item?.item_id || props.item?.itemId
    if (bv && /^BV[\w]{8,}$/.test(bv)) fetchBiliSentiment(bv)
  }
})

onUnmounted(() => {
  if (emotionChart) emotionChart.dispose()
  if (sentimentChart) sentimentChart.dispose()
  if (radarChart) radarChart.dispose()
  if (aspectRadarChart) aspectRadarChart.dispose()
  if (biliCommentChart) biliCommentChart.dispose()
  if (biliDanmakuChart) biliDanmakuChart.dispose()
  if (renderDebounceTimer) clearTimeout(renderDebounceTimer)
  if (renderAnimationFrame) cancelAnimationFrame(renderAnimationFrame)
})

watch(() => props.activeTab, (newTab) => {
  if (newTab === 'visual' && hasVisualData.value) {
    nextTick(() => renderCloud(props.item?.wordcloud))
  }
  if (newTab === 'visual' && biliSent.value) {
    nextTick(() => renderBiliSentCharts())
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
  color: var(--color-accent); 
  font-size: 11px; 
  font-weight: 800; 
  text-transform: uppercase; 
  margin-bottom: 24px; 
  letter-spacing: 0.12em; 
}
.source-tag { font-size: 11px; font-weight: 800; color: #64748b; display: flex; align-items: center; gap: 8px; text-transform: uppercase; letter-spacing: 0.12em; }
.absa-badge {
  display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 4px;
  background: var(--color-surface-2);
  color: var(--color-accent);
  border: 1px solid var(--color-border);
  font-size: 9px; font-weight: 800; letter-spacing: 0.12em;
  margin-left: auto;
}
.absa-badge--loading {
  background: var(--color-surface-2);
  color: var(--color-text-3);
  border-color: var(--color-border);
  animation: absa-pulse 1.4s ease-in-out infinite;
}
@keyframes absa-pulse { 0%,100%{opacity:1;} 50%{opacity:0.55;} }

/* === ABSA 卡片列表 === */
.absa-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 2px 2px;
  /* 高度对齐策略：左栏「情感极性分布」chart-shell 高 320px + label 区 ~ 24px
     + 卡片自身 padding 24×2，总外高约 416px。所以 ABSA 内可滚区放到 ~ 300px
     最合适——总外高 ≈ 348px < 左侧 416px，grid stretch 时整张卡以左侧为准
     被拉到 416px，ABSA 卡内部留出留白，不会反向把左侧撑高。 */
  max-height: 300px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.45) transparent;
}
.absa-list::-webkit-scrollbar { width: 6px; }
.absa-list::-webkit-scrollbar-thumb { background: rgba(148, 163, 184, 0.45); border-radius: 3px; }
.absa-list::-webkit-scrollbar-track { background: transparent; }
.absa-card {
  position: relative;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  padding: 12px 14px 12px 18px;
  box-shadow: 0 2px 6px -3px rgba(15, 23, 42, 0.08);
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}
.absa-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 22px -10px rgba(15, 23, 42, 0.18);
}
.absa-card::before {
  content: '';
  position: absolute;
  left: 0; top: 12px; bottom: 12px;
  width: 4px;
  border-radius: 0 4px 4px 0;
  background: #94a3b8;
}
.absa-card--positive::before { background: linear-gradient(180deg, #34d399, #10b981); }
.absa-card--neutral::before  { background: linear-gradient(180deg, #cbd5e1, #94a3b8); }
.absa-card--negative::before { background: linear-gradient(180deg, #f87171, #ef4444); }

.absa-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.absa-aspect {
  font-size: 15px;
  font-weight: 900;
  color: #0f172a;
  letter-spacing: 0.01em;
}
.absa-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
}
.absa-chip iconify-icon { font-size: 13px; }
.absa-chip--positive { background: rgba(16, 185, 129, 0.12); color: #047857; }
.absa-chip--neutral  { background: rgba(100, 116, 139, 0.12); color: #475569; }
.absa-chip--negative { background: rgba(239, 68, 68, 0.12); color: #b91c1c; }

.absa-evidence {
  margin-top: 8px;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  background: rgba(148, 163, 184, 0.08);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 12.5px;
  line-height: 1.55;
  color: #475569;
  font-style: italic;
}
.absa-evidence iconify-icon {
  font-size: 14px;
  color: #94a3b8;
  flex-shrink: 0;
  margin-top: 2px;
}

.absa-source-tip {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #94a3b8;
  margin: 4px 2px 0;
  line-height: 1.4;
}
.absa-source-tip iconify-icon { font-size: 13px; }

/* ABSA 骨架加载 */
.absa-loading {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 4px 2px;
}
.absa-skeleton {
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  padding: 12px 14px;
}
.sk-bar {
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(90deg, #f1f5f9 0%, #e2e8f0 50%, #f1f5f9 100%);
  background-size: 200% 100%;
  animation: sk-shimmer 1.4s linear infinite;
}
.sk-bar-aspect { width: 38%; margin-bottom: 8px; }
.sk-bar-evi { width: 86%; height: 10px; }
@keyframes sk-shimmer { 0%{background-position:200% 0;} 100%{background-position:-200% 0;} }
.absa-loading-text {
  text-align: center;
  font-size: 12px;
  color: #64748b;
  margin: 4px 0 0;
}

/* ABSA 空态 */
.absa-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px 16px;
  background: rgba(148, 163, 184, 0.04);
  border: 1px dashed rgba(148, 163, 184, 0.3);
  border-radius: 14px;
}
.absa-empty iconify-icon { font-size: 36px; color: #cbd5e1; margin-bottom: 6px; }
.absa-empty-title { font-size: 13px; font-weight: 800; color: #475569; margin: 0 0 4px; }
.absa-empty-hint { font-size: 11.5px; color: #94a3b8; line-height: 1.55; max-width: 320px; margin: 0; }

/* B6: B 站评论 / 弹幕情绪聚合卡（已拆成两个独立 intel-box，左右铺在 .intel-visual-grid 里） */
.bili-sent-box .intel-label iconify-icon { color: #fb7299; }
.bili-sent-loading { padding: 8px 0; }
.bili-sent-count { margin-left: auto; font-size: 11px; color: #94a3b8; font-weight: 800; padding: 2px 8px; background: rgba(251,114,153,0.08); border-radius: 999px; letter-spacing: 0.02em; }
/* 单卡内：饼图在上、Top 列表在下，整张卡气场统一 */
.bili-sent-single { display: flex; flex-direction: column; gap: 12px; }
.bili-sent-pie { width: 100%; height: 220px; }
/* P4：列表使用相同最小/最大高度，让评论卡 vs 弹幕卡视觉上严格对齐 */
.bili-sent-top {
  list-style: none;
  margin: 0;
  padding: 8px 0 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  border-top: 1px dashed rgba(251,114,153,0.18);
  min-height: 200px;
  max-height: 240px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(251, 114, 153, 0.35) transparent;
}
.bili-sent-top::-webkit-scrollbar { width: 5px; }
.bili-sent-top::-webkit-scrollbar-thumb { background: rgba(251, 114, 153, 0.35); border-radius: 3px; }
.bili-sent-top li { display: flex; align-items: flex-start; gap: 8px; font-size: 12px; line-height: 1.5; color: #334155; padding: 4px 0; }
.bili-sent-likes { flex-shrink: 0; color: #fb7299; font-weight: 800; min-width: 38px; }
.bili-sent-time { flex-shrink: 0; color: #94a3b8; font-weight: 700; min-width: 38px; font-family: 'Fira Code', monospace; font-size: 11px; }
.bili-sent-text { flex: 1; word-break: break-word; }

.capsule-scroll-body { flex:1; overflow-y: auto; padding: 20px 32px 30px; }
.article-header-group { margin-bottom: 16px; display: grid; gap: 10px; }
.article-subject { font-size: clamp(24px, 2.2vw, 36px); font-weight: 900; letter-spacing: -0.05em; color: #0f172a; margin-bottom: 0; line-height: 1.08; max-width: 1120px; }
.article-meta-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.article-timestamp { font-size: 13px; color: #64748b; font-weight: 700; }

.premium-source-btn {
  display: inline-flex; align-items: center; gap: 8px; background: var(--color-surface); color: var(--color-accent);
  padding: 8px 16px; border-radius: 4px; font-size: 12px; font-weight: 600;
  text-decoration: none; border: 1px solid var(--color-border); transition: 0.18s;
  min-height: auto; height: auto; text-transform: none; letter-spacing: 0.04em;
}
.premium-source-btn:hover { background: var(--color-surface-2); border-color: var(--color-text-3); transform: translateY(-1px); }

.capsule-navigation-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; gap: 12px; flex-wrap: wrap; }
.capsule-actions { display: flex; gap: 8px; align-items: center; }
.btn-export-pdf { display: flex; align-items: center; gap: 5px; font-weight: 700; font-size: 12px; border-radius: 10px; min-height: auto; height: 36px; text-transform: none; color: #dc2626; border-color: rgba(220, 38, 38, 0.2); }
.btn-export-pdf:hover { background: #dc2626; color: #fff; border-color: #dc2626; }
.capsule-tabs { background: var(--color-surface-2); padding: 4px; border-radius: 4px; display: flex; gap: 4px; border: 1px solid var(--color-border); }
.cap-tab { border:none; background: transparent; padding: 9px 14px; border-radius: 2px; font-size: 12px; font-weight: 600; color: var(--color-text-2); cursor: pointer; transition: 0.18s; min-height: auto; height: auto; text-transform: none; letter-spacing: 0.04em; }
.cap-tab.active { background: var(--color-text); color: var(--color-surface); }

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
  color: var(--color-accent); 
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
.report-body { font-size: 16px; line-height: 1.9; color: #1e293b; font-weight: 500; text-align: left; }
/* P3：AI 总结 markdown 渲染样式——与外部论述类似但专门调纯中文语义 */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) { font-weight: 900; color: #0f172a; margin: 18px 0 8px; line-height: 1.4; letter-spacing: -0.01em; }
.markdown-body :deep(h1) { font-size: 22px; }
.markdown-body :deep(h2) { font-size: 19px; padding-bottom: 6px; border-bottom: 1px solid var(--color-border); }
.markdown-body :deep(h3) { font-size: 17px; color: var(--color-accent); }
.markdown-body :deep(h4) { font-size: 15px; color: #334155; }
.markdown-body :deep(p) { margin: 8px 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 8px 0 8px 4px; padding-left: 22px; }
.markdown-body :deep(li) { margin: 4px 0; line-height: 1.75; }
.markdown-body :deep(li::marker) { color: var(--color-accent); font-weight: 800; }
.markdown-body :deep(strong) { color: #0f172a; font-weight: 900; }
.markdown-body :deep(em) { color: #475569; font-style: normal; background: linear-gradient(180deg, transparent 60%, rgba(250, 204, 21, 0.45) 60%); padding: 0 2px; }
.markdown-body :deep(blockquote) { margin: 12px 0; padding: 10px 14px; border-left: 3px solid var(--color-accent); background: var(--color-surface-2); border-radius: 0 4px 4px 0; color: var(--color-text-2); font-size: 14.5px; }
.markdown-body :deep(code) { background: rgba(15, 23, 42, 0.06); padding: 2px 6px; border-radius: 4px; font-family: 'Fira Code', monospace; font-size: 13px; color: #be185d; }
.markdown-body :deep(pre) { background: #0f172a; color: #e2e8f0; padding: 14px 16px; border-radius: 12px; overflow-x: auto; margin: 12px 0; }
.markdown-body :deep(pre code) { background: transparent; color: inherit; padding: 0; }
.markdown-body :deep(hr) { border: none; border-top: 1px dashed rgba(148, 163, 184, 0.4); margin: 16px 0; }
.markdown-body :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 14px; }
.markdown-body :deep(th),
.markdown-body :deep(td) { border: 1px solid rgba(148, 163, 184, 0.28); padding: 8px 10px; }
.markdown-body :deep(th) { background: var(--color-surface-2); font-weight: 600; color: var(--color-text); }
.markdown-body :deep(a) { color: var(--color-accent); text-decoration: underline; }

.report-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80px 24px; text-align: center;
  background: radial-gradient(circle at center, rgba(99, 102, 241, 0.05) 0%, transparent 70%);
  border-radius: 24px;
}
.report-empty iconify-icon { font-size: 48px; color: #94a3b8; margin-bottom: 14px; }
.report-empty .empty-title { font-size: 16px; font-weight: 700; color: #475569; margin: 0 0 6px; }
.report-empty .empty-hint { font-size: 13px; color: #64748b; margin: 0; max-width: 360px; line-height: 1.6; }
.report-empty .empty-hint strong { color: #4f46e5; font-weight: 700; }

/* 凭据失效提示卡片 */
.report-credential-error {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 64px 24px; text-align: center; gap: 6px;
  background: linear-gradient(135deg, rgba(248, 113, 113, 0.08) 0%, rgba(251, 146, 60, 0.06) 100%);
  border: 1px solid rgba(248, 113, 113, 0.25);
  border-radius: 20px;
}
.report-credential-error iconify-icon { font-size: 48px; color: #f97316; margin-bottom: 8px; }
.report-credential-error .empty-title { font-size: 16px; font-weight: 800; color: #b91c1c; margin: 0 0 4px; }
.report-credential-error .empty-hint { font-size: 13px; color: #475569; margin: 0; max-width: 420px; line-height: 1.7; }
.report-credential-error .empty-hint strong { color: #b91c1c; font-weight: 700; }

.analysis-spinner { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 100px 0; background: radial-gradient(circle at center, rgba(37, 99, 235, 0.05) 0%, transparent 70%); border-radius: 30px; }
.aura-spin { 
  width: 52px; height: 52px; 
  border: 3px solid var(--color-border); 
  border-top-color: var(--color-accent); 
  border-radius: 50%; 
  animation: spin 0.8s cubic-bezier(0.4, 0, 0.2, 1) infinite; 
  margin: 0 auto 24px;
  box-shadow: 0 0 12px rgba(180, 83, 9, 0.15);
}
.status-bright-text { color: #60a5fa; font-size: 14px; font-weight: 800; letter-spacing: 0.06em; text-shadow: 0 0 12px rgba(96, 165, 250, 0.4); }
.panel-visual--idle .status-bright-text { color: #475569; }
.panel-visual--idle .aura-spin { border-color: var(--color-border); border-top-color: var(--color-accent); box-shadow: none; }
.panel-visual--idle .empty-vis iconify-icon { color: rgba(148,163,184,0.3); }

.empty-vis { text-align: center; padding: 110px 0; position: relative; }
.empty-vis--error { padding: 70px 24px; }
.empty-vis--error .err-detail {
  margin: 12px auto 6px; max-width: 560px; color: #475569; font-size: 13px;
  background: rgba(239, 68, 68, 0.06); border: 1px solid rgba(239, 68, 68, 0.18);
  padding: 10px 14px; border-radius: 10px; font-family: "Fira Code", monospace; word-break: break-all;
}
.empty-vis--error .err-hint { margin: 4px auto 16px; max-width: 560px; color: #64748b; font-size: 12px; line-height: 1.6; }
.vis-error-banner {
  display: flex; align-items: center; gap: 10px;
  margin: 0 0 14px; padding: 10px 14px;
  background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.22);
  border-radius: 10px; color: #b91c1c; font-size: 13px;
}
.vis-error-banner iconify-icon { font-size: 20px; flex: 0 0 auto; color: #ef4444; }
.vis-error-banner__body { flex: 1 1 auto; word-break: break-all; line-height: 1.6; }
.vis-error-banner__retry { flex: 0 0 auto; background: #ef4444; color: #fff; border: 0; }
.vis-error-banner__retry:hover { background: #dc2626; color: #fff; }
.empty-vis iconify-icon { font-size: 48px; color: var(--color-text-3); margin-bottom: 24px; }
.btn-empty-sync {
  margin-top: 24px;
  background: var(--color-text);
  color: var(--color-surface);
  border: none;
  padding: 10px 24px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  cursor: pointer;
  transition: background 0.18s ease, transform 0.18s ease;
  min-height: auto;
  height: auto;
  text-transform: none;
}
.btn-empty-sync:hover { background: var(--color-accent); transform: translateY(-1px); }

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

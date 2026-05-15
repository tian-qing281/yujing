/**
 * Yujing Data Standard (YDS) Adapter
 * 统一各平台爬虫数据结构，实现归一化处理
 * （历史别名：HDS / Hongsou Data Standard）
 */

const SOURCE_CONFIG = {
  weibo_hot_search: { name: '微博', icon: 'ri:weibo-fill' },
  baidu_hot: { name: '百度', icon: 'ri:baidu-fill' },
  toutiao_hot: { name: '头条', icon: 'ri:fire-line' },
  bilibili_hot_video: { name: 'B站', icon: 'ri:bilibili-fill' },
  zhihu_hot_question: { name: '知乎', icon: 'ri:zhihu-fill' },
  thepaper_hot: { name: '澎湃', icon: 'ri:newspaper-line' },
  wallstreetcn_news: { name: '华见', icon: 'ri:line-chart-line' },
  cls_telegraph: { name: '财联社', icon: 'ri:flashlight-line' }
};

/**
 * 核心转换函数
 * @param {object} rawItem 原始数据
 * @param {string} sourceId 平台 id（可选，缺省时从 rawItem.source_id 取）
 * @param {number} listIndex 该条在当前平台列表中的 0-based 下标，作为 rank 兜底
 */
export function transformToHDS(rawItem, sourceId = '', listIndex) {
  const sid = sourceId || rawItem.source_id;
  const config = SOURCE_CONFIG[sid] || { name: '未知来源', icon: 'ri:link-m' };
  
  // 提取原始指标
  const extra = parseExtraInfo(rawItem.extra_info);
  
  return {
    ...rawItem,
    id: rawItem.id || `unf-${Date.now()}-${Math.random()}`,
    title: (rawItem.title || '').trim(),
    summary: (rawItem.ai_summary || extra.desc || extra.excerpt || '').trim(),
    content: rawItem.content || rawItem.raw_content || '',
    publishedAt: rawItem.pub_date || rawItem.fetch_time || new Date().toISOString(),
    
    // 来源统一
    source: {
      id: sid,
      name: config.name,
      icon: config.icon,
      url: rawItem.url || extra.origin_url || ''
    },

    // 影响力归一化 (0-100)
    impactScore: calculateImpactScore(sid, rawItem, extra, listIndex),
    
    // 情报深度指标 (0-100)
    intelDepth: calculateIntelDepth(rawItem),

    // 原始字段保留用于向后兼容
    raw: rawItem,
    extra: extra,
    wordcloud: rawItem.wordcloud || [],
    emotions: rawItem.emotions || []
  };
}

/**
 * 解析 extra_info 字符串
 */
function parseExtraInfo(info) {
  if (!info) return {};
  if (typeof info === 'object') return info;
  try {
    return JSON.parse(info);
  } catch (e) {
    return {};
  }
}

/**
 * 归一化热度值计算（Batch IV / F1）
 * - rank 兜底：rawItem.rank 缺失时用列表 index+1（百度/头条/B站/知乎爬虫未带 rank）
 * - 平台差异化 bonus：
 *   微博 hot_score / 200_000        头条 hot_value / 200_000_000
 *   百度 hot_score / 1_000_000      知乎 view_count / 1_000_000
 *   B 站 view / 500_000             澎湃/华见/财联社 已自带 rank，无 bonus
 * - 基础分梯度放宽到 25-100，让 50 名后也有梯度（原 max(40, ...) 把 41 名后全压到 40）
 */
function calculateImpactScore(sourceId, item, extra, listIndex) {
  // listIndex 来自前端 *按平台分组后的* 0-based 下标（榜单内排名 - 1）；
  // 仅当未传 listIndex 时回退用 rawItem.rank（部分爬虫给定）；99 是后端默认占位，不能信。
  const rawRank = Number(item.rank);
  const rank = Number.isInteger(listIndex)
    ? listIndex + 1
    : (rawRank && rawRank !== 99 ? rawRank : 99);
  // 1-30 名 → 91-50 分；30-50 名 → 50-25 分；为 bonus 留 8 分顶部空间，避免被 clamp 抹平
  const baseScore = Math.max(25, Math.round(92 - rank * 1.4));

  let bonus = 0;
  if (sourceId === 'weibo_hot_search') {
    bonus = Math.min(8, (Number(extra.hot_score) || 0) / 500000);
  } else if (sourceId === 'zhihu_hot_question') {
    bonus = Math.min(8, (Number(extra.view_count) || 0) / 3000000);
  } else if (sourceId === 'bilibili_hot_video') {
    bonus = Math.min(8, (Number(extra.view) || 0) / 1500000);
  } else if (sourceId === 'baidu_hot') {
    bonus = Math.min(8, (Number(extra.hot_score) || 0) / 5000000);
  } else if (sourceId === 'toutiao_hot') {
    bonus = Math.min(8, (Number(extra.hot_value) || 0) / 800000000);
  }

  return Math.min(100, Math.round(baseScore + bonus));
}

/**
 * 按 source_id 分组，对同源条目按 0-based 序号重算 impactScore。
 * 用于榜单页（filteredArticles 单源展示）—— 第一名永远 ≈99，与该源整体在
 * 全局 articles 中的位置无关。
 * @param {Array} list 已 transformToHDS 过的数组（会就地修改 impactScore）
 * @returns {Array} 同一 list（链式方便）
 */
export function recomputeImpactByGroup(list) {
  const counters = {};
  for (const it of list) {
    const sid = it.source_id || it.source?.id || 'unknown';
    const idx = counters[sid] || 0;
    counters[sid] = idx + 1;
    const extra = it.extra || parseExtraInfo(it.extra_info);
    it.impactScore = calculateImpactScore(sid, it, extra, idx);
  }
  return list;
}

/**
 * 计算情报深度 (基于内容完整度)
 */
function calculateIntelDepth(item) {
  let depth = 0;
  if (item.ai_summary) depth += 40;
  if (item.content || item.raw_content) depth += 30;
  if (item.wordcloud?.length > 0) depth += 20;
  if (item.emotions?.length > 0) depth += 10;
  return depth;
}

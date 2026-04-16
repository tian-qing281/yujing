/**
 * Hongsou Data Standard (HDS) Adapter
 * 统一各平台爬虫数据结构，实现归一化处理
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
 */
export function transformToHDS(rawItem, sourceId = '') {
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
    impactScore: calculateImpactScore(sid, rawItem, extra),
    
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
 * 归一化热度值计算
 */
function calculateImpactScore(sourceId, item, extra) {
  const rank = Number(item.rank) || 99;
  
  // 基础分数由排名决定（1-50名 -> 95-60分）
  let baseScore = Math.max(40, 100 - (rank * 1.5));
  
  // 附件加成逻辑
  let bonus = 0;
  if (sourceId === 'weibo_hot_search') {
    const hotValue = Number(extra.hot_score || 0);
    bonus = Math.min(10, hotValue / 200000); 
  } else if (sourceId === 'zhihu_hot_question') {
    const heatValue = parseFloat(extra.hot_score || 0); // 知乎通常是 "xxxx 万"
    bonus = Math.min(10, heatValue / 100);
  } else if (sourceId === 'bilibili_hot_video') {
    const views = Number(extra.view) || 0;
    bonus = Math.min(10, views / 500000);
  }
  
  return Math.min(100, Math.round(baseScore + bonus));
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

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
 * 归一化热度值计算（Batch IV / F1 / J-K）
 * - rank 优先级：listIndex（前端分组下标）> rawItem.rank（后端落库值，J/K 后已全平台真实）
 *   仅在两者都缺时才回退 99 占位（实际不会发生，base.py setdefault 已兜底）。
 * - 平台差异化 bonus：
 *   微博 hot_score / 200_000        头条 hot_value / 200_000_000
 *   百度 hot_score / 1_000_000      知乎 view_count / 1_000_000
 *   B 站 view / 500_000             澎湃/华见/财联社 已自带 rank，无 bonus
 * - 基础分梯度放宽到 25-100，让 50 名后也有梯度（原 max(40, ...) 把 41 名后全压到 40）
 */
function calculateImpactScore(sourceId, item, extra, listIndex) {
  // listIndex 来自前端 *按平台分组后的* 0-based 下标（榜单内排名 - 1）；
  // 未传 listIndex 时回退用 rawItem.rank（J/K 后端修复后此路径已是真实排名）。
  const rawRank = Number(item.rank);
  const rank = Number.isInteger(listIndex)
    ? listIndex + 1
    : (rawRank && rawRank !== 99 && rawRank !== 999 ? rawRank : 99);
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

  // T2 修复：硬上限 99 而不是 100，留 1 分作为「不可达上限」隔离带；
  // 即便未来 baseScore + bonus 超 100，也不会出现两条都顶到 100 的视觉撞顶。
  return Math.min(99, Math.round(baseScore + bonus));
}

/**
 * 按 source_id 分组，对同源条目按 0-based 序号重算 impactScore。
 *
 * 适用场景与语义：
 *  - 榜单页（articles.value 按平台原序追加）：序号即「该源榜单内排名」，语义准确。
 *  - 搜索页（searchedArticles 按相关度排序）：序号是「当前搜索结果中本源的命中顺序」，
 *    本质是「检索相关度近似排名」而非「平台原始热度排名」。当前 UX 借此让搜索结果
 *    也能展示影响指数 chip，避免后端 rank=99 占位导致的全 25 塌底；后续若需严谨
 *    可在搜索路径渲染「相关度」标签替代影响指数（属 NewsCard 视觉变更，本期不动）。
 *
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
 * F7：影响指数可解释拆解
 * 给定 item 反推 baseScore + bonus + 平台权重维度的人话说明，供 NewsCard tooltip 使用。
 * 不修改 item，纯只读计算。
 */
const SOURCE_NAME_MAP = {
  weibo_hot_search: '微博', baidu_hot: '百度', toutiao_hot: '头条',
  bilibili_hot_video: 'B 站', zhihu_hot_question: '知乎',
  thepaper_hot: '澎湃', wallstreetcn_news: '华尔街见闻', cls_telegraph: '财联社',
};
const BONUS_FIELD_MAP = {
  weibo_hot_search: { field: 'hot_score', divisor: 500000, label: '微博热度值' },
  zhihu_hot_question: { field: 'view_count', divisor: 3000000, label: '知乎浏览量' },
  bilibili_hot_video: { field: 'view', divisor: 1500000, label: 'B 站播放量' },
  baidu_hot: { field: 'hot_score', divisor: 5000000, label: '百度热度值' },
  toutiao_hot: { field: 'hot_value', divisor: 800000000, label: '头条热度值' },
};

export function explainImpact(item, listIndex) {
  if (!item) return '';
  const sid = item.source_id || item.source?.id || 'unknown';
  const extra = item.extra || parseExtraInfo(item.extra_info);
  const rawRank = Number(item.rank);
  const rank = Number.isInteger(listIndex)
    ? listIndex + 1
    : (rawRank && rawRank !== 99 && rawRank !== 999 ? rawRank : 99);
  const baseScore = Math.max(25, Math.round(92 - rank * 1.4));

  const bonusCfg = BONUS_FIELD_MAP[sid];
  const bonusRaw = bonusCfg ? (Number(extra[bonusCfg.field]) || 0) / bonusCfg.divisor : 0;
  const bonus = Math.min(8, bonusRaw);
  const total = Math.min(99, Math.round(baseScore + bonus));

  const sourceName = SOURCE_NAME_MAP[sid] || sid;
  const lines = [
    `${sourceName} · 第 ${rank} 名`,
    `基础分 ${baseScore}（按榜内排名）`,
  ];
  if (bonusCfg) {
    const rawValue = Number(extra[bonusCfg.field]) || 0;
    lines.push(`${bonusCfg.label} ${rawValue.toLocaleString()} → 加权 +${bonus.toFixed(1)}（上限 +8）`);
  } else {
    lines.push('该平台仅按排名计分，无热度加权');
  }
  lines.push(`合计影响指数 ${total} / 99`);
  return lines.join('\n');
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

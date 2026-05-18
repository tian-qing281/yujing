const rawApiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '').trim()

const normalizedApiBaseUrl = rawApiBaseUrl.endsWith('/')
  ? rawApiBaseUrl.slice(0, -1)
  : rawApiBaseUrl

export function buildApiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return normalizedApiBaseUrl ? `${normalizedApiBaseUrl}${normalizedPath}` : normalizedPath
}

// DEMO_MODE 总开关（与后端 YUJING_DEMO_MODE 对齐）。
// 启用时前端可拉长轮询、静默错误 toast，避免答辩现场出红条。
// 在 .env.local 或 .env.demo 中设置 VITE_DEMO_MODE=1 启用。
export const IS_DEMO = String(import.meta.env.VITE_DEMO_MODE || '').trim() === '1'

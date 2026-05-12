// markdown 渲染统一封装：AI 总结 / 早报 / 对话气泡共用
// - marked：低开销解析器
// - DOMPurify：白名单清洗，防 XSS
// - 关闭 mangle / headerIds（早报中文标题不需要）

import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({
  gfm: true,
  breaks: true,
  mangle: false,
  headerIds: false,
})

// 渲染并清洗，返回安全 HTML 字符串。空输入返回空串。
export function renderMarkdown(src) {
  if (!src || typeof src !== 'string') return ''
  try {
    const html = marked.parse(src)
    return DOMPurify.sanitize(html, {
      USE_PROFILES: { html: true },
    })
  } catch (e) {
    console.warn('[markdown] 渲染失败，回退原文', e)
    // 回退：保留换行
    return DOMPurify.sanitize(src.replace(/\n/g, '<br/>'))
  }
}

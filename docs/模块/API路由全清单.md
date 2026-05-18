# 模块 · API 路由全清单

> 最后更新 2026-05-18 · 主入口 [app/api/routes.py](../../app/api/routes.py) · 共 50+ 端点，分 11 组

## A. 热搜同步与文章

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sync` | 触发全 8 源并发同步 |
| GET | `/api/sync/status` | 同步进度 `{phase, errors}` |
| GET | `/api/platform-hubs` | 各平台 TopN 汇总（SWR 缓存）|
| GET | `/api/articles` | 文章分页 `?page&size&sort` |
| GET | `/api/articles/{id}` | 文章详情 |
| POST | `/api/articles/{id}/analyze` | 深度分析（Jina Reader + LLM 摘要 + ABSA）|
| GET | `/api/articles/{id}/content` | 仅取爬下来的正文 markdown |
| POST | `/api/articles/search` | 文章全文搜（Meili / FTS5 兜底）|

## B. 事件

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/events` | 事件分页 |
| GET | `/api/events/{id}` | 事件详情 + 代表文章 |
| POST | `/api/events/search` | 事件搜索 |
| GET | `/api/events/{id}/timeline` | 事件时间线（按文章 published_at）|
| GET | `/api/events/{id}/sentiment` | 8 分类情感分布 + 时序桶 |

## C. 主题

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/topics` | 主题分页 |
| GET | `/api/topics/{id}` | 主题详情（含事件列表）|
| POST | `/api/topics/search` | 主题搜索 |

## D. 语义检索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/semantic/neighbors?article_id=&topk=` | 相似文章 |
| GET | `/api/semantic/index-status` | 索引规模 / 上次构建时间 |

## E. 个性化推荐 & 画像

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/profile` | 用户画像（含 manual_tags）|
| POST | `/api/profile/track` | 行为埋点 `{article_id, action}` |
| GET | `/api/recommendations?limit=` | 融合打分推荐 |
| DELETE | `/api/profile/source/{source_id}` | 删除偏好源 |
| DELETE | `/api/profile/tag?tag=xxx` | 删除自动标签（加 blacklist）|
| POST | `/api/profile/tag` | 添加手动标签 `{tag}` |
| POST | `/api/profile/reset` | **重置整体画像**（清空所有推断数据）|

## F. 订阅 & 屏蔽

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/subscriptions` | 创建订阅 `{kind, value, weight}` |
| GET | `/api/subscriptions` | 查询订阅 |
| DELETE | `/api/subscriptions/{id}` | 删除订阅 |
| POST | `/api/blocklist` | 添加屏蔽词 `{term}` |
| GET | `/api/blocklist` | 查询屏蔽词 |
| DELETE | `/api/blocklist/{id}` | 删除屏蔽词 |

## G. 对比分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ai/compare` | 平台 A vs B 综合对比 `{platform_a, platform_b, topic_event_id?}` |
| POST | `/api/ai/compare-events` | 多事件对比 `{event_ids}` |

## H. AI 服务

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ai/chat` | Agent 流式对话（SSE）|
| GET | `/api/ai/morning_brief` | 当日早报（流式生成）|
| GET | `/api/ai/morning_brief/cached` | 当日早报（缓存命中）|

## I. Cookie

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/cookies/save` | 写入 cookies/{source_id}.txt |
| GET | `/api/cookies/check/{source_id}` | 验证有效性 |

## J. 报告导出

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/reports/export` | Word/PPT 导出 `{format, title, sections}` |

## K. 管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/admin/events/rebuild` | 全量重建事件 `?semantic=1&lookback_hours=72` |
| POST | `/admin/events/incremental` | 触发一次增量聚类 |
| POST | `/admin/semantic/index` | 重建 FAISS `?lookback_hours=72` |
| GET | `/admin/health` | 健康检查 `{status: "ok"}` |

---

## 全局状态

| 名称 | 用途 |
|------|------|
| `swr_cache` | 平台/事件/主题内存缓存（Stale-While-Revalidate）|
| `swr_state_lock` | SWR 异步锁 |
| `_analyze_global_semaphore` | 深度分析并发 ≤ 3 |
| `_analyze_inflight` | 同文章去重（`article_id → asyncio.Event`）|

## SSE 事件协议（`/api/ai/chat`）

| event | data | 含义 |
|-------|------|------|
| `step` | `{step, tool, args}` | 工具被调用 |
| `tool_result` | `{step, result}` | 工具返回 |
| `token` | `"文本片段"` | LLM 流式输出 |
| `done` | `{total_steps}` | 对话结束 |
| `error` | `{message}` | 出错 |

## CORS

`CORS_ALLOW_ORIGINS=http://localhost:5173`（默认）。生产改成实际域名。

## OpenAPI

启动后 `GET /docs` 自动生成 Swagger UI；`GET /openapi.json` 获取规范 JSON。

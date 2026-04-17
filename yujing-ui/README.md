# Yujing UI

这是 `yujing`（舆镜）项目的前端工作台，基于 Vue 3 + Vite。

当前前端不是模板页，而是一个已经拆成多工作区的分析界面：

- 平台热榜页
- 全景事件聚合页
- AI 研判中心

## 目录结构

`src/` 里的主要模块：

- `App.vue`
  - 主工作台入口
- `components/NewsCard.vue`
  - 文章热榜卡片
- `components/AnalysisModal.vue`
  - 文章详情与分析弹窗
- `components/EventCard.vue`
  - 事件卡片
- `components/EventModal.vue`
  - 事件详情弹窗
- `components/TopicCard.vue`
  - 话题卡片
- `components/TopicModal.vue`
  - 话题详情与宏观分析弹窗
- `components/AIConsultant.vue`
  - 本地检索问答工作台
- `components/CredentialModal.vue`
  - Cookie 配置弹窗
- `config/api.js`
  - API 地址构造工具

## 开发命令

安装依赖：

```powershell
npm install
```

启动开发环境：

```powershell
npm run dev
```

构建：

```powershell
npm run build
```

预览：

```powershell
npm run preview
```

## 联调说明

当前前端默认与后端 `http://localhost:8000` 联调。

虽然项目里已经有 `src/config/api.js`，但当前多数请求仍直接写死到了后端本地地址，因此：

- 联调时请先启动后端
- 默认后端地址请保持为 `http://localhost:8000`

## 当前状态

已经成型：

- 平台热榜浏览
- 文章详情分析
- AI 研判中心
- 事件 / 话题浏览和下钻

仍在继续完善：

- Event / Topic 结果呈现细节
- 前端 API 地址统一配置
- 目录清理与模板残留清除

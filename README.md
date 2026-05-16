# 舆镜 YuJing

面向多源中文社交舆情的实时采集 · 情感分析 · 可视化仪表盘。

## 功能概览

- **多源采集**：微博、百度、头条、哔哩哔哩、知乎、澎湃、华尔街见闻、财联社等热榜
- **正文提取**：基于 Playwright 的 Reader 与多层降级（HTTP / 浏览器 / 凭据失败透明诊断）
- **情感分析**：八分类情感引擎（喜悦/愤怒/厌恶/悲伤/惊讶/中性/关注/质疑）+ DeepSeek LLM ABSA 方面级情感
- **可视化**：情感极性分布、舆情倾向 / ABSA、关键词云、核心实体雷达
- **AI 总结**：DeepSeek 流式 SSE
- **订阅与全景事件**：候选算法透明、命中状态、分页

## 快速开始

```bash
# 后端
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端
cd yujing-ui
npm install
npm run dev   # http://localhost:5173
```

环境变量见 [.env.example](.env.example)。

## 目录结构

| 目录 | 说明 |
| --- | --- |
| [app/](app/) | FastAPI 后端：采集、分析、API 路由 |
| [yujing-ui/](yujing-ui/) | Vue 3 + ECharts 前端 |
| [scripts/](scripts/) | 运维与一次性脚本 |
| [docs/](docs/) | 项目设计、算法、答辩、部署等文档 |
| [crawler/](crawler/) | 独立 B 站爬虫子模块 |
| [runtime/](runtime/) | 运行期模型缓存（不入库） |
| [_backups/](_backups/) | 历史备份快照（不入库） |

## 文档导航

- [项目说明](docs/项目说明.md)（合并版：定位 / 五层架构 / 数据 / 服务 / 算法 / 接口 / 表现 / 决策 / CHANGELOG / 目录依赖）
- [核心原理文档](docs/核心原理文档.md)（评分体系 + 排序策略 + tiebreaker + 12 分精排）
- [Agent 算法文档](docs/Agent算法文档.md)（11 工具 · Loop · 评测）
- [情感分析文档](docs/情感分析文档.md)（粗粒度 8 类 BERT）
- [ABSA 算法文档](docs/ABSA算法文档.md)（方面级 LLM 抽取 + 文件缓存）
- [聚类算法文档](docs/聚类算法文档.md)（BGE + FAISS + 双层 Otsu）
- [评测指标文档](docs/评测指标文档.md)
- [部署文档](docs/部署文档.md)
- [升级路线图](升级路线图.md)（未来升级规划 + W1-W7 历史里程碑）
- [更新内容](更新内容.md)（全部升级与修复总览 · CHANGELOG）
- [答辩准备清单](docs/答辩准备清单.md)
- [手稿（docx）](docs/手稿/)

## Agent 协作规范

详见 [AGENTS.md](AGENTS.md)。

## 许可

仅供"中国大学生计算机设计大赛"参赛及学术研究使用。

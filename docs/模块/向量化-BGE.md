# 模块 · 向量化（BGE Embedding）

> 最后更新 2026-05-18 · 主入口 [app/services/embedding_service.py](../../app/services/embedding_service.py)

## 1. 角色

为「聚类 / 语义检索 / 订阅 / 推荐」四条链路提供 **统一的 512 维文本向量**。是整个系统的语义基础设施。

## 2. 模型

| 项 | 值 |
|----|---|
| 模型名 | `BAAI/bge-small-zh-v1.5` |
| 维度 | 512 |
| 上下文 | 512 tokens |
| 量化 | float32（无量化）|
| 设备 | 自动 cuda / cpu |

选 small 不选 base：CPU 推理 16 篇/秒（base 仅 5 篇），C-MTEB 中文 STS 差距 < 0.05，性价比最优。

## 3. 编码流程

```python
def encode(texts: list[str]) -> np.ndarray:
    # 1. 截断到 EMBED_MAX_LENGTH = 128
    # 2. tokenize
    # 3. forward
    # 4. CLS token + L2 归一化
    # 5. 返回 (N, 512) float32
```

关键参数：

| 名称 | 默认 | 说明 |
|------|------|------|
| `EMBED_BATCH` | 16 | 批大小 |
| `EMBED_MAX_LENGTH` | 128 | tokenizer 截断 |
| `EMBED_DIM` | 512 | 输出维度 |
| L2 归一化 | 强制 | 让内积 = 余弦相似度 |

## 4. 三层缓存

```
┌───────────────────────────────────────┐
│ L0 进程内 LRU dict（默认 5000 条）    │  ← 热文章命中
└──────────────┬────────────────────────┘
               │ miss
               ▼
┌───────────────────────────────────────┐
│ L1 ArticleEmbedding 表（SQLite BLOB） │  ← 持久化
└──────────────┬────────────────────────┘
               │ miss
               ▼
┌───────────────────────────────────────┐
│ L2 BGE 真实推理                       │  ← 写回 L0 + L1
└───────────────────────────────────────┘
```

- 缓存键：`article_id`（持久化）/ `sha1(text)`（订阅向量等无主键场景）
- 命中率：稳定 80%+（爬虫去重后 + 单文章被多链路使用）

## 5. 调用方

| 调用方 | 用途 |
|--------|------|
| [semantic_cluster.py](../../app/services/semantic_cluster.py) | 全量聚类前批量向量化 |
| [incremental_cluster.py](../../app/services/incremental_cluster.py) | 新文章向量化挂载 |
| [semantic_index.py](../../app/services/semantic_index.py) | FAISS 全局索引重建 |
| [recommend_service.py](../../app/services/recommend_service.py) | 订阅向量 vs 事件 centroid 相似度 |
| [profile_inference.py](../../app/services/profile_inference.py) | 邻近事件相似度 |

## 6. 启动加载

```python
# main.py 启动时单例初始化
from sentence_transformers import SentenceTransformer
_model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device=DEVICE)
```

冷启 ≈ 5s（下载需 100MB，国内建议 `EMBED_USE_MIRROR=1`）。预热一次 dummy 推理后稳定 50-60ms/批。

## 7. 性能

| 场景 | 设备 | 速度 |
|------|------|------|
| 单批 16 篇 | CPU（i7-12700H）| ≈ 60 ms |
| 单批 16 篇 | GPU（4090）| ≈ 8 ms |
| 5000 篇全量 | CPU | ≈ 35 s |
| 5000 篇全量 | GPU | ≈ 5 s |
| 缓存命中 | - | ≈ 0.1 ms |

## 8. 已知限制

1. **中文为主**：英文混合场景需切 bge-m3
2. **128 token 截断**：长文章只编码 title + summary 前段
3. **进程内单例**：多 worker 部署会重复加载模型（4G 内存 × N）

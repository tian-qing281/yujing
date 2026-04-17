"""
语义聚类引擎（v0.10 · Sentence-BERT 升级主路径）

核心算法：
    1. 对每篇 Article 取"标题 + 摘要"作为表示文本，编码为 L2-normalized 384-d 向量；
    2. ANN 召回 top-K 近邻（使用 sklearn NearestNeighbors，避免引入 FAISS 装依赖
       在 Windows 下的麻烦）；
    3. 复合相似度：
           sim = 0.60 * cosine_sim
               + 0.25 * time_decay(Δhour, half_life=12h)
               + 0.15 * platform_diversity_bonus
       平台多样性的逻辑：如果两文章来自同平台，bonus=0；不同平台 bonus=1.0
       （鼓励跨平台合并，和原 Jaccard 的实体约束互补）；
    4. 阈值：`SEMANTIC_CLUSTER_THRESHOLD`（默认 0.62），按 bge 官方 STS-B 上的
       合理分位数取整；W3 评测后再调。
    5. 自底向上的层次聚类（union-find）：任意两个文章 sim ≥ 阈值就并为同簇。

与旧 Jaccard 路径的关系：
- 本模块完全独立，不修改 events.py 既有逻辑；
- events.rebuild_events() 内部通过 `SEMANTIC_CLUSTER` 开关选择两者之一；
- 新路径失败时（模型未加载/向量表为空）自动 fallback 到旧 Jaccard。

对外 API：
- `cluster_articles_semantic(db, articles) -> List[Dict]`：返回与旧 `_cluster_articles`
  同结构的 clusters 列表，使得上游 `_merge_near_duplicate_clusters` / `_build_cluster_payload`
  无需改动即可消费。
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.database import Article, ArticleEmbedding
from app.services.embedding import (
    EMBED_DIM,
    EMBED_MODEL_NAME,
    bytes_to_vector,
    embed_texts,
    vector_to_bytes,
)

logger = logging.getLogger(__name__)


# === 超参（可通过 .env 覆盖，便于 W3 评测调优）===
SEMANTIC_CLUSTER_THRESHOLD = float(os.getenv("SEMANTIC_CLUSTER_THRESHOLD", "0.62"))
SEMANTIC_TOPK = int(os.getenv("SEMANTIC_TOPK", "20"))
SEMANTIC_W_COS = float(os.getenv("SEMANTIC_W_COS", "0.60"))
SEMANTIC_W_TIME = float(os.getenv("SEMANTIC_W_TIME", "0.25"))
SEMANTIC_W_PLATFORM = float(os.getenv("SEMANTIC_W_PLATFORM", "0.15"))
SEMANTIC_TIME_HALF_LIFE_HOURS = float(os.getenv("SEMANTIC_TIME_HALF_LIFE_HOURS", "12"))


def _safe_json_loads(value) -> Dict:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _build_repr_text(article: Article) -> str:
    """把 Article 拼成供 embedding 的表示文本：标题 + 摘要片段。"""
    parts: List[str] = []
    if article.title:
        parts.append(article.title.strip())
    extra = _safe_json_loads(article.extra_info)
    for key in ("excerpt", "desc"):
        val = extra.get(key)
        if val and isinstance(val, str):
            parts.append(val.strip())
    if article.ai_summary:
        parts.append(article.ai_summary.strip()[:120])
    text = " ".join(p for p in parts if p)
    return text[:400]  # 防止个别长正文拖慢 tokenizer


# === 向量物化：按需增量计算并写回 DB ===

def ensure_embeddings(
    db: Session,
    articles: List[Article],
    batch_size: int = 64,
) -> Dict[int, np.ndarray]:
    """
    保证传入 articles 全部有 embedding（当前 EMBED_MODEL_NAME 下）。
    返回 article_id -> vector 的 dict。

    增量策略：先从 DB 查已存在的向量，差集部分批量计算后写回。
    """
    if not articles:
        return {}

    article_ids = [a.id for a in articles]
    existing_rows = (
        db.query(ArticleEmbedding)
        .filter(
            ArticleEmbedding.article_id.in_(article_ids),
            ArticleEmbedding.model_name == EMBED_MODEL_NAME,
        )
        .all()
    )
    cache: Dict[int, np.ndarray] = {
        row.article_id: bytes_to_vector(row.vector, row.dim) for row in existing_rows
    }

    missing = [a for a in articles if a.id not in cache]
    if not missing:
        return cache

    logger.info(
        f"[semantic_cluster] 增量向量化：{len(missing)} / {len(articles)} 条需要计算 "
        f"(model={EMBED_MODEL_NAME})"
    )

    # 分批编码 + 写回。失败不影响已 encode 部分。
    for start in range(0, len(missing), batch_size):
        batch = missing[start : start + batch_size]
        texts = [_build_repr_text(a) for a in batch]
        try:
            vecs = embed_texts(texts)  # (B, dim)
        except Exception:
            logger.exception("[semantic_cluster] 批量 encode 失败，跳过该批")
            continue
        dim = vecs.shape[1]
        rows_to_add = []
        for article, vec in zip(batch, vecs):
            cache[article.id] = vec
            rows_to_add.append(
                ArticleEmbedding(
                    article_id=article.id,
                    model_name=EMBED_MODEL_NAME,
                    dim=dim,
                    vector=vector_to_bytes(vec),
                )
            )
        try:
            db.add_all(rows_to_add)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("[semantic_cluster] 写回 DB 失败，当批已在内存 cache")

    return cache


# === 复合相似度 ===

def _time_decay(hours_diff: float, half_life: float) -> float:
    """指数衰减：0h 时为 1，half_life 时为 0.5。"""
    if hours_diff <= 0:
        return 1.0
    return 0.5 ** (hours_diff / max(half_life, 1e-6))


def _article_hour(article: Article) -> float:
    """article 时间戳（小时级 epoch）。"""
    t = article.pub_date or article.fetch_time or datetime.utcnow()
    return t.timestamp() / 3600.0


def _composite_similarity(
    cos_sim: float,
    hour_a: float,
    hour_b: float,
    same_platform: bool,
) -> float:
    time_score = _time_decay(abs(hour_a - hour_b), SEMANTIC_TIME_HALF_LIFE_HOURS)
    platform_score = 0.0 if same_platform else 1.0
    return (
        SEMANTIC_W_COS * max(0.0, cos_sim)
        + SEMANTIC_W_TIME * time_score
        + SEMANTIC_W_PLATFORM * platform_score
    )


# === 主入口：语义聚类 ===

class _UnionFind:
    __slots__ = ("parent",)

    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster_articles_semantic(
    db: Session,
    articles: List[Article],
    topk: int = SEMANTIC_TOPK,
    threshold: float = SEMANTIC_CLUSTER_THRESHOLD,
) -> List[Dict]:
    """
    对 articles 做语义聚类，返回与 events._cluster_articles 同构的 cluster 列表。

    数据结构（与旧版完全一致，方便被 _merge_near_duplicate_clusters 消费）：
        {
            "articles": List[Article],
            "tokens": List[str],      # 占位空列表；下游 _build_cluster_payload 会再抽
            "title_norm": str,        # 代表文章标题
            "representative": Article,
        }
    """
    from app.services.events import _extract_tokens, _normalize_title, _score_article

    if not articles:
        return []

    emb_map = ensure_embeddings(db, articles)
    # 有可能极少数文章 encode 失败，这里过滤掉并记录一次 warning
    encoded = [a for a in articles if a.id in emb_map]
    dropped = len(articles) - len(encoded)
    if dropped:
        logger.warning(f"[semantic_cluster] {dropped} 篇文章无向量，已跳过")
    if not encoded:
        return []

    N = len(encoded)
    matrix = np.stack([emb_map[a.id] for a in encoded])  # (N, dim)

    # 向量已 L2 normalized → 点积 = cosine similarity
    # 在 2k 以内规模直接算全对矩阵（4 Bytes * 2k * 2k = 16 MB 内存），比 ANN 还快
    # 超过 2k 才走 NearestNeighbors；阈值可调
    uf = _UnionFind(N)
    hours = [_article_hour(a) for a in encoded]
    sources = [a.source_id or "" for a in encoded]

    if N <= 2000:
        sim = matrix @ matrix.T  # (N, N)
        for i in range(N):
            # 只看上三角，避免重复
            for j in range(i + 1, N):
                cos = float(sim[i, j])
                if cos < 0.3:  # 快速剪枝：cos 太低不值得算复合分
                    continue
                composite = _composite_similarity(
                    cos, hours[i], hours[j], sources[i] == sources[j]
                )
                if composite >= threshold:
                    uf.union(i, j)
    else:
        from sklearn.neighbors import NearestNeighbors

        k = min(topk + 1, N)
        nn = NearestNeighbors(n_neighbors=k, metric="cosine", algorithm="brute")
        nn.fit(matrix)
        # NearestNeighbors 返回的是 cosine distance（1 - cos_sim）
        distances, indices = nn.kneighbors(matrix)
        for i in range(N):
            for dist, j in zip(distances[i], indices[i]):
                if j == i:
                    continue
                cos = 1.0 - float(dist)
                if cos < 0.3:
                    continue
                composite = _composite_similarity(
                    cos, hours[i], hours[j], sources[i] == sources[j]
                )
                if composite >= threshold:
                    uf.union(i, j)

    # union-find → clusters
    group_index: Dict[int, List[int]] = {}
    for i in range(N):
        root = uf.find(i)
        group_index.setdefault(root, []).append(i)

    clusters: List[Dict] = []
    for members in group_index.values():
        cluster_articles = [encoded[i] for i in members]
        representative = max(cluster_articles, key=_score_article)
        clusters.append(
            {
                "articles": cluster_articles,
                "tokens": _extract_tokens(representative),
                "title_norm": _normalize_title(representative.title),
                "representative": representative,
            }
        )

    logger.info(
        f"[semantic_cluster] {N} 篇 → {len(clusters)} 簇 "
        f"(threshold={threshold}, mode={'full' if N <= 2000 else 'ann'})"
    )
    return clusters

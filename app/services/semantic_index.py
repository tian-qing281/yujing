from __future__ import annotations

import logging
import math
import os
import threading
import warnings
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app.runtime_warnings import suppress_known_dependency_warnings

with warnings.catch_warnings():
    suppress_known_dependency_warnings()
    import faiss
import numpy as np
from sqlalchemy.orm import Session

from app.database import Article, utcnow
from app.services.semantic_cluster import ensure_embeddings

logger = logging.getLogger(__name__)


SEMANTIC_INDEX_TOPK = int(os.getenv("SEMANTIC_INDEX_TOPK", "20"))
SEMANTIC_INDEX_NLIST = int(os.getenv("SEMANTIC_INDEX_NLIST", "64"))
SEMANTIC_INDEX_NPROBE = int(os.getenv("SEMANTIC_INDEX_NPROBE", "8"))
# --- 自适应阈值配置 ---
# 双层 Otsu 自动计算，无需手动设置百分位或固定阈值
# 数据不足时的回退值
SEMANTIC_THRESHOLD_FALLBACK = float(os.getenv("SEMANTIC_THRESHOLD_FALLBACK", "0.65"))
SEMANTIC_TIME_HALF_LIFE_HOURS = float(os.getenv("SEMANTIC_TIME_HALF_LIFE_HOURS", "12"))
SEMANTIC_W_COS = float(os.getenv("SEMANTIC_W_COS", "0.60"))
SEMANTIC_W_TIME = float(os.getenv("SEMANTIC_W_TIME", "0.25"))
SEMANTIC_W_PLATFORM = float(os.getenv("SEMANTIC_W_PLATFORM", "0.15"))


_state_lock = threading.Lock()
_semantic_index_state: Dict[str, object] = {
    "ready": False,
    "built_at": None,
    "count": 0,
    "lookback_hours": 0,
    "topk": SEMANTIC_INDEX_TOPK,
    "nlist": 0,
    "nprobe": 0,
    "threshold": SEMANTIC_THRESHOLD_FALLBACK,
    "threshold_p90": None,
    "threshold_p75": None,
    "candidate_pairs": 0,
    "cluster_count": 0,
    "cluster_sizes": [],
    "index": None,
    "article_ids": [],
    "articles": {},
    "vectors": {},
    "neighbors": {},
}


class _UnionFind:
    __slots__ = ("parent",)

    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        root = value
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[value] != root:
            self.parent[value], value = root, self.parent[value]
        return root

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[left_root] = right_root


def _safe_pub_time(article: Article) -> datetime:
    return article.pub_date or article.fetch_time or utcnow()


def _time_decay(hours_diff: float) -> float:
    if hours_diff <= 0:
        return 1.0
    return 0.5 ** (hours_diff / max(SEMANTIC_TIME_HALF_LIFE_HOURS, 1e-6))


def _composite_similarity(left: Article, right: Article, cosine_score: float) -> float:
    left_hour = _safe_pub_time(left).timestamp() / 3600.0
    right_hour = _safe_pub_time(right).timestamp() / 3600.0
    time_score = _time_decay(abs(left_hour - right_hour))
    platform_score = 0.0 if (left.source_id or "") == (right.source_id or "") else 1.0
    return (
        SEMANTIC_W_COS * max(0.0, float(cosine_score))
        + SEMANTIC_W_TIME * time_score
        + SEMANTIC_W_PLATFORM * platform_score
    )


def _otsu_threshold(values: np.ndarray, lo: float, hi: float, step: float = 0.005) -> float:
    """在 [lo, hi] 范围内用 Otsu 方法（最大类间方差）寻找最优二分割点。"""
    best_t, best_var = lo, 0.0
    for t in np.arange(lo, hi, step):
        c0 = values[values < t]
        c1 = values[values >= t]
        if len(c0) == 0 or len(c1) == 0:
            continue
        w0, w1 = len(c0) / len(values), len(c1) / len(values)
        var = w0 * w1 * (c0.mean() - c1.mean()) ** 2
        if var > best_var:
            best_var = var
            best_t = float(t)
    return best_t


def _compute_adaptive_thresholds(all_cosines: List[float]) -> Dict[str, Optional[float]]:
    """双层 Otsu 自适应阈值。

    第一层 Otsu：在全量 top-K cosine 上分割 → 噪声 vs 候选（过滤线）
    第二层 Otsu：在候选组内再分割 → 主题相似 vs 同事件（合并线）

    返回:
        p_filter: 噪声过滤线（硬门槛）
        p_merge:  合并阈值
        otsu_L1 / otsu_L2: 两层 Otsu 原始值（诊断用）
    """
    clean = np.array([float(s) for s in all_cosines if s > 0])
    if len(clean) < 50:
        return {
            "p_filter": SEMANTIC_THRESHOLD_FALLBACK,
            "p_merge": SEMANTIC_THRESHOLD_FALLBACK,
            "otsu_L1": None,
            "otsu_L2": None,
        }

    # 第一层 Otsu：噪声 vs 候选
    otsu_l1 = _otsu_threshold(clean, 0.30, 0.75)
    # 第二层 Otsu：在候选组(>= L1)内，主题相似 vs 同事件
    high_group = clean[clean >= otsu_l1]
    if len(high_group) < 20:
        otsu_l2 = otsu_l1
    else:
        otsu_l2 = _otsu_threshold(high_group, otsu_l1, 0.90)

    logger.info(
        "[semantic_index] 双层Otsu: L1(过滤)=%.4f, L2(合并)=%.4f, "
        "全量%d对, 候选组%d对",
        otsu_l1, otsu_l2, len(clean), len(high_group),
    )

    return {
        "p_filter": otsu_l1,
        "p_merge": otsu_l2,
        "otsu_L1": otsu_l1,
        "otsu_L2": otsu_l2,
    }


def _resolve_nlist(count: int, requested_nlist: int) -> int:
    if count <= 1:
        return 1
    return max(1, min(requested_nlist, int(math.sqrt(count)) or 1, count))


def _build_faiss_index(matrix: np.ndarray, article_ids: List[int], requested_nlist: int, nprobe: int):
    dim = int(matrix.shape[1])
    nlist = _resolve_nlist(len(article_ids), requested_nlist)
    quantizer = faiss.IndexFlatIP(dim)
    base_index = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
    base_index.train(matrix)
    index = faiss.IndexIDMap2(base_index)
    index.add_with_ids(matrix, np.asarray(article_ids, dtype=np.int64))
    index.nprobe = max(1, min(nprobe, nlist))
    return index, nlist, index.nprobe


def _collect_articles(db: Session, lookback_hours: int) -> List[Article]:
    cutoff = utcnow() - timedelta(hours=lookback_hours)
    return (
        db.query(Article)
        .filter(Article.fetch_time >= cutoff)
        .order_by(Article.fetch_time.desc(), Article.rank.asc())
        .all()
    )


def _search_neighbors(index, vector: np.ndarray, topk: int) -> List[Tuple[int, float]]:
    scores, ids = index.search(vector.reshape(1, -1), topk + 1)
    pairs: List[Tuple[int, float]] = []
    for article_id, score in zip(ids[0], scores[0]):
        if int(article_id) < 0:
            continue
        pairs.append((int(article_id), float(score)))
    return pairs


def _build_neighbor_graph(index, articles: Dict[int, Article], vectors: Dict[int, np.ndarray], topk: int):
    """收集全量 top-K 近邻及 cosine，不做任何硬门槛过滤。

    返回:
        neighbors: 每篇文章的近邻列表（含 cosine 和 composite）
        all_topk_cosines: 全量 cosine 列表（用于百分位计算）
        raw_pair_scores: 所有去重 pair 的最大 cosine
    """
    article_ids = list(articles.keys())
    neighbors: Dict[int, List[Dict[str, object]]] = {}
    all_topk_cosines: List[float] = []
    raw_pair_scores: Dict[Tuple[int, int], float] = {}

    for article_id in article_ids:
        article = articles[article_id]
        vector = vectors[article_id]
        items = []
        for neighbor_id, cosine_score in _search_neighbors(index, vector, topk):
            if neighbor_id == article_id or neighbor_id not in articles:
                continue
            cos_val = float(cosine_score)
            all_topk_cosines.append(cos_val)
            neighbor = articles[neighbor_id]
            composite = _composite_similarity(article, neighbor, cosine_score)
            items.append(
                {
                    "article_id": neighbor_id,
                    "cosine": round(cos_val, 4),
                    "composite": round(float(composite), 4),
                }
            )
            pair = (article_id, neighbor_id) if article_id < neighbor_id else (neighbor_id, article_id)
            previous = raw_pair_scores.get(pair)
            if previous is None or cos_val > previous:
                raw_pair_scores[pair] = cos_val
        items.sort(key=lambda item: item["cosine"], reverse=True)
        neighbors[article_id] = items[:topk]

    return neighbors, all_topk_cosines, raw_pair_scores


def _augment_exact_title_pairs(
    pair_scores: Dict[Tuple[int, int], float],
    articles: Dict[int, Article],
) -> int:
    """为 canonical title 完全一致的文章对补一条硬合并边。

    背景：少量完全同标题/同 canonical 标题的文章，虽然向量 cosine 很高，
    但可能被 IVF-Flat 的 ANN 召回漏掉，导致根本进不了 Union-Find 候选图。
    这里不改自适应阈值，只对这类强 lexical duplicate 直接注入一条 1.0 边。
    """
    from app.services.events import _canonicalize_title

    canonical_groups: Dict[str, List[int]] = {}
    for article_id, article in articles.items():
        canonical = _canonicalize_title(article.title)
        if not canonical:
            continue
        compact = canonical.replace(" ", "")
        if len(compact) < 6:
            continue
        canonical_groups.setdefault(canonical, []).append(article_id)

    injected = 0
    for article_ids in canonical_groups.values():
        if len(article_ids) < 2:
            continue
        ordered = sorted(article_ids)
        for left_index, left_id in enumerate(ordered):
            for right_id in ordered[left_index + 1 :]:
                pair = (left_id, right_id)
                previous = pair_scores.get(pair)
                if previous is None or previous < 1.0:
                    pair_scores[pair] = 1.0
                    injected += 1
    return injected


def _preview_clusters(article_ids: List[int], pair_scores: Dict[Tuple[int, int], float], threshold: float):
    positions = {article_id: index for index, article_id in enumerate(article_ids)}
    union_find = _UnionFind(len(article_ids))
    for (left_id, right_id), score in pair_scores.items():
        if score >= threshold:
            union_find.union(positions[left_id], positions[right_id])

    groups: Dict[int, List[int]] = {}
    for article_id, index in positions.items():
        root = union_find.find(index)
        groups.setdefault(root, []).append(article_id)

    clusters = sorted(groups.values(), key=len, reverse=True)
    return clusters


def _prepare_semantic_materials(
    db: Session,
    articles: List[Article],
    topk: int,
    requested_nlist: int,
    nprobe: int,
    batch_size: int,
) -> Dict[str, object]:
    embedding_map = ensure_embeddings(db, articles, batch_size=batch_size)
    encoded_articles = [article for article in articles if article.id in embedding_map]
    if not encoded_articles:
        raise RuntimeError("semantic index build failed: no embedded articles available")

    article_ids = [article.id for article in encoded_articles]
    vectors = {
        article.id: np.asarray(embedding_map[article.id], dtype=np.float32).reshape(-1)
        for article in encoded_articles
    }
    articles_by_id = {article.id: article for article in encoded_articles}
    matrix = np.stack([vectors[article_id] for article_id in article_ids]).astype(np.float32)
    index, resolved_nlist, resolved_nprobe = _build_faiss_index(matrix, article_ids, requested_nlist, nprobe)
    neighbors, all_topk_cosines, raw_pair_scores = _build_neighbor_graph(index, articles_by_id, vectors, topk)

    # 自适应双阈值：P75 过滤噪声，P90 合并决策
    thresholds = _compute_adaptive_thresholds(all_topk_cosines)
    p_filter = thresholds["p_filter"]
    p_merge = thresholds["p_merge"]

    # 用 P75 过滤 pair_scores（去噪 + 减少内存）
    pair_scores = {pair: cos for pair, cos in raw_pair_scores.items() if cos >= p_filter}

    injected_title_pairs = _augment_exact_title_pairs(pair_scores, articles_by_id)

    logger.info(
        "[semantic_index] 自适应阈值: P75(过滤)=%.4f, P90(合并)=%.4f, "
        "过滤前 %d 对 → 过滤后 %d 对, 同标题补边 %d 对",
        p_filter, p_merge, len(raw_pair_scores), len(pair_scores), injected_title_pairs,
    )

    clusters = _preview_clusters(article_ids, pair_scores, p_merge)
    return {
        "article_ids": article_ids,
        "articles_by_id": articles_by_id,
        "vectors": vectors,
        "index": index,
        "resolved_nlist": resolved_nlist,
        "resolved_nprobe": resolved_nprobe,
        "neighbors": neighbors,
        "all_topk_cosines": all_topk_cosines,
        "pair_scores": pair_scores,
        "forced_title_pairs": injected_title_pairs,
        "threshold": p_merge,
        "threshold_p90": thresholds["otsu_L2"],  # 合并阈值（二层Otsu）
        "threshold_p75": thresholds["otsu_L1"],  # 过滤阈值（一层Otsu）
        "clusters": clusters,
    }


def build_semantic_index(
    db: Session,
    lookback_hours: int = 720,
    topk: int = SEMANTIC_INDEX_TOPK,
    requested_nlist: int = SEMANTIC_INDEX_NLIST,
    nprobe: int = SEMANTIC_INDEX_NPROBE,
    batch_size: int = 64,
) -> Dict[str, object]:
    articles = _collect_articles(db, lookback_hours)
    if not articles:
        with _state_lock:
            _semantic_index_state.update(
                {
                    "ready": False,
                    "built_at": utcnow().isoformat(),
                    "count": 0,
                    "lookback_hours": lookback_hours,
                    "cluster_count": 0,
                    "cluster_sizes": [],
                    "candidate_pairs": 0,
                    "index": None,
                    "article_ids": [],
                    "articles": {},
                    "vectors": {},
                    "neighbors": {},
                }
            )
        return {"ok": True, "count": 0, "message": "no_articles"}

    materials = _prepare_semantic_materials(
        db,
        articles,
        topk=topk,
        requested_nlist=requested_nlist,
        nprobe=nprobe,
        batch_size=batch_size,
    )
    article_ids = materials["article_ids"]
    articles_by_id = materials["articles_by_id"]
    vectors = materials["vectors"]
    index = materials["index"]
    resolved_nlist = materials["resolved_nlist"]
    resolved_nprobe = materials["resolved_nprobe"]
    neighbors = materials["neighbors"]
    pair_scores = materials["pair_scores"]
    threshold = materials["threshold"]
    percentile_score = materials["threshold_p90"]
    clusters = materials["clusters"]
    built_at = utcnow().isoformat()

    with _state_lock:
        _semantic_index_state.update(
            {
                "ready": True,
                "built_at": built_at,
                "count": len(article_ids),
                "lookback_hours": lookback_hours,
                "topk": topk,
                "nlist": resolved_nlist,
                "nprobe": resolved_nprobe,
                "threshold": round(float(threshold), 4),
                "threshold_p90": round(float(percentile_score), 4) if percentile_score is not None else None,
                "candidate_pairs": len(pair_scores),
                "cluster_count": len(clusters),
                "cluster_sizes": [len(cluster) for cluster in clusters[:20]],
                "index": index,
                "article_ids": article_ids,
                "articles": articles_by_id,
                "vectors": vectors,
                "neighbors": neighbors,
            }
        )

    logger.info(
        "[semantic_index] built count=%s nlist=%s nprobe=%s topk=%s threshold=%.4f clusters=%s",
        len(article_ids),
        resolved_nlist,
        resolved_nprobe,
        topk,
        threshold,
        len(clusters),
    )
    return {
        "ok": True,
        "count": len(article_ids),
        "built_at": built_at,
        "lookback_hours": lookback_hours,
        "topk": topk,
        "nlist": resolved_nlist,
        "nprobe": resolved_nprobe,
        "threshold": round(float(threshold), 4),
        "threshold_p90": round(float(percentile_score), 4) if percentile_score is not None else None,
        "candidate_pairs": len(pair_scores),
        "cluster_count": len(clusters),
        "cluster_sizes": [len(cluster) for cluster in clusters[:10]],
    }


def cluster_articles_semantic_faiss(
    db: Session,
    articles: List[Article],
    topk: int = SEMANTIC_INDEX_TOPK,
    requested_nlist: int = SEMANTIC_INDEX_NLIST,
    nprobe: int = SEMANTIC_INDEX_NPROBE,
    batch_size: int = 64,
) -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    """
    正式事件聚合入口：返回与旧 `_cluster_articles` 兼容的簇结构。

    说明：
    - 底层走 Sentence-BERT + FAISS IVF-Flat + P95 自适应阈值；
    - 返回 clusters 时额外附带 `relation_scores`，供 events.py 落 EventArticle 时优先使用；
    - 不改写 Event/Article 表结构，保持对现有项目的最小侵入。
    """
    from app.services.events import _canonicalize_title, _extract_tokens, _normalize_title, _score_article

    if not articles:
        return [], {
            "count": 0,
            "nlist": 0,
            "nprobe": 0,
            "threshold": round(float(SEMANTIC_THRESHOLD_FALLBACK), 4),
            "threshold_p90": None,
            "candidate_pairs": 0,
            "cluster_count": 0,
        }

    materials = _prepare_semantic_materials(
        db,
        articles,
        topk=topk,
        requested_nlist=requested_nlist,
        nprobe=nprobe,
        batch_size=batch_size,
    )
    articles_by_id: Dict[int, Article] = materials["articles_by_id"]  # type: ignore[assignment]
    pair_scores: Dict[Tuple[int, int], float] = materials["pair_scores"]  # type: ignore[assignment]
    threshold = float(materials["threshold"])
    percentile_score = materials["threshold_p90"]
    raw_clusters: List[List[int]] = materials["clusters"]  # type: ignore[assignment]

    vectors: Dict[int, np.ndarray] = materials["vectors"]  # type: ignore[assignment]

    clusters: List[Dict[str, object]] = []
    expelled: List[int] = []  # 被簇内复核踢出的文章

    # 预计算 _score_article 的全局最大值，用于归一化
    all_hot_scores = [_score_article(a) for a in articles]
    max_hot = max(all_hot_scores) if all_hot_scores else 1.0
    if max_hot <= 0:
        max_hot = 1.0

    for cluster_ids in raw_clusters:
        cluster_articles = [articles_by_id[article_id] for article_id in cluster_ids if article_id in articles_by_id]
        if not cluster_articles:
            continue

        # 选代表：语义中心性(0.6) + 热度(0.4)
        # centrality = 文章与簇内其他成员的平均 cosine
        if len(cluster_articles) == 1:
            representative = cluster_articles[0]
            importance_scores = {representative.id: round(0.4 * _score_article(representative) / max_hot, 4)}
        else:
            cluster_vecs = {a.id: vectors.get(a.id) for a in cluster_articles}
            importance_scores = {}
            best_rep, best_score = cluster_articles[0], -1.0
            for a in cluster_articles:
                va = cluster_vecs.get(a.id)
                if va is None:
                    continue
                cos_sum = 0.0
                count = 0
                for b in cluster_articles:
                    if b.id == a.id:
                        continue
                    vb = cluster_vecs.get(b.id)
                    if vb is not None:
                        cos_sum += float(np.dot(va, vb))
                        count += 1
                centrality = cos_sum / count if count > 0 else 0.0
                hot_norm = _score_article(a) / max_hot
                combined = 0.6 * centrality + 0.4 * hot_norm
                importance_scores[a.id] = round(combined, 4)
                if combined > best_score:
                    best_score = combined
                    best_rep = a
            representative = best_rep

        # 簇内复核：成员与代表的 cosine 必须 >= threshold，
        # 否则踢出。解决 Union-Find 链式传染（A≈B, B≈C 但 A≠C）。
        rep_vec = vectors.get(representative.id)
        rep_canonical = _canonicalize_title(representative.title)
        verified = [representative]
        relation_scores: Dict[int, float] = {representative.id: 1.0}
        for article in cluster_articles:
            if article.id == representative.id:
                continue
            art_vec = vectors.get(article.id)
            if rep_vec is not None and art_vec is not None:
                cos_to_rep = float(np.dot(rep_vec, art_vec))
            else:
                cos_to_rep = 0.0
            same_canonical = (
                bool(rep_canonical)
                and rep_canonical == _canonicalize_title(article.title)
                and len(rep_canonical.replace(" ", "")) >= 6
            )
            if cos_to_rep < threshold and not same_canonical:
                expelled.append(article.id)
                continue
            # relation_score 用 composite 写入，仅供排序/诊断
            composite = _composite_similarity(representative, article, cos_to_rep)
            relation_scores[article.id] = round(float(composite), 4)
            verified.append(article)
        # 被踢出的文章不在 importance_scores 中，不需额外处理
        if not verified:
            continue
        clusters.append(
            {
                "articles": verified,
                "tokens": _extract_tokens(representative),
                "title_norm": _normalize_title(representative.title),
                "representative": representative,
                "relation_scores": relation_scores,
                "importance_scores": importance_scores,
            }
        )

    # 被踢出的文章各自成为独立单篇事件
    for article_id in expelled:
        article = articles_by_id.get(article_id)
        if not article:
            continue
        clusters.append(
            {
                "articles": [article],
                "tokens": _extract_tokens(article),
                "title_norm": _normalize_title(article.title),
                "representative": article,
                "relation_scores": {article.id: 1.0},
                "importance_scores": {article.id: round(0.4 * _score_article(article) / max_hot, 4)},
            }
        )
    if expelled:
        logger.info("[semantic_cluster] 簇内复核踢出 %d 篇离群文章", len(expelled))

    meta = {
        "count": len(materials["article_ids"]),
        "nlist": materials["resolved_nlist"],
        "nprobe": materials["resolved_nprobe"],
        "threshold": round(float(threshold), 4),
        "threshold_p90": round(float(percentile_score), 4) if percentile_score is not None else None,
        "candidate_pairs": len(pair_scores),
        "cluster_count": len(clusters),
    }
    return clusters, meta


def get_semantic_index_status() -> Dict[str, object]:
    with _state_lock:
        return {
            "ready": bool(_semantic_index_state["ready"]),
            "built_at": _semantic_index_state["built_at"],
            "count": _semantic_index_state["count"],
            "lookback_hours": _semantic_index_state["lookback_hours"],
            "topk": _semantic_index_state["topk"],
            "nlist": _semantic_index_state["nlist"],
            "nprobe": _semantic_index_state["nprobe"],
            "threshold": _semantic_index_state["threshold"],
            "threshold_p90": _semantic_index_state["threshold_p90"],
            "candidate_pairs": _semantic_index_state["candidate_pairs"],
            "cluster_count": _semantic_index_state["cluster_count"],
            "cluster_sizes": list(_semantic_index_state["cluster_sizes"]),
        }


def get_semantic_neighbors(article_id: int, limit: int = 10) -> Dict[str, object]:
    with _state_lock:
        if not _semantic_index_state["ready"]:
            raise RuntimeError("semantic index not ready")
        articles: Dict[int, Article] = _semantic_index_state["articles"]  # type: ignore[assignment]
        neighbors: Dict[int, List[Dict[str, object]]] = _semantic_index_state["neighbors"]  # type: ignore[assignment]
        threshold = float(_semantic_index_state["threshold"])

        if article_id not in articles:
            raise KeyError(f"article {article_id} not found in semantic index")

        source = articles[article_id]
        items = []
        for row in neighbors.get(article_id, [])[:limit]:
            neighbor = articles.get(int(row["article_id"]))
            if not neighbor:
                continue
            items.append(
                {
                    "article_id": neighbor.id,
                    "title": neighbor.title,
                    "source_id": neighbor.source_id,
                    "pub_date": _safe_pub_time(neighbor).isoformat(),
                    "cosine": row["cosine"],
                    "composite": row["composite"],
                    "above_threshold": bool(float(row["composite"]) >= threshold),
                }
            )

        return {
            "source": {
                "article_id": source.id,
                "title": source.title,
                "source_id": source.source_id,
                "pub_date": _safe_pub_time(source).isoformat(),
            },
            "threshold": round(threshold, 4),
            "neighbors": items,
        }


def get_semantic_cluster_preview(limit: int = 10) -> Dict[str, object]:
    with _state_lock:
        if not _semantic_index_state["ready"]:
            raise RuntimeError("semantic index not ready")
        article_ids: List[int] = list(_semantic_index_state["article_ids"])  # type: ignore[assignment]
        articles: Dict[int, Article] = _semantic_index_state["articles"]  # type: ignore[assignment]
        neighbors: Dict[int, List[Dict[str, object]]] = _semantic_index_state["neighbors"]  # type: ignore[assignment]
        threshold = float(_semantic_index_state["threshold"])

    pair_scores: Dict[Tuple[int, int], float] = {}
    for article_id, rows in neighbors.items():
        for row in rows:
            neighbor_id = int(row["article_id"])
            pair = (article_id, neighbor_id) if article_id < neighbor_id else (neighbor_id, article_id)
            score = float(row["composite"])
            previous = pair_scores.get(pair)
            if previous is None or score > previous:
                pair_scores[pair] = score

    clusters = _preview_clusters(article_ids, pair_scores, threshold)
    payload = []
    for cluster in clusters[:limit]:
        sample_titles = [articles[article_id].title for article_id in cluster[:3] if article_id in articles]
        payload.append(
            {
                "size": len(cluster),
                "article_ids": cluster[:12],
                "sample_titles": sample_titles,
            }
        )
    return {
        "threshold": round(threshold, 4),
        "cluster_count": len(clusters),
        "clusters": payload,
    }

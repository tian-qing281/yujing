"""
画像兴趣 tag 推断（V2 · v1.5）

背景：
- 原画像 tag_weights 仅来自 Article.extra_info.category，B 站/微博等热点源大多为空，
  导致「画像兴趣」维度在推荐打分中几乎是哑维度（命中率极低）。

方案：
1. 取 view_history 前 N 条，按行为权重加权聚合 article embedding → 用户兴趣向量 u（L2 归一）。
2. 用 u 在最近 D 天的文章里做 cosine TopK 邻近召回。
3. 把 TopK 文章的 keywords 按 (cosine × article_weight_in_history) 累加 → 推断 tag 权重。
4. 结果写入 UserProfile.data["inferred_tags"] + "inferred_at"，30 min TTL，避免每次推荐都重算。

接入：
- /profile：返回时若过期则重算，前端可展示「推断兴趣」chips。
- /recommendations：与原 tag_weights 融合（取 max），让 tag 维度真正参与排序。
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Dict, List, Tuple

import numpy as np
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import Article, ArticleEmbedding, EventArticle, Event, utcnow
from app.services.embedding import EMBED_MODEL_NAME

logger = logging.getLogger(__name__)


# 调参常量
HISTORY_LOOKBACK = 50           # 取最近 50 条浏览构建兴趣向量
NEIGHBOR_LOOKBACK_DAYS = 7      # 邻近召回候选：最近 7 天的文章
NEIGHBOR_TOPK = 80              # 召回 TopK 邻近文章
NEIGHBOR_MIN_COS = 0.55         # 邻近最低余弦阈值（低于则丢弃，BGE 同领域基线 0.5+）
INFERRED_TAG_TOPN = 20          # 输出推断 tag 数量上限
TTL_SECONDS = 1800              # 30 分钟缓存 TTL
MIN_HISTORY_FOR_INFER = 5       # 浏览不足 5 条不推断（冷启动）


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(vec))
    if n < 1e-9:
        return vec
    return (vec / n).astype(np.float32)


def _action_weight(record: dict) -> float:
    """与 routes.py 的权重规则保持一致：view=1, open=2, dwell=clamp(ms/5000,1,5)。"""
    action = record.get("action") or "view"
    if action == "dwell":
        return max(1.0, min(5.0, (record.get("dwell_ms") or 0) / 5000))
    if action == "open":
        return 2.0
    return 1.0


def build_user_interest_vector(
    db: Session, view_history: List[dict]
) -> Tuple[np.ndarray | None, Dict[int, float]]:
    """根据浏览历史聚合出用户兴趣向量 u（L2 归一）+ 历史文章 id→权重 字典。

    返回 (None, {}) 表示无可用数据（embedding 全缺）。
    """
    if not view_history:
        return None, {}

    # 收集 history 前 N 条且有 article_id 的记录
    article_weights: Dict[int, float] = {}
    for rec in view_history[:HISTORY_LOOKBACK]:
        aid = rec.get("article_id")
        if not aid:
            continue
        w = _action_weight(rec)
        # 同一篇文章多次浏览 → 累加权重
        article_weights[aid] = article_weights.get(aid, 0.0) + w

    if not article_weights:
        return None, {}

    aids = list(article_weights.keys())
    rows = (
        db.query(ArticleEmbedding.article_id, ArticleEmbedding.vector)
        .filter(
            ArticleEmbedding.article_id.in_(aids),
            ArticleEmbedding.model_name == EMBED_MODEL_NAME,
        )
        .all()
    )
    if not rows:
        return None, article_weights

    vecs = []
    weights = []
    for aid, vec_bytes in rows:
        try:
            v = np.frombuffer(vec_bytes, dtype=np.float32)
        except Exception:
            continue
        vecs.append(v)
        weights.append(article_weights[aid])

    if not vecs:
        return None, article_weights

    mat = np.stack(vecs).astype(np.float32)        # (N, dim)
    w = np.asarray(weights, dtype=np.float32).reshape(-1, 1)
    centroid = (mat * w).sum(axis=0) / max(w.sum(), 1e-9)
    centroid = _l2_normalize(centroid)
    return centroid, article_weights


def infer_tags_from_history(
    db: Session, view_history: List[dict]
) -> Tuple[List[Tuple[str, float]], dict]:
    """主入口：返回 [(tag, score), ...] + 元信息（用于写回 profile 缓存）。

    元信息字段：
      - history_used: 实际参与构建的文章数
      - candidates: 邻近召回候选数
      - neighbors_kept: 阈值过滤后保留的邻近数
    """
    meta = {"history_used": 0, "candidates": 0, "neighbors_kept": 0}
    if len(view_history) < MIN_HISTORY_FOR_INFER:
        return [], meta

    centroid, article_weights = build_user_interest_vector(db, view_history)
    if centroid is None:
        return [], meta
    meta["history_used"] = len(article_weights)

    # 邻近召回：最近 D 天的文章 embedding
    cutoff = utcnow() - timedelta(days=NEIGHBOR_LOOKBACK_DAYS)
    # 邻近召回：最近 D 天的文章 embedding；keywords 通过 EventArticle 关联到 Event 取
    cutoff = utcnow() - timedelta(days=NEIGHBOR_LOOKBACK_DAYS)
    cand_rows = (
        db.query(
            ArticleEmbedding.article_id,
            ArticleEmbedding.vector,
            Event.keywords,
        )
        .join(Article, Article.id == ArticleEmbedding.article_id)
        .join(EventArticle, EventArticle.article_id == Article.id)
        .join(Event, Event.id == EventArticle.event_id)
        .filter(
            Article.pub_date >= cutoff,
            ArticleEmbedding.model_name == EMBED_MODEL_NAME,
            Event.keywords.isnot(None),
        )
        .order_by(desc(Article.pub_date))
        .limit(3000)  # 硬上限，防止历史堆积时 OOM
        .all()
    )
    if not cand_rows:
        return [], meta
    meta["candidates"] = len(cand_rows)

    # 排除已经看过的文章（避免推断 tag 全是用户已读）
    seen_ids = set(article_weights.keys())

    cand_ids: List[int] = []
    cand_kws: List[List[str]] = []
    cand_vecs: List[np.ndarray] = []
    for aid, vec_bytes, kws_json in cand_rows:
        if aid in seen_ids:
            continue
        try:
            v = np.frombuffer(vec_bytes, dtype=np.float32)
            kws = json.loads(kws_json) if kws_json else []
            if not isinstance(kws, list) or not kws:
                continue
        except Exception:
            continue
        cand_ids.append(aid)
        cand_kws.append([str(k) for k in kws if k])
        cand_vecs.append(v)

    if not cand_vecs:
        return [], meta

    cand_mat = np.stack(cand_vecs).astype(np.float32)  # (M, dim)
    sims = cand_mat @ centroid                          # (M,)
    # TopK + 阈值过滤
    if sims.shape[0] > NEIGHBOR_TOPK:
        top_idx = np.argpartition(-sims, NEIGHBOR_TOPK)[:NEIGHBOR_TOPK]
    else:
        top_idx = np.arange(sims.shape[0])
    top_idx = top_idx[sims[top_idx] >= NEIGHBOR_MIN_COS]
    meta["neighbors_kept"] = int(len(top_idx))
    if top_idx.size == 0:
        return [], meta

    # 聚合 keyword 权重：sum(cos × 1.0)；同 keyword 多次出现累加
    tag_score: Dict[str, float] = {}
    for i in top_idx:
        cos = float(sims[i])
        for kw in cand_kws[i]:
            tag_score[kw] = tag_score.get(kw, 0.0) + cos

    # 排序 + 截断
    ranked = sorted(tag_score.items(), key=lambda x: -x[1])[:INFERRED_TAG_TOPN]
    return ranked, meta


def get_or_refresh_inferred_tags(
    db: Session, profile_data: dict, force: bool = False
) -> List[Tuple[str, float]]:
    """带 TTL 的缓存读取/重算：

    - 若 inferred_at 距今 < TTL 且非 force：直接返回缓存
    - 否则重算并写回 profile_data（调用方负责 _save_profile_data）
    返回 [(tag, score), ...]
    """
    cached = profile_data.get("inferred_tags") or []
    inferred_at = profile_data.get("inferred_at")
    now = utcnow()
    if not force and cached and inferred_at:
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(inferred_at)
            if (now - ts).total_seconds() < TTL_SECONDS:
                return [(t, float(s)) for t, s in cached]
        except Exception:
            pass

    history = profile_data.get("view_history") or []
    ranked, meta = infer_tags_from_history(db, history)
    profile_data["inferred_tags"] = [[t, round(s, 4)] for t, s in ranked]
    profile_data["inferred_at"] = now.isoformat()
    profile_data["inferred_meta"] = meta
    logger.info(
        "[profile_inference] 重算推断 tag：history=%d candidates=%d kept=%d → tags=%d",
        meta.get("history_used", 0),
        meta.get("candidates", 0),
        meta.get("neighbors_kept", 0),
        len(ranked),
    )
    return ranked

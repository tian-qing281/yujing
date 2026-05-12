"""
增量事件聚类（P1 · v1.5）

设计要点：
- 走与全量 FAISS 链路完全一致的向量化（bge-small-zh-v1.5 + L2 归一），
  阈值默认沿用全量路径的 L2 ≈ 0.69（可由 INCR_CLUSTER_THRESHOLD 覆盖）。
- 仅处理 `clustered_at IS NULL` 且最近 lookback_hours 的 Article，避免重新扫全库。
- 对每条新文章：
    * 若与某个已存在事件的 centroid cosine ≥ 阈值，挂到该事件，并用
      在线均值更新 centroid（c' = L2((c*n + v)/(n+1))）；
    * 否则进入 buffer，最后在 buffer 内做小规模 Union-Find 形成新事件。
- 不动现有 rebuild_events 全量路径，scheduler 仍可继续走全量；本服务仅新增一条
  `/admin/events/incremental` 入口供小步增量。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.orm import Session

from app.database import Article, Event, EventArticle, utcnow
from app.services.events import _build_cluster_payload, _score_article
from app.services.semantic_cluster import ensure_embeddings

logger = logging.getLogger(__name__)


# === 超参（可通过 .env 覆盖）===
INCR_CLUSTER_THRESHOLD = float(os.getenv("INCR_CLUSTER_THRESHOLD", "0.69"))
INCR_CLUSTER_LOOKBACK_HOURS = int(os.getenv("INCR_CLUSTER_LOOKBACK_HOURS", "168"))  # 7 天
INCR_CLUSTER_MAX_PENDING = int(os.getenv("INCR_CLUSTER_MAX_PENDING", "500"))


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        return v.astype(np.float32, copy=False)
    return (v / n).astype(np.float32)


def _load_event_centroids(db: Session) -> Tuple[List[Event], Optional[np.ndarray]]:
    """读出所有具备 centroid 的事件 + 拼成 (M, dim) 矩阵。"""
    events = (
        db.query(Event)
        .filter(Event.centroid.isnot(None))
        .filter(Event.centroid_count > 0)
        .all()
    )
    if not events:
        return [], None
    mat = np.stack(
        [np.frombuffer(e.centroid, dtype=np.float32) for e in events]
    ).astype(np.float32)
    return events, mat


def _refresh_event_platforms(db: Session, event: Event) -> None:
    """根据 EventArticle 反查 source_id 去重数，作为 platform_count。"""
    rows = (
        db.query(Article.source_id)
        .join(EventArticle, EventArticle.article_id == Article.id)
        .filter(EventArticle.event_id == event.id)
        .distinct()
        .all()
    )
    event.platform_count = len({sid for (sid,) in rows if sid})


def _attach_to_event(
    db: Session,
    event: Event,
    article: Article,
    vec: np.ndarray,
    sim: float,
    max_hot: float,
) -> None:
    """把 article 挂到 event：写 EventArticle、在线均值更新 centroid、刷新汇总字段。"""
    importance = round(0.6 * float(sim) + 0.4 * (_score_article(article) / max_hot), 4)
    db.add(
        EventArticle(
            event_id=event.id,
            article_id=article.id,
            relation_score=round(float(sim), 4),
            importance_score=importance,
            is_primary=False,
        )
    )
    # 在线均值更新 centroid
    if event.centroid is not None and (event.centroid_count or 0) > 0:
        old = np.frombuffer(event.centroid, dtype=np.float32)
        merged = (old * event.centroid_count + vec) / (event.centroid_count + 1)
    else:
        merged = vec
    new_c = _l2_normalize(merged)
    event.centroid = new_c.tobytes()
    event.centroid_count = (event.centroid_count or 0) + 1
    event.article_count = (event.article_count or 0) + 1
    _refresh_event_platforms(db, event)
    # 简化版热度增量：每挂一篇 +5；与全量 rebuild 的精确公式存在偏差，定期 rebuild 校准
    event.heat_score = round((event.heat_score or 0.0) + 5.0, 2)
    a_time = article.pub_date or article.fetch_time or utcnow()
    if event.latest_article_time is None or a_time > event.latest_article_time:
        event.latest_article_time = a_time
    event.updated_at = utcnow()


def _create_event_from_cluster(
    db: Session,
    articles_with_vec: List[Tuple[Article, np.ndarray]],
    max_hot: float,
) -> Event:
    """根据一组（文章, 向量）新建事件，centroid 取 L2(均值)。"""
    arts = [a for a, _ in articles_with_vec]
    payload = _build_cluster_payload(arts)
    centroid = _l2_normalize(
        np.mean(np.stack([v for _, v in articles_with_vec]), axis=0)
    )
    event = Event(
        title=payload["title"],
        summary=payload["summary"],
        keywords=json.dumps(payload["keywords"], ensure_ascii=False),
        sentiment=payload["sentiment"],
        article_count=payload["article_count"],
        platform_count=payload["platform_count"],
        heat_score=payload.get("heat_score", 0.0),
        latest_article_time=payload["latest_article_time"],
        representative_article_id=payload["representative_article_id"],
        primary_source_id=payload["primary_source_id"],
        centroid=centroid.tobytes(),
        centroid_count=len(arts),
    )
    db.add(event)
    db.flush()  # 拿到 event.id
    for art, vec in articles_with_vec:
        sim = float(np.dot(centroid, vec))
        importance = round(0.6 * sim + 0.4 * (_score_article(art) / max_hot), 4)
        db.add(
            EventArticle(
                event_id=event.id,
                article_id=art.id,
                relation_score=round(sim, 4),
                importance_score=importance,
                is_primary=(art.id == payload["representative_article_id"]),
            )
        )
    return event


def _mini_union_find(
    buf: List[Tuple[Article, np.ndarray]], threshold: float
) -> List[List[int]]:
    """buffer 内 cosine ≥ threshold 即合并；规模 ≤ INCR_CLUSTER_MAX_PENDING，O(n²) 可接受。"""
    n = len(buf)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    if n <= 1:
        return [[i] for i in range(n)]

    mat = np.stack([v for _, v in buf]).astype(np.float32)
    sim = mat @ mat.T
    for i in range(n):
        for j in range(i + 1, n):
            if sim[i, j] >= threshold:
                union(i, j)
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def incremental_cluster(
    db: Session,
    lookback_hours: int = INCR_CLUSTER_LOOKBACK_HOURS,
    threshold: float = INCR_CLUSTER_THRESHOLD,
    max_pending: int = INCR_CLUSTER_MAX_PENDING,
) -> Dict[str, object]:
    """对未聚类的最近文章做增量聚合，返回统计结果。"""
    cutoff = utcnow() - timedelta(hours=lookback_hours)
    pending: List[Article] = (
        db.query(Article)
        .filter(Article.clustered_at.is_(None))
        .filter((Article.pub_date >= cutoff) | (Article.fetch_time >= cutoff))
        .order_by(Article.fetch_time.desc())
        .limit(max_pending)
        .all()
    )
    if not pending:
        return {
            "pending": 0,
            "attached": 0,
            "new_events": 0,
            "threshold": threshold,
            "lookback_hours": lookback_hours,
        }

    emb_map = ensure_embeddings(db, pending)
    pending = [a for a in pending if a.id in emb_map]

    events, centroid_mat = _load_event_centroids(db)

    all_hot = [_score_article(a) for a in db.query(Article).all()]
    max_hot = max(all_hot) if all_hot else 1.0
    if max_hot <= 0:
        max_hot = 1.0

    attached = 0
    buffer: List[Tuple[Article, np.ndarray]] = []

    for art in pending:
        v = _l2_normalize(emb_map[art.id].astype(np.float32))
        if centroid_mat is not None and len(events) > 0:
            sims = centroid_mat @ v
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            if best_sim >= threshold:
                target = events[best_idx]
                _attach_to_event(db, target, art, v, best_sim, max_hot)
                centroid_mat[best_idx] = np.frombuffer(
                    target.centroid, dtype=np.float32
                )
                art.clustered_at = utcnow()
                attached += 1
                continue
        buffer.append((art, v))

    new_event_count = 0
    if buffer:
        groups = _mini_union_find(buffer, threshold)
        for grp in groups:
            cluster = [buffer[i] for i in grp]
            _create_event_from_cluster(db, cluster, max_hot)
            new_event_count += 1
            for art, _ in cluster:
                art.clustered_at = utcnow()

    db.commit()
    result = {
        "pending": len(pending),
        "attached": attached,
        "new_events": new_event_count,
        "threshold": threshold,
        "lookback_hours": lookback_hours,
    }
    logger.info(f"[incremental_cluster] {result}")
    return result


def calibrate_event_centroids(db: Session, only_missing: bool = False) -> Dict[str, int]:
    """全量校准 events.centroid：直接读 article_embeddings 取均值 + L2 归一。

    与 P1 的在线均值不同，本函数从原始向量重算，作为定时校准修正在线均值漂移。

    only_missing=True 时仅处理 centroid 为空的 event（等价 backfill 脚本）。
    """
    from app.database import ArticleEmbedding

    q = db.query(Event)
    if only_missing:
        q = q.filter(Event.centroid.is_(None))
    events = q.all()
    if not events:
        return {"checked": 0, "updated": 0, "skipped_no_vec": 0}

    updated = 0
    skipped_no_vec = 0
    for ev in events:
        rows = (
            db.query(ArticleEmbedding.vector)
            .join(EventArticle, EventArticle.article_id == ArticleEmbedding.article_id)
            .filter(EventArticle.event_id == ev.id)
            .all()
        )
        if not rows:
            skipped_no_vec += 1
            continue
        vecs = np.stack(
            [np.frombuffer(r[0], dtype=np.float32) for r in rows]
        )
        new_c = _l2_normalize(vecs.mean(axis=0))
        new_bytes = new_c.tobytes()
        new_count = int(vecs.shape[0])
        # 仅在变化时写库，减少 WAL
        if ev.centroid != new_bytes or ev.centroid_count != new_count:
            ev.centroid = new_bytes
            ev.centroid_count = new_count
            updated += 1
    db.commit()
    result = {
        "checked": len(events),
        "updated": updated,
        "skipped_no_vec": skipped_no_vec,
    }
    logger.info(f"[calibrate_event_centroids] {result}")
    return result

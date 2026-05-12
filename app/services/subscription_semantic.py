"""
订阅语义召回（S1 · v1.5）

设计要点：
- 复用 P1 增量聚类写入的 `Event.centroid`（L2 归一的 BGE 向量）做事件级表示；
  无需新增向量表，对现网零侵入。
- 订阅词向量进程内字典缓存（key 含模型名，避免换模型时命中错向量）。
- 提供 `score_events_for_subscriptions(events, subs)`：返回
  `{event_id: (max_cosine, hit_subscription_value)}`，便于推荐路由复用。
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np

from app.database import Event, Subscription
from app.services.embedding import EMBED_MODEL_NAME, embed_texts


# 哪些 kind 需要语义化（source 是站点 ID，没必要 embed）
SEMANTIC_KINDS = {"keyword", "event"}

logger = logging.getLogger(__name__)


# 进程内向量缓存：(text, model_name) -> np.ndarray (L2 归一 float32)
_sub_vec_cache: Dict[Tuple[str, str], np.ndarray] = {}


def _get_sub_vector(text: str) -> Optional[np.ndarray]:
    """获取订阅词向量，带进程内缓存。空文本返回 None。"""
    text = (text or "").strip()
    if not text:
        return None
    key = (text, EMBED_MODEL_NAME)
    cached = _sub_vec_cache.get(key)
    if cached is not None:
        return cached
    try:
        vec = embed_texts([text])[0].astype(np.float32)
    except Exception:
        logger.exception("[subscription_semantic] embed_texts 失败：%s", text)
        return None
    # embedding.py 已经 L2 归一，这里不重复归一
    _sub_vec_cache[key] = vec
    return vec


def get_subscription_vectors(values: Iterable[str]) -> Dict[str, np.ndarray]:
    """批量取订阅词向量；空文本与失败的会被丢弃。"""
    out: Dict[str, np.ndarray] = {}
    pending: List[str] = []
    for v in values:
        v = (v or "").strip()
        if not v:
            continue
        key = (v, EMBED_MODEL_NAME)
        if key in _sub_vec_cache:
            out[v] = _sub_vec_cache[key]
        elif v not in pending:
            pending.append(v)
    if pending:
        try:
            vecs = embed_texts(pending)
            for v, vec in zip(pending, vecs):
                arr = vec.astype(np.float32)
                _sub_vec_cache[(v, EMBED_MODEL_NAME)] = arr
                out[v] = arr
        except Exception:
            logger.exception("[subscription_semantic] 批量 embed 失败")
    return out


def encode_and_persist_subscription(db, sub: Subscription) -> bool:
    """S1.2：为新创建的订阅条目计算 BGE 向量并落库。

    - 仅对 SEMANTIC_KINDS 生效；source 类订阅不需要语义。
    - 同步写入 sub.embedding / sub.embedding_model；同时回填进程内缓存。
    - 返回是否成功落库（embed 失败/非语义类返回 False）。
    """
    if sub is None or sub.kind not in SEMANTIC_KINDS:
        return False
    val = (sub.value or "").strip()
    if not val:
        return False
    vec = _get_sub_vector(val)
    if vec is None:
        return False
    try:
        sub.embedding = vec.tobytes()
        sub.embedding_model = EMBED_MODEL_NAME
        db.commit()
        return True
    except Exception:
        logger.exception("[subscription_semantic] 持久化订阅向量失败 id=%s", sub.id)
        db.rollback()
        return False


def prime_cache_from_db(db, subs: Iterable[Subscription]) -> int:
    """S1.2：把 DB 中已持久化的订阅向量灌进进程内缓存，省去重复 embed。

    - 模型不匹配的旧向量直接跳过（等下次 create 时按当前模型重算）。
    - 返回命中条数。
    """
    hit = 0
    for sub in subs:
        if sub.kind not in SEMANTIC_KINDS:
            continue
        if not sub.embedding or not sub.embedding_model:
            continue
        if sub.embedding_model != EMBED_MODEL_NAME:
            continue
        val = (sub.value or "").strip()
        if not val:
            continue
        key = (val, EMBED_MODEL_NAME)
        if key in _sub_vec_cache:
            continue
        try:
            arr = np.frombuffer(sub.embedding, dtype=np.float32)
            _sub_vec_cache[key] = arr
            hit += 1
        except Exception:
            continue
    return hit


def _get_sub_vectors_legacy(values: Iterable[str]) -> Dict[str, np.ndarray]:
    """已废弃：保留空壳避免外部 import 报错；请使用 get_subscription_vectors。"""
    return get_subscription_vectors(values)



def score_events_for_subscriptions(
    events: List[Event],
    subscription_values: List[str],
    threshold: float = 0.45,
) -> Dict[int, Tuple[float, str]]:
    """
    对每个 event（要求 centroid 非空），算其与所有订阅词向量的最大 cosine；
    cosine ≥ threshold 才记录。
    返回：event_id -> (max_cos, 命中订阅值)
    """
    if not events or not subscription_values:
        return {}
    sub_vecs = get_subscription_vectors(subscription_values)
    if not sub_vecs:
        return {}
    sub_keys = list(sub_vecs.keys())
    sub_mat = np.stack([sub_vecs[k] for k in sub_keys]).astype(np.float32)  # (S, dim)

    out: Dict[int, Tuple[float, str]] = {}
    for ev in events:
        if not ev.centroid:
            continue
        try:
            c = np.frombuffer(ev.centroid, dtype=np.float32)
            if c.shape[0] != sub_mat.shape[1]:
                continue
        except Exception:
            continue
        sims = sub_mat @ c  # (S,)
        idx = int(np.argmax(sims))
        cos = float(sims[idx])
        if cos >= threshold:
            out[ev.id] = (cos, sub_keys[idx])
    return out

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

from app.database import Event
from app.services.embedding import EMBED_MODEL_NAME, embed_texts

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

from __future__ import annotations

import math
import warnings
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Sequence, Tuple

from app.runtime_warnings import suppress_known_dependency_warnings

with warnings.catch_warnings():
    suppress_known_dependency_warnings()
    import jieba
    import jieba.posseg as pseg


_STOP_WORDS = {
    "the", "of", "is", "and", "to", "in", "that", "we", "for", "an", "are",
    "by", "be", "as", "on", "with", "can", "if", "from", "which", "you", "it",
    "this", "then", "at", "have", "all", "not", "one", "has", "or",
}


@lru_cache(maxsize=1)
def _load_idf() -> Tuple[Dict[str, float], float]:
    idf_path = Path(jieba.__file__).resolve().parent / "analyse" / "idf.txt"
    idf_freq: Dict[str, float] = {}
    with idf_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            token, _, value = line.strip().partition(" ")
            if token and value:
                idf_freq[token] = float(value)

    if not idf_freq:
        return {}, 1.0

    median_idf = sorted(idf_freq.values())[len(idf_freq) // 2]
    return idf_freq, median_idf


def _iter_terms(text: str, allow_pos: Sequence[str]) -> Iterable[Tuple[str, str]]:
    if allow_pos:
        allowed_pos = frozenset(allow_pos)
        for token in pseg.cut(text):
            if token.flag in allowed_pos:
                yield token.word, token.flag
        return

    for token in jieba.cut(text):
        yield token, ""


def extract_tags(
    text: str,
    topK: int = 20,
    withWeight: bool = False,
    allowPOS: Sequence[str] = (),
    withFlag: bool = False,
):
    idf_freq, median_idf = _load_idf()
    frequencies: Dict[Tuple[str, str], float] = {}

    for word, flag in _iter_terms(text, allowPOS):
        normalized = word.strip()
        if len(normalized) < 2 or normalized.lower() in _STOP_WORDS:
            continue
        frequencies[(normalized, flag)] = frequencies.get((normalized, flag), 0.0) + 1.0

    total = sum(frequencies.values()) or 1.0
    ranked = []
    for (word, flag), count in frequencies.items():
        weight = count * idf_freq.get(word, median_idf) / total
        token = (word, flag) if withFlag and allowPOS else word
        ranked.append((token, weight))

    ranked.sort(key=lambda item: item[1], reverse=True)
    if topK:
        ranked = ranked[:topK]

    if withWeight:
        return ranked
    return [token for token, _ in ranked]


def textrank(
    text: str,
    topK: int = 20,
    withWeight: bool = False,
    allowPOS: Sequence[str] = ("ns", "n", "vn", "v"),
    withFlag: bool = False,
):
    candidate_terms = []
    for word, flag in _iter_terms(text, allowPOS):
        normalized = word.strip()
        if len(normalized) < 2 or normalized.lower() in _STOP_WORDS:
            continue
        candidate_terms.append((normalized, flag))

    graph = defaultdict(dict)
    window_size = 5
    for index, left in enumerate(candidate_terms):
        left_token = left if withFlag else left[0]
        for right in candidate_terms[index + 1:index + window_size]:
            right_token = right if withFlag else right[0]
            if left_token == right_token:
                continue
            graph[left_token][right_token] = graph[left_token].get(right_token, 0.0) + 1.0
            graph[right_token][left_token] = graph[right_token].get(left_token, 0.0) + 1.0

    if not graph:
        return [] if withWeight else []

    base_rank = 1.0 / len(graph)
    ranks = {token: base_rank for token in graph}

    for _ in range(10):
        updated = {}
        for token, neighbors in graph.items():
            score = 1.0 - 0.85
            for neighbor, weight in neighbors.items():
                neighbor_sum = sum(graph[neighbor].values()) or 1.0
                score += 0.85 * weight / neighbor_sum * ranks[neighbor]
            updated[token] = score
        ranks = updated

    min_rank = min(ranks.values())
    max_rank = max(ranks.values())
    if math.isclose(max_rank, min_rank):
        normalized_ranks = {token: 1.0 for token in ranks}
    else:
        baseline = min_rank / 10.0
        normalized_ranks = {
            token: (score - baseline) / (max_rank - baseline)
            for token, score in ranks.items()
        }

    ranked = sorted(normalized_ranks.items(), key=lambda item: item[1], reverse=True)
    if topK:
        ranked = ranked[:topK]

    if withWeight:
        return ranked
    return [token for token, _ in ranked]


__all__ = ["extract_tags", "textrank", "jieba", "pseg"]
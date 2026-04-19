from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.database import Article, EventArticle, SessionLocal, utcnow
from app.services.events import _extract_tokens


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT / "runtime" / "eval"


@dataclass
class ArticleRow:
    article_id: int
    event_id: int
    title: str
    source_id: str
    rank: int
    pub_date: Optional[datetime]
    fetch_time: Optional[datetime]
    importance_score: float
    is_primary: bool
    tokens: Tuple[str, ...]

    @property
    def timestamp(self) -> Optional[datetime]:
        return self.pub_date or self.fetch_time


def _iso(dt: Optional[datetime]) -> str:
    return dt.isoformat() if dt else ""


def _pair_key(left_id: int, right_id: int) -> Tuple[int, int]:
    return (left_id, right_id) if left_id < right_id else (right_id, left_id)


def _article_to_row(article: Article, event_article: EventArticle) -> ArticleRow:
    tokens = tuple(_extract_tokens(article))
    return ArticleRow(
        article_id=article.id,
        event_id=event_article.event_id,
        title=article.title or "",
        source_id=article.source_id or "",
        rank=article.rank or 99,
        pub_date=article.pub_date,
        fetch_time=article.fetch_time,
        importance_score=float(event_article.importance_score or 0.0),
        is_primary=bool(event_article.is_primary),
        tokens=tokens,
    )


def _load_rows(lookback_hours: int) -> List[ArticleRow]:
    db = SessionLocal()
    try:
        cutoff = utcnow() - timedelta(hours=lookback_hours)
        joined = (
            db.query(Article, EventArticle)
            .join(EventArticle, EventArticle.article_id == Article.id)
            .filter(Article.fetch_time >= cutoff)
            .order_by(Article.fetch_time.desc(), Article.id.desc())
            .all()
        )
        return [_article_to_row(article, event_article) for article, event_article in joined]
    finally:
        db.close()


def _group_by_event(rows: Sequence[ArticleRow]) -> Dict[int, List[ArticleRow]]:
    grouped: Dict[int, List[ArticleRow]] = defaultdict(list)
    for row in rows:
        grouped[row.event_id].append(row)
    for event_id in grouped:
        grouped[event_id].sort(
            key=lambda item: (
                not item.is_primary,
                -item.importance_score,
                item.rank,
                -(item.timestamp.timestamp() if item.timestamp else 0),
            )
        )
    return grouped


def _pick_positive_pairs(
    groups: Dict[int, List[ArticleRow]],
    target: int,
) -> List[Tuple[ArticleRow, ArticleRow]]:
    selected: List[Tuple[ArticleRow, ArticleRow]] = []
    seen = set()
    ordered = sorted(groups.values(), key=len, reverse=True)

    def add_pair(left: ArticleRow, right: ArticleRow) -> None:
        key = _pair_key(left.article_id, right.article_id)
        if left.article_id == right.article_id or key in seen:
            return
        seen.add(key)
        selected.append((left, right))

    for rows in ordered:
        if len(rows) >= 2:
            add_pair(rows[0], rows[1])
        if len(selected) >= target:
            return selected[:target]

    for rows in ordered:
        if len(rows) >= 3:
            add_pair(rows[0], rows[2])
        if len(selected) >= target:
            return selected[:target]

    for rows in ordered:
        if len(rows) >= 4:
            add_pair(rows[1], rows[2])
        if len(rows) >= target:
            return selected[:target]

    for rows in ordered:
        if len(rows) >= 4:
            add_pair(rows[0], rows[3])
        if len(selected) >= target:
            return selected[:target]

    return selected[:target]


def _token_overlap(left: ArticleRow, right: ArticleRow) -> float:
    left_tokens = set(left.tokens)
    right_tokens = set(right.tokens)
    if not left_tokens or not right_tokens:
        return 0.0
    inter = left_tokens & right_tokens
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(inter) / len(union)


def _time_proximity(left: ArticleRow, right: ArticleRow) -> float:
    if not left.timestamp or not right.timestamp:
        return 0.0
    delta_hours = abs((left.timestamp - right.timestamp).total_seconds()) / 3600.0
    if delta_hours <= 6:
        return 1.0
    if delta_hours <= 24:
        return 0.6
    if delta_hours <= 72:
        return 0.3
    return 0.0


def _pick_hard_negative_pairs(
    rows: Sequence[ArticleRow],
    target: int,
    pool_size: int = 400,
) -> List[Tuple[ArticleRow, ArticleRow]]:
    candidates: List[Tuple[float, Tuple[ArticleRow, ArticleRow]]] = []
    seen = set()
    pool = sorted(
        rows,
        key=lambda item: (
            -item.importance_score,
            item.rank,
            -(item.timestamp.timestamp() if item.timestamp else 0),
        ),
    )[:pool_size]

    for idx, left in enumerate(pool):
        for right in pool[idx + 1 :]:
            if left.event_id == right.event_id:
                continue
            key = _pair_key(left.article_id, right.article_id)
            if key in seen:
                continue
            overlap = _token_overlap(left, right)
            if overlap <= 0:
                continue
            score = 0.7 * overlap + 0.3 * _time_proximity(left, right)
            candidates.append((score, (left, right)))
            seen.add(key)

    candidates.sort(key=lambda item: item[0], reverse=True)
    return [pair for _, pair in candidates[:target]]


def _pick_random_negative_pairs(
    rows: Sequence[ArticleRow],
    target: int,
    rng: random.Random,
    occupied: Iterable[Tuple[int, int]],
) -> List[Tuple[ArticleRow, ArticleRow]]:
    selected: List[Tuple[ArticleRow, ArticleRow]] = []
    seen = set(occupied)
    if len(rows) < 2:
        return selected

    attempts = 0
    max_attempts = max(target * 40, 1000)
    while len(selected) < target and attempts < max_attempts:
        attempts += 1
        left, right = rng.sample(list(rows), 2)
        if left.event_id == right.event_id:
            continue
        key = _pair_key(left.article_id, right.article_id)
        if key in seen:
            continue
        seen.add(key)
        selected.append((left, right))
    return selected


def _serialize_pair(pair_id: str, left: ArticleRow, right: ArticleRow) -> Dict[str, object]:
    return {
        "pair_id": pair_id,
        "article_a": left.article_id,
        "source_a": left.source_id,
        "pub_date_a": _iso(left.pub_date),
        "fetch_time_a": _iso(left.fetch_time),
        "title_a": left.title,
        "article_b": right.article_id,
        "source_b": right.source_id,
        "pub_date_b": _iso(right.pub_date),
        "fetch_time_b": _iso(right.fetch_time),
        "title_b": right.title,
        "label": "",
        "note": "",
    }


def _write_jsonl(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    fieldnames = [
        "pair_id",
        "article_a",
        "source_a",
        "pub_date_a",
        "fetch_time_a",
        "title_a",
        "article_b",
        "source_b",
        "pub_date_b",
        "fetch_time_b",
        "title_b",
        "label",
        "note",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_pairs(limit: int, lookback_hours: int, seed: int) -> Tuple[Path, Path, Dict[str, int]]:
    rows = _load_rows(lookback_hours=lookback_hours)
    if len(rows) < 2:
        raise RuntimeError("可用于抽样的文章不足")

    groups = _group_by_event(rows)
    eligible_events = {event_id: items for event_id, items in groups.items() if len(items) >= 2}
    if not eligible_events:
        raise RuntimeError("没有至少包含 2 篇文章的事件，无法生成正样本候选")

    rng = random.Random(seed)
    positive_target = max(1, limit // 2)
    hard_negative_target = max(1, int(limit * 0.3))
    random_negative_target = max(0, limit - positive_target - hard_negative_target)

    positives = _pick_positive_pairs(eligible_events, positive_target)
    hard_negatives = _pick_hard_negative_pairs(rows, hard_negative_target)
    occupied = {_pair_key(left.article_id, right.article_id) for left, right in positives + hard_negatives}
    random_negatives = _pick_random_negative_pairs(rows, random_negative_target, rng, occupied)

    pairs = positives + hard_negatives + random_negatives
    rng.shuffle(pairs)
    pairs = pairs[:limit]

    serialized = [
        _serialize_pair(f"P{index:04d}", left, right)
        for index, (left, right) in enumerate(pairs, start=1)
    ]

    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = DEFAULT_OUTPUT_DIR / f"pairs_seed_{limit}.jsonl"
    csv_path = DEFAULT_OUTPUT_DIR / f"pairs_seed_{limit}.csv"
    _write_jsonl(jsonl_path, serialized)
    _write_csv(csv_path, serialized)

    summary = {
        "total_pairs": len(serialized),
        "candidate_positive": len(positives),
        "candidate_hard_negative": len(hard_negatives),
        "candidate_random_negative": len(random_negatives),
        "recent_articles": len(rows),
        "eligible_events": len(eligible_events),
    }
    return jsonl_path, csv_path, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="基于真实数据库文章生成聚类评测待标注样本")
    parser.add_argument("--limit", type=int, default=100, help="输出 pair 数量")
    parser.add_argument("--lookback", type=int, default=720, dest="lookback_hours", help="抽样时间窗口（小时）")
    parser.add_argument("--seed", type=int, default=20260419, help="随机种子")
    args = parser.parse_args()

    jsonl_path, csv_path, summary = generate_pairs(
        limit=max(10, args.limit),
        lookback_hours=max(24, args.lookback_hours),
        seed=args.seed,
    )
    print(json.dumps({
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
        **summary,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
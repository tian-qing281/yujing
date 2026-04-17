"""
聚类评测脚本（W3 会完善；W1 只先留接口和 CLI 骨架）

设计目标：
    跑同一批 Article 分别走 Jaccard 与 Sentence-BERT 两条路径，
    以人工标注的 article-pair 为 ground truth，输出：
        ARI / NMI / V-measure / Pair-F1 / Recall@K / 簇数分布
    供论文"实验"章节引用。

使用示例（W3 之后）：
    # 1) 先在当前库里标注若干 pair，存到 runtime/eval/pairs.jsonl
    #    {"article_a": 123, "article_b": 456, "label": 1}
    # 2) 运行
    python -m scripts.evaluate_clustering --pairs runtime/eval/pairs.jsonl

W1 先跑一个最小烟雾测试：
    python -m scripts.evaluate_clustering --smoke
它只会：
    - 取最近 200 篇文章
    - 各自跑一轮 Jaccard / 语义路径
    - 打印簇数、规模分布、耗时
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import List

# 允许直接 `python scripts/evaluate_clustering.py ...` 执行
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _smoke(limit: int = 200, lookback_hours: int = 72):
    from app.database import Article, SessionLocal
    from app.services.events import (
        _cluster_articles,
        _merge_near_duplicate_clusters,
        _compute_idf_map,
        _extract_tokens,
    )
    from app.services import events as events_mod

    db = SessionLocal()
    try:
        from datetime import datetime, timedelta
        cutoff = datetime.utcnow() - timedelta(hours=lookback_hours)
        articles = (
            db.query(Article)
            .filter(Article.fetch_time >= cutoff)
            .order_by(Article.fetch_time.desc())
            .limit(limit)
            .all()
        )
        if not articles:
            print("没有可用文章")
            return

        print(f"=== Smoke on {len(articles)} articles, lookback={lookback_hours}h ===\n")

        # --- Jaccard 路径 ---
        events_mod._CURRENT_IDF_MAP = _compute_idf_map([_extract_tokens(a) for a in articles])
        t0 = time.perf_counter()
        jaccard_clusters = _merge_near_duplicate_clusters(_cluster_articles(articles))
        t1 = time.perf_counter()
        _print_cluster_stats("Jaccard (IDF-weighted)", jaccard_clusters, t1 - t0)
        events_mod._CURRENT_IDF_MAP = {}

        # --- Semantic 路径 ---
        try:
            from app.services.semantic_cluster import cluster_articles_semantic
            t0 = time.perf_counter()
            semantic_clusters = cluster_articles_semantic(db, articles)
            semantic_clusters = _merge_near_duplicate_clusters(semantic_clusters)
            t1 = time.perf_counter()
            _print_cluster_stats("Semantic (bge-small-zh)", semantic_clusters, t1 - t0)
        except Exception as exc:
            print(f"[!] 语义路径失败（可能是模型还未下载好）：{exc}")
    finally:
        db.close()


def _print_cluster_stats(name: str, clusters: List[dict], elapsed: float):
    n_articles = sum(len(c["articles"]) for c in clusters)
    sizes = [len(c["articles"]) for c in clusters]
    sizes.sort(reverse=True)
    top5 = sizes[:5]
    bucket = Counter()
    for s in sizes:
        if s == 1:
            bucket["1 (singleton)"] += 1
        elif s <= 3:
            bucket["2-3"] += 1
        elif s <= 10:
            bucket["4-10"] += 1
        else:
            bucket["11+"] += 1

    print(f"--- {name} ---")
    print(f"  耗时：{elapsed:.2f}s")
    print(f"  总簇数：{len(clusters)}   覆盖文章：{n_articles}")
    print(f"  top5 簇规模：{top5}")
    print(f"  分布：{dict(bucket)}")
    print()


def main():
    parser = argparse.ArgumentParser(description="聚类评测（W3 版）")
    parser.add_argument("--smoke", action="store_true", help="最小烟雾测试，不需要标注集")
    parser.add_argument("--pairs", type=str, default=None, help="article-pair 标注 jsonl 路径")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--lookback", type=int, default=72, dest="lookback_hours")
    args = parser.parse_args()

    if args.smoke or not args.pairs:
        _smoke(limit=args.limit, lookback_hours=args.lookback_hours)
        return

    print("[TODO] W3 完善：pairs 标注集 → ARI / NMI / V-measure / Pair-F1")
    print(f"     pairs = {args.pairs}")


if __name__ == "__main__":
    main()

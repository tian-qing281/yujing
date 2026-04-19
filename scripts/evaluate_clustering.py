"""
聚类评测脚本。

当前支持：
    1. 基于人工标注 article-pair 的 Pair Precision / Recall / Accuracy / F1；
    2. 对照三套结果：当前库内持久化事件、Jaccard 基线、当前语义聚类；
    3. 如果额外提供闭集 gold cluster 文件，再计算 ARI / NMI / V-measure。

注意：
    仅有 pair 标注时，无法严谨推出全局 gold partition，
    因此 ARI / NMI / V-measure 需要单独的闭集 cluster 标注文件。

W1 先跑一个最小烟雾测试：
    python -m scripts.evaluate_clustering --smoke
它只会：
    - 取最近 200 篇文章
    - 各自跑一轮 Jaccard / 语义路径
    - 打印簇数、规模分布、耗时
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score, v_measure_score

# 允许直接 `python scripts/evaluate_clustering.py ...` 执行
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _smoke(limit: int = 200, lookback_hours: int = 72):
    from app.database import Article, SessionLocal, utcnow
    from app.services.events import (
        _cluster_articles,
        _merge_near_duplicate_clusters,
        _compute_idf_map,
        _extract_tokens,
    )
    from app.services import events as events_mod

    db = SessionLocal()
    try:
        from datetime import timedelta
        cutoff = utcnow() - timedelta(hours=lookback_hours)
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


def _load_pairs(path: Path) -> Tuple[List[Tuple[int, int, int]], Dict[str, int]]:
    pairs: List[Tuple[int, int, int]] = []
    meta = {"positive": 0, "negative": 0, "skipped": 0}

    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.DictReader(handle)
            for row in rows:
                label = (row.get("label") or "").strip()
                if label not in {"0", "1"}:
                    meta["skipped"] += 1
                    continue
                left = int(row["article_a"])
                right = int(row["article_b"])
                truth = int(label)
                pairs.append((left, right, truth))
                if truth == 1:
                    meta["positive"] += 1
                else:
                    meta["negative"] += 1
    else:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                row = json.loads(raw)
                label = str(row.get("label", "")).strip()
                if label not in {"0", "1"}:
                    meta["skipped"] += 1
                    continue
                left = int(row["article_a"])
                right = int(row["article_b"])
                truth = int(label)
                pairs.append((left, right, truth))
                if truth == 1:
                    meta["positive"] += 1
                else:
                    meta["negative"] += 1

    meta["usable"] = len(pairs)
    return pairs, meta


def _load_gold_clusters(path: Optional[Path]) -> Dict[int, str]:
    if path is None:
        return {}

    # 字段兼容: 模板导出的文件用 gold_cluster_id (见 _export_gold_template),
    # 文档和早期示例用 cluster_id; 两者都认, gold_cluster_id 优先.
    def _pick(row) -> str:
        for key in ("gold_cluster_id", "cluster_id"):
            value = str(row.get(key, "") or "").strip()
            if value:
                return value
        return ""

    labels: Dict[int, str] = {}
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.DictReader(handle)
            for row in rows:
                cluster_id = _pick(row)
                if not cluster_id:
                    continue
                labels[int(row["article_id"])] = cluster_id
    else:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                row = json.loads(raw)
                cluster_id = _pick(row)
                if not cluster_id:
                    continue
                labels[int(row["article_id"])] = cluster_id
    return labels


def _collect_articles(db, lookback_hours: int, article_ids: Optional[set[int]] = None):
    from datetime import timedelta

    from app.database import Article, utcnow

    cutoff = utcnow() - timedelta(hours=lookback_hours)
    query = db.query(Article).filter(Article.fetch_time >= cutoff)
    if article_ids is not None:
        query = query.filter(Article.id.in_(sorted(article_ids)))
    return query.order_by(Article.fetch_time.desc(), Article.rank.asc()).all()


def _mapping_from_clusters(clusters: List[dict]) -> Dict[int, int]:
    mapping: Dict[int, int] = {}
    for cluster_id, cluster in enumerate(clusters):
        for article in cluster["articles"]:
            mapping[article.id] = cluster_id
    return mapping


def _mapping_from_db_events(db, lookback_hours: int, article_ids: Optional[set[int]] = None) -> Dict[int, int]:
    from datetime import timedelta

    from app.database import Article, EventArticle, utcnow

    cutoff = utcnow() - timedelta(hours=lookback_hours)
    query = (
        db.query(EventArticle.article_id, EventArticle.event_id)
        .join(Article, Article.id == EventArticle.article_id)
        .filter(Article.fetch_time >= cutoff)
    )
    if article_ids is not None:
        query = query.filter(EventArticle.article_id.in_(sorted(article_ids)))
    rows = query.all()
    return {int(article_id): int(event_id) for article_id, event_id in rows}


def _mapping_from_jaccard(db, lookback_hours: int, article_ids: Optional[set[int]] = None) -> Dict[int, int]:
    from app.services import events as events_mod
    from app.services.events import _cluster_articles, _compute_idf_map, _extract_tokens, _merge_near_duplicate_clusters

    articles = _collect_articles(db, lookback_hours, article_ids=article_ids)
    tokens_per_doc = [_extract_tokens(article) for article in articles]
    events_mod._CURRENT_IDF_MAP = _compute_idf_map(tokens_per_doc)
    try:
        clusters = _merge_near_duplicate_clusters(_cluster_articles(articles))
        return _mapping_from_clusters(clusters)
    finally:
        events_mod._CURRENT_IDF_MAP = {}


def _mapping_from_semantic(
    db,
    lookback_hours: int,
    existing_embeddings_only: bool = False,
    article_ids: Optional[set[int]] = None,
    *,
    fixed_threshold: Optional[float] = None,
    skip_verification: bool = False,
    disable_canonical_merge: bool = False,
) -> Dict[int, int]:
    from app.database import ArticleEmbedding
    from app.services.semantic_index import cluster_articles_semantic_faiss
    from app.services.embedding import EMBED_MODEL_NAME

    articles = _collect_articles(db, lookback_hours, article_ids=article_ids)
    if existing_embeddings_only:
        rows = (
            db.query(ArticleEmbedding.article_id)
            .filter(ArticleEmbedding.model_name == EMBED_MODEL_NAME)
            .all()
        )
        embedded_ids = {int(article_id) for (article_id,) in rows}
        articles = [article for article in articles if article.id in embedded_ids]
    clusters, _ = cluster_articles_semantic_faiss(
        db,
        articles,
        fixed_threshold=fixed_threshold,
        skip_verification=skip_verification,
        disable_canonical_merge=disable_canonical_merge,
    )
    return _mapping_from_clusters(clusters)


# 消融实验预设。每个预设对应 semantic 主路径的一个开关组合，
# 便于一次 --ablation all 跑完全部四组并与 baseline 对齐比较。
_ABLATION_CONFIGS = {
    "baseline":            {"fixed_threshold": None, "skip_verification": False, "disable_canonical_merge": False},
    "fixed_0.62":          {"fixed_threshold": 0.62, "skip_verification": False, "disable_canonical_merge": False},
    "no_verification":     {"fixed_threshold": None, "skip_verification": True,  "disable_canonical_merge": False},
    "no_canonical_merge":  {"fixed_threshold": None, "skip_verification": False, "disable_canonical_merge": True},
}


def _evaluate_pairs(pairs: List[Tuple[int, int, int]], mapping: Dict[int, int]) -> Dict[str, float]:
    tp = fp = tn = fn = 0
    covered = 0
    for left, right, truth in pairs:
        pred_same = left in mapping and right in mapping and mapping[left] == mapping[right]
        if left in mapping and right in mapping:
            covered += 1
        if truth == 1 and pred_same:
            tp += 1
        elif truth == 1:
            fn += 1
        elif truth == 0 and pred_same:
            fp += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "covered": covered,
        "precision": precision,
        "recall": recall,
        "accuracy": accuracy,
        "f1": f1,
    }


def _evaluate_cluster_metrics(mapping: Dict[int, int], gold_clusters: Dict[int, str]) -> Optional[Dict[str, float]]:
    if not gold_clusters:
        return None

    article_ids = [article_id for article_id in gold_clusters if article_id in mapping]
    if len(article_ids) < 2:
        return None

    y_true = [gold_clusters[article_id] for article_id in article_ids]
    y_pred = [str(mapping[article_id]) for article_id in article_ids]
    return {
        "articles": len(article_ids),
        "ari": adjusted_rand_score(y_true, y_pred),
        "nmi": normalized_mutual_info_score(y_true, y_pred),
        "v_measure": v_measure_score(y_true, y_pred),
    }


def _safe_lookup(mapping: Dict[int, int], article_id: int) -> str:
    value = mapping.get(article_id)
    return "" if value is None else str(value)


def _export_gold_template(
    pairs_path: Path,
    lookback_hours: int,
    output_path: Path,
    semantic_existing_embeddings_only: bool,
) -> None:
    from app.database import SessionLocal

    pairs, meta = _load_pairs(pairs_path)
    if not pairs:
        print("没有可用的 0/1 pair 标注，无法导出 gold template")
        return

    article_ids = sorted({article_id for left, right, _ in pairs for article_id in (left, right)})
    db = SessionLocal()
    try:
        articles = _collect_articles(db, lookback_hours, article_ids=set(article_ids))
        articles_by_id = {article.id: article for article in articles}

        persisted_map = _mapping_from_db_events(db, lookback_hours, article_ids=set(article_ids))
        jaccard_map = _mapping_from_jaccard(db, lookback_hours, article_ids=set(article_ids))
        semantic_map = _mapping_from_semantic(
            db,
            lookback_hours,
            existing_embeddings_only=semantic_existing_embeddings_only,
            article_ids=set(article_ids),
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "article_id",
            "title",
            "source_id",
            "pub_date",
            "fetch_time",
            "gold_cluster_id",
            "gold_cluster_title",
            "note",
            "suggested_persisted_cluster",
            "suggested_jaccard_cluster",
            "suggested_semantic_cluster",
        ]
        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            rows = []
            for article_id in article_ids:
                article = articles_by_id.get(article_id)
                if article is None:
                    continue
                rows.append(
                    {
                        "article_id": article.id,
                        "title": article.title or "",
                        "source_id": article.source_id or "",
                        "pub_date": article.pub_date.isoformat() if article.pub_date else "",
                        "fetch_time": article.fetch_time.isoformat() if article.fetch_time else "",
                        "gold_cluster_id": "",
                        "gold_cluster_title": "",
                        "note": "",
                        "suggested_persisted_cluster": _safe_lookup(persisted_map, article.id),
                        "suggested_jaccard_cluster": _safe_lookup(jaccard_map, article.id),
                        "suggested_semantic_cluster": _safe_lookup(semantic_map, article.id),
                    }
                )
            rows.sort(
                key=lambda row: (
                    row["suggested_semantic_cluster"] or "zzz",
                    row["suggested_jaccard_cluster"] or "zzz",
                    row["title"],
                    int(row["article_id"]),
                )
            )
            writer.writerows(rows)
    finally:
        db.close()

    print(f"pairs={pairs_path}")
    print(
        f"usable={meta['usable']} positive={meta['positive']} negative={meta['negative']} skipped={meta['skipped']}"
    )
    print(f"gold_template={output_path}")
    print(f"articles={len(article_ids)}")
    print("columns=article_id,title,source_id,pub_date,fetch_time,gold_cluster_id,gold_cluster_title,note,suggested_persisted_cluster,suggested_jaccard_cluster,suggested_semantic_cluster")
    if semantic_existing_embeddings_only:
        print("semantic_existing_embeddings_only=true")


def _print_pair_eval(name: str, elapsed: float, stats: Dict[str, float], cluster_metrics: Optional[Dict[str, float]]) -> None:
    print(f"--- {name} ---")
    print(f"  耗时：{elapsed:.2f}s")
    print(f"  TP={int(stats['tp'])} FP={int(stats['fp'])} TN={int(stats['tn'])} FN={int(stats['fn'])}")
    print(f"  Precision={stats['precision']:.4f} Recall={stats['recall']:.4f} Accuracy={stats['accuracy']:.4f} F1={stats['f1']:.4f}")
    print(f"  覆盖标注对：{int(stats['covered'])}")
    if cluster_metrics is None:
        print("  ARI/NMI/V-measure：未计算（缺少闭集 gold cluster 标注）")
    else:
        print(
            "  ARI={ari:.4f} NMI={nmi:.4f} V-measure={v_measure:.4f} (覆盖文章={articles})".format(
                **cluster_metrics
            )
        )
    print()


def _run_pair_evaluation(
    pairs_path: Path,
    lookback_hours: int,
    gold_clusters_path: Optional[Path],
    systems: List[str],
    semantic_existing_embeddings_only: bool,
    restrict_to_pair_articles: bool,
) -> None:
    from app.database import SessionLocal

    pairs, meta = _load_pairs(pairs_path)
    gold_clusters = _load_gold_clusters(gold_clusters_path)
    pair_article_ids = {article_id for left, right, _ in pairs for article_id in (left, right)}
    selected_article_ids = pair_article_ids if restrict_to_pair_articles else None
    if not pairs:
        print("没有可用的 0/1 pair 标注")
        return

    print(f"pairs={pairs_path}")
    print(
        f"usable={meta['usable']} positive={meta['positive']} negative={meta['negative']} skipped={meta['skipped']}"
    )
    if gold_clusters_path is not None:
        print(f"gold_clusters={gold_clusters_path} labeled_articles={len(gold_clusters)}")
    print(f"systems={','.join(systems)}")
    if semantic_existing_embeddings_only:
        print("semantic_existing_embeddings_only=true")
    if restrict_to_pair_articles:
        print(f"restrict_to_pair_articles=true labeled_articles={len(pair_article_ids)}")
    print()

    db = SessionLocal()
    try:
        available_runners = {
            "persisted": (
                "Persisted Events",
                lambda: _mapping_from_db_events(db, lookback_hours, article_ids=selected_article_ids),
            ),
            "jaccard": (
                "Jaccard (IDF-weighted)",
                lambda: _mapping_from_jaccard(db, lookback_hours, article_ids=selected_article_ids),
            ),
            "semantic": (
                "Semantic (current main path)",
                lambda: _mapping_from_semantic(
                    db,
                    lookback_hours,
                    existing_embeddings_only=semantic_existing_embeddings_only,
                    article_ids=selected_article_ids,
                ),
            ),
        }
        runners = [available_runners[system] for system in systems]
        for name, runner in runners:
            t0 = time.perf_counter()
            try:
                mapping = runner()
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                print(f"--- {name} ---")
                print(f"  耗时：{elapsed:.2f}s")
                print(f"  评测失败：{exc}")
                print()
                continue
            elapsed = time.perf_counter() - t0
            pair_stats = _evaluate_pairs(pairs, mapping)
            cluster_metrics = _evaluate_cluster_metrics(mapping, gold_clusters)
            _print_pair_eval(name, elapsed, pair_stats, cluster_metrics)
    finally:
        db.close()

    print("[note] 当前 semantic_index 主聚类按 cosine pair graph 合并；SEMANTIC_W_TIME / SEMANTIC_W_PLATFORM 目前不直接影响 Union-Find 合并结果。")


def _run_ablation_evaluation(
    pairs_path: Path,
    lookback_hours: int,
    gold_clusters_path: Optional[Path],
    ablations: List[str],
    semantic_existing_embeddings_only: bool,
    restrict_to_pair_articles: bool,
) -> None:
    """对 semantic 主路径跑多组消融配置并打印指标，方便与 baseline 直接对比。"""
    from app.database import SessionLocal

    pairs, meta = _load_pairs(pairs_path)
    gold_clusters = _load_gold_clusters(gold_clusters_path)
    pair_article_ids = {article_id for left, right, _ in pairs for article_id in (left, right)}
    selected_article_ids = pair_article_ids if restrict_to_pair_articles else None
    if not pairs:
        print("没有可用的 0/1 pair 标注")
        return

    print(f"pairs={pairs_path}")
    print(
        f"usable={meta['usable']} positive={meta['positive']} negative={meta['negative']} skipped={meta['skipped']}"
    )
    if gold_clusters_path is not None:
        print(f"gold_clusters={gold_clusters_path} labeled_articles={len(gold_clusters)}")
    print(f"ablations={','.join(ablations)}")
    if semantic_existing_embeddings_only:
        print("semantic_existing_embeddings_only=true")
    if restrict_to_pair_articles:
        print(f"restrict_to_pair_articles=true labeled_articles={len(pair_article_ids)}")
    print()

    db = SessionLocal()
    try:
        for name in ablations:
            if name not in _ABLATION_CONFIGS:
                print(f"[skip] 未知消融预设: {name}")
                continue
            config = _ABLATION_CONFIGS[name]
            label = f"Semantic · ablation={name}"
            t0 = time.perf_counter()
            try:
                mapping = _mapping_from_semantic(
                    db,
                    lookback_hours,
                    existing_embeddings_only=semantic_existing_embeddings_only,
                    article_ids=selected_article_ids,
                    **config,
                )
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                print(f"--- {label} ---")
                print(f"  耗时：{elapsed:.2f}s")
                print(f"  评测失败：{exc}")
                print()
                continue
            elapsed = time.perf_counter() - t0
            pair_stats = _evaluate_pairs(pairs, mapping)
            cluster_metrics = _evaluate_cluster_metrics(mapping, gold_clusters)
            _print_pair_eval(label, elapsed, pair_stats, cluster_metrics)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="聚类评测（W3 版）")
    parser.add_argument("--smoke", action="store_true", help="最小烟雾测试，不需要标注集")
    parser.add_argument("--pairs", type=str, default=None, help="article-pair 标注 csv/jsonl 路径")
    parser.add_argument("--gold-clusters", type=str, default=None, help="闭集 gold cluster 标注 csv/jsonl 路径；字段需含 article_id, cluster_id")
    parser.add_argument("--export-gold-template", type=str, default=None, help="导出闭集 gold cluster 标注模板 csv 路径")
    parser.add_argument("--systems", nargs="+", choices=["persisted", "jaccard", "semantic"], default=["persisted", "jaccard", "semantic"], help="选择要评测的系统")
    parser.add_argument("--semantic-existing-embeddings-only", action="store_true", help="语义评测时只使用已存在 embedding 的文章，避免现场回填模型")
    parser.add_argument("--restrict-to-pair-articles", action="store_true", help="仅在标注对涉及的文章子集上评测；适合作为快速 proxy 对照，不等价于全量窗口实验")
    parser.add_argument(
        "--ablation",
        nargs="+",
        default=None,
        help=(
            "对 semantic 主路径跑消融实验。可选值："
            f"{', '.join(_ABLATION_CONFIGS.keys())}, all。"
            "设置该参数时 --systems 会被忽略，转而按预设跑 semantic 的不同开关组合。"
        ),
    )
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--lookback", type=int, default=72, dest="lookback_hours")
    args = parser.parse_args()

    if args.smoke or not args.pairs:
        _smoke(limit=args.limit, lookback_hours=args.lookback_hours)
        return

    if args.export_gold_template:
        _export_gold_template(
            pairs_path=Path(args.pairs),
            lookback_hours=args.lookback_hours,
            output_path=Path(args.export_gold_template),
            semantic_existing_embeddings_only=args.semantic_existing_embeddings_only,
        )
        return

    if args.ablation:
        raw = args.ablation
        if len(raw) == 1 and raw[0] == "all":
            ablations = list(_ABLATION_CONFIGS.keys())
        else:
            ablations = raw
        _run_ablation_evaluation(
            pairs_path=Path(args.pairs),
            lookback_hours=args.lookback_hours,
            gold_clusters_path=Path(args.gold_clusters) if args.gold_clusters else None,
            ablations=ablations,
            semantic_existing_embeddings_only=args.semantic_existing_embeddings_only,
            restrict_to_pair_articles=args.restrict_to_pair_articles,
        )
        return

    _run_pair_evaluation(
        pairs_path=Path(args.pairs),
        lookback_hours=args.lookback_hours,
        gold_clusters_path=Path(args.gold_clusters) if args.gold_clusters else None,
        systems=args.systems,
        semantic_existing_embeddings_only=args.semantic_existing_embeddings_only,
        restrict_to_pair_articles=args.restrict_to_pair_articles,
    )


if __name__ == "__main__":
    main()

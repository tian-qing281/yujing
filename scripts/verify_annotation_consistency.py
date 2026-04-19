"""
交叉校验 runtime/eval/pairs_seed_100.csv 与 gold_clusters_seed_100_template.csv 的一致性.

规则:
    pair=1 且 gold[a] != gold[b]  => 冲突 (pair 认为同事件, gold 却拆开)
    pair=0 且 gold[a] == gold[b]  => 冲突 (pair 认为不同事件, gold 却合并)
    任一端未被 gold 标注 (空 gold_cluster_id)  => skip (非冲突, 只报告数字)

退出码: 冲突数为 0 时返回 0; 非 0 时返回 1, 适合 CI.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "runtime" / "eval"
PAIRS_CSV = EVAL_DIR / "pairs_seed_100.csv"
GOLD_CSV = EVAL_DIR / "gold_clusters_seed_100_template.csv"


def _load_gold() -> Tuple[Dict[str, str], Dict[str, str]]:
    labels: Dict[str, str] = {}
    titles: Dict[str, str] = {}
    with GOLD_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cluster_id = (row.get("gold_cluster_id") or "").strip()
            if not cluster_id:
                continue
            article_id = str(row.get("article_id", "")).strip()
            if not article_id:
                continue
            labels[article_id] = cluster_id
            titles[article_id] = (row.get("title") or "").strip()
    return labels, titles


def _iter_pairs():
    with PAIRS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            label = (row.get("label") or "").strip()
            if label not in {"0", "1"}:
                continue
            yield str(row["article_a"]).strip(), str(row["article_b"]).strip(), label


def main() -> int:
    gold_labels, gold_titles = _load_gold()
    pos1_split: List[tuple] = []
    neg0_merge: List[tuple] = []
    skipped = 0
    total = 0
    for a, b, label in _iter_pairs():
        total += 1
        if a not in gold_labels or b not in gold_labels:
            skipped += 1
            continue
        ga, gb = gold_labels[a], gold_labels[b]
        if label == "1" and ga != gb:
            pos1_split.append((a, b, ga, gb))
        elif label == "0" and ga == gb:
            neg0_merge.append((a, b, ga))

    print("=== annotation consistency check ===")
    print(f"pair rows (with 0/1 label):              {total}")
    print(f"gold labeled articles:                   {len(gold_labels)}")
    print(f"pair with at least one side not in gold: {skipped}")
    print(f"pair=1 但 gold 拆开:                      {len(pos1_split)}")
    print(f"pair=0 但 gold 合并:                      {len(neg0_merge)}")
    print()

    if pos1_split:
        print("--- pair=1 冲突 ---")
        for a, b, ga, gb in pos1_split:
            print(f"  [a={a} c={ga}]  <->  [b={b} c={gb}]")
            print(f"    A: {gold_titles.get(a, '')}")
            print(f"    B: {gold_titles.get(b, '')}")
    if neg0_merge:
        print("--- pair=0 冲突 ---")
        for a, b, g in neg0_merge:
            print(f"  [a={a}]  <->  [b={b}]  (都在 gold cluster {g})")
            print(f"    A: {gold_titles.get(a, '')}")
            print(f"    B: {gold_titles.get(b, '')}")

    conflicts = len(pos1_split) + len(neg0_merge)
    print()
    print(f"conflicts={conflicts}")
    return 0 if conflicts == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

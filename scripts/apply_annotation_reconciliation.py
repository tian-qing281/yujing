"""
幂等地把 runtime/eval/reconciliation.json 里的裁决应用到:
    runtime/eval/pairs_seed_100.csv
    runtime/eval/pairs_seed_100.jsonl
    runtime/eval/gold_clusters_seed_100_template.csv

语义:
  merge_gold_clusters:  所有 gold_cluster_id == from 的行, gold_cluster_id 改为 into.
  flip_pair_labels:     匹配 (article_a, article_b) 的行, label 改为 to
                        (顺序不敏感, 即 (a,b) 和 (b,a) 都命中).

重复运行安全: 第二次执行时, 声明已经生效, 不再产生任何写入差异.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "runtime" / "eval"
RECON_PATH = EVAL_DIR / "reconciliation.json"
PAIRS_CSV = EVAL_DIR / "pairs_seed_100.csv"
PAIRS_JSONL = EVAL_DIR / "pairs_seed_100.jsonl"
GOLD_CSV = EVAL_DIR / "gold_clusters_seed_100_template.csv"


def _load_recon(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _apply_gold(recon: dict) -> Tuple[int, List[str]]:
    """返回 (变更行数, 人类可读的变更记录)."""
    merges: List[dict] = recon.get("merge_gold_clusters", [])
    if not merges:
        return 0, []
    rename: Dict[str, str] = {m["from"]: m["into"] for m in merges}

    # 支持传递合并链 (A -> B, B -> C 就得到 A -> C); 当前声明没有这种情况, 但代码便宜就支持了.
    def _resolve(label: str) -> str:
        seen = set()
        cur = label
        while cur in rename and cur not in seen:
            seen.add(cur)
            cur = rename[cur]
        return cur

    rows: List[dict] = []
    fieldnames: List[str] = []
    with GOLD_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    changed = 0
    log: List[str] = []
    for row in rows:
        original = row.get("gold_cluster_id", "")
        if not original:
            continue
        new_label = _resolve(original)
        if new_label != original:
            row["gold_cluster_id"] = new_label
            changed += 1
            log.append(f"  gold[article_id={row.get('article_id')}]: {original} -> {new_label}  # {row.get('title','')[:30]}")

    if changed:
        with GOLD_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    return changed, log


def _normalize_pair_key(a, b) -> Tuple[int, int]:
    left, right = int(a), int(b)
    return (left, right) if left < right else (right, left)


def _apply_pairs_csv(recon: dict) -> Tuple[int, List[str]]:
    flips: List[dict] = recon.get("flip_pair_labels", [])
    if not flips:
        return 0, []
    target: Dict[Tuple[int, int], str] = {
        _normalize_pair_key(f["article_a"], f["article_b"]): str(f["to"])
        for f in flips
    }

    rows: List[dict] = []
    fieldnames: List[str] = []
    with PAIRS_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    changed = 0
    log: List[str] = []
    for row in rows:
        try:
            key = _normalize_pair_key(row["article_a"], row["article_b"])
        except (KeyError, ValueError):
            continue
        if key not in target:
            continue
        new_label = target[key]
        if row.get("label") != new_label:
            log.append(f"  pair[{row['article_a']},{row['article_b']}]: {row.get('label')} -> {new_label}")
            row["label"] = new_label
            changed += 1

    if changed:
        with PAIRS_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    return changed, log


def _apply_pairs_jsonl(recon: dict) -> int:
    """保持 jsonl 与 csv 同步. 只做写回, 不再输出 log (csv 已打过)."""
    flips: List[dict] = recon.get("flip_pair_labels", [])
    if not flips or not PAIRS_JSONL.exists():
        return 0
    target: Dict[Tuple[int, int], str] = {
        _normalize_pair_key(f["article_a"], f["article_b"]): str(f["to"])
        for f in flips
    }

    lines_out: List[str] = []
    changed = 0
    with PAIRS_JSONL.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            if not raw.strip():
                lines_out.append(raw)
                continue
            obj = json.loads(raw)
            try:
                key = _normalize_pair_key(obj["article_a"], obj["article_b"])
            except (KeyError, ValueError):
                lines_out.append(raw)
                continue
            if key in target and str(obj.get("label")) != target[key]:
                obj["label"] = int(target[key]) if target[key] in ("0", "1") else target[key]
                changed += 1
                lines_out.append(json.dumps(obj, ensure_ascii=False))
            else:
                lines_out.append(raw)

    if changed:
        with PAIRS_JSONL.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines_out) + "\n")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="apply reconciliation.json to pairs/gold csv")
    parser.add_argument("--recon", default=str(RECON_PATH))
    args = parser.parse_args()

    recon = _load_recon(Path(args.recon))
    print(f"[apply] reconciliation file: {args.recon}")
    print(f"[apply] merge_gold_clusters entries: {len(recon.get('merge_gold_clusters', []))}")
    print(f"[apply] flip_pair_labels entries:    {len(recon.get('flip_pair_labels', []))}")

    gold_changed, gold_log = _apply_gold(recon)
    pair_changed, pair_log = _apply_pairs_csv(recon)
    jsonl_changed = _apply_pairs_jsonl(recon)

    print(f"\n[apply] gold rows changed:       {gold_changed}")
    for line in gold_log:
        print(line)
    print(f"\n[apply] pairs csv rows changed:  {pair_changed}")
    for line in pair_log:
        print(line)
    print(f"[apply] pairs jsonl rows changed: {jsonl_changed}")

    if gold_changed == 0 and pair_changed == 0 and jsonl_changed == 0:
        print("\n[apply] 无变动 (声明已是现状, 幂等退出).")
    else:
        print("\n[apply] 完成. 请立即跑 verify_annotation_consistency.py 确认 conflicts=0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

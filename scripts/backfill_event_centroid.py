"""S1.1 全量回填 events.centroid 脚本

前提：article_embeddings 已全量存在（W1 阶段铺好）。
本脚本不调 GPU 推理，纯 SQL+numpy；估计 7000 事件几分钟内跑完。

算法与 P1 增量聚类完全一致：
    centroid = L2_normalize(mean(article_vectors))
    centroid_count = 文章数

用法：
    python -m scripts.backfill_event_centroid [--dry-run]
"""
import argparse
import sqlite3
import sys
import time

import numpy as np

from app.services.embedding import EMBED_DIM

DB = r"runtime/db/yujing.db"
BATCH_COMMIT = 200


def l2_normalize(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-12:
        return v
    return (v / n).astype(np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 个事件，0=全部")
    args = parser.parse_args()

    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA journal_mode=WAL")

    sql = "SELECT id FROM events WHERE centroid IS NULL ORDER BY id"
    if args.limit > 0:
        sql += f" LIMIT {args.limit}"
    pending = [r[0] for r in conn.execute(sql).fetchall()]
    total = len(pending)
    print(f"[backfill] 待回填事件数：{total}（dry_run={args.dry_run}）")

    t0 = time.time()
    ok = skipped_no_vec = updated = 0
    batch_since_commit = 0

    for i, eid in enumerate(pending, 1):
        rows = conn.execute(
            """
            SELECT ae.vector
            FROM article_embeddings ae
            JOIN event_articles ea ON ea.article_id = ae.article_id
            WHERE ea.event_id = ?
            """,
            (eid,),
        ).fetchall()
        if not rows:
            skipped_no_vec += 1
            continue

        vecs = np.stack(
            [np.frombuffer(r[0], dtype=np.float32) for r in rows]
        )
        if vecs.shape[1] != EMBED_DIM:
            print(f"[warn] event {eid} dim mismatch {vecs.shape[1]} vs {EMBED_DIM}, skip")
            skipped_no_vec += 1
            continue

        centroid = l2_normalize(vecs.mean(axis=0))
        cnt = int(vecs.shape[0])

        if not args.dry_run:
            conn.execute(
                "UPDATE events SET centroid=?, centroid_count=? WHERE id=?",
                (centroid.tobytes(), cnt, eid),
            )
            updated += 1
            batch_since_commit += 1
            if batch_since_commit >= BATCH_COMMIT:
                conn.commit()
                batch_since_commit = 0

        ok += 1
        if i % 500 == 0 or i == total:
            elapsed = time.time() - t0
            rate = i / max(elapsed, 0.001)
            print(f"  [{i}/{total}]  ok={ok}  no_vec={skipped_no_vec}  updated={updated}  {rate:.1f} ev/s")

    if not args.dry_run and batch_since_commit > 0:
        conn.commit()

    elapsed = time.time() - t0
    print(f"\n[backfill] 完成。耗时 {elapsed:.1f}s  ok={ok}  无文章向量={skipped_no_vec}  实际写入={updated}")

    after = conn.execute("SELECT COUNT(*) FROM events WHERE centroid IS NOT NULL").fetchone()[0]
    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    print(f"[backfill] events.centroid 覆盖：{after}/{total_events} ({after / total_events * 100:.1f}%)")


if __name__ == "__main__":
    main()

"""构建答辩演示用数据库 yujing.demo.db。

策略：从主库 yujing.db 复制一份，再在副本内裁剪：每个平台保留 heat_score
最高的前 10 个事件，连带保留其全部关联文章 / embeddings / FTS / topics。
其他用户态表（subscriptions / blocklist / user_profiles）全量保留。

用法：
    python scripts/build_demo_db.py                   # 默认行为
    python scripts/build_demo_db.py --top 5           # 每平台 5 条
    python scripts/build_demo_db.py --dry-run         # 只打印统计不执行删除

幂等：每次都会重新拷贝主库覆盖 demo.db。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DB = PROJECT_ROOT / "runtime" / "db" / "yujing.db"
DST_DB = PROJECT_ROOT / "runtime" / "db" / "yujing.demo.db"


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} TB"


def copy_main_db() -> None:
    if not SRC_DB.exists():
        sys.exit(f"[ERR] 主库不存在: {SRC_DB}")

    # 清理旧 demo 库及其 WAL/SHM
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(DST_DB) + suffix)
        if p.exists():
            p.unlink()
            print(f"[清理] 删除旧文件 {p.name}")

    print(f"[拷贝] {SRC_DB.name} → {DST_DB.name}（{human_size(SRC_DB.stat().st_size)}）")
    shutil.copy2(SRC_DB, DST_DB)


def fetch_keep_event_ids(conn: sqlite3.Connection, top_n: int) -> list[int]:
    """每个 primary_source_id 取热度前 top_n 事件。"""
    sql = """
        WITH ranked AS (
            SELECT id, primary_source_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY primary_source_id
                       ORDER BY heat_score DESC, latest_article_time DESC, id DESC
                   ) AS rn
            FROM events
            WHERE primary_source_id IS NOT NULL AND primary_source_id != ''
        )
        SELECT id FROM ranked WHERE rn <= ?
    """
    rows = conn.execute(sql, (top_n,)).fetchall()
    return [r[0] for r in rows]


def fetch_keep_article_ids(conn: sqlite3.Connection, event_ids: list[int]) -> set[int]:
    if not event_ids:
        return set()
    placeholders = ",".join("?" * len(event_ids))
    # 关联文章
    rows = conn.execute(
        f"SELECT DISTINCT article_id FROM event_articles WHERE event_id IN ({placeholders})",
        event_ids,
    ).fetchall()
    ids = {r[0] for r in rows}
    # 代表文章（即便不在 event_articles 也兜底保留）
    rows = conn.execute(
        f"SELECT representative_article_id FROM events WHERE id IN ({placeholders}) "
        "AND representative_article_id IS NOT NULL",
        event_ids,
    ).fetchall()
    ids.update(r[0] for r in rows)
    ids.discard(None)
    return ids


def report_platform_stats(conn: sqlite3.Connection, label: str) -> None:
    print(f"\n[{label}] 各平台事件数：")
    rows = conn.execute(
        "SELECT COALESCE(primary_source_id,'<NULL>') AS s, COUNT(*) "
        "FROM events GROUP BY s ORDER BY s"
    ).fetchall()
    for s, c in rows:
        print(f"    {s:<20s} {c}")
    total_events = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    total_emb = conn.execute(
        "SELECT COUNT(*) FROM article_embeddings"
    ).fetchone()[0]
    total_topics = conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0]
    print(
        f"  合计：events={total_events} articles={total_articles} "
        f"embeddings={total_emb} topics={total_topics}"
    )


def prune(top_n: int, dry_run: bool) -> None:
    if not dry_run:
        copy_main_db()

    target = SRC_DB if dry_run else DST_DB
    if dry_run:
        # 主库可能被后端 WAL 模式打开，用 URI 只读连接避免抢锁
        conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(target)
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("PRAGMA journal_mode = DELETE")  # demo 库不用 WAL，方便分发

    report_platform_stats(conn, "裁剪前")

    keep_events = fetch_keep_event_ids(conn, top_n)
    print(f"\n[选取] 保留事件数 = {len(keep_events)}（按 primary_source_id 各取 top {top_n}）")

    keep_articles = fetch_keep_article_ids(conn, keep_events)
    print(f"[选取] 保留文章数 = {len(keep_articles)}")

    if dry_run:
        print("\n[dry-run] 未执行任何删除")
        conn.close()
        return

    cur = conn.cursor()
    ev_csv = ",".join(str(i) for i in keep_events) or "NULL"
    ar_csv = ",".join(str(i) for i in keep_articles) or "NULL"

    # 1. event_articles
    cur.execute(f"DELETE FROM event_articles WHERE event_id NOT IN ({ev_csv})")
    print(f"[删除] event_articles -{cur.rowcount}")

    # 2. topic_events
    cur.execute(f"DELETE FROM topic_events WHERE event_id NOT IN ({ev_csv})")
    print(f"[删除] topic_events -{cur.rowcount}")

    # 3. events
    cur.execute(f"DELETE FROM events WHERE id NOT IN ({ev_csv})")
    print(f"[删除] events -{cur.rowcount}")

    # 4. topics（无任何 topic_events 引用的）
    cur.execute(
        "DELETE FROM topics WHERE id NOT IN (SELECT DISTINCT topic_id FROM topic_events)"
    )
    print(f"[删除] topics -{cur.rowcount}")

    # 5. articles
    cur.execute(f"DELETE FROM articles WHERE id NOT IN ({ar_csv})")
    print(f"[删除] articles -{cur.rowcount}")

    # 6. article_embeddings
    cur.execute(f"DELETE FROM article_embeddings WHERE article_id NOT IN ({ar_csv})")
    print(f"[删除] article_embeddings -{cur.rowcount}")

    # 7. articles_fts（虚表，按 rowid 删；rowid 与 article.id 一致）
    try:
        cur.execute(f"DELETE FROM articles_fts WHERE rowid NOT IN ({ar_csv})")
        print(f"[删除] articles_fts -{cur.rowcount}")
    except sqlite3.OperationalError as e:
        print(f"[跳过] articles_fts: {e}")

    # 8. 校准 topics 表冗余统计字段（events 表的 article_count/platform_count
    # 经实测已与 event_articles 对齐，无需重算；topics 表则因裁剪后未刷新需修正）
    cur.execute(
        """
        UPDATE topics SET
          event_count = (
            SELECT COUNT(*) FROM topic_events WHERE topic_id = topics.id
          ),
          article_count = (
            SELECT COUNT(DISTINCT ea.article_id)
            FROM topic_events te
            JOIN event_articles ea ON ea.event_id = te.event_id
            WHERE te.topic_id = topics.id
          ),
          platform_count = (
            SELECT COUNT(DISTINCT a.source_id)
            FROM topic_events te
            JOIN event_articles ea ON ea.event_id = te.event_id
            JOIN articles a ON a.id = ea.article_id
            WHERE te.topic_id = topics.id
          )
        """
    )
    print(f"[校准] topics 统计字段 {cur.rowcount} 行")

    conn.commit()
    print("\n[压缩] VACUUM ...")
    t0 = time.time()
    conn.execute("VACUUM")
    print(f"[压缩] 完成，用时 {time.time() - t0:.1f}s")

    report_platform_stats(conn, "裁剪后")
    conn.close()

    final_size = DST_DB.stat().st_size
    print(f"\n[完成] {DST_DB}  大小 {human_size(final_size)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=10, help="每平台保留事件数（默认 10）")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不修改任何文件")
    args = parser.parse_args()
    prune(args.top, args.dry_run)


if __name__ == "__main__":
    main()

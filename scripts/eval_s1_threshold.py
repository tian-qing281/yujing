"""S1 订阅语义召回阈值评测脚本

目的：
    1. 在当前 334 个有 centroid 的事件上，对多个候选订阅词，统计不同阈值
       (0.30 ~ 0.65) 下的命中数与样例
    2. 检查命中是否包含字面匹配 (kw in title) 与纯语义匹配的占比
    3. 给阈值/权重的选择提供数据依据
"""
import sqlite3
import numpy as np
from app.services.subscription_semantic import get_subscription_vectors
from app.services.embedding import EMBED_DIM as DIM

DB = r"runtime/db/yujing.db"

# 测试订阅词：覆盖政治/科技/经济/民生/军事 五大类
TEST_KEYWORDS = [
    "美国", "人工智能", "房地产", "教育改革", "医疗保险",
    "新能源汽车", "半导体", "国防军事", "气候变化", "粮食安全",
]
THRESHOLDS = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]


def main():
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT id, title, centroid FROM events WHERE centroid IS NOT NULL"
    ).fetchall()
    print(f"=== 评测样本：{len(rows)} 个 event ===\n")

    centroids = np.frombuffer(b"".join([r[2] for r in rows]), dtype=np.float32).reshape(len(rows), DIM)
    titles = [r[1] for r in rows]

    sub_vecs = get_subscription_vectors(TEST_KEYWORDS)  # dict: kw -> (dim,)
    sub_mat = np.stack([sub_vecs[k] for k in TEST_KEYWORDS])  # (S, dim)

    # 余弦：所有事件 × 所有订阅词
    sim = centroids @ sub_mat.T  # (N, S)

    # 1) 各阈值下的命中事件总数 & 每订阅词命中数
    print("【阈值扫描：各订阅词命中事件数】")
    header = "kw".ljust(12) + "".join(f"  thr>={t:.2f}".ljust(11) for t in THRESHOLDS)
    print(header)
    for j, kw in enumerate(TEST_KEYWORDS):
        col = sim[:, j]
        line = kw.ljust(12)
        for t in THRESHOLDS:
            line += f"  {(col >= t).sum():>3}".ljust(11)
        print(line)

    # 2) 全局：每个 event 取最大相似度 → 直方图
    print("\n【全局 max-cos 分布（每个事件对 10 个订阅词取最大）】")
    max_sim = sim.max(axis=1)
    bins = [0.0, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 1.0]
    hist, _ = np.histogram(max_sim, bins=bins)
    for lo, hi, c in zip(bins[:-1], bins[1:], hist):
        bar = "█" * min(40, int(c / max(hist) * 40)) if hist.max() else ""
        print(f"  [{lo:.2f}, {hi:.2f})  {c:>4}  {bar}")

    # 3) 字面匹配 vs 纯语义匹配（thr=0.40）
    print("\n【thr=0.40 命中：字面 vs 纯语义】")
    for j, kw in enumerate(TEST_KEYWORDS):
        hits = np.where(sim[:, j] >= 0.40)[0]
        if len(hits) == 0:
            continue
        literal = sum(1 for i in hits if kw in titles[i])
        semantic_only = len(hits) - literal
        print(f"  {kw:<10} 命中 {len(hits):>3}  字面 {literal:>3}  纯语义 {semantic_only:>3}")

    # 4) 边界样例：thr ∈ [0.40, 0.50) 的 top10（验证人工感觉）
    print("\n【边界样例：cos ∈ [0.40, 0.50) 的纯语义命中（每订阅词最多 5 条）】")
    for j, kw in enumerate(TEST_KEYWORDS):
        col = sim[:, j]
        mask = (col >= 0.40) & (col < 0.50)
        idxs = np.where(mask)[0]
        # 按相似度从高到低
        idxs = sorted(idxs, key=lambda i: -col[i])
        shown = 0
        for i in idxs:
            if kw in titles[i]:
                continue
            if shown >= 5:
                break
            print(f"  [{col[i]:.3f}] {kw} ← {titles[i]}")
            shown += 1

    # 5) 高分样例：cos >= 0.50（验证阈值是否过严）
    print("\n【高置信样例：cos >= 0.50 的纯语义命中（每订阅词最多 3 条）】")
    for j, kw in enumerate(TEST_KEYWORDS):
        col = sim[:, j]
        idxs = np.where(col >= 0.50)[0]
        idxs = sorted(idxs, key=lambda i: -col[i])
        shown = 0
        for i in idxs:
            if kw in titles[i]:
                continue
            if shown >= 3:
                break
            print(f"  [{col[i]:.3f}] {kw} ← {titles[i]}")
            shown += 1


if __name__ == "__main__":
    main()

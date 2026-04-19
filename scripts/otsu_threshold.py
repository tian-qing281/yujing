"""用 Otsu 方法自动寻找 cosine 分布的最佳分割阈值"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import faiss, math
from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
rows = db.execute(text(
    "SELECT a.id, ae.vector FROM articles a "
    "JOIN article_embeddings ae ON a.id = ae.article_id "
    "WHERE a.pub_date > datetime('now', '-720 hours')"
)).fetchall()
db.close()

dim = 512
vectors, ids = {}, []
for r in rows:
    v = np.frombuffer(r[1], dtype=np.float32)
    if len(v) == dim:
        vectors[r[0]] = v
        ids.append(r[0])

print(f"文章数: {len(ids)}")
matrix = np.stack([vectors[i] for i in ids]).astype(np.float32)

nlist = max(1, min(64, int(math.sqrt(len(ids))), len(ids)))
quantizer = faiss.IndexFlatIP(dim)
base = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
base.train(matrix)
index = faiss.IndexIDMap2(base)
index.add_with_ids(matrix, np.array(ids, dtype=np.int64))
index.nprobe = min(8, nlist)

all_cos = []
for aid in ids:
    v = vectors[aid].reshape(1, -1)
    scores, nids = index.search(v, 21)
    for j in range(scores.shape[1]):
        nid = int(nids[0][j])
        if nid == aid or nid not in vectors:
            continue
        all_cos.append(float(scores[0][j]))

all_cos = np.array(all_cos)
print(f"共 {len(all_cos)} 个cosine值")

# Otsu: 在 [0.45, 0.85] 范围内搜索最大类间方差分割点
best_t, best_var = 0.6, 0
for t in np.arange(0.45, 0.85, 0.005):
    c0 = all_cos[all_cos < t]
    c1 = all_cos[all_cos >= t]
    if len(c0) == 0 or len(c1) == 0:
        continue
    w0, w1 = len(c0) / len(all_cos), len(c1) / len(all_cos)
    var = w0 * w1 * (c0.mean() - c1.mean()) ** 2
    if var > best_var:
        best_var = var
        best_t = t

print(f"\nOtsu 最优分割点: {best_t:.4f}")
print(f"  低于分割点: {(all_cos < best_t).sum()} ({(all_cos < best_t).mean()*100:.1f}%)")
print(f"  高于分割点: {(all_cos >= best_t).sum()} ({(all_cos >= best_t).mean()*100:.1f}%)")
print(f"  低组均值: {all_cos[all_cos < best_t].mean():.4f}")
print(f"  高组均值: {all_cos[all_cos >= best_t].mean():.4f}")

# 也试试 KMeans 二分类
from sklearn.cluster import KMeans
km = KMeans(n_clusters=2, random_state=42, n_init=10)
labels = km.fit_predict(all_cos.reshape(-1, 1))
centers = sorted(km.cluster_centers_.flatten())
kmeans_threshold = (centers[0] + centers[1]) / 2
print(f"\nKMeans 二分类中心: {centers[0]:.4f}, {centers[1]:.4f}")
print(f"KMeans 分割点(中点): {kmeans_threshold:.4f}")

# 在高组(>= Otsu分割点)上再做一次 Otsu，找同事件 vs 主题相似的分界
high_group = all_cos[all_cos >= best_t]
print(f"\n=== 高组内部二次分割 ===")
print(f"高组大小: {len(high_group)}, 均值: {high_group.mean():.4f}")
best_t2, best_var2 = 0.65, 0
for t in np.arange(0.55, 0.85, 0.005):
    c0 = high_group[high_group < t]
    c1 = high_group[high_group >= t]
    if len(c0) == 0 or len(c1) == 0:
        continue
    w0, w1 = len(c0) / len(high_group), len(c1) / len(high_group)
    var = w0 * w1 * (c0.mean() - c1.mean()) ** 2
    if var > best_var2:
        best_var2 = var
        best_t2 = t
print(f"高组 Otsu 分割点: {best_t2:.4f}")
print(f"  低子组: {(high_group < best_t2).sum()} ({(high_group < best_t2).mean()*100:.1f}%)")
print(f"  高子组: {(high_group >= best_t2).sum()} ({(high_group >= best_t2).mean()*100:.1f}%)")
print(f"  低子组均值: {high_group[high_group < best_t2].mean():.4f}")
print(f"  高子组均值: {high_group[high_group >= best_t2].mean():.4f}")

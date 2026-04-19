"""分析全量 top-K cosine 分布（包含低于硬门槛的），判断 P90 自适应阈值的实际值"""
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
vectors = {}
ids = []
for r in rows:
    aid = r[0]
    v = np.frombuffer(r[1], dtype=np.float32)
    if len(v) == dim:
        vectors[aid] = v
        ids.append(aid)

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
print(f"全量 top-K cosine 数: {len(all_cos)}")
print(f"均值={all_cos.mean():.4f}, std={all_cos.std():.4f}")
for p in [50, 75, 80, 85, 90, 95, 99]:
    print(f"  P{p} = {np.percentile(all_cos, p):.4f}")

# 统计各区间分布
bins = [0, 0.3, 0.4, 0.5, 0.55, 0.58, 0.6, 0.65, 0.7, 0.8, 1.0]
hist, _ = np.histogram(all_cos, bins=bins)
print("\n区间分布:")
for i in range(len(bins)-1):
    pct = hist[i] / len(all_cos) * 100
    print(f"  [{bins[i]:.2f}, {bins[i+1]:.2f}): {hist[i]:>6d} ({pct:.1f}%)")

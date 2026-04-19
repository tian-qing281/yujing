"""检查当前纯cosine候选对的P95自适应阈值"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from app.database import SessionLocal, Article, ArticleEmbedding, utcnow
from app.services.embedding import EMBED_MODEL_NAME, bytes_to_vector
from datetime import datetime, timedelta

def main():
    db = SessionLocal()
    cutoff = utcnow() - timedelta(hours=720)
    articles = db.query(Article).filter(Article.fetch_time >= cutoff).all()
    print(f"文章数: {len(articles)}")

    emb_rows = db.query(ArticleEmbedding).filter(
        ArticleEmbedding.model_name == EMBED_MODEL_NAME
    ).all()
    vecs = {r.article_id: bytes_to_vector(r.vector, r.dim) for r in emb_rows}
    print(f"有向量: {len(vecs)}")

    # 模拟 FAISS top-20 近邻的 cosine 分布（采样）
    import random
    art_ids = [a.id for a in articles if a.id in vecs]
    random.shuffle(art_ids)
    sample = art_ids[:500]  # 采样500篇

    all_cosines = []
    for aid in sample:
        va = vecs[aid]
        # 找 top-20
        scores = []
        for bid in art_ids:
            if bid == aid:
                continue
            vb = vecs.get(bid)
            if vb is not None:
                scores.append(float(np.dot(va, vb)))
        scores.sort(reverse=True)
        top20 = scores[:20]
        # 只取过了0.58硬门槛的
        filtered = [s for s in top20 if s >= 0.58]
        all_cosines.extend(filtered)

    arr = np.array(all_cosines)
    print(f"\n过0.58硬门槛的候选cosine: {len(arr)} 个")
    print(f"均值: {arr.mean():.4f}")
    for p in [50, 75, 90, 95, 99]:
        print(f"  P{p} = {np.percentile(arr, p):.4f}")

    db.close()

if __name__ == "__main__":
    main()

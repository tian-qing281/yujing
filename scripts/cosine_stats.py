"""
统计所有已向量化文章对的 cosine 分布
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from app.database import SessionLocal, Article, ArticleEmbedding
from app.services.embedding import EMBED_MODEL_NAME, bytes_to_vector
from tqdm import tqdm

def main():
    db = SessionLocal()
    try:
        # 取全部有向量的文章
        rows = db.query(ArticleEmbedding).filter(ArticleEmbedding.model_name == EMBED_MODEL_NAME).all()
        vecs = [bytes_to_vector(r.vector, r.dim) for r in rows]
        ids = [r.article_id for r in rows]
        vecs = np.stack(vecs)
        n = len(vecs)
        print(f"共 {n} 篇文章，{n*(n-1)//2} 对")
        # 只采样部分 pair，避免 OOM
        sample_size = min(100000, n*(n-1)//2)
        idx = np.random.choice(n*(n-1)//2, sample_size, replace=False)
        # 生成所有 pair 的上三角索引
        pairs = []
        for i in range(n):
            for j in range(i+1, n):
                pairs.append((i, j))
        sample_pairs = [pairs[k] for k in idx]
        cosines = []
        for i, j in tqdm(sample_pairs, desc="计算cosine"):
            cos = float(np.dot(vecs[i], vecs[j]))
            cosines.append(cos)
        cosines = np.array(cosines)
        print(f"均值: {cosines.mean():.4f}  标准差: {cosines.std():.4f}")
        print(f"分位数: 5%={np.percentile(cosines,5):.3f}  25%={np.percentile(cosines,25):.3f}  50%={np.percentile(cosines,50):.3f}  75%={np.percentile(cosines,75):.3f}  95%={np.percentile(cosines,95):.3f}")
        import matplotlib.pyplot as plt
        plt.hist(cosines, bins=50, alpha=0.7)
        plt.title("Cosine Similarity Distribution (sampled pairs)")
        plt.xlabel("cosine")
        plt.ylabel("count")
        plt.show()
    finally:
        db.close()

if __name__ == "__main__":
    main()

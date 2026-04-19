"""一次性全量向量化所有文章并重建 FAISS 索引"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal, Article
from app.services.semantic_cluster import ensure_embeddings

def main():
    db = SessionLocal()
    try:
        total = db.query(Article).count()
        articles = db.query(Article).all()
        print(f"数据库文章总数: {total}")

        emb_map = ensure_embeddings(db, articles)
        print(f"已向量化: {len(emb_map)} 篇")
        print(f"未覆盖: {total - len(emb_map)} 篇")
    finally:
        db.close()

if __name__ == "__main__":
    main()

"""分析多个事件的"标题明显相关"对的cosine分布，找到合理硬门槛"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from app.database import SessionLocal, Article, Event, EventArticle, ArticleEmbedding
from app.services.embedding import EMBED_MODEL_NAME, bytes_to_vector

def main():
    db = SessionLocal()

    # 取文章数最多的 top-20 大事件
    events = db.query(Event).order_by(Event.article_count.desc()).limit(20).all()

    all_intra_cosines = []  # 事件内所有对的cosine
    all_rep_cosines = []    # 与代表文章的cosine

    for event in events:
        eas = db.query(EventArticle).filter(EventArticle.event_id == event.id).all()
        aids = [ea.article_id for ea in eas]
        emb_rows = db.query(ArticleEmbedding).filter(
            ArticleEmbedding.article_id.in_(aids),
            ArticleEmbedding.model_name == EMBED_MODEL_NAME,
        ).all()
        vecs = {r.article_id: bytes_to_vector(r.vector, r.dim) for r in emb_rows}

        # 与代表文章的cosine
        if event.representative_article_id in vecs:
            rep_vec = vecs[event.representative_article_id]
            for aid, vec in vecs.items():
                if aid != event.representative_article_id:
                    cos = float(np.dot(rep_vec, vec))
                    all_rep_cosines.append(cos)

        # 事件内所有对
        vids = list(vecs.keys())
        for i in range(len(vids)):
            for j in range(i+1, len(vids)):
                cos = float(np.dot(vecs[vids[i]], vecs[vids[j]]))
                all_intra_cosines.append(cos)

    arr_rep = np.array(all_rep_cosines)
    arr_intra = np.array(all_intra_cosines)

    print(f"Top-20大事件，共 {len(all_rep_cosines)} 个成员-代表对")
    print(f"成员与代表的cosine分布:")
    print(f"  均值={arr_rep.mean():.4f}  中位数={np.median(arr_rep):.4f}")
    for p in [5, 10, 25, 50, 75, 90, 95]:
        print(f"  P{p}={np.percentile(arr_rep, p):.4f}")

    print(f"\nTop-20大事件，共 {len(all_intra_cosines)} 个事件内对")
    print(f"事件内cosine分布:")
    print(f"  均值={arr_intra.mean():.4f}  中位数={np.median(arr_intra):.4f}")
    for p in [5, 10, 25, 50, 75, 90, 95]:
        print(f"  P{p}={np.percentile(arr_intra, p):.4f}")

    # 对比：随机跨事件对
    import random
    all_events_vecs = {}
    for event in events:
        eas = db.query(EventArticle).filter(EventArticle.event_id == event.id).all()
        aids = [ea.article_id for ea in eas]
        emb_rows = db.query(ArticleEmbedding).filter(
            ArticleEmbedding.article_id.in_(aids),
            ArticleEmbedding.model_name == EMBED_MODEL_NAME,
        ).all()
        for r in emb_rows:
            all_events_vecs[r.article_id] = (event.id, bytes_to_vector(r.vector, r.dim))

    cross_cosines = []
    aids_list = list(all_events_vecs.keys())
    for _ in range(min(50000, len(aids_list)*10)):
        a, b = random.sample(aids_list, 2)
        if all_events_vecs[a][0] != all_events_vecs[b][0]:  # 不同事件
            cos = float(np.dot(all_events_vecs[a][1], all_events_vecs[b][1]))
            cross_cosines.append(cos)
    if cross_cosines:
        arr_cross = np.array(cross_cosines)
        print(f"\n跨事件随机对 {len(cross_cosines)} 个:")
        print(f"  均值={arr_cross.mean():.4f}  中位数={np.median(arr_cross):.4f}")
        for p in [5, 10, 25, 50, 75, 90, 95]:
            print(f"  P{p}={np.percentile(arr_cross, p):.4f}")

    db.close()

if __name__ == "__main__":
    main()

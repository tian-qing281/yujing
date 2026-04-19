"""诊断特定事件的聚类质量：分析每篇文章与代表文章的cosine"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from app.database import SessionLocal, Article, Event, EventArticle, ArticleEmbedding
from app.services.embedding import EMBED_MODEL_NAME, bytes_to_vector

def main():
    db = SessionLocal()
    # 找到这个事件
    event = db.query(Event).filter(Event.title.like("%摊主%借%手机%")).first()
    if not event:
        # 模糊搜索
        events = db.query(Event).filter(Event.title.like("%摊主%")).all()
        if events:
            event = events[0]
        else:
            print("未找到相关事件")
            return

    print(f"事件ID: {event.id}")
    print(f"事件标题: {event.title}")
    print(f"文章数: {event.article_count}")
    print(f"代表文章ID: {event.representative_article_id}")
    print("="*80)

    # 获取事件下所有文章
    eas = db.query(EventArticle).filter(EventArticle.event_id == event.id).all()
    article_ids = [ea.article_id for ea in eas]
    ea_map = {ea.article_id: ea for ea in eas}

    articles = db.query(Article).filter(Article.id.in_(article_ids)).all()
    art_map = {a.id: a for a in articles}

    # 获取代表文章的向量
    rep_id = event.representative_article_id
    rep_emb = db.query(ArticleEmbedding).filter(
        ArticleEmbedding.article_id == rep_id,
        ArticleEmbedding.model_name == EMBED_MODEL_NAME,
    ).first()

    if not rep_emb:
        print("代表文章无向量")
        return

    rep_vec = bytes_to_vector(rep_emb.vector, rep_emb.dim)
    rep_art = art_map.get(rep_id)
    print(f"代表文章: [{rep_art.source_id}] {rep_art.title}")
    print("="*80)

    # 获取所有文章的向量并计算与代表的cosine
    emb_rows = db.query(ArticleEmbedding).filter(
        ArticleEmbedding.article_id.in_(article_ids),
        ArticleEmbedding.model_name == EMBED_MODEL_NAME,
    ).all()
    emb_map = {r.article_id: bytes_to_vector(r.vector, r.dim) for r in emb_rows}

    results = []
    for aid in article_ids:
        art = art_map.get(aid)
        ea = ea_map.get(aid)
        if not art:
            continue
        vec = emb_map.get(aid)
        if vec is not None:
            cos = float(np.dot(rep_vec, vec))
        else:
            cos = None
        results.append({
            "id": aid,
            "title": art.title,
            "source": art.source_id,
            "cosine_vs_rep": cos,
            "relation_score": ea.relation_score if ea else None,
            "is_primary": ea.is_primary if ea else False,
        })

    # 按cosine排序
    results.sort(key=lambda x: x["cosine_vs_rep"] if x["cosine_vs_rep"] is not None else -1, reverse=True)

    print(f"\n{'cosine':>7} | {'relation':>8} | {'source':<16} | title")
    print("-"*100)
    for r in results:
        cos_str = f"{r['cosine_vs_rep']:.4f}" if r['cosine_vs_rep'] is not None else "  N/A "
        rel_str = f"{r['relation_score']:.4f}" if r['relation_score'] is not None else "  N/A "
        marker = " ★" if r['is_primary'] else ""
        print(f"{cos_str:>7} | {rel_str:>8} | {r['source']:<16} | {r['title'][:60]}{marker}")

    # 统计
    cosines = [r["cosine_vs_rep"] for r in results if r["cosine_vs_rep"] is not None]
    if cosines:
        arr = np.array(cosines)
        print(f"\n--- 统计 ---")
        print(f"文章数: {len(results)}, 有向量: {len(cosines)}")
        print(f"cosine 均值: {arr.mean():.4f}, 中位数: {np.median(arr):.4f}")
        print(f"cosine 最小: {arr.min():.4f}, 最大: {arr.max():.4f}")
        print(f"cosine < 0.5: {(arr < 0.5).sum()} 篇")
        print(f"cosine < 0.6: {(arr < 0.6).sum()} 篇")
        print(f"cosine < 0.7: {(arr < 0.7).sum()} 篇")

    db.close()

if __name__ == "__main__":
    main()

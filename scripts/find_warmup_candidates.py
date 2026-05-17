"""找出文章数最多、时间跨度最长的事件 top20，作为 ABSA 预热候选。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, Event, Article, EventArticle
from sqlalchemy import func

db = SessionLocal()
try:
    # 每个事件：文章数 + 最早/最晚 pub_date
    rows = (
        db.query(
            Event.id,
            Event.title,
            func.count(EventArticle.article_id).label("art_cnt"),
            func.min(Article.pub_date).label("t_min"),
            func.max(Article.pub_date).label("t_max"),
        )
        .join(EventArticle, EventArticle.event_id == Event.id)
        .join(Article, Article.id == EventArticle.article_id)
        .group_by(Event.id)
        .having(func.count(EventArticle.article_id) >= 5)
        .all()
    )

    cands = []
    for r in rows:
        if not r.t_min or not r.t_max:
            continue
        span_h = (r.t_max - r.t_min).total_seconds() / 3600
        if span_h < 6:  # 至少跨 6 小时，否则单桶
            continue
        # 综合分：文章数 × log(跨度)
        score = r.art_cnt * (1 + span_h / 24)
        cands.append({
            "id": r.id,
            "title": (r.title or "")[:40],
            "articles": r.art_cnt,
            "span_h": round(span_h, 1),
            "buckets_12h": int(span_h // 12) + 1,
            "score": round(score, 1),
        })

    cands.sort(key=lambda x: x["score"], reverse=True)
    print(f"满足条件的事件: {len(cands)} 个 (>=5 篇文章 且 时间跨度 >=6h)")
    print(f"\n{'rank':<5}{'eid':<7}{'arts':<6}{'span_h':<8}{'12hbkt':<8}{'score':<8}title")
    print("-" * 110)
    for i, c in enumerate(cands[:20], 1):
        print(f"{i:<5}{c['id']:<7}{c['articles']:<6}{c['span_h']:<8}{c['buckets_12h']:<8}{c['score']:<8}{c['title']}")
finally:
    db.close()

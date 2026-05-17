"""直接查 DB 扫描所有事件 ABSA 起伏度。绕过 API 不依赖后端进程。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datetime import datetime
from collections import defaultdict, Counter

from app.database import SessionLocal, Event, Article, EventArticle
from app.services import absa as absa_service

POLARITY = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
BUCKET_HOURS = 12
TOP_K = 5


def score_event(db, event_id: int):
    arts = (
        db.query(Article)
        .join(EventArticle, EventArticle.article_id == Article.id)
        .filter(EventArticle.event_id == event_id)
        .all()
    )
    if not arts:
        return None

    per_article = []
    for a in arts:
        title = a.title or ""
        content = a.content or ""
        key = absa_service._cache_key(title, content)
        data = absa_service._cache_load(key)
        if not data:
            continue
        t = a.pub_date or a.fetch_time
        if not t:
            continue
        aspects = [(d.get("aspect"), d.get("sentiment", "neutral")) for d in data if d.get("aspect")]
        if aspects:
            per_article.append((t, aspects))

    if not per_article:
        return None

    aspect_counter = Counter()
    for _, aspects in per_article:
        for asp, _ in aspects:
            aspect_counter[asp] += 1
    top_aspects = [a for a, _ in aspect_counter.most_common(TOP_K)]

    times = [t for t, _ in per_article]
    t_min, t_max = min(times), max(times)
    span_h = (t_max - t_min).total_seconds() / 3600
    bucket_count = max(1, int(span_h // BUCKET_HOURS) + 1)
    epoch = datetime(1970, 1, 1)
    base_h = int((t_min - epoch).total_seconds() // 3600)
    base_h = (base_h // BUCKET_HOURS) * BUCKET_HOURS

    buckets_data = [defaultdict(list) for _ in range(bucket_count)]
    for t, aspects in per_article:
        h = int((t - epoch).total_seconds() // 3600)
        idx = (h - base_h) // BUCKET_HOURS
        if 0 <= idx < bucket_count:
            for asp, sent in aspects:
                if asp in top_aspects:
                    buckets_data[idx][asp].append(POLARITY.get(sent, 0.0))

    variance_sum = 0.0
    has_pos = False
    has_neg = False
    non_null_pts = 0
    series_dump = {}
    for asp in top_aspects:
        series = []
        for i in range(bucket_count):
            vals = buckets_data[i].get(asp, [])
            if vals:
                avg = sum(vals) / len(vals)
                series.append(round(avg, 3))
                non_null_pts += 1
                if avg > 0.1:
                    has_pos = True
                if avg < -0.1:
                    has_neg = True
            else:
                series.append(None)
        series_dump[asp] = series
        non_null = [v for v in series if v is not None]
        if non_null:
            variance_sum += max(non_null) - min(non_null)

    sign_diversity = int(has_pos) + int(has_neg)
    score = (
        variance_sum * 10
        + sign_diversity * 5
        + bucket_count * 0.5
        + len(top_aspects) * 0.3
        + len(per_article) * 0.2
    )

    return {
        "event_id": event_id,
        "score": round(score, 2),
        "aspects": len(top_aspects),
        "buckets": bucket_count,
        "covered_articles": len(per_article),
        "total_articles": len(arts),
        "variance_sum": round(variance_sum, 2),
        "sign_diversity": sign_diversity,
        "non_null_points": non_null_pts,
        "aspect_names": top_aspects[:3],
        "series_sample": {k: v for k, v in list(series_dump.items())[:3]},
    }


def main():
    db = SessionLocal()
    try:
        event_ids = [e.id for e in db.query(Event.id).all()]
        print(f"共 {len(event_ids)} 个事件，开始扫描 (直查 DB)...")
        results = []
        for i, eid in enumerate(event_ids, 1):
            try:
                r = score_event(db, eid)
                if r:
                    results.append(r)
            except Exception as e:
                print(f"  事件 {eid} 失败: {e}")
            if i % 100 == 0:
                print(f"  进度 {i}/{len(event_ids)} (已找到 {len(results)} 个有 ABSA)")

        results.sort(key=lambda x: x["score"], reverse=True)
        print(f"\n=== 有 ABSA 数据的事件: {len(results)} 个 ===\n")
        header = f"{'rank':<5}{'eid':<6}{'score':<8}{'asp':<5}{'bkt':<5}{'cov/tot':<10}{'var':<7}{'sign':<6}aspects"
        print(header)
        print("-" * 110)
        for i, r in enumerate(results[:20], 1):
            print(
                f"{i:<5}{r['event_id']:<6}{r['score']:<8}{r['aspects']:<5}{r['buckets']:<5}"
                f"{r['covered_articles']}/{r['total_articles']:<7}{r['variance_sum']:<7}{r['sign_diversity']:<6}"
                f"{', '.join(r['aspect_names'] or [])}"
            )

        if results:
            print("\n=== 最佳候选 top3 完整 series ===")
            for r in results[:3]:
                print(f"\nevent_id={r['event_id']} score={r['score']} buckets={r['buckets']}")
                for asp, s in r["series_sample"].items():
                    print(f"  {asp}: {s}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

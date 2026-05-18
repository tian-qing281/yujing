"""一键回填：对指定事件下空正文文章批量抓取二级页正文，再顺手 warm ABSA。

用法：
    python scripts/enrich_articles_for_event.py <event_id> [--limit 30] [--min-len 60] [--skip-absa]

执行步骤：
    1. 找出该事件下 content 为空 / 过短的文章
    2. 串行调 extract_article_content(url) 抓正文（与前端「点击文章卡片」完全一致）
    3. 回写 Article.content（清空陈旧 ai_summary / ai_sentiment）
    4. 默认追加调用 absa_service.extract_aspects 生成 ABSA 缓存（--skip-absa 跳过）
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, Article, EventArticle  # noqa: E402
from app.crawler.reader import extract_article_content  # noqa: E402
from app.services import absa as absa_service  # noqa: E402


def _is_short(content: str | None, threshold: int) -> bool:
    if not content:
        return True
    return len(content.strip()) < threshold


async def run(event_id: int, limit: int, min_len: int, skip_absa: bool) -> int:
    db = SessionLocal()
    try:
        rows = db.query(EventArticle).filter(EventArticle.event_id == event_id).all()
        article_ids = [r.article_id for r in rows]
        if not article_ids:
            print(f"事件 {event_id} 下无文章")
            return 1

        articles = db.query(Article).filter(Article.id.in_(article_ids)).all()
        targets = [a for a in articles if _is_short(a.content, min_len) and a.url]
        targets = targets[:limit]
        print(f"事件 {event_id} 共 {len(articles)} 篇，需要补抓正文 {len(targets)} 篇")
        if not targets:
            print("无需 enrich")
        else:
            ok = skip = fail = 0
            for i, art in enumerate(targets, 1):
                t0 = time.time()
                try:
                    content = await extract_article_content(art.url)
                except Exception as exc:  # noqa: BLE001
                    fail += 1
                    print(f"  [{i}/{len(targets)}] #{art.id} 抓取异常 {exc} ({time.time()-t0:.1f}s)")
                    continue
                if not content or (isinstance(content, str) and content.startswith(("❌", "🎬"))):
                    skip += 1
                    flag = (content or "")[:6]
                    print(f"  [{i}/{len(targets)}] #{art.id} 返回无效 {flag!r} ({time.time()-t0:.1f}s)")
                    continue
                if len(content.strip()) < min_len:
                    skip += 1
                    print(f"  [{i}/{len(targets)}] #{art.id} 正文太短 len={len(content.strip())} ({time.time()-t0:.1f}s)")
                    continue
                art.content = content
                art.ai_summary = ""
                art.ai_sentiment = None
                db.commit()
                ok += 1
                print(f"  [{i}/{len(targets)}] #{art.id} 已回填 len={len(content)} ({time.time()-t0:.1f}s)")
            print(f"\n正文 enrich：成功 {ok} / 跳过 {skip} / 失败 {fail}")

        if skip_absa:
            return 0

        # 重新查一次（含刚回填的）走 ABSA
        articles = db.query(Article).filter(Article.id.in_(article_ids)).all()
        absa_targets = [a for a in articles if a.content and len(a.content.strip()) >= min_len]
        print(f"\nABSA 阶段：{len(absa_targets)} 篇可处理")
        hits = news = fails = 0
        for i, art in enumerate(absa_targets, 1):
            key = absa_service._cache_key(art.title or "", art.content or "")
            if absa_service._cache_load(key):
                hits += 1
                print(f"  [{i}/{len(absa_targets)}] #{art.id} 缓存命中")
                continue
            t0 = time.time()
            try:
                aspects = absa_service.extract_aspects(art.title or "", art.content or "")
                if aspects:
                    news += 1
                    print(f"  [{i}/{len(absa_targets)}] #{art.id} 新抽取 {len(aspects)} 个 aspect ({time.time()-t0:.1f}s)")
                else:
                    fails += 1
                    print(f"  [{i}/{len(absa_targets)}] #{art.id} LLM 返回空 ({time.time()-t0:.1f}s)")
            except Exception as exc:  # noqa: BLE001
                fails += 1
                print(f"  [{i}/{len(absa_targets)}] #{art.id} 失败 {exc}")
        print(f"\nABSA 完成：缓存命中 {hits} / 新抽取 {news} / 失败 {fails}")
        return 0
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_id", type=int)
    parser.add_argument("--limit", type=int, default=30, help="最多 enrich 多少篇")
    parser.add_argument("--min-len", type=int, default=60, help="正文长度下限")
    parser.add_argument("--skip-absa", action="store_true", help="只补正文不跑 ABSA")
    args = parser.parse_args()
    return asyncio.run(run(args.event_id, args.limit, args.min_len, args.skip_absa))


if __name__ == "__main__":
    raise SystemExit(main())

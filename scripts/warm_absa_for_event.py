"""F6 预热脚本：批量为指定事件下的文章触发 ABSA 抽取并写入文件缓存。

用法：
    python scripts/warm_absa_for_event.py <event_id> [--limit 30]

设计：
    - 调用 app.services.absa.extract_aspects（自带缓存命中短路）
    - 仅对正文 ≥ 60 字的文章生效
    - 顺序串行（避免触发 LLM 速率限制），打印进度

仅用于答辩演示前预生成；线上正常使用通过文章详情页『AI 分析』按钮按需触发。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 把项目根加入 sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, Article, EventArticle  # noqa: E402
from app.services import absa as absa_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_id", type=int)
    parser.add_argument("--limit", type=int, default=30, help="最多处理多少篇文章")
    parser.add_argument("--min-content", type=int, default=60, help="正文长度下限")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        link_rows = db.query(EventArticle).filter(EventArticle.event_id == args.event_id).all()
        article_ids = [r.article_id for r in link_rows]
        if not article_ids:
            print(f"事件 {args.event_id} 下无文章")
            return 1

        articles = db.query(Article).filter(Article.id.in_(article_ids)).all()
        articles = [a for a in articles if a.content and len(a.content.strip()) >= args.min_content]
        articles = articles[: args.limit]
        print(f"准备处理事件 {args.event_id} 下 {len(articles)} 篇文章")

        hits, news, fails = 0, 0, 0
        for i, art in enumerate(articles, 1):
            key = absa_service._cache_key(art.title or "", art.content or "")
            cached = absa_service._cache_load(key)
            if cached:
                hits += 1
                print(f"  [{i}/{len(articles)}] #{art.id} 缓存命中 ({len(cached)} 个 aspect)")
                continue
            t0 = time.time()
            try:
                aspects = absa_service.extract_aspects(art.title or "", art.content or "")
                dt = time.time() - t0
                if aspects:
                    news += 1
                    print(f"  [{i}/{len(articles)}] #{art.id} 新抽取 {len(aspects)} 个 aspect (耗时 {dt:.1f}s)")
                else:
                    fails += 1
                    print(f"  [{i}/{len(articles)}] #{art.id} LLM 返回空 (耗时 {dt:.1f}s)")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"  [{i}/{len(articles)}] #{art.id} 失败：{e}")

        print(f"\n完成：缓存命中 {hits} / 新抽取 {news} / 失败 {fails}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

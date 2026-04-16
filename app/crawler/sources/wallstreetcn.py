from datetime import datetime

from app.crawler.sources.base import BaseSource


class WallstreetcnNews(BaseSource):
    source_id = "wallstreetcn_news"
    interval_seconds = 180
    default_item_limit = 30
    fetch_detail_content = True

    async def fetch(self):
        client = self.get_client(timeout=12.0, follow_redirects=True)
        headers = {"User-Agent": "Mozilla/5.0"}
        rows = []
        seen = set()

        def add_resource(resource: dict, source_label: str = "华尔街见闻热榜"):
            target_url = str(resource.get("uri", "")).strip()
            title = str(resource.get("title") or resource.get("content_short") or "").strip()
            article_id = resource.get("id")
            if not title or not target_url or not article_id:
                return
            if "/articles/" not in target_url:
                return
            if article_id in seen:
                return
            seen.add(article_id)
            rank = len(rows) + 1
            display_time = resource.get("display_time") or resource.get("created_at") or None
            extra = {
                "hot_source": source_label,
                "article_id": article_id,
            }
            if "热榜" in source_label:
                extra["hot_metric"] = f"{source_label}第 {rank} 位"
            rows.append(
                {
                    "item_id": f"wallstreetcn_{article_id}",
                    "rank": rank,
                    "title": title,
                    "url": target_url,
                    "pub_date": datetime.fromtimestamp(display_time) if display_time else datetime.now(),
                    "extra": extra,
                }
            )

        hot_url = "https://api-one.wallstcn.com/apiv1/content/articles/hot?period=all"
        hot_response = await client.get(hot_url, headers=headers)
        hot_response.raise_for_status()
        hot_data = hot_response.json()
        for resource in hot_data.get("data", {}).get("day_items", []):
            if len(rows) >= self.get_item_limit():
                break
            add_resource(resource or {}, "华尔街见闻热榜")

        if len(rows) < self.get_item_limit():
            print(
                f"[热榜不足] 华尔街见闻热榜接口返回 {len(rows)} 条文章，"
                "不使用资讯流补足，避免把普通资讯误标为热点。"
            )

        return rows[: self.get_item_limit()]

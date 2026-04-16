from datetime import datetime

import httpx

from app.crawler.sources.base import BaseSource


class ThePaperHotNews(BaseSource):
    source_id = "thepaper_hot"
    interval_seconds = 300
    default_item_limit = 30
    fetch_detail_content = True

    async def fetch(self):
        url = "https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar"
        async with httpx.AsyncClient(
            timeout=12.0,
            follow_redirects=True,
            verify=False,
            http2=False,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        result = []
        now = datetime.now()
        item_limit = self.get_item_limit()
        for index, item in enumerate(data.get("data", {}).get("hotNews", [])[:item_limit], start=1):
            content_id = str(item.get("contId", "")).strip()
            title = str(item.get("name", "")).strip()
            if not content_id or not title:
                continue
            result.append(
                {
                    "item_id": f"thepaper_{content_id}",
                    "rank": index,
                    "title": title,
                    "url": f"https://www.thepaper.cn/newsDetail_forward_{content_id}",
                    "pub_date": now,
                    "extra": {
                        "hot_source": "澎湃热榜",
                        "hot_metric": f"热榜第 {index} 位",
                        "pub_time": item.get("pubTimeLong", ""),
                        "mobile_url": f"https://m.thepaper.cn/newsDetail_forward_{content_id}",
                    },
                }
            )
        return result

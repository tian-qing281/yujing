from datetime import datetime

from app.crawler.sources.base import BaseSource


class ToutiaoHotBoard(BaseSource):
    source_id = "toutiao_hot"
    interval_seconds = 120
    default_item_limit = 30

    async def fetch(self):
        url = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        client = self.get_client(timeout=10.0)
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        result = []
        limit = self.get_item_limit()
        for item in data.get("data", [])[:limit]:
            cluster_id = item.get("ClusterIdStr", "")
            result.append({
                "item_id": f"toutiao_{cluster_id}",
                "title": item.get("Title", ""),
                "url": f"https://www.toutiao.com/trending/{cluster_id}/",
                "pub_date": datetime.now(),
                "extra": {
                    "hot_value": item.get("HotValue", ""),
                },
            })
        return result

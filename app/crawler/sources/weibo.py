from datetime import datetime
from app.crawler.sources.base import BaseSource

class WeiboHotSearch(BaseSource):
    source_id = "weibo_hot_search"
    interval_seconds = 120 # 2分钟刷一次，平衡实时与性能
    default_item_limit = 30

    async def fetch(self):
        url = "https://weibo.com/ajax/side/hotSearch"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://s.weibo.com/"
        }
        cookie = self.get_credential()
        if cookie:
            headers["Cookie"] = cookie
        
        client = self.get_client(timeout=10.0)
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        result = []
        limit = self.get_item_limit()
        raw_items = data.get("data", {}).get("realtime", [])[:limit]
        for idx, item in enumerate(raw_items):
            if "word" in item:
                title = item["word"]
                item_id = str(item.get("mid", title)) # 微博有些热搜没有mid，用word做兜底
                result.append({
                    "item_id": f"weibo_{item_id}",
                    "rank": idx + 1, # 1-indexed rank
                    "title": title,
                    "url": f"https://s.weibo.com/weibo?q=%23{title}%23",
                    "pub_date": datetime.now(),
                    "extra": {
                        "hot_value": item.get("num", 0),
                        "category": item.get("category", "综合")
                    }
                })
        return result

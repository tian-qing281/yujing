import json
import re
from datetime import datetime

from app.crawler.sources.base import BaseSource


class BaiduHotSearch(BaseSource):
    source_id = "baidu_hot"
    interval_seconds = 120
    default_item_limit = 30

    async def fetch(self):
        url = "https://top.baidu.com/board?tab=realtime"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        client = self.get_client(timeout=10.0)
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: 百度拒绝了访问请求")
        html = response.text

        match = re.search(r"<!--s-data:(.*?)-->", html, re.DOTALL)
        if not match:
            raise Exception("未能解析到页面数据特征码")

        try:
            data = json.loads(match.group(1))
            items = data.get("data", {}).get("cards", [{}])[0].get("content", [])
        except Exception as exc:
            raise Exception(f"JSON 解析失败: {str(exc)}")

        result = []
        limit = self.get_item_limit()
        for item in items:
            if item.get("isTop"):
                continue
            word = item.get("word", "")
            result.append({
                "item_id": f"baidu_{word}",
                "title": word,
                "url": item.get("rawUrl", f"https://www.baidu.com/s?wd={word}"),
                "pub_date": datetime.now(),
                "extra": {
                    "desc": item.get("desc", ""),
                    "hot_score": item.get("hotScore", ""),
                },
            })
            if len(result) >= limit:
                break
        return result

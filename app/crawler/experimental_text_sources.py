import json
import re
from datetime import datetime

import httpx

from app.crawler.sources.base import BaseSource


class ThePaperHotNews(BaseSource):
    source_id = "thepaper_hot"
    interval_seconds = 300
    default_item_limit = 20

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
        for item in data.get("data", {}).get("hotNews", [])[: self.get_item_limit()]:
            content_id = str(item.get("contId", "")).strip()
            title = str(item.get("name", "")).strip()
            if not content_id or not title:
                continue
            result.append(
                {
                    "item_id": f"thepaper_{content_id}",
                    "title": title,
                    "url": f"https://www.thepaper.cn/newsDetail_forward_{content_id}",
                    "pub_date": now,
                    "extra": {
                        "hot_source": "澎湃热点",
                        "pub_time": item.get("pubTimeLong", ""),
                        "mobile_url": f"https://m.thepaper.cn/newsDetail_forward_{content_id}",
                    },
                }
            )
        return result


class IfengHotNews(BaseSource):
    source_id = "ifeng_hot"
    interval_seconds = 300
    default_item_limit = 20

    async def fetch(self):
        async with httpx.AsyncClient(
            timeout=12.0,
            follow_redirects=True,
            verify=False,
            http2=False,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as client:
            response = await client.get("https://www.ifeng.com/")
            response.raise_for_status()
            html = response.text

        match = re.search(r"var\s+allData\s*=\s*(\{[\s\S]*?\});", html)
        if not match:
            raise RuntimeError("未解析到凤凰热点数据")

        raw = json.loads(match.group(1))
        hot_news = raw.get("hotNews1", [])
        now = datetime.now()
        result = []
        for item in hot_news[: self.get_item_limit()]:
            title = str(item.get("title", "")).strip()
            target_url = str(item.get("url", "")).strip()
            if not title or not target_url:
                continue
            result.append(
                {
                    "item_id": f"ifeng_{target_url}",
                    "title": title,
                    "url": target_url,
                    "pub_date": now,
                    "extra": {
                        "hot_source": "凤凰热点",
                        "news_time": item.get("newsTime", ""),
                    },
                }
            )
        return result


class WallstreetcnNews(BaseSource):
    source_id = "wallstreetcn_news"
    interval_seconds = 180
    default_item_limit = 20

    async def fetch(self):
        api_url = "https://api-one.wallstcn.com/apiv1/content/information-flow?channel=global-channel&accept=article&limit=30"
        client = self.get_client(timeout=12.0, follow_redirects=True)
        response = await client.get(api_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        data = response.json()

        result = []
        for wrapper in data.get("data", {}).get("items", [])[: self.get_item_limit()]:
            if wrapper.get("resource_type") in {"theme", "ad"}:
                continue
            resource = wrapper.get("resource") or {}
            if resource.get("type") == "live":
                continue
            target_url = str(resource.get("uri", "")).strip()
            title = str(resource.get("title") or resource.get("content_short") or "").strip()
            article_id = resource.get("id")
            if not title or not target_url or not article_id:
                continue
            result.append(
                {
                    "item_id": f"wallstreetcn_{article_id}",
                    "title": title,
                    "url": target_url,
                    "pub_date": datetime.fromtimestamp((resource.get("display_time") or 0)),
                    "extra": {
                        "hot_source": "华尔街见闻",
                        "article_id": article_id,
                    },
                }
            )
        return result


class ClsTelegraph(BaseSource):
    source_id = "cls_telegraph"
    interval_seconds = 180
    default_item_limit = 20

    async def fetch(self):
        api_url = "https://www.cls.cn/nodeapi/updateTelegraphList"
        client = self.get_client(timeout=12.0, follow_redirects=True)
        response = await client.get(api_url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        data = response.json()

        result = []
        for item in data.get("data", {}).get("roll_data", [])[: self.get_item_limit()]:
            if item.get("is_ad"):
                continue
            item_id = item.get("id")
            title = str(item.get("title") or item.get("brief") or "").strip()
            if not item_id or not title:
                continue
            result.append(
                {
                    "item_id": f"cls_{item_id}",
                    "title": title,
                    "url": f"https://www.cls.cn/detail/{item_id}",
                    "pub_date": datetime.fromtimestamp((item.get("ctime") or 0)),
                    "extra": {"hot_source": "财联社电报"},
                }
            )
        return result


EXPERIMENTAL_TEXT_SOURCES = [
    ThePaperHotNews(),
    IfengHotNews(),
    WallstreetcnNews(),
    ClsTelegraph(),
]

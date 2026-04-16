import asyncio
from datetime import datetime

from app.crawler.sources.base import BaseSource


class BilibiliHotVideo(BaseSource):
    source_id = "bilibili_hot_video"
    interval_seconds = 120
    default_item_limit = 30

    async def fetch(self):
        limit = self.get_item_limit()
        page_size = min(max(limit, 1), 50)
        url1 = f"https://api.bilibili.com/x/web-interface/popular?pn=1&ps={page_size}"
        url2 = f"https://api.bilibili.com/x/web-interface/popular?pn=2&ps={page_size}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        client = self.get_client(timeout=10.0)
        res1, res2 = await asyncio.gather(
            client.get(url1, headers=headers),
            client.get(url2, headers=headers),
            return_exceptions=True,
        )
        list1 = []
        list2 = []
        if not isinstance(res1, Exception) and res1.status_code == 200:
            list1 = res1.json().get("data", {}).get("list", [])
        if not isinstance(res2, Exception) and res2.status_code == 200:
            list2 = res2.json().get("data", {}).get("list", [])
        if not list1 and not list2:
            raise Exception("B站两页热门视频均请求失败")

        seen_bv = set()
        all_videos = []
        for video in list1 + list2:
            bvid = video.get("bvid")
            if bvid and bvid not in seen_bv:
                seen_bv.add(bvid)
                all_videos.append(video)
            if len(all_videos) >= limit:
                break

        result = []
        for video in all_videos:
            result.append({
                "item_id": video["bvid"],
                "title": video["title"],
                "url": f"https://www.bilibili.com/video/{video['bvid']}",
                "pub_date": datetime.now(),
                "extra": {
                    "author": video["owner"]["name"],
                    "view": video["stat"]["view"],
                    "like": video["stat"]["like"],
                    "desc": video["desc"],
                },
            })
        return result

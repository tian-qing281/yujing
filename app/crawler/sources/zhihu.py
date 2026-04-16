from datetime import datetime

from app.crawler.sources.base import BaseSource


class ZhihuHotQuestion(BaseSource):
    source_id = "zhihu_hot_question"
    interval_seconds = 120
    default_item_limit = 30

    async def fetch(self):
        limit = min(self.get_item_limit(), 50)
        url = f"https://www.zhihu.com/api/v3/feed/topstory/hot-list-web?limit={limit}&desktop=true"
        cookie = self.get_credential()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Referer": "https://www.zhihu.com/hot",
            "Accept": "application/json, text/plain, */*",
        }
        if cookie:
            headers["Cookie"] = cookie

        client = self.get_client(timeout=10.0, follow_redirects=True)
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        result = []
        now = datetime.now()
        for item in data.get("data", [])[:limit]:
            target = item.get("target", {})
            title_area = target.get("title_area", {})
            link = target.get("link", {})
            metrics_area = target.get("metrics_area", {})
            metrics_text = metrics_area.get("text", "")
            browse_count = (
                target.get("read_count")
                or target.get("visit_count")
                or target.get("browse_count")
                or item.get("read_count")
                or item.get("visit_count")
            )

            question_url = link.get("url", "")
            title = title_area.get("text", "")
            if not title or not question_url:
                continue
            question_url_clean = question_url.split("?")[0]
            question_id = question_url_clean.split("/")[-1] if "/" in question_url_clean else title

            result.append({
                "item_id": f"zhihu_{question_id}",
                "title": title,
                "url": question_url,
                "pub_date": now,
                "extra": {
                    "hot_metric": metrics_text or (f"{browse_count} 浏览" if browse_count else ""),
                    "view_count": browse_count,
                    "excerpt": target.get("excerpt_area", {}).get("text", ""),
                },
            })
        return result

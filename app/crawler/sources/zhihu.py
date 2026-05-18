from datetime import datetime

import httpx

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
        # 友好降级：知乎 Cookie 失效 / 未登录时返回 401/403，
        # 不再抩异常造成后端日志震荡，而是打印明确提示 + 返回空列表，
        # 由上层 base.run_and_save 走「热榜不足」路径，不影响其他平台。
        if response.status_code in (401, 403):
            print(
                f"[凭据失效] 知乎热榜返回 HTTP {response.status_code}："
                "Cookie 已失效或未登录，请在「Cookie 配置」中更新 zhihu_hot_question 的 Cookie。"
            )
            return []
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            print(f"[知乎热榜] HTTP {exc.response.status_code}，跳过本轮拓取。")
            return []
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

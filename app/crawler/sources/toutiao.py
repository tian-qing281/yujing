import asyncio
import re
from datetime import datetime

from app.crawler.sources.base import BaseSource


class ToutiaoHotBoard(BaseSource):
    source_id = "toutiao_hot"
    interval_seconds = 120
    default_item_limit = 30
    # 并发探测 trending 页时的最大并发数（避免触发头条反爬）
    _probe_concurrency = 4
    # 单个 trending 页探测超时（秒）
    _probe_timeout = 8.0

    async def fetch(self):
        url = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        client = self.get_client(timeout=10.0)
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # 先整理出候选列表（保留 API 原 URL 以便后续判定类型）
        raw_items = []
        limit = self.get_item_limit()
        # 为给视频过滤留出余量，先取 API 返回的前 limit + 20 条候选
        for item in data.get("data", [])[: limit + 20]:
            cluster_id = item.get("ClusterIdStr", "")
            title = item.get("Title", "")
            api_url = item.get("Url", "") or f"https://www.toutiao.com/trending/{cluster_id}/"
            # Url 里会带很长的 log_pb query string，归一化为干净的 trending/article URL
            clean_url = self._normalize_toutiao_url(api_url, cluster_id)
            raw_items.append({
                "item_id": f"toutiao_{cluster_id}",
                "title": title,
                "url": clean_url,
                "pub_date": datetime.now(),
                "extra": {
                    "hot_value": item.get("HotValue", ""),
                    "cluster_type": item.get("ClusterType"),
                    "api_url": api_url,
                },
            })

        # 对 trending 类型的条目，并发探测 HTML 判断是否纯视频事件
        filtered = await self._filter_video_items(raw_items)
        return filtered[:limit]

    @staticmethod
    def _normalize_toutiao_url(api_url: str, cluster_id: str) -> str:
        """剥离 toutiao Url 里的 log_pb query string，保留 /article/ 或 /trending/ 主体。"""
        m = re.search(r"(https?://www\.toutiao\.com/(?:article|trending|video|w)/\d+)", api_url)
        if m:
            return m.group(1) + "/"
        return f"https://www.toutiao.com/trending/{cluster_id}/"

    async def _filter_video_items(self, items: list) -> list:
        """对 trending 类型的 item 并发探测其内容类型，过滤纯视频事件。

        判定逻辑：
        - URL 本身是 /article/ → 图文，保留
        - URL 是 /trending/ → 拉带 cookie 的 HTML，统计 /article/ /video/ /w/ 链接
          - 有 /article/ 或 /w/ → 保留（可正常分析）
          - 只有 /video/（article=0 且 w=0 且 video>0）→ 丢弃（视频事件）
          - 探测失败（网络错误/反爬/无 cookie）→ 保留（宁错放不误杀）
        """
        from app.crawler.reader import _fetch_toutiao_html_direct

        sem = asyncio.Semaphore(self._probe_concurrency)

        async def classify(item: dict) -> tuple[dict, str]:
            url = item["url"]
            if "/article/" in url:
                return item, "article"
            # trending：探测 HTML
            async with sem:
                try:
                    html = await asyncio.wait_for(
                        _fetch_toutiao_html_direct(url, timeout=self._probe_timeout),
                        timeout=self._probe_timeout + 2,
                    )
                except (asyncio.TimeoutError, Exception):
                    return item, "probe_fail"
            if not html:
                return item, "probe_fail"
            has_article = bool(re.search(r"/article/\d+", html))
            has_w = bool(re.search(r"/w/\d+", html))
            has_video = bool(re.search(r"/video/\d+", html))
            if has_article:
                return item, "article"
            if has_w:
                return item, "weitoutiao"
            if has_video:
                return item, "video_only"
            # 什么链接都没有（HTML 可能被反爬返回空）
            return item, "unknown"

        results = await asyncio.gather(*(classify(it) for it in items))

        kept, dropped = [], []
        for item, verdict in results:
            if verdict == "video_only":
                dropped.append(item["title"])
            else:
                kept.append(item)

        if dropped:
            print(
                f"[头条][视频过滤] 丢弃 {len(dropped)} 条纯视频事件: "
                + "; ".join(dropped[:5])
                + ("..." if len(dropped) > 5 else "")
            )
        return kept

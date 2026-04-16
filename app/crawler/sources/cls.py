import hashlib
from datetime import datetime
from urllib.parse import urlencode

from app.crawler.sources.base import BaseSource


def _cls_signed_params(extra: dict | None = None) -> dict:
    params = {
        "appName": "CailianpressWeb",
        "os": "web",
        "sv": "7.7.5",
    }
    if extra:
        params.update(extra)
    query = urlencode(sorted(params.items()))
    sha1_value = hashlib.sha1(query.encode("utf-8")).hexdigest()
    params["sign"] = hashlib.md5(sha1_value.encode("utf-8")).hexdigest()
    return params


class ClsTelegraph(BaseSource):
    source_id = "cls_telegraph"
    interval_seconds = 180
    default_item_limit = 30
    fetch_detail_content = True

    async def fetch(self):
        client = self.get_client(timeout=12.0, follow_redirects=True)
        headers = {"User-Agent": "Mozilla/5.0"}
        rows = []
        seen = set()

        def add_item(item: dict, source_label: str):
            item_id = item.get("id")
            title = str(item.get("title") or item.get("brief") or "").strip()
            if not item_id or not title or item.get("is_ad"):
                return
            if item_id in seen:
                return
            seen.add(item_id)
            rank = len(rows) + 1
            hot_value = (
                item.get("readNum")
                or item.get("reading_num")
                or item.get("readingNum")
                or item.get("read_num")
            )
            extra = {
                "hot_source": source_label,
                "excerpt": str(item.get("brief") or "").strip(),
            }
            if hot_value:
                extra["hot_value"] = hot_value
            if "热榜" in source_label:
                extra["hot_metric"] = f"{source_label}第 {rank} 位"
            rows.append(
                {
                    "item_id": f"cls_{item_id}",
                    "rank": rank,
                    "title": title,
                    "url": f"https://www.cls.cn/detail/{item_id}",
                    "pub_date": datetime.fromtimestamp(item["ctime"]) if item.get("ctime") else datetime.now(),
                    "extra": extra,
                }
            )

        hot_response = await client.get(
            "https://www.cls.cn/v2/article/hot/list",
            params=_cls_signed_params(),
            headers=headers,
        )
        hot_response.raise_for_status()
        for item in hot_response.json().get("data", []) or []:
            if len(rows) >= self.get_item_limit():
                break
            add_item(item or {}, "财联社热榜")

        if len(rows) < self.get_item_limit():
            print(
                f"[热榜不足] 财联社热榜接口返回 {len(rows)} 条文章，"
                "不使用深度/快讯补足，避免把普通资讯误标为热点。"
            )

        return rows[: self.get_item_limit()]

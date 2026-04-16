import asyncio
import json
import sys

import httpx
from bs4 import BeautifulSoup

from app.crawler.experimental_text_sources import EXPERIMENTAL_TEXT_SOURCES
from app.crawler.reader import extract_article_content


def _normalize_text_length(raw: str) -> int:
    if not raw:
        return 0
    if raw.startswith("JSON_STREAM_LIST:"):
        try:
            payload = json.loads(raw.split(":", 1)[1])
            return len(json.dumps(payload, ensure_ascii=False))
        except Exception:
            return len(raw)
    if raw.startswith("❌"):
        return 0
    return len(raw)


async def _extract_wallstreetcn_content(article_id) -> str:
    if not article_id:
        return ""
    url = f"https://api-one.wallstcn.com/apiv1/content/articles/{article_id}?extract=1"
    async with httpx.AsyncClient(
        timeout=20.0,
        follow_redirects=True,
        verify=False,
        http2=False,
        headers={"User-Agent": "Mozilla/5.0"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
    content_html = ((payload or {}).get("data") or {}).get("content") or ""
    if not content_html:
        return ""
    soup = BeautifulSoup(content_html, "html.parser")
    for node in soup(["script", "style", "img", "video", "svg"]):
        node.decompose()
    return soup.get_text(separator="\n", strip=True)[:6000]


async def _extract_sample_content(source, item) -> str:
    if source.source_id == "wallstreetcn_news":
        content = await _extract_wallstreetcn_content((item.get("extra") or {}).get("article_id"))
        if content:
            return content
    if source.source_id == "thepaper_hot":
        mobile_url = (item.get("extra") or {}).get("mobile_url")
        if mobile_url:
            content = await extract_article_content(mobile_url)
            if content and not content.startswith("❌"):
                return content
    return await extract_article_content(item.get("url"))


async def probe_source(source):
    result = {
        "source_id": source.source_id,
        "fetched": 0,
        "samples": [],
    }
    items = await source.fetch()
    result["fetched"] = len(items)
    for item in items[:3]:
        content = await _extract_sample_content(source, item)
        sample = {
            "title": item.get("title", ""),
            "url": item.get("url"),
            "status": "成功" if content and not content.startswith("❌") else "失败",
            "text_length": _normalize_text_length(content),
            "preview": (content or "")[:180].replace("\n", " "),
        }
        result["samples"].append(sample)
    return result


async def main():
    sys.stdout.reconfigure(encoding="utf-8")
    reports = []
    for source in EXPERIMENTAL_TEXT_SOURCES:
        try:
            reports.append(await probe_source(source))
        except Exception as exc:
            reports.append(
                {
                    "source_id": source.source_id,
                    "fetched": 0,
                    "error": str(exc),
                    "samples": [],
                }
            )
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

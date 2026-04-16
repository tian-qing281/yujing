"""
头条爬虫独立测试脚本
用法: python test_toutiao_crawler.py

测试流程:
1. 调用头条热榜 API 获取 trending 列表
2. 选取第一个 trending URL，通过 Jina 提取 markdown
3. 从 markdown 中提取 article 链接
4. 跟进 article 链接用 Jina 提取正文
5. 输出每个阶段的结果和耗时
"""

import asyncio
import re
import sys
import time

import httpx


# ── Jina 提取 ──────────────────────────────────────────────

def _build_jina_mirror_urls(target_url: str) -> list[str]:
    from urllib.parse import urlparse

    normalized = (target_url or "").strip()
    if not normalized:
        return []
    without_scheme = re.sub(r"^https?://", "", normalized, flags=re.IGNORECASE)
    candidates = [
        f"https://r.jina.ai/http://{normalized}",
        f"https://r.jina.ai/http://{without_scheme}",
    ]
    parsed = urlparse(normalized)
    if parsed.netloc.startswith("www."):
        trimmed_url = parsed._replace(netloc=parsed.netloc[4:]).geturl()
        trimmed_without_scheme = re.sub(r"^https?://", "", trimmed_url, flags=re.IGNORECASE)
        candidates.extend([
            f"https://r.jina.ai/http://{trimmed_url}",
            f"https://r.jina.ai/http://{trimmed_without_scheme}",
        ])
    seen = set()
    return [c for c in candidates if c and c not in seen and not seen.add(c)]


def extract_markdown_via_jina(target_url: str, timeout: float = 25.0) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/plain, text/markdown;q=0.9, */*;q=0.8",
    }
    with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout, verify=False) as client:
        for _ in range(2):
            for mirror_url in _build_jina_mirror_urls(target_url):
                try:
                    response = client.get(mirror_url)
                    response.raise_for_status()
                    text = response.text.strip()
                    if "Markdown Content:" in text:
                        text = text.split("Markdown Content:", 1)[1].strip()
                    if text:
                        return text
                except Exception as e:
                    print(f"  [Jina] 尝试 {mirror_url[:80]}... 失败: {e}")
    return ""


# ── 正文清洗 ───────────────────────────────────────────────

def clean_toutiao_article_markdown(markdown: str) -> str:
    if "Markdown Content:" in markdown:
        markdown = markdown.split("Markdown Content:", 1)[1].strip()
    first_heading = re.search(r"^#{1,3}\s+.+$", markdown, re.MULTILINE)
    if first_heading:
        markdown = markdown[first_heading.start():].strip()
    for tail in ["\n相关推荐", "\n热门评论", "\n延伸阅读", "\n更多内容", "\nTA的热门", "\n查看更多"]:
        if tail in markdown:
            markdown = markdown.split(tail, 1)[0].strip()
            break
    lines = []
    for line in markdown.splitlines():
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if "![Image" in s or "![image" in s:
            continue
        if s.startswith("*   ") and any(k in s for k in ["复制链接", "微信", "微博", "QQ空间", "分享"]):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


# ── 视频 URL 检测 ──────────────────────────────────────────

VIDEO_MARKERS = ("/video/", "video.toutiao.com")

def is_video_url(url: str) -> bool:
    lowered = (url or "").lower()
    return any(m in lowered for m in VIDEO_MARKERS)


# ── 主测试 ─────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("头条爬虫独立测试")
    print("=" * 60)

    # Step 1: 获取热榜
    print("\n[1/4] 获取头条热榜...")
    t0 = time.time()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        resp.raise_for_status()
        data = resp.json()

    items = data.get("data", [])[:5]
    print(f"  获取到 {len(items)} 条热榜 ({time.time() - t0:.1f}s)")
    for i, item in enumerate(items):
        cluster_id = item.get("ClusterIdStr", "")
        title = item.get("Title", "")
        print(f"  [{i+1}] {title}")
        print(f"      trending: https://www.toutiao.com/trending/{cluster_id}/")

    if not items:
        print("❌ 未获取到热榜数据")
        return

    # Step 2: Jina 提取 trending 页
    first = items[0]
    cluster_id = first.get("ClusterIdStr", "")
    trending_url = f"https://www.toutiao.com/trending/{cluster_id}/"
    title = first.get("Title", "")

    print(f"\n[2/4] Jina 提取 trending 页: {title}")
    print(f"  URL: {trending_url}")
    t1 = time.time()
    trending_md = await asyncio.to_thread(extract_markdown_via_jina, trending_url, 25.0)
    elapsed = time.time() - t1
    if trending_md:
        print(f"  ✅ 成功 ({elapsed:.1f}s)，markdown 长度: {len(trending_md)} 字符")
        print(f"  预览: {trending_md[:200]}...")
    else:
        print(f"  ❌ 失败 ({elapsed:.1f}s)，Jina 未返回内容")
        print("  测试终止: Jina 无法提取 trending 页面")
        return

    # Step 3: 从 trending markdown 提取 article 链接
    print(f"\n[3/4] 从 trending 页提取 article 链接...")
    article_urls = re.findall(r"https?://www\.toutiao\.com/article/\d+/?", trending_md)
    seen = set()
    unique_urls = []
    for u in article_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    if unique_urls:
        print(f"  找到 {len(unique_urls)} 个 article 链接:")
        for u in unique_urls[:5]:
            video_tag = " [视频,跳过]" if is_video_url(u) else ""
            print(f"    - {u}{video_tag}")
    else:
        print("  ⚠️ 未找到 article 链接，输出 trending 页摘要")
        print(f"  摘要: {trending_md[:500]}")
        return

    # Step 4: 跟进 article 页提取正文
    non_video_urls = [u for u in unique_urls if not is_video_url(u)]
    if not non_video_urls:
        print("  ⚠️ 所有 article 链接都是视频，无法提取正文")
        return

    target_article_url = non_video_urls[0]
    print(f"\n[4/4] Jina 提取 article 正文: {target_article_url}")
    t2 = time.time()
    article_md = await asyncio.to_thread(extract_markdown_via_jina, target_article_url, 25.0)
    elapsed = time.time() - t2

    if article_md and len(article_md) > 200:
        cleaned = clean_toutiao_article_markdown(article_md)
        if cleaned and len(cleaned) > 100:
            print(f"  ✅ 成功 ({elapsed:.1f}s)，正文长度: {len(cleaned)} 字符")
            print(f"\n{'─' * 60}")
            print("最终提取正文预览 (前800字):")
            print(f"{'─' * 60}")
            print(cleaned[:800])
            print(f"{'─' * 60}")
        else:
            print(f"  ⚠️ Jina 返回了内容但清洗后不足 ({elapsed:.1f}s)，原始长度: {len(article_md)}")
            print(f"  清洗后: {cleaned[:300]}")
    else:
        print(f"  ❌ 失败 ({elapsed:.1f}s)，未返回有效内容 (长度: {len(article_md) if article_md else 0})")

    # 总结
    print(f"\n{'=' * 60}")
    print("测试总结:")
    print(f"  热榜获取: ✅")
    print(f"  Trending Jina 提取: {'✅' if trending_md else '❌'}")
    print(f"  Article 链接提取: {'✅ ' + str(len(unique_urls)) + '条' if unique_urls else '❌'}")
    print(f"  Article 正文提取: {'✅' if article_md and len(article_md) > 200 else '❌'}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())

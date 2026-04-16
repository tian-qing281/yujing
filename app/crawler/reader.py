import json
import os
import re
import sys
import asyncio
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse, unquote

import httpx
from bs4 import BeautifulSoup


COOKIE_DIR = os.path.join(os.path.dirname(__file__), "cookies")
# 代理已禁用：所有请求走直连
VIDEO_URL_MARKERS = (
    "/video/",
    "video.toutiao.com",
    "bilibili.com/video/",
    ".mp4",
    ".m3u8",
    "/short_video/",
)


def _safe_print(label: str, value: str):
    try:
        text = f"{label}\n{value}\n"
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        else:
            print(text)
    except Exception:
        pass


def _is_video_url(url: str) -> bool:
    lowered = (url or "").strip().lower()
    return any(marker in lowered for marker in VIDEO_URL_MARKERS)


def _format_compact_count(value) -> str:
    try:
        number = int(float(str(value).replace(",", "")))
    except Exception:
        return "0"
    if number >= 100000000:
        return f"{number / 100000000:.1f}亿".replace(".0亿", "亿")
    if number >= 10000:
        return f"{number / 10000:.1f}万".replace(".0万", "万")
    return str(number)


def normalize_url(url: str, base_url: str = "") -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return f"https:{url}"
    if url.startswith("/"):
        if "weibo.com" in base_url:
            return f"https://weibo.com{url}"
        if "zhihu.com" in base_url:
            return f"https://www.zhihu.com{url}"
    return url


def _load_cookie_header(site_key: str) -> str:
    cookie_path = os.path.join(COOKIE_DIR, f"{site_key}.json")
    if not os.path.exists(cookie_path):
        return ""

    try:
        with open(cookie_path, "r", encoding="utf-8") as file:
            cookies = json.load(file)
        raw = "; ".join([f"{item['name']}={item['value']}" for item in cookies if item.get("name")])
        return raw.encode("ascii", errors="ignore").decode("ascii")
    except Exception:
        return ""


def _proxy_candidates() -> list[dict]:
    """始终直连，不使用代理。"""
    return [{"trust_env": False, "proxy": None, "label": "direct"}]


def _build_jina_mirror_urls(target_url: str) -> list[str]:
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
        candidates.extend(
            [
                f"https://r.jina.ai/http://{trimmed_url}",
                f"https://r.jina.ai/http://{trimmed_without_scheme}",
            ]
        )

    deduped = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def _extract_markdown_via_jina_sync(target_url: str, timeout: float = 30.0) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/plain, text/markdown;q=0.9, */*;q=0.8",
    }

    last_error = None
    for candidate in _proxy_candidates():
        with httpx.Client(
            headers=headers,
            follow_redirects=True,
            timeout=timeout,
            verify=False,
            trust_env=candidate["trust_env"],
            proxy=candidate["proxy"],
        ) as client:
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
                    except Exception as exc:
                        last_error = exc

    if last_error:
        raise last_error
    return ""


def _is_zhihu_safety_text(text: str) -> bool:
    markers = [
        "安全验证 - 知乎",
        "系统监测到您的网络环境存在异常风险",
        "请输入验证码进行验证",
        "暂时限制本次访问",
    ]
    return any(marker in (text or "") for marker in markers)


def _extract_toutiao_story_digest(markdown: str) -> str:
    title_match = re.search(r"^##\s+(.+)$", markdown, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else ""

    heat_match = re.search(r"(热门事件[^\n]*)", markdown)
    heat_line = heat_match.group(1).strip() if heat_match else ""

    link_matches = []
    for label, target in re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", markdown):
        clean_label = label.strip()
        clean_target = target.strip()
        if "toutiao.com" not in clean_target:
            continue
        if clean_label.startswith("Image"):
            continue
        link_matches.append((clean_label, clean_target))

    detail_entry = next(
        (
            (label, target)
            for label, target in link_matches
            if re.search(r"/(article|w|answer|topic)/", target) and not _is_video_url(target)
        ),
        None,
    )
    video_entry = next(((label, target) for label, target in link_matches if _is_video_url(target)), None)
    source_entry = next(
        ((label, target) for label, target in link_matches if "/c/user/" in target),
        None,
    )
    comment_entry = next(
        ((label, target) for label, target in link_matches if "评论" in label),
        None,
    )

    time_match = re.search(r"(\d+\s*小时前|\d+\s*分钟前|\d+\s*天前)", markdown)
    time_text = time_match.group(1).strip() if time_match else ""

    detail_title = detail_entry[0] if detail_entry else title
    detail_url = detail_entry[1] if detail_entry else ""
    source_name = source_entry[0] if source_entry else ""
    comment_text = comment_entry[0] if comment_entry else ""

    if video_entry and not detail_entry:
        return "❌ [跳过视频] 当前热点详情入口是视频页，未提供可稳定抽取的正文文本。"

    lines = ["[头条热点详情摘要]"]
    if title:
        lines.append(f"热榜标题: {title}")
    if heat_line:
        lines.append(f"热度: {heat_line}")
    if detail_title:
        lines.append(f"详情标题: {detail_title}")
    if source_name:
        lines.append(f"来源: {source_name}")
    if comment_text:
        lines.append(f"互动: {comment_text}")
    if time_text:
        lines.append(f"时间: {time_text}")
    if detail_url:
        lines.append(f"详情页链接: {detail_url}")
    lines.append("说明: 头条热榜聚合页未直接返回全文，当前已定位到真实内容详情入口。")
    return "\n".join(lines)


async def _extract_toutiao_content(url: str) -> str:
    markdown = await asyncio.to_thread(_extract_markdown_via_jina_sync, url, 20.0)
    if not markdown:
        return ""

    # 从 trending 聚合页的 Jina 输出中提取 article 链接
    article_urls = re.findall(r"https?://www\.toutiao\.com/article/\d+/?", markdown)
    # 去重保持顺序
    seen = set()
    unique_article_urls = []
    for u in article_urls:
        if u not in seen:
            seen.add(u)
            unique_article_urls.append(u)

    # 优先跟进 article 页获取完整正文（跳过视频链接）
    for article_url in unique_article_urls[:3]:
        if _is_video_url(article_url):
            continue
        try:
            article_md = await asyncio.to_thread(_extract_markdown_via_jina_sync, article_url, 20.0)
            if article_md and len(article_md) > 200:
                article_text = _clean_toutiao_article_markdown(article_md)
                if article_text and len(article_text) > 100:
                    return article_text[:8000]
        except Exception:
            continue

    # article 页都提取不到，回退到 trending 页面摘要
    markers = [
        "事件详情",
        "热门事件",
        "相关阅读",
        "相关内容",
    ]
    if not any(marker in markdown for marker in markers):
        return ""

    first_heading_index = markdown.find("\n## ")
    if first_heading_index != -1:
        markdown = markdown[first_heading_index + 1 :].strip()

    for section_marker in ["\n相关内容", "\n更多内容", "\n延伸阅读"]:
        if section_marker in markdown:
            markdown = markdown.split(section_marker, 1)[0].strip()
            break

    cleaned_lines = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if "![Image" in stripped:
            continue
        if stripped in {"*   复制链接", "*   微信  微信扫码分享", "*   新浪微博", "*   QQ空间"}:
            continue
        cleaned_lines.append(line)

    markdown = "\n".join(cleaned_lines).strip()
    structured = _extract_toutiao_story_digest(markdown)
    return structured[:8000] if structured else markdown[:8000]


def _clean_toutiao_article_markdown(markdown: str) -> str:
    """清理头条 article 页通过 Jina 提取的 markdown，只保留正文。"""
    # 去掉 Jina 开头的元信息
    if "Markdown Content:" in markdown:
        markdown = markdown.split("Markdown Content:", 1)[1].strip()

    # 定位正文起点：第一个标题之后
    first_heading = re.search(r"^#{1,3}\s+.+$", markdown, re.MULTILINE)
    if first_heading:
        markdown = markdown[first_heading.start():].strip()

    # 截断尾部噪音
    for tail_marker in ["\n相关推荐", "\n热门评论", "\n延伸阅读", "\n更多内容", "\nTA的热门", "\n查看更多"]:
        if tail_marker in markdown:
            markdown = markdown.split(tail_marker, 1)[0].strip()
            break

    # 逐行清理
    cleaned_lines = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if "![Image" in stripped or "![image" in stripped:
            continue
        if stripped.startswith("*   ") and any(k in stripped for k in ["复制链接", "微信", "微博", "QQ空间", "分享"]):
            continue
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines).strip()


def _normalize_weibo_time(time_str: str) -> str:
    now = datetime.now()
    if not time_str:
        return ""

    ts = time_str.strip()
    try:
        if any(token in ts for token in ["刚刚", "秒前"]):
            return now.strftime("%m-%d %H:%M")

        minute_match = re.search(r"(\d+)分钟", ts)
        if minute_match:
            return (now - timedelta(minutes=int(minute_match.group(1)))).strftime("%m-%d %H:%M")

        hour_match = re.search(r"(\d+)小时", ts)
        if hour_match:
            return (now - timedelta(hours=int(hour_match.group(1)))).strftime("%m-%d %H:%M")

        if "今天" in ts:
            clock = re.search(r"(\d{1,2}:\d{1,2})", ts)
            return f"{now.strftime('%m-%d')} {clock.group(1)}" if clock else ts

        if "昨天" in ts:
            clock = re.search(r"(\d{1,2}:\d{1,2})", ts)
            return f"{(now - timedelta(days=1)).strftime('%m-%d')} {clock.group(1)}" if clock else ts

        date_match = re.search(r"(\d{4}-)?(\d{1,2}-\d{1,2})(\s+\d{1,2}:\d{1,2})?", ts)
        if date_match:
            return f"{date_match.group(2)}{date_match.group(3) or ' 00:00'}".strip()
    except Exception:
        return ts

    return ts


def _is_recent_weibo_time(time_str: str) -> bool:
    if not time_str:
        return False
    ts = time_str.strip()
    if any(token in ts for token in ["秒前", "分钟前", "刚刚", "今天", "昨天"]):
        return True
    if "小时" in ts:
        match = re.search(r"\d+", ts)
        return int(match.group()) <= 24 if match else True
    return False


def _clean_text_node(node) -> str:
    for anchor in node.select("a"):
        if "展开" in anchor.get_text(strip=True):
            anchor.decompose()
    text = node.get_text(separator="\n", strip=True)
    text = re.sub(r"^\d+[\s\.]+", "", text)
    return text.strip()


async def _parse_weibo_search(client: httpx.AsyncClient, base_url: str):
    parsed = urlparse(base_url)
    q_value = parse_qs(parsed.query).get("q", [""])[0]
    topic_query = unquote(q_value).replace("#", "").strip()
    all_posts = []

    for page_index in range(1, 6):
        page_url = f"{base_url}&page={page_index}" if "page=" not in base_url else base_url
        try:
            response = await client.get(page_url)
            response.raise_for_status()
        except Exception:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select(".card-wrap") or soup.select(".card")
        if not cards:
            continue

        for card in cards:
            time_node = card.select_one(".from a") or card.select_one(".from") or card.select_one(".woo-box-item-flex .woo-box-flex")
            time_text = time_node.get_text(" ", strip=True) if time_node else ""
            if page_index > 1 and time_text and not _is_recent_weibo_time(time_text):
                continue

            content_node = (
                card.select_one('p[node-type="feed_list_content_full"]')
                or card.select_one('p[node-type="feed_list_content"]')
                or card.select_one(".txt")
                or card.select_one(".wbpro-feed-content")
            )
            if not content_node:
                continue

            clean_text = _clean_text_node(content_node)
            if len(clean_text) < 8:
                continue

            if topic_query:
                haystack = f"{clean_text} {card.get_text(' ', strip=True)}"
                if topic_query not in haystack:
                    continue

            author_node = card.select_one(".name") or card.select_one(".woo-typ-main")
            stats_text = ""
            action_nodes = card.select(".card-act li") or card.select(".woo-like-count")
            if action_nodes:
                stats_text = " | ".join(
                    [node.get_text(" ", strip=True) for node in action_nodes if node.get_text(" ", strip=True)]
                )

            all_posts.append(
                {
                    "author": author_node.get_text(strip=True) if author_node else "微博用户",
                    "time": _normalize_weibo_time(time_text),
                    "content_html": f"<p>{clean_text.replace(chr(10), '<br>')}</p>",
                    "stats": stats_text,
                    "page": page_index,
                }
            )

    if all_posts:
        _safe_print("--- WEIBO DEEP CRAWL JSON START ---", json.dumps(all_posts[:20], ensure_ascii=False, indent=2))
        _safe_print("--- WEIBO DEEP CRAWL JSON END ---", f"count={len(all_posts)}")
    return all_posts


async def _parse_zhihu_answers(soup: BeautifulSoup):
    answers = []
    items = soup.select(".List-item") or soup.select(".AnswerItem") or soup.select(".Card")
    for item in items[:6]:
        try:
            name = item.select_one(".AuthorInfo-name") or item.select_one(".UserItem-name")
            content = item.select_one(".RichText") or item.select_one(".ContentItem-description")
            if not content:
                continue
            answers.append(
                {
                    "author": name.get_text(strip=True) if name else "知乎网友",
                    "content_html": str(content),
                }
            )
        except Exception:
            continue
    return answers


async def _extract_zhihu_answers_api(url: str) -> list[dict]:
    match = re.search(r"zhihu\.com/question/(\d+)", url or "")
    if not match:
        return []

    question_id = match.group(1)
    api_url = (
        f"https://www.zhihu.com/api/v4/questions/{question_id}/answers"
        "?include=data%5B%2A%5D.content%2Cvoteup_count%2Ccomment_count%2Ccreated_time%2Cauthor.name"
        "&limit=8&offset=0&platform=desktop&sort_by=default"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": url,
        "Origin": "https://www.zhihu.com",
    }
    cookie_header = _load_cookie_header("zhihu_hot_question")
    if cookie_header:
        headers["Cookie"] = cookie_header

    last_error = None
    for candidate in _proxy_candidates():
        try:
            async with httpx.AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=20.0,
                verify=False,
                trust_env=candidate["trust_env"],
                proxy=candidate["proxy"],
            ) as client:
                response = await client.get(api_url)
                response.raise_for_status()
                payload = response.json()
                answers = []
                for item in (payload.get("data") or [])[:8]:
                    content_html = item.get("content") or ""
                    cleaned = _clean_plaintext_block(content_html, limit=2400)
                    if len(cleaned) < 20:
                        continue
                    answers.append(
                        {
                            "author": ((item.get("author") or {}).get("name")) or "知乎用户",
                            "content_html": f"<p>{cleaned.replace(chr(10), '<br>')}</p>",
                            "stats": f"赞同 {item.get('voteup_count', 0)} · 评论 {item.get('comment_count', 0)}",
                            "time": datetime.fromtimestamp(item.get("created_time") or 0).strftime("%Y-%m-%d %H:%M"),
                        }
                    )
                if answers:
                    print(f"[知乎详情] 问题 {question_id} 通过回答接口采集 {len(answers)} 条回答")
                return answers
        except httpx.HTTPStatusError as exc:
            last_error = f"HTTP {exc.response.status_code}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

    print(f"[知乎详情失败] 问题 {question_id}: {last_error or '未知错误'}")
    return []


def _clean_plaintext_block(text: str, limit: int = 8000) -> str:
    raw = str(text or "")
    if re.search(r"<(p|br|div|strong|span|section|article|img)\b", raw, flags=re.IGNORECASE):
        soup = BeautifulSoup(raw, "html.parser")
        for node in soup(["script", "style", "img", "video", "svg"]):
            node.decompose()
        raw = soup.get_text(separator="\n", strip=True)

    lines = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if len(line) <= 1:
            continue
        if line in {"返回顶部", "责任编辑", "打开APP", "下载APP", "分享", "评论", "收藏"}:
            continue
        lines.append(line)

    deduped = []
    seen = set()
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        deduped.append(line)
    return "\n".join(deduped)[:limit]


async def _extract_wallstreetcn_article(url: str) -> str:
    match = re.search(r"/articles/(\d+)", url or "")
    if not match:
        return ""

    article_id = match.group(1)
    api_url = f"https://api-one.wallstcn.com/apiv1/content/articles/{article_id}?extract=1"
    headers = {"User-Agent": "Mozilla/5.0"}

    last_error = None
    for candidate in _proxy_candidates():
        try:
            async with httpx.AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=20.0,
                verify=False,
                trust_env=candidate["trust_env"],
                proxy=candidate["proxy"],
            ) as client:
                response = await client.get(api_url)
                response.raise_for_status()
                payload = response.json()
                content_html = (((payload or {}).get("data") or {}).get("content")) or ""
                if not content_html:
                    return ""
                soup = BeautifulSoup(content_html, "html.parser")
                for node in soup(["script", "style", "img", "video", "svg"]):
                    node.decompose()
                return _clean_plaintext_block(soup.get_text(separator="\n", strip=True))
        except Exception as exc:
            last_error = exc

    if last_error:
        raise last_error
    return ""


async def _extract_thepaper_article(client: httpx.AsyncClient, url: str) -> str:
    target_url = url
    match = re.search(r"newsDetail_forward_(\d+)", url or "")
    if match:
        target_url = f"https://m.thepaper.cn/newsDetail_forward_{match.group(1)}"

    response = await client.get(target_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    selectors = [
        ".news_txt",
        ".index_cententWrap",
        ".topic-content",
        ".newsdetail_ct",
        ".news-detail-content",
        ".article-content",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        for child in node(["script", "style", "img", "video", "svg"]):
            child.decompose()
        text = _clean_plaintext_block(node.get_text(separator="\n", strip=True))
        if len(text) >= 120:
            return text

    for node in soup(["script", "style", "img", "video", "svg"]):
        node.decompose()
    return _clean_plaintext_block(soup.get_text(separator="\n", strip=True))


def _extract_cls_article_from_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data and next_data.string:
        try:
            payload = json.loads(next_data.string)
            props = (payload or {}).get("props") or {}
            detail = ((props.get("pageProps") or {}).get("detail")) or ((props.get("initialState") or {}).get("detail")) or {}
            article_detail = detail.get("articleDetail") or {}
            text = article_detail.get("content") or article_detail.get("brief") or article_detail.get("title") or ""
            cleaned = _clean_plaintext_block(text)
            if cleaned:
                return cleaned
        except Exception:
            pass

    selectors = [
        ".telegraph-detail-content",
        ".telegraph-content-box",
        ".article-content",
        ".detail-content",
        ".content",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if not node:
            continue
        for child in node(["script", "style", "img", "video", "svg"]):
            child.decompose()
        text = _clean_plaintext_block(node.get_text(separator="\n", strip=True))
        if len(text) >= 80:
            return text
    return ""


async def _extract_bilibili_video_context(url: str) -> str:
    bvid_match = re.search(r"/video/(BV[a-zA-Z0-9]+)", url or "")
    if not bvid_match:
        return ""

    bvid = bvid_match.group(1)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}",
        "Accept": "application/json, text/plain, */*",
    }
    cookie_header = _load_cookie_header("bilibili_hot_video")
    if cookie_header:
        headers["Cookie"] = cookie_header

    last_error = None
    for candidate in _proxy_candidates():
        try:
            async with httpx.AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=14.0,
                verify=False,
                trust_env=candidate["trust_env"],
                proxy=candidate["proxy"],
            ) as client:
                view_response = await client.get("https://api.bilibili.com/x/web-interface/view", params={"bvid": bvid})
                view_response.raise_for_status()
                view_payload = view_response.json()
                if view_payload.get("code") not in (0, None):
                    return f"❌ [B站详情失败] {view_payload.get('message') or '接口返回异常'}"

                data = view_payload.get("data") or {}
                aid = data.get("aid")
                stat = data.get("stat") or {}
                owner = data.get("owner") or {}
                lines = [
                    "[B站视频文本摘要]",
                    "平台: 哔哩哔哩",
                    "数据来源: B站视频详情接口 + 评论接口",
                    f"标题: {data.get('title') or bvid}",
                    f"UP主: {owner.get('name') or '未知'}",
                    f"播放: {_format_compact_count(stat.get('view'))} · 点赞: {_format_compact_count(stat.get('like'))} · 评论: {_format_compact_count(stat.get('reply'))}",
                ]

                desc = _clean_plaintext_block(data.get("desc") or "", limit=1200)
                if desc:
                    lines.append(f"简介: {desc}")

                replies = []
                if aid:
                    seen_messages = set()

                    def _collect_reply(item):
                        if len(replies) >= 30:
                            return
                        message = (((item or {}).get("content") or {}).get("message") or "").strip()
                        message = re.sub(r"\s+", " ", message)
                        if len(message) < 2 or message in seen_messages:
                            return
                        seen_messages.add(message)
                        member_name = (((item or {}).get("member") or {}).get("uname") or "B站用户").strip()
                        like_count = _format_compact_count((item or {}).get("like"))
                        replies.append(f"- {member_name}（{like_count}赞）: {message}")

                    # 策略1: reply/main（游标分页，热门排序）
                    for sort_mode in (3, 2):
                        next_cursor = None
                        for page in range(1, 6):
                            if len(replies) >= 30:
                                break
                            params = {"type": 1, "oid": aid, "mode": sort_mode, "ps": 20}
                            if next_cursor:
                                params["next"] = next_cursor
                            else:
                                params["pn"] = page
                            try:
                                reply_response = await client.get(
                                    "https://api.bilibili.com/x/v2/reply/main",
                                    params=params,
                                )
                                if reply_response.status_code != 200:
                                    continue
                                reply_payload = reply_response.json()
                                cursor_data = (reply_payload.get("data") or {}).get("cursor") or {}
                                next_cursor = cursor_data.get("next")
                                page_replies = ((reply_payload.get("data") or {}).get("replies") or [])
                                if not page_replies:
                                    break
                            except Exception:
                                break
                            for item in page_replies:
                                _collect_reply(item)
                                for sub in ((item or {}).get("replies") or []):
                                    _collect_reply(sub)
                        if len(replies) >= 30:
                            break

                    # 策略2: 老版 reply 接口（页码分页）补充不足
                    if len(replies) < 30:
                        for sort_val in (2, 0):
                            for pn in range(1, 6):
                                if len(replies) >= 30:
                                    break
                                try:
                                    reply_response = await client.get(
                                        "https://api.bilibili.com/x/v2/reply",
                                        params={"type": 1, "oid": aid, "sort": sort_val, "ps": 20, "pn": pn},
                                    )
                                    if reply_response.status_code != 200:
                                        continue
                                    reply_payload = reply_response.json()
                                    page_replies = ((reply_payload.get("data") or {}).get("replies") or [])
                                    if not page_replies:
                                        break
                                    for item in page_replies:
                                        _collect_reply(item)
                                        for sub in ((item or {}).get("replies") or []):
                                            _collect_reply(sub)
                                except Exception:
                                    break
                            if len(replies) >= 30:
                                break

                if replies:
                    lines.append(f"热评文本（{len(replies)} 条）:")
                    lines.extend(replies)
                else:
                    lines.append("说明: 已采集标题、简介与互动统计；评论接口当前未返回可用文本。")

                return "\n".join(lines)[:8000]
        except Exception as exc:
            last_error = exc

    if last_error:
        return f"❌ [B站详情失败] {str(last_error) or '接口连接失败'}"
    return ""


async def extract_article_content(url: str) -> str:
    if not url:
        return "❌ URL 不能为空"

    if "bilibili.com/video/" in url:
        bilibili_context = await _extract_bilibili_video_context(url)
        if bilibili_context:
            return bilibili_context

    if _is_video_url(url):
        return "❌ [跳过视频] 当前链接为视频页，未提供可稳定抽取的正文文本。"

    if "zhihu.com/question/" in url:
        answers = await _extract_zhihu_answers_api(url)
        if answers:
            return "JSON_STREAM_LIST:" + json.dumps(answers, ensure_ascii=False)

    if "toutiao.com" in url and "/trending/" in url:
        try:
            mirrored = await _extract_toutiao_content(url)
            if mirrored:
                return mirrored
        except Exception:
            pass
        return "❌ [抓取失败] 头条热点聚合页为纯 JS 渲染，当前无法直接提取正文。"

    if "toutiao.com" in url and "/article/" in url:
        try:
            article_md = await asyncio.to_thread(_extract_markdown_via_jina_sync, url, 20.0)
            if article_md and len(article_md) > 200:
                article_text = _clean_toutiao_article_markdown(article_md)
                if article_text and len(article_text) > 100:
                    return article_text[:8000]
        except Exception:
            pass

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    if "weibo.com" in url:
        cookie_header = _load_cookie_header("weibo_hot_search")
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        headers["Referer"] = "https://s.weibo.com/"
    elif "zhihu.com" in url:
        cookie_header = _load_cookie_header("zhihu_hot_question")
        headers["Referer"] = "https://www.zhihu.com/"
        headers["Origin"] = "https://www.zhihu.com"
    elif "bilibili.com" in url:
        cookie_header = _load_cookie_header("bilibili_hot_video")
    elif "toutiao.com" in url:
        cookie_header = _load_cookie_header("toutiao_hot")
        headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        headers["Referer"] = "https://www.toutiao.com/"
    else:
        cookie_header = ""

    if cookie_header:
        headers["Cookie"] = cookie_header

    last_error = None
    for candidate in _proxy_candidates():
      for _attempt in range(2):
        try:
            async with httpx.AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=20.0,
                verify=False,
                trust_env=candidate["trust_env"],
                proxy=candidate["proxy"],
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                html = response.text
                final_url = str(response.url)

                if "login" in final_url or "passport" in final_url:
                    return "❌ [凭据失效] 目标站点要求登录。请更新侧边栏 Cookie 配置。"

                if "weibo.com" in url:
                    structured = await _parse_weibo_search(client, url)
                    if structured:
                        return "JSON_STREAM_LIST:" + json.dumps(structured, ensure_ascii=False)
                    return "❌ [抓取失败] 微博搜索页未解析到与当前热词匹配的帖子，可能受登录态、搜索回流或反爬限制影响。"

                if "wallstreetcn.com/articles/" in url:
                    structured = await _extract_wallstreetcn_article(final_url)
                    if structured:
                        return structured

                soup = BeautifulSoup(html, "html.parser")

                if "zhihu.com" in url:
                    structured = await _parse_zhihu_answers(soup)
                    if structured:
                        return "JSON_STREAM_LIST:" + json.dumps(structured, ensure_ascii=False)

                if "thepaper.cn/newsDetail_forward_" in url:
                    structured = await _extract_thepaper_article(client, final_url)
                    if structured:
                        return structured

                if "cls.cn/detail/" in url:
                    structured = _extract_cls_article_from_html(html)
                    if structured:
                        return structured

                for node in soup(["script", "style", "img", "video", "svg"]):
                    node.decompose()
                plain_text = soup.get_text(separator="\n", strip=True)
                if "zhihu.com" in url and _is_zhihu_safety_text(plain_text):
                    return "❌ [凭据失效] 知乎返回安全验证页面，请更新 Cookie 后重试。"
                if "您需要允许该网站执行 JavaScript" in plain_text or "doesn't work properly without JavaScript" in plain_text:
                    return "❌ [抓取失败] 目标页面返回了前端壳资源，未直接提供可分析正文。"
                return plain_text[:6000]
        except httpx.HTTPStatusError as exc:
            last_error = f"❌ 站点状态异常 (HTTP {exc.response.status_code})"
            break
        except httpx.ConnectError as exc:
            last_error = f"❌ 采集引擎连通性故障: {str(exc) or '目标站点连接失败'}"
            if _attempt == 0:
                await asyncio.sleep(2)
                continue
        except Exception as exc:
            last_error = f"❌ 采集引擎连通性故障: {str(exc)}"
            break

    # 最终兜底：如果直连/代理抓取都失败了，且不是知乎/微博等特殊源，尝试用 Jina 路由最后搏一把
    if last_error and not any(k in url for k in ["weibo.com", "zhihu.com", "bilibili.com"]):
        try:
            # 使用同步 Jina 提取器的异步包装版
            jina_content = await asyncio.to_thread(_extract_markdown_via_jina_sync, url, 15.0)
            if jina_content and len(jina_content) > 50:
                return jina_content
        except Exception:
            pass

    return last_error or "❌ 采集引擎连通性故障: 未知错误"


def save_cookie_credential(source_id: str, raw_cookie: str) -> bool:
    os.makedirs(COOKIE_DIR, exist_ok=True)

    try:
        domain_map = {
            "weibo_hot_search": ".weibo.com",
            "baidu_hot": ".baidu.com",
            "toutiao_hot": ".toutiao.com",
            "bilibili_hot_video": ".bilibili.com",
            "zhihu_hot_question": ".zhihu.com",
            "thepaper_hot": ".thepaper.cn",
            "wallstreetcn_news": ".wallstreetcn.com",
            "cls_telegraph": ".cls.cn",
        }
        domain = domain_map.get(source_id, "")
        cookies = []
        for pair in raw_cookie.split(";"):
            if "=" not in pair:
                continue
            name, value = pair.strip().split("=", 1)
            cookies.append({"name": name, "value": value, "domain": domain, "path": "/"})

        with open(os.path.join(COOKIE_DIR, f"{source_id}.json"), "w", encoding="utf-8") as file:
            json.dump(cookies, file, ensure_ascii=False)
        return True
    except Exception:
        return False


def check_credential_exists(source_id: str) -> bool:
    return os.path.exists(os.path.join(COOKIE_DIR, f"{source_id}.json"))

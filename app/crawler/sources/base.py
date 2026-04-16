import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx

from app.database import Article, SessionLocal


class BaseSource:
    source_id = "unknown"
    interval_seconds = 600
    default_item_limit = 30
    fetch_detail_content = False
    _shared_clients = {}
    
    # 全局并发控制：隔离 DB 写入与 NLP 计算
    _db_write_lock = asyncio.Lock()
    _crawler_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="hs-crawler")

    async def fetch(self):
        raise NotImplementedError

    def get_credential(self) -> str:
        cookie_dir = os.path.join(os.path.dirname(__file__), "..", "cookies")
        path = os.path.join(cookie_dir, f"{self.source_id}.json")
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as file:
                cookies = json.load(file)
                raw = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
                return raw.encode("ascii", errors="ignore").decode("ascii")
        except Exception:
            return ""

    def get_client(
        self,
        *,
        timeout: float = 10.0,
        follow_redirects: bool = False,
        verify: bool = True,
    ) -> httpx.AsyncClient:
        key = (timeout, follow_redirects, verify)
        client = self._shared_clients.get(key)
        if client is None:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
            client = httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=follow_redirects,
                verify=verify,
                limits=limits,
                http2=True,
            )
            self._shared_clients[key] = client
        return client

    @classmethod
    async def close_shared_clients(cls):
        clients = list(cls._shared_clients.values())
        cls._shared_clients.clear()
        for client in clients:
            try:
                await client.aclose()
            except Exception:
                pass

    def get_item_limit(self) -> int:
        env_key = f"{self.source_id.upper()}_LIMIT"
        raw = os.getenv(env_key) or os.getenv("CRAWLER_ITEM_LIMIT")
        try:
            limit = int(raw) if raw else self.default_item_limit
        except (TypeError, ValueError):
            limit = self.default_item_limit
        return max(1, limit)

    @property
    def source_display_name(self):
        mapping = {
            "weibo_hot_search": "微博热搜",
            "baidu_hot": "百度热搜",
            "toutiao_hot": "今日头条",
            "bilibili_hot_video": "哔哩哔哩",
            "zhihu_hot_question": "知乎热榜",
            "thepaper_hot": "澎湃热榜",
            "wallstreetcn_news": "华尔街见闻热榜",
            "cls_telegraph": "财联社热榜",
        }
        return mapping.get(self.source_id, self.source_id)

    async def run_and_save(self):
        start_time = datetime.now()
        print(f"[{start_time.strftime('%H:%M:%S')}] [抓取开始] {self.source_display_name}...")
        try:
            items = await self.fetch()
            target_count = self.get_item_limit()
            if len(items) < target_count:
                print(
                    f"[数量不足] {self.source_display_name}: 目标 {target_count} 条，"
                    f"实际返回 {len(items)} 条；不使用非同类接口硬凑数量。"
                )
            if self.fetch_detail_content:
                await self._attach_detail_content(items)
            self._print_fetch_preview(items)
            
            # 使用专用线程池隔离同步 DB 操作，配合全局锁防止多线程竞争 SQLite 锁导致假死
            async with self._db_write_lock:
                await asyncio.get_event_loop().run_in_executor(
                    self._crawler_executor, self._save_to_db, items
                )
            
            duration = (datetime.now() - start_time).total_seconds()
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] [抓取成功] {self.source_display_name} "
                f"(新增/更新: {len(items)} | 耗时: {duration:.1f}秒)"
            )
        except Exception as exc:
            import traceback as _tb
            now_str = datetime.now().strftime('%H:%M:%S')
            error_type = type(exc).__name__
            error_msg = str(exc)
            # 分类诊断
            if isinstance(exc, httpx.TimeoutException):
                reason = "网络超时 — 目标站点响应过慢或不可达"
            elif isinstance(exc, httpx.ConnectError):
                reason = "连接失败 — DNS解析或TCP握手异常"
            elif isinstance(exc, httpx.HTTPStatusError):
                code = exc.response.status_code if hasattr(exc, 'response') else '?'
                reason = f"HTTP {code} — 可能需要更新Cookie或被反爬"
            else:
                reason = "未知异常"
            cookie_status = "有Cookie" if self.get_credential() else "无Cookie"
            print(
                f"[{now_str}] [抓取失败] {self.source_display_name}\n"
                f"  原因: {reason}\n"
                f"  详情: {error_type}: {error_msg}\n"
                f"  凭据: {cookie_status}\n"
                f"  堆栈: {_tb.format_exc().strip().splitlines()[-3:]}"
            )

    async def _attach_detail_content(self, items):
        from app.crawler.reader import extract_article_content
        
        # 增量优化：预先查询本地库，跳过已有正文的抓取
        db = SessionLocal()
        item_ids = [it["item_id"] for it in items if "item_id" in it]
        existing_content_map = {}
        if item_ids:
            try:
                found = db.query(Article.item_id, Article.content).filter(
                    Article.item_id.in_(item_ids),
                    Article.content != None,
                    Article.content != ""
                ).all()
                existing_content_map = {row[0]: row[1] for row in found}
            finally:
                db.close()

        # 并发抓取控制
        sem = asyncio.Semaphore(5)

        async def fetch_with_sem(item):
            item_id = item.get("item_id")
            # 命库内缓存
            if item_id in existing_content_map:
                item["content"] = existing_content_map[item_id]
                return

            url = item.get("url")
            if not url: return
            async with sem:
                try:
                    content = await extract_article_content(url)
                    if content and not str(content).startswith("❌"):
                        item["content"] = content
                except Exception as detail_exc:
                    print(f"  [正文抓取失败] {item.get('title', '?')[:30]} | {type(detail_exc).__name__}: {detail_exc}")

        await asyncio.gather(*(fetch_with_sem(item) for item in items))

    def _print_fetch_preview(self, items):
        pass

    def _save_to_db(self, items):
        if not items:
            return
        db = SessionLocal()
        try:
            now = datetime.now()
            db.query(Article).filter(Article.source_id == self.source_id).update({Article.rank: 999})

            item_ids = [item["item_id"] for item in items]
            existing_articles = db.query(Article).filter(Article.item_id.in_(item_ids)).all()
            existing_map = {article.item_id: article for article in existing_articles}

            for item in items:
                article = existing_map.get(item["item_id"])
                if article:
                    article.rank = item.get("rank", 99)
                    article.pub_date = item.get("pub_date", now)
                    article.url = item.get("url") or article.url
                    article.title = item.get("title") or article.title
                    if item.get("content"):
                        article.content = item["content"]
                    if "extra" in item:
                        article.extra_info = json.dumps(item["extra"], ensure_ascii=False)
                else:
                    db.add(
                        Article(
                            source_id=self.source_id,
                            item_id=item["item_id"],
                            rank=item.get("rank", 99),
                            title=item["title"],
                            url=item.get("url"),
                            pub_date=item.get("pub_date", now),
                            content=item.get("content"),
                            extra_info=json.dumps(item.get("extra", {}), ensure_ascii=False),
                        )
                    )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

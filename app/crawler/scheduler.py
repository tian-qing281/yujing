import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.crawler.sources.baidu import BaiduHotSearch
from app.crawler.sources.bilibili import BilibiliHotVideo
from app.crawler.sources.cls import ClsTelegraph
from app.crawler.sources.thepaper import ThePaperHotNews
from app.crawler.sources.toutiao import ToutiaoHotBoard
from app.crawler.sources.wallstreetcn import WallstreetcnNews
from app.crawler.sources.weibo import WeiboHotSearch
from app.crawler.sources.zhihu import ZhihuHotQuestion

scheduler = AsyncIOScheduler()

sources = [
    WeiboHotSearch(),
    BaiduHotSearch(),
    ToutiaoHotBoard(),
    BilibiliHotVideo(),
    ZhihuHotQuestion(),
    ThePaperHotNews(),
    WallstreetcnNews(),
    ClsTelegraph(),
]


async def _run_morning_brief():
    """定时生成早报并写入缓存。"""
    import httpx

    print("[早报定时] 开始自动生成今日早报...")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("GET", "http://localhost:8000/api/ai/morning_brief") as resp:
                async for _ in resp.aiter_lines():
                    pass
        print("[早报定时] 今日早报已生成并缓存。")
    except Exception as exc:
        print(f"[早报定时] 早报生成失败: {exc}")


async def _check_and_run_brief_on_startup():
    """启动后延迟检查: 若今日早报时间已过且缓存为空, 立即触发一次。"""
    import asyncio
    await asyncio.sleep(15)  # 等待服务器完全就绪
    try:
        from app.api.routes import _morning_brief_cache
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        if _morning_brief_cache.get("date") == today and _morning_brief_cache.get("content"):
            print("[早报定时] 今日早报缓存已存在，跳过启动补发。")
            return

        brief_hour = int(os.getenv("BRIEF_HOUR", "8"))
        brief_minute = int(os.getenv("BRIEF_MINUTE", "0"))
        now = datetime.now()
        scheduled_today = now.replace(hour=brief_hour, minute=brief_minute, second=0, microsecond=0)
        if now > scheduled_today:
            print(f"[早报定时] 今日 {brief_hour:02d}:{brief_minute:02d} 已过，启动补发早报...")
            await _run_morning_brief()
    except Exception as exc:
        print(f"[早报定时] 启动补发检查失败: {exc}")


def _run_incremental_cluster_job():
    """P1.1 · 定时增量聚类：仅处理 clustered_at IS NULL 的最近文章。"""
    from app.database import SessionLocal
    from app.services.incremental_cluster import incremental_cluster

    db = SessionLocal()
    try:
        result = incremental_cluster(db)
        if result.get("pending"):
            print(
                f"[增量聚类] pending={result['pending']} "
                f"attached={result['attached']} new={result['new_events']}"
            )
    except Exception as exc:
        print(f"[增量聚类] 失败: {exc}")
    finally:
        db.close()


def _run_centroid_calibrate_job():
    """P1.1 · 定时 centroid 校准：从原始 article_embeddings 重算，修正在线均值漂移。"""
    from app.database import SessionLocal
    from app.services.incremental_cluster import calibrate_event_centroids

    db = SessionLocal()
    try:
        result = calibrate_event_centroids(db, only_missing=False)
        print(
            f"[centroid 校准] checked={result['checked']} "
            f"updated={result['updated']} no_vec={result['skipped_no_vec']}"
        )
    except Exception as exc:
        print(f"[centroid 校准] 失败: {exc}")
    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        return

    # DEMO_MODE：只跳过 8 个爬虫 source job，数据冻结；
    # 增量聚类 / centroid 校准 / 早报 等基于现有数据的维护任务仍正常注册。
    from app.config import DEMO_MODE
    if DEMO_MODE:
        print("[DEMO_MODE] 已启用，跳过爬虫 source job 注册（聚类/校准/早报照常）")
    else:
        for source in sources:
            scheduler.add_job(
                source.run_and_save,
                "interval",
                seconds=source.interval_seconds,
                id=source.source_id,
                replace_existing=True,
                misfire_grace_time=3600,
            )

    # P1.1 · 增量事件聚类：每 INCR_CLUSTER_INTERVAL_MIN 分钟（默认 10）
    incr_interval = int(os.getenv("INCR_CLUSTER_INTERVAL_MIN", "10"))
    if incr_interval > 0:
        scheduler.add_job(
            _run_incremental_cluster_job,
            "interval",
            minutes=incr_interval,
            id="incremental_cluster",
            replace_existing=True,
            misfire_grace_time=300,
        )
        print(f"[增量聚类] 已注册：每 {incr_interval} 分钟执行一次")

    # P1.1 · centroid 校准：每 CENTROID_CALIBRATE_HOURS 小时（默认 6）
    calib_hours = int(os.getenv("CENTROID_CALIBRATE_HOURS", "6"))
    if calib_hours > 0:
        scheduler.add_job(
            _run_centroid_calibrate_job,
            "interval",
            hours=calib_hours,
            id="centroid_calibrate",
            replace_existing=True,
            misfire_grace_time=1800,
        )
        print(f"[centroid 校准] 已注册：每 {calib_hours} 小时执行一次")

    # 调试模式: BRIEF_INTERVAL_MINUTES 设为 >0 的值则用 interval 触发（如 2 = 每2分钟）
    brief_interval = int(os.getenv("BRIEF_INTERVAL_MINUTES", "0"))
    if brief_interval > 0:
        scheduler.add_job(
            _run_morning_brief,
            "interval",
            minutes=brief_interval,
            id="morning_brief",
            replace_existing=True,
            misfire_grace_time=60,  # 解除 "Run time missed" 警告：允许最多 60s 抖动
        )
        print(f"[早报定时] 调试模式: 每 {brief_interval} 分钟生成一次早报")
    else:
        # 正式模式: 默认每天 08:00
        brief_hour = int(os.getenv("BRIEF_HOUR", "8"))
        brief_minute = int(os.getenv("BRIEF_MINUTE", "0"))
        scheduler.add_job(
            _run_morning_brief,
            "cron",
            hour=brief_hour,
            minute=brief_minute,
            id="morning_brief",
            replace_existing=True,
            misfire_grace_time=7200,
        )
        print(f"[早报定时] 每日 {brief_hour:02d}:{brief_minute:02d} 自动生成早报")

        # 注册启动后补发检查
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_check_and_run_brief_on_startup())
        except Exception:
            pass

    scheduler.start()


def stop_scheduler():
    if not scheduler.running:
        return
    scheduler.shutdown(wait=False)

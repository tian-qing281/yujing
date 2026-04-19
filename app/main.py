import asyncio
import contextlib
import logging
import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
MEILI_DIR = os.path.join(RUNTIME_DIR, "meili")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.runtime_warnings import suppress_known_dependency_warnings

suppress_known_dependency_warnings()
logging.getLogger("jieba").setLevel(logging.ERROR)

load_dotenv(os.path.join(BASE_DIR, ".env"))


# v0.10: HF 环境早期注入
# 必须在 app.api / app.services 等任何可能 import transformers / huggingface_hub 的模块之前执行，
# 否则那些库会把 HF_HUB_OFFLINE / HF_ENDPOINT 读成模块常量并定格。
if os.getenv("EMBED_USE_MIRROR", "0").strip() in ("1", "true", "True", "yes"):
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.environ["HF_HUB_OFFLINE"] = "0"
    os.environ["TRANSFORMERS_OFFLINE"] = "0"
    os.environ["HF_DATASETS_OFFLINE"] = "0"


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _resolve_project_path(path_value: str, fallback: str) -> str:
    if not path_value:
        return fallback
    if os.path.isabs(path_value):
        return path_value
    return os.path.join(BASE_DIR, path_value)

from app.api import agent_routes, proxy, routes  # noqa: E402
from app.crawler.scheduler import start_scheduler, stop_scheduler  # noqa: E402
from app.crawler.sources.base import BaseSource  # noqa: E402
from app.database import Base, engine  # noqa: E402


Base.metadata.create_all(bind=engine)


def _parse_cors_origins():
    raw = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]

    return [origin.strip() for origin in raw.split(",") if origin.strip()]


import socket
import subprocess
import time

meili_process = None

def _is_meili_up(host_url: str):
    # Simple check for port 7700
    try:
        from urllib.parse import urlparse
        parsed = urlparse(host_url)
        with socket.create_connection((parsed.hostname, parsed.port or 80), timeout=1):
            return True
    except:
        return False

def start_meilisearch():
    global meili_process
    host = os.getenv("MEILI_HOST", "http://localhost:7700")
    if _is_meili_up(host):
        logging.info("MeiliSearch 已在运行。")
        return

    os.makedirs(MEILI_DIR, exist_ok=True)
    binary = _resolve_project_path(
        os.getenv("MEILI_BINARY_PATH"),
        os.path.join(MEILI_DIR, "meilisearch-windows-amd64.exe"),
    )
    db_path = _resolve_project_path(
        os.getenv("MEILI_DB_PATH"),
        os.path.join(MEILI_DIR, "data.ms"),
    )
    if not os.path.exists(binary):
        logging.warning(f"未找到 MeiliSearch 可执行文件：{binary}，已跳过自动启动。")
        return

    master_key = os.getenv("MEILI_MASTER_KEY", "yujing-master-secret-key-123456")
    logging.info(f"正在启动 MeiliSearch：{binary}")
    
    # Start MeiliSearch in background
    try:
        meili_process = subprocess.Popen(
            [binary, "--master-key", master_key, "--db-path", db_path],
            cwd=MEILI_DIR,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
    except Exception as e:
        logging.error(f"MeiliSearch 启动失败：{e}")


def stop_meilisearch():
    global meili_process
    if meili_process is None:
        return
    try:
        if meili_process.poll() is None:
            logging.info("正在停止 MeiliSearch 进程...")
            meili_process.terminate()
            try:
                meili_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                logging.warning("MeiliSearch 终止超时，正在强制清理...")
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(meili_process.pid)], capture_output=True)
                else:
                    meili_process.kill()
    except Exception as e:
        logging.error(f"停止 MeiliSearch 时发生异常: {e}")
    finally:
        meili_process = None

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. 扩大默认线程池：避免 Jina 抓取/BERT 推理占满 12-worker 默认池
    # 导致 db.commit / 调度器 callback / 其他 to_thread 调用排队等待
    import concurrent.futures
    loop = asyncio.get_running_loop()
    loop.set_default_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=32, thread_name_prefix="yj-worker")
    )

    # 1. 启动基础服务
    start_meilisearch()
    start_scheduler()
    
    # 2. 启动后台预热与同步任务
    warmup_task = asyncio.create_task(routes.warmup_runtime_dependencies())
    startup_refresh_task = asyncio.create_task(routes.run_startup_refresh())
    
    yield
    
    # 3. 释放资源与优雅停机
    logging.info("收到关机信号，正在执行清理程序...")
    routes._shutting_down.set()

    # 立即停止调度器（不再触发新任务）
    with contextlib.suppress(Exception):
        stop_scheduler()

    # 取消后台预热/同步任务
    for task in (startup_refresh_task, warmup_task):
        if not task.done():
            task.cancel()

    with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError, Exception):
        await asyncio.wait_for(
            asyncio.gather(startup_refresh_task, warmup_task, return_exceptions=True),
            timeout=2.0,
        )

    # 关闭爬虫线程池
    with contextlib.suppress(Exception):
        BaseSource._crawler_executor.shutdown(wait=False, cancel_futures=True)

    # 关闭共享 HTTP 连接池
    with contextlib.suppress(Exception):
        await asyncio.wait_for(BaseSource.close_shared_clients(), timeout=2.0)

    with contextlib.suppress(Exception):
        stop_meilisearch()

    logging.info("系统已安全退出。")


app = FastAPI(title="舆镜 YuJing", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_parse_cors_origins(),
    allow_origin_regex=os.getenv("CORS_ALLOW_ORIGIN_REGEX", r"https?://(localhost|127\.0\.0\.1)(:\d+)?"),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router, prefix="/api")
app.include_router(proxy.router, prefix="/api")
app.include_router(agent_routes.router, prefix="/api")


@app.get("/")
def read_root():
    return {"status": "ACTIVE", "commander": "舆镜 YuJing"}


if __name__ == "__main__":
    import uvicorn

    # 不再自定义 SIGINT handler：原先的实现只是替换 handler 但没通知 uvicorn，
    # 导致首次 Ctrl+C 被 Python 信号处理器吞掉、uvicorn 永远不进入停机流程（表现为"按 Ctrl+C 无反应"）。
    # uvicorn 原生的 SIGINT 行为：第一次触发 lifespan shutdown（2~5 秒）；第二次强制 kill。
    # lifespan 里所有清理动作均带 2~3 秒超时，不会卡死。
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        # 把 uvicorn 等待 app 完成的超时缩短为 5 秒，避免清理脚本吊死
        timeout_graceful_shutdown=5,
    )

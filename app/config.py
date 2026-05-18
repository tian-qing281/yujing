"""舆镜 · 全局配置开关。

集中读取环境变量，所有模块共用。新增配置请加在这里，避免散落 os.getenv。

当前只承载一项核心开关：DEMO_MODE。
其他历史配置仍保留在各自模块的 os.getenv 调用中，未来逐步迁移过来。
"""
from __future__ import annotations

import os


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


# ========== DEMO_MODE 总开关 ==========
# YUJING_DEMO_MODE=1 时进入「答辩演示模式」：
#   1. 数据库切换到 yujing.demo.db（不污染主库）
#   2. 所有 APScheduler 定时任务跳过注册（不爬虫、不增量聚类、不早报）
#   3. 前端通过 VITE_DEMO_MODE=1 同步进入对应模式（轮询拉长、错误静默）
# 默认 0，普通启动行为完全不变。
DEMO_MODE: bool = _is_truthy(os.getenv("YUJING_DEMO_MODE"))

# DEMO 模式专用数据库文件名（相对项目根 runtime/db/ 目录）
DEMO_DB_FILENAME: str = os.getenv("YUJING_DEMO_DB_FILENAME", "yujing.demo.db")


__all__ = ["DEMO_MODE", "DEMO_DB_FILENAME"]

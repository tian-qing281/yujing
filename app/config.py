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
# YUJING_DEMO_MODE=1 时进入「答辩演示模式」：仅冻结数据，不爬取实时数据。
#   - 跳过 8 个爬虫 source 的 APScheduler 定时 job
#   - sync_trigger_crawlers 入口短路（手动刷新 / SWR 后台刷新也不爬）
#   - 其余维护任务（增量聚类 / centroid 校准 / 早报）照常运行
#   - 数据库仍使用主库 runtime/db/yujing.db（不切库）
# 前端通过 VITE_DEMO_MODE=1 同步显示「演示模式」角标。
# 默认 0，普通启动行为完全不变。
DEMO_MODE: bool = _is_truthy(os.getenv("YUJING_DEMO_MODE"))


__all__ = ["DEMO_MODE"]

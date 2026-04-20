"""
Agent 工具 bootstrap。

import 本模块即触发所有 tool_*.py 的模块级 `default_registry.register(...)`
副作用，把工具注册进全局 registry。

M3 的 API 层在首次请求前会导入本模块一次；单测不 import 本模块，
而是各自新建独立 ToolRegistry 并手动注册，保持测试隔离。
"""

from . import tool_search_events  # noqa: F401
from . import tool_get_event_detail  # noqa: F401
from . import tool_get_morning_brief  # noqa: F401
from . import tool_list_hot_platforms  # noqa: F401
from . import tool_search_articles  # noqa: F401
from . import tool_semantic_search_articles  # noqa: F401
from . import tool_analyze_event_sentiment  # noqa: F401
from . import tool_compare_events  # noqa: F401
from . import tool_rank_events_by_sentiment  # noqa: F401

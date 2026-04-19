"""
工具注册表。

M1 只提供最基础的 register / get / list / 清空。
M2 开始，每个具体工具文件（tool_*.py）导入 `default_registry` 并调
`.register(spec)` 自注册。M3 的 API 层会在首次请求时触发一次 `bootstrap`
确保所有工具都被 import 过。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import ToolSpec


class ToolRegistry:
    """工具注册表。通常用全局单例 `default_registry`，测试时可新建独立实例。"""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not spec.name:
            raise ValueError("ToolSpec.name 不能为空")
        if spec.name in self._tools:
            raise ValueError(f"工具 {spec.name!r} 已注册过")
        self._tools[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    def list_all(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def to_openai_functions(self) -> List[Dict[str, Any]]:
        return [t.to_openai_function() for t in self._tools.values()]

    def clear(self) -> None:
        """仅测试用。生产路径不应调用。"""
        self._tools.clear()

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


default_registry = ToolRegistry()

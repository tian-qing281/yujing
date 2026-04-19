from __future__ import annotations

import warnings


def suppress_known_dependency_warnings() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r"pkg_resources is deprecated as an API\..*",
        category=UserWarning,
        module=r"jieba\._compat",
    )
    warnings.filterwarnings(
        "ignore",
        message=r"Deprecated call to `pkg_resources\.declare_namespace\('google'\)`.*",
        category=DeprecationWarning,
        module=r"pkg_resources(\..*)?",
    )
    warnings.filterwarnings(
        "ignore",
        message=r"unclosed file <_io\.BufferedReader name='.*jieba\\analyse\\idf\.txt'>",
        category=ResourceWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r"numpy\.core\._multiarray_umath is deprecated and has been renamed to numpy\._core\._multiarray_umath\..*",
        category=DeprecationWarning,
    )

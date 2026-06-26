"""用户自定义 method 的轻量加载工具。

该模块只服务普通用户接入路径：通过 `module:ClassName` import 一个无参构造的
`BaseMemoryProvider` 子类。内置 method 仍走 registry/TOML 深度集成路径。
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider


def load_custom_memory_provider(class_path: str) -> BaseMemoryProvider:
    """加载并实例化用户自定义 BaseMemoryProvider。

    输入:
        class_path: `module:ClassName` 格式，例如 `my_pkg.my_adapter:MyMemory`。

    输出:
        BaseMemoryProvider: 无参数构造后的 provider 实例。
    """

    module_name, class_name = _split_class_path(class_path)
    try:
        module = import_module(module_name)
    except Exception as exc:
        raise ConfigurationError(
            f"Cannot import custom method module '{module_name}': {exc}"
        ) from exc
    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ConfigurationError(
            f"Custom method class '{class_name}' was not found in '{module_name}'"
        ) from exc
    try:
        instance: Any = cls()
    except TypeError as exc:
        raise ConfigurationError(
            f"Custom method '{class_path}' must provide a no-argument constructor"
        ) from exc
    if not isinstance(instance, BaseMemoryProvider):
        raise ConfigurationError(
            f"Custom method '{class_path}' must inherit BaseMemoryProvider"
        )
    return instance


def _split_class_path(class_path: str) -> tuple[str, str]:
    """解析 `module:ClassName`，并给出明确错误信息。

    输入:
        class_path: 用户传入的 class path。

    输出:
        tuple[str, str]: module 名称和 class 名称。
    """

    if ":" not in class_path:
        raise ConfigurationError(
            "Custom method class must use 'module:ClassName' format"
        )
    module_name, class_name = class_path.split(":", 1)
    if not module_name.strip() or not class_name.strip():
        raise ConfigurationError(
            "Custom method class must use 'module:ClassName' format"
        )
    return module_name.strip(), class_name.strip()

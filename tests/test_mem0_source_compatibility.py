"""测试 vendored mem0 源码在非安装模式下的导入兼容性。

本项目当前直接从 `third_party/methods/mem0-main/` 读取 mem0 源码，而不是把
mem0 安装成 `mem0ai` Python 包。因此源码里的包版本读取逻辑不能依赖已安装
distribution metadata。这里用 fake 子模块隔离外部依赖，只验证 `mem0/__init__.py`
自身在源码模式下能完成初始化。
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from memory_benchmark.config.settings import load_path_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]


pytestmark = pytest.mark.unit


class Mem0SourceCompatibilityTests(unittest.TestCase):
    """验证 mem0 vendored 源码可以在未安装 `mem0ai` 时被加载。"""

    def test_mem0_init_uses_local_source_version_when_package_metadata_is_missing(self):
        """测试 `mem0ai` 元数据缺失时，`mem0.__version__` 使用本地源码 fallback。

        输入:
            无真实 mem0 依赖；测试内部构造 fake `mem0.client.main` 和
            `mem0.memory.main` 模块。

        输出:
            断言执行 `mem0/__init__.py` 后能得到 `local-source` 版本号，并且
            `Memory` 等导出符号仍然存在。
        """

        module = self._load_mem0_init_with_fake_submodules()

        self.assertEqual(module.__version__, "local-source")
        self.assertEqual(module.Memory.__name__, "Memory")
        self.assertEqual(module.MemoryClient.__name__, "MemoryClient")

    def _load_mem0_init_with_fake_submodules(self):
        """在隔离的 fake 包环境中执行 vendored `mem0/__init__.py`。

        输入:
            无。测试内部临时改写 `sys.modules` 并 patch
            `importlib.metadata.version()`。

        输出:
            module: 已执行完成的 fake `mem0` package 模块对象。
        """

        mem0_init_file = load_path_settings(PROJECT_ROOT).resolve_third_party_method_path(
            "mem0-main",
            "mem0",
            "__init__.py",
        )
        fake_modules = self._build_fake_mem0_submodules()
        original_modules = {name: sys.modules.get(name) for name in fake_modules}
        spec = importlib.util.spec_from_file_location(
            "mem0",
            mem0_init_file,
            submodule_search_locations=[str(mem0_init_file.parent)],
        )
        if spec is None or spec.loader is None:
            self.fail(f"无法加载 mem0 init 文件: {mem0_init_file}")

        module = importlib.util.module_from_spec(spec)
        try:
            sys.modules.update(fake_modules)
            sys.modules["mem0"] = module
            with patch(
                "importlib.metadata.version",
                side_effect=importlib.metadata.PackageNotFoundError("mem0ai"),
            ):
                spec.loader.exec_module(module)
        finally:
            for name, original in original_modules.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
            sys.modules.pop("mem0", None)
        return module

    def _build_fake_mem0_submodules(self) -> dict[str, types.ModuleType]:
        """构造 `mem0/__init__.py` 需要导入的最小 fake 子模块。

        输入:
            无。

        输出:
            dict[str, ModuleType]: 可临时写入 `sys.modules` 的 fake 模块表。
        """

        client_package = types.ModuleType("mem0.client")
        client_main = types.ModuleType("mem0.client.main")
        memory_package = types.ModuleType("mem0.memory")
        memory_main = types.ModuleType("mem0.memory.main")

        client_main.AsyncMemoryClient = type("AsyncMemoryClient", (), {})
        client_main.MemoryClient = type("MemoryClient", (), {})
        memory_main.AsyncMemory = type("AsyncMemory", (), {})
        memory_main.Memory = type("Memory", (), {})

        return {
            "mem0.client": client_package,
            "mem0.client.main": client_main,
            "mem0.memory": memory_package,
            "mem0.memory.main": memory_main,
        }


if __name__ == "__main__":
    unittest.main()

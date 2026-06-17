"""method factory 到 adapter 的 efficiency collector 依赖注入测试。

本模块只验证统一 registry 的依赖传递，不加载第三方源码、不访问网络，也不执行真实
Mem0 或 MemoryOS 算法。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.config import OpenAISettings, load_path_settings
from memory_benchmark.methods import registry as registry_module
from memory_benchmark.methods.mem0_adapter import Mem0Config
from memory_benchmark.methods.memoryos_adapter import MemoryOSPaperConfig
from memory_benchmark.methods.registry import MethodBuildContext, get_method_registration
from memory_benchmark.observability.efficiency import EfficiencyCollector


pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("method_name", "config", "adapter_attribute"),
    [
        ("mem0", Mem0Config.smoke(), "Mem0"),
        ("memoryos", MemoryOSPaperConfig(), "MemoryOS"),
    ],
)
def test_method_factory_passes_same_efficiency_collector_to_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    config: Any,
    adapter_attribute: str,
) -> None:
    """factory 必须把 runner 创建的同一 collector 原样注入 adapter。"""

    collector = EfficiencyCollector(run_id="factory-run", enabled=True)
    captured: dict[str, Any] = {}

    class FakeAdapter:
        """只记录构造参数的无网络 adapter。"""

        def __init__(self, **kwargs: Any) -> None:
            """保存 factory 实际传入的关键参数。"""

            captured.update(kwargs)

    monkeypatch.setattr(registry_module, adapter_attribute, FakeAdapter)
    context = MethodBuildContext(
        config=config,
        openai_settings=OpenAISettings(
            api_key="unit-test-key",
            base_url="https://example.invalid/v1",
        ),
        path_settings=load_path_settings(),
        storage_root=tmp_path / "method-state",
        efficiency_collector=collector,
    )

    get_method_registration(method_name).system_factory(context)

    assert captured["efficiency_collector"] is collector


@pytest.mark.parametrize(
    ("method_name", "config", "adapter_attribute"),
    [
        ("mem0", Mem0Config.smoke(), "Mem0"),
        ("memoryos", MemoryOSPaperConfig(), "MemoryOS"),
    ],
)
def test_method_factory_passes_none_when_efficiency_is_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    config: Any,
    adapter_attribute: str,
) -> None:
    """未启用观测时 factory 不应创建隐式 collector。"""

    captured: dict[str, Any] = {}

    class FakeAdapter:
        """只记录构造参数的无网络 adapter。"""

        def __init__(self, **kwargs: Any) -> None:
            """保存 factory 实际传入的关键参数。"""

            captured.update(kwargs)

    monkeypatch.setattr(registry_module, adapter_attribute, FakeAdapter)
    context = MethodBuildContext(
        config=config,
        openai_settings=OpenAISettings(
            api_key="unit-test-key",
            base_url="https://example.invalid/v1",
        ),
        path_settings=load_path_settings(),
        storage_root=tmp_path / "method-state",
    )

    get_method_registration(method_name).system_factory(context)

    assert captured["efficiency_collector"] is None

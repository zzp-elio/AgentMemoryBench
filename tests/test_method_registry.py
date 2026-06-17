"""测试统一 method registry 的能力声明、profile 和 system factory 装配。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.core import (
    ConfigurationError,
    MethodCapability,
    TaskFamily,
    validate_compatibility,
)
from memory_benchmark.methods.mem0_adapter import Mem0Config
from memory_benchmark.methods.memoryos_adapter import MemoryOSPaperConfig
from memory_benchmark.methods.registry import (
    get_method_registration,
    list_methods,
    load_method_profile,
)


pytestmark = pytest.mark.unit


def test_registry_lists_mem0_and_memoryos() -> None:
    """统一入口应同时暴露已迁移的 Mem0 与 MemoryOS。"""

    assert list_methods() == ["mem0", "memoryos"]


def test_mem0_registration_declares_capabilities_factory_and_api_boundary() -> None:
    """Mem0 registration 应声明通用能力和 factory，不持有运行期 secret。"""

    registration = get_method_registration("mem0")

    assert registration.task_families == frozenset({TaskFamily.CONVERSATION_QA})
    assert registration.provided_capabilities == frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.ANSWER_GENERATION,
        }
    )
    assert registration.profile_names == frozenset({"smoke", "official-full"})
    assert registration.requires_api is True
    assert registration.profile_relative_path == Path("configs/methods/mem0.toml")
    assert registration.system_factory is not None
    assert registration.source_identity_factory is not None
    assert registration.model_name_getter is not None
    assert registration.max_workers_getter is not None
    assert not hasattr(registration, "supported_benchmarks")
    assert not hasattr(registration, "predictor")
    assert not hasattr(registration, "api_key")


def test_memoryos_registration_uses_generic_contract() -> None:
    """MemoryOS registration 应声明统一 runner 所需的完整静态契约。"""

    registration = get_method_registration("memoryos")

    assert registration.config_type is MemoryOSPaperConfig
    assert registration.profile_names == frozenset({"smoke", "official-full"})
    assert registration.task_families == frozenset({TaskFamily.CONVERSATION_QA})
    assert registration.provided_capabilities == frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.ANSWER_GENERATION,
        }
    )
    assert registration.profile_relative_path == Path("configs/methods/memoryos.toml")
    assert registration.requires_api is True


def test_compatibility_requires_task_family_and_capabilities() -> None:
    """兼容性校验应接受匹配的 task family 与 capability 子集。"""

    validate_compatibility(
        benchmark_task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        method_task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
    )


def test_compatibility_rejects_unsupported_task_family() -> None:
    """method 不支持 benchmark task family 时应抛配置错误。"""

    with pytest.raises(ConfigurationError, match="task family"):
        validate_compatibility(
            benchmark_task_family=TaskFamily.CONVERSATION_QA,
            required_capabilities=frozenset(),
            method_task_families=frozenset(),
            provided_capabilities=frozenset(),
        )


def test_compatibility_rejects_missing_capabilities() -> None:
    """method 缺少 benchmark 所需 capability 时应抛配置错误。"""

    with pytest.raises(ConfigurationError, match="required capabilities"):
        validate_compatibility(
            benchmark_task_family=TaskFamily.CONVERSATION_QA,
            required_capabilities=frozenset(
                {
                    MethodCapability.CONVERSATION_ADD,
                    MethodCapability.ANSWER_GENERATION,
                }
            ),
            method_task_families=frozenset({TaskFamily.CONVERSATION_QA}),
            provided_capabilities=frozenset({MethodCapability.CONVERSATION_ADD}),
        )


def test_load_method_profile_returns_strongly_typed_mem0_config(
    tmp_path: Path,
) -> None:
    """registry 应通过 TOML loader 构造 owner method 的强类型配置。"""

    profile_path = tmp_path / "configs" / "methods" / "mem0.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
[smoke]
extraction_model = "gpt-4o-mini"
embedding_model = "text-embedding-3-small"
embedding_dimensions = 1536
reader_model = "gpt-4o-mini"
top_k = 10
max_workers = 1
ingestion_chunk_size = 1
infer = true
""",
        encoding="utf-8",
    )

    config = load_method_profile(
        method_name="mem0",
        profile_name="smoke",
        project_root=tmp_path,
    )

    assert isinstance(config, Mem0Config)
    assert config.profile_name == "smoke"
    assert config.top_k == 10


def test_load_method_profile_maps_public_name_to_toml_section(
    tmp_path: Path,
) -> None:
    """registry 应集中维护 CLI profile 名与 TOML section 的映射。"""

    profile_path = tmp_path / "configs" / "methods" / "mem0.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
[official_full]
extraction_model = "gpt-4o-mini"
embedding_model = "text-embedding-3-small"
embedding_dimensions = 1536
reader_model = "gpt-4o-mini"
top_k = 200
max_workers = 10
ingestion_chunk_size = 1
infer = true
""",
        encoding="utf-8",
    )

    config = load_method_profile(
        method_name="mem0",
        profile_name="official-full",
        project_root=tmp_path,
    )

    assert config.profile_name == "official_full"
    assert config.top_k == 200


def test_unknown_method_is_rejected() -> None:
    """未知 method 必须由 registry 给出明确错误。"""

    with pytest.raises(ConfigurationError, match="Unknown method"):
        get_method_registration("unknown")

def test_unknown_profile_is_rejected_by_registry() -> None:
    """未知 method profile 必须在读取 TOML 前失败。"""

    with pytest.raises(ConfigurationError, match="Unknown Mem0 profile"):
        load_method_profile(
            method_name="mem0",
            profile_name="cheap-ish",
            project_root=".",
        )

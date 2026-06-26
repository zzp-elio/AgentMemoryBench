"""测试统一 method registry 的能力声明、profile 和 system factory 装配。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.core import (
    ConfigurationError,
    Conversation,
    MethodCapability,
    TaskFamily,
    validate_compatibility,
)
from memory_benchmark.methods.mem0_adapter import Mem0Config
from memory_benchmark.methods.memoryos_adapter import MemoryOSPaperConfig
from memory_benchmark.methods.registry import (
    MethodBuildContext,
    get_method_registration,
    list_methods,
    load_method_profile,
)


pytestmark = pytest.mark.unit


def test_registry_lists_conversation_qa_methods() -> None:
    """统一入口应暴露当前已接入的 conversation-QA method。"""

    assert list_methods() == ["amem", "lightmem", "mem0", "memoryos"]


def test_mem0_registration_declares_capabilities_factory_and_api_boundary() -> None:
    """Mem0 registration 应声明通用能力和 factory，不持有运行期 secret。"""

    registration = get_method_registration("mem0")

    assert registration.task_families == frozenset({TaskFamily.CONVERSATION_QA})
    assert registration.provided_capabilities == frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.MEMORY_RETRIEVAL,
        }
    )
    assert registration.profile_names == frozenset({"smoke", "official-full"})
    assert registration.requires_api is True
    assert registration.profile_relative_path == Path("configs/methods/mem0.toml")
    assert registration.system_factory is not None
    assert registration.source_identity_factory is not None
    assert registration.model_name_getter is not None
    assert registration.max_workers_getter is not None
    assert registration.supports_shared_instance_parallelism is False
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
            MethodCapability.MEMORY_RETRIEVAL,
        }
    )
    assert registration.profile_relative_path == Path("configs/methods/memoryos.toml")
    assert registration.requires_api is True


def test_built_in_methods_advertise_memory_retrieval_capability() -> None:
    """retrieve-first prediction 要求内置 method 声明 memory_retrieval。"""

    for method_name in ("mem0", "memoryos", "amem", "lightmem"):
        registration = get_method_registration(method_name)

        assert MethodCapability.CONVERSATION_ADD in registration.provided_capabilities
        assert MethodCapability.MEMORY_RETRIEVAL in registration.provided_capabilities
        assert (
            MethodCapability.ANSWER_GENERATION
            not in registration.provided_capabilities
        )


def test_clean_retry_support_is_only_declared_by_methods_with_safe_state_cleanup() -> None:
    """只有能安全清理单个 conversation 状态的内置 method 才声明 clean retry。

    输入:
        registry 中四个内置 method。

    输出:
        A-Mem、LightMem、MemoryOS 有 conversation 级 clean hook；Mem0 仍为 None，
        避免误删共享 Qdrant/history 状态。
    """

    assert get_method_registration("amem").clean_failed_ingest_state is not None
    assert get_method_registration("lightmem").clean_failed_ingest_state is not None
    assert get_method_registration("memoryos").clean_failed_ingest_state is not None
    assert get_method_registration("mem0").clean_failed_ingest_state is None


def test_clean_retry_hook_uses_failed_worker_state_for_isolated_runs(
    tmp_path: Path,
) -> None:
    """isolated worker 失败重试时，应清理上次失败 worker 的 state 目录。

    输入:
        MethodBuildContext.storage_root 指向 run 级 `method_state/`，failed_state
        带 `worker_idx=2`。

    输出:
        A-Mem clean hook 删除 `method_state/worker_2/<conversation>/`，不会误删
        run 根目录下同名 conversation state。
    """

    root_state = tmp_path / "method_state" / "conv_1"
    worker_state = tmp_path / "method_state" / "worker_2" / "conv_1"
    root_state.mkdir(parents=True)
    worker_state.mkdir(parents=True)
    (root_state / "marker.txt").write_text("root", encoding="utf-8")
    (worker_state / "marker.txt").write_text("worker", encoding="utf-8")
    context = MethodBuildContext(
        config=None,
        openai_settings=None,
        path_settings=None,
        storage_root=tmp_path / "method_state",
    )
    conversation = Conversation(conversation_id="conv/1")

    clean_hook = get_method_registration("amem").clean_failed_ingest_state
    assert clean_hook is not None
    clean_hook(context, conversation, {"worker_idx": 2})

    assert root_state.exists()
    assert not worker_state.exists()


def test_compatibility_requires_task_family_and_capabilities() -> None:
    """兼容性校验应接受匹配的 task family 与 capability 子集。"""

    validate_compatibility(
        benchmark_task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        method_task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
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
                    MethodCapability.MEMORY_RETRIEVAL,
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
top_k = 200
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
    assert config.top_k == 200


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

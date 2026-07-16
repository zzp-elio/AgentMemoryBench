"""统一 method 注册表。

本模块声明 method 支持的任务族、能力、profile 类型和实例 factory。registry 不保存
API key、method 实例、benchmark 白名单或运行状态。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from memory_benchmark.config import (
    OpenAISettings,
    PathSettings,
    load_path_settings,
)
from memory_benchmark.config.profiles import load_typed_profile
from memory_benchmark.core import (
    BaseMemorySystem,
    ConfigurationError,
    Conversation,
    MethodCapability,
    TaskFamily,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    ModelDescriptor,
    RetrievalObservationContract,
)

from .amem_adapter import (
    AMem,
    AMemConfig,
    build_amem_source_identity,
    clean_amem_conversation_state,
)
from .lightmem_adapter import (
    LightMem,
    LightMemConfig,
    build_lightmem_source_identity,
    clean_lightmem_conversation_state,
)
from .mem0_adapter import Mem0, Mem0Config, build_mem0_source_identity
from .memoryos_adapter import (
    MemoryOS,
    MemoryOSPaperConfig,
    build_memoryos_source_identity,
    clean_memoryos_conversation_state,
)
from .simplemem_adapter import (
    SIMPLEMEM_LLM_MODEL_ID,
    SimpleMem,
    SimpleMemConfig,
    build_simplemem_source_identity,
    clean_simplemem_conversation_state,
)


@dataclass(frozen=True)
class MethodBuildContext:
    """构造一次运行所需 method 实例的依赖集合。

    字段:
        config: 从 method TOML profile 加载的强类型配置。
        openai_settings: 需要外部 API 时的 OpenAI-compatible 连接配置；离线
            method 为 `None`。
        path_settings: 项目路径配置。
        storage_root: 当前 run 独占的 method 状态目录。
        benchmark_name: 当前 benchmark registry 名，用于按 benchmark profile 特化
            method 实例级协议声明。
        completed_conversations: resume 时已确认完成写入的 conversation。
        efficiency_collector: runner 创建的可选效率 observation collector。
    """

    config: Any
    openai_settings: OpenAISettings | None
    path_settings: PathSettings
    storage_root: Path
    benchmark_name: str | None = None
    completed_conversations: tuple[Conversation, ...] = ()
    efficiency_collector: EfficiencyCollector | None = None


@dataclass(frozen=True)
class MethodRegistration:
    """一个统一 CLI method 的静态注册信息。

    字段:
        name: CLI 使用的 method 名称。
        task_families: method 支持的 benchmark 任务族。
        provided_capabilities: method 对 runner 提供的稳定能力。
        profile_sections: `(CLI profile 名, TOML section 名)` 的稳定映射。
        profile_relative_path: 相对项目根的 TOML profile 路径。
        config_type: profile 加载后构造的强类型配置类。
        requires_api: prediction 是否需要外部 API。
        system_factory: 根据运行上下文构造统一 memory system。
        source_identity_factory: 生成第三方 method 源码身份。
        model_name_getter: 从强类型配置读取生成模型名。
        max_workers_getter: 从强类型配置读取 conversation 并发数。
        display_name: 用于 CLI、manifest 和报错的人类可读 method 名称。
        protocol_version: method 显式声明的 provider 协议版本，供 manifest 盖章与
            worker 运行时交叉校验使用。
        provenance_granularity: 可选静态 provenance 粒度；为空时沿用实例声明。
        retrieval_evidence_contract_version: 可选逐题 retrieval evidence 契约版本；
            非空时写入 method manifest 作为 resume 身份，声明该 run 的 answer prompt
            artifact 携带 per-question `retrieval_evidence`。
        workload_estimator: 可选的公开工作量估算 hook。
        allow_smoke_worker_override: 是否允许 smoke worker 覆盖（CLI `--workers`）配置值。
        efficiency_model_inventory_getter: 启用效率观测时生成模型清单。
        efficiency_instrumentation_identity_getter: 启用观测时生成插桩身份。
        retrieval_observation_contract_getter: 启用观测时生成 retrieval 强契约。
        clean_failed_ingest_state: 可选 clean retry hook；只有内置 method 能证明可
            conversation 级安全清理半写入状态时才声明。
        embedding_identity_getter: 可选回调，从 ``config.to_manifest()`` 字典抽取当前
            build 的 ``(provider, model, dimension, revision)``，供给 track identity
            契约的 concrete embedding 身份；未声明时返回 None 表示 pending。值必须与
            method.config 同一真实值，不得提前写入未来配置。
    """

    name: str
    task_families: frozenset[TaskFamily]
    provided_capabilities: frozenset[MethodCapability]
    profile_sections: tuple[tuple[str, str], ...]
    profile_relative_path: Path
    config_type: type[Any]
    requires_api: bool
    system_factory: Callable[[MethodBuildContext], BaseMemorySystem]
    source_identity_factory: Callable[[PathSettings], dict[str, Any]]
    model_name_getter: Callable[[Any], str]
    max_workers_getter: Callable[[Any], int]
    display_name: str
    protocol_version: str
    provenance_granularity: str | None = None
    retrieval_evidence_contract_version: str | None = None
    workload_estimator: Callable[[Conversation, Any], int] | None = None
    allow_smoke_worker_override: bool = False
    efficiency_model_inventory_getter: (
        Callable[[Any], tuple[ModelDescriptor, ...]] | None
    ) = None
    efficiency_instrumentation_identity_getter: (
        Callable[[PathSettings, Any, dict[str, Any]], dict[str, object]] | None
    ) = None
    retrieval_observation_contract_getter: (
        Callable[[Any], RetrievalObservationContract] | None
    ) = None
    supports_shared_instance_parallelism: bool = False
    clean_failed_ingest_state: (
        Callable[[MethodBuildContext, Conversation, dict[str, Any]], None] | None
    ) = None
    embedding_identity_getter: (
        Callable[[dict[str, Any]], tuple[str | None, str | None, int | None, str | None] | None]
        | None
    ) = None

    @property
    def profile_names(self) -> frozenset[str]:
        """返回 method 对外公开的 CLI profile 名称。"""

        return frozenset(profile_name for profile_name, _ in self.profile_sections)

    def resolve_profile_section(self, profile_name: str) -> str:
        """把公开 profile 名解析为 TOML section，未知名称时显式报错。"""

        for public_name, section_name in self.profile_sections:
            if public_name == profile_name:
                return section_name
        supported = ", ".join(sorted(self.profile_names))
        raise ConfigurationError(
            f"Unknown {self.display_name} profile '{profile_name}'. "
            f"Supported: {supported}"
        )


def _build_mem0_system(context: MethodBuildContext) -> BaseMemorySystem:
    """根据统一 build context 构造本地 OSS Mem0 adapter。"""

    if not isinstance(context.config, Mem0Config):
        raise ConfigurationError("Mem0 factory requires Mem0Config")
    if context.openai_settings is None:
        raise ConfigurationError("Mem0 factory requires OpenAI settings")
    return Mem0(
        config=context.config,
        openai_settings=context.openai_settings,
        storage_root=context.storage_root,
        path_settings=context.path_settings,
        existing_conversation_ids={
            conversation.conversation_id
            for conversation in context.completed_conversations
        },
        efficiency_collector=context.efficiency_collector,
        consume_granularity=(
            "session"
            if context.benchmark_name in {"longmemeval", "halumem"}
            else "pair"
            if context.benchmark_name == "beam"
            else "turn"
        ),
        session_memory_report=context.benchmark_name == "halumem",
        benchmark_name=context.benchmark_name,
    )


def _build_simplemem_system(context: MethodBuildContext) -> BaseMemorySystem:
    """根据统一 build context 构造 SimpleMem text backend adapter。"""

    if not isinstance(context.config, SimpleMemConfig):
        raise ConfigurationError("SimpleMem factory requires SimpleMemConfig")
    if context.openai_settings is None:
        raise ConfigurationError("SimpleMem factory requires OpenAI settings")
    return SimpleMem(
        config=context.config,
        path_settings=context.path_settings,
        storage_root=context.storage_root,
        openai_settings=context.openai_settings,
        efficiency_collector=context.efficiency_collector,
    )


def _simplemem_model_name(config: Any) -> str:
    """从 SimpleMem 强类型配置读取 LLM 名称。"""

    if not isinstance(config, SimpleMemConfig):
        raise ConfigurationError("SimpleMem model getter requires SimpleMemConfig")
    return config.llm_model


def _simplemem_max_workers(config: Any) -> int:
    """从 SimpleMem 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, SimpleMemConfig):
        raise ConfigurationError("SimpleMem worker getter requires SimpleMemConfig")
    return config.max_workers


def _simplemem_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 SimpleMem efficiency observation 会引用的模型身份。"""

    if not isinstance(config, SimpleMemConfig):
        raise ConfigurationError(
            "SimpleMem model inventory getter requires SimpleMemConfig"
        )
    return (
        ModelDescriptor(
            model_id=SIMPLEMEM_LLM_MODEL_ID,
            model_name=config.llm_model,
            model_role="memory_and_retrieval_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="simplemem-embedding",
            model_name=config.embedding_model_path,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model_path,
            embedding_dimension=config.embedding_dimension,
            tokenizer_name=config.embedding_model_path,
        ),
    )


def _simplemem_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 SimpleMem 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, SimpleMemConfig):
        raise ConfigurationError(
            "SimpleMem instrumentation identity getter requires SimpleMemConfig"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/simplemem_adapter.py")
    return {
        "collector_schema": 1,
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": config.embedding_model_path,
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _build_amem_system(context: MethodBuildContext) -> BaseMemorySystem:
    """根据统一 build context 构造 A-Mem adapter。"""

    if not isinstance(context.config, AMemConfig):
        raise ConfigurationError("A-Mem factory requires AMemConfig")
    if context.openai_settings is None:
        raise ConfigurationError("A-Mem factory requires OpenAI settings")
    system = AMem(
        config=context.config,
        openai_api_key=context.openai_settings.api_key,
        openai_base_url=context.openai_settings.base_url,
        storage_root=context.storage_root,
        path_settings=context.path_settings,
        efficiency_collector=context.efficiency_collector,
    )
    for conversation in context.completed_conversations:
        system.load_existing_conversation_state(conversation)
    return system


def _amem_model_name(config: Any) -> str:
    """从 A-Mem 强类型配置读取回答模型名。"""

    if not isinstance(config, AMemConfig):
        raise ConfigurationError("A-Mem model getter requires AMemConfig")
    return config.llm_model


def _amem_max_workers(config: Any) -> int:
    """从 A-Mem 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, AMemConfig):
        raise ConfigurationError("A-Mem worker getter requires AMemConfig")
    return config.max_workers


def _amem_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 A-Mem efficiency observation 会引用的模型身份。"""

    if not isinstance(config, AMemConfig):
        raise ConfigurationError(
            "A-Mem model inventory getter requires AMemConfig"
        )
    return (
        ModelDescriptor(
            model_id="amem-memory-llm",
            model_name=config.llm_model,
            model_role="memory_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="amem-answer-llm",
            model_name=config.llm_model,
            model_role="answer_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="amem-embedding",
            model_name=config.embedding_model,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model,
            tokenizer_name=config.embedding_model,
        ),
    )


def _amem_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 A-Mem 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, AMemConfig):
        raise ConfigurationError(
            "A-Mem instrumentation identity getter requires AMemConfig"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/amem_adapter.py")
    return {
        "collector_schema": 1,
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": config.embedding_model,
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _mem0_model_name(config: Any) -> str:
    """从 Mem0 强类型配置读取 reader 模型名。"""

    if not isinstance(config, Mem0Config):
        raise ConfigurationError("Mem0 model getter requires Mem0Config")
    return config.reader_model


def _build_lightmem_system(context: MethodBuildContext) -> BaseMemorySystem:
    """根据统一 build context 构造 LightMem adapter。"""

    if not isinstance(context.config, LightMemConfig):
        raise ConfigurationError("LightMem factory requires LightMemConfig")
    if context.openai_settings is None:
        raise ConfigurationError("LightMem factory requires OpenAI settings")
    system = LightMem(
        config=context.config,
        openai_settings=context.openai_settings,
        storage_root=context.storage_root,
        path_settings=context.path_settings,
        efficiency_collector=context.efficiency_collector,
        consume_granularity=(
            "session"
            if context.benchmark_name == "halumem"
            else "pair"
            if context.benchmark_name == "longmemeval"
            else "turn"
        ),
        session_memory_report=context.benchmark_name == "halumem",
        benchmark_name=context.benchmark_name,
    )
    for conversation in context.completed_conversations:
        system.load_existing_conversation_state(conversation)
    return system


def _lightmem_model_name(config: Any) -> str:
    """从 LightMem 强类型配置读取回答模型名。"""

    if not isinstance(config, LightMemConfig):
        raise ConfigurationError("LightMem model getter requires LightMemConfig")
    return config.llm_model


def _lightmem_max_workers(config: Any) -> int:
    """从 LightMem 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, LightMemConfig):
        raise ConfigurationError("LightMem worker getter requires LightMemConfig")
    return config.max_workers


def _lightmem_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 LightMem efficiency observation 会引用的模型身份。"""

    if not isinstance(config, LightMemConfig):
        raise ConfigurationError(
            "LightMem model inventory getter requires LightMemConfig"
        )
    return (
        ModelDescriptor(
            model_id="lightmem-memory-llm",
            model_name=config.llm_model,
            model_role="memory_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="lightmem-answer-llm",
            model_name=config.llm_model,
            model_role="answer_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="lightmem-embedding",
            model_name=config.embedding_model_path,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model_path,
            embedding_dimension=config.embedding_dimensions,
            tokenizer_name=config.embedding_model_path,
        ),
    )


def _lightmem_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 LightMem 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, LightMemConfig):
        raise ConfigurationError(
            "LightMem instrumentation identity getter requires LightMemConfig"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/lightmem_adapter.py")
    return {
        "collector_schema": 1,
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": config.embedding_model_path,
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _mem0_max_workers(config: Any) -> int:
    """从 Mem0 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, Mem0Config):
        raise ConfigurationError("Mem0 worker getter requires Mem0Config")
    return config.max_workers


def _mem0_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 Mem0 efficiency observation 会引用的模型身份。"""

    if not isinstance(config, Mem0Config):
        raise ConfigurationError("Mem0 model inventory getter requires Mem0Config")
    return (
        ModelDescriptor(
            model_id="mem0-memory-llm",
            model_name=config.extraction_model,
            model_role="memory_llm",
            execution_mode="api",
            tokenizer_name=config.extraction_model,
        ),
        ModelDescriptor(
            model_id="mem0-answer-llm",
            model_name=config.reader_model,
            model_role="answer_llm",
            execution_mode="api",
            tokenizer_name=config.reader_model,
        ),
        ModelDescriptor(
            model_id="mem0-embedding",
            model_name=config.embedding_model,
            model_role="embedding",
            execution_mode="api",
            embedding_dimension=config.embedding_dimensions,
            tokenizer_name=config.embedding_model,
        ),
    )


def _mem0_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 Mem0 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, Mem0Config):
        raise ConfigurationError(
            "Mem0 instrumentation identity getter requires Mem0Config"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/mem0_adapter.py")
    return {
        "collector_schema": 1,
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "extraction_llm_hook": "mem0-openai-response-callback",
        "embedding_hook": "wrapped-embedding-model-methods",
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _separable_retrieval_contract(config: Any) -> RetrievalObservationContract:
    """当前官方集成均声明可精确拆分 retrieval 边界。"""

    return RetrievalObservationContract(
        required_by_profile=True,
        supported_by_method=True,
    )


def _build_memoryos_system(context: MethodBuildContext) -> BaseMemorySystem:
    """根据统一 build context 构造 MemoryOS adapter，并恢复已完成 conversation。"""

    if not isinstance(context.config, MemoryOSPaperConfig):
        raise ConfigurationError("MemoryOS factory requires MemoryOSPaperConfig")
    if context.openai_settings is None:
        raise ConfigurationError("MemoryOS factory requires OpenAI settings")
    system = MemoryOS(
        openai_api_key=context.openai_settings.api_key,
        openai_base_url=context.openai_settings.base_url,
        storage_root=context.storage_root,
        config=context.config,
        efficiency_collector=context.efficiency_collector,
        # 按 benchmark 设消费粒度（与 LightMem/A-Mem 既有模式一致）：
        # LongMemEval 数据 role=user/assistant 适合 pair 聚合；LoCoMo 数据
        # role=speaker 名，pair 聚合失效，用 session 粒度由 adapter 内部按
        # speaker 配对成 add_memory。详见 plan-memoryos-migration.md T2。
        consume_granularity=(
            "pair" if context.benchmark_name == "longmemeval" else "session"
        ),
        benchmark_name=context.benchmark_name,
    )
    for conversation in context.completed_conversations:
        system.load_existing_conversation_state(conversation)
    return system


def _clean_amem_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 A-Mem 单个 failed_ingest conversation 的 method state。"""

    clean_amem_conversation_state(
        _resolve_clean_retry_storage_root(context, failed_state),
        conversation.conversation_id,
    )


def _clean_mem0_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 Mem0 failed_ingest namespace 的全部算法可见状态。"""

    storage_root = _resolve_clean_retry_storage_root(context, failed_state)
    clean_context = MethodBuildContext(
        config=context.config,
        openai_settings=context.openai_settings,
        path_settings=context.path_settings,
        storage_root=storage_root,
        benchmark_name=context.benchmark_name,
    )
    system = _build_mem0_system(clean_context)
    if not isinstance(system, Mem0):
        raise ConfigurationError("Mem0 clean hook failed to build Mem0 adapter")
    run_id = context.storage_root.parent.name
    isolation_key = f"{run_id}_{conversation.conversation_id}"
    system.clean_failed_ingest_state(isolation_key)


def _clean_lightmem_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 LightMem 单个 failed_ingest conversation 的 method state。"""

    clean_lightmem_conversation_state(
        _resolve_clean_retry_storage_root(context, failed_state),
        conversation.conversation_id,
    )


def _clean_memoryos_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 MemoryOS 单个 failed_ingest conversation 的 method state。"""

    clean_memoryos_conversation_state(
        _resolve_clean_retry_storage_root(context, failed_state),
        conversation.conversation_id,
    )


def _clean_simplemem_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 SimpleMem 单个 failed_ingest conversation 的 isolation 状态。"""

    clean_simplemem_conversation_state(
        _resolve_clean_retry_storage_root(context, failed_state),
        conversation.conversation_id,
    )


def _resolve_clean_retry_storage_root(
    context: MethodBuildContext,
    failed_state: dict[str, Any],
) -> Path:
    """根据失败 checkpoint 定位 clean retry 应清理的 method state 根目录。

    isolated worker 失败时 checkpoint 会记录 `worker_idx`，真实脏状态位于
    `method_state/worker_<idx>/`；非 isolated 路径没有该字段，直接使用 run 级
    `method_state/`。
    """

    worker_idx = failed_state.get("worker_idx")
    if isinstance(worker_idx, int) and not isinstance(worker_idx, bool):
        return context.storage_root / f"worker_{worker_idx}"
    return context.storage_root


def _memoryos_model_name(config: Any) -> str:
    """从 MemoryOS 强类型配置读取回答模型名。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError("MemoryOS model getter requires MemoryOSPaperConfig")
    return config.llm_model


def _memoryos_max_workers(config: Any) -> int:
    """从 MemoryOS 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError("MemoryOS worker getter requires MemoryOSPaperConfig")
    return config.max_workers


def _memoryos_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 MemoryOS efficiency observation 会引用的模型身份。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError(
            "MemoryOS model inventory getter requires MemoryOSPaperConfig"
        )
    return (
        ModelDescriptor(
            model_id="memoryos-chat-llm",
            model_name=config.llm_model,
            model_role="memory_answer_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="memoryos-embedding",
            model_name=config.embedding_model_name,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model_name,
        ),
    )


def _memoryos_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 MemoryOS 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError(
            "MemoryOS instrumentation identity getter requires MemoryOSPaperConfig"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/memoryos_adapter.py")
    return {
        "collector_schema": 1,
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": None,
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _estimate_memoryos_update_batches(
    conversation: Conversation,
    config: Any,
) -> int:
    """估算单个 conversation 在 MemoryOS add 阶段的 update batch 数。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError(
            "MemoryOS workload estimator requires MemoryOSPaperConfig"
        )
    return MemoryOS.estimate_add_workload(
        conversation,
        config,
    ).update_batch_count


def _mem0_embedding_identity(
    config_manifest: dict[str, Any],
) -> tuple[str | None, str | None, int | None, str | None] | None:
    """从 Mem0 config manifest 抽取当前 build 的 embedding 身份四元组。

    Mem0 ``to_manifest`` 暴露 ``embedding_provider``、``embedding_model``、
    ``embedding_dimensions``；revision 由 provider 管理（HuggingFace local 时无 pin），
    本 getter 返回 None，由 config_track 按静态期望标 ``local_unpinned``。
    """

    if not isinstance(config_manifest, dict):
        return None
    provider = config_manifest.get("embedding_provider")
    model = config_manifest.get("embedding_model")
    dimension = config_manifest.get("embedding_dimensions")
    return (
        str(provider) if provider is not None else None,
        str(model) if model is not None else None,
        int(dimension) if isinstance(dimension, int) else None,
        None,
    )


def _lightmem_embedding_identity(
    config_manifest: dict[str, Any],
) -> tuple[str | None, str | None, int | None, str | None] | None:
    """从 LightMem config manifest 抽取 embedding 身份四元组。

    LightMem ``to_manifest`` 暴露 ``embedding_provider``、``embedding_model_path``、
    ``embedding_dimensions``；provider 取为 manifest 的 ``embedding_provider``
    （HuggingFace local）。
    """

    if not isinstance(config_manifest, dict):
        return None
    provider = config_manifest.get("embedding_provider")
    model = config_manifest.get("embedding_model_path")
    dimension = config_manifest.get("embedding_dimensions")
    return (
        str(provider) if provider is not None else None,
        str(model) if model is not None else None,
        int(dimension) if isinstance(dimension, int) else None,
        None,
    )


def _memoryos_embedding_identity(
    config_manifest: dict[str, Any],
) -> tuple[str | None, str | None, int | None, str | None] | None:
    """从 MemoryOS config manifest 抽取 embedding 身份四元组。

    MemoryOS ``to_manifest`` 在 asdict 中暴露 ``embedding_model_name``；engine 字段
    ``memoryos-pypi`` 作为 provider 身份。维度为模型固有值（``all-MiniLM-L6-v2`` 恒为
    384，审计 §2.3 一手核），manifest 不直接写字段，故按当前注册的唯一模型名回填
    固有维度——这是与 ``method.config`` 同一真实值（模型名确定 queried 维度），不是
    提前写入未来配置。当 ``embedding_model_name`` 缺失时返回 None 表示 pending。
    """

    if not isinstance(config_manifest, dict):
        return None
    model = config_manifest.get("embedding_model_name")
    if not model:
        return None
    dimension: int | None = None
    normalized_model = str(model).split("/")[-1].lower()
    if "all-minilm-l6-v2" in normalized_model:
        dimension = 384
    return (
        str(config_manifest.get("engine") or "memoryos-pypi"),
        str(model),
        dimension,
        None,
    )


def _simplemem_embedding_identity(
    config_manifest: dict[str, Any],
) -> tuple[str | None, str | None, int | None, str | None] | None:
    """从 SimpleMem config manifest 抽取 embedding 身份四元组。

    SimpleMem ``to_manifest`` 暴露 ``embedding_model_path``、``embedding_dimension``，
    provider 记为 ``sentence-transformers-local``（与 to_manifest 一致）。
    """

    if not isinstance(config_manifest, dict):
        return None
    model = config_manifest.get("embedding_model_path")
    dimension = config_manifest.get("embedding_dimension")
    return (
        "sentence-transformers-local" if model else None,
        str(model) if model is not None else None,
        int(dimension) if isinstance(dimension, int) else None,
        None,
    )


def _generic_pending_embedding_identity(
    config_manifest: dict[str, Any],
) -> tuple[str | None, str | None, int | None, str | None] | None:
    """未裁 method（A-Mem）的 embedding identity getter：恒返回 None 表示 pending。

    A-Mem 的 product-default embedding 尚未一手核；在各自 M 阶段补完前不得臆造
    product identity，故统一返回 None，让 track identity 的 embedding identity_status
    为 pending（A-Mem/SimpleMem 不因同名 MiniLM 自动盖 product-default）。
    """

    return None


_REGISTRATIONS = {
    "amem": MethodRegistration(
        name="amem",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=(
            ("smoke", "smoke"),
            ("official-full", "official_full"),
        ),
        profile_relative_path=Path("configs/methods/amem.toml"),
        config_type=AMemConfig,
        requires_api=True,
        system_factory=_build_amem_system,
        source_identity_factory=build_amem_source_identity,
        model_name_getter=_amem_model_name,
        max_workers_getter=_amem_max_workers,
        display_name="A-Mem",
        protocol_version="v3",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_amem_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _amem_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        clean_failed_ingest_state=_clean_amem_failed_ingest_state,
        embedding_identity_getter=_generic_pending_embedding_identity,
    ),
    "mem0": MethodRegistration(
        name="mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=(
            ("smoke", "smoke"),
            ("official-full", "official_full"),
        ),
        profile_relative_path=Path("configs/methods/mem0.toml"),
        config_type=Mem0Config,
        requires_api=True,
        system_factory=_build_mem0_system,
        source_identity_factory=build_mem0_source_identity,
        model_name_getter=_mem0_model_name,
        max_workers_getter=_mem0_max_workers,
        display_name="Mem0",
        protocol_version="v3",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_mem0_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _mem0_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        provenance_granularity="turn",
        retrieval_evidence_contract_version="v1",
        clean_failed_ingest_state=_clean_mem0_failed_ingest_state,
        supports_shared_instance_parallelism=False,
        embedding_identity_getter=_mem0_embedding_identity,
    ),
    "lightmem": MethodRegistration(
        name="lightmem",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=(
            ("smoke", "smoke"),
            ("official-full", "official_full"),
        ),
        profile_relative_path=Path("configs/methods/lightmem.toml"),
        config_type=LightMemConfig,
        requires_api=True,
        system_factory=_build_lightmem_system,
        source_identity_factory=build_lightmem_source_identity,
        model_name_getter=_lightmem_model_name,
        max_workers_getter=_lightmem_max_workers,
        display_name="LightMem",
        protocol_version="v3",
        provenance_granularity="turn",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_lightmem_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _lightmem_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        clean_failed_ingest_state=_clean_lightmem_failed_ingest_state,
        embedding_identity_getter=_lightmem_embedding_identity,
    ),
    "memoryos": MethodRegistration(
        name="memoryos",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=(
            ("smoke", "smoke"),
            ("official-full", "official_full"),
        ),
        profile_relative_path=Path("configs/methods/memoryos.toml"),
        config_type=MemoryOSPaperConfig,
        requires_api=True,
        system_factory=_build_memoryos_system,
        source_identity_factory=build_memoryos_source_identity,
        model_name_getter=_memoryos_model_name,
        max_workers_getter=_memoryos_max_workers,
        display_name="MemoryOS",
        protocol_version="v3",
        provenance_granularity="turn",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=True,
        workload_estimator=_estimate_memoryos_update_batches,
        efficiency_model_inventory_getter=_memoryos_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _memoryos_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        clean_failed_ingest_state=_clean_memoryos_failed_ingest_state,
        embedding_identity_getter=_memoryos_embedding_identity,
    ),
    "simplemem": MethodRegistration(
        name="simplemem",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=(
            ("smoke", "smoke"),
            ("official-full", "official_full"),
        ),
        profile_relative_path=Path("configs/methods/simplemem.toml"),
        config_type=SimpleMemConfig,
        requires_api=True,
        system_factory=_build_simplemem_system,
        source_identity_factory=build_simplemem_source_identity,
        model_name_getter=_simplemem_model_name,
        max_workers_getter=_simplemem_max_workers,
        display_name="SimpleMem",
        protocol_version="v3",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_simplemem_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _simplemem_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        supports_shared_instance_parallelism=False,
        clean_failed_ingest_state=_clean_simplemem_failed_ingest_state,
        embedding_identity_getter=_simplemem_embedding_identity,
    ),
}


def list_methods() -> list[str]:
    """返回统一入口当前支持的 method 名称。"""

    return sorted(_REGISTRATIONS)


def get_method_registration(method_name: str) -> MethodRegistration:
    """读取 method 注册信息，未知名称时给出支持列表。"""

    try:
        return _REGISTRATIONS[method_name]
    except KeyError as exc:
        supported = ", ".join(list_methods())
        raise ConfigurationError(
            f"Unknown method '{method_name}'. Supported: {supported}"
        ) from exc


def resolve_registered_factory_provenance_granularity(
    system_factory: Callable[[MethodBuildContext], BaseMemorySystem],
) -> str | None:
    """按注册 factory 身份返回静态 provenance 粒度，未注册时返回 None。"""

    for registration in _REGISTRATIONS.values():
        if registration.system_factory is system_factory:
            return registration.provenance_granularity
    return None


def resolve_registered_factory_retrieval_evidence_contract_version(
    system_factory: Callable[[MethodBuildContext], BaseMemorySystem],
) -> str | None:
    """按注册 factory 身份返回逐题 retrieval evidence 契约版本，未注册时返回 None。

    该解析与 `resolve_registered_factory_provenance_granularity` 同构：只靠
    `system_factory` 身份匹配，无需构造真实 method 实例，因此 workers>1 的根进程也能
    在不实例化 method 的前提下为 manifest 盖章。
    """

    for registration in _REGISTRATIONS.values():
        if registration.system_factory is system_factory:
            return registration.retrieval_evidence_contract_version
    return None


def resolve_registered_embedding_identity(
    method_name: str,
    config_manifest: dict[str, Any],
) -> tuple[str | None, str | None, int | None, str | None] | None:
    """按注册方法名从 config manifest 抽取当前 build 的 embedding 身份四元组。

    输入:
        method_name: method registry 名。
        config_manifest: ``method.config.to_manifest()`` 产生的公开配置字典。

    输出:
        ``(provider, model, dimension, revision)``；method 未声明 getter 时返回 None
        （表示 pending）。值必须与 ``method.config`` 同一真实值，不得提前写入未来
        配置（如 Mem0 未来 OpenAI/1536 不得写进当前 MiniLM run）。
    """

    registration = _REGISTRATIONS.get(method_name.strip().lower())
    if registration is None or registration.embedding_identity_getter is None:
        return None
    return registration.embedding_identity_getter(config_manifest)


def load_method_profile(
    method_name: str,
    profile_name: str,
    project_root: str | Path | None = None,
) -> Any:
    """从 method 的 TOML 文件构造强类型 profile。

    输入:
        method_name: registry 中的 method 名称。
        profile_name: TOML section 名称。
        project_root: 用于定位 `configs/` 的项目根目录。

    输出:
        Any: registration 声明的强类型 method 配置实例。
    """

    registration = get_method_registration(method_name)
    root = load_path_settings(project_root).project_root
    section_name = registration.resolve_profile_section(profile_name)
    return load_typed_profile(
        root / registration.profile_relative_path,
        section_name,
        registration.config_type,
    )


def _sha256_file(path: Path) -> str:
    """计算文件 SHA-256，用于 wrapper 插桩身份。"""

    if not path.is_file():
        raise ConfigurationError(f"Instrumentation wrapper file missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "MethodBuildContext",
    "MethodRegistration",
    "get_method_registration",
    "list_methods",
    "load_method_profile",
    "resolve_registered_factory_provenance_granularity",
    "resolve_registered_factory_retrieval_evidence_contract_version",
    "resolve_registered_embedding_identity",
]

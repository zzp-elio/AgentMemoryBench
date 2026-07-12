"""通用 prediction runner 的命令行装配入口。

当前入口先支持本地 OSS Mem0 + LoCoMo。它只选择 benchmark adapter、method adapter、
运行 profile 和标准输出目录，不复制 Mem0 算法、LoCoMo 转换或 runner 调度逻辑。
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    RunScope,
    get_benchmark_registration,
    resolve_variant_selector,
)
from memory_benchmark.benchmark_adapters.contracts import (
    normalize_variant_run_id_token,
)
from memory_benchmark.config.settings import (
    AnswerLLMSettings,
    DEFAULT_OPENAI_MODEL,
    load_openai_settings,
    load_path_settings,
    resolve_answer_llm_settings,
)
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    Conversation,
    MethodCapability,
    Question,
    validate_compatibility,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider, BaseMemorySystem
from memory_benchmark.core.provider_protocol import MemoryProvider
from memory_benchmark.methods.custom_loader import load_custom_memory_provider
from memory_benchmark.methods.config_track import resolve_config_track
from memory_benchmark.methods.mem0_adapter import Mem0Config
from memory_benchmark.methods.registry import (
    MethodBuildContext,
    get_method_registration,
    load_method_profile,
)
from memory_benchmark.observability import RunContext
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    ModelDescriptor,
    RetrievalObservationContract,
)
from memory_benchmark.readers import (
    FrameworkAnswerReader,
    OpenAICompatibleAnswerLLMClient,
    load_answer_prompt_template,
)
from memory_benchmark.runners.conversation_qa import _make_public_conversation
from memory_benchmark.runners.ingest_resume import (
    load_completed_conversation_ids,
)
from memory_benchmark.runners.operation_level import run_operation_level_predictions
from memory_benchmark.runners.prediction import (
    PredictionRunPolicy,
    PredictionRunSummary,
    _preflight_prediction_run,
    run_predictions,
)


SUPPORTED_BENCHMARK = "locomo"
SUPPORTED_METHOD = "mem0"
DEFAULT_SMOKE_TURN_LIMIT = 20
MAX_SMOKE_WORKERS = 10


@dataclass(frozen=True)
class PredictionVariantResult:
    """单个 concrete variant child run 的执行结果。"""

    variant: str
    run_id: str
    summary: PredictionRunSummary


@dataclass(frozen=True)
class PredictionBatchResult:
    """一次 registered prediction 调用返回的批次结果。"""

    benchmark: str
    selector: str
    runs: tuple[PredictionVariantResult, ...]


def _bind_clean_failed_ingest_conversation(
    *,
    method_registration: object,
    build_context: MethodBuildContext,
) -> Callable[[Conversation, dict[str, object]], None] | None:
    """把内置 method 的 clean retry hook 绑定到当前 child run 上下文。

    输入:
        method_registration: registry 中的 method 静态信息。用户自定义 method 没有
            该字段时返回 None。
        build_context: 当前 child run 的 method 构造上下文，含 method state 根目录。

    输出:
        Callable | None: runner 可直接调用的 clean hook。None 表示不支持
        failed_ingest clean retry，应保持 fail-closed。
    """

    clean_failed_ingest_state = getattr(
        method_registration,
        "clean_failed_ingest_state",
        None,
    )
    if clean_failed_ingest_state is None:
        return None

    def _clean_failed_ingest_conversation(
        conversation: Conversation,
        failed_state: dict[str, object],
    ) -> None:
        """用当前 child run 上下文清理一个 failed_ingest conversation。"""

        clean_failed_ingest_state(build_context, conversation, failed_state)

    return _clean_failed_ingest_conversation


class _UnusedRootSystem(BaseMemorySystem):
    """isolated worker path 的根 system 占位对象。

    registered runner 在 isolated path 中只需要 worker 内的 method instance。这个占位
    对象避免提前构造第三方 method，从而避免顶层 method_state 副作用。
    """

    def add(self, conversations: list[Conversation]) -> AddResult:
        """isolated path 不应调用根 system add。"""

        raise ConfigurationError("isolated root system must not be used for add")

    def get_answer(self, question: Question) -> AnswerResult:
        """isolated path 不应调用根 system get_answer。"""

        raise ConfigurationError(
            "isolated root system must not be used for get_answer"
        )


@dataclass(frozen=True)
class _PreparedPredictionChild:
    """单个 child run 在执行前的不可变装配结果。"""

    variant: str
    run_scope: RunScope
    dataset: object
    run_id: str
    run_context: RunContext
    policy: PredictionRunPolicy
    method_manifest: dict[str, object]
    benchmark_policy: dict[str, object] | None
    source_paths: tuple[Path, ...]
    efficiency_collector: EfficiencyCollector | None = None
    model_inventory: tuple[ModelDescriptor, ...] = ()
    instrumentation_identity: dict[str, object] | None = None
    retrieval_observation_contract: RetrievalObservationContract | None = None


def resolve_mem0_profile(
    profile_name: str,
    confirm_api: bool,
    confirm_full: bool,
    project_root: str | Path | None = None,
) -> Mem0Config:
    """解析 Mem0 profile 并执行真实 API 成本保护。

    输入:
        profile_name: `smoke` 或 `official-full`。
        confirm_api: 是否明确允许 extraction、embedding 和 reader API 调用。
        confirm_full: 是否额外明确允许 LoCoMo 全量调用。
        project_root: 用于定位 `configs/methods/mem0.toml` 的项目根目录。

    输出:
        Mem0Config: 已锁定的 smoke 或官方全量参数。
    """

    if not confirm_api:
        raise ConfigurationError(
            "Real Mem0 prediction requires --confirm-api because extraction, "
            "embedding and reader use paid API calls"
        )
    if profile_name == "official-full":
        if not confirm_full:
            raise ConfigurationError(
                "Mem0 official-full requires --confirm-full in addition to --confirm-api"
            )

    return load_method_profile(
        method_name=SUPPORTED_METHOD,
        profile_name=profile_name,
        project_root=project_root,
    )


def resolve_prediction_max_workers(
    config: Mem0Config,
    smoke_max_workers: int | None,
) -> int:
    """解析 runner 并发数，并阻止 smoke 覆盖污染官方全量 profile。

    输入:
        config: 已确认的 Mem0 smoke 或 official-full profile。
        smoke_max_workers: 可选 smoke 并发覆盖，最多允许 10。

    输出:
        int: 传给通用 prediction runner 的 conversation worker 数。
    """

    if smoke_max_workers is None:
        return config.max_workers
    if config.profile_name != "smoke":
        raise ConfigurationError(
            "smoke_max_workers is a smoke-only diagnostic option"
        )
    if smoke_max_workers < 1:
        raise ConfigurationError("Mem0 smoke_max_workers must be at least 1")
    if smoke_max_workers > MAX_SMOKE_WORKERS:
        raise ConfigurationError(
            f"Mem0 smoke_max_workers must be at most {MAX_SMOKE_WORKERS}"
        )
    return smoke_max_workers


def run_registered_conversation_qa_prediction(
    project_root: str | Path,
    method_name: str | None,
    benchmark_name: str,
    profile_name: str = "smoke",
    config_track: str = "unified",
    method_class: str | None = None,
    allow_unsafe_custom_parallel: bool = False,
    variant: str | None = None,
    run_id: str | None = None,
    resume: bool = False,
    confirm_api: bool = False,
    confirm_full: bool = False,
    smoke_turn_limit: int = DEFAULT_SMOKE_TURN_LIMIT,
    smoke_round_limit: int | None = None,
    smoke_conversation_limit: int = 1,
    smoke_session_limit: int | None = None,
    smoke_max_workers: int | None = None,
    max_new_conversations: int | None = None,
    retry_failed_conversations: bool = False,
    question_limit_per_conversation: int | None = None,
    enable_efficiency_observability: bool = True,
    answer_prompt_file: str | Path | None = None,
    answer_prompt_profile: str = "default",
    progress_enabled: bool = True,
    output_layout: str = "flat",
    membench_sources: tuple[str, ...] = (),
) -> PredictionBatchResult:
    """通过 benchmark/method registration 运行 conversation-QA prediction。

    输入:
        project_root: 项目根目录。
        method_name: method registry 中的稳定名称。
        benchmark_name: benchmark registry 中的稳定名称。
        profile_name: `smoke` 或 `official-full`。
        config_track: `unified` 保持框架默认；`native` 使用已注册 method 论文配置。
        variant: 可选 benchmark variant selector；为空时使用 registration 默认值。
        run_id: 可选稳定运行 id；resume 时必须传显式 base run_id。
        resume: 是否复用兼容 manifest/checkpoint 和 Mem0 method state。
        confirm_api: 是否允许真实付费 API 调用。
        confirm_full: 是否额外允许全量实验。
        smoke_turn_limit: smoke 最多写入的历史 turn 数。
        smoke_round_limit: CLI v2 smoke 的历史 round 上限；为空时沿用 legacy
            `smoke_turn_limit` 语义。
        smoke_conversation_limit: smoke 选择 1 或 2 个 conversation。
        smoke_max_workers: smoke runner 的可选并发覆盖，最多为 10。
        max_new_conversations: 本次命令最多推进多少个未完成 conversation；它只属于
            当前命令预算，不属于实验 identity。
        retry_failed_conversations: 是否重试 checkpoint 中已标记 failed 的 conversation；
            默认 False，避免失败项在 resume 时反复触发付费调用。
        question_limit_per_conversation: 本次命令每个 conversation 最多回答的问题数；
            为空时 smoke 默认 1 题，full 默认全部题。
        enable_efficiency_observability: 是否写入效率观测原始 artifact。
        answer_prompt_file: retrieve-first framework reader 的可选自定义 prompt 文件。
        answer_prompt_profile: retrieve-first framework reader 的 prompt profile 名称。
        progress_enabled: 是否在终端渲染 Rich 进度条；并行校准模式下应关闭。
        output_layout: 输出目录布局；`flat` 保持 legacy `outputs/{run_id}`，
            `hierarchical` 使用 `outputs/runs/{method}/{benchmark}/.../{run_id}`。

    输出:
        PredictionBatchResult: 按 concrete variant 拆开的 child run 结果。
    """

    root = Path(project_root).expanduser().resolve()
    path_settings = load_path_settings(project_root=root)
    benchmark_registration = get_benchmark_registration(benchmark_name)
    if bool(method_name) == bool(method_class):
        raise ConfigurationError("Pass exactly one of method_name or method_class")
    if method_class is not None:
        if config_track != "unified":
            raise ConfigurationError(
                "Custom methods do not have registered native config-track bundles"
            )
        return _run_custom_conversation_qa_prediction(
            project_root=root,
            path_settings=path_settings,
            benchmark_registration=benchmark_registration,
            benchmark_name=benchmark_name,
            profile_name=profile_name,
            method_class=method_class,
            allow_unsafe_custom_parallel=allow_unsafe_custom_parallel,
            variant=variant,
            run_id=run_id,
            resume=resume,
            confirm_api=confirm_api,
            confirm_full=confirm_full,
            smoke_turn_limit=smoke_turn_limit,
            smoke_round_limit=smoke_round_limit,
            smoke_conversation_limit=smoke_conversation_limit,
            smoke_session_limit=smoke_session_limit,
            smoke_max_workers=smoke_max_workers,
            max_new_conversations=max_new_conversations,
            retry_failed_conversations=retry_failed_conversations,
            question_limit_per_conversation=question_limit_per_conversation,
            enable_efficiency_observability=enable_efficiency_observability,
            answer_prompt_file=answer_prompt_file,
            answer_prompt_profile=answer_prompt_profile,
            progress_enabled=progress_enabled,
            output_layout=output_layout,
        )
    if method_name is None:
        raise ConfigurationError("method_name is required")
    method_registration = get_method_registration(method_name)
    config_track_bundle = (
        None
        if config_track == "unified"
        else resolve_config_track(method_name, benchmark_name, config_track)
    )
    if not benchmark_registration.prediction_enabled:
        raise ConfigurationError(
            f"Benchmark '{benchmark_name}' prediction is not enabled"
        )
    validate_compatibility(
        benchmark_task_family=benchmark_registration.task_family,
        required_capabilities=benchmark_registration.required_capabilities,
        method_task_families=method_registration.task_families,
        provided_capabilities=method_registration.provided_capabilities,
    )
    method_registration.resolve_profile_section(profile_name)
    _confirm_prediction_cost(
        method_display_name=method_registration.display_name,
        profile_name=profile_name,
        requires_api=method_registration.requires_api,
        confirm_api=confirm_api,
        confirm_full=confirm_full,
    )
    if resume and run_id is None:
        raise ConfigurationError(
            f"{method_name} resume requires an explicit existing run_id"
        )
    config = load_method_profile(
        method_name=method_name,
        profile_name=profile_name,
        project_root=path_settings.project_root,
    )
    run_scope = _resolve_profile_run_scope(config.profile_name)
    selector = variant or benchmark_registration.default_variant
    selected_variants = resolve_variant_selector(benchmark_registration, variant)
    selected_run_ids = _resolve_batch_run_ids(
        method_name=method_name,
        benchmark_name=benchmark_name,
        profile_name=config.profile_name,
        explicit_base_run_id=run_id,
        variants=selected_variants,
        registration=benchmark_registration,
    )
    multi_variant_registration = len(benchmark_registration.variant_names()) > 1
    selected_output_roots = tuple(
        _resolve_child_output_root(
            outputs_root=path_settings.outputs_root,
            method_name=method_name,
            benchmark_name=benchmark_name,
            profile_name=config.profile_name,
            variant=concrete_variant,
            multi_variant_registration=multi_variant_registration,
            output_layout=output_layout,
        )
        for concrete_variant in selected_variants
    )
    _validate_child_run_destinations(
        path_settings.outputs_root,
        tuple(
            output_root / selected_run_id
            for output_root, selected_run_id in zip(
                selected_output_roots,
                selected_run_ids,
                strict=True,
            )
        ),
    )
    source_identity = method_registration.source_identity_factory(path_settings)
    max_workers = method_registration.max_workers_getter(config)
    max_workers = _resolve_smoke_max_workers(
        method_display_name=method_registration.display_name,
        profile_name=config.profile_name,
        smoke_max_workers=smoke_max_workers,
        configured_max_workers=max_workers,
        allow_override=method_registration.allow_smoke_worker_override,
    )
    use_framework_answer_reader = (
        MethodCapability.MEMORY_RETRIEVAL
        in method_registration.provided_capabilities
    )
    prompt_track = (
        getattr(benchmark_registration, "prompt_track", "native")
        if use_framework_answer_reader
        else "native"
    )
    answer_llm_settings = (
        config_track_bundle.answer_llm_settings
        if config_track_bundle is not None
        else resolve_answer_llm_settings(
            method_name=method_registration.name,
            benchmark_name=benchmark_registration.name,
            model=DEFAULT_OPENAI_MODEL,
        )
        if use_framework_answer_reader
        else None
    )
    answer_reader_manifest = (
        _build_answer_reader_manifest(
            project_root=path_settings.project_root,
            prompt_file=answer_prompt_file,
            profile_name=answer_prompt_profile,
            answer_settings=answer_llm_settings,
        )
        if use_framework_answer_reader
        else None
    )
    benchmark_policy_manifest = _build_benchmark_policy_manifest(benchmark_registration)
    children: list[_PreparedPredictionChild] = []
    for concrete_variant, selected_run_id, selected_output_root in zip(
        selected_variants,
        selected_run_ids,
        selected_output_roots,
        strict=True,
    ):
        prepared = benchmark_registration.prepare(
            path_settings.project_root,
            BenchmarkLoadRequest(
                variant=concrete_variant,
                run_scope=run_scope,
                smoke_turn_limit=_resolve_adapter_smoke_history_limit(
                    benchmark_name=benchmark_name,
                    smoke_turn_limit=smoke_turn_limit,
                    smoke_round_limit=smoke_round_limit,
                ),
                smoke_conversation_limit=smoke_conversation_limit,
                smoke_session_limit=_resolve_adapter_smoke_session_limit(
                    benchmark_name=benchmark_name,
                    smoke_session_limit=smoke_session_limit,
                    smoke_round_limit=smoke_round_limit,
                ),
                membench_sources=membench_sources,
            ),
        )
        workload_estimate = _estimate_method_workload(
            method_registration=method_registration,
            dataset=prepared.dataset,
            config=config,
        )
        method_manifest = _build_method_manifest(
            config_manifest=config.to_manifest(),
            source_identity=source_identity,
            workload_estimate=workload_estimate,
            answer_reader_manifest=answer_reader_manifest,
            prompt_track=(
                "native"
                if config_track_bundle is not None
                else prompt_track
                if use_framework_answer_reader and prompt_track == "unified"
                else None
            ),
            config_track=("native" if config_track_bundle is not None else None),
        )
        policy = PredictionRunPolicy(
            max_workers=max_workers,
            question_limit_per_conversation=_question_limit_for_scope(
                run_scope,
                explicit_limit=question_limit_per_conversation,
            ),
            resume=resume,
            max_new_conversations=max_new_conversations,
            retry_failed_conversations=retry_failed_conversations,
            progress_enabled=progress_enabled,
        )
        run_context = RunContext.create(
            run_id=selected_run_id,
            benchmark_name=benchmark_name,
            method_name=method_registration.display_name,
            model_name=method_registration.model_name_getter(config),
            output_root=selected_output_root,
            resume=resume,
            ensure_directories=False,
        )
        (
            efficiency_collector,
            model_inventory,
            instrumentation_identity,
            retrieval_observation_contract,
        ) = _build_efficiency_observability_dependencies(
            enabled=enable_efficiency_observability,
            method_registration=method_registration,
            config=config,
            path_settings=path_settings,
            source_identity=source_identity,
            run_id=selected_run_id,
        )
        if use_framework_answer_reader and enable_efficiency_observability:
            model_inventory = _append_framework_answer_model_inventory(
                model_inventory,
                answer_settings=answer_llm_settings,
            )
        children.append(
            _PreparedPredictionChild(
                variant=prepared.variant,
                run_scope=prepared.run_scope,
                dataset=prepared.dataset,
                run_id=selected_run_id,
                run_context=run_context,
                policy=policy,
                method_manifest=method_manifest,
                benchmark_policy=benchmark_policy_manifest,
                source_paths=tuple(
                    path_settings.project_root / relative_path
                    for relative_path in prepared.source_relative_paths
                ),
                efficiency_collector=efficiency_collector,
                model_inventory=model_inventory,
                instrumentation_identity=instrumentation_identity,
                retrieval_observation_contract=retrieval_observation_contract,
            )
        )

    for child in children:
        if not getattr(benchmark_registration, "operation_level", False):
            _preflight_prediction_run(
                dataset=child.dataset,
                run_context=child.run_context,
                policy=child.policy,
                method_manifest=child.method_manifest,
                benchmark_policy=child.benchmark_policy,
                benchmark_variant=child.variant,
                run_scope=child.run_scope,
                source_paths=child.source_paths,
                efficiency_collector=child.efficiency_collector,
                model_inventory=child.model_inventory,
                instrumentation_identity=child.instrumentation_identity,
                retrieval_observation_contract=child.retrieval_observation_contract,
            )

    requires_openai_settings = (
        method_registration.requires_api or use_framework_answer_reader
    )
    openai_settings = (
        load_openai_settings(project_root=path_settings.project_root)
        if requires_openai_settings
        else None
    )
    answer_reader = None
    if use_framework_answer_reader:
        if openai_settings is None:
            raise ConfigurationError(
                "Framework answer reader requires OpenAI-compatible settings"
            )
        if openai_settings.model != DEFAULT_OPENAI_MODEL:
            raise ConfigurationError(
                "Framework answer reader currently requires model "
                f"{DEFAULT_OPENAI_MODEL}; got {openai_settings.model}"
            )
        if answer_llm_settings is None:
            raise ConfigurationError("Framework answer reader settings are missing")
        answer_reader = FrameworkAnswerReader(
            client=OpenAICompatibleAnswerLLMClient(
                settings=openai_settings,
                answer_settings=answer_llm_settings,
            ),
            prompt_template=load_answer_prompt_template(
                project_root=path_settings.project_root,
                prompt_file=answer_prompt_file,
                profile_name=answer_prompt_profile,
            ),
        )
    results: list[PredictionVariantResult] = []
    for child in children:
        child.run_context.ensure_directories()
        completed_conversation_ids = (
            load_completed_conversation_ids(
                child.run_context.run_dir,
                conversations=child.dataset.conversations,
            )
            if resume
            else set()
        )
        completed_conversations = tuple(
            _make_public_conversation(conversation)
            for conversation in child.dataset.conversations
            if conversation.conversation_id in completed_conversation_ids
        )
        build_context = MethodBuildContext(
            config=config,
            openai_settings=openai_settings,
            path_settings=path_settings,
            storage_root=child.run_context.method_state_dir,
            benchmark_name=benchmark_name,
            completed_conversations=completed_conversations,
            efficiency_collector=child.efficiency_collector,
        )
        clean_failed_ingest_conversation = _bind_clean_failed_ingest_conversation(
            method_registration=method_registration,
            build_context=build_context,
        )
        supports_shared_instance_parallelism = getattr(
            method_registration,
            "supports_shared_instance_parallelism",
            False,
        )
        use_isolated_worker_instances = (
            child.policy.max_workers > 1
            and not supports_shared_instance_parallelism
        )
        system: BaseMemorySystem = (
            _UnusedRootSystem()
            if use_isolated_worker_instances
            else method_registration.system_factory(build_context)
        )
        if getattr(benchmark_registration, "operation_level", False):
            if use_isolated_worker_instances:
                raise ConfigurationError(
                    "operation-level prediction currently requires max_workers=1"
                )
            if not isinstance(system, MemoryProvider):
                raise ConfigurationError(
                    "operation-level prediction requires a protocol v3 MemoryProvider"
                )
            if answer_reader is None:
                raise ConfigurationError(
                    "operation-level prediction requires framework answer reader"
                )
            unified_prompt_builder = getattr(
                benchmark_registration,
                "unified_prompt_builder",
                None,
            )
            if unified_prompt_builder is None:
                raise ConfigurationError(
                    "operation-level prediction requires unified_prompt_builder"
                )
            summary = run_operation_level_predictions(
                dataset=child.dataset,
                provider=system,
                run_context=child.run_context,
                policy=child.policy,
                method_manifest=child.method_manifest,
                benchmark_variant=child.variant,
                run_scope=child.run_scope,
                source_paths=child.source_paths,
                answer_reader=answer_reader,
                unified_prompt_builder=unified_prompt_builder,
                efficiency_collector=child.efficiency_collector,
                model_inventory=child.model_inventory,
                instrumentation_identity=child.instrumentation_identity,
            )
        else:
            summary = run_predictions(
                dataset=child.dataset,
                system=system,
                run_context=child.run_context,
                policy=child.policy,
                method_manifest=child.method_manifest,
                benchmark_policy=child.benchmark_policy,
                benchmark_variant=child.variant,
                run_scope=child.run_scope,
                source_paths=child.source_paths,
                efficiency_collector=child.efficiency_collector,
                model_inventory=child.model_inventory,
                instrumentation_identity=child.instrumentation_identity,
                retrieval_observation_contract=child.retrieval_observation_contract,
                system_factory=method_registration.system_factory,
                build_context_template=build_context,
                supports_shared_instance_parallelism=supports_shared_instance_parallelism,
                answer_reader=answer_reader,
                unified_prompt_builder=getattr(
                    benchmark_registration, "unified_prompt_builder", None
                )
                if config_track_bundle is None
                else None,
                prediction_transform=getattr(
                    benchmark_registration,
                    "prediction_transform",
                    None,
                ),
                protocol_version=getattr(
                    method_registration, "protocol_version", ""
                ),
                clean_failed_ingest_conversation=clean_failed_ingest_conversation,
            )
        results.append(
            PredictionVariantResult(
                variant=child.variant,
                run_id=child.run_id,
                summary=summary,
            )
        )

    return PredictionBatchResult(
        benchmark=benchmark_name,
        selector=selector,
        runs=tuple(results),
    )


def _run_custom_conversation_qa_prediction(
    *,
    project_root: Path,
    path_settings,
    benchmark_registration,
    benchmark_name: str,
    profile_name: str,
    method_class: str,
    allow_unsafe_custom_parallel: bool,
    variant: str | None,
    run_id: str | None,
    resume: bool,
    confirm_api: bool,
    confirm_full: bool,
    smoke_turn_limit: int,
    smoke_round_limit: int | None,
    smoke_conversation_limit: int,
    smoke_session_limit: int | None,
    smoke_max_workers: int | None,
    max_new_conversations: int | None,
    retry_failed_conversations: bool,
    question_limit_per_conversation: int | None,
    enable_efficiency_observability: bool,
    answer_prompt_file: str | Path | None,
    answer_prompt_profile: str,
    progress_enabled: bool,
    output_layout: str,
) -> PredictionBatchResult:
    """运行用户自定义 `BaseMemoryProvider` 的轻量 prediction 路径。

    该路径刻意绕开内置 method registry、TOML profile 和 source identity。用户只需
    提供无参构造的 `BaseMemoryProvider` 子类；framework 负责 benchmark 读取、answer
    LLM、artifact、resume 和基础效率观测。
    """

    if not benchmark_registration.prediction_enabled:
        raise ConfigurationError(
            f"Benchmark '{benchmark_name}' prediction is not enabled"
        )
    _confirm_prediction_cost(
        method_display_name=f"custom method '{method_class}'",
        profile_name=profile_name,
        requires_api=True,
        confirm_api=confirm_api,
        confirm_full=confirm_full,
    )
    if resume and run_id is None:
        raise ConfigurationError(
            "custom method resume requires an explicit existing run_id"
        )

    run_scope = _resolve_profile_run_scope(profile_name)
    selector = variant or benchmark_registration.default_variant
    selected_variants = resolve_variant_selector(benchmark_registration, variant)
    selected_run_ids = _resolve_batch_run_ids(
        method_name="custom",
        benchmark_name=benchmark_name,
        profile_name=profile_name,
        explicit_base_run_id=run_id,
        variants=selected_variants,
        registration=benchmark_registration,
    )
    multi_variant_registration = len(benchmark_registration.variant_names()) > 1
    selected_output_roots = tuple(
        _resolve_child_output_root(
            outputs_root=path_settings.outputs_root,
            method_name="custom",
            benchmark_name=benchmark_name,
            profile_name=profile_name,
            variant=concrete_variant,
            multi_variant_registration=multi_variant_registration,
            output_layout=output_layout,
        )
        for concrete_variant in selected_variants
    )
    _validate_child_run_destinations(
        path_settings.outputs_root,
        tuple(
            output_root / selected_run_id
            for output_root, selected_run_id in zip(
                selected_output_roots,
                selected_run_ids,
                strict=True,
            )
        ),
    )

    max_workers = _resolve_custom_max_workers(
        smoke_max_workers=smoke_max_workers,
        allow_unsafe_custom_parallel=allow_unsafe_custom_parallel,
    )
    answer_llm_settings = resolve_answer_llm_settings(
        method_name="custom",
        benchmark_name=benchmark_name,
        model=DEFAULT_OPENAI_MODEL,
    )
    answer_reader_manifest = _build_answer_reader_manifest(
        project_root=project_root,
        prompt_file=answer_prompt_file,
        profile_name=answer_prompt_profile,
        answer_settings=answer_llm_settings,
    )
    prompt_track = getattr(benchmark_registration, "prompt_track", "native")
    benchmark_policy_manifest = _build_benchmark_policy_manifest(benchmark_registration)

    children: list[_PreparedPredictionChild] = []
    for concrete_variant, selected_run_id, selected_output_root in zip(
        selected_variants,
        selected_run_ids,
        selected_output_roots,
        strict=True,
    ):
        prepared = benchmark_registration.prepare(
            path_settings.project_root,
            BenchmarkLoadRequest(
                variant=concrete_variant,
                run_scope=run_scope,
                smoke_turn_limit=_resolve_adapter_smoke_history_limit(
                    benchmark_name=benchmark_name,
                    smoke_turn_limit=smoke_turn_limit,
                    smoke_round_limit=smoke_round_limit,
                ),
                smoke_conversation_limit=smoke_conversation_limit,
                smoke_session_limit=_resolve_adapter_smoke_session_limit(
                    benchmark_name=benchmark_name,
                    smoke_session_limit=smoke_session_limit,
                    smoke_round_limit=smoke_round_limit,
                ),
                membench_sources=(),
            ),
        )
        method_manifest = _build_custom_method_manifest(
            method_class=method_class,
            answer_reader_manifest=answer_reader_manifest,
            allow_unsafe_custom_parallel=allow_unsafe_custom_parallel,
            prompt_track=prompt_track if prompt_track == "unified" else None,
        )
        policy = PredictionRunPolicy(
            max_workers=max_workers,
            question_limit_per_conversation=_question_limit_for_scope(
                run_scope,
                explicit_limit=question_limit_per_conversation,
            ),
            resume=resume,
            max_new_conversations=max_new_conversations,
            retry_failed_conversations=retry_failed_conversations,
            progress_enabled=progress_enabled,
        )
        run_context = RunContext.create(
            run_id=selected_run_id,
            benchmark_name=benchmark_name,
            method_name="CustomMethod",
            model_name=answer_llm_settings.model,
            output_root=selected_output_root,
            resume=resume,
            ensure_directories=False,
        )
        (
            efficiency_collector,
            model_inventory,
            instrumentation_identity,
            retrieval_observation_contract,
        ) = _build_custom_efficiency_dependencies(
            enabled=enable_efficiency_observability,
            method_class=method_class,
            answer_settings=answer_llm_settings,
            run_id=selected_run_id,
        )
        children.append(
            _PreparedPredictionChild(
                variant=prepared.variant,
                run_scope=prepared.run_scope,
                dataset=prepared.dataset,
                run_id=selected_run_id,
                run_context=run_context,
                policy=policy,
                method_manifest=method_manifest,
                benchmark_policy=benchmark_policy_manifest,
                source_paths=tuple(
                    path_settings.project_root / relative_path
                    for relative_path in prepared.source_relative_paths
                ),
                efficiency_collector=efficiency_collector,
                model_inventory=model_inventory,
                instrumentation_identity=instrumentation_identity,
                retrieval_observation_contract=retrieval_observation_contract,
            )
        )

    for child in children:
        _preflight_prediction_run(
            dataset=child.dataset,
            run_context=child.run_context,
            policy=child.policy,
            method_manifest=child.method_manifest,
            benchmark_policy=child.benchmark_policy,
            benchmark_variant=child.variant,
            run_scope=child.run_scope,
            source_paths=child.source_paths,
            efficiency_collector=child.efficiency_collector,
            model_inventory=child.model_inventory,
            instrumentation_identity=child.instrumentation_identity,
            retrieval_observation_contract=child.retrieval_observation_contract,
        )

    openai_settings = load_openai_settings(project_root=path_settings.project_root)
    if openai_settings.model != DEFAULT_OPENAI_MODEL:
        raise ConfigurationError(
            "Framework answer reader currently requires model "
            f"{DEFAULT_OPENAI_MODEL}; got {openai_settings.model}"
        )
    answer_reader = FrameworkAnswerReader(
        client=OpenAICompatibleAnswerLLMClient(
            settings=openai_settings,
            answer_settings=answer_llm_settings,
        ),
        prompt_template=load_answer_prompt_template(
            project_root=path_settings.project_root,
            prompt_file=answer_prompt_file,
            profile_name=answer_prompt_profile,
        ),
    )

    def build_custom_system(_context: MethodBuildContext) -> BaseMemoryProvider:
        """为 root 或 isolated worker 创建新的用户 provider 实例。"""

        return load_custom_memory_provider(method_class)

    results: list[PredictionVariantResult] = []
    for child in children:
        child.run_context.ensure_directories()
        completed_conversation_ids = (
            load_completed_conversation_ids(
                child.run_context.run_dir,
                conversations=child.dataset.conversations,
            )
            if resume
            else set()
        )
        completed_conversations = tuple(
            _make_public_conversation(conversation)
            for conversation in child.dataset.conversations
            if conversation.conversation_id in completed_conversation_ids
        )
        build_context = MethodBuildContext(
            config=None,
            openai_settings=openai_settings,
            path_settings=path_settings,
            storage_root=child.run_context.method_state_dir,
            completed_conversations=completed_conversations,
            efficiency_collector=child.efficiency_collector,
        )
        use_isolated_worker_instances = child.policy.max_workers > 1
        system: BaseMemorySystem | BaseMemoryProvider = (
            _UnusedRootSystem()
            if use_isolated_worker_instances
            else build_custom_system(build_context)
        )
        summary = run_predictions(
            dataset=child.dataset,
            system=system,
            run_context=child.run_context,
            policy=child.policy,
            method_manifest=child.method_manifest,
            benchmark_policy=child.benchmark_policy,
            benchmark_variant=child.variant,
            run_scope=child.run_scope,
            source_paths=child.source_paths,
            efficiency_collector=child.efficiency_collector,
            model_inventory=child.model_inventory,
            instrumentation_identity=child.instrumentation_identity,
            retrieval_observation_contract=child.retrieval_observation_contract,
            system_factory=build_custom_system,
            build_context_template=build_context,
            supports_shared_instance_parallelism=False,
            answer_reader=answer_reader,
            unified_prompt_builder=getattr(
                benchmark_registration,
                "unified_prompt_builder",
                None,
            ),
            prediction_transform=getattr(
                benchmark_registration,
                "prediction_transform",
                None,
            ),
            protocol_version="v2-bridged",
        )
        results.append(
            PredictionVariantResult(
                variant=child.variant,
                run_id=child.run_id,
                summary=summary,
            )
        )

    return PredictionBatchResult(
        benchmark=benchmark_name,
        selector=selector,
        runs=tuple(results),
    )


def _resolve_custom_max_workers(
    *,
    smoke_max_workers: int | None,
    allow_unsafe_custom_parallel: bool,
) -> int:
    """解析用户自定义 method 的 worker 数并执行 unsafe parallel 确认。"""

    max_workers = 1 if smoke_max_workers is None else smoke_max_workers
    if max_workers < 1:
        raise ConfigurationError("workers must be at least 1")
    if max_workers > MAX_SMOKE_WORKERS:
        raise ConfigurationError(f"workers must be at most {MAX_SMOKE_WORKERS}")
    if max_workers > 1 and not allow_unsafe_custom_parallel:
        raise ConfigurationError(
            "Custom method workers > 1 requires --allow-unsafe-custom-parallel"
        )
    return max_workers


def _build_custom_method_manifest(
    *,
    method_class: str,
    answer_reader_manifest: dict[str, object],
    allow_unsafe_custom_parallel: bool,
    prompt_track: str | None = None,
) -> dict[str, object]:
    """构造用户自定义 method 的公开 manifest。"""

    manifest: dict[str, object] = {
        "method_name": "custom",
        "method_class": method_class,
        "method_protocol": "BaseMemoryProvider",
        "integration_depth": "user_lightweight",
        "custom_method_contract": {
            "no_arg_constructor": True,
            "conversation_isolation_required": True,
            "parallel_requires_allow_unsafe_custom_parallel": True,
            "allow_unsafe_custom_parallel": allow_unsafe_custom_parallel,
        },
        "answer_reader": answer_reader_manifest,
    }
    if prompt_track is not None:
        manifest["prompt_track"] = prompt_track
    return manifest


def _build_custom_efficiency_dependencies(
    *,
    enabled: bool,
    method_class: str,
    answer_settings: AnswerLLMSettings,
    run_id: str,
) -> tuple[
    EfficiencyCollector | None,
    tuple[ModelDescriptor, ...],
    dict[str, object] | None,
    RetrievalObservationContract | None,
]:
    """为用户轻量接入路径构造框架可观测的最小 efficiency 依赖。"""

    if not enabled:
        return None, (), None, None
    return (
        EfficiencyCollector(run_id=run_id, enabled=True),
        (
            ModelDescriptor(
                model_id=answer_settings.model,
                model_name=answer_settings.model,
                model_role="answer_llm",
                execution_mode="api",
                tokenizer_name=answer_settings.model,
            ),
        ),
        {
            "collector_schema": 1,
            "integration_depth": "user_lightweight",
            "method_class": method_class,
            "framework_observed_only": True,
        },
        RetrievalObservationContract(
            required_by_profile=False,
            supported_by_method=True,
        ),
    )


def _build_efficiency_observability_dependencies(
    *,
    enabled: bool,
    method_registration,
    config,
    path_settings,
    source_identity: dict[str, object],
    run_id: str,
) -> tuple[
    EfficiencyCollector | None,
    tuple[ModelDescriptor, ...],
    dict[str, object] | None,
    RetrievalObservationContract | None,
]:
    """按 method registration 构造一次 child run 的效率观测依赖。"""

    if not enabled:
        return None, (), None, None
    if method_registration.efficiency_model_inventory_getter is None:
        raise ConfigurationError(
            f"{method_registration.display_name} does not provide efficiency "
            "model inventory"
        )
    if method_registration.efficiency_instrumentation_identity_getter is None:
        raise ConfigurationError(
            f"{method_registration.display_name} does not provide efficiency "
            "instrumentation identity"
        )
    if method_registration.retrieval_observation_contract_getter is None:
        raise ConfigurationError(
            f"{method_registration.display_name} does not provide retrieval "
            "observation contract"
        )
    collector = EfficiencyCollector(run_id=run_id, enabled=True)
    return (
        collector,
        method_registration.efficiency_model_inventory_getter(config),
        method_registration.efficiency_instrumentation_identity_getter(
            path_settings,
            config,
            source_identity,
        ),
        method_registration.retrieval_observation_contract_getter(config),
    )


def _append_framework_answer_model_inventory(
    model_inventory: tuple[ModelDescriptor, ...],
    *,
    answer_settings: AnswerLLMSettings | None,
) -> tuple[ModelDescriptor, ...]:
    """为 retrieve-first framework reader 追加 answer LLM 模型身份。"""

    if answer_settings is None:
        raise ConfigurationError("answer_settings is required for answer model inventory")
    if any(
        descriptor.model_id == answer_settings.model for descriptor in model_inventory
    ):
        return model_inventory
    return (
        *model_inventory,
        ModelDescriptor(
            model_id=answer_settings.model,
            model_name=answer_settings.model,
            model_role="answer_llm",
            execution_mode="api",
            tokenizer_name=answer_settings.model,
        ),
    )


def _resolve_profile_run_scope(profile_name: str) -> RunScope:
    """把 method profile 名映射为统一的 benchmark run scope。"""

    if profile_name == "smoke":
        return RunScope.SMOKE
    return RunScope.FULL


def _resolve_adapter_smoke_history_limit(
    *,
    benchmark_name: str,
    smoke_turn_limit: int,
    smoke_round_limit: int | None,
) -> int:
    """把 CLI smoke 历史预算转换成当前 adapter 的裁剪单位。

    legacy `predict --profile smoke` 路径按原有 turn 语义传递；CLI v2 `--rounds`
    使用 `smoke_round_limit`，LoCoMo 转成双 turn round，LongMemEval 已在
    adapter registry 内按完整 round 裁剪。
    """

    if smoke_round_limit is None:
        return smoke_turn_limit
    if smoke_round_limit < 1:
        raise ConfigurationError("rounds must be at least 1")
    if benchmark_name == "locomo":
        return smoke_round_limit * 2
    return smoke_round_limit


def _resolve_adapter_smoke_session_limit(
    *,
    benchmark_name: str,
    smoke_session_limit: int | None,
    smoke_round_limit: int | None,
) -> int | None:
    """拒绝 HaluMem 固定 smoke 的旧 session/round 裁剪轴。"""

    if benchmark_name == "halumem":
        if smoke_round_limit is not None:
            raise ConfigurationError("HaluMem smoke has a fixed shape")
        if smoke_session_limit is not None:
            raise ConfigurationError(
                "HaluMem smoke has a fixed shape and does not accept sessions"
            )
        return None
    if smoke_session_limit is not None:
        raise ConfigurationError("--sessions is only supported for HaluMem")
    return None


def _question_limit_for_scope(
    run_scope: RunScope,
    *,
    explicit_limit: int | None = None,
) -> int | None:
    """根据 run scope 和用户覆盖生成每 conversation 问题预算。"""

    if explicit_limit is not None:
        if explicit_limit < 1:
            raise ConfigurationError(
                "question_limit_per_conversation must be at least 1"
            )
        return explicit_limit
    if run_scope is RunScope.SMOKE:
        return 1
    return None


def _validate_child_run_destinations(
    outputs_root: str | Path,
    child_destinations: tuple[Path, ...],
) -> None:
    """在任何目录、secret 或 method 副作用前校验 child run 目标路径。"""

    canonical_outputs_root = Path(outputs_root).expanduser().resolve()
    seen_destinations: dict[str, Path] = {}
    for child_destination in child_destinations:
        canonical_destination = child_destination.resolve(strict=False)
        try:
            canonical_destination.relative_to(canonical_outputs_root)
        except ValueError as exc:
            raise ConfigurationError(
                f"child run destination '{child_destination}' resolves outside "
                f"outputs_root '{canonical_outputs_root}'"
            ) from exc
        destination_key = str(canonical_destination).casefold()
        existing_destination = seen_destinations.get(destination_key)
        if existing_destination is not None:
            raise ConfigurationError(
                "child run destinations must be unique after canonical and "
                "case-insensitive normalization: "
                f"'{existing_destination}' vs '{child_destination}'"
            )
        seen_destinations[destination_key] = child_destination


def _resolve_child_output_root(
    *,
    outputs_root: str | Path,
    method_name: str,
    benchmark_name: str,
    profile_name: str,
    variant: str,
    multi_variant_registration: bool,
    output_layout: str,
) -> Path:
    """根据 CLI 布局模式返回单个 child run 的 output_root。

    `RunContext.run_dir` 始终是 `output_root / run_id`。因此这里返回的是
    run_id 上一级目录，而不是最终 run 目录。
    """

    canonical_outputs_root = Path(outputs_root).expanduser().resolve()
    if output_layout == "flat":
        return canonical_outputs_root
    if output_layout != "hierarchical":
        raise ConfigurationError(
            f"Unknown prediction output_layout '{output_layout}'"
        )
    mode_directory = "smoke" if profile_name == "smoke" else "formal"
    path_parts = [
        canonical_outputs_root,
        Path("runs"),
        Path(method_name),
        Path(benchmark_name),
    ]
    if multi_variant_registration:
        path_parts.append(Path(normalize_variant_run_id_token(variant)))
    path_parts.append(Path(mode_directory))
    return Path(*path_parts).resolve()


def _resolve_batch_run_ids(
    *,
    method_name: str,
    benchmark_name: str,
    profile_name: str,
    explicit_base_run_id: str | None,
    variants: tuple[str, ...],
    registration,
) -> tuple[str, ...]:
    """为一批 concrete variants 生成稳定 child run_id。"""

    multi_variant_registration = len(registration.variant_names()) > 1
    if explicit_base_run_id is not None:
        base_run_id = _validate_explicit_base_run_id(explicit_base_run_id)
        if multi_variant_registration:
            _reject_registered_variant_suffix(
                base_run_id,
                registration.variant_names(),
            )
        run_ids = tuple(
            _build_explicit_child_run_id(
                base_run_id=base_run_id,
                variant=variant,
                multi_variant_registration=multi_variant_registration,
            )
            for variant in variants
        )
    else:
        run_ids = tuple(
            _build_automatic_child_run_id(
                method_name=method_name,
                benchmark_name=benchmark_name,
                profile_name=profile_name,
                variant=variant,
                multi_variant_registration=multi_variant_registration,
            )
            for variant in variants
        )
    if len(set(run_ids)) != len(run_ids):
        raise ConfigurationError(
            f"Duplicate child run_id generated for '{benchmark_name}': {run_ids}"
        )
    return run_ids


def _reject_registered_variant_suffix(
    base_run_id: str,
    registered_variants: tuple[str, ...],
) -> None:
    """拒绝已包含任一注册 variant 后缀的显式 base run_id。"""

    for registered_variant in registered_variants:
        variant_suffix = f"-{normalize_variant_run_id_token(registered_variant)}"
        if base_run_id.endswith(variant_suffix):
            raise ConfigurationError(
                f"Explicit run_id '{base_run_id}' already ends with registered "
                f"variant suffix '{variant_suffix}'"
            )


def _validate_explicit_base_run_id(run_id: str) -> str:
    """校验显式 base run_id 非空且不会逃逸输出目录。"""

    normalized_run_id = run_id.strip()
    if not normalized_run_id:
        raise ConfigurationError("run_id must not be blank")
    if normalized_run_id in {".", ".."}:
        raise ConfigurationError(f"run_id must not be unsafe: {run_id}")
    if "/" in normalized_run_id or "\\" in normalized_run_id:
        raise ConfigurationError(f"run_id must not contain path separators: {run_id}")
    if Path(normalized_run_id).is_absolute():
        raise ConfigurationError(f"run_id must not be an absolute path: {run_id}")
    return normalized_run_id


def _build_explicit_child_run_id(
    *,
    base_run_id: str,
    variant: str,
    multi_variant_registration: bool,
) -> str:
    """为显式 base run_id 生成一个 child run_id。"""

    if not multi_variant_registration:
        return base_run_id
    variant_suffix = f"-{normalize_variant_run_id_token(variant)}"
    if base_run_id.endswith(variant_suffix):
        raise ConfigurationError(
            f"Explicit run_id '{base_run_id}' already ends with variant suffix "
            f"'{variant_suffix}'"
        )
    return f"{base_run_id}{variant_suffix}"


def _build_automatic_child_run_id(
    *,
    method_name: str,
    benchmark_name: str,
    profile_name: str,
    variant: str,
    multi_variant_registration: bool,
) -> str:
    """为自动运行生成 child run_id。"""

    token = uuid4().hex[:8]
    if multi_variant_registration:
        return (
            f"{method_name}-{benchmark_name}-"
            f"{normalize_variant_run_id_token(variant)}-{profile_name}-{token}"
        )
    return f"{method_name}-{benchmark_name}-{profile_name}-{token}"


def _confirm_prediction_cost(
    *,
    method_display_name: str,
    profile_name: str,
    requires_api: bool,
    confirm_api: bool,
    confirm_full: bool,
) -> None:
    """在读取 secret 或构造 method 前校验真实 API 与全量成本确认。"""

    if requires_api and not confirm_api:
        raise ConfigurationError(
            f"Real {method_display_name} prediction requires --confirm-api"
        )
    if profile_name == "official-full" and not confirm_full:
        raise ConfigurationError(
            f"{method_display_name} official-full requires --confirm-full "
            "in addition to --confirm-api"
        )


def _resolve_smoke_max_workers(
    *,
    method_display_name: str,
    profile_name: str,
    smoke_max_workers: int | None,
    configured_max_workers: int,
    allow_override: bool,
) -> int:
    """校验用户传入的 conversation 并发覆盖。"""

    if smoke_max_workers is None:
        return configured_max_workers
    if not allow_override:
        raise ConfigurationError(
            f"{method_display_name} does not support --workers override"
        )
    if smoke_max_workers < 1:
        raise ConfigurationError("workers must be at least 1")
    if smoke_max_workers > MAX_SMOKE_WORKERS:
        raise ConfigurationError(
            f"workers must be at most {MAX_SMOKE_WORKERS}"
        )
    return smoke_max_workers


def _estimate_method_workload(
    *,
    method_registration,
    dataset,
    config,
) -> dict[str, object] | None:
    """使用 registration 提供的 hook 估算公开工作量。"""

    if method_registration.workload_estimator is None:
        return None
    total_update_batches = sum(
        method_registration.workload_estimator(
            _make_public_conversation(conversation),
            config,
        )
        for conversation in dataset.conversations
    )
    return {
        "kind": "memory_update_batches",
        "total_update_batches": total_update_batches,
        "conversation_count": len(dataset.conversations),
    }


def _build_benchmark_policy_manifest(
    benchmark_registration: object,
) -> dict[str, object] | None:
    """把已注册 benchmark 的 smoke/resume policy 转成可写入 manifest 的稳定字典。

    输入:
        benchmark_registration: 当前 benchmark 的静态注册声明。

    输出:
        dict | None: 尚未声明 policy 的 benchmark（B2-B5 待审计）返回 None，
        manifest 不新增字段，保持既有兼容路径；已注册的 benchmark（当前只有
        LoCoMo）返回稳定 `{"smoke": ..., "resume": ...}` 字典，供审计和 resume
        一致性检查复用，不再只存在于 CLI `--help` 文本里。
    """

    smoke_policy = getattr(benchmark_registration, "smoke_policy", None)
    resume_policy = getattr(benchmark_registration, "resume_policy", None)
    if smoke_policy is None and resume_policy is None:
        return None
    return {
        "smoke": None if smoke_policy is None else smoke_policy.to_dict(),
        "resume": None if resume_policy is None else resume_policy.to_dict(),
    }


def _build_method_manifest(
    *,
    config_manifest: dict[str, object],
    source_identity: dict[str, object],
    workload_estimate: dict[str, object] | None,
    answer_reader_manifest: dict[str, object] | None = None,
    prompt_track: str | None = None,
    config_track: str | None = None,
) -> dict[str, object]:
    """构造不含 secret 的 method manifest。"""

    manifest: dict[str, object] = {
        "config": config_manifest,
        "source": source_identity,
    }
    if answer_reader_manifest is not None:
        manifest["answer_reader"] = answer_reader_manifest
    if prompt_track is not None:
        manifest["prompt_track"] = prompt_track
    if config_track is not None:
        manifest["config_track"] = config_track
    if workload_estimate is not None:
        manifest["workload_estimate"] = workload_estimate
    return manifest


def _build_answer_reader_manifest(
    *,
    project_root: Path,
    prompt_file: str | Path | None,
    profile_name: str,
    answer_settings: AnswerLLMSettings | None,
) -> dict[str, object]:
    """构造 retrieve-first reader 的公开身份信息。

    该 manifest 只包含可公开复现实验身份的信息，不包含 API key、base URL 或 prompt 原文。
    """

    prompt_file_sha256 = None
    if prompt_file is not None:
        prompt_path = Path(prompt_file).expanduser()
        if not prompt_path.is_absolute():
            prompt_path = project_root / prompt_path
        prompt_file_sha256 = hashlib.sha256(prompt_path.read_bytes()).hexdigest()

    return {
        "answer_protocol": "retrieve_first_v1",
        "answer_prompt_profile": profile_name,
        "answer_prompt_file_sha256": prompt_file_sha256,
        "answer_model": None if answer_settings is None else answer_settings.model,
        "answer_parameters": (
            None if answer_settings is None else answer_settings.to_manifest_dict()
        ),
    }


def run_mem0_locomo_prediction(
    project_root: str | Path,
    profile_name: str = "smoke",
    run_id: str | None = None,
    resume: bool = False,
    confirm_api: bool = False,
    confirm_full: bool = False,
    smoke_turn_limit: int = DEFAULT_SMOKE_TURN_LIMIT,
    smoke_conversation_limit: int = 1,
    smoke_max_workers: int | None = None,
    max_new_conversations: int | None = None,
    question_limit_per_conversation: int | None = None,
) -> PredictionRunSummary:
    """兼容旧调用路径，转发到统一 registered prediction service。"""

    batch_result = run_registered_conversation_qa_prediction(
        project_root=project_root,
        method_name=SUPPORTED_METHOD,
        benchmark_name=SUPPORTED_BENCHMARK,
        profile_name=profile_name,
        run_id=run_id,
        resume=resume,
        confirm_api=confirm_api,
        confirm_full=confirm_full,
        smoke_turn_limit=smoke_turn_limit,
        smoke_conversation_limit=smoke_conversation_limit,
        smoke_max_workers=smoke_max_workers,
        max_new_conversations=max_new_conversations,
        question_limit_per_conversation=question_limit_per_conversation,
    )
    return batch_result.runs[0].summary


def main(argv: list[str] | None = None) -> int:
    """解析命令行并启动 Mem0-LoCoMo prediction run。"""

    parser = argparse.ArgumentParser(
        description="Generate LoCoMo answers with local OSS Mem0; metrics are not run.",
    )
    parser.add_argument("--root", default=".", help="Project root")
    parser.add_argument(
        "--benchmark",
        default=SUPPORTED_BENCHMARK,
        choices=[SUPPORTED_BENCHMARK],
    )
    parser.add_argument(
        "--method",
        default=SUPPORTED_METHOD,
        choices=[SUPPORTED_METHOD],
    )
    parser.add_argument(
        "--profile",
        default="smoke",
        choices=["smoke", "official-full"],
    )
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--confirm-api", action="store_true")
    parser.add_argument("--confirm-full", action="store_true")
    parser.add_argument(
        "--smoke-turn-limit",
        type=int,
        default=DEFAULT_SMOKE_TURN_LIMIT,
    )
    parser.add_argument(
        "--smoke-conversation-limit",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--max-new-conversations",
        type=int,
        default=None,
        help=(
            "per-command budget: advance at most this many unfinished "
            "conversations in this invocation. It is not experiment identity."
        ),
    )
    parser.add_argument(
        "--smoke-max-workers",
        type=int,
        default=None,
    )
    args = parser.parse_args(argv)

    summary = run_mem0_locomo_prediction(
        project_root=args.root,
        profile_name=args.profile,
        run_id=args.run_id,
        resume=args.resume,
        confirm_api=args.confirm_api,
        confirm_full=args.confirm_full,
        smoke_turn_limit=args.smoke_turn_limit,
        smoke_conversation_limit=args.smoke_conversation_limit,
        smoke_max_workers=args.smoke_max_workers,
        max_new_conversations=args.max_new_conversations,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "load_completed_conversation_ids",
    "main",
    "PredictionBatchResult",
    "PredictionVariantResult",
    "resolve_prediction_max_workers",
    "resolve_mem0_profile",
    "run_mem0_locomo_prediction",
    "run_registered_conversation_qa_prediction",
]

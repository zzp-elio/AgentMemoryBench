"""通用 prediction runner 的命令行装配入口。

当前入口先支持本地 OSS Mem0 + LoCoMo。它只选择 benchmark adapter、method adapter、
运行 profile 和标准输出目录，不复制 Mem0 算法、LoCoMo 转换或 runner 调度逻辑。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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
    load_openai_settings,
    load_path_settings,
)
from memory_benchmark.core import validate_compatibility
from memory_benchmark.core.exceptions import ConfigurationError
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
from memory_benchmark.runners.conversation_qa import _make_public_conversation
from memory_benchmark.runners.ingest_resume import (
    load_completed_conversation_ids,
)
from memory_benchmark.runners.prediction import (
    PredictionRunPolicy,
    PredictionRunSummary,
    _preflight_prediction_run,
    run_predictions,
)


SUPPORTED_BENCHMARK = "locomo"
SUPPORTED_METHOD = "mem0"
DEFAULT_SMOKE_TURN_LIMIT = 20


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
        smoke_max_workers: 可选 smoke 并发覆盖，仅允许 1 或 2。

    输出:
        int: 传给通用 prediction runner 的 conversation worker 数。
    """

    if smoke_max_workers is None:
        return config.max_workers
    if config.profile_name != "smoke":
        raise ConfigurationError(
            "--smoke-max-workers is a smoke-only diagnostic option"
        )
    if smoke_max_workers not in {1, 2}:
        raise ConfigurationError("Mem0 smoke_max_workers must be at most 2")
    return smoke_max_workers


def run_registered_conversation_qa_prediction(
    project_root: str | Path,
    method_name: str,
    benchmark_name: str,
    profile_name: str = "smoke",
    variant: str | None = None,
    run_id: str | None = None,
    resume: bool = False,
    confirm_api: bool = False,
    confirm_full: bool = False,
    smoke_turn_limit: int = DEFAULT_SMOKE_TURN_LIMIT,
    smoke_conversation_limit: int = 1,
    smoke_max_workers: int | None = None,
    max_new_conversations: int | None = None,
    enable_efficiency_observability: bool = False,
    progress_enabled: bool = True,
) -> PredictionBatchResult:
    """通过 benchmark/method registration 运行 conversation-QA prediction。

    输入:
        project_root: 项目根目录。
        method_name: method registry 中的稳定名称。
        benchmark_name: benchmark registry 中的稳定名称。
        profile_name: `smoke` 或 `official-full`。
        variant: 可选 benchmark variant selector；为空时使用 registration 默认值。
        run_id: 可选稳定运行 id；resume 时必须传显式 base run_id。
        resume: 是否复用兼容 manifest/checkpoint 和 Mem0 method state。
        confirm_api: 是否允许真实付费 API 调用。
        confirm_full: 是否额外允许全量实验。
        smoke_turn_limit: smoke 最多写入的历史 turn 数。
        smoke_conversation_limit: smoke 选择 1 或 2 个 conversation。
        smoke_max_workers: smoke runner 的可选并发覆盖，最多为 2。
        max_new_conversations: 本次命令最多推进多少个未完成 conversation；它只属于
            当前命令预算，不属于实验 identity。
        enable_efficiency_observability: 是否写入效率观测原始 artifact。
        progress_enabled: 是否在终端渲染 Rich 进度条；并行校准模式下应关闭。

    输出:
        PredictionBatchResult: 按 concrete variant 拆开的 child run 结果。
    """

    root = Path(project_root).expanduser().resolve()
    path_settings = load_path_settings(project_root=root)
    benchmark_registration = get_benchmark_registration(benchmark_name)
    method_registration = get_method_registration(method_name)
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
    _validate_child_run_destinations(
        path_settings.outputs_root,
        selected_run_ids,
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
    children: list[_PreparedPredictionChild] = []
    for concrete_variant, selected_run_id in zip(
        selected_variants,
        selected_run_ids,
        strict=True,
    ):
        prepared = benchmark_registration.prepare(
            path_settings.project_root,
            BenchmarkLoadRequest(
                variant=concrete_variant,
                run_scope=run_scope,
                smoke_turn_limit=smoke_turn_limit,
                smoke_conversation_limit=smoke_conversation_limit,
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
        )
        policy = PredictionRunPolicy(
            max_workers=max_workers,
            question_limit_per_conversation=_question_limit_for_scope(run_scope),
            resume=resume,
            max_new_conversations=max_new_conversations,
            progress_enabled=progress_enabled,
        )
        run_context = RunContext.create(
            run_id=selected_run_id,
            benchmark_name=benchmark_name,
            method_name=method_registration.display_name,
            model_name=method_registration.model_name_getter(config),
            output_root=path_settings.outputs_root,
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
        children.append(
            _PreparedPredictionChild(
                variant=prepared.variant,
                run_scope=prepared.run_scope,
                dataset=prepared.dataset,
                run_id=selected_run_id,
                run_context=run_context,
                policy=policy,
                method_manifest=method_manifest,
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
            benchmark_variant=child.variant,
            run_scope=child.run_scope,
            source_paths=child.source_paths,
            efficiency_collector=child.efficiency_collector,
            model_inventory=child.model_inventory,
            instrumentation_identity=child.instrumentation_identity,
            retrieval_observation_contract=child.retrieval_observation_contract,
        )

    openai_settings = (
        load_openai_settings(project_root=path_settings.project_root)
        if method_registration.requires_api
        else None
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
            completed_conversations=completed_conversations,
            efficiency_collector=child.efficiency_collector,
        )
        system = method_registration.system_factory(build_context)
        summary = run_predictions(
            dataset=child.dataset,
            system=system,
            run_context=child.run_context,
            policy=child.policy,
            method_manifest=child.method_manifest,
            benchmark_variant=child.variant,
            run_scope=child.run_scope,
            source_paths=child.source_paths,
            efficiency_collector=child.efficiency_collector,
            model_inventory=child.model_inventory,
            instrumentation_identity=child.instrumentation_identity,
            retrieval_observation_contract=child.retrieval_observation_contract,
            system_factory=method_registration.system_factory,
            build_context_template=build_context,
            supports_shared_instance_parallelism=(
                getattr(
                    method_registration,
                    "supports_shared_instance_parallelism",
                    False,
                )
            ),
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


def _resolve_profile_run_scope(profile_name: str) -> RunScope:
    """把 method profile 名映射为统一的 benchmark run scope。"""

    if profile_name == "smoke":
        return RunScope.SMOKE
    return RunScope.FULL


def _question_limit_for_scope(run_scope: RunScope) -> int | None:
    """根据 run scope 生成通用 runner 的每 conversation 问题上限。"""

    if run_scope is RunScope.SMOKE:
        return 1
    return None


def _validate_child_run_destinations(
    outputs_root: str | Path,
    run_ids: tuple[str, ...],
) -> None:
    """在任何目录、secret 或 method 副作用前校验 child run 目标路径。"""

    canonical_outputs_root = Path(outputs_root).expanduser().resolve()
    seen_destinations: dict[str, Path] = {}
    for run_id in run_ids:
        child_destination = canonical_outputs_root / run_id
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
    """校验 smoke 专用 conversation 并发覆盖。"""

    if smoke_max_workers is None:
        return configured_max_workers
    if profile_name != "smoke":
        raise ConfigurationError(
            "--smoke-max-workers is a smoke-only diagnostic option"
        )
    if not allow_override:
        raise ConfigurationError(
            f"{method_display_name} does not support --smoke-max-workers override"
        )
    if smoke_max_workers not in {1, 2}:
        raise ConfigurationError("smoke_max_workers must be at most 2")
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


def _build_method_manifest(
    *,
    config_manifest: dict[str, object],
    source_identity: dict[str, object],
    workload_estimate: dict[str, object] | None,
) -> dict[str, object]:
    """构造不含 secret 的 method manifest。"""

    manifest: dict[str, object] = {
        "config": config_manifest,
        "source": source_identity,
    }
    if workload_estimate is not None:
        manifest["workload_estimate"] = workload_estimate
    return manifest


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
        choices=[1, 2],
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
        choices=[1, 2],
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

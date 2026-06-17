"""通用 conversation-QA 回复生成 runner。

本模块只负责公开 conversation 写入、公开 question 回答、标准 artifact、
conversation 级调度和断点续跑。它不包含 benchmark/method 特判，也不计算 metric。
"""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core import AnswerResult, Conversation, Dataset, Question
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemorySystem, BaseResumableMemorySystem
from memory_benchmark.core.validators import validate_dataset, validate_no_private_keys
from memory_benchmark.observability import ProgressReporter, RunContext
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    EfficiencyObservation,
    ModelDescriptor,
    RetrievalObservationContract,
)
from memory_benchmark.runners.conversation_qa import (
    _make_public_conversation,
    _make_public_question,
)
from memory_benchmark.runners.ingest_resume import (
    TurnIngestCheckpoint,
    TurnIngestCheckpointStore,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    build_dataset_fingerprint,
    evaluator_private_label_record,
    public_question_record,
    read_jsonl,
)
from memory_benchmark.utils.run_logger import RunLogger


@dataclass(frozen=True)
class PredictionRunPolicy:
    """控制一次通用回复生成运行的公开策略。

    字段:
        max_workers: conversation 级最大并发数。
        conversation_ids: 可选 conversation 白名单；为空时选择全部。
        question_limit_per_conversation: 每个 conversation 最多回答的问题数。
        resume: 是否允许复用当前 run_id 的兼容 checkpoint。
        progress_enabled: 是否在终端渲染 Rich 进度条。
    """

    max_workers: int = 1
    conversation_ids: tuple[str, ...] | None = None
    question_limit_per_conversation: int | None = None
    resume: bool = False
    progress_enabled: bool = True

    def __post_init__(self) -> None:
        """校验调度参数，避免无效配置进入长实验。"""

        if self.max_workers < 1:
            raise ConfigurationError("Prediction max_workers must be at least 1")
        if (
            self.question_limit_per_conversation is not None
            and self.question_limit_per_conversation < 1
        ):
            raise ConfigurationError(
                "question_limit_per_conversation must be at least 1"
            )


@dataclass(frozen=True)
class PredictionRunSummary:
    """一次回复生成运行的机器可读摘要。"""

    run_id: str
    dataset_name: str
    total_conversations: int
    completed_conversations: int
    total_questions: int
    completed_questions: int
    prediction_path: str
    private_label_path: str
    summary_path: str

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化摘要。"""

        return asdict(self)


@dataclass(frozen=True)
class _ConversationAnswerBatch:
    """单个 worker 返回的不可变回复批次。"""

    conversation_id: str
    predictions: tuple[dict[str, Any], ...]
    observations: tuple[EfficiencyObservation, ...] = ()


@dataclass(frozen=True)
class _ConversationIngestBatch:
    """单个 worker 返回的不可变记忆构建批次。"""

    conversation_id: str
    observations: tuple[EfficiencyObservation, ...] = ()


def run_predictions(
    dataset: Dataset,
    system: BaseMemorySystem,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    source_paths: tuple[str | Path, ...] = (),
    efficiency_collector: EfficiencyCollector | None = None,
    model_inventory: tuple[ModelDescriptor, ...] = (),
    instrumentation_identity: dict[str, object] | None = None,
    retrieval_observation_contract: RetrievalObservationContract | None = None,
) -> PredictionRunSummary:
    """运行不含 metric 的通用 conversation-QA 回复生成。

    输入:
        dataset: benchmark adapter 生成的完整统一数据集。
        system: 实现 `BaseMemorySystem` 的被测记忆系统。
        run_context: 本次运行的标准目录和公开身份。
        policy: conversation/question 范围、并发和 resume 策略。
        method_manifest: method 公开配置和源码身份，不能包含 secret。
        benchmark_variant: 当前 benchmark 的 concrete variant，不能为 `all`。
        run_scope: 本次运行范围，必须是 `RunScope`。
        source_paths: 可选原始数据文件，用于数据指纹审计。

    输出:
        PredictionRunSummary: 回复数量和标准 artifact 路径。
    """

    dataset_fingerprint, manifest = _build_prediction_resume_artifacts(
        dataset=dataset,
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
        benchmark_variant=benchmark_variant,
        run_scope=run_scope,
        source_paths=source_paths,
        efficiency_collector=efficiency_collector,
        model_inventory=model_inventory,
        instrumentation_identity=instrumentation_identity,
        retrieval_observation_contract=retrieval_observation_contract,
    )
    selected_conversations = _select_conversations(dataset, policy)
    selected_questions = _selected_questions(selected_conversations, policy)
    paths = ExperimentPaths.create(run_context.run_dir)
    _prepare_run(paths=paths, manifest=manifest, resume=policy.resume)
    efficiency_store: EfficiencyArtifactStore | None = None
    if efficiency_collector is not None and efficiency_collector.enabled:
        efficiency_store = EfficiencyArtifactStore.for_prediction(paths)
        efficiency_store.write_model_inventory(model_inventory)
    logger = RunLogger(paths.logs_dir)
    atomic_write_json(paths.dataset_fingerprint_path, dataset_fingerprint)
    _write_input_artifacts(
        paths=paths,
        conversations=selected_conversations,
        selected_questions=selected_questions,
    )

    prediction_records = {
        record["question_id"]: record
        for record in read_jsonl(
            paths.method_predictions_path,
            recover_torn_tail=policy.resume,
        )
    }
    conversation_status = _read_json_object(paths.conversation_status_path)
    question_status = {
        record["question_id"]: record
        for record in read_jsonl(
            paths.question_status_path,
            recover_torn_tail=policy.resume,
        )
    }
    question_order = [
        question.question_id
        for conversation in selected_conversations
        for question in selected_questions[conversation.conversation_id]
    ]

    logger.info(
        "[bold]Prediction run[/bold] "
        f"benchmark={dataset.dataset_name} method={run_context.method_name} "
        f"conversations={len(selected_conversations)} questions={len(question_order)}"
    )
    logger.log_event(
        "run_started",
        {
            "run_id": run_context.run_id,
            "benchmark": dataset.dataset_name,
            "method": run_context.method_name,
            "resume": policy.resume,
        },
    )

    with ProgressReporter(
        paths.progress_path,
        enabled=policy.progress_enabled,
    ) as progress:
        progress.start_conversations(len(selected_conversations))
        progress.start_questions(len(question_order))
        _ingest_pending_conversations(
            conversations=selected_conversations,
            system=system,
            policy=policy,
            conversation_status=conversation_status,
            paths=paths,
            progress=progress,
            logger=logger,
            efficiency_collector=efficiency_collector,
            efficiency_store=efficiency_store,
        )
        _answer_pending_questions(
            conversations=selected_conversations,
            selected_questions=selected_questions,
            system=system,
            policy=policy,
            prediction_records=prediction_records,
            question_status=question_status,
            question_order=question_order,
            paths=paths,
            progress=progress,
            logger=logger,
            efficiency_collector=efficiency_collector,
            efficiency_store=efficiency_store,
            retrieval_observation_contract=retrieval_observation_contract,
        )
        progress.set_stage("Completed", step_index=3, step_count=3)
        progress.update_conversations(
            completed=len(selected_conversations),
            total=len(selected_conversations),
            current_conversation_id=None,
        )
        progress.update_questions(
            completed=len(prediction_records),
            total=len(question_order),
            current_conversation_id=None,
            current_question_id=None,
        )
        progress.flush()

    summary = PredictionRunSummary(
        run_id=run_context.run_id,
        dataset_name=dataset.dataset_name,
        total_conversations=len(selected_conversations),
        completed_conversations=sum(
            1
            for conversation in selected_conversations
            if conversation_status.get(conversation.conversation_id, {}).get("status")
            == "completed"
        ),
        total_questions=len(question_order),
        completed_questions=sum(
            1 for question_id in question_order if question_id in prediction_records
        ),
        prediction_path=str(paths.method_predictions_path),
        private_label_path=str(paths.evaluator_private_labels_path),
        summary_path=str(paths.summary_path),
    )
    atomic_write_json(paths.summary_path, summary.to_dict())
    logger.log_event("run_completed", summary.to_dict())
    logger.info(
        "[green]Prediction run completed[/green] "
        f"answers={summary.completed_questions}/{summary.total_questions}"
    )
    return summary


def _select_conversations(
    dataset: Dataset,
    policy: PredictionRunPolicy,
) -> list[Conversation]:
    """按 policy 选择 conversation，并拒绝不存在的显式 id。"""

    by_id = {
        conversation.conversation_id: conversation
        for conversation in dataset.conversations
    }
    if policy.conversation_ids is None:
        return list(dataset.conversations)

    missing = [
        conversation_id
        for conversation_id in policy.conversation_ids
        if conversation_id not in by_id
    ]
    if missing:
        raise ConfigurationError(
            f"Unknown conversation_ids in prediction policy: {', '.join(missing)}"
        )
    return [by_id[conversation_id] for conversation_id in policy.conversation_ids]


def _selected_questions(
    conversations: list[Conversation],
    policy: PredictionRunPolicy,
) -> dict[str, list[Question]]:
    """返回每个 conversation 本次需要回答的原始公开问题范围。"""

    return {
        conversation.conversation_id: list(
            conversation.questions[: policy.question_limit_per_conversation]
            if policy.question_limit_per_conversation is not None
            else conversation.questions
        )
        for conversation in conversations
    }


def _build_manifest(
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    dataset_fingerprint: dict[str, Any],
    efficiency_observability: dict[str, object] | None = None,
) -> dict[str, Any]:
    """构造用于 resume 兼容检查的公开 manifest。"""

    policy_payload = {
        "max_workers": policy.max_workers,
        "conversation_ids": (
            list(policy.conversation_ids)
            if policy.conversation_ids is not None
            else None
        ),
        "question_limit_per_conversation": policy.question_limit_per_conversation,
    }
    manifest = {
        "schema_version": 2,
        "runner": "generic_conversation_qa_prediction",
        "run_id": run_context.run_id,
        "benchmark_name": run_context.benchmark_name,
        "method_name": run_context.method_name,
        "model_name": run_context.model_name,
        "dataset_sha256": dataset_fingerprint["dataset_sha256"],
        "source_fingerprint_sha256": dataset_fingerprint[
            "source_fingerprint_sha256"
        ],
        "benchmark_variant": benchmark_variant,
        "run_scope": run_scope.value,
        "policy": policy_payload,
        "method": method_manifest,
    }
    if efficiency_observability is not None:
        manifest["efficiency_observability"] = efficiency_observability
    return manifest


def _build_prediction_resume_artifacts(
    *,
    dataset: Dataset,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    source_paths: tuple[str | Path, ...] = (),
    efficiency_collector: EfficiencyCollector | None = None,
    model_inventory: tuple[ModelDescriptor, ...] = (),
    instrumentation_identity: dict[str, object] | None = None,
    retrieval_observation_contract: RetrievalObservationContract | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """构造 resume 校验所需的数据集指纹与公开 manifest。"""

    validate_dataset(dataset)
    _validate_public_manifest(method_manifest)
    validated_variant = _validate_concrete_benchmark_variant(benchmark_variant)
    validated_run_scope = _validate_run_scope(run_scope)
    dataset_fingerprint = build_dataset_fingerprint(
        dataset=dataset,
        source_paths=[Path(path) for path in source_paths],
    )
    efficiency_observability = _build_efficiency_observability_manifest(
        run_context=run_context,
        efficiency_collector=efficiency_collector,
        model_inventory=model_inventory,
        instrumentation_identity=instrumentation_identity,
        retrieval_observation_contract=retrieval_observation_contract,
    )
    manifest = _build_manifest(
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
        benchmark_variant=validated_variant,
        run_scope=validated_run_scope,
        dataset_fingerprint=dataset_fingerprint,
        efficiency_observability=efficiency_observability,
    )
    return dataset_fingerprint, manifest


def _preflight_prediction_run(
    *,
    dataset: Dataset,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    source_paths: tuple[str | Path, ...] = (),
    efficiency_collector: EfficiencyCollector | None = None,
    model_inventory: tuple[ModelDescriptor, ...] = (),
    instrumentation_identity: dict[str, object] | None = None,
    retrieval_observation_contract: RetrievalObservationContract | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """只读预检 run manifest 与 resume 身份，不创建目录也不写文件。"""

    dataset_fingerprint, manifest = _build_prediction_resume_artifacts(
        dataset=dataset,
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
        benchmark_variant=benchmark_variant,
        run_scope=run_scope,
        source_paths=source_paths,
        efficiency_collector=efficiency_collector,
        model_inventory=model_inventory,
        instrumentation_identity=instrumentation_identity,
        retrieval_observation_contract=retrieval_observation_contract,
    )
    _validate_run_manifest_state(
        paths=ExperimentPaths(run_dir=run_context.run_dir.resolve()),
        manifest=manifest,
        resume=policy.resume,
    )
    return dataset_fingerprint, manifest


def _prepare_run(
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    resume: bool,
) -> None:
    """创建新 manifest，或在 resume 时验证关键配置完全一致。"""

    manifest_exists = paths.manifest_path.exists()
    _validate_run_manifest_state(paths=paths, manifest=manifest, resume=resume)
    if manifest_exists:
        return
    atomic_write_json(paths.manifest_path, manifest)
    redacted_config = {
        "runner": manifest["runner"],
        "policy": manifest["policy"],
        "method": manifest["method"],
    }
    if "efficiency_observability" in manifest:
        redacted_config["efficiency_observability"] = manifest[
            "efficiency_observability"
        ]
    atomic_write_json(paths.redacted_config_path, redacted_config)


def _build_efficiency_observability_manifest(
    *,
    run_context: RunContext,
    efficiency_collector: EfficiencyCollector | None,
    model_inventory: tuple[ModelDescriptor, ...],
    instrumentation_identity: dict[str, object] | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
) -> dict[str, object] | None:
    """构造启用观测时的不可变身份；关闭时保持旧 manifest 不变。"""

    enabled = efficiency_collector is not None and efficiency_collector.enabled
    if not enabled:
        if (
            model_inventory
            or instrumentation_identity is not None
            or retrieval_observation_contract is not None
        ):
            raise ConfigurationError(
                "Efficiency identity requires an enabled collector"
            )
        return None
    if efficiency_collector.run_id != run_context.run_id:
        raise ConfigurationError(
            "EfficiencyCollector run_id must match RunContext run_id"
        )
    if not model_inventory:
        raise ConfigurationError(
            "Enabled efficiency observability requires a model inventory"
        )
    model_ids = [descriptor.model_id for descriptor in model_inventory]
    if len(model_ids) != len(set(model_ids)):
        raise ConfigurationError(
            "Efficiency model inventory contains duplicate model_id"
        )
    if not isinstance(instrumentation_identity, dict) or not instrumentation_identity:
        raise ConfigurationError(
            "Enabled efficiency observability requires instrumentation identity"
        )
    _validate_public_manifest(instrumentation_identity)
    if not isinstance(
        retrieval_observation_contract,
        RetrievalObservationContract,
    ):
        raise ConfigurationError(
            "Enabled efficiency observability requires an explicit retrieval "
            "observation contract"
        )
    return {
        "enabled": True,
        "model_inventory": [
            descriptor.to_dict()
            for descriptor in sorted(
                model_inventory,
                key=lambda descriptor: descriptor.model_id,
            )
        ],
        "instrumentation_identity": instrumentation_identity,
        "retrieval_observation_contract": (
            retrieval_observation_contract.to_dict()
        ),
    }


def _validate_run_manifest_state(
    *,
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    resume: bool,
) -> None:
    """校验 run 目录的 manifest 是否允许本次新建或 resume。"""

    if paths.manifest_path.exists():
        existing = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
        if not resume:
            raise ConfigurationError(
                f"Run directory already has a manifest; use resume or a new run_id: "
                f"{paths.run_dir}"
            )
        if existing.get("schema_version") == 1:
            raise ConfigurationError(
                "Generic prediction manifest schema v1 artifacts remain usable for "
                "artifact-only evaluation, but cannot resume through the v2 "
                "registered prediction service; use a new run_id or a "
                "legacy-compatible entry."
            )
        if existing.get("source_fingerprint_sha256") != manifest.get(
            "source_fingerprint_sha256"
        ):
            raise ConfigurationError(
                "Resume source fingerprint mismatch: source files changed, "
                "are missing, or the existing schema v2 manifest predates "
                "source fingerprint identity"
            )
        if existing != manifest:
            raise ConfigurationError(
                "Resume manifest mismatch: dataset, method or run policy changed"
            )
        return
    if resume:
        raise ConfigurationError(
            f"Cannot resume because manifest is missing: {paths.manifest_path}"
        )


def _validate_concrete_benchmark_variant(benchmark_variant: str) -> str:
    """校验 concrete benchmark variant 已在命令层解析完成。"""

    if not isinstance(benchmark_variant, str):
        raise ConfigurationError("benchmark_variant must be a non-empty concrete value")
    normalized_variant = benchmark_variant.strip()
    if not normalized_variant or normalized_variant == "all":
        raise ConfigurationError("benchmark_variant must be a non-empty concrete value")
    return normalized_variant


def _validate_run_scope(run_scope: RunScope) -> RunScope:
    """校验 run_scope 使用强类型枚举，而不是宽松字符串。"""

    if not isinstance(run_scope, RunScope):
        raise ConfigurationError("run_scope must be a RunScope")
    return run_scope


def _write_input_artifacts(
    paths: ExperimentPaths,
    conversations: list[Conversation],
    selected_questions: dict[str, list[Question]],
) -> None:
    """原子写入公开问题与 evaluator-only 私有标签。"""

    public_records: list[dict[str, Any]] = []
    private_records: list[dict[str, Any]] = []
    for conversation in conversations:
        for source_question in selected_questions[conversation.conversation_id]:
            question = _make_public_question(source_question)
            public_records.append(public_question_record(question))
            private_records.append(
                evaluator_private_label_record(
                    conversation.gold_answers[question.question_id],
                    question.category,
                )
            )
    atomic_write_jsonl(paths.public_questions_path, public_records)
    atomic_write_jsonl(paths.evaluator_private_labels_path, private_records)


def _ingest_pending_conversations(
    conversations: list[Conversation],
    system: BaseMemorySystem,
    policy: PredictionRunPolicy,
    conversation_status: dict[str, Any],
    paths: ExperimentPaths,
    progress: ProgressReporter,
    logger: RunLogger,
    efficiency_collector: EfficiencyCollector | None,
    efficiency_store: EfficiencyArtifactStore | None,
) -> None:
    """并发写入尚未完成的 conversation，并由协调线程持久化状态。"""

    progress.set_stage("Ingest conversations", step_index=1, step_count=3)
    checkpoint_store = TurnIngestCheckpointStore(
        paths.ingest_turn_checkpoints_dir
    )
    resume_checkpoints = _preflight_ingest_checkpoints(
        conversations=conversations,
        system=system,
        policy=policy,
        conversation_status=conversation_status,
        checkpoint_store=checkpoint_store,
    )
    if any(
        conversation_status.get(conversation.conversation_id, {}).get("status")
        == "completed"
        and resume_checkpoints.get(conversation.conversation_id) is not None
        for conversation in conversations
    ):
        atomic_write_json(paths.conversation_status_path, conversation_status)

    completed = sum(
        1
        for conversation in conversations
        if conversation_status.get(conversation.conversation_id, {}).get("status")
        == "completed"
    )
    pending = [
        conversation
        for conversation in conversations
        if conversation_status.get(conversation.conversation_id, {}).get("status")
        != "completed"
    ]
    if not pending:
        progress.update_conversations(completed, len(conversations), None)
        return

    with ThreadPoolExecutor(max_workers=policy.max_workers) as executor:
        futures: dict[Future[_ConversationIngestBatch], str] = {
            executor.submit(
                _ingest_one,
                system,
                conversation,
                checkpoint_store,
                resume_checkpoints.get(conversation.conversation_id),
                efficiency_collector,
            ): conversation.conversation_id
            for conversation in pending
        }
        for future in as_completed(futures):
            conversation_id = futures[future]
            try:
                batch = future.result()
            except Exception as exc:
                conversation_status[conversation_id] = {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                atomic_write_json(paths.conversation_status_path, conversation_status)
                logger.log_event(
                    "conversation_failed",
                    {
                        "conversation_id": conversation_id,
                        "stage": "ingest",
                        "error_type": type(exc).__name__,
                    },
                )
                raise
            if efficiency_store is not None:
                efficiency_store.merge_observations(batch.observations)
            returned_id = batch.conversation_id
            if isinstance(system, BaseResumableMemorySystem):
                conversation = next(
                    item
                    for item in pending
                    if item.conversation_id == returned_id
                )
                checkpoint_store.mark_conversation_completed(
                    conversation_id=returned_id,
                    total_turns=_conversation_turn_count(conversation),
                )
            conversation_status[returned_id] = {"status": "completed"}
            completed += 1
            atomic_write_json(paths.conversation_status_path, conversation_status)
            progress.update_conversations(
                completed=completed,
                total=len(conversations),
                current_conversation_id=returned_id,
            )
            logger.log_event(
                "conversation_ingested",
                {"conversation_id": returned_id},
            )


def _preflight_ingest_checkpoints(
    conversations: list[Conversation],
    system: BaseMemorySystem,
    policy: PredictionRunPolicy,
    conversation_status: dict[str, Any],
    checkpoint_store: TurnIngestCheckpointStore,
) -> dict[str, TurnIngestCheckpoint | None]:
    """在创建任何 worker 前读取并验证全部 conversation checkpoint。

    返回:
        dict: conversation id 到已验证 checkpoint 的映射；无文件时值为 `None`。

    说明:
        预检先完成所有读取和错误判断，再修复 coarse 状态，保证任一 `in_flight`
        都会在 method 调用前终止整个 resume。
    """

    is_resumable = isinstance(system, BaseResumableMemorySystem)
    checkpoints: dict[str, TurnIngestCheckpoint | None] = {}
    for conversation in conversations:
        total_turns = _conversation_turn_count(conversation)
        checkpoint = checkpoint_store.load(
            conversation.conversation_id,
            total_turns=total_turns,
        )
        checkpoints[conversation.conversation_id] = checkpoint
        if checkpoint is None:
            continue
        if not is_resumable:
            raise ConfigurationError(
                "Turn ingest checkpoint exists, but method does not implement "
                f"BaseResumableMemorySystem: {conversation.conversation_id}"
            )
        if not policy.resume:
            raise ConfigurationError(
                "Turn ingest checkpoint exists for a non-resume run: "
                f"{conversation.conversation_id}"
            )
        if checkpoint.status == "in_flight":
            raise ConfigurationError(
                "Cannot automatically resume an in_flight turn for conversation: "
                f"{conversation.conversation_id}"
            )
        coarse_status = conversation_status.get(
            conversation.conversation_id, {}
        ).get("status")
        if coarse_status == "completed" and checkpoint.status != "completed":
            raise ConfigurationError(
                "Conversation coarse status is completed but turn checkpoint is not: "
                f"{conversation.conversation_id}"
            )

    for conversation in conversations:
        conversation_id = conversation.conversation_id
        checkpoint = checkpoints[conversation_id]
        if checkpoint is None:
            continue
        if checkpoint.status == "completed":
            conversation_status[conversation_id] = {"status": "completed"}

    return checkpoints


def _ingest_one(
    system: BaseMemorySystem,
    conversation: Conversation,
    checkpoint_store: TurnIngestCheckpointStore,
    checkpoint: TurnIngestCheckpoint | None,
    efficiency_collector: EfficiencyCollector | None,
) -> _ConversationIngestBatch:
    """worker 内重建公开 conversation，并选择完整或逐 turn 写入路径。"""

    public_conversation = _make_public_conversation(conversation)
    validate_no_private_keys(public_conversation.to_public_dict())
    if efficiency_collector is not None and efficiency_collector.enabled:
        with efficiency_collector.conversation_scope(
            conversation.conversation_id
        ) as scope:
            started_ns = perf_counter_ns()
            _add_public_conversation(
                system=system,
                public_conversation=public_conversation,
                checkpoint_store=checkpoint_store,
                checkpoint=checkpoint,
            )
            efficiency_collector.record_memory_build_total_latency(
                latency_ms=_elapsed_ms(started_ns)
            )
        return _ConversationIngestBatch(
            conversation_id=conversation.conversation_id,
            observations=scope.records,
        )

    _add_public_conversation(
        system=system,
        public_conversation=public_conversation,
        checkpoint_store=checkpoint_store,
        checkpoint=checkpoint,
    )
    return _ConversationIngestBatch(
        conversation_id=conversation.conversation_id,
    )


def _add_public_conversation(
    *,
    system: BaseMemorySystem,
    public_conversation: Conversation,
    checkpoint_store: TurnIngestCheckpointStore,
    checkpoint: TurnIngestCheckpoint | None,
) -> None:
    """执行一次公开 conversation 写入，并校验 method 返回 id。"""

    if isinstance(system, BaseResumableMemorySystem):
        total_turns = _conversation_turn_count(public_conversation)
        start_turn_index = (
            checkpoint.next_turn_index if checkpoint is not None else 0
        )
        result = system.add_from_turn(
            conversation=public_conversation,
            start_turn_index=start_turn_index,
            on_turn_started=lambda turn_index, turn: checkpoint_store.mark_started(
                conversation_id=public_conversation.conversation_id,
                turn_index=turn_index,
                turn_id=turn.turn_id,
                total_turns=total_turns,
            ),
            on_turn_completed=lambda turn_index, turn: checkpoint_store.mark_turn_completed(
                conversation_id=public_conversation.conversation_id,
                turn_index=turn_index,
                turn_id=turn.turn_id,
                total_turns=total_turns,
            ),
        )
    else:
        result = system.add([public_conversation])
    if public_conversation.conversation_id not in result.conversation_ids:
        raise ConfigurationError(
            "Method add result did not include expected conversation_id: "
            f"{public_conversation.conversation_id}"
        )


def _conversation_turn_count(conversation: Conversation) -> int:
    """返回按 session 原顺序展开后的 turn 总数，并拒绝空历史。"""

    total_turns = sum(len(session.turns) for session in conversation.sessions)
    if total_turns < 1:
        raise ConfigurationError(
            f"Conversation has no turns: {conversation.conversation_id}"
        )
    return total_turns


def _answer_pending_questions(
    conversations: list[Conversation],
    selected_questions: dict[str, list[Question]],
    system: BaseMemorySystem,
    policy: PredictionRunPolicy,
    prediction_records: dict[str, dict[str, Any]],
    question_status: dict[str, dict[str, Any]],
    question_order: list[str],
    paths: ExperimentPaths,
    progress: ProgressReporter,
    logger: RunLogger,
    efficiency_collector: EfficiencyCollector | None,
    efficiency_store: EfficiencyArtifactStore | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
) -> None:
    """按 conversation 并发回答问题，并由协调线程提交完整 batch。"""

    progress.set_stage("Answer questions", step_index=2, step_count=3)
    completed = sum(
        1 for question_id in question_order if question_id in prediction_records
    )
    pending_by_conversation: dict[str, list[Question]] = {}
    for conversation in conversations:
        pending_questions = [
            question
            for question in selected_questions[conversation.conversation_id]
            if question.question_id not in prediction_records
        ]
        if pending_questions:
            pending_by_conversation[conversation.conversation_id] = pending_questions

    with ThreadPoolExecutor(max_workers=policy.max_workers) as executor:
        futures: dict[Future[_ConversationAnswerBatch], str] = {
            executor.submit(
                _answer_conversation_questions,
                system,
                conversation_id,
                questions,
                efficiency_collector,
                retrieval_observation_contract,
            ): conversation_id
            for conversation_id, questions in pending_by_conversation.items()
        }
        for future in as_completed(futures):
            conversation_id = futures[future]
            try:
                batch = future.result()
            except Exception as exc:
                logger.log_event(
                    "question_batch_failed",
                    {
                        "conversation_id": conversation_id,
                        "stage": "answer",
                        "error_type": type(exc).__name__,
                    },
                )
                raise
            if efficiency_store is not None:
                efficiency_store.merge_observations(batch.observations)
            for record in batch.predictions:
                prediction_records[record["question_id"]] = record
                question_status[record["question_id"]] = {
                    "question_id": record["question_id"],
                    "conversation_id": record["conversation_id"],
                    "status": "completed",
                }
                completed += 1
                progress.update_questions(
                    completed=completed,
                    total=len(question_order),
                    current_conversation_id=record["conversation_id"],
                    current_question_id=record["question_id"],
                )
                logger.log_event(
                    "question_answered",
                    {
                        "conversation_id": record["conversation_id"],
                        "question_id": record["question_id"],
                    },
                )
            atomic_write_jsonl(
                paths.method_predictions_path,
                [
                    prediction_records[question_id]
                    for question_id in question_order
                    if question_id in prediction_records
                ],
            )
            atomic_write_jsonl(
                paths.question_status_path,
                [
                    question_status[question_id]
                    for question_id in question_order
                    if question_id in question_status
                ],
            )


def _answer_conversation_questions(
    system: BaseMemorySystem,
    conversation_id: str,
    questions: list[Question],
    efficiency_collector: EfficiencyCollector | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
) -> _ConversationAnswerBatch:
    """worker 内串行回答一个 conversation 的所有待处理问题。"""

    records: list[dict[str, Any]] = []
    observations: list[EfficiencyObservation] = []
    for source_question in questions:
        question = _make_public_question(source_question)
        validate_no_private_keys(question.to_dict())
        if efficiency_collector is not None and efficiency_collector.enabled:
            if not isinstance(
                retrieval_observation_contract,
                RetrievalObservationContract,
            ):
                raise ConfigurationError(
                    "Enabled efficiency observability requires an explicit "
                    "retrieval observation contract"
                )
            with efficiency_collector.question_scope(
                conversation_id,
                question.question_id,
            ) as scope:
                prediction = system.get_answer(question)
                if not retrieval_observation_contract.supported_by_method:
                    efficiency_collector.record_retrieval_unsupported_if_missing(
                        retrieval_observation_contract.unsupported_reason or ""
                    )
            observations.extend(scope.records)
        else:
            prediction = system.get_answer(question)
        _validate_prediction(prediction, question)
        validate_no_private_keys(prediction.metadata)
        records.append(
            {
                "question_id": question.question_id,
                "conversation_id": conversation_id,
                "question_text": question.text,
                "answer": prediction.answer,
                "metadata": prediction.metadata,
            }
        )
    return _ConversationAnswerBatch(
        conversation_id=conversation_id,
        predictions=tuple(records),
        observations=tuple(observations),
    )


def _elapsed_ms(started_ns: int) -> float:
    """把 `perf_counter_ns()` 起点转换为正的毫秒耗时。"""

    return max((perf_counter_ns() - started_ns) / 1_000_000, 0.0)


def _validate_prediction(prediction: AnswerResult, question: Question) -> None:
    """校验 method 返回值与公开问题严格对齐。"""

    if prediction.question_id != question.question_id:
        raise ConfigurationError(
            f"Prediction question_id mismatch: {prediction.question_id} != "
            f"{question.question_id}"
        )
    if prediction.conversation_id != question.conversation_id:
        raise ConfigurationError(
            f"Prediction conversation_id mismatch: {prediction.conversation_id} != "
            f"{question.conversation_id}"
        )
    if not prediction.answer.strip():
        raise ConfigurationError(
            f"Method returned an empty answer for question: {question.question_id}"
        )


def _validate_public_manifest(payload: dict[str, object]) -> None:
    """拒绝 method manifest 中的 secret 和私有评测字段。"""

    validate_no_private_keys(payload)
    forbidden_fragments = ("api_key", "secret", "token", "password")

    def walk(value: Any, path: str) -> None:
        """递归检查嵌套 manifest 的字段名称。"""

        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).lower()
                if any(fragment in normalized for fragment in forbidden_fragments):
                    raise ConfigurationError(
                        f"Method manifest contains a secret-like field: {path}.{key}"
                    )
                walk(child, f"{path}.{key}")
        elif isinstance(value, list | tuple):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload, "$")


def _read_json_object(path: Path) -> dict[str, Any]:
    """读取 JSON 对象；文件不存在时返回空字典。"""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigurationError(f"Expected JSON object checkpoint: {path}")
    return payload


__all__ = [
    "PredictionRunPolicy",
    "PredictionRunSummary",
    "run_predictions",
]

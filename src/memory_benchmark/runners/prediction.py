"""通用 conversation-QA 回复生成 runner。

本模块只负责公开 conversation 写入、公开 question 回答、标准 artifact、
conversation 级调度和断点续跑。它不包含 benchmark/method 特判，也不计算 metric。
"""

from __future__ import annotations

import json
import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from threading import Event
from time import perf_counter_ns
from typing import Any, Callable

from memory_benchmark.analysis.efficiency import build_efficiency_report_payloads
from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core import (
    AnswerResult,
    Conversation,
    Dataset,
    Question,
    AnswerPromptResult,
    PromptMessage,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import (
    BaseMemoryProvider,
    BaseMemorySystem,
    BaseResumableMemorySystem,
)
from memory_benchmark.core.provider_bridge import LegacyProviderBridge
from memory_benchmark.core.provider_protocol import (
    BRIDGE_EMPTY_MEMORY_SENTINEL,
    ConversationBatch,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    SessionBatch,
    SessionRef,
    SessionMemoryReport,
    TurnEvent,
    TurnPair,
    UnitRef,
)
from memory_benchmark.core.validators import validate_dataset, validate_no_private_keys
from memory_benchmark.methods.registry import MethodBuildContext
from memory_benchmark.observability import ProgressReporter, RunContext
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    EfficiencyObservation,
    EfficiencyStage,
    ModelDescriptor,
    RetrievalObservationContract,
    extract_api_token_usage,
    resolve_token_usage,
)
from memory_benchmark.readers.answer import AnswerLLMResponse, FrameworkAnswerReader
from memory_benchmark.runners.conversation_qa import (
    _make_public_conversation,
    _make_public_question,
)
from memory_benchmark.runners.event_stream import (
    GranularityAggregator,
    build_turn_events,
    default_isolation_key,
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


# 同一 conversation 所有 question 共享的 metadata key，应去重后单独保存。
_CONVERSATION_LEVEL_METADATA_KEYS: frozenset[str] = frozenset({"system_prompt"})


@dataclass(frozen=True)
class PredictionRunPolicy:
    """控制一次通用回复生成运行的公开策略。

    字段:
        max_workers: conversation 级最大并发数。
        conversation_ids: 可选 conversation 白名单；为空时选择全部。
        question_limit_per_conversation: 每个 conversation 最多回答的问题数。
        max_new_conversations: 本次命令最多推进多少个未完成 conversation；不属于
            实验 identity，可在 resume 命令之间变化。
        retry_failed_conversations: 是否把上次已标记 failed 的 conversation 重新纳入
            本次工作计划；默认 False，避免失败 conversation 在 resume 时反复空烧 API。
        max_consecutive_failures: 单个 worker 连续 conversation 失败熔断阈值；达到后
            停止该 worker 后续 conversation，避免配置或网络系统性异常时批量空烧。
        resume: 是否允许复用当前 run_id 的兼容 checkpoint。
        progress_enabled: 是否在终端渲染 Rich 进度条。
    """

    max_workers: int = 1
    conversation_ids: tuple[str, ...] | None = None
    question_limit_per_conversation: int | None = None
    max_new_conversations: int | None = None
    retry_failed_conversations: bool = False
    max_consecutive_failures: int | None = 3
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
        if self.max_new_conversations is not None and self.max_new_conversations < 1:
            raise ConfigurationError("max_new_conversations must be at least 1")
        if (
            self.max_consecutive_failures is not None
            and self.max_consecutive_failures < 1
        ):
            raise ConfigurationError("max_consecutive_failures must be at least 1")


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
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化摘要。"""

        return asdict(self)


@dataclass(frozen=True)
class _ConversationAnswerBatch:
    """单个 worker 返回的不可变回复批次。"""

    conversation_id: str
    predictions: tuple[dict[str, Any], ...]
    retrievals: tuple[dict[str, Any], ...] = ()
    session_reports: tuple[dict[str, Any], ...] = ()
    observations: tuple[EfficiencyObservation, ...] = ()
    ingested: bool = False


@dataclass(frozen=True)
class _ConversationIngestBatch:
    """单个 worker 返回的不可变记忆构建批次。"""

    conversation_id: str
    session_reports: tuple[dict[str, Any], ...] = ()
    observations: tuple[EfficiencyObservation, ...] = ()


@dataclass(frozen=True)
class _ConversationFailureBatch:
    """单个 isolated worker 捕获的 conversation 局部失败。

    字段:
        conversation_id: 失败 conversation id。
        stage: 失败阶段，例如 `isolated_worker`。
        error_type: 原始异常类型名。
        error: 原始异常消息。
        traceback_text: 完整 traceback，写入事件和 checkpoint 方便定位。
        observations: 失败前已采集的效率观测。
        predictions: 失败前已生成并校验通过的问题回答。
        retrievals: 失败前已生成并校验通过的 answer prompt 记录。
        ingested: 当前 conversation 的 memory state 是否已经写入完成。
    """

    conversation_id: str
    stage: str
    error_type: str
    error: str
    traceback_text: str
    observations: tuple[EfficiencyObservation, ...] = ()
    predictions: tuple[dict[str, Any], ...] = ()
    retrievals: tuple[dict[str, Any], ...] = ()
    session_reports: tuple[dict[str, Any], ...] = ()
    ingested: bool = False


class _RetrieveFirstAnswerError(RuntimeError):
    """retrieve-first answer 失败时携带已完成的 retrieval records。"""

    def __init__(
        self,
        *,
        original_error: Exception,
        retrievals: tuple[dict[str, Any], ...],
    ) -> None:
        """保存原始异常和已安全生成的 retrieval records。"""

        super().__init__(str(original_error))
        self.original_error = original_error
        self.retrievals = retrievals


@dataclass(frozen=True)
class _ConversationWorkItem:
    """本次命令要处理的单个 conversation 工作项。"""

    conversation: Conversation
    needs_ingest: bool
    pending_questions: tuple[Question, ...]


class _ConversationWorkItemError(RuntimeError):
    """isolated worker 内某个 conversation 失败时携带定位信息。

    字段:
        conversation_id: 失败 conversation，用于写入 quarantine checkpoint。
        stage: 失败发生的 runner 阶段。
        original_error: 第三方 method 或 runner 抛出的原始异常。
    """

    def __init__(
        self,
        *,
        conversation_id: str,
        stage: str,
        original_error: Exception,
    ) -> None:
        """保存失败定位信息，同时保留原始异常消息方便外层匹配。"""

        super().__init__(str(original_error))
        self.conversation_id = conversation_id
        self.stage = stage
        self.original_error = original_error


@dataclass(frozen=True)
class _PredictionWorkPlan:
    """本次命令裁剪后的 prediction 工作计划。"""

    items: tuple[_ConversationWorkItem, ...]
    conversation_order: tuple[str, ...]
    selected_questions: dict[str, list[Question]]
    question_order: tuple[str, ...]
    completed_question_ids: frozenset[str]
    ingested_conversation_ids: frozenset[str]
    skipped_failed_conversation_ids: tuple[str, ...]
    dataset_conversation_count: int
    budget_exhausted: bool


_STATUS_PENDING = "pending"
_STATUS_INGESTED = "ingested"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED_INGEST = "failed_ingest"
_STATUS_FAILED_ANSWER = "failed_answer"

_PredictionSystem = BaseMemorySystem | BaseMemoryProvider | MemoryProvider


def _conversation_state_status(state: dict[str, Any]) -> str:
    """读取 conversation 状态，并兼容旧 `failed + ingested` checkpoint。

    输入:
        state: `conversation_status.json` 中某个 conversation 的状态对象。

    输出:
        str: 标准化后的状态。旧 `failed` 会根据 `ingested` 映射到
        `failed_answer` 或 `failed_ingest`。
    """

    status = str(state.get("status", _STATUS_PENDING))
    if status == "failed":
        if state.get("ingested") is True:
            return _STATUS_FAILED_ANSWER
        return _STATUS_FAILED_INGEST
    return status


def _conversation_is_ingested(state: dict[str, Any]) -> bool:
    """判断 conversation 是否已完成 add，可直接进入 answer 阶段。"""

    status = _conversation_state_status(state)
    return (
        status
        in {
            _STATUS_INGESTED,
            _STATUS_COMPLETED,
            _STATUS_FAILED_ANSWER,
        }
        or state.get("ingested") is True
    )


def run_predictions(
    dataset: Dataset,
    system: _PredictionSystem,
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
    answer_reader: FrameworkAnswerReader | None = None,
    *,
    system_factory: Callable[
        [MethodBuildContext], _PredictionSystem
    ] | None = None,
    build_context_template: MethodBuildContext | None = None,
    supports_shared_instance_parallelism: bool = False,
    clean_failed_ingest_conversation: (
        Callable[[Conversation, dict[str, Any]], None] | None
    ) = None,
) -> PredictionRunSummary:
    """运行不含 metric 的通用 conversation-QA 回复生成。

    输入:
        dataset: benchmark adapter 生成的完整统一数据集。
        system: 实现旧 `BaseMemorySystem` 或新 `BaseMemoryProvider` 的被测记忆系统。
        run_context: 本次运行的标准目录和公开身份。
        policy: conversation/question 范围、并发和 resume 策略。
        answer_reader: retrieve-first provider 路径使用的 framework answer reader。
        method_manifest: method 公开配置和源码身份，不能包含 secret。
        benchmark_variant: 当前 benchmark 的 concrete variant，不能为 `all`。
        run_scope: 本次运行范围，必须是 `RunScope`。
        source_paths: 可选原始数据文件，用于数据指纹审计。
        system_factory: 独立 instance 模式下 worker 创建 system 的工厂函数。
        build_context_template: 独立 instance 模式下 worker 构造 context 的模板。
        supports_shared_instance_parallelism: method 是否支持共享实例线程并行。
        clean_failed_ingest_conversation: 可选 conversation 级 clean retry hook；
            只有内置 method 能证明可安全清理半写入状态时才应传入。

    输出:
        PredictionRunSummary: 回复数量和标准 artifact 路径。
    """

    system = _normalize_memory_system(system)
    method_manifest = _method_manifest_with_protocol(
        method_manifest=method_manifest,
        system=system,
    )
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
    cleaned_failed_ingest_conversation_ids = _prepare_clean_failed_ingest_retries(
        conversations=selected_conversations,
        conversation_status=conversation_status,
        policy=policy,
        clean_failed_ingest_conversation=clean_failed_ingest_conversation,
        paths=paths,
        logger=logger,
    )
    use_isolated = (
        system_factory is not None
        and build_context_template is not None
        and policy.max_workers > 1
        and not supports_shared_instance_parallelism
    )
    if not use_isolated:
        checkpoint_store = TurnIngestCheckpointStore(
            paths.ingest_turn_checkpoints_dir
        )
        _preflight_ingest_checkpoints(
            conversations=selected_conversations,
            system=system,
            policy=policy,
            conversation_status=conversation_status,
            checkpoint_store=checkpoint_store,
        )
        atomic_write_json(paths.conversation_status_path, conversation_status)
    work_plan = _build_prediction_work_plan(
        conversations=selected_conversations,
        selected_questions=selected_questions,
        conversation_status=conversation_status,
        prediction_records=prediction_records,
        policy=policy,
    )
    run_control_metadata = {
        "max_new_conversations": policy.max_new_conversations,
        "retry_failed_conversations": policy.retry_failed_conversations,
        "skipped_failed_conversations": list(
            work_plan.skipped_failed_conversation_ids
        ),
        "budget_exhausted": work_plan.budget_exhausted,
    }
    if cleaned_failed_ingest_conversation_ids:
        run_control_metadata["cleaned_failed_ingest_conversations"] = list(
            cleaned_failed_ingest_conversation_ids
        )

    _conversation_progress_total = (
        len(work_plan.ingested_conversation_ids) + len(work_plan.items)
    )
    _question_progress_total = (
        len(work_plan.completed_question_ids)
        + sum(len(item.pending_questions) for item in work_plan.items)
    )

    logger.info(
        "[bold]Prediction run[/bold] "
        f"benchmark={dataset.dataset_name} method={run_context.method_name} "
        f"conversations={_conversation_progress_total} questions={_question_progress_total}"
    )
    logger.log_event(
        "run_started",
        {
            "run_id": run_context.run_id,
            "benchmark": dataset.dataset_name,
            "method": run_context.method_name,
            "resume": policy.resume,
            "run_control": run_control_metadata,
        },
    )

    with ProgressReporter(
        paths.progress_path,
        enabled=policy.progress_enabled,
    ) as progress:
        progress.start_conversations(_conversation_progress_total)
        progress.start_questions(_question_progress_total)
        if use_isolated:
            _run_isolated_worker_pipeline(
                work_plan=work_plan,
                system_factory=system_factory,
                build_context_template=build_context_template,
                run_id=run_context.run_id,
                policy=policy,
                paths=paths,
                progress=progress,
                logger=logger,
                efficiency_collector=efficiency_collector,
                efficiency_store=efficiency_store,
                retrieval_observation_contract=retrieval_observation_contract,
                prediction_records=prediction_records,
                conversation_status=conversation_status,
                question_status=question_status,
                question_order=question_order,
                answer_reader=answer_reader,
            )
        else:
            ingest_conversations = [
                item.conversation for item in work_plan.items if item.needs_ingest
            ]
            answer_conversations = [
                item.conversation
                for item in work_plan.items
                if item.pending_questions
            ]
            pending_selected_questions = {
                item.conversation.conversation_id: list(item.pending_questions)
                for item in work_plan.items
                if item.pending_questions
            }
            _ingest_pending_conversations(
                conversations=ingest_conversations,
                system=system,
                run_id=run_context.run_id,
                policy=policy,
                conversation_status=conversation_status,
                paths=paths,
                progress=progress,
                logger=logger,
                efficiency_collector=efficiency_collector,
                efficiency_store=efficiency_store,
            )
            _answer_pending_questions(
                conversations=answer_conversations,
                selected_questions=pending_selected_questions,
                system=system,
                run_id=run_context.run_id,
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
                answer_reader=answer_reader,
            )
        progress.set_stage("Completed", step_index=3, step_count=3)
        completed_conversation_count = sum(
            1
            for conversation in selected_conversations
            if conversation_status.get(conversation.conversation_id, {}).get("status")
            == "completed"
        )
        progress.update_conversations(
            completed=completed_conversation_count,
            total=_conversation_progress_total,
            current_conversation_id=None,
        )
        progress.update_questions(
            completed=len(prediction_records),
            total=_question_progress_total,
            current_conversation_id=None,
            current_question_id=None,
        )
        progress.flush()

    conversation_prompts = _build_conversation_prompts(prediction_records)
    if conversation_prompts:
        atomic_write_jsonl(
            paths.conversation_prompts_path,
            [
                {"conversation_id": conv_id, **prompts}
                for conv_id, prompts in conversation_prompts.items()
            ],
        )
        _strip_conversation_metadata(prediction_records)
        atomic_write_jsonl(
            paths.method_predictions_path,
            [
                prediction_records[qid]
                for qid in question_order
                if qid in prediction_records
            ],
        )

    if efficiency_store is not None:
        _write_prediction_efficiency_summaries(
            paths=paths,
            efficiency_store=efficiency_store,
        )

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
        metadata={
            "run_control": run_control_metadata,
            "bridge_empty_memory_sentinel_count": _count_bridge_empty_memory_sentinel(
                paths.answer_prompts_path
            ),
        },
    )
    atomic_write_json(paths.summary_path, summary.to_dict())
    logger.log_event("run_completed", summary.to_dict())
    logger.info(
        "[green]Prediction run completed[/green] "
        f"answers={summary.completed_questions}/{summary.total_questions}"
    )
    return summary


def _write_prediction_efficiency_summaries(
    *,
    paths: ExperimentPaths,
    efficiency_store: EfficiencyArtifactStore,
) -> None:
    """从 raw observation 派生 prediction 阶段的人类可读效率摘要。

    输入:
        paths: 当前 run 的标准路径集合。
        efficiency_store: prediction 阶段 observation 存储。

    输出:
        None。函数会原子写入 overall、by_conversation 和 by_question 三个 JSON。
    """

    overall, by_conversation, by_question = build_efficiency_report_payloads(
        efficiency_store.read_observations()
    )
    atomic_write_json(paths.prediction_efficiency_overall_summary_path, overall)
    atomic_write_json(
        paths.prediction_efficiency_by_conversation_summary_path,
        by_conversation,
    )
    atomic_write_json(
        paths.prediction_efficiency_by_question_summary_path,
        by_question,
    )


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


def _prepare_clean_failed_ingest_retries(
    *,
    conversations: list[Conversation],
    conversation_status: dict[str, Any],
    policy: PredictionRunPolicy,
    clean_failed_ingest_conversation: (
        Callable[[Conversation, dict[str, Any]], None] | None
    ),
    paths: ExperimentPaths,
    logger: RunLogger,
) -> tuple[str, ...]:
    """在生成 work plan 前清理可安全重试的 failed_ingest conversation。

    输入:
        conversations: 本次 run 选择的原始 conversation；调用 clean hook 前会转换为
            public conversation，避免泄露 gold/evidence。
        conversation_status: 持久化 conversation 状态，会被原地更新。
        policy: 当前 resume/retry 策略。
        clean_failed_ingest_conversation: method 侧证明安全的清理 hook。
        paths: 当前 run 标准路径，用于清理后立即持久化 checkpoint。
        logger: 结构化事件日志。

    输出:
        tuple[str, ...]: 本次已清理的 conversation id。无 clean hook 时不改变状态，
        后续 work plan 仍会 fail closed。
    """

    if not policy.retry_failed_conversations:
        return ()
    if clean_failed_ingest_conversation is None:
        return ()

    cleaned_conversation_ids: list[str] = []
    for conversation in conversations:
        conversation_id = conversation.conversation_id
        state = conversation_status.get(conversation_id, {})
        if _conversation_state_status(state) != _STATUS_FAILED_INGEST:
            continue

        clean_failed_ingest_conversation(
            _make_public_conversation(conversation),
            dict(state),
        )
        conversation_status[conversation_id] = {
            "status": _STATUS_PENDING,
            "ingested": False,
            "retry_cleaned": True,
            "previous_status": state,
        }
        cleaned_conversation_ids.append(conversation_id)
        logger.log_event(
            "failed_ingest_cleaned_for_retry",
            {"conversation_id": conversation_id},
        )

    if cleaned_conversation_ids:
        atomic_write_json(paths.conversation_status_path, conversation_status)

    return tuple(cleaned_conversation_ids)


def _build_prediction_work_plan(
    *,
    conversations: list[Conversation],
    selected_questions: dict[str, list[Question]],
    conversation_status: dict[str, Any],
    prediction_records: dict[str, dict[str, Any]],
    policy: PredictionRunPolicy,
) -> _PredictionWorkPlan:
    """根据持久化状态和本次预算生成实际要执行的工作计划。

    `max_new_conversations` 只限制本次命令推进多少个未完成 conversation，不改变
    manifest identity。已完成 conversation 不占预算；已完成 add 但仍有未答问题的
    conversation 会占预算并只进入 answer 阶段。
    """

    selected_question_ids = {
        question.question_id
        for conversation in conversations
        for question in selected_questions[conversation.conversation_id]
    }
    completed_question_ids = frozenset(
        question_id
        for question_id in prediction_records
        if question_id in selected_question_ids
    )
    ingested_conversation_ids = frozenset(
        conversation.conversation_id
        for conversation in conversations
        if _conversation_is_ingested(
            conversation_status.get(conversation.conversation_id, {})
        )
    )
    question_order = tuple(
        question.question_id
        for conversation in conversations
        for question in selected_questions[conversation.conversation_id]
    )
    conversation_order = tuple(
        conversation.conversation_id for conversation in conversations
    )

    items: list[_ConversationWorkItem] = []
    skipped_failed_conversation_ids: list[str] = []
    unfinished_seen = 0
    budget_exhausted = False
    for conversation in conversations:
        conversation_id = conversation.conversation_id
        conversation_state = conversation_status.get(conversation_id, {})
        status = _conversation_state_status(conversation_state)
        if status == _STATUS_FAILED_INGEST:
            if policy.retry_failed_conversations:
                raise ConfigurationError(
                    f"Cannot retry conversation '{conversation_id}' after "
                    "failed ingest without clean retry support"
                )
            skipped_failed_conversation_ids.append(conversation_id)
            continue
        if status == _STATUS_FAILED_ANSWER and not policy.retry_failed_conversations:
            skipped_failed_conversation_ids.append(conversation_id)
            continue
        pending_questions = tuple(
            question
            for question in selected_questions[conversation_id]
            if question.question_id not in completed_question_ids
        )
        needs_ingest = conversation_id not in ingested_conversation_ids
        if not needs_ingest and not pending_questions:
            continue
        if (
            policy.max_new_conversations is not None
            and unfinished_seen >= policy.max_new_conversations
        ):
            budget_exhausted = True
            continue
        unfinished_seen += 1
        items.append(
            _ConversationWorkItem(
                conversation=conversation,
                needs_ingest=needs_ingest,
                pending_questions=pending_questions,
            )
        )

    return _PredictionWorkPlan(
        items=tuple(items),
        conversation_order=conversation_order,
        selected_questions=selected_questions,
        question_order=question_order,
        completed_question_ids=completed_question_ids,
        ingested_conversation_ids=ingested_conversation_ids,
        skipped_failed_conversation_ids=tuple(skipped_failed_conversation_ids),
        dataset_conversation_count=len(conversations),
        budget_exhausted=budget_exhausted,
    )


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
        if not _manifests_match_for_resume(existing, manifest):
            raise ConfigurationError(
                "Resume manifest mismatch: dataset, method or run policy changed"
            )
        return
    if resume:
        raise ConfigurationError(
            f"Cannot resume because manifest is missing: {paths.manifest_path}"
        )


def _normalize_manifest_for_resume_compare(
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """去掉允许随命令变化的运行预算字段后再比较 manifest。

    `question_limit_per_conversation` 是本次命令预算，不属于实验身份。旧 manifest
    可能仍在 `policy` 中包含该字段，因此 resume 比较时需要忽略它。
    """

    normalized = json.loads(json.dumps(manifest))
    policy = normalized.get("policy")
    if isinstance(policy, dict):
        policy.pop("question_limit_per_conversation", None)
    return normalized


def _manifests_match_for_resume(
    existing: dict[str, Any],
    manifest: dict[str, Any],
) -> bool:
    """比较 resume manifest，并兼容 T3 前缺省的协议字段。"""

    existing_normalized = _normalize_manifest_for_resume_compare(existing)
    current_normalized = _normalize_manifest_for_resume_compare(manifest)
    existing_method = existing_normalized.get("method")
    current_method = current_normalized.get("method")
    if isinstance(existing_method, dict) and isinstance(current_method, dict):
        for key in ("protocol_version", "prompt_track", "profile"):
            if key not in existing_method or key not in current_method:
                existing_method.pop(key, None)
                current_method.pop(key, None)
    return existing_normalized == current_normalized


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


def _normalize_memory_system(system: _PredictionSystem) -> BaseMemorySystem | MemoryProvider:
    """把旧 retrieve-first provider 规范化为 v3 MemoryProvider。"""

    if isinstance(system, MemoryProvider):
        return system
    if isinstance(system, BaseMemoryProvider):
        return LegacyProviderBridge(system)
    return system


def _method_manifest_with_protocol(
    *,
    method_manifest: dict[str, object],
    system: BaseMemorySystem | MemoryProvider,
) -> dict[str, object]:
    """按实际 provider 类型补充协议身份字段。"""

    if not isinstance(system, MemoryProvider):
        return method_manifest
    normalized = dict(method_manifest)
    protocol_version = "v2-bridged" if isinstance(system, LegacyProviderBridge) else "v3"
    normalized.setdefault("protocol_version", protocol_version)
    normalized.setdefault("prompt_track", "native")
    normalized.setdefault("profile", {})
    return normalized


def _is_memory_provider(system: BaseMemorySystem | MemoryProvider) -> bool:
    """判断系统是否已经进入 v3 provider 路径。"""

    return isinstance(system, MemoryProvider)


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


def _split_into_chunks(
    items: list[Any],
    num_chunks: int,
) -> list[list[Any]]:
    """把 conversation 列表均匀分布到 num_chunks 个 chunk。

    最后剩余不足 num_chunks 的归入最后一个非满 chunk。
    """

    if num_chunks < 1:
        raise ConfigurationError("num_chunks must be at least 1")
    if num_chunks > len(items):
        num_chunks = len(items)
    chunks: list[list[Any]] = [[] for _ in range(num_chunks)]
    for idx, item in enumerate(items):
        chunks[idx % num_chunks].append(item)
    return chunks


def _split_work_items_by_stable_conversation_order(
    *,
    items: tuple[_ConversationWorkItem, ...],
    conversation_order: tuple[str, ...],
    num_workers: int,
) -> tuple[tuple[int, tuple[_ConversationWorkItem, ...]], ...]:
    """按完整 conversation 顺序稳定分配 isolated worker 工作项。

    `items` 只包含本次命令仍需推进的 conversation；resume 后它可能只剩一个
    conversation。如果直接对 `items` 重新分块，同一个 conversation 的 worker state
    目录会从 `worker_5` 变成 `worker_0`。因此 worker index 必须基于完整
    `conversation_order` 计算，保证同一 `run_id + max_workers + dataset` 下 state root
    稳定。
    """

    if num_workers < 1:
        raise ConfigurationError("num_workers must be at least 1")
    if not conversation_order:
        raise ConfigurationError("conversation_order cannot be empty")
    worker_count = min(num_workers, len(conversation_order))
    index_by_conversation = {
        conversation_id: index
        for index, conversation_id in enumerate(conversation_order)
    }
    chunks: dict[int, list[_ConversationWorkItem]] = {
        worker_idx: [] for worker_idx in range(worker_count)
    }
    for item in items:
        try:
            conversation_index = index_by_conversation[item.conversation.conversation_id]
        except KeyError as exc:
            raise ConfigurationError(
                "Work item conversation is missing from stable conversation order: "
                f"{item.conversation.conversation_id}"
            ) from exc
        worker_idx = conversation_index % worker_count
        chunks[worker_idx].append(item)
    return tuple(
        (worker_idx, tuple(chunk))
        for worker_idx, chunk in chunks.items()
        if chunk
    )


def _run_isolated_worker_pipeline(
    *,
    work_plan: _PredictionWorkPlan,
    system_factory: Callable[
        [MethodBuildContext],
        _PredictionSystem,
    ],
    build_context_template: MethodBuildContext,
    policy: PredictionRunPolicy,
    paths: ExperimentPaths,
    progress: ProgressReporter,
    logger: RunLogger,
    efficiency_collector: EfficiencyCollector | None,
    efficiency_store: EfficiencyArtifactStore | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
    prediction_records: dict[str, dict[str, Any]],
    conversation_status: dict[str, Any],
    question_status: dict[str, Any],
    question_order: list[str],
    run_id: str = "prediction-run",
    answer_reader: FrameworkAnswerReader | None = None,
) -> None:
    """使用独立 method instance 并行处理 conversation 的 ingest 与 answer。

    每个 worker 创建自己的 method instance（storage 隔离到 worker_{idx}/），
    在内部串行 ingest + answer 分配给它的 conversation 子集。
    协调线程串行写入 artifact，避免竞态。
    """

    progress.set_stage("Ingest + answer", step_index=1, step_count=2)
    if any(paths.ingest_turn_checkpoints_dir.glob("*.json")):
        raise ConfigurationError(
            "Isolated worker prediction cannot resume turn-level ingest checkpoints"
        )
    _conv_progress_total = (
        len(work_plan.ingested_conversation_ids) + len(work_plan.items)
    )
    _question_progress_total = (
        len(work_plan.completed_question_ids)
        + sum(len(item.pending_questions) for item in work_plan.items)
    )
    if not work_plan.items:
        progress.update_conversations(
            completed=len(work_plan.ingested_conversation_ids),
            total=_conv_progress_total,
            current_conversation_id=None,
        )
        progress.update_questions(
            completed=len(work_plan.completed_question_ids),
            total=_question_progress_total,
            current_conversation_id=None,
            current_question_id=None,
        )
        return

    chunks = _split_work_items_by_stable_conversation_order(
        items=work_plan.items,
        conversation_order=work_plan.conversation_order,
        num_workers=policy.max_workers,
    )
    conversation_ingested: int = len(work_plan.ingested_conversation_ids)
    question_answered: int = len(work_plan.completed_question_ids)
    cancellation_event = Event()
    answer_prompt_records = {
        record["question_id"]: record
        for record in read_jsonl(
            paths.answer_prompts_path,
            recover_torn_tail=policy.resume,
        )
    }
    session_report_records = read_jsonl(paths.session_memory_reports_path)

    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        future_to_chunk: dict[
            Future[
                tuple[_ConversationAnswerBatch | _ConversationFailureBatch, ...]
            ],
            int,
        ] = {}
        for worker_idx, chunk in chunks:
            worker_storage = (
                build_context_template.storage_root / f"worker_{worker_idx}"
            )
            completed_for_chunk = tuple(
                _make_public_conversation(item.conversation)
                for item in chunk
                if not item.needs_ingest
            )
            worker_context = MethodBuildContext(
                config=build_context_template.config,
                openai_settings=build_context_template.openai_settings,
                path_settings=build_context_template.path_settings,
                storage_root=worker_storage,
                completed_conversations=completed_for_chunk,
                efficiency_collector=build_context_template.efficiency_collector,
            )
            future = executor.submit(
                _isolated_worker,
                worker_context,
                system_factory,
                tuple(chunk),
                run_id,
                efficiency_collector,
                retrieval_observation_contract,
                answer_reader,
                answer_prompt_records,
                cancellation_event,
                policy.max_consecutive_failures,
            )
            future_to_chunk[future] = worker_idx

        for future in as_completed(future_to_chunk):
            try:
                batches = future.result()
            except Exception as exc:
                cancellation_event.set()
                for pending_future in future_to_chunk:
                    if pending_future is not future:
                        pending_future.cancel()
                if isinstance(exc, _ConversationWorkItemError):
                    logged_error = exc.original_error
                    failed_conversation_id = exc.conversation_id
                    conversation_status[exc.conversation_id] = {
                        "status": _STATUS_FAILED_INGEST,
                        "stage": exc.stage,
                        "error_type": type(logged_error).__name__,
                        "error": str(logged_error),
                        "ingested": False,
                        "worker_idx": future_to_chunk[future],
                    }
                    atomic_write_json(
                        paths.conversation_status_path,
                        conversation_status,
                    )
                else:
                    logged_error = exc
                    failed_conversation_id = None
                logger.log_event(
                    "isolated_worker_failed",
                    {
                        "worker_idx": future_to_chunk[future],
                        "conversation_id": failed_conversation_id,
                        "error_type": type(logged_error).__name__,
                        "error": str(logged_error),
                        "traceback": "".join(
                            traceback.format_exception(
                                type(exc),
                                exc,
                                exc.__traceback__,
                            )
                        ),
                    },
                )
                if isinstance(exc, _ConversationWorkItemError):
                    raise exc.original_error from exc
                raise
            if efficiency_store is not None:
                for batch in batches:
                    efficiency_store.merge_observations(batch.observations)
            for batch in batches:
                if batch.session_reports:
                    session_report_records.extend(batch.session_reports)
                for answer_prompt_record in batch.retrievals:
                    answer_prompt_records[answer_prompt_record["question_id"]] = (
                        answer_prompt_record
                    )
                if isinstance(batch, _ConversationFailureBatch):
                    for record in batch.predictions:
                        prediction_records[record["question_id"]] = record
                        question_status[record["question_id"]] = {
                            "question_id": record["question_id"],
                            "conversation_id": record["conversation_id"],
                            "status": "completed",
                        }
                        question_answered += 1
                    conversation_status[batch.conversation_id] = {
                        "status": (
                            _STATUS_FAILED_ANSWER
                            if batch.ingested
                            else _STATUS_FAILED_INGEST
                        ),
                        "stage": batch.stage,
                        "error_type": batch.error_type,
                        "error": batch.error,
                        "traceback": batch.traceback_text,
                        "ingested": batch.ingested,
                        "worker_idx": future_to_chunk[future],
                    }
                    progress.update_conversations(
                        completed=conversation_ingested,
                        total=_conv_progress_total,
                        current_conversation_id=batch.conversation_id,
                    )
                    progress.update_questions(
                        completed=question_answered,
                        total=_question_progress_total,
                        current_conversation_id=batch.conversation_id,
                        current_question_id=None,
                    )
                    logger.log_event(
                        "conversation_failed_isolated",
                        {
                            "worker_idx": future_to_chunk[future],
                            "conversation_id": batch.conversation_id,
                            "stage": batch.stage,
                            "error_type": batch.error_type,
                            "error": batch.error,
                            "traceback": batch.traceback_text,
                            "ingested": batch.ingested,
                        },
                    )
                    continue
                for record in batch.predictions:
                    prediction_records[record["question_id"]] = record
                    question_status[record["question_id"]] = {
                        "question_id": record["question_id"],
                        "conversation_id": record["conversation_id"],
                        "status": "completed",
                    }
                    question_answered += 1
                if batch.ingested:
                    conversation_ingested += 1
                    conversation_status[batch.conversation_id] = {
                        "status": _STATUS_COMPLETED,
                        "ingested": True,
                    }
                progress.update_conversations(
                    completed=conversation_ingested,
                    total=_conv_progress_total,
                    current_conversation_id=batch.conversation_id,
                )
                progress.update_questions(
                    completed=question_answered,
                    total=_question_progress_total,
                    current_conversation_id=batch.conversation_id,
                    current_question_id=None,
                )
                logger.log_event(
                    "conversation_completed_isolated",
                    {"conversation_id": batch.conversation_id},
                )
            atomic_write_jsonl(
                paths.method_predictions_path,
                [
                    prediction_records[qid]
                    for qid in question_order
                    if qid in prediction_records
                ],
            )
            atomic_write_jsonl(
                paths.question_status_path,
                [
                    question_status[qid]
                    for qid in question_order
                    if qid in question_status
                ],
            )
            _persist_answer_prompt_records(
                paths=paths,
                answer_prompt_records=answer_prompt_records,
                question_order=question_order,
            )
            _persist_session_memory_reports(
                paths=paths,
                session_report_records=session_report_records,
            )
            atomic_write_json(paths.conversation_status_path, conversation_status)

    progress.set_stage("Completed", step_index=2, step_count=2)


def _isolated_worker(
    build_context: MethodBuildContext,
    system_factory: Callable[
        [MethodBuildContext],
        _PredictionSystem,
    ],
    work_items: tuple[_ConversationWorkItem, ...],
    run_id: str,
    efficiency_collector: EfficiencyCollector | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
    answer_reader: FrameworkAnswerReader | None,
    existing_retrieval_records: dict[str, dict[str, Any]],
    cancellation_event: Event | None = None,
    max_consecutive_failures: int | None = 3,
) -> tuple[_ConversationAnswerBatch | _ConversationFailureBatch, ...]:
    """单个独立 worker：创建 method instance，串行处理分配到的 conversation。

    每个 worker 内按 conversation 顺序执行 add → get_answer，
    conversation 间无共享状态。
    """

    system = _normalize_memory_system(system_factory(build_context))
    results: list[_ConversationAnswerBatch | _ConversationFailureBatch] = []
    consecutive_failures = 0
    for work_item in work_items:
        if cancellation_event is not None and cancellation_event.is_set():
            break
        conversation = work_item.conversation
        conv_predictions: list[dict[str, Any]] = []
        conv_retrievals: list[dict[str, Any]] = []
        conv_session_reports: list[dict[str, Any]] = []
        conv_observations: list[EfficiencyObservation] = []
        ingested = not work_item.needs_ingest
        try:
            public_conversation = _make_public_conversation(conversation)
            if work_item.needs_ingest:
                if (
                    efficiency_collector is not None
                    and efficiency_collector.enabled
                ):
                    started_ns = perf_counter_ns()
                    with efficiency_collector.conversation_scope(
                        conversation.conversation_id,
                    ) as conv_scope:
                        conv_session_reports.extend(
                            _add_public_conversation_coarse(
                                system=system,
                                run_id=run_id,
                                public_conversation=public_conversation,
                            )
                        )
                        efficiency_collector.record_memory_build_total_latency(
                            latency_ms=_elapsed_ms(started_ns),
                        )
                    conv_observations.extend(conv_scope.records)
                else:
                    conv_session_reports.extend(
                        _add_public_conversation_coarse(
                            system=system,
                            run_id=run_id,
                            public_conversation=public_conversation,
                        )
                    )
                ingested = True
            for source_question in work_item.pending_questions:
                question = _make_public_question(source_question)
                validate_no_private_keys(question.to_dict())
                if (
                    efficiency_collector is not None
                    and efficiency_collector.enabled
                ):
                    with efficiency_collector.question_scope(
                        conversation.conversation_id,
                        question.question_id,
                    ) as scope:
                        if _is_memory_provider(system):
                            prediction, retrieval_record = (
                                _answer_question_retrieve_first_or_reuse(
                                    provider=system,
                                    question=question,
                                    run_id=run_id,
                                    answer_reader=answer_reader,
                                    efficiency_collector=efficiency_collector,
                                    existing_retrieval_records=existing_retrieval_records,
                                )
                            )
                            if retrieval_record is not None:
                                conv_retrievals.append(retrieval_record)
                        else:
                            if not isinstance(
                                retrieval_observation_contract,
                                RetrievalObservationContract,
                            ):
                                raise ConfigurationError(
                                    "Enabled efficiency observability requires an "
                                    "explicit retrieval observation contract"
                                )
                            prediction = system.get_answer(question)
                            if (
                                not retrieval_observation_contract.supported_by_method
                            ):
                                efficiency_collector.record_retrieval_unsupported_if_missing(
                                    retrieval_observation_contract.unsupported_reason
                                    or ""
                                )
                    conv_observations.extend(scope.records)
                else:
                    if _is_memory_provider(system):
                        prediction, retrieval_record = (
                            _answer_question_retrieve_first_or_reuse(
                                provider=system,
                                question=question,
                                run_id=run_id,
                                answer_reader=answer_reader,
                                efficiency_collector=None,
                                existing_retrieval_records=existing_retrieval_records,
                            )
                        )
                        if retrieval_record is not None:
                            conv_retrievals.append(retrieval_record)
                    else:
                        prediction = system.get_answer(question)
                _validate_prediction(prediction, question)
                validate_no_private_keys(prediction.metadata)
                conv_predictions.append(
                    {
                        "question_id": question.question_id,
                        "conversation_id": conversation.conversation_id,
                        "question_text": question.text,
                        "answer": prediction.answer,
                        "metadata": prediction.metadata,
                    }
                )
        except Exception as exc:
            results.append(
                _ConversationFailureBatch(
                    conversation_id=conversation.conversation_id,
                    stage="isolated_worker",
                    error_type=type(exc).__name__,
                    error=str(exc),
                    traceback_text="".join(
                        traceback.format_exception(type(exc), exc, exc.__traceback__)
                    ),
                    observations=tuple(conv_observations),
                    predictions=tuple(conv_predictions),
                    retrievals=tuple(
                        conv_retrievals
                        + list(getattr(exc, "retrievals", ()))
                    ),
                    session_reports=tuple(conv_session_reports),
                    ingested=ingested,
                )
            )
            consecutive_failures += 1
            if (
                max_consecutive_failures is not None
                and consecutive_failures >= max_consecutive_failures
            ):
                if cancellation_event is not None:
                    cancellation_event.set()
                break
            continue
        results.append(
            _ConversationAnswerBatch(
                conversation_id=conversation.conversation_id,
                predictions=tuple(conv_predictions),
                retrievals=tuple(conv_retrievals),
                session_reports=tuple(conv_session_reports),
                observations=tuple(conv_observations),
                ingested=work_item.needs_ingest,
            )
        )
        consecutive_failures = 0
    return tuple(results)


def _add_public_conversation_coarse(
    *,
    system: BaseMemorySystem | MemoryProvider,
    run_id: str,
    public_conversation: Conversation,
) -> tuple[dict[str, Any], ...]:
    """isolated worker 使用的 conversation 级写入，不处理逐 turn checkpoint。"""

    if isinstance(system, MemoryProvider):
        return _ingest_memory_provider_conversation(
            provider=system,
            public_conversation=public_conversation,
            run_id=run_id,
        )
    result = system.add([public_conversation])
    if result is None:
        return ()
    if public_conversation.conversation_id not in result.conversation_ids:
        raise ConfigurationError(
            "Method add result did not include expected conversation_id: "
            f"{public_conversation.conversation_id}"
        )
    return ()


def _ingest_pending_conversations(
    conversations: list[Conversation],
    system: BaseMemorySystem | MemoryProvider,
    run_id: str,
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

    session_report_records = read_jsonl(paths.session_memory_reports_path)
    with ThreadPoolExecutor(max_workers=policy.max_workers) as executor:
        futures: dict[Future[_ConversationIngestBatch], str] = {
            executor.submit(
                _ingest_one,
                system,
                conversation,
                run_id,
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
                    "status": _STATUS_FAILED_INGEST,
                    "stage": "ingest",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "ingested": False,
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
            if batch.session_reports:
                session_report_records.extend(batch.session_reports)
                _persist_session_memory_reports(
                    paths=paths,
                    session_report_records=session_report_records,
                )
            returned_id = batch.conversation_id
            conversation = next(
                item
                for item in pending
                if item.conversation_id == returned_id
            )
            if _uses_turn_resume(system, conversation):
                checkpoint_store.mark_conversation_completed(
                    conversation_id=returned_id,
                    total_turns=_conversation_turn_count(conversation),
                )
            conversation_status[returned_id] = {
                "status": _STATUS_COMPLETED,
                "ingested": True,
            }
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
    system: BaseMemorySystem | MemoryProvider,
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
        if not _uses_turn_resume(system, conversation):
            raise ConfigurationError(
                "Turn ingest checkpoint exists, but method does not enable "
                "turn-level resume for conversation: "
                f"{conversation.conversation_id}"
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
        elif checkpoint.status == "ready":
            conversation_status[conversation_id] = {
                "status": "ready_for_turn_resume"
            }

    return checkpoints


def _ingest_one(
    system: BaseMemorySystem | MemoryProvider,
    conversation: Conversation,
    run_id: str,
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
            session_reports = _add_public_conversation(
                system=system,
                public_conversation=public_conversation,
                run_id=run_id,
                checkpoint_store=checkpoint_store,
                checkpoint=checkpoint,
            )
            efficiency_collector.record_memory_build_total_latency(
                latency_ms=_elapsed_ms(started_ns)
            )
        return _ConversationIngestBatch(
            conversation_id=conversation.conversation_id,
            session_reports=session_reports,
            observations=scope.records,
        )

    session_reports = _add_public_conversation(
        system=system,
        public_conversation=public_conversation,
        run_id=run_id,
        checkpoint_store=checkpoint_store,
        checkpoint=checkpoint,
    )
    return _ConversationIngestBatch(
        conversation_id=conversation.conversation_id,
        session_reports=session_reports,
    )


def _add_public_conversation(
    *,
    system: BaseMemorySystem | MemoryProvider,
    public_conversation: Conversation,
    run_id: str,
    checkpoint_store: TurnIngestCheckpointStore,
    checkpoint: TurnIngestCheckpoint | None,
) -> tuple[dict[str, Any], ...]:
    """执行一次公开 conversation 写入，并校验 method 返回 id。"""

    if _uses_turn_resume(system, public_conversation):
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
    elif isinstance(system, MemoryProvider):
        return _ingest_memory_provider_conversation(
            provider=system,
            public_conversation=public_conversation,
            run_id=run_id,
        )
    else:
        result = system.add([public_conversation])
    if public_conversation.conversation_id not in result.conversation_ids:
        raise ConfigurationError(
            "Method add result did not include expected conversation_id: "
            f"{public_conversation.conversation_id}"
        )
    return ()


def _ingest_memory_provider_conversation(
    *,
    provider: MemoryProvider,
    public_conversation: Conversation,
    run_id: str,
) -> tuple[dict[str, Any], ...]:
    """用 v3 conversation batch 调用 provider.ingest 并完成边界回调。"""

    isolation_key = default_isolation_key(run_id, public_conversation.conversation_id)
    events = tuple(build_turn_events(public_conversation, isolation_key))
    session_report_records: list[dict[str, Any]] = []
    units = tuple(
        GranularityAggregator(provider.consume_granularity).aggregate(
            events,
            isolation_key=isolation_key,
        )
    )
    for unit in units:
        if _is_ingest_unit(unit):
            result = provider.ingest(unit)
            session_report_records.extend(
                _session_reports_from_ingest_result(
                    provider=provider,
                    unit=unit,
                    result=result,
                    conversation_id=public_conversation.conversation_id,
                )
            )
            continue
        if isinstance(unit, SessionRef):
            report = provider.end_session(unit)
            if report is not None:
                session_report_records.append(
                    _session_memory_report_payload(
                        report=report,
                        conversation_id=public_conversation.conversation_id,
                        source="end_session",
                    )
                )
            continue
        if isinstance(unit, UnitRef):
            provider.end_conversation(unit)
    if provider.session_memory_report and not session_report_records:
        raise ConfigurationError(
            "Provider declared session_memory_report=True but returned no "
            f"session memory reports: {public_conversation.conversation_id}"
        )
    return tuple(session_report_records)


def _is_ingest_unit(unit: object) -> bool:
    """判断 stream signal 是否应投递给 provider.ingest。"""

    return isinstance(
        unit,
        TurnEvent | TurnPair | SessionBatch | ConversationBatch,
    )


def _session_reports_from_ingest_result(
    *,
    provider: MemoryProvider,
    unit: IngestUnit,
    result: IngestResult | None,
    conversation_id: str,
) -> tuple[dict[str, Any], ...]:
    """把 IngestResult.session_memories 转成 artifact records。"""

    if not provider.session_memory_report or result is None:
        return ()
    if not result.session_memories:
        return ()
    session_ref = _session_ref_from_ingest_result(unit=unit, result=result)
    return (
        {
            "conversation_id": conversation_id,
            "source": "ingest_result",
            "session_ref": asdict(session_ref),
            "memories": list(result.session_memories),
            "metadata": dict(result.metadata),
        },
    )


def _session_ref_from_ingest_result(
    *,
    unit: IngestUnit,
    result: IngestResult,
) -> SessionRef:
    """从 ingest unit/result 中推断 session memory report 的 session ref。"""

    if isinstance(result.unit_ref, SessionRef):
        return result.unit_ref
    if isinstance(unit, SessionBatch):
        return unit.ref
    if isinstance(unit, TurnEvent):
        return SessionRef(
            isolation_key=unit.isolation_key,
            session_id=unit.session_id,
        )
    if isinstance(unit, TurnPair):
        return SessionRef(
            isolation_key=unit.isolation_key,
            session_id=unit.session_id,
        )
    return SessionRef(
        isolation_key=unit.isolation_key,
        session_id=None,
    )


def _session_memory_report_payload(
    *,
    report: SessionMemoryReport,
    conversation_id: str,
    source: str,
) -> dict[str, Any]:
    """把 SessionMemoryReport 转成公开 artifact record。"""

    return {
        "conversation_id": conversation_id,
        "source": source,
        "session_ref": asdict(report.session_ref),
        "memories": list(report.memories),
        "metadata": dict(report.metadata),
    }


def _uses_turn_resume(
    system: BaseMemorySystem | MemoryProvider,
    conversation: Conversation,
) -> bool:
    """判断当前 method/conversation 是否使用逐 turn checkpoint。"""

    return isinstance(system, BaseResumableMemorySystem) and system.supports_turn_resume(
        conversation
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
    system: BaseMemorySystem | MemoryProvider,
    run_id: str,
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
    answer_reader: FrameworkAnswerReader | None,
) -> None:
    """按 conversation 并发回答问题，并由协调线程提交完整 batch。"""

    progress.set_stage("Answer questions", step_index=2, step_count=3)
    answer_prompt_records = {
        record["question_id"]: record
        for record in read_jsonl(
            paths.answer_prompts_path,
            recover_torn_tail=policy.resume,
        )
    }
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

    _answer_question_progress_total = completed + sum(
        len(qs) for qs in pending_by_conversation.values()
    )

    with ThreadPoolExecutor(max_workers=policy.max_workers) as executor:
        futures: dict[Future[_ConversationAnswerBatch], str] = {
            executor.submit(
                _answer_conversation_questions,
                system,
                run_id,
                conversation_id,
                questions,
                efficiency_collector,
                retrieval_observation_contract,
                answer_reader,
                answer_prompt_records,
            ): conversation_id
            for conversation_id, questions in pending_by_conversation.items()
        }
        for future in as_completed(futures):
            conversation_id = futures[future]
            try:
                batch = future.result()
            except Exception as exc:
                logged_error: Exception = exc
                if isinstance(exc, _RetrieveFirstAnswerError):
                    logged_error = exc.original_error
                    for answer_prompt_record in exc.retrievals:
                        answer_prompt_records[answer_prompt_record["question_id"]] = (
                            answer_prompt_record
                        )
                    _persist_answer_prompt_records(
                        paths=paths,
                        answer_prompt_records=answer_prompt_records,
                        question_order=question_order,
                    )
                logger.log_event(
                    "question_batch_failed",
                    {
                        "conversation_id": conversation_id,
                        "stage": "answer",
                        "error_type": type(logged_error).__name__,
                    },
                )
                if isinstance(exc, _RetrieveFirstAnswerError):
                    raise exc.original_error from exc
                raise
            if efficiency_store is not None:
                efficiency_store.merge_observations(batch.observations)
            for answer_prompt_record in batch.retrievals:
                answer_prompt_records[answer_prompt_record["question_id"]] = (
                    answer_prompt_record
                )
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
                    total=_answer_question_progress_total,
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
            _persist_answer_prompt_records(
                paths=paths,
                answer_prompt_records=answer_prompt_records,
                question_order=question_order,
            )
            atomic_write_jsonl(
                paths.question_status_path,
                [
                    question_status[question_id]
                    for question_id in question_order
                    if question_id in question_status
                ],
            )


def _persist_answer_prompt_records(
    *,
    paths: ExperimentPaths,
    answer_prompt_records: dict[str, dict[str, Any]],
    question_order: list[str],
) -> None:
    """按 question_order 稳定写入 method 生成的完整 answer prompt artifact。"""

    if not answer_prompt_records:
        return
    atomic_write_jsonl(
        paths.answer_prompts_path,
        [
            answer_prompt_records[question_id]
            for question_id in question_order
            if question_id in answer_prompt_records
        ],
    )


def _persist_session_memory_reports(
    *,
    paths: ExperimentPaths,
    session_report_records: list[dict[str, Any]],
) -> None:
    """稳定写入 provider session memory report artifact。"""

    if not session_report_records:
        return
    atomic_write_jsonl(paths.session_memory_reports_path, session_report_records)


def _answer_conversation_questions(
    system: BaseMemorySystem | MemoryProvider,
    run_id: str,
    conversation_id: str,
    questions: list[Question],
    efficiency_collector: EfficiencyCollector | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
    answer_reader: FrameworkAnswerReader | None,
    existing_retrieval_records: dict[str, dict[str, Any]] | None = None,
) -> _ConversationAnswerBatch:
    """worker 内串行回答一个 conversation 的所有待处理问题。"""

    records: list[dict[str, Any]] = []
    retrieval_records: list[dict[str, Any]] = []
    observations: list[EfficiencyObservation] = []
    existing_retrieval_records = existing_retrieval_records or {}
    for source_question in questions:
        question = _make_public_question(source_question)
        validate_no_private_keys(question.to_dict())
        if efficiency_collector is not None and efficiency_collector.enabled:
            with efficiency_collector.question_scope(
                conversation_id,
                question.question_id,
            ) as scope:
                if _is_memory_provider(system):
                    prediction, retrieval_record = (
                        _answer_question_retrieve_first_or_reuse(
                            provider=system,
                            question=question,
                            run_id=run_id,
                            answer_reader=answer_reader,
                            efficiency_collector=efficiency_collector,
                            existing_retrieval_records=existing_retrieval_records,
                        )
                    )
                else:
                    if not isinstance(
                        retrieval_observation_contract,
                        RetrievalObservationContract,
                    ):
                        raise ConfigurationError(
                            "Enabled efficiency observability requires an explicit "
                            "retrieval observation contract"
                        )
                    prediction = system.get_answer(question)
                    retrieval_record = None
                    if not retrieval_observation_contract.supported_by_method:
                        efficiency_collector.record_retrieval_unsupported_if_missing(
                            retrieval_observation_contract.unsupported_reason or ""
                        )
                if retrieval_record is not None:
                    retrieval_records.append(retrieval_record)
            observations.extend(scope.records)
        else:
            if _is_memory_provider(system):
                prediction, retrieval_record = _answer_question_retrieve_first_or_reuse(
                    provider=system,
                    question=question,
                    run_id=run_id,
                    answer_reader=answer_reader,
                    efficiency_collector=None,
                    existing_retrieval_records=existing_retrieval_records,
                )
                if retrieval_record is not None:
                    retrieval_records.append(retrieval_record)
            else:
                prediction = system.get_answer(question)
                retrieval_record = None
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
        retrievals=tuple(retrieval_records),
        observations=tuple(observations),
    )


def _answer_question_retrieve_first(
    *,
    provider: MemoryProvider,
    question: Question,
    run_id: str,
    answer_reader: FrameworkAnswerReader | None,
    efficiency_collector: EfficiencyCollector | None,
) -> tuple[AnswerResult, dict[str, Any]]:
    """执行 retrieve -> framework reader，并返回 prediction 和 answer prompt record。"""

    if answer_reader is None:
        raise ConfigurationError("Retrieve-first prediction requires answer_reader")

    started_ns = perf_counter_ns()
    if efficiency_collector is not None and efficiency_collector.enabled:
        with efficiency_collector.operation_stage(EfficiencyStage.RETRIEVAL):
            retrieval_result = provider.retrieve(
                _retrieval_query_from_question(question=question, run_id=run_id)
            )
    else:
        retrieval_result = provider.retrieve(
            _retrieval_query_from_question(question=question, run_id=run_id)
        )
    retrieval = _answer_prompt_from_retrieval_result(
        question=question,
        retrieval_result=retrieval_result,
    )
    _validate_retrieval(retrieval, question)
    if efficiency_collector is not None and efficiency_collector.enabled:
        efficiency_collector.record_retrieval_result_if_missing(
            latency_ms=_elapsed_ms(started_ns),
            injected_memory_context_tokens=_count_answer_context_tokens(
                retrieval.metadata,
                answer_reader.client.model_name,
            ),
        )

    answer_prompt_record = {
        "question_id": retrieval.question_id,
        "conversation_id": retrieval.conversation_id,
        "answer_prompt": retrieval.answer_prompt,
        "prompt_messages": [
            message.to_dict() for message in retrieval.prompt_messages
        ],
        "metadata": retrieval.metadata,
        "formatted_memory": retrieval_result.formatted_memory,
        "retrieved_items": _retrieved_items_payload(retrieval_result),
    }
    validate_no_private_keys(answer_prompt_record)

    answer_started_ns = perf_counter_ns()
    try:
        prediction, answer_prompt, answer_response = answer_reader.generate_answer_with_trace(
            question=question,
            retrieval=retrieval,
        )
    except Exception as exc:
        raise _RetrieveFirstAnswerError(
            original_error=exc,
            retrievals=(answer_prompt_record,),
        ) from exc
    if efficiency_collector is not None and efficiency_collector.enabled:
        with efficiency_collector.operation_stage(EfficiencyStage.ANSWER):
            _record_framework_answer_llm_call(
                efficiency_collector=efficiency_collector,
                model_id=answer_reader.client.model_name,
                model_name=answer_reader.client.model_name,
                prompt_text=answer_prompt,
                answer_text=prediction.answer,
                response=answer_response,
            )
        efficiency_collector.record_answer_generation(
            latency_ms=_elapsed_ms(answer_started_ns)
        )
    return prediction, answer_prompt_record


def _answer_question_retrieve_first_or_reuse(
    *,
    provider: MemoryProvider,
    question: Question,
    run_id: str,
    answer_reader: FrameworkAnswerReader | None,
    efficiency_collector: EfficiencyCollector | None,
    existing_retrieval_records: dict[str, dict[str, Any]],
) -> tuple[AnswerResult, dict[str, Any] | None]:
    """复用已落盘 retrieval，或执行新的 retrieve-first question 流程。"""

    existing_record = existing_retrieval_records.get(question.question_id)
    if existing_record is not None:
        if answer_reader is None:
            raise ConfigurationError("Retrieve-first prediction requires answer_reader")
        retrieval = _retrieval_from_record(existing_record)
        _validate_retrieval(retrieval, question)
        answer_started_ns = perf_counter_ns()
        prediction, answer_prompt, answer_response = answer_reader.generate_answer_with_trace(
            question=question,
            retrieval=retrieval,
        )
        if efficiency_collector is not None and efficiency_collector.enabled:
            with efficiency_collector.operation_stage(EfficiencyStage.ANSWER):
                _record_framework_answer_llm_call(
                    efficiency_collector=efficiency_collector,
                    model_id=answer_reader.client.model_name,
                    model_name=answer_reader.client.model_name,
                    prompt_text=answer_prompt,
                    answer_text=prediction.answer,
                    response=answer_response,
                )
            efficiency_collector.record_answer_generation(
                latency_ms=_elapsed_ms(answer_started_ns)
            )
        return prediction, None

    return _answer_question_retrieve_first(
        provider=provider,
        question=question,
        run_id=run_id,
        answer_reader=answer_reader,
        efficiency_collector=efficiency_collector,
    )


def _retrieval_query_from_question(
    *,
    question: Question,
    run_id: str,
) -> RetrievalQuery:
    """由公开 Question 构造 v3 RetrievalQuery。"""

    return RetrievalQuery(
        query_text=question.text,
        isolation_key=default_isolation_key(run_id, question.conversation_id),
        question_time=question.question_time,
        top_k=10,
        purpose="qa",
        source_question=question,
    )


def _answer_prompt_from_retrieval_result(
    *,
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """把 v3 RetrievalResult 转换为现有 answer reader 输入。"""

    if not retrieval_result.prompt_messages:
        raise ConfigurationError(
            "RetrievalResult.prompt_messages is required while prompt_track is native: "
            f"{question.question_id}"
        )
    legacy_answer_prompt = retrieval_result.metadata.get("bridge_legacy_answer_prompt")
    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        answer_prompt=legacy_answer_prompt if isinstance(legacy_answer_prompt, str) else "",
        prompt_messages=list(retrieval_result.prompt_messages),
        metadata=dict(retrieval_result.metadata),
    )


def _retrieved_items_payload(retrieval_result: RetrievalResult) -> list[dict[str, Any]]:
    """把 v3 retrieved items 转成 artifact 载荷。"""

    if retrieval_result.items is None:
        return []
    return [asdict(item) for item in retrieval_result.items]


def _retrieval_from_record(record: dict[str, Any]) -> AnswerPromptResult:
    """从 answer prompt artifact 还原 AnswerPromptResult。"""

    prompt_messages = [
        PromptMessage(
            role=str(message["role"]),
            content=str(message["content"]),
        )
        for message in record.get("prompt_messages") or []
    ]
    return AnswerPromptResult(
        question_id=str(record["question_id"]),
        conversation_id=str(record["conversation_id"]),
        answer_prompt=str(record.get("answer_prompt") or ""),
        prompt_messages=prompt_messages,
        metadata=dict(record.get("metadata") or {}),
    )


def _validate_retrieval(retrieval: AnswerPromptResult, question: Question) -> None:
    """校验 retrieve 输出与公开问题严格对齐。"""

    if retrieval.question_id != question.question_id:
        raise ConfigurationError(
            f"Retrieval question_id mismatch: {retrieval.question_id} != "
            f"{question.question_id}"
        )
    if retrieval.conversation_id != question.conversation_id:
        raise ConfigurationError(
            "Retrieval conversation_id mismatch: "
            f"{retrieval.conversation_id} != {question.conversation_id}"
        )
    if not retrieval.prompt_messages:
        raise ConfigurationError(
            f"Retrieval prompt_messages is empty: {question.question_id}"
        )
    if not retrieval.answer_prompt.strip():
        retrieval.answer_prompt = "\n\n".join(
            f"[{message.role}]\n{message.content}"
            for message in retrieval.prompt_messages
        )
    validate_no_private_keys(retrieval.metadata)


def _count_bridge_empty_memory_sentinel(answer_prompts_path: Path) -> int:
    """统计桥接 sentinel fallback 在 answer prompt artifact 中出现次数。"""

    return sum(
        1
        for record in read_jsonl(answer_prompts_path)
        if record.get("formatted_memory") == BRIDGE_EMPTY_MEMORY_SENTINEL
    )


def _count_answer_context_tokens(
    metadata: dict[str, Any],
    model_name: str,
) -> int | None:
    """如果 method 提供 answer_context，则计算该诊断字段的 token 数。"""

    answer_context = metadata.get("answer_context")
    if not isinstance(answer_context, str) or not answer_context.strip():
        return None
    return _count_openai_compatible_tokens(answer_context, model_name)


def _elapsed_ms(started_ns: int) -> float:
    """把 `perf_counter_ns()` 起点转换为正的毫秒耗时。"""

    return max((perf_counter_ns() - started_ns) / 1_000_000, 0.0)


def _count_openai_compatible_tokens(text: str, model_name: str) -> int:
    """按 framework answer LLM 的 OpenAI-compatible tokenizer 估算文本 token。"""

    if not text:
        return 0
    try:
        import tiktoken
    except Exception as exc:
        raise ConfigurationError(
            "tiktoken is required for framework answer context token estimation"
        ) from exc
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


class _OpenAICompatibleTokenCounter:
    """按 OpenAI-compatible 模型名计数 token 的 runner 侧轻量 wrapper。"""

    def __init__(self, model_name: str) -> None:
        """保存模型名，encoding 懒加载。"""

        self.model_name = model_name
        self._encoding = None

    def count_tokens(self, text: str) -> int:
        """返回文本 token 数；未知模型回退到 cl100k_base。"""

        if self._encoding is None:
            try:
                import tiktoken
            except Exception as exc:
                raise ConfigurationError(
                    "tiktoken is required for framework answer token estimation"
                ) from exc
            try:
                self._encoding = tiktoken.encoding_for_model(self.model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return len(self._encoding.encode(text or ""))


def _record_framework_answer_llm_call(
    *,
    efficiency_collector: EfficiencyCollector,
    model_id: str,
    model_name: str,
    prompt_text: str,
    answer_text: str,
    response: AnswerLLMResponse,
) -> None:
    """记录 framework reader answer LLM 的 token usage。"""

    api_input_tokens, api_output_tokens = extract_api_token_usage(response.usage)
    token_usage = resolve_token_usage(
        api_input_tokens=api_input_tokens,
        api_output_tokens=api_output_tokens,
        prompt_text=prompt_text,
        output_text=answer_text,
        tokenizer=_OpenAICompatibleTokenCounter(model_name),
    )
    efficiency_collector.record_llm_call(
        model_id=model_id,
        input_tokens=token_usage.input_tokens,
        output_tokens=token_usage.output_tokens,
        token_measurement_source=token_usage.source,
    )


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
    forbidden_fragments = ("api_key", "secret", "password")
    forbidden_token_keys = frozenset(
        {
            "token",
            "api_token",
            "access_token",
            "auth_token",
            "bearer_token",
            "id_token",
            "refresh_token",
        }
    )

    def walk(value: Any, path: str) -> None:
        """递归检查嵌套 manifest 的字段名称。"""

        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).lower()
                if any(fragment in normalized for fragment in forbidden_fragments) or (
                    normalized in forbidden_token_keys
                    or normalized.endswith("_token")
                    or normalized.endswith("-token")
                ):
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


def _build_conversation_prompts(
    prediction_records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """从已完成预测记录中提取每个 conversation 的共享 prompt 文本。

    同一 conversation 的首条记录的 `metadata.system_prompt` 被作为该 conversation
    的共享 prompt。后续问题记录中该字段已去重移除。
    """

    prompts: dict[str, dict[str, Any]] = {}
    for record in prediction_records.values():
        conv_id = record["conversation_id"]
        if conv_id in prompts:
            continue
        extracted: dict[str, Any] = {}
        for key in _CONVERSATION_LEVEL_METADATA_KEYS:
            value = record.get("metadata", {}).get(key)
            if value is not None:
                extracted[key] = value
        if extracted:
            prompts[conv_id] = extracted
    return prompts


def _strip_conversation_metadata(
    prediction_records: dict[str, dict[str, Any]],
) -> None:
    """从所有预测记录的 metadata 中移除已去重的 conversation 级字段。"""

    for record in prediction_records.values():
        metadata = record.get("metadata", {})
        if not metadata:
            continue
        for key in _CONVERSATION_LEVEL_METADATA_KEYS:
            metadata.pop(key, None)


__all__ = [
    "PredictionRunPolicy",
    "PredictionRunSummary",
    "run_predictions",
]

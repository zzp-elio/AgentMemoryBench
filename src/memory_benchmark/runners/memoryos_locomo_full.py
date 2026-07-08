"""MemoryOS-LoCoMo 全量 F1 legacy runner。

本模块只保留给历史 MemoryOS run 的复查与复现使用。新实验必须走统一的
`predict/evaluate/run` 入口，新 generic run 不能拿这里的根目录 legacy alias 做
resume 或混跑。该模块仍按 `conversation_id` 隔离 MemoryOS 状态，逐题写入预测和分数，
并支持从已完成的 checkpoint 继续，以便复现旧运行行为。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from memory_benchmark.benchmark_adapters.locomo import LoCoMoAdapter
from memory_benchmark.config.settings import load_path_settings
from memory_benchmark.core import AnswerResult, Conversation, Question
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.evaluators.locomo_f1 import LoCoMoF1Evaluator
from memory_benchmark.methods import memoryos_adapter as memoryos_adapter_module
from memory_benchmark.methods.memoryos_adapter import MemoryOSPaperConfig
from memory_benchmark.observability import ProgressReporter, RunContext
from memory_benchmark.runners.conversation_qa import (
    _make_public_conversation,
    _make_public_question,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    JsonlWriter,
    atomic_write_json,
    atomic_write_jsonl,
    build_dataset_fingerprint,
    evaluator_private_label_record,
    public_question_record,
    read_jsonl,
)
from memory_benchmark.utils.run_logger import RunLogger


MemoryOS = memoryos_adapter_module.MemoryOS


@dataclass(frozen=True)
class MemoryOSLoCoMoFullSummary:
    """MemoryOS-LoCoMo 全量运行摘要。

    字段:
        run_id: 本次运行 id。
        dataset_name: 数据集名。
        total_conversations: 本次加载的 conversation 数。
        completed_conversations: 至少完成 add 的 conversation 数。
        total_questions: 本次计划评测的 question 数。
        completed_questions: 已完成评分的 question 数。
        overall_f1: 所有已完成 question 的平均 F1。
        f1_by_category: 按 LoCoMo category 聚合的平均 F1。
        count_by_category: 每个 category 已完成 question 数。
        prediction_path: JSONL 预测输出路径。
        score_path: JSONL 分数输出路径。
        summary_path: summary JSON 输出路径。
        log_dir: 日志目录。
        metadata: 公开附加信息。
    """

    run_id: str
    dataset_name: str
    total_conversations: int
    completed_conversations: int
    total_questions: int
    completed_questions: int
    overall_f1: float
    f1_by_category: dict[str, float] = field(default_factory=dict)
    count_by_category: dict[str, int] = field(default_factory=dict)
    prediction_path: str = ""
    score_path: str = ""
    summary_path: str = ""
    log_dir: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换成 JSON 可序列化字典。

        输入:
            无。

        输出:
            dict[str, Any]: 本次运行摘要。
        """

        return asdict(self)


@contextmanager
def _progress_scope(progress: ProgressReporter):
    """管理 progress 生命周期，并在主流程失败时保留原始异常。

    输入:
        progress: 当前运行的进度报告器。

    输出:
        Iterator[ProgressReporter]: 已进入的进度报告器。

    异常:
        主流程异常存在时，忽略 progress 退出阶段的次生异常并原样重抛主异常；
        主流程成功时，progress 退出异常正常向上传播。
    """

    progress.__enter__()
    try:
        yield progress
    except BaseException as operational_error:
        try:
            progress.__exit__(
                type(operational_error),
                operational_error,
                operational_error.__traceback__,
            )
        except BaseException:
            pass
        raise
    else:
        progress.__exit__(None, None, None)


def run_memoryos_locomo_full(
    project_root: str | Path | None = None,
    output_root: str | Path | None = None,
    run_id: str | None = None,
    conversation_limit: int | None = None,
    question_limit_per_conversation: int | None = None,
    resume: bool = True,
    confirm_expensive: bool = False,
    show_progress: bool = True,
) -> MemoryOSLoCoMoFullSummary:
    """运行历史 MemoryOS-LoCoMo 全量 F1 评测。

    输入:
        project_root: 项目根目录；为空时自动解析。
        output_root: 输出根目录；为空时使用配置层 `outputs_root`。
        run_id: 本次运行 id；为空时自动生成。
        conversation_limit: 可选 conversation 数限制；None 表示全量 LoCoMo。
        question_limit_per_conversation: 可选每个 conversation 的问题数限制。
        resume: True 时读取已有 predictions/scores/status 并跳过已完成问题。
        confirm_expensive: True 时允许论文默认配置触发大量 MemoryOS 更新调用。
        show_progress: True 时显示 Rich 终端进度；关闭时仍写 progress.json。

    说明:
        本入口仅用于历史 MemoryOS run 的解释、复现和旧 checkpoint 读取；
        新实验必须使用统一 `predict/evaluate/run`，且不要把新 generic run 与旧
        根目录 alias 的 resume 状态混用。

    输出:
        MemoryOSLoCoMoFullSummary: 聚合 F1 和输出文件路径。
    """

    path_settings = load_path_settings(project_root=project_root)
    selected_output_root = Path(output_root or path_settings.outputs_root).resolve()
    selected_run_id = run_id or f"memoryos-locomo-full-{uuid4().hex[:8]}"
    run_dir = selected_output_root / selected_run_id
    _prepare_run_dir(run_dir, resume=resume)
    config = MemoryOSPaperConfig()
    run_context = RunContext.create(
        run_id=selected_run_id,
        benchmark_name="locomo",
        method_name="MemoryOS",
        model_name=config.llm_model,
        output_root=selected_output_root,
        resume=resume,
    )
    paths = ExperimentPaths.create(run_context.run_dir)
    run_dir = paths.run_dir
    attempt_id = uuid4().hex
    event_context = {
        "attempt_id": attempt_id,
        "resume": resume,
    }
    logger = RunLogger(paths.logs_dir)
    logger.info(
        f"MemoryOS-LoCoMo full run started run_id={selected_run_id} resume={resume}"
    )
    logger.log_event(
        "full_run_started",
        {
            "run_id": selected_run_id,
            **event_context,
            "confirm_expensive": confirm_expensive,
        },
    )
    progress: ProgressReporter | None = None
    current_stage: str | None = None
    current_conversation_id: str | None = None
    current_question_id: str | None = None

    try:
        current_stage = "Load dataset"
        dataset = LoCoMoAdapter(path_settings.project_root).load(limit=conversation_limit)
        _guard_expensive_run(dataset.conversations, config, confirm_expensive)
        planned_question_count = _planned_question_count(
            dataset.conversations,
            question_limit_per_conversation,
        )
        planned_question_conversation_ids = _planned_question_conversation_ids(
            dataset.conversations,
            question_limit_per_conversation,
        )
        current_dataset_fingerprint = build_dataset_fingerprint(
            dataset=dataset,
            source_paths=[
                path_settings.project_root
                / "data/locomo/locomo10.json"
            ],
        )
        prediction_path = paths.method_predictions_path
        score_path = paths.locomo_f1_scores_path
        summary_path = paths.summary_path
        status_path = paths.conversation_status_path
        memoryos_storage_root = paths.method_state_dir

        legacy_prediction_path = run_dir / "predictions.jsonl"
        legacy_score_path = run_dir / "scores.jsonl"
        legacy_summary_path = run_dir / "summary.json"
        legacy_status_path = run_dir / "conversation_status.json"

        reconciled_prediction_records: list[dict[str, Any]] = []
        reconciled_score_records: list[dict[str, Any]] = []
        prediction_records_by_question_id: dict[str, dict[str, Any]] = {}
        score_records_by_question_id: dict[str, dict[str, Any]] = {}
        if resume:
            _validate_dataset_resume_fingerprint(
                paths=paths,
                current_fingerprint=current_dataset_fingerprint,
                legacy_prediction_path=legacy_prediction_path,
                legacy_score_path=legacy_score_path,
                legacy_status_path=legacy_status_path,
            )
            _validate_resume_metadata(
                paths=paths,
                run_context=run_context,
                config=config,
                conversation_limit=conversation_limit,
                question_limit_per_conversation=question_limit_per_conversation,
            )
            reconciled_prediction_records = _merge_jsonl_alias_by_question_id(
                primary_path=prediction_path,
                alias_path=legacy_prediction_path,
                artifact_name="method_predictions",
            )
            reconciled_score_records = _merge_jsonl_alias_by_question_id(
                primary_path=score_path,
                alias_path=legacy_score_path,
                artifact_name="locomo_f1_scores",
            )
            prediction_records_by_question_id = _question_records_by_id(
                records=reconciled_prediction_records,
                source_path=prediction_path,
                artifact_name="method_predictions",
            )
            score_records_by_question_id = _question_records_by_id(
                records=reconciled_score_records,
                source_path=score_path,
                artifact_name="locomo_f1_scores",
            )
            _validate_prediction_score_consistency(
                prediction_records_by_question_id=prediction_records_by_question_id,
                score_records_by_question_id=score_records_by_question_id,
            )
            _validate_records_match_planned_questions(
                prediction_records_by_question_id=prediction_records_by_question_id,
                score_records_by_question_id=score_records_by_question_id,
                planned_question_conversation_ids=planned_question_conversation_ids,
            )

        progress = ProgressReporter(paths.progress_path, enabled=show_progress)
        with _progress_scope(progress):
            progress.set_stage("Load dataset", 1, 6)
            logger.log_event(
                "dataset_loaded",
                {
                    **event_context,
                    "dataset_name": dataset.dataset_name,
                    "conversation_count": len(dataset.conversations),
                    "question_count": planned_question_count,
                },
            )
            progress.start_conversations(len(dataset.conversations))
            progress.start_questions(planned_question_count)

            current_stage = "Prepare method state"
            progress.set_stage("Prepare method state", 2, 6)
            if resume:
                _migrate_legacy_conversation_status_path(paths)
                _persist_reconciled_jsonl_alias(
                    primary_path=prediction_path,
                    alias_path=legacy_prediction_path,
                    records=reconciled_prediction_records,
                )
                _persist_reconciled_jsonl_alias(
                    primary_path=score_path,
                    alias_path=legacy_score_path,
                    records=reconciled_score_records,
                )
                _seed_json_alias(primary_path=status_path, alias_path=legacy_status_path)

            conversation_status = _read_json(status_path, default={}) if resume else {}
            completed_question_ids = set(score_records_by_question_id)
            planned_conversation_ids = {
                conversation.conversation_id for conversation in dataset.conversations
            }
            completed_conversation_count = sum(
                1
                for conversation_id, status in conversation_status.items()
                if conversation_id in planned_conversation_ids and status == "added"
            )
            progress.update_conversations(
                completed=completed_conversation_count,
                total=len(dataset.conversations),
                current_conversation_id=None,
            )
            progress.update_questions(
                completed=len(completed_question_ids),
                total=planned_question_count,
                current_conversation_id=None,
                current_question_id=None,
            )
            evaluator = LoCoMoF1Evaluator()
            public_config, config_fingerprint = _public_memoryos_config_summary(config)
            logger.log_event(
                "method_configured",
                {
                    **event_context,
                    "method_name": "MemoryOS",
                    "storage_root": str(memoryos_storage_root),
                    "config": public_config,
                    "config_fingerprint": config_fingerprint,
                },
            )
            system = MemoryOS(storage_root=memoryos_storage_root, config=config)

            _write_run_metadata(
                paths=paths,
                run_context=run_context,
                config=config,
                conversation_limit=conversation_limit,
                question_limit_per_conversation=question_limit_per_conversation,
                confirm_expensive=confirm_expensive,
                dataset_fingerprint=current_dataset_fingerprint,
            )
            _rewrite_public_question_artifacts(
                conversations=dataset.conversations,
                question_limit_per_conversation=question_limit_per_conversation,
                public_question_path=paths.public_questions_path,
                private_label_path=paths.evaluator_private_labels_path,
            )

            logger.info(
                "[bold]MemoryOS-LoCoMo full run[/bold] "
                f"run_id={selected_run_id} conversations={len(dataset.conversations)}"
            )

            for conversation in dataset.conversations:
                current_conversation_id = conversation.conversation_id
                current_question_id = None
                progress.set_stage("Add conversations", 3, 6)
                public_conversation = _make_public_conversation(conversation)
                _validate_public_conversation(public_conversation)
                _ensure_conversation_state(
                    system=system,
                    conversation=public_conversation,
                    conversation_status=conversation_status,
                    status_path=status_path,
                    legacy_status_path=legacy_status_path,
                    memoryos_storage_root=memoryos_storage_root,
                    logger=logger,
                    event_context=event_context,
                )
                progress.update_conversations(
                    completed=sum(
                        1
                        for conversation_id, status in conversation_status.items()
                        if conversation_id in planned_conversation_ids
                        and status == "added"
                    ),
                    total=len(dataset.conversations),
                    current_conversation_id=conversation.conversation_id,
                )

                progress.set_stage("Answer questions", 4, 6)
                for question in _selected_questions(
                    conversation,
                    question_limit_per_conversation,
                ):
                    if question.question_id in completed_question_ids:
                        continue
                    current_question_id = question.question_id
                    public_question = _make_public_question(question)
                    _validate_public_question(public_question)
                    progress.update_questions(
                        completed=len(completed_question_ids),
                        total=planned_question_count,
                        current_conversation_id=public_question.conversation_id,
                        current_question_id=public_question.question_id,
                    )
                    existing_prediction = prediction_records_by_question_id.get(
                        public_question.question_id
                    )
                    if existing_prediction is None:
                        prediction = system.get_answer(public_question)
                    else:
                        prediction = _answer_result_from_prediction_record(
                            existing_prediction,
                            public_question,
                        )

                    metric = evaluator.evaluate(
                        question=public_question,
                        answer=prediction,
                        gold=conversation.gold_answers[public_question.question_id],
                    )
                    prediction_record = {
                        "conversation_id": public_question.conversation_id,
                        "question_id": public_question.question_id,
                        "question_text": public_question.text,
                        "category": public_question.category,
                        "prediction_answer": prediction.answer,
                        "answer_metadata": _safe_answer_metadata(prediction.metadata),
                    }
                    score_record = {
                        "conversation_id": public_question.conversation_id,
                        "question_id": public_question.question_id,
                        "category": metric.details.get("category"),
                        "f1": metric.score,
                        "metric_details": metric.details,
                    }
                    if existing_prediction is None:
                        _append_jsonl_with_alias(
                            prediction_path,
                            legacy_prediction_path,
                            prediction_record,
                        )
                        prediction_records_by_question_id[
                            public_question.question_id
                        ] = prediction_record
                    _append_jsonl_with_alias(score_path, legacy_score_path, score_record)
                    score_records_by_question_id[
                        public_question.question_id
                    ] = score_record
                    completed_question_ids.add(public_question.question_id)
                    progress.update_questions(
                        completed=len(completed_question_ids),
                        total=planned_question_count,
                        current_conversation_id=public_question.conversation_id,
                        current_question_id=public_question.question_id,
                    )
                    logger.log_event(
                        "question_scored",
                        {
                            **event_context,
                            "conversation_id": public_question.conversation_id,
                            "question_id": public_question.question_id,
                            "category": public_question.category,
                            "f1": metric.score,
                        },
                    )
                    _write_summary_with_alias(
                        summary_path=summary_path,
                        legacy_summary_path=legacy_summary_path,
                        summary=_build_summary(
                            run_id=selected_run_id,
                            dataset_name=dataset.dataset_name,
                            conversations=dataset.conversations,
                            question_limit_per_conversation=question_limit_per_conversation,
                            score_path=score_path,
                            prediction_path=prediction_path,
                            summary_path=summary_path,
                            log_dir=paths.logs_dir,
                            conversation_status=conversation_status,
                        ),
                    )

            current_conversation_id = None
            current_question_id = None
            progress.update_conversations(
                completed=sum(
                    1
                    for conversation_id, status in conversation_status.items()
                    if conversation_id in planned_conversation_ids
                    and status == "added"
                ),
                total=len(dataset.conversations),
                current_conversation_id=None,
            )
            progress.update_questions(
                completed=len(completed_question_ids),
                total=planned_question_count,
                current_conversation_id=None,
                current_question_id=None,
            )
            progress.flush()
            progress.set_stage("Evaluate answers", 5, 6)
            summary = _build_summary(
                run_id=selected_run_id,
                dataset_name=dataset.dataset_name,
                conversations=dataset.conversations,
                question_limit_per_conversation=question_limit_per_conversation,
                score_path=score_path,
                prediction_path=prediction_path,
                summary_path=summary_path,
                log_dir=paths.logs_dir,
                conversation_status=conversation_status,
            )
            progress.set_stage("Write summary", 6, 6)
            _write_summary_with_alias(
                summary_path=summary_path,
                legacy_summary_path=legacy_summary_path,
                summary=summary,
            )
        logger.log_event(
            "full_run_finished",
            {
                **summary.to_dict(),
                **event_context,
            },
        )
        return summary
    except Exception as exc:
        if progress is not None:
            try:
                progress.flush()
            except Exception:
                pass
        failure_payload = {
            "run_id": selected_run_id,
            **event_context,
            "exception_type": type(exc).__name__,
            "stage": (
                progress.snapshot["stage"]
                if progress is not None
                else current_stage
            ),
            "current_conversation_id": current_conversation_id,
            "current_question_id": current_question_id,
        }
        try:
            logger.log_event("full_run_failed", failure_payload)
        except Exception:
            pass
        try:
            logger.info(
                "MemoryOS-LoCoMo full run failed "
                f"run_id={selected_run_id} exception_type={type(exc).__name__} "
                f"stage={failure_payload['stage']} "
                f"conversation_id={current_conversation_id} "
                f"question_id={current_question_id}"
            )
        except Exception:
            pass
        raise


def _ensure_conversation_state(
    system: Any,
    conversation: Conversation,
    conversation_status: dict[str, str],
    status_path: Path,
    legacy_status_path: Path,
    memoryos_storage_root: Path,
    logger: RunLogger,
    event_context: dict[str, Any],
) -> None:
    """确保某个 conversation 的 MemoryOS 状态已写入或已 attach。

    输入:
        system: MemoryOS 实例。
        conversation: method 可见公开 conversation。
        conversation_status: conversation checkpoint 状态。
        status_path: checkpoint JSON 路径。
        legacy_status_path: legacy 根目录 checkpoint JSON 路径。
        memoryos_storage_root: MemoryOS 状态根目录。
        logger: 当前 run logger。
        event_context: 当前运行尝试的公开关联字段。

    输出:
        None。
    """

    if conversation_status.get(conversation.conversation_id) == "added":
        system.load_existing_conversation_state(conversation)
        logger.log_event(
            "conversation_attached",
            {
                **event_context,
                "conversation_id": conversation.conversation_id,
            },
        )
        return

    state_dir = memoryos_storage_root / _safe_path_name(conversation.conversation_id)
    if state_dir.exists():
        shutil.rmtree(state_dir)
    add_result = system.add([conversation])
    if conversation.conversation_id not in add_result.conversation_ids:
        raise ConfigurationError(
            f"MemoryOS add did not report conversation_id: {conversation.conversation_id}"
        )
    conversation_status[conversation.conversation_id] = "added"
    _write_status(status_path, legacy_status_path, conversation_status)
    logger.log_event(
        "conversation_added",
        {
            **event_context,
            "conversation_id": conversation.conversation_id,
        },
    )


def _public_memoryos_config_summary(
    config: MemoryOSPaperConfig,
) -> tuple[dict[str, Any], str]:
    """构造事件可记录的 MemoryOS 论文参数白名单及确定性指纹。

    输入:
        config: 当前 MemoryOS 配置。

    输出:
        tuple[dict[str, Any], str]: 显式公开参数摘要和 SHA-256 十六进制指纹。
    """

    public_config = {
        "llm_model": config.llm_model,
        "embedding_model_name": config.embedding_model_name,
        "short_term_capacity": config.short_term_capacity,
        "mid_term_capacity": config.mid_term_capacity,
        "long_term_knowledge_capacity": config.long_term_knowledge_capacity,
        "mid_term_heat_threshold": config.mid_term_heat_threshold,
        "mid_term_similarity_threshold": config.mid_term_similarity_threshold,
        "top_k_sessions": config.top_k_sessions,
        "retrieval_queue_capacity": config.retrieval_queue_capacity,
        "segment_similarity_threshold": config.segment_similarity_threshold,
        "page_similarity_threshold": config.page_similarity_threshold,
        "knowledge_threshold": config.knowledge_threshold,
    }
    canonical_config = json.dumps(
        public_config,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return public_config, hashlib.sha256(canonical_config).hexdigest()


def _write_run_metadata(
    paths: ExperimentPaths,
    run_context: RunContext,
    config: MemoryOSPaperConfig,
    conversation_limit: int | None,
    question_limit_per_conversation: int | None,
    confirm_expensive: bool,
    dataset_fingerprint: dict[str, Any],
) -> None:
    """写入本次运行的 manifest、脱敏配置和数据集指纹。

    输入:
        paths: 标准实验路径集合。
        run_context: 本次运行上下文。
        config: MemoryOS 公开配置。
        conversation_limit: 本次运行的 conversation 限制。
        question_limit_per_conversation: 每个 conversation 的问题限制。
        confirm_expensive: 是否确认高成本真实运行。
        dataset_fingerprint: 已在 resume 校验前计算的当前数据集指纹。

    输出:
        None。
    """

    _write_json(
        paths.manifest_path,
        _build_manifest_payload(
            paths=paths,
            run_context=run_context,
            config=config,
            conversation_limit=conversation_limit,
            question_limit_per_conversation=question_limit_per_conversation,
            confirm_expensive=confirm_expensive,
        ),
    )
    _write_json(paths.redacted_config_path, _build_redacted_config_payload(config))
    _write_json(paths.dataset_fingerprint_path, dataset_fingerprint)


def _validate_dataset_resume_fingerprint(
    paths: ExperimentPaths,
    current_fingerprint: dict[str, Any],
    legacy_prediction_path: Path,
    legacy_score_path: Path,
    legacy_status_path: Path,
) -> None:
    """在读取或改写任何旧状态前校验 dataset fingerprint。

    输入:
        paths: 标准实验路径集合。
        current_fingerprint: 当前已加载 Dataset 的完整指纹。
        legacy_prediction_path: legacy prediction JSONL 路径。
        legacy_score_path: legacy score JSONL 路径。
        legacy_status_path: legacy status JSON 路径。

    输出:
        None；全新空 run 目录允许缺少 fingerprint。

    异常:
        ConfigurationError: 可复用状态缺少兼容 fingerprint，或指纹不一致。
    """

    reusable_paths = (
        paths.public_questions_path,
        paths.evaluator_private_labels_path,
        paths.method_predictions_path,
        paths.locomo_f1_scores_path,
        paths.conversation_status_path,
        paths.legacy_conversation_status_jsonl_path,
        legacy_prediction_path,
        legacy_score_path,
        legacy_status_path,
        paths.manifest_path,
        paths.redacted_config_path,
    )
    has_reusable_state = any(path.exists() for path in reusable_paths) or any(
        paths.method_state_dir.iterdir()
    ) or _path_has_content(paths.run_dir / "memoryos_state")
    fingerprint_path = paths.dataset_fingerprint_path
    if not fingerprint_path.exists():
        if has_reusable_state:
            raise ConfigurationError(
                "resume state exists but dataset fingerprint is missing"
            )
        return

    fingerprint_is_invalid = False
    try:
        saved_fingerprint = _read_json(fingerprint_path, default={})
    except (json.JSONDecodeError, UnicodeError):
        fingerprint_is_invalid = True
        saved_fingerprint = {}
    if fingerprint_is_invalid:
        raise ConfigurationError("dataset fingerprint JSON is invalid") from None
    if not isinstance(saved_fingerprint, dict):
        raise ConfigurationError(
            f"dataset fingerprint must be a JSON object: {fingerprint_path}"
        )
    if "dataset_sha256" not in saved_fingerprint:
        if has_reusable_state:
            raise ConfigurationError(
                "resume state uses an incompatible dataset fingerprint "
                "without dataset_sha256"
            )
        return
    if saved_fingerprint != current_fingerprint:
        raise ConfigurationError("dataset fingerprint mismatch on resume")


def _path_has_content(path: Path) -> bool:
    """判断 legacy 状态路径是否包含可复用内容，空目录不计入。

    输入:
        path: legacy method state 路径。

    输出:
        bool: 文件或非空目录返回 True；缺失路径和空目录返回 False。
    """

    if not path.exists():
        return False
    if not path.is_dir():
        return True
    return any(path.iterdir())


def _build_manifest_payload(
    paths: ExperimentPaths,
    run_context: RunContext,
    config: MemoryOSPaperConfig,
    conversation_limit: int | None,
    question_limit_per_conversation: int | None,
    confirm_expensive: bool,
) -> dict[str, Any]:
    """构造 run manifest payload，供写入和 resume 校验共用。"""

    return {
        "run_id": run_context.run_id,
        "benchmark_name": run_context.benchmark_name,
        "method_name": run_context.method_name,
        "model_name": run_context.model_name,
        "resume": run_context.resume,
        "confirm_expensive": confirm_expensive,
        "conversation_limit": conversation_limit,
        "question_limit_per_conversation": question_limit_per_conversation,
        "memoryos_config": asdict(config),
        "output_dir": str(paths.run_dir),
        "started_at": run_context.started_at,
    }


def _build_redacted_config_payload(config: MemoryOSPaperConfig) -> dict[str, Any]:
    """构造脱敏配置 payload，不包含 secret。"""

    return {
        "memoryos_config": asdict(config),
        "secrets": "redacted",
    }


def _validate_resume_metadata(
    paths: ExperimentPaths,
    run_context: RunContext,
    config: MemoryOSPaperConfig,
    conversation_limit: int | None,
    question_limit_per_conversation: int | None,
) -> None:
    """resume 前校验既有 manifest/config 与当前运行形状一致。

    输入:
        paths: 标准实验路径集合。
        run_context: 当前运行上下文。
        config: 当前 MemoryOS 配置。
        conversation_limit: 当前 conversation 限制。
        question_limit_per_conversation: 当前每 conversation 问题限制。

    输出:
        None。

    异常:
        ConfigurationError: 既有 metadata 与当前配置不一致。
    """

    if not paths.manifest_path.exists():
        if paths.dataset_fingerprint_path.exists():
            raise ConfigurationError(
                "resume metadata is incomplete: manifest.json is missing"
            )
        return

    manifest = _read_resume_metadata_json(
        path=paths.manifest_path,
        payload_name="manifest",
    )
    if not isinstance(manifest, dict):
        raise ConfigurationError(f"manifest must be a JSON object: {paths.manifest_path}")

    expected_fields = {
        "benchmark_name": run_context.benchmark_name,
        "method_name": run_context.method_name,
        "model_name": run_context.model_name,
        "conversation_limit": conversation_limit,
        "question_limit_per_conversation": question_limit_per_conversation,
    }
    for key, expected_value in expected_fields.items():
        _assert_resume_metadata_field(
            payload=manifest,
            payload_name="manifest",
            key=key,
            expected_value=expected_value,
        )

    expected_memoryos_config = asdict(config)
    manifest_has_memoryos_config = "memoryos_config" in manifest
    if manifest_has_memoryos_config:
        _assert_resume_metadata_field(
            payload=manifest,
            payload_name="manifest",
            key="memoryos_config",
            expected_value=expected_memoryos_config,
        )

    if not paths.redacted_config_path.exists():
        if manifest_has_memoryos_config:
            return
        raise ConfigurationError(
            "resume metadata is incomplete: config.redacted.json is missing "
            "and manifest has no memoryos_config"
        )
    redacted_config = _read_resume_metadata_json(
        path=paths.redacted_config_path,
        payload_name="config.redacted",
    )
    if not isinstance(redacted_config, dict):
        raise ConfigurationError(
            f"redacted config must be a JSON object: {paths.redacted_config_path}"
        )
    _assert_resume_metadata_field(
        payload=redacted_config,
        payload_name="config.redacted",
        key="memoryos_config",
        expected_value=expected_memoryos_config,
    )


def _read_resume_metadata_json(path: Path, payload_name: str) -> Any:
    """读取 resume metadata，并把解析错误转换为脱敏领域异常。

    输入:
        path: manifest 或 redacted config 路径。
        payload_name: 对外错误中的公开产物名称。

    输出:
        Any: 已解析的 JSON payload。

    异常:
        ConfigurationError: JSON 或文本编码损坏，且不保留原始内容异常链。
    """

    try:
        return _read_json(path, default={})
    except (json.JSONDecodeError, UnicodeError):
        raise ConfigurationError(f"{payload_name} JSON is invalid") from None


def _assert_resume_metadata_field(
    payload: dict[str, Any],
    payload_name: str,
    key: str,
    expected_value: Any,
) -> None:
    """比较单个 resume metadata 字段，不一致时给出明确错误。"""

    if key not in payload:
        raise ConfigurationError(f"{payload_name} missing resume metadata field: {key}")
    actual_value = payload[key]
    if actual_value != expected_value:
        raise ConfigurationError(
            f"{payload_name} field {key} mismatch on resume: "
            f"existing={actual_value!r}, current={expected_value!r}"
        )


def _rewrite_public_question_artifacts(
    conversations: list[Conversation],
    question_limit_per_conversation: int | None,
    public_question_path: Path,
    private_label_path: Path,
) -> None:
    """重写公开 question 和 evaluator-only label artifacts。

    输入:
        conversations: 本次运行加载的 conversations。
        question_limit_per_conversation: 每个 conversation 的问题限制。
        public_question_path: method 可见公开问题 JSONL 路径。
        private_label_path: evaluator-only 私有标签 JSONL 路径。

    输出:
        None。
    """

    public_records: list[dict[str, Any]] = []
    private_records: list[dict[str, Any]] = []
    for conversation in conversations:
        for question in _selected_questions(conversation, question_limit_per_conversation):
            public_question = _make_public_question(question)
            public_records.append(public_question_record(public_question))
            private_records.append(
                evaluator_private_label_record(
                    conversation.gold_answers[public_question.question_id],
                    public_question.category,
                )
            )
    atomic_write_jsonl(public_question_path, public_records)
    atomic_write_jsonl(private_label_path, private_records)


def _migrate_legacy_conversation_status_path(paths: ExperimentPaths) -> None:
    """把旧版 `conversation_status.jsonl` 迁移到新的 `.json` 路径。

    输入:
        paths: 标准实验路径集合。

    输出:
        None。仅当旧路径存在且新路径不存在时复制。
    """

    old_path = paths.legacy_conversation_status_jsonl_path
    new_path = paths.conversation_status_path
    if old_path.exists() and not new_path.exists():
        _write_json(new_path, _read_json(old_path, default={}))


def _merge_jsonl_alias_by_question_id(
    primary_path: Path,
    alias_path: Path,
    artifact_name: str,
) -> list[dict[str, Any]]:
    """纯内存合并 canonical 与 legacy JSONL，并检测 question_id 冲突。

    输入:
        primary_path: canonical JSONL 路径。
        alias_path: legacy JSONL 路径。
        artifact_name: 产物名称，用于错误信息。

    输出:
        list[dict[str, Any]]: 按首次出现顺序去重后的记录，不改写文件。

    异常:
        ConfigurationError: 同一 question_id 出现内容不同的重复记录。
    """

    if not primary_path.exists() and not alias_path.exists():
        return []

    merged: dict[str, dict[str, Any]] = {}
    ordered_question_ids: list[str] = []
    _merge_question_records(
        records=_read_jsonl(primary_path, recover_torn_tail=True),
        source_path=primary_path,
        artifact_name=artifact_name,
        merged=merged,
        ordered_question_ids=ordered_question_ids,
    )
    _merge_question_records(
        records=_read_jsonl(alias_path, recover_torn_tail=True),
        source_path=alias_path,
        artifact_name=artifact_name,
        merged=merged,
        ordered_question_ids=ordered_question_ids,
    )
    return [merged[question_id] for question_id in ordered_question_ids]


def _persist_reconciled_jsonl_alias(
    primary_path: Path,
    alias_path: Path,
    records: list[dict[str, Any]],
) -> None:
    """把已通过 preflight 的合并记录持久化到 canonical 与 legacy alias。"""

    if not primary_path.exists() and not alias_path.exists():
        return
    _rewrite_jsonl(primary_path, records)
    if primary_path != alias_path:
        _rewrite_jsonl(alias_path, records)


def _merge_question_records(
    records: list[dict[str, Any]],
    source_path: Path,
    artifact_name: str,
    merged: dict[str, dict[str, Any]],
    ordered_question_ids: list[str],
) -> None:
    """把 JSONL 记录合并到 question_id 索引，并检测冲突。"""

    for record in records:
        question_id = _record_question_id(record, source_path, artifact_name)
        existing = merged.get(question_id)
        if existing is not None:
            if existing != record:
                raise ConfigurationError(
                    f"{artifact_name} has conflicting duplicate question_id "
                    f"{question_id}: {source_path}"
                )
            continue
        merged[question_id] = record
        ordered_question_ids.append(question_id)


def _record_question_id(
    record: dict[str, Any],
    source_path: Path,
    artifact_name: str,
) -> str:
    """读取记录中的 question_id，缺失时抛配置错误。"""

    question_id = record.get("question_id")
    if not question_id:
        raise ConfigurationError(
            f"{artifact_name} record missing question_id in {source_path}"
        )
    return str(question_id)


def _validate_prediction_score_consistency(
    prediction_records_by_question_id: dict[str, dict[str, Any]],
    score_records_by_question_id: dict[str, dict[str, Any]],
) -> None:
    """校验每条 score 都有同 question_id 的 prediction。

    输入:
        prediction_records_by_question_id: 已完成 alias 合并的预测索引。
        score_records_by_question_id: 已完成 alias 合并的分数索引。

    输出:
        None；prediction-only 记录允许后续复用并补评分。

    异常:
        ConfigurationError: 存在无法追溯到 prediction 的 score。
    """

    score_only_question_ids = sorted(
        set(score_records_by_question_id) - set(prediction_records_by_question_id)
    )
    if score_only_question_ids:
        raise ConfigurationError(
            "score records require matching prediction records for question_id: "
            + ", ".join(score_only_question_ids)
        )


def _validate_records_match_planned_questions(
    prediction_records_by_question_id: dict[str, dict[str, Any]],
    score_records_by_question_id: dict[str, dict[str, Any]],
    planned_question_conversation_ids: dict[str, str],
) -> None:
    """校验 resume 记录属于当前评测计划且 conversation_id 一致。

    输入:
        prediction_records_by_question_id: 已完成 alias 合并的预测索引。
        score_records_by_question_id: 已完成 alias 合并的分数索引。
        planned_question_conversation_ids: 当前计划中 question_id 到 conversation_id 的映射。

    输出:
        None。

    异常:
        ConfigurationError: 记录不属于当前计划，或 conversation_id 与计划不一致。
    """

    for artifact_name, records_by_question_id in (
        ("method_predictions", prediction_records_by_question_id),
        ("locomo_f1_scores", score_records_by_question_id),
    ):
        for question_id, record in records_by_question_id.items():
            expected_conversation_id = planned_question_conversation_ids.get(question_id)
            if expected_conversation_id is None:
                raise ConfigurationError(
                    f"{artifact_name} record is outside planned question ids: "
                    f"{question_id}"
                )
            actual_conversation_id = str(record.get("conversation_id") or "")
            if actual_conversation_id != expected_conversation_id:
                raise ConfigurationError(
                    f"{artifact_name} record conversation_id mismatch for "
                    f"question_id {question_id}"
                )


def _seed_json_alias(primary_path: Path, alias_path: Path) -> None:
    """resume 时在 canonical 与 legacy JSON 文件之间补齐或合并状态。

    输入:
        primary_path: canonical JSON 路径。
        alias_path: legacy JSON 路径。

    输出:
        None；两侧都是 dict 时合并，冲突状态会失败。
    """

    if primary_path.exists() and not alias_path.exists():
        _write_json(alias_path, _read_json(primary_path, default={}))
        return
    if alias_path.exists() and not primary_path.exists():
        _write_json(primary_path, _read_json(alias_path, default={}))
        return
    if primary_path.exists() and alias_path.exists():
        merged = _merge_json_dict_alias(primary_path, alias_path)
        _write_json(primary_path, merged)
        if primary_path != alias_path:
            _write_json(alias_path, merged)


def _merge_json_dict_alias(primary_path: Path, alias_path: Path) -> dict[str, Any]:
    """合并两个 JSON dict alias，遇到同 key 不同值时报错。"""

    primary_payload = _read_json(primary_path, default={})
    alias_payload = _read_json(alias_path, default={})
    if not isinstance(primary_payload, dict) or not isinstance(alias_payload, dict):
        raise ConfigurationError(
            f"JSON aliases must both be objects: {primary_path}, {alias_path}"
        )
    merged = dict(primary_payload)
    for key, value in alias_payload.items():
        if key in merged and merged[key] != value:
            raise ConfigurationError(
                f"JSON aliases conflict for key {key}: {primary_path}, {alias_path}"
            )
        merged[key] = value
    return merged


def _append_jsonl_with_alias(path: Path, legacy_path: Path, payload: dict[str, Any]) -> None:
    """向 canonical JSONL 追加记录，并同步 legacy alias。

    输入:
        path: canonical 输出路径。
        legacy_path: legacy 根目录 alias。
        payload: 单条 JSONL 记录。

    输出:
        None。
    """

    _append_jsonl(path, payload)
    if path != legacy_path:
        _append_jsonl(legacy_path, payload)


def _rewrite_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """重写 JSONL 文件，用于 resume reconcile 后落盘统一记录。"""

    atomic_write_jsonl(path, records)


def _write_status(path: Path, legacy_path: Path, payload: dict[str, str]) -> None:
    """写 conversation checkpoint，并同步 legacy alias。

    输入:
        path: canonical checkpoint 路径。
        legacy_path: legacy 根目录 checkpoint 路径。
        payload: conversation_id 到状态的映射。

    输出:
        None。
    """

    _write_json(path, payload)
    if path != legacy_path:
        _write_json(legacy_path, payload)


def _write_summary_with_alias(
    summary_path: Path,
    legacy_summary_path: Path,
    summary: MemoryOSLoCoMoFullSummary,
) -> None:
    """写 canonical summary，并同步 legacy 根目录 summary。

    输入:
        summary_path: canonical summary 路径。
        legacy_summary_path: legacy 根目录 summary 路径。
        summary: 当前聚合摘要。

    输出:
        None。
    """

    summary_payload = summary.to_dict()
    _write_json(summary_path, summary_payload)
    if summary_path != legacy_summary_path:
        _write_json(legacy_summary_path, summary_payload)


def _build_summary(
    run_id: str,
    dataset_name: str,
    conversations: list[Conversation],
    question_limit_per_conversation: int | None,
    score_path: Path,
    prediction_path: Path,
    summary_path: Path,
    log_dir: Path,
    conversation_status: dict[str, str],
) -> MemoryOSLoCoMoFullSummary:
    """根据 scores.jsonl 构造聚合 summary。

    输入:
        run_id: 本次运行 id。
        dataset_name: 数据集名。
        conversations: 本次计划评测的 conversations。
        question_limit_per_conversation: 每个 conversation 的问题数限制。
        score_path: 分数 JSONL 路径。
        prediction_path: 预测 JSONL 路径。
        summary_path: summary JSON 路径。
        log_dir: 日志目录。
        conversation_status: conversation add checkpoint。

    输出:
        MemoryOSLoCoMoFullSummary: 聚合摘要。
    """

    score_records = _read_jsonl(score_path)
    scores = [float(record["f1"]) for record in score_records]
    by_category: dict[str, list[float]] = {}
    for record in score_records:
        category = str(record.get("category") or "unknown")
        by_category.setdefault(category, []).append(float(record["f1"]))

    f1_by_category = {
        category: sum(values) / len(values)
        for category, values in sorted(by_category.items())
        if values
    }
    count_by_category = {
        category: len(values)
        for category, values in sorted(by_category.items())
    }
    total_questions = _planned_question_count(conversations, question_limit_per_conversation)
    planned_conversation_ids = {
        conversation.conversation_id for conversation in conversations
    }
    return MemoryOSLoCoMoFullSummary(
        run_id=run_id,
        dataset_name=dataset_name,
        total_conversations=len(conversations),
        completed_conversations=sum(
            1
            for conversation_id, status in conversation_status.items()
            if conversation_id in planned_conversation_ids and status == "added"
        ),
        total_questions=total_questions,
        completed_questions=len(score_records),
        overall_f1=(sum(scores) / len(scores)) if scores else 0.0,
        f1_by_category=f1_by_category,
        count_by_category=count_by_category,
        prediction_path=str(prediction_path),
        score_path=str(score_path),
        summary_path=str(summary_path),
        log_dir=str(log_dir),
        metadata={
            "runner": "memoryos_locomo_full",
            "question_limit_per_conversation": question_limit_per_conversation,
        },
    )


def _guard_expensive_run(
    conversations: list[Conversation],
    config: MemoryOSPaperConfig,
    confirm_expensive: bool,
) -> None:
    """在未确认时阻止会触发 MemoryOS 更新的真实运行。

    输入:
        conversations: 本次要运行的 conversations。
        config: MemoryOS 论文配置。
        confirm_expensive: 用户是否确认高成本运行。

    输出:
        None。
    """

    total_updates = sum(
        memoryos_adapter_module.MemoryOS.estimate_add_workload(
            conversation,
            config,
        ).update_batch_count
        for conversation in conversations
    )
    if total_updates > 0 and not confirm_expensive:
        raise ConfigurationError(
            "MemoryOS LoCoMo full run would trigger "
            f"{total_updates} update batches; pass confirm_expensive=True after确认成本。"
        )


def _validate_public_conversation(conversation: Conversation) -> None:
    """在调用 method.add/load 前校验公开 conversation 不含私有键。"""

    if hasattr(conversation, "to_public_dict"):
        payload = conversation.to_public_dict()
    else:
        payload = {
            "conversation_id": conversation.conversation_id,
            "sessions": conversation.sessions,
            "questions": conversation.questions,
            "metadata": conversation.metadata,
        }
    validate_no_private_keys(payload)


def _validate_public_question(question: Question) -> None:
    """在调用 method.get_answer 前校验公开 question 不含私有键。"""

    if hasattr(question, "to_dict"):
        payload = question.to_dict()
    else:
        payload = {
            "question_id": question.question_id,
            "conversation_id": question.conversation_id,
            "text": question.text,
            "category": question.category,
            "metadata": question.metadata,
        }
    validate_no_private_keys(payload)


def _answer_result_from_prediction_record(
    record: dict[str, Any],
    question: Question,
) -> AnswerResult:
    """把已落盘 prediction 记录还原为 evaluator 可用的 AnswerResult。"""

    if "prediction_answer" not in record:
        raise ConfigurationError(
            f"prediction record missing prediction_answer: {question.question_id}"
        )
    return AnswerResult(
        question_id=str(record.get("question_id") or question.question_id),
        conversation_id=str(record.get("conversation_id") or question.conversation_id),
        answer=str(record["prediction_answer"]),
        metadata=dict(record.get("answer_metadata") or {}),
    )


def _planned_question_count(
    conversations: list[Conversation],
    question_limit_per_conversation: int | None,
) -> int:
    """计算本次计划评测的问题数。"""

    return sum(
        len(_selected_questions(conversation, question_limit_per_conversation))
        for conversation in conversations
    )


def _planned_question_conversation_ids(
    conversations: list[Conversation],
    question_limit_per_conversation: int | None,
) -> dict[str, str]:
    """构造当前评测计划的 question_id 到 conversation_id 映射。

    输入:
        conversations: 当前数据集中的 conversation。
        question_limit_per_conversation: 每个 conversation 的问题数限制。

    输出:
        dict[str, str]: 只包含本次实际计划评测的问题。
    """

    return {
        question.question_id: question.conversation_id
        for conversation in conversations
        for question in _selected_questions(
            conversation,
            question_limit_per_conversation,
        )
    }


def _selected_questions(
    conversation: Conversation,
    question_limit_per_conversation: int | None,
) -> list[Question]:
    """返回某个 conversation 本次要评测的问题。"""

    if question_limit_per_conversation is None:
        return list(conversation.questions)
    if question_limit_per_conversation <= 0:
        raise ConfigurationError("question_limit_per_conversation must be positive")
    return list(conversation.questions[:question_limit_per_conversation])


def _safe_answer_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """移除过大的 prompt 字段后返回可落盘 metadata。

    输入:
        metadata: MemoryOS AnswerResult metadata。

    输出:
        dict[str, Any]: 不包含 system/user prompt 的调试摘要。
    """

    return {
        key: value
        for key, value in metadata.items()
        if key not in {"system_prompt", "user_prompt"}
    }


def _prepare_run_dir(run_dir: Path, resume: bool) -> None:
    """创建或校验运行目录。"""

    if run_dir.exists() and not resume and any(run_dir.iterdir()):
        raise ConfigurationError(f"run_dir already exists; use resume=True or new run_id: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)


def _read_completed_question_ids(score_path: Path) -> set[str]:
    """从 scores.jsonl 中读取已完成 question ids。"""

    return {str(record["question_id"]) for record in _read_jsonl(score_path)}


def _read_question_records_by_id(
    path: Path,
    artifact_name: str,
) -> dict[str, dict[str, Any]]:
    """读取 JSONL 并按 question_id 建索引，同时检测冲突重复。"""

    return _question_records_by_id(
        records=_read_jsonl(path),
        source_path=path,
        artifact_name=artifact_name,
    )


def _question_records_by_id(
    records: list[dict[str, Any]],
    source_path: Path,
    artifact_name: str,
) -> dict[str, dict[str, Any]]:
    """把内存 JSONL 记录按 question_id 建索引，同时检测冲突重复。"""

    records_by_question_id: dict[str, dict[str, Any]] = {}
    ordered_question_ids: list[str] = []
    _merge_question_records(
        records=records,
        source_path=source_path,
        artifact_name=artifact_name,
        merged=records_by_question_id,
        ordered_question_ids=ordered_question_ids,
    )
    return records_by_question_id


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """追加一条 JSONL 记录。"""

    JsonlWriter(path).append(payload)


def _read_jsonl(
    path: Path,
    *,
    recover_torn_tail: bool = False,
) -> list[dict[str, Any]]:
    """读取 JSONL 文件，可由 resume alias 对账显式恢复崩溃尾行。

    输入:
        path: JSONL 文件路径。
        recover_torn_tail: 是否丢弃无行终止符的损坏尾行，默认严格读取。

    输出:
        list[dict[str, Any]]: 已完整解析的对象记录。
    """

    return read_jsonl(path, recover_torn_tail=recover_torn_tail)


def _read_json(path: Path, default: Any) -> Any:
    """读取 JSON 文件；不存在时返回 default。"""

    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """写入 JSON 文件。"""

    atomic_write_json(path, payload)


def _safe_path_name(value: str) -> str:
    """把 conversation_id 转成安全目录名。"""

    return "".join(character if character.isalnum() or character in "-_." else "_" for character in value)


__all__ = [
    "MemoryOSLoCoMoFullSummary",
    "run_memoryos_locomo_full",
]

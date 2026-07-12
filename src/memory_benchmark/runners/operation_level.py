"""HaluMem operation-level prediction runner。

本模块实现 benchmark 级 operation-level 驱动顺序：每个 user 内按 session
逐段 ingest，在 session 边界就地触发 extraction、update probe 和 QA。它只
使用协议 v3 provider，不调用真实 API；answer 由调用方注入的 framework reader
负责。
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter, perf_counter_ns
from typing import Any, Callable

from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core import AnswerPromptResult, AnswerResult, Conversation, Dataset, Question, Session
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    SessionMemoryReport,
    SessionRef,
    UnitRef,
)
from memory_benchmark.core.validators import validate_dataset, validate_no_private_keys
from memory_benchmark.observability import RunContext, method_log_scope
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    EfficiencyObservation,
    EfficiencyStage,
    ModelDescriptor,
)
from memory_benchmark.readers.answer import FrameworkAnswerReader
from memory_benchmark.runners.conversation_qa import _make_public_question
from memory_benchmark.runners.event_stream import (
    GranularityAggregator,
    build_turn_events,
    default_isolation_key,
)
from memory_benchmark.runners.prediction import (
    PredictionRunPolicy,
    PredictionRunSummary,
    _count_answer_context_tokens,
    _elapsed_ms,
    _record_framework_answer_llm_call,
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


def run_operation_level_predictions(
    *,
    dataset: Dataset,
    provider: MemoryProvider,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    answer_reader: FrameworkAnswerReader,
    unified_prompt_builder: Callable[[Question, RetrievalResult], AnswerPromptResult],
    source_paths: tuple[str | Path, ...] = (),
    efficiency_collector: EfficiencyCollector | None = None,
    model_inventory: tuple[ModelDescriptor, ...] = (),
    instrumentation_identity: dict[str, object] | None = None,
) -> PredictionRunSummary:
    """运行 HaluMem operation-level prediction。

    输入:
        dataset: HaluMem adapter 生成的数据集。
        provider: 协议 v3 MemoryProvider。
        run_context: 标准输出目录上下文。
        policy: conversation 级范围与 resume 策略。本 runner 当前只支持单 worker。
        method_manifest: method 公开 manifest。
        benchmark_variant: concrete variant 名。
        run_scope: smoke/full。
        answer_reader: framework-owned answer reader。
        unified_prompt_builder: benchmark 官方 prompt builder。
        source_paths: 可选原始源文件路径，用于数据指纹。

    输出:
        PredictionRunSummary: 标准 prediction 摘要。
    """

    if policy.max_workers != 1:
        raise ConfigurationError(
            "operation-level runner currently requires max_workers=1"
        )
    validate_dataset(dataset)
    paths = ExperimentPaths.create(run_context.run_dir)
    with method_log_scope(paths.logs_dir):
        selected_conversations = _select_conversations(dataset, policy)
        method_manifest = _operation_method_manifest(method_manifest)
        manifest = _build_operation_manifest(
            dataset=dataset,
            run_context=run_context,
            policy=policy,
            method_manifest=method_manifest,
            benchmark_variant=benchmark_variant,
            run_scope=run_scope,
            source_paths=tuple(Path(path) for path in source_paths),
        )
        if instrumentation_identity is not None:
            manifest["instrumentation_identity"] = instrumentation_identity
        _prepare_operation_run(paths=paths, manifest=manifest, resume=policy.resume)
        _write_operation_input_artifacts(paths, selected_conversations)

        efficiency_store: EfficiencyArtifactStore | None = None
        if efficiency_collector is not None and efficiency_collector.enabled:
            if efficiency_collector.run_id != run_context.run_id:
                raise ConfigurationError(
                    "EfficiencyCollector run_id must match RunContext run_id"
                )
            efficiency_store = EfficiencyArtifactStore.for_prediction(paths)
            efficiency_store.write_model_inventory(model_inventory)

        conversation_status = _read_json_object(paths.conversation_status_path)
        prediction_records = {
            record["question_id"]: record
            for record in read_jsonl(
                paths.method_predictions_path,
                recover_torn_tail=policy.resume,
            )
        }
        session_report_records = read_jsonl(
            paths.session_memory_reports_path,
            recover_torn_tail=policy.resume,
        )
        update_probe_records = read_jsonl(
            _update_probe_results_path(paths),
            recover_torn_tail=policy.resume,
        )
        answer_prompt_records = read_jsonl(
            paths.answer_prompts_path,
            recover_torn_tail=policy.resume,
        )

        supports_extraction = type(provider).end_session is not MemoryProvider.end_session
        for conversation in selected_conversations:
            state = conversation_status.get(conversation.conversation_id, {})
            if policy.resume and state.get("status") == "completed":
                continue
            conversation_observations = _run_operation_conversation(
                conversation=conversation,
                provider=provider,
                run_id=run_context.run_id,
                answer_reader=answer_reader,
                unified_prompt_builder=unified_prompt_builder,
                supports_extraction=supports_extraction,
                session_report_records=session_report_records,
                update_probe_records=update_probe_records,
                prediction_records=prediction_records,
                answer_prompt_records=answer_prompt_records,
                efficiency_collector=efficiency_collector,
            )
            if efficiency_store is not None:
                efficiency_store.merge_observations(conversation_observations)
            conversation_status[conversation.conversation_id] = {
                "status": "completed",
                "ingested": True,
            }
            atomic_write_json(paths.conversation_status_path, conversation_status)
            _write_operation_output_artifacts(
                paths=paths,
                session_report_records=session_report_records,
                update_probe_records=update_probe_records,
                prediction_records=prediction_records,
                answer_prompt_records=answer_prompt_records,
                selected_conversations=selected_conversations,
            )

        completed_conversations = sum(
            1
            for conversation in selected_conversations
            if conversation_status.get(conversation.conversation_id, {}).get("status")
            == "completed"
        )
        selected_question_ids = _selected_operation_question_ids(selected_conversations)
        summary = PredictionRunSummary(
            run_id=run_context.run_id,
            dataset_name=dataset.dataset_name,
            total_conversations=len(selected_conversations),
            completed_conversations=completed_conversations,
            total_questions=len(selected_question_ids),
            completed_questions=sum(
                1 for question_id in selected_question_ids if question_id in prediction_records
            ),
            prediction_path=str(paths.method_predictions_path),
            private_label_path=str(paths.evaluator_private_labels_path),
            summary_path=str(paths.summary_path),
            metadata={"runner": "operation_level_prediction"},
        )
        atomic_write_json(paths.summary_path, summary.to_dict())
        return summary


def _run_operation_conversation(
    *,
    conversation: Conversation,
    provider: MemoryProvider,
    run_id: str,
    answer_reader: FrameworkAnswerReader,
    unified_prompt_builder: Callable[[Question, RetrievalResult], AnswerPromptResult],
    supports_extraction: bool,
    session_report_records: list[dict[str, Any]],
    update_probe_records: list[dict[str, Any]],
    prediction_records: dict[str, dict[str, Any]],
    answer_prompt_records: list[dict[str, Any]],
    efficiency_collector: EfficiencyCollector | None = None,
) -> list[EfficiencyObservation]:
    """按 spec S4.2 驱动单个 HaluMem user，并采集效率 observation。

    效率 scope 贴合官方 eval 的 per-session 交错语义（ingest→extraction→
    update-probe→该 session 的 QA），**不改变** ingest/QA 顺序：每个 session 的记忆
    构建包一层 conversation_scope（scope_discriminator=session_id 保证同一 conversation
    多 session 的 observation id 唯一），每个问题包一层 question_scope。返回本
    conversation 采集到的全部 observation，由调用方合并进 EfficiencyArtifactStore。
    """

    observations: list[EfficiencyObservation] = []
    enabled = efficiency_collector is not None and efficiency_collector.enabled
    isolation_key = default_isolation_key(run_id, conversation.conversation_id)
    questions_by_session = _questions_by_session(conversation)
    aggregator = GranularityAggregator(provider.consume_granularity)
    for session in conversation.sessions:
        if enabled:
            with efficiency_collector.conversation_scope(
                conversation.conversation_id,
                scope_discriminator=session.session_id,
            ) as memory_scope:
                started_ns = perf_counter_ns()
                generated = _ingest_and_probe_session(
                    session=session,
                    conversation=conversation,
                    isolation_key=isolation_key,
                    aggregator=aggregator,
                    provider=provider,
                    supports_extraction=supports_extraction,
                    session_report_records=session_report_records,
                    update_probe_records=update_probe_records,
                )
                efficiency_collector.record_memory_build_total_latency(
                    latency_ms=_elapsed_ms(started_ns)
                )
            observations.extend(memory_scope.records)
        else:
            generated = _ingest_and_probe_session(
                session=session,
                conversation=conversation,
                isolation_key=isolation_key,
                aggregator=aggregator,
                provider=provider,
                supports_extraction=supports_extraction,
                session_report_records=session_report_records,
                update_probe_records=update_probe_records,
            )
        if generated:
            continue

        for source_question in questions_by_session.get(session.session_id, []):
            question = _make_public_question(source_question)
            validate_no_private_keys(question.to_dict())
            if enabled:
                with efficiency_collector.question_scope(
                    conversation.conversation_id,
                    question.question_id,
                ) as question_scope:
                    _answer_operation_question(
                        question=question,
                        isolation_key=isolation_key,
                        provider=provider,
                        answer_reader=answer_reader,
                        unified_prompt_builder=unified_prompt_builder,
                        efficiency_collector=efficiency_collector,
                        prediction_records=prediction_records,
                        answer_prompt_records=answer_prompt_records,
                    )
                observations.extend(question_scope.records)
            else:
                _answer_operation_question(
                    question=question,
                    isolation_key=isolation_key,
                    provider=provider,
                    answer_reader=answer_reader,
                    unified_prompt_builder=unified_prompt_builder,
                    efficiency_collector=None,
                    prediction_records=prediction_records,
                    answer_prompt_records=answer_prompt_records,
                )

    if enabled:
        with efficiency_collector.conversation_scope(
            conversation.conversation_id,
            scope_discriminator="__end_conversation__",
        ) as end_scope:
            started_ns = perf_counter_ns()
            provider.end_conversation(UnitRef(isolation_key=isolation_key))
            efficiency_collector.record_memory_build_total_latency(
                latency_ms=_elapsed_ms(started_ns)
            )
        observations.extend(end_scope.records)
    else:
        provider.end_conversation(UnitRef(isolation_key=isolation_key))
    provider.cleanup()
    return observations


def _ingest_and_probe_session(
    *,
    session: Session,
    conversation: Conversation,
    isolation_key: str,
    aggregator: GranularityAggregator,
    provider: MemoryProvider,
    supports_extraction: bool,
    session_report_records: list[dict[str, Any]],
    update_probe_records: list[dict[str, Any]],
) -> bool:
    """ingest 单个 session + extraction + update probe，返回是否为 generated QA session。

    generated session 只 ingest + end_session（不记 session report、不跑 update
    probe、不 QA），与官方 eval 一致。全部 provider 调用发生在调用方开启的
    conversation scope 内，默认归 memory_build 阶段。
    """

    events = [
        event
        for event in build_turn_events(conversation, isolation_key)
        if event.session_id == session.session_id
    ]
    for signal in aggregator.aggregate(events, isolation_key=isolation_key):
        if isinstance(signal, UnitRef):
            continue
        if isinstance(signal, SessionRef):
            continue
        provider.ingest(signal)

    session_ref = SessionRef(
        isolation_key=isolation_key,
        session_id=session.session_id,
    )
    report = provider.end_session(session_ref) if supports_extraction else None
    generated = bool(session.private_metadata.get("is_generated_qa_session"))
    if generated:
        return True
    session_report_records.append(
        _session_report_record(
            session_ref=session_ref,
            report=report,
            supports_extraction=supports_extraction,
        )
    )
    for memory_point in _update_memory_points(session.private_metadata):
        started = perf_counter()
        retrieval = provider.retrieve(
            RetrievalQuery(
                query_text=str(memory_point["memory_content"]),
                isolation_key=isolation_key,
                question_time=None,
                top_k=10,
                purpose="memory_update_probe",
            )
        )
        update_probe_records.append(
            _update_probe_record(
                session_ref=session_ref,
                memory_point=memory_point,
                retrieval=retrieval,
                duration_ms=(perf_counter() - started) * 1000,
            )
        )
    return False


def _answer_operation_question(
    *,
    question: Question,
    isolation_key: str,
    provider: MemoryProvider,
    answer_reader: FrameworkAnswerReader,
    unified_prompt_builder: Callable[[Question, RetrievalResult], AnswerPromptResult],
    efficiency_collector: EfficiencyCollector | None,
    prediction_records: dict[str, dict[str, Any]],
    answer_prompt_records: list[dict[str, Any]],
) -> None:
    """检索 + 回答单个 QA 问题，并在启用时采集 retrieval/answer 效率 observation。

    效率口径与标准 runner 的 `_answer_question_retrieve_first` 完全对齐：retrieve
    包 RETRIEVAL 阶段并记 injected_memory_context_tokens；answer LLM 调用优先取
    api_usage token（`_record_framework_answer_llm_call`），再记 answer 生成延迟。
    """

    enabled = efficiency_collector is not None and efficiency_collector.enabled
    started_ns = perf_counter_ns()
    query = RetrievalQuery(
        query_text=question.text,
        isolation_key=isolation_key,
        question_time=question.question_time,
        top_k=20,
        purpose="qa",
        source_question=question,
    )
    if enabled:
        with efficiency_collector.operation_stage(EfficiencyStage.RETRIEVAL):
            retrieval_result = provider.retrieve(query)
    else:
        retrieval_result = provider.retrieve(query)
    retrieval = unified_prompt_builder(question, retrieval_result)
    if enabled:
        efficiency_collector.record_retrieval_result_if_missing(
            latency_ms=_elapsed_ms(started_ns),
            injected_memory_context_tokens=_count_answer_context_tokens(
                retrieval.metadata,
                answer_reader.client.model_name,
            ),
        )

    answer_started_ns = perf_counter_ns()
    prediction, answer_prompt, answer_response = (
        answer_reader.generate_answer_with_trace(
            question=question,
            retrieval=retrieval,
        )
    )
    if enabled:
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

    _validate_prediction(prediction, question)
    answer_prompt_records.append(
        _answer_prompt_record(
            retrieval=retrieval,
            retrieval_result=retrieval_result,
        )
    )
    prediction_records[question.question_id] = {
        "question_id": question.question_id,
        "conversation_id": question.conversation_id,
        "question_text": question.text,
        "answer": prediction.answer,
        "metadata": {
            **prediction.metadata,
            "operation_level_duration_ms": _elapsed_ms(started_ns),
        },
    }


def _select_conversations(
    dataset: Dataset,
    policy: PredictionRunPolicy,
) -> list[Conversation]:
    """按 policy 选择 conversation。"""

    if policy.conversation_ids is None:
        return list(dataset.conversations)
    by_id = {conversation.conversation_id: conversation for conversation in dataset.conversations}
    missing = [item for item in policy.conversation_ids if item not in by_id]
    if missing:
        raise ConfigurationError(
            f"Unknown conversation_ids in operation-level policy: {', '.join(missing)}"
        )
    return [by_id[item] for item in policy.conversation_ids]


def _questions_by_session(conversation: Conversation) -> dict[str | None, list[Question]]:
    """按 gold metadata 或 question_id 把问题归到 session。"""

    grouped: dict[str | None, list[Question]] = {}
    for question in conversation.questions:
        gold = conversation.gold_answers.get(question.question_id)
        session_id = None
        if gold is not None:
            metadata_session_id = gold.metadata.get("session_id")
            if isinstance(metadata_session_id, str):
                session_id = metadata_session_id
        if session_id is None:
            session_id = _question_session_id(question.question_id)
        grouped.setdefault(session_id, []).append(question)
    return grouped


def _question_session_id(question_id: str) -> str | None:
    """从 HaluMem question id 中解析 session id。"""

    parts = question_id.split(":")
    if len(parts) < 3:
        return None
    return parts[-2]


def _update_memory_points(private_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """筛选官方 update probe 需要的 memory points。"""

    memory_points = private_metadata.get("memory_points")
    if not isinstance(memory_points, list):
        return []
    selected: list[dict[str, Any]] = []
    for memory_point in memory_points:
        if not isinstance(memory_point, dict):
            continue
        if memory_point.get("is_update") == "False":
            continue
        original_memories = memory_point.get("original_memories")
        if not original_memories:
            continue
        if not isinstance(memory_point.get("memory_content"), str):
            continue
        selected.append(memory_point)
    return selected


def _session_report_record(
    *,
    session_ref: SessionRef,
    report: SessionMemoryReport | None,
    supports_extraction: bool,
) -> dict[str, Any]:
    """构造 session memory report artifact 记录。"""

    if report is None:
        return {
            "session_ref": asdict(session_ref),
            "memories": [],
            "metadata": {},
            "status": "n/a" if not supports_extraction else "empty",
        }
    return {
        "session_ref": asdict(report.session_ref),
        "memories": list(report.memories),
        "metadata": dict(report.metadata),
        "status": "ok",
    }


def _update_probe_record(
    *,
    session_ref: SessionRef,
    memory_point: dict[str, Any],
    retrieval: RetrievalResult,
    duration_ms: float,
) -> dict[str, Any]:
    """构造 update probe artifact 记录。"""

    return {
        "session_ref": asdict(session_ref),
        "gold_memory_index": memory_point.get("index"),
        "query_text": memory_point["memory_content"],
        "formatted_memory": retrieval.formatted_memory,
        "memories_from_system": _memories_from_retrieval(retrieval),
        "duration_ms": duration_ms,
    }


def _memories_from_retrieval(retrieval: RetrievalResult) -> list[str]:
    """把 RetrievalResult 转成 HaluMem update scorer 需要的 memory 列表。"""

    if retrieval.items is not None:
        return [item.content for item in retrieval.items]
    return [line for line in retrieval.formatted_memory.splitlines() if line.strip()]


def _answer_prompt_record(
    *,
    retrieval: AnswerPromptResult,
    retrieval_result: RetrievalResult,
) -> dict[str, Any]:
    """构造 QA answer prompt artifact 记录。"""

    record = {
        "question_id": retrieval.question_id,
        "conversation_id": retrieval.conversation_id,
        "answer_prompt": retrieval.answer_prompt,
        "prompt_messages": [message.to_dict() for message in retrieval.prompt_messages],
        "metadata": retrieval.metadata,
        "formatted_memory": retrieval_result.formatted_memory,
        "retrieved_items": [
            asdict(item) for item in retrieval_result.items or ()
        ],
    }
    validate_no_private_keys(record)
    return record


def _validate_prediction(prediction: AnswerResult, question: Question) -> None:
    """校验 framework reader 返回结果与公开 question 对齐。"""

    if prediction.question_id != question.question_id:
        raise ConfigurationError("operation-level prediction question_id mismatch")
    if prediction.conversation_id != question.conversation_id:
        raise ConfigurationError("operation-level prediction conversation_id mismatch")
    if not prediction.answer.strip():
        raise ConfigurationError("operation-level prediction answer is empty")
    validate_no_private_keys(prediction.metadata)


def _write_operation_input_artifacts(
    paths: ExperimentPaths,
    conversations: list[Conversation],
) -> None:
    """写入公开 question 与 evaluator-only 私有标签。"""

    public_questions: list[dict[str, Any]] = []
    private_labels: list[dict[str, Any]] = []
    private_session_labels: list[dict[str, Any]] = []
    for conversation in conversations:
        for session in conversation.sessions:
            if session.private_metadata.get("is_generated_qa_session") is True:
                continue
            private_session_labels.append(
                _evaluator_private_session_label_record(
                    conversation_id=conversation.conversation_id,
                    session=session,
                )
            )
        for question in conversation.questions:
            public_question = _make_public_question(question)
            public_questions.append(public_question_record(public_question))
            gold = conversation.gold_answers.get(question.question_id)
            if gold is not None:
                private_labels.append(
                    evaluator_private_label_record(gold, question.category)
                )
    atomic_write_jsonl(paths.public_questions_path, public_questions)
    atomic_write_jsonl(paths.evaluator_private_labels_path, private_labels)
    atomic_write_jsonl(
        paths.evaluator_private_session_labels_path,
        private_session_labels,
    )


def _evaluator_private_session_label_record(
    *,
    conversation_id: str,
    session: Session,
) -> dict[str, Any]:
    """构造 HaluMem session 级 evaluator-only gold 记录。"""

    memory_points = session.private_metadata.get("memory_points")
    if not isinstance(memory_points, list):
        memory_points = []
    return {
        "conversation_id": conversation_id,
        "session_id": session.session_id,
        "memory_points": list(memory_points),
        "dialogue": [turn.to_dict() for turn in session.turns],
    }


def _write_operation_output_artifacts(
    *,
    paths: ExperimentPaths,
    session_report_records: list[dict[str, Any]],
    update_probe_records: list[dict[str, Any]],
    prediction_records: dict[str, dict[str, Any]],
    answer_prompt_records: list[dict[str, Any]],
    selected_conversations: list[Conversation],
) -> None:
    """稳定写入 operation-level 输出 artifact。"""

    atomic_write_jsonl(paths.session_memory_reports_path, session_report_records)
    atomic_write_jsonl(_update_probe_results_path(paths), update_probe_records)
    question_order = _selected_operation_question_ids(selected_conversations)
    atomic_write_jsonl(
        paths.method_predictions_path,
        [
            prediction_records[question_id]
            for question_id in question_order
            if question_id in prediction_records
        ],
    )
    answer_prompts_by_question = {
        record["question_id"]: record for record in answer_prompt_records
    }
    atomic_write_jsonl(
        paths.answer_prompts_path,
        [
            answer_prompts_by_question[question_id]
            for question_id in question_order
            if question_id in answer_prompts_by_question
        ],
    )


def _selected_operation_question_ids(conversations: list[Conversation]) -> list[str]:
    """返回非 generated session 的 question id 顺序。"""

    question_ids: list[str] = []
    for conversation in conversations:
        generated_session_ids = {
            session.session_id
            for session in conversation.sessions
            if session.private_metadata.get("is_generated_qa_session") is True
        }
        for question in conversation.questions:
            if _question_session_id(question.question_id) in generated_session_ids:
                continue
            question_ids.append(question.question_id)
    return question_ids


def _operation_method_manifest(method_manifest: dict[str, object]) -> dict[str, object]:
    """补齐 operation-level manifest 的协议字段。"""

    manifest = dict(method_manifest)
    manifest.setdefault("protocol_version", "v3")
    manifest.setdefault("prompt_track", "unified")
    return manifest


def _build_operation_manifest(
    *,
    dataset: Dataset,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    source_paths: tuple[Path, ...],
) -> dict[str, Any]:
    """构造 operation-level runner manifest。"""

    dataset_fingerprint = build_dataset_fingerprint(dataset, list(source_paths))
    return {
        "schema_version": 2,
        "runner": "operation_level_prediction",
        "run_id": run_context.run_id,
        "benchmark_name": run_context.benchmark_name,
        "method_name": run_context.method_name,
        "model_name": run_context.model_name,
        "benchmark_variant": benchmark_variant,
        "run_scope": run_scope.value,
        "dataset_sha256": dataset_fingerprint["dataset_sha256"],
        "source_fingerprint_sha256": dataset_fingerprint["source_fingerprint_sha256"],
        "policy": {
            "max_workers": policy.max_workers,
            "conversation_ids": (
                list(policy.conversation_ids)
                if policy.conversation_ids is not None
                else None
            ),
        },
        "method": method_manifest,
    }


def _prepare_operation_run(
    *,
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    resume: bool,
) -> None:
    """写入或校验 operation-level manifest。"""

    if paths.manifest_path.exists():
        existing = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
        if not resume:
            raise ConfigurationError(
                f"Run directory already has a manifest; use resume or a new run_id: {paths.run_dir}"
            )
        if existing != manifest:
            raise ConfigurationError("Operation-level resume manifest mismatch")
        return
    if resume:
        raise ConfigurationError(
            f"Cannot resume because manifest is missing: {paths.manifest_path}"
        )
    atomic_write_json(paths.manifest_path, manifest)
    atomic_write_json(
        paths.redacted_config_path,
        {
            "runner": manifest["runner"],
            "policy": manifest["policy"],
            "method": manifest["method"],
        },
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    """读取 JSON object；缺失时返回空 dict。"""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigurationError(f"Expected JSON object checkpoint: {path}")
    return payload


def _update_probe_results_path(paths: ExperimentPaths) -> Path:
    """返回 HaluMem update probe artifact 路径。"""

    return paths.artifacts_dir / "update_probe_results.jsonl"


__all__ = ["run_operation_level_predictions"]

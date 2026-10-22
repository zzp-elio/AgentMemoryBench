"""标准化预测运行器 (Prediction Runner)。

串联 AgentMemoryBench 的核心数据流闭环：
1. [Ingest (Session)] 遍历 `Conversation.sessions`，携带 `isolation_key` 调用
   `MemoryProvider.ingest(IngestRequest(isolation_key, session))` 并校验 `Result.code == 200`；
2. [Retrieve] 针对每个公开 `Question`，携带 `isolation_key` 调用
   `MemoryProvider.retrieve(RetrieveRequest(...))` 获取 `Result[RetrievePayload]`（含 `formatted_memory`）；
3. [Black-Box Efficiency] 客观统计客户端可测量的三大黑盒效率指标：
   - `ingest_latency_ms`（记忆构建耗时）
   - `retrieve_latency_ms`（记忆检索耗时）
   - `retrieved_context_tokens`（检索返回的 `formatted_memory` Token 长度）
4. [Answer] 由框架统一 `FrameworkAnswerReader` 基于 `formatted_memory` 生成回答，
   并将公开预测与私有标签物理分流落盘。
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from memory_benchmark.core import (
    AnswerPromptResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Dataset,
    IngestRequest,
    MemoryProvider,
    PromptMessage,
    Question,
    RetrievePayload,
    RetrieveRequest,
)
from memory_benchmark.readers.answer import FrameworkAnswerReader
from memory_benchmark.storage import (
    ExperimentPaths,
    RunContext,
    atomic_write_json,
    atomic_write_jsonl,
)
from memory_benchmark.utils.run_logger import RunLogger


def default_isolation_key(run_id: str, conversation_id: str) -> str:
    """生成单段 Conversation 的默认记忆隔离键。"""
    return f"{run_id}_{conversation_id}"


def count_context_tokens(text: str) -> int:
    """统计检索返回的 `formatted_memory` 的 Token 数量（衡量下游 Reader LLM 上下文开销）。"""
    if not text or not text.strip():
        return 0
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())


@dataclass(frozen=True)
class PredictionRunPolicy:
    """控制一次回复生成运行的调度策略。"""

    max_workers: int = 1
    conversation_ids: tuple[str, ...] | None = None
    question_limit_per_conversation: int | None = None
    max_new_conversations: int | None = None
    top_k: int = 10
    skip_ingest: bool = False
    isolation_prefix: str | None = None

    def __post_init__(self) -> None:
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
    """一次回复生成运行的机器可读摘要（含三大黑盒效率指标）。"""

    run_id: str
    dataset_name: str
    total_conversations: int
    completed_conversations: int
    total_questions: int
    completed_questions: int
    prediction_path: str
    private_label_path: str
    summary_path: str
    efficiency_metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    failed_conversations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def failed_count(self) -> int:
        return self.failed_conversations


@dataclass
class _ConversationExecutionResult:
    index: int
    conv_id: str
    prediction_records: list[dict[str, Any]]
    answer_prompt_records: list[dict[str, Any]]
    ingest_latencies_ms: list[float]
    retrieve_latencies_ms: list[float]
    context_tokens: list[int]
    status_entry: dict[str, Any]


def _execute_single_conversation(
    *,
    index: int,
    conversation: Conversation,
    questions: list[Question],
    run_id: str,
    provider: MemoryProvider,
    answer_reader: FrameworkAnswerReader | None,
    unified_prompt_builder: (
        Callable[[Question, RetrievePayload], AnswerPromptResult] | None
    ),
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None,
    top_k: int,
    skip_ingest: bool = False,
    isolation_prefix: str | None = None,
    logger: RunLogger,
) -> _ConversationExecutionResult:
    conv_id = conversation.conversation_id
    effective_run_id = isolation_prefix or run_id
    isolation_key = default_isolation_key(effective_run_id, conv_id)
    try:
        if skip_ingest:
            conv_ingest_latencies = [0.0]
        else:
            conv_ingest_latencies = _ingest_conversation(
                conversation=conversation,
                isolation_key=isolation_key,
                provider=provider,
            )

        pred_records: list[dict[str, Any]] = []
        prompt_records: list[dict[str, Any]] = []
        ret_latencies: list[float] = []
        ctx_tokens_list: list[int] = []

        for question in questions:
            pred_record, prompt_record, ret_latency_ms, ctx_tokens = (
                _retrieve_and_answer_question(
                    question=question,
                    isolation_key=isolation_key,
                    provider=provider,
                    answer_reader=answer_reader,
                    unified_prompt_builder=unified_prompt_builder,
                    prediction_transform=prediction_transform,
                    top_k=top_k,
                )
            )
            pred_records.append(pred_record)
            prompt_records.append(prompt_record)
            ret_latencies.append(ret_latency_ms)
            ctx_tokens_list.append(ctx_tokens)

        status_entry = {
            "status": "completed",
            "session_count": len(conversation.sessions),
            "total_ingest_latency_ms": round(sum(conv_ingest_latencies), 3),
        }
        return _ConversationExecutionResult(
            index=index,
            conv_id=conv_id,
            prediction_records=pred_records,
            answer_prompt_records=prompt_records,
            ingest_latencies_ms=conv_ingest_latencies,
            retrieve_latencies_ms=ret_latencies,
            context_tokens=ctx_tokens_list,
            status_entry=status_entry,
        )
    except Exception as exc:
        logger.log_event(
            "conversation_failed",
            {"conversation_id": conv_id, "error": str(exc)},
        )
        raise


def run_predictions(
    dataset: Dataset,
    provider: MemoryProvider,
    run_context: RunContext,
    policy: PredictionRunPolicy | None = None,
    *,
    answer_reader: FrameworkAnswerReader | None = None,
    unified_prompt_builder: (
        Callable[[Question, RetrievePayload], AnswerPromptResult] | None
    ) = None,
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None = None,
    top_k: int = 10,
    benchmark_variant: str = "default",
) -> PredictionRunSummary:
    """执行 `Ingest(Session) -> Retrieve -> Answer` 全流程并落盘标准 Artifacts。"""

    active_policy = policy or PredictionRunPolicy()
    selected_conversations = _select_conversations(dataset, active_policy)
    selected_questions = _select_questions(selected_conversations, active_policy)

    paths = ExperimentPaths.create(run_context.run_dir)
    manifest = {
        "run_id": run_context.run_id,
        "benchmark_name": dataset.dataset_name,
        "benchmark_variant": benchmark_variant,
        "method_name": run_context.method_name,
    }
    atomic_write_json(paths.manifest_path, manifest)
    _write_question_artifacts(
        paths=paths,
        conversations=selected_conversations,
        selected_questions=selected_questions,
    )

    prediction_records: list[dict[str, Any]] = []
    answer_prompt_records: list[dict[str, Any]] = []
    conversation_status: dict[str, dict[str, Any]] = {}
    completed_conversations = 0
    failed_conversations = 0

    session_ingest_latencies_ms: list[float] = []
    question_retrieve_latencies_ms: list[float] = []
    question_context_tokens: list[int] = []

    logger = RunLogger(paths.logs_dir)
    indexed_conversations = list(enumerate(selected_conversations))
    conv_results: list[_ConversationExecutionResult] = []
    first_error: Exception | None = None

    effective_top_k = active_policy.top_k if active_policy and active_policy.top_k != 10 else top_k
    skip_ingest = active_policy.skip_ingest if active_policy else False
    isolation_prefix = active_policy.isolation_prefix if active_policy else None

    if active_policy.max_workers > 1 and len(indexed_conversations) > 1:
        with ThreadPoolExecutor(max_workers=active_policy.max_workers) as executor:
            future_to_idx = {
                executor.submit(
                    _execute_single_conversation,
                    index=idx,
                    conversation=conv,
                    questions=selected_questions[conv.conversation_id],
                    run_id=run_context.run_id,
                    provider=provider,
                    answer_reader=answer_reader,
                    unified_prompt_builder=unified_prompt_builder,
                    prediction_transform=prediction_transform,
                    top_k=effective_top_k,
                    skip_ingest=skip_ingest,
                    isolation_prefix=isolation_prefix,
                    logger=logger,
                ): idx
                for idx, conv in indexed_conversations
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                conv = indexed_conversations[idx][1]
                conv_id = conv.conversation_id
                try:
                    conv_results.append(future.result())
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
                    failed_conversations += 1
                    conversation_status[conv_id] = {
                        "status": "failed",
                        "error": str(exc),
                    }
                    logger.log_event(
                        "conversation_failed",
                        {"conversation_id": conv_id, "error": str(exc)},
                    )
    else:
        for idx, conv in indexed_conversations:
            conv_id = conv.conversation_id
            try:
                res = _execute_single_conversation(
                    index=idx,
                    conversation=conv,
                    questions=selected_questions[conv.conversation_id],
                    run_id=run_context.run_id,
                    provider=provider,
                    answer_reader=answer_reader,
                    unified_prompt_builder=unified_prompt_builder,
                    prediction_transform=prediction_transform,
                    top_k=effective_top_k,
                    skip_ingest=skip_ingest,
                    isolation_prefix=isolation_prefix,
                    logger=logger,
                )
                conv_results.append(res)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                failed_conversations += 1
                conversation_status[conv_id] = {
                    "status": "failed",
                    "error": str(exc),
                }
                logger.log_event(
                    "conversation_failed",
                    {"conversation_id": conv_id, "error": str(exc)},
                )

    conv_results.sort(key=lambda r: r.index)

    for r in conv_results:
        prediction_records.extend(r.prediction_records)
        answer_prompt_records.extend(r.answer_prompt_records)
        session_ingest_latencies_ms.extend(r.ingest_latencies_ms)
        question_retrieve_latencies_ms.extend(r.retrieve_latencies_ms)
        question_context_tokens.extend(r.context_tokens)
        conversation_status[r.conv_id] = r.status_entry
        completed_conversations += 1

    if completed_conversations == 0 and failed_conversations > 0:
        if first_error is not None:
            raise first_error
        raise RuntimeError(
            f"All {failed_conversations} conversations failed in run '{run_context.run_id}'. Check logs/events.jsonl for details."
        )

    atomic_write_jsonl(paths.method_predictions_path, prediction_records)
    atomic_write_jsonl(paths.answer_prompts_path, answer_prompt_records)
    atomic_write_json(paths.conversation_status_path, conversation_status)

    efficiency_metrics = {
        "total_ingest_latency_ms": round(sum(session_ingest_latencies_ms), 3),
        "mean_session_ingest_latency_ms": round(
            sum(session_ingest_latencies_ms) / len(session_ingest_latencies_ms), 3
        )
        if session_ingest_latencies_ms
        else 0.0,
        "mean_retrieve_latency_ms": round(
            sum(question_retrieve_latencies_ms) / len(question_retrieve_latencies_ms), 3
        )
        if question_retrieve_latencies_ms
        else 0.0,
        "mean_retrieved_context_tokens": round(
            sum(question_context_tokens) / len(question_context_tokens), 2
        )
        if question_context_tokens
        else 0.0,
    }

    total_questions = sum(len(qs) for qs in selected_questions.values())
    summary = PredictionRunSummary(
        run_id=run_context.run_id,
        dataset_name=dataset.dataset_name,
        total_conversations=len(selected_conversations),
        completed_conversations=completed_conversations,
        total_questions=total_questions,
        completed_questions=len(prediction_records),
        prediction_path=str(paths.method_predictions_path),
        private_label_path=str(paths.evaluator_private_labels_path),
        summary_path=str(paths.summary_path),
        efficiency_metrics=efficiency_metrics,
        failed_conversations=failed_conversations,
    )
    atomic_write_json(paths.summary_path, summary.to_dict())
    return summary


def _ingest_conversation(
    *,
    conversation: Conversation,
    isolation_key: str,
    provider: MemoryProvider,
) -> list[float]:
    latencies_ms: list[float] = []
    num_sessions = len(conversation.sessions)
    for s_idx, session in enumerate(conversation.sessions):
        is_last_session = (s_idx == num_sessions - 1)
        request = IngestRequest(
            isolation_key=isolation_key,
            session=session,
            metadata={"is_last_session": is_last_session},
        )
        start = time.perf_counter()
        result = provider.ingest(request)
        wall_ms = (time.perf_counter() - start) * 1000.0
        if not result.is_success:
            raise RuntimeError(
                f"Ingest failed with code={result.code} for session '{session.session_id}': {result.message}"
            )
        latencies_ms.append(result.latency_ms if result.latency_ms > 0 else wall_ms)
    return latencies_ms


def _retrieve_and_answer_question(
    *,
    question: Question,
    isolation_key: str,
    provider: MemoryProvider,
    answer_reader: FrameworkAnswerReader | None,
    unified_prompt_builder: (
        Callable[[Question, RetrievePayload], AnswerPromptResult] | None
    ),
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None,
    top_k: int,
) -> tuple[dict[str, Any], dict[str, Any], float, int]:
    """对单个问题执行记忆检索 (`retrieve`)、统计检索耗时与 Context Tokens，并生成回答 (`answer`)。"""

    req = RetrieveRequest(
        isolation_key=isolation_key,
        query=question.text,
        question_time=question.question_time,
        top_k=top_k,
        question_id=question.question_id,
        metadata=dict(question.metadata),
    )

    start = time.perf_counter()
    res = provider.retrieve(req)
    wall_ms = (time.perf_counter() - start) * 1000.0
    if not res.is_success or res.data is None:
        raise RuntimeError(
            f"Retrieve failed with code={res.code} for question '{question.question_id}': {res.message}"
        )

    retrieve_latency_ms = res.latency_ms if res.latency_ms > 0 else wall_ms
    payload = res.data
    formatted_memory = payload.formatted_memory
    context_tokens = count_context_tokens(formatted_memory)

    if unified_prompt_builder is not None:
        prompt_result = unified_prompt_builder(question, payload)
    elif answer_reader is not None:
        prompt_result = answer_reader.build_prompt(question, payload)
    else:
        prompt_result = _default_prompt_from_payload(question, payload)

    if answer_reader is not None:
        try:
            answer = answer_reader.generate_answer(
                question=question,
                retrieval=prompt_result,
            )
        except Exception as exc:
            err_msg = str(exc)
            if "content_filter" in err_msg.lower() or "content management policy" in err_msg.lower():
                answer = AnswerResult(
                    conversation_id=question.conversation_id,
                    question_id=question.question_id,
                    answer="",
                    metadata={"error": err_msg, "filtered": True},
                )
            else:
                raise
    else:
        answer = AnswerResult(
            conversation_id=question.conversation_id,
            question_id=question.question_id,
            answer=formatted_memory,
        )

    if prediction_transform is not None:
        answer = prediction_transform(answer)

    merged_metadata = dict(answer.metadata)
    merged_metadata.update(
        {
            "retrieve_latency_ms": round(retrieve_latency_ms, 3),
            "retrieved_context_tokens": context_tokens,
        }
    )

    prediction_record = {
        "question_id": question.question_id,
        "conversation_id": question.conversation_id,
        "answer": answer.answer,
        "metadata": merged_metadata,
    }
    prompt_record = {
        "question_id": question.question_id,
        "conversation_id": question.conversation_id,
        "formatted_memory": formatted_memory,
        "retrieved_context_tokens": context_tokens,
        "retrieve_latency_ms": round(retrieve_latency_ms, 3),
        "answer_prompt": prompt_result.answer_prompt,
    }
    return prediction_record, prompt_record, retrieve_latency_ms, context_tokens


def _default_prompt_from_payload(
    question: Question, payload: RetrievePayload
) -> AnswerPromptResult:
    memory_context = payload.formatted_memory
    prompt_text = (
        f"Memory Context:\n{memory_context}\n\n"
        f"Question: {question.text}\nAnswer:"
    )
    return AnswerPromptResult(
        conversation_id=question.conversation_id,
        question_id=question.question_id,
        answer_prompt=prompt_text,
        prompt_messages=[PromptMessage(role="user", content=prompt_text)],
    )


def _select_conversations(
    dataset: Dataset, policy: PredictionRunPolicy
) -> list[Conversation]:
    if policy.conversation_ids is None:
        conversations = list(dataset.conversations)
    else:
        by_id = {c.conversation_id: c for c in dataset.conversations}
        missing = [cid for cid in policy.conversation_ids if cid not in by_id]
        if missing:
            raise ConfigurationError(
                f"Unknown conversation_ids in prediction policy: {', '.join(missing)}"
            )
        conversations = [by_id[cid] for cid in policy.conversation_ids]

    if policy.max_new_conversations is not None:
        conversations = conversations[: policy.max_new_conversations]
    return conversations


def _select_questions(
    conversations: list[Conversation], policy: PredictionRunPolicy
) -> dict[str, list[Question]]:
    limit = policy.question_limit_per_conversation
    return {
        conv.conversation_id: list(
            conv.questions[:limit] if limit is not None else conv.questions
        )
        for conv in conversations
    }


def _write_question_artifacts(
    *,
    paths: ExperimentPaths,
    conversations: list[Conversation],
    selected_questions: dict[str, list[Question]],
) -> None:
    """将公开问题与私有标准答案分流写入两个独立的 JSONL Artifact（严防数据泄漏）。"""

    public_rows: list[dict[str, Any]] = []
    private_rows: list[dict[str, Any]] = []
    for conv in conversations:
        conv_id = conv.conversation_id
        for question in selected_questions[conv_id]:
            qid = question.question_id
            if qid not in conv.gold_answers:
                raise ConfigurationError(
                    f"Missing gold answer for question '{qid}' in conversation '{conv_id}'"
                )
            gold = conv.gold_answers[qid]
            public_rows.append(
                {
                    "question_id": qid,
                    "conversation_id": conv_id,
                    "question_text": question.text,
                    "question_time": question.question_time,
                    "category": question.category,
                    "capability": (
                        question.capability.value
                        if hasattr(question.capability, "value")
                        else question.capability
                    ),
                    "options": question.options,
                    "metadata": dict(question.metadata),
                }
            )
            private_rows.append(
                {
                    "question_id": qid,
                    "conversation_id": conv_id,
                    "gold_answer": gold.answer,
                    "metadata": dict(gold.metadata),
                }
            )
    atomic_write_jsonl(paths.public_questions_path, public_rows)
    atomic_write_jsonl(paths.evaluator_private_labels_path, private_rows)


__all__ = [
    "PredictionRunPolicy",
    "PredictionRunSummary",
    "count_context_tokens",
    "default_isolation_key",
    "run_predictions",
]

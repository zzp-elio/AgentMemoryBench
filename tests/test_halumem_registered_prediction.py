"""HaluMem registered fake 全链路 smoke 测试。

本文件只使用 fake v3 provider、fake answer reader 和 fake judge client，覆盖
operation-level prediction artifacts 到三段 HaluMem evaluator 的离线链路。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.audit.benchmark_probe import BenchmarkProbeProvider
from memory_benchmark.benchmark_adapters.contracts import BenchmarkLoadRequest, RunScope
from memory_benchmark.benchmark_adapters.halumem import (
    HALUMEM_RESUME_POLICY,
    HALUMEM_SMOKE_POLICY,
    build_halumem_unified_answer_prompt,
)
from memory_benchmark.benchmark_adapters.registry import get_benchmark_registration
from memory_benchmark.core import Conversation, Dataset, GoldAnswerInfo, Question, Session, Turn
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.core.provider_protocol import (
    IngestResult,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    RetrievedItem,
    SessionBatch,
    SessionMemoryReport,
    SessionRef,
    UnitRef,
)
from memory_benchmark.evaluators.halumem_extraction import HalumemExtractionEvaluator
from memory_benchmark.evaluators.halumem_memory_type import HalumemMemoryTypeEvaluator
from memory_benchmark.evaluators.halumem_qa import HalumemQAEvaluator
from memory_benchmark.evaluators.halumem_update import HalumemUpdateEvaluator
from memory_benchmark.observability import RunContext
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    ModelDescriptor,
)
from memory_benchmark.readers.answer import FakeAnswerLLMClient, FrameworkAnswerReader
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.runners.operation_level import run_operation_level_predictions
from memory_benchmark.runners.prediction import PredictionRunPolicy
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.integration
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class HalumemProbeProvider(BenchmarkProbeProvider):
    """以 session 粒度记录真实 HaluMem operation-level 调用。"""

    def __init__(self) -> None:
        """启用 session 增量报告，使 extraction evaluator 可评测。"""

        super().__init__(consume_granularity="session", session_memory_report=True)


class EmptyRetrievalHalumemProbe(HalumemProbeProvider):
    """保留 ingest/report，但让 update 与 QA 检索稳定返回空。"""

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """记录公开 query，并返回空检索结果。"""

        self.call_log.append("retrieve")
        self.retrieve_queries.append(query)
        return RetrievalResult(formatted_memory="No retrieved memory.", items=())


class FakeHalumemProvider(MemoryProvider):
    """提供 session 增量报告的 HaluMem fake provider。"""

    consume_granularity = "session"

    def __init__(self) -> None:
        """初始化调用记录和 session 状态。"""

        self.calls: list[tuple[str, str]] = []
        self.ingested_sessions: list[str] = []

    def ingest(self, unit: SessionBatch) -> IngestResult:
        """记录 session 写入。"""

        self.calls.append(("ingest", unit.session_id or ""))
        self.ingested_sessions.append(unit.session_id or "")
        return IngestResult(unit_ref=unit.ref)

    def end_session(self, ref: SessionRef) -> SessionMemoryReport:
        """返回本 session 的 fake 增量 memory。"""

        self.calls.append(("end_session", ref.session_id or ""))
        return SessionMemoryReport(
            session_ref=ref,
            memories=[f"Riley memory from {ref.session_id}"],
            metadata={"source": "fake"},
        )

    def end_conversation(self, ref: UnitRef) -> None:
        """记录 conversation 收尾。"""

        self.calls.append(("end_conversation", ref.isolation_key))

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回可供 update/QA artifacts 使用的 fake retrieval。"""

        self.calls.append((query.purpose, query.query_text))
        memory = " | ".join(self.ingested_sessions)
        return RetrievalResult(
            formatted_memory=f"{query.purpose}:{query.query_text}:{memory}",
            items=(
                RetrievedItem(
                    item_id=f"{query.purpose}-1",
                    content=f"retrieved:{query.query_text}",
                    score=1.0,
                    timestamp=None,
                ),
            ),
        )

    def cleanup(self) -> None:
        """记录 cleanup。"""

        self.calls.append(("cleanup", ""))


class NoSessionReportHalumemProvider(FakeHalumemProvider):
    """不提供 session extraction report 的 fake provider。"""

    end_session = MemoryProvider.end_session


class FailingSecondUserProvider(FakeHalumemProvider):
    """在第二个 user 写入时失败，用于制造 pending resume 状态。"""

    def ingest(self, unit: SessionBatch) -> IngestResult:
        """第二个 session 触发故障，其余沿用 fake 写入。"""

        if unit.session_id == "s-halu-user-2":
            raise RuntimeError("planned second user failure")
        return super().ingest(unit)


class FakeHalumemJudgeClient:
    """三段 HaluMem evaluator 共用的离线 fake judge。"""

    def judge_json(self, prompt: str) -> dict[str, str]:
        """按 prompt 类型返回官方字段形状。"""

        if "Memory Integrity" in prompt:
            return {"score": "2", "reasoning": "covered"}
        if "Dialogue Memory Accuracy Evaluator" in prompt:
            return {
                "accuracy_score": "2",
                "is_included_in_golden_memories": "true",
                "reason": "covered",
            }
        if "evaluate the update accuracy" in prompt:
            return {"evaluation_result": "Correct", "reason": "updated"}
        if "question answering" in prompt:
            return {"evaluation_result": "Correct", "reasoning": "answered"}
        raise AssertionError(f"unexpected HaluMem judge prompt: {prompt[:120]}")


def test_halumem_registered_medium_smoke_runs_three_operations_and_four_evaluators(
    tmp_path: Path,
) -> None:
    """真实 registry/Medium smoke 应贯通三操作、四 evaluator 与隐私边界。"""

    prepared, registration = _prepared_medium_smoke()
    conversation = prepared.dataset.conversations[0]
    assert len(conversation.sessions) == 4
    assert sum(len(session.turns) for session in conversation.sessions) == 8
    assert len(conversation.questions) == 1

    provider = HalumemProbeProvider()
    context = _real_context(tmp_path, run_id="halumem-h5-medium-smoke")
    collector = EfficiencyCollector(run_id=context.run_id, enabled=True)
    summary = run_operation_level_predictions(
        dataset=prepared.dataset,
        provider=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "benchmark-probe", "protocol_version": "v3"},
        benchmark_variant=prepared.variant,
        run_scope=prepared.run_scope,
        source_paths=tuple(PROJECT_ROOT / path for path in prepared.source_relative_paths),
        answer_reader=_reader(),
        unified_prompt_builder=registration.unified_prompt_builder,
        efficiency_collector=collector,
        model_inventory=(_fake_answer_model(),),
    )
    assert summary.completed_conversations == 1
    assert summary.completed_questions == 1
    assert len(provider.ingested_turns) == 8
    assert len(provider.ended_sessions) == 4
    assert sum(query.purpose == "memory_update_probe" for query in provider.retrieve_queries) == 7
    assert sum(query.purpose == "qa" for query in provider.retrieve_queries) == 1

    paths = ExperimentPaths.create(context.run_dir)
    judge = FakeHalumemJudgeClient()
    first_summaries = [
        run_artifact_evaluation(context.run_dir, evaluator, "halumem")
        for evaluator in (
            HalumemExtractionEvaluator(client=judge),
            HalumemUpdateEvaluator(client=judge),
            HalumemQAEvaluator(client=judge),
            HalumemMemoryTypeEvaluator(),
        )
    ]
    assert [item.metric_name for item in first_summaries] == [
        "halumem_extraction",
        "halumem_update",
        "halumem_qa",
        "halumem_memory_type",
    ]
    assert all(Path(item.score_path).is_file() for item in first_summaries)
    qa_summary = json.loads(
        paths.metric_summary_path("halumem_qa").read_text(encoding="utf-8")
    )
    gold = conversation.gold_answers[conversation.questions[0].question_id]
    assert {item["category"] for item in qa_summary["category_breakdown"]} == {
        gold.metadata["question_type"]
    }

    observations = EfficiencyArtifactStore.for_prediction(paths).read_observations()
    conversation_observations = [
        item
        for item in observations
        if item.to_dict()["observation_type"] == "conversation_efficiency"
    ]
    question_observations = [
        item
        for item in observations
        if item.to_dict()["observation_type"] == "question_efficiency"
    ]
    assert len(conversation_observations) == 5
    assert len({item.observation_id for item in conversation_observations}) == 5
    assert len(question_observations) == 1
    assert question_observations[0].retrieval_latency_ms is not None
    assert question_observations[0].answer_generation_latency_ms is not None

    for record in read_jsonl(paths.method_predictions_path):
        validate_no_private_keys(record.get("metadata", {}))
        _assert_absent_gold_fields(record)
    for record in read_jsonl(paths.answer_prompts_path):
        validate_no_private_keys(record)
        _assert_absent_gold_fields(record)
    public_conversation = conversation.to_public_dict()
    validate_no_private_keys(public_conversation)
    _assert_absent_gold_fields(public_conversation)

    rerun = run_artifact_evaluation(
        context.run_dir, HalumemMemoryTypeEvaluator(), "halumem"
    )
    assert rerun.mean_score == first_summaries[-1].mean_score
    assert HALUMEM_RESUME_POLICY.evaluation_artifact_only is True


def test_halumem_empty_update_retrieval_routes_to_integrity_and_keeps_none_ratio(
    tmp_path: Path,
) -> None:
    """空 update 检索仍发生调用，并使 update 0 分母显式为 None。"""

    prepared, registration = _prepared_medium_smoke()
    provider = EmptyRetrievalHalumemProbe()
    context = _real_context(tmp_path, run_id="halumem-h5-empty-update")
    run_operation_level_predictions(
        dataset=prepared.dataset,
        provider=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "benchmark-probe", "protocol_version": "v3"},
        benchmark_variant=prepared.variant,
        run_scope=prepared.run_scope,
        answer_reader=_reader(),
        unified_prompt_builder=registration.unified_prompt_builder,
    )
    assert sum(query.purpose == "memory_update_probe" for query in provider.retrieve_queries) == 7
    paths = ExperimentPaths.create(context.run_dir)
    assert len(read_jsonl(paths.artifacts_dir / "update_probe_results.jsonl")) == 7

    judge = FakeHalumemJudgeClient()
    extraction = run_artifact_evaluation(
        context.run_dir, HalumemExtractionEvaluator(client=judge), "halumem"
    )
    update = run_artifact_evaluation(
        context.run_dir, HalumemUpdateEvaluator(client=judge), "halumem"
    )
    assert extraction.total_questions > 0
    assert update.total_questions == 0
    update_payload = json.loads(Path(update.summary_path).read_text(encoding="utf-8"))
    update_ratio = update_payload["overall_score"]["memory_update"]
    assert update_ratio["update_memory_num"] == 0
    assert update_ratio["correct_update_memory_ratio(all)"] is None
    assert update_payload["skipped_empty_retrieval_count"] == 7


def test_halumem_generated_qa_session_only_ingests_without_probes_or_answers(
    tmp_path: Path,
) -> None:
    """generated QA session 只 ingest/end_session，不产生三段评测 artifact。"""

    dataset = _dataset("generated-user")
    session = dataset.conversations[0].sessions[0]
    session.private_metadata["is_generated_qa_session"] = True
    provider = FakeHalumemProvider()
    context = _context(tmp_path)
    summary = run_operation_level_predictions(
        dataset=dataset,
        provider=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="long",
        run_scope=RunScope.FULL,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
    )
    paths = ExperimentPaths.create(context.run_dir)
    assert ("ingest", session.session_id) in provider.calls
    assert ("end_session", session.session_id) in provider.calls
    assert not any(call[0] in {"memory_update_probe", "qa"} for call in provider.calls)
    assert read_jsonl(paths.session_memory_reports_path) == []
    assert read_jsonl(paths.artifacts_dir / "update_probe_results.jsonl") == []
    assert read_jsonl(paths.method_predictions_path) == []
    assert summary.total_questions == 0


def test_halumem_fake_registered_chain_runs_three_evaluators(tmp_path: Path) -> None:
    """fake provider 应端到端产出三段 evaluator 结果。"""

    provider = FakeHalumemProvider()
    run_context = _context(tmp_path)
    run_operation_level_predictions(
        dataset=_dataset("halu-user-1"),
        provider=provider,
        run_context=run_context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="medium",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
    )
    paths = ExperimentPaths.create(run_context.run_dir)
    client = FakeHalumemJudgeClient()

    summaries = [
        run_artifact_evaluation(
            run_dir=run_context.run_dir,
            evaluator=evaluator,
            expected_benchmark="halumem",
        )
        for evaluator in (
            HalumemExtractionEvaluator(client=client),
            HalumemUpdateEvaluator(client=client),
            HalumemQAEvaluator(client=client),
        )
    ]

    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    assert manifest["method"]["protocol_version"] == "v3"
    assert manifest["method"]["prompt_track"] == "unified"
    assert read_jsonl(paths.session_memory_reports_path)
    assert read_jsonl(paths.artifacts_dir / "update_probe_results.jsonl")
    assert read_jsonl(paths.method_predictions_path)
    assert [summary.metric_name for summary in summaries] == [
        "halumem_extraction",
        "halumem_update",
        "halumem_qa",
    ]
    assert read_jsonl(paths.metric_scores_path("halumem_extraction"))
    assert read_jsonl(paths.metric_scores_path("halumem_update"))
    assert read_jsonl(paths.metric_scores_path("halumem_qa"))


def test_halumem_fake_chain_marks_extraction_na_without_session_report(
    tmp_path: Path,
) -> None:
    """未覆写 end_session 时 extraction 为 N/A，但 update 与 QA 仍可评测。"""

    run_context = _context(tmp_path)
    run_operation_level_predictions(
        dataset=_dataset("halu-user-1"),
        provider=NoSessionReportHalumemProvider(),
        run_context=run_context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="medium",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
    )
    paths = ExperimentPaths.create(run_context.run_dir)
    client = FakeHalumemJudgeClient()

    extraction = run_artifact_evaluation(
        run_dir=run_context.run_dir,
        evaluator=HalumemExtractionEvaluator(client=client),
        expected_benchmark="halumem",
    )
    update = run_artifact_evaluation(
        run_dir=run_context.run_dir,
        evaluator=HalumemUpdateEvaluator(client=client),
        expected_benchmark="halumem",
    )
    qa = run_artifact_evaluation(
        run_dir=run_context.run_dir,
        evaluator=HalumemQAEvaluator(client=client),
        expected_benchmark="halumem",
    )
    extraction_summary = json.loads(
        Path(extraction.summary_path).read_text(encoding="utf-8")
    )

    assert [record["status"] for record in read_jsonl(paths.session_memory_reports_path)] == [
        "n/a"
    ]
    assert extraction_summary["status"] == "n/a"
    assert update.total_questions == 1
    assert qa.total_questions == 1


def test_halumem_operation_resume_skips_completed_and_runs_pending_user(
    tmp_path: Path,
) -> None:
    """resume 应跳过已完成 user，并继续处理 pending user。"""

    first_context = _context(tmp_path)
    with pytest.raises(RuntimeError, match="planned second user failure"):
        run_operation_level_predictions(
            dataset=_dataset("halu-user-1", "halu-user-2"),
            provider=FailingSecondUserProvider(),
            run_context=first_context,
            policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
            method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
            benchmark_variant="medium",
            run_scope=RunScope.FULL,
            answer_reader=_reader(),
            unified_prompt_builder=build_halumem_unified_answer_prompt,
        )

    second_provider = FakeHalumemProvider()
    summary = run_operation_level_predictions(
        dataset=_dataset("halu-user-1", "halu-user-2"),
        provider=second_provider,
        run_context=_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(max_workers=1, resume=True, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="medium",
        run_scope=RunScope.FULL,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
    )

    assert summary.completed_conversations == 2
    assert ("ingest", "s-halu-user-1") not in second_provider.calls
    assert ("ingest", "s-halu-user-2") in second_provider.calls
    assert HALUMEM_RESUME_POLICY.smoke_enabled is False
    assert HALUMEM_RESUME_POLICY.ingest_checkpoint == "conversation"
    assert HALUMEM_RESUME_POLICY.answer_checkpoint == "question"
    assert HALUMEM_RESUME_POLICY.reuse_saved_retrieval is True


def test_halumem_operation_level_records_efficiency_observations(
    tmp_path: Path,
) -> None:
    """operation-level runner 启用效率观测：不再崩（#6 的根因），并产出 per-session
    记忆构建 observation（id 唯一）+ per-question 检索/回答 observation + answer LLM 调用。"""

    provider = FakeHalumemProvider()
    run_context = _context(tmp_path)
    collector = EfficiencyCollector(run_id=run_context.run_id, enabled=True)
    inventory = (
        ModelDescriptor(
            model_id="fake-answer-llm",
            model_name="fake-answer-llm",
            model_role="answer_llm",
            execution_mode="local",
        ),
    )

    run_operation_level_predictions(
        dataset=_dataset("halu-user-1"),
        provider=provider,
        run_context=run_context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="medium",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
        efficiency_collector=collector,
        model_inventory=inventory,
    )

    paths = ExperimentPaths.create(run_context.run_dir)
    observations = EfficiencyArtifactStore.for_prediction(paths).read_observations()
    by_type: dict[str, list] = {}
    for observation in observations:
        by_type.setdefault(
            observation.to_dict()["observation_type"], []
        ).append(observation)

    # per-session 记忆构建 + end_conversation 收尾 → ≥2 条，且 observation_id 唯一
    conversation_obs = by_type.get("conversation_efficiency", [])
    assert len(conversation_obs) >= 2
    assert len({obs.observation_id for obs in conversation_obs}) == len(
        conversation_obs
    )
    assert all(obs.conversation_id == "halu-user-1" for obs in conversation_obs)

    # per-question 检索 + 回答
    question_obs = by_type.get("question_efficiency", [])
    assert len(question_obs) == 1
    assert question_obs[0].retrieval_latency_ms is not None
    assert question_obs[0].answer_generation_latency_ms >= 0.0

    # answer LLM 调用被记录（stage=answer）
    assert any(
        obs.stage.value == "answer" for obs in by_type.get("llm_call", [])
    )


def _dataset(*conversation_ids: str) -> Dataset:
    """构造最小 HaluMem dataset。"""

    return Dataset(
        dataset_name="halumem",
        conversations=[_conversation(conversation_id) for conversation_id in conversation_ids],
        metadata={"variant": "medium", "run_scope": "smoke"},
    )


def _conversation(conversation_id: str) -> Conversation:
    """构造单 session、含 extraction/update/QA 的 HaluMem conversation。"""

    session_id = f"s-{conversation_id}"
    question_id = f"{conversation_id}:{session_id}:q1"
    memory_content = f"Riley memory from {session_id}"
    update_memory = f"Riley update from {session_id}"
    return Conversation(
        conversation_id=conversation_id,
        sessions=[
            Session(
                session_id=session_id,
                session_time="2025-09-04T18:42:18+00:00",
                turns=[
                    Turn(
                        f"{session_id}:t1",
                        "user",
                        f"I said {memory_content}.",
                        normalized_role="user",
                    )
                ],
                private_metadata={
                    "is_generated_qa_session": False,
                    "memory_points": [
                        {
                            "index": 1,
                            "memory_content": memory_content,
                            "memory_type": "Persona Memory",
                            "is_update": "False",
                            "memory_source": "target",
                            "importance": 1,
                            "original_memories": [],
                        },
                        {
                            "index": 2,
                            "memory_content": update_memory,
                            "memory_type": "Persona Memory",
                            "is_update": "True",
                            "memory_source": "target",
                            "importance": 1,
                            "original_memories": ["Riley old update"],
                        },
                    ],
                },
            )
        ],
        questions=[
            Question(
                question_id=question_id,
                conversation_id=conversation_id,
                text="What does Riley remember?",
            )
        ],
        gold_answers={
            question_id: GoldAnswerInfo(
                question_id=question_id,
                answer="Riley remembers it.",
                evidence=[memory_content],
                metadata={"session_id": session_id, "question_type": "Fact"},
            )
        },
    )


def _context(tmp_path: Path, *, resume: bool = False) -> RunContext:
    """创建 HaluMem registered smoke run context。"""

    return RunContext.create(
        run_id="halumem-registered-test",
        benchmark_name="halumem",
        method_name="fake-v3",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=resume,
    )


def _reader() -> FrameworkAnswerReader:
    """创建 fake framework reader。"""

    return FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="fake answer"))


def _prepared_medium_smoke():
    """通过真实 registry 准备 H2 固定形状 Medium smoke。"""

    registration = get_benchmark_registration("halumem")
    assert registration.prepare_run is not None
    prepared = registration.prepare_run(
        PROJECT_ROOT,
        BenchmarkLoadRequest(
            variant="medium",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=HALUMEM_SMOKE_POLICY.default_history_limit,
            smoke_conversation_limit=HALUMEM_SMOKE_POLICY.default_isolation_limit,
        ),
    )
    return prepared, registration


def _real_context(tmp_path: Path, *, run_id: str) -> RunContext:
    """创建真实 registry e2e 使用的隔离 run context。"""

    return RunContext.create(
        run_id=run_id,
        benchmark_name="halumem",
        method_name="benchmark-probe",
        model_name="fake-reader",
        output_root=tmp_path,
    )


def _fake_answer_model() -> ModelDescriptor:
    """返回离线 answer reader 的效率 inventory。"""

    return ModelDescriptor(
        model_id="fake-answer-llm",
        model_name="fake-answer-llm",
        model_role="answer_llm",
        execution_mode="local",
    )


def _assert_absent_gold_fields(payload: object) -> None:
    """窄化扫描 HaluMem gold；prediction 的公开 answer 字段属于合法输出。"""

    forbidden = {"memory_points", "evidence", "gold_answer"}
    if isinstance(payload, dict):
        for key, value in payload.items():
            assert str(key).lower() not in forbidden
            _assert_absent_gold_fields(value)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _assert_absent_gold_fields(item)

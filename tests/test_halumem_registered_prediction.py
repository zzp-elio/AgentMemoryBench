"""HaluMem registered fake 全链路 smoke 测试。

本文件只使用 fake v3 provider、fake answer reader 和 fake judge client，覆盖
operation-level prediction artifacts 到三段 HaluMem evaluator 的离线链路。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.benchmark_adapters.halumem import (
    build_halumem_unified_answer_prompt,
)
from memory_benchmark.core import Conversation, Dataset, GoldAnswerInfo, Question, Session, Turn
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
from memory_benchmark.evaluators.halumem_qa import HalumemQAEvaluator
from memory_benchmark.evaluators.halumem_update import HalumemUpdateEvaluator
from memory_benchmark.observability import RunContext
from memory_benchmark.readers.answer import FakeAnswerLLMClient, FrameworkAnswerReader
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.runners.operation_level import run_operation_level_predictions
from memory_benchmark.runners.prediction import PredictionRunPolicy
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.integration


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
            run_scope=RunScope.SMOKE,
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
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
    )

    assert summary.completed_conversations == 2
    assert ("ingest", "s-halu-user-1") not in second_provider.calls
    assert ("ingest", "s-halu-user-2") in second_provider.calls


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

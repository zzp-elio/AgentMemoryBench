"""测试 HaluMem operation-level prediction runner。

本文件只使用 fake v3 provider 和 fake answer reader，验证 runner 的驱动顺序、
三类 artifact、generated session 跳过语义和 conversation 级 resume。
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
from memory_benchmark.observability import RunContext
from memory_benchmark.readers.answer import FakeAnswerLLMClient, FrameworkAnswerReader
from memory_benchmark.runners.operation_level import run_operation_level_predictions
from memory_benchmark.runners.prediction import PredictionRunPolicy
from memory_benchmark.storage import read_jsonl


pytestmark = pytest.mark.integration


class OperationFakeProvider(MemoryProvider):
    """记录 operation-level 调用序列的 fake provider。"""

    consume_granularity = "session"

    def __init__(self) -> None:
        """初始化调用记录与累积 session 状态。"""

        self.calls: list[tuple[str, str, str | None, int | None]] = []
        self.ingested_sessions: list[str] = []
        self.write_count = 0
        self.update_write_counts: list[tuple[int, int]] = []

    def ingest(self, unit: SessionBatch) -> IngestResult:
        """记录 session batch 写入，并把 session 加入累积状态。"""

        assert isinstance(unit, SessionBatch)
        self.calls.append(("ingest", unit.session_id or "", None, len(unit.events)))
        self.ingested_sessions.append(unit.session_id or "")
        self.write_count += 1
        return IngestResult(unit_ref=unit.ref)

    def end_session(self, ref: SessionRef) -> SessionMemoryReport:
        """返回本 session 增量抽取记忆。"""

        self.calls.append(("end_session", ref.session_id or "", None, None))
        return SessionMemoryReport(
            session_ref=ref,
            memories=[f"extracted:{ref.session_id}"],
        )

    def end_conversation(self, ref: UnitRef) -> None:
        """记录 conversation 结束。"""

        self.calls.append(("end_conversation", ref.isolation_key, None, None))

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """记录检索，并返回当前累积 session 状态。"""

        before = self.write_count
        self.calls.append(
            (
                "retrieve",
                query.purpose,
                query.query_text,
                query.top_k,
            )
        )
        if query.purpose == "memory_update_probe":
            self.update_write_counts.append((before, self.write_count))
        memory = " | ".join(self.ingested_sessions)
        return RetrievalResult(
            formatted_memory=f"{query.purpose}:{query.query_text}:{memory}",
            items=(
                RetrievedItem(
                    item_id=f"{query.purpose}-1",
                    content=f"memory:{query.query_text}:{memory}",
                    score=None,
                    timestamp=None,
                ),
            ),
        )

    def cleanup(self) -> None:
        """记录 cleanup。"""

        self.calls.append(("cleanup", "", None, None))


class NoSessionReportProvider(OperationFakeProvider):
    """不覆写 end_session 的 fake provider，用于 extraction N/A 路径。"""

    end_session = MemoryProvider.end_session


def _operation_dataset(*, include_generated_question: bool = True) -> Dataset:
    """构造覆盖 update、QA、generated session 和累积状态的 HaluMem 数据集。"""

    conversation_id = "halu-user-1"
    sessions = [
        Session(
            session_id="s1",
            session_time="2025-09-04T18:42:18+00:00",
            turns=[Turn("s1:t1", "user", "I live in Boston.", normalized_role="user")],
            private_metadata={
                "is_generated_qa_session": False,
                "memory_points": [
                    {
                        "index": 1,
                        "memory_content": "Riley lives in Boston",
                        "memory_type": "Persona Memory",
                        "is_update": "False",
                        "original_memories": [],
                    },
                    {
                        "index": 2,
                        "memory_content": "Riley drinks tea",
                        "memory_type": "Persona Memory",
                        "is_update": "True",
                        "original_memories": ["Riley drinks coffee"],
                    },
                ],
            },
        ),
        Session(
            session_id="s-generated",
            turns=[
                Turn(
                    "s-generated:t1",
                    "assistant",
                    "Generated context only.",
                    normalized_role="assistant",
                )
            ],
            private_metadata={
                "is_generated_qa_session": True,
                "memory_points": [
                    {
                        "index": 9,
                        "memory_content": "Generated memory must not be evaluated",
                        "memory_type": "Event Memory",
                        "is_update": "True",
                        "original_memories": ["old generated memory"],
                    }
                ],
            },
        ),
        Session(
            session_id="s-no-question",
            turns=[
                Turn(
                    "s-no-question:t1",
                    "user",
                    "I keep a green notebook.",
                    normalized_role="user",
                )
            ],
            private_metadata={
                "is_generated_qa_session": False,
                "memory_points": [
                    {
                        "index": 10,
                        "memory_content": "Riley keeps a green notebook",
                        "memory_type": "Event Memory",
                        "is_update": "False",
                        "original_memories": [],
                    }
                ],
            },
        ),
        Session(
            session_id="s2",
            turns=[Turn("s2:t1", "user", "I moved to Seattle.", normalized_role="user")],
            private_metadata={
                "is_generated_qa_session": False,
                "memory_points": [
                    {
                        "index": 3,
                        "memory_content": "Riley moved to Seattle",
                        "memory_type": "Persona Memory",
                        "is_update": "True",
                        "original_memories": ["Riley lives in Boston"],
                    }
                ],
            },
        ),
    ]
    questions = [
        Question(
            question_id=f"{conversation_id}:s1:q1",
            conversation_id=conversation_id,
            text="Where does Riley live?",
        ),
        Question(
            question_id=f"{conversation_id}:s2:q1",
            conversation_id=conversation_id,
            text="Where did Riley move?",
        ),
    ]
    if include_generated_question:
        questions.insert(
            1,
            Question(
                question_id=f"{conversation_id}:s-generated:q1",
                conversation_id=conversation_id,
                text="Should generated session be answered?",
            ),
        )
    gold_answers = {
        questions[0].question_id: GoldAnswerInfo(
            question_id=questions[0].question_id,
            answer="Boston",
            evidence=["Riley lives in Boston"],
            metadata={"session_id": "s1"},
        ),
        f"{conversation_id}:s2:q1": GoldAnswerInfo(
            question_id=f"{conversation_id}:s2:q1",
            answer="Seattle",
            evidence=["Riley moved to Seattle"],
            metadata={"session_id": "s2"},
        ),
    }
    if include_generated_question:
        gold_answers[f"{conversation_id}:s-generated:q1"] = GoldAnswerInfo(
            question_id=f"{conversation_id}:s-generated:q1",
            answer="Should not run",
            metadata={"session_id": "s-generated"},
        )
    return Dataset(
        dataset_name="halumem",
        conversations=[
            Conversation(
                conversation_id=conversation_id,
                sessions=sessions,
                questions=questions,
                gold_answers=gold_answers,
            )
        ],
        metadata={"variant": "medium", "run_scope": "smoke"},
    )


def _context(tmp_path: Path, *, resume: bool = False) -> RunContext:
    """创建 operation-level 测试 run context。"""

    return RunContext.create(
        run_id="halumem-operation-test",
        benchmark_name="halumem",
        method_name="fake-v3",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=resume,
    )


def _reader() -> FrameworkAnswerReader:
    """创建离线 fake framework reader。"""

    return FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="fake answer"))


def test_operation_level_runner_drives_three_stages_and_writes_artifacts(
    tmp_path: Path,
) -> None:
    """runner 应按 session 边界执行 extraction/update/QA 并写三类 artifact。"""

    provider = OperationFakeProvider()
    summary = run_operation_level_predictions(
        dataset=_operation_dataset(),
        provider=provider,
        run_context=_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="medium",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
    )

    artifacts = _context(tmp_path).artifacts_dir
    session_reports = read_jsonl(artifacts / "session_memory_reports.jsonl")
    session_labels = read_jsonl(
        artifacts / "evaluator_private_session_labels.jsonl"
    )
    update_results = read_jsonl(artifacts / "update_probe_results.jsonl")
    predictions = read_jsonl(artifacts / "method_predictions.jsonl")
    manifest = json.loads((_context(tmp_path).run_dir / "manifest.json").read_text())

    assert summary.completed_conversations == 1
    assert summary.completed_questions == 2
    assert [record["session_ref"]["session_id"] for record in session_reports] == [
        "s1",
        "s-no-question",
        "s2",
    ]
    assert [record["memories"] for record in session_reports] == [
        ["extracted:s1"],
        ["extracted:s-no-question"],
        ["extracted:s2"],
    ]
    assert [
        (record["conversation_id"], record["session_id"])
        for record in session_labels
    ] == [
        ("halu-user-1", "s1"),
        ("halu-user-1", "s-no-question"),
        ("halu-user-1", "s2"),
    ]
    assert session_labels[1]["memory_points"] == [
        {
            "index": 10,
            "memory_content": "Riley keeps a green notebook",
            "memory_type": "Event Memory",
            "is_update": "False",
            "original_memories": [],
        }
    ]
    assert session_labels[1]["dialogue"] == [
        {
            "turn_id": "s-no-question:t1",
            "speaker": "user",
            "content": "I keep a green notebook.",
            "normalized_role": "user",
            "turn_time": None,
            "images": [],
            "metadata": {},
        }
    ]
    assert "s-generated" not in {record["session_id"] for record in session_labels}
    for conversation in _operation_dataset().conversations:
        validate_no_private_keys(conversation.to_public_dict())
    assert [record["gold_memory_index"] for record in update_results] == [2, 3]
    assert [record["query_text"] for record in update_results] == [
        "Riley drinks tea",
        "Riley moved to Seattle",
    ]
    assert [record["question_id"] for record in predictions] == [
        "halu-user-1:s1:q1",
        "halu-user-1:s2:q1",
    ]
    assert "s-generated" not in {
        record["session_ref"]["session_id"] for record in session_reports
    }
    assert "Generated memory must not be evaluated" not in {
        record["query_text"] for record in update_results
    }
    assert "halu-user-1:s-generated:q1" not in {
        record["question_id"] for record in predictions
    }
    assert provider.update_write_counts == [(1, 1), (4, 4)]
    assert provider.calls == [
        ("ingest", "s1", None, 1),
        ("end_session", "s1", None, None),
        ("retrieve", "memory_update_probe", "Riley drinks tea", 10),
        ("retrieve", "qa", "Where does Riley live?", 20),
        ("ingest", "s-generated", None, 1),
        ("end_session", "s-generated", None, None),
        ("ingest", "s-no-question", None, 1),
        ("end_session", "s-no-question", None, None),
        ("ingest", "s2", None, 1),
        ("end_session", "s2", None, None),
        ("retrieve", "memory_update_probe", "Riley moved to Seattle", 10),
        ("retrieve", "qa", "Where did Riley move?", 20),
        ("end_conversation", "halumem-operation-test_halu-user-1", None, None),
        ("cleanup", "", None, None),
    ]
    assert "s1 | s-generated | s-no-question | s2" in update_results[1]["formatted_memory"]
    assert manifest["runner"] == "operation_level_prediction"
    assert manifest["method"]["protocol_version"] == "v3"
    assert manifest["method"]["prompt_track"] == "unified"


def test_operation_level_runner_writes_extraction_na_when_no_session_report(
    tmp_path: Path,
) -> None:
    """未覆写 end_session 的 provider 应写 extraction N/A，占位但不阻断 update/QA。"""

    provider = NoSessionReportProvider()
    run_operation_level_predictions(
        dataset=_operation_dataset(include_generated_question=False),
        provider=provider,
        run_context=_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="medium",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
    )

    session_reports = read_jsonl(
        _context(tmp_path).artifacts_dir / "session_memory_reports.jsonl"
    )
    predictions = read_jsonl(_context(tmp_path).artifacts_dir / "method_predictions.jsonl")

    assert [record["status"] for record in session_reports] == ["n/a", "n/a", "n/a"]
    assert [record["memories"] for record in session_reports] == [[], [], []]
    assert len(predictions) == 2


def test_operation_level_resume_skips_completed_user(tmp_path: Path) -> None:
    """conversation 级 resume 应跳过已完成 user，不重复调用 provider。"""

    first_provider = OperationFakeProvider()
    run_operation_level_predictions(
        dataset=_operation_dataset(include_generated_question=False),
        provider=first_provider,
        run_context=_context(tmp_path),
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="medium",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
    )

    second_provider = OperationFakeProvider()
    summary = run_operation_level_predictions(
        dataset=_operation_dataset(include_generated_question=False),
        provider=second_provider,
        run_context=_context(tmp_path, resume=True),
        policy=PredictionRunPolicy(max_workers=1, resume=True, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="medium",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
    )

    assert second_provider.calls == []
    assert summary.completed_conversations == 1
    assert summary.completed_questions == 2

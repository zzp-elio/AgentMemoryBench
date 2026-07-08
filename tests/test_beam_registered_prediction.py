"""BEAM registered fake 全链路 smoke 测试。

使用 fake v3 provider、fake answer reader 和 fake judge client，覆盖
conversation-QA prediction artifacts 到 beam_rubric_judge evaluator 的离线链路。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters.beam import build_beam_unified_answer_prompt
from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core import Conversation, Dataset, GoldAnswerInfo, Question, Session, Turn
from memory_benchmark.core.provider_protocol import (
    IngestResult,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    RetrievedItem,
    TurnEvent,
    UnitRef,
)
from memory_benchmark.evaluators.beam_rubric_judge import BeamRubricJudgeEvaluator
from memory_benchmark.observability import RunContext
from memory_benchmark.readers.answer import FakeAnswerLLMClient, FrameworkAnswerReader
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.runners.prediction import PredictionRunPolicy, run_predictions
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# fake provider
# ---------------------------------------------------------------------------


class FakeBeamProvider(MemoryProvider):
    """BEAM fake v3 provider，记录 ingest/retrieve 调用并返回固定 memory。"""

    consume_granularity = "turn"

    def __init__(self) -> None:
        """初始化调用记录和内部状态。"""

        self.calls: list[tuple[str, str]] = []
        self.ingested_turns: list[str] = []

    def ingest(self, unit: TurnEvent) -> IngestResult:
        """记录 turn 写入。"""

        self.calls.append(("ingest", unit.isolation_key))
        self.ingested_turns.append(unit.isolation_key)
        return IngestResult(unit_ref=UnitRef(unit.isolation_key))

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回固定 fake retrieval。"""

        self.calls.append(("retrieve", query.purpose))
        return RetrievalResult(
            formatted_memory="[2026-01-01] fake beam memory for question",
            items=(
                RetrievedItem(
                    item_id="beam-fake-1",
                    content="fake beam memory",
                    score=1.0,
                    timestamp=None,
                ),
            ),
            metadata={"method": "fake-beam"},
        )

    def end_conversation(self, ref: UnitRef) -> None:
        """记录 conversation 收尾。"""

        self.calls.append(("end_conversation", ref.isolation_key))

    def cleanup(self) -> None:
        """记录 cleanup。"""

        self.calls.append(("cleanup", ""))


# ---------------------------------------------------------------------------
# fake judge client
# ---------------------------------------------------------------------------


class FakeBeamJudgeClient:
    """BEAM rubric judge 离线 fake client，返回固定 0.5 分。"""

    def judge_json(self, prompt: str) -> dict[str, object]:
        """返回固定 judge 结果。"""

        return {"score": 0.5, "reason": "fake partial compliance"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _beam_dataset(conversation_id: str = "beam-test-1") -> Dataset:
    """构造最小 BEAM conversation-QA dataset（含 rubric gold）。"""

    question = Question(
        question_id=f"{conversation_id}:abstention:q1",
        conversation_id=conversation_id,
        text="What did I do yesterday?",
        category="abstention",
    )
    return Dataset(
        dataset_name="beam",
        conversations=[
            Conversation(
                conversation_id=conversation_id,
                sessions=[
                    Session(
                        session_id="s1",
                        session_time="March 15, 2024",
                        turns=[
                            Turn(
                                turn_id="s1:t1",
                                speaker="user",
                                content="I wrote code yesterday.",
                                normalized_role="user",
                                turn_time="March 15, 2024",
                            ),
                            Turn(
                                turn_id="s1:t2",
                                speaker="assistant",
                                content="That's great!",
                                normalized_role="assistant",
                                turn_time="March 15, 2024",
                            ),
                        ],
                    )
                ],
                questions=[question],
                gold_answers={
                    question.question_id: GoldAnswerInfo(
                        question_id=question.question_id,
                        answer="You wrote code.",
                        evidence=[],
                        metadata={
                            "ability": "abstention",
                            "rubric": [
                                "Answer mentions coding or programming",
                                "Answer is about yesterday's activity",
                            ],
                            "difficulty": "easy",
                        },
                    )
                },
            )
        ],
        metadata={"variant": "100k", "run_scope": "smoke"},
    )


def _run_context(tmp_path: Path, *, resume: bool = False) -> RunContext:
    """创建 BEAM registered smoke run context。"""

    return RunContext.create(
        run_id="beam-registered-test",
        benchmark_name="beam",
        method_name="fake-v3",
        model_name="fake-reader",
        output_root=tmp_path,
        resume=resume,
    )


def _reader() -> FrameworkAnswerReader:
    """创建 fake framework reader。"""

    return FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="fake beam answer"))


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_beam_fake_registered_chain_produces_artifacts_and_rubric_judge(
    tmp_path: Path,
) -> None:
    """BEAM × fake provider 应端到端产出 prediction artifacts + rubric judge 结果。"""

    provider = FakeBeamProvider()
    run_context = _run_context(tmp_path)
    run_predictions(
        dataset=_beam_dataset(),
        system=provider,
        run_context=run_context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="100k",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_beam_unified_answer_prompt,
        protocol_version="v3",
    )

    paths = ExperimentPaths.create(run_context.run_dir)

    # manifest 断言
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    assert manifest["method"]["protocol_version"] == "v3"
    assert manifest["method"]["prompt_track"] == "unified"
    assert manifest["benchmark_name"] == "beam"
    assert manifest["benchmark_variant"] == "100k"
    assert manifest["run_scope"] == "smoke"

    # prediction artifacts 非空
    predictions = read_jsonl(paths.method_predictions_path)
    assert len(predictions) == 1
    assert predictions[0]["answer"] == "fake beam answer"
    assert predictions[0]["question_id"] == "beam-test-1:abstention:q1"

    # answer prompts 含 unified track
    prompts = read_jsonl(paths.artifacts_dir / "answer_prompts.prediction.jsonl")
    assert len(prompts) == 1
    assert prompts[0]["metadata"]["prompt_track"] == "unified"
    assert prompts[0]["metadata"]["answer_prompt_profile"] == "beam_rag_v1"

    # evaluator private labels 含 rubric
    private_labels = read_jsonl(paths.evaluator_private_labels_path)
    assert len(private_labels) == 1
    assert private_labels[0]["metadata"]["rubric"] == [
        "Answer mentions coding or programming",
        "Answer is about yesterday's activity",
    ]
    assert private_labels[0]["metadata"]["ability"] == "abstention"

    # rubric judge evaluator
    client = FakeBeamJudgeClient()
    evaluator = BeamRubricJudgeEvaluator(client=client)
    summary = run_artifact_evaluation(
        run_dir=run_context.run_dir,
        evaluator=evaluator,
        expected_benchmark="beam",
    )

    assert summary.metric_name == "beam_rubric_judge"
    assert summary.total_questions == 1
    # fake judge returns 0.5 per rubric item, 2 items → per-question = 0.5
    # overall = mean of 10 abilities (only 1 has data) → 0.5/10 = 0.05
    assert summary.mean_score == pytest.approx(0.05)

    # metric scores artifact 非空
    scores = read_jsonl(paths.metric_scores_path("beam_rubric_judge"))
    assert len(scores) == 1
    assert scores[0]["metric_name"] == "beam_rubric_judge"

    # 验证 provider 调用序列
    assert len(provider.ingested_turns) == 2  # user + assistant
    assert any(call[0] == "retrieve" for call in provider.calls)


def test_beam_fake_chain_public_questions_exclude_private_data(
    tmp_path: Path,
) -> None:
    """公开 questions artifact 不得泄漏 rubric 等私有数据。"""

    run_context = _run_context(tmp_path)
    run_predictions(
        dataset=_beam_dataset(),
        system=FakeBeamProvider(),
        run_context=run_context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="100k",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_beam_unified_answer_prompt,
        protocol_version="v3",
    )

    paths = ExperimentPaths.create(run_context.run_dir)
    public_questions = read_jsonl(paths.public_questions_path)
    public_text = json.dumps(public_questions, ensure_ascii=False)

    assert "rubric" not in public_text
    assert "ideal_response" not in public_text
    assert "gold_answer" not in public_text


def test_beam_fake_chain_resume_skips_completed_conversation(
    tmp_path: Path,
) -> None:
    """resume 应跳过已完成 conversation。"""

    # 第一次运行
    run_context = _run_context(tmp_path)
    run_predictions(
        dataset=_beam_dataset("beam-resume-1"),
        system=FakeBeamProvider(),
        run_context=run_context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="100k",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_beam_unified_answer_prompt,
        protocol_version="v3",
    )

    # 第二次 resume
    second_provider = FakeBeamProvider()
    resume_context = _run_context(tmp_path, resume=True)
    run_predictions(
        dataset=_beam_dataset("beam-resume-1"),
        system=second_provider,
        run_context=resume_context,
        policy=PredictionRunPolicy(max_workers=1, resume=True, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="100k",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_beam_unified_answer_prompt,
        protocol_version="v3",
    )

    # resume 不应重复 ingest（已完成的 conversation 应跳过）
    ingest_count = sum(1 for call in second_provider.calls if call[0] == "ingest")
    assert ingest_count == 0, "resume should skip already-completed conversation"


def test_beam_fake_chain_answer_prompt_uses_rag_template(
    tmp_path: Path,
) -> None:
    """BEAM unified answer prompt 应使用官方 RAG 模板（非 long-context 路径）。"""

    run_context = _run_context(tmp_path)
    run_predictions(
        dataset=_beam_dataset(),
        system=FakeBeamProvider(),
        run_context=run_context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest={"adapter": "fake-v3", "protocol_version": "v3"},
        benchmark_variant="100k",
        run_scope=RunScope.SMOKE,
        answer_reader=_reader(),
        unified_prompt_builder=build_beam_unified_answer_prompt,
        protocol_version="v3",
    )

    paths = ExperimentPaths.create(run_context.run_dir)
    prompts = read_jsonl(paths.artifacts_dir / "answer_prompts.prediction.jsonl")
    answer_prompt = prompts[0]["answer_prompt"]

    # RAG 路径关键词
    assert "Answer ONLY based on the provided context" in answer_prompt
    # 不应使用 long-context 路径
    assert "NOTE: Only provide the answer" not in answer_prompt

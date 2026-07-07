"""测试 MemBench 离线 choice accuracy evaluator。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, Question
from memory_benchmark.evaluators.membench_choice_accuracy import (
    MemBenchChoiceAccuracyEvaluator,
)
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_jsonl,
    evaluator_private_label_record,
    public_question_record,
)


pytestmark = pytest.mark.unit


def test_membench_choice_accuracy_scores_correct_wrong_and_invalid_choice() -> None:
    """MemBench accuracy 应覆盖正确、错误与 invalid_choice 三态。"""

    evaluator = MemBenchChoiceAccuracyEvaluator()
    question = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="Which option?",
        category="highlevel",
    )
    gold = GoldAnswerInfo(
        question_id="conv-1:q1",
        answer="Coffee",
        metadata={"ground_truth": "B"},
    )

    correct = evaluator.evaluate(
        question,
        AnswerResult("conv-1:q1", "conv-1", "B"),
        gold,
    )
    wrong = evaluator.evaluate(
        question,
        AnswerResult("conv-1:q1", "conv-1", "A"),
        gold,
    )
    invalid = evaluator.evaluate(
        question,
        AnswerResult("conv-1:q1", "conv-1", "invalid_choice"),
        gold,
    )

    assert correct.score == 1.0
    assert correct.is_correct is True
    assert correct.details["category"] == "highlevel"
    assert wrong.score == 0.0
    assert wrong.is_correct is False
    assert invalid.score == 0.0
    assert invalid.is_correct is False
    assert invalid.details["valid_prediction"] is False


def test_membench_choice_accuracy_summary_uses_question_type_breakdown(
    tmp_path: Path,
) -> None:
    """artifact evaluation summary 应按 MemBench question_type 生成 category breakdown。"""

    run_dir = tmp_path / "membench-run"
    paths = ExperimentPaths.create(run_dir)
    _write_manifest(run_dir)
    questions = [
        Question("q-1", "conv-1", "Q1?", category="highlevel"),
        Question("q-2", "conv-1", "Q2?", category="highlevel"),
        Question("q-3", "conv-2", "Q3?", category="lowlevel"),
    ]
    atomic_write_jsonl(
        paths.public_questions_path,
        [public_question_record(question) for question in questions],
    )
    atomic_write_jsonl(
        paths.method_predictions_path,
        [
            {
                "question_id": "q-1",
                "conversation_id": "conv-1",
                "question_text": "Q1?",
                "answer": "A",
            },
            {
                "question_id": "q-2",
                "conversation_id": "conv-1",
                "question_text": "Q2?",
                "answer": "invalid_choice",
            },
            {
                "question_id": "q-3",
                "conversation_id": "conv-2",
                "question_text": "Q3?",
                "answer": "C",
            },
        ],
    )
    atomic_write_jsonl(
        paths.evaluator_private_labels_path,
        [
            evaluator_private_label_record(
                GoldAnswerInfo("q-1", "A text", metadata={"ground_truth": "A"}),
                category="highlevel",
            ),
            evaluator_private_label_record(
                GoldAnswerInfo("q-2", "B text", metadata={"ground_truth": "B"}),
                category="highlevel",
            ),
            evaluator_private_label_record(
                GoldAnswerInfo("q-3", "C text", metadata={"ground_truth": "C"}),
                category="lowlevel",
            ),
        ],
    )

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=MemBenchChoiceAccuracyEvaluator(),
        expected_benchmark="membench",
    )

    assert summary.metric_name == "membench_choice_accuracy"
    assert summary.mean_score == pytest.approx(2 / 3)
    summary_payload = json.loads(
        (run_dir / "summaries" / "summary.membench_choice_accuracy.json").read_text(
            encoding="utf-8",
        )
    )
    breakdown = {
        entry["category"]: entry for entry in summary_payload["category_breakdown"]
    }
    assert breakdown["highlevel"]["question_count"] == 2
    assert breakdown["highlevel"]["mean_score"] == 0.5
    assert breakdown["lowlevel"]["question_count"] == 1
    assert breakdown["lowlevel"]["mean_score"] == 1.0


def _write_manifest(run_dir: Path) -> None:
    """写入最小 prediction manifest。"""

    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runner": "generic_conversation_qa_prediction",
                "run_id": "membench-run",
                "benchmark_name": "membench",
                "method_name": "fake",
                "model_name": "fake",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

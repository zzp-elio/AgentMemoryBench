"""MemBench 论文来源四格准确率合成指标测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.core import AnswerResult, ConfigurationError, GoldAnswerInfo, Question
from memory_benchmark.evaluators.membench_choice_accuracy import (
    MemBenchChoiceAccuracyEvaluator,
)
from memory_benchmark.evaluators.membench_source_accuracy import (
    MemBenchSourceAccuracyEvaluator,
)
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    evaluator_private_label_record,
    public_question_record,
)


pytestmark = pytest.mark.unit


def test_four_cells_aggregate_from_conversation_id_prefix(tmp_path: Path) -> None:
    """四个 source 前缀应从真实 choice evaluator score 聚合。"""

    paths = _write_choice_run(
        tmp_path,
        [
            ("first-high-factual-s1-t1", "A", "A"),
            ("first-low-reflective-s2-t2", "A", "B"),
            ("third-high-factual-s3-t3", "C", "C"),
            ("third-low-reflective-s4-t4", "D", "D"),
        ],
    )
    result = MemBenchSourceAccuracyEvaluator().evaluate_run_artifacts(
        paths=paths, manifest={}
    )
    cells = {record["cell"]: record for record in result["score_records"]}
    assert [record["cell"] for record in result["score_records"][:4]] == [
        "first-high", "first-low", "third-high", "third-low"
    ]
    assert cells["first-high"]["accuracy"] == 1.0
    assert cells["first-low"]["accuracy"] == 0.0
    assert cells["third-high"]["accuracy"] == 1.0
    assert cells["third-low"]["accuracy"] == 1.0
    assert cells["total"]["question_count"] == 4
    assert cells["total"]["accuracy"] == pytest.approx(0.75)


def test_missing_upstream_artifact_fails_fast(tmp_path: Path) -> None:
    """缺少 choice-accuracy 上游 artifact 时必须 fail-fast。"""

    with pytest.raises(ConfigurationError, match="requires prior membench-choice-accuracy"):
        MemBenchSourceAccuracyEvaluator().evaluate_run_artifacts(
            paths=ExperimentPaths.create(tmp_path / "run"), manifest={}
        )


def test_unknown_source_prefix_fails_fast(tmp_path: Path) -> None:
    """未知 conversation_id 来源前缀不得静默丢弃。"""

    paths = _write_choice_run(tmp_path, [("unknown-high-factual-s1-t1", "A", "A")])
    with pytest.raises(ConfigurationError, match="unknown-high-factual-s1-t1"):
        MemBenchSourceAccuracyEvaluator().evaluate_run_artifacts(paths=paths, manifest={})


def test_empty_cell_reports_none_accuracy_with_zero_count(tmp_path: Path) -> None:
    """未出现的论文格应保留固定位置并报告 None/0。"""

    paths = _write_choice_run(tmp_path, [("first-high-factual-s1-t1", "A", "A")])
    result = MemBenchSourceAccuracyEvaluator().evaluate_run_artifacts(
        paths=paths, manifest={}
    )
    cells = {record["cell"]: record for record in result["score_records"]}
    assert cells["third-low"]["question_count"] == 0
    assert cells["third-low"]["correct_count"] == 0
    assert cells["third-low"]["accuracy"] is None


def _write_choice_run(
    tmp_path: Path,
    rows: list[tuple[str, str, str]],
) -> ExperimentPaths:
    """经生产 serializers 与 choice evaluator 生成真实上游 score artifact。"""

    run_dir = tmp_path / "run"
    paths = ExperimentPaths.create(run_dir)
    atomic_write_json(
        paths.manifest_path,
        {
            "schema_version": 2,
            "run_id": "membench-source-run",
            "benchmark_name": "membench",
            "method_name": "fake",
            "model_name": "fake",
        },
    )
    questions: list[Question] = []
    predictions: list[dict[str, object]] = []
    labels: list[dict[str, object]] = []
    for index, (conversation_id, prediction, gold) in enumerate(rows, start=1):
        question_id = f"{conversation_id}:q{index}"
        question = Question(question_id, conversation_id, "Which option?", category="highlevel")
        questions.append(question)
        answer = AnswerResult(question_id, conversation_id, prediction)
        predictions.append(
            {
                "question_id": answer.question_id,
                "conversation_id": answer.conversation_id,
                "question_text": question.text,
                "answer": answer.answer,
            }
        )
        labels.append(
            evaluator_private_label_record(
                GoldAnswerInfo(question_id, gold, metadata={"ground_truth": gold}),
                category=question.category,
            )
        )
    atomic_write_jsonl(
        paths.public_questions_path,
        [public_question_record(question) for question in questions],
    )
    atomic_write_jsonl(paths.method_predictions_path, predictions)
    atomic_write_jsonl(paths.evaluator_private_labels_path, labels)
    run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=MemBenchChoiceAccuracyEvaluator(),
        expected_benchmark="membench",
    )
    return paths

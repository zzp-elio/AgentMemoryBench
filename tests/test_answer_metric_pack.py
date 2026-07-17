"""通用 answer metric pack（normalized EM + directional substring EM）测试。

单题层锁死两个新指标的公式语义（归一化、partial 不满分、空 gold 不满分、
方向固定、token 边界、连续 token）；集成层用最小 fake run 证明它们经统一
`run_artifact_evaluation()` 的 answer-level 路径写出 score/summary，且不读取
`.env`、不构造 OpenAI settings/client、不重跑 method。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.core import (
    AnswerResult,
    GoldAnswerInfo,
    MetricResult,
    Question,
)
from memory_benchmark.evaluators.answer_metrics import (
    NormalizedExactMatchEvaluator,
    SubstringExactMatchEvaluator,
)
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.unit


def _evaluate(
    evaluator: object,
    prediction: str,
    gold: str,
    *,
    question_id: str = "q1",
    category: str | None = None,
) -> MetricResult:
    """构造同 id 实体并执行给定 answer-level evaluator。"""

    question = Question(
        question_id=question_id,
        conversation_id="c1",
        text="Question?",
        category=category,
    )
    answer = AnswerResult(
        question_id=question_id,
        conversation_id="c1",
        answer=prediction,
    )
    gold_answer = GoldAnswerInfo(question_id=question_id, answer=gold)
    return evaluator.evaluate(question, answer, gold_answer)


# ---------------------------------------------------------------------------
# normalized EM
# ---------------------------------------------------------------------------


def test_normalized_em_ignores_case_punctuation_articles_and_whitespace() -> None:
    """大小写、标点、冠词与空白归一化后相等应记满分。"""

    result = _evaluate(NormalizedExactMatchEvaluator(), "  The Seattle!  ", "seattle")

    assert result.metric_name == "normalized_em"
    assert result.score == 1.0
    assert result.is_correct is True
    assert result.details["metric_tier"] == "framework_supplementary"
    assert result.details["metric_pack_version"] == "answer-text-v1"
    assert result.details["strategy"] == "normalized_exact_match"
    assert result.details["normalized_prediction"] == "seattle"
    assert result.details["normalized_gold"] == "seattle"
    assert result.details["empty_normalized_gold"] is False


def test_normalized_em_matches_after_article_and_conjunction_removal() -> None:
    """`and` 与冠词属于归一化删除 token，不影响精确匹配。"""

    result = _evaluate(NormalizedExactMatchEvaluator(), "Salt and Pepper", "the salt pepper")

    assert result.score == 1.0
    assert result.details["normalized_prediction"] == "salt pepper"
    assert result.details["normalized_gold"] == "salt pepper"


def test_normalized_em_partial_overlap_is_not_full_match() -> None:
    """部分重叠不得记满分。"""

    result = _evaluate(NormalizedExactMatchEvaluator(), "Seattle Washington", "Seattle")

    assert result.score == 0.0
    assert result.is_correct is False


def test_normalized_em_empty_normalized_gold_scores_zero_not_full() -> None:
    """归一化 gold 为空固定记 0，即使预测同样归一化为空也不满分。"""

    result = _evaluate(NormalizedExactMatchEvaluator(), "the", "the!")

    assert result.details["normalized_prediction"] == ""
    assert result.details["normalized_gold"] == ""
    assert result.details["empty_normalized_gold"] is True
    assert result.score == 0.0
    assert result.is_correct is False


# ---------------------------------------------------------------------------
# directional substring EM
# ---------------------------------------------------------------------------


def test_substring_em_gold_contained_in_prediction_scores_one() -> None:
    """归一化 gold 作为连续 token 出现在预测中记 1（多余预测上下文允许）。"""

    result = _evaluate(
        SubstringExactMatchEvaluator(),
        "Alice moved to Seattle in 2023",
        "Seattle",
    )

    assert result.metric_name == "substring_em"
    assert result.score == 1.0
    assert result.is_correct is True
    assert result.details["direction"] == "gold_in_prediction"
    assert result.details["strategy"] == "gold_in_prediction_substring_em"
    assert result.details["metric_pack_version"] == "answer-text-v1"
    assert result.details["gold_tokens"] == ["seattle"]
    assert result.details["prediction_tokens"] == [
        "alice",
        "moved",
        "to",
        "seattle",
        "in",
        "2023",
    ]


def test_substring_em_direction_is_fixed_gold_in_prediction() -> None:
    """方向固定：预测是 gold 的子串（反方向）不记分。"""

    result = _evaluate(SubstringExactMatchEvaluator(), "Seattle", "Seattle in 2023")

    assert result.score == 0.0
    assert result.is_correct is False


def test_substring_em_requires_contiguous_tokens() -> None:
    """gold token 必须连续出现，散布命中不计。"""

    result = _evaluate(SubstringExactMatchEvaluator(), "red car and blue bike", "red bike")

    assert result.details["prediction_tokens"] == ["red", "car", "blue", "bike"]
    assert result.details["gold_tokens"] == ["red", "bike"]
    assert result.score == 0.0


def test_substring_em_matches_contiguous_multi_token_gold() -> None:
    """连续多 token gold 命中记 1。"""

    result = _evaluate(
        SubstringExactMatchEvaluator(),
        "she lives in New York City now",
        "New York",
    )

    assert result.score == 1.0


def test_substring_em_does_not_match_on_bare_character_overlap() -> None:
    """token 边界避免 `cat` 命中 `concatenate` 之类裸字符误判。"""

    result = _evaluate(SubstringExactMatchEvaluator(), "concatenate", "cat")

    assert result.details["prediction_tokens"] == ["concatenate"]
    assert result.details["gold_tokens"] == ["cat"]
    assert result.score == 0.0


def test_substring_em_empty_normalized_gold_scores_zero() -> None:
    """归一化 gold 为空固定记 0。"""

    result = _evaluate(SubstringExactMatchEvaluator(), "anything here", "the")

    assert result.details["gold_tokens"] == []
    assert result.details["empty_normalized_gold"] is True
    assert result.score == 0.0
    assert result.is_correct is False


# ---------------------------------------------------------------------------
# 集成：artifact-only 离线复算
# ---------------------------------------------------------------------------


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    """写入测试所需 JSONL。"""

    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_manifest(run_dir: Path, *, benchmark_name: str) -> None:
    """写入最小 manifest（answer-level 指标不需要 gold-evidence/method 契约）。"""

    (run_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "runner": "generic_conversation_qa_prediction",
                "run_id": "metric-pack-run",
                "benchmark_name": benchmark_name,
                "method_name": "fake-method",
                "model_name": "fake-model",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_answer_metric_pack_runs_through_artifact_evaluation_offline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两个新 metric 经统一 runner 写 score/summary，且不读 .env、不重跑 method。"""

    run_dir = ExperimentPaths.create(tmp_path / "metric-pack-run").run_dir
    _write_manifest(run_dir, benchmark_name="locomo")
    _write_jsonl(
        run_dir / "artifacts" / "public_questions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question_text": "Where did Alice move?",
                "category": "2",
                "metadata": {},
            },
            {
                "question_id": "conv-1:q2",
                "conversation_id": "conv-1",
                "question_text": "Where does Bob live?",
                "category": "2",
                "metadata": {},
            },
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "method_predictions.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "answer": "Alice moved to Seattle in 2023",
                "metadata": {"method": "fake"},
            },
            {
                "question_id": "conv-1:q2",
                "conversation_id": "conv-1",
                "answer": "Portland",
                "metadata": {"method": "fake"},
            },
        ],
    )
    _write_jsonl(
        run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        [
            {
                "question_id": "conv-1:q1",
                "gold_answer": "Seattle",
                "category": "2",
                "evidence": [],
                "metadata": {},
            },
            {
                "question_id": "conv-1:q2",
                "gold_answer": "Seattle",
                "category": "2",
                "evidence": [],
                "metadata": {},
            },
        ],
    )

    original_read_text = Path.read_text

    def guarded_read_text(self: Path, *args: object, **kwargs: object):
        """阻止 answer metric pack 意外读取 `.env`。"""

        if self.name == ".env":
            raise AssertionError("answer metric pack must not read .env")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    em_summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=NormalizedExactMatchEvaluator(),
        expected_benchmark="locomo",
    )
    substring_summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=SubstringExactMatchEvaluator(),
        expected_benchmark="locomo",
    )

    # normalized EM：两题都非精确相等 → 均值 0。
    assert em_summary.metric_name == "normalized_em"
    assert em_summary.total_questions == 2
    assert em_summary.mean_score == 0.0
    assert em_summary.correct_count == 0

    # substring EM：q1 gold "seattle" 连续出现在预测中 → 1；q2 未出现 → 0。
    assert substring_summary.metric_name == "substring_em"
    assert substring_summary.total_questions == 2
    assert substring_summary.mean_score == 0.5
    assert substring_summary.correct_count == 1

    em_scores = read_jsonl(Path(em_summary.score_path))
    substring_scores = read_jsonl(Path(substring_summary.score_path))
    assert {record["question_id"]: record["score"] for record in em_scores} == {
        "conv-1:q1": 0.0,
        "conv-1:q2": 0.0,
    }
    assert {record["question_id"]: record["score"] for record in substring_scores} == {
        "conv-1:q1": 1.0,
        "conv-1:q2": 0.0,
    }
    assert Path(em_summary.summary_path).is_file()
    assert Path(substring_summary.summary_path).is_file()
    # answer-level 路径完整落盘 details（含 pack identity 与方向）。
    assert em_scores[0]["details"]["metric_pack_version"] == "answer-text-v1"
    assert substring_scores[0]["details"]["direction"] == "gold_in_prediction"

    # 未重跑 method：仅消费既有 artifact，method_predictions.jsonl 内容不变。
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    assert [record["answer"] for record in predictions] == [
        "Alice moved to Seattle in 2023",
        "Portland",
    ]

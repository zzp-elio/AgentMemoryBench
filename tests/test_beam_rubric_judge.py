"""测试 BEAM rubric-nugget LLM judge evaluator。

关键测试：**float 0.5 不被 int() 截断**（回归官方 compute_metrics.py bug）、
rubric 逐条聚合、ability breakdown、event_ordering v1 仅 rubric 路径。
全部测试用 fake judge client，不调真实 API。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.evaluators.beam_rubric_judge import (
    BEAM_ABILITY_KEYS,
    BEAM_JUDGE_PROMPT,
    BeamRubricJudgeEvaluator,
    _build_evaluation_payload,
    _extract_ability,
    _extract_rubric,
    _index_by_question_id,
    _parse_judge_json,
)
from memory_benchmark.core.exceptions import JudgeOutputError
from memory_benchmark.storage import ExperimentPaths


# ---------------------------------------------------------------------------
# fake judge client
# ---------------------------------------------------------------------------


class _FakeBeamJudgeClient:
    """返回固定分数的 fake judge client。

    可以用 judge_json(prompt) 被 BeamRubricJudgeEvaluator._judge_json 调用。
    """

    def __init__(self, score: float = 1.0, reason: str = "fake"):
        self.score = score
        self.reason = reason
        self.calls: list[str] = []

    def judge_json(self, prompt: str) -> dict[str, Any]:
        """记录调用并返回固定分数。"""

        self.calls.append(prompt)
        return {"score": self.score, "reason": self.reason}


# ---------------------------------------------------------------------------
# helper: write minimal artifacts for evaluate_run_artifacts
# ---------------------------------------------------------------------------


def _write_artifacts(
    artifacts_dir: Path,
    *,
    questions: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    private_labels: list[dict[str, Any]],
) -> ExperimentPaths:
    """在 artifacts_dir 中写入三个必要 JSONL 并返回 ExperimentPaths。"""

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    for name, records in [
        ("public_questions.jsonl", questions),
        ("method_predictions.jsonl", predictions),
        ("evaluator_private_labels.jsonl", private_labels),
    ]:
        path = artifacts_dir / name
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return ExperimentPaths(run_dir=artifacts_dir.parent)


def _make_question_record(
    question_id: str,
    question_text: str,
    conversation_id: str = "1",
    category: str | None = None,
) -> dict[str, Any]:
    """构造一条 public_questions 记录。"""

    return {
        "question_id": question_id,
        "conversation_id": conversation_id,
        "question_text": question_text,
        "question_time": None,
        "category": category,
        "metadata": {},
    }


def _make_prediction_record(
    question_id: str,
    answer: str,
    conversation_id: str = "1",
) -> dict[str, Any]:
    """构造一条 method_predictions 记录。"""

    return {
        "question_id": question_id,
        "conversation_id": conversation_id,
        "answer": answer,
        "metadata": {},
    }


def _make_private_label(
    question_id: str,
    gold_answer: str = "test answer",
    rubric: list[Any] | None = None,
    ability: str = "abstention",
) -> dict[str, Any]:
    """构造一条 evaluator_private_labels 记录。"""

    return {
        "question_id": question_id,
        "gold_answer": gold_answer,
        "category": ability,
        "evidence": [],
        "metadata": {
            "ability": ability,
            "rubric": rubric or ["test rubric item"],
            "difficulty": "easy",
        },
    }


# ---------------------------------------------------------------------------
# T3.1 rubric 逐条聚合口径（对齐 compute_metrics.py:346-360）
# ---------------------------------------------------------------------------


def test_rubric_aggregation_aligns_with_official_formula() -> None:
    """每条 rubric item 独立打分 → llm_judge_score = Σ(item_score)/len(rubric)。"""

    evaluator = BeamRubricJudgeEvaluator(
        mode="compact",
        client=_FakeBeamJudgeClient(score=0.5),
    )

    # 3 条 rubric items，每条 fake judge 返回 0.5 → 期望均值 0.5
    rubric = ["item 1", "item 2", "item 3"]
    score_records = _run_mini_evaluation(evaluator, rubric=rubric, answer="test response")

    assert len(score_records) == 1
    record = score_records[0]
    # 均值 = (0.5 + 0.5 + 0.5) / 3 = 0.5
    assert record["score"] == pytest.approx(0.5)
    assert record["rubric_count"] == 3
    assert len(record["item_scores"]) == 3
    for item_score in record["item_scores"]:
        assert item_score["score"] == 0.5


# ---------------------------------------------------------------------------
# T3.2 **float 0.5 不被截断**（回归官方 int bug——最关键测试）
# ---------------------------------------------------------------------------


def test_score_0_5_is_preserved_not_truncated_to_0() -> None:
    """单项 rubric 得 0.5 时聚合分是 0.5 不是 0。

    官方 compute_metrics.py 9 个 evaluate_* 用 int(response['score'])
    把 0.5 截成 0。本测试专门锁：float 语义下 0.5 完整保留。
    """

    evaluator = BeamRubricJudgeEvaluator(
        mode="compact",
        client=_FakeBeamJudgeClient(score=0.5),
    )

    # 单条 rubric item，fake judge 返回 0.5 → 聚合分应为 0.5
    rubric = ["single rubric item that gets partial credit"]
    score_records = _run_mini_evaluation(evaluator, rubric=rubric, answer="partial answer")

    record = score_records[0]
    assert record["score"] == pytest.approx(0.5), (
        f"BUG: 0.5 was truncated to {record['score']}! "
        f"Using float() not int() for judge scores."
    )
    assert record["score"] != 0.0, "0.5 must NOT be truncated to 0 (official int() bug)"


def test_score_mixture_preserves_float_precision() -> None:
    """混合分数 (1.0, 0.5, 0.0) 应保留浮点精度，(1+0.5+0)/3=0.5。"""

    class _MixedFakeClient:
        def __init__(self):
            self.call_count = 0

        def judge_json(self, prompt: str) -> dict[str, Any]:
            scores = [1.0, 0.5, 0.0]
            score = scores[self.call_count % 3]
            self.call_count += 1
            return {"score": score, "reason": "mixed"}

    evaluator = BeamRubricJudgeEvaluator(
        mode="compact",
        client=_MixedFakeClient(),
    )

    rubric = ["item a", "item b", "item c"]
    score_records = _run_mini_evaluation(evaluator, rubric=rubric, answer="mixed answer")

    record = score_records[0]
    expected = (1.0 + 0.5 + 0.0) / 3
    assert record["score"] == pytest.approx(expected)
    assert record["score"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# T3.3 10 ability breakdown
# ---------------------------------------------------------------------------


def test_ability_breakdown_covers_all_10_abilities() -> None:
    """category_breakdown 应包含全部 10 个 ability。"""

    score_records: list[dict[str, Any]] = []
    for ability in BEAM_ABILITY_KEYS:
        for qi in range(1, 3):
            score_records.append(
                {
                    "question_id": f"1:{ability}:q{qi}",
                    "conversation_id": "1",
                    "ability": ability,
                    "score": 0.75,
                    "rubric_count": 2,
                    "item_scores": [],
                    "metric_name": "beam_rubric_judge",
                    "record_kind": "beam_rubric_judge",
                }
            )

    payload = _build_evaluation_payload(score_records)

    assert payload["total_questions"] == 20
    assert payload["mean_score"] == pytest.approx(0.75)

    breakdown = payload["summary"]["category_breakdown"]
    assert len(breakdown) == 10
    breakdown_abilities = {item["category"] for item in breakdown}
    assert breakdown_abilities == set(BEAM_ABILITY_KEYS)

    for item in breakdown:
        assert item["question_count"] == 2
        assert item["rubric_judge_mean_score"] == pytest.approx(0.75)

    overall = payload["summary"]["overall_score"]
    assert overall["beam_rubric_judge_mean"] == pytest.approx(0.75)


def test_ability_breakdown_handles_missing_abilities() -> None:
    """缺失 ability 时 breakdown 应填 0.0，overall 仍按 10 能力取均。"""

    score_records = [
        {
            "question_id": "1:abstention:q1",
            "conversation_id": "1",
            "ability": "abstention",
            "score": 0.8,
            "rubric_count": 2,
            "item_scores": [],
            "metric_name": "beam_rubric_judge",
            "record_kind": "beam_rubric_judge",
        }
    ]

    payload = _build_evaluation_payload(score_records)

    breakdown = payload["summary"]["category_breakdown"]
    abstention_item = next(
        item for item in breakdown if item["category"] == "abstention"
    )
    assert abstention_item["rubric_judge_mean_score"] == pytest.approx(0.8)
    assert abstention_item["question_count"] == 1

    # other abilities → 0.0
    other_item = next(
        item for item in breakdown if item["category"] == "summarization"
    )
    assert other_item["rubric_judge_mean_score"] == 0.0
    assert other_item["question_count"] == 0

    # overall = sum(ability_means) / 10
    overall = payload["summary"]["overall_score"]["beam_rubric_judge_mean"]
    assert overall == pytest.approx(0.08)  # 0.8/10


# ---------------------------------------------------------------------------
# T3.4 event_ordering v1 走 rubric 路径
# ---------------------------------------------------------------------------


def test_event_ordering_v1_uses_rubric_judge_only() -> None:
    """event_ordering v1 仅走 rubric judge 路径，不涉及 kendall-tau 排序分。"""

    evaluator = BeamRubricJudgeEvaluator(
        mode="compact",
        client=_FakeBeamJudgeClient(score=1.0),
    )

    rubric = ["event A before event B", "event C after event D"]
    score_records = _run_mini_evaluation(
        evaluator,
        rubric=rubric,
        answer="events ordered correctly",
        ability="event_ordering",
    )

    record = score_records[0]
    assert record["ability"] == "event_ordering"
    assert record["score"] == pytest.approx(1.0)
    assert len(record["item_scores"]) == 2
    # 确认只有 rubric judge 逻辑，没有 kendall-tau
    for item_score in record["item_scores"]:
        assert "score" in item_score
        assert "reason" in item_score


# ---------------------------------------------------------------------------
# T3.5 judge prompt 结构
# ---------------------------------------------------------------------------


def test_judge_prompt_contains_required_sections() -> None:
    """BEAM judge prompt 应包含官方 unified_llm_judge_base_prompt 关键要素。"""

    assert "SCORING SCALE" in BEAM_JUDGE_PROMPT
    assert "1.0 (Complete Compliance)" in BEAM_JUDGE_PROMPT
    assert "0.5 (Partial Compliance)" in BEAM_JUDGE_PROMPT
    assert "0.0 (No Compliance)" in BEAM_JUDGE_PROMPT
    assert "<question>" in BEAM_JUDGE_PROMPT
    assert "<rubric_item>" in BEAM_JUDGE_PROMPT
    assert "<llm_response>" in BEAM_JUDGE_PROMPT


def test_judge_prompt_substitution() -> None:
    """placeholders 正确替换为实际值。"""

    prompt = BEAM_JUDGE_PROMPT.replace(
        "<question>", "What did I do?"
    ).replace(
        "<rubric_item>", "Answer mentions coding"
    ).replace(
        "<llm_response>", "You wrote code."
    )

    assert "What did I do?" in prompt
    assert "Answer mentions coding" in prompt
    assert "You wrote code." in prompt
    assert "<question>" not in prompt
    assert "<rubric_item>" not in prompt
    assert "<llm_response>" not in prompt


# ---------------------------------------------------------------------------
# T3.6 JSON 解析
# ---------------------------------------------------------------------------


def test_parse_judge_json_handles_fenced_block() -> None:
    """应能解析 ```json fenced block。"""

    text = '```json\n{"score": 0.5, "reason": "partial"}\n```'
    result = _parse_judge_json(text)
    assert result == {"score": 0.5, "reason": "partial"}


def test_parse_judge_json_handles_plain_json() -> None:
    """应能解析裸 JSON。"""

    text = '{"score": 1.0, "reason": "full compliance"}'
    result = _parse_judge_json(text)
    assert result == {"score": 1.0, "reason": "full compliance"}


def test_parse_judge_json_rejects_non_dict() -> None:
    """非 dict JSON 应拒绝。"""

    with pytest.raises(JudgeOutputError, match="JSON object"):
        _parse_judge_json("[1, 2, 3]")


def test_parse_judge_json_rejects_invalid() -> None:
    """无效 JSON 应拒绝。"""

    with pytest.raises(JudgeOutputError, match="JSON"):
        _parse_judge_json("not json at all")


# ---------------------------------------------------------------------------
# T3.7 helper 单元测试
# ---------------------------------------------------------------------------


def test_extract_rubric_from_private_label() -> None:
    """应正确从私有标签提取 rubric。"""

    label = {"metadata": {"rubric": ["item 1", "item 2"]}}
    assert _extract_rubric(label) == ["item 1", "item 2"]

    assert _extract_rubric({"metadata": {}}) == []
    assert _extract_rubric({}) == []
    assert _extract_rubric({"metadata": {"rubric": "not a list"}}) == []


def test_extract_ability_from_private_label() -> None:
    """应正确从私有标签提取 ability。"""

    assert _extract_ability({"metadata": {"ability": "summarization"}}) == "summarization"
    assert _extract_ability({"metadata": {}}) is None
    assert _extract_ability({}) is None


def test_index_by_question_id_rejects_duplicates() -> None:
    """重复 question_id 应拒绝。"""

    from memory_benchmark.core.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError, match="duplicate"):
        _index_by_question_id(
            [
                {"question_id": "dup"},
                {"question_id": "dup"},
            ]
        )


# ---------------------------------------------------------------------------
# internal helper
# ---------------------------------------------------------------------------


def _run_mini_evaluation(
    evaluator: BeamRubricJudgeEvaluator,
    *,
    rubric: list[str],
    answer: str = "test answer",
    ability: str = "abstention",
    question_text: str = "test question?",
    question_id: str = "1:abstention:q1",
) -> list[dict[str, Any]]:
    """用 fake judge 跑一次最小 evaluate_run_artifacts 并返回 score_records。"""

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "test_run"
        artifacts_dir = run_dir / "artifacts"
        paths = _write_artifacts(
            artifacts_dir,
            questions=[_make_question_record(question_id, question_text, category=ability)],
            predictions=[_make_prediction_record(question_id, answer)],
            private_labels=[_make_private_label(question_id, rubric=rubric, ability=ability)],
        )
        result = evaluator.evaluate_run_artifacts(
            paths=paths,
            manifest={"benchmark": "beam"},
        )
    return result["score_records"]

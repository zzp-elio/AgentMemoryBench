"""HaluMem 问答 judge evaluator。"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.storage import ExperimentPaths

from .halumem_common import (
    HALUMEM_JUDGE_PROFILE_NOTE,
    HalumemJudgeEvaluatorBase,
    count_ratios,
    grouped_mean,
    read_required_jsonl,
    safe_div,
)


# Official source: third_party/benchmarks/HaluMem-main/eval/eval_tools.py:218-283
_QUESTION_PROMPT = """You are an **evaluation expert for AI memory system question answering**.

* **Question:**
  {question}

* **Reference Answer:**
  {reference_answer}

* **Key Memory Points:**
  {key_memory_points}

* **Memory System Response:**
  {response}

Return JSON: {{"reasoning": "...", "evaluation_result": "Correct | Hallucination | Omission"}}.
"""


class HalumemQAEvaluator(HalumemJudgeEvaluatorBase):
    """HaluMem QA 三分类聚合 evaluator。"""

    metric_name = "halumem_qa"
    official_source = "eval_tools.py:352-365; evaluation.py:176-197,332-362"
    profile_note = HALUMEM_JUDGE_PROFILE_NOTE

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """读取 QA prediction/private labels 并计算官方 QA 比例。"""

        public_by_id = _index_by_question_id(
            read_required_jsonl(paths.public_questions_path, "public_questions")
        )
        prediction_by_id = _index_by_question_id(
            read_required_jsonl(paths.method_predictions_path, "method_predictions")
        )
        private_by_id = _index_by_question_id(
            read_required_jsonl(
                paths.evaluator_private_labels_path,
                "evaluator_private_labels",
            )
        )
        score_records: list[dict[str, Any]] = []
        for question_id in public_by_id:
            if question_id not in prediction_by_id:
                continue
            if question_id not in private_by_id:
                raise ConfigurationError(f"missing private label for {question_id}")
            public_record = public_by_id[question_id]
            prediction_record = prediction_by_id[question_id]
            private_record = private_by_id[question_id]
            prompt = _QUESTION_PROMPT.format(
                question=public_record.get("question_text", ""),
                reference_answer=private_record.get("gold_answer", ""),
                key_memory_points="\n".join(_string_list(private_record.get("evidence"))),
                response=prediction_record.get("answer", ""),
            )
            result = self._judge_json(prompt)
            result_type = result.get("evaluation_result")
            score_records.append(
                {
                    "record_kind": "question_answering",
                    "question_id": question_id,
                    "conversation_id": public_record.get("conversation_id"),
                    "metric_name": self.metric_name,
                    "score": 1.0 if result_type == "Correct" else 0.0,
                    "result_type": result_type,
                    "question_type": _question_type(private_record),
                    "raw_judge_response": result,
                }
            )

        overall = {
            "question_answering": count_ratios(
                score_records,
                field="result_type",
                labels=("Correct", "Hallucination", "Omission"),
                output_prefix="qa",
                count_name="qa",
            )
        }
        return {
            "metric_name": self.metric_name,
            "score_records": score_records,
            "total_questions": len(score_records),
            "mean_score": safe_div(
                sum(float(record["score"]) for record in score_records),
                len(score_records),
            ),
            "correct_count": sum(
                1 for record in score_records if record.get("result_type") == "Correct"
            ),
            "summary": {
                "overall_score": overall,
                "category_breakdown": grouped_mean(
                    score_records,
                    category_field="question_type",
                    score_field="score",
                    output_score_name="correct_qa_ratio",
                    output_count_name="question_count",
                ),
                "official_source": self.official_source,
                "profile_note": self.profile_note,
            },
        }


def _index_by_question_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按 question_id 索引 artifact records。"""

    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        question_id = record.get("question_id")
        if not isinstance(question_id, str) or not question_id.strip():
            raise ConfigurationError("question_id is required")
        if question_id in indexed:
            raise ConfigurationError(f"duplicate question_id: {question_id}")
        indexed[question_id] = record
    return indexed


def _question_type(private_record: dict[str, Any]) -> str | None:
    """读取 HaluMem question_type。"""

    metadata = private_record.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("question_type")
    return value if isinstance(value, str) else None


def _string_list(value: Any) -> list[str]:
    """读取字符串列表。"""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]

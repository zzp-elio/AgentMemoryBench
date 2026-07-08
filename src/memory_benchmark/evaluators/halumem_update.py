"""HaluMem 记忆更新 judge evaluator。"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.storage import ExperimentPaths

from .halumem_common import (
    HALUMEM_JUDGE_PROFILE_NOTE,
    HalumemJudgeEvaluatorBase,
    count_ratios,
    index_session_labels,
    memory_points_by_index,
    read_jsonl_or_empty,
    read_session_labels,
    safe_div,
    session_key_from_ref,
)


# Official source: third_party/benchmarks/HaluMem-main/eval/eval_tools.py:161-215
_UPDATE_PROMPT = """Your task is to **evaluate the update accuracy** of an AI memory system.

1. **Generated Memories:**
   {memories}

2. **Target Memory for Update:**
   {updated_memory}

3. **Original Memory Content:**
   {original_memory}

Return JSON: {{"reason": "...", "evaluation_result": "Correct | Hallucination | Omission | Other"}}.
"""


class HalumemUpdateEvaluator(HalumemJudgeEvaluatorBase):
    """HaluMem memory update 聚合 evaluator。"""

    metric_name = "halumem_update"
    official_source = "eval_tools.py:329-349; evaluation.py:154-174,294-330"
    profile_note = HALUMEM_JUDGE_PROFILE_NOTE

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """读取 update probe artifact 并计算 update 比例。"""

        session_labels = index_session_labels(read_session_labels(paths))
        update_records = read_jsonl_or_empty(
            paths.artifacts_dir / "update_probe_results.jsonl",
            "update_probe_results",
        )
        score_records: list[dict[str, Any]] = []
        for update_record in update_records:
            session_id = session_key_from_ref(update_record)
            session_label = session_labels.get(session_id)
            if session_label is None:
                raise ConfigurationError(
                    f"missing session label for update session: {session_id}"
                )
            memory_point = memory_points_by_index(session_label).get(
                update_record.get("gold_memory_index")
            )
            if memory_point is None:
                raise ConfigurationError(
                    "missing gold memory point for update probe "
                    f"{session_id}:{update_record.get('gold_memory_index')}"
                )
            memories_from_system = _string_list(
                update_record.get("memories_from_system")
            )
            prompt = _UPDATE_PROMPT.format(
                memories="\n".join(memories_from_system),
                updated_memory=memory_point.get("memory_content", ""),
                original_memory="\n".join(
                    _string_list(memory_point.get("original_memories"))
                ),
            )
            result = self._judge_json(prompt)
            update_type = result.get("evaluation_result")
            score_records.append(
                {
                    "record_kind": "memory_update",
                    "session_id": session_id,
                    "gold_memory_index": update_record.get("gold_memory_index"),
                    "metric_name": self.metric_name,
                    "score": 1.0 if update_type == "Correct" else 0.0,
                    "memory_update_type": update_type,
                    "memory_content": memory_point.get("memory_content"),
                    "memory_type": memory_point.get("memory_type"),
                    "raw_judge_response": result,
                }
            )

        overall = {
            "memory_update": count_ratios(
                score_records,
                field="memory_update_type",
                labels=("Correct", "Hallucination", "Omission", "Other"),
                output_prefix="update_memory",
                count_name="update_memory",
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
                1 for record in score_records if record.get("memory_update_type") == "Correct"
            ),
            "summary": {
                "overall_score": overall,
                "official_source": self.official_source,
                "profile_note": self.profile_note,
            },
        }


def _string_list(value: Any) -> list[str]:
    """读取字符串列表。"""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]

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
from .halumem_prompts import EVALUATION_PROMPT_FOR_UPDATE_MEMORY as _UPDATE_PROMPT


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
        skipped_empty_retrieval_count = 0
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
            if not memories_from_system:
                # 官方路由（evaluation.py:59-70）：memories_from_system 为空的
                # update point 归 integrity 桶，不进入 update 评测与分母。
                skipped_empty_retrieval_count += 1
                continue
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
                    "importance": memory_point.get("importance"),
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
            ) or 0.0,
            "correct_count": sum(
                1 for record in score_records if record.get("memory_update_type") == "Correct"
            ),
            "summary": {
                "overall_score": overall,
                "category_breakdown": _memory_type_breakdown(score_records),
                "skipped_empty_retrieval_count": skipped_empty_retrieval_count,
                "official_source": self.official_source,
                "profile_note": self.profile_note,
            },
        }


def _string_list(value: Any) -> list[str]:
    """读取字符串列表。"""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _memory_type_breakdown(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 update 阶段内分母输出 memory_type breakdown。"""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        memory_type = record.get("memory_type")
        if memory_type is not None:
            grouped.setdefault(str(memory_type), []).append(record)
    return [
        {
            "category": memory_type,
            "memory_count": len(group),
            "correct_update_ratio": safe_div(
                sum(item.get("memory_update_type") == "Correct" for item in group),
                len(group),
            ),
            "denominator_scope": "update_stage_only",
        }
        for memory_type, group in sorted(grouped.items())
    ]

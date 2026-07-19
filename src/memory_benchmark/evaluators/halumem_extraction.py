"""HaluMem 记忆抽取 judge evaluator。"""

from __future__ import annotations

from typing import Any

from memory_benchmark.storage import ExperimentPaths

from .halumem_common import (
    HALUMEM_JUDGE_PROFILE_NOTE,
    HalumemJudgeEvaluatorBase,
    build_halumem_dialogue_str,
    build_halumem_golden_memories_str,
    compute_f1,
    index_session_labels,
    read_jsonl_or_empty,
    read_required_jsonl,
    read_session_labels,
    safe_div,
    session_key_from_ref,
)
from .halumem_prompts import (
    EVALUATION_PROMPT_FOR_MEMORY_ACCURACY as _ACCURACY_PROMPT,
    EVALUATION_PROMPT_FOR_MEMORY_INTEGRITY as _INTEGRITY_PROMPT,
)


class HalumemExtractionEvaluator(HalumemJudgeEvaluatorBase):
    """HaluMem extraction integrity + accuracy 聚合 evaluator。"""

    metric_name = "halumem_extraction"
    official_source = (
        "eval_tools.py:286-326; evaluation.py:58-152,214-292"
    )
    profile_note = HALUMEM_JUDGE_PROFILE_NOTE

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """读取 operation-level artifacts 并计算 extraction 指标。"""

        sink = self._new_efficiency_observation_sink()
        session_labels = read_session_labels(paths)
        labels_by_session = index_session_labels(session_labels)
        session_reports = read_required_jsonl(
            paths.session_memory_reports_path,
            "session_memory_reports",
        )
        update_records = read_jsonl_or_empty(
            paths.artifacts_dir / "update_probe_results.jsonl",
            "update_probe_results",
        )
        update_memory_keys = _update_memory_keys(update_records)
        score_records: list[dict[str, Any]] = []
        integrity_records: list[dict[str, Any]] = []
        accuracy_records: list[dict[str, Any]] = []
        routed_update_count = 0
        evaluable_reports = [
            report for report in session_reports if report.get("status") == "ok"
        ]
        if not evaluable_reports:
            return self._finalize_artifact_payload(
                _extraction_payload(
                    score_records=[],
                    integrity_records=[],
                    accuracy_records=[],
                    routed_update_count=0,
                    status="n/a",
                ),
                sink,
            )

        for report in evaluable_reports:
            session_id = session_key_from_ref(report)
            session_label = labels_by_session.get(session_id)
            if session_label is None:
                continue
            extracted_memories = _string_list(report.get("memories"))
            extracted_memories_str = "\n".join(extracted_memories)
            memory_points = _memory_points(session_label)
            # 每个 session 一个 judge scope：conversation 用 session 私有标签的真实
            # conversation_id，unit id 是含 metric + session id 的稳定 evaluator-unit id
            # （非公开 QA id，见实现 note），覆盖该 session 的全部 integrity/accuracy 调用。
            conversation_id = session_label.get("conversation_id")
            with sink.unit_scope(
                conversation_id,
                _extraction_scope_unit_id(self.metric_name, session_id),
            ):
                for memory_point in memory_points:
                    key = (session_id, memory_point.get("index"))
                    if memory_point.get("is_update") == "True" and key in update_memory_keys:
                        routed_update_count += 1
                        continue
                    integrity_record = self._evaluate_integrity(
                        session_id=session_id,
                        extracted_memories_str=extracted_memories_str,
                        memory_point=memory_point,
                    )
                    integrity_records.append(integrity_record)
                    score_records.append(integrity_record)

                dialogue_str = build_halumem_dialogue_str(session_label)
                golden_memories_str = build_halumem_golden_memories_str(session_label)
                for candidate_memory in extracted_memories:
                    accuracy_record = self._evaluate_accuracy(
                        session_id=session_id,
                        dialogue_str=dialogue_str,
                        golden_memories_str=golden_memories_str,
                        candidate_memory=candidate_memory,
                    )
                    accuracy_records.append(accuracy_record)
                    score_records.append(accuracy_record)

        return self._finalize_artifact_payload(
            _extraction_payload(
                score_records=score_records,
                integrity_records=integrity_records,
                accuracy_records=accuracy_records,
                routed_update_count=routed_update_count,
                status="ok",
            ),
            sink,
        )

    def _evaluate_integrity(
        self,
        *,
        session_id: str,
        extracted_memories_str: str,
        memory_point: dict[str, Any],
    ) -> dict[str, Any]:
        """对一个 gold memory point 执行 integrity judge。"""

        if extracted_memories_str.strip():
            prompt = _INTEGRITY_PROMPT.format(
                memories=extracted_memories_str,
                expected_memory_point=memory_point.get("memory_content", ""),
            )
            result = self._judge_json(prompt)
            score = _optional_int(result.get("score"))
            raw_result = result
        else:
            score = 0
            raw_result = {"score": "0", "reasoning": "empty extracted memories"}
        return {
            "record_kind": "memory_integrity",
            "session_id": session_id,
            "gold_memory_index": memory_point.get("index"),
            "metric_name": self.metric_name,
            "score": 1.0 if score == 2 else 0.0,
            "memory_integrity_score": score,
            "memory_content": memory_point.get("memory_content"),
            "memory_type": memory_point.get("memory_type"),
            "memory_source": memory_point.get("memory_source"),
            "importance": _importance(memory_point),
            "raw_judge_response": raw_result,
        }

    def _evaluate_accuracy(
        self,
        *,
        session_id: str,
        dialogue_str: str,
        golden_memories_str: str,
        candidate_memory: str,
    ) -> dict[str, Any]:
        """对一条 extracted memory 执行 accuracy judge。"""

        prompt = _ACCURACY_PROMPT.format(
            dialogue=dialogue_str,
            golden_memories=golden_memories_str,
            candidate_memory=candidate_memory,
        )
        result = self._judge_json(prompt)
        accuracy_score = _optional_int(result.get("accuracy_score"))
        included = str(result.get("is_included_in_golden_memories", "false"))
        return {
            "record_kind": "memory_accuracy",
            "session_id": session_id,
            "metric_name": self.metric_name,
            "score": 0.5 * accuracy_score if accuracy_score is not None else 0.0,
            "candidate_memory": candidate_memory,
            "memory_accuracy_score": accuracy_score,
            "is_included_in_golden_memories": included,
            "raw_judge_response": result,
        }


def _extraction_scope_unit_id(metric_name: str, session_id: str) -> str:
    """构造 extraction efficiency scope 的稳定 evaluator-unit id。

    extraction 官方评测按 session 而非公开 QA 遍历，因此没有天然公开 question id；这里用
    `<metric>:<session_id>` 作为无碰撞的 evaluator-unit 标识，只用于 efficiency observation
    归属，绝不是公开 QA id，也不会写回任何 score/summary artifact。
    """

    return f"{metric_name}:{session_id}"


def _extraction_payload(
    *,
    score_records: list[dict[str, Any]],
    integrity_records: list[dict[str, Any]],
    accuracy_records: list[dict[str, Any]],
    routed_update_count: int,
    status: str,
) -> dict[str, Any]:
    """构造 artifact-level evaluation payload。"""

    overall = _aggregate_extraction(
        integrity_records=integrity_records,
        accuracy_records=accuracy_records,
        routed_update_count=routed_update_count,
    )
    return {
        "metric_name": "halumem_extraction",
        "score_records": score_records,
        "total_questions": len(score_records),
        "mean_score": overall["memory_extraction_f1"] or 0.0,
        "correct_count": None,
        "summary": {
            "status": status,
            "overall_score": overall,
            "category_breakdown": _memory_type_breakdown(integrity_records),
            "official_source": HalumemExtractionEvaluator.official_source,
            "profile_note": HALUMEM_JUDGE_PROFILE_NOTE,
        },
    }


def _aggregate_extraction(
    *,
    integrity_records: list[dict[str, Any]],
    accuracy_records: list[dict[str, Any]],
    routed_update_count: int,
) -> dict[str, Any]:
    """按 `evaluation.py:214-292` 聚合 extraction 指标。"""

    non_interference = [
        record
        for record in integrity_records
        if record.get("memory_source") != "interference"
    ]
    interference = [
        record
        for record in integrity_records
        if record.get("memory_source") == "interference"
    ]
    valid_non_interference = [
        record
        for record in non_interference
        if record.get("memory_integrity_score") is not None
    ]
    valid_interference = [
        record
        for record in interference
        if record.get("memory_integrity_score") is not None
    ]
    memory_integrity_scores = sum(
        1
        for record in valid_non_interference
        if record.get("memory_integrity_score") == 2
    )
    weighted_score = sum(
        0.5 * float(record.get("memory_integrity_score", 0)) * _importance(record)
        for record in valid_non_interference
    )
    importance_sum = sum(_importance(record) for record in non_interference)
    valid_importance_sum = sum(_importance(record) for record in valid_non_interference)
    interference_scores = sum(
        1
        for record in valid_interference
        if record.get("memory_integrity_score") == 0
    )

    included_accuracy = [
        record
        for record in accuracy_records
        if record.get("is_included_in_golden_memories") in ("true", "True")
    ]
    valid_accuracy = [
        record
        for record in accuracy_records
        if record.get("memory_accuracy_score") is not None
    ]
    valid_included_accuracy = [
        record
        for record in included_accuracy
        if record.get("memory_accuracy_score") is not None
    ]
    target_accuracy_score = sum(
        0.5 * float(record.get("memory_accuracy_score", 0))
        for record in valid_included_accuracy
    )
    weighted_accuracy_score = sum(
        0.5 * float(record.get("memory_accuracy_score", 0))
        for record in valid_accuracy
    )
    recall = safe_div(memory_integrity_scores, len(non_interference))
    target_accuracy = safe_div(target_accuracy_score, len(included_accuracy))
    return {
        "memory_integrity": {
            "recall(all)": recall,
            "recall(valid)": safe_div(memory_integrity_scores, len(valid_non_interference)),
            "weighted_recall(all)": safe_div(weighted_score, importance_sum),
            "weighted_recall(valid)": safe_div(weighted_score, valid_importance_sum),
            "memory_valid_importance_sum": valid_importance_sum,
            "memory_importance_sum": importance_sum,
            "memory_valid_num": len(valid_non_interference),
            "memory_num": len(non_interference),
        },
        "memory_accuracy": {
            "interference_accuracy(all)": safe_div(
                interference_scores,
                len(interference),
            ),
            "interference_accuracy(valid)": safe_div(
                interference_scores,
                len(valid_interference),
            ),
            "interference_memory_valid_num": len(valid_interference),
            "interference_memory_num": len(interference),
            "target_accuracy(all)": target_accuracy,
            "target_accuracy(valid)": safe_div(
                target_accuracy_score,
                len(valid_included_accuracy),
            ),
            "target_memory_valid_num": len(valid_included_accuracy),
            "target_memory_num": len(included_accuracy),
            "weighted_accuracy(all)": safe_div(
                weighted_accuracy_score,
                len(accuracy_records),
            ),
            "weighted_accuracy(valid)": safe_div(
                weighted_accuracy_score,
                len(valid_accuracy),
            ),
            "memory_valid_num": len(valid_accuracy),
            "memory_num": len(accuracy_records),
        },
        "memory_extraction_f1": compute_f1(target_accuracy, recall),
        "memory_update_routed_num": routed_update_count,
    }


def _memory_type_breakdown(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 memory_type 输出 recall breakdown。"""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if record.get("memory_source") == "interference":
            continue
        memory_type = record.get("memory_type")
        if memory_type is None:
            continue
        grouped.setdefault(str(memory_type), []).append(record)
    breakdown: list[dict[str, Any]] = []
    for memory_type in sorted(grouped):
        group = grouped[memory_type]
        correct = sum(1 for record in group if record.get("memory_integrity_score") == 2)
        breakdown.append(
            {
                "category": memory_type,
                "memory_count": len(group),
                "recall": safe_div(correct, len(group)),
                "denominator_scope": "integrity_stage_only",
            }
        )
    return breakdown


def _update_memory_keys(update_records: list[dict[str, Any]]) -> set[tuple[str, Any]]:
    """返回有检索结果的 update memory key。"""

    keys: set[tuple[str, Any]] = set()
    for record in update_records:
        memories_from_system = record.get("memories_from_system")
        if not memories_from_system:
            continue
        keys.add((session_key_from_ref(record), record.get("gold_memory_index")))
    return keys


def _memory_points(session_label: dict[str, Any]) -> list[dict[str, Any]]:
    """读取 session memory_points。"""

    memory_points = session_label.get("memory_points")
    if not isinstance(memory_points, list):
        return []
    return [item for item in memory_points if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    """把 artifact 字段校验为字符串列表。"""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _optional_int(value: Any) -> int | None:
    """把 judge 分数字段转成 int。"""

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _importance(record: dict[str, Any]) -> float:
    """读取 memory importance，缺失时按 1 处理。"""

    value = record.get("importance", 1)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return 1.0

"""HaluMem 官方 memory_type 共享分母合成指标。"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.storage import ExperimentPaths, read_jsonl

from .halumem_common import safe_div


class HalumemMemoryTypeEvaluator:
    """从 extraction/update 已落盘分数合成官方 memory_type 维度。"""

    metric_name = "halumem_memory_type"
    official_source = "evaluation.py:364-383"

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """读取两份上游 metric artifact 并按官方共享分母聚合。"""

        extraction_path = paths.metric_scores_path("halumem_extraction")
        update_path = paths.metric_scores_path("halumem_update")
        missing = [
            path.name for path in (extraction_path, update_path) if not path.is_file()
        ]
        if missing:
            raise ConfigurationError(
                "halumem-memory-type requires prior halumem-extraction and "
                "halumem-update evaluation artifacts; missing: " + ", ".join(missing)
            )

        extraction_records = [
            record
            for record in read_jsonl(extraction_path)
            if record.get("record_kind") == "memory_integrity"
        ]
        update_records = [
            record
            for record in read_jsonl(update_path)
            if record.get("record_kind") == "memory_update"
        ]
        breakdown = _memory_type_accuracy(extraction_records, update_records)
        return {
            "metric_name": self.metric_name,
            "score_records": breakdown,
            "total_questions": len(breakdown),
            "mean_score": _mean_available(breakdown),
            "correct_count": None,
            "summary": {
                "overall_score": {"memory_type_accuracy": breakdown},
                "category_breakdown": breakdown,
                "denominator_scope": "official_shared_integrity_plus_update",
                "official_source": self.official_source,
            },
        }


def _memory_type_accuracy(
    integrity_records: list[dict[str, Any]],
    update_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """复刻 `evaluation.py:364-383` 的共享 total_num 公式。"""

    grouped: dict[str, dict[str, int]] = {}
    for record in integrity_records:
        if "memory_integrity_score" not in record or "importance" not in record:
            continue
        memory_type = record.get("memory_type")
        if memory_type is None:
            continue
        bucket = grouped.setdefault(
            str(memory_type), {"integrity_correct": 0, "update_correct": 0, "total": 0}
        )
        bucket["integrity_correct"] += record.get("memory_integrity_score") == 2
        bucket["total"] += 1
    for record in update_records:
        if "memory_update_type" not in record or "importance" not in record:
            continue
        memory_type = record.get("memory_type")
        if memory_type is None:
            continue
        bucket = grouped.setdefault(
            str(memory_type), {"integrity_correct": 0, "update_correct": 0, "total": 0}
        )
        bucket["update_correct"] += record.get("memory_update_type") == "Correct"
        bucket["total"] += 1

    result: list[dict[str, Any]] = []
    for memory_type, counts in sorted(grouped.items()):
        integrity_acc = safe_div(counts["integrity_correct"], counts["total"])
        update_acc = safe_div(counts["update_correct"], counts["total"])
        result.append(
            {
                "category": memory_type,
                "metric_name": "halumem_memory_type",
                "score": (
                    integrity_acc + update_acc
                    if integrity_acc is not None and update_acc is not None
                    else None
                ),
                "memory_integrity_acc": integrity_acc,
                "memory_update_acc": update_acc,
                "memory_acc": (
                    integrity_acc + update_acc
                    if integrity_acc is not None and update_acc is not None
                    else None
                ),
                "integrity_correct_num": counts["integrity_correct"],
                "update_correct_num": counts["update_correct"],
                "total_num": counts["total"],
            }
        )
    return result


def _mean_available(records: list[dict[str, Any]]) -> float:
    """计算可用 memory_acc 均值；空维度仅用 runner 兼容值 0。"""

    scores = [record["memory_acc"] for record in records if record["memory_acc"] is not None]
    return sum(scores) / len(scores) if scores else 0.0

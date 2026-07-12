"""MemBench First/Third × High/Low 论文四格准确率合成指标。"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.storage import ExperimentPaths, read_jsonl


SOURCE_CELLS = ("first-high", "first-low", "third-high", "third-low")


class MemBenchSourceAccuracyEvaluator:
    """从真实 membench choice score 的 conversation_id 聚合来源四格。"""

    metric_name = "membench_source_accuracy"

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """读取上游 choice-accuracy artifact 并输出固定顺序四格及总计。"""

        del manifest, max_workers
        upstream = paths.metric_scores_path("membench_choice_accuracy")
        if not upstream.is_file():
            raise ConfigurationError(
                "membench-source-accuracy requires prior membench-choice-accuracy "
                f"evaluation artifact; missing: {upstream.name}"
            )
        records = read_jsonl(upstream)
        grouped: dict[str, list[dict[str, Any]]] = {cell: [] for cell in SOURCE_CELLS}
        for record in records:
            conversation_id = record.get("conversation_id")
            if not isinstance(conversation_id, str) or not conversation_id:
                raise ConfigurationError(
                    "membench choice score record requires conversation_id"
                )
            cell = "-".join(conversation_id.split("-", 2)[:2])
            if cell not in grouped:
                raise ConfigurationError(
                    "unknown MemBench source prefix in conversation_id: "
                    f"{conversation_id}"
                )
            grouped[cell].append(record)

        breakdown = [_cell_record(cell, grouped[cell]) for cell in SOURCE_CELLS]
        total = _cell_record("total", records)
        score_records = [*breakdown, total]
        return {
            "metric_name": self.metric_name,
            "score_records": score_records,
            "total_questions": len(records),
            "mean_score": float(total["accuracy"] or 0.0),
            "correct_count": total["correct_count"],
            "summary": {
                "source_breakdown": score_records,
                "source_total": total,
                "source_cell_order": list(SOURCE_CELLS),
                "upstream_metric": "membench_choice_accuracy",
                "official_source": "benchmark_adapters/membench.py:797-832",
            },
        }


def _cell_record(cell: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """聚合单个来源格；空格 accuracy 明确为 None。"""

    correct = sum(bool(record.get("is_correct")) for record in records)
    count = len(records)
    return {
        "cell": cell,
        "metric_name": MemBenchSourceAccuracyEvaluator.metric_name,
        "score": correct / count if count else None,
        "question_count": count,
        "correct_count": correct,
        "accuracy": correct / count if count else None,
    }


__all__ = ["MemBenchSourceAccuracyEvaluator"]

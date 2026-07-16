"""BEAM turn-provenance 条件式 retrieval recall（artifact-only）。

权威 qrel 是 gold evidence contract v1 的 `evidence_group_sets`（`beam_source_message`
turn view）：每个稳定去重的官方 raw source id 是一个 group，单一 location →
singleton mapped，重复 raw id → multi-child mapped any-of，
unmatched → 分母保留 miss。abstention 与空 group 记 N/A，不做 0 分。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.gold_evidence_groups import (
    group_recall_score,
    parse_evidence_group_sets,
    require_manifest_gold_evidence_contract_v1,
    select_group_set,
)
from memory_benchmark.storage import ExperimentPaths, read_jsonl


class BeamRetrievalRecallEvaluator:
    """使用 evaluator-private 公开 turn-id 映射计算 BEAM recall。"""

    metric_name = "beam_recall"
    official_source = (
        "third_party/benchmarks/BEAM/src/evaluation/compute_metrics.py:339-628; "
        "framework supplementary retrieval metric"
    )

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """从 answer prompt 与私有标签 artifact 计算 recall。"""

        del max_workers
        provenance = _provenance_granularity(manifest)
        if provenance in {"none", "undeclared"}:
            return _na_payload(provenance)
        require_manifest_gold_evidence_contract_v1(manifest)
        if provenance != "turn":
            raise ConfigurationError(
                f"Unknown provenance_granularity {provenance!r} for BEAM recall; "
                "expected 'none' or 'turn'"
            )

        answers = read_jsonl(paths.answer_prompts_path)
        private = read_jsonl(paths.evaluator_private_labels_path)
        public = read_jsonl(paths.public_questions_path)
        _validate_question_ids(answers, private, public)
        private_by_id = {str(row["question_id"]): row for row in private}
        category_by_id = {str(row["question_id"]): row.get("category") for row in public}

        score_records: list[dict[str, Any]] = []
        scored: list[dict[str, Any]] = []
        top_ks: list[int] = []
        abstention_count = 0
        unmatched_gold_total = 0
        ambiguous_gold_total = 0

        for answer in answers:
            question_id = str(answer["question_id"])
            groups = select_group_set(
                parse_evidence_group_sets(private_by_id[question_id], question_id),
                provenance_granularity="turn",
                unit_kind="beam_source_message",
                question_id=question_id,
            ).groups

            # 兼容旧 metadata 字段，仅作审计披露，不参与权威 qrel。
            metadata = private_by_id[question_id].get("metadata")
            unmatched_count = 0
            ambiguous_count = 0
            if isinstance(metadata, dict):
                unmatched_count = _non_negative_int(
                    metadata, "unmatched_gold_id_count", question_id
                )
                ambiguous_count = _non_negative_int(
                    metadata, "ambiguous_gold_id_count", question_id
                )
            unmatched_gold_total += unmatched_count
            ambiguous_gold_total += ambiguous_count

            if not groups:
                abstention_count += 1
                score_records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "BEAM question has no matchable gold evidence",
                        "category": category_by_id[question_id],
                        "details": {
                            "unmatched_gold_id_count": unmatched_count,
                            "ambiguous_gold_id_count": ambiguous_count,
                        },
                    }
                )
                continue

            top_k, items = _retrieval_fields(answer)
            source_ids = {
                str(source_id)
                for item in items[:top_k]
                for source_id in item["source_turn_ids"]
            }
            score = group_recall_score(groups, source_ids)

            record = {
                "question_id": question_id,
                "conversation_id": answer.get("conversation_id"),
                "metric_name": self.metric_name,
                "score": score,
                "status": "ok",
                "category": category_by_id[question_id],
                "requested_top_k": top_k,
                "details": {
                    "gold_unit_ids": [group.unit_id for group in groups],
                    "unmatched_gold_unit_count": sum(
                        1 for group in groups if group.mapping_status == "unmatched"
                    ),
                    "ambiguous_gold_unit_count": sum(
                        1
                        for group in groups
                        if group.mapping_status == "mapped"
                        and len(group.child_ids) > 1
                    ),
                    "retrieved_source_turn_ids": sorted(source_ids),
                    "framework_supplementary": True,
                },
            }
            score_records.append(record)
            scored.append(record)
            top_ks.append(top_k)

        scores = [float(row["score"]) for row in scored]
        mean = sum(scores) / len(scores) if scores else 0.0
        return {
            "metric_name": self.metric_name,
            "score_records": score_records,
            "total_questions": len(scored),
            "mean_score": mean,
            "correct_count": None,
            "summary": {
                "status": "ok" if scored else "n/a",
                "provenance_granularity": provenance,
                "scored_question_count": len(scored),
                "abstention_question_count": abstention_count,
                "unmatched_gold_id_count": unmatched_gold_total,
                "ambiguous_gold_id_count": ambiguous_gold_total,
                "requested_top_k_distribution": dict(Counter(top_ks)),
                "overall_mean_recall_at_requested_k": mean,
                "framework_supplementary": True,
            },
        }


def _provenance_granularity(manifest: dict[str, Any]) -> str:
    """读取 method provenance 声明。"""

    method = manifest.get("method")
    if not isinstance(method, dict) or method.get("provenance_granularity") is None:
        return "undeclared"
    return str(method["provenance_granularity"])


def _validate_question_ids(*groups: list[dict[str, Any]]) -> None:
    """校验三类 artifact 的 question id 集合严格一致。"""

    ids = [[row.get("question_id") for row in group] for group in groups]
    if any(len(group) != len(set(group)) for group in ids) or not (
        set(ids[0]) == set(ids[1]) == set(ids[2])
    ):
        raise ConfigurationError(
            "BEAM recall artifact question IDs must match exactly across answer "
            "prompts, private labels and public questions"
        )


def _string_list(metadata: dict[str, Any], key: str, question_id: str) -> list[str]:
    """读取私有 metadata 中必需的字符串列表。"""

    value = metadata.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(
            f"question {question_id}: private label metadata requires {key} list"
        )
    return value


def _non_negative_int(metadata: dict[str, Any], key: str, question_id: str) -> int:
    """读取 adapter 记录的非负计数。"""

    value = metadata.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(
            f"question {question_id}: private label metadata {key} must be non-negative int"
        )
    return value


def _retrieval_fields(answer: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """校验已声明 provenance 时的 retrieval artifact。"""

    question_id = answer.get("question_id")
    top_k = answer.get("retrieval_query_top_k")
    items = answer.get("retrieved_items")
    if not isinstance(top_k, int) or top_k < 1:
        raise ConfigurationError(f"question {question_id}: invalid retrieval_query_top_k")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ConfigurationError(f"question {question_id}: retrieved_items is missing")
    for item in items[:top_k]:
        source_ids = item.get("source_turn_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ConfigurationError(
                f"question {question_id}: retrieved item source_turn_ids is missing or empty"
            )
    return top_k, items


def _na_payload(provenance: str) -> dict[str, Any]:
    """构造 provider 无 provenance 时的结构化 N/A。"""

    return {
        "metric_name": "beam_recall",
        "score_records": [],
        "total_questions": 0,
        "mean_score": 0.0,
        "correct_count": None,
        "summary": {
            "status": "n/a",
            "reason": "provider provenance is unavailable",
            "provenance_granularity": provenance,
        },
    }


__all__ = ["BeamRetrievalRecallEvaluator"]

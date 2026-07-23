"""BEAM turn-provenance 条件式 retrieval recall（artifact-only）。

权威 qrel 是 gold evidence contract v1 的 `evidence_group_sets`（`beam_source_message`
turn view）：每个稳定去重的官方 raw source id 是一个 group，单一 location →
singleton mapped，重复 raw id → multi-child mapped any-of，
unmatched → 分母保留 miss。abstention 与空 group 记 N/A，不做 0 分。

RetrievalEvidence M1 起，BEAM 只接受 turn 粒度 gold view。逐题
`retrieval_evidence` 经 `evaluators.retrieval_evidence` 严格 preflight 与
`decide_retrieval_eligibility` 裁决：非 turn 粒度（如 session）统一落在共享的
`gold_granularity_mismatch` N/A 分支，与 MemBench 共用同一条通用规则；
provider 侧 n_a/pending 产生独立的逐题 record，与官方 abstention（空 gold）
分开计数。
"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.gold_evidence_groups import (
    parse_evidence_group_sets,
    select_group_set,
)
from memory_benchmark.evaluators.retrieval_evidence import validated_retrieval_fields
from memory_benchmark.metrics.retrieval import recall_at_k
from memory_benchmark.storage import ExperimentPaths

from .common.artifact import load_retrieval_artifacts
from .common.retrieval import (
    RetrievalEvaluationState,
    build_retrieval_decisions,
)

_ALLOWED_GRANULARITIES = frozenset({"turn"})


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
        artifacts = load_retrieval_artifacts(
            paths=paths,
            manifest=manifest,
            mismatch_error=(
                "BEAM recall artifact question IDs must match exactly across answer "
                "prompts, private labels and public questions"
            ),
        )
        decisions_by_id = build_retrieval_decisions(
            artifacts.answer_records,
            allowed_granularities=_ALLOWED_GRANULARITIES,
            requires_stable_ranking=False,
        )
        state = RetrievalEvaluationState()
        abstention_count = 0
        unmatched_gold_total = 0
        ambiguous_gold_total = 0

        for answer in artifacts.answer_records:
            question_id = str(answer["question_id"])
            groups = select_group_set(
                parse_evidence_group_sets(
                    artifacts.private_by_id[question_id], question_id
                ),
                provenance_granularity="turn",
                unit_kind="beam_source_message",
                question_id=question_id,
            ).groups

            # 兼容旧 metadata 字段，仅作审计披露，不参与权威 qrel。
            metadata = artifacts.private_by_id[question_id].get("metadata")
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
                state.add_benchmark_exclusion(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "BEAM question has no matchable gold evidence",
                        "exclusion_source": "benchmark_policy",
                        "category": artifacts.category_by_id[question_id],
                        "provenance_granularity": "turn",
                        "details": {
                            "unmatched_gold_id_count": unmatched_count,
                            "ambiguous_gold_id_count": ambiguous_count,
                        },
                    }
                )
                continue

            decision = decisions_by_id[question_id]
            if decision.status != "valid":
                state.add_ineligible(
                    answer_record=answer,
                    metric_name=self.metric_name,
                    category=artifacts.category_by_id[question_id],
                    decision=decision,
                )
                continue

            top_k, items = validated_retrieval_fields(answer, question_id)
            recall_result = recall_at_k(groups, items, top_k)
            score = recall_result.score

            record = {
                "question_id": question_id,
                "conversation_id": answer.get("conversation_id"),
                "metric_name": self.metric_name,
                "score": score,
                "status": "ok",
                "retrieval_evidence_status": "valid",
                "category": artifacts.category_by_id[question_id],
                "requested_top_k": top_k,
                "provenance_granularity": "turn",
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
                    "retrieved_source_turn_ids": sorted(recall_result.source_ids),
                    "framework_supplementary": True,
                },
            }
            state.add_scored(record=record, decision=decision, top_k=top_k)

        payload = state.build_payload(
            metric_name=self.metric_name,
            include_by_category=False,
            summary_fields={
                "abstention_question_count": abstention_count,
                "unmatched_gold_id_count": unmatched_gold_total,
                "ambiguous_gold_id_count": ambiguous_gold_total,
                "overall_mean_recall_at_requested_k": None,
                "framework_supplementary": True,
            },
        )
        payload["summary"]["overall_mean_recall_at_requested_k"] = payload["mean_score"]
        return payload


def _non_negative_int(metadata: dict[str, Any], key: str, question_id: str) -> int:
    """读取 adapter 记录的非负计数。"""

    value = metadata.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(
            f"question {question_id}: private label metadata {key} must be non-negative int"
        )
    return value


__all__ = ["BeamRetrievalRecallEvaluator"]

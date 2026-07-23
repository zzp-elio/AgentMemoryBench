"""MemBench 条件式 retrieval recall（artifact-only，离线）。

匹配键统一在公开 turn-id 空间（1 基），官方 0 基 `target_step_id` 仅作
metadata 留档。权威 qrel 是 gold evidence contract v1 的 `evidence_group_sets`
（`membench_step` turn view）：每个去重 step 一个 group，越界 target 记
unmatched，空 target 记 N/A（不再错误记 1.0）。

RetrievalEvidence M1 起，MemBench 只接受 turn 粒度 gold view。逐题
`retrieval_evidence` 经 `evaluators.retrieval_evidence` 严格 preflight 与
`decide_retrieval_eligibility` 裁决：`session` 粒度（MemBench 单 session，
没有可召回的 session 结构）与其余非 turn 粒度统一落在共享的
`gold_granularity_mismatch` N/A 分支，不再由本 evaluator 手写专用判断；
provider 侧 n_a/pending 同样产生独立的逐题 record。
"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core import GoldEvidenceGroup
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


class MemBenchRetrievalRecallEvaluator:
    """按 provider 逐题声明的 retrieval evidence 计算 MemBench 条件式 recall。"""

    metric_name = "membench_recall"
    official_source = (
        "third_party/benchmarks/Membench-main/benchmark/load_test_data.py:57,"
        "MembenchAgent.py:46-92"
    )

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """从 manifest、answer prompt 与 evaluator-private labels 计算 recall。"""

        del max_workers
        artifacts = load_retrieval_artifacts(
            paths=paths,
            manifest=manifest,
            mismatch_error=(
                "MemBench recall artifact question IDs must match exactly across "
                "answer prompts, private labels and public questions"
            ),
        )
        decisions_by_id = build_retrieval_decisions(
            artifacts.answer_records,
            allowed_granularities=_ALLOWED_GRANULARITIES,
            requires_stable_ranking=False,
        )
        state = RetrievalEvaluationState()
        empty_gold_count = 0
        unmatched_gold_total = 0
        out_of_bounds_gold_total = 0

        for answer_record in artifacts.answer_records:
            question_id = str(answer_record["question_id"])
            category = artifacts.category_by_id.get(question_id)
            groups = select_group_set(
                parse_evidence_group_sets(
                    artifacts.private_by_id[question_id], question_id
                ),
                provenance_granularity="turn",
                unit_kind="membench_step",
                question_id=question_id,
            ).groups

            # 权威越界诊断：unmatched group 的 unit_id 就是越界的官方 0 基
            # step id，直接来自 gold group 本身，不再依赖 answer artifact 的
            # public_turn_count 启发式（拆分后 canonical turn 数已不等于源
            # step 数，该字段既不可靠也未被生产 answer prompt 写入）。
            oob_ids = _out_of_bounds_target_step_ids(groups)
            out_of_bounds_gold_total += len(oob_ids)

            if not groups:
                empty_gold_count += 1
                state.add_benchmark_exclusion(
                    {
                        "question_id": question_id,
                        "conversation_id": answer_record.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "MemBench question has no matchable gold evidence",
                        "exclusion_source": "benchmark_policy",
                        "category": category,
                        "provenance_granularity": "turn",
                        "details": {
                            "out_of_bounds_target_step_ids": oob_ids,
                            "official_source": self.official_source,
                        },
                    }
                )
                continue

            decision = decisions_by_id[question_id]
            if decision.status != "valid":
                state.add_ineligible(
                    answer_record=answer_record,
                    metric_name=self.metric_name,
                    category=category,
                    decision=decision,
                )
                continue

            top_k, retrieved_items = validated_retrieval_fields(
                answer_record, question_id
            )
            recall_result = recall_at_k(groups, retrieved_items, top_k)
            score = recall_result.score
            unmatched_count = sum(
                1 for group in groups if group.mapping_status == "unmatched"
            )
            unmatched_gold_total += unmatched_count
            record = {
                "question_id": question_id,
                "conversation_id": answer_record.get("conversation_id"),
                "metric_name": self.metric_name,
                "score": score,
                "status": "ok",
                "retrieval_evidence_status": "valid",
                "category": category,
                "requested_top_k": top_k,
                "provenance_granularity": "turn",
                "details": {
                    "gold_unit_ids": [group.unit_id for group in groups],
                    "unmatched_gold_unit_count": unmatched_count,
                    "out_of_bounds_target_step_ids": oob_ids,
                    "retrieved_source_turn_ids": sorted(recall_result.source_ids),
                    "official_source": self.official_source,
                },
            }
            state.add_scored(record=record, decision=decision, top_k=top_k)

        payload = state.build_payload(
            metric_name=self.metric_name,
            include_by_category=True,
            summary_fields={
                "empty_gold_question_count": empty_gold_count,
                "unmatched_gold_total": unmatched_gold_total,
                "out_of_bounds_gold_total": out_of_bounds_gold_total,
                "overall_mean_recall_at_requested_k": None,
                "official_source": self.official_source,
            },
        )
        payload["summary"]["overall_mean_recall_at_requested_k"] = payload["mean_score"]
        return payload


def _out_of_bounds_target_step_ids(
    groups: tuple[GoldEvidenceGroup, ...],
) -> list[int]:
    """从权威 unmatched group 还原越界的官方 0 基 target_step_id。

    一个 `membench_step` group 的 `unit_id` 就是官方 0 基 step id；
    `mapping_status == "unmatched"` 精确表示该 step id 越界（或映射失败），
    与旧的 `public_turn_count` 启发式无关——拆分后 canonical turn 数已不再等于
    源 step 数，该字段也从未被生产 answer prompt 写入。mapped 的 multi-child
    group（FirstAgent pair-step）绝不会出现在这里，不会被误报越界。
    """

    return [
        int(group.unit_id) for group in groups if group.mapping_status == "unmatched"
    ]


__all__ = ["MemBenchRetrievalRecallEvaluator"]

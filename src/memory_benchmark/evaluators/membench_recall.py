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

from collections import Counter
from typing import Any

from memory_benchmark.core import ConfigurationError, GoldEvidenceGroup
from memory_benchmark.evaluators.gold_evidence_groups import (
    parse_evidence_group_sets,
    require_manifest_gold_evidence_contract_v1,
    select_group_set,
)
from memory_benchmark.evaluators.retrieval_evidence import (
    AGGREGATION_CONTRACT_VERSION,
    RetrievalEligibilityDecision,
    decide_retrieval_eligibility,
    display_status,
    nullable_mean,
    parse_retrieval_evidence,
    require_manifest_retrieval_evidence_contract_v1,
    score_status_counts,
    summary_provenance_granularity,
    summary_status,
    validated_retrieval_fields,
)
from memory_benchmark.evaluators.retrieval_metrics import recall_at_k
from memory_benchmark.storage import ExperimentPaths, read_jsonl

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
        require_manifest_gold_evidence_contract_v1(manifest)
        require_manifest_retrieval_evidence_contract_v1(manifest)

        answer_records = read_jsonl(paths.answer_prompts_path)
        private_records = read_jsonl(paths.evaluator_private_labels_path)
        public_records = read_jsonl(paths.public_questions_path)
        _validate_matching_question_ids(answer_records, private_records, public_records)
        private_by_id = {record["question_id"]: record for record in private_records}
        category_by_id = {
            record["question_id"]: record.get("category") for record in public_records
        }

        decisions_by_id = _decisions_by_question_id(answer_records)

        score_records: list[dict[str, Any]] = []
        scored_records: list[dict[str, Any]] = []
        top_k_values: list[int] = []
        empty_gold_count = 0
        unmatched_gold_total = 0
        out_of_bounds_gold_total = 0
        evidence_status_counts: Counter[str] = Counter()
        evidence_reason_code_counts: Counter[str] = Counter()
        scored_decisions: list[RetrievalEligibilityDecision] = []

        for answer_record in answer_records:
            question_id = str(answer_record["question_id"])
            category = category_by_id.get(question_id)
            groups = select_group_set(
                parse_evidence_group_sets(
                    private_by_id[question_id], question_id
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
                score_records.append(
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
            evidence_status_counts[decision.status] += 1
            if decision.status != "valid":
                evidence_reason_code_counts[decision.reason_code] += 1
                score_records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer_record.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": display_status(decision.status),
                        "retrieval_evidence_status": decision.status,
                        "reason_code": decision.reason_code,
                        "reason": decision.reason,
                        "category": category,
                        "provenance_granularity": decision.provenance_granularity,
                    }
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
            top_k_values.append(top_k)
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
            score_records.append(record)
            scored_records.append(record)
            scored_decisions.append(decision)

        return _scored_payload(
            metric_name=self.metric_name,
            score_records=score_records,
            scored_records=scored_records,
            top_k_values=top_k_values,
            empty_gold_count=empty_gold_count,
            unmatched_gold_total=unmatched_gold_total,
            out_of_bounds_gold_total=out_of_bounds_gold_total,
            evidence_status_counts=evidence_status_counts,
            evidence_reason_code_counts=evidence_reason_code_counts,
            scored_decisions=scored_decisions,
            official_source=self.official_source,
        )


def _decisions_by_question_id(
    answer_records: list[dict[str, Any]],
) -> dict[str, RetrievalEligibilityDecision]:
    """对全部 answer records 做逐题 retrieval evidence preflight + 资格裁决。

    MemBench 只接受 turn 粒度；session 与其余粒度统一由共享裁决导出
    `gold_granularity_mismatch` N/A，不再手写专用判断。
    """

    decisions: dict[str, RetrievalEligibilityDecision] = {}
    for record in answer_records:
        question_id = str(record["question_id"])
        evidence = parse_retrieval_evidence(record.get("retrieval_evidence"), question_id)
        decisions[question_id] = decide_retrieval_eligibility(
            evidence,
            allowed_granularities=_ALLOWED_GRANULARITIES,
            requires_stable_ranking=False,
        )
    return decisions


def _validate_matching_question_ids(
    answer_records: list[dict[str, Any]],
    private_records: list[dict[str, Any]],
    public_records: list[dict[str, Any]],
) -> None:
    """校验三类 artifact 的 question id 必须唯一且集合完全一致。"""

    id_lists = [
        [record.get("question_id") for record in records]
        for records in (answer_records, private_records, public_records)
    ]
    if any(len(ids) != len(set(ids)) for ids in id_lists) or not (
        set(id_lists[0]) == set(id_lists[1]) == set(id_lists[2])
    ):
        raise ConfigurationError(
            "MemBench recall artifact question IDs must match exactly across "
            "answer prompts, private labels and public questions"
        )


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


def _scored_payload(
    *,
    metric_name: str,
    score_records: list[dict[str, Any]],
    scored_records: list[dict[str, Any]],
    top_k_values: list[int],
    empty_gold_count: int,
    unmatched_gold_total: int,
    out_of_bounds_gold_total: int,
    evidence_status_counts: Counter[str],
    evidence_reason_code_counts: Counter[str],
    scored_decisions: list[RetrievalEligibilityDecision],
    official_source: str,
) -> dict[str, Any]:
    """聚合已评分问题，按 question_type 输出分类聚合。"""

    scores = [float(record["score"]) for record in scored_records]
    mean_score = nullable_mean(scores)
    by_category: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[float]] = {}
    for record in scored_records:
        category = record.get("category")
        key = "unknown" if category is None else str(category)
        grouped.setdefault(key, []).append(float(record["score"]))
    for category, category_scores in sorted(grouped.items()):
        by_category[category] = {
            "scored_count": len(category_scores),
            "mean_score": sum(category_scores) / len(category_scores),
        }
    pending_count = evidence_status_counts.get("pending", 0)
    return {
        "metric_name": metric_name,
        "score_records": score_records,
        "total_questions": len(score_records),
        "mean_score": mean_score,
        "correct_count": None,
        "summary": {
            "status": summary_status(scored_count=len(scored_records), pending_count=pending_count),
            "provenance_granularity": summary_provenance_granularity(scored_decisions),
            "scored_question_count": len(scored_records),
            "empty_gold_question_count": empty_gold_count,
            "unmatched_gold_total": unmatched_gold_total,
            "out_of_bounds_gold_total": out_of_bounds_gold_total,
            "overall_mean_recall_at_requested_k": mean_score,
            "by_category": by_category,
            "requested_top_k_distribution": dict(Counter(top_k_values)),
            "retrieval_evidence_status_counts": dict(evidence_status_counts),
            "retrieval_evidence_reason_code_counts": dict(evidence_reason_code_counts),
            "score_status_counts": score_status_counts(score_records),
            "aggregation_contract_version": AGGREGATION_CONTRACT_VERSION,
            "metric_tier": "framework_supplementary",
            "official_source": official_source,
        },
    }


__all__ = ["MemBenchRetrievalRecallEvaluator"]

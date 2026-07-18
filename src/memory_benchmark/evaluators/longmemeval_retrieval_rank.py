"""LongMemEval 官方检索排名指标的 artifact-only 实现。

权威 qrel 是 gold evidence contract v1 的 `evidence_group_sets`；一个 group 的
rank 是其任一 child 首次出现的最小 rank，同 group 多 child 与同 child 重复命中
都只计一次；unmatched group 留在 ideal gold 数中但永远不命中。`_abs` 与官方
no-target 题（turn 主路径 canonical 分母 419）都记 N/A 不评分。

RetrievalEvidence M1 起，rank/NDCG 在 Recall 的 semantic provenance + gold
granularity 门之上，还要求逐题 `stable_ranking=valid`：`RetrievedItem` 列表
必须确实是 method 实际检索名次，未被 set 化或展示层二次重排，否则 DCG 折损
没有意义。stable_ranking 非 valid 时该题原样传播 n_a/pending，不产 metrics、
不进任何 k 的分母——当前三家真实 provider 的 stable_ranking 都恒为
`pending`，因此真实 run 的 rank 题应诚实输出 pending。本模块不改
`RetrievalQuery.top_k=10`，只按已声明的 query depth 报告可用 k，30/50 显式
标记为 unavailable（`evaluation_depth_not_requested`），不把物理多存的
items 或缺失名次当作官方 k=30/50 结果。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from math import log2
from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.entities import GoldEvidenceGroup
from memory_benchmark.storage import ExperimentPaths, read_jsonl

from .gold_evidence_groups import (
    group_first_hit_rank,
    parse_evidence_group_sets,
    require_manifest_gold_evidence_contract_v1,
    select_group_set,
)
from .retrieval_evidence import (
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


OFFICIAL_K = (1, 3, 5, 10, 30, 50)
_ALLOWED_GRANULARITIES = frozenset({"turn", "session"})
_EVALUATION_DEPTH_NOT_REQUESTED = "evaluation_depth_not_requested"


class LongMemEvalRetrievalRankEvaluator:
    """按公开 provenance id 计算官方 recall_any/all 与 NDCG。"""

    metric_name = "longmemeval_retrieval_rank"

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """读取 answer prompt 与 evaluator-private gold 并聚合排名指标。"""

        del max_workers
        require_manifest_gold_evidence_contract_v1(manifest)
        require_manifest_retrieval_evidence_contract_v1(manifest)

        answers = read_jsonl(paths.answer_prompts_path)
        private = read_jsonl(paths.evaluator_private_labels_path)
        public = read_jsonl(paths.public_questions_path)
        _validate_question_ids(answers, private, public)
        private_by_id = {record["question_id"]: record for record in private}
        category_by_id = {
            record["question_id"]: record.get("category") for record in public
        }

        decisions_by_id = _decisions_by_question_id(answers)

        records: list[dict[str, Any]] = []
        participating: dict[int, list[dict[str, float]]] = defaultdict(list)
        skipped_k: set[int] = set()
        skipped_k_count = 0
        abstention_count = 0
        no_target_count = 0
        evidence_status_counts: Counter[str] = Counter()
        evidence_reason_code_counts: Counter[str] = Counter()
        scored_decisions: list[RetrievalEligibilityDecision] = []

        for answer in answers:
            question_id = str(answer["question_id"])
            if "_abs" in question_id:
                # abstention 是官方 benchmark policy 剔除，与 evidence 内容/
                # stable ranking 无关；不计入 retrieval evidence status 统计。
                abstention_count += 1
                records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "exclusion_source": "benchmark_policy",
                        "abstention": True,
                        "category": category_by_id.get(question_id),
                    }
                )
                continue

            group_sets = parse_evidence_group_sets(
                private_by_id[question_id], question_id
            )
            canonical_turn_groups = select_group_set(
                group_sets,
                provenance_granularity="turn",
                unit_kind="longmemeval_user_target_turn",
                question_id=question_id,
            ).groups
            if not canonical_turn_groups:
                no_target_count += 1
                records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "official_no_target",
                        "exclusion_source": "benchmark_policy",
                        "abstention": False,
                        "category": category_by_id.get(question_id),
                    }
                )
                continue

            decision = decisions_by_id[question_id]
            evidence_status_counts[decision.status] += 1

            if decision.status != "valid":
                evidence_reason_code_counts[decision.reason_code] += 1
                records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": display_status(decision.status),
                        "retrieval_evidence_status": decision.status,
                        "reason_code": decision.reason_code,
                        "reason": decision.reason,
                        "abstention": False,
                        "category": category_by_id.get(question_id),
                    }
                )
                continue

            granularity = decision.provenance_granularity
            groups = canonical_turn_groups
            if granularity == "session":
                groups = select_group_set(
                    group_sets,
                    provenance_granularity="session",
                    unit_kind="longmemeval_answer_session",
                    question_id=question_id,
                ).groups
                if not groups:
                    raise ConfigurationError(
                        f"question {question_id}: canonical turn gold has targets but "
                        "the provider-required session gold view is empty"
                    )

            top_k, items = validated_retrieval_fields(answer, question_id)
            ranked_ids = _ranked_source_ids(items, top_k, granularity)

            metrics: dict[str, float] = {}
            available_k = [k for k in OFFICIAL_K if k <= top_k]
            unavailable_k = [k for k in OFFICIAL_K if k > top_k]
            skipped_k.update(unavailable_k)
            skipped_k_count += len(unavailable_k)
            for k in available_k:
                values = _evaluate_groups_at_k(ranked_ids, groups, k)
                metrics.update(values)
                participating[k].append(values)
            records.append(
                {
                    "question_id": question_id,
                    "conversation_id": answer.get("conversation_id"),
                    "metric_name": self.metric_name,
                    "score": metrics.get(f"ndcg_any@{max(available_k)}") if available_k else None,
                    "status": "ok",
                    "retrieval_evidence_status": "valid",
                    "abstention": False,
                    "category": category_by_id.get(question_id),
                    "retrieval_query_top_k": top_k,
                    "provenance_granularity": granularity,
                    "metrics": metrics,
                }
            )
            scored_decisions.append(decision)

        means = {
            metric: sum(row[metric] for row in rows) / len(rows)
            for k, rows in sorted(participating.items())
            for metric in (f"recall_any@{k}", f"recall_all@{k}", f"ndcg_any@{k}")
        }
        scored = [record for record in records if record["score"] is not None]
        pending_count = evidence_status_counts.get("pending", 0)
        return {
            "metric_name": self.metric_name,
            "score_records": records,
            "total_questions": len(records),
            "mean_score": nullable_mean([float(record["score"]) for record in scored]),
            "correct_count": None,
            "summary": {
                "status": summary_status(scored_count=len(scored), pending_count=pending_count),
                "provenance_granularity": summary_provenance_granularity(
                    scored_decisions
                ),
                "scored_question_count": len(scored),
                "overall_metrics": means,
                "participating_question_count_by_k": {
                    str(k): len(rows) for k, rows in sorted(participating.items())
                },
                "abstention_excluded_count": abstention_count,
                "official_no_target_question_count": no_target_count,
                "skipped_k_above_top_k": sorted(skipped_k),
                "skipped_k_above_top_k_count": skipped_k_count,
                "skipped_k_above_top_k_reason_code": _EVALUATION_DEPTH_NOT_REQUESTED,
                "turn2session_view": "not_artifact_computable",
                "group_rank_semantics": (
                    "group rank = min(first-appearance rank of any child); "
                    "same-group multi-child or repeated child only counts once; "
                    "unmatched groups stay in ideal gold count but never hit"
                ),
                "retrieval_evidence_status_counts": dict(evidence_status_counts),
                "retrieval_evidence_reason_code_counts": dict(evidence_reason_code_counts),
                "score_status_counts": score_status_counts(records),
                "aggregation_contract_version": AGGREGATION_CONTRACT_VERSION,
                "metric_tier": "framework_supplementary",
                "formula_parity_at_available_k": True,
                "official_sources": {
                    "formula": "src/retrieval/eval_utils.py:4-29",
                    "k_and_names": "src/retrieval/run_retrieval.py:316-321",
                    "abstention": "src/retrieval/run_retrieval.py:389-408",
                },
            },
        }


def _decisions_by_question_id(
    answers: list[dict[str, Any]],
) -> dict[str, RetrievalEligibilityDecision]:
    """对全部 answer records 做逐题 retrieval evidence preflight + 资格裁决。

    rank 在 recall 语义之上还要求 `stable_ranking=valid`；在进入 `_abs`/
    no-target 等 benchmark-specific 排除或计分循环前对**全部**记录解析。
    """

    decisions: dict[str, RetrievalEligibilityDecision] = {}
    for record in answers:
        question_id = str(record["question_id"])
        evidence = parse_retrieval_evidence(record.get("retrieval_evidence"), question_id)
        decisions[question_id] = decide_retrieval_eligibility(
            evidence,
            allowed_granularities=_ALLOWED_GRANULARITIES,
            requires_stable_ranking=True,
        )
    return decisions


def _evaluate_groups_at_k(
    ranked_ids: list[str],
    groups: tuple[GoldEvidenceGroup, ...],
    k: int,
) -> dict[str, float]:
    """按 gold evidence group any-of 语义计算一个 k 的官方三指标。

    每个 mapped group 的 rank = 其任一 child 首次出现的最小 rank（0 基），
    同 group 多 child 与同 child 重复命中都只计一次；unmatched 留在 ideal gold
    数中但永远不命中，对任何 k 都贡献 recall 0 + NDCG 0。
    """

    window_ids = set(ranked_ids[:k])
    # recall_any：至少一个 group 命中；recall_all：全部 mapped group 命中
    # （unmatched 不算命中，但它已永久扣在分母中）
    any_hit = any(
        group.mapping_status == "mapped"
        and any(child_id in window_ids for child_id in group.child_ids)
        for group in groups
    )
    all_hit = all(
        group.mapping_status == "mapped"
        and any(child_id in window_ids for child_id in group.child_ids)
        for group in groups
    )

    # NDCG：每个 group 的二值相关性由其最优（最小）命中 rank 折损
    actual_hits: list[float] = [0.0] * k
    for group in groups:
        rank = group_first_hit_rank(group, ranked_ids[:k])
        if rank is not None:
            actual_hits[rank] = 1.0
    actual_dcg = _dcg(actual_hits)
    # ideal：每个官方 gold unit 都占理想分母；unmatched 只是永远无法进入 actual，
    # 不能从 ideal gold 数中删除，否则会把映射失败悄悄洗成满分。
    ideal_dcg = _dcg([1.0] * min(len(groups), k))
    ndcg = actual_dcg / ideal_dcg if ideal_dcg else 0.0

    return {
        f"recall_any@{k}": float(any_hit),
        f"recall_all@{k}": float(all_hit),
        f"ndcg_any@{k}": ndcg,
    }


def _dcg(relevances: list[float]) -> float:
    """复刻官方 eval_utils.py:4-9 的 DCG 折损。"""

    if not relevances:
        return 0.0
    return relevances[0] + sum(
        relevance / log2(index)
        for index, relevance in enumerate(relevances[1:], start=2)
    )


def _ranked_source_ids(
    items: list[dict[str, Any]], top_k: int, granularity: str
) -> list[str]:
    """按 retrieved item/source 顺序展开公开 id，并保留首次出现位置。"""

    ranked: list[str] = []
    seen: set[str] = set()
    for item in items[:top_k]:
        for raw_id in item["source_turn_ids"]:
            source_id = str(raw_id)
            if granularity == "session":
                source_id = _public_session_id(source_id)
            if source_id not in seen:
                seen.add(source_id)
                ranked.append(source_id)
    return ranked


def _public_session_id(source_id: str) -> str:
    """把公开 turn id 上卷到公开 session id。"""

    prefix, separator, suffix = source_id.rpartition(":t")
    return prefix if separator and suffix.isdigit() else source_id


def _validate_question_ids(
    answers: list[dict[str, Any]],
    private: list[dict[str, Any]],
    public: list[dict[str, Any]],
) -> None:
    """校验三类 artifact question id 唯一且集合完全一致。"""

    id_lists = [
        [record.get("question_id") for record in records]
        for records in (answers, private, public)
    ]
    if any(len(ids) != len(set(ids)) for ids in id_lists) or not (
        set(id_lists[0]) == set(id_lists[1]) == set(id_lists[2])
    ):
        raise ConfigurationError(
            "LongMemEval retrieval-rank artifact question IDs must match exactly "
            "across answer prompts, private labels and public questions"
        )


__all__ = ["LongMemEvalRetrievalRankEvaluator"]

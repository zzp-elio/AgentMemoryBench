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

from collections import defaultdict
from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.entities import GoldEvidenceGroup
from memory_benchmark.metrics.ranking import (
    discounted_cumulative_gain,
    group_rank_metrics_at_k,
    ranked_source_ids,
)
from memory_benchmark.storage import ExperimentPaths

from .common.artifact import load_retrieval_artifacts
from .common.retrieval import (
    RetrievalEvaluationState,
    build_retrieval_decisions,
)
from .gold_evidence_groups import (
    parse_evidence_group_sets,
    select_group_set,
)
from .retrieval_evidence import validated_retrieval_fields


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
        artifacts = load_retrieval_artifacts(
            paths=paths,
            manifest=manifest,
            mismatch_error=(
                "LongMemEval retrieval-rank artifact question IDs must match exactly "
                "across answer prompts, private labels and public questions"
            ),
        )
        decisions_by_id = build_retrieval_decisions(
            artifacts.answer_records,
            allowed_granularities=_ALLOWED_GRANULARITIES,
            requires_stable_ranking=True,
        )
        state = RetrievalEvaluationState()
        participating: dict[int, list[dict[str, float]]] = defaultdict(list)
        skipped_k: set[int] = set()
        skipped_k_count = 0
        abstention_count = 0
        no_target_count = 0

        for answer in artifacts.answer_records:
            question_id = str(answer["question_id"])
            if "_abs" in question_id:
                # abstention 是官方 benchmark policy 剔除，与 evidence 内容/
                # stable ranking 无关；不计入 retrieval evidence status 统计。
                abstention_count += 1
                state.add_benchmark_exclusion(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "exclusion_source": "benchmark_policy",
                        "abstention": True,
                        "category": artifacts.category_by_id.get(question_id),
                    }
                )
                continue

            group_sets = parse_evidence_group_sets(
                artifacts.private_by_id[question_id], question_id
            )
            canonical_turn_groups = select_group_set(
                group_sets,
                provenance_granularity="turn",
                unit_kind="longmemeval_user_target_turn",
                question_id=question_id,
            ).groups
            if not canonical_turn_groups:
                no_target_count += 1
                state.add_benchmark_exclusion(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "official_no_target",
                        "exclusion_source": "benchmark_policy",
                        "abstention": False,
                        "category": artifacts.category_by_id.get(question_id),
                    }
                )
                continue

            decision = decisions_by_id[question_id]

            if decision.status != "valid":
                state.add_ineligible(
                    answer_record=answer,
                    metric_name=self.metric_name,
                    category=artifacts.category_by_id.get(question_id),
                    decision=decision,
                    extra_fields={"abstention": False},
                    include_provenance_granularity=False,
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
            record = {
                    "question_id": question_id,
                    "conversation_id": answer.get("conversation_id"),
                    "metric_name": self.metric_name,
                    "score": metrics.get(f"ndcg_any@{max(available_k)}") if available_k else None,
                    "status": "ok",
                    "retrieval_evidence_status": "valid",
                    "abstention": False,
                    "category": artifacts.category_by_id.get(question_id),
                    "retrieval_query_top_k": top_k,
                    "provenance_granularity": granularity,
                    "metrics": metrics,
                }
            state.add_scored(record=record, decision=decision, top_k=top_k)

        means = {
            metric: sum(row[metric] for row in rows) / len(rows)
            for k, rows in sorted(participating.items())
            for metric in (f"recall_any@{k}", f"recall_all@{k}", f"ndcg_any@{k}")
        }
        return state.build_payload(
            metric_name=self.metric_name,
            include_by_category=False,
            include_top_k_distribution=False,
            summary_fields={
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
                "formula_parity_at_available_k": True,
                "official_sources": {
                    "formula": "src/retrieval/eval_utils.py:4-29",
                    "k_and_names": "src/retrieval/run_retrieval.py:316-321",
                    "abstention": "src/retrieval/run_retrieval.py:389-408",
                },
            },
        )


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

    return group_rank_metrics_at_k(ranked_ids, groups, k)


def _dcg(relevances: list[float]) -> float:
    """复刻官方 eval_utils.py:4-9 的 DCG 折损。"""

    return discounted_cumulative_gain(relevances)


def _ranked_source_ids(
    items: list[dict[str, Any]], top_k: int, granularity: str
) -> list[str]:
    """按 retrieved item/source 顺序展开公开 id，并保留首次出现位置。"""

    projector = _public_session_id if granularity == "session" else str
    return ranked_source_ids(
        items[:top_k],
        source_id_projector=projector,
    )


def _public_session_id(source_id: str) -> str:
    """把公开 turn id 上卷到公开 session id。"""

    prefix, separator, suffix = source_id.rpartition(":t")
    return prefix if separator and suffix.isdigit() else source_id


__all__ = ["LongMemEvalRetrievalRankEvaluator"]

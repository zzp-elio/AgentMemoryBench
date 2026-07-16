"""LongMemEval 官方检索排名指标的 artifact-only 实现。

权威 qrel 是 gold evidence contract v1 的 `evidence_group_sets`；一个 group 的
rank 是其任一 child 首次出现的最小 rank，同 group 多 child 与同 child 重复命中
都只计一次；unmatched group 留在 ideal gold 数中但永远不命中。`_abs` 与官方
no-target 题（turn 主路径 canonical 分母 419）都记 N/A 不评分。
"""

from __future__ import annotations

from collections import defaultdict
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


OFFICIAL_K = (1, 3, 5, 10, 30, 50)


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
        granularity = _provenance_granularity(manifest)
        if granularity in {"none", "undeclared"}:
            return _na_payload(granularity)
        require_manifest_gold_evidence_contract_v1(manifest)
        if granularity not in {"turn", "session"}:
            raise ConfigurationError(
                f"Unknown provenance_granularity {granularity!r} in manifest['method']; "
                "expected 'none', 'session' or 'turn'"
            )

        answers = read_jsonl(paths.answer_prompts_path)
        private = read_jsonl(paths.evaluator_private_labels_path)
        public = read_jsonl(paths.public_questions_path)
        _validate_question_ids(answers, private, public)
        private_by_id = {record["question_id"]: record for record in private}
        category_by_id = {
            record["question_id"]: record.get("category") for record in public
        }

        records: list[dict[str, Any]] = []
        participating: dict[int, list[dict[str, float]]] = defaultdict(list)
        skipped_k: set[int] = set()
        skipped_k_count = 0
        abstention_count = 0
        no_target_count = 0
        for answer in answers:
            question_id = str(answer["question_id"])
            if "_abs" in question_id:
                abstention_count += 1
                records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "abstention": True,
                        "category": category_by_id.get(question_id),
                    }
                )
                continue

            groups = select_group_set(
                parse_evidence_group_sets(private_by_id[question_id], question_id),
                provenance_granularity=granularity,
                unit_kind=(
                    "longmemeval_user_target_turn"
                    if granularity == "turn"
                    else "longmemeval_answer_session"
                ),
                question_id=question_id,
            ).groups
            if not groups:
                # 官方 run_retrieval.py:389-410 聚合口径：无官方 gold unit 的题
                # 整题剔除，不参与任何 k 的均值。
                no_target_count += 1
                records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "official_no_target",
                        "abstention": False,
                        "category": category_by_id.get(question_id),
                    }
                )
                continue

            top_k, items = _retrieval_fields(answer, granularity)
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
                    "abstention": False,
                    "category": category_by_id.get(question_id),
                    "retrieval_query_top_k": top_k,
                    "provenance_granularity": granularity,
                    "metrics": metrics,
                }
            )

        means = {
            metric: sum(row[metric] for row in rows) / len(rows)
            for k, rows in sorted(participating.items())
            for metric in (f"recall_any@{k}", f"recall_all@{k}", f"ndcg_any@{k}")
        }
        scored = [record for record in records if record["score"] is not None]
        return {
            "metric_name": self.metric_name,
            "score_records": records,
            "total_questions": len(scored),
            "mean_score": (
                sum(float(record["score"]) for record in scored) / len(scored)
                if scored
                else 0.0
            ),
            "correct_count": None,
            "summary": {
                "status": "ok" if scored else "n/a",
                "provenance_granularity": granularity,
                "overall_metrics": means,
                "participating_question_count_by_k": {
                    str(k): len(rows) for k, rows in sorted(participating.items())
                },
                "abstention_excluded_count": abstention_count,
                "official_no_target_question_count": no_target_count,
                "skipped_k_above_top_k": sorted(skipped_k),
                "skipped_k_above_top_k_count": skipped_k_count,
                "turn2session_view": "not_artifact_computable",
                "group_rank_semantics": (
                    "group rank = min(first-appearance rank of any child); "
                    "same-group multi-child or repeated child only counts once; "
                    "unmatched groups stay in ideal gold count but never hit"
                ),
                "official_sources": {
                    "formula": "src/retrieval/eval_utils.py:4-29",
                    "k_and_names": "src/retrieval/run_retrieval.py:316-321",
                    "abstention": "src/retrieval/run_retrieval.py:389-408",
                },
            },
        }


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
    # ideal：全部 mapped group 优先于 unmatched，排在 rank 0,1,2,...
    mapped_count = sum(1 for group in groups if group.mapping_status == "mapped")
    ideal_dcg = _dcg([1.0] * min(mapped_count, k))
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


def _retrieval_fields(
    record: dict[str, Any], granularity: str
) -> tuple[int, list[dict[str, Any]]]:
    """校验声明 provenance 后所需的 top_k/items/source ids。"""

    question_id = record.get("question_id")
    top_k = record.get("retrieval_query_top_k")
    items = record.get("retrieved_items")
    if not isinstance(top_k, int) or top_k < 1:
        raise ConfigurationError(
            f"question {question_id}: provider declares provenance_granularity="
            f"{granularity!r} but retrieval_query_top_k is missing or invalid"
        )
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ConfigurationError(
            f"question {question_id}: provider declares provenance_granularity="
            f"{granularity!r} but retrieved_items is missing or invalid"
        )
    for item in items[:top_k]:
        source_ids = item.get("source_turn_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ConfigurationError(
                f"question {question_id}: provider declares provenance_granularity="
                f"{granularity!r} but a retrieved item has missing or empty source_turn_ids"
            )
    return top_k, items


def _provenance_granularity(manifest: dict[str, Any]) -> str:
    """读取 method manifest 的 provenance 声明。"""

    method = manifest.get("method")
    if not isinstance(method, dict) or method.get("provenance_granularity") is None:
        return "undeclared"
    return str(method["provenance_granularity"])


def _required_string_list(
    metadata: dict[str, Any], key: str, question_id: str
) -> list[str]:
    """读取 evaluator-private metadata 中必需的公开匹配键列表。"""

    value = metadata.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(
            f"question {question_id}: private label metadata requires {key} list"
        )
    return value


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


def _public_session_id(source_id: str) -> str:
    """把公开 turn id 上卷到公开 session id。"""

    prefix, separator, suffix = source_id.rpartition(":t")
    return prefix if separator and suffix.isdigit() else source_id


def _na_payload(granularity: str) -> dict[str, Any]:
    """构造 provider 未声明 provenance 时的结构化 N/A。"""

    return {
        "metric_name": LongMemEvalRetrievalRankEvaluator.metric_name,
        "score_records": [],
        "total_questions": 0,
        "mean_score": 0.0,
        "correct_count": None,
        "summary": {
            "status": "n/a",
            "reason": "provider provenance is unavailable",
            "provenance_granularity": granularity,
            "turn2session_view": "not_artifact_computable",
        },
    }


__all__ = ["LongMemEvalRetrievalRankEvaluator"]

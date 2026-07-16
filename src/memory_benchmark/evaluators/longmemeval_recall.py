"""LongMemEval 双粒度条件式 retrieval recall（artifact-only，离线）。

匹配只使用 method 可见的公开 id 空间。权威 qrel 是 gold evidence contract v1
的 `evidence_group_sets`：turn view 只含官方口径 user 侧 target
（`longmemeval_user_target_turn`），session view 以官方 answer_session_id 为
unit（`longmemeval_answer_session`）。`_abs` 题不评分；非 abs 且当前 view 无
gold unit 的题按官方 `run_retrieval.py:389-410` 剔除口径记 N/A（canonical 分母
=419），不再错误记 1.0。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.storage import ExperimentPaths, read_jsonl

from .gold_evidence_groups import (
    group_recall_score,
    parse_evidence_group_sets,
    require_manifest_gold_evidence_contract_v1,
    select_group_set,
)


class LongMemEvalRetrievalRecallEvaluator:
    """按 provider 声明的 provenance 粒度计算 LongMemEval 条件式 recall。"""

    metric_name = "longmemeval_recall"
    official_corpus_id_source = (
        "third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:79"
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
        provenance_granularity = _method_provenance_granularity(manifest)
        if provenance_granularity in {"none", "undeclared"}:
            return _na_payload(self.metric_name, provenance_granularity)
        if provenance_granularity not in {"turn", "session"}:
            raise ConfigurationError(
                f"Unknown provenance_granularity {provenance_granularity!r} in "
                "manifest['method']; expected 'none', 'session' or 'turn'"
            )

        answer_records = read_jsonl(paths.answer_prompts_path)
        private_records = read_jsonl(paths.evaluator_private_labels_path)
        public_records = read_jsonl(paths.public_questions_path)
        _validate_matching_question_ids(answer_records, private_records, public_records)
        private_by_id = {record["question_id"]: record for record in private_records}
        category_by_id = {
            record["question_id"]: record.get("category") for record in public_records
        }

        score_records: list[dict[str, Any]] = []
        scored_records: list[dict[str, Any]] = []
        top_k_values: list[int] = []
        no_target_count = 0
        abstention_count = 0

        for answer_record in answer_records:
            question_id = str(answer_record["question_id"])
            category = category_by_id.get(question_id)
            if "_abs" in question_id:
                abstention_count += 1
                score_records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer_record.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "abstention questions have no recallable gold evidence",
                        "abstention": True,
                        "category": category,
                        "provenance_granularity": provenance_granularity,
                    }
                )
                continue

            groups = select_group_set(
                parse_evidence_group_sets(private_by_id[question_id], question_id),
                provenance_granularity=provenance_granularity,
                unit_kind=(
                    "longmemeval_user_target_turn"
                    if provenance_granularity == "turn"
                    else "longmemeval_answer_session"
                ),
                question_id=question_id,
            ).groups
            if not groups:
                # 官方 run_retrieval.py:389-410 聚合口径：无官方 gold unit 的题
                # 整题剔除（turn 主路径 canonical 分母 419），不再错误记 1.0。
                no_target_count += 1
                score_records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer_record.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "official_no_target",
                        "abstention": False,
                        "category": category,
                        "provenance_granularity": provenance_granularity,
                    }
                )
                continue

            top_k, retrieved_items = _validated_retrieval_fields(
                answer_record,
                provenance_granularity,
            )
            source_ids = _source_ids(retrieved_items, top_k)
            if provenance_granularity == "session":
                source_ids = {
                    _public_session_id(source_id) for source_id in source_ids
                }
            score = group_recall_score(groups, source_ids)

            top_k_values.append(top_k)
            record = {
                "question_id": question_id,
                "conversation_id": answer_record.get("conversation_id"),
                "metric_name": self.metric_name,
                "score": score,
                "status": "ok",
                "abstention": False,
                "category": category,
                "requested_top_k": top_k,
                "provenance_granularity": provenance_granularity,
                "details": {
                    "gold_unit_ids": [group.unit_id for group in groups],
                    "unmatched_gold_unit_count": sum(
                        1 for group in groups if group.mapping_status == "unmatched"
                    ),
                    "retrieved_source_ids": sorted(source_ids),
                    "official_corpus_id_source": self.official_corpus_id_source,
                    "framework_supplementary": True,
                },
            }
            score_records.append(record)
            scored_records.append(record)

        return _scored_payload(
            metric_name=self.metric_name,
            score_records=score_records,
            scored_records=scored_records,
            top_k_values=top_k_values,
            no_target_count=no_target_count,
            abstention_count=abstention_count,
            provenance_granularity=provenance_granularity,
            official_corpus_id_source=self.official_corpus_id_source,
        )


def _method_provenance_granularity(manifest: dict[str, Any]) -> str:
    """读取 method manifest 的 provenance_granularity 声明。"""

    method = manifest.get("method")
    if not isinstance(method, dict) or method.get("provenance_granularity") is None:
        return "undeclared"
    return str(method["provenance_granularity"])


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
            "LongMemEval recall artifact question IDs must match exactly across "
            "answer prompts, private labels and public questions"
        )


def _validated_retrieval_fields(
    record: dict[str, Any],
    provenance_granularity: str,
) -> tuple[int, list[dict[str, Any]]]:
    """校验声明 provenance 后必需的 top_k、retrieved_items 与 source ids。"""

    question_id = record.get("question_id")
    top_k = record.get("retrieval_query_top_k")
    retrieved_items = record.get("retrieved_items")
    if not isinstance(top_k, int) or top_k < 1:
        raise ConfigurationError(
            f"question {question_id}: provider declares provenance_granularity="
            f"{provenance_granularity!r} but retrieval_query_top_k is missing or invalid"
        )
    if not isinstance(retrieved_items, list) or any(
        not isinstance(item, dict) for item in retrieved_items
    ):
        raise ConfigurationError(
            f"question {question_id}: provider declares provenance_granularity="
            f"{provenance_granularity!r} but retrieved_items is missing or invalid"
        )
    for item in retrieved_items[:top_k]:
        source_ids = item.get("source_turn_ids")
        if not isinstance(source_ids, list) or not source_ids:
            raise ConfigurationError(
                f"question {question_id}: provider declares provenance_granularity="
                f"{provenance_granularity!r} but a retrieved item has missing or empty "
                "source_turn_ids"
            )
    return top_k, retrieved_items


def _source_ids(retrieved_items: list[dict[str, Any]], top_k: int) -> set[str]:
    """合并有序 top-k retrieved items 的公开 source ids。"""

    return {
        str(source_id)
        for item in retrieved_items[:top_k]
        for source_id in item["source_turn_ids"]
    }


def _public_session_id(source_id: str) -> str:
    """把公开 turn id 上卷到公开 session id；原生 session id 保持不变。"""

    prefix, separator, suffix = source_id.rpartition(":t")
    if separator and suffix.isdigit():
        return prefix
    return source_id


def _na_payload(metric_name: str, provenance_granularity: str) -> dict[str, Any]:
    """构造 provider 无 provenance 能力时的结构化 N/A。"""

    return {
        "metric_name": metric_name,
        "score_records": [],
        "total_questions": 0,
        "mean_score": 0.0,
        "correct_count": None,
        "summary": {
            "status": "n/a",
            "reason": "provider provenance is unavailable",
            "provenance_granularity": provenance_granularity,
        },
    }


def _scored_payload(
    *,
    metric_name: str,
    score_records: list[dict[str, Any]],
    scored_records: list[dict[str, Any]],
    top_k_values: list[int],
    no_target_count: int,
    abstention_count: int,
    provenance_granularity: str,
    official_corpus_id_source: str,
) -> dict[str, Any]:
    """聚合已评分问题，保留 abstention 与官方 no-target 剔除的 N/A records。"""

    scores = [float(record["score"]) for record in scored_records]
    mean_score = sum(scores) / len(scores) if scores else 0.0
    grouped: dict[str, list[float]] = {}
    for record in scored_records:
        category = record.get("category")
        grouped.setdefault("unknown" if category is None else str(category), []).append(
            float(record["score"])
        )
    by_category = {
        category: {
            "scored_count": len(category_scores),
            "mean_score": sum(category_scores) / len(category_scores),
        }
        for category, category_scores in sorted(grouped.items())
    }
    return {
        "metric_name": metric_name,
        "score_records": score_records,
        "total_questions": len(scored_records),
        "mean_score": mean_score,
        "correct_count": None,
        "summary": {
            "status": "ok" if scored_records else "n/a",
            "provenance_granularity": provenance_granularity,
            "scored_question_count": len(scored_records),
            "abstention_question_count": abstention_count,
            "official_no_target_question_count": no_target_count,
            "official_denominator_source": (
                "LongMemEval-main/src/retrieval/run_retrieval.py:389-410 "
                "(canonical 419; print_retrieval_metrics.py:12 的 470 只是"
                "官方辅助脚本冲突披露，不用于主口径)"
            ),
            "overall_mean_recall_at_requested_k": mean_score,
            "by_category": by_category,
            "requested_top_k_distribution": dict(Counter(top_k_values)),
            "official_corpus_id_source": official_corpus_id_source,
            "framework_supplementary": True,
        },
    }


__all__ = ["LongMemEvalRetrievalRecallEvaluator"]

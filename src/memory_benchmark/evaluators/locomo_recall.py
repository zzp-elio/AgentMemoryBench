"""LoCoMo 条件式 retrieval recall evaluator（artifact-only，离线）。

本模块只从已落盘的 run artifact（manifest、`answer_prompts.prediction.jsonl`、
`evaluator_private_labels.jsonl`）重算 recall，不构造 provider、不重新调用
`retrieve()`。官方来源：
`third_party/benchmarks/locomo-main/task_eval/evaluation.py:189-241`
（dia_id recall 公式，含 evidence 为空时记 1.0 的官方行为）。

权威 qrel 是 gold evidence contract v1 的 `evidence_group_sets`（每个官方
dia_id 一个 unit，分母按稳定去重后的官方 unit 数）；旧扁平 `evidence` 只留
历史审计，不再参与计分。

provenance 分级：
- provider 声明 `provenance_granularity="turn"`：取有序
  `retrieved_items[:retrieval_query_top_k]` 的 `source_turn_ids` 并集，与
  turn view（`locomo_utterance`）group 匹配。
- provider 声明 `provenance_granularity="session"`：把 source turn id 向上聚合
  为 `D<n>` session 前缀，与 session view
  （`locomo_utterance_session_projection`）group 匹配，summary 明确标注
  session-level，不冒充 turn-level。
- provider 声明 `provenance_granularity="none"`：写结构化 N/A，不计 0 分。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.storage import ExperimentPaths, read_jsonl

from .gold_evidence_groups import (
    group_recall_score,
    parse_evidence_group_sets,
    require_manifest_gold_evidence_contract_v1,
    select_group_set,
)


class LoCoMoRetrievalRecallEvaluator:
    """按 provider 声明的 provenance_granularity 计算 LoCoMo 条件式 recall。"""

    metric_name = "locomo_recall"
    official_source = (
        "third_party/benchmarks/locomo-main/task_eval/evaluation.py:189-241"
    )

    def evaluate_run_artifacts(
        self,
        *,
        paths: ExperimentPaths,
        manifest: dict[str, Any],
        max_workers: int = 1,
    ) -> dict[str, Any]:
        """读取 manifest 与已落盘 artifact，计算条件式 recall。

        输入:
            paths: 已完成 prediction 的 run 目录路径集合。
            manifest: 已加载的 run manifest。
            max_workers: 未使用；离线计算不需要并行，保留签名兼容 artifact
                evaluator 通用调用约定。

        输出:
            dict: 供 `run_artifact_evaluation` 写盘的 artifact-level payload。
        """

        provenance_granularity = _method_provenance_granularity(manifest)
        if provenance_granularity in {"none", "undeclared"}:
            return _na_payload(
                metric_name=self.metric_name,
                reason=(
                    "provider provenance is unavailable; retrieval recall is not "
                    "evaluable for this run"
                ),
                provenance_granularity=provenance_granularity,
                official_source=self.official_source,
            )
        require_manifest_gold_evidence_contract_v1(manifest)
        if provenance_granularity not in ("turn", "session"):
            raise ConfigurationError(
                f"Unknown provenance_granularity {provenance_granularity!r} in "
                "manifest['method']; expected 'none', 'session' or 'turn'"
            )

        answer_prompt_records = read_jsonl(paths.answer_prompts_path)
        private_records = read_jsonl(paths.evaluator_private_labels_path)
        public_records = read_jsonl(paths.public_questions_path)
        answer_ids = [record.get("question_id") for record in answer_prompt_records]
        private_ids = [record.get("question_id") for record in private_records]
        public_ids = [record.get("question_id") for record in public_records]
        if (
            len(set(answer_ids)) != len(answer_ids)
            or len(set(private_ids)) != len(private_ids)
            or len(set(public_ids)) != len(public_ids)
            or set(answer_ids) != set(private_ids)
            or set(answer_ids) != set(public_ids)
        ):
            raise ConfigurationError(
                "LoCoMo recall artifact question IDs must match exactly across "
                "answer prompts, private labels and public questions"
            )
        private_by_id = {record["question_id"]: record for record in private_records}
        category_by_id = {
            record["question_id"]: record.get("category") for record in public_records
        }

        score_records: list[dict[str, Any]] = []
        top_k_values: list[int] = []
        empty_evidence_count = 0
        non_empty_evidence_scores: list[float] = []

        for record in answer_prompt_records:
            question_id = record.get("question_id")
            private = private_by_id[question_id]

            top_k = record.get("retrieval_query_top_k")
            retrieved_items = record.get("retrieved_items")
            if top_k is None:
                raise ConfigurationError(
                    f"question {question_id}: provider declares provenance_granularity="
                    f"{provenance_granularity!r} but answer prompt artifact is missing "
                    "retrieval_query_top_k"
                )
            if retrieved_items is None:
                raise ConfigurationError(
                    f"question {question_id}: provider declares provenance_granularity="
                    f"{provenance_granularity!r} but answer prompt artifact is missing "
                    "retrieved_items"
                )
            for item in retrieved_items[:top_k]:
                if "source_turn_ids" not in item:
                    raise ConfigurationError(
                        f"question {question_id}: provider declares "
                        f"provenance_granularity={provenance_granularity!r} but a "
                        "retrieved item is missing source_turn_ids"
                    )
                if not item["source_turn_ids"]:
                    raise ConfigurationError(
                        f"question {question_id}: provider declares "
                        f"provenance_granularity={provenance_granularity!r} but a "
                        "retrieved item has empty source_turn_ids"
                    )

            top_k_values.append(top_k)
            group_sets = parse_evidence_group_sets(private, question_id)
            unit_kind = (
                "locomo_utterance"
                if provenance_granularity == "turn"
                else "locomo_utterance_session_projection"
            )
            groups = select_group_set(
                group_sets,
                provenance_granularity=provenance_granularity,
                unit_kind=unit_kind,
                question_id=question_id,
            ).groups
            source_ids = _source_turn_ids(retrieved_items, top_k)
            if provenance_granularity == "session":
                source_ids = {_session_prefix(source_id) for source_id in source_ids}

            if not groups:
                # 官方原生行为：空 evidence 记 1（evaluation.py:237），保留披露。
                empty_evidence_count += 1
                score = 1.0
            else:
                score = group_recall_score(groups, source_ids)
                non_empty_evidence_scores.append(score)

            score_records.append(
                {
                    "question_id": question_id,
                    "conversation_id": record.get("conversation_id"),
                    "metric_name": self.metric_name,
                    "score": score,
                    "category": category_by_id.get(question_id),
                    "requested_top_k": top_k,
                    "empty_evidence": not groups,
                    "gold_unit_count": len(groups),
                    "provenance_granularity": provenance_granularity,
                }
            )

        return _scored_payload(
            metric_name=self.metric_name,
            score_records=score_records,
            top_k_values=top_k_values,
            empty_evidence_count=empty_evidence_count,
            non_empty_evidence_scores=non_empty_evidence_scores,
            provenance_granularity=provenance_granularity,
            official_source=self.official_source,
        )


def _method_provenance_granularity(manifest: dict[str, Any]) -> str:
    """从 manifest 读取实际 provider 的 provenance_granularity 声明。"""

    method_manifest = manifest.get("method")
    if not isinstance(method_manifest, dict):
        return "undeclared"
    provenance_granularity = method_manifest.get("provenance_granularity")
    if provenance_granularity is None:
        return "undeclared"
    return str(provenance_granularity)


def _source_turn_ids(
    retrieved_items: list[dict[str, Any]],
    top_k: int,
) -> set[str]:
    """按声明的 top_k 截取有序 retrieved_items，返回 source turn id 并集。"""

    ids: set[str] = set()
    for item in retrieved_items[:top_k]:
        for turn_id in item.get("source_turn_ids") or []:
            ids.add(str(turn_id))
    return ids


def _session_prefix(dia_id: str) -> str:
    """把 `D<n>:<turn>` 形式的 dia_id 向上聚合为 `D<n>` session 前缀。"""

    prefix, _, _rest = dia_id.partition(":")
    return prefix if _rest else dia_id


def _na_payload(
    *,
    metric_name: str,
    reason: str,
    provenance_granularity: str,
    official_source: str,
) -> dict[str, Any]:
    """构造 provenance_granularity='none' 时的结构化 N/A payload。"""

    return {
        "metric_name": metric_name,
        "score_records": [],
        "total_questions": 0,
        "mean_score": 0.0,
        "correct_count": None,
        "summary": {
            "status": "n/a",
            "reason": reason,
            "provenance_granularity": provenance_granularity,
            "official_source": official_source,
        },
    }


def _scored_payload(
    *,
    metric_name: str,
    score_records: list[dict[str, Any]],
    top_k_values: list[int],
    empty_evidence_count: int,
    non_empty_evidence_scores: list[float],
    provenance_granularity: str,
    official_source: str,
) -> dict[str, Any]:
    """聚合 overall / by-category / top-k 分布，构造 scored payload。"""

    scores = [record["score"] for record in score_records]
    overall_mean = sum(scores) / len(scores) if scores else 0.0
    non_empty_mean = (
        sum(non_empty_evidence_scores) / len(non_empty_evidence_scores)
        if non_empty_evidence_scores
        else None
    )

    by_category: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in score_records:
        category = record.get("category")
        key = "unknown" if category is None else str(category)
        grouped.setdefault(key, []).append(record)
    for category, records in sorted(grouped.items()):
        category_scores = [record["score"] for record in records]
        by_category[category] = {
            "scored_count": len(records),
            "mean_score": sum(category_scores) / len(category_scores),
        }

    top_k_distribution = dict(Counter(top_k_values))

    return {
        "metric_name": metric_name,
        "score_records": score_records,
        "total_questions": len(score_records),
        "mean_score": overall_mean,
        "correct_count": None,
        "summary": {
            "status": "ok",
            "provenance_granularity": provenance_granularity,
            "scored_question_count": len(score_records),
            "empty_evidence_question_count": empty_evidence_count,
            "non_empty_evidence_mean_recall_at_requested_k": non_empty_mean,
            "overall_mean_recall_at_requested_k": overall_mean,
            "by_category": by_category,
            "requested_top_k_distribution": top_k_distribution,
            "official_source": official_source,
        },
    }


__all__ = ["LoCoMoRetrievalRecallEvaluator"]

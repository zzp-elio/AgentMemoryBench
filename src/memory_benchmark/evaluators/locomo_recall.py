"""LoCoMo 条件式 retrieval recall evaluator（artifact-only，离线）。

本模块只从已落盘的 run artifact（manifest、`answer_prompts.prediction.jsonl`、
`evaluator_private_labels.jsonl`）重算 recall，不构造 provider、不重新调用
`retrieve()`。官方来源：
`third_party/benchmarks/locomo-main/task_eval/evaluation.py:189-241`
（dia_id recall 公式，含 evidence 为空时记 1.0 的官方行为）。

权威 qrel 是 gold evidence contract v1 的 `evidence_group_sets`（每个官方
dia_id 一个 unit，分母按稳定去重后的官方 unit 数）；旧扁平 `evidence` 只留
历史审计，不再参与计分。

RetrievalEvidence M1 起，资格改为逐题事实：每条 answer prompt 记录携带的
`retrieval_evidence`（provider 逐次陈述）经 `evaluators.retrieval_evidence`
严格 preflight 后，按 `decide_retrieval_eligibility` 派生 valid/n_a/pending
裁决——

- decision valid：按其逐题 granularity 选择 turn（`locomo_utterance`）或
  session（`locomo_utterance_session_projection`）Gold Evidence Group view，
  执行既有官方公式；
- decision n_a/pending：写结构化 N/A/pending record，不计 0 分、不进分母；
- 旧 run 级 `manifest["method"]["provenance_granularity"]` 字段不再参与任何
  资格判定或 view 选择，仅作历史审计遗留。
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
from .retrieval_evidence import (
    RetrievalEligibilityDecision,
    decide_retrieval_eligibility,
    display_status,
    parse_retrieval_evidence,
    require_manifest_retrieval_evidence_contract_v1,
    summary_provenance_granularity,
    summary_status,
    validated_retrieval_fields,
)

_ALLOWED_GRANULARITIES = frozenset({"turn", "session"})


class LoCoMoRetrievalRecallEvaluator:
    """按 provider 逐题声明的 retrieval evidence 计算 LoCoMo 条件式 recall。"""

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
        """读取 manifest 与已落盘 artifact，逐题裁决资格后计算条件式 recall。

        输入:
            paths: 已完成 prediction 的 run 目录路径集合。
            manifest: 已加载的 run manifest。
            max_workers: 未使用；离线计算不需要并行，保留签名兼容 artifact
                evaluator 通用调用约定。

        输出:
            dict: 供 `run_artifact_evaluation` 写盘的 artifact-level payload。
        """

        del max_workers
        require_manifest_gold_evidence_contract_v1(manifest)
        require_manifest_retrieval_evidence_contract_v1(manifest)

        answer_prompt_records = read_jsonl(paths.answer_prompts_path)
        private_records = read_jsonl(paths.evaluator_private_labels_path)
        public_records = read_jsonl(paths.public_questions_path)
        _validate_matching_question_ids(answer_prompt_records, private_records, public_records)
        private_by_id = {record["question_id"]: record for record in private_records}
        category_by_id = {
            record["question_id"]: record.get("category") for record in public_records
        }

        decisions_by_id = _decisions_by_question_id(answer_prompt_records)

        score_records: list[dict[str, Any]] = []
        top_k_values: list[int] = []
        empty_evidence_count = 0
        non_empty_evidence_scores: list[float] = []
        evidence_status_counts: Counter[str] = Counter()
        evidence_reason_code_counts: Counter[str] = Counter()
        scored_decisions: list[RetrievalEligibilityDecision] = []

        for record in answer_prompt_records:
            question_id = record.get("question_id")
            private = private_by_id[question_id]
            category = category_by_id.get(question_id)
            decision = decisions_by_id[question_id]
            evidence_status_counts[decision.status] += 1

            if decision.status != "valid":
                evidence_reason_code_counts[decision.reason_code] += 1
                score_records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": record.get("conversation_id"),
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

            provenance_granularity = decision.provenance_granularity
            top_k, retrieved_items = validated_retrieval_fields(record, question_id)

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
                    "status": "ok",
                    "retrieval_evidence_status": "valid",
                    "category": category,
                    "requested_top_k": top_k,
                    "empty_evidence": not groups,
                    "gold_unit_count": len(groups),
                    "provenance_granularity": provenance_granularity,
                }
            )
            scored_decisions.append(decision)

        return _scored_payload(
            metric_name=self.metric_name,
            score_records=score_records,
            top_k_values=top_k_values,
            empty_evidence_count=empty_evidence_count,
            non_empty_evidence_scores=non_empty_evidence_scores,
            evidence_status_counts=evidence_status_counts,
            evidence_reason_code_counts=evidence_reason_code_counts,
            scored_decisions=scored_decisions,
            official_source=self.official_source,
        )


def _decisions_by_question_id(
    answer_prompt_records: list[dict[str, Any]],
) -> dict[str, RetrievalEligibilityDecision]:
    """对全部 answer records 做逐题 retrieval evidence preflight + 资格裁决。

    在进入任何计分循环前对**全部**记录解析，即使某题最终会被跳过也必须先
    通过结构化校验——不给不计分题留下携带非法 evidence 的空子。
    """

    decisions: dict[str, RetrievalEligibilityDecision] = {}
    for record in answer_prompt_records:
        question_id = str(record["question_id"])
        evidence = parse_retrieval_evidence(record.get("retrieval_evidence"), question_id)
        decisions[question_id] = decide_retrieval_eligibility(
            evidence,
            allowed_granularities=_ALLOWED_GRANULARITIES,
            requires_stable_ranking=False,
        )
    return decisions


def _validate_matching_question_ids(
    answer_prompt_records: list[dict[str, Any]],
    private_records: list[dict[str, Any]],
    public_records: list[dict[str, Any]],
) -> None:
    """校验三类 artifact 的 question id 必须唯一且集合完全一致。"""

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


def _scored_payload(
    *,
    metric_name: str,
    score_records: list[dict[str, Any]],
    top_k_values: list[int],
    empty_evidence_count: int,
    non_empty_evidence_scores: list[float],
    evidence_status_counts: Counter[str],
    evidence_reason_code_counts: Counter[str],
    scored_decisions: list[RetrievalEligibilityDecision],
    official_source: str,
) -> dict[str, Any]:
    """聚合 overall / by-category / top-k 分布，构造逐题裁决感知的 payload。"""

    scored_records = [record for record in score_records if record["score"] is not None]
    scores = [record["score"] for record in scored_records]
    overall_mean = sum(scores) / len(scores) if scores else 0.0
    non_empty_mean = (
        sum(non_empty_evidence_scores) / len(non_empty_evidence_scores)
        if non_empty_evidence_scores
        else None
    )

    by_category: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in scored_records:
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
    pending_count = evidence_status_counts.get("pending", 0)

    return {
        "metric_name": metric_name,
        "score_records": score_records,
        "total_questions": len(scored_records),
        "mean_score": overall_mean,
        "correct_count": None,
        "summary": {
            "status": summary_status(scored_count=len(scored_records), pending_count=pending_count),
            "provenance_granularity": summary_provenance_granularity(scored_decisions),
            "scored_question_count": len(scored_records),
            "empty_evidence_question_count": empty_evidence_count,
            "non_empty_evidence_mean_recall_at_requested_k": non_empty_mean,
            "overall_mean_recall_at_requested_k": overall_mean,
            "by_category": by_category,
            "requested_top_k_distribution": top_k_distribution,
            "retrieval_evidence_status_counts": dict(evidence_status_counts),
            "retrieval_evidence_reason_code_counts": dict(evidence_reason_code_counts),
            "metric_tier": "framework_supplementary",
            "official_source": official_source,
        },
    }


__all__ = ["LoCoMoRetrievalRecallEvaluator"]

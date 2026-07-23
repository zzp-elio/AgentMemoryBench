"""retrieval evaluator 的公共资格、逐题记录与聚合壳。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..retrieval_evidence import (
    AGGREGATION_CONTRACT_VERSION,
    RetrievalEligibilityDecision,
    decide_retrieval_eligibility,
    display_status,
    nullable_mean,
    parse_retrieval_evidence,
    score_status_counts,
    summary_provenance_granularity,
    summary_status,
)


def build_retrieval_decisions(
    answer_records: list[dict[str, Any]],
    *,
    allowed_granularities: frozenset[str],
    requires_stable_ranking: bool,
) -> dict[str, RetrievalEligibilityDecision]:
    """在 benchmark 排除逻辑前，对全部 answer record 做严格 evidence preflight。"""

    decisions: dict[str, RetrievalEligibilityDecision] = {}
    for record in answer_records:
        question_id = str(record["question_id"])
        evidence = parse_retrieval_evidence(
            record.get("retrieval_evidence"), question_id
        )
        decisions[question_id] = decide_retrieval_eligibility(
            evidence,
            allowed_granularities=allowed_granularities,
            requires_stable_ranking=requires_stable_ranking,
        )
    return decisions


@dataclass
class RetrievalEvaluationState:
    """收集公共逐题状态，benchmark 壳只负责政策分支与详情字段。"""

    score_records: list[dict[str, Any]] = field(default_factory=list)
    scored_records: list[dict[str, Any]] = field(default_factory=list)
    top_k_values: list[int] = field(default_factory=list)
    evidence_status_counts: Counter[str] = field(default_factory=Counter)
    evidence_reason_code_counts: Counter[str] = field(default_factory=Counter)
    scored_decisions: list[RetrievalEligibilityDecision] = field(
        default_factory=list
    )

    def add_benchmark_exclusion(self, record: dict[str, Any]) -> None:
        """追加 benchmark-policy N/A；不污染 provider evidence 统计。"""

        self.score_records.append(record)

    def add_ineligible(
        self,
        *,
        answer_record: dict[str, Any],
        metric_name: str,
        category: Any,
        decision: RetrievalEligibilityDecision,
        extra_fields: dict[str, Any] | None = None,
        include_provenance_granularity: bool = True,
    ) -> None:
        """追加 provider n_a/pending record，并统一累计原因统计。"""

        self.evidence_status_counts[decision.status] += 1
        self.evidence_reason_code_counts[decision.reason_code] += 1
        record: dict[str, Any] = {
            "question_id": str(answer_record["question_id"]),
            "conversation_id": answer_record.get("conversation_id"),
            "metric_name": metric_name,
            "score": None,
            "status": display_status(decision.status),
            "retrieval_evidence_status": decision.status,
            "reason_code": decision.reason_code,
            "reason": decision.reason,
        }
        if extra_fields:
            record.update(extra_fields)
        record["category"] = category
        if include_provenance_granularity:
            record["provenance_granularity"] = decision.provenance_granularity
        self.score_records.append(record)

    def add_scored(
        self,
        *,
        record: dict[str, Any],
        decision: RetrievalEligibilityDecision,
        top_k: int,
    ) -> None:
        """追加真实计分 record，并同步公共分母、top-k 与粒度统计。"""

        self.evidence_status_counts[decision.status] += 1
        self.score_records.append(record)
        self.scored_records.append(record)
        self.top_k_values.append(top_k)
        self.scored_decisions.append(decision)

    def build_payload(
        self,
        *,
        metric_name: str,
        summary_fields: dict[str, Any],
        include_by_category: bool,
        include_top_k_distribution: bool = True,
        metric_tier: str = "framework_supplementary",
    ) -> dict[str, Any]:
        """构造所有 retrieval evaluator 共用的顶层与 summary 字段。"""

        scores = [float(record["score"]) for record in self.scored_records]
        mean_score = nullable_mean(scores)
        pending_count = self.evidence_status_counts.get("pending", 0)
        summary: dict[str, Any] = {
            "status": summary_status(
                scored_count=len(self.scored_records),
                pending_count=pending_count,
            ),
            "provenance_granularity": summary_provenance_granularity(
                self.scored_decisions
            ),
            "scored_question_count": len(self.scored_records),
        }
        summary.update(summary_fields)
        if include_by_category:
            summary["by_category"] = _scores_by_category(self.scored_records)
        if include_top_k_distribution:
            summary["requested_top_k_distribution"] = dict(
                Counter(self.top_k_values)
            )
        summary.update(
            {
                "retrieval_evidence_status_counts": dict(
                    self.evidence_status_counts
                ),
                "retrieval_evidence_reason_code_counts": dict(
                    self.evidence_reason_code_counts
                ),
                "score_status_counts": score_status_counts(self.score_records),
                "aggregation_contract_version": AGGREGATION_CONTRACT_VERSION,
                "metric_tier": metric_tier,
            }
        )
        return {
            "metric_name": metric_name,
            "score_records": self.score_records,
            "total_questions": len(self.score_records),
            "mean_score": mean_score,
            "correct_count": None,
            "summary": summary,
        }


def _scores_by_category(
    scored_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """按 category 聚合已评分记录。"""

    grouped: dict[str, list[float]] = {}
    for record in scored_records:
        category = record.get("category")
        key = "unknown" if category is None else str(category)
        grouped.setdefault(key, []).append(float(record["score"]))
    return {
        category: {
            "scored_count": len(scores),
            "mean_score": sum(scores) / len(scores),
        }
        for category, scores in sorted(grouped.items())
    }


__all__ = ["RetrievalEvaluationState", "build_retrieval_decisions"]

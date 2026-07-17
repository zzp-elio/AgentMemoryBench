"""LongMemEval 双粒度条件式 retrieval recall（artifact-only，离线）。

匹配只使用 method 可见的公开 id 空间。权威 qrel 是 gold evidence contract v1
的 `evidence_group_sets`：turn view 只含官方口径 user 侧 target
（`longmemeval_user_target_turn`），session view 以官方 answer_session_id 为
unit（`longmemeval_answer_session`）。`_abs` 题不评分（benchmark policy 剔除，
粒度无关，检查顺序在逐题裁决之前）；非 abs 题先用 canonical private turn view
判定 official no-target，按 `run_retrieval.py:389-410` 剔除口径记 N/A
（canonical 分母=419），两类排除均不计入 provider evidence status。只有 canonical
turn 有 target 的题才消费 eligibility，并按其粒度选择计分 view。

RetrievalEvidence M1 起，provider 侧资格改为逐题事实：每条 answer prompt
记录携带的 `retrieval_evidence` 经 `evaluators.retrieval_evidence` 严格
preflight 后按 `decide_retrieval_eligibility` 派生 valid/n_a/pending 裁决，
只有 valid 才继续选择 granularity 对应的 gold view 计分；n_a/pending 写独立
的逐题 record，与官方 abstention/no-target 分开计数。旧 run 级
`manifest["method"]["provenance_granularity"]` 字段不再参与任何资格判定或
view 选择。
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


class LongMemEvalRetrievalRecallEvaluator:
    """按 provider 逐题声明的 retrieval evidence 计算 LongMemEval 条件式 recall。"""

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
        no_target_count = 0
        abstention_count = 0
        evidence_status_counts: Counter[str] = Counter()
        evidence_reason_code_counts: Counter[str] = Counter()
        scored_decisions: list[RetrievalEligibilityDecision] = []

        for answer_record in answer_records:
            question_id = str(answer_record["question_id"])
            category = category_by_id.get(question_id)
            if "_abs" in question_id:
                # abstention 是官方 benchmark policy 剔除，与 evidence 内容无关，
                # 粒度无关；检查顺序在逐题裁决之前，不计入 retrieval evidence
                # status 统计。
                abstention_count += 1
                score_records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer_record.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "abstention questions have no recallable gold evidence",
                        "exclusion_source": "benchmark_policy",
                        "abstention": True,
                        "category": category,
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
                # 官方 no-target 必须由 canonical private turn view 判定，不能先
                # 根据 provider granularity 选择 view，更不能改写为 provider gap。
                no_target_count += 1
                score_records.append(
                    {
                        "question_id": question_id,
                        "conversation_id": answer_record.get("conversation_id"),
                        "metric_name": self.metric_name,
                        "score": None,
                        "status": "n/a",
                        "reason": "official_no_target",
                        "exclusion_source": "benchmark_policy",
                        "abstention": False,
                        "category": category,
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
                        "abstention": False,
                        "category": category,
                        "provenance_granularity": decision.provenance_granularity,
                    }
                )
                continue

            provenance_granularity = decision.provenance_granularity
            groups = canonical_turn_groups
            if provenance_granularity == "session":
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

            top_k, retrieved_items = validated_retrieval_fields(
                answer_record, question_id
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
                "retrieval_evidence_status": "valid",
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
            scored_decisions.append(decision)

        return _scored_payload(
            metric_name=self.metric_name,
            score_records=score_records,
            scored_records=scored_records,
            top_k_values=top_k_values,
            no_target_count=no_target_count,
            abstention_count=abstention_count,
            evidence_status_counts=evidence_status_counts,
            evidence_reason_code_counts=evidence_reason_code_counts,
            scored_decisions=scored_decisions,
            official_corpus_id_source=self.official_corpus_id_source,
        )


def _decisions_by_question_id(
    answer_records: list[dict[str, Any]],
) -> dict[str, RetrievalEligibilityDecision]:
    """对全部 answer records 做逐题 retrieval evidence preflight + 资格裁决。

    在进入 `_abs`/no-target 等 benchmark-specific 排除或计分循环前对**全部**
    记录解析——即将被 `_abs` 剔除的题也不得携带非法 evidence。
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
            "LongMemEval recall artifact question IDs must match exactly across "
            "answer prompts, private labels and public questions"
        )


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


def _scored_payload(
    *,
    metric_name: str,
    score_records: list[dict[str, Any]],
    scored_records: list[dict[str, Any]],
    top_k_values: list[int],
    no_target_count: int,
    abstention_count: int,
    evidence_status_counts: Counter[str],
    evidence_reason_code_counts: Counter[str],
    scored_decisions: list[RetrievalEligibilityDecision],
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
    pending_count = evidence_status_counts.get("pending", 0)
    return {
        "metric_name": metric_name,
        "score_records": score_records,
        "total_questions": len(scored_records),
        "mean_score": mean_score,
        "correct_count": None,
        "summary": {
            "status": summary_status(scored_count=len(scored_records), pending_count=pending_count),
            "provenance_granularity": summary_provenance_granularity(scored_decisions),
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
            "retrieval_evidence_status_counts": dict(evidence_status_counts),
            "retrieval_evidence_reason_code_counts": dict(evidence_reason_code_counts),
            "metric_tier": "framework_supplementary",
            "official_corpus_id_source": official_corpus_id_source,
            "framework_supplementary": True,
        },
    }


__all__ = ["LongMemEvalRetrievalRecallEvaluator"]

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

from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.metrics.retrieval import identity_source_id, recall_at_k
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
        artifacts = load_retrieval_artifacts(
            paths=paths,
            manifest=manifest,
            mismatch_error=(
                "LongMemEval recall artifact question IDs must match exactly across "
                "answer prompts, private labels and public questions"
            ),
        )
        decisions_by_id = build_retrieval_decisions(
            artifacts.answer_records,
            allowed_granularities=_ALLOWED_GRANULARITIES,
            requires_stable_ranking=False,
        )
        state = RetrievalEvaluationState()
        no_target_count = 0
        abstention_count = 0

        for answer_record in artifacts.answer_records:
            question_id = str(answer_record["question_id"])
            category = artifacts.category_by_id.get(question_id)
            if "_abs" in question_id:
                # abstention 是官方 benchmark policy 剔除，与 evidence 内容无关，
                # 粒度无关；检查顺序在逐题裁决之前，不计入 retrieval evidence
                # status 统计。
                abstention_count += 1
                state.add_benchmark_exclusion(
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
                artifacts.private_by_id[question_id], question_id
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
                state.add_benchmark_exclusion(
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

            if decision.status != "valid":
                state.add_ineligible(
                    answer_record=answer_record,
                    metric_name=self.metric_name,
                    category=category,
                    decision=decision,
                    extra_fields={"abstention": False},
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
            projector = (
                _public_session_id
                if provenance_granularity == "session"
                else identity_source_id
            )
            recall_result = recall_at_k(
                groups,
                retrieved_items,
                top_k,
                source_id_projector=projector,
            )
            score = recall_result.score

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
                    "retrieved_source_ids": sorted(recall_result.source_ids),
                    "official_corpus_id_source": self.official_corpus_id_source,
                    "framework_supplementary": True,
                },
            }
            state.add_scored(record=record, decision=decision, top_k=top_k)

        payload = state.build_payload(
            metric_name=self.metric_name,
            include_by_category=True,
            summary_fields={
                "abstention_question_count": abstention_count,
                "official_no_target_question_count": no_target_count,
                "official_denominator_source": (
                    "LongMemEval-main/src/retrieval/run_retrieval.py:389-410 "
                    "(canonical 419; print_retrieval_metrics.py:12 的 470 只是"
                    "官方辅助脚本冲突披露，不用于主口径)"
                ),
                "overall_mean_recall_at_requested_k": None,
                "official_corpus_id_source": self.official_corpus_id_source,
                "framework_supplementary": True,
            },
        )
        payload["summary"]["overall_mean_recall_at_requested_k"] = payload["mean_score"]
        return payload


def _public_session_id(source_id: str) -> str:
    """把公开 turn id 上卷到公开 session id；原生 session id 保持不变。"""

    prefix, separator, suffix = source_id.rpartition(":t")
    if separator and suffix.isdigit():
        return prefix
    return source_id


__all__ = ["LongMemEvalRetrievalRecallEvaluator"]

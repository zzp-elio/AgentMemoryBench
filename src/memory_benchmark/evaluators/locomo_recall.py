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

from typing import Any

from memory_benchmark.metrics.retrieval import identity_source_id, recall_at_k
from memory_benchmark.storage import ExperimentPaths

from .common.artifact import load_retrieval_artifacts
from .common.retrieval import (
    RetrievalEvaluationState,
    build_retrieval_decisions,
)
from .gold_evidence_groups import parse_evidence_group_sets, select_group_set
from .retrieval_evidence import validated_retrieval_fields

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
        artifacts = load_retrieval_artifacts(
            paths=paths,
            manifest=manifest,
            mismatch_error=(
                "LoCoMo recall artifact question IDs must match exactly across "
                "answer prompts, private labels and public questions"
            ),
        )
        decisions_by_id = build_retrieval_decisions(
            artifacts.answer_records,
            allowed_granularities=_ALLOWED_GRANULARITIES,
            requires_stable_ranking=False,
        )
        state = RetrievalEvaluationState()
        empty_evidence_count = 0
        non_empty_evidence_scores: list[float] = []

        for record in artifacts.answer_records:
            question_id = record.get("question_id")
            private = artifacts.private_by_id[question_id]
            category = artifacts.category_by_id.get(question_id)
            decision = decisions_by_id[question_id]

            if decision.status != "valid":
                state.add_ineligible(
                    answer_record=record,
                    metric_name=self.metric_name,
                    category=category,
                    decision=decision,
                )
                continue

            provenance_granularity = decision.provenance_granularity
            top_k, retrieved_items = validated_retrieval_fields(record, question_id)

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

            if not groups:
                # 官方原生行为：空 evidence 记 1（evaluation.py:237），保留披露。
                empty_evidence_count += 1
                score = 1.0
            else:
                projector = (
                    _session_prefix
                    if provenance_granularity == "session"
                    else identity_source_id
                )
                score = recall_at_k(
                    groups,
                    retrieved_items,
                    top_k,
                    source_id_projector=projector,
                ).score
                non_empty_evidence_scores.append(score)

            state.add_scored(
                record={
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
                },
                decision=decision,
                top_k=top_k,
            )

        non_empty_mean = (
            sum(non_empty_evidence_scores) / len(non_empty_evidence_scores)
            if non_empty_evidence_scores
            else None
        )
        payload = state.build_payload(
            metric_name=self.metric_name,
            include_by_category=True,
            summary_fields={
                "empty_evidence_question_count": empty_evidence_count,
                "non_empty_evidence_mean_recall_at_requested_k": non_empty_mean,
                "overall_mean_recall_at_requested_k": None,
                "official_source": self.official_source,
            },
        )
        payload["summary"]["overall_mean_recall_at_requested_k"] = payload["mean_score"]
        return payload


def _session_prefix(dia_id: str) -> str:
    """把 `D<n>:<turn>` 形式的 dia_id 向上聚合为 `D<n>` session 前缀。"""

    prefix, _, _rest = dia_id.partition(":")
    return prefix if _rest else dia_id


__all__ = ["LoCoMoRetrievalRecallEvaluator"]

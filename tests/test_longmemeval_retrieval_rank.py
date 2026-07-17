"""LongMemEval 官方 retrieval rank 指标测试。

RetrievalEvidence M1 后，rank/NDCG 在 Recall 的 semantic provenance + gold
granularity 门之上，还要求逐题 `stable_ranking=valid` 才计分：当前三家真实
provider 的 `stable_ranking` 都恒为 `pending`（rank 审计未完成），因此真实
run 上 rank 题应诚实输出 pending、不产指标。本文件用合成
`stable_ranking=valid` fixture 锁定既有 DCG/recall 公式与 k coverage 规则，
不代表任何真实 provider 现状。
"""

from __future__ import annotations

from math import log2
from pathlib import Path

import pytest

from memory_benchmark.core import ConfigurationError, GoldAnswerInfo, GoldEvidenceGroup, GoldEvidenceGroupSet, Question
from memory_benchmark.evaluators.longmemeval_retrieval_rank import (
    LongMemEvalRetrievalRankEvaluator,
    _evaluate_groups_at_k,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    evaluator_private_label_record,
    public_question_record,
)


pytestmark = pytest.mark.unit

V1_BENCHMARK_POLICY = {"gold_evidence_contract_version": "v1"}


def _v1_gold(qid: str, gold: list[str]) -> GoldAnswerInfo:
    """构造带 v1 turn view groups 的 gold label。"""

    groups = tuple(
        GoldEvidenceGroup(
            unit_id=gid,
            child_ids=(gid,),
            mapping_status="mapped",
        )
        for gid in gold
    )
    return GoldAnswerInfo(
        qid,
        "gold",
        metadata={
            "evidence_turn_ids": gold,
            "evidence_turn_corpus_ids": [],
            "evidence_session_public_ids": [],
        },
        gold_evidence_contract_version="v1",
        evidence_group_sets=(
            GoldEvidenceGroupSet(
                provenance_granularity="turn",
                unit_kind="longmemeval_user_target_turn",
                groups=groups,
            ),
        ),
    )


def _assertion(status: str, *, reason_code: str | None = None, reason: str | None = None) -> dict:
    """构造一条序列化后的 `EvidenceAssertion`（模拟 `asdict()` 输出）。"""

    return {"status": status, "reason_code": reason_code, "reason": reason}


def _synthetic_ranked_evidence(granularity: str = "turn") -> dict:
    """构造合成的 fully-valid evidence（含 `stable_ranking=valid`）。

    仅用于锁定既有 DCG/recall 公式；不代表任何真实 provider 现状——当前三家
    真实 provider 的 `stable_ranking` 都恒为 `pending`。
    """

    return {
        "semantic_provenance": _assertion("valid"),
        "provenance_granularity": granularity,
        "stable_ranking": _assertion("valid"),
    }


def _pending_ranking_evidence(granularity: str = "turn") -> dict:
    """构造 semantic provenance valid 但 `stable_ranking=pending` 的真实现状 evidence。"""

    return {
        "semantic_provenance": _assertion("valid"),
        "provenance_granularity": granularity,
        "stable_ranking": _assertion(
            "pending",
            reason_code="ranking_fidelity_not_audited",
            reason="per-method rank audit not completed",
        ),
    }


def _na_ranking_evidence(granularity: str = "turn") -> dict:
    """构造 semantic provenance valid 但 `stable_ranking=n_a` 的 evidence。"""

    return {
        "semantic_provenance": _assertion("valid"),
        "provenance_granularity": granularity,
        "stable_ranking": _assertion(
            "n_a",
            reason_code="ranking_not_recoverable",
            reason="method display layer re-sorts items, no stable rank available",
        ),
    }


def _na_semantic_evidence(
    reason_code: str = "benchmark_identity_missing",
    reason: str = "provider does not recognize this benchmark identity",
) -> dict:
    """构造 semantic provenance 本身就 `n_a` 的 evidence。"""

    return {
        "semantic_provenance": _assertion("n_a", reason_code=reason_code, reason=reason),
        "provenance_granularity": "none",
        "stable_ranking": _assertion("n_a", reason_code=reason_code, reason=reason),
    }


def test_ndcg_matches_official_formula_hand_computed(tmp_path: Path) -> None:
    """全命中、部分命中、零命中的 NDCG 应与官方 DCG 公式手算一致。"""

    paths, manifest = _write_run(
        tmp_path,
        rows=[
            ("q-all", ["s:t0", "s:t1"], ["s:t0", "s:t1", "s:t2"]),
            ("q-part", ["s:t0", "s:t1"], ["s:t2", "s:t0", "s:t3"]),
            ("q-zero", ["s:t0"], ["s:t2", "s:t3", "s:t4"]),
        ],
        top_k=3,
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    by_id = {record["question_id"]: record["metrics"] for record in result["score_records"]}
    # k=3: all=(1+1/log2(2))/(1+1/log2(2))=1；part=1/log2(2)/2=0.5；zero=0。
    ideal_two = 1.0 + 1.0 / log2(2)
    assert by_id["q-all"]["ndcg_any@3"] == pytest.approx(1.0)
    assert by_id["q-part"]["ndcg_any@3"] == pytest.approx((1.0 / log2(2)) / ideal_two)
    assert by_id["q-zero"]["ndcg_any@3"] == 0.0


def test_recall_all_requires_every_gold_doc(tmp_path: Path) -> None:
    """命中一个 gold 时 recall_any 为 1，而 recall_all 必须为 0。"""

    paths, manifest = _write_run(
        tmp_path, rows=[("q", ["s:t0", "s:t1"], ["s:t0"])], top_k=1
    )
    metrics = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )["score_records"][0]["metrics"]
    assert metrics["recall_any@1"] == 1.0
    assert metrics["recall_all@1"] == 0.0


def test_unmatched_group_stays_in_ndcg_ideal_denominator() -> None:
    """unmatched 官方 unit 必须扣在 ideal 分母，不能被洗成满分。"""

    groups = (
        GoldEvidenceGroup("mapped", ("hit",), "mapped"),
        GoldEvidenceGroup("unmatched", (), "unmatched"),
    )

    metrics = _evaluate_groups_at_k(["hit"], groups, 3)

    assert metrics["recall_any@3"] == 1.0
    assert metrics["recall_all@3"] == 0.0
    assert metrics["ndcg_any@3"] == pytest.approx(0.5)


def test_group_rank_uses_best_child_and_duplicate_child_has_no_extra_gain() -> None:
    """multi-child 取最小 rank，检索列表重复同一 child 不得重复累计 DCG。"""

    groups = (
        GoldEvidenceGroup("g1", ("late", "early"), "mapped"),
        GoldEvidenceGroup("g2", ("other",), "mapped"),
    )

    metrics = _evaluate_groups_at_k(
        ["noise", "early", "other", "late", "early"],
        groups,
        5,
    )

    expected_actual = 1.0 / log2(2) + 1.0 / log2(3)
    expected_ideal = 1.0 + 1.0 / log2(2)
    assert metrics["ndcg_any@5"] == pytest.approx(expected_actual / expected_ideal)


def test_k_above_top_k_is_skipped_and_counted(tmp_path: Path) -> None:
    """artifact top_k 以上的官方 k 不得输出下界冒充官方结果，并标注稳定 reason code。"""

    paths, manifest = _write_run(
        tmp_path, rows=[("q", ["s:t0"], ["s:t0"])], top_k=3
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    assert set(result["score_records"][0]["metrics"]) == {
        "recall_any@1", "recall_all@1", "ndcg_any@1",
        "recall_any@3", "recall_all@3", "ndcg_any@3",
    }
    assert result["summary"]["skipped_k_above_top_k"] == [5, 10, 30, 50]
    assert result["summary"]["skipped_k_above_top_k_count"] == 4
    assert (
        result["summary"]["skipped_k_above_top_k_reason_code"]
        == "evaluation_depth_not_requested"
    )


def test_query_top_k_10_yields_exactly_1_3_5_10_and_marks_30_50_unavailable(
    tmp_path: Path,
) -> None:
    """当前 `RetrievalQuery.top_k=10` 时应恰好产出官方 1/3/5/10，30/50 显式 unavailable。

    本卡不改 `top_k=10` 字面量、不二次 retrieve；30/50 物理上不可能被满足，
    必须诚实标记为 unavailable，不能把已有的 10 个 item 冒充成 k=30/50 结果。
    """

    paths, manifest = _write_run(
        tmp_path, rows=[("q", ["s:t0"], ["s:t0"])], top_k=10
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    assert set(result["score_records"][0]["metrics"]) == {
        "recall_any@1", "recall_all@1", "ndcg_any@1",
        "recall_any@3", "recall_all@3", "ndcg_any@3",
        "recall_any@5", "recall_all@5", "ndcg_any@5",
        "recall_any@10", "recall_all@10", "ndcg_any@10",
    }
    assert result["summary"]["skipped_k_above_top_k"] == [30, 50]


def test_per_k_denominator_only_counts_valid_questions_covering_that_k(
    tmp_path: Path,
) -> None:
    """每个 k 的 participating 分母只含 decision valid 且 query depth 覆盖该 k 的题。

    三题 top_k 各不相同（1/3/10），且其中一题 stable_ranking=pending：k=1 应
    被三题中的两题（top_k>=1 且 valid）覆盖，k=3 只被 top_k>=3 的一题覆盖，
    pending 题不参与任何 k。
    """

    paths, manifest = _write_run(
        tmp_path,
        rows=[("q-k1", ["s:t0"], ["s:t0"]), ("q-k10", ["s:t0"], ["s:t0"])],
        top_k=1,
        per_question_top_k={"q-k1": 1, "q-k10": 10},
        evidence_by_qid={"q-k1": _synthetic_ranked_evidence(), "q-k10": _synthetic_ranked_evidence()},
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    counts = result["summary"]["participating_question_count_by_k"]
    assert counts["1"] == 2
    assert counts["3"] == 1
    assert counts["10"] == 1


def test_abstention_questions_excluded_with_count(tmp_path: Path) -> None:
    """`_abs` 题应保留 N/A record，但从聚合分母排除。"""

    paths, manifest = _write_run(
        tmp_path, rows=[("q_abs_1", [], []), ("q", ["s:t0"], ["s:t0"])], top_k=1
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    records = {record["question_id"]: record for record in result["score_records"]}
    assert records["q_abs_1"]["score"] is None
    assert result["total_questions"] == 1
    assert result["summary"]["abstention_excluded_count"] == 1


def test_semantic_provenance_na_returns_na_record_without_metrics(tmp_path: Path) -> None:
    """semantic provenance 本身 n_a 时该题不产 metrics，且不计入任何 k 分母。"""

    paths, manifest = _write_run(
        tmp_path,
        rows=[("q1", ["s:t0"], ["s:t0"])],
        top_k=3,
        evidence_by_qid={"q1": _na_semantic_evidence("beam_style_gap", "coarser batch")},
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    record = result["score_records"][0]
    assert record["score"] is None
    assert record["status"] == "n/a"
    assert "metrics" not in record
    assert result["summary"]["participating_question_count_by_k"] == {}


def test_stable_ranking_pending_blocks_scoring_and_reports_pending_status(
    tmp_path: Path,
) -> None:
    """semantic provenance valid 但 stable_ranking=pending：该题应 pending，不产指标。

    这是当前三家真实 provider 的实际状态：rank 审计尚未完成，诚实输出 pending
    比为了保留分数而跳过 rank 门更正确。
    """

    paths, manifest = _write_run(
        tmp_path,
        rows=[("q1", ["s:t0"], ["s:t0"])],
        top_k=3,
        evidence_by_qid={"q1": _pending_ranking_evidence()},
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    record = result["score_records"][0]
    assert record["score"] is None
    assert record["status"] == "pending"
    assert record["retrieval_evidence_status"] == "pending"
    assert "metrics" not in record
    assert result["summary"]["status"] == "pending"
    assert result["summary"]["scored_question_count"] == 0


def test_stable_ranking_na_is_distinct_from_pending(tmp_path: Path) -> None:
    """stable_ranking=n_a 与 pending 必须各自保留独立 status，不混写成同一态。"""

    paths, manifest = _write_run(
        tmp_path,
        rows=[
            ("q-na", ["s:t0"], ["s:t0"]),
            ("q-pending", ["s:t0"], ["s:t0"]),
        ],
        top_k=3,
        evidence_by_qid={
            "q-na": _na_ranking_evidence(),
            "q-pending": _pending_ranking_evidence(),
        },
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    records = {record["question_id"]: record for record in result["score_records"]}
    assert records["q-na"]["status"] == "n/a"
    assert records["q-na"]["retrieval_evidence_status"] == "n_a"
    assert records["q-pending"]["status"] == "pending"
    assert records["q-pending"]["retrieval_evidence_status"] == "pending"


def test_synthetic_stable_ranking_valid_locks_formula(tmp_path: Path) -> None:
    """合成 stable_ranking=valid 时应正常产出与既有公式一致的 metrics。"""

    paths, manifest = _write_run(
        tmp_path,
        rows=[("q1", ["s:t0", "s:t1"], ["s:t0", "s:t1"])],
        top_k=3,
        evidence_by_qid={"q1": _synthetic_ranked_evidence()},
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    record = result["score_records"][0]
    assert record["status"] == "ok"
    assert record["retrieval_evidence_status"] == "valid"
    assert record["metrics"]["recall_all@3"] == 1.0


def test_missing_retrieval_evidence_contract_version_fails_fast(tmp_path: Path) -> None:
    """manifest 缺 retrieval_evidence_contract_version 必须先于旧 N/A 分支 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path, rows=[], top_k=1, retrieval_evidence_contract_version=None
    )
    with pytest.raises(ConfigurationError, match="retrieval_evidence_contract_version"):
        LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
            paths=paths, manifest=manifest
        )


def test_empty_run_returns_structured_na(tmp_path: Path) -> None:
    """没有任何问题的 run 应自然产生结构化 N/A。"""

    paths, manifest = _write_run(tmp_path, rows=[], top_k=1)
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    assert result["summary"]["status"] == "n/a"
    assert result["score_records"] == []


@pytest.mark.parametrize(
    "evidence",
    [
        _synthetic_ranked_evidence(),
        _pending_ranking_evidence(),
        _na_semantic_evidence(),
    ],
)
def test_official_no_target_precedes_rank_eligibility_for_every_status(
    tmp_path: Path, evidence: dict
) -> None:
    """canonical no-target 必须先于 rank valid/pending/n_a，且不计 evidence status。"""

    paths, manifest = _write_run(
        tmp_path,
        rows=[("q", [], [])],
        top_k=1,
        evidence_by_qid={"q": evidence},
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    record = result["score_records"][0]
    assert record["reason"] == "official_no_target"
    assert record["exclusion_source"] == "benchmark_policy"
    assert result["summary"]["retrieval_evidence_status_counts"] == {}
    assert result["summary"]["provenance_granularity"] is None


def test_summary_reports_metric_tier_and_formula_parity(tmp_path: Path) -> None:
    """summary 必须标注 framework_supplementary metric tier 与 available-k parity。"""

    paths, manifest = _write_run(
        tmp_path, rows=[("q", ["s:t0"], ["s:t0"])], top_k=1
    )
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    assert result["summary"]["metric_tier"] == "framework_supplementary"
    assert result["summary"]["formula_parity_at_available_k"] is True
    assert result["summary"]["scored_question_count"] == 1


def _write_run(
    tmp_path: Path,
    *,
    rows: list[tuple[str, list[str], list[str]]],
    top_k: int,
    evidence_by_qid: dict[str, dict] | None = None,
    per_question_top_k: dict[str, int] | None = None,
    retrieval_evidence_contract_version: str | None = "v1",
) -> tuple[ExperimentPaths, dict[str, object]]:
    """用生产 public/private serializers 构造排名 evaluator artifact。

    默认每题的 evidence 为合成 fully-valid（含 `stable_ranking=valid`），用于
    锁定既有公式；`evidence_by_qid` 可逐题覆盖以测试 n_a/pending 路径。
    """

    paths = ExperimentPaths.create(tmp_path / "run")
    method: dict[str, object] = {}
    if retrieval_evidence_contract_version is not None:
        method["retrieval_evidence_contract_version"] = retrieval_evidence_contract_version
    manifest: dict[str, object] = {
        "run_id": "rank-run", "benchmark_name": "longmemeval", "method": method,
    }
    manifest["benchmark_policy"] = V1_BENCHMARK_POLICY
    atomic_write_json(paths.manifest_path, manifest)
    questions = [Question(qid, qid, "Question?", category="multi-session") for qid, _, _ in rows]
    atomic_write_jsonl(
        paths.public_questions_path,
        [public_question_record(question) for question in questions],
    )
    atomic_write_jsonl(
        paths.evaluator_private_labels_path,
        [
            evaluator_private_label_record(
                _v1_gold(qid, gold),
                category="multi-session",
            )
            for qid, gold, _ in rows
        ],
    )
    evidence_by_qid = evidence_by_qid or {}
    per_question_top_k = per_question_top_k or {}
    atomic_write_jsonl(
        paths.answer_prompts_path,
        [
            {
                "question_id": qid,
                "conversation_id": qid,
                "retrieval_query_top_k": per_question_top_k.get(qid, top_k),
                "retrieved_items": [_item(source_id) for source_id in retrieved],
                "retrieval_evidence": (
                    evidence_by_qid[qid]
                    if qid in evidence_by_qid
                    else _synthetic_ranked_evidence()
                ),
            }
            for qid, _, retrieved in rows
        ],
    )
    return paths, manifest


def _item(source_id: str) -> dict[str, object]:
    """构造生产 answer-prompt artifact 中的公开 retrieved item 形状。"""

    return {
        "item_id": source_id,
        "content": "memory",
        "score": 1.0,
        "timestamp": None,
        "source_turn_ids": [source_id],
        "metadata": {},
    }

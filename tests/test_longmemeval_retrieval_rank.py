"""LongMemEval 官方 retrieval rank 指标测试。"""

from __future__ import annotations

from math import log2
from pathlib import Path

import pytest

from memory_benchmark.core import GoldAnswerInfo, GoldEvidenceGroup, GoldEvidenceGroupSet, Question
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
    """artifact top_k 以上的官方 k 不得输出下界冒充官方结果。"""

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


def test_missing_provenance_returns_na_payload(tmp_path: Path) -> None:
    """method 未声明 provenance 时整个指标应返回结构化 N/A。"""

    paths, manifest = _write_run(tmp_path, rows=[], top_k=1, provenance=None)
    result = LongMemEvalRetrievalRankEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )
    assert result["summary"]["status"] == "n/a"
    assert result["score_records"] == []


def _write_run(
    tmp_path: Path,
    *,
    rows: list[tuple[str, list[str], list[str]]],
    top_k: int,
    provenance: str | None = "turn",
) -> tuple[ExperimentPaths, dict[str, object]]:
    """用生产 public/private serializers 构造排名 evaluator artifact。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    method = {} if provenance is None else {"provenance_granularity": provenance}
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
    atomic_write_jsonl(
        paths.answer_prompts_path,
        [
            {
                "question_id": qid,
                "conversation_id": qid,
                "retrieval_query_top_k": top_k,
                "retrieved_items": [_item(source_id) for source_id in retrieved],
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

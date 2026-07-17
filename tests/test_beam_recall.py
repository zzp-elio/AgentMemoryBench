"""BEAM artifact-only conditional recall 测试。

RetrievalEvidence M1 后，BEAM recall 只接受 turn 粒度 gold view（`{"turn"}`）：
逐题 evidence 若 semantic provenance valid 但 granularity 非 turn，由共享
`decide_retrieval_eligibility` 统一导出 `n_a`/`gold_granularity_mismatch`，
与 MemBench 共用同一条通用规则，不再各自手写专用判断。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.core import (
    ConfigurationError,
    GoldAnswerInfo,
    GoldEvidenceGroup,
    GoldEvidenceGroupSet,
)
from memory_benchmark.evaluators.beam_recall import BeamRetrievalRecallEvaluator
from memory_benchmark.evaluators.locomo_recall import LoCoMoRetrievalRecallEvaluator
from memory_benchmark.evaluators.longmemeval_recall import (
    LongMemEvalRetrievalRecallEvaluator,
)
from memory_benchmark.evaluators.longmemeval_retrieval_rank import (
    LongMemEvalRetrievalRankEvaluator,
)
from memory_benchmark.evaluators.membench_recall import (
    MemBenchRetrievalRecallEvaluator,
)
from memory_benchmark.storage import ExperimentPaths, atomic_write_jsonl
from memory_benchmark.storage.artifacts import evaluator_private_label_record


pytestmark = pytest.mark.unit

V1_MANIFEST_BENCHMARK_POLICY = {"gold_evidence_contract_version": "v1"}


def _item(*source_ids: str) -> dict[str, object]:
    """构造带公开 turn provenance 的 retrieval item。"""

    return {"source_turn_ids": list(source_ids), "content": "memory"}


def _assertion(status: str, *, reason_code: str | None = None, reason: str | None = None) -> dict:
    """构造一条序列化后的 `EvidenceAssertion`（模拟 `asdict()` 输出）。"""

    return {"status": status, "reason_code": reason_code, "reason": reason}


def _valid_evidence(granularity: str = "turn") -> dict:
    """构造 `semantic_provenance=valid` 的逐题 evidence；`stable_ranking` 固定 pending。"""

    return {
        "semantic_provenance": _assertion("valid"),
        "provenance_granularity": granularity,
        "stable_ranking": _assertion(
            "pending",
            reason_code="ranking_fidelity_not_audited",
            reason="per-method rank audit not completed",
        ),
    }


def _na_evidence(
    reason_code: str = "ingest_batch_coarser_than_gold",
    reason: str = "provider ingest batch is coarser than gold turn granularity",
) -> dict:
    """构造 `semantic_provenance=n_a` 的逐题 evidence。"""

    return {
        "semantic_provenance": _assertion("n_a", reason_code=reason_code, reason=reason),
        "provenance_granularity": "none",
        "stable_ranking": _assertion("n_a", reason_code=reason_code, reason=reason),
    }


def _gold(
    question_id: str,
    evidence: list[str],
    *,
    unmatched: int = 0,
    ambiguous: int = 0,
) -> GoldAnswerInfo:
    """构造带 v1 group sets 的 evaluator-private gold。

    输入:
        evidence: 扁平 turn-id 列表；每个 id 建一个 singleton mapped child 的
            group。空 evidence 对应空 groups（abstention）。
    """

    groups = tuple(
        GoldEvidenceGroup(
            unit_id=evidence_id,
            child_ids=(evidence_id,),
            mapping_status="mapped",
        )
        for evidence_id in evidence
    )
    return _gold_with_groups(
        question_id,
        groups,
        legacy_evidence=evidence,
        unmatched=unmatched,
        ambiguous=ambiguous,
    )


def _gold_with_groups(
    question_id: str,
    groups: tuple[GoldEvidenceGroup, ...],
    *,
    legacy_evidence: list[str],
    unmatched: int = 0,
    ambiguous: int = 0,
) -> GoldAnswerInfo:
    """构造可表达 multi-child/unmatched 的 v1 BEAM 私有标签。"""

    return GoldAnswerInfo(
        question_id=question_id,
        answer="gold",
        metadata={
            "evidence_turn_ids": legacy_evidence,
            "source_chat_ids": [1],
            "unmatched_gold_id_count": unmatched,
            "ambiguous_gold_id_count": ambiguous,
        },
        gold_evidence_contract_version="v1",
        evidence_group_sets=(
            GoldEvidenceGroupSet(
                provenance_granularity="turn",
                unit_kind="beam_source_message",
                groups=groups,
            ),
        ),
    )


def _run(
    tmp_path: Path,
    *,
    golds: list[GoldAnswerInfo],
    answers: list[dict[str, object]],
    categories: list[str],
    retrieval_evidence_contract_version: str | None = "v1",
) -> dict[str, object]:
    """通过真实私有序列化函数写入三类 artifact。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    atomic_write_jsonl(
        paths.evaluator_private_labels_path,
        [
            evaluator_private_label_record(gold, category)
            for gold, category in zip(golds, categories, strict=True)
        ],
    )
    atomic_write_jsonl(
        paths.public_questions_path,
        [
            {"question_id": gold.question_id, "category": category}
            for gold, category in zip(golds, categories, strict=True)
        ],
    )
    atomic_write_jsonl(paths.answer_prompts_path, answers)
    method: dict[str, object] = {}
    if retrieval_evidence_contract_version is not None:
        method["retrieval_evidence_contract_version"] = retrieval_evidence_contract_version
    manifest: dict[str, object] = {"method": method}
    manifest["benchmark_policy"] = V1_MANIFEST_BENCHMARK_POLICY
    return BeamRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest,
    )


def _answer(
    question_id: str,
    *,
    evidence: dict | None,
    top_k: int | None = None,
    retrieved_items: list[dict] | None = None,
) -> dict[str, object]:
    """构造一条 answer prompt artifact 记录。"""

    return {
        "question_id": question_id,
        "conversation_id": "c1",
        "retrieval_query_top_k": top_k,
        "retrieved_items": retrieved_items,
        "retrieval_evidence": evidence,
    }


def test_turn_recall_matches_public_ids_and_any_ambiguous_position(tmp_path: Path) -> None:
    """公开 turn id 任一歧义映射位置命中即计 hit。"""

    gold = _gold_with_groups(
        "q1",
        (
            GoldEvidenceGroup(
                unit_id="raw-7",
                child_ids=("s1:t1", "s2:t1"),
                mapping_status="mapped",
            ),
        ),
        legacy_evidence=["s1:t1", "s2:t1"],
        ambiguous=1,
    )
    result = _run(
        tmp_path,
        golds=[gold],
        answers=[
            _answer(
                "q1", evidence=_valid_evidence("turn"), top_k=1, retrieved_items=[_item("s2:t1")]
            )
        ],
        categories=["knowledge_update"],
    )
    assert result["score_records"][0]["score"] == 1.0
    assert result["score_records"][0]["details"]["gold_unit_ids"] == ["raw-7"]


def test_empty_evidence_is_na(tmp_path: Path) -> None:
    """真实空 group（abstention）应为 N/A，不进入 scored 分母。"""

    result = _run(
        tmp_path,
        golds=[_gold("q1", [])],
        answers=[_answer("q1", evidence=_valid_evidence("turn"))],
        categories=["event_ordering"],
    )
    assert result["score_records"][0]["status"] == "n/a"
    assert result["summary"]["abstention_question_count"] == 1


def test_unmatched_group_is_zero_and_remains_in_denominator(tmp_path: Path) -> None:
    """不可映射的 ``--`` 是真实 gold unit，应记 0 而不是伪装成空 gold。"""

    gold = _gold_with_groups(
        "q1",
        (
            GoldEvidenceGroup(
                unit_id="--",
                child_ids=(),
                mapping_status="unmatched",
            ),
        ),
        legacy_evidence=[],
        unmatched=1,
    )
    result = _run(
        tmp_path,
        golds=[gold],
        answers=[
            _answer("q1", evidence=_valid_evidence("turn"), top_k=1, retrieved_items=[])
        ],
        categories=["event_ordering"],
    )

    assert result["score_records"][0]["status"] == "ok"
    assert result["score_records"][0]["score"] == 0.0
    assert result["score_records"][0]["details"]["unmatched_gold_unit_count"] == 1
    assert result["summary"]["abstention_question_count"] == 0
    assert result["summary"]["unmatched_gold_id_count"] == 1


def test_semantic_provenance_na_returns_structured_na(tmp_path: Path) -> None:
    """provider 逐题 semantic provenance=n_a 时该题应为结构化 N/A。"""

    result = _run(
        tmp_path,
        golds=[_gold("q1", ["s1:t1"])],
        answers=[_answer("q1", evidence=_na_evidence())],
        categories=["summarization"],
    )
    assert result["summary"]["status"] == "n/a"
    assert result["score_records"][0]["score"] is None


def test_session_decision_is_gold_granularity_mismatch_na(tmp_path: Path) -> None:
    """BEAM 只接受 turn 粒度：session decision 应导出 gold_granularity_mismatch N/A。"""

    result = _run(
        tmp_path,
        golds=[_gold("q1", ["s1:t1"])],
        answers=[_answer("q1", evidence=_valid_evidence("session"), top_k=1, retrieved_items=[])],
        categories=["summarization"],
    )
    record = result["score_records"][0]
    assert record["score"] is None
    assert record["reason_code"] == "gold_granularity_mismatch"


def test_missing_retrieval_evidence_contract_version_fails_fast(tmp_path: Path) -> None:
    """manifest 缺 retrieval_evidence_contract_version 必须 fail-fast。"""

    with pytest.raises(ConfigurationError, match="retrieval_evidence_contract_version"):
        _run(
            tmp_path,
            retrieval_evidence_contract_version=None,
            golds=[],
            answers=[],
            categories=[],
        )


def test_group_evaluators_validate_manifest_before_provenance_na(
    tmp_path: Path,
) -> None:
    """旧/非法 gold manifest 不能被任何 provenance N/A 早退分支掩盖。

    manifest 完全缺 `retrieval_evidence_contract_version`（不只是旧
    `provenance_granularity=none`），gold 合约门必须仍先于新增的 retrieval
    evidence 合约门触发。
    """

    for evaluator_type in (
        BeamRetrievalRecallEvaluator,
        LoCoMoRetrievalRecallEvaluator,
        LongMemEvalRetrievalRecallEvaluator,
        LongMemEvalRetrievalRankEvaluator,
        MemBenchRetrievalRecallEvaluator,
    ):
        for benchmark_policy in (None, {"gold_evidence_contract_version": "bogus"}):
            manifest: dict[str, object] = {"method": {}}
            if benchmark_policy is not None:
                manifest["benchmark_policy"] = benchmark_policy

            with pytest.raises(
                ConfigurationError, match="gold evidence contract|expected 'v1'"
            ):
                evaluator_type().evaluate_run_artifacts(
                    paths=ExperimentPaths.create(
                        tmp_path / f"{evaluator_type.__name__}-{benchmark_policy}"
                    ),
                    manifest=manifest,
                )


def test_declared_turn_provenance_missing_source_ids_fails_fast(tmp_path: Path) -> None:
    """decision valid 却缺 source ids 必须 fail-fast。"""

    with pytest.raises(ConfigurationError, match="source_turn_ids"):
        _run(
            tmp_path,
            golds=[_gold("q1", ["s1:t1"])],
            answers=[
                {
                    "question_id": "q1",
                    "conversation_id": "c1",
                    "retrieval_query_top_k": 1,
                    "retrieved_items": [{"content": "memory"}],
                    "retrieval_evidence": _valid_evidence("turn"),
                }
            ],
            categories=["summarization"],
        )


def test_stable_ranking_pending_does_not_block_recall_scoring(tmp_path: Path) -> None:
    """Recall 不要求 stable ranking：stable_ranking=pending 时仍应正常计分。"""

    evidence = _valid_evidence("turn")
    assert evidence["stable_ranking"]["status"] == "pending"
    result = _run(
        tmp_path,
        golds=[_gold("q1", ["s1:t1"])],
        answers=[_answer("q1", evidence=evidence, top_k=1, retrieved_items=[_item("s1:t1")])],
        categories=["summarization"],
    )
    assert result["score_records"][0]["score"] == 1.0


def test_summary_reports_metric_tier_and_representative_granularity(
    tmp_path: Path,
) -> None:
    """summary 必须标 metric_tier，并为存量消费者保留代表性 provenance_granularity。"""

    result = _run(
        tmp_path,
        golds=[_gold("q1", ["s1:t1"])],
        answers=[
            _answer(
                "q1", evidence=_valid_evidence("turn"), top_k=1, retrieved_items=[_item("s1:t1")]
            )
        ],
        categories=["summarization"],
    )
    assert result["summary"]["metric_tier"] == "framework_supplementary"
    assert result["summary"]["provenance_granularity"] == "turn"

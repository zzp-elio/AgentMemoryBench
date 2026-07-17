"""LongMemEval 双粒度 artifact-only retrieval recall 测试。

RetrievalEvidence M1 后，资格由逐题 `retrieval_evidence` 派生：`_abs` 题保持
原有 benchmark-policy 剔除（不看 evidence 内容，粒度无关，检查顺序在裁决之
前）；官方 no-target 题仍是 benchmark policy 剔除，但现在必须先过 decision
valid 才能选中对应 granularity 的 gold view 来判断是否为空；provider 侧
n_a/pending 则产生独立的逐题 N/A/pending record，不与官方剔除混淆。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.longmemeval_recall import (
    LongMemEvalRetrievalRecallEvaluator,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
)


pytestmark = pytest.mark.unit


def _item(*source_ids: str) -> dict[str, object]:
    """构造带公开 provenance id 的 retrieved item。"""

    return {
        "item_id": "i1",
        "content": "memory",
        "score": 1.0,
        "timestamp": None,
        "source_turn_ids": list(source_ids),
        "metadata": {},
    }


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
    reason_code: str = "benchmark_identity_missing",
    reason: str = "provider does not recognize this benchmark identity",
) -> dict:
    """构造 `semantic_provenance=n_a` 的逐题 evidence。"""

    return {
        "semantic_provenance": _assertion("n_a", reason_code=reason_code, reason=reason),
        "provenance_granularity": "none",
        "stable_ranking": _assertion("n_a", reason_code=reason_code, reason=reason),
    }


def _pending_evidence(
    reason_code: str = "provenance_audit_not_completed",
    reason: str = "provider provenance audit is still in progress",
) -> dict:
    """构造 `semantic_provenance=pending` 的逐题 evidence。"""

    return {
        "semantic_provenance": _assertion("pending", reason_code=reason_code, reason=reason),
        "provenance_granularity": "none",
        "stable_ranking": _assertion("pending", reason_code=reason_code, reason=reason),
    }


def _write_run(
    tmp_path: Path,
    *,
    answer_prompts: list[dict[str, object]],
    private_labels: list[dict[str, object]],
    public_questions: list[dict[str, object]],
    retrieval_evidence_contract_version: str | None = "v1",
    include_benchmark_policy: bool = True,
) -> tuple[ExperimentPaths, dict[str, object]]:
    """写入 LongMemEval recall 所需的最小 artifact 集合。

    默认 manifest 同时声明 gold evidence contract v1 与 retrieval evidence
    contract v1，模拟真实 registered v1 run。
    """

    paths = ExperimentPaths.create(tmp_path / "run")
    method: dict[str, object] = {}
    if retrieval_evidence_contract_version is not None:
        method["retrieval_evidence_contract_version"] = retrieval_evidence_contract_version
    manifest: dict[str, object] = {
        "run_id": "run",
        "benchmark_name": "longmemeval",
        "method": method,
    }
    if include_benchmark_policy:
        manifest["benchmark_policy"] = {"gold_evidence_contract_version": "v1"}
    atomic_write_json(paths.manifest_path, manifest)
    atomic_write_jsonl(paths.answer_prompts_path, answer_prompts)
    atomic_write_jsonl(paths.evaluator_private_labels_path, private_labels)
    atomic_write_jsonl(paths.public_questions_path, public_questions)
    return paths, manifest


def _answer_prompt(
    question_id: str,
    *,
    evidence: dict | None,
    top_k: int | None = None,
    retrieved_items: list[dict] | None = None,
) -> dict[str, object]:
    """构造一条 answer prompt artifact 记录。"""

    return {
        "question_id": question_id,
        "conversation_id": question_id,
        "retrieval_query_top_k": top_k,
        "retrieved_items": retrieved_items,
        "retrieval_evidence": evidence,
    }


def _private_label(
    question_id: str,
    *,
    turn_ids: list[str],
    corpus_ids: list[str],
    session_ids: list[str],
) -> dict[str, object]:
    """构造同时含 v1 group sets 和旧 metadata 的私有标签。"""

    groups = [
        {
            "unit_id": turn_id,
            "child_ids": [turn_id],
            "mapping_status": "mapped",
        }
        for turn_id in turn_ids
    ]
    return {
        "question_id": question_id,
        "gold_answer": "gold",
        "category": "multi-session",
        "evidence": ["original-session"],
        "gold_evidence_contract_version": "v1",
        "evidence_group_sets": [
            {
                "provenance_granularity": "turn",
                "unit_kind": "longmemeval_user_target_turn",
                "groups": groups,
            },
            {
                "provenance_granularity": "session",
                "unit_kind": "longmemeval_answer_session",
                "groups": [
                    {
                        "unit_id": sid,
                        "child_ids": [sid],
                        "mapping_status": "mapped",
                    }
                    for sid in session_ids
                ],
            },
        ],
        "metadata": {
            "evidence_turn_ids": turn_ids,
            "evidence_turn_corpus_ids": corpus_ids,
            "evidence_session_public_ids": session_ids,
        },
    }


def test_turn_provenance_matches_public_turn_ids_and_reports_official_aliases(
    tmp_path: Path,
) -> None:
    """turn recall 应用公开 turn id 匹配，并只在 details 展示官方 alias。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("session-a:t1")],
            )
        ],
        private_labels=[
            _private_label(
                "q1",
                turn_ids=["session-a:t1", "session-b:t0"],
                corpus_ids=["session-a_2", "session-b_1"],
                session_ids=["session-a", "session-b"],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )

    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    record = result["score_records"][0]
    assert record["score"] == pytest.approx(0.5)
    assert record["details"]["gold_unit_ids"] == [
        "session-a:t1",
        "session-b:t0",
    ]


def test_session_provenance_matches_public_session_ids(tmp_path: Path) -> None:
    """session recall 应使用 evidence_session_public_ids，而非原始官方 evidence。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("session"),
                top_k=1,
                retrieved_items=[_item("session-a#occurrence_2:t4")],
            )
        ],
        private_labels=[
            _private_label(
                "q1",
                turn_ids=["session-a#occurrence_2:t0"],
                corpus_ids=["session-a_1"],
                session_ids=["session-a#occurrence_2"],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )

    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    assert result["score_records"][0]["score"] == 1.0
    assert result["score_records"][0]["provenance_granularity"] == "session"


def test_official_corpus_alias_is_not_used_as_turn_match_key(tmp_path: Path) -> None:
    """只返回官方 corpus alias 时不得误判为公开 turn-id 命中。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("session-a_2")],
            )
        ],
        private_labels=[
            _private_label(
                "q1",
                turn_ids=["session-a:t1"],
                corpus_ids=["session-a_2"],
                session_ids=["session-a"],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )

    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    assert result["score_records"][0]["score"] == 0.0


def test_abstention_question_is_na_and_counted_separately(tmp_path: Path) -> None:
    """`_abs` 题应写 N/A record 并标记为 benchmark policy 排除，不看 evidence 内容。

    `_abs` 检查发生在逐题裁决之前——即使 evidence 是完全合法的 valid，abstention
    题也不应该被计分，也不应该计入 `retrieval_evidence_status_counts`。
    """

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q_abs_1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[],
            ),
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("session-a:t1")],
            ),
        ],
        private_labels=[
            _private_label(
                "q_abs_1",
                turn_ids=[],
                corpus_ids=[],
                session_ids=[],
            ),
            _private_label(
                "q1",
                turn_ids=["session-a:t1"],
                corpus_ids=["session-a_2"],
                session_ids=["session-a"],
            ),
        ],
        public_questions=[
            {"question_id": "q_abs_1", "category": "single-session-user"},
            {"question_id": "q1", "category": "multi-session"},
        ],
    )

    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    records = {record["question_id"]: record for record in result["score_records"]}
    assert records["q_abs_1"]["status"] == "n/a"
    assert records["q_abs_1"]["score"] is None
    assert records["q_abs_1"]["abstention"] is True
    assert result["total_questions"] == 1
    assert result["mean_score"] == 1.0
    assert result["summary"]["scored_question_count"] == 1
    assert result["summary"]["abstention_question_count"] == 1
    # abstention 是 benchmark policy 剔除，不是 provider N/A：不计入逐题裁决统计。
    assert result["summary"]["retrieval_evidence_status_counts"] == {"valid": 1}


def test_provider_na_evidence_produces_na_record_distinct_from_abstention(
    tmp_path: Path,
) -> None:
    """provider 侧 n_a 是独立的逐题事实，必须与官方 abstention 分开计数。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=_na_evidence("beam_style_gap", "coarser batch"), top_k=1
            )
        ],
        private_labels=[
            _private_label(
                "q1",
                turn_ids=["session-a:t1"],
                corpus_ids=["session-a_2"],
                session_ids=["session-a"],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )

    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest,
    )
    record = result["score_records"][0]
    assert record["status"] == "n/a"
    assert record.get("abstention") is not True
    assert record["reason_code"] == "beam_style_gap"
    assert result["summary"]["abstention_question_count"] == 0
    assert result["summary"]["retrieval_evidence_status_counts"] == {"n_a": 1}


def test_official_no_target_after_valid_decision_is_benchmark_policy_na(
    tmp_path: Path,
) -> None:
    """decision valid 但所选 granularity 的 gold view 为空时，仍是官方 no-target N/A。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("session-a:t1")],
            )
        ],
        private_labels=[
            _private_label("q1", turn_ids=[], corpus_ids=[], session_ids=["session-a"])
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )

    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest,
    )
    record = result["score_records"][0]
    assert record["score"] is None
    assert record["reason"] == "official_no_target"
    assert result["summary"]["scored_question_count"] == 0
    # decision 本身是 valid（provider 侧没问题），只是 gold view 为空。
    assert result["summary"]["retrieval_evidence_status_counts"] == {"valid": 1}


def test_none_or_undeclared_provenance_returns_structured_na(
    tmp_path: Path,
) -> None:
    """provider 逐题 n_a 时整体结果应为结构化 N/A（不再有整跑级 undeclared 概念）。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[_answer_prompt("q1", evidence=_na_evidence(), top_k=1)],
        private_labels=[
            _private_label(
                "q1", turn_ids=["session-a:t1"], corpus_ids=["session-a_2"], session_ids=["session-a"]
            )
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )
    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )
    assert result["summary"]["status"] == "n/a"
    assert result["score_records"][0]["score"] is None


def test_declared_provenance_missing_source_ids_fails_fast(tmp_path: Path) -> None:
    """decision valid 却缺 source_turn_ids 时必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [{"item_id": "i1", "content": "memory"}],
                "retrieval_evidence": _valid_evidence("turn"),
            }
        ],
        private_labels=[
            _private_label(
                "q1",
                turn_ids=["session-a:t1"],
                corpus_ids=["session-a_2"],
                session_ids=["session-a"],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )

    with pytest.raises(ConfigurationError, match="source_turn_ids"):
        LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )


def test_declared_provenance_missing_private_gold_fails_fast(tmp_path: Path) -> None:
    """benchmark 未提供对应粒度 gold 时必须 fail-fast，不能静默记零。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("session-a:t1")],
            )
        ],
        private_labels=[
            {
                "question_id": "q1",
                "gold_answer": "gold",
                "metadata": {},
            }
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )

    with pytest.raises(ConfigurationError, match="old or mixed version"):
        LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )


def test_missing_retrieval_evidence_contract_version_fails_fast_before_abstention(
    tmp_path: Path,
) -> None:
    """manifest 缺 retrieval_evidence_contract_version 必须先于 `_abs` 剔除 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        retrieval_evidence_contract_version=None,
        answer_prompts=[_answer_prompt("q_abs_1", evidence=None, top_k=1, retrieved_items=[])],
        private_labels=[_private_label("q_abs_1", turn_ids=[], corpus_ids=[], session_ids=[])],
        public_questions=[{"question_id": "q_abs_1", "category": "single-session-user"}],
    )

    with pytest.raises(ConfigurationError, match="retrieval_evidence_contract_version"):
        LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_null_retrieval_evidence_on_abstention_question_still_fails_fast_at_preflight(
    tmp_path: Path,
) -> None:
    """即将被 `_abs` 剔除的题也不能携带非法 evidence：preflight 覆盖全部记录。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[_answer_prompt("q_abs_1", evidence=None, top_k=1, retrieved_items=[])],
        private_labels=[_private_label("q_abs_1", turn_ids=[], corpus_ids=[], session_ids=[])],
        public_questions=[{"question_id": "q_abs_1", "category": "single-session-user"}],
    )

    with pytest.raises(ConfigurationError, match="q_abs_1"):
        LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_stable_ranking_pending_does_not_block_recall_scoring(tmp_path: Path) -> None:
    """Recall 不要求 stable ranking：stable_ranking=pending 时仍应正常计分。"""

    evidence = _valid_evidence("turn")
    assert evidence["stable_ranking"]["status"] == "pending"
    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=evidence, top_k=1, retrieved_items=[_item("session-a:t1")]
            )
        ],
        private_labels=[
            _private_label(
                "q1",
                turn_ids=["session-a:t1"],
                corpus_ids=["session-a_2"],
                session_ids=["session-a"],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )

    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["score_records"][0]["score"] == 1.0


def test_summary_has_framework_supplementary_metric_tier_and_representative_granularity(
    tmp_path: Path,
) -> None:
    """summary 必须标 metric_tier，并为存量消费者保留代表性 provenance_granularity。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("session-a:t1")],
            )
        ],
        private_labels=[
            _private_label(
                "q1",
                turn_ids=["session-a:t1"],
                corpus_ids=["session-a_2"],
                session_ids=["session-a"],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "multi-session"}],
    )

    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["summary"]["metric_tier"] == "framework_supplementary"
    assert result["summary"]["provenance_granularity"] == "turn"

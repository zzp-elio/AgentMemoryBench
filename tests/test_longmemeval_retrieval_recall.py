"""LongMemEval 双粒度 artifact-only retrieval recall 测试。"""

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


def _write_run(
    tmp_path: Path,
    *,
    provenance_granularity: str | None,
    answer_prompts: list[dict[str, object]],
    private_labels: list[dict[str, object]],
    public_questions: list[dict[str, object]],
) -> tuple[ExperimentPaths, dict[str, object]]:
    """写入 LongMemEval recall 所需的最小 artifact 集合。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    method: dict[str, object] = {}
    if provenance_granularity is not None:
        method["provenance_granularity"] = provenance_granularity
    manifest: dict[str, object] = {
        "run_id": "run",
        "benchmark_name": "longmemeval",
        "method": method,
        "benchmark_policy": {"gold_evidence_contract_version": "v1"},
    }
    atomic_write_json(paths.manifest_path, manifest)
    atomic_write_jsonl(paths.answer_prompts_path, answer_prompts)
    atomic_write_jsonl(paths.evaluator_private_labels_path, private_labels)
    atomic_write_jsonl(paths.public_questions_path, public_questions)
    return paths, manifest


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
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("session-a:t1")],
            }
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
        provenance_granularity="session",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("session-a#occurrence_2:t4")],
            }
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
    assert result["summary"]["provenance_granularity"] == "session"


def test_official_corpus_alias_is_not_used_as_turn_match_key(tmp_path: Path) -> None:
    """只返回官方 corpus alias 时不得误判为公开 turn-id 命中。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("session-a_2")],
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

    result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    assert result["score_records"][0]["score"] == 0.0


def test_abstention_question_is_na_and_counted_separately(tmp_path: Path) -> None:
    """`_abs` 题应写 N/A record，并从 recall 均值与 scored count 排除。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q_abs_1",
                "conversation_id": "q_abs_1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [],
            },
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("session-a:t1")],
            },
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


def test_none_or_undeclared_provenance_returns_structured_na(
    tmp_path: Path,
) -> None:
    """无 provenance 能力时整个指标应为结构化 N/A。"""

    for value in ("none", None):
        paths, manifest = _write_run(
            tmp_path / str(value),
            provenance_granularity=value,
            answer_prompts=[],
            private_labels=[],
            public_questions=[],
        )
        result = LongMemEvalRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )
        assert result["summary"]["status"] == "n/a"
        assert result["score_records"] == []


def test_declared_provenance_missing_source_ids_fails_fast(tmp_path: Path) -> None:
    """声明 provenance 却缺 source_turn_ids 时必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [{"item_id": "i1", "content": "memory"}],
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
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("session-a:t1")],
            }
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

"""MemBench artifact-only retrieval recall 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.membench_recall import (
    MemBenchRetrievalRecallEvaluator,
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
    """写入 MemBench recall 所需的最小 artifact 集合。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    method: dict[str, object] = {}
    if provenance_granularity is not None:
        method["provenance_granularity"] = provenance_granularity
    manifest: dict[str, object] = {
        "run_id": "run",
        "benchmark_name": "membench",
        "method": method,
    }
    atomic_write_json(paths.manifest_path, manifest)
    atomic_write_jsonl(paths.answer_prompts_path, answer_prompts)
    atomic_write_jsonl(paths.evaluator_private_labels_path, private_labels)
    atomic_write_jsonl(paths.public_questions_path, public_questions)
    return paths, manifest


def _private_label(
    question_id: str,
    *,
    evidence: list[str],
    target_step_ids: list[int],
) -> dict[str, object]:
    """构造同时含公开 evidence 和官方 target_step_id 0 基原值的私有标签。"""

    return {
        "question_id": question_id,
        "gold_answer": "gold",
        "category": "highlevel",
        "evidence": evidence,
        "metadata": {
            "evidence": evidence,
            "target_step_id": target_step_ids,
        },
    }


def test_turn_provenance_matches_public_turn_ids_and_keeps_official_aliases(
    tmp_path: Path,
) -> None:
    """turn recall 应用公开 turn id 匹配，官方 0 基 target_step_id 留 metadata。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("membench-conv-1:t2")],
                "metadata": {"public_turn_count": 5},
            }
        ],
        private_labels=[
            _private_label(
                "q1",
                evidence=["membench-conv-1:t2", "membench-conv-1:t3"],
                target_step_ids=[1, 2],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    record = result["score_records"][0]
    # evidence 是公开 turn-id 空间（1 基）：target_step_id=[1,2] → ["2","3"]
    # retrieved 命中 "t2" → 1 hit / 2 evidence = 0.5
    assert record["score"] == pytest.approx(0.5)
    assert record["details"]["gold_evidence_turn_ids"] == [
        "membench-conv-1:t2",
        "membench-conv-1:t3",
    ]
    # 官方 0 基原值保留在 metadata
    assert record["details"]["target_step_id_original"] == [1, 2]


def test_session_provenance_is_na_because_membench_has_no_session_structure(
    tmp_path: Path,
) -> None:
    """MemBench 单 session，session 粒度声明应记结构化 N/A。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="session",
        answer_prompts=[],
        private_labels=[],
        public_questions=[],
    )

    result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    assert result["summary"]["status"] == "n/a"
    assert "no session structure" in result["summary"]["reason"]
    assert result["score_records"] == []


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
        result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
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
                "metadata": {},
            }
        ],
        private_labels=[
            _private_label(
                "q1",
                evidence=["membench-conv-1:t2"],
                target_step_ids=[1],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    with pytest.raises(ConfigurationError, match="source_turn_ids"):
        MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )


def test_declared_provenance_missing_evidence_fails_fast(tmp_path: Path) -> None:
    """benchmark 未提供 evidence 时必须 fail-fast，不能静默记零。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("membench-conv-1:t2")],
                "metadata": {},
            }
        ],
        private_labels=[
            {
                "question_id": "q1",
                "gold_answer": "gold",
                "metadata": {"target_step_id": [1]},
            }
        ],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    with pytest.raises(ConfigurationError, match="evidence"):
        MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )


def test_out_of_bounds_target_step_id_is_counted_but_does_not_crash(
    tmp_path: Path,
) -> None:
    """0 基越界 target_step_id（>= public_turn_count）应保留在 evidence 并记 unmatched-gold。

    全库恰 2 例（comparative/events tid=4，0-10k 和 100k 各 1）。evidence 保留，
    不阻断；summary 单独计数。
    """

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                # 检索到 turn 1（公开空间），但 evidence 含越界 "t5"（公开 turn_count=4）
                "retrieved_items": [_item("membench-conv-1:t1")],
                "metadata": {"public_turn_count": 4},
            }
        ],
        private_labels=[
            _private_label(
                "q1",
                evidence=["membench-conv-1:t1", "membench-conv-1:t5"],
                # 0 基下：1 命中 "t2" 越界（>=4 → 越界），1 是正常 target
                # 实际：evidence 是公开空间，含 "t1"（hit）和 "t5"（unmatched 越界）
                target_step_ids=[0, 4],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    record = result["score_records"][0]
    # 1 hit / 2 evidence = 0.5（"t5" 算 miss）
    assert record["score"] == pytest.approx(0.5)
    # 越界 id 单独记录
    assert record["details"]["out_of_bounds_target_step_ids"] == [4]
    assert record["details"]["gold_evidence_turn_ids"] == [
        "membench-conv-1:t1",
        "membench-conv-1:t5",
    ]
    summary = result["summary"]
    assert summary["status"] == "ok"
    assert summary["out_of_bounds_gold_total"] == 1
    assert summary["unmatched_gold_total"] == 1


def test_empty_evidence_scores_one_and_keeps_zero_unmatched(tmp_path: Path) -> None:
    """空 evidence（highlevel_rec 等 task_type）应记 score=1.0 且 unmatched 不增加。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("membench-conv-1:t1")],
                "metadata": {"public_turn_count": 4},
            }
        ],
        private_labels=[
            _private_label(
                "q1",
                evidence=[],
                target_step_ids=[],
            )
        ],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    record = result["score_records"][0]
    assert record["score"] == 1.0
    summary = result["summary"]
    assert summary["empty_evidence_question_count"] == 1
    assert summary["unmatched_gold_total"] == 0

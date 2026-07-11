"""BEAM artifact-only conditional recall 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.core import ConfigurationError, GoldAnswerInfo
from memory_benchmark.evaluators.beam_recall import BeamRetrievalRecallEvaluator
from memory_benchmark.storage import ExperimentPaths, atomic_write_jsonl
from memory_benchmark.storage.artifacts import evaluator_private_label_record


def _item(*source_ids: str) -> dict[str, object]:
    """构造带公开 turn provenance 的 retrieval item。"""

    return {"source_turn_ids": list(source_ids), "content": "memory"}


def _gold(
    question_id: str,
    evidence: list[str],
    *,
    unmatched: int = 0,
    ambiguous: int = 0,
) -> GoldAnswerInfo:
    """构造 adapter 已映射的 evaluator-private gold。"""

    return GoldAnswerInfo(
        question_id=question_id,
        answer="gold",
        metadata={
            "evidence_turn_ids": evidence,
            "source_chat_ids": [1],
            "unmatched_gold_id_count": unmatched,
            "ambiguous_gold_id_count": ambiguous,
        },
    )


def _run(
    tmp_path: Path,
    *,
    provenance: str | None,
    golds: list[GoldAnswerInfo],
    answers: list[dict[str, object]],
    categories: list[str],
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
    method = {} if provenance is None else {"provenance_granularity": provenance}
    return BeamRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths, manifest={"method": method}
    )


def test_turn_recall_matches_public_ids_and_any_ambiguous_position(tmp_path: Path) -> None:
    """公开 turn id 任一歧义映射位置命中即计 hit。"""

    result = _run(
        tmp_path,
        provenance="turn",
        golds=[_gold("q1", ["s1:t1", "s2:t1"], ambiguous=1)],
        answers=[
            {
                "question_id": "q1",
                "conversation_id": "c1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("s2:t1")],
            }
        ],
        categories=["knowledge_update"],
    )
    assert result["score_records"][0]["score"] == 0.5
    assert result["summary"]["ambiguous_gold_id_count"] == 1


def test_empty_evidence_is_na_and_unmatched_is_counted(tmp_path: Path) -> None:
    """abstention 与不可解 ``--`` gold 都不计 0 分并单独计数。"""

    result = _run(
        tmp_path,
        provenance="turn",
        golds=[_gold("q1", [], unmatched=1)],
        answers=[{"question_id": "q1", "conversation_id": "c1"}],
        categories=["event_ordering"],
    )
    assert result["score_records"][0]["status"] == "n/a"
    assert result["summary"]["abstention_question_count"] == 1
    assert result["summary"]["unmatched_gold_id_count"] == 1


@pytest.mark.parametrize("provenance", [None, "none"])
def test_missing_provenance_returns_structured_na(
    tmp_path: Path, provenance: str | None
) -> None:
    """未声明 provenance 时不读 artifact，直接返回 N/A。"""

    result = _run(tmp_path, provenance=provenance, golds=[], answers=[], categories=[])
    assert result["summary"]["status"] == "n/a"


def test_declared_turn_provenance_missing_source_ids_fails_fast(tmp_path: Path) -> None:
    """声明 turn provenance 却缺 source ids 必须 fail-fast。"""

    with pytest.raises(ConfigurationError, match="source_turn_ids"):
        _run(
            tmp_path,
            provenance="turn",
            golds=[_gold("q1", ["s1:t1"])],
            answers=[
                {
                    "question_id": "q1",
                    "retrieval_query_top_k": 1,
                    "retrieved_items": [{"content": "memory"}],
                }
            ],
            categories=["summarization"],
        )


def test_session_provenance_is_rejected(tmp_path: Path) -> None:
    """BEAM 只有 turn evidence，session provenance 不得静默评分。"""

    with pytest.raises(ConfigurationError, match="expected 'none' or 'turn'"):
        _run(tmp_path, provenance="session", golds=[], answers=[], categories=[])

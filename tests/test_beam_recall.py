"""BEAM artifact-only conditional recall 测试。"""

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


V1_MANIFEST_BENCHMARK_POLICY = {"gold_evidence_contract_version": "v1"}


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
    manifest: dict[str, object] = {"method": method}
    manifest["benchmark_policy"] = V1_MANIFEST_BENCHMARK_POLICY
    return BeamRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest,
    )


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
        provenance="turn",
        golds=[gold],
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
    assert result["score_records"][0]["score"] == 1.0
    assert result["score_records"][0]["details"]["gold_unit_ids"] == ["raw-7"]


def test_empty_evidence_is_na(tmp_path: Path) -> None:
    """真实空 group（abstention）应为 N/A，不进入 scored 分母。"""

    result = _run(
        tmp_path,
        provenance="turn",
        golds=[_gold("q1", [])],
        answers=[{"question_id": "q1", "conversation_id": "c1"}],
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
        provenance="turn",
        golds=[gold],
        answers=[
            {
                "question_id": "q1",
                "conversation_id": "c1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [],
            }
        ],
        categories=["event_ordering"],
    )

    assert result["score_records"][0]["status"] == "ok"
    assert result["score_records"][0]["score"] == 0.0
    assert result["score_records"][0]["details"]["unmatched_gold_unit_count"] == 1
    assert result["summary"]["abstention_question_count"] == 0
    assert result["summary"]["unmatched_gold_id_count"] == 1


@pytest.mark.parametrize("provenance", [None, "none"])
def test_missing_provenance_returns_structured_na(
    tmp_path: Path, provenance: str | None
) -> None:
    """未声明 provenance 时不读 artifact，直接返回 N/A。"""

    result = _run(tmp_path, provenance=provenance, golds=[], answers=[], categories=[])
    assert result["summary"]["status"] == "n/a"


@pytest.mark.parametrize(
    "evaluator_type",
    [
        BeamRetrievalRecallEvaluator,
        LoCoMoRetrievalRecallEvaluator,
        LongMemEvalRetrievalRecallEvaluator,
        LongMemEvalRetrievalRankEvaluator,
        MemBenchRetrievalRecallEvaluator,
    ],
)
@pytest.mark.parametrize(
    "benchmark_policy",
    [None, {"gold_evidence_contract_version": "bogus"}],
    ids=["missing", "bogus"],
)
def test_group_evaluators_validate_manifest_before_provenance_na(
    tmp_path: Path,
    evaluator_type: type,
    benchmark_policy: dict[str, object] | None,
) -> None:
    """旧/非法 manifest 不能被 method provenance=N/A 的早退分支掩盖。"""

    manifest: dict[str, object] = {
        "method": {"provenance_granularity": "none"},
    }
    if benchmark_policy is not None:
        manifest["benchmark_policy"] = benchmark_policy

    with pytest.raises(ConfigurationError, match="gold evidence contract|expected 'v1'"):
        evaluator_type().evaluate_run_artifacts(
            paths=ExperimentPaths.create(tmp_path / evaluator_type.__name__),
            manifest=manifest,
        )


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

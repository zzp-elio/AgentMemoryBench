"""MemBench artifact-only retrieval recall 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.core import ConfigurationError, GoldAnswerInfo
from memory_benchmark.evaluators.membench_recall import (
    MemBenchRetrievalRecallEvaluator,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    evaluator_private_label_record,
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
    evidence: list[str],
    target_step_ids: list[int],
    oob_step_ids: tuple[int, ...] = (),
) -> dict[str, object]:
    """通过**真实生产序列化函数**构造私有标签。

    gold evidence contract v1: group 只由稳定去重后的 target_step_ids 构造，
    这里用退化 singleton child（生产 adapter 的 1 基公开 turn id
    `str(step_id + 1)`，对应 ThirdAgent string step 的真实形态）覆盖通用
    evaluator 计分逻辑；FirstAgent 真实 2-child pair group 的 any-of 语义见
    `test_multi_child_pair_group_any_of_hit_on_either_side_counts_once`。legacy
    evidence 只保留历史字段，长度不得截断权威 group。oob_step_ids 中的 0 基
    target 记 unmatched（与真实 adapter 一致）。
    """

    from memory_benchmark.core import GoldEvidenceGroup, GoldEvidenceGroupSet

    oob_set = set(oob_step_ids)
    groups = tuple(
        GoldEvidenceGroup(
            unit_id=str(step_id),
            child_ids=() if step_id in oob_set else (str(step_id + 1),),
            mapping_status="unmatched" if step_id in oob_set else "mapped",
        )
        for step_id in dict.fromkeys(target_step_ids)
    )
    gold = GoldAnswerInfo(
        question_id=question_id,
        answer="gold",
        evidence=evidence,
        metadata={"target_step_id": target_step_ids},
        gold_evidence_contract_version="v1",
        evidence_group_sets=(
            GoldEvidenceGroupSet(
                provenance_granularity="turn",
                unit_kind="membench_step",
                groups=groups,
            ),
        ),
    )
    return evaluator_private_label_record(gold, category="highlevel")


def test_turn_provenance_matches_public_turn_ids_and_keeps_official_aliases(
    tmp_path: Path,
) -> None:
    """公开 id 计分只由 target groups 决定，不受 legacy evidence 长度截断。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("2")],
                "metadata": {},
            }
        ],
        private_labels=[
            _private_label(
                "q1",
                evidence=["legacy-only"],
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
    assert record["score"] == pytest.approx(0.5)
    assert record["details"]["gold_unit_ids"] == ["1", "2"]


def test_multi_child_pair_group_any_of_hit_on_either_side_counts_once(
    tmp_path: Path,
) -> None:
    """真实 FirstAgent pair group（2 个 child）：命中 user-only、assistant-only

    或两侧都命中，同一 group 都只记 1 次；不得用两个 singleton 冒充 pair，也
    不得因为一个 group 有两个 child 就把它算成两个命中或半个命中。分母恒为
    2 个官方 step，不因 child 数变化。
    """

    from memory_benchmark.core import GoldEvidenceGroup, GoldEvidenceGroupSet

    def _pair_private_label(question_id: str) -> dict[str, object]:
        groups = (
            GoldEvidenceGroup(
                unit_id="0",
                child_ids=("1:user", "1:assistant"),
                mapping_status="mapped",
            ),
            GoldEvidenceGroup(
                unit_id="1",
                child_ids=("2:user", "2:assistant"),
                mapping_status="mapped",
            ),
        )
        gold = GoldAnswerInfo(
            question_id=question_id,
            answer="gold",
            evidence=["1", "2"],
            metadata={"target_step_id": [0, 1]},
            gold_evidence_contract_version="v1",
            evidence_group_sets=(
                GoldEvidenceGroupSet(
                    provenance_granularity="turn",
                    unit_kind="membench_step",
                    groups=groups,
                ),
            ),
        )
        return evaluator_private_label_record(gold, category="highlevel")

    cases = [
        (["1:user"], 0.5),  # 只命中 step0 的 user 侧：该 group 记满分
        (["1:assistant"], 0.5),  # 只命中 step0 的 assistant 侧：同上
        (["1:user", "1:assistant"], 0.5),  # 两侧都命中：同一 group 仍只计 1 次
        (["2:user", "2:assistant"], 0.5),  # 命中另一 group 的两侧
        (["9:user"], 0.0),  # 命中不相干 id：两个 group 都不中
    ]
    for index, (hit_ids, expected_score) in enumerate(cases):
        paths, manifest = _write_run(
            tmp_path / f"case{index}",
            provenance_granularity="turn",
            answer_prompts=[
                {
                    "question_id": "q1",
                    "conversation_id": "q1",
                    "retrieval_query_top_k": 1,
                    "retrieved_items": [_item(*hit_ids)],
                    "metadata": {},
                }
            ],
            private_labels=[_pair_private_label("q1")],
            public_questions=[{"question_id": "q1", "category": "highlevel"}],
        )
        result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )
        record = result["score_records"][0]
        assert record["score"] == pytest.approx(expected_score), (hit_ids, record)
        assert record["details"]["gold_unit_ids"] == ["0", "1"]


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
                evidence=["2"],
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
                "retrieved_items": [_item("2")],
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

    with pytest.raises(ConfigurationError, match="gold_evidence_contract_version"):
        MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )


def test_out_of_bounds_target_step_id_is_counted_but_does_not_crash(
    tmp_path: Path,
) -> None:
    """0 基越界 target_step_id 应保留在分母并记 unmatched-gold，不阻断评分。

    全库恰 2 例（comparative/events tid=4，0-10k 和 100k 各 1）。越界诊断权威
    来源是 gold group 自身的 `mapping_status="unmatched"`（不再读取 answer
    artifact 的 `public_turn_count` 启发式——拆分后 canonical turn 数已不等于
    源 step 数，该字段也从未被生产 answer prompt 写入）。
    """

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                # 检索到公开 turn "1"，但官方 step 4 越界。
                "retrieved_items": [_item("1")],
                "metadata": {},
            }
        ],
        private_labels=[
            _private_label(
                "q1",
                evidence=["1", "5"],
                target_step_ids=[0, 4],
                oob_step_ids=(4,),
            )
        ],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    record = result["score_records"][0]
    # 1 hit / 2 gold unit = 0.5；group unit_id=0 mapped→hit, unit_id=4 OOB→unmatched→miss
    assert record["score"] == pytest.approx(0.5)
    # 越界 id 直接从 unmatched group 的 unit_id 还原
    assert record["details"]["out_of_bounds_target_step_ids"] == [4]
    assert record["details"]["gold_unit_ids"] == ["0", "4"]
    assert record["details"]["unmatched_gold_unit_count"] == 1
    summary = result["summary"]
    assert summary["status"] == "ok"
    assert summary["out_of_bounds_gold_total"] == 1
    assert summary["unmatched_gold_total"] == 1


def test_empty_evidence_is_na_and_keeps_zero_unmatched(tmp_path: Path) -> None:
    """v1 下空 target 产生空 groups → evaluator 记 N/A，不再是旧框架错误记 1.0。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "q1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("1")],
                "metadata": {},
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
    assert record["status"] == "n/a"
    assert record["score"] is None
    assert result["summary"]["empty_gold_question_count"] == 1

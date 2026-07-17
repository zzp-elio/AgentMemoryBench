"""MemBench artifact-only retrieval recall 测试。

RetrievalEvidence M1 后，MemBench recall 只接受 turn 粒度 gold view
（`{"turn"}`）：逐题 evidence 若 semantic provenance valid 但 granularity 为
`session`（MemBench 单 session，没有可召回的 session 结构），由共享
`decide_retrieval_eligibility` 统一导出 `n_a`/`gold_granularity_mismatch`，
不再由本 evaluator 手写"MemBench 没有 session 结构"的专用分支。
"""

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


def _write_run(
    tmp_path: Path,
    *,
    answer_prompts: list[dict[str, object]],
    private_labels: list[dict[str, object]],
    public_questions: list[dict[str, object]],
    retrieval_evidence_contract_version: str | None = "v1",
) -> tuple[ExperimentPaths, dict[str, object]]:
    """写入 MemBench recall 所需的最小 artifact 集合。

    默认 manifest 同时声明 gold evidence contract v1 与 retrieval evidence
    contract v1，模拟真实 registered v1 run。
    """

    paths = ExperimentPaths.create(tmp_path / "run")
    method: dict[str, object] = {}
    if retrieval_evidence_contract_version is not None:
        method["retrieval_evidence_contract_version"] = retrieval_evidence_contract_version
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
        "metadata": {},
    }


def _private_label(
    question_id: str,
    *,
    evidence: list[str],
    target_step_ids: list[int],
    oob_step_ids: tuple[int, ...] = (),
) -> dict[str, object]:
    """通过**真实生产序列化函数**构造私有标签。

    gold evidence contract v1: group 只由稳定去重后的 target_step_ids 构造，
    这里用退化 singleton child（生产 adapter 中 ThirdAgent string step 的
    canonical child id 恰为 `str(step_id + 1)`）覆盖通用
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
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=_valid_evidence("turn"), top_k=1, retrieved_items=[_item("2")]
            )
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
    3 个官方 step，不因 child 数变化；只命中任一 step 的一侧或两侧都只能得
    1/3，绝不能按 6 个 child 算成 1/6。
    """

    from memory_benchmark.core import GoldEvidenceGroup, GoldEvidenceGroupSet

    def _pair_private_label(question_id: str) -> dict[str, object]:
        """构造含三个 FirstAgent pair-step group 的真实私有标签。"""

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
            GoldEvidenceGroup(
                unit_id="2",
                child_ids=("3:user", "3:assistant"),
                mapping_status="mapped",
            ),
        )
        gold = GoldAnswerInfo(
            question_id=question_id,
            answer="gold",
            evidence=["1", "2", "3"],
            metadata={"target_step_id": [0, 1, 2]},
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
        (["1:user"], 1 / 3),  # 只命中 step0 的 user 侧：该 group 记满分
        (["1:assistant"], 1 / 3),  # 只命中 step0 的 assistant 侧：同上
        (["1:user", "1:assistant"], 1 / 3),  # 两侧都命中：同一 group 仍只计 1 次
        (["2:user", "2:assistant"], 1 / 3),  # 命中另一 group 的两侧
        (["3:assistant"], 1 / 3),  # 第三个 step 的单侧命中仍按 group 计分
        (["9:user"], 0.0),  # 命中不相干 id：三个 group 都不中
    ]
    for index, (hit_ids, expected_score) in enumerate(cases):
        paths, manifest = _write_run(
            tmp_path / f"case{index}",
            answer_prompts=[
                _answer_prompt(
                    "q1",
                    evidence=_valid_evidence("turn"),
                    top_k=1,
                    retrieved_items=[_item(*hit_ids)],
                )
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
        assert record["details"]["gold_unit_ids"] == ["0", "1", "2"]


def test_session_decision_is_gold_granularity_mismatch_na(tmp_path: Path) -> None:
    """MemBench 只接受 turn 粒度：session 逐题 decision 应导出 gold_granularity_mismatch N/A。

    不再是 evaluator 手写的"MemBench 没有 session 结构"专用分支，而是共享
    `decide_retrieval_eligibility` 对不在允许集合内的粒度的通用处理——同一
    行为也适用于 BEAM。
    """

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt("q1", evidence=_valid_evidence("session"), top_k=1, retrieved_items=[])
        ],
        private_labels=[_private_label("q1", evidence=["1"], target_step_ids=[0])],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    record = result["score_records"][0]
    assert record["score"] is None
    assert record["status"] == "n/a"
    assert record["reason_code"] == "gold_granularity_mismatch"
    assert result["summary"]["scored_question_count"] == 0


def test_semantic_provenance_na_returns_structured_na(tmp_path: Path) -> None:
    """provider 逐题 semantic provenance=n_a 时该题应为结构化 N/A。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[_answer_prompt("q1", evidence=_na_evidence(), top_k=1)],
        private_labels=[_private_label("q1", evidence=["1"], target_step_ids=[0])],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )
    assert result["score_records"][0]["score"] is None
    assert result["summary"]["status"] == "n/a"


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
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=_valid_evidence("turn"), top_k=1, retrieved_items=[_item("2")]
            )
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


def test_missing_retrieval_evidence_contract_version_fails_fast(tmp_path: Path) -> None:
    """manifest 缺 retrieval_evidence_contract_version 必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        retrieval_evidence_contract_version=None,
        answer_prompts=[],
        private_labels=[],
        public_questions=[],
    )

    with pytest.raises(ConfigurationError, match="retrieval_evidence_contract_version"):
        MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


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
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                # 检索到 canonical child "1"，但官方 step 4 越界。
                retrieved_items=[_item("1")],
            )
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
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=_valid_evidence("turn"), top_k=1, retrieved_items=[_item("1")]
            )
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


def test_stable_ranking_pending_does_not_block_recall_scoring(tmp_path: Path) -> None:
    """Recall 不要求 stable ranking：stable_ranking=pending 时仍应正常计分。"""

    evidence = _valid_evidence("turn")
    assert evidence["stable_ranking"]["status"] == "pending"
    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt("q1", evidence=evidence, top_k=1, retrieved_items=[_item("1")])
        ],
        private_labels=[_private_label("q1", evidence=["1"], target_step_ids=[0])],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["score_records"][0]["score"] == 1.0


def test_summary_reports_metric_tier_and_representative_granularity(
    tmp_path: Path,
) -> None:
    """summary 必须标 metric_tier，并为存量消费者保留代表性 provenance_granularity。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=_valid_evidence("turn"), top_k=1, retrieved_items=[_item("1")]
            )
        ],
        private_labels=[_private_label("q1", evidence=["1"], target_step_ids=[0])],
        public_questions=[{"question_id": "q1", "category": "highlevel"}],
    )

    result = MemBenchRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["summary"]["metric_tier"] == "framework_supplementary"
    assert result["summary"]["provenance_granularity"] == "turn"

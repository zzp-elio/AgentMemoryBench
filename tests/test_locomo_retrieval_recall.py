"""测试 LoCoMo artifact-only retrieval recall evaluator。

本文件只从手工构造的 run 目录 artifact 出发（manifest + answer prompts +
private labels），验证 `LoCoMoRetrievalRecallEvaluator` 是否忠实实现官方
`task_eval/evaluation.py:189-241` 的条件式 recall 公式，不构造真实 provider、
不调用 API。

RetrievalEvidence M1 后，manifest 必须同时携带 gold evidence contract v1
（`benchmark_policy`）与 retrieval evidence contract v1
（`method.retrieval_evidence_contract_version`），每条 answer prompt 记录必须
携带逐题 `retrieval_evidence`；资格（valid/n_a/pending）由逐题证据派生，旧
run 级 `method.provenance_granularity` 字段不再参与任何判定，仅作历史审计。
本文件同时是 `evaluators/retrieval_evidence.py` 共享 preflight/裁决逻辑的
主要覆盖点（该模块没有独立测试文件，按 `gold_evidence_groups.py` 的既有
惯例只经 evaluator 间接测试）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.evaluators.locomo_recall import LoCoMoRetrievalRecallEvaluator
from memory_benchmark.storage import ExperimentPaths, atomic_write_json, atomic_write_jsonl


pytestmark = pytest.mark.unit


def _write_run(
    tmp_path: Path,
    *,
    answer_prompts: list[dict],
    private_labels: list[dict],
    public_questions: list[dict],
    retrieval_evidence_contract_version: str | None = "v1",
    legacy_provenance_granularity: str | None = None,
    include_benchmark_policy: bool = True,
) -> tuple[ExperimentPaths, dict]:
    """构造一个最小可用的 run 目录，写入 artifact-only recall 所需文件。

    默认 manifest 同时声明 gold evidence contract v1 与 retrieval evidence
    contract v1，模拟真实 registered v1 run。`legacy_provenance_granularity`
    仅用于验证旧 run 级字段不再参与任何资格判定或 fail-fast。

    输出:
        tuple: `(paths, manifest)`；manifest 与磁盘上写入的内容一致，供
        `evaluate_run_artifacts(manifest=...)` 直接复用，避免测试里出现磁盘
        内容和调用参数不一致的情况。
    """

    paths = ExperimentPaths.create(tmp_path / "run-1")
    method_manifest: dict = {}
    if legacy_provenance_granularity is not None:
        method_manifest["provenance_granularity"] = legacy_provenance_granularity
    if retrieval_evidence_contract_version is not None:
        method_manifest["retrieval_evidence_contract_version"] = (
            retrieval_evidence_contract_version
        )
    manifest: dict = {
        "run_id": "run-1",
        "benchmark_name": "locomo",
        "method": method_manifest,
    }
    if include_benchmark_policy:
        manifest["benchmark_policy"] = {"gold_evidence_contract_version": "v1"}
    atomic_write_json(paths.manifest_path, manifest)
    atomic_write_jsonl(paths.answer_prompts_path, answer_prompts)
    atomic_write_jsonl(paths.evaluator_private_labels_path, private_labels)
    atomic_write_jsonl(paths.public_questions_path, public_questions)
    return paths, manifest


def _item(item_id: str, source_turn_ids: list[str]) -> dict:
    """构造一条 retrieved item 字典（模拟 `asdict(RetrievedItem)` 输出）。"""

    return {
        "item_id": item_id,
        "content": "memory",
        "score": 1.0,
        "timestamp": None,
        "source_turn_ids": source_turn_ids,
        "metadata": {},
    }


def _assertion(status: str, *, reason_code: str | None = None, reason: str | None = None) -> dict:
    """构造一条序列化后的 `EvidenceAssertion`（模拟 `asdict()` 输出）。"""

    return {"status": status, "reason_code": reason_code, "reason": reason}


def _valid_evidence(granularity: str = "turn") -> dict:
    """构造 `semantic_provenance=valid` 的逐题 evidence；`stable_ranking` 固定 pending。

    Recall evaluator 不要求 stable ranking，因此 pending 不应阻断计分——这也是
    本文件验证的强反例之一。
    """

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


def _answer_prompt(
    question_id: str,
    *,
    evidence: dict | None,
    top_k: int | None = None,
    retrieved_items: list[dict] | None = None,
    conversation_id: str = "conv-1",
    omit_evidence_key: bool = False,
) -> dict:
    """构造一条 answer prompt artifact 记录。

    `omit_evidence_key=True` 时整个 `retrieval_evidence` key 都不写入，
    用于区分"key 缺失"与"值为 null"两种 preflight 强反例（行为应等价）。
    """

    record: dict = {
        "question_id": question_id,
        "conversation_id": conversation_id,
        "retrieval_query_top_k": top_k,
        "retrieved_items": retrieved_items,
    }
    if not omit_evidence_key:
        record["retrieval_evidence"] = evidence
    return record


def _label(qid: str, dia_ids: list[str]) -> dict:
    """构造含 gold evidence contract v1 group sets 的 locomo private label。

    每个 dia_id 一个 singleton mapped group（D<n>:<n> 格式是非歧义映射），
    空列表产生空 turn groups（官方记 1.0 的行为保持不变）。
    两组 view：turn（locomo_utterance）+ session（locomo_utterance_session_projection），
    child 为 D<n> session 前缀。
    """

    groups = [
        {
            "unit_id": dia_id,
            "child_ids": [dia_id],
            "mapping_status": "mapped",
        }
        for dia_id in dia_ids
    ]
    session_groups = [
        {
            "unit_id": dia_id,
            "child_ids": [dia_id.partition(":")[0]],
            "mapping_status": "mapped",
        }
        for dia_id in dia_ids
    ]
    return {
        "question_id": qid,
        "answer": "gold",
        "evidence": dia_ids,
        "gold_evidence_contract_version": "v1",
        "evidence_group_sets": [
            {
                "provenance_granularity": "turn",
                "unit_kind": "locomo_utterance",
                "groups": groups,
            },
            {
                "provenance_granularity": "session",
                "unit_kind": "locomo_utterance_session_projection",
                "groups": session_groups,
            },
        ],
    }


def test_turn_provenance_computes_official_hit_fraction(tmp_path: Path) -> None:
    """turn provenance 应按官方公式计算 evidence 命中比例。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=2,
                retrieved_items=[
                    _item("i1", ["D1:1"]),
                    _item("i2", ["D1:2"]),
                    _item("i3", ["D1:3"]),
                ],
            )
        ],
        private_labels=[_label("q1", ["D1:1", "D1:2"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )

    assert result["metric_name"] == "locomo_recall"
    assert result["score_records"][0]["score"] == 1.0
    assert result["score_records"][0]["status"] == "ok"
    assert result["score_records"][0]["retrieval_evidence_status"] == "valid"
    assert result["summary"]["status"] == "ok"


def test_turn_provenance_partial_hit_returns_fraction_not_zero_or_one(
    tmp_path: Path,
) -> None:
    """只命中部分 evidence 时应返回介于 0 和 1 之间的比例，而非二值判断。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:1"])],
            )
        ],
        private_labels=[_label("q1", ["D1:1", "D1:2"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["score_records"][0]["score"] == pytest.approx(0.5)


def test_turn_provenance_only_considers_items_within_requested_top_k(
    tmp_path: Path,
) -> None:
    """只取有序 retrieved_items[:top_k]，超出 top_k 的命中不计入。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[
                    _item("i1", ["D1:9"]),
                    _item("i2", ["D1:1"]),
                ],
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    # top_k=1 只看第一条 item（D1:9），D1:1 排在第二位，超出预算不计入。
    assert result["score_records"][0]["score"] == 0.0


def test_session_provenance_aggregates_dia_id_to_session_prefix(tmp_path: Path) -> None:
    """session provenance 应把 source/evidence 的 dia_id 都聚合为 D<n> 再匹配。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("session"),
                top_k=1,
                # 检索命中的 turn 是 D1:9（同一 session，但不是 evidence 原 turn）。
                retrieved_items=[_item("i1", ["D1:9"])],
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["score_records"][0]["score"] == 1.0
    assert result["score_records"][0]["provenance_granularity"] == "session"


def test_semantic_provenance_na_produces_na_record_not_whole_run_na(
    tmp_path: Path,
) -> None:
    """单题 semantic provenance=n_a 只应影响该题，产生带 reason 的 N/A record。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_na_evidence("beam_style_gap", "coarser ingest batch than gold"),
                top_k=10,
                retrieved_items=None,
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    record = result["score_records"][0]
    assert record["score"] is None
    assert record["status"] == "n/a"
    assert record["retrieval_evidence_status"] == "n_a"
    assert record["reason_code"] == "beam_style_gap"
    assert record["reason"] == "coarser ingest batch than gold"
    assert result["total_questions"] == 0
    assert result["summary"]["status"] == "n/a"
    assert result["summary"]["scored_question_count"] == 0
    assert result["summary"]["retrieval_evidence_status_counts"] == {"n_a": 1}
    assert result["summary"]["retrieval_evidence_reason_code_counts"] == {
        "beam_style_gap": 1
    }


def test_na_decision_does_not_re_validate_retrieved_items_lineage(tmp_path: Path) -> None:
    """n_a/pending 不因 items 没 lineage 被二次报错：即使 items 形状本身非法也不检查。

    这里 `retrieved_items` 携带一个非空 item 却缺 `source_turn_ids`——如果
    decision 是 valid，这会在字段校验阶段 fail-fast；但 decision 是 n_a 时，
    评分循环根本不会走到那段校验代码，必须正常产出 n_a record 而不是报错。
    """

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_na_evidence(),
                top_k=1,
                retrieved_items=[{"item_id": "i1", "content": "memory"}],
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    record = result["score_records"][0]
    assert record["score"] is None
    assert record["status"] == "n/a"


def test_semantic_provenance_pending_produces_pending_summary_when_nothing_scored(
    tmp_path: Path,
) -> None:
    """全部题 pending 时 summary 应为 pending，而不是被误判成 n/a。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt("q1", evidence=_pending_evidence(), top_k=10, retrieved_items=None)
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    record = result["score_records"][0]
    assert record["score"] is None
    assert record["status"] == "pending"
    assert record["retrieval_evidence_status"] == "pending"
    assert result["summary"]["status"] == "pending"
    assert result["summary"]["scored_question_count"] == 0


def test_mixed_valid_na_pending_questions_in_one_run(tmp_path: Path) -> None:
    """同一 run 混合 valid/n_a/pending：只有 valid 进入均值，其余各自保留原因。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q-valid",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:1"])],
            ),
            _answer_prompt(
                "q-na",
                evidence=_na_evidence(),
                top_k=1,
                retrieved_items=None,
            ),
            _answer_prompt(
                "q-pending",
                evidence=_pending_evidence(),
                top_k=1,
                retrieved_items=None,
            ),
        ],
        private_labels=[
            _label("q-valid", ["D1:1"]),
            _label("q-na", ["D1:1"]),
            _label("q-pending", ["D1:1"]),
        ],
        public_questions=[
            {"question_id": "q-valid", "category": "4"},
            {"question_id": "q-na", "category": "4"},
            {"question_id": "q-pending", "category": "4"},
        ],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["mean_score"] == 1.0
    assert result["total_questions"] == 1
    assert result["summary"]["status"] == "ok"
    assert result["summary"]["scored_question_count"] == 1
    counts = result["summary"]["retrieval_evidence_status_counts"]
    assert counts == {"valid": 1, "n_a": 1, "pending": 1}


def test_empty_run_returns_structured_na(tmp_path: Path) -> None:
    """没有任何问题的 run 应自然产生结构化 N/A，无需专门的整跑 N/A 分支。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[],
        private_labels=[],
        public_questions=[],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )
    assert result["summary"]["status"] == "n/a"
    assert result["total_questions"] == 0
    assert result["score_records"] == []


def test_legacy_manifest_granularity_field_does_not_participate_in_eligibility(
    tmp_path: Path,
) -> None:
    """旧 run 级 provenance_granularity 故意写与逐题相反的值，逐题 v1 仍决定资格与 view。

    manifest 声明 legacy 字段为完全非法值 `"paragraph"`（旧代码会因此立即
    fail-fast），但逐题 evidence 才是唯一事实源：turn provenance 逐题合法即
    正常计分，旧字段必须保持只读、不参与任何判定。
    """

    paths, manifest = _write_run(
        tmp_path,
        legacy_provenance_granularity="paragraph",
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:1"])],
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["score_records"][0]["score"] == 1.0
    assert result["summary"]["status"] == "ok"


def test_legacy_manifest_granularity_field_opposite_legal_value_still_ignored(
    tmp_path: Path,
) -> None:
    """旧字段写与逐题相反的合法值（session vs 逐题 turn），仍以逐题为准选 view。

    与上一测试的非法值反例互补：这里旧字段是完全合法但错误的 granularity，
    验证的不是"旧字段会崩"，而是"旧字段即使合法也不会被读取来选 gold view"。
    错误地读了旧字段会选中 session view 并因该 view 没有匹配的 evidence 而
    得到不同分数；本测试锁定 turn view 的真实计分结果。
    """

    paths, manifest = _write_run(
        tmp_path,
        legacy_provenance_granularity="session",
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:9"])],
            )
        ],
        # turn view: D1:9 不命中 D1:1；session view 会把两者都聚合成 D1 命中。
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["score_records"][0]["score"] == 0.0
    assert result["score_records"][0]["provenance_granularity"] == "turn"


def test_illegal_provenance_granularity_in_evidence_fails_fast_at_preflight(
    tmp_path: Path,
) -> None:
    """逐题 evidence 里非法 granularity 值必须在 preflight 阶段 fail-fast。"""

    bad_evidence = _valid_evidence("turn")
    bad_evidence["provenance_granularity"] = "paragraph"
    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=bad_evidence, top_k=1, retrieved_items=[_item("i1", ["D1:1"])]
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="q1"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_declared_turn_provenance_missing_top_k_fails_fast(tmp_path: Path) -> None:
    """decision valid 却缺 retrieval_query_top_k 必须 fail-fast，不能静默降级。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=_valid_evidence("turn"), retrieved_items=[_item("i1", ["D1:1"])]
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="retrieval_query_top_k"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_declared_turn_provenance_missing_retrieved_items_fails_fast(
    tmp_path: Path,
) -> None:
    """decision valid 却缺 retrieved_items 必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt("q1", evidence=_valid_evidence("turn"), top_k=10)
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="retrieved_items"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_declared_turn_provenance_missing_source_turn_ids_fails_fast(
    tmp_path: Path,
) -> None:
    """decision valid 却缺 source_turn_ids 字段必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[
                    {"item_id": "i1", "content": "memory", "score": 1.0, "timestamp": None}
                ],
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="source_turn_ids"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_declared_turn_provenance_empty_source_turn_ids_fails_fast(
    tmp_path: Path,
) -> None:
    """decision valid 命中的 item 不能用空 source_turn_ids 冒充可追溯（真实 item 缺 lineage）。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=_valid_evidence("turn"), top_k=1, retrieved_items=[_item("i1", [])]
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="empty source_turn_ids"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )


def test_valid_decision_with_empty_retrieved_items_list_is_zero_hit_not_fail_fast(
    tmp_path: Path,
) -> None:
    """真实 retrieved_items=[] 是合法 0-hit，不是 lineage 缺失，不得 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=_valid_evidence("turn"), top_k=5, retrieved_items=[]
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    record = result["score_records"][0]
    assert record["status"] == "ok"
    assert record["score"] == 0.0


def test_answer_prompt_and_private_label_question_ids_must_match(
    tmp_path: Path,
) -> None:
    """artifact ID 不一致必须 fail-fast，不能静默缩小 recall 分母。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q-prompt",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:1"])],
            )
        ],
        private_labels=[_label("q-private", ["D1:1"])],
        public_questions=[{"question_id": "q-prompt", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="question IDs"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )


def test_empty_evidence_scores_one_and_is_reported_separately(tmp_path: Path) -> None:
    """官方实现对空 evidence 记 1.0，同时必须单独报告数量和 non-empty 均值。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q-empty",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:9"])],
            ),
            _answer_prompt(
                "q-miss",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:9"])],
            ),
        ],
        private_labels=[_label("q-empty", []), _label("q-miss", ["D1:1"])],
        public_questions=[
            {"question_id": "q-empty", "category": "3"},
            {"question_id": "q-miss", "category": "4"},
        ],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    scores_by_id = {
        record["question_id"]: record["score"] for record in result["score_records"]
    }
    assert scores_by_id["q-empty"] == 1.0
    assert scores_by_id["q-miss"] == 0.0
    assert result["summary"]["empty_evidence_question_count"] == 1
    assert result["summary"]["non_empty_evidence_mean_recall_at_requested_k"] == 0.0
    # overall 必须包含空 evidence 的 1.0（官方行为），因此 overall > non-empty 均值。
    assert result["summary"]["overall_mean_recall_at_requested_k"] == pytest.approx(0.5)


def test_summary_reports_by_category_and_top_k_distribution(tmp_path: Path) -> None:
    """summary 必须给出 overall、by-category、scored count 和 top-k 分布。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=5,
                retrieved_items=[_item("i1", ["D1:1"])],
            ),
            _answer_prompt(
                "q2",
                evidence=_valid_evidence("turn"),
                top_k=10,
                retrieved_items=[_item("i1", ["D1:2"])],
            ),
        ],
        private_labels=[_label("q1", ["D1:1"]), _label("q2", ["D1:2"])],
        public_questions=[
            {"question_id": "q1", "category": "4"},
            {"question_id": "q2", "category": "1"},
        ],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["summary"]["scored_question_count"] == 2
    assert result["summary"]["by_category"]["4"]["mean_score"] == 1.0
    assert result["summary"]["by_category"]["1"]["mean_score"] == 1.0
    assert result["summary"]["requested_top_k_distribution"] == {5: 1, 10: 1}
    assert result["summary"]["metric_tier"] == "framework_supplementary"


def test_v1_gold_contract_unknown_manifest_version_fails_fast_before_retrieval_evidence(
    tmp_path: Path,
) -> None:
    """旧无版本 gold manifest 不得静默评分，必须先于 retrieval evidence 门 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[],
        private_labels=[],
        public_questions=[],
        include_benchmark_policy=False,
    )

    with pytest.raises(ConfigurationError, match="gold evidence contract"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths, manifest=manifest,
        )


def test_v1_manifest_with_mixed_version_labels_fails_fast(tmp_path: Path) -> None:
    """manifest v1 而 label 缺版本必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:1"])],
            )
        ],
        private_labels=[{"question_id": "q1", "answer": "gold", "evidence": ["D1:1"]}],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )
    with pytest.raises(ConfigurationError, match="old or mixed version"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths, manifest=manifest,
        )


def test_missing_retrieval_evidence_contract_version_fails_fast(tmp_path: Path) -> None:
    """manifest 缺 retrieval_evidence_contract_version 必须 fail-fast，即使旧字段声明可评。

    这道门必须先于旧 `provenance_granularity=none/undeclared` 分支与逐题 N/A：
    不能让缺契约版本的 artifact 因为"反正要评 N/A"而绕过身份门。
    """

    paths, manifest = _write_run(
        tmp_path,
        retrieval_evidence_contract_version=None,
        legacy_provenance_granularity="none",
        answer_prompts=[],
        private_labels=[],
        public_questions=[],
    )

    with pytest.raises(ConfigurationError, match="retrieval_evidence_contract_version"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_unknown_retrieval_evidence_contract_version_fails_fast(tmp_path: Path) -> None:
    """未知 retrieval_evidence_contract_version 值必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        retrieval_evidence_contract_version="v2",
        answer_prompts=[],
        private_labels=[],
        public_questions=[],
    )

    with pytest.raises(ConfigurationError, match="v1"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_missing_retrieval_evidence_key_fails_fast_at_preflight(tmp_path: Path) -> None:
    """answer prompt 完全缺 retrieval_evidence key（非仅值为 null）也必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=None,
                top_k=1,
                retrieved_items=[_item("i1", ["D1:1"])],
                omit_evidence_key=True,
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="q1"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_null_retrieval_evidence_fails_fast_at_preflight(tmp_path: Path) -> None:
    """answer prompt 的 retrieval_evidence 显式为 null 时必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=None, top_k=1, retrieved_items=[_item("i1", ["D1:1"])]
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="q1"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_retrieval_evidence_with_extra_key_fails_fast_at_preflight(tmp_path: Path) -> None:
    """retrieval_evidence 携带未知多余 key 必须 fail-fast，不能静默忽略。"""

    evidence = _valid_evidence("turn")
    evidence["unexpected_extra_field"] = "surprise"
    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=evidence, top_k=1, retrieved_items=[_item("i1", ["D1:1"])]
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="unexpected"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_retrieval_evidence_with_missing_required_key_fails_fast_at_preflight(
    tmp_path: Path,
) -> None:
    """retrieval_evidence 缺必需字段（stable_ranking）必须 fail-fast。"""

    evidence = _valid_evidence("turn")
    del evidence["stable_ranking"]
    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=evidence, top_k=1, retrieved_items=[_item("i1", ["D1:1"])]
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="missing"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_retrieval_evidence_with_illegal_status_fails_fast_at_preflight(
    tmp_path: Path,
) -> None:
    """semantic_provenance.status 非法值必须 fail-fast，不能静默当作某种默认资格。"""

    evidence = _valid_evidence("turn")
    evidence["semantic_provenance"] = _assertion("bogus", reason_code="x", reason="y")
    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=evidence, top_k=1, retrieved_items=[_item("i1", ["D1:1"])]
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="bogus"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_retrieval_evidence_preflight_runs_before_scoring_for_every_record(
    tmp_path: Path,
) -> None:
    """preflight 必须覆盖全部 answer records：一题合法、一题非法也必须整体 fail-fast。

    即使非法的那一题排在合法题之后，也不能因为先扫到合法题就先返回部分结果。
    """

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q-ok",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:1"])],
            ),
            _answer_prompt(
                "q-bad", evidence=None, top_k=1, retrieved_items=[_item("i1", ["D1:1"])]
            ),
        ],
        private_labels=[_label("q-ok", ["D1:1"]), _label("q-bad", ["D1:1"])],
        public_questions=[
            {"question_id": "q-ok", "category": "4"},
            {"question_id": "q-bad", "category": "4"},
        ],
    )

    with pytest.raises(ConfigurationError, match="q-bad"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_stable_ranking_pending_does_not_block_recall_scoring(tmp_path: Path) -> None:
    """Recall 不要求 stable ranking：stable_ranking=pending 时仍应正常计分。"""

    evidence = _valid_evidence("turn")
    assert evidence["stable_ranking"]["status"] == "pending"
    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1", evidence=evidence, top_k=1, retrieved_items=[_item("i1", ["D1:1"])]
            )
        ],
        private_labels=[_label("q1", ["D1:1"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)
    assert result["score_records"][0]["score"] == 1.0
    assert result["score_records"][0]["status"] == "ok"


def test_v1_turn_recall_uses_group_any_of_semantics(tmp_path: Path) -> None:
    """v1 group recall：多个 mapped group 各自 any-of 命中计分，分母=group 数。"""

    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=2,
                retrieved_items=[
                    _item("i1", ["D1:1"]),
                    _item("i2", ["D1:4"]),
                ],
            )
        ],
        private_labels=[_label("q1", ["D1:1", "D1:2", "D1:3"])],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )
    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest,
    )
    assert result["score_records"][0]["score"] == 1 / 3


def test_v1_unmatched_group_lowers_recall_but_stays_in_denominator(
    tmp_path: Path,
) -> None:
    """unmatched group 永远 0 命中、保留在分母中，不删分母。"""

    # 使用手动标签构造一个 unmatched group（D9:9 无对应公开 turn）
    unmatched_label = {
        "question_id": "q1",
        "answer": "gold",
        "evidence": ["D1:1", "D9:9"],
        "gold_evidence_contract_version": "v1",
        "evidence_group_sets": [
            {
                "provenance_granularity": "turn",
                "unit_kind": "locomo_utterance",
                "groups": [
                    {"unit_id": "D1:1", "child_ids": ["D1:1"], "mapping_status": "mapped"},
                    {"unit_id": "D9:9", "child_ids": [], "mapping_status": "unmatched"},
                ],
            },
            {
                "provenance_granularity": "session",
                "unit_kind": "locomo_utterance_session_projection",
                "groups": [
                    {"unit_id": "D1:1", "child_ids": ["D1"], "mapping_status": "mapped"},
                    {"unit_id": "D9:9", "child_ids": [], "mapping_status": "unmatched"},
                ],
            },
        ],
    }
    paths, manifest = _write_run(
        tmp_path,
        answer_prompts=[
            _answer_prompt(
                "q1",
                evidence=_valid_evidence("turn"),
                top_k=1,
                retrieved_items=[_item("i1", ["D1:1"])],
            )
        ],
        private_labels=[unmatched_label],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )
    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest,
    )
    assert result["score_records"][0]["score"] == 1 / 2

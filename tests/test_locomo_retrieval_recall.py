"""测试 LoCoMo artifact-only retrieval recall evaluator。

本文件只从手工构造的 run 目录 artifact 出发（manifest + answer prompts +
private labels），验证 `LoCoMoRetrievalRecallEvaluator` 是否忠实实现官方
`task_eval/evaluation.py:189-241` 的条件式 recall 公式，不构造真实 provider、
不调用 API。
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
    provenance_granularity: str | None,
    answer_prompts: list[dict],
    private_labels: list[dict],
    public_questions: list[dict],
) -> tuple[ExperimentPaths, dict]:
    """构造一个最小可用的 run 目录，写入 artifact-only recall 所需文件。

    输出:
        tuple: `(paths, manifest)`；manifest 与磁盘上写入的内容一致，供
        `evaluate_run_artifacts(manifest=...)` 直接复用，避免测试里出现磁盘
        内容和调用参数不一致的情况。
    """

    paths = ExperimentPaths.create(tmp_path / "run-1")
    method_manifest = {}
    if provenance_granularity is not None:
        method_manifest["provenance_granularity"] = provenance_granularity
    manifest = {
        "run_id": "run-1",
        "benchmark_name": "locomo",
        "method": method_manifest,
    }
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


def test_turn_provenance_computes_official_hit_fraction(tmp_path: Path) -> None:
    """turn provenance 应按官方公式计算 evidence 命中比例。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 2,
                "retrieved_items": [
                    _item("i1", ["D1:1"]),
                    _item("i2", ["D1:2"]),
                    _item("i3", ["D1:3"]),
                ],
            }
        ],
        private_labels=[
            {"question_id": "q1", "answer": "gold", "evidence": ["D1:1", "D1:2"]},
        ],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths, manifest=manifest
    )

    assert result["metric_name"] == "locomo_recall"
    assert result["score_records"][0]["score"] == 1.0
    assert result["summary"]["status"] == "ok"
    assert result["summary"]["provenance_granularity"] == "turn"


def test_turn_provenance_partial_hit_returns_fraction_not_zero_or_one(
    tmp_path: Path,
) -> None:
    """只命中部分 evidence 时应返回介于 0 和 1 之间的比例，而非二值判断。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("i1", ["D1:1"])],
            }
        ],
        private_labels=[
            {"question_id": "q1", "answer": "gold", "evidence": ["D1:1", "D1:2"]},
        ],
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
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [
                    _item("i1", ["D1:9"]),
                    _item("i2", ["D1:1"]),
                ],
            }
        ],
        private_labels=[
            {"question_id": "q1", "answer": "gold", "evidence": ["D1:1"]},
        ],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)

    # top_k=1 只看第一条 item（D1:9），D1:1 排在第二位，超出预算不计入。
    assert result["score_records"][0]["score"] == 0.0


def test_session_provenance_aggregates_dia_id_to_session_prefix(tmp_path: Path) -> None:
    """session provenance 应把 source/evidence 的 dia_id 都聚合为 D<n> 再匹配。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="session",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 1,
                # 检索命中的 turn 是 D1:9（同一 session，但不是 evidence 原 turn）。
                "retrieved_items": [_item("i1", ["D1:9"])],
            }
        ],
        private_labels=[
            {"question_id": "q1", "answer": "gold", "evidence": ["D1:1"]},
        ],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)

    assert result["score_records"][0]["score"] == 1.0
    assert result["summary"]["provenance_granularity"] == "session"


def test_provenance_none_returns_structured_na_without_zero_score(tmp_path: Path) -> None:
    """provenance_granularity='none' 必须写结构化 N/A，不计 0 分。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="none",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 10,
                "retrieved_items": None,
            }
        ],
        private_labels=[{"question_id": "q1", "answer": "gold", "evidence": ["D1:1"]}],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)

    assert result["summary"]["status"] == "n/a"
    assert result["total_questions"] == 0
    assert result["score_records"] == []
    assert "reason" in result["summary"]


def test_missing_provenance_declaration_returns_structured_na(tmp_path: Path) -> None:
    """历史 run 未声明 provenance 时应为 N/A，不能让 artifact-only evaluation 崩溃。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity=None,
        answer_prompts=[],
        private_labels=[],
        public_questions=[],
    )

    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
    )

    assert result["summary"]["status"] == "n/a"
    assert result["summary"]["provenance_granularity"] == "undeclared"
    assert result["total_questions"] == 0


def test_declared_turn_provenance_missing_top_k_fails_fast(tmp_path: Path) -> None:
    """声明 turn provenance 却缺 retrieval_query_top_k 必须 fail-fast，不能静默降级。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieved_items": [_item("i1", ["D1:1"])],
            }
        ],
        private_labels=[{"question_id": "q1", "answer": "gold", "evidence": ["D1:1"]}],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="retrieval_query_top_k"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_declared_turn_provenance_missing_retrieved_items_fails_fast(
    tmp_path: Path,
) -> None:
    """声明 turn provenance 却缺 retrieved_items 必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 10,
            }
        ],
        private_labels=[{"question_id": "q1", "answer": "gold", "evidence": ["D1:1"]}],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="retrieved_items"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_declared_turn_provenance_missing_source_turn_ids_fails_fast(
    tmp_path: Path,
) -> None:
    """声明 turn provenance 却缺 source_turn_ids 字段必须 fail-fast。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [
                    {"item_id": "i1", "content": "memory", "score": 1.0, "timestamp": None}
                ],
            }
        ],
        private_labels=[{"question_id": "q1", "answer": "gold", "evidence": ["D1:1"]}],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="source_turn_ids"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_declared_turn_provenance_empty_source_turn_ids_fails_fast(
    tmp_path: Path,
) -> None:
    """声明支持 provenance 的命中 item 不能用空 source_turn_ids 冒充可追溯。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("i1", [])],
            }
        ],
        private_labels=[{"question_id": "q1", "answer": "gold", "evidence": ["D1:1"]}],
        public_questions=[{"question_id": "q1", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="empty source_turn_ids"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )


def test_answer_prompt_and_private_label_question_ids_must_match(
    tmp_path: Path,
) -> None:
    """artifact ID 不一致必须 fail-fast，不能静默缩小 recall 分母。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q-prompt",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("i1", ["D1:1"])],
            }
        ],
        private_labels=[
            {"question_id": "q-private", "answer": "gold", "evidence": ["D1:1"]}
        ],
        public_questions=[{"question_id": "q-prompt", "category": "4"}],
    )

    with pytest.raises(ConfigurationError, match="question IDs"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
            paths=paths,
            manifest=manifest,
        )


def test_unknown_provenance_granularity_fails_fast(tmp_path: Path) -> None:
    """未知 provenance_granularity 值必须 fail-fast，不能静默当作 none 处理。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="paragraph",
        answer_prompts=[],
        private_labels=[],
        public_questions=[],
    )

    with pytest.raises(ConfigurationError, match="paragraph"):
        LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(paths=paths, manifest=manifest)


def test_empty_evidence_scores_one_and_is_reported_separately(tmp_path: Path) -> None:
    """官方实现对空 evidence 记 1.0，同时必须单独报告数量和 non-empty 均值。"""

    paths, manifest = _write_run(
        tmp_path,
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q-empty",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("i1", ["D1:9"])],
            },
            {
                "question_id": "q-miss",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [_item("i1", ["D1:9"])],
            },
        ],
        private_labels=[
            {"question_id": "q-empty", "answer": "gold", "evidence": []},
            {"question_id": "q-miss", "answer": "gold", "evidence": ["D1:1"]},
        ],
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
        provenance_granularity="turn",
        answer_prompts=[
            {
                "question_id": "q1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 5,
                "retrieved_items": [_item("i1", ["D1:1"])],
            },
            {
                "question_id": "q2",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 10,
                "retrieved_items": [_item("i1", ["D1:2"])],
            },
        ],
        private_labels=[
            {"question_id": "q1", "answer": "gold", "evidence": ["D1:1"]},
            {"question_id": "q2", "answer": "gold", "evidence": ["D1:2"]},
        ],
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

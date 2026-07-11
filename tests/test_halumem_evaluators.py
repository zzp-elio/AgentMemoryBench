"""HaluMem 三段 judge evaluator 的离线聚合测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.core import (
    ConfigurationError,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
)
from memory_benchmark.evaluators.halumem_extraction import (
    HalumemExtractionEvaluator,
    build_halumem_dialogue_str,
    build_halumem_golden_memories_str,
)
from memory_benchmark.evaluators.halumem_memory_type import HalumemMemoryTypeEvaluator
from memory_benchmark.evaluators.halumem_qa import HalumemQAEvaluator
from memory_benchmark.evaluators.halumem_update import HalumemUpdateEvaluator
from memory_benchmark.evaluators.registry import (
    create_evaluator,
    get_evaluator_registration,
    list_metrics,
)
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.runners.operation_level import _evaluator_private_session_label_record
from memory_benchmark.storage import (
    evaluator_private_label_record,
    public_question_record,
    read_jsonl,
)


pytestmark = pytest.mark.unit


class FakeHalumemJudgeClient:
    """按 prompt 内容返回固定 JSON 的 fake judge client。"""

    def __init__(self) -> None:
        """初始化 prompt 记录。"""

        self.prompts: list[str] = []

    def judge_json(self, prompt: str) -> dict[str, str]:
        """返回与官方 judge 输出字段同形的 JSON。"""

        self.prompts.append(prompt)
        if "Memory Integrity" in prompt:
            target = prompt.rsplit("Expected Memory Point:", maxsplit=1)[-1]
            if "keeps a cyan notebook" in target:
                return {"score": "2", "reasoning": "covered"}
            if "favorite drink changed to tea" in target:
                raise AssertionError("update memory must be routed away from integrity")
            if "should ignore marketing bait" in target:
                return {"score": "0", "reasoning": "not extracted"}
            return {"score": "1", "reasoning": "partial"}
        if "Dialogue Memory Accuracy Evaluator" in prompt:
            if "extra unsupported memory" in prompt:
                return {
                    "accuracy_score": "1",
                    "is_included_in_golden_memories": "false",
                    "reason": "部分幻觉",
                }
            if "keeps a cyan notebook" in prompt:
                return {
                    "accuracy_score": "2",
                    "is_included_in_golden_memories": "true",
                    "reason": "准确",
                }
            raise AssertionError("unexpected accuracy prompt")
        if "evaluate the update accuracy" in prompt:
            return {"evaluation_result": "Correct", "reason": "updated"}
        if "question answering" in prompt:
            if "What color is the notebook?" in prompt:
                return {"evaluation_result": "Correct", "reasoning": "right"}
            return {"evaluation_result": "Omission", "reasoning": "missing"}
        raise AssertionError(f"unexpected prompt: {prompt[:120]}")


def test_halumem_extraction_evaluator_matches_official_routing_and_aggregates(
    tmp_path: Path,
) -> None:
    """extraction 聚合应锁死 update 互斥路由、0.5 因子、FMR 和 F1。"""

    run_dir = _build_halumem_run_dir(tmp_path)
    evaluator = HalumemExtractionEvaluator(client=FakeHalumemJudgeClient())

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=evaluator,
        expected_benchmark="halumem",
    )

    score_records = read_jsonl(Path(summary.score_path))
    summary_payload = json.loads(Path(summary.summary_path).read_text(encoding="utf-8"))

    assert summary.metric_name == "halumem_extraction"
    assert summary.total_questions == 4
    assert [record["record_kind"] for record in score_records] == [
        "memory_integrity",
        "memory_integrity",
        "memory_accuracy",
        "memory_accuracy",
    ]
    overall = summary_payload["overall_score"]
    assert overall["memory_integrity"]["recall(all)"] == pytest.approx(1.0)
    assert overall["memory_integrity"]["weighted_recall(all)"] == pytest.approx(1.0)
    assert overall["memory_accuracy"]["interference_accuracy(all)"] == pytest.approx(1.0)
    assert overall["memory_accuracy"]["target_accuracy(all)"] == pytest.approx(1.0)
    assert overall["memory_accuracy"]["weighted_accuracy(all)"] == pytest.approx(0.75)
    assert overall["memory_extraction_f1"] == pytest.approx(1.0)
    assert overall["memory_integrity"]["memory_num"] == 1
    assert overall["memory_update_routed_num"] == 1
    assert summary_payload["category_breakdown"] == [
        {
            "category": "preference",
            "denominator_scope": "integrity_stage_only",
            "memory_count": 1,
            "recall": 1.0,
        }
    ]
    assert all(
        "favorite drink changed to tea" not in prompt
        for prompt in evaluator.client.prompts
        if "Memory Integrity" in prompt
    )


def test_halumem_update_and_qa_evaluators_use_official_inputs_and_breakdowns(
    tmp_path: Path,
) -> None:
    """update/QA judge 输入和比例应对齐 evaluation.py。"""

    run_dir = _build_halumem_run_dir(tmp_path)
    client = FakeHalumemJudgeClient()

    update_summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=HalumemUpdateEvaluator(client=client),
        expected_benchmark="halumem",
    )
    qa_summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=HalumemQAEvaluator(client=client),
        expected_benchmark="halumem",
    )

    update_payload = json.loads(
        Path(update_summary.summary_path).read_text(encoding="utf-8")
    )
    qa_payload = json.loads(Path(qa_summary.summary_path).read_text(encoding="utf-8"))

    assert update_payload["overall_score"]["memory_update"] == {
        "correct_update_memory_ratio(all)": 1.0,
        "correct_update_memory_ratio(valid)": 1.0,
        "hallucination_update_memory_ratio(all)": 0.0,
        "hallucination_update_memory_ratio(valid)": 0.0,
        "omission_update_memory_ratio(all)": 0.0,
        "omission_update_memory_ratio(valid)": 0.0,
        "other_update_memory_ratio(all)": 0.0,
        "other_update_memory_ratio(valid)": 0.0,
        "update_memory_valid_num": 1,
        "update_memory_num": 1,
    }
    assert qa_payload["overall_score"]["question_answering"] == {
        "correct_qa_ratio(all)": 0.5,
        "correct_qa_ratio(valid)": 0.5,
        "hallucination_qa_ratio(all)": 0.0,
        "hallucination_qa_ratio(valid)": 0.0,
        "omission_qa_ratio(all)": 0.5,
        "omission_qa_ratio(valid)": 0.5,
        "qa_valid_num": 2,
        "qa_num": 2,
    }
    assert qa_payload["category_breakdown"] == [
        {
            "category": "Memory Boundary",
            "correct_qa_ratio": 0.0,
            "question_count": 1,
        },
        {
            "category": "Preference",
            "correct_qa_ratio": 1.0,
            "question_count": 1,
        },
    ]
    update_prompt = next(
        prompt for prompt in client.prompts if "evaluate the update accuracy" in prompt
    )
    assert "retrieved updated tea memory" in update_prompt
    assert "favorite drink changed to tea" in update_prompt
    assert "old coffee memory" in update_prompt
    qa_prompt = next(
        prompt for prompt in client.prompts if "What color is the notebook?" in prompt
    )
    assert "reference blue" in qa_prompt
    assert "keeps a cyan notebook" in qa_prompt


def test_halumem_extraction_na_summary_when_session_reports_are_na(
    tmp_path: Path,
) -> None:
    """全 N/A extraction 不应计 0 分或调用 judge。"""

    run_dir = _build_halumem_run_dir(tmp_path, extraction_status="n/a")
    client = FakeHalumemJudgeClient()

    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=HalumemExtractionEvaluator(client=client),
        expected_benchmark="halumem",
    )
    payload = json.loads(Path(summary.summary_path).read_text(encoding="utf-8"))

    assert summary.total_questions == 0
    assert summary.mean_score == 0.0
    assert payload["status"] == "n/a"
    assert payload["overall_score"]["memory_integrity"]["memory_num"] == 0
    assert payload["overall_score"]["memory_integrity"]["recall(all)"] is None
    assert payload["overall_score"]["memory_accuracy"]["target_accuracy(all)"] is None
    assert client.prompts == []


def test_halumem_empty_denominators_are_none_with_explicit_counts(
    tmp_path: Path,
) -> None:
    """extraction/update/QA 空分母必须是 None 且保留计数字段。"""

    run_dir = _build_halumem_run_dir(tmp_path, extraction_status="n/a")
    artifacts = run_dir / "artifacts"
    _write_jsonl(artifacts / "update_probe_results.jsonl", [])
    _write_jsonl(
        artifacts / "public_questions.jsonl",
        [public_question_record(Question("q-public", "user-1", "Question?"))],
    )
    _write_jsonl(
        artifacts / "method_predictions.jsonl",
        [{"question_id": "q-other", "conversation_id": "user-1", "answer": "x"}],
    )
    _write_jsonl(
        artifacts / "evaluator_private_labels.jsonl",
        [evaluator_private_label_record(GoldAnswerInfo("q-public", "gold"), None)],
    )

    extraction = run_artifact_evaluation(
        run_dir, HalumemExtractionEvaluator(client=FakeHalumemJudgeClient()), "halumem"
    )
    update = run_artifact_evaluation(
        run_dir, HalumemUpdateEvaluator(client=FakeHalumemJudgeClient()), "halumem"
    )
    qa = run_artifact_evaluation(
        run_dir, HalumemQAEvaluator(client=FakeHalumemJudgeClient()), "halumem"
    )
    extraction_payload = json.loads(Path(extraction.summary_path).read_text())
    update_payload = json.loads(Path(update.summary_path).read_text())
    qa_payload = json.loads(Path(qa.summary_path).read_text())

    assert extraction_payload["overall_score"]["memory_integrity"]["recall(all)"] is None
    assert extraction_payload["overall_score"]["memory_integrity"]["memory_num"] == 0
    assert update_payload["overall_score"]["memory_update"]["correct_update_memory_ratio(all)"] is None
    assert update_payload["overall_score"]["memory_update"]["update_memory_num"] == 0
    assert qa_payload["overall_score"]["question_answering"]["correct_qa_ratio(all)"] is None
    assert qa_payload["overall_score"]["question_answering"]["qa_num"] == 0


def test_halumem_memory_type_uses_real_upstream_evaluator_artifacts(
    tmp_path: Path,
) -> None:
    """合成维度必须读真实 evaluator 落盘的共享分母记录。"""

    run_dir = _build_halumem_run_dir(tmp_path)
    client = FakeHalumemJudgeClient()
    run_artifact_evaluation(run_dir, HalumemExtractionEvaluator(client=client), "halumem")
    run_artifact_evaluation(run_dir, HalumemUpdateEvaluator(client=client), "halumem")
    summary = run_artifact_evaluation(
        run_dir, HalumemMemoryTypeEvaluator(), "halumem"
    )
    payload = json.loads(Path(summary.summary_path).read_text())

    assert payload["category_breakdown"] == [
        {
            "category": "interference",
            "integrity_correct_num": 0,
            "memory_acc": 0.0,
            "memory_integrity_acc": 0.0,
            "memory_update_acc": 0.0,
            "metric_name": "halumem_memory_type",
            "score": 0.0,
            "total_num": 1,
            "update_correct_num": 0,
        },
        {
            "category": "preference",
            "integrity_correct_num": 1,
            "memory_acc": 1.0,
            "memory_integrity_acc": 0.5,
            "memory_update_acc": 0.5,
            "metric_name": "halumem_memory_type",
            "score": 1.0,
            "total_num": 2,
            "update_correct_num": 1,
        },
    ]


def test_halumem_memory_type_requires_both_upstream_artifacts(tmp_path: Path) -> None:
    """缺任一上游 score artifact 都应明确 fail-fast。"""

    run_dir = _build_halumem_run_dir(tmp_path)
    with pytest.raises(
        ConfigurationError,
        match="requires prior halumem-extraction and halumem-update",
    ):
        run_artifact_evaluation(run_dir, HalumemMemoryTypeEvaluator(), "halumem")


def test_halumem_qa_breakdown_reports_all_six_official_question_types(
    tmp_path: Path,
) -> None:
    """QA category breakdown 应完整保留官方六类维度。"""

    question_types = [
        "Memory Boundary",
        "Basic Fact Recall",
        "Memory Conflict",
        "Generalization & Application",
        "Multi-hop Inference",
        "Dynamic Update",
    ]
    run_dir = _build_halumem_run_dir(tmp_path)
    artifacts = run_dir / "artifacts"
    public_records = []
    private_records = []
    predictions = []
    for index, question_type in enumerate(question_types):
        question_id = f"user-1:s1:q{index}"
        public_records.append(
            public_question_record(
                Question(question_id, "user-1", f"Question {index}?")
            )
        )
        private_records.append(
            evaluator_private_label_record(
                GoldAnswerInfo(
                    question_id,
                    "answer",
                    ["key memory"],
                    {"question_type": question_type, "session_id": "s1"},
                ),
                None,
            )
        )
        predictions.append(
            {
                "question_id": question_id,
                "conversation_id": "user-1",
                "answer": "unknown",
                "metadata": {},
            }
        )
    _write_jsonl(artifacts / "public_questions.jsonl", public_records)
    _write_jsonl(artifacts / "evaluator_private_labels.jsonl", private_records)
    _write_jsonl(artifacts / "method_predictions.jsonl", predictions)

    summary = run_artifact_evaluation(
        run_dir, HalumemQAEvaluator(client=FakeHalumemJudgeClient()), "halumem"
    )
    payload = json.loads(Path(summary.summary_path).read_text())
    assert {item["category"] for item in payload["category_breakdown"]} == set(
        question_types
    )


def test_halumem_dialogue_and_golden_memory_format_match_official_source() -> None:
    """accuracy judge 的 dialogue_str 与 golden_memories_str 应复刻 evaluation.py。"""

    session_label = {
        "dialogue": [
            {"turn_time": "Sep 01, 2025, 10:00:00", "speaker": "user", "content": "hi"},
            {
                "turn_time": "Sep 01, 2025, 10:00:01",
                "speaker": "assistant",
                "content": "hello",
            },
        ],
        "memory_points": [
            {
                "memory_content": "keep",
                "memory_source": "dialogue",
            },
            {
                "memory_content": "drop",
                "memory_source": "interference",
            },
        ],
    }

    assert build_halumem_dialogue_str(session_label) == (
        "[Sep 01, 2025, 10:00:00]user: hi\n"
        "[Sep 01, 2025, 10:00:01]assistant: hello\n"
    )
    assert build_halumem_golden_memories_str(session_label) == "keep"


def test_halumem_evaluator_registry_registers_metrics() -> None:
    """三个 judge 与一个离线合成 metric 应如实注册。"""

    assert "halumem-extraction" in list_metrics()
    assert "halumem-update" in list_metrics()
    assert "halumem-qa" in list_metrics()
    for cli_name, metric_name, evaluator_type in (
        ("halumem-extraction", "halumem_extraction", HalumemExtractionEvaluator),
        ("halumem-update", "halumem_update", HalumemUpdateEvaluator),
        ("halumem-qa", "halumem_qa", HalumemQAEvaluator),
    ):
        registration = get_evaluator_registration(cli_name)
        assert registration.metric_name == metric_name
        assert registration.requires_api is True
        assert registration.supported_benchmarks == frozenset({"halumem"})
        evaluator = create_evaluator(
            cli_name,
            benchmark_name="halumem",
            profile_name="compact",
            model="gpt-4o-mini",
            client=FakeHalumemJudgeClient(),
        )
        assert isinstance(evaluator, evaluator_type)
        assert evaluator.model == "gpt-4o-mini"
    registration = get_evaluator_registration("halumem-memory-type")
    assert registration.metric_name == "halumem_memory_type"
    assert registration.requires_api is False
    assert isinstance(
        create_evaluator("halumem-memory-type", benchmark_name="halumem"),
        HalumemMemoryTypeEvaluator,
    )


def _build_halumem_run_dir(
    tmp_path: Path,
    *,
    extraction_status: str = "ok",
) -> Path:
    """写出最小 HaluMem operation-level artifacts。"""

    run_dir = tmp_path / "run"
    artifacts = run_dir / "artifacts"
    checkpoints = run_dir / "checkpoints"
    summaries = run_dir / "summaries"
    artifacts.mkdir(parents=True)
    checkpoints.mkdir()
    summaries.mkdir()
    _write_json(
        run_dir / "manifest.json",
        {
            "run_id": "halumem-eval-test",
            "benchmark_name": "halumem",
            "runner": "operation_level_prediction",
            "method": {
                "protocol_version": "v3",
                "prompt_track": "unified",
            },
        },
    )
    memories = [] if extraction_status == "n/a" else [
        "keeps a cyan notebook",
        "extra unsupported memory",
    ]
    session = Session(
        session_id="s1",
        turns=[
            Turn("s1:t0", "user", "I keep a cyan notebook.", turn_time="Sep 01, 2025, 10:00:00"),
            Turn("s1:t1", "assistant", "Noted.", turn_time="Sep 01, 2025, 10:00:01"),
        ],
        private_metadata={"memory_points": _memory_points()},
    )
    _write_jsonl(
        artifacts / "evaluator_private_session_labels.jsonl",
        [_evaluator_private_session_label_record(conversation_id="user-1", session=session)],
    )
    _write_jsonl(
        artifacts / "session_memory_reports.jsonl",
        [
            {
                "session_ref": {
                    "isolation_key": "run_user-1",
                    "session_id": "s1",
                },
                "memories": memories,
                "metadata": {},
                "status": extraction_status,
            }
        ],
    )
    _write_jsonl(
        artifacts / "update_probe_results.jsonl",
        [
            {
                "session_ref": {
                    "isolation_key": "run_user-1",
                    "session_id": "s1",
                },
                "gold_memory_index": 2,
                "query_text": "favorite drink changed to tea",
                "memories_from_system": ["retrieved updated tea memory"],
                "formatted_memory": "retrieved updated tea memory",
            }
        ],
    )
    _write_jsonl(
        artifacts / "public_questions.jsonl",
        [
            {
                "question_id": "user-1:s1:q1",
                "conversation_id": "user-1",
                "question_text": "What color is the notebook?",
                "category": None,
                "metadata": {},
            },
            {
                "question_id": "user-1:s1:q2",
                "conversation_id": "user-1",
                "question_text": "What is outside memory?",
                "category": None,
                "metadata": {},
            },
        ],
    )
    _write_jsonl(
        artifacts / "method_predictions.jsonl",
        [
            {
                "question_id": "user-1:s1:q1",
                "conversation_id": "user-1",
                "answer": "cyan",
                "metadata": {},
            },
            {
                "question_id": "user-1:s1:q2",
                "conversation_id": "user-1",
                "answer": "unknown",
                "metadata": {},
            },
        ],
    )
    _write_jsonl(
        artifacts / "evaluator_private_labels.jsonl",
        [
            evaluator_private_label_record(
                GoldAnswerInfo(
                    "user-1:s1:q1", "reference blue", ["keeps a cyan notebook"],
                    {"question_type": "Preference", "session_id": "s1"},
                ),
                None,
            ),
            evaluator_private_label_record(
                GoldAnswerInfo(
                    "user-1:s1:q2", "not enough information", [],
                    {"question_type": "Memory Boundary", "session_id": "s1"},
                ),
                None,
            ),
        ],
    )
    return run_dir


def _memory_points() -> list[dict[str, Any]]:
    """返回覆盖 normal/update/interference 的 gold memory points。"""

    return [
        {
            "index": 1,
            "memory_content": "keeps a cyan notebook",
            "memory_type": "preference",
            "memory_source": "dialogue",
            "importance": 2,
            "is_update": "False",
            "original_memories": [],
        },
        {
            "index": 2,
            "memory_content": "favorite drink changed to tea",
            "memory_type": "preference",
            "memory_source": "dialogue",
            "importance": 8,
            "is_update": "True",
            "original_memories": ["old coffee memory"],
        },
        {
            "index": 3,
            "memory_content": "should ignore marketing bait",
            "memory_type": "interference",
            "memory_source": "interference",
            "importance": 1,
            "is_update": "False",
            "original_memories": [],
        },
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """写 JSON 测试文件。"""

    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """写 JSONL 测试文件。"""

    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_halumem_update_skips_empty_retrieval_per_official_routing(
    tmp_path: Path,
) -> None:
    """空 memories_from_system 的 probe 不进 update 评测与分母（evaluation.py:59-70）。

    官方路由把空检索的 update point 归 integrity 桶；update evaluator 必须
    跳过它（不调 judge、不进分母），全空时比率 None + 分母 0。probe record
    经 runner 真实序列化函数 `_update_probe_record` 构造（fixture 铁律）。
    """

    from memory_benchmark.core.provider_protocol import RetrievalResult, SessionRef
    from memory_benchmark.runners.operation_level import _update_probe_record

    run_dir = _build_halumem_run_dir(tmp_path)
    empty_probe = _update_probe_record(
        session_ref=SessionRef(isolation_key="run_user-1", session_id="s1"),
        memory_point=_memory_points()[1],
        retrieval=RetrievalResult(
            formatted_memory="no relevant memory found", items=()
        ),
        duration_ms=1.0,
    )
    assert empty_probe["memories_from_system"] == []
    _write_jsonl(run_dir / "artifacts" / "update_probe_results.jsonl", [empty_probe])

    client = FakeHalumemJudgeClient()
    summary = run_artifact_evaluation(
        run_dir=run_dir,
        evaluator=HalumemUpdateEvaluator(client=client),
        expected_benchmark="halumem",
    )
    payload = json.loads(Path(summary.summary_path).read_text(encoding="utf-8"))

    ratios = payload["overall_score"]["memory_update"]
    assert ratios["update_memory_num"] == 0
    assert ratios["correct_update_memory_ratio(all)"] is None
    assert payload["skipped_empty_retrieval_count"] == 1

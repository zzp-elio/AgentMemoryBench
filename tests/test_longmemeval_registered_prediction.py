"""LongMemEval 离线全链路：真实 registry/data/prompt/evaluator + B0 probe。

本测试只替换两个外部或算法边界：method 使用现有
`BenchmarkProbeProvider`，framework answer LLM 使用文件内离线 fake client。
LongMemEval registration、真实 S 数据、smoke policy、事件聚合、unified prompt、
artifact writer、通用 F1 与双粒度 recall evaluator 均使用生产实现。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.audit.benchmark_probe import BenchmarkProbeProvider
from memory_benchmark.benchmark_adapters.longmemeval_prompt import (
    LONGMEMEVAL_UNIFIED_ANSWER_PROMPT_PROFILE,
)
from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.config import OpenAISettings
from memory_benchmark.config.settings import PathSettings
from memory_benchmark.core.provider_protocol import ConsumeGranularity
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.evaluators.f1 import F1Evaluator
from memory_benchmark.evaluators.longmemeval_recall import (
    LongMemEvalRetrievalRecallEvaluator,
)
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _ProbeAsMem0(BenchmarkProbeProvider):
    """吞掉 mem0 factory 参数，同时完整保留 B0 probe 行为。"""

    instances: list["_ProbeAsMem0"] = []

    def __init__(
        self,
        *,
        consume_granularity: ConsumeGranularity,
        **_kwargs: object,
    ) -> None:
        """接收 factory 粒度、忽略其余 method 参数并记录探针实例。"""

        super().__init__(consume_granularity=consume_granularity)
        _ProbeAsMem0.instances.append(self)


class _FakeUnifiedAnswerClient:
    """记录 unified prompt 并返回固定答案的离线 answer client。"""

    model_name = "fake-longmemeval-answer-llm"

    def __init__(self, **_kwargs: object) -> None:
        """兼容真实 answer client 的关键字构造签名。"""

        self.calls: list[str] = []

    def complete(self, *, prompt: str) -> str:
        """保存 prompt，返回不要求答对的固定公开预测。"""

        self.calls.append(prompt)
        return "fake unified answer"


def _assert_no_forbidden_keys(payload: object, forbidden_keys: set[str]) -> None:
    """递归检查窄化私有键集合，允许 prediction 合法的 `answer` 字段。"""

    if isinstance(payload, dict):
        for key, value in payload.items():
            assert str(key).lower() not in forbidden_keys, (
                f"forbidden private key '{key}' found in public artifact"
            )
            _assert_no_forbidden_keys(value, forbidden_keys)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _assert_no_forbidden_keys(item, forbidden_keys)


def test_longmemeval_registered_prediction_offline_probe_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """跑通 LongMemEval 默认 smoke 的 ingest 到离线 F1/recall 四步链路。"""

    _ProbeAsMem0.instances.clear()
    path_settings = PathSettings(
        project_root=PROJECT_ROOT,
        data_root=PROJECT_ROOT / "data",
        models_root=PROJECT_ROOT / "models",
        outputs_root=tmp_path / "outputs",
        third_party_root=PROJECT_ROOT / "third_party",
        third_party_benchmarks_root=PROJECT_ROOT / "third_party" / "benchmarks",
        third_party_methods_root=PROJECT_ROOT / "third_party" / "methods",
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: path_settings,
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: OpenAISettings(api_key="sk-test", model="gpt-4o-mini"),
        raising=False,
    )
    fake_client = _FakeUnifiedAnswerClient()
    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        lambda **kwargs: fake_client,
        raising=False,
    )
    monkeypatch.setattr(method_registry_module, "Mem0", _ProbeAsMem0)

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="mem0",
        benchmark_name="longmemeval",
        profile_name="smoke",
        variant="s_cleaned",
        run_id="longmemeval-c5-probe-smoke",
        confirm_api=True,
        smoke_round_limit=1,
        smoke_conversation_limit=1,
        question_limit_per_conversation=1,
        enable_efficiency_observability=False,
        output_layout="hierarchical",
    )

    assert result.benchmark == "longmemeval"
    assert len(result.runs) == 1
    summary = result.runs[0].summary
    assert summary.total_conversations == 1
    assert summary.completed_conversations == 1
    assert summary.total_questions == 1
    assert summary.completed_questions == 1

    assert len(_ProbeAsMem0.instances) == 1
    probe = _ProbeAsMem0.instances[0]
    required_sequence = ["ingest", "end_session", "end_conversation", "retrieve"]
    call_indices = [probe.call_log.index(call) for call in required_sequence]
    assert call_indices == sorted(call_indices), (
        f"probe call_log {probe.call_log} does not preserve {required_sequence}"
    )
    assert len(probe.ingested_turns) == 2
    assert len(probe.ended_sessions) == 1
    assert len({turn.session_id for turn in probe.ingested_turns}) == 1
    assert len(probe.ended_conversations) == 1
    assert len(probe.retrieve_queries) == 1

    run_dir = Path(summary.prediction_path).resolve().parent.parent
    paths = ExperimentPaths.create(run_dir)
    public_questions = read_jsonl(paths.public_questions_path)
    answer_prompts = read_jsonl(paths.answer_prompts_path)
    predictions = read_jsonl(paths.method_predictions_path)
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))

    assert len(public_questions) == 1
    assert len(answer_prompts) == 1
    assert len(predictions) == 1
    assert answer_prompts[0]["metadata"]["prompt_track"] == "unified"
    assert (
        answer_prompts[0]["metadata"]["answer_prompt_profile"]
        == LONGMEMEVAL_UNIFIED_ANSWER_PROMPT_PROFILE
    )
    assert manifest["method"]["provenance_granularity"] == "turn"
    assert manifest["method"]["prompt_track"] == "unified"
    assert predictions[0]["answer"] == "fake unified answer"
    assert fake_client.calls

    expected_memory = "\n".join(
        f"{turn.speaker_name or turn.role}: {turn.content}"
        for turn in probe.ingested_turns
    )
    prompt = answer_prompts[0]["prompt_messages"][0]["content"]
    assert answer_prompts[0]["formatted_memory"] == expected_memory
    assert answer_prompts[0]["metadata"]["answer_context"] == expected_memory
    assert f"History Chats:\n\n{expected_memory}\n\nCurrent Date:" in prompt
    assert f"Current Date: {public_questions[0]['question_time']}" in prompt
    assert "### Session" not in prompt
    assert fake_client.calls == [prompt]

    f1_summary = run_artifact_evaluation(
        run_dir,
        F1Evaluator(),
        "longmemeval",
    )
    assert f1_summary.total_questions == 1
    # 每类分开报告契约：端到端 summary 必须携带 category_breakdown。
    f1_payload = json.loads(
        Path(f1_summary.summary_path).read_text(encoding="utf-8")
    )
    f1_breakdown = f1_payload["category_breakdown"]
    assert len(f1_breakdown) == 1
    assert f1_breakdown[0]["category"] == public_questions[0]["category"]
    assert f1_breakdown[0]["question_count"] == 1

    recall_summary = run_artifact_evaluation(
        run_dir,
        LongMemEvalRetrievalRecallEvaluator(),
        "longmemeval",
    )
    recall_payload = json.loads(
        Path(recall_summary.summary_path).read_text(encoding="utf-8")
    )
    assert recall_summary.total_questions == 1
    assert recall_payload["status"] == "ok"
    assert recall_payload["provenance_granularity"] == "turn"

    explicit_private_keys = {
        "answer_session_ids",
        "has_answer",
        "evidence_turn_ids",
        "evidence_turn_corpus_ids",
        "evidence_session_public_ids",
    }
    for record in public_questions:
        validate_no_private_keys(record)
        _assert_no_forbidden_keys(record, explicit_private_keys)
    for record in answer_prompts:
        validate_no_private_keys(record)
        _assert_no_forbidden_keys(record, explicit_private_keys)

    prediction_private_keys = explicit_private_keys | {
        "evidence",
        "gold",
        "gold_answer",
        "gold_answers",
        "ground_truth",
        "judge_label",
        "label",
        "target_step_id",
    }
    for record in predictions:
        _assert_no_forbidden_keys(record, prediction_private_keys)

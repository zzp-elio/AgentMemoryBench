"""LoCoMo 离线全链路测试：真实 registry/data/adapter/prompt/evaluator + B0 probe。

本文件是 LoCoMo B0+B1 plan 唯一允许的端到端测试（A6 批次）。只替换两处
外部/算法边界：
- method 使用现有 `BenchmarkProbeProvider`（Task 2 的 B0 中性探针），只包一层
  参数吞掉的薄壳以适配 mem0 registry factory 的关键字构造签名，探针本身的
  ingest/retrieve/end_session/end_conversation 行为完全不变；
- framework answer LLM 使用文件内固定离线 fake client，零真实 API 调用。

真实 LoCoMo benchmark registration、真实 `data/locomo/locomo10.json`、真实
smoke adapter、真实事件聚合、真实 unified prompt builder、真实 artifact
writer 和真实 F1/recall evaluator 全部不替换、不 monkeypatch。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.audit.benchmark_probe import BenchmarkProbeProvider
from memory_benchmark.benchmark_adapters.locomo_prompt import (
    LOCOMO_UNIFIED_ANSWER_PROMPT_PROFILE,
)
from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.cli.commands import EvaluateCommand, execute_evaluate
from memory_benchmark.config import OpenAISettings
from memory_benchmark.config.settings import PathSettings
from memory_benchmark.core.provider_protocol import ConsumeGranularity
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.evaluators.locomo_f1 import LoCoMoF1Evaluator
from memory_benchmark.evaluators.locomo_recall import LoCoMoRetrievalRecallEvaluator
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _ProbeAsMem0(BenchmarkProbeProvider):
    """把 B0 probe 包成可挂到 mem0 registry factory 的壳。

    真实 `_build_mem0_system` 会传入 mem0 专属关键字参数（`config`、
    `openai_settings`、`storage_root` 等）；探针按 Task 2 的显式反需求不接受
    这些参数，因此这里只做参数吞掉，不改变探针任何真实行为。`instances` 记录
    实际构造出的探针实例，供测试断言调用序列。
    """

    instances: list["_ProbeAsMem0"] = []

    def __init__(
        self,
        *,
        consume_granularity: ConsumeGranularity,
        **_kwargs: object,
    ) -> None:
        """接收 mem0 factory 粒度并忽略其余构造参数。"""

        super().__init__(consume_granularity=consume_granularity)
        _ProbeAsMem0.instances.append(self)


class _FakeUnifiedAnswerClient:
    """文件内离线 fake answer LLM client，零真实 API 调用。"""

    model_name = "fake-locomo-answer-llm"

    def __init__(self, **_kwargs: object) -> None:
        """兼容 `OpenAICompatibleAnswerLLMClient` 的关键字构造签名。"""

        self.calls: list[str] = []

    def complete(self, *, prompt: str) -> str:
        """记录 prompt 并返回固定答案；流程成功不要求答对。"""

        self.calls.append(prompt)
        return "fake unified answer"


def _assert_no_forbidden_keys(payload: object, forbidden_keys: set[str]) -> None:
    """递归扫描 payload，确认不含指定的私有键名（不复用会误判 answer 的通用 validator）。"""

    if isinstance(payload, dict):
        for key, value in payload.items():
            assert str(key).lower() not in forbidden_keys, (
                f"forbidden private key '{key}' found in prediction record"
            )
            _assert_no_forbidden_keys(value, forbidden_keys)
    elif isinstance(payload, (list, tuple)):
        for item in payload:
            _assert_no_forbidden_keys(item, forbidden_keys)


def test_locomo_registered_prediction_offline_probe_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 LoCoMo 四步链路 + B0 probe + 离线 fake answer LLM 的端到端验收。"""

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
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="locomo-a6-probe-smoke",
        confirm_api=True,
        smoke_round_limit=1,
        smoke_conversation_limit=1,
        question_limit_per_conversation=1,
        enable_efficiency_observability=False,
        output_layout="hierarchical",
    )

    # ---- 1 conversation x 1 round x 1 question ----
    assert result.benchmark == "locomo"
    assert len(result.runs) == 1
    summary = result.runs[0].summary
    assert summary.total_conversations == 1
    assert summary.completed_conversations == 1
    assert summary.total_questions == 1
    assert summary.completed_questions == 1

    # ---- probe 实例：ingest -> end_session -> end_conversation -> retrieve ----
    assert len(_ProbeAsMem0.instances) == 1
    probe = _ProbeAsMem0.instances[0]
    required_sequence = ["ingest", "end_session", "end_conversation", "retrieve"]
    call_indices = [
        probe.call_log.index(call) for call in required_sequence
    ]
    assert call_indices == sorted(call_indices), (
        f"probe call_log {probe.call_log} does not preserve required order "
        f"{required_sequence}"
    )
    # 1 round == 官方定义的前 2 个连续 turn，probe 实际 ingest 到的 turn 数核实此点。
    assert len(probe.ingested_turns) == 2
    assert len(probe.ended_sessions) >= 1
    assert len(probe.ended_conversations) == 1
    assert len(probe.retrieve_queries) == 1

    # ---- artifact 内容：unified prompt / top_k / provenance ----
    run_dir = Path(summary.prediction_path).resolve().parent.parent
    assert run_dir == (
        tmp_path
        / "outputs"
        / "runs"
        / "mem0"
        / "locomo"
        / "smoke"
        / "unified"
        / "locomo-a6-probe-smoke"
    ).resolve()
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
        == LOCOMO_UNIFIED_ANSWER_PROMPT_PROFILE
    )
    assert answer_prompts[0]["retrieval_query_top_k"] == 10
    assert manifest["method"]["provenance_granularity"] == "turn"
    assert manifest["method"]["prompt_track"] == "unified"
    assert manifest["method"]["retrieval_evidence_contract_version"] == "v1"
    assert predictions[0]["answer"] == "fake unified answer"
    assert fake_client.calls  # framework 确实调用了离线 fake，而非跳过 answer 步骤

    # ---- artifact-only 跑 F1 与 recall；分数允许为 0，流程成功不要求答对 ----
    f1_summary = run_artifact_evaluation(run_dir, LoCoMoF1Evaluator(), "locomo")
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
        run_dir, LoCoMoRetrievalRecallEvaluator(), "locomo"
    )
    assert recall_summary.total_questions == 1

    command_f1_summary = execute_evaluate(
        EvaluateCommand(
            project_root=tmp_path,
            run_id="locomo-a6-probe-smoke",
            metrics=("f1",),
        )
    )
    assert command_f1_summary[0].total_questions == 1

    resumed = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="mem0",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="locomo-a6-probe-smoke",
        resume=True,
        confirm_api=True,
        smoke_round_limit=1,
        smoke_conversation_limit=1,
        question_limit_per_conversation=1,
        enable_efficiency_observability=False,
        output_layout="hierarchical",
    )
    assert Path(resumed.runs[0].summary.prediction_path).resolve().parent.parent == run_dir
    assert len(read_jsonl(paths.method_predictions_path)) == 1

    # ---- 私有键扫描：public questions / answer prompts / predictions ----
    # public questions 和 answer prompts 本身不应包含任何"answer"字段（那些是
    # 提问前的公开载荷），可直接复用通用 validator。
    for record in public_questions:
        validate_no_private_keys(record)
    for record in answer_prompts:
        validate_no_private_keys(record)
    # method_predictions.jsonl 合法地带有公开的 "answer"（method 自己生成的
    # 预测文本），通用 validator 会把它当成 gold answer 误判；这里只扫描真正
    # 私有的 gold/evidence/judge 相关键，不复用会对合法字段报警的通用 validator。
    forbidden_private_keys = {
        "evidence",
        "gold",
        "gold_answer",
        "gold_answers",
        "ground_truth",
        "judge_label",
        "label",
        "target_step_id",
        "answer_session_ids",
    }
    for record in predictions:
        _assert_no_forbidden_keys(record, forbidden_private_keys)

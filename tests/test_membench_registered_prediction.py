"""MemBench 离线全链路：真实 registry/data/prompt/evaluator + B0 probe。

本测试只替换两个外部或算法边界：method 使用现有
`BenchmarkProbeProvider`，framework answer LLM 使用文件内离线 fake client。
MemBench registration、真实 0-10k 数据、smoke policy、事件聚合、unified MCQ
prompt、artifact writer、choice-accuracy 与 membench-recall evaluator 均使用
生产实现。

路径覆盖（D5 卡硬要求）：
- 第一人称 ingest（dict message → canonical split 后 1 round = user+assistant
  两条 Turn）；
- 第三人称 ingest（str message → 1 turn，含无冒号时间格式的 LowLevel turn_time
  非空——D2 时戳 bug 修复验收点）；
- 4 源文件各 1 trajectory，标准 smoke 口径（见
  `plan-b3-membench.md` §2.5 路径覆盖）；
- MCQ unified answer + `normalize_membench_choice_prediction` 跨 task type
  统一 parser（官方 enum A-D + JSON schema 两种形态均覆盖）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.audit.benchmark_probe import BenchmarkProbeProvider
from memory_benchmark.benchmark_adapters.membench import (
    MEMBENCH_INSTRUCTION_FIRST_PROFILE,
)
from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.config import OpenAISettings
from memory_benchmark.config.settings import PathSettings
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.evaluators.membench_choice_accuracy import (
    MemBenchChoiceAccuracyEvaluator,
)
from memory_benchmark.evaluators.membench_recall import (
    MemBenchRetrievalRecallEvaluator,
)
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _ProbeAsMem0(BenchmarkProbeProvider):
    """吞掉 mem0 factory 参数，同时完整保留 B0 probe 行为。"""

    instances: list["_ProbeAsMem0"] = []

    def __init__(self, **_kwargs: object) -> None:
        """忽略 method-specific 构造参数并记录实际探针实例。"""

        super().__init__()
        _ProbeAsMem0.instances.append(self)


class _FakeUnifiedAnswerClient:
    """记录 unified prompt 并返回可被 membench prediction_transform 解析的固定选项。"""

    model_name = "fake-membench-answer-llm"

    def __init__(self, **_kwargs: object) -> None:
        """兼容真实 answer client 的关键字构造签名。"""

        self.calls: list[str] = []

    def complete(self, *, prompt: str) -> str:
        """保存 prompt，返回官方 JSON schema 形态（exercise 解析器）。"""

        self.calls.append(prompt)
        return '{"choice": "B"}'


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


def test_membench_registered_prediction_offline_probe_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """跑通 MemBench 0_10k 4 源 smoke 的 ingest → answer → 离线 choice/recall 链路。"""

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
        benchmark_name="membench",
        profile_name="smoke",
        variant="0_10k",
        run_id="membench-d5-probe-smoke",
        confirm_api=True,
        smoke_round_limit=1,
        smoke_conversation_limit=1,
        question_limit_per_conversation=1,
        enable_efficiency_observability=False,
        output_layout="hierarchical",
    )

    assert result.benchmark == "membench"
    assert len(result.runs) == 1
    summary = result.runs[0].summary
    assert summary.total_conversations == 4
    assert summary.completed_conversations == 4
    assert summary.total_questions == 4
    assert summary.completed_questions == 4

    assert len(_ProbeAsMem0.instances) == 1
    probe = _ProbeAsMem0.instances[0]
    # 协议钩子覆盖：ingest → end_session → end_conversation → retrieve 4 类
    required_sequence = ["ingest", "end_session", "end_conversation", "retrieve"]
    call_indices = [probe.call_log.index(call) for call in required_sequence]
    assert call_indices == sorted(call_indices), (
        f"probe call_log {probe.call_log} does not preserve {required_sequence}"
    )
    # 第一人称 canonical split 后 1 round=1 源 step=user+assistant 2 turn/conv
    # × 2 convs + 第三人称 2 turns/conv × 2 convs = 8 turn
    assert len(probe.ingested_turns) == 8
    assert len(probe.ended_sessions) == 4
    # MemBench 单 session/conversation（session_id 全是 "s1"），用 isolation_key
    # 区分 4 conversation。
    assert len({turn.isolation_key for turn in probe.ingested_turns}) == 4
    assert len(probe.ended_conversations) == 4
    assert len(probe.retrieve_queries) == 4

    run_dir = Path(summary.prediction_path).resolve().parent.parent
    paths = ExperimentPaths.create(run_dir)
    public_questions = read_jsonl(paths.public_questions_path)
    answer_prompts = read_jsonl(paths.answer_prompts_path)
    predictions = read_jsonl(paths.method_predictions_path)
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))

    assert len(public_questions) == 4
    assert len(answer_prompts) == 4
    assert len(predictions) == 4

    # 双人称路径都执行：4 源各 1 trajectory → 2 first-person + 2 third-person
    conversation_ids = {record["conversation_id"] for record in public_questions}
    assert sum(cid.startswith("first-") for cid in conversation_ids) == 2
    assert sum(cid.startswith("third-") for cid in conversation_ids) == 2
    third_low_conversations = [
        record for record in public_questions
        if record["conversation_id"].startswith("third-low-")
    ]
    assert len(third_low_conversations) == 1
    third_low_turns = [
        turn for turn in probe.ingested_turns
        if turn.isolation_key.startswith("membench-d5-probe-smoke-0-10k_third-low-")
    ]
    # 第三人称 2 turn budget（= 1 round × 2）
    assert len(third_low_turns) == 2

    # 关键：D2 时戳正则修复验收——第三人称 LowLevel 无冒号 `time'…'`
    # 格式必须被解析为非空 turn_time（这是 path 覆盖关键断言）。
    # TurnEvent 把 turn_time 存到 metadata["original_turn_time"]。
    assert third_low_turns, "third-person LowLevel 探针未收到任何 turn"
    third_low_turn_times = [
        turn.metadata.get("original_turn_time") for turn in third_low_turns
    ]
    assert all(third_low_turn_times), (
        f"third-person LowLevel turn_time 全空，D2 时戳修复可能回退：{third_low_turn_times}"
    )

    # unified MCQ prompt：每个 answer_prompts 都是 MEMBENCH_INSTRUCTION_FIRST 模板
    for record in answer_prompts:
        assert record["metadata"]["prompt_track"] == "unified"
        assert (
            record["metadata"]["answer_prompt_profile"]
            == MEMBENCH_INSTRUCTION_FIRST_PROFILE
        )
    assert manifest["method"]["provenance_granularity"] == "turn"
    assert manifest["method"]["prompt_track"] == "unified"

    # prediction_transform 生效：fake 返回 `{"choice": "B"}`，transform 应归一为
    # 单字母 B（官方 json_schema 解析路径覆盖）。
    assert all(record["answer"] == "B" for record in predictions)
    assert all(
        record["metadata"].get("choice_parse_status") == "parsed"
        for record in predictions
    )
    assert all(
        record["metadata"].get("raw_answer") == '{"choice": "B"}'
        for record in predictions
    )
    assert fake_client.calls, "框架 answer reader 未被调用"

    # prompt 结构：含 4 个选项行 + 官方 "only one corresponding letter" 指令
    for record in answer_prompts:
        prompt_text = record["prompt_messages"][0]["content"]
        assert "A." in prompt_text
        assert "B." in prompt_text
        assert "C." in prompt_text
        assert "D." in prompt_text
        assert "only one corresponding letter" in prompt_text
        # `{memory}` 槽位 = probe formatted_memory
        formatted_memory = record["formatted_memory"]
        assert formatted_memory
        assert formatted_memory in prompt_text
        # public question time 应进入 prompt
        question_time = public_questions[next(
            index
            for index, item in enumerate(public_questions)
            if item["question_id"] == record["question_id"]
        )]["question_time"]
        if question_time:
            assert question_time in prompt_text
    assert len(fake_client.calls) == 4

    # 离线 choice-accuracy：4 题都给 B，fraction correct 取决于 gold；流程不要求
    # 答对，但 summary 落地 + category_breakdown 必现。
    choice_summary = run_artifact_evaluation(
        run_dir,
        MemBenchChoiceAccuracyEvaluator(),
        "membench",
    )
    assert choice_summary.total_questions == 4
    choice_payload = json.loads(
        Path(choice_summary.summary_path).read_text(encoding="utf-8")
    )
    category_breakdown = {
        entry["category"]: entry for entry in choice_payload["category_breakdown"]
    }
    # 4 源 = 2 task_type（first_high/third_high → highlevel，first_low/third_low
    # → simple）；每类各 2 题。category_breakdown 必须按 task_type 分组。
    assert sorted(category_breakdown) == ["highlevel", "simple"]
    assert category_breakdown["highlevel"]["question_count"] == 2
    assert category_breakdown["simple"]["question_count"] == 2

    # 离线 membench-recall：probe 声明 turn provenance → 必给非 N/A 结果
    recall_summary = run_artifact_evaluation(
        run_dir,
        MemBenchRetrievalRecallEvaluator(),
        "membench",
    )
    recall_payload = json.loads(
        Path(recall_summary.summary_path).read_text(encoding="utf-8")
    )
    assert recall_summary.total_questions == 4
    # run_artifact_evaluation 把 evaluator 返回的 summary 字段平铺进顶层
    # summary dict（见 evaluation.py:285-288）。
    assert recall_payload["status"] == "ok"
    assert recall_payload["provenance_granularity"] == "turn"

    # 公开 artifact 私有键扫描
    explicit_private_keys = {
        "evidence",
        "gold",
        "gold_answer",
        "gold_answers",
        "ground_truth",
        "judge_label",
        "label",
        "target_step_id",
    }
    for record in public_questions:
        validate_no_private_keys(record)
        _assert_no_forbidden_keys(record, explicit_private_keys)
    for record in answer_prompts:
        validate_no_private_keys(record)
        _assert_no_forbidden_keys(record, explicit_private_keys)

    # prediction 私有键扫描：answer 字段在 prediction 合法，不应被禁；但
    # gold/evidence/ground_truth/target_step_id 仍须为 0
    prediction_private_keys = explicit_private_keys
    for record in predictions:
        _assert_no_forbidden_keys(record, prediction_private_keys)

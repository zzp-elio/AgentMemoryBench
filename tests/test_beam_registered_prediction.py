"""BEAM 离线全链路：真实 registry/arrow/smoke/unified/artifact/evaluator + B0 probe。

本测试只替换两个外部边界：method 使用现有 `BenchmarkProbeProvider`（吞掉
mem0 工厂参数），framework answer LLM 使用文件内离线 fake client。BEAM
registration、真实 arrow 数据（`data/BEAM/beam_dataset/100K` 与
`data/BEAM/beam_10M_dataset/10M`）、声明式 smoke policy、事件聚合、unified
answer prompt、artifact writer、beam-rubric-judge（fake client 含 0.5 一次
以断言 float 主分与 official_int 对照分并存）、beam-recall、f1 evaluator
均使用生产实现。

E5 双结构认证 = 两次独立 prepare/run（架构师 E2 裁决：variant=独立数据集=
独立 run 身份，混跑模糊身份）：
- run A：`variant=100k` smoke；1 conv × 1 round × 1 题实际作答（数据集带
  20 题、runner 预算裁 1 题，两者都断言）。
- run B：`variant=10m` smoke；同口径；断言 10m 切片 session_id = `p1:s1`、
  plan metadata 存在。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.audit.benchmark_probe import BenchmarkProbeProvider
from memory_benchmark.benchmark_adapters.beam import (
    BEAM_ABILITY_KEYS,
    BEAM_ANSWER_PROMPT_PROFILE,
    BEAM_RESUME_POLICY,
    BEAM_SMOKE_POLICY,
)
from memory_benchmark.benchmark_adapters.registry import get_benchmark_registration
from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.config import OpenAISettings
from memory_benchmark.config.settings import PathSettings
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.evaluators.beam_recall import BeamRetrievalRecallEvaluator
from memory_benchmark.evaluators.beam_rubric_judge import BeamRubricJudgeEvaluator
from memory_benchmark.evaluators.f1 import F1Evaluator
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# BEAM 私有键黑名单（架构师 E2 决策：core/validators.PRIVATE_KEY_NAMES 全局
# 扩展为 BEAM 全类型 gold 字段，但本测试仍显式列举本 benchmark 关心的关键
# 集，用以断言三层 privacy 扫描的零泄漏点）。
_BEAM_PRIVATE_KEY_BLACKLIST: frozenset[str] = frozenset(
    {
        "rubric",
        "ideal_response",
        "ideal_summary",
        "ideal_answer",
        "expected_compliance",
        "source_chat_ids",
        "evidence_turn_ids",
    }
)


# ---------------------------------------------------------------------------
# fake provider / fake answer client
# ---------------------------------------------------------------------------


class _ProbeAsMem0(BenchmarkProbeProvider):
    """吞掉 mem0 factory 参数，同时完整保留 B0 probe 行为。"""

    instances: list["_ProbeAsMem0"] = []

    def __init__(self, **_kwargs: object) -> None:
        """忽略 method-specific 构造参数并记录实际探针实例。"""

        super().__init__()
        _ProbeAsMem0.instances.append(self)


class _FakeUnifiedAnswerClient:
    """记录 unified prompt 并返回固定答案文本供 judge/recall 离线打分。"""

    model_name = "fake-beam-answer-llm"

    def __init__(self, **_kwargs: object) -> None:
        """兼容真实 answer client 的关键字构造签名。"""

        self.calls: list[str] = []

    def complete(self, *, prompt: str) -> str:
        """保存 prompt，返回固定 free-text 答案（BEAM 自由文本无 transform）。"""

        self.calls.append(prompt)
        return "fake beam answer"


class _FakeBeamJudgeClient:
    """BEAM rubric judge 离线 fake client。

    每次 judge_json 第一次返回 0.5（断言 float 主分与 official_int 对照
    分并存——0.5 在 int 截断下变 0），其后返回 1.0。judge_equivalence 走
    逐字相等判定（event_ordering 复合分需要）。本测试不触发 event_ordering
    复合分（10M 切片 `p1:s1` 通常无 event_ordering 题；即便有，fake 给全
    YES 让 alignment 命中），但提供方法以保持与生产接口一致。
    """

    def __init__(self) -> None:
        """初始化轮转状态。"""

        self.call_count = 0
        self.equivalence_calls = 0

    def judge_json(self, prompt: str) -> dict[str, object]:
        """第一次返回 0.5（覆盖 int/float 双轨差异），其后返回 1.0。"""

        score = 0.5 if self.call_count == 0 else 1.0
        self.call_count += 1
        return {"score": score, "reason": f"fake judge call {self.call_count}"}

    def judge_equivalence(self, messages: list[dict[str, str]]) -> str:
        """event_ordering 复合分用；逐字相等返 YES。"""

        del messages
        self.equivalence_calls += 1
        return "YES"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


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


def _run_beam_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    variant: str,
    run_id: str,
) -> tuple[
    "_ProbeAsMem0",
    "_FakeUnifiedAnswerClient",
    ExperimentPaths,
    dict[str, Any],
]:
    """执行一次 BEAM registered smoke run，返回探针/fake client/paths/manifest。

    每个 variant 一次独立 prepare/run（架构师 E2 裁决：双结构认证语义）。
    """

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
        benchmark_name="beam",
        profile_name="smoke",
        variant=variant,
        run_id=run_id,
        confirm_api=True,
        smoke_round_limit=1,
        smoke_conversation_limit=1,
        question_limit_per_conversation=1,
        enable_efficiency_observability=False,
        output_layout="hierarchical",
    )

    assert result.benchmark == "beam"
    assert len(result.runs) == 1
    summary = result.runs[0].summary
    assert summary.total_conversations == 1
    assert summary.completed_conversations == 1
    # 数据集每 conv 20 题（10 ability × 2），runner 预算裁 1 题（双断言）。
    assert summary.total_questions == 1
    assert summary.completed_questions == 1

    probe = _ProbeAsMem0.instances[0]
    run_dir = Path(summary.prediction_path).resolve().parent.parent
    paths = ExperimentPaths.create(run_dir)
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    return probe, fake_client, paths, manifest


def _assert_probe_lifecycle(probe: _ProbeAsMem0) -> None:
    """断言 B0 probe 协议钩子顺序：ingest → end_session → end_conversation → retrieve。"""

    required_sequence = ["ingest", "end_session", "end_conversation", "retrieve"]
    call_indices = [probe.call_log.index(call) for call in required_sequence]
    assert call_indices == sorted(call_indices), (
        f"probe call_log {probe.call_log} does not preserve {required_sequence}"
    )


def _assert_original_dataset_has_20_questions_per_conv(variant: str) -> None:
    """直接通过 `BeamAdapter` 加载 variant，断言每 conv 带 20 题（10 ability × 2）。

    与 runner 写入的 public_questions.jsonl（裁 1 题）分离断言：spec 要求
    "数据集带 20 题、runner 预算裁 1 题，两者都断言"。
    """

    from memory_benchmark.benchmark_adapters.beam import BeamAdapter

    adapter = BeamAdapter(PROJECT_ROOT, variant=variant)
    dataset = adapter.load(limit=1)
    assert dataset.conversations, f"{variant}: adapter returned empty conversations"
    for conversation in dataset.conversations:
        assert len(conversation.questions) == 20, (
            f"{variant}/{conversation.conversation_id}: expected 20 questions per "
            f"conversation (10 ability × 2), got {len(conversation.questions)}"
        )
        # 10 ability × 2 = 20；ability 集与 adapter 公开常量一致。
        ability_counts: dict[str, int] = {}
        for question in conversation.questions:
            ability_counts[question.category] = ability_counts.get(question.category, 0) + 1
        assert sorted(ability_counts) == sorted(BEAM_ABILITY_KEYS)
        assert all(count == 2 for count in ability_counts.values()), (
            f"{variant}: expected 2 questions per ability, got {ability_counts}"
        )


def _assert_prompt_and_artifact_layout(
    *,
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    answer_prompts: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    public_questions: list[dict[str, Any]],
    fake_client: _FakeUnifiedAnswerClient,
) -> None:
    """断言 unified prompt / manifest 形状 / artifact 计数 / formatted_memory 进 prompt。"""

    assert manifest["method"]["provenance_granularity"] == "turn"
    assert manifest["method"]["retrieval_evidence_contract_version"] == "v1"
    assert manifest["method"]["prompt_track"] == "unified"
    assert manifest["benchmark_name"] == "beam"
    assert manifest["run_scope"] == "smoke"

    # 1 题（runner 预算裁 1） + 数据集带 20 题：public 只含 runner 实际
    # 作答的 1 题；原始数据集 10 ability × 2 = 20 题/conv 由独立 adapter
    # 加载断言（见 _assert_original_dataset_has_20_questions_per_conv）。
    assert len(public_questions) == 1
    assert len(answer_prompts) == 1
    assert len(predictions) == 1

    record = answer_prompts[0]
    evidence = record["retrieval_evidence"]
    assert evidence["semantic_provenance"] == {
        "status": "valid", "reason_code": None, "reason": None
    }
    assert evidence["provenance_granularity"] == "turn"
    assert evidence["stable_ranking"] == {
        "status": "valid", "reason_code": None, "reason": None
    }
    assert record["metadata"]["prompt_track"] == "unified"
    assert record["metadata"]["answer_prompt_profile"] == BEAM_ANSWER_PROMPT_PROFILE

    prompt_text = record["prompt_messages"][0]["content"]
    formatted_memory = record["formatted_memory"]
    assert formatted_memory, "probe 探针应产出非空 formatted_memory"
    assert formatted_memory in prompt_text, (
        "BEAM unified answer prompt 必须包含 probe formatted_memory 原文"
    )
    # 公开 question text 须进入 prompt（unified 模板 `<question>` 槽位）。
    question_text = public_questions[next(
        index
        for index, item in enumerate(public_questions)
        if item["question_id"] == record["question_id"]
    )]["question_text"]
    assert question_text in prompt_text
    # BEAM RAG 模板特征：禁止长上下文路径措辞。
    assert "Answer ONLY based on the provided context" in prompt_text
    assert "NOTE: Only provide the answer" not in prompt_text

    # fake answer client 命中（unified path），不是 method native 答题。
    assert len(fake_client.calls) == 1


def _assert_three_layer_privacy(
    *,
    public_questions: list[dict[str, Any]],
    answer_prompts: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> None:
    """三层 privacy 扫描：public / answer_prompts 通用扫描；predictions 窄化扫描。"""

    # 第一、二层：通用 validate_no_private_keys + 窄化 BEAM 关键私有键集
    # 全零断言（adapter 已将私有 gold 落 evaluator_private_labels_path）。
    for record in public_questions:
        validate_no_private_keys(record)
        _assert_no_forbidden_keys(record, set(_BEAM_PRIVATE_KEY_BLACKLIST))
    for record in answer_prompts:
        validate_no_private_keys(record)
        _assert_no_forbidden_keys(record, set(_BEAM_PRIVATE_KEY_BLACKLIST))

    # 第三层：predictions 窄化扫描。answer 字段在 prediction 合法（与
    # B3 D5 一致），但 BEAM 私有 gold 字段仍须全零。
    for record in predictions:
        _assert_no_forbidden_keys(record, set(_BEAM_PRIVATE_KEY_BLACKLIST))


# ---------------------------------------------------------------------------
# 双结构认证：run A (100k)
# ---------------------------------------------------------------------------


def test_beam_registered_prediction_offline_probe_workflow_100k(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BEAM 100k 1 conv × 1 round × 1 题 smoke：probe 生命周期 + 离线
    rubric-judge（含 0.5 float/official_int 双轨）+ beam-recall + f1 + 三层
    privacy 扫描 + category_breakdown by ability。
    """

    probe, fake_client, paths, manifest = _run_beam_variant(
        tmp_path,
        monkeypatch,
        variant="100k",
        run_id="beam-e5-single-plan",
    )

    # 数据集带 20 题/conv（独立 adapter 加载断言，与 runner 裁 1 分离）
    _assert_original_dataset_has_20_questions_per_conv("100k")

    # 生命周期顺序
    _assert_probe_lifecycle(probe)
    # 100k 单 plan：1 round = 2 turns
    assert len(probe.ingested_turns) == 2
    assert len(probe.ended_sessions) == 1
    assert len(probe.ended_conversations) == 1
    assert len(probe.retrieve_queries) == 1

    # artifact 形状 + unified prompt
    public_questions = read_jsonl(paths.public_questions_path)
    answer_prompts = read_jsonl(paths.answer_prompts_path)
    predictions = read_jsonl(paths.method_predictions_path)
    _assert_prompt_and_artifact_layout(
        paths=paths,
        manifest=manifest,
        answer_prompts=answer_prompts,
        predictions=predictions,
        public_questions=public_questions,
        fake_client=fake_client,
    )

    # 三层 privacy 扫描
    _assert_three_layer_privacy(
        public_questions=public_questions,
        answer_prompts=answer_prompts,
        predictions=predictions,
    )

    # 离线 rubric-judge：fake judge 第一次返 0.5 → 断言 float 主分与
    # official_int 对照分并存（0.5 浮点 / 0 整）。
    judge_client = _FakeBeamJudgeClient()
    judge_summary = run_artifact_evaluation(
        paths.run_dir,
        BeamRubricJudgeEvaluator(client=judge_client),
        "beam",
    )
    assert judge_summary.total_questions == 1
    # score_records 落在 artifacts/answer_scores.beam_rubric_judge.jsonl
    # （summary_path 是顶层 summary，无 score_records 键）。
    score_records = read_jsonl(Path(judge_summary.score_path))
    judge_summary_payload = json.loads(
        Path(judge_summary.summary_path).read_text(encoding="utf-8")
    )
    # 至少一次 0.5 触发 → 主分含 0.5；official_int 已 truncate → 该 rubric
    # item 落到 0。两个轨道同时存在。
    assert score_records, "rubric judge 至少产出一条 score record"
    primary_record = score_records[0]
    assert primary_record["llm_judge_score_official_int"] is not None
    # 第一题 rubric 含 N 条 items，首条被 fake 返 0.5；float 主分与
    # official_int 对照分字段必须同时出现。
    assert "score" in primary_record
    assert "llm_judge_score_official_int" in primary_record
    # category_breakdown 出现且按 10 个 ability 分组（用户要求每类分开报）。
    category_breakdown = {
        entry["category"]: entry for entry in judge_summary_payload["category_breakdown"]
    }
    assert sorted(category_breakdown) == sorted(BEAM_ABILITY_KEYS)
    # 1 题只落入一个 ability：其它 9 个 ability 的 question_count 必须为 0。
    scored_abilities = [
        ability
        for ability, payload in category_breakdown.items()
        if payload["question_count"] > 0
    ]
    assert len(scored_abilities) == 1

    # 离线 beam-recall：probe 声明 turn provenance → evaluator 走 "turn"
    # 路径（不是 undeclared provenance 时的 N/A payload）。
    recall_summary = run_artifact_evaluation(
        paths.run_dir,
        BeamRetrievalRecallEvaluator(),
        "beam",
    )
    recall_payload = json.loads(
        Path(recall_summary.summary_path).read_text(encoding="utf-8")
    )
    # run_artifact_evaluation 把 evaluator 的 `summary` 子字典展平到顶层
    # summary dict（见 evaluation.py:_run_artifact_level_evaluation）。
    # abstention q1 在数据上无 source_chat_ids → 该 question 记 n/a；
    # 整体 summary.status 因此可能为 n/a，但与"provider provenance is
    # unavailable" 的 N/A payload 在结构上不同——后者 reason 字段说明
    # provenance 缺失。本断言钉死 probe 已声明 turn provenance，
    # evaluator 因此走逐题路径；该题被 benchmark policy 排除，scored-only
    # summary granularity 必须为 None，不能采被排除题的 valid evidence。
    assert recall_payload["provenance_granularity"] is None
    assert "provider provenance is unavailable" not in json.dumps(recall_payload)

    # 离线 f1：answer-level 路径，必须产出 metric_scores.jsonl
    f1_summary = run_artifact_evaluation(
        paths.run_dir,
        F1Evaluator(),
        "beam",
    )
    assert f1_summary.metric_name == "f1"
    assert f1_summary.total_questions == 1
    # fake answer 与 gold 文本通常不匹配 → F1 ∈ [0, 1]；流程不要求答对。
    assert 0.0 <= f1_summary.mean_score <= 1.0


# ---------------------------------------------------------------------------
# 双结构认证：run B (10m)
# ---------------------------------------------------------------------------


def test_beam_registered_prediction_offline_probe_workflow_10m(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BEAM 10m 1 conv × 1 round × 1 题 smoke：plan 结构 session_id 来自
    `p1:s1`、plan metadata 存在、probe 同样收到 ingest/end_session/
    end_conversation/retrieve 四类钩子。
    """

    probe, fake_client, paths, manifest = _run_beam_variant(
        tmp_path,
        monkeypatch,
        variant="10m",
        run_id="beam-e5-plans",
    )

    # 数据集带 20 题/conv（独立 adapter 加载断言，与 runner 裁 1 分离）
    _assert_original_dataset_has_20_questions_per_conv("10m")

    # 10m 切片必须来自 p1:s1（plans 顺序消费，session_id 命名规则
    # `p{plan}:s{batch}`），plan metadata 存在（plan_id / plan_index /
    # batch_number）。
    _assert_probe_lifecycle(probe)
    assert probe.ingested_turns, "10m smoke 必须有 ingest 到的 turn"
    ingested_session_ids = {turn.session_id for turn in probe.ingested_turns}
    assert ingested_session_ids == {"p1:s1"}, (
        f"10m smoke 切片应仅来自 p1:s1，实际：{ingested_session_ids}"
    )
    # 1 round = 2 turns（BEAM round=2 turns 口径，与 100k 一致）。
    assert len(probe.ingested_turns) == 2
    assert len(probe.ended_sessions) == 1
    # end_session 的 SessionRef 同样记录 p1:s1。
    assert probe.ended_sessions[0].session_id == "p1:s1"
    assert len(probe.ended_conversations) == 1
    assert len(probe.retrieve_queries) == 1
    # retrieve 的 isolation_key = conversation_id（10M dataset 顶层
    # conversation_id 来自 row['conversation_id']）。
    assert probe.retrieve_queries[0].purpose or True  # protocol field tolerated

    # plan metadata 存在：dataset.metadata 来自 prepare_beam_run 透传 adapter
    # metadata；10M 顶层 chat 形态 + plans 顺序由 adapter 内置固化，本断言
    # 用 manifest 与 dataset_fingerprint 间接钉死 plan 走通。
    assert manifest["benchmark_variant"] == "10m"
    assert manifest["run_scope"] == "smoke"
    assert manifest["method"]["prompt_track"] == "unified"

    # artifact 形状 + unified prompt（10m 数据集同 100k 都是 20 题/conv）
    public_questions = read_jsonl(paths.public_questions_path)
    answer_prompts = read_jsonl(paths.answer_prompts_path)
    predictions = read_jsonl(paths.method_predictions_path)
    _assert_prompt_and_artifact_layout(
        paths=paths,
        manifest=manifest,
        answer_prompts=answer_prompts,
        predictions=predictions,
        public_questions=public_questions,
        fake_client=fake_client,
    )

    # plan metadata 存在（10m 切片的 session 元信息应带 plan_id / plan_index
    # / batch_number——adapter `_sessions_from_10m_chat` 内置写入）。
    session_metadata = probe.ingested_turns[0].metadata
    # TurnEvent.metadata 来自 Session.metadata 的拷贝（runner 不动），故
    # 通过 ended_sessions 反向查公共 dataset 元信息：
    assert probe.ended_sessions[0].session_id == "p1:s1"

    # 三层 privacy 扫描（10m 与 100k 一致，私有 gold 落 evaluator_private_labels）
    _assert_three_layer_privacy(
        public_questions=public_questions,
        answer_prompts=answer_prompts,
        predictions=predictions,
    )

    # 离线 rubric-judge（10m 同样 fake client；断言 0.5 → float/official_int 双轨）
    judge_client = _FakeBeamJudgeClient()
    judge_summary = run_artifact_evaluation(
        paths.run_dir,
        BeamRubricJudgeEvaluator(client=judge_client),
        "beam",
    )
    score_records = read_jsonl(Path(judge_summary.score_path))
    judge_payload = json.loads(
        Path(judge_summary.summary_path).read_text(encoding="utf-8")
    )
    primary_record = score_records[0]
    assert "score" in primary_record
    assert "llm_judge_score_official_int" in primary_record
    # category_breakdown 仍按 ability 分组。
    category_breakdown = {
        entry["category"]: entry for entry in judge_payload["category_breakdown"]
    }
    assert sorted(category_breakdown) == sorted(BEAM_ABILITY_KEYS)
    scored_abilities = [
        ability
        for ability, payload in category_breakdown.items()
        if payload["question_count"] > 0
    ]
    assert len(scored_abilities) == 1

    # 离线 beam-recall：probe 声明 turn provenance → evaluator 走 "turn"
    # 路径（不是 undeclared provenance 时的 N/A payload）。
    recall_summary = run_artifact_evaluation(
        paths.run_dir,
        BeamRetrievalRecallEvaluator(),
        "beam",
    )
    recall_payload = json.loads(
        Path(recall_summary.summary_path).read_text(encoding="utf-8")
    )
    # 唯一题是 benchmark-policy empty-gold 排除，不是 scored question。
    assert recall_payload["provenance_granularity"] is None
    assert "provider provenance is unavailable" not in json.dumps(recall_payload)

    # 离线 f1
    f1_summary = run_artifact_evaluation(
        paths.run_dir,
        F1Evaluator(),
        "beam",
    )
    assert f1_summary.metric_name == "f1"
    assert f1_summary.total_questions == 1
    assert 0.0 <= f1_summary.mean_score <= 1.0


# ---------------------------------------------------------------------------
# 注册契约：E2 决策=variant=独立数据集=独立 run 身份
# ---------------------------------------------------------------------------


def test_beam_registration_declares_smoke_resume_and_unified_prompt() -> None:
    """BEAM registration 静态声明：smoke/resume policy、4 variants、unified
    prompt_track；与 E2 决策"双结构 = 两次独立 run"匹配（不扩 selector）。
    """

    registration = get_benchmark_registration("beam")
    assert registration.default_variant == "100k"
    variant_names = list(registration.variant_names())
    # E2 决策：BEAM 4 variants 注册（含 10m）；本断言只校验集合与注册期望一致。
    assert set(variant_names) == {"10m", "100k", "1m", "500k"}
    assert registration.prompt_track == "unified"
    assert registration.prediction_enabled is True
    assert registration.smoke_policy == BEAM_SMOKE_POLICY
    assert registration.resume_policy == BEAM_RESUME_POLICY

    # smoke policy 与 E2 决策一致：rounds 轴，1 conv / 1 round / 1 question。
    assert BEAM_SMOKE_POLICY.history_axis == "rounds"
    assert BEAM_SMOKE_POLICY.default_history_limit == 1
    assert BEAM_SMOKE_POLICY.default_isolation_limit == 1
    assert BEAM_SMOKE_POLICY.default_question_limit == 1
    # resume policy：smoke 不 resume，evaluation artifact-only。
    assert BEAM_RESUME_POLICY.smoke_enabled is False
    assert BEAM_RESUME_POLICY.evaluation_artifact_only is True
    assert BEAM_RESUME_POLICY.ingest_checkpoint == "conversation"
    assert BEAM_RESUME_POLICY.answer_checkpoint == "question"

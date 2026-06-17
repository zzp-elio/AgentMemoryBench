"""测试通用 prediction CLI 的 Mem0-LoCoMo 装配与成本保护。

本模块只测试纯配置和数据裁剪逻辑，不创建真实 Mem0 backend，也不调用外部 API。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.cli import run_prediction as prediction_cli
from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    PreparedBenchmarkRun,
    RunScope,
)
from memory_benchmark.benchmark_adapters.locomo import build_locomo_smoke_dataset
from memory_benchmark.core import (
    Conversation,
    Dataset,
    GoldAnswerInfo,
    MethodCapability,
    Question,
    Session,
    TaskFamily,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.methods.mem0_adapter import Mem0Config
from memory_benchmark.observability.efficiency import (
    ModelDescriptor,
    RetrievalObservationContract,
)
from memory_benchmark.runners.ingest_resume import TurnIngestCheckpointStore
from memory_benchmark.cli.run_prediction import (
    load_completed_conversation_ids,
    run_registered_conversation_qa_prediction,
    resolve_prediction_max_workers,
    resolve_mem0_profile,
)


pytestmark = pytest.mark.unit


def _build_smoke_source_dataset() -> Dataset:
    """构造可验证 evidence 范围选择的三 turn 数据集。"""

    conversation_id = "conv-1"
    inside_question = Question("q-inside", conversation_id, "Inside?")
    outside_question = Question("q-outside", conversation_id, "Outside?")
    return Dataset(
        dataset_name="locomo",
        conversations=[
            Conversation(
                conversation_id=conversation_id,
                sessions=[
                    Session(
                        session_id="s1",
                        turns=[
                            Turn("t1", "Alice", "first"),
                            Turn("t2", "Bob", "second"),
                        ],
                    ),
                    Session(
                        session_id="s2",
                        turns=[Turn("t3", "Alice", "third")],
                    ),
                ],
                questions=[outside_question, inside_question],
                gold_answers={
                    "q-outside": GoldAnswerInfo(
                        question_id="q-outside",
                        answer="third",
                        evidence=["t3"],
                    ),
                    "q-inside": GoldAnswerInfo(
                        question_id="q-inside",
                        answer="first",
                        evidence=["t1"],
                    ),
                },
            )
        ],
    )


def _build_two_conversation_smoke_source_dataset() -> Dataset:
    """构造两个都能在前两 turn 找到完整 evidence 的 conversation。"""

    first = _build_smoke_source_dataset().conversations[0]
    second_question = Question("q-second", "conv-2", "Second?")
    second = Conversation(
        conversation_id="conv-2",
        sessions=[
            Session(
                session_id="s1",
                turns=[
                    Turn("u1", "Carol", "alpha"),
                    Turn("u2", "Dave", "beta"),
                ],
            )
        ],
        questions=[second_question],
        gold_answers={
            "q-second": GoldAnswerInfo(
                question_id="q-second",
                answer="beta",
                evidence=["u2"],
            )
        },
    )
    return Dataset(
        dataset_name="locomo",
        conversations=[first, second],
    )


def _build_prepared_run(
    *,
    dataset_name: str,
    variant: str,
    run_scope: RunScope,
) -> PreparedBenchmarkRun:
    """构造带 variant/run scope metadata 的 prepared benchmark 结果。"""

    source_dataset = _build_smoke_source_dataset()
    return PreparedBenchmarkRun(
        variant=variant,
        run_scope=run_scope,
        dataset=Dataset(
            dataset_name=dataset_name,
            conversations=list(source_dataset.conversations),
            metadata={
                "variant": variant,
                "run_scope": run_scope.value,
            },
        ),
        source_relative_paths=(Path(f"sources/{variant}.json"),),
    )


def test_resolve_mem0_profile_requires_explicit_api_confirmation() -> None:
    """任何真实 Mem0 profile 都必须显式确认 API 消耗。"""

    with pytest.raises(ConfigurationError, match="confirm-api"):
        resolve_mem0_profile(
            profile_name="smoke",
            confirm_api=False,
            confirm_full=False,
        )


def test_official_full_requires_second_cost_confirmation() -> None:
    """全量 profile 除 API 确认外还必须单独确认全量成本。"""

    with pytest.raises(ConfigurationError, match="confirm-full"):
        resolve_mem0_profile(
            profile_name="official-full",
            confirm_api=True,
            confirm_full=False,
        )

    config = resolve_mem0_profile(
        profile_name="official-full",
        confirm_api=True,
        confirm_full=True,
    )
    assert config.top_k == 200
    assert config.max_workers == 10


def test_resolve_mem0_profile_reads_real_values_from_toml(
    tmp_path: Path,
) -> None:
    """prediction profile 必须读取项目 TOML，不能继续使用 classmethod 硬编码。"""

    profile_path = tmp_path / "configs" / "methods" / "mem0.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
        [smoke]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 17
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true

        [official_full]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 200
        max_workers = 10
        ingestion_chunk_size = 1
        infer = true
        """,
        encoding="utf-8",
    )

    config = resolve_mem0_profile(
        profile_name="smoke",
        confirm_api=True,
        confirm_full=False,
        project_root=tmp_path,
    )

    assert config.top_k == 17
    assert config.profile_name == "smoke"


def test_unknown_profile_is_rejected() -> None:
    """未知 profile 不能静默回退到 smoke 或全量参数。"""

    with pytest.raises(ConfigurationError, match="Unknown Mem0 profile"):
        resolve_mem0_profile(
            profile_name="cheap-ish",
            confirm_api=True,
            confirm_full=True,
        )


def test_smoke_dataset_keeps_only_turns_covering_one_private_evidence_set() -> None:
    """smoke 应选 evidence 完全落在截断历史中的一道题，但不公开 evidence。"""

    smoke_dataset = build_locomo_smoke_dataset(
        _build_smoke_source_dataset(),
        turn_limit=2,
    )

    conversation = smoke_dataset.conversations[0]
    assert [
        turn.turn_id
        for session in conversation.sessions
        for turn in session.turns
    ] == ["t1", "t2"]
    assert [question.question_id for question in conversation.questions] == [
        "q-inside"
    ]
    assert set(conversation.gold_answers) == {"q-inside"}
    assert "evidence" not in str(conversation.to_public_dict()).lower()


def test_smoke_dataset_can_select_two_independent_conversations() -> None:
    """并发 smoke 应为每个 conversation 独立裁剪历史并选择一道可回答问题。"""

    smoke_dataset = build_locomo_smoke_dataset(
        _build_two_conversation_smoke_source_dataset(),
        turn_limit=2,
        conversation_limit=2,
    )

    assert [
        conversation.conversation_id
        for conversation in smoke_dataset.conversations
    ] == ["conv-1", "conv-2"]
    assert [
        conversation.questions[0].question_id
        for conversation in smoke_dataset.conversations
    ] == ["q-inside", "q-second"]
    assert smoke_dataset.metadata["smoke_conversation_limit"] == 2


def test_smoke_concurrency_override_is_bounded_and_does_not_change_full() -> None:
    """smoke 只允许最多两个 worker，official-full 必须继续使用官方十并发。"""

    smoke = Mem0Config.smoke()
    full = Mem0Config.official_full()

    assert resolve_prediction_max_workers(smoke, smoke_max_workers=None) == 1
    assert resolve_prediction_max_workers(smoke, smoke_max_workers=2) == 2
    assert resolve_prediction_max_workers(full, smoke_max_workers=None) == 10

    with pytest.raises(ConfigurationError, match="at most 2"):
        resolve_prediction_max_workers(smoke, smoke_max_workers=3)
    with pytest.raises(ConfigurationError, match="smoke-only"):
        resolve_prediction_max_workers(full, smoke_max_workers=2)


def test_smoke_dataset_rejects_history_without_answerable_question() -> None:
    """截断历史不覆盖任何 evidence 时应报错，不能执行无意义付费 smoke。"""

    dataset = _build_smoke_source_dataset()
    dataset.conversations[0].gold_answers["q-inside"].evidence = ["t3"]

    with pytest.raises(ConfigurationError, match="evidence"):
        build_locomo_smoke_dataset(dataset, turn_limit=2)


def test_load_completed_conversation_ids_reads_only_completed_rows(
    tmp_path: Path,
) -> None:
    """resume 只附着 checkpoint 中明确完成写入的 conversation namespace。"""

    checkpoint = tmp_path / "checkpoints" / "conversation_status.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text(
        """
        {
          "conv-1": {"status": "completed"},
          "conv-2": {"status": "failed"},
          "conv-3": {"status": "running"}
        }
        """,
        encoding="utf-8",
    )

    assert load_completed_conversation_ids(tmp_path) == {"conv-1"}


def test_load_completed_conversation_ids_includes_completed_turn_checkpoint(
    tmp_path: Path,
) -> None:
    """coarse 状态缺失时，只附着逐 turn 已 completed 的 namespace。"""

    conversations = _build_two_conversation_smoke_source_dataset().conversations
    store = TurnIngestCheckpointStore(
        tmp_path / "checkpoints" / "ingest_turns"
    )
    store.mark_started("conv-1", 0, "t1", total_turns=3)
    store.mark_turn_completed("conv-1", 0, "t1", total_turns=3)
    store.mark_started("conv-1", 1, "t2", total_turns=3)
    store.mark_turn_completed("conv-1", 1, "t2", total_turns=3)
    store.mark_started("conv-1", 2, "t3", total_turns=3)
    store.mark_turn_completed("conv-1", 2, "t3", total_turns=3)
    store.mark_conversation_completed("conv-1", total_turns=3)
    store.mark_started("conv-2", 0, "u1", total_turns=2)
    store.mark_turn_completed("conv-2", 0, "u1", total_turns=2)

    assert load_completed_conversation_ids(
        tmp_path,
        conversations=conversations,
    ) == {"conv-1"}


def test_registered_prediction_builds_system_from_registry_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """统一 service 应返回单 child batch，并通过 registration factory 装配 method。"""

    config = Mem0Config.smoke()
    fake_system = object()
    expected_summary = SimpleNamespace(
        run_id="run-1",
        dataset_name="locomo",
        completed_conversations=1,
        completed_questions=1,
    )
    build_contexts: list[object] = []
    runner_calls: list[dict[str, object]] = []
    path_settings = SimpleNamespace(
        project_root=tmp_path,
        outputs_root=tmp_path / "outputs",
    )
    prepared_run = _build_prepared_run(
        dataset_name="locomo",
        variant="locomo10",
        run_scope=RunScope.SMOKE,
    )
    prepare_calls: list[BenchmarkLoadRequest] = []

    def _prepare(
        project_root: Path,
        request: BenchmarkLoadRequest,
    ) -> PreparedBenchmarkRun:
        """记录 prepare 请求并返回固定数据集。"""

        assert project_root == tmp_path
        prepare_calls.append(request)
        return prepared_run

    benchmark_registration = SimpleNamespace(
        name="locomo",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="locomo10",
        variant_names=lambda: ("locomo10",),
        prepare=_prepare,
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        name="mem0",
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
        system_factory=lambda context: build_contexts.append(context) or fake_system,
        source_identity_factory=lambda settings: {"source_sha256": "abc"},
        model_name_getter=lambda selected: selected.reader_model,
        max_workers_getter=lambda selected: selected.max_workers,
        workload_estimator=None,
        allow_smoke_worker_override=True,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_benchmark_registration",
        lambda name: benchmark_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_method_registration",
        lambda name: method_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_method_profile",
        lambda **kwargs: config,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda project_root: path_settings,
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda project_root: object(),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_completed_conversation_ids",
        lambda run_dir, conversations: {"conv-1"},
    )
    monkeypatch.setattr(
        prediction_cli,
        "_preflight_prediction_run",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        prediction_cli,
        "run_predictions",
        lambda **kwargs: runner_calls.append(kwargs) or expected_summary,
    )

    result = run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="mem0",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="run-1",
        resume=True,
        confirm_api=True,
        confirm_full=False,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        smoke_max_workers=None,
    )

    assert hasattr(prediction_cli, "PredictionBatchResult")
    assert result.benchmark == "locomo"
    assert result.selector == "locomo10"
    assert len(result.runs) == 1
    assert result.runs[0].variant == "locomo10"
    assert result.runs[0].run_id == "run-1"
    assert result.runs[0].summary is expected_summary
    assert prepare_calls == [
        BenchmarkLoadRequest(
            variant="locomo10",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=2,
            smoke_conversation_limit=1,
        )
    ]
    assert build_contexts[0].completed_conversations[0].conversation_id == "conv-1"
    assert build_contexts[0].completed_conversations[0].gold_answers == {}
    assert runner_calls[0]["system"] is fake_system
    assert runner_calls[0]["benchmark_variant"] == "locomo10"
    assert runner_calls[0]["run_scope"] is RunScope.SMOKE
    assert runner_calls[0]["method_manifest"]["source"] == {
        "source_sha256": "abc"
    }
    assert runner_calls[0]["source_paths"] == (
        tmp_path / "sources/locomo10.json",
    )


def test_registered_prediction_rejects_cost_before_loading_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未确认 API 成本时不得读取 `.env`、dataset 或构造 method。"""

    benchmark_registration = SimpleNamespace(
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
        workload_estimator=None,
        allow_smoke_worker_override=True,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_benchmark_registration",
        lambda name: benchmark_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_method_registration",
        lambda name: method_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda **kwargs: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("cost guard must run before .env loading")
        ),
        raising=False,
    )

    with pytest.raises(ConfigurationError, match="confirm-api"):
        run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="mem0",
            benchmark_name="locomo",
            profile_name="smoke",
            confirm_api=False,
        )


def test_registered_prediction_allows_mem0_smoke_worker_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """允许 override 的 Mem0 应继续把 smoke_max_workers 传入 policy。"""

    config = Mem0Config.smoke()
    fake_system = object()
    expected_summary = SimpleNamespace(run_id="run-1")
    path_settings = SimpleNamespace(
        project_root=tmp_path,
        outputs_root=tmp_path / "outputs",
    )
    prepared_run = _build_prepared_run(
        dataset_name="locomo",
        variant="locomo10",
        run_scope=RunScope.SMOKE,
    )
    benchmark_registration = SimpleNamespace(
        name="locomo",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="locomo10",
        variant_names=lambda: ("locomo10",),
        prepare=lambda project_root, request: prepared_run,
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        name="mem0",
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
        system_factory=lambda context: fake_system,
        source_identity_factory=lambda settings: {"source_sha256": "abc"},
        model_name_getter=lambda selected: selected.reader_model,
        max_workers_getter=lambda selected: selected.max_workers,
        workload_estimator=None,
        allow_smoke_worker_override=True,
    )
    runner_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        prediction_cli,
        "get_benchmark_registration",
        lambda name: benchmark_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_method_registration",
        lambda name: method_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_method_profile",
        lambda **kwargs: config,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda project_root: path_settings,
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda project_root: object(),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "_preflight_prediction_run",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        prediction_cli,
        "run_predictions",
        lambda **kwargs: runner_calls.append(kwargs) or expected_summary,
    )

    result = run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="mem0",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="run-1",
        resume=False,
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        smoke_max_workers=2,
    )

    assert result.runs[0].summary is expected_summary
    assert runner_calls[0]["policy"].max_workers == 2


def test_registered_prediction_wires_efficiency_observability_when_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开启效率观测时 registered path 必须把同一身份传给 preflight/factory/runner。"""

    config = Mem0Config.smoke()
    fake_system = object()
    expected_summary = SimpleNamespace(run_id="run-1")
    path_settings = SimpleNamespace(
        project_root=tmp_path,
        outputs_root=tmp_path / "outputs",
    )
    prepared_run = _build_prepared_run(
        dataset_name="locomo",
        variant="locomo10",
        run_scope=RunScope.SMOKE,
    )
    benchmark_registration = SimpleNamespace(
        name="locomo",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="locomo10",
        variant_names=lambda: ("locomo10",),
        prepare=lambda project_root, request: prepared_run,
        prediction_enabled=True,
    )
    model_inventory = (
        ModelDescriptor(
            model_id="mem0-answer-llm",
            model_name="gpt-4o-mini",
            model_role="answer_llm",
            execution_mode="api",
            tokenizer_name="gpt-4o-mini",
        ),
    )
    retrieval_contract = RetrievalObservationContract(
        required_by_profile=True,
        supported_by_method=True,
    )
    build_contexts: list[object] = []
    preflight_calls: list[dict[str, object]] = []
    runner_calls: list[dict[str, object]] = []
    method_registration = SimpleNamespace(
        name="mem0",
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
        system_factory=lambda context: build_contexts.append(context) or fake_system,
        source_identity_factory=lambda settings: {"source_sha256": "abc"},
        model_name_getter=lambda selected: selected.reader_model,
        max_workers_getter=lambda selected: selected.max_workers,
        workload_estimator=None,
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=lambda selected: model_inventory,
        efficiency_instrumentation_identity_getter=lambda settings, selected, source_identity: {
            "collector_schema": 1,
            "wrapper_sha256": "def",
            "source_sha256": source_identity["source_sha256"],
        },
        retrieval_observation_contract_getter=lambda selected: retrieval_contract,
    )

    monkeypatch.setattr(
        prediction_cli,
        "get_benchmark_registration",
        lambda name: benchmark_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_method_registration",
        lambda name: method_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_method_profile",
        lambda **kwargs: config,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda project_root: path_settings,
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda project_root: object(),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "_preflight_prediction_run",
        lambda **kwargs: preflight_calls.append(kwargs),
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_completed_conversation_ids",
        lambda *args, **kwargs: set(),
    )
    monkeypatch.setattr(
        prediction_cli,
        "run_predictions",
        lambda **kwargs: runner_calls.append(kwargs) or expected_summary,
    )

    run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="mem0",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="run-1",
        confirm_api=True,
        enable_efficiency_observability=True,
    )

    assert len(preflight_calls) == 1
    assert len(build_contexts) == 1
    assert len(runner_calls) == 1
    collector = preflight_calls[0]["efficiency_collector"]
    assert collector is build_contexts[0].efficiency_collector
    assert collector is runner_calls[0]["efficiency_collector"]
    assert preflight_calls[0]["model_inventory"] == model_inventory
    assert runner_calls[0]["model_inventory"] == model_inventory
    assert preflight_calls[0]["instrumentation_identity"] == {
        "collector_schema": 1,
        "wrapper_sha256": "def",
        "source_sha256": "abc",
    }
    assert runner_calls[0]["instrumentation_identity"] == preflight_calls[0][
        "instrumentation_identity"
    ]
    assert preflight_calls[0]["retrieval_observation_contract"] is retrieval_contract
    assert runner_calls[0]["retrieval_observation_contract"] is retrieval_contract


def test_all_expands_in_registration_order_and_uses_explicit_variant_suffixes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LongMemEval `all` 必须按注册顺序展开，并为每个 child 追加 variant 后缀。"""

    config = Mem0Config.smoke()
    path_settings = SimpleNamespace(
        project_root=tmp_path,
        outputs_root=tmp_path / "outputs",
    )
    prepared_runs = {
        "s_cleaned": _build_prepared_run(
            dataset_name="longmemeval",
            variant="s_cleaned",
            run_scope=RunScope.SMOKE,
        ),
        "m_cleaned": _build_prepared_run(
            dataset_name="longmemeval",
            variant="m_cleaned",
            run_scope=RunScope.SMOKE,
        ),
    }
    prepare_calls: list[str] = []
    runner_calls: list[dict[str, object]] = []

    def _prepare(
        project_root: Path,
        request: BenchmarkLoadRequest,
    ) -> PreparedBenchmarkRun:
        """按请求 variant 返回对应 prepared child。"""

        assert project_root == tmp_path
        prepare_calls.append(request.variant)
        return prepared_runs[request.variant]

    benchmark_registration = SimpleNamespace(
        name="longmemeval",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="s_cleaned",
        variant_names=lambda: ("s_cleaned", "m_cleaned"),
        prepare=_prepare,
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        name="mem0",
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
        system_factory=lambda context: object(),
        source_identity_factory=lambda settings: {"source_sha256": "abc"},
        model_name_getter=lambda selected: selected.reader_model,
        max_workers_getter=lambda selected: selected.max_workers,
        workload_estimator=None,
        allow_smoke_worker_override=True,
    )

    monkeypatch.setattr(
        prediction_cli,
        "get_benchmark_registration",
        lambda name: benchmark_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_method_registration",
        lambda name: method_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_method_profile",
        lambda **kwargs: config,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda project_root: path_settings,
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda project_root: object(),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_completed_conversation_ids",
        lambda *args, **kwargs: set(),
    )
    monkeypatch.setattr(
        prediction_cli,
        "_preflight_prediction_run",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        prediction_cli,
        "run_predictions",
        lambda **kwargs: runner_calls.append(kwargs)
        or SimpleNamespace(run_id=kwargs["run_context"].run_id),
    )

    result = run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="mem0",
        benchmark_name="longmemeval",
        profile_name="smoke",
        variant="all",
        run_id="exp1",
        confirm_api=True,
    )

    assert result.selector == "all"
    assert prepare_calls == ["s_cleaned", "m_cleaned"]
    assert [child.variant for child in result.runs] == [
        "s_cleaned",
        "m_cleaned",
    ]
    assert [child.run_id for child in result.runs] == [
        "exp1-s-cleaned",
        "exp1-m-cleaned",
    ]
    assert [call["benchmark_variant"] for call in runner_calls] == [
        "s_cleaned",
        "m_cleaned",
    ]


def test_longmemeval_single_variant_run_id_uses_explicit_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多 variant benchmark 的单 concrete child 也必须追加 variant 后缀。"""

    config = Mem0Config.smoke()
    prepared_run = _build_prepared_run(
        dataset_name="longmemeval",
        variant="s_cleaned",
        run_scope=RunScope.SMOKE,
    )
    benchmark_registration = SimpleNamespace(
        name="longmemeval",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="s_cleaned",
        variant_names=lambda: ("s_cleaned", "m_cleaned"),
        prepare=lambda project_root, request: prepared_run,
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
        system_factory=lambda context: object(),
        source_identity_factory=lambda settings: {"source_sha256": "abc"},
        model_name_getter=lambda selected: selected.reader_model,
        max_workers_getter=lambda selected: selected.max_workers,
        workload_estimator=None,
        allow_smoke_worker_override=True,
    )
    monkeypatch.setattr(prediction_cli, "get_benchmark_registration", lambda name: benchmark_registration)
    monkeypatch.setattr(prediction_cli, "get_method_registration", lambda name: method_registration)
    monkeypatch.setattr(prediction_cli, "load_method_profile", lambda **kwargs: config)
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda project_root: object(),
        raising=False,
    )
    monkeypatch.setattr(prediction_cli, "_preflight_prediction_run", lambda **kwargs: None)
    monkeypatch.setattr(prediction_cli, "load_completed_conversation_ids", lambda *args, **kwargs: set())
    monkeypatch.setattr(
        prediction_cli,
        "run_predictions",
        lambda **kwargs: SimpleNamespace(run_id=kwargs["run_context"].run_id),
    )

    result = run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="mem0",
        benchmark_name="longmemeval",
        profile_name="smoke",
        variant="s_cleaned",
        run_id="exp1",
        confirm_api=True,
    )

    assert result.runs[0].run_id == "exp1-s-cleaned"


def test_locomo_run_id_does_not_add_single_variant_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单 variant benchmark 的显式 run_id 必须保持不变。"""

    config = Mem0Config.smoke()
    prepared_run = _build_prepared_run(
        dataset_name="locomo",
        variant="locomo10",
        run_scope=RunScope.SMOKE,
    )
    benchmark_registration = SimpleNamespace(
        name="locomo",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="locomo10",
        variant_names=lambda: ("locomo10",),
        prepare=lambda project_root, request: prepared_run,
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
        system_factory=lambda context: object(),
        source_identity_factory=lambda settings: {"source_sha256": "abc"},
        model_name_getter=lambda selected: selected.reader_model,
        max_workers_getter=lambda selected: selected.max_workers,
        workload_estimator=None,
        allow_smoke_worker_override=True,
    )
    monkeypatch.setattr(prediction_cli, "get_benchmark_registration", lambda name: benchmark_registration)
    monkeypatch.setattr(prediction_cli, "get_method_registration", lambda name: method_registration)
    monkeypatch.setattr(prediction_cli, "load_method_profile", lambda **kwargs: config)
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda project_root: object(),
        raising=False,
    )
    monkeypatch.setattr(prediction_cli, "_preflight_prediction_run", lambda **kwargs: None)
    monkeypatch.setattr(prediction_cli, "load_completed_conversation_ids", lambda *args, **kwargs: set())
    monkeypatch.setattr(
        prediction_cli,
        "run_predictions",
        lambda **kwargs: SimpleNamespace(run_id=kwargs["run_context"].run_id),
    )

    result = run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="mem0",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="exp1",
        confirm_api=True,
    )

    assert result.runs[0].run_id == "exp1"


def test_duplicate_variant_suffix_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式 base run_id 已含同 variant 后缀时必须拒绝，避免双重拼接。"""

    benchmark_registration = SimpleNamespace(
        name="longmemeval",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="s_cleaned",
        variant_names=lambda: ("s_cleaned", "m_cleaned"),
        prepare=lambda project_root, request: (_ for _ in ()).throw(
            AssertionError("duplicate suffix must fail before prepare")
        ),
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
    )
    monkeypatch.setattr(prediction_cli, "get_benchmark_registration", lambda name: benchmark_registration)
    monkeypatch.setattr(prediction_cli, "get_method_registration", lambda name: method_registration)
    monkeypatch.setattr(
        prediction_cli,
        "load_method_profile",
        lambda **kwargs: Mem0Config.smoke(),
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda **kwargs: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("duplicate suffix must fail before secret loading")
        ),
        raising=False,
    )

    with pytest.raises(ConfigurationError, match="run_id"):
        run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="mem0",
            benchmark_name="longmemeval",
            profile_name="smoke",
            variant="s_cleaned",
            run_id="exp1-s-cleaned",
            confirm_api=True,
        )


def test_other_registered_variant_suffix_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式 base run_id 含其他已注册 variant 后缀时也必须拒绝。"""

    benchmark_registration = SimpleNamespace(
        name="longmemeval",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="s_cleaned",
        variant_names=lambda: ("s_cleaned", "m_cleaned"),
        prepare=lambda project_root, request: (_ for _ in ()).throw(
            AssertionError("variant-suffixed base must fail before prepare")
        ),
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_benchmark_registration",
        lambda name: benchmark_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_method_registration",
        lambda name: method_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_method_profile",
        lambda **kwargs: Mem0Config.smoke(),
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda **kwargs: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )

    with pytest.raises(ConfigurationError, match="variant suffix"):
        run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="mem0",
            benchmark_name="longmemeval",
            profile_name="smoke",
            variant="m_cleaned",
            run_id="exp1-s-cleaned",
            confirm_api=True,
        )


def test_resume_requires_explicit_base_run_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resume 模式必须由用户显式提供 base run_id。"""

    benchmark_registration = SimpleNamespace(
        name="locomo",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="locomo10",
        variant_names=lambda: ("locomo10",),
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
    )
    monkeypatch.setattr(prediction_cli, "get_benchmark_registration", lambda name: benchmark_registration)
    monkeypatch.setattr(prediction_cli, "get_method_registration", lambda name: method_registration)
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda **kwargs: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )

    with pytest.raises(ConfigurationError, match="explicit existing run_id"):
        run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="mem0",
            benchmark_name="locomo",
            profile_name="smoke",
            resume=True,
            confirm_api=True,
        )


def test_second_child_preflight_failure_creates_no_output_or_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """任一 child 预检失败时，所有 child 都不能创建目录、读 secret 或构造 method。"""

    config = Mem0Config.smoke()
    path_settings = SimpleNamespace(
        project_root=tmp_path,
        outputs_root=tmp_path / "outputs",
    )
    prepared_runs = {
        "s_cleaned": _build_prepared_run(
            dataset_name="longmemeval",
            variant="s_cleaned",
            run_scope=RunScope.SMOKE,
        ),
        "m_cleaned": _build_prepared_run(
            dataset_name="longmemeval",
            variant="m_cleaned",
            run_scope=RunScope.SMOKE,
        ),
    }
    benchmark_registration = SimpleNamespace(
        name="longmemeval",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="s_cleaned",
        variant_names=lambda: ("s_cleaned", "m_cleaned"),
        prepare=lambda project_root, request: prepared_runs[request.variant],
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
        system_factory=lambda context: (_ for _ in ()).throw(
            AssertionError("factory must not run before all preflights pass")
        ),
        source_identity_factory=lambda settings: {"source_sha256": "abc"},
        model_name_getter=lambda selected: selected.reader_model,
        max_workers_getter=lambda selected: selected.max_workers,
        workload_estimator=None,
        allow_smoke_worker_override=True,
    )
    preflight_variants: list[str] = []
    openai_loaded: list[str] = []
    monkeypatch.setattr(prediction_cli, "get_benchmark_registration", lambda name: benchmark_registration)
    monkeypatch.setattr(prediction_cli, "get_method_registration", lambda name: method_registration)
    monkeypatch.setattr(prediction_cli, "load_method_profile", lambda **kwargs: config)
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda project_root: path_settings,
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda project_root: openai_loaded.append("loaded"),
        raising=False,
    )

    def _preflight(**kwargs):
        """第二个 child 预检失败。"""

        preflight_variants.append(kwargs["benchmark_variant"])
        if kwargs["benchmark_variant"] == "m_cleaned":
            raise ConfigurationError("second child preflight failed")

    monkeypatch.setattr(prediction_cli, "_preflight_prediction_run", _preflight)
    monkeypatch.setattr(
        prediction_cli,
        "run_predictions",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("runner must not start after preflight failure")
        ),
    )

    with pytest.raises(ConfigurationError, match="second child preflight failed"):
        run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="mem0",
            benchmark_name="longmemeval",
            profile_name="smoke",
            variant="all",
            run_id="exp1",
            confirm_api=True,
        )

    assert preflight_variants == ["s_cleaned", "m_cleaned"]
    assert openai_loaded == []
    assert not (tmp_path / "outputs" / "exp1-s-cleaned").exists()
    assert not (tmp_path / "outputs" / "exp1-m-cleaned").exists()


def test_openai_settings_load_only_after_all_preflights(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`.env` 读取必须晚于所有 child 预检，且只读取一次。"""

    config = Mem0Config.smoke()
    path_settings = SimpleNamespace(
        project_root=tmp_path,
        outputs_root=tmp_path / "outputs",
    )
    prepared_runs = {
        "s_cleaned": _build_prepared_run(
            dataset_name="longmemeval",
            variant="s_cleaned",
            run_scope=RunScope.SMOKE,
        ),
        "m_cleaned": _build_prepared_run(
            dataset_name="longmemeval",
            variant="m_cleaned",
            run_scope=RunScope.SMOKE,
        ),
    }
    events: list[str] = []
    benchmark_registration = SimpleNamespace(
        name="longmemeval",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="s_cleaned",
        variant_names=lambda: ("s_cleaned", "m_cleaned"),
        prepare=lambda project_root, request: prepared_runs[request.variant],
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
        system_factory=lambda context: events.append(
            f"factory:{context.storage_root.parent.name}"
        )
        or object(),
        source_identity_factory=lambda settings: {"source_sha256": "abc"},
        model_name_getter=lambda selected: selected.reader_model,
        max_workers_getter=lambda selected: selected.max_workers,
        workload_estimator=None,
        allow_smoke_worker_override=True,
    )
    monkeypatch.setattr(prediction_cli, "get_benchmark_registration", lambda name: benchmark_registration)
    monkeypatch.setattr(prediction_cli, "get_method_registration", lambda name: method_registration)
    monkeypatch.setattr(prediction_cli, "load_method_profile", lambda **kwargs: config)
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda project_root: path_settings,
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda project_root: events.append("openai") or object(),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "_preflight_prediction_run",
        lambda **kwargs: events.append(f"preflight:{kwargs['benchmark_variant']}"),
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_completed_conversation_ids",
        lambda *args, **kwargs: set(),
    )
    monkeypatch.setattr(
        prediction_cli,
        "run_predictions",
        lambda **kwargs: events.append(
            f"run:{kwargs['benchmark_variant']}"
        )
        or SimpleNamespace(run_id=kwargs["run_context"].run_id),
    )

    run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="mem0",
        benchmark_name="longmemeval",
        profile_name="smoke",
        variant="all",
        run_id="exp1",
        confirm_api=True,
    )

    assert events[:2] == ["preflight:s_cleaned", "preflight:m_cleaned"]
    assert events[2] == "openai"
    assert events[3:] == [
        "factory:exp1-s-cleaned",
        "run:s_cleaned",
        "factory:exp1-m-cleaned",
        "run:m_cleaned",
    ]


def test_symlink_child_run_path_outside_outputs_fails_before_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已有 child run symlink 若解析到 outputs 之外，必须在 prepare 前拒绝。"""

    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir()
    outside_root = tmp_path / "outside-run"
    outside_root.mkdir()
    (outputs_root / "exp1").symlink_to(outside_root, target_is_directory=True)

    benchmark_registration = SimpleNamespace(
        name="locomo",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="locomo10",
        variant_names=lambda: ("locomo10",),
        prepare=lambda project_root, request: (_ for _ in ()).throw(
            AssertionError("unsafe child destination must fail before prepare")
        ),
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_benchmark_registration",
        lambda name: benchmark_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_method_registration",
        lambda name: method_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda **kwargs: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=outputs_root,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_method_profile",
        lambda **kwargs: Mem0Config.smoke(),
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("unsafe child destination must fail before secret loading")
        ),
        raising=False,
    )

    with pytest.raises(ConfigurationError, match="outside outputs_root"):
        run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="mem0",
            benchmark_name="locomo",
            profile_name="smoke",
            run_id="exp1",
            confirm_api=True,
        )


def test_case_insensitive_child_run_destination_collision_fails_before_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """仅大小写不同的 child destination 必须跨平台保守拒绝。"""

    benchmark_registration = SimpleNamespace(
        name="demo",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        default_variant="A",
        variant_names=lambda: ("A", "a"),
        prepare=lambda project_root, request: (_ for _ in ()).throw(
            AssertionError("colliding child destinations must fail before prepare")
        ),
        prediction_enabled=True,
    )
    method_registration = SimpleNamespace(
        display_name="Mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.ANSWER_GENERATION,
            }
        ),
        requires_api=True,
        resolve_profile_section=lambda profile_name: profile_name,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_benchmark_registration",
        lambda name: benchmark_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "get_method_registration",
        lambda name: method_registration,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_path_settings",
        lambda **kwargs: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_method_profile",
        lambda **kwargs: Mem0Config.smoke(),
    )
    monkeypatch.setattr(
        prediction_cli,
        "load_openai_settings",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("colliding child destinations must fail before secret loading")
        ),
        raising=False,
    )

    with pytest.raises(ConfigurationError, match="case-insensitive"):
        run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="mem0",
            benchmark_name="demo",
            profile_name="smoke",
            variant="all",
            run_id="exp1",
            confirm_api=True,
        )


def test_run_mem0_locomo_prediction_returns_single_summary_from_batch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """兼容包装器应从单 child batch 中返回唯一 summary。"""

    expected_summary = SimpleNamespace(run_id="run-1")
    batch_result = SimpleNamespace(
        benchmark="locomo",
        selector="locomo10",
        runs=(
            SimpleNamespace(
                variant="locomo10",
                run_id="run-1",
                summary=expected_summary,
            ),
        ),
    )
    monkeypatch.setattr(
        prediction_cli,
        "run_registered_conversation_qa_prediction",
        lambda **kwargs: batch_result,
    )

    assert (
        prediction_cli.run_mem0_locomo_prediction(
            project_root=tmp_path,
            confirm_api=True,
        )
        is expected_summary
    )


def test_run_prediction_module_has_no_locomo_specific_generic_imports() -> None:
    """通用 registered service 源码不能再直接 import LoCoMo helper。"""

    source = Path(prediction_cli.__file__).read_text(encoding="utf-8")
    assert "build_locomo_smoke_dataset" not in source
    assert "benchmark_adapters.locomo" not in source

"""测试 MemoryOS 通过统一 registry 进入通用 prediction runner 的装配。"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    PreparedBenchmarkRun,
    RunScope,
)
from memory_benchmark.benchmark_adapters.locomo import (
    LOCOMO_SOURCE_PATH,
    build_locomo_smoke_dataset,
)
from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.config import AnswerLLMSettings, OpenAISettings
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    Question,
    AnswerPromptResult,
    Session,
    Turn,
)
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.methods import memoryos_adapter as memoryos_adapter_module
from memory_benchmark.methods.memoryos_adapter import MemoryOS as RealMemoryOS
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.observability import RunContext
from memory_benchmark.observability.efficiency.entities import ModelDescriptor
from memory_benchmark.runners import prediction as prediction_runner_module
from memory_benchmark.storage import read_jsonl


pytestmark = pytest.mark.unit


def _write_memoryos_profiles(project_root: Path) -> None:
    """写入供 registry loader 使用的最小 MemoryOS TOML。"""

    profile_path = project_root / "configs" / "methods" / "memoryos.toml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        """
[smoke]
llm_model = "gpt-4o-mini"
embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
short_term_capacity = 1
mid_term_capacity = 2000
long_term_knowledge_capacity = 100
retrieval_queue_capacity = 7
mid_term_heat_threshold = 5.0
mid_term_similarity_threshold = 0.6
segment_similarity_threshold = 0.1
page_similarity_threshold = 0.1
knowledge_threshold = 0.01
top_k_sessions = 5
top_k_knowledge = 20
api_timeout_seconds = 120
api_max_retries = 8
api_retry_wait_seconds = 5
api_retry_backoff_multiplier = 2
api_retry_max_wait_seconds = 60
suppress_official_stdout = true
max_workers = 1
longmemeval_prompt_profile = "memoryos-pypi-retrieve-v1"

[official_full]
llm_model = "gpt-4o-mini"
embedding_model_name = "sentence-transformers/all-MiniLM-L6-v2"
short_term_capacity = 1
mid_term_capacity = 2000
long_term_knowledge_capacity = 100
retrieval_queue_capacity = 7
mid_term_heat_threshold = 5.0
mid_term_similarity_threshold = 0.6
segment_similarity_threshold = 0.1
page_similarity_threshold = 0.1
knowledge_threshold = 0.01
top_k_sessions = 5
top_k_knowledge = 20
api_timeout_seconds = 120
api_max_retries = 8
api_retry_wait_seconds = 5
api_retry_backoff_multiplier = 2
api_retry_max_wait_seconds = 60
suppress_official_stdout = true
max_workers = 1
longmemeval_prompt_profile = "memoryos-pypi-retrieve-v1"
""",
        encoding="utf-8",
    )


def _build_locomo_like_dataset() -> Dataset:
    """构造可被 LoCoMo smoke helper 裁剪的最小数据集。"""

    question_one = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="前两轮里说了什么？",
    )
    question_two = Question(
        question_id="conv-1:q2",
        conversation_id="conv-1",
        text="后两轮里说了什么？",
    )
    return Dataset(
        dataset_name="locomo",
        conversations=[
            Conversation(
                conversation_id="conv-1",
                sessions=[
                    Session(
                        session_id="session_1",
                        turns=[
                            Turn("conv-1:t1", "Alice", "第一轮用户"),
                            Turn("conv-1:t2", "Bob", "第一轮助手"),
                            Turn("conv-1:t3", "Alice", "第二轮用户"),
                            Turn("conv-1:t4", "Bob", "第二轮助手"),
                        ],
                    )
                ],
                questions=[question_one, question_two],
                gold_answers={
                    question_one.question_id: GoldAnswerInfo(
                        question_id=question_one.question_id,
                        answer="前两轮答案",
                        evidence=["conv-1:t1", "conv-1:t2"],
                    ),
                    question_two.question_id: GoldAnswerInfo(
                        question_id=question_two.question_id,
                        answer="后两轮答案",
                        evidence=["conv-1:t3", "conv-1:t4"],
                    ),
                },
                metadata={"speaker_a": "Alice", "speaker_b": "Bob"},
            )
        ],
    )


def _build_locomo_prepared_run(
    *,
    turn_limit: int = 2,
    conversation_limit: int = 1,
    run_scope: RunScope = RunScope.SMOKE,
) -> PreparedBenchmarkRun:
    """构造通过 registration.prepare 返回的 LoCoMo prepared run。"""

    source_dataset = _build_locomo_like_dataset()
    if run_scope is RunScope.SMOKE:
        dataset = build_locomo_smoke_dataset(
            source_dataset,
            turn_limit=turn_limit,
            conversation_limit=conversation_limit,
        )
    else:
        dataset = source_dataset
    metadata = dict(dataset.metadata)
    metadata.update(
        {
            "variant": "locomo10",
            "run_scope": run_scope.value,
        }
    )
    return PreparedBenchmarkRun(
        variant="locomo10",
        run_scope=run_scope,
        dataset=Dataset(
            dataset_name=dataset.dataset_name,
            conversations=list(dataset.conversations),
            metadata=metadata,
        ),
        source_relative_paths=(LOCOMO_SOURCE_PATH,),
    )


def _patch_locomo_registration(
    monkeypatch: pytest.MonkeyPatch,
    *,
    prepared_run: PreparedBenchmarkRun | None = None,
) -> list[BenchmarkLoadRequest]:
    """注入最小 benchmark registration，并返回 prepare 调用记录。"""

    prepare_calls: list[BenchmarkLoadRequest] = []

    def _prepare(
        project_root: Path,
        request: BenchmarkLoadRequest,
    ) -> PreparedBenchmarkRun:
        """记录请求，并返回固定 prepared run。"""

        prepare_calls.append(request)
        if prepared_run is None:
            raise AssertionError("prepare must not run in this scenario")
        assert isinstance(project_root, Path)
        return prepared_run

    registration = SimpleNamespace(
        name="locomo",
        task_family=run_prediction_module.get_benchmark_registration("locomo").task_family,
        required_capabilities=run_prediction_module.get_benchmark_registration(
            "locomo"
        ).required_capabilities,
        default_variant="locomo10",
        variant_names=lambda: ("locomo10",),
        prepare=_prepare,
        prediction_enabled=True,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda benchmark_name: registration,
    )
    return prepare_calls


class _FakeAdapter:
    """返回固定数据集并记录 load limit 的假 adapter。"""

    def __init__(self, dataset: Dataset):
        """保存固定数据集，并初始化 adapter 调用记录。"""

        self.dataset = dataset
        self.load_limits: list[int | None] = []

    def load(self, limit: int | None = None) -> Dataset:
        """返回测试数据集。"""

        self.load_limits.append(limit)
        return self.dataset


class _FakeMemoryOS(BaseMemoryProvider):
    """用于验证 registry factory 装配顺序的假 MemoryOS。"""

    instances: list["_FakeMemoryOS"] = []

    def __init__(
        self,
        openai_api_key: str | None = None,
        openai_base_url: str | None = None,
        storage_root: str | Path | None = None,
        config=None,
        efficiency_collector=None,
        consume_granularity: str | None = None,
        benchmark_name: str | None = None,
    ):
        """保存 factory 参数，并初始化恢复与写入调用记录。"""

        self.openai_api_key = openai_api_key
        self.openai_base_url = openai_base_url
        self.storage_root = Path(storage_root) if storage_root is not None else None
        self.config = config
        self.efficiency_collector = efficiency_collector
        if consume_granularity is not None:
            self.consume_granularity = consume_granularity
        self.benchmark_name = benchmark_name
        self.loaded_conversation_ids: list[str] = []
        self.add_calls: list[list[Conversation]] = []
        self.answered_question_ids: list[str] = []
        self.retrieved_question_ids: list[str] = []
        _FakeMemoryOS.instances.append(self)

    def load_existing_conversation_state(self, conversation: Conversation) -> None:
        """记录 resume 恢复请求。"""

        self.loaded_conversation_ids.append(conversation.conversation_id)

    @staticmethod
    def estimate_add_workload(conversation: Conversation, config):
        """复用真实静态估算逻辑，避免测试复制算法。"""

        return RealMemoryOS.estimate_add_workload(conversation, config)

    def add(self, conversations: Conversation | list[Conversation]) -> AddResult:
        """记录 add 调用，便于测试未被错误触发。"""

        if isinstance(conversations, Conversation):
            conversations = [conversations]
        self.add_calls.append(conversations)
        return AddResult(
            conversation_ids=[conversation.conversation_id for conversation in conversations]
        )

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """返回固定检索上下文，覆盖 retrieve-first runner 主路径。"""

        self.retrieved_question_ids.append(question.question_id)
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt="MemoryOS fake context",
            metadata={"method": "fake-memoryos"},
        )

    def get_answer(self, question: Question) -> AnswerResult:
        """返回固定答案，避免触发任何真实 API。"""

        self.answered_question_ids.append(question.question_id)
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer="前两轮答案",
            metadata={"method": "fake-memoryos"},
        )


def _patch_memoryos_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """用真实 registration 加 fake source/efficiency identity，避免外部源码依赖。"""

    registration = replace(
        method_registry_module.get_method_registration("memoryos"),
        # 本文件的 _FakeMemoryOS 仍是旧协议 BaseMemoryProvider 形态（经桥接运行），
        # 协议声明必须与 fake 实际形态一致，否则运行时交叉校验会 fail-fast。
        # fake 升级为原生 v3 形态归入 ws06 tests-restructure。
        protocol_version="v2-bridged",
        source_identity_factory=lambda path_settings: {"source": "fake-memoryos"},
        efficiency_instrumentation_identity_getter=lambda path_settings, config, source_identity: {
            "collector_schema": 1,
            "wrapper_path": "src/fake/wrapper.py",
            "wrapper_sha256": "a" * 64,
            "llm_tokenizer": "fake-model",
            "embedding_tokenizer": None,
            "method_source_sha256": "b" * 64,
        },
        efficiency_model_inventory_getter=lambda config: [
            ModelDescriptor(
                model_id="fake-model",
                model_name="fake-model",
                model_role="memory_answer_llm",
                execution_mode="api",
                tokenizer_name="fake-model",
            )
        ],
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_method_registration",
        lambda method_name: registration,
    )


def _openai_settings() -> OpenAISettings:
    """返回完整 OpenAI-compatible 测试配置，避免 registered 测试缺字段。"""

    return OpenAISettings(
        api_key="sk-test",
        base_url="https://example.invalid/v1",
    )


def _patch_framework_answer_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """替换 framework answer client，避免 registered 测试触发真实 API。"""

    class FakeAnswerClient:
        """离线 fake framework answer client。"""

        model_name = "fake-answer-client"

        def __init__(
            self,
            *,
            settings: OpenAISettings,
            answer_settings: AnswerLLMSettings,
        ) -> None:
            """保存 settings，以覆盖真实 client 的构造路径。"""

            self.settings = settings
            self.answer_settings = answer_settings

        def complete(self, *, prompt: str) -> str:
            """返回固定答案；prompt 拼接由 framework reader 负责验证。"""

            return "framework fake answer"

    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        FakeAnswerClient,
        raising=False,
    )


def test_memoryos_requires_confirm_api_before_settings_or_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未确认付费调用时，不能读取 profile、prepare、secret 或构造 MemoryOS。"""

    _FakeMemoryOS.instances.clear()
    _patch_memoryos_registration(monkeypatch)
    _patch_locomo_registration(monkeypatch)
    monkeypatch.setattr(method_registry_module, "MemoryOS", _FakeMemoryOS)
    monkeypatch.setattr(
        run_prediction_module,
        "load_method_profile",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("profile must not load before confirm_api")
        ),
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("settings must not load before confirm_api")
        ),
        raising=False,
    )

    with pytest.raises(ConfigurationError, match="confirm-api"):
        run_prediction_module.run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="memoryos",
            benchmark_name="locomo",
            profile_name="smoke",
            confirm_api=False,
            smoke_turn_limit=2,
            smoke_conversation_limit=1,
        )

    assert _FakeMemoryOS.instances == []


def test_memoryos_official_full_requires_confirm_full_before_settings_or_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """official-full 在构造 method 前必须额外确认全量成本。"""

    _FakeMemoryOS.instances.clear()
    _patch_memoryos_registration(monkeypatch)
    _patch_locomo_registration(monkeypatch)
    monkeypatch.setattr(method_registry_module, "MemoryOS", _FakeMemoryOS)
    monkeypatch.setattr(
        run_prediction_module,
        "load_method_profile",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("profile must not load before confirm_full")
        ),
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("settings must not load before confirm_full")
        ),
        raising=False,
    )

    with pytest.raises(ConfigurationError, match="confirm-full"):
        run_prediction_module.run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="memoryos",
            benchmark_name="locomo",
            profile_name="official-full",
            confirm_api=True,
            confirm_full=False,
        )

    assert _FakeMemoryOS.instances == []


def test_memoryos_registered_prediction_uses_generic_runner_with_smoke_crop_resume_and_workload_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MemoryOS 应走通用 batch service，并保留 smoke 裁剪、resume 恢复与 workload 估算。"""

    _FakeMemoryOS.instances.clear()
    _write_memoryos_profiles(tmp_path)
    _patch_memoryos_registration(monkeypatch)
    prepare_calls = _patch_locomo_registration(
        monkeypatch,
        prepared_run=_build_locomo_prepared_run(),
    )
    monkeypatch.setattr(method_registry_module, "MemoryOS", _FakeMemoryOS)
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: _openai_settings(),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_completed_conversation_ids",
        lambda run_dir, conversations: {"conv-1"},
    )
    monkeypatch.setattr(
        run_prediction_module,
        "_preflight_prediction_run",
        lambda **kwargs: None,
    )
    captured: dict[str, object] = {}

    def _fake_run_predictions(**kwargs):
        """记录通用 runner 参数，并返回最小运行摘要。"""

        captured.update(kwargs)
        return SimpleNamespace(run_id=kwargs["run_context"].run_id)

    monkeypatch.setattr(
        run_prediction_module,
        "run_predictions",
        _fake_run_predictions,
    )

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="memoryos",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="memoryos-run",
        resume=True,
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        smoke_max_workers=None,
        enable_efficiency_observability=False,
    )

    assert result.runs[0].run_id == "memoryos-run"
    assert result.runs[0].summary.run_id == "memoryos-run"
    assert prepare_calls == [
        BenchmarkLoadRequest(
            variant="locomo10",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=2,
            smoke_conversation_limit=1,
        )
    ]
    assert isinstance(captured["system"], _FakeMemoryOS)
    assert _FakeMemoryOS.instances[0].loaded_conversation_ids == ["conv-1"]
    assert _FakeMemoryOS.instances[0].add_calls == []
    assert _FakeMemoryOS.instances[0].benchmark_name == "locomo"
    assert captured["policy"].max_workers == 1
    assert captured["policy"].question_limit_per_conversation == 1
    assert captured["benchmark_variant"] == "locomo10"
    assert captured["run_scope"] is RunScope.SMOKE
    dataset = captured["dataset"]
    assert len(dataset.conversations) == 1
    smoke_conversation = dataset.conversations[0]
    turns = [
        turn
        for session in smoke_conversation.sessions
        for turn in session.turns
    ]
    assert [turn.turn_id for turn in turns] == ["conv-1:t1", "conv-1:t2"]
    assert [question.question_id for question in smoke_conversation.questions] == [
        "conv-1:q1"
    ]
    # LoCoMo reader 参数由 benchmark 统一冻结，不能继续沿用 MemoryOS 旧 profile。
    assert captured["method_manifest"] == {
        "answer_reader": {
            "answer_model": "gpt-4o-mini",
            "answer_parameters": {
                "message_role": "user",
                "temperature": 0.0,
                "max_tokens": 32,
                "top_p": 1.0,
                "timeout_seconds": 60.0,
                "max_retries": 8,
            },
            "answer_prompt_file_sha256": None,
            "answer_prompt_profile": "default",
            "answer_protocol": "retrieve_first_v1",
        },
        "config": _FakeMemoryOS.instances[0].config.to_manifest(),
        "source": {"source": "fake-memoryos"},
        "retrieval_evidence_contract_version": "v1",
        "workload_estimate": {
            "kind": "memory_update_batches",
            "total_update_batches": 1,
            "conversation_count": 1,
        },
    }
    assert captured["source_paths"] == (tmp_path / LOCOMO_SOURCE_PATH,)


def test_new_memoryos_run_writes_only_canonical_prediction_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """新的 MemoryOS 通用 run 只能写 canonical artifacts，不能回写根目录 legacy alias。"""

    _FakeMemoryOS.instances.clear()
    _write_memoryos_profiles(tmp_path)
    _patch_memoryos_registration(monkeypatch)
    prepare_calls = _patch_locomo_registration(
        monkeypatch,
        prepared_run=_build_locomo_prepared_run(),
    )
    outputs_root = tmp_path / "outputs"
    monkeypatch.setattr(method_registry_module, "MemoryOS", _FakeMemoryOS)
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=outputs_root,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: _openai_settings(),
        raising=False,
    )
    _patch_framework_answer_client(monkeypatch)

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="memoryos",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="memoryos-canonical-run",
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        enable_efficiency_observability=False,
    )
    summary = result.runs[0].summary

    run_dir = outputs_root / "memoryos-canonical-run"
    canonical_paths = {
        "manifest": run_dir / "manifest.json",
        "config": run_dir / "config.redacted.json",
        "dataset_fingerprint": run_dir / "artifacts" / "dataset_fingerprint.json",
        "public_questions": run_dir / "artifacts" / "public_questions.jsonl",
        "predictions": run_dir / "artifacts" / "method_predictions.jsonl",
        "private_labels": run_dir / "artifacts" / "evaluator_private_labels.jsonl",
        "conversation_status": run_dir / "checkpoints" / "conversation_status.json",
        "question_status": run_dir / "checkpoints" / "question_status.jsonl",
        "progress": run_dir / "checkpoints" / "progress.json",
        "summary": run_dir / "summaries" / "summary.json",
    }
    legacy_root_aliases = (
        run_dir / "predictions.jsonl",
        run_dir / "scores.jsonl",
        run_dir / "conversation_status.json",
        run_dir / "summary.json",
    )

    assert summary.run_id == "memoryos-canonical-run"
    assert summary.completed_conversations == 1
    assert summary.completed_questions == 1
    assert _FakeMemoryOS.instances[0].retrieved_question_ids == ["conv-1:q1"]
    assert _FakeMemoryOS.instances[0].answered_question_ids == []
    assert prepare_calls == [
        BenchmarkLoadRequest(
            variant="locomo10",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=2,
            smoke_conversation_limit=1,
        )
    ]
    for path in canonical_paths.values():
        assert path.exists(), path
    for path in legacy_root_aliases:
        assert not path.exists(), path

    public_questions = read_jsonl(canonical_paths["public_questions"])
    predictions = read_jsonl(canonical_paths["predictions"])
    private_labels = read_jsonl(canonical_paths["private_labels"])

    assert public_questions == [
        {
                "question_id": "conv-1:q1",
                "conversation_id": "conv-1",
                "question_text": "前两轮里说了什么？",
                "question_time": None,
                "category": None,
                "metadata": {},
            }
    ]
    assert predictions == [
        {
            "question_id": "conv-1:q1",
            "conversation_id": "conv-1",
            "question_text": "前两轮里说了什么？",
            "answer": "framework fake answer",
                "metadata": {
                    "answer_reader": "framework",
                    "answer_model": "fake-answer-client",
                    "answer_prompt_profile": "method_owned",
                },
            }
        ]
    assert private_labels == [
        {
            "question_id": "conv-1:q1",
            "gold_answer": "前两轮答案",
            "category": None,
            "evidence": ["conv-1:t1", "conv-1:t2"],
            "metadata": {},
        }
    ]


def test_memoryos_resume_manifest_mismatch_fails_before_factory_attach_or_directory_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """wrapper source identity 变化时，resume 应在所有副作用前失败。"""

    _FakeMemoryOS.instances.clear()
    _write_memoryos_profiles(tmp_path)
    prepared_run = _build_locomo_prepared_run()
    _patch_locomo_registration(monkeypatch, prepared_run=prepared_run)
    outputs_root = tmp_path / "outputs"
    run_dir = outputs_root / "memoryos-run"
    run_dir.mkdir(parents=True)
    base_registration = method_registry_module.get_method_registration("memoryos")
    current_source_identity = memoryos_adapter_module._build_memoryos_source_identity_from_components(
        vendored_files=["README.md", "eval/main_loco_parse.py"],
        vendored_source_sha256="a" * 64,
        wrapper_logical_path="src/memory_benchmark/methods/memoryos_adapter.py",
        wrapper_bytes=b"wrapper-new",
    )
    old_wrapper_source_identity = memoryos_adapter_module._build_memoryos_source_identity_from_components(
        vendored_files=["README.md", "eval/main_loco_parse.py"],
        vendored_source_sha256="a" * 64,
        wrapper_logical_path="src/memory_benchmark/methods/memoryos_adapter.py",
        wrapper_bytes=b"wrapper-old",
    )
    registration = replace(
        base_registration,
        source_identity_factory=lambda path_settings: current_source_identity,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_method_registration",
        lambda method_name: registration,
    )
    config = method_registry_module.load_method_profile(
        method_name="memoryos",
        profile_name="smoke",
        project_root=tmp_path,
    )
    smoke_dataset = prepared_run.dataset
    workload_estimate = run_prediction_module._estimate_method_workload(
        method_registration=registration,
        dataset=smoke_dataset,
        config=config,
    )
    method_manifest = run_prediction_module._build_method_manifest(
        config_manifest=config.to_manifest(),
        source_identity=current_source_identity,
        workload_estimate=workload_estimate,
    )
    run_context = RunContext.create(
        run_id="memoryos-run",
        benchmark_name="locomo",
        method_name=registration.display_name,
        model_name=registration.model_name_getter(config),
        output_root=outputs_root,
        resume=True,
        ensure_directories=False,
    )
    policy = prediction_runner_module.PredictionRunPolicy(
        max_workers=1,
        question_limit_per_conversation=1,
        resume=True,
    )
    source_paths = tuple(
        tmp_path / relative_path
        for relative_path in prepared_run.source_relative_paths
    )
    _, current_manifest = prediction_runner_module._build_prediction_resume_artifacts(
        dataset=smoke_dataset,
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
        benchmark_variant=prepared_run.variant,
        run_scope=prepared_run.run_scope,
        source_paths=source_paths,
    )
    existing_manifest = json.loads(json.dumps(current_manifest))
    existing_manifest["method"]["source"] = old_wrapper_source_identity
    (run_dir / "manifest.json").write_text(
        json.dumps(existing_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert (
        existing_manifest["method"]["source"]["vendored_source_sha256"]
        == current_source_identity["vendored_source_sha256"]
    )
    assert (
        existing_manifest["method"]["source"]["wrapper_sha256"]
        != current_source_identity["wrapper_sha256"]
    )
    assert (
        existing_manifest["method"]["source"]["source_sha256"]
        != current_source_identity["source_sha256"]
    )
    monkeypatch.setattr(method_registry_module, "MemoryOS", _FakeMemoryOS)
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=outputs_root,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: _openai_settings(),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_completed_conversation_ids",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("resume attach must not run before manifest preflight")
        ),
    )
    monkeypatch.setattr(
        run_prediction_module,
        "run_predictions",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("generic runner must not run after preflight failure")
        ),
    )

    with pytest.raises(ConfigurationError, match="Resume manifest mismatch"):
        run_prediction_module.run_registered_conversation_qa_prediction(
            project_root=tmp_path,
            method_name="memoryos",
            benchmark_name="locomo",
            profile_name="smoke",
            run_id="memoryos-run",
            resume=True,
            confirm_api=True,
            smoke_turn_limit=2,
            smoke_conversation_limit=1,
            enable_efficiency_observability=False,
        )

    assert _FakeMemoryOS.instances == []
    assert not (run_dir / "logs").exists()
    assert not (run_dir / "artifacts").exists()
    assert not (run_dir / "checkpoints").exists()
    assert not (run_dir / "summaries").exists()
    assert not (run_dir / "method_state").exists()


def test_memoryos_smoke_worker_override_is_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """支持 override 的 method 传入 smoke_max_workers 时正常通过。"""

    _FakeMemoryOS.instances.clear()
    _write_memoryos_profiles(tmp_path)
    _patch_memoryos_registration(monkeypatch)
    _patch_locomo_registration(
        monkeypatch,
        prepared_run=_build_locomo_prepared_run(),
    )
    monkeypatch.setattr(method_registry_module, "MemoryOS", _FakeMemoryOS)
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: SimpleNamespace(
            project_root=tmp_path,
            outputs_root=tmp_path / "outputs",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: _openai_settings(),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "run_predictions",
        lambda **kwargs: SimpleNamespace(
            run_id="test-run",
            benchmark_name="locomo",
            method_name="MemoryOS",
            total_conversations=1,
            completed_conversations=1,
            total_questions=1,
            completed_questions=1,
            prediction_path="/tmp/x.jsonl",
            private_label_path="/tmp/y.jsonl",
            summary_path="/tmp/z.json",
        ),
    )

    # 不应报 ConfigurationError，override 被接受
    run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=tmp_path,
        method_name="memoryos",
        benchmark_name="locomo",
        profile_name="smoke",
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        smoke_max_workers=2,
    )

    assert _FakeMemoryOS.instances == []

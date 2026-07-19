"""测试 LightMem 通过统一 registry 进入通用 prediction runner 的装配。

本文件只使用 fake LightMem runtime，不初始化官方 LightMemory、不调用真实 API。
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    BenchmarkRegistration,
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
)
from memory_benchmark.benchmark_adapters.base import BenchmarkAdapter
from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.config import AnswerLLMSettings, OpenAISettings, load_path_settings
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    MethodCapability,
    Question,
    AnswerPromptResult,
    PromptMessage,
    Session,
    TaskFamily,
    Turn,
)
from memory_benchmark.evaluators.locomo_judge import LoCoMoJudgeEvaluator
from memory_benchmark.evaluators.longmemeval_judge import LongMemEvalJudgeEvaluator
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.methods.config_track import resolve_config_track
from memory_benchmark.readers.answer import AnswerLLMResponse
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.storage import read_jsonl


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeLightMemForRegisteredPrediction(BaseMemoryProvider):
    """替代真实 LightMem adapter，避免模型加载和 API 调用。"""

    instances: list["FakeLightMemForRegisteredPrediction"] = []

    def __init__(self, **kwargs) -> None:
        """记录 registry factory 传入的构造参数。"""

        self.kwargs = kwargs
        self.added_conversations: list[list[Conversation]] = []
        self.answered_questions: list[Question] = []
        self.retrieved_questions: list[Question] = []
        self.instances.append(self)

    def add(self, conversations: Conversation | list[Conversation]) -> AddResult:
        """记录公开 conversation 写入请求。"""

        if isinstance(conversations, Conversation):
            conversations = [conversations]
        self.added_conversations.append(conversations)
        return AddResult(
            conversation_ids=[
                conversation.conversation_id for conversation in conversations
            ]
        )

    def get_answer(self, question: Question) -> AnswerResult:
        """返回固定答案，用于验证通用 runner artifacts。"""

        self.answered_questions.append(question)
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=f"fake lightmem answer for {question.question_id}",
        )

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """返回固定检索上下文，用于验证 retrieve-first runner artifacts。"""

        self.retrieved_questions.append(question)
        longmemeval = self.kwargs.get("consume_granularity") == "pair"
        prompt_messages = (
            [
                PromptMessage(role="system", content="You are a helpful assistant."),
                PromptMessage(
                    role="user",
                    content=(
                        f"Question time:{question.question_time} and question:{question.text}\n"
                        "Please answer the question based on the following memories: "
                        "LIGHTMEM-LONGMEMEVAL-NATIVE-MEMORY"
                    ),
                ),
            ]
            if longmemeval
            else [PromptMessage(role="system", content="LIGHTMEM-LOCOMO-NATIVE-PROMPT")]
        )
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt=f"fake lightmem context for {question.question_id}",
            prompt_messages=prompt_messages,
            metadata={
                "method": "lightmem",
                "answer_context": "reader-layout-must-not-replace-native-messages",
            },
        )


class FakeBenchmarkAdapter(BenchmarkAdapter):
    """满足 BenchmarkRegistration 类型约束的空 adapter。"""

    name = "locomo"

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """本测试不通过 adapter 实例加载数据。"""

        raise AssertionError("registered smoke uses prepare_run directly")


def _build_registered_smoke_dataset() -> Dataset:
    """构造最小 LoCoMo-like conversation-QA 数据集。"""

    return Dataset(
        dataset_name="locomo",
        metadata={"variant": "locomo10", "run_scope": RunScope.SMOKE.value},
        conversations=[
            Conversation(
                conversation_id="conv-lightmem-1",
                sessions=[
                    Session(
                        session_id="session-1",
                        session_time="2026-01-01",
                        turns=[
                            Turn(
                                turn_id="turn-1",
                                speaker="Alice",
                                content="I like tea.",
                            ),
                            Turn(
                                turn_id="turn-2",
                                speaker="Bob",
                                content="I will remember that.",
                            ),
                        ],
                    )
                ],
                questions=[
                    Question(
                        question_id="q-1",
                        conversation_id="conv-lightmem-1",
                        text="What does Alice like?",
                        category="1",
                    )
                ],
                gold_answers={
                    "q-1": GoldAnswerInfo(
                        question_id="q-1",
                        answer="tea",
                        evidence=["private-evidence"],
                    )
                },
            )
        ],
    )


def _build_fake_benchmark_registration() -> BenchmarkRegistration:
    """构造只含一个 locomo10 variant 的 fake benchmark registration。"""

    def prepare_run(
        project_root: Path,
        request: BenchmarkLoadRequest,
    ) -> PreparedBenchmarkRun:
        """返回固定 smoke dataset，并校验 service 传入的 request。"""

        assert project_root == PROJECT_ROOT
        assert request == BenchmarkLoadRequest(
            variant="locomo10",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=2,
            smoke_conversation_limit=1,
        )
        return PreparedBenchmarkRun(
            variant="locomo10",
            run_scope=RunScope.SMOKE,
            dataset=_build_registered_smoke_dataset(),
            source_relative_paths=(Path("pyproject.toml"),),
        )

    return BenchmarkRegistration(
        name="locomo",
        adapter_cls=FakeBenchmarkAdapter,
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        variants=(
            BenchmarkVariantSpec(
                name="locomo10",
                source_relative_paths=(Path("pyproject.toml"),),
            ),
        ),
        default_variant="locomo10",
        prepare_run=prepare_run,
        prediction_enabled=True,
    )


def test_lightmem_registered_prediction_runs_generic_runner_offline(
    tmp_path,
    monkeypatch,
) -> None:
    """LightMem 应通过统一 registered prediction service 写出标准 artifacts。"""

    FakeLightMemForRegisteredPrediction.instances.clear()
    real_paths = load_path_settings(PROJECT_ROOT)
    test_paths = replace(real_paths, outputs_root=tmp_path / "outputs")
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: test_paths,
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda benchmark_name: _build_fake_benchmark_registration(),
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
        ),
        raising=False,
    )

    class FakeAnswerClient:
        """离线 fake framework answer client，避免 registered 测试触发真实 API。"""

        model_name = "fake-answer-client"

        def __init__(
            self,
            *,
            settings: OpenAISettings,
            answer_settings: AnswerLLMSettings,
        ) -> None:
            """保存 OpenAI-compatible settings 以覆盖构造路径。"""

            self.settings = settings
            self.answer_settings = answer_settings

        def complete(self, *, prompt: str) -> str:
            """返回固定答案；prompt 内容由 framework reader 负责拼接。"""

            return "framework fake answer"

    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        FakeAnswerClient,
        raising=False,
    )
    monkeypatch.setattr(
        method_registry_module,
        "LightMem",
        FakeLightMemForRegisteredPrediction,
    )
    # FakeLightMemForRegisteredPrediction 仍是旧协议 BaseMemoryProvider 形态（经
    # 桥接运行），协议声明必须与 fake 实际形态一致，否则运行时交叉校验
    # fail-fast；fake 升级为原生 v3 形态归入 ws06 tests-restructure。
    legacy_registration = replace(
        method_registry_module.get_method_registration("lightmem"),
        protocol_version="v2-bridged",
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_method_registration",
        lambda method_name: legacy_registration,
    )

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="lightmem",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="lightmem-offline-smoke",
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        enable_efficiency_observability=False,
    )

    assert result.benchmark == "locomo"
    assert result.selector == "locomo10"
    assert result.runs[0].run_id == "lightmem-offline-smoke"
    assert len(FakeLightMemForRegisteredPrediction.instances) == 1
    fake_method = FakeLightMemForRegisteredPrediction.instances[0]
    assert fake_method.kwargs["config"].profile_name == "smoke"
    assert len(fake_method.added_conversations) == 1
    assert fake_method.added_conversations[0][0].conversation_id == "conv-lightmem-1"
    assert fake_method.answered_questions == []
    assert [question.question_id for question in fake_method.retrieved_questions] == [
        "q-1"
    ]

    run_dir = tmp_path / "outputs" / "lightmem-offline-smoke"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    public_questions = read_jsonl(run_dir / "artifacts" / "public_questions.jsonl")

    assert manifest["method_name"] == "LightMem"
    assert manifest["method"]["config"]["profile_name"] == "smoke"
    assert manifest["method"]["consume_granularity"] == "turn"
    assert predictions[0]["answer"] == "framework fake answer"
    assert public_questions[0]["question_id"] == "q-1"
    assert "gold_answers" not in public_questions[0]


class NativeTrackFakeAnswerClient:
    """记录 native reader 的 settings/messages，零网络返回固定答案。"""

    instances: list["NativeTrackFakeAnswerClient"] = []
    model_name = "gpt-4o-mini"

    def __init__(
        self,
        *,
        settings: OpenAISettings,
        answer_settings: AnswerLLMSettings,
    ) -> None:
        """保存本次 native sampling 配置。"""

        self.settings = settings
        self.answer_settings = answer_settings
        self.messages: list[list[PromptMessage]] = []
        self.instances.append(self)

    def complete_messages_with_metadata(
        self,
        *,
        messages: list[PromptMessage],
    ) -> AnswerLLMResponse:
        """记录 method-owned messages 并返回离线答案。"""

        self.messages.append(list(messages))
        return AnswerLLMResponse(text="native fake answer")


class NativeTrackFakeJudgeClient:
    """记录 native judge prompt 的 OpenAI-compatible fake client。"""

    def __init__(self, response_text: str) -> None:
        """初始化固定回复和调用记录。"""

        self.response_text = response_text
        self.calls: list[dict[str, object]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **kwargs):
        """记录 judge 参数并返回最小 chat completion。"""

        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.response_text))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=1),
        )


def test_lightmem_native_config_track_flows_through_both_official_grids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """LightMem 两个 native 格应贯通 prompt、sampling、judge 和 manifest。"""

    NativeTrackFakeAnswerClient.instances.clear()
    FakeLightMemForRegisteredPrediction.instances.clear()
    real_paths = load_path_settings(PROJECT_ROOT)
    test_paths = replace(real_paths, outputs_root=tmp_path / "outputs")
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: test_paths,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda benchmark_name: _build_fake_benchmark_registration_for(benchmark_name),
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root: OpenAISettings(
            api_key="sk-test", base_url="https://example.invalid/v1"
        ),
    )
    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        NativeTrackFakeAnswerClient,
    )
    monkeypatch.setattr(
        method_registry_module,
        "LightMem",
        FakeLightMemForRegisteredPrediction,
    )
    legacy_registration = replace(
        method_registry_module.get_method_registration("lightmem"),
        protocol_version="v2-bridged",
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_method_registration",
        lambda method_name: legacy_registration,
    )

    for benchmark in ("locomo", "longmemeval"):
        run_id = f"lightmem-{benchmark}-native"
        run_prediction_module.run_registered_conversation_qa_prediction(
            project_root=PROJECT_ROOT,
            method_name="lightmem",
            benchmark_name=benchmark,
            profile_name="smoke",
            config_track="native",
            run_id=run_id,
            confirm_api=True,
            smoke_turn_limit=2,
            smoke_conversation_limit=1,
            enable_efficiency_observability=False,
        )
        run_dir = tmp_path / "outputs" / run_id
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        prompts = read_jsonl(
            run_dir / "artifacts" / "answer_prompts.prediction.jsonl"
        )
        reader = next(
            instance
            for instance in reversed(NativeTrackFakeAnswerClient.instances)
            if instance.messages
        )

        assert manifest["method"]["config_track"] == "native"
        assert manifest["method"]["prompt_track"] == "native"
        assert manifest["method"]["consume_granularity"] == (
            "pair" if benchmark == "longmemeval" else "turn"
        )
        assert (
            reader.answer_settings.temperature,
            reader.answer_settings.max_tokens,
            reader.answer_settings.top_p,
        ) == (0.0, 2000, 0.8)
        assert prompts[0]["prompt_messages"] == [
            message.to_dict() for message in reader.messages[0]
        ]

        bundle = resolve_config_track("lightmem", benchmark, "native")
        assert bundle is not None
        judge_client = NativeTrackFakeJudgeClient(
            '{"label": "CORRECT"}' if benchmark == "locomo" else "yes"
        )
        if benchmark == "locomo":
            judge = LoCoMoJudgeEvaluator(
                mode="compact",
                model="gpt-4o-mini",
                client=judge_client,
                prompt_template_override=bundle.judge_profile.prompt_template,
                skipped_categories=bundle.judge_profile.skipped_categories,
                prompt_profile_override=bundle.judge_profile.profile_name,
            )
            assert "LIGHTMEM-LOCOMO-NATIVE-PROMPT" in reader.messages[0][0].content
        else:
            judge = LongMemEvalJudgeEvaluator(
                mode="compact",
                model="gpt-4o-mini",
                client=judge_client,
            )
            assert "LIGHTMEM-LONGMEMEVAL-NATIVE-MEMORY" in reader.messages[0][1].content
        summary = run_artifact_evaluation(run_dir, judge, benchmark)

        assert summary.total_questions == 1
        assert judge_client.calls


def _build_fake_benchmark_registration_for(
    benchmark_name: str,
) -> BenchmarkRegistration:
    """构造 LoCoMo/LongMemEval native flow-through 共用的最小注册。"""

    variant = "locomo10" if benchmark_name == "locomo" else "s"
    dataset = _build_registered_smoke_dataset()
    dataset.dataset_name = benchmark_name
    dataset.metadata["variant"] = variant
    question = dataset.conversations[0].questions[0]
    if benchmark_name == "longmemeval":
        question.category = "single-session-user"
        question.question_time = "2026-01-02"

    def prepare_run(
        project_root: Path,
        request: BenchmarkLoadRequest,
    ) -> PreparedBenchmarkRun:
        """返回当前 benchmark 的固定离线切片。"""

        return PreparedBenchmarkRun(
            variant=variant,
            run_scope=RunScope.SMOKE,
            dataset=dataset,
            source_relative_paths=(Path("pyproject.toml"),),
        )

    return BenchmarkRegistration(
        name=benchmark_name,
        adapter_cls=FakeBenchmarkAdapter,
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {MethodCapability.CONVERSATION_ADD, MethodCapability.MEMORY_RETRIEVAL}
        ),
        variants=(
            BenchmarkVariantSpec(
                name=variant,
                source_relative_paths=(Path("pyproject.toml"),),
            ),
        ),
        default_variant=variant,
        prepare_run=prepare_run,
        prediction_enabled=True,
    )

"""测试 A-Mem 通过统一 registry 进入通用 prediction runner 的装配。

本文件只使用 fake A-Mem runtime，不加载真实 embedding 模型、不调用真实 API。
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
    Session,
    TaskFamily,
    Turn,
)
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.methods.amem_adapter import AMemConfig
from memory_benchmark.methods.registry import MethodBuildContext
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.storage import read_jsonl


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeAMemForRegisteredPrediction(BaseMemoryProvider):
    """替代真实 A-Mem adapter，避免模型加载和 API 调用。"""

    instances: list["FakeAMemForRegisteredPrediction"] = []

    def __init__(self, **kwargs) -> None:
        """记录 registry factory 传入的构造参数。"""

        self.kwargs = kwargs
        self.added_conversations: list[list[Conversation]] = []
        self.answered_questions: list[Question] = []
        self.retrieved_questions: list[Question] = []
        self.loaded_conversations: list[Conversation] = []
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
            answer=f"fake answer for {question.question_id}",
        )

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """返回固定检索上下文，用于验证 retrieve-first runner artifacts。"""

        self.retrieved_questions.append(question)
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt=f"fake memory context for {question.question_id}",
            metadata={"method": "amem"},
        )

    def load_existing_conversation_state(self, conversation: Conversation) -> None:
        """记录 registry factory 请求恢复的 completed conversation。"""

        self.loaded_conversations.append(conversation)


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
                conversation_id="conv-amem-1",
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
                        conversation_id="conv-amem-1",
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


def test_amem_registered_prediction_runs_generic_runner_offline(
    tmp_path,
    monkeypatch,
) -> None:
    """A-Mem 应通过统一 registered prediction service 写出标准 artifacts。"""

    FakeAMemForRegisteredPrediction.instances.clear()
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
    monkeypatch.setattr(method_registry_module, "AMem", FakeAMemForRegisteredPrediction)
    # FakeAMemForRegisteredPrediction 仍是旧协议 BaseMemoryProvider 形态（经桥接
    # 运行），协议声明必须与 fake 实际形态一致，否则运行时交叉校验 fail-fast；
    # fake 升级为原生 v3 形态归入 ws06 tests-restructure。
    legacy_registration = replace(
        method_registry_module.get_method_registration("amem"),
        protocol_version="v2-bridged",
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_method_registration",
        lambda method_name: legacy_registration,
    )

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="amem",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="amem-offline-smoke",
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        enable_efficiency_observability=False,
    )

    assert result.benchmark == "locomo"
    assert result.selector == "locomo10"
    assert result.runs[0].run_id == "amem-offline-smoke"
    assert len(FakeAMemForRegisteredPrediction.instances) == 1
    fake_method = FakeAMemForRegisteredPrediction.instances[0]
    assert fake_method.kwargs["openai_api_key"] == "sk-test"
    assert fake_method.kwargs["openai_base_url"] == "https://example.invalid/v1"
    assert fake_method.kwargs["config"].profile_name == "smoke"
    assert len(fake_method.added_conversations) == 1
    assert fake_method.added_conversations[0][0].conversation_id == "conv-amem-1"
    assert fake_method.answered_questions == []
    assert [question.question_id for question in fake_method.retrieved_questions] == [
        "q-1"
    ]

    run_dir = tmp_path / "outputs" / "amem-offline-smoke"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    public_questions = read_jsonl(run_dir / "artifacts" / "public_questions.jsonl")

    assert manifest["method_name"] == "A-Mem"
    assert manifest["method"]["config"]["profile_name"] == "smoke"
    assert predictions[0]["answer"] == "framework fake answer"
    assert public_questions[0]["question_id"] == "q-1"
    assert "gold_answers" not in public_questions[0]


def test_amem_factory_loads_completed_conversations_for_resume(
    tmp_path,
    monkeypatch,
) -> None:
    """registry factory 应把 completed conversations 接到 A-Mem 持久化恢复路径。"""

    FakeAMemForRegisteredPrediction.instances.clear()
    monkeypatch.setattr(method_registry_module, "AMem", FakeAMemForRegisteredPrediction)
    conversation = _build_registered_smoke_dataset().conversations[0]
    context = MethodBuildContext(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
        ),
        path_settings=replace(load_path_settings(PROJECT_ROOT), outputs_root=tmp_path),
        storage_root=tmp_path / "method_state",
        completed_conversations=(conversation,),
    )
    registration = method_registry_module.get_method_registration("amem")

    system = registration.system_factory(context)

    assert system.kwargs["storage_root"] == tmp_path / "method_state"
    assert [item.conversation_id for item in system.loaded_conversations] == [
        "conv-amem-1"
    ]
    assert system.added_conversations == []

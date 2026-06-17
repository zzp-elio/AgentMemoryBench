"""A-Mem adapter 的配置、源码身份和基础契约测试。

这些测试默认不调用真实 API。测试目标是确认 adapter 能找到 vendored A-Mem 源码、
能加载强类型 profile，并且 source identity 会覆盖官方核心源码。
"""

from __future__ import annotations

import pytest

from memory_benchmark.config import load_path_settings
from memory_benchmark.core import (
    AnswerResult,
    ConfigurationError,
    Conversation,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
)
from memory_benchmark.methods.amem_adapter import (
    AMem,
    AMemConfig,
    build_amem_source_identity,
    import_amem_robust_classes,
)
import memory_benchmark.methods.amem_adapter as amem_adapter_module
from memory_benchmark.observability.efficiency import EfficiencyCollector


def test_amem_config_rejects_invalid_retrieve_k() -> None:
    """retrieve_k 是 method 内部检索深度，必须为正数。"""

    with pytest.raises(ConfigurationError, match="retrieve_k"):
        AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=0,
            max_workers=1,
            use_robust_layer=True,
            profile_name="bad",
        )


def test_amem_source_identity_covers_official_core_files() -> None:
    """source identity 必须覆盖 A-Mem 官方核心文件，保证 resume 可审计。"""

    identity = build_amem_source_identity(load_path_settings())

    assert identity["source_sha256"]
    assert identity["file_count"] >= 3
    assert "memory_layer_robust.py" in identity["files"]
    assert "llm_text_parsers.py" in identity["files"]
    assert "README.md" in identity["files"]


class FakeAMemRuntime:
    """模拟 A-Mem runtime，只记录 wrapper 传入的公开内容。"""

    def __init__(self) -> None:
        """初始化 fake 调用记录。"""

        self.added_notes: list[dict[str, object]] = []
        self.queries: list[dict[str, object]] = []

    def add_note(self, content: str, time: str | None = None) -> str:
        """记录写入内容并返回 fake note id。"""

        self.added_notes.append({"content": content, "time": time})
        return f"note-{len(self.added_notes)}"

    def find_related_memories_raw(self, query: str, k: int = 5) -> str:
        """记录检索请求并返回 fake memory context。"""

        self.queries.append({"query": query, "k": k})
        return "memory content from fake runtime"


class FakeAMemLLM:
    """模拟 OpenAI-compatible reader，返回固定答案。"""

    def __init__(self) -> None:
        """初始化 fake prompt 调用记录。"""

        self.prompts: list[dict[str, object]] = []

    def get_completion(self, prompt: str, temperature: float = 0.7) -> str:
        """记录 prompt 并返回固定答案。"""

        self.prompts.append({"prompt": prompt, "temperature": temperature})
        return "fake answer"


def _conversation_with_private_gold() -> Conversation:
    """构造一个包含私有 gold/evidence 的最小 conversation。"""

    question = Question(
        question_id="q-1",
        conversation_id="conv-1",
        text="What does Alice like?",
        category="1",
    )
    return Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="s-1",
                session_time="2026-01-01",
                turns=[
                    Turn(turn_id="t-1", speaker="Alice", content="I like tea."),
                    Turn(turn_id="t-2", speaker="Bob", content="Noted."),
                ],
            )
        ],
        questions=[question],
        gold_answers={
            "q-1": GoldAnswerInfo(
                question_id="q-1",
                answer="tea",
                evidence=["private-evidence-id"],
            )
        },
    )


def test_amem_add_and_get_answer_never_pass_private_gold_to_method() -> None:
    """A-Mem wrapper 只能把公开 conversation 和 question 传给第三方 runtime。"""

    runtime = FakeAMemRuntime()
    llm = FakeAMemLLM()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: runtime,
        answer_llm=llm,
    )
    conversation = _conversation_with_private_gold()

    add_result = method.add([conversation])
    answer = method.get_answer(conversation.questions[0])

    assert add_result.conversation_ids == ["conv-1"]
    assert isinstance(answer, AnswerResult)
    assert answer.answer == "fake answer"
    public_text = "\n".join(str(note["content"]) for note in runtime.added_notes)
    prompt_text = str(llm.prompts[0]["prompt"])
    assert "private-evidence-id" not in public_text
    assert "private-evidence-id" not in prompt_text
    assert "tea" not in prompt_text
    assert runtime.queries == [{"query": "What does Alice like?", "k": 2}]


def test_amem_can_import_official_robust_layer_without_calling_api() -> None:
    """adapter 应能从 vendored A-Mem 源码导入官方 robust runtime 类。"""

    classes = import_amem_robust_classes(load_path_settings())

    assert classes["RobustAgenticMemorySystem"].__name__ == "RobustAgenticMemorySystem"


def test_amem_production_runtime_receives_openai_compatible_settings(monkeypatch) -> None:
    """生产 runtime 必须把 API key/base URL 和 profile 模型传给官方 A-Mem 类。"""

    created_kwargs: dict[str, object] = {}

    class FakeOfficialRuntime:
        """替代官方 RobustAgenticMemorySystem，避免加载真实 embedding 模型。"""

        def __init__(self, **kwargs) -> None:
            """记录 wrapper 传入官方 runtime 的构造参数。"""

            created_kwargs.update(kwargs)

        def add_note(self, content: str, time: str | None = None) -> str:
            """模拟官方写入接口，避免真实模型和 API 调用。"""

            return "note-1"

    monkeypatch.setattr(
        amem_adapter_module,
        "import_amem_robust_classes",
        lambda path_settings=None: {
            "RobustAgenticMemorySystem": FakeOfficialRuntime,
            "RobustLLMController": object,
        },
    )
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        openai_api_key="test-key",
        openai_base_url="https://api.example.test/v1",
    )

    method.add([_conversation_with_private_gold()])

    assert created_kwargs["model_name"] == "all-MiniLM-L6-v2"
    assert created_kwargs["llm_backend"] == "openai"
    assert created_kwargs["llm_model"] == "gpt-4o-mini"
    assert created_kwargs["api_key"] == "test-key"
    assert created_kwargs["api_base"] == "https://api.example.test/v1"
    assert created_kwargs["check_connection"] is False


def test_amem_records_question_efficiency_observations() -> None:
    """启用 collector 后，A-Mem 应记录 retrieval、context token 和 answer latency。"""

    runtime = FakeAMemRuntime()
    llm = FakeAMemLLM()
    collector = EfficiencyCollector(run_id="amem-efficiency-run", enabled=True)
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: runtime,
        answer_llm=llm,
        efficiency_collector=collector,
    )
    conversation = _conversation_with_private_gold()
    method.add([conversation])

    with collector.question_scope("conv-1", "q-1") as scope:
        method.get_answer(conversation.questions[0])

    records = [record.to_dict() for record in scope.records]
    question_records = [
        record
        for record in records
        if record["observation_type"] == "question_efficiency"
    ]
    assert len(question_records) == 1
    assert question_records[0]["retrieval_latency_ms"] >= 0
    assert question_records[0]["unsupported_reason"] is None
    assert question_records[0]["injected_memory_context_tokens"] > 0
    assert question_records[0]["answer_generation_latency_ms"] >= 0

"""A-Mem adapter 的配置、源码身份和基础契约测试。

这些测试默认不调用真实 API。测试目标是确认 adapter 能找到 vendored A-Mem 源码、
能加载强类型 profile，并且 source identity 会覆盖官方核心源码。
"""

from __future__ import annotations

import json
from pathlib import Path

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
    assert "test_advanced_robust.py" in identity["files"]
    assert "run_k_sweep.sh" in identity["files"]


class FakeAMemRuntime:
    """模拟 A-Mem runtime，只记录 wrapper 传入的公开内容。"""

    def __init__(self) -> None:
        """初始化 fake 调用记录。"""

        self.added_notes: list[dict[str, object]] = []
        self.queries: list[dict[str, object]] = []
        self.memories: dict[str, dict[str, object]] = {}
        self.retriever = FakeAMemRetriever()

    def add_note(self, content: str, time: str | None = None) -> str:
        """记录写入内容并返回 fake note id。"""

        self.added_notes.append({"content": content, "time": time})
        note_id = f"note-{len(self.added_notes)}"
        self.memories[note_id] = {
            "id": note_id,
            "content": content,
            "time": time,
        }
        self.retriever.saved_documents.append(content)
        return note_id

    def find_related_memories_raw(self, query: str, k: int = 5) -> str:
        """记录检索请求并返回 fake memory context。"""

        self.queries.append({"query": query, "k": k})
        return "memory content from fake runtime"


class FakeAMemRetriever:
    """模拟 A-Mem 官方 retriever 的 save/load 接口。"""

    def __init__(self) -> None:
        """初始化 fake 检索器状态。"""

        self.saved_documents: list[str] = []
        self.loaded_from: tuple[str, str] | None = None

    def save(self, retriever_cache_file: str, retriever_cache_embeddings_file: str) -> None:
        """用文本文件模拟官方 retriever cache 和 embeddings 文件。"""

        Path(retriever_cache_file).write_text(
            json.dumps({"documents": self.saved_documents}, ensure_ascii=False),
            encoding="utf-8",
        )
        Path(retriever_cache_embeddings_file).write_text(
            json.dumps({"embedding_count": len(self.saved_documents)}),
            encoding="utf-8",
        )

    def load(
        self,
        retriever_cache_file: str,
        retriever_cache_embeddings_file: str,
    ) -> "FakeAMemRetriever":
        """记录 load 路径并恢复 fake 文档列表。"""

        self.loaded_from = (retriever_cache_file, retriever_cache_embeddings_file)
        payload = json.loads(Path(retriever_cache_file).read_text(encoding="utf-8"))
        self.saved_documents = list(payload["documents"])
        return self


class FakeAMemLLM:
    """模拟 OpenAI-compatible LLM，区分 query generation 和 answer prompt。"""

    def __init__(self) -> None:
        """初始化 fake prompt 调用记录。"""

        self.prompts: list[dict[str, object]] = []

    def get_completion(self, prompt: str, temperature: float = 0.7) -> str:
        """记录 prompt，并按 prompt 类型返回关键词或答案。"""

        self.prompts.append({"prompt": prompt, "temperature": temperature})
        if "generate several keywords separated by commas" in prompt:
            return "generated keywords"
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


def test_amem_add_and_get_answer_never_pass_private_gold_to_method(tmp_path) -> None:
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
        storage_root=tmp_path,
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
    assert runtime.queries == [{"query": "generated keywords", "k": 40}]
    assert "generate several keywords separated by commas" in str(llm.prompts[0]["prompt"])


def test_amem_add_persists_conversation_state(tmp_path) -> None:
    """A-Mem 写完 conversation 后应保存 memories、retriever 和 manifest。"""

    runtime = FakeAMemRuntime()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: runtime,
        answer_llm=FakeAMemLLM(),
        storage_root=tmp_path,
    )

    method.add([_conversation_with_private_gold()])

    state_dir = tmp_path / "conv-1"
    manifest = json.loads((state_dir / "state_manifest.json").read_text("utf-8"))
    assert (state_dir / "memories.pkl").is_file()
    assert (state_dir / "retriever.pkl").is_file()
    assert (state_dir / "retriever_embeddings.npy").is_file()
    assert manifest["conversation_id"] == "conv-1"
    assert manifest["adapter_version"]
    assert manifest["turn_count"] == 2
    assert manifest["profile"]["profile_name"] == "smoke"
    assert set(manifest["files"]) == {
        "memories.pkl",
        "retriever.pkl",
        "retriever_embeddings.npy",
    }


def test_amem_load_existing_conversation_state_restores_runtime(tmp_path) -> None:
    """新 A-Mem 实例应能加载已完成 conversation 并直接回答问题。"""

    first_runtime = FakeAMemRuntime()
    conversation = _conversation_with_private_gold()
    first_method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: first_runtime,
        answer_llm=FakeAMemLLM(),
        storage_root=tmp_path,
    )
    first_method.add([conversation])

    restored_runtime = FakeAMemRuntime()
    restored_llm = FakeAMemLLM()
    second_method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: restored_runtime,
        answer_llm=restored_llm,
        storage_root=tmp_path,
    )

    second_method.load_existing_conversation_state(conversation)
    answer = second_method.get_answer(conversation.questions[0])

    assert answer.answer == "fake answer"
    assert restored_runtime.added_notes == []
    assert restored_runtime.memories == first_runtime.memories
    assert restored_runtime.retriever.loaded_from == (
        str(tmp_path / "conv-1" / "retriever.pkl"),
        str(tmp_path / "conv-1" / "retriever_embeddings.npy"),
    )
    assert restored_runtime.queries == [{"query": "generated keywords", "k": 40}]


def test_amem_load_existing_state_rejects_corrupt_manifest(tmp_path) -> None:
    """manifest 被破坏时必须拒绝恢复，避免错误状态污染实验。"""

    runtime = FakeAMemRuntime()
    conversation = _conversation_with_private_gold()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: runtime,
        answer_llm=FakeAMemLLM(),
        storage_root=tmp_path,
    )
    method.add([conversation])
    manifest_path = tmp_path / "conv-1" / "state_manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["profile"]["llm_model"] = "different-model"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    restored = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: FakeAMemRuntime(),
        answer_llm=FakeAMemLLM(),
        storage_root=tmp_path,
    )

    with pytest.raises(ConfigurationError, match="profile"):
        restored.load_existing_conversation_state(conversation)


def test_amem_get_answer_uses_table8_category_k_values(tmp_path) -> None:
    """A-Mem Table 1 GPT-4o-mini profile 应按 category 使用 Table 8 的 k。"""

    runtime = FakeAMemRuntime()
    llm = FakeAMemLLM()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=10,
            max_workers=1,
            profile_name="official-mini",
        ),
        runtime_factory=lambda conversation_id: runtime,
        answer_llm=llm,
        storage_root=tmp_path,
    )
    conversation = _conversation_with_private_gold()
    method.add([conversation])

    expected_k_by_category = {
        "1": 40,
        "2": 40,
        "3": 50,
        "4": 50,
    }
    for category, expected_k in expected_k_by_category.items():
        question = Question(
            question_id=f"q-{category}",
            conversation_id="conv-1",
            text=f"Question for category {category}?",
            category=category,
        )
        method.get_answer(question)
        assert runtime.queries[-1] == {
            "query": "generated keywords",
            "k": expected_k,
        }


def test_amem_rejects_adversarial_category_without_gold_answer(tmp_path) -> None:
    """A-Mem adversarial 官方 prompt 需要 gold answer，普通 profile 必须显式拒绝。"""

    runtime = FakeAMemRuntime()
    llm = FakeAMemLLM()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=10,
            max_workers=1,
            profile_name="official-mini",
        ),
        runtime_factory=lambda conversation_id: runtime,
        answer_llm=llm,
        storage_root=tmp_path,
    )
    conversation = _conversation_with_private_gold()
    method.add([conversation])
    question = Question(
        question_id="q-5",
        conversation_id="conv-1",
        text="Which option is correct?",
        category="5",
    )

    with pytest.raises(ConfigurationError, match="adversarial"):
        method.get_answer(question)


def test_amem_can_import_official_robust_layer_without_calling_api() -> None:
    """adapter 应能从 vendored A-Mem 源码导入官方 robust runtime 类。"""

    classes = import_amem_robust_classes(load_path_settings())

    assert classes["RobustAgenticMemorySystem"].__name__ == "RobustAgenticMemorySystem"


def test_amem_production_runtime_receives_openai_compatible_settings(
    monkeypatch,
    tmp_path,
) -> None:
    """生产 runtime 必须把 API key/base URL 和 profile 模型传给官方 A-Mem 类。"""

    created_kwargs: dict[str, object] = {}

    class FakeOfficialRuntime:
        """替代官方 RobustAgenticMemorySystem，避免加载真实 embedding 模型。"""

        def __init__(self, **kwargs) -> None:
            """记录 wrapper 传入官方 runtime 的构造参数。"""

            created_kwargs.update(kwargs)
            self.memories: dict[str, object] = {}
            self.retriever = FakeAMemRetriever()
            self.llm_controller = type(
                "FakeLLMController",
                (),
                {"llm": type("FakeLLM", (), {"client": "official-default-client"})()},
            )()

        def add_note(self, content: str, time: str | None = None) -> str:
            """模拟官方写入接口，避免真实模型和 API 调用。"""

            self.memories[f"note-{len(self.memories) + 1}"] = {
                "content": content,
                "time": time,
            }
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
        storage_root=tmp_path,
    )

    method.add([_conversation_with_private_gold()])

    assert created_kwargs["model_name"] == "all-MiniLM-L6-v2"
    assert created_kwargs["llm_backend"] == "openai"
    assert created_kwargs["llm_model"] == "gpt-4o-mini"
    assert created_kwargs["api_key"] == "test-key"
    assert created_kwargs["api_base"] == "https://api.example.test/v1"
    assert created_kwargs["check_connection"] is False


def test_amem_replaces_official_openai_client_when_base_url_is_configured(
    monkeypatch,
    tmp_path,
) -> None:
    """官方 OpenAI controller 忽略 api_base 时，adapter 应在 wrapper 层注入 base URL。"""

    created_clients: list[dict[str, str | None]] = []
    runtime_instances: list[object] = []

    class FakeOfficialRuntime:
        """记录被 adapter 创建的 official runtime。"""

        def __init__(self, **kwargs) -> None:
            """构造带 client 字段的 fake LLM controller。"""

            self.kwargs = kwargs
            self.memories: dict[str, object] = {}
            self.retriever = FakeAMemRetriever()
            self.llm_controller = type(
                "FakeLLMController",
                (),
                {"llm": type("FakeLLM", (), {"client": "official-default-client"})()},
            )()
            runtime_instances.append(self)

        def add_note(self, content: str, time: str | None = None) -> str:
            """模拟官方写入接口。"""

            self.memories[f"note-{len(self.memories) + 1}"] = {
                "content": content,
                "time": time,
            }
            return "note-1"

    monkeypatch.setattr(
        amem_adapter_module,
        "import_amem_robust_classes",
        lambda path_settings=None: {
            "RobustAgenticMemorySystem": FakeOfficialRuntime,
            "RobustLLMController": object,
        },
    )
    monkeypatch.setattr(
        amem_adapter_module,
        "_create_openai_compatible_client",
        lambda api_key, base_url: created_clients.append(
            {"api_key": api_key, "base_url": base_url}
        )
        or "patched-client",
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
        openai_base_url="https://ohmygpt.example/v1",
        storage_root=tmp_path,
    )

    method.add([_conversation_with_private_gold()])

    assert created_clients == [
        {"api_key": "test-key", "base_url": "https://ohmygpt.example/v1"}
    ]
    assert runtime_instances[0].llm_controller.llm.client == "patched-client"


def test_amem_records_question_efficiency_observations(tmp_path) -> None:
    """启用 collector 后，A-Mem 应记录问题级汇总和两次 LLM 调用 token。"""

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
        storage_root=tmp_path,
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
    llm_records = [
        record for record in records if record["observation_type"] == "llm_call"
    ]
    assert [record["stage"] for record in llm_records] == ["retrieval", "answer"]
    assert [record["model_id"] for record in llm_records] == [
        "amem-query-llm",
        "amem-answer-llm",
    ]
    assert all(record["input_tokens"] > 0 for record in llm_records)
    assert all(record["output_tokens"] > 0 for record in llm_records)
    assert all(
        record["token_measurement_source"] == "tokenizer_estimate"
        for record in llm_records
    )

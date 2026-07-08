"""测试 SimpleMem adapter 的配置、资源和 source identity。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.config import load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    RetrievalQuery,
    TurnEvent,
    UnitRef,
)
from memory_benchmark.observability.efficiency import EfficiencyCollector
from memory_benchmark.methods.simplemem_adapter import (
    SIMPLEMEM_LLM_MODEL_ID,
    SIMPLEMEM_OFFICIAL_PROFILE_NAME,
    SimpleMem,
    SimpleMemConfig,
    build_simplemem_source_identity,
    clean_simplemem_conversation_state,
    parse_simplemem_timestamp,
)
from memory_benchmark.methods.simplemem_adapter import _format_simplemem_memory


pytestmark = pytest.mark.unit


def _config(**overrides) -> SimpleMemConfig:
    """构造默认 SimpleMem 测试配置。"""

    payload = {
        "llm_model": "gpt-4o-mini",
        "embedding_model_path": "models/Qwen3-Embedding-0.6B",
        "embedding_dimension": 1024,
        "window_size": 40,
        "overlap_size": 2,
        "semantic_top_k": 25,
        "keyword_top_k": 5,
        "structured_top_k": 5,
        "max_workers": 1,
    }
    payload.update(overrides)
    return SimpleMemConfig(**payload)


def test_simplemem_config_manifest_and_local_model_validation() -> None:
    """SimpleMem config 应保留官方 text 参数并校验本地 Qwen 模型。"""

    config = _config()
    path_settings = load_path_settings()

    config.validate_required_local_resources(path_settings)
    manifest = config.to_manifest()

    assert manifest["profile_name"] == SIMPLEMEM_OFFICIAL_PROFILE_NAME
    assert manifest["official_profile"] == SIMPLEMEM_OFFICIAL_PROFILE_NAME
    assert manifest["backend"] == "text"
    assert manifest["llm_model"] == "gpt-4o-mini"
    assert manifest["embedding_model_path"] == "models/Qwen3-Embedding-0.6B"
    assert manifest["window_size"] == 40
    assert manifest["overlap_size"] == 2
    assert manifest["semantic_top_k"] == 25
    assert manifest["keyword_top_k"] == 5
    assert manifest["structured_top_k"] == 5


def test_simplemem_config_rejects_invalid_core_parameters() -> None:
    """SimpleMem config 应拒绝会破坏官方窗口语义的参数。"""

    with pytest.raises(ConfigurationError, match="overlap_size"):
        _config(overlap_size=40)

    with pytest.raises(ConfigurationError, match="semantic_top_k"):
        _config(semantic_top_k=0)

    with pytest.raises(ConfigurationError, match="api_max_retries"):
        _config(api_max_retries=-1)


def test_simplemem_local_model_validation_reports_missing_path(
    tmp_path: Path,
) -> None:
    """本地 embedding 路径缺失时应在构造真实 provider 前 fail-fast。"""

    config = _config(embedding_model_path="models/missing-qwen")
    path_settings = load_path_settings(project_root=tmp_path)

    with pytest.raises(ConfigurationError, match="required local embedding model"):
        config.validate_required_local_resources(path_settings)


def test_simplemem_source_identity_covers_text_core_and_wrapper() -> None:
    """SimpleMem source identity 应覆盖官方 text 核心文件与本项目 wrapper。"""

    identity = build_simplemem_source_identity(load_path_settings())

    assert identity["source_mode"] == "vendored-simplemem-text-plus-wrapper"
    assert identity["wrapper_path"] == "src/memory_benchmark/methods/simplemem_adapter.py"
    assert identity["file_count"] >= 10
    assert "main.py" in identity["files"]
    assert "simplemem/core/memory_builder.py" in identity["files"]
    assert "simplemem/core/hybrid_retriever.py" in identity["files"]
    assert "simplemem/core/answer_generator.py" in identity["files"]
    assert len(identity["source_sha256"]) == 64
    assert len(identity["wrapper_sha256"]) == 64


def test_simplemem_provider_skeleton_declares_protocol_shape(tmp_path: Path) -> None:
    """T1 registry skeleton 应构造 turn 粒度 v3 provider。"""

    provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
    )

    assert provider.consume_granularity == "turn"
    assert provider.session_memory_report is False
    assert provider.provenance_granularity == "none"


def test_simplemem_ingest_adds_turns_in_order_and_finalizes_once(
    tmp_path: Path,
) -> None:
    """T2 写入链路应保持逐 turn 顺序并在 conversation 末尾 finalize。"""

    created: dict[str, FakeSimpleMemSystem] = {}

    def factory(isolation_key: str, state_dir: Path) -> "FakeSimpleMemSystem":
        """构造记录调用序列的 fake SimpleMemSystem。"""

        system = FakeSimpleMemSystem(isolation_key=isolation_key, state_dir=state_dir)
        created[isolation_key] = system
        return system

    provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        system_factory=factory,
    )

    first = TurnEvent(
        role="user",
        speaker_name="Alice",
        content="Bob, let's meet at the cafe.",
        timestamp="1:56 pm on 8 May, 2023",
        isolation_key="conv/1",
        session_id="s1",
        turn_id="t1",
    )
    second = TurnEvent(
        role="assistant",
        speaker_name=None,
        content="Sure, see you there.",
        timestamp="2023-05-08T14:03:00",
        isolation_key="conv/1",
        session_id="s1",
        turn_id="t2",
    )

    first_result = provider.ingest(first)
    second_result = provider.ingest(second)
    provider.end_conversation(UnitRef(isolation_key="conv/1"))
    provider.end_conversation(UnitRef(isolation_key="conv/1"))

    system = created["conv/1"]
    assert system.state_dir.parent == tmp_path
    assert system.state_dir.name.startswith("isolation_")
    assert first_result is not None
    assert second_result is not None
    assert first_result.metadata["timestamp"] == "2023-05-08T13:56:00"
    assert second_result.metadata["timestamp"] == "2023-05-08T14:03:00"
    assert system.calls == [
        (
            "add_dialogue",
            {
                "speaker": "Alice",
                "content": "Bob, let's meet at the cafe.",
                "timestamp": "2023-05-08T13:56:00",
            },
        ),
        (
            "add_dialogue",
            {
                "speaker": "assistant",
                "content": "Sure, see you there.",
                "timestamp": "2023-05-08T14:03:00",
            },
        ),
        ("finalize", {}),
    ]


def test_simplemem_timestamp_parser_returns_none_for_unparseable() -> None:
    """SimpleMem timestamp 转换器不应猜测未知格式。"""

    assert parse_simplemem_timestamp(None) is None
    assert parse_simplemem_timestamp("   ") is None
    assert parse_simplemem_timestamp("next spring after lunch") is None


def test_simplemem_retrieve_uses_hybrid_retriever_and_builds_native_prompt(
    tmp_path: Path,
) -> None:
    """T3 检索应绕开 ask，并复刻官方 AnswerGenerator prompt 结构。"""

    system = FakeRetrievalSimpleMemSystem(
        [
            FakeMemoryEntry(
                entry_id="m1",
                lossless_restatement="Alice will meet Bob at the cafe.",
                timestamp="2023-05-08T13:56:00",
                persons=["Alice", "Bob"],
                topic="meeting",
            ),
            FakeMemoryEntry(
                entry_id="m2",
                lossless_restatement="The meeting topic is the new product.",
                timestamp="2023-05-08T14:03:00",
                entities=["new product"],
            ),
        ]
    )
    provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        system_factory=lambda _isolation_key, _state_dir: system,
    )

    result = provider.retrieve(
        RetrievalQuery(
            query_text="When will Alice meet Bob?",
            isolation_key="conv-1",
            question_time=None,
            top_k=5,
            purpose="qa",
        )
    )

    assert system.retrieve_queries == ["When will Alice meet Bob?"]
    assert system.ask_queries == []
    assert result.formatted_memory == (
        "[Context 1]\n"
        "Content: Alice will meet Bob at the cafe.\n"
        "Time: 2023-05-08T13:56:00\n"
        "Persons: Alice, Bob\n"
        "Topic: meeting\n"
        "\n"
        "[Context 2]\n"
        "Content: The meeting topic is the new product.\n"
        "Time: 2023-05-08T14:03:00\n"
        "Related Entities: new product"
    )
    assert result.items is not None
    assert [item.item_id for item in result.items] == ["m1", "m2"]
    assert result.items[0].source_turn_ids == ()
    assert result.prompt_messages is not None
    assert [message.role for message in result.prompt_messages] == ["system", "user"]
    assert result.prompt_messages[0].content == (
        "You are a professional Q&A assistant. Extract concise answers from "
        "context. You must output valid JSON format."
    )
    user_prompt = result.prompt_messages[1].content
    assert "User Question: When will Alice meet Bob?" in user_prompt
    assert "[Context 1]\nContent: Alice will meet Bob at the cafe." in user_prompt
    assert "Time: 2023-05-08T13:56:00" in user_prompt
    assert "Persons: Alice, Bob" in user_prompt
    assert "Topic: meeting" in user_prompt
    assert "Return ONLY the JSON, no other text." in user_prompt
    assert result.metadata["prompt_source"] == (
        "third_party/methods/SimpleMem/simplemem/core/answer_generator.py:43-52,117-153"
    )


def test_simplemem_formatted_memory_covers_all_symbolic_fields() -> None:
    """formatted_memory 应覆盖 MemoryEntry 全部 Symbolic 层字段，不丢 location/persons/entities/topic。

    对齐 ws02.5 audit F1：unified 口径用的 formatted_memory 必须与官方
    ``AnswerGenerator._format_contexts``（answer_generator.py:85-111）同口径，
    覆盖 lossless_restatement + timestamp + location + persons + entities + topic。
    """

    entry = FakeMemoryEntry(
        entry_id="m-full",
        lossless_restatement="Alice met Bob at Starbucks to discuss product XYZ.",
        timestamp="2025-11-15T14:30:00",
        location="Starbucks, Shanghai",
        persons=["Alice", "Bob"],
        entities=["product XYZ"],
        topic="product marketing",
    )

    memory = _format_simplemem_memory([entry])

    assert "Content: Alice met Bob at Starbucks to discuss product XYZ." in memory
    assert "Time: 2025-11-15T14:30:00" in memory
    assert "Location: Starbucks, Shanghai" in memory
    assert "Persons: Alice, Bob" in memory
    assert "Related Entities: product XYZ" in memory
    assert "Topic: product marketing" in memory


def test_simplemem_clean_retry_removes_partial_state_and_replays_all_turns(
    tmp_path: Path,
) -> None:
    """T4 clean retry 应删除半写入 isolation 状态，后续整段重放。"""

    first_systems: dict[str, FakeSimpleMemSystem] = {}
    first_provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        system_factory=lambda isolation_key, state_dir: first_systems.setdefault(
            isolation_key,
            FakeSimpleMemSystem(isolation_key=isolation_key, state_dir=state_dir),
        ),
    )
    first_provider.ingest(
        TurnEvent(
            role="user",
            speaker_name="Alice",
            content="Partial turn before crash.",
            timestamp=None,
            isolation_key="run-1_conv-1",
            session_id="s1",
            turn_id="t1",
            metadata={"conversation_id": "conv-1"},
        )
    )
    dirty_state_dir = first_systems["run-1_conv-1"].state_dir
    (dirty_state_dir / "partial.txt").write_text("dirty", encoding="utf-8")

    sibling_state = tmp_path / "isolation_sibling"
    sibling_state.mkdir()
    (sibling_state / "conversation_id.txt").write_text("conv-2", encoding="utf-8")

    clean_simplemem_conversation_state(tmp_path, "conv-1")

    assert not dirty_state_dir.exists()
    assert sibling_state.exists()

    replay_systems: dict[str, FakeSimpleMemSystem] = {}
    replay_provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        system_factory=lambda isolation_key, state_dir: replay_systems.setdefault(
            isolation_key,
            FakeSimpleMemSystem(isolation_key=isolation_key, state_dir=state_dir),
        ),
    )
    for turn_id, content in (("t1", "Partial turn before crash."), ("t2", "Replay turn.")):
        replay_provider.ingest(
            TurnEvent(
                role="user",
                speaker_name="Alice",
                content=content,
                timestamp=None,
                isolation_key="run-1_conv-1",
                session_id="s1",
                turn_id=turn_id,
                metadata={"conversation_id": "conv-1"},
            )
        )
    replay_provider.end_conversation(UnitRef(isolation_key="run-1_conv-1"))

    assert replay_systems["run-1_conv-1"].calls == [
        (
            "add_dialogue",
            {
                "speaker": "Alice",
                "content": "Partial turn before crash.",
                "timestamp": None,
            },
        ),
        (
            "add_dialogue",
            {
                "speaker": "Alice",
                "content": "Replay turn.",
                "timestamp": None,
            },
        ),
        ("finalize", {}),
    ]


def test_simplemem_llm_client_wrapper_records_usage_in_active_scope(
    tmp_path: Path,
) -> None:
    """T4 应记录 SimpleMem build/retrieval 服务型 LLM token usage。"""

    collector = EfficiencyCollector(run_id="simplemem-obs", enabled=True)
    system = FakeObservedSimpleMemSystem()
    provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        system_factory=lambda _isolation_key, _state_dir: system,
        efficiency_collector=collector,
    )

    with collector.conversation_scope("conv-1") as scope:
        provider.ingest(
            TurnEvent(
                role="user",
                speaker_name="Alice",
                content="Trigger wrapper install.",
                timestamp=None,
                isolation_key="run-1_conv-1",
                session_id="s1",
                turn_id="t1",
                metadata={"conversation_id": "conv-1"},
            )
        )
        assert system.llm_client.chat_completion(
            [{"role": "user", "content": "extract memory"}]
        ) == '{"answer": "ok"}'
        collector.record_memory_build_total_latency(latency_ms=1.0)

    llm_records = [
        record
        for record in scope.records
        if getattr(record, "model_id", None) == SIMPLEMEM_LLM_MODEL_ID
    ]
    assert len(llm_records) == 1
    assert llm_records[0].stage.value == "memory_build"
    assert llm_records[0].token_measurement_source.value == "tokenizer_estimate"
    assert llm_records[0].input_tokens > 0
    assert llm_records[0].output_tokens > 0


class FakeSimpleMemSystem:
    """记录 SimpleMem 写入调用的测试 fake。"""

    def __init__(self, *, isolation_key: str, state_dir: Path) -> None:
        """保存隔离键和状态目录。"""

        self.isolation_key = isolation_key
        self.state_dir = state_dir
        self.calls: list[tuple[str, dict[str, object]]] = []

    def add_dialogue(
        self,
        *,
        speaker: str,
        content: str,
        timestamp: str | None = None,
    ) -> None:
        """记录 add_dialogue 调用。"""

        self.calls.append(
            (
                "add_dialogue",
                {
                    "speaker": speaker,
                    "content": content,
                    "timestamp": timestamp,
                },
            )
        )

    def finalize(self) -> None:
        """记录 finalize 调用。"""

        self.calls.append(("finalize", {}))


class FakeMemoryEntry:
    """模拟 SimpleMem MemoryEntry 的公开字段。"""

    def __init__(
        self,
        *,
        entry_id: str,
        lossless_restatement: str,
        timestamp: str | None = None,
        keywords: list[str] | None = None,
        location: str | None = None,
        persons: list[str] | None = None,
        entities: list[str] | None = None,
        topic: str | None = None,
    ) -> None:
        """保存 fake memory entry 字段。"""

        self.entry_id = entry_id
        self.lossless_restatement = lossless_restatement
        self.timestamp = timestamp
        self.keywords = keywords or []
        self.location = location
        self.persons = persons or []
        self.entities = entities or []
        self.topic = topic


class FakeHybridRetriever:
    """记录 retrieve 查询并返回预置 entries。"""

    def __init__(
        self,
        entries: list[FakeMemoryEntry],
        query_log: list[str],
    ) -> None:
        """保存预置 entries 和查询日志。"""

        self.entries = entries
        self.query_log = query_log

    def retrieve(self, query_text: str) -> list[FakeMemoryEntry]:
        """模拟 SimpleMem HybridRetriever.retrieve。"""

        self.query_log.append(query_text)
        return self.entries


class FakeRetrievalSimpleMemSystem:
    """带 hybrid_retriever 与 ask 记录的检索 fake。"""

    def __init__(self, entries: list[FakeMemoryEntry]) -> None:
        """创建 fake retriever。"""

        self.retrieve_queries: list[str] = []
        self.ask_queries: list[str] = []
        self.hybrid_retriever = FakeHybridRetriever(entries, self.retrieve_queries)

    def ask(self, query_text: str) -> str:
        """若 adapter 误调 ask，测试会通过日志发现。"""

        self.ask_queries.append(query_text)
        return "should not be used"


class FakeObservedLLMClient:
    """可被 SimpleMem adapter 包装的 fake LLMClient。"""

    def __init__(self) -> None:
        """初始化调用日志。"""

        self.calls: list[list[dict[str, str]]] = []

    def chat_completion(self, messages: list[dict[str, str]], **_kwargs) -> str:
        """模拟官方 chat_completion，只返回文本。"""

        self.calls.append(messages)
        return '{"answer": "ok"}'


class FakeObservedSimpleMemSystem(FakeSimpleMemSystem):
    """带 llm_client 的写入 fake。"""

    def __init__(self) -> None:
        """初始化 fake system。"""

        super().__init__(isolation_key="run-1_conv-1", state_dir=Path("/tmp/fake"))
        self.llm_client = FakeObservedLLMClient()

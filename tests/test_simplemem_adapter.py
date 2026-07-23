"""测试 SimpleMem adapter 的配置、资源和 source identity。"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from memory_benchmark.config import OpenAISettings, load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    RetrievalQuery,
    SessionRef,
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
    assert manifest["enable_parallel_processing"] is False
    assert manifest["enable_parallel_retrieval"] is True


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


def test_simplemem_real_text_product_imports_and_native_fts_works(
    tmp_path: Path,
) -> None:
    """真实 text product 必须可导入，当前 LanceDB native FTS 必须真可查。

    fake ``system_factory`` 测试不会触发官方 ``main.py`` 的顶层 import；
    该门同时防止缺失 ``dateparser`` 或旧 ``use_tantivy=True`` 直到付费
    smoke 才暴露。
    """

    project_root = Path(__file__).resolve().parents[1]
    product_root = project_root / "third_party" / "methods" / "SimpleMem"
    product_patch = (
        project_root / "scripts" / "patches" / "simplemem-product-compat.patch"
    )
    patch_check = subprocess.run(
        [
            "git",
            "-C",
            str(product_root),
            "apply",
            "--unidiff-zero",
            "--reverse",
            "--check",
            str(product_patch),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert patch_check.returncode == 0, patch_check.stderr
    script = (
        "import sys\n"
        "import numpy as np\n"
        f"sys.path.insert(0, {str(product_root)!r})\n"
        "from main import SimpleMemSystem\n"
        "from simplemem.core.database.vector_store import VectorStore\n"
        "from simplemem.core.models.memory_entry import MemoryEntry\n"
        "class FakeEmbedding:\n"
        "    dimension = 2\n"
        "    def encode_documents(self, texts):\n"
        "        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)\n"
        "    def encode_single(self, text, is_query=False):\n"
        "        return np.array([1.0, 0.0], dtype=np.float32)\n"
        "assert SimpleMemSystem.__name__ == 'SimpleMemSystem'\n"
        f"store = VectorStore(db_path={str(tmp_path / 'lancedb')!r}, "
        "embedding_model=FakeEmbedding(), table_name='memories')\n"
        "store.add_entries([MemoryEntry("
        "entry_id='m1', "
        "lossless_restatement='Caroline attended an LGBTQ support group', "
        "keywords=['Caroline', 'support'])])\n"
        "assert store._fts_initialized is True\n"
        "hits = store.keyword_search(['Caroline', 'support'], top_k=3)\n"
        "assert [item.entry_id for item in hits] == ['m1']\n"
        "from contextvars import ContextVar\n"
        "from simplemem.core.hybrid_retriever import HybridRetriever\n"
        "probe = ContextVar('simplemem_probe', default='missing')\n"
        "retriever = object.__new__(HybridRetriever)\n"
        "retriever.max_retrieval_workers = 2\n"
        "retriever._semantic_search_worker = "
        "lambda query, index: [probe.get()]\n"
        "token = probe.set('question-scope')\n"
        "try:\n"
        "    values = retriever._execute_parallel_searches(['q1', 'q2'])\n"
        "finally:\n"
        "    probe.reset(token)\n"
        "assert values == ['question-scope', 'question-scope']\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


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


@pytest.mark.parametrize(
    ("raw_timestamp", "expected"),
    [
        ("2023/05/20 (Sat) 02:21", "2023-05-20T02:21:00"),
        ("March-15-2024", "2024-03-15T00:00:00"),
        ("2024-10-01 08:00", "2024-10-01T08:00:00"),
    ],
)
def test_simplemem_timestamp_parser_covers_all_benchmark_source_formats(
    raw_timestamp: str,
    expected: str,
) -> None:
    """五家 benchmark 的非 LoCoMo 时间格式也必须确定性解析。"""

    assert parse_simplemem_timestamp(raw_timestamp) == expected


def test_simplemem_ingest_rejects_nonempty_unknown_timestamp(tmp_path: Path) -> None:
    """非空时间不能静默降级为 None。"""

    provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        system_factory=lambda isolation_key, state_dir: FakeSimpleMemSystem(
            isolation_key=isolation_key,
            state_dir=state_dir,
        ),
    )

    with pytest.raises(ConfigurationError, match="cannot normalize timestamp"):
        provider.ingest(
            TurnEvent(
                role="user",
                speaker_name="user",
                content="Unknown-time message.",
                timestamp="sometime after lunch",
                isolation_key="conv-1",
                session_id="s1",
                turn_id="t1",
            )
        )


def test_simplemem_ingest_preserves_speaker_content_caption_and_typed_time(
    tmp_path: Path,
) -> None:
    """写入应保留 speaker，不重写 MemBench 尾部，图片用共享语义。"""

    system = FakeSimpleMemSystem(isolation_key="conv-1", state_dir=tmp_path)
    provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        system_factory=lambda _isolation_key, _state_dir: system,
    )
    source = (
        "I visited Boston. "
        "(place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
    )

    provider.ingest(
        TurnEvent(
            role="assistant",
            speaker_name="assistant",
            content="legacy rendered text",
            timestamp="2024-10-01 08:00",
            isolation_key="conv-1",
            session_id="s1",
            turn_id="t1",
            metadata={
                "original_content": source,
                "turn_images": [
                    {
                        "image_id": "img-1",
                        "path": None,
                        "caption": "a red bicycle",
                        "metadata": {},
                    }
                ],
            },
        )
    )

    payload = system.calls[0][1]
    assert payload == {
        "speaker": "assistant",
        "content": f"{source} [Sharing image that shows: a red bicycle]",
        "timestamp": "2024-10-01T08:00:00",
    }


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
    assert result.evidence is not None
    assert result.evidence.semantic_provenance.status == "n_a"
    assert result.evidence.semantic_provenance.reason_code == (
        "simplemem_synthesized_memory_not_turn_exact"
    )
    assert result.evidence.provenance_granularity == "none"
    assert result.evidence.stable_ranking.status == "pending"
    assert (
        result.evidence.stable_ranking.reason_code
        == "simplemem_parallel_merge_has_no_stable_global_rank"
    )
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


def test_simplemem_halumem_session_report_returns_only_new_synthesized_entries(
    tmp_path: Path,
) -> None:
    """HaluMem 边界只上报当次 finalize 新生成的产品记忆。"""

    class FakeBuilder:
        """模拟官方窗口的 previous_entries 状态。"""

        def __init__(self) -> None:
            """预置上一窗口参考。"""

            self.previous_entries = ["old-window-entry"]

    class FakeSessionSystem(FakeSimpleMemSystem):
        """每次 finalize 向全库增加一条记忆的 fake。"""

        def __init__(self) -> None:
            """初始化累计记忆与窗口状态。"""

            super().__init__(isolation_key="conv-1", state_dir=tmp_path)
            self.memory_builder = FakeBuilder()
            self.entries: list[FakeMemoryEntry] = []

        def finalize(self) -> None:
            """模拟完成当前 session 的合成。"""

            super().finalize()
            index = len(self.entries) + 1
            self.entries.append(
                FakeMemoryEntry(
                    entry_id=f"m{index}",
                    lossless_restatement=f"session memory {index}",
                    timestamp=f"2024-01-0{index}T00:00:00",
                )
            )

        def get_all_memories(self) -> list[FakeMemoryEntry]:
            """返回截至当前的全部记忆。"""

            return list(self.entries)

    system = FakeSessionSystem()
    provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        system_factory=lambda _isolation_key, _state_dir: system,
        session_memory_report=True,
        benchmark_name="halumem",
    )
    provider.ingest(
        TurnEvent(
            role="user",
            speaker_name="user",
            content="first session",
            timestamp=None,
            isolation_key="conv-1",
            session_id="s1",
            turn_id="t1",
        )
    )
    first = provider.end_session(SessionRef("conv-1", "s1"))
    provider.ingest(
        TurnEvent(
            role="assistant",
            speaker_name="assistant",
            content="second session",
            timestamp=None,
            isolation_key="conv-1",
            session_id="s2",
            turn_id="t2",
        )
    )
    second = provider.end_session(SessionRef("conv-1", "s2"))

    assert first is not None and second is not None
    assert len(first.memories) == 1
    assert "session memory 1" in first.memories[0]
    assert len(second.memories) == 1
    assert "session memory 2" in second.memories[0]
    assert system.memory_builder.previous_entries == []


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


def test_simplemem_embedding_wrapper_records_actual_calls_in_active_scope(
    tmp_path: Path,
) -> None:
    """SimpleMem 本地 embedding 只在实际 encode 成功后记录。"""

    class FakeTokenizer:
        """按空格切分的可确定 token 计数器。"""

        def encode(self, text: str, **_kwargs: object) -> list[str]:
            """返回伪 token 序列。"""

            return text.split()

    class FakeSentenceTransformer:
        """暴露 SimpleMem observer 依赖的 tokenizer 字段。"""

        tokenizer = FakeTokenizer()
        max_seq_length = 128

    class FakeEmbeddingModel:
        """模拟产品 EmbeddingModel.encode。"""

        def __init__(self) -> None:
            """保存底层 SentenceTransformer fake。"""

            self.model = FakeSentenceTransformer()

        def encode(self, texts: list[str], **_kwargs: object) -> list[list[float]]:
            """返回与输入数量一致的伪向量。"""

            return [[1.0] for _ in texts]

    system = FakeObservedSimpleMemSystem()
    system.embedding_model = FakeEmbeddingModel()
    collector = EfficiencyCollector(run_id="simplemem-embedding", enabled=True)
    provider = SimpleMem(
        config=_config(),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        system_factory=lambda _isolation_key, _state_dir: system,
        efficiency_collector=collector,
    )
    provider.ingest(
        TurnEvent(
            role="user",
            speaker_name="user",
            content="install observers",
            timestamp=None,
            isolation_key="conv-1",
            session_id="s1",
            turn_id="t1",
        )
    )

    with collector.conversation_scope("conv-1") as scope:
        assert system.embedding_model.encode(["two tokens", "three token input"]) == [
            [1.0],
            [1.0],
        ]
        collector.record_memory_build_total_latency(latency_ms=1.0)

    records = [
        record
        for record in scope.records
        if getattr(record, "model_id", None) == "simplemem-embedding"
    ]
    assert len(records) == 1
    assert records[0].input_tokens == 5
    assert records[0].stage.value == "memory_build"


def test_simplemem_transport_uses_profile_timeout_and_product_retry_loop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SimpleMem transport 不得忽略 TOML timeout/retry 或形成双层重试。"""

    created_clients: list[dict[str, object]] = []
    completion_kwargs: list[dict[str, object]] = []

    class FakeLLMClient:
        """模拟官方带 max_retries 参数的 LLMClient。"""

        client: object | None = None

        def chat_completion(
            self,
            messages: list[dict[str, str]],
            **kwargs: object,
        ) -> str:
            """记录 adapter 注入的产品层 retry 次数。"""

            del messages
            completion_kwargs.append(dict(kwargs))
            return "ok"

    class FakeSystem:
        """只暴露 transport 配置需要的官方字段。"""

        def __init__(self) -> None:
            """创建 fake LLM client。"""

            self.llm_client = FakeLLMClient()

    import openai

    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **kwargs: created_clients.append(dict(kwargs)) or object(),
    )
    provider = SimpleMem(
        config=_config(api_timeout_seconds=17.0, api_max_retries=6),
        path_settings=load_path_settings(),
        storage_root=tmp_path,
        openai_settings=OpenAISettings(
            api_key="sk-offline-test",
            base_url="https://example.invalid/v1",
        ),
    )
    system = FakeSystem()

    provider._configure_official_llm_transport(
        system=system,
        isolation_key="conv-1",
    )
    assert system.llm_client.chat_completion(
        [{"role": "user", "content": "probe"}]
    ) == "ok"

    assert created_clients == [
        {
            "api_key": "sk-offline-test",
            "base_url": "https://example.invalid/v1",
            "timeout": 17.0,
            "max_retries": 0,
        }
    ]
    assert completion_kwargs == [{"max_retries": 7}]


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

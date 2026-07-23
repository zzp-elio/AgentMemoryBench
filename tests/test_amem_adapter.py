"""A-Mem adapter 的配置、源码身份和基础契约测试。

这些测试默认不调用真实 API。测试目标是确认 adapter 能找到 vendored A-Mem 源码、
能加载强类型 profile，并且 source identity 会覆盖官方核心源码。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.config import OpenAISettings, load_path_settings
from memory_benchmark.core import (
    AnswerResult,
    ConfigurationError,
    Conversation,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
)
from memory_benchmark.core.provider_protocol import (
    MemoryProvider,
    RetrievalQuery,
    SessionRef,
    TurnEvent,
)
from memory_benchmark.methods.amem_adapter import (
    AMem,
    AMemConfig,
    build_amem_source_identity,
    clean_amem_conversation_state,
    import_amem_product_classes,
)
import memory_benchmark.methods.amem_adapter as amem_adapter_module
from memory_benchmark.methods.registry import MethodBuildContext, _build_amem_system
from memory_benchmark.observability.efficiency import EfficiencyCollector
from memory_benchmark.runners.prediction import _method_manifest_with_protocol
from tests.equivalence_utils import run_bridge_sequence, run_native_sequence


def test_amem_config_rejects_invalid_retrieve_k() -> None:
    """retrieve_k 是 method 内部检索深度，必须为正数。"""

    with pytest.raises(ConfigurationError, match="retrieve_k"):
        AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=0,
            max_workers=1,
            use_product_layer=True,
            profile_name="bad",
        )


def test_amem_source_identity_covers_official_core_files() -> None:
    """source identity 必须覆盖 A-Mem 官方核心文件，保证 resume 可审计。"""

    identity = build_amem_source_identity(load_path_settings())

    assert identity["source_sha256"]
    assert identity["file_count"] >= 3
    assert identity["source_mode"] == "official-general-product-plus-wrapper"
    assert "agentic_memory/memory_system.py" in identity["files"]
    assert "agentic_memory/retrievers.py" in identity["files"]
    assert "README.md" in identity["files"]
    assert "agentic_memory/llm_controller.py" in identity["files"]


def test_clean_amem_conversation_state_only_removes_target_directory(
    tmp_path: Path,
) -> None:
    """A-Mem clean retry 只能删除目标 conversation 的持久化 state。

    输入:
        storage_root: 同时包含目标 conversation state 和 sibling state。

    输出:
        目标目录被删除，其他 conversation 的目录保持不变。
    """

    target_state = tmp_path / "conv_1"
    sibling_state = tmp_path / "conv-2"
    target_state.mkdir()
    sibling_state.mkdir()
    (target_state / "partial.pkl").write_text("dirty", encoding="utf-8")
    (sibling_state / "state_manifest.json").write_text("{}", encoding="utf-8")

    clean_amem_conversation_state(tmp_path, "conv/1")

    assert not target_state.exists()
    assert sibling_state.exists()


class FakeAMemRuntime:
    """模拟 A-Mem runtime，只记录 wrapper 传入的公开内容。"""

    def __init__(self, *, build_llm: object | None = None) -> None:
        """初始化 fake 调用记录。"""

        self.added_notes: list[dict[str, object]] = []
        self.queries: list[dict[str, object]] = []
        self.memories: dict[str, SimpleNamespace] = {}
        self.retriever = FakeAMemRetriever()
        if build_llm is not None:
            self.llm_controller = SimpleNamespace(llm=build_llm)

    def analyze_content(self, content: str) -> dict[str, object]:
        """模拟通用产品显式内容分析入口。"""

        return {
            "keywords": ["memory"],
            "context": "fake context",
            "tags": ["fake"],
        }

    def add_note(
        self,
        content: str,
        time: str | None = None,
        **kwargs: object,
    ) -> str:
        """记录写入内容并返回 fake note id。"""

        if hasattr(self, "llm_controller"):
            self.llm_controller.llm.get_completion(
                f"Analyze memory content: {content}",
                temperature=0.3,
            )
        self.added_notes.append({"content": content, "time": time, **kwargs})
        note_id = f"note-{len(self.added_notes)}"
        self.memories[note_id] = SimpleNamespace(
            id=note_id,
            content=content,
            timestamp=time,
            keywords=list(kwargs.get("keywords") or []),
            context=str(kwargs.get("context") or ""),
            tags=list(kwargs.get("tags") or []),
            links=[],
            retrieval_count=0,
            last_accessed=None,
            evolution_history=[],
            category="Uncategorized",
        )
        self.retriever.saved_documents.append(content)
        return note_id

    def update(self, note_id: str, **kwargs: object) -> bool:
        """模拟产品 update，用于保留缺失时间。"""

        note = self.memories.get(note_id)
        if note is None:
            return False
        for key, value in kwargs.items():
            setattr(note, key, value)
        return True

    def search_agentic(self, query: str, k: int = 5) -> list[dict[str, object]]:
        """模拟通用产品有序检索入口。"""

        self.queries.append({"query": query, "k": k})
        return [
            {
                "id": note.id,
                "content": note.content,
                "timestamp": note.timestamp,
                "context": note.context,
                "keywords": note.keywords,
                "tags": note.tags,
                "score": 1.0 / index,
                "is_neighbor": False,
            }
            for index, note in enumerate(list(self.memories.values())[:k], 1)
        ]

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

    def add_document(
        self,
        document: str,
        metadata: dict[str, object],
        doc_id: str,
    ) -> None:
        """模拟恢复时的产品索引重建。"""

        del metadata, doc_id
        self.saved_documents.append(document)

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


class FakeAMemLLMWithUsage(FakeAMemLLM):
    """模拟能暴露 API usage 的 A-Mem LLM wrapper。"""

    def get_completion(self, prompt: str, temperature: float = 0.7) -> str:
        """记录 prompt，同时暴露最近一次 API usage。"""

        response = super().get_completion(prompt, temperature=temperature)
        self.last_usage = SimpleNamespace(prompt_tokens=11, completion_tokens=3)
        return response


def _snapshot_amem_calls_and_state(system: AMem) -> list[dict[str, object]]:
    """把 A-Mem runtime 调用和持久化状态归一化为可比较序列。"""

    calls: list[dict[str, object]] = []
    for conversation_id, runtime in system._runtimes.items():
        for note in runtime.added_notes:
            calls.append(
                {
                    "op": "add_note",
                    "conversation_id": conversation_id,
                    "content": note["content"],
                    "time": note["time"],
                }
            )
        for query in runtime.queries:
            calls.append(
                {
                    "op": "retrieve",
                    "conversation_id": conversation_id,
                    "query": query["query"],
                    "k": query["k"],
                }
            )
        state_dir = system._conversation_state_dir(conversation_id)
        if state_dir.exists():
            calls.append(
                {
                    "op": "state",
                    "conversation_id": conversation_id,
                    "files": _state_file_hashes(state_dir),
                    "manifest": json.loads(
                        (state_dir / "state_manifest.json").read_text("utf-8")
                    ),
                }
            )
    return calls


def _state_file_hashes(state_dir: Path) -> dict[str, str]:
    """返回 A-Mem 状态文件的内容哈希。"""

    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(state_dir.iterdir())
        if path.is_file()
    }


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


def _longmemeval_conversation() -> Conversation:
    """构造 LongMemEval 风格 conversation，用于验证 question_time reader prompt。

    输入:
        无。

    输出:
        Conversation: 一个 LongMemEval instance 映射成的 conversation；haystack
        date 放在 `session_time`，question date 放在 `question_time`。
    """

    question = Question(
        question_id="lme:q1",
        conversation_id="lme:q1",
        text="What tea does the user like?",
        question_time="2026-01-04",
        category="single-session-user",
        metadata={"source_format": "longmemeval"},
    )
    return Conversation(
        conversation_id="lme:q1",
        sessions=[
            Session(
                session_id="haystack-1",
                session_time="2026-01-01",
                turns=[
                    Turn(
                        turn_id="haystack-1:t0",
                        speaker="user",
                        content="I like jasmine tea.",
                    ),
                    Turn(
                        turn_id="haystack-1:t1",
                        speaker="assistant",
                        content="I will remember that.",
                    ),
                ],
                metadata={"source_format": "longmemeval_haystack_session"},
            )
        ],
        questions=[question],
        gold_answers={
            question.question_id: GoldAnswerInfo(
                question_id=question.question_id,
                answer="jasmine tea",
                evidence=["haystack-1"],
            )
        },
        metadata={"source_path": "data/longmemeval/longmemeval_s_cleaned.json"},
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
    assert runtime.queries == [{"query": "generated keywords", "k": 2}]
    assert "generate several keywords separated by commas" in str(llm.prompts[0]["prompt"])


def test_amem_retrieve_returns_query_keywords_and_context(tmp_path) -> None:
    """retrieve 应保留官方 query keyword generation，统一用 profile retrieve_k。"""

    runtime = FakeAMemRuntime()
    llm = FakeAMemLLM()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
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
        question_id="q-1",
        conversation_id="conv-1",
        text="Where did Alice go?",
        category="1",
    )

    retrieval = method.retrieve(question)

    assert retrieval.question_id == "q-1"
    assert retrieval.conversation_id == "conv-1"
    assert [message.role for message in retrieval.prompt_messages] == [
        "system",
        "user",
    ]
    assert "Follow the format specified" in retrieval.prompt_messages[0].content
    assert "memory content from fake runtime" in retrieval.answer_prompt
    assert "Where did Alice go?" in retrieval.answer_prompt
    assert retrieval.metadata["answer_context"] == "memory content from fake runtime"
    assert retrieval.metadata["method"] == "amem"
    assert retrieval.metadata["query_keywords"] == "generated keywords"
    assert retrieval.metadata["retrieve_k"] == 2
    assert retrieval.metadata["query_keyword_prompt_version"]
    assert runtime.queries == [{"query": "generated keywords", "k": 2}]
    assert len(llm.prompts) == 1
    assert "generate several keywords separated by commas" in str(
        llm.prompts[0]["prompt"]
    )


def test_amem_longmemeval_retrieve_uses_lightmem_style_reader_prompt(tmp_path) -> None:
    """A-Mem LongMemEval prompt 应保留 method-specific memory context。

    该测试不调用真实 API；fake LLM 只返回检索关键词，fake runtime 返回固定
    `memory content/context/keywords/tags` 字符串，验证 adapter 不会把 A-Mem 的
    检索上下文丢掉。
    """

    runtime = FakeAMemRuntime()
    llm = FakeAMemLLM()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=3,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: runtime,
        answer_llm=llm,
        storage_root=tmp_path,
    )
    conversation = _longmemeval_conversation()

    method.add(conversation)
    retrieval = method.retrieve(conversation.questions[0])

    assert [message.role for message in retrieval.prompt_messages] == [
        "system",
        "user",
    ]
    assert retrieval.prompt_messages[0].content == "You are a helpful assistant."
    user_prompt = retrieval.prompt_messages[1].content
    assert (
        "Question time:2026-01-04 and question:What tea does the user like?"
        in user_prompt
    )
    assert "Please answer the question based on the following memories:" in user_prompt
    assert "memory content from fake runtime" in user_prompt
    assert retrieval.metadata["answer_context"] == "memory content from fake runtime"
    assert retrieval.metadata["answer_prompt_profile"] == "lightmem_longmemeval_reader_v1"
    assert retrieval.metadata["query_keywords"] == "generated keywords"
    assert retrieval.metadata["retrieve_k"] == 3


def test_amem_v3_preserves_roles_speakers_caption_time_and_exact_lineage(
    tmp_path: Path,
) -> None:
    """产品 v3 链路应无损写入五格输入并保留 turn sidecar。"""

    runtime = FakeAMemRuntime()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=10,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda _conversation_id: runtime,
        storage_root=tmp_path,
    )
    method.ingest(
        TurnEvent(
            role="Caroline",
            speaker_name="Caroline",
            content="legacy caption rendering",
            timestamp="1:56 pm on 8 May, 2023",
            isolation_key="run_conv-1",
            session_id="s1",
            turn_id="D1:1",
            metadata={
                "conversation_id": "conv-1",
                "original_content": "I adopted a cat.",
                "original_session_time": "1:56 pm on 8 May, 2023",
                "original_turn_time": None,
                "turn_images": [
                    {
                        "image_id": "img-1",
                        "path": None,
                        "caption": "a gray kitten",
                        "metadata": {},
                    }
                ],
            },
        )
    )
    method.ingest(
        TurnEvent(
            role="assistant",
            speaker_name="assistant",
            content="Thanks for sharing.",
            timestamp="2024-10-01 08:00",
            isolation_key="run_conv-1",
            session_id="s1",
            turn_id="D1:2",
            metadata={
                "conversation_id": "conv-1",
                "original_content": "Thanks for sharing.",
                "original_turn_time": "2024-10-01 08:00",
            },
        )
    )

    assert runtime.added_notes[0]["content"] == (
        "Caroline: I adopted a cat. "
        "[Sharing image that shows: a gray kitten]"
    )
    assert runtime.added_notes[0]["time"] == "1:56 pm on 8 May, 2023"
    assert runtime.added_notes[1]["content"] == "assistant: Thanks for sharing."
    assert runtime.added_notes[1]["time"] == "2024-10-01 08:00"

    result = method.retrieve(
        RetrievalQuery(
            query_text="What pet did Caroline adopt?",
            isolation_key="run_conv-1",
            question_time=None,
            top_k=10,
            purpose="qa",
        )
    )

    assert result.items is not None
    assert [item.source_turn_ids for item in result.items] == [
        ("D1:1",),
        ("D1:2",),
    ]
    assert result.items[0].timestamp == "1:56 pm on 8 May, 2023"
    assert "Time: 1:56 pm on 8 May, 2023" in result.formatted_memory
    assert result.evidence is not None
    assert result.evidence.semantic_provenance.status == "valid"
    assert result.evidence.provenance_granularity == "turn"
    assert result.evidence.stable_ranking.status == "valid"
    assert runtime.queries[-1] == {
        "query": "What pet did Caroline adopt?",
        "k": 10,
    }


def test_amem_v3_preserves_missing_timestamp_and_reports_halumem_delta(
    tmp_path: Path,
) -> None:
    """缺失时间不得被墙钟污染，HaluMem 只上报当前 session 新 note。"""

    runtime = FakeAMemRuntime()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=10,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda _conversation_id: runtime,
        storage_root=tmp_path,
        session_memory_report=True,
        benchmark_name="halumem",
    )
    method.ingest(
        TurnEvent(
            role="user",
            speaker_name="user",
            content="A timeless noise message.",
            timestamp=None,
            isolation_key="run_conv-1",
            session_id="s1",
            turn_id="t1",
            metadata={"conversation_id": "conv-1"},
        )
    )
    first = method.end_session(SessionRef("run_conv-1", "s1"))
    second = method.end_session(SessionRef("run_conv-1", "s1"))

    assert runtime.memories["note-1"].timestamp is None
    assert first is not None and second is not None
    assert len(first.memories) == 1
    assert "Memory content: user: A timeless noise message." in first.memories[0]
    assert second.memories == []


def test_amem_v3_rejects_product_analysis_failure_sentinel(tmp_path: Path) -> None:
    """官方吞掉 API/JSON 异常后的固定空分析不得形成假绿 note。"""

    runtime = FakeAMemRuntime()
    runtime.analyze_content = lambda _content: {
        "keywords": [],
        "context": "General",
        "tags": [],
    }
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=10,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda _conversation_id: runtime,
        storage_root=tmp_path,
    )

    with pytest.raises(ConfigurationError, match="content analysis failed"):
        method.ingest(
            TurnEvent(
                role="user",
                speaker_name="user",
                content="important fact",
                timestamp=None,
                isolation_key="run_conv-1",
                session_id="s1",
                turn_id="t1",
                metadata={"conversation_id": "conv-1"},
            )
        )

    assert runtime.added_notes == []


def test_amem_v3_rejects_false_zero_hit_from_nonempty_product_store(
    tmp_path: Path,
) -> None:
    """search_agentic 吞错后返回的 [] 不得冒充合法 zero-hit。"""

    runtime = FakeAMemRuntime()
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=10,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda _conversation_id: runtime,
        storage_root=tmp_path,
    )
    method.ingest(
        TurnEvent(
            role="user",
            speaker_name="user",
            content="important fact",
            timestamp=None,
            isolation_key="run_conv-1",
            session_id="s1",
            turn_id="t1",
            metadata={"conversation_id": "conv-1"},
        )
    )
    runtime.search_agentic = lambda _query, k=5: []

    with pytest.raises(ConfigurationError, match="non-empty memory store"):
        method.retrieve(
            RetrievalQuery(
                query_text="important",
                isolation_key="run_conv-1",
                question_time=None,
                top_k=10,
                purpose="qa",
            )
        )


def test_amem_add_persists_conversation_state(tmp_path) -> None:
    """A-Mem 写完 conversation 后应保存 memories、lineage 和 manifest。"""

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
    assert (state_dir / "note_lineage.json").is_file()
    assert manifest["conversation_id"] == "conv-1"
    assert manifest["adapter_version"]
    assert manifest["turn_count"] == 2
    assert manifest["profile"]["profile_name"] == "smoke"
    assert set(manifest["files"]) == {
        "memories.pkl",
        "note_lineage.json",
    }


def test_native_amem_preserves_add_state_but_uses_product_retrieval(
    tmp_path: Path,
) -> None:
    """v3 保持写入/状态，检索则必须改用通用产品入口。"""

    conversation = _conversation_with_private_gold()
    question = conversation.questions[0]
    bridge = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda conversation_id: FakeAMemRuntime(),
        answer_llm=FakeAMemLLM(),
        storage_root=tmp_path / "bridge",
    )
    native = AMem(
        config=bridge.config,
        runtime_factory=lambda conversation_id: FakeAMemRuntime(),
        answer_llm=FakeAMemLLM(),
        storage_root=tmp_path / "native",
    )

    bridge_result = run_bridge_sequence(
        provider=bridge,
        conversation=conversation,
        question=question,
        run_id="amem-equivalence",
        snapshot_calls=_snapshot_amem_calls_and_state,
    )
    native_result = run_native_sequence(
        provider=native,
        conversation=conversation,
        question=question,
        run_id="amem-equivalence",
        snapshot_calls=_snapshot_amem_calls_and_state,
    )

    assert isinstance(native, MemoryProvider)
    assert bridge_result.calls[:2] == native_result.calls[:2]
    assert bridge_result.calls[-1] == native_result.calls[-1]
    assert bridge_result.calls[2]["query"] == "generated keywords"
    assert native_result.calls[2]["query"] == "What does Alice like?"
    assert (tmp_path / "native" / "conv-1" / "state_manifest.json").is_file()


def test_amem_registry_builds_native_v3_provider(tmp_path: Path) -> None:
    """registry 应直接构造 A-Mem 原生 v3 provider。"""

    provider = _build_amem_system(
        MethodBuildContext(
            config=AMemConfig(
                llm_model="gpt-4o-mini",
                embedding_model="all-MiniLM-L6-v2",
                retrieve_k=2,
                max_workers=1,
                profile_name="smoke",
            ),
            openai_settings=OpenAISettings(api_key="sk-test"),
            path_settings=load_path_settings(),
            storage_root=tmp_path,
            benchmark_name="locomo",
        )
    )

    assert isinstance(provider, MemoryProvider)
    assert provider.consume_granularity == "turn"
    assert _method_manifest_with_protocol(
        method_manifest={},
        protocol_version="v3",
    )["protocol_version"] == "v3"


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
    assert restored_runtime.retriever.loaded_from is None
    assert restored_runtime.retriever.saved_documents == [
        note.content for note in first_runtime.memories.values()
    ]
    assert restored_runtime.queries == [{"query": "generated keywords", "k": 2}]


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


def test_amem_get_answer_uses_unified_retrieve_k_across_categories(tmp_path) -> None:
    """归一化后各 category 统一用 profile retrieve_k（不再按 Table 8 per-category k）。"""

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

    for category in ("1", "2", "3", "4"):
        question = Question(
            question_id=f"q-{category}",
            conversation_id="conv-1",
            text=f"Question for category {category}?",
            category=category,
        )
        method.get_answer(question)
        assert runtime.queries[-1] == {
            "query": "generated keywords",
            "k": 10,
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


def test_amem_can_import_official_product_layer_without_calling_api() -> None:
    """adapter 应能从 A-Mem 通用仓库导入官方产品 runtime。"""

    classes = import_amem_product_classes(load_path_settings())

    assert classes["AgenticMemorySystem"].__name__ == "AgenticMemorySystem"
    assert classes["ChromaRetriever"].__name__ == "ChromaRetriever"
    assert classes["PersistentChromaRetriever"].__name__ == "PersistentChromaRetriever"
    assert "third_party/A-mem/agentic_memory" in str(
        Path(classes["memory_system_module"].__file__).resolve()
    )


def test_amem_scoped_consolidation_rebuilds_only_target_conversation(
    tmp_path: Path,
) -> None:
    """产品触发 consolidation 时不得 reset sibling conversation 的索引。"""

    class FakeClient:
        """记录单个 conversation client 的 reset 次数。"""

        def __init__(self) -> None:
            """初始化 reset 计数。"""

            self.reset_calls = 0

        def reset(self) -> None:
            """记录产品要求的索引清空动作。"""

            self.reset_calls += 1

    class FakeScopedRetriever:
        """模拟 consolidation 后的 conversation-scoped retriever。"""

        instances: list["FakeScopedRetriever"] = []

        def __init__(self, collection_name: str, model_name: str) -> None:
            """保留官方构造参数并记录新索引。"""

            self.collection_name = collection_name
            self.model_name = model_name
            self.client = FakeClient()
            self.documents: list[tuple[str, str]] = []
            self.instances.append(self)

        def add_document(
            self,
            document: str,
            metadata: dict[str, object],
            doc_id: str,
        ) -> None:
            """记录按官方 MemoryNote 集合重建的文档。"""

            assert metadata["id"] == doc_id
            self.documents.append((doc_id, document))

    target_client = FakeClient()
    sibling_client = FakeClient()
    note = SimpleNamespace(
        id="note-1",
        content="target memory",
        keywords=["target"],
        links=[],
        retrieval_count=0,
        timestamp=None,
        last_accessed=None,
        context="test",
        evolution_history=[],
        category="Uncategorized",
        tags=["test"],
    )
    runtime = SimpleNamespace(
        model_name="all-MiniLM-L6-v2",
        retriever=SimpleNamespace(client=target_client),
        memories={"note-1": note},
    )
    method = AMem(
        config=AMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model="all-MiniLM-L6-v2",
            retrieve_k=2,
            max_workers=1,
            profile_name="smoke",
        ),
        runtime_factory=lambda _conversation_id: runtime,
        storage_root=tmp_path,
    )

    method._bind_conversation_scoped_consolidation(
        runtime=runtime,
        conversation_id="target",
        retriever_cls=FakeScopedRetriever,
    )
    runtime.consolidate_memories()

    assert target_client.reset_calls == 1
    assert sibling_client.reset_calls == 0
    assert runtime.retriever.documents == [("note-1", "target memory")]
    assert runtime.retriever.collection_name == "memories"
    assert runtime.retriever.model_name == "all-MiniLM-L6-v2"


def test_amem_production_runtime_receives_openai_compatible_settings(
    monkeypatch,
    tmp_path,
) -> None:
    """生产 runtime 必须把 API key/base URL 和 profile 模型传给官方 A-Mem 类。"""

    created_kwargs: dict[str, object] = {}

    class FakeOfficialRuntime:
        """替代官方 AgenticMemorySystem，避免加载真实 embedding 模型。"""

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
        "import_amem_product_classes",
        lambda path_settings=None: {
            "AgenticMemorySystem": FakeOfficialRuntime,
            "ChromaRetriever": object,
            "PersistentChromaRetriever": object,
            "memory_system_module": SimpleNamespace(ChromaRetriever=object),
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
    assert "api_base" not in created_kwargs
    assert "check_connection" not in created_kwargs


def test_amem_configures_official_openai_client_transport(
    monkeypatch,
    tmp_path,
) -> None:
    """adapter 应给官方 client 注入 endpoint、timeout 与 retry。"""

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
        "import_amem_product_classes",
        lambda path_settings=None: {
            "AgenticMemorySystem": FakeOfficialRuntime,
            "ChromaRetriever": object,
            "PersistentChromaRetriever": object,
            "memory_system_module": SimpleNamespace(ChromaRetriever=object),
        },
    )
    monkeypatch.setattr(
        amem_adapter_module,
        "_create_openai_compatible_client",
            lambda api_key, base_url, timeout, max_retries: created_clients.append(
                {"api_key": api_key, "base_url": base_url, "timeout": timeout, "max_retries": max_retries}
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
        {"api_key": "test-key", "base_url": "https://ohmygpt.example/v1", "timeout": 60.0, "max_retries": 8}
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


def test_amem_prefers_api_usage_when_llm_exposes_usage(tmp_path) -> None:
    """A-Mem LLM 暴露 usage 时，应记录精确 `api_usage` 而不是 tokenizer 估算。"""

    runtime = FakeAMemRuntime()
    llm = FakeAMemLLMWithUsage()
    collector = EfficiencyCollector(run_id="amem-api-usage-run", enabled=True)
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

    llm_records = [
        record.to_dict()
        for record in scope.records
        if record.to_dict()["observation_type"] == "llm_call"
    ]
    assert llm_records
    assert all(
        record["token_measurement_source"] == "api_usage"
        for record in llm_records
    )
    assert all(record["input_tokens"] == 11 for record in llm_records)
    assert all(record["output_tokens"] == 3 for record in llm_records)


def test_amem_records_memory_build_llm_api_usage(tmp_path) -> None:
    """A-Mem add 阶段内部 LLM 调用应记录为 memory_build/api_usage。"""

    build_llm = FakeAMemLLMWithUsage()
    runtime = FakeAMemRuntime(build_llm=build_llm)
    collector = EfficiencyCollector(run_id="amem-build-usage-run", enabled=True)
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
        efficiency_collector=collector,
        storage_root=tmp_path,
    )

    with collector.conversation_scope("conv-1") as scope:
        method.add([_conversation_with_private_gold()])
        collector.record_memory_build_total_latency(latency_ms=1.0)

    llm_records = [
        record.to_dict()
        for record in scope.records
        if record.to_dict()["observation_type"] == "llm_call"
    ]
    assert len(llm_records) == 2
    assert {record["stage"] for record in llm_records} == {"memory_build"}
    assert {record["model_id"] for record in llm_records} == {
        "amem-memory-llm"
    }
    assert all(
        record["token_measurement_source"] == "api_usage"
        for record in llm_records
    )
    assert sum(record["input_tokens"] for record in llm_records) == 22
    assert sum(record["output_tokens"] for record in llm_records) == 6

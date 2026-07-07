"""测试 Mem0 conversation-QA adapter。

本模块使用 fake Mem0 backend 和 fake OpenAI reader，验证官方配置 profile、
vendored 源码身份、逐 turn 写入、conversation namespace 隔离和回复归一化。
测试不会访问网络，也不会修改第三方 Mem0 仓库。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.config.settings import OpenAISettings, load_path_settings
from memory_benchmark.core import Conversation, Question, Session, Turn
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import MemoryProvider
from memory_benchmark.methods.mem0_adapter import (
    Mem0,
    Mem0Config,
    build_mem0_source_identity,
)
from memory_benchmark.methods.registry import MethodBuildContext, _build_mem0_system
from memory_benchmark.observability.efficiency import EfficiencyCollector
from memory_benchmark.runners.prediction import _method_manifest_with_protocol
from tests.equivalence_utils import run_bridge_sequence, run_native_sequence
from tests.fake_corpus import build_multimodal_consecutive_speaker_conversation


pytestmark = pytest.mark.unit


class FakeMemoryBackend:
    """记录 Mem0 add/search 调用的无网络 fake backend。"""

    def __init__(self):
        """初始化调用记录和可配置检索结果。"""

        self.add_calls: list[dict[str, object]] = []
        self.search_calls: list[dict[str, object]] = []
        self.search_results: list[dict[str, object]] = [
            {"id": "m1", "memory": "Alice likes jasmine tea.", "score": 0.91}
        ]

    def add(self, messages, **kwargs):
        """记录单次写入并模拟 Mem0 v1.1 add 返回值。"""

        self.add_calls.append({"messages": messages, **kwargs})
        return {
            "results": [
                {
                    "id": f"m{len(self.add_calls)}",
                    "memory": messages[0]["content"],
                    "event": "ADD",
                }
            ]
        }

    def search(self, query, **kwargs):
        """记录检索参数并返回预设记忆。"""

        self.search_calls.append({"query": query, **kwargs})
        return {"results": list(self.search_results)}


class FakeReaderClient:
    """模拟 OpenAI `chat.completions.create()` 的 reader client。"""

    def __init__(
        self,
        answer: str = "Jasmine tea.",
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
    ):
        """保存固定回答并构造 OpenAI 风格嵌套接口。"""

        self.answer = answer
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.calls: list[dict[str, object]] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )

    def _create(self, **kwargs):
        """记录 reader 调用并返回 OpenAI 风格 completion。"""

        self.calls.append(kwargs)
        usage = None
        if self.prompt_tokens is not None and self.completion_tokens is not None:
            usage = SimpleNamespace(
                prompt_tokens=self.prompt_tokens,
                completion_tokens=self.completion_tokens,
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.answer),
                )
            ],
            usage=usage,
        )


class NamespacedFakeMemoryBackend(FakeMemoryBackend):
    """按 run_id 保存内容的线程安全语义 fake，用于并发隔离测试。"""

    def __init__(self):
        """初始化父类调用记录和 namespace 内容。"""

        super().__init__()
        self.memories_by_run_id: dict[str, list[str]] = {}

    def add(self, messages, **kwargs):
        """把消息保存到对应 run_id，并沿用标准 add 返回结构。"""

        result = super().add(messages, **kwargs)
        run_id = str(kwargs["run_id"])
        self.memories_by_run_id.setdefault(run_id, []).append(
            messages[0]["content"]
        )
        return result

    def search(self, query, **kwargs):
        """只返回 filters 中 run_id 对应的记忆。"""

        self.search_calls.append({"query": query, **kwargs})
        run_id = str(kwargs["filters"]["run_id"])
        return {
            "results": [
                {"memory": memory, "score": 1.0}
                for memory in self.memories_by_run_id.get(run_id, [])
            ]
        }


class EchoMemoryReaderClient(FakeReaderClient):
    """把 system prompt 中收到的检索上下文原样作为回答返回。"""

    def _create(self, **kwargs):
        """记录调用并返回当前 namespace 的 reader 上下文。"""

        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=kwargs["messages"][0]["content"],
                    ),
                )
            ]
        )


class LazyEntityStoreBackend(FakeMemoryBackend):
    """模拟 vendored Mem0 的无锁 entity_store 懒加载属性。"""

    def __init__(self):
        """初始化访问次数和固定 entity store。"""

        super().__init__()
        self.entity_store_access_count = 0
        self._entity_store_value = object()

    @property
    def entity_store(self):
        """记录 adapter 是否在 worker 启动前单线程预热。"""

        self.entity_store_access_count += 1
        return self._entity_store_value


class ObservableMemoryBackend(FakeMemoryBackend):
    """模拟 Mem0 生产 backend 的 LLM callback 与 embedding_model 边界。"""

    def __init__(self):
        """初始化可被 adapter 包装的 llm 和 embedding model。"""

        super().__init__()
        self.llm = SimpleNamespace(
            config=SimpleNamespace(response_callback=None),
        )
        self.embedding_model = ObservableEmbeddingModel()

    def add(self, messages, **kwargs):
        """在 fake add 内触发生产 Mem0 会发生的 LLM 与 embedding 调用。"""

        callback = self.llm.config.response_callback
        if callback is not None:
            callback(
                self.llm,
                _fake_usage_response(prompt_tokens=31, completion_tokens=5),
                {"messages": messages},
            )
        self.embedding_model.embed(messages[0]["content"], memory_action="add")
        return super().add(messages, **kwargs)


class ObservableEmbeddingModel:
    """记录 embed 调用并返回固定向量的 fake embedding model。"""

    def __init__(self):
        """初始化调用记录。"""

        self.calls: list[dict[str, object]] = []

    def embed(self, text: str, memory_action: str | None = None):
        """记录单文本 embedding 调用。"""

        self.calls.append({"text": text, "memory_action": memory_action})
        return [0.1, 0.2, 0.3]

    def embed_batch(self, texts, memory_action="add"):
        """记录批量 embedding 调用。"""

        self.calls.append({"texts": list(texts), "memory_action": memory_action})
        return [[0.1, 0.2, 0.3] for _ in texts]


class OptionTrackingOpenAIClient:
    """记录 OpenAI SDK `with_options()` 调用的 fake client。"""

    def __init__(self):
        """初始化 option 调用记录。"""

        self.option_calls: list[dict[str, object]] = []

    def with_options(self, **kwargs):
        """记录 timeout/retry 参数，并模拟 OpenAI SDK 返回新 client。"""

        self.option_calls.append(kwargs)
        return self


class OpenAIClientBackend(FakeMemoryBackend):
    """模拟 vendored Mem0 中持有 OpenAI client 的 LLM 与 embedding backend。"""

    def __init__(self):
        """初始化可被 adapter 配置的 fake OpenAI clients。"""

        super().__init__()
        self.llm = SimpleNamespace(
            config=SimpleNamespace(response_callback=None),
            client=OptionTrackingOpenAIClient(),
        )
        self.embedding_model = SimpleNamespace(
            client=OptionTrackingOpenAIClient(),
        )


def _snapshot_mem0_backend_calls(system: Mem0) -> list[dict[str, object]]:
    """把 Mem0 backend 调用归一化为可比较序列。"""

    calls: list[dict[str, object]] = []
    backend = system._memory
    for call in backend.add_calls:
        calls.append(
            {
                "op": "add",
                "messages": call["messages"],
                "namespace": "<namespace>",
                "metadata": call["metadata"],
                "infer": call["infer"],
                "prompt": call["prompt"],
                "message_count": len(call["messages"]),
            }
        )
    for call in backend.search_calls:
        calls.append(
            {
                "op": "search",
                "query": call["query"],
                "namespace": "<namespace>",
                "top_k": call["top_k"],
            }
        )
    return calls


def _fake_usage_response(prompt_tokens: int, completion_tokens: int):
    """构造带 OpenAI-compatible usage 的 fake response。"""

    return SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    )


def _build_conversation() -> Conversation:
    """构造包含两个 session、三个 turn 的公开 conversation。"""

    return Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="s1",
                session_time="2023-05-08T13:56:00",
                turns=[
                    Turn(
                        turn_id="t1",
                        speaker="Alice",
                        content="I like jasmine tea.",
                        turn_time="2023-05-08T13:56:01",
                    ),
                    Turn(
                        turn_id="t2",
                        speaker="Bob",
                        content="I will remember that.",
                    ),
                ],
            ),
            Session(
                session_id="s2",
                session_time="2023-05-10T10:00:00",
                turns=[
                    Turn(
                        turn_id="t3",
                        speaker="Alice",
                        content="Tea helps me relax.",
                    )
                ],
            ),
        ],
    )


def _build_named_conversation(
    conversation_id: str,
    speaker: str,
    content: str,
) -> Conversation:
    """构造一个单 turn conversation，便于观察 namespace 是否串写。"""

    return Conversation(
        conversation_id=conversation_id,
        sessions=[
            Session(
                session_id="s1",
                session_time="2023-05-08",
                turns=[
                    Turn(
                        turn_id=f"{conversation_id}:t1",
                        speaker=speaker,
                        content=content,
                    )
                ],
            )
        ],
    )


def _build_longmemeval_conversation() -> Conversation:
    """构造 LongMemEval 风格 conversation，用于验证官方 pair 级写入。"""

    return Conversation(
        conversation_id="lme-q1",
        sessions=[
            Session(
                session_id="haystack-1",
                session_time="2024-01-01",
                turns=[
                    Turn(
                        turn_id="haystack-1:t0",
                        speaker="user",
                        normalized_role="user",
                        content="I prefer jasmine tea in the morning.",
                    ),
                    Turn(
                        turn_id="haystack-1:t1",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="I will keep that preference in mind.",
                    ),
                    Turn(
                        turn_id="haystack-1:t2",
                        speaker="user",
                        normalized_role="user",
                        content="I dislike coffee after lunch.",
                    ),
                    Turn(
                        turn_id="haystack-1:t3",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="Noted, no coffee after lunch.",
                    ),
                ],
            ),
            Session(
                session_id="haystack-2",
                session_time="2024-01-03",
                turns=[
                    Turn(
                        turn_id="haystack-2:t0",
                        speaker="user",
                        normalized_role="user",
                        content="Mint tea is acceptable at night.",
                    )
                ],
            ),
        ],
        metadata={
            "source_path": "data/longmemeval/longmemeval_s_cleaned.json",
            "variant": "s_cleaned",
        },
    )


def test_mem0_profiles_separate_smoke_and_official_full_parameters() -> None:
    """smoke 只降低运行范围参数，全量 profile 必须锁定官方 benchmark 参数。"""

    smoke = Mem0Config.smoke()
    full = Mem0Config.official_full()

    assert smoke.extraction_model == "gpt-4o-mini"
    assert smoke.embedding_model == "text-embedding-3-small"
    assert smoke.embedding_dimensions == 1536
    assert smoke.top_k == 200
    assert smoke.max_workers == 1
    assert smoke.ingestion_chunk_size == 1
    assert smoke.infer is True
    assert smoke.api_timeout_seconds == 60.0
    assert smoke.api_max_retries == 8

    assert full.extraction_model == "gpt-4o-mini"
    assert full.embedding_model == "text-embedding-3-small"
    assert full.embedding_dimensions == 1536
    assert full.top_k == 200
    assert full.max_workers == 10
    assert full.ingestion_chunk_size == 1
    assert full.infer is True
    assert full.api_timeout_seconds == 60.0
    assert full.api_max_retries == 8


def test_mem0_config_rejects_invalid_api_retry_settings() -> None:
    """Mem0 API timeout/retry 配置必须强校验，避免长实验无兜底运行。"""

    with pytest.raises(ConfigurationError, match="api_timeout_seconds"):
        Mem0Config(
            extraction_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            reader_model="gpt-4o-mini",
            top_k=200,
            max_workers=1,
            api_timeout_seconds=0,
        )

    with pytest.raises(ConfigurationError, match="api_max_retries"):
        Mem0Config(
            extraction_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            reader_model="gpt-4o-mini",
            top_k=200,
            max_workers=1,
            api_max_retries=-1,
        )


def test_mem0_source_identity_records_version_and_deterministic_core_hash() -> None:
    """源码身份应固定 Mem0 核心源码，不能把嵌套 benchmark 仓库算进去。"""

    path_settings = load_path_settings()
    first = build_mem0_source_identity(path_settings)
    second = build_mem0_source_identity(path_settings)

    assert first == second
    assert first["package_version"] == "2.0.4"
    assert len(first["source_sha256"]) == 64
    assert first["file_count"] > 1
    allowed_memory_benchmark_files = {
        "memory-benchmarks/benchmarks/locomo/prompts.py",
        "memory-benchmarks/benchmarks/longmemeval/prompts.py",
    }
    assert all(
        path.startswith(("mem0/", "pyproject.toml", "LICENSE"))
        or path in allowed_memory_benchmark_files
        for path in first["files"]
    )
    assert allowed_memory_benchmark_files.issubset(set(first["files"]))
    assert not any(
        path.startswith("memory-benchmarks/") and path not in allowed_memory_benchmark_files
        for path in first["files"]
    )
    assert not any("__pycache__" in path for path in first["files"])


def test_add_writes_each_turn_separately_with_conversation_namespace() -> None:
    """每个 turn 应独立调用官方 Mem0 add，并统一使用 conversation id 隔离。"""

    backend = FakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
    )

    result = system.add([_build_conversation()])

    assert result.conversation_ids == ["conv-1"]
    assert len(backend.add_calls) == 3
    assert all(call["run_id"] == "conv-1" for call in backend.add_calls)
    assert all(call["infer"] is True for call in backend.add_calls)
    assert backend.add_calls[0]["prompt"] == (
        "The observation date and time for this message is "
        "'2023-05-08T13:56:00'. Resolve relative time expressions such as "
        "'yesterday', 'today', and 'last week' only against this observation "
        "time, even if another current or observation date appears elsewhere "
        "in the extraction prompt."
    )
    assert backend.add_calls[1]["prompt"] == backend.add_calls[0]["prompt"]
    assert backend.add_calls[2]["prompt"] == (
        "The observation date and time for this message is "
        "'2023-05-10T10:00:00'. Resolve relative time expressions such as "
        "'yesterday', 'today', and 'last week' only against this observation "
        "time, even if another current or observation date appears elsewhere "
        "in the extraction prompt."
    )
    assert backend.add_calls[0]["messages"] == [
        {
            "role": "user",
            "content": (
                "[Session time: 2023-05-08T13:56:00] "
                "[Turn time: 2023-05-08T13:56:01] "
                "Alice: I like jasmine tea."
            ),
        }
    ]
    assert backend.add_calls[1]["messages"] == [
        {
            "role": "assistant",
            "content": (
                "[Session time: 2023-05-08T13:56:00] "
                "Bob: I will remember that."
            ),
        }
    ]
    assert backend.add_calls[2]["messages"] == [
        {
            "role": "user",
            "content": (
                "[Session time: 2023-05-10T10:00:00] "
                "Alice: Tea helps me relax."
            ),
        }
    ]
    first_metadata = backend.add_calls[0]["metadata"]
    assert first_metadata["conversation_id"] == "conv-1"
    assert first_metadata["session_id"] == "s1"
    assert first_metadata["turn_id"] == "t1"
    assert first_metadata["speaker"] == "Alice"
    assert first_metadata["session_time"] == "2023-05-08T13:56:00"
    assert first_metadata["turn_time"] == "2023-05-08T13:56:01"


def test_add_batches_longmemeval_turns_as_user_assistant_pairs() -> None:
    """LongMemEval 应按官方 `CHUNK_SIZE=2` 把 user+assistant pair 写入 Mem0。"""

    backend = FakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
    )
    conversation = _build_longmemeval_conversation()

    result = system.add([conversation])

    assert result.conversation_ids == ["lme-q1"]
    assert result.metadata["turn_count"] == 5
    assert [len(call["messages"]) for call in backend.add_calls] == [2, 2, 1]
    assert backend.add_calls[0]["messages"] == [
        {
            "role": "user",
            "content": (
                "[Session time: 2024-01-01] "
                "user: I prefer jasmine tea in the morning."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "[Session time: 2024-01-01] "
                "assistant: I will keep that preference in mind."
            ),
        },
    ]
    assert backend.add_calls[2]["messages"] == [
        {
            "role": "user",
            "content": (
                "[Session time: 2024-01-03] "
                "user: Mint tea is acceptable at night."
            ),
        }
    ]
    assert backend.add_calls[0]["metadata"] == {
        "conversation_id": "lme-q1",
        "session_id": "haystack-1",
        "turn_ids": ["haystack-1:t0", "haystack-1:t1"],
        "first_turn_id": "haystack-1:t0",
        "last_turn_id": "haystack-1:t1",
        "speaker": "user+assistant",
        "session_time": "2024-01-01",
    }
    assert all(call["run_id"] == "lme-q1" for call in backend.add_calls)


def test_native_mem0_locomo_matches_bridge_add_and_search_sequence() -> None:
    """Mem0 原生 turn 路径应与桥接路径发出等价 add/search 序列。"""

    conversation = build_multimodal_consecutive_speaker_conversation()
    question = conversation.questions[0]
    bridge = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
    )
    native = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
    )

    bridge_result = run_bridge_sequence(
        provider=bridge,
        conversation=conversation,
        question=question,
        run_id="mem0-equivalence",
        snapshot_calls=_snapshot_mem0_backend_calls,
    )
    native_result = run_native_sequence(
        provider=native,
        conversation=conversation,
        question=question,
        run_id="mem0-equivalence",
        snapshot_calls=_snapshot_mem0_backend_calls,
    )

    assert isinstance(native, MemoryProvider)
    assert bridge_result.calls == native_result.calls
    assert native._memory.add_calls[0]["run_id"] == "mem0-equivalence_conv-rich"
    assert native._memory.search_calls[0]["filters"] == {
        "run_id": "mem0-equivalence_conv-rich"
    }


def test_native_mem0_longmemeval_matches_bridge_session_sequence() -> None:
    """Mem0 原生 session 路径应保持 LongMemEval 官方 CHUNK_SIZE=2 批次。"""

    conversation = _build_longmemeval_conversation()
    question = Question(
        question_id="lme-q1",
        conversation_id="lme-q1",
        text="What kind of tea does the user prefer?",
        question_time="2024-01-04",
    )
    bridge = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
    )
    native = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
        consume_granularity="session",
    )

    bridge_result = run_bridge_sequence(
        provider=bridge,
        conversation=conversation,
        question=question,
        run_id="mem0-equivalence",
        snapshot_calls=_snapshot_mem0_backend_calls,
    )
    native_result = run_native_sequence(
        provider=native,
        conversation=conversation,
        question=question,
        run_id="mem0-equivalence",
        snapshot_calls=_snapshot_mem0_backend_calls,
    )

    assert bridge_result.calls == native_result.calls
    assert [call["message_count"] for call in native_result.calls if call["op"] == "add"] == [
        2,
        2,
        1,
    ]


def test_native_mem0_longmemeval_assistant_first_session_keeps_official_chunks() -> None:
    """assistant 开头 session 必须保持官方位置切块且逐消息 role 不反转。"""

    conversation = Conversation(
        conversation_id="lme-af",
        sessions=[
            Session(
                session_id="haystack-af",
                session_time="2024-01-01",
                turns=[
                    Turn(
                        turn_id=f"haystack-af:t{index}",
                        speaker=role,
                        normalized_role=role,
                        content=f"message {index}",
                    )
                    for index, role in enumerate(
                        ["assistant", "user", "assistant", "user", "assistant"]
                    )
                ],
            )
        ],
        questions=[],
        metadata={"source_path": "data/longmemeval/longmemeval_s_cleaned.json"},
    )
    question = Question(
        question_id="lme-af-q1",
        conversation_id="lme-af",
        text="What did the assistant say first?",
        question_time="2024-01-04",
    )
    bridge = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
    )
    native = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
        consume_granularity="session",
    )

    bridge_result = run_bridge_sequence(
        provider=bridge,
        conversation=conversation,
        question=question,
        run_id="mem0-equivalence",
        snapshot_calls=_snapshot_mem0_backend_calls,
    )
    native_result = run_native_sequence(
        provider=native,
        conversation=conversation,
        question=question,
        run_id="mem0-equivalence",
        snapshot_calls=_snapshot_mem0_backend_calls,
    )

    assert bridge_result.calls == native_result.calls
    add_calls = [call for call in native_result.calls if call["op"] == "add"]
    assert [call["message_count"] for call in add_calls] == [2, 2, 1]
    assert [message["role"] for message in add_calls[0]["messages"]] == [
        "assistant",
        "user",
    ]


def test_mem0_registry_specializes_consume_granularity_by_benchmark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """registry 应按 benchmark profile 设置 Mem0 实例级消费粒度。"""

    monkeypatch.setattr(
        Mem0,
        "_create_memory_backend",
        lambda self, openai_settings: FakeMemoryBackend(),
    )
    monkeypatch.setattr(
        Mem0,
        "_prewarm_entity_store",
        lambda self, memory_backend: None,
    )

    locomo = _build_mem0_system(
        MethodBuildContext(
            config=Mem0Config.smoke(),
            openai_settings=OpenAISettings(api_key="sk-test"),
            path_settings=load_path_settings(),
            storage_root=tmp_path / "locomo",
            benchmark_name="locomo",
        )
    )
    longmemeval = _build_mem0_system(
        MethodBuildContext(
            config=Mem0Config.smoke(),
            openai_settings=OpenAISettings(api_key="sk-test"),
            path_settings=load_path_settings(),
            storage_root=tmp_path / "longmemeval",
            benchmark_name="longmemeval",
        )
    )

    assert isinstance(locomo, MemoryProvider)
    assert locomo.consume_granularity == "turn"
    assert isinstance(longmemeval, MemoryProvider)
    assert longmemeval.consume_granularity == "session"
    assert _method_manifest_with_protocol(
        method_manifest={},
        system=locomo,
    )["protocol_version"] == "v3"


def test_mem0_turn_level_resume_is_disabled_for_all_benchmarks() -> None:
    """Mem0 统一使用 conversation-level resume，不再启用 runner turn checkpoint。"""

    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
    )

    assert system.supports_turn_resume(_build_conversation()) is False
    assert system.supports_turn_resume(_build_longmemeval_conversation()) is False


def test_add_from_turn_skips_confirmed_prefix_and_reports_callback_order() -> None:
    """增量写入应跳过已确认 turn，并严格包围实际 backend 调用。"""

    events: list[str] = []

    class OrderedBackend(FakeMemoryBackend):
        """在 add 时记录调用顺序的 fake backend。"""

        def add(self, messages, **kwargs):
            """记录 backend 事件后执行父类逻辑。"""

            events.append(f"backend:{kwargs['metadata']['turn_id']}")
            return super().add(messages, **kwargs)

    backend = OrderedBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
    )

    result = system.add_from_turn(
        conversation=_build_conversation(),
        start_turn_index=2,
        on_turn_started=lambda index, turn: events.append(
            f"started:{index}:{turn.turn_id}"
        ),
        on_turn_completed=lambda index, turn: events.append(
            f"completed:{index}:{turn.turn_id}"
        ),
    )

    assert result.conversation_ids == ["conv-1"]
    assert [call["metadata"]["turn_id"] for call in backend.add_calls] == ["t3"]
    assert events == [
        "started:2:t3",
        "backend:t3",
        "completed:2:t3",
    ]


def test_get_answer_searches_only_question_conversation_and_calls_reader() -> None:
    """回答问题时只能检索对应 conversation，并把检索记忆交给 reader。"""

    backend = FakeMemoryBackend()
    reader = FakeReaderClient(answer="She likes jasmine tea.")
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=reader,
    )
    system.add([_build_conversation()])
    question = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="What kind of tea does Alice like?",
    )

    prediction = system.get_answer(question)

    assert backend.search_calls == [
        {
            "query": question.text,
            "filters": {"run_id": "conv-1"},
            "top_k": 200,
        }
    ]
    assert prediction.question_id == "conv-1:q1"
    assert prediction.conversation_id == "conv-1"
    assert prediction.answer == "She likes jasmine tea."
    assert prediction.metadata == {
        "method": "mem0",
        "retrieved_memory_count": 1,
        "top_k": 200,
        "reader_model": "gpt-4o-mini",
    }
    reader_messages = reader.calls[0]["messages"]
    assert len(reader_messages) == 1
    assert "Alice likes jasmine tea." in reader_messages[0]["content"]
    assert question.text in reader_messages[0]["content"]


def test_mem0_retrieve_returns_answer_prompt() -> None:
    """retrieve 只检索当前 conversation，并返回完整 answer prompt。"""

    backend = FakeMemoryBackend()
    reader = FakeReaderClient()
    config = Mem0Config.smoke()
    system = Mem0(
        config=config,
        memory_backend=backend,
        reader_client=reader,
    )
    system.add([_build_conversation()])
    question = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="What kind of tea does Alice like?",
    )

    retrieval = system.retrieve(question)

    assert backend.search_calls == [
        {
            "query": question.text,
            "filters": {"run_id": "conv-1"},
            "top_k": config.top_k,
        }
    ]
    assert reader.calls == []
    assert retrieval.question_id == question.question_id
    assert retrieval.conversation_id == question.conversation_id
    assert [message.role for message in retrieval.prompt_messages] == [
        "system",
        "user",
    ]
    assert "Alice likes jasmine tea." in retrieval.answer_prompt
    assert question.text in retrieval.answer_prompt
    assert retrieval.metadata["answer_context"] == "- Alice likes jasmine tea."
    assert retrieval.metadata["retrieved_memories"] == [
        {
            "content": "Alice likes jasmine tea.",
            "score": 0.91,
            "created_at": None,
        }
    ]
    assert retrieval.metadata["method"] == "mem0"
    assert retrieval.metadata["top_k"] == config.top_k
    assert retrieval.metadata["answer_prompt_profile"] == "generic"


def test_get_answer_uses_mem0_locomo_official_answer_prompt() -> None:
    """LoCoMo 问题应使用 Mem0 memory-benchmarks 的官方 answer prompt。"""

    backend = FakeMemoryBackend()
    backend.search_results = [
        {
            "id": "m1",
            "memory": "Alice likes jasmine tea.",
            "score": 0.91,
            "created_at": "2023-05-08T13:56:00",
        }
    ]
    reader = FakeReaderClient(answer="ANSWER: jasmine tea")
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=reader,
    )
    conversation = _build_conversation()
    conversation.metadata["source_path"] = "data/locomo/locomo10.json"
    system.add([conversation])
    question = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="What kind of tea does Alice like?",
    )

    system.get_answer(question)

    reader_messages = reader.calls[0]["messages"]
    assert len(reader_messages) == 1
    prompt = reader_messages[0]["content"]
    assert "You are answering a question using retrieved memories" in prompt
    assert "## Step 1: SCAN ALL MEMORIES" in prompt
    assert "These conversations took place around 2023-05-10T10:00:00" in prompt
    assert "(Monday, May 08, 2023) Alice likes jasmine tea." in prompt
    assert "Question: What kind of tea does Alice like?" in prompt


def test_get_answer_uses_mem0_longmemeval_official_answer_prompt() -> None:
    """LongMemEval 问题应使用 Mem0 memory-benchmarks 的官方 answer prompt。"""

    backend = FakeMemoryBackend()
    backend.search_results = [
        {
            "id": "m1",
            "memory": "Alice likes jasmine tea.",
            "score": 0.91,
            "created_at": "2023-05-08T13:56:00",
        }
    ]
    reader = FakeReaderClient(answer="jasmine tea")
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=reader,
    )
    system.add([_build_longmemeval_conversation()])
    question = Question(
        question_id="lme-q1",
        conversation_id="lme-q1",
        text="What kind of tea does the user prefer?",
        question_time="2024-01-04",
    )

    system.get_answer(question)

    reader_messages = reader.calls[0]["messages"]
    assert len(reader_messages) == 1
    prompt = reader_messages[0]["content"]
    assert "You are a personal assistant with access to memories" in prompt
    assert "IMPORTANT: Today's date is 2024-01-04." in prompt
    assert "--- Monday, May 08, 2023 ---" in prompt
    assert "- Alice likes jasmine tea." in prompt
    assert "Question: What kind of tea does the user prefer?" in prompt


def test_get_answer_records_efficiency_observations_when_collector_enabled() -> None:
    """开启 collector 时 Mem0 应记录 retrieval、memory context token 和 reader LLM。"""

    backend = FakeMemoryBackend()
    reader = FakeReaderClient(
        answer="She likes jasmine tea.",
        prompt_tokens=123,
        completion_tokens=7,
    )
    collector = EfficiencyCollector(run_id="mem0-eff-run", enabled=True)
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=reader,
        efficiency_collector=collector,
    )
    system.add([_build_conversation()])
    question = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="What kind of tea does Alice like?",
    )

    with collector.question_scope("conv-1", "conv-1:q1") as scope:
        system.get_answer(question)

    records = [record.to_dict() for record in scope.records]
    reader_calls = [
        record
        for record in records
        if record["observation_type"] == "llm_call"
        and record["model_id"] == "mem0-answer-llm"
    ]
    question_records = [
        record
        for record in records
        if record["observation_type"] == "question_efficiency"
    ]
    assert len(reader_calls) == 1
    assert reader_calls[0]["stage"] == "answer"
    assert reader_calls[0]["input_tokens"] == 123
    assert reader_calls[0]["output_tokens"] == 7
    assert reader_calls[0]["token_measurement_source"] == "api_usage"
    assert reader_calls[0]["conversation_id"] == "conv-1"
    assert reader_calls[0]["question_id"] == "conv-1:q1"
    assert len(question_records) == 1
    assert question_records[0]["retrieval_latency_ms"] >= 0
    assert question_records[0]["unsupported_reason"] is None
    assert question_records[0]["injected_memory_context_tokens"] > 0
    assert question_records[0]["answer_generation_latency_ms"] >= 0


def test_mem0_records_build_llm_and_embedding_observations_when_available() -> None:
    """Mem0 wrapper 应观测官方 backend 的 extraction LLM 和 embedding 调用。"""

    backend = ObservableMemoryBackend()
    collector = EfficiencyCollector(run_id="mem0-build-run", enabled=True)
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        efficiency_collector=collector,
    )

    with collector.conversation_scope("conv-1") as scope:
        system.add([_build_named_conversation("conv-1", "Alice", "ALPHA")])
        collector.record_memory_build_total_latency(latency_ms=1.0)

    records = [record.to_dict() for record in scope.records]
    assert any(
        record["observation_type"] == "llm_call"
        and record["stage"] == "memory_build"
        and record["model_id"] == "mem0-memory-llm"
        and record["input_tokens"] == 31
        and record["output_tokens"] == 5
        for record in records
    )
    assert any(
        record["observation_type"] == "embedding_call"
        and record["stage"] == "memory_build"
        and record["model_id"] == "mem0-embedding"
        and record["input_tokens"] > 0
        and record["latency_ms"] >= 0
        for record in records
    )


def test_get_answer_rejects_question_for_unadded_conversation() -> None:
    """未写入 conversation 的问题必须立即报错，不能跨 namespace 猜测回答。"""

    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
    )

    with pytest.raises(ConfigurationError, match="not added"):
        system.get_answer(
            Question(
                question_id="missing:q1",
                conversation_id="missing",
                text="What happened?",
            )
        )


def test_existing_conversation_ids_allow_resume_without_reingestion() -> None:
    """resume 可附着已持久化 namespace，避免重复调用 Mem0 add。"""

    backend = FakeMemoryBackend()
    reader = FakeReaderClient()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=reader,
        existing_conversation_ids={"conv-1"},
    )

    prediction = system.get_answer(
        Question(
            question_id="conv-1:q1",
            conversation_id="conv-1",
            text="What tea does Alice like?",
        )
    )

    assert backend.add_calls == []
    assert backend.search_calls[0]["filters"] == {"run_id": "conv-1"}
    assert prediction.answer == "Jasmine tea."


def test_add_rejects_duplicate_conversation_namespace() -> None:
    """重复写入同一 conversation 会污染断点语义，因此必须显式拒绝。"""

    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
    )
    conversation = _build_conversation()
    system.add([conversation])

    with pytest.raises(ConfigurationError, match="already added"):
        system.add([conversation])


def test_shared_mem0_instance_keeps_two_concurrent_conversations_isolated() -> None:
    """共享 Mem0 实例并发 add/search 时必须始终按 conversation id 隔离。"""

    backend = NamespacedFakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=EchoMemoryReaderClient(),
    )
    conversations = [
        _build_named_conversation("conv-a", "Alice", "ALPHA_ONLY"),
        _build_named_conversation("conv-b", "Bob", "BETA_ONLY"),
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda item: system.add([item]), conversations))

    questions = [
        Question("conv-a:q1", "conv-a", "What is remembered?"),
        Question("conv-b:q1", "conv-b", "What is remembered?"),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        answers = list(executor.map(system.get_answer, questions))

    assert "ALPHA_ONLY" in answers[0].answer
    assert "BETA_ONLY" not in answers[0].answer
    assert "BETA_ONLY" in answers[1].answer
    assert "ALPHA_ONLY" not in answers[1].answer
    assert {
        call["filters"]["run_id"] for call in backend.search_calls
    } == {"conv-a", "conv-b"}


def test_production_backend_prewarms_lazy_entity_store_before_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """生产 backend 应在构造阶段预热 entity store，消除首次并发访问竞态。"""

    backend = LazyEntityStoreBackend()
    monkeypatch.setattr(
        Mem0,
        "_create_memory_backend",
        lambda self, openai_settings: backend,
    )

    Mem0(
        config=Mem0Config.smoke(),
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.test/v1",
        ),
        storage_root=tmp_path,
        reader_client=FakeReaderClient(),
    )

    assert backend.entity_store_access_count == 1


def test_production_config_injects_openai_and_local_storage_without_secrets_in_manifest(
    tmp_path: Path,
) -> None:
    """生产配置应同时注入 extraction/embedder，并只公开脱敏参数摘要。"""

    settings = OpenAISettings(
        api_key="secret-test-key",
        base_url="https://example.invalid/v1",
        model="gpt-4o-mini",
    )
    config = Mem0Config.official_full()

    backend_config = Mem0.build_backend_config(
        config=config,
        openai_settings=settings,
        storage_root=tmp_path,
    )
    manifest = config.to_manifest()

    assert backend_config["llm"]["config"]["api_key"] == "secret-test-key"
    assert backend_config["llm"]["config"]["openai_base_url"] == settings.base_url
    assert backend_config["embedder"]["config"]["api_key"] == "secret-test-key"
    assert backend_config["embedder"]["config"]["openai_base_url"] == settings.base_url
    assert backend_config["vector_store"]["config"]["embedding_model_dims"] == 1536
    assert backend_config["vector_store"]["config"]["path"] == str(tmp_path / "qdrant")
    assert backend_config["history_db_path"] == str(tmp_path / "history.db")
    assert "secret-test-key" not in str(manifest)
    assert "api_key" not in str(manifest)


def test_mem0_configures_vendored_openai_clients_with_timeout_and_retries() -> None:
    """adapter 应给 vendored LLM/embedding OpenAI client 注入 timeout 和 retry。"""

    backend = OpenAIClientBackend()
    config = Mem0Config(
        extraction_model="gpt-4o-mini",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536,
        reader_model="gpt-4o-mini",
        top_k=200,
        max_workers=1,
        api_timeout_seconds=12.5,
        api_max_retries=6,
    )

    Mem0(
        config=config,
        memory_backend=backend,
        reader_client=FakeReaderClient(),
    )

    assert backend.llm.client.option_calls == [
        {"timeout": 12.5, "max_retries": 6}
    ]
    assert backend.embedding_model.client.option_calls == [
        {"timeout": 12.5, "max_retries": 6}
    ]

"""测试 Mem0 conversation-QA adapter。

本模块使用 fake Mem0 backend 和 fake OpenAI reader，验证官方配置 profile、
vendored 源码身份、逐 turn 写入、conversation namespace 隔离和回复归一化。
测试不会访问网络，也不会修改第三方 Mem0 仓库。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import pytest

import memory_benchmark.methods.registry as method_registry
from memory_benchmark.config.settings import OpenAISettings, load_path_settings
from memory_benchmark.core import Conversation, ImageRef, Question, Session, Turn
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    MemoryProvider,
    RetrievalQuery,
    SessionBatch,
    SessionRef,
    TurnPair,
)
from memory_benchmark.methods.mem0_adapter import (
    Mem0,
    Mem0Config,
    _load_mem0_benchmark_prompt_module,
    build_mem0_source_identity,
)
from memory_benchmark.methods.registry import (
    MethodBuildContext,
    _build_mem0_system,
    get_method_registration,
)
from memory_benchmark.observability.efficiency import EfficiencyCollector
from memory_benchmark.runners.event_stream import (
    GranularityAggregator,
    build_turn_events,
)
from memory_benchmark.runners.prediction import (
    _method_manifest_with_protocol,
    _validate_run_manifest_state,
)
from memory_benchmark.storage import ExperimentPaths, atomic_write_json
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


class FakeRecentMessageStore:
    """按 Mem0 session_scope 保存和清理 recent messages。"""

    def __init__(self) -> None:
        """初始化空的 scope 映射和删除记录。"""

        self.messages: dict[str, list[dict[str, str]]] = {}
        self.deleted_scopes: list[str] = []

    def delete_messages(self, session_scope: str) -> None:
        """删除一个 scope，并记录 adapter 使用的精确 scope。"""

        self.deleted_scopes.append(session_scope)
        self.messages.pop(session_scope, None)


class CleanableFakeMemoryBackend(FakeMemoryBackend):
    """模拟 recent-message 污染、namespace 删除和再次提取。"""

    def __init__(self) -> None:
        """初始化 recent-message store、删除记录和提取上下文。"""

        super().__init__()
        self.db = FakeRecentMessageStore()
        self.deleted_run_ids: list[str] = []
        self.extraction_contexts: list[list[str]] = []

    def add(self, messages, **kwargs):
        """记录 add 前可见的历史消息，再保存本批消息。"""

        scope = f"run_id={kwargs['run_id']}"
        self.extraction_contexts.append(
            [item["content"] for item in self.db.messages.get(scope, [])]
        )
        self.db.messages.setdefault(scope, []).extend(messages)
        return super().add(messages, **kwargs)

    def delete_all(self, *, run_id: str):
        """记录按 run_id 清理向量的生产调用形态。"""

        self.deleted_run_ids.append(run_id)
        return {"message": "Memories deleted successfully!"}


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
    assert smoke.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert smoke.embedding_dimensions == 384
    assert smoke.embedding_provider == "huggingface"
    assert smoke.top_k == 20
    assert smoke.max_workers == 1
    assert smoke.ingestion_chunk_size == 1
    assert smoke.infer is True
    assert smoke.api_timeout_seconds == 60.0
    assert smoke.api_max_retries == 8

    assert full.extraction_model == "gpt-4o-mini"
    assert full.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert full.embedding_dimensions == 384
    assert full.embedding_provider == "huggingface"
    assert full.top_k == 20
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
    """LongMemEval 应按官方 `CHUNK_SIZE=2` 把 user+assistant pair 写入 Mem0。

    turn 已带结构化 `normalized_role`，content 不再前置 `user:`/`assistant:`——
    否则 Mem0 `parse_messages()` 会在已经是 role 字段的文本上再看到一遍
    `user: user: ...`，这正是五格输入保真修复要去掉的重复渲染。
    """

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
                "I prefer jasmine tea in the morning."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "[Session time: 2024-01-01] "
                "I will keep that preference in mind."
            ),
        },
    ]
    assert backend.add_calls[2]["messages"] == [
        {
            "role": "user",
            "content": (
                "[Session time: 2024-01-03] "
                "Mint tea is acceptable at night."
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


# ---- MemBench source-time 单次渲染（Phase C）强反例 ---------------------------------
# 这些测试只覆盖 Mem0 content-only renderer 契约本身（任意 content + marker 组合都
# 不得重复前置 [Turn time]），不调真实 API。自 MemBench canonical split
# （branches/input-role-semantics/cards/actor-prompt-membench-canonical-split.md）
# 起，真实 MemBench adapter 已不再把 user/agent 拼成一行——下面这条 composite 字面量
# 只是一个合成的单-turn renderer 边界样本，不代表当前 `membench.py` 的真实输出；真实
# 拆分后 turn 结构由 `tests/test_membench_conversation_adapter.py` 独立验证。两条路径
# （legacy add 与 v3 ingest）仍必须对同一 content 产出字节完全一致的 message，证明
# marker 在事件层往返后未丢失。
_MEMBENCH_TURN_CONTENT = (
    "'user': I watched it. (place: Boston, MA; time: '2024-10-01 08:00' Monday); "
    "'agent': Noted. (place: Boston, MA; time: '2024-10-01 08:00' Monday)"
)
_MEMBENCH_TURN_TIME = "2024-10-01 08:00"


def _build_membench_turn_conversation() -> Conversation:
    """构造单-turn synthetic conversation：turn_time 与 content 内嵌时间一致，marker=True。

    content 字面量沿用 canonical split 前的拼接形态，仅用于覆盖 Mem0 content-only
    renderer 的边界行为（不代表 split 后真实 MemBench adapter 的输出结构）。
    """

    return Conversation(
        conversation_id="membench-c1",
        sessions=[
            Session(
                session_id="s1",
                session_time=None,
                turns=[
                    Turn(
                        turn_id="t1",
                        speaker="user",
                        normalized_role="user",
                        content=_MEMBENCH_TURN_CONTENT,
                        turn_time=_MEMBENCH_TURN_TIME,
                        metadata={"source_timestamp_embedded_in_content": True},
                    )
                ],
            )
        ],
    )


def test_mem0_legacy_add_skips_duplicate_turn_time_when_content_has_marker() -> None:
    """legacy add 路径：MemBench 原文已带 time 时 Mem0 message 不再前置 [Turn time]。

    first-person dict step 把 user/agent 拼成一行，时间字面值 `2024-10-01 08:00`
    在原 content 内出现 2 次（user 段、agent 段各 1 次）。renderer marker 触发跳过
    `[Turn time]` 前缀，故最终 message 中该时间字面值仍只出现 2 次（来自原文），
    不含 `[Turn time:` 前缀；place 子串（`Boston, MA`）仍保留。turn 的
    `normalized_role="user"` 有效，五格输入保真修复后 content 不再额外前置
    `user:`——原文本身就以 `'user':` 开头，不是 renderer 加的。
    """

    backend = FakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
    )

    result = system.add([_build_membench_turn_conversation()])

    assert result.conversation_ids == ["membench-c1"]
    assert len(backend.add_calls) == 1
    message_content = backend.add_calls[0]["messages"][0]["content"]
    # 单一渲染：marker 触发跳过 [Turn time]；session_time 也不会越权前置
    assert "[Turn time:" not in message_content
    assert "[Session time:" not in message_content
    # 原文时间字面值只来自 content（first-person dict 拼接后 user+agent 各 1 次）
    # 关键断言：renderer 没有再前置一遍，否则会出现 3 次
    assert message_content.count("2024-10-01 08:00") == 2
    assert "place: Boston, MA" in message_content
    # role-native content 不再前置 adapter 自己的 "user: "；原文只保留它本来的
    # "'user': " 字面值一次
    assert message_content.startswith("'user': I watched it.")
    assert message_content == _MEMBENCH_TURN_CONTENT


def test_mem0_v3_ingest_dedups_marker_after_event_stream() -> None:
    """v3 build_turn_events -> Mem0.ingest 路径同样去重，证明 marker 在事件层未丢失。

    喂一条 MemBench 风格 conversation 走 v3 provider 的 `ingest(SessionBatch)`，
    断言最终 `_memory.add()` 收到的 message 与 legacy add 完全一致。`_turn_from_event`
    重建 Turn 时必须保留 `turn.metadata["source_timestamp_embedded_in_content"]`，
    否则 renderer 会回退到 `[Turn time:]` 重复前缀。
    """

    backend = FakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        consume_granularity="session",
    )
    conversation = _build_membench_turn_conversation()
    events = tuple(
        build_turn_events(conversation, isolation_key="v3_run_membench-c1")
    )
    batch = SessionBatch(
        isolation_key="v3_run_membench-c1",
        session_id="s1",
        events=events,
        session_time=None,
    )

    system.ingest(batch)

    assert len(backend.add_calls) == 1
    v3_message_content = backend.add_calls[0]["messages"][0]["content"]
    assert "[Turn time:" not in v3_message_content
    assert "[Session time:" not in v3_message_content
    # 原文时间字面值在 content 中出现 2 次（first-person dict 拼接 user+agent），
    # renderer 没再前置一遍，所以仍是 2 次（legacy 路径同数）
    assert v3_message_content.count("2024-10-01 08:00") == 2
    assert "place: Boston, MA" in v3_message_content
    # 事件层 metadata 也必须透传 marker；防止事件流重建 Turn 时丢键
    rebuilt_turn = Mem0._turn_from_event(events[0])
    assert rebuilt_turn.metadata.get("source_timestamp_embedded_in_content") is True


def test_mem0_renderer_falls_back_to_turn_when_both_turn_and_session_set() -> None:
    """非 MemBench turn 同时有 typed turn_time 和 session_time：只一个 [Turn time]。

    覆盖 BEAM/HaluMem 形态（BEAM turn 自带时间、session 也有时间；HaluMem 整 session
    batch）。legacy add 走 `add_from_turn`，v3 路径走 `ingest(SessionBatch)`，两条
    路径必须产出一致结果。session time 永远不与 turn time 共存于同一 message。
    """

    backend_legacy = FakeMemoryBackend()
    legacy_system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend_legacy,
        reader_client=FakeReaderClient(),
    )
    legacy_conversation = _build_conversation()  # t1 同时有 turn_time + session_time
    legacy_system.add([legacy_conversation])
    legacy_first_message = backend_legacy.add_calls[0]["messages"][0]["content"]
    assert "[Turn time: 2023-05-08T13:56:01]" in legacy_first_message
    assert "[Session time:" not in legacy_first_message

    backend_v3 = FakeMemoryBackend()
    v3_system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend_v3,
        reader_client=FakeReaderClient(),
        consume_granularity="session",
    )
    v3_events = tuple(
        build_turn_events(_build_conversation(), isolation_key="v3_run_conv-1")
    )
    v3_batch = SessionBatch(
        isolation_key="v3_run_conv-1",
        session_id="s1",
        events=v3_events[:1],
        session_time="2023-05-08T13:56:00",
    )
    v3_system.ingest(v3_batch)
    v3_first_message = backend_v3.add_calls[0]["messages"][0]["content"]
    assert v3_first_message == legacy_first_message
    assert "[Session time:" not in v3_first_message


def test_mem0_renderer_session_only_and_no_time_byte_stable() -> None:
    """turn_time 缺失、session_time 有值时 `[Session time]` 字节级保持现状；两者都缺无 header。

    LoCoMo/LongMemEval session-only 形态（t2/t3 of `_build_conversation`）必须继续
    出现 `[Session time: 2023-05-08T13:56:00] Bob: ...`；新增第三条全空 turn 验证
    无 header。同时确认 marker 必须严格为 True 才跳过（字符串 "true" / 1 / 缺键都
    不触发 dedup）。
    """

    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
    )
    conversation = _build_conversation()  # 已有 s1/t1 (turn+session), s1/t2 (session only)

    # 额外加一个全空 turn（turn_time=None, session_time=None）— 抽到独立 session 以
    # 保证不污染既有断言
    conversation.sessions.append(
        Session(
            session_id="s_empty",
            session_time=None,
            turns=[
                Turn(
                    turn_id="t_empty",
                    speaker="Alice",
                    content="No time at all.",
                )
            ],
        )
    )
    backend = system._memory  # type: ignore[attr-defined]
    backend.add_calls.clear()
    system.add([conversation])

    # 现有 session-only 形态字节级保持
    s1_messages = [
        call["messages"][0]["content"]
        for call in backend.add_calls
        if call["metadata"]["session_id"] == "s1" and call["metadata"]["turn_id"] == "t2"
    ]
    assert s1_messages == [
        "[Session time: 2023-05-08T13:56:00] Bob: I will remember that."
    ]

    # 全空 turn 不应有 header
    empty_messages = [
        call["messages"][0]["content"]
        for call in backend.add_calls
        if call["metadata"].get("turn_id") == "t_empty"
    ]
    assert empty_messages == ["Alice: No time at all."]

    # marker 严格 True：字符串 "true" / 1 / 缺键 / None 都不应触发 dedup
    marker_cases: list[tuple[object, str]] = [
        ("true", "[Turn time: 2024-01-01 00:00:00] "),
        (1, "[Turn time: 2024-01-01 00:00:00] "),
        (None, "[Turn time: 2024-01-01 00:00:00] "),
    ]
    base_turn = Turn(
        turn_id="t_marker",
        speaker="Alice",
        content="hello",
        turn_time="2024-01-01 00:00:00",
    )
    for marker_value, expected_prefix in marker_cases:
        probe_turn = Turn(
            turn_id=base_turn.turn_id,
            speaker=base_turn.speaker,
            content=base_turn.content,
            turn_time=base_turn.turn_time,
            metadata={"source_timestamp_embedded_in_content": marker_value},
        )
        probe_message = Mem0._turn_to_message(
            probe_turn,
            speaker_roles={"Alice": "user"},
            session_time="2024-01-02 00:00:00",
        )
        assert probe_message["content"].startswith(expected_prefix), (
            f"marker={marker_value!r} should not dedup, got {probe_message['content']!r}"
        )

    # 反例：marker=True 时确实跳过
    true_turn = Turn(
        turn_id=base_turn.turn_id,
        speaker=base_turn.speaker,
        content=base_turn.content,
        turn_time=base_turn.turn_time,
        metadata={"source_timestamp_embedded_in_content": True},
    )
    true_message = Mem0._turn_to_message(
        true_turn,
        speaker_roles={"Alice": "user"},
        session_time="2024-01-02 00:00:00",
    )
    assert true_message["content"] == "Alice: hello"


def test_mem0_observation_time_prompt_text_unchanged() -> None:
    """`_observation_time_prompt()` 既有 batch/session 语义与文本零变化。

    这次修复只改 `_turn_to_message` 单条 message 的前缀，不触及 batch 相对时间
    锚点；session time 缺值仍返回 None，session time 有值仍产出原样 prompt。MemBench
    session_time=None，所以无时间 MemBench message 的 prompt 必须为 None。
    """

    assert Mem0._observation_time_prompt(None) is None
    assert Mem0._observation_time_prompt("") is None
    assert Mem0._observation_time_prompt("   ") is None
    assert Mem0._observation_time_prompt("2023-05-08T13:56:00") == (
        "The observation date and time for this message is "
        "'2023-05-08T13:56:00'. Resolve relative time expressions such as "
        "'yesterday', 'today', and 'last week' only against this observation "
        "time, even if another current or observation date appears elsewhere "
        "in the extraction prompt."
    )


def test_mem0_adapter_version_bumped_to_v3_with_v2_legacy_mention() -> None:
    """adapter manifest 当前版本必须为 v3，并保留旧版本边界断言。

    五格输入/readout 保真修复改变了进入 extraction/embedding 的 build bytes
    （LoCoMo 显式 role 映射、role-native 去重复前缀、caption wrapper），因此
    `MEM0_ADAPTER_VERSION` 必须从 v2 再升一版；不删除旧值——只升当前值。真实
    resume preflight 的拒绝行为由相邻强反例单独覆盖。
    """

    from memory_benchmark.methods.mem0_adapter import MEM0_ADAPTER_VERSION

    assert MEM0_ADAPTER_VERSION == "conversation-qa-v3"
    manifest = Mem0Config.smoke().to_manifest()
    assert manifest["adapter_version"] == "conversation-qa-v3"
    # 显式不再声明 v2，防止旧 run 的 manifest 被误判兼容并静默 resume
    assert manifest["adapter_version"] != "conversation-qa-v2"
    assert manifest["adapter_version"] != "conversation-qa-v1"


def test_mem0_v2_manifest_is_rejected_by_real_resume_preflight(tmp_path: Path) -> None:
    """真实 resume preflight 必须接受同一 v3，并拒绝仅版本不同的旧 v2。"""

    current_manifest = {
        "schema_version": 2,
        "source_fingerprint_sha256": "same-hermetic-source-fingerprint",
        "method": Mem0Config.smoke().to_manifest(),
    }
    assert current_manifest["method"]["adapter_version"] == "conversation-qa-v3"
    legacy_manifest = deepcopy(current_manifest)
    legacy_manifest["method"]["adapter_version"] = "conversation-qa-v2"

    legacy_with_current_version = deepcopy(legacy_manifest)
    legacy_with_current_version["method"]["adapter_version"] = "conversation-qa-v3"
    assert legacy_with_current_version == current_manifest

    paths = ExperimentPaths.create(tmp_path / "mem0-resume-version-gate")
    atomic_write_json(paths.manifest_path, current_manifest)
    _validate_run_manifest_state(
        paths=paths,
        manifest=current_manifest,
        resume=True,
    )

    atomic_write_json(paths.manifest_path, legacy_manifest)
    with pytest.raises(ConfigurationError, match="Resume manifest mismatch"):
        _validate_run_manifest_state(
            paths=paths,
            manifest=current_manifest,
            resume=True,
        )


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


def test_mem0_halumem_session_report_returns_current_session_add_results() -> None:
    """HaluMem session 模式应在边界返回本 session 的 Mem0 add().results。

    turn 已带结构化 `normalized_role="user"`，session report 里的 memory 文本
    不应再看到 adapter 自己前置的 `user:`——content renderer 只改变正文渲染，
    不影响 session report/lineage 的 session id 顺序与条数。
    """

    conversation = Conversation(
        conversation_id="halu-user-1",
        sessions=[
            Session(
                session_id="session-a",
                session_time="Sep 01, 2025, 10:00:00",
                turns=[
                    Turn(
                        turn_id=f"a:t{index}",
                        speaker="user" if index % 2 == 0 else "assistant",
                        normalized_role="user" if index % 2 == 0 else "assistant",
                        content=f"session a message {index}",
                    )
                    for index in range(3)
                ],
            ),
            Session(
                session_id="session-b",
                session_time="Sep 02, 2025, 10:00:00",
                turns=[
                    Turn(
                        turn_id="b:t0",
                        speaker="user",
                        normalized_role="user",
                        content="session b message 0",
                    )
                ],
            ),
        ],
        metadata={"source_path": "data/halumem/HaluMem-Medium.jsonl"},
    )
    provider = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
        consume_granularity="session",
        session_memory_report=True,
    )
    reports = []
    events = tuple(build_turn_events(conversation, "halumem-run_halu-user-1"))

    for signal in GranularityAggregator("session").aggregate(
        events,
        isolation_key="halumem-run_halu-user-1",
    ):
        if isinstance(signal, SessionBatch):
            provider.ingest(signal)
        elif isinstance(signal, SessionRef):
            reports.append(provider.end_session(signal))

    assert [report.session_ref.session_id for report in reports if report] == [
        "session-a",
        "session-b",
    ]
    assert reports[0] is not None
    assert reports[0].memories == [
        "[Session time: Sep 01, 2025, 10:00:00] session a message 0",
    ]
    assert reports[1] is not None
    assert reports[1].memories == [
        "[Session time: Sep 02, 2025, 10:00:00] session b message 0",
    ]
    assert provider.session_memory_report is True
    assert [len(call["messages"]) for call in provider._memory.add_calls] == [3, 1]


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
    beam = _build_mem0_system(
        MethodBuildContext(
            config=Mem0Config.smoke(),
            openai_settings=OpenAISettings(api_key="sk-test"),
            path_settings=load_path_settings(),
            storage_root=tmp_path / "beam",
            benchmark_name="beam",
        )
    )
    halumem = _build_mem0_system(
        MethodBuildContext(
            config=Mem0Config.smoke(),
            openai_settings=OpenAISettings(api_key="sk-test"),
            path_settings=load_path_settings(),
            storage_root=tmp_path / "halumem",
            benchmark_name="halumem",
        )
    )

    assert isinstance(locomo, MemoryProvider)
    assert locomo.benchmark_name == "locomo"
    assert locomo.consume_granularity == "turn"
    assert locomo.session_memory_report is False
    assert isinstance(longmemeval, MemoryProvider)
    assert longmemeval.benchmark_name == "longmemeval"
    assert longmemeval.consume_granularity == "session"
    assert longmemeval.session_memory_report is False
    assert isinstance(beam, MemoryProvider)
    assert beam.benchmark_name == "beam"
    assert beam.consume_granularity == "pair"
    assert isinstance(halumem, MemoryProvider)
    assert halumem.benchmark_name == "halumem"
    assert halumem.consume_granularity == "session"
    assert halumem.session_memory_report is True
    assert _method_manifest_with_protocol(
        method_manifest={},
        protocol_version="v3",
    )["protocol_version"] == "v3"


def test_mem0_beam_pair_ingest_keeps_official_two_turn_chunk() -> None:
    """BEAM 的 v3 pair 路径应一次 add 两条规范 user/assistant 消息。"""

    backend = FakeMemoryBackend()
    provider = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        consume_granularity="pair",
    )
    events = tuple(build_turn_events(_build_conversation(), "beam-run_conv-1"))
    pair = TurnPair(first=events[0], second=events[1], metadata={"pair_index": 0})

    provider.ingest(pair)

    assert len(backend.add_calls) == 1
    assert [message["role"] for message in backend.add_calls[0]["messages"]] == [
        "user",
        "assistant",
    ]
    assert backend.add_calls[0]["metadata"]["turn_ids"] == ["t1", "t2"]


def _mem0_evidence_provider(benchmark_name: str | None) -> Mem0:
    """构造只用于 evidence 断言的轻量 Mem0 实例，不触发真实 API。"""

    return Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
        consume_granularity="turn",
        benchmark_name=benchmark_name,
    )


def test_mem0_retrieval_evidence_matrix_across_benchmarks() -> None:
    """Mem0 五 benchmark 的 provenance turn/session/n_a 矩阵与 BEAM reason 精确。"""

    for name in ("locomo", "membench"):
        evidence = _mem0_evidence_provider(name)._build_retrieval_evidence()
        assert evidence.semantic_provenance.status == "valid"
        assert evidence.semantic_provenance.reason_code is None
        assert evidence.provenance_granularity == "turn"
    for name in ("longmemeval", "halumem"):
        evidence = _mem0_evidence_provider(name)._build_retrieval_evidence()
        assert evidence.semantic_provenance.status == "valid"
        assert evidence.provenance_granularity == "session"

    beam = _mem0_evidence_provider("beam")._build_retrieval_evidence()
    assert beam.semantic_provenance.status == "n_a"
    assert beam.semantic_provenance.reason_code == "ingest_batch_coarser_than_gold"
    assert beam.provenance_granularity == "none"

    for identity in (None, "mystery"):
        missing = _mem0_evidence_provider(identity)._build_retrieval_evidence()
        assert missing.semantic_provenance.status == "pending"
        assert missing.semantic_provenance.reason_code == "benchmark_identity_missing"
        assert missing.provenance_granularity == "none"


def test_mem0_stable_ranking_is_pending() -> None:
    """Mem0 stable_ranking 未审计，一律 pending，不得因命中有序误盖 valid。"""

    evidence = _mem0_evidence_provider("locomo")._build_retrieval_evidence()
    assert evidence.stable_ranking.status == "pending"
    assert evidence.stable_ranking.reason_code == "ranking_fidelity_not_audited"


def test_mem0_clean_removes_vectors_messages_and_failed_attempt_context(
    tmp_path: Path,
) -> None:
    """clean 后同 namespace 再 add 不得看到失败尝试的 recent messages。"""

    backend = CleanableFakeMemoryBackend()
    provider = Mem0(
        config=Mem0Config.smoke(),
        storage_root=tmp_path,
        memory_backend=backend,
        reader_client=FakeReaderClient(),
    )
    failed = _build_named_conversation(
        "run-1_conv-failed",
        "Alice",
        "FAILED_CONTEXT",
    )
    provider.add(failed)

    provider.clean_failed_ingest_state("run-1_conv-failed")
    provider.add(
        _build_named_conversation("run-1_conv-failed", "Alice", "CLEAN_RETRY")
    )

    assert backend.deleted_run_ids == ["run-1_conv-failed"]
    assert backend.db.deleted_scopes == ["run_id=run-1_conv-failed"]
    assert backend.extraction_contexts == [[], []]
    assert get_method_registration("mem0").clean_failed_ingest_state is not None


def test_mem0_registry_clean_hook_reconstructs_v3_isolation_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """clean hook 应从 run state 路径恢复与 ingest 完全相同的 isolation key。"""

    backend = CleanableFakeMemoryBackend()
    provider = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
    )
    build_contexts: list[MethodBuildContext] = []

    def _fake_build(context: MethodBuildContext) -> Mem0:
        """记录 clean hook 传入的构建上下文并返回共享 fake provider。"""

        build_contexts.append(context)
        return provider

    monkeypatch.setattr(method_registry, "_build_mem0_system", _fake_build)
    hook = get_method_registration("mem0").clean_failed_ingest_state
    assert hook is not None
    context = MethodBuildContext(
        config=Mem0Config.smoke(),
        openai_settings=OpenAISettings(api_key="sk-test"),
        path_settings=load_path_settings(),
        storage_root=tmp_path / "run-123" / "method_state",
        benchmark_name="locomo",
    )

    hook(
        context,
        _build_named_conversation("conv-1", "Alice", "failed"),
        {"worker_idx": 2},
    )

    assert build_contexts[0].storage_root == context.storage_root / "worker_2"
    assert backend.deleted_run_ids == ["run-123_conv-1"]
    assert backend.db.deleted_scopes == ["run_id=run-123_conv-1"]


def test_vendored_sqlite_delete_messages_is_scoped(tmp_path: Path) -> None:
    """vendored SQLite API 只删除目标 session_scope 的 recent messages。"""

    mem0_root = load_path_settings().resolve_third_party_method_path("mem0-main")
    root_text = str(mem0_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    storage_module = importlib.import_module("mem0.memory.storage")
    manager = storage_module.SQLiteManager(str(tmp_path / "history.db"))
    manager.save_messages([{"role": "user", "content": "alpha"}], "run_id=a")
    manager.save_messages([{"role": "user", "content": "beta"}], "run_id=b")

    manager.delete_messages("run_id=a")

    assert manager.get_last_messages("run_id=a") == []
    assert [item["content"] for item in manager.get_last_messages("run_id=b")] == [
        "beta"
    ]


def test_production_qdrant_filters_two_mem0_namespaces(tmp_path: Path) -> None:
    """生产 Qdrant filter 层必须阻止两个 run_id namespace 交叉读取。"""

    mem0_root = load_path_settings().resolve_third_party_method_path("mem0-main")
    root_text = str(mem0_root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    qdrant_module = importlib.import_module("mem0.vector_stores.qdrant")
    store = qdrant_module.Qdrant(
        collection_name="mem0-isolation-test",
        embedding_model_dims=2,
        path=str(tmp_path / "qdrant"),
    )
    store._has_bm25_slot = False
    ids = [str(uuid.uuid4()), str(uuid.uuid4())]
    store.insert(
        vectors=[[1.0, 0.0], [1.0, 0.0]],
        ids=ids,
        payloads=[
            {"data": "ALPHA_ONLY", "run_id": "run-a"},
            {"data": "BETA_ONLY", "run_id": "run-b"},
        ],
    )

    alpha = store.search("alpha", [1.0, 0.0], top_k=10, filters={"run_id": "run-a"})
    beta = store.search("beta", [1.0, 0.0], top_k=10, filters={"run_id": "run-b"})

    assert [point.payload["data"] for point in alpha] == ["ALPHA_ONLY"]
    assert [point.payload["data"] for point in beta] == ["BETA_ONLY"]


def test_mem0_provenance_sidecar_maps_turn_and_chunk_ids(tmp_path: Path) -> None:
    """官方 memory id 应持久映射到单 turn 或完整 chunk 的公开 turn ids。"""

    turn_backend = FakeMemoryBackend()
    turn_provider = Mem0(
        config=Mem0Config.smoke(),
        storage_root=tmp_path / "turn",
        memory_backend=turn_backend,
        reader_client=FakeReaderClient(),
    )
    turn_event = tuple(build_turn_events(_build_conversation(), "run_conv-1"))[0]
    turn_provider.ingest(turn_event)
    turn_result = turn_provider.retrieve(
        RetrievalQuery(
            isolation_key="run_conv-1",
            query_text="tea",
            question_time=None,
            top_k=20,
            purpose="qa",
        )
    )
    assert turn_result.items[0].item_id == "m1"
    assert turn_result.items[0].source_turn_ids == ("t1",)

    pair_backend = FakeMemoryBackend()
    pair_provider = Mem0(
        config=Mem0Config.smoke(),
        storage_root=tmp_path / "pair",
        memory_backend=pair_backend,
        reader_client=FakeReaderClient(),
        consume_granularity="pair",
    )
    events = tuple(build_turn_events(_build_conversation(), "run_conv-1"))
    pair_provider.ingest(TurnPair(first=events[0], second=events[1]))
    pair_result = pair_provider.retrieve(
        RetrievalQuery(
            isolation_key="run_conv-1",
            query_text="tea",
            question_time=None,
            top_k=20,
            purpose="qa",
        )
    )
    assert pair_result.items[0].item_id == "m1"
    assert pair_result.items[0].source_turn_ids == ("t1", "t2")
    assert get_method_registration("mem0").provenance_granularity == "turn"


def test_mem0_retrieve_promotes_dialogue_time_from_search_metadata(
    tmp_path: Path,
) -> None:
    """检索应优先用对话 session_time，并保留存储墙钟供审计。"""

    backend = FakeMemoryBackend()
    backend.search_results = [
        {
            "id": "m1",
            "memory": "Alice planned a trip.",
            "score": 0.91,
            "created_at": "2026-07-14T07:39:30Z",
            "metadata": {
                "session_time": "2024-03-15T00:00:00",
                "first_turn_time": "2024-03-15T09:30:00",
            },
        }
    ]
    provider = Mem0(
        config=Mem0Config.smoke(),
        storage_root=tmp_path,
        memory_backend=backend,
        reader_client=FakeReaderClient(),
    )
    event = tuple(build_turn_events(_build_conversation(), "run_conv-1"))[0]
    provider.ingest(event)

    result = provider.retrieve(
        RetrievalQuery(
            isolation_key="run_conv-1",
            query_text="trip",
            question_time=None,
            top_k=20,
            purpose="qa",
        )
    )

    assert result.formatted_memory == (
        "- 2024-03-15T00:00:00: Alice planned a trip."
    )
    assert result.items[0].timestamp == "2024-03-15T00:00:00"
    assert result.items[0].metadata == {
        "timestamp_source": "session_time",
        "storage_created_at": "2026-07-14T07:39:30Z",
    }


def test_mem0_retrieve_falls_back_to_created_at_for_legacy_memory(
    tmp_path: Path,
) -> None:
    """旧记忆没有对话时间时应回退 created_at，并显式标记来源。"""

    backend = FakeMemoryBackend()
    backend.search_results = [
        {
            "id": "m1",
            "memory": "Alice planned a trip.",
            "score": 0.91,
            "created_at": "2023-05-08T13:56:00",
        }
    ]
    provider = Mem0(
        config=Mem0Config.smoke(),
        storage_root=tmp_path,
        memory_backend=backend,
        reader_client=FakeReaderClient(),
    )
    event = tuple(build_turn_events(_build_conversation(), "run_conv-1"))[0]
    provider.ingest(event)

    result = provider.retrieve(
        RetrievalQuery(
            isolation_key="run_conv-1",
            query_text="trip",
            question_time=None,
            top_k=20,
            purpose="qa",
        )
    )

    assert result.formatted_memory == (
        "- 2023-05-08T13:56:00: Alice planned a trip."
    )
    assert result.items[0].timestamp == "2023-05-08T13:56:00"
    assert result.items[0].metadata == {
        "timestamp_source": "created_at",
        "storage_created_at": "2023-05-08T13:56:00",
    }


def test_mem0_resume_requires_persisted_provenance_sidecar(tmp_path: Path) -> None:
    """旧 state 没有 sidecar 时必须 fail-fast，禁止 rank-index 伪造来源。"""

    with pytest.raises(ConfigurationError, match="predates.*provenance sidecar"):
        Mem0(
            config=Mem0Config.smoke(),
            storage_root=tmp_path,
            memory_backend=FakeMemoryBackend(),
            reader_client=FakeReaderClient(),
            existing_conversation_ids={"conv-old"},
        )


def test_mem0_provenance_sidecar_survives_resume(tmp_path: Path) -> None:
    """新 state 的 sidecar 应在 conversation-level resume 后恢复。"""

    first_backend = FakeMemoryBackend()
    first = Mem0(
        config=Mem0Config.smoke(),
        storage_root=tmp_path,
        memory_backend=first_backend,
        reader_client=FakeReaderClient(),
    )
    event = tuple(build_turn_events(_build_conversation(), "run_conv-1"))[0]
    first.ingest(event)

    resumed_backend = FakeMemoryBackend()
    resumed = Mem0(
        config=Mem0Config.smoke(),
        storage_root=tmp_path,
        memory_backend=resumed_backend,
        reader_client=FakeReaderClient(),
        existing_conversation_ids={"run_conv-1"},
    )
    result = resumed.retrieve(
        RetrievalQuery(
            isolation_key="run_conv-1",
            query_text="tea",
            question_time=None,
            top_k=20,
            purpose="qa",
        )
    )

    assert result.items[0].item_id == "m1"
    assert result.items[0].source_turn_ids == ("t1",)


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
            "top_k": 20,
        }
    ]
    assert prediction.question_id == "conv-1:q1"
    assert prediction.conversation_id == "conv-1"
    assert prediction.answer == "She likes jasmine tea."
    assert prediction.metadata == {
        "method": "mem0",
        "retrieved_memory_count": 1,
        "top_k": 20,
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
            "created_at": "2026-07-14T07:39:30Z",
            "metadata": {"session_time": "2023-05-08T13:56:00"},
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
    assert "2026-07-14" not in prompt
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


def test_mem0_beam_native_messages_match_official_builder() -> None:
    """显式 BEAM 身份必须生成官方 memory-benchmarks answer prompt。"""

    backend = FakeMemoryBackend()
    backend.search_results = [
        {
            "id": "m1",
            "memory": "Alice likes jasmine tea.",
            "score": 0.91,
            "created_at": "2024-04-02T00:00:00",
        }
    ]
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        benchmark_name="beam",
    )
    system.add([_build_conversation()])
    question = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="What tea does Alice like?",
        category="temporal_reasoning",
    )

    retrieval = system.retrieve(question)
    prompt_module = _load_mem0_benchmark_prompt_module(
        system.path_settings,
        "beam",
        prompt_builder_name="get_beam_answer_generation_prompt",
    )
    expected = prompt_module.get_beam_answer_generation_prompt(
        question=question.text,
        memories=system._normalize_search_results(backend.search_results),
        top_k=None,
    )

    assert [message.role for message in retrieval.prompt_messages] == ["user"]
    assert retrieval.prompt_messages[0].content == expected
    assert retrieval.metadata["answer_prompt_profile"] == "beam"


def test_mem0_explicit_benchmark_identity_precedes_shape_heuristics() -> None:
    """显式 benchmark 身份必须压过 category 与 question_time 启发式。"""

    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
        benchmark_name="beam",
    )
    misleading_question = Question(
        question_id="q1",
        conversation_id="c1",
        text="Question?",
        question_time="2024-01-01",
        category="1",
    )

    assert system._reader_prompt_kind(misleading_question) == "beam"


def test_mem0_beam_unified_prompt_ignores_native_provider_messages() -> None:
    """BEAM unified builder 只读 formatted_memory，native messages 不得改字节。"""

    from memory_benchmark.benchmark_adapters.beam import (
        build_beam_unified_answer_prompt,
    )
    from memory_benchmark.core import PromptMessage
    from memory_benchmark.core.provider_protocol import RetrievalResult

    question = Question("q1", "c1", "What happened?")
    formatted_memory = "2024-04-02: Alice changed her preference."
    generic = RetrievalResult(
        formatted_memory=formatted_memory,
        prompt_messages=(PromptMessage(role="system", content="generic"),),
    )
    native = RetrievalResult(
        formatted_memory=formatted_memory,
        prompt_messages=(PromptMessage(role="user", content="official native"),),
    )

    assert (
        build_beam_unified_answer_prompt(question, generic).answer_prompt
        == build_beam_unified_answer_prompt(question, native).answer_prompt
    )


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
    # embedder 归一化为本地 huggingface provider，不带 api_key/openai_base_url。
    assert backend_config["embedder"]["provider"] == "huggingface"
    assert backend_config["embedder"]["config"]["model"] == (
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    assert backend_config["embedder"]["config"]["embedding_dims"] == 384
    assert "api_key" not in backend_config["embedder"]["config"]
    assert "openai_base_url" not in backend_config["embedder"]["config"]
    assert backend_config["vector_store"]["config"]["embedding_model_dims"] == 384
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


# ---- Mem0 五格输入/readout 保真 R1 强反例 ------------------------------------
# 联合裁决=docs/workstreams/ws02.7-method-track/branches/method-recertification/
# mem0/notes/mem0-joint-ruling.md。五个真实缺口：LoCoMo 显式 speaker_a/b 映射、
# 共享 caption wrapper、role-native content 去重复前缀、MemBench/HaluMem native
# sanity readout 误标、HaluMem update probe top_k 透传。不新增任何 placeholder。


def _build_locomo_conversation(
    *,
    conversation_id: str,
    speaker_a: str,
    speaker_b: str,
    first_speaker: str,
) -> Conversation:
    """构造两 turn 的 LoCoMo 风格 conversation：无 normalized_role，显式声明 speaker_a/b。"""

    second_speaker = speaker_b if first_speaker == speaker_a else speaker_a
    return Conversation(
        conversation_id=conversation_id,
        sessions=[
            Session(
                session_id="s1",
                session_time="2023-05-08",
                turns=[
                    Turn(
                        turn_id=f"{conversation_id}:t0",
                        speaker=first_speaker,
                        content=f"{first_speaker} speaks first.",
                    ),
                    Turn(
                        turn_id=f"{conversation_id}:t1",
                        speaker=second_speaker,
                        content=f"{second_speaker} replies.",
                    ),
                ],
            )
        ],
        metadata={"speaker_a": speaker_a, "speaker_b": speaker_b},
    )


def test_mem0_locomo_explicit_speaker_mapping_locks_speaker_b_first_via_legacy_add() -> None:
    """LoCoMo speaker_a 首发与 speaker_b 首发都必须得到同一显式映射（speaker_a=user）。

    current-main 的首现 `_build_speaker_roles` 会在 speaker_b 首发时把官方角色
    整体反转——source-locked `locomo10.json` 10 个 conversation 里恰有 6 个是这种
    形状。这里用同一对 speaker_a/speaker_b 分别构造 speaker_a 先说和 speaker_b
    先说两个 conversation，必须得到完全相同的 user/assistant 归属，与说话顺序
    无关。
    """

    speaker_a_first = _build_locomo_conversation(
        conversation_id="locomo-a-first",
        speaker_a="Caroline",
        speaker_b="Melanie",
        first_speaker="Caroline",
    )
    speaker_b_first = _build_locomo_conversation(
        conversation_id="locomo-b-first",
        speaker_a="Caroline",
        speaker_b="Melanie",
        first_speaker="Melanie",
    )

    backend = FakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        benchmark_name="locomo",
    )

    system.add([speaker_a_first])
    system.add([speaker_b_first])

    a_first_roles = [
        backend.add_calls[0]["messages"][0]["role"],
        backend.add_calls[1]["messages"][0]["role"],
    ]
    b_first_roles = [
        backend.add_calls[2]["messages"][0]["role"],
        backend.add_calls[3]["messages"][0]["role"],
    ]
    # Caroline(=speaker_a) 恒为 user、Melanie(=speaker_b) 恒为 assistant，
    # 与谁先说话无关——这正是 current-main 首现算法会算错的地方。
    assert a_first_roles == ["user", "assistant"]
    assert b_first_roles == ["assistant", "user"]
    assert backend.add_calls[0]["messages"][0]["content"] == (
        "[Session time: 2023-05-08] Caroline: Caroline speaks first."
    )
    assert backend.add_calls[2]["messages"][0]["content"] == (
        "[Session time: 2023-05-08] Melanie: Melanie speaks first."
    )


def test_mem0_locomo_v3_event_speaker_mapping_matches_legacy_add_byte_for_byte() -> None:
    """v3 event 路径必须用同一显式映射；speaker_b 首发时 legacy 与 v3 产出字节完全一致。"""

    conversation = _build_locomo_conversation(
        conversation_id="locomo-v3-b-first",
        speaker_a="Caroline",
        speaker_b="Melanie",
        first_speaker="Melanie",
    )

    legacy_backend = FakeMemoryBackend()
    legacy_system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=legacy_backend,
        reader_client=FakeReaderClient(),
        benchmark_name="locomo",
    )
    legacy_system.add([conversation])

    v3_backend = FakeMemoryBackend()
    v3_system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=v3_backend,
        reader_client=FakeReaderClient(),
        benchmark_name="locomo",
        consume_granularity="turn",
    )
    events = tuple(build_turn_events(conversation, "locomo-run_locomo-v3-b-first"))
    for event in events:
        v3_system.ingest(event)

    legacy_messages = [call["messages"][0] for call in legacy_backend.add_calls]
    v3_messages = [call["messages"][0] for call in v3_backend.add_calls]
    assert legacy_messages == v3_messages
    assert [message["role"] for message in v3_messages] == ["assistant", "user"]


def test_mem0_locomo_speaker_mapping_fails_fast_on_missing_blank_or_equal_metadata() -> None:
    """缺 speaker_a、空白 speaker_b、二者相同，均必须 fail-fast，不回落首现推断。"""

    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
        benchmark_name="locomo",
    )

    def _single_turn_conversation(conversation_id: str, metadata: dict[str, object]) -> Conversation:
        """构造只含一个 turn 的最小 conversation，专用于校验 metadata fail-fast。"""

        return Conversation(
            conversation_id=conversation_id,
            sessions=[
                Session(
                    session_id="s1",
                    session_time="2023-05-08",
                    turns=[Turn(turn_id="t0", speaker="Caroline", content="hi")],
                )
            ],
            metadata=metadata,
        )

    with pytest.raises(ConfigurationError, match="speaker_a and speaker_b"):
        system.add(
            [_single_turn_conversation("locomo-missing-a", {"speaker_b": "Melanie"})]
        )
    with pytest.raises(ConfigurationError, match="speaker_a and speaker_b"):
        system.add(
            [
                _single_turn_conversation(
                    "locomo-blank-b", {"speaker_a": "Caroline", "speaker_b": "   "}
                )
            ]
        )
    with pytest.raises(ConfigurationError, match="must be distinct"):
        system.add(
            [
                _single_turn_conversation(
                    "locomo-equal", {"speaker_a": "Caroline", "speaker_b": "Caroline"}
                )
            ]
        )


def test_mem0_locomo_speaker_mapping_fails_fast_on_undeclared_third_speaker() -> None:
    """真实 turn 出现未在 speaker_a/b 声明的第三方发言者时必须 fail-fast。"""

    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
        benchmark_name="locomo",
    )
    conversation = Conversation(
        conversation_id="locomo-third-speaker",
        sessions=[
            Session(
                session_id="s1",
                session_time="2023-05-08",
                turns=[
                    Turn(turn_id="t0", speaker="Caroline", content="hi"),
                    Turn(turn_id="t1", speaker="Stranger", content="who are you?"),
                ],
            )
        ],
        metadata={"speaker_a": "Caroline", "speaker_b": "Melanie"},
    )

    with pytest.raises(ConfigurationError, match="not declared in"):
        system.add([conversation])


def test_mem0_locomo_singleton_turns_have_exactly_one_message_and_no_placeholder() -> None:
    """LoCoMo 单独 user turn、单独 assistant turn 各自只产生一条 message，无 placeholder。"""

    backend = FakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        benchmark_name="locomo",
    )
    metadata = {"speaker_a": "Caroline", "speaker_b": "Melanie"}

    user_only = Conversation(
        conversation_id="locomo-user-singleton",
        sessions=[
            Session(
                session_id="s1",
                session_time="2023-05-08",
                turns=[Turn(turn_id="t0", speaker="Caroline", content="solo user turn")],
            )
        ],
        metadata=metadata,
    )
    assistant_only = Conversation(
        conversation_id="locomo-assistant-singleton",
        sessions=[
            Session(
                session_id="s1",
                session_time="2023-05-08",
                turns=[Turn(turn_id="t0", speaker="Melanie", content="solo assistant turn")],
            )
        ],
        metadata=metadata,
    )

    system.add([user_only])
    system.add([assistant_only])

    assert [len(call["messages"]) for call in backend.add_calls] == [1, 1]
    assert backend.add_calls[0]["messages"][0]["role"] == "user"
    assert backend.add_calls[0]["messages"][0]["content"] == (
        "[Session time: 2023-05-08] Caroline: solo user turn"
    )
    assert backend.add_calls[1]["messages"][0]["role"] == "assistant"
    assert backend.add_calls[1]["messages"][0]["content"] == (
        "[Session time: 2023-05-08] Melanie: solo assistant turn"
    )


def test_mem0_locomo_caption_wrapper_variants_render_exactly_once() -> None:
    """正文+caption、caption-only、多个 caption、空白 caption：wrapper 恰一次，query/URL 不泄漏。"""

    backend = FakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        benchmark_name="locomo",
    )
    metadata = {"speaker_a": "Caroline", "speaker_b": "Melanie"}

    def _single_image_conversation(
        conversation_id: str, content: str, images: list[ImageRef]
    ) -> Conversation:
        """构造只含一个带图片 turn 的最小 conversation，session_time=None 避免时间前缀干扰。"""

        return Conversation(
            conversation_id=conversation_id,
            sessions=[
                Session(
                    session_id="s1",
                    session_time=None,
                    turns=[
                        Turn(
                            turn_id="t0",
                            speaker="Caroline",
                            content=content,
                            images=images,
                        )
                    ],
                )
            ],
            metadata=metadata,
        )

    text_and_caption = _single_image_conversation(
        "locomo-caption-text",
        "check this out",
        [
            ImageRef(
                image_id="img-1",
                path="images/vase.jpg?query=vase&token=secret",
                caption="a blue vase on a table",
                metadata={"query": "vase"},
            )
        ],
    )
    caption_only = _single_image_conversation(
        "locomo-caption-only",
        "",
        [ImageRef(image_id="img-2", path="images/cat.jpg", caption="a sleeping cat")],
    )
    multi_caption = _single_image_conversation(
        "locomo-caption-multi",
        "two photos",
        [
            ImageRef(image_id="img-3", caption="a red bike"),
            ImageRef(image_id="img-4", caption="a green door"),
        ],
    )
    blank_caption = _single_image_conversation(
        "locomo-caption-blank",
        "no usable caption here",
        [
            ImageRef(image_id="img-5", caption="   "),
            ImageRef(image_id="img-6", caption=None),
        ],
    )

    for conversation in (text_and_caption, caption_only, multi_caption, blank_caption):
        system.add([conversation])

    contents = [call["messages"][0]["content"] for call in backend.add_calls]

    assert contents[0] == (
        "Caroline: check this out [Sharing image that shows: a blue vase on a table]"
    )
    assert contents[0].count("[Sharing image that shows:") == 1
    assert "query" not in contents[0]
    assert "secret" not in contents[0]
    assert "vase.jpg" not in contents[0]

    assert contents[1] == "Caroline: [Sharing image that shows: a sleeping cat]"

    assert contents[2] == (
        "Caroline: two photos [Sharing image that shows: a red bike] "
        "[Sharing image that shows: a green door]"
    )
    assert contents[2].count("[Sharing image that shows:") == 2

    assert contents[3] == "Caroline: no usable caption here"
    assert "[Sharing image that shows:" not in contents[3]


def test_mem0_longmemeval_consecutive_same_role_session_has_no_role_text_duplication() -> None:
    """LongMemEval 连续同 role（如两个连续 user）必须保持官方位置切块，且无角色文本重复。"""

    conversation = Conversation(
        conversation_id="lme-consecutive",
        sessions=[
            Session(
                session_id="haystack-cc",
                session_time="2024-02-01",
                turns=[
                    Turn(
                        turn_id=f"haystack-cc:t{index}",
                        speaker=role,
                        normalized_role=role,
                        content=f"message {index}",
                    )
                    for index, role in enumerate(["user", "user", "assistant"])
                ],
            )
        ],
        metadata={"source_path": "data/longmemeval/longmemeval_s_cleaned.json"},
    )
    backend = FakeMemoryBackend()
    system = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        consume_granularity="session",
        benchmark_name="longmemeval",
    )
    events = tuple(build_turn_events(conversation, "lme-run_lme-consecutive"))
    batch = SessionBatch(
        isolation_key="lme-run_lme-consecutive",
        session_id="haystack-cc",
        events=events,
        session_time="2024-02-01",
    )

    system.ingest(batch)

    assert [len(call["messages"]) for call in backend.add_calls] == [2, 1]
    first_chunk = backend.add_calls[0]["messages"]
    second_chunk = backend.add_calls[1]["messages"]
    assert [message["role"] for message in first_chunk] == ["user", "user"]
    assert first_chunk[0]["content"] == "[Session time: 2024-02-01] message 0"
    assert first_chunk[1]["content"] == "[Session time: 2024-02-01] message 1"
    assert second_chunk[0]["role"] == "assistant"
    for message in first_chunk + second_chunk:
        assert "user: " not in message["content"]
        assert "assistant: " not in message["content"]


def test_mem0_membench_first_agent_children_and_third_agent_singleton_render_original_text_once() -> None:
    """MemBench FirstAgent 两个 canonical child 各自 singleton；ThirdAgent singleton user；

    正文/内嵌时间原样一次，marker=True 时无 [Turn time]/[Session time] header，
    且 role-native content 不再重复前置角色文本。
    """

    backend = FakeMemoryBackend()
    provider = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        consume_granularity="turn",
        benchmark_name="membench",
    )
    conversation = Conversation(
        conversation_id="membench-fa-ta",
        sessions=[
            Session(
                session_id="s1",
                session_time=None,
                turns=[
                    Turn(
                        turn_id="s1:user",
                        speaker="user",
                        normalized_role="user",
                        content=(
                            "(place: Boston, MA; time: '2024-10-01 08:00' Monday) "
                            "I watched a movie."
                        ),
                        turn_time="2024-10-01 08:00",
                        metadata={"source_timestamp_embedded_in_content": True},
                    ),
                    Turn(
                        turn_id="s1:agent",
                        speaker="agent",
                        normalized_role="assistant",
                        content=(
                            "(place: Boston, MA; time: '2024-10-01 08:00' Monday) Noted."
                        ),
                        turn_time="2024-10-01 08:00",
                        metadata={"source_timestamp_embedded_in_content": True},
                    ),
                ],
            ),
            Session(
                session_id="s2",
                session_time=None,
                turns=[
                    Turn(
                        turn_id="s2:third",
                        speaker="user",
                        normalized_role="user",
                        content=(
                            "(place: Boston, MA; time: '2024-10-01 09:00' Monday) "
                            "The user watched a movie."
                        ),
                        turn_time="2024-10-01 09:00",
                        metadata={"source_timestamp_embedded_in_content": True},
                    ),
                ],
            ),
        ],
    )
    events = tuple(build_turn_events(conversation, "membench-run_membench-fa-ta"))
    for event in events:
        provider.ingest(event)

    assert [len(call["messages"]) for call in backend.add_calls] == [1, 1, 1]
    first_child = backend.add_calls[0]["messages"][0]
    second_child = backend.add_calls[1]["messages"][0]
    third_agent = backend.add_calls[2]["messages"][0]
    assert first_child["role"] == "user"
    assert first_child["content"] == (
        "(place: Boston, MA; time: '2024-10-01 08:00' Monday) I watched a movie."
    )
    assert second_child["role"] == "assistant"
    assert second_child["content"] == (
        "(place: Boston, MA; time: '2024-10-01 08:00' Monday) Noted."
    )
    assert third_agent["role"] == "user"
    assert third_agent["content"] == (
        "(place: Boston, MA; time: '2024-10-01 09:00' Monday) The user watched a movie."
    )
    for message in (first_child, second_child, third_agent):
        assert "user:" not in message["content"]
        assert "assistant:" not in message["content"]
        assert "[Turn time" not in message["content"]
        assert "[Session time" not in message["content"]


def test_mem0_beam_dangling_tail_produces_singleton_add_with_no_synthetic_partner() -> None:
    """BEAM 10M 风格奇数 session（user,assistant,user）：dangling tail 只单独 add，不补 assistant。"""

    backend = FakeMemoryBackend()
    provider = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        consume_granularity="pair",
        benchmark_name="beam",
    )
    conversation = Conversation(
        conversation_id="beam-dangling",
        sessions=[
            Session(
                session_id="s1",
                session_time="2024-04-02T00:00:00",
                turns=[
                    Turn(
                        turn_id="s1:t0",
                        speaker="user",
                        normalized_role="user",
                        content="first user turn",
                    ),
                    Turn(
                        turn_id="s1:t1",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="assistant reply",
                    ),
                    Turn(
                        turn_id="s1:t2",
                        speaker="user",
                        normalized_role="user",
                        content="dangling user turn",
                    ),
                ],
            )
        ],
    )
    events = tuple(build_turn_events(conversation, "beam-run_beam-dangling"))

    for signal in GranularityAggregator("pair").aggregate(
        events,
        isolation_key="beam-run_beam-dangling",
    ):
        if isinstance(signal, TurnPair):
            provider.ingest(signal)

    assert len(backend.add_calls) == 2
    assert [len(call["messages"]) for call in backend.add_calls] == [2, 1]
    normal_pair = backend.add_calls[0]["messages"]
    assert [message["role"] for message in normal_pair] == ["user", "assistant"]
    assert normal_pair[0]["content"] == "[Session time: 2024-04-02T00:00:00] first user turn"
    assert normal_pair[1]["content"] == "[Session time: 2024-04-02T00:00:00] assistant reply"

    dangling_call = backend.add_calls[1]
    assert len(dangling_call["messages"]) == 1
    assert dangling_call["messages"][0]["role"] == "user"
    assert dangling_call["messages"][0]["content"] == (
        "[Session time: 2024-04-02T00:00:00] dangling user turn"
    )
    assert dangling_call["metadata"]["turn_ids"] == ["s1:t2"]


def test_mem0_halumem_update_probe_uses_query_top_k_while_qa_keeps_configured_top_k() -> None:
    """`purpose=memory_update_probe` 时忠实采用 `query.top_k`；`qa` 仍用 profile top_k。

    HaluMem 官方 update probe 请求窗口为 10（`operation_level.py` 硬编码），与
    `Mem0Config.smoke().top_k=20` 的标准检索深度不同。qa 请求刻意传入
    `top_k=5`（不同于 config 的 20），证明 qa purpose 是真正忽略 `query.top_k`，
    而不是恰好与 config 数值相同。
    """

    backend = FakeMemoryBackend()
    provider = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=backend,
        reader_client=FakeReaderClient(),
        benchmark_name="halumem",
    )
    event = tuple(build_turn_events(_build_conversation(), "halumem-run_conv-1"))[0]
    provider.ingest(event)

    update_result = provider.retrieve(
        RetrievalQuery(
            isolation_key="halumem-run_conv-1",
            query_text="some memory point content",
            question_time=None,
            top_k=10,
            purpose="memory_update_probe",
        )
    )
    qa_result = provider.retrieve(
        RetrievalQuery(
            isolation_key="halumem-run_conv-1",
            query_text="qa question",
            question_time=None,
            top_k=5,
            purpose="qa",
        )
    )

    assert backend.search_calls[0]["top_k"] == 10
    assert backend.search_calls[1]["top_k"] == 20
    assert update_result.metadata["top_k"] == 10
    assert update_result.metadata["configured_top_k"] == 20
    assert update_result.metadata["top_k_source"] == "query_top_k"
    assert qa_result.metadata["top_k"] == 20
    assert qa_result.metadata["configured_top_k"] == 20
    assert qa_result.metadata["top_k_source"] == "config_top_k"


def test_mem0_reader_prompt_kind_explicit_non_native_identity_stays_generic() -> None:
    """显式 benchmark_name 不在三家官方 native prompt 名单时一律 generic，不猜成别家。

    MemBench 100% 问题都带 `question_time`；HaluMem category 恰好撞上 LoCoMo
    启发式使用的数字类目。两者都必须仍返回 generic，不能被数据形态启发式带偏。
    """

    membench = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
        benchmark_name="membench",
    )
    membench_question = Question(
        question_id="q1",
        conversation_id="c1",
        text="What happened?",
        question_time="2024-10-01 08:00",
    )
    assert membench._reader_prompt_kind(membench_question) == "generic"

    halumem = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
        benchmark_name="halumem",
    )
    halumem_question = Question(
        question_id="q2",
        conversation_id="c2",
        text="What happened?",
        category="1",
    )
    assert halumem._reader_prompt_kind(halumem_question) == "generic"


def test_mem0_reader_prompt_kind_none_identity_still_uses_legacy_heuristics() -> None:
    """`benchmark_name is None` 的旧版兼容调用必须保留 `question_time` 兜底启发式。

    只有显式 identity 缺失时才允许这条启发式生效；上一条测试锁住显式非三家
    identity 必须走 generic，两条测试合起来证明分支互不覆盖。
    """

    legacy = Mem0(
        config=Mem0Config.smoke(),
        memory_backend=FakeMemoryBackend(),
        reader_client=FakeReaderClient(),
    )
    question = Question(
        question_id="q1",
        conversation_id="c1",
        text="What happened?",
        question_time="2024-10-01 08:00",
    )
    assert legacy._reader_prompt_kind(question) == "longmemeval"

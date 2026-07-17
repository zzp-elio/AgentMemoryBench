"""LightMem adapter 的配置、源码身份和基础契约测试。

这些测试不调用真实 API，也不初始化重模型。目标是先锁定官方源码路径和强配置校验。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import logging
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from memory_benchmark.config import (
    OpenAISettings,
    PathSettings,
    load_path_settings,
    load_typed_profile,
)
from memory_benchmark.core import (
    AnswerResult,
    ConfigurationError,
    Conversation,
    TaskFamily,
    Question,
    Session,
    Turn,
    validate_compatibility,
)
from memory_benchmark.core.provider_protocol import (
    MemoryProvider,
    RetrievalQuery,
    RetrievedItem,
    SessionBatch,
    SessionRef,
    TurnEvent,
    UnitRef,
)
from memory_benchmark.methods.lightmem_adapter import (
    LIGHTMEM_ADAPTER_VERSION,
    LIGHTMEM_PLACEHOLDER_MARKER,
    LightMem,
    LightMemConfig,
    _turn_timestamp,
    build_lightmem_source_identity,
    clean_lightmem_conversation_state,
    import_lightmem_classes,
)
from memory_benchmark.methods.lightmem_native_prompts import (
    build_lightmem_locomo_native_answer_prompt,
    build_lightmem_longmemeval_native_answer_prompt,
)
from memory_benchmark.methods.registry import (
    MethodBuildContext,
    _build_lightmem_system,
    get_method_registration,
)
from memory_benchmark.observability.efficiency import EfficiencyCollector
from memory_benchmark.runners.event_stream import GranularityAggregator, build_turn_events
from memory_benchmark.runners.prediction import _method_manifest_with_protocol
from tests.equivalence_utils import run_bridge_sequence, run_native_sequence


def test_lightmem_config_rejects_invalid_retrieve_limit() -> None:
    """retrieve_limit 是 method 内部检索数量，必须为正数。"""

    with pytest.raises(ConfigurationError, match="retrieve_limit"):
        LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=0,
            max_workers=1,
            profile_name="bad",
        )


def test_lightmem_config_rejects_invalid_lifecycle_profile() -> None:
    """lifecycle_profile 只接受 online_soft 与 locomo_offline_consolidated 两个值。"""

    with pytest.raises(ConfigurationError, match="lifecycle_profile"):
        LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=60,
            max_workers=1,
            profile_name="bad",
            lifecycle_profile="online",
        )


@pytest.mark.parametrize(
    "lifecycle_profile",
    ["online_soft", "locomo_offline_consolidated"],
)
def test_lightmem_config_accepts_valid_lifecycle_profiles(
    lifecycle_profile: str,
) -> None:
    """两个合法 lifecycle_profile 取值都应通过强校验。"""

    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=60,
        max_workers=1,
        profile_name="official-mini",
        lifecycle_profile=lifecycle_profile,
    )

    assert config.lifecycle_profile == lifecycle_profile


def test_lightmem_config_manifest_includes_lifecycle_profile_and_adapter_version_v4() -> None:
    """公开 manifest 必须携带 lifecycle_profile、missing_timestamp_policy 与
    messages_use，adapter_version 升级为 v4（旧 v3 manifest 由全 manifest 比较拒绝
    resume）。"""

    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=60,
        max_workers=1,
        profile_name="official-mini",
    )

    manifest = config.to_manifest()

    assert manifest["lifecycle_profile"] == "online_soft"
    assert manifest["missing_timestamp_policy"] == "require"
    assert manifest["messages_use"] == "user_only"
    assert manifest["adapter_version"] == LIGHTMEM_ADAPTER_VERSION == "conversation-qa-v5"


def test_lightmem_toml_profiles_declare_online_soft_lifecycle_explicitly() -> None:
    """smoke/official_full TOML profile 都应显式声明 online_soft 与 hybrid messages_use。"""

    toml_path = (
        load_path_settings().project_root / "configs" / "methods" / "lightmem.toml"
    )

    smoke = load_typed_profile(toml_path, "smoke", LightMemConfig)
    official_full = load_typed_profile(toml_path, "official_full", LightMemConfig)

    assert smoke.lifecycle_profile == "online_soft"
    assert official_full.lifecycle_profile == "online_soft"
    assert smoke.missing_timestamp_policy == "preserve_none"
    assert official_full.missing_timestamp_policy == "preserve_none"
    assert smoke.messages_use == "hybrid"
    assert official_full.messages_use == "hybrid"


def test_lightmem_source_identity_covers_official_core_files() -> None:
    """source identity 必须覆盖 LightMem 官方核心包和实验入口。"""

    identity = build_lightmem_source_identity(load_path_settings())

    assert identity["source_sha256"]
    assert "src/lightmem/memory/lightmem.py" in identity["files"]
    assert "experiments/locomo/add_locomo.py" in identity["files"]
    assert "experiments/locomo/search_locomo.py" in identity["files"]


def test_lightmem_can_import_official_lightmemory_class() -> None:
    """adapter 应能从 vendored LightMem 源码导入官方 LightMemory 类。"""

    classes = import_lightmem_classes(load_path_settings())

    assert classes["LightMemory"].__name__ == "LightMemory"


def test_lightmem_import_keeps_vendored_src_path_for_thread_safety() -> None:
    """LightMem vendored src 路径导入后应保留，避免多线程反复插拔 `sys.path`。"""

    path_settings = load_path_settings()
    src_root = (
        path_settings.resolve_third_party_method_path("LightMem") / "src"
    ).resolve()
    src_root_text = str(src_root)
    if src_root_text in sys.path:
        sys.path.remove(src_root_text)

    classes = import_lightmem_classes(path_settings)

    assert classes["LightMemory"].__name__ == "LightMemory"
    assert src_root_text in sys.path


def test_clean_lightmem_conversation_state_removes_target_qdrant_and_logs(
    tmp_path: Path,
) -> None:
    """LightMem clean retry 应删除目标 conversation 的 Qdrant 和日志目录。

    输入:
        storage_root: LightMem method state 根目录，含目标 conversation 与 sibling
            conversation 的 collection 目录。

    输出:
        目标 conversation 的 embedding、summary 和 log 目录被删除；sibling 保留。
    """

    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
        retrieve_limit=2,
        max_workers=1,
        profile_name="smoke",
    )
    openai_settings = OpenAISettings(
        api_key="sk-test",
        base_url="https://example.invalid/v1",
    )
    target_backend_config = LightMem.build_backend_config(
        config=config,
        openai_settings=openai_settings,
        storage_root=tmp_path,
        conversation_id="conv/1",
        project_root=tmp_path,
    )
    sibling_backend_config = LightMem.build_backend_config(
        config=config,
        openai_settings=openai_settings,
        storage_root=tmp_path,
        conversation_id="conv-2",
        project_root=tmp_path,
    )
    target_paths = [
        Path(target_backend_config["embedding_retriever"]["configs"]["path"]),
        Path(target_backend_config["summary_retriever"]["configs"]["path"]),
        Path(target_backend_config["logging"]["log_dir"]),
    ]
    sibling_paths = [
        Path(sibling_backend_config["embedding_retriever"]["configs"]["path"]),
        Path(sibling_backend_config["summary_retriever"]["configs"]["path"]),
        Path(sibling_backend_config["logging"]["log_dir"]),
    ]
    for path in target_paths + sibling_paths:
        path.mkdir(parents=True)
        (path / "marker.txt").write_text("state", encoding="utf-8")

    clean_lightmem_conversation_state(tmp_path, "conv/1")

    assert all(not path.exists() for path in target_paths)
    assert all(path.exists() for path in sibling_paths)


class FakeLightMemoryBackend:
    """模拟官方 LightMemory 的 add_memory/retrieve 方法。"""

    def __init__(self) -> None:
        """初始化 fake 调用记录。"""

        self.added_messages: list[dict[str, object]] = []
        self.queries: list[dict[str, object]] = []
        self.construct_update_calls: list[dict[str, object]] = []
        self.offline_update_calls: list[dict[str, object]] = []
        self.text_embedder = FakeLightMemEmbedder()
        self.embedding_retriever = FakeLightMemEmbeddingRetriever()
        self.manager = FakeLightMemManager()

    def add_memory(self, messages, **kwargs):
        """记录写入消息和 LightMem pipeline 参数。"""

        self.added_messages.append({"messages": messages, "kwargs": kwargs})
        if kwargs.get("force_extract"):
            self.manager.generate_response(
                messages=[
                    {"role": "system", "content": "extract memory"},
                    {"role": "user", "content": str(messages)},
                ],
                response_format={"type": "json_object"},
            )
        return {"api_call_nums": 0}

    def retrieve(self, query, limit=10, filters=None):
        """记录检索请求并返回 fake memory context。"""

        self.queries.append({"query": query, "limit": limit, "filters": filters})
        return ["2026-01-01 Alice likes tea"]

    def construct_update_queue_all_entries(self, **kwargs):
        """记录官方 LoCoMo 离线更新前的 update queue 构造。"""

        self.construct_update_calls.append(kwargs)

    def offline_update_all_entries(self, **kwargs):
        """记录官方 LoCoMo 离线更新调用。"""

        self.offline_update_calls.append(kwargs)


class SessionCaptureFakeLightMemoryBackend(FakeLightMemoryBackend):
    """在 force extraction 时模拟 LightMem 向量 payload 插入。"""

    def add_memory(self, messages, **kwargs):
        """记录调用，并把当前 session 的一条生成记忆写入 fake retriever。"""

        result = super().add_memory(messages, **kwargs)
        if kwargs.get("force_extract"):
            session_number = len(self.added_messages)
            self.embedding_retriever.insert(
                vectors=[[1.0, 0.0]],
                payloads=[
                    {
                        "memory": f"session-memory-{session_number}",
                        "time_stamp": messages[0]["time_stamp"],
                    }
                ],
                ids=[f"session-memory-id-{session_number}"],
            )
        return result


class ThreadedUpdateFakeLightMemoryBackend(FakeLightMemoryBackend):
    """模拟 LightMem OP-update 在线程池内调用 memory manager。"""

    def offline_update_all_entries(self, **kwargs):
        """用线程池调用 manager.generate_response，复现 ContextVar 丢失场景。"""

        super().offline_update_all_entries(**kwargs)
        payloads = ("update-entry-1", "update-entry-2")

        def _call_manager(payload: str):
            """在子线程执行一次官方 manager LLM 调用。"""

            return self.manager.generate_response(
                messages=[
                    {"role": "system", "content": "update memory"},
                    {"role": "user", "content": payload},
                ],
                response_format={"type": "json_object"},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            list(executor.map(_call_manager, payloads))


class FakeLightMemEmbedder:
    """模拟 LightMem 官方 TextEmbedderHuggingface。"""

    def __init__(self) -> None:
        """初始化 query 记录。"""

        self.embedded_texts: list[str] = []

    def embed(self, text: str) -> list[float]:
        """返回稳定二维向量，便于测试 cosine 排序。"""

        self.embedded_texts.append(text)
        return [1.0, 0.0]


class FakeLightMemEmbeddingRetriever:
    """模拟 LightMem 官方 Qdrant retriever 的 search/get_all 接口。"""

    def __init__(self) -> None:
        """初始化带 payload/vector 的 fake Qdrant entries。"""

        self.get_all_calls: list[dict[str, object]] = []
        self.search_calls: list[dict[str, object]] = []
        self.entries = [
            {
                "id": "alice-tea",
                "vector": [1.0, 0.0],
                "payload": {
                    "speaker_name": "Alice",
                    "memory": "Alice likes jasmine tea.",
                    "time_stamp": "2026-01-01T00:00:00.000",
                    "weekday": "Thu",
                    "source_external_id": "D1:1",
                    "source_external_ids": ["D1:1"],
                },
            },
            {
                "id": "bob-tea",
                "vector": [0.8, 0.0],
                "payload": {
                    "speaker_name": "Bob",
                    "memory": "Bob remembered Alice's tea preference.",
                    "time_stamp": "2026-01-01T00:00:01.000",
                    "weekday": "Thu",
                    "source_external_id": "D1:2",
                    "source_external_ids": ["D1:2"],
                },
            },
            {
                "id": "irrelevant",
                "vector": [0.0, 1.0],
                "payload": {
                    "speaker_name": "Alice",
                    "memory": "Alice dislikes noisy airports.",
                    "time_stamp": "2026-01-01T00:00:02.000",
                    "weekday": "Thu",
                    "source_external_id": "D2:1",
                    "source_external_ids": ["D2:1"],
                },
            },
        ]

    def get_all(self, with_vectors: bool = True, with_payload: bool = True):
        """记录读取参数并返回 fake Qdrant entries。"""

        self.get_all_calls.append(
            {"with_vectors": with_vectors, "with_payload": with_payload}
        )
        return self.entries

    def exists(self, item_id: str) -> bool:
        """按 id 检查本地条目。"""

        return any(entry["id"] == item_id for entry in self.entries)

    def insert(self, *, vectors, payloads, ids) -> None:
        """模拟官方 Qdrant 的本地向量插入。"""

        self.entries.extend(
            {"id": item_id, "vector": vector, "payload": payload}
            for item_id, vector, payload in zip(ids, vectors, payloads)
        )

    def search(
        self,
        query_vector,
        limit: int = 5,
        filters=None,
        exclude_ids=None,
        return_full: bool = False,
    ):
        """模拟官方 Qdrant retriever 的 search（cosine top-k，返回带 payload 结果）。

        与 LightMemory.retrieve 内部调用 embedding_retriever.search 的行为一致：
        按 cosine 相似度排序，返回前 limit 条，return_full=True 时带 payload。
        """

        self.search_calls.append(
            {
                "limit": limit,
                "filters": filters,
                "return_full": return_full,
            }
        )
        scored: list[tuple[float, dict[str, object]]] = []
        for entry in self.entries:
            vec = entry.get("vector")
            if vec is None:
                continue
            dot = sum(a * b for a, b in zip(query_vector, vec))
            query_norm = sum(a * a for a in query_vector) ** 0.5
            vec_norm = sum(b * b for b in vec) ** 0.5
            score = dot / (query_norm * vec_norm) if query_norm and vec_norm else 0.0
            scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {"id": entry["id"], "score": score, "payload": entry["payload"]}
            for score, entry in scored[:limit]
        ]


class FakeLightMemManager:
    """模拟 LightMem 官方 memory manager 的 LLM 入口。"""

    def __init__(self) -> None:
        """初始化调用记录。"""

        self.calls: list[dict[str, object]] = []

    def generate_response(self, **kwargs):
        """返回 OpenAI manager 风格的文本和 usage_info。"""

        self.calls.append(kwargs)
        return "[]", {
            "prompt_tokens": 23,
            "completion_tokens": 7,
            "total_tokens": 30,
        }


class FakeLightMemAnswerClient:
    """模拟回答 LLM。"""

    def __init__(self) -> None:
        """初始化 fake prompt 调用记录。"""

        self.prompts: list[str] = []

    def create_answer(self, prompt: str) -> str:
        """记录 prompt 并返回固定答案。"""

        self.prompts.append(prompt)
        return "fake lightmem answer"


class FakeLightMemAnswerClientWithUsage(FakeLightMemAnswerClient):
    """模拟能暴露 API usage 的 LightMem reader client。"""

    def create_answer(self, prompt: str) -> str:
        """返回答案并暴露最近一次 API usage。"""

        answer = super().create_answer(prompt)
        self.last_usage = SimpleNamespace(prompt_tokens=13, completion_tokens=5)
        return answer


class FakeOfficialLightMemory:
    """模拟官方 LightMemory.from_config() 入口，避免加载模型和触网。"""

    created_configs: list[dict[str, object]] = []

    @classmethod
    def from_config(cls, config):
        """记录官方 backend 构造配置，并返回可写入和检索的 fake backend。"""

        cls.created_configs.append(config)
        return FakeLightMemoryBackend()


def _snapshot_lightmem_backend_calls(system: LightMem) -> list[dict[str, object]]:
    """把 LightMem backend 调用归一化为可比较序列。"""

    if not system._backends:
        return []
    backend = next(iter(system._backends.values()))
    calls: list[dict[str, object]] = []
    for call in backend.added_messages:
        kwargs = dict(call["kwargs"])
        calls.append(
            {
                "op": "add_memory",
                "messages": call["messages"],
                "force_segment": kwargs.get("force_segment"),
                "force_extract": kwargs.get("force_extract"),
                "metadata_prompt": bool(kwargs.get("METADATA_GENERATE_PROMPT")),
            }
        )
    for call in backend.construct_update_calls:
        calls.append({"op": "construct_update", "kwargs": call})
    for call in backend.offline_update_calls:
        calls.append({"op": "offline_update", "kwargs": call})
    for call in backend.queries:
        calls.append(
            {
                "op": "retrieve",
                "query": call["query"],
                "limit": call["limit"],
                "filters": call["filters"],
            }
        )
    for text in backend.text_embedder.embedded_texts:
        calls.append({"op": "embed_query", "query": text})
    for call in backend.embedding_retriever.search_calls:
        calls.append({"op": "search", "kwargs": call})
    return calls


def _lightmem_conversation() -> Conversation:
    """构造最小 LoCoMo 风格 conversation-QA 样本。"""

    question = Question(
        question_id="q-1",
        conversation_id="conv-1",
        text="What does Alice like?",
    )
    return Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="s-1",
                session_time="2026-01-01",
                turns=[
                    Turn(turn_id="t-1", speaker="Alice", content="I like tea."),
                    Turn(turn_id="t-2", speaker="Bob", content="I will remember that."),
                ],
            )
        ],
        questions=[question],
        metadata={
            "source_path": "data/locomo/locomo10.json",
            "speaker_a": "Alice",
            "speaker_b": "Bob",
        },
    )


def _locomo_style_lightmem_conversation() -> Conversation:
    """构造 LoCoMo 风格多 turn 样本。

    LightMem 的 LoCoMo 脚本会把每条原始发言转成
    `user(content)+assistant("")`，因此四条原始 turn 应产生四次
    `add_memory()` 调用。
    """

    question = Question(
        question_id="q-locomo",
        conversation_id="conv-locomo",
        text="What does Alice like?",
    )
    return Conversation(
        conversation_id="conv-locomo",
        sessions=[
            Session(
                session_id="s-1",
                session_time="2026-01-01",
                turns=[
                    Turn(turn_id="t-1", speaker="Alice", content="I like tea."),
                    Turn(turn_id="t-2", speaker="Bob", content="I will remember tea."),
                ],
            ),
            Session(
                session_id="s-2",
                session_time="2026-01-02",
                turns=[
                    Turn(turn_id="t-3", speaker="Alice", content="I also like jazz."),
                    Turn(turn_id="t-4", speaker="Bob", content="Jazz is noted."),
                ],
            ),
        ],
        questions=[question],
        metadata={
            "source_path": "data/locomo/locomo10.json",
            "speaker_a": "Alice",
            "speaker_b": "Bob",
        },
    )


def _longmemeval_style_lightmem_conversation() -> Conversation:
    """构造 LongMemEval 风格 user/assistant pair 样本。

    LongMemEval 官方脚本会跳过开头非 user 消息，然后按真实
    `user+assistant` pair 逐组调用 `add_memory()`。
    """

    question = Question(
        question_id="q-long",
        conversation_id="conv-long",
        text="What does Alice like?",
        question_time="2026-01-03",
    )
    return Conversation(
        conversation_id="conv-long",
        sessions=[
            Session(
                session_id="s-1",
                session_time="2026-01-01",
                turns=[
                    Turn(
                        turn_id="t-1",
                        speaker="user",
                        normalized_role="user",
                        content="I like tea.",
                    ),
                    Turn(
                        turn_id="t-2",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="Tea is noted.",
                    ),
                ],
            ),
            Session(
                session_id="s-2",
                session_time="2026-01-02",
                turns=[
                    Turn(
                        turn_id="t-3",
                        speaker="user",
                        normalized_role="user",
                        content="I also like jazz.",
                    ),
                    Turn(
                        turn_id="t-4",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="Jazz is noted.",
                    ),
                ],
            ),
        ],
        questions=[question],
        metadata={
            "source_path": "data/longmemeval/longmemeval_s_cleaned.json",
            "variant": "s_cleaned",
        },
    )


@pytest.mark.parametrize(
    ("raw_timestamp", "expected"),
    [
        ("March-15-2024", "2024-03-15T00:00:00"),
        ("July-01-2024", "2024-07-01T00:00:00"),
        ("Smarch-15-2024", "Smarch-15-2024"),
        ("1:56 pm on 8 May, 2023", "2023/05/08 (Mon) 13:56"),
        ("2024-04-02T08:30:00", "2024-04-02T08:30:00"),
    ],
)
def test_lightmem_turn_timestamp_adapts_month_name_dates_without_mutating_source(
    raw_timestamp: str,
    expected: str,
) -> None:
    """月名日期应在 adapter 消息侧转 ISO，原 canonical 时间仍可审计。"""

    turn = Turn(
        turn_id="s1:t1",
        speaker="user",
        content="Real BEAM-shaped turn.",
        turn_time=raw_timestamp,
    )
    session = Session(session_id="s1", turns=[turn], session_time=raw_timestamp)

    assert _turn_timestamp(turn, session) == expected
    assert turn.turn_time == raw_timestamp
    assert session.session_time == raw_timestamp


def test_lightmem_turn_timestamp_keeps_missing_time_fail_fast() -> None:
    """完全无时间时应维持既有 ConfigurationError，不伪造默认日期。"""

    turn = Turn(turn_id="s1:t1", speaker="user", content="Missing timestamp.")
    session = Session(session_id="s1", turns=[turn])

    with pytest.raises(ConfigurationError, match="requires turn_time or session_time"):
        _turn_timestamp(turn, session)


def test_lightmem_turn_timestamp_preserve_none_returns_none_for_missing_time() -> None:
    """preserve_none 下完全无时间应返回 None（原样透传），不伪造时间也不报错。"""

    turn = Turn(turn_id="s1:t1", speaker="user", content="Missing timestamp noise.")
    session = Session(session_id="s1", turns=[turn])

    assert _turn_timestamp(turn, session, "preserve_none") is None
    # 有时间时不受 policy 影响，仍按官方格式转换。
    timed_turn = Turn(
        turn_id="s1:t2",
        speaker="user",
        content="Timed.",
        turn_time="March-15-2024",
    )
    timed_session = Session(session_id="s1", turns=[timed_turn])
    assert (
        _turn_timestamp(timed_turn, timed_session, "preserve_none")
        == "2024-03-15T00:00:00"
    )


def test_lightmem_turn_timestamp_preserve_none_rejects_empty_string_without_fallback() -> None:
    """R1-2：preserve_none 只对双 None 返回 None；来源含空字符串且无可用非空 fallback
    时仍抛错，不把坏数据静默正规化成缺失值。"""

    # turn_time="" 空串 + session_time=None：无可用非空 fallback → 抛错
    turn_empty = Turn(turn_id="s1:t1", speaker="user", content="x", turn_time="")
    session_none = Session(session_id="s1", turns=[turn_empty], session_time=None)
    with pytest.raises(ConfigurationError, match="requires turn_time or session_time"):
        _turn_timestamp(turn_empty, session_none, "preserve_none")

    # turn_time=None + session_time="" 空串：同样抛错
    turn_none = Turn(turn_id="s1:t2", speaker="user", content="y")
    session_empty = Session(session_id="s1", turns=[turn_none], session_time="")
    with pytest.raises(ConfigurationError, match="requires turn_time or session_time"):
        _turn_timestamp(turn_none, session_empty, "preserve_none")


def test_lightmem_turn_timestamp_preserve_none_uses_session_fallback_for_empty_turn() -> None:
    """R1-2：空 turn_time + 合法 session_time 仍按既有优先级回落到 session。"""

    turn = Turn(turn_id="s1:t1", speaker="user", content="x", turn_time="")
    session = Session(session_id="s1", turns=[turn], session_time="2023-05-20")

    assert _turn_timestamp(turn, session, "preserve_none") == "2023-05-20"


def _missing_time_config(
    *,
    lifecycle_profile: str = "online_soft",
    missing_timestamp_policy: str = "preserve_none",
) -> LightMemConfig:
    """构造缺失时间兼容测试用的 LightMemConfig。"""

    return LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=60,
        max_workers=1,
        profile_name="missing-time",
        lifecycle_profile=lifecycle_profile,
        missing_timestamp_policy=missing_timestamp_policy,
    )


def _missing_time_locomo_conversation() -> Conversation:
    """构造含无时间 noise turn 的 MemBench 风格 conversation。

    turn_time/session_time 均为 None（缺失就诚实保持缺失），content 内嵌 place 但无
    时间，用于验证 online-soft 下缺失时间原样透传、content 完整保留。
    """

    question = Question(
        question_id="q-missing",
        conversation_id="conv-missing",
        text="Where did the meetup happen?",
    )
    return Conversation(
        conversation_id="conv-missing",
        sessions=[
            Session(
                session_id="s-1",
                session_time=None,
                turns=[
                    Turn(
                        turn_id="t-noise-1",
                        speaker="user",
                        normalized_role="user",
                        content="We met at the harbor cafe near Pier 39.",
                        turn_time=None,
                    ),
                ],
            )
        ],
        questions=[question],
        metadata={
            "source_path": "data/membench/membench_100k.json",
            "speaker_a": "user",
            "speaker_b": "assistant",
        },
    )


def test_lightmem_config_rejects_preserve_none_with_consolidated_profile() -> None:
    """preserve_none 只允许与 online_soft 组合，consolidated 补充轨须在构造期被拒绝。"""

    with pytest.raises(ConfigurationError, match="preserve_none"):
        _missing_time_config(
            lifecycle_profile="locomo_offline_consolidated",
            missing_timestamp_policy="preserve_none",
        )


def _lightmem_evidence_system(
    *,
    lifecycle_profile: str = "online_soft",
    benchmark_name: str | None = "locomo",
) -> LightMem:
    """构造只用于 evidence 断言的轻量 LightMem 实例，不触发真实 API。"""

    missing_policy = (
        "require" if lifecycle_profile == "locomo_offline_consolidated" else "preserve_none"
    )
    return LightMem(
        config=_missing_time_config(
            lifecycle_profile=lifecycle_profile,
            missing_timestamp_policy=missing_policy,
        ),
        backend_factory=lambda _conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name=benchmark_name,
    )


def test_lightmem_online_soft_evidence_depends_on_items_lineage() -> None:
    """online_soft：items=() 真实 0 hit 仍 valid(turn)，items=None 缺 lineage 记 n_a。"""

    system = _lightmem_evidence_system(benchmark_name="locomo")

    empty_hit = system._build_retrieval_evidence(())
    assert empty_hit.semantic_provenance.status == "valid"
    assert empty_hit.provenance_granularity == "turn"

    populated = system._build_retrieval_evidence(
        (RetrievedItem(item_id="m1", content="c", score=None, timestamp=None),)
    )
    assert populated.semantic_provenance.status == "valid"
    assert populated.provenance_granularity == "turn"

    incomplete = system._build_retrieval_evidence(None)
    assert incomplete.semantic_provenance.status == "n_a"
    assert (
        incomplete.semantic_provenance.reason_code == "retrieval_hit_lineage_incomplete"
    )
    assert incomplete.provenance_granularity == "none"


def test_lightmem_consolidated_evidence_is_na_even_with_complete_items() -> None:
    """locomo_offline_consolidated：即使 items 完整也恒为 n_a（无 output-to-source map）。"""

    system = _lightmem_evidence_system(
        lifecycle_profile="locomo_offline_consolidated",
        benchmark_name="locomo",
    )
    evidence = system._build_retrieval_evidence(
        (RetrievedItem(item_id="m1", content="c", score=None, timestamp=None),)
    )
    assert evidence.semantic_provenance.status == "n_a"
    assert (
        evidence.semantic_provenance.reason_code
        == "semantic_mapping_unavailable_after_mutation"
    )
    assert evidence.provenance_granularity == "none"


def test_lightmem_missing_benchmark_identity_is_pending() -> None:
    """benchmark_name 缺失时 online_soft 也只能 pending，不静态按 benchmark 写死。"""

    system = _lightmem_evidence_system(benchmark_name=None)
    evidence = system._build_retrieval_evidence(())
    assert evidence.semantic_provenance.status == "pending"
    assert evidence.semantic_provenance.reason_code == "benchmark_identity_missing"
    assert evidence.provenance_granularity == "none"


def test_lightmem_stable_ranking_is_pending() -> None:
    """LightMem stable_ranking 未审计，一律 pending。"""

    evidence = _lightmem_evidence_system()._build_retrieval_evidence(())
    assert evidence.stable_ranking.status == "pending"
    assert evidence.stable_ranking.reason_code == "ranking_fidelity_not_audited"


def test_lightmem_config_rejects_unknown_missing_timestamp_policy() -> None:
    """missing_timestamp_policy 只接受 preserve_none 与 require 两个值。"""

    with pytest.raises(ConfigurationError, match="missing_timestamp_policy"):
        _missing_time_config(missing_timestamp_policy="skip")


def test_lightmem_normalizer_preserves_none_alongside_timestamped_message() -> None:
    """真实 MessageNormalizer 混合 timestamped 与 None message：前者保持既有 ISO/
    weekday，后者三个时间字段为空且 content/external_id 完整。"""

    import_lightmem_classes(load_path_settings())
    normalizer_class = sys.modules["lightmem.memory.lightmem"].MessageNormalizer

    normalized = normalizer_class().normalize_messages(
        [
            {
                "role": "user",
                "content": "Timed message.",
                "external_id": "e1",
                "time_stamp": "2023/05/20 (Sat) 00:44",
            },
            {
                "role": "user",
                "content": "Noise at Pier 39.",
                "external_id": "e2",
                "time_stamp": None,
            },
        ]
    )

    assert normalized[0]["time_stamp"] == "2023-05-20T00:44:00.000"
    assert normalized[0]["weekday"] == "Sat"
    assert normalized[0]["session_time"] == "2023/05/20 (Sat) 00:44"
    assert normalized[0]["external_id"] == "e1"

    assert normalized[1]["time_stamp"] is None
    assert normalized[1]["session_time"] is None
    assert normalized[1]["weekday"] is None
    assert normalized[1]["content"] == "Noise at Pier 39."
    assert normalized[1]["external_id"] == "e2"


def test_lightmem_normalizer_rejects_missing_key_and_empty_string() -> None:
    """R1-1：只有显式 time_stamp=None 走 preserve 分支；缺键与空字符串仍按 upstream
    原逻辑报错，不被静默当成缺失时间。"""

    import_lightmem_classes(load_path_settings())
    normalizer_class = sys.modules["lightmem.memory.lightmem"].MessageNormalizer

    # 根本没有 time_stamp 键 → 拒绝
    with pytest.raises(ValueError):
        normalizer_class().normalize_messages(
            [{"role": "user", "content": "no time_stamp key", "external_id": "e1"}]
        )

    # time_stamp 为空字符串 → 拒绝
    with pytest.raises(ValueError):
        normalizer_class().normalize_messages(
            [
                {
                    "role": "user",
                    "content": "empty time_stamp",
                    "external_id": "e2",
                    "time_stamp": "",
                }
            ]
        )


def test_lightmem_sequence_assignment_keeps_none_group_aligned() -> None:
    """assign_sequence_numbers_with_timestamps 混合时/无时消息：不解析 None 分组，
    但仍按原顺序分配 sequence_number，五条并行数组保持索引对齐。"""

    import_lightmem_classes(load_path_settings())
    lm_utils = sys.modules["lightmem.memory.utils"]

    msg_timed = {
        "role": "user",
        "content": "Timed",
        "session_time": "2023-05-20",
        "time_stamp": "placeholder",
        "weekday": "Sat",
        "speaker_id": "A",
        "speaker_name": "Alice",
        "external_id": "e1",
    }
    msg_none = {
        "role": "user",
        "content": "Noise",
        "session_time": None,
        "time_stamp": None,
        "weekday": None,
        "speaker_id": "B",
        "speaker_name": "Bob",
        "external_id": "e2",
    }
    extract_list = [[[msg_timed, msg_none]]]

    (
        _new_extract,
        timestamps_list,
        weekday_list,
        speaker_list,
        external_ids,
        _seq_to_topic,
        _source_external_ids_list,
    ) = lm_utils.assign_sequence_numbers_with_timestamps(
        extract_list, offset_ms=500, topic_id_mapping=[[0]]
    )

    assert msg_timed["sequence_number"] == 0
    assert msg_none["sequence_number"] == 1
    assert timestamps_list[0].startswith("2023-05-20T00:00:00")
    assert timestamps_list[1] is None
    assert weekday_list == ["Sat", None]
    assert [info["speaker_id"] for info in speaker_list] == ["A", "B"]
    assert external_ids == ["e1", "e2"]


def test_lightmem_memory_entry_from_missing_time_keeps_lineage() -> None:
    """timestamp 为 None 时 MemoryEntry 的 timestamp/float 为 None，但 speaker、
    topic、source_external_id 完整（不被宽 catch 连带清空）。"""

    import_lightmem_classes(load_path_settings())
    lm_utils = sys.modules["lightmem.memory.utils"]

    mem = lm_utils._create_memory_entry_from_fact(
        {"source_id": 0, "fact": "harbor cafe noise"},
        timestamps_list=[None],
        weekday_list=[None],
        speaker_list=[{"speaker_id": "B", "speaker_name": "Bob"}],
        topic_id=7,
        external_ids=["e2"],
    )

    assert mem is not None
    assert mem.time_stamp is None
    assert mem.float_time_stamp is None
    assert mem.speaker_id == "B"
    assert mem.speaker_name == "Bob"
    assert mem.topic_id == 7
    assert mem.source_external_id == "e2"
    assert mem.memory == "harbor cafe noise"


def test_lightmem_memory_entry_time_fields_are_optional() -> None:
    """R1-3：MemoryEntry 真实存储 None，因此 time_stamp/float_time_stamp/weekday 的
    annotation 必须是 Optional，让类型声明与运行时值一致。"""

    from typing import get_args, get_type_hints

    import_lightmem_classes(load_path_settings())
    lm_utils = sys.modules["lightmem.memory.utils"]

    hints = get_type_hints(lm_utils.MemoryEntry)
    for field_name in ("time_stamp", "float_time_stamp", "weekday"):
        assert type(None) in get_args(hints[field_name]), (
            f"MemoryEntry.{field_name} must be Optional"
        )


def test_lightmem_vendored_retrieve_omits_time_label_for_null_payload() -> None:
    """项目 fake retriever direct insert 接受 null payload，向量 retrieve 仍按 score
    返回；缺时间的格式化结果只含 memory 文本，不出现字面量 'None None'。"""

    import_lightmem_classes(load_path_settings())
    lightmem_module = sys.modules["lightmem.memory.lightmem"]
    lightmemory_class = lightmem_module.LightMemory

    class _NullPayloadRetriever:
        """返回一个 null-timestamp payload 与一个 timestamped payload 的 fake retriever。"""

        def search(self, query_vector, limit=10, filters=None, return_full=False):
            """按预置顺序返回带 payload 的检索结果。"""

            return [
                {
                    "id": "m-null",
                    "score": 0.9,
                    "payload": {
                        "time_stamp": None,
                        "weekday": None,
                        "memory": "noise at harbor cafe",
                    },
                },
                {
                    "id": "m-timed",
                    "score": 0.5,
                    "payload": {
                        "time_stamp": "2023-05-20T00:00:00.000",
                        "weekday": "Sat",
                        "memory": "timed memory",
                    },
                },
            ]

    stub = SimpleNamespace(
        text_embedder=FakeLightMemEmbedder(),
        embedding_retriever=_NullPayloadRetriever(),
        logger=logging.getLogger("test-lightmem-retrieve"),
    )

    formatted = lightmemory_class.retrieve(stub, "where did we meet?", limit=5)

    assert formatted[0] == "noise at harbor cafe"
    assert formatted[1] == "2023-05-20T00:00:00.000 Sat timed memory"
    assert "None None" not in "\n".join(formatted)


def test_lightmem_online_soft_preserve_none_passes_missing_time_to_backend() -> None:
    """online_soft + preserve_none 下，MemBench-like 无时间 noise 在 bridge 与 native
    两条路径都不被过滤：完整 content + time_stamp=None 到 backend，零 synthetic time。"""

    conversation = _missing_time_locomo_conversation()

    # bridge / legacy add 路径
    bridge_backend = FakeLightMemoryBackend()
    bridge_system = LightMem(
        config=_missing_time_config(),
        backend_factory=lambda _conversation_id: bridge_backend,
        answer_client=FakeLightMemAnswerClient(),
    )
    bridge_system.add([conversation])
    bridge_messages = [
        message
        for call in bridge_backend.added_messages
        for message in call["messages"]
    ]
    assert bridge_messages
    assert all(message["time_stamp"] is None for message in bridge_messages)
    assert any("harbor cafe" in message["content"] for message in bridge_messages)

    # native v3 ingest 路径
    native_backend = FakeLightMemoryBackend()
    native_system = LightMem(
        config=_missing_time_config(),
        backend_factory=lambda _conversation_id: native_backend,
        answer_client=FakeLightMemAnswerClient(),
    )
    isolation_key = "conv-missing"
    events = tuple(build_turn_events(conversation, isolation_key))
    for signal in GranularityAggregator("turn").aggregate(
        events, isolation_key=isolation_key
    ):
        if isinstance(signal, TurnEvent):
            native_system.ingest(signal)
        elif isinstance(signal, SessionRef):
            native_system.end_session(signal)
        elif isinstance(signal, UnitRef):
            native_system.end_conversation(signal)
    native_messages = [
        message
        for call in native_backend.added_messages
        for message in call["messages"]
    ]
    assert native_messages
    assert all(message["time_stamp"] is None for message in native_messages)
    assert any("harbor cafe" in message["content"] for message in native_messages)


def test_lightmem_require_policy_fails_before_backend_creation() -> None:
    """missing_timestamp_policy=require 时，legacy 与 native 缺失输入都在 backend
    工厂计数仍为 0 时 fail-fast。"""

    conversation = _missing_time_locomo_conversation()

    factory_calls = {"count": 0}

    def _counting_factory(_conversation_id: str) -> FakeLightMemoryBackend:
        """记录 backend 工厂被调用次数。"""

        factory_calls["count"] += 1
        return FakeLightMemoryBackend()

    # legacy add 路径
    legacy_system = LightMem(
        config=_missing_time_config(missing_timestamp_policy="require"),
        backend_factory=_counting_factory,
        answer_client=FakeLightMemAnswerClient(),
    )
    with pytest.raises(ConfigurationError, match="requires turn_time or session_time"):
        legacy_system.add([conversation])
    assert factory_calls["count"] == 0

    # native ingest 路径
    native_system = LightMem(
        config=_missing_time_config(missing_timestamp_policy="require"),
        backend_factory=_counting_factory,
        answer_client=FakeLightMemAnswerClient(),
    )
    events = tuple(build_turn_events(conversation, "conv-missing"))
    first_event = events[0]
    with pytest.raises(ConfigurationError, match="requires turn_time or session_time"):
        native_system.ingest(first_event)
    assert factory_calls["count"] == 0


@pytest.mark.parametrize("raw_timestamp", ["March-15-2024", "July-01-2024"])
def test_lightmem_month_name_timestamp_is_accepted_by_official_normalizer(
    raw_timestamp: str,
) -> None:
    """真实 BEAM anchor 转换后应通过官方 MessageNormalizer 的离线解析。"""

    import_lightmem_classes(load_path_settings())
    normalizer_class = sys.modules["lightmem.memory.lightmem"].MessageNormalizer
    turn = Turn(
        turn_id="s1:t1",
        speaker="user",
        content="Real BEAM-shaped turn.",
        turn_time=raw_timestamp,
    )
    session = Session(session_id="s1", turns=[turn], session_time=raw_timestamp)

    normalized = normalizer_class().normalize_messages(
        [
            {
                "role": "user",
                "content": turn.content,
                "time_stamp": _turn_timestamp(turn, session),
            }
        ]
    )

    assert normalized[0]["time_stamp"].endswith("T00:00:00.000")
    assert normalized[0]["session_time"] == _turn_timestamp(turn, session)
    assert turn.turn_time == raw_timestamp


def test_lightmem_external_id_survives_official_preprocessing_pipeline() -> None:
    """公开 external_id 应穿过 normalizer、压缩和两级 buffer。"""

    import_lightmem_classes(load_path_settings())
    from lightmem.factory.memory_buffer.sensory_memory import SenMemBufferManager
    from lightmem.factory.memory_buffer.short_term_memory import ShortMemBufferManager
    from lightmem.factory.pre_compressor.llmlingua_2 import LlmLingua2Compressor

    class _Tokenizer:
        """为官方 buffer 提供稳定的离线 token 计数。"""

        def encode(self, text: str) -> list[str]:
            """按空白切分测试文本。"""

            return text.split()

    class _PromptCompressor:
        """模拟 LLMLingua 内核，仅改变 content。"""

        def compress_prompt(self, **kwargs):
            """返回固定压缩文本。"""

            return {"compressed_prompt": f"compressed {kwargs['context'][0]}"}

    class _Segmenter:
        """让 sensory buffer 以原消息字典切出单段。"""

        def propose_cut(self, _buffer_texts):
            """空边界触发官方整段 copy 路径。"""

            return []

    normalizer_class = sys.modules["lightmem.memory.lightmem"].MessageNormalizer
    messages = [
        {
            "role": "user",
            "content": "Alice likes tea.",
            "time_stamp": "2026-01-01T00:00:00",
            "external_id": "D1:1",
        },
        {
            "role": "assistant",
            "content": "Tea is noted.",
            "time_stamp": "2026-01-01T00:00:00",
            "external_id": "D1:2",
        },
    ]
    normalized = normalizer_class(offset_ms=500).normalize_messages(messages)
    compressor = LlmLingua2Compressor.__new__(LlmLingua2Compressor)
    compressor.config = SimpleNamespace(compress_config={})
    compressor._compressor = _PromptCompressor()
    compressed = compressor.compress(normalized, _Tokenizer())
    sensory = SenMemBufferManager(max_tokens=512, tokenizer=_Tokenizer())
    assert sensory.add_messages(compressed, _Segmenter(), None) == []
    segments = sensory.cut_with_segmenter(_Segmenter(), None, force_segment=True)
    short = ShortMemBufferManager(max_tokens=2000, tokenizer=_Tokenizer())
    trigger_count, extract_list = short.add_segments(
        segments,
        messages_use="user_only",
        force_extract=True,
    )

    assert trigger_count == 1
    assert [message["external_id"] for message in extract_list[0][0]] == [
        "D1:1",
        "D1:2",
    ]


def test_lightmem_external_id_survives_topic_segment_disabled_path() -> None:
    """关闭 topic segmentation 时早退消息也必须保留 external_id。"""

    classes = import_lightmem_classes(load_path_settings())

    class _Logger:
        """提供官方早退路径使用的无输出 logger。"""

        def __getattr__(self, _name):
            """所有日志级别都返回空操作。"""

            return lambda *_args, **_kwargs: None

    backend = classes["LightMemory"].__new__(classes["LightMemory"])
    backend.config = SimpleNamespace(
        extraction_mode="flat",
        pre_compress=False,
        topic_segment=False,
    )
    backend.logger = _Logger()

    result = backend.add_memory(
        [
            {
                "role": "user",
                "content": "Alice likes tea.",
                "time_stamp": "2026-01-01T00:00:00",
                "external_id": "D1:1",
            }
        ]
    )

    assert result["emitted_messages"][0]["external_id"] == "D1:1"


def test_lightmem_conversion_and_storage_conditionally_preserve_external_id(
    tmp_path: Path,
) -> None:
    """抽取来源应进入 MemoryEntry；缺来源时旧序列化键集合保持不变。"""

    import_lightmem_classes(load_path_settings())
    utils = sys.modules["lightmem.memory.utils"]
    extracted_results = [
        {
            "cleaned_result": [
                [{"source_id": 0, "fact": "Alice likes tea."}],
            ]
        }
    ]
    common = {
        "extracted_results": extracted_results,
        "timestamps_list": [
            "2026-01-01T00:00:00.000",
            "2026-01-01T00:00:00.500",
        ],
        "weekday_list": ["Thu", "Thu"],
        "speaker_list": [
            {"speaker_id": "speaker_a", "speaker_name": "Alice"},
            {"speaker_id": "speaker_a", "speaker_name": "Alice"},
        ],
        "topic_id_map": {0: 7, 1: 7},
        "max_source_ids": [0],
        "logger": SimpleNamespace(
            warning=lambda *_args, **_kwargs: None,
            error=lambda *_args, **_kwargs: None,
        ),
    }

    with_source = utils.convert_extraction_results_to_memory_entries(
        **common,
        external_ids=["D1:1", "D1:1"],
    )[0]
    without_source = utils.convert_extraction_results_to_memory_entries(**common)[0]

    assert with_source.source_external_id == "D1:1"
    assert without_source.source_external_id is None
    old_shape_path = tmp_path / "old-shape.json"
    utils.save_memory_entries([without_source], old_shape_path)
    old_shape = json.loads(old_shape_path.read_text(encoding="utf-8"))[0]
    assert old_shape == {
        "id": without_source.id,
        "time_stamp": "2026-01-01T00:00:00.000",
        "topic_id": 7,
        "topic_summary": "",
        "category": "",
        "subcategory": "",
        "memory_class": "",
        "memory": "Alice likes tea.",
        "original_memory": "",
        "compressed_memory": "",
        "hit_time": 0,
        "update_queue": [],
        "float_time_stamp": without_source.float_time_stamp,
        "weekday": "Thu",
        "speaker_id": "speaker_a",
        "speaker_name": "Alice",
        "consolidated": False,
    }
    with_source_path = tmp_path / "with-source.json"
    utils.save_memory_entries([with_source], with_source_path)
    assert json.loads(with_source_path.read_text(encoding="utf-8"))[0][
        "source_external_id"
    ] == "D1:1"


def test_lightmem_offline_update_conditionally_writes_external_id_payload() -> None:
    """embedding payload 仅在 MemoryEntry 有公开来源时新增来源键。"""

    classes = import_lightmem_classes(load_path_settings())
    utils = sys.modules["lightmem.memory.utils"]

    class _Retriever:
        """记录官方 offline_update 的本地向量写入 payload。"""

        def __init__(self) -> None:
            """初始化插入记录。"""

            self.payloads: list[dict[str, object]] = []

        def exists(self, _item_id: str) -> bool:
            """测试 id 均不冲突。"""

            return False

        def insert(self, *, vectors, payloads, ids) -> None:
            """记录条件 payload，不执行外部 I/O。"""

            assert vectors and ids
            self.payloads.extend(payloads)

    retriever = _Retriever()
    backend = classes["LightMemory"].__new__(classes["LightMemory"])
    backend.config = SimpleNamespace(index_strategy="embedding")
    backend.logger = SimpleNamespace(
        info=lambda *_args, **_kwargs: None,
        debug=lambda *_args, **_kwargs: None,
    )
    backend.text_embedder = SimpleNamespace(embed=lambda _text: [1.0, 0.0])
    backend.embedding_retriever = retriever
    entries = [
        utils.MemoryEntry(memory="with source", source_external_id="D1:1"),
        utils.MemoryEntry(memory="without source"),
    ]

    backend.offline_update(entries)

    assert retriever.payloads[0]["source_external_id"] == "D1:1"
    assert "source_external_id" not in retriever.payloads[1]


def test_lightmem_local_retrieval_provenance_scores_locomo_recall(
    tmp_path: Path,
) -> None:
    """MemoryEntry 经本地向量链检索后应产出可评分的 canonical turn id。"""

    from memory_benchmark.core import (
        GoldAnswerInfo,
        GoldEvidenceGroup,
        GoldEvidenceGroupSet,
    )
    from memory_benchmark.evaluators.locomo_recall import (
        LoCoMoRetrievalRecallEvaluator,
    )
    from memory_benchmark.storage import (
        ExperimentPaths,
        atomic_write_jsonl,
        evaluator_private_label_record,
        public_question_record,
    )

    classes = import_lightmem_classes(load_path_settings())
    utils = sys.modules["lightmem.memory.utils"]
    retriever = FakeLightMemEmbeddingRetriever()
    retriever.entries.clear()
    backend = classes["LightMemory"].__new__(classes["LightMemory"])
    backend.config = SimpleNamespace(index_strategy="embedding")
    backend.logger = SimpleNamespace(
        info=lambda *_args, **_kwargs: None,
        debug=lambda *_args, **_kwargs: None,
    )
    backend.text_embedder = FakeLightMemEmbedder()
    backend.embedding_retriever = retriever
    backend.offline_update(
        [
            utils.MemoryEntry(
                id="memory-D1-1",
                time_stamp="2026-01-01T00:00:00.000",
                weekday="Thu",
                memory="Alice likes tea.",
                speaker_name="Alice",
                source_external_id="D1:1",
                source_external_ids=["D1:1"],
            )
        ]
    )
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=1,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda _conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )
    method._backends["conv-1"] = backend
    method._conversation_metadata["conv-1"] = {
        "source_path": "data/locomo/locomo10.json",
        "speaker_a": "Alice",
        "speaker_b": "Bob",
    }
    question = Question(
        question_id="q-1",
        conversation_id="conv-1",
        text="What does Alice like?",
        category="4",
    )

    retrieval = method.retrieve(
        RetrievalQuery(
            query_text=question.text,
            isolation_key="conv-1",
            question_time=question.question_time,
            top_k=1,
            purpose="qa",
            source_question=question,
        )
    )

    assert retrieval.items is not None
    assert retrieval.items[0].source_turn_ids == ("D1:1",)
    paths = ExperimentPaths.create(tmp_path / "run")
    atomic_write_jsonl(
        paths.answer_prompts_path,
        [
            {
                "question_id": "q-1",
                "conversation_id": "conv-1",
                "retrieval_query_top_k": 1,
                "retrieved_items": [asdict(item) for item in retrieval.items],
            }
        ],
    )
    atomic_write_jsonl(
        paths.evaluator_private_labels_path,
        [
            evaluator_private_label_record(
                GoldAnswerInfo(
                    question_id="q-1",
                    answer="tea",
                    evidence=["D1:1"],
                    gold_evidence_contract_version="v1",
                    evidence_group_sets=(
                        GoldEvidenceGroupSet(
                            provenance_granularity="turn",
                            unit_kind="locomo_utterance",
                            groups=(
                                GoldEvidenceGroup(
                                    unit_id="D1:1",
                                    child_ids=("D1:1",),
                                    mapping_status="mapped",
                                ),
                            ),
                        ),
                    ),
                ),
                question.category,
            )
        ],
    )
    atomic_write_jsonl(paths.public_questions_path, [public_question_record(question)])
    result = LoCoMoRetrievalRecallEvaluator().evaluate_run_artifacts(
        paths=paths,
        manifest={
            "benchmark_policy": {"gold_evidence_contract_version": "v1"},
            "method": {"provenance_granularity": "turn"},
        },
    )

    assert result["total_questions"] == 1
    assert result["mean_score"] == 1.0


def _tmp_path_settings(project_root) -> PathSettings:
    """构造只用于资源校验测试的临时项目路径配置。"""

    return PathSettings(
        project_root=project_root,
        data_root=project_root / "data",
        models_root=project_root / "models",
        outputs_root=project_root / "outputs",
        third_party_root=project_root / "third_party",
        third_party_benchmarks_root=project_root / "third_party" / "benchmarks",
        third_party_methods_root=project_root / "third_party" / "methods",
    )


def test_lightmem_local_model_resource_check_reports_missing_paths(tmp_path) -> None:
    """LightMem 真实运行前应明确报出缺失的本地模型路径。"""

    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=60,
        max_workers=1,
        profile_name="smoke",
    )

    with pytest.raises(ConfigurationError, match="LightMem required local model"):
        config.validate_required_local_resources(_tmp_path_settings(tmp_path))


def test_lightmem_local_model_resource_check_accepts_existing_paths(tmp_path) -> None:
    """LightMem 本地模型目录齐全时资源校验应通过。"""

    (tmp_path / "models" / "all-MiniLM-L6-v2").mkdir(parents=True)
    (
        tmp_path
        / "models"
        / "llmlingua-2-bert-base-multilingual-cased-meetingbank"
    ).mkdir(parents=True)
    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=60,
        max_workers=1,
        profile_name="smoke",
    )

    config.validate_required_local_resources(_tmp_path_settings(tmp_path))


def test_lightmem_add_and_get_answer_with_fake_backend() -> None:
    """LightMem wrapper 应能通过统一接口写入 conversation 并回答问题。"""

    backend = FakeLightMemoryBackend()
    chat = FakeLightMemAnswerClient()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=2,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=chat,
        benchmark_name="locomo",
    )
    conversation = _lightmem_conversation()

    add_result = method.add([conversation])
    answer = method.get_answer(conversation.questions[0])

    assert add_result.conversation_ids == ["conv-1"]
    assert isinstance(answer, AnswerResult)
    assert answer.answer == "fake lightmem answer"
    assert backend.queries == []
    assert backend.embedding_retriever.get_all_calls == []
    assert backend.embedding_retriever.search_calls == [
        {"limit": 2, "filters": None, "return_full": True}
    ]
    assert "Alice likes jasmine tea." in chat.prompts[0]
    first_message = backend.added_messages[0]["messages"][0]
    assert first_message["time_stamp"] == "2026-01-01"
    assert "timestamp" not in first_message
    assert first_message["speaker_id"] == "speaker_a"
    assert first_message["speaker_name"] == "Alice"
    assert first_message["role"] == "user"


@pytest.mark.parametrize(
    ("conversation_factory", "native_builder", "expected_message_count", "benchmark_name"),
    (
        (_locomo_style_lightmem_conversation, build_lightmem_locomo_native_answer_prompt, 1, "locomo"),
        (
            _longmemeval_style_lightmem_conversation,
            build_lightmem_longmemeval_native_answer_prompt,
            2,
            "longmemeval",
        ),
    ),
)
def test_lightmem_native_builder_passes_through_adapter_prompt_messages(
    conversation_factory,
    native_builder,
    expected_message_count: int,
    benchmark_name: str,
) -> None:
    """真实 adapter retrieve 到 native builder 应逐字透传官方 prompt messages。"""

    backend = FakeLightMemoryBackend()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=2,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name=benchmark_name,
    )
    conversation = conversation_factory()
    method.add([conversation])
    question = conversation.questions[0]
    retrieval = method.retrieve(
        RetrievalQuery(
            query_text=question.text,
            isolation_key=conversation.conversation_id,
            question_time=question.question_time,
            top_k=2,
            purpose="qa",
            source_question=question,
        )
    )

    result = native_builder(question, retrieval)

    assert len(retrieval.prompt_messages or ()) == expected_message_count
    assert retrieval.metadata["provenance_granularity"] == "turn"
    assert retrieval.items is not None
    assert retrieval.items[0].source_turn_ids == ("D1:1",)
    assert result.prompt_messages == list(retrieval.prompt_messages or ())
    if expected_message_count == 2:
        assert retrieval.formatted_memory not in result.prompt_messages[1].content
        assert "2026-01-01T00:00:00.000 Thu Alice likes jasmine tea." in (
            result.prompt_messages[1].content
        )


def test_lightmem_retrieve_missing_external_id_falls_back_without_error() -> None:
    """旧 payload 缺来源字段时应整次回落 none，不返回部分 provenance。"""

    backend = FakeLightMemoryBackend()
    for entry in backend.embedding_retriever.entries:
        entry["payload"].pop("source_external_id", None)
        entry["payload"].pop("source_external_ids", None)
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=2,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda _conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )
    conversation = _locomo_style_lightmem_conversation()
    method.add([conversation])
    question = conversation.questions[0]

    retrieval = method.retrieve(
        RetrievalQuery(
            query_text=question.text,
            isolation_key=conversation.conversation_id,
            question_time=question.question_time,
            top_k=2,
            purpose="qa",
            source_question=question,
        )
    )

    assert retrieval.items is None
    assert retrieval.metadata["provenance_granularity"] == "none"


def test_lightmem_load_existing_conversation_state_rebuilds_backend() -> None:
    """resume 时 LightMem 应重建 completed conversation 的 backend 以回答剩余问题。"""

    backend = FakeLightMemoryBackend()
    chat = FakeLightMemAnswerClient()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=2,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=chat,
    )
    conversation = _lightmem_conversation()

    method.load_existing_conversation_state(conversation)
    answer = method.get_answer(conversation.questions[0])

    assert answer.answer == "fake lightmem answer"
    assert backend.added_messages == []
    assert backend.embedding_retriever.get_all_calls == []
    assert backend.embedding_retriever.search_calls == [
        {"limit": 2, "filters": None, "return_full": True}
    ]
    assert "Alice likes jasmine tea." in chat.prompts[0]


def test_lightmem_add_uses_locomo_single_turn_incremental_feeding() -> None:
    """LoCoMo 写入应复刻官方脚本的单 turn + 空 assistant 增量喂入。"""

    backend = FakeLightMemoryBackend()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=60,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )

    method.add([_locomo_style_lightmem_conversation()])

    assert len(backend.added_messages) == 4
    first_call = backend.added_messages[0]
    last_call = backend.added_messages[-1]
    assert first_call["kwargs"]["force_segment"] is False
    assert first_call["kwargs"]["force_extract"] is False
    assert last_call["kwargs"]["force_segment"] is True
    assert last_call["kwargs"]["force_extract"] is True
    assert first_call["kwargs"]["METADATA_GENERATE_PROMPT"]
    assert [message["content"] for message in first_call["messages"]] == [
        "I like tea.",
        "",
    ]
    assert [message["role"] for message in first_call["messages"]] == [
        "user",
        "assistant",
    ]
    assert [message["speaker_id"] for message in first_call["messages"]] == [
        "speaker_a",
        "speaker_a",
    ]
    assert [message["time_stamp"] for message in first_call["messages"]] == [
        "2026-01-01",
        "2026-01-01",
    ]
    assert [message["external_id"] for message in first_call["messages"]] == [
        "t-1",
        "t-1",
    ]
    assert [message["content"] for message in last_call["messages"]] == [
        "Jazz is noted.",
        "",
    ]


def test_lightmem_locomo_add_online_soft_skips_offline_update() -> None:
    """online_soft 主 profile（默认）下，LoCoMo legacy add 完成不应触发全库 offline update。"""

    backend = FakeLightMemoryBackend()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=60,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )

    method.add([_locomo_style_lightmem_conversation()])

    assert backend.construct_update_calls == []
    assert backend.offline_update_calls == []


def test_lightmem_locomo_add_offline_consolidated_runs_official_offline_update_after_all_turns() -> None:
    """显式 locomo_offline_consolidated 补充 profile 保留旧的 post-build offline update。"""

    backend = FakeLightMemoryBackend()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=60,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
            lifecycle_profile="locomo_offline_consolidated",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )

    method.add([_locomo_style_lightmem_conversation()])

    assert backend.construct_update_calls == [{}]
    assert backend.offline_update_calls == [{"score_threshold": 0.8}]


def test_lightmem_locomo_offline_consolidated_requires_explicit_locomo_benchmark_identity() -> None:
    """locomo_offline_consolidated 补充 profile 缺失或错误 benchmark identity 时必须在构造期 fail-fast。

    该补充 profile 会在 conversation 末尾触发全库 offline consolidation
    （改写/删除既有 memory entry）；不允许从 conversation 的 source_path 或
    question 字段猜测身份，因此校验必须发生在任何 add()/ingest() 调用之前。
    """

    consolidated_config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=60,
        max_workers=1,
        profile_name="official-mini",
        lifecycle_profile="locomo_offline_consolidated",
    )

    with pytest.raises(ConfigurationError, match="locomo_offline_consolidated"):
        LightMem(
            config=consolidated_config,
            backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
            answer_client=FakeLightMemAnswerClient(),
        )

    with pytest.raises(ConfigurationError, match="locomo_offline_consolidated"):
        LightMem(
            config=consolidated_config,
            backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
            answer_client=FakeLightMemAnswerClient(),
            benchmark_name="longmemeval",
        )

    # 显式声明为非 locomo 补充 profile 缺乏正当用途，本项目当前只支持 LoCoMo；
    # 正确用法（benchmark_name="locomo"）在其他定向测试中覆盖，此处只锁反例。


def test_lightmem_add_uses_longmemeval_user_assistant_pair_feeding() -> None:
    """LongMemEval 写入应复刻官方脚本的真实 user+assistant pair 增量喂入。"""

    backend = FakeLightMemoryBackend()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=20,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
    )

    method.add([_longmemeval_style_lightmem_conversation()])

    assert len(backend.added_messages) == 2
    first_call = backend.added_messages[0]
    second_call = backend.added_messages[1]
    assert first_call["kwargs"]["force_segment"] is False
    assert first_call["kwargs"]["force_extract"] is False
    assert second_call["kwargs"]["force_segment"] is True
    assert second_call["kwargs"]["force_extract"] is True
    assert "METADATA_GENERATE_PROMPT" not in first_call["kwargs"]
    assert [message["content"] for message in first_call["messages"]] == [
        "I like tea.",
        "Tea is noted.",
    ]
    assert [message["role"] for message in first_call["messages"]] == [
        "user",
        "assistant",
    ]
    assert [message["external_id"] for message in first_call["messages"]] == [
        "t-1",
        "t-2",
    ]
    assert backend.construct_update_calls == []
    assert backend.offline_update_calls == []


def test_native_lightmem_locomo_matches_bridge_online_soft_force_sequence() -> None:
    """online_soft 主 profile 下，LightMem 原生 turn 路径应等价复现 LoCoMo force 顺序。

    两条路径都不应触发全库 offline update（§4 required test item 4）。
    """

    conversation = _locomo_style_lightmem_conversation()
    question = conversation.questions[0]
    bridge = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=60,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )
    native = LightMem(
        config=bridge.config,
        backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )

    bridge_result = run_bridge_sequence(
        provider=bridge,
        conversation=conversation,
        question=question,
        run_id="lightmem-equivalence",
        snapshot_calls=_snapshot_lightmem_backend_calls,
    )
    native_result = run_native_sequence(
        provider=native,
        conversation=conversation,
        question=question,
        run_id="lightmem-equivalence",
        snapshot_calls=_snapshot_lightmem_backend_calls,
    )

    assert isinstance(native, MemoryProvider)
    assert bridge_result.calls == native_result.calls
    assert [call["force_extract"] for call in native_result.calls if call["op"] == "add_memory"] == [
        False,
        False,
        False,
        True,
    ]
    add_calls = [call for call in native_result.calls if call["op"] == "add_memory"]
    assert [message["external_id"] for message in add_calls[0]["messages"]] == [
        "t-1",
        "t-1",
    ]
    call_ops = [call["op"] for call in native_result.calls]
    assert "construct_update" not in call_ops
    assert "offline_update" not in call_ops
    assert call_ops[-2:] == ["embed_query", "search"]


def test_native_lightmem_locomo_offline_consolidated_matches_bridge_force_and_update_sequence() -> None:
    """显式 locomo_offline_consolidated 补充 profile 下，原生与桥接路径应等价复现 LoCoMo force 与 post-build 顺序。

    两条路径都应在最后一批后各调用一次 queue/update，且既有 offline
    score_threshold 保持不变（§4 required test item 5）。
    """

    conversation = _locomo_style_lightmem_conversation()
    question = conversation.questions[0]
    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=60,
        max_workers=1,
        compression_rate=0.7,
        stm_threshold=512,
        profile_name="official-mini",
        lifecycle_profile="locomo_offline_consolidated",
    )
    bridge = LightMem(
        config=config,
        backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )
    native = LightMem(
        config=config,
        backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )

    bridge_result = run_bridge_sequence(
        provider=bridge,
        conversation=conversation,
        question=question,
        run_id="lightmem-equivalence",
        snapshot_calls=_snapshot_lightmem_backend_calls,
    )
    native_result = run_native_sequence(
        provider=native,
        conversation=conversation,
        question=question,
        run_id="lightmem-equivalence",
        snapshot_calls=_snapshot_lightmem_backend_calls,
    )

    assert isinstance(native, MemoryProvider)
    assert bridge_result.calls == native_result.calls
    assert [call["op"] for call in native_result.calls[-4:]] == [
        "construct_update",
        "offline_update",
        "embed_query",
        "search",
    ]
    offline_update_calls = [
        call for call in native_result.calls if call["op"] == "offline_update"
    ]
    assert offline_update_calls == [
        {"op": "offline_update", "kwargs": {"score_threshold": 0.8}}
    ]


def test_native_lightmem_longmemeval_matches_bridge_pair_sequence() -> None:
    """LightMem 原生 pair 路径应等价复现 LongMemEval 写入与检索。"""

    conversation = _longmemeval_style_lightmem_conversation()
    question = conversation.questions[0]
    bridge = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=20,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
    )
    native = LightMem(
        config=bridge.config,
        backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        consume_granularity="pair",
    )

    bridge_result = run_bridge_sequence(
        provider=bridge,
        conversation=conversation,
        question=question,
        run_id="lightmem-equivalence",
        snapshot_calls=_snapshot_lightmem_backend_calls,
    )
    native_result = run_native_sequence(
        provider=native,
        conversation=conversation,
        question=question,
        run_id="lightmem-equivalence",
        snapshot_calls=_snapshot_lightmem_backend_calls,
    )

    assert bridge_result.calls == native_result.calls
    assert [call["force_extract"] for call in native_result.calls if call["op"] == "add_memory"] == [
        False,
        True,
    ]
    add_calls = [call for call in native_result.calls if call["op"] == "add_memory"]
    assert [message["external_id"] for message in add_calls[0]["messages"]] == [
        "t-1",
        "t-2",
    ]


@pytest.mark.parametrize(
    ("source_path", "turn_id"),
    [
        ("data/membench/locomo/trajectory.jsonl", "17"),
        ("data/BEAM/beam_dataset", "p1:s1:t1"),
    ],
)
def test_native_lightmem_turn_path_preserves_public_external_id(
    source_path: str,
    turn_id: str,
) -> None:
    """MemBench/BEAM 共用的 v3 turn 路径应透传公开 canonical turn id。"""

    backend = FakeLightMemoryBackend()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=20,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
    )
    conversation = Conversation(
        conversation_id="conv-v3-turn",
        sessions=[
            Session(
                session_id="p1:s1",
                session_time="2024-04-02",
                turns=[
                    Turn(
                        turn_id=turn_id,
                        speaker="user",
                        normalized_role="user",
                        content="Remember this public turn.",
                    )
                ],
            )
        ],
        metadata={"source_path": source_path},
    )
    isolation_key = "run_conv-v3-turn"
    event = next(build_turn_events(conversation, isolation_key))

    method.ingest(event)
    method.end_conversation(UnitRef(isolation_key))

    assert len(backend.added_messages) == 1
    assert [
        message["external_id"]
        for message in backend.added_messages[0]["messages"]
    ] == [turn_id, turn_id]


def test_native_lightmem_longmemeval_assistant_first_skips_orphan_like_official_trim() -> None:
    """assistant 开头 session 的原生 pair 路径必须等价官方整段开头裁剪。

    对照 smoke 抓到的真实回归：LongMemEval 约 8% 的 session 以 assistant
    开头（如 e47becba/sharegpt_qRdLQvN_7），位置两两切分产出反序 pair，
    官方裁剪后剩 1 条 → 奇数报错。user 锚定配对 + orphan 跳过后，原生
    调用序列必须与桥接（官方整段处理）一致。
    """

    question = Question(
        question_id="q-af",
        conversation_id="conv-af",
        text="What does Alice like?",
        question_time="2026-01-03",
    )
    conversation = Conversation(
        conversation_id="conv-af",
        sessions=[
            Session(
                session_id="s-af",
                session_time="2026-01-01",
                turns=[
                    Turn(
                        turn_id="t-0",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="Welcome back!",
                    ),
                    Turn(
                        turn_id="t-1",
                        speaker="user",
                        normalized_role="user",
                        content="I like tea.",
                    ),
                    Turn(
                        turn_id="t-2",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="Tea is noted.",
                    ),
                    Turn(
                        turn_id="t-3",
                        speaker="user",
                        normalized_role="user",
                        content="I also like jazz.",
                    ),
                    Turn(
                        turn_id="t-4",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="Jazz is noted.",
                    ),
                ],
            ),
        ],
        questions=[question],
        metadata={
            "source_path": "data/longmemeval/longmemeval_s_cleaned.json",
            "variant": "s_cleaned",
        },
    )
    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=20,
        max_workers=1,
        compression_rate=0.7,
        stm_threshold=512,
        profile_name="official-mini",
    )
    bridge = LightMem(
        config=config,
        backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="longmemeval",
    )
    native = LightMem(
        config=config,
        backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        consume_granularity="pair",
        benchmark_name="longmemeval",
    )

    bridge_result = run_bridge_sequence(
        provider=bridge,
        conversation=conversation,
        question=question,
        run_id="lightmem-equivalence",
        snapshot_calls=_snapshot_lightmem_backend_calls,
    )
    native_result = run_native_sequence(
        provider=native,
        conversation=conversation,
        question=question,
        run_id="lightmem-equivalence",
        snapshot_calls=_snapshot_lightmem_backend_calls,
    )

    assert bridge_result.calls == native_result.calls
    add_calls = [call for call in native_result.calls if call["op"] == "add_memory"]
    assert len(add_calls) == 3
    assert add_calls[0]["messages"][0].get("memory_benchmark_structural_placeholder") is True
    assert add_calls[0]["messages"][1]["content"] == "Welcome back!"
    assert [message["content"] for message in add_calls[1]["messages"]] == [
        "I like tea.",
        "Tea is noted.",
    ]
    assert [call["force_extract"] for call in add_calls] == [False, False, True]


def test_lightmem_halumem_session_reports_are_incremental_and_force_flushed() -> None:
    """HaluMem 两个 session 的报告必须只含各自窗口内新插入的记忆。"""

    backend = SessionCaptureFakeLightMemoryBackend()
    provider = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=20,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        consume_granularity="session",
        session_memory_report=True,
    )
    conversation = Conversation(
        conversation_id="halumem-user-1",
        sessions=[
            Session(
                session_id="session-a",
                session_time="2025-09-01T10:00:00",
                turns=[
                    Turn(
                        turn_id="session-a:t1",
                        speaker="user",
                        normalized_role="user",
                        content="First session user message.",
                    ),
                    Turn(
                        turn_id="session-a:t2",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="First session assistant message.",
                    ),
                ],
            ),
            Session(
                session_id="session-b",
                session_time="2025-09-02T10:00:00",
                turns=[
                    Turn(
                        turn_id="session-b:t1",
                        speaker="user",
                        normalized_role="user",
                        content="Second session user message.",
                    ),
                    Turn(
                        turn_id="session-b:t2",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="Second session assistant message.",
                    ),
                ],
            ),
        ],
        metadata={"source_path": "data/halumem/HaluMem-Medium.jsonl"},
    )
    isolation_key = "halumem-run_halumem-user-1"
    reports = []

    for signal in GranularityAggregator("session").aggregate(
        build_turn_events(conversation, isolation_key),
        isolation_key=isolation_key,
    ):
        if isinstance(signal, SessionBatch):
            provider.ingest(signal)
        elif isinstance(signal, SessionRef):
            reports.append(provider.end_session(signal))

    assert [call["kwargs"] for call in backend.added_messages] == [
        {"force_segment": True, "force_extract": True},
        {"force_segment": True, "force_extract": True},
    ]
    assert [
        [message["content"] for message in call["messages"]]
        for call in backend.added_messages
    ] == [
        ["First session user message.", "First session assistant message."],
        ["Second session user message.", "Second session assistant message."],
    ]
    assert [
        [message["external_id"] for message in call["messages"]]
        for call in backend.added_messages
    ] == [
        ["session-a:t1", "session-a:t2"],
        ["session-b:t1", "session-b:t2"],
    ]
    assert [report.memories for report in reports if report is not None] == [
        ["session-memory-1"],
        ["session-memory-2"],
    ]
    assert reports[0] is not None
    assert reports[0].metadata == {
        "method": "lightmem",
        "source": "embedding_insert_observer",
        "capture_status": "ok",
        "captured_memory_count": 1,
        "force_segment": True,
        "force_extract": True,
    }
    assert "insert" not in vars(backend.embedding_retriever)


def test_lightmem_halumem_empty_capture_is_reported_without_fabrication() -> None:
    """未插入 memory payload 时应返回带留痕的空报告，不补造候选。"""

    backend = FakeLightMemoryBackend()
    provider = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=20,
            max_workers=1,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        consume_granularity="session",
        session_memory_report=True,
    )
    conversation = Conversation(
        conversation_id="halumem-empty",
        sessions=[
            Session(
                session_id="s1",
                session_time="2025-09-01T10:00:00",
                turns=[
                    Turn(
                        turn_id="s1:t1",
                        speaker="user",
                        normalized_role="user",
                        content="No extracted memory in this fake.",
                    )
                ],
            )
        ],
        metadata={"source_path": "data/halumem/HaluMem-Medium.jsonl"},
    )
    isolation_key = "halumem-run_halumem-empty"
    event = next(build_turn_events(conversation, isolation_key))
    batch = SessionBatch(
        isolation_key=isolation_key,
        session_id="s1",
        events=(event,),
        session_time=event.timestamp,
    )

    provider.ingest(batch)
    report = provider.end_session(batch.ref)

    assert report is not None
    assert report.memories == []
    assert report.metadata["capture_status"] == "empty"
    assert report.metadata["captured_memory_count"] == 0


def test_lightmem_end_session_is_inactive_outside_halumem() -> None:
    """未启用 HaluMem report 能力时 end_session 必须保持默认空行为。"""

    provider = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=20,
            max_workers=1,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
    )

    assert provider.end_session(SessionRef("locomo-run", "s1")) is None


def test_lightmem_registry_specializes_consume_granularity_by_benchmark(
    tmp_path: Path,
) -> None:
    """registry 应按 benchmark profile 设置 LightMem 实例级消费粒度。"""

    (tmp_path / "models" / "all-MiniLM-L6-v2").mkdir(parents=True)
    (
        tmp_path
        / "models"
        / "llmlingua-2-bert-base-multilingual-cased-meetingbank"
    ).mkdir(parents=True)
    path_settings = _tmp_path_settings(tmp_path)
    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=20,
        max_workers=1,
        compression_rate=0.7,
        stm_threshold=512,
        profile_name="official-mini",
    )

    locomo = _build_lightmem_system(
        MethodBuildContext(
            config=config,
            openai_settings=OpenAISettings(api_key="sk-test"),
            path_settings=path_settings,
            storage_root=tmp_path / "locomo",
            benchmark_name="locomo",
        )
    )
    longmemeval = _build_lightmem_system(
        MethodBuildContext(
            config=config,
            openai_settings=OpenAISettings(api_key="sk-test"),
            path_settings=path_settings,
            storage_root=tmp_path / "longmemeval",
            benchmark_name="longmemeval",
        )
    )
    halumem = _build_lightmem_system(
        MethodBuildContext(
            config=config,
            openai_settings=OpenAISettings(api_key="sk-test"),
            path_settings=path_settings,
            storage_root=tmp_path / "halumem",
            benchmark_name="halumem",
        )
    )

    assert isinstance(locomo, MemoryProvider)
    assert locomo.consume_granularity == "turn"
    assert locomo.session_memory_report is False
    assert locomo.benchmark_name == "locomo"
    assert isinstance(longmemeval, MemoryProvider)
    assert longmemeval.consume_granularity == "pair"
    assert longmemeval.session_memory_report is False
    assert longmemeval.benchmark_name == "longmemeval"
    assert isinstance(halumem, MemoryProvider)
    assert halumem.consume_granularity == "session"
    assert halumem.session_memory_report is True
    assert halumem.benchmark_name == "halumem"
    registration = get_method_registration("lightmem")
    validate_compatibility(
        benchmark_task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(),
        method_task_families=registration.task_families,
        provided_capabilities=registration.provided_capabilities,
    )
    assert _method_manifest_with_protocol(
        method_manifest={},
        protocol_version="v3",
    )["protocol_version"] == "v3"
    assert _method_manifest_with_protocol(
        method_manifest={},
        protocol_version="v3",
        system=locomo,
    )["provenance_granularity"] == "turn"


def test_lightmem_backend_config_uses_official_mini_profile_values() -> None:
    """LightMem `(0.7,512)` profile 应显式传入压缩率并记录 STM 阈值。"""

    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=60,
        max_workers=1,
        compression_rate=0.7,
        stm_threshold=512,
        profile_name="official-mini",
    )
    backend_config = LightMem.build_backend_config(
        config=config,
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
        ),
        storage_root="/tmp/lightmem-state",
        conversation_id="conv-profile",
        project_root="/project",
    )

    compress_config = backend_config["pre_compressor"]["configs"]["compress_config"]
    assert compress_config["rate"] == 0.7
    assert backend_config["lightmem_profile"]["stm_threshold"] == 512


@pytest.mark.parametrize(
    "lifecycle_profile",
    ["online_soft", "locomo_offline_consolidated"],
)
def test_lightmem_backend_config_always_uses_offline_update_regardless_of_lifecycle_profile(
    lifecycle_profile: str,
) -> None:
    """两种 lifecycle_profile 都必须继续给上游传 `update="offline"`。

    论文 online soft 的直接插入本身就是由 vendored
    `update="offline" -> offline_update(memory_entries)` 实现（见
    `lightmem-update-lifecycle-ruling.md` §3）；错误地把它改成 `update="online"`
    会命中官方空壳 `online_update()`，导致 memory 根本不入库。这里锁死两种
    profile 构造出的 backend config 都不能触碰这个键。
    """

    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path=(
            "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        ),
        retrieve_limit=60,
        max_workers=1,
        compression_rate=0.7,
        stm_threshold=512,
        profile_name="official-mini",
        lifecycle_profile=lifecycle_profile,
    )

    backend_config = LightMem.build_backend_config(
        config=config,
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
        ),
        storage_root="/tmp/lightmem-state",
        conversation_id="conv-profile",
        project_root="/project",
    )

    assert backend_config["update"] == "offline"


def test_lightmem_locomo_reader_prompt_uses_official_memory_layout() -> None:
    """LoCoMo reader prompt 应使用官方按 speaker 分组的 memory 布局。"""

    backend = FakeLightMemoryBackend()
    chat = FakeLightMemAnswerClient()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=2,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=chat,
        benchmark_name="locomo",
    )
    conversation = _locomo_style_lightmem_conversation()
    method.add([conversation])

    method.get_answer(conversation.questions[0])

    prompt = chat.prompts[0]
    assert "Memories for user Alice" in prompt
    assert "Memories for user Bob" in prompt
    assert "Question: What does Alice like?" in prompt
    assert "The answer should be less than 5-6 words." in prompt


def test_lightmem_locomo_get_answer_uses_qdrant_payload_vector_search() -> None:
    """LoCoMo 回答应复刻 search_locomo.py 的 Qdrant payload 检索路径。"""

    backend = FakeLightMemoryBackend()
    chat = FakeLightMemAnswerClient()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=2,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=chat,
        benchmark_name="locomo",
    )
    conversation = _locomo_style_lightmem_conversation()
    method.add([conversation])

    method.get_answer(conversation.questions[0])

    assert backend.queries == []
    assert backend.text_embedder.embedded_texts == ["What does Alice like?"]
    assert backend.embedding_retriever.get_all_calls == []
    assert backend.embedding_retriever.search_calls == [
        {"limit": 2, "filters": None, "return_full": True}
    ]
    prompt = chat.prompts[0]
    assert "Alice likes jasmine tea." in prompt
    assert "Bob remembered Alice's tea preference." in prompt
    assert "Alice dislikes noisy airports." not in prompt
    assert "Memories for user Alice" in prompt
    assert "Memories for user Bob" in prompt
    assert "[Memory recorded on: 01 January 2026, Thu]" in prompt


def test_lightmem_retrieve_locomo_uses_specialized_context() -> None:
    """LoCoMo retrieve 应走 search_locomo 风格的 Qdrant payload 检索路径。"""

    backend = FakeLightMemoryBackend()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=2,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )
    conversation = _locomo_style_lightmem_conversation()
    method.add([conversation])

    retrieval = method.retrieve(conversation.questions[0])

    assert backend.queries == []
    assert backend.text_embedder.embedded_texts == ["What does Alice like?"]
    assert retrieval.question_id == "q-locomo"
    assert retrieval.conversation_id == "conv-locomo"
    assert [message.role for message in retrieval.prompt_messages] == ["system"]
    assert "Alice likes jasmine tea." in retrieval.answer_prompt
    assert retrieval.metadata["method"] == "lightmem"
    assert retrieval.metadata["retrieval_profile"] == "lightmemory_retrieve"


def test_lightmem_retrieve_longmemeval_uses_backend_retrieve() -> None:
    """LongMemEval retrieve 应走官方检索组件返回带 payload 的结果（统一 search 路径）。"""

    backend = FakeLightMemoryBackend()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=20,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
    )
    conversation = _longmemeval_style_lightmem_conversation()
    method.add([conversation])

    retrieval = method.retrieve(conversation.questions[0])

    assert backend.queries == []
    assert backend.embedding_retriever.get_all_calls == []
    assert backend.embedding_retriever.search_calls == [
        {"limit": 20, "filters": None, "return_full": True}
    ]
    assert retrieval.question_id == "q-long"
    assert retrieval.conversation_id == "conv-long"
    assert [message.role for message in retrieval.prompt_messages] == [
        "system",
        "user",
    ]
    assert retrieval.prompt_messages[0].content == "You are a helpful assistant."
    assert "Alice likes jasmine tea." in retrieval.answer_prompt
    assert "What does Alice like?" in retrieval.answer_prompt
    assert "[Memory recorded on:" in retrieval.metadata["answer_context"]
    assert retrieval.metadata["method"] == "lightmem"
    assert retrieval.metadata["retrieval_profile"] == "lightmemory_retrieve"


def test_lightmem_longmemeval_reader_prompt_includes_question_time() -> None:
    """LongMemEval reader prompt 应复刻官方包含 question_time 的格式。"""

    backend = FakeLightMemoryBackend()
    chat = FakeLightMemAnswerClient()
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=20,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=chat,
    )
    conversation = _longmemeval_style_lightmem_conversation()
    method.add([conversation])

    method.get_answer(conversation.questions[0])

    prompt = chat.prompts[0]
    assert "Question time:2026-01-03 and question:What does Alice like?" in prompt
    assert "Please answer the question based on the following memories:" in prompt


def test_lightmem_records_question_efficiency_observations() -> None:
    """LightMem wrapper 应记录 question-level 汇总和 reader LLM token。"""

    backend = FakeLightMemoryBackend()
    chat = FakeLightMemAnswerClient()
    collector = EfficiencyCollector(run_id="lightmem-efficiency-run", enabled=True)
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=2,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=chat,
        efficiency_collector=collector,
        benchmark_name="locomo",
    )
    conversation = _lightmem_conversation()
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
    assert len(llm_records) == 1
    assert llm_records[0]["stage"] == "answer"
    assert llm_records[0]["model_id"] == "lightmem-answer-llm"
    assert llm_records[0]["input_tokens"] > 0
    assert llm_records[0]["output_tokens"] > 0
    assert llm_records[0]["token_measurement_source"] == "tokenizer_estimate"


def test_lightmem_prefers_api_usage_when_answer_client_exposes_usage() -> None:
    """LightMem reader 暴露 usage 时，应记录精确 `api_usage`。"""

    backend = FakeLightMemoryBackend()
    chat = FakeLightMemAnswerClientWithUsage()
    collector = EfficiencyCollector(run_id="lightmem-api-usage-run", enabled=True)
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=2,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=chat,
        efficiency_collector=collector,
        benchmark_name="locomo",
    )
    conversation = _lightmem_conversation()
    method.add([conversation])

    with collector.question_scope("conv-1", "q-1") as scope:
        method.get_answer(conversation.questions[0])

    llm_records = [
        record.to_dict()
        for record in scope.records
        if record.to_dict()["observation_type"] == "llm_call"
    ]
    assert len(llm_records) == 1
    assert llm_records[0]["token_measurement_source"] == "api_usage"
    assert llm_records[0]["input_tokens"] == 13
    assert llm_records[0]["output_tokens"] == 5


def test_lightmem_records_memory_build_manager_api_usage() -> None:
    """LightMem add 阶段 manager.generate_response usage 应记录为 memory_build。"""

    backend = FakeLightMemoryBackend()
    collector = EfficiencyCollector(run_id="lightmem-build-usage-run", enabled=True)
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=20,
            max_workers=1,
            profile_name="smoke",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        efficiency_collector=collector,
    )

    with collector.conversation_scope("conv-long") as scope:
        method.add([_longmemeval_style_lightmem_conversation()])
        collector.record_memory_build_total_latency(latency_ms=1.0)

    llm_records = [
        record.to_dict()
        for record in scope.records
        if record.to_dict()["observation_type"] == "llm_call"
    ]
    assert len(llm_records) == 1
    assert llm_records[0]["stage"] == "memory_build"
    assert llm_records[0]["model_id"] == "lightmem-memory-llm"
    assert llm_records[0]["token_measurement_source"] == "api_usage"
    assert llm_records[0]["input_tokens"] == 23
    assert llm_records[0]["output_tokens"] == 7


def test_lightmem_buffers_threaded_offline_update_manager_usage() -> None:
    """线程池中的 OP-update LLM usage 应回到 conversation scope 后落盘。

    OP-update 线程池只在显式 locomo_offline_consolidated 补充 profile 下触发
    （online_soft 主 profile 不再执行全库 consolidation），因此本测试显式声明该
    profile 与 benchmark_name="locomo"。
    """

    backend = ThreadedUpdateFakeLightMemoryBackend()
    collector = EfficiencyCollector(
        run_id="lightmem-threaded-update-usage-run",
        enabled=True,
    )
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=60,
            max_workers=1,
            compression_rate=0.7,
            stm_threshold=512,
            profile_name="official-mini",
            lifecycle_profile="locomo_offline_consolidated",
        ),
        backend_factory=lambda conversation_id: backend,
        answer_client=FakeLightMemAnswerClient(),
        efficiency_collector=collector,
        benchmark_name="locomo",
    )

    with collector.conversation_scope("conv-locomo") as scope:
        method.add([_locomo_style_lightmem_conversation()])
        collector.record_memory_build_total_latency(latency_ms=1.0)

    llm_records = [
        record.to_dict()
        for record in scope.records
        if record.to_dict()["observation_type"] == "llm_call"
    ]
    assert len(llm_records) == 3
    assert {
        record["model_id"]
        for record in llm_records
    } == {"lightmem-memory-llm"}
    assert [record["input_tokens"] for record in llm_records] == [23, 23, 23]
    assert [record["output_tokens"] for record in llm_records] == [7, 7, 7]


def test_lightmem_production_backend_receives_openai_and_storage_settings(
    tmp_path,
    monkeypatch,
) -> None:
    """生产 backend 应通过官方 from_config 接收 API、模型和隔离存储路径。"""

    embedding_model_path = tmp_path / "models" / "all-MiniLM-L6-v2"
    llmlingua_model_path = (
        tmp_path
        / "models"
        / "llmlingua-2-bert-base-multilingual-cased-meetingbank"
    )
    embedding_model_path.mkdir(parents=True)
    llmlingua_model_path.mkdir(parents=True)
    FakeOfficialLightMemory.created_configs.clear()
    monkeypatch.setattr(
        "memory_benchmark.methods.lightmem_adapter.import_lightmem_classes",
        lambda path_settings=None: {"LightMemory": FakeOfficialLightMemory},
    )
    method = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path=str(embedding_model_path),
            llmlingua_model_path=str(llmlingua_model_path),
            retrieve_limit=2,
            max_workers=1,
            profile_name="smoke",
        ),
        openai_settings=OpenAISettings(
            api_key="sk-test-lightmem",
            base_url="https://example.invalid/v1",
        ),
        storage_root=tmp_path / "lightmem-state",
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )

    method.add([_lightmem_conversation()])

    assert len(FakeOfficialLightMemory.created_configs) == 1
    official_config = FakeOfficialLightMemory.created_configs[0]
    assert official_config["memory_manager"]["configs"]["api_key"] == (
        "sk-test-lightmem"
    )
    assert official_config["memory_manager"]["configs"]["openai_base_url"] == (
        "https://example.invalid/v1"
    )
    assert official_config["memory_manager"]["configs"]["model"] == "gpt-4o-mini"
    assert official_config["text_embedder"]["configs"]["model"] == (
        str(embedding_model_path.resolve())
    )
    assert official_config["pre_compressor"]["configs"]["llmlingua_config"][
        "model_name"
    ] == (
        str(llmlingua_model_path.resolve())
    )
    retriever_config = official_config["embedding_retriever"]["configs"]
    assert retriever_config["collection_name"].startswith("lightmem_conv-1")
    assert str(tmp_path / "lightmem-state") in retriever_config["path"]


# === hybrid role profile 强反例（2026-07-16） ===


@pytest.mark.parametrize("messages_use", ["user_only", "assistant_only", "hybrid"])
def test_lightmem_config_accepts_valid_messages_use(messages_use: str) -> None:
    """三个合法 messages_use 值都应通过强校验。"""

    config = LightMemConfig(
        llm_model="gpt-4o-mini",
        embedding_model_path="models/all-MiniLM-L6-v2",
        llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
        retrieve_limit=60,
        max_workers=1,
        messages_use=messages_use,
    )
    assert config.messages_use == messages_use


@pytest.mark.parametrize(
    "bad_value",
    ["", "  ", "HYBRID", "User_Only", "all", 42, None],
)
def test_lightmem_config_rejects_invalid_messages_use(bad_value) -> None:
    """空白、大小写、未知、非字符串 messages_use 都应被拒绝。"""

    with pytest.raises(ConfigurationError, match="messages_use"):
        LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            retrieve_limit=60,
            max_workers=1,
            messages_use=bad_value,
        )


def test_lightmem_backend_config_reads_messages_use_from_config() -> None:
    """build_backend_config 必须从 config.messages_use 读取，禁止硬编码。"""

    openai_settings = OpenAISettings(
        api_key="sk-test", base_url="https://example.invalid/v1"
    )
    for value in ("user_only", "assistant_only", "hybrid"):
        config = LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            retrieve_limit=60,
            max_workers=1,
            messages_use=value,
        )
        backend_config = LightMem.build_backend_config(
            config=config,
            openai_settings=openai_settings,
            storage_root="/tmp/test",
            conversation_id="conv-1",
            project_root="/tmp",
        )
        assert backend_config["messages_use"] == value


def test_lightmem_normalizer_locomo_pair_preserves_named_speaker() -> None:
    """LoCoMo normalizer 应生成 user(真实) + assistant(placeholder) pair。"""

    system = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            retrieve_limit=60,
            max_workers=1,
        ),
        backend_factory=lambda _id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )
    conversation = _lightmem_conversation()
    session = conversation.sessions[0]
    batches = system._normalize_session_to_pairs(session, conversation)

    assert len(batches) == 2
    first_pair = batches[0]
    assert first_pair[0]["role"] == "user"
    assert first_pair[0]["content"] == "I like tea."
    assert first_pair[0]["speaker_name"] == "Alice"
    assert first_pair[1]["role"] == "assistant"
    assert first_pair[1]["content"] == ""
    assert first_pair[1].get("memory_benchmark_structural_placeholder") is True
    assert first_pair[0]["source_external_ids"] == ["t-1"]
    assert first_pair[1]["source_external_ids"] == ["t-1"]


def test_lightmem_normalizer_generic_pair_handles_all_sequences() -> None:
    """通用 normalizer 应正确处理所有 role 序列。"""

    system = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            retrieve_limit=60,
            max_workers=1,
        ),
        backend_factory=lambda _id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="longmemeval",
    )

    session_normal = Session(
        session_id="s1",
        session_time="2026-01-01",
        turns=[
            Turn(turn_id="u1", speaker="user", normalized_role="user", content="hi"),
            Turn(turn_id="a1", speaker="assistant", normalized_role="assistant", content="hello"),
        ],
    )
    conv = Conversation(conversation_id="c1", sessions=[session_normal])
    batches = system._normalize_session_to_pairs(session_normal, conv)
    assert len(batches) == 1
    assert batches[0][0]["role"] == "user"
    assert batches[0][1]["role"] == "assistant"
    assert batches[0][0]["source_external_ids"] == ["u1", "a1"]

    session_user_user = Session(
        session_id="s2",
        session_time="2026-01-01",
        turns=[
            Turn(turn_id="u1", speaker="user", normalized_role="user", content="a"),
            Turn(turn_id="u2", speaker="user", normalized_role="user", content="b"),
        ],
    )
    conv2 = Conversation(conversation_id="c2", sessions=[session_user_user])
    batches2 = system._normalize_session_to_pairs(session_user_user, conv2)
    assert len(batches2) == 2
    assert batches2[0][0]["role"] == "user"
    assert batches2[0][1].get("memory_benchmark_structural_placeholder") is True
    assert batches2[1][0]["role"] == "user"
    assert batches2[1][1].get("memory_benchmark_structural_placeholder") is True

    session_dangling = Session(
        session_id="s3",
        session_time="2026-01-01",
        turns=[
            Turn(turn_id="u1", speaker="user", normalized_role="user", content="bye"),
        ],
    )
    conv3 = Conversation(conversation_id="c3", sessions=[session_dangling])
    batches3 = system._normalize_session_to_pairs(session_dangling, conv3)
    assert len(batches3) == 1
    assert batches3[0][0]["role"] == "user"
    assert batches3[0][0]["content"] == "bye"
    assert batches3[0][1].get("memory_benchmark_structural_placeholder") is True

    session_asst_assistant = Session(
        session_id="s4",
        session_time="2026-01-01",
        turns=[
            Turn(turn_id="a1", speaker="assistant", normalized_role="assistant", content="x"),
            Turn(turn_id="a2", speaker="assistant", normalized_role="assistant", content="y"),
        ],
    )
    conv4 = Conversation(conversation_id="c4", sessions=[session_asst_assistant])
    batches4 = system._normalize_session_to_pairs(session_asst_assistant, conv4)
    assert len(batches4) == 2
    assert batches4[0][0].get("memory_benchmark_structural_placeholder") is True
    assert batches4[0][1]["role"] == "assistant"
    assert batches4[1][0].get("memory_benchmark_structural_placeholder") is True
    assert batches4[1][1]["role"] == "assistant"


def test_lightmem_normalizer_rejects_unknown_role_without_benchmark() -> None:
    """缺 benchmark identity 且遇到非 user/assistant role 时应 fail-fast。"""

    system = LightMem(
        config=LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path="models/llmlingua-2-bert-base-multilingual-cased-meetingbank",
            retrieve_limit=60,
            max_workers=1,
        ),
        backend_factory=lambda _id: FakeLightMemoryBackend(),
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name=None,
    )
    session = Session(
        session_id="s1",
        session_time="2026-01-01",
        turns=[
            Turn(turn_id="t1", speaker="Alice", content="hi"),
        ],
    )
    conv = Conversation(conversation_id="c1", sessions=[session])
    with pytest.raises(ConfigurationError, match="canonical normalized_role"):
        system._normalize_session_to_pairs(session, conv)


@pytest.mark.parametrize(
    ("roles", "expected_real_groups"),
    [
        (["user", "assistant"], [["t0", "t1"]]),
        (["assistant", "user"], [["t0"], ["t1"]]),
        (["user", "user"], [["t0"], ["t1"]]),
        (["assistant", "assistant"], [["t0"], ["t1"]]),
        (["user"], [["t0"]]),
        (["assistant"], [["t0"]]),
    ],
)
def test_lightmem_generic_normalizer_preserves_each_real_turn_once(
    roles: list[str],
    expected_real_groups: list[list[str]],
) -> None:
    """六类病态 role 序列都应保持真实 turn 的顺序、次数和 pair 候选组。"""

    system = _lightmem_evidence_system(benchmark_name="longmemeval")
    turns = [
        Turn(
            turn_id=f"t{index}",
            speaker=role,
            normalized_role=role,
            content=f"content-{index}",
        )
        for index, role in enumerate(roles)
    ]
    session = Session(
        session_id="s1",
        session_time="2026-01-01",
        turns=turns,
    )
    conversation = Conversation(conversation_id="c1", sessions=[session])

    pairs = system._normalize_session_to_pairs(session, conversation)

    assert [[message["role"] for message in pair] for pair in pairs] == [
        ["user", "assistant"] for _ in expected_real_groups
    ]
    real_ids = [
        message["external_id"]
        for pair in pairs
        for message in pair
        if message.get("memory_benchmark_structural_placeholder") is not True
    ]
    assert real_ids == [turn.turn_id for turn in turns]
    assert [pair[0]["source_external_ids"] for pair in pairs] == expected_real_groups
    assert [pair[1]["source_external_ids"] for pair in pairs] == expected_real_groups


def test_lightmem_generic_normalizer_does_not_pair_across_sessions() -> None:
    """session 尾 user 与下一 session 首 assistant 必须各自补位，不得跨界配对。"""

    system = _lightmem_evidence_system(benchmark_name="longmemeval")
    session_user = Session(
        session_id="s-user",
        session_time="2026-01-01",
        turns=[
            Turn(
                turn_id="u1",
                speaker="user",
                normalized_role="user",
                content="first session",
            )
        ],
    )
    session_assistant = Session(
        session_id="s-assistant",
        session_time="2026-01-02",
        turns=[
            Turn(
                turn_id="a1",
                speaker="assistant",
                normalized_role="assistant",
                content="second session",
            )
        ],
    )
    conversation = Conversation(
        conversation_id="c-cross",
        sessions=[session_user, session_assistant],
    )

    batches = system._conversation_to_lightmem_batches(conversation)

    assert [batch[0]["source_external_ids"] for batch in batches] == [["u1"], ["a1"]]
    assert batches[0][1]["memory_benchmark_structural_placeholder"] is True
    assert batches[1][0]["memory_benchmark_structural_placeholder"] is True


def test_lightmem_generic_normalizer_keeps_real_empty_content() -> None:
    """真实空 content 仍是来源 turn；只有 marker=True 才代表结构占位。"""

    system = _lightmem_evidence_system(benchmark_name="beam")
    turn = Turn(
        turn_id="empty-real",
        speaker="user",
        normalized_role="user",
        content="",
    )
    session = Session(session_id="s1", session_time="2026-01-01", turns=[turn])
    conversation = Conversation(conversation_id="c-empty", sessions=[session])

    pair = system._normalize_session_to_pairs(session, conversation)[0]

    assert pair[0]["content"] == ""
    assert "memory_benchmark_structural_placeholder" not in pair[0]
    assert pair[0]["source_external_ids"] == ["empty-real"]
    assert pair[1]["memory_benchmark_structural_placeholder"] is True


@pytest.mark.parametrize(
    "turn",
    [
        Turn(
            turn_id="missing",
            speaker="assistant",
            content="metadata must not launder",
            metadata={"role": "assistant"},
        ),
        Turn(
            turn_id="upper",
            speaker="user",
            normalized_role="USER",
            content="case must stay strict",
        ),
        Turn(
            turn_id="tool",
            speaker="tool",
            normalized_role="tool",
            content="unknown role",
        ),
        Turn(
            turn_id="unhashable",
            speaker="user",
            normalized_role=["user"],
            content="runtime type error must be normalized",
        ),
    ],
)
def test_lightmem_generic_normalizer_rejects_missing_or_noncanonical_role(
    turn: Turn,
) -> None:
    """只读 canonical normalized_role；metadata/speaker/大小写均不能洗成合法 role。"""

    system = _lightmem_evidence_system(benchmark_name="membench")
    session = Session(session_id="s1", session_time="2026-01-01", turns=[turn])
    conversation = Conversation(conversation_id="c-role", sessions=[session])

    with pytest.raises(ConfigurationError, match="canonical normalized_role"):
        system._normalize_session_to_pairs(session, conversation)


@pytest.mark.parametrize(
    "content",
    [
        "A third-person memory narrative.",
        "'user': I like tea.; 'agent': Tea is noted.",
    ],
)
def test_lightmem_membench_treats_single_user_turn_as_singleton_pair(
    content: str,
) -> None:
    """ThirdAgent observation turn（与任何看似 composite 的 content）都不得在

    LightMem 内二次解析/伪造 assistant。canonical split 后 FirstAgent 已不再
    产出这种拼接文本，本用例改为通用防御：无论 content 长什么样，单条
    `normalized_role="user"` turn 一律只补结构占位 assistant，不解析 content。
    """

    system = _lightmem_evidence_system(benchmark_name="membench")
    turn = Turn(
        turn_id="step-1",
        speaker="user",
        normalized_role="user",
        content=content,
    )
    session = Session(session_id="s1", session_time="2026-01-01", turns=[turn])
    conversation = Conversation(conversation_id="c-membench", sessions=[session])

    pair = system._normalize_session_to_pairs(session, conversation)[0]

    assert pair[0]["content"] == content
    assert pair[0]["external_id"] == "step-1"
    assert pair[1]["memory_benchmark_structural_placeholder"] is True


def test_lightmem_membench_canonical_pair_yields_two_real_pair_candidate_ids() -> None:
    """canonical split 后的真实 MemBench user+assistant pair 应产出两个真实 child id。

    对应 §2.6/§5.3 裁决：LightMem 不解析 MemBench content，只读 canonical
    normalized_role；一个真实 user turn 紧邻一个真实 assistant turn 时，两侧
    `source_external_ids` 都必须是这两个真实 turn id 的稳定去重集合，而不是
    单侧真实 + 单侧 placeholder。
    """

    system = _lightmem_evidence_system(benchmark_name="membench")
    user_turn = Turn(
        turn_id="1:user",
        speaker="user",
        normalized_role="user",
        content="I work with Maya.",
    )
    assistant_turn = Turn(
        turn_id="1:assistant",
        speaker="agent",
        normalized_role="assistant",
        content="Maya is your colleague.",
    )
    session = Session(
        session_id="s1", session_time="2026-01-01", turns=[user_turn, assistant_turn]
    )
    conversation = Conversation(conversation_id="c-membench-pair", sessions=[session])

    pairs = system._normalize_session_to_pairs(session, conversation)

    assert len(pairs) == 1
    user_msg, assistant_msg = pairs[0]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "I work with Maya."
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "Maya is your colleague."
    assert LIGHTMEM_PLACEHOLDER_MARKER not in user_msg
    assert LIGHTMEM_PLACEHOLDER_MARKER not in assistant_msg
    assert user_msg["source_external_ids"] == ["1:user", "1:assistant"]
    assert assistant_msg["source_external_ids"] == ["1:user", "1:assistant"]


def test_lightmem_membench_extraction_batch_keeps_pair_lineage_by_source_id() -> None:
    """同一 extraction batch 内两个 MemBench pair 不得互相 union lineage。

    本用例不 fake 被测映射链：先由 adapter 生成两个 canonical
    pair，再经真实 vendored ``MessageNormalizer``、
    ``assign_sequence_numbers_with_timestamps`` 与
    ``_create_memory_entry_from_fact``。fact source_id=0/1 必须分别选中
    sequence 0/2 上的单个 pair candidate ids。
    """

    system = _lightmem_evidence_system(benchmark_name="membench")
    turns = [
        Turn("1:user", "user", "User fact one.", normalized_role="user"),
        Turn(
            "1:assistant",
            "agent",
            "Assistant fact one.",
            normalized_role="assistant",
        ),
        Turn("2:user", "user", "User fact two.", normalized_role="user"),
        Turn(
            "2:assistant",
            "agent",
            "Assistant fact two.",
            normalized_role="assistant",
        ),
    ]
    session = Session(
        session_id="s1",
        session_time="2026-01-01T00:00:00",
        turns=turns,
    )
    conversation = Conversation(conversation_id="c-two-pairs", sessions=[session])
    pairs = system._normalize_session_to_pairs(session, conversation)
    assert len(pairs) == 2

    import_lightmem_classes(load_path_settings())
    lightmem_module = sys.modules["lightmem.memory.lightmem"]
    utils = sys.modules["lightmem.memory.utils"]
    normalized = lightmem_module.MessageNormalizer().normalize_messages(
        [message for pair in pairs for message in pair]
    )
    (
        _extract,
        timestamps,
        weekdays,
        speakers,
        external_ids,
        _topics,
        plural_lists,
    ) = utils.assign_sequence_numbers_with_timestamps([[[*normalized]]])
    entries = [
        utils._create_memory_entry_from_fact(
            {"source_id": source_id, "fact": f"Extracted fact {source_id}."},
            timestamps,
            weekdays,
            speakers,
            external_ids=external_ids,
            source_external_ids_list=plural_lists,
        )
        for source_id in (0, 1)
    ]

    assert [entry.source_external_ids for entry in entries] == [
        ["1:user", "1:assistant"],
        ["2:user", "2:assistant"],
    ]
    assert all(entry.source_external_id is None for entry in entries)


def _capture_lightmem_extraction_messages(
    messages: list[dict[str, object]],
    messages_use: str,
) -> list[dict[str, str]]:
    """用离线 fake 捕获 vendored extraction 的 system/user messages。"""

    import_lightmem_classes(load_path_settings())
    from lightmem.factory.memory_manager.openai import OpenaiManager

    manager = OpenaiManager.__new__(OpenaiManager)

    def _fake_generate_response(**kwargs):
        """返回空 extraction JSON，并保留传入 messages 供结果断言。"""

        return json.dumps({"data": []}), {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    manager.generate_response = _fake_generate_response
    result = manager._extract_with_prompt(
        "SYSTEM-PROMPT-BYTE-ANCHOR",
        [[messages]],
        messages_use,
        topic_id_mapping=[[7]],
    )
    assert len(result) == 1
    return result[0]["input_prompt"]


def _lightmem_short_token_count(
    messages: list[dict[str, object]],
    messages_use: str,
) -> int:
    """离线调用 vendored short buffer 的原始 token 计数边界。"""

    import_lightmem_classes(load_path_settings())
    from lightmem.factory.memory_buffer.short_term_memory import ShortMemBufferManager

    short = ShortMemBufferManager.__new__(ShortMemBufferManager)
    short.tokenizer = None
    return short._count_tokens(messages, messages_use)


def test_lightmem_locomo_placeholder_keeps_hybrid_user_only_prompt_and_tokens_equal() -> None:
    """LoCoMo placeholder 不渲染/计数，hybrid 与 user_only 输入必须严格相等。"""

    messages = [
        {
            "role": "user",
            "content": "Alice likes tea.",
            "speaker_name": "Alice",
            "sequence_number": 0,
            "time_stamp": "2026-01-01T00:00:00.000",
            "weekday": "Thu",
        },
        {
            "role": "assistant",
            "content": "",
            "speaker_name": "Alice",
            "sequence_number": 1,
            "time_stamp": "2026-01-01T00:00:00.500",
            "weekday": "Thu",
            "memory_benchmark_structural_placeholder": True,
        },
    ]

    hybrid = _capture_lightmem_extraction_messages(messages, "hybrid")
    user_only = _capture_lightmem_extraction_messages(messages, "user_only")

    assert hybrid == user_only
    assert hybrid[0] == user_only[0] == {
        "role": "system",
        "content": "SYSTEM-PROMPT-BYTE-ANCHOR",
    }
    assert "Alice likes tea." in hybrid[1]["content"]
    assert hybrid[1]["content"].count("Alice:") == 1
    assert _lightmem_short_token_count(messages, "hybrid") == (
        _lightmem_short_token_count(messages, "user_only")
    )


def test_lightmem_hybrid_prompt_and_tokens_include_real_assistant_only() -> None:
    """真实 assistant 只在 hybrid 可见；system prompt 不变且 token 数真实增加。"""

    messages = [
        {
            "role": "user",
            "content": "User fact.",
            "speaker_name": "user",
            "sequence_number": 0,
        },
        {
            "role": "assistant",
            "content": "Assistant correction.",
            "speaker_name": "assistant",
            "sequence_number": 1,
        },
    ]

    hybrid = _capture_lightmem_extraction_messages(messages, "hybrid")
    user_only = _capture_lightmem_extraction_messages(messages, "user_only")

    assert hybrid[0] == user_only[0]
    assert "Assistant correction." in hybrid[1]["content"]
    assert "Assistant correction." not in user_only[1]["content"]
    assert _lightmem_short_token_count(messages, "hybrid") > (
        _lightmem_short_token_count(messages, "user_only")
    )


def test_lightmem_truthy_non_bool_placeholder_marker_is_real_message() -> None:
    """只有 marker is True 才过滤；字符串 'false' 必须保留为真实消息。"""

    messages = [
        {
            "role": "assistant",
            "content": "Truthy marker is still real.",
            "speaker_name": "assistant",
            "sequence_number": 1,
            "memory_benchmark_structural_placeholder": "false",
        }
    ]

    extraction = _capture_lightmem_extraction_messages(messages, "hybrid")

    assert "Truthy marker is still real." in extraction[1]["content"]
    assert _lightmem_short_token_count(messages, "hybrid") == len(
        "Truthy marker is still real."
    )


@pytest.mark.parametrize(
    ("turns", "expected_plural", "expected_singular", "expected_speaker"),
    [
        (
            [Turn("u1", "user", "User only.", normalized_role="user")],
            ["u1"],
            "u1",
            "user",
        ),
        (
            [
                Turn("u1", "user", "User fact.", normalized_role="user"),
                Turn(
                    "a1",
                    "assistant",
                    "Assistant fact.",
                    normalized_role="assistant",
                ),
            ],
            ["u1", "a1"],
            None,
            "user",
        ),
        (
            [
                Turn(
                    "a1",
                    "assistant",
                    "Assistant only.",
                    normalized_role="assistant",
                )
            ],
            ["a1"],
            "a1",
            "assistant",
        ),
    ],
)
def test_lightmem_pair_lineage_survives_normalizer_sequence_and_memory_entry(
    turns: list[Turn],
    expected_plural: list[str],
    expected_singular: str | None,
    expected_speaker: str,
) -> None:
    """单侧、双侧、assistant-only 的 plural/singular 应穿过真实 vendored 链。"""

    system = _lightmem_evidence_system(benchmark_name="longmemeval")
    session = Session(
        session_id="s1",
        session_time="2026-01-01T00:00:00",
        turns=turns,
    )
    conversation = Conversation(conversation_id="c-lineage", sessions=[session])
    pair = system._normalize_session_to_pairs(session, conversation)[0]

    import_lightmem_classes(load_path_settings())
    lightmem_module = sys.modules["lightmem.memory.lightmem"]
    utils = sys.modules["lightmem.memory.utils"]
    normalized = lightmem_module.MessageNormalizer().normalize_messages(pair)
    (
        _extract,
        timestamps,
        weekdays,
        speakers,
        external_ids,
        _topics,
        plural_lists,
    ) = utils.assign_sequence_numbers_with_timestamps([[[*normalized]]])
    entry = utils._create_memory_entry_from_fact(
        {"source_id": 0, "fact": "Extracted fact."},
        timestamps,
        weekdays,
        speakers,
        external_ids=external_ids,
        source_external_ids_list=plural_lists,
    )

    assert entry.source_external_ids == expected_plural
    assert entry.source_external_id == expected_singular
    assert entry.speaker_name == expected_speaker


def test_lightmem_pair_lineage_stably_deduplicates_canonical_ids() -> None:
    """合法 canonical id 的重复项应稳定去重且不改变顺序。"""

    import_lightmem_classes(load_path_settings())
    utils = sys.modules["lightmem.memory.utils"]
    message = {
        "role": "user",
        "content": "fact",
        "session_time": None,
        "time_stamp": None,
        "weekday": None,
        "speaker_id": "user",
        "speaker_name": "user",
        "external_id": "legacy",
        "source_external_ids": ["u1", "u1", "u2", "u1"],
    }

    result = utils.assign_sequence_numbers_with_timestamps([[[message]]])
    plural_lists = result[-1]
    entry = utils._create_memory_entry_from_fact(
        {"source_id": 0, "fact": "Extracted."},
        result[1],
        result[2],
        result[3],
        external_ids=result[4],
        source_external_ids_list=plural_lists,
    )

    assert plural_lists == [["u1", "u2"]]
    assert entry.source_external_ids == ["u1", "u2"]
    assert entry.source_external_id is None


@pytest.mark.parametrize(
    "raw_plural",
    [
        ["u1", None],
        ["u1", "  "],
        ["u1", " u2 "],
        ["u1", 7],
        [],
        "u1",
        None,
    ],
)
def test_lightmem_malformed_pair_lineage_never_yields_partial_provenance(
    raw_plural,
) -> None:
    """任一坏 plural 元素/结构都应令整组无 lineage，不能截出 u1 或读 singular。"""

    import_lightmem_classes(load_path_settings())
    utils = sys.modules["lightmem.memory.utils"]
    message = {
        "role": "user",
        "content": "fact",
        "session_time": None,
        "time_stamp": None,
        "weekday": None,
        "speaker_id": "user",
        "speaker_name": "user",
        "external_id": "legacy-singular",
        "source_external_ids": raw_plural,
    }

    result = utils.assign_sequence_numbers_with_timestamps([[[message]]])
    entry = utils._create_memory_entry_from_fact(
        {"source_id": 0, "fact": "Extracted."},
        result[1],
        result[2],
        result[3],
        external_ids=result[4],
        source_external_ids_list=result[-1],
    )

    assert result[-1] == [[]]
    assert entry.source_external_ids == []
    assert entry.source_external_id is None


@pytest.mark.parametrize(
    "raw_plural",
    [
        ["u1", None],
        ["u1", "  "],
        ["u1", " u2 "],
        ["u1", 7],
        [],
        "u1",
        None,
    ],
)
def test_lightmem_adapter_rejects_malformed_plural_without_singular_fallback(
    raw_plural,
) -> None:
    """adapter 对 mixed/空/错结构 plural 整次回落 None，不读 legacy singular。"""

    memories = [
        {
            "id": "m1",
            "score": 0.9,
            "payload": {
                "memory": "fact",
                "source_external_id": "legacy-singular",
                "source_external_ids": raw_plural,
            },
        }
    ]

    assert LightMem._retrieved_items_from_lightmem_memories(memories) is None


def test_lightmem_adapter_reads_valid_plural_with_stable_deduplication() -> None:
    """合法 plural 允许重复但按原顺序去重，并保持 id 字节。"""

    memories = [
        {
            "id": "m1",
            "score": 0.9,
            "payload": {
                "memory": "fact",
                "source_external_ids": ["u1", "u1", "u2"],
            },
        }
    ]

    items = LightMem._retrieved_items_from_lightmem_memories(memories)

    assert items is not None
    assert items[0].source_turn_ids == ("u1", "u2")


def test_lightmem_offline_insert_writes_plural_without_false_singular() -> None:
    """双侧 MemoryEntry 插入 payload 只写 plural，不把 user id 冒充 exact singular。"""

    classes = import_lightmem_classes(load_path_settings())
    utils = sys.modules["lightmem.memory.utils"]

    class _Retriever:
        """记录 offline_update 插入 payload 的本地 fake。"""

        def __init__(self) -> None:
            """初始化记录。"""

            self.payloads = []

        def exists(self, _item_id: str) -> bool:
            """本测试没有 id 冲突。"""

            return False

        def insert(self, *, vectors, payloads, ids) -> None:
            """记录 payload，不执行外部 I/O。"""

            assert vectors and ids
            self.payloads.extend(payloads)

    retriever = _Retriever()
    backend = classes["LightMemory"].__new__(classes["LightMemory"])
    backend.config = SimpleNamespace(index_strategy="embedding")
    backend.logger = SimpleNamespace(
        info=lambda *_args, **_kwargs: None,
        debug=lambda *_args, **_kwargs: None,
    )
    backend.text_embedder = SimpleNamespace(embed=lambda _text: [1.0, 0.0])
    backend.embedding_retriever = retriever

    backend.offline_update(
        [
            utils.MemoryEntry(
                memory="two-sided fact",
                source_external_id=None,
                source_external_ids=["u1", "a1"],
            )
        ]
    )

    assert retriever.payloads[0]["source_external_ids"] == ["u1", "a1"]
    assert "source_external_id" not in retriever.payloads[0]


def _prompt_identity_conversation(source_path: str) -> Conversation:
    """构造同时可走 generic/LoCoMo 的最小 conversation，用于身份反例。"""

    return Conversation(
        conversation_id=f"c-{source_path.replace('/', '-')}",
        sessions=[
            Session(
                session_id="s1",
                session_time="2026-01-01",
                turns=[
                    Turn(
                        turn_id="u1",
                        speaker="Alice",
                        normalized_role="user",
                        content="User fact.",
                    ),
                    Turn(
                        turn_id="a1",
                        speaker="Bob",
                        normalized_role="assistant",
                        content="Assistant fact.",
                    ),
                ],
            )
        ],
        metadata={
            "source_path": source_path,
            "speaker_a": "Alice",
            "speaker_b": "Bob",
        },
    )


def test_lightmem_legacy_locomo_prompt_uses_only_constructor_identity(
    monkeypatch,
) -> None:
    """legacy add 不得从 source_path 猜 LoCoMo；构造期 identity 是唯一选择器。"""

    import memory_benchmark.methods.lightmem_adapter as adapter_module

    monkeypatch.setattr(
        adapter_module,
        "_load_lightmem_locomo_prompt",
        lambda *_args: "LOC-PROMPT",
    )
    spoof_backend = FakeLightMemoryBackend()
    spoof = LightMem(
        config=_missing_time_config(),
        backend_factory=lambda _key: spoof_backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="longmemeval",
    )
    spoof.add(_prompt_identity_conversation("data/locomo/spoof.json"))
    assert "METADATA_GENERATE_PROMPT" not in spoof_backend.added_messages[0]["kwargs"]

    explicit_backend = FakeLightMemoryBackend()
    explicit = LightMem(
        config=_missing_time_config(),
        backend_factory=lambda _key: explicit_backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )
    explicit.add(_prompt_identity_conversation("data/other/source.json"))
    assert all(
        call["kwargs"]["METADATA_GENERATE_PROMPT"] == "LOC-PROMPT"
        for call in explicit_backend.added_messages
    )


def test_lightmem_native_locomo_prompt_uses_only_constructor_identity(
    monkeypatch,
) -> None:
    """native write 同样不得读取缓存 source_path 决定 LoCoMo extraction prompt。"""

    import memory_benchmark.methods.lightmem_adapter as adapter_module

    monkeypatch.setattr(
        adapter_module,
        "_load_lightmem_locomo_prompt",
        lambda *_args: "LOC-PROMPT",
    )
    messages = [{"role": "user", "content": "fact"}]

    spoof_backend = FakeLightMemoryBackend()
    spoof = LightMem(
        config=_missing_time_config(),
        backend_factory=lambda _key: spoof_backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="beam",
    )
    spoof._conversation_metadata["ns-spoof"] = {
        "source_path": "data/locomo/spoof.json"
    }
    spoof._write_native_batch("ns-spoof", messages, is_final=True)
    assert "METADATA_GENERATE_PROMPT" not in spoof_backend.added_messages[0]["kwargs"]

    explicit_backend = FakeLightMemoryBackend()
    explicit = LightMem(
        config=_missing_time_config(),
        backend_factory=lambda _key: explicit_backend,
        answer_client=FakeLightMemAnswerClient(),
        benchmark_name="locomo",
    )
    explicit._conversation_metadata["ns-locomo"] = {
        "source_path": "data/other/source.json"
    }
    explicit._write_native_batch("ns-locomo", messages, is_final=True)
    assert explicit_backend.added_messages[0]["kwargs"][
        "METADATA_GENERATE_PROMPT"
    ] == "LOC-PROMPT"


def test_lightmem_halumem_irregular_session_is_one_flattened_add_call() -> None:
    """HaluMem SessionBatch 保持 session-level 单次 pipeline 边界并保留 pair marker。"""

    backend = SessionCaptureFakeLightMemoryBackend()
    provider = LightMem(
        config=_missing_time_config(),
        backend_factory=lambda _key: backend,
        answer_client=FakeLightMemAnswerClient(),
        consume_granularity="session",
        session_memory_report=True,
        benchmark_name="halumem",
    )
    conversation = Conversation(
        conversation_id="c-halu-irregular",
        sessions=[
            Session(
                session_id="s1",
                session_time="2026-01-01",
                turns=[
                    Turn(
                        turn_id="a1",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="Assistant first.",
                    ),
                    Turn(
                        turn_id="u1",
                        speaker="user",
                        normalized_role="user",
                        content="Dangling user.",
                    ),
                ],
            )
        ],
        metadata={"source_path": "data/halumem/sample.jsonl"},
    )
    events = tuple(build_turn_events(conversation, "halu-run_c-halu-irregular"))
    batch = SessionBatch(
        isolation_key="halu-run_c-halu-irregular",
        session_id="s1",
        events=events,
        session_time=events[0].timestamp,
    )

    provider.ingest(batch)

    assert len(backend.added_messages) == 1
    call = backend.added_messages[0]
    assert call["kwargs"] == {"force_segment": True, "force_extract": True}
    assert [message["content"] for message in call["messages"]] == [
        "",
        "Assistant first.",
        "Dangling user.",
        "",
    ]
    assert call["messages"][0]["memory_benchmark_structural_placeholder"] is True
    assert call["messages"][3]["memory_benchmark_structural_placeholder"] is True
    assert [message["source_external_ids"] for message in call["messages"]] == [
        ["a1"],
        ["a1"],
        ["u1"],
        ["u1"],
    ]


def test_lightmem_evidence_matrix_per_benchmark() -> None:
    """RetrievalEvidence 矩阵逐 benchmark 锁 status/reason/granularity。"""

    items_empty: tuple[RetrievedItem, ...] = ()
    items_none = None

    locomo = _lightmem_evidence_system(benchmark_name="locomo")
    assert locomo._build_retrieval_evidence(items_empty).semantic_provenance.status == "valid"
    assert locomo._build_retrieval_evidence(items_empty).provenance_granularity == "turn"
    assert locomo._build_retrieval_evidence(items_none).semantic_provenance.status == "n_a"

    membench = _lightmem_evidence_system(benchmark_name="membench")
    ev = membench._build_retrieval_evidence(items_empty)
    assert ev.semantic_provenance.status == "valid"
    assert ev.provenance_granularity == "turn"
    ev = membench._build_retrieval_evidence(items_none)
    assert ev.semantic_provenance.status == "n_a"
    assert ev.semantic_provenance.reason_code == "retrieval_hit_lineage_incomplete"
    assert ev.provenance_granularity == "none"

    lme = _lightmem_evidence_system(benchmark_name="longmemeval")
    ev = lme._build_retrieval_evidence(items_empty)
    assert ev.semantic_provenance.status == "n_a"
    assert ev.semantic_provenance.reason_code == "pair_source_id_not_turn_exact"

    beam = _lightmem_evidence_system(benchmark_name="beam")
    ev = beam._build_retrieval_evidence(items_empty)
    assert ev.semantic_provenance.status == "n_a"
    assert ev.semantic_provenance.reason_code == "beam_gold_is_single_message"

    halu = _lightmem_evidence_system(benchmark_name="halumem")
    ev = halu._build_retrieval_evidence(items_empty)
    assert ev.semantic_provenance.status == "n_a"
    assert ev.semantic_provenance.reason_code == "halumem_no_turn_qrel"

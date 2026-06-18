"""LightMem adapter 的配置、源码身份和基础契约测试。

这些测试不调用真实 API，也不初始化重模型。目标是先锁定官方源码路径和强配置校验。
"""

from __future__ import annotations

import pytest

from memory_benchmark.config import OpenAISettings, PathSettings, load_path_settings
from memory_benchmark.core import (
    AnswerResult,
    ConfigurationError,
    Conversation,
    Question,
    Session,
    Turn,
)
from memory_benchmark.methods.lightmem_adapter import (
    LightMem,
    LightMemConfig,
    build_lightmem_source_identity,
    import_lightmem_classes,
)
from memory_benchmark.observability.efficiency import EfficiencyCollector


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

    def add_memory(self, messages, **kwargs):
        """记录写入消息和 LightMem pipeline 参数。"""

        self.added_messages.append({"messages": messages, "kwargs": kwargs})
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
    """模拟 LightMem 官方 Qdrant retriever 的 get_all 接口。"""

    def __init__(self) -> None:
        """初始化带 payload/vector 的 fake Qdrant entries。"""

        self.get_all_calls: list[dict[str, object]] = []
        self.entries = [
            {
                "id": "alice-tea",
                "vector": [1.0, 0.0],
                "payload": {
                    "speaker_name": "Alice",
                    "memory": "Alice likes jasmine tea.",
                    "time_stamp": "2026-01-01T00:00:00.000",
                    "weekday": "Thu",
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
                },
            },
        ]

    def get_all(self, with_vectors: bool = True, with_payload: bool = True):
        """记录读取参数并返回 fake Qdrant entries。"""

        self.get_all_calls.append(
            {"with_vectors": with_vectors, "with_payload": with_payload}
        )
        return self.entries


class FakeLightMemAnswerClient:
    """模拟回答 LLM。"""

    def __init__(self) -> None:
        """初始化 fake prompt 调用记录。"""

        self.prompts: list[str] = []

    def create_answer(self, prompt: str) -> str:
        """记录 prompt 并返回固定答案。"""

        self.prompts.append(prompt)
        return "fake lightmem answer"


class FakeOfficialLightMemory:
    """模拟官方 LightMemory.from_config() 入口，避免加载模型和触网。"""

    created_configs: list[dict[str, object]] = []

    @classmethod
    def from_config(cls, config):
        """记录官方 backend 构造配置，并返回可写入和检索的 fake backend。"""

        cls.created_configs.append(config)
        return FakeLightMemoryBackend()


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
    )
    conversation = _lightmem_conversation()

    add_result = method.add([conversation])
    answer = method.get_answer(conversation.questions[0])

    assert add_result.conversation_ids == ["conv-1"]
    assert isinstance(answer, AnswerResult)
    assert answer.answer == "fake lightmem answer"
    assert backend.queries == []
    assert backend.embedding_retriever.get_all_calls == [
        {"with_vectors": True, "with_payload": True}
    ]
    assert "Alice likes jasmine tea." in chat.prompts[0]
    first_message = backend.added_messages[0]["messages"][0]
    assert first_message["time_stamp"] == "2026-01-01"
    assert "timestamp" not in first_message
    assert first_message["speaker_id"] == "speaker_a"
    assert first_message["speaker_name"] == "Alice"
    assert first_message["role"] == "user"


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
    assert [message["content"] for message in last_call["messages"]] == [
        "Jazz is noted.",
        "",
    ]


def test_lightmem_locomo_add_runs_official_offline_update_after_all_turns() -> None:
    """LoCoMo 的 add 完成应包含官方 post-build offline update。"""

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
    )

    method.add([_locomo_style_lightmem_conversation()])

    assert backend.construct_update_calls == [{}]
    assert backend.offline_update_calls == [{"score_threshold": 0.9}]


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
    assert backend.construct_update_calls == []
    assert backend.offline_update_calls == []


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
    )
    conversation = _locomo_style_lightmem_conversation()
    method.add([conversation])

    method.get_answer(conversation.questions[0])

    assert backend.queries == []
    assert backend.text_embedder.embedded_texts == ["What does Alice like?"]
    assert backend.embedding_retriever.get_all_calls == [
        {"with_vectors": True, "with_payload": True}
    ]
    prompt = chat.prompts[0]
    assert "Alice likes jasmine tea." in prompt
    assert "Bob remembered Alice's tea preference." in prompt
    assert "Alice dislikes noisy airports." not in prompt
    assert "Memories for user Alice" in prompt
    assert "Memories for user Bob" in prompt
    assert "[Memory recorded on: 01 January 2026, Thu]" in prompt


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
    """LightMem wrapper 应记录 retrieval/context/answer 的 question-level observation。"""

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

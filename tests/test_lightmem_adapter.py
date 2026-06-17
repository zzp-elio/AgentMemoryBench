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

    def add_memory(self, messages, **kwargs):
        """记录写入消息和 LightMem pipeline 参数。"""

        self.added_messages.append({"messages": messages, "kwargs": kwargs})
        return {"api_call_nums": 0}

    def retrieve(self, query, limit=10, filters=None):
        """记录检索请求并返回 fake memory context。"""

        self.queries.append({"query": query, "limit": limit, "filters": filters})
        return ["2026-01-01 Alice likes tea"]


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
    """构造最小 conversation-QA 样本。"""

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
    assert backend.queries == [
        {"query": "What does Alice like?", "limit": 2, "filters": None}
    ]
    assert "Alice likes tea" in chat.prompts[0]
    first_message = backend.added_messages[0]["messages"][0]
    assert first_message["time_stamp"] == "2026-01-01"
    assert "timestamp" not in first_message
    assert first_message["speaker_id"] == "Alice"
    assert first_message["speaker_name"] == "Alice"
    assert first_message["role"] == "user"


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

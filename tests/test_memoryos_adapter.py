"""测试 MemoryOS 通用产品（memoryos-pypi）适配器。

本文件只做不访问真实 LLM 的单元/集成测试：确认 pypi 引擎加载、per-conversation
物理隔离、pair 粒度 add_memory 注入（含 orphan/dangling 空串容错）、retrieve
剥离全层 formatted_memory 与无写副作用、config pypi 默认参数、source identity
与 registered provider 装配。所有 LLM 调用通过 stub ``client.chat_completion`` 拦截，
embedding 通过 stub ``get_embedding`` 返回固定向量。
"""

from __future__ import annotations

from dataclasses import asdict
import math
from pathlib import Path
import tempfile

import numpy as np
import pytest

from memory_benchmark.config.settings import PathSettings, load_path_settings
from memory_benchmark.core import (
    Conversation,
    GoldAnswerInfo,
    ImageRef,
    Question,
    Session,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    MemoryProvider,
    SessionBatch,
    TurnEvent,
    TurnPair,
    UnitRef,
)
from memory_benchmark.methods import build_memoryos_source_identity
from memory_benchmark.methods import memoryos_adapter as memoryos_adapter_module
from memory_benchmark.methods.memoryos_adapter import (
    MEMORYOS_PROVENANCE_SIDECAR_FILENAME,
    MemoryOS,
    MemoryOSPaperConfig,
    clean_memoryos_conversation_state,
)
from memory_benchmark.methods.registry import MethodBuildContext, _build_memoryos_system
from memory_benchmark.runners.event_stream import (
    GranularityAggregator,
    build_turn_events,
    default_isolation_key,
)


pytestmark = [pytest.mark.integration, pytest.mark.memoryos]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FIXED_EMBEDDING = np.array([0.1, 0.2, 0.3], dtype="float32")


# ---------------------------------------------------------------------- #
# fixture / helper
# ---------------------------------------------------------------------- #


def build_small_conversation() -> Conversation:
    """构造一个短 conversation（2 个 user/assistant pair，不触发 STM 满）。"""

    question = Question(
        question_id="conv-test:q1",
        conversation_id="conv-test",
        text="Where did Alice move?",
        category="2",
    )
    return Conversation(
        conversation_id="conv-test",
        sessions=[
            Session(
                session_id="session_1",
                session_time="2024-01-01",
                turns=[
                    Turn(turn_id="D1:1", speaker="Alice", content="I moved to Seattle."),
                    Turn(turn_id="D1:2", speaker="Bob", content="Seattle sounds great."),
                    Turn(turn_id="D1:3", speaker="Alice", content="I adopted a cat."),
                    Turn(turn_id="D1:4", speaker="Bob", content="That is lovely."),
                ],
            )
        ],
        questions=[question],
        gold_answers={
            question.question_id: GoldAnswerInfo(
                question_id=question.question_id,
                answer="Seattle",
                evidence=["D1:1"],
            )
        },
        metadata={"speaker_a": "Alice", "speaker_b": "Bob"},
    )


def build_longmemeval_conversation() -> Conversation:
    """构造 LongMemEval 风格 conversation（user/assistant role）。"""

    question = Question(
        question_id="lme:q1",
        conversation_id="lme:q1",
        text="What drink does the user prefer?",
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
                        content="I prefer jasmine tea.",
                        normalized_role="user",
                    ),
                    Turn(
                        turn_id="haystack-1:t1",
                        speaker="assistant",
                        content="I will remember that.",
                        normalized_role="assistant",
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


def _stub_pypi_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    """stub pypi get_embedding 返回固定向量，避免加载真实 SentenceTransformer。

    pypi 的 mid_term/long_term 在 import 时 ``from .utils import get_embedding``
    绑定到各自模块命名空间，因此要同时 patch utils / mid_term / long_term 三处。
    """

    package = memoryos_adapter_module._load_memoryos_pypi_classes(load_path_settings())[
        "package"
    ]
    utils_module = __import__(
        "memoryos_pypi_vendor.utils", fromlist=["get_embedding"]
    )
    mid_term_module = __import__(
        "memoryos_pypi_vendor.mid_term", fromlist=["get_embedding"]
    )
    long_term_module = __import__(
        "memoryos_pypi_vendor.long_term", fromlist=["get_embedding"]
    )

    def fake_get_embedding(text: str, **kwargs: object):
        """返回固定向量，使检索点积恒为 1.0 以命中阈值。"""

        return _FIXED_EMBEDDING

    monkeypatch.setattr(utils_module, "get_embedding", fake_get_embedding)
    monkeypatch.setattr(mid_term_module, "get_embedding", fake_get_embedding)
    monkeypatch.setattr(long_term_module, "get_embedding", fake_get_embedding)


def _build_system(tmp_path: Path, **kwargs: object) -> MemoryOS:
    """构造占位 key 的 MemoryOS 实例，不触发真实 API。"""

    return MemoryOS(
        openai_api_key="placeholder-key",
        openai_base_url="https://example.invalid/v1",
        storage_root=tmp_path,
        **kwargs,
    )


def _drive_native_ingest(
    system: MemoryOS,
    conversation: Conversation,
    run_id: str = "memoryos-test",
    granularity: str = "pair",
) -> None:
    """用 v3 事件流驱动 MemoryOS 原生 ingest。

    LongMemEval（role=user/assistant）用 pair 粒度；LoCoMo（role=speaker 名）
    用 session 粒度（pair 聚合按 role=="user" 锚，speaker 数据会全 orphan）。
    """

    isolation_key = default_isolation_key(run_id, conversation.conversation_id)
    events = tuple(build_turn_events(conversation, isolation_key))
    for signal in GranularityAggregator(granularity).aggregate(
        events,
        isolation_key=isolation_key,
    ):
        if isinstance(signal, (TurnPair, SessionBatch)):
            system.ingest(signal)
        elif isinstance(signal, UnitRef):
            system.end_conversation(signal)


# ---------------------------------------------------------------------- #
# T4：config pypi 默认参数与校验
# ---------------------------------------------------------------------- #


def test_default_config_uses_pypi_official_defaults() -> None:
    """默认配置应使用 memoryos-pypi 官方默认参数，而非旧 eval/ LoCoMo 调参。"""

    config = MemoryOSPaperConfig()
    assert config.llm_model == "gpt-4o-mini"
    assert config.embedding_model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert config.short_term_capacity == 10
    assert config.mid_term_capacity == 2000
    assert config.long_term_knowledge_capacity == 100
    assert config.retrieval_queue_capacity == 7
    assert config.mid_term_heat_threshold == 5.0
    assert config.mid_term_similarity_threshold == 0.6
    assert config.top_k_sessions == 5
    assert config.top_k_knowledge == 20


def test_config_manifest_marks_pypi_engine_and_source_mode() -> None:
    """manifest 应标注 pypi 引擎与 wrapper source 模式。"""

    config = MemoryOSPaperConfig()
    manifest = config.to_manifest()
    assert manifest["adapter_version"] == "conversation-qa-v1"
    assert manifest["source_mode"] == "memoryos-pypi-wrapper"
    assert manifest["engine"] == "memoryos-pypi"
    for value in manifest.values():
        if isinstance(value, float):
            assert math.isfinite(value)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("short_term_capacity", 0),
        ("short_term_capacity", -1),
        ("short_term_capacity", True),
        ("mid_term_capacity", 0),
        ("mid_term_capacity", True),
        ("long_term_knowledge_capacity", 0),
        ("retrieval_queue_capacity", -1),
        ("top_k_sessions", 0),
        ("top_k_knowledge", 0),
        ("max_workers", 0),
        ("api_max_retries", -1),
        ("api_max_retries", True),
    ],
)
def test_config_requires_positive_integers(field_name: str, value: object) -> None:
    """整数字段必须满足精确整数类型约束。"""

    with pytest.raises(ConfigurationError, match=field_name):
        MemoryOSPaperConfig(**{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("mid_term_similarity_threshold", -0.1),
        ("mid_term_similarity_threshold", 1.1),
        ("mid_term_similarity_threshold", True),
        ("segment_similarity_threshold", 1.1),
        ("page_similarity_threshold", -0.1),
        ("knowledge_threshold", True),
        ("knowledge_threshold", math.nan),
    ],
)
def test_config_requires_unit_interval_thresholds(
    field_name: str, value: float
) -> None:
    """相似度/阈值字段必须在 [0, 1]。"""

    with pytest.raises(ConfigurationError, match=field_name):
        MemoryOSPaperConfig(**{field_name: value})


def test_config_requires_non_negative_heat_threshold() -> None:
    """mid_term_heat_threshold 不得为负。"""

    with pytest.raises(ConfigurationError, match="mid_term_heat_threshold"):
        MemoryOSPaperConfig(mid_term_heat_threshold=-0.1)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("llm_model", ""),
        ("llm_model", "   "),
        ("llm_model", None),
        ("embedding_model_name", ""),
        ("profile_name", None),
        ("longmemeval_prompt_profile", ""),
    ],
)
def test_config_requires_non_empty_strings(field_name: str, value: object) -> None:
    """模型名与 profile 字段必须是非空字符串。"""

    with pytest.raises(ConfigurationError, match=field_name):
        MemoryOSPaperConfig(**{field_name: value})


# ---------------------------------------------------------------------- #
# T1：引擎加载 + per-conversation 隔离 + source identity
# ---------------------------------------------------------------------- #


def test_build_memoryos_source_identity_hashes_pypi_package() -> None:
    """source identity 应 hash memoryos-pypi/*.py，而非旧 eval/*.py。"""

    first = build_memoryos_source_identity()
    second = build_memoryos_source_identity()
    assert first == second
    assert len(first["source_sha256"]) == 64
    assert len(first["vendored_source_sha256"]) == 64
    assert first["wrapper_path"] == "src/memory_benchmark/methods/memoryos_adapter.py"
    assert first["source_mode"] == "vendored-memoryos-pypi-with-framework-wrapper"
    assert first["vendored_source_mode"] == "vendored-memoryos-pypi"
    assert first["file_count"] == len(first["files"])
    assert first["source_sha256"] != first["vendored_source_sha256"]
    # 全部文件来自 memoryos-pypi/ 或根 README/LICENSE，无 eval/ 残留
    assert all(
        path.startswith("memoryos-pypi/") or path in ("README.md", "LICENSE")
        for path in first["files"]
    )
    assert all(not path.startswith("eval/") for path in first["files"])
    assert all("__pycache__" not in path for path in first["files"])


def test_source_identity_wrapper_bytes_change_only_wrapper_component() -> None:
    """wrapper 字节变化时，应只改变 wrapper 组件和组合 source hash。"""

    current = build_memoryos_source_identity()
    first = memoryos_adapter_module._build_memoryos_source_identity_from_components(
        vendored_files=current["files"],
        vendored_source_sha256=current["vendored_source_sha256"],
        wrapper_logical_path=current["wrapper_path"],
        wrapper_bytes=b"wrapper version one",
    )
    second = memoryos_adapter_module._build_memoryos_source_identity_from_components(
        vendored_files=current["files"],
        vendored_source_sha256=current["vendored_source_sha256"],
        wrapper_logical_path=current["wrapper_path"],
        wrapper_bytes=b"wrapper version two",
    )
    assert first["vendored_source_sha256"] == second["vendored_source_sha256"]
    assert first["wrapper_sha256"] != second["wrapper_sha256"]
    assert first["source_sha256"] != second["source_sha256"]


def test_pypi_engine_loads_as_named_package_without_polluting_utils() -> None:
    """pypi 应加载为 memoryos_pypi_vendor 命名包，不污染全局 utils 模块。"""

    classes = memoryos_adapter_module._load_memoryos_pypi_classes(load_path_settings())
    assert classes["Memoryos"] is not None
    assert classes["package"] is not None
    # 命名包存在
    import sys

    assert "memoryos_pypi_vendor" in sys.modules
    # 全局 utils 不被 pypi 的 utils 污染（pypi 用命名包子模块）
    assert "utils" not in sys.modules or sys.modules.get("utils") is not sys.modules.get(
        "memoryos_pypi_vendor.utils"
    )


def test_per_conversation_backends_are_physically_isolated(tmp_path: Path) -> None:
    """两个 conversation 应使用独立 data_storage_path，状态互不串。"""

    system = _build_system(tmp_path)
    conv_a = build_small_conversation()
    conv_b = Conversation(
        conversation_id="conv-other",
        sessions=[
            Session(
                session_id="s1",
                session_time="2024-02-02",
                turns=[
                    Turn(turn_id="O:1", speaker="Carol", content="I live in Tokyo."),
                    Turn(turn_id="O:2", speaker="Dave", content="Tokyo is busy."),
                ],
            )
        ],
        metadata={"speaker_a": "Carol", "speaker_b": "Dave"},
    )
    system.add([conv_a])
    system.add([conv_b])

    backend_a = system.get_debug_state("conv-test")
    backend_b = system.get_debug_state("conv-other")
    assert backend_a is not backend_b
    assert backend_a.user_id != backend_b.user_id
    assert backend_a.data_storage_path != backend_b.data_storage_path
    # short_term 内容隔离
    a_pages = backend_a.short_term_memory.get_all()
    b_pages = backend_b.short_term_memory.get_all()
    assert any("Seattle" in p.get("user_input", "") for p in a_pages)
    assert any("Tokyo" in p.get("user_input", "") for p in b_pages)
    assert not any("Tokyo" in p.get("user_input", "") for p in a_pages)


def test_clean_retry_removes_only_target_conversation_directory(tmp_path: Path) -> None:
    """clean-retry 应只删目标 conversation 目录，保留 sibling。"""

    system = _build_system(tmp_path)
    conv_a = build_small_conversation()
    conv_b = Conversation(
        conversation_id="conv-other",
        sessions=[
            Session(
                session_id="s1",
                session_time="2024-02-02",
                turns=[
                    Turn(turn_id="O:1", speaker="Carol", content="I live in Tokyo."),
                    Turn(turn_id="O:2", speaker="Dave", content="Tokyo is busy."),
                ],
            )
        ],
        metadata={"speaker_a": "Carol", "speaker_b": "Dave"},
    )
    system.add([conv_a, conv_b])
    target_dir = system.storage_root / "conv-test"
    sibling_dir = system.storage_root / "conv-other"
    assert target_dir.is_dir()
    assert sibling_dir.is_dir()

    clean_memoryos_conversation_state(system.storage_root, "conv-test")

    assert not target_dir.exists()
    assert sibling_dir.exists()


def test_default_storage_root_is_unique_per_instance(tmp_path: Path) -> None:
    """默认 storage_root 应按实例隔离。"""

    first = MemoryOS(
        openai_api_key="placeholder-key",
        openai_base_url="https://example.invalid/v1",
        path_settings=PathSettings(
            project_root=PROJECT_ROOT,
            data_root=PROJECT_ROOT / "data",
            models_root=PROJECT_ROOT / "models",
            outputs_root=tmp_path,
            third_party_root=PROJECT_ROOT / "third_party",
            third_party_benchmarks_root=PROJECT_ROOT / "third_party" / "benchmarks",
            third_party_methods_root=PROJECT_ROOT / "third_party" / "methods",
        ),
    )
    second = MemoryOS(
        openai_api_key="placeholder-key",
        openai_base_url="https://example.invalid/v1",
        path_settings=PathSettings(
            project_root=PROJECT_ROOT,
            data_root=PROJECT_ROOT / "data",
            models_root=PROJECT_ROOT / "models",
            outputs_root=tmp_path,
            third_party_root=PROJECT_ROOT / "third_party",
            third_party_benchmarks_root=PROJECT_ROOT / "third_party" / "benchmarks",
            third_party_methods_root=PROJECT_ROOT / "third_party" / "methods",
        ),
    )
    assert first.storage_root != second.storage_root


def test_registry_builds_native_v3_provider(tmp_path: Path) -> None:
    """registry 应直接构造 MemoryOS 原生 v3 provider。"""

    provider = _build_memoryos_system(
        MethodBuildContext(
            config=MemoryOSPaperConfig(),
            openai_settings=type(
                "S",
                (),
                {"api_key": "sk-test", "base_url": "https://example.invalid/v1"},
            )(),
            path_settings=load_path_settings(),
            storage_root=tmp_path,
            benchmark_name="locomo",
        )
    )
    assert isinstance(provider, MemoryProvider)
    # registry 按 benchmark 设：locomo→session（speaker 数据），longmemeval→pair
    assert provider.consume_granularity == "session"
    assert provider.provenance_granularity == "turn"


# ---------------------------------------------------------------------- #
# T2：pair 粒度 add_memory 注入（含 orphan/dangling 空串容错）
# ---------------------------------------------------------------------- #


def test_conversation_to_memory_pages_pairs_by_role() -> None:
    """conversation 应按 user/assistant role 配对成 QA pair。"""

    conversation = build_small_conversation()
    pages = MemoryOS.conversation_to_memory_pages(conversation)
    assert pages == [
        {
            "user_input": "I moved to Seattle.",
            "agent_response": "Seattle sounds great.",
            "timestamp": "2024-01-01",
        },
        {
            "user_input": "I adopted a cat.",
            "agent_response": "That is lovely.",
            "timestamp": "2024-01-01",
        },
    ]


def test_conversation_to_memory_pages_handles_dangling_user() -> None:
    """dangling user（无后续 assistant）应 agent_response 留空。"""

    conversation = Conversation(
        conversation_id="conv-dangling",
        sessions=[
            Session(
                session_id="s1",
                session_time="2024-01-01",
                turns=[
                    Turn(turn_id="t1", speaker="user", content="hello", normalized_role="user"),
                    Turn(turn_id="t2", speaker="assistant", content="hi", normalized_role="assistant"),
                    Turn(turn_id="t3", speaker="user", content="orphan user", normalized_role="user"),
                ],
            )
        ],
        metadata={},
    )
    pages = MemoryOS.conversation_to_memory_pages(conversation)
    assert pages[-1] == {
        "user_input": "orphan user",
        "agent_response": "",
        "timestamp": "2024-01-01",
    }


def test_conversation_to_memory_pages_handles_orphan_assistant() -> None:
    """orphan assistant（无前置 user）应 user_input 留空。"""

    conversation = Conversation(
        conversation_id="conv-orphan",
        sessions=[
            Session(
                session_id="s1",
                session_time="2024-01-01",
                turns=[
                    Turn(turn_id="t1", speaker="assistant", content="orphan assistant", normalized_role="assistant"),
                    Turn(turn_id="t2", speaker="user", content="hello", normalized_role="user"),
                    Turn(turn_id="t3", speaker="assistant", content="hi", normalized_role="assistant"),
                ],
            )
        ],
        metadata={},
    )
    pages = MemoryOS.conversation_to_memory_pages(conversation)
    assert pages[0] == {
        "user_input": "",
        "agent_response": "orphan assistant",
        "timestamp": "2024-01-01",
    }


def test_add_writes_short_term_without_gold(tmp_path: Path) -> None:
    """add 应只写公开 QA pair，不写 gold answer/evidence。"""

    conversation = build_small_conversation()
    system = _build_system(tmp_path)
    result = system.add([conversation])
    assert result.conversation_ids == ["conv-test"]
    backend = system.get_debug_state("conv-test")
    pages = backend.short_term_memory.get_all()
    assert len(pages) == 2
    assert "answer" not in pages[0]
    assert "gold_answer" not in pages[0]
    assert "evidence" not in str(pages)
    assert pages[0]["user_input"] == "I moved to Seattle."


def test_native_session_ingest_matches_bridge_pages(tmp_path: Path) -> None:
    """LoCoMo 数据用 session 粒度，native ingest 应与 bridge add 等价。

    LoCoMo Turn normalized_role=None，build_turn_events role=speaker 名，
    pair 聚合按 role=="user" 锚会全 orphan；session 粒度把整个 session 一次
    投递，adapter 内部 conversation_to_memory_pages 按 speaker 配对。
    """

    conversation = build_small_conversation()
    bridge = _build_system(tmp_path / "bridge")
    native = _build_system(tmp_path / "native", consume_granularity="session")
    bridge.add([conversation])
    _drive_native_ingest(native, conversation, granularity="session")
    assert isinstance(native, MemoryProvider)
    assert native.consume_granularity == "session"
    native_pages = [dict(p) for p in native.get_debug_state("conv-test").short_term_memory.get_all()]
    bridge_pages = [dict(p) for p in bridge.get_debug_state("conv-test").short_term_memory.get_all()]
    assert native_pages == bridge_pages


def test_native_pair_ingest_longmemeval_matches_bridge(tmp_path: Path) -> None:
    """LongMemEval 数据（role=user/assistant）用 pair 粒度，与 bridge add 等价。"""

    conversation = build_longmemeval_conversation()
    bridge = _build_system(tmp_path / "bridge")
    native = _build_system(tmp_path / "native", consume_granularity="pair")
    bridge.add([conversation])
    _drive_native_ingest(native, conversation, granularity="pair")
    native_pages = [dict(p) for p in native.get_debug_state("lme:q1").short_term_memory.get_all()]
    bridge_pages = [dict(p) for p in bridge.get_debug_state("lme:q1").short_term_memory.get_all()]
    assert native_pages == bridge_pages
    assert native_pages[0]["user_input"] == "I prefer jasmine tea."
    assert native_pages[0]["agent_response"] == "I will remember that."


def test_native_pair_ingest_handles_orphan_and_dangling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pair ingest 应处理 orphan assistant 与 dangling user，不崩不丢。"""

    _stub_pypi_embedding(monkeypatch)
    conversation = Conversation(
        conversation_id="conv-mixed",
        sessions=[
            Session(
                session_id="s1",
                session_time="2024-01-01",
                turns=[
                    Turn(turn_id="t1", speaker="assistant", content="orphan assistant", normalized_role="assistant"),
                    Turn(turn_id="t2", speaker="user", content="hello", normalized_role="user"),
                    Turn(turn_id="t3", speaker="assistant", content="hi", normalized_role="assistant"),
                    Turn(turn_id="t4", speaker="user", content="dangling user", normalized_role="user"),
                ],
            )
        ],
        metadata={},
    )
    system = _build_system(tmp_path)
    _drive_native_ingest(system, conversation, granularity="pair")
    backend = system.get_debug_state("conv-mixed")
    pages = backend.short_term_memory.get_all()
    # orphan assistant + (user,assistant) pair + dangling user = 3 条
    assert len(pages) == 3
    assert pages[0]["user_input"] == ""
    assert pages[0]["agent_response"] == "orphan assistant"
    assert pages[1]["user_input"] == "hello"
    assert pages[1]["agent_response"] == "hi"
    assert pages[2]["user_input"] == "dangling user"
    assert pages[2]["agent_response"] == ""


# ---------------------------------------------------------------------- #
# T3 核心：retrieve 剥离全层 formatted_memory + 无写副作用
# ---------------------------------------------------------------------- #


def test_retrieve_assembles_all_memory_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """retrieve 的 formatted_memory 必须覆盖短/中/长 profile/user_knowledge/assistant_knowledge 全层。

    漏任何一层 = 记忆不完整 = 数字失真（ws02.5(c) 完整性，本迁移核心验收点）。
    """

    _stub_pypi_embedding(monkeypatch)
    conversation = build_small_conversation()
    system = _build_system(tmp_path)
    system.add([conversation])
    backend = system.get_debug_state(conversation.conversation_id)
    # stub LLM，防止 add_memory 后续任何 LLM 触发
    backend.client.chat_completion = lambda **kw: "stubbed"

    # 注入中期 session（add_session 内部用 stub 的 get_embedding）
    backend.mid_term_memory.add_session(
        summary="Alice relocation and pet",
        details=[
            {
                "user_input": "I moved to Seattle.",
                "agent_response": "Seattle sounds great.",
                "timestamp": "2024-01-01",
            }
        ],
    )
    # 注入长期 profile + user knowledge + assistant knowledge
    backend.user_long_term_memory.update_user_profile(
        backend.user_id, "Alice is a hiking enthusiast.", merge=False
    )
    backend.user_long_term_memory.add_user_knowledge("Alice works as a software engineer.")
    backend.assistant_long_term_memory.add_assistant_knowledge("Bob knows Seattle parks.")

    result = system.retrieve(conversation.questions[0])
    formatted = result.metadata["answer_context"]

    # 短期层
    assert "I moved to Seattle." in formatted
    assert "【Historical Memory】" in formatted
    # 中期层（retrieved_pages）
    assert "Conversation chain overview" in formatted
    # 长期 profile 层
    assert "【Alice Profile】" in formatted
    assert "Alice is a hiking enthusiast." in formatted
    # 长期 user knowledge 层
    assert "【Relevant Alice Knowledge Entries】" in formatted
    assert "Alice works as a software engineer." in formatted
    # 长期 assistant knowledge 层
    assert "【Assistant Knowledge Base】" in formatted
    assert "Bob knows Seattle parks." in formatted
    # metadata 计数
    assert result.metadata["method"] == "MemoryOS"
    assert result.metadata["retrieval_profile"] == "memoryos_pypi_retrieve"
    assert result.metadata["retrieved_page_count"] >= 1
    assert result.metadata["retrieved_user_knowledge_count"] >= 1
    assert result.metadata["retrieved_assistant_knowledge_count"] >= 1


def test_retrieve_has_no_write_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """retrieve 绝不能触发 add_memory 写副作用，记忆内容前后不变。

    这是 plan 红线："retrieve 零写副作用：绝不触发步骤 10 的 add_memory"。
    注：pypi retrieve_context 内部 search_sessions 会更新 mid_term 访问统计
    （N_visit/last_visit_time/H_segment）并 save——这是 MemoryOS 检索算法固有
    行为（用于 LFU/heat），非 add_memory 写副作用，不在本断言范围。
    """

    _stub_pypi_embedding(monkeypatch)
    conversation = build_small_conversation()
    system = _build_system(tmp_path)
    system.add([conversation])
    backend = system.get_debug_state(conversation.conversation_id)
    backend.client.chat_completion = lambda **kw: "stubbed"
    # 注入中期 session 让 retrieve_context 有内容可检索
    backend.mid_term_memory.add_session(
        summary="Alice relocation",
        details=[
            {
                "user_input": "I moved to Seattle.",
                "agent_response": "Seattle sounds great.",
                "timestamp": "2024-01-01",
            }
        ],
    )
    backend.user_long_term_memory.add_user_knowledge("Alice works as a engineer.")

    # spy add_memory
    add_memory_calls: list[tuple] = []
    original_add_memory = backend.add_memory

    def spy_add_memory(*args, **kwargs):
        """记录 add_memory 调用，验证 retrieve 不触发写副作用。"""

        add_memory_calls.append((args, kwargs))
        return original_add_memory(*args, **kwargs)

    backend.add_memory = spy_add_memory

    # 记录 retrieve 前记忆内容快照
    pre_short = [dict(p) for p in backend.short_term_memory.get_all()]
    pre_profile = backend.user_long_term_memory.get_raw_user_profile(backend.user_id)
    pre_user_kb = [dict(k) for k in backend.user_long_term_memory.get_user_knowledge()]
    pre_assistant_kb = [
        dict(k) for k in backend.assistant_long_term_memory.get_assistant_knowledge()
    ]

    system.retrieve(conversation.questions[0])

    # 核心断言：add_memory 未被调用
    assert add_memory_calls == [], "retrieve must not trigger add_memory write side-effect"

    # 记忆内容不变（short_term / profile / user_knowledge / assistant_knowledge）
    post_short = [dict(p) for p in backend.short_term_memory.get_all()]
    post_profile = backend.user_long_term_memory.get_raw_user_profile(backend.user_id)
    post_user_kb = [dict(k) for k in backend.user_long_term_memory.get_user_knowledge()]
    post_assistant_kb = [
        dict(k) for k in backend.assistant_long_term_memory.get_assistant_knowledge()
    ]
    assert post_short == pre_short
    assert post_profile == pre_profile
    assert len(post_user_kb) == len(pre_user_kb)
    assert len(post_assistant_kb) == len(pre_assistant_kb)


def test_retrieve_returns_non_empty_formatted_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """retrieve 应返回非空 formatted_memory（即使无中期命中，短期层也要回）。"""

    _stub_pypi_embedding(monkeypatch)
    conversation = build_small_conversation()
    system = _build_system(tmp_path)
    system.add([conversation])
    result = system.retrieve(conversation.questions[0])
    assert result.metadata["answer_context"]
    assert "I moved to Seattle." in result.metadata["answer_context"]


def test_retrieve_native_returns_retrieval_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """v3 RetrievalQuery 口径应返回 RetrievalResult。"""

    _stub_pypi_embedding(monkeypatch)
    conversation = build_small_conversation()
    system = _build_system(tmp_path, consume_granularity="session")
    _drive_native_ingest(system, conversation, granularity="session")
    from memory_benchmark.core.provider_protocol import RetrievalQuery

    query = RetrievalQuery(
        query_text="Where did Alice move?",
        isolation_key=default_isolation_key("memoryos-test", conversation.conversation_id),
        question_time=None,
        top_k=5,
        purpose="qa",
    )
    result = system.retrieve(query)
    from memory_benchmark.core.provider_protocol import RetrievalResult

    assert isinstance(result, RetrievalResult)
    assert result.formatted_memory
    assert "I moved to Seattle." in result.formatted_memory


def test_retrieve_skips_answer_llm_and_add_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """retrieve 跳过 get_response 步骤 8-9 答题 LLM 与步骤 10 add_memory。

    retrieve 只调 retrieve_context（纯 embedding），不调 client.chat_completion
    （答题 LLM），不调 add_memory。用 spy 验证两者均未被触达。
    """

    _stub_pypi_embedding(monkeypatch)
    conversation = build_small_conversation()
    system = _build_system(tmp_path)
    system.add([conversation])
    backend = system.get_debug_state(conversation.conversation_id)
    # spy chat_completion（答题 LLM）
    llm_calls: list[dict] = []
    backend.client.chat_completion = lambda **kw: (llm_calls.append(kw) or "stubbed")
    # spy add_memory
    add_calls: list[tuple] = []
    original_add = backend.add_memory
    backend.add_memory = lambda *a, **k: (add_calls.append((a, k)) or original_add(*a, **k))

    system.retrieve(conversation.questions[0])

    assert llm_calls == [], "retrieve must not call answer LLM (step 8-9)"
    assert add_calls == [], "retrieve must not call add_memory (step 10)"


def test_retrieve_requires_conversation_to_be_added_first(tmp_path: Path) -> None:
    """retrieve 在 conversation_id 未写入时必须报配置错误。"""

    system = _build_system(tmp_path)
    question = Question(
        question_id="missing:q1",
        conversation_id="missing",
        text="What does Alice remember?",
    )
    with pytest.raises(ConfigurationError):
        system.retrieve(question)


# ---------------------------------------------------------------------- #
# T2 补充：estimate_add_workload
# ---------------------------------------------------------------------- #


def test_estimate_add_workload_counts_pages_and_update_batches() -> None:
    """add 前应能估算 page 数和会触发的 MemoryOS 更新批次数。"""

    conversation = build_small_conversation()
    default_estimate = MemoryOS.estimate_add_workload(conversation, MemoryOSPaperConfig())
    small_capacity_estimate = MemoryOS.estimate_add_workload(
        conversation,
        MemoryOSPaperConfig(short_term_capacity=1),
    )
    assert default_estimate.page_count == 2
    assert default_estimate.update_batch_count == 0
    assert default_estimate.remaining_short_term_pages == 2
    assert not default_estimate.will_trigger_updates
    assert small_capacity_estimate.page_count == 2
    assert small_capacity_estimate.update_batch_count == 2
    assert small_capacity_estimate.remaining_short_term_pages == 0
    assert small_capacity_estimate.will_trigger_updates


# ---------------------------------------------------------------------- #
# T1 补充：load_existing_conversation_state（resume）
# ---------------------------------------------------------------------- #


def test_load_existing_conversation_state_attaches_without_duplicate_add(
    tmp_path: Path,
) -> None:
    """已写入的 conversation 状态应能重新 attach，不重复 add。"""

    conversation = build_small_conversation()
    storage_root = tmp_path / "memoryos_state"
    first = _build_system(storage_root)
    first.add([conversation])
    pre_count = len(first.get_debug_state("conv-test").short_term_memory.get_all())

    second = _build_system(storage_root)
    second.load_existing_conversation_state(conversation)
    backend = second.get_debug_state("conv-test")
    post_count = len(backend.short_term_memory.get_all())
    assert post_count == pre_count


def test_load_existing_conversation_state_requires_state_directory(tmp_path: Path) -> None:
    """attach 不存在的 conversation 状态时必须报错。"""

    conversation = build_small_conversation()
    system = _build_system(tmp_path)
    with pytest.raises(ConfigurationError):
        system.load_existing_conversation_state(conversation)


def test_image_ingest_uses_shared_caption_text_and_ignores_query(tmp_path: Path) -> None:
    """MemoryOS 注入应使用共享 photo tag，且不读取数据构造 query。"""

    conversation = build_small_conversation()
    conversation.sessions[0].turns[0].images = [ImageRef(caption="a blue bicycle")]
    conversation.sessions[0].turns[0].metadata["query"] = "hidden construction hint"
    system = _build_system(tmp_path)

    system.add(conversation)

    page = system.get_debug_state("conv-test").short_term_memory.get_all()[0]
    assert page["user_input"] == (
        "I moved to Seattle. [Sharing image that shows: a blue bicycle]"
    )
    assert "hidden construction hint" not in page["user_input"]


def test_locomo_formatted_memory_and_native_prompt_restore_speaker_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LoCoMo 检索出口与 native prompt 应从持久化映射恢复真实 speaker。"""

    _stub_pypi_embedding(monkeypatch)
    conversation = build_small_conversation()
    system = _build_system(
        tmp_path,
        consume_granularity="session",
        benchmark_name="locomo",
    )
    _drive_native_ingest(system, conversation, granularity="session")
    query = memoryos_adapter_module.RetrievalQuery(
        query_text="Where did Alice move?",
        isolation_key=default_isolation_key("memoryos-test", "conv-test"),
        question_time=None,
        top_k=5,
        purpose="qa",
        source_question=conversation.questions[0],
    )

    result = system.retrieve(query)

    assert "Alice: I moved to Seattle." in result.formatted_memory
    assert "Bob: Seattle sounds great." in result.formatted_memory
    assert result.prompt_messages is not None
    assert "role-playing as Bob" in result.prompt_messages[0].content
    assert "Recent conversation between Alice and Bob" in result.prompt_messages[1].content


def test_non_locomo_formatted_memory_keeps_generic_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 LoCoMo benchmark 不得引入真实 speaker 身份替换。"""

    _stub_pypi_embedding(monkeypatch)
    conversation = build_longmemeval_conversation()
    system = _build_system(tmp_path, benchmark_name="longmemeval")
    system.add(conversation)

    result = system.retrieve(conversation.questions[0])

    assert "User: I prefer jasmine tea." in result.metadata["answer_context"]
    assert "Assistant: I will remember that." in result.metadata["answer_context"]


def test_retrieved_page_maps_exactly_to_all_duplicate_source_turn_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """重复 page 文本必须返回全部公开来源 id，不能按 rank 任选一条。"""

    _stub_pypi_embedding(monkeypatch)
    conversation = build_small_conversation()
    conversation.sessions[0].turns[2].content = "I moved to Seattle."
    conversation.sessions[0].turns[3].content = "Seattle sounds great."
    system = _build_system(
        tmp_path,
        consume_granularity="session",
        benchmark_name="locomo",
    )
    _drive_native_ingest(system, conversation, granularity="session")
    backend = system.get_debug_state("conv-test")
    backend.mid_term_memory.add_session(
        summary="Seattle",
        details=[
            {
                "user_input": "I moved to Seattle.",
                "agent_response": "Seattle sounds great.",
                "timestamp": "2024-01-01",
            }
        ],
    )
    query = memoryos_adapter_module.RetrievalQuery(
        query_text="Seattle",
        isolation_key=default_isolation_key("memoryos-test", "conv-test"),
        question_time=None,
        top_k=5,
        purpose="qa",
        source_question=conversation.questions[0],
    )

    result = system.retrieve(query)

    assert result.items
    assert result.items[0].source_turn_ids == ("D1:1", "D1:2", "D1:3", "D1:4")
    assert result.items[0].metadata["provenance_match"] == "exact_page_text"


def test_resume_rejects_state_without_required_sidecar(tmp_path: Path) -> None:
    """旧状态缺 sidecar 时必须 fail-fast，不能伪造 provenance 或 speaker。"""

    conversation = build_small_conversation()
    storage_root = tmp_path / "state"
    first = _build_system(storage_root)
    first.add(conversation)
    sidecar = storage_root / "conv-test" / MEMORYOS_PROVENANCE_SIDECAR_FILENAME
    sidecar.unlink()
    resumed = _build_system(storage_root)

    with pytest.raises(ConfigurationError, match="predates the required provenance sidecar"):
        resumed.load_existing_conversation_state(conversation)


def test_retrieval_branch_exception_is_audited_as_degraded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """被 pypi 吞掉的检索分支异常必须进入公开降级 metadata。"""

    _stub_pypi_embedding(monkeypatch)
    conversation = build_small_conversation()
    system = _build_system(tmp_path)
    system.add(conversation)
    backend = system.get_debug_state("conv-test")

    def fail_mid_term(*args: object, **kwargs: object) -> list[object]:
        """模拟 embedding 检索分支异常。"""

        raise RuntimeError("embedding failed")

    backend.retriever._retrieve_mid_term_context = fail_mid_term

    result = system.retrieve(conversation.questions[0])

    assert result.metadata["degraded_retrieval"] is True
    assert result.metadata["degraded_retrieval_count"] == 1
    assert result.metadata["degraded_retrieval_stages"] == [
        "_retrieve_mid_term_context"
    ]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])

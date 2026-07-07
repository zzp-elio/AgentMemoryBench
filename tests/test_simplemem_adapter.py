"""测试 SimpleMem adapter 的配置、资源和 source identity。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.config import load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.provider_protocol import TurnEvent, UnitRef
from memory_benchmark.methods.simplemem_adapter import (
    SIMPLEMEM_OFFICIAL_PROFILE_NAME,
    SimpleMem,
    SimpleMemConfig,
    build_simplemem_source_identity,
    parse_simplemem_timestamp,
)


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

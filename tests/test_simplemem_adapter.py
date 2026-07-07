"""测试 SimpleMem adapter 的配置、资源和 source identity。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.config import load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.simplemem_adapter import (
    SIMPLEMEM_OFFICIAL_PROFILE_NAME,
    SimpleMem,
    SimpleMemConfig,
    build_simplemem_source_identity,
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

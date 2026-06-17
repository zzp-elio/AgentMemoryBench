"""配置 profile 加载测试。

本文件验证 TOML profile 读取、严格字段校验、`profile_name` 自动填充，以及
OpenAI 配置的延迟加载行为。测试不会暴露任何密钥信息。
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from memory_benchmark.config.profiles import load_typed_profile
from memory_benchmark.config.settings import load_openai_settings, load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.mem0_adapter import Mem0Config
from memory_benchmark.methods.memoryos_adapter import MemoryOSPaperConfig


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_toml(path: Path, content: str) -> None:
    """写入格式化后的 TOML 测试内容。"""

    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")


def test_load_typed_profile_builds_mem0_smoke_profile_from_section(tmp_path: Path) -> None:
    """TOML 的 `[smoke]` section 应能构造 `Mem0Config.smoke()`。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [smoke]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 10
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        """,
    )

    config = load_typed_profile(toml_path, "smoke", Mem0Config)

    assert config == Mem0Config.smoke()


def test_load_typed_profile_requires_requested_section(tmp_path: Path) -> None:
    """请求不存在的 profile 时应抛出配置异常。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [official-full]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 200
        max_workers = 10
        ingestion_chunk_size = 1
        infer = true
        """,
    )

    with pytest.raises(ConfigurationError, match="smoke"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_typed_profile_rejects_unknown_key(tmp_path: Path) -> None:
    """TOML section 中出现 dataclass 未定义的 key 时应显式失败。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [smoke]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 10
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        unexpected = "value"
        """,
    )

    with pytest.raises(ConfigurationError, match="unexpected"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_typed_profile_rejects_wrong_field_type(tmp_path: Path) -> None:
    """字段类型不匹配时应包装为 `ConfigurationError`。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [smoke]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = "1536"
        reader_model = "gpt-4o-mini"
        top_k = 10
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        """,
    )

    with pytest.raises(ConfigurationError, match="embedding_dimensions"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_typed_profile_autofills_profile_name_and_rejects_duplicate(tmp_path: Path) -> None:
    """`profile_name` 应由 section 名自动填充，且 TOML 不得重复声明。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        [smoke]
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 10
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        profile_name = "custom"
        """,
    )

    with pytest.raises(ConfigurationError, match="profile_name"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_typed_profile_rejects_root_without_section(tmp_path: Path) -> None:
    """TOML 顶层如果不是 section/table，应拒绝加载。"""

    toml_path = tmp_path / "mem0.toml"
    _write_toml(
        toml_path,
        """
        extraction_model = "gpt-4o-mini"
        embedding_model = "text-embedding-3-small"
        embedding_dimensions = 1536
        reader_model = "gpt-4o-mini"
        top_k = 10
        max_workers = 1
        ingestion_chunk_size = 1
        infer = true
        """,
    )

    with pytest.raises(ConfigurationError, match="section"):
        load_typed_profile(toml_path, "smoke", Mem0Config)


def test_load_openai_settings_reads_key_and_base_url_from_env_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`load_openai_settings()` 应从指定 `.env` 延迟读取密钥和 base URL。"""

    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_KEY=sk-test-from-file\nBASE_URL=https://example.test/v1\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    settings = load_openai_settings(project_root=tmp_path, env_file=env_file)

    assert settings.api_key == "sk-test-from-file"
    assert settings.base_url == "https://example.test/v1"
    assert settings.model == "gpt-4o-mini"


def test_load_typed_profile_builds_memoryos_official_full_profile_from_project_toml() -> None:
    """项目内的 MemoryOS official_full profile 应加载为固定论文参数。"""

    config = load_typed_profile(
        PROJECT_ROOT / "configs" / "methods" / "memoryos.toml",
        "official_full",
        MemoryOSPaperConfig,
    )

    assert config.profile_name == "official_full"
    assert config.short_term_capacity == 7
    assert config.retrieval_top_m_segments == 5
    assert config.retrieval_queue_capacity == 10
    assert config.max_workers == 1


def test_load_typed_profile_builds_matching_memoryos_smoke_and_official_profiles() -> None:
    """MemoryOS smoke 与 official_full 应只在自动填充的 profile_name 上不同。"""

    toml_path = PROJECT_ROOT / "configs" / "methods" / "memoryos.toml"
    smoke = load_typed_profile(toml_path, "smoke", MemoryOSPaperConfig)
    official_full = load_typed_profile(toml_path, "official_full", MemoryOSPaperConfig)

    assert smoke.profile_name == "smoke"
    assert official_full.profile_name == "official_full"
    assert smoke.embedding_model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert official_full.embedding_model_name == "sentence-transformers/all-MiniLM-L6-v2"
    assert {
        key: value
        for key, value in smoke.to_manifest().items()
        if key != "profile_name"
    } == {
        key: value
        for key, value in official_full.to_manifest().items()
        if key != "profile_name"
    }


def test_load_path_settings_exposes_phase_e_project_roots() -> None:
    """`load_path_settings(PROJECT_ROOT)` 应暴露 Phase E 需要的 data 和 third_party 目录。"""

    paths = load_path_settings(PROJECT_ROOT)

    assert paths.project_root == PROJECT_ROOT
    assert paths.data_root == PROJECT_ROOT / "data"
    assert paths.third_party_benchmarks_root == PROJECT_ROOT / "third_party" / "benchmarks"
    assert paths.third_party_methods_root == PROJECT_ROOT / "third_party" / "methods"

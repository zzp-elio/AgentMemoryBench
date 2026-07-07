"""SimpleMem text backend 的协议 v3 adapter。

T1 先落地配置、资源校验、source identity 和 registry 骨架；后续 task 会把
`SimpleMem` 类补齐为真实 ingest/retrieve provider。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re
from typing import Any

from memory_benchmark.config import PathSettings, load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    TurnEvent,
    UnitRef,
)


SIMPLEMEM_ADAPTER_VERSION = "simplemem-text-v1"
SIMPLEMEM_METHOD_DIRECTORY = "SimpleMem"
SIMPLEMEM_OFFICIAL_PROFILE_NAME = "official-text-v1"
SIMPLEMEM_WRAPPER_LOGICAL_PATH = "src/memory_benchmark/methods/simplemem_adapter.py"
SIMPLEMEM_SOURCE_MODE = "vendored-simplemem-text-plus-wrapper"
_LOCOMO_TIMESTAMP_PATTERN = re.compile(
    r"^\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*"
    r"(?P<period>am|pm)\s+on\s+"
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+),\s*"
    r"(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
SimpleMemSystemFactory = Callable[[str, Path], Any]


@dataclass(frozen=True)
class SimpleMemConfig:
    """SimpleMem text backend 运行 profile。"""

    llm_model: str
    embedding_model_path: str
    embedding_dimension: int
    window_size: int
    overlap_size: int
    semantic_top_k: int
    keyword_top_k: int
    structured_top_k: int
    max_workers: int
    api_timeout_seconds: float = 60.0
    api_max_retries: int = 8
    enable_planning: bool = True
    enable_reflection: bool = True
    max_reflection_rounds: int = 2
    enable_parallel_processing: bool = True
    enable_parallel_retrieval: bool = True
    profile_name: str = SIMPLEMEM_OFFICIAL_PROFILE_NAME

    def __post_init__(self) -> None:
        """强校验影响实验语义的 SimpleMem 参数。"""

        if not self.llm_model.strip():
            raise ConfigurationError("SimpleMem llm_model is required")
        if not self.embedding_model_path.strip():
            raise ConfigurationError("SimpleMem embedding_model_path is required")
        for field_name in (
            "embedding_dimension",
            "window_size",
            "semantic_top_k",
            "keyword_top_k",
            "structured_top_k",
            "max_workers",
        ):
            if getattr(self, field_name) < 1:
                raise ConfigurationError(f"SimpleMem {field_name} must be positive")
        if self.overlap_size < 0:
            raise ConfigurationError("SimpleMem overlap_size cannot be negative")
        if self.overlap_size >= self.window_size:
            raise ConfigurationError(
                "SimpleMem overlap_size must be smaller than window_size"
            )
        if self.api_timeout_seconds <= 0:
            raise ConfigurationError("SimpleMem api_timeout_seconds must be positive")
        if self.api_max_retries < 0:
            raise ConfigurationError("SimpleMem api_max_retries cannot be negative")
        if self.max_reflection_rounds < 0:
            raise ConfigurationError(
                "SimpleMem max_reflection_rounds cannot be negative"
            )

    def validate_required_local_resources(self, path_settings: PathSettings) -> None:
        """校验 SimpleMem 本地 embedding 模型目录存在。"""

        model_path = _resolve_project_relative_path(
            self.embedding_model_path,
            path_settings.project_root,
        )
        if model_path is not None and not model_path.is_dir():
            raise ConfigurationError(
                "SimpleMem required local embedding model missing: "
                f"{model_path}. Download Qwen/Qwen3-Embedding-0.6B to "
                "models/Qwen3-Embedding-0.6B before running prediction."
            )

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 secret 与绝对状态路径的公开配置。"""

        return {
            **asdict(self),
            "adapter_version": SIMPLEMEM_ADAPTER_VERSION,
            "official_profile": SIMPLEMEM_OFFICIAL_PROFILE_NAME,
            "llm_provider": "openai-compatible",
            "embedding_provider": "sentence-transformers-local",
            "backend": "text",
        }


class SimpleMem(MemoryProvider):
    """SimpleMem text backend provider。"""

    consume_granularity = "turn"
    session_memory_report = False
    provenance_granularity = "none"

    def __init__(
        self,
        *,
        config: SimpleMemConfig,
        path_settings: PathSettings,
        storage_root: Path,
        system_factory: SimpleMemSystemFactory | None = None,
    ) -> None:
        """保存构造依赖并延迟初始化每个 isolation 的 SimpleMemSystem。"""

        config.validate_required_local_resources(path_settings)
        self.config = config
        self.path_settings = path_settings
        self.storage_root = storage_root
        self._system_factory = system_factory
        self._systems_by_isolation_key: dict[str, Any] = {}
        self._finalized_isolation_keys: set[str] = set()

    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """把 turn 事件写入 SimpleMem 的 `add_dialogue()` 入口。"""

        if not isinstance(unit, TurnEvent):
            raise ConfigurationError("SimpleMem native provider only accepts TurnEvent")
        system = self._system_for_isolation_key(unit.isolation_key)
        timestamp = parse_simplemem_timestamp(unit.timestamp)
        speaker = unit.speaker_name or unit.role
        system.add_dialogue(
            speaker=speaker,
            content=unit.content,
            timestamp=timestamp,
        )
        return IngestResult(
            unit_ref=UnitRef(isolation_key=unit.isolation_key),
            metadata={
                "method": "simplemem",
                "turn_id": unit.turn_id,
                "timestamp": timestamp,
            },
        )

    def end_conversation(self, ref: UnitRef) -> None:
        """在隔离单元结束时调用 SimpleMem `finalize()` 处理残余窗口。"""

        if ref.isolation_key in self._finalized_isolation_keys:
            return None
        system = self._systems_by_isolation_key.get(ref.isolation_key)
        if system is None:
            return None
        system.finalize()
        self._finalized_isolation_keys.add(ref.isolation_key)
        return None

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:  # pragma: no cover - T3 实现
        """执行 SimpleMem retrieve；T3 补齐。"""

        raise NotImplementedError("SimpleMem retrieve is implemented in T3")

    def _system_for_isolation_key(self, isolation_key: str) -> Any:
        """返回 isolation 专属 SimpleMemSystem，必要时创建状态目录。"""

        system = self._systems_by_isolation_key.get(isolation_key)
        if system is not None:
            return system
        state_dir = self.storage_root / _state_dir_name(isolation_key)
        state_dir.mkdir(parents=True, exist_ok=True)
        if self._system_factory is not None:
            system = self._system_factory(isolation_key, state_dir)
        else:
            system = self._create_official_system(isolation_key, state_dir)
        self._systems_by_isolation_key[isolation_key] = system
        return system

    def _create_official_system(self, isolation_key: str, state_dir: Path) -> Any:
        """构造官方 SimpleMemSystem；T5 前真实路径不应被无配置调用。"""

        raise ConfigurationError(
            "SimpleMem production system factory is not configured: "
            f"{isolation_key}"
        )


def parse_simplemem_timestamp(raw_timestamp: str | None) -> str | None:
    """把 benchmark 原始时间转成 SimpleMem 可接受的 ISO 字符串。"""

    if raw_timestamp is None:
        return None
    value = raw_timestamp.strip()
    if not value:
        return None
    iso_value = _parse_iso_timestamp(value)
    if iso_value is not None:
        return iso_value
    match = _LOCOMO_TIMESTAMP_PATTERN.match(value)
    if match is None:
        return None
    month = _MONTHS.get(match.group("month").lower())
    if month is None:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        return None
    period = match.group("period").lower()
    if period == "pm" and hour != 12:
        hour += 12
    if period == "am" and hour == 12:
        hour = 0
    try:
        parsed = datetime(
            int(match.group("year")),
            month,
            int(match.group("day")),
            hour,
            minute,
        )
    except ValueError:
        return None
    return parsed.isoformat(timespec="seconds")


def _parse_iso_timestamp(value: str) -> str | None:
    """解析已有 ISO 时间；不可解析时返回 None。"""

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.isoformat(timespec="seconds")


def _state_dir_name(isolation_key: str) -> str:
    """把任意 isolation key 映射为安全、稳定的状态目录名。"""

    digest = hashlib.sha256(isolation_key.encode("utf-8")).hexdigest()[:16]
    return f"isolation_{digest}"


def build_simplemem_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 SimpleMem text 核心源码与 wrapper 的稳定身份。"""

    settings = path_settings or load_path_settings()
    simplemem_root = settings.resolve_third_party_method_path(
        SIMPLEMEM_METHOD_DIRECTORY
    )
    required_files = [
        "README.md",
        "setup.py",
        "main.py",
        "simplemem/core/memory_builder.py",
        "simplemem/core/hybrid_retriever.py",
        "simplemem/core/answer_generator.py",
        "simplemem/core/settings.py",
        "simplemem/core/utils/llm_client.py",
        "simplemem/core/utils/embedding.py",
        "simplemem/core/database/vector_store.py",
        "simplemem/core/models/memory_entry.py",
    ]
    source_files = [simplemem_root / relative_path for relative_path in required_files]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise ConfigurationError(f"SimpleMem source files missing: {missing_text}")

    vendored_source_sha256, relative_paths = _hash_relative_source_files(
        root=simplemem_root,
        source_files=source_files,
    )
    wrapper_path = settings.project_root / SIMPLEMEM_WRAPPER_LOGICAL_PATH
    if not wrapper_path.is_file():
        raise ConfigurationError(f"SimpleMem wrapper file missing: {wrapper_path}")
    return _build_simplemem_source_identity_from_components(
        vendored_files=relative_paths,
        vendored_source_sha256=vendored_source_sha256,
        wrapper_logical_path=SIMPLEMEM_WRAPPER_LOGICAL_PATH,
        wrapper_bytes=wrapper_path.read_bytes(),
    )


def _build_simplemem_source_identity_from_components(
    *,
    vendored_files: list[str],
    vendored_source_sha256: str,
    wrapper_logical_path: str,
    wrapper_bytes: bytes,
) -> dict[str, Any]:
    """组合官方源码与 wrapper bytes，生成公开 source identity。"""

    if Path(wrapper_logical_path).is_absolute():
        raise ConfigurationError(
            "SimpleMem wrapper_logical_path must be a stable logical path"
        )
    wrapper_sha256 = hashlib.sha256(wrapper_bytes).hexdigest()
    digest = hashlib.sha256()
    for field_name, field_value in (
        ("vendored_source_sha256", vendored_source_sha256),
        ("wrapper_path", wrapper_logical_path),
        ("wrapper_sha256", wrapper_sha256),
    ):
        field_name_bytes = field_name.encode("utf-8")
        field_value_bytes = field_value.encode("utf-8")
        digest.update(len(field_name_bytes).to_bytes(8, byteorder="big"))
        digest.update(field_name_bytes)
        digest.update(len(field_value_bytes).to_bytes(8, byteorder="big"))
        digest.update(field_value_bytes)

    return {
        "source_sha256": digest.hexdigest(),
        "vendored_source_sha256": vendored_source_sha256,
        "file_count": len(vendored_files),
        "files": list(vendored_files),
        "wrapper_path": wrapper_logical_path,
        "wrapper_sha256": wrapper_sha256,
        "source_mode": SIMPLEMEM_SOURCE_MODE,
    }


def _hash_relative_source_files(
    *,
    root: Path,
    source_files: list[Path],
) -> tuple[str, list[str]]:
    """按相对路径与内容计算源码集合 SHA-256。"""

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative_path = source_file.relative_to(root).as_posix()
        relative_paths.append(relative_path)
        path_bytes = relative_path.encode("utf-8")
        content = source_file.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, byteorder="big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, byteorder="big"))
        digest.update(content)
    return digest.hexdigest(), relative_paths


def _resolve_project_relative_path(value: str, project_root: Path) -> Path | None:
    """把 `models/...` 这类配置解析成项目内路径。"""

    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0] in {"models", "third_party"}:
        return project_root / candidate
    return None


__all__ = [
    "SIMPLEMEM_ADAPTER_VERSION",
    "SIMPLEMEM_OFFICIAL_PROFILE_NAME",
    "SimpleMem",
    "SimpleMemConfig",
    "build_simplemem_source_identity",
    "parse_simplemem_timestamp",
]

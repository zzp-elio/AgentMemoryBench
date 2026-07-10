"""benchmark variant 与 run scope 的强类型契约。

本模块只放 benchmark registration 需要共享的轻量类型，不依赖 runner，也不
包含具体 benchmark 的加载逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal
import re

from memory_benchmark.core import Dataset
from memory_benchmark.core.exceptions import ConfigurationError


_SAFE_VARIANT_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def normalize_variant_run_id_token(variant_name: str) -> str:
    """把已校验的 variant 名转换为稳定的 child run-id token。"""

    return variant_name.replace("_", "-")


def normalize_variant_run_id_collision_key(variant_name: str) -> str:
    """返回跨平台保守比较用的 variant run-id token 键。"""

    return normalize_variant_run_id_token(variant_name).casefold()


def _validate_relative_source_path(path: Path, variant_name: str) -> None:
    """校验 variant 使用的源码路径是否安全。

    输入:
        path: 相对项目根目录的源码路径。
        variant_name: 当前 variant 名称，用于构造错误信息。

    输出:
        None。绝对路径或包含 `..` 的路径会抛 `ConfigurationError`。
    """

    if path.is_absolute() or ".." in path.parts:
        raise ConfigurationError(
            f"{variant_name}: source_relative_paths must stay under project root: {path}"
        )


class RunScope(StrEnum):
    """一次 benchmark 运行的范围。"""

    SMOKE = "smoke"
    FULL = "full"


_SMOKE_HISTORY_AXES = frozenset({"rounds", "turns", "sessions", "sources"})


@dataclass(frozen=True)
class BenchmarkSmokePolicy:
    """一个 benchmark 声明的 smoke 历史裁剪轴与默认预算。

    `history_axis` 是该 benchmark 自然的历史裁剪单位（round/turn/session/
    source 文件），CLI 只接受与该轴匹配的参数，其余轴一律 fail-fast，避免
    “全局 20”假装所有 benchmark 共享同一种历史语义（本任务修复的具体 bug，
    见 `BenchmarkLoadRequest.smoke_turn_limit` 的历史默认值）。
    """

    history_axis: Literal["rounds", "turns", "sessions", "sources"]
    default_history_limit: int
    default_isolation_limit: int = 1
    default_question_limit: int = 1

    def __post_init__(self) -> None:
        """校验历史轴取值合法，且三个默认预算都是正整数。"""

        if self.history_axis not in _SMOKE_HISTORY_AXES:
            allowed = ", ".join(sorted(_SMOKE_HISTORY_AXES))
            raise ConfigurationError(
                f"BenchmarkSmokePolicy.history_axis must be one of: {allowed}"
            )
        if self.default_history_limit < 1:
            raise ConfigurationError(
                "BenchmarkSmokePolicy.default_history_limit must be at least 1"
            )
        if self.default_isolation_limit < 1:
            raise ConfigurationError(
                "BenchmarkSmokePolicy.default_isolation_limit must be at least 1"
            )
        if self.default_question_limit < 1:
            raise ConfigurationError(
                "BenchmarkSmokePolicy.default_question_limit must be at least 1"
            )

    def to_dict(self) -> dict[str, object]:
        """转换为可写入 manifest/dataset metadata 的稳定字典。"""

        return {
            "history_axis": self.history_axis,
            "default_history_limit": self.default_history_limit,
            "default_isolation_limit": self.default_isolation_limit,
            "default_question_limit": self.default_question_limit,
        }


@dataclass(frozen=True)
class BenchmarkResumePolicy:
    """一个 benchmark 声明的 resume/checkpoint 语义。

    `ingest_checkpoint`/`answer_checkpoint` 当前只有一个合法取值，仍然显式
    校验，避免未来字段扩展时静默接受非法组合。
    """

    smoke_enabled: bool
    ingest_checkpoint: Literal["conversation"]
    answer_checkpoint: Literal["question"]
    reuse_saved_retrieval: bool
    evaluation_artifact_only: bool

    def __post_init__(self) -> None:
        """校验 checkpoint 粒度取值合法。"""

        if self.ingest_checkpoint != "conversation":
            raise ConfigurationError(
                "BenchmarkResumePolicy.ingest_checkpoint must be 'conversation'"
            )
        if self.answer_checkpoint != "question":
            raise ConfigurationError(
                "BenchmarkResumePolicy.answer_checkpoint must be 'question'"
            )

    def to_dict(self) -> dict[str, object]:
        """转换为可写入 manifest/dataset metadata 的稳定字典。"""

        return {
            "smoke_enabled": self.smoke_enabled,
            "ingest_checkpoint": self.ingest_checkpoint,
            "answer_checkpoint": self.answer_checkpoint,
            "reuse_saved_retrieval": self.reuse_saved_retrieval,
            "evaluation_artifact_only": self.evaluation_artifact_only,
        }


@dataclass(frozen=True)
class BenchmarkVariantSpec:
    """benchmark 的一个 concrete variant 声明。"""

    name: str
    source_relative_paths: tuple[Path, ...]

    def __post_init__(self) -> None:
        """在构造时校验 variant 名和 source path。"""

        normalized_name = self.name.strip()
        if not normalized_name:
            raise ConfigurationError("benchmark variant name is required")
        if normalized_name == "all":
            raise ConfigurationError("benchmark variant name cannot be 'all'")
        if normalized_name != self.name or not _SAFE_VARIANT_NAME_PATTERN.fullmatch(
            self.name
        ):
            raise ConfigurationError(
                "benchmark variant name must use only letters, numbers, "
                "underscores or hyphens and must start with a letter or number"
            )
        if not self.source_relative_paths:
            raise ConfigurationError(
                f"{self.name}: source_relative_paths must contain at least one path"
            )
        for path in self.source_relative_paths:
            _validate_relative_source_path(path, self.name)


@dataclass(frozen=True)
class BenchmarkLoadRequest:
    """准备 benchmark 运行时所需的请求参数。"""

    variant: str
    run_scope: RunScope
    smoke_turn_limit: int = 20
    smoke_conversation_limit: int = 1
    smoke_session_limit: int | None = None

    def __post_init__(self) -> None:
        """校验 smoke 裁剪参数是正整数。"""

        if self.smoke_turn_limit < 1:
            raise ConfigurationError("smoke_turn_limit must be at least 1")
        if self.smoke_conversation_limit < 1:
            raise ConfigurationError(
                "smoke_conversation_limit must be at least 1"
            )
        if self.smoke_session_limit is not None and self.smoke_session_limit < 1:
            raise ConfigurationError("smoke_session_limit must be at least 1")


@dataclass(frozen=True)
class PreparedBenchmarkRun:
    """benchmark registration 预处理后的运行结果。"""

    variant: str
    run_scope: RunScope
    dataset: Dataset
    source_relative_paths: tuple[Path, ...]

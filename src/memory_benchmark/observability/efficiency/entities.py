"""成本与效率原始 observation 实体。

本模块只定义可序列化的数据契约和强校验，不负责计时、token 统计、文件写入或费用计算。
所有实体都面向原始事实记录，禁止把估算费用混入实验 observation。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, TypeAlias

from memory_benchmark.core import ConfigurationError


class EfficiencyStage(str, Enum):
    """一次模型或检索操作所属的实验阶段。"""

    MEMORY_BUILD = "memory_build"
    RETRIEVAL = "retrieval"
    ANSWER = "answer"
    JUDGE = "judge"


class MeasurementSource(str, Enum):
    """token 或 latency 数值的实际计量来源。"""

    API_USAGE = "api_usage"
    METHOD_NATIVE = "method_native"
    FRAMEWORK_TIMER = "framework_timer"
    TOKENIZER_ESTIMATE = "tokenizer_estimate"


@dataclass(frozen=True)
class RetrievalObservationContract:
    """一次 prediction run 的 retrieval 观测兼容契约。

    字段:
        required_by_profile: benchmark/profile 是否要求精确 retrieval 观测。
        supported_by_method: 当前 method adapter 是否声明可精确上报 retrieval。
        unsupported_reason: method 不支持精确拆分时写入 artifact 的稳定原因。
    """

    required_by_profile: bool
    supported_by_method: bool
    unsupported_reason: str | None = None

    def __post_init__(self) -> None:
        """在付费运行前拒绝 profile 与 method 能力不兼容的组合。"""

        _require_bool(self.required_by_profile, "required_by_profile")
        _require_bool(self.supported_by_method, "supported_by_method")
        if self.required_by_profile and not self.supported_by_method:
            raise ConfigurationError(
                "Profile requires separable retrieval observation, but the "
                "method adapter does not support it"
            )
        if self.supported_by_method:
            if self.unsupported_reason is not None:
                raise ConfigurationError(
                    "unsupported_reason must be null when retrieval observation "
                    "is supported"
                )
            return
        _require_text(self.unsupported_reason, "unsupported_reason")

    def to_dict(self) -> dict[str, Any]:
        """返回可写入 immutable manifest 的公开契约。"""

        return asdict(self)


@dataclass(frozen=True)
class ModelDescriptor:
    """一次 run 中使用的模型身份。

    字段:
        model_id: 当前 run 内供 observation 引用的稳定 id。
        model_name: 实际模型名称。
        model_role: 模型用途，例如 answer_llm、judge_llm 或 embedding。
        execution_mode: `api` 或 `local`。
        revision_or_path: 可选本地 revision、版本或路径。
        embedding_dimension: embedding 模型的向量维数。
        tokenizer_name: token 计数所用 tokenizer 身份。
    """

    model_id: str
    model_name: str
    model_role: str
    execution_mode: str
    revision_or_path: str | None = None
    embedding_dimension: int | None = None
    tokenizer_name: str | None = None

    def __post_init__(self) -> None:
        """校验模型身份字段。"""

        _require_text(self.model_id, "model_id")
        _require_text(self.model_name, "model_name")
        _require_text(self.model_role, "model_role")
        if self.execution_mode not in {"api", "local"}:
            raise ConfigurationError("execution_mode must be 'api' or 'local'")
        if self.revision_or_path is not None:
            _require_text(self.revision_or_path, "revision_or_path")
        if self.embedding_dimension is not None:
            _require_non_negative_int(
                self.embedding_dimension,
                "embedding_dimension",
                allow_zero=False,
            )
        if self.tokenizer_name is not None:
            _require_text(self.tokenizer_name, "tokenizer_name")

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化模型身份。"""

        return asdict(self)


@dataclass(frozen=True)
class ConversationEfficiencyObservation:
    """单个 conversation 的记忆构建总耗时。"""

    observation_id: str
    conversation_id: str
    memory_build_total_latency_ms: float

    def __post_init__(self) -> None:
        """校验 conversation 级 observation。"""

        _require_text(self.observation_id, "observation_id")
        _require_text(self.conversation_id, "conversation_id")
        _require_latency(
            self.memory_build_total_latency_ms,
            "memory_build_total_latency_ms",
        )

    def to_dict(self) -> dict[str, Any]:
        """返回带 observation 类型的 JSON 记录。"""

        return {
            "observation_type": "conversation_efficiency",
            **asdict(self),
        }


@dataclass(frozen=True)
class QuestionEfficiencyObservation:
    """单个问题的检索、记忆上下文和回答生成效率。"""

    observation_id: str
    conversation_id: str
    question_id: str
    retrieval_latency_ms: float | None
    unsupported_reason: str | None
    injected_memory_context_tokens: int | None
    answer_generation_latency_ms: float

    def __post_init__(self) -> None:
        """校验 question 级 observation 及 unsupported 语义。"""

        _require_text(self.observation_id, "observation_id")
        _require_text(self.conversation_id, "conversation_id")
        _require_text(self.question_id, "question_id")
        if self.retrieval_latency_ms is None:
            _require_text(self.unsupported_reason, "unsupported_reason")
        else:
            _require_latency(self.retrieval_latency_ms, "retrieval_latency_ms")
            if self.unsupported_reason is not None:
                raise ConfigurationError(
                    "unsupported_reason must be null when retrieval_latency_ms is available"
                )
        if self.injected_memory_context_tokens is not None:
            _require_non_negative_int(
                self.injected_memory_context_tokens,
                "injected_memory_context_tokens",
            )
        _require_latency(
            self.answer_generation_latency_ms,
            "answer_generation_latency_ms",
        )

    def to_dict(self) -> dict[str, Any]:
        """返回带 observation 类型的 JSON 记录。"""

        return {
            "observation_type": "question_efficiency",
            **asdict(self),
        }


@dataclass(frozen=True)
class LLMCallObservation:
    """一次真实 LLM 调用的 input/output token 记录。"""

    observation_id: str
    stage: EfficiencyStage
    model_id: str
    input_tokens: int
    output_tokens: int
    token_measurement_source: MeasurementSource
    conversation_id: str | None = None
    question_id: str | None = None

    def __post_init__(self) -> None:
        """校验 LLM 调用字段和允许的阶段。"""

        _require_text(self.observation_id, "observation_id")
        _require_text(self.model_id, "model_id")
        _require_enum(self.stage, EfficiencyStage, "stage")
        if self.stage not in {
            EfficiencyStage.MEMORY_BUILD,
            EfficiencyStage.RETRIEVAL,
            EfficiencyStage.ANSWER,
            EfficiencyStage.JUDGE,
        }:
            raise ConfigurationError(f"LLM call stage is not supported: {self.stage}")
        _require_measurement_source(
            self.token_measurement_source,
            "token_measurement_source",
            allowed={
                MeasurementSource.API_USAGE,
                MeasurementSource.METHOD_NATIVE,
                MeasurementSource.TOKENIZER_ESTIMATE,
            },
        )
        _require_non_negative_int(self.input_tokens, "input_tokens")
        _require_non_negative_int(self.output_tokens, "output_tokens")
        _validate_optional_scope_ids(self.conversation_id, self.question_id)

    def to_dict(self) -> dict[str, Any]:
        """返回枚举已转换为字符串的 JSON 记录。"""

        return {
            "observation_type": "llm_call",
            **_enum_values(asdict(self)),
        }


@dataclass(frozen=True)
class EmbeddingCallObservation:
    """一次真实 embedding 调用的 token 与 latency 记录。"""

    observation_id: str
    stage: EfficiencyStage
    model_id: str
    input_tokens: int
    latency_ms: float
    token_measurement_source: MeasurementSource
    latency_measurement_source: MeasurementSource
    conversation_id: str | None = None
    question_id: str | None = None

    def __post_init__(self) -> None:
        """校验 embedding 调用字段和允许的阶段。"""

        _require_text(self.observation_id, "observation_id")
        _require_text(self.model_id, "model_id")
        _require_enum(self.stage, EfficiencyStage, "stage")
        if self.stage not in {
            EfficiencyStage.MEMORY_BUILD,
            EfficiencyStage.RETRIEVAL,
        }:
            raise ConfigurationError(
                f"Embedding call stage is not supported: {self.stage}"
            )
        _require_non_negative_int(self.input_tokens, "input_tokens")
        _require_latency(self.latency_ms, "latency_ms")
        _require_measurement_source(
            self.token_measurement_source,
            "token_measurement_source",
            allowed={
                MeasurementSource.API_USAGE,
                MeasurementSource.METHOD_NATIVE,
                MeasurementSource.TOKENIZER_ESTIMATE,
            },
        )
        _require_measurement_source(
            self.latency_measurement_source,
            "latency_measurement_source",
            allowed={
                MeasurementSource.METHOD_NATIVE,
                MeasurementSource.FRAMEWORK_TIMER,
            },
        )
        _validate_optional_scope_ids(self.conversation_id, self.question_id)

    def to_dict(self) -> dict[str, Any]:
        """返回枚举已转换为字符串的 JSON 记录。"""

        return {
            "observation_type": "embedding_call",
            **_enum_values(asdict(self)),
        }


EfficiencyObservation: TypeAlias = (
    ConversationEfficiencyObservation
    | QuestionEfficiencyObservation
    | LLMCallObservation
    | EmbeddingCallObservation
)


def _require_text(value: str | None, field_name: str) -> None:
    """要求字段为非空字符串。"""

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field_name} must be a non-empty string")


def _require_bool(value: bool, field_name: str) -> None:
    """要求配置字段是真正的布尔值，拒绝整数和字符串冒充。"""

    if not isinstance(value, bool):
        raise ConfigurationError(f"{field_name} must be a boolean")


def _require_non_negative_int(
    value: int,
    field_name: str,
    *,
    allow_zero: bool = True,
) -> None:
    """要求字段为非负整数，必要时拒绝零。"""

    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigurationError(f"{field_name} must be an integer")
    minimum = 0 if allow_zero else 1
    if value < minimum:
        comparator = "non-negative" if allow_zero else "positive"
        raise ConfigurationError(f"{field_name} must be {comparator}")


def _require_latency(value: float, field_name: str) -> None:
    """要求 latency 为有限的非负数。"""

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigurationError(f"{field_name} must be a finite non-negative number")
    if not math.isfinite(float(value)) or value < 0:
        raise ConfigurationError(f"{field_name} must be a finite non-negative number")


def _require_enum(value: Any, enum_type: type[Enum], field_name: str) -> None:
    """要求运行时值是指定枚举实例，而不是碰巧相等的字符串。"""

    if not isinstance(value, enum_type):
        raise ConfigurationError(f"{field_name} must be a {enum_type.__name__}")


def _require_measurement_source(
    value: MeasurementSource,
    field_name: str,
    *,
    allowed: set[MeasurementSource],
) -> None:
    """校验计量来源枚举及其与 metric 类型的兼容性。"""

    _require_enum(value, MeasurementSource, field_name)
    if value not in allowed:
        allowed_text = ", ".join(sorted(source.value for source in allowed))
        raise ConfigurationError(
            f"{field_name} must be one of: {allowed_text}"
        )


def _validate_optional_scope_ids(
    conversation_id: str | None,
    question_id: str | None,
) -> None:
    """校验可选 conversation/question 关联字段。"""

    if conversation_id is not None:
        _require_text(conversation_id, "conversation_id")
    if question_id is not None:
        _require_text(question_id, "question_id")
        if conversation_id is None:
            raise ConfigurationError(
                "conversation_id is required when question_id is provided"
            )


def _enum_values(payload: dict[str, Any]) -> dict[str, Any]:
    """把 dataclass 字典中的枚举转换为 JSON 字符串。"""

    return {
        key: value.value if isinstance(value, Enum) else value
        for key, value in payload.items()
    }


__all__ = [
    "ConversationEfficiencyObservation",
    "EfficiencyObservation",
    "EfficiencyStage",
    "EmbeddingCallObservation",
    "LLMCallObservation",
    "MeasurementSource",
    "ModelDescriptor",
    "QuestionEfficiencyObservation",
    "RetrievalObservationContract",
]

"""task family 与 method capability 的稳定声明。"""

from __future__ import annotations

from enum import StrEnum

from .exceptions import ConfigurationError


class TaskFamily(StrEnum):
    """框架当前识别的 benchmark 任务族。"""

    CONVERSATION_QA = "conversation_qa"


class MethodCapability(StrEnum):
    """method 可以向 benchmark 提供的稳定能力。"""

    CONVERSATION_ADD = "conversation_add"
    ANSWER_GENERATION = "answer_generation"
    MEMORY_RETRIEVAL = "memory_retrieval"


def validate_compatibility(
    *,
    benchmark_task_family: TaskFamily,
    required_capabilities: frozenset[MethodCapability],
    method_task_families: frozenset[TaskFamily],
    provided_capabilities: frozenset[MethodCapability],
) -> None:
    """校验 benchmark 与 method 的 task family/capability 契约。

    输入:
        benchmark_task_family: benchmark 声明的任务族。
        required_capabilities: benchmark 要求 method 提供的能力集合。
        method_task_families: method 支持的任务族集合。
        provided_capabilities: method 实际提供的能力集合。

    输出:
        None。兼容时静默返回。

    异常:
        ConfigurationError: method 不支持目标 task family，或缺少必需 capability。
    """

    if benchmark_task_family not in method_task_families:
        raise ConfigurationError(
            f"Method does not support task family: {benchmark_task_family.value}"
        )

    missing_capabilities = required_capabilities - provided_capabilities
    if missing_capabilities:
        missing_names = ", ".join(
            sorted(capability.value for capability in missing_capabilities)
        )
        raise ConfigurationError(
            f"Method is missing required capabilities: {missing_names}"
        )

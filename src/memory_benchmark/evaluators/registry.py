"""统一 evaluator 注册表。

本模块只声明当前统一 CLI 已完成装配的 metric、benchmark 兼容矩阵和无状态
factory。registry 不保存 OpenAI client、API key 或运行中的 evaluator 实例。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory_benchmark.config import load_path_settings
from memory_benchmark.config.profiles import load_typed_profile
from memory_benchmark.core import ConfigurationError

from .beam_rubric_judge import BeamRubricJudgeEvaluator
from .f1 import F1Evaluator
from .halumem_extraction import HalumemExtractionEvaluator
from .halumem_qa import HalumemQAEvaluator
from .halumem_update import HalumemUpdateEvaluator
from .llm_judge import LLMJudgeProfileConfig
from .longmemeval_judge import LongMemEvalJudgeEvaluator
from .longmemeval_recall import LongMemEvalRetrievalRecallEvaluator
from .locomo_f1 import LoCoMoF1Evaluator
from .locomo_judge import LoCoMoJudgeEvaluator
from .locomo_recall import LoCoMoRetrievalRecallEvaluator
from .membench_choice_accuracy import MemBenchChoiceAccuracyEvaluator


EvaluatorFactory = Callable[..., Any]


@dataclass(frozen=True)
class EvaluatorRegistration:
    """一个统一 CLI metric 的静态注册信息。

    字段:
        cli_name: CLI 使用的稳定名称。
        metric_name: evaluator 写入 artifact 的指标名称。
        supported_benchmarks: 当前已完成装配的 benchmark 集合。
        requires_api: 构造或执行该 evaluator 是否可能调用外部 API。
        profile_names: 允许的配置 profile；离线固定指标为空集合。
        profile_relative_path: 相对项目根的 TOML profile 路径。
        config_type: TOML section 对应的强类型配置；离线指标为空。
        factory: 每次运行构造新 evaluator 的无状态 factory。
    """

    cli_name: str
    metric_name: str
    supported_benchmarks: frozenset[str]
    requires_api: bool
    profile_names: frozenset[str]
    profile_relative_path: Path | None
    config_type: type[Any] | None
    factory: EvaluatorFactory


def _build_beam_rubric_judge(
    *,
    profile_name: str,
    model: str | None = None,
    client: Any | None = None,
    project_root: str | None = None,
    env_file: str | None = None,
) -> BeamRubricJudgeEvaluator:
    """按已验证 profile 构造 BEAM rubric judge。"""

    return BeamRubricJudgeEvaluator(
        mode=profile_name,
        model=model,
        client=client,
        project_root=project_root,
        env_file=env_file,
    )


def _build_locomo_f1(**_: Any) -> LoCoMoF1Evaluator:
    """构造无外部依赖的 LoCoMo F1 evaluator。"""

    return LoCoMoF1Evaluator()


def _build_f1(**_: Any) -> F1Evaluator:
    """构造无外部依赖的通用 token F1 evaluator。"""

    return F1Evaluator()


def _build_membench_choice_accuracy(**_: Any) -> MemBenchChoiceAccuracyEvaluator:
    """构造无外部依赖的 MemBench choice accuracy evaluator。"""

    return MemBenchChoiceAccuracyEvaluator()


def _build_locomo_recall(**_: Any) -> LoCoMoRetrievalRecallEvaluator:
    """构造无外部依赖的 LoCoMo retrieval recall evaluator。"""

    return LoCoMoRetrievalRecallEvaluator()


def _build_longmemeval_recall(**_: Any) -> LongMemEvalRetrievalRecallEvaluator:
    """构造无外部依赖的 LongMemEval retrieval recall evaluator。"""

    return LongMemEvalRetrievalRecallEvaluator()


def _build_locomo_judge(
    *,
    profile_name: str,
    model: str | None = None,
    client: Any | None = None,
    project_root: str | None = None,
    env_file: str | None = None,
) -> LoCoMoJudgeEvaluator:
    """按已验证 profile 构造 LoCoMo LLM judge。"""

    return LoCoMoJudgeEvaluator(
        mode=profile_name,
        model=model,
        client=client,
        project_root=project_root,
        env_file=env_file,
    )


def _build_longmemeval_judge(
    *,
    profile_name: str,
    model: str | None = None,
    client: Any | None = None,
    project_root: str | None = None,
    env_file: str | None = None,
) -> LongMemEvalJudgeEvaluator:
    """按已验证 profile 构造 LongMemEval LLM judge。"""

    return LongMemEvalJudgeEvaluator(
        mode=profile_name,
        model=model,
        client=client,
        project_root=project_root,
        env_file=env_file,
    )


def _build_halumem_extraction(
    *,
    profile_name: str,
    model: str | None = None,
    client: Any | None = None,
    project_root: str | None = None,
    env_file: str | None = None,
) -> HalumemExtractionEvaluator:
    """按已验证 profile 构造 HaluMem extraction judge。"""

    return HalumemExtractionEvaluator(
        mode=profile_name,
        model=model,
        client=client,
        project_root=project_root,
        env_file=env_file,
    )


def _build_halumem_update(
    *,
    profile_name: str,
    model: str | None = None,
    client: Any | None = None,
    project_root: str | None = None,
    env_file: str | None = None,
) -> HalumemUpdateEvaluator:
    """按已验证 profile 构造 HaluMem update judge。"""

    return HalumemUpdateEvaluator(
        mode=profile_name,
        model=model,
        client=client,
        project_root=project_root,
        env_file=env_file,
    )


def _build_halumem_qa(
    *,
    profile_name: str,
    model: str | None = None,
    client: Any | None = None,
    project_root: str | None = None,
    env_file: str | None = None,
) -> HalumemQAEvaluator:
    """按已验证 profile 构造 HaluMem QA judge。"""

    return HalumemQAEvaluator(
        mode=profile_name,
        model=model,
        client=client,
        project_root=project_root,
        env_file=env_file,
    )


_REGISTRATIONS = {
    "beam-rubric-judge": EvaluatorRegistration(
        cli_name="beam-rubric-judge",
        metric_name="beam_rubric_judge",
        supported_benchmarks=frozenset({"beam"}),
        requires_api=True,
        profile_names=frozenset({"compact", "detailed"}),
        profile_relative_path=Path("configs/evaluators/llm_judge.toml"),
        config_type=LLMJudgeProfileConfig,
        factory=_build_beam_rubric_judge,
    ),
    "halumem-extraction": EvaluatorRegistration(
        cli_name="halumem-extraction",
        metric_name="halumem_extraction",
        supported_benchmarks=frozenset({"halumem"}),
        requires_api=True,
        profile_names=frozenset({"compact", "detailed"}),
        profile_relative_path=Path("configs/evaluators/llm_judge.toml"),
        config_type=LLMJudgeProfileConfig,
        factory=_build_halumem_extraction,
    ),
    "halumem-update": EvaluatorRegistration(
        cli_name="halumem-update",
        metric_name="halumem_update",
        supported_benchmarks=frozenset({"halumem"}),
        requires_api=True,
        profile_names=frozenset({"compact", "detailed"}),
        profile_relative_path=Path("configs/evaluators/llm_judge.toml"),
        config_type=LLMJudgeProfileConfig,
        factory=_build_halumem_update,
    ),
    "halumem-qa": EvaluatorRegistration(
        cli_name="halumem-qa",
        metric_name="halumem_qa",
        supported_benchmarks=frozenset({"halumem"}),
        requires_api=True,
        profile_names=frozenset({"compact", "detailed"}),
        profile_relative_path=Path("configs/evaluators/llm_judge.toml"),
        config_type=LLMJudgeProfileConfig,
        factory=_build_halumem_qa,
    ),
    "f1": EvaluatorRegistration(
        cli_name="f1",
        metric_name="f1",
        supported_benchmarks=frozenset(
            {"beam", "halumem", "locomo", "longmemeval"}
        ),
        requires_api=False,
        profile_names=frozenset(),
        profile_relative_path=None,
        config_type=None,
        factory=_build_f1,
    ),
    "locomo-f1": EvaluatorRegistration(
        cli_name="locomo-f1",
        metric_name="locomo_f1",
        supported_benchmarks=frozenset({"locomo"}),
        requires_api=False,
        profile_names=frozenset(),
        profile_relative_path=None,
        config_type=None,
        factory=_build_locomo_f1,
    ),
    "locomo-judge": EvaluatorRegistration(
        cli_name="locomo-judge",
        metric_name="locomo_judge_accuracy",
        supported_benchmarks=frozenset({"locomo"}),
        requires_api=True,
        profile_names=frozenset({"compact", "detailed"}),
        profile_relative_path=Path("configs/evaluators/llm_judge.toml"),
        config_type=LLMJudgeProfileConfig,
        factory=_build_locomo_judge,
    ),
    "longmemeval-judge": EvaluatorRegistration(
        cli_name="longmemeval-judge",
        metric_name="longmemeval_judge_accuracy",
        supported_benchmarks=frozenset({"longmemeval"}),
        requires_api=True,
        profile_names=frozenset({"compact", "detailed"}),
        profile_relative_path=Path("configs/evaluators/llm_judge.toml"),
        config_type=LLMJudgeProfileConfig,
        factory=_build_longmemeval_judge,
    ),
    "longmemeval-recall": EvaluatorRegistration(
        cli_name="longmemeval-recall",
        metric_name="longmemeval_recall",
        supported_benchmarks=frozenset({"longmemeval"}),
        requires_api=False,
        profile_names=frozenset(),
        profile_relative_path=None,
        config_type=None,
        factory=_build_longmemeval_recall,
    ),
    "membench-choice-accuracy": EvaluatorRegistration(
        cli_name="membench-choice-accuracy",
        metric_name="membench_choice_accuracy",
        supported_benchmarks=frozenset({"membench"}),
        requires_api=False,
        profile_names=frozenset(),
        profile_relative_path=None,
        config_type=None,
        factory=_build_membench_choice_accuracy,
    ),
    "locomo-recall": EvaluatorRegistration(
        cli_name="locomo-recall",
        metric_name="locomo_recall",
        supported_benchmarks=frozenset({"locomo"}),
        requires_api=False,
        profile_names=frozenset(),
        profile_relative_path=None,
        config_type=None,
        factory=_build_locomo_recall,
    ),
}


def list_metrics() -> list[str]:
    """返回统一入口当前支持的 metric 名称。"""

    return sorted(_REGISTRATIONS)


def get_evaluator_registration(metric_name: str) -> EvaluatorRegistration:
    """读取 metric 注册信息，未知名称时给出支持列表。"""

    try:
        return _REGISTRATIONS[metric_name]
    except KeyError as exc:
        supported = ", ".join(list_metrics())
        raise ConfigurationError(
            f"Unknown metric '{metric_name}'. Supported: {supported}"
        ) from exc


def create_evaluator(
    metric_name: str,
    benchmark_name: str,
    *,
    profile_name: str | None = None,
    model: str | None = None,
    client: Any | None = None,
    project_root: str | None = None,
    env_file: str | None = None,
) -> Any:
    """校验兼容矩阵并构造一个新的 evaluator。

    输入:
        metric_name: registry 中的 CLI metric 名称。
        benchmark_name: 当前 run manifest 中的 benchmark 名称。
        profile_name: LLM judge profile；离线固定指标不使用。
        model: 可选 judge 模型覆盖，由 command service 从强类型 profile 提供。
        client: 可选测试 client；registry 不缓存。
        project_root: judge 延迟读取 secret 时使用的项目根。
        env_file: judge 延迟读取 secret 时使用的 `.env`。

    输出:
        Any: 新建的 answer-level evaluator 实例。
    """

    registration = get_evaluator_registration(metric_name)
    if benchmark_name not in registration.supported_benchmarks:
        raise ConfigurationError(
            f"Metric '{metric_name}' does not support benchmark "
            f"'{benchmark_name}'"
        )

    if registration.profile_names:
        selected_profile = profile_name or "compact"
        if selected_profile not in registration.profile_names:
            supported = ", ".join(sorted(registration.profile_names))
            raise ConfigurationError(
                f"Unknown evaluator profile '{selected_profile}' for "
                f"'{metric_name}'. Supported: {supported}"
            )
        return registration.factory(
            profile_name=selected_profile,
            model=model,
            client=client,
            project_root=project_root,
            env_file=env_file,
        )

    if profile_name is not None:
        raise ConfigurationError(
            f"Metric '{metric_name}' does not use an evaluator profile"
        )
    return registration.factory()


def load_evaluator_profile(
    metric_name: str,
    profile_name: str,
    project_root: str | Path | None = None,
) -> Any:
    """读取需要 profile 的 evaluator 强类型配置。

    输入:
        metric_name: registry 中的 CLI metric 名称。
        profile_name: TOML section 名称。
        project_root: 用于定位 `configs/` 的项目根目录。

    输出:
        Any: registration 声明的强类型 evaluator 配置。
    """

    registration = get_evaluator_registration(metric_name)
    if (
        registration.profile_relative_path is None
        or registration.config_type is None
    ):
        raise ConfigurationError(
            f"Metric '{metric_name}' does not use an evaluator profile"
        )
    if profile_name not in registration.profile_names:
        supported = ", ".join(sorted(registration.profile_names))
        raise ConfigurationError(
            f"Unknown evaluator profile '{profile_name}' for '{metric_name}'. "
            f"Supported: {supported}"
        )
    root = load_path_settings(project_root).project_root
    return load_typed_profile(
        root / registration.profile_relative_path,
        profile_name,
        registration.config_type,
    )


__all__ = [
    "EvaluatorRegistration",
    "create_evaluator",
    "get_evaluator_registration",
    "list_metrics",
    "load_evaluator_profile",
]

"""统一 CLI 的命令编排服务。

本模块接收已经解析好的强类型 command，负责 registry 查询、成本确认和 runner
调用。它不解析 argv、不打印终端内容，也不直接实现 method 或 metric 算法。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memory_benchmark.config import load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.registry import (
    create_evaluator,
    get_evaluator_registration,
    load_evaluator_profile,
)
from memory_benchmark.evaluators.locomo_judge import LoCoMoJudgeEvaluator
from memory_benchmark.methods.config_track import resolve_config_track
from memory_benchmark.cli.run_prediction import (
    PredictionBatchResult,
    run_registered_conversation_qa_prediction,
)
from memory_benchmark.runners.cost_calibration import (
    CalibrationSmokeCommand,
    CalibrationSmokeSummary,
    run_cost_calibration_smoke,
)
from memory_benchmark.runners.evaluation import (
    EvaluationRunSummary,
    run_artifact_evaluation,
)
from memory_benchmark.runners.prediction import PredictionRunSummary


@dataclass(frozen=True)
class PredictCommand:
    """生成 method prediction 的运行参数。"""

    project_root: str | Path
    benchmark: str
    profile: str
    config_track: str = "unified"
    method: str | None = None
    method_class: str | None = None
    allow_unsafe_custom_parallel: bool = False
    variant: str | None = None
    run_id: str | None = None
    resume: bool = False
    confirm_api: bool = False
    confirm_full: bool = False
    smoke_turn_limit: int = 20
    smoke_round_limit: int | None = None
    smoke_conversation_limit: int = 1
    smoke_session_limit: int | None = None
    smoke_max_workers: int | None = None
    max_new_conversations: int | None = None
    retry_failed_conversations: bool = False
    question_limit_per_conversation: int | None = None
    enable_efficiency_observability: bool = True
    answer_prompt_file: str | Path | None = None
    answer_prompt_profile: str = "default"
    # 默认 flat 是自定义 --method-class 的安全兜底（无 registry method 名，拼不出
    # 分层目录）。注册 method 走 CLI 时由 normalizer 显式升级为 hierarchical。
    output_layout: str = "flat"
    # --membench-sources 调试旋钮：逗号分隔的源名称（first_high/first_low/
    # third_high/third_low），仅 debug smoke 下对 membench 生效。
    membench_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluateCommand:
    """读取已有 artifacts 执行一个或多个 metric 的参数。"""

    project_root: str | Path
    run_id: str
    metrics: tuple[str, ...]
    judge_profile: str = "compact"
    confirm_api: bool = False
    max_eval_workers: int = 1

    def __post_init__(self) -> None:
        """强校验评测范围，避免空运行或路径逃逸。"""

        if not self.run_id.strip():
            raise ConfigurationError("Evaluation run_id is required")
        if not self.metrics:
            raise ConfigurationError("Evaluation requires at least one metric")
        if any(not metric.strip() for metric in self.metrics):
            raise ConfigurationError("Evaluation metric names cannot be empty")


@dataclass(frozen=True)
class RunCommand:
    """一次执行 prediction 和后续 evaluation 的参数。"""

    prediction: PredictCommand
    metrics: tuple[str, ...]
    judge_profile: str = "compact"

    def __post_init__(self) -> None:
        """要求 run 子命令至少指定一个 metric。"""

        if not self.metrics:
            raise ConfigurationError("Run command requires at least one metric")


@dataclass(frozen=True)
class RunCommandResult:
    """`run` 子命令按 concrete variant 汇总 prediction 和 evaluation。"""

    benchmark: str
    selector: str
    runs: tuple["RunVariantResult", ...]


@dataclass(frozen=True)
class RunVariantResult:
    """一个 concrete variant child run 的命令层结果。"""

    variant: str
    prediction: PredictionRunSummary
    evaluations: tuple[EvaluationRunSummary, ...]


def execute_predict(command: PredictCommand) -> PredictionBatchResult:
    """通过 method registry 执行 prediction。"""

    return run_registered_conversation_qa_prediction(
        method_name=command.method,
        method_class=command.method_class,
        allow_unsafe_custom_parallel=command.allow_unsafe_custom_parallel,
        benchmark_name=command.benchmark,
        project_root=command.project_root,
        profile_name=command.profile,
        config_track=command.config_track,
        variant=command.variant,
        run_id=command.run_id,
        resume=command.resume,
        confirm_api=command.confirm_api,
        confirm_full=command.confirm_full,
        smoke_turn_limit=command.smoke_turn_limit,
        smoke_round_limit=command.smoke_round_limit,
        smoke_conversation_limit=command.smoke_conversation_limit,
        smoke_session_limit=command.smoke_session_limit,
        smoke_max_workers=command.smoke_max_workers,
        max_new_conversations=command.max_new_conversations,
        retry_failed_conversations=command.retry_failed_conversations,
        question_limit_per_conversation=command.question_limit_per_conversation,
        enable_efficiency_observability=command.enable_efficiency_observability,
        answer_prompt_file=command.answer_prompt_file,
        answer_prompt_profile=command.answer_prompt_profile,
        output_layout=command.output_layout,
        membench_sources=command.membench_sources,
    )


def execute_calibrate_smoke(
    command: CalibrationSmokeCommand,
) -> CalibrationSmokeSummary:
    """执行成本校准 smoke 矩阵。

    该入口强制使用 runner 层的 calibration service；真实 API 成本确认仍由每个
    child prediction run 自己执行。
    """

    return run_cost_calibration_smoke(command)


def execute_evaluate(command: EvaluateCommand) -> tuple[Any, ...]:
    """基于既有 run artifacts 执行所选 evaluator。

    离线 evaluator 不读取 OpenAI 配置。需要 API 的 evaluator 会先检查
    `confirm_api`，然后把 TOML judge profile 传给懒加载 evaluator。
    """

    root = load_path_settings(command.project_root).project_root
    run_dir = _resolve_run_dir(root, command.run_id)
    manifest = _read_manifest(run_dir)
    benchmark_name = _required_manifest_text(manifest, "benchmark_name")
    method_manifest = manifest.get("method")
    native_bundle = None
    if isinstance(method_manifest, dict) and method_manifest.get("config_track") == "native":
        native_bundle = resolve_config_track(
            _required_manifest_text(manifest, "method_name"),
            benchmark_name,
            "native",
        )

    results: list[Any] = []
    for metric_name in command.metrics:
        registration = get_evaluator_registration(metric_name)
        if registration.requires_api and not command.confirm_api:
            raise ConfigurationError(
                f"Metric '{metric_name}' requires --confirm-api"
            )
        if registration.requires_api:
            profile = load_evaluator_profile(
                metric_name=metric_name,
                profile_name=command.judge_profile,
                project_root=root,
            )
            evaluator = create_evaluator(
                metric_name,
                benchmark_name,
                profile_name=profile.mode,
                model=profile.model,
                project_root=str(root),
            )
            if native_bundle is not None and metric_name == "locomo-judge":
                native_judge = native_bundle.judge_profile
                evaluator = LoCoMoJudgeEvaluator(
                    mode=profile.mode,
                    model=profile.model,
                    project_root=str(root),
                    prompt_template_override=native_judge.prompt_template,
                    skipped_categories=native_judge.skipped_categories,
                    prompt_profile_override=native_judge.profile_name,
                )
        else:
            evaluator = create_evaluator(metric_name, benchmark_name)
        results.append(
            run_artifact_evaluation(
                run_dir, evaluator, benchmark_name,
                max_workers=command.max_eval_workers,
            )
        )
    return tuple(results)


def execute_run(command: RunCommand) -> RunCommandResult:
    """先完成 prediction，再按每个 child run 的真实 run id 独立评测。"""

    prediction_batch = execute_predict(command.prediction)
    results: list[RunVariantResult] = []
    for prediction_run in prediction_batch.runs:
        evaluations = execute_evaluate(
            EvaluateCommand(
                project_root=command.prediction.project_root,
                run_id=prediction_run.run_id,
                metrics=command.metrics,
                judge_profile=command.judge_profile,
                confirm_api=command.prediction.confirm_api,
            )
        )
        results.append(
            RunVariantResult(
                variant=prediction_run.variant,
                prediction=prediction_run.summary,
                evaluations=evaluations,
            )
        )
    return RunCommandResult(
        benchmark=prediction_batch.benchmark,
        selector=prediction_batch.selector,
        runs=tuple(results),
    )


def _resolve_run_dir(project_root: Path, run_id: str) -> Path:
    """把 run id 安全解析到项目 outputs 目录内。

    兼容两种目录布局：
    - legacy: `outputs/{run_id}`
    - CLI v2: `outputs/runs/{method}/{benchmark}/{mode}/{run_id}`
    """

    outputs_root = (project_root / "outputs").resolve()
    flat_run_dir = (outputs_root / run_id).resolve()
    try:
        flat_run_dir.relative_to(outputs_root)
    except ValueError as exc:
        raise ConfigurationError(
            f"Evaluation run_id escapes outputs directory: {run_id}"
        ) from exc

    hierarchical_matches = tuple(
        manifest_path.parent
        for manifest_path in (outputs_root / "runs").glob("**/manifest.json")
        if manifest_path.parent.name == run_id
    )
    flat_exists = (flat_run_dir / "manifest.json").is_file()
    if flat_exists and hierarchical_matches:
        rendered = ", ".join(str(path) for path in hierarchical_matches)
        raise ConfigurationError(
            f"Evaluation run_id '{run_id}' is ambiguous between legacy "
            f"directory '{flat_run_dir}' and outputs/runs: {rendered}"
        )
    if flat_exists:
        return flat_run_dir
    if len(hierarchical_matches) == 1:
        return hierarchical_matches[0].resolve()
    if len(hierarchical_matches) > 1:
        rendered = ", ".join(str(path) for path in hierarchical_matches)
        raise ConfigurationError(
            f"Evaluation run_id '{run_id}' is ambiguous under outputs/runs: "
            f"{rendered}"
        )
    return flat_run_dir


def _read_manifest(run_dir: Path) -> dict[str, Any]:
    """读取 command service 所需的 run manifest。"""

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ConfigurationError(f"Run manifest is missing: {manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Run manifest JSON is invalid: {manifest_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ConfigurationError(
            f"Run manifest must be a JSON object: {manifest_path}"
        )
    return payload


def _required_manifest_text(payload: dict[str, Any], field_name: str) -> str:
    """读取 manifest 必填非空文本字段。"""

    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"Run manifest {field_name} is required")
    return value


__all__ = [
    "EvaluateCommand",
    "PredictCommand",
    "RunCommand",
    "RunCommandResult",
    "RunVariantResult",
    "CalibrationSmokeCommand",
    "execute_evaluate",
    "execute_calibrate_smoke",
    "execute_predict",
    "execute_run",
]

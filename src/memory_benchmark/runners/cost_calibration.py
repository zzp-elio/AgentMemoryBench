"""成本校准 smoke 的外层并行调度。

本模块只负责把多个 method × benchmark 的极小 prediction smoke 安排成独立
child run，并强制开启 efficiency observation。它不实现 benchmark adapter、
method adapter、metric 或真实费用计算；这些能力继续复用现有 registered prediction
service 和 analysis 层。
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed, wait
from dataclasses import dataclass
import importlib
from pathlib import Path
from typing import Callable, Iterable, Literal

from memory_benchmark.cli.run_prediction import (
    PredictionBatchResult,
    run_registered_conversation_qa_prediction,
)
from memory_benchmark.core import ConfigurationError
from memory_benchmark.runners.calibration_progress import (
    CalibrationProgressMonitor,
)
from memory_benchmark.runners.prediction import PredictionRunSummary


PredictionRunner = Callable[..., PredictionBatchResult]
CalibrationStatus = Literal["completed", "failed"]


@dataclass(frozen=True)
class CalibrationSmokeCommand:
    """成本校准 smoke 的完整运行参数。

    字段:
        project_root: 项目根目录。
        methods: 需要校准的 method 名称列表。
        benchmarks: 需要校准的 benchmark 名称列表。
        run_prefix: 本批校准的稳定 run id 前缀。
        profile: 固定为 `smoke`，避免误跑全量实验。
        resume: 是否允许 child run 复用已有 compatible artifacts。
        confirm_api: 是否允许真实 API 调用。
        smoke_turn_limit: conversation 型 benchmark 的历史 turn 裁剪上限。
        smoke_conversation_limit: 固定为 1，表示每个组合只跑一个 conversation/instance。
        max_new_conversations: 本次命令最多推进多少个未完成 conversation；仅是命令预算，
            不属于实验 identity。
        max_parallel_runs: 外层同时运行的 child run 数，当前最多为 4。
    """

    project_root: str | Path
    methods: tuple[str, ...]
    benchmarks: tuple[str, ...]
    run_prefix: str
    profile: str = "smoke"
    resume: bool = False
    confirm_api: bool = False
    smoke_turn_limit: int = 20
    smoke_conversation_limit: int = 1
    max_new_conversations: int | None = None
    max_parallel_runs: int = 2

    def __post_init__(self) -> None:
        """强校验校准范围，避免误触发大规模付费实验。"""

        object.__setattr__(
            self,
            "methods",
            _normalize_nonempty_tuple("methods", self.methods),
        )
        object.__setattr__(
            self,
            "benchmarks",
            _normalize_nonempty_tuple("benchmarks", self.benchmarks),
        )
        _validate_run_prefix(self.run_prefix)
        if self.profile != "smoke":
            raise ConfigurationError("Cost calibration only supports smoke profile")
        if self.smoke_conversation_limit != 1:
            raise ConfigurationError(
                "Cost calibration smoke must use exactly 1 conversation/instance"
            )
        if self.smoke_turn_limit < 1:
            raise ConfigurationError("smoke_turn_limit must be positive")
        if (
            self.max_new_conversations is not None
            and self.max_new_conversations < 1
        ):
            raise ConfigurationError(
                "max_new_conversations must be positive when provided"
            )
        if self.max_parallel_runs not in {1, 2, 4}:
            raise ConfigurationError("max_parallel_runs must be 1, 2 or 4")


@dataclass(frozen=True)
class CalibrationChildRunResult:
    """一个成本校准 child run 的结果记录。

    字段:
        task_index: method × benchmark 任务的稳定序号，用于恢复提交顺序。
        method: method registry 名称。
        benchmark: benchmark registry 名称。
        base_run_id: 传给 registered prediction 的 base run id。
        variant: concrete benchmark variant；失败发生在 variant 展开前时为空。
        run_id: 实际 child run id；多 variant benchmark 可能在 base 后追加 variant suffix。
        status: `completed` 或 `failed`。
        summary: 成功时的 prediction summary。
        error_type: 失败异常类型。
        error: 失败异常消息。
    """

    task_index: int
    method: str
    benchmark: str
    base_run_id: str
    variant: str | None
    run_id: str
    status: CalibrationStatus
    summary: PredictionRunSummary | object | None = None
    error_type: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class CalibrationSmokeSummary:
    """一次成本校准 smoke 矩阵的汇总结果。"""

    run_prefix: str
    methods: tuple[str, ...]
    benchmarks: tuple[str, ...]
    max_parallel_runs: int
    total_tasks: int
    completed_count: int
    failed_count: int
    runs: tuple[CalibrationChildRunResult, ...]


@dataclass(frozen=True)
class _CalibrationTask:
    """内部调度用的 method × benchmark 任务。"""

    task_index: int
    method: str
    benchmark: str
    base_run_id: str


def run_cost_calibration_smoke(
    command: CalibrationSmokeCommand,
    *,
    prediction_runner: PredictionRunner = run_registered_conversation_qa_prediction,
    dependency_preloader: Callable[[CalibrationSmokeCommand], None] | None = None,
) -> CalibrationSmokeSummary:
    """运行成本校准 smoke 矩阵。

    输入:
        command: 强类型成本校准参数。
        prediction_runner: 可注入的 registered prediction 函数；测试中使用 fake。

    输出:
        CalibrationSmokeSummary。即使部分 child run 失败，也会返回完整结果。
    """

    preloader = dependency_preloader or _preload_parallel_dependencies
    preloader(command)
    tasks = _build_tasks(command)
    results: list[CalibrationChildRunResult] = []
    progress_enabled_child = command.max_parallel_runs <= 1
    with ThreadPoolExecutor(max_workers=command.max_parallel_runs) as executor:
        child_futures: dict[Future[tuple[CalibrationChildRunResult, ...]], float]
        child_futures = {}
        for task in tasks:
            future = executor.submit(
                _run_one_task,
                task,
                command,
                prediction_runner,
                progress_enabled_child,
            )
            child_futures[future] = _clock()

        if command.max_parallel_runs > 1:
            _run_with_progress_monitor(
                futures=child_futures,
                command=command,
                tasks=tasks,
                results=results,
            )
        else:
            for future in as_completed(child_futures):
                results.extend(future.result())

    ordered_results = tuple(
        sorted(
            results,
            key=lambda item: (
                item.task_index,
                item.variant or "",
                item.run_id,
            ),
        )
    )
    failed_count = sum(1 for item in ordered_results if item.status == "failed")
    completed_count = sum(
        1 for item in ordered_results if item.status == "completed"
    )
    return CalibrationSmokeSummary(
        run_prefix=command.run_prefix,
        methods=command.methods,
        benchmarks=command.benchmarks,
        max_parallel_runs=command.max_parallel_runs,
        total_tasks=len(tasks),
        completed_count=completed_count,
        failed_count=failed_count,
        runs=ordered_results,
    )


def _preload_parallel_dependencies(command: CalibrationSmokeCommand) -> None:
    """在外层线程并发前串行预加载第三方重型依赖。

    LightMem、MemoryOS 和 A-Mem 都可能在 child run 内触发 transformers /
    sentence-transformers 的懒加载。部分版本的 transformers lazy module 在多线程首次
    导入时不稳定，因此这里先在主线程完成导入，避免 worker 互相踩全局 import 状态。
    """

    method_names = set(command.methods)
    modules: list[str] = []
    if method_names & {"lightmem", "memoryos", "amem"}:
        modules.extend(
            [
                "transformers",
                "transformers.tokenization_utils_fast",
                "sentence_transformers",
            ]
        )
    for module_name in modules:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            raise ConfigurationError(
                "Failed to preload parallel smoke dependency "
                f"{module_name!r}: {exc}"
            ) from exc


def _build_tasks(command: CalibrationSmokeCommand) -> tuple[_CalibrationTask, ...]:
    """按 method × benchmark 生成稳定 child task 列表。"""

    tasks: list[_CalibrationTask] = []
    task_index = 0
    for method in command.methods:
        for benchmark in command.benchmarks:
            tasks.append(
                _CalibrationTask(
                    task_index=task_index,
                    method=method,
                    benchmark=benchmark,
                    base_run_id=f"{command.run_prefix}-{method}-{benchmark}",
                )
            )
            task_index += 1
    return tuple(tasks)


def _run_one_task(
    task: _CalibrationTask,
    command: CalibrationSmokeCommand,
    prediction_runner: PredictionRunner,
    progress_enabled: bool = True,
) -> tuple[CalibrationChildRunResult, ...]:
    """执行一个 method × benchmark child task，并把异常转为失败结果。"""

    try:
        batch = prediction_runner(
            project_root=command.project_root,
            method_name=task.method,
            benchmark_name=task.benchmark,
            profile_name=command.profile,
            variant=None,
            run_id=task.base_run_id,
            resume=command.resume,
            confirm_api=command.confirm_api,
            confirm_full=False,
            smoke_turn_limit=command.smoke_turn_limit,
            smoke_conversation_limit=command.smoke_conversation_limit,
            smoke_max_workers=None,
            max_new_conversations=command.max_new_conversations,
            enable_efficiency_observability=True,
            progress_enabled=progress_enabled,
        )
    except Exception as exc:  # noqa: BLE001 - 调度层必须隔离单个 child 失败。
        return (
            CalibrationChildRunResult(
                task_index=task.task_index,
                method=task.method,
                benchmark=task.benchmark,
                base_run_id=task.base_run_id,
                variant=None,
                run_id=task.base_run_id,
                status="failed",
                error_type=type(exc).__name__,
                error=str(exc),
            ),
        )

    return tuple(
        CalibrationChildRunResult(
            task_index=task.task_index,
            method=task.method,
            benchmark=task.benchmark,
            base_run_id=task.base_run_id,
            variant=child.variant,
            run_id=child.run_id,
            status="completed",
            summary=child.summary,
        )
        for child in batch.runs
    )


def _run_with_progress_monitor(
    *,
    futures: dict[Future[tuple[CalibrationChildRunResult, ...]], float],
    command: CalibrationSmokeCommand,
    tasks: tuple[_CalibrationTask, ...],
    results: list[CalibrationChildRunResult],
) -> None:
    """在并行模式下用统一进度监控表收集 child run 结果。

    本函数在 ThreadPoolExecutor 上下文内调用。它创建 CalibrationProgressMonitor，
    定期轮询各 child run 的 progress.json，并用 Rich Live(Table) 统一展示状态；
    child run 各自的 Rich 进度条已被禁用。
    """

    run_ids = tuple(task.base_run_id for task in tasks)
    methods = tuple(task.method for task in tasks)
    benchmarks = tuple(task.benchmark for task in tasks)
    monitor = CalibrationProgressMonitor(
        output_root=Path(command.project_root) / "outputs",
        run_ids=run_ids,
        methods=methods,
        benchmarks=benchmarks,
    )
    monitor.start()
    try:
        for run_id, task in zip(run_ids, tasks, strict=True):
            monitor.start_task(run_id)
        pending = set(futures.keys())
        while pending:
            done, pending = wait(pending, timeout=0.2)
            for future in done:
                run_results = future.result()
                results.extend(run_results)
                for run_result in run_results:
                    if run_result.status == "completed":
                        monitor.mark_completed(run_result.run_id)
                    else:
                        monitor.mark_failed(
                            run_result.run_id,
                            run_result.error or "unknown",
                        )
            monitor._refresh_table()
    finally:
        monitor.stop()


def _clock() -> float:
    """返回单调时间秒数。独立函数便于测试注入。"""

    import time as _time

    return _time.monotonic()


def _normalize_nonempty_tuple(
    field_name: str,
    values: Iterable[str],
) -> tuple[str, ...]:
    """把 CLI/Python 输入规范成非空字符串 tuple。"""

    if isinstance(values, str):
        raise ConfigurationError(f"{field_name} must be a sequence of names")
    normalized = tuple(str(value).strip() for value in values)
    if not normalized:
        raise ConfigurationError(f"{field_name} must not be empty")
    if any(not value for value in normalized):
        raise ConfigurationError(f"{field_name} must not contain empty values")
    return normalized


def _validate_run_prefix(run_prefix: str) -> None:
    """校验 run_prefix 不为空且不会变成路径逃逸。"""

    normalized = run_prefix.strip()
    if not normalized:
        raise ConfigurationError("run_prefix must not be blank")
    if normalized in {".", ".."}:
        raise ConfigurationError(f"run_prefix must not be unsafe: {run_prefix}")
    if "/" in normalized or "\\" in normalized:
        raise ConfigurationError(
            f"run_prefix must not contain path separators: {run_prefix}"
        )
    if Path(normalized).is_absolute():
        raise ConfigurationError(f"run_prefix must not be absolute: {run_prefix}")


__all__ = [
    "CalibrationChildRunResult",
    "CalibrationSmokeCommand",
    "CalibrationSmokeSummary",
    "run_cost_calibration_smoke",
]

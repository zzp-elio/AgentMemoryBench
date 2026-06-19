"""Agent Memory Benchmark 统一命令行入口。

本模块只解析 `predict/evaluate/run` 子命令、构造强类型 command，并把结果交给
command service。它不读取 benchmark、不构造 method、不调用模型，也不写实验 artifact。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from rich.console import Console

from memory_benchmark.benchmark_adapters import list_prediction_benchmarks
from memory_benchmark.core import MemoryBenchmarkError
from memory_benchmark.evaluators.registry import list_metrics
from memory_benchmark.methods.registry import list_methods

from .commands import (
    CalibrationSmokeCommand,
    EvaluateCommand,
    PredictCommand,
    RunCommand,
    execute_calibrate_smoke,
    execute_evaluate,
    execute_predict,
    execute_run,
)


CONSOLE = Console()
ERROR_CONSOLE = Console(stderr=True)
MAX_NEW_CONVERSATIONS_HELP = (
    "per-command budget: advance at most this many unfinished conversations in "
    "this invocation. It does not become experiment identity and does not "
    "affect resume compatibility."
)


def main(argv: list[str] | None = None) -> int:
    """解析统一 CLI，并返回适合 shell 的退出码。"""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = _dispatch(args)
    except MemoryBenchmarkError as exc:
        if args.debug:
            raise
        ERROR_CONSOLE.print(f"[bold red]Error:[/bold red] {exc}")
        return 2

    _print_result(result)
    return _exit_code_for_result(result)


def _build_parser() -> argparse.ArgumentParser:
    """构造包含三个子命令的 argparse parser。"""

    parser = argparse.ArgumentParser(
        prog="memory-benchmark",
        description="Run conversation-QA memory benchmarks and answer-level metrics.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Re-raise project errors with a traceback.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    predict_parser = subparsers.add_parser(
        "predict",
        help="Generate method answers without computing metrics.",
    )
    _add_prediction_arguments(predict_parser)

    evaluate_parser = subparsers.add_parser(
        "evaluate",
        help="Evaluate existing prediction artifacts without rerunning the method.",
    )
    _add_common_root_argument(evaluate_parser)
    evaluate_parser.add_argument("--run-id", required=True)
    evaluate_parser.add_argument(
        "--metric",
        action="append",
        required=True,
        choices=list_metrics(),
        dest="metrics",
    )
    evaluate_parser.add_argument(
        "--judge-profile",
        default="compact",
        choices=["compact", "detailed"],
    )
    evaluate_parser.add_argument("--confirm-api", action="store_true")

    run_parser = subparsers.add_parser(
        "run",
        help="Generate predictions and then evaluate the produced artifacts.",
    )
    _add_prediction_arguments(run_parser)
    run_parser.add_argument(
        "--metric",
        action="append",
        required=True,
        choices=list_metrics(),
        dest="metrics",
    )
    run_parser.add_argument(
        "--judge-profile",
        default="compact",
        choices=["compact", "detailed"],
    )

    calibration_parser = subparsers.add_parser(
        "calibrate-smoke",
        help="Run a tiny method × benchmark smoke matrix for API cost calibration.",
    )
    _add_calibration_arguments(calibration_parser)
    return parser


def _add_common_root_argument(parser: argparse.ArgumentParser) -> None:
    """为子命令添加项目根目录参数。"""

    parser.add_argument(
        "--root",
        default=".",
        help="Project root containing configs/, data/, third_party/ and outputs/.",
    )


def _add_prediction_arguments(parser: argparse.ArgumentParser) -> None:
    """为 predict/run 添加一致的 prediction 参数。"""

    _add_common_root_argument(parser)
    parser.add_argument("--method", required=True, choices=list_methods())
    parser.add_argument(
        "--benchmark",
        required=True,
        choices=list_prediction_benchmarks(),
    )
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--variant", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--confirm-api", action="store_true")
    parser.add_argument("--confirm-full", action="store_true")
    parser.add_argument("--smoke-turn-limit", type=int, default=20)
    parser.add_argument(
        "--smoke-conversation-limit",
        type=int,
        choices=[1, 2],
        default=1,
    )
    parser.add_argument(
        "--smoke-max-workers",
        type=int,
        choices=[1, 2],
        default=None,
    )
    parser.add_argument(
        "--enable-efficiency-observability",
        action="store_true",
        help="Write raw token/latency observations for this prediction run.",
    )
    parser.add_argument(
        "--max-new-conversations",
        type=int,
        default=None,
        help=MAX_NEW_CONVERSATIONS_HELP,
    )


def _add_calibration_arguments(parser: argparse.ArgumentParser) -> None:
    """为成本校准 smoke 添加矩阵调度参数。"""

    _add_common_root_argument(parser)
    parser.add_argument(
        "--method",
        action="append",
        required=True,
        choices=list_methods(),
        dest="methods",
        help="Method to include; repeat for multiple methods.",
    )
    parser.add_argument(
        "--benchmark",
        action="append",
        required=True,
        choices=list_prediction_benchmarks(),
        dest="benchmarks",
        help="Benchmark to include; repeat for multiple benchmarks.",
    )
    parser.add_argument("--run-prefix", required=True)
    parser.add_argument("--confirm-api", action="store_true")
    resume_group = parser.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume",
        action="store_true",
        dest="resume",
        default=False,
        help="Resume compatible child runs when their manifests already exist.",
    )
    resume_group.add_argument(
        "--no-resume",
        action="store_false",
        dest="resume",
        help="Start child runs without resume; this is the default.",
    )
    parser.add_argument(
        "--smoke-turn-limit",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--max-new-conversations",
        type=int,
        default=None,
        help=MAX_NEW_CONVERSATIONS_HELP,
    )
    parser.add_argument(
        "--max-parallel-runs",
        type=int,
        choices=[1, 2, 4],
        default=2,
    )


def _dispatch(args: argparse.Namespace) -> Any:
    """把 argparse namespace 映射为强类型 command。"""

    if args.command == "predict":
        return execute_predict(_prediction_command_from_args(args))
    if args.command == "evaluate":
        return execute_evaluate(
            EvaluateCommand(
                project_root=Path(args.root),
                run_id=args.run_id,
                metrics=tuple(args.metrics),
                judge_profile=args.judge_profile,
                confirm_api=args.confirm_api,
            )
        )
    if args.command == "run":
        return execute_run(
            RunCommand(
                prediction=_prediction_command_from_args(args),
                metrics=tuple(args.metrics),
                judge_profile=args.judge_profile,
            )
        )
    if args.command == "calibrate-smoke":
        return execute_calibrate_smoke(
            CalibrationSmokeCommand(
                project_root=Path(args.root),
                methods=tuple(args.methods),
                benchmarks=tuple(args.benchmarks),
                run_prefix=args.run_prefix,
                resume=args.resume,
                confirm_api=args.confirm_api,
                smoke_turn_limit=args.smoke_turn_limit,
                max_new_conversations=args.max_new_conversations,
                max_parallel_runs=args.max_parallel_runs,
            )
        )
    raise MemoryBenchmarkError(f"Unsupported command: {args.command}")


def _prediction_command_from_args(args: argparse.Namespace) -> PredictCommand:
    """从 predict/run 参数构造统一 prediction command。"""

    return PredictCommand(
        project_root=Path(args.root),
        method=args.method,
        benchmark=args.benchmark,
        profile=args.profile,
        variant=args.variant,
        run_id=args.run_id,
        resume=args.resume,
        confirm_api=args.confirm_api,
        confirm_full=args.confirm_full,
        smoke_turn_limit=args.smoke_turn_limit,
        smoke_conversation_limit=args.smoke_conversation_limit,
        smoke_max_workers=args.smoke_max_workers,
        max_new_conversations=args.max_new_conversations,
        enable_efficiency_observability=args.enable_efficiency_observability,
    )


def _print_result(result: Any) -> None:
    """把 command summary 以 JSON 形式输出到 Rich console。"""

    payload = _to_json_value(result)
    CONSOLE.print_json(json.dumps(payload, ensure_ascii=False))


def _exit_code_for_result(result: Any) -> int:
    """根据 command summary 返回 shell 退出码。"""

    failed_count = getattr(result, "failed_count", 0)
    try:
        return 1 if int(failed_count) > 0 else 0
    except (TypeError, ValueError):
        return 0


def _to_json_value(value: Any) -> Any:
    """递归把 summary/dataclass 转换为 JSON 可序列化值。"""

    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, tuple | list):
        return [_to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {
            str(key): _to_json_value(item)
            for key, item in vars(value).items()
        }
    return value


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]

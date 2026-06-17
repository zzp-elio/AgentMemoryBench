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
    EvaluateCommand,
    PredictCommand,
    RunCommand,
    execute_evaluate,
    execute_predict,
    execute_run,
)


CONSOLE = Console()
ERROR_CONSOLE = Console(stderr=True)


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
    return 0


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
    )


def _print_result(result: Any) -> None:
    """把 command summary 以 JSON 形式输出到 Rich console。"""

    payload = _to_json_value(result)
    CONSOLE.print_json(json.dumps(payload, ensure_ascii=False))


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

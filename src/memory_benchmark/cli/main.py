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

from memory_benchmark.benchmark_adapters import (
    get_benchmark_registration,
    list_prediction_benchmarks,
)
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
    evaluate_parser.add_argument(
        "--allow-api",
        "--confirm-api",
        dest="confirm_api",
        action="store_true",
    )
    evaluate_parser.add_argument(
        "--workers",
        "--max-eval-workers",
        dest="max_eval_workers",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel workers for evaluation (default: 1, serial).",
    )

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

    parser.add_argument(
        "prediction_mode",
        nargs="?",
        choices=["smoke", "formal"],
        help=(
            "CLI v2 mode: smoke for tiny connectivity tests, formal for "
            "official-profile runs."
        ),
    )
    _add_common_root_argument(parser)
    parser.add_argument("--method", choices=list_methods(), default=None)
    parser.add_argument(
        "--method-class",
        default=None,
        help="Custom user method class in module:ClassName format.",
    )
    parser.add_argument(
        "--allow-unsafe-custom-parallel",
        action="store_true",
        help=(
            "Allow workers>1 for a custom --method-class. The user is "
            "responsible for run, benchmark, worker and conversation "
            "isolation."
        ),
    )
    parser.add_argument(
        "--benchmark",
        required=True,
        choices=list_prediction_benchmarks(),
    )
    parser.add_argument("--profile", choices=["smoke", "official-full"], default=None)
    parser.add_argument("--variant", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--allow-api",
        "--confirm-api",
        dest="confirm_api",
        action="store_true",
    )
    parser.add_argument("--confirm-full", action="store_true")
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--turns", type=int, default=None)
    parser.add_argument("--sessions", type=int, default=None)
    parser.add_argument("--sources", type=int, default=None)
    parser.add_argument(
        "--membench-sources",
        type=str,
        default=None,
        help="Comma-separated MemBench source filters: first_high,first_low,third_high,third_low (debug knob, default=all 4)",
    )
    parser.add_argument("--smoke-turn-limit", type=int, default=None)
    parser.add_argument("--conversations", type=int, default=None)
    parser.add_argument(
        "--smoke-conversation-limit",
        type=int,
        default=None,
    )
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument(
        "--smoke-max-workers",
        type=int,
        default=None,
        help="Override smoke conversation worker count; validated by method profile.",
    )
    efficiency_group = parser.add_mutually_exclusive_group()
    efficiency_group.add_argument(
        "--enable-efficiency-observability",
        dest="enable_efficiency_observability",
        action="store_true",
        default=True,
        help=(
            "Write raw token/latency observations for this prediction run "
            "(default)."
        ),
    )
    efficiency_group.add_argument(
        "--disable-efficiency-observability",
        dest="enable_efficiency_observability",
        action="store_false",
        help="Disable prediction efficiency observation for this run.",
    )
    parser.add_argument(
        "--max-new-conversations",
        type=int,
        default=None,
        help=MAX_NEW_CONVERSATIONS_HELP,
    )
    parser.add_argument(
        "--conversation-budget",
        type=int,
        default=None,
        help=(
            "formal mode only: advance at most this many unfinished "
            "conversations in this invocation."
        ),
    )
    parser.add_argument(
        "--retry-failed",
        dest="retry_failed_conversations",
        action="store_true",
        help=(
            "Retry failed conversations recorded in checkpoints. By default, "
            "failed conversations stay quarantined during resume to avoid "
            "repeated API burn."
        ),
    )
    parser.add_argument(
        "--questions-per-conversation",
        type=int,
        default=None,
        help="smoke mode only: maximum questions per selected conversation.",
    )
    parser.add_argument(
        "--question-limit-per-conversation",
        type=int,
        default=None,
        help=(
            "Per-command question budget for each selected conversation. It is "
            "not experiment identity, so a later resume can increase it."
        ),
    )
    parser.add_argument(
        "--answer-prompt-file",
        default=None,
        help=(
            "Path to a custom framework answer prompt template containing "
            "{question} and {memory_context}."
        ),
    )
    parser.add_argument(
        "--answer-prompt-profile",
        default="default",
        help="Answer prompt profile name written to framework-reader metadata.",
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
        choices=[1, 2, 3, 4],
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
                max_eval_workers=args.max_eval_workers,
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

    normalized = _normalize_prediction_args(args)
    _validate_method_selector(args, normalized)
    return PredictCommand(
        project_root=Path(args.root),
        method=args.method,
        method_class=args.method_class,
        allow_unsafe_custom_parallel=args.allow_unsafe_custom_parallel,
        benchmark=args.benchmark,
        profile=normalized["profile"],
        variant=args.variant,
        run_id=args.run_id,
        resume=args.resume,
        confirm_api=args.confirm_api,
        confirm_full=normalized["confirm_full"],
        smoke_turn_limit=normalized["smoke_turn_limit"],
        smoke_round_limit=normalized["smoke_round_limit"],
        smoke_conversation_limit=normalized["smoke_conversation_limit"],
        smoke_session_limit=normalized["smoke_session_limit"],
        smoke_max_workers=normalized["workers"],
        max_new_conversations=normalized["max_new_conversations"],
        retry_failed_conversations=args.retry_failed_conversations,
        question_limit_per_conversation=normalized[
            "question_limit_per_conversation"
        ],
        enable_efficiency_observability=args.enable_efficiency_observability,
        answer_prompt_file=(
            None
            if args.answer_prompt_file is None
            else Path(args.answer_prompt_file)
        ),
        answer_prompt_profile=args.answer_prompt_profile,
        output_layout=normalized["output_layout"],
        membench_sources=tuple(normalized["membench_sources"]),
    )


def _validate_method_selector(
    args: argparse.Namespace,
    normalized: dict[str, Any],
) -> None:
    """校验内置 method 和用户自定义 method class 的选择关系。"""

    if bool(args.method) == bool(args.method_class):
        raise MemoryBenchmarkError("Pass exactly one of --method or --method-class")
    workers = normalized["workers"]
    if args.method_class and workers is not None and workers > 1:
        if not args.allow_unsafe_custom_parallel:
            raise MemoryBenchmarkError(
                "Custom --method-class uses workers=1 by default. Pass "
                "--allow-unsafe-custom-parallel to use workers>1 after "
                "confirming your adapter is safe for parallel runs."
            )


def _normalize_prediction_args(args: argparse.Namespace) -> dict[str, Any]:
    """把 CLI v2 和 legacy prediction 参数归一化为 command service 字段。"""

    if args.prediction_mode is None:
        return _normalize_legacy_prediction_args(args)
    if args.profile is not None:
        raise MemoryBenchmarkError(
            "Do not pass --profile with 'predict smoke' or 'predict formal'; "
            "the subcommand already selects the run mode."
        )
    if args.prediction_mode == "smoke":
        return _normalize_smoke_prediction_args(args)
    return _normalize_formal_prediction_args(args)


_LEGACY_SMOKE_HISTORY_DEFAULT = 20


_MEMBENCH_SOURCE_NAMES = frozenset(
    {"first_high", "first_low", "third_high", "third_low"}
)


def _validate_membench_sources(raw: str | None, *, is_membench: bool = False) -> tuple[str, ...]:
    """校验 --membench-sources 值域；非 membench 传入该旗标必须 fail-fast。"""
    if not is_membench:
        if raw is not None:
            raise MemoryBenchmarkError(
                "--membench-sources is only supported for MemBench smoke"
            )
        return ()
    if raw is None:
        return tuple(sorted(_MEMBENCH_SOURCE_NAMES))
    names = [n.strip() for n in raw.split(",") if n.strip()]
    if not names:
        raise MemoryBenchmarkError(
            "--membench-sources must be a comma-separated list of: "
            + ", ".join(sorted(_MEMBENCH_SOURCE_NAMES))
        )
    for name in names:
        if name not in _MEMBENCH_SOURCE_NAMES:
            raise MemoryBenchmarkError(
                f"Unknown --membench-sources value '{name}'. Allowed: "
                + ", ".join(sorted(_MEMBENCH_SOURCE_NAMES))
            )
    return tuple(names)


def _default_smoke_history_limit(benchmark_name: str) -> int:
    """返回某 benchmark smoke 历史轴的默认预算。

    只有完成审计并注册了 `BenchmarkSmokePolicy` 的 benchmark（当前五个
    benchmark 已全部注册）才使用其声明的 `default_history_limit`；
    尚无 policy 的 benchmark 继续沿用 legacy 全局默认值 20。
    """

    smoke_policy = getattr(get_benchmark_registration(benchmark_name), "smoke_policy", None)
    if smoke_policy is None:
        return _LEGACY_SMOKE_HISTORY_DEFAULT
    return smoke_policy.default_history_limit


def _normalize_legacy_prediction_args(args: argparse.Namespace) -> dict[str, Any]:
    """保持旧 `predict --profile ...` 写法可用，并接入新别名。"""

    _reject_conflicting_aliases(args)
    _validate_smoke_axis_args(args)
    default_history_limit = _default_smoke_history_limit(args.benchmark)
    return {
        "profile": args.profile or "smoke",
        "confirm_full": args.confirm_full,
        "smoke_turn_limit": _positive_or_default(
            args.rounds if args.rounds is not None else args.smoke_turn_limit,
            default=default_history_limit,
            field_name="rounds",
        ),
        "smoke_round_limit": None,
        "smoke_conversation_limit": _positive_or_default(
            (
                args.conversations
                if args.conversations is not None
                else args.smoke_conversation_limit
            ),
            default=1,
            field_name="conversations",
        ),
        "smoke_session_limit": _positive_or_none(
            args.sessions,
            field_name="sessions",
        ),
        "workers": _positive_or_none(
            args.workers if args.workers is not None else args.smoke_max_workers,
            field_name="workers",
        ),
        "max_new_conversations": _positive_or_none(
            (
                args.conversation_budget
                if args.conversation_budget is not None
                else args.max_new_conversations
            ),
            field_name="conversation budget",
        ),
        "question_limit_per_conversation": _positive_or_none(
            (
                args.questions_per_conversation
                if args.questions_per_conversation is not None
                else args.question_limit_per_conversation
            ),
            field_name="questions per conversation",
        ),
        # ws02.6: legacy `--profile` 也走分层布局，杜绝结果扁平散落 outputs/ 根。
        # `--profile` 的彻底废弃另起 actor 卡（涉及 legacy-only 组合的测试删改）。
        "output_layout": "hierarchical",
        "membench_sources": _validate_membench_sources(
            args.membench_sources, is_membench=(args.benchmark == "membench")
        ),
    }


def _normalize_smoke_prediction_args(args: argparse.Namespace) -> dict[str, Any]:
    """校验并归一化 `predict smoke` 参数。"""

    _reject_conflicting_aliases(args)
    _validate_smoke_axis_args(args)
    if args.resume:
        raise MemoryBenchmarkError("predict smoke does not support --resume")
    if args.retry_failed_conversations:
        raise MemoryBenchmarkError("predict smoke does not support --retry-failed")
    if args.conversation_budget is not None or args.max_new_conversations is not None:
        raise MemoryBenchmarkError(
            "predict smoke does not support --conversation-budget or "
            "--max-new-conversations; use --conversations"
        )
    halumem_smoke = args.benchmark == "halumem"
    round_limit = (
        args.rounds if args.rounds is not None else args.smoke_turn_limit
    )
    default_history_limit = _default_smoke_history_limit(args.benchmark)
    return {
        "profile": "smoke",
        "confirm_full": False,
        "smoke_turn_limit": _positive_or_default(
            round_limit,
            default=default_history_limit,
            field_name="rounds",
        ),
        "smoke_round_limit": None
        if halumem_smoke
        else _positive_or_default(
            round_limit,
            default=default_history_limit,
            field_name="rounds",
        ),
        "smoke_conversation_limit": _positive_or_default(
            (
                args.conversations
                if args.conversations is not None
                else args.smoke_conversation_limit
            ),
            default=1,
            field_name="conversations",
        ),
        "smoke_session_limit": None,
        "workers": _positive_or_none(
            args.workers if args.workers is not None else args.smoke_max_workers,
            field_name="workers",
        ),
        "max_new_conversations": None,
        "question_limit_per_conversation": _positive_or_default(
            (
                args.questions_per_conversation
                if args.questions_per_conversation is not None
                else args.question_limit_per_conversation
            ),
            default=1,
            field_name="questions per conversation",
        ),
        "output_layout": "hierarchical",
        "membench_sources": _validate_membench_sources(
            args.membench_sources, is_membench=(args.benchmark == "membench")
        ),
    }


def _normalize_formal_prediction_args(args: argparse.Namespace) -> dict[str, Any]:
    """校验并归一化 `predict formal` 参数。"""

    _reject_conflicting_aliases(args)
    if args.retry_failed_conversations and not args.resume:
        raise MemoryBenchmarkError("--retry-failed requires --resume")
    if args.rounds is not None or args.smoke_turn_limit is not None:
        raise MemoryBenchmarkError("predict formal does not support --rounds")
    if args.turns is not None:
        raise MemoryBenchmarkError("predict formal does not support --turns")
    if getattr(args, "membench_sources", None) is not None:
        # smoke 调试旋钮；formal 静默忽略会让人误以为跑了部分源。
        raise MemoryBenchmarkError("predict formal does not support --membench-sources")
    if args.conversations is not None or args.smoke_conversation_limit is not None:
        raise MemoryBenchmarkError("predict formal does not support --conversations")
    if args.sessions is not None:
        raise MemoryBenchmarkError("predict formal does not support --sessions")
    if args.sources is not None:
        raise MemoryBenchmarkError("predict formal does not support --sources")
    if (
        args.questions_per_conversation is not None
        or args.question_limit_per_conversation is not None
    ):
        raise MemoryBenchmarkError(
            "predict formal does not support --questions-per-conversation"
        )
    return {
        "profile": "official-full",
        "confirm_full": True,
        "smoke_turn_limit": 20,
        "smoke_round_limit": None,
        "smoke_conversation_limit": 1,
        "smoke_session_limit": None,
        "workers": _positive_or_none(
            args.workers if args.workers is not None else args.smoke_max_workers,
            field_name="workers",
        ),
        "max_new_conversations": _positive_or_none(
            (
                args.conversation_budget
                if args.conversation_budget is not None
                else args.max_new_conversations
            ),
            field_name="conversation budget",
        ),
        "question_limit_per_conversation": None,
        "output_layout": "hierarchical",
        "membench_sources": (),
    }


def _reject_conflicting_aliases(args: argparse.Namespace) -> None:
    """拒绝新旧别名同时出现，避免用户误解最终生效值。"""

    if args.workers is not None and args.smoke_max_workers is not None:
        raise MemoryBenchmarkError("Use either --workers or --smoke-max-workers, not both")
    if args.rounds is not None and args.smoke_turn_limit is not None:
        raise MemoryBenchmarkError("Use either --rounds or --smoke-turn-limit, not both")
    if args.conversations is not None and args.smoke_conversation_limit is not None:
        raise MemoryBenchmarkError(
            "Use either --conversations or --smoke-conversation-limit, not both"
        )
    if (
        args.questions_per_conversation is not None
        and args.question_limit_per_conversation is not None
    ):
        raise MemoryBenchmarkError(
            "Use either --questions-per-conversation or "
            "--question-limit-per-conversation, not both"
        )
    if args.conversation_budget is not None and args.max_new_conversations is not None:
        raise MemoryBenchmarkError(
            "Use either --conversation-budget or --max-new-conversations, not both"
        )


def _validate_smoke_axis_args(args: argparse.Namespace) -> None:
    """按 benchmark 校验 smoke 历史裁剪轴。"""

    if args.benchmark == "halumem":
        if (
            args.rounds is not None
            or args.smoke_turn_limit is not None
            or args.turns is not None
            or args.sessions is not None
            or args.sources is not None
            or args.conversations is not None
            or args.smoke_conversation_limit is not None
            or args.questions_per_conversation is not None
            or args.question_limit_per_conversation is not None
        ):
            raise MemoryBenchmarkError(
                "HaluMem smoke has a fixed shape and does not accept cropping parameters"
            )
        return
    if args.benchmark == "locomo":
        # LoCoMo 注册的 BenchmarkSmokePolicy.history_axis 是 "rounds"（见
        # benchmark_adapters/registry.py 的 LOCOMO_SMOKE_POLICY）；turns/
        # sessions/sources 是其他尚未审计 benchmark 的轴，对 LoCoMo 一律
        # fail-fast，避免用户以为传了就生效。
        if (
            args.turns is not None
            or args.sessions is not None
            or args.sources is not None
        ):
            raise MemoryBenchmarkError(
                "LoCoMo smoke uses --rounds; do not pass --turns, --sessions "
                "or --sources"
            )
        return
    if args.benchmark == "longmemeval":
        # LongMemEval registered history_axis is "rounds" (LONGMEMEVAL_SMOKE_POLICY);
        # only --rounds is the audited smoke axis. --turns/--sessions/--sources are
        # unsupported (membench sources / halumem sessions / unregistered turns) and
        # must fail-fast rather than be silently ignored.
        if (
            args.turns is not None
            or args.sessions is not None
            or args.sources is not None
        ):
            raise MemoryBenchmarkError(
                "LongMemEval smoke uses --rounds; do not pass --turns, --sessions "
                "or --sources"
            )
        return
    if args.benchmark == "membench":
        # MemBench registered history_axis is "rounds" (MEMBENCH_SMOKE_POLICY);
        # --membench-sources is a debug knob for selecting source files, not the
        # generic --sources axis. Unregistered axes must fail-fast.
        if args.turns is not None or args.sessions is not None or args.sources is not None:
            raise MemoryBenchmarkError(
                "MemBench smoke uses --rounds; do not pass --turns, --sessions "
                "or --sources"
            )
        _validate_membench_sources(args.membench_sources)
        return
    if args.benchmark == "beam":
        if (
            args.turns is not None
            or args.sessions is not None
            or args.sources is not None
        ):
            raise MemoryBenchmarkError(
                "BEAM smoke uses --rounds; do not pass --turns, --sessions or --sources"
            )
        return
    if args.sessions is not None:
        raise MemoryBenchmarkError(
            "--sessions is only supported for HaluMem smoke"
        )
    if args.turns is not None or args.sources is not None:
        raise MemoryBenchmarkError(
            f"{args.benchmark} smoke has not registered --turns or --sources"
        )


def _positive_or_default(
    value: int | None,
    *,
    default: int,
    field_name: str,
) -> int:
    """返回正整数参数；未提供时使用默认值。"""

    normalized = default if value is None else value
    if normalized < 1:
        raise MemoryBenchmarkError(f"{field_name} must be at least 1")
    return normalized


def _positive_or_none(value: int | None, *, field_name: str) -> int | None:
    """返回可选正整数参数；未提供时保持 None。"""

    if value is None:
        return None
    if value < 1:
        raise MemoryBenchmarkError(f"{field_name} must be at least 1")
    return value


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

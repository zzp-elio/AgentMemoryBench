"""AgentMemoryBench 命令行入口 (`memory-benchmark` / `python -m memory_benchmark`)。

提供清晰的阶段解耦子命令架构：
1. `run`：一站式全流程评测 (Ingest -> Query -> Evaluate)；
2. `ingest`：阶段一，仅将长会话历史写入外部 Memory Server；
3. `query`：阶段二，仅根据已构建的记忆检索上下文并生成回答；
4. `eval`：阶段三，仅离线读取预测产物计算评测指标 (F1 / ExactMatch / LLM-Judge)。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from memory_benchmark.benchmark_adapters import get_adapter, list_benchmarks
from memory_benchmark.core import (
    ConfigurationError,
    Conversation,
    Dataset,
    MemoryBenchmarkError,
    create_provider,
    list_methods,
    load_app_config,
)
from memory_benchmark.evaluators import create_evaluator, list_evaluators
from memory_benchmark.readers import (
    FakeAnswerLLMClient,
    FrameworkAnswerReader,
    OpenAICompatibleAnswerLLMClient,
)
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.runners.prediction import PredictionRunPolicy, run_predictions
from memory_benchmark.storage import RunContext


def _slice_dataset(
    dataset: Dataset,
    smoke: bool = False,
    max_conversations: int | None = None,
    max_questions: int | None = None,
    max_sessions: int | None = None,
    max_turns_per_session: int | None = None,
) -> Dataset:
    """数据集裁剪引擎：支持一键 `--smoke` 快速冒烟或指定深度裁剪。"""
    convs: list[Conversation] = []
    base_convs = list(dataset.conversations)

    # 1. 一键冒烟锁定：极简截取 1 个会话、1 个 Session、1 道题（实现秒级真实微服务与网络连通性冒烟）
    if smoke:
        max_conversations = 1
        max_sessions = 1
        max_questions = 1

    if max_conversations and max_conversations > 0:
        base_convs = base_convs[:max_conversations]

    for c in base_convs:
        sessions = list(c.sessions)
        if max_sessions and max_sessions > 0:
            sessions = sessions[:max_sessions]
        if max_turns_per_session and max_turns_per_session > 0:
            sessions = [
                replace(s, turns=list(s.turns[:max_turns_per_session]))
                for s in sessions
            ]
        questions = list(c.questions)
        if max_questions and max_questions > 0:
            questions = questions[:max_questions]
        q_ids = {q.question_id for q in questions}
        gold_answers = {qid: ga for qid, ga in c.gold_answers.items() if qid in q_ids}
        convs.append(
            replace(
                c,
                sessions=sessions,
                questions=questions,
                gold_answers=gold_answers,
            )
        )
    return Dataset(dataset.dataset_name, convs, dict(dataset.metadata))


def _add_common_data_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("Benchmark & Data Options")
    g.add_argument(
        "-b",
        "--benchmark",
        default="locomo",
        choices=list_benchmarks(),
        help="Target benchmark dataset.",
    )
    g.add_argument(
        "--smoke",
        action="store_true",
        default=False,
        help="One-click smoke test mode: safely clamps to 1 conversation, 1 session, and 1 question for rapid validation.",
    )
    g.add_argument(
        "--project-root",
        default=".",
        help="Path to project root directory.",
    )
    # 隐藏的微调内部参数（保持向后兼容，不暴露给普通用户）
    g.add_argument("-c", "--max-conversations", type=int, default=None, help=argparse.SUPPRESS)
    g.add_argument("-q", "--max-questions", "--max-questions-per-conversation", type=int, default=None, dest="max_questions", help=argparse.SUPPRESS)
    g.add_argument("--max-sessions", "--max-sessions-per-conversation", type=int, default=None, dest="max_sessions", help=argparse.SUPPRESS)
    g.add_argument("--max-turns", "--max-turns-per-session", type=int, default=None, dest="max_turns", help=argparse.SUPPRESS)


def _add_common_conn_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("Memory Server Connection Options")
    g.add_argument(
        "-m",
        "--method",
        default="mock",
        choices=list_methods(),
        help="Memory provider mode: 'http' for remote memory server, 'mock' for local in-memory test.",
    )
    g.add_argument(
        "-u",
        "--server-url",
        default=None,
        help="Base URL of remote Memory Server when --method=http (e.g. http://127.0.0.1:8002).",
    )
    # 隐藏兼容参数
    g.add_argument("-k", "--top-k", type=int, default=10, help=argparse.SUPPRESS)
    g.add_argument("--skip-ingest", action="store_true", default=False, help=argparse.SUPPRESS)
    g.add_argument("--reuse-ingest-run-id", "--isolation-prefix", default=None, dest="reuse_ingest_run_id", help=argparse.SUPPRESS)


def _add_common_exec_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("Execution & Concurrency Options")
    g.add_argument(
        "-w",
        "--max-workers",
        type=int,
        default=1,
        help="Max worker threads for concurrent conversation evaluation.",
    )
    g.add_argument(
        "--run-id",
        default=None,
        help="Explicit experiment run_id identifier.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory-benchmark",
        description="Standardized C/S evaluation middleware for AI Agent long-term memory systems.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # 顶层全局参数（保证不带子命令时默认以 run 模式执行，并完全向后兼容旧版调用）
    _add_common_data_args(parser)
    _add_common_conn_args(parser)
    _add_common_exec_args(parser)
    p_top_eval = parser.add_argument_group("Metrics & LLM Options")
    p_top_eval.add_argument(
        "--metrics",
        default="f1",
        help=f"Comma-separated answer metrics ({', '.join(list_evaluators())}).",
    )
    p_top_eval.add_argument(
        "--mock-llm",
        action="store_true",
        default=False,
        help="Force using offline deterministic FakeAnswerLLMClient instead of real external LLM API.",
    )
    p_top_eval.add_argument("--confirm-api", action="store_true", default=False, help=argparse.SUPPRESS)
    p_top_eval.add_argument(
        "--run-dir",
        "--eval-run-dir",
        "--eval-dir",
        default=None,
        dest="run_dir",
        help=argparse.SUPPRESS,
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # 1. run 子命令：一站式全流程
    p_run = subparsers.add_parser("run", help="Run end-to-end benchmark evaluation (Ingest -> Query -> Evaluate).")
    _add_common_data_args(p_run)
    _add_common_conn_args(p_run)
    p_run_eval = p_run.add_argument_group("Metrics & LLM Options")
    p_run_eval.add_argument(
        "--metrics",
        default="f1",
        help=f"Comma-separated answer metrics ({', '.join(list_evaluators())}).",
    )
    p_run_eval.add_argument(
        "--mock-llm",
        action="store_true",
        default=False,
        help="Force using offline deterministic FakeAnswerLLMClient instead of real external LLM API.",
    )
    p_run_eval.add_argument("--confirm-api", action="store_true", default=False, help=argparse.SUPPRESS)
    _add_common_exec_args(p_run)

    # 2. ingest 子命令：仅注入记忆
    p_ingest = subparsers.add_parser("ingest", help="Stage 1 only: Ingest dialogue sessions into Memory Server.")
    _add_common_data_args(p_ingest)
    _add_common_conn_args(p_ingest)
    _add_common_exec_args(p_ingest)

    # 3. query 子命令：仅检索记忆与回答
    p_query = subparsers.add_parser("query", help="Stage 2 only: Retrieve memories and generate answers (assumes data pre-ingested).")
    _add_common_data_args(p_query)
    _add_common_conn_args(p_query)
    p_query_eval = p_query.add_argument_group("LLM Options")
    p_query_eval.add_argument(
        "--mock-llm",
        action="store_true",
        default=False,
        help="Force using offline deterministic FakeAnswerLLMClient instead of real external LLM API.",
    )
    p_query_eval.add_argument("--confirm-api", action="store_true", default=False, help=argparse.SUPPRESS)
    _add_common_exec_args(p_query)

    # 4. eval 子命令：仅离线重新评测打分
    p_eval = subparsers.add_parser("eval", help="Stage 3 only: Offline evaluate an existing run directory without touching Memory Server.")
    p_eval.add_argument(
        "--run-dir",
        "--eval-run-dir",
        "--eval-dir",
        required=True,
        dest="run_dir",
        help="Path to an existing experiment output directory containing method_predictions.jsonl.",
    )
    p_eval.add_argument(
        "-b",
        "--benchmark",
        default="locomo",
        choices=list_benchmarks(),
        help="Benchmark dataset matching the predictions.",
    )
    p_eval.add_argument(
        "--metrics",
        default="f1",
        help=f"Comma-separated answer metrics ({', '.join(list_evaluators())}).",
    )
    p_eval.add_argument(
        "-w",
        "--max-workers",
        type=int,
        default=1,
        help="Max worker threads for concurrent judge evaluation.",
    )
    p_eval.add_argument(
        "--project-root",
        default=".",
        help="Path to project root directory.",
    )

    parser.set_defaults(subcommand="run")
    return parser


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并调度执行对应的阶段流水线。"""
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # 兼容处理 1：如果包含 --eval-run-dir 或 --eval-dir 且未传子命令，自动转为 eval 子命令
    if raw_args and any(arg.startswith(("--eval-run-dir", "--eval-dir", "--run-dir")) for arg in raw_args):
        if raw_args[0] != "eval":
            raw_args = ["eval"] + [a for a in raw_args if a != "eval"]

    # 兼容处理 2：如果第一个参数不是子命令也不是帮助选项，自动缺省为 run 子命令
    elif raw_args and raw_args[0] not in {"run", "ingest", "query", "eval", "-h", "--help"}:
        raw_args = ["run"] + raw_args
    elif not raw_args:
        raw_args = ["run"]

    parser = _build_parser()
    args = parser.parse_args(raw_args)

    try:
        app_cfg = load_app_config(args.project_root)

        # ----------------------------------------------------------------------
        # 分支 1: eval 离线重打分阶段
        # ----------------------------------------------------------------------
        if args.subcommand == "eval":
            run_dir = Path(args.run_dir)
            if not run_dir.is_dir():
                run_dir = Path(app_cfg.outputs_root) / args.run_dir
            if not run_dir.is_dir():
                raise ConfigurationError(f"Evaluation run directory not found: {args.run_dir}")

            prof = app_cfg.profile(args.benchmark)
            metrics = [m.strip() for m in str(args.metrics).split(",") if m.strip()]
            eval_summaries = [
                asdict(
                    run_artifact_evaluation(
                        run_dir=run_dir,
                        evaluator=create_evaluator(
                            m,
                            benchmark_name=args.benchmark,
                            llm_props=prof.judge_llm,
                            prompt_props=prof.prompts,
                        ),
                        expected_benchmark=args.benchmark,
                        max_workers=max(1, args.max_workers),
                    )
                )
                for m in metrics
            ]
            print(
                json.dumps(
                    {"evaluations": eval_summaries},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return 0

        # ----------------------------------------------------------------------
        # 分支 2: run / ingest / query 阶段
        # ----------------------------------------------------------------------
        # 加载与裁剪数据集
        smoke_enabled = bool(getattr(args, "smoke", False))
        max_convs = getattr(args, "max_conversations", None)
        max_qs = getattr(args, "max_questions", None)
        max_sess = getattr(args, "max_sessions", None)
        max_t = getattr(args, "max_turns", None)

        adapter = get_adapter(args.benchmark, app_cfg.project_root)
        limit_load = 1 if smoke_enabled else max_convs
        dataset = _slice_dataset(
            adapter.load(limit=limit_load),
            smoke=smoke_enabled,
            max_conversations=max_convs,
            max_questions=max_qs,
            max_sessions=max_sess,
            max_turns_per_session=max_t,
        )

        # 连接被测记忆系统
        provider_cfg: dict[str, Any] = {}
        if args.server_url:
            provider_cfg["base_url"] = args.server_url
        provider = create_provider(args.method, config=provider_cfg)

        prof = app_cfg.profile(args.benchmark)

        # 构造 Answer Reader (仅 run 和 query 需要)
        reader: FrameworkAnswerReader | None = None
        if args.subcommand in {"run", "query"}:
            use_fake_llm = bool(getattr(args, "mock_llm", False))
            if not use_fake_llm:
                if args.method == "mock" and not getattr(args, "confirm_api", False):
                    use_fake_llm = True
                elif not prof.answer_llm.api_key.strip():
                    raise ConfigurationError(
                        "Missing LLM API key for Answer generation. Please set API_KEY in .env or run with --mock-llm."
                    )

            if use_fake_llm:
                reader = FrameworkAnswerReader(
                    client=FakeAnswerLLMClient("mock answer"),
                    prompts=prof.prompts,
                )
            else:
                reader = FrameworkAnswerReader(
                    client=OpenAICompatibleAnswerLLMClient(prof.answer_llm),
                    prompts=prof.prompts,
                )

        run_id = args.run_id or f"{args.benchmark}_{args.method}"
        run_ctx = RunContext.create(
            run_id=run_id,
            benchmark_name=args.benchmark,
            method_name=args.method,
            model_name=reader.client.model_name if reader else "none",
            output_root=app_cfg.outputs_root,
        )

        # 控制 Ingest 与 Retrieve 的执行边界
        is_ingest_only = (args.subcommand == "ingest")
        is_query_only = (args.subcommand == "query")
        skip_ingest = is_query_only or bool(getattr(args, "skip_ingest", False))
        skip_retrieval = is_ingest_only

        policy = PredictionRunPolicy(
            max_workers=max(1, args.max_workers),
            top_k=int(getattr(args, "top_k", 10)),
            skip_ingest=skip_ingest,
            skip_retrieval=skip_retrieval,
            isolation_prefix=getattr(args, "reuse_ingest_run_id", None),
        )

        pred_summary = run_predictions(
            dataset,
            provider,
            run_ctx,
            policy=policy,
            answer_reader=reader,
            top_k=policy.top_k,
        )

        # ingest 子命令直接打印写入报告
        if args.subcommand == "ingest":
            print(
                json.dumps(
                    {
                        "ingest_summary": {
                            "run_id": pred_summary.run_id,
                            "dataset_name": pred_summary.dataset_name,
                            "total_conversations": pred_summary.total_conversations,
                            "completed_conversations": pred_summary.completed_conversations,
                            "efficiency_metrics": asdict(pred_summary.efficiency_metrics) if hasattr(pred_summary.efficiency_metrics, "__dataclass_fields__") else pred_summary.efficiency_metrics,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return 0

        # query 子命令打印检索与回答生成报告
        if args.subcommand == "query":
            print(
                json.dumps(
                    {"prediction": asdict(pred_summary)},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
            return 0

        # run 子命令继续执行在线评估打分
        metrics = [m.strip() for m in str(args.metrics).split(",") if m.strip()]
        eval_summaries = [
            asdict(
                run_artifact_evaluation(
                    run_dir=run_ctx.run_dir,
                    evaluator=create_evaluator(
                        m,
                        benchmark_name=args.benchmark,
                        llm_props=prof.judge_llm,
                        prompt_props=prof.prompts,
                    ),
                    expected_benchmark=args.benchmark,
                    max_workers=max(1, args.max_workers),
                )
            )
            for m in metrics
        ]
        print(
            json.dumps(
                {"prediction": asdict(pred_summary), "evaluations": eval_summaries},
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return 0

    except KeyboardInterrupt:
        print("\nAborted by user.")
        return 130
    except MemoryBenchmarkError as exc:
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

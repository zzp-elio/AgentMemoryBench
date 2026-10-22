"""AgentMemoryBench 极简命令行入口 (`python -m memory_benchmark` / `memory-benchmark`)。

基于仿 Spring Boot 的 `configs/application.yaml` 自动配置注入，一键驱动：
加载数据集 (Adapter) -> 写入与检索记忆 (MemoryProvider) -> 生成回答 (Reader) -> 质量与效率评测 (Evaluator)。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from memory_benchmark.benchmark_adapters import get_adapter, list_benchmarks
from memory_benchmark.core import (
    ConfigurationError,
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
    max_conversations: int | None = None,
    max_questions: int | None = None,
    max_sessions: int | None = None,
    max_turns_per_session: int | None = None,
) -> Dataset:
    """按对话数、单段对话 Session 数、单 Session Turn 数与问题数轻量裁剪数据集（用于快速冒烟验证）。"""
    convs: list[Conversation] = []
    base_convs = list(dataset.conversations)
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory-benchmark",
        description="Standardized C/S evaluation middleware for AI Agent long-term memory systems.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # 1. 基准与数据抽样控制
    g_data = parser.add_argument_group("Benchmark & Data Sampling Options")
    g_data.add_argument(
        "-b",
        "--benchmark",
        default="locomo",
        choices=list_benchmarks(),
        help="Target benchmark dataset.",
    )
    g_data.add_argument(
        "-c",
        "--max-conversations",
        type=int,
        default=None,
        help="Maximum conversations to evaluate (default: None, evaluates all conversations).",
    )
    g_data.add_argument(
        "-q",
        "--max-questions",
        "--max-questions-per-conversation",
        type=int,
        default=None,
        dest="max_questions_per_conversation",
        help="Maximum questions per conversation to evaluate (default: all questions).",
    )
    g_data.add_argument(
        "--project-root",
        default=".",
        help="Path to project root directory.",
    )
    # 隐藏的微调内部参数（保持向后兼容，不干扰普通开源用户）
    g_data.add_argument("--max-sessions", "--max-sessions-per-conversation", type=int, default=None, dest="max_sessions", help=argparse.SUPPRESS)
    g_data.add_argument("--max-turns", "--max-turns-per-session", type=int, default=None, dest="max_turns", help=argparse.SUPPRESS)

    # 2. 被测记忆系统连接配置
    g_conn = parser.add_argument_group("Memory Server Connection Options")
    g_conn.add_argument(
        "-m",
        "--method",
        default="mock",
        choices=list_methods(),
        help="Memory provider mode: 'http' for remote memory server, 'mock' for offline smoke test.",
    )
    g_conn.add_argument(
        "-u",
        "--server-url",
        default=None,
        help="Base URL of remote Memory Server when --method=http (e.g. http://127.0.0.1:8002).",
    )
    # 隐藏的底层专家选项（默认 top_k=10，完整两阶段评测无需手动干预）
    g_conn.add_argument("-k", "--top-k", type=int, default=10, help=argparse.SUPPRESS)
    g_conn.add_argument("--skip-ingest", action="store_true", default=False, help=argparse.SUPPRESS)
    g_conn.add_argument("--reuse-ingest-run-id", "--isolation-prefix", default=None, dest="reuse_ingest_run_id", help=argparse.SUPPRESS)

    # 3. 评测指标与模型控制
    g_eval = parser.add_argument_group("Metrics & LLM Execution Options")
    g_eval.add_argument(
        "--metrics",
        default="f1",
        help=f"Comma-separated answer metrics ({', '.join(list_evaluators())}).",
    )
    g_eval.add_argument(
        "--mock-llm",
        action="store_true",
        default=False,
        help="Force using offline deterministic FakeAnswerLLMClient instead of real external LLM API.",
    )
    g_eval.add_argument(
        "--confirm-api",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,  # 隐蔽废弃参数，保持向后兼容
    )

    # 4. 并发与执行管理
    g_exec = parser.add_argument_group("Concurrency & Execution Options")
    g_exec.add_argument(
        "-w",
        "--max-workers",
        type=int,
        default=1,
        help="Max worker threads for concurrent conversation evaluation.",
    )
    g_exec.add_argument(
        "--run-id",
        default=None,
        help="Explicit experiment run_id identifier.",
    )

    # 5. 高级解耦模式与 Coordinator 微服务
    g_adv = parser.add_argument_group("Advanced & Service Mode Options")
    g_adv.add_argument(
        "--eval-run-dir",
        "--eval-dir",
        default=None,
        dest="eval_run_dir",
        help="Directly evaluate an existing experiment run directory without re-running predictions.",
    )
    g_adv.add_argument(
        "--server",
        action="store_true",
        help="Run AgentMemoryBench as Coordinator HTTP Server listening for /ready requests.",
    )
    g_adv.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind Coordinator Server.",
    )
    g_adv.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind Coordinator Server.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """解析命令行参数并执行端到端预测与评测流水线。"""
    args = _build_parser().parse_args(argv)
    try:
        app_cfg = load_app_config(args.project_root)
        if args.server:
            from memory_benchmark.coordinator import CoordinatorContext, CoordinatorServer

            ctx = CoordinatorContext(app_config=app_cfg)
            server = CoordinatorServer(ctx, host=args.host, port=args.port)
            print(f"AgentMemoryBench Coordinator Server running on {server.base_url}")
            try:
                server.start(threaded=False)
            except KeyboardInterrupt:
                print("\nShutting down Coordinator Server...")
                server.stop()
            return 0

        if args.eval_run_dir:
            run_dir = Path(args.eval_run_dir)
            if not run_dir.is_dir():
                run_dir = Path(app_cfg.outputs_root) / args.eval_run_dir
            if not run_dir.is_dir():
                raise ConfigurationError(f"evaluation run directory not found: {args.eval_run_dir}")
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

        dataset = _slice_dataset(
            get_adapter(args.benchmark, app_cfg.project_root).load(limit=args.max_conversations),
            max_conversations=args.max_conversations,
            max_questions=args.max_questions_per_conversation,
            max_sessions=args.max_sessions,
            max_turns_per_session=args.max_turns,
        )

        provider_cfg: dict[str, Any] = {}
        if args.server_url:
            provider_cfg["base_url"] = args.server_url
        provider = create_provider(args.method, config=provider_cfg)

        prof = app_cfg.profile(args.benchmark)
        # 1. 显式指定 --mock-llm 时，强制使用 Fake 客户端
        # 2. 当 --method=mock 时，除非显式指定了 --confirm-api，否则默认使用 Fake 客户端，杜绝离线测试意外消耗真实 API Token
        # 3. 当 --method=http 时，默认必须使用真实 LLM 客户端
        if args.mock_llm:
            use_fake_llm = True
        elif args.method == "mock" and not args.confirm_api:
            use_fake_llm = True
        else:
            use_fake_llm = False

        if use_fake_llm:
            reader = FrameworkAnswerReader(
                client=FakeAnswerLLMClient("mock answer"),
                prompts=prof.prompts,
            )
        else:
            if not prof.answer_llm.api_key.strip():
                raise ConfigurationError(
                    "Missing LLM API key for Answer generation. Please set API_KEY in .env or run with --mock-llm."
                )
            reader = FrameworkAnswerReader(
                client=OpenAICompatibleAnswerLLMClient(prof.answer_llm),
                prompts=prof.prompts,
            )

        run_id = args.run_id or f"{args.benchmark}_{args.method}"
        run_ctx = RunContext.create(
            run_id=run_id,
            benchmark_name=args.benchmark,
            method_name=args.method,
            model_name=reader.client.model_name,
            output_root=app_cfg.outputs_root,
        )
        policy = PredictionRunPolicy(
            max_workers=max(1, args.max_workers),
            top_k=args.top_k,
            skip_ingest=args.skip_ingest,
            isolation_prefix=args.reuse_ingest_run_id,
        )
        pred_summary = run_predictions(
            dataset,
            provider,
            run_ctx,
            policy=policy,
            answer_reader=reader,
            top_k=args.top_k,
        )

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

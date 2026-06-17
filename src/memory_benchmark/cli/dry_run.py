"""loader-only dry-run 命令。

本模块用于验证 adapter 能读取数据并产出 public Dataset 摘要。它不调用外部
LLM API，不调用原 benchmark eval 脚本，也不计算 metric。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from memory_benchmark.benchmark_adapters import get_adapter, list_benchmarks
from memory_benchmark.core import DryRunSummary


def run_dry_run(
    project_root: str | Path,
    benchmark: str = "all",
    limit: int | None = 1,
) -> list[DryRunSummary]:
    """运行 loader-only dry-run。

    输入:
        project_root: 项目根目录，必须包含 canonical `data/`。
        benchmark: benchmark 名称；传 `all` 时遍历 registry 中全部 benchmark。
        limit: 每个 benchmark 最多读取的 case 数。

    输出:
        list[DryRunSummary]: 每个 benchmark 的 conversation/session/turn/question 计数摘要。
    """

    benchmark_names = list_benchmarks() if benchmark == "all" else [benchmark]
    summaries = []
    for benchmark_name in benchmark_names:
        adapter = get_adapter(benchmark_name, project_root)
        dataset = adapter.load(limit=limit)
        conversations = dataset.conversations
        summaries.append(
            DryRunSummary(
                benchmark=benchmark_name,
                conversation_count=len(conversations),
                sample_conversation_ids=[
                    conversation.conversation_id for conversation in conversations[:3]
                ],
                total_sessions=sum(len(conversation.sessions) for conversation in conversations),
                total_turns=sum(
                    len(session.turns)
                    for conversation in conversations
                    for session in conversation.sessions
                ),
                total_questions=sum(len(conversation.questions) for conversation in conversations),
            )
        )
    return summaries


def main(argv: list[str] | None = None) -> int:
    """CLI 入口函数。

    输入:
        argv: 可选命令行参数列表；None 表示使用真实命令行参数。

    输出:
        int: 进程退出码，0 表示正常完成。
    """

    parser = argparse.ArgumentParser(description="Run loader-only benchmark dry-runs.")
    parser.add_argument(
        "--root",
        default=".",
        help="Project root containing canonical data/",
    )
    parser.add_argument("--benchmark", default="all", help="Benchmark name or 'all'")
    parser.add_argument("--limit", type=int, default=1, help="Cases per benchmark")
    args = parser.parse_args(argv)

    summaries = run_dry_run(args.root, benchmark=args.benchmark, limit=args.limit)
    print(json.dumps([summary.to_dict() for summary in summaries], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

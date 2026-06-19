"""calibrate-smoke 并行模式下的统一进度监控。

本模块在 calibrate-smoke 以 max_parallel_runs > 1 运行时，禁用各 child run 的
Rich Live progress，改由外层 orchestrator 主线程定时读取各 run 的
checkpoints/progress.json，并渲染一张 Rich Live(Table)。
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.table import Table


class CalibrationProgressMonitor:
    """统一监控多个并行 child run 的进度。

    参数:
        output_root: 包含所有 child run 目录的 outputs 根目录。
        run_ids: 各 child run 的 run_id 列表。
        methods: 对应的 method 名称列表（与 run_ids 对齐）。
        benchmarks: 对应的 benchmark 名称列表（与 run_ids 对齐）。
        refresh_per_second: Rich Live 刷新频率。
        console: 可选 Rich Console。
        clock: 可注入单调时钟（测试用）。
    """

    def __init__(
        self,
        output_root: str | Path,
        run_ids: tuple[str, ...],
        methods: tuple[str, ...],
        benchmarks: tuple[str, ...],
        refresh_per_second: float = 10.0,
        console: Console | None = None,
        clock: Any | None = None,
    ):
        """初始化监控器，保存参数但不立即创建 Live。"""

        self._output_root = Path(output_root)
        self._run_ids = run_ids
        self._methods = methods
        self._benchmarks = benchmarks
        if len(run_ids) != len(methods) or len(run_ids) != len(benchmarks):
            raise ValueError(
                "run_ids, methods and benchmarks must have the same length"
            )
        self._clock = clock or time.monotonic
        self._started_at: dict[str, float] = {}
        self._task_to_index: dict[str, int] = {
            run_id: idx for idx, run_id in enumerate(run_ids)
        }
        self._live: Live | None = None
        self._console = console or Console()
        self._refresh_per_second = refresh_per_second

    def start(self) -> None:
        """创建并启动 Rich Live 上下文。

        必须在 child run 提交后调用，调用方负责 __exit__。
        """

        table = self._build_snapshot_table()
        self._live = Live(
            table,
            console=self._console,
            refresh_per_second=self._refresh_per_second,
        )
        self._live.start()

    def stop(self) -> None:
        """停止 Rich Live 并渲染最终表格。"""

        if self._live is not None:
            try:
                final_table = self._build_snapshot_table()
                self._live.update(final_table)
                self._live.refresh()
            finally:
                self._live.stop()
                self._live = None

    def start_task(self, run_id: str) -> None:
        """记录 child run 开始时间。"""

        if run_id not in self._started_at:
            self._started_at[run_id] = self._clock()

    def mark_completed(self, run_id: str) -> None:
        """标记任务完成并刷新表格。"""

        self._refresh_table()

    def mark_failed(self, run_id: str, error: str) -> None:
        """标记任务失败并刷新表格。"""

        self._refresh_table()

    def _refresh_table(self) -> None:
        """读取所有 progress.json 并更新 Live 表格。"""

        if self._live is None:
            return
        table = self._build_snapshot_table()
        self._live.update(table, refresh=True)

    def _build_snapshot_table(self) -> Table:
        """根据当前 progress.json 和状态构建 Rich Table。"""

        table = Table(title="calibrate-smoke")
        table.add_column("Method", style="cyan", width=9, no_wrap=True)
        table.add_column("Bench", style="magenta", width=11)
        table.add_column("Status", width=11)
        table.add_column("Stage", width=22)
        table.add_column("Conv", justify="right", width=5)
        table.add_column("Q", justify="right", width=5)
        table.add_column("Elapsed", justify="right", width=7)
        table.add_column("Run ID", width=36)
        table.add_column("Error", style="red", width=20)

        for idx, run_id in enumerate(self._run_ids):
            method = self._methods[idx]
            benchmark = self._benchmarks[idx]
            progress = self._read_progress(run_id)
            elapsed = self._format_elapsed(run_id)
            status = self._derive_status(progress)
            stage = progress.get("stage") or "—"
            conv_completed = progress.get("conversation_completed", 0)
            conv_total = progress.get("conversation_total", 0)
            q_completed = progress.get("question_completed", 0)
            q_total = progress.get("question_total", 0)
            error_text = ""

            status_style: str = ""
            if status == "completed":
                status_style = "green"
            elif status == "failed":
                status_style = "red"
            elif status == "running":
                status_style = "yellow"

            status_cell = (
                f"[{status_style}]{status}[/{status_style}]"
                if status_style
                else status
            )

            table.add_row(
                method,
                benchmark,
                status_cell,
                stage,
                f"{conv_completed}/{conv_total}" if conv_total else "—",
                f"{q_completed}/{q_total}" if q_total else "—",
                elapsed,
                run_id,
                error_text,
            )
        return table

    def _read_progress(self, run_id: str) -> dict[str, Any]:
        """读取单个 child run 的 progress.json；文件不存在时返回空 dict。"""

        progress_path = (
            self._output_root / run_id / "checkpoints" / "progress.json"
        )
        try:
            raw = progress_path.read_text(encoding="utf-8")
            return json.loads(raw)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _derive_status(self, progress: dict[str, Any]) -> str:
        """根据 progress.json 内容推导运行状态。

        规则: 如果 stage 为 'Completed' 且 question 全完成，视为 completed；
        如果有 stage 但未全完成，视为 running；无 stage 视为 pending。
        """

        stage = progress.get("stage")
        if stage == "Completed":
            q_completed = progress.get("question_completed", 0)
            q_total = progress.get("question_total", 0)
            if q_total > 0 and q_completed >= q_total:
                return "completed"
        if stage:
            return "running"
        return "pending"

    def _format_elapsed(self, run_id: str) -> str:
        """格式化 child run 的已运行时间。"""

        started = self._started_at.get(run_id)
        if started is None:
            return "—"
        elapsed_seconds = int(self._clock() - started)
        minutes = elapsed_seconds // 60
        seconds = elapsed_seconds % 60
        return f"{minutes:02d}:{seconds:02d}"


__all__ = ["CalibrationProgressMonitor"]

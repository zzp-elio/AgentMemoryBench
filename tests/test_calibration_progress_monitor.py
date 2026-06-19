"""测试 calibrate-smoke 统一进度监控（CalibrationProgressMonitor）。

这些测试全部离线，使用临时 progress.json 文件验证 Rich Table 的渲染内容。
不调用真实 API。
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from memory_benchmark.runners.calibration_progress import (
    CalibrationProgressMonitor,
)
from rich.console import Console


pytestmark = pytest.mark.unit


def _render_table(table) -> str:
    """把 Rich Table 渲染为纯文本字符串。"""

    buf = io.StringIO()
    # 进度表包含 9 列，测试必须给足宽度。当前 Rich 在 force_terminal=True
    # 时会回退到 80 列，因此这里渲染为普通文本，保证断言稳定。
    console = Console(file=buf, width=260, force_terminal=False)
    console.print(table)
    return buf.getvalue()


def _write_progress(
    output_root: Path,
    run_id: str,
    stage: str | None = None,
    step_index: int = 0,
    step_count: int = 0,
    conversation_completed: int = 0,
    conversation_total: int = 0,
    question_completed: int = 0,
    question_total: int = 0,
) -> None:
    """写入一个最小的 progress.json 到 child run 的 checkpoints 目录。"""

    checkpoints_dir = output_root / run_id / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    progress = {
        "stage": stage,
        "step_index": step_index,
        "step_count": step_count,
        "conversation_completed": conversation_completed,
        "conversation_total": conversation_total,
        "question_completed": question_completed,
        "question_total": question_total,
        "current_conversation_id": None,
        "current_question_id": None,
    }
    (checkpoints_dir / "progress.json").write_text(
        json.dumps(progress, indent=2),
        encoding="utf-8",
    )


class _FakeClock:
    """单调递增的假时钟，每次调用 +1 秒。"""

    def __init__(self, start: float = 0.0) -> None:
        """保存起始时间。"""

        self._now = start

    def __call__(self) -> float:
        """返回当前模拟时间并自增。"""

        self._now += 1.0
        return self._now


def test_monitor_builds_table_with_pending_runs(
    tmp_path: Path,
) -> None:
    """无 progress.json 时各 run 显示为 pending。"""

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    monitor = CalibrationProgressMonitor(
        output_root=outputs,
        run_ids=("run-a", "run-b"),
        methods=("mem0", "memoryos"),
        benchmarks=("locomo", "locomo"),
    )
    table = monitor._build_snapshot_table()
    rendered = _render_table(table)

    assert "mem0" in rendered
    assert "memoryos" in rendered
    assert "locomo" in rendered
    assert "pending" in rendered


def test_monitor_detects_running_when_progress_has_stage(
    tmp_path: Path,
) -> None:
    """progress.json 有 stage 且未完成时，状态应为 running。"""

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _write_progress(
        outputs,
        "run-a",
        stage="Ingest conversations",
        conversation_total=1,
        question_total=1,
    )
    _write_progress(
        outputs,
        "run-b",
        stage="Answer questions",
        conversation_completed=1,
        conversation_total=1,
        question_completed=0,
        question_total=1,
    )

    monitor = CalibrationProgressMonitor(
        output_root=outputs,
        run_ids=("run-a", "run-b"),
        methods=("mem0", "amem"),
        benchmarks=("locomo", "locomo"),
    )
    table = monitor._build_snapshot_table()
    rendered = _render_table(table)

    assert "Ingest conversations" in rendered
    assert "Answer questions" in rendered
    assert "running" in rendered


def test_monitor_detects_completed_when_stage_is_completed(
    tmp_path: Path,
) -> None:
    """progress.json stage 为 'Completed' 且 question 全完成时，状态为 completed。"""

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _write_progress(
        outputs,
        "run-a",
        stage="Completed",
        conversation_completed=1,
        conversation_total=1,
        question_completed=1,
        question_total=1,
    )

    monitor = CalibrationProgressMonitor(
        output_root=outputs,
        run_ids=("run-a",),
        methods=("mem0",),
        benchmarks=("locomo",),
    )
    table = monitor._build_snapshot_table()
    rendered = _render_table(table)

    assert "completed" in rendered
    assert "1/1" in rendered


def test_monitor_formats_elapsed_from_task_start(
    tmp_path: Path,
) -> None:
    """start_task 记录开始时间后，elapsed 应从该时间点算起。"""

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _write_progress(
        outputs,
        "run-a",
        stage="Ingest conversations",
        conversation_total=1,
        question_total=1,
    )
    clock = _FakeClock()
    monitor = CalibrationProgressMonitor(
        output_root=outputs,
        run_ids=("run-a",),
        methods=("mem0",),
        benchmarks=("locomo",),
        clock=clock,
    )
    monitor.start_task("run-a")
    # 经过模拟时间
    table = monitor._build_snapshot_table()
    rendered = _render_table(table)

    assert "00:01" in rendered


def test_monitor_rejects_mismatched_lengths() -> None:
    """run_ids、methods、benchmarks 长度不一致时应报错。"""

    with pytest.raises(ValueError, match="same length"):
        CalibrationProgressMonitor(
            output_root=Path("/tmp"),
            run_ids=("a", "b"),
            methods=("mem0",),
            benchmarks=("locomo",),
        )


def test_monitor_reads_progress_inside_subdirectories(
    tmp_path: Path,
) -> None:
    """monitor 从 outputs/<run_id>/checkpoints/progress.json 读取进度。"""

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _write_progress(
        outputs,
        "calib-mem0-locomo",
        stage="Answer questions",
        conversation_completed=1,
        conversation_total=1,
        question_completed=0,
        question_total=1,
    )

    monitor = CalibrationProgressMonitor(
        output_root=outputs,
        run_ids=("calib-mem0-locomo",),
        methods=("mem0",),
        benchmarks=("locomo",),
    )
    progress = monitor._read_progress("calib-mem0-locomo")
    assert progress["stage"] == "Answer questions"
    assert progress["conversation_completed"] == 1
    assert progress["question_total"] == 1


def test_monitor_handles_missing_progress_file(
    tmp_path: Path,
) -> None:
    """progress.json 不存在时返回空 dict，不抛异常。"""

    outputs = tmp_path / "outputs"
    outputs.mkdir()

    monitor = CalibrationProgressMonitor(
        output_root=outputs,
        run_ids=("nonexistent-run",),
        methods=("mem0",),
        benchmarks=("locomo",),
    )
    progress = monitor._read_progress("nonexistent-run")
    assert progress == {}


def test_monitor_start_and_stop_lifecycle(
    tmp_path: Path,
) -> None:
    """monitor 的 start/stop 生命周期不抛异常。"""

    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _write_progress(
        outputs,
        "run-a",
        stage="Completed",
        conversation_completed=1,
        conversation_total=1,
        question_completed=1,
        question_total=1,
    )

    monitor = CalibrationProgressMonitor(
        output_root=outputs,
        run_ids=("run-a",),
        methods=("mem0",),
        benchmarks=("locomo",),
    )
    monitor.start()
    monitor.start_task("run-a")
    monitor.mark_completed("run-a")
    monitor.stop()
    assert monitor._live is None

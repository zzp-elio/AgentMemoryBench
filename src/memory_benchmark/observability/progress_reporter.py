"""Rich 进度条和 progress.json 快照写入。

本模块为长时间 benchmark run 提供终端进度展示和可恢复检查的轻量快照文件。
progress.json 只保存公开运行进度，不包含 gold answer、secret 或 method 私有状态。
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)


class ProgressReporter:
    """封装 Rich Progress，并同步写入最新进度快照。

    参数:
        progress_path: progress.json 文件路径；构造时会自动创建父目录。
        console: 可选 Rich Console，便于测试或复用外部终端配置。
        enabled: 是否启用终端进度条；关闭时仍会写 progress.json。
        snapshot_interval: 普通进度更新的最小持久化间隔，单位秒。
        clock: 可注入的单调时钟，主要用于确定性测试。
    """

    def __init__(
        self,
        progress_path: str | Path,
        console: Console | None = None,
        enabled: bool = True,
        snapshot_interval: float = 1.0,
        clock: Callable[[], float] | None = None,
    ):
        """初始化进度条和默认快照。

        输入:
            progress_path: 字符串或 Path，指向要覆盖写入的 progress.json。
            console: 可选 Rich Console。
            enabled: False 时禁用终端渲染，但保留文件快照。
            snapshot_interval: 高频更新之间的最小落盘间隔。
            clock: 返回单调时间秒数的可调用对象。

        输出:
            None；调用后父目录存在，内部快照字段完整。
        """

        self.progress_path = Path(progress_path)
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        if snapshot_interval < 0:
            raise ValueError("snapshot_interval must be non-negative")
        self.snapshot_interval = snapshot_interval
        self._clock = clock or time.monotonic
        self._last_snapshot_at: float | None = None
        self.snapshot: dict[str, Any] = {
            "stage": None,
            "step_index": 0,
            "step_count": 0,
            "conversation_completed": 0,
            "conversation_total": 0,
            "question_completed": 0,
            "question_total": 0,
            "current_conversation_id": None,
            "current_question_id": None,
        }
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
            disable=not enabled,
        )
        self._stage_task_id: TaskID | None = None
        self._conversation_task_id: TaskID | None = None
        self._question_task_id: TaskID | None = None

    def __enter__(self) -> "ProgressReporter":
        """启动 Rich 进度条上下文。

        输出:
            ProgressReporter: 当前对象，供 `with` 语句内继续更新阶段和任务。
        """

        self.progress.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """退出上下文时写入最终快照并停止进度条。

        输入:
            exc_type、exc_value、traceback: Python 上下文管理器异常信息。

        输出:
            None；异常不在这里吞掉。
        """

        try:
            self._write_snapshot()
        finally:
            self.progress.stop()

    def set_stage(self, stage: str, step_index: int, step_count: int) -> None:
        """更新当前运行阶段并写入 progress.json。

        输入:
            stage: 当前阶段名称。
            step_index: 当前阶段序号。
            step_count: 总阶段数。

        输出:
            None；快照会被覆盖写入。
        """

        self.snapshot["stage"] = stage
        self.snapshot["step_index"] = step_index
        self.snapshot["step_count"] = step_count
        description = f"Stage [{step_index}/{step_count}] {stage}"
        if self._stage_task_id is None:
            self._stage_task_id = self.progress.add_task(
                description,
                total=step_count,
                completed=step_index,
            )
        else:
            self.progress.update(
                self._stage_task_id,
                description=description,
                completed=step_index,
                total=step_count,
            )
        self._persist_snapshot(force=True)

    def start_conversations(self, total: int) -> None:
        """创建 conversation 进度任务并记录总数。

        输入:
            total: 本次 run 需要处理的 conversation 总数。

        输出:
            None；Rich task 和快照都会更新。
        """

        self.snapshot["conversation_completed"] = 0
        self.snapshot["conversation_total"] = total
        self._conversation_task_id = self.progress.add_task(
            "Conversations",
            total=total,
            completed=0,
        )
        self._persist_snapshot(force=True)

    def update_conversations(
        self,
        completed: int,
        total: int,
        current_conversation_id: str | None,
    ) -> None:
        """更新 conversation 进度并写入快照。

        输入:
            completed: 已完成 conversation 数。
            total: conversation 总数。
            current_conversation_id: 当前处理的 conversation id，可为空。

        输出:
            None；存在 Rich task 时同步刷新终端进度。
        """

        self.snapshot["conversation_completed"] = completed
        self.snapshot["conversation_total"] = total
        self.snapshot["current_conversation_id"] = current_conversation_id
        if self._conversation_task_id is not None:
            description = "Conversations"
            if current_conversation_id is not None:
                description += f" | current={current_conversation_id}"
            self.progress.update(
                self._conversation_task_id,
                description=description,
                completed=completed,
                total=total,
            )
        self._persist_snapshot()

    def start_questions(self, total: int) -> None:
        """创建 question 进度任务并记录总数。

        输入:
            total: 本次 run 需要回答的问题总数。

        输出:
            None；Rich task 和快照都会更新。
        """

        self.snapshot["question_completed"] = 0
        self.snapshot["question_total"] = total
        self._question_task_id = self.progress.add_task(
            "Questions",
            total=total,
            completed=0,
        )
        self._persist_snapshot(force=True)

    def update_questions(
        self,
        completed: int,
        total: int,
        current_conversation_id: str | None,
        current_question_id: str | None,
    ) -> None:
        """更新 question 进度并写入快照。

        输入:
            completed: 已完成 question 数。
            total: question 总数。
            current_conversation_id: 当前问题所属 conversation id，可为空。
            current_question_id: 当前 question id，可为空。

        输出:
            None；存在 Rich task 时同步刷新终端进度。
        """

        self.snapshot["question_completed"] = completed
        self.snapshot["question_total"] = total
        self.snapshot["current_conversation_id"] = current_conversation_id
        self.snapshot["current_question_id"] = current_question_id
        if self._question_task_id is not None:
            description = "Questions"
            if current_conversation_id is not None:
                description += f" | conversation={current_conversation_id}"
            if current_question_id is not None:
                description += f" | current={current_question_id}"
            self.progress.update(
                self._question_task_id,
                description=description,
                completed=completed,
                total=total,
            )
        self._persist_snapshot()

    def flush(self) -> None:
        """立即持久化当前内存快照。

        输出:
            None；忽略节流间隔，适合显式最终状态或关键边界。
        """

        self._persist_snapshot(force=True)

    def _persist_snapshot(self, force: bool = False) -> None:
        """按节流策略持久化快照。

        输入:
            force: True 时忽略间隔立即写入。

        输出:
            None；被合并的更新仍保留在内存快照中。
        """

        now = self._clock()
        if (
            not force
            and self._last_snapshot_at is not None
            and now - self._last_snapshot_at < self.snapshot_interval
        ):
            return
        self._write_snapshot()
        self._last_snapshot_at = now

    def _write_snapshot(self) -> None:
        """原子覆盖写入最新 progress.json。

        输出:
            None；文件内容为缩进 JSON，保留中文字符。
        """

        snapshot_json = json.dumps(self.snapshot, ensure_ascii=False, indent=2)
        temporary_path: Path | None = None
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.progress_path.parent,
            prefix=f".{self.progress_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(snapshot_json)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)

        try:
            os.replace(temporary_path, self.progress_path)
            temporary_path = None
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

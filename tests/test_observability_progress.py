"""测试 Rich 进度条封装。"""

from __future__ import annotations

import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path

import pytest

from rich.console import Console

from memory_benchmark.observability import ProgressReporter


pytestmark = pytest.mark.integration


class ProgressReporterTests(unittest.TestCase):
    """验证 ProgressReporter 能记录阶段和 progress.json。"""

    def _read_snapshot(self, progress_path: Path) -> dict[str, object]:
        """读取 progress.json 并返回解析后的快照。

        输入:
            progress_path: progress.json 文件路径。

        输出:
            dict[str, object]: JSON 解析后的进度快照。
        """

        return json.loads(progress_path.read_text(encoding="utf-8"))

    def test_progress_reporter_writes_progress_snapshot(self):
        """更新阶段和 question 后，应写入最新 progress.json。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress.json"
            console = Console(file=None, force_terminal=False, width=100)
            reporter = ProgressReporter(
                progress_path=progress_path,
                console=console,
                enabled=False,
            )

            with reporter:
                reporter.set_stage("Answer questions", step_index=4, step_count=6)
                reporter.update_questions(
                    completed=7,
                    total=10,
                    current_conversation_id="conv-1",
                    current_question_id="conv-1:q7",
                )

            snapshot = self._read_snapshot(progress_path)

            self.assertEqual(snapshot["stage"], "Answer questions")
            self.assertEqual(snapshot["step_index"], 4)
            self.assertEqual(snapshot["question_completed"], 7)
            self.assertEqual(snapshot["question_total"], 10)
            self.assertEqual(snapshot["current_question_id"], "conv-1:q7")

    def test_progress_reporter_creates_parent_directory(self):
        """progress_path 父目录不存在时，初始化应自动创建。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "missing" / "nested" / "progress.json"

            ProgressReporter(progress_path=progress_path, enabled=False)

            self.assertTrue(progress_path.parent.exists())

    def test_conversation_progress_updates_snapshot(self):
        """conversation 任务启动和更新后，应记录最新完成数和当前 conversation。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress.json"
            reporter = ProgressReporter(progress_path=progress_path, enabled=False)

            with reporter:
                reporter.start_conversations(total=3)
                reporter.update_conversations(
                    completed=2,
                    total=3,
                    current_conversation_id="conv-2",
                )

            snapshot = self._read_snapshot(progress_path)

            self.assertEqual(snapshot["conversation_completed"], 2)
            self.assertEqual(snapshot["conversation_total"], 3)
            self.assertEqual(snapshot["current_conversation_id"], "conv-2")

    def test_repeated_question_updates_keep_latest_snapshot(self):
        """连续更新 question 进度时，progress.json 应只保留最新状态。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress.json"
            reporter = ProgressReporter(progress_path=progress_path, enabled=False)

            with reporter:
                reporter.start_questions(total=5)
                reporter.update_questions(
                    completed=1,
                    total=5,
                    current_conversation_id="conv-1",
                    current_question_id="conv-1:q1",
                )
                reporter.update_questions(
                    completed=4,
                    total=5,
                    current_conversation_id="conv-3",
                    current_question_id="conv-3:q4",
                )

            snapshot = self._read_snapshot(progress_path)

            self.assertEqual(snapshot["question_completed"], 4)
            self.assertEqual(snapshot["question_total"], 5)
            self.assertEqual(snapshot["current_conversation_id"], "conv-3")
            self.assertEqual(snapshot["current_question_id"], "conv-3:q4")

    def test_disabled_rich_progress_still_writes_snapshots(self):
        """禁用 Rich 终端渲染时，阶段和任务更新仍应写入文件。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress.json"
            reporter = ProgressReporter(progress_path=progress_path, enabled=False)

            with reporter:
                reporter.set_stage("Load dataset", step_index=1, step_count=4)
                reporter.start_conversations(total=2)
                reporter.update_conversations(
                    completed=1,
                    total=2,
                    current_conversation_id="conv-1",
                )

            snapshot = self._read_snapshot(progress_path)

            self.assertEqual(snapshot["stage"], "Load dataset")
            self.assertEqual(snapshot["step_index"], 1)
            self.assertEqual(snapshot["conversation_completed"], 1)

    def test_throttled_updates_coalesce_writes_and_exit_flushes_latest_snapshot(self):
        """高频更新应合并写入，但退出上下文必须强制保存最新状态。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress.json"
            clock_values = iter([0.0, 0.1, 0.2])
            reporter = ProgressReporter(
                progress_path=progress_path,
                enabled=False,
                snapshot_interval=1.0,
                clock=lambda: next(clock_values),
            )
            write_count = 0
            original_write_snapshot = reporter._write_snapshot

            def count_write_snapshot() -> None:
                """记录实际持久化次数后调用原始写入实现。"""

                nonlocal write_count
                write_count += 1
                original_write_snapshot()

            reporter._write_snapshot = count_write_snapshot

            with reporter:
                reporter.start_questions(total=5)
                reporter.update_questions(
                    completed=1,
                    total=5,
                    current_conversation_id="conv-1",
                    current_question_id="conv-1:q1",
                )
                reporter.update_questions(
                    completed=2,
                    total=5,
                    current_conversation_id="conv-1",
                    current_question_id="conv-1:q2",
                )

                self.assertEqual(write_count, 1)

            snapshot = self._read_snapshot(progress_path)

            self.assertEqual(write_count, 2)
            self.assertEqual(snapshot["question_completed"], 2)
            self.assertEqual(snapshot["current_question_id"], "conv-1:q2")

    def test_rich_descriptions_include_stage_and_current_ids(self):
        """Rich task 描述应展示当前阶段、conversation 和 question id。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            reporter = ProgressReporter(
                progress_path=Path(temp_dir) / "progress.json",
                console=Console(file=StringIO(), force_terminal=True, width=120),
                enabled=True,
                snapshot_interval=60.0,
                clock=lambda: 0.0,
            )

            with reporter:
                reporter.set_stage("Answer questions", step_index=4, step_count=6)
                reporter.start_conversations(total=2)
                reporter.start_questions(total=3)
                reporter.update_conversations(
                    completed=1,
                    total=2,
                    current_conversation_id="conv-a",
                )
                reporter.update_questions(
                    completed=1,
                    total=3,
                    current_conversation_id="conv-a",
                    current_question_id="conv-a:q2",
                )

                descriptions = [task.description for task in reporter.progress.tasks]

            self.assertTrue(
                any("Answer questions" in description for description in descriptions)
            )
            self.assertTrue(any("conv-a" in description for description in descriptions))
            self.assertTrue(
                any("conv-a:q2" in description for description in descriptions)
            )


if __name__ == "__main__":
    unittest.main()

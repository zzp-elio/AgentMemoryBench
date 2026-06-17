"""测试运行期日志工具的文件输出行为。"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import pytest

from memory_benchmark.utils.run_logger import RunLogger


pytestmark = pytest.mark.integration


class RunLoggerTests(unittest.TestCase):
    """验证 RunLogger 能安全写入临时运行日志目录。"""

    def test_log_event_writes_jsonl_event_and_payload(self):
        """log_event 应写入包含时间戳、事件名和 payload 的 JSONL 行。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            logger = RunLogger(Path(temp_dir))

            logger.log_event("case_started", {"case_id": "q1", "score": 0.75})

            events_path = Path(temp_dir) / "events.jsonl"
            line = events_path.read_text(encoding="utf-8").strip()
            event = json.loads(line)

            self.assertIn("timestamp", event)
            self.assertEqual(event["event"], "case_started")
            self.assertEqual(event["payload"], {"case_id": "q1", "score": 0.75})

    def test_info_writes_to_run_log(self):
        """info 应把可读消息写入 run.log。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            terminal_output = io.StringIO()

            with contextlib.redirect_stdout(terminal_output):
                logger = RunLogger(Path(temp_dir))
                logger.info("开始加载 benchmark")

            log_path = Path(temp_dir) / "run.log"
            content = log_path.read_text(encoding="utf-8")

            self.assertIn("开始加载 benchmark", content)

    def test_info_accepts_rich_markup_and_file_log_strips_markup(self):
        """info 写终端时可用 Rich markup，写 run.log 时应保持可读文本。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            terminal_output = io.StringIO()

            with contextlib.redirect_stdout(terminal_output):
                logger = RunLogger(Path(temp_dir))
                logger.info("[bold]Memory Benchmark Run[/bold]")

            log_path = Path(temp_dir) / "run.log"
            content = log_path.read_text(encoding="utf-8")

            self.assertIn("Memory Benchmark Run", content)
            self.assertNotIn("[bold]", content)

    def test_info_handles_malformed_rich_markup_without_aborting_run(self):
        """info 遇到错误 Rich markup 时不应中断运行，并应把原文写入 run.log。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            terminal_output = io.StringIO()

            with contextlib.redirect_stdout(terminal_output):
                logger = RunLogger(Path(temp_dir))
                logger.info("[bold]bad[/red]")

            log_path = Path(temp_dir) / "run.log"
            content = log_path.read_text(encoding="utf-8")

            self.assertIn("[bold]bad[/red]", content)

    def test_constructor_creates_missing_directory(self):
        """构造函数应创建不存在的日志目录。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "outputs" / "run-001" / "logs"

            RunLogger(log_dir)

            self.assertTrue(log_dir.is_dir())

    def test_multiple_events_append_as_multiple_lines(self):
        """多次 log_event 调用应追加为多行 JSONL。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            logger = RunLogger(Path(temp_dir))

            logger.log_event("first", {"index": 1})
            logger.log_event("second", {"index": 2})

            events_path = Path(temp_dir) / "events.jsonl"
            lines = events_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in lines]

            self.assertEqual(len(events), 2)
            self.assertEqual([event["event"] for event in events], ["first", "second"])
            self.assertEqual([event["payload"]["index"] for event in events], [1, 2])


if __name__ == "__main__":
    unittest.main()

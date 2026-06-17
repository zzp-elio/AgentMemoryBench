"""测试运行上下文和结构化事件写入。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pytest

from memory_benchmark.observability import EventWriter, RunContext


pytestmark = pytest.mark.integration


class ObservabilityRunContextTests(unittest.TestCase):
    """验证 RunContext 和 EventWriter 的基础行为。"""

    def test_run_context_creates_standard_directories(self):
        """RunContext 应统一暴露 outputs/<run_id> 下的标准目录。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            expected_run_dir = Path(temp_dir).resolve() / "run-001"
            context = RunContext.create(
                run_id="run-001",
                benchmark_name="locomo",
                method_name="MemoryOS",
                model_name="gpt-4o-mini",
                output_root=Path(temp_dir),
                resume=True,
            )

            self.assertEqual(context.run_dir, expected_run_dir)
            self.assertEqual(context.logs_dir, context.run_dir / "logs")
            self.assertEqual(context.artifacts_dir, context.run_dir / "artifacts")
            self.assertEqual(context.checkpoints_dir, context.run_dir / "checkpoints")
            self.assertEqual(context.summaries_dir, context.run_dir / "summaries")
            self.assertTrue(context.logs_dir.is_dir())
            self.assertTrue(context.artifacts_dir.is_dir())
            self.assertTrue(context.checkpoints_dir.is_dir())
            self.assertTrue(context.summaries_dir.is_dir())

    def test_event_writer_appends_jsonl_events(self):
        """EventWriter 应追加结构化事件并自动补时间戳和事件名。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "events.jsonl"
            writer = EventWriter(event_path)

            writer.write("run_started", {"run_id": "run-001"})
            writer.write("question_done", {"question_id": "conv-1:q1", "f1": 0.5})

            rows = [
                json.loads(line)
                for line in event_path.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual([row["event"] for row in rows], ["run_started", "question_done"])
            self.assertEqual(rows[0]["payload"], {"run_id": "run-001"})
            self.assertIn("timestamp", rows[0])

    def test_run_context_can_skip_directory_creation_for_preflight(self):
        """预检上下文应能只构造路径对象而不触发任何目录副作用。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            context = RunContext.create(
                run_id="run-002",
                benchmark_name="locomo",
                method_name="MemoryOS",
                model_name="gpt-4o-mini",
                output_root=Path(temp_dir),
                resume=True,
                ensure_directories=False,
            )

            self.assertEqual(context.run_dir, Path(temp_dir).resolve() / "run-002")
            self.assertFalse(context.run_dir.exists())


if __name__ == "__main__":
    unittest.main()

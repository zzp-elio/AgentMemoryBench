"""测试 MemoryOS-LoCoMo smoke 入口的成本保护行为。

这些测试不访问真实 LLM，也不真正实例化 MemoryOS 官方代码。它们只验证：
默认模式只做 workload 估算；论文默认配置如果会触发大量更新，必须显式确认；
safe add-only 模式会使用高 STM capacity 跑公开 conversation 写入链路并写日志。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.runners.memoryos_locomo_smoke import run_memoryos_locomo_smoke


pytestmark = [pytest.mark.integration, pytest.mark.memoryos]


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MemoryOSLoCoMoSmokeTests(unittest.TestCase):
    """验证 MemoryOS-LoCoMo smoke 入口不会误触发高成本实验。"""

    def test_default_mode_only_estimates_workload_without_creating_memoryos(self):
        """默认 estimate 模式应只读取 LoCoMo 并估算，不实例化 MemoryOS。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("memory_benchmark.runners.memoryos_locomo_smoke.MemoryOS") as memoryos_cls:
                summary = run_memoryos_locomo_smoke(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-estimate",
                )

        self.assertEqual(summary.mode, "estimate")
        self.assertEqual(summary.conversation_id, "conv-26")
        self.assertEqual(summary.page_count, 214)
        self.assertEqual(summary.question_count, 152)
        self.assertEqual(summary.update_batch_count, 208)
        self.assertTrue(summary.will_trigger_updates)
        self.assertFalse(summary.add_executed)
        self.assertFalse(summary.answer_executed)
        memoryos_cls.assert_not_called()

    def test_paper_config_add_only_requires_explicit_confirmation(self):
        """paper-default add-only 会触发更新时，必须显式 confirm_expensive。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ConfigurationError):
                run_memoryos_locomo_smoke(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-guard",
                    mode="add-only",
                    use_paper_config=True,
                    confirm_expensive=False,
                )

    def test_safe_add_only_uses_large_capacity_and_writes_logs(self):
        """safe add-only 应避免更新、调用 MemoryOS.add，并写出结构化日志。"""

        fake_system = Mock()
        fake_system.add.return_value.conversation_ids = ["conv-26"]

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "memory_benchmark.runners.memoryos_locomo_smoke.MemoryOS",
                return_value=fake_system,
            ) as memoryos_cls:
                summary = run_memoryos_locomo_smoke(
                    project_root=PROJECT_ROOT,
                    output_root=Path(temp_dir),
                    run_id="unit-add-only",
                    mode="add-only",
                )

            log_dir = Path(temp_dir) / "unit-add-only" / "logs"
            event_lines = (log_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            events = [json.loads(line) for line in event_lines]

        self.assertEqual(summary.mode, "add-only")
        self.assertEqual(summary.page_count, 214)
        self.assertGreater(summary.short_term_capacity, summary.page_count)
        self.assertEqual(summary.update_batch_count, 0)
        self.assertFalse(summary.will_trigger_updates)
        self.assertTrue(summary.add_executed)
        self.assertFalse(summary.answer_executed)
        self.assertEqual(summary.added_conversation_ids, ["conv-26"])
        memoryos_cls.assert_called_once()
        fake_system.add.assert_called_once()
        self.assertIn("smoke_started", [event["event"] for event in events])
        self.assertIn("smoke_finished", [event["event"] for event in events])


if __name__ == "__main__":
    unittest.main()

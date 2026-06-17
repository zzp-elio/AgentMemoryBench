"""测试 LoCoMo 转换为 conversation-QA v2 Dataset。

这些测试只验证 adapter 的数据映射和 public/private 隔离，不评测 answer
质量，也不要求 Phase 1 method 处理图片推理。
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any
import unittest

import pytest

from memory_benchmark.benchmark_adapters import get_adapter, list_benchmarks
from memory_benchmark.benchmark_adapters.locomo import LoCoMoAdapter
from memory_benchmark.core.exceptions import DatasetValidationError


pytestmark = pytest.mark.integration


ROOT = Path(__file__).resolve().parents[1]


def _collect_keys(payload: Any) -> set[str]:
    """递归收集公开 payload 中出现过的所有 dict key。

    输入:
        payload: `to_public_dict()` 返回的公开结构。

    输出:
        set[str]: 所有层级的 key 名称集合。
    """

    keys: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(str(key))
            keys.update(_collect_keys(value))
    elif isinstance(payload, list):
        for item in payload:
            keys.update(_collect_keys(item))
    return keys


class LoCoMoConversationAdapterTest(unittest.TestCase):
    """验证 LoCoMo 的 conversation/session/turn/question 结构。"""

    def test_load_one_conversation_returns_locomo_dataset(self):
        """读取一条样本时，应返回名为 locomo 且只含一个 Conversation 的 Dataset。"""

        dataset = LoCoMoAdapter(ROOT).load(limit=1)

        self.assertEqual(dataset.dataset_name, "locomo")
        self.assertEqual(len(dataset.conversations), 1)
        self.assertEqual(dataset.metadata["source_path"], "data/locomo/locomo10.json")
        self.assertEqual(dataset.metadata["split"], "locomo10")

    def test_zero_limit_fails_with_clear_validation_error(self):
        """limit=0 没有可评测 conversation，应明确报校验错误。"""

        with self.assertRaises(DatasetValidationError):
            LoCoMoAdapter(ROOT).load(limit=0)

    def test_first_conversation_has_sessions_turns_questions_and_gold(self):
        """第一条 conversation 应包含 session、turn、公开问题和匹配的私有 gold。"""

        conversation = LoCoMoAdapter(ROOT).load(limit=1).conversations[0]
        first_session = conversation.sessions[0]
        first_turn = first_session.turns[0]
        first_question = conversation.questions[0]

        self.assertGreater(len(conversation.sessions), 0)
        self.assertGreater(len(first_session.turns), 0)
        self.assertGreater(len(conversation.questions), 0)
        self.assertEqual(len(conversation.questions), len(conversation.gold_answers))
        self.assertIn(first_question.question_id, conversation.gold_answers)
        self.assertEqual(first_question.conversation_id, conversation.conversation_id)
        self.assertTrue(first_session.session_time)
        self.assertTrue(first_turn.speaker)
        self.assertTrue(first_turn.content)
        self.assertTrue(first_turn.turn_id)
        self.assertIsNone(first_turn.normalized_role)

    def test_category_5_adversarial_questions_are_skipped(self):
        """LoCoMo category 5 是 adversarial，Phase 1 adapter 不应纳入公开问题。"""

        conversation = LoCoMoAdapter(ROOT).load(limit=1).conversations[0]

        self.assertNotIn("5", {question.category for question in conversation.questions})
        self.assertGreater(len(conversation.questions), 0)

    def test_malformed_session_is_not_silently_dropped(self):
        """形如 session_<n> 的坏字段必须报错，不能被 adapter 静默跳过。"""

        adapter = LoCoMoAdapter(ROOT)
        sample = copy.deepcopy(adapter.load_json("data", "locomo", "locomo10.json")[0])
        sample["conversation"]["session_1"] = "broken session"

        with self.assertRaises(DatasetValidationError):
            adapter._conversation_from_sample(sample, raw_index="0")

    def test_public_conversation_does_not_leak_gold_answer_or_evidence(self):
        """公开结构必须有 questions，但不能出现 gold_answers、answer 或 evidence key。"""

        conversation = LoCoMoAdapter(ROOT).load(limit=1).conversations[0]
        public = conversation.to_public_dict()
        public_keys = _collect_keys(public)

        self.assertIn("questions", public)
        self.assertNotIn("gold_answers", public_keys)
        self.assertNotIn("answer", public_keys)
        self.assertNotIn("evidence", public_keys)

    def test_registry_can_create_locomo_adapter(self):
        """默认 registry 应能列出并创建 LoCoMo v2 adapter。"""

        self.assertIn("locomo", list_benchmarks())
        adapter = get_adapter("locomo", ROOT)

        self.assertIsInstance(adapter, LoCoMoAdapter)


if __name__ == "__main__":
    unittest.main()

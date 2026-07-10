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


class LoCoMoOfficialSourceIdentityAndFullDataProfileTest(unittest.TestCase):
    """锁定 LoCoMo 官方来源身份 metadata 与全量真实数据剖面。

    这些测试用官方已核实的事实（见 `docs/survey/benchmarks/LoCoMo.md`）作为
    断言基准，防止 adapter 用硬编码/伪造数值伪装成"已计算"。全量断言必须
    读取完整 `locomo10.json`（不带 limit），保证计数来自真实解析结果。
    """

    @classmethod
    def setUpClass(cls) -> None:
        """加载一次全量 raw JSON 和全量 Dataset，供本类所有测试复用。"""

        cls.raw_samples: list[dict[str, Any]] = LoCoMoAdapter(ROOT).load_json(
            "data", "locomo", "locomo10.json"
        )
        cls.dataset = LoCoMoAdapter(ROOT).load()

    def test_dataset_metadata_records_official_source_identity_and_counts(self):
        """Dataset metadata 必须至少包含官方来源身份和真实聚合计数。"""

        metadata = self.dataset.metadata

        self.assertEqual(
            metadata["official_source_commit"],
            "3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376",
        )
        self.assertEqual(
            metadata["source_sha256"],
            "79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4",
        )
        self.assertEqual(metadata["official_question_count"], 1986)
        self.assertEqual(metadata["phase1_question_count"], 1540)
        self.assertEqual(metadata["excluded_question_categories"], [5])
        self.assertEqual(metadata["task"], "question_answering")

    def test_official_question_count_is_computed_from_raw_qa_not_hardcoded(self):
        """official_question_count 必须等于对 raw JSON 所有 qa 条目的真实计数。"""

        raw_qa_total = sum(len(sample.get("qa", [])) for sample in self.raw_samples)

        self.assertEqual(raw_qa_total, 1986)
        self.assertEqual(self.dataset.metadata["official_question_count"], raw_qa_total)

    def test_phase1_question_count_is_computed_from_actual_conversation_questions(self):
        """phase1_question_count 必须等于最终 Conversation.questions 实际总数。"""

        actual_final_question_total = sum(
            len(conversation.questions) for conversation in self.dataset.conversations
        )

        self.assertEqual(actual_final_question_total, 1540)
        self.assertEqual(
            self.dataset.metadata["phase1_question_count"], actual_final_question_total
        )

    def test_full_dataset_conversation_session_turn_counts(self):
        """全量数据应为 10 conversation、272 个实际 session、5,882 turn。"""

        conversations = self.dataset.conversations
        total_sessions = sum(len(conversation.sessions) for conversation in conversations)
        total_turns = sum(
            len(session.turns)
            for conversation in conversations
            for session in conversation.sessions
        )

        self.assertEqual(len(conversations), 10)
        self.assertEqual(total_sessions, 272)
        self.assertEqual(total_turns, 5882)

    def test_official_qa_category_counts_match_known_profile(self):
        """raw QA 按 category 统计必须是 {1:282, 2:321, 3:96, 4:841, 5:446}。"""

        category_counts: dict[int, int] = {}
        for sample in self.raw_samples:
            for qa_item in sample.get("qa", []):
                category = qa_item.get("category")
                category_counts[category] = category_counts.get(category, 0) + 1

        self.assertEqual(category_counts, {1: 282, 2: 321, 3: 96, 4: 841, 5: 446})

    def test_phase1_excludes_only_category_5(self):
        """排除 category 5 后，raw QA 总数应下降到 1,540，与 adapter 输出一致。"""

        raw_qa_total = sum(len(sample.get("qa", [])) for sample in self.raw_samples)
        category_5_total = sum(
            1
            for sample in self.raw_samples
            for qa_item in sample.get("qa", [])
            if qa_item.get("category") == 5
        )

        self.assertEqual(raw_qa_total - category_5_total, 1540)
        actual_final_question_total = sum(
            len(conversation.questions) for conversation in self.dataset.conversations
        )
        self.assertEqual(actual_final_question_total, 1540)

    def test_odd_turn_session_count_is_140_of_272(self):
        """140/272 个实际 session 应为奇数 turn 数。"""

        sessions = [
            session
            for conversation in self.dataset.conversations
            for session in conversation.sessions
        ]
        odd_sessions = [session for session in sessions if len(session.turns) % 2 == 1]

        self.assertEqual(len(sessions), 272)
        self.assertEqual(len(odd_sessions), 140)

    def test_no_turn_has_turn_level_timestamp_but_every_session_has_session_time(self):
        """5,882 个 turn 均无 turn 级时间戳，272 个实际 session 均有 session_time。"""

        sessions = [
            session
            for conversation in self.dataset.conversations
            for session in conversation.sessions
        ]
        turns = [turn for session in sessions for turn in session.turns]
        turns_with_timestamp = [turn for turn in turns if turn.turn_time]
        sessions_missing_time = [session for session in sessions if not session.session_time]

        self.assertEqual(len(turns), 5882)
        self.assertEqual(len(turns_with_timestamp), 0)
        self.assertEqual(len(sessions_missing_time), 0)

    def test_conv_26_has_16_date_only_session_keys_but_no_phantom_sessions(self):
        """conv-26 有 16 个 date-only key，adapter 不能据此构造空 session。"""

        conv_26_raw = next(
            sample
            for sample in self.raw_samples
            if sample.get("sample_id") == "conv-26"
        )
        conversation_raw = conv_26_raw["conversation"]
        session_numbers = {
            key[len("session_") :]
            for key in conversation_raw
            if key.startswith("session_")
            and key[len("session_") :].isdigit()
        }
        date_time_numbers = {
            key[len("session_") : -len("_date_time")]
            for key in conversation_raw
            if key.startswith("session_")
            and key.endswith("_date_time")
            and key[len("session_") : -len("_date_time")].isdigit()
        }
        date_only_numbers = date_time_numbers - session_numbers

        self.assertEqual(len(date_only_numbers), 16)

        conv_26 = next(
            conversation
            for conversation in self.dataset.conversations
            if conversation.conversation_id == "conv-26"
        )
        adapted_session_numbers = {
            session.session_id[len("session_") :] for session in conv_26.sessions
        }
        self.assertTrue(date_only_numbers.isdisjoint(adapted_session_numbers))

    def test_image_and_caption_turn_profile(self):
        """910 个 turn 有 img_url，1,226 个有 blip_caption，其中 316 个只有 caption。"""

        turns_with_url = 0
        turns_with_caption = 0
        caption_only_turns = 0
        for sample in self.raw_samples:
            conversation_raw = sample["conversation"]
            for key in conversation_raw:
                if not (key.startswith("session_") and key[len("session_") :].isdigit()):
                    continue
                for turn in conversation_raw[key]:
                    has_url = bool(turn.get("img_url"))
                    has_caption = bool(turn.get("blip_caption"))
                    if has_url:
                        turns_with_url += 1
                    if has_caption:
                        turns_with_caption += 1
                    if has_caption and not has_url:
                        caption_only_turns += 1

        self.assertEqual(turns_with_url, 910)
        self.assertEqual(turns_with_caption, 1226)
        self.assertEqual(caption_only_turns, 316)

    def test_no_duplicate_or_missing_dia_id_and_no_consecutive_same_speaker(self):
        """conversation 内无重复/缺失 dia_id，同一 session 内相邻 turn 无连续同 speaker。"""

        for conversation in self.dataset.conversations:
            turn_ids = [
                turn.turn_id
                for session in conversation.sessions
                for turn in session.turns
            ]
            self.assertTrue(all(turn_ids))
            self.assertEqual(len(turn_ids), len(set(turn_ids)))

            for session in conversation.sessions:
                previous_speaker = None
                for turn in session.turns:
                    if previous_speaker is not None:
                        self.assertNotEqual(turn.speaker, previous_speaker)
                    previous_speaker = turn.speaker


if __name__ == "__main__":
    unittest.main()

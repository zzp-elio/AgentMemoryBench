"""测试 LongMemEval 转换为 conversation-QA v2 Dataset。

这些测试只覆盖 adapter 的结构转换和 public/private 隔离。LongMemEval 的
`answer_session_ids` 与 turn 级 `has_answer` 都是评测标签，不能出现在 method
可见的公开 payload 中。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import unittest

import pytest

from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    RunScope,
    get_adapter,
    get_benchmark_registration,
    list_benchmarks,
)
from memory_benchmark.benchmark_adapters.longmemeval import LongMemEvalAdapter
from memory_benchmark.core.exceptions import ConfigurationError, DatasetValidationError


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


def _minimal_instance() -> dict[str, Any]:
    """构造一条最小 LongMemEval 原始 instance，用于坏数据校验测试。

    输出:
        dict[str, Any]: 字段完整、只有一个 session 的 synthetic instance。
    """

    return {
        "question_id": "synthetic_q1",
        "question_type": "single-session-user",
        "question": "What did I say I like?",
        "answer": "tea",
        "question_date": "2023/05/30 (Tue) 23:40",
        "haystack_session_ids": ["session_a"],
        "haystack_dates": ["2023/05/20 (Sat) 02:21"],
        "haystack_sessions": [
            [
                {"role": "user", "content": "I like tea.", "has_answer": True},
                {"role": "assistant", "content": "Noted."},
            ]
        ],
        "answer_session_ids": ["session_a"],
    }


class LongMemEvalConversationAdapterTest(unittest.TestCase):
    """验证 LongMemEval QA-centered instance 转换。"""

    def test_default_variant_loads_s_cleaned_dataset(self):
        """默认构造应加载 s_cleaned，并写入对应 metadata。"""

        dataset = LongMemEvalAdapter(ROOT).load(limit=1)

        self.assertEqual(dataset.metadata["source_path"], "data/longmemeval/longmemeval_s_cleaned.json")
        self.assertEqual(dataset.metadata["split"], "s_cleaned")
        self.assertEqual(dataset.metadata["variant"], "s_cleaned")
        self.assertEqual(dataset.metadata["total_raw_instances"], 1)
        self.assertFalse(dataset.metadata["source_fully_scanned"])
        self.assertEqual(dataset.conversations[0].metadata["source_path"], "data/longmemeval/longmemeval_s_cleaned.json")
        self.assertEqual(dataset.conversations[0].metadata["split"], "s_cleaned")
        self.assertEqual(dataset.conversations[0].metadata["variant"], "s_cleaned")

    def test_explicit_m_variant_loads_m_cleaned_dataset_with_limit_one(self):
        """显式 variant=m_cleaned 时，应能按 limit=1 读取 M 文件。"""

        dataset = LongMemEvalAdapter(ROOT, variant="m_cleaned").load(limit=1)

        self.assertEqual(dataset.metadata["source_path"], "data/longmemeval/longmemeval_m_cleaned.json")
        self.assertEqual(dataset.metadata["split"], "m_cleaned")
        self.assertEqual(dataset.metadata["variant"], "m_cleaned")
        self.assertEqual(dataset.metadata["total_raw_instances"], 1)
        self.assertFalse(dataset.metadata["source_fully_scanned"])
        self.assertEqual(len(dataset.conversations), 1)
        self.assertEqual(dataset.conversations[0].metadata["source_path"], "data/longmemeval/longmemeval_m_cleaned.json")
        self.assertEqual(dataset.conversations[0].metadata["split"], "m_cleaned")
        self.assertEqual(dataset.conversations[0].metadata["variant"], "m_cleaned")

    def test_unknown_variant_rejects_with_configuration_error(self):
        """未知或空白 variant 必须抛 ConfigurationError。"""

        with self.assertRaises(ConfigurationError):
            LongMemEvalAdapter(ROOT, variant="unknown").load(limit=1)

        with self.assertRaises(ConfigurationError):
            LongMemEvalAdapter(ROOT, variant="   ").load(limit=1)

    def test_load_one_conversation_returns_longmemeval_dataset(self):
        """limit=1 时，应返回 longmemeval Dataset 且只有一个 Conversation。"""

        dataset = LongMemEvalAdapter(ROOT).load(limit=1)

        self.assertEqual(dataset.dataset_name, "longmemeval")
        self.assertEqual(len(dataset.conversations), 1)
        self.assertEqual(dataset.metadata["source_path"], "data/longmemeval/longmemeval_s_cleaned.json")
        self.assertEqual(dataset.metadata["split"], "s_cleaned")
        self.assertEqual(dataset.metadata["variant"], "s_cleaned")
        self.assertEqual(dataset.metadata["total_raw_instances"], 1)
        self.assertFalse(dataset.metadata["source_fully_scanned"])

    def test_first_conversation_has_one_public_question_and_matching_gold(self):
        """每条 LongMemEval instance 应转换为一个公开 question 和对应 gold。"""

        conversation = LongMemEvalAdapter(ROOT).load(limit=1).conversations[0]
        question = conversation.questions[0]

        self.assertEqual(len(conversation.questions), 1)
        self.assertEqual(len(conversation.gold_answers), 1)
        self.assertIn(question.question_id, conversation.gold_answers)
        self.assertEqual(question.conversation_id, conversation.conversation_id)
        self.assertEqual(
            conversation.gold_answers[question.question_id].question_id,
            question.question_id,
        )
        self.assertTrue(conversation.gold_answers[question.question_id].answer)
        self.assertGreater(len(conversation.gold_answers[question.question_id].evidence), 0)

    def test_first_question_has_time_and_category(self):
        """公开 Question 应保留 question_date 和 question_type。"""

        question = LongMemEvalAdapter(ROOT).load(limit=1).conversations[0].questions[0]

        self.assertTrue(question.question_time)
        self.assertTrue(question.category)

    def test_list_answer_is_serialized_as_deterministic_json(self):
        """list 类型标准答案应保留顺序并序列化为稳定 JSON 文本。"""

        instance = _minimal_instance()
        instance["answer"] = ["tea", {"kind": "green", "rank": 1}]

        conversation = LongMemEvalAdapter(ROOT)._conversation_from_instance(
            instance,
            raw_index=0,
        )

        self.assertEqual(
            conversation.gold_answers["synthetic_q1"].answer,
            '["tea", {"kind": "green", "rank": 1}]',
        )

    def test_dict_answer_is_serialized_with_sorted_keys(self):
        """dict 类型标准答案应按 key 排序生成确定性 JSON 文本。"""

        instance = _minimal_instance()
        instance["answer"] = {"zeta": 2, "alpha": ["tea"]}

        conversation = LongMemEvalAdapter(ROOT)._conversation_from_instance(
            instance,
            raw_index=0,
        )

        self.assertEqual(
            conversation.gold_answers["synthetic_q1"].answer,
            '{"alpha": ["tea"], "zeta": 2}',
        )

    def test_first_session_has_time_turns_and_public_turn_fields(self):
        """history session 应保留时间、turn_id、speaker 和 content。"""

        first_session = LongMemEvalAdapter(ROOT).load(limit=1).conversations[0].sessions[0]
        first_turn = first_session.turns[0]

        self.assertTrue(first_session.session_time)
        self.assertGreater(len(first_session.turns), 0)
        self.assertTrue(first_turn.turn_id)
        self.assertTrue(first_turn.speaker)
        self.assertTrue(first_turn.content)

    def test_full_official_split_loads_after_source_normalization(self):
        """官方 S split 应全量可读，并锁住主检索路径 419 题分母。"""

        dataset = LongMemEvalAdapter(ROOT).load()

        self.assertEqual(len(dataset.conversations), 500)
        self.assertEqual(dataset.metadata["total_raw_instances"], 500)
        self.assertTrue(dataset.metadata["source_fully_scanned"])
        self.assertEqual(dataset.metadata["skipped_blank_turn_count"], 12)
        self.assertEqual(dataset.metadata["deduplicated_session_id_count"], 13)

        abstention_count = 0
        no_user_target_count = 0
        scored_count = 0
        for conversation in dataset.conversations:
            question = conversation.questions[0]
            gold = conversation.gold_answers[question.question_id]
            turn_view = next(
                group_set
                for group_set in gold.evidence_group_sets
                if (
                    group_set.provenance_granularity == "turn"
                    and group_set.unit_kind == "longmemeval_user_target_turn"
                )
            )
            if "_abs" in question.question_id:
                abstention_count += 1
            elif not turn_view.groups:
                no_user_target_count += 1
            else:
                scored_count += 1

        self.assertEqual(abstention_count, 30)
        self.assertEqual(no_user_target_count, 51)
        self.assertEqual(scored_count, 419)
        self.assertEqual(
            abstention_count + no_user_target_count + scored_count,
            500,
        )

    def test_full_m_cleaned_split_loads_all_instances(self):
        """M split 应能全量加载 500 个 evaluation instance。"""

        dataset = LongMemEvalAdapter(ROOT, variant="m_cleaned").load()

        self.assertEqual(len(dataset.conversations), 500)
        self.assertEqual(dataset.metadata["source_path"], "data/longmemeval/longmemeval_m_cleaned.json")
        self.assertEqual(dataset.metadata["split"], "m_cleaned")
        self.assertEqual(dataset.metadata["variant"], "m_cleaned")
        self.assertEqual(dataset.metadata["total_raw_instances"], 500)
        self.assertTrue(dataset.metadata["source_fully_scanned"])

    def test_blank_message_is_skipped_and_recorded(self):
        """空 content message 不进入统一 Turn，但跳过数量要写入 metadata 方便 debug。"""

        instance = _minimal_instance()
        instance["haystack_sessions"][0].append({"role": "user", "content": ""})

        conversation = LongMemEvalAdapter(ROOT)._conversation_from_instance(
            instance,
            raw_index=0,
        )

        self.assertEqual(conversation.metadata["skipped_blank_turn_count"], 1)
        self.assertEqual(len(conversation.sessions[0].turns), 2)

    def test_message_missing_content_and_text_fails(self):
        """缺少 content/text 字段是结构错误，不能当成官方空字符串脏数据跳过。"""

        instance = _minimal_instance()
        instance["haystack_sessions"][0].append({"role": "user"})

        with self.assertRaises(DatasetValidationError):
            LongMemEvalAdapter(ROOT)._conversation_from_instance(instance, raw_index=0)

    def test_duplicate_session_ids_are_made_unique_with_original_id_metadata(self):
        """重复 haystack_session_id 应生成唯一内部 session_id，并保留 original_session_id。"""

        instance = _minimal_instance()
        instance["haystack_session_ids"] = ["session_a", "session_a"]
        instance["haystack_dates"] = [
            "2023/05/20 (Sat) 02:21",
            "2023/05/21 (Sun) 02:21",
        ]
        instance["haystack_sessions"] = [
            [{"role": "user", "content": "I like tea."}],
            [{"role": "assistant", "content": "I remember that."}],
        ]

        conversation = LongMemEvalAdapter(ROOT)._conversation_from_instance(
            instance,
            raw_index=0,
        )
        session_ids = [session.session_id for session in conversation.sessions]

        self.assertEqual(len(session_ids), len(set(session_ids)))
        self.assertEqual(conversation.sessions[1].metadata["original_session_id"], "session_a")
        self.assertEqual(conversation.metadata["deduplicated_session_id_count"], 1)

    def test_gold_metadata_preserves_public_and_official_evidence_ids(self):
        """私有 gold 应同时保存公开匹配键与官方 corpus id 对照。"""

        instance = _minimal_instance()
        instance["haystack_session_ids"] = ["session_a", "session_a"]
        instance["haystack_dates"] = [
            "2023/05/20 (Sat) 02:21",
            "2023/05/21 (Sun) 02:21",
        ]
        instance["haystack_sessions"] = [
            [
                {"role": "assistant", "content": ""},
                {"role": "user", "content": "I like tea.", "has_answer": True},
            ],
            [
                {
                    "role": "assistant",
                    "content": "You told me you like tea.",
                    "has_answer": True,
                }
            ],
        ]
        instance["answer_session_ids"] = ["session_a"]

        conversation = LongMemEvalAdapter(ROOT)._conversation_from_instance(
            instance,
            raw_index=0,
        )
        gold = conversation.gold_answers["synthetic_q1"]

        self.assertEqual(gold.evidence, ["session_a"])
        self.assertEqual(
            gold.metadata["evidence_turn_ids"],
            ["session_a:t1", "session_a#occurrence_2:t0"],
        )
        self.assertEqual(
            gold.metadata["evidence_turn_corpus_ids"],
            ["session_a_2", "session_a_1"],
        )
        self.assertEqual(
            gold.metadata["evidence_session_public_ids"],
            ["session_a", "session_a#occurrence_2"],
        )

        public_keys = _collect_keys(conversation.to_public_dict())
        self.assertNotIn("has_answer", public_keys)
        self.assertNotIn("evidence_turn_ids", public_keys)
        self.assertNotIn("evidence_turn_corpus_ids", public_keys)
        self.assertNotIn("evidence_session_public_ids", public_keys)

    def test_public_conversation_does_not_leak_gold_answer_or_evidence(self):
        """公开结构有 questions，但不能出现答案、evidence 或 LongMemEval 私有标签。"""

        conversation = LongMemEvalAdapter(ROOT).load(limit=1).conversations[0]
        public = conversation.to_public_dict()
        public_keys = _collect_keys(public)

        self.assertIn("questions", public)
        self.assertNotIn("gold_answers", public_keys)
        self.assertNotIn("answer", public_keys)
        self.assertNotIn("evidence", public_keys)
        self.assertNotIn("answer_session_ids", public_keys)
        self.assertNotIn("has_answer", public_keys)

    def test_public_payload_for_m_variant_keeps_private_labels_isolated(self):
        """M variant 的公开 payload 也不能泄漏 private labels。"""

        conversation = LongMemEvalAdapter(ROOT, variant="m_cleaned").load(limit=1).conversations[0]
        public = conversation.to_public_dict()
        public_keys = _collect_keys(public)

        self.assertNotIn("answer_session_ids", public_keys)
        self.assertNotIn("has_answer", public_keys)
        self.assertNotIn("answer", public_keys)
        self.assertNotIn("evidence", public_keys)
        self.assertNotIn("gold", public_keys)

    def test_zero_limit_fails_with_clear_validation_error(self):
        """limit=0 没有可评测 conversation，应明确报校验错误。"""

        with self.assertRaises(DatasetValidationError):
            LongMemEvalAdapter(ROOT).load(limit=0)

    def test_haystack_parallel_length_mismatch_fails(self):
        """haystack ids/dates/sessions 三个并行列表长度不一致时必须报错。"""

        instance = _minimal_instance()
        instance["haystack_dates"] = []

        with self.assertRaises(DatasetValidationError):
            LongMemEvalAdapter(ROOT)._conversation_from_instance(instance, raw_index=0)

    def test_registry_can_create_longmemeval_adapter(self):
        """默认 registry 应能列出并创建 LongMemEval v2 adapter。"""

        self.assertIn("longmemeval", list_benchmarks())
        adapter = get_adapter("longmemeval", ROOT)

        self.assertIsInstance(adapter, LongMemEvalAdapter)

    def test_registry_prepares_explicit_variant_requests(self):
        """registry 的 LongMemEval preparation 应按 request.variant 选择 concrete file。"""

        registration = get_benchmark_registration("longmemeval")
        self.assertEqual(registration.default_variant, "s_cleaned")
        self.assertEqual(registration.prediction_enabled, True)
        self.assertEqual(registration.variant_names(), ("s_cleaned", "m_cleaned"))

        smoke_run = registration.prepare(
            ROOT,
            BenchmarkLoadRequest(
                variant="m_cleaned",
                run_scope=RunScope.SMOKE,
                smoke_turn_limit=1,
                smoke_conversation_limit=99,
            ),
        )
        self.assertEqual(smoke_run.variant, "m_cleaned")
        self.assertEqual(
            smoke_run.source_relative_paths,
            (Path("data/longmemeval/longmemeval_m_cleaned.json"),),
        )
        self.assertEqual(smoke_run.dataset.metadata["source_path"], "data/longmemeval/longmemeval_m_cleaned.json")
        self.assertEqual(smoke_run.dataset.metadata["split"], "m_cleaned")
        self.assertEqual(smoke_run.dataset.metadata["variant"], "m_cleaned")
        self.assertEqual(smoke_run.dataset.metadata["total_raw_instances"], 99)
        self.assertFalse(smoke_run.dataset.metadata["source_fully_scanned"])
        self.assertEqual(len(smoke_run.dataset.conversations), 99)
        self.assertEqual(smoke_run.dataset.conversations[0].metadata["source_path"], "data/longmemeval/longmemeval_m_cleaned.json")
        self.assertEqual(smoke_run.dataset.conversations[0].metadata["split"], "m_cleaned")
        self.assertEqual(smoke_run.dataset.conversations[0].metadata["variant"], "m_cleaned")


class LongMemEvalGoldEvidenceGroupTest(unittest.TestCase):
    """验证 LongMemEval gold evidence contract v1 group views。"""

    def _convert(self, instance: dict[str, Any]):
        """用 s_cleaned adapter 把 synthetic instance 转成 conversation。"""

        return LongMemEvalAdapter(ROOT)._conversation_from_instance(instance, 0)

    def test_assistant_has_answer_turn_is_not_a_turn_gold_unit(self):
        """assistant 侧 has_answer 不得进入官方 turn view（官方只收 user）。"""

        instance = _minimal_instance()
        instance["haystack_sessions"] = [
            [
                {"role": "user", "content": "I like tea.", "has_answer": True},
                {"role": "assistant", "content": "You like tea.", "has_answer": True},
            ]
        ]
        conversation = self._convert(instance)
        gold = conversation.gold_answers["synthetic_q1"]

        self.assertEqual(gold.gold_evidence_contract_version, "v1")
        views = {
            (group_set.provenance_granularity, group_set.unit_kind): group_set
            for group_set in gold.evidence_group_sets
        }
        self.assertEqual(
            set(views),
            {
                ("turn", "longmemeval_user_target_turn"),
                ("session", "longmemeval_answer_session"),
            },
        )
        turn_view = views[("turn", "longmemeval_user_target_turn")]
        self.assertEqual(len(turn_view.groups), 1)
        self.assertEqual(turn_view.groups[0].unit_id, "session_a:t0")
        self.assertEqual(turn_view.groups[0].child_ids, ("session_a:t0",))
        self.assertEqual(turn_view.groups[0].mapping_status, "mapped")
        # 旧 role-agnostic metadata 仍保留供审计，但权威 qrel 不再收 assistant。
        self.assertEqual(
            gold.metadata["evidence_turn_ids"],
            ["session_a:t0", "session_a:t1"],
        )

    def test_no_user_target_question_has_empty_turn_view(self):
        """只有 assistant 侧 target 的题在 turn view 得到空 groups。"""

        instance = _minimal_instance()
        instance["haystack_sessions"] = [
            [
                {"role": "user", "content": "I like tea."},
                {"role": "assistant", "content": "Noted.", "has_answer": True},
            ]
        ]
        conversation = self._convert(instance)
        gold = conversation.gold_answers["synthetic_q1"]
        turn_view = next(
            group_set
            for group_set in gold.evidence_group_sets
            if group_set.provenance_granularity == "turn"
        )

        self.assertEqual(turn_view.groups, ())

    def test_session_view_maps_official_session_to_public_ids(self):
        """session view 以官方 answer_session_id 为 unit，child 为公开 session id。"""

        instance = _minimal_instance()
        instance["haystack_session_ids"] = ["session_a", "session_a", "session_b"]
        instance["haystack_dates"] = ["d1", "d2", "d3"]
        instance["haystack_sessions"] = [
            [{"role": "user", "content": "one", "has_answer": True}],
            [{"role": "user", "content": "two"}],
            [{"role": "user", "content": "three"}],
        ]
        instance["answer_session_ids"] = ["session_a", "session_a", "missing_session"]
        conversation = self._convert(instance)
        gold = conversation.gold_answers["synthetic_q1"]
        session_view = next(
            group_set
            for group_set in gold.evidence_group_sets
            if group_set.provenance_granularity == "session"
        )

        groups = {group.unit_id: group for group in session_view.groups}
        # 官方 id 稳定去重：session_a 只出现一次。
        self.assertEqual(
            [group.unit_id for group in session_view.groups],
            ["session_a", "missing_session"],
        )
        # 重复 haystack session id 的两个公开 occurrence 都是合法 child。
        self.assertEqual(
            groups["session_a"].child_ids,
            ("session_a", "session_a#occurrence_2"),
        )
        self.assertEqual(groups["session_a"].mapping_status, "mapped")
        # 找不到公开 session 的官方 id 记 unmatched，不静默删分母。
        self.assertEqual(groups["missing_session"].mapping_status, "unmatched")

    def test_blank_user_target_turn_becomes_unmatched(self):
        """因空内容被跳过的 user 侧 target turn 记 unmatched，不制造伪 child。"""

        instance = _minimal_instance()
        instance["haystack_sessions"] = [
            [
                {"role": "user", "content": "   ", "has_answer": True},
                {"role": "user", "content": "I like tea.", "has_answer": True},
                {"role": "assistant", "content": "Noted."},
            ]
        ]
        conversation = self._convert(instance)
        gold = conversation.gold_answers["synthetic_q1"]
        turn_view = next(
            group_set
            for group_set in gold.evidence_group_sets
            if group_set.provenance_granularity == "turn"
        )

        self.assertEqual(
            [(group.unit_id, group.mapping_status) for group in turn_view.groups],
            [("session_a:t0", "unmatched"), ("session_a:t1", "mapped")],
        )

    def test_real_data_first_instance_declares_v1_views(self):
        """真实 s_cleaned 首条 instance 应声明 v1 且公开 payload 无泄漏。"""

        conversation = LongMemEvalAdapter(ROOT).load(limit=1).conversations[0]
        gold = next(iter(conversation.gold_answers.values()))

        self.assertEqual(gold.gold_evidence_contract_version, "v1")
        self.assertEqual(len(gold.evidence_group_sets), 2)
        keys = _collect_keys(conversation.to_public_dict())
        self.assertNotIn("evidence_group_sets", keys)
        self.assertNotIn("unit_id", keys)
        self.assertNotIn("gold_evidence_contract_version", keys)


if __name__ == "__main__":
    unittest.main()

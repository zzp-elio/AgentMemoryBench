"""测试 conversation-QA 数据强约束校验。"""

import unittest

import pytest

from memory_benchmark.benchmark_adapters.base import BenchmarkAdapter
from memory_benchmark.core import Conversation, Dataset, GoldAnswerInfo, Question, Session, Turn
from memory_benchmark.core.exceptions import DataLeakageError, DatasetValidationError
from memory_benchmark.core.validators import (
    validate_dataset,
    validate_no_private_keys,
)


pytestmark = pytest.mark.unit


def build_valid_dataset() -> Dataset:
    """构造一个最小合法 Dataset。"""

    question = Question(question_id="q1", conversation_id="conv1", text="What does Alice like?")
    return Dataset(
        dataset_name="dummy",
        conversations=[
            Conversation(
                conversation_id="conv1",
                sessions=[
                    Session(
                        session_id="s1",
                        session_time="2024-01-01",
                        turns=[Turn(turn_id="t1", speaker="Alice", content="I like tea.")],
                    )
                ],
                questions=[question],
                gold_answers={"q1": GoldAnswerInfo(question_id="q1", answer="tea")},
            )
        ],
    )


class MetadataLeakAdapter(BenchmarkAdapter):
    """测试用 adapter，用于确认 load() 会检查公开 metadata 泄漏。"""

    name = "metadata_leak"

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """返回一个结构合法但公开 metadata 含私有键的数据集。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].metadata["gold_answer"] = "tea"
        return dataset


class ConversationDatasetValidationTest(unittest.TestCase):
    """验证数据缺字段时能尽早报错。"""

    def test_valid_dataset_passes(self):
        """合法数据集应通过通用校验。"""

        validate_dataset(build_valid_dataset())

    def test_question_without_gold_answer_fails(self):
        """每个 Question 必须有对应 GoldAnswerInfo。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].gold_answers = {}

        with self.assertRaises(DatasetValidationError):
            validate_dataset(dataset)

    def test_extra_gold_answer_without_question_fails(self):
        """gold_answers 里不能出现没有公开 Question 对应的私有答案。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].gold_answers["q2"] = GoldAnswerInfo(
            question_id="q2",
            answer="coffee",
        )

        with self.assertRaises(DatasetValidationError):
            validate_dataset(dataset)

    def test_turn_without_content_fails(self):
        """纯文本 Phase 1 中 turn content 不能为空。"""

        dataset = build_valid_dataset()
        dataset.conversations[0].sessions[0].turns[0].content = ""

        with self.assertRaises(DatasetValidationError):
            validate_dataset(dataset)

    def test_public_conversation_payload_has_no_private_keys(self):
        """公开 Conversation 导出应通过 private key 泄漏检查。"""

        conversation = build_valid_dataset().conversations[0]

        validate_no_private_keys(conversation.to_public_dict())

    def test_payload_with_gold_answer_key_fails(self):
        """公开 payload 里出现 gold_answers 应被视为泄漏风险。"""

        payload = build_valid_dataset().conversations[0].to_public_dict()
        payload["gold_answers"] = {"q1": {"answer": "tea"}}

        with self.assertRaises(DataLeakageError):
            validate_no_private_keys(payload)

    def test_payload_with_answer_session_ids_key_fails(self):
        """公开 payload 里出现 LongMemEval answer_session_ids 应被视为泄漏。"""

        payload = build_valid_dataset().conversations[0].to_public_dict()
        payload["metadata"]["answer_session_ids"] = ["session_1"]

        with self.assertRaises(DataLeakageError):
            validate_no_private_keys(payload)

    def test_adapter_load_checks_public_metadata_leakage(self):
        """BenchmarkAdapter.load 应阻止公开 metadata 中的 gold_answer 键。"""

        adapter = MetadataLeakAdapter(project_root=".")

        with self.assertRaises(DataLeakageError):
            adapter.load()


if __name__ == "__main__":
    unittest.main()

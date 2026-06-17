"""测试 conversation-QA runner 和 mock memory system。"""

import unittest

import pytest

from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    ImageRef,
    MetricResult,
    Question,
    Session,
    Turn,
)
from memory_benchmark.methods.mock import MockMemorySystem
from memory_benchmark.runners.conversation_qa import run_conversation_qa


pytestmark = pytest.mark.integration


def build_runner_dataset() -> Dataset:
    """构造一个包含两个公开问题和私有 gold 的最小 Dataset。"""

    questions = [
        Question(
            question_id="q1",
            conversation_id="conv1",
            text="Alice likes which drink?",
            metadata={"difficulty": "easy"},
        ),
        Question(
            question_id="q2",
            conversation_id="conv1",
            text="Who likes coffee?",
        ),
    ]
    return Dataset(
        dataset_name="runner_dummy",
        conversations=[
            Conversation(
                conversation_id="conv1",
                sessions=[
                    Session(
                        session_id="s1",
                        turns=[
                            Turn(
                                turn_id="t1",
                                speaker="Alice",
                                content="I like tea.",
                            ),
                            Turn(
                                turn_id="t2",
                                speaker="Bob",
                                content="I like coffee.",
                            ),
                        ],
                    )
                ],
                questions=questions,
                gold_answers={
                    "q1": GoldAnswerInfo(
                        question_id="q1",
                        answer="tea",
                        evidence=["s1:t1"],
                    ),
                    "q2": GoldAnswerInfo(
                        question_id="q2",
                        answer="Bob",
                        evidence=["s1:t2"],
                    ),
                },
            )
        ],
    )


class RecordingMockMemorySystem(MockMemorySystem):
    """记录 runner 传入的公开对象，方便检查是否发生私有数据泄漏。"""

    def __init__(self, answers_by_question_id: dict[str, str]):
        """保存固定答案并初始化调用记录。"""

        super().__init__(answers_by_question_id=answers_by_question_id)
        self.add_payloads: list[list[Conversation]] = []
        self.question_payloads: list[Question] = []

    def add(self, conversations: list[Conversation]) -> AddResult:
        """记录 add 入参后委托给 mock 实现。"""

        self.add_payloads.append(conversations)
        return super().add(conversations)

    def get_answer(self, question: Question) -> AnswerResult:
        """记录 get_answer 入参后委托给 mock 实现。"""

        self.question_payloads.append(question)
        return super().get_answer(question)


class ExactMatchEvaluator:
    """测试用 evaluator，确认 runner 在内部把 gold 交给 scorer。"""

    def __init__(self):
        """初始化 evaluator 调用记录。"""

        self.seen_gold_answers: list[str] = []

    def evaluate(
        self,
        question: Question,
        prediction: AnswerResult,
        gold_answer: GoldAnswerInfo,
    ) -> MetricResult:
        """按标准答案字符串精确匹配，返回一个 MetricResult。"""

        self.seen_gold_answers.append(gold_answer.answer)
        is_correct = prediction.answer == gold_answer.answer
        return MetricResult(
            metric_name="exact_match",
            score=1.0 if is_correct else 0.0,
            is_correct=is_correct,
            details={"question_id": question.question_id},
        )


class ConversationQARunnerTest(unittest.TestCase):
    """验证同步 conversation-QA runner 的最小闭环。"""

    def test_runner_calls_add_and_get_answer(self):
        """runner 应先 add 当前 conversation，再逐题调用 get_answer。"""

        dataset = build_runner_dataset()
        system = RecordingMockMemorySystem(
            answers_by_question_id={"q1": "tea", "q2": "Bob"}
        )

        result = run_conversation_qa(dataset=dataset, system=system)

        self.assertEqual(system.added_conversation_ids, ["conv1"])
        self.assertEqual(len(system.add_payloads), 1)
        self.assertEqual([question.question_id for question in system.question_payloads], ["q1", "q2"])
        self.assertEqual(result.dataset_name, "runner_dummy")

    def test_runner_does_not_pass_gold_answers_to_system_add(self):
        """传给 method.add 的 Conversation 不能包含 gold_answers 私有负载。"""

        dataset = build_runner_dataset()
        system = RecordingMockMemorySystem(answers_by_question_id={"q1": "tea", "q2": "Bob"})

        run_conversation_qa(dataset=dataset, system=system)

        public_conversation = system.add_payloads[0][0]
        public_payload_text = str(public_conversation.to_public_dict())
        self.assertEqual(public_conversation.gold_answers, {})
        self.assertNotIn("gold_answers", public_payload_text)
        self.assertNotIn("s1:t1", public_payload_text)
        self.assertNotIn("s1:t2", public_payload_text)

    def test_runner_passes_question_without_answer_or_evidence_to_get_answer(self):
        """传给 get_answer 的 Question 只能包含公开问题字段。"""

        dataset = build_runner_dataset()
        system = RecordingMockMemorySystem(answers_by_question_id={"q1": "tea", "q2": "Bob"})

        run_conversation_qa(dataset=dataset, system=system)

        first_question = system.question_payloads[0]
        self.assertEqual(first_question.text, "Alice likes which drink?")
        self.assertFalse(hasattr(first_question, "answer"))
        self.assertFalse(hasattr(first_question, "evidence"))
        self.assertNotIn("answer", first_question.to_dict())
        self.assertNotIn("evidence", first_question.to_dict())

    def test_runner_rebuilds_public_objects_without_dynamic_private_attrs(self):
        """runner 不能把 dataclass 动态挂载的私有属性传给 method。

        背景:
            Python dataclass 默认允许运行时追加属性。仅检查 `to_public_dict()`
            不足以发现这些动态属性，因为 method 收到的是对象本身。
        """

        dataset = build_runner_dataset()
        conversation = dataset.conversations[0]
        session = conversation.sessions[0]
        turn = session.turns[0]
        image = ImageRef(image_id="img1", path="/tmp/example.png", caption="public image")
        turn.images.append(image)
        conversation.gold_answer = "dynamic-private-conversation"
        session.answer_session_ids = ["s1"]
        turn.evidence = ["t1"]
        image.judge_label = True
        conversation.questions[0].answer = "dynamic-private-question"
        system = RecordingMockMemorySystem(answers_by_question_id={"q1": "tea", "q2": "Bob"})

        run_conversation_qa(dataset=dataset, system=system)

        public_conversation = system.add_payloads[0][0]
        public_session = public_conversation.sessions[0]
        public_turn = public_session.turns[0]
        public_image = public_turn.images[0]
        public_question_in_add = public_conversation.questions[0]
        public_question_in_answer = system.question_payloads[0]
        self.assertFalse(hasattr(public_conversation, "gold_answer"))
        self.assertFalse(hasattr(public_session, "answer_session_ids"))
        self.assertFalse(hasattr(public_turn, "evidence"))
        self.assertFalse(hasattr(public_image, "judge_label"))
        self.assertFalse(hasattr(public_question_in_add, "answer"))
        self.assertFalse(hasattr(public_question_in_answer, "answer"))

    def test_evaluator_receives_gold_internally_and_returns_metric(self):
        """runner 内部取 gold 给 evaluator，并把 MetricResult 写入明细。"""

        dataset = build_runner_dataset()
        system = RecordingMockMemorySystem(
            answers_by_question_id={"q1": "tea", "q2": "wrong"}
        )
        evaluator = ExactMatchEvaluator()

        result = run_conversation_qa(
            dataset=dataset,
            system=system,
            evaluators=[evaluator],
        )

        self.assertEqual(evaluator.seen_gold_answers, ["tea", "Bob"])
        self.assertEqual(result.detailed_results[0]["metrics"]["exact_match"]["score"], 1.0)
        self.assertEqual(result.detailed_results[1]["metrics"]["exact_match"]["score"], 0.0)
        self.assertEqual(result.metrics["exact_match"]["score"], 0.5)

    def test_total_question_count_and_detail_shape_are_sane(self):
        """EvaluationResult 应包含总题数和稳定的单题明细字段。"""

        dataset = build_runner_dataset()
        system = RecordingMockMemorySystem(answers_by_question_id={"q1": "tea", "q2": "Bob"})

        result = run_conversation_qa(dataset=dataset, system=system)

        self.assertEqual(result.total_questions, 2)
        self.assertEqual(len(result.detailed_results), 2)
        self.assertEqual(
            set(result.detailed_results[0]),
            {
                "conversation_id",
                "question_id",
                "question_text",
                "prediction_answer",
                "metrics",
            },
        )
        self.assertEqual(result.detailed_results[0]["conversation_id"], "conv1")
        self.assertEqual(result.detailed_results[0]["question_id"], "q1")
        self.assertEqual(result.detailed_results[0]["prediction_answer"], "tea")


if __name__ == "__main__":
    unittest.main()

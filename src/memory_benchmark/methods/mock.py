"""conversation-QA 测试用 mock memory system。

本模块提供一个同步、无外部依赖的 BaseMemorySystem 实现，用于 runner
单元测试和后续 smoke test。它只按 question_id 返回固定答案，不做真实记忆。
"""

from __future__ import annotations

from collections.abc import Mapping

from memory_benchmark.core import AddResult, AnswerResult, Conversation, Question
from memory_benchmark.core.interfaces import BaseMemorySystem


class MockMemorySystem(BaseMemorySystem):
    """按 question_id 返回固定答案的 mock 记忆系统。

    字段:
        answers_by_question_id: 测试配置的答案映射。
        added_conversation_ids: 已通过 add 写入的 conversation id，供测试检查。
    """

    def __init__(
        self,
        answers_by_question_id: Mapping[str, str] | None = None,
        default_answer: str | None = None,
    ):
        """初始化 mock 答案表。

        输入:
            answers_by_question_id: question_id 到回答文本的映射。
            default_answer: 未配置 question_id 时返回的兜底答案；None 时按 question_id
                生成可诊断的 mock 文本。

        输出:
            None。实例会记录后续 add 调用中的 conversation id。
        """

        self.answers_by_question_id = dict(answers_by_question_id or {})
        self.default_answer = default_answer
        self.added_conversation_ids: list[str] = []

    def add(self, conversations: list[Conversation]) -> AddResult:
        """记录已写入的公开 conversation。

        输入:
            conversations: runner 传入的公开 Conversation 列表，预期不含 gold_answers。

        输出:
            AddResult: 本次写入的 conversation ids。
        """

        conversation_ids = [conversation.conversation_id for conversation in conversations]
        self.added_conversation_ids.extend(conversation_ids)
        return AddResult(conversation_ids=conversation_ids, metadata={"method": "mock"})

    def get_answer(self, question: Question) -> AnswerResult:
        """返回固定答案或兜底 mock 答案。

        输入:
            question: runner 传入的公开 Question，不能包含标准答案或 evidence。

        输出:
            AnswerResult: question_id、conversation_id 和预测答案。
        """

        if question.question_id in self.answers_by_question_id:
            answer = self.answers_by_question_id[question.question_id]
        elif self.default_answer is not None:
            answer = self.default_answer
        else:
            answer = f"mock-answer-for:{question.question_id}"

        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=answer,
            metadata={"method": "mock"},
        )


__all__ = ["MockMemorySystem"]

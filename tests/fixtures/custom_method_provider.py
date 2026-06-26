"""pytest 用的用户自定义 method fixture。

它模拟普通用户只实现 BaseMemoryProvider，不接入内置 registry、TOML 或 source identity。
"""

from __future__ import annotations

from memory_benchmark.core import (
    AddResult,
    AnswerPromptResult,
    Conversation,
    PromptMessage,
    Question,
)
from memory_benchmark.core.interfaces import BaseMemoryProvider


class FixtureCustomMemory(BaseMemoryProvider):
    """最小用户 memory provider：把 conversation 文本存在进程内 dict。"""

    def __init__(self) -> None:
        """无参数构造，符合用户轻量接入契约。"""

        self._memory_by_conversation: dict[str, str] = {}

    def add(self, conversation: Conversation) -> AddResult:
        """按 conversation_id 写入公开历史。"""

        snippets: list[str] = []
        for session in conversation.sessions:
            for turn in session.turns:
                snippets.append(f"{turn.speaker}: {turn.content}")
        self._memory_by_conversation[conversation.conversation_id] = "\n".join(
            snippets
        )
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """构造完整 answer prompt messages。"""

        memory = self._memory_by_conversation.get(question.conversation_id, "")
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            prompt_messages=[
                PromptMessage(
                    role="system",
                    content="Answer from the provided memory.",
                ),
                PromptMessage(
                    role="user",
                    content=f"Memory:\n{memory}\n\nQuestion: {question.text}",
                ),
            ],
            metadata={"answer_context": memory},
        )

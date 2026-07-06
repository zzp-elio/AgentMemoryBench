"""测试 adapter 原生化等价性工具骨架。"""

from __future__ import annotations

from memory_benchmark.core import AddResult, AnswerPromptResult, PromptMessage, Question
from memory_benchmark.core.interfaces import BaseMemoryProvider
from tests.equivalence_utils import run_bridge_sequence
from tests.fake_corpus import build_multimodal_consecutive_speaker_conversation


class RecordingSequenceProvider(BaseMemoryProvider):
    """记录旧 provider add/retrieve 调用序列的 fake provider。"""

    def __init__(self) -> None:
        """初始化调用序列。"""

        self.calls: list[dict[str, object]] = []

    def add(self, conversation):
        """记录旧 add 收到的公开 conversation。"""

        self.calls.append(
            {
                "op": "add",
                "conversation": conversation.to_public_dict(),
            }
        )
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """记录旧 retrieve 收到的公开 question。"""

        self.calls.append({"op": "retrieve", "question": question.to_dict()})
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            prompt_messages=[PromptMessage(role="user", content="memory")],
            metadata={"answer_context": "memory"},
        )


def test_bridge_sequence_self_equivalence() -> None:
    """等价性工具对桥接路径自比应得到完全一致的调用序列。"""

    conversation = build_multimodal_consecutive_speaker_conversation()
    question = conversation.questions[0]
    left = RecordingSequenceProvider()
    right = RecordingSequenceProvider()

    left_result = run_bridge_sequence(
        provider=left,
        conversation=conversation,
        question=question,
        run_id="equiv-run",
    )
    right_result = run_bridge_sequence(
        provider=right,
        conversation=conversation,
        question=question,
        run_id="equiv-run",
    )

    assert left_result.calls == right_result.calls
    assert left_result.calls == tuple(left.calls)

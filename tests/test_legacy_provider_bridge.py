"""测试旧 BaseMemoryProvider 到 v3 MemoryProvider 的兼容桥。"""

from __future__ import annotations

from memory_benchmark.core import (
    AddResult,
    AnswerPromptResult,
    PromptMessage,
    Question,
)
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.core.provider_bridge import LegacyProviderBridge
from memory_benchmark.core.provider_protocol import (
    BRIDGE_EMPTY_MEMORY_SENTINEL,
    ConversationBatch,
    RetrievalQuery,
    SessionBatch,
    TurnEvent,
)


class RecordingLegacyProvider(BaseMemoryProvider):
    """记录旧接口调用并返回指定 retrieval metadata 的 fake provider。"""

    def __init__(self, metadata: dict[str, object]):
        """保存 retrieval metadata 并初始化调用记录。"""

        self.metadata = metadata
        self.added_conversation_ids: list[str] = []
        self.added_session_ids: list[list[str]] = []
        self.retrieved_questions: list[Question] = []

    def add(self, conversation):
        """记录兼容桥重建出的旧 Conversation。"""

        self.added_conversation_ids.append(conversation.conversation_id)
        self.added_session_ids.append(
            [session.session_id for session in conversation.sessions]
        )
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """返回包含 prompt messages 的旧 AnswerPromptResult。"""

        self.retrieved_questions.append(question)
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            prompt_messages=[
                PromptMessage(role="system", content="legacy system prompt"),
                PromptMessage(role="user", content=f"legacy answer {question.text}"),
            ],
            metadata=dict(self.metadata),
        )


def _batch() -> ConversationBatch:
    """构造 conversation 粒度批量 ingest 单元。"""

    return ConversationBatch(
        isolation_key="run-1_conv-1",
        sessions=(
            SessionBatch(
                isolation_key="run-1_conv-1",
                session_id="s1",
                session_time="2026-07-06T00:00:00Z",
                events=(
                    TurnEvent(
                        role="user",
                        speaker_name="Alice",
                        content="公开记忆",
                        timestamp=None,
                        isolation_key="run-1_conv-1",
                        session_id="s1",
                        turn_id="t1",
                        metadata={"conversation_id": "conv-1"},
                    ),
                ),
            ),
        ),
        metadata={"conversation_id": "conv-1"},
    )


def _query() -> RetrievalQuery:
    """构造带原始公开 Question 的 v3 检索输入。"""

    question = Question(
        question_id="q1",
        conversation_id="conv-1",
        text="问题？",
        question_time="2026-07-06T00:01:00Z",
    )
    return RetrievalQuery(
        query_text=question.text,
        isolation_key="run-1_conv-1",
        question_time=question.question_time,
        top_k=5,
        purpose="qa",
        source_question=question,
    )


def test_bridge_rebuilds_conversation_for_legacy_add() -> None:
    """桥接 ingest 必须重建旧 Conversation 并调用 legacy add。"""

    legacy = RecordingLegacyProvider(metadata={"answer_context": "记忆上下文"})
    bridge = LegacyProviderBridge(legacy)

    result = bridge.ingest(_batch())

    assert bridge.consume_granularity == "conversation"
    assert legacy.added_conversation_ids == ["conv-1"]
    assert legacy.added_session_ids == [["s1"]]
    assert result is not None
    assert result.unit_ref is not None
    assert result.unit_ref.isolation_key == "run-1_conv-1"


def test_bridge_prefers_answer_context_for_formatted_memory() -> None:
    """formatted_memory 应优先来自旧 metadata.answer_context。"""

    legacy = RecordingLegacyProvider(metadata={"answer_context": "显式上下文"})
    bridge = LegacyProviderBridge(legacy)

    result = bridge.retrieve(_query())

    assert legacy.retrieved_questions == [_query().source_question]
    assert result.formatted_memory == "显式上下文"
    assert result.prompt_messages == (
        PromptMessage(role="system", content="legacy system prompt"),
        PromptMessage(role="user", content="legacy answer 问题？"),
    )


def test_bridge_joins_retrieved_memories_when_context_missing() -> None:
    """answer_context 缺失时应拼接 retrieved_memories 的公开 content。"""

    legacy = RecordingLegacyProvider(
        metadata={
            "retrieved_memories": [
                {"content": "第一条记忆", "score": 0.9},
                {"content": "第二条记忆", "score": 0.8},
            ]
        }
    )
    bridge = LegacyProviderBridge(legacy)

    result = bridge.retrieve(_query())

    assert result.formatted_memory == "第一条记忆\n第二条记忆"


def test_bridge_uses_nonblank_sentinel_and_warning_when_memory_empty() -> None:
    """旧 provider 未暴露 memory context 时只能使用非空 sentinel。"""

    legacy = RecordingLegacyProvider(metadata={"retrieved_memories": []})
    bridge = LegacyProviderBridge(legacy)

    result = bridge.retrieve(_query())

    assert result.formatted_memory == BRIDGE_EMPTY_MEMORY_SENTINEL
    assert result.metadata["bridge_warning"] == "legacy_provider_exposed_no_memory_context"

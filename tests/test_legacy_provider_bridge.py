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
from tests.fake_corpus import build_multimodal_consecutive_speaker_conversation


class RecordingLegacyProvider(BaseMemoryProvider):
    """记录旧接口调用并返回指定 retrieval metadata 的 fake provider。"""

    def __init__(self, metadata: dict[str, object]):
        """保存 retrieval metadata 并初始化调用记录。"""

        self.metadata = metadata
        self.added_conversation_ids: list[str] = []
        self.added_session_ids: list[list[str]] = []
        self.added_conversations: list[object] = []
        self.retrieved_questions: list[Question] = []

    def add(self, conversation):
        """记录兼容桥重建出的旧 Conversation。"""

        self.added_conversation_ids.append(conversation.conversation_id)
        self.added_session_ids.append(
            [session.session_id for session in conversation.sessions]
        )
        self.added_conversations.append(conversation)
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

def test_bridge_restores_original_content_without_baked_caption() -> None:
    """桥接重建的 Turn 必须还原原始 content，防止旧 adapter 二次拼接 caption。"""

    from memory_benchmark.core.entities import Conversation, ImageRef, Session, Turn
    from memory_benchmark.core.provider_protocol import ConversationBatch as _CB
    from memory_benchmark.runners.event_stream import (
        GranularityAggregator,
        build_turn_events,
    )

    conversation = Conversation(
        conversation_id="conv-img",
        sessions=[
            Session(
                session_id="s1",
                session_time="2026-07-06T00:00:00Z",
                turns=[
                    Turn(
                        turn_id="d1",
                        speaker="Alice",
                        content="看这张照片",
                        normalized_role="user",
                        images=[ImageRef(caption="a bowl with flowers")],
                    )
                ],
            )
        ],
        questions=[],
        gold_answers={},
        metadata={},
    )
    events = tuple(build_turn_events(conversation, "run-1_conv-img"))
    assert "(image description: a bowl with flowers)" in events[0].content

    units = tuple(
        GranularityAggregator("conversation").aggregate(
            events, isolation_key="run-1_conv-img"
        )
    )
    batch = next(unit for unit in units if isinstance(unit, _CB))
    legacy = RecordingLegacyProvider(metadata={"answer_context": "记忆上下文"})
    LegacyProviderBridge(legacy).ingest(batch)

    rebuilt_turn = legacy.added_conversations[0].sessions[0].turns[0]
    assert rebuilt_turn.content == "看这张照片"
    assert [image.caption for image in rebuilt_turn.images] == [
        "a bowl with flowers"
    ]


def test_bridge_accepts_shared_fake_corpus_with_caption_and_repeated_speaker() -> None:
    """共享 fake 语料必须覆盖图片 caption 与连续同 speaker 的桥接路径。"""

    from memory_benchmark.core.provider_protocol import ConversationBatch as _CB
    from memory_benchmark.runners.event_stream import (
        GranularityAggregator,
        build_turn_events,
    )

    conversation = build_multimodal_consecutive_speaker_conversation()
    events = tuple(build_turn_events(conversation, "run-1_conv-rich"))
    units = tuple(
        GranularityAggregator("conversation").aggregate(
            events,
            isolation_key="run-1_conv-rich",
        )
    )
    batch = next(unit for unit in units if isinstance(unit, _CB))
    legacy = RecordingLegacyProvider(metadata={"answer_context": "记忆上下文"})

    LegacyProviderBridge(legacy).ingest(batch)

    rebuilt_turns = legacy.added_conversations[0].sessions[0].turns
    assert [turn.speaker for turn in rebuilt_turns] == ["Alice", "Alice", "Bob"]
    assert rebuilt_turns[0].content == "我拍了一张花瓶照片"
    assert rebuilt_turns[0].images[0].caption == "a blue vase on a table"

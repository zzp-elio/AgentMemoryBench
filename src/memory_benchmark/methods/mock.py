"""conversation-QA 测试用 mock memory system/provider。

本模块提供同步、无外部依赖的 mock method，用于 runner 单元测试和后续 smoke test。
`MockMemorySystem` 保留 legacy `get_answer()` 路径；`MockMemoryProvider` 用于新的
retrieve-first 路径。
"""

from __future__ import annotations

from collections.abc import Mapping

from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    Conversation,
    PromptMessage,
    Question,
)
from memory_benchmark.core.interfaces import BaseMemorySystem
from memory_benchmark.core.provider_protocol import (
    ConsumeGranularity,
    ConversationBatch,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievedItem,
    RetrievalQuery,
    RetrievalResult,
    SessionBatch,
    SessionMemoryReport,
    SessionRef,
    TurnEvent,
    TurnPair,
    UnitRef,
)


class MockMemoryProvider(MemoryProvider):
    """按 question_id 返回固定 retrieval context 的 mock provider。

    字段:
        context_by_question_id: 测试配置的检索上下文映射。
        default_context: 未配置 question_id 时返回的兜底上下文。
        added_conversation_ids: 已通过 add 写入的 conversation id，供测试检查。
    """

    consume_granularity: ConsumeGranularity = "conversation"
    session_memory_report = True
    provenance_granularity = "turn"

    def __init__(
        self,
        context_by_question_id: Mapping[str, str] | None = None,
        default_context: str | None = None,
        consume_granularity: ConsumeGranularity = "conversation",
    ) -> None:
        """初始化 mock 检索上下文表。

        输入:
            context_by_question_id: question_id 到 formatted context 的映射。
            default_context: 未配置 question_id 时返回的兜底上下文；None 时按
                question_id 生成可诊断文本。
            consume_granularity: v3 runner 投递给 mock provider 的 ingest 粒度。

        输出:
            None。实例会记录后续 add 调用中的 conversation id。
        """

        if consume_granularity not in {"turn", "pair", "session", "conversation"}:
            raise ValueError(
                "consume_granularity must be one of: turn, pair, session, conversation"
            )
        self.context_by_question_id = dict(context_by_question_id or {})
        self.default_context = default_context
        self.consume_granularity = consume_granularity
        self.added_conversation_ids: list[str] = []
        self.ingested_units: list[str] = []
        self.ended_sessions: list[SessionRef] = []
        self.ended_conversations: list[UnitRef] = []
        self._turn_ids_by_conversation: dict[str, list[str]] = {}

    def add(self, conversation: Conversation) -> AddResult:
        """兼容旧测试的单 conversation 写入入口。

        输入:
            conversation: runner 传入的公开 Conversation，预期不含 gold_answers。

        输出:
            AddResult: 本次写入的 conversation id。
        """

        self.added_conversation_ids.append(conversation.conversation_id)
        self._turn_ids_by_conversation[conversation.conversation_id] = [
            turn.turn_id
            for session in conversation.sessions
            for turn in session.turns
            if turn.turn_id
        ]
        return AddResult(
            conversation_ids=[conversation.conversation_id],
            metadata={"method": "mock"},
        )

    def ingest(self, unit: IngestUnit) -> IngestResult:
        """记录 v3 ingest unit，并维护 conversation 与 turn provenance。"""

        conversation_id = _unit_conversation_id(unit)
        if conversation_id is not None and conversation_id not in self.added_conversation_ids:
            self.added_conversation_ids.append(conversation_id)
        if conversation_id is not None:
            self._turn_ids_by_conversation.setdefault(conversation_id, [])
            for turn_id in _unit_turn_ids(unit):
                if turn_id not in self._turn_ids_by_conversation[conversation_id]:
                    self._turn_ids_by_conversation[conversation_id].append(turn_id)
        self.ingested_units.append(type(unit).__name__)
        if isinstance(unit, SessionBatch):
            return IngestResult(
                unit_ref=unit.ref,
                session_memories=[f"mock-session-memory:{unit.session_id}"],
                metadata={"method": "mock"},
            )
        return IngestResult(metadata={"method": "mock"})

    def end_session(self, ref: SessionRef) -> SessionMemoryReport:
        """在 session 边界返回 mock session memory report。"""

        self.ended_sessions.append(ref)
        return SessionMemoryReport(
            session_ref=ref,
            memories=[f"mock-session-memory:{ref.session_id}"],
            metadata={"method": "mock"},
        )

    def end_conversation(self, ref: UnitRef) -> None:
        """记录 conversation 边界。"""

        self.ended_conversations.append(ref)

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回固定 v3 retrieval result 或兜底 mock prompt。

        输入:
            query: runner 传入的公开 RetrievalQuery，不能包含标准答案或 evidence。

        输出:
            RetrievalResult: 可直接转换为 answer reader 输入的检索结果。
        """

        question = query.source_question
        question_id = question.question_id if question is not None else query.query_text
        conversation_id = (
            question.conversation_id
            if question is not None
            else _conversation_id_from_isolation_key(query.isolation_key)
        )
        context = self.context_by_question_id.get(question_id)
        if context is None:
            context = self.default_context or f"mock-context-for:{question_id}"
        source_turn_ids = tuple(self._turn_ids_by_conversation.get(conversation_id, ()))
        return RetrievalResult(
            formatted_memory=context,
            prompt_messages=(PromptMessage(role="user", content=context),),
            items=(
                RetrievedItem(
                    item_id=f"{question_id}:mock-hit",
                    content=context,
                    score=1.0,
                    timestamp=None,
                    source_turn_ids=source_turn_ids,
                    metadata={"method": "mock"},
                ),
            ),
            metadata={"method": "mock", "answer_context": context},
        )


def _unit_conversation_id(unit: IngestUnit) -> str | None:
    """从 v3 ingest unit 中提取 conversation id。"""

    for event in _unit_events(unit):
        conversation_id = event.metadata.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id:
            return conversation_id
    return None


def _unit_turn_ids(unit: IngestUnit) -> list[str]:
    """从 v3 ingest unit 中提取 turn ids。"""

    return [event.turn_id for event in _unit_events(unit) if event.turn_id]


def _unit_events(unit: IngestUnit) -> tuple[TurnEvent, ...]:
    """把任意 ingest unit 展开成 turn events。"""

    if isinstance(unit, TurnEvent):
        return (unit,)
    if isinstance(unit, TurnPair):
        return unit.turns
    if isinstance(unit, SessionBatch):
        return unit.events
    if isinstance(unit, ConversationBatch):
        return unit.events
    return ()


def _conversation_id_from_isolation_key(isolation_key: str) -> str:
    """从默认 isolation_key 中提取 conversation id fallback。"""

    if "_" not in isolation_key:
        return isolation_key
    return isolation_key.split("_", 1)[1]


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


__all__ = ["MockMemoryProvider", "MockMemorySystem"]

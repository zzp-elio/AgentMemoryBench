"""provider v3 事件流生成与粒度聚合。"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Literal, TypeAlias

from memory_benchmark.core import Conversation, Turn
from memory_benchmark.core.provider_protocol import (
    ConversationBatch,
    IngestUnit,
    SessionBatch,
    SessionRef,
    TurnEvent,
    TurnPair,
    UnitRef,
)

StreamSignal: TypeAlias = IngestUnit | SessionRef | UnitRef
ConsumeGranularity: TypeAlias = Literal["turn", "pair", "session", "conversation"]


def default_isolation_key(run_id: str, conversation_id: str) -> str:
    """按默认规则发放隔离键。"""

    return f"{run_id}_{conversation_id}"


def build_turn_events(
    conversation: Conversation,
    isolation_key: str,
) -> Iterator[TurnEvent]:
    """把公开 Conversation 展开成规范 TurnEvent 流。"""

    for session_index, session in enumerate(conversation.sessions):
        for turn_index, turn in enumerate(session.turns):
            yield TurnEvent(
                role=turn.normalized_role or turn.speaker,
                speaker_name=turn.speaker,
                content=_turn_content(turn),
                timestamp=turn.turn_time or session.session_time,
                isolation_key=isolation_key,
                session_id=session.session_id,
                turn_id=_stable_turn_id(turn, session_index, turn_index),
                metadata={
                    "conversation_id": conversation.conversation_id,
                    "session_index": session_index,
                    "turn_index": turn_index,
                    "original_turn_id": turn.turn_id,
                },
            )


class GranularityAggregator:
    """把 turn 级事件流聚合成 provider 声明的消费粒度。"""

    _VALID_GRANULARITIES = {"turn", "pair", "session", "conversation"}

    def __init__(self, consume_granularity: ConsumeGranularity):
        """创建指定消费粒度的聚合器。"""

        if consume_granularity not in self._VALID_GRANULARITIES:
            raise ValueError(
                "consume_granularity must be one of: turn, pair, session, conversation"
            )
        self.consume_granularity = consume_granularity

    def aggregate(
        self,
        events: Iterable[TurnEvent],
        isolation_key: str | None = None,
    ) -> Iterator[StreamSignal]:
        """产出 ingest unit 与 session/conversation 边界信号。"""

        event_tuple = tuple(events)
        effective_isolation_key = isolation_key or _infer_isolation_key(event_tuple)
        if not event_tuple:
            if effective_isolation_key is not None:
                yield UnitRef(effective_isolation_key)
            return

        if self.consume_granularity == "turn":
            yield from self._aggregate_turns(event_tuple)
        elif self.consume_granularity == "pair":
            yield from self._aggregate_pairs(event_tuple)
        elif self.consume_granularity == "session":
            yield from self._aggregate_sessions(event_tuple)
        else:
            yield from self._aggregate_conversation(event_tuple)

        yield UnitRef(event_tuple[0].isolation_key)

    def _aggregate_turns(self, events: tuple[TurnEvent, ...]) -> Iterator[StreamSignal]:
        """按 turn 粒度产出事件和 session 边界。"""

        for session_events in _group_by_session(events):
            for event in session_events:
                yield event
            yield _session_ref(session_events)

    def _aggregate_pairs(self, events: tuple[TurnEvent, ...]) -> Iterator[StreamSignal]:
        """按 pair 粒度产出事件和 session 边界。"""

        for session_events in _group_by_session(events):
            index = 0
            while index < len(session_events):
                first = session_events[index]
                second = session_events[index + 1] if index + 1 < len(session_events) else None
                metadata = {"pair_index": index // 2}
                if second is None:
                    metadata["dangling"] = True
                yield TurnPair(first=first, second=second, metadata=metadata)
                index += 2
            yield _session_ref(session_events)

    def _aggregate_sessions(self, events: tuple[TurnEvent, ...]) -> Iterator[StreamSignal]:
        """按 session 粒度产出 SessionBatch 和 session 边界。"""

        for session_events in _group_by_session(events):
            batch = _session_batch(session_events)
            yield batch
            yield batch.ref

    def _aggregate_conversation(self, events: tuple[TurnEvent, ...]) -> Iterator[StreamSignal]:
        """按 conversation 粒度产出 ConversationBatch 和 session 边界。"""

        sessions = tuple(_session_batch(session_events) for session_events in _group_by_session(events))
        yield ConversationBatch(isolation_key=events[0].isolation_key, sessions=sessions)
        for session in sessions:
            yield session.ref


def _turn_content(turn: Turn) -> str:
    """生成包含图片 caption fallback 的 turn 文本。"""

    content = turn.content
    captions = [image.caption for image in turn.images if image.caption]
    if captions:
        caption_text = "; ".join(captions)
        if content:
            return f"{content} (image description: {caption_text})"
        return f"(image description: {caption_text})"
    return content


def _stable_turn_id(turn: Turn, session_index: int, turn_index: int) -> str:
    """返回 benchmark 稳定 turn id 或顺序 fallback。"""

    if turn.turn_id.strip():
        return turn.turn_id
    return f"s{session_index}t{turn_index}"


def _infer_isolation_key(events: tuple[TurnEvent, ...]) -> str | None:
    """从事件流推断唯一 isolation_key。"""

    if not events:
        return None
    isolation_key = events[0].isolation_key
    for event in events:
        if event.isolation_key != isolation_key:
            raise ValueError("all TurnEvent objects must share isolation_key")
    return isolation_key


def _group_by_session(events: tuple[TurnEvent, ...]) -> Iterator[tuple[TurnEvent, ...]]:
    """按连续 session_id 分组事件。"""

    _infer_isolation_key(events)
    current: list[TurnEvent] = []
    current_session_id: str | None = None
    for event in events:
        if not current:
            current = [event]
            current_session_id = event.session_id
            continue
        if event.session_id == current_session_id:
            current.append(event)
            continue
        yield tuple(current)
        current = [event]
        current_session_id = event.session_id
    if current:
        yield tuple(current)


def _session_ref(events: tuple[TurnEvent, ...]) -> SessionRef:
    """从同一 session 的事件生成 SessionRef。"""

    return SessionRef(isolation_key=events[0].isolation_key, session_id=events[0].session_id)


def _session_batch(events: tuple[TurnEvent, ...]) -> SessionBatch:
    """从同一 session 的事件生成 SessionBatch。"""

    session_time = events[0].timestamp
    return SessionBatch(
        isolation_key=events[0].isolation_key,
        session_id=events[0].session_id,
        events=events,
        session_time=session_time,
    )


__all__ = [
    "ConsumeGranularity",
    "GranularityAggregator",
    "StreamSignal",
    "build_turn_events",
    "default_isolation_key",
]

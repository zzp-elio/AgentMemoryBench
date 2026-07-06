"""测试 v3 事件流生成与粒度聚合。"""

from __future__ import annotations

import pytest

from memory_benchmark.core import Conversation, Session, Turn
from memory_benchmark.core.provider_protocol import (
    ConversationBatch,
    SessionBatch,
    SessionRef,
    TurnEvent,
    TurnPair,
    UnitRef,
)
from memory_benchmark.runners.event_stream import (
    GranularityAggregator,
    build_turn_events,
    default_isolation_key,
)


def _conversation() -> Conversation:
    """构造包含多 session、落单 turn 和时间继承的 conversation。"""

    return Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="s1",
                session_time="2026-07-06",
                turns=[
                    Turn("a", "Alice", "hi", normalized_role="user"),
                    Turn("b", "Bob", "hello", normalized_role="assistant", turn_time="2026-07-06T10:01"),
                ],
            ),
            Session(
                session_id="s2",
                session_time="2026-07-07",
                turns=[
                    Turn("", "Alice", "single", normalized_role="user"),
                ],
            ),
        ],
    )


def _events() -> tuple[TurnEvent, ...]:
    """返回测试 conversation 的规范事件流。"""

    return tuple(build_turn_events(_conversation(), isolation_key="run_conv-1"))


def _turn_ids(signals: tuple[object, ...]) -> list[str]:
    """从聚合输出中还原全部 turn_id。"""

    turn_ids: list[str] = []
    for signal in signals:
        if isinstance(signal, TurnEvent):
            turn_ids.append(signal.turn_id)
        elif isinstance(signal, TurnPair):
            turn_ids.extend(event.turn_id for event in signal.turns)
        elif isinstance(signal, SessionBatch):
            turn_ids.extend(event.turn_id for event in signal.events)
        elif isinstance(signal, ConversationBatch):
            turn_ids.extend(event.turn_id for event in signal.events)
    return turn_ids


def test_default_isolation_key_uses_run_and_conversation_id() -> None:
    """默认隔离键必须按 run_id + conversation_id 发放。"""

    assert default_isolation_key("run-1", "conv-1") == "run-1_conv-1"


def test_build_turn_events_expands_sessions_in_order() -> None:
    """build_turn_events 必须按 session/turn 顺序展开。"""

    events = _events()

    assert [event.turn_id for event in events] == ["a", "b", "s1t0"]
    assert [event.session_id for event in events] == ["s1", "s1", "s2"]
    assert [event.content for event in events] == ["hi", "hello", "single"]


def test_build_turn_events_inherits_session_time_when_turn_time_missing() -> None:
    """turn_time 缺失时必须继承 session_time。"""

    events = _events()

    assert events[0].timestamp == "2026-07-06"
    assert events[1].timestamp == "2026-07-06T10:01"
    assert events[2].timestamp == "2026-07-07"


def test_build_turn_events_preserves_public_boundary_metadata() -> None:
    """事件 metadata 必须保留公开边界信息。"""

    event = _events()[2]

    assert event.metadata["conversation_id"] == "conv-1"
    assert event.metadata["session_index"] == 1
    assert event.metadata["turn_index"] == 0
    assert event.metadata["original_turn_id"] == ""


@pytest.mark.parametrize("granularity", ["turn", "pair", "session", "conversation"])
def test_aggregator_preserves_turn_content_for_every_granularity(granularity: str) -> None:
    """四种粒度聚合后都必须能无损还原 turn 集合。"""

    events = _events()
    signals = tuple(GranularityAggregator(granularity).aggregate(events))

    assert _turn_ids(signals) == [event.turn_id for event in events]


def test_turn_granularity_emits_turns_then_session_and_conversation_boundaries() -> None:
    """turn 粒度必须在每个 session 后产出边界信号。"""

    signals = tuple(GranularityAggregator("turn").aggregate(_events()))

    assert [type(signal).__name__ for signal in signals] == [
        "TurnEvent",
        "TurnEvent",
        "SessionRef",
        "TurnEvent",
        "SessionRef",
        "UnitRef",
    ]
    assert signals[2] == SessionRef("run_conv-1", "s1")
    assert signals[-1] == UnitRef("run_conv-1")


def test_pair_granularity_pairs_adjacent_user_assistant_and_marks_dangling() -> None:
    """pair 粒度必须配对相邻 turn，并把落单 turn 标记为 dangling。"""

    signals = tuple(GranularityAggregator("pair").aggregate(_events()))
    pairs = [signal for signal in signals if isinstance(signal, TurnPair)]

    assert [tuple(event.turn_id for event in pair.turns) for pair in pairs] == [
        ("a", "b"),
        ("s1t0",),
    ]
    assert pairs[1].metadata["dangling"] is True


def test_session_granularity_emits_one_batch_per_session() -> None:
    """session 粒度必须按 session 产出 SessionBatch。"""

    signals = tuple(GranularityAggregator("session").aggregate(_events()))
    batches = [signal for signal in signals if isinstance(signal, SessionBatch)]

    assert [batch.session_id for batch in batches] == ["s1", "s2"]
    assert [[event.turn_id for event in batch.events] for batch in batches] == [["a", "b"], ["s1t0"]]


def test_conversation_granularity_emits_single_conversation_batch() -> None:
    """conversation 粒度必须产出单个 ConversationBatch。"""

    signals = tuple(GranularityAggregator("conversation").aggregate(_events()))
    batches = [signal for signal in signals if isinstance(signal, ConversationBatch)]

    assert len(batches) == 1
    assert [session.session_id for session in batches[0].sessions] == ["s1", "s2"]
    assert [event.turn_id for event in batches[0].events] == ["a", "b", "s1t0"]


def test_single_session_stream_gets_one_session_boundary() -> None:
    """单 session 事件流只能产出一个 session boundary。"""

    conversation = Conversation(
        conversation_id="conv-2",
        sessions=[Session(session_id="only", turns=[Turn("t1", "Alice", "hi")])],
    )
    events = tuple(build_turn_events(conversation, isolation_key="run_conv-2"))
    signals = tuple(GranularityAggregator("turn").aggregate(events))

    assert [signal for signal in signals if isinstance(signal, SessionRef)] == [
        SessionRef("run_conv-2", "only")
    ]


def test_empty_event_stream_with_explicit_isolation_gets_conversation_boundary() -> None:
    """空事件流在显式 isolation_key 下仍应产出 conversation 边界。"""

    signals = tuple(GranularityAggregator("turn").aggregate((), isolation_key="run_empty"))

    assert signals == (UnitRef("run_empty"),)


def test_aggregator_rejects_unknown_granularity() -> None:
    """聚合器必须拒绝未知 consume_granularity。"""

    with pytest.raises(ValueError, match="consume_granularity"):
        GranularityAggregator("document")  # type: ignore[arg-type]

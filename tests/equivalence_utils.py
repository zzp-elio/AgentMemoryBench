"""adapter 原生化等价性测试工具。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from memory_benchmark.core import Conversation, Question
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.core.provider_bridge import LegacyProviderBridge
from memory_benchmark.core.provider_protocol import (
    ConversationBatch,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
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


@dataclass(frozen=True)
class SequenceRunResult:
    """一次等价性驱动后的调用序列快照。"""

    calls: tuple[dict[str, object], ...]


def run_bridge_sequence(
    *,
    provider: BaseMemoryProvider,
    conversation: Conversation,
    question: Question,
    run_id: str,
    snapshot_calls: Callable[[BaseMemoryProvider], Sequence[dict[str, object]]] | None = None,
) -> SequenceRunResult:
    """通过 LegacyProviderBridge 驱动旧 provider 并返回调用序列。"""

    bridge = LegacyProviderBridge(provider)
    batch = _conversation_batch(conversation=conversation, run_id=run_id)
    bridge.ingest(batch)
    bridge.retrieve(_retrieval_query(question=question, run_id=run_id))
    return SequenceRunResult(
        calls=tuple(_snapshot_calls(provider, snapshot_calls)),
    )


def run_native_sequence(
    *,
    provider: MemoryProvider,
    conversation: Conversation,
    question: Question,
    run_id: str,
    snapshot_calls: Callable[[MemoryProvider], Sequence[dict[str, object]]] | None = None,
) -> SequenceRunResult:
    """通过 v3 事件流路径驱动原生 provider 并返回调用序列。"""

    isolation_key = default_isolation_key(run_id, conversation.conversation_id)
    events = tuple(build_turn_events(conversation, isolation_key))
    signals = GranularityAggregator(provider.consume_granularity).aggregate(
        events,
        isolation_key=isolation_key,
    )
    for signal in signals:
        if _is_ingest_unit(signal):
            provider.ingest(signal)
        elif isinstance(signal, SessionRef):
            provider.end_session(signal)
        elif isinstance(signal, UnitRef):
            provider.end_conversation(signal)
    provider.retrieve(_retrieval_query(question=question, run_id=run_id))
    return SequenceRunResult(
        calls=tuple(_snapshot_calls(provider, snapshot_calls)),
    )


def _conversation_batch(
    *,
    conversation: Conversation,
    run_id: str,
) -> ConversationBatch:
    """把公开 conversation 转成桥接路径使用的 ConversationBatch。"""

    isolation_key = default_isolation_key(run_id, conversation.conversation_id)
    events = tuple(build_turn_events(conversation, isolation_key))
    for signal in GranularityAggregator("conversation").aggregate(
        events,
        isolation_key=isolation_key,
    ):
        if isinstance(signal, ConversationBatch):
            return signal
    raise AssertionError("conversation batch was not produced")


def _retrieval_query(*, question: Question, run_id: str) -> RetrievalQuery:
    """由公开 question 构造等价性测试用 RetrievalQuery。"""

    return RetrievalQuery(
        query_text=question.text,
        isolation_key=default_isolation_key(run_id, question.conversation_id),
        question_time=question.question_time,
        top_k=10,
        purpose="qa",
        source_question=question,
    )


def _snapshot_calls(
    provider: Any,
    snapshot_calls: Callable[[Any], Sequence[dict[str, object]]] | None,
) -> list[dict[str, object]]:
    """读取 fake provider/runtime 暴露的调用序列。"""

    if snapshot_calls is not None:
        return [dict(call) for call in snapshot_calls(provider)]
    calls = getattr(provider, "calls", None)
    if calls is None:
        raise AssertionError("provider must expose calls or snapshot_calls")
    return [dict(call) for call in calls]


def _is_ingest_unit(signal: object) -> bool:
    """判断 stream signal 是否应投递给 provider.ingest。"""

    return isinstance(
        signal,
        TurnEvent | TurnPair | SessionBatch | ConversationBatch,
    )


__all__ = ["SequenceRunResult", "run_bridge_sequence", "run_native_sequence"]

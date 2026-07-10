"""B0 method-neutral benchmark probe provider 实现。

`BenchmarkProbeProvider` 是一个假的 v3 `MemoryProvider` 实现，唯一用途是校验
benchmark/runner/registry 机制向 v3 协议发出了什么调用——正确的 ingest unit、
正确的生命周期调用顺序、正确的 `RetrievalQuery` 字段——而不是模拟任何真实
method 的记忆算法。

设计上的硬约束（对应 plan 中的显式反需求，不得因为"方便"而添加）：

- 构造参数只允许四项：消费粒度、是否产生 session report、固定 retrieve item
  上限、可选受控异常触发点。不接受 `benchmark_name`、gold answer 映射，或任何
  "返回正确答案"的入口。
- 探针只在内存中记录它收到的公开协议对象（`TurnEvent`/`TurnPair`/
  `SessionBatch`/`ConversationBatch`/`RetrievalQuery` 等），不读写网络、文件、
  数据库，也不调用任何真实 method 代码。
- `retrieve()` 返回的 `formatted_memory`/`items` 只从"已经 ingest 过的公开
  turn"确定性推导，不查看 `query_text`、`source_question` 的内容或
  metadata——这样才能证明探针无法被用来做 benchmark 专用答案注入。
- 没有 ingest 任何 turn 时，`retrieve()` 返回中性占位符
  `"No ingested public memory."`，不得借用 framework 的
  `BRIDGE_EMPTY_MEMORY_SENTINEL`（那是 legacy bridge 的专用哨兵，语义不同）。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from memory_benchmark.core.provider_protocol import (
    ConsumeGranularity,
    ConversationBatch,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    ProvenanceGranularity,
    RetrievalQuery,
    RetrievalResult,
    RetrievedItem,
    SessionBatch,
    SessionMemoryReport,
    SessionRef,
    TurnEvent,
    TurnPair,
    UnitRef,
)

_NEUTRAL_EMPTY_MEMORY = "No ingested public memory."

FailureHook: TypeAlias = Literal[
    "prepare", "ingest", "end_session", "end_conversation", "retrieve", "cleanup"
]


@dataclass(frozen=True)
class ProbeFailureTrigger:
    """声明探针在指定钩子第几次被调用时受控抛错。

    字段:
        hook: 触发失败的协议钩子名称。
        trigger_at_call_index: 0-indexed 调用序号；例如 0 表示该钩子第一次被
            调用就抛错，1 表示第二次调用才抛错。
    """

    hook: FailureHook
    trigger_at_call_index: int = 0

    def __post_init__(self) -> None:
        """校验触发点合法。"""

        valid_hooks = {
            "prepare",
            "ingest",
            "end_session",
            "end_conversation",
            "retrieve",
            "cleanup",
        }
        if self.hook not in valid_hooks:
            raise ValueError(f"hook must be one of: {sorted(valid_hooks)}")
        if self.trigger_at_call_index < 0:
            raise ValueError("trigger_at_call_index must be non-negative")


class ProbeControlledFailure(RuntimeError):
    """探针受控异常点触发时抛出的异常类型。

    用于测试 runner/CLI 在某个协议钩子失败时的隔离、重试或 resume 行为；
    异常信息只描述钩子名称与调用序号，不携带任何 benchmark 私有信息。
    """


def _flatten_turns(unit: IngestUnit) -> tuple[TurnEvent, ...]:
    """把任意 v3 ingest unit 展开成按原始顺序排列的 turn event 元组。"""

    if isinstance(unit, TurnEvent):
        return (unit,)
    if isinstance(unit, TurnPair):
        return unit.turns
    if isinstance(unit, SessionBatch):
        return unit.events
    if isinstance(unit, ConversationBatch):
        return unit.events
    raise TypeError(f"unsupported ingest unit type: {type(unit).__name__}")


def _unit_ref(unit: IngestUnit) -> SessionRef | UnitRef:
    """推导 ingest unit 对应的边界引用，供 IngestResult.unit_ref 使用。"""

    if isinstance(unit, SessionBatch):
        return unit.ref
    if isinstance(unit, ConversationBatch):
        return unit.ref
    if isinstance(unit, TurnEvent):
        return SessionRef(isolation_key=unit.isolation_key, session_id=unit.session_id)
    if isinstance(unit, TurnPair):
        return SessionRef(isolation_key=unit.isolation_key, session_id=unit.session_id)
    raise TypeError(f"unsupported ingest unit type: {type(unit).__name__}")


class BenchmarkProbeProvider(MemoryProvider):
    """method-neutral 的 v3 协议探针 provider。

    只用于校验 benchmark/runner/registry 是否忠实向 v3 协议发出预期调用；
    不实现任何真实记忆算法，不代表任何 Phase 1 method 的效果或效率。

    字段:
        consume_granularity: runner 应按此粒度向探针投递 ingest unit。
        session_memory_report: 是否在 `end_session` 产生
            `SessionMemoryReport`；关闭时 `end_session` 只返回 None，绝不
            伪造报告。
        call_log: 探针收到的协议钩子调用序列（按发生顺序，包含受控失败前
            的调用尝试），供调用顺序断言使用。
        ingested_units: 原样保存的 ingest unit 列表（保真，未做任何转换）。
        ingested_turns: 按 ingest 顺序展开的 turn event 列表，供 retrieve/
            end_session 做 provenance 查找。
        ended_sessions / ended_conversations: 已收到的边界引用。
        retrieve_queries: 原样保存的 RetrievalQuery 列表。
        cleanup_call_count: cleanup 被调用的次数。
    """

    provenance_granularity: ProvenanceGranularity = "turn"

    def __init__(
        self,
        consume_granularity: ConsumeGranularity = "conversation",
        session_memory_report: bool = False,
        retrieve_item_limit: int = 5,
        failure_trigger: ProbeFailureTrigger | None = None,
    ) -> None:
        """初始化探针内存状态。

        输入:
            consume_granularity: 声明的 ingest 消费粒度，仅允许
                turn/pair/session/conversation。
            session_memory_report: 是否在 end_session 产生 session memory
                report。
            retrieve_item_limit: retrieve 返回条目数的固定上限（正整数）。
            failure_trigger: 可选的受控异常触发点，用于测试失败隔离/resume；
                为 None 时探针永不主动抛出受控异常。

        输出:
            None。
        """

        if consume_granularity not in {"turn", "pair", "session", "conversation"}:
            raise ValueError(
                "consume_granularity must be one of: turn, pair, session, conversation"
            )
        if retrieve_item_limit <= 0:
            raise ValueError("retrieve_item_limit must be a positive integer")

        self.consume_granularity: ConsumeGranularity = consume_granularity
        self.session_memory_report = session_memory_report
        self._retrieve_item_limit = retrieve_item_limit
        self._failure_trigger = failure_trigger
        self._hook_call_counts: dict[str, int] = defaultdict(int)

        self.call_log: list[str] = []
        self.prepare_calls: list[Any] = []
        self.ingested_units: list[IngestUnit] = []
        self.ingested_turns: list[TurnEvent] = []
        self.ended_sessions: list[SessionRef] = []
        self.ended_conversations: list[UnitRef] = []
        self.retrieve_queries: list[RetrievalQuery] = []
        self.cleanup_call_count = 0

    def _maybe_fail(self, hook: FailureHook) -> None:
        """在受控触发点匹配时抛出 `ProbeControlledFailure`。"""

        call_index = self._hook_call_counts[hook]
        self._hook_call_counts[hook] = call_index + 1
        trigger = self._failure_trigger
        if (
            trigger is not None
            and trigger.hook == hook
            and trigger.trigger_at_call_index == call_index
        ):
            raise ProbeControlledFailure(
                f"benchmark probe controlled failure at hook={hook} call_index={call_index}"
            )

    def prepare(self, run_context: Any) -> None:
        """记录 prepare 调用，不做任何真实初始化。"""

        self.call_log.append("prepare")
        self._maybe_fail("prepare")
        self.prepare_calls.append(run_context)
        return None

    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """原样记录一个 ingest unit 及其展开后的 turn event。"""

        self.call_log.append("ingest")
        self._maybe_fail("ingest")

        turns = _flatten_turns(unit)
        self.ingested_units.append(unit)
        self.ingested_turns.extend(turns)

        return IngestResult(
            unit_ref=_unit_ref(unit),
            metadata={
                "probe_ingested_turn_count": len(turns),
                "probe_unit_type": type(unit).__name__,
            },
        )

    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None:
        """在 session_memory_report 开启时，只用已 ingest 的本 session turn 生成报告。"""

        self.call_log.append("end_session")
        self._maybe_fail("end_session")
        self.ended_sessions.append(ref)

        if not self.session_memory_report:
            return None

        session_turns = [
            turn
            for turn in self.ingested_turns
            if turn.isolation_key == ref.isolation_key and turn.session_id == ref.session_id
        ]
        memories = [f"turn:{turn.turn_id}:{turn.content}" for turn in session_turns]
        return SessionMemoryReport(
            session_ref=ref,
            memories=memories,
            metadata={"probe_source_turn_ids": tuple(turn.turn_id for turn in session_turns)},
        )

    def end_conversation(self, ref: UnitRef) -> None:
        """记录 conversation 边界收尾调用。"""

        self.call_log.append("end_conversation")
        self._maybe_fail("end_conversation")
        self.ended_conversations.append(ref)
        return None

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """按已 ingest 的公开 turn 返回确定性检索结果，不查看 query 文本内容。"""

        self.call_log.append("retrieve")
        self._maybe_fail("retrieve")
        self.retrieve_queries.append(query)

        matched_turns = [
            turn for turn in self.ingested_turns if turn.isolation_key == query.isolation_key
        ]
        if not matched_turns:
            return RetrievalResult(
                formatted_memory=_NEUTRAL_EMPTY_MEMORY,
                items=(),
                metadata={"probe_matched_turn_count": 0},
            )

        cap = min(self._retrieve_item_limit, query.top_k)
        selected = matched_turns[:cap]
        items = tuple(
            RetrievedItem(
                item_id=f"probe-item::{turn.turn_id}",
                content=f"{turn.speaker_name or turn.role}: {turn.content}",
                score=round(1.0 - 0.01 * rank, 4),
                timestamp=turn.timestamp,
                source_turn_ids=(turn.turn_id,),
                metadata={},
            )
            for rank, turn in enumerate(selected)
        )
        formatted_memory = "\n".join(item.content for item in items)
        return RetrievalResult(
            formatted_memory=formatted_memory,
            items=items,
            metadata={
                "probe_matched_turn_count": len(matched_turns),
                "probe_returned_item_count": len(items),
            },
        )

    def cleanup(self) -> None:
        """记录 cleanup 调用，不做任何真实资源释放。"""

        self.call_log.append("cleanup")
        self._maybe_fail("cleanup")
        self.cleanup_call_count += 1
        return None


__all__ = [
    "BenchmarkProbeProvider",
    "FailureHook",
    "ProbeControlledFailure",
    "ProbeFailureTrigger",
]

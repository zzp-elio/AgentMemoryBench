"""测试 B0 method-neutral benchmark probe provider。

本文件只验证 `BenchmarkProbeProvider` 是否忠实执行 v3 协议：正确的 ingest
payload 记录、正确的生命周期调用顺序、正确的 `RetrievalQuery` 字段回显、
可控 session report、确定性检索结果，以及不可通过 question 文本或私有标签
注入 benchmark 专用答案。探针本身不代表任何真实 method 的效果或效率。
"""

from __future__ import annotations

import pytest

from memory_benchmark.core import PromptMessage, Question
from memory_benchmark.core.provider_protocol import (
    ConsumeGranularity,
    ConversationBatch,
    RetrievalQuery,
    SessionBatch,
    SessionRef,
    TurnEvent,
    TurnPair,
    UnitRef,
)
from memory_benchmark.core.validators import validate_no_private_keys


def _turn(
    turn_id: str,
    *,
    role: str = "user",
    speaker_name: str | None = "Alice",
    content: str | None = None,
    timestamp: str | None = "2026-07-06T10:00:00",
    isolation_key: str = "conv-1",
    session_id: str | None = "s1",
    metadata: dict | None = None,
) -> TurnEvent:
    """构造测试用公开 turn event。"""

    return TurnEvent(
        role=role,
        speaker_name=speaker_name,
        content=content if content is not None else f"content-of-{turn_id}",
        timestamp=timestamp,
        isolation_key=isolation_key,
        session_id=session_id,
        turn_id=turn_id,
        metadata=metadata or {"origin": "fixture"},
    )


def _make_probe(**kwargs):
    """按需构造 BenchmarkProbeProvider，延迟 import 便于确认 RED 阶段失败原因。"""

    from memory_benchmark.audit.benchmark_probe import BenchmarkProbeProvider

    return BenchmarkProbeProvider(**kwargs)


def _query(
    *,
    query_text: str = "What does Alice like?",
    isolation_key: str = "conv-1",
    question_time: str | None = "2026-07-06T12:00:00",
    top_k: int = 10,
    purpose: str = "qa",
    source_question: Question | None = None,
) -> RetrievalQuery:
    """构造测试用公开 RetrievalQuery。"""

    return RetrievalQuery(
        query_text=query_text,
        isolation_key=isolation_key,
        question_time=question_time,
        top_k=top_k,
        purpose=purpose,
        source_question=source_question,
    )


GRANULARITIES: tuple[ConsumeGranularity, ...] = ("turn", "pair", "session", "conversation")


# ---------------------------------------------------------------------------
# 构造参数边界
# ---------------------------------------------------------------------------


def test_construction_rejects_unknown_granularity() -> None:
    """测试非法 consume_granularity 立即 fail-fast。"""

    with pytest.raises(ValueError, match="consume_granularity"):
        _make_probe(consume_granularity="paragraph")


def test_construction_rejects_non_positive_retrieve_item_limit() -> None:
    """测试 retrieve_item_limit 必须为正整数。"""

    with pytest.raises(ValueError, match="retrieve_item_limit"):
        _make_probe(retrieve_item_limit=0)


def test_construction_rejects_benchmark_name_parameter() -> None:
    """测试构造函数不接受 benchmark_name，探针必须 method/benchmark 中立。"""

    with pytest.raises(TypeError):
        _make_probe(benchmark_name="locomo")  # type: ignore[call-arg]


def test_construction_rejects_answer_injection_parameters() -> None:
    """测试构造函数不接受任何"返回正确答案"式入口。"""

    with pytest.raises(TypeError):
        _make_probe(gold_answers={"q1": "tea"})  # type: ignore[call-arg]

    with pytest.raises(TypeError):
        _make_probe(context_by_question_id={"q1": "tea"})  # type: ignore[call-arg]


def test_provenance_granularity_is_always_turn() -> None:
    """测试 provenance_granularity 固定为 turn，不随构造参数变化。"""

    for granularity in GRANULARITIES:
        probe = _make_probe(consume_granularity=granularity)
        assert probe.provenance_granularity == "turn"


# ---------------------------------------------------------------------------
# ingest payload 保真（四种粒度）
# ---------------------------------------------------------------------------


def test_ingest_records_turn_granularity_payload_verbatim() -> None:
    """测试 turn 粒度下 probe 原样记录单个 TurnEvent 的全部公开字段。"""

    probe = _make_probe(consume_granularity="turn")
    turn = _turn("t1", content="Alice likes tea.", metadata={"turn_index": 0})

    probe.ingest(turn)

    assert len(probe.ingested_units) == 1
    recorded_unit = probe.ingested_units[0]
    assert recorded_unit is turn
    assert probe.ingested_turns == [turn]
    recorded_turn = probe.ingested_turns[0]
    assert recorded_turn.turn_id == "t1"
    assert recorded_turn.role == "user"
    assert recorded_turn.speaker_name == "Alice"
    assert recorded_turn.content == "Alice likes tea."
    assert recorded_turn.timestamp == "2026-07-06T10:00:00"
    assert recorded_turn.metadata == {"turn_index": 0}


def test_ingest_records_pair_granularity_payload_verbatim() -> None:
    """测试 pair 粒度下 probe 原样记录两个 turn 及 pair metadata。"""

    probe = _make_probe(consume_granularity="pair")
    first = _turn("t1", role="user", content="Hi")
    second = _turn("t2", role="assistant", content="Hello")
    pair = TurnPair(first=first, second=second, metadata={"pair_index": 0})

    probe.ingest(pair)

    assert probe.ingested_units == [pair]
    assert probe.ingested_turns == [first, second]


def test_ingest_records_session_granularity_payload_verbatim() -> None:
    """测试 session 粒度下 probe 原样记录整批 turn 及 session ref。"""

    probe = _make_probe(consume_granularity="session")
    events = (
        _turn("t1", content="Hi"),
        _turn("t2", role="assistant", content="Hello"),
    )
    batch = SessionBatch(
        isolation_key="conv-1",
        session_id="s1",
        events=events,
        session_time="2026-07-06",
        metadata={"batch": 1},
    )

    result = probe.ingest(batch)

    assert probe.ingested_units == [batch]
    assert probe.ingested_turns == list(events)
    assert result is not None
    assert result.unit_ref == SessionRef(isolation_key="conv-1", session_id="s1")


def test_ingest_records_conversation_granularity_payload_verbatim() -> None:
    """测试 conversation 粒度下 probe 原样记录跨 session 的全部 turn。"""

    probe = _make_probe(consume_granularity="conversation")
    session_one = SessionBatch(
        isolation_key="conv-1",
        session_id="s1",
        events=(_turn("t1", content="Hi"),),
    )
    session_two = SessionBatch(
        isolation_key="conv-1",
        session_id="s2",
        events=(_turn("t2", role="assistant", content="Hello", session_id="s2"),),
    )
    batch = ConversationBatch(isolation_key="conv-1", sessions=(session_one, session_two))

    result = probe.ingest(batch)

    assert probe.ingested_units == [batch]
    assert probe.ingested_turns == [session_one.events[0], session_two.events[0]]
    assert result is not None
    assert result.unit_ref == UnitRef(isolation_key="conv-1")


# ---------------------------------------------------------------------------
# 生命周期调用顺序
# ---------------------------------------------------------------------------


def test_lifecycle_calls_are_recorded_in_strict_order() -> None:
    """测试 prepare/ingest/end_session/end_conversation/retrieve/cleanup 严格顺序。"""

    probe = _make_probe(consume_granularity="conversation")
    session = SessionBatch(
        isolation_key="conv-1",
        session_id="s1",
        events=(_turn("t1", content="Hi"),),
    )
    batch = ConversationBatch(isolation_key="conv-1", sessions=(session,))

    probe.prepare({"run_id": "r1"})
    probe.ingest(batch)
    probe.end_session(SessionRef(isolation_key="conv-1", session_id="s1"))
    probe.end_conversation(UnitRef(isolation_key="conv-1"))
    probe.retrieve(_query())
    probe.cleanup()

    assert probe.call_log == [
        "prepare",
        "ingest",
        "end_session",
        "end_conversation",
        "retrieve",
        "cleanup",
    ]


# ---------------------------------------------------------------------------
# RetrievalQuery 字段保真
# ---------------------------------------------------------------------------


def test_retrieve_records_query_fields_verbatim() -> None:
    """测试 retrieve 原样记录 isolation key、question time、top_k、purpose。"""

    probe = _make_probe(consume_granularity="conversation")
    question = Question(
        question_id="q1",
        conversation_id="conv-1",
        text="What does Alice like?",
    )
    query = _query(
        isolation_key="conv-1",
        question_time="2026-07-06T12:00:00",
        top_k=7,
        purpose="qa",
        source_question=question,
    )

    probe.retrieve(query)

    assert len(probe.retrieve_queries) == 1
    recorded = probe.retrieve_queries[0]
    assert recorded is query
    assert recorded.isolation_key == "conv-1"
    assert recorded.question_time == "2026-07-06T12:00:00"
    assert recorded.top_k == 7
    assert recorded.purpose == "qa"
    assert recorded.source_question is question


# ---------------------------------------------------------------------------
# 私有数据边界
# ---------------------------------------------------------------------------


def test_ingest_and_retrieve_results_contain_no_private_keys() -> None:
    """测试 ingest/retrieve 结果的 metadata 不含 answer/gold/evidence/judge_label。"""

    probe = _make_probe(consume_granularity="turn")
    turn = _turn("t1", content="Alice likes tea.")

    ingest_result = probe.ingest(turn)
    assert ingest_result is not None
    validate_no_private_keys(ingest_result.metadata)

    retrieval = probe.retrieve(_query())
    validate_no_private_keys(retrieval.metadata)
    for item in retrieval.items or ():
        validate_no_private_keys(item.metadata)


# ---------------------------------------------------------------------------
# SessionMemoryReport 可选生成
# ---------------------------------------------------------------------------


def test_end_session_returns_none_when_report_disabled() -> None:
    """测试关闭 session report 时 end_session 不得伪造报告。"""

    probe = _make_probe(consume_granularity="session", session_memory_report=False)
    batch = SessionBatch(
        isolation_key="conv-1",
        session_id="s1",
        events=(_turn("t1", content="Hi"),),
    )
    probe.ingest(batch)

    report = probe.end_session(SessionRef(isolation_key="conv-1", session_id="s1"))

    assert report is None


def test_end_session_report_reflects_only_ingested_turns_when_enabled() -> None:
    """测试开启 session report 时内容只来自本 session 已 ingest 的 turn，不额外编造。"""

    probe = _make_probe(consume_granularity="session", session_memory_report=True)
    events = (
        _turn("t1", content="Alice likes tea."),
        _turn("t2", role="assistant", content="Noted."),
    )
    batch = SessionBatch(isolation_key="conv-1", session_id="s1", events=events)
    probe.ingest(batch)

    report = probe.end_session(SessionRef(isolation_key="conv-1", session_id="s1"))

    assert report is not None
    assert report.session_ref == SessionRef(isolation_key="conv-1", session_id="s1")
    assert len(report.memories) == 2
    combined = "\n".join(report.memories)
    assert "t1" in combined
    assert "t2" in combined
    assert "Alice likes tea." in combined
    assert "Noted." in combined
    validate_no_private_keys(report.metadata)


def test_end_session_report_does_not_include_other_sessions_turns() -> None:
    """测试 session report 不得混入其他 session 的 turn。"""

    probe = _make_probe(consume_granularity="session", session_memory_report=True)
    batch_one = SessionBatch(
        isolation_key="conv-1", session_id="s1", events=(_turn("t1", content="Hi"),)
    )
    batch_two = SessionBatch(
        isolation_key="conv-1",
        session_id="s2",
        events=(_turn("t2", role="assistant", content="Hello", session_id="s2"),),
    )
    probe.ingest(batch_one)
    probe.ingest(batch_two)

    report = probe.end_session(SessionRef(isolation_key="conv-1", session_id="s1"))

    assert report is not None
    combined = "\n".join(report.memories)
    assert "t1" in combined
    assert "t2" not in combined


# ---------------------------------------------------------------------------
# 检索结果确定性与 provenance
# ---------------------------------------------------------------------------


def test_retrieve_returns_neutral_placeholder_when_nothing_ingested() -> None:
    """测试没有 ingest 任何 turn 时，retrieve 返回中性占位符，而非 framework sentinel。"""

    probe = _make_probe(consume_granularity="conversation")

    result = probe.retrieve(_query(isolation_key="conv-empty"))

    assert result.formatted_memory == "No ingested public memory."
    assert result.items == ()
    assert result.evidence is not None
    assert result.evidence.semantic_provenance.status == "valid"
    assert result.evidence.provenance_granularity == "turn"
    assert result.evidence.stable_ranking.status == "valid"
    assert result.evidence.semantic_provenance.reason_code is None
    assert result.evidence.stable_ranking.reason_code is None


def test_retrieve_returns_deterministic_ordered_items_referencing_ingested_turns() -> None:
    """测试 retrieve 返回确定性、非空、有序的 RetrievedItem，且 source_turn_ids 只来自已 ingest 的 turn。"""

    probe = _make_probe(consume_granularity="turn", retrieve_item_limit=5)
    turns = [_turn(f"t{i}", content=f"fact-{i}") for i in range(1, 4)]
    for turn in turns:
        probe.ingest(turn)

    result_a = probe.retrieve(_query())
    result_b = probe.retrieve(_query())

    assert result_a.formatted_memory
    assert result_a.formatted_memory == result_b.formatted_memory
    assert result_a.items is not None
    assert len(result_a.items) == 3
    ingested_ids = {turn.turn_id for turn in turns}
    ordered_source_ids = [item.source_turn_ids for item in result_a.items]
    assert ordered_source_ids == [("t1",), ("t2",), ("t3",)]
    assert result_a.evidence is not None
    assert result_a.evidence.semantic_provenance.status == "valid"
    assert result_a.evidence.provenance_granularity == "turn"
    assert result_a.evidence.stable_ranking.status == "valid"
    assert result_a.evidence.semantic_provenance.reason is None
    assert result_a.evidence.stable_ranking.reason is None
    for item in result_a.items:
        assert set(item.source_turn_ids) <= ingested_ids


def test_retrieve_item_count_capped_by_constructor_limit() -> None:
    """测试 retrieve 返回条数受构造时固定上限约束。"""

    probe = _make_probe(consume_granularity="turn", retrieve_item_limit=2)
    for i in range(1, 6):
        probe.ingest(_turn(f"t{i}", content=f"fact-{i}"))

    result = probe.retrieve(_query(top_k=10))

    assert result.items is not None
    assert len(result.items) == 2


def test_retrieve_respects_query_top_k_within_constructor_limit() -> None:
    """测试 retrieve 条数同时不超过 query.top_k。"""

    probe = _make_probe(consume_granularity="turn", retrieve_item_limit=5)
    for i in range(1, 4):
        probe.ingest(_turn(f"t{i}", content=f"fact-{i}"))

    result = probe.retrieve(_query(top_k=1))

    assert result.items is not None
    assert len(result.items) == 1


def test_retrieve_only_returns_items_for_matching_isolation_key() -> None:
    """测试 retrieve 不跨 isolation_key 泄漏其它 conversation 的记忆。"""

    probe = _make_probe(consume_granularity="turn")
    probe.ingest(_turn("t1", isolation_key="conv-1", content="conv-1 fact"))
    probe.ingest(_turn("t2", isolation_key="conv-2", content="conv-2 fact"))

    result = probe.retrieve(_query(isolation_key="conv-1"))

    assert result.items is not None
    assert [item.source_turn_ids for item in result.items] == [("t1",)]


# ---------------------------------------------------------------------------
# 不能通过 question 文本或私有标签注入答案
# ---------------------------------------------------------------------------


def test_retrieve_ignores_question_text_content_for_memory_selection() -> None:
    """测试 formatted_memory 不随 question 文本变化，防止 benchmark 专用答案注入。"""

    probe = _make_probe(consume_granularity="turn")
    probe.ingest(_turn("t1", content="Alice likes tea."))

    result_one = probe.retrieve(_query(query_text="What does Alice like?"))
    result_two = probe.retrieve(_query(query_text="totally unrelated question text"))

    assert result_one.formatted_memory == result_two.formatted_memory
    assert result_one.items == result_two.items


def test_retrieve_ignores_source_question_metadata_for_memory_selection() -> None:
    """测试 formatted_memory 不随 source_question 的 category/metadata 变化。"""

    probe = _make_probe(consume_granularity="turn")
    probe.ingest(_turn("t1", content="Alice likes tea."))

    question_a = Question(
        question_id="q1", conversation_id="conv-1", text="Q?", category="1"
    )
    question_b = Question(
        question_id="q2", conversation_id="conv-1", text="Q?", category="5"
    )

    result_a = probe.retrieve(_query(source_question=question_a))
    result_b = probe.retrieve(_query(source_question=question_b))

    assert result_a.formatted_memory == result_b.formatted_memory


# ---------------------------------------------------------------------------
# 受控异常点
# ---------------------------------------------------------------------------


def test_failure_trigger_raises_at_configured_call_index() -> None:
    """测试受控异常点能让指定钩子在第 N 次调用时确定性抛错。"""

    from memory_benchmark.audit.benchmark_probe import ProbeControlledFailure, ProbeFailureTrigger

    probe = _make_probe(
        consume_granularity="turn",
        failure_trigger=ProbeFailureTrigger(hook="ingest", trigger_at_call_index=1),
    )

    probe.ingest(_turn("t1", content="ok"))
    with pytest.raises(ProbeControlledFailure):
        probe.ingest(_turn("t2", content="boom"))


def test_failure_trigger_only_affects_configured_hook() -> None:
    """测试受控异常点只影响声明的钩子，不影响其他钩子。"""

    from memory_benchmark.audit.benchmark_probe import ProbeFailureTrigger

    probe = _make_probe(
        consume_granularity="turn",
        failure_trigger=ProbeFailureTrigger(hook="retrieve", trigger_at_call_index=0),
    )

    probe.ingest(_turn("t1", content="ok"))
    probe.prepare({"run_id": "r1"})
    probe.end_conversation(UnitRef(isolation_key="conv-1"))
    probe.cleanup()


# ---------------------------------------------------------------------------
# PromptMessage 未被探针错误使用（防御性回归）
# ---------------------------------------------------------------------------


def test_retrieval_result_has_no_native_prompt_messages_by_default() -> None:
    """测试探针不主动构造 native prompt_messages，只提供 formatted_memory/items。"""

    probe = _make_probe(consume_granularity="turn")
    probe.ingest(_turn("t1", content="Alice likes tea."))

    result = probe.retrieve(_query())

    assert result.prompt_messages is None
    assert isinstance(result.formatted_memory, str)
    assert not isinstance(result.formatted_memory, PromptMessage)

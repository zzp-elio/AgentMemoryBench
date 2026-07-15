"""测试 v3 provider 协议实体与能力声明。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass

import pytest

from memory_benchmark.core import PromptMessage, Question
from memory_benchmark.core.exceptions import DataLeakageError
from memory_benchmark.core.provider_protocol import (
    ConversationBatch,
    EvidenceAssertion,
    IngestResult,
    MemoryProvider,
    RetrievalEvidence,
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
from memory_benchmark.core.validators import validate_no_private_keys


def _turn(turn_id: str = "t1", role: str = "user", content: str = "hello") -> TurnEvent:
    """构造测试用公开 turn event。"""

    return TurnEvent(
        role=role,
        speaker_name="Alice",
        content=content,
        timestamp="2026-07-06T10:00:00",
        isolation_key="run_conv",
        session_id="s1",
        turn_id=turn_id,
        metadata={"source": "fixture"},
    )


def test_turn_event_is_frozen_dataclass() -> None:
    """TurnEvent 必须是不可变 dataclass。"""

    event = _turn()

    assert is_dataclass(event)
    with pytest.raises(FrozenInstanceError):
        event.content = "changed"  # type: ignore[misc]


def test_turn_event_rejects_private_metadata_keys() -> None:
    """TurnEvent metadata 不能携带私有评分字段。"""

    with pytest.raises(DataLeakageError):
        TurnEvent(
            role="user",
            speaker_name=None,
            content="hello",
            timestamp=None,
            isolation_key="run_conv",
            session_id="s1",
            turn_id="t1",
            metadata={"evidence": ["t1"]},
        )


def test_turn_event_requires_non_blank_content() -> None:
    """TurnEvent content 不能为空白字符串。"""

    with pytest.raises(ValueError, match="content"):
        TurnEvent(
            role="user",
            speaker_name=None,
            content=" ",
            timestamp=None,
            isolation_key="run_conv",
            session_id="s1",
            turn_id="t1",
            metadata={},
        )


def test_turn_pair_preserves_pair_granularity_payload() -> None:
    """TurnPair 必须保存同一隔离空间内的相邻 turn。"""

    first = _turn("t1", "user", "hi")
    second = _turn("t2", "assistant", "hello")
    pair = TurnPair(first=first, second=second, metadata={"pair_index": 0})

    assert pair.turns == (first, second)
    assert pair.isolation_key == "run_conv"
    assert pair.session_id == "s1"


def test_turn_pair_allows_dangling_single_turn() -> None:
    """TurnPair 要能表达落单 turn，供聚合器记录边界。"""

    first = _turn("t1", "user", "hi")
    pair = TurnPair(first=first, second=None, metadata={"dangling": True})

    assert pair.turns == (first,)
    assert pair.metadata["dangling"] is True


def test_turn_pair_rejects_cross_isolation_payload() -> None:
    """TurnPair 不能混入不同 isolation_key 的 turn。"""

    first = _turn("t1")
    second = TurnEvent(
        role="assistant",
        speaker_name="Bob",
        content="hello",
        timestamp=None,
        isolation_key="other",
        session_id="s1",
        turn_id="t2",
        metadata={},
    )

    with pytest.raises(ValueError, match="isolation_key"):
        TurnPair(first=first, second=second)


def test_session_batch_preserves_session_granularity_payload() -> None:
    """SessionBatch 必须保存一个 session 内的 turn 序列。"""

    batch = SessionBatch(
        isolation_key="run_conv",
        session_id="s1",
        events=(_turn("t1"), _turn("t2", "assistant", "hello")),
        session_time="2026-07-06",
        metadata={"batch": 1},
    )

    assert [event.turn_id for event in batch.events] == ["t1", "t2"]
    assert batch.ref == SessionRef(isolation_key="run_conv", session_id="s1")


def test_session_batch_rejects_event_from_other_session() -> None:
    """SessionBatch 不能混入其他 session 的 turn。"""

    event = TurnEvent(
        role="user",
        speaker_name=None,
        content="hello",
        timestamp=None,
        isolation_key="run_conv",
        session_id="s2",
        turn_id="t1",
        metadata={},
    )

    with pytest.raises(ValueError, match="session_id"):
        SessionBatch(isolation_key="run_conv", session_id="s1", events=(event,))


def test_conversation_batch_preserves_conversation_granularity_payload() -> None:
    """ConversationBatch 必须保存完整隔离空间内的 session 序列。"""

    session = SessionBatch(
        isolation_key="run_conv",
        session_id="s1",
        events=(_turn("t1"),),
        session_time=None,
    )
    batch = ConversationBatch(isolation_key="run_conv", sessions=(session,))

    assert batch.ref == UnitRef(isolation_key="run_conv")
    assert batch.events == (_turn("t1"),)


def test_conversation_batch_rejects_cross_isolation_session() -> None:
    """ConversationBatch 不能混入其他 isolation_key 的 session。"""

    event = TurnEvent(
        role="user",
        speaker_name="Alice",
        content="hello",
        timestamp=None,
        isolation_key="other",
        session_id="s1",
        turn_id="t1",
        metadata={},
    )
    session = SessionBatch(isolation_key="other", session_id="s1", events=(event,))

    with pytest.raises(ValueError, match="isolation_key"):
        ConversationBatch(isolation_key="run_conv", sessions=(session,))


def test_ref_entities_are_frozen_dataclasses() -> None:
    """SessionRef 和 UnitRef 必须是不可变 dataclass。"""

    session_ref = SessionRef(isolation_key="run_conv", session_id="s1")
    unit_ref = UnitRef(isolation_key="run_conv")

    assert is_dataclass(session_ref)
    assert is_dataclass(unit_ref)
    with pytest.raises(FrozenInstanceError):
        session_ref.session_id = "changed"  # type: ignore[misc]


def test_ingest_result_can_carry_session_memories() -> None:
    """IngestResult 必须能携带 HaluMem 式 session memories。"""

    result = IngestResult(
        unit_ref=SessionRef(isolation_key="run_conv", session_id="s1"),
        session_memories=["Alice likes tea."],
        metadata={"count": 1},
    )

    assert result.session_memories == ["Alice likes tea."]
    assert result.metadata["count"] == 1


def test_session_memory_report_records_boundary_memories() -> None:
    """SessionMemoryReport 必须表达 end_session 的新增记忆报告。"""

    report = SessionMemoryReport(
        session_ref=SessionRef(isolation_key="run_conv", session_id="s1"),
        memories=["Alice likes tea."],
        metadata={"source": "end_session"},
    )

    assert report.session_ref.session_id == "s1"
    assert report.memories == ["Alice likes tea."]


def test_retrieval_query_accepts_only_declared_purposes() -> None:
    """RetrievalQuery purpose 只允许三种已批准语义。"""

    question = Question("q1", "conv", "What does Alice like?")
    query = RetrievalQuery(
        query_text="What does Alice like?",
        isolation_key="run_conv",
        question_time=None,
        top_k=5,
        purpose="qa",
        source_question=question,
    )

    assert query.source_question is question
    with pytest.raises(ValueError, match="purpose"):
        RetrievalQuery(
            query_text="probe",
            isolation_key="run_conv",
            question_time=None,
            top_k=5,
            purpose="invalid",  # type: ignore[arg-type]
            source_question=None,
        )


def test_retrieval_query_rejects_private_source_question_metadata() -> None:
    """RetrievalQuery 不能通过 source_question metadata 泄漏私有字段。"""

    question = Question(
        "q1",
        "conv",
        "What does Alice like?",
        metadata={"ground_truth": "tea"},
    )

    with pytest.raises(DataLeakageError):
        RetrievalQuery(
            query_text="What does Alice like?",
            isolation_key="run_conv",
            question_time=None,
            top_k=5,
            purpose="qa",
            source_question=question,
        )


def test_retrieved_item_records_turn_level_provenance() -> None:
    """RetrievedItem 必须能记录 turn 级 source_turn_ids。"""

    item = RetrievedItem(
        item_id="m1",
        content="Alice likes tea.",
        score=0.8,
        timestamp="2026-07-06",
        source_turn_ids=("t1", "t2"),
    )

    assert item.source_turn_ids == ("t1", "t2")


def test_retrieval_result_requires_formatted_memory() -> None:
    """RetrievalResult formatted_memory 是必需且非空的规范记忆文本。"""

    with pytest.raises(ValueError, match="formatted_memory"):
        RetrievalResult(formatted_memory=" ", metadata={})


def test_retrieval_result_keeps_native_prompt_and_items() -> None:
    """RetrievalResult 可同时保存 native prompt 与结构化检索条目。"""

    item = RetrievedItem(
        item_id="m1",
        content="Alice likes tea.",
        score=None,
        timestamp=None,
        source_turn_ids=("t1",),
    )
    result = RetrievalResult(
        formatted_memory="[2026-07-06] Alice likes tea.",
        prompt_messages=(PromptMessage("user", "Question?"),),
        items=(item,),
        metadata={"profile": "native"},
    )

    assert result.prompt_messages[0].content == "Question?"
    assert result.items == (item,)


def test_evidence_assertion_valid_rejects_reason_fields() -> None:
    """status=valid 时 reason_code/reason 必须都为 None。"""

    assert EvidenceAssertion(status="valid").reason_code is None
    with pytest.raises(ValueError, match="valid EvidenceAssertion"):
        EvidenceAssertion(status="valid", reason_code="x", reason="y")


@pytest.mark.parametrize("status", ["n_a", "pending"])
def test_evidence_assertion_non_valid_requires_reason(status: str) -> None:
    """status=n_a|pending 时 reason_code 与 reason 必须都是非空字符串。"""

    with pytest.raises(ValueError, match="reason_code"):
        EvidenceAssertion(status=status, reason=" spelled out ")
    with pytest.raises(ValueError, match="reason"):
        EvidenceAssertion(status=status, reason_code="code")
    ok = EvidenceAssertion(status=status, reason_code="code", reason="human readable")
    assert ok.status == status


def test_retrieval_evidence_valid_provenance_requires_turn_or_session() -> None:
    """semantic provenance=valid 时 granularity 只能是 turn|session。"""

    for granularity in ("turn", "session"):
        evidence = RetrievalEvidence(
            semantic_provenance=EvidenceAssertion(status="valid"),
            provenance_granularity=granularity,
            stable_ranking=EvidenceAssertion(status="valid"),
        )
        assert evidence.provenance_granularity == granularity
    with pytest.raises(ValueError, match="valid semantic_provenance"):
        RetrievalEvidence(
            semantic_provenance=EvidenceAssertion(status="valid"),
            provenance_granularity="none",
            stable_ranking=EvidenceAssertion(status="valid"),
        )


def test_retrieval_evidence_non_valid_provenance_requires_none() -> None:
    """semantic provenance 非 valid 时 granularity 必须为 none。"""

    with pytest.raises(ValueError, match="requires provenance_granularity='none'"):
        RetrievalEvidence(
            semantic_provenance=EvidenceAssertion(
                status="n_a", reason_code="c", reason="r"
            ),
            provenance_granularity="turn",
            stable_ranking=EvidenceAssertion(status="valid"),
        )


def test_retrieval_evidence_asdict_carries_no_private_keys() -> None:
    """合法 RetrievalEvidence 可 asdict() 序列化且不含私有评分键。"""

    from dataclasses import asdict

    evidence = RetrievalEvidence(
        semantic_provenance=EvidenceAssertion(status="valid"),
        provenance_granularity="turn",
        stable_ranking=EvidenceAssertion(
            status="pending", reason_code="ranking_fidelity_not_audited", reason="r"
        ),
    )
    payload = asdict(evidence)
    validate_no_private_keys(payload)
    assert payload["semantic_provenance"]["status"] == "valid"
    assert payload["stable_ranking"]["reason_code"] == "ranking_fidelity_not_audited"


def test_retrieval_result_carries_optional_evidence() -> None:
    """RetrievalResult 默认 evidence 为 None，可携带逐题 RetrievalEvidence。"""

    assert RetrievalResult(formatted_memory="m").evidence is None
    evidence = RetrievalEvidence(
        semantic_provenance=EvidenceAssertion(status="valid"),
        provenance_granularity="session",
        stable_ranking=EvidenceAssertion(
            status="pending", reason_code="ranking_fidelity_not_audited", reason="r"
        ),
    )
    result = RetrievalResult(formatted_memory="m", evidence=evidence)
    assert result.evidence is evidence


def test_memory_provider_default_capability_declarations() -> None:
    """MemoryProvider 默认能力声明必须与 spec 保持一致。"""

    class ExampleProvider(MemoryProvider):
        """测试用最小 v3 provider。"""

        consume_granularity = "turn"

        def ingest(self, unit: TurnEvent) -> IngestResult | None:
            """记录一个 ingest 调用。"""

            return None

        def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
            """返回最小合法检索结果。"""

            return RetrievalResult(formatted_memory="memory")

    provider = ExampleProvider()

    assert provider.consume_granularity == "turn"
    assert provider.session_memory_report is False
    assert provider.provenance_granularity == "none"
    assert provider.prepare(run_context={"run_id": "r1"}) is None
    assert provider.cleanup() is None
    assert provider.end_session(SessionRef("run_conv", "s1")) is None
    assert provider.end_conversation(UnitRef("run_conv")) is None

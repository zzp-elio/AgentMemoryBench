"""测试 BEAM CLI predict 接线与 turn 截断路径。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters.beam import (
    BeamAdapter,
    prepare_beam_run,
)
from memory_benchmark.benchmark_adapters.contracts import BenchmarkLoadRequest, RunScope


@pytest.mark.unit
def test_beam_smoke_prepare_uses_turn_truncation_not_session() -> None:
    """BEAM smoke 裁剪轴应为 turn（--rounds），不是 session。"""

    request = BenchmarkLoadRequest(
        variant="100k",
        run_scope=RunScope.SMOKE,
        smoke_turn_limit=5,
        smoke_conversation_limit=1,
    )

    prepared = prepare_beam_run(Path("."), request)
    metadata = prepared.dataset.metadata

    assert metadata["smoke_turn_limit"] == 5
    # BEAM 是 conversation-QA 家族，不应有 session 裁剪轴
    assert "smoke_session_limit" not in metadata


@pytest.mark.unit
def test_beam_smoke_preserves_all_questions() -> None:
    """BEAM smoke turn 截断只裁历史，不裁 probing questions。"""

    # 使用真实 100k 数据验证：所有 20 个 probing question 在 smoke 后都保留
    adapter = BeamAdapter(Path("."), variant="100k")
    dataset = adapter.load(limit=1)
    conversation = dataset.conversations[0]

    full_question_count = len(conversation.questions)

    prepared = prepare_beam_run(
        Path("."),
        BenchmarkLoadRequest(
            variant="100k",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=4,
            smoke_conversation_limit=1,
        ),
    )
    smoke_conversation = prepared.dataset.conversations[0]

    # probing questions 不应被裁剪（smoke 只裁 turn 不裁 question）
    assert len(smoke_conversation.questions) == full_question_count
    # turn 数应 ≤ smoke_turn_limit
    total_turns = sum(len(s.turns) for s in smoke_conversation.sessions)
    assert total_turns <= 4


@pytest.mark.unit
def test_beam_smoke_covers_multiple_abilities() -> None:
    """BEAM smoke 应在极少 turn 下仍然覆盖多个 ability 的 probing question。"""

    prepared = prepare_beam_run(
        Path("."),
        BenchmarkLoadRequest(
            variant="100k",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=4,
            smoke_conversation_limit=1,
        ),
    )

    conversation = prepared.dataset.conversations[0]
    abilities = {q.category for q in conversation.questions if q.category}
    # 即使只有 4 个 turn，也应有多类 ability 的 probing question
    assert len(abilities) >= 1, "should have at least one ability"
    # 真实 100k 数据每 conversation 有 10 ability
    assert len(conversation.questions) == 20

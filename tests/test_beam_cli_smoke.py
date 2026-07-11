"""测试 BEAM CLI predict 接线与 round 截断路径。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters.beam import (
    BeamAdapter,
    prepare_beam_run,
)
from memory_benchmark.benchmark_adapters.contracts import BenchmarkLoadRequest, RunScope


@pytest.mark.unit
def test_beam_smoke_prepare_uses_round_truncation_not_session() -> None:
    """BEAM smoke 裁剪轴应为完整 round，不是 session。"""

    request = BenchmarkLoadRequest(
        variant="100k",
        run_scope=RunScope.SMOKE,
        smoke_turn_limit=1,
        smoke_conversation_limit=1,
    )

    prepared = prepare_beam_run(Path("."), request)
    metadata = prepared.dataset.metadata

    assert metadata["smoke_round_limit"] == 1
    assert metadata["smoke_retained_turn_count"] == 2
    # BEAM 是 conversation-QA 家族，不应有 session 裁剪轴
    assert "smoke_session_limit" not in metadata


@pytest.mark.unit
def test_beam_smoke_preserves_questions_for_runner_budgeting() -> None:
    """adapter 保留问题集，runner 按公开顺序执行 policy 的单题预算。"""

    # 使用真实 100k 数据验证：所有 20 个 probing question 在 smoke 后都保留
    adapter = BeamAdapter(Path("."), variant="100k")
    dataset = adapter.load(limit=1)
    conversation = dataset.conversations[0]

    full_question_ids = [question.question_id for question in conversation.questions]

    prepared = prepare_beam_run(
        Path("."),
        BenchmarkLoadRequest(
            variant="100k",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=1,
            smoke_conversation_limit=1,
        ),
    )
    smoke_conversation = prepared.dataset.conversations[0]

    assert [question.question_id for question in smoke_conversation.questions] == (
        full_question_ids
    )
    total_turns = sum(len(s.turns) for s in smoke_conversation.sessions)
    assert total_turns == 2


@pytest.mark.unit
def test_beam_smoke_question_order_starts_with_abstention() -> None:
    """runner 的默认单题预算将取公开顺序首题，不读取 gold 选题。"""

    prepared = prepare_beam_run(
        Path("."),
        BenchmarkLoadRequest(
            variant="100k",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=1,
            smoke_conversation_limit=1,
        ),
    )

    conversation = prepared.dataset.conversations[0]
    assert conversation.questions[0].category == "abstention"

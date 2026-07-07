"""测试 HaluMem 转换为统一 Dataset。

这些测试只覆盖 adapter 层的数据映射、私有标注隔离和 variant 声明，不运行
operation-level runner，也不调用真实 API。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.benchmark_adapters.halumem import (
    HaluMemAdapter,
    HALUMEM_VARIANT_SPECS,
    parse_halumem_timestamp,
    prepare_halumem_run,
)
from memory_benchmark.benchmark_adapters.contracts import BenchmarkLoadRequest, RunScope
from memory_benchmark.core.validators import validate_no_private_keys


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """把 HaluMem 风格 rows 写成 JSONL fixture。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _user_row(uuid: str = "user-1") -> dict[str, Any]:
    """构造覆盖普通 session、无 question update session 和生成 session 的样本。"""

    return {
        "uuid": uuid,
        "persona_info": "Name: Riley Chen; Location: Boston.",
        "sessions": [
            {
                "start_time": "Sep 04, 2025, 18:42:18",
                "end_time": "Sep 04, 2025, 21:12:18",
                "memory_points": [
                    {
                        "index": 1,
                        "memory_content": "Riley lives in Boston",
                        "memory_type": "Persona Memory",
                        "is_update": "False",
                        "original_memories": [],
                        "timestamp": "Sep 04, 2025, 21:12:18",
                    },
                    {
                        "index": 2,
                        "memory_content": "Riley likes tea",
                        "memory_type": "Persona Memory",
                        "is_update": "True",
                        "original_memories": ["Riley likes coffee"],
                        "timestamp": "Sep 04, 2025, 21:12:18",
                    },
                ],
                "dialogue": [
                    {
                        "role": "user",
                        "content": "I live in Boston.",
                        "timestamp": "Sep 04, 2025, 18:42:18",
                        "dialogue_turn": 0,
                    },
                    {
                        "role": "assistant",
                        "content": "I will remember that.",
                        "timestamp": "Sep 04, 2025, 18:43:18",
                        "dialogue_turn": 0,
                    },
                ],
                "questions": [
                    {
                        "question": "Where does Riley live?",
                        "answer": "Boston",
                        "evidence": [
                            {
                                "memory_content": "Riley lives in Boston",
                                "memory_type": "Persona Memory",
                            }
                        ],
                        "difficulty": "easy",
                        "question_type": "Basic Fact Recall",
                    }
                ],
            },
            {
                "start_time": "Sep 05, 2025, 18:42:18",
                "end_time": "Sep 05, 2025, 21:12:18",
                "memory_points": [
                    {
                        "index": 3,
                        "memory_content": "Riley moved to Seattle",
                        "memory_type": "Persona Memory",
                        "is_update": "True",
                        "original_memories": ["Riley lives in Boston"],
                        "timestamp": "Sep 05, 2025, 21:12:18",
                    }
                ],
                "dialogue": [
                    {
                        "role": "user",
                        "content": "I moved to Seattle.",
                        "timestamp": "Sep 05, 2025, 18:42:18",
                        "dialogue_turn": 0,
                    }
                ],
                "questions": [],
            },
            {
                "session_id": "generated-context",
                "start_time": "bad timestamp",
                "end_time": "Sep 06, 2025, 21:12:18",
                "is_generated_qa_session": True,
                "memory_points": [],
                "dialogue": [
                    {
                        "role": "assistant",
                        "content": "Synthetic context only.",
                        "timestamp": "bad timestamp",
                        "dialogue_turn": 0,
                    }
                ],
                "questions": [],
            },
        ],
    }


def test_synthetic_user_maps_user_sessions_turns_questions_and_private_gold(
    tmp_path: Path,
) -> None:
    """HaluMem user/session/turn/question 应映射到统一 Dataset 且 gold 留在私有侧。"""

    source = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    _write_jsonl(source, [_user_row()])

    dataset = HaluMemAdapter(tmp_path, variant="medium").load()
    conversation = dataset.conversations[0]
    first_session = conversation.sessions[0]
    first_turn = first_session.turns[0]
    question = conversation.questions[0]
    gold = conversation.gold_answers[question.question_id]

    assert dataset.dataset_name == "halumem"
    assert dataset.metadata["variant"] == "medium"
    assert conversation.conversation_id == "user-1"
    assert first_session.session_id == "s1"
    assert first_session.session_time == "2025-09-04T18:42:18+00:00"
    assert first_session.start_time == "2025-09-04T18:42:18+00:00"
    assert first_session.end_time == "2025-09-04T21:12:18+00:00"
    assert first_turn.speaker == "user"
    assert first_turn.normalized_role == "user"
    assert first_turn.content == "I live in Boston."
    assert first_turn.turn_time == "2025-09-04T18:42:18+00:00"
    assert first_turn.metadata["dialogue_turn"] == 0
    assert question.text == "Where does Riley live?"
    assert question.metadata == {}
    assert gold.answer == "Boston"
    assert gold.evidence == ["1"]
    assert gold.metadata["difficulty"] == "easy"
    assert gold.metadata["question_type"] == "Basic Fact Recall"
    assert gold.metadata["raw_evidence"][0]["memory_content"] == "Riley lives in Boston"
    assert first_session.private_metadata["memory_points"][1]["memory_content"] == (
        "Riley likes tea"
    )
    assert first_session.private_metadata["persona_info"] == (
        "Name: Riley Chen; Location: Boston."
    )


def test_public_conversation_excludes_gold_memory_points_and_generated_flag(
    tmp_path: Path,
) -> None:
    """公开 Conversation 不得泄漏 HaluMem gold、evidence 或生成 session 标志。"""

    source = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    _write_jsonl(source, [_user_row()])
    conversation = HaluMemAdapter(tmp_path, variant="medium").load().conversations[0]
    public = conversation.to_public_dict()
    public_text = json.dumps(public, ensure_ascii=False)

    validate_no_private_keys(public)
    assert "memory_points" not in public_text
    assert "Riley likes tea" not in public_text
    assert "persona_info" not in public_text
    assert "is_generated_qa_session" not in public_text
    assert "Basic Fact Recall" not in public_text
    assert "Boston" not in public["questions"][0]


def test_session_private_metadata_preserves_generated_flag_and_no_question_gold(
    tmp_path: Path,
) -> None:
    """无 question 的 session 仍须保留私有 memory_points；生成标志只在私有侧。"""

    source = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    _write_jsonl(source, [_user_row()])
    conversation = HaluMemAdapter(tmp_path, variant="medium").load().conversations[0]

    no_question_session = conversation.sessions[1]
    generated_session = conversation.sessions[2]

    assert no_question_session.private_metadata["memory_points"][0]["index"] == 3
    assert no_question_session.private_metadata["is_generated_qa_session"] is False
    assert generated_session.session_id == "generated-context"
    assert generated_session.session_time is None
    assert generated_session.turns[0].turn_time is None
    assert generated_session.private_metadata["is_generated_qa_session"] is True


def test_parse_halumem_timestamp_returns_iso_or_none() -> None:
    """HaluMem 官方时间格式应转成 UTC ISO，无法解析时返回 None。"""

    assert parse_halumem_timestamp("Sep 04, 2025, 21:12:18") == (
        "2025-09-04T21:12:18+00:00"
    )
    assert parse_halumem_timestamp("not a timestamp") is None
    assert parse_halumem_timestamp(None) is None


def test_halumem_variants_declare_medium_and_long_sources() -> None:
    """HaluMem 应声明 medium/long 双 variant 与各自 JSONL 源文件。"""

    assert HALUMEM_VARIANT_SPECS[0].name == "medium"
    assert HALUMEM_VARIANT_SPECS[0].source_relative_paths == (
        Path("data/halumem/HaluMem-Medium.jsonl"),
    )
    assert HALUMEM_VARIANT_SPECS[1].name == "long"
    assert HALUMEM_VARIANT_SPECS[1].source_relative_paths == (
        Path("data/halumem/HaluMem-Long.jsonl"),
    )


def test_prepare_halumem_run_smoke_limits_user_count(tmp_path: Path) -> None:
    """smoke_conversation_limit 应按 HaluMem user 数裁剪，不新增契约字段。"""

    medium = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    long = tmp_path / "data" / "halumem" / "HaluMem-Long.jsonl"
    _write_jsonl(medium, [_user_row("user-1"), _user_row("user-2")])
    _write_jsonl(long, [_user_row("user-3")])

    prepared = prepare_halumem_run(
        tmp_path,
        BenchmarkLoadRequest(
            variant="medium",
            run_scope=RunScope.SMOKE,
            smoke_conversation_limit=1,
        ),
    )

    assert prepared.variant == "medium"
    assert prepared.run_scope is RunScope.SMOKE
    assert prepared.source_relative_paths == (
        Path("data/halumem/HaluMem-Medium.jsonl"),
    )
    assert prepared.dataset.metadata["run_scope"] == "smoke"
    assert prepared.dataset.metadata["variant"] == "medium"
    assert len(prepared.dataset.conversations) == 1

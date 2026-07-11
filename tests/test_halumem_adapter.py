"""测试 HaluMem 转换为统一 Dataset。

这些测试只覆盖 adapter 层的数据映射、私有标注隔离和 variant 声明，不运行
operation-level runner，也不调用真实 API。
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.benchmark_adapters.halumem import (
    HaluMemAdapter,
    HALUMEM_RESUME_POLICY,
    HALUMEM_SMOKE_POLICY,
    HALUMEM_VARIANT_SPECS,
    _halumem_smoke_prefix,
    parse_halumem_timestamp,
    prepare_halumem_run,
)
from memory_benchmark.benchmark_adapters.contracts import BenchmarkLoadRequest, RunScope
from memory_benchmark.core.exceptions import ConfigurationError
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
                "questions": [
                    {
                        "question": "Where did Riley previously live?",
                        "answer": "Boston",
                        "evidence": [
                            {
                                "memory_content": "Riley lives in Boston",
                                "memory_type": "Persona Memory",
                            }
                        ],
                        "difficulty": "medium",
                        "question_type": "Dynamic Update",
                    }
                ],
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
    assert dataset.metadata["source_sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    assert dataset.metadata["source_size_bytes"] == source.stat().st_size
    assert dataset.metadata["loaded_conversation_count"] == 1
    assert dataset.metadata["loaded_session_count"] == 3
    assert dataset.metadata["loaded_turn_count"] == 4
    assert dataset.metadata["loaded_question_count"] == 2
    assert dataset.metadata["official_repo_url"] == "https://github.com/MemTensor/HaluMem"
    assert dataset.metadata["official_paper_url"] == "https://arxiv.org/abs/2511.03506"
    assert dataset.metadata["official_dataset_url"] == (
        "https://huggingface.co/datasets/IAAR-Shanghai/HaluMem"
    )
    assert dataset.metadata["license"] == "CC-BY-NC-ND-4.0"
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
    assert gold.evidence == ["Riley lives in Boston"]
    assert gold.metadata["difficulty"] == "easy"
    assert gold.metadata["question_type"] == "Basic Fact Recall"
    assert gold.metadata["raw_evidence"][0]["memory_content"] == "Riley lives in Boston"
    assert gold.metadata["raw_evidence"][0]["memory_type"] == "Persona Memory"
    assert first_session.private_metadata["memory_points"][1]["memory_content"] == (
        "Riley likes tea"
    )
    assert first_session.private_metadata["persona_info"] == (
        "Name: Riley Chen; Location: Boston."
    )


def test_public_conversation_excludes_gold_but_preserves_generated_control_flag(
    tmp_path: Path,
) -> None:
    """公开 Conversation 不泄漏 gold，并保留 runner 所需生成 session 标志。"""

    source = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    _write_jsonl(source, [_user_row()])
    conversation = HaluMemAdapter(tmp_path, variant="medium").load().conversations[0]
    public = conversation.to_public_dict()
    public_text = json.dumps(public, ensure_ascii=False)

    validate_no_private_keys(public)
    assert "memory_points" not in public_text
    assert "Riley likes tea" not in public_text
    assert "persona_info" not in public_text
    assert public["sessions"][2]["metadata"]["is_generated_qa_session"] is True
    assert "Basic Fact Recall" not in public_text
    assert "Boston" not in public["questions"][0]


def test_gold_evidence_preserves_cross_session_memory_content(
    tmp_path: Path,
) -> None:
    """跨 session evidence 应保留 memory_content，不能映射成本 session index。"""

    source = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    _write_jsonl(source, [_user_row()])
    conversation = HaluMemAdapter(tmp_path, variant="medium").load().conversations[0]
    cross_session_question = conversation.questions[1]
    gold = conversation.gold_answers[cross_session_question.question_id]

    assert gold.evidence == ["Riley lives in Boston"]
    assert gold.metadata["raw_evidence"][0] == {
        "memory_content": "Riley lives in Boston",
        "memory_type": "Persona Memory",
    }


def test_session_private_metadata_preserves_generated_flag(
    tmp_path: Path,
) -> None:
    """session 私有 metadata 须保留 memory_points 与生成标志。"""

    source = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    _write_jsonl(source, [_user_row()])
    conversation = HaluMemAdapter(tmp_path, variant="medium").load().conversations[0]

    update_session = conversation.sessions[1]
    generated_session = conversation.sessions[2]

    assert update_session.private_metadata["memory_points"][0]["index"] == 3
    assert update_session.private_metadata["is_generated_qa_session"] is False
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


def test_prepare_halumem_run_builds_fixed_shape_and_policy_metadata(
    tmp_path: Path,
) -> None:
    """smoke 应按三操作前缀裁 session、每 session 两 turn且只留一题。"""

    medium = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    long = tmp_path / "data" / "halumem" / "HaluMem-Long.jsonl"
    _write_jsonl(medium, [_user_row("user-1"), _user_row("user-2")])
    _write_jsonl(long, [_user_row("user-3")])

    prepared = prepare_halumem_run(
        tmp_path,
        BenchmarkLoadRequest(
            variant="medium",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=4,
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
    assert prepared.dataset.metadata["smoke_fixed_shape"] is True
    assert prepared.dataset.metadata["smoke_policy"] == HALUMEM_SMOKE_POLICY.to_dict()
    assert prepared.dataset.metadata["resume_policy"] == HALUMEM_RESUME_POLICY.to_dict()
    assert prepared.dataset.metadata["smoke_conversation_shapes"][0][
        "smoke_prefix_rule"
    ]["final_prefix_length"] == 1
    assert len(prepared.dataset.conversations) == 1
    conversation = prepared.dataset.conversations[0]
    assert len(conversation.sessions) == 1
    assert len(conversation.sessions[0].turns) == 2
    assert len(conversation.questions) == 1
    assert conversation.metadata["smoke_prefix_rule"] == {
        "extraction_first_session": 1,
        "update_first_session": 1,
        "qa_first_session": 1,
        "final_prefix_length": 1,
    }
    assert conversation.metadata["smoke_removed_question_count"] == 1


def test_halumem_smoke_prefix_spans_operations_and_preserves_generated_flag(
    tmp_path: Path,
) -> None:
    """三操作分散时取最大首现序号，生成 session 不贡献操作且 flag 公开。"""

    row = _user_row()
    extraction = row["sessions"][0]
    extraction["memory_points"] = [extraction["memory_points"][0]]
    extraction["questions"] = []
    update = row["sessions"][1]
    update["questions"] = []
    update["dialogue"][0]["role"] = "assistant"
    generated = row["sessions"][2]
    qa = copy.deepcopy(_user_row()["sessions"][0])
    qa["session_id"] = "qa-session"
    qa["memory_points"] = []
    row["sessions"] = [extraction, update, generated, qa]

    source = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    _write_jsonl(source, [row])
    prepared = prepare_halumem_run(
        tmp_path,
        BenchmarkLoadRequest(
            variant="medium", run_scope=RunScope.SMOKE, smoke_turn_limit=4
        ),
    )
    conversation = prepared.dataset.conversations[0]

    assert len(conversation.sessions) == 4
    assert conversation.metadata["smoke_prefix_rule"]["final_prefix_length"] == 4
    assert conversation.metadata["smoke_round_anomaly"] is True
    assert conversation.metadata["smoke_session_turn_shapes"][1] == {
        "session_id": "s2",
        "original_turn_count": 1,
        "retained_turn_count": 1,
        "smoke_round_anomaly": True,
    }
    assert conversation.sessions[2].metadata["is_generated_qa_session"] is True
    assert conversation.sessions[2].private_metadata["memory_points"] == []
    assert len(conversation.questions) == 1
    assert conversation.metadata["smoke_removed_question_count"] == 0


def test_halumem_smoke_incomplete_keeps_all_sessions(tmp_path: Path) -> None:
    """缺少 update 操作时 smoke 应全保留并明确标记 incomplete。"""

    row = _user_row()
    for session in row["sessions"]:
        for point in session.get("memory_points", []):
            point["is_update"] = "False"
            point["original_memories"] = []
    source = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    _write_jsonl(source, [row])
    prepared = prepare_halumem_run(
        tmp_path,
        BenchmarkLoadRequest(
            variant="medium", run_scope=RunScope.SMOKE, smoke_turn_limit=4
        ),
    )

    conversation = prepared.dataset.conversations[0]
    assert len(conversation.sessions) == len(row["sessions"])
    assert conversation.metadata["smoke_prefix_incomplete"] is True
    assert conversation.metadata["smoke_prefix_rule"]["update_first_session"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"smoke_turn_limit": 3},
        {"smoke_conversation_limit": 2},
        {"smoke_session_limit": 1},
    ],
)
def test_prepare_halumem_smoke_rejects_cropping_parameters(
    tmp_path: Path, overrides: dict[str, int]
) -> None:
    """adapter 直接入口不得接受偏离固定形状的裁剪参数。"""

    source = tmp_path / "data" / "halumem" / "HaluMem-Medium.jsonl"
    _write_jsonl(source, [_user_row()])
    request = {
        "variant": "medium",
        "run_scope": RunScope.SMOKE,
        "smoke_turn_limit": 4,
    }
    request.update(overrides)

    with pytest.raises(ConfigurationError, match="fixed shape"):
        prepare_halumem_run(tmp_path, BenchmarkLoadRequest(**request))


def test_halumem_medium_real_data_smoke_prefix_anchor() -> None:
    """真实 Medium 应锁定 20 user 前缀分布与首 conversation 固定形状。"""

    root = Path(__file__).resolve().parents[1]
    dataset = HaluMemAdapter(root, variant="medium").load()
    prefix_lengths = [
        _halumem_smoke_prefix(conversation.sessions)[0]
        for conversation in dataset.conversations
    ]
    first = dataset.conversations[0]
    first_prefix, first_seen = _halumem_smoke_prefix(first.sessions)
    update_points = first.sessions[3].private_metadata["memory_points"]

    assert Counter(prefix_lengths) == Counter({4: 18, 2: 1, 5: 1})
    assert first_prefix == 4
    assert first_seen == {"extraction": 1, "update": 4, "qa": 1}
    assert first.sessions[3].private_metadata["source_question_count"] == 0
    assert sum(
        point.get("is_update") == "True" and bool(point.get("original_memories"))
        for point in update_points
    ) == 7

    smoke = prepare_halumem_run(
        root,
        BenchmarkLoadRequest(
            variant="medium", run_scope=RunScope.SMOKE, smoke_turn_limit=4
        ),
    ).dataset
    smoke_first = smoke.conversations[0]
    assert len(smoke_first.sessions) == 4
    assert sum(len(session.turns) for session in smoke_first.sessions) == 8
    assert len(smoke_first.questions) == 1

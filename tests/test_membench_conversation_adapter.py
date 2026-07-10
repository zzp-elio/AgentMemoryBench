"""测试 MemBench 转换为 conversation-QA v2 Dataset。

这些测试覆盖 data2test 层级展开、PS/OS step 映射、target_step_id 私有隔离，
以及真实样本中的 step_id / target_step_id 对齐风险。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.benchmark_adapters.membench import MemBenchAdapter
from memory_benchmark.core.exceptions import DataLeakageError, DatasetValidationError
from memory_benchmark.core.validators import validate_no_private_keys


ROOT = Path(__file__).resolve().parents[1]


def _write_fixture(path: Path, payload: dict[str, Any]) -> None:
    """把 MemBench 风格 fixture 写成 JSON 文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _synthetic_payload() -> dict[str, Any]:
    """构造同时包含 PS dict step 与 OS string step 的迷你 MemBench 数据。"""

    return {
        "simple": {
            "roles": [
                {
                    "tid": "ps-1",
                    "message_list": [
                        {
                            "user": "I work with Maya.",
                            "agent": "Maya is your colleague.",
                        },
                        {
                            "user": "Maya moved to Boston.",
                            "agent": "I will remember Boston.",
                        },
                    ],
                    "QA": {
                        "qid": 7,
                        "question": "Where did Maya move?",
                        "answer": "Boston",
                        "target_step_id": [1],
                        "choices": {
                            "A": "Austin",
                            "B": "Boston",
                            "C": "Chicago",
                            "D": "Denver",
                        },
                        "ground_truth": "B",
                        "time": "'2024-10-01 08:13' Tuesday",
                    },
                }
            ],
            "observations": [
                {
                    "tid": "os-1",
                    "message_list": [
                        "My favorite cafe is Blue Bottle.",
                        "I usually go there on Fridays.",
                    ],
                    "QA": {
                        "qid": "q-os",
                        "question": "Which cafe do I like?",
                        "answer": "Blue Bottle",
                        "target_step_id": [0],
                        "choices": {
                            "A": "Blue Bottle",
                            "B": "Philz",
                            "C": "Sightglass",
                            "D": "Verve",
                        },
                        "ground_truth": "A",
                        "time": "'2024-10-02 09:00' Wednesday",
                    },
                }
            ],
        }
    }


def test_synthetic_fixture_maps_ps_and_os_steps(tmp_path: Path) -> None:
    """PS dict step 应合并成官方 store 文本，OS string step 应原样保留。"""

    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, _synthetic_payload())

    adapter = MemBenchAdapter(tmp_path, variant="0_10k", source_relative_paths=(source.relative_to(tmp_path),))
    dataset = adapter.load()

    assert dataset.dataset_name == "membench"
    assert dataset.metadata["variant"] == "0_10k"
    assert len(dataset.conversations) == 2

    ps_conversation = dataset.conversations[0]
    ps_turn = ps_conversation.sessions[0].turns[0]
    assert ps_conversation.conversation_id == "first-low-simple-roles-ps-1"
    assert ps_turn.turn_id == "1"
    assert ps_turn.normalized_role == "user"
    assert ps_turn.content == "'user': I work with Maya.; 'agent': Maya is your colleague."
    assert ps_turn.metadata["ps_user"] == "I work with Maya."
    assert ps_turn.metadata["ps_agent"] == "Maya is your colleague."
    assert ps_turn.metadata["source_step_index"] == 0
    assert "0[|]" not in ps_turn.content

    os_conversation = dataset.conversations[1]
    os_turn = os_conversation.sessions[0].turns[0]
    assert os_conversation.conversation_id == "first-low-simple-observations-os-1"
    assert os_turn.content == "My favorite cafe is Blue Bottle."
    assert os_turn.metadata["source_step_index"] == 0
    assert "ps_user" not in os_turn.metadata


def test_membench_extracts_embedded_turn_time_and_session_fallback(
    tmp_path: Path,
) -> None:
    """step 文本内嵌 time 应结构化到 turn_time；session_time 兜底取首个带时间戳的 turn。

    时间戳原样保留在 content（其它 method 仍能从文本读到），只是额外结构化，让
    LightMem 等时间感知 method 的 `turn.turn_time or session.session_time` 不落空。
    """

    payload = {
        "simple": {
            "roles": [
                {
                    "tid": "t-time",
                    "message_list": [
                        {
                            "user": "I love this film. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)",
                            "agent": "Nice! (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)",
                        },
                        {"user": "No timestamp here.", "agent": "Still none."},
                    ],
                    "QA": {
                        "qid": 1,
                        "question": "q?",
                        "answer": "a",
                        "target_step_id": [0],
                        "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
                        "ground_truth": "A",
                        "time": "'2024-10-01 08:00' Tuesday",
                    },
                }
            ]
        }
    }
    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, payload)
    dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(source.relative_to(tmp_path),),
    ).load()

    session = dataset.conversations[0].sessions[0]
    first_turn, second_turn = session.turns
    assert first_turn.turn_time == "2024-10-01 08:00"
    assert "time: '2024-10-01 08:00'" in first_turn.content  # 双写：文本仍保留
    assert second_turn.turn_time is None  # 无内嵌时间戳
    assert session.session_time == "2024-10-01 08:00"  # 兜底取首个带时间戳的 turn


def test_question_public_fields_and_private_gold_are_split(tmp_path: Path) -> None:
    """choices/time/question_type 公开，ground_truth/answer/target_step_id 只进 gold。"""

    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, _synthetic_payload())
    dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(source.relative_to(tmp_path),),
    ).load(limit=1)
    conversation = dataset.conversations[0]
    question = conversation.questions[0]
    gold = conversation.gold_answers[question.question_id]

    assert question.text == "Where did Maya move?"
    assert question.question_time == "'2024-10-01 08:13' Tuesday"
    assert question.category == "simple"
    assert question.metadata["choices"]["B"] == "Boston"
    assert question.options == question.metadata["choices"]
    assert gold.answer == "Boston"
    assert gold.evidence == ["1"]
    assert gold.metadata["ground_truth"] == "B"
    assert gold.metadata["target_step_id"] == [1]

    validate_no_private_keys(conversation.to_public_dict())
    with pytest.raises(DataLeakageError):
        validate_no_private_keys({"target_step_id": [1]})


def test_duplicate_conversation_id_within_one_source_file_fails_fast(tmp_path: Path) -> None:
    """同一 source file 内重复 conversation_id 会导致隔离不可靠，必须 fail-fast。"""

    payload = _synthetic_payload()
    payload["simple"]["roles"].append(payload["simple"]["roles"][0])
    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, payload)
    adapter = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(source.relative_to(tmp_path),),
    )

    with pytest.raises(DatasetValidationError, match="duplicate conversation_id"):
        adapter.load()


def test_canonical_sample_aligns_target_step_id_with_source_message() -> None:
    """真实样本中 target_step_id=0 应指向原始 message_list[0]，避免 off-by-one。"""

    dataset = MemBenchAdapter(
        ROOT,
        variant="0_10k",
        source_relative_paths=(
            Path("data/membench/Membenchdata/data2test/0-10k/ThirdAgentDataHighLevel_multiple_0.json"),
        ),
    ).load(limit=1)
    conversation = dataset.conversations[0]
    turn = conversation.sessions[0].turns[0]
    question = conversation.questions[0]
    gold = conversation.gold_answers[question.question_id]

    assert turn.turn_id == "1"
    assert turn.metadata["source_step_index"] == 0
    assert gold.evidence[0] == "0"
    assert "Casablanca" in turn.content
    assert gold.metadata["target_step_id"][0] == turn.metadata["source_step_index"]


def test_canonical_public_payload_does_not_leak_private_keys() -> None:
    """真实 MemBench 公开 payload 不得泄漏 answer/ground_truth/target_step_id。

    双保险：① validate_no_private_keys（12 条黑名单键递归扫描）；
    ② 入公共 dict 的 keys 不得出现精确命中私有关键词（防新字段绕过 validate）。
    """

    adapter = MemBenchAdapter(ROOT, variant="0_10k")
    dataset = adapter.load(limit=3)  # 覆盖多个 source 文件
    for conversation in dataset.conversations:
        public = conversation.to_public_dict()
        validate_no_private_keys(public)

    # key-level 扫描：gold_answers 已被 to_public_dict() 排除，但其 metadata 内
    # 也包含 answer/ground_truth/target_step_id，确认全量公共输出不含这些键
    public_data = {
        conv.conversation_id: conv.to_public_dict() for conv in dataset.conversations
    }
    _assert_no_private_key_in_dict(public_data, "answer")
    _assert_no_private_key_in_dict(public_data, "ground_truth")
    _assert_no_private_key_in_dict(public_data, "target_step_id")

    validate_no_private_keys(public_data)


def _assert_no_private_key_in_dict(data: object, key: str) -> None:
    """递归断言 data 中没有任何 dict 包含指定 key。"""
    if isinstance(data, dict):
        assert key not in data, f"private key '{key}' found in public dict: {list(data.keys())}"
        for v in data.values():
            _assert_no_private_key_in_dict(v, key)
    elif isinstance(data, list):
        for item in data:
            _assert_no_private_key_in_dict(item, key)


def test_dataset_metadata_includes_source_identity() -> None:
    """Dataset metadata 应包含官方来源身份和实际数据审计字段。"""

    dataset = MemBenchAdapter(ROOT, variant="0_10k").load(limit=1)
    md = dataset.metadata

    assert md["official_repo_url"] == "https://github.com/ThetaReta-CN/MemBench"
    assert md["official_paper_url"] == "https://arxiv.org/abs/2506.21605"
    assert md["license"] == "MIT"
    assert md["official_conversation_count"] == 1  # post-limit count
    assert md["official_question_count"] == 1
    assert "source_sha256" in md
    assert md["source_sha256"]
    assert len(md["source_sha256"]) == 64  # hex sha256


def test_combined_source_sha256_with_subset() -> None:
    """部分源文件的合并 SHA-256 应为确定值。"""

    dataset = MemBenchAdapter(
        ROOT,
        variant="0_10k",
        source_relative_paths=(
            Path("data/membench/Membenchdata/data2test/0-10k/ThirdAgentDataHighLevel_multiple_0.json"),
        ),
    ).load()
    md = dataset.metadata

    assert md["source_sha256"]
    assert len(md["source_sha256"]) == 64
    # 单文件：ThirdAgentDataHighLevel(0-10k) 共 400 条
    assert md["total_raw_trajectories"] == 400
    # NOTE: 全 4 源文件的 full load 会触发已知错误 —— highlevel_rec/* 中有
    # target_step_id=[] 空列表，_target_step_ids 坚持非空 → DatasetValidationError。
    # 该 bug 不在 D1 修复范围，留 D2/D3 处理。

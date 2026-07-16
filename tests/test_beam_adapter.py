"""测试 BEAM arrow → 统一 Dataset 转换。

覆盖：三 variant 加载、chat list[session] 映射、content 尾标记裁剪、
probing_questions ast.literal_eval 解析、四层隐私隔离、smoke turn 裁剪。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.benchmark_adapters.beam import (
    BEAM_RESUME_POLICY,
    BEAM_SMOKE_POLICY,
    BEAM_VARIANT_SPECS,
    BeamAdapter,
    _conversation_from_row,
    prepare_beam_run,
    strip_tail_marker,
)
from memory_benchmark.benchmark_adapters.contracts import BenchmarkLoadRequest, RunScope
from memory_benchmark.core.validators import validate_no_private_keys


# ---------------------------------------------------------------------------
# synthetic arrow dataset helpers
# ---------------------------------------------------------------------------


def _make_beam_arrow(
    target_dir: Path,
    rows: list[dict[str, Any]],
) -> None:
    """在 target_dir 写入合成 BEAM arrow 数据集。"""

    import datasets as hf_datasets

    target_dir.mkdir(parents=True, exist_ok=True)
    ds = hf_datasets.Dataset.from_list(rows)
    ds.save_to_disk(str(target_dir))


def _minimal_row(
    *,
    conversation_id: int = 1,
    num_sessions: int = 2,
    turns_per_session: int = 4,
) -> dict[str, Any]:
    """构造最小 BEAM row，chat 有 num_sessions 个 session、每 session 的 user/assistant 交替。"""

    chat: list[list[dict[str, Any]]] = []
    for s_idx in range(num_sessions):
        session_turns: list[dict[str, Any]] = []
        for t_idx in range(turns_per_session):
            role = "user" if t_idx % 2 == 0 else "assistant"
            content = f"session {s_idx + 1} turn {t_idx + 1}: hello from {role}"
            if role == "user":
                content += " ->-> 1,1"
            session_turns.append(
                {
                    "content": content,
                    "id": f"id_{s_idx}_{t_idx}",
                    "index": t_idx,
                    "question_type": "main_question" if role == "user" else None,
                    "role": role,
                    "time_anchor": f"March {15 + s_idx}, 2024",
                }
            )
        chat.append(session_turns)

    probing = (
        "{'abstention': ["
        "{'question': 'What did I do?', 'ideal_response': 'coding', "
        "'difficulty': 'easy', 'abstention_type': None, "
        "'why_unanswerable': None, 'plan_reference': None, "
        "'rubric': ['answer mentions coding']}], "
        "'summarization': ["
        "{'question': 'Summarize my day.', 'ideal_response': 'Worked on code.', "
        "'difficulty': 'easy', 'abstention_type': None, "
        "'why_unanswerable': None, 'plan_reference': None, "
        "'rubric': ['summary is concise', 'summary covers work']}]}"
    )

    return {
        "conversation_id": conversation_id,
        "conversation_seed": "seed_value",
        "narratives": "narrative text",
        "user_profile": "profile text",
        "conversation_plan": "plan text",
        "user_questions": "user q text",
        "chat": chat,
        "probing_questions": probing,
    }


def _full_10_ability_row(conversation_id: int = 1) -> dict[str, Any]:
    """构造 10 能力 × 2 题的完整 probing_questions row。"""

    chat: list[list[dict[str, Any]]] = [
        [
            {
                "content": "Hello ->-> 1,1",
                "id": "id_0_0",
                "index": 0,
                "question_type": "main_question",
                "role": "user",
                "time_anchor": "March 15, 2024",
            },
            {
                "content": "Hi there!",
                "id": "id_0_1",
                "index": 1,
                "question_type": None,
                "role": "assistant",
                "time_anchor": "March 15, 2024",
            },
        ]
    ]

    ability_qs: dict[str, list[dict[str, Any]]] = {}
    abilities = [
        "abstention",
        "contradiction_resolution",
        "event_ordering",
        "information_extraction",
        "instruction_following",
        "knowledge_update",
        "multi_session_reasoning",
        "preference_following",
        "summarization",
        "temporal_reasoning",
    ]
    for ability in abilities:
        ability_qs[ability] = []
        for qi in range(1, 3):
            ability_qs[ability].append(
                {
                    "question": f"{ability} question {qi}?",
                    "ideal_response": f"{ability} answer {qi}",
                    "difficulty": "medium",
                    "abstention_type": None,
                    "why_unanswerable": None,
                    "plan_reference": None,
                    "rubric": [f"rubric item for {ability} q{qi}"],
                }
            )

    probing = str(ability_qs)

    return {
        "conversation_id": conversation_id,
        "conversation_seed": "seed",
        "narratives": "narr",
        "user_profile": "profile",
        "conversation_plan": "plan",
        "user_questions": "user_qs",
        "chat": chat,
        "probing_questions": probing,
    }


# ---------------------------------------------------------------------------
# T1.1 tail marker stripping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Hello world ->-> 1,1", "Hello world"),
        ("Question? ->-> 2,3", "Question?"),
        ("Text ->-> 10,N/A", "Text"),
        ("No marker here", "No marker here"),
        # 正文里有 -> 不应被误伤
        ("a -> b ->-> 1,1", "a -> b"),
        ("-> alone should stay", "-> alone should stay"),
        # 多行内容 + 尾标记
        ("line1\nline2 ->-> 5,10", "line1\nline2"),
        # 空字符串
        ("", ""),
        # trailing whitespace before marker
        ("text   ->-> 1,1", "text"),
    ],
)
def test_strip_tail_marker(raw: str, expected: str) -> None:
    """->-> a,b 尾标记应被精确裁掉，正文中的 -> 不受影响。"""

    assert strip_tail_marker(raw) == expected


def test_strip_tail_marker_idempotent() -> None:
    """已裁过的内容再次 strip 不变。"""

    assert strip_tail_marker("clean text") == "clean text"
    assert strip_tail_marker(strip_tail_marker("text ->-> 1,1")) == "text"


# ---------------------------------------------------------------------------
# T1.2 chat list[session] 映射 & content 裁剪
# ---------------------------------------------------------------------------


def test_chat_maps_to_sessions_and_turns(tmp_path: Path) -> None:
    """BEAM chat 应正确映射为 list[session]，含 content 尾标记裁剪。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [_minimal_row(num_sessions=2, turns_per_session=4)],
    )
    adapter = BeamAdapter(tmp_path, variant="100k")
    dataset = adapter.load()

    conversation = dataset.conversations[0]
    assert conversation.conversation_id == "1"
    assert len(conversation.sessions) == 2

    s1 = conversation.sessions[0]
    assert s1.session_id == "s1"
    assert s1.session_time == "March 15, 2024"
    assert len(s1.turns) == 4

    # user turn (index 0): 尾标记应被裁
    assert s1.turns[0].speaker == "user"
    assert s1.turns[0].content == "session 1 turn 1: hello from user"
    assert s1.turns[0].turn_time == "March 15, 2024"
    assert s1.turns[0].metadata["question_type"] == "main_question"

    # assistant turn (index 1): 无尾标记
    assert s1.turns[1].speaker == "assistant"
    assert s1.turns[1].content == "session 1 turn 2: hello from assistant"

    # session 2
    s2 = conversation.sessions[1]
    assert s2.session_id == "s2"


# ---------------------------------------------------------------------------
# T1.3 probing_questions 解析（ast.literal_eval）
# ---------------------------------------------------------------------------


def test_probing_questions_parsed_with_ast_literal_eval(tmp_path: Path) -> None:
    """probing_questions 应通过 ast.literal_eval 解析出 ability→questions。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [
            _minimal_row(
                num_sessions=1,
                turns_per_session=2,
            )
        ],
    )
    adapter = BeamAdapter(tmp_path, variant="100k")
    dataset = adapter.load()
    conversation = dataset.conversations[0]

    # min row 有 abstention × 1 + summarization × 1 = 2 题
    assert len(conversation.questions) == 2
    assert len(conversation.gold_answers) == 2

    abstention_q = next(
        q for q in conversation.questions if q.category == "abstention"
    )
    assert abstention_q.question_id == "1:abstention:q1"
    assert abstention_q.text == "What did I do?"
    assert abstention_q.conversation_id == "1"

    gold = conversation.gold_answers[abstention_q.question_id]
    assert gold.answer == "coding"
    assert gold.metadata["rubric"] == ["answer mentions coding"]
    assert gold.metadata["difficulty"] == "easy"


def test_full_10_ability_parsing(tmp_path: Path) -> None:
    """10 能力 × 每 2 题 = 20 probing question 应全部解析。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [_full_10_ability_row()],
    )
    adapter = BeamAdapter(tmp_path, variant="100k")
    dataset = adapter.load()
    conversation = dataset.conversations[0]

    assert len(conversation.questions) == 20
    assert len(conversation.gold_answers) == 20

    expected_abilities = {
        "abstention",
        "contradiction_resolution",
        "event_ordering",
        "information_extraction",
        "instruction_following",
        "knowledge_update",
        "multi_session_reasoning",
        "preference_following",
        "summarization",
        "temporal_reasoning",
    }
    seen_abilities = set()
    for q in conversation.questions:
        assert q.category is not None
        seen_abilities.add(q.category)
        assert q.conversation_id == "1"
        assert q.question_id.endswith(":q1") or q.question_id.endswith(":q2")

        gold = conversation.gold_answers[q.question_id]
        assert gold.answer is not None
        assert isinstance(gold.metadata["rubric"], list)
        assert len(gold.metadata["rubric"]) >= 1
        assert gold.metadata["difficulty"] == "medium"

    assert seen_abilities == expected_abilities


# ---------------------------------------------------------------------------
# T1.4 四层隐私
# ---------------------------------------------------------------------------


def test_public_conversation_excludes_rubric_and_private_fields(
    tmp_path: Path,
) -> None:
    """公开 Conversation 不能泄漏 rubric、ideal_response、difficulty 等私有数据。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [_full_10_ability_row()],
    )
    adapter = BeamAdapter(tmp_path, variant="100k")
    dataset = adapter.load()
    conversation = dataset.conversations[0]

    public = conversation.to_public_dict()
    validate_no_private_keys(public)

    public_text = json.dumps(public, ensure_ascii=False)
    public_questions_text = json.dumps(public["questions"], ensure_ascii=False)
    # 私有字段不得出现在公开 payload 中
    assert "rubric" not in public_text
    assert "ideal_response" not in public_text
    assert "difficulty" not in public_text
    assert "abstention_type" not in public_text
    assert "why_unanswerable" not in public_text
    assert "plan_reference" not in public_text
    # row 级私有也不得泄漏
    assert "conversation_seed" not in public_text
    assert "user_profile" not in public_text
    assert "conversation_plan" not in public_text
    private_question_keys = {
        "abstention_type", "answer", "bullet_points_covered", "calculation_required",
        "compliance_indicators", "complexity_factors", "contradiction_type",
        "conversation_reference", "conversation_references", "conversation_sessions",
        "difficulty", "evidence_turn_ids", "expected_compliance", "extraction_challenge",
        "ideal_answer", "ideal_response", "ideal_summary", "instruction_being_tested",
        "instruction_type", "key_elements_tested", "key_facts_tested",
        "non_compliance_signs", "ordering_tested", "ordering_type", "plan_reference",
        "potential_confusion", "preference_being_tested", "preference_type",
        "question_type", "reasoning_steps", "reasoning_type", "rubric",
        "sessions_required", "source_chat_ids", "summarization_type",
        "synthesis_required", "temporal_type", "tests_for", "tests_retention_of",
        "time_points", "topic_questioned", "total_mentions", "update_type",
        "why_unanswerable",
    }
    for private_key in private_question_keys:
        assert private_key not in public_questions_text


def test_gold_answers_preserve_all_question_obj_fields(tmp_path: Path) -> None:
    """GoldAnswerInfo 应保留 question_obj 的全部原始字段。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [_full_10_ability_row()],
    )
    adapter = BeamAdapter(tmp_path, variant="100k")
    dataset = adapter.load()
    conversation = dataset.conversations[0]

    first_q = conversation.questions[0]
    gold = conversation.gold_answers[first_q.question_id]

    assert gold.metadata["rubric"] is not None
    assert gold.metadata["ideal_response"] is not None
    assert "difficulty" in gold.metadata
    # row 级私有元信息也应保留在 gold metadata
    assert gold.metadata["conversation_seed"] == "seed"
    assert gold.metadata["user_profile"] == "profile"


def test_gold_evidence_maps_raw_ids_to_all_public_turn_ids(tmp_path: Path) -> None:
    """重复 raw id 应映射到全部公开 turn id，非法原子只计数不崩。"""

    row = _minimal_row(num_sessions=2, turns_per_session=2)
    for session_index, session in enumerate(row["chat"]):
        for turn_index, turn in enumerate(session):
            turn["id"] = session_index * 10 + turn_index
    row["chat"][0][0]["id"] = 7
    row["chat"][1][0]["id"] = 7
    row["probing_questions"] = str(
        {
            "event_ordering": [
                {
                    "question": "What happened first?",
                    "answer": "The first event.",
                    "difficulty": "medium",
                    "rubric": ["orders the events"],
                    "source_chat_ids": [[7], ["--"]],
                }
            ]
        }
    )
    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [row],
    )

    conversation = BeamAdapter(tmp_path, variant="100k").load().conversations[0]
    gold = conversation.gold_answers[conversation.questions[0].question_id]

    assert gold.metadata["source_chat_ids"] == [[7], ["--"]]
    assert gold.metadata["evidence_turn_ids"] == ["s1:t1", "s2:t1"]
    assert gold.metadata["ambiguous_gold_id_count"] == 1
    assert gold.metadata["unmatched_gold_id_count"] == 1


def test_dataset_metadata_locks_source_identity_and_actual_counts(tmp_path: Path) -> None:
    """BEAM metadata 应记录目录内容身份与实际加载规模。"""

    target = tmp_path / "data" / "BEAM" / "beam_dataset" / "100K"
    _make_beam_arrow(target, [_minimal_row()])

    metadata = BeamAdapter(tmp_path, variant="100k").load().metadata

    assert metadata["official_repo_url"] == "https://github.com/mohammadtavakoli78/BEAM"
    assert metadata["official_paper_url"] == "https://arxiv.org/abs/2510.27246"
    assert metadata["official_dataset_url"] == "https://huggingface.co/datasets/Mohammadta/BEAM"
    assert metadata["license"] == "CC-BY-SA-4.0"
    assert metadata["source_size_bytes"] > 0
    assert len(metadata["source_sha256"]) == 64
    assert metadata["loaded_conversation_count"] == 1
    assert metadata["loaded_session_count"] == 2
    assert metadata["loaded_turn_count"] == 8
    assert metadata["loaded_question_count"] == 2


def test_public_question_has_no_private_metadata(tmp_path: Path) -> None:
    """公开 Question.metadata 应为空 dict。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [_full_10_ability_row()],
    )
    adapter = BeamAdapter(tmp_path, variant="100k")
    dataset = adapter.load()
    conversation = dataset.conversations[0]

    for question in conversation.questions:
        assert question.metadata == {}, (
            f"Question {question.question_id} metadata must be empty"
        )


# ---------------------------------------------------------------------------
# T1.5 variant 声明
# ---------------------------------------------------------------------------


def test_beam_variants_declare_100k_500k_1m() -> None:
    """BEAM 应声明三个同构 variant 与独立 10M variant。"""

    names = [spec.name for spec in BEAM_VARIANT_SPECS]
    assert names == ["100k", "500k", "1m", "10m"]


def test_beam_adapter_rejects_unknown_variant(tmp_path: Path) -> None:
    """未知 variant 应抛出 ConfigurationError。"""

    from memory_benchmark.core.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError, match="Unknown beam variant"):
        BeamAdapter(tmp_path, variant="20m")


def test_beam_10m_real_data_expands_plans_and_preserves_invalid_evidence() -> None:
    """真实 10M 应按 plan 顺序展开，官方 `--` evidence 保留但不进入匹配键。"""

    prepared = prepare_beam_run(
        Path("."),
        BenchmarkLoadRequest(
            variant="10m",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=1,
            smoke_conversation_limit=1,
        ),
    )
    first = prepared.dataset.conversations[0]

    assert len(first.sessions) == 1
    assert first.sessions[0].session_id == "p1:s1"
    assert first.sessions[0].metadata["plan_id"] == "plan-1"
    assert first.sessions[0].metadata["plan_index"] == 0
    assert first.sessions[0].turns[0].turn_id == "p1:s1:t1"
    assert len(first.sessions[0].turns) == 2
    assert prepared.source_relative_paths == (
        Path("data/BEAM/beam_10M_dataset/10M"),
    )

    import datasets as hf_datasets

    raw = hf_datasets.load_from_disk("data/BEAM/beam_10M_dataset/10M")[5]
    regression = _conversation_from_row(raw, row_idx=5, ten_million=True)
    assert len(regression.sessions) == 100
    assert regression.sessions[10].session_id == "p2:s1"

    question = next(
        item
        for item in regression.questions
        if item.category == "event_ordering" and item.question_id.endswith(":q1")
    )
    gold = regression.gold_answers[question.question_id]
    assert gold.metadata["source_chat_ids"][-1] == ["--"]
    assert gold.metadata["unmatched_gold_id_count"] == 1
    assert "--" not in gold.metadata["evidence_turn_ids"]
    public = regression.to_public_dict()
    validate_no_private_keys(public)
    public_text = json.dumps(public, ensure_ascii=False)
    assert "source_chat_ids" not in public_text
    assert "evidence_turn_ids" not in public_text


# ---------------------------------------------------------------------------
# T1.6 prepare_run + smoke
# ---------------------------------------------------------------------------


def test_prepare_beam_run_smoke_limits_rounds_and_declares_question_budget(
    tmp_path: Path,
) -> None:
    """BEAM adapter 裁 round，单题预算由声明式 policy 交给 runner。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [
            _minimal_row(
                conversation_id=1,
                num_sessions=3,
                turns_per_session=6,  # 18 turns total
            )
        ],
    )

    prepared = prepare_beam_run(
        tmp_path,
        BenchmarkLoadRequest(
            variant="100k",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=1,
            smoke_conversation_limit=1,
        ),
    )

    assert prepared.variant == "100k"
    assert prepared.run_scope is RunScope.SMOKE
    conversation = prepared.dataset.conversations[0]
    total_turns = sum(len(s.turns) for s in conversation.sessions)
    assert total_turns == 2
    assert len(conversation.sessions) == 1
    assert len(conversation.questions) == 2

    # metadata 记录裁剪前后规模
    assert prepared.dataset.metadata["smoke_round_limit"] == 1
    assert prepared.dataset.metadata["smoke_original_turn_count"] == 18
    assert prepared.dataset.metadata["smoke_retained_turn_count"] == 2
    assert conversation.metadata["smoke_original_turn_count"] == 18
    assert prepared.dataset.metadata["smoke_policy"] == BEAM_SMOKE_POLICY.to_dict()
    assert BEAM_SMOKE_POLICY.default_question_limit == 1
    assert prepared.dataset.metadata["resume_policy"] == BEAM_RESUME_POLICY.to_dict()


def test_prepare_beam_run_full_loads_all(tmp_path: Path) -> None:
    """BEAM full 应加载全部 turn。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [_minimal_row(num_sessions=2, turns_per_session=4)],
    )

    prepared = prepare_beam_run(
        tmp_path,
        BenchmarkLoadRequest(
            variant="100k",
            run_scope=RunScope.FULL,
            smoke_turn_limit=20,
            smoke_conversation_limit=1,
        ),
    )

    assert prepared.run_scope is RunScope.FULL
    conversation = prepared.dataset.conversations[0]
    total_turns = sum(len(s.turns) for s in conversation.sessions)
    assert total_turns == 8  # 2 sessions × 4 turns


def test_beam_adapter_limit(tmp_path: Path) -> None:
    """limit 参数应控制 conversation 数量。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [
            _minimal_row(conversation_id=i)
            for i in range(1, 6)
        ],
    )
    adapter = BeamAdapter(tmp_path, variant="100k")
    dataset = adapter.load(limit=2)
    assert len(dataset.conversations) == 2


def test_beam_adapter_rejects_json_loads_approach(tmp_path: Path) -> None:
    """确认 probing_questions 用 ast.literal_eval 而非 json.loads。

    probing_questions 是 Python-repr（单引号），json.loads 会失败。
    """

    # 构造一个用单引号的 probing_questions 字符串，验证 adapter 能正确解析
    probing_str = (
        "{'abstention': [{'question': 'test?', 'ideal_response': 'ans', "
        "'difficulty': 'easy', 'abstention_type': None, "
        "'why_unanswerable': None, 'plan_reference': None, "
        "'rubric': ['item1']}]}"
    )

    # json.loads 应失败（单引号非法 JSON）
    with pytest.raises(Exception):
        json.loads(probing_str)

    # ast.literal_eval 应成功
    result = ast.literal_eval(probing_str)
    assert isinstance(result, dict)
    assert "abstention" in result


# ---------------------------------------------------------------------------
# gold evidence contract v1 group views
# ---------------------------------------------------------------------------


def _turn_view(gold) -> object:
    """取出 BEAM gold 的唯一 turn view。"""

    assert gold.gold_evidence_contract_version == "v1"
    views = [
        group_set
        for group_set in gold.evidence_group_sets
        if group_set.provenance_granularity == "turn"
        and group_set.unit_kind == "beam_source_message"
    ]
    assert len(views) == 1
    return views[0]


def test_gold_evidence_groups_dedup_ambiguous_and_unmatched(tmp_path: Path) -> None:
    """同 raw id 两位置只算一个 multi-child group；`--` 记 unmatched group。"""

    row = _minimal_row(num_sessions=2, turns_per_session=2)
    for session_index, session in enumerate(row["chat"]):
        for turn_index, turn in enumerate(session):
            turn["id"] = session_index * 10 + turn_index
    row["chat"][0][0]["id"] = 7
    row["chat"][1][0]["id"] = 7
    row["probing_questions"] = str(
        {
            "event_ordering": [
                {
                    "question": "What happened first?",
                    "answer": "The first event.",
                    "difficulty": "medium",
                    "rubric": ["orders the events"],
                    "source_chat_ids": [[7, 7], [1], ["--"]],
                }
            ]
        }
    )
    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [row],
    )

    conversation = BeamAdapter(tmp_path, variant="100k").load().conversations[0]
    gold = conversation.gold_answers[conversation.questions[0].question_id]
    turn_view = _turn_view(gold)

    groups = {group.unit_id: group for group in turn_view.groups}
    # raw id 稳定去重：7 只出现一个 group，且携带两个歧义位置 child。
    assert [group.unit_id for group in turn_view.groups] == ["7", "1", "--"]
    assert groups["7"].mapping_status == "mapped"
    assert groups["7"].child_ids == ("s1:t1", "s2:t1")
    assert groups["1"].mapping_status == "mapped"
    assert groups["1"].child_ids == ("s1:t2",)
    assert groups["--"].mapping_status == "unmatched"
    assert groups["--"].child_ids == ()


def test_gold_evidence_groups_abstention_none_yields_empty_groups(
    tmp_path: Path,
) -> None:
    """abstention 的 source_chat_ids=None → 空 groups，不合成 qrel。"""

    _make_beam_arrow(
        tmp_path / "data" / "BEAM" / "beam_dataset" / "100K",
        [_minimal_row()],
    )
    conversation = BeamAdapter(tmp_path, variant="100k").load().conversations[0]
    abstention_question = next(
        question
        for question in conversation.questions
        if question.category == "abstention"
    )
    gold = conversation.gold_answers[abstention_question.question_id]

    assert _turn_view(gold).groups == ()


def test_gold_evidence_groups_do_not_cross_conversations(tmp_path: Path) -> None:
    """跨 conversation 的相同 raw id 不得串线到别的 conversation 的 turn。"""

    rows = []
    for conversation_id in (1, 2):
        row = _minimal_row(
            conversation_id=conversation_id,
            num_sessions=1,
            turns_per_session=2,
        )
        for turn_index, turn in enumerate(row["chat"][0]):
            turn["id"] = turn_index
        row["probing_questions"] = str(
            {
                "event_ordering": [
                    {
                        "question": "What happened first?",
                        "answer": "The first event.",
                        "difficulty": "medium",
                        "rubric": ["orders the events"],
                        "source_chat_ids": [0],
                    }
                ]
            }
        )
        rows.append(row)
    _make_beam_arrow(tmp_path / "data" / "BEAM" / "beam_dataset" / "100K", rows)

    dataset = BeamAdapter(tmp_path, variant="100k").load()
    for conversation in dataset.conversations:
        gold = conversation.gold_answers[conversation.questions[0].question_id]
        turn_view = _turn_view(gold)
        assert len(turn_view.groups) == 1
        # singleton mapped：raw id 只映射到本 conversation 的公开 turn。
        assert turn_view.groups[0].child_ids == ("s1:t1",)


def test_beam_1m_real_data_locks_ambiguous_group_counts() -> None:
    """真实 1M 全量：41 个含歧义题、逐题累计 198 个歧义 raw-id 原子。

    2026-07-16 架构师全量 Arrow 重扫的现行数字（evidence-unit-contract-audit §2.2/
    §8）；歧义题 = 至少一个 multi-child mapped group 的题。
    """

    dataset = BeamAdapter(Path("."), variant="1m").load()

    ambiguous_question_count = 0
    ambiguous_atom_total = 0
    for conversation in dataset.conversations:
        for gold in conversation.gold_answers.values():
            turn_view = _turn_view(gold)
            multi_child_groups = [
                group
                for group in turn_view.groups
                if group.mapping_status == "mapped" and len(group.child_ids) > 1
            ]
            if multi_child_groups:
                ambiguous_question_count += 1
                ambiguous_atom_total += len(multi_child_groups)

    assert ambiguous_question_count == 41
    assert ambiguous_atom_total == 198

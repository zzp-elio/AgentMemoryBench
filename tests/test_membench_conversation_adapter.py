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
from memory_benchmark.runners.event_stream import build_turn_events


# 强反例的固定常量：message 内嵌一个过去时刻，QA.time 用明显不同的未来日期。
# 二者必须始终分居不同字段，绝不能串到一起。
_MSG_EMBEDDED_TIME = "2025-06-30 14:00"
_QA_FUTURE_TIME_RAW = "'2099-12-31 23:59' Sunday"


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
    """PS dict step 应拆成 user+assistant 两条 canonical turn，OS string step 原样保留。"""

    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, _synthetic_payload())

    adapter = MemBenchAdapter(tmp_path, variant="0_10k", source_relative_paths=(source.relative_to(tmp_path),))
    dataset = adapter.load()

    assert dataset.dataset_name == "membench"
    assert dataset.metadata["variant"] == "0_10k"
    assert len(dataset.conversations) == 2

    ps_conversation = dataset.conversations[0]
    ps_turns = ps_conversation.sessions[0].turns
    assert ps_conversation.conversation_id == "first-low-simple-roles-ps-1"
    # 一个 dict step 拆成 user + assistant 两条 canonical turn；两个 step 共 4 条。
    assert [t.turn_id for t in ps_turns] == ["1:user", "1:assistant", "2:user", "2:assistant"]

    step1_user, step1_assistant = ps_turns[0], ps_turns[1]
    assert step1_user.speaker == "user"
    assert step1_user.normalized_role == "user"
    assert step1_user.content == "I work with Maya."
    assert step1_user.metadata["ps_user"] == "I work with Maya."
    assert "ps_agent" not in step1_user.metadata  # peer 原文不复制进本 child
    assert step1_user.metadata["source_step_index"] == 0
    assert step1_user.metadata["source_step_number"] == 1
    assert step1_user.metadata["source_step_role"] == "user"

    assert step1_assistant.speaker == "agent"
    assert step1_assistant.normalized_role == "assistant"
    assert step1_assistant.content == "Maya is your colleague."
    assert step1_assistant.metadata["ps_agent"] == "Maya is your colleague."
    assert "ps_user" not in step1_assistant.metadata  # peer 原文不复制进本 child
    assert step1_assistant.metadata["source_step_index"] == 0
    assert step1_assistant.metadata["source_step_number"] == 1
    assert step1_assistant.metadata["source_step_role"] == "agent"

    # 旧 composite 字符串（`'user': ...; 'agent': ...`）不得存在于任何 child content。
    for turn in ps_turns:
        assert "'user':" not in turn.content
        assert "; 'agent':" not in turn.content

    os_conversation = dataset.conversations[1]
    os_turn = os_conversation.sessions[0].turns[0]
    assert os_conversation.conversation_id == "first-low-simple-observations-os-1"
    assert os_turn.turn_id == "1"
    assert os_turn.speaker == "user"
    assert os_turn.normalized_role == "user"
    assert os_turn.content == "My favorite cafe is Blue Bottle."
    assert os_turn.metadata["source_step_index"] == 0
    assert os_turn.metadata["source_step_role"] == "observation"
    assert "ps_user" not in os_turn.metadata


def _future_time_counterexample_payload(*, first_person: bool) -> dict[str, Any]:
    """构造时间语义强反例 payload：首条 message 无时间、次条内嵌一个过去时刻、
    QA.time 用明显不同的未来日期。

    first_person=True 时 message 为 {user, agent} dict（FirstAgent 源）；否则为
    纯字符串 step（ThirdAgent 源）。两种 step 形态必须产出完全一致的时间语义。
    """

    if first_person:
        message_list: list[Any] = [
            {"user": "No timestamp noise here.", "agent": "Still nothing."},
            {
                "user": (
                    f"I watched it. (place: Boston, MA; time: '{_MSG_EMBEDDED_TIME}' Monday)"
                ),
                "agent": (
                    f"Noted. (place: Boston, MA; time: '{_MSG_EMBEDDED_TIME}' Monday)"
                ),
            },
        ]
    else:
        message_list = [
            "No timestamp noise here.",
            f"They watched it. (place: Boston, MA; time: '{_MSG_EMBEDDED_TIME}' Monday)",
        ]
    return {
        "simple": {
            "roles": [
                {
                    "tid": "t-future",
                    "message_list": message_list,
                    "QA": {
                        "qid": 1,
                        "question": "q?",
                        "answer": "a",
                        "target_step_id": [1],
                        "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
                        "ground_truth": "A",
                        "time": _QA_FUTURE_TIME_RAW,
                    },
                }
            ]
        }
    }


def test_membench_third_agent_missing_message_time_stays_none_without_session_smear(
    tmp_path: Path,
) -> None:
    """ThirdAgent：无时间 message 保持 turn_time=None，session_time 显式为 None。

    强反例：首条无时间 noise、次条内嵌过去时刻、QA.time 为未来日期。断言单向
    时间流——message 内嵌时间 → 该 turn.turn_time；message 无时间 → None；
    MemBench 无原生 session 时间 → session_time=None（不取兄弟 turn）；QA.time
    只进入 question_time。
    """

    source = tmp_path / "data2test" / "0-10k" / "ThirdAgentDataHighLevel_multiple_0.json"
    _write_fixture(source, _future_time_counterexample_payload(first_person=False))
    dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(source.relative_to(tmp_path),),
    ).load()

    conversation = dataset.conversations[0]
    session = conversation.sessions[0]
    # 无时间 noise 未被过滤：两条 turn 都在
    assert len(session.turns) == 2
    first_turn, second_turn = session.turns

    # 首条无时间 noise：turn_time=None，content 逐字保留，不含 message 时间或 QA 时间
    assert first_turn.turn_time is None
    assert "No timestamp noise here." in first_turn.content
    assert _MSG_EMBEDDED_TIME not in first_turn.content
    assert "2099" not in first_turn.content

    # 次条：turn_time 只等于自身内嵌时间；原文 place/time 一并保留
    assert second_turn.turn_time == _MSG_EMBEDDED_TIME
    assert f"time: '{_MSG_EMBEDDED_TIME}'" in second_turn.content
    assert "place: Boston, MA" in second_turn.content
    assert "2099" not in second_turn.content

    # MemBench 无原生 session 时间：显式 None，绝不取兄弟 turn 时间伪造
    assert session.session_time is None

    # QA.time 单向流入 question_time，原样保留，且与 message 时间明显不同
    question = conversation.questions[0]
    assert question.question_time == _QA_FUTURE_TIME_RAW
    assert question.question_time != second_turn.turn_time


def test_membench_first_agent_missing_message_time_stays_none_per_child(
    tmp_path: Path,
) -> None:
    """FirstAgent：拆分后每个 child 只从自身 content 解析时间，不跨 user/agent fallback。

    第一个 dict step 的 user/agent 两侧都无时间 noise；第二个 dict step 的
    user/agent 两侧都内嵌相同时间戳（`_MSG_EMBEDDED_TIME`）。四条 canonical
    turn 逐条断言：turn_time 只取自身 content 解析结果，session_time 仍
    None，QA 未来日期绝不串入任何一侧。
    """

    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, _future_time_counterexample_payload(first_person=True))
    dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(source.relative_to(tmp_path),),
    ).load()

    conversation = dataset.conversations[0]
    session = conversation.sessions[0]
    assert len(session.turns) == 4
    step1_user, step1_assistant, step2_user, step2_assistant = session.turns

    # step 1（无时间 noise）：user、assistant 两侧都 None，内容原样保留
    assert step1_user.turn_time is None
    assert "No timestamp noise here." in step1_user.content
    assert step1_assistant.turn_time is None
    assert "Still nothing." in step1_assistant.content
    for turn in (step1_user, step1_assistant):
        assert _MSG_EMBEDDED_TIME not in turn.content
        assert "2099" not in turn.content

    # step 2（两侧都内嵌同一时间戳）：各自独立解析，互不依赖对方
    assert step2_user.turn_time == _MSG_EMBEDDED_TIME
    assert f"time: '{_MSG_EMBEDDED_TIME}'" in step2_user.content
    assert "place: Boston, MA" in step2_user.content
    assert step2_assistant.turn_time == _MSG_EMBEDDED_TIME
    assert f"time: '{_MSG_EMBEDDED_TIME}'" in step2_assistant.content
    assert "place: Boston, MA" in step2_assistant.content
    for turn in (step2_user, step2_assistant):
        assert "2099" not in turn.content

    # MemBench 无原生 session 时间
    assert session.session_time is None

    question = conversation.questions[0]
    assert question.question_time == _QA_FUTURE_TIME_RAW
    assert question.question_time != step2_user.turn_time


def test_membench_first_agent_time_is_per_child_not_cross_side_fallback(
    tmp_path: Path,
) -> None:
    """强反例：user/agent 时间不同、只一侧有时间、两侧都无时间——三态互不 fallback。

    旧实现 `_membench_turn_time(user_text) or _membench_turn_time(agent_text)`
    会让「只 agent 侧有时间」的 step 错误地让 composite turn 拿到该时间；拆分后
    user child 必须保持 turn_time=None，不得沿用 agent 侧的值，反之亦然。
    """

    user_only_time = "2024-11-01 10:00"
    agent_only_time = "2024-12-01 11:00"
    payload = {
        "simple": {
            "roles": [
                {
                    "tid": "t-cross-side",
                    "message_list": [
                        {
                            # step 0：只 user 侧有时间
                            "user": f"I saw it. (place: NYC; time: '{user_only_time}' Friday)",
                            "agent": "Noted, no time here.",
                        },
                        {
                            # step 1：只 agent 侧有时间
                            "user": "Just chatting, no time here.",
                            "agent": f"Got it. (place: NYC; time: '{agent_only_time}' Sunday)",
                        },
                        {
                            # step 2：两侧都无时间
                            "user": "Neither side has a timestamp.",
                            "agent": "Confirmed, still no timestamp.",
                        },
                    ],
                    "QA": {
                        "qid": 1,
                        "question": "q?",
                        "answer": "a",
                        "target_step_id": [0, 1, 2],
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
    turns = dataset.conversations[0].sessions[0].turns
    assert len(turns) == 6
    step0_user, step0_assistant, step1_user, step1_assistant, step2_user, step2_assistant = turns

    # step 0：只 user 侧有时间；assistant 侧绝不沿用 user 的时间
    assert step0_user.turn_time == user_only_time
    assert step0_assistant.turn_time is None

    # step 1：只 agent 侧有时间；user 侧绝不沿用 agent 的时间（旧 bug 的核心反例）
    assert step1_user.turn_time is None
    assert step1_assistant.turn_time == agent_only_time

    # step 2：两侧都无时间
    assert step2_user.turn_time is None
    assert step2_assistant.turn_time is None

    # marker 与 turn_time 完全同步
    assert step0_user.metadata["source_timestamp_embedded_in_content"] is True
    assert step0_assistant.metadata["source_timestamp_embedded_in_content"] is False
    assert step1_user.metadata["source_timestamp_embedded_in_content"] is False
    assert step1_assistant.metadata["source_timestamp_embedded_in_content"] is True
    assert step2_user.metadata["source_timestamp_embedded_in_content"] is False
    assert step2_assistant.metadata["source_timestamp_embedded_in_content"] is False


def test_membench_build_turn_events_keeps_missing_timestamp_none(
    tmp_path: Path,
) -> None:
    """对强反例调用 build_turn_events：无时间 turn 的 event.timestamp 与
    original_turn_time 均为 None，有时间 turn 只取自身 turn_time；四条 event
    （2 步 × user/assistant）顺序为 user→assistant→user→assistant，
    original_session_time 都为 None；任何 event 字段都不出现 QA 的未来日期。
    """

    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, _future_time_counterexample_payload(first_person=True))
    dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(source.relative_to(tmp_path),),
    ).load()
    conversation = dataset.conversations[0]

    events = list(build_turn_events(conversation, isolation_key="run_t-future"))
    assert len(events) == 4
    step1_user, step1_assistant, step2_user, step2_assistant = events

    # event 顺序与原文 turn_id 保真，user 先于 assistant
    assert [e.turn_id for e in events] == [
        "1:user",
        "1:assistant",
        "2:user",
        "2:assistant",
    ]

    # step 1（无时间 noise）：两条 event 的 timestamp/original_turn_time 都 None
    assert step1_user.timestamp is None
    assert step1_user.metadata["original_turn_time"] is None
    assert step1_assistant.timestamp is None
    assert step1_assistant.metadata["original_turn_time"] is None

    # step 2：两条 event 各自只取自身 turn_time
    assert step2_user.timestamp == _MSG_EMBEDDED_TIME
    assert step2_user.metadata["original_turn_time"] == _MSG_EMBEDDED_TIME
    assert step2_assistant.timestamp == _MSG_EMBEDDED_TIME
    assert step2_assistant.metadata["original_turn_time"] == _MSG_EMBEDDED_TIME

    for event in events:
        # 无 session smear：original_session_time 保持 None
        assert event.metadata["original_session_time"] is None
        # QA 的未来日期不得进入任何 event 字段（timestamp/content/metadata）
        assert "2099" not in repr(event)


def test_membench_parses_both_embedded_time_formats_and_keeps_content(
    tmp_path: Path,
) -> None:
    """两种官方内嵌时间格式（`time: '…'` 与无冒号 `time'…'`）都能解析到 turn_time，
    且原 content 中完整 message、place、time 子串逐字保留，不做去重删除。
    """

    colon_user = "I loved the show. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
    nocolon_user = "They loved it. (place: Austin, TX; time'2024-10-02 09:30' Wednesday)"
    payload = {
        "simple": {
            "roles": [
                {
                    "tid": "t-formats",
                    "message_list": [
                        {"user": colon_user, "agent": "ok"},
                        {"user": nocolon_user, "agent": "ok"},
                    ],
                    "QA": {
                        "qid": 1,
                        "question": "q?",
                        "answer": "a",
                        "target_step_id": [0],
                        "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
                        "ground_truth": "A",
                        "time": _QA_FUTURE_TIME_RAW,
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
    assert len(session.turns) == 4
    colon_turn, colon_agent_turn, nocolon_turn, nocolon_agent_turn = session.turns

    # 有冒号格式（user 侧）
    assert colon_turn.turn_time == "2024-10-01 08:00"
    assert "I loved the show." in colon_turn.content
    assert "place: Boston, MA" in colon_turn.content
    assert "time: '2024-10-01 08:00'" in colon_turn.content
    assert colon_turn.metadata["source_timestamp_embedded_in_content"] is True

    # 同一 step 的 agent 侧内容是 "ok"，本身无时间：不得沿用 user 侧的时间
    assert colon_agent_turn.content == "ok"
    assert colon_agent_turn.turn_time is None
    assert colon_agent_turn.metadata["source_timestamp_embedded_in_content"] is False

    # 无冒号格式（user 侧）
    assert nocolon_turn.turn_time == "2024-10-02 09:30"
    assert "They loved it." in nocolon_turn.content
    assert "place: Austin, TX" in nocolon_turn.content
    assert "time'2024-10-02 09:30'" in nocolon_turn.content
    assert nocolon_turn.metadata["source_timestamp_embedded_in_content"] is True

    # 同上：agent 侧 "ok" 无时间，不沿用 user 侧
    assert nocolon_agent_turn.content == "ok"
    assert nocolon_agent_turn.turn_time is None
    assert nocolon_agent_turn.metadata["source_timestamp_embedded_in_content"] is False

    # 结构化只是 additive：session_time 仍为 None，不因存在 turn 时间而被兜底填充
    assert session.session_time is None


def test_membench_marker_states_cover_first_third_and_noise(tmp_path: Path) -> None:
    """MemBench adapter 应在 `Turn.metadata` 写明 source time 嵌入事实，三种态全部覆盖。

    强反例 1：first-person dict step 的 user 侧内嵌完整 time marker →
    marker=True，turn_time 取到具体时间，原 content 保留 place/time/具体值；
    同一 step 的 assistant 侧（"ok first"）无时间，绝不沿用 user 侧的值。
    强反例 2：third-person string step 无冒号格式 `time'…'` → marker=True。
    强反例 3：噪声 step（无 time marker） → marker=False，turn_time=None；
    QA.time 只在 question_time 出现，绝不进入 turn metadata / content。
    同时验证：混合 dict/string/string 三个源 step 的 `source_step_index` 按
    step 分组去重后必须是连续 `0, 1, 2`（不因 dict step 拆成两条 turn 而错位）。
    """

    first_message = (
        f"I went there. (place: Boston, MA; time: '{_MSG_EMBEDDED_TIME}' Monday)"
    )
    third_message = (
        f"They went there. (place: Austin, TX; time'{_MSG_EMBEDDED_TIME}' Monday)"
    )
    noise_message = "Just a noise step without any timestamp."
    payload = {
        "simple": {
            "roles": [
                {
                    "tid": "t-marker",
                    "message_list": [
                        {"user": first_message, "agent": "ok first"},
                        third_message,
                        noise_message,
                    ],
                    "QA": {
                        "qid": 1,
                        "question": "q?",
                        "answer": "a",
                        "target_step_id": [0, 1],
                        "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
                        "ground_truth": "A",
                        "time": _QA_FUTURE_TIME_RAW,
                    },
                }
            ]
        }
    }
    # FirstAgent 源会同时含 PS dict step 与 OS string step，正好覆盖 first/third 两种
    # 人称；放入临时 0-10k 文件以走真实 adapter mapping。
    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, payload)
    dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(source.relative_to(tmp_path),),
    ).load()
    conversation = dataset.conversations[0]
    session = conversation.sessions[0]
    assert len(session.turns) == 4
    first_user_turn, first_assistant_turn, third_turn, noise_turn = session.turns
    assert [t.turn_id for t in session.turns] == ["1:user", "1:assistant", "2", "3"]

    # 混合 dict/string/string：去重后 source_step_index 必须是连续 0,1,2
    step_indices_in_order: list[int] = []
    for turn in session.turns:
        idx = turn.metadata["source_step_index"]
        if idx not in step_indices_in_order:
            step_indices_in_order.append(idx)
    assert step_indices_in_order == [0, 1, 2]

    # 强反例 1：first-person dict step 的 user 侧解析到 turn_time，marker=True，原文全保留
    assert first_user_turn.turn_time == _MSG_EMBEDDED_TIME
    assert first_user_turn.metadata["source_timestamp_embedded_in_content"] is True
    assert "place: Boston, MA" in first_user_turn.content
    assert f"time: '{_MSG_EMBEDDED_TIME}'" in first_user_turn.content
    # 未来 QA 日期不得反向串进 turn metadata / content
    assert "2099" not in first_user_turn.content
    assert "2099" not in str(first_user_turn.metadata)

    # 同一 step 的 assistant 侧（"ok first"）无时间，绝不沿用 user 侧的值
    assert first_assistant_turn.content == "ok first"
    assert first_assistant_turn.turn_time is None
    assert first_assistant_turn.metadata["source_timestamp_embedded_in_content"] is False

    # 强反例 2：third-person string step 无冒号格式也 marker=True
    assert third_turn.turn_time == _MSG_EMBEDDED_TIME
    assert third_turn.metadata["source_timestamp_embedded_in_content"] is True
    assert "place: Austin, TX" in third_turn.content
    assert f"time'{_MSG_EMBEDDED_TIME}'" in third_turn.content
    assert "2099" not in third_turn.content

    # 强反例 3：无时间 noise 保持 turn_time=None，marker=False，QA.time 不入
    assert noise_turn.turn_time is None
    assert noise_turn.metadata["source_timestamp_embedded_in_content"] is False
    assert noise_turn.content == noise_message
    assert "2099" not in noise_turn.content
    assert "2099" not in str(noise_turn.metadata)

    # QA.time 只进入 question_time，turn 侧全部不沾
    question = conversation.questions[0]
    assert question.question_time == _QA_FUTURE_TIME_RAW
    for turn in (first_user_turn, first_assistant_turn, third_turn, noise_turn):
        assert "2099" not in str(turn.metadata)
        assert "2099" not in turn.content

    # session_time 仍 None（无原生 session 时间）
    assert session.session_time is None

    # marker 必须 JSON-safe boolean：序列化往返仍严格为 True/False 而非 truthy 字符串
    import json as _json

    roundtrip = _json.loads(_json.dumps(first_user_turn.metadata))
    assert roundtrip["source_timestamp_embedded_in_content"] is True
    roundtrip_noise = _json.loads(_json.dumps(noise_turn.metadata))
    assert roundtrip_noise["source_timestamp_embedded_in_content"] is False


def test_membench_marker_survives_event_stream_roundtrip(tmp_path: Path) -> None:
    """强反例 1 改用 `build_turn_events` 路径：marker 仍有效，event.metadata 透传。

    锁住 v3 `TurnEvent.metadata["turn_metadata"]` 必须保留原
    `source_timestamp_embedded_in_content` 值，content-only renderer
    走事件流后还能读到 marker；四条 event（2 步 × user/assistant）逐条独立。
    """

    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, _future_time_counterexample_payload(first_person=True))
    dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(source.relative_to(tmp_path),),
    ).load()
    conversation = dataset.conversations[0]

    events = list(build_turn_events(conversation, isolation_key="run_marker"))
    assert len(events) == 4
    step1_user, step1_assistant, step2_user, step2_assistant = events

    # step 1（无时间 noise）：两条 event 的 marker 都仍 False
    assert (
        step1_user.metadata["turn_metadata"]["source_timestamp_embedded_in_content"]
        is False
    )
    assert (
        step1_assistant.metadata["turn_metadata"]["source_timestamp_embedded_in_content"]
        is False
    )
    # step 2（两侧都内嵌时间）：marker 仍 True，值不变
    assert (
        step2_user.metadata["turn_metadata"]["source_timestamp_embedded_in_content"]
        is True
    )
    assert (
        step2_assistant.metadata["turn_metadata"]["source_timestamp_embedded_in_content"]
        is True
    )
    # 原文仍保留
    assert f"time: '{_MSG_EMBEDDED_TIME}'" in step2_user.content
    assert "place: Boston, MA" in step2_user.content
    assert f"time: '{_MSG_EMBEDDED_TIME}'" in step2_assistant.content
    assert "place: Boston, MA" in step2_assistant.content


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
    # D4 修复：公开 turn id 1 基（`str(step_index + 1)`），target_step_id=1（0 基）→
    # 公开 turn id "2"。metadata 保留官方 0 基原值供对照。
    assert gold.evidence == ["2"]
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
    """真实样本中 target_step_id=0 应映射到公开 turn_id=1（+1 平移），避免 off-by-one。"""

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
    # D4：evidence 存公开 turn-id 空间，target_step_id=0（0 基）→ "1"。
    assert gold.evidence[0] == "1"
    assert "Casablanca" in turn.content
    assert gold.metadata["target_step_id"][0] == turn.metadata["source_step_index"]


def test_evidence_step_to_turn_shift_is_consistent_across_persons(tmp_path: Path) -> None:
    """first/third 两种人称的 step→turn 映射：third 仍 1 step=1 turn+1 平移；

    first 拆分后一个 step 对应两条 canonical turn，权威映射改由 gold evidence
    group 的 `child_ids` 承担（而不是 legacy `evidence` 字符串平移）。legacy
    `evidence`（`str(step_id + 1)`）在两种人称下算法上完全一致，但对 first 这
    个值不再对应任何真实 turn_id——只保留为历史审计别名，不得被误当作
    canonical turn-id 列表使用。不存在"跳过空 step"的路径：source_step_index
    去重分组后必须是连续 `0..N-1`。
    """

    # 构造一个同时含 0 基 target_step_id=0（→ "1"）和 =1（→ "2"）的合成 payload，
    # 验证两种人称在 +1 平移后都能正确映射到公开 turn-id 空间。
    payload = {
        "simple": {
            "roles": [
                {
                    "tid": "ps-1",
                    "message_list": [
                        {"user": "msg 0", "agent": "ok 0"},
                        {"user": "msg 1", "agent": "ok 1"},
                    ],
                    "QA": {
                        "qid": 1,
                        "question": "q?",
                        "answer": "a",
                        "target_step_id": [0, 1],  # 0 基 → 公开 "1", "2"
                        "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
                        "ground_truth": "A",
                        "time": "'2024-10-01 08:00' Tuesday",
                    },
                }
            ],
            "observations": [
                {
                    "tid": "os-1",
                    "message_list": [
                        "msg 0",
                        "msg 1",
                    ],
                    "QA": {
                        "qid": 2,
                        "question": "q?",
                        "answer": "a",
                        "target_step_id": [0, 1],  # 0 基 → 公开 "1", "2"
                        "choices": {"A": "a", "B": "b", "C": "c", "D": "d"},
                        "ground_truth": "A",
                        "time": "'2024-10-01 08:00' Tuesday",
                    },
                }
            ],
        }
    }

    # 第三人称源文件（ThirdAgentDataHighLevel）—— 字符串 step
    third_source = (
        tmp_path
        / "data2test"
        / "0-10k"
        / "ThirdAgentDataHighLevel_multiple_0.json"
    )
    _write_fixture(third_source, payload)
    # 第一人称源文件（FirstAgentDataLowLevel）—— dict step
    first_source = (
        tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    )
    _write_fixture(first_source, payload)

    third_dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(third_source.relative_to(tmp_path),),
    ).load()
    first_dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(first_source.relative_to(tmp_path),),
    ).load()

    # legacy evidence 的 str(step_id+1) 平移在两种人称下算法完全一致
    for dataset in (third_dataset, first_dataset):
        for conversation in dataset.conversations:
            question = conversation.questions[0]
            gold = conversation.gold_answers[question.question_id]
            # 0 基 target_step_id=[0,1] → legacy evidence "1", "2"（历史别名，不变）
            assert gold.evidence == ["1", "2"]
            # 官方 0 基原值保留在 metadata
            assert gold.metadata["target_step_id"] == [0, 1]
            # 不存在"跳过空 step"的路径：source_step_index 去重分组后必须是 0..N-1 连续
            step_indices = sorted(
                {
                    turn.metadata["source_step_index"]
                    for session in conversation.sessions
                    for turn in session.turns
                }
            )
            assert step_indices == list(range(len(step_indices)))
        # 确保两条 trajectory 都被加载（PS + OS）以覆盖两种人称
        assert len(dataset.conversations) == 2

    # 关键事实：拆分行为由**每条 trajectory 自身的 step 形态**（dict vs string）
    # 决定，与它躺在哪个源文件（"first"/"third" 命名）无关——本 fixture 特意把
    # 同一份含 dict trajectory（scenario="roles"）+ string trajectory
    # （scenario="observations"）的 payload 同时写进两个文件，用来证明这一点。
    for dataset in (third_dataset, first_dataset):
        by_scenario = {conv.metadata["scenario"]: conv for conv in dataset.conversations}
        dict_conversation = by_scenario["roles"]
        string_conversation = by_scenario["observations"]

        # dict-step trajectory：仍拆成 user+assistant，legacy evidence 不再对应
        # 任何真实 turn_id（纯历史别名）；权威映射改由 gold evidence group 的
        # child_ids 承担。
        gold = dict_conversation.gold_answers[dict_conversation.questions[0].question_id]
        all_turn_ids = [
            turn.turn_id
            for session in dict_conversation.sessions
            for turn in session.turns
        ]
        assert all_turn_ids == ["1:user", "1:assistant", "2:user", "2:assistant"]
        for evidence_turn_id in gold.evidence:
            assert evidence_turn_id not in all_turn_ids
        turn_view = [
            group_set
            for group_set in gold.evidence_group_sets
            if group_set.provenance_granularity == "turn"
            and group_set.unit_kind == "membench_step"
        ][0]
        groups_by_unit = {group.unit_id: group for group in turn_view.groups}
        assert groups_by_unit["0"].child_ids == ("1:user", "1:assistant")
        assert groups_by_unit["1"].child_ids == ("2:user", "2:assistant")
        for group in turn_view.groups:
            for child_id in group.child_ids:
                assert child_id in all_turn_ids

        # string-step trajectory：仍是 1 step=1 turn，legacy evidence 恰好也是
        # 真实 canonical turn_id（+1 平移）。
        gold = string_conversation.gold_answers[
            string_conversation.questions[0].question_id
        ]
        all_turn_ids = [
            turn.turn_id
            for session in string_conversation.sessions
            for turn in session.turns
        ]
        assert all_turn_ids == ["1", "2"]
        for evidence_turn_id in gold.evidence:
            assert evidence_turn_id in all_turn_ids
        for session in string_conversation.sessions:
            for turn in session.turns:
                assert turn.turn_id == str(turn.metadata["source_step_index"] + 1)


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

    assert md["official_repo_url"] == "https://github.com/import-myself/Membench"
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


def test_empty_target_step_id_produces_empty_evidence(tmp_path: Path) -> None:
    """空 target_step_id（合法保留，highlevel_rec 全空）应生成空 evidence 列表。

    D2 修复：空列表 = 无 step 证据，合法保留进 gold，recall 侧记 N/A。
    D4 +1 平移对空列表退化为空（`[str(s+1) for s in []]` = `[]`）。
    """

    payload = {
        "simple": {
            "roles": [
                {
                    "tid": "t-empty",
                    "message_list": [
                        {
                            "user": "I have no step evidence.",
                            "agent": "OK.",
                        }
                    ],
                    "QA": {
                        "qid": 1,
                        "question": "q?",
                        "answer": "a",
                        "target_step_id": [],
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
    conversation = dataset.conversations[0]
    question = conversation.questions[0]
    gold = conversation.gold_answers[question.question_id]

    assert gold.evidence == []  # 公开 turn-id 空间也是空
    assert gold.metadata["target_step_id"] == []  # 官方 0 基原值也空


def test_out_of_bounds_target_step_id_maps_to_nonexistent_turn_id(tmp_path: Path) -> None:
    """越界 target_step_id（0 基下 == len(message_list)）应映射到不存在公开 turn_id。

    全库恰 2 例（comparative/events tid=4，0-10k 和 100k 各 1）。+1 平移后该 id
    超出 message_list 真实范围（最大有效 turn_id=len），recall 侧记 unmatched-gold
    + 单独计数，不崩。
    """

    payload = {
        "simple": {
            "roles": [
                {
                    "tid": "t-oob",
                    "message_list": [
                        {"user": "msg 0", "agent": "ok 0"},
                        {"user": "msg 1", "agent": "ok 1"},
                    ],
                    "QA": {
                        "qid": 1,
                        "question": "q?",
                        "answer": "a",
                        # 0 基 len=2 → 0 基合法范围 0..1；2 越界
                        "target_step_id": [2],
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
    conversation = dataset.conversations[0]
    question = conversation.questions[0]
    gold = conversation.gold_answers[question.question_id]
    all_turn_ids = [
        turn.turn_id
        for session in conversation.sessions
        for turn in session.turns
    ]
    # +1 平移后 evidence="3"，但 message_list 只有 2 条（turn_id=1,2）
    assert gold.evidence == ["3"]
    assert "3" not in all_turn_ids  # 公开空间确实无对应 turn
    assert gold.metadata["target_step_id"] == [2]  # 官方 0 基原值保留


# ---------------------------------------------------------------------------
# gold evidence contract v1 group views
# ---------------------------------------------------------------------------


def _membench_turn_view(gold) -> object:
    """取出 MemBench gold 的唯一 turn view。"""

    assert gold.gold_evidence_contract_version == "v1"
    views = [
        group_set
        for group_set in gold.evidence_group_sets
        if group_set.provenance_granularity == "turn"
        and group_set.unit_kind == "membench_step"
    ]
    assert len(views) == 1
    return views[0]


def _load_with_qa_override(tmp_path: Path, qa_override: dict[str, Any]):
    """以覆盖 QA 字段后的 synthetic FirstAgent payload 加载首条 conversation。"""

    payload = _synthetic_payload()
    payload["simple"]["roles"][0]["QA"].update(qa_override)
    payload["simple"].pop("observations")
    source = tmp_path / "data2test" / "0-10k" / "FirstAgentDataLowLevel_multiple_0.json"
    _write_fixture(source, payload)
    dataset = MemBenchAdapter(
        tmp_path,
        variant="0_10k",
        source_relative_paths=(source.relative_to(tmp_path),),
    ).load()
    return dataset.conversations[0]


def test_membench_step_splits_into_two_turns_with_pair_group(
    tmp_path: Path,
) -> None:
    """FirstAgent 一 step 拆成 user+assistant 两条 turn，group 是真正的 2-child pair。"""

    conversation = _load_with_qa_override(tmp_path, {"target_step_id": [1]})
    # canonical split：两 step → 四 turn（每 step 都是 user+assistant）。
    assert [turn.turn_id for session in conversation.sessions for turn in session.turns] == [
        "1:user",
        "1:assistant",
        "2:user",
        "2:assistant",
    ]
    gold = conversation.gold_answers[conversation.questions[0].question_id]
    turn_view = _membench_turn_view(gold)

    assert len(turn_view.groups) == 1
    group = turn_view.groups[0]
    assert group.unit_id == "1"  # 官方 0 基 step id 作私有 unit_id
    # any-of pair：一个官方 step 对应两个真实 child，不是 singleton 冒充
    assert group.child_ids == ("2:user", "2:assistant")
    assert group.mapping_status == "mapped"


def test_membench_duplicate_targets_dedup_to_one_group(tmp_path: Path) -> None:
    """重复官方 target 稳定去重，一个 step 一个 group（各自真正的 2-child pair）。"""

    conversation = _load_with_qa_override(tmp_path, {"target_step_id": [1, 0, 1]})
    gold = conversation.gold_answers[conversation.questions[0].question_id]
    turn_view = _membench_turn_view(gold)

    assert [group.unit_id for group in turn_view.groups] == ["1", "0"]
    assert all(group.mapping_status == "mapped" for group in turn_view.groups)
    groups_by_unit = {group.unit_id: group for group in turn_view.groups}
    assert groups_by_unit["1"].child_ids == ("2:user", "2:assistant")
    assert groups_by_unit["0"].child_ids == ("1:user", "1:assistant")


def test_membench_multi_target_group_denominator_is_step_count_not_child_count(
    tmp_path: Path,
) -> None:
    """3 个 target step 拆分后仍是 3 个 group，不因每 step 两 child 而翻倍成 6。"""

    payload = {
        "simple": {
            "roles": [
                {
                    "tid": "t-three-target",
                    "message_list": [
                        {"user": "msg 0", "agent": "ok 0"},
                        {"user": "msg 1", "agent": "ok 1"},
                        {"user": "msg 2", "agent": "ok 2"},
                    ],
                    "QA": {
                        "qid": 1,
                        "question": "q?",
                        "answer": "a",
                        "target_step_id": [0, 1, 2],
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
    conversation = dataset.conversations[0]
    gold = conversation.gold_answers[conversation.questions[0].question_id]
    turn_view = _membench_turn_view(gold)

    # 分母 = 3 个官方 step，不是 6 个 child
    assert len(turn_view.groups) == 3
    assert [group.unit_id for group in turn_view.groups] == ["0", "1", "2"]
    for group in turn_view.groups:
        assert group.mapping_status == "mapped"
        assert len(group.child_ids) == 2


def test_membench_out_of_bounds_target_becomes_unmatched_group(
    tmp_path: Path,
) -> None:
    """`target_step_id == len(message_list)` 建 unmatched group，不造伪 child。"""

    conversation = _load_with_qa_override(tmp_path, {"target_step_id": [2]})
    gold = conversation.gold_answers[conversation.questions[0].question_id]
    turn_view = _membench_turn_view(gold)

    assert len(turn_view.groups) == 1
    assert turn_view.groups[0].unit_id == "2"
    assert turn_view.groups[0].mapping_status == "unmatched"
    assert turn_view.groups[0].child_ids == ()


def test_membench_empty_target_keeps_empty_groups(tmp_path: Path) -> None:
    """空 target（highlevel_rec 孤例形态）→ 空 groups，不合成 qrel。"""

    conversation = _load_with_qa_override(tmp_path, {"target_step_id": []})
    gold = conversation.gold_answers[conversation.questions[0].question_id]

    assert _membench_turn_view(gold).groups == ()


def test_membench_public_payload_has_no_group_keys(tmp_path: Path) -> None:
    """公开 payload 不得出现 group/unit/version 键。"""

    conversation = _load_with_qa_override(tmp_path, {"target_step_id": [1]})
    public_text = json.dumps(conversation.to_public_dict(), ensure_ascii=False)

    assert "evidence_group_sets" not in public_text
    assert "unit_id" not in public_text
    assert "gold_evidence_contract_version" not in public_text
    validate_no_private_keys(conversation.to_public_dict())

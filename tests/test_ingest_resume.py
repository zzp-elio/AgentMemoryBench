"""测试逐 turn 写入断点的路径安全、状态转换和强校验。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.runners.ingest_resume import TurnIngestCheckpointStore


pytestmark = pytest.mark.integration


def test_checkpoint_path_hashes_untrusted_conversation_id(tmp_path: Path) -> None:
    """conversation id 即使包含路径字符，也只能映射到断点目录内的哈希文件。"""

    store = TurnIngestCheckpointStore(tmp_path / "ingest_turns")
    conversation_id = "../../conv"

    checkpoint_path = store.path_for(conversation_id)

    expected_name = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
    assert checkpoint_path.parent == (tmp_path / "ingest_turns").resolve()
    assert checkpoint_path.name == f"{expected_name}.json"


def test_checkpoint_store_round_trips_all_states(tmp_path: Path) -> None:
    """store 应依次保存 in_flight、ready 和 completed，并保留原始 conversation id。"""

    store = TurnIngestCheckpointStore(tmp_path / "ingest_turns")

    store.mark_started(
        conversation_id="conv-1",
        turn_index=0,
        turn_id="turn-1",
        total_turns=2,
    )
    in_flight = store.load("conv-1", total_turns=2)
    assert in_flight is not None
    assert in_flight.status == "in_flight"
    assert in_flight.next_turn_index == 0
    assert in_flight.current_turn_id == "turn-1"

    store.mark_turn_completed(
        conversation_id="conv-1",
        turn_index=0,
        turn_id="turn-1",
        total_turns=2,
    )
    ready = store.load("conv-1", total_turns=2)
    assert ready is not None
    assert ready.status == "ready"
    assert ready.next_turn_index == 1
    assert ready.current_turn_index is None

    store.mark_started(
        conversation_id="conv-1",
        turn_index=1,
        turn_id="turn-2",
        total_turns=2,
    )
    store.mark_turn_completed(
        conversation_id="conv-1",
        turn_index=1,
        turn_id="turn-2",
        total_turns=2,
    )
    store.mark_conversation_completed(
        conversation_id="conv-1",
        total_turns=2,
    )
    completed = store.load("conv-1", total_turns=2)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.next_turn_index == 2


@pytest.mark.parametrize(
    ("field", "invalid_value", "expected_message"),
    [
        ("schema_version", 999, "schema_version"),
        ("conversation_id", "conv-other", "conversation_id"),
        ("status", "unknown", "status"),
        ("next_turn_index", 4, "next_turn_index"),
        ("total_turns", 3, "total_turns"),
    ],
)
def test_checkpoint_store_rejects_invalid_persisted_payload(
    tmp_path: Path,
    field: str,
    invalid_value: object,
    expected_message: str,
) -> None:
    """损坏、错配或越界的持久化状态必须显式报错，不能静默恢复。"""

    store = TurnIngestCheckpointStore(tmp_path / "ingest_turns")
    checkpoint_path = store.path_for("conv-1")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "conversation_id": "conv-1",
        "status": "ready",
        "next_turn_index": 1,
        "total_turns": 2,
        "current_turn_index": None,
        "current_turn_id": None,
    }
    payload[field] = invalid_value
    checkpoint_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigurationError, match=expected_message):
        store.load("conv-1", total_turns=2)


def test_mark_turn_completed_rejects_mismatched_in_flight_turn(tmp_path: Path) -> None:
    """completed callback 必须与当前 in_flight turn 完全一致。"""

    store = TurnIngestCheckpointStore(tmp_path / "ingest_turns")
    store.mark_started("conv-1", 0, "turn-1", total_turns=2)

    with pytest.raises(ConfigurationError, match="in-flight turn"):
        store.mark_turn_completed("conv-1", 1, "turn-2", total_turns=2)

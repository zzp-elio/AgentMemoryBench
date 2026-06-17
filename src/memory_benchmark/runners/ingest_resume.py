"""逐 turn 写入断点状态机。

本模块为支持增量写入的 method 保存每个 conversation 的独立原子 JSON。
它只记录已确认的调用边界，不猜测超时请求是否已被第三方服务处理。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from memory_benchmark.core import ConfigurationError, Conversation
from memory_benchmark.storage import atomic_write_json


CHECKPOINT_SCHEMA_VERSION = 1
TurnIngestStatus = Literal["ready", "in_flight", "completed"]
VALID_STATUSES = {"ready", "in_flight", "completed"}


def load_completed_conversation_ids(
    run_dir: str | Path,
    conversations: list[Conversation] | None = None,
) -> set[str]:
    """读取 resume checkpoint 中明确完成写入的 conversation ids。

    输入:
        run_dir: `outputs/<run_id>/` 运行目录。
        conversations: 可选当前统一 conversation 列表。提供后会同时校验逐 turn
            checkpoint，并附着其中 `completed` 的 namespace。

    输出:
        set[str]: coarse 或逐 turn状态明确为 `completed` 的 namespace。
    """

    resolved_run_dir = Path(run_dir)
    checkpoint_path = (
        resolved_run_dir / "checkpoints" / "conversation_status.json"
    )
    completed_ids: set[str] = set()
    if checkpoint_path.exists():
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ConfigurationError(
                f"Conversation checkpoint must be a JSON object: {checkpoint_path}"
            )
        completed_ids.update(
            str(conversation_id)
            for conversation_id, state in payload.items()
            if isinstance(state, dict) and state.get("status") == "completed"
        )

    if conversations is None:
        return completed_ids

    turn_store = TurnIngestCheckpointStore(
        resolved_run_dir / "checkpoints" / "ingest_turns"
    )
    for conversation in conversations:
        total_turns = sum(len(session.turns) for session in conversation.sessions)
        checkpoint = turn_store.load(
            conversation.conversation_id,
            total_turns=total_turns,
        )
        if checkpoint is not None and checkpoint.status == "completed":
            completed_ids.add(conversation.conversation_id)
    return completed_ids


@dataclass(frozen=True)
class TurnIngestCheckpoint:
    """单个 conversation 的逐 turn 写入状态。

    字段:
        schema_version: checkpoint 格式版本。
        conversation_id: 原始 conversation id，不用于构造文件路径。
        status: `ready`、`in_flight` 或 `completed`。
        next_turn_index: 下一条尚未确认成功的零基 turn index。
        total_turns: 当前 conversation 的总 turn 数。
        current_turn_index: `in_flight` 时正在调用 method 的 turn index。
        current_turn_id: `in_flight` 时正在调用 method 的 turn id。
    """

    schema_version: int
    conversation_id: str
    status: TurnIngestStatus
    next_turn_index: int
    total_turns: int
    current_turn_index: int | None = None
    current_turn_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        """返回可原子写入 JSON 的字典。"""

        return asdict(self)


class TurnIngestCheckpointStore:
    """读写按 conversation 隔离的逐 turn checkpoint。"""

    def __init__(self, root_dir: str | Path):
        """初始化 store，并把根目录解析为绝对路径。"""

        self.root_dir = Path(root_dir).expanduser().resolve()

    def path_for(self, conversation_id: str) -> Path:
        """返回 conversation id 对应的 SHA-256 checkpoint 路径。"""

        self._validate_conversation_id(conversation_id)
        digest = hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()
        return self.root_dir / f"{digest}.json"

    def load(
        self,
        conversation_id: str,
        total_turns: int,
    ) -> TurnIngestCheckpoint | None:
        """读取并强校验 checkpoint；文件不存在时返回 `None`。"""

        self._validate_total_turns(total_turns)
        path = self.path_for(conversation_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"Invalid turn ingest checkpoint JSON: {path}"
            ) from exc
        if not isinstance(payload, dict):
            raise ConfigurationError(
                f"Turn ingest checkpoint must be a JSON object: {path}"
            )

        checkpoint = self._from_payload(payload)
        self._validate_checkpoint(
            checkpoint,
            expected_conversation_id=conversation_id,
            expected_total_turns=total_turns,
        )
        return checkpoint

    def mark_started(
        self,
        conversation_id: str,
        turn_index: int,
        turn_id: str,
        total_turns: int,
    ) -> TurnIngestCheckpoint:
        """在调用 method 前把指定 turn 标记为 `in_flight`。"""

        self._validate_turn_identity(turn_index, turn_id, total_turns)
        existing = self.load(conversation_id, total_turns)
        expected_index = 0 if existing is None else existing.next_turn_index
        if existing is not None and existing.status != "ready":
            raise ConfigurationError(
                "Cannot start a turn unless checkpoint status is ready"
            )
        if turn_index != expected_index:
            raise ConfigurationError(
                "Turn ingest start index does not match next_turn_index: "
                f"{turn_index} != {expected_index}"
            )

        checkpoint = TurnIngestCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            conversation_id=conversation_id,
            status="in_flight",
            next_turn_index=turn_index,
            total_turns=total_turns,
            current_turn_index=turn_index,
            current_turn_id=turn_id,
        )
        self._write(checkpoint)
        return checkpoint

    def mark_turn_completed(
        self,
        conversation_id: str,
        turn_index: int,
        turn_id: str,
        total_turns: int,
    ) -> TurnIngestCheckpoint:
        """在 method 成功返回后把下一位置标记为 `ready`。"""

        self._validate_turn_identity(turn_index, turn_id, total_turns)
        existing = self.load(conversation_id, total_turns)
        if (
            existing is None
            or existing.status != "in_flight"
            or existing.current_turn_index != turn_index
            or existing.current_turn_id != turn_id
        ):
            raise ConfigurationError(
                "Completed callback does not match the current in-flight turn"
            )

        checkpoint = TurnIngestCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            conversation_id=conversation_id,
            status="ready",
            next_turn_index=turn_index + 1,
            total_turns=total_turns,
        )
        self._write(checkpoint)
        return checkpoint

    def mark_conversation_completed(
        self,
        conversation_id: str,
        total_turns: int,
    ) -> TurnIngestCheckpoint:
        """确认所有 turn 成功后标记整个 conversation 写入完成。"""

        existing = self.load(conversation_id, total_turns)
        if (
            existing is None
            or existing.status != "ready"
            or existing.next_turn_index != total_turns
        ):
            raise ConfigurationError(
                "Conversation cannot complete before all turns are confirmed"
            )
        checkpoint = TurnIngestCheckpoint(
            schema_version=CHECKPOINT_SCHEMA_VERSION,
            conversation_id=conversation_id,
            status="completed",
            next_turn_index=total_turns,
            total_turns=total_turns,
        )
        self._write(checkpoint)
        return checkpoint

    def _write(self, checkpoint: TurnIngestCheckpoint) -> None:
        """把 checkpoint 原子写入其 conversation 专属文件。"""

        atomic_write_json(
            self.path_for(checkpoint.conversation_id),
            checkpoint.to_dict(),
        )

    @staticmethod
    def _from_payload(payload: dict[str, object]) -> TurnIngestCheckpoint:
        """把 JSON 字典转换为 checkpoint，并统一报告字段类型错误。"""

        try:
            return TurnIngestCheckpoint(
                schema_version=payload["schema_version"],
                conversation_id=payload["conversation_id"],
                status=payload["status"],
                next_turn_index=payload["next_turn_index"],
                total_turns=payload["total_turns"],
                current_turn_index=payload.get("current_turn_index"),
                current_turn_id=payload.get("current_turn_id"),
            )
        except (KeyError, TypeError) as exc:
            raise ConfigurationError(
                f"Turn ingest checkpoint fields are invalid: {exc}"
            ) from exc

    @classmethod
    def _validate_checkpoint(
        cls,
        checkpoint: TurnIngestCheckpoint,
        expected_conversation_id: str,
        expected_total_turns: int,
    ) -> None:
        """校验持久化状态的 schema、归属、范围和状态组合。"""

        if (
            type(checkpoint.schema_version) is not int
            or checkpoint.schema_version != CHECKPOINT_SCHEMA_VERSION
        ):
            raise ConfigurationError(
                "Turn ingest checkpoint schema_version is unsupported"
            )
        if (
            not isinstance(checkpoint.conversation_id, str)
            or checkpoint.conversation_id != expected_conversation_id
        ):
            raise ConfigurationError(
                "Turn ingest checkpoint conversation_id does not match"
            )
        if checkpoint.status not in VALID_STATUSES:
            raise ConfigurationError("Turn ingest checkpoint status is invalid")
        if (
            type(checkpoint.total_turns) is not int
            or checkpoint.total_turns != expected_total_turns
        ):
            raise ConfigurationError(
                "Turn ingest checkpoint total_turns does not match conversation"
            )
        if (
            type(checkpoint.next_turn_index) is not int
            or checkpoint.next_turn_index < 0
            or checkpoint.next_turn_index > expected_total_turns
        ):
            raise ConfigurationError(
                "Turn ingest checkpoint next_turn_index is out of range"
            )

        if checkpoint.status == "in_flight":
            if (
                type(checkpoint.current_turn_index) is not int
                or checkpoint.current_turn_index != checkpoint.next_turn_index
                or checkpoint.current_turn_index >= expected_total_turns
                or not isinstance(checkpoint.current_turn_id, str)
                or not checkpoint.current_turn_id.strip()
            ):
                raise ConfigurationError(
                    "Turn ingest checkpoint in_flight fields are invalid"
                )
        elif (
            checkpoint.current_turn_index is not None
            or checkpoint.current_turn_id is not None
        ):
            raise ConfigurationError(
                "Turn ingest checkpoint current turn fields require in_flight status"
            )

        if (
            checkpoint.status == "completed"
            and checkpoint.next_turn_index != expected_total_turns
        ):
            raise ConfigurationError(
                "Completed turn ingest checkpoint next_turn_index must equal total_turns"
            )

    @staticmethod
    def _validate_conversation_id(conversation_id: str) -> None:
        """拒绝空 conversation id。"""

        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ConfigurationError("Turn ingest checkpoint conversation_id is required")

    @staticmethod
    def _validate_total_turns(total_turns: int) -> None:
        """要求 conversation 至少包含一个 turn。"""

        if type(total_turns) is not int or total_turns < 1:
            raise ConfigurationError(
                "Turn ingest checkpoint total_turns must be positive"
            )

    @classmethod
    def _validate_turn_identity(
        cls,
        turn_index: int,
        turn_id: str,
        total_turns: int,
    ) -> None:
        """校验 callback 提供的 turn index 和 id。"""

        cls._validate_total_turns(total_turns)
        if type(turn_index) is not int or turn_index < 0 or turn_index >= total_turns:
            raise ConfigurationError("Turn ingest callback turn_index is out of range")
        if not isinstance(turn_id, str) or not turn_id.strip():
            raise ConfigurationError("Turn ingest callback turn_id is required")


__all__ = [
    "TurnIngestCheckpoint",
    "TurnIngestCheckpointStore",
    "load_completed_conversation_ids",
]

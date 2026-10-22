"""BEAM conversation-QA benchmark adapter。

把 `data/BEAM/` 下 100K/500K/1M/10M 的 HF arrow 数据转换为统一
Dataset。前三个 variant 的 chat 是 list[session]；10M 是按 plan 聚合的
list[dict]，按官方顺序展开为全 conversation 唯一的 canonical session。
probing_questions 是 Python-repr 字符串（`ast.literal_eval` 解析），
content 末尾带 `->-> a,b` 尾标记需裁剪。私有 rubric/ideal_response 等仅
进 GoldAnswerInfo，公开 conversation 过 validate_no_private_keys。
"""

from __future__ import annotations

import ast
import copy
import re
from pathlib import Path
from typing import Any

from memory_benchmark.core import (
    Conversation,
    Dataset,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
    map_native_task_to_capability,
)
from memory_benchmark.core.exceptions import ConfigurationError, DatasetValidationError

from .base import BenchmarkAdapter, reached_limit


_BEAM_DATASET_DIR = Path("data/BEAM/beam_dataset")
_BEAM_10M_DATASET_DIR = Path("data/BEAM/beam_10M_dataset")

_VARIANT_PATH_MAP: dict[str, Path] = {
    "100k": _BEAM_DATASET_DIR / "100K",
    "500k": _BEAM_DATASET_DIR / "500K",
    "1m": _BEAM_DATASET_DIR / "1M",
    "10m": _BEAM_10M_DATASET_DIR / "10M",
}

BEAM_ABILITY_KEYS: tuple[str, ...] = (
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
)

_TAIL_MARKER_PATTERN = re.compile(r"\s*->->\s+\d+\s*,\s*(?:\d+|N/A)\s*$")


class BeamGoldAnswerInfo(GoldAnswerInfo):
    """保留完整私有事实，但为落盘提供紧凑 evaluator 投影。"""

    def evaluator_artifact_metadata(self) -> dict[str, Any]:
        return {
            "ability": self.metadata.get("ability"),
            "rubric": self.metadata.get("rubric"),
            "difficulty": self.metadata.get("difficulty"),
        }


def strip_tail_marker(content: str) -> str:
    """裁掉 content 末尾的 `->-> a,b` 尾标记，保留真实文本。"""
    return _TAIL_MARKER_PATTERN.sub("", content)


class BeamAdapter(BenchmarkAdapter):
    """BEAM arrow → 统一 Dataset adapter。"""

    name = "beam"

    def __init__(
        self,
        project_root: str | Path,
        variant: str = "100k",
    ) -> None:
        super().__init__(project_root)
        normalized_variant = variant.strip().lower() if isinstance(variant, str) else ""
        if not normalized_variant:
            raise ConfigurationError("beam variant is required")
        if normalized_variant not in _VARIANT_PATH_MAP:
            allowed = ", ".join(_VARIANT_PATH_MAP)
            raise ConfigurationError(
                f"Unknown beam variant '{variant}'. Allowed: {allowed}"
            )
        self.variant = normalized_variant
        self._source_relative_path = _VARIANT_PATH_MAP[normalized_variant]

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取 HF arrow 并转换为统一 Dataset。"""
        if limit is not None and limit <= 0:
            raise DatasetValidationError("beam limit must be a positive integer")

        try:
            import datasets as hf_datasets
        except ImportError as exc:
            raise ConfigurationError(
                "datasets (HuggingFace) is required for BEAM adapter"
            ) from exc

        dataset_path = self.require_path(*self._source_relative_path.parts)
        ds = hf_datasets.load_from_disk(str(dataset_path))

        conversations: list[Conversation] = []
        source_fully_scanned = True
        for row_idx, row in enumerate(ds):
            conversations.append(
                _conversation_from_row(
                    row,
                    row_idx=row_idx,
                    ten_million=self.variant == "10m",
                )
            )
            if reached_limit(len(conversations), limit):
                source_fully_scanned = False
                break

        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_paths": [str(dataset_path)],
                "variant": self.variant,
                "source_format": "beam_arrow",
                "total_raw_rows": len(ds),
                "source_fully_scanned": source_fully_scanned,
                "loaded_conversation_count": len(conversations),
                "loaded_session_count": sum(
                    len(conversation.sessions) for conversation in conversations
                ),
                "loaded_turn_count": sum(
                    len(session.turns)
                    for conversation in conversations
                    for session in conversation.sessions
                ),
                "loaded_question_count": sum(
                    len(conversation.questions) for conversation in conversations
                ),
            },
        )


def _conversation_from_row(
    row: dict[str, Any],
    *,
    row_idx: int,
    ten_million: bool = False,
) -> Conversation:
    conversation_id = str(row.get("conversation_id", row_idx + 1))
    chat_raw = row.get("chat")
    if not isinstance(chat_raw, list):
        raise DatasetValidationError(
            f"beam row {row_idx}: chat must be a list, got {type(chat_raw).__name__}"
        )

    sessions = (
        _sessions_from_10m_chat(chat_raw, conversation_id=conversation_id)
        if ten_million
        else _sessions_from_standard_chat(chat_raw, conversation_id=conversation_id)
    )

    probing_raw = row.get("probing_questions")
    if not isinstance(probing_raw, str) or not probing_raw.strip():
        raise DatasetValidationError(
            f"{conversation_id}: probing_questions must be a non-empty string"
        )
    try:
        probing = ast.literal_eval(probing_raw)
    except (ValueError, SyntaxError) as exc:
        raise DatasetValidationError(
            f"{conversation_id}: probing_questions is not valid Python literal: {exc}"
        ) from exc
    if not isinstance(probing, dict):
        raise DatasetValidationError(
            f"{conversation_id}: probing_questions must evaluate to a dict"
        )

    questions: list[Question] = []
    gold_answers: dict[str, GoldAnswerInfo] = {}
    for ability, question_list in probing.items():
        if not isinstance(question_list, list):
            raise DatasetValidationError(
                f"{conversation_id}/{ability}: probing value must be a list"
            )
        for q_idx, q_obj in enumerate(question_list, start=1):
            if not isinstance(q_obj, dict):
                raise DatasetValidationError(
                    f"{conversation_id}/{ability}[{q_idx - 1}]: must be a dict"
                )
            question_id = f"{conversation_id}:{ability}:q{q_idx}"
            question_text = _required_text(q_obj, "question", question_id)
            gold_answer_text = _resolve_answer_field(q_obj, question_id)

            gold_metadata: dict[str, Any] = {
                "ability": ability,
                **{k: copy.deepcopy(v) for k, v in q_obj.items() if k != "question"},
            }

            capability = map_native_task_to_capability("beam", ability)
            questions.append(
                Question(
                    question_id=question_id,
                    conversation_id=conversation_id,
                    text=question_text,
                    category=ability,
                    capability=capability,
                    metadata={},
                )
            )
            gold_answers[question_id] = BeamGoldAnswerInfo(
                question_id=question_id,
                answer=gold_answer_text,
                metadata=gold_metadata,
            )

    return Conversation(
        conversation_id=conversation_id,
        sessions=sessions,
        questions=questions,
        gold_answers=gold_answers,
        metadata={},
    )


def _sessions_from_standard_chat(
    chat_raw: list[Any],
    *,
    conversation_id: str,
) -> list[Session]:
    sessions: list[Session] = []
    for session_index, session_turns in enumerate(chat_raw, start=1):
        if not isinstance(session_turns, list):
            raise DatasetValidationError(
                f"{conversation_id}: chat[{session_index - 1}] must be a list"
            )
        sessions.append(
            _session_from_turns(
                session_turns,
                conversation_id=conversation_id,
                session_id=f"s{session_index}",
            )
        )
    return sessions


def _sessions_from_10m_chat(
    chat_raw: list[Any],
    *,
    conversation_id: str,
) -> list[Session]:
    sessions: list[Session] = []
    for plan_index, plan_slot in enumerate(chat_raw):
        plan_number = plan_index + 1
        plan_id = f"plan-{plan_number}"
        if not isinstance(plan_slot, dict):
            raise DatasetValidationError(
                f"{conversation_id}: 10M chat[{plan_index}] must be a dict"
            )
        batches = plan_slot.get(plan_id)
        if not isinstance(batches, list):
            raise DatasetValidationError(
                f"{conversation_id}: 10M chat[{plan_index}]['{plan_id}'] must be a list"
            )
        for batch_index, batch in enumerate(batches):
            if not isinstance(batch, dict) or not isinstance(batch.get("turns"), list):
                raise DatasetValidationError(
                    f"{conversation_id}/{plan_id}: batch[{batch_index}] must contain turns"
                )
            session_turns: list[dict[str, Any]] = []
            for group_index, turn_group in enumerate(batch["turns"]):
                if not isinstance(turn_group, list):
                    raise DatasetValidationError(
                        f"{conversation_id}/{plan_id}/batch[{batch_index}]: "
                        f"turns[{group_index}] must be a list"
                    )
                session_turns.extend(turn_group)
            sessions.append(
                _session_from_turns(
                    session_turns,
                    conversation_id=conversation_id,
                    session_id=f"p{plan_number}:s{batch_index + 1}",
                    session_metadata={
                        "plan_id": plan_id,
                        "plan_index": plan_index,
                        "batch_number": batch.get("batch_number", batch_index + 1),
                    },
                )
            )
    return sessions


_ANSWER_FIELD_CANDIDATES: tuple[str, ...] = (
    "ideal_response",
    "ideal_answer",
    "answer",
    "expected_compliance",
    "ideal_summary",
)


def _resolve_answer_field(q_obj: dict[str, Any], question_id: str) -> str:
    for field_name in _ANSWER_FIELD_CANDIDATES:
        value = q_obj.get(field_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise DatasetValidationError(
        f"{question_id}: no valid answer field found (tried: "
        + ", ".join(_ANSWER_FIELD_CANDIDATES)
        + ")"
    )


def _session_from_turns(
    session_turns: list[dict[str, Any]],
    *,
    conversation_id: str,
    session_id: str,
    session_metadata: dict[str, Any] | None = None,
) -> Session:
    turns: list[Turn] = []
    session_time: str | None = None
    for turn_index, turn_raw in enumerate(session_turns, start=1):
        if not isinstance(turn_raw, dict):
            raise DatasetValidationError(
                f"{conversation_id}/{session_id}: turn[{turn_index - 1}] must be a dict"
            )
        role = _required_text(turn_raw, "role", f"{conversation_id}/{session_id}/t{turn_index}")
        raw_content = _required_text(
            turn_raw, "content", f"{conversation_id}/{session_id}/t{turn_index}"
        )
        content = strip_tail_marker(raw_content)

        time_anchor = turn_raw.get("time_anchor")
        if isinstance(time_anchor, str) and time_anchor.strip():
            turn_time = time_anchor.strip()
            if session_time is None:
                session_time = turn_time
        else:
            turn_time = None

        turns.append(
            Turn(
                turn_id=f"{session_id}:t{turn_index}",
                speaker=role,
                normalized_role=role,
                content=content,
                turn_time=turn_time,
                metadata={
                    "id": turn_raw.get("id"),
                    "index": turn_raw.get("index"),
                    "question_type": turn_raw.get("question_type"),
                },
            )
        )

    return Session(
        session_id=session_id,
        turns=turns,
        session_time=session_time,
        start_time=session_time,
        end_time=None,
        metadata=copy.deepcopy(session_metadata or {}),
        private_metadata={},
    )


def _required_text(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{context}: {key} is required")
    return value.strip()

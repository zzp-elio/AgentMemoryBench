"""LongMemEval conversation-QA adapter。

本模块负责把 `data/longmemeval/longmemeval_s_cleaned.json` 和
`data/longmemeval/longmemeval_m_cleaned.json` 转换为统一的
`Dataset -> Conversation -> Session -> Turn -> Question` 结构。
标准答案、evidence session id 和 turn 级 `has_answer` 标签不能进入 method
可见的公开对象。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import ijson

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


LONGMEMEVAL_VARIANT_PATHS: dict[str, Path] = {
    "s_cleaned": Path("data/longmemeval/longmemeval_s_cleaned.json"),
    "m_cleaned": Path("data/longmemeval/longmemeval_m_cleaned.json"),
}
LONGMEMEVAL_SOURCE_PATH = str(LONGMEMEVAL_VARIANT_PATHS["s_cleaned"])
NORMALIZED_ROLES = {"user", "assistant", "system"}
PRIVATE_MESSAGE_KEYS = {
    "answer",
    "answer_session_ids",
    "answers",
    "evidence",
    "gold",
    "gold_answer",
    "gold_answers",
    "ground_truth",
    "has_answer",
    "judge_label",
    "label",
}
MESSAGE_CORE_KEYS = {"role", "speaker", "content", "text"}
LONGMEMEVAL_TASK = "question_answering"


class LongMemEvalAdapter(BenchmarkAdapter):
    """LongMemEval benchmark 数据 adapter。"""

    name = "longmemeval"

    def __init__(self, project_root: str | Path, variant: str = "s_cleaned"):
        super().__init__(project_root)
        normalized_variant = variant.strip() if isinstance(variant, str) else ""
        if not normalized_variant:
            raise ConfigurationError("longmemeval variant is required")
        if normalized_variant not in LONGMEMEVAL_VARIANT_PATHS:
            allowed = ", ".join(LONGMEMEVAL_VARIANT_PATHS)
            raise ConfigurationError(
                f"Unknown longmemeval variant '{variant}'. Allowed: {allowed}"
            )

        self.variant = normalized_variant
        self.split = normalized_variant
        self.source_relative_path = LONGMEMEVAL_VARIANT_PATHS[normalized_variant]

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取选定的 LongMemEval 原始数据并转换为统一 Dataset。"""
        if limit is not None and limit <= 0:
            raise DatasetValidationError("longmemeval limit must be a positive integer")

        conversations: list[Conversation] = []
        source_fully_scanned = False
        source_path = self.require_path(*self.source_relative_path.parts)
        with source_path.open("rb") as handle:
            for raw_index, instance in enumerate(ijson.items(handle, "item")):
                if not isinstance(instance, dict):
                    raise DatasetValidationError(
                        f"instance {raw_index}: instance must be a dict"
                    )
                conversations.append(self._conversation_from_instance(instance, raw_index))
                if reached_limit(len(conversations), limit):
                    break
            else:
                source_fully_scanned = True

        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_path": str(self.source_relative_path),
                "split": self.split,
                "variant": self.variant,
                "source_format": "longmemeval",
                "task": LONGMEMEVAL_TASK,
                "total_raw_instances": len(conversations),
                "source_fully_scanned": source_fully_scanned,
                "official_question_count": len(conversations),
                "abstention_question_count": sum(
                    1
                    for conversation in conversations
                    if "_abs" in conversation.metadata.get("source_question_id", "")
                ),
                "skipped_blank_turn_count": sum(
                    int(conversation.metadata.get("skipped_blank_turn_count", 0))
                    for conversation in conversations
                ),
                "deduplicated_session_id_count": sum(
                    int(conversation.metadata.get("deduplicated_session_id_count", 0))
                    for conversation in conversations
                ),
            },
        )

    def _conversation_from_instance(
        self,
        instance: dict[str, Any],
        raw_index: int | str,
    ) -> Conversation:
        """把一条 LongMemEval evaluation instance 转成 Conversation。"""
        context = f"instance {raw_index}"
        question_id = _required_text(instance, "question_id", context)
        question_text = _required_text(instance, "question", question_id)
        question_type = _optional_text(instance.get("question_type"))
        question_date = _optional_text(instance.get("question_date"))

        (
            sessions,
            skipped_blank_turn_count,
            deduplicated_session_id_count,
            evidence_turn_ids,
        ) = self._sessions_from_instance(instance, question_id)
        answer_session_ids = _string_list(instance.get("answer_session_ids"))
        effective_task = "abstention" if question_id.endswith("_abs") else question_type
        capability = map_native_task_to_capability("longmemeval", effective_task)
        question = Question(
            question_id=question_id,
            conversation_id=question_id,
            text=question_text,
            question_time=question_date,
            category=question_type,
            capability=capability,
            metadata={"source_index": raw_index},
        )
        gold = GoldAnswerInfo(
            question_id=question_id,
            answer=_answer_to_text(instance.get("answer")),
            metadata={
                "question_type": question_type,
                "question_date": question_date,
                "source_index": raw_index,
                "evidence_turn_ids": evidence_turn_ids,
            },
        )

        return Conversation(
            conversation_id=question_id,
            sessions=sessions,
            questions=[question],
            gold_answers={question_id: gold},
            metadata={
                "source_path": str(self.source_relative_path),
                "split": self.split,
                "variant": self.variant,
                "source_question_id": question_id,
                "skipped_blank_turn_count": skipped_blank_turn_count,
                "deduplicated_session_id_count": deduplicated_session_id_count,
            },
        )

    def _sessions_from_instance(
        self,
        instance: dict[str, Any],
        question_id: str,
    ) -> tuple[list[Session], int, int, list[str]]:
        """把 LongMemEval 三个 haystack 并行列表转成 Session 列表。"""
        session_ids = _required_list(instance, "haystack_session_ids", question_id)
        session_dates = _required_list(instance, "haystack_dates", question_id)
        sessions_raw = _required_list(instance, "haystack_sessions", question_id)
        _validate_parallel_haystack_lengths(
            question_id,
            session_ids,
            session_dates,
            sessions_raw,
        )

        sessions: list[Session] = []
        skipped_blank_turn_count = 0
        deduplicated_session_id_count = 0
        evidence_turn_ids: list[str] = []
        seen_session_ids: dict[str, int] = {}
        for session_index, (session_id_raw, session_date_raw, turns_raw) in enumerate(
            zip(session_ids, session_dates, sessions_raw),
        ):
            original_session_id = (
                _optional_text(session_id_raw) or f"{question_id}:session_{session_index}"
            )
            occurrence = seen_session_ids.get(original_session_id, 0) + 1
            seen_session_ids[original_session_id] = occurrence
            session_id = _unique_session_id(original_session_id, occurrence)
            if occurrence > 1:
                deduplicated_session_id_count += 1
            session_time = _optional_text(session_date_raw)
            (
                session,
                skipped_count,
                session_evidence_ids,
            ) = self._session_from_raw(
                session_id,
                session_time,
                turns_raw,
                original_session_id=original_session_id,
                session_index=session_index,
                occurrence=occurrence,
            )
            skipped_blank_turn_count += skipped_count
            sessions.append(session)
            evidence_turn_ids.extend(session_evidence_ids)
        return (
            sessions,
            skipped_blank_turn_count,
            deduplicated_session_id_count,
            evidence_turn_ids,
        )

    def _session_from_raw(
        self,
        session_id: str,
        session_time: str | None,
        turns_raw: object,
        *,
        original_session_id: str,
        session_index: int,
        occurrence: int,
    ) -> tuple[Session, int, list[str]]:
        """把一个 haystack session 转成统一 Session。"""
        if not isinstance(turns_raw, list):
            raise DatasetValidationError(f"{session_id}: session must be a list")

        turns: list[Turn] = []
        skipped_blank_turn_count = 0
        evidence_turn_ids: list[str] = []
        for turn_index, turn_raw in enumerate(turns_raw):
            turn_id = f"{session_id}:t{turn_index}"
            if not isinstance(turn_raw, dict):
                raise DatasetValidationError(f"{turn_id}: turn must be a dict")
            blank_content = _has_blank_message_content(turn_raw)
            if turn_raw.get("has_answer") is True:
                evidence_turn_ids.append(turn_id)
            if blank_content:
                skipped_blank_turn_count += 1
                continue
            turns.append(_turn_from_raw(turn_raw, session_id, turn_index))

        if not turns:
            raise DatasetValidationError(f"{session_id}: session has no non-empty turns")

        return (
            Session(
                session_id=session_id,
                session_time=session_time,
                turns=turns,
                metadata={
                    "source_format": "longmemeval_haystack_session",
                    "source_index": session_index,
                    "original_session_id": original_session_id,
                    "session_id_occurrence": occurrence,
                    "skipped_blank_turn_count": skipped_blank_turn_count,
                },
            ),
            skipped_blank_turn_count,
            evidence_turn_ids,
        )


def _validate_parallel_haystack_lengths(
    question_id: str,
    session_ids: list[Any],
    session_dates: list[Any],
    sessions_raw: list[Any],
) -> None:
    lengths = {
        "haystack_session_ids": len(session_ids),
        "haystack_dates": len(session_dates),
        "haystack_sessions": len(sessions_raw),
    }
    if len(set(lengths.values())) != 1:
        raise DatasetValidationError(
            f"{question_id}: haystack parallel list length mismatch: {lengths}"
        )


def _unique_session_id(original_session_id: str, occurrence: int) -> str:
    if occurrence <= 1:
        return original_session_id
    return f"{original_session_id}#occurrence_{occurrence}"


def _turn_from_raw(raw_turn: object, session_id: str, turn_index: int) -> Turn:
    turn_id = f"{session_id}:t{turn_index}"
    if not isinstance(raw_turn, dict):
        raise DatasetValidationError(f"{turn_id}: turn must be a dict")

    role = _optional_text(raw_turn.get("role"))
    speaker = role or _required_text(raw_turn, "speaker", turn_id)
    content = _message_content(raw_turn, turn_id)

    return Turn(
        turn_id=turn_id,
        speaker=speaker,
        content=content,
        normalized_role=_normalized_role(role),
        metadata=_public_message_metadata(raw_turn),
    )


def _message_content(raw_turn: dict[str, Any], turn_id: str) -> str:
    content = _message_content_value(raw_turn)
    if content is None:
        raise DatasetValidationError(f"{turn_id}: content is required")
    return content


def _message_content_value(raw_turn: dict[str, Any]) -> str | None:
    content = _optional_text(raw_turn.get("content"))
    if content is None:
        content = _optional_text(raw_turn.get("text"))
    return content


def _has_blank_message_content(raw_turn: dict[str, Any]) -> bool:
    for key in ("content", "text"):
        if key in raw_turn and _optional_text(raw_turn.get(key)) is None:
            return True
    return False


def _normalized_role(role: str | None) -> str | None:
    if role is None:
        return None
    normalized = role.lower()
    return normalized if normalized in NORMALIZED_ROLES else None


def _public_message_metadata(raw_turn: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key, value in raw_turn.items():
        normalized_key = str(key).lower()
        if normalized_key in MESSAGE_CORE_KEYS or normalized_key in PRIVATE_MESSAGE_KEYS:
            continue
        metadata[str(key)] = value
    return metadata


def _required_list(raw: dict[str, Any], key: str, context: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise DatasetValidationError(f"{context}: {key} must be a list")
    return value


def _required_text(raw: dict[str, Any], key: str, context: str) -> str:
    value = _optional_text(raw.get(key))
    if value is None:
        raise DatasetValidationError(f"{context}: {key} is required")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _answer_to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []

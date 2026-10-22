"""HaluMem conversation-QA benchmark adapter。

本模块负责把 `data/halumem/HaluMem-*.jsonl` 的 user/session/turn/question
层级转换为统一 Dataset。`memory_points`、reference answer、evidence、
difficulty、question_type 和 persona_info 只进入私有结构，不能出现在 method
可见公开 payload 中。
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
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


HALUMEM_MEDIUM_SOURCE_PATH = Path("data/halumem/HaluMem-Medium.jsonl")
HALUMEM_LONG_SOURCE_PATH = Path("data/halumem/HaluMem-Long.jsonl")
HALUMEM_VARIANT_PATHS: dict[str, Path] = {
    "medium": HALUMEM_MEDIUM_SOURCE_PATH,
    "long": HALUMEM_LONG_SOURCE_PATH,
}


class HaluMemAdapter(BenchmarkAdapter):
    """HaluMem user 级连续会话数据 adapter。"""

    name = "halumem"

    def __init__(
        self,
        project_root: str | Path,
        variant: str = "medium",
        source_relative_path: Path | None = None,
    ):
        super().__init__(project_root)
        normalized_variant = variant.strip() if isinstance(variant, str) else ""
        if not normalized_variant:
            raise ConfigurationError("halumem variant is required")
        if source_relative_path is None:
            if normalized_variant not in HALUMEM_VARIANT_PATHS:
                allowed = ", ".join(HALUMEM_VARIANT_PATHS)
                raise ConfigurationError(
                    f"Unknown halumem variant '{variant}'. Allowed: {allowed}"
                )
            selected_source_path = HALUMEM_VARIANT_PATHS[normalized_variant]
        else:
            selected_source_path = Path(source_relative_path)

        self.variant = normalized_variant
        self.source_relative_path = selected_source_path

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取 HaluMem JSONL 并转换为统一 Dataset。"""
        if limit is not None and limit <= 0:
            raise DatasetValidationError("halumem limit must be a positive integer")

        source_path = self.require_path(*self.source_relative_path.parts)
        conversations: list[Conversation] = []
        total_raw_users = 0
        source_fully_scanned = True
        with source_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                total_raw_users += 1
                try:
                    raw_user = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DatasetValidationError(
                        f"{self.source_relative_path.as_posix()}:{line_number}: invalid JSONL"
                    ) from exc
                if not isinstance(raw_user, dict):
                    raise DatasetValidationError(
                        f"{self.source_relative_path.as_posix()}:{line_number}: user row must be a dict"
                    )
                conversations.append(
                    _conversation_from_user(
                        raw_user,
                        source_relative_path=self.source_relative_path,
                        source_line_number=line_number,
                    )
                )
                if reached_limit(len(conversations), limit):
                    source_fully_scanned = False
                    break

        loaded_session_count = sum(
            len(conversation.sessions) for conversation in conversations
        )
        loaded_turn_count = sum(
            len(session.turns)
            for conversation in conversations
            for session in conversation.sessions
        )
        loaded_question_count = sum(
            len(conversation.questions) for conversation in conversations
        )
        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_paths": [self.source_relative_path.as_posix()],
                "variant": self.variant,
                "source_format": "halumem_jsonl",
                "total_raw_users": total_raw_users,
                "source_fully_scanned": source_fully_scanned,
                "loaded_conversation_count": len(conversations),
                "loaded_session_count": loaded_session_count,
                "loaded_turn_count": loaded_turn_count,
                "loaded_question_count": loaded_question_count,
            },
        )


def parse_halumem_timestamp(value: object) -> str | None:
    """把 HaluMem 官方时间字符串转成 UTC ISO；无法解析时返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.strptime(value.strip(), "%b %d, %Y, %H:%M:%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc).isoformat()


def _conversation_from_user(
    raw_user: dict[str, Any],
    *,
    source_relative_path: Path,
    source_line_number: int,
) -> Conversation:
    source_context = f"{source_relative_path.as_posix()}:{source_line_number}"
    uuid = _required_text(raw_user, "uuid", source_context)
    sessions_raw = _required_list(raw_user, "sessions", uuid)
    persona_info = raw_user.get("persona_info")
    if persona_info is not None and not isinstance(persona_info, str):
        raise DatasetValidationError(f"{uuid}: persona_info must be a string")

    sessions: list[Session] = []
    questions: list[Question] = []
    gold_answers: dict[str, GoldAnswerInfo] = {}
    for session_index, session_raw in enumerate(sessions_raw, start=1):
        if not isinstance(session_raw, dict):
            raise DatasetValidationError(f"{uuid}: sessions[{session_index - 1}] must be a dict")
        session, session_questions, session_gold = _session_from_raw(
            session_raw,
            conversation_id=uuid,
            session_index=session_index,
            persona_info=persona_info,
        )
        sessions.append(session)
        questions.extend(session_questions)
        gold_answers.update(session_gold)

    return Conversation(
        conversation_id=uuid,
        sessions=sessions,
        questions=questions,
        gold_answers=gold_answers,
        metadata={},
    )


def _session_from_raw(
    session_raw: dict[str, Any],
    *,
    conversation_id: str,
    session_index: int,
    persona_info: str | None,
) -> tuple[Session, list[Question], dict[str, GoldAnswerInfo]]:
    session_id = _optional_text(session_raw.get("session_id")) or f"s{session_index}"
    start_time = parse_halumem_timestamp(session_raw.get("start_time"))
    end_time = parse_halumem_timestamp(session_raw.get("end_time"))
    dialogue_raw = _required_list(session_raw, "dialogue", f"{conversation_id}/{session_id}")
    memory_points = _optional_list(session_raw.get("memory_points"), "memory_points")
    questions_raw = _optional_list(session_raw.get("questions"), "questions")

    turns = [
        _turn_from_raw(
            turn_raw,
            conversation_id=conversation_id,
            session_id=session_id,
            turn_index=turn_index,
        )
        for turn_index, turn_raw in enumerate(dialogue_raw, start=1)
    ]
    questions, gold_answers = _questions_from_raw(
        questions_raw,
        conversation_id=conversation_id,
        session_id=session_id,
        session_index=session_index,
        memory_points=memory_points,
        persona_info=persona_info,
    )

    return (
        Session(
            session_id=session_id,
            turns=turns,
            session_time=start_time,
            start_time=start_time,
            end_time=end_time,
            metadata={
                "is_generated_qa_session": bool(
                    session_raw.get("is_generated_qa_session", False)
                )
            },
            private_metadata={
                "source_format": "halumem_session",
                "source_session_index": session_index - 1,
                "source_session_id": _optional_text(session_raw.get("session_id")),
                "raw_start_time": session_raw.get("start_time"),
                "raw_end_time": session_raw.get("end_time"),
                "is_generated_qa_session": bool(
                    session_raw.get("is_generated_qa_session", False)
                ),
                "source_question_count": len(questions_raw),
                "memory_points": copy.deepcopy(memory_points),
                "persona_info": persona_info,
            },
        ),
        questions,
        gold_answers,
    )


def _turn_from_raw(
    turn_raw: object,
    *,
    conversation_id: str,
    session_id: str,
    turn_index: int,
) -> Turn:
    if not isinstance(turn_raw, dict):
        raise DatasetValidationError(
            f"{conversation_id}/{session_id}: dialogue[{turn_index - 1}] must be a dict"
        )
    role = _required_text(turn_raw, "role", f"{conversation_id}/{session_id}/t{turn_index}")
    content = _required_text(
        turn_raw,
        "content",
        f"{conversation_id}/{session_id}/t{turn_index}",
    )
    return Turn(
        turn_id=f"{session_id}:t{turn_index}",
        speaker=role,
        normalized_role=role,
        content=content,
        turn_time=parse_halumem_timestamp(turn_raw.get("timestamp")),
        metadata={"dialogue_turn": turn_raw.get("dialogue_turn")},
    )


def _questions_from_raw(
    questions_raw: list[Any],
    *,
    conversation_id: str,
    session_id: str,
    session_index: int,
    memory_points: list[Any],
    persona_info: str | None,
) -> tuple[list[Question], dict[str, GoldAnswerInfo]]:
    questions: list[Question] = []
    gold_answers: dict[str, GoldAnswerInfo] = {}
    for question_index, question_raw in enumerate(questions_raw, start=1):
        if not isinstance(question_raw, dict):
            raise DatasetValidationError(
                f"{conversation_id}/{session_id}: questions[{question_index - 1}] must be a dict"
            )
        question_id = f"{conversation_id}:{session_id}:q{question_index}"
        question_text = _required_text(question_raw, "question", question_id)
        answer_text = _required_text(question_raw, "answer", question_id)
        raw_evidence = _optional_list(question_raw.get("evidence"), "evidence")
        evidence_memory_contents = _evidence_memory_contents(raw_evidence)
        question_type = _optional_text(question_raw.get("question_type"))
        capability = map_native_task_to_capability("halumem", question_type)

        questions.append(
            Question(
                question_id=question_id,
                conversation_id=conversation_id,
                text=question_text,
                category=question_type,
                capability=capability,
                metadata={},
            )
        )
        gold_answers[question_id] = GoldAnswerInfo(
            question_id=question_id,
            answer=answer_text,
            metadata={
                "answer": answer_text,
                "raw_evidence": copy.deepcopy(raw_evidence),
                "difficulty": _optional_text(question_raw.get("difficulty")),
                "question_type": _optional_text(question_raw.get("question_type")),
                "session_id": session_id,
                "session_index": session_index,
                "source_question_index": question_index - 1,
                "session_memory_points": copy.deepcopy(memory_points),
                "persona_info": persona_info,
            },
        )

    return questions, gold_answers


def _evidence_memory_contents(raw_evidence: list[Any]) -> list[str]:
    memory_contents: list[str] = []
    for evidence in raw_evidence:
        if not isinstance(evidence, dict):
            continue
        evidence_content = evidence.get("memory_content")
        if isinstance(evidence_content, str) and evidence_content.strip():
            memory_contents.append(evidence_content.strip())
    return memory_contents


def _required_text(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{context}: {key} is required")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _required_list(payload: dict[str, Any], key: str, context: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise DatasetValidationError(f"{context}: {key} must be a list")
    return value


def _optional_list(value: object, key: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DatasetValidationError(f"{key} must be a list")
    return value

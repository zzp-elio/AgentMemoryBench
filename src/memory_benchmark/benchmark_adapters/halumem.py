"""HaluMem operation-level benchmark adapter。

本模块只负责把 `data/halumem/HaluMem-*.jsonl` 的 user/session/turn/question
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
    AnswerPromptResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    PromptMessage,
    Question,
    Session,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError, DatasetValidationError
from memory_benchmark.core.provider_protocol import RetrievalResult

from .base import BenchmarkAdapter, reached_limit
from .contracts import (
    BenchmarkLoadRequest,
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
)


HALUMEM_MEDIUM_SOURCE_PATH = Path("data/halumem/HaluMem-Medium.jsonl")
HALUMEM_LONG_SOURCE_PATH = Path("data/halumem/HaluMem-Long.jsonl")
HALUMEM_VARIANT_SPECS = (
    BenchmarkVariantSpec(
        name="medium",
        source_relative_paths=(HALUMEM_MEDIUM_SOURCE_PATH,),
    ),
    BenchmarkVariantSpec(
        name="long",
        source_relative_paths=(HALUMEM_LONG_SOURCE_PATH,),
    ),
)
HALUMEM_VARIANT_BY_NAME = {spec.name: spec for spec in HALUMEM_VARIANT_SPECS}
HALUMEM_MEMZERO_PROMPT_PROFILE = "halumem_memzero_v1"
HALUMEM_MEMZERO_OFFICIAL_SOURCE = (
    "third_party/benchmarks/HaluMem-main/eval/prompts.py:1-40"
)
HALUMEM_MEMZERO_PROMPT = """
    You are an intelligent memory assistant tasked with retrieving accurate information from conversation memories.

    # CONTEXT:
    You have access to memories from two speakers in a conversation. These memories contain
    timestamped information that may be relevant to answering the question.

    # INSTRUCTIONS:
    1. Carefully analyze all provided memories from both speakers
    2. Pay special attention to the timestamps to determine the answer
    3. If the question asks about a specific event or fact, look for direct evidence in the memories
    4. If the memories contain contradictory information, prioritize the most recent memory
    5. If there is a question about time references (like "last year", "two months ago", etc.),
       calculate the actual date based on the memory timestamp. For example, if a memory from
       4 May 2022 mentions "went to India last year," then the trip occurred in 2021.
    6. Always convert relative time references to specific dates, months, or years. For example,
       convert "last year" to "2022" or "two months ago" to "March 2023" based on the memory
       timestamp. Ignore the reference while answering the question.
    7. Focus only on the content of the memories from both speakers. Do not confuse character
       names mentioned in memories with the actual users who created those memories.
    8. The answer should be less than 5-6 words.

    # APPROACH (Think step by step):
    1. First, examine all memories that contain information related to the question
    2. Examine the timestamps and content of these memories carefully
    3. Look for explicit mentions of dates, times, locations, or events that answer the question
    4. If the answer requires calculation (e.g., converting relative time references), show your work
    5. Formulate a precise, concise answer based solely on the evidence in the memories
    6. Double-check that your answer directly addresses the question asked
    7. Ensure your final answer is specific and avoids vague time references

    {context}

    Question: {question}

    Answer:
    """


class HaluMemAdapter(BenchmarkAdapter):
    """HaluMem user 级连续会话数据 adapter。"""

    name = "halumem"

    def __init__(
        self,
        project_root: str | Path,
        variant: str = "medium",
        source_relative_path: Path | None = None,
    ):
        """初始化 HaluMem adapter 并锁定 concrete variant。"""

        super().__init__(project_root)
        normalized_variant = variant.strip() if isinstance(variant, str) else ""
        if not normalized_variant:
            raise ConfigurationError("halumem variant is required")
        if source_relative_path is None:
            try:
                variant_spec = HALUMEM_VARIANT_BY_NAME[normalized_variant]
            except KeyError as exc:
                allowed = ", ".join(spec.name for spec in HALUMEM_VARIANT_SPECS)
                raise ConfigurationError(
                    f"Unknown halumem variant '{variant}'. Allowed: {allowed}"
                ) from exc
            selected_source_path = variant_spec.source_relative_paths[0]
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

        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_paths": [self.source_relative_path.as_posix()],
                "variant": self.variant,
                "source_format": "halumem_jsonl",
                "total_raw_users": total_raw_users,
                "source_fully_scanned": source_fully_scanned,
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


def prepare_halumem_run(
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """为 HaluMem concrete variant 构造 full 或 smoke 运行。"""

    variant_spec = HALUMEM_VARIANT_BY_NAME.get(request.variant)
    if variant_spec is None:
        allowed = ", ".join(spec.name for spec in HALUMEM_VARIANT_SPECS)
        raise ConfigurationError(
            f"Unknown halumem variant '{request.variant}'. Allowed: {allowed}"
        )

    adapter = HaluMemAdapter(project_root, variant=request.variant)
    if request.run_scope is RunScope.FULL:
        dataset = adapter.load()
    elif request.run_scope is RunScope.SMOKE:
        dataset = adapter.load(limit=request.smoke_conversation_limit)
    else:  # pragma: no cover - RunScope 只有 smoke / full
        raise ConfigurationError(f"unsupported HaluMem run scope: {request.run_scope}")

    metadata = copy.deepcopy(dataset.metadata)
    metadata["variant"] = request.variant
    metadata["run_scope"] = request.run_scope.value
    return PreparedBenchmarkRun(
        variant=request.variant,
        run_scope=request.run_scope,
        dataset=Dataset(
            dataset_name=dataset.dataset_name,
            conversations=list(dataset.conversations),
            metadata=metadata,
        ),
        source_relative_paths=variant_spec.source_relative_paths,
    )


def build_halumem_unified_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """按 HaluMem 官方 PROMPT_MEMZERO 构造 framework reader prompt。"""

    answer_prompt = HALUMEM_MEMZERO_PROMPT.format(
        context=retrieval_result.formatted_memory,
        question=question.text,
    )
    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        answer_prompt=answer_prompt,
        prompt_messages=[PromptMessage(role="user", content=answer_prompt)],
        metadata={
            "prompt_track": "unified",
            "answer_prompt_profile": HALUMEM_MEMZERO_PROMPT_PROFILE,
            "official_source": HALUMEM_MEMZERO_OFFICIAL_SOURCE,
        },
    )


def _conversation_from_user(
    raw_user: dict[str, Any],
    *,
    source_relative_path: Path,
    source_line_number: int,
) -> Conversation:
    """把一个 HaluMem JSONL user row 转成 Conversation。"""

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
    """把 HaluMem session 拆成公开 Session 与私有 gold 标注。"""

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
            metadata={},
            private_metadata={
                "source_format": "halumem_session",
                "source_session_index": session_index - 1,
                "source_session_id": _optional_text(session_raw.get("session_id")),
                "raw_start_time": session_raw.get("start_time"),
                "raw_end_time": session_raw.get("end_time"),
                "is_generated_qa_session": bool(
                    session_raw.get("is_generated_qa_session", False)
                ),
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
    """把 HaluMem dialogue turn 转成公开 Turn。"""

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
    """把 session questions 拆成公开 Question 和私有 GoldAnswerInfo。"""

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
        evidence_indices = _evidence_memory_indices(raw_evidence, memory_points)

        questions.append(
            Question(
                question_id=question_id,
                conversation_id=conversation_id,
                text=question_text,
                metadata={},
            )
        )
        gold_answers[question_id] = GoldAnswerInfo(
            question_id=question_id,
            answer=answer_text,
            evidence=evidence_indices,
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


def _evidence_memory_indices(
    raw_evidence: list[Any],
    memory_points: list[Any],
) -> list[str]:
    """把 question evidence 文本映射为本 session memory point index。"""

    indices: list[str] = []
    for evidence in raw_evidence:
        if not isinstance(evidence, dict):
            continue
        evidence_content = evidence.get("memory_content")
        evidence_type = evidence.get("memory_type")
        for memory_point in memory_points:
            if not isinstance(memory_point, dict):
                continue
            if memory_point.get("memory_content") != evidence_content:
                continue
            if evidence_type is not None and memory_point.get("memory_type") != evidence_type:
                continue
            if "index" in memory_point:
                indices.append(str(memory_point["index"]))
            break
    return indices


def _required_text(payload: dict[str, Any], key: str, context: str) -> str:
    """读取必需字符串字段并标准化空白。"""

    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{context}: {key} is required")
    return value.strip()


def _optional_text(value: object) -> str | None:
    """把可选字符串字段标准化为空或文本。"""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _required_list(payload: dict[str, Any], key: str, context: str) -> list[Any]:
    """读取必需 list 字段。"""

    value = payload.get(key)
    if not isinstance(value, list):
        raise DatasetValidationError(f"{context}: {key} must be a list")
    return value


def _optional_list(value: object, key: str) -> list[Any]:
    """读取可选 list 字段，缺失时返回空列表。"""

    if value is None:
        return []
    if not isinstance(value, list):
        raise DatasetValidationError(f"{key} must be a list")
    return value

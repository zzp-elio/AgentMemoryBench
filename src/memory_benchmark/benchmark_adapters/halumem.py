"""HaluMem operation-level benchmark adapter。

本模块只负责把 `data/halumem/HaluMem-*.jsonl` 的 user/session/turn/question
层级转换为统一 Dataset。`memory_points`、reference answer、evidence、
difficulty、question_type 和 persona_info 只进入私有结构，不能出现在 method
可见公开 payload 中。
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
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
    BenchmarkResumePolicy,
    BenchmarkSmokePolicy,
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
HALUMEM_OFFICIAL_REPO_URL = "https://github.com/MemTensor/HaluMem"
HALUMEM_OFFICIAL_PAPER_URL = "https://arxiv.org/abs/2511.03506"
HALUMEM_OFFICIAL_DATASET_URL = "https://huggingface.co/datasets/IAAR-Shanghai/HaluMem"
HALUMEM_LICENSE = "CC-BY-NC-ND-4.0"
HALUMEM_SMOKE_POLICY = BenchmarkSmokePolicy(
    history_axis="sessions",
    default_history_limit=4,
    default_isolation_limit=1,
    default_question_limit=1,
)
HALUMEM_RESUME_POLICY = BenchmarkResumePolicy(
    smoke_enabled=False,
    ingest_checkpoint="conversation",
    answer_checkpoint="question",
    reuse_saved_retrieval=True,
    evaluation_artifact_only=True,
)
HALUMEM_MEMZERO_PROMPT_PROFILE = "halumem_memzero_v1"
HALUMEM_MEMZERO_OFFICIAL_SOURCE = (
    "third_party/benchmarks/HaluMem-main/eval/prompts.py:1-37"
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

        source_digest = hashlib.sha256()
        source_size_bytes = 0
        with source_path.open("rb") as source_file:
            while chunk := source_file.read(1024 * 1024):
                source_digest.update(chunk)
                source_size_bytes += len(chunk)

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
                "official_repo_url": HALUMEM_OFFICIAL_REPO_URL,
                "official_paper_url": HALUMEM_OFFICIAL_PAPER_URL,
                "official_dataset_url": HALUMEM_OFFICIAL_DATASET_URL,
                "license": HALUMEM_LICENSE,
                "source_sha256": source_digest.hexdigest(),
                "source_size_bytes": source_size_bytes,
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
        if (
            request.smoke_turn_limit != HALUMEM_SMOKE_POLICY.default_history_limit
            or request.smoke_conversation_limit
            != HALUMEM_SMOKE_POLICY.default_isolation_limit
            or request.smoke_session_limit is not None
        ):
            raise ConfigurationError(
                "halumem smoke has a fixed shape and does not accept cropping parameters"
            )
        dataset = _build_halumem_smoke_dataset(adapter.load(limit=1))
    else:  # pragma: no cover - RunScope 只有 smoke / full
        raise ConfigurationError(f"unsupported HaluMem run scope: {request.run_scope}")

    metadata = copy.deepcopy(dataset.metadata)
    metadata["variant"] = request.variant
    metadata["run_scope"] = request.run_scope.value
    metadata["smoke_policy"] = HALUMEM_SMOKE_POLICY.to_dict()
    metadata["resume_policy"] = HALUMEM_RESUME_POLICY.to_dict()
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
        evidence_memory_contents = _evidence_memory_contents(raw_evidence)

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
            evidence=evidence_memory_contents,
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
    """从 question evidence 中提取 judge 需要的 memory_content 文本。"""

    memory_contents: list[str] = []
    for evidence in raw_evidence:
        if not isinstance(evidence, dict):
            continue
        evidence_content = evidence.get("memory_content")
        if isinstance(evidence_content, str) and evidence_content.strip():
            memory_contents.append(evidence_content.strip())
    return memory_contents


def _build_halumem_smoke_dataset(
    dataset: Dataset,
) -> Dataset:
    """按三操作首现前缀、每 session 两 turn、全局一题构造固定 smoke。"""

    cropped_conversations: list[Conversation] = []
    total_original_session_count = 0
    total_retained_session_count = 0
    total_original_turn_count = 0
    total_retained_turn_count = 0
    total_original_question_count = 0
    total_retained_question_count = 0
    for conversation in dataset.conversations:
        prefix_length, first_seen = _halumem_smoke_prefix(conversation.sessions)
        retained_sessions = copy.deepcopy(conversation.sessions[:prefix_length])
        turn_shapes: list[dict[str, object]] = []
        round_anomaly = False
        for source_session, retained_session in zip(
            conversation.sessions[:prefix_length], retained_sessions, strict=True
        ):
            original_turn_count = len(source_session.turns)
            retained_session.turns = retained_session.turns[:2]
            session_anomaly = (
                original_turn_count < 2
                or not source_session.turns
                or source_session.turns[0].normalized_role != "user"
            )
            round_anomaly = round_anomaly or session_anomaly
            turn_shapes.append(
                {
                    "session_id": source_session.session_id,
                    "original_turn_count": original_turn_count,
                    "retained_turn_count": len(retained_session.turns),
                    "smoke_round_anomaly": session_anomaly,
                }
            )
        retained_session_ids = {session.session_id for session in retained_sessions}
        eligible_questions = [
            copy.deepcopy(question)
            for question in conversation.questions
            if _question_session_id(question.question_id) in retained_session_ids
        ]
        retained_questions = eligible_questions[:1]
        retained_gold_answers = {
            question.question_id: copy.deepcopy(
                conversation.gold_answers[question.question_id]
            )
            for question in retained_questions
        }
        total_original_session_count += len(conversation.sessions)
        total_retained_session_count += len(retained_sessions)
        total_original_turn_count += sum(
            len(session.turns) for session in conversation.sessions
        )
        total_retained_turn_count += sum(
            len(session.turns) for session in retained_sessions
        )
        total_original_question_count += len(conversation.questions)
        total_retained_question_count += len(retained_questions)
        metadata = copy.deepcopy(conversation.metadata)
        metadata.update(
            {
                "smoke_prefix_rule": {
                    "extraction_first_session": first_seen["extraction"],
                    "update_first_session": first_seen["update"],
                    "qa_first_session": first_seen["qa"],
                    "final_prefix_length": prefix_length,
                },
                "smoke_prefix_incomplete": any(
                    value is None for value in first_seen.values()
                ),
                "smoke_original_session_count": len(conversation.sessions),
                "smoke_retained_session_count": len(retained_sessions),
                "smoke_session_turn_shapes": turn_shapes,
                "smoke_round_anomaly": round_anomaly,
                "smoke_original_question_count": len(conversation.questions),
                "smoke_retained_question_count": len(retained_questions),
                "smoke_removed_question_count": (
                    len(conversation.questions) - len(retained_questions)
                ),
            }
        )
        cropped_conversations.append(
            Conversation(
                conversation_id=conversation.conversation_id,
                sessions=retained_sessions,
                questions=retained_questions,
                gold_answers=retained_gold_answers,
                metadata=metadata,
            )
        )

    metadata = copy.deepcopy(dataset.metadata)
    metadata.update(
        {
            "smoke_fixed_shape": True,
            "smoke_original_session_count": total_original_session_count,
            "smoke_retained_session_count": total_retained_session_count,
            "smoke_original_turn_count": total_original_turn_count,
            "smoke_retained_turn_count": total_retained_turn_count,
            "smoke_original_question_count": total_original_question_count,
            "smoke_retained_question_count": total_retained_question_count,
            "smoke_removed_question_count": (
                total_original_question_count - total_retained_question_count
            ),
            "smoke_conversation_shapes": [
                {
                    "conversation_id": conversation.conversation_id,
                    "smoke_prefix_rule": copy.deepcopy(
                        conversation.metadata["smoke_prefix_rule"]
                    ),
                    "smoke_prefix_incomplete": conversation.metadata[
                        "smoke_prefix_incomplete"
                    ],
                    "smoke_session_turn_shapes": copy.deepcopy(
                        conversation.metadata["smoke_session_turn_shapes"]
                    ),
                    "smoke_round_anomaly": conversation.metadata[
                        "smoke_round_anomaly"
                    ],
                    "smoke_original_question_count": conversation.metadata[
                        "smoke_original_question_count"
                    ],
                    "smoke_retained_question_count": conversation.metadata[
                        "smoke_retained_question_count"
                    ],
                    "smoke_removed_question_count": conversation.metadata[
                        "smoke_removed_question_count"
                    ],
                }
                for conversation in cropped_conversations
            ],
        }
    )
    return Dataset(
        dataset_name=dataset.dataset_name,
        conversations=cropped_conversations,
        metadata=metadata,
    )


def _halumem_smoke_prefix(
    sessions: list[Session],
) -> tuple[int, dict[str, int | None]]:
    """返回提取、更新、QA 三操作均首现时的最短 session 前缀。"""

    first_seen: dict[str, int | None] = {
        "extraction": None,
        "update": None,
        "qa": None,
    }
    for session_index, session in enumerate(sessions, start=1):
        memory_points = session.private_metadata.get("memory_points")
        if not isinstance(memory_points, list):
            memory_points = []
        if first_seen["extraction"] is None and memory_points:
            first_seen["extraction"] = session_index
        if first_seen["update"] is None and any(
            isinstance(point, dict)
            and point.get("is_update") == "True"
            and bool(point.get("original_memories"))
            for point in memory_points
        ):
            first_seen["update"] = session_index
        if (
            first_seen["qa"] is None
            and session.private_metadata.get("source_question_count", 0) > 0
        ):
            first_seen["qa"] = session_index
    if all(value is not None for value in first_seen.values()):
        prefix_length = max(
            value for value in first_seen.values() if value is not None
        )
        return prefix_length, first_seen
    return len(sessions), first_seen


def _question_session_id(question_id: str) -> str | None:
    """从 HaluMem question_id 中解析 session_id。"""

    parts = question_id.split(":")
    if len(parts) < 3:
        return None
    return parts[-2]


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

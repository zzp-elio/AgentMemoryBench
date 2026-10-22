"""MemBench conversation-QA adapter。

本模块负责把 `data/membench/Membenchdata/data2test` 下的 MemBench
trajectory 转换为统一 `Dataset -> Conversation -> Session -> Turn -> Question`
结构。`ground_truth`、`answer` 和 `target_step_id` 只进入 `GoldAnswerInfo`，
不能出现在 method 可见的公开 payload 中。
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from memory_benchmark.core import (
    AnswerResult,
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


MEMBENCH_DATA2TEST_ROOT = Path("data/membench/Membenchdata/data2test")
MEMBENCH_0_10K_SOURCE_PATHS = (
    MEMBENCH_DATA2TEST_ROOT / "0-10k/FirstAgentDataHighLevel_multiple_0.json",
    MEMBENCH_DATA2TEST_ROOT / "0-10k/FirstAgentDataLowLevel_multiple_0.json",
    MEMBENCH_DATA2TEST_ROOT / "0-10k/ThirdAgentDataHighLevel_multiple_0.json",
    MEMBENCH_DATA2TEST_ROOT / "0-10k/ThirdAgentDataLowLevel_multiple_0.json",
)
MEMBENCH_100K_SOURCE_PATHS = (
    MEMBENCH_DATA2TEST_ROOT / "100k/FirstAgentDataHighLevel_multiple_100.json",
    MEMBENCH_DATA2TEST_ROOT / "100k/FirstAgentDataLowLevel_multiple_100.json",
    MEMBENCH_DATA2TEST_ROOT / "100k/ThirdAgentDataHighLevel_multiple_100.json",
    MEMBENCH_DATA2TEST_ROOT / "100k/ThirdAgentDataLowLevel_multiple_100.json",
)
MEMBENCH_VARIANT_PATHS: dict[str, tuple[Path, ...]] = {
    "0_10k": MEMBENCH_0_10K_SOURCE_PATHS,
    "100k": MEMBENCH_100K_SOURCE_PATHS,
}
_MEMBENCH_CHOICE_PATTERN_UPPER = re.compile(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])")
_MEMBENCH_CHOICE_PATTERN_LOWER = re.compile(r"(?<![A-Za-z])([abcd])(?![A-Za-z])")


class MemBenchAdapter(BenchmarkAdapter):
    """MemBench benchmark 的 trajectory-QA 数据 adapter。"""

    name = "membench"

    def __init__(
        self,
        project_root: str | Path,
        variant: str = "0_10k",
        source_relative_paths: tuple[Path, ...] | None = None,
    ):
        super().__init__(project_root)
        normalized_variant = variant.strip() if isinstance(variant, str) else ""
        if not normalized_variant:
            raise ConfigurationError("membench variant is required")
        if source_relative_paths is None:
            if normalized_variant not in MEMBENCH_VARIANT_PATHS:
                allowed = ", ".join(MEMBENCH_VARIANT_PATHS)
                raise ConfigurationError(
                    f"Unknown membench variant '{variant}'. Allowed: {allowed}"
                )
            selected_source_paths = MEMBENCH_VARIANT_PATHS[normalized_variant]
        else:
            selected_source_paths = tuple(Path(path) for path in source_relative_paths)
            if not selected_source_paths:
                raise ConfigurationError("membench source_relative_paths cannot be empty")

        self.variant = normalized_variant
        self.source_relative_paths = selected_source_paths

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取选定 MemBench 文件并转换为统一 Dataset。"""
        if limit is not None and limit <= 0:
            raise DatasetValidationError("membench limit must be a positive integer")

        conversations: list[Conversation] = []
        total_raw_trajectories = 0
        scored_conversations_count = 0
        source_fully_scanned = True
        for source_relative_path in self.source_relative_paths:
            raw_data = self.load_json(*source_relative_path.parts)
            source_context = source_relative_path.as_posix()
            source_profile = _source_profile_from_path(source_relative_path)
            seen_conversation_ids_in_file: set[str] = set()
            for question_type, scenario, trajectory in _iter_trajectories(
                raw_data,
                source_context,
            ):
                total_raw_trajectories += 1
                tid = _required_text(trajectory, "tid", source_context)
                conversation_id = _conversation_id(
                    source_profile=source_profile,
                    question_type=question_type,
                    scenario=scenario,
                    tid=tid,
                )
                if conversation_id in seen_conversation_ids_in_file:
                    raise DatasetValidationError(
                        f"{source_context}: duplicate conversation_id within source file: "
                        f"{conversation_id}"
                    )
                seen_conversation_ids_in_file.add(conversation_id)
                conv = _conversation_from_trajectory(
                    trajectory,
                    question_type=question_type,
                    scenario=scenario,
                    source_profile=source_profile,
                    source_relative_path=source_relative_path,
                )
                conversations.append(conv)
                if any(q.unified_capability is not None for q in conv.questions):
                    scored_conversations_count += 1
                    if reached_limit(scored_conversations_count, limit):
                        source_fully_scanned = False
                        return self._dataset(
                            conversations,
                            total_raw_trajectories=total_raw_trajectories,
                            source_fully_scanned=source_fully_scanned,
                        )

        return self._dataset(
            conversations,
            total_raw_trajectories=total_raw_trajectories,
            source_fully_scanned=source_fully_scanned,
        )

    def _dataset(
        self,
        conversations: list[Conversation],
        *,
        total_raw_trajectories: int,
        source_fully_scanned: bool,
    ) -> Dataset:
        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_paths": [path.as_posix() for path in self.source_relative_paths],
                "variant": self.variant,
                "source_format": "membench_data2test",
                "total_raw_trajectories": total_raw_trajectories,
                "source_fully_scanned": source_fully_scanned,
                "official_conversation_count": len(conversations),
                "official_question_count": len(conversations),
            },
        )


def normalize_membench_choice_prediction(prediction: AnswerResult) -> AnswerResult:
    """把 MemBench reader 原始输出规整为 A/B/C/D；无法解析时记 invalid_choice。"""
    raw_answer = prediction.answer
    parsed_choice = parse_membench_choice(raw_answer)
    metadata = dict(prediction.metadata)
    metadata["raw_answer"] = raw_answer
    metadata["choice_parse_status"] = (
        "parsed" if parsed_choice != "invalid_choice" else "invalid_choice"
    )
    return AnswerResult(
        question_id=prediction.question_id,
        conversation_id=prediction.conversation_id,
        answer=parsed_choice,
        metadata=metadata,
    )


def parse_membench_choice(raw_answer: str) -> str:
    """从 reader 输出中提取 A/B/C/D，失败返回 `invalid_choice`。"""
    text = str(raw_answer).strip()
    if not text:
        return "invalid_choice"
    json_choice = _choice_from_json_text(text)
    if json_choice is not None:
        return json_choice
    match = _MEMBENCH_CHOICE_PATTERN_UPPER.search(text)
    if match is None:
        match = _MEMBENCH_CHOICE_PATTERN_LOWER.search(text)
    if match is None:
        return "invalid_choice"
    return match.group(1).upper()


def _choice_from_json_text(text: str) -> str | None:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    choice = payload.get("choice")
    if not isinstance(choice, str):
        return None
    normalized = choice.strip().upper()
    if normalized in {"A", "B", "C", "D"}:
        return normalized
    return "invalid_choice"


def _iter_trajectories(
    raw_data: object,
    source_context: str,
) -> list[tuple[str, str, dict[str, Any]]]:
    if not isinstance(raw_data, dict):
        raise DatasetValidationError(f"{source_context}: top-level JSON must be a dict")

    trajectories: list[tuple[str, str, dict[str, Any]]] = []
    for question_type, scenarios in raw_data.items():
        if not isinstance(scenarios, dict):
            raise DatasetValidationError(
                f"{source_context}/{question_type}: scenarios must be a dict"
            )
        for scenario, trajectory_list in scenarios.items():
            if not isinstance(trajectory_list, list):
                raise DatasetValidationError(
                    f"{source_context}/{question_type}/{scenario}: trajectories must be a list"
                )
            for index, trajectory in enumerate(trajectory_list):
                if not isinstance(trajectory, dict):
                    raise DatasetValidationError(
                        f"{source_context}/{question_type}/{scenario}[{index}]: "
                        "trajectory must be a dict"
                    )
                trajectories.append((str(question_type), str(scenario), trajectory))
    return trajectories


def _conversation_from_trajectory(
    trajectory: dict[str, Any],
    *,
    question_type: str,
    scenario: str,
    source_profile: dict[str, str],
    source_relative_path: Path,
) -> Conversation:
    tid = _required_text(trajectory, "tid", source_relative_path.as_posix())
    conversation_id = _conversation_id(
        source_profile=source_profile,
        question_type=question_type,
        scenario=scenario,
        tid=tid,
    )
    messages = _required_list(trajectory, "message_list", conversation_id)
    qa = _required_dict(trajectory, "QA", conversation_id)
    turns: list[Turn] = []
    for index, step in enumerate(messages):
        step_turns = _turns_from_step(
            step, step_index=index, conversation_id=conversation_id
        )
        turns.extend(step_turns)
    if not turns:
        raise DatasetValidationError(f"{conversation_id}: message_list is empty")

    question, gold = _question_and_gold_from_qa(
        qa,
        conversation_id=conversation_id,
        question_type=question_type,
        scenario=scenario,
        tid=tid,
    )

    return Conversation(
        conversation_id=conversation_id,
        sessions=[
            Session(
                session_id="s1",
                session_time=None,
                turns=turns,
                metadata={
                    "source_format": "membench_trajectory",
                    "tid": tid,
                    "scenario": scenario,
                    **source_profile,
                },
            )
        ],
        questions=[question],
        gold_answers={question.question_id: gold},
        metadata={
            "source_path": source_relative_path.as_posix(),
            "source_format": "membench",
            "variant_source_stream": source_profile["source_stream"],
            "level": source_profile["level"],
            "question_type": question_type,
            "scenario": scenario,
            "source_tid": tid,
        },
    )


_MEMBENCH_TURN_TIME_RE = re.compile(r"time:?\s*'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})'")


def _membench_turn_time(text: str) -> str | None:
    match = _MEMBENCH_TURN_TIME_RE.search(text)
    return match.group(1) if match else None


def _turns_from_step(
    step: object,
    *,
    step_index: int,
    conversation_id: str,
) -> list[Turn]:
    step_number = step_index + 1
    context = f"{conversation_id}:step{step_number}"
    if isinstance(step, dict):
        user_text = _required_text(step, "user", context)
        agent_text = _required_text(step, "agent", context)
        return [
            _build_step_turn(
                turn_id=f"{step_number}:user",
                speaker="user",
                normalized_role="user",
                content=user_text,
                step_index=step_index,
                step_number=step_number,
                source_step_role="user",
                side_metadata={"ps_user": user_text},
            ),
            _build_step_turn(
                turn_id=f"{step_number}:assistant",
                speaker="agent",
                normalized_role="assistant",
                content=agent_text,
                step_index=step_index,
                step_number=step_number,
                source_step_role="agent",
                side_metadata={"ps_agent": agent_text},
            ),
        ]
    if isinstance(step, str):
        content = step
        if not content.strip():
            raise DatasetValidationError(
                f"{conversation_id}: step {step_number} content is empty"
            )
        return [
            _build_step_turn(
                turn_id=str(step_number),
                speaker="user",
                normalized_role="user",
                content=content,
                step_index=step_index,
                step_number=step_number,
                source_step_role="observation",
                side_metadata={},
            )
        ]
    raise DatasetValidationError(
        f"{conversation_id}: message_list[{step_index}] must be a dict or string"
    )


def _build_step_turn(
    *,
    turn_id: str,
    speaker: str,
    normalized_role: str,
    content: str,
    step_index: int,
    step_number: int,
    source_step_role: str,
    side_metadata: dict[str, str],
) -> Turn:
    turn_time = _membench_turn_time(content)
    metadata: dict[str, Any] = {
        "source_step_index": step_index,
        "source_step_number": step_number,
        "source_step_role": source_step_role,
        **side_metadata,
        "source_timestamp_embedded_in_content": bool(turn_time),
    }
    return Turn(
        turn_id=turn_id,
        speaker=speaker,
        normalized_role=normalized_role,
        content=content,
        turn_time=turn_time,
        metadata=metadata,
    )


def _question_and_gold_from_qa(
    qa: dict[str, Any],
    *,
    conversation_id: str,
    question_type: str,
    scenario: str,
    tid: str,
) -> tuple[Question, GoldAnswerInfo]:
    question_text = _required_text(qa, "question", conversation_id)
    answer_text = _required_text(qa, "answer", conversation_id)
    ground_truth = _required_text(qa, "ground_truth", conversation_id).upper()
    if ground_truth not in {"A", "B", "C", "D"}:
        raise DatasetValidationError(
            f"{conversation_id}: ground_truth must be one of A/B/C/D"
        )
    question_time = _optional_text(qa.get("time"))
    choices = _choices_dict(qa.get("choices"), conversation_id)
    target_step_ids = _target_step_ids(qa.get("target_step_id"), conversation_id)
    qid = _optional_text(qa.get("qid")) or "0"
    question_id = f"{conversation_id}:q{qid}"

    capability = map_native_task_to_capability("membench", question_type)
    question = Question(
        question_id=question_id,
        conversation_id=conversation_id,
        text=question_text,
        question_time=question_time,
        category=question_type,
        capability=capability,
        options=choices,
        metadata={
            "choices": choices,
            "question_type": question_type,
            "scenario": scenario,
            "source_qid": qid,
            "source_tid": tid,
        },
    )
    gold = GoldAnswerInfo(
        question_id=question_id,
        answer=answer_text,
        metadata={
            "ground_truth": ground_truth,
            "answer": answer_text,
            "target_step_id": target_step_ids,
            "question_type": question_type,
            "scenario": scenario,
            "source_qid": qid,
            "source_tid": tid,
        },
    )
    return question, gold


def _source_profile_from_path(path: Path) -> dict[str, str]:
    name = path.name
    if name.startswith("FirstAgent"):
        source_stream = "first"
    elif name.startswith("ThirdAgent"):
        source_stream = "third"
    else:
        raise DatasetValidationError(f"{path.as_posix()}: unknown MemBench source stream")

    if "HighLevel" in name:
        level = "high"
    elif "LowLevel" in name:
        level = "low"
    else:
        raise DatasetValidationError(f"{path.as_posix()}: unknown MemBench level")
    return {"source_stream": source_stream, "level": level}


def _conversation_id(
    *,
    source_profile: dict[str, str],
    question_type: str,
    scenario: str,
    tid: str,
) -> str:
    return (
        f"{source_profile['source_stream']}-"
        f"{source_profile['level']}-"
        f"{question_type}-"
        f"{_safe_id_part(scenario)}-"
        f"{tid}"
    )


def _safe_id_part(value: str) -> str:
    return str(value).strip().replace(" ", "_")


def _required_text(raw: dict[str, Any], key: str, context: str) -> str:
    value = raw.get(key)
    text = str(value).strip() if value is not None else ""
    if not text:
        raise DatasetValidationError(f"{context}: {key} is required")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_dict(raw: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise DatasetValidationError(f"{context}: {key} must be a dict")
    return value


def _required_list(raw: dict[str, Any], key: str, context: str) -> list[Any]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise DatasetValidationError(f"{context}: {key} must be a list")
    return value


def _choices_dict(value: object, context: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise DatasetValidationError(f"{context}: choices must be a dict")
    choices: dict[str, str] = {}
    for key in ("A", "B", "C", "D"):
        text = str(value.get(key)).strip() if value.get(key) is not None else ""
        if not text:
            raise DatasetValidationError(f"{context}: choices.{key} is required")
        choices[key] = text
    return choices


def _target_step_ids(value: object, context: str) -> list[int]:
    if not isinstance(value, list):
        raise DatasetValidationError(f"{context}: target_step_id must be a list")
    step_ids: list[int] = []
    for index, item in enumerate(value):
        if isinstance(item, bool):
            raise DatasetValidationError(
                f"{context}: target_step_id[{index}] must be an integer"
            )
        try:
            step_id = int(item)
        except (TypeError, ValueError) as exc:
            raise DatasetValidationError(
                f"{context}: target_step_id[{index}] must be an integer"
            ) from exc
        if step_id < 0:
            raise DatasetValidationError(
                f"{context}: target_step_id[{index}] must be non-negative"
            )
        step_ids.append(step_id)
    return step_ids


__all__ = [
    "MEMBENCH_0_10K_SOURCE_PATHS",
    "MEMBENCH_100K_SOURCE_PATHS",
    "MemBenchAdapter",
    "normalize_membench_choice_prediction",
    "parse_membench_choice",
]

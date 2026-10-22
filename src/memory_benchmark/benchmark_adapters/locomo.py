"""LoCoMo conversation-QA adapter。

本模块负责把 `data/locomo/locomo10.json` 转换为统一的
`Dataset -> Conversation -> Session -> Turn -> Question` 结构。标准答案和
evidence 只写入 `GoldAnswerInfo`，不能进入 method 可见的 `Question`。
"""

from __future__ import annotations

import json
import re
from typing import Any

from memory_benchmark.core import (
    Conversation,
    Dataset,
    GoldAnswerInfo,
    ImageRef,
    Question,
    Session,
    Turn,
    map_native_task_to_capability,
)
from memory_benchmark.core.exceptions import DatasetValidationError

from .base import BenchmarkAdapter, reached_limit


LOCOMO_SOURCE_PATH = "data/locomo/locomo10.json"
ADVERSARIAL_CATEGORY = "5"
SESSION_KEY_PATTERN = re.compile(r"^session_(\d+)$")
LOCOMO_TASK = "question_answering"
LOCOMO_EXCLUDED_QUESTION_CATEGORIES = (int(ADVERSARIAL_CATEGORY),)


class LoCoMoAdapter(BenchmarkAdapter):
    """LoCoMo benchmark 数据 adapter。

    输入数据:
        项目根目录下的 `data/locomo/locomo10.json`。

    输出:
        一个 top-level sample 转成一个 `Conversation`，其中 QA 被拆成公开
        `Question` 和 evaluator-only `GoldAnswerInfo`。
    """

    name = "locomo"

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取 LoCoMo 原始数据并转换为统一 Dataset。"""
        if limit is not None and limit <= 0:
            raise DatasetValidationError("locomo limit must be a positive integer")

        raw_samples = self.load_json("data", "locomo", "locomo10.json")
        sample_items = _sample_items(raw_samples)

        conversations: list[Conversation] = []
        for raw_index, sample in sample_items:
            conversations.append(self._conversation_from_sample(sample, raw_index))
            if reached_limit(len(conversations), limit):
                break

        processed_sample_items = sample_items[: len(conversations)]
        official_question_count = sum(
            len(sample.get("qa", [])) for _, sample in processed_sample_items
        )
        loaded_question_count = sum(
            len(conversation.questions) for conversation in conversations
        )

        return Dataset(
            dataset_name=self.name,
            conversations=conversations,
            metadata={
                "source_path": LOCOMO_SOURCE_PATH,
                "split": "locomo10",
                "source_format": "locomo",
                "total_raw_samples": len(sample_items),
                "task": LOCOMO_TASK,
                "official_question_count": official_question_count,
                "loaded_question_count": loaded_question_count,
                "excluded_question_categories": list(LOCOMO_EXCLUDED_QUESTION_CATEGORIES),
            },
        )

    def _conversation_from_sample(
        self,
        sample: dict[str, Any],
        raw_index: str,
    ) -> Conversation:
        """把一个 LoCoMo sample 转成 Conversation。"""
        conversation_id = _required_text(sample, "sample_id", f"sample {raw_index}")
        conversation_raw = _required_dict(sample, "conversation", conversation_id)
        sessions = [
            self._session_from_raw(conversation_raw, session_key)
            for session_key in _session_keys(conversation_raw)
        ]
        questions, gold_answers, skipped_adversarial_count = self._questions_from_raw(
            sample.get("qa", []),
            conversation_id,
        )

        return Conversation(
            conversation_id=conversation_id,
            sessions=sessions,
            questions=questions,
            gold_answers=gold_answers,
            metadata={
                "source_path": LOCOMO_SOURCE_PATH,
                "source_sample_id": conversation_id,
                "speaker_a": _optional_text(conversation_raw.get("speaker_a")),
                "speaker_b": _optional_text(conversation_raw.get("speaker_b")),
                "skipped_adversarial_question_count": skipped_adversarial_count,
            },
        )

    def _session_from_raw(
        self,
        conversation_raw: dict[str, Any],
        session_key: str,
    ) -> Session:
        """把一个 `session_<n>` 字段转成 Session。"""
        turns_raw = conversation_raw.get(session_key)
        if not isinstance(turns_raw, list):
            raise DatasetValidationError(f"{session_key}: session must be a list")

        session_number = _session_number(session_key)
        session_time = _optional_text(conversation_raw.get(f"{session_key}_date_time"))
        turns = [
            _turn_from_raw(turn_raw, session_number, turn_index)
            for turn_index, turn_raw in enumerate(turns_raw, start=1)
        ]

        return Session(
            session_id=session_key,
            session_time=session_time,
            turns=turns,
            metadata={"session_number": session_number},
        )

    def _questions_from_raw(
        self,
        qa_raw: object,
        conversation_id: str,
    ) -> tuple[list[Question], dict[str, GoldAnswerInfo], int]:
        """把 LoCoMo QA 标注拆成公开 Question 和私有 GoldAnswerInfo。"""
        if not isinstance(qa_raw, list):
            raise DatasetValidationError(f"{conversation_id}: qa must be a list")

        questions: list[Question] = []
        gold_answers: dict[str, GoldAnswerInfo] = {}
        skipped_adversarial_count = 0

        for index, qa_item in enumerate(qa_raw):
            if not isinstance(qa_item, dict):
                raise DatasetValidationError(f"{conversation_id}: qa[{index}] must be a dict")

            category = _qa_category(qa_item)
            if category == ADVERSARIAL_CATEGORY:
                skipped_adversarial_count += 1
                continue

            question_id = f"{conversation_id}:q{index}"
            question_text = _required_text(qa_item, "question", question_id)
            if "answer" not in qa_item:
                raise DatasetValidationError(f"{question_id}: answer is required")

            capability = map_native_task_to_capability("locomo", category)
            questions.append(
                Question(
                    question_id=question_id,
                    conversation_id=conversation_id,
                    text=question_text,
                    category=category,
                    capability=capability,
                    metadata={"source_index": index},
                )
            )
            gold_answers[question_id] = GoldAnswerInfo(
                question_id=question_id,
                answer=_answer_to_text(qa_item.get("answer")),
                metadata={
                    "category": category,
                    "source_index": index,
                },
            )

        return questions, gold_answers, skipped_adversarial_count


def _session_keys(conversation_raw: dict[str, object]) -> list[str]:
    keys = [key for key in conversation_raw if SESSION_KEY_PATTERN.fullmatch(key)]
    return sorted(keys, key=_session_number)


def _session_number(session_key: str) -> int:
    match = SESSION_KEY_PATTERN.fullmatch(session_key)
    if match is None:
        raise DatasetValidationError(f"{session_key}: invalid session key")
    return int(match.group(1))


def _qa_category(raw: dict[str, object]) -> str | None:
    category = raw.get("category")
    if category is None:
        return None
    category_text = str(category).strip()
    return category_text or None


def _sample_items(raw_samples: object) -> list[tuple[str, dict[str, Any]]]:
    if isinstance(raw_samples, list):
        items = [(str(index), sample) for index, sample in enumerate(raw_samples)]
    elif isinstance(raw_samples, dict):
        items = [(str(key), raw_samples[key]) for key in sorted(raw_samples)]
    else:
        raise DatasetValidationError("locomo raw data must be a list or dict")

    for raw_index, sample in items:
        if not isinstance(sample, dict):
            raise DatasetValidationError(f"sample {raw_index}: sample must be a dict")
    return items


def _turn_from_raw(raw_turn: object, session_number: int, turn_index: int) -> Turn:
    if not isinstance(raw_turn, dict):
        raise DatasetValidationError(f"D{session_number}:{turn_index}: turn must be a dict")

    turn_id = _optional_text(raw_turn.get("dia_id")) or f"D{session_number}:{turn_index}"
    speaker = _required_text(raw_turn, "speaker", turn_id)
    content = _optional_text(raw_turn.get("text")) or ""
    caption = _optional_text(raw_turn.get("blip_caption"))
    if caption:
        content = f"{content} (image description: {caption})".strip()
    images = _image_refs_from_turn(raw_turn, turn_id)

    metadata: dict[str, Any] = {}
    query = _optional_text(raw_turn.get("query"))
    if query is not None:
        metadata["image_query"] = query
    if "re-download" in raw_turn:
        metadata["image_redownload_requested"] = bool(raw_turn.get("re-download"))

    return Turn(
        turn_id=turn_id,
        speaker=speaker,
        content=content,
        normalized_role=None,
        images=images,
        metadata=metadata,
    )


def _image_refs_from_turn(raw_turn: dict[str, Any], turn_id: str) -> list[ImageRef]:
    caption = _optional_text(raw_turn.get("blip_caption"))
    query = _optional_text(raw_turn.get("query"))
    image_urls = _image_url_list(raw_turn.get("img_url"))

    if not image_urls and caption is None:
        return []

    if not image_urls:
        return [
            ImageRef(
                image_id=f"{turn_id}:image1",
                caption=caption,
                metadata=_image_metadata(None, query),
            )
        ]

    return [
        ImageRef(
            image_id=f"{turn_id}:image{index}",
            caption=caption,
            metadata=_image_metadata(url, query),
        )
        for index, url in enumerate(image_urls, start=1)
    ]


def _image_url_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _image_metadata(url: str | None, query: str | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if url is not None:
        metadata["url"] = url
        metadata["source_field"] = "img_url"
    if query is not None:
        metadata["query"] = query
    return metadata


def _required_dict(raw: dict[str, Any], key: str, context: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise DatasetValidationError(f"{context}: {key} must be a dict")
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


def _evidence_to_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []

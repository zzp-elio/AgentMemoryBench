"""旧 BaseMemoryProvider 到 provider v3 协议的兼容桥。"""

from __future__ import annotations

import logging
from dataclasses import is_dataclass, asdict
from typing import Any

from memory_benchmark.core.entities import Conversation, ImageRef, Session, Turn
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.core.provider_protocol import (
    BRIDGE_EMPTY_MEMORY_SENTINEL,
    ConversationBatch,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
)


_LOGGER = logging.getLogger(__name__)
_BRIDGE_WARNING = "legacy_provider_exposed_no_memory_context"


class LegacyProviderBridge(MemoryProvider):
    """把旧 retrieve-first provider 包装成 v3 MemoryProvider。"""

    consume_granularity = "conversation"

    def __init__(self, legacy_provider: BaseMemoryProvider):
        """保存被包装的旧 provider。"""

        self.legacy_provider = legacy_provider

    def ingest(self, unit: IngestUnit) -> IngestResult:
        """把 ConversationBatch 重建为旧 Conversation 后调用 add。"""

        if not isinstance(unit, ConversationBatch):
            raise ConfigurationError(
                "LegacyProviderBridge only accepts ConversationBatch ingest units"
            )
        conversation = _conversation_from_batch(unit)
        result = self.legacy_provider.add(conversation)
        if conversation.conversation_id not in result.conversation_ids:
            raise ConfigurationError(
                "Legacy provider add result did not include expected "
                f"conversation_id: {conversation.conversation_id}"
            )
        return IngestResult(
            unit_ref=unit.ref,
            metadata={
                "legacy_conversation_id": conversation.conversation_id,
            },
        )

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """调用旧 retrieve 并映射为 v3 RetrievalResult。"""

        if query.source_question is None:
            raise ConfigurationError(
                "LegacyProviderBridge requires RetrievalQuery.source_question"
            )
        legacy_result = self.legacy_provider.retrieve(query.source_question)
        if legacy_result.question_id != query.source_question.question_id:
            raise ConfigurationError(
                "Legacy retrieval question_id mismatch: "
                f"{legacy_result.question_id} != {query.source_question.question_id}"
            )
        if legacy_result.conversation_id != query.source_question.conversation_id:
            raise ConfigurationError(
                "Legacy retrieval conversation_id mismatch: "
                f"{legacy_result.conversation_id} != "
                f"{query.source_question.conversation_id}"
            )
        metadata = dict(legacy_result.metadata)
        if legacy_result.answer_prompt.strip():
            metadata["bridge_legacy_answer_prompt"] = legacy_result.answer_prompt
        formatted_memory = _formatted_memory_from_metadata(metadata)
        if formatted_memory is None:
            metadata["bridge_warning"] = _BRIDGE_WARNING
            formatted_memory = BRIDGE_EMPTY_MEMORY_SENTINEL
            _LOGGER.warning(
                "legacy_provider_empty_memory_context",
                extra={
                    "question_id": query.source_question.question_id,
                    "conversation_id": query.source_question.conversation_id,
                    "bridge_warning": _BRIDGE_WARNING,
                },
            )
        return RetrievalResult(
            formatted_memory=formatted_memory,
            prompt_messages=tuple(legacy_result.prompt_messages),
            metadata=metadata,
        )


def _conversation_from_batch(batch: ConversationBatch) -> Conversation:
    """从 v3 conversation batch 重建旧 Conversation。"""

    conversation_id = _conversation_id_from_batch(batch)
    sessions: list[Session] = []
    for session_batch in batch.sessions:
        turns = [
            Turn(
                turn_id=event.turn_id,
                speaker=event.speaker_name or event.role,
                content=event.content,
                normalized_role=event.role,
                turn_time=_optional_text(event.metadata.get("original_turn_time")),
                images=_images_from_event(event.metadata),
                metadata=dict(event.metadata.get("turn_metadata") or {}),
            )
            for event in session_batch.events
        ]
        session_metadata = dict(session_batch.metadata)
        sessions.append(
            Session(
                session_id=session_batch.session_id or "",
                turns=turns,
                session_time=session_batch.session_time,
                start_time=_optional_text(session_metadata.pop("session_start_time", None)),
                end_time=_optional_text(session_metadata.pop("session_end_time", None)),
                metadata=session_metadata,
            )
        )
    return Conversation(
        conversation_id=conversation_id,
        sessions=sessions,
        questions=[],
        gold_answers={},
        metadata={
            **dict(batch.metadata),
            "isolation_key": batch.isolation_key,
        },
    )


def _conversation_id_from_batch(batch: ConversationBatch) -> str:
    """从 batch metadata 或事件 metadata 推断旧 conversation id。"""

    metadata_id = batch.metadata.get("conversation_id")
    if isinstance(metadata_id, str) and metadata_id.strip():
        return metadata_id
    for event in batch.events:
        event_id = event.metadata.get("conversation_id")
        if isinstance(event_id, str) and event_id.strip():
            return event_id
    return batch.isolation_key


def _formatted_memory_from_metadata(metadata: dict[str, Any]) -> str | None:
    """按桥接裁定的 fallback 链提取 formatted_memory。"""

    answer_context = metadata.get("answer_context")
    if isinstance(answer_context, str) and answer_context.strip():
        return answer_context.strip()

    retrieved_memories = metadata.get("retrieved_memories")
    contents = _memory_contents(retrieved_memories)
    if contents:
        return "\n".join(contents)
    return None


def _memory_contents(value: Any) -> list[str]:
    """从旧 retrieved_memories 形态中抽取非空 content。"""

    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list | tuple):
        return []
    contents: list[str] = []
    for item in value:
        content = _memory_content(item)
        if content:
            contents.append(content)
    return contents


def _memory_content(item: Any) -> str | None:
    """从单条旧 memory 记录中抽取公开文本。"""

    if isinstance(item, str):
        return item.strip() or None
    if isinstance(item, dict):
        content = item.get("content")
    elif is_dataclass(item):
        content = asdict(item).get("content")
    else:
        content = getattr(item, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    return None


def _images_from_event(metadata: dict[str, Any]) -> list[ImageRef]:
    """从事件 metadata 中恢复公开图片引用。"""

    raw_images = metadata.get("turn_images")
    if not isinstance(raw_images, list):
        return []
    images: list[ImageRef] = []
    for raw_image in raw_images:
        if not isinstance(raw_image, dict):
            continue
        images.append(
            ImageRef(
                image_id=_optional_text(raw_image.get("image_id")),
                path=_optional_text(raw_image.get("path")),
                caption=_optional_text(raw_image.get("caption")),
                metadata=dict(raw_image.get("metadata") or {}),
            )
        )
    return images


def _optional_text(value: Any) -> str | None:
    """把可选公开文本值规范为 str | None。"""

    return value if isinstance(value, str) else None


__all__ = ["LegacyProviderBridge"]

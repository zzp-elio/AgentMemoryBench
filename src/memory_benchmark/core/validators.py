"""conversation-QA 数据校验工具。

adapter 转换原始数据后必须立刻调用这些函数，保证缺字段在进入 method 前暴露。
公开 payload 进入 method 前也可以用 private key 检查防止标准答案泄漏。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .entities import Conversation, Dataset
from .exceptions import DataLeakageError, DatasetValidationError


PRIVATE_KEY_NAMES = {
    "answer",
    "answer_session_ids",
    "answers",
    "evidence",
    "gold",
    "gold_answer",
    "gold_answers",
    "ground_truth",
    "judge_label",
    "label",
    "target_step_id",
}


def validate_dataset(dataset: Dataset) -> None:
    """校验完整 Dataset。

    输入:
        dataset: adapter 生成的统一数据集。

    输出:
        None。发现问题时抛 DatasetValidationError。
    """

    if not dataset.dataset_name:
        raise DatasetValidationError("dataset_name is required")
    if not dataset.conversations:
        raise DatasetValidationError("dataset must contain at least one conversation")

    seen_conversation_ids: set[str] = set()
    for conversation in dataset.conversations:
        if conversation.conversation_id in seen_conversation_ids:
            raise DatasetValidationError(
                f"{conversation.conversation_id}: duplicate conversation_id"
            )
        seen_conversation_ids.add(conversation.conversation_id)
        validate_conversation(conversation)


def validate_conversation(conversation: Conversation) -> None:
    """校验单个 Conversation。

    输入:
        conversation: adapter 转换出的单个 conversation。

    输出:
        None。字段缺失或 question/gold 对不齐时抛 DatasetValidationError。
    """

    if not conversation.conversation_id:
        raise DatasetValidationError("conversation_id is required")
    if not conversation.sessions:
        raise DatasetValidationError(f"{conversation.conversation_id}: sessions are required")

    seen_session_ids: set[str] = set()
    for session in conversation.sessions:
        if not session.session_id:
            raise DatasetValidationError(f"{conversation.conversation_id}: session_id is required")
        if session.session_id in seen_session_ids:
            raise DatasetValidationError(
                f"{conversation.conversation_id}/{session.session_id}: duplicate session_id"
            )
        seen_session_ids.add(session.session_id)
        if not session.turns:
            raise DatasetValidationError(
                f"{conversation.conversation_id}/{session.session_id}: turns are required"
            )

        seen_turn_ids: set[str] = set()
        for turn in session.turns:
            if not turn.turn_id:
                raise DatasetValidationError(
                    f"{conversation.conversation_id}/{session.session_id}: turn_id is required"
                )
            if turn.turn_id in seen_turn_ids:
                raise DatasetValidationError(f"{turn.turn_id}: duplicate turn_id")
            seen_turn_ids.add(turn.turn_id)
            if not turn.speaker:
                raise DatasetValidationError(f"{turn.turn_id}: speaker is required")
            if not turn.content and not turn.images:
                raise DatasetValidationError(f"{turn.turn_id}: content or images are required")

    if not conversation.questions:
        raise DatasetValidationError(f"{conversation.conversation_id}: questions are required")

    seen_question_ids: set[str] = set()
    for question in conversation.questions:
        if not question.question_id:
            raise DatasetValidationError(
                f"{conversation.conversation_id}: question_id is required"
            )
        if question.question_id in seen_question_ids:
            raise DatasetValidationError(f"{question.question_id}: duplicate question_id")
        seen_question_ids.add(question.question_id)
        if question.conversation_id != conversation.conversation_id:
            raise DatasetValidationError(
                f"{question.question_id}: question conversation_id does not match parent conversation"
            )
        if not question.text:
            raise DatasetValidationError(f"{question.question_id}: question text is required")
        if question.question_id not in conversation.gold_answers:
            raise DatasetValidationError(f"{question.question_id}: missing GoldAnswerInfo")

        gold = conversation.gold_answers[question.question_id]
        if gold.question_id != question.question_id:
            raise DatasetValidationError(f"{question.question_id}: gold question_id mismatch")
        if not gold.answer:
            raise DatasetValidationError(f"{question.question_id}: gold answer is required")

    for gold_question_id in conversation.gold_answers:
        if gold_question_id not in seen_question_ids:
            raise DatasetValidationError(
                f"{conversation.conversation_id}: gold answer {gold_question_id} has no public question"
            )


def validate_no_private_keys(payload: Any, path: str = "$") -> None:
    """检查公开 payload 中是否出现常见私有标签键。

    输入:
        payload: 即将传给 method 的字典、列表或标量。
        path: 当前递归路径，调用方通常不需要传入。

    输出:
        None。发现 gold answer/evidence 等私有键时抛 DataLeakageError。
    """

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            normalized = key_text.lower()
            if normalized in PRIVATE_KEY_NAMES:
                raise DataLeakageError(f"{path}.{key_text} contains private scoring data")
            validate_no_private_keys(value, f"{path}.{key_text}")
        return

    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, value in enumerate(payload):
            validate_no_private_keys(value, f"{path}[{index}]")

"""实验产物记录结构转换工具。

本模块把核心实体转换为 JSONL 友好的公开问题记录和 evaluator-only 私有标签记录。
"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core import GoldAnswerInfo, Question
from memory_benchmark.core.validators import validate_no_private_keys


def public_question_record(question: Question) -> dict[str, Any]:
    """生成 method 可见的公开问题记录，并阻断私有字段泄漏。"""

    record = {
        "question_id": question.question_id,
        "conversation_id": question.conversation_id,
        "question_text": question.text,
        "question_time": question.question_time,
        "category": question.category,
        "options": question.options,
        "metadata": question.metadata,
    }
    validate_no_private_keys(record)
    return record


def evaluator_private_label_record(
    gold: GoldAnswerInfo, category: str | None = None
) -> dict[str, Any]:
    """生成 evaluator-only 私有标签记录，绝不能传给 method。"""

    return {
        "question_id": gold.question_id,
        "gold_answer": gold.answer,
        "category": category,
        "metadata": gold.metadata,
    }

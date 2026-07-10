"""LongMemEval unified answer prompt builder。

本模块只保存 benchmark-owned 的官方非 CoT answer prompt，不读取 method config，
也不改变 provider 返回的记忆排版。官方来源：
`third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:57`。
"""

from __future__ import annotations

from memory_benchmark.core import AnswerPromptResult, PromptMessage, Question
from memory_benchmark.core.provider_protocol import RetrievalResult


LONGMEMEVAL_OFFICIAL_NON_COT_ANSWER_PROMPT = (
    "I will give you several history chats between you and a user. Please answer "
    "the question based on the relevant chat history.\n\n\nHistory Chats:\n\n{}\n\n"
    "Current Date: {}\nQuestion: {}\nAnswer:"
)

LONGMEMEVAL_UNIFIED_ANSWER_PROMPT_PROFILE = "longmemeval_official_non_cot_rag_v1"

LONGMEMEVAL_UNIFIED_PROMPT_OFFICIAL_SOURCE = (
    "third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:57"
)

LONGMEMEVAL_MISSING_QUESTION_DATE_WARNING = "missing_question_date"


def build_longmemeval_unified_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """按 LongMemEval 官方非 CoT 模板构造 framework reader prompt。

    `formatted_memory` 由 method 负责排版，本函数只原样填入 History Chats 槽位。
    问题日期缺失时按空串处理，并在公开 metadata 中留下 warning 标记。
    """

    question_date = question.question_time or ""
    answer_prompt = LONGMEMEVAL_OFFICIAL_NON_COT_ANSWER_PROMPT.format(
        retrieval_result.formatted_memory,
        question_date,
        question.text,
    )

    metadata = dict(retrieval_result.metadata)
    metadata.update(
        {
            "prompt_track": "unified",
            "answer_prompt_profile": LONGMEMEVAL_UNIFIED_ANSWER_PROMPT_PROFILE,
            "official_source": LONGMEMEVAL_UNIFIED_PROMPT_OFFICIAL_SOURCE,
            "answer_context": retrieval_result.formatted_memory,
        }
    )
    if question.question_time is None:
        metadata["question_date_warning"] = LONGMEMEVAL_MISSING_QUESTION_DATE_WARNING

    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        answer_prompt=answer_prompt,
        prompt_messages=[PromptMessage(role="user", content=answer_prompt)],
        metadata=metadata,
    )


__all__ = [
    "LONGMEMEVAL_MISSING_QUESTION_DATE_WARNING",
    "LONGMEMEVAL_OFFICIAL_NON_COT_ANSWER_PROMPT",
    "LONGMEMEVAL_UNIFIED_ANSWER_PROMPT_PROFILE",
    "LONGMEMEVAL_UNIFIED_PROMPT_OFFICIAL_SOURCE",
    "build_longmemeval_unified_answer_prompt",
]

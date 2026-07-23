"""MemBench benchmark 所有的统一选择题答题 prompt。"""

from __future__ import annotations

from memory_benchmark.core import AnswerPromptResult, PromptMessage, Question
from memory_benchmark.core.exceptions import DatasetValidationError
from memory_benchmark.core.provider_protocol import RetrievalResult

MEMBENCH_INSTRUCTION_FIRST_PROFILE = "membench_instruction_first_v1"
MEMBENCH_INSTRUCTION_FIRST = """Please answer the following question based on past memories of your'conversation with the user.
Past memory: {memory}
Question: (current time is {time}) {question}
Choices:
A. {choice_A}
B. {choice_B}
C. {choice_C}
D. {choice_D}
Please output the correct option for the question, only one corresponding letter, without any other messages.
Example: D
"""
MEMBENCH_UNIFIED_PROMPT_OFFICIAL_SOURCE = (
    "third_party/benchmarks/Membench-main/benchmark/"
    "MembenchAgent.py:21-31,89-92,93-112"
)


def build_membench_unified_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """按官方 INSTRUCTION_FIRST 构造完整 framework reader prompt。"""

    choices = question.options or {}
    missing_choices = [
        choice for choice in ("A", "B", "C", "D") if choice not in choices
    ]
    if missing_choices:
        raise DatasetValidationError(
            f"MemBench question choices missing {missing_choices}: {question.question_id}"
        )
    answer_prompt = MEMBENCH_INSTRUCTION_FIRST.format(
        memory=retrieval_result.formatted_memory,
        question=question.text,
        time=question.question_time or "",
        choice_A=choices["A"],
        choice_B=choices["B"],
        choice_C=choices["C"],
        choice_D=choices["D"],
    )
    metadata = dict(retrieval_result.metadata)
    metadata.update(
        {
            "answer_prompt_profile": MEMBENCH_INSTRUCTION_FIRST_PROFILE,
            "prompt_track": "unified",
            "answer_context": retrieval_result.formatted_memory,
            "official_source": MEMBENCH_UNIFIED_PROMPT_OFFICIAL_SOURCE,
        }
    )
    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        answer_prompt=answer_prompt,
        prompt_messages=[PromptMessage(role="user", content=answer_prompt)],
        metadata=metadata,
    )


__all__ = [
    "MEMBENCH_INSTRUCTION_FIRST",
    "MEMBENCH_INSTRUCTION_FIRST_PROFILE",
    "MEMBENCH_UNIFIED_PROMPT_OFFICIAL_SOURCE",
    "build_membench_unified_answer_prompt",
]

"""HaluMem benchmark 所有的统一答题 prompt。"""

from __future__ import annotations

from memory_benchmark.core import AnswerPromptResult, PromptMessage, Question
from memory_benchmark.core.provider_protocol import RetrievalResult

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


def build_halumem_unified_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """按官方 PROMPT_MEMZERO 构造完整 framework reader prompt。"""

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


__all__ = [
    "HALUMEM_MEMZERO_OFFICIAL_SOURCE",
    "HALUMEM_MEMZERO_PROMPT",
    "HALUMEM_MEMZERO_PROMPT_PROFILE",
    "build_halumem_unified_answer_prompt",
]

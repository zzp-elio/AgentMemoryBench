"""LightMem paper-native answer/judge 配置资产。

本模块只注册从 vendored LightMem 官方实验逐字抽取的离线 profile；运行时
config-track 选择由后续批次实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from memory_benchmark.core import AnswerPromptResult, ConfigurationError, PromptMessage, Question
from memory_benchmark.core.provider_protocol import RetrievalResult


LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROMPT = '''
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

Memories for user {speaker_1_name}:

{speaker_1_memories}

Memories for user {speaker_2_name}:

{speaker_2_memories}

Question: {question}

Answer:
'''

LIGHTMEM_LONGMEMEVAL_NATIVE_SYSTEM_PROMPT = "You are a helpful assistant."
LIGHTMEM_LONGMEMEVAL_NATIVE_USER_PROMPT = (
    "Question time:{question_date} and question:{question}\n"
    "Please answer the question based on the following memories: {formatted_memory}"
)

LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROFILE = "lightmem_locomo_paper_native_v1"
LIGHTMEM_LONGMEMEVAL_NATIVE_ANSWER_PROFILE = "lightmem_longmemeval_paper_native_v1"


@dataclass(frozen=True)
class LightMemNativeAnswerSettings:
    """LightMem `LLMModel` 的 paper-native answer 调用参数。"""

    temperature: float
    max_tokens: int
    top_p: float


@dataclass(frozen=True)
class LightMemNativeAnswerProfile:
    """一个 benchmark 的 LightMem native answer 静态 profile。"""

    profile_name: str
    builder: Callable[[Question, RetrievalResult], AnswerPromptResult]
    settings: LightMemNativeAnswerSettings
    official_source: str


LIGHTMEM_NATIVE_ANSWER_SETTINGS = LightMemNativeAnswerSettings(
    temperature=0.0,
    max_tokens=2000,
    top_p=0.8,
)


def build_lightmem_locomo_native_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """复用 LightMem adapter 已按官方 speaker 分组生成的 LoCoMo system prompt。"""

    messages = retrieval_result.prompt_messages
    if (
        messages is None
        or len(messages) != 1
        or messages[0].role != "system"
        or not messages[0].content.strip()
    ):
        raise ConfigurationError(
            "LightMem LoCoMo native answer requires one adapter-produced system prompt"
        )
    prompt_messages = list(messages)
    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        answer_prompt=messages[0].content,
        prompt_messages=prompt_messages,
        metadata={
            **retrieval_result.metadata,
            "prompt_track": "native",
            "answer_prompt_profile": LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROFILE,
            "official_source": (
                "third_party/methods/LightMem/experiments/locomo/"
                "prompts.py:148-190; search_locomo.py:258-280"
            ),
            "answer_context": retrieval_result.formatted_memory,
        },
    )


def build_lightmem_longmemeval_native_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """按 LightMem LongMemEval 官方 system/user 两段逐字构造 native prompt。"""

    user_prompt = LIGHTMEM_LONGMEMEVAL_NATIVE_USER_PROMPT.format(
        question_date=question.question_time,
        question=question.text,
        formatted_memory=retrieval_result.formatted_memory,
    )
    messages = [
        PromptMessage(role="system", content=LIGHTMEM_LONGMEMEVAL_NATIVE_SYSTEM_PROMPT),
        PromptMessage(role="user", content=user_prompt),
    ]
    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        prompt_messages=messages,
        metadata={
            **retrieval_result.metadata,
            "prompt_track": "native",
            "answer_prompt_profile": LIGHTMEM_LONGMEMEVAL_NATIVE_ANSWER_PROFILE,
            "official_source": (
                "third_party/methods/LightMem/experiments/longmemeval/"
                "run_lightmem_gpt.py:182-188"
            ),
            "answer_context": retrieval_result.formatted_memory,
        },
    )


LIGHTMEM_NATIVE_ANSWER_PROFILES = {
    "locomo": LightMemNativeAnswerProfile(
        profile_name=LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROFILE,
        builder=build_lightmem_locomo_native_answer_prompt,
        settings=LIGHTMEM_NATIVE_ANSWER_SETTINGS,
        official_source=(
            "third_party/methods/LightMem/experiments/locomo/"
            "prompts.py:148-190; search_locomo.py:258-280"
        ),
    ),
    "longmemeval": LightMemNativeAnswerProfile(
        profile_name=LIGHTMEM_LONGMEMEVAL_NATIVE_ANSWER_PROFILE,
        builder=build_lightmem_longmemeval_native_answer_prompt,
        settings=LIGHTMEM_NATIVE_ANSWER_SETTINGS,
        official_source=(
            "third_party/methods/LightMem/experiments/longmemeval/"
            "run_lightmem_gpt.py:51-80,182-188"
        ),
    ),
}


__all__ = [
    "LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROFILE",
    "LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROMPT",
    "LIGHTMEM_LONGMEMEVAL_NATIVE_ANSWER_PROFILE",
    "LIGHTMEM_LONGMEMEVAL_NATIVE_SYSTEM_PROMPT",
    "LIGHTMEM_LONGMEMEVAL_NATIVE_USER_PROMPT",
    "LIGHTMEM_NATIVE_ANSWER_PROFILES",
    "LIGHTMEM_NATIVE_ANSWER_SETTINGS",
    "LightMemNativeAnswerProfile",
    "LightMemNativeAnswerSettings",
    "build_lightmem_locomo_native_answer_prompt",
    "build_lightmem_longmemeval_native_answer_prompt",
]

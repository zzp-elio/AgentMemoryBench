"""LightMem paper-native answer/judge 配置资产。

本模块只注册从 vendored LightMem 官方实验逐字抽取的离线 profile；运行时
config-track 选择由后续批次实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from memory_benchmark.core import AnswerPromptResult, ConfigurationError, PromptMessage, Question
from memory_benchmark.core.provider_protocol import RetrievalResult
from memory_benchmark.evaluators.longmemeval_judge import LongMemEvalJudgeEvaluator


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

LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT = '''
Your task is to label an answer to a question as ’CORRECT’ or ’WRONG’. You will be given the following data:
    (1) a question (posed by one user to another user), 
    (2) a ’gold’ (ground truth) answer, 
    (3) a generated answer
which you will score as CORRECT/WRONG.

The point of the question is to ask about something one user should know about the other user based on their prior conversations.
The gold answer will usually be a concise and short answer that includes the referenced topic, for example:
Question: Do you remember what I got the last time I went to Hawaii?
Gold answer: A shell necklace
The generated answer might be much longer, but you should be generous with your grading - as long as it touches on the same topic as the gold answer, it should be counted as CORRECT. 

For time related questions, the gold answer will be a specific date, month, year, etc. The generated answer might be much longer or use relative time references (like "last Tuesday" or "next month"), but you should be generous with your grading - as long as it refers to the same date or time period as the gold answer, it should be counted as CORRECT. Even if the format differs (e.g., "May 7th" vs "7 May"), consider it CORRECT if it's the same date.

Now it's time for the real question:
Question: {question}
Gold answer: {gold_answer}
Generated answer: {generated_answer}

First, provide a short (one sentence) explanation of your reasoning, then finish with CORRECT or WRONG. 
Do NOT include both CORRECT and WRONG in your response, or it will break the evaluation script.

Just return the label CORRECT or WRONG in a json format with the key as "label".
'''

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


@dataclass(frozen=True)
class LightMemNativeJudgeProfile:
    """一个 benchmark 的 LightMem native judge 静态 profile。"""

    profile_name: str
    prompt_template: str | None
    evaluator_type: type | None
    temperature: float
    max_tokens: int | None
    n: int | None
    response_format: dict[str, str] | None
    skipped_categories: frozenset[str]
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

LIGHTMEM_NATIVE_JUDGE_PROFILES = {
    "locomo": LightMemNativeJudgeProfile(
        profile_name="lightmem_locomo_paper_native_judge_v1",
        prompt_template=LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT,
        evaluator_type=None,
        temperature=0.0,
        max_tokens=None,
        n=None,
        response_format={"type": "json_object"},
        skipped_categories=frozenset({"5"}),
        official_source=(
            "third_party/methods/LightMem/experiments/locomo/"
            "llm_judge.py:22-46,60-74,106-108"
        ),
    ),
    "longmemeval": LightMemNativeJudgeProfile(
        profile_name="longmemeval_official_evaluate_qa_v1",
        prompt_template=None,
        evaluator_type=LongMemEvalJudgeEvaluator,
        temperature=0.0,
        max_tokens=10,
        n=1,
        response_format=None,
        skipped_categories=frozenset(),
        official_source=(
            "third_party/methods/LightMem/experiments/longmemeval/"
            "run_lightmem_gpt.py:8-28; reused framework official parity evaluator"
        ),
    ),
}


def lightmem_locomo_native_judge_skips_category(category: str | int | None) -> bool:
    """按官方 `int(category) == 5` 判断 LoCoMo native judge 是否跳过。"""

    if category is None:
        return False
    try:
        return int(category) == 5
    except (TypeError, ValueError):
        return False


__all__ = [
    "LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROFILE",
    "LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROMPT",
    "LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT",
    "LIGHTMEM_LONGMEMEVAL_NATIVE_ANSWER_PROFILE",
    "LIGHTMEM_LONGMEMEVAL_NATIVE_SYSTEM_PROMPT",
    "LIGHTMEM_LONGMEMEVAL_NATIVE_USER_PROMPT",
    "LIGHTMEM_NATIVE_ANSWER_PROFILES",
    "LIGHTMEM_NATIVE_ANSWER_SETTINGS",
    "LIGHTMEM_NATIVE_JUDGE_PROFILES",
    "LightMemNativeAnswerProfile",
    "LightMemNativeAnswerSettings",
    "LightMemNativeJudgeProfile",
    "build_lightmem_locomo_native_answer_prompt",
    "build_lightmem_longmemeval_native_answer_prompt",
    "lightmem_locomo_native_judge_skips_category",
]

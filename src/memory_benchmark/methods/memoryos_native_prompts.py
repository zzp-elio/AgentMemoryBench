"""MemoryOS LoCoMo readout-native answer 配置资产。"""

from __future__ import annotations

from dataclasses import dataclass

from memory_benchmark.config.settings import AnswerLLMSettings
from memory_benchmark.core import PromptMessage


MEMORYOS_LOCOMO_NATIVE_SYSTEM_PROMPT = (
    "You are role-playing as {speaker_b} in a conversation with the user is playing is  {speaker_a}. "
    "Here are some of your character traits and knowledge:\n{assistant_knowledge}\n"
    "Any content referring to 'User' in the prompt refers to {speaker_a}'s content, and any content referring to 'AI'or 'assiant' refers to {speaker_b}'s content."
    "Your task is to answer questions about {speaker_a} or {speaker_b} in an extremely concise manner.\n"
    'When the question is: "What did the charity race raise awareness for?", you should not answer in the form of: "The charity race raised awareness for mental health." Instead, it should be: "mental health", as this is more concise.'
)

MEMORYOS_LOCOMO_NATIVE_USER_PROMPT = (
    "<CONTEXT>\n"
    "Recent conversation between {speaker_a} and {speaker_b}:\n"
    "{history_text}\n\n"
    "<MEMORY>\n"
    "Relevant past conversations:\n"
    "{retrieval_text}\n\n"
    "<CHARACTER TRAITS>\n"
    "Characteristics of {speaker_a}:\n"
    "{background}\n\n"
    "the question is: {question}\n"
    "Your task is to answer questions about {speaker_a} or {speaker_b} in an extremely concise manner.\n"
    "Please only provide the content of the answer, without including 'answer:'\n"
    'For questions that require answering a date or time, strictly follow the format "15 July 2023" and provide a specific date whenever possible. For example, if you need to answer "last year," give the specific year of last year rather than just saying "last year." Only provide one year, date, or time, without any extra responses.\n'
    "If the question is about the duration, answer in the form of several years, months, or days.\n"
    "Generate answers primarily composed of concrete entities, such as Mentoring program, school speech, etc"
)

MEMORYOS_NATIVE_ANSWER_SETTINGS = AnswerLLMSettings(
    model="gpt-4o-mini",
    message_role="user",
    temperature=0.7,
    max_tokens=2000,
    top_p=None,
)

# Readout-native 当前不消费 build override；逐参资产供后续框架级 native-build 卡使用。
MEMORYOS_NATIVE_LOCOMO_HYPERPARAMETERS = {
    "short_term_capacity": 7,
    "mid_term_capacity": 2000,  # DISPUTED: paper 的 200 是段长还是段数不明确。
    "retrieval_queue_capacity": 10,
    "heat_alpha": 1.0,
    "heat_beta": 1.0,
    "heat_gamma": 1.0,
    "mid_term_heat_threshold": 5.0,
    "mid_term_similarity_threshold": 0.6,
    "top_k_sessions": 5,
    "segment_similarity_threshold": 0.1,  # DISPUTED: paper 未给，取 eval 实配。
    "page_similarity_threshold": 0.1,  # DISPUTED: paper 未给，取 eval 实配。
    "knowledge_threshold": 0.1,  # DISPUTED: paper 未给，取 eval 实配。
}


@dataclass(frozen=True)
class MemoryOSNativeAnswerProfile:
    """MemoryOS 单个 benchmark 的官方 answer readout profile。"""

    profile_name: str
    settings: AnswerLLMSettings
    official_source: str


def build_memoryos_locomo_native_answer_prompt(
    *,
    query_text: str,
    speaker_a: str,
    speaker_b: str,
    history_text: str,
    retrieval_text: str,
    background: str,
    assistant_knowledge: str,
) -> tuple[PromptMessage, ...]:
    """按官方 eval 的角色扮演模板构造 LoCoMo answer messages。"""

    return (
        PromptMessage(
            role="system",
            content=MEMORYOS_LOCOMO_NATIVE_SYSTEM_PROMPT.format(
                speaker_a=speaker_a,
                speaker_b=speaker_b,
                assistant_knowledge=assistant_knowledge,
            ),
        ),
        PromptMessage(
            role="user",
            content=MEMORYOS_LOCOMO_NATIVE_USER_PROMPT.format(
                speaker_a=speaker_a,
                speaker_b=speaker_b,
                history_text=history_text,
                retrieval_text=retrieval_text,
                background=background,
                question=query_text,
            ),
        ),
    )


MEMORYOS_NATIVE_ANSWER_PROFILES = {
    "locomo": MemoryOSNativeAnswerProfile(
        profile_name="memoryos_locomo_eval_readout_native_v1",
        settings=MEMORYOS_NATIVE_ANSWER_SETTINGS,
        official_source=(
            "third_party/methods/MemoryOS-main/eval/main_loco_parse.py:83-157"
        ),
    )
}


__all__ = [
    "MEMORYOS_LOCOMO_NATIVE_SYSTEM_PROMPT",
    "MEMORYOS_LOCOMO_NATIVE_USER_PROMPT",
    "MEMORYOS_NATIVE_ANSWER_PROFILES",
    "MEMORYOS_NATIVE_LOCOMO_HYPERPARAMETERS",
    "MemoryOSNativeAnswerProfile",
    "build_memoryos_locomo_native_answer_prompt",
]

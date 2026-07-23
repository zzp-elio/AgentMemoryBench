"""LoCoMo benchmark-owned unified answer prompt builder。

本模块只放 benchmark-owned 的官方 QA prompt 与来源常量，不读取 method
config、不引入任何 method 专属逻辑。官方来源：
`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:25-29,243-244`
（问题 prompt 与 category 2 日期提示）。
"""

from __future__ import annotations

from memory_benchmark.core import AnswerPromptResult, PromptMessage, Question
from memory_benchmark.core.provider_protocol import RetrievalResult

# 官方 short-phrase QA prompt，逐字保留自
# `third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:25-29`。
LOCOMO_OFFICIAL_QA_PROMPT = (
    "\nBased on the above context, write an answer in the form of a short "
    "phrase for the following question. Answer with exact words from the "
    "context whenever possible.\n\nQuestion: {question} Short answer:\n"
)

# 官方 category 2（temporal）日期提示后缀，逐字保留自
# `third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:243-244`。
LOCOMO_CATEGORY_2_DATE_SUFFIX = (
    " Use DATE of CONVERSATION to answer with an approximate date."
)

LOCOMO_TEMPORAL_CATEGORY = "2"

LOCOMO_UNIFIED_ANSWER_PROMPT_PROFILE = "locomo_official_qa_rag_v1"

LOCOMO_UNIFIED_PROMPT_OFFICIAL_SOURCE = (
    "third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:25-29,243-244"
)

# LightMem 官方 llm_judge.py 的 ACCURACY_PROMPT。LoCoMo 官方 QA 仓库没有
# LLM-as-judge；本模板属于 framework auxiliary benchmark judge 资产。
LOCOMO_JUDGE_PROMPT = """\
Your task is to label an answer to a question as \u2018CORRECT\u2019 or \u2018WRONG\u2019. You will be given the following data:
    (1) a question (posed by one user to another user),
    (2) a \u2018gold\u2019 (ground truth) answer,
    (3) a generated answer
which you will score as CORRECT/WRONG.

The point of the question is to ask about something one user should know about the other user based on their prior conversations.
The gold answer will usually be a concise and short answer that includes the referenced topic, for example:
Question: Do you remember what I got the last time I went to Hawaii?
Gold answer: A shell necklace
The generated answer might be much longer, but you should be generous with your grading - as long as it touches on the same topic as the gold answer, it should be counted as CORRECT.

For time related questions, the gold answer will be a specific date, month, year, etc. The generated answer might be much longer or use relative time references (like "last Tuesday" or "next month"), but you should be generous with your grading - as long as it refers to the same date or time period as the gold answer, it should be counted as CORRECT. Even if the format differs (e.g., "May 7th" vs "7 May"), consider it CORRECT if it\u2019s the same date.

Now it\u2019s time for the real question:
Question: {question}
Gold answer: {gold_answer}
Generated answer: {generated_answer}
"""


def build_locomo_unified_answer_prompt(
    question: Question,
    retrieval_result: RetrievalResult,
) -> AnswerPromptResult:
    """按 LoCoMo 官方 short-phrase QA prompt 构造 framework reader prompt。

    输入:
        question: 公开问题，只使用 `text`/`category`，不读取 gold/evidence。
        retrieval_result: provider 检索结果，只使用 `formatted_memory`。

    输出:
        AnswerPromptResult: 单条 `user` role 的完整 prompt，metadata 标注
        `prompt_track`/`answer_prompt_profile`/官方来源与 `answer_context`。
    """

    question_text = question.text
    if question.category == LOCOMO_TEMPORAL_CATEGORY:
        question_text = f"{question_text}{LOCOMO_CATEGORY_2_DATE_SUFFIX}"

    answer_prompt = (
        f"{retrieval_result.formatted_memory}\n\n"
        f"{LOCOMO_OFFICIAL_QA_PROMPT.format(question=question_text)}"
    )

    metadata = dict(retrieval_result.metadata)
    metadata.update(
        {
            "prompt_track": "unified",
            "answer_prompt_profile": LOCOMO_UNIFIED_ANSWER_PROMPT_PROFILE,
            "official_source": LOCOMO_UNIFIED_PROMPT_OFFICIAL_SOURCE,
            "answer_context": retrieval_result.formatted_memory,
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
    "LOCOMO_CATEGORY_2_DATE_SUFFIX",
    "LOCOMO_JUDGE_PROMPT",
    "LOCOMO_OFFICIAL_QA_PROMPT",
    "LOCOMO_TEMPORAL_CATEGORY",
    "LOCOMO_UNIFIED_ANSWER_PROMPT_PROFILE",
    "LOCOMO_UNIFIED_PROMPT_OFFICIAL_SOURCE",
    "build_locomo_unified_answer_prompt",
]

"""LongMemEval benchmark-owned unified answer prompt builder。

本模块只保存 benchmark-owned 的官方非 CoT answer prompt，不读取 method config，
也不改变 provider 返回的记忆排版。官方来源：
`third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:57`。
"""

from __future__ import annotations

from memory_benchmark.core import AnswerPromptResult, PromptMessage, Question
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import RetrievalResult


LONGMEMEVAL_COMMON_QA_TASKS = frozenset(
    {"single-session-user", "single-session-assistant", "multi-session"}
)

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


def build_longmemeval_official_judge_prompt(
    *,
    task: str,
    question: str,
    answer: str,
    response: str,
    abstention: bool,
) -> str:
    """逐字构造 LongMemEval 官方 task-specific judge prompt。"""

    if abstention:
        template = (
            "I will give you an unanswerable question, an explanation, and a response "
            "from a model. Please answer yes if the model correctly identifies the question "
            "as unanswerable. The model could say that the information is incomplete, or "
            "some other information is given but the asked information is not.\n\nQuestion: "
            "{}\n\nExplanation: {}\n\nModel Response: {}\n\nDoes the model correctly "
            "identify the question as unanswerable? Answer yes or no only."
        )
        return template.format(question, answer, response)

    if task in LONGMEMEVAL_COMMON_QA_TASKS:
        template = (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, "
            "answer no. If the response is equivalent to the correct answer or contains "
            "all the intermediate steps to get the correct answer, you should also "
            "answer yes. If the response only contains a subset of the information "
            "required by the answer, answer no. \n\nQuestion: {}\n\nCorrect Answer: "
            "{}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
        )
    elif task == "temporal-reasoning":
        template = (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, "
            "answer no. If the response is equivalent to the correct answer or contains "
            "all the intermediate steps to get the correct answer, you should also "
            "answer yes. If the response only contains a subset of the information "
            "required by the answer, answer no. In addition, do not penalize off-by-one "
            "errors for the number of days. If the question asks for the number of "
            "days/weeks/months, etc., and the model makes off-by-one errors (e.g., "
            "predicting 19 days when the answer is 18), the model's response is still "
            "correct. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: "
            "{}\n\nIs the model response correct? Answer yes or no only."
        )
    elif task == "knowledge-update":
        template = (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, "
            "answer no. If the response contains some previous information along with "
            "an updated answer, the response should be considered as correct as long "
            "as the updated answer is the required answer.\n\nQuestion: {}\n\nCorrect "
            "Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
        )
    elif task == "single-session-preference":
        template = (
            "I will give you a question, a rubric for desired personalized response, "
            "and a response from a model. Please answer yes if the response satisfies "
            "the desired response. Otherwise, answer no. The model does not need to "
            "reflect all the points in the rubric. The response is correct as long as "
            "it recalls and utilizes the user's personal information correctly.\n\n"
            "Question: {}\n\nRubric: {}\n\nModel Response: {}\n\nIs the model "
            "response correct? Answer yes or no only."
        )
    else:
        raise ConfigurationError(f"Unsupported LongMemEval judge task: {task}")

    return template.format(question, answer, response)


__all__ = [
    "LONGMEMEVAL_COMMON_QA_TASKS",
    "LONGMEMEVAL_MISSING_QUESTION_DATE_WARNING",
    "LONGMEMEVAL_OFFICIAL_NON_COT_ANSWER_PROMPT",
    "LONGMEMEVAL_UNIFIED_ANSWER_PROMPT_PROFILE",
    "LONGMEMEVAL_UNIFIED_PROMPT_OFFICIAL_SOURCE",
    "build_longmemeval_official_judge_prompt",
    "build_longmemeval_unified_answer_prompt",
]

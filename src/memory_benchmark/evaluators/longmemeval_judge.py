"""LongMemEval benchmark 专用 LLM judge 外壳。"""

from __future__ import annotations

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, Question
from memory_benchmark.core.exceptions import ConfigurationError

from .llm_judge import LLMJudgeEvaluator


_COMMON_QA_TASKS = frozenset(
    {"single-session-user", "single-session-assistant", "multi-session"}
)


class LongMemEvalJudgeEvaluator(LLMJudgeEvaluator):
    """LongMemEval QA answer-level judge。

    该类封装 LongMemEval 官方 `evaluate_qa.py` 的 task-specific 判分规则和 metric 名称。
    真实模型调用由父类懒加载；输出格式仍遵守本项目 compact/detailed parser。
    """

    metric_name = "longmemeval_judge_accuracy"
    benchmark_name = "LongMemEval"

    def build_prompt(
        self,
        question: Question | str,
        prediction: AnswerResult | str,
        gold_answer: GoldAnswerInfo | str,
    ) -> str:
        """构造 LongMemEval judge prompt。

        输入:
            question: 公开问题对象或文本。
            prediction: method 预测答案对象或文本。
            gold_answer: evaluator 私有标准答案对象或文本。

        输出:
            str: 简洁的 LongMemEval 判分 prompt。
        """

        question_text, prediction_text, gold_text = self._extract_text_fields(
            question,
            prediction,
            gold_answer,
        )
        task = _extract_task_type(question)
        body = _build_official_longmemeval_judge_body(
            task=task,
            question=question_text,
            answer=gold_text,
            response=prediction_text,
            abstention=_is_abstention_question(question),
        )
        return (
            f"{body}\n\n"
            "Follow the LongMemEval rule above, but use the framework output format below.\n"
            "If the official yes/no decision is yes, output true. "
            "If the official yes/no decision is no, output false.\n"
            f"{self._output_instruction()}"
        )


def _extract_task_type(question: Question | str) -> str:
    """从公开问题中提取 LongMemEval question_type。

    输入:
        question: 统一 Question 或纯文本。真实 LongMemEval adapter 会把 `question_type`
            放到 `Question.category`。

    输出:
        str: 官方 judge prompt 使用的 task 名。缺省时回退 common QA，兼容旧测试。
    """

    if isinstance(question, Question):
        if question.category:
            return question.category
        metadata_task = question.metadata.get("question_type")
        if isinstance(metadata_task, str) and metadata_task.strip():
            return metadata_task.strip()
    return "single-session-user"


def _is_abstention_question(question: Question | str) -> bool:
    """LongMemEval 官方用 question_id 中 `_abs` 判断不可回答题。"""

    return isinstance(question, Question) and "_abs" in question.question_id


def _build_official_longmemeval_judge_body(
    *,
    task: str,
    question: str,
    answer: str,
    response: str,
    abstention: bool,
) -> str:
    """构造 LongMemEval 官方 task-specific 判分规则主体。

    该函数从官方 `evaluate_qa.py:get_anscheck_prompt()` 迁移规则文本，但去掉最后
    `Answer yes or no only` 的硬输出要求，由 `LongMemEvalJudgeEvaluator` 统一映射到
    本项目 parser 所需的 true/false 或 JSON。
    """

    if abstention:
        template = (
            "I will give you an unanswerable question, an explanation, and a response "
            "from a model. Please answer yes if the model correctly identifies the "
            "question as unanswerable. The model could say that the information is "
            "incomplete, or some other information is given but the asked information "
            "is not.\n\nQuestion: {question}\n\nExplanation: {answer}\n\n"
            "Model Response: {response}\n\nDoes the model correctly identify the "
            "question as unanswerable?"
        )
        return template.format(question=question, answer=answer, response=response)

    if task in _COMMON_QA_TASKS:
        template = (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, "
            "answer no. If the response is equivalent to the correct answer or contains "
            "all the intermediate steps to get the correct answer, you should also "
            "answer yes. If the response only contains a subset of the information "
            "required by the answer, answer no.\n\nQuestion: {question}\n\n"
            "Correct Answer: {answer}\n\nModel Response: {response}\n\n"
            "Is the model response correct?"
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
            "correct.\n\nQuestion: {question}\n\nCorrect Answer: {answer}\n\n"
            "Model Response: {response}\n\nIs the model response correct?"
        )
    elif task == "knowledge-update":
        template = (
            "I will give you a question, a correct answer, and a response from a model. "
            "Please answer yes if the response contains the correct answer. Otherwise, "
            "answer no. If the response contains some previous information along with "
            "an updated answer, the response should be considered as correct as long "
            "as the updated answer is the required answer.\n\nQuestion: {question}\n\n"
            "Correct Answer: {answer}\n\nModel Response: {response}\n\n"
            "Is the model response correct?"
        )
    elif task == "single-session-preference":
        template = (
            "I will give you a question, a rubric for desired personalized response, "
            "and a response from a model. Please answer yes if the response satisfies "
            "the desired response. Otherwise, answer no. The model does not need to "
            "reflect all the points in the rubric. The response is correct as long as "
            "it recalls and utilizes the user's personal information correctly.\n\n"
            "Question: {question}\n\nRubric: {answer}\n\n"
            "Model Response: {response}\n\nIs the model response correct?"
        )
    else:
        raise ConfigurationError(f"Unsupported LongMemEval judge task: {task}")

    return template.format(question=question, answer=answer, response=response)

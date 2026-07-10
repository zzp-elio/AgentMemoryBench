"""LongMemEval benchmark 专用 LLM judge 外壳。"""

from __future__ import annotations

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, MetricResult, Question
from memory_benchmark.core.exceptions import ConfigurationError, JudgeOutputError
from memory_benchmark.observability.efficiency import resolve_token_usage

from .llm_judge import (
    JudgeModelResponse,
    LLMJudgeEvaluator,
    _TiktokenCounter,
    _extract_usage_tokens,
)


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

    def evaluate(
        self,
        question: Question,
        prediction: AnswerResult | str,
        gold_answer: GoldAnswerInfo | str,
    ) -> MetricResult:
        """调用 LongMemEval judge 并返回单题 metric。

        prompt、调用参数和 label 解析均逐项对齐官方 `evaluate_qa.py`。
        """

        prompt = self.build_prompt(question, prediction, gold_answer)
        model_response = self._call_model_with_usage(prompt)
        self._record_judge_llm_call(model_response)
        is_correct = _parse_official_yes_no(model_response.text)
        return MetricResult(
            metric_name=self.metric_name,
            score=1.0 if is_correct else 0.0,
            is_correct=is_correct,
            details={
                "reason": "",
                "raw_judge_response": model_response.text,
                "prompt_profile": "longmemeval_official_evaluate_qa_v1",
            },
        )

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
            str: 与官方 `get_anscheck_prompt()` 逐字一致的判分 prompt。
        """

        question_text, prediction_text, gold_text = self._extract_text_fields(
            question,
            prediction,
            gold_answer,
        )
        task = _extract_task_type(question)
        return _build_official_longmemeval_judge_prompt(
            task=task,
            question=question_text,
            answer=gold_text,
            response=prediction_text,
            abstention=_is_abstention_question(question),
        )

    def _call_model_with_usage(self, prompt: str) -> JudgeModelResponse:
        """按官方 `evaluate_qa.py:102-110` 使用 Chat Completions 参数。"""

        client = self._get_client()
        model = self.model or self._get_settings().openai.model
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            n=1,
            temperature=0,
            max_tokens=10,
        )
        text = response.choices[0].message.content
        if not isinstance(text, str) or not text.strip():
            raise JudgeOutputError("model response is empty")
        input_tokens, output_tokens = _extract_usage_tokens(response)
        usage = resolve_token_usage(
            api_input_tokens=input_tokens,
            api_output_tokens=output_tokens,
            prompt_text=prompt,
            output_text=text,
            tokenizer=_TiktokenCounter(model),
        )
        return JudgeModelResponse(
            text=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_measurement_source=usage.source,
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


def _parse_official_yes_no(response: str) -> bool:
    """按官方 `evaluate_qa.py:113` 的 `'yes' in response.lower()` 解析。"""

    return "yes" in str(response).lower()


def _build_official_longmemeval_judge_prompt(
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

    if task in _COMMON_QA_TASKS:
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

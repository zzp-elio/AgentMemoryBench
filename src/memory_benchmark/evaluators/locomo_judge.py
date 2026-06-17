"""LoCoMo benchmark 专用 LLM judge 外壳。"""

from __future__ import annotations

from memory_benchmark.core import AnswerResult, GoldAnswerInfo, Question

from .llm_judge import LLMJudgeEvaluator


class LoCoMoJudgeEvaluator(LLMJudgeEvaluator):
    """LoCoMo QA answer-level judge。

    该类只封装 LoCoMo 的判分提示词和 metric 名称，真实模型调用由父类懒加载。
    """

    metric_name = "locomo_judge_accuracy"
    benchmark_name = "LoCoMo"

    def build_prompt(
        self,
        question: Question | str,
        prediction: AnswerResult | str,
        gold_answer: GoldAnswerInfo | str,
    ) -> str:
        """构造 LoCoMo judge prompt。

        输入:
            question: 公开问题对象或文本。
            prediction: method 预测答案对象或文本。
            gold_answer: evaluator 私有标准答案对象或文本。

        输出:
            str: 简洁的 LoCoMo 判分 prompt。
        """

        question_text, prediction_text, gold_text = self._extract_text_fields(
            question,
            prediction,
            gold_answer,
        )
        return (
            "You are judging LoCoMo conversation-memory QA.\n"
            "Decide whether the prediction answers the question consistently with the gold answer.\n"
            "Allow paraphrases and harmless extra details. Mark false for contradictions, omissions, or unsupported answers.\n"
            f"{self._output_instruction()}\n"
            f"Question: {question_text}\n"
            f"Prediction: {prediction_text}\n"
            f"Gold answer: {gold_text}\n"
        )

"""LoCoMo benchmark 专用 LLM judge 外壳。

使用 LightMem 官方 llm_judge.py 的 ACCURACY_PROMPT、`chat.completions.create` 和
`response_format={"type": "json_object"}` 逻辑。
compact 模式下解析 JSON `{"label": "CORRECT"}`。
"""

from __future__ import annotations

import json
from typing import Any

from memory_benchmark.config import load_settings
from memory_benchmark.core import AnswerResult, GoldAnswerInfo, MetricResult, Question
from memory_benchmark.core.exceptions import ConfigurationError, JudgeOutputError
from memory_benchmark.observability.efficiency import resolve_token_usage

from .llm_judge import (
    JudgeModelResponse,
    LLMJudgeEvaluator,
    _extract_usage_tokens,
    _get_first_int,
    _get_mapping_or_attr,
    parse_judge_response,
)

# LightMem 官方 llm_judge.py 的 ACCURACY_PROMPT。
# compact 模式下输出 JSON {"label": "CORRECT"}，
# 详细模式走项目统一 JSON {"is_correct": ..., "reason": ...}。
_LOC0MO_JUDGE_PROMPT = """\
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


class LoCoMoJudgeEvaluator(LLMJudgeEvaluator):
    """LoCoMo QA answer-level judge。

    使用 LightMem 官方的 ACCURACY_PROMPT 模板。默认裁判模型为 gpt-4o-mini。
    """

    metric_name = "locomo_judge_accuracy"
    benchmark_name = "LoCoMo"
    # LoCoMo 官方 QA 仓库没有 LLM-as-judge；本 judge 只是参考 LightMem 官方
    # LoCoMo 评测 prompt 的框架辅助指标，不是官方主指标（见 plan Task 6.4）。
    metric_tier = "framework_auxiliary"
    prompt_profile = "framework_auxiliary_lightmem_reference_v1"

    def build_prompt(
        self,
        question: Question | str,
        prediction: AnswerResult | str,
        gold_answer: GoldAnswerInfo | str,
    ) -> str:
        """构造 LoCoMo judge prompt（LightMem 官方模板 + 项目输出格式指令）。

        输入:
            question: 公开问题对象或文本。
            prediction: method 预测答案对象或文本。
            gold_answer: evaluator 私有标准答案对象或文本。

        输出:
            str: 完整的 LoCoMo 判分 prompt。
        """

        question_text, prediction_text, gold_text = self._extract_text_fields(
            question,
            prediction,
            gold_answer,
        )
        judge_prompt = _LOC0MO_JUDGE_PROMPT.format(
            question=question_text,
            gold_answer=gold_text,
            generated_answer=prediction_text,
        )
        return (
            judge_prompt
            + "First, provide a short (one sentence) explanation of your reasoning, "
            + "then finish with CORRECT or WRONG. "
            + "Do NOT include both CORRECT and WRONG in your response, "
            + "or it will break the evaluation script.\n\n"
            + self._output_instruction()
        )

    def _output_instruction(self) -> str:
        """覆盖父类，compact 模式输出 JSON {"label": "CORRECT"}。"""

        if self.mode.strip().lower() == "compact":
            return "Just return the label CORRECT or WRONG in a json format with the key as 'label'.\n"
        return super()._output_instruction()

    def evaluate(
        self,
        question: Question,
        prediction: AnswerResult | str,
        gold_answer: GoldAnswerInfo | str,
    ) -> MetricResult:
        """调用 LLM judge 并返回单题 metric。

        compact 模式对齐 LightMem 官方：JSON {"label": "CORRECT/WRONG"}，
        `chat.completions.create` + `response_format={"type": "json_object"}`。
        详细模式走父类 JSON {"is_correct": ..., "reason": ...}。
        """

        prompt = self.build_prompt(question, prediction, gold_answer)
        model_response = self._call_model_with_usage(prompt)
        self._record_judge_llm_call(model_response)

        if self.mode.strip().lower() == "compact":
            label = self._parse_compact_label(model_response.text)
            is_correct = label == "CORRECT"
            return MetricResult(
                metric_name=self.metric_name,
                score=1.0 if is_correct else 0.0,
                is_correct=is_correct,
                details={
                    "raw_judge_response": model_response.text,
                    "metric_tier": self.metric_tier,
                    "prompt_profile": self.prompt_profile,
                },
            )

        decision = parse_judge_response(model_response.text, mode=self.mode)
        return MetricResult(
            metric_name=self.metric_name,
            score=1.0 if decision.is_correct else 0.0,
            is_correct=decision.is_correct,
            details={
                "reason": decision.reason,
                "raw_judge_response": model_response.text,
                "metric_tier": self.metric_tier,
                "prompt_profile": self.prompt_profile,
            },
        )

    def _call_model_with_usage(self, prompt: str) -> JudgeModelResponse:
        """对齐 LightMem 官方：`chat.completions.create` + JSON mode。

        覆盖父类 `responses.create`，因为 LightMem 官方 judge 使用 Chat
        Completions API 而非 Responses API。
        """

        client = self._get_client()
        model = self.model or self._get_settings().openai.model
        kwargs: dict[str, Any] = dict(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        if self.mode.strip().lower() == "compact":
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content
        if not isinstance(text, str) or not text.strip():
            raise JudgeOutputError("model response is empty")
        input_tokens, output_tokens = _extract_usage_tokens(response)
        usage = resolve_token_usage(
            api_input_tokens=input_tokens,
            api_output_tokens=output_tokens,
            prompt_text=prompt,
            output_text=text,
            tokenizer=self._tokenizer(model),
        )
        return JudgeModelResponse(
            text=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_measurement_source=usage.source,
        )

    @staticmethod
    def _parse_compact_label(text: str) -> str:
        """解析 compact judge 输出的 JSON `{"label": "CORRECT"}`。

        容错：若 JSON 解析失败，尝试从纯文本匹配 CORRECT/WRONG（兜底）。
        """

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # fallback: match CORRECT/WRONG from plain text
            import re
            text_upper = text.strip().upper()
            match = re.search(r"\b(CORRECT|WRONG)\b", text_upper)
            if match:
                return match.group(1)
            raise JudgeOutputError(
                "compact output must be valid JSON or contain CORRECT/WRONG"
            ) from None
        if not isinstance(payload, dict):
            raise JudgeOutputError("compact JSON must be an object")
        label = payload.get("label")
        if not isinstance(label, str) or label.upper() not in ("CORRECT", "WRONG"):
            raise JudgeOutputError(
                "compact JSON label must be CORRECT or WRONG"
            )
        return label.upper()

    @staticmethod
    def _tokenizer(model: str) -> Any:
        """懒加载 tiktoken encoding 供 token 估算。"""

        from memory_benchmark.evaluators.llm_judge import _TiktokenCounter
        return _TiktokenCounter(model)

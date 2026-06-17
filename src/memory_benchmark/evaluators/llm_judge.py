"""LLM judge 输出解析和通用调用外壳。

本模块只负责把模型返回文本解析成统一决策，并提供可被具体 benchmark
复用的懒加载 OpenAI 调用外壳。单元测试不会触发真实网络请求。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from memory_benchmark.config import load_settings
from memory_benchmark.core import AnswerResult, GoldAnswerInfo, MetricResult, Question
from memory_benchmark.core.exceptions import ConfigurationError, JudgeOutputError
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
    ModelDescriptor,
    resolve_token_usage,
)


@dataclass(frozen=True)
class JudgeDecision:
    """LLM judge 对单题回答是否正确的结构化决策。

    字段:
        is_correct: 预测答案是否应计为正确。
        reason: 可选解释，主要用于审计日志和调试。
    """

    is_correct: bool
    reason: str = ""


@dataclass(frozen=True)
class LLMJudgeProfileConfig:
    """LLM judge TOML profile 的强类型表示。

    字段:
        mode: 输出模式，只允许 `compact` 或 `detailed`。
        model: judge 使用的模型名称。
    """

    mode: str
    model: str

    def __post_init__(self) -> None:
        """校验输出模式和模型名称。"""

        if self.mode not in {"compact", "detailed"}:
            raise ConfigurationError(f"Unsupported judge mode: {self.mode}")
        if not self.model.strip():
            raise ConfigurationError("Judge model is required")


@dataclass(frozen=True)
class JudgeModelResponse:
    """一次 Judge LLM 调用的文本与 token 计量结果。"""

    text: str
    input_tokens: int
    output_tokens: int
    token_measurement_source: MeasurementSource


def parse_judge_response(text: str, mode: str) -> JudgeDecision:
    """解析 judge 原始文本输出。

    输入:
        text: LLM 返回的原始文本。
        mode: 解析模式；`compact` 只接受 true/false，`detailed` 接受 JSON 对象。

    输出:
        JudgeDecision: 统一后的布尔判定和可选原因。

    异常:
        JudgeOutputError: 输出为空、格式错误或字段类型不符合约定。
    """

    normalized_mode = mode.strip().lower()
    if normalized_mode == "compact":
        return _parse_compact_response(text)
    if normalized_mode == "detailed":
        return _parse_detailed_response(text)
    raise JudgeOutputError(f"unsupported judge mode: {mode}")


class LLMJudgeEvaluator:
    """可复用的 LLM judge evaluator 外壳。

    子类负责提供 benchmark-specific prompt；本类负责懒加载配置、调用模型、
    解析输出并生成 `MetricResult`。构造对象本身不会读取 `.env` 或创建客户端。
    """

    metric_name = "llm_judge_accuracy"
    benchmark_name = "generic"
    supports_efficiency_observability = True

    def __init__(
        self,
        mode: str = "detailed",
        model: str | None = None,
        client: Any | None = None,
        project_root: str | None = None,
        env_file: str | None = None,
        efficiency_collector: EfficiencyCollector | None = None,
    ) -> None:
        """初始化 judge 外壳。

        输入:
            mode: judge 输出解析模式，默认 detailed。
            model: 覆盖配置层模型名；为空时在真实调用前读取配置。
            client: 可注入的兼容 OpenAI client，便于后续测试或替换。
            project_root: 读取配置时使用的项目根目录。
            env_file: 读取配置时使用的 `.env` 路径。
            efficiency_collector: runner 管理的可选 evaluator-side observation collector。

        输出:
            None。
        """

        self.mode = mode
        self.model = model
        self._client = client
        self._project_root = project_root
        self._env_file = env_file
        self._settings = None
        self.efficiency_collector = efficiency_collector

    def build_prompt(
        self,
        question: Question | str,
        prediction: AnswerResult | str,
        gold_answer: GoldAnswerInfo | str,
    ) -> str:
        """构造 judge prompt。

        输入:
            question: 公开问题对象或问题文本。
            prediction: method 答案对象或答案文本。
            gold_answer: evaluator 私有标准答案对象或答案文本。

        输出:
            str: 发送给 LLM judge 的 prompt。
        """

        raise NotImplementedError("subclasses must implement build_prompt")

    def evaluate(
        self,
        question: Question,
        prediction: AnswerResult | str,
        gold_answer: GoldAnswerInfo | str,
    ) -> MetricResult:
        """调用 LLM judge 并返回单题 metric。

        输入:
            question: method 可见的公开问题。
            prediction: method 输出答案。
            gold_answer: evaluator 私有标准答案。

        输出:
            MetricResult: 包含 0/1 分数、布尔正确性和 judge 原因。
        """

        prompt = self.build_prompt(question, prediction, gold_answer)
        model_response = self._call_model_with_usage(prompt)
        self._record_judge_llm_call(model_response)
        decision = parse_judge_response(model_response.text, mode=self.mode)
        return MetricResult(
            metric_name=self.metric_name,
            score=1.0 if decision.is_correct else 0.0,
            is_correct=decision.is_correct,
            details={
                "reason": decision.reason,
                "raw_judge_response": model_response.text,
            },
        )

    def efficiency_model_inventory(self) -> tuple[ModelDescriptor, ...]:
        """返回 judge evaluator 会写入 observation 的模型身份。"""

        model_name = self.model or self._get_settings().openai.model
        return (
            ModelDescriptor(
                model_id="judge-llm",
                model_name=model_name,
                model_role="judge_llm",
                execution_mode="api",
                tokenizer_name=model_name,
            ),
        )

    def _extract_text_fields(
        self,
        question: Question | str,
        prediction: AnswerResult | str,
        gold_answer: GoldAnswerInfo | str,
    ) -> tuple[str, str, str]:
        """从实体或字符串中提取 prompt 所需文本。

        输入:
            question: 公开问题对象或文本。
            prediction: method 答案对象或文本。
            gold_answer: 标准答案对象或文本。

        输出:
            tuple[str, str, str]: 问题、预测答案、标准答案文本。
        """

        question_text = question.text if isinstance(question, Question) else str(question)
        prediction_text = prediction.answer if isinstance(prediction, AnswerResult) else str(prediction)
        gold_text = gold_answer.answer if isinstance(gold_answer, GoldAnswerInfo) else str(gold_answer)
        return question_text, prediction_text, gold_text

    def _output_instruction(self) -> str:
        """根据解析模式生成与 parser 对齐的输出格式指令。

        输入:
            无。读取当前 evaluator 的 `mode`。

        输出:
            str: prompt 中要求 judge 遵守的输出格式。
        """

        normalized_mode = self.mode.strip().lower()
        if normalized_mode == "compact":
            return "Return exactly one lowercase word: true or false.\n"
        if normalized_mode == "detailed":
            return 'Return JSON exactly as {"is_correct": true|false, "reason": "..."}.\n'
        raise JudgeOutputError(f"unsupported judge mode: {self.mode}")

    def _call_model(self, prompt: str) -> str:
        """调用真实 LLM judge。

        输入:
            prompt: 已构造好的 judge prompt。

        输出:
            str: 模型原始文本输出。
        """

        return self._call_model_with_usage(prompt).text

    def _call_model_with_usage(self, prompt: str) -> JudgeModelResponse:
        """调用 LLM judge，并解析文本和 token usage。"""

        client = self._get_client()
        model = self.model or self._get_settings().openai.model
        response = client.responses.create(
            model=model,
            input=prompt,
            temperature=0,
        )
        text = _extract_response_text(response)
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

    def _record_judge_llm_call(self, model_response: JudgeModelResponse) -> None:
        """在 runner 建立的 judge scope 内记录一次 LLM 调用。"""

        collector = self.efficiency_collector
        if collector is None or not collector.enabled:
            return
        with collector.operation_stage(EfficiencyStage.JUDGE):
            collector.record_llm_call(
                model_id="judge-llm",
                input_tokens=model_response.input_tokens,
                output_tokens=model_response.output_tokens,
                token_measurement_source=model_response.token_measurement_source,
            )

    def _get_client(self) -> Any:
        """懒加载 OpenAI client。

        输入:
            无。

        输出:
            Any: OpenAI SDK client 或注入的兼容 client。
        """

        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(**self._get_settings().openai.to_client_kwargs())
        return self._client

    def _get_settings(self) -> Any:
        """懒加载项目配置。

        输入:
            无。

        输出:
            AppSettings: 配置层返回的结构化设置。
        """

        if self._settings is None:
            self._settings = load_settings(
                project_root=self._project_root,
                env_file=self._env_file,
            )
        return self._settings


def _parse_compact_response(text: str) -> JudgeDecision:
    """解析 compact judge 输出。

    输入:
        text: LLM 原始输出。

    输出:
        JudgeDecision: true/false 对应的结构化判定。
    """

    normalized_text = _ensure_text(text).strip().lower()
    if normalized_text == "true":
        return JudgeDecision(is_correct=True)
    if normalized_text == "false":
        return JudgeDecision(is_correct=False)
    raise JudgeOutputError("compact output must be exactly true or false")


def _parse_detailed_response(text: str) -> JudgeDecision:
    """解析 detailed JSON judge 输出。

    输入:
        text: LLM 原始输出，必须是 JSON object 字符串。

    输出:
        JudgeDecision: JSON 中的结构化判定。
    """

    raw_text = _ensure_text(text)
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise JudgeOutputError("detailed output must be valid JSON") from exc

    if not isinstance(payload, dict):
        raise JudgeOutputError("detailed output must be a JSON object")
    if "is_correct" not in payload:
        raise JudgeOutputError("detailed output missing is_correct")
    if not isinstance(payload["is_correct"], bool):
        raise JudgeOutputError("is_correct must be a boolean")

    reason = payload.get("reason", "")
    if not isinstance(reason, str):
        raise JudgeOutputError("reason must be a string when provided")

    return JudgeDecision(is_correct=payload["is_correct"], reason=reason)


def _ensure_text(text: str) -> str:
    """校验并返回字符串输出。

    输入:
        text: 待解析对象。

    输出:
        str: 原始字符串。
    """

    if not isinstance(text, str):
        raise JudgeOutputError("judge response must be a string")
    return text


def _extract_response_text(response: Any) -> str:
    """从 OpenAI SDK 响应对象中提取文本。

    输入:
        response: OpenAI Responses API 返回对象，或测试中注入的兼容结构。

    输出:
        str: 可交给 parser 的 judge 原始文本。
    """

    if isinstance(response, str):
        return response

    output_text = _get_mapping_or_attr(response, "output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    if isinstance(response, dict):
        output = response.get("output")
    else:
        output = getattr(response, "output", None)

    if isinstance(output, list):
        for item in output:
            content = _get_mapping_or_attr(item, "content")
            if isinstance(content, list):
                for content_item in content:
                    text = _get_mapping_or_attr(content_item, "text")
                    if isinstance(text, str) and text.strip():
                        return text

    raise JudgeOutputError("model response does not contain output text")


class _TiktokenCounter:
    """按 OpenAI-compatible 模型名计数 token 的轻量 wrapper。"""

    def __init__(self, model_name: str) -> None:
        """保存模型名，encoding 懒加载以避免无观测路径额外开销。"""

        self.model_name = model_name
        self._encoding = None

    def count_tokens(self, text: str) -> int:
        """返回文本 token 数；未知模型回退到 cl100k_base。"""

        if self._encoding is None:
            try:
                import tiktoken
            except Exception as exc:
                raise ConfigurationError(
                    "tiktoken is required for judge token estimation"
                ) from exc
            try:
                self._encoding = tiktoken.encoding_for_model(self.model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return len(self._encoding.encode(text or ""))


def _extract_usage_tokens(response: Any) -> tuple[int | None, int | None]:
    """从 OpenAI Responses API usage 中提取 input/output token。"""

    usage = _get_mapping_or_attr(response, "usage")
    if usage is None:
        return None, None
    input_tokens = _get_first_int(usage, ("input_tokens", "prompt_tokens"))
    output_tokens = _get_first_int(usage, ("output_tokens", "completion_tokens"))
    return input_tokens, output_tokens


def _get_first_int(source: Any, field_names: tuple[str, ...]) -> int | None:
    """按候选字段顺序读取第一个整数 token 值。"""

    for field_name in field_names:
        value = _get_mapping_or_attr(source, field_name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _get_mapping_or_attr(value: Any, key: str) -> Any:
    """兼容 dict 和 SDK 对象读取字段。

    输入:
        value: dict 或普通对象。
        key: 字段名。

    输出:
        Any: 字段值；不存在时返回 None。
    """

    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)

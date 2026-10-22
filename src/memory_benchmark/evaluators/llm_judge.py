"""工业级 Pydantic 双模式强类型 LLM-as-a-Judge 评测器 (`LLMJudgeEvaluator`)。

设计亮点：
1. **Pydantic 双模式（Binary / Rubric）强类型契约**：
   - `BinaryJudgeEvaluation`：针对 LoCoMo、LongMemEval、MemBench、HaluMem 等二元基准，物理杜绝 `PARTIAL`，严格在 `CORRECT`/`WRONG`/`UNDECIDABLE` 中裁决；
   - `RubricJudgeEvaluation`：针对 BEAM 等复合基准，放开 `PARTIAL` 选项评定半部分值；
2. **CoT 思维链思考前置（Reasoning-First）**：
   - 规定 `reason` 字段位于 `verdict` 之前，迫使自回归大模型先生成充分比对事实证据，再基于注意力注意力机制下达裁决；
3. **剥离 `score` 生成与确定性映射**：
   - LLM 仅负责语义判定，分值（1.0 / 0.5 / 0.0）100% 由 Python 字典根据 `verdict` 确定性映射，彻底杜绝大模型数字越界或自相矛盾；
4. **API 语法硬约束 + 运行时多层防线安检**：
   - 请求时携带 `response_format={"type": "json_object"}`，接收后利用 Pydantic `model_validate_json` 实行类型与非空安检，辅以正则围栏剥离与启发式降级兜底。
"""

from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

from memory_benchmark.core import (
    AnswerResult,
    GoldAnswerInfo,
    JudgeOutputError,
    LLMProperties,
    MetricResult,
    PromptProperties,
    Question,
    build_prompt_variable_pool,
    format_prompt_template,
)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)

VALID_VERDICTS = ("CORRECT", "PARTIAL", "WRONG", "UNDECIDABLE")

VERDICT_SCORE_MAP: dict[str, float] = {
    "CORRECT": 1.0,
    "PARTIAL": 0.5,
    "WRONG": 0.0,
    "UNDECIDABLE": 0.0,
}


class BinaryJudgeEvaluation(BaseModel):
    """二元裁判契约（针对 LoCoMo、LongMemEval、MemBench、HaluMem 等非黑即白基准）。

    在 Schema 语法层物理杜绝 PARTIAL，模型只能在 CORRECT、WRONG 与 UNDECIDABLE 间做选择题。
    """

    reason: str = Field(
        ...,
        description="Detailed step-by-step reasoning comparing the predicted answer against the gold answer.",
    )
    verdict: Literal["CORRECT", "WRONG", "UNDECIDABLE"] = Field(
        ...,
        description="Final judgment verdict. Must be one of CORRECT, WRONG, or UNDECIDABLE.",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("reason must not be empty or blank")
        return cleaned


class RubricJudgeEvaluation(BaseModel):
    """三档量规裁判契约（针对 BEAM 等复合多实体或部分正确基准）。

    语法层开放 PARTIAL 选项，允许按 0.5 分评定部分记忆召回。
    """

    reason: str = Field(
        ...,
        description="Detailed step-by-step reasoning comparing the predicted answer against the gold answer.",
    )
    verdict: Literal["CORRECT", "PARTIAL", "WRONG", "UNDECIDABLE"] = Field(
        ...,
        description="Final judgment verdict. Must be one of CORRECT, PARTIAL, WRONG, or UNDECIDABLE.",
    )

    @field_validator("reason")
    @classmethod
    def validate_reason_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("reason must not be empty or blank")
        return cleaned


@dataclass(frozen=True)
class JudgeDecision:
    """LLM 裁判解析后的结构化裁决结果。"""

    verdict: str
    score: float
    reason: str
    needs_human_review: bool = False
    raw_response: str = ""

    @property
    def is_correct(self) -> bool:
        return self.verdict == "CORRECT" or self.score >= 1.0


def parse_judge_response(
    text: str,
    mode: Literal["binary", "rubric"] = "binary",
) -> JudgeDecision:
    """解析裁判 LLM 输出，优先使用对应模式的 Pydantic 模型校验，辅以正则与启发式降级。"""
    cleaned = (text or "").strip()
    if not cleaned:
        raise JudgeOutputError("Judge LLM returned an empty response")

    schema_cls: type[BaseModel] = RubricJudgeEvaluation if mode == "rubric" else BinaryJudgeEvaluation

    # 1. 第一防线：使用 Pydantic 强类型反序列化校验
    json_candidate = cleaned
    match = _JSON_BLOCK_RE.search(cleaned)
    if match:
        json_candidate = match.group(0)

    try:
        parsed = schema_cls.model_validate_json(json_candidate)
        verdict = str(parsed.verdict).upper()
        reason = str(parsed.reason).strip()
        score = VERDICT_SCORE_MAP.get(verdict, 0.0)
        needs_review = (verdict == "UNDECIDABLE")
        return JudgeDecision(
            verdict=verdict,
            score=score,
            reason=reason or ("Insufficient context; routed to human review." if needs_review else ""),
            needs_human_review=needs_review,
            raw_response=cleaned,
        )
    except Exception:
        # Pydantic 校验未通过时（如字段命名略有出入或老测试桩），进入第二防线
        pass

    # 2. 第二防线：提取 JSON 字典并进行别名容错
    if match:
        try:
            payload = json.loads(match.group(0))
            if isinstance(payload, dict):
                raw_v = str(payload.get("verdict") or payload.get("label") or "").strip().upper()
                raw_r = str(payload.get("reason") or payload.get("explanation") or "").strip()

                if raw_v in {"CORRECT", "PARTIAL", "WRONG", "UNDECIDABLE"}:
                    if mode == "binary" and raw_v == "PARTIAL":
                        raw_v = "WRONG"
                    needs_review = (raw_v == "UNDECIDABLE")
                    return JudgeDecision(
                        verdict=raw_v,
                        score=VERDICT_SCORE_MAP.get(raw_v, 0.0),
                        reason=raw_r or ("Insufficient context; routed to human review." if needs_review else ""),
                        needs_human_review=needs_review,
                        raw_response=cleaned,
                    )
        except Exception:
            pass

    # 3. 第三防线：首词启发式扫描兜底（保证离线测试桩与极端异常不中断主循环）
    upper = cleaned.upper()
    if "UNDECIDABLE" in upper:
        return JudgeDecision("UNDECIDABLE", 0.0, cleaned, True, cleaned)
    if upper.startswith("CORRECT") or upper.startswith("YES"):
        return JudgeDecision("CORRECT", 1.0, cleaned, False, cleaned)
    if mode == "rubric" and upper.startswith("PARTIAL"):
        return JudgeDecision("PARTIAL", 0.5, cleaned, False, cleaned)
    if upper.startswith("WRONG") or upper.startswith("INCORRECT") or upper.startswith("NO"):
        return JudgeDecision("WRONG", 0.0, cleaned, False, cleaned)

    raise JudgeOutputError(f"Unable to parse Judge LLM response into {schema_cls.__name__}: {cleaned!r}")


@dataclass
class LLMJudgeEvaluator:
    """遵循构造器依赖注入 (DI) 的通用 LLM 裁判评估器。"""

    llm_props: LLMProperties = field(default_factory=LLMProperties)
    prompt_props: PromptProperties = field(default_factory=PromptProperties)
    mode: Literal["binary", "rubric"] = "binary"
    completion_fn: Any | None = None
    metric_name: str = "llm_judge"
    _client: Any = field(default=None, init=False, repr=False)
    _client_lock: Any = field(default_factory=threading.Lock, init=False, repr=False)

    def _get_client(self) -> OpenAI:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = OpenAI(
                        api_key=self.llm_props.require_api_key(),
                        base_url=self.llm_props.base_url,
                        timeout=self.llm_props.timeout_seconds,
                        max_retries=self.llm_props.max_retries,
                    )
        return self._client

    def _call_judge_llm(self, system_prompt: str, user_prompt: str) -> str:
        if callable(self.completion_fn):
            return str(self.completion_fn(system_prompt=system_prompt, user_prompt=user_prompt))

        client = self._get_client()
        messages: list[dict[str, str]] = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt.strip()})
        messages.append({"role": "user", "content": user_prompt.strip()})

        kwargs: dict[str, Any] = {
            "model": self.llm_props.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": self.llm_props.temperature,
        }
        if self.llm_props.max_tokens and self.llm_props.max_tokens > 0:
            kwargs["max_tokens"] = self.llm_props.max_tokens

        max_attempts = 4
        for attempt in range(max_attempts):
            try:
                resp = client.chat.completions.create(**kwargs)
                content = resp.choices[0].message.content
                return "" if content is None else str(content)
            except Exception as exc:
                if attempt < max_attempts - 1:
                    sleep_s = min(1.5 ** attempt, 8.0)
                    time.sleep(sleep_s)
                else:
                    raise

    def evaluate(
        self,
        question: Question,
        answer: AnswerResult,
        gold: GoldAnswerInfo,
    ) -> MetricResult:
        """渲染注入的 `prompt_props`，调用 Judge LLM 并解析结构化裁决结果。"""
        system_template = self.prompt_props.get_judge_system(question.category)
        user_template = self.prompt_props.judge_user

        variables = build_prompt_variable_pool(
            question_text=question.text,
            question_time=question.question_time or "",
            gold_answer=gold.answer,
            predicted_answer=answer.answer,
            conversation_id=question.conversation_id,
            category=question.category or "",
            options=question.options,
            extra={**question.metadata, **gold.metadata},
        )
        system_prompt = format_prompt_template(system_template, variables).strip()
        user_prompt = format_prompt_template(user_template, variables).strip()

        try:
            raw_output = self._call_judge_llm(system_prompt, user_prompt)
            decision = parse_judge_response(raw_output, mode=self.mode)
        except Exception as exc:
            decision = JudgeDecision(
                verdict="UNDECIDABLE",
                score=0.0,
                reason=f"Judge invocation failed after retries: {exc}",
                needs_human_review=True,
                judgment=f"ERROR: {exc}",
            )
        return MetricResult(
            metric_name=self.metric_name,
            score=decision.score,
            is_correct=decision.is_correct,
            details={
                "question_id": question.question_id,
                "conversation_id": question.conversation_id,
                "mode": self.mode,
                "verdict": decision.verdict,
                "reason": decision.reason,
                "needs_human_review": decision.needs_human_review,
                "judge_model": self.llm_props.model,
                "judge_temperature": self.llm_props.temperature,
            },
        )


__all__ = [
    "BinaryJudgeEvaluation",
    "JudgeDecision",
    "LLMJudgeEvaluator",
    "RubricJudgeEvaluation",
    "VALID_VERDICTS",
    "VERDICT_SCORE_MAP",
    "parse_judge_response",
]

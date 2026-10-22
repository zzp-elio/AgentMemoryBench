"""Answer 质量评估器 (`evaluators`) 门面协议、工厂路由与统一导出。

模块结构：
- `exact_match.py` : `ExactMatchEvaluator`（归一化精确匹配 + 单字母选择题判分）
- `f1.py`          : `F1Evaluator`（标准词袋 Token F1 基线）
- `llm_judge.py`   : `LLMJudgeEvaluator`（YAML 配置依赖注入 + `UNDECIDABLE` 拒判路由）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from memory_benchmark.core import (
    AnswerResult,
    ConfigurationError,
    GoldAnswerInfo,
    MetricResult,
    Question,
)

from .exact_match import ExactMatchEvaluator, normalize_answer
from .f1 import F1Evaluator, normalized_tokens
from .llm_judge import (
    VALID_VERDICTS,
    VERDICT_SCORE_MAP,
    BinaryJudgeEvaluation,
    JudgeDecision,
    LLMJudgeEvaluator,
    RubricJudgeEvaluation,
    parse_judge_response,
)


@runtime_checkable
class AnswerEvaluator(Protocol):
    """单题回答质量评估器标准协议。"""

    metric_name: str

    def evaluate(
        self,
        question: Question,
        answer: AnswerResult,
        gold: GoldAnswerInfo,
    ) -> MetricResult:
        """评估单个问题的模型回答质量。"""


SUPPORTED_METRICS: tuple[str, ...] = ("f1", "exact_match", "llm_judge")


def list_evaluators() -> list[str]:
    """返回支持的三大标准评测器名称。"""
    return list(SUPPORTED_METRICS)


list_metrics = list_evaluators


def create_evaluator(
    metric_name: str,
    benchmark_name: str = "default",
    *,
    project_root: str | Path = ".",
    llm_props: Any | None = None,
    prompt_props: Any | None = None,
    overrides: dict[str, Any] | None = None,
    completion_fn: Any | None = None,
) -> AnswerEvaluator:
    """根据指标名称构造对应的标准 `AnswerEvaluator` 实例（支持显式依赖注入与按 Benchmark 覆盖）。"""
    from memory_benchmark.core import load_app_config

    key = metric_name.strip().lower().replace("-", "_")
    if key == "f1":
        return F1Evaluator()
    if key in {"exact_match", "em", "normalized_em"}:
        return ExactMatchEvaluator()
    if key in {"llm_judge", "judge"}:
        if llm_props is None or prompt_props is None:
            prof = load_app_config(project_root).profile(benchmark_name, overrides=overrides)
            llm_props = llm_props or prof.judge_llm
            prompt_props = prompt_props or prof.prompts
        mode = "rubric" if benchmark_name.strip().lower() == "beam" else "binary"
        return LLMJudgeEvaluator(
            llm_props=llm_props,
            prompt_props=prompt_props,
            mode=mode,
            completion_fn=completion_fn,
        )
    raise ConfigurationError(
        f"Unknown metric '{metric_name}'. Supported metrics: {', '.join(SUPPORTED_METRICS)}"
    )



# 默认包导出
# 比如from evaluators import *
# 那么默认只能用到这些东西
__all__ = [
    "AnswerEvaluator",
    "BinaryJudgeEvaluation",
    "ExactMatchEvaluator",
    "F1Evaluator",
    "JudgeDecision",
    "LLMJudgeEvaluator",
    "RubricJudgeEvaluation",
    "SUPPORTED_METRICS",
    "VALID_VERDICTS",
    "VERDICT_SCORE_MAP",
    "create_evaluator",
    "list_evaluators",
    "list_metrics",
    "normalize_answer",
    "normalized_tokens",
    "parse_judge_response",
]

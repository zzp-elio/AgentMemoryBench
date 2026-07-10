"""测试统一 evaluator registry 的支持矩阵和构造边界。"""

from __future__ import annotations

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.beam_rubric_judge import (
    BeamRubricJudgeEvaluator,
)
from memory_benchmark.evaluators.longmemeval_judge import (
    LongMemEvalJudgeEvaluator,
)
from memory_benchmark.evaluators.locomo_f1 import LoCoMoF1Evaluator
from memory_benchmark.evaluators.locomo_judge import LoCoMoJudgeEvaluator
from memory_benchmark.evaluators.locomo_recall import LoCoMoRetrievalRecallEvaluator
from memory_benchmark.evaluators.llm_judge import LLMJudgeProfileConfig
from memory_benchmark.evaluators.membench_choice_accuracy import (
    MemBenchChoiceAccuracyEvaluator,
)
from memory_benchmark.evaluators.registry import (
    create_evaluator,
    get_evaluator_registration,
    list_metrics,
    load_evaluator_profile,
)


pytestmark = pytest.mark.unit


def test_registry_lists_only_currently_supported_unified_metrics() -> None:
    """统一入口应列出当前已装配的 LoCoMo 与 LongMemEval 指标。"""

    assert list_metrics() == [
        "beam-rubric-judge",
        "halumem-extraction",
        "halumem-qa",
        "halumem-update",
        "locomo-f1",
        "locomo-judge",
        "locomo-recall",
        "longmemeval-judge",
        "membench-choice-accuracy",
    ]


def test_locomo_f1_registration_is_offline_and_locomo_only() -> None:
    """LoCoMo F1 应标记为离线指标，且不能用于其他 benchmark。"""

    registration = get_evaluator_registration("locomo-f1")

    assert registration.metric_name == "locomo_f1"
    assert registration.supported_benchmarks == frozenset({"locomo"})
    assert registration.requires_api is False
    assert isinstance(
        create_evaluator("locomo-f1", benchmark_name="locomo"),
        LoCoMoF1Evaluator,
    )

    with pytest.raises(ConfigurationError, match="does not support benchmark"):
        create_evaluator("locomo-f1", benchmark_name="longmemeval")


def test_locomo_recall_registration_is_offline_and_locomo_only() -> None:
    """LoCoMo retrieval recall 应标记为离线指标，且不能用于其他 benchmark。"""

    registration = get_evaluator_registration("locomo-recall")

    assert registration.metric_name == "locomo_recall"
    assert registration.supported_benchmarks == frozenset({"locomo"})
    assert registration.requires_api is False
    assert isinstance(
        create_evaluator("locomo-recall", benchmark_name="locomo"),
        LoCoMoRetrievalRecallEvaluator,
    )

    with pytest.raises(ConfigurationError, match="does not support benchmark"):
        create_evaluator("locomo-recall", benchmark_name="longmemeval")


def test_membench_choice_accuracy_registration_is_offline_and_membench_only() -> None:
    """MemBench choice accuracy 应标记为离线指标，且不能用于其他 benchmark。"""

    registration = get_evaluator_registration("membench-choice-accuracy")

    assert registration.metric_name == "membench_choice_accuracy"
    assert registration.supported_benchmarks == frozenset({"membench"})
    assert registration.requires_api is False
    assert isinstance(
        create_evaluator(
            "membench-choice-accuracy",
            benchmark_name="membench",
        ),
        MemBenchChoiceAccuracyEvaluator,
    )

    with pytest.raises(ConfigurationError, match="does not support benchmark"):
        create_evaluator(
            "membench-choice-accuracy",
            benchmark_name="locomo",
        )


def test_locomo_judge_registration_requires_api_and_valid_profile() -> None:
    """LoCoMo judge 应声明 API 成本，并只接受 compact/detailed profile。"""

    registration = get_evaluator_registration("locomo-judge")

    assert registration.metric_name == "locomo_judge_accuracy"
    assert registration.requires_api is True
    assert registration.profile_names == frozenset({"compact", "detailed"})
    assert registration.profile_relative_path is not None

    evaluator = create_evaluator(
        "locomo-judge",
        benchmark_name="locomo",
        profile_name="compact",
        model="gpt-4o-mini",
        client=object(),
    )
    assert isinstance(evaluator, LoCoMoJudgeEvaluator)
    assert evaluator.mode == "compact"
    assert evaluator.model == "gpt-4o-mini"

    with pytest.raises(ConfigurationError, match="Unknown evaluator profile"):
        create_evaluator(
            "locomo-judge",
            benchmark_name="locomo",
            profile_name="verbose",
        )


def test_longmemeval_judge_registration_requires_api_and_longmemeval_only() -> None:
    """LongMemEval judge 应复用现有 judge profile，并限制在 longmemeval。"""

    registration = get_evaluator_registration("longmemeval-judge")

    assert registration.metric_name == "longmemeval_judge_accuracy"
    assert registration.supported_benchmarks == frozenset({"longmemeval"})
    assert registration.requires_api is True
    assert registration.profile_names == frozenset({"compact", "detailed"})
    assert registration.profile_relative_path is not None

    evaluator = create_evaluator(
        "longmemeval-judge",
        benchmark_name="longmemeval",
        profile_name="detailed",
        model="gpt-4o-mini",
        client=object(),
    )
    assert isinstance(evaluator, LongMemEvalJudgeEvaluator)
    assert evaluator.mode == "detailed"
    assert evaluator.model == "gpt-4o-mini"

    with pytest.raises(ConfigurationError, match="does not support benchmark"):
        create_evaluator(
            "longmemeval-judge",
            benchmark_name="locomo",
            profile_name="compact",
        )


def test_load_evaluator_profile_returns_strongly_typed_judge_config(
    tmp_path,
) -> None:
    """judge TOML section 应转换为强类型配置，而不是裸字典。"""

    profile_path = tmp_path / "configs" / "evaluators" / "llm_judge.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
[compact]
mode = "compact"
model = "gpt-4o-mini"
""",
        encoding="utf-8",
    )

    config = load_evaluator_profile(
        metric_name="locomo-judge",
        profile_name="compact",
        project_root=tmp_path,
    )

    assert config == LLMJudgeProfileConfig(
        mode="compact",
        model="gpt-4o-mini",
    )


def test_unknown_metric_is_rejected_before_evaluator_construction() -> None:
    """未知 metric 应给出支持列表，不能静默回退。"""

    with pytest.raises(ConfigurationError, match="Unknown metric"):
        get_evaluator_registration("bleu")


def test_beam_rubric_judge_registration_requires_api_and_beam_only() -> None:
    """BEAM rubric judge 应声明 API 成本，并限制在 beam benchmark。"""

    registration = get_evaluator_registration("beam-rubric-judge")

    assert registration.metric_name == "beam_rubric_judge"
    assert registration.supported_benchmarks == frozenset({"beam"})
    assert registration.requires_api is True
    assert registration.profile_names == frozenset({"compact", "detailed"})
    assert registration.profile_relative_path is not None

    evaluator = create_evaluator(
        "beam-rubric-judge",
        benchmark_name="beam",
        profile_name="detailed",
        model="gpt-4o-mini",
        client=object(),
    )
    assert isinstance(evaluator, BeamRubricJudgeEvaluator)
    assert evaluator.mode == "detailed"
    assert evaluator.model == "gpt-4o-mini"

    with pytest.raises(ConfigurationError, match="does not support benchmark"):
        create_evaluator(
            "beam-rubric-judge",
            benchmark_name="locomo",
            profile_name="compact",
        )

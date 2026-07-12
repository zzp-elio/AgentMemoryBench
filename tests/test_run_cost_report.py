"""每次运行成本报告的纯离线测试。"""

from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

import pytest

from memory_benchmark.analysis.cost import APILLMPrice, load_pricing
from memory_benchmark.analysis.run_cost_report import build_run_cost_report
from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyStage,
    LLMCallObservation,
    MeasurementSource,
    ModelDescriptor,
)
from memory_benchmark.storage.experiment_paths import ExperimentPaths


def _llm_call(
    observation_id: str,
    stage: EfficiencyStage,
    input_tokens: int,
    source: MeasurementSource = MeasurementSource.API_USAGE,
) -> LLMCallObservation:
    """构造成本报告测试用 LLM observation。"""

    return LLMCallObservation(
        observation_id=observation_id,
        stage=stage,
        model_id="gpt-4o-mini",
        input_tokens=input_tokens,
        output_tokens=0,
        token_measurement_source=source,
        conversation_id="conv-1",
        question_id=None if stage is EfficiencyStage.MEMORY_BUILD else "q-1",
    )


def _api_inventory() -> list[ModelDescriptor]:
    """返回测试用 API 模型清单。"""

    return [
        ModelDescriptor(
            model_id="gpt-4o-mini",
            model_name="gpt-4o-mini",
            model_role="shared_llm",
            execution_mode="api",
        )
    ]


def _prices() -> dict[str, APILLMPrice]:
    """返回便于手算的测试价格。"""

    return {
        "gpt-4o-mini": APILLMPrice(
            input_cost_per_million_tokens=Decimal("1"),
            output_cost_per_million_tokens=Decimal("1"),
            currency="USD",
        )
    }


def test_load_ohmygpt_pricing_parses_api_and_skips_local_model() -> None:
    """加载器应强类型解析占位 API 价格，并把本地模型留给 inventory 处理。"""

    prices = load_pricing(Path("configs/pricing/ohmygpt.toml"))

    assert prices == {
        "gpt-4o-mini": APILLMPrice(
            input_cost_per_million_tokens=Decimal("0.0"),
            output_cost_per_million_tokens=Decimal("0.0"),
            currency="USD",
        )
    }
    assert "all-MiniLM-L6-v2" not in prices


def test_load_pricing_fails_fast_on_missing_field(tmp_path: Path) -> None:
    """API 价格缺字段时应立即失败，不能生成不完整价格对象。"""

    path = tmp_path / "broken.toml"
    path.write_text(
        """
[[models]]
model_id = "model"
kind = "llm"
execution_mode = "api"
input_cost_per_million_tokens = 1.0
currency = "USD"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="output_cost_per_million_tokens"):
        load_pricing(path)


def test_build_run_cost_report_merges_prediction_and_evaluator_stores(
    tmp_path: Path,
) -> None:
    """报告应合并 build、answer 与 evaluator judge 成本并读取 config track。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    paths.manifest_path.write_text(
        json.dumps({"method": {"config_track": "native"}}),
        encoding="utf-8",
    )
    EfficiencyArtifactStore.for_prediction(paths).merge_observations(
        [
            _llm_call("build", EfficiencyStage.MEMORY_BUILD, 100),
            _llm_call("answer", EfficiencyStage.ANSWER, 200),
        ]
    )
    EfficiencyArtifactStore.for_evaluator(paths, "judge_accuracy").merge_observations(
        [_llm_call("judge", EfficiencyStage.JUDGE, 300)]
    )

    report = build_run_cost_report(paths.run_dir, _prices(), _api_inventory())

    assert report.total_cost == Decimal("0.0006")
    assert report.cost_by_stage == {
        EfficiencyStage.MEMORY_BUILD: Decimal("0.0001"),
        EfficiencyStage.ANSWER: Decimal("0.0002"),
        EfficiencyStage.JUDGE: Decimal("0.0003"),
    }
    assert report.config_track == "native"
    assert report.complete is True
    assert report.missing_stores == ()


def test_run_cost_report_exposes_mixed_token_source_confidence(tmp_path: Path) -> None:
    """混合真实 usage 与 tokenizer estimate 时应给出 token 数、占比和标注。"""

    paths = ExperimentPaths.create(tmp_path / "run")
    EfficiencyArtifactStore.for_prediction(paths).merge_observations(
        [
            _llm_call("build", EfficiencyStage.MEMORY_BUILD, 100),
            _llm_call(
                "answer",
                EfficiencyStage.ANSWER,
                300,
                MeasurementSource.TOKENIZER_ESTIMATE,
            ),
        ]
    )
    EfficiencyArtifactStore.for_evaluator(paths, "judge").merge_observations(
        [_llm_call("judge", EfficiencyStage.JUDGE, 100)]
    )

    report = build_run_cost_report(paths.run_dir, _prices(), _api_inventory())

    assert report.total_cost == Decimal("0.0005")
    assert report.token_source_mix.api_usage_tokens == 200
    assert report.token_source_mix.tokenizer_estimate_tokens == 300
    assert report.token_source_mix.api_usage_ratio == pytest.approx(0.4)
    assert report.token_source_mix.tokenizer_estimate_ratio == pytest.approx(0.6)
    assert report.token_source_mix.confidence == "contains_tokenizer_estimate"

"""合并 prediction 与 evaluator 效率产物的单次运行成本报告。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import json
from pathlib import Path
from typing import Mapping, Sequence

from memory_benchmark.analysis.cost import APIPrice, CostReport, calculate_cost
from memory_benchmark.analysis.efficiency import EfficiencySummary, aggregate_efficiency
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyObservation,
    EfficiencyStage,
    EmbeddingCallObservation,
    LLMCallObservation,
    MeasurementSource,
    ModelDescriptor,
)
from memory_benchmark.storage.experiment_paths import ExperimentPaths


@dataclass(frozen=True)
class TokenSourceMix:
    """计费调用 token 的计量来源构成与置信标注。"""

    api_usage_tokens: int
    tokenizer_estimate_tokens: int
    other_source_tokens: int
    total_tokens: int
    api_usage_ratio: float | None
    tokenizer_estimate_ratio: float | None
    confidence: str


@dataclass(frozen=True)
class RunCostReport:
    """一次 run 的合并效率与成本结果。

    ``complete`` 同时要求 prediction/evaluator 两类 store 可见且所有 API 模型有
    价格；缺失 store 会列入 ``missing_stores``，避免把未采集角色静默解释为零。
    """

    config_track: str
    total_cost: Decimal
    currency: str | None
    complete: bool
    efficiency_summary: EfficiencySummary
    cost_by_stage: dict[EfficiencyStage, Decimal] = field(default_factory=dict)
    missing_price_model_ids: tuple[str, ...] = ()
    skipped_local_model_ids: tuple[str, ...] = ()
    missing_stores: tuple[str, ...] = ()
    token_source_mix: TokenSourceMix = field(
        default_factory=lambda: TokenSourceMix(0, 0, 0, 0, None, None, "no_tokens")
    )


def build_run_cost_report(
    run_dir: str | Path,
    prices: Mapping[str, APIPrice],
    model_inventory: Sequence[ModelDescriptor],
) -> RunCostReport:
    """合并一次运行的两个效率 store，并生成 fail-loud 离线成本报告。"""

    paths = ExperimentPaths(run_dir=Path(run_dir).resolve())
    observations, missing_stores = _read_all_observations(paths)
    efficiency_summary = aggregate_efficiency(observations)
    cost_report = calculate_cost(
        observations,
        prices,
        model_inventory=model_inventory,
    )
    cost_by_stage = {
        stage: stage_report.total_cost
        for stage in EfficiencyStage
        if (
            stage_report := calculate_cost(
                [
                    observation
                    for observation in observations
                    if getattr(observation, "stage", None) is stage
                ],
                prices,
                model_inventory=model_inventory,
            )
        ).total_cost
        != 0
        or any(getattr(item, "stage", None) is stage for item in observations)
    }
    return RunCostReport(
        config_track=_read_config_track(paths.manifest_path),
        total_cost=cost_report.total_cost,
        currency=cost_report.currency,
        complete=cost_report.complete and not missing_stores,
        efficiency_summary=efficiency_summary,
        cost_by_stage=cost_by_stage,
        missing_price_model_ids=cost_report.missing_price_model_ids,
        skipped_local_model_ids=cost_report.skipped_local_model_ids,
        missing_stores=missing_stores,
        token_source_mix=_build_token_source_mix(observations),
    )


def _build_token_source_mix(
    observations: Sequence[EfficiencyObservation],
) -> TokenSourceMix:
    """按真实 observation 汇总 token 来源，不把 latency 等非 token 记录混入。"""

    tokens_by_source = {source: 0 for source in MeasurementSource}
    for observation in observations:
        if isinstance(observation, LLMCallObservation):
            token_count = observation.input_tokens + observation.output_tokens
        elif isinstance(observation, EmbeddingCallObservation):
            token_count = observation.input_tokens
        else:
            continue
        tokens_by_source[observation.token_measurement_source] += token_count

    api_tokens = tokens_by_source[MeasurementSource.API_USAGE]
    estimate_tokens = tokens_by_source[MeasurementSource.TOKENIZER_ESTIMATE]
    other_tokens = sum(tokens_by_source.values()) - api_tokens - estimate_tokens
    total_tokens = api_tokens + estimate_tokens + other_tokens
    if total_tokens == 0:
        confidence = "no_tokens"
    elif estimate_tokens > 0:
        confidence = "contains_tokenizer_estimate"
    elif other_tokens > 0:
        confidence = "contains_other_source"
    else:
        confidence = "high"
    return TokenSourceMix(
        api_usage_tokens=api_tokens,
        tokenizer_estimate_tokens=estimate_tokens,
        other_source_tokens=other_tokens,
        total_tokens=total_tokens,
        api_usage_ratio=None if total_tokens == 0 else api_tokens / total_tokens,
        tokenizer_estimate_ratio=(
            None if total_tokens == 0 else estimate_tokens / total_tokens
        ),
        confidence=confidence,
    )


def _read_all_observations(
    paths: ExperimentPaths,
) -> tuple[list[EfficiencyObservation], tuple[str, ...]]:
    """经标准 store 读取 prediction 和全部 evaluator observation。"""

    observations: list[EfficiencyObservation] = []
    missing_stores: list[str] = []
    prediction_store = EfficiencyArtifactStore.for_prediction(paths)
    if prediction_store.observations_path.is_file():
        observations.extend(prediction_store.read_observations())
    else:
        missing_stores.append("prediction")

    evaluator_paths = sorted(
        path
        for path in paths.artifacts_dir.glob("efficiency_observations.*.jsonl")
        if path.name != paths.prediction_efficiency_observations_path.name
    )
    if not evaluator_paths:
        missing_stores.append("evaluator")
    for observation_path in evaluator_paths:
        metric_name = observation_path.name.removeprefix(
            "efficiency_observations."
        ).removesuffix(".jsonl")
        observations.extend(
            EfficiencyArtifactStore.for_evaluator(
                paths,
                metric_name,
            ).read_observations()
        )
    return observations, tuple(missing_stores)


def _read_config_track(manifest_path: Path) -> str:
    """从 manifest 读取配置轨；旧 manifest 降级为 unified，缺失或坏文件为 unknown。"""

    if not manifest_path.is_file():
        return "unknown"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return "unknown"
    if not isinstance(manifest, dict):
        return "unknown"
    method = manifest.get("method")
    if not isinstance(method, dict):
        return "unified"
    config_track = method.get("config_track", "unified")
    return config_track if isinstance(config_track, str) and config_track else "unknown"


__all__ = ["RunCostReport", "TokenSourceMix", "build_run_cost_report"]

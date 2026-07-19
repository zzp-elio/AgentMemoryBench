"""artifact-only answer evaluation runner。

本模块只读取标准 artifacts，重建 Question、AnswerResult、GoldAnswerInfo，
并执行单个 answer-level evaluator。它不会构造 method、不会读取 `.env`，
也不会调用任何 prediction 逻辑。

对于带 category 字段的 benchmark，本模块自动计算 overall 与 by-category 聚合。
支持通过 `max_workers` 参数启用多线程并行评测（适用于 LLM Judge 等 API 密集型
evaluator）。
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from memory_benchmark.core import (
    AnswerResult,
    ConfigurationError,
    GoldAnswerInfo,
    Question,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    EfficiencyObservation,
    ModelDescriptor,
)
from memory_benchmark.runners.conversation_qa import BaseAnswerEvaluator
from memory_benchmark.storage import ExperimentPaths, atomic_write_json, atomic_write_jsonl, read_jsonl


# 哨兵：区分 artifact evaluator 完全未声明 `efficiency_observations` 与显式返回空序列。
_MISSING_EFFICIENCY_OBSERVATIONS = object()


@dataclass(frozen=True)
class EvaluationRunSummary:
    """一次 artifact-only 评测的机器可读摘要。"""

    run_id: str
    benchmark_name: str
    metric_name: str
    total_questions: int
    mean_score: float | None
    correct_count: int | None
    score_path: str
    summary_path: str

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化摘要。"""

        return asdict(self)


def run_artifact_evaluation(
    run_dir: str | Path,
    evaluator: BaseAnswerEvaluator,
    expected_benchmark: str,
    max_workers: int = 1,
) -> EvaluationRunSummary:
    """基于标准 artifacts 运行单个 evaluator。

    输入:
        run_dir: 已存在 prediction artifacts 的 run 目录。
        evaluator: 单题 answer-level evaluator。
        expected_benchmark: 命令层期望的 benchmark 名称，用于前置兼容校验。
        max_workers: 并行评测线程数；默认为 1（串行）。LLM Judge 等 API 密集型
            evaluator 可通过增大该值加速。

    输出:
        EvaluationRunSummary: 单个 metric 的路径与聚合结果。
    """

    paths = ExperimentPaths.create(run_dir)
    manifest = _read_json_object(paths.manifest_path, payload_name="manifest")
    benchmark_name = _require_non_empty_string(
        manifest.get("benchmark_name"),
        "manifest benchmark_name",
    )
    if benchmark_name != expected_benchmark:
        raise ConfigurationError(
            f"artifact benchmark mismatch: expected {expected_benchmark}, got {benchmark_name}"
        )
    run_id = _require_non_empty_string(manifest.get("run_id"), "manifest run_id")
    artifact_evaluator = getattr(evaluator, "evaluate_run_artifacts", None)
    if callable(artifact_evaluator):
        return _run_artifact_level_evaluation(
            paths=paths,
            manifest=manifest,
            benchmark_name=benchmark_name,
            run_id=run_id,
            evaluator=evaluator,
            max_workers=max_workers,
        )

    public_records = _read_required_jsonl(
        paths.public_questions_path,
        artifact_name="public_questions",
    )
    prediction_records = _read_required_jsonl(
        paths.method_predictions_path,
        artifact_name="method_predictions",
    )
    private_records = _read_required_jsonl(
        paths.evaluator_private_labels_path,
        artifact_name="evaluator_private_labels",
    )

    public_by_id, ordered_question_ids = _index_records(
        public_records,
        source_path=paths.public_questions_path,
        artifact_name="public_questions",
    )
    prediction_by_id, _ = _index_records(
        prediction_records,
        source_path=paths.method_predictions_path,
        artifact_name="method_predictions",
    )
    private_by_id, _ = _index_records(
        private_records,
        source_path=paths.evaluator_private_labels_path,
        artifact_name="evaluator_private_labels",
    )
    _validate_matching_question_ids(
        public_by_id=public_by_id,
        prediction_by_id=prediction_by_id,
        private_by_id=private_by_id,
    )

    score_records: list[dict[str, Any]] = []
    categories: dict[str, str] = {}  # question_id -> category
    metric_name: str | None = None
    score_sum = 0.0
    correct_values: list[bool] = []
    efficiency_collector = _resolve_evaluator_efficiency_collector(
        evaluator,
        run_id,
    )
    efficiency_observations: list[EfficiencyObservation] = []
    model_inventory: tuple[ModelDescriptor, ...] = ()
    if efficiency_collector is not None and efficiency_collector.enabled:
        if efficiency_collector.run_id != run_id:
            raise ConfigurationError(
                "Evaluator EfficiencyCollector run_id must match manifest run_id"
            )
        model_inventory = _get_evaluator_model_inventory(evaluator)

    ordered_question_ids = [
        qid for qid in ordered_question_ids if qid in prediction_by_id
    ]
    eval_results = _evaluate_questions(
        evaluator=evaluator,
        public_by_id=public_by_id,
        prediction_by_id=prediction_by_id,
        private_by_id=private_by_id,
        ordered_question_ids=ordered_question_ids,
        efficiency_collector=efficiency_collector,
        max_workers=max_workers,
    )

    for result_item in eval_results:
        question_id = result_item["question_id"]
        result_metric_name = result_item["metric_name"]
        if metric_name is None:
            metric_name = result_metric_name
        elif result_metric_name != metric_name:
            raise ConfigurationError(
                "evaluator returned inconsistent metric_name across questions"
            )
        if result_item.get("category") is not None:
            categories[question_id] = result_item["category"]
        score_sum += result_item["score"]
        if result_item["is_correct"] is not None:
            correct_values.append(result_item["is_correct"])
        score_records.append(
            {
                "question_id": question_id,
                "conversation_id": result_item["conversation_id"],
                "metric_name": result_metric_name,
                "score": result_item["score"],
                "is_correct": result_item["is_correct"],
                "details": result_item["details"],
            }
        )
        efficiency_observations.extend(result_item["efficiency_observations"])

    resolved_metric_name = metric_name or getattr(evaluator, "metric_name", None)
    if not resolved_metric_name:
        raise ConfigurationError("evaluator metric_name is required")
    score_path = paths.metric_scores_path(resolved_metric_name)
    summary_path = paths.metric_summary_path(resolved_metric_name)
    total_questions = len(score_records)
    mean_score = score_sum / total_questions if total_questions else 0.0
    correct_count = (
        sum(1 for value in correct_values if value)
        if correct_values
        else None
    )
    summary = EvaluationRunSummary(
        run_id=run_id,
        benchmark_name=benchmark_name,
        metric_name=resolved_metric_name,
        total_questions=total_questions,
        mean_score=mean_score,
        correct_count=correct_count,
        score_path=str(score_path.resolve()),
        summary_path=str(summary_path.resolve()),
    )
    if efficiency_collector is not None and efficiency_collector.enabled:
        efficiency_store = EfficiencyArtifactStore.for_evaluator(
            paths,
            resolved_metric_name,
        )
        efficiency_store.write_model_inventory(model_inventory)
        efficiency_store.merge_observations(efficiency_observations)
    summary_dict = summary.to_dict()
    if categories:
        category_breakdown = _build_category_breakdown(score_records, categories)
        if category_breakdown:
            summary_dict["category_breakdown"] = category_breakdown
    atomic_write_jsonl(score_path, score_records)
    atomic_write_json(summary_path, summary_dict)
    return summary


def _run_artifact_level_evaluation(
    *,
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    benchmark_name: str,
    run_id: str,
    evaluator: BaseAnswerEvaluator,
    max_workers: int,
) -> EvaluationRunSummary:
    """运行自带 artifact 聚合逻辑的 evaluator，并复用普通路径的效率观测契约。

    与普通逐题路径一致：调用 evaluator 之前解析/注入 collector；启用时校验 run_id 并取得
    强类型 model inventory。声明 efficiency support 且 collector enabled 的 evaluator 必须在
    payload 里显式返回 runner-internal 的 `efficiency_observations`（哪怕本次零真实调用而值
    为空），runner 严格校验元素类型后写入 evaluator 专属 store；该字段不进 score/summary。
    未声明 support 的离线 artifact evaluator（collector 为 None）行为与现状字节级一致。
    """

    efficiency_collector = _resolve_evaluator_efficiency_collector(evaluator, run_id)
    collector_enabled = (
        efficiency_collector is not None and efficiency_collector.enabled
    )
    model_inventory: tuple[ModelDescriptor, ...] = ()
    if collector_enabled:
        if efficiency_collector.run_id != run_id:
            raise ConfigurationError(
                "Evaluator EfficiencyCollector run_id must match manifest run_id"
            )
        model_inventory = _get_evaluator_model_inventory(evaluator)

    payload = evaluator.evaluate_run_artifacts(
        paths=paths,
        manifest=manifest,
        max_workers=max_workers,
    )
    if not isinstance(payload, dict):
        raise ConfigurationError("artifact-level evaluator must return a dict")
    efficiency_observations = _extract_artifact_efficiency_observations(
        payload,
        collector_enabled=collector_enabled,
    )
    metric_name = _require_non_empty_string(
        payload.get("metric_name"),
        "artifact evaluator metric_name",
    )
    raw_score_records = payload.get("score_records", [])
    if not isinstance(raw_score_records, list) or any(
        not isinstance(record, dict) for record in raw_score_records
    ):
        raise ConfigurationError("artifact evaluator score_records must be a list")
    score_records = raw_score_records
    score_path = paths.metric_scores_path(metric_name)
    summary_path = paths.metric_summary_path(metric_name)
    total_questions = _non_negative_int_or_default(
        payload.get("total_questions"),
        len(score_records),
        "artifact evaluator total_questions",
    )
    mean_score = _resolve_artifact_mean_score(payload, score_records)
    correct_count = payload.get("correct_count")
    if correct_count is not None:
        correct_count = _non_negative_int_or_default(
            correct_count,
            0,
            "artifact evaluator correct_count",
        )
    summary = EvaluationRunSummary(
        run_id=run_id,
        benchmark_name=benchmark_name,
        metric_name=metric_name,
        total_questions=total_questions,
        mean_score=mean_score,
        correct_count=correct_count,
        score_path=str(score_path.resolve()),
        summary_path=str(summary_path.resolve()),
    )
    summary_dict = summary.to_dict()
    extra_summary = payload.get("summary", {})
    if not isinstance(extra_summary, dict):
        raise ConfigurationError("artifact evaluator summary must be a JSON object")
    summary_dict.update(extra_summary)
    if collector_enabled:
        efficiency_store = EfficiencyArtifactStore.for_evaluator(paths, metric_name)
        efficiency_store.write_model_inventory(model_inventory)
        efficiency_store.merge_observations(efficiency_observations)
    atomic_write_jsonl(score_path, score_records)
    atomic_write_json(summary_path, summary_dict)
    return summary


def _extract_artifact_efficiency_observations(
    payload: dict[str, Any],
    *,
    collector_enabled: bool,
) -> list[EfficiencyObservation]:
    """从 artifact evaluator payload 中取出并校验 runner-internal 效率 observation。

    该字段仅供 runner 内部消费，因此无论 collector 是否启用都从 payload 中剥离，避免泄漏进
    score/summary。collector 启用时必须显式存在且为 `list/tuple[EfficiencyObservation]`，
    缺字段、非序列或含非 observation 元素一律 fail-fast，不得静默当作零调用；collector 未启用
    时忽略该字段并返回空列表。
    """

    raw = payload.pop("efficiency_observations", _MISSING_EFFICIENCY_OBSERVATIONS)
    if not collector_enabled:
        return []
    if raw is _MISSING_EFFICIENCY_OBSERVATIONS:
        raise ConfigurationError(
            "artifact evaluator with enabled efficiency collector must return "
            "efficiency_observations"
        )
    if not isinstance(raw, (list, tuple)):
        raise ConfigurationError(
            "artifact evaluator efficiency_observations must be a list or tuple"
        )
    observations: list[EfficiencyObservation] = []
    for observation in raw:
        if not isinstance(observation, EfficiencyObservation):
            raise ConfigurationError(
                "artifact evaluator efficiency_observations must contain only "
                "EfficiencyObservation instances"
            )
        observations.append(observation)
    return observations


def _evaluate_questions(
    *,
    evaluator: BaseAnswerEvaluator,
    public_by_id: dict[str, dict[str, Any]],
    prediction_by_id: dict[str, dict[str, Any]],
    private_by_id: dict[str, dict[str, Any]],
    ordered_question_ids: list[str],
    efficiency_collector: EfficiencyCollector | None,
    max_workers: int,
) -> list[dict[str, Any]]:
    """按 order_index 排序的问题评测结果列表。

    每项是一个 dict，包含 `_idx`、`question_id`、`metric_name`、`score`、
    `is_correct`、`details`、`category` 和 `efficiency_observations` 字段。
    """
    should_skip_category = getattr(evaluator, "should_skip_category", None)
    question_args = [
        (
            evaluator,
            public_by_id[qid],
            prediction_by_id[qid],
            private_by_id[qid],
            efficiency_collector,
            idx,
        )
        for idx, qid in enumerate(ordered_question_ids)
        if not callable(should_skip_category)
        or not should_skip_category(public_by_id[qid].get("category"))
    ]

    if max_workers <= 1:
        return [_evaluate_one_question(*args) for args in question_args]

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_evaluate_one_question, *args): args[-1]
            for args in question_args
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda r: r["_idx"])
    return results


def _evaluate_one_question(
    evaluator: BaseAnswerEvaluator,
    public_record: dict[str, Any],
    prediction_record: dict[str, Any],
    private_record: dict[str, Any],
    efficiency_collector: EfficiencyCollector | None,
    order_index: int,
) -> dict[str, Any]:
    """评测单个问题，返回带排序索引的结果字典。"""

    question, prediction, gold = _rebuild_entities(
        public_record=public_record,
        prediction_record=prediction_record,
        private_record=private_record,
    )

    if efficiency_collector is not None and efficiency_collector.enabled:
        with efficiency_collector.judge_scope(
            question.conversation_id,
            question.question_id,
        ) as scope:
            metric_result = evaluator.evaluate(question, prediction, gold)
        efficiency_observations = list(scope.records)
    else:
        metric_result = evaluator.evaluate(question, prediction, gold)
        efficiency_observations: list[Any] = []

    return {
        "_idx": order_index,
        "question_id": question.question_id,
        "conversation_id": question.conversation_id,
        "metric_name": metric_result.metric_name,
        "score": metric_result.score,
        "is_correct": metric_result.is_correct,
        "details": metric_result.details,
        "category": question.category,
        "efficiency_observations": efficiency_observations,
    }


def _resolve_evaluator_efficiency_collector(
    evaluator: BaseAnswerEvaluator,
    run_id: str,
) -> EfficiencyCollector | None:
    """读取或自动创建 evaluator 可选 efficiency collector。"""

    collector = getattr(evaluator, "efficiency_collector", None)
    if collector is None:
        if not getattr(evaluator, "supports_efficiency_observability", False):
            return None
        collector = EfficiencyCollector(run_id=run_id, enabled=True)
        setattr(evaluator, "efficiency_collector", collector)
        return collector
    if not getattr(evaluator, "supports_efficiency_observability", False):
        raise ConfigurationError(
            "evaluator defines efficiency_collector but does not declare support"
        )
    if not isinstance(collector, EfficiencyCollector):
        raise ConfigurationError("evaluator efficiency_collector has invalid type")
    return collector


def _get_evaluator_model_inventory(
    evaluator: BaseAnswerEvaluator,
) -> tuple[ModelDescriptor, ...]:
    """读取 evaluator 的模型清单，供 evaluator efficiency artifact 使用。"""

    inventory_factory = getattr(evaluator, "efficiency_model_inventory", None)
    if not callable(inventory_factory):
        raise ConfigurationError(
            "evaluator with efficiency_collector must expose efficiency_model_inventory()"
        )
    inventory = inventory_factory()
    if not isinstance(inventory, tuple) or not all(
        isinstance(descriptor, ModelDescriptor)
        for descriptor in inventory
    ):
        raise ConfigurationError(
            "evaluator efficiency_model_inventory() must return tuple[ModelDescriptor, ...]"
        )
    return inventory


def _read_json_object(path: Path, *, payload_name: str) -> dict[str, Any]:
    """读取并校验 JSON 对象文件。"""

    if not path.exists():
        raise ConfigurationError(f"{payload_name} is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raise ConfigurationError(f"{payload_name} JSON is invalid") from None
    if not isinstance(payload, dict):
        raise ConfigurationError(f"{payload_name} must be a JSON object: {path}")
    return payload


def _read_required_jsonl(
    path: Path,
    *,
    artifact_name: str,
) -> list[dict[str, Any]]:
    """读取评测必需的非空 JSONL，并把底层解析错误转换为领域异常。"""

    if not path.is_file():
        raise ConfigurationError(f"{artifact_name} is missing: {path}")
    try:
        records = read_jsonl(path)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        raise ConfigurationError(
            f"{artifact_name} contains invalid JSONL: {path}"
        ) from exc
    if not records:
        raise ConfigurationError(f"{artifact_name} is empty: {path}")
    return records


def _index_records(
    records: list[dict[str, Any]],
    *,
    source_path: Path,
    artifact_name: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """按 question_id 建立稳定索引，并拒绝任何重复 id。"""

    indexed: dict[str, dict[str, Any]] = {}
    ordered_question_ids: list[str] = []
    for record in records:
        question_id = _require_non_empty_string(
            record.get("question_id"),
            f"{artifact_name} question_id",
        )
        if question_id in indexed:
            raise ConfigurationError(
                f"{artifact_name} has duplicate question_id: {question_id} in {source_path}"
            )
        indexed[question_id] = record
        ordered_question_ids.append(question_id)
    return indexed, ordered_question_ids


def _validate_matching_question_ids(
    *,
    public_by_id: dict[str, dict[str, Any]],
    prediction_by_id: dict[str, dict[str, Any]],
    private_by_id: dict[str, dict[str, Any]],
) -> None:
    """校验 artifacts 的 question id 集合关系：predictions 必须是 public/private 的子集。

    在分批实验（per-command conversation 预算）场景下，predictions 可能只包含部分
    conversation 的 question，此时允许 predictions 为 public/private 的子集。
    public 和 private 仍需完全一致。
    """

    public_ids = set(public_by_id)
    prediction_ids = set(prediction_by_id)
    private_ids = set(private_by_id)
    if public_ids != private_ids:
        raise ConfigurationError("public question and private label id sets do not match")
    if not prediction_ids.issubset(public_ids):
        extra = prediction_ids - public_ids
        raise ConfigurationError(
            f"prediction contains question ids not in public questions: {sorted(extra)}"
        )


def _rebuild_entities(
    *,
    public_record: dict[str, Any],
    prediction_record: dict[str, Any],
    private_record: dict[str, Any],
) -> tuple[Question, AnswerResult, GoldAnswerInfo]:
    """从公开/私有 artifact 记录显式重建核心实体。"""

    question_id = _require_non_empty_string(public_record.get("question_id"), "question_id")
    question_conversation_id = _require_non_empty_string(
        public_record.get("conversation_id"),
        "public question conversation_id",
    )
    prediction_conversation_id = _require_non_empty_string(
        prediction_record.get("conversation_id"),
        "prediction conversation_id",
    )
    if prediction_conversation_id != question_conversation_id:
        raise ConfigurationError(
            f"prediction conversation_id mismatch for {question_id}"
        )
    question_text = _require_non_empty_string(
        public_record.get("question_text"),
        "question_text",
    )
    question_time = public_record.get("question_time")
    if question_time is not None and not isinstance(question_time, str):
        raise ConfigurationError("question_time must be a string or null")
    prediction_answer = _require_prediction_answer(prediction_record.get("answer"))
    gold_answer = _require_non_empty_string(
        private_record.get("gold_answer"),
        "gold_answer",
    )
    question_category = public_record.get("category", private_record.get("category"))
    question = Question(
        question_id=question_id,
        conversation_id=question_conversation_id,
        text=question_text,
        question_time=question_time,
        category=question_category if question_category is None else str(question_category),
        metadata=_coerce_dict(public_record.get("metadata"), "public question metadata"),
    )
    prediction = AnswerResult(
        question_id=question_id,
        conversation_id=prediction_conversation_id,
        answer=prediction_answer,
        metadata=_coerce_dict(prediction_record.get("metadata"), "prediction metadata"),
    )
    gold = GoldAnswerInfo(
        question_id=question_id,
        answer=gold_answer,
        evidence=_coerce_string_list(private_record.get("evidence"), "gold evidence"),
        metadata=_coerce_dict(private_record.get("metadata"), "gold metadata"),
    )
    return question, prediction, gold


def _coerce_dict(value: Any, field_name: str) -> dict[str, Any]:
    """把可选 metadata 校验为 dict。"""

    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigurationError(f"{field_name} must be a JSON object")
    return value


def _coerce_string_list(value: Any, field_name: str) -> list[str]:
    """把可选 evidence 校验为字符串列表。"""

    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigurationError(f"{field_name} must be a list of strings")
    return value


def _build_category_breakdown(
    score_records: list[dict[str, Any]],
    categories: dict[str, str],
) -> list[dict[str, Any]] | None:
    """按 category 分组聚合指标，返回有序 breakdown 列表。

    若所有 question 均无 category，返回 None。
    """

    category_scores: dict[str, list[float]] = defaultdict(list)
    category_correct: dict[str, list[bool]] = defaultdict(list)
    for record in score_records:
        question_id = record["question_id"]
        category = categories.get(question_id)
        if category is None:
            continue
        category_scores[category].append(record["score"])
        if record.get("is_correct") is not None:
            category_correct[category].append(record["is_correct"])

    if not category_scores:
        return None

    breakdown: list[dict[str, Any]] = []
    for category in sorted(category_scores):
        scores = category_scores[category]
        entry: dict[str, Any] = {
            "category": category,
            "question_count": len(scores),
            "mean_score": sum(scores) / len(scores) if scores else 0.0,
        }
        correct_list = category_correct.get(category, [])
        if correct_list:
            entry["correct_count"] = sum(1 for v in correct_list if v)
        breakdown.append(entry)
    return breakdown


def _require_non_empty_string(value: Any, field_name: str) -> str:
    """读取必填非空字符串。"""

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field_name} is required")
    return value


def _require_prediction_answer(value: Any) -> str:
    """读取 prediction answer，并把空字符串错误区分出来。"""

    if not isinstance(value, str):
        raise ConfigurationError("prediction answer is required")
    if not value.strip():
        raise ConfigurationError("prediction answer is empty")
    return value


def _mean_score(score_records: list[dict[str, Any]]) -> float:
    """从 score record 计算默认均值。"""

    scores = [
        record.get("score")
        for record in score_records
        if isinstance(record.get("score"), int | float)
    ]
    return sum(float(score) for score in scores) / len(scores) if scores else 0.0


def _non_negative_int_or_default(
    value: Any,
    default: int,
    field_name: str,
) -> int:
    """读取非负整数，缺省时返回 default。"""

    if value is None:
        return default
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    raise ConfigurationError(f"{field_name} must be a non-negative integer")


def _resolve_artifact_mean_score(
    payload: dict[str, Any],
    score_records: list[dict[str, Any]],
) -> float | None:
    """解析 artifact-level evaluator 的可空 `mean_score`。

    输入:
        payload: `evaluate_run_artifacts` 返回的原始 payload。
        score_records: 该 payload 对应的逐题 score record，仅在 payload 未
            声明 `mean_score` key 时用于向后兼容默认值。

    输出:
        float | None: payload 完全未声明 `mean_score` key 时，按旧行为从
        `score_records` 回算默认值（兼容尚未显式声明该字段的 artifact
        evaluator）；显式声明且值为 `null` 时忠实返回 `None`，不得回退成
        `0.0` 或任何计算默认值；显式声明为数值时必须是有限数，非数值类型
        （含字符串、布尔）与 NaN、正负无穷统一 fail-fast。
    """

    if "mean_score" not in payload:
        return _mean_score(score_records)
    raw_value = payload["mean_score"]
    if raw_value is None:
        return None
    if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
        raise ConfigurationError("artifact evaluator mean_score must be a number or null")
    value = float(raw_value)
    if math.isnan(value) or math.isinf(value):
        raise ConfigurationError("artifact evaluator mean_score must be a finite number")
    return value

"""artifact-only answer evaluation runner。

本模块只读取标准 artifacts，重建 Question、AnswerResult、GoldAnswerInfo，
并执行单个 answer-level evaluator。它不会构造 method、不会读取 `.env`，
也不会调用任何 prediction 逻辑。
"""

from __future__ import annotations

import json
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


@dataclass(frozen=True)
class EvaluationRunSummary:
    """一次 artifact-only 评测的机器可读摘要。"""

    run_id: str
    benchmark_name: str
    metric_name: str
    total_questions: int
    mean_score: float
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
) -> EvaluationRunSummary:
    """基于标准 artifacts 运行单个 evaluator。

    输入:
        run_dir: 已存在 prediction artifacts 的 run 目录。
        evaluator: 单题 answer-level evaluator。
        expected_benchmark: 命令层期望的 benchmark 名称，用于前置兼容校验。

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

    for question_id in ordered_question_ids:
        question, prediction, gold = _rebuild_entities(
            public_record=public_by_id[question_id],
            prediction_record=prediction_by_id[question_id],
            private_record=private_by_id[question_id],
        )
        if efficiency_collector is not None and efficiency_collector.enabled:
            with efficiency_collector.judge_scope(
                question.conversation_id,
                question.question_id,
            ) as scope:
                metric_result = evaluator.evaluate(question, prediction, gold)
            efficiency_observations.extend(scope.records)
        else:
            metric_result = evaluator.evaluate(question, prediction, gold)
        if metric_name is None:
            metric_name = metric_result.metric_name
        elif metric_result.metric_name != metric_name:
            raise ConfigurationError(
                "evaluator returned inconsistent metric_name across questions"
            )
        score_sum += metric_result.score
        if metric_result.is_correct is not None:
            correct_values.append(metric_result.is_correct)
        score_records.append(
            {
                "question_id": question.question_id,
                "conversation_id": question.conversation_id,
                "metric_name": metric_result.metric_name,
                "score": metric_result.score,
                "is_correct": metric_result.is_correct,
                "details": metric_result.details,
            }
        )

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
    atomic_write_jsonl(score_path, score_records)
    atomic_write_json(summary_path, summary.to_dict())
    return summary


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
    """校验三类 artifacts 的 question id 集合完全一致。"""

    public_ids = set(public_by_id)
    prediction_ids = set(prediction_by_id)
    private_ids = set(private_by_id)
    if public_ids != prediction_ids or public_ids != private_ids:
        raise ConfigurationError("artifact question id sets do not match")


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

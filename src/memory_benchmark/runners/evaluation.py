"""统一 Answer-Level 评测运行器 (Evaluation Runner)。

读取预测阶段产出的标准 Artifacts (`public_questions.jsonl`、`method_predictions.jsonl`、
`evaluator_private_labels.jsonl`)，重建强类型领域实体 `(Question, AnswerResult, GoldAnswerInfo)`，
并调用任意实现了 `AnswerEvaluator` 协议的评估器计算单题得分与分类汇总。
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
    UnifiedCapability,
)
from memory_benchmark.evaluators import AnswerEvaluator
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    read_jsonl,
)


@dataclass(frozen=True)
class EvaluationRunSummary:
    """一次 Answer-Level 离线评测的机器可读摘要。"""

    run_id: str
    benchmark_name: str
    metric_name: str
    total_questions: int
    mean_score: float | None
    correct_count: int | None
    score_path: str
    summary_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_artifact_evaluation(
    run_dir: str | Path,
    evaluator: AnswerEvaluator,
    expected_benchmark: str | None = None,
    max_workers: int = 1,
) -> EvaluationRunSummary:
    """基于标准 Artifacts 运行单个 AnswerEvaluator 并输出得分与分类汇总。"""

    paths = ExperimentPaths.create(run_dir)
    manifest = _read_json_object(paths.manifest_path, payload_name="manifest")
    benchmark_name = _require_non_empty_string(
        manifest.get("benchmark_name"),
        "manifest benchmark_name",
    )
    if expected_benchmark is not None and benchmark_name != expected_benchmark:
        raise ConfigurationError(
            f"artifact benchmark mismatch: expected {expected_benchmark}, got {benchmark_name}"
        )
    run_id = _require_non_empty_string(manifest.get("run_id"), "manifest run_id")

    public_records = _read_required_jsonl(
        paths.public_questions_path, artifact_name="public_questions"
    )
    prediction_records = _read_required_jsonl(
        paths.method_predictions_path, artifact_name="method_predictions"
    )
    private_records = _read_required_jsonl(
        paths.evaluator_private_labels_path, artifact_name="evaluator_private_labels"
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

    completed_question_ids = [
        qid for qid in ordered_question_ids if qid in prediction_by_id
    ]
    should_skip_category = getattr(evaluator, "should_skip_category", None)
    eligible_question_ids = [
        qid
        for qid in completed_question_ids
        if not callable(should_skip_category)
        or not should_skip_category(public_by_id[qid].get("category"))
    ]

    eval_results = _evaluate_questions(
        evaluator=evaluator,
        public_by_id=public_by_id,
        prediction_by_id=prediction_by_id,
        private_by_id=private_by_id,
        ordered_question_ids=eligible_question_ids,
        max_workers=max_workers,
    )

    score_records: list[dict[str, Any]] = []
    categories: dict[str, str] = {}
    capabilities: dict[str, str] = {}
    metric_name: str | None = None
    score_sum = 0.0
    correct_values: list[bool] = []

    for result_item in eval_results:
        qid = result_item["question_id"]
        result_metric_name = result_item["metric_name"]
        if metric_name is None:
            metric_name = result_metric_name
        elif result_metric_name != metric_name:
            raise ConfigurationError(
                "evaluator returned inconsistent metric_name across questions"
            )
        score_records.append(
            {
                "question_id": qid,
                "conversation_id": result_item["conversation_id"],
                "metric_name": result_metric_name,
                "score": result_item["score"],
                "is_correct": result_item["is_correct"],
                "category": result_item.get("category"),
                "capability": result_item.get("capability"),
                "details": result_item["details"],
            }
        )
        if result_item["category"] is not None:
            categories[qid] = str(result_item["category"])
        if result_item.get("capability") is not None:
            capabilities[qid] = str(result_item["capability"])
        score_sum += float(result_item["score"])
        if result_item["is_correct"] is not None:
            correct_values.append(bool(result_item["is_correct"]))

    resolved_metric_name = metric_name or getattr(evaluator, "metric_name", None)
    if not isinstance(resolved_metric_name, str) or not resolved_metric_name.strip():
        raise ConfigurationError("evaluator metric_name is required")

    score_path = paths.metric_scores_path(resolved_metric_name)
    summary_path = paths.metric_summary_path(resolved_metric_name)
    total_questions = len(score_records)
    mean_score = score_sum / total_questions if total_questions else 0.0
    correct_count = (
        sum(1 for val in correct_values if val) if correct_values else None
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
    summary_dict = summary.to_dict()
    if categories:
        category_breakdown = _build_category_breakdown(score_records, categories)
        if category_breakdown:
            summary_dict["category_breakdown"] = category_breakdown
    if capabilities:
        capability_breakdown = _build_capability_breakdown(score_records, capabilities)
        if capability_breakdown:
            summary_dict["capability_breakdown"] = capability_breakdown

    atomic_write_jsonl(score_path, score_records)
    atomic_write_json(summary_path, summary_dict)
    return summary


def _evaluate_questions(
    *,
    evaluator: AnswerEvaluator,
    public_by_id: dict[str, dict[str, Any]],
    prediction_by_id: dict[str, dict[str, Any]],
    private_by_id: dict[str, dict[str, Any]],
    ordered_question_ids: list[str],
    max_workers: int,
) -> list[dict[str, Any]]:
    question_args = [
        (
            evaluator,
            public_by_id[qid],
            prediction_by_id[qid],
            private_by_id[qid],
            idx,
        )
        for idx, qid in enumerate(ordered_question_ids)
    ]
    total = len(question_args)
    metric_name = getattr(evaluator, "metric_name", "evaluator")
    if max_workers <= 1:
        results = []
        for completed, args in enumerate(question_args, 1):
            results.append(_evaluate_one_question(*args))
            if completed % 100 == 0 or completed == total:
                print(f"[{metric_name}] Evaluated {completed}/{total} ({completed/total*100:.1f}%) questions...")
        return results

    results = []
    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_evaluate_one_question, *args): args[-1]
            for args in question_args
        }
        for future in as_completed(futures):
            results.append(future.result())
            completed += 1
            if completed % 100 == 0 or completed == total:
                print(f"[{metric_name}] Evaluated {completed}/{total} ({completed/total*100:.1f}%) questions...")
    results.sort(key=lambda r: r["_idx"])
    return results


def _evaluate_one_question(
    evaluator: AnswerEvaluator,
    public_record: dict[str, Any],
    prediction_record: dict[str, Any],
    private_record: dict[str, Any],
    order_index: int,
) -> dict[str, Any]:
    question, prediction, gold = _rebuild_entities(
        public_record=public_record,
        prediction_record=prediction_record,
        private_record=private_record,
    )
    metric_result = evaluator.evaluate(question, prediction, gold)

    if (
        not isinstance(metric_result.score, (int, float))
        or isinstance(metric_result.score, bool)
        or not math.isfinite(float(metric_result.score))
    ):
        raise ConfigurationError("evaluator score must be a finite number")

    return {
        "_idx": order_index,
        "question_id": question.question_id,
        "conversation_id": question.conversation_id,
        "metric_name": metric_result.metric_name,
        "score": float(metric_result.score),
        "is_correct": metric_result.is_correct,
        "details": dict(metric_result.details),
        "category": question.category,
        "capability": (
            question.capability.value
            if hasattr(question.capability, "value")
            else question.capability
        ),
    }


def _rebuild_entities(
    *,
    public_record: dict[str, Any],
    prediction_record: dict[str, Any],
    private_record: dict[str, Any],
) -> tuple[Question, AnswerResult, GoldAnswerInfo]:
    question_id = _require_non_empty_string(
        public_record.get("question_id"), "question_id"
    )
    conversation_id = _require_non_empty_string(
        public_record.get("conversation_id"), "public question conversation_id"
    )
    if prediction_record.get("conversation_id") != conversation_id:
        raise ConfigurationError(
            f"prediction conversation_id mismatch for {question_id}"
        )
    if private_record.get("conversation_id") != conversation_id:
        raise ConfigurationError(
            f"private label conversation_id mismatch for {question_id}"
        )
    question_text = _require_non_empty_string(
        public_record.get("question_text"), "question_text"
    )
    question_time = public_record.get("question_time")
    prediction_answer = str(prediction_record.get("answer") or "")
    gold_answer = _require_non_empty_string(
        private_record.get("gold_answer"), "gold_answer"
    )
    raw_category = public_record.get("category")
    category = (
        str(raw_category).strip()
        if raw_category is not None and str(raw_category).strip()
        else None
    )
    raw_capability = public_record.get("capability")
    capability = (
        str(raw_capability).strip()
        if raw_capability is not None and str(raw_capability).strip()
        else None
    )

    question = Question(
        question_id=question_id,
        conversation_id=conversation_id,
        text=question_text,
        question_time=question_time,
        category=category,
        capability=capability,
        metadata=_ensure_dict(public_record.get("metadata")),
    )
    prediction = AnswerResult(
        conversation_id=conversation_id,
        question_id=question_id,
        answer=prediction_answer,
        metadata=_ensure_dict(prediction_record.get("metadata")),
    )
    gold = GoldAnswerInfo(
        question_id=question_id,
        answer=gold_answer,
        metadata=_ensure_dict(private_record.get("metadata")),
    )
    return question, prediction, gold


def _build_category_breakdown(
    score_records: list[dict[str, Any]],
    categories: dict[str, str],
) -> list[dict[str, Any]]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in score_records:
        qid = record["question_id"]
        if qid in categories:
            by_category[categories[qid]].append(record)

    breakdown: list[dict[str, Any]] = []
    for cat in sorted(by_category):
        records = by_category[cat]
        count = len(records)
        cat_sum = sum(float(r["score"]) for r in records)
        correct_vals = [
            r["is_correct"] for r in records if r["is_correct"] is not None
        ]
        breakdown.append(
            {
                "category": cat,
                "question_count": count,
                "mean_score": cat_sum / count if count else 0.0,
                "correct_count": (
                    sum(1 for v in correct_vals if v) if correct_vals else None
                ),
            }
        )
    return breakdown


def _build_capability_breakdown(
    score_records: list[dict[str, Any]],
    capabilities: dict[str, str],
) -> list[dict[str, Any]]:
    by_cap: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in score_records:
        qid = record["question_id"]
        if qid in capabilities:
            by_cap[capabilities[qid]].append(record)

    breakdown: list[dict[str, Any]] = []
    for cap_key in sorted(by_cap):
        records = by_cap[cap_key]
        count = len(records)
        cap_sum = sum(float(r["score"]) for r in records)
        correct_vals = [
            r["is_correct"] for r in records if r["is_correct"] is not None
        ]
        human_review_count = sum(
            1
            for r in records
            if isinstance(r.get("details"), dict)
            and (
                r["details"].get("human_review_required") is True
                or r["details"].get("needs_human_review") is True
                or r["details"].get("verdict") == "UNDECIDABLE"
                or r["details"].get("judgment") == "UNDECIDABLE"
            )
        )

        label_zh = cap_key
        layer = "Unknown"
        try:
            uc = UnifiedCapability(cap_key)
            label_zh = uc.label_zh
            layer = uc.layer
        except (ValueError, KeyError):
            pass

        breakdown.append(
            {
                "capability": cap_key,
                "label_zh": label_zh,
                "layer": layer,
                "question_count": count,
                "mean_score": round(cap_sum / count, 4) if count else 0.0,
                "correct_count": (
                    sum(1 for v in correct_vals if v) if correct_vals else None
                ),
                "human_review_count": human_review_count,
            }
        )
    return breakdown


def _read_json_object(path: Path, *, payload_name: str) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(f"{payload_name} is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"{payload_name} JSON is invalid") from exc
    if not isinstance(payload, dict):
        raise ConfigurationError(f"{payload_name} must be a JSON object: {path}")
    return payload


def _read_required_jsonl(path: Path, *, artifact_name: str) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ConfigurationError(f"{artifact_name} is missing: {path}")
    records = read_jsonl(path)
    if not records:
        raise ConfigurationError(f"{artifact_name} is empty: {path}")
    return records


def _index_records(
    records: list[dict[str, Any]],
    *,
    source_path: Path,
    artifact_name: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    for record in records:
        qid = _require_non_empty_string(
            record.get("question_id"), f"{artifact_name} question_id"
        )
        if qid in indexed:
            raise ConfigurationError(
                f"{artifact_name} has duplicate question_id: {qid} in {source_path}"
            )
        indexed[qid] = record
        ordered_ids.append(qid)
    return indexed, ordered_ids


def _validate_matching_question_ids(
    *,
    public_by_id: dict[str, dict[str, Any]],
    prediction_by_id: dict[str, dict[str, Any]],
    private_by_id: dict[str, dict[str, Any]],
) -> None:
    public_ids = set(public_by_id)
    prediction_ids = set(prediction_by_id)
    private_ids = set(private_by_id)
    if public_ids != private_ids:
        raise ConfigurationError(
            "public question and private label id sets do not match"
        )
    if not prediction_ids.issubset(public_ids):
        extra = prediction_ids - public_ids
        raise ConfigurationError(
            f"prediction contains question ids not in public questions: {sorted(extra)}"
        )


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field_name} is required")
    return value


def _ensure_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigurationError("artifact metadata must be a JSON object")
    return dict(value)


__all__ = ["EvaluationRunSummary", "run_artifact_evaluation"]

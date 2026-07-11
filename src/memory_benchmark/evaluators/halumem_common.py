"""HaluMem judge evaluator 共享工具。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError, JudgeOutputError
from memory_benchmark.evaluators.llm_judge import LLMJudgeEvaluator
from memory_benchmark.storage import ExperimentPaths, read_jsonl


HALUMEM_JUDGE_PROFILE_NOTE = (
    "HaluMem official paper used gpt-4o; this project uses gpt-4o-mini by policy."
)


class HalumemJudgeEvaluatorBase(LLMJudgeEvaluator):
    """HaluMem artifact-level judge evaluator 基类。"""

    benchmark_name = "HaluMem"

    @property
    def client(self) -> Any | None:
        """返回测试注入的 fake client。"""

        return self._client

    def _judge_json(self, prompt: str) -> dict[str, Any]:
        """调用 fake/真实 judge 并解析 JSON 对象。"""

        if self._client is not None and hasattr(self._client, "judge_json"):
            payload = self._client.judge_json(prompt)
            if not isinstance(payload, dict):
                raise JudgeOutputError("fake HaluMem judge must return a dict")
            return payload
        model_response = self._call_model_with_usage(prompt)
        self._record_judge_llm_call(model_response)
        return _parse_json_object(model_response.text)


def read_required_jsonl(path: Path, artifact_name: str) -> list[dict[str, Any]]:
    """读取非空 JSONL artifact。"""

    if not path.is_file():
        raise ConfigurationError(f"{artifact_name} is missing: {path}")
    rows = read_jsonl(path)
    if not rows:
        raise ConfigurationError(f"{artifact_name} is empty: {path}")
    if any(not isinstance(row, dict) for row in rows):
        raise ConfigurationError(f"{artifact_name} rows must be JSON objects")
    return rows


def read_jsonl_or_empty(path: Path, artifact_name: str) -> list[dict[str, Any]]:
    """读取允许为空的 JSONL artifact。"""

    if not path.is_file():
        return []
    rows = read_jsonl(path)
    if any(not isinstance(row, dict) for row in rows):
        raise ConfigurationError(f"{artifact_name} rows must be JSON objects")
    return rows


def read_session_labels(paths: ExperimentPaths) -> list[dict[str, Any]]:
    """读取 HaluMem session 级 evaluator 私有标签。"""

    return read_required_jsonl(
        paths.evaluator_private_session_labels_path,
        "evaluator_private_session_labels",
    )


def session_key_from_ref(record: dict[str, Any]) -> str:
    """从 artifact record 的 session_ref 里取 session_id。"""

    session_ref = record.get("session_ref")
    if not isinstance(session_ref, dict):
        raise ConfigurationError("session_ref must be a JSON object")
    session_id = session_ref.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ConfigurationError("session_ref.session_id is required")
    return session_id


def index_session_labels(
    session_labels: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """按 session_id 索引 session 私有标签。"""

    indexed: dict[str, dict[str, Any]] = {}
    for label in session_labels:
        session_id = _required_text(label.get("session_id"), "session_id")
        if session_id in indexed:
            raise ConfigurationError(f"duplicate HaluMem session label: {session_id}")
        indexed[session_id] = label
    return indexed


def memory_points_by_index(
    session_label: dict[str, Any],
) -> dict[Any, dict[str, Any]]:
    """按 gold memory index 索引一个 session 的 memory_points。"""

    memory_points = session_label.get("memory_points")
    if not isinstance(memory_points, list):
        raise ConfigurationError("session memory_points must be a list")
    indexed: dict[Any, dict[str, Any]] = {}
    for memory_point in memory_points:
        if not isinstance(memory_point, dict):
            continue
        indexed[memory_point.get("index")] = memory_point
    return indexed


def build_halumem_dialogue_str(session_label: dict[str, Any]) -> str:
    """按 `evaluation.py:74-81` 构造 accuracy judge dialogue_str。"""

    dialogue = session_label.get("dialogue")
    if not isinstance(dialogue, list):
        raise ConfigurationError("session dialogue must be a list")
    lines: list[str] = []
    for turn in dialogue:
        if not isinstance(turn, dict):
            continue
        timestamp = turn.get("timestamp", turn.get("turn_time"))
        role = turn.get("role", turn.get("speaker"))
        content = turn.get("content")
        lines.append(f"[{timestamp}]{role}: {content}")
        if role == "assistant":
            lines.append("")
    return "\n".join(lines)


def build_halumem_golden_memories_str(session_label: dict[str, Any]) -> str:
    """按 `evaluation.py:83-85` 拼接非 interference gold memory。"""

    memory_points = session_label.get("memory_points")
    if not isinstance(memory_points, list):
        return ""
    return "\n".join(
        str(memory_point.get("memory_content"))
        for memory_point in memory_points
        if isinstance(memory_point, dict)
        and memory_point.get("memory_source") != "interference"
        and isinstance(memory_point.get("memory_content"), str)
    )


def compute_f1(precision: float | None, recall: float | None) -> float | None:
    """按 `evaluation.py:8-18` 计算 F1。"""

    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def safe_div(numerator: float, denominator: float) -> float | None:
    """除数为 0 时返回 None，保留空分母语义。"""

    return numerator / denominator if denominator else None


def count_ratios(
    records: list[dict[str, Any]],
    *,
    field: str,
    labels: tuple[str, ...],
    output_prefix: str,
    count_name: str,
) -> dict[str, Any]:
    """按官方 all/valid 口径统计分类比例。"""

    counts = {label: 0 for label in labels}
    total = len(records)
    valid = 0
    for record in records:
        value = record.get(field)
        if value not in counts:
            continue
        counts[value] += 1
        valid += 1
    result: dict[str, Any] = {}
    for label in labels:
        key = label.lower()
        result[f"{key}_{output_prefix}_ratio(all)"] = safe_div(counts[label], total)
        result[f"{key}_{output_prefix}_ratio(valid)"] = safe_div(counts[label], valid)
    result[f"{count_name}_valid_num"] = valid
    result[f"{count_name}_num"] = total
    return result


def grouped_mean(
    records: list[dict[str, Any]],
    *,
    category_field: str,
    score_field: str,
    output_score_name: str,
    output_count_name: str,
) -> list[dict[str, Any]]:
    """按分类计算均值 breakdown。"""

    grouped: dict[str, list[float]] = defaultdict(list)
    for record in records:
        category = record.get(category_field)
        score = record.get(score_field)
        if category is None or not isinstance(score, int | float):
            continue
        grouped[str(category)].append(float(score))
    return [
        {
            "category": category,
            output_score_name: safe_div(sum(scores), len(scores)),
            output_count_name: len(scores),
        }
        for category, scores in sorted(grouped.items())
    ]


def _parse_json_object(text: str) -> dict[str, Any]:
    """解析 judge JSON，兼容 ```json fenced block。"""

    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise JudgeOutputError("HaluMem judge output must be JSON") from exc
    if not isinstance(payload, dict):
        raise JudgeOutputError("HaluMem judge output must be a JSON object")
    return payload


def _required_text(value: Any, field_name: str) -> str:
    """读取必填字符串。"""

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{field_name} is required")
    return value

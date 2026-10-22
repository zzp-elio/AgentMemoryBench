"""实验运行上下文 (`RunContext`) 与标准产物路径 (`ExperimentPaths`) 定义。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re

from memory_benchmark.core import ConfigurationError

_SAFE_METRIC_PATH_PATTERN = re.compile(r"^[a-z0-9_.-]+$")


@dataclass(frozen=True)
class RunContext:
    """描述一次评测运行的公开上下文与目录根路径。"""

    run_id: str
    benchmark_name: str
    method_name: str
    model_name: str
    output_root: Path
    started_at: str

    @classmethod
    def create(
        cls,
        run_id: str,
        benchmark_name: str,
        method_name: str,
        model_name: str,
        output_root: str | Path,
        ensure_directories: bool = True,
    ) -> "RunContext":
        """创建运行上下文并确保标准输出子目录存在。"""
        context = cls(
            run_id=run_id,
            benchmark_name=benchmark_name,
            method_name=method_name,
            model_name=model_name,
            output_root=Path(output_root).expanduser().resolve(),
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        if ensure_directories:
            ExperimentPaths.create(context.run_dir)
        return context

    @property
    def run_dir(self) -> Path:
        return self.output_root / self.run_id


@dataclass(frozen=True)
class ExperimentPaths:
    """一次评测运行的标准输出路径集合。"""

    run_dir: Path

    @classmethod
    def create(cls, run_dir: str | Path) -> "ExperimentPaths":
        """创建标准目录布局并返回路径集合。"""
        resolved_run_dir = Path(run_dir).resolve()
        paths = cls(run_dir=resolved_run_dir)
        for directory in (
            paths.artifacts_dir,
            paths.logs_dir,
            paths.checkpoints_dir,
            paths.summaries_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return paths

    @property
    def artifacts_dir(self) -> Path:
        return self.run_dir / "artifacts"

    @property
    def logs_dir(self) -> Path:
        return self.run_dir / "logs"

    @property
    def checkpoints_dir(self) -> Path:
        return self.run_dir / "checkpoints"

    @property
    def summaries_dir(self) -> Path:
        return self.run_dir / "summaries"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    @property
    def public_questions_path(self) -> Path:
        return self.artifacts_dir / "public_questions.jsonl"

    @property
    def method_predictions_path(self) -> Path:
        return self.artifacts_dir / "method_predictions.jsonl"

    @property
    def answer_prompts_path(self) -> Path:
        return self.artifacts_dir / "answer_prompts.prediction.jsonl"

    @property
    def evaluator_private_labels_path(self) -> Path:
        return self.artifacts_dir / "evaluator_private_labels.jsonl"

    @property
    def conversation_status_path(self) -> Path:
        return self.checkpoints_dir / "conversation_status.json"

    @property
    def summary_path(self) -> Path:
        return self.summaries_dir / "summary.json"

    def metric_scores_path(self, metric_name: str) -> Path:
        safe = _safe_metric_path_component(metric_name)
        return self.artifacts_dir / f"answer_scores.{safe}.jsonl"

    def metric_summary_path(self, metric_name: str) -> Path:
        safe = _safe_metric_path_component(metric_name)
        return self.summaries_dir / f"summary.{safe}.json"


def _safe_metric_path_component(metric_name: str) -> str:
    if not isinstance(metric_name, str) or not metric_name:
        raise ConfigurationError("metric_name is required for artifact paths")
    if not _SAFE_METRIC_PATH_PATTERN.fullmatch(metric_name):
        raise ConfigurationError(
            "metric_name may only contain lowercase letters, digits, dot, underscore and dash"
        )
    return metric_name


__all__ = ["ExperimentPaths", "RunContext"]

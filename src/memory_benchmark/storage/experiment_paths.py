"""实验运行产物的标准路径定义。

本模块只负责创建和派生 run 目录下的稳定文件路径，不负责写入文件内容。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from memory_benchmark.core import ConfigurationError


_SAFE_METRIC_PATH_PATTERN = re.compile(r"^[a-z0-9_.-]+$")


@dataclass(frozen=True)
class ExperimentPaths:
    """一次实验运行的标准输出路径集合。

    参数:
        run_dir: 单次实验运行的根目录，构造时建议使用 `create()` 统一创建子目录。
    """

    run_dir: Path

    @classmethod
    def create(cls, run_dir: str | Path) -> "ExperimentPaths":
        """创建标准目录布局并返回路径集合。

        输入:
            run_dir: 运行根目录；会被解析为绝对路径。

        输出:
            ExperimentPaths: 已确保核心子目录存在的冻结路径对象。
        """

        resolved_run_dir = Path(run_dir).resolve()
        paths = cls(run_dir=resolved_run_dir)
        for directory in (
            paths.artifacts_dir,
            paths.logs_dir,
            paths.checkpoints_dir,
            paths.ingest_turn_checkpoints_dir,
            paths.summaries_dir,
            paths.method_state_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        return paths

    @property
    def artifacts_dir(self) -> Path:
        """返回公开和私有评测产物目录。"""

        return self.run_dir / "artifacts"

    @property
    def logs_dir(self) -> Path:
        """返回结构化事件和文本日志目录。"""

        return self.run_dir / "logs"

    @property
    def checkpoints_dir(self) -> Path:
        """返回断点续跑状态目录。"""

        return self.run_dir / "checkpoints"

    @property
    def ingest_turn_checkpoints_dir(self) -> Path:
        """返回按 conversation 隔离的逐 turn 写入断点目录。"""

        return self.checkpoints_dir / "ingest_turns"

    @property
    def summaries_dir(self) -> Path:
        """返回实验摘要输出目录。"""

        return self.run_dir / "summaries"

    @property
    def method_state_dir(self) -> Path:
        """返回 method 自有状态隔离目录。"""

        return self.run_dir / "method_state"

    @property
    def manifest_path(self) -> Path:
        """返回实验 manifest 文件路径。"""

        return self.run_dir / "manifest.json"

    @property
    def redacted_config_path(self) -> Path:
        """返回脱敏配置快照文件路径。"""

        return self.run_dir / "config.redacted.json"

    @property
    def dataset_fingerprint_path(self) -> Path:
        """返回数据集指纹文件路径。"""

        return self.artifacts_dir / "dataset_fingerprint.json"

    @property
    def public_questions_path(self) -> Path:
        """返回 method 可见公开问题 JSONL 路径。"""

        return self.artifacts_dir / "public_questions.jsonl"

    @property
    def method_predictions_path(self) -> Path:
        """返回 method 预测答案 JSONL 路径。"""

        return self.artifacts_dir / "method_predictions.jsonl"

    @property
    def evaluator_private_labels_path(self) -> Path:
        """返回 evaluator-only 私有标签 JSONL 路径。"""

        return self.artifacts_dir / "evaluator_private_labels.jsonl"

    @property
    def prediction_model_inventory_path(self) -> Path:
        """返回 prediction 阶段模型清单路径。"""

        return self.artifacts_dir / "model_inventory.prediction.json"

    @property
    def prediction_efficiency_observations_path(self) -> Path:
        """返回 prediction 阶段效率 observation JSONL 路径。"""

        return self.artifacts_dir / "efficiency_observations.prediction.jsonl"

    def evaluator_model_inventory_path(self, metric_name: str) -> Path:
        """返回指定 evaluator 的独立模型清单路径。"""

        safe_metric_name = _safe_evaluator_efficiency_path_component(metric_name)
        return self.artifacts_dir / f"model_inventory.{safe_metric_name}.json"

    def evaluator_efficiency_observations_path(self, metric_name: str) -> Path:
        """返回指定 evaluator 的独立效率 observation JSONL 路径。"""

        safe_metric_name = _safe_evaluator_efficiency_path_component(metric_name)
        return self.artifacts_dir / (
            f"efficiency_observations.{safe_metric_name}.jsonl"
        )

    @property
    def locomo_f1_scores_path(self) -> Path:
        """返回 LoCoMo F1 明细分数 JSONL 路径。"""

        return self.metric_scores_path("locomo_f1")

    def metric_scores_path(self, metric_name: str) -> Path:
        """返回指定 metric 的分数 JSONL 路径。"""

        safe_metric_name = _safe_metric_path_component(metric_name)
        return self.artifacts_dir / f"answer_scores.{safe_metric_name}.jsonl"

    def metric_summary_path(self, metric_name: str) -> Path:
        """返回指定 metric 的 JSON 摘要路径。"""

        safe_metric_name = _safe_metric_path_component(metric_name)
        return self.summaries_dir / f"summary.{safe_metric_name}.json"

    @property
    def conversation_status_path(self) -> Path:
        """返回 conversation 级断点状态文件路径。"""

        return self.checkpoints_dir / "conversation_status.json"

    @property
    def legacy_conversation_status_jsonl_path(self) -> Path:
        """返回旧版 conversation 状态 JSONL 命名路径，用于 resume 迁移。"""

        return self.checkpoints_dir / "conversation_status.jsonl"

    @property
    def question_status_path(self) -> Path:
        """返回 question 级断点状态文件路径。"""

        return self.checkpoints_dir / "question_status.jsonl"

    @property
    def progress_path(self) -> Path:
        """返回运行进度快照文件路径。"""

        return self.checkpoints_dir / "progress.json"

    @property
    def summary_path(self) -> Path:
        """返回机器可读 JSON 摘要路径。"""

        return self.summaries_dir / "summary.json"

    @property
    def summary_markdown_path(self) -> Path:
        """返回人类可读 Markdown 摘要路径。"""

        return self.summaries_dir / "summary.md"


def _safe_metric_path_component(metric_name: str) -> str:
    """校验 metric 文件名片段，阻止路径逃逸。"""

    if not isinstance(metric_name, str) or not metric_name:
        raise ConfigurationError("metric_name is required for artifact paths")
    if not _SAFE_METRIC_PATH_PATTERN.fullmatch(metric_name):
        raise ConfigurationError(
            "metric_name may only contain lowercase letters, digits, dot, underscore and dash"
        )
    return metric_name


def _safe_evaluator_efficiency_path_component(metric_name: str) -> str:
    """校验 evaluator efficiency 路径，并拒绝 prediction 保留名称。"""

    safe_metric_name = _safe_metric_path_component(metric_name)
    if safe_metric_name == "prediction":
        raise ConfigurationError(
            "metric_name 'prediction' is reserved for prediction efficiency artifacts"
        )
    return safe_metric_name

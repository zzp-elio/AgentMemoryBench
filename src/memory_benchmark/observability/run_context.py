"""运行上下文与标准输出目录定义。

本模块为一次 benchmark run 生成稳定的目录布局，后续 runner 可通过同一个
RunContext 写入日志、产物、checkpoint、summary 和 method 状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RunContext:
    """描述一次 benchmark 运行的公开上下文。

    字段:
        run_id: 本次运行的唯一标识，会作为输出根目录下的子目录名。
        benchmark_name: benchmark 名称，例如 `locomo`。
        method_name: method 名称，例如 `MemoryOS`。
        model_name: method 使用的模型名称。
        output_root: 输出根目录，通常是项目下的 `outputs/`。
        resume: 是否允许复用已有 run 目录继续运行。
        started_at: 创建上下文时的 UTC ISO 时间戳。
    """

    run_id: str
    benchmark_name: str
    method_name: str
    model_name: str
    output_root: Path
    resume: bool
    started_at: str

    @classmethod
    def create(
        cls,
        run_id: str,
        benchmark_name: str,
        method_name: str,
        model_name: str,
        output_root: str | Path,
        resume: bool = False,
        ensure_directories: bool = True,
    ) -> "RunContext":
        """创建运行上下文并确保标准目录存在。

        输入:
            run_id: 本次运行 id。
            benchmark_name: benchmark 名称。
            method_name: method 名称。
            model_name: 模型名称。
            output_root: 输出根目录，可传字符串或 Path。
            resume: 是否以断点续跑模式使用该目录。
            ensure_directories: 是否立即创建标准目录；resume 预检可关闭以避免副作用。

        输出:
            RunContext: 已创建目录后的不可变上下文对象。
        """

        context = cls(
            run_id=run_id,
            benchmark_name=benchmark_name,
            method_name=method_name,
            model_name=model_name,
            output_root=Path(output_root).expanduser().resolve(),
            resume=resume,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        if ensure_directories:
            context.ensure_directories()
        return context

    @property
    def run_dir(self) -> Path:
        """返回本次运行目录。

        输出:
            Path: `output_root / run_id`。
        """

        return self.output_root / self.run_id

    @property
    def logs_dir(self) -> Path:
        """返回日志目录。

        输出:
            Path: `run_dir / "logs"`。
        """

        return self.run_dir / "logs"

    @property
    def artifacts_dir(self) -> Path:
        """返回产物目录。

        输出:
            Path: `run_dir / "artifacts"`。
        """

        return self.run_dir / "artifacts"

    @property
    def checkpoints_dir(self) -> Path:
        """返回 checkpoint 目录。

        输出:
            Path: `run_dir / "checkpoints"`。
        """

        return self.run_dir / "checkpoints"

    @property
    def summaries_dir(self) -> Path:
        """返回摘要目录。

        输出:
            Path: `run_dir / "summaries"`。
        """

        return self.run_dir / "summaries"

    @property
    def method_state_dir(self) -> Path:
        """返回 method 私有状态目录。

        输出:
            Path: `run_dir / "method_state"`。
        """

        return self.run_dir / "method_state"

    def ensure_directories(self) -> None:
        """创建本次运行需要的所有标准目录。

        输入:
            无，目录路径来自当前 RunContext。

        输出:
            None；调用后标准目录均存在。
        """

        for directory in (
            self.logs_dir,
            self.artifacts_dir,
            self.checkpoints_dir,
            self.summaries_dir,
            self.method_state_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

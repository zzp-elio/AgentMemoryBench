"""benchmark adapter 基类。

adapter 负责读取原始 benchmark 数据，并转换成 conversation-QA v2 Dataset。
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from memory_benchmark.core import Dataset
from memory_benchmark.core.exceptions import DatasetNotFoundError
from memory_benchmark.core.validators import validate_dataset, validate_no_private_keys


class BenchmarkAdapter(ABC):
    """所有 benchmark adapter 的基类。"""

    name: str

    def __init__(self, project_root: str | Path):
        """初始化 adapter。

        输入:
            project_root: 项目根目录路径，可以是字符串或 Path。

        输出:
            None。初始化后 adapter 可用 `self.path()` 定位文件。
        """

        self.project_root = Path(project_root)

    def path(self, *parts: str) -> Path:
        """拼接项目内路径。

        输入:
            *parts: 相对项目根目录的路径片段。

        输出:
            Path: 拼接后的路径。
        """

        return self.project_root.joinpath(*parts)

    def require_path(self, *parts: str) -> Path:
        """检查项目内路径必须存在。

        输入:
            *parts: 相对项目根目录的路径片段。

        输出:
            Path: 已确认存在的路径。

        异常:
            DatasetNotFoundError: 路径不存在时抛出领域异常。
        """

        path = self.path(*parts)
        if not path.exists():
            raise DatasetNotFoundError(self.name, "/".join(parts))
        return path

    def load_json(self, *parts: str) -> Any:
        """读取 JSON 文件。

        输入:
            *parts: 相对项目根目录的 JSON 文件路径片段。

        输出:
            Any: `json.load()` 解析出的 Python 对象。
        """

        with self.require_path(*parts).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def load(self, limit: int | None = None) -> Dataset:
        """读取、转换并校验 Dataset。

        输入:
            limit: 最多读取多少个 conversation；None 表示不限制。

        输出:
            Dataset: 已通过通用校验和 adapter 自定义校验的数据集。
        """

        dataset = self.load_dataset(limit=limit)
        validate_dataset(dataset)
        for conversation in dataset.conversations:
            validate_no_private_keys(conversation.to_public_dict())
        self.validate_benchmark_rules(dataset)
        return dataset

    @abstractmethod
    def load_dataset(self, limit: int | None = None) -> Dataset:
        """读取并转换为统一 Dataset。

        输入:
            limit: 最多读取多少个 conversation；None 表示不限制。

        输出:
            Dataset: 未必已校验的统一数据集，由 `load()` 负责校验。
        """

        raise NotImplementedError

    def validate_benchmark_rules(self, dataset: Dataset) -> None:
        """benchmark-specific 校验 hook，默认无额外校验。

        输入:
            dataset: 已通过通用校验的数据集。

        输出:
            None。子类发现 benchmark-specific 问题时应抛领域异常。
        """


def reached_limit(count: int, limit: int | None) -> bool:
    """判断是否达到读取上限。

    输入:
        count: 已经产出的 conversation 数。
        limit: 用户指定上限；None 表示无限制。

    输出:
        bool: 达到上限时返回 True。
    """

    return limit is not None and count >= limit


def sorted_json_files(path: Path) -> list[Path]:
    """返回目录下按文件名排序的 JSON 文件。

    输入:
        path: 要扫描的目录。

    输出:
        list[Path]: 只包含普通 `.json` 文件的排序列表。
    """

    return sorted(file for file in path.glob("*.json") if file.is_file())

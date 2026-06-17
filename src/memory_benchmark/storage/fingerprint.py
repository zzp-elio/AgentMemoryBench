"""数据集来源指纹工具。

本模块生成完整规范化 Dataset 内容 hash，并记录源文件和问题规模。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from memory_benchmark.core import Dataset


SOURCE_HASH_CHUNK_SIZE = 1024 * 1024


def build_dataset_fingerprint(dataset: Dataset, source_paths: list[Path]) -> dict[str, Any]:
    """构建数据集内容、规模和源文件指纹。

    输入:
        dataset: 已加载的 conversation-QA 数据集。
        source_paths: 原始数据或配置文件路径列表，缺失文件也会被记录。

    输出:
        dict[str, Any]: 包含完整 Dataset 内容 hash、规模和源文件指纹。
    """

    canonical_dataset = json.dumps(
        dataset.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    source_fingerprints = [
        _source_path_fingerprint(path) for path in source_paths
    ]
    canonical_source_fingerprints = json.dumps(
        source_fingerprints,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "dataset_name": dataset.dataset_name,
        "conversation_count": len(dataset.conversations),
        "question_count": sum(
            len(conversation.questions) for conversation in dataset.conversations
        ),
        "dataset_sha256": hashlib.sha256(canonical_dataset).hexdigest(),
        "source_fingerprint_sha256": hashlib.sha256(
            canonical_source_fingerprints
        ).hexdigest(),
        "source_paths": source_fingerprints,
    }


def _source_path_fingerprint(path: Path) -> dict[str, Any]:
    """返回单个源路径的大小和 sha256。

    输入:
        path: 待记录的源路径。

    输出:
        dict[str, Any]: 文件缺失时 size_bytes 和 sha256 均为 None。
    """

    source_path = Path(path)
    if not source_path.exists():
        return {"path": str(source_path), "size_bytes": None, "sha256": None}

    digest = hashlib.sha256()
    size_bytes = 0
    with source_path.open("rb") as source_file:
        while chunk := source_file.read(SOURCE_HASH_CHUNK_SIZE):
            digest.update(chunk)
            size_bytes += len(chunk)
    return {
        "path": str(source_path),
        "size_bytes": size_bytes,
        "sha256": digest.hexdigest(),
    }

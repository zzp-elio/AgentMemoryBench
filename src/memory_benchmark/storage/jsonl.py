"""JSONL 文件读写工具。

本模块提供最小追加写入和读取能力，供 runner 保存可审计的逐行记录。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlWriter:
    """追加写入 JSONL 记录。

    参数:
        path: 目标 JSONL 文件路径；构造时会自动创建父目录。
    """

    def __init__(self, path: str | Path):
        """初始化写入器并创建父目录。

        输入:
            path: 字符串或 Path，指向目标 JSONL 文件。

        输出:
            None；后续调用 `append()` 会向该文件追加一行 JSON。
        """

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        """追加一条 JSON 可序列化记录。

        输入:
            record: 单条结构化记录。

        输出:
            None；记录会以 UTF-8 和 `ensure_ascii=False` 写成一行。
        """

        with self.path.open("a", encoding="utf-8") as jsonl_file:
            jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(
    path: str | Path,
    *,
    recover_torn_tail: bool = False,
) -> list[dict[str, Any]]:
    """读取 JSONL 文件中的非空对象记录。

    输入:
        path: JSONL 文件路径；文件不存在时返回空列表。
        recover_torn_tail: 是否丢弃无行终止符且 JSON 损坏的最后一个非空物理行。
            默认关闭；仅适合 append-only 文件在崩溃恢复时显式启用。

    输出:
        list[dict[str, Any]]: 按文件顺序解析出的 JSON 对象列表。

    异常:
        json.JSONDecodeError: 中间行、已带行终止符的尾行或严格模式下存在坏 JSON。
        ValueError: 某条合法 JSON 记录不是对象。
    """

    jsonl_path = Path(path)
    if not jsonl_path.exists():
        return []

    lines = jsonl_path.read_text(encoding="utf-8").splitlines(keepends=True)
    non_empty_line_indexes = [
        index for index, line in enumerate(lines) if line.strip()
    ]
    last_non_empty_line_index = (
        non_empty_line_indexes[-1] if non_empty_line_indexes else None
    )

    records: list[dict[str, Any]] = []
    for line_index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            is_recoverable_tail = (
                recover_torn_tail
                and line_index == last_non_empty_line_index
                and not line.endswith(("\n", "\r"))
            )
            if is_recoverable_tail:
                break
            raise
        if not isinstance(record, dict):
            raise ValueError(
                f"JSONL record must be a JSON object: "
                f"{jsonl_path} line {line_index + 1}"
            )
        records.append(record)
    return records

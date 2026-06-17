"""JSON 和 JSONL 文件的原子覆盖写入工具。

本模块通过同目录临时文件、文件同步和原子替换，避免长实验在写入中断时
留下截断的目标文件。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, TextIO


def atomic_write_json(path: str | Path, payload: Any) -> None:
    """原子覆盖写入一个缩进 JSON 文件。

    输入:
        path: 目标文件路径；函数会自动创建父目录。
        payload: 任意 JSON 可序列化对象。

    输出:
        None；内容使用 UTF-8、`ensure_ascii=False` 和两空格缩进。
    """

    def write_payload(temporary_file: TextIO) -> None:
        """把 JSON payload 序列化到已打开的临时文件。"""

        json.dump(payload, temporary_file, ensure_ascii=False, indent=2)

    _atomic_write_text(path, write_payload)


def atomic_write_jsonl(
    path: str | Path,
    records: Iterable[dict[str, Any]],
) -> None:
    """原子覆盖写入 JSONL 记录集合。

    输入:
        path: 目标文件路径；函数会自动创建父目录。
        records: 可迭代的 JSON 可序列化字典，每条记录写成独立一行。

    输出:
        None；非空记录集合以换行结尾，空集合写为空文件。
    """

    def write_records(temporary_file: TextIO) -> None:
        """逐条序列化 JSONL records 到已打开的临时文件。"""

        for record in records:
            json.dump(record, temporary_file, ensure_ascii=False)
            temporary_file.write("\n")

    _atomic_write_text(path, write_records)


def _atomic_write_text(
    path: str | Path,
    write_content: Callable[[TextIO], None],
) -> None:
    """通过同目录临时文件原子替换文本目标。

    输入:
        path: 最终目标路径。
        write_content: 接收临时文本文件并写入完整内容的回调。

    输出:
        None；写入和同步成功后才替换目标，失败时清理临时文件。
    """

    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            write_content(temporary_file)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, target_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                if temporary_path.exists():
                    temporary_path.unlink()
            except OSError:
                pass

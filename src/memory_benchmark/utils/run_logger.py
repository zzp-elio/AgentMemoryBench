"""运行期日志工具。

本模块只负责把一次 benchmark run 的可读日志和结构化事件写入指定目录。
它不读取 `.env`，不配置全局 logging，也不直接使用 print。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.errors import MarkupError
from rich.text import Text


class RunLogger:
    """写入单次运行的终端日志、run.log 和 events.jsonl。

    参数:
        log_dir: 本次运行的日志目录，例如 `outputs/<run_id>/logs/`。

    输出:
        构造后目录会存在；后续调用会追加写入 `run.log` 和 `events.jsonl`。
    """

    def __init__(self, log_dir: str | Path):
        """初始化日志目录和 Rich 终端输出对象。

        参数:
            log_dir: 字符串或 Path，指向本次运行的日志目录。

        返回:
            None。
        """

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.run_log_path = self.log_dir / "run.log"
        self.events_path = self.log_dir / "events.jsonl"
        self.console = Console()

    def info(self, message: str) -> None:
        """输出一条人类可读日志到终端和 run.log。

        参数:
            message: 已由调用方确认可公开记录的日志文本。

        返回:
            None。
        """

        timestamp = self._current_timestamp()
        try:
            plain_message = Text.from_markup(message).plain
            self.console.print(message)
        except MarkupError:
            # Rich markup 写错时降级为普通文本，避免长实验因为日志格式中断。
            plain_message = message
            self.console.print(message, markup=False)
        with self.run_log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {plain_message}\n")

    def log_event(self, event: str, payload: dict[str, Any]) -> None:
        """追加一条结构化 JSONL 事件。

        参数:
            event: 事件名称，例如 `case_started`。
            payload: 事件载荷，只应包含 method 可记录的公开信息。

        返回:
            None。
        """

        record = {
            "timestamp": self._current_timestamp(),
            "event": event,
            "payload": payload,
        }
        with self.events_path.open("a", encoding="utf-8") as events_file:
            events_file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _current_timestamp(self) -> str:
        """返回 UTC ISO-8601 时间戳字符串。

        参数:
            无。

        返回:
            str: 带时区信息的当前 UTC 时间戳。
        """

        return datetime.now(timezone.utc).isoformat()

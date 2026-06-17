"""结构化事件 JSONL 写入器。

本模块只负责追加公开结构化事件，不负责终端展示、secret 读取或全局日志配置。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EventWriter:
    """追加写入结构化 JSONL 事件。

    参数:
        event_path: JSONL 文件路径；构造时会自动创建父目录。
    """

    def __init__(self, event_path: str | Path):
        """初始化事件文件路径。

        输入:
            event_path: 字符串或 Path，指向要追加写入的 JSONL 文件。

        输出:
            None；调用后父目录存在。
        """

        self.event_path = Path(event_path)
        self.event_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, payload: dict[str, Any]) -> None:
        """追加一条带时间戳的结构化事件。

        输入:
            event: 事件名称，例如 `run_started`。
            payload: JSON 可序列化的公开事件载荷。

        输出:
            None；事件会作为一行 JSON 写入文件末尾。
        """

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        with self.event_path.open("a", encoding="utf-8") as event_file:
            event_file.write(json.dumps(record, ensure_ascii=False) + "\n")

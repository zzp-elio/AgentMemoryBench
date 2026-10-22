"""协调器核心领域实体与传输对象 (Coordinator DTOs & Entities)。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    """协调器评测任务调度状态。"""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ReadyRequest:
    """被测记忆系统向 Coordinator 发起就绪注册的请求载荷 (DTO)。"""

    method_name: str
    endpoint: str
    benchmark: str = "locomo"
    run_id: str | None = None
    metrics: list[str] = field(default_factory=lambda: ["f1"])
    max_conversations: int | None = None
    max_questions_per_conversation: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationTaskInfo:
    """由 Coordinator 异步调度管理的评测任务追踪实体。"""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    method_name: str = ""
    endpoint: str = ""
    benchmark: str = "locomo"
    run_id: str = ""
    metrics: list[str] = field(default_factory=lambda: ["f1"])
    status: TaskState = TaskState.QUEUED
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    started_at: str | None = None
    completed_at: str | None = None
    error_message: str | None = None
    result_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "method_name": self.method_name,
            "endpoint": self.endpoint,
            "benchmark": self.benchmark,
            "run_id": self.run_id,
            "metrics": list(self.metrics),
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "result_summary": self.result_summary,
        }


__all__ = [
    "EvaluationTaskInfo",
    "ReadyRequest",
    "TaskState",
]

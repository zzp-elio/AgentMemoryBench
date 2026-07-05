# Observability And Artifacts Phase A/B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Execution status:** COMPLETE AND FINAL OVERALL REVIEW APPROVED on 2026-06-11. The unchecked boxes below preserve the original TDD execution procedure and are not the live project status. Final verification reached focused 79/79, full 161/161, fake runner 37/37, and `compileall` exit 0. Current status is maintained in `AGENTS.md` and `docs/handoffs/2026-06-05-observability-artifacts.md`.

**Goal:** Add rich terminal progress, structured file logs, and reusable experiment artifacts for long MemoryOS-LoCoMo runs without changing src-layout yet.

**Architecture:** Introduce focused `observability` and `storage` packages under the current `memory_benchmark/` package. The runner will use these packages to write `manifest.json`, redacted config, dataset fingerprint, append-only artifacts, checkpoint files, rich progress, `run.log`, `events.jsonl`, and `progress.json`. Existing root-level output filenames are kept as transition aliases so current scripts and tests do not break.

**Tech Stack:** Python dataclasses, pathlib, json/jsonl, Rich progress, existing `uv`, existing `unittest` test suite.

---

## Scope

This plan implements only Phase A and Phase B from:

- `docs/superpowers/specs/2026-06-05-observability-src-layout-design.md`

It does not migrate to `src-layout`, does not move third-party repos, and does not migrate tests to pytest. Those are separate future plans after this phase is stable.

## Files To Create Or Modify

Create:

- `memory_benchmark/observability/__init__.py`
- `memory_benchmark/observability/run_context.py`
- `memory_benchmark/observability/event_writer.py`
- `memory_benchmark/observability/progress_reporter.py`
- `memory_benchmark/storage/__init__.py`
- `memory_benchmark/storage/experiment_paths.py`
- `memory_benchmark/storage/jsonl.py`
- `memory_benchmark/storage/fingerprint.py`
- `memory_benchmark/storage/artifacts.py`
- `tests/test_observability_run_context.py`
- `tests/test_observability_progress.py`
- `tests/test_experiment_storage.py`

Modify:

- `memory_benchmark/runners/memoryos_locomo_full.py`
- `memory_benchmark/utils/run_logger.py`
- `tests/test_run_logger.py`
- `tests/test_memoryos_locomo_full_runner.py`
- `docs/superpowers/specs/2026-06-05-observability-src-layout-design.md`
- `AGENTS.md`
- `README.md`

## Task 1: RunContext And EventWriter

**Files:**

- Create: `memory_benchmark/observability/__init__.py`
- Create: `memory_benchmark/observability/run_context.py`
- Create: `memory_benchmark/observability/event_writer.py`
- Test: `tests/test_observability_run_context.py`

- [ ] **Step 1: Write tests for run context and event writer**

Create `tests/test_observability_run_context.py` with tests shaped like:

```python
"""测试运行上下文和结构化事件写入。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_benchmark.observability import EventWriter, RunContext


class ObservabilityRunContextTests(unittest.TestCase):
    """验证 RunContext 和 EventWriter 的基础行为。"""

    def test_run_context_creates_standard_directories(self):
        """RunContext 应统一暴露 outputs/<run_id> 下的标准目录。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            context = RunContext.create(
                run_id="run-001",
                benchmark_name="locomo",
                method_name="MemoryOS",
                model_name="gpt-4o-mini",
                output_root=Path(temp_dir),
                resume=True,
            )

            self.assertEqual(context.run_dir, Path(temp_dir) / "run-001")
            self.assertEqual(context.logs_dir, context.run_dir / "logs")
            self.assertEqual(context.artifacts_dir, context.run_dir / "artifacts")
            self.assertEqual(context.checkpoints_dir, context.run_dir / "checkpoints")
            self.assertEqual(context.summaries_dir, context.run_dir / "summaries")
            self.assertTrue(context.logs_dir.is_dir())
            self.assertTrue(context.artifacts_dir.is_dir())
            self.assertTrue(context.checkpoints_dir.is_dir())

    def test_event_writer_appends_jsonl_events(self):
        """EventWriter 应追加结构化事件并自动补时间戳和事件名。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "events.jsonl"
            writer = EventWriter(event_path)

            writer.write("run_started", {"run_id": "run-001"})
            writer.write("question_done", {"question_id": "conv-1:q1", "f1": 0.5})

            rows = [
                json.loads(line)
                for line in event_path.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual([row["event"] for row in rows], ["run_started", "question_done"])
            self.assertEqual(rows[0]["payload"], {"run_id": "run-001"})
            self.assertIn("timestamp", rows[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run python -m unittest tests/test_observability_run_context.py -v
```

Expected: fail because `memory_benchmark.observability` does not exist.

- [ ] **Step 3: Implement RunContext**

Create `memory_benchmark/observability/run_context.py`:

```python
"""运行上下文实体。

本模块保存一次实验运行的稳定路径和公开配置，不读取 `.env`，不记录 API key。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RunContext:
    """一次 benchmark run 的公开上下文。

    字段:
        run_id: 本次运行 id。
        benchmark_name: benchmark 名称，例如 `locomo`。
        method_name: method 名称，例如 `MemoryOS`。
        model_name: 模型名，例如 `gpt-4o-mini`。
        output_root: 输出根目录。
        resume: 是否从已有 checkpoint 继续。
        started_at: UTC ISO-8601 启动时间。
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
        resume: bool,
    ) -> "RunContext":
        """创建上下文并确保标准目录存在。"""

        context = cls(
            run_id=run_id,
            benchmark_name=benchmark_name,
            method_name=method_name,
            model_name=model_name,
            output_root=Path(output_root).resolve(),
            resume=resume,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        context.ensure_directories()
        return context

    @property
    def run_dir(self) -> Path:
        """返回 `outputs/<run_id>` 目录。"""

        return self.output_root / self.run_id

    @property
    def logs_dir(self) -> Path:
        """返回日志目录。"""

        return self.run_dir / "logs"

    @property
    def artifacts_dir(self) -> Path:
        """返回实验产物目录。"""

        return self.run_dir / "artifacts"

    @property
    def checkpoints_dir(self) -> Path:
        """返回 checkpoint 目录。"""

        return self.run_dir / "checkpoints"

    @property
    def summaries_dir(self) -> Path:
        """返回 summary 目录。"""

        return self.run_dir / "summaries"

    @property
    def method_state_dir(self) -> Path:
        """返回 method 状态目录。"""

        return self.run_dir / "method_state"

    def ensure_directories(self) -> None:
        """创建本次运行需要的标准目录。"""

        for directory in [
            self.logs_dir,
            self.artifacts_dir,
            self.checkpoints_dir,
            self.summaries_dir,
            self.method_state_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Implement EventWriter and package exports**

Create `memory_benchmark/observability/event_writer.py`:

```python
"""结构化运行事件写入器。

本模块只负责 append-only JSONL，不负责业务判断。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EventWriter:
    """把运行事件追加写入 JSONL 文件。"""

    def __init__(self, event_path: str | Path):
        """初始化事件文件路径并创建父目录。"""

        self.event_path = Path(event_path)
        self.event_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, payload: dict[str, Any]) -> None:
        """追加一条带时间戳的事件。"""

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        with self.event_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
```

Create `memory_benchmark/observability/__init__.py`:

```python
"""运行可观测性模块。

包含运行上下文、结构化事件、终端进度和文件日志相关工具。
"""

from .event_writer import EventWriter
from .run_context import RunContext

__all__ = ["EventWriter", "RunContext"]
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```bash
uv run python -m unittest tests/test_observability_run_context.py -v
```

Expected: 2 tests pass.

## Task 2: ProgressReporter

**Files:**

- Create: `memory_benchmark/observability/progress_reporter.py`
- Modify: `memory_benchmark/observability/__init__.py`
- Test: `tests/test_observability_progress.py`

- [ ] **Step 1: Write tests for progress reporter**

Create `tests/test_observability_progress.py`:

```python
"""测试 Rich 进度条封装。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rich.console import Console

from memory_benchmark.observability import ProgressReporter


class ProgressReporterTests(unittest.TestCase):
    """验证 ProgressReporter 能记录阶段和 progress.json。"""

    def test_progress_reporter_writes_progress_snapshot(self):
        """更新阶段和 question 后，应写入最新 progress.json。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            progress_path = Path(temp_dir) / "progress.json"
            console = Console(file=None, force_terminal=False, width=100)
            reporter = ProgressReporter(
                progress_path=progress_path,
                console=console,
                enabled=False,
            )

            with reporter:
                reporter.set_stage("Answer questions", step_index=4, step_count=6)
                reporter.update_questions(
                    completed=7,
                    total=10,
                    current_conversation_id="conv-1",
                    current_question_id="conv-1:q7",
                )

            snapshot = json.loads(progress_path.read_text(encoding="utf-8"))

            self.assertEqual(snapshot["stage"], "Answer questions")
            self.assertEqual(snapshot["step_index"], 4)
            self.assertEqual(snapshot["question_completed"], 7)
            self.assertEqual(snapshot["question_total"], 10)
            self.assertEqual(snapshot["current_question_id"], "conv-1:q7")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run python -m unittest tests/test_observability_progress.py -v
```

Expected: fail because `ProgressReporter` does not exist.

- [ ] **Step 3: Implement ProgressReporter**

Create `memory_benchmark/observability/progress_reporter.py`:

```python
"""Rich 进度条封装。

本模块为长实验提供终端进度和 progress.json 快照。关闭 Rich 显示时仍会写快照，
便于单元测试和后台运行。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn


class ProgressReporter:
    """记录当前运行阶段、conversation 进度和 question 进度。"""

    def __init__(
        self,
        progress_path: str | Path,
        console: Console | None = None,
        enabled: bool = True,
    ):
        """初始化进度条。

        参数:
            progress_path: `outputs/<run_id>/checkpoints/progress.json`。
            console: 可选 Rich Console；测试可传入自定义对象。
            enabled: False 时不显示动态进度条，但仍写 progress.json。
        """

        self.progress_path = Path(progress_path)
        self.progress_path.parent.mkdir(parents=True, exist_ok=True)
        self.console = console or Console()
        self.enabled = enabled
        self.snapshot: dict[str, Any] = {
            "stage": "not_started",
            "step_index": 0,
            "step_count": 0,
            "conversation_completed": 0,
            "conversation_total": 0,
            "question_completed": 0,
            "question_total": 0,
            "current_conversation_id": "",
            "current_question_id": "",
        }
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=self.console,
            disable=not self.enabled,
        )
        self._conversation_task_id = None
        self._question_task_id = None

    def __enter__(self) -> "ProgressReporter":
        """进入上下文并启动 Rich progress。"""

        self._progress.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """退出上下文并停止 Rich progress。"""

        self._write_snapshot()
        self._progress.__exit__(exc_type, exc, tb)

    def set_stage(self, stage: str, step_index: int, step_count: int) -> None:
        """更新当前阶段名称。"""

        self.snapshot.update(
            {
                "stage": stage,
                "step_index": step_index,
                "step_count": step_count,
            }
        )
        self._write_snapshot()

    def start_conversations(self, total: int) -> None:
        """初始化 conversation 进度。"""

        self.snapshot.update({"conversation_completed": 0, "conversation_total": total})
        self._conversation_task_id = self._progress.add_task("Conversations", total=total)
        self._write_snapshot()

    def update_conversations(self, completed: int, total: int, current_conversation_id: str) -> None:
        """更新 conversation 进度。"""

        self.snapshot.update(
            {
                "conversation_completed": completed,
                "conversation_total": total,
                "current_conversation_id": current_conversation_id,
            }
        )
        if self._conversation_task_id is not None:
            self._progress.update(
                self._conversation_task_id,
                completed=completed,
                total=total,
                description=f"Conversations {current_conversation_id}",
            )
        self._write_snapshot()

    def start_questions(self, total: int) -> None:
        """初始化 question 进度。"""

        self.snapshot.update({"question_completed": 0, "question_total": total})
        self._question_task_id = self._progress.add_task("Questions", total=total)
        self._write_snapshot()

    def update_questions(
        self,
        completed: int,
        total: int,
        current_conversation_id: str,
        current_question_id: str,
    ) -> None:
        """更新 question 进度。"""

        self.snapshot.update(
            {
                "question_completed": completed,
                "question_total": total,
                "current_conversation_id": current_conversation_id,
                "current_question_id": current_question_id,
            }
        )
        if self._question_task_id is not None:
            self._progress.update(
                self._question_task_id,
                completed=completed,
                total=total,
                description=f"Questions {current_question_id}",
            )
        self._write_snapshot()

    def _write_snapshot(self) -> None:
        """把当前状态写入 progress.json。"""

        self.progress_path.write_text(
            json.dumps(self.snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

- [ ] **Step 4: Export ProgressReporter**

Modify `memory_benchmark/observability/__init__.py`:

```python
"""运行可观测性模块。

包含运行上下文、结构化事件、终端进度和文件日志相关工具。
"""

from .event_writer import EventWriter
from .progress_reporter import ProgressReporter
from .run_context import RunContext

__all__ = ["EventWriter", "ProgressReporter", "RunContext"]
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```bash
uv run python -m unittest tests/test_observability_progress.py -v
```

Expected: 1 test passes.

## Task 3: Experiment Storage Primitives

**Files:**

- Create: `memory_benchmark/storage/__init__.py`
- Create: `memory_benchmark/storage/experiment_paths.py`
- Create: `memory_benchmark/storage/jsonl.py`
- Create: `memory_benchmark/storage/fingerprint.py`
- Create: `memory_benchmark/storage/artifacts.py`
- Test: `tests/test_experiment_storage.py`

- [ ] **Step 1: Write tests for storage paths, JSONL, and fingerprint**

Create `tests/test_experiment_storage.py`:

```python
"""测试实验产物存储工具。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from memory_benchmark.core import Conversation, Dataset, Question, Session, Turn
from memory_benchmark.storage import (
    ExperimentPaths,
    JsonlWriter,
    build_dataset_fingerprint,
)


class ExperimentStorageTests(unittest.TestCase):
    """验证标准输出路径、JSONL 写入和数据指纹。"""

    def test_experiment_paths_create_standard_layout(self):
        """ExperimentPaths 应创建 artifacts/logs/checkpoints/summaries。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = ExperimentPaths.create(Path(temp_dir) / "run-001")

            self.assertTrue(paths.artifacts_dir.is_dir())
            self.assertTrue(paths.logs_dir.is_dir())
            self.assertTrue(paths.checkpoints_dir.is_dir())
            self.assertEqual(paths.method_predictions_path.name, "method_predictions.jsonl")
            self.assertEqual(paths.summary_path.name, "summary.json")

    def test_jsonl_writer_appends_records(self):
        """JsonlWriter 应把多条记录追加为多行 JSONL。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "records.jsonl"
            writer = JsonlWriter(path)

            writer.append({"id": "a", "score": 1.0})
            writer.append({"id": "b", "score": 0.5})

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual([row["id"] for row in rows], ["a", "b"])

    def test_dataset_fingerprint_counts_conversations_and_questions(self):
        """dataset fingerprint 应记录 conversation/question 数。"""

        dataset = Dataset(
            dataset_name="fake",
            conversations=[
                Conversation(
                    conversation_id="conv-1",
                    sessions=[
                        Session(
                            session_id="s1",
                            turns=[Turn("t1", "Alice", "hello")],
                        )
                    ],
                    questions=[
                        Question("conv-1:q1", "conv-1", "Where?"),
                        Question("conv-1:q2", "conv-1", "When?"),
                    ],
                )
            ],
        )

        fingerprint = build_dataset_fingerprint(
            dataset=dataset,
            source_paths=[Path("benchmarks/fake/data.json")],
        )

        self.assertEqual(fingerprint["dataset_name"], "fake")
        self.assertEqual(fingerprint["conversation_count"], 1)
        self.assertEqual(fingerprint["question_count"], 2)
        self.assertEqual(fingerprint["source_paths"][0]["path"], "benchmarks/fake/data.json")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run python -m unittest tests/test_experiment_storage.py -v
```

Expected: fail because `memory_benchmark.storage` does not exist.

- [ ] **Step 3: Implement ExperimentPaths**

Create `memory_benchmark/storage/experiment_paths.py`:

```python
"""实验输出路径实体。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentPaths:
    """一次 run 的标准输出路径集合。"""

    run_dir: Path

    @classmethod
    def create(cls, run_dir: str | Path) -> "ExperimentPaths":
        """创建标准目录并返回路径集合。"""

        paths = cls(Path(run_dir).resolve())
        for directory in [
            paths.artifacts_dir,
            paths.logs_dir,
            paths.checkpoints_dir,
            paths.summaries_dir,
            paths.method_state_dir,
        ]:
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
    def method_state_dir(self) -> Path:
        return self.run_dir / "method_state"

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "manifest.json"

    @property
    def redacted_config_path(self) -> Path:
        return self.run_dir / "config.redacted.json"

    @property
    def dataset_fingerprint_path(self) -> Path:
        return self.run_dir / "dataset_fingerprint.json"

    @property
    def public_questions_path(self) -> Path:
        return self.artifacts_dir / "public_questions.jsonl"

    @property
    def method_predictions_path(self) -> Path:
        return self.artifacts_dir / "method_predictions.jsonl"

    @property
    def evaluator_private_labels_path(self) -> Path:
        return self.artifacts_dir / "evaluator_private_labels.jsonl"

    @property
    def locomo_f1_scores_path(self) -> Path:
        return self.artifacts_dir / "answer_scores.locomo_f1.jsonl"

    @property
    def conversation_status_path(self) -> Path:
        return self.checkpoints_dir / "conversation_status.json"

    @property
    def question_status_path(self) -> Path:
        return self.checkpoints_dir / "question_status.json"

    @property
    def progress_path(self) -> Path:
        return self.logs_dir / "progress.json"

    @property
    def summary_path(self) -> Path:
        return self.summaries_dir / "summary.json"

    @property
    def summary_markdown_path(self) -> Path:
        return self.summaries_dir / "summary.md"
```

- [ ] **Step 4: Implement JSONL writer**

Create `memory_benchmark/storage/jsonl.py`:

```python
"""JSONL 读写工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonlWriter:
    """append-only JSONL writer。"""

    def __init__(self, path: str | Path):
        """初始化 JSONL 路径并创建父目录。"""

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        """追加一条 JSON record。"""

        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """读取 JSONL；文件不存在时返回空列表。"""

    jsonl_path = Path(path)
    if not jsonl_path.exists():
        return []
    return [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
```

- [ ] **Step 5: Implement dataset fingerprint**

Create `memory_benchmark/storage/fingerprint.py`:

```python
"""数据集指纹工具。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from memory_benchmark.core import Dataset


def build_dataset_fingerprint(
    dataset: Dataset,
    source_paths: list[Path],
) -> dict[str, Any]:
    """构造公开数据集指纹。

    文件不存在时仍记录路径，hash 和 size 写为 None，避免测试 fixture 必须真实存在。
    """

    return {
        "dataset_name": dataset.dataset_name,
        "conversation_count": len(dataset.conversations),
        "question_count": sum(len(conversation.questions) for conversation in dataset.conversations),
        "source_paths": [_file_fingerprint(path) for path in source_paths],
    }


def _file_fingerprint(path: Path) -> dict[str, Any]:
    """返回单个文件的路径、大小和 SHA256。"""

    if not path.exists():
        return {"path": str(path), "size_bytes": None, "sha256": None}
    data = path.read_bytes()
    return {
        "path": str(path),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
```

- [ ] **Step 6: Implement artifact helpers and exports**

Create `memory_benchmark/storage/artifacts.py`:

```python
"""实验产物记录构造工具。"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core import GoldAnswerInfo, Question


def public_question_record(question: Question) -> dict[str, Any]:
    """把公开 Question 转成 JSONL record。"""

    return {
        "question_id": question.question_id,
        "conversation_id": question.conversation_id,
        "question_text": question.text,
        "category": question.category,
        "metadata": question.metadata,
    }


def evaluator_private_label_record(gold: GoldAnswerInfo, category: str | None) -> dict[str, Any]:
    """把 evaluator-only gold 信息转成 JSONL record。

    该 record 只能写入 artifacts，不能传给 method。
    """

    return {
        "question_id": gold.question_id,
        "gold_answer": gold.answer,
        "category": category,
        "evidence": gold.evidence,
        "metadata": gold.metadata,
    }
```

Create `memory_benchmark/storage/__init__.py`:

```python
"""实验输出存储模块。"""

from .artifacts import evaluator_private_label_record, public_question_record
from .experiment_paths import ExperimentPaths
from .fingerprint import build_dataset_fingerprint
from .jsonl import JsonlWriter, read_jsonl

__all__ = [
    "ExperimentPaths",
    "JsonlWriter",
    "build_dataset_fingerprint",
    "evaluator_private_label_record",
    "public_question_record",
    "read_jsonl",
]
```

- [ ] **Step 7: Run tests and verify they pass**

Run:

```bash
uv run python -m unittest tests/test_experiment_storage.py -v
```

Expected: 3 tests pass.

## Task 4: Upgrade RunLogger Without Breaking Existing Tests

**Files:**

- Modify: `memory_benchmark/utils/run_logger.py`
- Modify: `tests/test_run_logger.py`

- [ ] **Step 1: Add tests for progress-friendly file logging**

Modify `tests/test_run_logger.py` to add:

```python
    def test_info_accepts_rich_markup_and_file_log_strips_markup(self):
        """info 写终端时可用 Rich markup，写 run.log 时应保持可读文本。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            terminal_output = io.StringIO()

            with contextlib.redirect_stdout(terminal_output):
                logger = RunLogger(Path(temp_dir))
                logger.info("[bold]Memory Benchmark Run[/bold]")

            log_path = Path(temp_dir) / "run.log"
            content = log_path.read_text(encoding="utf-8")

            self.assertIn("Memory Benchmark Run", content)
            self.assertNotIn("[bold]", content)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run python -m unittest tests/test_run_logger.py -v
```

Expected: new test fails because current run.log preserves markup.

- [ ] **Step 3: Strip Rich markup for run.log**

Modify `memory_benchmark/utils/run_logger.py`:

```python
from rich.markup import escape
from rich.text import Text
```

Update `info()`:

```python
    def info(self, message: str) -> None:
        """输出一条人类可读日志到终端和 run.log。"""

        timestamp = self._current_timestamp()
        self.console.print(message)
        plain_message = Text.from_markup(message).plain
        with self.run_log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {plain_message}\n")
```

If `escape` is unused after editing, do not keep the import.

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
uv run python -m unittest tests/test_run_logger.py -v
```

Expected: all RunLogger tests pass.

## Task 5: Integrate Standard Artifacts Into MemoryOS-LoCoMo Runner

**Files:**

- Modify: `memory_benchmark/runners/memoryos_locomo_full.py`
- Modify: `tests/test_memoryos_locomo_full_runner.py`

- [ ] **Step 1: Extend runner tests for new output layout**

Modify `tests/test_memoryos_locomo_full_runner.py` in `test_full_runner_writes_predictions_scores_and_summary` after `run_dir` is defined:

```python
            manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            fingerprint = json.loads(
                (run_dir / "dataset_fingerprint.json").read_text(encoding="utf-8")
            )
            artifact_predictions = _read_jsonl(
                run_dir / "artifacts" / "method_predictions.jsonl"
            )
            private_labels = _read_jsonl(
                run_dir / "artifacts" / "evaluator_private_labels.jsonl"
            )
            artifact_scores = _read_jsonl(
                run_dir / "artifacts" / "answer_scores.locomo_f1.jsonl"
            )
            summary_payload = json.loads(
                (run_dir / "summaries" / "summary.json").read_text(encoding="utf-8")
            )
```

Add assertions:

```python
        self.assertEqual(manifest["run_id"], "unit-full")
        self.assertEqual(manifest["benchmark_name"], "locomo")
        self.assertEqual(manifest["method_name"], "MemoryOS")
        self.assertEqual(fingerprint["question_count"], 3)
        self.assertEqual(len(artifact_predictions), 3)
        self.assertEqual(len(private_labels), 3)
        self.assertEqual(len(artifact_scores), 3)
        self.assertIn("gold_answer", private_labels[0])
        self.assertNotIn("gold_answer", artifact_predictions[0])
```

Keep existing checks for legacy `predictions.jsonl`, `scores.jsonl`, and root `summary.json`.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

Expected: fail because standard artifact files are not written yet.

- [ ] **Step 3: Import new observability/storage helpers**

Modify the imports in `memory_benchmark/runners/memoryos_locomo_full.py`:

```python
from memory_benchmark.observability import ProgressReporter, RunContext
from memory_benchmark.storage import (
    ExperimentPaths,
    JsonlWriter,
    build_dataset_fingerprint,
    evaluator_private_label_record,
    public_question_record,
    read_jsonl,
)
```

- [ ] **Step 4: Create RunContext and ExperimentPaths**

In `run_memoryos_locomo_full()`, after `selected_run_id` is computed, replace direct `run_dir` construction with:

```python
    run_context = RunContext.create(
        run_id=selected_run_id,
        benchmark_name="locomo",
        method_name="MemoryOS",
        model_name="gpt-4o-mini",
        output_root=selected_output_root,
        resume=resume,
    )
    paths = ExperimentPaths.create(run_context.run_dir)
    run_dir = paths.run_dir
```

Keep `_prepare_run_dir(run_dir, resume=resume)` immediately after this block. After `_prepare_run_dir`, call `run_context.ensure_directories()` and `paths = ExperimentPaths.create(run_dir)` again so non-resume cleanup recreates standard directories.

- [ ] **Step 5: Move canonical paths to standard layout while keeping legacy aliases**

Set canonical paths:

```python
    prediction_path = paths.method_predictions_path
    score_path = paths.locomo_f1_scores_path
    summary_path = paths.summary_path
    status_path = paths.conversation_status_path
    memoryos_storage_root = paths.method_state_dir
```

Set legacy aliases:

```python
    legacy_prediction_path = run_dir / "predictions.jsonl"
    legacy_score_path = run_dir / "scores.jsonl"
    legacy_summary_path = run_dir / "summary.json"
    legacy_status_path = run_dir / "conversation_status.json"
```

Resume compatibility rule:

```python
    if resume and not prediction_path.exists() and legacy_prediction_path.exists():
        prediction_path = legacy_prediction_path
    if resume and not score_path.exists() and legacy_score_path.exists():
        score_path = legacy_score_path
    if resume and not status_path.exists() and legacy_status_path.exists():
        status_path = legacy_status_path
```

This preserves old runs while new runs use standard paths.

- [ ] **Step 6: Write manifest, redacted config, and fingerprint**

After loading dataset and config, write:

```python
    _write_json(
        paths.manifest_path,
        {
            "run_id": selected_run_id,
            "benchmark_name": "locomo",
            "method_name": "MemoryOS",
            "model_name": "gpt-4o-mini",
            "resume": resume,
            "confirm_expensive": confirm_expensive,
            "conversation_limit": conversation_limit,
            "question_limit_per_conversation": question_limit_per_conversation,
            "output_dir": str(run_dir),
            "started_at": run_context.started_at,
        },
    )
    _write_json(
        paths.redacted_config_path,
        {
            "memoryos_config": config.to_public_dict()
            if hasattr(config, "to_public_dict")
            else asdict(config),
            "secrets": "redacted",
        },
    )
    _write_json(
        paths.dataset_fingerprint_path,
        build_dataset_fingerprint(
            dataset=dataset,
            source_paths=[path_settings.project_root / "benchmarks/locomo-main/data/locomo10.json"],
        ),
    )
```

If `MemoryOSPaperConfig` lacks `to_public_dict`, `asdict(config)` is acceptable because it contains no API key.

- [ ] **Step 7: Write public questions and private labels once per run**

Before answering questions, write standard artifacts only when not resuming with existing files:

```python
    if not resume or not paths.public_questions_path.exists():
        _rewrite_public_question_artifacts(
            conversations=dataset.conversations,
            question_limit_per_conversation=question_limit_per_conversation,
            public_question_path=paths.public_questions_path,
            private_label_path=paths.evaluator_private_labels_path,
        )
```

Add helper:

```python
def _rewrite_public_question_artifacts(
    conversations: list[Conversation],
    question_limit_per_conversation: int | None,
    public_question_path: Path,
    private_label_path: Path,
) -> None:
    """重写公开 question 和 evaluator-only label artifacts。"""

    public_question_path.unlink(missing_ok=True)
    private_label_path.unlink(missing_ok=True)
    public_writer = JsonlWriter(public_question_path)
    private_writer = JsonlWriter(private_label_path)
    for conversation in conversations:
        for question in _selected_questions(conversation, question_limit_per_conversation):
            public_question = _make_public_question(question)
            public_writer.append(public_question_record(public_question))
            private_writer.append(
                evaluator_private_label_record(
                    conversation.gold_answers[public_question.question_id],
                    public_question.category,
                )
            )
```

- [ ] **Step 8: Mirror new outputs to legacy aliases after each write**

After writing each prediction and score record, append to both canonical and legacy files if paths differ:

```python
            _append_jsonl(prediction_path, prediction_record)
            if prediction_path != legacy_prediction_path:
                _append_jsonl(legacy_prediction_path, prediction_record)
            _append_jsonl(score_path, score_record)
            if score_path != legacy_score_path:
                _append_jsonl(legacy_score_path, score_record)
```

When writing summary:

```python
            _write_json(summary_path, summary_payload)
            if summary_path != legacy_summary_path:
                _write_json(legacy_summary_path, summary_payload)
```

When writing status:

```python
    _write_json(status_path, conversation_status)
    if status_path != legacy_status_path:
        _write_json(legacy_status_path, conversation_status)
```

Pass `legacy_status_path` into `_ensure_conversation_state()` or centralize status writing in a helper:

```python
def _write_status(path: Path, legacy_path: Path, payload: dict[str, str]) -> None:
    """写 checkpoint，并同步 legacy alias。"""

    _write_json(path, payload)
    if path != legacy_path:
        _write_json(legacy_path, payload)
```

- [ ] **Step 9: Update summary paths**

The returned summary should point to canonical files:

```python
prediction_path=str(paths.method_predictions_path)
score_path=str(paths.locomo_f1_scores_path)
summary_path=str(paths.summary_path)
log_dir=str(paths.logs_dir)
```

The legacy root files remain for compatibility, but summary reports canonical paths.

- [ ] **Step 10: Run full runner tests**

Run:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

Expected: all tests pass.

## Task 6: Add Rich Progress To MemoryOS-LoCoMo Runner

**Files:**

- Modify: `memory_benchmark/runners/memoryos_locomo_full.py`
- Modify: `tests/test_memoryos_locomo_full_runner.py`

- [ ] **Step 1: Add test for progress.json**

Modify `tests/test_memoryos_locomo_full_runner.py` in `test_full_runner_writes_predictions_scores_and_summary`:

```python
            progress = json.loads(
                (run_dir / "logs" / "progress.json").read_text(encoding="utf-8")
            )
```

Add assertions:

```python
        self.assertEqual(progress["stage"], "Write summary")
        self.assertEqual(progress["question_completed"], 3)
        self.assertEqual(progress["question_total"], 3)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

Expected: fail because `progress.json` is not written.

- [ ] **Step 3: Use ProgressReporter in runner**

In `run_memoryos_locomo_full()`, create:

```python
    progress = ProgressReporter(paths.progress_path)
```

Wrap the main body:

```python
    with progress:
        progress.set_stage("Load dataset", 1, 6)
        ...
```

Use these stages:

```text
1 Load dataset
2 Prepare method state
3 Add conversations
4 Answer questions
5 Evaluate answers
6 Write summary
```

Because evaluation happens immediately after each answer, stage 5 can be set before score writing or folded into the question loop as:

```python
            progress.set_stage("Evaluate answers", 5, 6)
```

Then return to:

```python
            progress.set_stage("Answer questions", 4, 6)
```

This gives terminal feedback without changing runner behavior.

- [ ] **Step 4: Update progress during loops**

Before conversation loop:

```python
        progress.start_conversations(len(dataset.conversations))
        progress.start_questions(
            _planned_question_count(dataset.conversations, question_limit_per_conversation)
        )
```

Maintain counters:

```python
        completed_conversation_count = sum(
            1 for status in conversation_status.values() if status == "added"
        )
        completed_question_count = len(completed_question_ids)
```

After each conversation is ensured:

```python
            completed_conversation_count = sum(
                1 for status in conversation_status.values() if status == "added"
            )
            progress.update_conversations(
                completed=completed_conversation_count,
                total=len(dataset.conversations),
                current_conversation_id=conversation.conversation_id,
            )
```

After each question score:

```python
            completed_question_count = len(completed_question_ids)
            progress.update_questions(
                completed=completed_question_count,
                total=_planned_question_count(dataset.conversations, question_limit_per_conversation),
                current_conversation_id=public_question.conversation_id,
                current_question_id=public_question.question_id,
            )
```

Before final summary write:

```python
        progress.set_stage("Write summary", 6, 6)
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

Expected: all tests pass.

## Task 7: Improve Event Log Coverage

**Files:**

- Modify: `memory_benchmark/runners/memoryos_locomo_full.py`
- Modify: `tests/test_memoryos_locomo_full_runner.py`

- [ ] **Step 1: Add event assertions**

Modify `tests/test_memoryos_locomo_full_runner.py`:

```python
            events = _read_jsonl(run_dir / "logs" / "events.jsonl")
```

Add assertions:

```python
        event_names = [event["event"] for event in events]
        self.assertIn("full_run_started", event_names)
        self.assertIn("dataset_loaded", event_names)
        self.assertIn("conversation_added", event_names)
        self.assertIn("question_scored", event_names)
        self.assertIn("full_run_finished", event_names)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

Expected: fail because `dataset_loaded` is not currently logged.

- [ ] **Step 3: Add missing events**

After dataset load:

```python
    logger.log_event(
        "dataset_loaded",
        {
            "dataset_name": dataset.dataset_name,
            "conversation_count": len(dataset.conversations),
            "question_count": _planned_question_count(
                dataset.conversations,
                question_limit_per_conversation,
            ),
        },
    )
```

Before MemoryOS construction:

```python
    logger.log_event(
        "method_configured",
        {
            "method_name": "MemoryOS",
            "storage_root": str(memoryos_storage_root),
            "config": asdict(config),
        },
    )
```

When reusing existing state, keep current `conversation_attached` event.

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

Expected: all tests pass.

## Task 8: Documentation Updates

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/specs/2026-06-05-observability-src-layout-design.md`

- [ ] **Step 1: Update README run output section**

Add a concise section to `README.md`:

```markdown
## 实验输出结构

长实验输出位于 `outputs/<run_id>/`。核心文件包括：

- `manifest.json`: 本次运行的公开配置和路径。
- `dataset_fingerprint.json`: 数据集路径、hash、conversation/question 数。
- `artifacts/method_predictions.jsonl`: method 的回答，可用于后续复算指标。
- `artifacts/evaluator_private_labels.jsonl`: evaluator-only 标准答案，不能传给 method。
- `artifacts/answer_scores.locomo_f1.jsonl`: LoCoMo F1 明细。
- `logs/run.log`: 人类可读日志。
- `logs/events.jsonl`: 结构化事件日志。
- `checkpoints/progress.json`: 最近进度快照。
- `summaries/summary.json`: 聚合结果。

旧的根目录 `predictions.jsonl`、`scores.jsonl`、`summary.json` 会在过渡期保留为兼容文件。
```

- [ ] **Step 2: Update AGENTS.md**

Add or update rules:

```markdown
- 长实验 runner 必须写 `outputs/<run_id>/logs/run.log`、`events.jsonl` 和 `progress.json`。
- 新 runner 应优先写标准 artifacts 目录，并保留必要的 legacy alias，直到迁移期结束。
- 已有 `method_predictions.jsonl` 和 `evaluator_private_labels.jsonl` 时，新增 evaluator 不应重新调用 method。
- Phase A/B 完成后再单独规划 src-layout 和 pytest 迁移。
```

- [ ] **Step 3: Update design spec status**

In `docs/superpowers/specs/2026-06-05-observability-src-layout-design.md`, add:

```markdown
Phase A/B implementation plan:

- `docs/superpowers/plans/2026-06-05-observability-artifacts-phase-ab.md`
```

- [ ] **Step 4: Run documentation standards tests**

Run:

```bash
uv run python -m unittest tests/test_documentation_standards.py -v
```

Expected: documentation tests pass.

## Task 9: Verification Suite

**Files:**

- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
uv run python -m unittest \
  tests/test_observability_run_context.py \
  tests/test_observability_progress.py \
  tests/test_experiment_storage.py \
  tests/test_run_logger.py \
  tests/test_memoryos_locomo_full_runner.py \
  -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
uv run python -m unittest discover -s tests -v
```

Expected: full suite passes. If the `.env` API smoke test runs, verify it does not print secrets.

- [ ] **Step 3: Run a safe fake or limited runner check**

Run a no-real-API unit-level check only:

```bash
uv run python -m unittest tests/test_memoryos_locomo_full_runner.py -v
```

Expected: output directory in a temp dir contains:

```text
artifacts/method_predictions.jsonl
artifacts/evaluator_private_labels.jsonl
artifacts/answer_scores.locomo_f1.jsonl
logs/run.log
logs/events.jsonl
checkpoints/progress.json
summaries/summary.json
```

## Self-Review

- Spec coverage: Phase A terminal/file observability is covered by Tasks 1, 2, 4, 6, 7. Phase B reusable experiment artifacts are covered by Tasks 3 and 5. Documentation is covered by Task 8. Verification is covered by Task 9.
- Scope check: src-layout, third-party repo migration, and pytest migration are intentionally excluded and will need separate plans after Phase A/B passes.
- Placeholder scan: this plan contains no unresolved placeholders and each task has concrete files, commands, expected outcomes, and code shape.
- Type consistency: `RunContext`, `EventWriter`, `ProgressReporter`, `ExperimentPaths`, `JsonlWriter`, and storage helper names are consistent across tests and implementation steps.

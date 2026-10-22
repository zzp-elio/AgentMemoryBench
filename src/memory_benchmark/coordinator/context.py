"""状态组件依赖注入上下文 (`CoordinatorContext`)。

维护无状态单例组件（`AppConfig`、`HttpTransport`、`FrameworkAnswerReader`、`Evaluators`），
通过纯 DTO (`ReadyRequest`) 接收异步任务，复用无状态连接池与执行器流水线。
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
from typing import Any, Callable

from memory_benchmark.benchmark_adapters import get_adapter
from memory_benchmark.coordinator.entities import (
    EvaluationTaskInfo,
    ReadyRequest,
    TaskState,
)
from memory_benchmark.core import (
    AppConfig,
    Dataset,
    HttpMemoryProvider,
    HttpTransport,
    MemoryProvider,
    MockMemoryProvider,
    load_app_config,
)
from memory_benchmark.evaluators import create_evaluator
from memory_benchmark.readers import FakeAnswerLLMClient, FrameworkAnswerReader
from memory_benchmark.runners.evaluation import run_artifact_evaluation
from memory_benchmark.runners.prediction import run_predictions
from memory_benchmark.storage import RunContext

logger = logging.getLogger(__name__)


class CoordinatorContext:
    """评测协调器 IoC 上下文：统一托管单例 Bean 与任务调度队列。"""

    def __init__(
        self,
        app_config: AppConfig | None = None,
        answer_reader: FrameworkAnswerReader | None = None,
        provider_factory: Callable[[str, str], MemoryProvider] | None = None,
        max_workers: int = 2,
        timeout_seconds: float = 300.0,
        shared_transport: HttpTransport | None = None,
    ) -> None:
        self.app_config = app_config or load_app_config(".")
        self.timeout_seconds = timeout_seconds
        self.shared_transport = shared_transport
        self.answer_reader = answer_reader
        self.provider_factory = provider_factory or self._default_provider_factory
        self._tasks: dict[str, EvaluationTaskInfo] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="coordinator-worker"
        )
        self._is_shutdown = False

    def _default_provider_factory(self, method_name: str, endpoint: str) -> MemoryProvider:
        if method_name == "mock":
            return MockMemoryProvider()
        return HttpMemoryProvider(
            base_url=endpoint,
            timeout_seconds=self.timeout_seconds,
            transport=self.shared_transport,
        )

    def submit_ready_task(self, request: ReadyRequest) -> EvaluationTaskInfo:
        """接收被测方法的 /ready 请求，创建任务实体并提交至后台执行池。"""
        with self._lock:
            if self._is_shutdown:
                raise RuntimeError("CoordinatorContext is shutting down")
            run_id = (
                request.run_id
                or f"{request.benchmark}_{request.method_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            task = EvaluationTaskInfo(
                method_name=request.method_name,
                endpoint=request.endpoint,
                benchmark=request.benchmark,
                run_id=run_id,
                metrics=list(request.metrics or ["f1"]),
                status=TaskState.QUEUED,
            )
            self._tasks[task.task_id] = task

        self._executor.submit(self._run_task_pipeline, task, request)
        return task

    def get_task(self, task_id: str) -> EvaluationTaskInfo | None:
        """按 ID 查询任务信息。"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[EvaluationTaskInfo]:
        """获取所有已登记任务列表。"""
        with self._lock:
            return list(self._tasks.values())

    def _run_task_pipeline(
        self, task: EvaluationTaskInfo, request: ReadyRequest
    ) -> None:
        """在后台工作线程中执行端到端评测流水线。"""
        task.status = TaskState.RUNNING
        task.started_at = datetime.now(timezone.utc).isoformat()
        try:
            provider = self.provider_factory(request.method_name, request.endpoint)
            adapter = get_adapter(request.benchmark, self.app_config.project_root)
            raw_dataset = adapter.load(limit=request.max_conversations)
            dataset = self._slice_dataset(
                raw_dataset,
                max_conversations=request.max_conversations,
                max_questions=request.max_questions_per_conversation,
            )

            prof = self.app_config.profile(request.benchmark)
            reader = self.answer_reader or FrameworkAnswerReader(
                client=FakeAnswerLLMClient("mock answer"),
                prompts=prof.prompts,
            )

            run_ctx = RunContext.create(
                run_id=task.run_id,
                benchmark_name=request.benchmark,
                method_name=request.method_name,
                model_name=getattr(getattr(reader, "client", None), "model_name", "stateless-reader"),
                output_root=self.app_config.outputs_root,
            )

            pred_summary = run_predictions(
                dataset=dataset,
                provider=provider,
                run_context=run_ctx,
                answer_reader=reader,
            )

            eval_summaries: list[dict[str, Any]] = []
            for metric in task.metrics:
                evaluator = create_evaluator(
                    metric,
                    benchmark_name=request.benchmark,
                    llm_props=prof.judge_llm,
                    prompt_props=prof.prompts,
                )
                eval_sum = run_artifact_evaluation(
                    run_dir=run_ctx.run_dir,
                    evaluator=evaluator,
                    expected_benchmark=request.benchmark,
                )
                eval_summaries.append(asdict(eval_sum))

            task.status = TaskState.COMPLETED
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.result_summary = {
                "prediction": asdict(pred_summary),
                "evaluations": eval_summaries,
            }
        except Exception as exc:
            logger.exception("Task %s failed: %s", task.task_id, exc)
            task.status = TaskState.FAILED
            task.completed_at = datetime.now(timezone.utc).isoformat()
            task.error_message = str(exc)

    @staticmethod
    def _slice_dataset(
        dataset: Dataset,
        max_conversations: int | None,
        max_questions: int | None,
    ) -> Dataset:
        convs = list(dataset.conversations)
        if max_conversations and max_conversations > 0:
            convs = convs[:max_conversations]
        if max_questions and max_questions > 0:
            convs = [
                replace(c, questions=list(c.questions[:max_questions]))
                for c in convs
            ]
        return Dataset(dataset.dataset_name, convs, dict(dataset.metadata))

    def shutdown(self, wait: bool = True) -> None:
        """关闭线程池与执行器。"""
        with self._lock:
            self._is_shutdown = True
        self._executor.shutdown(wait=wait)


__all__ = ["CoordinatorContext"]

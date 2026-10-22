"""基于 Python 标准库 `ThreadingHTTPServer` 的轻量级评测协调器服务端 (`CoordinatorServer`)。

对外提供遵循统一 `Result[T]` 协议的 HTTP 接口：
- `POST /ready` 或 `/api/v1/ready`：接收被测记忆服务主动就绪通知并下发评测任务
- `GET /status?task_id=...`：查询单任务执行状态与结果
- `GET /tasks`：查询所有任务大盘列表
- `GET /health`：服务探活
- `POST /shutdown`：优雅停机
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from memory_benchmark.coordinator.context import CoordinatorContext
from memory_benchmark.coordinator.entities import ReadyRequest
from memory_benchmark.core import Result

logger = logging.getLogger(__name__)


class CoordinatorHandler(BaseHTTPRequestHandler):
    """协调器 HTTP 请求处理器（统一封装 Result[T] 响应信封）。"""

    server: CoordinatorServer

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in {"/ready", "/api/v1/ready"}:
            self._handle_ready()
        elif path in {"/shutdown", "/api/v1/shutdown"}:
            self._handle_shutdown()
        else:
            self._send_result(404, Result.fail(code=404, message=f"Not Found: {path}"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in {"/health", "/api/v1/health"}:
            tasks = self.server.context.list_tasks()
            self._send_result(
                200,
                Result.ok(
                    data={
                        "status": "UP",
                        "active_tasks": sum(
                            1 for t in tasks if t.status.value in {"QUEUED", "RUNNING"}
                        ),
                        "total_tasks": len(tasks),
                    }
                ),
            )
        elif path in {"/status", "/api/v1/status"}:
            self._handle_status(parsed.query)
        elif path in {"/tasks", "/api/v1/tasks"}:
            tasks = [t.to_dict() for t in self.server.context.list_tasks()]
            self._send_result(200, Result.ok(data=tasks))
        else:
            self._send_result(404, Result.fail(code=404, message=f"Not Found: {path}"))

    def _handle_ready(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(content_length)
            payload = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
            if not isinstance(payload, dict):
                self._send_result(
                    400, Result.fail(code=400, message="JSON body must be an object")
                )
                return

            endpoint = str(payload.get("endpoint") or "").strip()
            method_name = str(payload.get("method_name") or "").strip()
            if not endpoint or not method_name:
                self._send_result(
                    400,
                    Result.fail(
                        code=400,
                        message="'method_name' and 'endpoint' are required in /ready request",
                    ),
                )
                return

            metrics_val = payload.get("metrics")
            metrics = (
                [str(m).strip() for m in metrics_val]
                if isinstance(metrics_val, list)
                else ["f1"]
            )
            ready_req = ReadyRequest(
                method_name=method_name,
                endpoint=endpoint,
                benchmark=str(payload.get("benchmark") or "locomo").strip(),
                run_id=payload.get("run_id"),
                metrics=metrics,
                max_conversations=payload.get("max_conversations"),
                max_questions_per_conversation=payload.get(
                    "max_questions_per_conversation"
                ),
                metadata=payload.get("metadata") or {},
            )
            task = self.server.context.submit_ready_task(ready_req)
            self._send_result(200, Result.ok(data=task.to_dict()))
        except Exception as exc:
            logger.exception("Error handling /ready: %s", exc)
            self._send_result(500, Result.fail(code=500, message=str(exc)))

    def _handle_status(self, query_string: str) -> None:
        params = parse_qs(query_string)
        task_ids = params.get("task_id")
        if not task_ids or not task_ids[0].strip():
            self._send_result(
                400, Result.fail(code=400, message="'task_id' query param is required")
            )
            return

        task_id = task_ids[0].strip()
        task = self.server.context.get_task(task_id)
        if task is None:
            self._send_result(
                404, Result.fail(code=404, message=f"Task '{task_id}' not found")
            )
            return

        self._send_result(200, Result.ok(data=task.to_dict()))

    def _handle_shutdown(self) -> None:
        self._send_result(200, Result.ok(data={"message": "Server shutting down..."}))
        threading.Thread(target=self.server.stop, daemon=True).start()

    def _send_result(self, http_code: int, result: Result[Any]) -> None:
        payload = json.dumps(
            {
                "code": result.code,
                "message": result.message,
                "data": result.data,
                "latency_ms": result.latency_ms,
            },
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")

        self.send_response(http_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        """静默默认控制台输出，由 Python logging 接管。"""
        logger.debug("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)


class CoordinatorServer(ThreadingHTTPServer):
    """基于 ThreadingHTTPServer 的非阻塞评测协调器。"""

    def __init__(
        self,
        context: CoordinatorContext,
        host: str = "127.0.0.1",
        port: int = 8000,
    ) -> None:
        super().__init__((host, port), CoordinatorHandler)
        self.context = context
        self.host = host
        self.port = self.server_port
        self._serve_thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, threaded: bool = True) -> None:
        """启动服务端（默认在守护线程中非阻塞运行）。"""
        if threaded:
            self._serve_thread = threading.Thread(
                target=self.serve_forever, daemon=True, name="coordinator-server"
            )
            self._serve_thread.start()
        else:
            self.serve_forever()

    def stop(self) -> None:
        """安全停机。"""
        self.shutdown()
        self.server_close()
        self.context.shutdown(wait=False)

    def __enter__(self) -> CoordinatorServer:
        self.start(threaded=True)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


__all__ = ["CoordinatorHandler", "CoordinatorServer"]

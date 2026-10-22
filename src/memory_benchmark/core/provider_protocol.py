"""C/S 架构标准化记忆评测中间层协议 (`MemoryProvider` & `Result[T]`) 与客户端实现。

本模块定义评测框架（Bench）与被测记忆服务（Method Server / Docker）之间的唯一标准契约与内置客户端：
1. 仿 Spring Boot 的泛型响应封装 `Result[T]`：将协议状态码 (`code=200`)、消息 (`message`)、
   耗时 (`latency_ms`) 与纯业务载荷 (`data: T`) 彻底解耦；
2. 极简双方法抽象接口 `MemoryProvider`：仅包含 `ingest`（按单个 `Session` 写入对话轮次列表）
   与 `retrieve`（按问题检索并返回 `RetrievePayload(formatted_memory)`），每次调用均显式传递
   `isolation_key` 由被测服务自行管理存储隔离；
3. 标准远程客户端 `HttpMemoryProvider`（通过 `POST /ingest` 与 `POST /retrieve` 调用任意记忆容器）
   与本地测试桩 `MockMemoryProvider`。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import json
import time
from typing import Any, Generic, TypeVar
import urllib.error
import urllib.request

from .entities import Session, Turn
from .exceptions import ConfigurationError
from .validators import validate_no_private_keys

T = TypeVar("T")
HttpTransport = Callable[[str, dict[str, Any], float | None], dict[str, Any]]
SUPPORTED_METHODS: tuple[str, ...] = ("mock", "http")


def _require_text(value: str, field_name: str) -> None:
    """校验必填文本字段非空。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")


@dataclass(frozen=True)
class Result(Generic[T]):
    """统一服务响应包装类（对齐 Spring Boot `Result<T>` 设计规范）。

    字段:
        code: 状态码，200 表示成功，非 200（如 400/500/504）表示异常。
        message: 状态描述或异常原因说明。
        data: 泛型业务数据载荷（`ingest` 为 `None`，`retrieve` 为 `RetrievePayload`）。
        latency_ms: 本次请求执行耗时（毫秒）。
    """

    code: int = 200
    message: str = "ok"
    data: T | None = None
    latency_ms: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.code, int) or isinstance(self.code, bool):
            raise ValueError("Result.code must be an integer")
        if self.latency_ms < 0:
            raise ValueError("Result.latency_ms must be non-negative")

    @property
    def is_success(self) -> bool:
        """判断本次调用是否成功 (`code == 200`)。"""
        return self.code == 200

    @classmethod
    def ok(
        cls,
        data: T | None = None,
        *,
        message: str = "ok",
        latency_ms: float = 0.0,
    ) -> "Result[T]":
        """快速构造成功响应 (`code=200`)。"""
        return cls(code=200, message=message, data=data, latency_ms=latency_ms)

    @classmethod
    def fail(
        cls,
        code: int = 500,
        message: str = "error",
        *,
        latency_ms: float = 0.0,
    ) -> "Result[T]":
        """快速构造失败响应 (`code != 200`)。"""
        if code == 200:
            raise ValueError("Failure Result code must not be 200")
        return cls(code=code, message=message, data=None, latency_ms=latency_ms)

    def to_dict(self) -> dict[str, Any]:
        """序列化为标准 JSON 字典（供 HTTP 传输或日志落盘）。"""
        serialized_data: Any = self.data
        if hasattr(self.data, "to_dict") and callable(getattr(self.data, "to_dict")):
            serialized_data = self.data.to_dict()
        return {
            "code": self.code,
            "message": self.message,
            "data": serialized_data,
            "latency_ms": self.latency_ms,
        }


@dataclass(frozen=True)
class IngestRequest:
    """单次记忆写入请求：以一个 `Session`（内含 `turns: list[Turn]`）为标准传输单元。"""

    isolation_key: str
    session: Session
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.isolation_key, "isolation_key")
        if not isinstance(self.session, Session):
            raise ValueError("session must be a Session instance")
        validate_no_private_keys(self.session.to_dict())
        validate_no_private_keys(self.metadata)

    @property
    def session_id(self) -> str:
        """返回当前写入会话的 session_id。"""
        return self.session.session_id

    @property
    def session_time(self) -> str | None:
        """返回当前写入会话的时间锚点。"""
        return self.session.session_time

    @property
    def turns(self) -> list[Turn]:
        """返回当前会话包含的对话轮次列表 (`list[Turn]`)。"""
        return self.session.turns

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 请求体字典（供 HTTP `POST /ingest` 发送）。"""
        return {
            "isolation_key": self.isolation_key,
            "session": self.session.to_dict(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RetrieveRequest:
    """单次记忆检索请求。"""

    isolation_key: str
    query: str
    question_time: str | None = None
    top_k: int = 10
    question_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.isolation_key, "isolation_key")
        _require_text(self.query, "query")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")
        validate_no_private_keys(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 请求体字典（供 HTTP `POST /retrieve` 发送）。"""
        return {
            "isolation_key": self.isolation_key,
            "query": self.query,
            "question_time": self.question_time,
            "top_k": self.top_k,
            "question_id": self.question_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RetrievePayload:
    """记忆检索返回的纯业务载荷（仅包含格式化后的记忆上下文）。"""

    formatted_memory: str

    def __post_init__(self) -> None:
        if not isinstance(self.formatted_memory, str):
            raise ValueError("formatted_memory must be a string")

    def to_dict(self) -> dict[str, Any]:
        return {"formatted_memory": self.formatted_memory}


class MemoryProvider(ABC):
    """极简双方法记忆评测中间层协议。

    被测记忆系统（无论是远程 HTTP Server/Docker 容器，还是本地 Mock 实现）
    均只需实现 `ingest` 与 `retrieve` 两个方法，并根据 `isolation_key` 自行管理记忆隔离。
    """

    @abstractmethod
    def ingest(self, request: IngestRequest) -> Result[None]:
        """将一个 Session 的对话列表写入 `request.isolation_key` 对应的记忆空间。"""
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, request: RetrieveRequest) -> Result[RetrievePayload]:
        """从 `request.isolation_key` 对应的记忆空间检索相关上下文并返回 `RetrievePayload`。"""
        raise NotImplementedError


def _default_urllib_transport(
    url: str,
    payload: dict[str, Any],
    timeout_seconds: float | None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """使用标准库 urllib 发送 JSON POST 请求并解析 JSON 响应，具备抗高并发短暂网络重试机制。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_error_message = ""

    for attempt in range(max_retries):
        req = urllib.request.Request(
            url=url,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Connection": "close",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw_text = resp.read().decode("utf-8")
                status_code = resp.status
                break
        except urllib.error.HTTPError as exc:
            error_text = exc.read().decode("utf-8", errors="replace")
            try:
                parsed_err = json.loads(error_text)
                if isinstance(parsed_err, dict):
                    parsed_err.setdefault("code", exc.code)
                    parsed_err.setdefault("message", str(exc.reason))
                    return parsed_err
            except json.JSONDecodeError:
                pass
            return {
                "code": int(exc.code),
                "message": f"HTTP {exc.code}: {error_text or exc.reason}",
                "data": None,
            }
        except (urllib.error.URLError, ConnectionError, OSError, TimeoutError) as exc:
            last_error_message = str(exc)
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            return {
                "code": 503,
                "message": f"Network error calling {url} after {max_retries} attempts: {last_error_message}",
                "data": None,
            }
    else:
        return {
            "code": 503,
            "message": f"Network error calling {url}: {last_error_message}",
            "data": None,
        }

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return {
            "code": 502,
            "message": f"Invalid JSON response from {url}",
            "data": None,
        }

    if not isinstance(parsed, dict):
        return {
            "code": 502,
            "message": f"Expected JSON object from {url}",
            "data": None,
        }
    parsed.setdefault("code", status_code)
    return parsed


class HttpMemoryProvider(MemoryProvider):
    """对接外部记忆系统 Server / Docker 容器的 HTTP 客户端中间层实现。"""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        *,
        timeout_seconds: float | None = 1800.0,
        transport: HttpTransport | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive or None")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._transport: HttpTransport = transport or _default_urllib_transport

    def ingest(self, request: IngestRequest) -> Result[None]:
        """调用远程 `POST /ingest` 接口写入一个 Session 的对话历史。"""
        url = f"{self.base_url}/ingest"
        start = time.perf_counter()
        raw_resp = self._transport(url, request.to_dict(), self.timeout_seconds)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        code = int(raw_resp.get("code", 200))
        message = str(raw_resp.get("message") or ("ok" if code == 200 else "error"))
        latency_ms = float(raw_resp.get("latency_ms") or elapsed_ms)
        return Result(
            code=code,
            message=message,
            data=None,
            latency_ms=latency_ms,
        )

    def retrieve(self, request: RetrieveRequest) -> Result[RetrievePayload]:
        """调用远程 `POST /retrieve` 接口检索记忆并返回 `Result[RetrievePayload]`。"""
        url = f"{self.base_url}/retrieve"
        start = time.perf_counter()
        raw_resp = self._transport(url, request.to_dict(), self.timeout_seconds)
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        code = int(raw_resp.get("code", 200))
        message = str(raw_resp.get("message") or ("ok" if code == 200 else "error"))
        latency_ms = float(raw_resp.get("latency_ms") or elapsed_ms)

        if code != 200:
            return Result.fail(code=code, message=message, latency_ms=latency_ms)

        data_obj = raw_resp.get("data")
        if isinstance(data_obj, dict):
            formatted_memory = str(data_obj.get("formatted_memory") or "")
        elif isinstance(data_obj, str):
            formatted_memory = data_obj
        else:
            formatted_memory = str(raw_resp.get("formatted_memory") or "")

        return Result.ok(
            RetrievePayload(formatted_memory=formatted_memory),
            message=message,
            latency_ms=latency_ms,
        )


class MockMemoryProvider(MemoryProvider):
    """基于内存字典的 `MemoryProvider` 参考实现（用于契约测试与离线冒烟验证）。"""

    def __init__(
        self,
        context_by_question_id: Mapping[str, str] | None = None,
        default_context: str | None = None,
    ) -> None:
        self.context_by_question_id = dict(context_by_question_id or {})
        self.default_context = default_context
        self.ingested_sessions_by_key: dict[str, list[str]] = {}
        self.turns_by_key: dict[str, list[str]] = {}

    def ingest(self, request: IngestRequest) -> Result[None]:
        """将一个 Session 的全部 Turn 按 `isolation_key` 存入内存。"""
        start = time.perf_counter()
        key = request.isolation_key
        self.ingested_sessions_by_key.setdefault(key, []).append(request.session_id)
        bucket = self.turns_by_key.setdefault(key, [])
        for turn in request.turns:
            speaker = turn.speaker or turn.normalized_role or "speaker"
            bucket.append(f"{speaker}: {turn.content}")
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return Result.ok(None, latency_ms=elapsed_ms)

    def retrieve(self, request: RetrieveRequest) -> Result[RetrievePayload]:
        """按 `isolation_key` 检索已写入的对话上下文并封装为 `Result[RetrievePayload]`。"""
        start = time.perf_counter()
        context: str | None = None
        if request.question_id:
            context = self.context_by_question_id.get(request.question_id)
        if context is None:
            stored_turns = self.turns_by_key.get(request.isolation_key, [])
            context = (
                self.default_context
                or "\n".join(stored_turns)
                or f"mock-context-for:{request.query}"
            )
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        return Result.ok(
            RetrievePayload(formatted_memory=context),
            latency_ms=elapsed_ms,
        )


def list_methods() -> tuple[str, ...]:
    """返回内置支持的 Provider 类型列表 (`mock`, `http`)。"""
    return SUPPORTED_METHODS


def create_provider(
    method_name: str = "mock",
    *,
    config: Mapping[str, Any] | None = None,
) -> MemoryProvider:
    """根据方法名与可选连接参数创建 `MemoryProvider` 实例。"""
    normalized = method_name.strip().lower()
    cfg = dict(config or {})

    if normalized == "mock" and "base_url" not in cfg:
        return MockMemoryProvider(
            context_by_question_id=cfg.get("context_by_question_id"),
            default_context=cfg.get("default_context"),
        )

    if normalized == "http" or "base_url" in cfg:
        base_url = str(cfg.get("base_url") or "http://127.0.0.1:8000")
        timeout_raw = cfg.get("timeout_seconds", 1800.0)
        timeout_seconds = float(timeout_raw) if timeout_raw is not None else None
        return HttpMemoryProvider(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )

    raise ConfigurationError(
        f"Unknown method '{method_name}'. Use 'mock' for local testing or 'http' "
        "(with base_url) to connect to a running Method Server."
    )


__all__ = [
    "HttpMemoryProvider",
    "HttpTransport",
    "IngestRequest",
    "MemoryProvider",
    "MockMemoryProvider",
    "Result",
    "RetrievePayload",
    "RetrieveRequest",
    "SUPPORTED_METHODS",
    "create_provider",
    "list_methods",
]

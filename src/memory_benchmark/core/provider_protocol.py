"""provider v3 协议实体与抽象接口。

本模块只定义协议层数据对象和最小 provider ABC，不驱动 runner、不调用
LLM、不读取第三方 method 状态。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from .entities import PromptMessage, Question
from .validators import validate_no_private_keys

ConsumeGranularity: TypeAlias = Literal["turn", "pair", "session", "conversation"]
ProvenanceGranularity: TypeAlias = Literal["none", "session", "turn"]
RetrievalPurpose: TypeAlias = Literal["qa", "memory_update_probe", "extraction_probe"]
BRIDGE_EMPTY_MEMORY_SENTINEL = "[bridge] legacy provider exposed no memory context"


def _require_text(value: str, field_name: str) -> None:
    """校验必填文本字段非空。"""

    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _validate_metadata(metadata: dict[str, Any]) -> None:
    """校验公开 metadata 不含私有评分字段。"""

    validate_no_private_keys(metadata)


@dataclass(frozen=True)
class TurnEvent:
    """规范事件流的最小单元。"""

    role: str
    speaker_name: str | None
    content: str
    timestamp: str | None
    isolation_key: str
    session_id: str | None
    turn_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 turn 公开载荷。"""

        _require_text(self.role, "role")
        _require_text(self.content, "content")
        _require_text(self.isolation_key, "isolation_key")
        _require_text(self.turn_id, "turn_id")
        _validate_metadata(self.metadata)


@dataclass(frozen=True)
class TurnPair:
    """pair 粒度 provider 接收的相邻 turn 载荷。"""

    first: TurnEvent
    second: TurnEvent | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 pair 内 turn 属于同一隔离空间和 session。"""

        _validate_metadata(self.metadata)
        if self.second is None:
            return
        if self.first.isolation_key != self.second.isolation_key:
            raise ValueError("TurnPair turns must share isolation_key")
        if self.first.session_id != self.second.session_id:
            raise ValueError("TurnPair turns must share session_id")

    @property
    def turns(self) -> tuple[TurnEvent, ...]:
        """返回 pair 中实际存在的 turn。"""

        if self.second is None:
            return (self.first,)
        return (self.first, self.second)

    @property
    def isolation_key(self) -> str:
        """返回 pair 所属隔离键。"""

        return self.first.isolation_key

    @property
    def session_id(self) -> str | None:
        """返回 pair 所属 session id。"""

        return self.first.session_id


@dataclass(frozen=True)
class SessionRef:
    """session 边界引用。"""

    isolation_key: str
    session_id: str | None

    def __post_init__(self) -> None:
        """校验 session 引用。"""

        _require_text(self.isolation_key, "isolation_key")


@dataclass(frozen=True)
class UnitRef:
    """隔离单元引用。"""

    isolation_key: str

    def __post_init__(self) -> None:
        """校验隔离单元引用。"""

        _require_text(self.isolation_key, "isolation_key")


@dataclass(frozen=True)
class SessionBatch:
    """session 粒度 provider 接收的批量 turn 载荷。"""

    isolation_key: str
    session_id: str | None
    events: tuple[TurnEvent, ...]
    session_time: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 session batch 内 turn 边界一致。"""

        _require_text(self.isolation_key, "isolation_key")
        _validate_metadata(self.metadata)
        for event in self.events:
            if event.isolation_key != self.isolation_key:
                raise ValueError("SessionBatch events must share isolation_key")
            if event.session_id != self.session_id:
                raise ValueError("SessionBatch events must share session_id")

    @property
    def ref(self) -> SessionRef:
        """返回当前 session batch 的边界引用。"""

        return SessionRef(isolation_key=self.isolation_key, session_id=self.session_id)


@dataclass(frozen=True)
class ConversationBatch:
    """conversation 粒度 provider 接收的完整隔离空间载荷。"""

    isolation_key: str
    sessions: tuple[SessionBatch, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 conversation batch 内 session 边界一致。"""

        _require_text(self.isolation_key, "isolation_key")
        _validate_metadata(self.metadata)
        for session in self.sessions:
            if session.isolation_key != self.isolation_key:
                raise ValueError("ConversationBatch sessions must share isolation_key")

    @property
    def ref(self) -> UnitRef:
        """返回当前 conversation batch 的隔离单元引用。"""

        return UnitRef(isolation_key=self.isolation_key)

    @property
    def events(self) -> tuple[TurnEvent, ...]:
        """按 session 顺序展开全部 turn event。"""

        return tuple(event for session in self.sessions for event in session.events)


IngestUnit: TypeAlias = TurnEvent | TurnPair | SessionBatch | ConversationBatch


@dataclass(frozen=True)
class IngestResult:
    """provider 写入一个 ingest unit 后的结果。"""

    unit_ref: SessionRef | UnitRef | None = None
    session_memories: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 ingest 结果公开 metadata。"""

        _validate_metadata(self.metadata)


@dataclass(frozen=True)
class SessionMemoryReport:
    """session 边界新增记忆报告。"""

    session_ref: SessionRef
    memories: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 session memory report。"""

        _validate_metadata(self.metadata)


@dataclass(frozen=True)
class RetrievalQuery:
    """provider v3 检索输入。"""

    query_text: str
    isolation_key: str
    question_time: str | None
    top_k: int
    purpose: RetrievalPurpose
    source_question: Question | None = None

    def __post_init__(self) -> None:
        """校验检索查询不含私有数据。"""

        _require_text(self.query_text, "query_text")
        _require_text(self.isolation_key, "isolation_key")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")
        if self.purpose not in {"qa", "memory_update_probe", "extraction_probe"}:
            raise ValueError("purpose must be one of: qa, memory_update_probe, extraction_probe")
        if self.source_question is not None:
            validate_no_private_keys(self.source_question.to_dict())


@dataclass(frozen=True)
class RetrievedItem:
    """结构化检索命中条目。"""

    item_id: str
    content: str
    score: float | None
    timestamp: str | None
    source_turn_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验检索条目公开字段。"""

        _require_text(self.item_id, "item_id")
        _require_text(self.content, "content")
        _validate_metadata(self.metadata)


@dataclass(frozen=True)
class RetrievalResult:
    """provider v3 检索输出。"""

    formatted_memory: str
    prompt_messages: tuple[PromptMessage, ...] | None = None
    items: tuple[RetrievedItem, ...] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 formatted_memory 必填并保持 metadata 公开。"""

        _require_text(self.formatted_memory, "formatted_memory")
        _validate_metadata(self.metadata)


class MemoryProvider(ABC):
    """provider v3 最小抽象接口。"""

    consume_granularity: ConsumeGranularity
    session_memory_report: bool = False
    provenance_granularity: ProvenanceGranularity = "none"

    def prepare(self, run_context: Any) -> None:
        """运行前准备钩子，默认无操作。"""

        return None

    @abstractmethod
    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """写入一个按声明粒度聚合后的 ingest unit。"""

        raise NotImplementedError

    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None:
        """session 边界钩子，默认无操作。"""

        return None

    def end_conversation(self, ref: UnitRef) -> None:
        """隔离单元收尾钩子，默认无操作。"""

        return None

    @abstractmethod
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """根据公开 query 返回检索结果，不生成最终答案。"""

        raise NotImplementedError

    def cleanup(self) -> None:
        """运行后清理钩子，默认无操作。"""

        return None


__all__ = [
    "BRIDGE_EMPTY_MEMORY_SENTINEL",
    "ConsumeGranularity",
    "ConversationBatch",
    "IngestResult",
    "IngestUnit",
    "MemoryProvider",
    "ProvenanceGranularity",
    "RetrievalPurpose",
    "RetrievalQuery",
    "RetrievalResult",
    "RetrievedItem",
    "SessionBatch",
    "SessionMemoryReport",
    "SessionRef",
    "TurnEvent",
    "TurnPair",
    "UnitRef",
]

"""Mem0 OSS 的 conversation-QA 适配器。

本模块直接调用 `third_party/methods/mem0-main/` 中的官方 Mem0 `Memory` 算法，
不修改第三方源码。它负责官方 benchmark 参数、逐 turn 写入、conversation namespace
隔离、记忆检索和固定 reader 回答；runner 只依赖统一 `BaseMemorySystem` 接口。
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import os
import sys
import threading
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from openai import OpenAI

from memory_benchmark.config.settings import (
    OpenAISettings,
    PathSettings,
    load_path_settings,
    load_settings,
)
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    Conversation,
    ImageRef,
    Question,
    AnswerPromptResult,
    PromptMessage,
    Session,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider, BaseResumableMemorySystem
from memory_benchmark.core.provider_protocol import (
    ConsumeGranularity,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    RetrievedItem,
    SessionBatch,
    SessionMemoryReport,
    SessionRef,
    TurnEvent,
    TurnPair,
    UnitRef,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
    resolve_token_usage,
)


MEM0_METHOD_DIRECTORY = "mem0-main"
MEM0_ADAPTER_VERSION = "conversation-qa-v1"
MEM0_READER_PROMPT_VERSION = "mem0-memory-benchmarks-reader-v2"
VALID_MESSAGE_ROLES = {"user", "assistant"}
LONGMEMEVAL_QUESTION_TYPES = {
    "temporal-reasoning",
    "multi-session",
    "knowledge-update",
    "single-session-user",
    "single-session-assistant",
    "single-session-preference",
}


@dataclass(frozen=True)
class Mem0Config:
    """Mem0 官方 benchmark 参数及运行 profile。

    字段:
        extraction_model: Mem0 写入阶段用于事实提取和记忆更新的 LLM。
        embedding_model: Mem0 写入和检索使用的 embedding 模型。
        embedding_dimensions: 向量维度，必须与 Qdrant collection 一致。
        reader_model: 框架固定 reader 用于根据检索记忆生成最终回答的模型。
        top_k: method 内部检索记忆上限，不进入统一接口参数。
        max_workers: conversation 级建议并发数，由 runner policy 读取。
        ingestion_chunk_size: 每次 Mem0 add 包含的 turn 数；官方 LoCoMo 配置为 1。
        infer: 是否启用 Mem0 官方事实提取、ADD/UPDATE/DELETE 算法。
        api_timeout_seconds: Mem0 内部 OpenAI-compatible LLM/embedding 请求超时秒数。
        api_max_retries: Mem0 内部 OpenAI-compatible LLM/embedding 请求最大重试次数。
        profile_name: 可审计的 profile 名称。
    """

    extraction_model: str
    embedding_model: str
    embedding_dimensions: int
    reader_model: str
    top_k: int
    max_workers: int
    ingestion_chunk_size: int = 1
    infer: bool = True
    api_timeout_seconds: float = 60.0
    api_max_retries: int = 8
    profile_name: str = "custom"

    def __post_init__(self) -> None:
        """强校验会影响实验语义的参数。"""

        if not self.extraction_model.strip():
            raise ConfigurationError("Mem0 extraction_model is required")
        if not self.embedding_model.strip():
            raise ConfigurationError("Mem0 embedding_model is required")
        if not self.reader_model.strip():
            raise ConfigurationError("Mem0 reader_model is required")
        if self.embedding_dimensions < 1:
            raise ConfigurationError("Mem0 embedding_dimensions must be positive")
        if self.top_k < 1:
            raise ConfigurationError("Mem0 top_k must be positive")
        if self.max_workers < 1:
            raise ConfigurationError("Mem0 max_workers must be positive")
        if self.ingestion_chunk_size != 1:
            raise ConfigurationError(
                "Current Mem0 adapter requires official per-turn ingestion_chunk_size=1"
            )
        if not self.infer:
            raise ConfigurationError(
                "Mem0 benchmark adapter requires infer=True to test the Mem0 algorithm"
            )
        if self.api_timeout_seconds <= 0:
            raise ConfigurationError(
                "Mem0 api_timeout_seconds must be positive"
            )
        if self.api_max_retries < 0:
            raise ConfigurationError(
                "Mem0 api_max_retries cannot be negative"
            )

    @classmethod
    def smoke(cls) -> "Mem0Config":
        """返回低成本真实链路 smoke profile。

        smoke 只降低 conversation/question/turn 的运行规模和 conversation 并发；
        extraction、embedding、检索深度、逐 turn add 和 `infer=True` 均保持官方
        benchmark 语义。
        """

        return cls(
            extraction_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            reader_model="gpt-4o-mini",
            top_k=200,
            max_workers=1,
            ingestion_chunk_size=1,
            infer=True,
            api_timeout_seconds=60.0,
            api_max_retries=8,
            profile_name="smoke",
        )

    @classmethod
    def official_full(cls) -> "Mem0Config":
        """返回 Mem0 官方 memory-benchmarks 的 LoCoMo 全量 profile。"""

        return cls(
            extraction_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            reader_model="gpt-4o-mini",
            top_k=200,
            max_workers=10,
            ingestion_chunk_size=1,
            infer=True,
            api_timeout_seconds=60.0,
            api_max_retries=8,
            profile_name="official_full",
        )

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 API key、base URL 或本地绝对存储路径的公开配置。"""

        return {
            **asdict(self),
            "adapter_version": MEM0_ADAPTER_VERSION,
            "reader_prompt_version": MEM0_READER_PROMPT_VERSION,
            "vector_store_provider": "qdrant",
            "llm_provider": "openai",
            "embedding_provider": "openai",
        }


def build_mem0_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 vendored Mem0 核心源码的确定性身份。

    输入:
        path_settings: 可选项目路径设置；为空时从当前项目根加载。

    输出:
        dict: package version、SHA-256、文件数量和参与哈希的相对路径。

    说明:
        只哈希 `mem0/**/*.py`、根 `pyproject.toml` 和 `LICENSE`。嵌套的
        `memory-benchmarks` 仓库、`.git`、缓存和实验输出不会进入身份。
    """

    settings = path_settings or load_path_settings()
    mem0_root = settings.resolve_third_party_method_path(MEM0_METHOD_DIRECTORY)
    pyproject_path = mem0_root / "pyproject.toml"
    if not pyproject_path.is_file():
        raise ConfigurationError(f"Mem0 pyproject.toml missing: {pyproject_path}")

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    package_version = str(pyproject.get("project", {}).get("version", "")).strip()
    if not package_version:
        raise ConfigurationError("Mem0 package version missing from pyproject.toml")

    source_files = sorted(
        [
            path
            for path in (mem0_root / "mem0").rglob("*.py")
            if "__pycache__" not in path.parts
        ]
        + [
            path
            for path in (mem0_root / "pyproject.toml", mem0_root / "LICENSE")
            if path.is_file()
        ],
        key=lambda path: path.relative_to(mem0_root).as_posix(),
    )
    benchmark_prompt_files = [
        mem0_root / "memory-benchmarks" / "benchmarks" / "locomo" / "prompts.py",
        mem0_root / "memory-benchmarks" / "benchmarks" / "longmemeval" / "prompts.py",
    ]
    source_files.extend(path for path in benchmark_prompt_files if path.is_file())
    source_files = sorted(
        source_files,
        key=lambda path: path.relative_to(mem0_root).as_posix(),
    )
    if not source_files:
        raise ConfigurationError(f"Mem0 source files missing: {mem0_root}")

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative_path = source_file.relative_to(mem0_root).as_posix()
        relative_paths.append(relative_path)
        path_bytes = relative_path.encode("utf-8")
        content = source_file.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, byteorder="big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, byteorder="big"))
        digest.update(content)

    return {
        "package_version": package_version,
        "source_sha256": digest.hexdigest(),
        "file_count": len(relative_paths),
        "files": relative_paths,
    }


class Mem0(BaseMemoryProvider, BaseResumableMemorySystem, MemoryProvider):
    """使用官方 Mem0 OSS `Memory` 算法的统一 memory system。"""

    consume_granularity: ConsumeGranularity = "turn"
    provenance_granularity = "none"

    def __init__(
        self,
        config: Mem0Config | None = None,
        openai_settings: OpenAISettings | None = None,
        storage_root: str | Path | None = None,
        memory_backend: Any | None = None,
        reader_client: Any | None = None,
        path_settings: PathSettings | None = None,
        existing_conversation_ids: set[str] | None = None,
        efficiency_collector: EfficiencyCollector | None = None,
        consume_granularity: ConsumeGranularity | None = None,
        session_memory_report: bool = False,
    ):
        """初始化 Mem0 adapter。

        输入:
            config: smoke/full 参数；为空时使用 smoke，避免无意启动昂贵全量配置。
            openai_settings: extraction、embedding 和 reader 的 OpenAI-compatible 配置。
            storage_root: 当前 run 的 Mem0 Qdrant/history 状态目录。
            memory_backend: 测试可注入 fake；为空时从 vendored Mem0 源码构造。
            reader_client: 测试可注入 fake；为空时构造 OpenAI client。
            path_settings: 可选项目路径设置。
            existing_conversation_ids: resume 已验证为完成写入的 namespace 集合。
            efficiency_collector: runner 管理的可选效率 observation collector。
            consume_granularity: v3 provider 实例级消费粒度；registry 会按 benchmark
                profile 设置，缺省为 LoCoMo 官方 turn 级。
            session_memory_report: 是否在 session 边界公开 Mem0 本 session 新增记忆。

        输出:
            None。构造生产 backend 时不会调用 API，但会初始化本地 Qdrant 和客户端。
        """

        self.config = config or Mem0Config.smoke()
        self._efficiency_collector = efficiency_collector
        self.path_settings = path_settings or load_path_settings()
        settings = openai_settings
        if memory_backend is None or reader_client is None:
            settings = settings or load_settings(
                project_root=self.path_settings.project_root
            ).openai

        if storage_root is None:
            selected_storage_root = (
                self.path_settings.outputs_root / "mem0" / "unscoped-method-state"
            )
        else:
            selected_storage_root = Path(storage_root)
        self.storage_root = selected_storage_root.expanduser().resolve()

        creates_production_backend = memory_backend is None
        if creates_production_backend:
            if settings is None:
                raise ConfigurationError("Mem0 production backend requires OpenAI settings")
            self.storage_root.mkdir(parents=True, exist_ok=True)
            memory_backend = self._create_memory_backend(settings)
            self._prewarm_entity_store(memory_backend)
        if reader_client is None:
            if settings is None:
                raise ConfigurationError("Mem0 reader requires OpenAI settings")
            reader_client = OpenAI(**settings.to_client_kwargs())

        self._memory = memory_backend
        self._reader = reader_client
        self._namespace_lock = threading.RLock()
        self._added_conversation_ids = set(existing_conversation_ids or ())
        self._conversation_metadata: dict[str, dict[str, Any]] = {}
        self._native_speaker_roles: dict[str, dict[str, str]] = {}
        self._session_report_memories: dict[tuple[str, str | None], list[str]] = {}
        self.session_memory_report = session_memory_report
        if consume_granularity is not None:
            self.consume_granularity = consume_granularity
        if any(not conversation_id.strip() for conversation_id in self._added_conversation_ids):
            raise ConfigurationError(
                "Mem0 existing_conversation_ids cannot contain empty ids"
            )
        self._configure_backend_openai_clients()
        self._install_efficiency_observers()

    @staticmethod
    def build_backend_config(
        config: Mem0Config,
        openai_settings: OpenAISettings,
        storage_root: str | Path,
    ) -> dict[str, Any]:
        """构造只传给 Mem0 `Memory.from_config()` 的内部配置。

        输入:
            config: 当前 Mem0 profile。
            openai_settings: 含 API key/base URL 的私有配置。
            storage_root: 当前实验的 method state 目录。

        输出:
            dict: extraction、embedding、Qdrant 和 history DB 配置。该字典含 secret，
            不能写入日志、manifest 或 artifact。
        """

        root = Path(storage_root).expanduser().resolve()
        return {
            "version": "v1.1",
            "llm": {
                "provider": "openai",
                "config": {
                    "model": config.extraction_model,
                    "temperature": 0.1,
                    "api_key": openai_settings.api_key,
                    "openai_base_url": openai_settings.base_url,
                },
            },
            "embedder": {
                "provider": "openai",
                "config": {
                    "model": config.embedding_model,
                    "embedding_dims": config.embedding_dimensions,
                    "api_key": openai_settings.api_key,
                    "openai_base_url": openai_settings.base_url,
                },
            },
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "path": str(root / "qdrant"),
                    "collection_name": "mem0",
                    "embedding_model_dims": config.embedding_dimensions,
                },
            },
            "history_db_path": str(root / "history.db"),
        }

    def add(self, conversations: Conversation | list[Conversation]) -> AddResult:
        """按原始顺序逐 turn 写入一个或多个 conversation。

        输入:
            conversations: runner 已清洗的单个公开 conversation，或迁移期兼容列表。

        输出:
            AddResult: 成功写入的 conversation ids 和公开统计信息。
        """

        if isinstance(conversations, Conversation):
            conversations = [conversations]
        if not conversations:
            raise ConfigurationError("Mem0.add() requires at least one conversation")

        conversation_ids: list[str] = []
        turn_count = 0
        for conversation in conversations:
            if self._is_longmemeval_conversation(conversation):
                result = self._add_longmemeval_conversation(conversation)
            else:
                result = self.add_from_turn(
                    conversation=conversation,
                    start_turn_index=0,
                    on_turn_started=lambda index, turn: None,
                    on_turn_completed=lambda index, turn: None,
                )
            conversation_ids.extend(result.conversation_ids)
            turn_count += int(result.metadata.get("turn_count", 0))

        return AddResult(
            conversation_ids=conversation_ids,
            metadata={
                "method": "mem0",
                "turn_count": turn_count,
                "infer": self.config.infer,
            },
        )

    def supports_turn_resume(self, conversation: Conversation) -> bool:
        """Mem0 统一交给 runner 使用 conversation-level resume。

        输入:
            conversation: runner 清洗后的公开 conversation。

        输出:
            bool: 始终返回 False。LoCoMo 内部仍按官方 `CHUNK_SIZE=1` 逐条调用
            Mem0 `Memory.add()`，但不再暴露 runner turn checkpoint。
        """

        return False

    def ingest(self, unit: IngestUnit) -> IngestResult:
        """按 v3 协议写入一个 turn、pair 或 session 单元。"""

        if isinstance(unit, TurnEvent):
            self._ingest_native_turn(unit)
            return IngestResult(unit_ref=UnitRef(unit.isolation_key))
        if isinstance(unit, TurnPair):
            self._ingest_native_pair(unit)
            return IngestResult(unit_ref=UnitRef(unit.isolation_key))
        if isinstance(unit, SessionBatch):
            self._ingest_native_session(unit)
            return IngestResult(unit_ref=UnitRef(unit.isolation_key))
        raise ConfigurationError(
            "Mem0 native provider only accepts TurnEvent, TurnPair or "
            "SessionBatch ingest units"
        )

    def _ingest_native_turn(self, event: TurnEvent) -> None:
        """写入 v3 turn 单元，复用旧 turn message 构造逻辑。"""

        self._ensure_native_namespace(event)
        speaker_roles = self._native_speaker_roles.setdefault(event.isolation_key, {})
        turn = self._turn_from_event(event)
        if turn.speaker not in speaker_roles:
            speaker_roles[turn.speaker] = (
                "user" if len(speaker_roles) % 2 == 0 else "assistant"
            )
        session_time = self._session_time_from_event(event)
        self._memory.add(
            [self._turn_to_message(turn, speaker_roles, session_time=session_time)],
            run_id=event.isolation_key,
            metadata=self._native_turn_metadata(event),
            infer=self.config.infer,
            prompt=self._observation_time_prompt(session_time),
        )

    def _ingest_native_pair(self, pair: TurnPair) -> None:
        """写入 v3 pair 单元，保持 LongMemEval 官方两 turn 批次。"""

        first = pair.first
        self._ensure_native_namespace(first)
        speaker_roles = self._native_speaker_roles.setdefault(first.isolation_key, {})
        turns = [self._turn_from_event(event) for event in pair.turns]
        for turn in turns:
            if turn.speaker not in speaker_roles:
                speaker_roles[turn.speaker] = (
                    "user" if len(speaker_roles) % 2 == 0 else "assistant"
                )
        session_time = self._session_time_from_event(first)
        conversation = self._native_conversation_from_event(first)
        session = self._native_session_from_event(first)
        self._memory.add(
            [
                self._turn_to_message(
                    turn,
                    speaker_roles,
                    session_time=session_time,
                )
                for turn in turns
            ],
            run_id=first.isolation_key,
            metadata=self._turn_batch_metadata(conversation, session, turns),
            infer=self.config.infer,
            prompt=self._observation_time_prompt(session_time),
        )

    def _ingest_native_session(self, batch: SessionBatch) -> None:
        """按 Mem0 官方 LongMemEval `CHUNK_SIZE=2` 写入一个 v3 session 单元。

        官方脚本对 session 消息按位置两两切块、不裁剪开头非 user 消息；
        该口径保留在 adapter 内部，避免框架级 user 锚定配对改变官方分组
        （LongMemEval 约 8% 的 session 不以 user 开头）。
        """

        first = batch.events[0]
        self._ensure_native_namespace(first)
        speaker_roles = self._native_speaker_roles.setdefault(batch.isolation_key, {})
        turns = [self._turn_from_event(event) for event in batch.events]
        for turn in turns:
            if turn.speaker not in speaker_roles:
                speaker_roles[turn.speaker] = (
                    "user" if len(speaker_roles) % 2 == 0 else "assistant"
                )
        session_time = self._session_time_from_event(first)
        conversation = self._native_conversation_from_event(first)
        session = self._native_session_from_event(first)
        report_key = (batch.isolation_key, session.session_id)
        if self.session_memory_report:
            self._session_report_memories[report_key] = []
        for start in range(0, len(turns), 2):
            chunk = turns[start : start + 2]
            add_result = self._memory.add(
                [
                    self._turn_to_message(
                        turn,
                        speaker_roles,
                        session_time=session_time,
                    )
                    for turn in chunk
                ],
                run_id=batch.isolation_key,
                metadata=self._turn_batch_metadata(conversation, session, chunk),
                infer=self.config.infer,
                prompt=self._observation_time_prompt(session_time),
            )
            if self.session_memory_report:
                self._session_report_memories[report_key].extend(
                    self._memory_texts_from_add_result(add_result)
                )

    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None:
        """在 HaluMem session 边界返回本 session 的 Mem0 add().results 记忆。"""

        if not self.session_memory_report:
            return None
        memories = self._session_report_memories.pop(
            (ref.isolation_key, ref.session_id),
            [],
        )
        return SessionMemoryReport(
            session_ref=ref,
            memories=memories,
            metadata={
                "method": "mem0",
                "source": "mem0_add_results",
            },
        )

    def _ensure_native_namespace(self, event: TurnEvent) -> None:
        """首次看到 v3 isolation_key 时登记 namespace 与公开 metadata。"""

        namespace = event.isolation_key
        with self._namespace_lock:
            if namespace not in self._added_conversation_ids:
                self._added_conversation_ids.add(namespace)
        self._conversation_metadata[namespace] = self._native_public_metadata(event)

    def _native_conversation_from_event(self, event: TurnEvent) -> Conversation:
        """构造供旧 helper 复用的最小公开 conversation。"""

        return Conversation(
            conversation_id=self._conversation_id_from_event(event),
            sessions=[],
            metadata=self._native_public_metadata(event),
        )

    def _native_session_from_event(self, event: TurnEvent) -> Session:
        """构造供旧 helper 复用的最小公开 session。"""

        return Session(
            session_id=event.session_id or "",
            turns=[],
            session_time=self._session_time_from_event(event),
        )

    @staticmethod
    def _turn_from_event(event: TurnEvent) -> Turn:
        """从规范 TurnEvent 恢复旧 adapter helper 需要的 Turn。"""

        return Turn(
            turn_id=event.turn_id,
            speaker=event.speaker_name or event.role,
            content=Mem0._original_content_from_event(event),
            normalized_role=event.role if event.role in VALID_MESSAGE_ROLES else None,
            turn_time=Mem0._optional_event_text(event, "original_turn_time"),
            images=Mem0._images_from_event(event),
            metadata=dict(event.metadata.get("turn_metadata") or {}),
        )

    @staticmethod
    def _native_turn_metadata(event: TurnEvent) -> dict[str, Any]:
        """构造 v3 turn 写入 Mem0 时使用的公开定位元信息。"""

        metadata: dict[str, Any] = {
            "conversation_id": Mem0._conversation_id_from_event(event),
            "session_id": event.session_id,
            "turn_id": event.turn_id,
            "speaker": event.speaker_name or event.role,
        }
        session_time = Mem0._session_time_from_event(event)
        turn_time = Mem0._optional_event_text(event, "original_turn_time")
        if session_time:
            metadata["session_time"] = session_time
        if turn_time:
            metadata["turn_time"] = turn_time
        return metadata

    @staticmethod
    def _native_public_metadata(event: TurnEvent) -> dict[str, Any]:
        """恢复 v3 事件中携带的 conversation 级公开 metadata。"""

        metadata = dict(event.metadata.get("conversation_metadata") or {})
        metadata["conversation_id"] = Mem0._conversation_id_from_event(event)
        explicit_reference_date = (
            metadata.get("reference_date") or metadata.get("question_reference_date")
        )
        if explicit_reference_date is not None and str(explicit_reference_date).strip():
            metadata["reference_date"] = str(explicit_reference_date).strip()
        else:
            session_time = Mem0._session_time_from_event(event)
            if session_time:
                metadata.setdefault("reference_date", session_time)
        return metadata

    @staticmethod
    def _conversation_id_from_event(event: TurnEvent) -> str:
        """从 v3 event metadata 中读取原始 conversation id。"""

        conversation_id = event.metadata.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id.strip():
            return conversation_id
        return event.isolation_key

    @staticmethod
    def _session_time_from_event(event: TurnEvent) -> str | None:
        """从 v3 event metadata 中读取原始 session time。"""

        return Mem0._optional_event_text(event, "original_session_time") or event.timestamp

    @staticmethod
    def _original_content_from_event(event: TurnEvent) -> str:
        """读取事件前原始 turn 文本，避免 caption 在 native 路径重复拼接。"""

        original = event.metadata.get("original_content")
        if isinstance(original, str):
            return original
        return event.content

    @staticmethod
    def _optional_event_text(event: TurnEvent, field_name: str) -> str | None:
        """读取 TurnEvent metadata 中的可选文本字段。"""

        value = event.metadata.get(field_name)
        return value if isinstance(value, str) else None

    @staticmethod
    def _images_from_event(event: TurnEvent) -> list[ImageRef]:
        """从 v3 event metadata 恢复公开图片引用。"""

        raw_images = event.metadata.get("turn_images")
        if not isinstance(raw_images, list):
            return []
        images: list[ImageRef] = []
        for raw_image in raw_images:
            if not isinstance(raw_image, dict):
                continue
            images.append(
                ImageRef(
                    image_id=raw_image.get("image_id"),
                    path=raw_image.get("path"),
                    caption=raw_image.get("caption"),
                    metadata=dict(raw_image.get("metadata") or {}),
                )
            )
        return images

    def add_from_turn(
        self,
        conversation: Conversation,
        start_turn_index: int,
        on_turn_started: Callable[[int, Turn], None],
        on_turn_completed: Callable[[int, Turn], None],
    ) -> AddResult:
        """从指定扁平 turn index 继续写入一个 conversation。

        输入:
            conversation: runner 清洗后的公开 conversation。
            start_turn_index: 下一条尚未确认成功的零基 turn index。
            on_turn_started: 调用官方 Mem0 backend 前执行。
            on_turn_completed: backend 成功返回后执行。

        输出:
            AddResult: conversation id 和本次实际写入的 turn 数。
        """

        indexed_turns = [
            (session, turn)
            for session in conversation.sessions
            for turn in session.turns
        ]
        total_turns = len(indexed_turns)
        if total_turns == 0:
            raise ConfigurationError(
                f"Mem0 conversation has no turns: {conversation.conversation_id}"
            )
        if start_turn_index < 0 or start_turn_index > total_turns:
            raise ConfigurationError(
                "Mem0 start_turn_index is outside conversation bounds: "
                f"{start_turn_index} not in [0, {total_turns}]"
            )

        if start_turn_index == 0:
            self._reserve_namespace(conversation.conversation_id)
        else:
            self._attach_existing_namespace(conversation.conversation_id)
        self._conversation_metadata[conversation.conversation_id] = (
            self._conversation_public_metadata(conversation)
        )

        speaker_roles = self._build_speaker_roles(conversation)
        if self._is_longmemeval_conversation(conversation):
            raise ConfigurationError(
                "Mem0 LongMemEval does not support turn-level resume; use "
                "conversation-level add() so the official user+assistant pair "
                "ingestion remains intact."
            )

        written_turn_count = 0
        for turn_index, (session, turn) in enumerate(indexed_turns):
            if turn_index < start_turn_index:
                continue
            on_turn_started(turn_index, turn)
            message = self._turn_to_message(
                turn,
                speaker_roles,
                session_time=session.session_time,
            )
            metadata = self._turn_metadata(conversation, session, turn)
            self._memory.add(
                [message],
                run_id=conversation.conversation_id,
                metadata=metadata,
                infer=self.config.infer,
                prompt=self._observation_time_prompt(session.session_time),
            )
            on_turn_completed(turn_index, turn)
            written_turn_count += 1

        return AddResult(
            conversation_ids=[conversation.conversation_id],
            metadata={
                "method": "mem0",
                "turn_count": written_turn_count,
                "infer": self.config.infer,
                "start_turn_index": start_turn_index,
                "total_turns": total_turns,
            },
        )

    def _add_longmemeval_conversation(self, conversation: Conversation) -> AddResult:
        """按 Mem0 官方 LongMemEval `CHUNK_SIZE=2` 完整写入 conversation。

        输入:
            conversation: 已确认来自 LongMemEval 的公开 conversation。

        输出:
            AddResult: conversation id 和本次覆盖的 turn 数。该路径不支持逐 turn
            checkpoint，runner 应以 conversation-level resume 管理。
        """

        chunks = self._longmemeval_ingestion_chunks(conversation)
        total_turns = sum(len(session.turns) for session in conversation.sessions)
        if total_turns == 0:
            raise ConfigurationError(
                f"Mem0 conversation has no turns: {conversation.conversation_id}"
            )
        self._reserve_namespace(conversation.conversation_id)
        self._conversation_metadata[conversation.conversation_id] = (
            self._conversation_public_metadata(conversation)
        )

        speaker_roles = self._build_speaker_roles(conversation)
        written_turn_count = 0
        for _, session, turns in chunks:
            messages = [
                self._turn_to_message(
                    turn,
                    speaker_roles,
                    session_time=session.session_time,
                )
                for turn in turns
            ]
            self._memory.add(
                messages,
                run_id=conversation.conversation_id,
                metadata=self._turn_batch_metadata(conversation, session, turns),
                infer=self.config.infer,
                prompt=self._observation_time_prompt(session.session_time),
            )
            written_turn_count += len(turns)

        return AddResult(
            conversation_ids=[conversation.conversation_id],
            metadata={
                "method": "mem0",
                "turn_count": written_turn_count,
                "infer": self.config.infer,
                "ingestion_chunk_size": 2,
            },
        )

    def retrieve(self, question: Question | RetrievalQuery) -> AnswerPromptResult | RetrievalResult:
        """检索当前 question 所属 conversation，并构造完整 Mem0 prompt messages。

        输入:
            question: 不含 gold/evidence 的公开问题，或 v3 RetrievalQuery。

        输出:
            AnswerPromptResult 或 RetrievalResult: `prompt_messages` 可直接交给
            framework answer LLM。
        """

        if isinstance(question, RetrievalQuery):
            return self._retrieve_native(question)

        with self._namespace_lock:
            is_added = question.conversation_id in self._added_conversation_ids
        if not is_added:
            raise ConfigurationError(
                "Mem0 question conversation was not added: "
                f"{question.conversation_id}"
            )
        if not question.text.strip():
            raise ConfigurationError(
                f"Mem0 question text is empty: {question.question_id}"
            )

        retrieval_started_ns = perf_counter_ns()
        collector = self._efficiency_collector
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                raw_result = self._memory.search(
                    question.text,
                    filters={"run_id": question.conversation_id},
                    top_k=self.config.top_k,
                )
        else:
            raw_result = self._memory.search(
                question.text,
                filters={"run_id": question.conversation_id},
                top_k=self.config.top_k,
            )
        memories = self._normalize_search_results(raw_result)
        injected_memory_text = self._memory_context_text(memories)
        reader_messages = self._reader_messages(question, memories)
        answer_prompt = _messages_to_answer_prompt(reader_messages)
        if collector is not None and collector.enabled:
            collector.record_retrieval_result(
                latency_ms=_elapsed_ms(retrieval_started_ns),
                injected_memory_context_tokens=(
                    self._count_tokens(injected_memory_text, self.config.reader_model)
                    if injected_memory_text
                    else 0
                ),
            )

        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt=answer_prompt,
            prompt_messages=_prompt_messages_from_dicts(reader_messages),
            metadata={
                "method": "mem0",
                "answer_context": injected_memory_text,
                "retrieved_memories": [
                    {
                        "content": memory["memory"],
                        "score": memory.get("score"),
                        "created_at": memory.get("created_at"),
                    }
                    for memory in memories
                ],
                "retrieved_memory_count": len(memories),
                "top_k": self.config.top_k,
                "answer_prompt_profile": self._reader_prompt_kind(question),
            },
        )

    def _retrieve_native(self, query: RetrievalQuery) -> RetrievalResult:
        """执行 v3 检索并返回不生成最终答案的 RetrievalResult。"""

        with self._namespace_lock:
            is_added = query.isolation_key in self._added_conversation_ids
        if not is_added:
            raise ConfigurationError(
                "Mem0 query isolation_key was not ingested: "
                f"{query.isolation_key}"
            )
        source_question = query.source_question or Question(
            question_id=query.isolation_key,
            conversation_id=query.isolation_key,
            text=query.query_text,
            question_time=query.question_time,
        )
        native_question = Question(
            question_id=source_question.question_id,
            conversation_id=query.isolation_key,
            text=query.query_text,
            question_time=query.question_time or source_question.question_time,
            category=source_question.category,
            metadata=dict(source_question.metadata),
        )
        if not native_question.text.strip():
            raise ConfigurationError(
                f"Mem0 question text is empty: {native_question.question_id}"
            )

        retrieval_started_ns = perf_counter_ns()
        collector = self._efficiency_collector
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                raw_result = self._memory.search(
                    native_question.text,
                    filters={"run_id": query.isolation_key},
                    top_k=self.config.top_k,
                )
        else:
            raw_result = self._memory.search(
                native_question.text,
                filters={"run_id": query.isolation_key},
                top_k=self.config.top_k,
            )
        memories = self._normalize_search_results(raw_result)
        injected_memory_text = self._memory_context_text(memories)
        reader_messages = self._reader_messages(native_question, memories)
        if collector is not None and collector.enabled:
            collector.record_retrieval_result(
                latency_ms=_elapsed_ms(retrieval_started_ns),
                injected_memory_context_tokens=(
                    self._count_tokens(injected_memory_text, self.config.reader_model)
                    if injected_memory_text
                    else 0
                ),
            )

        formatted_memory = (
            injected_memory_text if injected_memory_text else "(No relevant memories found)"
        )
        return RetrievalResult(
            formatted_memory=formatted_memory,
            prompt_messages=tuple(_prompt_messages_from_dicts(reader_messages)),
            items=tuple(
                RetrievedItem(
                    item_id=f"mem0:{index}",
                    content=memory["memory"],
                    score=memory.get("score"),
                    timestamp=memory.get("created_at"),
                )
                for index, memory in enumerate(memories)
            ),
            metadata={
                "method": "mem0",
                "answer_context": injected_memory_text,
                "retrieved_memories": [
                    {
                        "content": memory["memory"],
                        "score": memory.get("score"),
                        "created_at": memory.get("created_at"),
                    }
                    for memory in memories
                ],
                "retrieved_memory_count": len(memories),
                "top_k": self.config.top_k,
                "answer_prompt_profile": self._reader_prompt_kind(native_question),
            },
        )

    def get_answer(self, question: Question) -> AnswerResult:
        """在 question 所属 conversation namespace 内检索并生成回答。

        输入:
            question: 不含 gold/evidence 的公开问题。

        输出:
            AnswerResult: reader 生成的非空答案和不含原始记忆的公开诊断信息。
        """

        prompt_result = self.retrieve(question)
        reader_messages = [{"role": "user", "content": prompt_result.answer_prompt}]
        answer_started_ns = perf_counter_ns()
        collector = self._efficiency_collector
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.ANSWER):
                response = self._reader.chat.completions.create(
                    model=self.config.reader_model,
                    messages=reader_messages,
                )
        else:
            response = self._reader.chat.completions.create(
                model=self.config.reader_model,
                messages=reader_messages,
            )
        answer_latency_ms = _elapsed_ms(answer_started_ns)
        answer = self._extract_reader_answer(response)
        if self._reader_prompt_kind(question) == "locomo":
            answer = self._extract_final_answer(answer)
        if not answer:
            raise ConfigurationError(
                f"Mem0 reader returned an empty answer: {question.question_id}"
            )
        if collector is not None and collector.enabled:
            collector.record_answer_generation(latency_ms=answer_latency_ms)
            with collector.operation_stage(EfficiencyStage.ANSWER):
                self._record_reader_llm_call(
                    response=response,
                    messages=reader_messages,
                    answer=answer,
                )

        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=answer,
            metadata={
                "method": "mem0",
                "retrieved_memory_count": prompt_result.metadata.get(
                    "retrieved_memory_count",
                    0,
                ),
                "top_k": self.config.top_k,
                "reader_model": self.config.reader_model,
            },
        )

    def _create_memory_backend(self, openai_settings: OpenAISettings) -> Any:
        """从 vendored Mem0 源码构造官方 `Memory` backend。"""

        os.environ["MEM0_TELEMETRY"] = "False"
        mem0_root = self.path_settings.resolve_third_party_method_path(
            MEM0_METHOD_DIRECTORY
        )
        root_text = str(mem0_root)
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
        importlib.invalidate_caches()
        try:
            mem0_module = importlib.import_module("mem0")
        except Exception as exc:
            raise ConfigurationError(
                f"Failed to import vendored Mem0 source from {mem0_root}: {exc}"
            ) from exc

        module_file = Path(getattr(mem0_module, "__file__", "")).resolve()
        if mem0_root not in module_file.parents:
            raise ConfigurationError(
                f"Imported Mem0 does not come from vendored source: {module_file}"
            )
        backend_config = self.build_backend_config(
            config=self.config,
            openai_settings=openai_settings,
            storage_root=self.storage_root,
        )
        try:
            return mem0_module.Memory.from_config(backend_config)
        except Exception as exc:
            raise ConfigurationError(
                f"Failed to initialize vendored Mem0 backend: {exc}"
            ) from exc

    @staticmethod
    def _prewarm_entity_store(memory_backend: Any) -> None:
        """在 conversation worker 启动前单线程初始化 Mem0 entity store。

        vendored Mem0 2.0.4 的 `entity_store` 属性采用无锁懒加载。共享一个
        `Memory` 实例并发写入时，首次访问可能重复初始化；adapter 在构造阶段访问
        一次该公开属性，以消除这个首次访问竞态。
        """

        try:
            memory_backend.entity_store
        except Exception as exc:
            raise ConfigurationError(
                f"Failed to prewarm Mem0 entity store: {exc}"
            ) from exc

    def _configure_backend_openai_clients(self) -> None:
        """给 vendored Mem0 内部 OpenAI clients 注入 timeout/retry。

        说明:
            当前 Mem0 2.0.4 的 OpenAI LLM 和 OpenAIEmbedding 构造函数不会从
            Mem0 config 读取 timeout/max_retries。这里在 adapter 层对已构造的
            SDK client 调用 `with_options()`，只影响网络兜底，不改变算法、prompt、
            检索或状态写入逻辑。fake 或非 OpenAI client 没有 `with_options()` 时
            保持原样。
        """

        self._configure_owner_openai_client(getattr(self._memory, "llm", None))
        self._configure_owner_openai_client(
            getattr(self._memory, "embedding_model", None)
        )

    def _configure_owner_openai_client(self, owner: Any) -> None:
        """如果对象持有 OpenAI SDK client，则替换为带 timeout/retry 的 client。"""

        if owner is None:
            return
        client = getattr(owner, "client", None)
        with_options = getattr(client, "with_options", None)
        if not callable(with_options):
            return
        configured_client = with_options(
            timeout=self.config.api_timeout_seconds,
            max_retries=self.config.api_max_retries,
        )
        setattr(owner, "client", configured_client)

    def _install_efficiency_observers(self) -> None:
        """给 Mem0 backend 安装纯 observation wrapper，不改变算法返回值。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        self._install_llm_response_callback_observer()
        self._install_embedding_model_observer()

    def _install_llm_response_callback_observer(self) -> None:
        """复用 Mem0 OpenAI LLM 的 response_callback 记录写入阶段 LLM usage。"""

        llm_config = getattr(getattr(self._memory, "llm", None), "config", None)
        if llm_config is None or not hasattr(llm_config, "response_callback"):
            return
        previous_callback = llm_config.response_callback

        def _callback(llm, response, params):
            """先执行原 callback，再记录 extraction LLM token usage。"""

            if previous_callback is not None:
                previous_callback(llm, response, params)
            self._record_memory_llm_call(response=response, params=params)

        llm_config.response_callback = _callback

    def _install_embedding_model_observer(self) -> None:
        """包住 Mem0 embedding_model 的 embed/embed_batch 方法记录 token 和耗时。"""

        embedding_model = getattr(self._memory, "embedding_model", None)
        if embedding_model is None or getattr(
            embedding_model,
            "_memory_benchmark_efficiency_wrapped",
            False,
        ):
            return
        if hasattr(embedding_model, "embed"):
            original_embed = embedding_model.embed

            def _wrapped_embed(text, *args, **kwargs):
                """记录单文本 embedding 调用，并原样返回官方结果。"""

                started_ns = perf_counter_ns()
                result = original_embed(text, *args, **kwargs)
                self._record_embedding_call(
                    texts=[str(text)],
                    latency_ms=_elapsed_ms(started_ns),
                )
                return result

            embedding_model.embed = _wrapped_embed
        if hasattr(embedding_model, "embed_batch"):
            original_embed_batch = embedding_model.embed_batch

            def _wrapped_embed_batch(texts, *args, **kwargs):
                """记录批量 embedding 调用，并原样返回官方结果。"""

                text_list = [str(text) for text in texts]
                started_ns = perf_counter_ns()
                result = original_embed_batch(texts, *args, **kwargs)
                self._record_embedding_call(
                    texts=text_list,
                    latency_ms=_elapsed_ms(started_ns),
                )
                return result

            embedding_model.embed_batch = _wrapped_embed_batch
        embedding_model._memory_benchmark_efficiency_wrapped = True

    def _record_memory_llm_call(self, *, response: Any, params: Any) -> None:
        """记录 Mem0 写入阶段 extraction LLM 的 token usage。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        prompt_tokens, completion_tokens = _extract_usage_tokens(response)
        prompt_text = _messages_to_text(_params_messages(params))
        output_text = self._extract_optional_response_text(response)
        usage = resolve_token_usage(
            api_input_tokens=prompt_tokens,
            api_output_tokens=completion_tokens,
            prompt_text=prompt_text,
            output_text=output_text,
            tokenizer=_TiktokenCounter(self.config.extraction_model),
        )
        collector.record_llm_call(
            model_id="mem0-memory-llm",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_measurement_source=usage.source,
        )

    def _record_reader_llm_call(
        self,
        *,
        response: Any,
        messages: list[dict[str, str]],
        answer: str,
    ) -> None:
        """记录固定 reader LLM 的 token usage。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        prompt_tokens, completion_tokens = _extract_usage_tokens(response)
        usage = resolve_token_usage(
            api_input_tokens=prompt_tokens,
            api_output_tokens=completion_tokens,
            prompt_text=_messages_to_text(messages),
            output_text=answer,
            tokenizer=_TiktokenCounter(self.config.reader_model),
        )
        collector.record_llm_call(
            model_id="mem0-answer-llm",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_measurement_source=usage.source,
        )

    def _record_embedding_call(self, *, texts: list[str], latency_ms: float) -> None:
        """记录 Mem0 embedding 调用的输入 token 和耗时。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        collector.record_embedding_call(
            model_id="mem0-embedding",
            input_tokens=sum(
                self._count_tokens(text, self.config.embedding_model)
                for text in texts
            ),
            latency_ms=latency_ms,
            token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
            latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
        )

    @staticmethod
    def _extract_optional_response_text(response: Any) -> str:
        """尽力从 OpenAI-compatible response 中提取文本，用于 usage 缺失时估算。"""

        try:
            return str(response.choices[0].message.content or "")
        except (AttributeError, IndexError, TypeError):
            return ""

    @staticmethod
    def _count_tokens(text: str, model_name: str) -> int:
        """使用与 OpenAI-compatible 模型匹配的 tokenizer 估算 token 数。"""

        return _TiktokenCounter(model_name).count_tokens(text)

    def _reserve_namespace(self, conversation_id: str) -> None:
        """原子保留 conversation namespace，阻止重复或并发双写。"""

        if not conversation_id.strip():
            raise ConfigurationError("Mem0 conversation_id is required")
        with self._namespace_lock:
            if conversation_id in self._added_conversation_ids:
                raise ConfigurationError(
                    f"Mem0 conversation already added: {conversation_id}"
                )
            self._added_conversation_ids.add(conversation_id)

    def _attach_existing_namespace(self, conversation_id: str) -> None:
        """把已有持久化 namespace 附着到当前 adapter 实例。"""

        if not conversation_id.strip():
            raise ConfigurationError("Mem0 conversation_id is required")
        with self._namespace_lock:
            self._added_conversation_ids.add(conversation_id)

    @staticmethod
    def _build_speaker_roles(conversation: Conversation) -> dict[str, str]:
        """按 speaker 首次出现顺序构造稳定 user/assistant 映射。"""

        roles: dict[str, str] = {}
        for session in conversation.sessions:
            for turn in session.turns:
                if turn.speaker not in roles:
                    roles[turn.speaker] = (
                        "user" if len(roles) % 2 == 0 else "assistant"
                    )
        return roles

    @staticmethod
    def _turn_to_message(
        turn: Turn,
        speaker_roles: dict[str, str],
        session_time: str | None = None,
    ) -> dict[str, str]:
        """把统一 Turn 转成 Mem0 message，并显式保留 speaker 和时间语义。"""

        normalized_role = (turn.normalized_role or "").strip().lower()
        role = (
            normalized_role
            if normalized_role in VALID_MESSAGE_ROLES
            else speaker_roles.get(turn.speaker, "user")
        )
        content_parts = [turn.content.strip()] if turn.content.strip() else []
        content_parts.extend(
            image.caption.strip()
            for image in turn.images
            if image.caption and image.caption.strip()
        )
        if not content_parts:
            raise ConfigurationError(f"Mem0 turn has no text content: {turn.turn_id}")
        time_parts: list[str] = []
        if session_time:
            time_parts.append(f"[Session time: {session_time}]")
        if turn.turn_time:
            time_parts.append(f"[Turn time: {turn.turn_time}]")
        prefix = f"{' '.join(time_parts)} " if time_parts else ""
        return {
            "role": role,
            "content": f"{prefix}{turn.speaker}: {' '.join(content_parts)}",
        }

    @staticmethod
    def _turn_metadata(
        conversation: Conversation,
        session: Any,
        turn: Turn,
    ) -> dict[str, Any]:
        """构造写入 Mem0 的公开 turn 定位元信息。"""

        metadata: dict[str, Any] = {
            "conversation_id": conversation.conversation_id,
            "session_id": session.session_id,
            "turn_id": turn.turn_id,
            "speaker": turn.speaker,
        }
        if session.session_time:
            metadata["session_time"] = session.session_time
        if turn.turn_time:
            metadata["turn_time"] = turn.turn_time
        return metadata

    @staticmethod
    def _turn_batch_metadata(
        conversation: Conversation,
        session: Session,
        turns: list[Turn],
    ) -> dict[str, Any]:
        """构造 LongMemEval pair 写入 Mem0 时使用的公开 batch 元信息。"""

        turn_ids = [turn.turn_id for turn in turns]
        metadata: dict[str, Any] = {
            "conversation_id": conversation.conversation_id,
            "session_id": session.session_id,
            "turn_ids": turn_ids,
            "first_turn_id": turn_ids[0],
            "last_turn_id": turn_ids[-1],
            "speaker": "+".join(turn.speaker for turn in turns),
        }
        if session.session_time:
            metadata["session_time"] = session.session_time
        first_turn_time = turns[0].turn_time
        last_turn_time = turns[-1].turn_time
        if first_turn_time:
            metadata["first_turn_time"] = first_turn_time
        if last_turn_time and last_turn_time != first_turn_time:
            metadata["last_turn_time"] = last_turn_time
        return metadata

    @staticmethod
    def _longmemeval_ingestion_chunks(
        conversation: Conversation,
    ) -> list[tuple[int, Session, list[Turn]]]:
        """按 session 内 2 条一组生成 Mem0 官方 LongMemEval 写入 chunk。"""

        chunks: list[tuple[int, Session, list[Turn]]] = []
        flat_index = 0
        for session in conversation.sessions:
            for session_turn_index in range(0, len(session.turns), 2):
                turns = session.turns[session_turn_index : session_turn_index + 2]
                if turns:
                    chunks.append((flat_index + session_turn_index, session, turns))
            flat_index += len(session.turns)
        return chunks

    @staticmethod
    def _is_longmemeval_conversation(conversation: Conversation) -> bool:
        """根据公开 metadata 判断 conversation 是否来自 LongMemEval。"""

        source_text = " ".join(
            str(value)
            for value in (
                conversation.metadata.get("source_path"),
                conversation.metadata.get("source_format"),
                conversation.metadata.get("variant"),
            )
            if value is not None
        ).lower()
        return "longmemeval" in source_text

    @staticmethod
    def _conversation_public_metadata(conversation: Conversation) -> dict[str, Any]:
        """构造 Mem0 reader 可使用的公开 conversation metadata。

        LoCoMo 官方 answer prompt 需要全局 `reference_date` 辅助相对时间推理。
        数据集未单独提供时，使用当前 conversation 最后一个有值的 session time；
        该时间来自公开历史，不包含 gold answer 或 evidence。
        """

        metadata: dict[str, Any] = {
            **conversation.metadata,
            "conversation_id": conversation.conversation_id,
        }
        explicit_reference_date = (
            metadata.get("reference_date") or metadata.get("question_reference_date")
        )
        if explicit_reference_date is not None and str(explicit_reference_date).strip():
            metadata["reference_date"] = str(explicit_reference_date).strip()
            return metadata
        for session in reversed(conversation.sessions):
            if session.session_time and session.session_time.strip():
                metadata["reference_date"] = session.session_time.strip()
                break
        return metadata

    @staticmethod
    def _observation_time_prompt(session_time: str | None) -> str | None:
        """为 Mem0 提取器构造 session 级相对时间锚点。

        当前 vendored Mem0 的本地 `Memory.add()` 没有 timestamp 参数，且 V3
        提取链不会从 metadata 读取 observation date。这里使用其公开 `prompt`
        扩展点补上传入数据本身已有的 session 时间；没有时间的数据集保持默认行为。
        """

        if not session_time or not session_time.strip():
            return None
        return (
            "The observation date and time for this message is "
            f"'{session_time.strip()}'. Resolve relative time expressions such as "
            "'yesterday', 'today', and 'last week' only against this observation "
            "time, even if another current or observation date appears elsewhere "
            "in the extraction prompt."
        )

    @staticmethod
    def _normalize_search_results(raw_result: Any) -> list[dict[str, Any]]:
        """把 Mem0 不同版本的 search 返回值归一化为记忆字典列表。"""

        if isinstance(raw_result, dict):
            results = raw_result.get("results", [])
        else:
            results = raw_result
        if not isinstance(results, list):
            raise ConfigurationError("Mem0 search results must be a list")

        normalized: list[dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                raise ConfigurationError("Mem0 search result item must be a dict")
            memory = item.get("memory") or item.get("content")
            if memory is None or not str(memory).strip():
                continue
            normalized.append(
                {
                    "memory": str(memory).strip(),
                    "score": item.get("score"),
                    "created_at": item.get("created_at"),
                }
            )
        return normalized

    @staticmethod
    def _memory_texts_from_add_result(raw_result: Any) -> list[str]:
        """从 Mem0 `Memory.add()` 返回值中提取新增 memory 文本。"""

        if not isinstance(raw_result, dict):
            return []
        results = raw_result.get("results")
        if not isinstance(results, list):
            return []
        memories: list[str] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            memory = item.get("memory")
            if isinstance(memory, str) and memory.strip():
                memories.append(memory)
        return memories

    def _reader_messages(
        self,
        question: Question,
        memories: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """构造固定 reader 的 system/user messages。"""

        prompt_kind = self._reader_prompt_kind(question)
        if prompt_kind == "locomo":
            prompt = self._build_mem0_locomo_prompt(question, memories)
            return [{"role": "user", "content": prompt}]
        if prompt_kind == "longmemeval":
            prompt = self._build_mem0_longmemeval_prompt(question, memories)
            return [{"role": "user", "content": prompt}]

        memory_text = Mem0._memory_context_text(memories)
        if not memory_text:
            memory_text = "(No relevant memories found)"
        system_prompt = (
            "Answer the user's question using only the retrieved conversation "
            "memories below. Preserve names, dates and concrete details. "
            "Give a direct concise answer.\n\nRetrieved memories:\n"
            f"{memory_text}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question.text},
        ]

    def _reader_prompt_kind(self, question: Question) -> str:
        """选择 Mem0 官方 benchmark prompt；未知数据集保持通用 fallback。"""

        metadata = self._conversation_metadata.get(question.conversation_id, {})
        source_text = " ".join(
            str(value)
            for value in (
                metadata.get("source_path"),
                metadata.get("source_format"),
                metadata.get("variant"),
                question.metadata.get("source_path"),
                question.metadata.get("source_format"),
            )
            if value is not None
        ).lower()
        category = str(question.category or "").strip()
        if "longmemeval" in source_text or category in LONGMEMEVAL_QUESTION_TYPES:
            return "longmemeval"
        if "locomo" in source_text or category in {"1", "2", "3", "4", "5"}:
            return "locomo"
        if question.question_time:
            return "longmemeval"
        return "generic"

    def _build_mem0_locomo_prompt(
        self,
        question: Question,
        memories: list[dict[str, Any]],
    ) -> str:
        """调用 Mem0 memory-benchmarks 的 LoCoMo answer prompt。"""

        prompt_module = _load_mem0_benchmark_prompt_module(
            self.path_settings,
            "locomo",
        )
        prompt_builder = getattr(prompt_module, "get_answer_generation_prompt")
        metadata = self._conversation_metadata.get(question.conversation_id, {})
        reference_date = (
            metadata.get("reference_date")
            or metadata.get("question_reference_date")
            or _reference_year_from_memories(memories)
            or "2023"
        )
        return prompt_builder(
            question=question.text,
            search_results=memories,
            reference_date=str(reference_date),
            user_profile=None,
        )

    def _build_mem0_longmemeval_prompt(
        self,
        question: Question,
        memories: list[dict[str, Any]],
    ) -> str:
        """调用 Mem0 memory-benchmarks 的 LongMemEval answer prompt。"""

        if not question.question_time:
            raise ConfigurationError(
                "Mem0 LongMemEval official prompt requires question_time: "
                f"{question.question_id}"
            )
        prompt_module = _load_mem0_benchmark_prompt_module(
            self.path_settings,
            "longmemeval",
        )
        prompt_builder = getattr(prompt_module, "get_answer_generation_prompt")
        return prompt_builder(
            question=question.text,
            search_results=memories,
            question_date=question.question_time,
            user_profile=None,
        )

    @staticmethod
    def _memory_context_text(memories: list[dict[str, Any]]) -> str:
        """返回实际注入 reader prompt 的记忆文本；无记忆时为空串。"""

        return "\n".join(f"- {memory['memory']}" for memory in memories)

    @staticmethod
    def _extract_reader_answer(response: Any) -> str:
        """从 OpenAI-compatible chat completion 中提取文本答案。"""

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise ConfigurationError(
                "Mem0 reader returned an unsupported response shape"
            ) from exc
        return str(content or "").strip()

    @staticmethod
    def _extract_final_answer(text: str) -> str:
        """从 LoCoMo 推理链文本中提取最终 ANSWER: 之后的部分。

        LoCoMo 官方 prompt 指示 LLM 输出 7 步推理 + "ANSWER:" 标记后的最终答案。
        若无 "ANSWER:" 标记，返回原文（兼容旧 prompt 或无推理链的输出）。
        """

        idx = text.rfind("ANSWER:")
        if idx == -1:
            return text
        return text[idx + len("ANSWER:"):].strip()


class _TiktokenCounter:
    """按 OpenAI-compatible 模型名计数 token 的轻量 wrapper。"""

    def __init__(self, model_name: str) -> None:
        """保存模型名，encoding 懒加载以避免无观测路径额外开销。"""

        self.model_name = model_name
        self._encoding = None

    def count_tokens(self, text: str) -> int:
        """返回文本 token 数；未知模型回退到 cl100k_base。"""

        if self._encoding is None:
            try:
                import tiktoken
            except Exception as exc:
                raise ConfigurationError(
                    "tiktoken is required for Mem0 token estimation"
                ) from exc
            try:
                self._encoding = tiktoken.encoding_for_model(self.model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return len(self._encoding.encode(text or ""))


def _elapsed_ms(started_ns: int) -> float:
    """把 perf_counter_ns 起点转换为非负毫秒。"""

    return max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)


def _extract_usage_tokens(response: Any) -> tuple[int | None, int | None]:
    """从 OpenAI-compatible response.usage 中提取 input/output token。"""

    usage = _get_value(response, "usage")
    if usage is None:
        return None, None
    prompt_tokens = _get_first_int(
        usage,
        ("prompt_tokens", "input_tokens"),
    )
    completion_tokens = _get_first_int(
        usage,
        ("completion_tokens", "output_tokens"),
    )
    return prompt_tokens, completion_tokens


def _get_first_int(source: Any, field_names: tuple[str, ...]) -> int | None:
    """按候选字段顺序读取第一个整数 token 值。"""

    for field_name in field_names:
        value = _get_value(source, field_name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _get_value(source: Any, field_name: str) -> Any:
    """兼容 dict 和对象属性读取字段。"""

    if isinstance(source, dict):
        return source.get(field_name)
    return getattr(source, field_name, None)


def _params_messages(params: Any) -> list[Any]:
    """从 Mem0 LLM callback 参数中取出 messages。"""

    messages = _get_value(params, "messages")
    if isinstance(messages, list):
        return messages
    return []


def _messages_to_text(messages: list[Any]) -> str:
    """把 OpenAI message list 拼成稳定纯文本，用于 tokenizer fallback。"""

    parts: list[str] = []
    for message in messages:
        role = _get_value(message, "role")
        content = _get_value(message, "content")
        if role is not None:
            parts.append(str(role))
        if content is not None:
            parts.append(str(content))
    return "\n".join(parts)


def _load_mem0_benchmark_prompt_module(
    path_settings: PathSettings,
    benchmark_name: str,
) -> Any:
    """从 vendored Mem0 memory-benchmarks 加载指定 benchmark 的 prompt 模块。"""

    prompt_path = (
        path_settings.resolve_third_party_method_path(MEM0_METHOD_DIRECTORY)
        / "memory-benchmarks"
        / "benchmarks"
        / benchmark_name
        / "prompts.py"
    )
    if not prompt_path.is_file():
        raise ConfigurationError(f"Mem0 benchmark prompt file missing: {prompt_path}")
    module_name = f"_memory_benchmark_mem0_{benchmark_name}_prompts"
    spec = importlib.util.spec_from_file_location(module_name, prompt_path)
    if spec is None or spec.loader is None:
        raise ConfigurationError(f"Mem0 prompt module cannot be loaded: {prompt_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "get_answer_generation_prompt"):
        raise ConfigurationError(
            f"Mem0 prompt module missing get_answer_generation_prompt: {prompt_path}"
        )
    return module


def _reference_year_from_memories(memories: list[dict[str, Any]]) -> str | None:
    """从检索结果 `created_at` 推断 LoCoMo reference year。"""

    for memory in memories:
        created_at = memory.get("created_at")
        if isinstance(created_at, str) and len(created_at) >= 4:
            year = created_at[:4]
            if year.isdigit():
                return year
    return None


def _messages_to_answer_prompt(messages: list[dict[str, str]]) -> str:
    """把 method reader messages 转为单条 answer LLM prompt。"""

    if len(messages) == 1:
        return messages[0].get("content", "")
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").upper()
        content = str(message.get("content") or "").strip()
        if content:
            parts.append(f"{role}:\n{content}")
    return "\n\n".join(parts)


def _prompt_messages_from_dicts(messages: list[dict[str, str]]) -> list[PromptMessage]:
    """把官方 reader message 字典转换为核心 PromptMessage。"""

    prompt_messages: list[PromptMessage] = []
    for message in messages:
        role = str(message.get("role") or "user")
        content = str(message.get("content") or "")
        if content.strip():
            prompt_messages.append(PromptMessage(role=role, content=content))
    return prompt_messages


__all__ = [
    "Mem0",
    "Mem0Config",
    "build_mem0_source_identity",
]

"""LightMem 的 conversation-QA 适配器。

本模块包装 `third_party/methods/LightMem/` 中的官方 LightMemory。Adapter 负责配置、
conversation 隔离、状态路径和统一接口；不重写 LightMem 的核心记忆算法。
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import importlib
import importlib.util
import io
from pathlib import Path
import re
import shutil
import sys
import threading
from time import perf_counter_ns
from typing import Any

from openai import OpenAI

from memory_benchmark.config.settings import (
    OpenAISettings,
    PathSettings,
    load_path_settings,
)
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Question,
    AnswerPromptResult,
    PromptMessage,
    Session,
    Turn,
)
from memory_benchmark.core.interfaces import BaseMemoryProvider, BaseMemorySystem
from memory_benchmark.core.provider_protocol import (
    ConsumeGranularity,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievedItem,
    RetrievalQuery,
    RetrievalResult,
    TurnEvent,
    TurnPair,
    UnitRef,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
    extract_api_token_usage,
    resolve_token_usage,
)


LIGHTMEM_METHOD_DIRECTORY = "LightMem"
LIGHTMEM_ADAPTER_VERSION = "conversation-qa-v1"
LIGHTMEM_READER_PROMPT_VERSION = "lightmem-reader-v1"
LIGHTMEM_MEMORY_LLM_MODEL_ID = "lightmem-memory-llm"
_LIGHTMEM_IMPORT_LOCK = threading.Lock()
LIGHTMEM_MODEL_DOWNLOADS = {
    "embedding_model_path": "sentence-transformers/all-MiniLM-L6-v2",
    "llmlingua_model_path": (
        "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
    ),
}


@dataclass(frozen=True)
class _BufferedMemoryManagerUsage:
    """LightMem 子线程中暂存的 memory manager LLM usage。

    字段:
        input_tokens: API usage 或 tokenizer 回退得到的输入 token 数。
        output_tokens: API usage 或 tokenizer 回退得到的输出 token 数。
        token_measurement_source: token 计量来源，保留 api_usage / tokenizer_estimate
            的区别。
    """

    input_tokens: int
    output_tokens: int
    token_measurement_source: MeasurementSource


@dataclass(frozen=True)
class LightMemConfig:
    """LightMem 运行 profile。

    字段:
        llm_model: LightMem memory manager 和 reader 使用的 LLM。
        embedding_model_path: 本地 embedding 模型路径或名称。
        llmlingua_model_path: 本地 LLMLingua 压缩模型路径或名称。
        retrieve_limit: method 内部检索条数，不进入统一接口参数。
        api_timeout_seconds: OpenAI-compatible 请求超时秒数。
        api_max_retries: OpenAI-compatible 请求最大重试次数。
        max_workers: runner 可读取的建议 conversation 并发数。
        pre_compress: 是否启用官方预压缩。
        compression_rate: LLMLingua-2 预压缩率；LightMem Table 2/3 的
            official-mini profile 使用 0.7。
        stm_threshold: STM buffer 容量阈值。当前 vendored LightMem 源码硬编码
            512 tokens，因此 adapter 只允许显式声明 512。
        topic_segment: 是否启用官方 topic segmentation。
        text_summary: 是否启用文本摘要。
        extract_threshold: LightMem extract_threshold（repo 默认 0.5，
            configs/base.py:58 `default=0.5`）。决定内容是否作为
            metadata/highlight 提取的阈值。归一化前 paper 对齐 0.1，归一化后
            用 repo 默认 0.5。
        offline_update_score_threshold: LightMem offline_update_all_entries 的
            score_threshold（README/tutorial 用 0.8，函数签名默认 0.9）。
            归一化前 paper 对齐 0.9，归一化后用 0.8。
        suppress_official_stdout: 是否压制第三方 stdout。
        profile_name: 可审计 profile 名称。
    """

    llm_model: str
    embedding_model_path: str
    llmlingua_model_path: str
    retrieve_limit: int
    max_workers: int
    api_timeout_seconds: float = 60.0
    api_max_retries: int = 8
    pre_compress: bool = True
    compression_rate: float = 0.7
    stm_threshold: int = 512
    topic_segment: bool = True
    text_summary: bool = True
    embedding_dimensions: int = 384
    embedding_device: str = "cpu"
    extract_threshold: float = 0.5
    offline_update_score_threshold: float = 0.8
    llmlingua_device_map: str = "cpu"
    extraction_mode: str = "flat"
    suppress_official_stdout: bool = True
    profile_name: str = "custom"

    def __post_init__(self) -> None:
        """强校验会影响实验语义的配置。"""

        if not self.llm_model.strip():
            raise ConfigurationError("LightMem llm_model is required")
        if not self.embedding_model_path.strip():
            raise ConfigurationError("LightMem embedding_model_path is required")
        if not self.llmlingua_model_path.strip():
            raise ConfigurationError("LightMem llmlingua_model_path is required")
        if self.retrieve_limit < 1:
            raise ConfigurationError("LightMem retrieve_limit must be positive")
        if self.api_timeout_seconds <= 0:
            raise ConfigurationError("LightMem api_timeout_seconds must be positive")
        if self.api_max_retries < 0:
            raise ConfigurationError("LightMem api_max_retries cannot be negative")
        if self.max_workers < 1:
            raise ConfigurationError("LightMem max_workers must be positive")
        if self.embedding_dimensions < 1:
            raise ConfigurationError("LightMem embedding_dimensions must be positive")
        if self.compression_rate <= 0 or self.compression_rate > 1:
            raise ConfigurationError(
                "LightMem compression_rate must be in the range (0, 1]"
            )
        if not 0 < self.extract_threshold <= 1:
            raise ConfigurationError(
                "LightMem extract_threshold must be in the range (0, 1]"
            )
        if not 0 < self.offline_update_score_threshold <= 1:
            raise ConfigurationError(
                "LightMem offline_update_score_threshold must be in the range (0, 1]"
            )
        if self.stm_threshold != 512:
            raise ConfigurationError(
                "LightMem stm_threshold currently must be 512 because the vendored "
                "LightMem ShortMemBufferManager hardcodes max_tokens=512"
            )
        if self.extraction_mode not in {"flat", "event"}:
            raise ConfigurationError("LightMem extraction_mode must be flat or event")

    def validate_required_local_resources(self, path_settings: PathSettings) -> None:
        """校验当前 profile 声明的本地模型资源是否存在。

        输入:
            path_settings: 项目路径配置，用于解析 `models/...` 这类相对路径。

        输出:
            无返回值；资源齐全时直接返回。

        异常:
            ConfigurationError: 配置指向本地模型路径但该目录不存在。
        """

        required_models = (
            ("embedding_model_path", self.embedding_model_path),
            ("llmlingua_model_path", self.llmlingua_model_path),
        )
        missing: list[str] = []
        for field_name, model_reference in required_models:
            local_path = _resolve_local_model_reference(
                model_reference,
                path_settings.project_root,
            )
            if local_path is not None and not local_path.is_dir():
                download_source = LIGHTMEM_MODEL_DOWNLOADS[field_name]
                missing.append(
                    f"{field_name}={local_path} "
                    f"(expected {download_source})"
                )

        if missing:
            missing_text = "; ".join(missing)
            raise ConfigurationError(
                "LightMem required local model resources missing: "
                f"{missing_text}. Put the models under the configured paths "
                "before running real LightMem prediction."
            )

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 secret 和绝对存储路径的公开配置。"""

        return {
            **asdict(self),
            "adapter_version": LIGHTMEM_ADAPTER_VERSION,
            "reader_prompt_version": LIGHTMEM_READER_PROMPT_VERSION,
            "llm_provider": "openai-compatible",
            "embedding_provider": "huggingface-local",
        }


def import_lightmem_classes(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """从 vendored LightMem 源码导入官方 LightMemory 类。

    输入:
        path_settings: 项目路径配置；为空时自动加载。

    输出:
        dict: 官方 LightMemory 类。
    """

    settings = path_settings or load_path_settings()
    lightmem_root = settings.resolve_third_party_method_path(LIGHTMEM_METHOD_DIRECTORY)
    src_root = lightmem_root / "src"
    if not (src_root / "lightmem" / "memory" / "lightmem.py").is_file():
        raise ConfigurationError(f"LightMem source package missing: {src_root}")

    root_text = str(src_root)
    with _LIGHTMEM_IMPORT_LOCK:
        if root_text not in sys.path:
            sys.path.insert(0, root_text)
        module = importlib.import_module("lightmem.memory.lightmem")
        return {"LightMemory": module.LightMemory}


def build_lightmem_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 vendored LightMem 关键源码的确定性身份。"""

    settings = path_settings or load_path_settings()
    lightmem_root = settings.resolve_third_party_method_path(LIGHTMEM_METHOD_DIRECTORY)
    required_files = [
        "README.md",
        "pyproject.toml",
        "src/lightmem/memory/lightmem.py",
        "experiments/locomo/add_locomo.py",
        "experiments/locomo/search_locomo.py",
        "experiments/locomo/prompts.py",
        "experiments/longmemeval/run_lightmem_gpt.py",
    ]
    source_files = [lightmem_root / relative_path for relative_path in required_files]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise ConfigurationError(f"LightMem source files missing: {missing_text}")

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative_path = source_file.relative_to(lightmem_root).as_posix()
        relative_paths.append(relative_path)
        path_bytes = relative_path.encode("utf-8")
        content = source_file.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, byteorder="big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, byteorder="big"))
        digest.update(content)

    return {
        "source_sha256": digest.hexdigest(),
        "file_count": len(relative_paths),
        "files": relative_paths,
    }


class LightMem(BaseMemoryProvider, BaseMemorySystem, MemoryProvider):
    """使用官方 LightMemory 的统一 memory system。"""

    consume_granularity: ConsumeGranularity = "turn"
    provenance_granularity = "turn"

    def __init__(
        self,
        config: LightMemConfig,
        backend_factory: Callable[[str], Any] | None = None,
        answer_client: Any | None = None,
        openai_settings: OpenAISettings | None = None,
        storage_root: str | Path | None = None,
        path_settings: PathSettings | None = None,
        efficiency_collector: EfficiencyCollector | None = None,
        consume_granularity: ConsumeGranularity | None = None,
    ):
        """初始化 LightMem adapter。

        输入:
            config: LightMem 强类型 profile。
            backend_factory: 测试可注入 fake；生产为空时后续任务构造官方 LightMemory。
            answer_client: 测试可注入 fake reader。
            openai_settings: 传给官方 memory manager 和固定 reader 的 OpenAI-compatible 配置。
            storage_root: 当前 run 独占的 LightMem Qdrant/log 状态目录。
            path_settings: 项目路径配置。
            efficiency_collector: runner 管理的可选效率 observation collector。
            consume_granularity: v3 provider 实例级消费粒度；registry 按 benchmark
                profile 设置，缺省为 LoCoMo turn 级。
        """

        self.config = config
        self._backend_factory = backend_factory
        self.path_settings = path_settings or load_path_settings()
        self._openai_settings = openai_settings
        self.storage_root = (
            Path(storage_root)
            if storage_root is not None
            else self.path_settings.outputs_root / "lightmem" / "unscoped-method-state"
        ).expanduser().resolve()
        if answer_client is None and openai_settings is not None:
            answer_client = _OpenAIAnswerClient(
                client=OpenAI(**openai_settings.to_client_kwargs()),
                model=config.llm_model,
            )
        self._answer_client = answer_client
        self._efficiency_collector = efficiency_collector
        self._backends: dict[str, Any] = {}
        self._conversation_metadata: dict[str, dict[str, Any]] = {}
        self._memory_manager_usage_lock = threading.Lock()
        self._buffered_memory_manager_usages: dict[
            str,
            list[_BufferedMemoryManagerUsage],
        ] = {}
        self._native_pending_batches: dict[str, list[dict[str, object]]] = {}
        if consume_granularity is not None:
            self.consume_granularity = consume_granularity
        if self._backend_factory is None:
            self.config.validate_required_local_resources(self.path_settings)

    @staticmethod
    def build_backend_config(
        config: LightMemConfig,
        openai_settings: OpenAISettings,
        storage_root: str | Path,
        conversation_id: str,
        project_root: str | Path | None = None,
    ) -> dict[str, Any]:
        """构造只传给官方 `LightMemory.from_config()` 的内部配置。

        输入:
            config: 当前 LightMem profile。
            openai_settings: 含 API key/base URL 的私有配置。
            storage_root: 当前实验 run 的 method state 根目录。
            conversation_id: 当前隔离 conversation id。
            project_root: 用于把 `models/...` 解析成绝对路径的项目根目录。

        输出:
            dict[str, Any]: 官方 LightMemory 配置。该字典含 secret，不能写入
            manifest、日志或 artifact。
        """

        resolved_project_root = (
            Path(project_root).expanduser().resolve()
            if project_root is not None
            else load_path_settings().project_root
        )
        root = Path(storage_root).expanduser().resolve()
        collection_name = _storage_safe_collection_name(conversation_id)
        qdrant_path = root / "qdrant" / collection_name
        summary_qdrant_path = root / "qdrant" / f"{collection_name}_summary"
        embedding_model_reference = _model_reference_for_backend(
            config.embedding_model_path,
            resolved_project_root,
        )
        llmlingua_model_reference = _model_reference_for_backend(
            config.llmlingua_model_path,
            resolved_project_root,
        )
        return {
            "pre_compress": config.pre_compress,
            "pre_compressor": {
                "model_name": "llmlingua-2",
                "configs": {
                    "llmlingua_config": {
                        "model_name": llmlingua_model_reference,
                        "device_map": config.llmlingua_device_map,
                        "use_llmlingua2": True,
                        "model_config": {"attn_implementation": "eager"},
                    },
                    "compress_config": {
                        "instruction": "",
                        "rate": config.compression_rate,
                        "target_token": -1,
                    },
                },
            },
            "topic_segment": config.topic_segment,
            "precomp_topic_shared": True,
            "topic_segmenter": {"model_name": "llmlingua-2"},
            "messages_use": "user_only",
            "metadata_generate": True,
            "text_summary": config.text_summary,
            "memory_manager": {
                "model_name": "openai",
                "configs": {
                    "model": config.llm_model,
                    "api_key": openai_settings.api_key,
                    "max_tokens": 16000,
                    "openai_base_url": openai_settings.base_url,
                },
            },
            "extract_threshold": config.extract_threshold,
            "index_strategy": "embedding",
            "text_embedder": {
                "model_name": "huggingface",
                "configs": {
                    "model": embedding_model_reference,
                    "embedding_dims": config.embedding_dimensions,
                    "model_kwargs": {"device": config.embedding_device},
                },
            },
            "retrieve_strategy": "embedding",
            "embedding_retriever": {
                "model_name": "qdrant",
                "configs": {
                    "collection_name": collection_name,
                    "embedding_model_dims": config.embedding_dimensions,
                    "path": str(qdrant_path),
                    "on_disk": True,
                },
            },
            "summary_retriever": {
                "model_name": "qdrant",
                "configs": {
                    "collection_name": f"{collection_name}_summary",
                    "embedding_model_dims": config.embedding_dimensions,
                    "path": str(summary_qdrant_path),
                    "on_disk": True,
                },
            },
            "update": "offline",
            "logging": {
                "level": "WARNING",
                "file_enabled": True,
                "log_dir": str(root / "logs" / collection_name),
            },
            "extraction_mode": config.extraction_mode,
            "lightmem_profile": {
                "compression_rate": config.compression_rate,
                "stm_threshold": config.stm_threshold,
            },
        }

    def add(self, conversations: Conversation | list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。"""

        if isinstance(conversations, Conversation):
            conversations = [conversations]
        conversation_ids: list[str] = []
        for conversation in conversations:
            backend = self._get_or_create_backend(conversation.conversation_id)
            self._conversation_metadata[conversation.conversation_id] = {
                **conversation.metadata,
                "conversation_id": conversation.conversation_id,
            }
            batches = self._conversation_to_lightmem_batches(conversation)
            locomo_metadata_prompt = self._locomo_metadata_prompt_if_needed(
                conversation
            )
            for batch_index, messages in enumerate(batches):
                is_last_batch = batch_index == len(batches) - 1
                kwargs: dict[str, Any] = {
                    "force_segment": is_last_batch,
                    "force_extract": is_last_batch,
                }
                if locomo_metadata_prompt is not None:
                    kwargs["METADATA_GENERATE_PROMPT"] = locomo_metadata_prompt
                self._suppress_stdout_if_needed(
                    backend.add_memory,
                    messages,
                    **kwargs,
                )
            if _is_locomo_conversation(conversation):
                self._run_locomo_offline_update(backend, conversation.conversation_id)
            self._flush_buffered_memory_manager_usages(conversation.conversation_id)
            conversation_ids.append(conversation.conversation_id)
        return AddResult(conversation_ids=conversation_ids)

    def load_existing_conversation_state(self, conversation: Conversation) -> None:
        """恢复已完成写入的 conversation backend。

        输入:
            conversation: runner 根据 `conversation_status=completed` 传入的公开对象。

        输出:
            None；该方法只重建 LightMemory backend 和公开 metadata，不重新调用
            `add_memory()`。
        """

        if conversation.conversation_id in self._backends:
            return
        backend = self._get_or_create_backend(conversation.conversation_id)
        self._conversation_metadata[conversation.conversation_id] = {
            **conversation.metadata,
            "conversation_id": conversation.conversation_id,
        }
        if backend is None:
            raise ConfigurationError(
                f"LightMem backend cannot be restored: {conversation.conversation_id}"
            )

    def ingest(self, unit: IngestUnit) -> IngestResult:
        """按 v3 协议缓冲一个 turn 或 pair 单元。"""

        if isinstance(unit, TurnEvent):
            namespace = unit.isolation_key
            batch = self._native_turn_batch(unit)
            self._ensure_native_metadata(unit)
        elif isinstance(unit, TurnPair):
            namespace = unit.isolation_key
            batch = self._native_pair_batch(unit)
            self._ensure_native_metadata(unit.first)
        else:
            raise ConfigurationError(
                "LightMem native provider only accepts TurnEvent or TurnPair ingest units"
            )
        self._get_or_create_backend(namespace)
        if batch is None:
            return IngestResult(unit_ref=UnitRef(namespace))
        pending = self._native_pending_batches.get(namespace)
        if pending is not None:
            self._write_native_batch(namespace, pending, is_final=False)
        self._native_pending_batches[namespace] = batch
        return IngestResult(unit_ref=UnitRef(namespace))

    def end_conversation(self, ref: UnitRef) -> None:
        """在 conversation 边界写出最后一批并执行 LoCoMo post-build update。"""

        pending = self._native_pending_batches.pop(ref.isolation_key, None)
        if pending is None:
            return
        backend = self._get_or_create_backend(ref.isolation_key)
        self._write_native_batch(ref.isolation_key, pending, is_final=True)
        if self._is_native_locomo(ref.isolation_key):
            self._run_locomo_offline_update(backend, ref.isolation_key)
        self._flush_buffered_memory_manager_usages(ref.isolation_key)

    def _write_native_batch(
        self,
        namespace: str,
        messages: list[dict[str, object]],
        *,
        is_final: bool,
    ) -> None:
        """向 LightMemory 写入一个已聚合 batch。"""

        backend = self._get_or_create_backend(namespace)
        kwargs: dict[str, Any] = {
            "force_segment": is_final,
            "force_extract": is_final,
        }
        if self._is_native_locomo(namespace):
            kwargs["METADATA_GENERATE_PROMPT"] = _load_lightmem_locomo_prompt(
                self.path_settings,
                "METADATA_GENERATE_PROMPT_locomo",
            )
        self._suppress_stdout_if_needed(backend.add_memory, messages, **kwargs)

    def _native_turn_batch(self, event: TurnEvent) -> list[dict[str, object]]:
        """把 v3 TurnEvent 转成 LightMem LoCoMo 单 turn batch。"""

        conversation = self._native_conversation_from_events((event,))
        batches = self._conversation_to_locomo_batches(conversation)
        if len(batches) != 1:
            raise ConfigurationError("LightMem native turn produced invalid batch count")
        return batches[0]

    def _native_pair_batch(self, pair: TurnPair) -> list[dict[str, object]] | None:
        """把 v3 TurnPair 转成 LightMem LongMemEval pair batch。

        orphan pair（session 开头无 user 锚点的 turn）经官方开头裁剪后没有
        可写消息，返回 None 表示跳过——与旧路径整段 session 裁剪行为等价。
        """

        conversation = self._native_conversation_from_events(pair.turns)
        batches = self._conversation_to_longmemeval_batches(conversation)
        if not batches:
            return None
        if len(batches) != 1:
            raise ConfigurationError("LightMem native pair produced invalid batch count")
        return batches[0]

    def _native_conversation_from_events(
        self,
        events: tuple[TurnEvent, ...],
    ) -> Conversation:
        """从 v3 events 恢复旧 helper 需要的最小公开 conversation。"""

        if not events:
            raise ConfigurationError("LightMem native unit has no events")
        first = events[0]
        session = Session(
            session_id=first.session_id or "",
            session_time=self._session_time_from_event(first),
            turns=[self._turn_from_event(event) for event in events],
        )
        return Conversation(
            conversation_id=self._conversation_id_from_event(first),
            sessions=[session],
            metadata=self._native_public_metadata(first),
        )

    def _ensure_native_metadata(self, event: TurnEvent) -> None:
        """登记 native namespace 的公开 conversation metadata。"""

        self._conversation_metadata[event.isolation_key] = self._native_public_metadata(
            event
        )

    def _is_native_locomo(self, namespace: str) -> bool:
        """判断 native namespace 是否应执行 LoCoMo 特化逻辑。"""

        metadata = self._conversation_metadata.get(namespace, {})
        source_path = str(metadata.get("source_path") or "").lower()
        return "locomo" in source_path

    @staticmethod
    def _turn_from_event(event: TurnEvent) -> Turn:
        """从规范 TurnEvent 恢复旧 adapter helper 需要的 Turn。"""

        return Turn(
            turn_id=event.turn_id,
            speaker=event.speaker_name or event.role,
            content=LightMem._original_content_from_event(event),
            normalized_role=event.role if event.role in {"user", "assistant"} else None,
            turn_time=LightMem._optional_event_text(event, "original_turn_time"),
            metadata=dict(event.metadata.get("turn_metadata") or {}),
        )

    @staticmethod
    def _native_public_metadata(event: TurnEvent) -> dict[str, Any]:
        """恢复 v3 事件中携带的 conversation 级公开 metadata。"""

        metadata = dict(event.metadata.get("conversation_metadata") or {})
        metadata["conversation_id"] = LightMem._conversation_id_from_event(event)
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

        return LightMem._optional_event_text(event, "original_session_time") or event.timestamp

    @staticmethod
    def _original_content_from_event(event: TurnEvent) -> str:
        """读取事件前原始 turn 文本，避免 caption 被提前拼入。"""

        original = event.metadata.get("original_content")
        if isinstance(original, str):
            return original
        return event.content

    @staticmethod
    def _optional_event_text(event: TurnEvent, field_name: str) -> str | None:
        """读取 TurnEvent metadata 中的可选文本字段。"""

        value = event.metadata.get(field_name)
        return value if isinstance(value, str) else None

    def retrieve(self, question: Question | RetrievalQuery) -> AnswerPromptResult | RetrievalResult:
        """检索 LightMem context，不生成最终 answer。"""

        if isinstance(question, RetrievalQuery):
            return self._retrieve_native(question)

        retrieval, _items = self._retrieve_question(question)
        return retrieval

    def _retrieve_question(
        self,
        question: Question,
    ) -> tuple[AnswerPromptResult, tuple[RetrievedItem, ...] | None]:
        """检索公开问题，并同时保留 v3 provenance items。"""

        if question.conversation_id not in self._backends:
            raise ConfigurationError(
                f"LightMem conversation has not been added: {question.conversation_id}"
            )
        backend = self._backends[question.conversation_id]
        collector = self._efficiency_collector
        retrieval_started_ns = perf_counter_ns()
        retrieval_profile = "lightmemory_retrieve"
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                memories = self._retrieve_with_payload(backend, question)
        else:
            memories = self._retrieve_with_payload(backend, question)
        memory_context = "\n".join(
            _format_lightmem_memory(memory) for memory in memories
        )
        prompt_messages = self._build_prompt_messages(question, memories)
        answer_prompt = "\n\n".join(
            f"[{message.role}]\n{message.content}" for message in prompt_messages
        )
        if collector is not None and collector.enabled:
            collector.record_retrieval_result(
                latency_ms=_elapsed_ms(retrieval_started_ns),
                injected_memory_context_tokens=_count_openai_tokens(
                    memory_context,
                    self.config.llm_model,
                ),
            )
        retrieval = AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt=answer_prompt,
            prompt_messages=prompt_messages,
            metadata={
                "method": "lightmem",
                "answer_context": memory_context,
                "retrieved_memories": [
                    self._metadata_memory_from_lightmem_item(memory)
                    for memory in memories
                ],
                "retrieve_limit": self.config.retrieve_limit,
                "retrieval_profile": retrieval_profile,
                "answer_prompt_profile": (
                    "longmemeval"
                    if _is_longmemeval_question(question, self._conversation_metadata)
                    else "locomo"
                ),
            },
        )
        return retrieval, self._retrieved_items_from_lightmem_memories(memories)

    def _retrieve_native(self, query: RetrievalQuery) -> RetrievalResult:
        """执行 v3 检索并返回不生成最终答案的 RetrievalResult。"""

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
        retrieval, items = self._retrieve_question(native_question)
        formatted_memory = (
            retrieval.metadata.get("answer_context")
            if isinstance(retrieval.metadata.get("answer_context"), str)
            else ""
        )
        metadata = dict(retrieval.metadata)
        metadata["provenance_granularity"] = "turn" if items is not None else "none"
        return RetrievalResult(
            formatted_memory=formatted_memory or "(No relevant memories found)",
            prompt_messages=tuple(retrieval.prompt_messages),
            items=items,
            metadata=metadata,
        )

    def get_answer(self, question: Question) -> AnswerResult:
        """基于 LightMem 检索上下文回答公开问题。"""

        retrieval = self.retrieve(question)
        prompt = _user_visible_prompt_text(retrieval.prompt_messages)
        answer_started_ns = perf_counter_ns()
        collector = self._efficiency_collector
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.ANSWER):
                answer = self._call_answer_client(prompt=prompt, question=question)
        else:
            answer = self._call_answer_client(prompt=prompt, question=question)
        if collector is not None and collector.enabled:
            collector.record_answer_generation(latency_ms=_elapsed_ms(answer_started_ns))
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=str(answer).strip(),
            metadata={
                "method": "lightmem",
                "retrieve_limit": self.config.retrieve_limit,
                "reader_prompt_version": LIGHTMEM_READER_PROMPT_VERSION,
            },
        )

    def _get_or_create_backend(self, conversation_id: str) -> Any:
        """返回当前 conversation 的隔离 LightMemory backend。"""

        if conversation_id not in self._backends:
            if self._backend_factory is None:
                backend = self._create_official_backend(
                    conversation_id
                )
            else:
                backend = self._backend_factory(conversation_id)
            self._install_memory_manager_usage_observer(
                backend=backend,
                conversation_id=conversation_id,
            )
            self._backends[conversation_id] = backend
        return self._backends[conversation_id]

    def _create_official_backend(self, conversation_id: str) -> Any:
        """构造当前 conversation 独占的官方 LightMemory backend，并注入 timeout/retry。"""

        if self._openai_settings is None:
            raise ConfigurationError(
                f"LightMem production backend requires OpenAI settings for {conversation_id}"
            )
        self.storage_root.mkdir(parents=True, exist_ok=True)
        classes = import_lightmem_classes(self.path_settings)
        lightmemory_cls = classes["LightMemory"]
        backend_config = self.build_backend_config(
            config=self.config,
            openai_settings=self._openai_settings,
            storage_root=self.storage_root,
            conversation_id=conversation_id,
            project_root=self.path_settings.project_root,
        )
        backend = self._suppress_stdout_if_needed(lightmemory_cls.from_config, backend_config)
        self._inject_api_retry_timeout(backend, conversation_id)
        return backend

    def _inject_api_retry_timeout(
        self,
        backend: Any,
        conversation_id: str,
    ) -> None:
        """对 vendored LightMem memory manager 的 OpenAI client 注入 timeout/retry。

        不修改 vendored 源码；只在 backend 构造完成后通过 with_options 注入网络兜底参数。
        """
        manager = getattr(backend, "manager", None)
        if manager is None or not hasattr(manager, "client"):
            return
        client = manager.client
        with_options = getattr(client, "with_options", None)
        if not callable(with_options):
            return
        timeout = self.config.api_timeout_seconds
        max_retries = self.config.api_max_retries
        manager.client = with_options(
            timeout=timeout,
            max_retries=max_retries,
        )

    def _install_memory_manager_usage_observer(
        self,
        backend: Any,
        conversation_id: str,
    ) -> None:
        """包装 LightMem memory manager 的 LLM 入口，记录 build 阶段 API usage。

        LightMem 官方 `OpenaiManager.generate_response()` 会返回
        `(parsed_response, usage_info)`。这里只读取 usage_info 并写入当前
        conversation scope，不改变返回值、prompt、并发或 LightMem 内部算法。
        """

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        manager = getattr(backend, "manager", None)
        if manager is None or not hasattr(manager, "generate_response"):
            return
        if getattr(manager, "_memory_benchmark_usage_wrapped", False):
            return
        original_generate_response = manager.generate_response

        def wrapped_generate_response(*args: Any, **kwargs: Any) -> Any:
            """调用官方 LightMem manager，并把 usage 归还给当前 conversation。"""

            response = original_generate_response(*args, **kwargs)
            usage = self._resolve_memory_manager_usage(
                response=response,
                args=args,
                kwargs=kwargs,
            )
            if collector.active_scope_type() == "conversation":
                self._record_memory_manager_usage(collector, usage)
            else:
                self._buffer_memory_manager_usage(conversation_id, usage)
            return response

        manager.generate_response = wrapped_generate_response
        manager._memory_benchmark_usage_wrapped = True

    def _resolve_memory_manager_usage(
        self,
        *,
        response: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> _BufferedMemoryManagerUsage:
        """从 LightMem manager 返回值中解析一次 LLM token usage。

        输入:
            response: 官方 `generate_response()` 原始返回值，常见为
                `(parsed_response, usage_info)`。
            args/kwargs: 原始调用参数，用于 API usage 缺失时回退 tokenizer 估算。

        输出:
            _BufferedMemoryManagerUsage: 可直接记录或跨线程暂存的 usage。
        """

        parsed_response = response[0] if isinstance(response, tuple) else response
        usage_info = (
            response[1]
            if isinstance(response, tuple) and len(response) > 1
            else None
        )
        api_input_tokens, api_output_tokens = extract_api_token_usage(usage_info)
        messages = kwargs.get("messages")
        if messages is None and args:
            messages = args[0]
        usage = resolve_token_usage(
            api_input_tokens=api_input_tokens,
            api_output_tokens=api_output_tokens,
            prompt_text=str(messages or ""),
            output_text=str(parsed_response or ""),
            tokenizer=_TiktokenCounter(self.config.llm_model),
        )
        return _BufferedMemoryManagerUsage(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_measurement_source=usage.source,
        )

    def _record_memory_manager_usage(
        self,
        collector: EfficiencyCollector,
        usage: _BufferedMemoryManagerUsage,
    ) -> None:
        """把 LightMem memory manager usage 记录到当前 collector scope。"""

        collector.record_llm_call(
            model_id=LIGHTMEM_MEMORY_LLM_MODEL_ID,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_measurement_source=usage.token_measurement_source,
        )

    def _buffer_memory_manager_usage(
        self,
        conversation_id: str,
        usage: _BufferedMemoryManagerUsage,
    ) -> None:
        """暂存子线程中无法直接写入 ContextVar scope 的 memory manager usage。"""

        with self._memory_manager_usage_lock:
            self._buffered_memory_manager_usages.setdefault(
                conversation_id,
                [],
            ).append(usage)

    def _flush_buffered_memory_manager_usages(self, conversation_id: str) -> None:
        """把子线程暂存 usage 刷回当前 conversation scope。

        LightMem LoCoMo OP-update 使用线程池，ContextVar 不会自动传播。Adapter 在
        `add()` 返回前仍处于 runner 的 conversation scope，因此这里把暂存 usage 统一
        写回，避免真实 OP-update 的 build LLM token 丢失。
        """

        with self._memory_manager_usage_lock:
            usages = self._buffered_memory_manager_usages.pop(conversation_id, [])
        if not usages:
            return
        collector = self._efficiency_collector
        if (
            collector is None
            or not collector.enabled
            or collector.active_scope_type() != "conversation"
        ):
            return
        for usage in usages:
            self._record_memory_manager_usage(collector, usage)

    def _run_locomo_offline_update(self, backend: Any, conversation_id: str) -> None:
        """执行 LightMem LoCoMo 官方构建脚本中的 post-build offline update。"""

        if not hasattr(backend, "construct_update_queue_all_entries"):
            raise ConfigurationError(
                "LightMem LoCoMo backend does not expose "
                f"construct_update_queue_all_entries: {conversation_id}"
            )
        if not hasattr(backend, "offline_update_all_entries"):
            raise ConfigurationError(
                "LightMem LoCoMo backend does not expose "
                f"offline_update_all_entries: {conversation_id}"
            )
        self._suppress_stdout_if_needed(backend.construct_update_queue_all_entries)
        self._suppress_stdout_if_needed(
            backend.offline_update_all_entries,
            score_threshold=self.config.offline_update_score_threshold,
        )

    def _retrieve_with_payload(
        self,
        backend: Any,
        question: Question,
    ) -> list[dict[str, Any]]:
        """通过官方检索组件 `embedding_retriever.search` 检索，返回带 payload 的结果。

        复用 `LightMemory.retrieve` 内部的检索路径（`text_embedder.embed` +
        `embedding_retriever.search`），但保留官方 retrieve 会丢弃的 payload，
        供 LoCoMo speaker 分组与统一 formatted_memory 使用。LongMemEval 与
        LoCoMo 两路径统一调用此方法，消除原 LoCoMo 自复刻的 get_all + 手算
        cosine（ws02.5 P1：统一走官方 retrieve 组件）。

        输入:
            backend: 当前 conversation 的官方 LightMemory 实例。
            question: 公开问题对象。

        输出:
            list[dict[str, Any]]: 带 payload、score 和 `_retrieved_speaker` 的条目。
        """

        text_embedder = getattr(backend, "text_embedder", None)
        embedding_retriever = getattr(backend, "embedding_retriever", None)
        if text_embedder is None or not hasattr(text_embedder, "embed"):
            raise ConfigurationError(
                f"LightMem backend has no text embedder: {question.conversation_id}"
            )
        if embedding_retriever is None or not hasattr(embedding_retriever, "search"):
            raise ConfigurationError(
                "LightMem backend has no official embedding retriever: "
                f"{question.conversation_id}"
            )
        query_vector = text_embedder.embed(question.text)
        results = embedding_retriever.search(
            query_vector=query_vector,
            limit=self.config.retrieve_limit,
            filters=None,
            return_full=True,
        )
        retrieved: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            payload = result.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            retrieved.append(
                {
                    "id": str(result.get("id", "")),
                    "score": float(result.get("score", 0.0)),
                    "payload": payload,
                    "source": "vector",
                    "_retrieved_speaker": (
                        str(payload.get("speaker_name"))
                        if payload.get("speaker_name") is not None
                        else "Unknown"
                    ),
                }
            )
        return retrieved

    @staticmethod
    def _metadata_memory_from_lightmem_item(memory: Any) -> dict[str, Any]:
        """把 LightMem retrieval item 转成 metadata 中的轻量诊断字典。"""

        score: float | None = None
        metadata: dict[str, Any] = {}
        if isinstance(memory, dict):
            raw_score = memory.get("score")
            if isinstance(raw_score, (int, float)):
                score = float(raw_score)
            for key in ("id", "source", "_retrieved_speaker"):
                value = memory.get(key)
                if value is not None:
                    metadata[key] = value
            payload = memory.get("payload")
            if isinstance(payload, dict):
                metadata["payload"] = payload
        return {
            "content": _format_lightmem_memory(memory),
            "score": score,
            "metadata": metadata,
        }

    @staticmethod
    def _retrieved_items_from_lightmem_memories(
        memories: list[Any],
    ) -> tuple[RetrievedItem, ...] | None:
        """把带 external id 的 payload 转成 turn-level provenance items。

        旧状态或未附 `external_id` 的调用路径没有无损来源信息；遇到任一此类
        命中时整次检索回落为无 provenance，而不是返回部分来源制造假 recall。
        """

        items: list[RetrievedItem] = []
        for memory in memories:
            if not isinstance(memory, dict):
                return None
            payload = memory.get("payload")
            if not isinstance(payload, dict):
                return None
            source_external_id = payload.get("source_external_id")
            if not isinstance(source_external_id, str) or not source_external_id.strip():
                return None
            item_id = str(memory.get("id") or "").strip()
            content = _format_lightmem_memory(memory)
            if not item_id or not content.strip():
                return None
            raw_score = memory.get("score")
            score = float(raw_score) if isinstance(raw_score, (int, float)) else None
            raw_timestamp = payload.get("time_stamp")
            timestamp = str(raw_timestamp) if raw_timestamp is not None else None
            items.append(
                RetrievedItem(
                    item_id=item_id,
                    content=content,
                    score=score,
                    timestamp=timestamp,
                    source_turn_ids=(source_external_id,),
                    metadata={"source": str(memory.get("source") or "vector")},
                )
            )
        return tuple(items)

    def _conversation_to_lightmem_batches(
        self,
        conversation: Conversation,
    ) -> list[list[dict[str, object]]]:
        """把统一 conversation 转换为官方 `add_memory()` 调用批次。

        LightMem 的 LoCoMo 脚本把每条原始发言包装为 `user(content)+assistant("")`；
        LongMemEval 脚本按真实 `user+assistant` pair 写入。这里根据公开
        source metadata 选择对应转换，避免把整个 conversation 一次性喂给
        LightMemory。
        """

        if _is_longmemeval_conversation(conversation):
            batches = self._conversation_to_longmemeval_batches(conversation)
        else:
            batches = self._conversation_to_locomo_batches(conversation)
        if not batches:
            raise ConfigurationError(
                f"LightMem conversation has no addable turn batches: "
                f"{conversation.conversation_id}"
            )
        return batches

    def _conversation_to_locomo_batches(
        self,
        conversation: Conversation,
    ) -> list[list[dict[str, object]]]:
        """按 LightMem 的 LoCoMo 脚本生成单 turn + 空 assistant 批次。"""

        batches: list[list[dict[str, object]]] = []
        for session in conversation.sessions:
            for turn in session.turns:
                timestamp = _turn_timestamp(turn, session)
                speaker_id = _locomo_speaker_id(conversation, turn)
                speaker_name = turn.speaker
                batches.append(
                    [
                        {
                            "role": "user",
                            "content": turn.content,
                            "speaker_id": speaker_id,
                            "speaker_name": speaker_name,
                            "time_stamp": timestamp,
                            "external_id": turn.turn_id,
                        },
                        {
                            "role": "assistant",
                            "content": "",
                            "speaker_id": speaker_id,
                            "speaker_name": speaker_name,
                            "time_stamp": timestamp,
                            "external_id": turn.turn_id,
                        },
                    ]
                )
        return batches

    def _conversation_to_longmemeval_batches(
        self,
        conversation: Conversation,
    ) -> list[list[dict[str, object]]]:
        """按 LongMemEval 官方脚本生成真实 user+assistant pair 批次。"""

        batches: list[list[dict[str, object]]] = []
        for session in conversation.sessions:
            messages = [
                self._turn_to_role_message(turn, session)
                for turn in session.turns
            ]
            while messages and messages[0]["role"] != "user":
                messages.pop(0)
            if len(messages) % 2 != 0:
                raise ConfigurationError(
                    f"LightMem LongMemEval session has odd message count after "
                    f"normalization: {conversation.conversation_id}/{session.session_id}"
                )
            for index in range(0, len(messages), 2):
                pair = messages[index : index + 2]
                if pair[0]["role"] != "user" or pair[1]["role"] != "assistant":
                    raise ConfigurationError(
                        "LightMem LongMemEval session must be user/assistant pairs: "
                        f"{conversation.conversation_id}/{session.session_id}"
                    )
                batches.append(pair)
        return batches

    def _turn_to_role_message(
        self,
        turn: Turn,
        session: Session,
    ) -> dict[str, object]:
        """把 LongMemEval turn 转成保留真实 role 的 LightMem message。"""

        role = turn.normalized_role or turn.metadata.get("role") or turn.speaker
        normalized_role = str(role).strip().lower()
        if normalized_role not in {"user", "assistant"}:
            raise ConfigurationError(
                f"LightMem LongMemEval turn role must be user or assistant: {turn.turn_id}"
            )
        timestamp = _turn_timestamp(turn, session)
        return {
            "role": normalized_role,
            "content": turn.content,
            "speaker_id": turn.speaker,
            "speaker_name": turn.speaker,
            "time_stamp": timestamp,
            "external_id": turn.turn_id,
        }

    def _locomo_metadata_prompt_if_needed(
        self,
        conversation: Conversation,
    ) -> str | None:
        """LoCoMo official profile 传入官方抽取 prompt，其他数据不传。"""

        if not _is_locomo_conversation(conversation):
            return None
        return _load_lightmem_locomo_prompt(
            self.path_settings,
            "METADATA_GENERATE_PROMPT_locomo",
        )

    def _build_answer_prompt(
        self,
        question: Question,
        memories: list[Any],
    ) -> str:
        """构造不含 gold answer 的 LightMem reader prompt。"""

        return _user_visible_prompt_text(self._build_prompt_messages(question, memories))

    def _build_prompt_messages(
        self,
        question: Question,
        memories: list[Any],
    ) -> list[PromptMessage]:
        """构造 LightMem 官方 answer LLM role messages。"""

        if _is_longmemeval_question(question, self._conversation_metadata):
            memory_context = "\n".join(
                _format_lightmem_memory_as_official_retrieve(memory)
                for memory in memories
            )
            return [
                PromptMessage(role="system", content="You are a helpful assistant."),
                PromptMessage(
                    role="user",
                    content=(
                        f"Question time:{question.question_time} and question:{question.text}\n"
                        "Please answer the question based on the following memories: "
                        f"{memory_context}"
                    ),
                ),
            ]
        return [
            PromptMessage(
                role="system",
                content=self._build_locomo_answer_prompt(question, memories),
            )
        ]

    def _build_locomo_answer_prompt(
        self,
        question: Question,
        memories: list[Any],
    ) -> str:
        """使用 LightMem LoCoMo `ANSWER_PROMPT` 的 speaker 分组布局。"""

        metadata = self._conversation_metadata.get(question.conversation_id, {})
        speaker_a = str(metadata.get("speaker_a") or "Speaker 1")
        speaker_b = str(metadata.get("speaker_b") or "Speaker 2")
        speaker_a_memories, speaker_b_memories = _split_memories_by_speaker(
            memories,
            speaker_a,
            speaker_b,
        )
        answer_prompt = _load_lightmem_locomo_prompt(
            self.path_settings,
            "ANSWER_PROMPT",
        )
        return answer_prompt.format(
            speaker_1_name=speaker_a,
            speaker_1_memories=speaker_a_memories,
            speaker_2_name=speaker_b,
            speaker_2_memories=speaker_b_memories,
            question=question.text,
        )

    def _call_answer_client(self, prompt: str, question: Question) -> str:
        """调用测试或生产 reader。"""

        if self._answer_client is None:
            raise ConfigurationError(
                f"LightMem answer client is not available for {question.conversation_id}"
            )
        response = self._suppress_stdout_if_needed(
            self._answer_client.create_answer,
            prompt,
        )
        response_text = str(response)
        self._record_answer_llm_call(prompt_text=prompt, output_text=response_text)
        return response_text

    def _record_answer_llm_call(self, *, prompt_text: str, output_text: str) -> None:
        """记录 LightMem 固定 reader 的 LLM token。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        api_input_tokens, api_output_tokens = extract_api_token_usage(
            getattr(self._answer_client, "last_usage", None)
        )
        usage = resolve_token_usage(
            api_input_tokens=api_input_tokens,
            api_output_tokens=api_output_tokens,
            prompt_text=prompt_text,
            output_text=output_text,
            tokenizer=_TiktokenCounter(self.config.llm_model),
        )
        collector.record_llm_call(
            model_id="lightmem-answer-llm",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_measurement_source=usage.source,
        )

    def _suppress_stdout_if_needed(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """按配置压制第三方 stdout。"""

        if not self.config.suppress_official_stdout:
            return func(*args, **kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            return func(*args, **kwargs)


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
                    "tiktoken is required for LightMem token estimation"
                ) from exc
            try:
                self._encoding = tiktoken.encoding_for_model(self.model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return len(self._encoding.encode(text or ""))


def _elapsed_ms(started_ns: int) -> float:
    """把 perf_counter_ns 起点转换为非负毫秒。"""

    return max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)


def _count_openai_tokens(text: str, model_name: str) -> int:
    """使用 OpenAI-compatible tokenizer 估算注入 LLM 的文本 token 数。"""

    if not text:
        return 0
    return _TiktokenCounter(model_name).count_tokens(text)


def _is_locomo_conversation(conversation: Conversation) -> bool:
    """根据公开 metadata 判断 conversation 是否来自 LoCoMo。"""

    source_path = str(conversation.metadata.get("source_path") or "").lower()
    return "locomo" in source_path


def _is_longmemeval_conversation(conversation: Conversation) -> bool:
    """根据公开 metadata/session metadata 判断 conversation 是否来自 LongMemEval。"""

    source_path = str(conversation.metadata.get("source_path") or "").lower()
    if "longmemeval" in source_path:
        return True
    return any(
        str(session.metadata.get("source_format") or "").startswith("longmemeval")
        for session in conversation.sessions
    )


def _is_longmemeval_question(
    question: Question,
    conversation_metadata: dict[str, dict[str, Any]],
) -> bool:
    """判断问题是否应使用 LongMemEval 官方 reader prompt。"""

    metadata = conversation_metadata.get(question.conversation_id, {})
    source_path = str(metadata.get("source_path") or "").lower()
    return "longmemeval" in source_path or question.question_time is not None


def _turn_timestamp(turn: Turn, session: Session) -> str:
    """读取 LightMem 必需的 `time_stamp` 字段，并转为官方格式。

    LightMem 的 MessageNormalizer 要求格式为 "2023/05/20 (Sat) 00:44" 或 ISO。
    LoCoMo 数据集的 session time 是 "1:56 pm on 8 May, 2023"，需要转换。
    月名-日-年格式（例如 "April-02-2024"）转为 ISO；其余 compatible 格式透传。
    转换只作用于发给 LightMem 的消息副本，原始 Turn/Session 时间字段保持不变，
    并继续由公开 conversation 与 TurnEvent 的 original_* metadata 审计链保存。
    """

    raw_timestamp = turn.turn_time or session.session_time
    if not raw_timestamp:
        raise ConfigurationError(
            f"LightMem requires turn_time or session_time for turn {turn.turn_id}"
        )
    converted = _locomo_time_to_lightmem(raw_timestamp)
    if converted is not None:
        return converted
    converted = _month_name_date_to_iso(raw_timestamp)
    if converted is not None:
        return converted
    return raw_timestamp


def _locomo_time_to_lightmem(raw_time: str) -> str | None:
    """尝试把 LoCoMo 数据集的时间格式转为 LightMem 认可的格式。

    LoCoMo 格式: "1:56 pm on 8 May, 2023"
    LightMem 期望: "2023/05/08 (Mon) 13:56"

    输入:
        raw_time: 原始 session/turn 时间字符串。

    输出:
        str | None: 转换后的时间字符串；如果格式不匹配则返回 None。
    """

    try:
        dt = datetime.strptime(raw_time, "%I:%M %p on %d %B, %Y")
    except (ValueError, TypeError):
        return None
    return dt.strftime("%Y/%m/%d (%a) %H:%M")


def _month_name_date_to_iso(raw_time: str) -> str | None:
    """把英文月名-日-年时间转为 LightMem 可解析的 ISO 时间。

    输入:
        raw_time: 形如 ``April-02-2024`` 的原始日期字符串。

    输出:
        str | None: 午夜时刻的 ISO 字符串；格式或日期无效时返回 None，由调用方
        保持原有透传行为。
    """

    if re.fullmatch(r"[A-Za-z]+-\d{1,2}-\d{4}", raw_time) is None:
        return None
    try:
        dt = datetime.strptime(raw_time, "%B-%d-%Y")
    except (ValueError, TypeError):
        return None
    return dt.isoformat()


def _locomo_speaker_id(conversation: Conversation, turn: Turn) -> str:
    """按 LightMem LoCoMo 脚本的 speaker_a/speaker_b 语义生成 speaker_id。"""

    speaker_a = conversation.metadata.get("speaker_a")
    speaker_b = conversation.metadata.get("speaker_b")
    if speaker_a and turn.speaker == speaker_a:
        return "speaker_a"
    if speaker_b and turn.speaker == speaker_b:
        return "speaker_b"
    return turn.speaker


def _load_lightmem_locomo_prompt(
    path_settings: PathSettings,
    prompt_name: str,
) -> str:
    """从 vendored LightMem LoCoMo prompt 文件读取指定 prompt 常量。"""

    prompt_path = (
        path_settings.resolve_third_party_method_path(LIGHTMEM_METHOD_DIRECTORY)
        / "experiments"
        / "locomo"
        / "prompts.py"
    )
    if not prompt_path.is_file():
        raise ConfigurationError(f"LightMem LoCoMo prompt file missing: {prompt_path}")
    module_name = f"_memory_benchmark_lightmem_prompts_{prompt_name}"
    spec = importlib.util.spec_from_file_location(module_name, prompt_path)
    if spec is None or spec.loader is None:
        raise ConfigurationError(f"LightMem prompt file cannot be loaded: {prompt_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompt = getattr(module, prompt_name, None)
    if not isinstance(prompt, str) or not prompt.strip():
        raise ConfigurationError(
            f"LightMem LoCoMo prompt '{prompt_name}' is missing or empty"
        )
    return prompt


def _split_memories_by_speaker(
    memories: list[Any],
    speaker_a: str,
    speaker_b: str,
) -> tuple[str, str]:
    """把检索 memory 粗分到 LoCoMo 官方 prompt 的两个 speaker 区域。

    LightMem 的 `search_locomo.py` 直接读取 Qdrant payload，可按 speaker_name 精确分组；
    `LightMemory.retrieve()` 返回格式化字符串时不保留 payload。对字符串 fallback，
    这里放入 speaker_a 区域，同时保留 speaker_b 的空上下文标题。
    """

    speaker_a_lines: list[str] = []
    speaker_b_lines: list[str] = []
    for memory in memories:
        speaker_name = _memory_speaker_name(memory)
        formatted = _format_lightmem_memory(memory)
        if speaker_name == speaker_b:
            speaker_b_lines.append(formatted)
        else:
            speaker_a_lines.append(formatted)
    return (
        "\n\n".join(speaker_a_lines) or "No memories available.",
        "\n\n".join(speaker_b_lines) or "No memories available.",
    )


def _memory_speaker_name(memory: Any) -> str | None:
    """从可能的 LightMem retrieval entry 中读取 speaker_name。"""

    if not isinstance(memory, dict):
        return None
    payload = memory.get("payload")
    if isinstance(payload, dict):
        speaker_name = payload.get("speaker_name")
        if speaker_name is not None:
            return str(speaker_name)
    speaker_name = memory.get("_retrieved_speaker") or memory.get("speaker_name")
    if speaker_name is None:
        return None
    return str(speaker_name)


def _format_lightmem_memory(memory: Any) -> str:
    """把 LightMem retrieval item 格式化为 reader prompt 可读文本。"""

    if not isinstance(memory, dict):
        return str(memory)
    payload = memory.get("payload")
    source = payload if isinstance(payload, dict) else memory
    time_stamp = source.get("time_stamp", "")
    weekday = source.get("weekday", "")
    memory_text = (
        source.get("memory")
        or source.get("original_memory")
        or source.get("compressed_memory")
        or memory.get("memory")
        or ""
    )
    if time_stamp:
        formatted_date = _format_lightmem_memory_date(str(time_stamp))
        if formatted_date:
            weekday_text = f", {weekday}" if weekday else ""
            return (
                f"[Memory recorded on: {formatted_date}{weekday_text}]\n"
                f"{memory_text}"
            ).strip()
    prefix = " ".join(str(value) for value in (time_stamp, weekday) if value)
    if prefix:
        return f"{prefix}\n{memory_text}".strip()
    return str(memory_text or memory)


def _format_lightmem_memory_date(time_stamp: str) -> str | None:
    """按 LightMem LoCoMo `format_related_memories()` 的日期格式化时间。"""

    try:
        parsed = datetime.fromisoformat(time_stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.strftime("%d %B %Y")


def _format_lightmem_memory_as_official_retrieve(memory: Any) -> str:
    """按官方 `LightMemory.retrieve` 的格式化口径（lightmem.py:693-701）输出单条记忆。

    官方 retrieve 返回 `"{time_stamp} {weekday} {memory}"` 的 list[str]，
    本函数从带 payload 的 retrieval dict 中还原同一格式，使 LongMemEval 路径
    在统一改用 `embedding_retriever.search`（返回 dict）后，answer prompt 的
    memory 呈现与官方 `run_lightmem_gpt.py:186` `'\n'.join(related_memories)`
    保持一致（ws02.5 P1：统一检索组件但不改 answer prompt 格式）。
    """

    if not isinstance(memory, dict):
        return str(memory)
    payload = memory.get("payload")
    source = payload if isinstance(payload, dict) else memory
    time_stamp = str(source.get("time_stamp", "") or "")
    weekday = str(source.get("weekday", "") or "")
    memory_text = (
        source.get("memory")
        or source.get("original_memory")
        or source.get("compressed_memory")
        or memory.get("memory")
        or ""
    )
    return f"{time_stamp} {weekday} {memory_text}".strip()


def _user_visible_prompt_text(messages: list[PromptMessage]) -> str:
    """把 LightMem role messages 转成 legacy reader 使用的 prompt 文本。"""

    if len(messages) == 1:
        return messages[0].content
    return "\n\n".join(
        f"[{message.role}]\n{message.content}" for message in messages
    )


class _OpenAIAnswerClient:
    """LightMem 固定 reader 的 OpenAI-compatible client wrapper。"""

    def __init__(self, client: Any, model: str) -> None:
        """保存 chat completion client 和 reader 模型名。"""

        self._client = client
        self._model = model
        self.last_usage: Any | None = None

    def create_answer(self, prompt: str) -> str:
        """调用 chat completion 并返回文本答案。"""

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
        self.last_usage = getattr(response, "usage", None)
        try:
            return str(response.choices[0].message.content or "").strip()
        except (AttributeError, IndexError, TypeError) as exc:
            raise ConfigurationError(
                "LightMem reader returned an unsupported response shape"
            ) from exc


def _storage_safe_collection_name(conversation_id: str) -> str:
    """把 conversation id 转成稳定且路径安全的 Qdrant collection 名。"""

    if not conversation_id.strip():
        raise ConfigurationError("LightMem conversation_id is required")
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", conversation_id.strip())
    digest = hashlib.sha1(conversation_id.encode("utf-8")).hexdigest()[:10]
    safe_id = normalized[:64].strip("._-") or "conversation"
    return f"lightmem_{safe_id}_{digest}"


def clean_lightmem_conversation_state(
    storage_root: str | Path,
    conversation_id: str,
) -> None:
    """删除 LightMem 单个 conversation 的 Qdrant collection 和日志目录。

    输入:
        storage_root: 当前 run 的 LightMem method state 根目录。
        conversation_id: 需要重新 ingest 的 conversation id。

    输出:
        None。目标目录不存在时视为已经干净。
    """

    root = Path(storage_root).expanduser().resolve()
    collection_name = _storage_safe_collection_name(conversation_id)
    targets = (
        root / "qdrant" / collection_name,
        root / "qdrant" / f"{collection_name}_summary",
        root / "logs" / collection_name,
    )
    for raw_target in targets:
        target = raw_target.resolve()
        if root == target or root not in target.parents:
            raise ConfigurationError(f"Unsafe LightMem state cleanup path: {target}")
        shutil.rmtree(target, ignore_errors=True)


def _resolve_local_model_reference(
    model_reference: str,
    project_root: str | Path,
) -> Path | None:
    """把显式本地模型引用解析为绝对路径。

    输入:
        model_reference: 配置中的模型引用。`models/...`、绝对路径和 `./...`
            会被视为本地路径；普通 HuggingFace model id 不在这里校验。
        project_root: 项目根目录，用于解析相对路径。

    输出:
        Path | None: 本地模型路径；如果配置看起来是远程模型 id，则返回 `None`。
    """

    raw_reference = model_reference.strip()
    raw_path = Path(raw_reference).expanduser()
    if raw_path.is_absolute():
        return raw_path.resolve(strict=False)
    if raw_reference.startswith(("models/", "./", "../")):
        return (Path(project_root).expanduser().resolve() / raw_path).resolve(
            strict=False
        )
    return None


def _model_reference_for_backend(
    model_reference: str,
    project_root: str | Path,
) -> str:
    """返回传给官方 backend 的模型引用。

    输入:
        model_reference: 配置中的模型引用。
        project_root: 项目根目录。

    输出:
        str: 本地模型会转换为绝对路径；非本地引用原样返回。
    """

    local_path = _resolve_local_model_reference(model_reference, project_root)
    if local_path is None:
        return model_reference
    return str(local_path)

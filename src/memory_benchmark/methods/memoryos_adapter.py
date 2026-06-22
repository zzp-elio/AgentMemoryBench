"""MemoryOS 的 conversation-QA v2 适配器。

本模块把 MemoryOS 官方 `eval/` 目录中的 LoCoMo 评测实现包装成当前项目的
`BaseMemorySystem`。适配器只允许加入不改变算法返回的纯 observer hook；所有 API key、
base URL、论文参数和 embedding 缓存都在本项目侧注入，避免直接运行官方脚本中的硬编码配置。
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import io
import json
import math
import openai as openai_package
import re
import sys
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from types import ModuleType
from typing import Any

import httpcore
import httpx
from openai import APIConnectionError, APITimeoutError, OpenAI

from memory_benchmark.config.settings import PathSettings, load_path_settings, load_settings
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    Conversation,
    Question,
    AnswerPromptResult,
    PromptMessage,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider, BaseMemorySystem
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
    resolve_token_usage,
)
from memory_benchmark.utils.logger import get_logger


LOGGER = get_logger(__name__)
MEMORYOS_METHOD_DIRECTORY = "MemoryOS-main"
MEMORYOS_ADAPTER_VERSION = "conversation-qa-v1"
MEMORYOS_WRAPPER_SOURCE_MODE = "official-eval-wrapper"
MEMORYOS_VENDORED_SOURCE_MODE = "vendored-official-eval"
MEMORYOS_COMBINED_SOURCE_MODE = "vendored-official-eval-with-framework-wrapper"
MEMORYOS_WRAPPER_LOGICAL_PATH = "src/memory_benchmark/methods/memoryos_adapter.py"
MEMORYOS_LONGMEMEVAL_READER_PROMPT_VERSION = "lightmem_longmemeval_reader_v1"
MEMORYOS_PYPI_GENERIC_READER_PROMPT_VERSION = "memoryos_pypi_generic_v1"
MEMORYOS_LONGMEMEVAL_READER_PROMPT_PROFILES = frozenset(
    {
        MEMORYOS_LONGMEMEVAL_READER_PROMPT_VERSION,
        MEMORYOS_PYPI_GENERIC_READER_PROMPT_VERSION,
    }
)
LONGMEMEVAL_QUESTION_TYPES = frozenset(
    {
        "single-session-user",
        "single-session-assistant",
        "single-session-preference",
        "temporal-reasoning",
        "knowledge-update",
        "multi-session",
    }
)
MEMORYOS_EVAL_MODULE_NAMES = [
    "utils",
    "short_term_memory",
    "mid_term_memory",
    "long_term_memory",
    "dynamic_update",
    "retrieval_and_answer",
    "main_loco_parse",
]

_MEMORYOS_EVAL_IMPORT_LOCK = threading.Lock()


@dataclass(frozen=True)
class MemoryOSPaperConfig:
    """MemoryOS 论文中 LoCoMo 实验设置的本项目表示。

    字段:
        llm_model: 论文主结果使用的回答模型。
        embedding_model_name: 开源 eval 默认 MiniLM；这里使用完整 HF 模型名。
        short_term_capacity: STM dialogue page queue length。
        mid_term_capacity: MTM 最大 segment 数量/长度的适配值。
        long_term_knowledge_capacity: User KB / Agent Traits 的论文容量。
        heat_threshold: MTM -> LPM 更新阈值。
        topic_similarity_threshold: 论文中的相似度阈值 theta。
        retrieval_top_m_segments: 检索 MTM segment 的 top-m。
        retrieval_queue_capacity: LoCoMo retrieved dialogue page top-k。
        segment_threshold: 开源 eval 检索时使用的 segment 过滤阈值。
        page_threshold: 开源 eval 检索时使用的 page 过滤阈值。
        knowledge_threshold: 开源 eval 检索时使用的 long-term knowledge 阈值。
        api_timeout_seconds: 单次 OpenAI-compatible API 请求超时时间。
        api_max_retries: 单次 MemoryOS LLM 调用失败后的最大重试次数。
        api_retry_wait_seconds: 第一次重试前等待秒数。
        api_retry_backoff_multiplier: 后续重试等待时间的指数放大倍数。
        api_retry_max_wait_seconds: 单次重试等待时间上限。
        suppress_official_stdout: 是否屏蔽 MemoryOS 官方脚本中的 print 输出。
        max_workers: conversation 级建议并发数，当前固定为 1。
        longmemeval_prompt_profile: LongMemEval reader prompt profile。默认使用
            LightMem-style QA prompt；可选 MemoryOS PyPI generic prompt。
        profile_name: 可审计的 profile 名称。
    """

    llm_model: str = "gpt-4o-mini"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    short_term_capacity: int = 7
    mid_term_capacity: int = 200
    long_term_knowledge_capacity: int = 100
    heat_threshold: float = 5.0
    topic_similarity_threshold: float = 0.6
    retrieval_top_m_segments: int = 5
    retrieval_queue_capacity: int = 10
    segment_threshold: float = 0.1
    page_threshold: float = 0.1
    knowledge_threshold: float = 0.1
    api_timeout_seconds: float = 120.0
    api_max_retries: int = 8
    api_retry_wait_seconds: float = 5.0
    api_retry_backoff_multiplier: float = 2.0
    api_retry_max_wait_seconds: float = 60.0
    suppress_official_stdout: bool = True
    max_workers: int = 1
    longmemeval_prompt_profile: str = MEMORYOS_LONGMEMEVAL_READER_PROMPT_VERSION
    profile_name: str = "custom"

    def __post_init__(self) -> None:
        """强校验会影响 MemoryOS 语义和运行安全的参数。"""

        _require_non_empty_string(self.llm_model, "llm_model")
        _require_non_empty_string(self.embedding_model_name, "embedding_model_name")
        _require_non_empty_string(self.profile_name, "profile_name")
        _require_non_empty_string(
            self.longmemeval_prompt_profile,
            "longmemeval_prompt_profile",
        )
        if (
            self.longmemeval_prompt_profile
            not in MEMORYOS_LONGMEMEVAL_READER_PROMPT_PROFILES
        ):
            allowed = ", ".join(sorted(MEMORYOS_LONGMEMEVAL_READER_PROMPT_PROFILES))
            raise ConfigurationError(
                "MemoryOS longmemeval_prompt_profile must be one of: "
                f"{allowed}"
            )

        for field_name in (
            "short_term_capacity",
            "mid_term_capacity",
            "long_term_knowledge_capacity",
            "retrieval_top_m_segments",
            "retrieval_queue_capacity",
            "max_workers",
        ):
            _require_positive_int(getattr(self, field_name), field_name)

        _require_non_negative_int(self.api_max_retries, "api_max_retries")
        if type(self.suppress_official_stdout) is not bool:
            raise ConfigurationError(
                "MemoryOS suppress_official_stdout must be a boolean"
            )

        heat_threshold = _require_finite_number(self.heat_threshold, "heat_threshold")
        if heat_threshold < 0:
            raise ConfigurationError("MemoryOS heat_threshold must be non-negative")

        for field_name in (
            "topic_similarity_threshold",
            "segment_threshold",
            "page_threshold",
            "knowledge_threshold",
        ):
            value = _require_finite_number(getattr(self, field_name), field_name)
            if value < 0 or value > 1:
                raise ConfigurationError(f"MemoryOS {field_name} must be within [0, 1]")

        api_timeout_seconds = _require_finite_number(
            self.api_timeout_seconds,
            "api_timeout_seconds",
        )
        if api_timeout_seconds <= 0:
            raise ConfigurationError("MemoryOS api_timeout_seconds must be positive")
        api_retry_wait_seconds = _require_finite_number(
            self.api_retry_wait_seconds,
            "api_retry_wait_seconds",
        )
        if api_retry_wait_seconds < 0:
            raise ConfigurationError("MemoryOS api_retry_wait_seconds must be non-negative")
        api_retry_backoff_multiplier = _require_finite_number(
            self.api_retry_backoff_multiplier,
            "api_retry_backoff_multiplier",
        )
        if api_retry_backoff_multiplier < 1:
            raise ConfigurationError(
                "MemoryOS api_retry_backoff_multiplier must be at least 1"
            )
        api_retry_max_wait_seconds = _require_finite_number(
            self.api_retry_max_wait_seconds,
            "api_retry_max_wait_seconds",
        )
        if api_retry_max_wait_seconds <= 0:
            raise ConfigurationError("MemoryOS api_retry_max_wait_seconds must be positive")

    def to_manifest(self) -> dict[str, Any]:
        """返回不含密钥和绝对路径的公开配置 manifest。"""

        return {
            **asdict(self),
            "adapter_version": MEMORYOS_ADAPTER_VERSION,
            "source_mode": MEMORYOS_WRAPPER_SOURCE_MODE,
        }


def build_memoryos_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 vendored 官方 eval 源码加本项目 wrapper 的确定性身份。

    输入:
        path_settings: 可选项目路径配置；为空时从当前项目根加载。

    输出:
        dict: 组合 SHA-256、vendored 官方文件列表以及稳定 wrapper 审计字段。

    说明:
        vendored 部分覆盖 `MemoryOS-main/eval/*.py`、根 `README.md`、`LICENSE` 和
        可选 PyPI prompt profile 使用的 `memoryos-pypi/prompts.py`；wrapper 部分只覆盖当前执行的
        `src/memory_benchmark/methods/memoryos_adapter.py`。输出不暴露绝对路径。
    """

    settings = path_settings or load_path_settings()
    memoryos_root = settings.resolve_third_party_method_path(MEMORYOS_METHOD_DIRECTORY)
    source_files = sorted(
        [
            path
            for path in (memoryos_root / "eval").glob("*.py")
            if path.is_file()
        ]
        + [
            path
            for path in (
                memoryos_root / "README.md",
                memoryos_root / "LICENSE",
                memoryos_root / "memoryos-pypi" / "prompts.py",
            )
            if path.is_file()
        ],
        key=lambda path: path.relative_to(memoryos_root).as_posix(),
    )
    if not source_files:
        raise ConfigurationError(f"MemoryOS source files missing: {memoryos_root}")

    vendored_source_sha256, relative_paths = _hash_relative_source_files(
        root=memoryos_root,
        source_files=source_files,
    )
    wrapper_source_path = Path(__file__).resolve()
    return _build_memoryos_source_identity_from_components(
        vendored_files=relative_paths,
        vendored_source_sha256=vendored_source_sha256,
        wrapper_logical_path=MEMORYOS_WRAPPER_LOGICAL_PATH,
        wrapper_bytes=wrapper_source_path.read_bytes(),
    )


def _hash_relative_source_files(
    *,
    root: Path,
    source_files: list[Path],
) -> tuple[str, list[str]]:
    """按相对路径和字节内容计算一组源码文件的稳定 SHA-256。"""

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative_path = source_file.relative_to(root).as_posix()
        relative_paths.append(relative_path)
        path_bytes = relative_path.encode("utf-8")
        content = source_file.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, byteorder="big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, byteorder="big"))
        digest.update(content)
    return digest.hexdigest(), relative_paths


def _build_memoryos_source_identity_from_components(
    *,
    vendored_files: list[str],
    vendored_source_sha256: str,
    wrapper_logical_path: str,
    wrapper_bytes: bytes,
) -> dict[str, Any]:
    """组合 vendored 官方源码和 wrapper 源码，生成可审计的公开身份。"""

    if Path(wrapper_logical_path).is_absolute():
        raise ConfigurationError(
            "MemoryOS wrapper_logical_path must be a stable logical path"
        )
    wrapper_sha256 = hashlib.sha256(wrapper_bytes).hexdigest()
    digest = hashlib.sha256()
    for field_name, field_value in (
        ("vendored_source_sha256", vendored_source_sha256),
        ("wrapper_path", wrapper_logical_path),
        ("wrapper_sha256", wrapper_sha256),
    ):
        field_name_bytes = field_name.encode("utf-8")
        field_value_bytes = field_value.encode("utf-8")
        digest.update(len(field_name_bytes).to_bytes(8, byteorder="big"))
        digest.update(field_name_bytes)
        digest.update(len(field_value_bytes).to_bytes(8, byteorder="big"))
        digest.update(field_value_bytes)

    return {
        "source_sha256": digest.hexdigest(),
        "vendored_source_sha256": vendored_source_sha256,
        "file_count": len(vendored_files),
        "files": list(vendored_files),
        "wrapper_path": wrapper_logical_path,
        "wrapper_sha256": wrapper_sha256,
        "source_mode": MEMORYOS_COMBINED_SOURCE_MODE,
        "vendored_source_mode": MEMORYOS_VENDORED_SOURCE_MODE,
    }


def _require_non_empty_string(value: object, field_name: str) -> str:
    """校验字段是非空字符串，避免构造阶段抛出裸类型异常。"""

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"MemoryOS {field_name} must be a non-empty string")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    """校验字段是严格正整数，不接受 bool。"""

    if type(value) is not int or value <= 0:
        raise ConfigurationError(f"MemoryOS {field_name} must be a positive integer")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    """校验字段是严格非负整数，不接受 bool。"""

    if type(value) is not int or value < 0:
        raise ConfigurationError(f"MemoryOS {field_name} must be a non-negative integer")
    return value


def _require_finite_number(value: object, field_name: str) -> float:
    """校验字段是有限数值，允许 int/float 但不接受 bool。"""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigurationError(f"MemoryOS {field_name} must be a finite number")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ConfigurationError(f"MemoryOS {field_name} must be a finite number")
    return numeric_value


def _validate_existing_state_files(state_dir: Path) -> None:
    """校验 resume 所需的现有状态文件结构。

    输入:
        state_dir: 单个 conversation 的 MemoryOS 状态目录。

    异常:
        ConfigurationError: 必需文件缺失、JSON 损坏或顶层 schema 不符合当前 wrapper
            允许恢复的最小语义。
    """

    short_term_path = state_dir / "short_term.json"
    if not short_term_path.is_file():
        raise ConfigurationError(
            f"MemoryOS existing state missing short_term.json: {short_term_path}"
        )
    short_payload = _load_existing_state_json(
        short_term_path,
        "short_term.json",
    )
    if not isinstance(short_payload, list):
        raise ConfigurationError(
            f"MemoryOS short_term.json must contain a top-level list: {short_term_path}"
        )

    mid_term_path = state_dir / "mid_term.json"
    if mid_term_path.is_file():
        mid_payload = _load_existing_state_json(mid_term_path, "mid_term.json")
        if not isinstance(mid_payload, dict):
            raise ConfigurationError(
                f"MemoryOS mid_term.json must contain a top-level dict: {mid_term_path}"
            )
        if not isinstance(mid_payload.get("sessions"), dict):
            raise ConfigurationError(
                f"MemoryOS mid_term.json must contain a 'sessions' dict: {mid_term_path}"
            )
        if not isinstance(mid_payload.get("access_frequency"), dict):
            raise ConfigurationError(
                f"MemoryOS mid_term.json must contain an 'access_frequency' dict: {mid_term_path}"
            )

    long_term_path = state_dir / "long_term.json"
    if long_term_path.is_file():
        long_payload = _load_existing_state_json(long_term_path, "long_term.json")
        if not isinstance(long_payload, dict):
            raise ConfigurationError(
                f"MemoryOS long_term.json must contain a top-level dict: {long_term_path}"
            )
        if not isinstance(long_payload.get("user_profiles"), dict):
            raise ConfigurationError(
                f"MemoryOS long_term.json must contain a 'user_profiles' dict: {long_term_path}"
            )
        if not isinstance(long_payload.get("knowledge_base"), list):
            raise ConfigurationError(
                f"MemoryOS long_term.json must contain a 'knowledge_base' list: {long_term_path}"
            )
        if not isinstance(long_payload.get("assistant_knowledge"), list):
            raise ConfigurationError(
                f"MemoryOS long_term.json must contain an 'assistant_knowledge' list: {long_term_path}"
            )


def _load_existing_state_json(path: Path, semantic_name: str) -> Any:
    """读取并包装现有状态 JSON，给出带语义的错误信息。"""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(
            f"MemoryOS {semantic_name} cannot be read as valid JSON: {path}"
        ) from exc


@dataclass
class MemoryOSConversationState:
    """单个 conversation_id 对应的一套 MemoryOS 状态。

    字段:
        conversation_id: 当前记忆命名空间。
        speaker_a: LoCoMo speaker_a，MemoryOS eval 中作为 user。
        speaker_b: LoCoMo speaker_b，MemoryOS eval 中作为 assistant。
        short_memory: MemoryOS eval 的 ShortTermMemory 实例。
        mid_memory: MemoryOS eval 的 MidTermMemory 实例。
        long_memory: MemoryOS eval 的 LongTermMemory 实例。
        dynamic_updater: MemoryOS eval 的 DynamicUpdate 实例。
        retrieval_system: MemoryOS eval 的 RetrievalAndAnswer 实例。
        storage_dir: 当前 conversation 的状态文件目录。
    """

    conversation_id: str
    speaker_a: str
    speaker_b: str
    short_memory: Any
    mid_memory: Any
    long_memory: Any
    dynamic_updater: Any
    retrieval_system: Any
    storage_dir: Path


@dataclass(frozen=True)
class MemoryOSAddEstimate:
    """MemoryOS add 阶段的成本估算。

    字段:
        page_count: conversation 会转换出的 MemoryOS page 数量。
        short_term_capacity: 当前配置的 STM 容量。
        update_batch_count: 预计触发 short-term -> mid-term 更新的批次数。
        remaining_short_term_pages: add 结束后仍留在 STM 中的 page 数。
        will_trigger_updates: 是否会触发至少一次 MemoryOS 更新。
    """

    page_count: int
    short_term_capacity: int
    update_batch_count: int
    remaining_short_term_pages: int
    will_trigger_updates: bool


@dataclass
class _MemoryOSEvalModules:
    """MemoryOS eval 目录脚本模块集合。

    这些模块以脚本形式互相 `import utils`，因此只能按官方 eval 目录路径加载。
    """

    utils: ModuleType
    short_term_memory: ModuleType
    mid_term_memory: ModuleType
    long_term_memory: ModuleType
    dynamic_update: ModuleType
    retrieval_and_answer: ModuleType
    main_loco_parse: ModuleType


class MemoryOS(BaseMemoryProvider, BaseMemorySystem):
    """MemoryOS 的 conversation-QA v2 method wrapper。"""

    def __init__(
        self,
        openai_api_key: str | None = None,
        openai_base_url: str | None = None,
        storage_root: str | Path | None = None,
        config: MemoryOSPaperConfig | None = None,
        efficiency_collector: EfficiencyCollector | None = None,
    ):
        """初始化 MemoryOS wrapper。

        输入:
            openai_api_key: OpenAI-compatible API key；为空时从项目配置层读取。
            openai_base_url: API base URL；为空时从项目配置层读取。
            storage_root: MemoryOS 状态文件根目录；为空时写入
                `outputs/memoryos/<run-id>`，避免不同 run 复用 JSON 状态。
            config: MemoryOS 论文参数配置；为空时使用 `MemoryOSPaperConfig()`。
            efficiency_collector: runner 管理的可选效率 observation collector。

        输出:
            None。实例内部会缓存每个 conversation_id 对应的 MemoryOS 状态。
        """

        self.config = config or MemoryOSPaperConfig()
        self._efficiency_collector = efficiency_collector
        self._memory_context_text_var: ContextVar[str | None] = ContextVar(
            f"memoryos_memory_context_text_{id(self)}",
            default=None,
        )
        settings = None
        if openai_api_key is None or openai_base_url is None:
            try:
                settings = load_settings()
            except ConfigurationError:
                if openai_api_key is None:
                    raise
                settings = None

        if openai_api_key is None:
            if settings is None:
                raise ConfigurationError("MemoryOS requires an OpenAI API key")
            openai_api_key = settings.openai.api_key
        if openai_base_url is None and settings is not None:
            openai_base_url = settings.openai.base_url

        path_settings = settings.paths if settings is not None else load_path_settings()
        if storage_root is None:
            selected_storage_root = path_settings.outputs_root / "memoryos" / _new_memoryos_run_id()
        else:
            selected_storage_root = Path(storage_root)
        self.storage_root = selected_storage_root.resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)

        self.openai_api_key = openai_api_key
        self.openai_base_url = openai_base_url
        self._modules = self._load_eval_modules(path_settings)
        self._client = self._modules.utils.OpenAIClient(
            api_key=openai_api_key,
            base_url=openai_base_url,
        )
        self._embedding_cache: dict[str, Any] = {}
        self._embedding_model: Any | None = None
        self._patch_eval_modules()
        self._states: dict[str, MemoryOSConversationState] = {}

    def add(self, conversations: Conversation | list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。

        输入:
            conversations: runner 传入的单个公开 Conversation 或迁移期兼容列表；即使对象上有
                gold_answers，本方法也只读取 sessions、turns 和公开 metadata。

        输出:
            AddResult: 本次成功写入的 conversation ids。
        """

        if isinstance(conversations, Conversation):
            conversations = [conversations]
        if not conversations:
            raise ConfigurationError("MemoryOS.add() requires at least one conversation")

        conversation_ids: list[str] = []
        for conversation in conversations:
            if conversation.conversation_id in self._states:
                raise ConfigurationError(
                    f"MemoryOS conversation already added: {conversation.conversation_id}"
                )
            state = self._create_state(conversation)
            pages = self.conversation_to_memory_pages(conversation)
            with self._official_stdout_context():
                for page in pages:
                    state.short_memory.add_qa_pair(dict(page))
                    if state.short_memory.is_full():
                        state.dynamic_updater.bulk_evict_and_update_mid_term()
                    self._update_user_profile_if_needed(state)
            self._states[conversation.conversation_id] = state
            conversation_ids.append(conversation.conversation_id)

        return AddResult(
            conversation_ids=conversation_ids,
            metadata={
                "method": "MemoryOS",
                "config": self._safe_config_metadata(),
            },
        )

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """执行 MemoryOS 官方 retrieval 并格式化上下文。"""

        state = self._states.get(question.conversation_id)
        if state is None:
            raise ConfigurationError(
                f"MemoryOS has no conversation state for question: {question.conversation_id}"
            )

        collector = self._efficiency_collector
        effective_text = _effective_question_text(question)
        retrieval_started_ns = time.perf_counter_ns()
        with self._official_stdout_context():
            if collector is not None and collector.enabled:
                with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                    retrieval_result = state.retrieval_system.retrieve(
                        effective_text,
                        segment_threshold=self.config.segment_threshold,
                        page_threshold=self.config.page_threshold,
                        knowledge_threshold=self.config.knowledge_threshold,
                        client=self._client,
                    )
            else:
                retrieval_result = state.retrieval_system.retrieve(
                    effective_text,
                    segment_threshold=self.config.segment_threshold,
                    page_threshold=self.config.page_threshold,
                    knowledge_threshold=self.config.knowledge_threshold,
                    client=self._client,
                )
        prompt_messages, answer_prompt, memory_context = _build_memoryos_answer_prompt(
            question=question,
            query=effective_text,
            state=state,
            retrieval_result=retrieval_result,
            longmemeval_prompt_profile=self.config.longmemeval_prompt_profile,
        )
        if collector is not None and collector.enabled:
            collector.record_retrieval_result(
                latency_ms=_elapsed_ms(retrieval_started_ns),
                injected_memory_context_tokens=_count_openai_tokens(
                    memory_context,
                    self.config.llm_model,
                ),
            )

        retrieval_queue = retrieval_result.get("retrieval_queue") or []
        long_term_knowledge = retrieval_result.get("long_term_knowledge") or []
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt=answer_prompt,
            prompt_messages=prompt_messages,
            metadata={
                "method": "MemoryOS",
                "answer_context": memory_context,
                "retrieved_page_count": len(retrieval_queue),
                "retrieved_knowledge_count": len(long_term_knowledge),
                "answer_prompt_profile": _answer_prompt_profile_for_question(
                    question,
                    self.config.longmemeval_prompt_profile,
                ),
            },
        )

    def get_answer(self, question: Question) -> AnswerResult:
        """基于已写入的 conversation 回答公开问题。

        输入:
            question: method 可见问题，不包含 gold answer 或 evidence。

        输出:
            AnswerResult: MemoryOS 生成的答案和可审计 metadata。
        """

        state = self._states.get(question.conversation_id)
        if state is None:
            raise ConfigurationError(
                f"MemoryOS has no conversation state for question: {question.conversation_id}"
            )

        collector = self._efficiency_collector
        effective_text = _effective_question_text(question)
        retrieval_started_ns = time.perf_counter_ns()
        with self._official_stdout_context():
            if collector is not None and collector.enabled:
                with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                    retrieval_result = state.retrieval_system.retrieve(
                        effective_text,
                        segment_threshold=self.config.segment_threshold,
                        page_threshold=self.config.page_threshold,
                        knowledge_threshold=self.config.knowledge_threshold,
                        client=self._client,
                    )
            else:
                retrieval_result = state.retrieval_system.retrieve(
                    effective_text,
                    segment_threshold=self.config.segment_threshold,
                    page_threshold=self.config.page_threshold,
                    knowledge_threshold=self.config.knowledge_threshold,
                    client=self._client,
                )
        retrieval_latency_ms = _elapsed_ms(retrieval_started_ns)

        answer_started_ns = time.perf_counter_ns()
        memory_context_token = self._memory_context_text_var.set(None)
        try:
            with self._official_stdout_context():
                if collector is not None and collector.enabled:
                    with collector.operation_stage(EfficiencyStage.ANSWER):
                        answer, system_prompt, user_prompt = (
                            self._modules.main_loco_parse.generate_system_response_with_meta(
                                effective_text,
                                state.short_memory,
                                state.long_memory,
                                retrieval_result["retrieval_queue"],
                                retrieval_result["long_term_knowledge"],
                                self._client,
                                state.conversation_id,
                                state.speaker_a,
                                state.speaker_b,
                                {
                                    "conversation_id": state.conversation_id,
                                    "question_id": question.question_id,
                                },
                            )
                        )
                else:
                    answer, system_prompt, user_prompt = (
                        self._modules.main_loco_parse.generate_system_response_with_meta(
                            effective_text,
                            state.short_memory,
                            state.long_memory,
                            retrieval_result["retrieval_queue"],
                            retrieval_result["long_term_knowledge"],
                            self._client,
                            state.conversation_id,
                            state.speaker_a,
                            state.speaker_b,
                            {
                                "conversation_id": state.conversation_id,
                                "question_id": question.question_id,
                            },
                        )
                    )
            observed_memory_context_text = self._memory_context_text_var.get()
        finally:
            self._memory_context_text_var.reset(memory_context_token)
        if collector is not None and collector.enabled:
            memory_context_text = (
                observed_memory_context_text
                if observed_memory_context_text is not None
                else _memoryos_retrieved_context_text(retrieval_result)
            )
            collector.record_retrieval_result(
                latency_ms=retrieval_latency_ms,
                injected_memory_context_tokens=_count_openai_tokens(
                    memory_context_text,
                    self.config.llm_model,
                ),
            )
            collector.record_answer_generation(
                latency_ms=_elapsed_ms(answer_started_ns),
            )

        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=answer,
            metadata={
                "method": "MemoryOS",
                "retrieved_page_count": len(retrieval_result["retrieval_queue"]),
                "retrieved_knowledge_count": len(retrieval_result["long_term_knowledge"]),
                "system_prompt": system_prompt,
            },
        )

    @staticmethod
    def conversation_to_memory_pages(conversation: Conversation) -> list[dict[str, str]]:
        """把统一 Conversation 转成 MemoryOS eval 的 QA page 列表。

        输入:
            conversation: 已校验的 conversation-QA v2 Conversation。

        输出:
            list[dict[str, str]]: 每条包含 `user_input`、`agent_response` 和
            `timestamp`，对应 MemoryOS 官方 eval 的 page 格式。
        """

        speaker_a, speaker_b = _resolve_speakers(conversation)
        pages: list[dict[str, str]] = []

        for session in conversation.sessions:
            timestamp = session.session_time or session.start_time or session.end_time or ""
            for turn in session.turns:
                content = _turn_text_with_image_captions(turn)
                if turn.speaker == speaker_a:
                    pages.append(
                        {
                            "user_input": content,
                            "agent_response": "",
                            "timestamp": timestamp,
                        }
                    )
                elif turn.speaker == speaker_b:
                    if pages and pages[-1]["agent_response"] == "":
                        pages[-1]["agent_response"] = content
                    else:
                        pages.append(
                            {
                                "user_input": "",
                                "agent_response": content,
                                "timestamp": timestamp,
                            }
                        )
                else:
                    raise ConfigurationError(
                        f"{conversation.conversation_id}: unknown speaker for MemoryOS: {turn.speaker}"
                    )

        return pages

    def get_debug_state(self, conversation_id: str) -> MemoryOSConversationState:
        """返回某个 conversation 的 MemoryOS 内部状态。

        输入:
            conversation_id: 已写入的 conversation id。

        输出:
            MemoryOSConversationState: 测试和 debug 可读取的状态对象。
        """

        state = self._states.get(conversation_id)
        if state is None:
            raise ConfigurationError(f"MemoryOS state not found: {conversation_id}")
        return state

    def load_existing_conversation_state(self, conversation: Conversation) -> None:
        """挂载已写入磁盘的 conversation 状态，不重复 add 历史对话。

        输入:
            conversation: 需要恢复的 conversation。方法会根据 `conversation_id`
                定位 `storage_root/<conversation_id>/` 下的 MemoryOS JSON 状态。

        输出:
            None。恢复后可直接调用 `get_answer()`。
        """

        if conversation.conversation_id in self._states:
            return

        state_dir = self.storage_root / _safe_path_name(conversation.conversation_id)
        _validate_existing_state_files(state_dir)
        self._states[conversation.conversation_id] = self._create_state(conversation)

    def get_debug_modules(self) -> _MemoryOSEvalModules:
        """返回当前实例持有的 MemoryOS eval 模块集合。

        输入:
            无。

        输出:
            _MemoryOSEvalModules: 仅供单元测试和 debug 检查导入隔离状态。
        """

        return self._modules

    @staticmethod
    def estimate_add_workload(
        conversation: Conversation,
        config: MemoryOSPaperConfig | None = None,
    ) -> MemoryOSAddEstimate:
        """估算 add 阶段的 MemoryOS 更新成本。

        输入:
            conversation: 待写入的统一 Conversation。
            config: MemoryOS 配置；为空时使用论文默认配置。

        输出:
            MemoryOSAddEstimate: page 数、预计更新批次数和剩余 STM page 数。
        """

        selected_config = config or MemoryOSPaperConfig()
        if selected_config.short_term_capacity <= 0:
            raise ConfigurationError("MemoryOS short_term_capacity must be positive")

        page_count = len(MemoryOS.conversation_to_memory_pages(conversation))
        if page_count < selected_config.short_term_capacity:
            update_batch_count = 0
            remaining_short_term_pages = page_count
        else:
            update_batch_count = page_count - selected_config.short_term_capacity + 1
            remaining_short_term_pages = selected_config.short_term_capacity - 1
        return MemoryOSAddEstimate(
            page_count=page_count,
            short_term_capacity=selected_config.short_term_capacity,
            update_batch_count=update_batch_count,
            remaining_short_term_pages=remaining_short_term_pages,
            will_trigger_updates=update_batch_count > 0,
        )

    def _create_state(self, conversation: Conversation) -> MemoryOSConversationState:
        """为一个 conversation 创建独立 MemoryOS 状态。"""

        speaker_a, speaker_b = _resolve_speakers(conversation)
        state_dir = self.storage_root / _safe_path_name(conversation.conversation_id)
        state_dir.mkdir(parents=True, exist_ok=True)

        with self._official_stdout_context():
            short_memory = self._modules.short_term_memory.ShortTermMemory(
                max_capacity=self.config.short_term_capacity,
                file_path=str(state_dir / "short_term.json"),
            )
            mid_memory = self._modules.mid_term_memory.MidTermMemory(
                max_capacity=self.config.mid_term_capacity,
                file_path=str(state_dir / "mid_term.json"),
            )
            mid_memory.search_sessions_by_summary = partial(
                mid_memory.search_sessions_by_summary,
                top_k=self.config.retrieval_top_m_segments,
            )
            long_memory = self._modules.long_term_memory.LongTermMemory(
                file_path=str(state_dir / "long_term.json"),
            )
            dynamic_updater = self._modules.dynamic_update.DynamicUpdate(
                short_memory,
                mid_memory,
                long_memory,
                topic_similarity_threshold=self.config.topic_similarity_threshold,
                client=self._client,
            )
            retrieval_system = self._modules.retrieval_and_answer.RetrievalAndAnswer(
                short_memory,
                mid_memory,
                long_memory,
                dynamic_updater,
                queue_capacity=self.config.retrieval_queue_capacity,
            )

        return MemoryOSConversationState(
            conversation_id=conversation.conversation_id,
            speaker_a=speaker_a,
            speaker_b=speaker_b,
            short_memory=short_memory,
            mid_memory=mid_memory,
            long_memory=long_memory,
            dynamic_updater=dynamic_updater,
            retrieval_system=retrieval_system,
            storage_dir=state_dir,
        )

    def _load_eval_modules(self, path_settings: PathSettings) -> _MemoryOSEvalModules:
        """加载 MemoryOS 官方 eval 目录中的脚本模块。"""

        eval_dir = path_settings.resolve_third_party_method_path("MemoryOS-main", "eval")
        if not eval_dir.is_dir():
            raise ConfigurationError(f"MemoryOS eval directory missing: {eval_dir}")

        return self._import_eval_modules_with_safe_openai(eval_dir)

    def _import_eval_modules_with_safe_openai(self, eval_dir: Path) -> _MemoryOSEvalModules:
        """在官方空 API key 硬编码存在时安全导入 eval 模块。

        MemoryOS `eval/utils.py` 在 import 阶段会执行 `OpenAI(api_key="")`。
        新版 OpenAI SDK 会立即报错。这里临时把空 key 替换成占位 key，仅用于
        完成模块导入；导入后 `_patch_eval_modules()` 会注入真实 client。
        本函数会在导入前后恢复同名 `sys.modules` 和 `sys.path`，避免不同
        MemoryOS 实例共享被 monkeypatch 的官方 eval 模块。
        整个导入过程受 `_MEMORYOS_EVAL_IMPORT_LOCK` 保护，避免并行 worker 的
        sys.modules/sys.path 竞态。
        """

        with _MEMORYOS_EVAL_IMPORT_LOCK:
            real_openai_class = openai_package.OpenAI
            eval_dir_text = str(eval_dir)
            saved_modules = {
                module_name: sys.modules.get(module_name)
                for module_name in MEMORYOS_EVAL_MODULE_NAMES
            }
            inserted_path = False

            def safe_openai_constructor(*args: Any, **kwargs: Any) -> OpenAI:
                """为空 API key 补占位值，保证官方 eval 模块能完成导入。"""

                if not kwargs.get("api_key"):
                    kwargs["api_key"] = "memoryos-import-placeholder"
                return real_openai_class(*args, **kwargs)

            openai_package.OpenAI = safe_openai_constructor
            try:
                for module_name in MEMORYOS_EVAL_MODULE_NAMES:
                    sys.modules.pop(module_name, None)
                if eval_dir_text not in sys.path:
                    sys.path.insert(0, eval_dir_text)
                    inserted_path = True
                return _MemoryOSEvalModules(
                    utils=importlib.import_module("utils"),
                    short_term_memory=importlib.import_module("short_term_memory"),
                    mid_term_memory=importlib.import_module("mid_term_memory"),
                    long_term_memory=importlib.import_module("long_term_memory"),
                    dynamic_update=importlib.import_module("dynamic_update"),
                    retrieval_and_answer=importlib.import_module("retrieval_and_answer"),
                    main_loco_parse=importlib.import_module("main_loco_parse"),
                )
            finally:
                openai_package.OpenAI = real_openai_class
                for module_name in MEMORYOS_EVAL_MODULE_NAMES:
                    sys.modules.pop(module_name, None)
                for module_name, module in saved_modules.items():
                    if module is not None:
                        sys.modules[module_name] = module
                if inserted_path and eval_dir_text in sys.path:
                    sys.path.remove(eval_dir_text)

    def _patch_eval_modules(self) -> None:
        """注入 API 配置、论文热度公式和 embedding 缓存。"""

        client_kwargs: dict[str, Any] = {
            "api_key": self.openai_api_key,
            "timeout": self.config.api_timeout_seconds,
            "max_retries": 0,
        }
        if self.openai_base_url:
            client_kwargs["base_url"] = self.openai_base_url
        self._modules.utils.gpt_client = OpenAI(**client_kwargs)
        self._client.chat_completion = self._chat_completion_with_retry
        self._modules.mid_term_memory.client = self._client
        self._modules.main_loco_parse.H_THRESHOLD = self.config.heat_threshold
        self._modules.main_loco_parse.memory_context_observer = (
            self._observe_memory_context
        )

        def compute_segment_heat(session: dict[str, Any], alpha: float = 1.0, beta: float = 1.0, gamma: float = 1.0) -> float:
            """按论文 Eq.4 alpha/beta/gamma 默认值计算 segment heat。"""

            return (
                alpha * session.get("N_visit", 0)
                + beta * session.get("L_interaction", 0)
                + gamma * session.get("R_recency", 1.0)
            )

        self._modules.mid_term_memory.compute_segment_heat = compute_segment_heat
        self._modules.utils.get_embedding = self._get_embedding
        self._modules.mid_term_memory.get_embedding = self._get_embedding
        self._modules.long_term_memory.get_embedding = self._get_embedding

    def _observe_memory_context(self, payload: Any) -> None:
        """接收官方生成函数暴露的最终 prompt memory context。

        输入:
            payload: 官方函数在发送 LLM 前提供的上下文字段。缺字段时按空文本处理。

        输出:
            None。该方法只写入当前 ContextVar，不改变 MemoryOS 返回值或状态。
        """

        if not isinstance(payload, dict):
            return
        self._memory_context_text_var.set(
            _memoryos_memory_context_payload_text(payload)
        )

    def _chat_completion_with_retry(
        self,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """替换 MemoryOS 官方 chat_completion，增加超时和连接错误重试。

        输入:
            model: 本次官方 eval 请求指定的模型名。
            messages: OpenAI chat messages。
            temperature: 生成温度。
            max_tokens: 最大输出 token 数。

        输出:
            str: OpenAI-compatible chat completion 的第一条 message content。
        """

        total_attempts = self.config.api_max_retries + 1
        for attempt in range(1, total_attempts + 1):
            try:
                response = self._modules.utils.gpt_client.chat.completions.create(
                    model=model or self.config.llm_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content
                self._record_llm_call(
                    model=model or self.config.llm_model,
                    messages=messages,
                    response=response,
                    content=content or "",
                )
                if attempt > 1:
                    LOGGER.info(
                        "MemoryOS API call recovered after %s attempts",
                        attempt,
                    )
                return content or ""
            except _RETRYABLE_API_ERRORS as error:
                if attempt >= total_attempts:
                    LOGGER.error(
                        "MemoryOS API call failed after %s attempts: %s",
                        total_attempts,
                        type(error).__name__,
                    )
                    raise
                wait_seconds = self._retry_wait_seconds(attempt)
                LOGGER.warning(
                    "MemoryOS API call failed on attempt %s/%s with %s; retrying in %.1fs",
                    attempt,
                    total_attempts,
                    type(error).__name__,
                    wait_seconds,
                )
                if wait_seconds > 0:
                    time.sleep(wait_seconds)

        raise RuntimeError("MemoryOS retry loop exited unexpectedly")

    def _record_llm_call(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response: Any,
        content: str,
    ) -> None:
        """记录 MemoryOS eval 通过统一 chat_completion 发出的 LLM 调用。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        prompt_tokens, completion_tokens = _extract_usage_tokens(response)
        usage = resolve_token_usage(
            api_input_tokens=prompt_tokens,
            api_output_tokens=completion_tokens,
            prompt_text=_messages_to_text(messages),
            output_text=content,
            tokenizer=_TiktokenCounter(model or self.config.llm_model),
        )
        collector.record_llm_call(
            model_id="memoryos-chat-llm",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            token_measurement_source=usage.source,
        )

    def _retry_wait_seconds(self, failed_attempt_index: int) -> float:
        """计算下一次 MemoryOS API 重试前的等待时间。

        输入:
            failed_attempt_index: 第几次失败，从 1 开始。

        输出:
            float: 本次重试前应等待的秒数。
        """

        wait_seconds = self.config.api_retry_wait_seconds * (
            self.config.api_retry_backoff_multiplier ** (failed_attempt_index - 1)
        )
        return min(wait_seconds, self.config.api_retry_max_wait_seconds)

    def _get_embedding(self, text: str, model_name: str | None = None) -> Any:
        """使用缓存的 MiniLM 模型生成 embedding。"""

        selected_model = self.config.embedding_model_name
        cache_key = f"{selected_model}::{text}"
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer

            LOGGER.info("Loading MemoryOS embedding model: %s", selected_model)
            self._embedding_model = SentenceTransformer(selected_model)

        started_ns = time.perf_counter_ns()
        embedding = self._embedding_model.encode([text], convert_to_numpy=True)[0]
        self._record_embedding_call(
            text=text,
            latency_ms=_elapsed_ms(started_ns),
        )
        self._embedding_cache[cache_key] = embedding
        return embedding

    def _record_embedding_call(self, *, text: str, latency_ms: float) -> None:
        """记录 MemoryOS 本地 embedding 模型的 cache miss 调用。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        collector.record_embedding_call(
            model_id="memoryos-embedding",
            input_tokens=_count_sentence_transformer_tokens(
                self._embedding_model,
                text,
            ),
            latency_ms=latency_ms,
            token_measurement_source=MeasurementSource.METHOD_NATIVE,
            latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
        )

    def _update_user_profile_if_needed(self, state: MemoryOSConversationState) -> None:
        """按 MemoryOS eval 的热度规则触发 user profile / knowledge 更新。"""

        self._modules.main_loco_parse.update_user_profile_from_top_segment(
            state.mid_memory,
            state.long_memory,
            state.conversation_id,
            self._client,
        )
        _trim_long_term_capacity(state.long_memory, self.config.long_term_knowledge_capacity)

    @contextlib.contextmanager
    def _official_stdout_context(self):
        """必要时屏蔽 MemoryOS 官方脚本中的 print 输出。"""

        if not self.config.suppress_official_stdout:
            yield
            return

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            yield

    def _safe_config_metadata(self) -> dict[str, Any]:
        """返回可写入日志的配置摘要，不包含 API key。"""

        return self.config.to_manifest()


def _resolve_speakers(conversation: Conversation) -> tuple[str, str]:
    """解析 MemoryOS eval 所需的 speaker_a / speaker_b。"""

    speaker_a = _metadata_text(conversation.metadata.get("speaker_a"))
    speaker_b = _metadata_text(conversation.metadata.get("speaker_b"))
    if speaker_a and speaker_b:
        return speaker_a, speaker_b

    ordered_speakers: list[str] = []
    for session in conversation.sessions:
        for turn in session.turns:
            if turn.speaker not in ordered_speakers:
                ordered_speakers.append(turn.speaker)
            if len(ordered_speakers) == 2:
                return ordered_speakers[0], ordered_speakers[1]

    raise ConfigurationError(
        f"{conversation.conversation_id}: MemoryOS requires two speakers or speaker_a/speaker_b metadata"
    )


def _turn_text_with_image_captions(turn: Any) -> str:
    """拼接 turn 文本和可选图片 caption。"""

    content = turn.content or ""
    captions = [image.caption for image in turn.images if image.caption]
    if captions:
        caption_text = "; ".join(captions)
        return f"{content} (image description: {caption_text})"
    return content


def _metadata_text(value: Any) -> str | None:
    """把 metadata 字段转成非空文本。"""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_path_name(value: str) -> str:
    """把 conversation_id 转成安全目录名。"""

    return "".join(character if character.isalnum() or character in "-_." else "_" for character in value)


def _new_memoryos_run_id() -> str:
    """生成 MemoryOS 默认状态目录使用的唯一 run id。

    输入:
        无。

    输出:
        str: 以 `run-` 开头的短 UUID，避免不同实例复用同一 JSON 状态。
    """

    return f"run-{uuid.uuid4().hex[:12]}"


_RETRYABLE_API_ERRORS = (
    APITimeoutError,
    APIConnectionError,
    httpx.TimeoutException,
    httpx.ConnectError,
    httpcore.TimeoutException,
    httpcore.ConnectError,
    TimeoutError,
    ConnectionError,
)


def _trim_long_term_capacity(long_memory: Any, capacity: int) -> None:
    """限制长期知识容量，贴近论文中的 User KB / Agent Traits 容量。"""

    if capacity <= 0:
        return
    if len(long_memory.knowledge_base) > capacity:
        long_memory.knowledge_base = long_memory.knowledge_base[-capacity:]
    if len(long_memory.assistant_knowledge) > capacity:
        long_memory.assistant_knowledge = long_memory.assistant_knowledge[-capacity:]


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
                    "tiktoken is required for MemoryOS token estimation"
                ) from exc
            try:
                self._encoding = tiktoken.encoding_for_model(self.model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return len(self._encoding.encode(text or ""))


def _effective_question_text(question: Question) -> str:
    """构造含可选时间上下文的有效问题文本。

    LoCoMo 不含 question_time，返回原始文本。LongMemEval 的 question_time
    会作为时间前缀拼接，供检索和回答 prompt 使用。
    """

    if question.question_time:
        return f"Question time: {question.question_time}. Question: {question.text}"
    return str(question.text)


def _normalize_category(category: object) -> str | None:
    """把 question category 归一为非空字符串。"""

    if category is None:
        return None
    category_text = str(category).strip()
    return category_text or None


def _is_longmemeval_question(question: Question) -> bool:
    """判断问题是否应使用 LongMemEval reader prompt。"""

    if question.question_time:
        return True
    category = _normalize_category(question.category)
    return category in LONGMEMEVAL_QUESTION_TYPES


def _answer_prompt_profile_for_question(
    question: Question,
    longmemeval_prompt_profile: str = MEMORYOS_LONGMEMEVAL_READER_PROMPT_VERSION,
) -> str:
    """返回当前 question 对应的 answer prompt profile 名称。"""

    if _is_longmemeval_question(question):
        return longmemeval_prompt_profile
    return "memoryos_official_eval"


def _elapsed_ms(started_ns: int) -> float:
    """把 perf_counter_ns 起点转换为非负毫秒。"""

    return max(0.0, (time.perf_counter_ns() - started_ns) / 1_000_000)


def _count_openai_tokens(text: str, model_name: str) -> int:
    """使用 OpenAI-compatible tokenizer 估算注入 LLM 的文本 token 数。"""

    if not text:
        return 0
    return _TiktokenCounter(model_name).count_tokens(text)


def _count_sentence_transformer_tokens(model: Any, text: str) -> int:
    """使用 SentenceTransformer 自带 tokenizer 计算本地 embedding 输入 token。"""

    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None:
        raise ConfigurationError(
            "MemoryOS embedding token counting requires a SentenceTransformer tokenizer"
        )
    encoded = tokenizer(text or "", add_special_tokens=True)
    input_ids = _get_value(encoded, "input_ids")
    if isinstance(input_ids, list):
        if input_ids and isinstance(input_ids[0], list):
            return len(input_ids[0])
        return len(input_ids)
    raise ConfigurationError("MemoryOS embedding tokenizer did not return input_ids")


def _memoryos_retrieved_context_text(retrieval_result: dict[str, Any]) -> str:
    """抽取 MemoryOS 最终回答阶段可见的检索记忆上下文文本。"""

    parts: list[str] = []
    for page in retrieval_result.get("retrieval_queue", []):
        if isinstance(page, dict):
            user_input = str(page.get("user_input") or "").strip()
            agent_response = str(page.get("agent_response") or "").strip()
            if user_input:
                parts.append(user_input)
            if agent_response:
                parts.append(agent_response)
        elif page is not None:
            parts.append(str(page))
    for knowledge in retrieval_result.get("long_term_knowledge", []):
        if isinstance(knowledge, str):
            text = knowledge.strip()
        else:
            text = json.dumps(knowledge, ensure_ascii=False, sort_keys=True)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _build_memoryos_answer_prompt(
    *,
    question: Question,
    query: str,
    state: MemoryOSConversationState,
    retrieval_result: dict[str, Any],
    longmemeval_prompt_profile: str = MEMORYOS_LONGMEMEVAL_READER_PROMPT_VERSION,
) -> tuple[list[PromptMessage], str, str]:
    """按 MemoryOS 官方 eval prompt 逻辑构造完整 answer role messages。"""

    speaker_a = state.speaker_a
    speaker_b = state.speaker_b
    history = state.short_memory.get_all()
    history_text = "\n".join(
        [
            f"{speaker_a}: {qa.get('user_input', '')}\n"
            f"{speaker_b}: {qa.get('agent_response', '')}\n"
            f"Time: ({qa.get('timestamp', '')})"
            for qa in history
        ]
    )

    retrieval_queue = retrieval_result.get("retrieval_queue") or []
    retrieval_text = "\n".join(
        [
            f"【Historical Memory】 {speaker_a}: {page.get('user_input', '')}\n"
            f"{speaker_b}: {page.get('agent_response', '')}\n"
            f"Time:({page.get('timestamp', '')})\n"
            f"Conversation chain overview:({page.get('meta_info', '')})\n"
            for page in retrieval_queue
            if isinstance(page, dict)
        ]
    )

    profile_obj = state.long_memory.get_user_profile(state.conversation_id)
    user_profile_text = str(profile_obj.get("data", "None")) if profile_obj else "None"
    background = f"【User Profile】\n{user_profile_text}\n\n"
    for knowledge in retrieval_result.get("long_term_knowledge") or []:
        if isinstance(knowledge, dict):
            background += f"{knowledge.get('knowledge', '')}\n"
        else:
            background += f"{knowledge}\n"
    background = re.sub(r"(?i)\buser\b", speaker_a, background)
    background = re.sub(r"(?i)\bassistant\b", speaker_b, background)

    assistant_knowledge = state.long_memory.get_assistant_knowledge()
    assistant_knowledge_text = "【Assistant Knowledge】\n"
    for knowledge in assistant_knowledge:
        assistant_knowledge_text += (
            f"- {knowledge.get('knowledge', '')} ({knowledge.get('timestamp', '')})\n"
        )
    assistant_knowledge_text = re.sub(r"\bI\b", speaker_b, assistant_knowledge_text)

    system_prompt = (
        f"You are role-playing as {speaker_b} in a conversation with the user is playing is  {speaker_a}. "
        f"Here are some of your character traits and knowledge:\n{assistant_knowledge_text}\n"
        f"Any content referring to 'User' in the prompt refers to {speaker_a}'s content, and any content referring to 'AI'or 'assiant' refers to {speaker_b}'s content."
        f"Your task is to answer questions about {speaker_a} or {speaker_b} in an extremely concise manner.\n"
        f"When the question is: \"What did the charity race raise awareness for?\", you should not answer in the form of: \"The charity race raised awareness for mental health.\" Instead, it should be: \"mental health\", as this is more concise."
    )
    user_prompt = (
        f"<CONTEXT>\n"
        f"Recent conversation between {speaker_a} and {speaker_b}:\n"
        f"{history_text}\n\n"
        f"<MEMORY>\n"
        f"Relevant past conversations:\n"
        f"{retrieval_text}\n\n"
        f"<CHARACTER TRAITS>\n"
        f"Characteristics of {speaker_a}:\n"
        f"{background}\n\n"
        f"the question is: {query}\n"
        f"Your task is to answer questions about {speaker_a} or {speaker_b} in an extremely concise manner.\n"
        f"Please only provide the content of the answer, without including 'answer:'\n"
        f"For questions that require answering a date or time, strictly follow the format \"15 July 2023\" and provide a specific date whenever possible. For example, if you need to answer \"last year,\" give the specific year of last year rather than just saying \"last year.\" Only provide one year, date, or time, without any extra responses.\n"
        f"If the question is about the duration, answer in the form of several years, months, or days.\n"
        f"Generate answers primarily composed of concrete entities, such as Mentoring program, school speech, etc"
    )
    answer_context = "\n\n".join(
        text
        for text in (
            history_text,
            retrieval_text,
            background,
            assistant_knowledge_text,
        )
        if text.strip()
    )
    if _is_longmemeval_question(question):
        if not question.question_time:
            raise ConfigurationError(
                "MemoryOS LongMemEval reader prompt requires question_time: "
                f"{question.question_id}"
            )
        if longmemeval_prompt_profile == MEMORYOS_PYPI_GENERIC_READER_PROMPT_VERSION:
            query_with_time = (
                f"Question time:{question.question_time} and question:{question.text}"
            )
            meta_data_text = "\n".join(
                item
                for item in (
                    f"Question time: {question.question_time}",
                    f"Question type: {question.category}" if question.category else "",
                )
                if item
            )
            system_prompt = (
                "As a communication expert with outstanding communication habits, "
                f"you embody the role of {speaker_b} throughout the following dialogues.\n"
                "Here are some of your distinctive personal traits and knowledge:\n"
                f"{assistant_knowledge_text}\n"
                "User's profile:\n"
                f"{meta_data_text or 'None'}\n"
                "Your task is to generate responses that align with these traits "
                "and maintain the tone.\n"
            )
            user_prompt = (
                "<CONTEXT>\n"
                "Drawing from your recent conversation with the user:\n"
                f"{history_text}\n\n"
                "<MEMORY>\n"
                "The memories linked to the ongoing conversation are:\n"
                f"{retrieval_text or '(No relevant historical memories found)'}\n\n"
                "<USER TRAITS>\n"
                "During the conversation process between you and the user in the "
                "past, you found that the user has the following characteristics:\n"
                f"{background}\n\n"
                f"Now, please role-play as {speaker_b} to continue the dialogue "
                "between you and the user.\n"
                f"The user just said: {query_with_time}\n"
                "Please respond to the user's statement using the following format "
                "(maximum 30 words, must be in English):\n "
                "When answering questions, be sure to check whether the timestamp "
                "of the referenced information matches the timeframe of the question"
            )
            prompt_messages = [
                PromptMessage(role="system", content=system_prompt),
                PromptMessage(role="user", content=user_prompt),
            ]
            answer_prompt = "\n\n".join(
                f"[{message.role}]\n{message.content}" for message in prompt_messages
            )
            memory_context = "\n\n".join(
                text
                for text in (
                    history_text,
                    retrieval_text,
                    background,
                    assistant_knowledge_text,
                )
                if text.strip()
            )
            return prompt_messages, answer_prompt, memory_context

        memory_sections = [
            "<CONTEXT>\n"
            f"Recent conversation between {speaker_a} and {speaker_b}:\n"
            f"{history_text}",
            "<MEMORY>\n"
            "Relevant past conversations:\n"
            f"{retrieval_text or '(No relevant historical memories found)'}",
            "<CHARACTER TRAITS>\n"
            f"Characteristics of {speaker_a}:\n"
            f"{background}",
            "<ASSISTANT KNOWLEDGE>\n"
            f"{assistant_knowledge_text}",
        ]
        longmemeval_memory_context = "\n\n".join(
            section for section in memory_sections if section.strip()
        )
        user_prompt = (
            f"Question time:{question.question_time} and question:{question.text}\n"
            "Please answer the question based on the following memories: "
            f"{longmemeval_memory_context}"
        )
        prompt_messages = [
            PromptMessage(role="system", content="You are a helpful assistant."),
            PromptMessage(role="user", content=user_prompt),
        ]
        answer_prompt = "\n\n".join(
            f"[{message.role}]\n{message.content}" for message in prompt_messages
        )
        return prompt_messages, answer_prompt, longmemeval_memory_context

    prompt_messages = [
        PromptMessage(role="system", content=system_prompt),
        PromptMessage(role="user", content=user_prompt),
    ]
    answer_prompt = "\n\n".join(
        f"[{message.role}]\n{message.content}" for message in prompt_messages
    )
    return prompt_messages, answer_prompt, answer_context


def _memoryos_memory_context_payload_text(payload: dict[str, Any]) -> str:
    """把官方 observer payload 转成最终 prompt memory context 计数文本。

    输入:
        payload: `main_loco_parse.generate_system_response_with_meta()` 在发送 LLM
            前暴露的 memory context 字段。

    输出:
        str: 只包含记忆上下文，不包含最终 question 或通用指令。
    """

    parts: list[str] = []
    for field_name in (
        "history_text",
        "retrieval_text",
        "user_profile_and_knowledge",
        "assistant_knowledge",
    ):
        value = payload.get(field_name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts)


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


def _messages_to_text(messages: list[dict[str, Any]]) -> str:
    """把 OpenAI message list 拼成稳定纯文本，用于 tokenizer fallback。"""

    parts: list[str] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if role is not None:
            parts.append(str(role))
        if content is not None:
            parts.append(str(content))
    return "\n".join(parts)


__all__ = [
    "MemoryOS",
    "MemoryOSAddEstimate",
    "MemoryOSConversationState",
    "MemoryOSPaperConfig",
    "build_memoryos_source_identity",
]

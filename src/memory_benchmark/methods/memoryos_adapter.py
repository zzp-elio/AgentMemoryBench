"""MemoryOS 的 conversation-QA 适配器（memoryos-pypi 通用产品引擎）。

本模块把 MemoryOS 官方 ``memoryos-pypi`` 包（``pip install memoryos`` 得到的通用
产品引擎）包装成当前项目的 ``MemoryProvider`` / ``BaseMemorySystem``。adapter 负责
配置、per-conversation 物理隔离、统一接口与效率观测；不重写 MemoryOS 的核心记忆
算法。

迁移背景（ws02.5）：原 adapter 包装 ``eval/`` 目录的 LoCoMo 专用评测副本，存在
"主场优势"问题。现改用通用产品 ``memoryos-pypi``，使 MemoryOS 跨全部 benchmark
使用同一套注入/检索接口，保证公平与可比。

关键设计：
- 注入 = ``add_memory(user_input, agent_response, timestamp)``（pair 粒度），
  consume_granularity="pair"。orphan/dangling turn 按空侧留空串注入不丢。
- 检索 = 从 ``get_response`` 剥离纯检索步骤 1-7，组装短/中/长/各 knowledge 层成
  formatted_memory，跳过步骤 8-9 答题与步骤 10 的 add_memory 写副作用。
- 参数 = pypi 官方默认（short_term_capacity=10 等），不再用 LoCoMo 调参。
- 答题 = 框架 unified answer prompt（retrieve-first 主线），不用 MemoryOS 的
  get_response 答题。
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import math
import re
import shutil
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from openai import APIConnectionError, APITimeoutError, OpenAI

from memory_benchmark.config.settings import (
    OpenAISettings,
    PathSettings,
    load_path_settings,
    load_settings,
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
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider, BaseMemorySystem
from memory_benchmark.core.provider_protocol import (
    ConsumeGranularity,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    SessionBatch,
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
from memory_benchmark.utils.logger import get_logger


LOGGER = get_logger(__name__)

MEMORYOS_METHOD_DIRECTORY = "MemoryOS-main"
MEMORYOS_PYPI_SUBDIRECTORY = "memoryos-pypi"
MEMORYOS_ADAPTER_VERSION = "conversation-qa-v1"
MEMORYOS_WRAPPER_SOURCE_MODE = "memoryos-pypi-wrapper"
MEMORYOS_VENDORED_SOURCE_MODE = "vendored-memoryos-pypi"
MEMORYOS_COMBINED_SOURCE_MODE = "vendored-memoryos-pypi-with-framework-wrapper"
MEMORYOS_WRAPPER_LOGICAL_PATH = "src/memory_benchmark/methods/memoryos_adapter.py"
MEMORYOS_READER_PROMPT_VERSION = "memoryos-pypi-retrieve-v1"
MEMORYOS_MEMORY_LLM_MODEL_ID = "memoryos-chat-llm"
MEMORYOS_EMBEDDING_MODEL_ID = "memoryos-embedding"
MEMORYOS_DEFAULT_ASSISTANT_ID = "default_assistant_profile"

# pypi 官方默认参数（memoryos.py:30-44），与旧 eval/ LoCoMo 调参不同。
_MEMORYOS_PYPI_DEFAULT_SHORT_TERM_CAPACITY = 10
_MEMORYOS_PYPI_DEFAULT_MID_TERM_CAPACITY = 2000
_MEMORYOS_PYPI_DEFAULT_LONG_TERM_KNOWLEDGE_CAPACITY = 100
_MEMORYOS_PYPI_DEFAULT_RETRIEVAL_QUEUE_CAPACITY = 7
_MEMORYOS_PYPI_DEFAULT_HEAT_THRESHOLD = 5.0
_MEMORYOS_PYPI_DEFAULT_SIMILARITY_THRESHOLD = 0.6

_MEMORYOS_PYPI_IMPORT_LOCK = threading.Lock()
_MEMORYOS_PYPI_PACKAGE_NAME = "memoryos_pypi_vendor"
_MEMORYOS_PYPI_CACHE: dict[str, Any] = {}


@dataclass(frozen=True)
class MemoryOSPaperConfig:
    """MemoryOS 通用产品（memoryos-pypi）运行 profile。

    字段:
        llm_model: MemoryOS add_memory 触发的 profile/knowledge 抽取与 mid-term
            summarize 使用的 LLM；框架答题另用 unified reader。
        embedding_model_name: 本地 SentenceTransformer embedding 模型名。
        short_term_capacity: STM dialogue page 队列容量（pypi 默认 10）。
        mid_term_capacity: MTM 最大 segment 数（pypi 默认 2000）。
        long_term_knowledge_capacity: User KB / Agent Knowledge 容量（pypi 默认 100）。
        retrieval_queue_capacity: 检索中期 page top-k（pypi 默认 7）。
        mid_term_heat_threshold: MTM segment heat 触发 profile/knowledge 更新的阈值。
        mid_term_similarity_threshold: STM→MTM 合并 session 的相似度阈值。
        segment_similarity_threshold: 检索 session 级相似度阈值。
        page_similarity_threshold: 检索 page 级相似度阈值。
        knowledge_threshold: 检索长期知识相似度阈值。
        top_k_sessions: 检索中期 session top-k。
        top_k_knowledge: 检索长期知识 top-k。
        api_timeout_seconds: OpenAI-compatible 请求超时秒数。
        api_max_retries: 失败后最大重试次数。
        api_retry_wait_seconds: 首次重试等待秒数。
        api_retry_backoff_multiplier: 后续重试等待指数放大倍数。
        api_retry_max_wait_seconds: 单次重试等待上限。
        suppress_official_stdout: 是否压制第三方 stdout。
        max_workers: conversation 级建议并发数。
        longmemeval_prompt_profile: 遗留字段，保留向后兼容；迁移后 retrieve 统一
            用 memoryos-pypi-retrieve-v1，不再按此字段分支。
        profile_name: 可审计 profile 名称。
    """

    llm_model: str = "gpt-4o-mini"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    short_term_capacity: int = _MEMORYOS_PYPI_DEFAULT_SHORT_TERM_CAPACITY
    mid_term_capacity: int = _MEMORYOS_PYPI_DEFAULT_MID_TERM_CAPACITY
    long_term_knowledge_capacity: int = _MEMORYOS_PYPI_DEFAULT_LONG_TERM_KNOWLEDGE_CAPACITY
    retrieval_queue_capacity: int = _MEMORYOS_PYPI_DEFAULT_RETRIEVAL_QUEUE_CAPACITY
    mid_term_heat_threshold: float = _MEMORYOS_PYPI_DEFAULT_HEAT_THRESHOLD
    mid_term_similarity_threshold: float = _MEMORYOS_PYPI_DEFAULT_SIMILARITY_THRESHOLD
    segment_similarity_threshold: float = 0.1
    page_similarity_threshold: float = 0.1
    knowledge_threshold: float = 0.01
    top_k_sessions: int = 5
    top_k_knowledge: int = 20
    api_timeout_seconds: float = 120.0
    api_max_retries: int = 8
    api_retry_wait_seconds: float = 5.0
    api_retry_backoff_multiplier: float = 2.0
    api_retry_max_wait_seconds: float = 60.0
    suppress_official_stdout: bool = True
    max_workers: int = 1
    longmemeval_prompt_profile: str = MEMORYOS_READER_PROMPT_VERSION
    profile_name: str = "custom"

    def __post_init__(self) -> None:
        """强校验会影响 MemoryOS 语义和运行安全的参数。"""

        _require_non_empty_string(self.llm_model, "llm_model")
        _require_non_empty_string(self.embedding_model_name, "embedding_model_name")
        _require_non_empty_string(self.profile_name, "profile_name")
        _require_non_empty_string(self.longmemeval_prompt_profile, "longmemeval_prompt_profile")

        for field_name in (
            "short_term_capacity",
            "mid_term_capacity",
            "long_term_knowledge_capacity",
            "retrieval_queue_capacity",
            "top_k_sessions",
            "top_k_knowledge",
            "max_workers",
        ):
            _require_positive_int(getattr(self, field_name), field_name)

        _require_non_negative_int(self.api_max_retries, "api_max_retries")
        if type(self.suppress_official_stdout) is not bool:
            raise ConfigurationError("MemoryOS suppress_official_stdout must be a boolean")

        heat = _require_finite_number(self.mid_term_heat_threshold, "mid_term_heat_threshold")
        if heat < 0:
            raise ConfigurationError("MemoryOS mid_term_heat_threshold must be non-negative")

        for field_name in (
            "mid_term_similarity_threshold",
            "segment_similarity_threshold",
            "page_similarity_threshold",
            "knowledge_threshold",
        ):
            value = _require_finite_number(getattr(self, field_name), field_name)
            if value < 0 or value > 1:
                raise ConfigurationError(f"MemoryOS {field_name} must be within [0, 1]")

        api_timeout = _require_finite_number(self.api_timeout_seconds, "api_timeout_seconds")
        if api_timeout <= 0:
            raise ConfigurationError("MemoryOS api_timeout_seconds must be positive")
        retry_wait = _require_finite_number(self.api_retry_wait_seconds, "api_retry_wait_seconds")
        if retry_wait < 0:
            raise ConfigurationError("MemoryOS api_retry_wait_seconds must be non-negative")
        backoff = _require_finite_number(self.api_retry_backoff_multiplier, "api_retry_backoff_multiplier")
        if backoff < 1:
            raise ConfigurationError("MemoryOS api_retry_backoff_multiplier must be at least 1")
        retry_max = _require_finite_number(self.api_retry_max_wait_seconds, "api_retry_max_wait_seconds")
        if retry_max <= 0:
            raise ConfigurationError("MemoryOS api_retry_max_wait_seconds must be positive")

    def to_manifest(self) -> dict[str, Any]:
        """返回不含密钥和绝对路径的公开配置 manifest。"""

        return {
            **asdict(self),
            "adapter_version": MEMORYOS_ADAPTER_VERSION,
            "source_mode": MEMORYOS_WRAPPER_SOURCE_MODE,
            "engine": "memoryos-pypi",
        }


@dataclass(frozen=True)
class MemoryOSAddEstimate:
    """MemoryOS add 阶段的成本估算。

    字段:
        page_count: conversation 会转换出的 MemoryOS QA pair 数量。
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


def _load_memoryos_pypi_classes(path_settings: PathSettings) -> dict[str, Any]:
    """加载 vendored memoryos-pypi 包，返回官方 ``Memoryos`` 类等组件。

    memoryos-pypi 目录名含连字符，无法作为常规包名导入。这里用
    ``importlib.util.spec_from_file_location`` 把它加载为命名包
    ``memoryos_pypi_vendor``，使其内部 ``from .utils import`` 相对导入正常工作，
    且不污染全局 ``utils`` 等通用模块名。加载结果带锁缓存，避免重复 exec。

    输入:
        path_settings: 项目路径配置，用于解析 MemoryOS third_party 目录。

    输出:
        dict: 含 ``Memoryos`` 类与 ``package`` 模块引用的缓存字典。

    异常:
        ConfigurationError: memoryos-pypi 包缺失或无法加载。
    """

    with _MEMORYOS_PYPI_IMPORT_LOCK:
        if _MEMORYOS_PYPI_CACHE:
            return _MEMORYOS_PYPI_CACHE
        pypi_dir = path_settings.resolve_third_party_method_path(
            MEMORYOS_METHOD_DIRECTORY,
            MEMORYOS_PYPI_SUBDIRECTORY,
        )
        init_path = pypi_dir / "__init__.py"
        if not init_path.is_file():
            raise ConfigurationError(f"MemoryOS pypi package missing: {pypi_dir}")
        spec = importlib.util.spec_from_file_location(
            _MEMORYOS_PYPI_PACKAGE_NAME,
            str(init_path),
            submodule_search_locations=[str(pypi_dir)],
        )
        if spec is None or spec.loader is None:
            raise ConfigurationError(f"MemoryOS pypi package cannot be loaded: {pypi_dir}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_MEMORYOS_PYPI_PACKAGE_NAME] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            sys.modules.pop(_MEMORYOS_PYPI_PACKAGE_NAME, None)
            raise ConfigurationError(
                f"MemoryOS pypi package failed to load: {pypi_dir}: {exc}"
            ) from exc
        memoryos_cls = getattr(module, "Memoryos", None)
        if memoryos_cls is None:
            raise ConfigurationError(
                f"MemoryOS pypi package exposes no Memoryos class: {pypi_dir}"
            )
        _MEMORYOS_PYPI_CACHE["Memoryos"] = memoryos_cls
        _MEMORYOS_PYPI_CACHE["package"] = module
        _MEMORYOS_PYPI_CACHE["package_dir"] = pypi_dir
        return _MEMORYOS_PYPI_CACHE


def build_memoryos_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 vendored memoryos-pypi 源码加本项目 wrapper 的确定性身份。

    输入:
        path_settings: 可选项目路径配置；为空时从当前项目根加载。

    输出:
        dict: 组合 SHA-256、vendored 官方文件列表以及稳定 wrapper 审计字段。
    """

    settings = path_settings or load_path_settings()
    memoryos_root = settings.resolve_third_party_method_path(MEMORYOS_METHOD_DIRECTORY)
    pypi_dir = memoryos_root / MEMORYOS_PYPI_SUBDIRECTORY
    source_files = sorted(
        [path for path in pypi_dir.glob("*.py") if path.is_file()],
        key=lambda path: path.relative_to(memoryos_root).as_posix(),
    ) + [
        path
        for path in (
            memoryos_root / "README.md",
            memoryos_root / "LICENSE",
        )
        if path.is_file()
    ]
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


class MemoryOS(BaseMemoryProvider, BaseMemorySystem, MemoryProvider):
    """使用官方 memoryos-pypi ``Memoryos`` 的统一 memory system。

    每个 conversation 对应一个独立 ``Memoryos`` 实例（user_id + data_storage_path
    隔离），clean-retry = 删该 conversation 的状态目录。注入走 ``add_memory``
    pair 粒度；检索从 ``get_response`` 剥离纯检索步骤 1-7，组装全层
    formatted_memory，跳过答题与 add_memory 写副作用。
    """

    consume_granularity: ConsumeGranularity = "pair"
    provenance_granularity = "none"

    def __init__(
        self,
        openai_api_key: str | None = None,
        openai_base_url: str | None = None,
        storage_root: str | Path | None = None,
        config: MemoryOSPaperConfig | None = None,
        efficiency_collector: EfficiencyCollector | None = None,
        *,
        backend_factory: Callable[[str], Any] | None = None,
        answer_client: Any | None = None,
        openai_settings: OpenAISettings | None = None,
        path_settings: PathSettings | None = None,
        consume_granularity: ConsumeGranularity | None = None,
    ):
        """初始化 MemoryOS adapter。

        输入:
            openai_api_key: OpenAI-compatible API key；为空时从项目配置层读取。
            openai_base_url: API base URL；为空时从项目配置层读取。
            storage_root: MemoryOS 状态文件根目录；为空时写入
                ``outputs/memoryos/<run-id>``。
            config: MemoryOS profile；为空时使用 ``MemoryOSPaperConfig()``。
            efficiency_collector: runner 管理的可选效率 observation collector。
            backend_factory: 测试可注入 fake；生产为空时构造官方 pypi Memoryos。
            answer_client: 测试可注入 fake reader；bridge get_answer 路径使用。
            openai_settings: 含 key/base_url 的私有配置，优先于单独传入的 key。
            path_settings: 项目路径配置。
            consume_granularity: v3 provider 实例级消费粒度；registry 按 benchmark
                profile 设置（LongMemEval→pair，LoCoMo→session）。缺省为类级
                ``"pair"``。LongMemEval 数据 role=user/assistant 适合 pair 聚合；
                LoCoMo 数据 role=speaker 名，pair 聚合失效，用 session 粒度由
                adapter 内部按 speaker 配对。与 LightMem/A-Mem 既有模式一致。
        """

        self.config = config or MemoryOSPaperConfig()
        self._efficiency_collector = efficiency_collector
        self._backend_factory = backend_factory
        self._answer_client = answer_client
        self.path_settings = path_settings or load_path_settings()
        if consume_granularity is not None:
            self.consume_granularity = consume_granularity

        settings = None
        if openai_settings is not None:
            self.openai_api_key = openai_settings.api_key
            self.openai_base_url = openai_settings.base_url
        else:
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
            self.openai_api_key = openai_api_key
            self.openai_base_url = openai_base_url

        path_settings = settings.paths if settings is not None else self.path_settings
        if storage_root is None:
            selected_storage_root = path_settings.outputs_root / "memoryos" / _new_memoryos_run_id()
        else:
            selected_storage_root = Path(storage_root)
        self.storage_root = selected_storage_root.expanduser().resolve()
        self.storage_root.mkdir(parents=True, exist_ok=True)

        # 生产路径预加载 pypi 包，确保 source identity 与 backend 构造可用。
        if self._backend_factory is None:
            _load_memoryos_pypi_classes(self.path_settings)

        self._backends: dict[str, Any] = {}
        self._conversation_metadata: dict[str, dict[str, Any]] = {}
        self._native_isolation_to_conversation_id: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # bridge 路径：add / get_answer / load_existing_conversation_state
    # ------------------------------------------------------------------ #

    def add(self, conversations: Conversation | list[Conversation]) -> AddResult:
        """写入一个或多个 conversation（bridge 兼容路径）。

        内部把 conversation 转成 MemoryOS QA pair，逐个调用 ``add_memory``。
        注意 ``add_memory`` 会触发 LLM（mid-term summarize + profile/knowledge
        抽取）；离线测试须 stub ``backend.client.chat_completion``。

        输入:
            conversations: 单个公开 Conversation 或列表；即使对象上有
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
            if conversation.conversation_id in self._backends:
                raise ConfigurationError(
                    f"MemoryOS conversation already added: {conversation.conversation_id}"
                )
            backend = self._get_or_create_backend(conversation.conversation_id)
            self._register_conversation_metadata(conversation)
            pages = self.conversation_to_memory_pages(conversation)
            with self._suppress_stdout_if_needed():
                for page in pages:
                    backend.add_memory(
                        user_input=page["user_input"],
                        agent_response=page["agent_response"],
                        timestamp=page["timestamp"],
                    )
            conversation_ids.append(conversation.conversation_id)

        return AddResult(
            conversation_ids=conversation_ids,
            metadata={
                "method": "MemoryOS",
                "config": self._safe_config_metadata(),
            },
        )

    def load_existing_conversation_state(self, conversation: Conversation) -> None:
        """挂载已写入磁盘的 conversation 状态，不重复 add 历史对话。

        pypi Memoryos 构造时会从 data_storage_path load JSON 状态，因此重建
        backend 即可恢复 short/mid/long 各层。resume 路径使用。

        输入:
            conversation: 需要恢复的 conversation。方法会根据 conversation_id
                定位 storage_root/<safe-id>/ 下的 pypi 状态目录。

        输出:
            None。恢复后可直接调用 retrieve / get_answer。
        """

        if conversation.conversation_id in self._backends:
            return
        state_dir = self.storage_root / _safe_path_name(conversation.conversation_id)
        _validate_existing_pypi_state(state_dir)
        self._register_conversation_metadata(conversation)
        self._get_or_create_backend(conversation.conversation_id)

    def get_answer(self, question: Question) -> AnswerResult:
        """基于 retrieve 的 formatted_memory 回答公开问题（bridge 兼容路径）。

        主线（retrieve-first runner）不调用本方法，改由 framework reader 答题。
        bridge 路径使用注入的 answer_client；未注入时报错。

        输入:
            question: method 可见问题，不包含 gold answer 或 evidence。

        输出:
            AnswerResult: 答案和可审计 metadata。
        """

        retrieval = self.retrieve(question)
        prompt = _user_visible_prompt_text(retrieval.prompt_messages)
        answer_started_ns = perf_counter_ns()
        collector = self._efficiency_collector
        answer = self._call_answer_client(prompt=prompt, question=question)
        if collector is not None and collector.enabled:
            collector.record_answer_generation(latency_ms=_elapsed_ms(answer_started_ns))
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=str(answer).strip(),
            metadata={
                "method": "MemoryOS",
                "reader_prompt_version": MEMORYOS_READER_PROMPT_VERSION,
            },
        )

    # ------------------------------------------------------------------ #
    # v3 provider 路径：ingest / retrieve / end_conversation
    # ------------------------------------------------------------------ #

    def ingest(self, unit: IngestUnit) -> IngestResult:
        """按 v3 协议写入一个 ingest unit。

        pair 粒度：``TurnPair`` → ``add_memory``。dangling user（second=None 且
        first.role=="user"）→ ``agent_response=""``；orphan assistant（second=None
        且 first.role!="user"）→ ``user_input=""``。session 粒度（SessionBatch）
        作为 bridge 兼容入参，内部转 pages 逐个 add_memory。

        输入:
            unit: TurnPair 或 SessionBatch（兼容）。

        输出:
            IngestResult: 携带隔离单元引用。
        """

        if isinstance(unit, TurnPair):
            return self._ingest_pair(unit)
        if isinstance(unit, SessionBatch):
            return self._ingest_session_batch(unit)
        raise ConfigurationError(
            "MemoryOS native provider only accepts TurnPair or SessionBatch ingest units"
        )

    def _ingest_pair(self, pair: TurnPair) -> IngestResult:
        """把 v3 TurnPair 转成 add_memory 调用。"""

        isolation_key = pair.isolation_key
        conversation_id = self._conversation_id_from_event(pair.first)
        self._native_isolation_to_conversation_id[isolation_key] = conversation_id
        self._ensure_native_metadata(pair.first, conversation_id)
        backend = self._get_or_create_backend(conversation_id)
        user_input, agent_response = self._pair_to_add_memory_args(pair)
        timestamp = self._timestamp_from_event(pair.first)
        with self._suppress_stdout_if_needed():
            backend.add_memory(
                user_input=user_input,
                agent_response=agent_response,
                timestamp=timestamp,
            )
        return IngestResult(unit_ref=UnitRef(isolation_key))

    def _ingest_session_batch(self, batch: SessionBatch) -> IngestResult:
        """把 v3 SessionBatch 转成逐个 add_memory（session 粒度入参）。

        session 粒度用于 LoCoMo 等 role=speaker 名的数据：pair 聚合按
        role=="user" 锚会失效，因此整 session 一次投递，adapter 内部用
        ``conversation_to_memory_pages`` 按 speaker/role 配对成 QA pair，
        保证与 bridge add 等价。
        """

        conversation = self._conversation_from_session_batch(batch)
        conversation_id = conversation.conversation_id
        self._native_isolation_to_conversation_id[batch.isolation_key] = conversation_id
        self._register_conversation_metadata(conversation)
        backend = self._get_or_create_backend(conversation_id)
        pages = self.conversation_to_memory_pages(conversation)
        with self._suppress_stdout_if_needed():
            for page in pages:
                backend.add_memory(
                    user_input=page["user_input"],
                    agent_response=page["agent_response"],
                    timestamp=page["timestamp"],
                )
        return IngestResult(unit_ref=UnitRef(batch.isolation_key))

    def _conversation_from_session_batch(self, batch: SessionBatch) -> Conversation:
        """从 v3 SessionBatch 恢复 conversation_to_memory_pages 需要的 Conversation。"""

        first_event = batch.events[0] if batch.events else None
        if first_event is None:
            raise ConfigurationError("MemoryOS SessionBatch has no events")
        metadata = dict(first_event.metadata.get("conversation_metadata") or {})
        conversation_id = self._conversation_id_from_event(first_event)
        metadata["conversation_id"] = conversation_id
        return Conversation(
            conversation_id=conversation_id,
            sessions=[
                Session(
                    session_id=batch.session_id or "",
                    session_time=batch.session_time,
                    metadata=dict(batch.metadata),
                    turns=[self._turn_from_event(event) for event in batch.events],
                )
            ],
            metadata=metadata,
        )

    @staticmethod
    def _turn_from_event(event: TurnEvent) -> Turn:
        """从规范 TurnEvent 恢复 conversation_to_memory_pages 需要的 Turn。"""

        return Turn(
            turn_id=event.turn_id,
            speaker=event.speaker_name or event.role,
            content=MemoryOS._original_content_from_event(event),
            normalized_role=event.role if event.role in {"user", "assistant"} else None,
            turn_time=MemoryOS._optional_event_text(event, "original_turn_time"),
            metadata=dict(event.metadata.get("turn_metadata") or {}),
        )

    @staticmethod
    def _optional_event_text(event: TurnEvent, field_name: str) -> str | None:
        """读取 TurnEvent metadata 中的可选文本字段。"""

        value = event.metadata.get(field_name)
        return value if isinstance(value, str) else None

    def end_conversation(self, ref: UnitRef) -> None:
        """conversation 边界钩子，默认无操作。"""

        return None

    def retrieve(
        self, question: Question | RetrievalQuery
    ) -> AnswerPromptResult | RetrievalResult:
        """执行 MemoryOS 纯检索并格式化全层上下文。

        复刻官方 ``get_response`` 步骤 1-7（``memoryos.py:259-302``）：
        1. ``retriever.retrieve_context`` 取中期 pages + user/assistant knowledge；
        2. ``short_term_memory.get_all`` 取短期 history；
        4. ``user_long_term_memory.get_raw_user_profile`` 取长期 profile；
        3/5/6 把上述各层组装成文本。
        **跳过步骤 8-9 答题与步骤 10 的 add_memory 写副作用**。

        输入:
            question: 公开问题或 v3 RetrievalQuery。

        输出:
            AnswerPromptResult（Question 口径）或 RetrievalResult（RetrievalQuery
            口径），均含覆盖短/中/长各层的 formatted_memory。
        """

        if isinstance(question, RetrievalQuery):
            return self._retrieve_native(question)

        conversation_id = question.conversation_id
        backend = self._backends.get(conversation_id)
        if backend is None:
            raise ConfigurationError(
                f"MemoryOS has no conversation state for question: {conversation_id}"
            )

        effective_text = _effective_question_text(question)
        collector = self._efficiency_collector
        retrieval_started_ns = perf_counter_ns()
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                retrieval_results = self._retrieve_context(backend, effective_text)
        else:
            retrieval_results = self._retrieve_context(backend, effective_text)
        formatted_memory = _assemble_memoryos_formatted_memory(backend, retrieval_results)
        prompt_messages = _build_memoryos_prompt_messages(question, formatted_memory)
        answer_prompt = "\n\n".join(
            f"[{message.role}]\n{message.content}" for message in prompt_messages
        )
        if collector is not None and collector.enabled:
            collector.record_retrieval_result_if_question_scope(
                latency_ms=_elapsed_ms(retrieval_started_ns),
                injected_memory_context_tokens=_count_openai_tokens(
                    formatted_memory,
                    self.config.llm_model,
                ),
            )

        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt=answer_prompt,
            prompt_messages=prompt_messages,
            metadata={
                "method": "MemoryOS",
                "answer_context": formatted_memory,
                "retrieved_page_count": len(retrieval_results["retrieved_pages"]),
                "retrieved_user_knowledge_count": len(
                    retrieval_results["retrieved_user_knowledge"]
                ),
                "retrieved_assistant_knowledge_count": len(
                    retrieval_results["retrieved_assistant_knowledge"]
                ),
                "retrieval_profile": "memoryos_pypi_retrieve",
                "answer_prompt_profile": MEMORYOS_READER_PROMPT_VERSION,
            },
        )

    def _retrieve_native(self, query: RetrievalQuery) -> RetrievalResult:
        """执行 v3 检索并返回不生成最终答案的 RetrievalResult。"""

        source_question = query.source_question or Question(
            question_id=query.isolation_key,
            conversation_id=query.isolation_key,
            text=query.query_text,
            question_time=query.question_time,
        )
        conversation_id = self._native_isolation_to_conversation_id.get(
            query.isolation_key,
            source_question.conversation_id,
        )
        native_question = Question(
            question_id=source_question.question_id,
            conversation_id=conversation_id,
            text=query.query_text,
            question_time=query.question_time or source_question.question_time,
            category=source_question.category,
            metadata=dict(source_question.metadata),
        )
        retrieval = self.retrieve(native_question)
        formatted_memory = (
            retrieval.metadata.get("answer_context")
            if isinstance(retrieval.metadata.get("answer_context"), str)
            else ""
        )
        return RetrievalResult(
            formatted_memory=formatted_memory or "(No relevant memories found)",
            prompt_messages=tuple(retrieval.prompt_messages),
            metadata=dict(retrieval.metadata),
        )

    def _retrieve_context(self, backend: Any, query: str) -> dict[str, Any]:
        """调用官方 ``retriever.retrieve_context``，传入 config 检索阈值。

        retrieve_context 是纯 embedding 检索（``search_sessions`` /
        ``search_user_knowledge`` / ``search_assistant_knowledge``），不调 LLM。
        注意 ``search_sessions`` 会更新 mid_term 访问统计（N_visit/last_visit_time/
        H_segment）并 save——这是 MemoryOS 检索算法固有行为（用于 LFU/heat），
        非 add_memory 写副作用。
        """

        with self._suppress_stdout_if_needed():
            return backend.retriever.retrieve_context(
                user_query=query,
                user_id=backend.user_id,
                segment_similarity_threshold=self.config.segment_similarity_threshold,
                page_similarity_threshold=self.config.page_similarity_threshold,
                knowledge_threshold=self.config.knowledge_threshold,
                top_k_sessions=self.config.top_k_sessions,
                top_k_knowledge=self.config.top_k_knowledge,
            )

    # ------------------------------------------------------------------ #
    # backend 构造与隔离
    # ------------------------------------------------------------------ #

    def _get_or_create_backend(self, conversation_id: str) -> Any:
        """返回当前 conversation 隔离的官方 pypi Memoryos 实例。"""

        if conversation_id not in self._backends:
            if self._backend_factory is None:
                backend = self._create_official_backend(conversation_id)
            else:
                backend = self._backend_factory(conversation_id)
            self._backends[conversation_id] = backend
        return self._backends[conversation_id]

    def _create_official_backend(self, conversation_id: str) -> Any:
        """构造 conversation 独占的官方 pypi Memoryos，并注入 timeout/retry。"""

        classes = _load_memoryos_pypi_classes(self.path_settings)
        memoryos_cls = classes["Memoryos"]
        data_storage_path = self.storage_root / _safe_path_name(conversation_id)
        data_storage_path.mkdir(parents=True, exist_ok=True)
        # pypi OpenAIClient 构造时 OpenAI(api_key) 懒连接，占位 key 不报错；
        # 真实 key 由调用方传入。
        api_key = self.openai_api_key or "memoryos-placeholder-key"
        with self._suppress_stdout_if_needed():
            backend = memoryos_cls(
                user_id=_safe_user_id(conversation_id),
                openai_api_key=api_key,
                data_storage_path=str(data_storage_path),
                openai_base_url=self.openai_base_url,
                assistant_id=MEMORYOS_DEFAULT_ASSISTANT_ID,
                short_term_capacity=self.config.short_term_capacity,
                mid_term_capacity=self.config.mid_term_capacity,
                long_term_knowledge_capacity=self.config.long_term_knowledge_capacity,
                retrieval_queue_capacity=self.config.retrieval_queue_capacity,
                mid_term_heat_threshold=self.config.mid_term_heat_threshold,
                mid_term_similarity_threshold=self.config.mid_term_similarity_threshold,
                llm_model=self.config.llm_model,
                embedding_model_name=self.config.embedding_model_name,
            )
        self._inject_api_retry_timeout(backend)
        return backend

    def _inject_api_retry_timeout(self, backend: Any) -> None:
        """对 pypi OpenAIClient.chat_completion 注入 timeout/retry。

        不修改 vendored 源码；只在 backend 构造后替换 chat_completion 方法。
        add_memory 触发的所有 LLM（updater summarize/continuity/meta_info +
        profile/knowledge 抽取）都走 ``client.chat_completion``，统一被覆盖。
        """

        original_chat_completion = backend.client.chat_completion
        config = self.config
        collector = self._efficiency_collector

        def chat_completion_with_retry(
            model: str,
            messages: list[dict[str, Any]],
            temperature: float = 0.7,
            max_tokens: int = 2000,
        ) -> str:
            """带 timeout/retry 与效率观测的 chat_completion 包装。"""

            total_attempts = config.api_max_retries + 1
            for attempt in range(1, total_attempts + 1):
                try:
                    response = backend.client.client.chat.completions.create(
                        model=model or config.llm_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=config.api_timeout_seconds,
                    )
                    content = response.choices[0].message.content or ""
                    _record_memoryos_llm_call(
                        collector,
                        model=model or config.llm_model,
                        messages=messages,
                        response=response,
                        content=content,
                        config=config,
                    )
                    return content
                except _RETRYABLE_API_ERRORS as error:
                    if attempt >= total_attempts:
                        LOGGER.error(
                            "MemoryOS API call failed after %s attempts: %s",
                            total_attempts,
                            type(error).__name__,
                        )
                        raise
                    wait_seconds = _retry_wait_seconds(config, attempt)
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

        backend.client.chat_completion = chat_completion_with_retry

    def get_debug_state(self, conversation_id: str) -> Any:
        """返回某个 conversation 的 pypi Memoryos backend（测试与 debug 用）。

        输入:
            conversation_id: 已写入的 conversation id。

        输出:
            官方 pypi Memoryos 实例，暴露 short_term_memory / mid_term_memory /
            user_long_term_memory / assistant_long_term_memory / retriever /
            updater / client 等属性。
        """

        backend = self._backends.get(conversation_id)
        if backend is None:
            raise ConfigurationError(f"MemoryOS state not found: {conversation_id}")
        return backend

    def get_debug_package(self) -> Any:
        """返回 vendored memoryos-pypi 包模块（测试与 debug 用）。"""

        return _load_memoryos_pypi_classes(self.path_settings)["package"]

    # ------------------------------------------------------------------ #
    # 静态辅助：page 转换、workload 估算
    # ------------------------------------------------------------------ #

    @staticmethod
    def conversation_to_memory_pages(
        conversation: Conversation,
    ) -> list[dict[str, str]]:
        """把统一 Conversation 转成 MemoryOS add_memory 的 QA pair 列表。

        按 normalized_role 配对：user turn 开启一个 page，紧跟 assistant 闭合；
        dangling user（无后续 assistant）→ agent_response=""；orphan assistant
        （无前置 user）→ user_input=""。保证不丢 turn。

        输入:
            conversation: 已校验的 conversation-QA v2 Conversation。

        输出:
            list[dict[str, str]]: 每条含 user_input、agent_response、timestamp。
        """

        pages: list[dict[str, str]] = []
        for session in conversation.sessions:
            timestamp = (
                session.session_time or session.start_time or session.end_time or ""
            )
            for turn in session.turns:
                content = _turn_text_with_image_captions(turn)
                role = _turn_normalized_role(turn)
                if role == "user":
                    pages.append(
                        {
                            "user_input": content,
                            "agent_response": "",
                            "timestamp": timestamp,
                        }
                    )
                elif role == "assistant":
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
                    # 未知 role：按 speaker 顺序推断（LoCoMo speaker_a 视作 user）。
                    speaker_a, speaker_b = _resolve_speakers(conversation)
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

    @staticmethod
    def estimate_add_workload(
        conversation: Conversation,
        config: MemoryOSPaperConfig | None = None,
    ) -> MemoryOSAddEstimate:
        """估算 add 阶段的 MemoryOS 更新成本。

        输入:
            conversation: 待写入的统一 Conversation。
            config: MemoryOS 配置；为空时使用 pypi 默认。

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

    # ------------------------------------------------------------------ #
    # v3 event → add_memory 参数转换
    # ------------------------------------------------------------------ #

    def _pair_to_add_memory_args(self, pair: TurnPair) -> tuple[str, str]:
        """把 v3 TurnPair 转成 (user_input, agent_response)。

        - second 非 None：first=user, second=assistant（完整 pair）。
        - second None + first.role=="user"：dangling user → agent_response=""。
        - second None + first.role!="user"：orphan assistant → user_input=""。
        """

        first_content = self._original_content_from_event(pair.first)
        if pair.second is None:
            if pair.first.role == "user":
                return first_content, ""
            return "", first_content
        second_content = self._original_content_from_event(pair.second)
        return first_content, second_content

    @staticmethod
    def _original_content_from_event(event: TurnEvent) -> str:
        """读取事件前原始 turn 文本，避免图片 caption 重复拼接。"""

        original = event.metadata.get("original_content")
        if isinstance(original, str):
            return original
        return event.content

    @staticmethod
    def _conversation_id_from_event(event: TurnEvent) -> str:
        """从 v3 event metadata 中读取原始 conversation id。"""

        conversation_id = event.metadata.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id.strip():
            return conversation_id
        return event.isolation_key

    @staticmethod
    def _timestamp_from_event(event: TurnEvent) -> str:
        """从 v3 event 读取 timestamp，缺失时回退当前时间。"""

        original = event.metadata.get("original_turn_time")
        if isinstance(original, str) and original.strip():
            return original
        if event.timestamp:
            return event.timestamp
        return _pypi_timestamp_now()

    def _ensure_native_metadata(
        self,
        event: TurnEvent,
        conversation_id: str,
    ) -> None:
        """登记 native conversation 的公开 metadata。"""

        raw = event.metadata.get("conversation_metadata")
        metadata = dict(raw) if isinstance(raw, dict) else {}
        metadata["conversation_id"] = conversation_id
        self._conversation_metadata[conversation_id] = metadata

    def _register_conversation_metadata(self, conversation: Conversation) -> None:
        """登记 bridge conversation 的公开 metadata。"""

        self._conversation_metadata[conversation.conversation_id] = {
            **conversation.metadata,
            "conversation_id": conversation.conversation_id,
        }

    def _call_answer_client(self, prompt: str, question: Question) -> str:
        """调用 bridge answer client；未注入时报错。"""

        if self._answer_client is None:
            raise ConfigurationError(
                f"MemoryOS answer client is not available for {question.conversation_id}"
            )
        response = self._suppress_stdout_if_needed(
            self._answer_client.create_answer,
            prompt,
        )
        return str(response)

    @contextlib.contextmanager
    def _suppress_stdout_if_needed(self, *args: Any, **kwargs: Any):
        """按配置压制第三方 stdout；可作 contextmanager 或函数包装器。"""

        if not self.config.suppress_official_stdout:
            if args or kwargs:
                func = args[0]
                return func(*args[1:], **kwargs)
            yield
            return
        if args:
            func = args[0]
            with contextlib.redirect_stdout(io.StringIO()):
                return func(*args[1:], **kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            yield

    def _safe_config_metadata(self) -> dict[str, Any]:
        """返回可写入日志的配置摘要，不包含 API key。"""

        return self.config.to_manifest()


# ---------------------------------------------------------------------- #
# formatted_memory 全层组装（忠实复刻 get_response :270-302）
# ---------------------------------------------------------------------- #


def _assemble_memoryos_formatted_memory(
    backend: Any,
    retrieval_results: dict[str, Any],
) -> str:
    """把短期/中期/长期各层记忆组装成 formatted_memory。

    忠实复刻官方 ``get_response``（``memoryos.py:268-302``）的文本拼装口径，
    覆盖全部记忆层：
    - 短期：``short_term_memory.get_all()`` → history_text。
    - 中期：``retrieved_pages`` → retrieval_text。
    - 长期 profile：``user_long_term_memory.get_raw_user_profile`` → background。
    - 长期 user knowledge：``retrieved_user_knowledge`` → background 追加。
    - 长期 assistant knowledge：``retrieved_assistant_knowledge``。

    漏任何一层 = 记忆不完整 = 数字失真（ws02.5(c) 完整性）。

    输入:
        backend: pypi Memoryos 实例。
        retrieval_results: ``retriever.retrieve_context`` 返回的 dict。

    输出:
        str: 覆盖短/中/长各层的 formatted_memory。
    """

    # 步骤2：短期 history（:269-273）
    short_term_history = backend.short_term_memory.get_all()
    history_text = "\n".join(
        [
            f"User: {qa.get('user_input', '')}\nAssistant: {qa.get('agent_response', '')} (Time: {qa.get('timestamp', '')})"
            for qa in short_term_history
        ]
    )

    # 步骤3：中期 retrieved_pages（:276-279）
    retrieved_pages = retrieval_results.get("retrieved_pages") or []
    retrieval_text = "\n".join(
        [
            f"【Historical Memory】\nUser: {page.get('user_input', '')}\nAssistant: {page.get('agent_response', '')}\nTime: {page.get('timestamp', '')}\nConversation chain overview: {page.get('meta_info', 'N/A')}"
            for page in retrieved_pages
            if isinstance(page, dict)
        ]
    )

    # 步骤4：长期 profile（:282-284）
    user_profile_text = backend.user_long_term_memory.get_raw_user_profile(backend.user_id)
    if not user_profile_text or user_profile_text.lower() == "none":
        user_profile_text = "No detailed profile available yet."

    # 步骤5：长期 user knowledge（:287-293）
    retrieved_user_knowledge = retrieval_results.get("retrieved_user_knowledge") or []
    user_knowledge_background = ""
    if retrieved_user_knowledge:
        user_knowledge_background = "\n【Relevant User Knowledge Entries】\n"
        for kn_entry in retrieved_user_knowledge:
            if isinstance(kn_entry, dict):
                user_knowledge_background += (
                    f"- {kn_entry.get('knowledge', '')} (Recorded: {kn_entry.get('timestamp', '')})\n"
                )
            else:
                user_knowledge_background += f"- {kn_entry}\n"
    background_context = f"【User Profile】\n{user_profile_text}\n{user_knowledge_background}"

    # 步骤6：长期 assistant knowledge（:297-302）
    retrieved_assistant_knowledge = (
        retrieval_results.get("retrieved_assistant_knowledge") or []
    )
    assistant_knowledge_text = "【Assistant Knowledge Base】\n"
    if retrieved_assistant_knowledge:
        for ak_entry in retrieved_assistant_knowledge:
            if isinstance(ak_entry, dict):
                assistant_knowledge_text += (
                    f"- {ak_entry.get('knowledge', '')} (Recorded: {ak_entry.get('timestamp', '')})\n"
                )
            else:
                assistant_knowledge_text += f"- {ak_entry}\n"
    else:
        assistant_knowledge_text += "- No relevant assistant knowledge found for this query.\n"

    parts = [history_text, retrieval_text, background_context, assistant_knowledge_text]
    return "\n\n".join(text for text in parts if text and text.strip())


def _build_memoryos_prompt_messages(
    question: Question,
    formatted_memory: str,
) -> list[PromptMessage]:
    """构造 unified reader 使用的 prompt messages。

    主线 retrieve-first runner 用 framework reader 答题，prompt 由 framework 构造；
    本方法为 bridge get_answer 与 metadata 记录提供一致口径。
    """

    return [
        PromptMessage(role="system", content="You are a helpful assistant."),
        PromptMessage(
            role="user",
            content=(
                f"Question time:{question.question_time} and question:{question.text}\n"
                "Please answer the question based on the following memories: "
                f"{formatted_memory}"
            )
            if question.question_time
            else f"Please answer the question based on the following memories: {formatted_memory}\nQuestion: {question.text}"
        ),
    ]


# ---------------------------------------------------------------------- #
# 辅助函数
# ---------------------------------------------------------------------- #


def _resolve_speakers(conversation: Conversation) -> tuple[str, str]:
    """解析 MemoryOS 所需的 speaker_a / speaker_b（LoCoMo 兼容）。"""

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


def _turn_normalized_role(turn: Any) -> str | None:
    """读取 turn 的归一化 role（user/assistant），未归一时返回 None。"""

    role = getattr(turn, "normalized_role", None)
    if role in {"user", "assistant"}:
        return role
    metadata_role = turn.metadata.get("role") if turn.metadata else None
    if metadata_role in {"user", "assistant"}:
        return metadata_role
    return None


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

    return "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in value
    )


def _safe_user_id(conversation_id: str) -> str:
    """把 conversation_id 转成 pypi Memoryos 的 user_id。

    user_id 同时用作目录名（users/<user_id>）和 profile key，需路径安全且
    避免特殊字符。复用 _safe_path_name。
    """

    return _safe_path_name(conversation_id) or "default_user"


def _new_memoryos_run_id() -> str:
    """生成 MemoryOS 默认状态目录使用的唯一 run id。"""

    return f"run-{uuid.uuid4().hex[:12]}"


def _pypi_timestamp_now() -> str:
    """返回 pypi 兼容的当前时间戳（与官方 get_timestamp 格式一致）。"""

    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


def _effective_question_text(question: Question) -> str:
    """构造含可选时间上下文的有效问题文本。"""

    if question.question_time:
        return f"Question time: {question.question_time}. Question: {question.text}"
    return str(question.text)


def _elapsed_ms(started_ns: int) -> float:
    """把 perf_counter_ns 起点转换为非负毫秒。"""

    return max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)


def _count_openai_tokens(text: str, model_name: str) -> int:
    """使用 OpenAI-compatible tokenizer 估算注入 LLM 的文本 token 数。"""

    if not text:
        return 0
    return _TiktokenCounter(model_name).count_tokens(text)


def _retry_wait_seconds(config: MemoryOSPaperConfig, failed_attempt_index: int) -> float:
    """计算下一次 MemoryOS API 重试前的等待时间。"""

    wait_seconds = config.api_retry_wait_seconds * (
        config.api_retry_backoff_multiplier ** (failed_attempt_index - 1)
    )
    return min(wait_seconds, config.api_retry_max_wait_seconds)


def _record_memoryos_llm_call(
    collector: EfficiencyCollector | None,
    *,
    model: str,
    messages: list[dict[str, Any]],
    response: Any,
    content: str,
    config: MemoryOSPaperConfig,
) -> None:
    """记录 MemoryOS 通过 chat_completion 发出的 LLM 调用。"""

    if collector is None or not collector.enabled:
        return
    prompt_tokens, completion_tokens = extract_api_token_usage(getattr(response, "usage", None))
    usage = resolve_token_usage(
        api_input_tokens=prompt_tokens,
        api_output_tokens=completion_tokens,
        prompt_text=_messages_to_text(messages),
        output_text=content,
        tokenizer=_TiktokenCounter(model or config.llm_model),
    )
    collector.record_llm_call(
        model_id=MEMORYOS_MEMORY_LLM_MODEL_ID,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        token_measurement_source=usage.source,
    )


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


def _user_visible_prompt_text(messages: list[PromptMessage]) -> str:
    """把 role messages 转成 bridge reader 使用的 prompt 文本。"""

    if len(messages) == 1:
        return messages[0].content
    return "\n\n".join(
        f"[{message.role}]\n{message.content}" for message in messages
    )


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


_RETRYABLE_API_ERRORS = (
    APITimeoutError,
    APIConnectionError,
    TimeoutError,
    ConnectionError,
)


def _validate_existing_pypi_state(state_dir: Path) -> None:
    """校验 resume 所需的 pypi 状态目录结构。

    pypi 状态目录：``users/<user_id>/{short_term,mid_term,long_term_user}.json``
    + ``assistants/<assistant_id>/long_term_assistant.json``。构造 Memoryos 时
    会 load 这些 JSON；这里只做最小存在性校验，避免 resume 一个空目录。

    输入:
        state_dir: 单个 conversation 的 MemoryOS 状态目录（data_storage_path）。

    异常:
        ConfigurationError: 必需的 short_term.json 缺失或状态目录不存在。
    """

    if not state_dir.is_dir():
        raise ConfigurationError(
            f"MemoryOS existing state directory missing: {state_dir}"
        )
    # pypi 把 user_id 目录放在 users/ 下；user_id 由 conversation_id 派生。
    # 这里不强校验 user_id 子目录名（避免与 _safe_user_id 耦合），只确认至少
    # 有一个 users/<id>/short_term.json。
    users_dir = state_dir / "users"
    if not users_dir.is_dir():
        raise ConfigurationError(
            f"MemoryOS existing state missing users/ directory: {state_dir}"
        )
    short_term_files = list(users_dir.glob("*/short_term.json"))
    if not short_term_files:
        raise ConfigurationError(
            f"MemoryOS existing state missing users/*/short_term.json: {state_dir}"
        )


def clean_memoryos_conversation_state(
    storage_root: str | Path,
    conversation_id: str,
) -> None:
    """删除 MemoryOS 单个 conversation 的状态目录。

    pypi 每 conversation 一个 data_storage_path 目录（含 users/ + assistants/），
    删该目录即 clean-retry。

    输入:
        storage_root: 当前 run 的 MemoryOS method state 根目录。
        conversation_id: 需要重新 ingest 的 conversation id。

    输出:
        None。目标目录不存在时视为已经干净。
    """

    root = Path(storage_root).expanduser().resolve()
    target = (root / _safe_path_name(conversation_id)).resolve()
    if root == target or root not in target.parents:
        raise ConfigurationError(f"Unsafe MemoryOS state cleanup path: {target}")
    shutil.rmtree(target, ignore_errors=True)


__all__ = [
    "MemoryOS",
    "MemoryOSAddEstimate",
    "MemoryOSPaperConfig",
    "build_memoryos_source_identity",
    "clean_memoryos_conversation_state",
]

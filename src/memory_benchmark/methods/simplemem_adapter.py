"""SimpleMem text backend 的协议 v3 adapter。

T1 先落地配置、资源校验、source identity 和 registry 骨架；后续 task 会把
`SimpleMem` 类补齐为真实 ingest/retrieve provider。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re
import shutil
import sys
from typing import Any

from memory_benchmark.config import OpenAISettings, PathSettings, load_path_settings
from memory_benchmark.core import ConfigurationError, PromptMessage
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    resolve_token_usage,
)
from memory_benchmark.core.provider_protocol import (
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    RetrievedItem,
    TurnEvent,
    UnitRef,
)


SIMPLEMEM_ADAPTER_VERSION = "simplemem-text-v1"
SIMPLEMEM_METHOD_DIRECTORY = "SimpleMem"
SIMPLEMEM_OFFICIAL_PROFILE_NAME = "official-text-v1"
SIMPLEMEM_WRAPPER_LOGICAL_PATH = "src/memory_benchmark/methods/simplemem_adapter.py"
SIMPLEMEM_SOURCE_MODE = "vendored-simplemem-text-plus-wrapper"
SIMPLEMEM_LLM_MODEL_ID = "simplemem-llm"
SIMPLEMEM_CONVERSATION_MARKER = "conversation_id.txt"
_LOCOMO_TIMESTAMP_PATTERN = re.compile(
    r"^\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*"
    r"(?P<period>am|pm)\s+on\s+"
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+),\s*"
    r"(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
SimpleMemSystemFactory = Callable[[str, Path], Any]
SIMPLEMEM_ANSWER_PROMPT_SOURCE = (
    "third_party/methods/SimpleMem/simplemem/core/answer_generator.py:"
    "43-52,117-153"
)
_SIMPLEMEM_ANSWER_SYSTEM_PROMPT = (
    # 官方 AnswerGenerator.generate_answer() messages[0]，见 answer_generator.py:43-47。
    "You are a professional Q&A assistant. Extract concise answers from context. "
    "You must output valid JSON format."
)


@dataclass(frozen=True)
class SimpleMemConfig:
    """SimpleMem text backend 运行 profile。"""

    llm_model: str
    embedding_model_path: str
    embedding_dimension: int
    window_size: int
    overlap_size: int
    semantic_top_k: int
    keyword_top_k: int
    structured_top_k: int
    max_workers: int
    api_timeout_seconds: float = 60.0
    api_max_retries: int = 8
    enable_planning: bool = True
    enable_reflection: bool = True
    max_reflection_rounds: int = 2
    enable_parallel_processing: bool = True
    enable_parallel_retrieval: bool = True
    profile_name: str = SIMPLEMEM_OFFICIAL_PROFILE_NAME

    def __post_init__(self) -> None:
        """强校验影响实验语义的 SimpleMem 参数。"""

        if not self.llm_model.strip():
            raise ConfigurationError("SimpleMem llm_model is required")
        if not self.embedding_model_path.strip():
            raise ConfigurationError("SimpleMem embedding_model_path is required")
        for field_name in (
            "embedding_dimension",
            "window_size",
            "semantic_top_k",
            "keyword_top_k",
            "structured_top_k",
            "max_workers",
        ):
            if getattr(self, field_name) < 1:
                raise ConfigurationError(f"SimpleMem {field_name} must be positive")
        if self.overlap_size < 0:
            raise ConfigurationError("SimpleMem overlap_size cannot be negative")
        if self.overlap_size >= self.window_size:
            raise ConfigurationError(
                "SimpleMem overlap_size must be smaller than window_size"
            )
        if self.api_timeout_seconds <= 0:
            raise ConfigurationError("SimpleMem api_timeout_seconds must be positive")
        if self.api_max_retries < 0:
            raise ConfigurationError("SimpleMem api_max_retries cannot be negative")
        if self.max_reflection_rounds < 0:
            raise ConfigurationError(
                "SimpleMem max_reflection_rounds cannot be negative"
            )

    def validate_required_local_resources(self, path_settings: PathSettings) -> None:
        """校验 SimpleMem 本地 embedding 模型目录存在。"""

        model_path = _resolve_project_relative_path(
            self.embedding_model_path,
            path_settings.project_root,
        )
        if model_path is not None and not model_path.is_dir():
            raise ConfigurationError(
                "SimpleMem required local embedding model missing: "
                f"{model_path}. Download Qwen/Qwen3-Embedding-0.6B to "
                "models/Qwen3-Embedding-0.6B before running prediction."
            )

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 secret 与绝对状态路径的公开配置。"""

        return {
            **asdict(self),
            "adapter_version": SIMPLEMEM_ADAPTER_VERSION,
            "official_profile": SIMPLEMEM_OFFICIAL_PROFILE_NAME,
            "llm_provider": "openai-compatible",
            "embedding_provider": "sentence-transformers-local",
            "backend": "text",
        }


class SimpleMem(MemoryProvider):
    """SimpleMem text backend provider。"""

    consume_granularity = "turn"
    session_memory_report = False
    provenance_granularity = "none"

    def __init__(
        self,
        *,
        config: SimpleMemConfig,
        path_settings: PathSettings,
        storage_root: Path,
        system_factory: SimpleMemSystemFactory | None = None,
        openai_settings: OpenAISettings | None = None,
        efficiency_collector: EfficiencyCollector | None = None,
    ) -> None:
        """保存构造依赖并延迟初始化每个 isolation 的 SimpleMemSystem。"""

        config.validate_required_local_resources(path_settings)
        self.config = config
        self.path_settings = path_settings
        self.storage_root = storage_root
        self._system_factory = system_factory
        self._openai_settings = openai_settings
        self._efficiency_collector = efficiency_collector
        self._systems_by_isolation_key: dict[str, Any] = {}
        self._state_dirs_by_isolation_key: dict[str, Path] = {}
        self._finalized_isolation_keys: set[str] = set()

    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """把 turn 事件写入 SimpleMem 的 `add_dialogue()` 入口。"""

        if not isinstance(unit, TurnEvent):
            raise ConfigurationError("SimpleMem native provider only accepts TurnEvent")
        system = self._system_for_isolation_key(unit.isolation_key)
        self._write_conversation_marker(unit)
        timestamp = parse_simplemem_timestamp(unit.timestamp)
        speaker = unit.speaker_name or unit.role
        system.add_dialogue(
            speaker=speaker,
            content=unit.content,
            timestamp=timestamp,
        )
        return IngestResult(
            unit_ref=UnitRef(isolation_key=unit.isolation_key),
            metadata={
                "method": "simplemem",
                "turn_id": unit.turn_id,
                "timestamp": timestamp,
            },
        )

    def end_conversation(self, ref: UnitRef) -> None:
        """在隔离单元结束时调用 SimpleMem `finalize()` 处理残余窗口。"""

        if ref.isolation_key in self._finalized_isolation_keys:
            return None
        system = self._systems_by_isolation_key.get(ref.isolation_key)
        if system is None:
            return None
        system.finalize()
        self._finalized_isolation_keys.add(ref.isolation_key)
        return None

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """绕开 `ask()`，直接调用 SimpleMem hybrid retriever。"""

        system = self._system_for_isolation_key(query.isolation_key)
        contexts = list(system.hybrid_retriever.retrieve(query.query_text))
        context_str = _format_simplemem_contexts(contexts)
        formatted_memory = _format_simplemem_memory(contexts)
        return RetrievalResult(
            formatted_memory=formatted_memory,
            prompt_messages=(
                PromptMessage(role="system", content=_SIMPLEMEM_ANSWER_SYSTEM_PROMPT),
                PromptMessage(
                    role="user",
                    content=_build_simplemem_answer_prompt(
                        query=query.query_text,
                        context_str=context_str,
                    ),
                ),
            ),
            items=tuple(
                _retrieved_item_from_context(index, context)
                for index, context in enumerate(contexts, 1)
            ),
            metadata={
                "method": "simplemem",
                "prompt_track": "native",
                "prompt_source": SIMPLEMEM_ANSWER_PROMPT_SOURCE,
                "retrieval_path": "hybrid_retriever.retrieve",
            },
        )

    def _system_for_isolation_key(self, isolation_key: str) -> Any:
        """返回 isolation 专属 SimpleMemSystem，必要时创建状态目录。"""

        system = self._systems_by_isolation_key.get(isolation_key)
        if system is not None:
            return system
        state_dir = self.storage_root / _state_dir_name(isolation_key)
        state_dir.mkdir(parents=True, exist_ok=True)
        if self._system_factory is not None:
            system = self._system_factory(isolation_key, state_dir)
        else:
            system = self._create_official_system(isolation_key, state_dir)
        self._install_llm_usage_observation(system)
        self._systems_by_isolation_key[isolation_key] = system
        self._state_dirs_by_isolation_key[isolation_key] = state_dir
        return system

    def _create_official_system(self, isolation_key: str, state_dir: Path) -> Any:
        """按 approved text backend 口径构造官方 SimpleMemSystem。"""

        if self._openai_settings is None:
            raise ConfigurationError(
                "SimpleMem production system requires OpenAI settings: "
                f"{isolation_key}"
            )
        simplemem_root = self.path_settings.resolve_third_party_method_path(
            SIMPLEMEM_METHOD_DIRECTORY
        )
        if str(simplemem_root) not in sys.path:
            sys.path.insert(0, str(simplemem_root))
        try:
            from main import SimpleMemSystem
            from simplemem.core.settings import settings as simplemem_settings
        except Exception as exc:
            raise ConfigurationError(
                f"SimpleMem source package cannot be imported: {simplemem_root}"
            ) from exc

        db_path = state_dir / "lancedb"
        table_name = "memories"
        simplemem_settings.OPENAI_API_KEY = self._openai_settings.api_key
        simplemem_settings.OPENAI_BASE_URL = self._openai_settings.base_url
        simplemem_settings.LLM_MODEL = self.config.llm_model
        simplemem_settings.EMBEDDING_MODEL = self.config.embedding_model_path
        simplemem_settings.EMBEDDING_DIMENSION = self.config.embedding_dimension
        simplemem_settings.LANCEDB_PATH = str(db_path)
        simplemem_settings.MEMORY_TABLE_NAME = table_name
        simplemem_settings.ENABLE_PLANNING = self.config.enable_planning
        simplemem_settings.ENABLE_REFLECTION = self.config.enable_reflection
        simplemem_settings.MAX_REFLECTION_ROUNDS = self.config.max_reflection_rounds
        simplemem_settings.ENABLE_PARALLEL_PROCESSING = (
            self.config.enable_parallel_processing
        )
        simplemem_settings.MAX_PARALLEL_WORKERS = self.config.max_workers
        simplemem_settings.ENABLE_PARALLEL_RETRIEVAL = (
            self.config.enable_parallel_retrieval
        )
        simplemem_settings.MAX_RETRIEVAL_WORKERS = self.config.max_workers
        simplemem_settings.SEMANTIC_TOP_K = self.config.semantic_top_k
        simplemem_settings.KEYWORD_TOP_K = self.config.keyword_top_k
        simplemem_settings.STRUCTURED_TOP_K = self.config.structured_top_k
        simplemem_settings.WINDOW_SIZE = self.config.window_size
        simplemem_settings.OVERLAP_SIZE = self.config.overlap_size
        return SimpleMemSystem(
            api_key=self._openai_settings.api_key,
            model=self.config.llm_model,
            base_url=self._openai_settings.base_url,
            db_path=str(db_path),
            table_name=table_name,
            clear_db=False,
            enable_planning=self.config.enable_planning,
            enable_reflection=self.config.enable_reflection,
            max_reflection_rounds=self.config.max_reflection_rounds,
            enable_parallel_processing=self.config.enable_parallel_processing,
            max_parallel_workers=self.config.max_workers,
            enable_parallel_retrieval=self.config.enable_parallel_retrieval,
            max_retrieval_workers=self.config.max_workers,
        )

    def _write_conversation_marker(self, unit: TurnEvent) -> None:
        """在状态目录写入公开 conversation id，供 failed_ingest clean retry 定位。"""

        conversation_id = unit.metadata.get("conversation_id")
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            return
        state_dir = self._state_dirs_by_isolation_key.get(unit.isolation_key)
        if state_dir is None:
            return
        marker_path = state_dir / SIMPLEMEM_CONVERSATION_MARKER
        marker_path.write_text(conversation_id, encoding="utf-8")

    def _install_llm_usage_observation(self, system: Any) -> None:
        """包装 SimpleMem LLMClient.chat_completion，记录 build/retrieval LLM usage。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        llm_client = getattr(system, "llm_client", None)
        if llm_client is None or getattr(
            llm_client,
            "_memory_benchmark_efficiency_wrapped",
            False,
        ):
            return
        original_chat_completion = getattr(llm_client, "chat_completion", None)
        if original_chat_completion is None:
            return

        def _wrapped_chat_completion(*args: Any, **kwargs: Any) -> Any:
            """调用官方 chat_completion 并把 token usage 写入 collector。"""

            messages = kwargs.get("messages")
            if messages is None and args:
                messages = args[0]
            response = original_chat_completion(*args, **kwargs)
            prompt_text = _messages_to_text(messages)
            output_text = str(response or "")
            usage = resolve_token_usage(
                api_input_tokens=None,
                api_output_tokens=None,
                prompt_text=prompt_text,
                output_text=output_text,
                tokenizer=_TiktokenCounter(self.config.llm_model),
            )
            collector.record_llm_call(
                model_id=SIMPLEMEM_LLM_MODEL_ID,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                token_measurement_source=usage.source,
            )
            return response

        llm_client.chat_completion = _wrapped_chat_completion
        llm_client._memory_benchmark_efficiency_wrapped = True


def parse_simplemem_timestamp(raw_timestamp: str | None) -> str | None:
    """把 benchmark 原始时间转成 SimpleMem 可接受的 ISO 字符串。"""

    if raw_timestamp is None:
        return None
    value = raw_timestamp.strip()
    if not value:
        return None
    iso_value = _parse_iso_timestamp(value)
    if iso_value is not None:
        return iso_value
    match = _LOCOMO_TIMESTAMP_PATTERN.match(value)
    if match is None:
        return None
    month = _MONTHS.get(match.group("month").lower())
    if month is None:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        return None
    period = match.group("period").lower()
    if period == "pm" and hour != 12:
        hour += 12
    if period == "am" and hour == 12:
        hour = 0
    try:
        parsed = datetime(
            int(match.group("year")),
            month,
            int(match.group("day")),
            hour,
            minute,
        )
    except ValueError:
        return None
    return parsed.isoformat(timespec="seconds")


def _parse_iso_timestamp(value: str) -> str | None:
    """解析已有 ISO 时间；不可解析时返回 None。"""

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.isoformat(timespec="seconds")


def _state_dir_name(isolation_key: str) -> str:
    """把任意 isolation key 映射为安全、稳定的状态目录名。"""

    digest = hashlib.sha256(isolation_key.encode("utf-8")).hexdigest()[:16]
    return f"isolation_{digest}"


def clean_simplemem_conversation_state(
    storage_root: Path,
    conversation_id: str,
) -> None:
    """删除指定 conversation 对应的 SimpleMem isolation 状态目录。"""

    if not conversation_id.strip():
        raise ConfigurationError("SimpleMem clean retry conversation_id is required")
    if not storage_root.exists():
        return
    for candidate in storage_root.glob("isolation_*"):
        if not candidate.is_dir():
            continue
        marker_path = candidate / SIMPLEMEM_CONVERSATION_MARKER
        if not marker_path.is_file():
            continue
        marker = marker_path.read_text(encoding="utf-8").strip()
        if marker == conversation_id:
            shutil.rmtree(candidate)


def _format_simplemem_memory(contexts: list[Any]) -> str:
    """把命中 MemoryEntry 拼成统一 formatted_memory。"""

    lines = []
    for context in contexts:
        timestamp = _optional_context_text(context, "timestamp") or "unknown"
        lines.append(
            f"[{timestamp}] {_required_context_text(context, 'lossless_restatement')}"
        )
    if not lines:
        return "No relevant information found"
    return "\n".join(lines)


def _format_simplemem_contexts(contexts: list[Any]) -> str:
    """复刻官方 `AnswerGenerator._format_contexts()`，见 answer_generator.py:85-111。"""

    formatted = []
    for index, entry in enumerate(contexts, 1):
        parts = [f"[Context {index}]"]
        parts.append(f"Content: {_required_context_text(entry, 'lossless_restatement')}")
        timestamp = _optional_context_text(entry, "timestamp")
        if timestamp:
            parts.append(f"Time: {timestamp}")
        location = _optional_context_text(entry, "location")
        if location:
            parts.append(f"Location: {location}")
        persons = _optional_context_list(entry, "persons")
        if persons:
            parts.append(f"Persons: {', '.join(persons)}")
        entities = _optional_context_list(entry, "entities")
        if entities:
            parts.append(f"Related Entities: {', '.join(entities)}")
        topic = _optional_context_text(entry, "topic")
        if topic:
            parts.append(f"Topic: {topic}")
        formatted.append("\n".join(parts))
    if not formatted:
        return "No relevant information found"
    return "\n\n".join(formatted)


def _build_simplemem_answer_prompt(*, query: str, context_str: str) -> str:
    """复刻官方 `_build_answer_prompt()`，见 answer_generator.py:117-153。"""

    return f"""
Answer the user's question based on the provided context.

User Question: {query}

Relevant Context:
{context_str}

Requirements:
1. First, think through the reasoning process
2. Then provide a very CONCISE answer (short phrase about core information)
3. Answer must be based ONLY on the provided context
4. All dates in the response must be formatted as 'DD Month YYYY' but you can output more or less details if needed
5. Return your response in JSON format

Output Format:
```json
{{
  "reasoning": "Brief explanation of your thought process",
  "answer": "Concise answer in a short phrase"
}}
```

Example:
Question: "When will they meet?"
Context: "Alice suggested meeting Bob at 2025-11-16T14:00:00..."

Output:
```json
{{
  "reasoning": "The context explicitly states the meeting time as 2025-11-16T14:00:00",
  "answer": "16 November 2025 at 2:00 PM"
}}
```

Now answer the question. Return ONLY the JSON, no other text.
"""


def _retrieved_item_from_context(index: int, context: Any) -> RetrievedItem:
    """把 SimpleMem MemoryEntry 转成协议 v3 RetrievedItem。"""

    return RetrievedItem(
        item_id=_optional_context_text(context, "entry_id") or f"simplemem-{index}",
        content=_required_context_text(context, "lossless_restatement"),
        score=None,
        timestamp=_optional_context_text(context, "timestamp"),
        source_turn_ids=(),
        metadata={
            "keywords": _optional_context_list(context, "keywords"),
            "location": _optional_context_text(context, "location"),
            "persons": _optional_context_list(context, "persons"),
            "entities": _optional_context_list(context, "entities"),
            "topic": _optional_context_text(context, "topic"),
        },
    )


def _required_context_text(context: Any, field_name: str) -> str:
    """读取 MemoryEntry 必填文本字段。"""

    value = _optional_context_text(context, field_name)
    if value is None:
        raise ConfigurationError(f"SimpleMem retrieved entry missing {field_name}")
    return value


def _optional_context_text(context: Any, field_name: str) -> str | None:
    """读取 MemoryEntry 可选文本字段。"""

    value = getattr(context, field_name, None)
    if value is None:
        return None
    text = str(value)
    if not text.strip():
        return None
    return text


def _optional_context_list(context: Any, field_name: str) -> list[str]:
    """读取 MemoryEntry 可选字符串列表字段。"""

    value = getattr(context, field_name, None)
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(item) for item in value if str(item).strip()]


def _messages_to_text(messages: Any) -> str:
    """把 SimpleMem LLMClient messages 归一化为 token 估算文本。"""

    if messages is None:
        return ""
    if isinstance(messages, str):
        return messages
    if isinstance(messages, list):
        parts = []
        for message in messages:
            if isinstance(message, dict):
                role = str(message.get("role") or "")
                content = str(message.get("content") or "")
                parts.append(f"[{role}]\n{content}")
            else:
                parts.append(str(message))
        return "\n\n".join(parts)
    return str(messages)


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
                    "tiktoken is required for SimpleMem token estimation"
                ) from exc
            try:
                self._encoding = tiktoken.encoding_for_model(self.model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return len(self._encoding.encode(text or ""))


def build_simplemem_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 SimpleMem text 核心源码与 wrapper 的稳定身份。"""

    settings = path_settings or load_path_settings()
    simplemem_root = settings.resolve_third_party_method_path(
        SIMPLEMEM_METHOD_DIRECTORY
    )
    required_files = [
        "README.md",
        "setup.py",
        "main.py",
        "simplemem/core/memory_builder.py",
        "simplemem/core/hybrid_retriever.py",
        "simplemem/core/answer_generator.py",
        "simplemem/core/settings.py",
        "simplemem/core/utils/llm_client.py",
        "simplemem/core/utils/embedding.py",
        "simplemem/core/database/vector_store.py",
        "simplemem/core/models/memory_entry.py",
    ]
    source_files = [simplemem_root / relative_path for relative_path in required_files]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise ConfigurationError(f"SimpleMem source files missing: {missing_text}")

    vendored_source_sha256, relative_paths = _hash_relative_source_files(
        root=simplemem_root,
        source_files=source_files,
    )
    wrapper_path = settings.project_root / SIMPLEMEM_WRAPPER_LOGICAL_PATH
    if not wrapper_path.is_file():
        raise ConfigurationError(f"SimpleMem wrapper file missing: {wrapper_path}")
    return _build_simplemem_source_identity_from_components(
        vendored_files=relative_paths,
        vendored_source_sha256=vendored_source_sha256,
        wrapper_logical_path=SIMPLEMEM_WRAPPER_LOGICAL_PATH,
        wrapper_bytes=wrapper_path.read_bytes(),
    )


def _build_simplemem_source_identity_from_components(
    *,
    vendored_files: list[str],
    vendored_source_sha256: str,
    wrapper_logical_path: str,
    wrapper_bytes: bytes,
) -> dict[str, Any]:
    """组合官方源码与 wrapper bytes，生成公开 source identity。"""

    if Path(wrapper_logical_path).is_absolute():
        raise ConfigurationError(
            "SimpleMem wrapper_logical_path must be a stable logical path"
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
        "source_mode": SIMPLEMEM_SOURCE_MODE,
    }


def _hash_relative_source_files(
    *,
    root: Path,
    source_files: list[Path],
) -> tuple[str, list[str]]:
    """按相对路径与内容计算源码集合 SHA-256。"""

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


def _resolve_project_relative_path(value: str, project_root: Path) -> Path | None:
    """把 `models/...` 这类配置解析成项目内路径。"""

    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0] in {"models", "third_party"}:
        return project_root / candidate
    return None


__all__ = [
    "SIMPLEMEM_ADAPTER_VERSION",
    "SIMPLEMEM_OFFICIAL_PROFILE_NAME",
    "SimpleMem",
    "SimpleMemConfig",
    "build_simplemem_source_identity",
    "clean_simplemem_conversation_state",
    "parse_simplemem_timestamp",
]

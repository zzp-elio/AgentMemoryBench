"""LightMem 的 conversation-QA 适配器。

本模块包装 `third_party/methods/LightMem/` 中的官方 LightMemory。Adapter 负责配置、
conversation 隔离、状态路径和统一接口；不重写 LightMem 的核心记忆算法。
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import importlib
import io
from pathlib import Path
import re
import sys
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
    Session,
)
from memory_benchmark.core.interfaces import BaseMemorySystem
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
)


LIGHTMEM_METHOD_DIRECTORY = "LightMem"
LIGHTMEM_ADAPTER_VERSION = "conversation-qa-v1"
LIGHTMEM_READER_PROMPT_VERSION = "lightmem-reader-v1"
LIGHTMEM_MODEL_DOWNLOADS = {
    "embedding_model_path": "sentence-transformers/all-MiniLM-L6-v2",
    "llmlingua_model_path": (
        "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
    ),
}


@dataclass(frozen=True)
class LightMemConfig:
    """LightMem 运行 profile。

    字段:
        llm_model: LightMem memory manager 和 reader 使用的 LLM。
        embedding_model_path: 本地 embedding 模型路径或名称。
        llmlingua_model_path: 本地 LLMLingua 压缩模型路径或名称。
        retrieve_limit: method 内部检索条数，不进入统一接口参数。
        max_workers: runner 可读取的建议 conversation 并发数。
        pre_compress: 是否启用官方预压缩。
        topic_segment: 是否启用官方 topic segmentation。
        text_summary: 是否启用文本摘要。
        suppress_official_stdout: 是否压制第三方 stdout。
        profile_name: 可审计 profile 名称。
    """

    llm_model: str
    embedding_model_path: str
    llmlingua_model_path: str
    retrieve_limit: int
    max_workers: int
    pre_compress: bool = True
    topic_segment: bool = True
    text_summary: bool = True
    embedding_dimensions: int = 384
    embedding_device: str = "cpu"
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
        if self.max_workers < 1:
            raise ConfigurationError("LightMem max_workers must be positive")
        if self.embedding_dimensions < 1:
            raise ConfigurationError("LightMem embedding_dimensions must be positive")
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
    inserted = False
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
        inserted = True
    try:
        module = importlib.import_module("lightmem.memory.lightmem")
        return {"LightMemory": module.LightMemory}
    finally:
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(root_text)


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


class LightMem(BaseMemorySystem):
    """使用官方 LightMemory 的统一 memory system。"""

    def __init__(
        self,
        config: LightMemConfig,
        backend_factory: Callable[[str], Any] | None = None,
        answer_client: Any | None = None,
        openai_settings: OpenAISettings | None = None,
        storage_root: str | Path | None = None,
        path_settings: PathSettings | None = None,
        efficiency_collector: EfficiencyCollector | None = None,
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
                    },
                    "compress_config": {
                        "instruction": "",
                        "rate": 0.6,
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
            "extract_threshold": 0.1,
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
        }

    def add(self, conversations: list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。"""

        conversation_ids: list[str] = []
        for conversation in conversations:
            backend = self._get_or_create_backend(conversation.conversation_id)
            messages = self._conversation_to_lightmem_messages(conversation)
            self._suppress_stdout_if_needed(
                backend.add_memory,
                messages,
                force_segment=True,
                force_extract=True,
            )
            conversation_ids.append(conversation.conversation_id)
        return AddResult(conversation_ids=conversation_ids)

    def get_answer(self, question: Question) -> AnswerResult:
        """基于 LightMem 检索上下文回答公开问题。"""

        if question.conversation_id not in self._backends:
            raise ConfigurationError(
                f"LightMem conversation has not been added: {question.conversation_id}"
            )
        backend = self._backends[question.conversation_id]
        collector = self._efficiency_collector
        retrieval_started_ns = perf_counter_ns()
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                memories = backend.retrieve(
                    question.text,
                    limit=self.config.retrieve_limit,
                    filters=None,
                )
        else:
            memories = backend.retrieve(
                question.text,
                limit=self.config.retrieve_limit,
                filters=None,
            )
        memory_context = "\n".join(str(memory) for memory in memories)
        if collector is not None and collector.enabled:
            collector.record_retrieval_result(
                latency_ms=_elapsed_ms(retrieval_started_ns),
                injected_memory_context_tokens=_count_openai_tokens(
                    memory_context,
                    self.config.llm_model,
                ),
            )
        prompt = self._build_answer_prompt(question, memory_context)
        answer_started_ns = perf_counter_ns()
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
                self._backends[conversation_id] = self._create_official_backend(
                    conversation_id
                )
            else:
                self._backends[conversation_id] = self._backend_factory(conversation_id)
        return self._backends[conversation_id]

    def _create_official_backend(self, conversation_id: str) -> Any:
        """构造当前 conversation 独占的官方 LightMemory backend。"""

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
        return self._suppress_stdout_if_needed(lightmemory_cls.from_config, backend_config)

    def _conversation_to_lightmem_messages(
        self,
        conversation: Conversation,
    ) -> list[dict[str, object]]:
        """把统一 conversation 转换为官方 LightMem message 列表。"""

        messages: list[dict[str, object]] = []
        for session in conversation.sessions:
            messages.extend(self._session_to_lightmem_messages(session))
        return messages

    def _session_to_lightmem_messages(self, session: Session) -> list[dict[str, object]]:
        """把单个 session 转换为 LightMem message 列表。"""

        messages: list[dict[str, object]] = []
        for turn in session.turns:
            timestamp = turn.turn_time or session.session_time
            messages.append(
                {
                    "role": "user",
                    "content": turn.content,
                    "speaker_id": turn.speaker,
                    "speaker_name": turn.speaker,
                    "time_stamp": timestamp,
                }
            )
        return messages

    def _build_answer_prompt(self, question: Question, memory_context: str) -> str:
        """构造不含 gold answer 的固定 reader prompt。"""

        return (
            "Based on the retrieved memories below, answer the question with a short "
            "phrase whenever possible.\n\n"
            f"Memories:\n{memory_context}\n\n"
            f"Question: {question.text}\nShort answer:"
        )

    def _call_answer_client(self, prompt: str, question: Question) -> str:
        """调用测试或生产 reader。"""

        if self._answer_client is None:
            raise ConfigurationError(
                f"LightMem answer client is not available for {question.conversation_id}"
            )
        return self._suppress_stdout_if_needed(
            self._answer_client.create_answer,
            prompt,
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


class _OpenAIAnswerClient:
    """LightMem 固定 reader 的 OpenAI-compatible client wrapper。"""

    def __init__(self, client: Any, model: str) -> None:
        """保存 chat completion client 和 reader 模型名。"""

        self._client = client
        self._model = model

    def create_answer(self, prompt: str) -> str:
        """调用 chat completion 并返回文本答案。"""

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
        )
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

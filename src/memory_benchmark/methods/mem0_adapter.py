"""Mem0 OSS 的 conversation-QA 适配器。

本模块直接调用 `third_party/methods/mem0-main/` 中的官方 Mem0 `Memory` 算法，
不修改第三方源码。它负责官方 benchmark 参数、逐 turn 写入、conversation namespace
隔离、记忆检索和固定 reader 回答；runner 只依赖统一 `BaseMemorySystem` 接口。
"""

from __future__ import annotations

import hashlib
import importlib
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
from memory_benchmark.core import AddResult, AnswerResult, Conversation, Question, Turn
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseResumableMemorySystem
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
    resolve_token_usage,
)


MEM0_METHOD_DIRECTORY = "mem0-main"
MEM0_ADAPTER_VERSION = "conversation-qa-v1"
MEM0_READER_PROMPT_VERSION = "mem0-reader-v1"
VALID_MESSAGE_ROLES = {"user", "assistant"}


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

    @classmethod
    def smoke(cls) -> "Mem0Config":
        """返回低成本真实链路 smoke profile。

        smoke 只降低检索深度和 conversation 并发；extraction、embedding、逐 turn add
        和 `infer=True` 均保持官方 benchmark 语义。
        """

        return cls(
            extraction_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
            embedding_dimensions=1536,
            reader_model="gpt-4o-mini",
            top_k=10,
            max_workers=1,
            ingestion_chunk_size=1,
            infer=True,
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


class Mem0(BaseResumableMemorySystem):
    """使用官方 Mem0 OSS `Memory` 算法的统一 memory system。"""

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
        if any(not conversation_id.strip() for conversation_id in self._added_conversation_ids):
            raise ConfigurationError(
                "Mem0 existing_conversation_ids cannot contain empty ids"
            )
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

    def add(self, conversations: list[Conversation]) -> AddResult:
        """按原始顺序逐 turn 写入一个或多个 conversation。

        输入:
            conversations: runner 已清洗的公开 conversation 列表。

        输出:
            AddResult: 成功写入的 conversation ids 和公开统计信息。
        """

        if not conversations:
            raise ConfigurationError("Mem0.add() requires at least one conversation")

        conversation_ids: list[str] = []
        turn_count = 0
        for conversation in conversations:
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

        speaker_roles = self._build_speaker_roles(conversation)
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

    def get_answer(self, question: Question) -> AnswerResult:
        """在 question 所属 conversation namespace 内检索并生成回答。

        输入:
            question: 不含 gold/evidence 的公开问题。

        输出:
            AnswerResult: reader 生成的非空答案和不含原始记忆的公开诊断信息。
        """

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
        if collector is not None and collector.enabled:
            collector.record_retrieval_result(
                latency_ms=_elapsed_ms(retrieval_started_ns),
                injected_memory_context_tokens=(
                    self._count_tokens(injected_memory_text, self.config.reader_model)
                    if injected_memory_text
                    else 0
                ),
            )

        reader_messages = self._reader_messages(question, memories)
        answer_started_ns = perf_counter_ns()
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
                "retrieved_memory_count": len(memories),
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
    def _reader_messages(
        question: Question,
        memories: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """构造固定 reader 的 system/user messages。"""

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


__all__ = [
    "Mem0",
    "Mem0Config",
    "build_mem0_source_identity",
]

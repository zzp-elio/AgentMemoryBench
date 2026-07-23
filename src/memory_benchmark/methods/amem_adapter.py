"""A-Mem 官方通用产品接口的 provider v3 适配器。

本模块包装 ``third_party/methods/A-mem-product/agentic_memory`` 的
``AgenticMemorySystem``。
Adapter 只负责 benchmark 输入映射、conversation 隔离、持久化、观测与公开
provenance sidecar；note 构建、链接、evolution 与检索顺序仍由产品实现决定。
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
from dataclasses import asdict, dataclass
import hashlib
import importlib
import io
import json
import pickle
import shutil
from pathlib import Path
import sys
from threading import Lock
from time import perf_counter_ns
from types import MethodType
from typing import Any

from memory_benchmark.config.settings import PathSettings, load_path_settings
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Question,
    AnswerPromptResult,
    ImageRef,
    PromptMessage,
    Turn,
)
from memory_benchmark.core.interfaces import BaseMemoryProvider, BaseMemorySystem
from memory_benchmark.core.provider_protocol import (
    ConsumeGranularity,
    EvidenceAssertion,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalEvidence,
    RetrievalResult,
    RetrievedItem,
    SessionMemoryReport,
    SessionRef,
    TurnEvent,
    UnitRef,
)
from memory_benchmark.methods.image_text import turn_text_with_images
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
    extract_api_token_usage,
    resolve_token_usage,
)
from memory_benchmark.storage import atomic_write_json


AMEM_PRODUCT_DIRECTORY = "A-mem-product"
AMEM_ADAPTER_VERSION = "conversation-qa-v2-product"
AMEM_READER_PROMPT_VERSION = "amem-reader-v1"
AMEM_LONGMEMEVAL_READER_PROMPT_VERSION = "lightmem_longmemeval_reader_v1"
AMEM_QUERY_KEYWORD_PROMPT_VERSION = "amem-query-keywords-v1"
AMEM_ANSWER_SYSTEM_MESSAGE = (
    "Follow the format specified in the prompt exactly. Do not add extra commentary."
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
AMEM_STATE_SCHEMA_VERSION = 2
AMEM_MEMORIES_FILENAME = "memories.pkl"
AMEM_LINEAGE_FILENAME = "note_lineage.json"
AMEM_STATE_MANIFEST_FILENAME = "state_manifest.json"
AMEM_SOURCE_MODE = "official-general-product-plus-wrapper"
AMEM_EMBEDDING_MODEL_ID = "amem-embedding"
_AMEM_RUNTIME_CONSTRUCTION_LOCK = Lock()
# A-Mem paper Table 8 的 GPT-4o-mini per-category 最优检索深度（cat1/2/5=40、
# cat3/4=50）。ws02.5 config 归一化（方案 B，2026-07-09）后**不再使用**——
# 统一用 profile `retrieve_k`（repo 默认 10，test_advanced_robust.py:348
# --retrieve_k default=10；底层 memory_layer_robust.py:430 签名 k=5 被覆盖
# 不生效）。paper Table 8 值留档于 method-interface-inventory.md hyperparameters
# 字段，作为"论文复现验证配置"，不作 5×5 矩阵默认。
AMEM_PAPER_TABLE8_GPT4O_MINI_K = {
    "1": 40,
    "2": 40,
    "3": 50,
    "4": 50,
    "5": 40,
}


@dataclass(frozen=True)
class AMemConfig:
    """A-Mem 运行 profile。

    字段:
        llm_model: A-Mem 写入、查询改写和 reader 使用的 LLM。
        embedding_model: A-Mem SimpleEmbeddingRetriever 使用的 SentenceTransformer 模型。
        retrieve_k: method 内部检索记忆数量，不进入统一接口参数。
        api_timeout_seconds: OpenAI-compatible 请求超时秒数。
        api_max_retries: OpenAI-compatible 请求最大重试次数。
        max_workers: runner 可读取的建议 conversation 并发数；初期保持 1。
        use_product_layer: 是否使用官方通用产品 layer；当前必须为 true。
        suppress_official_stdout: 是否压制第三方源码中的 stdout。
        profile_name: 可审计 profile 名称。
    """

    llm_model: str
    embedding_model: str
    retrieve_k: int
    max_workers: int
    api_timeout_seconds: float = 60.0
    api_max_retries: int = 8
    use_product_layer: bool = True
    suppress_official_stdout: bool = True
    profile_name: str = "custom"

    def __post_init__(self) -> None:
        """强校验会影响实验语义的配置。"""

        if not self.llm_model.strip():
            raise ConfigurationError("A-Mem llm_model is required")
        if not self.embedding_model.strip():
            raise ConfigurationError("A-Mem embedding_model is required")
        if self.retrieve_k < 1:
            raise ConfigurationError("A-Mem retrieve_k must be positive")
        if self.api_timeout_seconds <= 0:
            raise ConfigurationError("A-Mem api_timeout_seconds must be positive")
        if self.api_max_retries < 0:
            raise ConfigurationError("A-Mem api_max_retries cannot be negative")
        if self.max_workers < 1:
            raise ConfigurationError("A-Mem max_workers must be positive")
        if not self.use_product_layer:
            raise ConfigurationError(
                "A-Mem adapter requires use_product_layer=true"
            )

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 secret 和绝对存储路径的公开配置。"""

        return {
            **asdict(self),
            "adapter_version": AMEM_ADAPTER_VERSION,
            "reader_prompt_version": AMEM_READER_PROMPT_VERSION,
            "llm_provider": "openai-compatible",
            "embedding_provider": "sentence-transformers",
        }


def build_amem_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算官方 A-Mem 通用产品源码的确定性身份。

    输入:
        path_settings: 项目路径配置；为空时从当前项目根加载。

    输出:
        dict: SHA-256、文件数量和参与哈希的相对路径。
    """

    settings = path_settings or load_path_settings()
    amem_root = settings.resolve_third_party_method_path(AMEM_PRODUCT_DIRECTORY)
    if not amem_root.is_dir():
        raise ConfigurationError(f"A-Mem product source directory missing: {amem_root}")
    required_files = [
        "README.md",
        "pyproject.toml",
        "agentic_memory/__init__.py",
        "agentic_memory/memory_system.py",
        "agentic_memory/retrievers.py",
        "agentic_memory/llm_controller.py",
    ]
    source_files = [amem_root / relative_path for relative_path in required_files]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise ConfigurationError(f"A-Mem source files missing: {missing_text}")

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative_path = source_file.relative_to(amem_root).as_posix()
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
        "source_mode": AMEM_SOURCE_MODE,
    }


def import_amem_product_classes(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """从官方通用 A-Mem 源码导入产品类。

    输入:
        path_settings: 项目路径配置；为空时自动加载。

    输出:
        dict: 官方 ``AgenticMemorySystem`` 和 ``ChromaRetriever`` 类。

    说明:
        导入过程临时把 A-Mem 根目录放入 `sys.path`，避免把第三方源码安装成一等
        package，也避免污染本项目 package discovery。
    """

    settings = path_settings or load_path_settings()
    amem_root = settings.resolve_third_party_method_path(AMEM_PRODUCT_DIRECTORY)
    if not (amem_root / "agentic_memory" / "memory_system.py").is_file():
        raise ConfigurationError(f"A-Mem product layer missing: {amem_root}")

    root_text = str(amem_root)
    inserted = False
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
        inserted = True
    try:
        module = importlib.import_module("agentic_memory.memory_system")
        retriever_module = importlib.import_module("agentic_memory.retrievers")
        expected_package_root = (amem_root / "agentic_memory").resolve()
        for imported_module in (module, retriever_module):
            module_file = Path(str(getattr(imported_module, "__file__", ""))).resolve()
            if expected_package_root not in module_file.parents:
                raise ConfigurationError(
                    "A-Mem import resolved outside the official general product "
                    f"repository: {module_file}"
                )
        return {
            "AgenticMemorySystem": module.AgenticMemorySystem,
            "ChromaRetriever": retriever_module.ChromaRetriever,
            "PersistentChromaRetriever": retriever_module.PersistentChromaRetriever,
            "memory_system_module": module,
        }
    finally:
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(root_text)


class AMem(BaseMemoryProvider, BaseMemorySystem, MemoryProvider):
    """使用官方 A-Mem 通用产品 layer 的统一 memory system。"""

    consume_granularity: ConsumeGranularity = "turn"
    provenance_granularity = "turn"

    def __init__(
        self,
        config: AMemConfig,
        runtime_factory: Callable[[str], Any] | None = None,
        answer_llm: Any | None = None,
        openai_api_key: str | None = None,
        openai_base_url: str | None = None,
        storage_root: str | Path | None = None,
        path_settings: PathSettings | None = None,
        efficiency_collector: EfficiencyCollector | None = None,
        session_memory_report: bool = False,
        benchmark_name: str | None = None,
    ):
        """初始化 A-Mem adapter。

        输入:
            config: A-Mem 强类型 profile。
            runtime_factory: 测试可注入 fake；生产为空时后续任务构造官方 runtime。
            answer_llm: 测试可注入 fake；生产为空时后续任务使用官方 LLM controller。
            openai_api_key: 传给官方 OpenAI-compatible backend 的 API key。
            openai_base_url: 传给官方 OpenAI-compatible backend 的 base URL。
            storage_root: 当前 run 的 A-Mem 状态目录；为空时使用隔离的默认输出目录。
            path_settings: 项目路径配置。
            efficiency_collector: runner 管理的可选效率 observation collector。
        """

        self.config = config
        self._runtime_factory = runtime_factory
        self._answer_llm = answer_llm
        self._openai_api_key = openai_api_key
        self._openai_base_url = openai_base_url
        self.path_settings = path_settings or load_path_settings()
        self.storage_root = Path(storage_root) if storage_root is not None else (
            self.path_settings.outputs_root / "amem" / "unscoped-method-state"
        )
        self._efficiency_collector = efficiency_collector
        self.session_memory_report = session_memory_report
        self.benchmark_name = benchmark_name
        self._runtimes: dict[str, Any] = {}
        self._native_isolation_to_conversation_id: dict[str, str] = {}
        self._native_turn_counts: dict[str, int] = {}
        self._native_conversations: dict[str, Conversation] = {}
        self._note_source_turn_ids: dict[str, dict[str, str]] = {}
        self._session_note_ids: dict[tuple[str, str | None], list[str]] = {}

    def add(self, conversations: Conversation | list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。"""

        if isinstance(conversations, Conversation):
            conversations = [conversations]
        conversation_ids: list[str] = []
        for conversation in conversations:
            runtime = self._get_or_create_runtime(conversation.conversation_id)
            turn_count = 0
            lineage = self._note_source_turn_ids.setdefault(
                conversation.conversation_id, {}
            )
            for session in conversation.sessions:
                for turn in session.turns:
                    note_id = self._call_runtime_add(
                        runtime, turn, session.session_time
                    )
                    lineage[note_id] = turn.turn_id
                    turn_count += 1
            self._save_conversation_state(
                conversation=conversation,
                runtime=runtime,
                turn_count=turn_count,
            )
            conversation_ids.append(conversation.conversation_id)
        return AddResult(conversation_ids=conversation_ids)

    def load_existing_conversation_state(self, conversation: Conversation) -> None:
        """从 wrapper 状态目录恢复一个已完成写入的 conversation。

        输入:
            conversation: runner 已确认 `conversation_status=completed` 的公开对象。

        输出:
            None；恢复后的官方 runtime 会注册到 `self._runtimes`。

        异常:
            ConfigurationError: 状态文件缺失、manifest 不匹配或 checksum 不一致。
        """

        conversation_id = conversation.conversation_id
        if conversation_id in self._runtimes:
            return
        state_dir = self._conversation_state_dir(conversation_id)
        manifest = self._load_and_validate_state_manifest(
            conversation=conversation,
            state_dir=state_dir,
        )
        runtime = self._get_or_create_runtime(conversation_id)
        memories_path = state_dir / AMEM_MEMORIES_FILENAME
        with memories_path.open("rb") as memories_file:
            runtime.memories = pickle.load(memories_file)
        lineage = json.loads(
            (state_dir / AMEM_LINEAGE_FILENAME).read_text(encoding="utf-8")
        )
        if not isinstance(lineage, dict) or not all(
            isinstance(note_id, str) and isinstance(turn_id, str)
            for note_id, turn_id in lineage.items()
        ):
            raise ConfigurationError(
                f"A-Mem note lineage is invalid: {conversation_id}"
            )
        self._note_source_turn_ids[conversation_id] = dict(lineage)
        self._rebuild_product_retriever(runtime, conversation_id)
        self._runtimes[conversation_id] = runtime
        current_turn_count = sum(
            len(session.turns) for session in conversation.sessions
        )
        if int(manifest.get("turn_count", -1)) != current_turn_count:
            raise ConfigurationError(
                f"A-Mem state turn_count mismatch for {conversation_id}"
            )

    def ingest(self, unit: IngestUnit) -> IngestResult:
        """按 v3 协议写入一个 turn 单元。"""

        if not isinstance(unit, TurnEvent):
            raise ConfigurationError("A-Mem native provider only accepts TurnEvent")
        conversation_id = self._conversation_id_from_event(unit)
        self._native_isolation_to_conversation_id[unit.isolation_key] = conversation_id
        runtime = self._get_or_create_runtime(conversation_id)
        note_id = self._call_runtime_add(
            runtime,
            self._turn_from_event(unit),
            self._session_time_from_event(unit),
        )
        self._note_source_turn_ids.setdefault(conversation_id, {})[note_id] = unit.turn_id
        self._session_note_ids.setdefault(
            (unit.isolation_key, unit.session_id), []
        ).append(note_id)
        self._native_turn_counts[conversation_id] = (
            self._native_turn_counts.get(conversation_id, 0) + 1
        )
        self._native_conversations[conversation_id] = Conversation(
            conversation_id=conversation_id,
            sessions=[],
            metadata=self._native_public_metadata(unit),
        )
        return IngestResult(unit_ref=UnitRef(unit.isolation_key))

    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None:
        """在 HaluMem session 边界报告该 session 新建的官方 MemoryNote。"""

        if not self.session_memory_report:
            return None
        conversation_id = self._native_isolation_to_conversation_id.get(
            ref.isolation_key,
            ref.isolation_key,
        )
        runtime = self._runtimes.get(conversation_id)
        if runtime is None:
            return SessionMemoryReport(session_ref=ref, memories=[])
        note_ids = self._session_note_ids.pop(
            (ref.isolation_key, ref.session_id), []
        )
        memories = [
            _format_amem_memory_note(runtime.memories[note_id])
            for note_id in note_ids
            if note_id in runtime.memories
        ]
        return SessionMemoryReport(
            session_ref=ref,
            memories=memories,
            metadata={"memory_unit": "official_product_note", "note_count": len(memories)},
        )

    def end_conversation(self, ref: UnitRef) -> None:
        """在 conversation 边界持久化 A-Mem runtime 状态。"""

        conversation_id = self._native_isolation_to_conversation_id.get(
            ref.isolation_key,
            ref.isolation_key,
        )
        runtime = self._runtimes.get(conversation_id)
        if runtime is None:
            return
        conversation = self._native_conversations.get(
            conversation_id,
            Conversation(conversation_id=conversation_id),
        )
        self._save_conversation_state(
            conversation=conversation,
            runtime=runtime,
            turn_count=self._native_turn_counts.get(conversation_id, 0),
        )

    @staticmethod
    def _turn_from_event(event: TurnEvent) -> Turn:
        """从规范 TurnEvent 恢复旧 adapter helper 需要的 Turn。"""

        return Turn(
            turn_id=event.turn_id,
            speaker=event.speaker_name or event.role,
            content=AMem._original_content_from_event(event),
            normalized_role=event.role if event.role in {"user", "assistant"} else None,
            turn_time=AMem._optional_event_text(event, "original_turn_time"),
            images=AMem._images_from_event(event),
            metadata=dict(event.metadata.get("turn_metadata") or {}),
        )

    @staticmethod
    def _native_public_metadata(event: TurnEvent) -> dict[str, Any]:
        """恢复 v3 事件中携带的 conversation 级公开 metadata。"""

        metadata = dict(event.metadata.get("conversation_metadata") or {})
        metadata["conversation_id"] = AMem._conversation_id_from_event(event)
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

        return AMem._optional_event_text(event, "original_session_time") or event.timestamp

    @staticmethod
    def _original_content_from_event(event: TurnEvent) -> str:
        """读取事件前原始 turn 文本。"""

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

    def retrieve(self, question: Question | RetrievalQuery) -> AnswerPromptResult | RetrievalResult:
        """执行 A-Mem 官方 query keyword generation 和 memory retrieval。"""

        if isinstance(question, RetrievalQuery):
            return self._retrieve_native(question)

        if question.conversation_id not in self._runtimes:
            raise ConfigurationError(
                f"A-Mem conversation has not been added: {question.conversation_id}"
            )
        if self._is_adversarial_category(question):
            raise ConfigurationError(
                "A-Mem official adversarial prompt requires gold answer in the "
                "method input, which is forbidden by this framework; category 5 "
                "is therefore unsupported for A-Mem official-mini profile."
            )
        runtime = self._runtimes[question.conversation_id]
        retrieve_k = self._retrieve_k_for_question(question)
        collector = self._efficiency_collector
        retrieval_started_ns = perf_counter_ns()
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                query_keywords = self._generate_query_keywords(
                    question=question,
                    runtime=runtime,
                )
                context = runtime.find_related_memories_raw(
                    query_keywords,
                    k=retrieve_k,
                )
        else:
            query_keywords = self._generate_query_keywords(
                question=question,
                runtime=runtime,
            )
            context = runtime.find_related_memories_raw(
                query_keywords,
                k=retrieve_k,
            )
        retrieval_latency_ms = _elapsed_ms(retrieval_started_ns)
        memory_context = str(context)
        answer_prompt = self._build_answer_prompt(
            question=question,
            memory_context=memory_context,
        )
        prompt_messages = self._build_prompt_messages(
            question=question,
            answer_prompt=answer_prompt,
        )
        if collector is not None and collector.enabled:
            collector.record_retrieval_result_if_question_scope(
                latency_ms=retrieval_latency_ms,
                injected_memory_context_tokens=_count_openai_tokens(
                    memory_context,
                    self.config.llm_model,
                ),
            )

        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt=answer_prompt,
            prompt_messages=prompt_messages,
            metadata={
                "method": "amem",
                "answer_context": memory_context,
                "retrieve_k": retrieve_k,
                "query_keywords": query_keywords,
                "answer_prompt_profile": _answer_prompt_profile_for_question(question),
                "query_keyword_prompt_version": AMEM_QUERY_KEYWORD_PROMPT_VERSION,
            },
        )

    def _retrieve_native(self, query: RetrievalQuery) -> RetrievalResult:
        """直接调用通用产品 ``search_agentic`` 并保留真实名次。"""

        conversation_id = self._native_isolation_to_conversation_id.get(
            query.isolation_key,
            query.isolation_key,
        )
        runtime = self._runtimes.get(conversation_id)
        if runtime is None:
            raise ConfigurationError(
                f"A-Mem conversation has not been added: {conversation_id}"
            )
        top_k = min(query.top_k, self.config.retrieve_k)
        collector = self._efficiency_collector
        started_ns = perf_counter_ns()
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                raw_results = self._suppress_stdout_if_needed(
                    runtime.search_agentic,
                    query.query_text,
                    k=top_k,
                )
        else:
            raw_results = self._suppress_stdout_if_needed(
                runtime.search_agentic,
                query.query_text,
                k=top_k,
            )
        if not isinstance(raw_results, list):
            raise ConfigurationError("A-Mem search_agentic must return a list")
        if getattr(runtime, "memories", None) and not raw_results:
            # 产品 search_agentic() 会把任何 Chroma 异常吞成 []。对非空
            # collection，向量检索 k>0 必然至少命中一条；因此这里的空列表不是
            # 合法 zero-hit，而是必须阻断的产品检索失败。
            raise ConfigurationError(
                "A-Mem search_agentic returned no results for a non-empty memory store"
            )
        lineage = self._note_source_turn_ids.get(conversation_id, {})
        items = tuple(
            _amem_retrieved_item(raw, lineage=lineage, index=index)
            for index, raw in enumerate(raw_results, 1)
        )
        formatted_memory = _format_amem_search_results(raw_results)
        if collector is not None and collector.enabled:
            collector.record_retrieval_result_if_question_scope(
                latency_ms=_elapsed_ms(started_ns),
                injected_memory_context_tokens=_count_openai_tokens(
                    formatted_memory,
                    self.config.llm_model,
                ),
            )
        evidence = RetrievalEvidence(
            semantic_provenance=EvidenceAssertion(status="valid"),
            provenance_granularity="turn",
            stable_ranking=EvidenceAssertion(status="valid"),
        )
        return RetrievalResult(
            formatted_memory=formatted_memory,
            items=items,
            metadata={
                "method": "amem",
                "retrieval_path": "AgenticMemorySystem.search_agentic",
                "retrieve_k": top_k,
                "prompt_track": "unified",
                "provenance_granularity": "turn",
            },
            evidence=evidence,
        )

    def get_answer(self, question: Question) -> AnswerResult:
        """基于 A-Mem 检索上下文回答公开问题。"""

        retrieval = self.retrieve(question)
        runtime = self._runtimes[question.conversation_id]
        retrieve_k = int(retrieval.metadata["retrieve_k"])
        query_keywords = str(retrieval.metadata["query_keywords"])
        prompt = _user_prompt_from_prompt_messages(retrieval.prompt_messages)
        answer_started_ns = perf_counter_ns()
        collector = self._efficiency_collector
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.ANSWER):
                answer = self._call_answer_llm(
                    prompt=prompt,
                    question=question,
                    runtime=runtime,
                )
        else:
            answer = self._call_answer_llm(
                prompt=prompt,
                question=question,
                runtime=runtime,
            )
        if collector is not None and collector.enabled:
            collector.record_answer_generation(latency_ms=_elapsed_ms(answer_started_ns))
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=str(answer).strip(),
            metadata={
                "method": "amem",
                "retrieve_k": retrieve_k,
                "query_keywords": query_keywords,
                "reader_prompt_version": AMEM_READER_PROMPT_VERSION,
                "query_keyword_prompt_version": AMEM_QUERY_KEYWORD_PROMPT_VERSION,
            },
        )

    def _get_or_create_runtime(self, conversation_id: str) -> Any:
        """返回当前 conversation 的隔离 runtime。"""

        if conversation_id not in self._runtimes:
            if self._runtime_factory is None:
                runtime = self._create_official_runtime(
                    conversation_id
                )
            else:
                runtime = self._runtime_factory(conversation_id)
            self._install_memory_build_usage_observer(
                runtime=runtime,
                conversation_id=conversation_id,
            )
            self._runtimes[conversation_id] = runtime
        return self._runtimes[conversation_id]

    def _save_conversation_state(
        self,
        conversation: Conversation,
        runtime: Any,
        turn_count: int,
    ) -> None:
        """保存一个已完整写入 conversation 的 A-Mem wrapper 状态。"""

        state_dir = self._conversation_state_dir(conversation.conversation_id)
        state_dir.mkdir(parents=True, exist_ok=True)
        memories_path = state_dir / AMEM_MEMORIES_FILENAME
        _atomic_pickle_dump(memories_path, getattr(runtime, "memories", {}))
        atomic_write_json(
            state_dir / AMEM_LINEAGE_FILENAME,
            self._note_source_turn_ids.get(conversation.conversation_id, {}),
        )
        manifest = self._build_state_manifest(
            conversation=conversation,
            state_dir=state_dir,
            turn_count=turn_count,
        )
        atomic_write_json(state_dir / AMEM_STATE_MANIFEST_FILENAME, manifest)

    def _build_state_manifest(
        self,
        conversation: Conversation,
        state_dir: Path,
        turn_count: int,
    ) -> dict[str, Any]:
        """构造 A-Mem conversation 状态 manifest。"""

        files = {
            AMEM_MEMORIES_FILENAME: _sha256_file(state_dir / AMEM_MEMORIES_FILENAME),
            AMEM_LINEAGE_FILENAME: _sha256_file(state_dir / AMEM_LINEAGE_FILENAME),
        }
        source_identity = build_amem_source_identity(self.path_settings)
        return {
            "schema_version": AMEM_STATE_SCHEMA_VERSION,
            "conversation_id": conversation.conversation_id,
            "adapter_version": AMEM_ADAPTER_VERSION,
            "source_sha256": source_identity["source_sha256"],
            "profile": self.config.to_manifest(),
            "turn_count": turn_count,
            "files": files,
        }

    def _load_and_validate_state_manifest(
        self,
        conversation: Conversation,
        state_dir: Path,
    ) -> dict[str, Any]:
        """读取并强校验 A-Mem conversation 状态 manifest。"""

        manifest_path = state_dir / AMEM_STATE_MANIFEST_FILENAME
        if not manifest_path.is_file():
            raise ConfigurationError(
                f"A-Mem state manifest missing: {manifest_path}"
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != AMEM_STATE_SCHEMA_VERSION:
            raise ConfigurationError(
                f"A-Mem state schema mismatch for {conversation.conversation_id}"
            )
        if manifest.get("conversation_id") != conversation.conversation_id:
            raise ConfigurationError(
                f"A-Mem state conversation_id mismatch for {conversation.conversation_id}"
            )
        if manifest.get("adapter_version") != AMEM_ADAPTER_VERSION:
            raise ConfigurationError(
                f"A-Mem state adapter_version mismatch for {conversation.conversation_id}"
            )
        expected_source = build_amem_source_identity(self.path_settings)["source_sha256"]
        if manifest.get("source_sha256") != expected_source:
            raise ConfigurationError(
                f"A-Mem state source identity mismatch for {conversation.conversation_id}"
            )
        if manifest.get("profile") != self.config.to_manifest():
            raise ConfigurationError(
                f"A-Mem state profile mismatch for {conversation.conversation_id}"
            )
        files = manifest.get("files")
        if not isinstance(files, dict):
            raise ConfigurationError(
                f"A-Mem state files manifest invalid for {conversation.conversation_id}"
            )
        for filename in (
            AMEM_MEMORIES_FILENAME,
            AMEM_LINEAGE_FILENAME,
        ):
            file_path = state_dir / filename
            if not file_path.is_file():
                raise ConfigurationError(f"A-Mem state file missing: {file_path}")
            expected_sha = files.get(filename)
            if expected_sha != _sha256_file(file_path):
                raise ConfigurationError(
                    f"A-Mem state checksum mismatch for {file_path}"
                )
        return manifest

    def _conversation_state_dir(self, conversation_id: str) -> Path:
        """返回单个 conversation 的状态目录。"""

        return self.storage_root / _safe_path_name(conversation_id)

    def _rebuild_product_retriever(self, runtime: Any, conversation_id: str) -> None:
        """从已验证 MemoryNote 重建产品 Chroma 索引，不重跑 LLM。"""

        retriever = getattr(runtime, "retriever", None)
        add_document = getattr(retriever, "add_document", None)
        if not callable(add_document):
            raise ConfigurationError(
                f"A-Mem product retriever cannot rebuild state: {conversation_id}"
            )
        for note_id, note in getattr(runtime, "memories", {}).items():
            self._suppress_stdout_if_needed(
                add_document,
                str(note.content),
                _amem_memory_metadata(note),
                str(note_id),
            )

    def _create_official_runtime(self, conversation_id: str) -> Any:
        """构造官方 A-Mem 通用产品 runtime。

        输入:
            conversation_id: 当前 conversation id，只用于错误信息和后续扩展。

        输出:
            Any: 官方 ``AgenticMemorySystem`` 实例。
        """

        if not self._openai_api_key:
            raise ConfigurationError(
                f"A-Mem production runtime requires OpenAI API key for {conversation_id}"
            )
        classes = import_amem_product_classes(self.path_settings)
        runtime_cls = classes["AgenticMemorySystem"]
        persistent_retriever_cls = classes["PersistentChromaRetriever"]
        runtime_module = classes["memory_system_module"]
        chroma_directory = self._conversation_state_dir(conversation_id) / "chromadb"

        class _ConversationPersistentRetriever(persistent_retriever_cls):
            """把官方 Chroma retriever 限定到当前 conversation 目录。"""

            def __init__(
                self,
                collection_name: str = "memories",
                model_name: str = "all-MiniLM-L6-v2",
            ) -> None:
                """保留官方签名，仅改为独立 persistent client。"""

                import chromadb
                from chromadb.config import Settings as ChromaSettings
                from chromadb.utils.embedding_functions import (
                    SentenceTransformerEmbeddingFunction,
                )

                chroma_directory.mkdir(parents=True, exist_ok=True)
                self.client = chromadb.PersistentClient(
                    path=str(chroma_directory),
                    settings=ChromaSettings(allow_reset=True),
                )
                self.embedding_function = SentenceTransformerEmbeddingFunction(
                    model_name=model_name
                )
                existing_names = {
                    collection.name for collection in self.client.list_collections()
                }
                if collection_name in existing_names:
                    self.collection = self.client.get_collection(
                        name=collection_name,
                        embedding_function=self.embedding_function,
                    )
                else:
                    self.collection = self.client.get_or_create_collection(
                        name=collection_name,
                        embedding_function=self.embedding_function,
                    )
                self.collection_name = collection_name

        # 官方构造器把 ChromaRetriever 作为 module global 调用两次，
        # 其中第一次 client.reset() 会清空 client 内全部 collection。
        # 在锁内临时换成 conversation 专属的官方 persistent 子类，
        # 使 reset 只作用于当前目录，不破坏 sibling conversation。
        with _AMEM_RUNTIME_CONSTRUCTION_LOCK:
            original_retriever_cls = runtime_module.ChromaRetriever
            runtime_module.ChromaRetriever = _ConversationPersistentRetriever
            try:
                runtime = runtime_cls(
                    model_name=self.config.embedding_model,
                    llm_backend="openai",
                    llm_model=self.config.llm_model,
                    api_key=self._openai_api_key,
                )
            finally:
                runtime_module.ChromaRetriever = original_retriever_cls
        self._bind_conversation_scoped_consolidation(
            runtime=runtime,
            conversation_id=conversation_id,
            retriever_cls=_ConversationPersistentRetriever,
        )
        self._configure_openai_transport(
            runtime=runtime,
            conversation_id=conversation_id,
        )
        self._install_openai_usage_observer(
            runtime=runtime,
            conversation_id=conversation_id,
        )
        self._install_embedding_usage_observer(runtime)
        return runtime

    def _bind_conversation_scoped_consolidation(
        self,
        *,
        runtime: Any,
        conversation_id: str,
        retriever_cls: type[Any],
    ) -> None:
        """把官方索引重建限定到当前 conversation 的持久化目录。

        官方 ``consolidate_memories()`` 会重新实例化模块全局
        ``ChromaRetriever("memories")``，从而越过构造期的 conversation 隔离。
        本绑定不改变 evolution 触发时机、MemoryNote 集合或重建顺序，只把同一批
        文档写回当前 runtime 已经使用的独立 Chroma client。
        """

        def consolidate_scoped(runtime_self: Any) -> None:
            """清空当前 conversation 的索引并按官方顺序完整重建。"""

            current_retriever = getattr(runtime_self, "retriever", None)
            current_client = getattr(current_retriever, "client", None)
            if current_client is None or not hasattr(current_client, "reset"):
                raise ConfigurationError(
                    "A-Mem product consolidation requires a resettable "
                    f"conversation retriever: {conversation_id}"
                )
            current_client.reset()
            runtime_self.retriever = retriever_cls(
                collection_name="memories",
                model_name=runtime_self.model_name,
            )
            self._install_embedding_usage_observer(runtime_self)
            self._rebuild_product_retriever(runtime_self, conversation_id)

        runtime.consolidate_memories = MethodType(consolidate_scoped, runtime)

    def _configure_openai_transport(self, runtime: Any, conversation_id: str) -> None:
        """把 endpoint、timeout 与 retry 注入官方 OpenAI controller。

        A-Mem 通用产品 controller 只调用 ``OpenAI(api_key=...)``。本方法只替换
        传输层 client，不改变 A-Mem
        的记忆算法、prompt 或调用顺序。
        """

        llm_controller = getattr(runtime, "llm_controller", None)
        llm = getattr(llm_controller, "llm", None)
        if llm is None or not hasattr(llm, "client"):
            raise ConfigurationError(
                "A-Mem official runtime does not expose a patchable OpenAI "
                f"client for {conversation_id}"
            )
        llm.client = _create_openai_compatible_client(
            api_key=self._openai_api_key,
            base_url=self._openai_base_url,
            timeout=self.config.api_timeout_seconds,
            max_retries=self.config.api_max_retries,
        )

    def _install_openai_usage_observer(
        self,
        runtime: Any,
        conversation_id: str,
    ) -> None:
        """为官方 OpenAI client 安装只读 usage observer。

        该 observer 只保存最近一次 response.usage 到官方 LLM 对象，不改变请求参数、
        返回对象或重试逻辑。没有开启 efficiency collector 时不安装，避免无观测运行
        增加额外包装。
        """

        if self._efficiency_collector is None or not self._efficiency_collector.enabled:
            return
        llm_controller = getattr(runtime, "llm_controller", None)
        llm = getattr(llm_controller, "llm", None)
        client = getattr(llm, "client", None)
        if llm is None or client is None:
            raise ConfigurationError(
                "A-Mem efficiency observation requires a patchable OpenAI "
                f"client for {conversation_id}"
            )
        if getattr(client, "_memory_benchmark_usage_wrapped", False):
            return
        llm.client = _UsageTrackingOpenAIClient(client, llm)

    def _install_embedding_usage_observer(self, runtime: Any) -> None:
        """包装官方 Chroma embedding function，只记录真实调用。"""

        collector = self._efficiency_collector
        retriever = getattr(runtime, "retriever", None)
        embedding_function = getattr(retriever, "embedding_function", None)
        model = getattr(embedding_function, "_model", None)
        if (
            collector is None
            or not collector.enabled
            or embedding_function is None
            or model is None
            or not hasattr(model, "encode")
            or getattr(model, "_memory_benchmark_embedding_wrapped", False)
        ):
            return

        original_encode = model.encode

        def wrapped_encode(input: Any, *args: Any, **kwargs: Any) -> Any:
            """原样返回 embedding 结果，成功后记录 token 与耗时。"""

            started_ns = perf_counter_ns()
            result = original_encode(input, *args, **kwargs)
            if collector.active_scope_type() is None:
                return result
            texts = [str(item) for item in input] if isinstance(input, list) else [str(input)]
            collector.record_embedding_call(
                model_id=AMEM_EMBEDDING_MODEL_ID,
                input_tokens=sum(
                    _count_sentence_transformer_tokens(model, text)
                    for text in texts
                ),
                latency_ms=_elapsed_ms(started_ns),
                token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
                latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
            )
            return result

        model.encode = wrapped_encode
        model._memory_benchmark_embedding_wrapped = True

    def _install_memory_build_usage_observer(
        self,
        runtime: Any,
        conversation_id: str,
    ) -> None:
        """包装官方 build LLM 入口，逐次记录 memory_build LLM token。

        该包装只在 runner 已建立 conversation scope 时记录；question scope 的
        query/answer 调用仍由 `_generate_query_keywords()` 和 `_call_answer_llm()`
        显式记录，避免重复计数。
        """

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        llm_controller = getattr(runtime, "llm_controller", None)
        llm = getattr(llm_controller, "llm", None)
        if llm is None or not hasattr(llm, "get_completion"):
            return
        if getattr(llm, "_memory_benchmark_build_usage_wrapped", False):
            return
        original_get_completion = llm.get_completion

        def wrapped_get_completion(*args: Any, **kwargs: Any) -> Any:
            """调用官方 LLM 方法并在 conversation scope 内记录 build token。"""

            response = original_get_completion(*args, **kwargs)
            if collector.active_scope_type() == "conversation":
                prompt_text = ""
                if args:
                    prompt_text = str(args[0])
                elif "prompt" in kwargs:
                    prompt_text = str(kwargs["prompt"])
                self._record_llm_call(
                    model_id="amem-memory-llm",
                    prompt_text=prompt_text,
                    output_text=str(response),
                    llm=llm,
                )
            return response

        llm.get_completion = wrapped_get_completion
        llm._memory_benchmark_build_usage_wrapped = True

    def _call_runtime_add(
        self, runtime: Any, turn: Turn, session_time: str | None = None,
    ) -> str:
        """把一个公开 turn 写入 A-Mem 产品 note，返回稳定 note id。"""

        rendered_text = turn_text_with_images(turn)
        if not rendered_text:
            raise ConfigurationError(f"A-Mem turn has no text content: {turn.turn_id}")
        normalized_role = (turn.normalized_role or "").strip().lower()
        speaker = normalized_role if normalized_role in {"user", "assistant"} else turn.speaker
        content = f"{speaker}: {rendered_text}"
        timestamp = turn.turn_time or session_time
        add_kwargs: dict[str, Any] = {}
        analyze_content = getattr(runtime, "analyze_content", None)
        if callable(analyze_content):
            analysis = self._suppress_stdout_if_needed(analyze_content, content)
            if not isinstance(analysis, dict):
                raise ConfigurationError("A-Mem analyze_content must return a dict")
            if (
                analysis.get("keywords") == []
                and analysis.get("context") == "General"
                and analysis.get("tags") == []
            ):
                # 官方 analyze_content() 对 API/JSON 任意异常返回这组固定 sentinel。
                # 若继续写 note，smoke 会在构建失败后假绿，因此必须在 adapter 边界阻断。
                raise ConfigurationError(
                    f"A-Mem content analysis failed for turn: {turn.turn_id}"
                )
            add_kwargs = {
                key: analysis[key]
                for key in ("keywords", "context", "tags")
                if key in analysis
            }
        note_id = self._suppress_stdout_if_needed(
            runtime.add_note,
            content,
            time=timestamp,
            **add_kwargs,
        )
        if not isinstance(note_id, str) or not note_id.strip():
            raise ConfigurationError("A-Mem add_note must return a non-empty note id")
        if timestamp is None:
            # 产品 MemoryNote 对 None 会默认填入墙钟。benchmark 缺失时间不能被
            # 运行时刻污染；立即经官方 update() 写回 None，不改 content/向量。
            update = getattr(runtime, "update", None)
            if callable(update):
                if update(note_id, timestamp=None) is not True:
                    raise ConfigurationError(
                        f"A-Mem failed to preserve missing timestamp: {turn.turn_id}"
                    )
            else:
                note = getattr(runtime, "memories", {}).get(note_id)
                if note is not None:
                    note.timestamp = None
        return note_id

    def _build_answer_prompt(self, question: Question, memory_context: str) -> str:
        """构造不含 gold answer 的固定 reader prompt。"""

        if _is_longmemeval_question(question):
            if not question.question_time:
                raise ConfigurationError(
                    "A-Mem LongMemEval reader prompt requires question_time: "
                    f"{question.question_id}"
                )
            memories = memory_context.strip() or "(No relevant memories found)"
            return (
                f"Question time:{question.question_time} and question:{question.text}\n"
                "Please answer the question based on the following memories: "
                f"{memories}"
            )

        question_text = _effective_question_text(question)
        if question.category == "2":
            return (
                f"Based on the context: {memory_context}, answer the following question. "
                "Use DATE of CONVERSATION to answer with an approximate date. "
                "Please generate the shortest possible answer, using words from the "
                "conversation where possible, and avoid using any subjects.\n\n"
                f"Question: {question_text} Short answer:"
            )
        return (
            f"Based on the context: {memory_context}, write an answer in the form of a "
            "short phrase for the following question. Answer with exact words from the "
            f"context whenever possible.\n\nQuestion: {question_text} Short answer:"
        )

    def _build_prompt_messages(
        self,
        *,
        question: Question,
        answer_prompt: str,
    ) -> list[PromptMessage]:
        """构造 answer LLM role messages。

        LongMemEval 使用 LightMem 论文脚本里的通用 reader 形态；其他 benchmark
        保持 A-Mem robust LoCoMo prompt 的 system + user 结构。
        """

        if _is_longmemeval_question(question):
            return [
                PromptMessage(role="system", content="You are a helpful assistant."),
                PromptMessage(role="user", content=answer_prompt),
            ]
        return [
            PromptMessage(role="system", content=AMEM_ANSWER_SYSTEM_MESSAGE),
            PromptMessage(role="user", content=answer_prompt),
        ]

    def _generate_query_keywords(self, question: Question, runtime: Any) -> str:
        """按 A-Mem 官方 robust QA 脚本先把问题改写为检索关键词。

        输入:
            question: 公开问题对象，不能包含 gold answer。
            runtime: 当前 conversation 隔离的 A-Mem runtime。

        输出:
            str: 传给 `find_related_memories_raw()` 的关键词查询文本。
        """

        llm = self._select_llm(runtime=runtime, question=question)
        effective_text = _effective_question_text(question)
        prompt = (
            "Given the following question, generate several keywords separated by "
            "commas.\n\n"
            f"Question: {effective_text}\n\n"
            "Keywords:"
        )
        response = self._suppress_stdout_if_needed(llm.get_completion, prompt)
        response_text = str(response)
        self._record_llm_call(
            model_id="amem-query-llm",
            prompt_text=prompt,
            output_text=response_text,
            llm=llm,
        )
        parsed_keywords = _parse_keywords_response(response_text)
        return parsed_keywords or effective_text

    def _retrieve_k_for_question(self, question: Question) -> int:
        """返回检索记忆数量。

        ws02.5 config 归一化（方案 B，2026-07-09）：统一用 profile 的
        `retrieve_k`（repo 默认 10，test_advanced_robust.py:348 --retrieve_k
        default=10；底层 memory_layer_robust.py:430 签名 k=5 被 retrieve_k=10
        覆盖不生效），不再按 LoCoMo category 用 paper Table 8 的 per-category k
        （cat1/2/5=40、cat3/4=50，已弃用并留档 method-interface-inventory.md
        hyperparameters 字段，作论文复现验证配置）。
        """

        return self.config.retrieve_k

    def _is_adversarial_category(self, question: Question) -> bool:
        """判断是否为 A-Mem 官方 adversarial prompt 需要 gold 的类别。"""

        return _normalize_category(question.category) == "5"

    def _select_llm(self, runtime: Any, question: Question) -> Any:
        """选择 query generation 和 reader 共用的 LLM。"""

        selected_llm = self._answer_llm
        if selected_llm is None and hasattr(runtime, "llm_controller"):
            selected_llm = runtime.llm_controller.llm
        if selected_llm is None:
            raise ConfigurationError(
                f"A-Mem LLM is not available for {question.conversation_id}"
            )
        return selected_llm

    def _call_answer_llm(self, prompt: str, question: Question, runtime: Any) -> str:
        """调用 reader LLM；测试阶段由 fake LLM 提供。"""

        answer_llm = self._select_llm(runtime=runtime, question=question)
        temperature = 0.7
        response = self._suppress_stdout_if_needed(
            answer_llm.get_completion,
            prompt,
            temperature=temperature,
        )
        response_text = str(response)
        self._record_llm_call(
            model_id="amem-answer-llm",
            prompt_text=prompt,
            output_text=response_text,
            llm=answer_llm,
        )
        return response_text

    def _record_llm_call(
        self,
        *,
        model_id: str,
        prompt_text: str,
        output_text: str,
        llm: Any,
    ) -> None:
        """记录 A-Mem wrapper 可见的一次 LLM 调用 token。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        api_input_tokens, api_output_tokens = extract_api_token_usage(
            getattr(llm, "last_usage", None)
        )
        usage = resolve_token_usage(
            api_input_tokens=api_input_tokens,
            api_output_tokens=api_output_tokens,
            prompt_text=prompt_text,
            output_text=output_text,
            tokenizer=_TiktokenCounter(self.config.llm_model),
        )
        collector.record_llm_call(
            model_id=model_id,
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
        """按配置压制第三方源码 stdout。"""

        if not self.config.suppress_official_stdout:
            return func(*args, **kwargs)
        with contextlib.redirect_stdout(io.StringIO()):
            return func(*args, **kwargs)


def _amem_memory_metadata(note: Any) -> dict[str, Any]:
    """按产品 ``add_note`` 的字段集合构造 Chroma metadata。"""

    return {
        "id": str(getattr(note, "id", "")),
        "content": str(getattr(note, "content", "")),
        "keywords": list(getattr(note, "keywords", []) or []),
        "links": list(getattr(note, "links", []) or []),
        "retrieval_count": int(getattr(note, "retrieval_count", 0) or 0),
        "timestamp": getattr(note, "timestamp", None),
        "last_accessed": getattr(note, "last_accessed", None),
        "context": str(getattr(note, "context", "") or ""),
        "evolution_history": list(getattr(note, "evolution_history", []) or []),
        "category": str(getattr(note, "category", "Uncategorized") or "Uncategorized"),
        "tags": list(getattr(note, "tags", []) or []),
    }


def _format_amem_memory_note(note: Any) -> str:
    """把一条产品 MemoryNote 无损渲染为公开 memory 文本。"""

    return _format_amem_result_fields(
        content=getattr(note, "content", ""),
        timestamp=getattr(note, "timestamp", None),
        context=getattr(note, "context", None),
        keywords=getattr(note, "keywords", None),
        tags=getattr(note, "tags", None),
    )


def _format_amem_result_fields(
    *,
    content: Any,
    timestamp: Any,
    context: Any,
    keywords: Any,
    tags: Any,
) -> str:
    """用稳定标签渲染 A-Mem 产品返回的全部 answer-visible 字段。"""

    parts = [f"Memory content: {str(content)}"]
    if timestamp is not None and str(timestamp).strip():
        parts.append(f"Time: {str(timestamp)}")
    if context is not None and str(context).strip():
        parts.append(f"Context: {str(context)}")
    keyword_values = [str(item) for item in keywords or [] if str(item).strip()]
    if keyword_values:
        parts.append(f"Keywords: {', '.join(keyword_values)}")
    tag_values = [str(item) for item in tags or [] if str(item).strip()]
    if tag_values:
        parts.append(f"Tags: {', '.join(tag_values)}")
    return "\n".join(parts)


def _format_amem_search_results(results: list[Any]) -> str:
    """依产品检索名次渲染 formatted_memory，零命中显式返回 sentinel。"""

    formatted: list[str] = []
    for index, raw in enumerate(results, 1):
        if not isinstance(raw, dict):
            raise ConfigurationError("A-Mem search_agentic result must be a dict")
        if not str(raw.get("content") or "").strip():
            raise ConfigurationError("A-Mem retrieved memory is missing content")
        body = _format_amem_result_fields(
            content=raw.get("content"),
            timestamp=raw.get("timestamp"),
            context=raw.get("context"),
            keywords=raw.get("keywords"),
            tags=raw.get("tags"),
        )
        formatted.append(f"[Memory {index}]\n{body}")
    return "\n\n".join(formatted) if formatted else "No relevant memories found"


def _amem_retrieved_item(
    raw: Any,
    *,
    lineage: dict[str, str],
    index: int,
) -> RetrievedItem:
    """把产品 ``search_agentic`` 命中映射为带精确 turn sidecar 的 item。"""

    if not isinstance(raw, dict):
        raise ConfigurationError("A-Mem search_agentic result must be a dict")
    item_id = str(raw.get("id") or "").strip()
    content = str(raw.get("content") or "").strip()
    if not item_id or not content:
        raise ConfigurationError(f"A-Mem retrieved item {index} lacks id/content")
    source_turn_id = lineage.get(item_id)
    if not isinstance(source_turn_id, str) or not source_turn_id.strip():
        raise ConfigurationError(
            f"A-Mem retrieved note lacks source-turn sidecar: {item_id}"
        )
    raw_score = raw.get("score")
    score = float(raw_score) if isinstance(raw_score, (int, float)) else None
    raw_timestamp = raw.get("timestamp")
    return RetrievedItem(
        item_id=item_id,
        content=content,
        score=score,
        timestamp=(
            str(raw_timestamp)
            if raw_timestamp is not None and str(raw_timestamp).strip()
            else None
        ),
        source_turn_ids=(source_turn_id,),
        metadata={
            "context": str(raw.get("context") or ""),
            "keywords": [str(item) for item in raw.get("keywords") or []],
            "tags": [str(item) for item in raw.get("tags") or []],
            "is_neighbor": bool(raw.get("is_neighbor", False)),
        },
    )


def _count_sentence_transformer_tokens(model: Any, text: str) -> int:
    """用 A-Mem 实际 SentenceTransformer tokenizer 按真实截断上限计数。"""

    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None or not hasattr(tokenizer, "encode"):
        raise ConfigurationError("A-Mem embedding tokenizer is unavailable")
    max_length = getattr(model, "max_seq_length", None)
    if isinstance(max_length, int) and max_length > 0:
        return len(tokenizer.encode(text, truncation=True, max_length=max_length))
    return len(tokenizer.encode(text))


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
                    "tiktoken is required for A-Mem token estimation"
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


def _effective_question_text(question: Question) -> str:
    """构造含可选时间上下文的有效问题文本。

    LoCoMo 不含 question_time，返回原始文本。LongMemEval 的 question_time
    会作为时间前缀拼接，供检索和回答 prompt 使用。
    """

    if question.question_time:
        return f"Question time: {question.question_time}. Question: {question.text}"
    return str(question.text)


def _normalize_category(category: object) -> str | None:
    """把 benchmark category 归一为字符串；缺失时返回 None。"""

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


def _answer_prompt_profile_for_question(question: Question) -> str:
    """返回当前 question 对应的 answer prompt profile 名称。"""

    if _is_longmemeval_question(question):
        return AMEM_LONGMEMEVAL_READER_PROMPT_VERSION
    return AMEM_READER_PROMPT_VERSION


def _parse_keywords_response(response: str) -> str:
    """复刻 A-Mem 官方 `parse_keywords_response()` 的关键词解析逻辑。"""

    cleaned = _strip_markdown_fences(response.strip())
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return cleaned
    if isinstance(payload, dict) and "keywords" in payload:
        return str(payload["keywords"]).strip()
    return cleaned


def _strip_markdown_fences(text: str) -> str:
    """去掉 LLM 可能包裹的 markdown code fence。"""

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _create_openai_compatible_client(
    api_key: str | None,
    base_url: str | None,
    timeout: float,
    max_retries: int,
) -> Any:
    """创建显式携带 base_url、timeout 和 retry 的 OpenAI-compatible client。"""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ConfigurationError("openai package is required for A-Mem") from exc
    if not api_key:
        raise ConfigurationError("A-Mem OpenAI-compatible client requires API key")
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        max_retries=max_retries,
    )


class _UsageTrackingOpenAIClient:
    """透明包装 OpenAI client，只记录 response.usage。"""

    _memory_benchmark_usage_wrapped = True

    def __init__(self, client: Any, usage_target: Any) -> None:
        """保存原始 client，并包装 chat completions 入口。"""

        self._client = client
        self.chat = _UsageTrackingChat(getattr(client, "chat"), usage_target)

    def __getattr__(self, name: str) -> Any:
        """未显式包装的属性全部转发给原始 client。"""

        return getattr(self._client, name)


class _UsageTrackingChat:
    """透明包装 OpenAI chat namespace。"""

    def __init__(self, chat: Any, usage_target: Any) -> None:
        """保存原始 chat namespace，并包装 completions。"""

        self._chat = chat
        self.completions = _UsageTrackingCompletions(
            getattr(chat, "completions"),
            usage_target,
        )

    def __getattr__(self, name: str) -> Any:
        """未显式包装的属性全部转发给原始 chat namespace。"""

        return getattr(self._chat, name)


class _UsageTrackingCompletions:
    """透明包装 OpenAI chat.completions namespace。"""

    def __init__(self, completions: Any, usage_target: Any) -> None:
        """保存原始 completions namespace 和 usage 写入目标。"""

        self._completions = completions
        self._usage_target = usage_target

    def create(self, *args: Any, **kwargs: Any) -> Any:
        """调用原始 create，并把 response.usage 保存到 A-Mem LLM 对象。"""

        response = self._completions.create(*args, **kwargs)
        self._usage_target.last_usage = getattr(response, "usage", None)
        return response

    def __getattr__(self, name: str) -> Any:
        """未显式包装的属性全部转发给原始 completions namespace。"""

        return getattr(self._completions, name)


def _atomic_pickle_dump(path: Path, payload: Any) -> None:
    """原子写入 pickle 文件。

    输入:
        path: 目标 pickle 文件路径。
        payload: 要写入的 Python 对象；仅用于本项目生成并读取的 method state。

    输出:
        None；写入完成后原子替换目标文件。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        with temporary_path.open("wb") as temporary_file:
            pickle.dump(payload, temporary_file)
        temporary_path.replace(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary_path.unlink()


def clean_amem_conversation_state(storage_root: str | Path, conversation_id: str) -> None:
    """删除 A-Mem 单个 conversation 的半写入状态目录。

    输入:
        storage_root: 当前 run 的 A-Mem method state 根目录。
        conversation_id: 需要重新 ingest 的 conversation id。

    输出:
        None。目标目录不存在时视为已经干净。
    """

    root = Path(storage_root).expanduser().resolve()
    target = (root / _safe_path_name(conversation_id)).resolve()
    if root == target or root not in target.parents:
        raise ConfigurationError(f"Unsafe A-Mem state cleanup path: {target}")
    shutil.rmtree(target, ignore_errors=True)


def _user_prompt_from_prompt_messages(messages: list[PromptMessage]) -> str:
    """从 prompt_messages 中取 legacy A-Mem `get_completion()` 需要的 user prompt。"""

    for message in messages:
        if message.role == "user":
            return message.content
    raise ConfigurationError("A-Mem answer prompt is missing user message")


def _sha256_file(path: Path) -> str:
    """计算单个状态文件的 SHA-256。"""

    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_path_name(value: str) -> str:
    """把 conversation_id 转成安全目录名。"""

    return "".join(
        character if character.isalnum() or character in "-_." else "_"
        for character in value
    )

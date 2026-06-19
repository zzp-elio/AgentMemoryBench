"""A-Mem 的 conversation-QA 适配器。

本模块包装 `third_party/methods/A-mem/` 中的官方 robust memory layer。Adapter 负责
配置校验、源码身份、conversation 隔离和统一接口；不重写 A-Mem 的记忆算法。
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
from pathlib import Path
import sys
from time import perf_counter_ns
from typing import Any

from memory_benchmark.config.settings import PathSettings, load_path_settings
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    ConfigurationError,
    Conversation,
    Question,
    Turn,
)
from memory_benchmark.core.interfaces import BaseMemorySystem
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    resolve_token_usage,
)
from memory_benchmark.storage import atomic_write_json


AMEM_METHOD_DIRECTORY = "A-mem"
AMEM_ADAPTER_VERSION = "conversation-qa-v1"
AMEM_READER_PROMPT_VERSION = "amem-reader-v1"
AMEM_QUERY_KEYWORD_PROMPT_VERSION = "amem-query-keywords-v1"
AMEM_STATE_SCHEMA_VERSION = 1
AMEM_MEMORIES_FILENAME = "memories.pkl"
AMEM_RETRIEVER_FILENAME = "retriever.pkl"
AMEM_RETRIEVER_EMBEDDINGS_FILENAME = "retriever_embeddings.npy"
AMEM_STATE_MANIFEST_FILENAME = "state_manifest.json"
AMEM_GPT4O_MINI_CATEGORY_K = {
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
        max_workers: runner 可读取的建议 conversation 并发数；初期保持 1。
        use_robust_layer: 是否使用官方 robust layer；当前必须为 true。
        suppress_official_stdout: 是否压制第三方源码中的 stdout。
        profile_name: 可审计 profile 名称。
    """

    llm_model: str
    embedding_model: str
    retrieve_k: int
    max_workers: int
    use_robust_layer: bool = True
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
        if self.max_workers < 1:
            raise ConfigurationError("A-Mem max_workers must be positive")
        if not self.use_robust_layer:
            raise ConfigurationError(
                "A-Mem adapter currently requires use_robust_layer=true"
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
    """计算 vendored A-Mem 关键源码的确定性身份。

    输入:
        path_settings: 项目路径配置；为空时从当前项目根加载。

    输出:
        dict: SHA-256、文件数量和参与哈希的相对路径。
    """

    settings = path_settings or load_path_settings()
    amem_root = settings.resolve_third_party_method_path(AMEM_METHOD_DIRECTORY)
    required_files = [
        "README.md",
        "memory_layer_robust.py",
        "llm_text_parsers.py",
        "test_advanced_robust.py",
        "run_k_sweep.sh",
        "requirements.txt",
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
    }


def import_amem_robust_classes(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """从 vendored A-Mem 源码导入 robust 类。

    输入:
        path_settings: 项目路径配置；为空时自动加载。

    输出:
        dict: 官方 `RobustAgenticMemorySystem` 和 `RobustLLMController` 类。

    说明:
        导入过程临时把 A-Mem 根目录放入 `sys.path`，避免把第三方源码安装成一等
        package，也避免污染本项目 package discovery。
    """

    settings = path_settings or load_path_settings()
    amem_root = settings.resolve_third_party_method_path(AMEM_METHOD_DIRECTORY)
    if not (amem_root / "memory_layer_robust.py").is_file():
        raise ConfigurationError(f"A-Mem robust layer missing: {amem_root}")

    root_text = str(amem_root)
    inserted = False
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
        inserted = True
    try:
        module = importlib.import_module("memory_layer_robust")
        return {
            "RobustAgenticMemorySystem": module.RobustAgenticMemorySystem,
            "RobustLLMController": module.RobustLLMController,
        }
    finally:
        if inserted:
            with contextlib.suppress(ValueError):
                sys.path.remove(root_text)


class AMem(BaseMemorySystem):
    """使用官方 A-Mem robust memory layer 的统一 memory system。"""

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
        self._runtimes: dict[str, Any] = {}

    def add(self, conversations: list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。"""

        conversation_ids: list[str] = []
        for conversation in conversations:
            runtime = self._get_or_create_runtime(conversation.conversation_id)
            turn_count = 0
            for turn in self._iter_turns(conversation):
                self._call_runtime_add(runtime, turn)
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
        retriever = getattr(runtime, "retriever", None)
        if retriever is None or not hasattr(retriever, "load"):
            raise ConfigurationError(
                f"A-Mem retriever cannot load persisted state: {conversation_id}"
            )
        self._suppress_stdout_if_needed(
            retriever.load,
            str(state_dir / AMEM_RETRIEVER_FILENAME),
            str(state_dir / AMEM_RETRIEVER_EMBEDDINGS_FILENAME),
        )
        self._runtimes[conversation_id] = runtime
        if int(manifest.get("turn_count", -1)) != len(self._iter_turns(conversation)):
            raise ConfigurationError(
                f"A-Mem state turn_count mismatch for {conversation_id}"
            )

    def get_answer(self, question: Question) -> AnswerResult:
        """基于 A-Mem 检索上下文回答公开问题。"""

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
        if collector is not None and collector.enabled:
            collector.record_retrieval_result(
                latency_ms=retrieval_latency_ms,
                injected_memory_context_tokens=_count_openai_tokens(
                    memory_context,
                    self.config.llm_model,
                ),
            )
        prompt = self._build_answer_prompt(
            question=question,
            memory_context=memory_context,
        )
        answer_started_ns = perf_counter_ns()
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
                self._runtimes[conversation_id] = self._create_official_runtime(
                    conversation_id
                )
            else:
                self._runtimes[conversation_id] = self._runtime_factory(conversation_id)
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
        retriever = getattr(runtime, "retriever", None)
        if retriever is None or not hasattr(retriever, "save"):
            raise ConfigurationError(
                "A-Mem retriever cannot persist state because it does not expose save()"
            )
        self._suppress_stdout_if_needed(
            retriever.save,
            str(state_dir / AMEM_RETRIEVER_FILENAME),
            str(state_dir / AMEM_RETRIEVER_EMBEDDINGS_FILENAME),
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
            AMEM_RETRIEVER_FILENAME: _sha256_file(state_dir / AMEM_RETRIEVER_FILENAME),
            AMEM_RETRIEVER_EMBEDDINGS_FILENAME: _sha256_file(
                state_dir / AMEM_RETRIEVER_EMBEDDINGS_FILENAME
            ),
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
            AMEM_RETRIEVER_FILENAME,
            AMEM_RETRIEVER_EMBEDDINGS_FILENAME,
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

    def _create_official_runtime(self, conversation_id: str) -> Any:
        """构造官方 A-Mem robust runtime。

        输入:
            conversation_id: 当前 conversation id，只用于错误信息和后续扩展。

        输出:
            Any: 官方 `RobustAgenticMemorySystem` 实例。
        """

        if not self._openai_api_key:
            raise ConfigurationError(
                f"A-Mem production runtime requires OpenAI API key for {conversation_id}"
            )
        classes = import_amem_robust_classes(self.path_settings)
        runtime_cls = classes["RobustAgenticMemorySystem"]
        runtime = runtime_cls(
            model_name=self.config.embedding_model,
            llm_backend="openai",
            llm_model=self.config.llm_model,
            api_key=self._openai_api_key,
            api_base=self._openai_base_url,
            check_connection=False,
        )
        self._ensure_openai_base_url(runtime=runtime, conversation_id=conversation_id)
        return runtime

    def _ensure_openai_base_url(self, runtime: Any, conversation_id: str) -> None:
        """把 OpenAI-compatible base URL 注入官方 OpenAI controller。

        A-Mem robust runtime 接收 `api_base`，但当前 vendored `RobustOpenAIController`
        实际只调用 `OpenAI(api_key=...)`。本方法只替换传输层 client，不改变 A-Mem
        的记忆算法、prompt 或调用顺序。
        """

        if not self._openai_base_url:
            return
        llm_controller = getattr(runtime, "llm_controller", None)
        llm = getattr(llm_controller, "llm", None)
        if llm is None or not hasattr(llm, "client"):
            raise ConfigurationError(
                "A-Mem OpenAI-compatible base URL is configured, but the official "
                f"runtime does not expose a patchable OpenAI client for {conversation_id}"
            )
        llm.client = _create_openai_compatible_client(
            api_key=self._openai_api_key,
            base_url=self._openai_base_url,
        )

    def _iter_turns(self, conversation: Conversation) -> list[Turn]:
        """按 session 顺序展开公开 turn。"""

        turns: list[Turn] = []
        for session in conversation.sessions:
            turns.extend(session.turns)
        return turns

    def _call_runtime_add(self, runtime: Any, turn: Turn) -> None:
        """把一个公开 turn 写入 A-Mem runtime。"""

        content = f"Speaker {turn.speaker} says: {turn.content}"
        self._suppress_stdout_if_needed(runtime.add_note, content, time=turn.turn_time)

    def _build_answer_prompt(self, question: Question, memory_context: str) -> str:
        """构造不含 gold answer 的固定 reader prompt。"""

        if question.category == "2":
            return (
                f"Based on the context: {memory_context}, answer the following question. "
                "Use DATE of CONVERSATION to answer with an approximate date. "
                "Please generate the shortest possible answer, using words from the "
                "conversation where possible, and avoid using any subjects.\n\n"
                f"Question: {question.text} Short answer:"
            )
        return (
            f"Based on the context: {memory_context}, write an answer in the form of a "
            "short phrase for the following question. Answer with exact words from the "
            f"context whenever possible.\n\nQuestion: {question.text} Short answer:"
        )

    def _generate_query_keywords(self, question: Question, runtime: Any) -> str:
        """按 A-Mem 官方 robust QA 脚本先把问题改写为检索关键词。

        输入:
            question: 公开问题对象，不能包含 gold answer。
            runtime: 当前 conversation 隔离的 A-Mem runtime。

        输出:
            str: 传给 `find_related_memories_raw()` 的关键词查询文本。
        """

        llm = self._select_llm(runtime=runtime, question=question)
        prompt = (
            "Given the following question, generate several keywords separated by "
            "commas.\n\n"
            f"Question: {question.text}\n\n"
            "Keywords:"
        )
        response = self._suppress_stdout_if_needed(llm.get_completion, prompt)
        response_text = str(response)
        self._record_llm_call(
            model_id="amem-query-llm",
            prompt_text=prompt,
            output_text=response_text,
        )
        parsed_keywords = _parse_keywords_response(response_text)
        return parsed_keywords or question.text

    def _retrieve_k_for_question(self, question: Question) -> int:
        """返回 A-Mem Table 8 的 GPT-4o-mini 类别检索深度。

        LoCoMo category 与 Table 8 对齐；非 LoCoMo 或缺 category 的数据集回退到
        profile 中的 `retrieve_k`，避免把 LoCoMo 特例升格为统一接口字段。
        """

        category = _normalize_category(question.category)
        if category is None:
            return self.config.retrieve_k
        return AMEM_GPT4O_MINI_CATEGORY_K.get(category, self.config.retrieve_k)

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
        )
        return response_text

    def _record_llm_call(
        self,
        *,
        model_id: str,
        prompt_text: str,
        output_text: str,
    ) -> None:
        """记录 A-Mem wrapper 可见的一次 LLM 调用 token。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        usage = resolve_token_usage(
            api_input_tokens=None,
            api_output_tokens=None,
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


def _normalize_category(category: object) -> str | None:
    """把 benchmark category 归一为字符串；缺失时返回 None。"""

    if category is None:
        return None
    category_text = str(category).strip()
    return category_text or None


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


def _create_openai_compatible_client(api_key: str | None, base_url: str | None) -> Any:
    """创建显式携带 base_url 的 OpenAI-compatible client。"""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ConfigurationError("openai package is required for A-Mem") from exc
    if not api_key:
        raise ConfigurationError("A-Mem OpenAI-compatible client requires API key")
    return OpenAI(api_key=api_key, base_url=base_url)


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

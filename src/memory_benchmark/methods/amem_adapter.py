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
)


AMEM_METHOD_DIRECTORY = "A-mem"
AMEM_ADAPTER_VERSION = "conversation-qa-v1"
AMEM_READER_PROMPT_VERSION = "amem-reader-v1"


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
            path_settings: 项目路径配置。
            efficiency_collector: runner 管理的可选效率 observation collector。
        """

        self.config = config
        self._runtime_factory = runtime_factory
        self._answer_llm = answer_llm
        self._openai_api_key = openai_api_key
        self._openai_base_url = openai_base_url
        self.path_settings = path_settings or load_path_settings()
        self._efficiency_collector = efficiency_collector
        self._runtimes: dict[str, Any] = {}

    def add(self, conversations: list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。"""

        conversation_ids: list[str] = []
        for conversation in conversations:
            runtime = self._get_or_create_runtime(conversation.conversation_id)
            for turn in self._iter_turns(conversation):
                self._call_runtime_add(runtime, turn)
            conversation_ids.append(conversation.conversation_id)
        return AddResult(conversation_ids=conversation_ids)

    def get_answer(self, question: Question) -> AnswerResult:
        """基于 A-Mem 检索上下文回答公开问题。"""

        if question.conversation_id not in self._runtimes:
            raise ConfigurationError(
                f"A-Mem conversation has not been added: {question.conversation_id}"
            )
        runtime = self._runtimes[question.conversation_id]
        collector = self._efficiency_collector
        retrieval_started_ns = perf_counter_ns()
        if collector is not None and collector.enabled:
            with collector.operation_stage(EfficiencyStage.RETRIEVAL):
                context = runtime.find_related_memories_raw(
                    question.text,
                    k=self.config.retrieve_k,
                )
        else:
            context = runtime.find_related_memories_raw(
                question.text,
                k=self.config.retrieve_k,
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
                "retrieve_k": self.config.retrieve_k,
                "reader_prompt_version": AMEM_READER_PROMPT_VERSION,
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
        return runtime_cls(
            model_name=self.config.embedding_model,
            llm_backend="openai",
            llm_model=self.config.llm_model,
            api_key=self._openai_api_key,
            api_base=self._openai_base_url,
            check_connection=False,
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

    def _call_answer_llm(self, prompt: str, question: Question, runtime: Any) -> str:
        """调用 reader LLM；测试阶段由 fake LLM 提供。"""

        answer_llm = self._answer_llm
        if answer_llm is None and hasattr(runtime, "llm_controller"):
            answer_llm = runtime.llm_controller.llm
        if answer_llm is None:
            raise ConfigurationError(
                f"A-Mem answer LLM is not available for {question.conversation_id}"
            )
        temperature = 0.7
        return self._suppress_stdout_if_needed(
            answer_llm.get_completion,
            prompt,
            temperature=temperature,
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

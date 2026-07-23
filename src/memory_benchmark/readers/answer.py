"""framework-owned answer LLM caller。

本模块只把已选 builder 构造好的完整 `prompt_messages` 交给可替换 LLM client。
主配置 builder 归 `prompts.benchmarks`，显式作者校准 builder 归
`prompts.author`；method adapter 只负责返回 `formatted_memory` 与公开 readout
变量，不拥有主表 answer prompt。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from openai import OpenAI

from memory_benchmark.config import AnswerLLMSettings, OpenAISettings
from memory_benchmark.core import (
    AnswerPromptResult,
    AnswerResult,
    ConfigurationError,
    PromptMessage,
    Question,
)


DEFAULT_ANSWER_PROMPT = """You are a question-answering system.
Answer the question using only the retrieved memory context.
If the context is insufficient, answer "I don't know".

Question:
{question}

Question Time:
{question_time}

Retrieved Memory Context:
{memory_context}

Answer:"""


class AnswerLLMClient(Protocol):
    """framework reader 使用的最小 LLM client 协议。"""

    model_name: str

    def complete(self, *, prompt: str) -> str:
        """输入 prompt，返回纯文本 answer。

        输入:
            prompt: 已包含 question 与 memory context 的完整 reader prompt。

        输出:
            str: LLM 生成的原始文本答案。
        """


@dataclass(frozen=True)
class AnswerLLMResponse:
    """answer LLM 的标准返回结构。

    字段:
        text: LLM 生成的文本。
        usage: SDK 返回的 token usage 对象；没有时为 None。
        raw_response: 原始 SDK response，仅供 debug，不直接进入标准 artifact。
    """

    text: str
    usage: Any | None = None
    raw_response: Any | None = None


@dataclass(frozen=True)
class AnswerPromptTemplate:
    """answer prompt 模板。"""

    template: str = DEFAULT_ANSWER_PROMPT
    profile_name: str = "default"

    def __post_init__(self) -> None:
        """校验核心占位符，避免 prompt 未注入问题或记忆上下文。

        输入:
            无。使用 dataclass 字段。

        输出:
            None。模板不合法时抛出 ConfigurationError。
        """

        if "{question}" not in self.template:
            raise ConfigurationError("Answer prompt template must include {question}")
        if "{memory_context}" not in self.template:
            raise ConfigurationError(
                "Answer prompt template must include {memory_context}"
            )

    def render(self, *, question: Question, memory_context: str) -> str:
        """渲染公开 Question 和检索上下文。

        输入:
            question: framework reader 可见的公开问题。
            memory_context: method 返回且已经格式化好的记忆上下文。

        输出:
            str: 可直接交给 answer LLM 的 prompt。
        """

        return self.template.format(
            question=question.text,
            memory_context=memory_context,
            question_time=question.question_time or "",
            conversation_id=question.conversation_id,
            category=question.category or "",
            options=question.options or {},
        )


@dataclass
class FrameworkAnswerReader:
    """统一 answer reader。"""

    client: AnswerLLMClient
    prompt_template: AnswerPromptTemplate = field(default_factory=AnswerPromptTemplate)

    def generate_answer(
        self,
        *,
        question: Question,
        retrieval: AnswerPromptResult,
    ) -> AnswerResult:
        """基于检索上下文生成最终 answer。

        输入:
            question: 当前待回答的公开问题。
            retrieval: method 返回的完整 prompt messages，其中 `prompt_messages` 必须非空。

        输出:
            AnswerResult: framework reader 生成的答案及公开元信息。
        """

        answer, _, _ = self.generate_answer_with_trace(
            question=question,
            retrieval=retrieval,
        )
        return answer

    def generate_answer_with_trace(
        self,
        *,
        question: Question,
        retrieval: AnswerPromptResult,
    ) -> tuple[AnswerResult, str, AnswerLLMResponse]:
        """生成 answer，并返回 prompt 与 LLM usage 供 runner 做效率观测。"""

        if retrieval.question_id != question.question_id:
            raise ConfigurationError(
                "Retrieval question_id mismatch: "
                f"{retrieval.question_id} != {question.question_id}"
            )
        if retrieval.conversation_id != question.conversation_id:
            raise ConfigurationError(
                "Retrieval conversation_id mismatch: "
                f"{retrieval.conversation_id} != {question.conversation_id}"
            )
        prompt_messages = retrieval.prompt_messages
        if not prompt_messages:
            raise ConfigurationError(
                f"Retrieval prompt_messages is empty: {question.question_id}"
            )
        prompt = retrieval.answer_prompt.strip()

        response = _complete_answer_client(
            self.client,
            prompt=prompt,
            prompt_messages=prompt_messages,
        )
        answer = response.text.strip()
        if not answer:
            raise ConfigurationError(
                "Framework answer reader returned an empty answer: "
                f"{question.question_id}"
            )
        result = AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=answer,
            metadata={
                "answer_reader": "framework",
                "answer_model": self.client.model_name,
                "answer_prompt_profile": retrieval.metadata.get(
                    "answer_prompt_profile",
                    retrieval.metadata.get("prompt_profile", "method_owned"),
                ),
            },
        )
        return result, prompt, response


class OpenAICompatibleAnswerLLMClient:
    """OpenAI-compatible answer LLM client。

    该类只负责把 framework reader 渲染好的 prompt 交给 OpenAI-compatible
    chat completions API。API key、base URL、timeout 和 retry 都来自配置层。
    """

    def __init__(
        self,
        *,
        settings: OpenAISettings,
        answer_settings: AnswerLLMSettings | None = None,
    ) -> None:
        """初始化 OpenAI-compatible client。

        输入:
            settings: `.env` 和默认配置解析后的 OpenAI-compatible API 配置。
            answer_settings: answer LLM 的显式请求参数；为空时使用保守默认值。

        输出:
            None。内部创建 OpenAI SDK client，但不立即发起网络请求。
        """

        self.settings = settings
        self.answer_settings = answer_settings or AnswerLLMSettings(
            model=settings.model
        )
        self.model_name = self.answer_settings.model
        self._client = OpenAI(
            **self.answer_settings.to_client_kwargs(settings)
        )

    def complete_with_metadata(self, *, prompt: str) -> AnswerLLMResponse:
        """调用 chat completions API，并保留 usage 供效率观测。

        输入:
            prompt: framework reader 渲染后的完整 answer prompt。

        输出:
            AnswerLLMResponse: 文本、usage 和原始 response。
        """

        response = self._client.chat.completions.create(
            model=self.answer_settings.model,
            messages=[
                {
                    "role": self.answer_settings.message_role,
                    "content": prompt,
                }
            ],
            **self.answer_settings.to_request_kwargs(),
        )
        content = response.choices[0].message.content
        return AnswerLLMResponse(
            text="" if content is None else str(content),
            usage=getattr(response, "usage", None),
            raw_response=response,
        )

    def complete(self, *, prompt: str) -> str:
        """调用 chat completions API 并返回纯文本回答。"""

        return self.complete_with_metadata(prompt=prompt).text

    def complete_messages_with_metadata(
        self,
        *,
        messages: list[PromptMessage],
    ) -> AnswerLLMResponse:
        """调用 chat completions API，直接保留 method 返回的 role messages。"""

        response = self._client.chat.completions.create(
            model=self.answer_settings.model,
            messages=[message.to_dict() for message in messages],
            **self.answer_settings.to_request_kwargs(),
        )
        content = response.choices[0].message.content
        return AnswerLLMResponse(
            text="" if content is None else str(content),
            usage=getattr(response, "usage", None),
            raw_response=response,
        )


def load_answer_prompt_template(
    *,
    project_root: Path,
    prompt_file: str | Path | None,
    profile_name: str,
) -> AnswerPromptTemplate:
    """读取默认或用户自定义 answer prompt。

    输入:
        project_root: 项目根目录；相对 prompt 路径基于该目录解析。
        prompt_file: 可选自定义 prompt 文件。文件内容必须包含 `{question}` 和
            `{memory_context}`。
        profile_name: 写入 answer metadata/manifest 的 prompt profile 名称。

    输出:
        AnswerPromptTemplate: 已校验核心占位符的 prompt 模板。
    """

    if prompt_file is None:
        return AnswerPromptTemplate(profile_name=profile_name)

    path = Path(prompt_file).expanduser()
    if not path.is_absolute():
        path = project_root / path
    return AnswerPromptTemplate(
        template=path.read_text(encoding="utf-8"),
        profile_name=profile_name,
    )


class FakeAnswerLLMClient:
    """测试用 LLM client，记录 prompt 并返回固定文本。"""

    model_name = "fake-answer-llm"

    def __init__(self, answer: str) -> None:
        """初始化 fake client。

        输入:
            answer: 每次 `complete()` 返回的固定答案。

        输出:
            None。`calls` 会记录每次传入的 prompt。
        """

        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, prompt: str) -> str:
        """记录 prompt 并返回固定答案。"""

        self.calls.append({"prompt": prompt})
        return self.answer

    def complete_messages_with_metadata(
        self,
        *,
        messages: list[PromptMessage],
    ) -> AnswerLLMResponse:
        """记录 role messages 并返回固定答案。"""

        prompt = "\n\n".join(
            f"[{message.role}]\n{message.content}" for message in messages
        )
        self.calls.append(
            {
                "prompt": prompt,
                "messages": [message.to_dict() for message in messages],
            }
        )
        return AnswerLLMResponse(text=self.answer)


def _complete_answer_client(
    client: AnswerLLMClient,
    *,
    prompt: str,
    prompt_messages: list[PromptMessage],
) -> AnswerLLMResponse:
    """兼容旧 `complete()` client 和新 `complete_with_metadata()` client。"""

    complete_messages_with_metadata = getattr(
        client,
        "complete_messages_with_metadata",
        None,
    )
    if callable(complete_messages_with_metadata):
        response = complete_messages_with_metadata(messages=prompt_messages)
        if not isinstance(response, AnswerLLMResponse):
            raise ConfigurationError(
                "complete_messages_with_metadata() must return AnswerLLMResponse"
            )
        return response
    complete_with_metadata = getattr(client, "complete_with_metadata", None)
    if callable(complete_with_metadata):
        response = complete_with_metadata(prompt=prompt)
        if not isinstance(response, AnswerLLMResponse):
            raise ConfigurationError(
                "complete_with_metadata() must return AnswerLLMResponse"
            )
        return response
    return AnswerLLMResponse(text=client.complete(prompt=prompt))

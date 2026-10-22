"""框架统一回答生成器 (`FrameworkAnswerReader`)。

职责边界：
1. 接收 `MemoryProvider.retrieve()` 返回的纯文本 `formatted_memory` 与公开 `Question`；
2. 从 `configs/application.yaml` 注入的 `PromptProperties` 模板渲染生成 Prompt（代码与 Prompt 数据分离）；
3. 调用 `llm.answer` 配置对应的 OpenAI 兼容客户端（或本地测试 `FakeAnswerLLMClient`）生成 `AnswerResult`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import OpenAI

from memory_benchmark.core import (
    AnswerPromptResult,
    AnswerResult,
    ConfigurationError,
    LLMProperties,
    PromptMessage,
    PromptProperties,
    Question,
    RetrievePayload,
    build_prompt_variable_pool,
    format_prompt_messages,
    format_prompt_template,
)


class AnswerLLMClient(Protocol):
    """FrameworkAnswerReader 使用的最小 LLM 客户端协议。"""

    model_name: str

    def complete(self, *, prompt: str) -> str:
        """输入完整 Prompt，返回模型生成的文本回答。"""


@dataclass(frozen=True)
class AnswerLLMResponse:
    """Answer LLM 的标准返回封装。"""

    text: str
    usage: Any | None = None
    raw_response: Any | None = None
    api_called: bool = True


def _format_options_text(options: dict[str, str] | None) -> str:
    if not options:
        return ""
    return "\n".join(f"{k}. {v}" for k, v in sorted(options.items()))


@dataclass
class FrameworkAnswerReader:
    """基于配置化 `PromptProperties` 的统一回答生成器。"""

    client: AnswerLLMClient
    prompts: PromptProperties = field(default_factory=PromptProperties)

    def build_prompt(
        self,
        question: Question,
        payload: RetrievePayload,
    ) -> AnswerPromptResult:
        """使用 `PromptProperties` 渲染当前问题的针对性 System + User 消息。"""
        template = self.prompts.get_answer_user(question.category)
        variables = build_prompt_variable_pool(
            question_text=question.text,
            memory_context=payload.formatted_memory,
            question_time=question.question_time or "",
            conversation_id=question.conversation_id,
            category=question.category or "",
            options=question.options,
            extra=question.metadata,
        )
        user_content = format_prompt_template(template, variables).strip()
        system_content = format_prompt_template(self.prompts.answer_system, variables).strip()

        messages: list[PromptMessage] = []
        if system_content:
            messages.append(PromptMessage(role="system", content=system_content))
        messages.append(PromptMessage(role="user", content=user_content))
        return AnswerPromptResult(
            conversation_id=question.conversation_id,
            question_id=question.question_id,
            answer_prompt=format_prompt_messages(messages),
            prompt_messages=messages,
        )

    def generate_answer(
        self,
        *,
        question: Question,
        retrieval: AnswerPromptResult,
    ) -> AnswerResult:
        """基于渲染好的 `AnswerPromptResult` 调用 Answer LLM 生成回答。"""
        if not retrieval.prompt_messages:
            raise ConfigurationError(f"Empty prompt_messages for question '{question.question_id}'")

        complete_msgs = getattr(self.client, "complete_messages_with_metadata", None)
        if callable(complete_msgs):
            resp = complete_msgs(messages=retrieval.prompt_messages)
            answer_text = resp.text.strip()
        else:
            answer_text = self.client.complete(prompt=retrieval.answer_prompt).strip()

        if not answer_text:
            raise ConfigurationError(f"Answer reader returned empty answer for '{question.question_id}'")

        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=answer_text,
            metadata={
                "answer_reader": "framework",
                "answer_model": self.client.model_name,
            },
        )


class OpenAICompatibleAnswerLLMClient:
    """基于 `LLMProperties` (`llm.answer`) 的 OpenAI 兼容回答生成客户端。"""

    def __init__(self, settings: LLMProperties) -> None:
        self.settings = settings
        self.model_name = settings.model
        self._client = OpenAI(
            api_key=settings.require_api_key(),
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )

    def complete_messages_with_metadata(
        self,
        *,
        messages: list[PromptMessage],
    ) -> AnswerLLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.settings.temperature,
        }
        if self.settings.max_tokens and self.settings.max_tokens > 0:
            kwargs["max_tokens"] = self.settings.max_tokens

        response = self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return AnswerLLMResponse(
            text="" if content is None else str(content),
            usage=getattr(response, "usage", None),
            raw_response=response,
        )

    def complete(self, *, prompt: str) -> str:
        return self.complete_messages_with_metadata(
            messages=[PromptMessage(role="user", content=prompt)]
        ).text


class FakeAnswerLLMClient:
    """零外部依赖的确定性测试 LLM 客户端。"""

    model_name = "fake-answer-llm"

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, prompt: str) -> str:
        self.calls.append({"prompt": prompt})
        return self.answer

    def complete_messages_with_metadata(
        self,
        *,
        messages: list[PromptMessage],
    ) -> AnswerLLMResponse:
        prompt = format_prompt_messages(messages)
        self.calls.append(
            {
                "prompt": prompt,
                "messages": [m.to_dict() for m in messages],
            }
        )
        return AnswerLLMResponse(text=self.answer)


__all__ = [
    "AnswerLLMClient",
    "AnswerLLMResponse",
    "FakeAnswerLLMClient",
    "FrameworkAnswerReader",
    "OpenAICompatibleAnswerLLMClient",
]

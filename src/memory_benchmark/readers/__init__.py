"""回答生成模块 (`readers`) 统一导出入口。"""

from .answer import (
    AnswerLLMClient,
    AnswerLLMResponse,
    FakeAnswerLLMClient,
    FrameworkAnswerReader,
    OpenAICompatibleAnswerLLMClient,
)

__all__ = [
    "AnswerLLMClient",
    "AnswerLLMResponse",
    "FakeAnswerLLMClient",
    "FrameworkAnswerReader",
    "OpenAICompatibleAnswerLLMClient",
]

"""核心数据实体定义。

本模块只定义纯数据对象，不读取文件、不调用模型、不计算指标。核心层级是：
Dataset -> Conversation -> Session -> Turn，以及公开 Question 和私有
GoldAnswerInfo 的强隔离。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .capabilities import UnifiedCapability


@dataclass
class ImageRef:
    """多模态图片引用。"""

    image_id: str | None = None
    path: str | None = None
    caption: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class Turn:
    """单条发言，即一个 speaker 的一次 content。"""

    turn_id: str
    speaker: str
    content: str
    normalized_role: str | None = None
    turn_time: str | None = None
    images: list[ImageRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class Session:
    """一次有边界的对话 session。"""

    session_id: str
    turns: list[Turn] = field(default_factory=list)
    session_time: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    private_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 method 可见的 JSON。不含 private_metadata。"""

        return {
            "session_id": self.session_id,
            "turns": [turn.to_dict() for turn in self.turns],
            "session_time": self.session_time,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "metadata": self.metadata,
        }


@dataclass
class Question:
    """method 可见的公开问题（绝不包含标准答案或评分标签）。"""

    question_id: str
    conversation_id: str
    text: str
    question_time: str | None = None
    category: str | None = None
    capability: UnifiedCapability | str | None = None
    options: dict[str, str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def unified_capability(self) -> UnifiedCapability | None:
        """返回解析后的统一能力枚举。"""
        if isinstance(self.capability, UnifiedCapability):
            return self.capability
        if isinstance(self.capability, str):
            try:
                return UnifiedCapability(self.capability)
            except ValueError:
                return None
        return None

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""
        data = asdict(self)
        if isinstance(self.capability, UnifiedCapability):
            data["capability"] = self.capability.value
        return data


@dataclass
class GoldAnswerInfo:
    """evaluator 可见的私有标准答案信息（严禁传给被测 method）。"""

    question_id: str
    answer: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return {
            "question_id": self.question_id,
            "answer": self.answer,
            "metadata": self.metadata,
        }


@dataclass
class Conversation:
    """一个独立记忆隔离空间下的完整对话与问题集。"""

    conversation_id: str
    sessions: list[Session] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    gold_answers: dict[str, GoldAnswerInfo] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        """导出 method 可见内容，物理剥离 gold_answers。"""

        return {
            "conversation_id": self.conversation_id,
            "sessions": [session.to_dict() for session in self.sessions],
            "questions": [question.to_dict() for question in self.questions],
            "metadata": self.metadata,
        }

    def to_dict(self) -> dict[str, Any]:
        """导出完整内容，仅用于 evaluator。"""

        return asdict(self)


@dataclass
class Dataset:
    """一次加载得到的统一数据集。"""

    dataset_name: str
    conversations: list[Conversation] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        """导出 method 可见数据集，不包含任何 gold_answers。"""

        return {
            "dataset_name": self.dataset_name,
            "conversations": [
                conversation.to_public_dict() for conversation in self.conversations
            ],
            "metadata": self.metadata,
        }

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class PromptMessage:
    """交给 answer LLM 的一条 role message。"""

    role: str
    content: str

    def __post_init__(self) -> None:
        """校验 message role 和内容非空。"""

        if self.role not in {"system", "user", "assistant"}:
            raise ValueError(
                "PromptMessage role must be one of: system, user, assistant"
            )
        if not self.content.strip():
            raise ValueError("PromptMessage content must not be blank")

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


def format_prompt_messages(messages: list[PromptMessage]) -> str:
    """把 role messages 转换为可读文本视图。"""

    return "\n\n".join(
        f"[{message.role}]\n{message.content}" for message in messages
    )


@dataclass
class AnswerPromptResult:
    """构造好的完整 answer prompt messages。"""

    question_id: str
    conversation_id: str
    answer_prompt: str = ""
    prompt_messages: list[PromptMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """自动同步 prompt_messages 与文本视图。"""

        if self.prompt_messages:
            if not self.answer_prompt.strip():
                self.answer_prompt = format_prompt_messages(self.prompt_messages)
            return
        if self.answer_prompt.strip():
            self.prompt_messages = [
                PromptMessage(role="user", content=self.answer_prompt)
            ]

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class AnswerResult:
    """对公开 Question 生成的最终回答。"""

    question_id: str
    conversation_id: str
    answer: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class MetricResult:
    """单题或聚合评测指标结果。"""

    metric_name: str
    score: float
    is_correct: bool | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class EvaluationResult:
    """一次 evaluation 的聚合结果。"""

    dataset_name: str
    total_questions: int
    metrics: dict[str, Any] = field(default_factory=dict)
    detailed_results: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)

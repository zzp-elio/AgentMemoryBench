"""conversation-QA v2 核心数据实体。

本模块只定义纯数据对象，不读取文件、不调用模型、不计算指标。核心层级是：
Dataset -> Conversation -> Session -> Turn，以及公开 Question 和私有
GoldAnswerInfo 的强隔离。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ImageRef:
    """多模态图片引用。

    字段:
        image_id: benchmark 内部图片 id。
        path: 本地图片路径。
        caption: 文本 fallback。
        metadata: 图片级公开元信息。
    """

    image_id: str | None = None
    path: str | None = None
    caption: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class Turn:
    """单条发言，即一个 speaker 的一次 content。

    `speaker` 是原始说话人；`normalized_role` 是可选标准角色，不能替代 speaker。
    """

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

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class Question:
    """method 可见的公开问题。

    注意：这里绝不能包含 gold answer、evidence 或 judge label。
    """

    question_id: str
    conversation_id: str
    text: str
    question_time: str | None = None
    category: str | None = None
    options: dict[str, str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class GoldAnswerInfo:
    """evaluator 可见的私有标准答案信息。

    该对象只能进入 evaluator、日志或结果审计，不能传给 method。
    """

    question_id: str
    answer: str
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class Conversation:
    """一个独立 memory namespace 下的长期 conversation。"""

    conversation_id: str
    sessions: list[Session] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    gold_answers: dict[str, GoldAnswerInfo] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        """导出 method 可见内容，不包含 gold_answers。"""

        return {
            "conversation_id": self.conversation_id,
            "sessions": [session.to_dict() for session in self.sessions],
            "questions": [question.to_dict() for question in self.questions],
            "metadata": self.metadata,
        }

    def to_dict(self) -> dict[str, Any]:
        """导出完整内容，仅用于 evaluator/debug。"""

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
class AddResult:
    """method 写入 conversation 后的最小结果。"""

    conversation_ids: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class RetrievedMemory:
    """method 返回的一条相关记忆。"""

    content: str
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class RetrievalResult:
    """检索能力输出，Phase 1 runner 不强制使用。"""

    question_id: str
    conversation_id: str
    memories: list[RetrievedMemory] = field(default_factory=list)
    formatted_context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class AnswerResult:
    """method 对公开 Question 的回答。"""

    question_id: str
    conversation_id: str
    answer: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class MetricResult:
    """单题或聚合 metric 结果。"""

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

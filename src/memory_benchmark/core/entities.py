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
    private_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """返回 method 可见的 JSON 可序列化字典。"""

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


GOLD_EVIDENCE_CONTRACT_V1 = "v1"
_GOLD_EVIDENCE_MAPPING_STATUSES = ("mapped", "unmatched")
_GOLD_EVIDENCE_GRANULARITIES = ("turn", "session")


def _require_exact_identifier(value: object, field_name: str) -> str:
    """强校验 gold evidence 标识符：严格 str、非空、未 strip 前后等价。

    输入:
        value: 待校验的原始标识符。
        field_name: 报错时的字段定位名。

    输出:
        str: 校验通过后的原值，不做任何宽松正规化。
    """

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a str, got {type(value).__name__}")
    if not value or value != value.strip():
        raise ValueError(
            f"{field_name} must be a non-blank string without leading/trailing "
            f"whitespace, got {value!r}"
        )
    return value


@dataclass(frozen=True)
class GoldEvidenceGroup:
    """一个官方 gold evidence unit 到 canonical child ids 的私有映射组。

    该对象只能进入 evaluator 私有通道，绝不能进入 method 可见 payload。
    `mapping_status="mapped"` 表示官方 unit 至少映射到一个 canonical child，
    命中任一 child 即该 unit 命中一次；`"unmatched"` 表示官方 unit 存在但无法
    映射到任何 canonical child，留在分母中永远 miss。
    """

    unit_id: str
    child_ids: tuple[str, ...]
    mapping_status: str

    def __post_init__(self) -> None:
        """运行时 fail-fast 校验，不依赖 annotation。"""

        _require_exact_identifier(self.unit_id, "GoldEvidenceGroup.unit_id")
        if self.mapping_status not in _GOLD_EVIDENCE_MAPPING_STATUSES:
            raise ValueError(
                "GoldEvidenceGroup.mapping_status must be one of "
                f"{_GOLD_EVIDENCE_MAPPING_STATUSES}, got {self.mapping_status!r}"
            )
        if not isinstance(self.child_ids, tuple):
            raise ValueError(
                "GoldEvidenceGroup.child_ids must be a tuple, got "
                f"{type(self.child_ids).__name__}"
            )
        seen_child_ids: set[str] = set()
        for child_id in self.child_ids:
            _require_exact_identifier(child_id, "GoldEvidenceGroup.child_ids item")
            if child_id in seen_child_ids:
                raise ValueError(
                    f"GoldEvidenceGroup child_ids must be unique, got duplicate {child_id!r}"
                )
            seen_child_ids.add(child_id)
        if self.mapping_status == "mapped" and not self.child_ids:
            raise ValueError(
                f"mapped GoldEvidenceGroup {self.unit_id!r} requires at least one child id"
            )
        if self.mapping_status == "unmatched" and self.child_ids:
            raise ValueError(
                f"unmatched GoldEvidenceGroup {self.unit_id!r} must have zero child ids"
            )

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典（child_ids 序列化为 list）。"""

        return {
            "unit_id": self.unit_id,
            "child_ids": list(self.child_ids),
            "mapping_status": self.mapping_status,
        }


@dataclass(frozen=True)
class GoldEvidenceGroupSet:
    """同一题在一个 (granularity, unit_kind) view 下的全部 gold groups。

    `groups=()` 合法，表示该 view 存在但确实没有 gold unit。
    """

    provenance_granularity: str
    unit_kind: str
    groups: tuple[GoldEvidenceGroup, ...]

    def __post_init__(self) -> None:
        """运行时 fail-fast 校验，不依赖 annotation。"""

        if self.provenance_granularity not in _GOLD_EVIDENCE_GRANULARITIES:
            raise ValueError(
                "GoldEvidenceGroupSet.provenance_granularity must be one of "
                f"{_GOLD_EVIDENCE_GRANULARITIES}, got {self.provenance_granularity!r}"
            )
        _require_exact_identifier(self.unit_kind, "GoldEvidenceGroupSet.unit_kind")
        if not isinstance(self.groups, tuple):
            raise ValueError(
                "GoldEvidenceGroupSet.groups must be a tuple, got "
                f"{type(self.groups).__name__}"
            )
        seen_unit_ids: set[str] = set()
        for group in self.groups:
            if not isinstance(group, GoldEvidenceGroup):
                raise ValueError(
                    "GoldEvidenceGroupSet.groups items must be GoldEvidenceGroup, "
                    f"got {type(group).__name__}"
                )
            if group.unit_id in seen_unit_ids:
                raise ValueError(
                    "GoldEvidenceGroupSet unit ids must be unique, got duplicate "
                    f"{group.unit_id!r}"
                )
            seen_unit_ids.add(group.unit_id)

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典（groups 序列化为 list）。"""

        return {
            "provenance_granularity": self.provenance_granularity,
            "unit_kind": self.unit_kind,
            "groups": [group.to_dict() for group in self.groups],
        }


@dataclass
class GoldAnswerInfo:
    """evaluator 可见的私有标准答案信息。

    该对象只能进入 evaluator、日志或结果审计，不能传给 method。
    `evidence` 是历史扁平 qrel，仅保留答案/历史兼容用途；迁移到 gold evidence
    contract v1 后，retrieval evaluator 的权威 qrel 是 `evidence_group_sets`。
    """

    question_id: str
    answer: str
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    gold_evidence_contract_version: str | None = None
    evidence_group_sets: tuple[GoldEvidenceGroupSet, ...] = ()

    def __post_init__(self) -> None:
        """强校验 gold evidence contract 版本与 group set views。"""

        if self.gold_evidence_contract_version not in (None, GOLD_EVIDENCE_CONTRACT_V1):
            raise ValueError(
                "GoldAnswerInfo.gold_evidence_contract_version must be None or "
                f"{GOLD_EVIDENCE_CONTRACT_V1!r}, got "
                f"{self.gold_evidence_contract_version!r}"
            )
        if not isinstance(self.evidence_group_sets, tuple):
            raise ValueError(
                "GoldAnswerInfo.evidence_group_sets must be a tuple, got "
                f"{type(self.evidence_group_sets).__name__}"
            )
        seen_views: set[tuple[str, str]] = set()
        for group_set in self.evidence_group_sets:
            if not isinstance(group_set, GoldEvidenceGroupSet):
                raise ValueError(
                    "GoldAnswerInfo.evidence_group_sets items must be "
                    f"GoldEvidenceGroupSet, got {type(group_set).__name__}"
                )
            view = (group_set.provenance_granularity, group_set.unit_kind)
            if view in seen_views:
                raise ValueError(
                    "GoldAnswerInfo evidence_group_sets views must be unique, got "
                    f"duplicate {view!r}"
                )
            seen_views.add(view)
        if (
            self.evidence_group_sets
            and self.gold_evidence_contract_version != GOLD_EVIDENCE_CONTRACT_V1
        ):
            raise ValueError(
                "GoldAnswerInfo with evidence_group_sets requires "
                f"gold_evidence_contract_version={GOLD_EVIDENCE_CONTRACT_V1!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典（group sets 序列化为 list）。"""

        return {
            "question_id": self.question_id,
            "answer": self.answer,
            "evidence": list(self.evidence),
            "metadata": self.metadata,
            "gold_evidence_contract_version": self.gold_evidence_contract_version,
            "evidence_group_sets": [
                group_set.to_dict() for group_set in self.evidence_group_sets
            ],
        }


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
class PromptMessage:
    """交给 answer LLM 的一条 role message。

    字段:
        role: chat completion 角色，例如 `system`、`user`、`assistant`。
        content: 当前 role 下的 prompt 内容，不能为空。
    """

    role: str
    content: str

    def __post_init__(self) -> None:
        """强校验 message role 和内容，避免静默构造无效 prompt。"""

        if self.role not in {"system", "user", "assistant"}:
            raise ValueError(
                "PromptMessage role must be one of: system, user, assistant"
            )
        if not self.content.strip():
            raise ValueError("PromptMessage content must not be blank")

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化字典。"""

        return asdict(self)


@dataclass
class AnswerPromptResult:
    """method 构造好的完整 answer prompt messages。

    字段:
        question_id: 当前问题 id，必须与公开 Question 对齐。
        conversation_id: 当前 conversation id，必须与公开 Question 对齐。
        prompt_messages: method 内部完成检索、记忆格式化和 prompt 拼接后的完整 role
            messages，是 framework answer LLM 的主输入。
        answer_prompt: prompt_messages 的兼容文本视图；旧 artifact 和旧测试可以继续读取。
        metadata: 公开诊断信息；可放 answer_context、retrieved_memories、raw_items_ref
            等 method-specific 调试内容，但不能包含 gold/evidence/secret。
    """

    question_id: str
    conversation_id: str
    answer_prompt: str = ""
    prompt_messages: list[PromptMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """在迁移期兼容旧 answer_prompt，同时优先使用 prompt_messages。"""

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


def format_prompt_messages(messages: list[PromptMessage]) -> str:
    """把 role messages 转换为可读文本视图。

    输入:
        messages: 已校验的 prompt message 列表。

    输出:
        str: 带 role 标记的 prompt 文本，仅用于兼容 artifact、日志和 token 估算。
    """

    return "\n\n".join(
        f"[{message.role}]\n{message.content}" for message in messages
    )


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

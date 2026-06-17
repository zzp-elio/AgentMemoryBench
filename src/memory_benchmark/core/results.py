"""运行结果结构。

本模块放框架级结果对象。当前只有 loader dry-run 摘要，完整 evaluation
result 使用 `entities.EvaluationResult`。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class DryRunSummary:
    """conversation-QA loader-only dry-run 的摘要。

    字段:
        benchmark: benchmark 名称。
        conversation_count: 本次 dry-run 实际读取的 conversation 数。
        sample_conversation_ids: 抽样 conversation id。
        total_sessions: 抽样 conversation 中 session 总数。
        total_turns: 抽样 conversation 中 turn 总数。
        total_questions: 抽样 conversation 中 question 总数。
    """

    benchmark: str
    conversation_count: int
    sample_conversation_ids: list[str] = field(default_factory=list)
    total_sessions: int = 0
    total_turns: int = 0
    total_questions: int = 0

    def to_dict(self) -> dict:
        """转换为可序列化字典。

        输入:
            无，使用当前 summary 字段。

        输出:
            dict: 可直接 JSON 序列化的 dry-run 摘要。
        """

        return asdict(self)

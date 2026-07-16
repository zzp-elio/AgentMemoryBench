"""实验产物记录结构转换工具。

本模块把核心实体转换为 JSONL 友好的公开问题记录和 evaluator-only 私有标签记录。
"""

from __future__ import annotations

from typing import Any

from memory_benchmark.core import GOLD_EVIDENCE_CONTRACT_V1, GoldAnswerInfo, Question
from memory_benchmark.core.validators import validate_no_private_keys


def public_question_record(question: Question) -> dict[str, Any]:
    """生成 method 可见的公开问题记录，并阻断私有字段泄漏。

    输入:
        question: 不含 gold answer、evidence 或 judge label 的公开问题。

    输出:
        dict[str, Any]: 可写入 `public_questions.jsonl` 的公开字段。

    异常:
        DataLeakageError: metadata 或其它公开字段中出现私有评测键。
    """

    record = {
        "question_id": question.question_id,
        "conversation_id": question.conversation_id,
        "question_text": question.text,
        "question_time": question.question_time,
        "category": question.category,
        "metadata": question.metadata,
    }
    validate_no_private_keys(record)
    return record


def evaluator_private_label_record(
    gold: GoldAnswerInfo, category: str | None
) -> dict[str, Any]:
    """生成 evaluator-only 私有标签记录，绝不能传给 method。

    输入:
        gold: 私有标准答案信息，包含 gold answer、evidence 和审计 metadata。
        category: 题目类别；可为空以保留原始数据缺失状态。

    输出:
        dict[str, Any]: 仅供 evaluator、审计日志和结果文件使用的私有字段。

    说明:
        这是明确的 evaluator 私有边界，因此允许保留 gold_answer 和 evidence。
        gold evidence contract v1 的 label 顶层额外携带
        `gold_evidence_contract_version` 与 JSON list 形态的
        `evidence_group_sets`；旧无版本 gold 保持旧 shape，不凭空加字段。
    """

    record = {
        "question_id": gold.question_id,
        "gold_answer": gold.answer,
        "category": category,
        "evidence": gold.evidence,
        "metadata": gold.metadata,
    }
    if gold.gold_evidence_contract_version == GOLD_EVIDENCE_CONTRACT_V1:
        record["gold_evidence_contract_version"] = GOLD_EVIDENCE_CONTRACT_V1
        record["evidence_group_sets"] = [
            group_set.to_dict() for group_set in gold.evidence_group_sets
        ]
    return record

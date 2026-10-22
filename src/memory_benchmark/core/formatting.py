r"""Prompt 模板安全变量注入与格式化引擎。
设计目标：
1. **零未赋值残留（Zero Unfilled Variables）**：提供全面的富变量别名池（涵盖 question/context/date/gold/prediction 等各类官方命名），确保渲染后无任何 `{...}` 残留；
2. **防 JSON 语法大括号冲突**：利用精准标识符正则 `\{([A-Za-z_][A-Za-z0-9_]*)\}` 进行替换，100% 免疫 JSON 结构体中的 `{"reason": ...}` 符号，绝不抛出 KeyError 或格式化异常。
"""

from __future__ import annotations

import re
from typing import Any

_VAR_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def build_prompt_variable_pool(
    *,
    question_text: str = "",
    memory_context: str = "",
    question_time: str = "",
    gold_answer: str = "",
    predicted_answer: str = "",
    conversation_id: str = "",
    category: str = "",
    options: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    """构建覆盖 5 大基准及其原生题型所有同义别名的富参数池。"""
    options_map = options or {}
    options_text = (
        "\n".join(f"{k}. {v}" for k, v in sorted(options_map.items()))
        if options_map
        else ""
    )

    q_time = str(question_time or "").strip()
    mem = str(memory_context or "").strip()
    q_txt = str(question_text or "").strip()
    g_ans = str(gold_answer or "").strip()
    p_ans = str(predicted_answer or "").strip()

    pool: dict[str, str] = {
        # 1. 记忆上下文同义别名
        "memory_context": mem,
        "formatted_memory": mem,
        "context": mem,
        "memory": mem,
        "memories": mem,
        "History_Chats": mem,
        "history_chats": mem,
        "chats": mem,
        "history": mem,
        # 2. 问题文本同义别名
        "question": q_txt,
        "text": q_txt,
        "query": q_txt,
        # 3. 提问时间锚点同义别名
        "question_time": q_time or "N/A",
        "date": q_time or "N/A",
        "time": q_time or "N/A",
        "Current_Date": q_time or "N/A",
        "current_date": q_time or "N/A",
        # 4. 标准答案同义别名
        "gold_answer": g_ans,
        "golden_answers": g_ans,
        "reference_answer": g_ans,
        "correct_answer": g_ans,
        "answer": g_ans,
        "expected_answer": g_ans,
        "updated_memory": g_ans,
        "original_memory": g_ans,
        # 5. 预测答案同义别名
        "predicted_answer": p_ans,
        "prediction": p_ans,
        "response": p_ans,
        "model_response": p_ans,
        "llm_response": p_ans,
        "generated_answer": p_ans,
        # 6. 选择题同义别名
        "options_text": options_text,
        "choice_A": options_map.get("A", ""),
        "choice_B": options_map.get("B", ""),
        "choice_C": options_map.get("C", ""),
        "choice_D": options_map.get("D", ""),
        # 7. 任务分类与元数据
        "conversation_id": conversation_id or "",
        "category": category or "",
    }

    if extra:
        for k, v in extra.items():
            pool[k] = str(v)
            if k == "rubric_item":
                pool["rubric"] = str(v)
            elif k == "key_memory_points":
                pool["key_points"] = str(v)

    return pool


def format_prompt_template(template: str, variables: dict[str, str]) -> str:
    """智能填充 Prompt 模板：100% 替换已知变量，绝不破坏 JSON 大括号语法。"""
    if not template:
        return ""

    # 规范化可能存在的历史尖括号或美元符占位形式（如 <question> 或 $question）
    normalized = template
    for canon in (
        "question",
        "context",
        "memory",
        "gold_answer",
        "golden_answers",
        "predicted_answer",
        "prediction",
        "rubric_item",
        "llm_response",
        "reference_answer",
        "key_memory_points",
        "response",
        "ordered_reference",
    ):
        normalized = normalized.replace(f"<{canon}>", f"{{{canon}}}")
        normalized = normalized.replace(f"${canon}", f"{{{canon}}}")

    def _replace_var(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in variables:
            return variables[key]
        key_lower = key.lower()
        for k, v in variables.items():
            if k.lower() == key_lower:
                return v
        # 未命中任何变量时，若为非声明槽位返回空串，确保 LLM 看到的 prompt 无残缺未赋值变量
        return ""

    return _VAR_PATTERN.sub(_replace_var, normalized)


__all__ = [
    "build_prompt_variable_pool",
    "format_prompt_template",
]

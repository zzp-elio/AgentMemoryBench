"""MemoryOS LoCoMo native answer prompt 的逐字 parity 测试。"""

from __future__ import annotations

import ast
from pathlib import Path

from memory_benchmark.methods.memoryos_native_prompts import (
    MEMORYOS_LOCOMO_NATIVE_SYSTEM_PROMPT,
    MEMORYOS_LOCOMO_NATIVE_USER_PROMPT,
    build_memoryos_locomo_native_answer_prompt,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _official_prompt_assignment(name: str, values: dict[str, str]) -> str:
    """从官方函数 AST 逐段渲染指定 f-string 赋值。"""

    source = (
        PROJECT_ROOT
        / "third_party/methods/MemoryOS-main/eval/main_loco_parse.py"
    ).read_text(encoding="utf-8")
    module = ast.parse(source)
    function = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "generate_system_response_with_meta"
    )
    assignment = next(
        node
        for node in function.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == name
    )
    joined = assignment.value
    assert isinstance(joined, ast.JoinedStr)
    parts: list[str] = []
    for value in joined.values:
        if isinstance(value, ast.Constant):
            parts.append(str(value.value))
        else:
            assert isinstance(value, ast.FormattedValue)
            assert isinstance(value.value, ast.Name)
            parts.append(values[value.value.id])
    return "".join(parts)


def test_memoryos_native_templates_match_official_runtime_strings() -> None:
    """system/user 模板渲染后必须与官方 AST f-string 逐字一致。"""

    values = {
        "speaker_a": "Alice",
        "speaker_b": "Bob",
        "assistant_knowledge_text": "ASSISTANT-KNOWLEDGE",
        "history_text": "HISTORY",
        "retrieval_text": "RETRIEVAL",
        "background": "BACKGROUND",
        "query": "QUESTION",
    }
    assert MEMORYOS_LOCOMO_NATIVE_SYSTEM_PROMPT.format(
        speaker_a="Alice",
        speaker_b="Bob",
        assistant_knowledge="ASSISTANT-KNOWLEDGE",
    ) == _official_prompt_assignment("system_prompt", values)
    assert MEMORYOS_LOCOMO_NATIVE_USER_PROMPT.format(
        speaker_a="Alice",
        speaker_b="Bob",
        history_text="HISTORY",
        retrieval_text="RETRIEVAL",
        background="BACKGROUND",
        question="QUESTION",
    ) == _official_prompt_assignment("user_prompt", values)


def test_memoryos_native_builder_preserves_roles_and_speaker_values() -> None:
    """builder 应返回官方 system/user 双消息并填充真实 speaker。"""

    messages = build_memoryos_locomo_native_answer_prompt(
        query_text="Where?",
        speaker_a="Alice",
        speaker_b="Bob",
        history_text="history",
        retrieval_text="retrieval",
        background="background",
        assistant_knowledge="knowledge",
    )

    assert [message.role for message in messages] == ["system", "user"]
    assert "role-playing as Bob" in messages[0].content
    assert "Recent conversation between Alice and Bob" in messages[1].content

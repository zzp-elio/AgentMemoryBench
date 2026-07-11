"""HaluMem unified answer prompt 官方逐字 parity 测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters.halumem import (
    HALUMEM_MEMZERO_OFFICIAL_SOURCE,
    HALUMEM_MEMZERO_PROMPT,
    build_halumem_unified_answer_prompt,
)
from memory_benchmark.core import PromptMessage, Question
from memory_benchmark.core.provider_protocol import RetrievalResult


pytestmark = pytest.mark.unit

_OFFICIAL_PROMPTS = (
    Path(__file__).resolve().parents[1]
    / "third_party"
    / "benchmarks"
    / "HaluMem-main"
    / "eval"
    / "prompts.py"
)


def _official_memzero_prompt() -> str:
    """运行时从官方 prompts.py AST 提取 PROMPT_MEMZERO。"""

    tree = ast.parse(_OFFICIAL_PROMPTS.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "PROMPT_MEMZERO"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            return value
    pytest.fail("official PROMPT_MEMZERO assignment not found")


def test_halumem_prompt_template_exactly_matches_official_memzero_source() -> None:
    """框架模板必须逐字等于官方 PROMPT_MEMZERO，包括全部空白。"""

    official = _official_memzero_prompt()

    assert len(official) == 2104
    assert len(HALUMEM_MEMZERO_PROMPT) == len(official)
    assert HALUMEM_MEMZERO_PROMPT == official


def test_halumem_prompt_builder_substitutes_memory_and_question_verbatim() -> None:
    """formatted_memory/question 仅替换官方槽位，不重排、不截断或再排版。"""

    memory = "RAW SESSION HEADER\n" + ("timestamp-free <> memory\n" * 5000)
    question = Question(
        question_id="user-1:s4:q1",
        conversation_id="user-1",
        text="What happened <exactly>?",
    )

    result = build_halumem_unified_answer_prompt(
        question,
        RetrievalResult(formatted_memory=memory, metadata={"provider": "probe"}),
    )
    expected = _official_memzero_prompt().format(
        context=memory,
        question=question.text,
    )

    assert result.answer_prompt == expected
    assert memory in result.answer_prompt
    assert question.text in result.answer_prompt
    assert result.answer_prompt.count(memory) == 1
    assert result.prompt_messages == [
        PromptMessage(role="user", content=result.answer_prompt)
    ]
    assert result.metadata["official_source"] == HALUMEM_MEMZERO_OFFICIAL_SOURCE

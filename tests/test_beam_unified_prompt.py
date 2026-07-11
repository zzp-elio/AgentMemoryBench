"""BEAM unified answer prompt 官方逐字 parity 测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters.beam import (
    BEAM_ANSWER_PROMPT_OFFICIAL_SOURCE,
    BEAM_ANSWER_PROMPT_TEMPLATE,
    build_beam_unified_answer_prompt,
)
from memory_benchmark.core import PromptMessage, Question
from memory_benchmark.core.provider_protocol import RetrievalResult


pytestmark = pytest.mark.unit

_OFFICIAL_PROMPTS = (
    Path(__file__).resolve().parents[1]
    / "third_party"
    / "benchmarks"
    / "BEAM"
    / "src"
    / "prompts.py"
)


def _official_rag_answer_template() -> str:
    """运行时从官方 prompts.py AST 提取 answer_generation_for_rag。"""

    tree = ast.parse(_OFFICIAL_PROMPTS.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "answer_generation_for_rag"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            return value
    pytest.fail("official answer_generation_for_rag assignment not found")


def test_beam_prompt_template_exactly_matches_official_rag_source() -> None:
    """框架模板必须逐字等于官方 RAG 模板，包括首换行和行尾空格。"""

    assert BEAM_ANSWER_PROMPT_TEMPLATE == _official_rag_answer_template()


def test_beam_prompt_builder_substitutes_memory_and_question_verbatim() -> None:
    """formatted_memory/question 只替换官方槽位，不重排、不截断。"""

    memory = "SESSION-Z\n" + ("memory block <> \n" * 5000)
    question = Question(
        question_id="beam-1:q1",
        conversation_id="beam-1",
        text="What happened <exactly>?",
    )

    result = build_beam_unified_answer_prompt(
        question,
        RetrievalResult(formatted_memory=memory, metadata={"provider": "probe"}),
    )
    expected = _official_rag_answer_template().replace("<context>", memory).replace(
        "<question>", question.text
    )

    assert result.answer_prompt == expected
    assert memory in result.answer_prompt
    assert question.text in result.answer_prompt
    assert result.prompt_messages == [
        PromptMessage(role="user", content=result.answer_prompt)
    ]
    assert result.metadata["official_source"] == BEAM_ANSWER_PROMPT_OFFICIAL_SOURCE


def test_beam_prompt_has_no_unmapped_time_or_date_slot() -> None:
    """官方 RAG 模板没有时间槽，builder 不得自行引入日期。"""

    official = _official_rag_answer_template()
    assert "<time>" not in official
    assert "<date>" not in official
    assert "Current Date" not in official


def test_beam_registration_keeps_free_text_prediction_without_transform() -> None:
    """BEAM 自由文本答案不得增加 choice/parser transform。"""

    from memory_benchmark.benchmark_adapters import get_benchmark_registration

    assert get_benchmark_registration("beam").prediction_transform is None

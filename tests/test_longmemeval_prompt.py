"""LongMemEval unified answer prompt builder 测试。"""

from __future__ import annotations

from memory_benchmark.benchmark_adapters.longmemeval_prompt import (
    LONGMEMEVAL_UNIFIED_ANSWER_PROMPT_PROFILE,
    build_longmemeval_unified_answer_prompt,
)
from memory_benchmark.core import Question
from memory_benchmark.core.provider_protocol import RetrievalResult


def _question(*, question_time: str | None) -> Question:
    """构造只含公开字段的 LongMemEval 测试问题。"""

    return Question(
        question_id="q1",
        conversation_id="q1",
        text="What drink do I like?",
        question_time=question_time,
    )


def test_longmemeval_unified_prompt_matches_official_non_cot_template() -> None:
    """builder 应逐字复刻官方非 CoT、无 fact expansion 模板。"""

    retrieval = RetrievalResult(
        formatted_memory="user: I like tea.\nassistant: Noted.",
        metadata={"provider": "fake"},
    )

    result = build_longmemeval_unified_answer_prompt(
        _question(question_time="2023/05/30 (Tue) 23:40"),
        retrieval,
    )

    expected = (
        "I will give you several history chats between you and a user. Please answer "
        "the question based on the relevant chat history.\n\n\nHistory Chats:\n\n"
        "user: I like tea.\nassistant: Noted.\n\nCurrent Date: "
        "2023/05/30 (Tue) 23:40\nQuestion: What drink do I like?\nAnswer:"
    )
    assert result.answer_prompt == expected
    assert result.prompt_messages[0].role == "user"
    assert result.prompt_messages[0].content == expected
    assert result.metadata["provider"] == "fake"
    assert result.metadata["prompt_track"] == "unified"
    assert (
        result.metadata["answer_prompt_profile"]
        == LONGMEMEVAL_UNIFIED_ANSWER_PROMPT_PROFILE
    )
    assert result.metadata["answer_context"] == retrieval.formatted_memory
    assert "run_generation.py:57" in result.metadata["official_source"]
    assert "question_date_warning" not in result.metadata


def test_longmemeval_unified_prompt_marks_missing_question_date() -> None:
    """question_date 缺失时应使用空串并在 metadata 标记 warning。"""

    result = build_longmemeval_unified_answer_prompt(
        _question(question_time=None),
        RetrievalResult(formatted_memory="memory"),
    )

    assert "Current Date: \nQuestion: What drink do I like?" in result.answer_prompt
    assert result.metadata["question_date_warning"] == "missing_question_date"


def test_longmemeval_unified_prompt_preserves_long_formatted_memory() -> None:
    """超长 formatted_memory 应原样进入 prompt，不截断或二次排版。"""

    formatted_memory = "method-owned-memory\n" * 20_000
    result = build_longmemeval_unified_answer_prompt(
        _question(question_time="2023/05/30 (Tue) 23:40"),
        RetrievalResult(formatted_memory=formatted_memory),
    )

    assert result.metadata["answer_context"] == formatted_memory
    assert f"History Chats:\n\n{formatted_memory}\n\nCurrent Date:" in result.answer_prompt
    assert "### Session" not in result.answer_prompt

"""MemBench unified answer prompt parity + choice parser edge case 测试。

本测试比较 MEMBENCH_INSTRUCTION_FIRST 与官方 MembenchAgent.py
INSTRUCTION_FIRST 的逐字文本，并在运行时从官方文件读取字符串用于水印式校验。
参照 LongMemEval C3 验收时的程序化比对法。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters.membench import (
    MEMBENCH_INSTRUCTION_FIRST,
    MEMBENCH_INSTRUCTION_FIRST_PROFILE,
    build_membench_unified_answer_prompt,
    normalize_membench_choice_prediction,
    parse_membench_choice,
)
from memory_benchmark.core import AnswerResult, PromptMessage, Question
from memory_benchmark.core.provider_protocol import RetrievalResult

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# 官方事实源路径
# ---------------------------------------------------------------------------
_OFFICIAL_MEMBENCH_AGENT = (
    Path(__file__).resolve().parents[1]
    / "third_party"
    / "benchmarks"
    / "Membench-main"
    / "benchmark"
    / "MembenchAgent.py"
)


def _official_instruction_first_text() -> str:
    """从官方 MembenchAgent.py 中提取 INSTRUCTION_FIRST 模板文本。"""
    source = _OFFICIAL_MEMBENCH_AGENT.read_text(encoding="utf-8")
    # INSTRUCTION_FIRST 从第 21 行开始，定位标志
    start_marker = 'INSTRUCTION_FIRST = """'
    start = source.find(start_marker)
    if start == -1:
        pytest.fail("Cannot find INSTRUCTION_FIRST in official MembenchAgent.py")
    start += len(start_marker)
    end = source.index('"""', start)
    return source[start:end]


def _official_source_path() -> str:
    """返回官方 MembenchAgent.py 相对路径字符串（用于 metadata 断言）。"""
    return "third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py"


# ---------------------------------------------------------------------------
# 1. Prompt 逐字 Parity 审计
# ---------------------------------------------------------------------------


class TestPromptParity:
    """MEMBENCH_INSTRUCTION_FIRST 与官方 INSTRUCTION_FIRST 逐字对照。"""

    def test_prompt_exact_match_with_official_instruction_first(self) -> None:
        """MEMBENCH_INSTRUCTION_FIRST 应与官方 INSTRUCTION_FIRST 逐字一致。"""
        official = _official_instruction_first_text()
        assert (
            MEMBENCH_INSTRUCTION_FIRST == official
        ), f"Prompt mismatch:\n--- official ---\n{official}\n--- ours ---\n{MEMBENCH_INSTRUCTION_FIRST}"

    def test_prompt_uses_instruction_first_not_third(self) -> None:
        """框架使用 INSTRUCTION_FIRST（含 "your'conversation"），非 INSTRUCTION_THIRD（"the user's messages"）。"""
        assert "your'conversation" in MEMBENCH_INSTRUCTION_FIRST
        assert "the user's messages" not in MEMBENCH_INSTRUCTION_FIRST

    def test_prompt_preserves_official_typo(self) -> None:
        """官方 "your'conversation" typo（your 与 ' 无空格）原样保留。"""
        official = _official_instruction_first_text()
        assert "your'conversation" in official
        assert "your 'conversation" not in official
        assert "your'conversation" in MEMBENCH_INSTRUCTION_FIRST

    def test_prompt_contains_four_choice_slots(self) -> None:
        """模板应包含 {choice_A} 到 {choice_D} 四个槽位。"""
        for key in ("choice_A", "choice_B", "choice_C", "choice_D"):
            assert "{" + key + "}" in MEMBENCH_INSTRUCTION_FIRST

    def test_prompt_contains_memory_slot(self) -> None:
        """模板应包含 {memory} 槽位。"""
        assert "{memory}" in MEMBENCH_INSTRUCTION_FIRST

    def test_prompt_contains_time_slot(self) -> None:
        """模板应包含 {time} 槽位。"""
        assert "{time}" in MEMBENCH_INSTRUCTION_FIRST

    def test_prompt_contains_question_slot(self) -> None:
        """模板应包含 {question} 槽位。"""
        assert "{question}" in MEMBENCH_INSTRUCTION_FIRST

    def test_prompt_has_only_one_letter_instruction(self) -> None:
        """模板应包含"only one corresponding letter"指令。"""
        assert "only one corresponding letter" in MEMBENCH_INSTRUCTION_FIRST

    def test_prompt_has_example_d(self) -> None:
        """模板应以 "Example: D" 结尾。"""
        assert MEMBENCH_INSTRUCTION_FIRST.strip().endswith("Example: D")


# ---------------------------------------------------------------------------
# 2. build_membench_unified_answer_prompt 功能测试
# ---------------------------------------------------------------------------


class TestPromptBuilder:
    """build_membench_unified_answer_prompt 构建结果测试。"""

    def _make_question(
        self,
        *,
        question_time: str | None = "2026-01-02",
        options: dict[str, str] | None = None,
    ) -> Question:
        """构造带四个 MCQ 选项的最小公开 Question fixture。"""

        return Question(
            question_id="conv-1:q1",
            conversation_id="conv-1",
            text="What will Alex choose?",
            question_time=question_time,
            options=options
            or {
                "A": "Tea",
                "B": "Coffee",
                "C": "Juice",
                "D": "Water",
            },
        )

    def test_builds_prompt_with_formatted_memory_verbatim(self) -> None:
        """formatted_memory 应原样进入 {memory} 槽位，不重排不截断。"""
        formatted_memory = "Alex said coffee is the morning choice."
        result = build_membench_unified_answer_prompt(
            self._make_question(),
            RetrievalResult(
                formatted_memory=formatted_memory,
                metadata={"provider": "fake"},
            ),
        )
        assert "Past memory: Alex said coffee is the morning choice." in result.answer_prompt
        assert result.metadata["answer_context"] == formatted_memory

    def test_builds_prompt_with_missing_question_time(self) -> None:
        """question_time 缺失时应使用空字符串。"""
        result = build_membench_unified_answer_prompt(
            self._make_question(question_time=None),
            RetrievalResult(
                formatted_memory="memory",
                metadata={},
            ),
        )
        assert "(current time is )" in result.answer_prompt

    def test_builds_prompt_four_choices_mapped_correctly(self) -> None:
        """A/B/C/D 四个选项应正确映射到 choice_A 到 choice_D 槽位。"""
        result = build_membench_unified_answer_prompt(
            self._make_question(
                options={
                    "A": "OptionA",
                    "B": "OptionB",
                    "C": "OptionC",
                    "D": "OptionD",
                }
            ),
            RetrievalResult(
                formatted_memory="mem",
                metadata={},
            ),
        )
        assert "A. OptionA" in result.answer_prompt
        assert "B. OptionB" in result.answer_prompt
        assert "C. OptionC" in result.answer_prompt
        assert "D. OptionD" in result.answer_prompt

    def test_builds_prompt_metadata_contains_profile(self) -> None:
        """metadata 应包含 answer_prompt_profile。"""
        result = build_membench_unified_answer_prompt(
            self._make_question(),
            RetrievalResult(
                formatted_memory="mem",
                metadata={"provider": "fake"},
            ),
        )
        assert result.metadata["answer_prompt_profile"] == MEMBENCH_INSTRUCTION_FIRST_PROFILE
        assert result.metadata["prompt_track"] == "unified"
        assert result.metadata["provider"] == "fake"
        assert "MembenchAgent.py:" in result.metadata["official_source"]

    def test_builds_prompt_prompt_messages_single_user(self) -> None:
        """prompt_messages 应包含一条 role=user 的消息。"""
        result = build_membench_unified_answer_prompt(
            self._make_question(),
            RetrievalResult(
                formatted_memory="mem",
                metadata={},
            ),
        )
        assert result.prompt_messages == [
            PromptMessage(role="user", content=result.answer_prompt)
        ]

    def test_builds_prompt_raises_on_missing_choice(self) -> None:
        """缺少任一 A/B/C/D 选项时应报错。"""
        with pytest.raises(Exception):
            build_membench_unified_answer_prompt(
                self._make_question(
                    options={
                        "A": "Only",
                        "B": "Two",
                        "C": "Choices",
                        # D 缺失
                    }
                ),
                RetrievalResult(
                    formatted_memory="mem",
                    metadata={},
                ),
            )


# ---------------------------------------------------------------------------
# 3. parse_membench_choice 边界测试
# ---------------------------------------------------------------------------


class TestChoiceParser:
    """parse_membench_choice 坏输出行为契约。"""

    @pytest.mark.parametrize(
        ("raw_answer", "expected"),
        [
            # 正常单字母
            ("D", "D"),
            ("A", "A"),
            # 去空白
            (" B ", "B"),
            ("  C  ", "C"),
            # 小写
            ("a", "A"),
            ("b", "B"),
            # 带标点
            ("C.", "C"),
            ("D!", "D"),
            # 前后文
            ("The answer is B.", "B"),
            ("I choose D", "D"),
            ("A sounds right", "A"),
            # 句首/句尾
            ("D is the answer", "D"),
            ("the answer is A", "A"),
            # 官方 JSON schema 格式
            ('{"choice": "D"}', "D"),
            ('{"choice": "c"}', "C"),
            ('{"choice": "B"}', "B"),
            # 纯换行
            ("D\n", "D"),
            ("\nA\n", "A"),
        ],
    )
    def test_parse_valid_choices(self, raw_answer: str, expected: str) -> None:
        """正确输出应被解析为对应大写字母。"""
        assert parse_membench_choice(raw_answer) == expected

    @pytest.mark.parametrize(
        ("raw_answer",),
        [
            pytest.param("", id="empty string"),
            pytest.param("   ", id="whitespace only"),
            pytest.param("\n\t\n", id="newlines only"),
            pytest.param("I cannot decide", id="no letter"),
            pytest.param("Maybe option E?", id="letter outside A-D"),
            pytest.param("12345", id="numbers only"),
            pytest.param("None", id="string None"),
        ],
    )
    def test_parse_invalid_choices_return_invalid_choice(self, raw_answer: str) -> None:
        """不可解析的输出应返回 invalid_choice。"""
        assert parse_membench_choice(raw_answer) == "invalid_choice"

    def test_parse_uppercase_priority_over_lowercase(self) -> None:
        """大写字母应优先于小写：独立小写 'a' 是英文冠词，不得抢在选项字母之前。"""
        # "Alex bought a bike, so the answer is C." → "C"（大写 C 优先）
        assert parse_membench_choice("Alex bought a bike, so the answer is C.") == "C"

    def test_parse_first_match_when_multiple_letters(self) -> None:
        """多字母输出应取首个匹配字母。"""
        assert parse_membench_choice("A and B") == "A"
        assert parse_membench_choice("C then D") == "C"

    def test_parse_json_with_invalid_choice(self) -> None:
        """JSON 格式中 choice 值不在 A-D 时应返回 invalid_choice。"""
        assert parse_membench_choice('{"choice": "E"}') == "invalid_choice"
        assert parse_membench_choice('{"choice": "maybe"}') == "invalid_choice"

    def test_parse_json_missing_choice_key_falls_through_to_regex(self) -> None:
        """JSON 格式但无 choice 键时回退到正则解析，仍能从文本中提取字母。"""
        assert parse_membench_choice('{"answer": "D"}') == "D"

    def test_parse_non_dict_json_fallback_to_regex(self) -> None:
        """JSON 非 dict 类型回退到正则解析，仍能从文本中提取字母。"""
        assert parse_membench_choice('["A"]') == "A"

    def test_parse_does_not_crash_on_none(self) -> None:
        """None 输入不应崩溃。"""
        result = parse_membench_choice(None)  # type: ignore[arg-type]
        assert result == "invalid_choice"

    def test_parse_does_not_crash_on_non_string(self) -> None:
        """非字符串输入不应崩溃。"""
        result = parse_membench_choice(123)  # type: ignore[arg-type]
        assert result == "invalid_choice"


# ---------------------------------------------------------------------------
# 4. normalize_membench_choice_prediction 包装测试
# ---------------------------------------------------------------------------


class TestNormalizePrediction:
    """normalize_membench_choice_prediction 包装函数行为测试。"""

    def test_normalize_records_raw_answer_in_metadata(self) -> None:
        """metadata 中应记录原始 raw_answer。"""
        transformed = normalize_membench_choice_prediction(
            AnswerResult(
                question_id="q1",
                conversation_id="conv-1",
                answer="The answer is B.",
                metadata={"source": "test"},
            )
        )
        assert transformed.metadata["raw_answer"] == "The answer is B."
        assert transformed.metadata["choice_parse_status"] == "parsed"
        assert transformed.answer == "B"

    def test_normalize_invalid_choice_sets_parse_status(self) -> None:
        """不可解析答案的 metadata 中应标记 choice_parse_status=invalid_choice。"""
        transformed = normalize_membench_choice_prediction(
            AnswerResult(
                question_id="q1",
                conversation_id="conv-1",
                answer="I cannot decide",
                metadata={},
            )
        )
        assert transformed.metadata["raw_answer"] == "I cannot decide"
        assert transformed.metadata["choice_parse_status"] == "invalid_choice"
        assert transformed.answer == "invalid_choice"

    def test_normalize_preserves_question_and_conversation_ids(self) -> None:
        """question_id、conversation_id 应保持不变。"""
        transformed = normalize_membench_choice_prediction(
            AnswerResult(
                question_id="orig-q",
                conversation_id="orig-conv",
                answer="A",
                metadata={},
            )
        )
        assert transformed.question_id == "orig-q"
        assert transformed.conversation_id == "orig-conv"

    def test_normalize_preserves_original_metadata(self) -> None:
        """原始 metadata 应保留在结果中。"""
        transformed = normalize_membench_choice_prediction(
            AnswerResult(
                question_id="q1",
                conversation_id="conv-1",
                answer="B",
                metadata={"original_key": "original_value"},
            )
        )
        assert transformed.metadata["original_key"] == "original_value"

    def test_normalize_json_choice(self) -> None:
        """JSON schema 格式需要被正确处理。"""
        transformed = normalize_membench_choice_prediction(
            AnswerResult(
                question_id="q1",
                conversation_id="conv-1",
                answer='{"choice": "C"}',
                metadata={},
            )
        )
        assert transformed.answer == "C"
        assert transformed.metadata["choice_parse_status"] == "parsed"

    def test_normalize_empty_string(self) -> None:
        """空字符串应被记为 invalid_choice。"""
        transformed = normalize_membench_choice_prediction(
            AnswerResult(
                question_id="q1",
                conversation_id="conv-1",
                answer="",
                metadata={},
            )
        )
        assert transformed.answer == "invalid_choice"
        assert transformed.metadata["choice_parse_status"] == "invalid_choice"


# ---------------------------------------------------------------------------
# 5. 负空间需求：必须报错/不得出现
# ---------------------------------------------------------------------------


class TestNegativeSpace:
    """负空间需求：本卡要求的不应出现的情况。"""

    def test_prompt_builder_requires_all_four_choices(self) -> None:
        """缺少任一选项（A/B/C/D）必须报错，不得静默忽略。"""
        for missing in ("A", "B", "C", "D"):
            options = {"A": "a", "B": "b", "C": "c", "D": "d"}
            del options[missing]
            with pytest.raises(Exception, match="choices"):
                build_membench_unified_answer_prompt(
                    Question(
                        question_id="q1",
                        conversation_id="c1",
                        text="Q?",
                        options=options,
                    ),
                    RetrievalResult(
                        formatted_memory="mem",
                        metadata={},
                    ),
                )

    def test_normalize_never_crashes_on_any_input(self) -> None:
        """normalize_membench_choice_prediction 在任何输入下都不应崩溃。"""
        bad_inputs = [
            "",
            "   ",
            "\n\n",
            "I don't know",
            "AB",
            "A and B and C",
            "maybe",
            "123",
            "None",
            "{}",
            '{"choice": null}',
            "你好",
        ]
        for bad in bad_inputs:
            transformed = normalize_membench_choice_prediction(
                AnswerResult(
                    question_id="q1",
                    conversation_id="conv-1",
                    answer=bad,
                    metadata={},
                )
            )
            # 核心约束：不崩 + 返回 answer
            assert transformed.answer in {"A", "B", "C", "D", "invalid_choice"}
            assert isinstance(transformed.metadata["raw_answer"], str)

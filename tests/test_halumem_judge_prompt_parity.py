"""HaluMem 四套官方 judge prompt 运行时 parity 测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from memory_benchmark.evaluators.halumem_prompts import (
    EVALUATION_PROMPT_FOR_MEMORY_ACCURACY,
    EVALUATION_PROMPT_FOR_MEMORY_INTEGRITY,
    EVALUATION_PROMPT_FOR_QUESTION,
    EVALUATION_PROMPT_FOR_UPDATE_MEMORY,
)


pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_OFFICIAL_PROMPTS = (
    _PROJECT_ROOT / "third_party/benchmarks/HaluMem-main/eval/eval_tools.py"
)


def _official_prompt(name: str) -> str:
    """从现场官方文件 AST 提取指定 prompt 字符串。"""

    tree = ast.parse(_OFFICIAL_PROMPTS.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            return value
    raise AssertionError(f"official prompt not found: {name}")


@pytest.mark.parametrize(
    ("name", "framework_prompt"),
    [
        ("EVALUATION_PROMPT_FOR_MEMORY_INTEGRITY", EVALUATION_PROMPT_FOR_MEMORY_INTEGRITY),
        ("EVALUATION_PROMPT_FOR_MEMORY_ACCURACY", EVALUATION_PROMPT_FOR_MEMORY_ACCURACY),
        ("EVALUATION_PROMPT_FOR_UPDATE_MEMORY", EVALUATION_PROMPT_FOR_UPDATE_MEMORY),
        ("EVALUATION_PROMPT_FOR_QUESTION", EVALUATION_PROMPT_FOR_QUESTION),
    ],
)
def test_halumem_judge_prompt_matches_official_ast_value(
    name: str,
    framework_prompt: str,
) -> None:
    """四套模板必须与 eval_tools.py 现场 AST 值逐字一致。"""

    official = _official_prompt(name)
    assert len(framework_prompt) == len(official)
    assert framework_prompt == official

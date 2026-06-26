"""测试用户自定义 method 的轻量加载入口。

本模块只验证 `--method-class module:ClassName` 底层 loader，不触碰内置 method
registry、TOML 或真实 API。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from memory_benchmark.core import AddResult, AnswerPromptResult, PromptMessage
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider
from memory_benchmark.methods.custom_loader import load_custom_memory_provider


pytestmark = pytest.mark.unit


def _write_module(tmp_path: Path, source: str) -> str:
    """写入一个临时 Python module，并返回 importable module 名。

    输入:
        tmp_path: pytest 提供的临时目录。
        source: 要写入临时 module 的 Python 源码。

    输出:
        str: 可被 import 的 module 名称。
    """

    module_path = tmp_path / "custom_adapter.py"
    module_path.write_text(source, encoding="utf-8")
    sys.modules.pop("custom_adapter", None)
    sys.path.insert(0, str(tmp_path))
    return "custom_adapter"


def test_load_custom_memory_provider_instantiates_no_arg_class(
    tmp_path: Path,
) -> None:
    """合法用户 adapter 只需无参构造并继承 BaseMemoryProvider。"""

    module_name = _write_module(
        tmp_path,
        '''
from memory_benchmark.core import AddResult, AnswerPromptResult, PromptMessage
from memory_benchmark.core.interfaces import BaseMemoryProvider


class MyMemory(BaseMemoryProvider):
    def add(self, conversation):
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question):
        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            prompt_messages=[PromptMessage(role="user", content=question.text)],
        )
''',
    )

    provider = load_custom_memory_provider(f"{module_name}:MyMemory")

    assert isinstance(provider, BaseMemoryProvider)


def test_load_custom_memory_provider_rejects_missing_colon() -> None:
    """class path 必须是 module:ClassName，避免用户传入含糊路径。"""

    with pytest.raises(ConfigurationError, match="module:ClassName"):
        load_custom_memory_provider("custom_adapter.MyMemory")


def test_load_custom_memory_provider_rejects_constructor_args(
    tmp_path: Path,
) -> None:
    """第一版用户 adapter 必须能无参数构造。"""

    module_name = _write_module(
        tmp_path,
        '''
from memory_benchmark.core.interfaces import BaseMemoryProvider


class NeedsArgs(BaseMemoryProvider):
    def __init__(self, path):
        self.path = path

    def add(self, conversation):
        raise NotImplementedError

    def retrieve(self, question):
        raise NotImplementedError
''',
    )

    with pytest.raises(ConfigurationError, match="no-argument constructor"):
        load_custom_memory_provider(f"{module_name}:NeedsArgs")


def test_load_custom_memory_provider_rejects_wrong_base_class(
    tmp_path: Path,
) -> None:
    """用户传入的类必须实现 BaseMemoryProvider。"""

    module_name = _write_module(
        tmp_path,
        '''
class NotMemory:
    pass
''',
    )

    with pytest.raises(ConfigurationError, match="BaseMemoryProvider"):
        load_custom_memory_provider(f"{module_name}:NotMemory")

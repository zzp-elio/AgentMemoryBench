"""method / memory system 抽象接口。

Phase 1 使用同步接口，只要求完整 memory system 支持 add 和 get_answer。
检索能力拆到 BaseMemoryRetriever，只有需要检索能力的 benchmark runner 才会要求。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from .entities import (
    AddResult,
    AnswerResult,
    Conversation,
    Question,
    RetrievalResult,
    Turn,
)


class BaseMemorySystem(ABC):
    """完整记忆系统接口。"""

    @abstractmethod
    def add(self, conversations: list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。

        输入:
            conversations: 已完成校验的公开 conversation 列表，不含私有 gold answers。

        输出:
            AddResult: 写入结果，只包含 conversation ids 和公开元信息。
        """

        raise NotImplementedError

    @abstractmethod
    def get_answer(self, question: Question) -> AnswerResult:
        """基于已写入的 conversation 回答公开问题。

        输入:
            question: method 可见问题，不含 gold answer/evidence。

        输出:
            AnswerResult: method 生成答案。
        """

        raise NotImplementedError


class BaseResumableMemorySystem(BaseMemorySystem):
    """可选的逐 turn 安全续写能力。

    普通 benchmark runner 仍只依赖 `BaseMemorySystem`。长 conversation runner
    可以检测该子类，并在每个 turn 前后持久化 method 私有 checkpoint。
    """

    @abstractmethod
    def add_from_turn(
        self,
        conversation: Conversation,
        start_turn_index: int,
        on_turn_started: Callable[[int, Turn], None],
        on_turn_completed: Callable[[int, Turn], None],
    ) -> AddResult:
        """从指定扁平 turn index 开始继续写入一个 conversation。

        输入:
            conversation: 已清洗的公开 conversation。
            start_turn_index: 下一条尚未确认成功的零基 turn index。
            on_turn_started: method 调用前执行的 callback。
            on_turn_completed: method 成功返回后执行的 callback。

        输出:
            AddResult: 当前 conversation 的写入结果。
        """

        raise NotImplementedError


class BaseMemoryRetriever(ABC):
    """可选记忆检索能力接口。"""

    @abstractmethod
    def retrieve(self, question: Question) -> RetrievalResult:
        """根据公开问题返回相关记忆。

        输入:
            question: method 可见问题。

        输出:
            RetrievalResult: 相关记忆。Phase 1 不把它用于 recall metric。
        """

        raise NotImplementedError

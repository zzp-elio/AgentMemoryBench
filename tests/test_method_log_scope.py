"""测试 per-run method.log 日志落盘作用域（ws04 卡 Y）。

本模块只用 fake logger / fake run（无网络、无真实 API），验证
``memory_benchmark.observability.method_log_scope`` 与 ``run_predictions`` 集成：
① ``logs/method.log`` 被创建；② 含预期的 INFO 行；③ run 结束后 root logger 上
不再残留该 FileHandler（防泄漏）；④ 被降噪的第三方 namespace 行不出现；
⑤ 两次连续 run 各写各的 ``method.log``、不串写。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from memory_benchmark.core import (
    AnswerPromptResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    PromptMessage,
    Question,
    Session,
    Turn,
)
from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core.provider_protocol import (
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    SessionRef,
    TurnEvent,
    UnitRef,
)
from memory_benchmark.observability import (
    METHOD_LOG_FILENAME,
    NOISY_THIRD_PARTY_NAMESPACES,
    RunContext,
    method_log_scope,
)
from memory_benchmark.readers.answer import FakeAnswerLLMClient, FrameworkAnswerReader
from memory_benchmark.runners.prediction import PredictionRunPolicy, run_predictions

pytestmark = pytest.mark.integration


@pytest.fixture
def _root_logger_at_info():
    """模拟真实 run 里 method（如 LightMem apply_logging）将 root 设为 INFO 的前置。

    真实 run 在 system 构造时由 method 自行把 root logger 置为 INFO（或更低），
    所以 method 自己 logger 打的 INFO 会传播到本作用域挂的 FileHandler。本
    fixture 仅在测试里复现该前置；退出时恢复 root 原级别，避免污染其他测试。
    """

    root = logging.getLogger()
    previous = root.level
    root.setLevel(logging.INFO)
    try:
        yield root
    finally:
        root.setLevel(previous)


def _root_file_handlers() -> list[logging.FileHandler]:
    """返回 root logger 当前挂载的、本作用域产生的 FileHandler 实例列表。"""

    return [
        handler
        for handler in logging.getLogger().handlers
        if isinstance(handler, logging.FileHandler)
        and Path(handler.baseFilename).name == METHOD_LOG_FILENAME
    ]


def test_method_log_scope_creates_file_and_captures_info(
    tmp_path: Path, _root_logger_at_info
) -> None:
    """作用域应创建 logs/method.log 并把 INFO 级日志写入，退出后摘掉 handler。"""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    method_logger = logging.getLogger("LightMemory")
    before_handlers = _root_file_handlers()

    with method_log_scope(log_dir):
        # 作用域内 INFO 应落入 method.log
        method_logger.info("Created 7 MemoryEntry objects")

    log_path = log_dir / METHOD_LOG_FILENAME
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "Created 7 MemoryEntry objects" in content
    assert "LightMemory" in content
    assert "INFO" in content
    # 退出作用域后 handler 必须已摘，防泄漏
    after_handlers = _root_file_handlers()
    assert len(after_handlers) == len(before_handlers)


def test_method_log_scope_filters_noisy_third_party_info(
    tmp_path: Path, _root_logger_at_info
) -> None:
    """第三方刷屏 namespace 的 INFO 应被压，但其 WARNING 应保留。"""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    noisy = logging.getLogger("httpx.core")
    retained = logging.getLogger("LightMemory")

    with method_log_scope(log_dir):
        noisy.info("noisy third party info line")  # 应被过滤
        noisy.warning("httpx real warning")  # WARNING 应保留
        retained.info("retained method info line")

    content = (log_dir / METHOD_LOG_FILENAME).read_text(encoding="utf-8")
    assert "noisy third party info line" not in content
    assert "httpx real warning" in content
    assert "retained method info line" in content


def test_method_log_scope_each_namespace_covered(
    tmp_path: Path, _root_logger_at_info
) -> None:
    """NOISY_THIRD_PARTY_NAMESPACES 中每个 namespace 的子 logger INFO 都应被压。"""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    with method_log_scope(log_dir):
        for ns in NOISY_THIRD_PARTY_NAMESPACES:
            logging.getLogger(f"{ns}.sub").info("noisy")

    content = (log_dir / METHOD_LOG_FILENAME).read_text(encoding="utf-8")
    assert "noisy" not in content


def test_method_log_scope_removes_handler_on_exception(tmp_path: Path) -> None:
    """作用域内抛异常时 finally 仍应摘 handler 并 close，防泄漏。"""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    before_handlers = _root_file_handlers()

    with pytest.raises(RuntimeError, match="boom"):
        with method_log_scope(log_dir):
            logging.getLogger("LightMemory").info("some info before boom")
            raise RuntimeError("boom")

    # 异常退出后 handler 同样不应残留
    assert len(_root_file_handlers()) == len(before_handlers)


def test_method_log_scope_two_runs_do_not_cross_write(
    tmp_path: Path, _root_logger_at_info
) -> None:
    """两次连续 run 各写各的 logs/method.log，不串写。"""

    run_a = tmp_path / "run-a" / "logs"
    run_b = tmp_path / "run-b" / "logs"
    run_a.mkdir(parents=True)
    run_b.mkdir(parents=True)

    with method_log_scope(run_a):
        logging.getLogger("LightMemory").info("run-a marker")

    with method_log_scope(run_b):
        logging.getLogger("LightMemory").info("run-b marker")

    a_content = (run_a / METHOD_LOG_FILENAME).read_text(encoding="utf-8")
    b_content = (run_b / METHOD_LOG_FILENAME).read_text(encoding="utf-8")
    assert "run-a marker" in a_content and "run-b marker" not in a_content
    assert "run-b marker" in b_content and "run-a marker" not in b_content


def test_method_log_scope_does_not_duplicate_handler_within_run(
    tmp_path: Path, _root_logger_at_info
) -> None:
    """作用域内 root logger 上同时挂的本作用域 FileHandler 应只有一份。"""

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    with method_log_scope(log_dir):
        assert len(_root_file_handlers()) == 1
        logging.getLogger("LightMemory").info("single handler line")
    assert len(_root_file_handlers()) == 0


class _LoggingV3TurnProvider(MemoryProvider):
    """在 ingest/retrieve 中向 method logger 打 INFO 的可观测 fake provider。

    复现真实 method（如 LightMem ``LightMemory``）在线程内打 INFO 的行为，用于验证
    ``run_predictions`` 把这些行落盘到 ``logs/method.log``。
    """

    consume_granularity = "turn"
    session_memory_report = False
    provenance_granularity = "turn"

    def __init__(self) -> None:
        """初始化 method logger。"""

        self._logger = logging.getLogger("LightMemory")

    def ingest(self, unit: IngestUnit) -> IngestResult:
        """记录一个 turn 单元并向 logger 打一行 INFO。"""

        if isinstance(unit, TurnEvent):
            self._logger.info("ingested turn %s", unit.turn_id)
        return IngestResult()

    def end_session(self, ref: SessionRef) -> None:  # type: ignore[override]
        """无操作；本 fake 不产 session report。"""

        return None

    def end_conversation(self, ref: UnitRef) -> None:  # type: ignore[override]
        """无操作。"""

        return None

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回最小 formatted_memory 并打一行 INFO。"""

        self._logger.info("retrieved question %s", query.query_text)
        return RetrievalResult(
            formatted_memory=f"memory for {query.query_text}",
            prompt_messages=(
                PromptMessage(role="user", content=f"memory for {query.query_text}"),
            ),
            items=(),
        )


def _build_min_dataset() -> Dataset:
    """构造单 conversation、单 turn、单 question 的最小 fake 数据集。"""

    question = Question(
        question_id="conv-1:q1",
        conversation_id="conv-1",
        text="问题 1",
    )
    conversation = Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="conv-1:s1",
                turns=[
                    Turn(
                        turn_id="conv-1:t1",
                        speaker="Speaker-1",
                        content="公开记忆 1",
                    )
                ],
            )
        ],
        questions=[question],
        gold_answers={
            question.question_id: GoldAnswerInfo(
                question_id=question.question_id,
                answer="私有答案不应落进 method.log",
                evidence=["conv-1:t1"],
            )
        },
    )
    return Dataset(dataset_name="fake-conversation-qa", conversations=[conversation])


def test_run_predictions_persists_method_log_and_removes_handler(
    tmp_path: Path,
) -> None:
    """run_predictions 应把 method logger 的 INFO 行落盘到 logs/method.log，
    且 run 结束后不在 root logger 上残留本作用域 FileHandler。"""

    context = RunContext.create(
        run_id="prediction-run",
        benchmark_name="fake-conversation-qa",
        method_name="logging-v3",
        model_name="fake-reader",
        output_root=tmp_path,
    )
    provider = _LoggingV3TurnProvider()
    reader = FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="ok"))

    expected_lines = []
    # 先把 root 提到 INFO，复现真实 run 里 method apply 的前置（见 fixture 说明）。
    root = logging.getLogger()
    previous = root.level
    root.setLevel(logging.INFO)
    try:
        handler_count_before = len(_root_file_handlers())
        summary = run_predictions(
            dataset=_build_min_dataset(),
            system=provider,
            run_context=context,
            policy=PredictionRunPolicy(max_workers=1),
            answer_reader=reader,
            method_manifest={"adapter": "logging-v3"},
            benchmark_variant="test_variant",
            run_scope=RunScope.FULL,
        )
    finally:
        root.setLevel(previous)

    method_log = context.logs_dir / METHOD_LOG_FILENAME
    assert method_log.exists(), "logs/method.log should be created by run_predictions"
    content = method_log.read_text(encoding="utf-8")
    assert "ingested turn conv-1:t1" in content
    assert "retrieved question 问题 1" in content
    assert "LightMemory" in content
    # 私有 gold 不得因观测插桩泄漏进 method.log
    assert "私有答案不应落进 method.log" not in content
    # run 结束后本作用域 FileHandler 不得残留
    assert len(_root_file_handlers()) == handler_count_before
    # 主链路结果不应因为观测插桩而改变
    assert summary.completed_questions == 1
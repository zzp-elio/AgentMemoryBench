"""成本与效率 collector 的作用域、并发和确定性测试。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
)


def test_question_scope_builds_one_question_observation() -> None:
    """同一问题的检索、上下文和回答耗时应合并为一条 question observation。"""

    collector = EfficiencyCollector(run_id="run-1", enabled=True)

    with collector.question_scope("conv-1", "q-1") as scope:
        collector.record_retrieval_result(
            latency_ms=1.5,
            injected_memory_context_tokens=17,
        )
        collector.record_answer_generation(latency_ms=2.5)

    assert len(scope.records) == 1
    payload = scope.records[0].to_dict()
    assert payload["observation_type"] == "question_efficiency"
    assert payload["conversation_id"] == "conv-1"
    assert payload["question_id"] == "q-1"
    assert payload["retrieval_latency_ms"] == 1.5
    assert payload["injected_memory_context_tokens"] == 17
    assert payload["answer_generation_latency_ms"] == 2.5


def test_question_scope_records_explicit_unsupported_retrieval() -> None:
    """无法精确拆分检索时 collector 应保存 null 和原因。"""

    collector = EfficiencyCollector(run_id="run-1", enabled=True)

    with collector.question_scope("conv-1", "q-1") as scope:
        collector.record_retrieval_unsupported("opaque end-to-end method")
        collector.record_answer_generation(latency_ms=2.5)

    payload = scope.records[0].to_dict()
    assert payload["retrieval_latency_ms"] is None
    assert payload["unsupported_reason"] == "opaque end-to-end method"


def test_question_scope_rejects_missing_retrieval_status() -> None:
    """启用 question efficiency 时必须明确给出检索耗时或 unsupported。"""

    collector = EfficiencyCollector(run_id="run-1", enabled=True)

    with pytest.raises(ConfigurationError, match="retrieval"):
        with collector.question_scope("conv-1", "q-1"):
            collector.record_answer_generation(latency_ms=2.5)


def test_question_scope_rejects_missing_answer_generation_latency() -> None:
    """每个成功回答的问题都必须记录 Answer LLM 生成耗时。"""

    collector = EfficiencyCollector(run_id="run-1", enabled=True)

    with pytest.raises(ConfigurationError, match="answer generation"):
        with collector.question_scope("conv-1", "q-1"):
            collector.record_retrieval_result(
                latency_ms=1.5,
                injected_memory_context_tokens=17,
            )


def test_conversation_scope_records_build_latency() -> None:
    """conversation scope 应保存一条记忆构建总耗时。"""

    collector = EfficiencyCollector(run_id="run-1", enabled=True)

    with collector.conversation_scope("conv-1") as scope:
        collector.record_memory_build_total_latency(latency_ms=8.25)

    assert scope.records[0].to_dict()["memory_build_total_latency_ms"] == 8.25


def test_conversation_scope_discriminator_makes_reentrant_ids_unique() -> None:
    """operation-level 路径按 session 多次进入同一 conversation scope 时，
    discriminator 让每次 observation id 唯一（避免 storage 层同 id 冲突）；不传
    discriminator 时 id 与旧行为完全一致（backward-compatible）。"""

    collector = EfficiencyCollector(run_id="run-1", enabled=True)
    with collector.conversation_scope("conv-1", scope_discriminator="s1") as first:
        collector.record_memory_build_total_latency(latency_ms=5.0)
    with collector.conversation_scope("conv-1", scope_discriminator="s2") as second:
        collector.record_memory_build_total_latency(latency_ms=7.0)

    first_obs = first.records[0]
    second_obs = second.records[0]
    assert first_obs.conversation_id == second_obs.conversation_id == "conv-1"
    assert first_obs.observation_id != second_obs.observation_id

    # discriminator=None 与不传参产生相同 id → 标准 runner 行为不变
    plain = EfficiencyCollector(run_id="run-1", enabled=True)
    with plain.conversation_scope("conv-1") as plain_scope:
        plain.record_memory_build_total_latency(latency_ms=5.0)
    explicit_none = EfficiencyCollector(run_id="run-1", enabled=True)
    with explicit_none.conversation_scope(
        "conv-1", scope_discriminator=None
    ) as none_scope:
        explicit_none.record_memory_build_total_latency(latency_ms=5.0)
    assert (
        plain_scope.records[0].observation_id
        == none_scope.records[0].observation_id
    )


def test_llm_call_uses_current_scope_and_operation_stage() -> None:
    """内部 callback 可通过当前作用域和阶段自动关联 question。"""

    collector = EfficiencyCollector(run_id="run-1", enabled=True)

    with collector.question_scope("conv-1", "q-1") as scope:
        collector.record_retrieval_unsupported("no explicit retrieval")
        collector.record_answer_generation(latency_ms=2.5)
        with collector.operation_stage(EfficiencyStage.ANSWER):
            collector.record_llm_call(
                model_id="answer-llm",
                input_tokens=31,
                output_tokens=4,
                token_measurement_source=MeasurementSource.API_USAGE,
            )

    llm_record = next(
        record
        for record in scope.records
        if record.to_dict()["observation_type"] == "llm_call"
    )
    assert llm_record.to_dict()["conversation_id"] == "conv-1"
    assert llm_record.to_dict()["question_id"] == "q-1"
    assert llm_record.to_dict()["stage"] == "answer"


def test_question_scopes_do_not_mix_records_between_threads() -> None:
    """共享 collector 的并发线程必须保持 conversation/question 完全隔离。"""

    collector = EfficiencyCollector(run_id="parallel-run", enabled=True)

    def collect(conversation_id: str, question_id: str) -> tuple[dict[str, object], ...]:
        """在当前 worker 内生成一组 question observations。"""

        with collector.question_scope(conversation_id, question_id) as scope:
            collector.record_retrieval_result(
                latency_ms=1.0,
                injected_memory_context_tokens=3,
            )
            collector.record_answer_generation(latency_ms=2.0)
            with collector.operation_stage(EfficiencyStage.ANSWER):
                collector.record_llm_call(
                    model_id="answer-llm",
                    input_tokens=5,
                    output_tokens=1,
                    token_measurement_source=MeasurementSource.API_USAGE,
                )
        return tuple(record.to_dict() for record in scope.records)

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(collect, "conv-a", "q-a")
        future_b = executor.submit(collect, "conv-b", "q-b")
        records_a = future_a.result()
        records_b = future_b.result()

    assert {record["conversation_id"] for record in records_a} == {"conv-a"}
    assert {record["question_id"] for record in records_a} == {"q-a"}
    assert {record["conversation_id"] for record in records_b} == {"conv-b"}
    assert {record["question_id"] for record in records_b} == {"q-b"}


def test_observation_ids_are_deterministic_for_same_scope_and_call_order() -> None:
    """相同 run、作用域和调用顺序应生成相同 observation id。"""

    def collect_once() -> tuple[str, ...]:
        """构造同一 question 的固定 observation 序列。"""

        collector = EfficiencyCollector(run_id="stable-run", enabled=True)
        with collector.question_scope("conv-1", "q-1") as scope:
            collector.record_retrieval_result(
                latency_ms=1.0,
                injected_memory_context_tokens=3,
            )
            collector.record_answer_generation(latency_ms=2.0)
            with collector.operation_stage(EfficiencyStage.ANSWER):
                collector.record_llm_call(
                    model_id="answer-llm",
                    input_tokens=5,
                    output_tokens=1,
                    token_measurement_source=MeasurementSource.API_USAGE,
                )
        return tuple(record.observation_id for record in scope.records)

    assert collect_once() == collect_once()


def test_disabled_collector_returns_empty_scope_and_ignores_records() -> None:
    """关闭观测时不得影响 method，也不得产生空占位 observation。"""

    collector = EfficiencyCollector(run_id="run-1", enabled=False)

    with collector.question_scope("conv-1", "q-1") as scope:
        collector.record_retrieval_result(
            latency_ms=1.0,
            injected_memory_context_tokens=3,
        )
        collector.record_answer_generation(latency_ms=2.0)

    assert scope.records == ()


def test_recording_outside_scope_fails_when_enabled() -> None:
    """启用观测时，脱离 runner 作用域的记录应立即报错。"""

    collector = EfficiencyCollector(run_id="run-1", enabled=True)

    with pytest.raises(ConfigurationError, match="scope"):
        collector.record_memory_build_total_latency(latency_ms=1.0)

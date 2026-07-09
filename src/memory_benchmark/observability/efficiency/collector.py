"""线程安全的成本与效率 observation 收集器。

Collector 通过 ContextVar 关联当前 conversation/question，因此共享 method 实例在
conversation 级线程并发下不会串写。它只在内存中构造 observation，文件提交由 runner
协调层负责。
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Iterator

from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency.entities import (
    ConversationEfficiencyObservation,
    EfficiencyObservation,
    EfficiencyStage,
    EmbeddingCallObservation,
    LLMCallObservation,
    MeasurementSource,
    QuestionEfficiencyObservation,
)


@dataclass
class ObservationScope:
    """一次 conversation 或 question 作用域返回的 observation 集合。

    `records` 只在作用域正常退出后冻结。作用域内部由 collector 管理，调用方不应修改。
    """

    records: tuple[EfficiencyObservation, ...] = ()


@dataclass
class _ScopeState:
    """Collector 当前执行上下文的可变内部状态。"""

    scope_type: str
    conversation_id: str
    question_id: str | None
    handle: ObservationScope
    scope_discriminator: str | None = None
    records: list[EfficiencyObservation] = field(default_factory=list)
    call_indexes: dict[str, int] = field(default_factory=dict)
    memory_build_total_latency_ms: float | None = None
    retrieval_recorded: bool = False
    retrieval_latency_ms: float | None = None
    unsupported_reason: str | None = None
    injected_memory_context_tokens: int | None = None
    answer_generation_latency_ms: float | None = None


class EfficiencyCollector:
    """按 runner 生命周期收集原始效率 observation。

    参数:
        run_id: observation 确定性 id 的运行身份。
        enabled: 是否启用观测；关闭后所有记录方法为空操作。
    """

    def __init__(self, *, run_id: str, enabled: bool) -> None:
        """创建 collector，并为当前实例建立独立 ContextVar。"""

        if not isinstance(run_id, str) or not run_id.strip():
            raise ConfigurationError("EfficiencyCollector run_id is required")
        self.run_id = run_id
        self.enabled = enabled
        suffix = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:12]
        self._scope_var: ContextVar[_ScopeState | None] = ContextVar(
            f"efficiency_scope_{suffix}_{id(self)}",
            default=None,
        )
        self._stage_var: ContextVar[EfficiencyStage | None] = ContextVar(
            f"efficiency_stage_{suffix}_{id(self)}",
            default=None,
        )

    @contextmanager
    def conversation_scope(
        self,
        conversation_id: str,
        *,
        scope_discriminator: str | None = None,
    ) -> Iterator[ObservationScope]:
        """建立单个 conversation 的记忆构建作用域。

        `scope_discriminator` 供 operation-level runner 在同一 conversation 内按
        session 多次进入 conversation scope 时区分 observation id（默认 None 时
        id 与旧行为完全一致，不影响标准 runner）。
        """

        with self._scope(
            scope_type="conversation",
            conversation_id=conversation_id,
            question_id=None,
            scope_discriminator=scope_discriminator,
        ) as scope:
            yield scope

    @contextmanager
    def question_scope(
        self,
        conversation_id: str,
        question_id: str,
        *,
        scope_discriminator: str | None = None,
    ) -> Iterator[ObservationScope]:
        """建立单个公开问题的检索与回答作用域。"""

        with self._scope(
            scope_type="question",
            conversation_id=conversation_id,
            question_id=question_id,
            scope_discriminator=scope_discriminator,
        ) as scope:
            yield scope

    @contextmanager
    def judge_scope(
        self,
        conversation_id: str,
        question_id: str,
    ) -> Iterator[ObservationScope]:
        """建立单个 evaluator judge 调用作用域。"""

        with self._scope(
            scope_type="judge",
            conversation_id=conversation_id,
            question_id=question_id,
        ) as scope:
            yield scope

    @contextmanager
    def operation_stage(
        self,
        stage: EfficiencyStage,
    ) -> Iterator[None]:
        """临时声明内部 LLM/embedding 调用所属阶段。"""

        if not isinstance(stage, EfficiencyStage):
            raise ConfigurationError("Efficiency operation stage must be EfficiencyStage")
        if not self.enabled:
            yield
            return
        self._require_scope()
        token = self._stage_var.set(stage)
        try:
            yield
        finally:
            self._stage_var.reset(token)

    def active_scope_type(self) -> str | None:
        """返回当前线程的 observation scope 类型；无 scope 时返回 None。

        该只读方法供 method adapter 在第三方内部回调中判断是否处于
        conversation/question/judge 作用域，避免在 runner 未建立 scope 时误写观测。
        """

        if not self.enabled:
            return None
        state = self._scope_var.get()
        if state is None:
            return None
        return state.scope_type

    def record_memory_build_total_latency(self, *, latency_ms: float) -> None:
        """记录当前 conversation 完成记忆构建所需的总耗时。"""

        state = self._active_state_or_none()
        if state is None:
            return
        if state.scope_type != "conversation":
            raise ConfigurationError(
                "memory build latency requires a conversation scope"
            )
        if state.memory_build_total_latency_ms is not None:
            raise ConfigurationError(
                "memory build latency was already recorded for this scope"
            )
        state.memory_build_total_latency_ms = latency_ms

    def record_retrieval_result(
        self,
        *,
        latency_ms: float,
        injected_memory_context_tokens: int | None,
    ) -> None:
        """记录当前 question 的精确检索耗时和最终注入记忆 token。"""

        state = self._active_state_or_none()
        if state is None:
            return
        self._require_question_state(state)
        self._ensure_retrieval_not_recorded(state)
        state.retrieval_recorded = True
        state.retrieval_latency_ms = latency_ms
        state.injected_memory_context_tokens = injected_memory_context_tokens

    def record_retrieval_result_if_missing(
        self,
        *,
        latency_ms: float,
        injected_memory_context_tokens: int | None,
    ) -> None:
        """仅在 adapter 未上报 retrieval 时记录；已上报时补齐 context tokens。

        answer-prompt 路径中，adapter 可能能精确记录检索耗时，但 runner 才能统一读取
        method metadata 中可选的 `answer_context`。这个方法避免重复 retrieval
        observation，同时允许 runner 回填可诊断的 memory context token 数。
        """

        state = self._active_state_or_none()
        if state is None:
            return
        self._require_question_state(state)
        if state.retrieval_recorded:
            if (
                state.injected_memory_context_tokens is None
                and injected_memory_context_tokens is not None
            ):
                state.injected_memory_context_tokens = injected_memory_context_tokens
            return
        self.record_retrieval_result(
            latency_ms=latency_ms,
            injected_memory_context_tokens=injected_memory_context_tokens,
        )

    def record_retrieval_unsupported(self, reason: str) -> None:
        """声明当前 method 无法精确拆分 question 的 retrieval。"""

        state = self._active_state_or_none()
        if state is None:
            return
        self._require_question_state(state)
        self._ensure_retrieval_not_recorded(state)
        if not isinstance(reason, str) or not reason.strip():
            raise ConfigurationError("retrieval unsupported reason is required")
        state.retrieval_recorded = True
        state.unsupported_reason = reason

    def record_retrieval_unsupported_if_missing(self, reason: str) -> None:
        """仅在 adapter 未上报 retrieval 时补充 unsupported 声明。

        Runner 在 `get_answer()` 返回后调用本方法。若 adapter 已记录精确 retrieval，
        本方法保持原记录不变；否则写入明确原因，禁止用 0 冒充可测延迟。
        """

        state = self._active_state_or_none()
        if state is None:
            return
        self._require_question_state(state)
        if state.retrieval_recorded:
            return
        self.record_retrieval_unsupported(reason)

    def record_answer_generation(self, *, latency_ms: float) -> None:
        """记录当前 question 的 Answer LLM 生成耗时。"""

        state = self._active_state_or_none()
        if state is None:
            return
        self._require_question_state(state)
        if state.answer_generation_latency_ms is not None:
            raise ConfigurationError(
                "answer generation latency was already recorded for this scope"
            )
        state.answer_generation_latency_ms = latency_ms

    def record_llm_call(
        self,
        *,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        token_measurement_source: MeasurementSource,
    ) -> None:
        """记录当前作用域内一次成功的 LLM 调用。"""

        state = self._active_state_or_none()
        if state is None:
            return
        stage = self._resolve_current_stage(state)
        observation = LLMCallObservation(
            observation_id=self._next_observation_id(
                state,
                observation_type="llm_call",
                stage=stage,
                model_id=model_id,
            ),
            stage=stage,
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            token_measurement_source=token_measurement_source,
            conversation_id=state.conversation_id,
            question_id=state.question_id,
        )
        state.records.append(observation)

    def record_embedding_call(
        self,
        *,
        model_id: str,
        input_tokens: int,
        latency_ms: float,
        token_measurement_source: MeasurementSource,
        latency_measurement_source: MeasurementSource,
    ) -> None:
        """记录当前作用域内一次成功的 embedding 调用。"""

        state = self._active_state_or_none()
        if state is None:
            return
        stage = self._resolve_current_stage(state)
        observation = EmbeddingCallObservation(
            observation_id=self._next_observation_id(
                state,
                observation_type="embedding_call",
                stage=stage,
                model_id=model_id,
            ),
            stage=stage,
            model_id=model_id,
            input_tokens=input_tokens,
            latency_ms=latency_ms,
            token_measurement_source=token_measurement_source,
            latency_measurement_source=latency_measurement_source,
            conversation_id=state.conversation_id,
            question_id=state.question_id,
        )
        state.records.append(observation)

    @contextmanager
    def _scope(
        self,
        *,
        scope_type: str,
        conversation_id: str,
        question_id: str | None,
        scope_discriminator: str | None = None,
    ) -> Iterator[ObservationScope]:
        """建立内部 scope，并在正常退出时完成聚合 observation。"""

        handle = ObservationScope()
        if not self.enabled:
            yield handle
            return
        if self._scope_var.get() is not None:
            raise ConfigurationError("Efficiency scopes cannot be nested")
        state = _ScopeState(
            scope_type=scope_type,
            conversation_id=conversation_id,
            question_id=question_id,
            handle=handle,
            scope_discriminator=scope_discriminator,
        )
        token = self._scope_var.set(state)
        completed = False
        try:
            yield handle
            self._finalize_scope(state)
            completed = True
        finally:
            self._scope_var.reset(token)
            if completed:
                handle.records = tuple(state.records)

    def _finalize_scope(self, state: _ScopeState) -> None:
        """把 scope 聚合字段转换为最终 observation。"""

        if state.scope_type == "conversation":
            if state.memory_build_total_latency_ms is None:
                raise ConfigurationError(
                    "conversation scope requires memory build latency"
                )
            state.records.append(
                ConversationEfficiencyObservation(
                    observation_id=self._aggregate_observation_id(
                        state,
                        "conversation_efficiency",
                    ),
                    conversation_id=state.conversation_id,
                    memory_build_total_latency_ms=state.memory_build_total_latency_ms,
                )
            )
            return

        if state.scope_type == "judge":
            return

        if not state.retrieval_recorded:
            raise ConfigurationError(
                "question scope requires retrieval latency or unsupported reason"
            )
        if state.answer_generation_latency_ms is None:
            raise ConfigurationError(
                "question scope requires answer generation latency"
            )
        state.records.append(
            QuestionEfficiencyObservation(
                observation_id=self._aggregate_observation_id(
                    state,
                    "question_efficiency",
                ),
                conversation_id=state.conversation_id,
                question_id=state.question_id or "",
                retrieval_latency_ms=state.retrieval_latency_ms,
                unsupported_reason=state.unsupported_reason,
                injected_memory_context_tokens=state.injected_memory_context_tokens,
                answer_generation_latency_ms=state.answer_generation_latency_ms,
            )
        )

    def _active_state_or_none(self) -> _ScopeState | None:
        """返回当前 scope；关闭 collector 时所有记录方法为空操作。"""

        if not self.enabled:
            return None
        return self._require_scope()

    def _require_scope(self) -> _ScopeState:
        """要求当前线程已经进入 runner 管理的 observation scope。"""

        state = self._scope_var.get()
        if state is None:
            raise ConfigurationError(
                "Efficiency observation recording requires an active scope"
            )
        return state

    @staticmethod
    def _require_question_state(state: _ScopeState) -> None:
        """要求当前记录发生在 question scope。"""

        if state.scope_type != "question":
            raise ConfigurationError("question efficiency requires a question scope")

    @staticmethod
    def _ensure_retrieval_not_recorded(state: _ScopeState) -> None:
        """拒绝同一 question 重复声明 retrieval 状态。"""

        if state.retrieval_recorded:
            raise ConfigurationError(
                "retrieval efficiency was already recorded for this scope"
            )

    def _resolve_current_stage(self, state: _ScopeState) -> EfficiencyStage:
        """解析内部调用阶段，避免 question scope 模糊归类。"""

        stage = self._stage_var.get()
        if stage is not None:
            return stage
        if state.scope_type == "conversation":
            return EfficiencyStage.MEMORY_BUILD
        if state.scope_type == "judge":
            return EfficiencyStage.JUDGE
        raise ConfigurationError(
            "question-scope model calls require an explicit operation stage"
        )

    def _next_observation_id(
        self,
        state: _ScopeState,
        *,
        observation_type: str,
        stage: EfficiencyStage,
        model_id: str,
    ) -> str:
        """按当前 scope 内稳定调用顺序生成 observation id。"""

        counter_key = f"{observation_type}:{stage.value}:{model_id}"
        call_index = state.call_indexes.get(counter_key, 0)
        state.call_indexes[counter_key] = call_index + 1
        return self._build_observation_id(
            state,
            observation_type=observation_type,
            stage=stage.value,
            model_id=model_id,
            call_index=call_index,
        )

    def _aggregate_observation_id(
        self,
        state: _ScopeState,
        observation_type: str,
    ) -> str:
        """为 conversation/question 聚合记录生成确定性 id。"""

        return self._build_observation_id(
            state,
            observation_type=observation_type,
            stage=state.scope_type,
            model_id=None,
            call_index=0,
        )

    def _build_observation_id(
        self,
        state: _ScopeState,
        *,
        observation_type: str,
        stage: str,
        model_id: str | None,
        call_index: int,
    ) -> str:
        """对 canonical identity payload 计算 SHA-256。"""

        payload = {
            "run_id": self.run_id,
            "observation_type": observation_type,
            "stage": stage,
            "conversation_id": state.conversation_id,
            "question_id": state.question_id,
            "model_id": model_id,
            "call_index": call_index,
        }
        # 仅在显式提供 discriminator 时才纳入 id 计算，保证标准 runner（None）的
        # observation id 与历史完全一致，不破坏既有断言与 resume 兼容。
        if state.scope_discriminator is not None:
            payload["scope_discriminator"] = state.scope_discriminator
        serialized = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


__all__ = ["EfficiencyCollector", "ObservationScope"]

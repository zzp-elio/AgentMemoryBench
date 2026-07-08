"""MemoryOS-LoCoMo 小样本 legacy smoke runner。

本模块只保留给历史 MemoryOS smoke run 的复查与复现使用。新实验必须走统一的
`predict/evaluate/run` 入口，新 generic run 不能拿这里的根目录 legacy alias 做
resume 或混跑。默认只做成本估算，不会实例化 MemoryOS，也不会调用 LLM；只有显式
选择 add-only 并通过成本保护时，才会把公开 conversation 写入 MemoryOS，以便复现旧
smoke 行为。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal
from uuid import uuid4

from memory_benchmark.benchmark_adapters.locomo import LoCoMoAdapter
from memory_benchmark.config.settings import load_path_settings
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.methods import memoryos_adapter as memoryos_adapter_module
from memory_benchmark.methods.memoryos_adapter import MemoryOSPaperConfig
from memory_benchmark.utils.run_logger import RunLogger


MemoryOS = memoryos_adapter_module.MemoryOS
SmokeMode = Literal["estimate", "add-only"]


@dataclass(frozen=True)
class MemoryOSLoCoMoSmokeSummary:
    """MemoryOS-LoCoMo smoke 的可序列化摘要。

    字段:
        mode: 本次运行模式，`estimate` 不实例化 method，`add-only` 只写入记忆。
        run_id: 本次 smoke run id。
        conversation_id: 本次抽样的 LoCoMo conversation id。
        page_count: conversation 转成 MemoryOS page 后的数量。
        question_count: 当前 conversation 的公开 question 数。
        short_term_capacity: 本次配置的 STM capacity。
        update_batch_count: 预计触发 MemoryOS 更新批次数。
        remaining_short_term_pages: 写入结束后预计留在 STM 的 page 数。
        will_trigger_updates: 是否会触发 MemoryOS 更新。
        add_executed: 是否实际调用了 `MemoryOS.add()`。
        answer_executed: 是否实际调用了 `MemoryOS.get_answer()`。
        added_conversation_ids: add-only 模式下 method 返回的 conversation ids。
        log_dir: 本次运行日志目录。
        metadata: 可公开记录的附加信息。
    """

    mode: str
    run_id: str
    conversation_id: str
    page_count: int
    question_count: int
    short_term_capacity: int
    update_batch_count: int
    remaining_short_term_pages: int
    will_trigger_updates: bool
    add_executed: bool = False
    answer_executed: bool = False
    added_conversation_ids: list[str] = field(default_factory=list)
    log_dir: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """转换成 JSON 可序列化字典。

        输入:
            无。

        输出:
            dict[str, object]: 本次 smoke 摘要。
        """

        return asdict(self)


def run_memoryos_locomo_smoke(
    project_root: str | Path | None = None,
    output_root: str | Path | None = None,
    run_id: str | None = None,
    mode: SmokeMode = "estimate",
    use_paper_config: bool = False,
    confirm_expensive: bool = False,
) -> MemoryOSLoCoMoSmokeSummary:
    """运行历史 MemoryOS-LoCoMo 受保护 smoke。

    输入:
        project_root: 项目根目录；为空时从当前目录向上解析。
        output_root: smoke 输出根目录；为空时使用配置层的 `outputs_root`。
        run_id: 本次运行 id；为空时自动生成。
        mode: `estimate` 只估算，`add-only` 写入公开 conversation 但不答题。
        use_paper_config: True 时使用论文默认 STM capacity=7；False 时使用 safe
            capacity，避免 add-only 阶段触发 MemoryOS LLM 更新。
        confirm_expensive: 当配置会触发 MemoryOS 更新时，必须显式置 True。

    说明:
        本入口仅用于历史 MemoryOS smoke run 的解释、复现和旧 checkpoint 读取；
        新实验必须使用统一 `predict/evaluate/run`，且不要把新 generic run 与旧
        根目录 alias 的 resume 状态混用。

    输出:
        MemoryOSLoCoMoSmokeSummary: 本次 smoke 的成本估算和执行摘要。

    异常:
        ConfigurationError: mode 非法，或高成本配置未显式确认。
    """

    if mode not in ("estimate", "add-only"):
        raise ConfigurationError(f"Unsupported MemoryOS-LoCoMo smoke mode: {mode}")

    path_settings = load_path_settings(project_root=project_root)
    selected_output_root = Path(output_root or path_settings.outputs_root).resolve()
    selected_run_id = run_id or f"memoryos-locomo-smoke-{uuid4().hex[:8]}"
    log_dir = selected_output_root / selected_run_id / "logs"
    logger = RunLogger(log_dir)

    dataset = LoCoMoAdapter(path_settings.project_root).load(limit=1)
    if not dataset.conversations:
        raise ConfigurationError("LoCoMo smoke requires at least one conversation")
    conversation = dataset.conversations[0]

    base_config = MemoryOSPaperConfig()
    if mode == "estimate":
        config = base_config
    else:
        config = _select_memoryos_config(conversation, base_config, use_paper_config)
    estimate = memoryos_adapter_module.MemoryOS.estimate_add_workload(conversation, config)
    summary_metadata = {
        "dataset_name": dataset.dataset_name,
        "use_paper_config": use_paper_config,
        "confirm_expensive": confirm_expensive,
    }
    logger.info(
        "[bold]MemoryOS-LoCoMo smoke[/bold] "
        f"mode={mode} conversation={conversation.conversation_id} "
        f"pages={estimate.page_count} updates={estimate.update_batch_count}"
    )
    logger.log_event(
        "smoke_started",
        {
            "mode": mode,
            "conversation_id": conversation.conversation_id,
            "page_count": estimate.page_count,
            "question_count": len(conversation.questions),
            "short_term_capacity": estimate.short_term_capacity,
            "update_batch_count": estimate.update_batch_count,
            "will_trigger_updates": estimate.will_trigger_updates,
            "use_paper_config": use_paper_config,
        },
    )

    if mode != "estimate" and estimate.will_trigger_updates and not confirm_expensive:
        logger.log_event(
            "smoke_blocked",
            {
                "reason": "expensive_memoryos_updates_require_confirmation",
                "update_batch_count": estimate.update_batch_count,
            },
        )
        raise ConfigurationError(
            "MemoryOS smoke would trigger "
            f"{estimate.update_batch_count} update batches; pass confirm_expensive=True "
            "only after确认本次 LLM 调用成本可接受。"
        )

    added_conversation_ids: list[str] = []
    add_executed = False
    if mode == "add-only":
        system = MemoryOS(
            storage_root=selected_output_root / selected_run_id / "memoryos_state",
            config=config,
        )
        add_result = system.add([conversation])
        added_conversation_ids = list(add_result.conversation_ids)
        add_executed = True
        logger.log_event(
            "conversation_added",
            {
                "conversation_id": conversation.conversation_id,
                "added_conversation_ids": added_conversation_ids,
            },
        )

    summary = MemoryOSLoCoMoSmokeSummary(
        mode=mode,
        run_id=selected_run_id,
        conversation_id=conversation.conversation_id,
        page_count=estimate.page_count,
        question_count=len(conversation.questions),
        short_term_capacity=estimate.short_term_capacity,
        update_batch_count=estimate.update_batch_count,
        remaining_short_term_pages=estimate.remaining_short_term_pages,
        will_trigger_updates=estimate.will_trigger_updates,
        add_executed=add_executed,
        answer_executed=False,
        added_conversation_ids=added_conversation_ids,
        log_dir=str(log_dir),
        metadata=summary_metadata,
    )
    logger.log_event("smoke_finished", summary.to_dict())
    return summary


def _select_memoryos_config(
    conversation,
    base_config: MemoryOSPaperConfig,
    use_paper_config: bool,
) -> MemoryOSPaperConfig:
    """选择本次 smoke 使用的 MemoryOS 配置。

    输入:
        conversation: 当前 LoCoMo conversation。
        base_config: 论文默认配置。
        use_paper_config: 是否严格使用论文默认 STM capacity。

    输出:
        MemoryOSPaperConfig: paper 或 safe add-only 配置。
    """

    if use_paper_config:
        return base_config

    page_count = len(memoryos_adapter_module.MemoryOS.conversation_to_memory_pages(conversation))
    safe_capacity = max(base_config.short_term_capacity, page_count + 1)
    return MemoryOSPaperConfig(
        llm_model=base_config.llm_model,
        embedding_model_name=base_config.embedding_model_name,
        short_term_capacity=safe_capacity,
        mid_term_capacity=base_config.mid_term_capacity,
        long_term_knowledge_capacity=base_config.long_term_knowledge_capacity,
        mid_term_heat_threshold=base_config.mid_term_heat_threshold,
        mid_term_similarity_threshold=base_config.mid_term_similarity_threshold,
        top_k_sessions=base_config.top_k_sessions,
        retrieval_queue_capacity=base_config.retrieval_queue_capacity,
        segment_similarity_threshold=base_config.segment_similarity_threshold,
        page_similarity_threshold=base_config.page_similarity_threshold,
        knowledge_threshold=base_config.knowledge_threshold,
        suppress_official_stdout=base_config.suppress_official_stdout,
    )


__all__ = [
    "MemoryOSLoCoMoSmokeSummary",
    "run_memoryos_locomo_smoke",
]

"""benchmark adapter 注册表。

新增 benchmark 时，优先新增一个 `BenchmarkAdapter` 子类，然后通过
`BenchmarkRegistry.register()` 注册。这样核心 runner 和 CLI 不需要知道具体
adapter 类的实现细节，后续也可以扩展成插件发现机制。
"""

from __future__ import annotations

import copy
import importlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from memory_benchmark.core import (
    AnswerPromptResult,
    AnswerResult,
    Conversation,
    Dataset,
    MethodCapability,
    Question,
    Session,
    TaskFamily,
)
from memory_benchmark.core.exceptions import (
    AdapterAlreadyRegisteredError,
    ConfigurationError,
    UnknownBenchmarkError,
)
from memory_benchmark.core.provider_protocol import RetrievalResult
from memory_benchmark.utils import get_logger

from .base import BenchmarkAdapter
from .contracts import (
    BenchmarkLoadRequest,
    BenchmarkResumePolicy,
    BenchmarkSmokePolicy,
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
    normalize_variant_run_id_collision_key,
    normalize_variant_run_id_token,
)
from .beam import (
    BEAM_RESUME_POLICY,
    BEAM_SMOKE_POLICY,
    BEAM_VARIANT_SPECS,
    build_beam_unified_answer_prompt,
    prepare_beam_run,
)
from .halumem import (
    HALUMEM_RESUME_POLICY,
    HALUMEM_SMOKE_POLICY,
    HALUMEM_VARIANT_SPECS,
    build_halumem_unified_answer_prompt,
    prepare_halumem_run,
)
from .locomo import LOCOMO_VARIANT_SPECS, prepare_locomo_run
from .locomo_prompt import build_locomo_unified_answer_prompt
from .longmemeval import LONGMEMEVAL_VARIANT_SPECS, LongMemEvalAdapter
from .longmemeval_prompt import build_longmemeval_unified_answer_prompt
from .membench import (
    MEMBENCH_RESUME_POLICY,
    MEMBENCH_SMOKE_POLICY,
    MEMBENCH_VARIANT_SPECS,
    build_membench_unified_answer_prompt,
    normalize_membench_choice_prediction,
    prepare_membench_run_with_policy_metadata,
)


logger = get_logger(__name__)


def _copy_dataset_with_metadata(
    dataset: Dataset,
    *,
    variant: str,
    run_scope: RunScope,
) -> Dataset:
    """复制数据集并补齐注册层需要的 metadata。"""

    metadata = copy.deepcopy(dataset.metadata)
    metadata["variant"] = variant
    metadata["run_scope"] = run_scope.value
    return Dataset(
        dataset_name=dataset.dataset_name,
        conversations=list(dataset.conversations),
        metadata=metadata,
    )


def _build_longmemeval_smoke_dataset(
    dataset: Dataset,
    *,
    round_limit: int,
) -> Dataset:
    """按完整 user+assistant round 裁剪 LongMemEval smoke 历史。

    输入:
        dataset: 已通过 `LongMemEvalAdapter.load(limit=1)` 得到的单 instance 数据。
        round_limit: 最多保留多少个双 turn round；必须为正数。

    输出:
        Dataset: conversation/question/gold 保持不变，sessions 只保留前 `round_limit`
        个完整双 turn round，并在 metadata 中记录原始和保留规模。
    """

    if round_limit < 1:
        raise ConfigurationError("LongMemEval smoke round_limit must be positive")

    cropped_conversations: list[Conversation] = []
    total_original_turn_count = 0
    total_retained_turn_count = 0
    total_retained_round_count = 0
    for conversation in dataset.conversations:
        remaining_rounds = round_limit
        cropped_sessions: list[Session] = []
        original_turn_count = sum(len(session.turns) for session in conversation.sessions)
        retained_turn_count = 0
        retained_round_count = 0
        total_original_turn_count += original_turn_count

        for session in conversation.sessions:
            if remaining_rounds <= 0:
                break
            round_turn_count = min(len(session.turns) // 2, remaining_rounds) * 2
            if round_turn_count <= 0:
                continue
            retained_turns = copy.deepcopy(session.turns[:round_turn_count])
            retained_rounds = round_turn_count // 2
            remaining_rounds -= retained_rounds
            retained_turn_count += round_turn_count
            retained_round_count += retained_rounds
            session_metadata = copy.deepcopy(session.metadata)
            session_metadata.update(
                {
                    "smoke_original_turn_count": len(session.turns),
                    "smoke_retained_turn_count": round_turn_count,
                    "smoke_retained_round_count": retained_rounds,
                }
            )
            cropped_sessions.append(
                Session(
                    session_id=session.session_id,
                    turns=retained_turns,
                    session_time=session.session_time,
                    start_time=session.start_time,
                    end_time=session.end_time,
                    metadata=session_metadata,
                )
            )

        if retained_round_count < 1:
            raise ConfigurationError(
                "LongMemEval smoke requires at least one complete two-turn round"
            )
        total_retained_turn_count += retained_turn_count
        total_retained_round_count += retained_round_count
        conversation_metadata = copy.deepcopy(conversation.metadata)
        conversation_metadata.update(
            {
                "smoke_round_limit": round_limit,
                "smoke_original_turn_count": original_turn_count,
                "smoke_retained_turn_count": retained_turn_count,
                "smoke_retained_round_count": retained_round_count,
            }
        )
        cropped_conversations.append(
            Conversation(
                conversation_id=conversation.conversation_id,
                sessions=cropped_sessions,
                questions=copy.deepcopy(conversation.questions),
                gold_answers=copy.deepcopy(conversation.gold_answers),
                metadata=conversation_metadata,
            )
        )

    metadata = copy.deepcopy(dataset.metadata)
    metadata.update(
        {
            "smoke_round_limit": round_limit,
            "smoke_original_turn_count": total_original_turn_count,
            "smoke_retained_turn_count": total_retained_turn_count,
            "smoke_retained_round_count": total_retained_round_count,
        }
    )
    return Dataset(
        dataset_name=dataset.dataset_name,
        conversations=cropped_conversations,
        metadata=metadata,
    )


def _prepare_longmemeval_run(
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """为当前的 LongMemEval concrete variant 构造一次运行。"""

    adapter = LongMemEvalAdapter(project_root, variant=request.variant)
    if request.run_scope is RunScope.FULL:
        dataset = adapter.load()
    elif request.run_scope is RunScope.SMOKE:
        dataset = _build_longmemeval_smoke_dataset(
            adapter.load(limit=request.smoke_conversation_limit),
            round_limit=request.smoke_turn_limit,
        )
    else:  # pragma: no cover - RunScope 只有 smoke / full
        raise ConfigurationError(f"unsupported LongMemEval run scope: {request.run_scope}")

    variant_spec = next(
        spec for spec in LONGMEMEVAL_VARIANT_SPECS if spec.name == request.variant
    )

    return PreparedBenchmarkRun(
        variant=request.variant,
        run_scope=request.run_scope,
        dataset=_copy_dataset_with_metadata(
            dataset,
            variant=request.variant,
            run_scope=request.run_scope,
        ),
        source_relative_paths=variant_spec.source_relative_paths,
    )


def _prepare_longmemeval_run_with_policy_metadata(
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """在 LongMemEval 既有 prepare_run 之上补齐已注册的 smoke/resume policy metadata。

    只追加 dataset metadata 字段，不改变 `longmemeval.py` 的转换算法，也不
    修改 `_build_longmemeval_smoke_dataset` 的 round 裁剪（round 预算与 original/
    retained 规模已由该函数记录，本函数只把声明的 policy 进 dataset metadata，
    供 manifest/dataset metadata 审计使用，避免 policy 只存在于 CLI `--help`
    文本里）。
    """

    prepared = _prepare_longmemeval_run(project_root, request)
    metadata = copy.deepcopy(prepared.dataset.metadata)
    metadata["smoke_policy"] = LONGMEMEVAL_SMOKE_POLICY.to_dict()
    metadata["resume_policy"] = LONGMEMEVAL_RESUME_POLICY.to_dict()
    return PreparedBenchmarkRun(
        variant=prepared.variant,
        run_scope=prepared.run_scope,
        dataset=Dataset(
            dataset_name=prepared.dataset.dataset_name,
            conversations=list(prepared.dataset.conversations),
            metadata=metadata,
        ),
        source_relative_paths=prepared.source_relative_paths,
    )


# LongMemEval 是本 workstream 第二个完成 smoke/resume 审计的 benchmark（见
# docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md C2）。
# 自然裁剪单位 = round（双 turn），与 LoCoMo 同属第一人称对话流；默认 smoke 取
# 第 1 个 instance 的前 1 个 round（2 turn），1 round 足以验证四步链路，无需
# 保证问题可答。选择不读 answer/answer_session_ids/has_answer。LongMemEval 真实
# 数据约 8% session 非严格 user-first 交替（见 notes/longmemeval-b2-audit.md），
# round 裁剪按"前 2 个 turn"预算截断即可，不强配对，orphan/dangling 标记由
# 框架聚合层负责（本 policy 不实现新标记逻辑）。resume 与 LoCoMo 同：smoke 禁
# resume（smoke_enabled=False），formal 为 conversation(=instance) 级 resume，
# 不引入任何 turn/session 级 resume。
LONGMEMEVAL_SMOKE_POLICY = BenchmarkSmokePolicy(
    history_axis="rounds",
    default_history_limit=1,
    default_isolation_limit=1,
    default_question_limit=1,
)
LONGMEMEVAL_RESUME_POLICY = BenchmarkResumePolicy(
    smoke_enabled=False,
    ingest_checkpoint="conversation",
    answer_checkpoint="question",
    reuse_saved_retrieval=True,
    evaluation_artifact_only=True,
)

# LoCoMo 是本 workstream 第一个完成 smoke/resume 审计的 benchmark（见
# docs/workstreams/ws02.6-first-smoke-hardening/plan-b0-b1-locomo.md Task 3）。
# 具体取值：LoCoMo session 内相邻 turn 在当前 release 中交替 speaker，smoke 的
# round 仅定义为原始顺序的两个连续 turn，不改变 canonical turn stream；smoke
# 无需保证问题可回答，1 round 足以验证四步链路，故 default_history_limit=1。resume
# 上，smoke 数据量太小、状态不值得跨 run 复用（smoke_enabled=False），但
# checkpoint 粒度、retrieval 复用和"只跑 evaluator"仍遵循与 full 相同的
# conversation/question 级约定。
LOCOMO_SMOKE_POLICY = BenchmarkSmokePolicy(
    history_axis="rounds",
    default_history_limit=1,
    default_isolation_limit=1,
    default_question_limit=1,
)
LOCOMO_RESUME_POLICY = BenchmarkResumePolicy(
    smoke_enabled=False,
    ingest_checkpoint="conversation",
    answer_checkpoint="question",
    reuse_saved_retrieval=True,
    evaluation_artifact_only=True,
)


def _prepare_locomo_run_with_policy_metadata(
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """在 LoCoMo 既有 prepare_run 之上补齐已注册的 smoke/resume policy metadata。

    只追加 dataset metadata 字段，不改变 `locomo.py` 的转换/裁剪算法，也不
    修改 conversation/question/gold 内容；供 manifest/dataset metadata 审计
    使用，避免 policy 只存在于 CLI `--help` 文本里。
    """

    prepared = prepare_locomo_run(project_root, request)
    metadata = copy.deepcopy(prepared.dataset.metadata)
    metadata["smoke_policy"] = LOCOMO_SMOKE_POLICY.to_dict()
    metadata["resume_policy"] = LOCOMO_RESUME_POLICY.to_dict()
    return PreparedBenchmarkRun(
        variant=prepared.variant,
        run_scope=prepared.run_scope,
        dataset=Dataset(
            dataset_name=prepared.dataset.dataset_name,
            conversations=list(prepared.dataset.conversations),
            metadata=metadata,
        ),
        source_relative_paths=prepared.source_relative_paths,
    )


@dataclass(frozen=True)
class BenchmarkRegistration:
    """一个 benchmark 的静态注册声明。"""

    name: str
    adapter_cls: type[BenchmarkAdapter]
    task_family: TaskFamily
    required_capabilities: frozenset[MethodCapability]
    variants: tuple[BenchmarkVariantSpec, ...]
    default_variant: str
    prepare_run: Callable[[Path, BenchmarkLoadRequest], PreparedBenchmarkRun]
    prediction_enabled: bool
    prompt_track: str = "native"
    operation_level: bool = False
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ) = None
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None = None
    # smoke/resume policy 是可选声明：只有完成 B2-B5 审计的 benchmark 才注册,
    # 未注册的 benchmark 保持现状兼容路径（CLI 沿用全局默认值/legacy 行为）。
    smoke_policy: BenchmarkSmokePolicy | None = None
    resume_policy: BenchmarkResumePolicy | None = None
    # gold evidence contract 属于 benchmark/private-label identity：声明 v1 表示
    # 该 benchmark 的 adapter 在 load 时为每个 gold label 落 evaluator-private
    # `evidence_group_sets`，并要求 manifest benchmark_policy 携带同一版本。
    gold_evidence_contract_version: str | None = None

    def __post_init__(self) -> None:
        """在注册阶段校验 variant 声明是否自洽。"""

        if not self.name:
            raise ConfigurationError("benchmark registration name is required")
        if self.gold_evidence_contract_version is not None and (
            not isinstance(self.gold_evidence_contract_version, str)
            or self.gold_evidence_contract_version != "v1"
        ):
            raise ConfigurationError(
                f"{self.name}: gold_evidence_contract_version must be None or 'v1', "
                f"got {self.gold_evidence_contract_version!r}"
            )
        if not self.variants:
            raise ConfigurationError(f"{self.name}: at least one variant is required")

        seen_names: set[str] = set()
        seen_run_id_tokens: set[str] = set()
        seen_casefolded_run_id_tokens: set[str] = set()
        for spec in self.variants:
            if spec.name in seen_names:
                raise ConfigurationError(
                    f"{self.name}: duplicate variant name: {spec.name}"
                )
            seen_names.add(spec.name)
            run_id_token = normalize_variant_run_id_token(spec.name)
            if run_id_token in seen_run_id_tokens:
                raise ConfigurationError(
                    f"{self.name}: duplicate normalized variant run-id token: "
                    f"{run_id_token}"
                )
            seen_run_id_tokens.add(run_id_token)
            casefolded_run_id_token = normalize_variant_run_id_collision_key(spec.name)
            if casefolded_run_id_token in seen_casefolded_run_id_tokens:
                raise ConfigurationError(
                    f"{self.name}: duplicate case-insensitive normalized "
                    f"variant run-id token: {run_id_token}"
                )
            seen_casefolded_run_id_tokens.add(casefolded_run_id_token)

        if self.default_variant not in seen_names:
            allowed = ", ".join(spec.name for spec in self.variants)
            raise ConfigurationError(
                f"{self.name}: default_variant '{self.default_variant}' must be one of: {allowed}"
            )
        if "all" in seen_names:
            raise ConfigurationError(f"{self.name}: concrete variants cannot be named 'all'")
        if self.prompt_track not in {"native", "unified"}:
            raise ConfigurationError(
                f"{self.name}: prompt_track must be native or unified"
            )
        if self.prompt_track == "unified" and self.unified_prompt_builder is None:
            raise ConfigurationError(
                f"{self.name}: unified prompt_track requires unified_prompt_builder"
            )
        if self.prompt_track == "native" and self.unified_prompt_builder is not None:
            raise ConfigurationError(
                f"{self.name}: native prompt_track cannot declare unified_prompt_builder"
            )
        if (self.smoke_policy is None) != (self.resume_policy is None):
            raise ConfigurationError(
                f"{self.name}: smoke_policy and resume_policy must be declared together"
            )

    def variant_names(self) -> tuple[str, ...]:
        """返回 registration 声明顺序中的 concrete variant 名称。"""

        return tuple(spec.name for spec in self.variants)

    def variant_spec(self, variant: str) -> BenchmarkVariantSpec:
        """查找指定 concrete variant 的静态声明。"""

        for spec in self.variants:
            if spec.name == variant:
                return spec
        allowed = ", ".join((*self.variant_names(), "all"))
        raise ConfigurationError(
            f"Unknown benchmark variant '{variant}' for '{self.name}'. Allowed: {allowed}"
        )

    def prepare(
        self,
        project_root: str | Path,
        request: BenchmarkLoadRequest,
    ) -> PreparedBenchmarkRun:
        """调用 benchmark 专属准备钩子并校验返回值。"""

        if not isinstance(request.run_scope, RunScope):
            raise ConfigurationError(f"{self.name}: run_scope must be a RunScope value")

        variant_spec = self.variant_spec(request.variant)
        prepared = self.prepare_run(Path(project_root), request)

        if prepared.variant != request.variant:
            raise ConfigurationError(
                f"{self.name}: prepared variant '{prepared.variant}' does not match request '{request.variant}'"
            )
        if not isinstance(prepared.run_scope, RunScope):
            raise ConfigurationError(
                f"{self.name}: prepared run_scope must be a RunScope value"
            )
        if prepared.run_scope is not request.run_scope:
            raise ConfigurationError(
                f"{self.name}: prepared run_scope '{prepared.run_scope}' does not match request '{request.run_scope}'"
            )

        for path in prepared.source_relative_paths:
            if path.is_absolute() or ".." in path.parts:
                raise ConfigurationError(
                    f"{self.name}: prepared source_relative_paths must stay under project root: {path}"
                )
        if tuple(prepared.source_relative_paths) != variant_spec.source_relative_paths:
            raise ConfigurationError(
                f"{self.name}: prepared source_relative_paths do not match variant '{request.variant}'"
            )

        metadata = prepared.dataset.metadata
        if metadata.get("variant") != request.variant:
            raise ConfigurationError(
                f"{self.name}: dataset metadata.variant must be '{request.variant}'"
            )
        if metadata.get("run_scope") != request.run_scope.value:
            raise ConfigurationError(
                f"{self.name}: dataset metadata.run_scope must be '{request.run_scope.value}'"
            )

        return prepared


class BenchmarkRegistry:
    """保存 benchmark name 到静态注册声明的映射。"""

    def __init__(self):
        """初始化空注册表。"""

        self._registrations: dict[str, BenchmarkRegistration] = {}

    def register(self, registration: BenchmarkRegistration) -> None:
        """注册一个 benchmark 声明。"""

        name = registration.name
        if name in self._registrations:
            raise AdapterAlreadyRegisteredError(name)
        self._registrations[name] = registration
        logger.debug("registered benchmark adapter: %s", name)

    def list_names(self) -> list[str]:
        """返回已注册 benchmark 名称，按字母排序。"""

        return sorted(self._registrations)

    def list_prediction_names(self) -> list[str]:
        """返回当前开放 prediction 的 benchmark 名称，按字母排序。"""

        return sorted(
            name
            for name, registration in self._registrations.items()
            if registration.prediction_enabled
        )

    def get_registration(self, name: str) -> BenchmarkRegistration:
        """返回指定 benchmark 的静态注册声明。"""

        try:
            return self._registrations[name]
        except KeyError as exc:
            raise UnknownBenchmarkError(name, self.list_names()) from exc

    def create(self, name: str, project_root: str | Path) -> BenchmarkAdapter:
        """实例化指定 benchmark adapter。"""

        return self.get_registration(name).adapter_cls(project_root)


def _try_register_adapter(
    registry: BenchmarkRegistry,
    module_name: str,
    class_name: str,
    *,
    task_family: TaskFamily,
    required_capabilities: frozenset[MethodCapability],
    variants: tuple[BenchmarkVariantSpec, ...],
    default_variant: str,
    prepare_run: Callable[[Path, BenchmarkLoadRequest], PreparedBenchmarkRun],
    prediction_enabled: bool,
    prompt_track: str = "native",
    operation_level: bool = False,
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ) = None,
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None = None,
    smoke_policy: BenchmarkSmokePolicy | None = None,
    resume_policy: BenchmarkResumePolicy | None = None,
    gold_evidence_contract_version: str | None = None,
) -> None:
    """尝试注册一个已迁移 adapter。"""

    try:
        module = importlib.import_module(module_name)
        adapter_cls = getattr(module, class_name)
    except (AttributeError, ImportError) as exc:
        logger.info("delay adapter registration for %s.%s: %s", module_name, class_name, exc)
        return
    registry.register(
        BenchmarkRegistration(
            name=adapter_cls.name,
            adapter_cls=adapter_cls,
            task_family=task_family,
            required_capabilities=required_capabilities,
            variants=variants,
            default_variant=default_variant,
            prepare_run=prepare_run,
            prediction_enabled=prediction_enabled,
            prompt_track=prompt_track,
            operation_level=operation_level,
            unified_prompt_builder=unified_prompt_builder,
            prediction_transform=prediction_transform,
            smoke_policy=smoke_policy,
            resume_policy=resume_policy,
            gold_evidence_contract_version=gold_evidence_contract_version,
        )
    )


def resolve_variant_selector(
    registration: BenchmarkRegistration,
    selector: str | None,
) -> tuple[str, ...]:
    """把 CLI selector 解析为 concrete variant 序列。"""

    if selector is None:
        return (registration.default_variant,)

    if selector == "all":
        return registration.variant_names()

    if selector in registration.variant_names():
        return (selector,)

    allowed = ", ".join((*registration.variant_names(), "all"))
    raise ConfigurationError(
        f"Unknown benchmark variant selector '{selector}' for '{registration.name}'. "
        f"Requested: {selector}. Allowed: {allowed}"
    )


def _build_default_registry() -> BenchmarkRegistry:
    """创建默认 registry。"""

    registry = BenchmarkRegistry()
    conversation_qa_capabilities = frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.MEMORY_RETRIEVAL,
        }
    )
    # Task 7-8 会把这两个 adapter 迁移到 v2 数据模型；迁移前导入失败就跳过。
    _try_register_adapter(
        registry,
        "memory_benchmark.benchmark_adapters.locomo",
        "LoCoMoAdapter",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=conversation_qa_capabilities,
        variants=LOCOMO_VARIANT_SPECS,
        default_variant="locomo10",
        prepare_run=_prepare_locomo_run_with_policy_metadata,
        prediction_enabled=True,
        smoke_policy=LOCOMO_SMOKE_POLICY,
        resume_policy=LOCOMO_RESUME_POLICY,
        prompt_track="unified",
        unified_prompt_builder=build_locomo_unified_answer_prompt,
        gold_evidence_contract_version="v1",
    )
    _try_register_adapter(
        registry,
        "memory_benchmark.benchmark_adapters.longmemeval",
        "LongMemEvalAdapter",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=conversation_qa_capabilities,
        variants=LONGMEMEVAL_VARIANT_SPECS,
        default_variant="s_cleaned",
        prepare_run=_prepare_longmemeval_run_with_policy_metadata,
        prediction_enabled=True,
        smoke_policy=LONGMEMEVAL_SMOKE_POLICY,
        resume_policy=LONGMEMEVAL_RESUME_POLICY,
        prompt_track="unified",
        unified_prompt_builder=build_longmemeval_unified_answer_prompt,
        gold_evidence_contract_version="v1",
    )
    _try_register_adapter(
        registry,
        "memory_benchmark.benchmark_adapters.membench",
        "MemBenchAdapter",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=conversation_qa_capabilities,
        variants=MEMBENCH_VARIANT_SPECS,
        default_variant="0_10k",
        prepare_run=prepare_membench_run_with_policy_metadata,
        prediction_enabled=True,
        smoke_policy=MEMBENCH_SMOKE_POLICY,
        resume_policy=MEMBENCH_RESUME_POLICY,
        prompt_track="unified",
        unified_prompt_builder=build_membench_unified_answer_prompt,
        prediction_transform=normalize_membench_choice_prediction,
        gold_evidence_contract_version="v1",
    )
    _try_register_adapter(
        registry,
        "memory_benchmark.benchmark_adapters.halumem",
        "HaluMemAdapter",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(),
        variants=HALUMEM_VARIANT_SPECS,
        default_variant="medium",
        prepare_run=prepare_halumem_run,
        prediction_enabled=True,
        smoke_policy=HALUMEM_SMOKE_POLICY,
        resume_policy=HALUMEM_RESUME_POLICY,
        prompt_track="unified",
        operation_level=True,
        unified_prompt_builder=build_halumem_unified_answer_prompt,
        gold_evidence_contract_version="v1",
    )
    _try_register_adapter(
        registry,
        "memory_benchmark.benchmark_adapters.beam",
        "BeamAdapter",
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(),
        variants=BEAM_VARIANT_SPECS,
        default_variant="100k",
        prepare_run=prepare_beam_run,
        prediction_enabled=True,
        smoke_policy=BEAM_SMOKE_POLICY,
        resume_policy=BEAM_RESUME_POLICY,
        prompt_track="unified",
        unified_prompt_builder=build_beam_unified_answer_prompt,
        gold_evidence_contract_version="v1",
    )
    return registry


DEFAULT_REGISTRY = _build_default_registry()


def list_benchmarks() -> list[str]:
    """列出当前默认 registry 中的 benchmark。"""

    return DEFAULT_REGISTRY.list_names()


def get_adapter(name: str, project_root: str | Path) -> BenchmarkAdapter:
    """创建 benchmark adapter 实例。"""

    return DEFAULT_REGISTRY.create(name, project_root)


def get_benchmark_registration(name: str) -> BenchmarkRegistration:
    """读取 benchmark 的静态注册声明。"""

    return DEFAULT_REGISTRY.get_registration(name)


def list_prediction_benchmarks() -> list[str]:
    """列出当前默认 registry 中开放 prediction 的 benchmark。"""

    return DEFAULT_REGISTRY.list_prediction_names()

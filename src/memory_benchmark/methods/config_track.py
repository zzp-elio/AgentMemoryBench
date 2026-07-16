"""method 双轨运行配置解析与 run 身份契约。

unified 轨用 ``None`` 表示完全沿用既有框架默认；native 轨只解析已经一手锁定的
method × benchmark 配置资产。两类 run 都产出不可变 ``TrackIdentity``，让 manifest
如实声明实现的 implementation/build/readout/judge 身份，并严格参与 resume。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping, Sequence

from memory_benchmark.config.settings import AnswerLLMSettings, DEFAULT_OPENAI_MODEL
from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.lightmem_native_prompts import (
    LIGHTMEM_NATIVE_ANSWER_PROFILES,
    LIGHTMEM_NATIVE_JUDGE_PROFILES,
    LightMemNativeJudgeProfile,
)
from memory_benchmark.methods.mem0_native_prompts import (
    MEM0_NATIVE_ANSWER_PROFILES,
    MEM0_NATIVE_JUDGE_PROFILES,
    Mem0NativeJudgeProfile,
)
from memory_benchmark.methods.memoryos_native_prompts import (
    MEMORYOS_NATIVE_ANSWER_PROFILES,
)

# ----------------------------------------------------------------------
# 枚举与契约常量
# ----------------------------------------------------------------------

CONTRACT_VERSION = "v1"

ImplementationVariant = Literal["product", "reproduction:memoryos-chromadb"]
ReadoutTrack = Literal["unified", "native"]
NativeScope = Literal["none", "readout_only"]
EmbeddingProfile = Literal[
    "controlled_embedding_v1",
    "product_canonical_required_config_v1",
    "product_default_v1",
    "unclassified_pending",
]
JudgeSource = Literal["framework_default", "official_parity", "framework_fallback"]
AnswerModelSource = Literal[
    "framework_default",
    "official_parity",
    "framework_model_override",
]
EmbeddingRevisionStatus = Literal[
    "local_unpinned",
    "provider_managed_unpinned",
    "pending",
]
EmbeddingIdentityStatus = Literal["declared", "pending"]

_IMPLEMENTMENT_VARIANTS: frozenset[str] = frozenset({"product", "reproduction:memoryos-chromadb"})
_READOUT_TRACKS: frozenset[str] = frozenset({"unified", "native"})
_NATIVE_SCOPES: frozenset[str] = frozenset({"none", "readout_only"})
_EMBEDDING_PROFILES: frozenset[str] = frozenset(
    {
        "controlled_embedding_v1",
        "product_canonical_required_config_v1",
        "product_default_v1",
        "unclassified_pending",
    }
)
_JUDGE_SOURCES: frozenset[str] = frozenset(
    {"framework_default", "official_parity", "framework_fallback"}
)
_ANSWER_MODEL_SOURCES: frozenset[str] = frozenset(
    {"framework_default", "official_parity", "framework_model_override"}
)
_EMBEDDING_REVISION_STATUSES: frozenset[str] = frozenset(
    {"local_unpinned", "provider_managed_unpinned", "pending"}
)
_EMBEDDING_IDENTITY_STATUSES: frozenset[str] = frozenset({"declared", "pending"})

# native 矩阵：readout-only，无 build override，按 method 锁 embedding_profile。
# implementation_variant 三家（及 A-Mem/SimpleMem 的 unified）当前均为 product 通用实现。
# reproduction 分叉（如 memoryos-chromadb）不在本卡 build_override 范围，保留枚举容量
# 供后续 variant 身份使用。


@dataclass(frozen=True)
class EmbeddingIdentity:
    """method 当前 build 的 embedding 身份（与 method.config 同一真实值）。"""

    provider: str | None
    model: str | None
    dimension: int | None
    revision: str | None
    revision_status: EmbeddingRevisionStatus
    normalization: str | None
    instruction: str | None
    distance: str | None
    identity_status: EmbeddingIdentityStatus

    def to_manifest_dict(self) -> dict[str, Any]:
        """返回可公开写入 manifest 的 embedding 身份字典。"""

        return {
            "provider": self.provider,
            "model": self.model,
            "dimension": self.dimension,
            "revision": self.revision,
            "revision_status": self.revision_status,
            "normalization": self.normalization,
            "instruction": self.instruction,
            "distance": self.distance,
            "identity_status": self.identity_status,
        }


@dataclass(frozen=True)
class TrackIdentity:
    """run 级双轨实现身份契约（不可变，运行时强校验）。

    字段:
        contract_version: 契约版本；当前固定 ``"v1"``，缺此值参与的旧 manifest 与新 run
            严格 resume mismatch。
        implementation_variant: 算法实现身份；``product`` 表示通用 OSS 产品实现，
            ``reproduction:*`` 表示算法 fork 的复现变体。
        readout_track: 本 run 的 readout 口径，``unified`` 或 ``native``。
        native_scope: native 覆盖层级；``none`` 表示未启用 native（含 unified 与单轨格），
            ``readout_only`` 表示只切 answer/judge readout 资产、未切 build。
        build_override_applied: 是否对本 run 应用了 build 侧覆盖（embedding/超参）。
            本卡恒为 False：native bundle 的 build reference 只作声明、不生效。
        embedding_profile: 当前 embedding build 所属轨道分类。
        historical_controlled_build_equivalent_to_current_main: 当前实际 build 是否与
            product-default 主轨字节重合；避免为纯标签差异重烧 API。
        embedding: 当前 build 的 concrete embedding 身份（provider/model/dimension/...）。
        judge_source: native run 的 judge 来源；``framework_fallback`` 表示官方无 LLM
            judge、回落框架 judge，不得称 full-native。
        answer_model_source: answer 模型来源；官方模型被项目 gpt-4o-mini 锁覆盖时标
            ``framework_model_override``。
    """

    contract_version: str
    implementation_variant: ImplementationVariant
    readout_track: ReadoutTrack
    native_scope: NativeScope
    build_override_applied: bool
    embedding_profile: EmbeddingProfile
    historical_controlled_build_equivalent_to_current_main: bool
    embedding: EmbeddingIdentity
    judge_source: JudgeSource
    answer_model_source: AnswerModelSource

    def to_manifest_dict(self) -> dict[str, Any]:
        """返回可公开写入 manifest 的 track identity 字典。"""

        return {
            "contract_version": self.contract_version,
            "implementation_variant": self.implementation_variant,
            "readout_track": self.readout_track,
            "native_scope": self.native_scope,
            "build_override_applied": self.build_override_applied,
            "embedding_profile": self.embedding_profile,
            "historical_controlled_build_equivalent_to_current_main": (
                self.historical_controlled_build_equivalent_to_current_main
            ),
            "embedding": self.embedding.to_manifest_dict(),
            "judge_source": self.judge_source,
            "answer_model_source": self.answer_model_source,
        }


# ----------------------------------------------------------------------
# 静态身份期望（来自裁决，按 method 注册注入）
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class _MethodTrackIdentityExpectation:
    """由 method 注册表提供的静态身份期望（不含 concrete embedding）。

    字段:
        implementation_variant: 算法实现身份。
        unified_embedding_profile: unified 轨 embedding_profile。
        unified_historical_equivalent: unified 当前 build 是否与 product-default 主轨
            字节重合。
        native_embedding_profile: native 轨 embedding_profile（若有 native grid）。
        native_historical_equivalent: native 当前 build 是否与 product-default 重合。
        unified_distance: unified 轨 embedding 距离度量。
        unified_revision_status: unified 轨 embedding revision 状态。
        answer_model_source_native: native run 的 answer 模型来源。
    """

    implementation_variant: ImplementationVariant
    unified_embedding_profile: EmbeddingProfile
    unified_historical_equivalent: bool
    unified_distance: str
    unified_revision_status: EmbeddingRevisionStatus
    native_embedding_profile: EmbeddingProfile
    native_historical_equivalent: bool
    native_distance: str
    native_revision_status: EmbeddingRevisionStatus
    answer_model_source_native: AnswerModelSource


# 三家 + A-Mem/SimpleMem 的静态身份期望。值来自 product-default-embedding-ruling 与
# integrated-method-dual-track-identity-audit（含架构师订正）。
#
# normalization/instruction 三家一致为 None（审计 §2）。Mem0 unified embedding 当前
# 是 controlled MiniLM/384 local，product-default 主轨为远端 OpenAI/1536，二者不重合
# → historical_equivalent=false。LightMem/MemoryOS 当前 MiniLM 与新主轨 MiniLM 重合 → true。
_METHOD_IDENTITY_EXPECTATIONS: Mapping[
    str, _MethodTrackIdentityExpectation
] = {
    "mem0": _MethodTrackIdentityExpectation(
        implementation_variant="product",
        unified_embedding_profile="controlled_embedding_v1",
        unified_historical_equivalent=False,
        unified_distance="qdrant-cosine",
        unified_revision_status="local_unpinned",
        native_embedding_profile="controlled_embedding_v1",
        native_historical_equivalent=False,
        native_distance="qdrant-cosine",
        native_revision_status="local_unpinned",
        answer_model_source_native="framework_model_override",
    ),
    "lightmem": _MethodTrackIdentityExpectation(
        implementation_variant="product",
        unified_embedding_profile="product_canonical_required_config_v1",
        unified_historical_equivalent=True,
        unified_distance="qdrant-cosine",
        unified_revision_status="local_unpinned",
        native_embedding_profile="product_canonical_required_config_v1",
        native_historical_equivalent=True,
        native_distance="qdrant-cosine",
        native_revision_status="local_unpinned",
        answer_model_source_native="framework_default",
    ),
    "memoryos": _MethodTrackIdentityExpectation(
        implementation_variant="reproduction:memoryos-chromadb",
        unified_embedding_profile="product_default_v1",
        unified_historical_equivalent=True,
        unified_distance="faiss-inner-product-on-l2-normalized",
        unified_revision_status="local_unpinned",
        native_embedding_profile="product_default_v1",
        native_historical_equivalent=True,
        native_distance="faiss-inner-product-on-l2-normalized",
        native_revision_status="local_unpinned",
        answer_model_source_native="framework_default",
    ),
    "amem": _MethodTrackIdentityExpectation(
        implementation_variant="product",
        unified_embedding_profile="unclassified_pending",
        unified_historical_equivalent=False,
        unified_distance="unknown",
        unified_revision_status="pending",
        native_embedding_profile="unclassified_pending",
        native_historical_equivalent=False,
        native_distance="unknown",
        native_revision_status="pending",
        answer_model_source_native="framework_default",
    ),
    "simplemem": _MethodTrackIdentityExpectation(
        implementation_variant="product",
        unified_embedding_profile="unclassified_pending",
        unified_historical_equivalent=False,
        unified_distance="unknown",
        unified_revision_status="pending",
        native_embedding_profile="unclassified_pending",
        native_historical_equivalent=False,
        native_distance="unknown",
        native_revision_status="pending",
        answer_model_source_native="framework_default",
    ),
}


def _resolve_expectation(method: str) -> _MethodTrackIdentityExpectation:
    """按 method 名解析静态身份期望，未声明的 method 用通用 pending 兜底。"""

    expectation = _METHOD_IDENTITY_EXPECTATIONS.get(method.strip().lower())
    if expectation is None:
        return _MethodTrackIdentityExpectation(
            implementation_variant="product",
            unified_embedding_profile="unclassified_pending",
            unified_historical_equivalent=False,
            unified_distance="unknown",
            unified_revision_status="pending",
            native_embedding_profile="unclassified_pending",
            native_historical_equivalent=False,
            native_distance="unknown",
            native_revision_status="pending",
            answer_model_source_native="framework_default",
        )
    return expectation


def _build_embedding_identity(
    *,
    concrete: tuple[str | None, str | None, int | None, str | None] | None,
    distance: str,
    revision_status: EmbeddingRevisionStatus,
) -> EmbeddingIdentity:
    """从运行时 embedding getter 抽取的 concrete 值合成 embedding 身份。

    输入:
        concrete: ``(provider, model, dimension, revision)``，缺失统一传 None。
        distance: 该 method/run 的距离度量（来自注册静态期望）。
        revision_status: revision 可锁性（来自注册静态期望）。

    输出:
        EmbeddingIdentity: 强校验后的不可变 embedding 身份。

    说明:
        值缺失（A-Mem/SimpleMem 未裁、或 getter 未声明）时用显式 None 并把
        identity_status 置 pending，不编字符串填满。dimension 非空时必须 > 0。
    """

    if concrete is None:
        identity_status: EmbeddingIdentityStatus = "pending"
        provider, model, dimension, revision = None, None, None, None
        resolved_revision_status: EmbeddingRevisionStatus = "pending"
    else:
        provider, model, dimension, revision = concrete
        all_missing = (
            not provider
            and not model
            and (dimension is None or dimension <= 0)
            and not revision
        )
        if all_missing:
            identity_status = "pending"
            resolved_revision_status = "pending"
        else:
            identity_status = "declared"
            resolved_revision_status = revision_status
    embedding = EmbeddingIdentity(
        provider=provider if provider else None,
        model=model if model else None,
        dimension=dimension,
        revision=revision if revision else None,
        revision_status=resolved_revision_status,
        normalization=None,
        instruction=None,
        distance=distance if identity_status == "declared" else None,
        identity_status=identity_status,
    )
    validate_embedding_identity(embedding)
    return embedding


def build_unified_track_identity(
    *,
    method: str,
    concrete_embedding: tuple[str | None, str | None, int | None, str | None] | None,
) -> TrackIdentity:
    """构造 unified run 的 track identity（readout_track=unified, native_scope=none）。

    输入:
        method: method registry 名。
        concrete_embedding: 运行时从 ``method.config`` 抽取的
            ``(provider, model, dimension, revision)``；未声明时传 None。

    输出:
        TrackIdentity: unified run 身份；judge/answer model source 反映 unified 不切
            native readout（framework_default）。
    """

    expectation = _resolve_expectation(method)
    embedding = _build_embedding_identity(
        concrete=concrete_embedding,
        distance=expectation.unified_distance,
        revision_status=expectation.unified_revision_status,
    )
    identity = TrackIdentity(
        contract_version=CONTRACT_VERSION,
        implementation_variant=expectation.implementation_variant,
        readout_track="unified",
        native_scope="none",
        build_override_applied=False,
        embedding_profile=expectation.unified_embedding_profile,
        historical_controlled_build_equivalent_to_current_main=(
            expectation.unified_historical_equivalent
        ),
        embedding=embedding,
        judge_source="framework_default",
        answer_model_source="framework_default",
    )
    validate_track_identity(identity)
    return identity


def build_native_track_identity(
    *,
    method: str,
    benchmark: str,
    concrete_embedding: tuple[str | None, str | None, int | None, str | None] | None,
    judge_profile: (
        LightMemNativeJudgeProfile | Mem0NativeJudgeProfile | None
    ),
    native_scope: str = "readout_only",
) -> TrackIdentity:
    """构造 native run 的 track identity（readout_track=native, native_scope=readout_only）。

    输入:
        method: method registry 名。
        benchmark: benchmark registry 名（用于错误信息）。
        concrete_embedding: 运行时从 ``method.config`` 抽取的 embedding 四元组。
        judge_profile: native bundle 的 judge profile；None 表示官方无 LLM judge、回落
            框架 judge → judge_source=framework_fallback。
        native_scope: native 覆盖层级；本卡矩阵恒为 ``readout_only``。

    输出:
        TrackIdentity: native run 身份。

    说明:
        judge_source 由 judge_profile 是否为 None 直接推导，不只靠 None 值散落拼接。
    """

    expectation = _resolve_expectation(method)
    embedding = _build_embedding_identity(
        concrete=concrete_embedding,
        distance=expectation.native_distance,
        revision_status=expectation.native_revision_status,
    )
    judge_source: JudgeSource = (
        "framework_fallback" if judge_profile is None else "official_parity"
    )
    identity = TrackIdentity(
        contract_version=CONTRACT_VERSION,
        implementation_variant=expectation.implementation_variant,
        readout_track="native",
        native_scope=native_scope,  # type: ignore[arg-type]
        build_override_applied=False,
        embedding_profile=expectation.native_embedding_profile,
        historical_controlled_build_equivalent_to_current_main=(
            expectation.native_historical_equivalent
        ),
        embedding=embedding,
        judge_source=judge_source,
        answer_model_source=expectation.answer_model_source_native,
    )
    validate_track_identity(identity)
    return identity


# ----------------------------------------------------------------------
# 运行时强校验
# ----------------------------------------------------------------------


def _require_enum(value: str, allowed: frozenset[str], label: str) -> str:
    """校验字符串属于允许集合，否则 fail-fast。"""

    if not isinstance(value, str) or value not in allowed:
        raise ConfigurationError(
            f"track identity {label}={value!r} not in {sorted(allowed)}"
        )
    return value


def validate_embedding_identity(embedding: EmbeddingIdentity) -> None:
    """强校验 embedding 身份字段，非法组合 fail-fast。"""

    if embedding.revision_status not in _EMBEDDING_REVISION_STATUSES:
        raise ConfigurationError(
            f"embedding revision_status={embedding.revision_status!r} not in "
            f"{sorted(_EMBEDDING_REVISION_STATUSES)}"
        )
    if embedding.identity_status not in _EMBEDDING_IDENTITY_STATUSES:
        raise ConfigurationError(
            f"embedding identity_status={embedding.identity_status!r} not in "
            f"{sorted(_EMBEDDING_IDENTITY_STATUSES)}"
        )
    if embedding.identity_status == "declared":
        if not embedding.model:
            raise ConfigurationError(
                "declared embedding identity requires a non-empty model"
            )
        if not isinstance(embedding.dimension, int) or embedding.dimension <= 0:
            raise ConfigurationError(
                f"declared embedding identity requires dimension>0, got "
                f"{embedding.dimension!r}"
            )
        if not embedding.provider:
            raise ConfigurationError(
                "declared embedding identity requires a non-empty provider"
            )
    else:
        # pending: dimension 可空，但若提供必须 > 0；revision_status 必为 pending。
        if embedding.dimension is not None and (
            not isinstance(embedding.dimension, int) or embedding.dimension <= 0
        ):
            raise ConfigurationError(
                f"pending embedding identity dimension must be >0, got "
                f"{embedding.dimension!r}"
            )


def validate_track_identity(identity: TrackIdentity) -> None:
    """强校验 TrackIdentity 枚举与互斥组合，非法 fail-fast。"""

    _require_enum(
        identity.contract_version, frozenset({CONTRACT_VERSION}), "contract_version"
    )
    _require_enum(
        identity.implementation_variant, _IMPLEMENTMENT_VARIANTS, "implementation_variant"
    )
    _require_enum(identity.readout_track, _READOUT_TRACKS, "readout_track")
    _require_enum(identity.native_scope, _NATIVE_SCOPES, "native_scope")
    _require_enum(
        identity.embedding_profile, _EMBEDDING_PROFILES, "embedding_profile"
    )
    _require_enum(identity.judge_source, _JUDGE_SOURCES, "judge_source")
    _require_enum(
        identity.answer_model_source,
        _ANSWER_MODEL_SOURCES,
        "answer_model_source",
    )
    if not isinstance(identity.build_override_applied, bool):
        raise ConfigurationError(
            f"build_override_applied must be bool, got "
            f"{type(identity.build_override_applied).__name__}"
        )
    # readout_track=native 与 native_scope=none 互斥：native run 不允许否认 native 覆盖。
    if identity.readout_track == "native" and identity.native_scope == "none":
        raise ConfigurationError(
            "native readout_track='native' requires native_scope != 'none'"
        )
    # unified run 不得声明 native 覆盖。
    if identity.readout_track == "unified" and identity.native_scope != "none":
        raise ConfigurationError(
            "unified readout_track requires native_scope='none'"
        )
    validate_embedding_identity(identity.embedding)


# ----------------------------------------------------------------------
# native bundle（readout 资产 + track identity）
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigTrackBundle:
    """一个已批准 native 格的运行时配置覆盖。

    字段:
        answer_prompt_source: native answer prompt 的来源标识。
        answer_llm_settings: native answer LLM 采样配置。
        judge_profile: native judge profile；None 表示官方无 LLM judge。
        embedding_profile: 该 native run 的 embedding 轨道分类（声明用，不生效）。
        declared_unwired_build_reference: 未生效的 build reference 老旧命名；本卡显式
            记录它仅作声明、未被运行时应用。
        build_override_applied: 是否应用了 build 覆盖；恒 False。
        track_identity: native run 的完整不可变身份契约。
    """

    answer_prompt_source: str
    answer_llm_settings: AnswerLLMSettings
    judge_profile: LightMemNativeJudgeProfile | Mem0NativeJudgeProfile | None
    embedding_profile: EmbeddingProfile
    declared_unwired_build_reference: str
    build_override_applied: bool
    track_identity: TrackIdentity


def _lightmem_bundle(benchmark: str, track_identity: TrackIdentity) -> ConfigTrackBundle:
    """由已验收的 LightMem 静态 profile 构造 native bundle。"""

    settings = LIGHTMEM_NATIVE_ANSWER_PROFILES[benchmark].settings
    return ConfigTrackBundle(
        answer_prompt_source="provider_prompt_messages",
        answer_llm_settings=AnswerLLMSettings(
            model=DEFAULT_OPENAI_MODEL,
            message_role="user",
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            top_p=settings.top_p,
        ),
        judge_profile=LIGHTMEM_NATIVE_JUDGE_PROFILES[benchmark],
        embedding_profile=track_identity.embedding_profile,
        declared_unwired_build_reference="lightmem.product_canonical_required_config_v1",
        build_override_applied=False,
        track_identity=track_identity,
    )


def _mem0_bundle(benchmark: str, track_identity: TrackIdentity) -> ConfigTrackBundle:
    """由 Mem0 memory-benchmarks 静态 profile 构造 native bundle。"""

    settings = MEM0_NATIVE_ANSWER_PROFILES[benchmark].settings
    return ConfigTrackBundle(
        answer_prompt_source="provider_prompt_messages",
        answer_llm_settings=AnswerLLMSettings(
            model=DEFAULT_OPENAI_MODEL,
            message_role="user",
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            top_p=settings.top_p,
        ),
        judge_profile=MEM0_NATIVE_JUDGE_PROFILES[benchmark],
        embedding_profile=track_identity.embedding_profile,
        declared_unwired_build_reference="mem0.memory-benchmarks.repo_default",
        build_override_applied=False,
        track_identity=track_identity,
    )


def _memoryos_bundle(track_identity: TrackIdentity) -> ConfigTrackBundle:
    """由 MemoryOS eval readout profile 构造 LoCoMo native bundle。"""

    settings = MEMORYOS_NATIVE_ANSWER_PROFILES["locomo"].settings
    return ConfigTrackBundle(
        answer_prompt_source="provider_prompt_messages",
        answer_llm_settings=settings,
        # 官方评测只有本地 token-set F1；无 method-native LLM judge 资产。
        judge_profile=None,
        embedding_profile=track_identity.embedding_profile,
        declared_unwired_build_reference="memoryos.readout-native.build-profile-not-yet-wired",
        build_override_applied=False,
        track_identity=track_identity,
    )


def _native_bundle(
    method: str,
    benchmark: str,
    concrete_embedding: tuple[str | None, str | None, int | None, str | None] | None,
) -> ConfigTrackBundle:
    """按 method × benchmark 解析 native bundle 并合成完整 track identity。"""

    key = (method.strip().lower(), benchmark.strip().lower())
    if key not in _NATIVE_CONFIG_TRACK_BUNDLES:
        raise ConfigurationError(
            "No native config-track bundle is registered for "
            f"method='{method}', benchmark='{benchmark}'"
        )
    bundle = _NATIVE_CONFIG_TRACK_BUNDLES[key]
    judge_profile = bundle.judge_profile
    track_identity = build_native_track_identity(
        method=method,
        benchmark=benchmark,
        concrete_embedding=concrete_embedding,
        judge_profile=judge_profile,
    )
    return replace(bundle, track_identity=track_identity)


# 静态 readout 资产（不含 track_identity，由 _native_bundle 在运行时合成以注入真实
# embedding）。track_identity 字段先填占位再 replace，保持 dataclass frozen 合法。
_PLACEHOLDER_IDENTITY = TrackIdentity(
    contract_version=CONTRACT_VERSION,
    implementation_variant="product",
    readout_track="native",
    native_scope="readout_only",
    build_override_applied=False,
    embedding_profile="unclassified_pending",
    historical_controlled_build_equivalent_to_current_main=False,
    embedding=EmbeddingIdentity(
        provider=None,
        model=None,
        dimension=None,
        revision=None,
        revision_status="pending",
        normalization=None,
        instruction=None,
        distance=None,
        identity_status="pending",
    ),
    judge_source="framework_fallback",
    answer_model_source="framework_default",
)

_NATIVE_CONFIG_TRACK_BUNDLES: dict[tuple[str, str], ConfigTrackBundle] = {
    ("lightmem", benchmark): _lightmem_bundle(
        benchmark, replace(_PLACEHOLDER_IDENTITY, embedding_profile="product_canonical_required_config_v1")
    )
    for benchmark in ("locomo", "longmemeval")
}
_NATIVE_CONFIG_TRACK_BUNDLES.update(
    {
        ("mem0", benchmark): _mem0_bundle(
            benchmark, replace(_PLACEHOLDER_IDENTITY, embedding_profile="controlled_embedding_v1")
        )
        for benchmark in ("locomo", "longmemeval", "beam")
    }
)
_NATIVE_CONFIG_TRACK_BUNDLES[("memoryos", "locomo")] = _memoryos_bundle(
    replace(_PLACEHOLDER_IDENTITY, embedding_profile="product_default_v1")
)


def resolve_config_track(
    method: str,
    benchmark: str,
    config_track: str,
    concrete_embedding: tuple[str | None, str | None, int | None, str | None] | None = None,
) -> ConfigTrackBundle | None:
    """解析 run 级配置轨；unified 不产生任何覆盖。

    输入:
        method: method registry 名。
        benchmark: benchmark registry 名。
        config_track: ``unified`` 或 ``native``。
        concrete_embedding: 运行时从 ``method.config`` 抽取的 embedding 四元组，用于在
            native bundle 合成真实 embedding 身份；为空时 native bundle 仍返回但
            embedding 为 pending（仅当注册未声明的 method 时）。unified 轨忽略此参数
            （unified 身份由 ``build_unified_track_identity`` 单独合成）。

    输出:
        native 返回带 track_identity 的 bundle；unified 返回 None（保留既有语义）。
    """

    normalized_track = config_track.strip().lower()
    if normalized_track == "unified":
        return None
    if normalized_track != "native":
        raise ConfigurationError(
            "config_track must be one of ['native', 'unified']"
        )
    return _native_bundle(
        method=method,
        benchmark=benchmark,
        concrete_embedding=concrete_embedding,
    )


__all__ = [
    "CONTRACT_VERSION",
    "ConfigTrackBundle",
    "EmbeddingIdentity",
    "TrackIdentity",
    "build_native_track_identity",
    "build_unified_track_identity",
    "resolve_config_track",
    "validate_embedding_identity",
    "validate_track_identity",
]
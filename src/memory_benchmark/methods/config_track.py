"""method 双轨 readout 配置与可验证的 run 身份契约。

注册表负责从当前强类型 method config 解析 build 身份；本模块只组合 build 身份与
unified/native readout 资产，并为 manifest 提供严格的 v1 序列化、解析和校验。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping, TypeAlias, cast, get_args

from memory_benchmark.config.settings import AnswerLLMSettings, DEFAULT_OPENAI_MODEL
from memory_benchmark.core import ConfigurationError
from memory_benchmark.prompts.author.lightmem import (
    LIGHTMEM_NATIVE_ANSWER_PROFILES,
    LIGHTMEM_NATIVE_JUDGE_PROFILES,
    LightMemNativeJudgeProfile,
)
from memory_benchmark.prompts.author.mem0 import (
    MEM0_NATIVE_ANSWER_PROFILES,
    MEM0_NATIVE_JUDGE_PROFILES,
    Mem0NativeJudgeProfile,
)
from memory_benchmark.prompts.author.memoryos import (
    MEMORYOS_NATIVE_ANSWER_PROFILES,
)


TrackContractVersion = Literal["v1"]
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
JudgeModelSource = Literal[
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

LiteralAlias: TypeAlias = Any
CONTRACT_VERSION: TrackContractVersion = cast(
    TrackContractVersion, get_args(TrackContractVersion)[0]
)


def _literal_values(alias: LiteralAlias) -> frozenset[Any]:
    """从 Literal 注解单源派生运行时允许集合。"""

    return frozenset(get_args(alias))


def _require_literal(value: Any, alias: LiteralAlias, label: str) -> Any:
    """校验值属于指定 Literal；错误中给出稳定允许集合。"""

    allowed = _literal_values(alias)
    # 先做精确类型判断，避免 list/dict 等不可哈希输入在集合 membership 处泄漏
    # TypeError；manifest parser 的所有非法输入都应稳定转换为 ConfigurationError。
    if type(value) is not str or value not in allowed:
        raise ConfigurationError(
            f"track identity {label}={value!r} not in {sorted(allowed)}"
        )
    return value


def _require_exact_keys(raw: Mapping[str, Any], expected: frozenset[str], label: str) -> None:
    """拒绝 manifest 对象缺键或携带未声明字段。"""

    non_text_keys = [repr(key) for key in raw if type(key) is not str]
    if non_text_keys:
        raise ConfigurationError(
            f"{label} keys must be strings, got {sorted(non_text_keys)}"
        )
    actual = frozenset(raw)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ConfigurationError(
            f"{label} keys mismatch: missing={missing}, extra={extra}"
        )


def _optional_manifest_text(value: Any, label: str) -> str | None:
    """解析可空文本；非字符串和空白字符串均 fail-fast。"""

    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise ConfigurationError(f"{label} must be null or a non-blank string")
    return value


@dataclass(frozen=True)
class EmbeddingIdentity:
    """method 当前 build 的 concrete embedding 身份。"""

    provider: str | None
    model: str | None
    dimension: int | None
    revision: str | None
    revision_status: EmbeddingRevisionStatus
    normalization: str | None
    instruction: str | None
    distance: str | None
    identity_status: EmbeddingIdentityStatus

    def __post_init__(self) -> None:
        """构造时立即拒绝非法或自相矛盾的 embedding 身份。"""

        validate_embedding_identity(self)

    def to_manifest_dict(self) -> dict[str, Any]:
        """返回可公开写入 manifest 的稳定字典。"""

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

    @classmethod
    def from_manifest_dict(cls, raw: Mapping[str, Any]) -> "EmbeddingIdentity":
        """严格解析 manifest embedding；拒绝缺键、多余键和宽松类型转换。"""

        if not isinstance(raw, Mapping):
            raise ConfigurationError("track identity embedding must be an object")
        _require_exact_keys(
            raw,
            frozenset(
                {
                    "provider",
                    "model",
                    "dimension",
                    "revision",
                    "revision_status",
                    "normalization",
                    "instruction",
                    "distance",
                    "identity_status",
                }
            ),
            "track identity embedding",
        )
        dimension = raw["dimension"]
        if dimension is not None and type(dimension) is not int:
            raise ConfigurationError("embedding dimension must be null or an integer")
        return cls(
            provider=_optional_manifest_text(raw["provider"], "embedding provider"),
            model=_optional_manifest_text(raw["model"], "embedding model"),
            dimension=dimension,
            revision=_optional_manifest_text(raw["revision"], "embedding revision"),
            revision_status=cast(
                EmbeddingRevisionStatus,
                _require_literal(
                    raw["revision_status"],
                    EmbeddingRevisionStatus,
                    "embedding.revision_status",
                ),
            ),
            normalization=_optional_manifest_text(
                raw["normalization"], "embedding normalization"
            ),
            instruction=_optional_manifest_text(
                raw["instruction"], "embedding instruction"
            ),
            distance=_optional_manifest_text(raw["distance"], "embedding distance"),
            identity_status=cast(
                EmbeddingIdentityStatus,
                _require_literal(
                    raw["identity_status"],
                    EmbeddingIdentityStatus,
                    "embedding.identity_status",
                ),
            ),
        )


@dataclass(frozen=True)
class BuildIdentityDeclaration:
    """注册表从当前 config 解析出的单一 build 身份事实源。"""

    implementation_variant: ImplementationVariant
    embedding_profile: EmbeddingProfile
    historical_controlled_build_equivalent_to_current_main: bool
    embedding: EmbeddingIdentity

    def __post_init__(self) -> None:
        """校验注册声明的枚举、布尔类型与 pending 对齐关系。"""

        _require_literal(
            self.implementation_variant,
            ImplementationVariant,
            "implementation_variant",
        )
        _require_literal(self.embedding_profile, EmbeddingProfile, "embedding_profile")
        if type(self.historical_controlled_build_equivalent_to_current_main) is not bool:
            raise ConfigurationError(
                "historical_controlled_build_equivalent_to_current_main must be bool"
            )
        if (
            self.embedding_profile == "unclassified_pending"
            and self.embedding.identity_status != "pending"
        ):
            raise ConfigurationError(
                "unclassified_pending profile requires pending embedding identity"
            )
        if (
            self.embedding_profile != "unclassified_pending"
            and self.embedding.identity_status != "declared"
        ):
            raise ConfigurationError(
                "classified embedding profile requires declared embedding identity"
            )


@dataclass(frozen=True)
class TrackIdentity:
    """run 级 implementation/build/readout/judge 身份契约。"""

    contract_version: TrackContractVersion
    implementation_variant: ImplementationVariant
    readout_track: ReadoutTrack
    native_scope: NativeScope
    build_override_applied: bool
    embedding_profile: EmbeddingProfile
    historical_controlled_build_equivalent_to_current_main: bool
    embedding: EmbeddingIdentity
    judge_source: JudgeSource
    answer_model_source: AnswerModelSource
    judge_model_source: JudgeModelSource

    def __post_init__(self) -> None:
        """构造时立即执行 v1 全量强校验。"""

        validate_track_identity(self)

    def to_manifest_dict(self) -> dict[str, Any]:
        """返回可公开写入 manifest 的稳定字典。"""

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
            "judge_model_source": self.judge_model_source,
        }

    @classmethod
    def from_manifest_dict(cls, raw: Mapping[str, Any]) -> "TrackIdentity":
        """严格解析 v1 track identity，并拒绝未知版本与任意宽松对象。"""

        if not isinstance(raw, Mapping):
            raise ConfigurationError("method.track_identity must be an object")
        _require_exact_keys(
            raw,
            frozenset(
                {
                    "contract_version",
                    "implementation_variant",
                    "readout_track",
                    "native_scope",
                    "build_override_applied",
                    "embedding_profile",
                    "historical_controlled_build_equivalent_to_current_main",
                    "embedding",
                    "judge_source",
                    "answer_model_source",
                    "judge_model_source",
                }
            ),
            "method.track_identity",
        )
        if type(raw["build_override_applied"]) is not bool:
            raise ConfigurationError("build_override_applied must be bool")
        if type(raw["historical_controlled_build_equivalent_to_current_main"]) is not bool:
            raise ConfigurationError(
                "historical_controlled_build_equivalent_to_current_main must be bool"
            )
        embedding_raw = raw["embedding"]
        if not isinstance(embedding_raw, Mapping):
            raise ConfigurationError("method.track_identity.embedding must be an object")
        return cls(
            contract_version=cast(
                TrackContractVersion,
                _require_literal(
                    raw["contract_version"],
                    TrackContractVersion,
                    "contract_version",
                ),
            ),
            implementation_variant=cast(
                ImplementationVariant,
                _require_literal(
                    raw["implementation_variant"],
                    ImplementationVariant,
                    "implementation_variant",
                ),
            ),
            readout_track=cast(
                ReadoutTrack,
                _require_literal(raw["readout_track"], ReadoutTrack, "readout_track"),
            ),
            native_scope=cast(
                NativeScope,
                _require_literal(raw["native_scope"], NativeScope, "native_scope"),
            ),
            build_override_applied=raw["build_override_applied"],
            embedding_profile=cast(
                EmbeddingProfile,
                _require_literal(
                    raw["embedding_profile"], EmbeddingProfile, "embedding_profile"
                ),
            ),
            historical_controlled_build_equivalent_to_current_main=raw[
                "historical_controlled_build_equivalent_to_current_main"
            ],
            embedding=EmbeddingIdentity.from_manifest_dict(embedding_raw),
            judge_source=cast(
                JudgeSource,
                _require_literal(raw["judge_source"], JudgeSource, "judge_source"),
            ),
            answer_model_source=cast(
                AnswerModelSource,
                _require_literal(
                    raw["answer_model_source"],
                    AnswerModelSource,
                    "answer_model_source",
                ),
            ),
            judge_model_source=cast(
                JudgeModelSource,
                _require_literal(
                    raw["judge_model_source"],
                    JudgeModelSource,
                    "judge_model_source",
                ),
            ),
        )


def validate_embedding_identity(embedding: EmbeddingIdentity) -> None:
    """强校验 embedding 字段及 declared/pending 互斥语义。"""

    _require_literal(
        embedding.revision_status,
        EmbeddingRevisionStatus,
        "embedding.revision_status",
    )
    _require_literal(
        embedding.identity_status,
        EmbeddingIdentityStatus,
        "embedding.identity_status",
    )
    for label, value in (
        ("provider", embedding.provider),
        ("model", embedding.model),
        ("revision", embedding.revision),
        ("normalization", embedding.normalization),
        ("instruction", embedding.instruction),
        ("distance", embedding.distance),
    ):
        _optional_manifest_text(value, f"embedding {label}")
        if isinstance(value, str) and value.strip().lower() == "unknown":
            raise ConfigurationError(
                f"embedding {label} must use null instead of the string 'unknown'"
            )
    if embedding.dimension is not None and (
        type(embedding.dimension) is not int or embedding.dimension <= 0
    ):
        raise ConfigurationError(
            f"embedding dimension must be a positive int or null, got {embedding.dimension!r}"
        )
    if embedding.identity_status == "declared":
        if embedding.provider is None or embedding.model is None:
            raise ConfigurationError(
                "declared embedding identity requires non-blank provider and model"
            )
        if embedding.dimension is None:
            raise ConfigurationError(
                "declared embedding identity requires a positive dimension"
            )
        if embedding.revision_status == "pending":
            raise ConfigurationError(
                "declared embedding identity cannot use pending revision_status"
            )
        if embedding.distance is None:
            raise ConfigurationError(
                "declared embedding identity requires a known distance"
            )
    else:
        if embedding.revision_status != "pending":
            raise ConfigurationError(
                "pending embedding identity requires revision_status='pending'"
            )
        if embedding.revision is not None:
            raise ConfigurationError(
                "pending embedding identity cannot claim a concrete revision"
            )


def validate_track_identity(identity: TrackIdentity) -> None:
    """强校验 v1 TrackIdentity 枚举、布尔和 readout 组合。"""

    _require_literal(identity.contract_version, TrackContractVersion, "contract_version")
    _require_literal(
        identity.implementation_variant,
        ImplementationVariant,
        "implementation_variant",
    )
    _require_literal(identity.readout_track, ReadoutTrack, "readout_track")
    _require_literal(identity.native_scope, NativeScope, "native_scope")
    _require_literal(identity.embedding_profile, EmbeddingProfile, "embedding_profile")
    _require_literal(identity.judge_source, JudgeSource, "judge_source")
    _require_literal(
        identity.answer_model_source, AnswerModelSource, "answer_model_source"
    )
    _require_literal(
        identity.judge_model_source, JudgeModelSource, "judge_model_source"
    )
    if type(identity.build_override_applied) is not bool:
        raise ConfigurationError("build_override_applied must be bool")
    if identity.build_override_applied:
        raise ConfigurationError("track identity v1 does not support build override")
    if type(identity.historical_controlled_build_equivalent_to_current_main) is not bool:
        raise ConfigurationError(
            "historical_controlled_build_equivalent_to_current_main must be bool"
        )
    if identity.readout_track == "native" and identity.native_scope != "readout_only":
        raise ConfigurationError(
            "native readout_track requires native_scope='readout_only'"
        )
    if identity.readout_track == "unified" and identity.native_scope != "none":
        raise ConfigurationError("unified readout_track requires native_scope='none'")
    if identity.readout_track == "unified" and (
        identity.judge_source != "framework_default"
        or identity.answer_model_source != "framework_default"
        or identity.judge_model_source != "framework_default"
    ):
        raise ConfigurationError(
            "unified readout requires framework-default answer and judge sources"
        )
    if identity.readout_track == "native" and identity.judge_source == "framework_default":
        raise ConfigurationError(
            "native readout must declare official_parity or framework_fallback judge source"
        )
    if (
        identity.embedding_profile == "unclassified_pending"
        and identity.embedding.identity_status != "pending"
    ):
        raise ConfigurationError(
            "unclassified_pending profile requires pending embedding identity"
        )
    if (
        identity.embedding_profile != "unclassified_pending"
        and identity.embedding.identity_status != "declared"
    ):
        raise ConfigurationError(
            "classified embedding profile requires declared embedding identity"
        )
    validate_embedding_identity(identity.embedding)


@dataclass(frozen=True)
class ConfigTrackBundle:
    """已批准 native readout 资产；不保存或覆盖 build 身份。"""

    answer_prompt_source: str
    answer_llm_settings: AnswerLLMSettings
    judge_profile: LightMemNativeJudgeProfile | Mem0NativeJudgeProfile | None
    judge_source: JudgeSource
    answer_model_source: AnswerModelSource
    judge_model_source: JudgeModelSource

    def __post_init__(self) -> None:
        """校验 readout 来源枚举与 judge profile 的一致性。"""

        _require_literal(self.judge_source, JudgeSource, "bundle.judge_source")
        _require_literal(
            self.answer_model_source,
            AnswerModelSource,
            "bundle.answer_model_source",
        )
        _require_literal(
            self.judge_model_source,
            JudgeModelSource,
            "bundle.judge_model_source",
        )
        if self.judge_source == "framework_fallback" and self.judge_profile is not None:
            raise ConfigurationError(
                "framework_fallback native bundle cannot carry a native judge profile"
            )
        if self.judge_source == "official_parity" and self.judge_profile is None:
            raise ConfigurationError(
                "official_parity native bundle requires a native judge profile"
            )


def build_unified_track_identity(
    *, build_identity: BuildIdentityDeclaration
) -> TrackIdentity:
    """把注册表 build 声明组合为 unified run 身份。"""

    return TrackIdentity(
        contract_version=CONTRACT_VERSION,
        implementation_variant=build_identity.implementation_variant,
        readout_track="unified",
        native_scope="none",
        build_override_applied=False,
        embedding_profile=build_identity.embedding_profile,
        historical_controlled_build_equivalent_to_current_main=(
            build_identity.historical_controlled_build_equivalent_to_current_main
        ),
        embedding=build_identity.embedding,
        judge_source="framework_default",
        answer_model_source="framework_default",
        judge_model_source="framework_default",
    )


def build_native_track_identity(
    *,
    build_identity: BuildIdentityDeclaration,
    bundle: ConfigTrackBundle,
) -> TrackIdentity:
    """把同一次 run 的 build 声明与 native readout 资产组合成身份。"""

    return TrackIdentity(
        contract_version=CONTRACT_VERSION,
        implementation_variant=build_identity.implementation_variant,
        readout_track="native",
        native_scope="readout_only",
        build_override_applied=False,
        embedding_profile=build_identity.embedding_profile,
        historical_controlled_build_equivalent_to_current_main=(
            build_identity.historical_controlled_build_equivalent_to_current_main
        ),
        embedding=build_identity.embedding,
        judge_source=bundle.judge_source,
        answer_model_source=bundle.answer_model_source,
        judge_model_source=bundle.judge_model_source,
    )


def _lightmem_bundle(benchmark: str) -> ConfigTrackBundle:
    """构造 LightMem 官方 readout bundle。"""

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
        judge_source="official_parity",
        answer_model_source="official_parity",
        judge_model_source="official_parity",
    )


def _mem0_bundle(benchmark: str) -> ConfigTrackBundle:
    """构造 Mem0 memory-benchmarks readout bundle。"""

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
        judge_source="official_parity",
        answer_model_source="framework_model_override",
        judge_model_source="framework_model_override",
    )


def _memoryos_bundle() -> ConfigTrackBundle:
    """构造 MemoryOS LoCoMo readout bundle；官方无 LLM judge。"""

    return ConfigTrackBundle(
        answer_prompt_source="provider_prompt_messages",
        answer_llm_settings=MEMORYOS_NATIVE_ANSWER_PROFILES["locomo"].settings,
        judge_profile=None,
        judge_source="framework_fallback",
        answer_model_source="official_parity",
        judge_model_source="framework_default",
    )


_NATIVE_CONFIG_TRACK_BUNDLES: dict[tuple[str, str], ConfigTrackBundle] = {
    ("lightmem", benchmark): _lightmem_bundle(benchmark)
    for benchmark in ("locomo", "longmemeval")
}
_NATIVE_CONFIG_TRACK_BUNDLES.update(
    {
        ("mem0", benchmark): _mem0_bundle(benchmark)
        for benchmark in ("locomo", "longmemeval", "beam")
    }
)
_NATIVE_CONFIG_TRACK_BUNDLES[("memoryos", "locomo")] = _memoryos_bundle()


def resolve_config_track(
    method: str,
    benchmark: str,
    config_track: str,
) -> ConfigTrackBundle | None:
    """解析 readout 配置轨；unified 不返回覆盖，native 仅返回 readout 资产。"""

    normalized_track = config_track.strip().lower()
    if normalized_track == "unified":
        return None
    if normalized_track != "native":
        raise ConfigurationError("config_track must be one of ['native', 'unified']")
    key = (method.strip().lower(), benchmark.strip().lower())
    try:
        return _NATIVE_CONFIG_TRACK_BUNDLES[key]
    except KeyError as exc:
        raise ConfigurationError(
            "No native config-track bundle is registered for "
            f"method='{method}', benchmark='{benchmark}'"
        ) from exc


__all__ = [
    "CONTRACT_VERSION",
    "BuildIdentityDeclaration",
    "ConfigTrackBundle",
    "EmbeddingIdentity",
    "TrackIdentity",
    "build_native_track_identity",
    "build_unified_track_identity",
    "resolve_config_track",
    "validate_embedding_identity",
    "validate_track_identity",
]

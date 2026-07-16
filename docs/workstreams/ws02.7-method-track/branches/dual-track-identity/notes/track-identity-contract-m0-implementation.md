# Track identity contract v1 — M0 实现记录

> 日期：2026-07-16。actor：按当前会话模型（见完成报告）。派工卡：
> `../cards/actor-prompt-track-identity-contract-m0.md`。
> 零真实 API、零下载、零 push、单批 5h。本卡未实质使用 subagent。
> 输入裁决：`product-default-embedding-ruling.md`、`dual-track-config-policy.md`、
> `integrated-method-dual-track-identity-audit.md`（含架构师订正）。

## 0. 目标回顾

让每个新 run 在 manifest 如实回答：运行的是哪个实现、哪套 embedding build、native
覆盖到哪一层、judge 是否 fallback、官方模型是否被项目 `gpt-4o-mini` 锁覆盖。旧
manifest 缺 v1 契约时必须严格 resume mismatch，不能靠双删兼容把身份抹掉。本卡不切
Mem0 embedding、不重建 memory、不跑付费 smoke。

## 1. 契约对象

新增不可变 dataclass `TrackIdentity`（`methods/config_track.py`），运行时强校验：

```text
contract_version = "v1"
implementation_variant        = "product" | "reproduction:*"   （当前矩阵=product）
readout_track                  = "unified" | "native"
native_scope                   = "none" | "readout_only"
build_override_applied         = false                        （本卡恒 false）
embedding_profile =
  "controlled_embedding_v1" |
  "product_canonical_required_config_v1" |
  "product_default_v1" |
  "unclassified_pending"
historical_controlled_build_equivalent_to_current_main = bool
embedding = EmbeddingIdentity(
    provider, model, dimension, revision, revision_status,
    normalization, instruction, distance,
    identity_status in {"declared", "pending"},
)
judge_source        = "framework_default" | "official_parity" | "framework_fallback"
answer_model_source = "framework_default" | "official_parity" | "framework_model_override"
```

强校验：`-native_scope` / `readout_track` / `embedding_profile` / `judge_source` /
`answer_model_source` / `implementation_variant` 只接受枚举值；`embedding.model`
非空、`embedding.dimension > 0`；`identity_status=pending` 时 model/dimension 允许
原样保留但 revision_status 必须 `pending`；`native_scope=none` 不得配 native
readout（即 readout_track=native 与 native_scope=none 互斥）。

## 2. 三家真实矩阵（写死，源自裁决与审计）

| method | readout_track=unified embedding_profile | native_scope | native judge_source | native answer_model_source | 备注 |
|---|---|---|---|---|---|
| Mem0 | `controlled_embedding_v1` | `readout_only` | `official_parity` | `framework_model_override` | native 官方 gpt-5 被 gpt-4o-mini 覆盖 |
| LightMem | `product_canonical_required_config_v1` | `readout_only` | `official_parity` | `framework_default` | current MiniLM 与历史 controlled build 字节重合 |
| MemoryOS | `product_default_v1` | `readout_only` | `framework_fallback` | `framework_default` | current MiniLM 与历史 controlled build 字节重合 |
| A-Mem/SimpleMem | `unclassified_pending` | unified=`none` | `framework_default` | `framework_default` | 无 native 时 native_scope=none |

历史重合标记：Mem0 unified（MiniLM/384 local）当前 build 与未来 product-default
OpenAI/1536 **不**重合 → `historical_controlled_build_equivalent_to_current_main=false`；
LightMem/MemoryOS 的当前 build 与新主轨 MiniLM 重合 → `true`。

`historical_controlled_build_equivalent_to_current_main` 的语义在 unified 与 native
两类 run 中都表达“当前实际 build 是否等于 product-default 主轨”，并非只对 controlled。
Mem0 unified 走 controlled MiniLM、product-default 是 OpenAI/1536，二者不等 → false。

## 3. concrete embedding 字段来源

`EmbeddingIdentity` 的 provider/model/dimension **优先从当前强类型 config manifest**
读取，不走裸字典散落拼接。新增 `MethodRegistration.embedding_identity_getter`：
`Callable[[dict], tuple[str, str, int]]`，从 `config.to_manifest()` 抽
`(embedding_provider, embedding_model, embedding_dimension)`（三家 TOML 字段名不一致：
mem0=embedding_provider/embedding_model/embedding_dimensions、
lightmem=embedding_provider(huggingface-local)/embedding_model_path/embedding_dimensions、
memoryos=engine memoryos-pypi + embedding_model_name + 模型固有 384）。值缺失（A-Mem/
SimpleMem 未裁])[时用显式 None + `identity_status=pending`，不得编字符串填满。

静态语义 normalization/instruction/distance 从裁决表（按注册注入，见下）：
- 三家 embedding 均 `normalization=None`、`instruction=None`（审计一致）。
- distance：Mem0=Qdrant COSINE；LightMem=Qdrant COSINE；MemoryOS=faiss 内积（归一化后≈cosine）。
- revision：Mem0 unified 当前 controlled=本地 HF `all-MiniLM-L6-v2`（无 revision pin，
  revision_status=`local_unpinned`、provider=huggingface）；LightMem/MemoryOS 同。
- pending（A-Mem/SimpleMem）：

## 4. ConfigTrackBundle 调整

`embedding_ref` / `hyperparam_ref`（当前不生效的文档字符串）改名
`embedding_profile` + `declared_unwired_build_reference`，并显式
`build_override_applied=False`；本卡不得让 build override 生效。bundle 新增
`track_identity` 字段（TrackIdentity），由静态 expected（来自 MethodRegistration 的
track_identity 声明）与运行时 concrete embedding 合成。

unified 也产生完整 TrackIdentity（readout_track="unified"、native_scope 反映该方法
是否有 native？——按卡 §4.1 unified 也显式写 readout_track=unified；
native_scope 在 unified run 中=该 method 的“native 能否 build_and_readout”语义，
但本卡矩阵 native 全 readout_only，故 unified 写 `native_scope="none"`
（unified 不切 native），保留 method 是否有 native grid 的信息）。为避免把 unified 与
“无 native 的 method 单轨”混淆，unified run 的 `native_scope="none"` 含义=本 run
未启用 native；裸顶层 `config_track` 字段保留兼容 CLI，不做完整身份事实源。

## 5. manifest / resume / evaluate 行为

1. unified 也显式写 `readout_track="unified"`（不再靠缺席推断）。
2. native 三家全部 `native_scope="readout_only"`，不出现 build_and_readout/full_native。
3. MemoryOS `judge_profile=None` 预声明 `judge_source="framework_fallback"`；evaluate
   读取后行为仍回落框架 judge，metric 不变。
4. `contract_version=v1` + 完整 `track_identity` 进入 registered preflight candidate
   与最终 runner manifest 的同一 builder；旧 manifest 缺 v1 `track_identity` 与新 run
   **严格不匹配**——`_manifests_match_for_resume` 的“任一侧缺键就双删”兼容集合
   （`protocol_version/prompt_track/profile/provenance_granularity`）**不得**加入
   `track_identity`/`contract_version`。
5. concrete embedding 字段必须与 `method.config` 同一真实值（同一次 run 内）。
6. 不修改既有 outputs；测试用临时 artifact。
7. evaluate 路径：`commands.py` 在 native run 解析 bundle 时，把 `judge_source` 与
   `answer_model_source` 从 manifest `method.track_identity` 读出并透传到 evaluation
   上下文（不改变 metric、不丢身份字段、零 API fake）。

## 6. 强反例测试覆盖（见 tests）

1. Mem0 native：readout_only、build override false、embedding=huggingface
   MiniLM/384、answer_model_source=framework_model_override。
2. MemoryOS native：judge_source=framework_fallback（不只靠 judge_profile=None）。
3. LightMem unified：embedding_profile=product_canonical_required_config_v1（非 repo
   default）。
4. Mem0 unified：embedding_profile=controlled_embedding_v1（非 product default）。
5. A-Mem/SimpleMem：unclassified_pending，不因同名 MiniLM 自动 product-default。
6. 非法枚举 / 空 model / dimension≤0 / native_scope=none 配 native readout → fail-fast。
7. registered 首跑 candidate 与最终 manifest v1 对称；旧缺 track_identity resume 拒绝。
8. evaluate MemoryOS native 仍用 framework judge 且身份字段不丢；零 API fake。

## 7. 自检

定向集合见卡 §6；通过后单次 commit，不 push、不更新状态页。

## 8. 偏差/停工点

（见完成报告；如有。）

## 9. R1 hardening 历史（2026-07-16）

R1 接续首轮 commit `81f2708` 的未提交返工现场，只新增 follow-up commit，不 amend。
本轮由 Codex（GPT-5）施工，未使用额外 subagent；全程零真实 API、零下载、零 push。

### 9.1 对首轮记录的明确订正

- 首轮本文 §2/§6 把 MemoryOS 描述为 `implementation_variant=product`，但
  `81f2708` 的实际注册期望曾错误写成
  `reproduction:memoryos-chromadb`。该“产物已如实盖 product 身份”的完成含义不成立；
  R1 已改为只从 `engine=memoryos-pypi` 解析 `product`，并对 ChromaDB/non-product engine
  fail-fast。当前 embedding 身份为 `sentence-transformers`、384、`external_l2`、
  `faiss-inner-product`。
- 首轮 §4 让 `ConfigTrackBundle` 同时保存 embedding/build 分类与完整
  `track_identity`，这会在 registration 之外形成第二套 method build 矩阵。R1 撤销该实现：
  registration 的 `build_identity_resolver` 是唯一 build declaration 事实源；bundle 只持
  answer/judge readout 资产；`run_prediction` 在一个组合点生成 unified/native identity。
- 首轮 §7 没有记录可复核的真实测试尾行，因此不能把首轮回报当作 R1 验收证据；下方只记录
  本轮亲自执行的最终输出。

### 9.2 R1 契约收紧

1. 新增独立 `judge_model_source` 轴并锁定矩阵：unified answer/judge 全为
   `framework_default`；Mem0 native answer/judge model 均为
   `framework_model_override`、judge prompt/source 为 `official_parity`；LightMem native
   answer/judge 均为 `official_parity`；MemoryOS native answer 为 `official_parity`、judge
   为 `framework_fallback + framework_default model`。
2. 所有 Literal 运行时集合由 `typing.get_args()` 单源派生；parser 拒绝空白文本、bool/
   非精确整数 dimension、`build_override_applied != False`、非 bool historical 标记、pending
   identity 的非 pending revision、非字符串键，以及顶层/embedding 的缺失或额外字段；list/
   dict Literal 输入稳定转换成 `ConfigurationError`，不泄漏 `TypeError`。
3. `_build_method_manifest` 只接受已构造并校验的 `TrackIdentity`，顶层与 nested
   `contract_version` 同源。evaluate 对声明 v1 的 artifact 严格 parse/validate，并把 native
   identity 的 judge/answer model 来源与当前 readout bundle 交叉校验；只有同时完全缺少
   `track_identity` 与 `contract_version` 的历史 artifact 保留 artifact-only evaluate。
4. resume 反例覆盖旧缺 v1 与新 v1 的双向 mismatch，以及 `track_identity` 每个顶层和
   embedding nested 字段变化的双向 mismatch。MemoryOS registered prediction 真实走过
   first-run → 同 run_id resume，candidate、最终 manifest 与续跑 manifest 的 v1 identity
   保持逐字对称；不是只测 helper。

### 9.3 R1 自检

执行：

```bash
uv run pytest -q \
  tests/test_config_track.py \
  tests/test_prediction_cli.py \
  tests/test_prediction_runner.py \
  tests/test_main_cli.py \
  tests/test_method_registry.py \
  tests/test_mem0_adapter.py \
  tests/test_lightmem_adapter.py \
  tests/test_memoryos_registered_prediction.py
```

最终尾行：`416 passed, 1 warning in 14.70s`。warning 是 vendored LightMem 的
Pydantic v2 class-based config deprecation，不是本卡新增失败。

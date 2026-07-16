# 三家 embedding 主轨与实现身份裁决

> 日期：2026-07-16。裁决者：GPT-5.6 sol（架构师）。
> 输入证据：`integrated-method-dual-track-identity-audit.md`；架构师逐锚复核 Mem0 默认、
> LightMem config/factory、MemoryOS PyPI/ChromaDB 分叉及当前 manifest。
> 本文是审计回卡后的现行裁决，不修改受保护 outputs，也不授权真实 API。

## 0. 结论

| method | unified 主 build identity | 当前 build 是否重建 | 关键限制 |
|---|---|---:|---|
| Mem0 | `product_default_v1`：OpenAI `text-embedding-3-small`、1536、Qdrant cosine；revision status=`provider_managed_unpinned` | **是** | 托管模型无权重 revision pin；真实重建须用户批预算 |
| LightMem | `product_canonical_required_config_v1`：HuggingFace local `all-MiniLM-L6-v2`、384、Qdrant cosine | **否** | 不是顶层 `repo_default`；它是无零配置可运行默认时的官方 canonical 必填配置 |
| MemoryOS | `product_default_v1`：SentenceTransformer `all-MiniLM-L6-v2`、384、外部 L2 normalize + FAISS IP | **否** | 裸名与限定名须用本地模型 hash/解析身份证明等价 |

2026-07-09 shared MiniLM 历史结果继续保留。Mem0 既有结果只能称
`controlled_embedding_v1`；LightMem/MemoryOS 的实际模型恰与新主轨重合，旧产物仍保留历史
controlled 身份，但无需为相同 build 字节重烧，可在新报告声明
`historical_controlled_build_equivalent_to_current_main=true`。

## 1. 没有可运行默认时的操作化规则

`product default` 不是机械读取一个 dataclass 字段。按以下证据优先级解析：

1. 通用产品入口存在无覆盖且可运行的构造默认 → 锁该默认；
2. 某能力是产品运行必填、顶层故意不设默认 → 锁官方通用 quickstart 的唯一 canonical 配置；
3. quickstart 仍是路径占位符 → 只有当官方 backend 内部缺省与官方 experiments/paper 对该轴
   一致时，才可裁为 `product_canonical_required_config`；
4. 候选仍冲突 → `SOURCE_UNDETERMINED`，不得自行找近似模型。

LightMem 命中第 3 条：顶层 `text_embedder=None` 配合默认 embedding retrieval 不可运行；HF
backend 缺省 `all-MiniLM-L6-v2`，LoCoMo/LME 官方配置与 paper 又一致使用 MiniLM。因此锁
HF local MiniLM，但**名称必须是 product canonical required config，禁止再写
`lightmem.repo_default.*`**。

## 2. 三家逐项裁决

### 2.1 Mem0

- 通用 OSS 产品默认 provider/model/dimension 已由源码闭合；跨五 benchmark 固定同一 profile。
- OpenAI 托管模型只能记录 `provider/model/base_url_identity/run_timestamp`；不能伪造 revision。
  manifest 应写 `revision_status=provider_managed_unpinned`。
- 迁移从 local MiniLM/384 到 remote OpenAI/1536 改变 build/retrieve，必须新 run_id 全量重建；
  B8+ 与 B11 重开。B3/B4/B5 的结构结论可继承，但新 smoke artifact 必须重新产出。
- 在 run identity contract 落地前不切配置；在用户确认预算、规模、run_id 前不调用 API。

### 2.2 LightMem

- P1 已关闭：主轨锁 `product_canonical_required_config_v1`，实际值与当前 MiniLM build 重合。
- 不重建、不重跑只是因为实际 build 字节重合，不是因为旧 manifest 已经正确；新 run 必须盖
  canonical identity，本地模型目录 hash/revision 仍须补齐。
- LoCoMo harness-local brute-force cosine 是 retrieval implementation 资产，不把它伪装成
  TOML-only native；当前 native 仍是 readout-only。

### 2.3 MemoryOS

- Phase 1 继续 `memoryos-pypi` canonical；当前 embedding 与签名默认解析为同一模型，零重建。
- `memoryos-chromadb` 改了检索、合并、heat/LTM、持久化和异常语义，裁为
  `reproduction_variant:memoryos-chromadb`，不进入普通 native/config-track。
- 若未来接入该 variant，B3/B4/B5/B6/B8/B11 六门全部重开；当前阶段不排入 smoke 主线。

## 3. native 身份硬门

当前 `config_track=native` 只让 answer/judge readout 资产部分生效，`embedding_ref` 与
`hyperparam_ref` 未应用、未进 manifest。三家既有 native 产物的真实身份是：

`readout_native + current_build`，而不是 full-native。

因此在任何新付费/native smoke 前，必须先落 `track_identity_contract_v1`，至少声明：

- `implementation_variant`；
- `readout_track` 与 `native_scope`；
- `build_override_applied`；
- embedding profile + provider/model/dimension/revision status/normalization/instruction/distance；
- `judge_source` 与 answer/judge model override。

旧 outputs 不改写；报告侧按本裁决重标，旧 manifest 不允许无痕 resume 到新契约。

## 4. 退出条件与下一动作

1. `track_identity_contract_v1` 离线实现、强反例、strict resume 门通过；
2. 再写 Mem0 product-default build-profile 迁移卡，并保留 controlled profile 的正交选择；
3. 用户批准预算后才重跑 Mem0 product-default smoke；LightMem/MemoryOS 不因模型字节相同重复
   烧 API，只补身份后继续各自未完成的 B11/M1 门。

消费者：B9/B10/B11、compact 恢复胶囊、三家 integration 实例页。退出后本文转稳定判例，
活跃动作仍只看父 ws02.7 README。

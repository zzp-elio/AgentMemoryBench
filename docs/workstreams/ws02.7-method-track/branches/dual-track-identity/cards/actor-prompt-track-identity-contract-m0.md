# Actor 卡：双轨 run identity 真实性契约 M0

> **给当前 actor 的直接执行指令：你就是用户已选中的执行者。**本卡被发送到当前会话即
> 代表用户已完成选择与授权，请直接施工；不要再选择、派发或等待另一个跨产品 actor。
> 是否使用当前执行环境自己的 subagent 由你判断；不得扩大 scope，实质使用时须在回报中
> 说明。单批上限 5h；全程离线、零真实 API、零下载、不 push。

## 0. 白话目标

现在 CLI 路径叫 `config_track=native`，但三家实际只切了 answer/judge readout；embedding 与
method 内部 build 参数没有切换。manifest 只写一个裸 `native`，容易把 readout-only 误读成
full-native。本卡先让**产物说真话**，不切 Mem0 embedding、不重建 memory、不跑付费 smoke。

最终每个新 run 都要明确回答：运行的是哪个实现、哪套 embedding build、native 覆盖到哪一
层、judge 是否 fallback、官方模型是否被项目 `gpt-4o-mini` 锁覆盖。旧 manifest 缺新契约时
必须 strict resume mismatch，不能靠兼容双删把身份抹掉。

## 1. 上工、隔离与最小读序

```bash
cd /Users/wz/Desktop/memoryBenchmark
git status --short
git worktree add -b actor/track-identity-contract-m0 \
  /Users/wz/Desktop/mb-actor-track-identity-m0 main
cd /Users/wz/Desktop/mb-actor-track-identity-m0
```

若 branch/worktree 已存在或 main 不是最新，停工回报；不 reset、不删除来源不明现场。

按顺序读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点；
3. `docs/workstreams/ws02.7-method-track/branches/dual-track-identity/README.md`；
4. 本卡全文；
5. `docs/reference/actor-handbook.md` §0-§4、§6-§7；
6. `docs/reference/dual-track-config-policy.md` §0-§3；
7. `docs/workstreams/ws02.7-method-track/branches/dual-track-identity/notes/integrated-method-dual-track-identity-audit.md` §0、§5；
8. `docs/workstreams/ws02.7-method-track/branches/dual-track-identity/notes/product-default-embedding-ruling.md` 全文；
9. 当前 `src/memory_benchmark/methods/config_track.py`、registered prediction
   manifest/preflight/resume 链与下列测试。

## 2. 允许修改范围

- `src/memory_benchmark/methods/config_track.py`；
- `src/memory_benchmark/methods/registry.py`（仅注册静态 build identity 所需）；
- `src/memory_benchmark/cli/run_prediction.py`；
- `src/memory_benchmark/cli/commands.py`（仅让 evaluate 消费/保留同一 judge source 身份）；
- `tests/test_config_track.py`；
- `tests/test_prediction_cli.py`；
- `tests/test_main_cli.py`；
- `tests/test_method_registry.py`；
- 已存在且确有必要的三家 registered prediction 测试：
  `tests/test_memoryos_registered_prediction.py`、`tests/test_lightmem_registered_prediction.py`、
  `tests/test_membench_registered_prediction.py`；不得新建空壳测试文件；
- 新增 `docs/workstreams/ws02.7-method-track/branches/dual-track-identity/notes/track-identity-contract-m0-implementation.md`。

不得改 TOML、adapter 算法、third_party、outputs、policy/checklist/README、evaluator metric 语义。

## 3. 已裁 v1 契约

新增不可变、运行时强校验的 track identity（具体 dataclass 名可按现有风格，但不得用裸 dict
散落拼接），最终写入 `method.track_identity`：

```text
contract_version = "v1"
implementation_variant = "product"
readout_track = "unified" | "native"
native_scope = "none" | "readout_only"
build_override_applied = false
embedding_profile =
  "controlled_embedding_v1" |
  "product_canonical_required_config_v1" |
  "product_default_v1" |
  "unclassified_pending"
historical_controlled_build_equivalent_to_current_main = bool
embedding = {provider, model, dimension, revision, revision_status,
             normalization, instruction, distance}
judge_source = "framework_default" | "official_parity" | "framework_fallback"
answer_model_source = "framework_default" | "official_parity" | "framework_model_override"
```

当前真实矩阵写死为：

| method | unified embedding_profile | native_scope | native judge | 备注 |
|---|---|---|---|---|
| Mem0 | `controlled_embedding_v1` | `readout_only` | `official_parity` | native 官方 gpt-5 被 gpt-4o-mini 覆盖，answer model source=override |
| LightMem | `product_canonical_required_config_v1` | `readout_only` | `official_parity` | current MiniLM 与历史 controlled build 字节重合 |
| MemoryOS | `product_default_v1` | `readout_only` | `framework_fallback` | current MiniLM 与历史 controlled build 字节重合 |
| A-Mem/SimpleMem | `unclassified_pending` | 无 native 时 `none` | framework default | 等各自 M 阶段，不臆造 product identity |

具体 provider/model/dimension 优先从当前强类型 config manifest 读取，静态语义
normalization/instruction/distance 从 method 注册声明注入。值缺失就用显式 `null +
revision_status/identity_status=pending`，不得编字符串填满。

`ConfigTrackBundle.embedding_ref/hyperparam_ref` 当前是不生效的文档字符串：将其改成不会误导的
`declared_unwired_build_reference`（或等价单字段），并显式 `build_override_applied=False`；禁止
本卡顺手让 build override 生效。

## 4. manifest / resume / evaluate 行为

1. unified 也显式写 `readout_track=unified`，不再靠字段缺席推断；旧顶层
   `config_track` 可暂留兼容 CLI，但不得作为完整身份事实源。
2. native 三家全部写 `native_scope=readout_only`，不得出现 `build_and_readout/full_native`。
3. MemoryOS `judge_profile=None` 必须在预测 manifest 预声明 `judge_source=framework_fallback`；
   evaluate 读取后行为仍回落框架 judge，不改变 metric。
4. `contract_version=v1` 进入 registered preflight candidate 与最终 runner manifest 的同一
   builder；旧 manifest 缺 v1 与新 run **严格不匹配**，不得加入“任一侧缺失就双删”集合。
5. concrete embedding 字段必须与 `method.config` 同一真实值；不得把未来 Mem0
   text-embedding-3-small 提前写进当前 MiniLM run。
6. 不修改既有 outputs；测试用临时 artifact。

## 5. 必测强反例

至少覆盖：

1. Mem0 native：`config_track=native` 但 `native_scope=readout_only`、build override false、
   embedding 仍是当前 huggingface MiniLM/384，且 answer model source=framework override；
2. MemoryOS native：judge source 明确 framework fallback，不能只靠 `judge_profile=None`；
3. LightMem unified：profile 是 product canonical required config，不是 repo default；
4. Mem0 unified：profile 仍 controlled，不能提前冒充 product default；
5. A-Mem/SimpleMem：pending，不因 all-MiniLM 名称相同自动盖 product-default；
6. 非法枚举、空 model、dimension≤0、`native_scope=none` 配 native readout 等组合 fail-fast；
7. registered 首跑 candidate 与最终 manifest v1 对称；旧缺 v1 resume 明确拒绝；
8. evaluate MemoryOS native 仍使用 framework judge，且身份字段不丢；零 API fake。

若真实 manifest 构造链需要一个未列入允许范围的**既有**测试文件，先写停点回报，不自行扩大。

## 6. 自检、提交与报告

只跑一次卡内定向集合（按实际改动保留所有非空文件）：

```bash
uv run pytest -q \
  tests/test_config_track.py \
  tests/test_prediction_cli.py \
  tests/test_main_cli.py \
  tests/test_method_registry.py \
  tests/test_mem0_adapter.py \
  tests/test_lightmem_adapter.py \
  tests/test_memoryos_registered_prediction.py
git diff --check
```

`git status --short` 过目后只显式 add 实际改动路径，禁止 `git add -A`/`.`。提交：

```bash
git commit -m "feat(runs): stamp truthful track identity"
```

到此停止，不 push、不更新状态。按 actor-handbook §4 回报 commit hash、测试尾行原文、实际文件、
偏差/停工点和 subagent 分工。commit author/trailer 必须按当前会话真实模型填写；不确定就不写
猜测的 `Co-Authored-By`。

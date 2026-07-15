# Actor 卡：RetrievalEvidence M0（协议与 artifact plumbing）

> **给当前 actor 的执行指令：你就是用户已选中的执行者。** 本卡被发送到当前会话即代表
> 用户已经完成选择与授权，请直接按卡施工；不要再询问由谁派发，也不要另派 actor。
> 仓库侧的前置依赖与可派时机只看本支线 README，不属于 actor 收卡后的二次决策。
> 本卡本身就是可整份复制的 prompt；单批上限 5h、零真实 API。
> 目标只做 M0 plumbing，**不切 evaluator、不修 LongMemEval 分母、不改 top_k**；M1 必须
> 等本卡经架构师强验收合入后再派。
> 前置依赖一已满足：LightMem online-soft 卡已强验收合入主线 `825132f`。
> 新前置依赖：`../../membench-time-semantics/` Phase A 已强验收；Phase B
> `actor-prompt-lightmem-missing-time-online-soft.md` 仍须强验收合入。否则本卡会在
> LightMem adapter version/manifest/lineage 尚可能变化时声明 retrieval contract。

## 0. 上工与隔离

按顺序只读以下最小集合：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部“Codex 恢复胶囊”；
3. 本卡全文；
4. `docs/reference/actor-handbook.md` §0-§4；
5. `docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
   retrieval-metric-eligibility-ruling.md` §1、§3-§4、§7；
6. `docs/workstreams/ws02.7-method-track/branches/lightmem-lifecycle/notes/
   lightmem-update-lifecycle-ruling.md` §3-§5、§7；
7. `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/README.md`；
8. `src/memory_benchmark/core/provider_protocol.py` 的 retrieval 实体；
9. `src/memory_benchmark/runners/prediction.py::_answer_question_retrieve_first` 与
   `operation_level.py::_answer_prompt_record`。

从届时 `main` 新建；路径/分支已存在就停工，不删、不复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-retrieval-evidence-m0 \
  -b actor/retrieval-evidence-contract-m0 main
cd /Users/wz/Desktop/mb-actor-retrieval-evidence-m0
uv sync
```

允许修改：

- `src/memory_benchmark/core/provider_protocol.py`；
- `src/memory_benchmark/core/__init__.py`；
- `src/memory_benchmark/methods/registry.py`；
- `src/memory_benchmark/methods/{mem0,lightmem,memoryos}_adapter.py`；
- `src/memory_benchmark/cli/run_prediction.py`（只传 operation-level contract version）；
- `src/memory_benchmark/runners/{prediction,operation_level}.py`；
- 与上述行为直接对应的现有 `tests/test_{provider_protocol,prediction_runner,
  operation_level_runner,mem0_adapter,lightmem_adapter,memoryos_adapter}.py`；
- `tests/test_halumem_registered_prediction.py`（只锁 registered operation-level manifest）；
- 新建 `docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
  retrieval-evidence-contract-m0.md`。

禁止改 evaluator、CLI 其他模块、TOML、third_party、其他 method、README/status/
checklist、outputs；不得 push。若真实文件名与允许清单不符，先停工，不自行扩表。

## 1. 已裁数据模型（不得换成 per-metric 白名单）

在 `provider_protocol.py` 增加并公开导出以下三个 frozen dataclass/type；命名可按同目录
风格做不改变语义的微调，note 必须写最终名字：

1. `RetrievalEvidenceStatus = Literal["valid", "n_a", "pending"]`；
2. `EvidenceAssertion`：字段为 `status`、`reason_code: str | None`、
   `reason: str | None`；
3. `RetrievalEvidence`：字段为
   `semantic_provenance: EvidenceAssertion`、
   `provenance_granularity: ProvenanceGranularity`、
   `stable_ranking: EvidenceAssertion`。

校验契约：

- assertion=`valid` 时 reason_code/reason 必须都为 None；
- assertion=`n_a|pending` 时 reason_code/reason 必须都是非空字符串；
- semantic provenance=`valid` 时 granularity 只能是 `turn|session`；非 valid 时必须
  为 `none`；
- reason 是公开 artifact 字段，走既有 private-key validator；
- `RetrievalResult` 新增
  `evidence: RetrievalEvidence | None = None`，None 只为旧自定义 provider/旧测试兼容，
  不能成为下面三家注册 method 的生产返回值。

不要新增 `metric_name`、benchmark 白名单或 evaluator 判定字段。provider 只陈述事实。

## 2. Artifact 与 manifest plumbing

### 2.1 Answer prompt artifact

两条 runner 都新增顶层 `retrieval_evidence`：

- 有 evidence 时用 `dataclasses.asdict()` 原样序列化；
- 无 evidence 时写 `null`，不能偷读旧 manifest 拼一个假的逐题值；
- prediction 现有 `retrieved_items`/`retrieval_query_top_k` 不改；
- operation-level 只加 evidence，不趁机发明 `retrieval_query_top_k`。

### 2.2 Contract version

`MethodRegistration` 新增可选静态字段
`retrieval_evidence_contract_version: str | None = None`。Mem0、LightMem、MemoryOS 三个
注册项显式写 `"v1"`；其余 method 保持 None。`_method_manifest_with_protocol()` 在
registry 可解析到非 None 时，把该值写入 `manifest["method"]`，isolated worker 根对象
不构造真实 method 也必须能盖章。

该 version 是 resume identity：**不要**把它加进“任一侧缺失就双删”的旧兼容键集合。
旧 run 缺 version 与新 v1 run 必须 resume mismatch，避免同一 artifact 混入有/无逐题
contract 的记录。补锁定测试。

## 3. 三家 adapter 的逐题事实

三家当前尚未完成逐 method rank 审计，所以 `stable_ranking` 一律：

```text
status="pending"
reason_code="ranking_fidelity_not_audited"
reason="provider result order has not passed the method-specific ranking audit"
```

不得因为列表“看起来有序”提前改 valid。

### 3.1 Mem0

复用已有显式 `self.benchmark_name`，不得从数据形态猜 benchmark：

- `locomo`、`membench`：semantic provenance valid + turn；
- `longmemeval`、`halumem`：valid + session；LongMemEval adapter 内两 turn chunk 的
  source ids 向上同属一个 session，不得声明 turn；
- `beam`：n_a + none，reason_code=`ingest_batch_coarser_than_gold`，reason 说明 pair
  source union 无法无损归因到每条 extracted fact；
- benchmark_name 缺失/未知：pending + none，reason_code=`benchmark_identity_missing`。

sidecar 缺映射仍维持既有 fail-fast；不要把它降级成 n_a。空检索但机制完整仍返回上述
valid contract，不把真实 0 hit 当 provenance 缺失。

### 3.2 LightMem

复用前置 lifecycle 卡已经显式注入的 `self.benchmark_name`；不使用 source_path/问题时间
启发式决定资格。资格同时取决于实际 lifecycle：

- `lifecycle_profile="online_soft"` + 任一已注册 benchmark：当 adapter 内部算出的
  `items is not None` 时 valid + turn；`items is None` 时 n_a + none，reason_code=
  `retrieval_hit_lineage_incomplete`；
- `lifecycle_profile="locomo_offline_consolidated"` + `locomo`：恒为 n_a + none，
  reason_code=`semantic_mapping_unavailable_after_mutation`，reason 说明 post-build
  consolidation 不提供 output-to-source mapping；
- benchmark_name 缺失/未知：pending + none，reason_code=`benchmark_identity_missing`。

本卡只描述**已经通过输入兼容门并实际发生 retrieval** 的逐题事实，不把 method 能否
诚实 ingest 某 variant 解释为 retrieval evidence。MemBench 100k 输入门由前置支线裁定，
本卡不得顺手造 timestamp 或建立 variant 白名单。

注意空 tuple 与 None 不同：`items=()` 是检索 0 hit、仍可 valid；None 才是本次 lineage
不可用。不要改 LightMem lifecycle、update/insert/merge 算法；若前置卡尚未合入，立即
停工，不能在本卡顺手补。

### 3.3 MemoryOS

复用已有显式 `self.benchmark_name`。现有 page sidecar 缺失仍 fail-fast；已注册 benchmark
返回 valid + turn，identity 缺失/未知返回 pending + none
（`benchmark_identity_missing`）。不得在本卡重审或改 page 映射算法。

## 4. 必测反例

至少锁定：

1. dataclass 的三组非法组合都 fail-fast；合法值可 `asdict()` 且无私有字段；
2. prediction 与 operation-level artifact 都写逐题 `retrieval_evidence`；
3. 三家注册/isolated manifest 均写 version v1，A-Mem/SimpleMem 不写；
4. v1 manifest 与旧缺 version manifest 拒绝 resume；
5. Mem0 五 benchmark 的 turn/session/n_a 矩阵，BEAM reason code 精确；
6. LightMem `online_soft` 五格的 `items=()` 为 valid、`items=None` 为 n_a；
   `locomo_offline_consolidated` 即使 items 完整也 n_a；复用 factory 的 benchmark_name；
7. MemoryOS 已知 benchmark valid(turn)，未知 identity pending；
8. 三家 stable_ranking 都是 pending，禁止某家误盖 valid。

所有新增/修改的 Python 模块、类、函数、嵌套 helper 与测试函数都带中文 docstring。

## 5. 明确不做

- 不改 5 个 retrieval evaluator；
- 不修 LongMemEval empty-gold/no-target 分母；
- 不改 `RetrievalQuery.top_k=10`，不新增第二次 retrieve；
- 不建立 method × benchmark × metric eligibility 表；
- 不把旧 `provenance_granularity` 字段删掉或重解释；M1 才迁 evaluator；
- 不改 LightMem lifecycle profile 或 TOML；
- 不跑真实 API、不下载数据/模型、不更新 frozen/status 文档。

## 6. 停工条件

- 逐题 evidence 无法在不改 evaluator/CLI 的前提下写入两条 artifact；
- registered isolated manifest 无法只靠现有 `system_factory` identity 盖 version；
- 任一 adapter 必须改 third_party 算法才能生成上述事实；
- 前置 LightMem lifecycle profile/card 未在 main 合入，或字段/取值与本卡不一致；
- LightMem missing-time Phase B 尚未由架构师强验收合入；
- 发现本裁决矩阵与生产 benchmark_name/ingest 路径矛盾；
- 定向测试失败且 15 分钟内不能定位。

命中后在 note 写停工点，提交当前可审证据后停止，不自行扩 scope。

## 7. 唯一自检、commit 与回报

只跑一次：

```bash
uv run pytest -q \
  tests/test_provider_protocol.py \
  tests/test_prediction_runner.py \
  tests/test_operation_level_runner.py \
  tests/test_halumem_registered_prediction.py \
  tests/test_mem0_adapter.py \
  tests/test_lightmem_adapter.py \
  tests/test_memoryos_adapter.py
```

通过后：

```bash
git diff --check
git status --short
git add \
  src/memory_benchmark/core/provider_protocol.py \
  src/memory_benchmark/core/__init__.py \
  src/memory_benchmark/methods/registry.py \
  src/memory_benchmark/methods/mem0_adapter.py \
  src/memory_benchmark/methods/lightmem_adapter.py \
  src/memory_benchmark/methods/memoryos_adapter.py \
  src/memory_benchmark/cli/run_prediction.py \
  src/memory_benchmark/runners/prediction.py \
  src/memory_benchmark/runners/operation_level.py \
  tests/test_provider_protocol.py \
  tests/test_prediction_runner.py \
  tests/test_operation_level_runner.py \
  tests/test_halumem_registered_prediction.py \
  tests/test_mem0_adapter.py \
  tests/test_lightmem_adapter.py \
  tests/test_memoryos_adapter.py \
  docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/retrieval-evidence-contract-m0.md
git commit -m "feat(metrics): add retrieval evidence contract"
```

若允许清单内某个测试文件实际不存在，不创建同名空壳，改用真实对应测试文件并在 note/
回报列出偏差；若因此会增加允许清单外测试文件，停工。到此停止，不 push。按
actor-handbook §4 回报 commit、测试尾行原文、实际改动文件、偏差/停工点；若实质使用了
subagent，再用一句话说明分工。

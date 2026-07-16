# Actor 卡：三家已接 method 的双轨实现身份与 build-axis 审计

> **给当前 actor 的直接执行指令：你就是用户已选中的执行者。**本卡被发送到当前会话即
> 代表用户已经完成选择与授权，请直接施工；不要再选择、派发或等待另一个跨产品 actor。
> 是否使用当前执行环境自己的 subagent 由你判断，实质使用时在回报中说明分工。单批上限
> 5h；全程离线、docs-only、零真实 API、零下载、不 push。

## 0. 白话目标与架构边界

项目的 unified 主线必须调用 method 的通用 OSS 产品接口；native 只允许在**同一算法实现**
上切换官方实验配置。当前文档仍有三个高风险含糊点：

1. Mem0 generic OSS 与 `memory-benchmarks` harness 是否真的调用同一 `Memory.add/search` core；
2. LightMem `src/lightmem` 与 experiments 是同一 core + 参数，还是包含 algorithm fork；
3. MemoryOS `memoryos-pypi`、`memoryos-chromadb`、`eval/` 在 storage/update/retrieval 上哪些
   等价、哪些是不同 variant。

另有 build identity 冲突：旧 unified 政策统一 embedding，但用户与现行产品接口原则要求
repo default；Mem0 当前 shared MiniLM 与产品默认 `text-embedding-3-small` 已知不同。项目
还硬锁所有真实 LLM 为 `gpt-4o-mini`；官方 harness 若使用别的 answer/judge model，只能形成
partial-native，不能在审计表里被抹成 full parity。

你的任务是产出一手证据表，不替架构师拍最终实验政策，不改任何生产代码/配置/既有政策。

## 1. 上工、隔离与最小读序

先在主树确认状态，再建立隔离 worktree：

```bash
cd /Users/wz/Desktop/memoryBenchmark
git status --short
git worktree add -b actor/dual-track-identity-audit \
  /Users/wz/Desktop/mb-actor-dual-track-audit main
cd /Users/wz/Desktop/mb-actor-dual-track-audit
```

若分支或 worktree 已存在、主树不是你看到的最新 main，停工回报；不要 reset、删除或复用
来源不明的现场。

按顺序读最小集合：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点；
3. 本支线 `README.md`；
4. 本卡全文（它就是当前批次的 plan/prompt）；
5. `docs/reference/actor-handbook.md` §0-§4、§6-§7；
6. `docs/reference/dual-track-config-policy.md`；
7. `docs/workstreams/ws02.7-method-track/notes/m1-memoryos-evidence.md`；
8. `docs/workstreams/ws02.7-method-track/notes/lightmem-native-config-threeway.md`；
9. `docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
   mem0-provenance-validity-audit.md`；
10. 三家当前 adapter、TOML、config-track bundle 与下文指定一手目录。

已有 note 只作导航；关键结论必须回到当前一手源码/实际调用点复核，禁止复制旧结论充数。

## 2. 唯一交付物与允许范围

只允许新增：

`docs/workstreams/ws02.7-method-track/branches/dual-track-identity/notes/
integrated-method-dual-track-identity-audit.md`

不得修改 README、policy、checklist、代码、TOML、tests、third_party、roadmap 或 outputs。

## 3. 审计 A：implementation identity（逐家画真实调用链）

对 Mem0、LightMem、MemoryOS 各给一张表，至少包含：

| 字段 | 必答内容 |
|---|---|
| Phase 1 通用产品实现 | adapter 实际 import/构造的类与 ingest/retrieve 调用点 |
| 官方 benchmark harness | eval/experiments 入口实际调用的类/函数，不看 README 口号 |
| core reuse | harness 是 import 同一 core、复制同源文件，还是 forked implementation |
| material differences | storage、update/merge/delete、retrieval/rank、flush、side effect、并发 |
| classification | `CONFIG_EQUIVALENT` / `STORAGE_BACKEND_VARIANT` / `ALGORITHM_VARIANT` / `UNDETERMINED` |
| native 可否只换配置 | yes/no + 一句话理由 + 文件:行号 |

一手范围：

- Mem0：`third_party/methods/mem0-main/mem0/`、`memory-benchmarks/benchmarks/`、
  `memory-benchmarks/docker/mem0/`；
- LightMem：`third_party/methods/LightMem/src/lightmem/`、`experiments/locomo/`、
  `experiments/longmemeval/`；
- MemoryOS：`third_party/methods/MemoryOS-main/memoryos-pypi/`、
  `memoryos-chromadb/`、`eval/`。

不要以文件名相同推断算法等价；要追活跃构造器和调用点。机械 diff 可作导航，不能单独作为
“等价/不等价”结论。

## 4. 审计 B：build-axis 三方表

每家分别对比：

1. 通用产品**真正的无特殊 flag/无覆盖默认**；
2. 当前框架 unified TOML/adapter 实际传值；
3. 官方 benchmark harness/native 实际传值。

至少列：implementation variant、storage backend、embedding provider/model/dimension、method
build LLM/model、extraction prompt、update lifecycle、chunk/segment、retrieval top-k/threshold、
summary/consolidation、并发，以及 answer/judge 各自的 model、decoding、prompt、parse/metric
semantics。每格必须区分：签名默认、README demo 覆盖、实际 CLI 默认、调用点显式传值；不能
把其中一种冒充另一种。官方 model 非 `gpt-4o-mini` 时明确标
`FRAMEWORK_MODEL_OVERRIDE / PARTIAL_NATIVE`，不得建议绕过当前硬规则。

输出明确标记：`PRODUCT_DEFAULT` / `FRAMEWORK_OVERRIDE` / `BENCHMARK_NATIVE` /
`SOURCE_UNDETERMINED`。若当前文档/TOML 注释把 framework override 写成 repo default，列入
“需要架构师勘误”的精确路径/行号清单，不直接修改。

## 5. 审计 C：MemoryOS pypi / ChromaDB 专项

除 §3 通表外，逐项回答：

- `Memoryos` 公开构造/`add_memory`/纯检索能力是否同形；
- STM 满载迁移顺序、MTM page/segment 构造、heat 更新、LTM profile/knowledge 更新是否同序；
- ChromaDB 是否只替换 persistence/vector store，还是同时改变 id、排序、阈值、top-k、过滤、
  side effects、异常降级；
- 两者 repo defaults 是否相同；
- 当前 framework sidecar 的 exact page provenance 能否原样迁移；
- 若作为 storage variant，最少需重开 B3/B4/B5/B6/B8/B11 哪些门。

结论只给 evidence-backed classification；不替架构师选择主实现。

## 6. 审计 D：实验身份与复证影响

给出不含预算数字的影响表：

- 若把 current unified 的 framework override 改回 product default，是否必须重建 memory；
- 哪些既有 LightMem/Mem0/MemoryOS smoke artifact 失去可比性；
- 哪些只需 readout 重跑，哪些必须 build+retrieve+answer 全重跑；
- 建议 manifest 至少新增哪些静态 identity 字段，才能区分
  `product_default / controlled_backbone / benchmark_native / reproduction_variant`。

这是审计建议，不改协议。特别检查 current `config_track=native` 是否会把 partial-native
过度标成 full-native。

## 7. 强反证与停工条件

必须主动寻找至少四类反证：

1. README 说“默认”，但实际入口显式覆盖；
2. eval 文件名相似，但 update/retrieval 顺序不同；
3. 同 embedder 名但 provider/dimension/normalization 不同；
4. answer/judge 资产存在，但 build 或 judge 缺失，属于 partial-native。

以下任一命中则在 note 写清断点并停止对应 method，不猜：关键目录缺失；活跃入口无法在
5h 内确定；需要联网/真实 API/下载模型；一手源与本卡的硬架构边界冲突。可继续完成其他
method，但报告必须逐项标 `UNDETERMINED`，不得为了填表推断。

## 8. note 结构、唯一自检与提交

note 必须按以下结构：结论摘要 → 三家 implementation 表 → 三家 build-axis 表 → MemoryOS
专项 → 复证/manifest 影响 → 过时文字清单 → 来源待溯/停工点。所有关键结论给文件:行号；
PDF 事实用页码 + 可复算提取命令。

只跑一次最小自检：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

随后 `git status --short` 过目，只显式 add 唯一 note，禁止 `git add -A`/`.`：

```bash
git add docs/workstreams/ws02.7-method-track/branches/dual-track-identity/notes/integrated-method-dual-track-identity-audit.md
git commit -m "docs(ws02.7): audit dual-track implementation identity"
```

到此停止，不 push、不更新状态。按 actor-handbook §4 回报 commit hash、测试尾行原文、实际
改动文件、偏差/停工点；实质使用 subagent 时补一句分工。

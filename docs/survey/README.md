# 调查事实索引

本页解决两个问题：**已经调查过什么，稳定结论应去哪里找。**它只做导航和少量承重摘要，
不复制 workstream note 的完整取证，避免索引本身变成另一份会漂移的事实源。

## 1. 结论落点规则

| 调查对象 | 稳定结论落点 | 一手证据与裁决过程 | 当前施工状态 |
|---|---|---|---|
| 单个 benchmark | `benchmarks/` 总览 + `datasets/` schema + `workflows/` 评测流程 | 对应 workstream `notes/` | 活跃 workstream README |
| 单个 method | `docs/reference/integration/<method>.md` | method-track 支线 `notes/` | ws02.7 README + method-recertification |
| 跨 benchmark/method 契约 | `docs/reference/` 的长期政策/协议 | 对应支线审计与 ruling note | 父 workstream README |
| 已被取代的历史 | 不继续更新稳定页；正文加 superseded 链接 | `docs/archive/` 或历史 note | 不作为恢复入口 |

调查通过架构师强验收后，必须把**稳定、可复用的结论**回填到上表第一/二列，并从本页或
`docs/README.md` 能找到；完整命令、统计、争议和 actor 历史留在 evidence note。禁止把聊天
原文或整份 note 再复制一遍，也禁止只落 note 却不更新稳定入口。

### 1.1 Dataset 异常的四层处置账

每个 benchmark 在推进到某个 method 时发现的新异常，按四层落点记录，禁止只留在聊天，也
禁止给十个 method 复制十份相同事实：

1. `异常情况/<benchmark>.md` 是详细异常账的单一来源：记录数据版本、计数、真实位置、代表
   样本、异常理由与完整处置矩阵；未经 owner 一手规则支持，不得擅自清洗或猜测修复 gold。
2. `datasets/<benchmark>.md` 只保留 schema 与异常摘要，并链接详细异常账，不复制长样本表。
3. `workflows/<benchmark>.md` 记录框架统一处置：canonical adapter 如何保真、evaluator 如何
   计分/披露、smoke 如何裁剪，以及异常是否只存在于 evaluator-private 通道。
4. `docs/reference/integration/<method>.md` 只记录该 method 的**差分影响**：需要 placeholder、
   timestamp fallback、文本 fallback 等才写；若异常已在 benchmark 层完全吸收，则明确写
   “无 method 特判”并链接回前述 benchmark 层。

完整探针、命令与争议仍留在 workstream note；稳定页写结论与复核锚。这样既能逐 benchmark
稳扎稳打，又不会因复制粘贴形成十份互相漂移的“异常真相”。

## 2. Phase 1 五 benchmark 四联入口

| Benchmark | 总览 | Dataset schema | 异常详账 | 官方/框架 workflow | 当前 gold evidence unit 摘要 |
|---|---|---|---|---|---|
| LoCoMo | [benchmark](benchmarks/LoCoMo.md) | [dataset](datasets/locomo.md) | [anomalies](异常情况/locomo.md) | [workflow](workflows/locomo.md) | 单 utterance `dia_id`；9 个 turn-unmatched unit，1 个重复 occurrence 稳定去重 |
| LongMemEval | [benchmark](benchmarks/LongMemEval.md) | [dataset](datasets/longmemeval.md) | 待强验收 | [workflow](workflows/longmemeval.md) | user-side `has_answer` turn + answer session；主 retrieval 路径分母 419 |
| HaluMem | [benchmark](benchmarks/HaluMem.md) | [dataset](datasets/halumem.md) | 待逐格建立 | [workflow](workflows/halumem.md) | memory-point fact；无 turn 回指，turn Recall=N/A |
| BEAM | [benchmark](benchmarks/BEAM.md) | [dataset](datasets/BEAM.md) | 待按 variant 建立 | [workflow](workflows/BEAM.md) | `source_chat_ids` 本意指 message；1M 四个 conversation 有 raw-id 歧义；Recall 为 framework supplementary |
| MemBench | [benchmark](benchmarks/MemBench.md) | [dataset](datasets/membench.md) | [anomalies](异常情况/membench.md) | [workflow](workflows/membench.md) | FirstAgent=pair-step、ThirdAgent=string-step；拆分后按 evaluator-private any-of group 计一次 |

五家 gold-unit 的完整一手对表与方案裁决见
[canonical turn 与 gold evidence unit 审计](../workstreams/ws02.7-method-track/branches/input-role-semantics/notes/evidence-unit-contract-audit.md)。

## 3. Method 稳定入口

| Method | 接入事实页 |
|---|---|
| LightMem | [integration/lightmem.md](../reference/integration/lightmem.md) |
| Mem0 | [integration/mem0.md](../reference/integration/mem0.md) |
| MemoryOS | [integration/memoryos.md](../reference/integration/memoryos.md) |
| A-Mem | [integration/amem.md](../reference/integration/amem.md) |
| SimpleMem | [integration/simplemem.md](../reference/integration/simplemem.md) |
| EverOS | [integration/everos.md](../reference/integration/everos.md) |

尚未形成接入事实页的 method 先看 `docs/reference/method-interface-inventory.md`；完成首轮一手
审计后再建对应 integration 页，不用散落的 actor 卡冒充稳定文档。

## 4. 当前跨切面调查入口

| 主题 | 权威入口 |
|---|---|
| role、LightMem `messages_use`、MemBench pair-step | [input-role-semantics](../workstreams/ws02.7-method-track/branches/input-role-semantics/README.md) |
| timestamp、MemBench 缺失时间与 content 单次渲染 | [membench-time-semantics](../workstreams/ws02.7-method-track/branches/membench-time-semantics/README.md) |
| Recall/NDCG 资格与 RetrievalEvidence | [retrieval-metrics](../workstreams/ws02.7-method-track/branches/retrieval-metrics/README.md) |
| unified/native 与 build identity | [dual-track-identity](../workstreams/ws02.7-method-track/branches/dual-track-identity/README.md) |
| 逐 method 重认证 | [method-recertification](../workstreams/ws02.7-method-track/branches/method-recertification/README.md) |

这些支线结束后，本表应指向稳定 policy/integration/survey，而不是永久依赖活跃任务卡。

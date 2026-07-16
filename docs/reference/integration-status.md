# 接入状态实例化（每 method / 每 benchmark 的 checklist 落表）

> 2026-07-13 建（用户提议：`method-integration-checklist.md` 是**模板**，本文是它对
> **每个具体 method / benchmark 的实例化**——逐项打勾 + 特殊情况就地补全，免得"总忘记
> 谁过了 checklist"。判据全文见 `docs/reference/method-integration-checklist.md`
> （benchmark=A1-A8、method=B1-B11）。**每次接入/冻结/发现特殊情况,更新本文对应行。**
> 状态图例：✅ 过并留痕 / 🟡 进行中或部分 / ⬜ 未开始 / N/A 不适用（附因）。
>
> **三层结构（2026-07-13 用户二次拍板补全）**：模板（checklist）→ 本文（勾选总表，
> 一眼看谁过了哪项）→ **`integration/` 逐实体实例文档**（每 method / benchmark 一份，
> 逐项展开证据 + `文件:行号` 锚 + method 的**接口调用面黑盒拆解**）。表中名字即链接；
> 勾选变化与实例文档必须同步更新。

## 一、Benchmark 侧（A1-A8）

ws02.6 于 2026-07-12 将五家全部 frozen-v1；2026-07-15 MemBench 因 100k message
时间语义短暂重开 A2/A8，Phase A `2e6b4d7` 经定向/全量/compileall 强验收后已恢复，当前
五家 benchmark 均为 frozen-v1。历史冻结记录在 `ws02.6/notes/<b>-frozen-v1.md`，新反证与
复验以追加勘误保留，不能覆盖历史。

| benchmark | A1 来源锁 | A2 数据契约 | A3 公私边界 | A4 canonical/GC-1 | A5 prompt/metric parity | A6 smoke/resume | A7 artifact/eff | A8 冻结门 | frozen |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| [LoCoMo](integration/locomo.md) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |
| [LongMemEval](integration/longmemeval.md) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |
| [MemBench](integration/membench.md) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |
| [HaluMem](integration/halumem.md) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |
| [BEAM](integration/beam.md) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |

**特殊情况（就地补全）**
- **HaluMem**：retrieval recall = **N/A**（evidence 无 turn id，官方无 retrieval recall 指标，
  禁凭文本相似度造 gold 映射）；memory_type 共同分母怪癖按官方原样（evaluation.py:364-383）；
  update 聚合 0 分母优雅处理。冻结限制见 `halumem-frozen-v1.md`。
- **LoCoMo/LongMemEval judge**：框架 `locomo-judge` 是 lightmem 衍生（7 处文本偏差）；
  `longmemeval-judge` = 官方 parity。native 轨另注册**逐字无偏差**版（见 method 侧 LightMem）。
- **LongMemEval retrieval-rank**：官方 NDCG@k/recall k∈[1,3,5,10,30,50]；`_abs` 与
  无目标 turn 均剔除。旧 3000 例“公式零失配”只证明单题公式，不证明 overall 分母；
  2026-07-15 审计确认框架把无目标题记 1 分且 `top_k=10` 挡死 k30/50，现已重开
  evaluator 正确性门。
- **BEAM**：测试需 `datasets` 模块（环境依赖；缺失会 18 项 fail，非回归——2026-07-13 判例）。
- **MemBench**：源文件维度聚合 four-cell（first/third × high/low）。2026-07-15 发现
  100k 258,000 个无时间 noise 被首个有时 turn 派生的伪 `session_time` 覆盖；Phase A
  `2e6b4d7` 已删除 fallback 并完成全量回归，A2/A8 恢复。`QA.time` 不进入 ingest。

## 二、Method 侧（B1-B11）

判据 B1-B11 见 checklist。**method-frozen-v1** = B1-B11 全过 + 架构师验收 + `notes/<m>-frozen-v1.md`。

| method | 适配器 | B1 来源/接口 | B2 注入粒度 | B3 隔离 | B4 fmt+时间戳 | B5 provenance | B6 flush | B7 api_usage | B8 副作用 | B9 模型口径 | B10 双轨 | B11 smoke+冻结 | method-frozen |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| [**LightMem**](integration/lightmem.md) | ✅ | ✅ | ✅ | ✅物理 | ✅timestamped + explicit-None online-soft | ✅online-soft turn；consolidated N/A | ✅online-soft | ✅ | ✅ | ✅canonical-required MiniLM；零重建 | 🟡readout-only 身份 M0 待落 | 🟡M1 evaluator + identity 后主轨复证 | **v1 suspended** |
| [Mem0](integration/mem0.md) | ✅ | ✅content-hash锁(声明1) | ✅ | ✅混合(par2×4实弹) | ✅effective time 单次渲染 | ✅turn/session；BEAM recall=N/A | ✅零flush | ✅(native计量=R0前置,声明2) | ✅B8+清单落档(M5,下载点声明4) | 🟡OpenAI product-default 迁移待施工/预算 | 🟡readout-only 身份 M0 待落 | 🟡13格 controlled 证据保留；主轨复证 | **v1 局部重开** |
| [MemoryOS](integration/memoryos.md) | ✅ | ✅PyPI；Chroma=reproduction variant | ✅pair/session | ✅物理 | ✅全层+时间 | ✅turn + M0 v1 | ✅no-op | ✅ | ✅降级审计 | ✅product-default MiniLM；零重建 | 🟡readout-only 身份 M0 待落 | 🟡身份门后五格 smoke | 待 B11 |
| [A-Mem](integration/amem.md) | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| [SimpleMem](integration/simplemem.md) | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MemOS | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Letta/MemGPT | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| LangMem | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Supermemory | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| [EverOS](integration/everos.md) | ✅vendored | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

> "适配器 ✅" 只代表代码入口存在，不代表冻结。Mem0 原 frozen-v1 的大部分证据保留，
> MemBench/BEAM/HaluMem B4 effective-time 离线修复已验收，内容抽查并入后续 B11；三家 B9
> 精确身份审计与架构裁决已完成，旧 shared MiniLM 证据保留为 controlled 而非删除。Mem0
> product-default 迁移待身份 M0 后另施工；LightMem/MemoryOS 与现 build 字节重合，无需重建。
> MemoryOS 已完成 M1 一手取证与 M2 离线施工/全量门，只差身份
> 审计后的 B11 真实 smoke；LightMem 因 2026-07-15
> 发现 LoCoMo post-update 无 semantic source mapping 而重开 B5/B11；逐题 M0 声明机制已落，
> 现待 M1 evaluator 消费。A-Mem/SimpleMem 待各自 M 阶段。N/A 是能力结论，不是强造指标。

**逐项证据与接口调用面**：全部收归各实体的实例文档（表中名字即链接），本文不再
就地展开（2026-07-13 起，原"LightMem 详情"节已迁入
[integration/lightmem.md](integration/lightmem.md)，避免双源漂移）。

**跨 method 横向事实（2026-07-13 取证）**
- **provenance 现状（2026-07-15 重审）**：MemoryOS 维持既有 turn 声明；Mem0 的
  sidecar 是 ingest 批归属，故 LoCoMo/MemBench=turn、LongMemEval=session、BEAM
  turn Recall=N/A。LightMem 五格 paper `online_soft` 主 profile 已于主线 `825132f`
  合入：初始 external-id 透传后不运行全库 merge，可逐题审 semantic provenance；
  B6 已恢复，M0 已逐题写 valid/N/A/pending，B11 现待 M1 evaluator 消费。LoCoMo
  `locomo_offline_consolidated` 补充轨会把
  candidate 文本
  并进 target；即使合并全部输入 id，也只能证明 transformation inputs，不能证明新文本
  仍承载每个 fact，故该补充轨 provenance-based Recall/NDCG 应 N/A，见
  `ws02.7/branches/lightmem-lifecycle/notes/lightmem-update-lifecycle-ruling.md`。
  A-Mem/SimpleMem 仍为 `"none"`；
  不可评 metric 必须 N/A，不得按 0 分。
- **clean-retry 钩子覆盖（2026-07-14 M2 后五家全员到齐）**：Mem0 的 hook =
  `delete_all(run_id)` + 批准的第二个 B5+ third_party 最小 diff
  `SQLiteManager.delete_messages(session_scope)`（污染场景有测试钉死）。
  Mem0 隔离形态实为 **worker 间物理、worker 内逻辑**（M1 取证 §3;生产
  Qdrant 零 API 泄漏测试已补;共享实例并行维持关闭）。
- **B5+ provenance 无损改造重审（2026-07-15）**：Mem0 ADD-only 负空间审计已完成，
  证明 mutation 仅 ADD、同时暴露批粒度归因；MemoryOS 为既有 page sidecar；amem、
  simplemem 待各自 M 阶段。
  LightMem 初次 fact insert 可透传 source id，但 LoCoMo post-update 没有 output-to-source
  语义映射，判为**该格不可无损改造、指标 N/A**，不再把 plural 输入并集列作 PR 候选。
  三策略全景 +
  反面判例（绕管线换指标不可取）：`ws02.7/notes/memorydata-recall-retrofit-survey.md`。

## 三、维护约定
- 接入推进 / 冻结 / 发现特殊情况 → **同步更新**本文对应行 + 该实体的
  `integration/<entity>.md` 实例文档。
- 本文是**勾选总表**，判据模板以 `method-integration-checklist.md` 为准、逐项证据以
  实例文档为准，都不在此复制。
- 与 ws02.7 README 断点区互补：README=时间线叙事，本文=**当前静态勾选状态**。

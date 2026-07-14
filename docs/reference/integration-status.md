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

五家均 **frozen-v1**（ws02.6，冻结记录 `ws02.6/notes/<b>-frozen-v1.md`；B6 横向总验收
2026-07-12 通过）。A1-A8 全过。

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
- **LongMemEval retrieval-rank**：官方 NDCG@k/recall k∈[1,3,5,10,30,50]，abstention 排除；
  经 3000 例复算与官方零失配（F1 卡）。
- **BEAM**：测试需 `datasets` 模块（环境依赖；缺失会 18 项 fail，非回归——2026-07-13 判例）。
- **MemBench**：源文件维度聚合 four-cell（first/third × high/low）。

## 二、Method 侧（B1-B11）

判据 B1-B11 见 checklist。**method-frozen-v1** = B1-B11 全过 + 架构师验收 + `notes/<m>-frozen-v1.md`。

| method | 适配器 | B1 来源/接口 | B2 注入粒度 | B3 隔离 | B4 fmt+时间戳 | B5 provenance | B6 flush | B7 api_usage | B8 副作用 | B9 模型口径 | B10 双轨 | B11 smoke+冻结 | method-frozen |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| [**LightMem**](integration/lightmem.md) | ✅ | ✅ | ✅ | ✅物理 | ✅ | ✅turn | ✅offline | ✅ | ✅ | ✅分叉 | ✅ | ✅ | **v1** |
| [Mem0](integration/mem0.md) | ✅ | 🟡 | ✅ | ✅混合 | ✅M3对话时间(s2实弹复证) | ✅turn(首个非零recall) | ✅零flush | 🟡 | 🟡韧性清单B8+待列 | ✅ | 🟡M4卡待派(native三格) | 🟡六格全指标评完;缺par2+native | ⬜ |
| [MemoryOS](integration/memoryos.md) | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| [A-Mem](integration/amem.md) | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| [SimpleMem](integration/simplemem.md) | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MemOS | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Letta/MemGPT | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| LangMem | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Supermemory | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| [EverOS](integration/everos.md) | ✅vendored | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

> "适配器 ✅" = 有 adapter 代码（旧 5 个在 ws02.5 前落地），**但未逐项走 B1-B11
> method-frozen-v1 流程**；Mem0/MemoryOS/A-Mem/SimpleMem 的 B 列待各自 M 阶段一手补。
> LightMem 是当前唯一在跑 M0 的 method。

**逐项证据与接口调用面**：全部收归各实体的实例文档（表中名字即链接），本文不再
就地展开（2026-07-13 起，原"LightMem 详情"节已迁入
[integration/lightmem.md](integration/lightmem.md)，避免双源漂移）。

**跨 method 横向事实（2026-07-13 取证）**
- **provenance 现状（2026-07-13 更新，M0-9 修正）**：**LightMem 已升级 `"turn"` =
  首个 provenance 生产者**（M0-7b external_id 透传，locomo 实证 recall n=1；
  **全部注入路径已覆盖**——两个消息构建器即全集，v3 turn/pair 复用之，M0-9
  离线测试用真实 id 形态钉死 lme/membench/beam 三家，四个 recall 类 evaluator
  契约"确定对齐无 gap"，见 `ws02.7/notes/m0-9-provenance-breadth.md`）；
  **Mem0 已升级 `"turn"`（2026-07-14 M2:原生 id 映射 sidecar 持久化+旧 state
  fail-fast,判例库策略② 首次落地,`notes/m2-mem0-adapter.md`）**;其余三家仍
  `"none"`（memoryos:448 / amem:239 / simplemem:163，B5+ 均已判"可无损改造"
  待各自 M 阶段）→ recall/ndcg/retrieval-rank 对这三家 N/A 是声明的事实。
- **clean-retry 钩子覆盖（2026-07-14 M2 后五家全员到齐）**：Mem0 的 hook =
  `delete_all(run_id)` + 批准的第二个 B5+ third_party 最小 diff
  `SQLiteManager.delete_messages(session_scope)`（污染场景有测试钉死）。
  Mem0 隔离形态实为 **worker 间物理、worker 内逻辑**（M1 取证 §3;生产
  Qdrant 零 API 泄漏测试已补;共享实例并行维持关闭）。
- **B5+ provenance 无损改造初判（2026-07-13，MemoryData 判例取证）**：mem0（id 映射
  sidecar）/ memoryos（文本反查）/ amem、simplemem（in-band 或 id 映射）四家
  **可无损改造**（adapter 层零 third_party）；**lightmem 需 third_party 最小 diff**
  （上游抽取已产出 fact 级 source_id、构造时丢弃）= 上游 PR 候选。三策略全景 +
  反面判例（绕管线换指标不可取）：`ws02.7/notes/memorydata-recall-retrofit-survey.md`。

## 三、维护约定
- 接入推进 / 冻结 / 发现特殊情况 → **同步更新**本文对应行 + 该实体的
  `integration/<entity>.md` 实例文档。
- 本文是**勾选总表**，判据模板以 `method-integration-checklist.md` 为准、逐项证据以
  实例文档为准，都不在此复制。
- 与 ws02.7 README 断点区互补：README=时间线叙事，本文=**当前静态勾选状态**。

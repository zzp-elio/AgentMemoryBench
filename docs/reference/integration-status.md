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
>
> **2026-07-17 配置政策更新：**B9-B11 不再按全局 `unified/native` 双流水线判定；现行判据是
> 一个 method TOML、跨五 benchmark 的主 section、稀疏 `author_<benchmark>` section 与
> 完整 answer builder。表内 `native/readout-only/product-default` 字样只解释既有产物身份，
> 新门以 `method-toml-and-answer-builder-policy.md` 和 checklist B10 为准。

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
  `longmemeval-judge` = 官方 parity。旧 config-track 另注册的逐字版保留历史身份；未来
  `author_<benchmark>` 只选择完整 answer builder，judge 仍由 benchmark 统一，不能暗换。
- **LongMemEval retrieval-rank**：官方 NDCG@k/recall k∈[1,3,5,10,30,50]；`_abs` 与
  无目标 turn 均剔除。旧 3000 例“公式零失配”只证明单题公式，不证明 overall 分母；
  2026-07-15 审计确认框架把无目标题记 1 分且 `top_k=10` 挡死 k30/50，现已重开
  evaluator 正确性门。
- **BEAM**：测试需 `datasets` 模块（环境依赖；缺失会 18 项 fail，非回归——2026-07-13 判例）。
- **MemBench**：源文件维度聚合 four-cell（first/third × high/low）。2026-07-15 发现
  100k 258,000 个无时间 noise 被首个有时 turn 派生的伪 `session_time` 覆盖；Phase A
  `2e6b4d7` 已删除 fallback。2026-07-17 canonical split 又以 `ce1a9a8` + `d852fff` +
  `68b674b` 把 FirstAgent pair 拆成真实双 role child，仍按一个 private group 计分；
  A2/A4/A8 已完成全量复验。`QA.time` 不进入 ingest。

## 二、Method 侧（B1-B11）

判据 B1-B11 见 checklist。**method-frozen-vN** = current build 的 B1-B11 全过 + 架构师验收 +
对应版本 frozen note；旧版本保留为历史快照，不覆盖改写。

| method | 适配器 | B1 来源/接口 | B2 注入粒度 | B3 隔离 | B4 fmt+时间戳 | B5 provenance | B6 flush | B7 api_usage | B8 副作用 | B9 模型口径 | B10 TOML/builder | B11 smoke+冻结 | method-frozen |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| [**LightMem**](integration/lightmem.md) | ✅ | ✅ | ✅caption v6 + MemBench/BEAM pair + HaluMem session | ✅五格真实 state；并行格物理隔离 | ✅v7 五格 readout/时间真实验收 | ✅LoCoMo/MemBench valid；LME/BEAM/HaluMem N/A；ranking pending 如实披露 | ✅online-soft + forced flush R1 | ✅prediction 与 artifact judge observations 实测 | ✅ | ✅当前 MiniLM smoke build | ✅主 TOML；author builder 按政策延后到校准前 | ✅五格 `REAL_SMOKE_PASSED` + 100K current-identity refill | **method-frozen-v3** |
| [Mem0](integration/mem0.md) | ✅ | ✅content-hash锁(声明1) | ✅五格 role/granularity v3 | ✅混合(W2×4实弹) | ✅time/caption/role 单次渲染 | ✅turn/session；BEAM recall=N/A | ✅零flush | ✅五格 prediction+judge 实测 | ✅clean retry + 精确失败 stage | ✅当前 MiniLM smoke build；性能主配置待裁 | ✅current 主配置 truthful；author builder 待迁 | ✅五格 8 run 开箱 + inventory R1 | **method-frozen-v2** |
| [MemoryOS](integration/memoryos.md) | ✅ | ✅PyPI；Chroma=reproduction variant | ✅pair/session | ✅物理 | ✅全层+时间 | ✅turn + M0 v1 | ✅no-op | ✅ | ✅降级审计 | ✅当前 MiniLM smoke build | 🟡旧 readout 身份 truthful；author builder 待迁 | 🟡五格主 smoke | 待 B11 |
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
> Track identity M0 已以 `dcd3e7b` + `d6fd56f` + `d032d45` 关闭；LightMem/MemoryOS 的
> 旧 Track identity 已如实标出 readout-only/current build，因此历史产物不改写；新 B10
> 仍需在首个作者校准或真实效果 full run 前迁为 TOML section + 完整 answer builder。当前
> 5×10 主 smoke 不等待 product-default embedding 迁移，Mem0/LightMem/MemoryOS 沿用已验收
> build；性能主配置到站后逐 method 裁定。
> MemoryOS 已完成 M1 一手取证与 M2 离线施工/全量门，只差排到其顺序后的 B11 真实 smoke；
> Mem0 五格 input/readout v3 与 HaluMem operation clean retry 已于 2026-07-20 以
> `7fb3cd9`/`e1b2c9c`、`1bdfa98`/`5d1f91e` 强验收，随后 8 个真实 run 的 manifest、metric、
> judge scope、worker state、Qdrant↔sidecar 与 public/private artifact 全部开箱。机器门的
> HaluMem field-presence 误判已订正；actual observations 反证不可达 legacy reader 后，
> registered model inventory 以 `14b6c31` 收紧。Mem0 现恢复为 `method-frozen-v2`。
> LightMem 因 2026-07-15 发现 LoCoMo post-update 无 semantic source mapping 而重开 B5/B11；
> RetrievalEvidence M1、MemBench canonical/role、caption v6 与最新 LoCoMo 单/双 worker B11
> 已全部关闭，2026-07-17 曾恢复为 method-frozen-v2；2026-07-18 v7 readout/embedding
> 可观测契约一度重开冻结门，现已由五格 current-v7 artifact、forced-flush 修复与 100K
> current-identity refill 全部关闭，升级为 method-frozen-v3。
> A-Mem/SimpleMem 待各自 M 阶段。N/A 是
> 能力结论，不是强造指标。

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

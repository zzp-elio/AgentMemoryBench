# 接入状态实例化（每 method / 每 benchmark 的 checklist 落表）

> 2026-07-13 建（用户提议：`method-integration-checklist.md` 是**模板**，本文是它对
> **每个具体 method / benchmark 的实例化**——逐项打勾 + 特殊情况就地补全，免得"总忘记
> 谁过了 checklist"。判据全文见 `docs/reference/method-integration-checklist.md`
> （benchmark=A1-A8、method=B1-B11）。**每次接入/冻结/发现特殊情况,更新本文对应行。**
> 状态图例：✅ 过并留痕 / 🟡 进行中或部分 / ⬜ 未开始 / N/A 不适用（附因）。

## 一、Benchmark 侧（A1-A8）

五家均 **frozen-v1**（ws02.6，冻结记录 `ws02.6/notes/<b>-frozen-v1.md`；B6 横向总验收
2026-07-12 通过）。A1-A8 全过。

| benchmark | A1 来源锁 | A2 数据契约 | A3 公私边界 | A4 canonical/GC-1 | A5 prompt/metric parity | A6 smoke/resume | A7 artifact/eff | A8 冻结门 | frozen |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| LoCoMo | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |
| LongMemEval | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |
| MemBench | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |
| HaluMem | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |
| BEAM | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | v1 |

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
| **LightMem** | ✅ | ✅ | 🟡 | ✅物理 | 🟡 | ✅none | ✅offline | ✅ | 🟡 | 🟡 | ✅ | 🟡 | ⬜ |
| Mem0 | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MemoryOS | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| A-Mem | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| SimpleMem | ✅ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MemOS | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Letta/MemGPT | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| LangMem | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| Supermemory | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| EverOS | ✅vendored | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

> "适配器 ✅" = 有 adapter 代码（旧 5 个在 ws02.5 前落地），**但未逐项走 B1-B11
> method-frozen-v1 流程**；Mem0/MemoryOS/A-Mem/SimpleMem 的 B 列待各自 M 阶段一手补。
> LightMem 是当前唯一在跑 M0 的 method。

### LightMem 详情（当前 M0，🟡 进行中）
- **B1 来源/接口**✅：vendored `third_party/methods/LightMem`；用 retrieve+add_memory，不用其 chat 入口。
- **B2 注入粒度**🟡：locomo=turn/batch，longmemeval=pair；HaluMem memory_point 支持待核。
- **B3 隔离**✅：物理（per-conversation Qdrant collection/path，adapter:388-390）。
- **B4 formatted_memory+时间戳**🟡：locomo 用官方 speaker 分组 + `_format_lightmem_memory`；
  longmemeval native 用 `_format_lightmem_memory_as_official_retrieve`（M0-1b 已透传对齐）。
- **B5 provenance**✅ = **none**（adapter:304）→ recall/rank 类指标对 LightMem **全 N/A**。
- **B6 flush**✅：offline_update（online 是 `return None` 空壳，唯一可用模式）；
  force_segment/force_extract 已接（last-batch + end_conversation）。
- **B7 api_usage**✅：build/answer/judge 三角色都记真实 token（2026-07-12 效率审计无缺口）。
- **B8 副作用/清理**🟡：per-conversation 状态 + `clean_lightmem_conversation_state`；resume 复建。
- **B9 模型口径**🟡：unified=gpt-4o-mini；native answer=gpt-4o-mini + (temp0/max2000/top_p0.8)；
  embedding=all-MiniLM 两轨同；native 内部超参 vs repo 默认待 M0.2 核。
- **B10 双轨**✅：unified+native config-track 机制（M0-1b 验收通过，unified 字节零回归）。
- **B11 smoke+冻结**🟡：flow-through smoke 已跑通（1 conv/1 round/1 q，管道 OK）；
  **⚠️ 空库待诊断**（1-round 抽取 0 条 entry，待卡 Y 日志落地后重跑读 `Created N`）；
  cost-probe（整条 conversation）+ native 轨 smoke + method-frozen-v1 未做。
- **特殊情况**：① StructMem 是独立实验（换 build+检索+embedding），native 不接；
  ② 空库诊断悬而未决；③ 双轨政策见 `dual-track-config-policy.md`。

## 三、维护约定
- 接入推进 / 冻结 / 发现特殊情况 → 立即更新本文对应行 + 补"特殊情况"。
- 本文是**状态实例**，判据模板仍以 `method-integration-checklist.md` 为准，不在此复制判据全文。
- 与 ws02.7 README 断点区互补：README=时间线叙事，本文=**当前静态勾选状态**。

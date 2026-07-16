# LightMem 当前主线 B1-B11 gap matrix

> 抽锚日期：2026-07-16；基线 main `6d768d7`。状态只用
> `revalidated / retested / N/A / pending`。本轮零真实 API，故没有把旧 smoke 惯性写成
> `retested`。role/evidence-unit 新反证见
> `../../../input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md`。

| 判据 | 状态 | 当前证据与缺口 | 下一门 |
|---|---|---|---|
| B1 来源锁/产品接口 | revalidated | 仍走 vendored `LightMemory.add_memory/retrieve` 通用产品接口；未换 eval fork | role 修复不改接口选择 |
| B2 注入粒度 | pending | LME pair、HaluMem session、其余 turn 的旧路由会在 BEAM/MemBench role-complete 后变化；10M 有同 role anomaly | evidence-unit 裁决后定 pair/占位规则 |
| B3 隔离/clean | revalidated | 每 conversation 独立 Qdrant path/collection；失败清理钩不受本轮影响 | 后续并行 smoke 复验 |
| B4 输入/时间/formatted_memory | pending | 时间链成立；但 hardcoded `user_only` 与 BEAM role laundering、MemBench pair 拼接使 role 输入不真实 | unified `hybrid` + canonical role 施工 |
| B5 provenance | pending | online-soft 避开 consolidation；但 MemBench gold 是 step、provider 报 turn，现有精确匹配资格不成立 | 通用 evidence-unit/qrel 契约 |
| B5+ 无损改造 | pending | role 分离可在 benchmark/adapter 层无损做；qrel 表达面尚未裁 | Fable docs-only 审计后架构师裁决 |
| B6 flush/finalize | revalidated | online-soft direct insert、end_conversation 最后一批 flush 与补充 consolidated gate 证据仍有效 | role 改后定向回归 |
| B7 效率插桩 | revalidated | memory manager/embedding/retrieval observer 路径未变；hybrid 会改变合法 token 数但不改变计量入口 | B11 复验 usage 完整性 |
| B8 检索副作用 | revalidated | retrieve 路径与 lifecycle 裁决未变 | B11 复验状态隔离 |
| B8+ 韧性 | revalidated | timeout/retry wrapper 与失败态清理未受影响 | 真实 smoke 前对表 |
| B9 模型/build 口径 | pending | MiniLM canonical-required 身份仍成立；`messages_use` 目前未进入强类型 config/manifest，却实质改变 build | 把 role profile 纳入 build identity |
| B10 双轨 | pending | 当前 readout-only identity 不能表达 unified-hybrid 与官方 LME user-only 两个 build；两者不得 collapse | 定义 role-complete 与 reproduction build axes |
| B11 五格 smoke/冻结 | pending | 角色输入会改变真实 memory build；旧五格资产不能证明新 profile | 代码强验收后，用户批预算再重建/跑 smoke |

## 当前冻结判词

LightMem 不是“全部作废”，也不是“继续 frozen”。准确状态是：**B1/B3/B6/B7/B8/B8+
可重用；B2/B4/B5/B5+/B9/B10/B11 定点重开。**在这些门关闭前，旧
`method-frozen-v1` 只作历史快照，不能作为当前 build 的完成声明。

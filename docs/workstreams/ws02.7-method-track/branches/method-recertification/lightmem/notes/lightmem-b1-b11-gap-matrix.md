# LightMem 当前主线 B1-B11 gap matrix

> 抽锚日期：2026-07-16；复核基线 main `8e108e4`。状态只用
> `revalidated / retested / N/A / pending`。本轮零真实 API，故没有把旧 smoke 惯性写成
> `retested`。role/evidence-unit 新反证见
> `../../../input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md`。

| 判据 | 状态 | 当前证据与缺口 | 下一门 |
|---|---|---|---|
| B1 来源锁/产品接口 | revalidated | 仍走 vendored `LightMemory.add_memory/retrieve` 通用产品接口；未换 eval fork | role 修复不改接口选择 |
| B2 注入粒度 | pending | role-slot normalizer 已裁：真实 role 不改写，assistant-first/同 role/dangling 用结构 slot 成对；但 upstream segmentation 仍 user-anchored | hybrid role profile 施工并锁强反例 |
| B3 隔离/clean | revalidated | 每 conversation 独立 Qdrant path/collection；失败清理钩不受本轮影响 | 后续并行 smoke 复验 |
| B4 输入/时间/formatted_memory | pending | 时间链成立；但 hardcoded `user_only` 与 BEAM role laundering、MemBench pair 拼接使 role 输入不真实 | unified `hybrid` + canonical role 施工 |
| B5 provenance | pending | online-soft 避开 consolidation；但官方 extraction `source_id` 是 pair index，随后固定读 user slot。hybrid 后只能得到 pair candidate ids：LoCoMo 单 utterance exact；MemBench 待 step-group；LME turn/BEAM message 不能冒充 exact | gold-evidence M0 + RetrievalEvidence M1 分格裁资格 |
| B5+ 无损改造 | pending | evaluator-private gold group 已裁，能无损表达 MemBench pair-step 与 BEAM multi-child；role-slot/pair-candidate 观测仍待代码强验收 | gold M0 与 hybrid role profile 并行施工后对表 |
| B6 flush/finalize | revalidated | online-soft direct insert、end_conversation 最后一批 flush 与补充 consolidated gate 证据仍有效 | role 改后定向回归 |
| B7 效率插桩 | revalidated | memory manager/embedding/retrieval observer 路径未变；hybrid 会改变合法 token 数但不改变计量入口 | B11 复验 usage 完整性 |
| B8 检索副作用 | revalidated | retrieve 路径与 lifecycle 裁决未变 | B11 复验状态隔离 |
| B8+ 韧性 | revalidated | timeout/retry wrapper 与失败态清理未受影响 | 真实 smoke 前对表 |
| B9 模型/build 口径 | pending | MiniLM canonical-required 身份仍成立；`messages_use` 目前未进入强类型 config/manifest，却实质改变 build；placeholder 过滤也改变 prompt/token identity | 把 role profile 纳入 config/manifest 并 bump adapter version |
| B10 双轨 | pending | 当前 readout-only identity 不能表达 unified-hybrid 与官方 LME user-only 两个 build；PR #72 只是 open docs-only 说明，不能把两轨 collapse | unified=hybrid；LME Table 2=user_only reproduction profile |
| B11 五格 smoke/冻结 | pending | 角色输入会改变真实 memory build；旧五格资产不能证明新 profile | 代码强验收后，用户批预算再重建/跑 smoke |

## 当前冻结判词

LightMem 不是“全部作废”，也不是“继续 frozen”。准确状态是：**B1/B3/B6/B7/B8/B8+
可重用；B2/B4/B5/B5+/B9/B10/B11 定点重开。**在这些门关闭前，旧
`method-frozen-v1` 只作历史快照，不能作为当前 build 的完成声明。

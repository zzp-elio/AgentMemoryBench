# LightMem 当前主线 B1-B11 gap matrix

> 抽锚日期：2026-07-17；复核基线 main `68b674b`。状态只用
> `revalidated / retested / N/A / pending`。本轮零真实 API，故没有把旧 smoke 惯性写成
> `retested`。role/evidence-unit 新反证见
> `../../../input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md`。

| 判据 | 状态 | 当前证据与缺口 | 下一门 |
|---|---|---|---|
| B1 来源锁/产品接口 | revalidated | 仍走 vendored `LightMemory.add_memory/retrieve` 通用产品接口；未换 eval fork | role 修复不改接口选择 |
| B2 注入粒度 | retested | hybrid role-slot normalizer 已用 assistant-first/同 role/dangling 强反例锁住：真实 canonical role 不改写，结构缺口才补 placeholder；upstream extraction prompt 仍 user-oriented 是质量/B11 披露，不再是 role laundering | B11 看真实五格成色，不改算法 prompt |
| B3 隔离/clean | revalidated | 每 conversation 独立 Qdrant path/collection；失败清理钩不受本轮影响 | 后续并行 smoke 复验 |
| B4 输入/时间/formatted_memory | retested | hybrid role 已验；MemBench FirstAgent 拆为真实 user/assistant child，每侧原文与自身时间独立，8 个正式文件 step→child 映射零缺陷；None 兼容与其他四格时间链历史门保留 | B11 复验真实 formatted memory，不再改 canonical |
| B5 provenance | pending | online-soft 避开 consolidation。LoCoMo 单 utterance与 MemBench pair-step 可逐题 valid；MemBench 两 pair 同 batch 未跨 step union，但不能声称 pair 内 child-exact；LME/BEAM/HaluMem 仍 N/A | RetrievalEvidence M1 让 evaluator 消费逐题事实 |
| B5+ 无损改造 | retested | evaluator-private gold group 已无损表达 MemBench pair-step 与 BEAM multi-child；hybrid pair candidate 全有或全无，MemBench cross-batch 强反例已通过 | M1 只消费，不重写 group/schema |
| B6 flush/finalize | revalidated | online-soft direct insert、end_conversation 最后一批 flush 与补充 consolidated gate 证据仍有效 | role 改后定向回归 |
| B7 效率插桩 | revalidated | memory manager/embedding/retrieval observer 路径未变；hybrid 会改变合法 token 数但不改变计量入口 | B11 复验 usage 完整性 |
| B8 检索副作用 | revalidated | retrieve 路径与 lifecycle 裁决未变 | B11 复验状态隔离 |
| B8+ 韧性 | revalidated | timeout/retry wrapper 与失败态清理未受影响 | 真实 smoke 前对表 |
| B9 模型/build 口径 | pending | MiniLM current smoke identity 仍成立；`messages_use=hybrid` 已进入强类型 config/manifest，adapter 已升 v5。现行 TOML section 政策仍待在首个效果实验前迁移 | 保持当前 smoke build；性能阶段裁 embedding/参数 |
| B10 TOML/builder | pending | 当前 manifest 能如实区分 hybrid build，但旧 `config_track` 不是新架构；官方 LME `user_only` 只能作为 author/reproduction section，不能暗切 | 按 method TOML +完整 answer builder 政策迁移 |
| B11 五格 smoke/冻结 | pending | 角色输入会改变真实 memory build；旧五格资产不能证明新 profile | 代码强验收后，用户批预算再重建/跑 smoke |

## 当前冻结判词

LightMem 不是“全部作废”，也不是“继续 frozen”。准确状态是：**B1/B3/B6/B7/B8/B8+
证据 revalidated，B2/B4/B5+ 已 retested；B5/B9/B10/B11 仍 pending。**在这些门关闭前，旧
`method-frozen-v1` 只作历史快照，不能作为当前 build 的完成声明。

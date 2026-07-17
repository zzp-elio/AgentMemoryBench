# LightMem 当前主线 B1-B11 gap matrix

> 抽锚日期：2026-07-17；复核基线 main `5c5b850`。状态只用
> `revalidated / retested / N/A / pending`。本轮零真实 API，故没有把旧 smoke 惯性写成
> `retested`。role/evidence-unit 新反证见
> `../../../input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md`。

| 判据 | 状态 | 当前证据与缺口 | 下一门 |
|---|---|---|---|
| B1 来源锁/产品接口 | revalidated | 仍走 vendored `LightMemory.add_memory/retrieve` 通用产品接口；未换 eval fork | role 修复不改接口选择 |
| B2 注入粒度 | retested | hybrid role-slot normalizer 已用 assistant-first/同 role/dangling 强反例锁住；LME audit 全量证明每个 retained canonical turn 恰出现一次。官方 author harness 会丢 2,020/20,283 raw turn（含 3+3 个 answer-session assistant target）；这是 reproduction 与 unified profile 的已知分叉 | B11 披露 profile，不再重开 role mapping |
| B3 隔离/clean | revalidated | 每 conversation 独立 Qdrant path/collection；失败清理钩不受本轮影响 | 后续并行 smoke 复验 |
| B4 输入/时间/formatted_memory | retested | LME S/M q<latest=`76/118` 且全为同日分钟错序；dataset raw timestamp 原样传、完整 history 不截断，retrieve 明确 `filters=None`。500ms 只在 repeated raw timestamp key 内递增，distinct per-turn time 保持；placeholder 保 lineage/speaker 但会影响 method-derived slot time。无需 corrected timestamp 或代码修复 | B11 披露 source session time 与 method-derived order time |
| B5 provenance | retested | RetrievalEvidence M1 已严格消费逐题事实：online-soft LoCoMo 单 utterance与 MemBench pair-step 可 valid；LME/BEAM/HaluMem N/A，consolidated 恒 N/A，stable ranking 仍 pending。assistant-first 镜像保 lineage/speaker，但 pair index 不具 child-exact time/turn provenance | B11 核对 artifact status，不再用静态资格猜测 |
| B5+ 无损改造 | retested | evaluator-private gold group 已无损表达 MemBench pair-step 与 BEAM multi-child；hybrid pair candidate 全有或全无，MemBench cross-batch 强反例已通过 | M1 只消费，不重写 group/schema |
| B6 flush/finalize | revalidated | online-soft direct insert、end_conversation 最后一批 flush 与补充 consolidated gate 证据仍有效 | role 改后定向回归 |
| B7 效率插桩 | revalidated | memory manager/embedding/retrieval observer 路径未变；hybrid 会改变合法 token 数但不改变计量入口 | B11 复验 usage 完整性 |
| B8 检索副作用 | revalidated | retrieve 路径与 lifecycle 裁决未变 | B11 复验状态隔离 |
| B8+ 韧性 | revalidated | timeout/retry wrapper 与失败态清理未受影响 | 真实 smoke 前对表 |
| B9 模型/build 口径 | revalidated | 当前五格 smoke identity=MiniLM/384/cosine + hybrid + online-soft，强类型 manifest 可复算。效果参数/embedding 的最终裁决按政策延后，不冒充当前 smoke 缺口 | 当前 build 进 B11；首个效果 full 前再裁参数 |
| B10 TOML/builder | revalidated | 当前 manifest 对既有 smoke build truthful；新 TOML section/完整 author builder 已明确排在首个 author calibration/效果 full 前，按政策不阻塞 5×10 smoke。官方 LME `user_only` 未来只能显式 author section，不能暗切 | B11 使用当前已验收 section；效果实验前迁移 |
| B11 五格 smoke/冻结 | pending | 角色输入会改变真实 memory build；旧五格资产不能证明新 profile | 代码强验收后，用户批预算再重建/跑 smoke |

## 当前冻结判词

LightMem 不是“全部作废”，也不是“继续 frozen”。准确状态是：**B1/B3/B6/B7/B8/B8+/B9/B10
证据 revalidated，B2/B4/B5/B5+ 已 retested；只剩 B11 pending。**在 B11 关闭前，旧
`method-frozen-v1` 只作历史快照，不能作为当前 build 的完成声明。

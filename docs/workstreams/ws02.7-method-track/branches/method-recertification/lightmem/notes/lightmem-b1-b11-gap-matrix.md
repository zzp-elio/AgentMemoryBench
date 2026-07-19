# LightMem 当前主线 B1-B11 gap matrix

> 2026-07-19 current-v7 更新：LongMemEval 与 LoCoMo 单/双 worker 四组真实 artifact 已关闭
> v7 重新打开的 B4/B7 及这两个格子的 B11；`method-frozen-v2` 仍只是 v6 历史快照。
> MemBench current-v7 单/双 worker 已于 2026-07-19 强验收通过；BEAM 核心 artifacts 已通过，
> rubric judge evaluator-side efficiency 的共享代码修复也已强验收合入，但既有 2+1 道 judge
> 尚待重跑补 artifact；HaluMem method 侧离线预检 READY、真实 B11 排在补观测之后，因此
> method 整体仍不 frozen。

> 抽锚日期：2026-07-17；最新真实 smoke 基线 main `568b95d`。状态只用
> `revalidated / retested / N/A / pending`。role/evidence-unit 新反证见
> `../../../input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md`。

| 判据 | 状态 | 当前证据与缺口 | 下一门 |
|---|---|---|---|
| B1 来源锁/产品接口 | revalidated | 仍走 vendored `LightMemory.add_memory/retrieve` 通用产品接口；未换 eval fork | role 修复不改接口选择 |
| B2 注入粒度 | retested | LoCoMo v3 已从 `turn_images` 恢复 `ImageRef`；legacy/v3 caption-bearing message 共用共享 helper，无有效 caption 保留原文 bytes；真实 v6 LTM lineage 覆盖 caption-bearing `conv-26/D1:5` | 冻结；不再改注入协议 |
| B3 隔离/clean | retested | 单 worker 直接使用 run 级 `method_state/qdrant`；双 worker 使用 `worker_0/worker_1`。LoCoMo/LME 与 MemBench current-v7 均实测物理隔离；MemBench 四源按 high→worker0、low→worker1 唯一落点 | 冻结；失败清理钩继续由离线强反例覆盖 |
| B4 输入/时间/formatted_memory | revalidated | v7 LME/LoCoMo/MemBench/BEAM 真实 hit 均走 product ISO readout；BEAM 两格共 5 条 pair-lineage LTM，缺时/anchor 异常 preserve、不猜修。HaluMem 离线 full-ISO/None/zero-hit 强反例通过 | HaluMem 真实 Medium B11 再抽查；当前无 B4 代码缺口 |
| B5 provenance | retested | RetrievalEvidence M1 已严格消费逐题事实：online-soft LoCoMo 单 utterance与 MemBench pair-step 可 valid；LME/BEAM/HaluMem N/A，consolidated 恒 N/A，stable ranking 仍 pending。assistant-first 镜像保 lineage/speaker，但 pair index 不具 child-exact time/turn provenance | B11 核对 artifact status，不再用静态资格猜测 |
| B5+ 无损改造 | retested | evaluator-private gold group 已无损表达 MemBench pair-step 与 BEAM multi-child；hybrid pair candidate 全有或全无，MemBench cross-batch 强反例已通过 | M1 只消费，不重写 group/schema |
| B6 flush/finalize | revalidated | online-soft direct insert、end_conversation 最后一批 flush 与补充 consolidated gate 证据仍有效 | role 改后定向回归 |
| B7 效率插桩 | retested(code) / pending(real refill) | LoCoMo/LME/MemBench current-v7 prediction 观测成立；BEAM prediction 有 5 build+3 retrieval embedding。共享 artifact-level judge 断链已由 `174bd46` 关闭并经 fake-API/全量门验证；既有 BEAM run 尚无修复后的 metric-side artifacts，HaluMem 尚未真实执行 | 只补 BEAM 2+1 judge observations，再以同一契约跑 HaluMem；不重跑 build |
| B8 检索副作用 | retested | retrieve 路径与 lifecycle 裁决未变；真实单/双 worker state 独立且无跨 conversation collection | 冻结 |
| B8+ 韧性 | revalidated | timeout/retry wrapper 与失败态清理未受影响 | 真实 smoke 前对表 |
| B9 模型/build 口径 | revalidated | 当前五格 smoke identity=MiniLM/384/cosine + hybrid + online-soft，强类型 manifest 可复算。效果参数/embedding 的最终裁决按政策延后，不冒充当前 smoke 缺口 | 进入 B11；首个效果 full 前再裁参数 |
| B10 TOML/builder | revalidated | 当前 manifest 对既有 smoke build truthful；新 TOML section/完整 author builder 已明确排在首个 author calibration/效果 full 前，按政策不阻塞 5×10 smoke。官方 LME `user_only` 未来只能显式 author section，不能暗切 | 用当前 section 跑 B11；效果实验前迁移 |
| B11 五格 smoke/冻结 | pending | LoCoMo/LME/MemBench current-v7 为 `REAL_SMOKE_PASSED`；BEAM 100K W2+10M W1 核心 artifact/score 已过，共享代码已修，待补 3 次 evaluator observation；HaluMem current-v7 离线 READY，真实 Medium W1 随后执行 | 补 BEAM judge-only → 跑 HaluMem 全指标；当前不 frozen |

## 当前冻结判词

LightMem 的 v6 重认证曾完成：**B1-B11 当时均有证据，build 为 `method-frozen-v2`。**
current-v7 的 LoCoMo/LongMemEval/MemBench 受影响门已用新 artifact 关闭；BEAM 的 method/core
artifact 已实跑通过，共享 artifact-level judge efficiency 代码已修但历史 run 尚待补观测，
HaluMem method 侧 READY 而真实 smoke 尚未启动，所以仍不 frozen。旧 `method-frozen-v1/v2`
继续作为历史快照，
不覆盖、不改写。
已声明的 stable-ranking、k>10、author builder/效果参数与真实 resume 缺口见
[`lightmem-frozen-v2.md`](lightmem-frozen-v2.md)；它们不推翻历史 v6 判词。current-v7 的
B4 已关闭；当前阻断是 BEAM judge-only 补观测与 HaluMem B11，不再有共享 evaluator 代码缺口。

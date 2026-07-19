# LightMem 当前主线 B1-B11 gap matrix

> 2026-07-19 current-v7 更新：LongMemEval 与 LoCoMo 单/双 worker 四组真实 artifact 已关闭
> v7 重新打开的 B4/B7 及这两个格子的 B11；`method-frozen-v2` 仍只是 v6 历史快照。
> MemBench current-v7 单/双 worker 已于 2026-07-19 强验收通过；BEAM 核心 artifacts 与既有
> 2+1 道 rubric judge 的 evaluator-side efficiency 补观测均已通过。HaluMem 真实 sensory
> 反例抓出的两处 forced-flush bookkeeping 已由 `8879af9` 修复并经 real-core/全量强验收，B11
> Medium W1 全 evaluator 又已真实执行并开箱通过。source identity 随 sensory 纳入 hash 而变化；
> 前四格旧 artifacts 不可 resume，
> 最终冻结前另做 exact-smoke reachability，因此 method 整体仍不 frozen。

> 抽锚日期：2026-07-17；最新真实 smoke 基线 main `568b95d`。状态只用
> `revalidated / retested / N/A / pending`。role/evidence-unit 新反证见
> `../../../input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md`。

| 判据 | 状态 | 当前证据与缺口 | 下一门 |
|---|---|---|---|
| B1 来源锁/产品接口 | retested | 仍走 vendored `LightMemory.add_memory/retrieve` 通用产品接口；sensory runtime 已纳入 method source identity，旧 hash 严格不兼容 | HaluMem 新 run 使用新 hash；前四格只做 reachability，不伪装 resume |
| B2 注入粒度 | retested | LoCoMo v3 已从 `turn_images` 恢复 `ImageRef`；legacy/v3 caption-bearing message 共用共享 helper，无有效 caption 保留原文 bytes；真实 v6 LTM lineage 覆盖 caption-bearing `conv-26/D1:5` | 冻结；不再改注入协议 |
| B3 隔离/clean | retested | 单 worker 直接使用 run 级 `method_state/qdrant`；双 worker 使用 `worker_0/worker_1`。LoCoMo/LME 与 MemBench current-v7 均实测物理隔离；MemBench 四源按 high→worker0、low→worker1 唯一落点 | 冻结；失败清理钩继续由离线强反例覆盖 |
| B4 输入/时间/formatted_memory | retested | v7 LME/LoCoMo/MemBench/BEAM 真实 hit 均走 product ISO readout；BEAM 两格共 5 条 pair-lineage LTM，缺时/anchor 异常 preserve、不猜修。HaluMem 真实 QA 为合法 zero-hit sentinel，7 个 update probe 的 product ISO readout 均完整且只来自 s4 | 当前无 B4 代码缺口；前四格只做新 source reachability |
| B5 provenance | retested | RetrievalEvidence M1 已严格消费逐题事实：online-soft LoCoMo 单 utterance与 MemBench pair-step 可 valid；LME/BEAM/HaluMem N/A，consolidated 恒 N/A，stable ranking 仍 pending。assistant-first 镜像保 lineage/speaker，但 pair index 不具 child-exact time/turn provenance | B11 核对 artifact status，不再用静态资格猜测 |
| B5+ 无损改造 | retested | evaluator-private gold group 已无损表达 MemBench pair-step 与 BEAM multi-child；hybrid pair candidate 全有或全无，MemBench cross-batch 强反例已通过 | M1 只消费，不重写 group/schema |
| B6 flush/finalize | retested | `8879af9` 只修 forced cleanup index 与 automatic+tail 合并；real LightMemory/SenMem/STM 双 session 强反例证明 report 严格本 session、暂存态清空、早期非空 LTM 保留；真实 HaluMem report=`[0,0,0,2]` 且 Qdrant 仅 s4 lineage | 关闭；不再改算法 |
| B7 效率插桩 | retested | LoCoMo/LME/MemBench current-v7 prediction 观测成立；BEAM prediction 有 5 build+3 retrieval embedding，judge-only refill 又落 2+1 条 metric observations。HaluMem real run 实见 4 memory LLM、2 build+8 retrieval embedding、1 answer LLM 与 judge=`7+7+1`，scope/token inventory 精确 | 关闭；离线 evaluator 继续不得造空观测 |
| B8 检索副作用 | retested | retrieve 路径与 lifecycle 裁决未变；真实单/双 worker state 独立且无跨 conversation collection | 冻结 |
| B8+ 韧性 | revalidated | timeout/retry wrapper 与失败态清理未受影响 | 真实 smoke 前对表 |
| B9 模型/build 口径 | revalidated | 当前五格 smoke identity=MiniLM/384/cosine + hybrid + online-soft，强类型 manifest 可复算。效果参数/embedding 的最终裁决按政策延后，不冒充当前 smoke 缺口 | 进入 B11；首个效果 full 前再裁参数 |
| B10 TOML/builder | revalidated | 当前 manifest 对既有 smoke build truthful；新 TOML section/完整 author builder 已明确排在首个 author calibration/效果 full 前，按政策不阻塞 5×10 smoke。官方 LME `user_only` 未来只能显式 author section，不能暗切 | 用当前 section 跑 B11；效果实验前迁移 |
| B11 五格 smoke/冻结 | pending | 五格真实行为 artifacts 均已过；HaluMem fixed Medium W1 全指标=`REAL_SMOKE_PASSED`。前四格使用修复前 source hash，新 hash 不兼容旧 resume，但不等于必须重烧四格 | 前四格 exact-smoke 零 API reachability → frozen 裁决 |

## 当前冻结判词

LightMem 的 v6 重认证曾完成：**B1-B11 当时均有证据，build 为 `method-frozen-v2`。**
current-v7 的 LoCoMo/LongMemEval/MemBench 受影响门已有真实 artifact；BEAM 的 method/core
artifact 与 judge efficiency 补观测也已通过。HaluMem session-flush 反例已由最小 bookkeeping
修复，并由 fixed Medium W1 全指标真实 smoke 关闭；但前四格 artifacts 的 source hash 早于
sensory identity 修复，所以仍不 frozen。旧 `method-frozen-v1/v2`
继续作为历史快照，
不覆盖、不改写。
已声明的 stable-ranking、k>10、author builder/效果参数与真实 resume 缺口见
[`lightmem-frozen-v2.md`](lightmem-frozen-v2.md)；它们不推翻历史 v6 判词。current-v7 的
B4、共享 evaluator、forced-session flush 与 HaluMem B11 均已关闭。当前唯一冻结门是前四格
exact-smoke reachability；不默认进行付费重跑。

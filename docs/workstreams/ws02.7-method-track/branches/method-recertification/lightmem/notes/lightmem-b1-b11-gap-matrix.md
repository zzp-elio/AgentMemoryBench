# LightMem 当前主线 B1-B11 gap matrix

> 2026-07-19 current-v7 更新：LongMemEval 与 LoCoMo 单/双 worker 四组真实 artifact 已关闭
> v7 重新打开的 B4/B7 及这两个格子的 B11；`method-frozen-v2` 仍只是 v6 历史快照。
> MemBench current-v7 单/双 worker 已于 2026-07-19 强验收通过；BEAM、HaluMem 尚未按
> current-main 逐格重认证，因此 method 整体仍不 frozen。

> 抽锚日期：2026-07-17；最新真实 smoke 基线 main `568b95d`。状态只用
> `revalidated / retested / N/A / pending`。role/evidence-unit 新反证见
> `../../../input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md`。

| 判据 | 状态 | 当前证据与缺口 | 下一门 |
|---|---|---|---|
| B1 来源锁/产品接口 | revalidated | 仍走 vendored `LightMemory.add_memory/retrieve` 通用产品接口；未换 eval fork | role 修复不改接口选择 |
| B2 注入粒度 | retested | LoCoMo v3 已从 `turn_images` 恢复 `ImageRef`；legacy/v3 caption-bearing message 共用共享 helper，无有效 caption 保留原文 bytes；真实 v6 LTM lineage 覆盖 caption-bearing `conv-26/D1:5` | 冻结；不再改注入协议 |
| B3 隔离/clean | retested | 单 worker 直接使用 run 级 `method_state/qdrant`；双 worker 使用 `worker_0/worker_1`。LoCoMo/LME 与 MemBench current-v7 均实测物理隔离；MemBench 四源按 high→worker0、low→worker1 唯一落点 | 冻结；失败清理钩继续由离线强反例覆盖 |
| B4 输入/时间/formatted_memory | revalidated | v7 LME hit 保留完整 ISO、zero-hit sentinel 一致；LoCoMo 16 个、MemBench 25 个 hit 同样走 product ISO readout；无 author pretty-date wrapper。LoCoMo D1:5 与 MemBench First/Third lineage 均实见 | 三格受影响门关闭；BEAM/HaluMem 随逐格重认证抽查 |
| B5 provenance | retested | RetrievalEvidence M1 已严格消费逐题事实：online-soft LoCoMo 单 utterance与 MemBench pair-step 可 valid；LME/BEAM/HaluMem N/A，consolidated 恒 N/A，stable ranking 仍 pending。assistant-first 镜像保 lineage/speaker，但 pair index 不具 child-exact time/turn provenance | B11 核对 artifact status，不再用静态资格猜测 |
| B5+ 无损改造 | retested | evaluator-private gold group 已无损表达 MemBench pair-step 与 BEAM multi-child；hybrid pair candidate 全有或全无，MemBench cross-batch 强反例已通过 | M1 只消费，不重写 group/schema |
| B6 flush/finalize | revalidated | online-soft direct insert、end_conversation 最后一批 flush 与补充 consolidated gate 证据仍有效 | role 改后定向回归 |
| B7 效率插桩 | revalidated | LoCoMo/LME/MemBench current-v7 每题均有 retrieval embedding；build calls 分别 28/2/25，与实际 LTM insert 对齐。LME W1 0 LTM/0 build 是未发生调用，不是漏观测；raw 与 overall 聚合一致 | 采用 actual-call-aware 判据；BEAM/HaluMem 随逐格重认证抽查 |
| B8 检索副作用 | retested | retrieve 路径与 lifecycle 裁决未变；真实单/双 worker state 独立且无跨 conversation collection | 冻结 |
| B8+ 韧性 | revalidated | timeout/retry wrapper 与失败态清理未受影响 | 真实 smoke 前对表 |
| B9 模型/build 口径 | revalidated | 当前五格 smoke identity=MiniLM/384/cosine + hybrid + online-soft，强类型 manifest 可复算。效果参数/embedding 的最终裁决按政策延后，不冒充当前 smoke 缺口 | 进入 B11；首个效果 full 前再裁参数 |
| B10 TOML/builder | revalidated | 当前 manifest 对既有 smoke build truthful；新 TOML section/完整 author builder 已明确排在首个 author calibration/效果 full 前，按政策不阻塞 5×10 smoke。官方 LME `user_only` 未来只能显式 author section，不能暗切 | 用当前 section 跑 B11；效果实验前迁移 |
| B11 五格 smoke/冻结 | pending | LoCoMo/LME/MemBench current-v7 各 W1/W2 均为 `REAL_SMOKE_PASSED`；readout、evidence、summary v2、embedding observation、caption/pair lineage 与 worker state 已开箱通过 | 逐格压实 BEAM、HaluMem；当前不 frozen |

## 当前冻结判词

LightMem 的 v6 重认证曾完成：**B1-B11 当时均有证据，build 为 `method-frozen-v2`。**
current-v7 的 LoCoMo/LongMemEval/MemBench 受影响门已用新 artifact 关闭，但五格重认证尚缺
BEAM、HaluMem，所以仍不 frozen。旧 `method-frozen-v1/v2` 继续作为历史快照，
不覆盖、不改写。
已声明的 stable-ranking、k>10、author builder/效果参数与真实 resume 缺口见
[`lightmem-frozen-v2.md`](lightmem-frozen-v2.md)；它们不推翻历史 v6 判词。current-v7 的
B4/B7 受影响差量已经关闭，实际阻断只剩 B11 的 BEAM/HaluMem 两格重认证。

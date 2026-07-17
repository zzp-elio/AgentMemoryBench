# LightMem 当前主线 B1-B11 gap matrix

> 抽锚日期：2026-07-17；最新真实 smoke 基线 main `568b95d`。状态只用
> `revalidated / retested / N/A / pending`。role/evidence-unit 新反证见
> `../../../input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md`。

| 判据 | 状态 | 当前证据与缺口 | 下一门 |
|---|---|---|---|
| B1 来源锁/产品接口 | revalidated | 仍走 vendored `LightMemory.add_memory/retrieve` 通用产品接口；未换 eval fork | role 修复不改接口选择 |
| B2 注入粒度 | retested | LoCoMo v3 已从 `turn_images` 恢复 `ImageRef`；legacy/v3 caption-bearing message 共用共享 helper，无有效 caption 保留原文 bytes；真实 v6 LTM lineage 覆盖 caption-bearing `conv-26/D1:5` | 冻结；不再改注入协议 |
| B3 隔离/clean | retested | 单 worker 直接使用 run 级 `method_state/qdrant`；双 worker 使用 `worker_0/worker_1`，分别只含 conv-26/conv-30 独立 Qdrant collection | 冻结；失败清理钩继续由离线强反例覆盖 |
| B4 输入/时间/formatted_memory | retested | 时间链仍成立；离线探针确认 legacy=v3、wrapper 恰一次、旧 wrapper/query/URL 零泄漏；真实 3-round build 中 D1:5 产生带正确 lineage 的 LTM entry，formatted memory 非空 | 冻结；不要求抽取 LLM 逐字保留 caption wrapper |
| B5 provenance | retested | RetrievalEvidence M1 已严格消费逐题事实：online-soft LoCoMo 单 utterance与 MemBench pair-step 可 valid；LME/BEAM/HaluMem N/A，consolidated 恒 N/A，stable ranking 仍 pending。assistant-first 镜像保 lineage/speaker，但 pair index 不具 child-exact time/turn provenance | B11 核对 artifact status，不再用静态资格猜测 |
| B5+ 无损改造 | retested | evaluator-private gold group 已无损表达 MemBench pair-step 与 BEAM multi-child；hybrid pair candidate 全有或全无，MemBench cross-batch 强反例已通过 | M1 只消费，不重写 group/schema |
| B6 flush/finalize | revalidated | online-soft direct insert、end_conversation 最后一批 flush 与补充 consolidated gate 证据仍有效 | role 改后定向回归 |
| B7 效率插桩 | retested | 两组 run 均有 model inventory、raw observations、overall/by-conversation/by-question summary；hybrid 会改变合法 token 数但不改变计量入口 | 冻结 |
| B8 检索副作用 | retested | retrieve 路径与 lifecycle 裁决未变；真实单/双 worker state 独立且无跨 conversation collection | 冻结 |
| B8+ 韧性 | revalidated | timeout/retry wrapper 与失败态清理未受影响 | 真实 smoke 前对表 |
| B9 模型/build 口径 | revalidated | 当前五格 smoke identity=MiniLM/384/cosine + hybrid + online-soft，强类型 manifest 可复算。效果参数/embedding 的最终裁决按政策延后，不冒充当前 smoke 缺口 | 进入 B11；首个效果 full 前再裁参数 |
| B10 TOML/builder | revalidated | 当前 manifest 对既有 smoke build truthful；新 TOML section/完整 author builder 已明确排在首个 author calibration/效果 full 前，按政策不阻塞 5×10 smoke。官方 LME `user_only` 未来只能显式 author section，不能暗切 | 用当前 section 跑 B11；效果实验前迁移 |
| B11 五格 smoke/冻结 | retested | 历史五格五件套继续有效；唯一被 caption v6 失效的 LoCoMo 已补 `r3q1-w1` 与 `c2-w2`：1/1、2/2 prediction，四项当时适用 evaluator 全落盘，Recall@10 独立重算，效率/隐私/隔离均通过 | `method-frozen-v2`，下一家转 Mem0 |

## 当前冻结判词

LightMem 已完成本轮重认证：**B1-B11 全部有现行证据，诚实的 N/A/pending 不算缺门；当前
build 为 `method-frozen-v2`。**旧 `method-frozen-v1` 继续作为历史快照，不覆盖、不改写。
已声明的 stable-ranking、k>10、author builder/效果参数与真实 resume 缺口见
[`lightmem-frozen-v2.md`](lightmem-frozen-v2.md)，均不阻塞本轮冻结。

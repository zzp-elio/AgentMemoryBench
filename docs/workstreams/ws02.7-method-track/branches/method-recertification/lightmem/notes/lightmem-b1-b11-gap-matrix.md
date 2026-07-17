# LightMem 当前主线 B1-B11 gap matrix

> 抽锚日期：2026-07-17；复核基线 main `65f5805`。状态只用
> `revalidated / retested / N/A / pending`。本轮零真实 API，故没有把旧 smoke 惯性写成
> `retested`。role/evidence-unit 新反证见
> `../../../input-role-semantics/notes/lightmem-messages-membench-beam-role-audit.md`。

| 判据 | 状态 | 当前证据与缺口 | 下一门 |
|---|---|---|---|
| B1 来源锁/产品接口 | revalidated | 仍走 vendored `LightMemory.add_memory/retrieve` 通用产品接口；未换 eval fork | role 修复不改接口选择 |
| B2 注入粒度 | retested | LoCoMo v3 已从 `turn_images` 恢复 `ImageRef`；legacy/v3 caption-bearing message 共用共享 helper，无有效 caption 保留原文 bytes；1,226-turn 缺口由 adapter v6 + R1 关闭 | B11 用最新 build 抽查真实 artifact，不再改注入协议 |
| B3 隔离/clean | revalidated | 每 conversation 独立 Qdrant path/collection；失败清理钩不受本轮影响 | 后续并行 smoke 复验 |
| B4 输入/时间/formatted_memory | retested | 时间链仍成立；真实 `conv-26/D1:5` 离线探针又确认 legacy=v3、wrapper 恰一次、旧 wrapper/query/URL 零泄漏，空 assistant/speaker/time/lineage 不变 | B11 以 3 rounds 覆盖 D1:5，验证真实 build/readout artifact |
| B5 provenance | retested | RetrievalEvidence M1 已严格消费逐题事实：online-soft LoCoMo 单 utterance与 MemBench pair-step 可 valid；LME/BEAM/HaluMem N/A，consolidated 恒 N/A，stable ranking 仍 pending。assistant-first 镜像保 lineage/speaker，但 pair index 不具 child-exact time/turn provenance | B11 核对 artifact status，不再用静态资格猜测 |
| B5+ 无损改造 | retested | evaluator-private gold group 已无损表达 MemBench pair-step 与 BEAM multi-child；hybrid pair candidate 全有或全无，MemBench cross-batch 强反例已通过 | M1 只消费，不重写 group/schema |
| B6 flush/finalize | revalidated | online-soft direct insert、end_conversation 最后一批 flush 与补充 consolidated gate 证据仍有效 | role 改后定向回归 |
| B7 效率插桩 | revalidated | memory manager/embedding/retrieval observer 路径未变；hybrid 会改变合法 token 数但不改变计量入口 | B11 复验 usage 完整性 |
| B8 检索副作用 | revalidated | retrieve 路径与 lifecycle 裁决未变 | B11 复验状态隔离 |
| B8+ 韧性 | revalidated | timeout/retry wrapper 与失败态清理未受影响 | 真实 smoke 前对表 |
| B9 模型/build 口径 | revalidated | 当前五格 smoke identity=MiniLM/384/cosine + hybrid + online-soft，强类型 manifest 可复算。效果参数/embedding 的最终裁决按政策延后，不冒充当前 smoke 缺口 | 进入 B11；首个效果 full 前再裁参数 |
| B10 TOML/builder | revalidated | 当前 manifest 对既有 smoke build truthful；新 TOML section/完整 author builder 已明确排在首个 author calibration/效果 full 前，按政策不阻塞 5×10 smoke。官方 LME `user_only` 未来只能显式 author section，不能暗切 | 用当前 section 跑 B11；效果实验前迁移 |
| B11 五格 smoke/冻结 | pending | hybrid/online-soft/v6 均要求最新 build；旧五格与默认 1-round 不能证明 caption 路径。单 worker 与真实双 worker 的 run_id/命令已交用户，尚未回收输出 | 用户按 command pack 串行运行，架构师开箱验货后裁定 |

## 当前冻结判词

LightMem 不是“全部作废”，也不是“继续 frozen”。准确状态是：**B1/B3/B6/B7/B8/B8+/B9/B10
证据 revalidated，B2/B4/B5/B5+ 已 retested；只剩 B11 最新 build smoke pending。**在 B11
关闭前，旧
`method-frozen-v1` 只作历史快照，不能作为当前 build 的完成声明。

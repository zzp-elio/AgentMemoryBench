# Mem0 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**method-frozen-v1 局部重开（2026-07-16：source-time B4）**。冻结证据与九项声明缺口见
> `../../workstreams/ws02.7-method-track/notes/mem0-frozen-v1.md`；下列 B1-B11 是现行
> 结论，不再把 2026-07-13 的预填风险冒充当前状态。2026-07-15 ADD-only/provenance
> 负空间审计已由架构师验收：memory mutation 仅 ADD；同时确认 sidecar 是 ingest 批
> 归属，不自动等于 fact-level turn provenance。现行逐格裁决见
> `../../workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
> retrieval-metric-eligibility-ruling.md`。

- adapter：`src/memory_benchmark/methods/mem0_adapter.py`
- 算法源：vendored `third_party/methods/mem0-main`（官方 `Memory` 类）
- native 格：**locomo、longmemeval、beam**（来源=`memory-benchmarks` 当前 eval
  harness；旧论文配置只用于后续 R0 校准，不替代当前产品路径）

## 0. 接口调用面

| 框架钩子 | adapter 行为 | 落到 Mem0 官方接口 |
|---|---|---|
| `ingest(TurnEvent)` | `consume_granularity="turn"`；`_ingest_native_turn` 做 speaker→user/assistant 交替角色映射 | `_add_with_provenance` → `Memory.add([message], run_id=isolation_key, metadata=…, infer=…, prompt=…)` |
| `ingest(SessionBatch)` | `_ingest_native_session`：常规 session 按位置两两切块；HaluMem `session_memory_report` 路径整 session 单次 add | 同上逐 chunk/session 调 `Memory.add()` |
| `end_session` | HaluMem 用：返回本 session `add().results` 产出的 `SessionMemoryReport` | 无额外官方调用（复用 add 返回值） |
| `end_conversation` | —（无钩子；Mem0 add 即建，无缓冲） | — |
| `retrieve(query)` | `retrieve` 处理公开 Question；`_retrieve_native` 处理 v3 `RetrievalQuery` | `Memory.search(..., filters={"run_id": isolation_key}, top_k=…)` |

## B1-B11 当前结论

- **B1 ✅ 来源/接口**：使用 vendored OSS `Memory.add/search`；上游压缩包无可追 commit，
  以 package 2.0.4 + 146 文件 content hash 锁定，并把 5×10 后 upstream drift 对比列为
  声明缺口。
- **B2 ✅ 注入粒度**：LoCoMo/MemBench=turn，BEAM=pair，LongMemEval/HaluMem=
  framework session；LongMemEval 在 adapter 内按位置两 turn chunk，HaluMem 整 session。
  HaluMem 的 memory-point 复用 `end_session` 返回的 `add().results`。
- **B3 ✅ 混合隔离**：worker 间独立 backend 物理隔离，worker 内按官方 `run_id`
  namespacing 逻辑隔离；四格 par2 smoke 已实证。
- **B4 🟡 输入可见性+formatted_memory 时间（effective time 单次渲染待修）**：OSS `Memory.add()` 没有独立 timestamp
  参数，且 phased extraction 从 parsed messages 而非 storage metadata 读取新对话；因此
  adapter 的 `_turn_to_message()` 把公开 session/turn 时间渲染成 `[Session time: …]` /
  `[Turn time: …]`，同时仍把时间写 metadata 供持久化与检索。2026-07-16 现场复核确认
  MemBench 原 content 已带 place/time 时仍会再前置相同 `[Turn time]`；且普通 turn/session
  同时有值时会同时前置两行，未遵守 `turn_time → session_time → None` fallback。前者不是
  additive typed channel，而是同一 content 双拼；后者给 content-only method 额外输入两份
  时间。裁决为原文不删、typed time 仍保留，但每条 Mem0 message 只渲染一个 effective
  timestamp：turn 优先、session 仅 fallback、原文已嵌 effective turn time 则不再加 header；
  无时间 noise 不补时间。retrieve 侧再把
  payload 对话时间提升到 `created_at` 槽供官方 reader 使用。server 丢弃独立 timestamp
  字段仍是 upstream 缺口，但不等于当前 extraction 看不见 adapter 已内联的公开时间。
- **B5 ✅/N/A 逐格 provenance**：原生 memory id→持久 sidecar source ids；命中缺映射
  fail-fast，旧 state 不静默回落。LoCoMo/MemBench=valid(turn)；LongMemEval 只能安全
  声明 valid(session)，不得冒充 turn；BEAM pair 的批 id 并集不能证明每条 fact 同时承载
  两个 turn，turn Recall=N/A；HaluMem 官方无 retrieval recall。
- **B6 ✅ no-op flush**：`add()` 同步抽取并写入，无 conversation 尾部缓冲。
- **B7 ✅ api_usage（带声明缺口）**：build/answer/judge 观测已贯通；三格 native
  injected-token 计量尚未完全跟随官方实际嵌入段，列入 R0 前置包。
- **B8 ✅ 副作用/韧性**：失败清理为 `delete_all(run_id)` + 批准的 third_party
  `SQLiteManager.delete_messages(session_scope)` 最小 diff + sidecar 清除；两类业务 API
  点有 timeout/retry。首次模型下载仍需新机器预热预检。
- **B9 ✅ 模型/超参口径**：unified 与 native 分叉均已声明；官方 0.1 相关性门槛导致
  空检索属于方法语义，不当作框架故障。
- **B10 ✅ 双轨**：native 注册 LoCoMo、LongMemEval、BEAM；judge 路由泛化和旧论文
  校准配置属于 R0 前置包，不伪装成已消费。
- **B11 🟡 既有 13 格证据保留，受影响三 benchmark B4 修复后局部复证**：13 格 predict、免费/付费指标与既定
  并行门完成；冻结时基线 1164 passed。既有 BEAM provenance recall 与 LongMemEval
  turn-level/rank 数字不再作可信指标声明。逐题 RetrievalEvidence contract v1 已由 M0
  落盘，现待 M1 evaluator 消费；MemBench/BEAM/HaluMem 新输入字节须局部复证，LoCoMo/
  LongMemEval 的 session-only 输入及既有 add-only 证据继续有效。

## 特殊情况
1. Mem0 是当前唯一混合隔离方法，不能把 worker 内逻辑隔离误写成全局纯逻辑隔离。
2. `method-frozen-v1` 允许携带声明缺口，不等于这些缺口消失；解冻边界和 R0 前置包以
   frozen note §3-§4 为准。
3. `ADD_ONLY_MUTATION_PROVEN` 只回答旧 memory 是否被改写/删除；它不替代 semantic
   provenance 审计。任务卡旧标签 `ADD_ONLY_PROVEN` 的过宽语义以现行 ruling 为准。

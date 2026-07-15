# Mem0 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**method-frozen-v1（2026-07-14）**。冻结证据与九项声明缺口见
> `../../workstreams/ws02.7-method-track/notes/mem0-frozen-v1.md`；下列 B1-B11 是现行
> 结论，不再把 2026-07-13 的预填风险冒充当前状态。2026-07-15 已开 docs-only
> ADD-only/provenance 负空间审计卡；在一手证据回卡前维持冻结，不因类上存在公开
> `update/delete` API 就推断 adapter 可达 mutation。

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
- **B2 ✅ 注入粒度**：LoCoMo/LongMemEval=turn，BEAM=pair，HaluMem=整 session；
  HaluMem 的 memory-point 复用 `end_session` 返回的 `add().results`。
- **B3 ✅ 混合隔离**：worker 间独立 backend 物理隔离，worker 内按官方 `run_id`
  namespacing 逻辑隔离；四格 par2 smoke 已实证。
- **B4 ✅ formatted_memory+时间**：add 侧对话时间写 metadata，retrieve 侧提升到
  `created_at` 槽；OSS 无 timestamp 参数及 server 丢弃字段是已声明 upstream 缺口。
- **B5 ✅ turn provenance**：原生 memory id→持久 sidecar source ids；命中缺映射
  fail-fast，旧 state 不静默回落。
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
- **B11 ✅ smoke+冻结**：13 格 predict、免费/付费指标与既定并行门完成；冻结时基线
  1164 passed。完整 run_id、数字和九项声明缺口以 frozen note 为准。

## 特殊情况
1. Mem0 是当前唯一混合隔离方法，不能把 worker 内逻辑隔离误写成全局纯逻辑隔离。
2. `method-frozen-v1` 允许携带声明缺口，不等于这些缺口消失；解冻边界和 R0 前置包以
   frozen note §3-§4 为准。

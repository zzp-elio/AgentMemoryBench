# A-Mem 接入实例（B1-B11）

> adapter：`src/memory_benchmark/methods/amem_adapter.py`
>
> 状态：**B1-B10 已按 current product 重认证；B11 真实五格待执行。**

## 接口调用面

| framework | A-Mem 产品调用 | 裁决 |
|---|---|---|
| `ingest(TurnEvent)` | `AgenticMemorySystem.analyze_content()` + `add_note()` | turn；不配 pair，不造 placeholder |
| `retrieve(RetrievalQuery)` | `search_agentic(query, k)` | 只读产品 Chroma + linked neighbors；framework 自己回答 |
| `end_session` | 读取本 session 新 note delta | HaluMem extraction 可测 |
| `end_conversation` | pickle note + JSON lineage | resume 不重跑 LLM |
| clean retry | 删除该 conversation 独占 state dir | 物理隔离 |

## B1-B11

- **B1 ✅**：官方通用仓库 `third_party/A-mem`，upstream
  `ceffb860f0712bbae97b184d440df62bc910ca8d`，MIT；不用 LoCoMo 复现 engine。
- **B2 ✅**：五格均 turn ingest；LoCoMo speaker name，其余 canonical role；无 pair 约束。
- **B3 ✅**：每 conversation 独占 persistent Chroma；100-evolution consolidation 仍落回同一
  scoped retriever；clean retry 物理删除。
- **B4 ✅**：content/role/speaker/caption 无损；typed time 走
  `turn → session → None`；formatted_memory 回带 time/context/keywords/tags。
- **B5 ✅**：MemoryNote content/id/source time 不随 evolution 改写；sidecar 给 exact turn
  provenance，Recall 有资格；Chroma 顺序保留，ranking valid。
- **B6 ✅**：add_note 同步完成 note 写入与 evolution；无待 flush 的 buffer。
- **B7 ✅**：build LLM、embedding、retrieval 与 framework answer 真实 observation 可落盘。
- **B8 ✅**：检索只读；官方 swallow-error 两处在 wrapper fail-fast；endpoint/timeout/retry 注入。
- **B9 ✅**：`gpt-4o-mini` + product-default MiniLM-384/Chroma cosine；revision 诚实 unpinned。
- **B10 ✅**：主 TOML 跨五 benchmark 固定；作者 LoCoMo builder/复现参数不混入主表。
- **B11 🟡**：离线全量 `1679 passed`、compileall 0；真实 smoke 与冻结 note 待完成。

实现与算法证据见
[`amem-official-product-r1-implementation.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/amem/notes/amem-official-product-r1-implementation.md)。

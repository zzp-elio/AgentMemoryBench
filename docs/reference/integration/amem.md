# A-Mem 接入实例（B1-B11）

> adapter：`src/memory_benchmark/methods/amem_adapter.py`
>
> 状态：**B1-B11 已按 current product 重认证，`method-frozen-v1`。**

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
- **B5 ✅（retrieval metric=N/A）**：Chroma 检索对象是 evolution 后的当前
  `MemoryNote`，其 links/context/tags 已不是原始 dataset turn；即使 content/id/source time
  字段仍稳定，sidecar 也只能证明该 turn 参与过生成，不能把当前记忆重新解释成原始 evidence。
  因此 Recall@K/Precision@K/NDCG 不运行、不报告；sidecar 只用于审计、HaluMem delta 与隔离
  验货。
- **B6 ✅**：add_note 同步完成 note 写入与 evolution；无待 flush 的 buffer。
- **B7 ✅**：build LLM、embedding、retrieval 与 framework answer 真实 observation 可落盘。
- **B8 ✅**：检索只读；官方 swallow-error 两处在 wrapper fail-fast；endpoint/timeout/retry 注入。
- **B9 ✅**：`gpt-4o-mini` + product-default MiniLM-384/Chroma cosine；revision 诚实 unpinned。
- **B10 ✅**：主 TOML 跨五 benchmark 固定；作者 LoCoMo builder/复现参数不混入主表。
- **B11 ✅**：最终主树全量 `1680 passed`、compileall 0；五 benchmark 共 11 个真实 run
  覆盖 W1/W2、BEAM 100K/10M、HaluMem extraction/update/QA/type，artifact/state/
  efficiency 机器门全部通过；冻结记录见
  [`amem-frozen-v1.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/amem/notes/amem-frozen-v1.md)。

实现与算法证据见
[`amem-official-product-r1-implementation.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/amem/notes/amem-official-product-r1-implementation.md)。

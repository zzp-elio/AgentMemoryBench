# Actor 卡 M0-9：provenance 铺开到 lme/membench/beam 注入路径（小卡）

> 派发日 2026-07-13。自包含代码卡。允许修改：
> `src/memory_benchmark/methods/lightmem_adapter.py`、tests、新建
> `docs/workstreams/ws02.7-method-track/notes/m0-9-provenance-breadth.md`。
> 禁改 third_party（M0-7b 的 diff 已够用）、禁真实 API。
> **与 M0-8 卡都动 adapter，必须串行。**

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m09 -b actor/m0-9-provenance
cd /Users/wz/Desktop/mb-actor-m09 && uv sync
```
禁 push；只跑目标测试 + compileall（playbook #18）。

## 1. 背景

M0-7b 已落地 external_id → `MemoryEntry.source_external_id` → payload →
`RetrievedItem.source_turn_ids` 全链（notes/m0-7-lightmem-provenance.md §6），
locomo 实证 recall n=1。但**只有 locomo 批次构建器附了 `external_id`**
（adapter `_conversation_to_lightmem_batches` 内两处）；lme pair 路径与
membench/beam 走的 v3 TurnEvent 路径未附 → 这些 benchmark 检索时优雅回落
none。本卡把剩余注入路径全部接上。

## 2. 施工内容

1. **找全消息构建点**：adapter 内所有把 turn 转成 LightMem message dict 的
   位置（已知 lme pair 构建器 adapter:1158-1207 一带 + v3/native 批路径
   `_write_native_batch` 上游的构建处），逐处列锚。
2. **附 id**：每处给 user/assistant 消息副本加 `external_id` = 该 turn 的
   **公开 canonical turn id**（与 locomo 处同语义）。
3. **评测契约对齐核查（每 benchmark 一节，硬答案）**：逐个读
   `evaluators/longmemeval_recall.py`、`longmemeval_retrieval_rank.py`、
   `membench_recall.py`、`beam_recall.py`——它们期望的 id 空间是 turn 级还是
   session 级、键名是什么、与我们 `Question`/private label 的 evidence 格式
   如何对上。**若某家 evidence 粒度 ≠ turn（如 session 级）**：在 adapter 的
   provenance 出口不变的前提下说明映射方案（turn id → session id 可由公开
   turn id 结构派生则派生;派生不了 → 该 benchmark 的对齐记 gap,不硬造），
   停给架构师裁决,不擅自实现降粒度转换以外的逻辑。
4. **测试**：每条新路径一个离线测试（构造 TurnEvent/pair → 消息 dict 断言
   `external_id` 就位）；回归确认 locomo 路径不动。

## 3. 完成门
目标测试 + compileall 全绿（报数字）；note = 构建点清单 + 逐 benchmark 契约
对齐表 + gap 清单（若有）。真实验证（各 benchmark 新 predict 点亮 recall）
由架构师/用户随后跑，不在本卡。

## 4. 停工条件
- 某 benchmark 的 evidence id 空间与公开 turn id 无确定映射；v3 路径构建点
  被多 benchmark 共享导致 per-benchmark 语义分叉。

## 施工报告（actor 填写）
（待填）

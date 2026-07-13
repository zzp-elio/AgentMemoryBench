# M0-5：HaluMem 官方 harness 喂法取证

更新日期：2026-07-13

## 0. 口径与范围

- 官方评测目录实际为 `third_party/benchmarks/HaluMem-main/eval/`；其 README 明列六个
  wrapper，并声明它们遵守同一输入/输出契约
  （`third_party/benchmarks/HaluMem-main/eval/README.md:81-92`）。本文的“官方支持”仅指
  这些随 HaluMem 仓库发布、且被聚合器 `--frame` 接受的 wrapper；聚合器 choices 与六家
  一致（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:508-524`）。
- 本文只描述代码事实，不判断 LightMem 应采用哪种适配方案。下文把“前后 diff”严格区分为
  “全库前后快照相减”和“按时间窗/响应 ID 读取本次增量”。

## 1. 官方支持的 method 名单

| method / 变体 | 官方适配文件 | 注册证据 |
| --- | --- | --- |
| Mem0 | `eval_memzero.py`（`third_party/benchmarks/HaluMem-main/eval/README.md:83-86`） | scorer frame=`memzero`（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:508-514`） |
| Mem0 Graph | `eval_memzero_graph.py`（`third_party/benchmarks/HaluMem-main/eval/README.md:83-87`） | scorer frame=`memzero-graph`（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:508-514`） |
| MemOS | `eval_memos.py`（`third_party/benchmarks/HaluMem-main/eval/README.md:83-88`） | scorer frame=`memos`（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:508-514`） |
| Memobase | `eval_memobase.py`（`third_party/benchmarks/HaluMem-main/eval/README.md:83-89`） | scorer frame=`memobase`（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:508-514`） |
| Zep | `eval_zep.py`（`third_party/benchmarks/HaluMem-main/eval/README.md:83-90`） | scorer frame=`zep`（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:508-514`） |
| Supermemory | `eval_supermemory.py`（`third_party/benchmarks/HaluMem-main/eval/README.md:83-90`） | scorer frame=`supermemory`（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:508-514`） |

## 2. 逐 method 喂法

| method | 实际注入粒度 | wrapper / method 接口签名与实际调用 | session 边界如何告知 method |
| --- | --- | --- | --- |
| Mem0 | 外层逐 session；一个 session 的完整 dialogue 先转成 role/content 列表，再一次 add（`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:168-194`）。 | wrapper `add_memory(client, user_id, message, timestamp)`；实际 `client.add(message, user_id=..., version="v2", output_format="v1.1", timestamp=..., enable_graph=False)`（`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:75-88`）。 | 没有 session id 参数；同一用户连续写入，session 只由 harness 循环的一次调用和该 session 的 start timestamp 隐式划界（`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:168-194`）。 |
| Mem0 Graph | 外层逐 session；完整 dialogue 一次 add（`third_party/benchmarks/HaluMem-main/eval/eval_memzero_graph.py:184-210`）。 | wrapper `add_memory(client, user_id, message, timestamp, retries=3, retry_delay=1.0)`；实际 `client.add(..., enable_graph=True)`，签名中的 `retries/retry_delay` 在函数体未传给 client（`third_party/benchmarks/HaluMem-main/eval/eval_memzero_graph.py:80-93`）。 | 没有 session id 参数；靠一次调用与 session start timestamp 隐式划界（`third_party/benchmarks/HaluMem-main/eval/eval_memzero_graph.py:184-210`）。 |
| MemOS | 外层逐 session；session dialogue 转成带 `chat_time` 的 messages，再按 20 条一批写入（`third_party/benchmarks/HaluMem-main/eval/eval_memos.py:71-97,172-188`）。 | wrapper `add(messages, user_id, conv_id)` POST `/product/add`，payload 含 messages/user_id/mem_cube_id/conversation_id、`mode="fine"`、`async_mode="sync"`（`third_party/benchmarks/HaluMem-main/eval/eval_memos.py:46-68`）。 | 显式：每个 session 生成 `conv_id=f"{session_id}_{user_name}"`，每个内部 batch 复用它（`third_party/benchmarks/HaluMem-main/eval/eval_memos.py:170-188`）。 |
| Memobase | 外层逐 session；每 session 内按 20 turns 构造 `ChatBlob` 并 insert。虽然调用点传 `batch_size=10`，函数进入后硬重置为 20，故实际为 20（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:150-168,241-255`）。 | wrapper `add_memory(client, user_id, dialogues, batch_size=20)`；每批实际 `u.insert(ChatBlob(messages=...))` 后 `u.flush(sync=True)`（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:150-174`）。 | method 调用无 session id；所有 session 共用同一 Memobase user，边界靠 harness 逐 session 调用及 wrapper 记录的本次 wall-clock 起点隐式划界（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:150-174,241-255`）。 |
| Zep | 外层逐 session；一个 session 先按最多 28 条且最多 2400 字符切块，再逐块 add messages（`third_party/benchmarks/HaluMem-main/eval/eval_zep.py:57-95,161-177`）。 | wrapper `add_memory(client, user_id, thread_id, messages)` 先 `client.thread.create(thread_id=..., user_id=...)`，再调用 `client.thread.add_messages(thread_id, messages=...)`（`third_party/benchmarks/HaluMem-main/eval/eval_zep.py:138-177`）。 | 显式：每个 session 新建随机 `thread_id`，写入后保存为 `zep_thread_id`（`third_party/benchmarks/HaluMem-main/eval/eval_zep.py:280-297`）。 |
| Supermemory | 外层逐 session；session dialogue 按 20 turns 拼为文本块后逐块写入（`third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:47-72,175-195`）。 | wrapper `add_memory(client, user_id, dialogues, conv_id, batch_size=20)`；实际 `client.memories.add(content=..., container_tag=user_id, metadata={"conv_id": conv_id})`（`third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:47-72`）。 | 显式：每 session 生成 `conv_id=f"{session_id}_{user_name}"` 并放入每个块的 metadata；用户空间由 container_tag 划分（`third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:60-65,175-195`）。 |

## 3. memory points 收集口径

这里的官方候选产物字段统一名为 `extracted_memories`；gold 字段仍是数据中的
`memory_points`（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:49-57`）。

| method | 官方如何取得“本 session 新增的记忆” | add 是否直接返回 entries | 是否是 flush / 事后收集姿势 |
| --- | --- | --- | --- |
| Mem0 | 直接取本 session `client.add` 返回的 `result["results"][*]["memory"]`（`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:189-207`）。 | 是，wrapper 返回 client result 与时长（`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:75-88`）。 | 无显式 flush；无全库前后 diff（该 wrapper 的收集点即 add 返回，`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:189-207`）。 |
| Mem0 Graph | 直接取本 session add 返回的 `result["results"][*]["memory"]`（`third_party/benchmarks/HaluMem-main/eval/eval_memzero_graph.py:205-223`）。 | 是，wrapper 返回 client result 与时长（`third_party/benchmarks/HaluMem-main/eval/eval_memzero_graph.py:80-93`）。 | 无显式 flush；无全库前后 diff（`third_party/benchmarks/HaluMem-main/eval/eval_memzero_graph.py:205-223`）。 |
| MemOS | 每个同步 batch 的 HTTP 响应 `response["data"][*]["memory"]` 立即累积，session 结束后写入 `extracted_memories`（`third_party/benchmarks/HaluMem-main/eval/eval_memos.py:85-97,198-201`）。 | 是：`add` 返回 response JSON，`add_dialogue` 将其中 memories 聚合后返回（`third_party/benchmarks/HaluMem-main/eval/eval_memos.py:46-68,85-97`）。 | API payload 明确 `async_mode="sync"`，但 wrapper 未调用名为 flush/dump 的接口，也未做库 diff（`third_party/benchmarks/HaluMem-main/eval/eval_memos.py:50-68`）。 |
| Memobase | 每批 `insert` 后强制 `u.flush(sync=True)`；全部批次结束后，以 wrapper 开始时间为下界直接查询底层 DB 中该 user 的 `created_at` 或 `updated_at` 记录，再格式化为 memories（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:101-114,150-174,265-269`）。 | 否：`u.insert` 的 `bid` 未作为 memory entries 返回/使用；候选来自随后的 DB 查询（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:164-174`）。 | **有显式 force-flush**，且最后一个 batch 后也执行；**有事后存储增量读取**。它不是“导出全库前后快照再做集合相减”，而是按开始时间查询新增或更新行（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:101-114,150-174`）。 |
| Zep | add 阶段只保存 thread id；另一个 search 阶段调用 `thread.get_user_context(thread_id, mode="basic")` 并解析 context，写为 `extracted_memories`（`third_party/benchmarks/HaluMem-main/eval/eval_zep.py:186-197,331-367`）。 | 否：wrapper `add_memory` 只返回 duration（`third_party/benchmarks/HaluMem-main/eval/eval_zep.py:161-177`）。 | 无显式 flush；属事后 thread dump/context 读取，但官方说明该接口只返回近期 memories、不是该 session 的完整集合（`third_party/benchmarks/HaluMem-main/eval/README.md:137-141`）。 |
| Supermemory | add 只收集每批 response id；随后逐 id 轮询 `memories.get` 到 done，再从该响应对象的 `memories` 取出 memory 文本并合并为本 session 候选（`third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:47-72,81-106,205-218`）。 | 否：add 返回 response id 列表，不返回 entries（`third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:47-72`）。 | 无名为 force-flush 的调用；有**事后按本次响应 ID 收集**，不是全库 diff（`third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:81-106,205-218`）。 |

## 4. 无原生返回能力 / 无 session 概念时的官方处理

- **官方处理过“add 不返回 entries”**：Zep 的 add wrapper 只返回时长，后续从该
  session 的 thread context 读取；Supermemory 的 add 只返回 response ids，后续逐 id
  轮询读取生成 memories（`third_party/benchmarks/HaluMem-main/eval/eval_zep.py:161-197,331-367`；
  `third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:47-106,205-218`）。
- **官方处理过“method 调用没有 session id，且 add/insert 不提供 entries”**：
  Memobase 对同一 user 逐 session 写入，wrapper 强制同步 flush 后按本次开始时间查底层
  DB 增量。README 明说因为没有 Get Dialogue Memory API，官方采用本地部署并直读底层
  数据库（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:101-114,150-174,241-269`；
  `third_party/benchmarks/HaluMem-main/eval/README.md:128-135`）。
- **官方也保留无法完整取得 session memories 的系统，但不宣称问题已解决**：Zep
  wrapper 仍把 `get_user_context` 的近期结果写进 `extracted_memories`；README 明确说
  无法评 extraction，生成的 `memory_accuracy`/`memory_recall` 不能准确反映性能
  （`third_party/benchmarks/HaluMem-main/eval/eval_zep.py:365-367`；
  `third_party/benchmarks/HaluMem-main/eval/README.md:137-141`）。代码没有为 Zep 跳过
  extraction 的 frame 分支；它仍是 scorer choice（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:508-524`）。
- 六家中没有 wrapper 修改 method vendored 源码的路径；发布面是独立的六个 eval
  wrapper（`third_party/benchmarks/HaluMem-main/eval/README.md:81-92`）。这是对发布目录
  结构的事实描述，不推断各 pip/service 实现内部行为。

## 5. 指标与收集产物的耦合面

| 指标面 | scorer 的实际输入 | 收集不到时的官方代码行为 |
| --- | --- | --- |
| memory integrity / omission（gold 逐点 recall） | 每个非 generated-QA session 必须读取 `memory_points` 与 `extracted_memories`；把候选 join 后与每个 gold memory point 比较（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:49-70`）。 | `extracted_memories=[]` 时，候选字符串为空，代码直接给每个 integrity record 记 0；不是跳过（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:104-111`）。若字段根本不存在，`session["extracted_memories"]` 直接取值会抛 `KeyError`（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:49-56`）。 |
| memory accuracy / hallucination（candidate 逐点 precision） | 对 `extracted_memories` 中每一条候选，用 dialogue 与非 interference gold memories 评 accuracy（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:72-95,129-152`）。 | 候选空时不会生成 accuracy record；聚合器仍直接用 `memory_accuracy_num`、`target_memory_accuracy_num` 作除数，未见 skip/零分保护，因而全空时会发生除零而非稳定记 0（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:252-286`）。 |
| extraction F1 | precision 取上述 target accuracy(all)，recall 取 integrity recall(all)（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:288-292`）。 | 依赖前两面先成功聚合；没有单独的 missing/empty 分支（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:252-292`）。 |
| memory update | 不使用 `extracted_memories`；只对标为 update 且 wrapper 已填入 `memories_from_system` 的 gold point 建输入，候选来自按该 gold memory 查询的检索结果（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:58-70,154-174`）。 | 若没有 `memories_from_system`，该 update gold 会落入 integrity 分支，不进入 update scorer（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:58-70`）。 |
| QA | 不直接使用 `extracted_memories`；输入是 question/answer/gold evidence 与 wrapper 已生成的 `system_response`（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:97-102,176-197`）。 | 缺 `system_response` 会在构造 judge 调用参数时直接取值失败；没有 skip/记 0 分支（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:176-187`）。 |

因此，本卡所问的“存在性/幻觉类”memory extraction 指标，输入正是六个 wrapper 写入的
`extracted_memories`；update 和 QA 是另两条输入链，并不复用该 session 候选集合
（`third_party/benchmarks/HaluMem-main/eval/evaluation.py:49-102,154-197`）。

## 6. 结论小表（仅事实）

| 官方存在 session 级批量注入姿势？ | 官方存在事后 diff / 增量收集姿势？ | 官方存在 force-flush 姿势？ |
| --- | --- | --- |
| **有**：六个 wrapper 都在外层逐 session 调用；例如 Mem0 整 session 一次 add，MemOS/Supermemory 则 session 内再分 batch（`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:168-194`；`third_party/benchmarks/HaluMem-main/eval/eval_memos.py:71-97,172-188`；`third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:47-72,175-195`）。 | **有**：Memobase 在写入完成后按本次开始时间查底层 DB 的新增/更新行；这是时间窗增量读取，不是全库前后快照相减。另有 Supermemory 按本次 response ids 事后收集（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:101-114,150-174`；`third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:81-106,205-218`）。 | **有**：Memobase 每个 batch 的 `insert` 后显式 `u.flush(sync=True)`，因此最后一个 batch 后同样强制同步 flush，再查 DB（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:150-174`）。 |

## 7. MemoryData 对照与来源待溯

- `第三方框架参考/MemoryData/` 的 README 明列其四个 benchmark family 为
  MemoryAgentBench、LoCoMo、LongBench、MemBench，目录布局也只列这四类，未接 HaluMem
  （`第三方框架参考/MemoryData/README.md:39-43,67-69,173-190`）。
- **来源待溯：0 项。**

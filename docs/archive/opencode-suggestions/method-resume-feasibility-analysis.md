# Method 断点重连可行性分析

更新日期：2026-06-17

本文梳理四个 method 的 resume 现状、turn 级 vs conversation 级的实现条件、以及建议的分级策略。

---

## 一、当前 resume 状态

| Method | 实现 `BaseResumableMemorySystem`? | 状态持久化？ | 当前 resume 行为 |
|---|---|---|---|
| Mem0 | 是（`add_from_turn`） | 是（Qdrant + SQLite） | turn 级 resume |
| MemoryOS | 否（非标 `load_existing_conversation_state`） | 是（JSON 文件） | conversation 级 resume |
| A-Mem | 否 | **无**（纯内存：dict + Faiss） | conversation 级，但进程重启状态全丢 |
| LightMem | 否 | 是（Qdrant 文件） | conversation 级 |

---

## 二、turn 级 resume 的必备条件

要实现 turn 级（或最小喂入单元级）resume，method 必须同时满足三个条件：

### 条件 1：写入接口可逐单元独立调用

每个最小单元的写入不依赖前一个单元在进程内存中的上下文。换句话说，可以跳过前 N 个单元，直接从第 N+1 个开始调。

```python
# 示例：adapter 内部的 add_from_turn()
for i, turn in enumerate(turns):
    if i < start_turn_index:
        continue                           # 跳过已完成的
    method.native_add(turn)                # 独立调用，不依赖前面
```

### 条件 2：每个单元写入后状态立即持久化

每完成一个单元写入，其效果必须已经落地到磁盘/外部存储，不能只停在进程内的 buffer。否则进程重启后，runner 认为"已完成"的单元在 method 侧实际上丢了。

**反面例子——LightMem**：`add_memory()` 调用层面是 turn-pair 级别，但前 N-1 次调用只把消息堆在 buffer 里，只有最后一次 `force_extract=True` 才 flush 全部积压、写 Qdrant。所以中间任何一次调用的"完成"不等于"已持久化"，不能作为 turn 级 resume 的断点。

**正面例子——Mem0**：每次 `Memory.add([message])` 都是完整的提取→embedding→写入 Qdrant 管线，调完就落地，可以按每次调用作为断点。

### 条件 3：重复 add 不会产生副作用

如果 checkpoint 记录有误（比如刚完成 turn 5、还没写入 checkpoint 就崩溃了），resume 时 runner 可能从 turn 5 开始重调。method 必须能安全处理这种情况——不会因为重复调用产生错误、脏数据或 panic。

**Mem0 的处理**：Qdrant 按 UUID 存储，重复调用会产生相同内容的新记录（不同 UUID），不会报错或写脏数据。这是可接受的。

### 条件汇总

| Method | 条件 1：逐单元独立调？ | 条件 2：即调即持久化？ | 条件 3：可重复调？ | 能 turn 级 resume？ |
|---|---|---|---|---|
| Mem0 | 是，`Memory.add([message])` | 是，每次完整管线 | 是，不同 UUID | **是（已实现）** |
| A-Mem | 是，`add_note(content)` | **否**，纯内存 | — | 否（缺持久化） |
| MemoryOS | **否**，最小单元是 QA pair（两 turn 拼一页） | 是，每次写 JSON 文件 | — | 否（降不到 turn 级） |
| LightMem |**否**，调用是 turn-pair 但内部 buffer 积压，仅最后 force 才 flush | 是，Qdrant 文件 | — | 否（中间无持久化语义） |

---

## 三、分级 resume 策略

### 层级定义

```
turn 级 resume
  → 如果跑 100 个 turn 时在第 50 个崩溃，resume 从第 51 个开始
  → 要求：method 的三个条件全满足

conversation 级 resume
  → 如果跑 10 个 conversation 时第 4 个崩溃，resume 跳过前 3 个，从第 4 个开始
  → 要求：method 的状态可跨进程持久化（每个 conversation 完成后存盘）
  → 第 4 个 conversation 的 turn 从头重加
```

### 按 method 分配

| Method | 采用级别 | 原因 |
|---|---|---|
| Mem0 | turn 级 | 三个条件全满足，已实现 `add_from_turn()` |
| MemoryOS | conversation 级 | 最小单元是 QA pair（降不到 turn），但 JSON 文件持久化满足 conversation 级 |
| A-Mem | conversation 级（加 wrapper 持久化后） | 不满足条件 2（纯内存），加持久化后可满足 conversation 级。turn 级在有持久化后也可以加，但收益很小（crash 后重写一个 conversation 就是几百次 `add_note`，API 成本仍在可接受范围） |
| LightMem | conversation 级 | 不满足条件 2（buffer 机制），但 Qdrant 持久化满足 conversation 级。turn 级做不了，因为中间 trun 的"完成"不保证已持久化 |

### Runner 行为

```python
# prediction.py 现有逻辑
if isinstance(system, BaseResumableMemorySystem):
    result = system.add_from_turn(start_turn_index, ...)   # turn 级
else:
    result = system.add([conversation])                     # conversation 级
```

runner 根据 method 是否实现 `BaseResumableMemorySystem` 自动选择路径。
`conversation_status.json` 决定哪些 conversation 跳过。
`method_predictions.jsonl` 决定哪些 question 跳过（question 级 resume 对所有 method 通用）。

---

## 四、question 级 resume

### 为什么简单

question 级 resume 对所有 method 通用且已经实现，原因：

1. **`get_answer()` 是只读操作**——检索已有记忆、拼 prompt、调 LLM、返回答案。不修改 method 的持久化状态
2. **每答完一个立即记录**——`method_predictions.jsonl` 原子写入，崩溃不会丢
3. **adapter 零感知**——它不知道也不需要知道自己在被 resume
4. **重问安全**——崩溃时该 question 的答案没写进 JSONL，resume 后重调一次 `get_answer()`，不会影响已持久化的记忆

### 四个 method 的 `get_answer()` 是否有状态修改？

| Method | `get_answer()` 流程 | 修改持久化状态？ |
|---|---|---|
| Mem0 | `search()` → 拼 prompt → LLM → 返回 | 否（search 只读） |
| MemoryOS | `retrieve()` → `generate_system_response_with_meta()` → LLM | 否（retrieve 和生成均为只读） |
| A-Mem | `find_related_memories_raw()` → 拼 prompt → LLM | 否（检索只读） |
| LightMem | `retrieve()` → 拼 prompt → LLM | 否（检索只读） |

全部四个 method 的 `get_answer()` 都不修改持久化状态，因此 **question 级 resume 天然安全，不需要 method 做任何特殊支持**。

### 如果 `get_answer()` 会修改状态怎么办？

这种情况 question 级 resume 就会复杂——崩溃后重问同一个问题，可能对 method 状态产生两次影响（比如把回答也写入记忆，导致重复）。但**这不是当前四个 method 的情况**。如果将来接入的 method 有这种行为，需要单独评估是否需要引入问后状态回滚/快照机制。

### Runner 侧实现

```
1. 读 method_predictions.jsonl → 已有答案的 question_id 集合
2. 筛选：pending = [q for q in questions if q.question_id not in answered]
3. 只对 pending 调 system.get_answer(q)
4. 每批完成 → atomic_write_jsonl(全部 predictions)
```

没有任何 adapter 参与，完全由 runner 控制。

---

## 五、A-Mem Wrapper 层持久化方案（支撑 conversation 级 resume）

### 问题

`RobustAgenticMemorySystem` 的状态全在内存：

```python
self.memories: Dict[str, RobustMemoryNote] = {}
self.retriever = SimpleEmbeddingRetriever(model_name)  # Faiss
```

进程重启后 state 全丢，conversation 级 resume 无法实现——已完成的 conversation 状态不存在，必须重加。

### 方案：Wrapper 层持久化（不改 A-Mem 源码）

`add()` 完成后，adapter 把状态序列化到磁盘：

```text
checkpoints/<cid>/
  faiss.index      ← faiss.write_index()
  memories.json    ← 序列化 memories 字典（content/context/keywords/tags/timestamp/links/id）
  evo_cnt.json     ← 演进计数器
```

resume 时从文件重建：

```text
faiss.read_index("checkpoints/<cid>/faiss.index")
memories = 反序列化("checkpoints/<cid>/memories.json")
重建 runtime.memories 和 runtime.retriever
```

### 为什么这是最优方案

- **不改第三方源码**：所有持久化逻辑在 adapter wrapper 层，A-Mem 的 `memory_layer_robust.py` 一行不动
- **不改变算法行为**：Faiss Flat 索引的序列化/反序列化保证检索向量和距离完全一致
- **对实验结果零影响**：只是 `add()` 完成后多了磁盘 I/O，检索和回答路径不变
- Faiss 自带 `write_index()`/`read_index()`，Flat 索引不需要额外依赖

### 不推荐的方案

| 方案 | 问题 |
|---|---|
| 替换 Faiss 为 Qdrant | 改变了检索器的距离计算和实现，理论上可能影响检索排序 |
| 修改 A-Mem 源码加 save/load | 违反"不修改第三方核心算法"的项目规则 |
| 用 pickle 序列化 | JSON 可审计、可人工检查、跨版本安全，pickle 有反序列化安全风险 |
| 不做持久化，接受重跑 | 每次 resume 重加所有已完成的 conversation，浪费大量 LLM API 调用 |

---

## 六、conversation 级 resume 并行失败恢复示例

场景：10 个 conversation 并行跑，第 4 个失败（比如 API 超时）。

```
正常跑：
  conv 1-3 完成，状态写入 checkpoints/conv_1/faiss.index 等
  conv 4 失败（API 超时或崩溃）
  conv 5-10 继续完成，状态持久化

resume 时：
  adapter 新建实例
  读取 conversation_status.json → conv 1-3、5-10 已完成
  [Mem0]     传入 existing_conversation_ids={1,2,3,5,6,7,8,9,10}
  [MemoryOS] 逐 conv 调 load_existing_conversation_state()
  [A-Mem]    从 disk 反序列化 Faiss 索引 + memories 字典
  [LightMem] 创建新 LightMemory 实例指向已有 Qdrant collection
  只重新跑 conv 4 的 add()
  对所有 unconversation 的 pending question 调 get_answer()
```

---

## 七、总结

1. **turn 级 resume 的准入门槛高**：需要 method 同时满足"逐单元独立调 + 即调即持久化 + 可安全重复调"三个条件。四个 method 中只有 Mem0 满足，不要强行给其他 method 加 turn 级 resume
2. **conversation 级 resume 是默认策略**：对不满足 turn 级条件的 method，采用 conversation 级——runner 通过 `conversation_status.json` 跳过已完成的 conversation，未完成的整 conversation 重加
3. **A-Mem 必须加 wrapper 层持久化**：当前纯内存状态导致 conversation 级 resume 都无法实现。方案是用 Faiss 自带序列化 + JSON，不改源码、不影响实验结果
4. **question 级 resume 对所有 method 通用**：不受 method 类型限制，runner 直接读 `method_predictions.jsonl` 跳过已回答的问题

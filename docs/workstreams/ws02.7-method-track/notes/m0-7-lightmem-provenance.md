# M0-7 LightMem provenance 取证断点

> 日期：2026-07-13  
> actor：Codex（GPT-5）  
> 状态：**Phase A 停工，未进入实现**

## 1. 结论

**触发任务卡停工条件：当前 `source_id` / `sequence_number` 只在一次抽取触发
范围内可定位消息，跨 conversation 的多次抽取会重新从 0 编号；仅把
`source_sequence` 条件写入 payload，adapter 无法只凭自己提交消息的全局顺序
无歧义恢复公开 turn id。**

本卡批准的 third-party 最小 diff 没有为来源字段同时携带“抽取触发身份”或公开
turn id。继续实现会让不同抽取触发产生的 `source_sequence=0` 指向不同公开 turn，
违反 GC-1 和 recall evaluator 对精确 canonical id 的要求。因此未修改源码或测试，
等待架构师裁定扩展来源身份的最小方案。

## 2. A1：`source_id` 的实际语义链

### 2.1 谁赋 sequence number

`MessageNormalizer` 只复制消息并补 `session_time`、规范化 `time_stamp`、`weekday`，
不赋 `sequence_number`（
`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:59-104`）。而且
`add_memory()` 每次调用都会新建一个 `MessageNormalizer`（
`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:264-276`）。

真正的编号者是 `assign_sequence_numbers_with_timestamps()`：函数入口将
`current_index = 0`，然后按本次 `extract_list` 的 batch → segment → message
遍历顺序连续写 `message["sequence_number"] = current_index`（
`third_party/methods/LightMem/src/lightmem/memory/utils.py:60-69,112-123`）。
`add_memory()` 在 short-memory buffer 触发抽取后调用该函数（
`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:323-340`）。

### 2.2 LLM 看到和返回的 id

OpenAI manager 在每个抽取 API call 中读取上述 `sequence_number`，但写入 prompt
时使用 `sequence_id // 2`（
`third_party/methods/LightMem/src/lightmem/factory/memory_manager/openai.py:281-313`）；
官方 extraction prompt 要求模型把消息整数前缀原样作为 `source_id`（
`third_party/methods/LightMem/src/lightmem/memory/prompts.py:8-30`）。因此在当前
adapter 固定 `messages_use="user_only"` 且每个可抽取 user 消息后跟一个 assistant
消息的路径中，LLM 返回值满足：

```text
source_id = sequence_number // 2
sequence_candidate = source_id * 2
```

后半式在转换器中现场实现（
`third_party/methods/LightMem/src/lightmem/memory/utils.py:247-271`），构造
`MemoryEntry` 时又用同一计算读取 timestamp/weekday/speaker（
`third_party/methods/LightMem/src/lightmem/memory/utils.py:289-351`）。

### 2.3 唯一性的真实边界

**硬答案 A1：`source_id` 不是 conversation 全局 user 消息索引，也不能简单称为
adapter 当前一次 `add_memory(messages)` 参数内的局部索引。它是“一次 extraction
invocation 的 `extract_list` 内，由遍历顺序得到的 user-message 索引”。**

原因是 short-memory buffer 是 backend 实例上的持久状态：未达到阈值的 segment
留在 `self.buffer`，后续 `add_memory()` 可继续追加；超过阈值时抽出旧 buffer，
`force_extract` 时抽出剩余 buffer（
`third_party/methods/LightMem/src/lightmem/factory/memory_buffer/short_term_memory.py:4-9,36-57`）。
所以一次抽取可能消费前几次 `add_memory()` 积累的消息。反过来，每次抽取调用
`assign_sequence_numbers_with_timestamps()` 都重新从 0 开始（
`third_party/methods/LightMem/src/lightmem/memory/utils.py:60-69`）。

adapter 的 LoCoMo 路径按每个公开 turn 提交一组 `user(content)+assistant("")`
（`src/memory_benchmark/methods/lightmem_adapter.py:1126-1156`），循环中只有最后一批
显式 `force_segment/force_extract=True`（
`src/memory_benchmark/methods/lightmem_adapter.py:474-502`）；v3 native 路径同样只在
最终 batch 强制刷洗（`src/memory_benchmark/methods/lightmem_adapter.py:568-587`）。
正式长 conversation 可因 token 阈值产生多个自然抽取触发，因此多个不同公开 turn
都可能最终持久化为 `source_id=0` / `source_sequence=0`。

### 2.4 同一 extraction invocation 内还有一个既有不一致

manager 展示给各 API call 的 `source_id` 来自对整个 `extract_list` 连续编号后的
`sequence_number // 2`（
`third_party/methods/LightMem/src/lightmem/factory/memory_manager/openai.py:295-313`）。
但 `max_source_ids` 却按每个 batch 的 user 数量分别计算（
`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:340-343`），转换器再用
这个 batch-local 上限裁剪模型返回值（
`third_party/methods/LightMem/src/lightmem/memory/utils.py:237-258`）。当一次 invocation
含多个 extraction batch 时，两种 id 空间并不一致。并且 topic 解析使用裁剪后的
`sid`，而 `_create_memory_entry_from_fact()` 又从原始 `fact_entry` 重读未裁剪的
`source_id`（`third_party/methods/LightMem/src/lightmem/memory/utils.py:260-281,313-326`）。
这是既有行为，本卡未获授权修正；它进一步说明不能把 payload 中单个 sequence 数字
视为稳定 conversation provenance。

## 3. A2：三个候选值的判定

| 候选 | 一手判定 | 能否由 adapter 无歧义映射公开 turn id |
|---|---|---|
| 原始 `source_id` | LLM 所见的 `sequence_number // 2`；每次 extraction invocation 重置 | 否；跨触发重复，且多 batch 上限逻辑与 prompt id 空间不一致 |
| 解析后的 `sequence_number` | 当前实现为 `source_id * 2`，同样随 invocation 重置 | 否；乘 2 不增加身份信息 |
| 两者同时保存 | 两者存在确定函数关系 | 否；仍缺 extraction invocation / conversation-global offset |

**硬答案 A2：在本卡批准的三个候选中，没有一个单独或组合后足以稳定回到公开
turn id。最可靠的来源键必须再包含一个不会跨抽取重置的身份，例如在 adapter
提交消息时附带并沿原消息对象透传的 canonical `turn_id`，或由 third-party 在
持久化时保存 `(extraction invocation identity, source_sequence)` 并让 adapter
维护同一 identity 的映射。两者都超出当前“仅增加一个已解析 sequence 可选字段、
目标约 10 行”的批准边界，需架构师裁定。**

不能用 timestamp/speaker/content 猜回 turn：这些字段允许重复；GC-1 要求精确公开
id，不能以启发式相似匹配制造 gold 映射。LoCoMo recall 实际要求每个 top-k item
携带非空 `source_turn_ids`（
`src/memory_benchmark/evaluators/locomo_recall.py:117-129`），并与私有 evidence 的
canonical id 直接做字符串集合命中（
`src/memory_benchmark/evaluators/locomo_recall.py:182-217`）。

## 4. 请求架构师裁定

建议在以下方向中裁定其一；本 note 不替架构师做设计决定：

1. 扩展批准边界，让 adapter 在每条提交 message 附加公开 `turn_id`，third-party
   在按 `sequence_number` 找到源 message 后把该值作为可选 `source_turn_id` 原样存入
   `MemoryEntry` / payload。该方向不依赖抽取触发边界，但需修改转换函数参数或让构造
   路径能访问源 message。
2. 引入 extraction invocation identity + sequence 的复合来源键，并明确 adapter
   如何获得完全相同的 invocation 边界；若需复制 short-buffer 算法则不建议。
3. 若只批准 `source_sequence`，将能力保持 `provenance_granularity="none"`，不能宣称
   recall@k 无损改造完成。

## 5. 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m07`
- branch：`actor/m0-7-lightmem-provenance`
- 创建命令：
  `git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m07 -b actor/m0-7-lightmem-provenance`
- 依赖：`uv sync` 成功，154 packages resolved、130 packages installed。
- 完成范围：Phase A 一手取证与 A1/A2 硬答案。
- 未执行：Phase B/C、目标 pytest、compileall；停工发生在任何代码改动之前。
- 真实 API：0。
- plan 偏差：无；按 §1/§4 的 Phase A 歧义停工条件执行。
- commit：本断点 note 单独提交；hash 见 actor 交付消息与本分支 `git log -1`。

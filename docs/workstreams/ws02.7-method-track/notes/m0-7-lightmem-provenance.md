# M0-7 LightMem provenance 取证断点

> 日期：2026-07-13  
> actor：Codex（GPT-5）  
> 状态：**M0-7b 已按 §5 裁决复工完成，待架构师验收**

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

## 6. M0-7b 裁决后施工

### 6.1 §5.2 前置验证

前置门通过。`MessageNormalizer` 对原 message 做 `copy.deepcopy()` 后只覆盖时间
字段，因此保留未知键（
`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:79-102`）。官方
LLMLingua compressor 和 entropy compressor 都只原地改 `content` 并返回原 dict
（`third_party/methods/LightMem/src/lightmem/factory/pre_compressor/llmlingua_2.py:39-90`；
`third_party/methods/LightMem/src/lightmem/factory/pre_compressor/entropy_compress.py:69-92`）。
sensory buffer 直接保存 message 对象并以 list copy/slice 切段，short buffer 再保存
这些 segment（
`third_party/methods/LightMem/src/lightmem/factory/memory_buffer/sensory_memory.py:15-38,43-113`；
`third_party/methods/LightMem/src/lightmem/factory/memory_buffer/short_term_memory.py:36-57`）。
`topic_segment=False` 的早退路径返回 normalizer 产出的 `msgs`（
`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:300-309`）。

离线测试
`test_lightmem_external_id_survives_official_preprocessing_pipeline` 与
`test_lightmem_external_id_survives_topic_segment_disabled_path` 分别锁定
pre-compress + 两级 buffer + extract_list 路径和 topic-segment 关闭路径；前置门
实际输出为 `2 passed, 37 deselected, 1 warning in 4.03s`。

### 6.2 实现与评测契约

- adapter 对 LoCoMo 的 user/空 assistant 两条 message 写同一个公开 `turn.turn_id`，
  对 LongMemEval pair 的每条 message 写各自公开 `turn.turn_id`（
  `src/memory_benchmark/methods/lightmem_adapter.py:1185-1212,1243-1264`）。字段名是
  benchmark-neutral 的 `external_id`，没有 benchmark 专用 provenance 分支。
- third-party 在 timestamp/weekday/speaker 的同一 sequence 遍历中平行构建
  `external_ids`（
  `third_party/methods/LightMem/src/lightmem/memory/utils.py:61-137`），并在现有
  `source_id * 2` 位置读取为 `MemoryEntry.source_external_id`（同文件
  `:211-364`）。context JSON 和 embedding payload 都只在值非 `None` 时新增键
  （同文件 `:140-165`；`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:419-440`）。
- adapter 将 payload 的 `source_external_id` 直接写入
  `RetrievedItem.source_turn_ids` 并声明 `provenance_granularity="turn"`（
  `src/memory_benchmark/methods/lightmem_adapter.py:301-305,1117-1155`）。任一命中
  缺字段时整次结果 `items=None` 且 result metadata 标 `none`，不返回部分来源
  制造假 recall（同文件 `:766-796,1117-1155`）。
- LoCoMo evaluator 对 top-k items 的 `source_turn_ids` 与私有 evidence canonical
  dia_id 作字符串精确匹配（
  `src/memory_benchmark/evaluators/locomo_recall.py:117-142,182-217`）。离线测试使用
  `evaluator_private_label_record()` 的真实私有序列化边界，构造
  `MemoryEntry → offline_update → 本地向量 search → RetrievalResult → locomo-recall`
  全链，实际得到 `total_questions=1`、`mean_score=1.0`。

### 6.3 零行为变化与已知限制

无 `external_id` 时，`MemoryEntry.source_external_id` 默认为 `None`，context JSON
逐键等于改造前 17 键，embedding payload 不新增键；对应测试为
`test_lightmem_conversion_and_storage_conditionally_preserve_external_id` 和
`test_lightmem_offline_update_conditionally_writes_external_id_payload`。抽取 prompt、
sid 计算、buffer、存储流程和检索排序均未修改。

归因精度原样继承上游 sid 体系：同一 extraction invocation 多 batch 时，prompt
展示的全 invocation sequence 与 `max_source_ids` 的 batch-local 裁剪不一致（本 note
§2.4），本改造不修复。provenance 与 LightMem 自身 timestamp/speaker 归因使用同一
`source_id * 2` 位置，因此只保证“不新增归因误差”，不宣称修复上游误归因；该项是
upstream issue 候选。

旧状态或非本 adapter 的 harness 没有附 `external_id` 时，检索仍正常返回 formatted
memory，但 provenance result metadata 回落 `none`，测试
`test_lightmem_retrieve_missing_external_id_falls_back_without_error` 锁定“不报错、不
返回部分来源”。新 run 的 manifest 声明 turn；源码 fingerprint 已因本 diff 改变，旧
状态不能冒充同一实验身份。

### 6.4 third-party 完整 diff（upstream PR 素材）

动机：LightMem extraction 已为每个 fact 解析来源消息，但构造 MemoryEntry 后丢失；
本 diff 允许调用方附中立 `external_id`，并把它纯透传到存储 payload。未附 id 时旧
序列化和 payload 逐键不变。下列为完整 `git diff`；仅清除了上游源码原有的行尾
空白，避免 Markdown 自身触发 `git diff --check`，其余逐行保留。

```diff
diff --git a/third_party/methods/LightMem/src/lightmem/memory/lightmem.py b/third_party/methods/LightMem/src/lightmem/memory/lightmem.py
index 860d8f7..0be1c20 100644
--- a/third_party/methods/LightMem/src/lightmem/memory/lightmem.py
+++ b/third_party/methods/LightMem/src/lightmem/memory/lightmem.py
@@ -337,7 +337,7 @@ class LightMemory:
         self.logger.debug(f"topic_id_mapping: {topic_id_mapping}")
         self.logger.info(f"[{call_id}] Assigned global topic IDs: total={sum(len(x) for x in topic_id_mapping)}, mapping={topic_id_mapping}")
         self.logger.info(f"[{call_id}] Extraction triggered {extract_trigger_num} times, extract_list length: {len(extract_list)}")
-        extract_list, timestamps_list, weekday_list, speaker_list, topic_id_map = assign_sequence_numbers_with_timestamps(extract_list, offset_ms=500, topic_id_mapping=topic_id_mapping)
+        extract_list, timestamps_list, weekday_list, speaker_list, external_ids, topic_id_map = assign_sequence_numbers_with_timestamps(extract_list, offset_ms=500, topic_id_mapping=topic_id_mapping)
         self.logger.debug(f"[{call_id}] Extract list sample: {json.dumps(extract_list)}")
         max_source_ids = [sum(1 for seg in batch for msg in seg if msg.get("role") == "user") - 1 for batch in extract_list]
         self.logger.info(f"[{call_id}] Batch max_source_ids: {max_source_ids}")
@@ -367,7 +367,8 @@ class LightMemory:
             speaker_list=speaker_list,
             topic_id_map=topic_id_map,
             max_source_ids=max_source_ids,
-            logger=self.logger
+            logger=self.logger,
+            external_ids=external_ids,
         )
         self.logger.info(f"[{call_id}] Created {len(memory_entries)} MemoryEntry objects")
         if boundmem_tags is not None:
@@ -433,6 +434,9 @@ class LightMemory:
                 }
                 if bam_tags:
                     payload["bam_tags"] = bam_tags
+                source_external_id = getattr(mem_obj, "source_external_id", None)
+                if source_external_id is not None:
+                    payload["source_external_id"] = source_external_id
                 self.embedding_retriever.insert(
                     vectors = [embedding_vector],
                     payloads = [payload],
diff --git a/third_party/methods/LightMem/src/lightmem/memory/utils.py b/third_party/methods/LightMem/src/lightmem/memory/utils.py
index ccf2067..67cfcc7 100644
--- a/third_party/methods/LightMem/src/lightmem/memory/utils.py
+++ b/third_party/methods/LightMem/src/lightmem/memory/utils.py
@@ -30,6 +30,7 @@ class MemoryEntry:
     update_queue: List = field(default_factory=list)
     consolidated: bool = False
     bam_tags: List[Any] = field(default_factory=list)
+    source_external_id: Optional[str] = None

 def clean_response(response: str) -> List[Dict[str, Any]]:
     """
@@ -66,6 +67,7 @@ def assign_sequence_numbers_with_timestamps(extract_list, offset_ms: int = 500,
     timestamps_list = []
     weekday_list = []
     speaker_list = []
+    external_ids = []
     message_refs = []

     for segments in extract_list:
@@ -120,6 +122,7 @@ def assign_sequence_numbers_with_timestamps(extract_list, offset_ms: int = 500,
                     'speaker_name': message.get('speaker_name', 'Unknown')
                 }
                 speaker_list.append(speaker_info)
+                external_ids.append(message.get("external_id"))
                 current_index += 1

     sequence_to_topic = {}
@@ -131,7 +134,7 @@ def assign_sequence_numbers_with_timestamps(extract_list, offset_ms: int = 500,
                     seq = msg.get("sequence_number")
                     sequence_to_topic[seq] = tid

-    return extract_list, timestamps_list, weekday_list, speaker_list, sequence_to_topic
+    return extract_list, timestamps_list, weekday_list, speaker_list, external_ids, sequence_to_topic

 # TODO：merge into context retriever
 def save_memory_entries(memory_entries, file_path="memory_entries.json"):
@@ -157,6 +160,8 @@ def save_memory_entries(memory_entries, file_path="memory_entries.json"):
         }
         if getattr(entry, "bam_tags", []):
             data["bam_tags"] = entry.bam_tags
+        if getattr(entry, "source_external_id", None) is not None:
+            data["source_external_id"] = entry.source_external_id
         return data

     if os.path.exists(file_path):
@@ -210,7 +215,8 @@ def convert_extraction_results_to_memory_entries(
     speaker_list: List = None,
     topic_id_map: Dict[int, int] = None,
     max_source_ids: List[int] = None,
-    logger = None
+    logger = None,
+    external_ids: List[Optional[str]] = None,
 ) -> List[MemoryEntry]:
     """
     Convert extraction results to MemoryEntry objects.
@@ -278,6 +284,7 @@ def convert_extraction_results_to_memory_entries(
                     topic_id=resolved_topic_id,
                     topic_summary="",
                     logger=logger,
+                    external_ids=external_ids,
                 )

                 if mem_obj:
@@ -293,7 +300,8 @@ def _create_memory_entry_from_fact(
     speaker_list: List = None,
     topic_id: int = None,
     topic_summary: str = "",
-    logger = None
+    logger = None,
+    external_ids: List[Optional[str]] = None,
 ) -> Optional[MemoryEntry]:
     """
     Helper function to create a MemoryEntry from a fact entry.
@@ -326,6 +334,7 @@ def _create_memory_entry_from_fact(
         speaker_info = speaker_list[sequence_n]
         speaker_id = speaker_info.get('speaker_id', 'unknown')
         speaker_name = speaker_info.get('speaker_name', 'Unknown')
+        source_external_id = external_ids[sequence_n] if external_ids else None

     except (IndexError, TypeError, ValueError) as e:
         if logger:
@@ -337,6 +346,7 @@ def _create_memory_entry_from_fact(
         weekday = None
         speaker_id = 'unknown'
         speaker_name = 'Unknown'
+        source_external_id = None

     mem_obj = MemoryEntry(
         time_stamp=time_stamp,
@@ -348,6 +358,7 @@ def _create_memory_entry_from_fact(
         topic_id=topic_id,
         topic_summary=topic_summary,
         consolidated=False,
+        source_external_id=source_external_id,
     )

     return mem_obj
```

### 6.5 upstream PR 素材与遗留门

- 动机：不绕开 LightMem 抽取算法，保留 LLM 已选定的 fact source，支持下游可审计
  recall@k。
- diff 性质：一个可选 message 键、一个可选 dataclass 字段、两个条件 serializer；
  未使用功能时 storage payload 不变。
- 测试证据：未知键穿透、无来源旧形状、条件 payload、本地检索及 LoCoMo recall
  均为离线测试。
- 遗留：真实 API smoke 的 `locomo-recall n>0` 仍待用户授权运行；本批未调用真实
  API。

### 6.6 M0-7b 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m07b`
- branch：`actor/m0-7b-lightmem-provenance`
- 创建命令：
  `git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m07b -b actor/m0-7b-lightmem-provenance`
- `uv sync`：154 packages resolved，130 packages installed/checked。
- 定向测试：`uv run pytest -q tests/test_lightmem_adapter.py` →
  `43 passed, 1 warning in 4.62s`。
- compile：`uv run python -m compileall -q src/memory_benchmark tests` → exit 0，
  无输出。
- 真实 API：0；未运行全量 pytest。
- 允许面解释：§5.3 明确新增“写进 note 与实例文档”，因此除初始 allowlist 外仅定向
  更新 `docs/reference/integration/lightmem.md` 的既有 B5 条目；未改其他实例章节。
- 已知限制：sid 多 batch 归因问题未修；真实 locomo smoke recall 仍待用户授权。

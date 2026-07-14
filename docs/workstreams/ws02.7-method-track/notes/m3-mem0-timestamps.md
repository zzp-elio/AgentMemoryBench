# M3 Mem0 formatted_memory 时间口径取证与施工

> 日期：2026-07-14。范围仅为 Mem0 adapter 的检索时间归一化；零真实 API，
> 未修改 third_party、benchmark adapter 或 runner。

## 1. Phase A：官方 answer 上下文时间口径

三个当前官方 harness 共用的 `format_search_results` 只把检索结果的
`created_at`/`updated_at` 提升到规范结果，其他 metadata 不会进入 answer 路径
（`third_party/methods/mem0-main/memory-benchmarks/benchmarks/common/mem0_client.py:448-476`）。
但三个 ingest 路径都先把数据集对话时间转换为 epoch，再作为 `timestamp` 传给
Mem0：LoCoMo 为 session date（`benchmarks/locomo/run.py:302-340`），
LongMemEval 为 haystack session date（`benchmarks/longmemeval/run.py:407-451`），
BEAM 为 batch 的首个 `time_anchor`（`benchmarks/beam/run.py:275-285,428-476`）。
因此官方 answer 侧读取的 `created_at` 承担的是上述对话时间轴，而不是 benchmark
进程启动时的实验墙钟语义。

| benchmark | search 到 answer 的实际调用点 | 是否带时间、字段与格式 |
|---|---|---|
| LoCoMo | search 后调用共享 formatter，再把 cutoff 结果送入 answer builder（`benchmarks/locomo/run.py:415-420,460-466`） | **带**。builder 按 `created_at` 排序并渲染为 `({weekday}, {Month} {DD}, {YYYY}) {memory}`；缺失时为 `(unknown date)`（`benchmarks/locomo/prompts.py:143-182`）。 |
| LongMemEval | search 后共享 formatter；answer 前再次按 `created_at` 排序（`benchmarks/longmemeval/run.py:538-549,578-593`） | **带**。builder 按 `created_at` 分组，日期标题为 `--- {weekday}, {Month} {DD}, {YYYY} ---`，其下是 `- {memory}`（`benchmarks/longmemeval/prompts.py:210-258`）。 |
| BEAM | search 后共享 formatter；answer 前按 `created_at` 排序并调用 BEAM builder（`benchmarks/beam/run.py:688-695,726-739`） | **带**。builder 截取 `created_at` 前 10 字符，渲染为 `{rank}. [{YYYY-MM-DD}] {memory}`；无时间则省略日期（`benchmarks/beam/prompts.py:104-137`）。 |

旧论文评测路径同样不是“无时间”口径：search 从
`memory["metadata"]["timestamp"]` 取时间（
`third_party/methods/mem0-main/evaluation/src/memzero/search.py:37-88`），answer
前逐项拼成 `timestamp: memory`（同文件 `:90-106`）。本次通用
`formatted_memory` 采用这个已有的 Mem0 方法级格式，并保留框架原有 `- ` bullet；
三套 native reader prompt 则继续由各 benchmark 的官方 builder 自行排版。

**硬答案：三个当前官方 benchmark 的 answer 上下文全部带时间，读取字段均为
`created_at`；该值对应 ingest 时显式传入的对话/session 时间。旧论文路径读取
metadata timestamp，并以 `timestamp: memory` 拼接。**

## 2. Phase B：实现

1. `_normalize_search_results` 现在从 search item 顶层、嵌套 `metadata`、嵌套
   `payload` 三处保留时间字段；选择顺序是 `session_time` →
   `first_turn_time` → `turn_time` → 旧 `timestamp` → `created_at`
   （`src/memory_benchmark/methods/mem0_adapter.py:1537-1613`）。这是对官方
   `created_at` 对话时间语义的本地 OSS 等价恢复；原实验墙钟另存为
   `storage_created_at`，没有静默丢弃。
2. 归一结果把选中的对话时间置于 reader 所需的 `created_at`。因此既有 LoCoMo/
   LongMemEval 官方 prompt builder 无需改动即可收到正确时间；通用
   `formatted_memory` 按旧官方 `timestamp: memory` 形式输出，有时间时为
   `- {timestamp}: {memory}`，完全无时间时仍为原来的 `- {memory}`
   （`src/memory_benchmark/methods/mem0_adapter.py:1866-1880`）。
3. `RetrievedItem.timestamp` 使用所选对话时间；item metadata 记录
   `timestamp_source`，并在存在墙钟值时记录 `storage_created_at`
   （`src/memory_benchmark/methods/mem0_adapter.py:1018-1040`）。旧记忆没有
   对话 metadata 时，显式标为 `timestamp_source=created_at`。
4. reader 上下文发生可观察变化，manifest 中的 prompt 版本由
   `mem0-memory-benchmarks-reader-v2` 升为 `mem0-memory-benchmarks-reader-v3`
   （`src/memory_benchmark/methods/mem0_adapter.py:68-71`）。

## 3. Phase C：离线测试锚

- `test_mem0_retrieve_promotes_dialogue_time_from_search_metadata`：嵌套
  `session_time` 优先于墙钟，覆盖 formatted_memory、item timestamp、来源标记和
  墙钟留存（`tests/test_mem0_adapter.py:1163-1207`）。
- `test_mem0_retrieve_falls_back_to_created_at_for_legacy_memory`：没有对话时间的
  旧记忆回退 `created_at` 且显式标记（`tests/test_mem0_adapter.py:1210-1250`）。
- `test_get_answer_uses_mem0_locomo_official_answer_prompt`：官方 LoCoMo builder
  收到对话时间，不会把实验墙钟写入 answer prompt
  （`tests/test_mem0_adapter.py:1445-1483`）。
- 既有无时间路径断言继续要求 `- Alice likes jasmine tea.`，锁住无时间文本行为
  （`tests/test_mem0_adapter.py:1396-1442`）。

## 4. 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m3mem0`
- branch：`actor/m3-mem0-timestamps`
- 修改范围：`mem0_adapter.py`、`test_mem0_adapter.py`、本 note；无偏离允许清单。
- 停工条件：未触发。三条官方 answer 路径均带时间；缺对话 metadata 时仍有
  `created_at` 明确 fallback。
- 目标测试：`uv run pytest -q tests/test_mem0_adapter.py` →
  `35 passed in 2.13s`。
- compileall：`uv run python -m compileall -q src/memory_benchmark tests` →
  退出码 0，无输出。
- commit：本 note 所在提交（最终 hash 见 `git log -1`）。

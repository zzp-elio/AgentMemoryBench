# Actor 卡 M3-mem0：formatted_memory 时间口径官方对齐（B4 修缮,取证+施工合卡）

> 派发日 2026-07-14。允许修改：`src/memory_benchmark/methods/mem0_adapter.py`、
> tests（mem0 相关）、新建 `docs/workstreams/ws02.7-method-track/notes/
> m3-mem0-timestamps.md`。禁改 third_party、禁真实 API。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m3mem0 -b actor/m3-mem0-timestamps
cd /Users/wz/Desktop/mb-actor-m3mem0 && uv sync
```
禁 push;只跑目标测试 + compileall（playbook #18）。

## 1. 问题实锤（架构师开箱验收 2026-07-14）

mem0 五格 smoke 的产物检查发现:①membench 格 formatted_memory 里的记忆
**不带任何对话时间**（对照 LightMem 的 `[Memory recorded on: 15 March
2024]`）;②`RetrievedItem.timestamp` 用的是 `created_at` = **实验墙钟时间**
（`2026-07-14T07:39:30Z`）,不是对话时间。而 add 侧 payload 里对话时间
**明明在**（qdrant payload 有 `session_time`/`first_turn_time`,架构师
开库实证）——检索规范化时被丢弃（adapter `_normalize_search_results`
只留 memory/score/created_at/id）。时间敏感型问题（locomo temporal、
lme temporal-reasoning、beam 时序）答题会因此缺时间线索。

## 2. 施工内容

### Phase A 取证（写进 note,先于施工）
官方 answer 上下文的时间口径:逐个读 memory-benchmarks 三个 run.py 的
search→answer prompt 构建段（locomo/longmemeval/beam,锚见
`notes/m1-mem0-evidence.md` §1.2 表）——官方把检索结果拼进答题上下文时
**带不带时间戳、带哪个时间（记忆时间/对话时间/created_at）、什么格式**;
另核旧论文路径 `evaluation/src/memzero/search.py:37-88`（M1 已锚"拼时间
戳上下文"）作对照。**硬答案表:每 benchmark 一行官方时间口径。**

### Phase B 施工（按 Phase A 的官方口径,不发明自己的格式）
1. `_normalize_search_results` 保留 payload 的对话时间字段（session_time/
   first_turn_time 等,以官方读取的字段为准）;
2. `_memory_context_text` / reader 上下文按官方格式带上时间;
3. `RetrievedItem.timestamp` 改用对话时间（官方无明确口径时:优先
   session_time,fallback created_at 并在 metadata 留 `timestamp_source`
   标记）;
4. reader prompt 版本号 bump（`MEM0_READER_PROMPT_VERSION`——上下文格式
   变了,口径纪律要求版本可追溯）。

### Phase C 测试
离线:注入带 session_time 的 fake 检索结果 → formatted_memory 含对话
时间、item.timestamp=对话时间;无时间字段的旧记忆 → fallback+标记;
既有非时间断言不回归。

## 3. 完成门
目标测试 + compileall 全绿（报数字）;note = Phase A 官方口径表 + 实现锚。

## 4. 停工条件
- 官方三个 run.py 的答题上下文**都不带**时间（那 B4 口径=官方无时间,
  我们不能私自加——停工交架构师裁决"无时间声明"还是"框架增强轨"）;
- payload 时间字段在部分 benchmark 缺失且无 fallback 可用。

## 施工报告（actor 填写）
（待填）

# M0-8 LightMem × HaluMem session wrapper

日期：2026-07-13  
分支：`actor/m0-8-halumem`

## 1. 框架契约

HaluMem benchmark 注册为 `TaskFamily.CONVERSATION_QA`、静态
`required_capabilities=frozenset()`，并启用 operation-level runner
（`src/memory_benchmark/benchmark_adapters/registry.py:648-663`）。LightMem 注册已声明
同一 task family，并提供 conversation add 与 retrieval
（`src/memory_benchmark/methods/registry.py:768-797`），所以静态兼容性没有缺口；本卡
只需在 factory 中将 HaluMem 实例特化为 session 消费粒度和 session report 能力。

`SessionMemoryReport` 的稳定字段是 `session_ref`、`memories: list[str]` 与公开
`metadata`（`src/memory_benchmark/core/provider_protocol.py:198-209`），能力旗是
`MemoryProvider.session_memory_report`（同文件 `:271-292`）。operation-level runner
逐 session 构造 `SessionBatch`，ingest 后立即以相同 isolation/session id 调
`end_session`（`src/memory_benchmark/runners/operation_level.py:319-364`）；report 被写为
`session_memory_reports.jsonl` 的 `memories` 列表（同文件 `:533-553`）。
`halumem-extraction` 只消费状态为 `ok` 的 report，并把 `memories` 作为本 session
候选记忆（`src/memory_benchmark/evaluators/halumem_extraction.py:46-104`）。字段与
wrapper 输出可以直接对齐，不需要修改 benchmark adapter、runner 或 evaluator。

## 2. 捕获点选型

**选择：adapter 在单次 HaluMem session 调用窗口内临时包装
`embedding_retriever.insert`，成功调用原函数后只读 payload。**

一手调用链：`add_memory` 把 extraction 结果转换为 `MemoryEntry`，offline 配置随后调
`offline_update(memory_entries)`
（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:363-386`）；offline
路径逐 entry 构造含 `memory`、时间戳及可选 `source_external_id` 的 payload，再调用
`embedding_retriever.insert`
（同文件 `:398-445`）。该点满足：

1. 只观察实际成功进入向量库的 session 新条目，不修改参数、返回值、抽取 prompt、
   分段、存储或排序；
2. 包装窗口由一次 `SessionBatch` ingest 明确界定，不需要全库前后 diff，也不会把前一
   session 的旧条目收入当前 report；
3. 捕获为空时返回真实空列表并在 metadata 标记，不从 gold 或检索结果补造。

备选“写后查询 Qdrant 增量”侵入更深：需要额外读取全库并自行判定新旧边界，而 insert
旁听已有天然调用窗口。HaluMem 官方 Memobase wrapper 同样逐 session 写入，每批显式
`flush(sync=True)`，随后按本次开始时间查询底层 DB 增量
（`third_party/benchmarks/HaluMem-main/eval/eval_memobase.py:150-174,241-269`）；官方
README 也明确说明其直接访问底层数据库是 API 缺口 workaround
（`third_party/benchmarks/HaluMem-main/eval/README.md:128-141`）。本 wrapper 的只读旁听
没有改变 method 内部数据。

## 3. HaluMem session 边界

HaluMem adapter 逐原始 session 生成公开 `Session`，session id 来自官方字段或稳定
`s<index>` fallback；turn id 为 `{session_id}:t{1-based-index}`
（`src/memory_benchmark/benchmark_adapters/halumem.py:312-402,415-437`）。事件聚合器把
同 session events 组成一个 `SessionBatch`，保留 isolation key、session id、events 与
session time（`src/memory_benchmark/runners/event_stream.py:156-162,237-251`）。因此
LightMem 的捕获 key 直接使用 `(SessionBatch.isolation_key, SessionBatch.session_id)`，
与 runner 发给 `end_session(SessionRef)` 的边界逐字段一致。

## 4. 实现与测试

### 4.1 实现

- `LightMem` 新增实例级 `session_memory_report` 开关与按
  `(isolation_key, session_id)` 保存的待报告记忆；默认关闭，所以其他 benchmark
  实例行为不变（`src/memory_benchmark/methods/lightmem_adapter.py:304-366`）。
- HaluMem 的 `SessionBatch` 走独立路径：完整 session messages 一次传给
  `add_memory`，并显式设置 `force_segment=True, force_extract=True`
  （同文件 `:540-589`）。消息继续用公开 turn id 作 `external_id`。
- insert observer 先调用真实 insert，只有成功后才读取 payload 的非空 `memory`；
  `finally` 精确恢复/删除实例级包装，不改变后续检索和写入
  （同文件 `:591-634`）。
- `end_session` 只在能力启用时返回 report；空捕获也返回 `memories=[]`，metadata
  明确 `capture_status=empty` 与计数 0，不补造内容（同文件 `:636-656`）。
- LightMem factory 仅在 `benchmark_name == "halumem"` 时设置 session 粒度与
  report 能力；LongMemEval 仍为 pair，其余仍为 turn
  （`src/memory_benchmark/methods/registry.py:369-393`）。静态 method registration
  无需改变。

### 4.2 离线契约锁

- `test_lightmem_halumem_session_reports_are_incremental_and_force_flushed`：两个 session
  连跑，断言每次整批 force、公开 external ids 保留、第二份 report 不含第一份
  memory，并验证 observer 无残留（`tests/test_lightmem_adapter.py:1659-1766`）。
- `test_lightmem_halumem_empty_capture_is_reported_without_fabrication`：无 insert 时返回
  空列表与显式留痕（同文件 `:1769-1822`）。
- `test_lightmem_end_session_is_inactive_outside_halumem`：默认实例保持 None
  （同文件 `:1825-1843`）。
- `test_lightmem_registry_specializes_consume_granularity_by_benchmark`：锁定
  turn/pair/session 三种实例特化、能力旗和 `validate_compatibility` 通过
  （同文件 `:1846-1923`）。

## 5. 语义代价

逐 session 强制 `force_segment=True, force_extract=True` 会改变 LightMem 原生跨 session
自然缓冲与分段节奏；这是 HaluMem extraction 协议为取得 session 增量候选所需的适配，
不是 LightMem 原生默认节奏。官方六个 wrapper 均按 session 注入，Memobase 还采用强制
flush 后事后增量收集；公平性依据成立，但实验报告仍必须声明该差异。该声明已存在于
`docs/reference/integration/lightmem.md:170-199`，本卡不越过允许文件清单重复修改。

## 6. 五件套 smoke 命令建议

以下命令仅为用户后续显式批准真实 API 后执行的建议，本卡未运行。HaluMem smoke 是
固定形状，故不传通用裁剪旋钮；operation-level runner 要求一个 worker。

```bash
uv run memory-benchmark predict smoke \
  --method lightmem \
  --benchmark halumem \
  --variant medium \
  --run-id lightmem-halumem-medium-smoke \
  --allow-api \
  --workers 1

uv run memory-benchmark evaluate \
  --run-id lightmem-halumem-medium-smoke \
  --metric halumem-extraction \
  --allow-api

uv run memory-benchmark evaluate \
  --run-id lightmem-halumem-medium-smoke \
  --metric halumem-update \
  --allow-api

uv run memory-benchmark evaluate \
  --run-id lightmem-halumem-medium-smoke \
  --metric halumem-qa \
  --allow-api

uv run memory-benchmark evaluate \
  --run-id lightmem-halumem-medium-smoke \
  --metric halumem-memory-type
```

前三个 evaluator 含 judge，属于付费 API；`halumem-memory-type` 只读取已生成的
extraction/update score artifacts，免费但必须最后运行。

## 施工报告

- 串行门：M0-9 commit `9ca97d3` 已是 main `78c933f` 的 ancestor，开工条件满足。
- worktree：`/Users/wz/Desktop/mb-actor-m08`，分支 `actor/m0-8-halumem`。
- 修改范围：LightMem adapter、LightMem factory、LightMem 测试与本 note；未改
  third_party、HaluMem benchmark adapter/evaluator 或其他 method/runner。
- 目标测试：`uv run pytest -q tests/test_lightmem_adapter.py` →
  `48 passed, 1 warning in 30.06s`。
- 编译检查：`uv run python -m compileall -q src/memory_benchmark tests` → 退出码 0，
  无输出。
- 真实 API：零调用。
- 已知文档差异：`docs/reference/integration/lightmem.md:170-199` 仍称静态
  `task_families` 是注册缺口；现场代码证明 HaluMem 与 LightMem 均已是
  `CONVERSATION_QA` 且 benchmark required capabilities 为空，实际缺口只有 factory
  实例特化。该实例文档不在本卡允许修改清单内，故只在此留档，交架构师验收时修订。
- 偏离/停工点：无。

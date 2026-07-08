---
id: ws02.5
doc: plan（MemoryOS eval→pypi 迁移，写任务，串行占据）
status: ready（待 actor 施工）
created: 2026-07-08
author: Claude Opus 4.8（架构师，第一手调研）
---
# MemoryOS eval/ → memoryos-pypi 迁移 plan

依据（**每条回一手源，架构师 2026-07-08 已第一手核实**）：
`third_party/methods/MemoryOS-main/memoryos-pypi/memoryos.py`（迁移目标引擎）、
`.../eval/`（现 adapter 所包的 LoCoMo 主场副本，要迁走）、现 adapter
`src/memory_benchmark/methods/memoryos_adapter.py`。版本裁定见
[README.md](README.md)"MemoryOS 版本裁定"（用 pypi，不用 mcp/chromadb/eval）。

## 架构师第一手已定（施工蓝图，施工前必读）

### 1. 迁移目标 = pypi `Memoryos`（文件式、按 user_id 目录隔离）

- 构造：`Memoryos(user_id, assistant_id, data_storage_path,
  short_term_capacity=10, mid_term_capacity=2000, long_term_knowledge_capacity=100,
  retrieval_queue_capacity=7, ...)`（`memoryos.py:30-40`）。
- 存储：`data_storage_path/users/<user_id>/{short_term.json, mid_term.json,
  long_term_user.json}` + `assistants/<assistant_id>/long_term_assistant.json`
  （`memoryos.py:71-84`）。**天然文件式物理隔离** → 每 conversation 一个
  `data_storage_path`（或 user_id），clean-retry = 删目录。
- **引擎与 eval/ 是同算法的"更成熟产品版"**（第一手行数对比：short_term
  eval 44 vs pypi 66、mid_term 270 vs 393、long_term 133 vs 172）——pypi 是
  README 说的"5x 加速+并行"版。迁移**会改变数值 vs 旧 LoCoMo eval/ 跑**，这是
  **对的**（我们要产品版、要跨 benchmark 公平），不是 bug。

### 2. 注入 = `add_memory(user_input, agent_response, timestamp)`（pair 粒度）

- `memoryos.py:226`，一次一个 user-agent 交换对。→ adapter
  `consume_granularity="pair"`。
- **⚠ 注意：`add_memory` 会触发 LLM 调用**（mid-term 分析 + profile/knowledge
  抽取，`memoryos.py:126 _trigger_profile_and_knowledge_update_if_needed` +
  异步任务 154/164）。即 **MemoryOS 注入是 LLM-heavy 的**——真实 smoke 有 API
  成本；fake 全链路测试须 stub 掉 LLM client。
- orphan/dangling（assistant 开头 / 连续同 role，见 event_stream `_aggregate_pairs`）：
  MemoryOS `add_memory` 要 user+agent 两侧。**裁定**：dangling user（无 agent）
  → `add_memory(user_input=user, agent_response="")`；orphan assistant（无 user）
  → `add_memory(user_input="", agent_response=assistant)`。都注入不丢，空侧留空串。
  （actor 施工时核对 add_memory 对空串的容错，若崩则停工上报。）

### 3. 检索 = **从 get_response 剥离出纯检索**（护栏 A：MemoryOS retrieve 与答题耦合）

pypi **无独立公开 retrieve**；检索埋在 `get_response`（`memoryos.py:252-348`）里。
第一手拆解——步骤 1-7 是纯检索+组装，步骤 8-9 是答题（跳过），**步骤 10
`add_memory` 是写副作用（:346，必须跳过）**：

- 步骤1（:259）`self.retriever.retrieve_context(user_query, user_id)` →
  `retrieved_pages`(中期) + `retrieved_user_knowledge` + `retrieved_assistant_knowledge`。
- 步骤2（:269）`self.short_term_memory.get_all()` → 短期 history。
- 步骤4（:282）`self.user_long_term_memory.get_raw_user_profile(user_id)` → 长期 profile。
- 步骤3/5/6（:275-302）把中期页 / user_knowledge / assistant_knowledge 组装成文本。

**剥离方案**：adapter 新增 `retrieve` 内部**复刻步骤 1-7**，把
短期 history + 中期 retrieved_pages + 长期 profile + user_knowledge +
assistant_knowledge **全部组装成 `formatted_memory`**（沿用官方 :270-302 的拼装
文本，保证忠实），然后**停在步骤 7**：不调步骤 8-9 的 LLM、**不做步骤 10 的
add_memory**。这样 formatted_memory **覆盖短/中/长全部记忆层**（满足 ws02.5(c)
完整性）。

- **不污染契约（更正版，见 T3 ⚠）**：retrieve 只锁"不写新内容污染"——不调
  step-10 `add_memory`、short_term 条目/profile/knowledge 内容不变。**但检索
  固有的 mid_term heat/`N_visit` 更新必须保留**（算法机制，作者 eval:236-237
  就这么做），**不要**照搬 HaluMem update 探针的"状态全不变"。

### 4. 参数 = pypi 官方默认

现 eval/ adapter 用 LoCoMo 调优参数（short_term_capacity=7 等，见现 adapter
`MEMORYOS_PYPI_GENERIC_READER_PROMPT_VERSION` 附近配置）。**裁定**：迁移改用
**pypi 官方默认**（short_term_capacity=10/mid_term_capacity=2000 等），符合
ws02.5"用产品默认"公平原则；profile 里标注"用 pypi 官方默认，与旧 LoCoMo 调参
不同"。

### 5. 答题 = 框架 unified answer prompt

retrieve 返回 formatted_memory → framework reader 用 benchmark 的 unified answer
prompt 答题（主线口径），**不**用 MemoryOS 的 get_response 答题。

## Task 分解

### T1 引擎切换 + 每 conversation 物理隔离
改动：`memoryos_adapter.py` 把实例化从 eval/ 引擎改为
`memoryos-pypi` 的 `Memoryos`；`data_storage_path` 每 conversation 独立目录
（复用现有隔离键派生）；cleanup/clean-retry = 删该目录。vendored 覆盖清单更新
（不再需要 eval/*.py，改覆盖 memoryos-pypi/*.py）。
验收：focused 测试建 2 个 conversation 实例、状态互不串；删目录后重建干净。

### T2 注入 via add_memory（pair）
改动：ingest 把 TurnEvent pair → `add_memory(user, agent, timestamp)`；
consume_granularity="pair"；orphan/dangling 按上方裁定注入不丢。LLM client 走
本项目注入（不用官方硬编码 key），fake 测试 stub。
验收：focused 测试 ingest 一段对话后 short/mid/long 文件有内容；orphan/dangling
用例不崩。

### T3 剥离纯检索 → formatted_memory 全层 + 无写副作用（核心）
改动：新 `retrieve` 复刻 get_response 步骤1-7，组装短+中+长+knowledge 成
formatted_memory，跳过答题与 add_memory。
验收：focused 测试 ①formatted_memory 含短/中/长各层内容（给构造好的记忆状态，
断言各层都出现）②**不污染记忆内容**（retrieve 未调 step-10 `add_memory`、
short_term 条目/profile/knowledge 内容前后不变）③非空。
**⚠ 架构师更正（2026-07-08，用户点破 + eval 第一手证实）**：这里**不能**要求
"retrieve 前后记忆状态/文件完全不变"——那是**过度套用** HaluMem update 探针。
MemoryOS 检索**固有地**更新 mid_term 的 `N_visit`/`last_visit_time`/heat 并
save（驱动中→长晋升），这是**算法机制**：作者自己的 eval `search_sessions_by_
summary`（`eval/mid_term_memory.py:236-237` `N_visit+=1`、`last_visit_time=now`、
`:265 rebuild_heap`）就这么做。**必须保留**这个 heat 变化（压掉就不是 MemoryOS）。
契约只锁"不写新内容污染"（step-10 add_memory + short/profile/knowledge 内容），
mid_term 访问统计/heat 变化如实发生、不断言。

### T4 参数改 pypi 官方默认 + 清理 eval/ 残留
改动：配置改 pypi 默认；删 eval/-specific 逻辑/import；profile 标注差异。
验收：无 eval/ 依赖残留（grep 无 `eval/` import）。

### T5 测试 + registered fake 全链路
改动：`test_memoryos_adapter.py` 全面改（fake LLM client 离线）；registered fake
链路 MemoryOS × benchmark 端到端；resume。
验收：focused 全绿；`uv run pytest -q -m "not api"` **≥892 不跌破**；compileall。

### T6 收尾
改动：ws02.5 README 断点 + 任务清单 P1 MemoryOS 勾选；接口文档 MemoryOS 节
（注入 add_memory + 检索剥离口径 + 全层 formatted_memory + pypi 默认参数）。
验收：git status 干净；交架构师复跑 + 第一手核对（重点核 T3 剥离是否全层 +
无写副作用、T1 隔离）。

## 风险与红线
- **MemoryOS 注入 LLM-heavy**：真实 smoke 成本高于纯向量 method；fake 测试必须
  stub LLM。成本表要单列。
- **剥离必须全层**：漏任何一层（如漏长期 profile）= 记忆不完整 = 数字失真。
  T3 验收重点。
- **retrieve 零写副作用**：绝不触发步骤 10 的 add_memory。
- 不改 `third_party/`；数值 vs 旧 eval/ 跑变化是预期（产品版），不是回归。
- 遇 plan 未覆盖的一手缺口（如 add_memory 不容空串、retrieve_context 签名有别）
  → 停工上报，别硬编。

# M1 Mem0 接入取证

> 日期：2026-07-14。范围：只补 `docs/reference/integration/mem0.md` 尚未正式
> 验收的 B1/B2/B3/B5/B6/B9 与 HaluMem 能力证据；不重复流水线已经付清的
> runner、provenance evaluator、smoke/resume 等通用资产。本卡未调用真实 API。
>
> vendored `third_party/methods/mem0-main/` 没有嵌套 `.git`，因此上游 commit
> **来源待溯**；框架现有 source identity 以 package version、源码文件列表和
> 聚合 SHA-256 锁内容，且明确不把嵌套 `memory-benchmarks` 整体纳入身份
> （`src/memory_benchmark/methods/mem0_adapter.py:203-217,225-271`）。官方 repo
> URL 可由根 README 的 GitHub 链接核实（`third_party/methods/mem0-main/README.md:1-4`），
> 根 LICENSE 是 Apache-2.0（`third_party/methods/mem0-main/LICENSE:1-5`）。

## 1. B1 来源与 native 注册面

### 1.1 仓库实际提供的 benchmark

当前官方复现入口是 vendored `memory-benchmarks`：README 明列 LoCoMo、
LongMemEval、BEAM 三项（`third_party/methods/mem0-main/memory-benchmarks/README.md:5-12`），
并分别给出 CLI（同文件 `:30-48,64-75`）。根 README 也把这套框架链接为当前
可复现入口，并报告三家的新算法结果（`third_party/methods/mem0-main/README.md:45-69`）。

旧 `evaluation/` 是论文期 LoCoMo 专用复现：README 明说只在 LoCoMo 数据集上
比较各技术（`third_party/methods/mem0-main/evaluation/README.md:8-20`），其
`run_experiments.py` 仅把 `dataset/locomo10.json` 分派给 Mem0 add/search
（`third_party/methods/mem0-main/evaluation/run_experiments.py:39-49`）。它是历史
证据，不额外扩张当前 native 格。

**硬答案：native 注册面 = LoCoMo、LongMemEval、BEAM；MemBench、HaluMem 在
Mem0 仓库中没有复现脚本，因此无 native 格。**

### 1.2 三个当前复现脚本的调用序列

| benchmark | 复现脚本与 ingest | search / answer / judge |
|---|---|---|
| LoCoMo | `memory-benchmarks/benchmarks/locomo/run.py`；官方设 `CHUNK_SIZE=1`，把 session turn 转为单 turn chunk（`:88,165-190`），逐 chunk `mem0.add(..., timestamp=...)`（`:302-340`） | 每题先 `mem0.search`（`:389-420`），再 answerer（`:460-468`）和 structured judge（`:470-487`）；外层明确先 ingest 再逐题处理（`:859-875,893-930`） |
| LongMemEval | `memory-benchmarks/benchmarks/longmemeval/run.py`；`CHUNK_SIZE=2`，按原位置两 turn 一 pair（`:96,314-324`），逐 pair `mem0.add`（`:407-451`） | 外层先 `ingest_question`（`:1272-1310`），随后按 mode search + answer/judge 或 retrieval judge（`:1317-1350`） |
| BEAM | `memory-benchmarks/benchmarks/beam/run.py`；`CHUNK_SIZE=2`（`:89`），标准化 role/content 后每两 turn 一 chunk（`:255-272`），逐 chunk `mem0.add`（`:428-476`） | Phase 1 先 ingest（`:1092-1105`），Phase 2 枚举问题（`:1111-1142`）并执行 search + answer + rubric judge（`:1164-1188`；题内调用链见 `:688-757`） |

旧论文 LoCoMo 路径则是两个独立命令：add 侧先按两个 speaker namespace 删除，
再把每个 session 的消息按默认 batch size 2 写入（
`third_party/methods/mem0-main/evaluation/src/memzero/add.py:45-70,80-95,97-130`）；
search 侧分别检索两个 speaker、拼时间戳上下文、调用 answer model
（`third_party/methods/mem0-main/evaluation/src/memzero/search.py:37-88,90-127`）。

## 2. B2 注入粒度

### 2.1 框架现状

Mem0 provider 类默认声明 `consume_granularity="turn"`，provenance 仍为
`none`（`src/memory_benchmark/methods/mem0_adapter.py:275-292`）。注册 factory
按 benchmark 实例级特化：LongMemEval、HaluMem 使用 `session`，其余使用
`turn`，且只在 HaluMem 打开 session report（
`src/memory_benchmark/methods/registry.py:165-188`）。

实际消息构建点如下：

- turn 路径把一个 `TurnEvent` 转成单消息，并用 `run_id=isolation_key` 调一次
  `Memory.add`（`src/memory_benchmark/methods/mem0_adapter.py:465-499`）。旧
  conversation 路径同样逐 turn 调 add（同文件 `:772-790`）。
- session 路径并不是整 session 一次 add，而是在 session 内按位置每 2 turn
  切 chunk，逐 chunk add（同文件 `:531-573`）。LongMemEval 旧 conversation
  路径也按 2 turn chunk（同文件 `:804-844`）。

### 2.2 与官方喂法对照

| benchmark / 路径 | 官方粒度 | 当前 adapter | 结论 |
|---|---|---|---|
| LoCoMo 当前 harness | 每次 1 turn（官方 `run.py:88,165-190,340`） | turn，每次 1 turn（adapter `:482-499,772-790`） | 一致 |
| LongMemEval 当前 harness | session 内每次 2 turn（官方 `run.py:96,314-324,407-451`） | provider 对 runner 声明 session，但内部每 2 turn 一次 add（adapter `:531-573`） | add 调用序列一致；声明 session 是为了保持 batch 边界，不代表整 session 单调用 |
| BEAM 当前 harness | 每次 2 turn（官方 `run.py:89,255-272,428-476`） | factory 对 BEAM 选 turn，逐 turn add（registry `:182-186`；adapter `:482-499`） | **不一致：官方 pair，框架 turn** |
| HaluMem 官方 wrapper | 每个 session 的完整 `dialogue` 构成一个 message list，一次 add（`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:168-194`） | runner 给 SessionBatch，但 adapter 再切成 2-turn add（adapter `:531-573`） | **不一致：官方整 session，框架 pair** |
| MemBench | Mem0 官方仓库无脚本（§1） | turn | 无官方姿态，按流水线轻姿态预判 |

HaluMem 指定源码位于 gitignored benchmark 快照，独立 worktree 不含该目录；上述
行号是在主树同一路径只读现场核实，未复制或修改资产。

**硬答案：当前 LoCoMo 与 LongMemEval 的 add 调用粒度对齐；BEAM 应从 turn
改为官方 2-turn chunk；HaluMem 虽能产 session report，但 add 调用仍需改为整
session 一次。** 这两项属于下一张施工卡，不在本卡修改。

## 3. B3 逻辑隔离等价性

### 3.1 写入分区与“清得干净”

adapter 把公开 conversation/isolation key 作为 Mem0 `run_id` 写入
（`src/memory_benchmark/methods/mem0_adapter.py:482-499,531-568,772-789`），
本地 backend 使用同一 adapter storage root 下的 Qdrant collection `mem0` 和
history DB（同文件 `:360-410`）。Mem0 官方 `_build_filters_and_metadata` 会把
`run_id` 同时写入 payload metadata 和查询 filter（
`third_party/methods/mem0-main/mem0/memory/main.py:276-314`），批量持久化时完整
payload 随 vector 入库（同文件 `:807-834`）。

官方有按 namespace 清理向量的同步 API：`delete_all(..., run_id=...)` 构造 filter，
只列出该 filter 的记忆并逐条删除（同文件 `:1540-1571`）；Qdrant `list` 把 filter
传入 `scroll_filter`（`third_party/methods/mem0-main/mem0/vector_stores/qdrant.py:531-550`）。
但这**不等价于物理清空 namespace**：逐条 `_delete_memory` 会新增 DELETE history
记录（official main `:1722-1748`），而 history schema 本身没有 run/session scope
字段（`third_party/methods/mem0-main/mem0/memory/storage.py:102-121,150-190`）。更关键的
是 add 会读取该 scope 最近 10 条 messages，并在结束时保存 messages
（official main `:699-714,957-971`）；`messages` 表按 `session_scope` 存储，但
SQLiteManager 只有 save/get/reset，没有单 scope delete
（`third_party/methods/mem0-main/mem0/memory/storage.py:128-147,257-327`）。
`delete_all(run_id=...)` 没有清理这些 messages。因此失败后以同一个 run_id 重试，
提取 prompt 仍可能读到失败尝试留下的最近消息，**“清得干净”判据不通过**。

但框架注册没有把它挂为 failed-ingest clean hook：Mem0 registration 到
`supports_shared_instance_parallelism=False` 即结束（
`src/memory_benchmark/methods/registry.py:745-774`）。对照 A-Mem、LightMem、
MemoryOS、SimpleMem 的 hook 函数均已存在（同文件 `:566-615`），注册挂点分别是
`:743,804,835,866`。

**结论（清理）：证据 = 官方 `delete_all(run_id=...)` 只能清 vector/entity 引用，
不能清该 scope 的 recent messages，history 也只追加 tombstone；gap = 底层没有公开的
单 scope 完整 reset，框架也未挂 clean hook；建议动作 = 不可只接 `delete_all` 冒充
等价清理。架构师应在“每 conversation 物理 state”与“批准最小 third-party
`delete_messages(session_scope)` + 明确 history 保留不影响算法”之间裁决。**

### 3.2 检索过滤与“漏不出去”

adapter 两条检索路径都强制传 `filters={"run_id": conversation/isolation_key}`
（`src/memory_benchmark/methods/mem0_adapter.py:886-896,933-976`）。官方 search
要求 filter 至少含 `user_id/agent_id/run_id` 之一，并把有效 filter 原样交给
vector search（`third_party/methods/mem0-main/mem0/memory/main.py:1173-1227`）。
Qdrant 简单标量 filter 转为 `MatchValue`（
`third_party/methods/mem0-main/mem0/vector_stores/qdrant.py:224-248`），并作为
`query_filter` 传入 query（同文件 `:374-394`）。

现有离线测试 `test_shared_mem0_instance_keeps_two_concurrent_conversations_isolated`
确实断言两个 namespace 不互见，但 backend 是 `NamespacedFakeMemoryBackend`
（`tests/test_mem0_adapter.py:1268-1298`），不是生产 Qdrant。另有生产 OSS
`test_mem0_locomo_two_conversation_concurrent_api_smoke`（
`tests/test_mem0_locomo_api.py:96-152`），但整个文件被标为 api/expensive/integration
（同文件 `:1-5,30-35`），不是零成本回归网。

**结论（泄漏）：证据 = adapter→Mem0→Qdrant 的 run_id filter 链闭合，fake 单测
也锁了期望语义；gap = 没有零 API、生产 Qdrant backend 的跨 namespace 泄漏测试；
建议动作 = 用本地 fake embedding + `infer=False` 或直接预置生产 Qdrant payload，
补真实 filter 层的双 namespace 检索断言。**

### 3.3 多 worker 与“并行不打架”

当前正式注册明确 `supports_shared_instance_parallelism=False`
（`src/memory_benchmark/methods/registry.py:773`）。因此多 worker runner 为每个 worker
创建独立 `method_state/worker_<idx>` storage root（
`src/memory_benchmark/runners/prediction.py:1474-1504`），每个 worker 自建 system，
并在自己分到的 conversations 上串行处理（同文件 `:1681-1713`）。Mem0 adapter
又把 Qdrant path 定为传入 root 下的 `qdrant/`（
`src/memory_benchmark/methods/mem0_adapter.py:402-410`）。

所以正式多 worker 路径**不共享本地 Qdrant**：worker 间是物理隔离；只有同一
worker 内的多个 conversation 共用 collection，并靠 run_id 逻辑隔离。vendored
Qdrant wrapper 以本地 `path` 构造单个 `QdrantClient`（
`third_party/methods/mem0-main/mem0/vector_stores/qdrant.py:29-76`），代码没有给出
“多个独立 client/process 同写同一路径”的安全保证；当前 runner 也没有这么做。

**结论（并行）：证据 = 现行 registered runner 通过 worker 独立目录规避共享
store 竞态；gap = 共享实例/共享本地 Qdrant 的生产并发安全未被零 API 证明；建议
动作 = 保持 `supports_shared_instance_parallelism=False`，不要把现状宣称为纯逻辑
隔离并行。**

### 3.4 给架构师的 B3 总裁决输入

| 等价项 | 证据 | gap | 建议 |
|---|---|---|---|
| 清得干净 | `delete_all(run_id=...)` 可删向量/实体引用（official main `:1540-1571,1722-1748`） | recent messages 未清，重试会进入提取上下文（official main `:699-714`；storage `:257-327`）；registry 也无 hook | **不通过**；不能只挂 delete_all，须架构裁决物理 per-conversation 或最小存储 API |
| 漏不出去 | filter 链闭合（adapter `:886-896,966-976`；official main `:1173-1227`；Qdrant `:374-394`） | 生产 backend 零 API 跨 namespace 测试缺失 | 补本地 Qdrant filter 测试 |
| 并行不打架 | runner 给 worker 独立 root（prediction `:1474-1504`） | 这证明的是物理隔离，不是共享 store 安全 | 继续物理兜底，暂不开放共享实例 |

**总建议：B3 按不合格处理：worker 间虽有物理兜底，但 worker 内 failed-ingest
无法按 namespace 完整清理，纯逻辑隔离等价性明确失败。** 在架构师裁定新的 state
布局或单 scope messages 清理前，不能把 Mem0 登记为逻辑隔离已通过。这比现有实例
文档“唯一逻辑隔离”的预填说法更精确，但不否定 adapter 确实使用 run_id namespace
的事实。

## 4. B5 provenance 改造落点

Mem0 原生 id 链是闭合的：

1. add 的 infer=False 路径由 `_create_memory` 生成 UUID，并在返回项写
   `{"id", "memory", "event", ...}`（
   `third_party/methods/mem0-main/mem0/memory/main.py:663-697,1586-1616`）。
2. 正常 infer=True 批处理也生成 UUID（同文件 `:792-818`），持久化后返回
   `{"id": r[0], "memory": r[1], "event": "ADD"}`（同文件 `:824-834,957-971`）。
3. search 格式化时把 vector id 放进 `MemoryItem.id`（同文件 `:1381-1424`），
   因而检索结果带同一个原生 id。

当前 adapter 恰在两端丢失它：`_normalize_search_results` 只保留 memory/score/
created_at（`src/memory_benchmark/methods/mem0_adapter.py:1500-1525`），随后
`RetrievedItem.item_id` 使用不稳定的 `mem0:<rank index>`，且没有
`source_turn_ids`（同文件 `:990-1004`）。写入侧 turn/pair metadata 已分别带
公开 `turn_id` 或 `turn_ids`（同文件 `:1378-1423`），但 add 返回值目前未用于
provenance；session report 只抽 memory 文本（同文件 `:1527-1543`）。

**硬答案：策略② sidecar 可无损落在 adapter。** 最小路径为：

- 每次 add 返回后，读取 `results[*].id`，映射到该调用已知的公开 `turn_id` 或
  `turn_ids`；单 turn 精确到 turn，pair/session chunk 如实保存该 chunk 的全部 turn id。
- 将 `memory_id -> tuple[public_turn_id, ...]` 写入 `storage_root` 下持久 sidecar；
  resume 时加载，旧 state 无 sidecar 必须 fail-fast，不能静默把 provenance 说成 turn。
- search normalization 保留官方 `id`；RetrievedItem 用官方 id 作为 `item_id`，
  从 sidecar 填 `source_turn_ids`，再把 provider/registration provenance 改成 turn。
- 未命中 sidecar 的旧记忆逐项回落无来源并留计数；不能用 rank index 伪造来源。

这与既有预判一致：MemoryData survey 指定 Mem0 使用“原生 id 映射 sidecar”，并要求
持久化和旧 state fail-fast（
`docs/workstreams/ws02.7-method-track/notes/memorydata-recall-retrofit-survey.md:20-32,64`）。

## 5. B6 flush / update 姿态

Mem0 `Memory.add` 是同步建立即返回：入口调用 `_add_to_vector_store` 后直接返回
`{"results": ...}`（`third_party/methods/mem0-main/mem0/memory/main.py:650-660`）；
正常 infer 流程在返回前已完成 vector insert、history、entity linking、message save
（同文件 `:824-971`）。官方接口没有 LightMem 式 `offline_update/finalize` 阶段。

| benchmark | 官方调用点证据 | 预判姿态 |
|---|---|---|
| LoCoMo | ingest 后直接逐题 search（official `locomo/run.py:859-875,893-930`） | 不跑 post-build；add 后直接 retrieve |
| LongMemEval | `ingest_question` 后立即进入 search + answer/judge（official `longmemeval/run.py:1292-1350`） | 不跑 post-build |
| BEAM | Phase 1 ingest 后直接 Phase 2 questions（official `beam/run.py:1092-1112,1164-1188`） | 不跑 post-build |
| HaluMem | 每 session add 后立即用结果做 extraction，并开始 update search（`third_party/benchmarks/HaluMem-main/eval/eval_memzero.py:168-215`） | 不跑 post-build；保持 session 边界报告 |
| MemBench | Mem0 官方仓库无复现脚本（§1） | 无官方姿态，采轻姿态：只 add/retrieve |

**硬答案：五格均不应新增 flush/finalize；需要修的是 B2 add 分组，不是新增整理
阶段。**

## 6. B9 模型口径

### 6.1 当前 native 三格

当前 LoCoMo、LongMemEval、BEAM 三个脚本的 answerer/judge CLI 默认均为 `gpt-5`
（分别为 `memory-benchmarks/benchmarks/locomo/run.py:677-689`、
`longmemeval/run.py:934-972`、`beam/run.py:894-929`）。三者都把该参数直接传给
`LLMClient`（LoCoMo `run.py:757-759`；LongMemEval `run.py:1115-1120`；BEAM
`run.py:1030-1035`）。

`LLMClient.generate` 与 `generate_structured` 的默认参数是 temperature=0、
max_tokens=4096（`memory-benchmarks/benchmarks/common/llm_client.py:136-156,225-250`），
但 gpt-5 实际调用会**省略 temperature**并改传 `max_completion_tokens=4096`
（同文件 `:71-83,158-174,265-276`）。LongMemEval yes/no judge 也走同一 generate
入口（同文件 `:366-369`）。因此不能把 gpt-5 的实际 temperature 记成 0；它使用
API 默认温度。

当前 OSS memory build 默认另有一套模型：README 指定 extraction=`gpt-4o-mini`、
embedding=`text-embedding-3-small`（`memory-benchmarks/README.md:51-77,121-124`），
示例 config 把 extraction temperature 设为 0.1（
`memory-benchmarks/configs/openai.yaml:5-16`）。这是 method 内部 build 模型，不是
answer/judge。

### 6.2 旧论文 LoCoMo 复现

旧 paper evaluation README 建议 `MODEL="gpt-4o-mini"`、embedding
`text-embedding-3-small`（`third_party/methods/mem0-main/evaluation/README.md:56-70`）。
answer 调用读取 `MODEL` 且 temperature=0.0（
`third_party/methods/mem0-main/evaluation/src/memzero/search.py:101-115`）；judge
代码固定 `gpt-4o-mini`、JSON response、temperature=0.0，未显式设置 max tokens
（`third_party/methods/mem0-main/evaluation/metrics/llm_judge.py:39-55`）。

**硬答案：当前 native 三格的 answer/judge 不是 gpt-4o-mini，而是 gpt-5；按
流水线“非 4o-mini 官方结果第一阶段不校准”规则，第一阶段不复现当前 harness 的
论文/榜单数字。旧论文 LoCoMo 代码确实是 gpt-4o-mini，但它是历史复现面，不扩大
当前 native 注册面。** 框架统一 gpt-4o-mini 的主线保持不变；native 模型差异只
在后续一次性校准阶段声明。

## 7. HaluMem 能力现状

框架协议的 `SessionMemoryReport` 要求 `session_ref`、`memories` 与公开 metadata，
provider 以 `session_memory_report` 布尔旗声明，并在 `end_session` 返回报告
（`src/memory_benchmark/core/provider_protocol.py:198-209,271-292`）。Mem0 已实现：
session ingest 时按 `(isolation_key, session_id)` 建增量窗口，把每个 add 返回的
memory 文本累积起来，`end_session` pop 后返回报告（
`src/memory_benchmark/methods/mem0_adapter.py:531-591`）。

factory 在 HaluMem 下同时选 session granularity 和打开能力旗
（`src/memory_benchmark/methods/registry.py:165-188`）。benchmark 侧 HaluMem
登记为 `operation_level=True`，required capabilities 当前为空
（`src/memory_benchmark/benchmark_adapters/registry.py:648-663`）；method 侧仍是
`TaskFamily.CONVERSATION_QA` + add/retrieval，恰能通过当前 compatibility 模型
（`src/memory_benchmark/methods/registry.py:745-773`；task family/capability 枚举
本身没有 session-report 项，见 `src/memory_benchmark/core/capabilities.py:10-22`）。

**硬答案：离 `SessionMemoryReport` 功能契约本身没有缺口，能力旗、factory 特化、
end_session 增量 pop 都已存在，registry 也能接入 HaluMem。** 最小剩余差距只有：

1. **官方喂法差距**：当前 session 内每 2 turn add，官方是整 session 一次 add
   （§2；adapter `:531-573` 对比 HaluMem `eval_memzero.py:168-194`）。
2. **声明面表达力缺口**：静态 `MethodCapability` 没有 session report 枚举，当前
   只靠实例旗和 HaluMem `required_capabilities=frozenset()`；这不阻塞运行，但 registry
   无法在 build 前静态拒绝不支持 report 的 method（capabilities `:16-22`；benchmark
   registry `:648-663`）。是否扩枚举属于架构师协议裁决，不在 Mem0 adapter 卡自行改。

## 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m1mem0`
- branch：`actor/m1-mem0-evidence`
- 实际改动：只新增本文件。
- 测试：纯文档卡，按任务要求未运行 pytest/compileall；未调用真实 API。
- 停工点：无。Mem0 核心、旧 evaluation 和当前 memory-benchmarks 均存在；HaluMem
  指定快照仅在主树 gitignored 资产中存在，已只读核实指定调用点并在 §2 说明。
- 与既有实例文档的差异：不是 adapter 重大矛盾；实例文档本就把 clean-retry 标为
  gap。本卡进一步找到严格反证：`delete_all(run_id)` 不清会参与后续提取的 recent
  messages，因此 B3 清理项应判不通过；并把并行形态细化为“worker 内逻辑、worker
  间物理”。两项均交架构师裁决后再更新实例文档。

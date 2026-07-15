# Mem0 ADD-only 路径与 provenance 有效性审计

> actor：Sonnet 5（Claude Code）。派工卡：
> `../cards/actor-prompt-mem0-provenance-validity-audit.md`。docs-only、零真实 API，
> 纯静态代码追踪（未跑 pytest/compileall，未调用任何 LLM/embedding API）。

## 结论（置顶，三选一）

**`ADD_ONLY_PROVEN`**——当前五 benchmark（LoCoMo/LongMemEval/MemBench/BEAM/
HaluMem）× 双轨（native/unified）所有 adapter 可达路径，最终且唯一调用
`self._memory.add(...)`（`mem0_adapter.py:1632`），不存在可达的
`update`/`delete`/`reset`/graph/procedural 旁路。详细证据见 §2、§5。

是否足以维持 Mem0 frozen-v1 B5/B11：**不裁决，只列候选**，见 §6。其中候选 C
（LongMemEval 注入粒度文档误标）与候选 B（sidecar 为批粒度而非事实粒度
provenance）是本次审计发现的、独立于 ADD-only 结论本身的重要伴生问题。

## 0. 版本/commit 身份

- adapter：`src/memory_benchmark/methods/mem0_adapter.py`；本次审计在独立
  worktree/branch `actor/mem0-provenance-validity-audit`（自 `main` @
  `eed497b` 新建）中进行，全程只读，未对 src/third_party 做任何改动。
- vendored 算法源：`third_party/methods/mem0-main`，`pyproject.toml:6-7`
  声明 `name = "mem0ai"` / `version = "2.0.4"`，与
  `notes/mem0-frozen-v1.md` §1/§3-1 记录一致。
- 上游 commit：不可溯（vendored 快照通过压缩包导入；`third_party/methods/
  mem0-main` 目录本身只携带本仓库自己的 git 历史，没有独立上游 VCS
  元数据）。版本锁定机制是 `build_mem0_source_identity`
  （`mem0_adapter.py:206-275`）对 `mem0/**/*.py` + 根 `pyproject.toml` +
  `LICENSE` + 两个 benchmark prompts 文件做确定性 SHA-256；本次审计未重新
  计算该哈希值是否仍等于 frozen-v1 记录的 `debda89…`（该 upstream drift
  对比是 frozen-v1 §3 item 1 声明的独立待办，不在本卡范围，见 §7 未知项）。
- 该 `Memory` 类文件 `mem0/memory/main.py` 共 3222 行，同时定义同步
  `class Memory(MemoryBase):`（`main.py:331`）与异步
  `class AsyncMemory(MemoryBase):`（`main.py:1795`）。按卡内 §2.2
  要求，本审计只审同步 `Memory`；已用全文 grep 确认
  `mem0_adapter.py` 从不引用 `AsyncMemory`、`mem0.client`
  （`MemoryClient`/`AsyncMemoryClient`）或 `server/` 下任何符号——
  `_create_memory_backend`（`mem0_adapter.py:1124-1157`）只
  `importlib.import_module("mem0")` 后取 `mem0_module.Memory.from_config(...)`
  （`mem0_adapter.py:1153`），不经过任何 HTTP/云端客户端。

## 1. adapter 可达调用图

### 1.1 起点：`_build_mem0_system`

`methods/registry.py:165-191`：

```python
165  def _build_mem0_system(context: MethodBuildContext) -> BaseMemorySystem:
...
172      return Mem0(
...
182          consume_granularity=(
183              "session"
184              if context.benchmark_name in {"longmemeval", "halumem"}
185              else "pair"
186              if context.benchmark_name == "beam"
187              else "turn"
188          ),
189          session_memory_report=context.benchmark_name == "halumem",
190          benchmark_name=context.benchmark_name,
191      )
```

`context.benchmark_name` 的字面值来自各 benchmark adapter 的
`name` 类属性（一手核对）：`locomo`（`benchmark_adapters/locomo.py:72`）、
`longmemeval`（`benchmark_adapters/longmemeval.py:90`）、
`membench`（`benchmark_adapters/membench.py:166`）、
`halumem`（`benchmark_adapters/halumem.py:118`）、
`beam`（`benchmark_adapters/beam.py:168`），并经
`benchmark_adapters/registry.py:549-566` 的 `BenchmarkRegistration(name=
adapter_cls.name, ...)` 注册，与 `_build_mem0_system` 里判断的字符串完全
匹配（无别名/大小写偏差）。

**⚠️ 与现有文档不一致（候选 C，见 §6）**：`registry.py:182-188` 把
`longmemeval` 与 `halumem` 同归为 `consume_granularity="session"`，只有
`beam` 是 `"pair"`；`locomo`/`membench` 走 else 分支 `"turn"`。但
`docs/reference/integration/mem0.md:30`（B2）与
`notes/mem0-frozen-v1.md:40-41` 都写"LoCoMo/LongMemEval=turn，BEAM=pair，
HaluMem=整 session"——**LongMemEval 实际不是 turn，也不是严格意义的框架级
pair，而是与 HaluMem 同组的 session 粒度**（内部再按位置切块，见 §1.3）。

### 1.2 `consume_granularity` → 聚合产出单元（`runners/event_stream.py`）

`GranularityAggregator.__init__`/`aggregate`（`event_stream.py:63-101`）按
实例声明的 `consume_granularity` 分派：

| `consume_granularity` | 聚合方法 | 产出单元 | 覆盖的 benchmark |
|---|---|---|---|
| `"turn"` | `_aggregate_turns`（`event_stream.py:102-109`） | `TurnEvent` | locomo, membench |
| `"pair"` | `_aggregate_pairs`（`event_stream.py:110-155`，user 锚定配对） | `TurnPair` | beam |
| `"session"` | `_aggregate_sessions`（`event_stream.py:156-163`） | `SessionBatch` | longmemeval, halumem |

### 1.3 `ingest(unit)` 分派 → adapter helper（`mem0_adapter.py:494-509`）

```python
494  def ingest(self, unit: IngestUnit) -> IngestResult:
497      if isinstance(unit, TurnEvent):
498          self._ingest_native_turn(unit)
500      if isinstance(unit, TurnPair):
501          self._ingest_native_pair(unit)
503      if isinstance(unit, SessionBatch):
504          self._ingest_native_session(unit)
```

三个 helper 各自的唯一出口都是 `self._add_with_provenance(...)`：

- `_ingest_native_turn`（`mem0_adapter.py:511-529`）：单 turn 消息列表，
  `source_turn_ids=(event.turn_id,)`（524），调用点 522。
- `_ingest_native_pair`（`mem0_adapter.py:531-560`）：2-turn 消息列表，
  `source_turn_ids=tuple(2 个 turn_id)`（555），调用点 546。docstring
  写"保持 LongMemEval 官方两 turn 批次"（532）——**这是过时表述**，因为
  `TurnPair` 现在只由 BEAM 触发（见 §1.1 discrepancy）。
- `_ingest_native_session`（`mem0_adapter.py:562-607`）：docstring
  明确解释了为什么 LongMemEval 不用框架级 `TurnPair`（566-567：
  "LongMemEval 约 8% 的 session 不以 user 开头"，框架级 user 锚定配对会
  错位官方分组），改为在 session 内部自行切块：
  ```python
  585  chunks = [turns] if self.session_memory_report else [
  586      turns[start : start + 2] for start in range(0, len(turns), 2)
  587  ]
  ```
  `session_memory_report=False`（LongMemEval）→ 按位置两两切块，每块一次
  `_add_with_provenance`（调用点 589，`source_turn_ids` 为该 2-turn 的
  id，598）；`session_memory_report=True`（HaluMem）→ `chunks=[turns]`
  整 session 一次 `_add_with_provenance`（`source_turn_ids` 为**全 session
  turn id**）。

### 1.4 生产 runner 如何到达 `ingest()`——以及为什么旧 `add()` 不可达

起点 `cli/run_prediction.py` → `runners/prediction.py:run_predictions()`
→ `_ingest_pending_conversations`（1895）→ `_ingest_one`（2086）→
`_add_public_conversation`（2132-2176）：

```python
2142   if _uses_turn_resume(system, public_conversation):
2147       result = system.add_from_turn(...)          # 旧协议逐 turn resume
2163   elif isinstance(system, MemoryProvider):
2164       return _ingest_memory_provider_conversation(
2165           provider=system, ...)                    # v3 provider 路径
2170   else:
2170       result = system.add([public_conversation])   # 旧协议整段 add
```

`_uses_turn_resume`（`prediction.py:2328-2336`）= `isinstance(system,
BaseResumableMemorySystem) and system.supports_turn_resume(conversation)`。
`Mem0.supports_turn_resume`（`mem0_adapter.py:481-492`）**恒返回
`False`**（docstring 原文："始终返回 False"）。`Mem0` 同时是
`MemoryProvider` 的实例（`mem0_adapter.py:278`
`class Mem0(BaseMemoryProvider, BaseResumableMemorySystem, MemoryProvider)`）。
因此对 Mem0 而言，`_uses_turn_resume` 恒 `False`，`elif isinstance(system,
MemoryProvider)` 恒 `True` → **每次都走 `_ingest_memory_provider_conversation`
（2163-2168），`add_from_turn` 分支（2147）与旧 `add()` 分支（2170）对 Mem0
恒不可达**。isolated-worker 粗粒度变体 `_add_public_conversation_coarse`
（`prediction.py:1870-1892`）同构，`isinstance(system, MemoryProvider)`
（1878）为真时同样直调 `_ingest_memory_provider_conversation`（1879），
`system.add([public_conversation])`（1884）分支同样对 Mem0 不可达。

`_ingest_memory_provider_conversation`（`prediction.py:2179-2226`）：

```python
2188   events = tuple(build_turn_events(public_conversation, isolation_key))
2190   units = tuple(
2191       GranularityAggregator(provider.consume_granularity).aggregate(
2192           events, isolation_key=isolation_key)
2196   for unit in units:
2197       if _is_ingest_unit(unit):
2198           result = provider.ingest(unit)          # ← 唯一 ingest 调用点
```

HaluMem 的 operation-level 专线（`runners/operation_level.py:331-395`
`_ingest_and_probe_session`）结构相同：同一
`GranularityAggregator(provider.consume_granularity).aggregate(...)`
（354）→ 循环 `provider.ingest(signal)`（359）→
`provider.end_session(session_ref)`（365）→
`provider.retrieve(RetrievalQuery(...))`（378-386，"update probe"，只读）。
未见任何 `.add(`/`.update(`/`.delete(` 调用。

**旧 `Mem0.add()`/`add_from_turn()`/`_add_longmemeval_conversation()`
（`mem0_adapter.py:442/755/839`）在生产调用链中被证明不可达**；它们唯一的
调用者是 `runners/conversation_qa.py:77` 的
`system.add([public_conversation])`，位于 `run_conversation_qa()`
（`conversation_qa.py:53-106`）内。全仓库 grep `run_conversation_qa(` 的
调用者只有 `tests/test_conversation_runner.py`（142/155/170/200/224/241
六处）；`cli/run_prediction.py`、`runners/evaluation.py`、
`runners/operation_level.py`、`runners/prediction.py` 虽然都
`import` 了 `conversation_qa.py` 的符号，但只导入
`_make_public_conversation`/`_make_public_question`/
`BaseAnswerEvaluator`（类型协议），**从未导入或调用
`run_conversation_qa` 本体**。即：这条旧路径只被测试 fixture 使用，不是
生产源码路径（按 actor-handbook §2 硬规则，不得用测试 fixture 代替生产
源码证据，此处反向确认：它恰恰证明了该路径**不是**生产路径）。

### 1.5 native/unified 是否复用同一 build 路径

**ingest 侧**：native/unified 不区分——`ingest()`/三个 `_ingest_native_*`
对两条 track 完全相同，写入阶段没有 track 分叉。

**retrieve 侧**：两者调用 `self._memory.search(...)` 时参数完全一致
（`question.text`/`native_question.text`, `filters={"run_id": ...}`,
`top_k=self.config.top_k`），仅结果包装不同：
- `retrieve(Question)`（native，`mem0_adapter.py:892-967`）搜索调用见
  906-932，构造 `AnswerPromptResult`，**不附带 `source_turn_ids`**（该
  返回类型没有 `items`/provenance 字段）。
- `_retrieve_native(RetrievalQuery)`（unified，`mem0_adapter.py:969-1065`）
  搜索调用见 998-1012，构造 `RetrievalResult`，在 1032-1049 为每条
  `RetrievedItem` 附加 `source_turn_ids=self._source_turn_ids_for_memory(
  memory["id"])`（1038）。

全文 grep 确认 `_source_turn_ids_for_memory` 只有这一个调用点
（`mem0_adapter.py:1038`，定义在 1658）。**换言之，provenance/
source_turn_ids 机制只在 unified track 生效；native track 完全不经过
sidecar 反查**，这是 B5/B11 结论范围需要明确的口径边界。

## 2. `Memory.add()` 全分支（`third_party/methods/mem0-main/mem0/memory/main.py`）

`add()` 定义 `main.py:573-660`，实际调用形态（由 `_add_with_provenance`
传入）恒为 `user_id=None, agent_id=None, memory_type=None, infer=True`
（推导见 §3）。

| 分支 | 触发条件 | 本 adapter 是否可达 | 证据 |
|---|---|---|---|
| procedural memory | `agent_id is not None and memory_type==PROCEDURAL` | **不可达**：adapter 全文 grep `agent_id`/`memory_type` 零命中，恒为 `None` | `main.py:650-652` |
| `memory_type` 非法校验早退 | `memory_type not in (None, PROCEDURAL)` | 恒不触发（`memory_type` 恒 `None`） | `main.py:628-634` |
| vision parse | `parse_vision_messages(messages, ...)` | 可达但恒为 no-op passthrough：adapter 消息 `content` 恒为纯字符串（`_turn_to_message`, `mem0_adapter.py:1404-1420`），从不是 `list`/`image_url` dict，故只命中 utils.py 的 else 直通分支 | `main.py:654-657`；`memory/utils.py:170-197`（可达分支仅 193-195） |
| `infer=False` 原始注入 | `add(infer=False)` | **不可达**：`Mem0Config.__post_init__`（`mem0_adapter.py:137-140`）强制 `infer=True`，`smoke()`/`official_full()` 硬编码 `infer=True`（168/187），`configs/methods/mem0.toml` 的 `["smoke"]`/`["official_full"]` 两段也都是 `infer = true`——registry→dataclass→TOML 三层闭合，无法构造出 `infer=False` 的 `Mem0Config` | `main.py:663-697` |
| **V3 phased batch pipeline**（`infer=True`） | 恒定路径 | **唯一可达路径** | `main.py:699-971` |
| Phase 1 既有记忆检索 | 恒执行，只读 `vector_store.search` | 可达 | `main.py:706-714` |
| Phase 2 LLM 抽取（`ADDITIVE_EXTRACTION_PROMPT`） | 恒执行；异常→捕获返回 `[]` | 可达 | `main.py:723-748` |
| 空抽取 | `extracted_memories` 为空 | 可达；只 `db.save_messages`，不新增 memory，返回 `[]` | `main.py:765-768` |
| hash 去重 | `md5(text)` 命中 `existing_hashes` 或本批已见 | 可达；跳过，不新增不改写 | `main.py:799-803` |
| 全部去重后 `records` 为空 | | 可达；`db.save_messages`，返回 `[]` | `main.py:820-822` |
| Phase 6 批量 insert（新 `uuid4()`） | `records` 非空 | 可达；纯插入新向量，批失败→逐条 fallback | `main.py:807, 824-841` |
| Phase 6 history 写入 `event="ADD"` | 同上 | 可达；`old_memory=None, is_deleted=0` | `main.py:844-863` |
| Phase 7 entity_store 更新 | 命中相似实体（余弦≥0.95） | 可达但**只改实体索引的 `linked_memory_ids` 关联列表**，不改任何 memory 正文/id；异常吞掉继续 | `main.py:865-955`，尤其 918-932 |
| Phase 8 返回 `event="ADD"` | 恒定 | 可达；本函数返回值 event 可达全集 = `{"ADD"}` | `main.py:957-971` |
| `update()`/`_update_memory()` | 需显式调用 `Memory.update()` | **不可达**：adapter 全文对 `self._memory` 只有 6 处调用（见 §5），无 `.update(` | 定义 `main.py:1501-1523`/`1657-1721` |
| `delete()`/`_delete_memory()`（单条） | 需显式调用 `Memory.delete()` | **不可达**：adapter 从未调用裸 `.delete(` | 定义 `main.py:1524-1539`/`1722-1751` |
| `delete_all()` → 循环 `_delete_memory` | `clean_failed_ingest_state` 唯一入口 | **可达，但仅限失败重试的整命名空间擦除**，见 §4 | `mem0_adapter.py:1735-1751`；`main.py:1540-1571` |
| `reset()` | 需显式调用 | **不可达**：adapter 全文 grep 零命中 | `main.py:1752-1784` |
| agent-scoped 记忆（纯 `agent_id`，无 procedural） | 影响 `system_prompt` 后缀 | **不可达**：同样依赖 `agent_id`，adapter 从不传 | `main.py:724-727` |
| graph memory | 需 `self.graph`/`graph_store` config | **架构上不存在**：整个 `mem0/memory/main.py`（含 `AsyncMemory`）grep `self.graph` 零命中；`MemoryConfig`（`mem0/configs/base.py`）无 `graph_store` 字段；`mem0/` 包内无任何 `*graph*` 模块 | 全文 grep，见 §5 |
| `AsyncMemory` 全部方法 | 需显式 `import AsyncMemory` | **不可达**：adapter 全文 grep 零 `AsyncMemory` 引用 | `main.py:1795-3222` |
| 云端 `MemoryClient`/reranker | 需 `mem0.client` 或 `config.reranker` | **不可达**：adapter grep 零命中；`build_backend_config`（`mem0_adapter.py:389-440`）不含 `reranker` key，`main.py:349-354` 显示 reranker 仅当 `config.reranker` 真值时初始化 | `mem0_adapter.py:389-440` |
| `_should_use_agent_memory_extraction` | 定义于 `main.py:552` | **vendored 源码自身死代码**：在同步 `Memory` 类体（331-1794）范围内 grep，除自身定义外零调用（`add()`/`_add_to_vector_store()` 均不引用它） | `main.py:552` |

## 3. 调用形态推导（`_add_with_provenance` 传给 `Memory.add` 的实际 kwargs）

三个 `_ingest_native_*` 都通过 `self._add_with_provenance(messages,
source_turn_ids=..., run_id=event.isolation_key, metadata=...,
infer=self.config.infer, prompt=...)` 调用（`mem0_adapter.py:522-529` /
546-560 / 589-603），`_add_with_provenance`（1623-1643）原样透传
`**kwargs` 给 `self._memory.add(messages, **kwargs)`（1632）。全文 grep
`mem0_adapter.py` 未见任何调用点传入 `user_id`/`agent_id`/`memory_type`。
故 `Memory.add()` 实际收到的固定形态为
`user_id=None, agent_id=None, run_id=<isolation_key>, memory_type=None,
infer=True`，这正是 §2 表格里"可达/不可达"判断的依据。

## 4. `clean_failed_ingest_state`——唯一可达的删除路径

```python
1735 def clean_failed_ingest_state(self, isolation_key: str) -> None:
1740     session_scope = f"run_id={isolation_key}"
1741     self._memory.delete_all(run_id=isolation_key)
1742     self._memory.db.delete_messages(session_scope)
1743     with self._namespace_lock:
1744         self._provenance_by_memory_id = {
1745             memory_id: record
1746             for memory_id, record in self._provenance_by_memory_id.items()
1747             if record.get("isolation_key") != isolation_key
1748         }
```

`Memory.delete_all(run_id=...)`（`main.py:1540-1571`）要求至少一个
filter（1557-1560 空 filter 会 `raise ValueError`，因此**不可能被误用为
全局清空**——那是 `reset()` 的专职，本 adapter 不可达），按
`self.vector_store.list(filters={"run_id": isolation_key})`
（1565）精确 scope 到该 conversation 自己的向量，逐条
`self._delete_memory(memory.id)`（1567，产出 `event="DELETE"` 历史行，
`main.py:1738`）。

**这是唯一触达 DELETE 语义的调用**，但只在 `clean_failed_ingest_state`
被调用时发生。调用链：`cli/run_prediction.py:100-133`
`_bind_clean_failed_ingest_conversation` 绑定 → `runners/prediction.py:
737-795` `_prepare_clean_failed_ingest_retries`：

```python
764   if not policy.retry_failed_conversations:
765       return ()
...
773       if _conversation_state_status(state) != _STATUS_FAILED_INGEST:
774           continue
776       clean_failed_ingest_conversation(...)
```

`_STATUS_FAILED_INGEST`（`prediction.py:285`）只标记**从未完成 ingest**
的 conversation——按 4 步主线（ingest→retrieve→answer→metric），一个
conversation 只有在 ingest 阶段整体失败/未完成时才会落在这个状态，此时
它从未进入过 retrieve/answer 阶段，即从未支撑过任何已产出的检索或回答。
清理后连带把 sidecar 中该 `isolation_key` 的全部映射一并清除
（1743-1751），不留孤儿映射。

结论：delete_all 是**失败重试前的整命名空间擦除**，精确 scope 到未曾服务
过检索的 conversation，不构成"已用于回答问题的 memory 被静默删除/改写"。
本审计核实了这一条已声明路径的行为与其触发前置条件（`_STATUS_FAILED_
INGEST` 语义、`retry_failed_conversations` 策略门），未做 resume/
checkpoint 状态机的穷尽性证明（不在本卡范围，见 §7）。

## 5. 负空间搜索（检索词 + 零命中范围）

| # | 检索词 | 检索范围 | 结果 |
|---|---|---|---|
| 1 | `self\._memory\.` | `mem0_adapter.py` 全文 | 恰好 6 处：`search`×4（922/928/1002/1008）、`add`×1（1632）、`delete_all`+`db.delete_messages`×1 对（1741/1742）。无其它调用。 |
| 2 | `\.update\(` | `mem0_adapter.py` 全文 | 仅 `hashlib.digest.update(...)`（265-268）与 `set.update(...)`（368），均与 Mem0 记忆无关；零 Mem0 API 命中。 |
| 3 | `\.delete\(`（裸） | `mem0_adapter.py` 全文 | 零命中（`delete_all`/`db.delete_messages` 不匹配此模式，已由 #1 单独枚举）。 |
| 4 | `\.reset\(` | `mem0_adapter.py` 全文 | 零命中。 |
| 5 | `graph` | `mem0_adapter.py` 全文 | 零命中。 |
| 6 | `procedural`（忽略大小写） | `mem0_adapter.py` 全文 | 零命中。 |
| 7 | `agent_id`/`memory_type`/`agent_scoped` | `mem0_adapter.py` 全文 | 零命中。 |
| 8 | `self\.graph\b` | `third_party/methods/mem0-main/mem0/memory/main.py` 全文（含 `Memory`+`AsyncMemory` 两个类） | 零命中。 |
| 9 | `graph_store`/`graph` | `third_party/methods/mem0-main/mem0/configs/base.py`（`MemoryConfig` schema） | 零命中——`graph_store` 不是该版本配置 schema 的字段。 |
| 10 | 文件名含 `graph` | `find third_party/methods/mem0-main/mem0 -iname "*graph*"` | 零文件。 |
| 11 | `self.update(`/`self.delete(`/`self._update_memory(`/`self._delete_memory(`/`self.reset(`/`self.delete_all(` | 同步 `Memory` 类体（`main.py:331-1794`） | 恰好 3 处（1521/1537/1567），全部落在 `update()`/`delete()`/`delete_all()` 自身方法体内，均不在 `add()`（573-660）、`_add_to_vector_store()`（662-971）或 `search()`（1126-1237）/`_search_vector_store()`（1343-1439）的方法体范围内。 |
| 12 | `"UPDATE"`/`"DELETE"`（history event 字面量） | `main.py` 全文 | 仅 4 处：1707/1738（同步 `_update_memory`/`_delete_memory` 内部）、3141/3174（`AsyncMemory` 对应方法，越界不审）。`add()`/`_add_to_vector_store()` 自身范围内零命中，可达 event 字面量只有 `"ADD"`（692 不可达 + 961 可达）。 |
| 13 | `run_conversation_qa(` 调用者 | `src/` + `tests/` 全仓库 | 仅 `tests/test_conversation_runner.py`（142/155/170/200/224/241）；`src/` 内 4 个 import 者（`cli/run_prediction.py`、`runners/evaluation.py`、`runners/operation_level.py`、`runners/prediction.py`）只导入其内部辅助函数/协议类型，不导入/调用 `run_conversation_qa` 本体。 |
| 14 | `AsyncMemory`/`mem0.client`/`MemoryClient`/`reranker`/`rerank` | `mem0_adapter.py` 全文 | 零命中。 |
| 15 | `self.db` | `search()`+`_search_vector_store()`（`main.py:1126-1439`） | 零命中——检索路径完全不触达历史 SQLite（`self.db`），只查 `self.vector_store`。 |
| 16 | `_should_use_agent_memory_extraction` 调用者 | 同步 `Memory` 类体（`main.py:331-1794`） | 除自身定义（552）外零调用；vendored 源码自身的死代码，非 adapter 特有裁剪。 |

## 6. 结论对 B5/B11 的影响候选（不裁决）

- **候选 A（支持维持现状）**：若 B5"turn provenance"的声明只要求"每条
  memory 的 sidecar 映射准确反映其诞生批次里出现过的公开 turn 集合，且该
  集合不会被后续操作篡改"，本次一手证据满足这一版本的 B5；B11 的 13 格
  证据不因本审计作废。
- **候选 B（可能需要收紧声明或部分改判 N/A）**：sidecar 的
  `source_turn_ids` 实际是**"ingest 批粒度"而非"单条抽取事实粒度"**
  （见 §1.3）——turn 粒度（locomo/membench）单 turn 精确无歧义；但 BEAM
  （2-turn）、LongMemEval（2-turn chunk）、尤其 HaluMem（**整 session**，
  可能数十 turn）三者中，若一次 `add()` 抽出多条 memory，每条都会被
  记成"来自该批次内全部 turn"，即使某条实际只源自其中一个 turn。这与
  README 断点已述的 LightMem 案例（"transformation-input union 会制造
  semantic provenance 假阳性"）同构，需要架构师判断是否要在 metric 层做
  批粒度加权/拆分，或对 HaluMem/BEAM/LongMemEval 的逐 turn 粒度 Recall/
  NDCG 改判 N/A 或降级为"批级"声明。
- **候选 C（文档纠正，独立于 ADD-only 结论，也独立于候选 B）**：
  `docs/reference/integration/mem0.md:30`（B2）与
  `docs/workstreams/ws02.7-method-track/notes/mem0-frozen-v1.md:40-41`
  都把 LongMemEval 注入粒度写成"turn"，但 `registry.py:182-188` 实际把
  它与 HaluMem 同归为 `consume_granularity="session"`；
  `mem0_adapter.py:532` 的中文 docstring"保持 LongMemEval 官方两 turn
  批次"同样是过时表述（`TurnPair` 现在只由 BEAM 触发）。此项不影响
  `ADD_ONLY_PROVEN` 本身，但两份参考文档 + 一处内部 docstring 需要更新，
  且更新前基于这两份文档做判断的后续工作（包括未来的 actor 派工卡）可能
  继承这个误标。
- **附带观察（非 mutation，设计层面的潜在缺口）**：`_add_with_provenance`
  写 sidecar 是普通赋值而非合并（`mem0_adapter.py:1638`
  `self._provenance_by_memory_id[memory_id] = {...}`）——当前可达路径下
  每条新 memory 恒分配 `uuid4()` 新 id（`main.py:807`），不会发生 id
  复用，故这条"覆盖不合并"的语义目前不可观察、不构成现存问题；但它是
  sidecar 自身没有防御的一点，若未来任何改动（不限于本 adapter）引入 id
  复用，现有 fail-fast（`mem0_adapter.py:1664-1668`）只能防"缺映射"，
  防不了"存在但已被覆盖的错误映射"。

## 7. 未知项

- 本审计为纯静态代码追踪，未运行任何测试/真实 API（卡内零 API 要求本身
  如此），不构成运行时行为的直接观察；结论建立在控制流可达性分析上。
- 未重新计算 `build_mem0_source_identity`（`mem0_adapter.py:206-275`）的
  当前 SHA-256 是否仍等于 frozen-v1 记录的 `debda89…`——这是 frozen-v1
  §3 item 1 声明的独立 upstream drift 待办（5×10 矩阵完工后做），不在本
  卡范围。
- `AsyncMemory`（`main.py:1795-3222`）、`mem0/client`
  （`MemoryClient`/`AsyncMemoryClient`）、`server/main.py` 完全未逐行
  审查——已用全文 grep 确认 adapter 不引用它们（§5 #14），按卡内"不审
  async 未调用路径"排除，未进一步读其内部实现（无必要，因为不可达）。
- `clean_failed_ingest_state` 与 resume/checkpoint 状态机的完整交互
  （例如是否存在"部分 chunk 已写入、conversation 既未标记
  `failed_ingest` 也未被清理"的中间态）未做穷尽性状态机审计；本次只验证
  了"`failed_ingest` → 清理"这一条已声明路径的行为，以及该状态在被标记
  前不会先经过 retrieve/answer 阶段（依据 checkpoint 语义与 4 步主线的
  结构性论证，非逐行穷举 resume 全部分支）。完整 resume 正确性审计不属
  本卡范围（且 resume 逻辑变更需架构师另行 review，见 `AGENTS.md`）。
- 未深入 `embedding_provider="openai"` 分支（`build_backend_config` 中
  `embedder_config["api_key"]`/`["openai_base_url"]` 路径，
  `mem0_adapter.py:413-415`）的行为，因为当前两个 profile（smoke/
  official_full）固定用 `embedding_provider="huggingface"` 本地模型
  （`configs/methods/mem0.toml`）；该分支存在但配置层面当前不可达，未
  评估其是否改变 ADD-only 结论（理论上不会，因为它只影响 embedder
  provider，不影响 add/update/delete 决策路径，但未逐行验证）。
- 未逐行验证 `_search_vector_store`/`_compute_entity_boosts`
  （`main.py:1343-1500`）内部排序/entity-boost 逻辑的正确性——只确认了
  它们不调用 `update`/`delete`（§5 #11 的范围排除已覆盖），未审查其打分
  逻辑是否影响 metric（超出本卡"provenance mutation"范围）。

## 8. 未命中停工条件

卡内 §4 列出的 5 条停工条件逐条核对：adapter 实际绑定的 Mem0 类/版本可从
`_create_memory_backend`（`mem0_adapter.py:1124-1157`）+ `pyproject.toml:
6-7` 确定；`infer`/`consume_granularity`/`session_memory_report` 等配置
值均可从 registry→dataclass→TOML 链条闭合（见 §2、§3）；全程未需要运行
真实 LLM 判断控制流（纯静态读码）；未改允许清单外文件；未发现相互矛盾且
15 分钟内无法消解的一手实现。故本次未触发停工，note 写完即按卡内 §5
自检并提交。

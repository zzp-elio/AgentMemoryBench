# Mem0 产品 messages / namespace / time 契约审计

> actor：Sonnet 5（Claude Code）。派工卡：
> [`../cards/actor-prompt-mem0-core-message-contract-audit.md`](../cards/actor-prompt-mem0-core-message-contract-audit.md)。
> 隔离 worktree `.claude/worktrees/actor+mem0-core-contract-audit`（分支
> `worktree-actor+mem0-core-contract-audit`，起点 `main@6643e56`，全程干净、无未提交前置改动）。
> 零真实 API、零网络（含遥测，见 §4.0）；全部结论要么来自一手源码逐行追踪，要么来自
> hermetic 探针（真实 vendored `Memory` 类 + fake LLM/embedder/vector store + **真实**
> in-memory `SQLiteManager`）的实测 stdout。本卡不裁 benchmark consume granularity，不改
> 生产代码。

## 0. 结论（置顶）

```text
CORE_CONTRACT_READY(
  接受 str/dict/list[dict] 全部 messages 形状；
  Memory.add()/_add_to_vector_store() 在运行期对 role 序列零校验——
  不检查交替、不检查首尾 role、不检查奇偶长度，任意角色序列（含连续同 role、
  assistant 起始、单条、奇数条、system 角色、未知角色）均可正常跑完并返回，
  已用真实 core + hermetic fake 实测 18+2 组组合验证；
  唯一的两个硬性崩溃点是消息 dict 缺 "role" 或缺 "content" 键（parse_messages
  的裸 bracket 访问，KeyError 直接冒出 add()，LLM 未被调用、messages 表无写入）；
  role 与说话人身份是两个独立通道——content 靠具名前缀 "speaker: text" 承载身份，
  role 只决定该消息在 parse_messages() 输出里是否可见及被视为 user/assistant/system；
  批次边界有真实代价：last_messages(limit=10) 会让上一次 add() 持久化的原始消息
  渗入下一次调用的 "Last k Messages" 上下文（仅作指代消解背景，不与本次 New
  Messages 一起被抽取），因此"一次 add 两条"与"两次 add 各一条"不是抽取语义等价，
  是本次实测证实的 batch identity 差异；namespace 上 user_id/agent_id/run_id
  可同批叠加组成一个复合 AND scope（非独立记忆库），且在 core 算法/隔离层面
  run_id 单独使用与 user_id 单独使用是 CONFIG_EQUIVALENT（唯一已知差异分支
  is_agent_scoped 只认 "agent_id 存在且 user_id 缺失"，与 run_id 无关、与消息内
  是否出现 assistant 角色也无关）；抽取 LLM 唯一能看到的时间来源是 content 内嵌
  文本或 prompt=/custom_instructions 覆盖，metadata 里的 turn_time/session_time 与
  REST client 专属的 timestamp 参数一律不可见，Observation Date/Current Date 两个
  prompt 字段在当前调用形态下恒等于真实挂钟日期；本地 core 与两条"官方"
  benchmark 入口分属三种不同 product surface（本地 core / 自托管 REST / 云端
  SDK），legacy 双 namespace + role 互换 + user-only custom instruction 抽取
  是一种在本地 core 结构上不会自动复现的历史行为，不能与当前产品主轨混为一谈。
  明确限制见 §9，给五张 benchmark 卡的可复用契约输入见 §10。
)
```

## 1. Source identity

- adapter：`src/memory_benchmark/methods/mem0_adapter.py`（本次审计只读，未改一行）。
- vendored 算法源：`third_party/methods/mem0-main`，`pyproject.toml` 声明
  `mem0ai==2.0.4`，与 `notes/mem0-frozen-v1.md`、
  `../../retrieval-metrics/notes/mem0-provenance-validity-audit.md` 记录一致；本卡
  未重新计算 `build_mem0_source_identity()`（`mem0_adapter.py:216-275`）的当前
  SHA-256 是否仍等于 frozen-v1 记录的 `debda89…`——upstream drift 对比是既有卡已声明
  的独立待办，不在本卡范围。
- 只审同步 `class Memory(MemoryBase)`（`mem0/memory/main.py:331-1794`）。`AsyncMemory`
  （1795-3222）、`mem0.client.MemoryClient`/`AsyncMemoryClient`（用于 §2 legacy 入口）、
  `mem0/server/` 均未逐行审查；`mem0-provenance-validity-audit.md` §5 #14 已用全文 grep
  确认 `mem0_adapter.py` 从不引用它们，本卡沿用该结论、未重复该 grep。

## 2. 三类"官方"入口身份表

| 入口 | 调用对象 | namespace 形状 | message 形状 | 时间参数 | chunk size | 定位 |
|---|---|---|---|---|---|---|
| **本框架** `mem0_adapter.py` | 本地 vendored `mem0.memory.main.Memory`（`_create_memory_backend` 用 `importlib.import_module("mem0")`，`sys.path` 指向 `third_party/methods/mem0-main`；`mem0_adapter.py:1177-1186`）| 唯一 `run_id=isolation_key`（conversation 级）；全文 grep 从不传 `user_id`/`agent_id`（`_add_with_provenance` 原样透传 kwargs 给 `self._memory.add`，`mem0_adapter.py:1703-1723`） | `{"role": role, "content": f"{prefix}{turn.speaker}: {text}"}`；`role` 优先取 `event.role`（若已 ∈ {user,assistant}），否则回退到**会话级粘性映射** `self._native_speaker_roles[isolation_key]`——首次遇到的新 speaker→"user"，第二个新 speaker→"assistant"，第三个新 speaker再次落到 "user"（`len(speaker_roles) % 2 == 0`），该映射跨同一 conversation 的多次 ingest 调用持久（`mem0_adapter.py:521-617,1444-1465`） | 内容头 `[Turn time: …]`/`[Session time: …]`（`turn→session→None` 唯一 fallback，`_effective_time_prefix`，`mem0_adapter.py:1474-1501`）+ metadata `turn_time`/`session_time`（`_native_turn_metadata`，`mem0_adapter.py:679-694`，只供 retrieve 侧提升为 reader `created_at`，见 §7）+ `prompt=` 注入 `_observation_time_prompt()` 自然语言覆盖（`mem0_adapter.py:1607-1623`） | locomo/membench=1（turn 粒度）、beam=2（pair）、longmemeval/halumem=session 内部按位置两两切块或整 session 一次（`session_memory_report`）| Phase 1 unified 主轨——runner 唯一实际调用的路径（`_ingest_memory_provider_conversation`，见既有 provenance 审计 §1.4，本卡未重复复核，直接沿用） |
| **当前产品 benchmark harness** `memory-benchmarks/benchmarks/{locomo,longmemeval,beam}/run.py` + `common/mem0_client.py` | `Mem0Client`（**REST，非本地 core**）：`mode="oss"`→`http://localhost:8888` 自托管 server 的 `POST /memories`/`POST /search`；`mode="cloud"`→`api.mem0.ai` `/v3/memories/` 异步事件轮询（`mem0_client.py:117-345`）| 唯一 `user_id`；LoCoMo/BEAM=每 conversation 一个（`f"locomo_{conv_idx}_{run_id}"` `locomo/run.py:256`、`f"beam_{chat_size}_{conv_idx}_{run_id}"` `beam/run.py:359`——此处的 `run_id` 是该 harness 自己"这次 benchmark 执行"的书签变量，与 Mem0 API 的 `run_id` 命名空间参数**同名不同义**，两者不可混称）；LongMemEval=**每 question 一个**（`f"longmemeval_{question_id}_{run_id}"`，`longmemeval/run.py:348`，官方注释原文"Each question gets its own user_id so memories don't leak between questions"，`longmemeval/run.py:343`）| LoCoMo：`{"role": "user"/"assistant", "content": f"{speaker}: {text}"}`，role 由 `speaker == speaker_a` 二值判定（`locomo/run.py:165-186`）；LongMemEval：`{"role": t["role"], "content": t["content"]}` **原样透传数据集自带 role，不加具名前缀**（`longmemeval/run.py:314-324`，与 LoCoMo/legacy/本框架的具名前缀约定不同）；BEAM：`{"role": turn.get("role","user"), "content": ...}`，缺 role 时**这一层**（非 Mem0 core）先兜底填 "user"（`beam/run.py:255-269`）| REST payload 顶层 `timestamp`（unix epoch整数，由 session/turn 原始日期折算；LoCoMo `timestamp=session_epoch` `run.py:340`，LongMemEval `timestamp=session_timestamp` `run.py:451`，BEAM `timestamp=time_epoch` `run.py:476`）——**这是 `Mem0Client`/server 端参数，本地 `Memory.add()` Python 签名没有 `timestamp` 形参**，两者不可混用（见 §7）| LoCoMo=1、LongMemEval=2（`pair_turns` 按位置切，不校验角色）、BEAM=2 | 官方 Phase 1 产品 benchmark 复现口径的"当前默认跑法"，但物理上走 REST/云端 API surface，不是本仓库直接依赖的本地 core 调用形态 |
| **legacy/paper LoCoMo** `evaluation/src/memzero/{add,search}.py` | `from mem0 import MemoryClient`——Mem0 **云端 SDK 客户端**（`api_key`/`org_id`/`project_id`，`add.py:47-51`），**既不是本地 core 也不是上一行的自托管 REST 包装**；`add()` 额外传 `version="v2"`、`enable_graph=self.is_graph`（`add.py:69-71`）——`version`/`enable_graph` 在本地 vendored `Memory.add()` 签名中完全不存在 | **两个独立** `user_id`：`speaker_a_user_id=f"{speaker_a}_{idx}"`、`speaker_b_user_id=f"{speaker_b}_{idx}"`（`add.py:90-91`）；处理前先各自 `delete_all(user_id=...)` 清空（`add.py:94-95`）| 每条 chat turn **同时**追加进两份等长列表：`messages`（speaker_a→role="user"、speaker_b→role="assistant"）与 `messages_reverse`（**同一内容，role 整体互换**：speaker_a→"assistant"、speaker_b→"user"）；content 同为具名前缀 `f"{speaker}: {text}"`（`add.py:105-115`）；`messages`→写入 `speaker_a_user_id` 的记忆库，`messages_reverse`→写入 `speaker_b_user_id` 的记忆库（`add.py:117-130`）；custom_instructions 显式要求"只从 user 消息抽取，不吸收 assistant 回复"（`add.py:39`）| `metadata={"timestamp": <session_N_date_time 原始字符串>}`（云端 `MemoryClient.add()` 的 `metadata=` 参数，`add.py:83`）——与上一行 REST client 的 `timestamp=` unix epoch 整数参数是**第三种**不同的时间签名 | `batch_size=2`（每个 speaker 各自的等长列表按 2 条切，`add.py:80-83`）| **历史/论文复现参照，不代表当前 Phase 1 产品主轨**；检索侧 `search.py` 对两个 namespace 各自 `search_memory` 一次，再把两份结果一起塞进同一 answer prompt 模板（`search.py:90-127`）——"分开写入、合并作答" |

**分层结论**：三条入口调用的是三种不同的 Mem0 产品 surface（本地 OSS core／自托管
REST 包装／云端 SDK），彼此不能互证"角色交替假设"或"namespace 语义"是否成立。
legacy 路径的 `messages`/`messages_reverse` 双写 + role 整体互换，本质是用**两个独立
memory store、each 只信任一侧角色**的方式，配合 custom_instructions 的"只抽 user"指令，
构造出"每个说话人只从自己的第一人称视角被记住"的效果——这是本地 vendored core 的
`ADDITIVE_EXTRACTION_PROMPT`（结构上双侧抽取，见 §6）不会自动复现的行为：本地
`Memory.add()` 没有"只抽 user 侧"的代码级开关，是否服从这类 custom_instructions 属于
LLM 遵循自然语言指令的问题，本卡未调用真实 LLM，不对此下结论（禁止用输出质量证明
结构契约）。

## 3. §2 已验收事实 drift 检查

逐条核对当前 source，**无冲突**：

1. 本框架调用的是 vendored OSS `Memory.add/search`——确认，`_create_memory_backend`
   `importlib.import_module("mem0")` 后取本地类，未见任何 HTTP/云端客户端引用。
2. adapter 只传 `run_id=isolation_key`——确认，`_add_with_provenance` 全文透传
   kwargs，三个 `_ingest_native_*` 调用点均只含 `run_id=`，全文 grep `mem0_adapter.py`
   零 `user_id=`/`agent_id=` 调用点。
3. `ADD_ONLY_MUTATION_PROVEN`——本卡未重扫完整 mutation 图（卡内禁止），仅在 §6 读
   `main.py` Phase 0-8 时顺带确认 Phase 6/7 只有 `insert`/`entity_store` 更新，未见
   `update()`/`delete()` 调用，与既有判词方向一致，不构成推翻。
4. OSS `Memory.add()` 无独立 timestamp 参数、adapter 用 `turn_time→session_time→None`
   唯一 effective time——确认，且本卡在 §7 用 hermetic 探针把这一判词的机制**加深**到
   prompt 组装层：不仅 `add()` 签名无 `timestamp`，连内部 `generate_additive_extraction_
   prompt()` 的 `timestamp`/`current_date` 形参也**从未被 `_add_to_vector_store()` 传入**
   （`main.py:731-736` 只传 `existing_memories`/`new_messages`/`last_k_messages`/
   `custom_instructions` 四个kwargs），这不是对既有判词的反证，而是解释了 adapter 为何
   必须用 `prompt=` 通道做 `_observation_time_prompt()` 覆盖——细节见 §7。
5. 当前 smoke 配置 MiniLM/gpt-4o-mini——本卡未触碰配置文件，未见需要更新之处。

附带确认：既有候选 C（`docs/reference/integration/mem0.md` B2 与
`notes/mem0-frozen-v1.md:40-41` 把 LongMemEval 注入粒度写成"turn"，但
`registry.py:207-211`/`_mem0_consume_granularity` 与 `mem0-provenance-validity-audit.md`
均显示实际是 `"session"`）依然存在，本次直接 grep `registry.py` 复核（`_mem0_consume_
granularity`：`longmemeval`/`halumem`→`"session"`，`beam`→`"pair"`，其余→`"turn"`），
未见新证据推翻或修复。本卡不裁决/不修复此项（超出卡内范围），仅确认 drift 状态未变，
不构成本卡的停工条件（卡内 §2 列出的 5 条既有事实中不含此项）。

## 4. 探针方法论

用真实 `mem0.memory.main.Memory`（`sys.path` 插入
`third_party/methods/mem0-main`，`MEM0_TELEMETRY=False` 在 import 前设置以关闭
PostHog 遥测——`mem0/memory/telemetry.py:14` 在模块导入时读取该环境变量，不设置会在
`Memory()` 构造时创建真实 PostHog 客户端并可能发出网络请求），只替换 I/O 边界：

- `EmbedderFactory.create`/`VectorStoreFactory.create`/`LlmFactory.create`
  三个工厂在 `Memory()` 构造**之前**打桩为 `MagicMock`（构造期不产生真实网络/模型
  加载），构造完成后再手动覆盖实例属性为下列专用 fake：
- `memory.db = SQLiteManager(":memory:")`——**真实**、有状态的 vendored
  `SQLiteManager`（纯 `sqlite3`，进程内 `:memory:`，零磁盘/零网络），而非
  `MagicMock`；这是本卡刻意的选择：actor-handbook §6 明确要求"批次/session 增量声称
  必须执行承重的 stateful core，不能只用'每次 add 直接伪造 insert'的 backend"——若把
  `db.get_last_messages`/`db.save_messages` mock 成固定返回值，就无法观测 §7/§8 里
  "上一次 add 的消息是否渗入下一次调用" 这类跨调用状态效应，因此这一层必须是真实
  SQL 执行。
- `memory.vector_store`：极简 fake，`search()` 恒返回 `[]`（不含预置记忆，简化 Phase 1
  语境），`insert()` 记录调用参数供事后断言。
- `memory.embedding_model`：`embed`/`embed_batch` 返回固定向量，不做真实 embedding。
- `memory.llm`：`RecordingLLM`，记录每次 `generate_response(messages=…)` 的**原始
  kwargs**（可逐条读出 system/user 两条消息的确切文本），并从一个预置队列里弹出
  canned 响应（可以是异常实例，用于模拟 LLM 调用失败）。

核心构造（完整脚本见 `/private/tmp/.../scratchpad/mem0_core_contract_probe.py` 等
三个文件，会话本地临时文件，不提交仓库；以下为其中判定"能否运行/能否观测"的最小
必要代码，逐字摘录）：

```python
os.environ["MEM0_TELEMETRY"] = "False"
sys.path.insert(0, ".../third_party/methods/mem0-main")
from mem0.memory.main import Memory
from mem0.memory.storage import SQLiteManager

def make_memory(llm_responses):
    with patch("mem0.utils.factory.EmbedderFactory.create", return_value=MagicMock()), \
         patch("mem0.utils.factory.VectorStoreFactory.create", return_value=MagicMock()), \
         patch("mem0.utils.factory.LlmFactory.create", return_value=MagicMock()), \
         patch("mem0.memory.storage.SQLiteManager", return_value=MagicMock()):
        memory = Memory()
    memory.config.custom_instructions = None
    memory.custom_instructions = None
    memory.db = SQLiteManager(":memory:")       # 真实、有状态
    memory.vector_store = FakeVectorStore()       # search()->[]，insert() 记录
    memory.embedding_model = FakeEmbedder()       # 固定向量
    memory.llm = RecordingLLM(llm_responses)      # 记录每次 generate_response(messages=)
    return memory
```

该模式与 vendored 包自带单测（`third_party/methods/mem0-main/tests/memory/
test_main.py:10-27,30-46,81-104`）的 mock 方式一致（同样先打桩三个 Factory 再构造
`Memory()`，同样手动覆盖 `memory.db.get_last_messages`/`save_messages`），本卡额外把
`db` 换成真实 `SQLiteManager(":memory:")` 而非该文件用的 `MagicMock`，以获得跨调用的
真实状态转移。

对每个 case，实际执行 `memory.add(**kwargs)`（走完整公开入口，包含 `str`/`dict`/
`list` 归一化与 `_build_filters_and_metadata`），随后读出：
`memory.llm.calls[-1]["messages"]`（system+user 两条消息的确切文本）、
`SELECT role,content,name,created_at FROM messages WHERE session_scope=?`
（真实持久化的原始消息）、`SELECT * FROM history`（ADD/UPDATE/DELETE 事件）、
`memory.vector_store.inserted`（Phase 6 实际写入的向量 payload）。

## 5. 十八种角色/batch 探针逐条结果

以下 role 均指 Mem0 message 的 `"role"` 字段值（不是说话人身份，见 §6/§8 的区分）。

### 5.1 八种基础角色形状（单次 add() 调用）

| # | 输入 role 序列 | 结果 | New Messages 呈现 |
|---|---|---|---|
| 1 | user→assistant | 正常返回 `{'results': []}` | `user: ...\nassistant: ...\n` |
| 2 | user→user（连续同 role）| 正常返回，**不合并、不丢弃、不报错** | `user: I love hiking.\nuser: Also I love swimming.\n` |
| 3 | assistant→assistant（连续同 role）| 正常返回，同上 | `assistant: I recommend trail X.\nassistant: Also try trail Y.\n` |
| 4 | assistant→user（assistant 起始）| 正常返回，**无"首条必须 user"校验** | `assistant: Welcome!...\nuser: I'm Marcus.\n` |
| 5 | 单条 user | 正常返回 | `user: I just adopted a cat named Whiskers.\n` |
| 6 | 单条 assistant | 正常返回 | `assistant: I recommend reading Dune.\n` |
| 7 | user,assistant,user（奇数 3）| 正常返回，**无偶数长度校验** | 三行按序原样 |
| 7b | user,assistant,user,assistant,user（奇数 5）| 正常返回 | 五行按序原样 |
| 8a | system,user,assistant | 正常返回，**system 角色被 parse_messages 识别并保留** | `system: ...\nuser: ...\nassistant: ...\n` |
| 8b | 未知角色 "narrator",user | 正常返回，**但 narrator 那一行从 New Messages 里"消失"**（`parse_messages` 只认 system/user/assistant 三个字面量，见 §6）| 只剩 `user: I ordered a latte.\n`，narrator 行完全不出现 |

实测原文（case 2，逐字摘自 stdout，证明连续同 role 不合并）：

```text
## New Messages
user: I love hiking.
user: Also I love swimming.
```

实测原文（case 8b，逐字摘自 stdout，证明未知 role 从 New Messages 消失但仍写库）：

```text
## New Messages
user: I ordered a latte.
```
```text
--- final sqlite messages table (session_scope='run_id=probe') ---
('narrator', 'Scene: a quiet cafe.', None, '2026-07-19T...')
('user', 'I ordered a latte.', None, '2026-07-19T...')
```

结论：**core 运行期对 role 序列零校验**——不检查交替、不检查首尾、不检查奇偶长度。
唯一的角色相关差异化行为是"未知角色的消息不会出现在喂给抽取 LLM 的 New Messages
文本里，但仍会原样持久化进 messages 表"（下一次调用时会以 Last k Messages 身份重新
出现，见 5.5 Probe D）。

### 5.2 边界：缺字段、空内容

| # | 输入 | 结果 |
|---|---|---|
| 9 | `[{"content": "no role field"}]`（缺 `role`）| **硬崩溃**：`add()` 直接抛出 `KeyError: 'role'`（`parse_messages()` 用裸 `msg["role"]` bracket 访问，在 Phase 0，早于 LLM 调用）。实测 LLM **未被调用**、`messages`/`history` 两张表均**无任何写入**——异常发生在任何持久化之前。 |
| 10 | `[{"role": "user"}]`（缺 `content`）| **硬崩溃**：`KeyError: 'content'`，同样在 Phase 0、同样 LLM 未调用、同样零持久化。 |
| 11 | `[{"role": "user", "content": ""}]`（空字符串，非缺键）| **不崩溃**——空字符串是合法值：New Messages 保留一行 `user: \n`（不是被丢弃），且原样写入 messages 表 `('user', '', None, ...)`。空字符串与缺键是两种不同的失败模式。 |

结论：`parse_messages()` 对 `role`/`content` 使用裸 `dict[key]` 访问（非
`.get()`），因此**消息 dict 缺 `role` 或缺 `content` 键会在 Phase 0（`add()` 内部，
早于 LLM 调用与任何 `save_messages`）抛出未捕获的 `KeyError`，直接冒出到调用方**；
空字符串 content 则被完整保留（不是"跳过"），这与部分下游函数（`_format_
conversation_history`，见 5.5）用 truthiness 判断、会把空字符串当"跳过"处理的行为
不同，二者不能混为一谈。

### 5.3 边界：抽取失败/零抽取/正常 ADD 时，raw messages 是否同样落库

| # | 场景 | `add()` 返回值 | messages 表是否落库 |
|---|---|---|---|
| 12 | LLM 调用本身抛异常（模拟服务不可用）| `{'results': []}`（`main.py:746-748` 捕获后直接 `return []`）| **否**——该批 raw messages **完全没有** `save_messages()` 调用，实测 sqlite `messages` 表为空 |
| 12b | LLM 正常返回但内容不是合法 JSON（"not json at all"）| `{'results': []}`（`main.py:761-763` 捕获解析异常→`extracted_memories=[]`）| **是**——落入 `main.py:765-768` 的"零抽取仍保存"分支，实测 `('user', "This call's LLM returns garbage.", ...)` 确实写入 |

实测原文（case 12，证明 LLM 异常时 messages 表为空）：

```text
>>> add() call #1 returned: {'results': []}
--- final sqlite messages table (session_scope='run_id=probe') ---
--- final sqlite history table ---
```

结论：**"LLM 调用异常"与"LLM 返回但解析失败"是两种不同的持久化结局**——前者连
原始消息都不会进入 `last_messages`/历史，后者会。源码正常路径（Phase 6/7/8 之后）
与"零抽取"（`main.py:765-768`）、"全部去重"（`main.py:820-822`）两个早退分支，三处
都调用了同一个 `self.db.save_messages(messages, session_scope)`，**唯独** Phase 2 的
`try/except`（`main.py:738-748`）捕获异常后直接 `return []`、跳过了 `save_messages`。
这是源码里唯一一处"正常 ADD 路径可达但不落库原始消息"的分支。

### 5.4 batch identity：一次 add 两条 vs 两次 add 各一条

这是本卡的核心承重问题。同一 `run_id`，同样两条消息（"Message ONE." / "Message
TWO."），只改变"是一次调用送两条,还是两次调用各送一条"：

**13a（一次调用两条）**——LLM 唯一一次调用：

```text
## Last k Messages


## New Messages
user: Message ONE.
assistant: Message TWO.
```

**13b（两次调用各一条，同一 run_id）**——LLM 第一次调用：

```text
## Last k Messages


## New Messages
user: Message ONE.
```

LLM 第二次调用（**Message ONE. 从 "New Messages" 移动到了 "Last k Messages"**）：

```text
## Last k Messages
user: Message ONE.


## New Messages
assistant: Message TWO.
```

结论：**两者不是抽取语义等价**。13a 中两条消息在**同一次** LLM 调用里同时作为
"New Messages"（抽取目标，系统 prompt 明确要求"从 New Messages 提取，不要从
Existing/Recent 提取"）；13b 中 Message ONE 在第二次调用里降级为"Last k Messages"
——系统 prompt 原文对该字段的定位是"Use to resolve references and pronouns in New
Messages"（`prompts.py:521`），不是抽取来源。也就是说，**如果 benchmark 的聚合策略把
本该同批处理的两条消息拆成两次独立 `add()` 调用，第一条消息实质上从"被抽取的一等
公民"降级为"仅用于指代消解的背景"**——这不是"能不能跑"的问题，而是抽取语义
（"这条信息本身是否被当作待抽取内容"）的真实差异，五格若关心这一点必须显式决定
是否可接受（见 §10）。

### 5.5 last_k_messages 与 New Messages 的过滤规则不对称（Probe D/E）

- **Probe D**（未知角色 "narrator" 第一次调用被持久化，第二次调用是否会以
  Last k Messages 身份重新出现？）：**会**。实测第二次调用的 user payload 含
  `narrator: Scene: a quiet cafe.` 一行——即：`narrator` 这条消息在**它自己被提交
  的那次调用**里对 LLM"隐身"（`parse_messages()` 用角色白名单 {system,user,
  assistant} 过滤），但**下一次调用**里会以 Last k Messages 身份重新对 LLM
  可见（`_format_conversation_history()` 没有角色白名单，只按 truthiness 过滤
  role/content 是否非空，`prompts.py:982-992`）。同一条消息在不同轮次里"可见性"
  不一致，根因是 `parse_messages()`（白名单三角色）与 `_format_conversation_
  history()`（无白名单、只查真值）是两套不同的过滤规则。
- **Probe E**（空字符串 content 第一次调用被持久化——New Messages 里空字符串会
  保留一行，见 5.2 case 11——第二次调用的 Last k Messages 是否也保留？）：**不会**。
  实测第二次调用的 `## Last k Messages` 到 `## Recently Extracted Memories` 之间
  是纯空白（`'\n\n\n'`），完全没有对应这条空消息的行——因为 `_format_conversation_
  history()` 对空字符串走 `if role and content:` 真值过滤，直接跳过，这与
  `parse_messages()` 保留空字符串行的行为相反。

结论：**"这条消息会不会被 LLM 看到"不是这条消息的固有属性，而取决于它当前处于
New Messages 通道还是 Last k Messages 通道**——两条通道的过滤规则（角色白名单 vs
纯真值判断）互相独立、互不对称，benchmark 卡若假设"只要曾经成功 add 过就一定能在
后续检索/上下文里被抽取模型看到"是不成立的。

### 5.6 单次 add() 消息数 > 10：eviction 的 tie-break 行为（HaluMem 整 session 相关）

同一次 `save_messages()` 调用内，全部消息共享**同一个**挂钟 `created_at`
（`storage.py:263` 的 `now` 只计算一次）。用 12 条消息（"Turn number 0."…"Turn
number 11."）做一次 `add()`：

```text
--- final sqlite messages table (session_scope='run_id=probe') ---
('user', 'Turn number 0.', ...)
('assistant', 'Turn number 1.', ...)
...
('user', 'Turn number 8.', ...)
('assistant', 'Turn number 9.', ...)
```

实测**只剩 10 条（Turn 0-9），Turn 10/11 被淘汰**——按 `save_messages()` 的淘汰 SQL
（`DELETE ... WHERE session_scope=? AND id NOT IN (SELECT id FROM (SELECT id FROM
messages WHERE session_scope=? ORDER BY created_at DESC LIMIT 10))`，
`storage.py:282-291`）的字面意图，"DESC LIMIT 10"应保留"最近 10 条"；但当全部 12
条 `created_at` 完全相同时，DESC 排序对相等值的 tie-break 顺序 SQL 标准不作保证，
本次实测环境下**保留的是插入顺序靠前的 10 条（Turn 0-9），被淘汰的恰恰是本该
"最新"的 Turn 10/11**——即批内 tie-break 顺序与"保留最近"的直觉相反。后续
一次追加调用（新消息有**独立、更晚**的 `created_at`，不再与旧 10 条同 tie）：

```text
--- 14b final sqlite messages table ---
('user', 'Turn number 0.', ...) ... ('user', 'Turn number 8.', ...)
('user', 'Follow-up turn after the big batch.', ...)
```

这次正确淘汰了 tie 组里"最旧"的 Turn 9（该次是新旧不同 `created_at` 的正常比较，非
全 tie），保留 Turn 0-8 + 追加消息共 10 条。

结论：**这是一个由"同批消息共享同一挂钟时间戳"触发的真实、可复现的边界行为**，与
"消息数是否超过 10"无关，只在"单次 `add()`/`save_messages()` 批量 > 10 条"时触发；
淘汰的具体 tie-break 顺序不受 SQL 保证，本次实测观察到的是"淘汰批内插入顺序靠后的
消息"，不能假设未来 SQLite 版本/查询计划一定复现同一具体顺序，但"全 tie 时淘汰顺序
不等于时间顺序"这一结构性事实是稳固的。**这与 HaluMem 的 `session_memory_report=True`
整 session 单次 add() 路径直接相关**——真实 session 若含超过 10 turn，本次 add() 结束
后该 session_scope 下 `last_messages()` 能看到的"最近历史"不保证是该 session 真正
最后发生的那些 turn。

### 5.7 str / dict 输入归一化

- Case 15（`messages="Just a plain string turn."`）：实测归一化为单条
  `{"role":"user","content":"Just a plain string turn."}`，New Messages 呈现
  `user: Just a plain string turn.`——与 `add()` 源码 `isinstance(messages, str)`
  分支一致。
- Case 16（`messages={"role":"user","content":"Single dict input."}`）：实测归一化
  为单元素列表，New Messages 呈现 `user: Single dict input.`——与 `isinstance
  (messages, dict)` 分支一致。

两者均不受角色规则约束（str 输入固定映射为 user；dict 输入原样使用其自带 role）。

## 6. role/content 归一化管线（逐层追踪，对应卡内 §4 要求的层级图）

```text
Memory.add(messages, run_id=...)
  │
  ├─ str        -> [{"role":"user","content":messages}]        (实测 case 15)
  ├─ dict       -> [messages]                                   (实测 case 16)
  ├─ list[dict] -> 原样透传（唯一要求：是 list，元素不强制校验形状）
  │
  ├─ parse_vision_messages(messages, ...)
  │     content 是 list 或 {"type":"image_url",...} dict 时才转成图片描述；
  │     本框架与三条"官方"入口的 content 恒为纯字符串（caption 已在上游拼成文本，
  │     见 §8），故该分支在所有已知入口下均为 no-op passthrough（`utils.py:170-197`
  │     的 else 分支）。
  │
  ▼ _add_to_vector_store(messages, metadata, filters, infer=True)
  │
  ├─ Phase 0: session_scope = _build_session_scope(filters)         （见 §7 namespace）
  │           last_messages = db.get_last_messages(session_scope, limit=10)
  │           parsed_messages = parse_messages(messages)   ← 逐条 msg["role"]/msg["content"]
  │             裸 bracket 访问：role∈{system,user,assistant} 才输出该行；
  │             role 不在白名单则**该行不输出但不报错**；role/content 键缺失则 KeyError
  │             （实测 case 8b / 9 / 10）
  │
  ├─ Phase 1: existing_memories = vector_store.search(parsed_messages, filters)
  │           （只取 id/text，不含任何时间字段，见 §7）
  │
  ├─ Phase 2: is_agent_scoped = bool(filters.get("agent_id")) and not filters.get("user_id")
  │             system_prompt = ADDITIVE_EXTRACTION_PROMPT (+AGENT_CONTEXT_SUFFIX if 上式为真)
  │             user_prompt = generate_additive_extraction_prompt(
  │                 existing_memories=existing_memories,
  │                 new_messages=parsed_messages,      # 已经是 parse_messages() 的字符串
  │                 last_k_messages=last_messages,      # db 读出的 list[dict]
  │                 custom_instructions=prompt or self.custom_instructions,
  │             )  # 注意：summary/recently_extracted_memories/timestamp/current_date
  │             #      四个形参本调用点**全部未传**，见 §7
  │             llm.generate_response(messages=[{"role":"system",...},{"role":"user",...}])
  │             —— 到达 LLM 的固定是 2 条消息（system+user），原始逐 turn 的 role 序列
  │                只以纯文本形式嵌在 user 消息内部，从未作为独立 chat-message 传给 LLM
  │
  ├─ 解析失败/异常 -> 见 §5.3（是否 save_messages 的分叉点）
  │
  ├─ Phase 3-7: 逐条 hash 去重、embed、insert、history(event="ADD")、entity_store 关联
  │
  └─ Phase 8: db.save_messages(messages, session_scope)   ← 原始 messages（未过滤角色）
              return {"results": [...]}
```

承重问题回答：

- **是否校验 role 交替/首尾/奇偶**：否，源码与 18 组实测均确认零校验。
- **raw roles 是否直接交给 LLM**：否，先经 `parse_messages()` 拍平成一段
  `"role: content\n"` 文本，塞进单条 `{"role":"user",...}` 消息的 content 里；LLM
  收到的 chat-message 列表恒为 `[system, user]` 两条，不随原始 turn 数变化。
- **连续同 role 是否被合并/丢弃/交换/只留最后一条**：均否，逐条原样保留、原样呈现
  （§5.1 case 2/3 实测）。
- **`last_messages(limit=10)` 是否让上一批进入下一批上下文**：是，且这正是 §5.4 的
  batch identity 差异来源；一批两条与两批各一条**不等价**，差异体现在"该消息处于
  New Messages 通道还是 Last k Messages 通道"，不是"能不能跑"的问题。
- **空 content/未知 role/缺 role-content 的确切行为**：空 content 保留但在 Last k
  Messages 侧被过滤（§5.5 Probe E）；未知 role 在 New Messages 侧被过滤但仍持久化、
  且会在 Last k Messages 侧重新可见（§5.5 Probe D）；缺 `role`/`content` 键是硬
  `KeyError`，在 LLM 调用与任何持久化之前（§5.2 case 9/10）。
- **抽取失败/零 memory/正常 ADD 三种情形，raw messages 是否同 scope 保存**：不完全
  一致——LLM 调用异常时不保存（§5.3 case 12），LLM 返回但解析失败/零抽取/正常 ADD
  三种情形下均保存（§5.3 case 12b 及源码 Phase 2/5 两处早退分支）。

## 7. namespace 图 + time 可见链

### 7.1 namespace

```text
Memory.add(user_id=?, agent_id=?, run_id=?, metadata=?)
        │
        ▼
_build_filters_and_metadata(user_id, agent_id, run_id, input_metadata)
        │  校验+trim 每个非空 id，全部塞进同一对字典（不是分裂成多次调用）：
        ├─ base_metadata_template  = {**input_metadata, [user_id?], [agent_id?], [run_id?]}
        └─ effective_query_filters = {[user_id?], [agent_id?], [run_id?], [actor_id?]}
        │  （至少需要三者之一，否则 raise Mem0ValidationError）
        ▼
Phase 6 insert：mem_metadata = deepcopy(base_metadata_template) + data/hash/created_at/...
        ▼ 一条记录的 payload 同时携带全部已提供的 id 字段（实测 case 18：
          {'user_id': 'userA', 'run_id': 'runB', 'data': ..., ...} 单条 payload 里两个键并存）
        ▼
search(filters={...}) -> Qdrant _create_filter()：
  普通 key:value（非 AND/OR/NOT 包裹）一律进入 `must=[...]`，即**逻辑 AND**
  （vector_stores/qdrant.py:298-372，`_build_field_condition` 对纯量值走
  `else: condition=...; must.append(condition)`）
```

- **同一 add 是否允许同时给多个实体 id**：允许，且它们进入的是**同一条**
  `base_metadata_template`/`effective_query_filters`，不是分裂成两次独立调用（实测
  case 18：`user_id="userA", run_id="runB"` 一次 `add()`，落库 payload 同时含两个
  键）。
- **多个 id 是"两个独立记忆库"还是"一个复合 scope"**：**一个复合 scope**——
  Qdrant 层面纯量 filter 走 `must`（AND）语义，一条记录必须同时匹配所有已提供的
  id 才会被检索命中；这是当前 vector store（Qdrant，`to_manifest()` 中
  `"vector_store_provider": "qdrant"`）的确认行为，未验证其他 vector store 后端是否
  同构（本卡范围未要求验证）。
- **legacy `speaker_a_user_id`/`speaker_b_user_id` 是两次独立 add/search 还是一次
  调用传两个 user id**：**两次独立**——`add.py:94-95`（各自 `delete_all`）、
  `add.py:118-130`（各自开线程各自 `add_memory`）、`search.py:91-96`（各自
  `search_memory`），从未在同一次 Mem0 API 调用里同时传两个 user id；`messages`/
  `messages_reverse` 存在的原因见 §2 分层结论——用两个独立记忆库 + 角色互换 +
  custom_instructions"只抽 user"，构造"each 说话人只记自己第一人称视角"的效果。
- **当前 memory-benchmarks LoCoMo 的单 `user_id` 与本框架单 `run_id` 是
  `CONFIG_EQUIVALENT`、`BEHAVIOR_VARIANT` 还是无法判定**：**CONFIG_EQUIVALENT**。
  理由（不凭名称判断，逐条给出机制证据）：
  1. `_build_filters_and_metadata` 对三种 id 的校验/合并逻辑完全对称（同一段代码，
     只是键名不同，`main.py:282-299`）；
  2. `search()`/`_create_filter()` 对不同 key 名的纯量过滤走同一条 `must.append`
     路径，无按 key 名分支的特殊逻辑；
  3. 全文 grep `filters.get("user_id")`/`"agent_id"`/`"run_id")` 在可达的同步
     `add`/`_add_to_vector_store` 范围内**只有一处**差异分支——`is_agent_scoped =
     bool(filters.get("agent_id")) and not filters.get("user_id")`（`main.py:724`）
     ——该分支只关心 `agent_id`/`user_id` 二者，**从不读 `run_id`**；本框架从不设
     `agent_id`，当前产品 harness 从不设 `agent_id`，故双方在这一唯一差异分支上表现
     均为 `False`，无实际差异（实测 case 17a：仅 `run_id` → suffix 不出现；系统提示
     长度基线一致）；
  4. 会话历史 `session_scope` 字符串按排序后的 key 名拼接
     （`_build_session_scope`：`sorted(["user_id","agent_id","run_id"])` 决定顺序），
     因此 `run_id=X` 与 `user_id=X` 天然落在不同 `session_scope` 字符串下，互不冲突、
     互不覆盖，纯粹是命名空间隔离更彻底，不引入算法差异。
  唯一已知的边界（不影响此结论，仅作诚实披露）：legacy 入口用到的
  `mem0_client.get_user_profile(user_id)`（`locomo/run.py:885`，云端/REST 专属高阶
  功能）在 API 语义上专属 `user_id`，本框架与当前产品 harness 均未使用该功能，
  local `Memory` 类也不存在对应方法（全文未见 `get_user_profile` 定义于
  `mem0/memory/main.py`），不构成对 add/search 核心契约"CONFIG_EQUIVALENT"判断的
  反证。
- **assistant 内容何时触发 agent-memory extraction**：**只取决于 `agent_id`
  是否存在（且 `user_id` 缺失），与消息里是否出现 assistant 角色内容完全无关**。
  三组实测（17a/17b/17c，构造完全相同的 `[user,assistant]` 两条消息，只改 id
  kwargs）：
  - 17a：仅 `run_id`（无 `agent_id`）→ system prompt 不含 "Entity Context"，长度
    33653 字符（基线）。
  - 17b：仅 `agent_id`（无 `user_id`）→ system prompt **包含** "Entity Context"，
    长度增至 34216 字符（恰好等于基线 + `AGENT_CONTEXT_SUFFIX` 文本长度）。
  - 17c：`agent_id` 与 `user_id` 同时存在 → system prompt 不含 "Entity Context"
    （与 `bool(agent_id) and not user_id` 的布尔逻辑完全吻合）。
  vendored 源码里另有一个同名方法 `_should_use_agent_memory_extraction`
  （`main.py:552-571`，文档字符串写"agent_id 存在且消息含 assistant 角色→True"）
  ——**该方法是死代码**，在同步 `Memory` 类体内除自身定义外零调用点（`add()`/
  `_add_to_vector_store()` 均不引用它），真正生效的是 `main.py:724` 那行内联判断，
  与该方法文档字符串描述的条件不同（真正生效的条件不含"是否含 assistant 角色"这一
  项）。本框架与三条"官方"入口均从不设 `agent_id`，故 `is_agent_scoped` 对所有已知
  入口恒为 `False`。

### 7.2 time 可见链

三层的严格区分（不得混用）：

| 层 | 是否有 `timestamp` 概念 | 抽取 LLM 是否可见 |
|---|---|---|
| benchmark harness REST `Mem0Client.add(timestamp=...)` | 有（unix epoch 整数，server 端参数）| **不适用**——本框架从不经过这条 REST 路径，local `Memory.add()` 根本没有同名参数，二者是两个不同的产品 surface，不能"因为 REST client 接受就假设本地 core 也接受"（本卡已核实 `main.py:573-583` 的 `add()` 签名不含 `timestamp` 形参）|
| 本地 core `Memory.add()` Python 签名 | **无**（`user_id/agent_id/run_id/metadata/infer/memory_type/prompt`，无 `timestamp`）| — |
| 本地 core 内部 `generate_additive_extraction_prompt()` 的 `timestamp`/`current_date` 形参 | **有**（决定 prompt 里的 Observation Date/Current Date），但 `_add_to_vector_store()` 唯一调用点（`main.py:731-736`）**从未传入**这两个形参，也未传 `summary`/`recently_extracted_memories` | 因未传参，`_resolve_dates(None, None)` 恒返回**当前真实挂钟日期**（`configs/prompts.py:1007-1013`，`datetime.now(timezone.utc).date().isoformat()`）；实测全部 18+ 组探针的 `## Observation Date`/`## Current Date` 均输出运行时的真实当天日期（本次实测环境为 `2026-07-19`，与本会话系统日期一致），从未反映任何 benchmark 时间 |
| 框架 content 内嵌文本（`_turn_to_message()` 的 `[Turn time: …]`/`[Session time: …]` 头）| 有 | **可见**——这段文本是 `turn.content` 的一部分，经 `parse_messages()` 原样进入 "## New Messages"；实测 Probe B 直接证实字符串 `'[Turn time: 1:57 pm on 8 May, 2023]'` 逐字出现在 user payload 里 |
| 框架 metadata（`_native_turn_metadata()` 写入的 `turn_time`/`session_time` 键）| 有 | **不可见**——Phase 2 的 `existing_memories` 只含 `id`/`text`（`main.py:719-721`，从 `mem.payload.get("data","")` 取，不含时间字段），`last_k_messages`只含 role/content/name/created_at（`storage.py:298-324`，且 `_format_conversation_history()` 只读 `role`/`message`or`content`，`prompts.py:982-992`），两处均不读 `turn_time`/`session_time`；实测 Probe A 直接证实把 `session_time`/`turn_time` 只放进 `metadata=` 而不放进 content 时，两个日期字符串**完全不出现**在抽取 prompt 的任何位置（逐字符串搜索为 `False`）|
| 框架 `prompt=` 覆盖（`_observation_time_prompt()`，仅在 `session_time` 非空时生成）| 有 | **可见，且验证了投放位置**——实测直接调用 adapter 真实函数
  `Mem0._observation_time_prompt("1:56 pm on 8 May, 2023")` 得到的原文："The
  observation date and time for this message is '1:56 pm on 8 May, 2023'. Resolve
  relative time expressions such as 'yesterday', 'today', and 'last week' only
  against this observation time, even if another current or observation date
  appears elsewhere in the extraction prompt."——通过 `add(prompt=...)` 送入后，
  逐字出现在 `## Custom Instructions` 段落，且该段落物理位置**在** `## Observation
  Date`（索引 191）与 `## Current Date`（索引 223）**之后**（索引 251），即"覆盖
  指令"在文本顺序上晚于、可以引用/纠正前面两个错误日期段落；但 `## Observation
  Date` 段落本身的文本值**依旧是真实挂钟日期，不会被替换或删除**——是否真的服从
  这条自然语言覆盖指令属于 LLM 遵循度问题，本卡未调用真实 LLM，不作结论。|

回答卡内三条禁止项：

- **未把 metadata 被持久化误判为"LLM 能看见"**：Probe A 直接反证——`turn_time`/
  `session_time` 写进 metadata 后，抽取 prompt 里逐字搜索不到这两个值。
- **未把 REST client 接受 timestamp 误判为本地 core 也接受**：已核实本地
  `Memory.add()` 签名及其唯一下游 `generate_additive_extraction_prompt()` 调用点均不
  接收/不传递 `timestamp`；REST client 的 `timestamp=` 是完全独立的 server 端参数
  （`Mem0Client._add_oss`，`mem0_client.py:141-143`，进 HTTP payload，不进本地
  Python 函数调用栈）。
- **区分"能不能持久化"与"抽取 LLM 能不能看见"**：`_native_turn_metadata()` 写的
  `turn_time`/`session_time` 会被持久化进向量 payload、并在 §7 之外的 retrieve 侧
  被提升为 reader 的 `created_at` 槽（`mem0_adapter.py:1650-1701` `_normalize_search_
  results()`，专供 answer-prompt reader 使用），但这条通道与"抽取时 LLM 能否看见
  时间"是两回事——检索侧的时间提升发生在**记忆已经生成之后**，不会倒果为因地影响
  抽取阶段的 Observation Date。

## 8. speaker / image 语义（仅查 core 语义）

- **具名说话人前缀是否是当前/legacy 两条官方 LoCoMo 路径的共同语义**：**是**。
  - 当前 `memory-benchmarks/benchmarks/locomo/run.py:186`：
    `messages.append({"role": role, "content": f"{speaker}: {text}"})`
  - legacy `evaluation/src/memzero/add.py:109,112`：
    `f"{speaker_a}: {chat['text']}"` / `f"{speaker_b}: {chat['text']}"`
  - 本框架 `mem0_adapter.py:1481`：
    `f"{prefix}{turn.speaker}: {' '.join(content_parts)}"`
  三者用的都是 `"{说话人}: {正文}"` 前缀约定；LongMemEval 当前入口是唯一例外
  （`longmemeval/run.py:319` 原样透传 `{"role":t["role"],"content":t["content"]}`，
  不加具名前缀）——但卡内此问只问"两条官方 LoCoMo 路径"，不含 LongMemEval，故不
  影响此结论；LongMemEval 差异仅作背景记录，供后续 LongMemEval 差量卡参考。
- **当前 phased prompt 对 assistant 侧具名说话人 fact 的规则**：`ADDITIVE_
  EXTRACTION_PROMPT` 有专门条款（`prompts.py:572`）："From assistant messages
  (ONLY when genuinely new): ... Personal facts, experiences, and details shared
  by named speakers — in multi-speaker conversations, the 'assistant' role may
  represent a real person sharing their own life ... Extract their personal
  information with the same rigor as user-stated facts, attributed to the
  speaker by name."，并配有完整的 few-shot 示例（Example 12，`prompts.py:886-904`：
  John=user 角色、Maria=具名 assistant 角色，均被要求按说话人姓名各自抽取），
  `attributed_to` 字段（`"user"`或`"assistant"`）标记原始角色，与说话人姓名是两个
  独立维度。这是**当前**单一 phased 抽取器的通用规则，不因数据来自哪个 benchmark
  而不同；本卡不代 LoCoMo 卡裁 caption renderer 的具体实现，仅确认 core prompt 层面
  确有这条规则、且该规则不依赖任何特殊的角色交替假设。
- **图片/caption**：`parse_vision_messages()` 只对 `content` 是 `list` 或
  `{"type":"image_url",...}` dict 的消息做真正的视觉处理（`utils.py:170-197`）；
  本框架（`_turn_to_message` 把 `image.caption` 文本拼进 `content_parts`，
  `mem0_adapter.py:1466-1471`）、当前 LoCoMo harness（`session_to_chunks()` 把
  `blip_caption`/`query` 拼成 `[Sharing image - query: ... The image shows: ...]`
  文本，`locomo/run.py:172-182`）两条入口的 `content` 恒为**纯字符串**，从未构造
  `list`/`image_url` 形状——即 Mem0 结构化视觉分支在本框架与当前 LoCoMo 入口下从未
  被触发，图片始终以"文本内嵌 caption"约定传递。`ADDITIVE_EXTRACTION_PROMPT` 也确
  有对应的纯文本指引段落"Shared Photos and Images"（`prompts.py:597-603`），专门
  说明如何从 `"[Shared photo: ...]"` 风格文本里抽取事实——即 core 对"图片"的支持
  本质上是"提示词层面认识某种文本约定"，不是代码层面的结构化图片处理。此发现只是
  core 语义确认，不替 LoCoMo/BEAM/MemBench 任何一张 benchmark 卡裁定各自 caption
  renderer 的具体格式是否与此约定吻合。

## 9. 明确限制（供五张 benchmark 卡与后续实现参考）

1. 消息 dict 缺 `role` 或缺 `content` 键会导致 `add()` 抛出未捕获 `KeyError`，发生在
   任何 LLM 调用/持久化之前；任何 benchmark adapter 在把 turn 转成 Mem0 message 前，
   必须保证这两个键始终存在（哪怕值为空字符串）。
2. LLM 调用异常（非解析失败）会导致该批原始消息**完全不落库**——不进
   `messages` 表、不影响后续 `last_k_messages`。这是一个静默的历史丢失点，若某个
   benchmark 卡未来要求"重试后必须保证原始消息不丢"，需要在 adapter 层面另加保护，
   不能假设 Mem0 core 自己会保底保存。
3. 单次 `add()`/`save_messages()` 批量 > 10 条时，10 条上限淘汰的 tie-break 顺序
   在同批全部消息共享同一挂钟 `created_at` 时不受 SQL 保证为"保留最新"（本次实测
   反而保留批内靠前的 10 条）；HaluMem `session_memory_report=True` 整 session 单次
   add() 若 session turn 数 > 10，需知晓这一行为，不能假设 `last_messages()` 总能
   看到该 session 最后发生的内容。
4. "## Recently Extracted Memories" 与 "## Summary" 两个 prompt 段落在
   `_add_to_vector_store()` 当前唯一调用点下**恒为空**（`[]`/空字符串）——这不是
   探针构造缺陷，是源码调用点从未传 `recently_extracted_memories=`/`summary=`
   两个形参（`main.py:731-736`）；系统提示文档字符串描述"Recently Extracted
   Memories...primary deduplication reference"，但实际去重只依赖 `existing_
   memories`（向量检索结果）。若未来有 benchmark/method 层面的去重诉求依赖这两个
   字段，需知道它们目前是死参数。
5. Observation Date/Current Date 两个 prompt 字段在当前调用形态下恒等于**运行时
   真实挂钟日期**，与任何 benchmark/turn/session 时间无关；唯一让抽取 LLM 看到
   benchmark 时间的两条通道是（a）content 内嵌文本头、（b）`prompt=`
   custom_instructions 覆盖——两者都已被 `mem0_adapter.py` 现有实现使用，本卡确认
   其到达 LLM 的具体位置符合预期，但"是否被 LLM 正确遵循"不属于结构契约范畴，
   未验证。
6. 三条"官方"入口分属三种不同 product surface（本地 core / 自托管 REST /
   云端 SDK），彼此的 namespace 形状、时间参数签名、custom_instructions 语义均不
   相同，不能把其中任何一条的行为默认当作另外两条的"官方参照"；尤其 legacy 路径的
   "双 namespace + role 互换 + user-only 抽取"依赖 custom_instructions 对云端 LLM
   的遵循程度，在本地 core 结构层面没有对应的强制机制。
7. 本卡的复合 namespace 结论（AND 语义）仅针对当前配置的 Qdrant 后端验证；未验证
   其他 vector store provider 是否同构（配置层面当前 5×10 主 smoke 固定 Qdrant，
   非本卡待办）。

## 10. 给五张 benchmark 卡的契约输入

1. 五格现有 `consume_granularity`（turn/pair/session）投递给 `Memory.add()`
   的任何 role 序列都不会被拒绝或改写；不需要为"保证严格交替"调整聚合逻辑，也
   不需要为"是否 user 起始"加保护。
2. 连续同 role（同一批或跨批同说话人连续出现）不会被 core 合并/丢弃/交换；这在
   语义上是否合理是 benchmark 数据本身的属性，不是 core 强加的限制。
3. 若某格把本该同批的消息拆成多次独立 `add()` 调用（而非一次调用内多条），跨次
   调用之间会通过 `last_messages(limit=10)` 产生"上一批渗入下一批 Last k Messages
   上下文"的非等价效应（§5.4）——第一条消息从"抽取目标"降级为"指代消解背景"。
   各卡若关心"同批 vs 分批"的语义差异，必须在各自卡内显式讨论是否可接受，不能
   假设"反正最后都送进同一次 add() 就行"或"反正分批也语义相同"。
4. HaluMem 整 session 单次 add()（`session_memory_report=True`）在 session turn 数
   > 10 时，会立刻触发 §5.6 描述的 tie-break 淘汰行为；若 HaluMem 卡要对
   "session 内最近消息可见性"做任何假设，必须知晓这一非直觉行为。
5. 五格若只把 turn_time/session_time 写进 adapter 的 metadata（不经过
   `_turn_to_message()` 的内容头或 `prompt=` 覆盖两条既有通道），抽取 LLM 完全
   看不到，Observation Date 会静默退化成运行时真实挂钟日期。这不是新契约，是复核
   确认现有 `_turn_to_message`/`_observation_time_prompt` 两条通道是唯一生效路径，
   五格不需要、也不应该新造第三条时间通道。
6. namespace：五格目前都只使用 `run_id`（不引入 `user_id`/`agent_id`），这在 core
   算法/隔离层面与改用 `user_id` 是 `CONFIG_EQUIVALENT`（§7.1），不构成迁移的技术
   阻碍，但目前没有需要迁移的理由；改用 `agent_id` 则会触发 `AGENT_CONTEXT_SUFFIX`
   （系统提示措辞变化），且与消息中是否出现 assistant 角色内容无关，五格若未来
   考虑引入 `agent_id` 需先評估这一措辞变化是否影响抽取质量（本卡不判断质量，只
   确认触发条件）。
7. 具名说话人前缀（`"{speaker}: {content}"`）是当前 adapter 与两条官方 LoCoMo
   路径的共同约定；`ADDITIVE_EXTRACTION_PROMPT` 有专门的"assistant 角色下的具名
   说话人"抽取规则（Example 12），LoCoMo/BEAM/MemBench 若沿用具名前缀约定，不需要
   额外 prompt 工程"教会" Mem0 处理多说话人 assistant 角色；LongMemEval 当前官方
   入口不use 具名前缀（原样透传 role/content），若 LongMemEval 卡决定引入具名前缀
   需自行论证依据，本卡不代为裁定。
8. 图片/caption：core 没有会被本框架任何入口触发的结构化图片处理路径（vision
   分支只对 list/dict content 生效，所有已知入口的 content 都是纯字符串）；本框架、
   当前产品 harness（LoCoMo）、legacy harness 全部使用"文本内嵌 caption/photo tag"
   约定，`ADDITIVE_EXTRACTION_PROMPT` 也有对应的文字指引。MemBench/LoCoMo/BEAM
   若沿用文本内嵌 caption，不需要额外验证 vision 代码路径是否被触发（结构上不会）。

## 11. 未知项 / 明确排除

- upstream drift（`build_mem0_source_identity()` 当前 SHA-256 是否仍等于 frozen-v1
  记录值）——既有卡已声明的独立待办，本卡未重新计算。
- `AsyncMemory`、`mem0.client`（`MemoryClient`/`AsyncMemoryClient`）、
  `mem0/server/` 内部实现——未逐行审查，只确认 adapter 不引用（沿用既有 grep 结论，
  未重复执行）。legacy 入口虽然**使用** `MemoryClient`，但本卡只读了调用方
  （`evaluation/src/memzero/{add,search}.py`）如何构造请求，未读 `mem0/client/
  main.py` 内部对这些请求的服务端等效实现（该实现本身在我们的 vendored 快照里也
  只是客户端 SDK，真正的云端服务端代码本来就不在 vendored 范围内）。
- `Mem0Client` OSS 模式对应的自托管 server（`mem0/server/`）如何在服务端把
  REST payload 的 `timestamp` 字段接入到本地 `Memory` 算法——未审查，本卡只确认
  本地 `Memory.add()`/`generate_additive_extraction_prompt()` 的 Python 签名/调用点
  不接收该参数，不代表服务端没有另外的桥接逻辑（不影响本卡结论，因为本框架从不
  经过这条 server 路径）。
- custom_instructions（含 `_observation_time_prompt()` 覆盖文本、legacy 的
  "只抽 user"指令）是否被真实 LLM 正确遵循——结构上确认了文本到达 LLM 的位置，
  但遵循程度需要真实 LLM 调用才能验证，卡内禁止用输出质量证明结构契约，本卡不
  作结论。
- 其他 vector store provider（非 Qdrant）的 filter AND/OR 语义是否与 §7.1 一致——
  未验证，当前 5×10 主 smoke 固定使用 Qdrant，不在本卡待办范围。

## 12. 停工条件核对

卡内 §6 列出的四条停工触发条件逐条核对：current source 与 §2 无冲突（§3）；全程
零网络零真实 API（§4.0 已关闭遥测，全部探针 hermetic）；未修改任何算法 core（只读
vendored 源码 + 独立 hermetic 脚本，从未 `Edit`/`Write` `third_party/` 或 `src/`
任何文件）；未写允许清单外文件（只新增本 note 一个文件）。全部 20 组探针均在
20 分钟量级的 hermetic 脚本内跑通并得到确定性输出，无需把任何动态点标记为
pending。故本次未触发停工，note 写完即按卡内 §7 自检并提交。

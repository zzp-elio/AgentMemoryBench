# Method 接入轻量化与失败重试干净状态设计

日期：2026-06-24

## 背景

当前 conversation + QA 主线已经收敛到 retrieve-first 协议：

```text
BaseMemoryProvider.add(conversation)
BaseMemoryProvider.retrieve(question) -> AnswerPromptResult.prompt_messages
framework answer reader -> answer
evaluator -> score
```

但项目中同时存在两类完全不同的接入对象：

1. **框架开发者维护的内置 method**：Mem0、MemoryOS、A-Mem、LightMem。
   这类 method 需要官方参数复现、TOML profile、source identity、内部 LLM/embedding
   配置、method state 管理和深度 efficiency 插桩。
2. **普通用户带来的自定义 method**：用户只希望把自己的 memory algorithm 接进来，
   在框架已有 benchmark 上跑实验并与内置 method 对比。

之前的文档和代码叙述把这两类接入深度混在一起，导致“新 method 接入流程”看起来必须
实现 TOML、registry factory、source identity、efficiency inventory 和内部状态恢复。这对
普通用户过重，也不符合当前项目希望降低接入门槛的目标。

同时，当前 conversation-level resume 还有一个必须明确的安全语义：如果某个 conversation
在 `add()` 过程中失败，但第三方 method 已经写入了部分记忆，后续 `--retry-failed` 直接
重新 `add()` 会造成重复记忆或脏状态。例如 Mem0 在 Qdrant 中已经写入前 30 条 memory，
重试时从第 1 条重新写，可能得到重复的前 30 条。该问题必须作为 method 接入轻量化任务的
一部分一起处理，因为它直接关系到用户 method 的正确性和框架可信度。

## 目标

- 把用户自定义 method 的必需接入面压缩到 `BaseMemoryProvider`。
- 明确区分“用户轻量接入路径”和“内置 method 深度接入路径”。
- 把并行、resume、artifact、日志、answer LLM、judge、CLI 参数校验等框架能力尽量从
  method adapter 中拿出来。
- 明确用户自定义 method 的并行策略：默认单 worker；只有用户显式传
  `--allow-unsafe-custom-parallel` 时才允许 `workers > 1`，且框架不证明用户后端并发安全。
- 明确 CLI 与 TOML 的边界：CLI 管框架运行参数，TOML 管内置白盒 method 的内部复现参数。
- 明确 outputs 边界：框架只承诺记录自己能捕捉的数据；用户黑盒 method 的外部 memory
  backend 不默认由框架管理。
- 修正 `--retry-failed` 的语义：失败 conversation 需要重新 add 时，必须先保证干净状态；
  不能保证时直接报错，不允许在可能污染的 state 上继续运行。

## 非目标

- 本任务不新增新的 benchmark task family。
- 本任务不恢复 retrieval recall。
- 本任务不把用户黑盒 method 的内部 token、内部 LLM 调用、内部 embedding 调用强制纳入
  精确观测。
- 本任务不要求用户 method 必须支持 TOML。
- 本任务不要求用户 method 必须支持 internal LLM provider 统一配置。
- 本任务不立即删除所有历史接口；删除必须等 retrieve-first 主路径和测试完全稳定后执行。

## 角色边界

### 框架用户

框架用户是带着自己 method 来跑 benchmark 的人。对这类用户，推荐接入面应是：

```python
class MyMethod(BaseMemoryProvider):
    def add(self, conversation: Conversation) -> AddResult:
        ...

    def retrieve(self, question: Question) -> AnswerPromptResult:
        ...
```

用户 method 的必需责任：

- 写入公开 `Conversation`，不得依赖 gold answer、evidence、judge label 等私有字段。
- 根据公开 `Question` 返回完整 `AnswerPromptResult.prompt_messages`。
- 保证同一个 `conversation_id` 的记忆不会污染其他 conversation。
- 返回合法 `AddResult` 和 `AnswerPromptResult`。
- 如果用户希望使用 `--retry-failed` 重新 add 失败 conversation，必须让框架能够确认干净
  retry；否则 retry 应 fail closed。

用户 method 的非必需责任：

- 不需要实现 answer LLM 调用。
- 不需要实现 evaluator。
- 不需要实现 Rich 进度条。
- 不需要实现 framework artifact 写入。
- 不需要实现通用并行调度。自定义 method 默认单 worker；如用户主动开启 unsafe parallel，
  必须自行保证外部存储、namespace 和检索隔离安全。
- 不需要实现 source identity。
- 不需要实现内部 efficiency 插桩。
- 不需要写 TOML，除非用户自己希望通过我们的 CLI 工厂加载参数。

### 用户 method 构造函数与软契约

第一版用户自定义 method 采用无参数构造：

```python
method = MyMethod()
```

框架不向用户 method 构造函数传入 `state_dir`、`run_id`、`worker_id`、`api_key`、
logger、observer 或 runtime context。这样做的目的是把用户接入门槛降到最低：用户只需要
实现算法入口，不需要先理解 AgentMemoryBench 的 outputs 目录、manifest、worker 调度和
内部观测系统。

如果用户 method 需要内部参数，应由用户自己的代码管理，例如：

- 在 method 内部读取自己的 `.env`。
- 读取用户自己的 yaml/json/toml。
- 连接用户自己的数据库、向量库或远程 memory service。
- 使用用户自己代码里的默认参数。

因此，第一版用户接入依赖的是软契约而不是框架强接管：

- 用户必须让无参构造后的对象能正常运行。
- 用户必须自己保证 `conversation_id` 级记忆隔离。
- 如果用户希望跨进程 / 跨命令 resume，必须让无参构造后的对象能重新连接到同一份状态。
- 如果用户开启 `--allow-unsafe-custom-parallel`，必须自己保证多 worker、多进程、多 run
  不污染同一份状态。
- 如果用户希望安全重试 ingest 阶段失败的 conversation，必须提供
  `reset_conversation(conversation_id)`、attempt namespace 或等价的清理策略。

未来可以增加高级可选能力，例如 `from_context(MethodRuntimeContext)`，由框架传入
`storage_root`、`run_id`、`worker_id` 和 observer。但这不是第一版用户接入的必需项，也
不能写入最小接入教程。

### 框架开发者

框架开发者是维护 AgentMemoryBench 内置能力的人。我们对内置 method 可以做更深集成：

- TOML profile 和强类型 config。
- 官方参数、prompt、embedding、LLM、top-k、compression 等复现配置。
- source identity 和 wrapper identity。
- 内部 LLM/embedding token observation。
- method state 存储在标准 outputs 目录。
- 失败恢复、清理、状态加载的 method-specific 实现。

这条路径服务于“内置 method 可复现”，不是普通用户接入的最低要求。

## CLI 与 TOML 边界

### CLI 管框架运行参数

这些参数属于框架运行时控制，应通过 CLI 传递，并进入 run manifest 或 run control metadata：

- `method`
- `benchmark`
- `variant`
- `run-id`
- `workers`
- `resume`
- `retry-failed`
- `conversation-budget`
- smoke 下的 `conversations`
- smoke 下的 `rounds`
- smoke 下的 `questions-per-conversation`
- `allow-api`
- `allow-unsafe-custom-parallel`
- evaluator / judge workers
- metric 或 evaluator 选择

这类参数不应要求用户写 TOML。

## 用户自定义 method 并行策略

### 默认策略

用户自定义 method 第一版默认单 worker：

```text
custom method + workers=1 -> 允许
custom method + workers>1 且无显式确认 -> 报错
```

如果用户要让框架对自定义 method 开启 conversation-level 并行，必须显式传：

```bash
--workers 4 --allow-unsafe-custom-parallel
```

该参数只表示用户确认自己的 adapter 适合被框架创建多个实例并行运行。框架不额外要求用户
继承新的并行父类，也不尝试静态证明用户后端是否真的并发安全。

### 为什么使用显式 unsafe 开关

EverCore 和 supermemoryai-memorybench 等参考框架也支持并发/并行，但安全前提是
provider/adapter 开发者正确使用 `containerTag`、`conversation_id`、`user_id`、
`group_id`、graph id 或 namespace。框架可以传入隔离字段，可以做 checkpoint 和
artifact 合并，但无法证明：

- 用户是否真的按 `conversation_id` 过滤检索。
- 用户是否让多个 run 共用了同一个未隔离 DB、文件或远程 namespace。
- 用户本地文件或数据库是否支持多实例并发写。
- 用户是否在 retry 前清理了失败写入的部分 state。

因此，`--allow-unsafe-custom-parallel` 是显式风险确认，而不是强安全证明。

### 用户必须遵守的并行契约

当用户对自定义 method 开启 `--allow-unsafe-custom-parallel` 时，必须保证以下事项：

1. **Conversation 隔离**
   `retrieve(question)` 必须只读取 `question.conversation_id` 对应的记忆，不能跨
   conversation 检索。
2. **Run 隔离**
   同一个 method 同时跑多个 `run_id` 时，不能共用未隔离的 memory namespace、DB 或文件。
   如果使用外部服务，namespace 至少应包含 `run_id`。
3. **Benchmark 隔离**
   不同 benchmark 不能共用未隔离的 namespace。推荐 namespace 包含 `benchmark_name`。
4. **Worker 并发安全**
   `workers > 1` 时，框架可能创建多个 adapter 实例并行处理不同 conversation。如果多个
   实例连接同一个 DB 或外部服务，该后端必须支持并发写入，且用户必须通过 namespace、
   metadata filter、collection、graph id 或其他方式隔离数据。如果多个实例写普通
   JSON/pickle/text 文件，用户必须自行加锁或拆分为不同文件。
5. **失败重试安全**
   并行确认不等于 failed ingest retry 安全。如果用户希望 `--retry-failed` 可以重试
   add 阶段失败的 conversation，仍必须实现 `reset_conversation(conversation_id)`、
   使用唯一 attempt namespace，或提供等价 clean 策略。否则框架应 fail closed。
6. **外部服务命名建议**
   推荐 namespace 模板：

   ```text
   {project_or_user_prefix}:{run_id}:{benchmark}:{conversation_id}
   ```

   如果用户希望 worker 也物理隔离，可使用：

   ```text
   {project_or_user_prefix}:{run_id}:{benchmark}:worker-{worker_id}:{conversation_id}
   ```

   第一版轻量用户接口不强制传入 worker context；如果用户需要 worker id 级别隔离，应先
   保持 `workers=1`，或等待未来高级并行协议。

### 内置 method 例外

Mem0、MemoryOS、A-Mem、LightMem 属于框架开发者维护的内置 method。它们的并行支持、
state root、namespace、source identity、效率插桩和 official profile 由框架开发者负责
验证和维护；不要求用户传 `--allow-unsafe-custom-parallel`。

### TOML 管内置白盒 method 内部参数

这些参数属于我们内置 method 的实验复现配置，适合留在 TOML：

- 内部 memory LLM model、temperature、top_p、max_tokens。
- 内部 embedding model 或本地模型路径。
- method-specific top-k、threshold、compression ratio、buffer capacity。
- MemoryOS 的 STM/MTM/LPM 相关参数。
- LightMem 的 `r`、`th`、OP-update profile。
- Mem0 官方 profile、chunk size、top_k。
- A-Mem 官方 category-k、query keyword generation profile。

用户自定义 method 的内部配置由用户自己的代码管理。框架可以提供可选 factory/config
辅助，但不能把 TOML 作为用户 method 接入的强制条件。

## Outputs 边界

框架永远负责写出：

- run manifest。
- public predictions。
- private evaluator labels。
- answer prompt artifact。
- efficiency observations。
- summary。
- logs。
- checkpoint。

对内置 method，框架还负责 method state：

```text
outputs/runs/{method}/{benchmark}/{variant}/{profile}/{run_id}/method_state/
```

对用户黑盒 method，框架只提供一个推荐的 `storage_root`。如果用户 method 把 memory DB
写到外部服务、本地其他目录或远端系统，框架不会声称自己管理了这些 state。框架只能在
manifest 中记录公开可复现的信息和用户显式提供的 state pointer。

## Registry 减重方向

Registry 继续保留，但必须保持轻量。

Registry 的合理职责：

- 把 CLI 名称映射到 benchmark loader / method factory / evaluator factory。
- 声明内置 method 的 config/profile/source identity。
- 提供 run 前构造对象需要的稳定元信息。

Registry 不应承担：

- 复杂能力推理。
- 用户 method 的内部配置管理。
- 用户 method 的内部状态管理。
- 过重的 capability 矩阵。

用户轻量路径应提供更简单的加载方式，例如：

```bash
memory-benchmark predict smoke \
  --method-class my_package.my_adapter:MyMemory \
  --benchmark locomo \
  --conversations 1 \
  --rounds 20 \
  --questions-per-conversation 1
```

其中 `my_package.my_adapter:MyMemory` 表示从 Python module
`my_package.my_adapter` 中 import 类 `MyMemory`。未来也可以支持
`--method-file ./my_method.py --method-class MyMemory` 的单文件快速测试形式。具体 API
需要在实施计划中结合现有 CLI 入口落地。

## 失败与重试语义

### 当前必须明确的问题

当一个 run 跑 10 个 conversation、开 10 个 worker 时，如果其中一个 conversation 失败：

- checkpoint 中应只有一个当前 conversation 状态，按 `conversation_id` 覆盖。
- 日志中可以同时保留历史 failed event 和后续 completed event。
- prediction artifact 应按 `question_id` 去重，不应该出现同一问题两条最终预测。
- method state 物理目录可能残留失败前的部分写入，这是当前最大风险。

因此用户提出的“是否会有一个失败 conversation 和一个成功 conversation 同时存在”应拆成：

- **逻辑状态层**：不应该。`conversation_status.json` 应只有该 conversation 的当前状态。
- **事件日志层**：会保留失败和成功两段历史，这是审计需要。
- **物理 method state 层**：如果 retry 前不清理，确实可能同时存在失败写入残留和成功写入
  新数据，从而污染检索结果。

### 默认失败策略

默认策略保持保守：

- conversation 失败后标记为 `failed`。
- 后续 resume 默认跳过 failed conversation。
- 只有显式传 `--retry-failed` 才重新纳入计划。
- 单次命令中，一个 conversation 最多被尝试一次，不做失败-重试-失败循环。
- worker 可以继续处理自己分配到的其他 conversation，除非达到连续失败熔断阈值或发生
  无法归因的 catastrophic worker failure。

为了让 resume 行为可解释，框架内部应把 conversation 当前状态细分为：

```text
pending
ingesting
ingested
answering
completed
failed_ingest
failed_answer
```

这些状态的语义如下：

- `pending`：还未开始处理。
- `ingesting`：正在执行或上次中断于 `add(conversation)`。
- `ingested`：`add(conversation)` 已完成，但 question 尚未全部回答。
- `answering`：正在回答 question，或上次中断于回答阶段。
- `completed`：该 conversation 的写入和应答均已完成。
- `failed_ingest`：`add(conversation)` 阶段失败，method 内部可能已有部分写入。
- `failed_answer`：`add(conversation)` 已完成，回答阶段失败。

resume 规则：

- `completed`：跳过。
- `ingested`、`answering`、`failed_answer`：不重新 `add()`，只继续 pending questions。
- `failed_ingest`：默认跳过；只有显式 `--retry-failed` 且 clean retry preflight 通过时
  才允许重新 `add()`。
- `pending`：正常处理。

并行时，启动一次命令会先选出本次 eligible conversation 列表；如果用户设置
`--conversation-budget 5`，则成功和失败加起来最多推进 5 个 conversation。每个
conversation 在同一次命令中最多处理一次。某个 worker 的单个 conversation 失败后，框架
只标记该 conversation 失败，不应因此取消其他已经正常运行的 worker；空闲 worker 可以继续
领取本次预算内尚未开始的 conversation，但不能在同一次命令里重新领取刚失败的 conversation。

### Clean retry 规则

当 `--retry-failed` 需要重新执行 `add(conversation)` 时，框架必须满足以下规则之一：

1. **已确认无需重新 add**
   上次失败发生在 answer 阶段，且 checkpoint 明确记录 `ingested=True`。这种情况下 retry
   只回答 pending questions，不清理 memory state。

2. **框架可清理该 conversation 的 state**
   对内置 method，框架或 adapter 必须能定位该 conversation 的 state，并在 retry 前清理
   失败尝试留下的部分写入。

3. **method 声明并实现干净 retry hook**
   用户或内置 method 可以实现可选清理能力，例如 `reset_conversation(conversation_id)`。
   该能力不是普通接入的必需项，但如果用户要对失败 ingest 使用 `--retry-failed`，它就成为
   必需条件。

4. **新 attempt namespace**
   如果无法删除旧 state，但能为同一个 conversation 创建新的 attempt namespace，并确保
   后续 retrieve 只读取新 attempt namespace，则可以不用物理删除旧 state。

如果以上条件都不满足，`--retry-failed` 必须 fail closed，提示用户该 method/run 无法安全
重试失败 ingest，避免重复记忆污染。

## 设计选项

### 选项 A：要求所有 adapter 自己保证幂等 add

做法：文档要求 `add(conversation)` 必须幂等，retry 时直接调用。

优点：

- 框架最简单。

缺点：

- 对用户不友好。
- 很多第三方 memory backend 天然不是幂等写入。
- 用户很难知道自己是否真的处理了所有脏状态。
- 一旦污染，问题很隐蔽。

结论：不采用。

### 选项 B：框架统一清理失败 conversation state

做法：框架在 retry 前删除该 conversation 的 state root。

优点：

- 对用户友好。
- retry 语义清晰。

缺点：

- 只有当 state 被框架管理且按 conversation 隔离时才可靠。
- 对外部服务或全局 DB，如某些 Qdrant/user namespace，仍需要 method-specific 删除逻辑。

结论：作为内置 method 和框架托管 state 的首选。

### 选项 C：clean retry capability + fail closed

做法：轻量协议仍只要求 `add/retrieve`；但如果要重试失败 ingest，method 必须满足
框架托管清理、可选 reset hook 或 attempt namespace 之一。否则拒绝 retry。

优点：

- 普通用户接入仍然轻。
- 需要 retry 的高级能力有强约束。
- 不会在不确定状态下污染实验。
- 适配内置 method 和用户黑盒 method。

缺点：

- 需要增加一层 retry preflight 和清理/命名空间判断。

结论：推荐采用。

## 推荐设计

本任务采用“单协议、双接入深度、clean retry fail-closed”的方案。

### 主协议

主协议保持：

```python
BaseMemoryProvider.add(conversation) -> AddResult
BaseMemoryProvider.retrieve(question) -> AnswerPromptResult
```

这是用户轻量接入唯一必须实现的接口。

### 用户轻量接入路径

用户只需要：

1. 写一个 `BaseMemoryProvider` 子类。
2. 保持无参数构造函数，或不显式定义 `__init__()`。
3. 确保 `add()` 不读取私有 label。
4. 确保 `retrieve()` 返回完整 `prompt_messages`。
5. 通过 `--method-class module:ClassName` 让框架加载该类。
6. 运行框架提供的 contract tests。

`--method-class my_package.my_adapter:MyMemory` 的含义是从 Python module
`my_package.my_adapter` import 类 `MyMemory`。第一版不实现 `--method-file ./my_method.py`
作为主路径；后续如果确实需要单文件快速调试，再把它作为语法糖补上。

如果用户不实现 clean retry hook，则：

- 普通新 run 可以跑。
- completed conversation resume 可以跑。
- 默认只允许 `workers=1`。
- `workers>1` 需要显式 `--allow-unsafe-custom-parallel`，并由用户承担后端并发安全责任。
- failed conversation 默认跳过。
- 对失败 ingest 使用 `--retry-failed` 时，框架必须报错说明该 method 不支持安全重试。

### 内置 method 深度接入路径

我们维护的四个内置 method 可以继续有：

- TOML profile。
- source identity。
- official profile。
- internal LLM/embedding config。
- deep efficiency observation。
- method_state 归档。
- clean retry hook 或 attempt namespace。

这类复杂度不得写进“用户新 method 接入最小流程”。

### Resume / retry checkpoint

conversation checkpoint 至少需要区分：

- `status`: `pending | ingesting | ingested | answering | completed | failed_ingest | failed_answer`
- `stage`: `ingest | retrieve | answer | isolated_worker | unknown`
- `ingested`: `true | false | unknown`
- `attempt`: 整数，记录第几次尝试。
- `clean_retry_required`: 对 ingest 未完成失败的 conversation 为 true。
- `clean_retry_supported`: preflight 判断结果。

retry 时：

1. 读取旧状态。
2. 如果 `status != failed`，不走 retry。
3. 如果 `failed` 且 `ingested=True`，不重新 add，只补 pending questions。
4. 如果 `failed` 且 `ingested=False/unknown`，执行 clean retry preflight。
5. preflight 通过后清理 state 或切换新 attempt namespace。
6. preflight 不通过则报错，不运行该 conversation。

## 测试策略

### 用户轻量接入 contract tests

新增一个极小 fake user method，用于证明用户只实现 `add/retrieve` 就能跑：

- 可以完成 smoke prediction。
- 可以写出 standard artifacts。
- 可以走 framework answer reader。
- 默认 `workers=1` 可以运行。
- `workers>1` 且未传 `--allow-unsafe-custom-parallel` 时应明确报错。
- `workers>1` 且传 `--allow-unsafe-custom-parallel` 时，框架可以调度多个实例，但测试只验证
  artifact/checkpoint 合并正确，不声称证明用户后端并发安全。
- 可以 resume completed conversation。
- 默认不支持 failed ingest retry，传 `--retry-failed` 时应 fail closed。

### Clean retry tests

构造一个会在 `add()` 写入一部分状态后失败的 fake method：

- 第一次运行标记 conversation failed。
- 默认 resume 跳过 failed conversation。
- `--retry-failed` 且无 clean retry 支持时报错。
- 实现 reset hook 后，retry 前清理旧状态，最终不会出现重复 memory。
- 使用 attempt namespace 后，retrieve 只读最新 attempt。

### 内置 method 回归

四个内置 method 需要逐步补齐 clean retry 证明：

- Mem0：确认 user/namespace 或 Qdrant state 能按 conversation/attempt 安全隔离。
- MemoryOS：确认 conversation state dir 可删除或版本化。
- A-Mem：确认 per-conversation state dir 可删除或版本化。
- LightMem：确认 Qdrant/log state 可按 conversation/attempt 隔离。

在证明前，内置 method 的 failed ingest retry 也应 fail closed，而不是默许脏重跑。

## 实施顺序草案

1. 写清用户轻量接入文档和最小示例。
2. 增加 custom method CLI 加载设计：优先支持 `--method-class module:ClassName`，再评估
   是否支持 `--method-file`。
3. 增加 fake user method contract tests，锁定“只实现 add/retrieve 也能跑”。
4. 对 custom method 默认强制 `workers=1`；`workers>1` 必须显式
   `--allow-unsafe-custom-parallel`。
5. 梳理 registry，避免普通用户路径暴露内置 method 深度字段。
6. 增加 clean retry preflight 设计和测试。
7. 实现 failed ingest retry 的 fail-closed 逻辑。
8. 为内置 method 分别补 clean retry hook 或 attempt namespace。
9. 清理文档，把内置 method 深度集成流程从用户接入流程中拆出去。
10. 在 retrieve-first 稳定后，再单独计划删除 `BaseResumableMemorySystem`、
   `BaseMemoryRetriever` 和能力枚举的迁移期用法。

## 验收标准

- 新 method 接入文档中，用户最小必需代码不超过一个 `BaseMemoryProvider` 子类，以及
  CLI 中的 `--method-class module:ClassName`。
- 新用户不需要理解 TOML、source identity、efficiency inventory、官方 profile 才能跑通
  smoke。
- 用户自定义 method 默认单 worker；`workers>1` 必须通过
  `--allow-unsafe-custom-parallel` 显式确认风险。
- `--retry-failed` 不会在无法确认干净状态的 failed ingest conversation 上继续运行。
- `conversation_status.json` 对每个 conversation 只有一个当前状态；历史失败只保留在日志和
  event artifact 中。
- prediction artifact 仍按 `question_id` 去重，retry 成功后不会保留同一问题的重复最终预测。
- 内置 method 的深度复现能力不倒退。
- 现有 LoCoMo / LongMemEval retrieve-first smoke 路径不因轻量化改造失效。

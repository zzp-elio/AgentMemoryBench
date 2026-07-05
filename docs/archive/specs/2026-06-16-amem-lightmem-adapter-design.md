# A-Mem 与 LightMem Adapter 接入设计

更新日期：2026-06-16

## 背景

Phase G 已完成成本与效率观测底座，并已覆盖 Mem0 与 MemoryOS。当前用户明确要求暂缓
通用并行调度，优先接入 A-Mem 和 LightMem。两者都必须复用现有 conversation + QA
通用 runner、标准 artifact、resume 和效率 observation；不得新增
`<method>_<benchmark>_full.py` 这类 method × benchmark 专用 runner。

本阶段不启动全量付费实验。真实 API 只允许在 adapter 离线测试通过后，按用户明确确认的
小样本范围执行 smoke。

## 目标

- 新增 A-Mem 与 LightMem 的第一方 wrapper adapter。
- 直接调用 `third_party/methods/` 中的第三方 method 源码，不重写核心记忆算法。
- 通过 `conversation_id` 隔离每个 conversation 的 method 状态。
- 接入现有 `BaseMemorySystem.add()` 和 `BaseMemorySystem.get_answer()` 协议。
- 接入 method registry、TOML profile、source identity、model inventory 和效率 observation。
- 先打通 LoCoMo prediction 的离线/小样本路径，再扩展到 LongMemEval。

## 非目标

- 不实现通用并行调度；Phase H 顺延。
- 不启动 A-Mem/LightMem 的 full run。
- 不接入 retrieval recall 指标。
- 不恢复 PrefEval。
- 不把 official script 当作黑盒 subprocess 跑实验。
- 不为了观测而修改第三方核心算法；只有 wrapper 无法准确观测时，才允许增加默认关闭、
  可审计、行为等价的纯 observer。

## 方案比较

### 方案 A：分阶段垂直接入，先 A-Mem 后 LightMem

先实现 A-Mem adapter 的最小闭环：配置、注册、conversation 隔离、公开输入安全、
fake/offline 测试和效率 observation。A-Mem 稳定后，用同一模式实现 LightMem。

优点：每一步可验证，失败面小；A-Mem 依赖和代码路径相对轻，适合作为新 method 模板。
缺点：LightMem 接入会晚一点开始。

### 方案 B：两个 method 同时接入

同时开发 A-Mem 和 LightMem 的 wrapper、配置和注册。

优点：表面进度快。
缺点：两个第三方仓库依赖形态不同，容易把问题混在一起；不利于 TDD 和断点恢复。

### 方案 C：直接包装官方实验脚本

通过调用第三方 method 仓库中针对 LoCoMo 的作者实验脚本得到预测。

优点：短期看起来最接近官方复现。
缺点：无法可靠复用通用 runner、artifact、resume、private boundary 和 efficiency
observation；也更容易把 gold answer 传入 method。

结论：采用方案 A。

## A-Mem 接入设计

### 使用边界

A-Mem 官方脚本中存在 `answer_question(question, category, answer)` 这类入口，其中
`answer` 是 gold answer。该入口不能用于本项目 prediction，因为违反私有标签边界。

Adapter 只调用底层记忆系统、检索器和 LLM controller：

- memory build：把统一 `Conversation` 转换为 A-Mem 的 memory note。
- retrieval：基于公开 `Question` 生成/使用查询，并调用 A-Mem 记忆检索。
- answer：用公开 question 和检索出的 memory context 构造 reader prompt，调用 A-Mem
  使用的 LLM controller 生成答案。

### 状态隔离

每个 `conversation_id` 拥有独立 A-Mem runtime/state。`add()` 接收
`list[Conversation]` 时逐个初始化或复用 conversation runtime；`get_answer()` 只能访问
`question.conversation_id` 对应 runtime。未知 conversation 或未 add 的 question 必须抛
项目领域异常。

### 配置

新增 `configs/methods/amem.toml`，至少包含：

- `smoke`
- `official`
- `custom`

关键配置包括：

- LLM backend 与模型名。
- embedding 模型名。
- retrieval 数量，例如 A-Mem 官方默认 `retrieve_k`。
- max workers，初期固定为 1 或受 registry 限制。
- 是否启用 robust 入口；若官方 robust 实现更稳定，应默认使用 robust。

所有配置加载到强类型 `AMemConfig`，禁止在 adapter 内散落硬编码实验参数。

### 效率 observation

A-Mem adapter 应记录：

- `memory_build_total_latency_ms`
- retrieval latency
- injected memory context tokens
- answer generation latency
- memory build / retrieval / answer 阶段的 LLM input/output tokens
- memory build / retrieval 阶段的 embedding input tokens 和 latency

优先在 wrapper 边界和第三方公开对象边界记录。若第三方 LLM/embedding 返回值不暴露
usage，使用匹配 tokenizer 估算，并在 `measurement_source` 标注为 tokenizer estimate。

## LightMem 接入设计

### 使用边界

LightMem 应优先通过官方 `LightMemory` 或等价公开类接入，而不是跑
`experiments/locomo/*.py` 脚本。官方实验脚本只作为理解配置、prompt、检索和更新流程的
事实来源。

如果 `LightMemory` 的公开 API 无法直接完成 conversation + QA 运行，adapter 可以在本项目
侧组合 LightMem 的官方组件，但不能复制或重写核心算法逻辑。

### 状态隔离

LightMem 同样按 `conversation_id` 隔离 runtime/state。若官方实现依赖 collection 或存储
backend，adapter 必须把 collection/storage 路径派生自当前 run 的 method storage root 和
conversation id，避免不同 run 或 conversation 串写。

### 配置

新增 `configs/methods/lightmem.toml`，至少包含：

- `smoke`
- `official`
- `custom`

关键配置包括：

- answer LLM 模型。
- embedding 模型和执行模式。
- compression / memory manager / retriever 相关参数。
- 外部存储 backend 配置。
- max workers，初期保持保守。

若 LightMem 依赖缺失或资源未配置，adapter 必须在运行前抛清晰配置错误，而不是运行到一半失败。

### 效率 observation

LightMem 先记录 wrapper 能精确观测的字段：

- `memory_build_total_latency_ms`
- retrieval latency
- injected memory context tokens
- answer generation latency

LLM/embedding tokens 若可从官方组件或返回 usage 中精确获得，则记录；若只能在 wrapper
边界估算，则标注 measurement source；若无法区分阶段，必须记录为 unsupported/null 或在
运行前声明不支持对应 contract，禁止估算冒充实测。

## Registry 与兼容性

两个 method 都注册为 conversation + QA task family 的官方集成 method。它们只声明真实实现
的 capability：

- end-to-end answer capability 必须实现。
- retrieval capability 只有在 adapter 暴露稳定 `retrieve()` 且通过测试后才声明。

source identity 必须覆盖：

- 第三方 method 关键源码文件。
- 本项目 wrapper 文件。
- 影响行为的配置 profile。
- 观测插桩身份。

resume 时若 source identity、profile、benchmark 数据指纹或 instrumentation identity 不一致，
必须在创建运行副作用前拒绝继续。

## 测试策略

每个 method 分四层测试：

1. adapter contract：配置校验、未 add conversation 报错、conversation 隔离、private 字段不泄漏。
2. fake/offline：用 fake LLM / fake embedding 或轻量 stub 验证 add/get_answer 和效率 observation。
3. registry/runner smoke：通过通用 registered prediction 路径跑极小 LoCoMo 样本，不触网。
4. API smoke：用户确认后执行显式小样本真实 API。

正式 full run 不属于本阶段。

## 实施顺序

1. 阅读 A-Mem 官方 README、核心 memory layer 和 robust 脚本，确定最小公开调用路径。
2. 写 A-Mem adapter 的失败测试。
3. 实现 A-Mem config、wrapper、registry 和 source identity。
4. 补齐 A-Mem efficiency observation。
5. 跑 A-Mem focused 离线回归。
6. 阅读 LightMem 官方 README、`LightMemory` 类和 LoCoMo/LongMemEval 实验脚本，确定最小公开调用路径。
7. 写 LightMem adapter 的失败测试。
8. 实现 LightMem config、wrapper、registry 和 source identity。
9. 补齐 LightMem 可精确观测的 efficiency observation。
10. 跑 LightMem focused 离线回归。
11. 更新 AGENTS、roadmap、handoff 和 README 中的 method 接入状态。

## 风险与处理

- A-Mem 官方入口可能需要 gold answer：不能使用该入口，必须绕到底层公开组件。
- A-Mem/LightMem 可能硬编码 OpenAI client 或不支持 base_url：优先通过 wrapper 注入可配置 client；
  若必须 patch，只做可审计、行为等价的配置注入或 observer，不改算法。
- LightMem 依赖可能较重：先做 import/source compatibility 和配置前置校验，避免运行中失败。
- 不同 method 的记忆注入粒度不同：adapter 遵循第三方算法推荐入口，不强行统一到 turn/session。
- token usage 可能不可得：用已有 token counting 机制估算并标注来源，或声明 unsupported。

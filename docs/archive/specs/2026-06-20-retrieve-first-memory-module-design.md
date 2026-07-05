# Retrieve-First Memory Module 架构设计

日期：2026-06-20

## 背景

当前 conversation + QA 主线已经接入 Mem0、MemoryOS、A-Mem 和 LightMem，并具备
conversation-level resume、conversation 并行、标准 artifact、LLM judge、F1 和效率观测。

现有 method 主接口是：

```python
add(conversations: list[Conversation]) -> AddResult
get_answer(question: Question) -> AnswerResult
```

但复核四个 method 的实际实现后发现：

- Mem0、A-Mem、LightMem 的 `get_answer()` 本质上是在 adapter 中先执行 method 官方检索逻辑，
  再由 adapter 拼 prompt 调 reader LLM。
- MemoryOS 也可以拆为 `retrieval_system.retrieve()` 和官方 answer prompt/LLM 两步。
- 因此 `get_answer()` 并不是更轻的 method 原生接口，反而把检索、prompt、answer LLM、
  token 观测都混在 adapter 中，增加了新 method 接入难度。

用户最初明确的新方向是把 method 视为 memory module：

```text
conversation history -> add(conversation)
question -> retrieve(question) -> formatted_context
framework reader -> answer
evaluator -> score
```

也就是把 method 统一视为 memory module，而不是完整 agent system。

2026-06-22 修订：进一步复核 LoCoMo、LongMemEval 以及四个 method 后，确认许多
benchmark 没有官方 answer prompt，且不同 method 的 memory schema、检索结果和
reader prompt 设计差异很大。为了避免 framework 替 method 设计 reader 造成更大不公平，
新协议应把 **answer prompt 设计视为 method 的一部分**：

```text
question -> retrieve(question) -> prompt_messages
framework answer LLM -> answer
evaluator -> score
```

2026-06-22 进一步修订：`retrieve()` 的核心结果不再是单字符串
`answer_prompt`，而是 method 已经构造好的完整 role message 结构
`AnswerPromptResult.prompt_messages`。`answer_prompt` 只作为兼容 artifact、日志和 token
估算文本视图保留。framework 只负责选择/调用 answer LLM、记录 token 和保存 artifact。

## 设计目标

- 新主协议只强制 method 实现 `add(conversation)` 和 `retrieve(question)`。
- `retrieve()` 返回 method 内部已经处理好的完整 answer prompt messages。
- framework 统一负责 answer LLM、answer artifact、quality metric 和 judge。
- 保留现有 conversation-level resume、question-level resume、conversation 并行和标准输出目录。
- 保留内置四个 method 已实现的深度 efficiency 插桩。
- 降低用户自定义 method 接入门槛；用户需要实现 answer prompt 构造，但不需要自己调用
  answer LLM。
- 允许未来对内置 method 的 internal LLM provider 做可配置扩展。

## 非目标

- 本设计不恢复 retrieval recall metric。Phase 1 仍只评 answer-level 指标。
- 本设计不做 turn-level resume。
- 本设计不立即实现 method 原生 batch ingest。
- 本设计不立即支持 Claude、本地 LLM 或其他 internal LLM provider；当前仍默认
  OpenAI-compatible `gpt-4o-mini`。
- 本设计不改变第三方 method 的 memory construction、compression、ranking、retrieval
  等核心算法流程。
- 本设计不启动新的真实 API full 实验。

## 核心协议

### BaseMemoryProvider

新的 method 主接口建议命名为 `BaseMemoryProvider` 或同等语义名称：

```python
class BaseMemoryProvider(ABC):
    def add(self, conversation: Conversation) -> AddResult:
        ...

    def retrieve(self, question: Question) -> AnswerPromptResult:
        ...
```

`add()` 接收单个 `Conversation`，不是 `list[Conversation]`。

原因：

- 最小接入成本最低。
- 与 conversation-level resume 对齐。
- runner 可以自然按 conversation 并行。
- 用户 adapter 不需要处理分片、并发、失败隔离和 artifact 提交。

未来如果某些 method 有高效批量写入能力，可以增加可选能力：

```python
add_many(conversations: list[Conversation]) -> list[AddResult]
```

但 `add_many()` 不进入第一轮重构范围。

### AnswerPromptResult

`retrieve()` 的核心输出不是“原始记忆列表”，也不是单独的 memory context，而是可直接交给
answer LLM 的完整 role messages。这样可以把 method 的 reader/prompt 设计纳入被测方法本身，
并保留官方 system/user prompt 结构。

建议实体：

```python
@dataclass
class AnswerPromptResult:
    question_id: str
    conversation_id: str
    prompt_messages: list[PromptMessage]
    answer_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
```

字段语义：

- `prompt_messages`: 必填。method 内部已经完成 query rewrite、检索、rerank、merge、去重、
  格式化和 reader prompt 拼接后的完整 role messages。
- `answer_prompt`: 兼容文本视图。若为空，实体由 `prompt_messages` 自动生成带 role 标记的
  可读文本；旧 artifact 只含 `answer_prompt` 时可降级为 user message。
- `metadata`: 唯一扩展口。可放 `answer_context`、标准化 `retrieved_memories`、
  `raw_items_ref`、`query_keywords`、`retrieve_k`、`search_strategy`、`prompt_profile`、
  `source_method`、`unsupported_reason` 等公开诊断信息。不得包含 gold answer、evidence、
  judge label、secret 或超大 raw object；大对象应写入单独 debug artifact 后只放引用。

`prompt_messages` 为空应 fail closed。

`injected_memory_context_tokens` 不再是强制主指标。若 method 在 metadata 中提供
`answer_context`，framework 可以计算该诊断值；否则写为 `null/unsupported`。主成本指标
应以 answer LLM 的 input/output tokens 为准。

## Framework Reader

answer LLM 调用从 method adapter 上移到 framework；answer prompt messages 构造仍属于 method。

流程：

```text
AnswerPromptResult.prompt_messages
AnswerLLMConfig
        |
        v
AnswerResult
```

默认 prompt template 必须至少支持：

```text
{question}
{memory_context}
```

可选支持：

```text
{question_time}
{conversation_id}
{category}
{options}
```

如果用户传自定义 prompt，framework 必须校验模板中包含 `{question}` 和
`{memory_context}`。缺失时直接报错，避免用户以为使用了检索记忆但实际 prompt 未注入。

默认 answer LLM：

```text
model = gpt-4o-mini
provider = openai_compatible
api_key = OPENAI_KEY
base_url = BASE_URL
```

当前阶段不主动切换模型。

## Built-in Method 迁移思路

### Mem0

`retrieve()` 应保留当前官方 LoCoMo / LongMemEval 检索逻辑：

- LoCoMo 写入仍按官方 `CHUNK_SIZE=1`。
- LongMemEval 写入仍按官方 `CHUNK_SIZE=2` user+assistant pair。
- 检索仍调用 vendored Mem0 backend 的 search。
- `formatted_context` 使用当前 `_memory_context_text()` 或官方 prompt 需要的 memory 格式。

当前 `get_answer()` 中 reader LLM 调用移到 framework reader。

### A-Mem

`retrieve()` 应保留：

- 官方 query keyword generation。
- Table 8 category-specific `k`。
- official runtime retriever。
- adversarial category 仍按 public-input 规则显式拒绝，除非后续另行设计私有 gold 边界。

`formatted_context` 使用当前 `find_related_memories_raw()` 的上下文格式或更稳定的字符串格式。

### LightMem

`retrieve()` 应保留：

- LoCoMo 专门化的 `search_locomo.py` 风格 Qdrant payload/vector combined 检索。
- LoCoMo `add()` 后的 `construct_update_queue_all_entries()` 和
  `offline_update_all_entries(score_threshold=0.9)`。
- LongMemEval 当前保持通用 `LightMemory.retrieve()` online 路径。

`formatted_context` 使用当前 reader prompt 前的 memories 格式化结果。

### MemoryOS

`retrieve()` 应调用：

```text
state.retrieval_system.retrieve(...)
```

然后把以下内容格式化为 `formatted_context`：

- retrieval queue / retrieved pages。
- long-term knowledge。
- 必要的 user profile / agent traits / STM 摘要，如果官方 answer prompt 实际依赖。

不再由 MemoryOS adapter 调用最终 answer 生成函数作为主路径。MemoryOS 官方 answer prompt
中的有价值结构可以迁移为 framework prompt profile。

## Prompt Profile

官方论文风格不需要保留 `get_answer()`。

它应表达为：

```text
method.retrieve strategy
answer prompt profile
answer LLM config
manifest identity
```

例如：

```text
answer_prompt_profile = "locomo_default"
answer_llm.model = "gpt-4o-mini"
retrieval_profile = "lightmem_locomo_official_0.7_512"
```

如果某个 method/benchmark 有官方 prompt，可以作为 framework prompt profile 注册。
如果没有，使用 framework 默认 prompt。

这意味着重构后的实验是 memory-module evaluation：

```text
同一 answer reader + 不同 method retrieve context
```

这比 adapter 内各自拼 answer 更适合长期横向比较。

## Internal LLM 配置策略

LLM 配置分三层：

```text
method_internal_llm
answer_llm
judge_llm
```

### Phase 1

- `method_internal_llm` 默认 OpenAI-compatible `gpt-4o-mini`。
- `answer_llm` 默认 OpenAI-compatible `gpt-4o-mini`。
- `judge_llm` 默认 OpenAI-compatible `gpt-4o-mini`。
- API key 和 base URL 仍来自 `.env` 的 `OPENAI_KEY` / `BASE_URL`。

### Future

用户已授权修改第三方 method 源码，但边界是：

- 可以改 provider/client 适配层。
- 可以改参数注入层。
- 可以加 observer 插桩。
- 不得改变 memory construction、retrieval、compression、ranking 等核心算法流程。

未来可让内置 method 支持：

- OpenAI-compatible。
- Anthropic / Claude。
- 本地开源 LLM。

每个内置 method 必须声明它实际支持的 internal LLM backend。不支持时配置校验直接报错。

用户自定义 method 不强制暴露 internal LLM 配置。用户 adapter 内部可以完全自管自己的
LLM、温度、max tokens、本地模型路径等参数。

## Observability

framework 层必须稳定记录：

- conversation memory build total latency。
- per-question retrieval latency。
- injected memory context tokens，即 `formatted_context` token 数。
- answer LLM input/output tokens。
- answer generation latency。
- judge LLM input/output tokens，仅在真实 judge 运行时记录。

内置 method 继续保留深度插桩：

- memory build LLM tokens。
- memory build embedding tokens/latency。
- retrieval-stage LLM tokens。
- retrieval embedding tokens/latency。
- method-native token/latency。

用户自定义 method 不强制实现内部插桩。缺失时应显示为 `unsupported` 或 `null`，并带
`unsupported_reason`。

## Resume 和并行

保持当前基本语义：

- conversation-level add resume。
- question-level retrieve/answer resume。
- failed conversation 默认隔离，`--retry-failed` 才重新纳入。
- 同一次 run 内每个 conversation 最多尝试一次。
- `max_workers` 表示单个 method × benchmark run 内 conversation 级最大并发数。

重构后 answer 阶段应拆成两个可恢复步骤：

```text
retrieve phase
answer phase
```

如果 retrieve 已完成但 answer 失败，resume 时应复用已保存的 retrieval artifact，而不是
重新检索，除非用户显式要求 rerun retrieval。

## Artifact 设计

建议新增或调整 prediction artifacts：

```text
artifacts/retrieval_results.prediction.jsonl
artifacts/method_predictions.jsonl
artifacts/answer_prompts.jsonl 或 conversation/question prompt reference
summaries/efficiency_*.prediction.json
```

`retrieval_results.prediction.jsonl` 至少包含：

```json
{
  "question_id": "...",
  "conversation_id": "...",
  "formatted_context": "...",
  "metadata": {},
  "memories": []
}
```

`method_predictions.jsonl` 继续保存最终 answer，但不重复写入大段 context。需要追溯时通过
`question_id` 关联 retrieval artifact。

## 配置与 Manifest

prediction manifest 需要纳入：

- method name / profile。
- benchmark / variant。
- retrieval protocol version。
- answer prompt profile 或 prompt file fingerprint。
- answer LLM config identity。
- judge LLM config identity，仅 evaluation manifest。
- method internal LLM config identity。
- source identity。
- observability config identity。

用户覆盖 internal LLM、answer prompt 或 answer LLM 时，manifest 必须显式记录，避免和
官方默认配置结果混淆。

## 迁移计划概览

1. 新增 retrieve-first protocol entity 与接口，保留旧 `get_answer()` 作为临时兼容。
2. 新增 framework reader 组件和 prompt template 校验。
3. 修改 prediction runner：`get_answer()` 路径拆成 `retrieve()` + reader answer。
4. 新增 retrieval artifact 和 retrieve/answer phase resume。
5. 迁移 Mem0 adapter。
6. 迁移 A-Mem adapter。
7. 迁移 LightMem adapter。
8. 迁移 MemoryOS adapter。
9. 更新 CLI/config/manifest。
10. 更新 tests、README、AGENTS、method 接入文档。
11. 删除或降级旧 `get_answer()` 主协议。

## 验收标准

- Fake method 可只实现 `add()` 和 `retrieve()`，并通过 prediction runner 生成 answer。
- 四个内置 method 的 retrieve-first smoke 在 LoCoMo 上通过。
- `formatted_context` 为空时 fail closed。
- 自定义 prompt 缺 `{question}` 或 `{memory_context}` 时 fail closed。
- resume 可从 retrieve completed / answer pending 状态继续。
- `max_workers > 1` 时 retrieval artifact、answer artifact 和 efficiency observation 不串写。
- artifact-only F1 / judge evaluation 仍可基于 prediction artifact 运行。
- 内置 method 深度插桩仍能写出原始 observation。
- 未经用户确认，不执行 full API 实验。

## 风险和处理

- 风险：统一 reader 会改变历史 official-style 结果。
  - 处理：manifest 记录 protocol version 和 answer prompt profile；旧 run 不与新 run 混比。
- 风险：MemoryOS 官方 answer prompt 逻辑较复杂。
  - 处理：先把 MemoryOS retrieval context 格式化和 prompt profile 做成显式、可测试组件。
- 风险：`formatted_context` 太长导致 answer LLM token 成本高。
  - 处理：记录 `injected_memory_context_tokens`，后续再做 context budget。
- 风险：用户自定义 method 只返回非结构化 context，debug 困难。
  - 处理：`memories` 可选，不强制；文档建议尽量填 metadata 和 memories。

## 当前结论

主线协议收敛为：

```text
add(conversation) -> retrieve(question) -> framework reader answer -> evaluate
```

`get_answer()` 不再作为新 method 必须实现的接口。第一轮实现只支持
OpenAI-compatible `gpt-4o-mini`，但架构预留内置 method internal LLM provider 可配置能力。

# 成本与效率观测设计

日期：2026-06-15

## 1. 目标

为 conversation + QA 实验建立可复现、可审计的原始效率观测能力。第一阶段覆盖
LoCoMo、LongMemEval-S，以及已经接入的 MemoryOS、Mem0；A-Mem、LightMem 在各自
adapter 接入时复用同一套协议。

本阶段不把费用绑定到任何官方模型价格。项目当前使用的是 OpenAI-compatible API，
并非 OpenAI 官方计费服务，因此：

1. 实验运行只记录真实 token、调用、延迟、模型身份和计量来源。
2. 实验结束后，用户提供实际服务商价格配置。
3. 离线分析层根据原始 observation 计算真实费用。
4. 价格变化时只需重新分析，不得重跑 prediction 或 judge。

## 2. 非目标

- 不实现 retrieval recall。
- 不把本地 GPU、显存和电费纳入第一阶段费用。
- 不估算没有实际运行的 LLM Judge。
- 不记录 retrieved memory 条数或未进入最终 prompt 的候选记忆 token。
- 不通过总耗时相减、经验公式或猜测伪造细粒度指标。
- 不修改第三方 method 的核心算法、prompt、模型参数、控制流或返回值。
- 不在本阶段接入 A-Mem、LightMem adapter，也不启动全量付费实验。

## 3. 总体架构

```text
predict
  -> method adapter
  -> optional observer instrumentation
  -> predictions
  -> raw efficiency observations

evaluate
  -> F1: offline, no LLM usage
  -> LLM judge: actual judge observations only

offline analysis
  -> aggregate tokens and latency
  -> apply user-supplied pricing
  -> cost report
```

各层职责如下：

- Runner 定义 conversation、question 生命周期和公共计时边界。
- Method adapter 把统一阶段映射到 method 的真实内部操作。
- Observer 只采集数据，不参与算法决策。
- Evaluator 负责 Judge 调用和 Judge usage，不修改 prediction artifact。
- Analysis 负责聚合和费用计算，不调用 method 或 evaluator。
- Storage 继续使用标准实验目录、原子写入、checkpoint 和 resume 规则。

## 4. 观测指标

### 4.1 Conversation 级

`memory_build_total_latency_ms`

- 从开始向 method 注入某个 conversation 的第一条记忆计时。
- 到该 method 按当前 benchmark + method official profile 已经可以回答问题时结束。
- 包括 official profile 明确要求在问答前完成的 flush、summary 或 offline update。
- 不包括 method 初始化时间。
- LoCoMo 的 LightMem official profile 包含问答前 offline update。
- LongMemEval 的 LightMem 默认 official profile不包含 offline update。

### 4.2 Question 级

`retrieval_latency_ms`

- 从 method 开始处理该 question 的记忆检索，到最终注入 Answer LLM 的记忆上下文准备完毕。
- 不包含 Answer LLM 的答案生成时间。
- 能从官方接口或明确内部边界精确测量时记录非负数。
- 无法精确拆分时记录 `null`，并填写 `unsupported_reason`。
- 禁止通过 `get_answer 总耗时 - LLM 延迟` 进行估算。

`injected_memory_context_tokens`

- 只统计最终实际注入 Answer LLM prompt 的记忆上下文。
- 使用 Answer LLM 对应 tokenizer。
- 它是 `answer_input_tokens` 的组成部分，只用于分析记忆上下文开销，费用聚合时不得重复计费。

`answer_generation_latency_ms`

- 从实际提交 Answer LLM 请求到获得完整答案响应。
- 不包含 retrieval。

### 4.3 LLM 调用级

每次真实 LLM 调用分别记录：

- `stage`: `memory_build`、`answer` 或 `judge`
- `model_id`
- `input_tokens`
- `output_tokens`
- `token_measurement_source`
- 可关联的 `conversation_id` 和可选 `question_id`

Judge 只有实际运行时才产生 observation。未运行 Judge 时：

- 不生成调用数估算。
- 不生成 input/output token 估算。
- 不生成费用估算。

### 4.4 Embedding 调用级

每次 embedding 调用分别记录：

- `stage`: `memory_build` 或 `retrieval`
- `model_id`
- `input_tokens`
- `latency_ms`
- `token_measurement_source`
- `latency_measurement_source`
- 可关联的 `conversation_id` 和可选 `question_id`

Embedding 不记录 output token。API embedding 可在实验后按实际服务商价格计费；本地
embedding 第一阶段费用为 0，但仍记录输入 token 和 latency。

## 5. 模型身份

每个 run 保存独立的模型清单，observation 只引用稳定的 `model_id`，避免在每一行重复
大段身份信息。

模型清单至少记录：

- `model_id`: run 内稳定标识。
- `model_name`: 实际模型名称。
- `model_role`: memory LLM、answer LLM、judge LLM、embedding 或其他辅助模型。
- `execution_mode`: `api` 或 `local`。
- `revision_or_path`: 本地模型版本、revision 或路径；无法获得时明确为 `null`。
- `embedding_dimension`: 仅 embedding 模型适用。
- `tokenizer_name`: 用于 tokenizer 估算和 memory context 计数。

不要求在可见模型清单中展示 provider。离线价格配置通过 `model_id` 与计费项匹配。

## 6. 计量来源与可信度

token 可信度优先级固定为：

```text
API 原生 usage
> method 官方原生统计
> tokenizer 计数
> unsupported/null
```

latency 可信度优先级固定为：

```text
method 官方原生计时
> 框架在明确调用边界进行的计时
> unsupported/null
```

来源字段按具体 metric 分开记录，避免 token 和 latency 共用一个含义模糊的来源字段。
稳定枚举为：

- `api_usage`
- `method_native`
- `framework_timer`
- `tokenizer_estimate`

规则：

- API 返回 usage 时必须优先使用，不重复 tokenizer 估算。
- API 不返回 usage 时，使用与实际模型匹配的 tokenizer，并标记
  `tokenizer_estimate`。
- tokenizer 不可确定时，token 字段不得假装精确；应报配置错误或记录 unsupported，
  具体取决于该指标是否为当前 profile 的 required observation。
- 所有 token 必须是非负整数；所有 latency 必须是有限的非负数。

## 7. Observer 与第三方插桩

观测实现采用混合策略：

1. 优先读取 method 官方已有 usage/statistics。
2. adapter 外层存在准确边界时，在 adapter 中计时或计数。
3. 前两项无法覆盖时，允许在第三方源码中加入纯 observer 插桩。
4. 仍无法可靠观测时使用 `unsupported/null`。

第三方插桩必须满足：

- observer 默认可关闭。
- 关闭 observer 时，行为应与未插桩官方源码一致。
- 不改变 prompt、模型参数、控制流、返回值、异常语义和持久化状态。
- observer 失败不能改变 method 算法结果；对应 observation 标记缺失或失败。
- 第三方源码不依赖完整 `memory_benchmark` package，只依赖轻量 callback/protocol。
- 记录官方 upstream commit/tree hash 和 instrumentation patch hash。
- source identity 同时覆盖官方源码和本项目实际执行的 observer/wrapper 源码。
- 每个插桩点必须有关闭 observer 时的行为等价测试。

该规则取代“绝不修改第三方源码”的旧绝对限制，但仍禁止修改第三方核心算法。

## 8. 框架组件

在现有 src-layout 下增加聚焦组件，不修改 `BaseMemorySystem` 公共接口：

```text
src/memory_benchmark/observability/efficiency/
  entities.py       # 强类型 observation 和枚举
  collector.py      # 运行期收集、作用域关联和校验
  token_counting.py # tokenizer 适配与计量来源
  storage.py        # 标准 artifact 写入、读取和恢复

src/memory_benchmark/analysis/
  efficiency.py     # token/latency 离线聚合
  cost.py           # 用户价格配置和真实费用计算
```

Method adapter 通过可选 observer/collector 依赖上报数据。未启用效率观测时，不改变
现有 method 行为；用户自定义 method 也不被迫扩展公共接口。

Runner 在以下边界创建作用域：

```text
conversation scope
  add conversation
  official pre-question finalization

question scope
  retrieval
  answer generation
```

Evaluator 在自己的 judge scope 中记录 Judge 调用。Prediction 与 Judge observation
保持独立，符合 `predict` 与 `evaluate` 分离原则。

## 9. Artifact 与恢复

Prediction 在标准 `artifacts/` 下保存：

```text
artifacts/
  model_inventory.prediction.json
  efficiency_observations.prediction.jsonl
```

每个实际执行的 evaluator 保存自己的独立文件：

```text
artifacts/
  model_inventory.<metric_name>.json
  efficiency_observations.<metric_name>.jsonl
```

这样后续运行 Judge 不会重写或污染已完成的 prediction observation；未运行 Judge 时也
不会创建 Judge 文件。离线分析可以显式选择仅分析 prediction，或合并指定 evaluator。

每个 efficiency observation JSONL 使用带 `observation_type` 的强类型记录，至少支持：

- `conversation_efficiency`
- `question_efficiency`
- `llm_call`
- `embedding_call`

每条 observation 具有确定性 `observation_id`，由 run、阶段、conversation、question、
调用序号等稳定信息生成。

并发和 resume 规则：

- worker 不直接并发写共享 JSONL。
- worker 返回该 conversation 的 prediction 与 observation bundle。
- 协调层串行提交标准 artifact。
- checkpoint 只在对应 bundle 成功提交后推进。
- resume 根据确定性 observation id 和 checkpoint 防止重复记录。
- observability 配置、模型清单和 instrumentation identity 进入 immutable manifest。
- resume 时上述身份不一致必须在构建 method 和产生目录副作用前拒绝。

## 10. 离线聚合与费用

效率聚合不依赖价格，可输出：

- conversation memory build latency 的 count、mean、P50、P95、sum。
- question retrieval latency 的 supported count、unsupported count、mean、P50、P95。
- answer generation latency 的 count、mean、P50、P95、sum。
- injected memory context tokens 的 count、mean、P50、P95、sum。
- 按 stage/model 聚合的 LLM input/output tokens。
- 按 stage/model 聚合的 embedding input tokens 和 latency。

费用计算读取单独的用户价格配置：

- API LLM input 单价。
- API LLM output 单价。
- API embedding input 单价。
- 币种和计价 token 单位。

费用报告必须：

- 只计算 `execution_mode=api` 且存在价格映射的模型。
- 本地模型费用记为 0，但保留其用量和延迟。
- 区分 memory build、answer、judge、embedding build、embedding retrieval。
- 给出未配置价格的模型列表，禁止静默按 0 计算。
- 不把 `injected_memory_context_tokens` 再次加入 answer input token 费用。

## 11. Method 适配策略

### MemoryOS

- 公共 build 总耗时由 runner 测量。
- adapter 已有明确 retrieval 调用边界，可测 retrieval latency。
- 优先复用官方响应 usage；缺失时在实际 LLM client 边界计数。
- 本地 `all-MiniLM-L6-v2` 记录 build/retrieval embedding token 与 latency。

### Mem0

- 公共 build 总耗时由 runner 测量。
- adapter 已有明确 search 调用边界，可测 retrieval latency。
- API LLM 和 `text-embedding-3-small` usage 优先读取 API 返回。
- 需要时包装 Mem0 使用的 client；只有 wrapper 无法覆盖时才插入 observer。

### A-Mem

- adapter 尚未实现。
- 后续按官方 turn-level `add_note` 和检索调用接入同一 collector。
- 本设计不提前修改其源码。

### LightMem

- adapter 尚未实现。
- 后续优先复用官方 `get_token_statistics`，但必须先验证其字段与本协议语义一致。
- LoCoMo official profile 的 offline update 计入 build 总耗时。
- LongMemEval 默认 official profile 不执行 offline update。
- LLMLingua-2 等本地辅助模型写入模型清单；第一阶段不计算本地费用。

## 12. 错误处理

- required observation 缺失：在付费运行前配置校验失败，或按 profile 明确标为
  unsupported；不得静默填 0。
- 非法 token/latency：抛项目领域异常，不写入 artifact。
- observer 异常：记录结构化错误日志；算法可继续时将对应指标标为 unsupported，算法
  本身失败时保留原始异常语义。
- 模型身份缺失或价格映射缺失：离线分析明确报错或生成 incomplete report，不能生成
  看似完整的总费用。
- Judge 未运行：Judge observation 集合为空，不生成估算记录。

## 13. 验证

实现遵循小步验证：

1. observation 实体、枚举和强校验单元测试。
2. tokenizer/API usage 优先级测试。
3. conversation/question scope 与并发隔离测试。
4. JSONL artifact、确定性 id、resume 去重和 immutable manifest 测试。
5. fake method 验证 build/retrieval/answer 边界。
6. fake LLM/embedding client 验证 input/output token 分离。
7. MemoryOS、Mem0 adapter 的不触网 focused tests。
8. 第三方插桩的 observer on/off 行为等价测试。
9. Judge 未运行时无 Judge observation；实际 fake Judge 调用时才产生记录。
10. 离线聚合和价格计算测试，确认 context tokens 不重复计费。
11. 完整离线回归和受保护 MemoryOS-LoCoMo 资产哈希校验。

付费 API smoke 必须由用户明确确认规模后执行，不作为默认测试。

## 14. 实施顺序

1. 建立 observation schema、collector、storage 和测试。
2. 接入通用 runner 的 conversation/question scope。
3. 接入 Mem0 和 MemoryOS 的精确观测点。
4. 接入 LLM Judge observation。
5. 实现离线效率聚合和用户价格计算。
6. 完成不触网回归、行为等价检查与综合 review。
7. A-Mem、LightMem 在各自 adapter 阶段接入，不阻塞本阶段闭环。

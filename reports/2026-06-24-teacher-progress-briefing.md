# AgentMemoryBench 项目进度

## 1. 项目目标

Agent Memory 方向的实验目前比较分散：不同方法通常自带不同的数据处理脚本、prompt、运行流程和指标计算方式。最直接的问题是横向比较困难，但更本质的问题是：研究者如果想验证一个新 memory method，往往要先花大量时间处理数据格式、工程脚本、恢复机制、日志、指标和成本估算，而不是专注在 method 本身。

- **横向比较困难**：Mem0、MemoryOS、A-Mem、LightMem 等方法各自有评测脚本，实验产物格式不统一。
- **新方法接入繁琐**：新 method 作者不应该从零理解每个 benchmark 的原始仓库、数据字段、prompt 和评测脚本。
- **运行过程不可靠**：长对话 benchmark 会产生大量 LLM 调用，因此需要 resume、日志、异常定位和标准实验产物，避免一次中断就重跑全部实验。
- **实验成本记录**：框架需要记录 token、调用次数和耗时，让预算估算有真实实验依据，而不是只按数据集规模粗估。

因此，本项目的核心目标是：让用户少在工程细节上消耗精力，直接用统一接口接入 method、选择 benchmark、运行实验、复算指标，并能和框架已经集成的 baseline method 做公平可审计的对比。

---

## 2. 当前框架主要服务谁

当前框架主要服务两类使用场景：

| 使用场景 | 用户想做什么 | 框架提供什么 |
| --- | --- | --- |
| 接入自己的新 method | 用户已经有自己的 memory method，希望直接在 LoCoMo、LongMemEval 等 benchmark 上跑实验 | 只需实现轻量接口 `add(conversation)` 和 `retrieve(question)`；框架负责 benchmark 读取、answer LLM、指标、日志、resume 和实验产物 |
| 运行框架已集成的 method | 用户希望直接运行 Mem0、MemoryOS、A-Mem、LightMem，并通过调参比较不同实验设置 | 框架提供已封装好的 method adapter；用户可通过 `configs/` 下的 TOML 调整内置 method 的白盒参数，例如内部 LLM、embedding、top-k、threshold 等 |

这里需要明确一条边界：`configs/` 主要服务我们已经集成好的 method 和 evaluator。用户自己的黑盒 method 不要求写我们的 TOML，也不要求理解 registry、source identity 或内部 efficiency inventory。用户自己的 method 内部参数，仍然由用户自己的代码或配置管理。

---

## 3. 当前项目覆盖范围

| 类型 | 当前范围 |
| --- | --- |
| Benchmark | LoCoMo、LongMemEval-S / LongMemEval-M |
| Method | Mem0、MemoryOS、A-Mem、LightMem |
| 质量指标 | LoCoMo F1、LoCoMo LLM judge、LongMemEval LLM judge |
| 效率观测 | token、latency、API calls、model identity、memory context tokens |
| 当前默认 LLM | `gpt-4o-mini`，通过 OpenAI-compatible API 调用 |

---

## 4. 总体运行链路

当前框架采用 retrieve-first memory-module 架构。一次实验从原始 benchmark 数据开始，到最终指标和成本报告结束，中间可以分为 8 个环节：

1. **Benchmark Adapter 读取数据**  
   把 LoCoMo、LongMemEval 等原始 dataset 转成统一的 `Dataset / Conversation / Session / Turn / Question / GoldAnswerInfo`。

2. **Public / Private 分离**  
   `Conversation` 和 `Question` 给 method；`GoldAnswerInfo` 只给 evaluator。gold answer、evidence、category 等标签不能进入 method。

3. **Method.add(conversation)**  
   method 只接收当前 conversation 的公开历史，把它写入自己的 memory backend。conversation 是隔离边界。

4. **Method.retrieve(question)**  
   method 根据 question 和 conversation_id 检索相关记忆，并返回完整 `AnswerPromptResult.prompt_messages`。这里的 prompt messages 可以包含 method-specific memory context，因为 prompt 构造本身往往是 memory method 的一部分。

5. **Framework Answer LLM 统一生成答案**  
   框架用统一 answer LLM 读取 `prompt_messages` 并生成最终 answer。这样 answer token、answer latency 和 answer model 配置都能由框架统一记录。

6. **标准实验产物落盘**  
   prediction、prompt、public question、private label、efficiency observation、checkpoint、summary 都写入 outputs。后续 evaluate 不需要重新跑 method。

7. **Evaluator 计算指标**  
   F1、LLM judge 等 evaluator 只读取已有产物和 private labels，计算质量指标。

8. **Efficiency / Cost 离线分析**  
   基于 observation 统计 LLM input/output tokens、embedding tokens、latency、API calls 和模型身份，再按实际服务商价格离线换算费用。

现在method adapter主协议为：

```text
add(conversation)
retrieve(question) -> AnswerPromptResult(prompt_messages)
framework answer LLM -> answer
```

### 4.1 架构图

![AgentMemoryBench 架构图](</Users/wz/Desktop/memoryBenchmark/reports/assets/2026-06-25-framework-architecture.png>)

---

## 5. Benchmark Adapter

Benchmark adapter 只负责：

```text
原始 dataset -> 统一 Dataset
```

它不负责 method 算法，也不负责最终打分。

### 5.1 统一数据模型

当前 LoCoMo 和 LongMemEval 都归一到：

dataset的完整规划：类别、时间规划

```text
Dataset
└── Conversation
    ├── Session
    │   └── Turn
    ├── Question
    └── GoldAnswerInfo
```

| 实体 | 含义 |
| --- | --- |
| Dataset | 一个 benchmark variant，例如 LoCoMo 或 LongMemEval-S |
| Conversation | 一个隔离的对话命名空间，QA 不能跨 conversation 混用记忆 |
| Session | conversation 内的一段对话，通常有 session time |
| Turn | 单个 speaker 的一次发言 |
| Question | method 可见的问题，包含 question text、conversation_id、可选 question_time |
| GoldAnswerInfo | evaluator 私有标签，包括 gold answer、evidence、category 等 |

### 5.2 公开 / 私有边界

Gold answer、evidence、has_answer、target_step_id 等字段只能给 evaluator，不能进入 method。

当前框架做了几层保护：

- 数据结构上把 `Question` 和 `GoldAnswerInfo` 分开。
- method 只能拿 public conversation 和 public question。
- private label 单独保存为 evaluator artifact。
- 运行前会扫描 public input，如果混入 gold/evidence 等私有字段则报错。

### 5.3 LoCoMo

LoCoMo 的结构接近：

```text
conversation
  -> multiple sessions
      -> multiple turns
  -> multiple QA
```

当前处理方式：

- 一个 LoCoMo sample 转成一个 `Conversation`。
- 每个 session 保留 session time。
- 每个 speaker utterance 转成一个 `Turn`。
- QA 转成 public `Question` 和 private `GoldAnswerInfo`。
- category 用于 F1 / judge 后续按类别聚合。
- smoke 模式可裁剪 conversation 数、round 数和每个 conversation 的问题数。

LoCoMo category id 当前按本地 summary 文件确认：

| Category ID | 含义 |
| --- | --- |
| 1 | Multi-hop |
| 2 | Temporal |
| 3 | Open-domain / Commonsense |
| 4 | Single-hop |

### 5.4 LongMemEval

LongMemEval 与 LoCoMo 相似，但有一个重要差异：它的问题和历史 session 都带时间信息。

当前处理方式：

- 一个 LongMemEval instance 转成一个 `Conversation`。
- 支持 `s_cleaned` 和 `m_cleaned` 两个 variant。
- S/M 不合并，避免 resume、指标、成本和排行榜统计混乱。
- `question_time` 会进入 answer prompt，用于时间推理。
- LongMemEval judge 当前按 LightMem LongMemEval 的 yes/no judge 流程走，便于和 LightMem 论文结果比较。

---

## 6. Method Adapter

Method adapter 的职责是：

```text
统一接口 -> 调用第三方 method 官方源码或官方评测逻辑
```

我们不是重写 Mem0、MemoryOS、A-Mem、LightMem 的算法，而是在外层做包装：

- 把统一 `Conversation` 转成各方法需要的写入粒度。
- 按 `conversation_id` 隔离状态。
- 调用第三方 method 的 add / retrieve / search 逻辑。
- 构造 method-specific answer prompt。
- 对内置 method，额外配合框架暴露状态加载、source identity 和精细效率观测。并行、resume、日志、artifact 和 evaluator 仍主要由框架 runner 负责。

当前四个内置 method 的状态：

| Method | 当前接入状态 | 关键对齐点 |
| --- | --- | --- |
| Mem0 | 已接入 LoCoMo / LongMemEval | 使用 Mem0 OSS 和 memory-benchmarks prompt；LoCoMo 按官方 `CHUNK_SIZE=1` 写入；LongMemEval 按 user+assistant pair 写入 |
| MemoryOS | 已接入 LoCoMo / LongMemEval | LoCoMo 保留官方 eval prompt；LongMemEval 新增 retrieve-first 分支，保留短期/中期/长期记忆、用户画像和 assistant knowledge |
| A-Mem | 已接入 LoCoMo / LongMemEval | LoCoMo 保留官方 query keyword generation 和 category k；LongMemEval 复用 LightMem-style reader prompt，同时保留 A-Mem memory context |
| LightMem | 已接入 LoCoMo / LongMemEval | LoCoMo 对齐 `search_locomo.py` 风格；LongMemEval 走 LightMem 原本更通用的 retrieve 流程；当前 profile 固定 `(r=0.7, th=512)` |

### 用户自定义 method 的目标接入方式

未来用户接入新 method 时，理想最小代码是：

```python
class MyMemory(BaseMemoryProvider):
    def add(self, conversation):
        ...

    def retrieve(self, question):
        return AnswerPromptResult(prompt_messages=[...])
```

框架负责：

- benchmark 数据读取和标准化；
- answer LLM 调用；
- metric 计算；
- artifact 写入；
- conversation-level resume；
- 日志和可观测性；
- smoke / formal CLI 参数校验。

用户 method 负责：

- 按 `conversation_id` 管理自己的记忆隔离；
- 在 `retrieve(question)` 中返回完整 `prompt_messages`；
- 如果使用自己的外部数据库或服务，自行管理状态路径、namespace 和清理策略。

这是下一阶段“降低用户接入难度”的重点。

---

## 7. Predict / Evaluate 两阶段

框架把实验拆成两个阶段：

### 7.1 Predict

Predict 只负责跑 method，生成 answer 和标准实验产物：

```text
conversation -> add
question -> retrieve
prompt_messages -> answer LLM
answer -> method_predictions.jsonl
```

Predict 阶段产物包括：

- `method_predictions.jsonl`
- `answer_prompts.prediction.jsonl`
- `public_questions.jsonl`
- `evaluator_private_labels.jsonl`
- `efficiency_observations.prediction.jsonl`
- `summary.json`
- logs 和 checkpoints

### 7.2 Evaluate

Evaluate 只基于已有实验产物计算指标，不重新跑 method：

```text
method_predictions.jsonl + evaluator_private_labels.jsonl -> metric summary
```

好处：

- 同一批 prediction 可以反复计算 F1、LLM judge 或其他指标。
- 如果 judge prompt 调整，不需要重跑 method。
- 如果需要补算新 metric，只需读取已有 artifact。
- 降低 API 成本和实验风险。

这里的 artifact 可以理解为“实验产物文件”，即 prediction、label、prompt、observation、summary 等落盘结果。

---

## 8. 并行和 Resume

当前只做 **单个 method × 单个 benchmark 内部的 conversation 级并行**。

也就是说，一个 run 内可以多个 worker 同时处理不同 conversation；但 method × benchmark 外层矩阵并行暂时不作为主线功能，因为用户可以用多个终端分别跑。

### 8.1 Conversation 级并行

一个 run 里，每个 conversation 是独立命名空间。并行时：

- worker A 处理 conversation 1；
- worker B 处理 conversation 2；
- 不同 conversation 的 method state 不能互相污染；
- 成功和失败都写 checkpoint。

如果某个 conversation 失败：

- 默认只标记该 conversation failed；
- 其他 worker 可以继续完成自己的 conversation；
- 同一次 run 内不会对同一个失败 conversation 反复重试，避免空烧 API。

### 8.2 Resume

Resume 分两层：

1. **框架 artifact 层 resume**  
   框架知道哪些 conversation 已完成、哪些 question 已回答，因此可以跳过已完成内容。

2. **method 内部状态 resume**  
   对内置 method，我们把状态放入标准 `method_state/`，并按 conversation 或 worker 隔离。
   对用户黑盒 method，框架不能证明其内部状态是否可恢复；用户需要遵守软契约，确保自己的 method 能基于 `conversation_id` 找回对应状态。

当前已确认的状态机设计：

```text
pending
ingesting
ingested
answering
completed
failed_ingest
failed_answer
```

关键规则：

- `completed`：跳过。
- `ingested / answering / failed_answer`：不重新 add，只继续未完成 question。
- `failed_ingest`：默认跳过，只有 clean retry preflight 通过才允许重跑。

这个设计是为了避免 add 阶段失败后，method 已经写入一半记忆，直接重跑导致重复记忆。

---

## 9. CLI 使用方式

当前推荐入口分为三类：

```bash
memory-benchmark predict smoke ...
memory-benchmark predict formal ...
memory-benchmark evaluate ...
```

其中：

- `smoke`：小样本连通性测试，可以限制 conversations、rounds、questions。
- `formal`：正式 profile，可以用 `--conversation-budget` 分批推进，并支持 resume。
- `evaluate`：基于已有实验产物计算指标，不重新跑 method。

### 9.1 Smoke

Smoke 用来确认“method + benchmark + API + 本地资源”能否跑通。它允许裁剪数据：

```bash
memory-benchmark predict smoke \
  --method mem0 \
  --benchmark locomo \
  --conversations 2 \
  --rounds 20 \
  --questions-per-conversation 1 \
  --workers 2 \
  --allow-api
```

含义：

- 最多取 2 个 conversation。
- 每个 conversation 最多保留 20 个 round。
- 每个 conversation 最多回答 1 个 question。
- 真实数量不足时自动取 `min(用户参数, 数据集真实数量)`。
- smoke 不用于最终结果汇报，只用于连通性、资源和小规模成本检查。

### 9.2 Formal

Formal 用于正式实验。它不裁剪 history，也不裁剪每个 conversation 的问题，只允许通过
`--conversation-budget` 控制本次最多推进多少个未完成 conversation：

```bash
memory-benchmark predict formal \
  --method lightmem \
  --benchmark longmemeval \
  --variant s_cleaned \
  --run-id lightmem-longmemeval-s-formal-20260624 \
  --conversation-budget 5 \
  --workers 2 \
  --resume \
  --allow-api
```

含义：

- 本次最多推进 5 个尚未完成的 conversation。
- 如果剩余不足 5 个，自动取剩余数量。
- `--resume` 会复用同一个 run-id 下已完成的 artifact 和 checkpoint。
- 默认不会重跑失败 conversation；只有显式 `--retry-failed` 才考虑重试。

### 9.3 Evaluate

Evaluate 只读取已有 prediction 产物：

```bash
memory-benchmark evaluate \
  --run-id lightmem-longmemeval-s-formal-20260624 \
  --metric llm_judge \
  --workers 4 \
  --allow-api
```

这样同一批 prediction 可以重复计算不同指标。例如先算 F1，后续再补 LLM judge，不需要重新运行 method。

---

## 10. 工程保险机制

### 10.1 API / 网络请求兜底

之前 Mem0 full run 遇到过 embedding API SSL 断连。现在四个内置 method 的 OpenAI-compatible 调用都已经补了基础 timeout / retry：

- Mem0
- MemoryOS
- A-Mem
- LightMem

所以网络请求稳定性不再作为当前阻塞风险，但后续仍需要在更大规模实验中观察真实表现。

### 10.2 异常处理和可诊断性

框架会把错误写入：

- 终端错误信息；
- `logs/run.log`；
- `logs/events.jsonl`；
- `checkpoints/conversation_status.json`。

这样可以定位是哪个 method、哪个 benchmark、哪个 conversation、哪个 question 出错。

### 10.3 可复现性保护

对内置 method，框架会做比较强的 resume 校验。每个 run 都会记录：

- dataset fingerprint；
- method source identity；
- wrapper identity；
- config.redacted；
- model inventory；
- run manifest。

Resume 时会检查关键 identity，避免出现“旧数据集 + 新代码 + 旧 method state”混在一起继续跑的情况。

对用户黑盒 method，不做同等强度的内部状态校验。原因是用户 method 可能把记忆存在自己的数据库、远程服务、向量库或本地文件里，框架无法证明这些内部状态是否真的和当前 run 匹配。

因此用户 method 的 resume 策略是：

- 框架保护自己能看到的内容，例如 run-id、benchmark、public questions、private labels、prediction artifact、checkpoint。
- 用户负责保证自己的 method 按 `conversation_id` 隔离，并能在重新运行时找回对应状态。
- 如果用户 method 在 add 阶段失败，框架不会默认强行重试；除非后续能证明 clean retry 安全，否则 fail closed，避免重复写入半截记忆。

### 10.4 原子写入

原子写入是一个文件安全机制，主要保护 checkpoint、summary 和实验产物文件不被“写到一半的中断”损坏。

举一个真实运行时会遇到的例子：

```text
我们正在跑 LoCoMo formal 实验。
已经完成了 6 个 conversation，框架准备更新 summary.json：

{
  "completed_conversations": 6,
  "completed_questions": 923,
  ...
}

如果程序直接覆盖 summary.json，并且刚写到一半时电脑断电或进程被杀，
磁盘上可能只剩下半截文件：

{
  "completed_conversations": 6,
  "completed_ques

下一次 resume 时，框架读取这个坏掉的 JSON 就会失败，
甚至无法判断哪些 conversation 已经完成。
```

原子写入的处理方式是：

```text
1. 先写临时文件 summary.json.tmp
2. 确认临时文件完整写完
3. 再一次性 rename 成 summary.json
```

这样即使程序在第 1 步或第 2 步中断，旧的 `summary.json` 仍然是完整可读的；如果第 3 步完成，新的 `summary.json` 也是完整可读的。

它的作用是：

- 防止程序中断时留下半截 JSON；
- 防止 checkpoint 写到一半导致 resume 读到坏文件；
- 保证 progress、conversation status、summary 等关键文件更可靠。

需要注意：原子写入解决的是“框架文件写坏”的问题，不解决 method 内部数据库污染。例如某个 method 在 add 阶段已经往向量库写入了 30 条 memory 后崩溃，原子写入不能自动删除这 30 条 memory；这种情况需要 clean retry 或 conversation 级状态清理机制处理。

当前 runner 在写 checkpoint、summary、prediction artifact 等关键产物时使用了项目里的 `atomic_write_json` / `atomic_write_jsonl`。

### 10.5 成本安全门

真实 API 实验需要显式传 `--allow-api`。正式 profile 还会有额外确认，防止误触发大规模付费运行。

---

## 11. 成本和效率观测

当前 prediction 阶段会记录：

| 指标 | 含义 |
| --- | --- |
| `memory_build_latency_ms` | 一个 conversation 构建记忆的总耗时 |
| `retrieval_latency_ms` | 每个 question 检索记忆耗时 |
| `answer_generation_latency_ms` | answer LLM 生成耗时 |
| `injected_memory_context_tokens` | method 检索/构造后注入 answer prompt 的记忆上下文 token |
| `llm_tokens` | 按 stage/model 记录 LLM input/output tokens |
| `embedding_tokens` | 如果 embedding 是 API 或可计量，会记录 embedding input tokens 和 latency |
| `model_inventory` | 记录 answer LLM、judge LLM、memory LLM、embedding model 的身份 |

费用计算和实验运行分离。实验阶段只记录 token 和模型身份；实验结束后再按实际 API 服务商价格离线换算费用。

---

## 12. 当前实验结果

### 12.1 LoCoMo 全量实验

数据来源：

```text
outputs/locomo完整的正确记录/
```

四个 method 均完成 LoCoMo 10 conversations / 1540 questions 的全量 answer 质量评测。

#### Overall

| Method | Run ID | Questions | LoCoMo F1 (%) | LLM Judge Acc (%) |
| --- | --- | ---: | ---: | ---: |
| Mem0 | `mem0-locomo-full-v4` | 1540 / 1540 | 32.09 | 86.36 |
| MemoryOS | `memoryos-locomo-official_full-14b68b2d` | 1540 / 1540 | 44.18 | 57.60 |
| A-Mem | `amem-locomo-full-v2` | 1540 / 1540 | 41.64 | 65.13 |
| LightMem | `lightmem-locomo-0619-1303` | 1540 / 1540 | 50.19 | 69.81 |

说明：

- F1 是 LoCoMo answer-level F1，越高越好。
- LLM Judge Acc 是用 judge LLM 判断回答是否正确，越高越好。
- 两个指标口径不同，因此排序不必完全一致。

#### LoCoMo F1 按类别展开

| Method | Multi-hop | Temporal | Open-domain | Single-hop |
| --- | ---: | ---: | ---: | ---: |
| Mem0 | 32.60 | 34.80 | 18.87 | 32.40 |
| MemoryOS | 35.20 | 43.30 | 30.14 | 49.13 |
| A-Mem | 26.98 | 47.83 | 12.66 | 47.50 |
| LightMem | 36.72 | 60.27 | 25.67 | 53.66 |

#### LoCoMo LLM Judge Acc 按类别展开

| Method | Multi-hop | Temporal | Open-domain | Single-hop |
| --- | ---: | ---: | ---: | ---: |
| Mem0 | 87.23 | 76.32 | 67.71 | 92.03 |
| MemoryOS | 54.96 | 41.43 | 48.96 | 65.64 |
| A-Mem | 59.93 | 52.65 | 39.58 | 74.55 |
| LightMem | 59.57 | 73.52 | 45.83 | 74.55 |

### 12.2 LongMemEval-S 1-conversation cost pilot

数据来源：

```text
outputs/*-longmemeval-s-1conv-costpilot-20260622-s-cleaned/
```

当前只跑了 LongMemEval-S `s_cleaned` 中的 1 个 conversation / 1 个 question。这个结果不能代表最终模型效果，但可以用于估算 full run 成本和耗时。

#### 质量结果

| Method | Completed | LongMemEval Judge Acc |
| --- | ---: | ---: |
| Mem0 | 1 / 500 questions | 100.00% |
| MemoryOS | 1 / 500 questions | 100.00% |
| A-Mem | 1 / 500 questions | 100.00% |
| LightMem | 1 / 500 questions | 100.00% |

该 pilot 样本过小，因此质量分数只说明链路可跑通，不能作为最终结论。

#### 单 conversation 效率观测

| Method | Build Time (s) | Retrieval (ms) | Answer (ms) | LLM Calls | LLM Input | LLM Output | Emb Calls | Emb Input | Context Tokens |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mem0 | 2876.7 | 1216 | 4033 | 278 | 2,556,939 | 49,008 | 827 | 147,377 | 2,597 |
| MemoryOS | 4309.1 | 2579 | 4167 | 1,363 | 704,565 | 109,239 | 921 | 98,615 | 8,232 |
| A-Mem | 5207.2 | 2547 | 4122 | 1,688 | 2,381,972 | 101,923 | 0 | 0 | 9,472 |
| LightMem | 315.3 | 17 | 1736 | 20 | 27,702 | 9,814 | 0 | 0 | 2,008 |

#### 按 500 conversations 线性外推的 GPT-4o-mini 费用参考

这里使用 OpenAI 官方 GPT-4o-mini 价格做参考：

```text
input:  $0.165 / 1M tokens
output: $0.660 / 1M tokens
```

实际费用需要按 ohmygpt 的真实计费价格重新换算。

| Method | 1-conv LLM Cost | 1-conv Judge Cost | 500-conv Estimated LLM+Judge Cost |
| --- | ---: | ---: | ---: |
| Mem0 | $0.4542 | $0.00003 | $227.13 |
| MemoryOS | $0.1884 | $0.00002 | $94.19 |
| A-Mem | $0.4603 | $0.00002 | $230.16 |
| LightMem | $0.0110 | $0.00002 | $5.53 |

注意：

- 上表主要统计 GPT-4o-mini 相关 LLM 调用。
- embedding token 已记录，但未在该表中按价格折算。
- 线性外推只是预算估计，真实 full run 可能因样本长度分布、网络重试、API 服务商计费方式不同而变化。

---

## 13. 当前主要风险

### 13.1 Prompt 公平性

LoCoMo 和 LongMemEval 没有统一强制所有 method 使用同一个 answer prompt。很多 memory method 的 prompt 构造本身就是方法的一部分，例如：

- MemoryOS 会把短期、中期、长期记忆和画像拼到 prompt。
- A-Mem 会先做 query keyword generation 和 category-specific retrieval。
- LightMem 针对 LoCoMo 有专门的 memory organization 和检索逻辑。

因此当前实验属于“method 级系统比较”，不是纯检索模块比较。后续报告结果时需要说明这个口径。

### 13.2 Judge 口径

LLM judge prompt 会影响 accuracy。当前策略：

- LoCoMo 使用我们当前统一的 LoCoMo judge prompt。
- LongMemEval 使用 LightMem LongMemEval 的 yes/no judge 流程，方便与 LightMem 论文结果比较。

后续如果要发表或形成排行榜，需要把 judge prompt 固化并公开。

### 13.3 用户黑盒 method 的隔离能力

内置 method 的状态隔离、source identity、resume、retry 可以由框架维护；用户黑盒 method 的内部数据库或外部服务无法完全由框架证明安全。

因此下一步会把用户 method 接入做成轻量路径，同时写清软契约：

- 必须按 `conversation_id` 隔离。
- 默认 `workers=1`。
- 如果开启并行，需要显式传 `--allow-unsafe-custom-parallel`。
- 如果要重试 add 阶段失败的 conversation，需要提供 clean retry 机制，否则 fail closed。

---

## 14. 下一步计划

### 14.1 LongMemEval 是否扩大规模。

当前已有 1-conversation pilot。

### 14.2 降低新 method 接入难度

目标是让普通用户只写一个 `BaseMemoryProvider` 子类即可跑已有 benchmark：

```text
add(conversation)
retrieve(question) -> prompt_messages
```

计划实现：

- `--method-class module:ClassName` 轻量加载路径。
- 用户 method 默认无参数构造。
- 用户 method 默认 `workers=1`。
- `--allow-unsafe-custom-parallel` 作为并行风险确认。
- failed ingest clean retry preflight，避免脏状态重跑。
- 编写手把手 custom method onboarding 文档和最小可运行示例。

### 14.3 CLI 和实验产物继续产品化

当前 CLI 已经能区分 smoke、formal 和 evaluate，但后续还需要让用户更容易使用：

- 继续清理旧参数的兼容路径，在文档中只保留推荐写法；
- 补充参数异常提示，例如 smoke / formal 参数混用、variant 不存在、run-id 歧义等；
- 增强输出目录说明，让用户更容易理解 prediction、prompt、label、observation、summary 分别是什么；
- 为每个 run 自动生成更适合人阅读的实验摘要，减少用户直接读 JSONL 的负担。

### 14.4 内置 method 的可调参数和 LLM provider 灵活配置

用户运行我们已集成 method 时，应该能通过 TOML 或 CLI 调整不改变核心算法的实验参数，例如：

- answer LLM；
- judge LLM；
- 内置 method 内部 memory LLM；
- embedding model；
- top-k、threshold、compression rate 等 method 白盒超参数。

当前优先支持 OpenAI-compatible API。后续可以扩展 Claude、Gemini、本地 Hugging Face / vLLM / Ollama 等 provider。

### 14.5 BEAM dataset 和更多 conversation-QA benchmark

后续可以继续接入新的 conversation + QA 数据集，例如 BEAM dataset。接入前需要先确认：

- 是否能自然表示为 `Conversation -> Question -> Answer`；
- 是否有明确 gold answer 或 judge 口径；
- 是否需要新的字段，例如时间、多模态、事件证据。

### 14.6 多模态 benchmark

当前实体类保留了图片引用等多模态字段，但 Phase 1 没跑多模态。后续如果接入多模态 benchmark，需要补充：

- image reference 的标准表示；
- 多模态 method adapter 约束；
- 多模态 answer LLM / judge LLM 配置；
- 多模态 artifact 的存储和复现策略。

### 14.7 排行榜和 Web 展示

更长期的方向是把框架产物转成可展示的 leaderboard：

- 不同 method 在不同 benchmark 上的质量指标；
- token、耗时、调用次数等效率指标；

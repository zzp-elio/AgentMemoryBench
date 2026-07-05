# MemoryAgentBench Benchmark 调研卡片

更新日期：2026-06-29

调研依据：

- 论文：`third_party/benchmarks/MemoryAgentBench/MemoryAgentBench.pdf`
- 官方仓库：`third_party/benchmarks/MemoryAgentBench/`
- HuggingFace 数据：`https://huggingface.co/datasets/ai-hyz/MemoryAgentBench/tree/main`
- 本地数据：`data/MemoryAgentBench/`
- 重点核验代码：
  - `third_party/benchmarks/MemoryAgentBench/conversation_creator.py`
  - `third_party/benchmarks/MemoryAgentBench/initialization.py`
  - `third_party/benchmarks/MemoryAgentBench/agent.py`
  - `third_party/benchmarks/MemoryAgentBench/main.py`
  - `third_party/benchmarks/MemoryAgentBench/utils/templates.py`
  - `third_party/benchmarks/MemoryAgentBench/utils/eval_data_utils.py`
  - `third_party/benchmarks/MemoryAgentBench/utils/eval_other_utils.py`
  - `third_party/benchmarks/MemoryAgentBench/llm_based_eval/longmem_qa_evaluate.py`
  - `third_party/benchmarks/MemoryAgentBench/llm_based_eval/summarization_evaluate.py`

## 1. 一句话结论

MemoryAgentBench 不是 LoCoMo 那种自然 conversation-session-turn + QA benchmark。它更像
**chunk-stream memory construction + multi-task QA/evaluation**：每条样本先把一个很长的
`context` 切成 chunks，按顺序喂给 memory agent 进行记忆构建；随后对同一个 context
提出一批问题，并按不同子任务使用 exact match、substring exact match、Recall@5 或
LLM judge 评分。

它对当前框架的主要冲击是：

- 不能简单假设所有 benchmark 都是“一个 conversation 有多个 session，每个 session 有多
  个 turn”。MemoryAgentBench 的基本输入是长文本/文档/对话/示例/事实流统一后的
  `context`。
- 仍然可以把一条 dataset row 映射成一个 `Conversation`，但里面的 event 更准确地说是
  **按 chunk 顺序到来的 memory stream**，不一定是自然对话 turn。
- `BaseMemoryProvider.add(conversation) + retrieve(question)` 可以覆盖一部分接入形态，
  但框架内部需要支持“按 chunk 顺序增量写入”的 loader/runner 语义。
- 完整复现需要多 metric family：普通 QA 准确率、推荐 Recall@5、summary LLM judge、
  LongMemEval LLM judge；这比当前 LoCoMo / LongMemEval 单一 answer-quality 评测更宽。
- method 侧最小能力不是 retrieval recall，而是：**按顺序 ingest 很长的 memory stream，
  并基于构建后的 memory 对多种任务格式输出最终答案**。

## 2. Dataset 数据结构

### 2.1 本地文件与 split

HuggingFace 数据已下载到 `data/MemoryAgentBench/`：

| 文件 | 含义 |
| --- | --- |
| `data/Accurate_Retrieval-00000-of-00001.parquet` | Accurate Retrieval 类任务 |
| `data/Test_Time_Learning-00000-of-00001.parquet` | Test-Time Learning 类任务 |
| `data/Long_Range_Understanding-00000-of-00001.parquet` | Long-Range Understanding 类任务 |
| `data/Conflict_Resolution-00000-of-00001.parquet` | Conflict Resolution / Selective Forgetting 类任务 |
| `entity2id.json` | ReDial movie recommendation 任务的 movie/entity id 映射 |

本地 parquet 抽样统计：

| split | rows | questions 总数 | 主要 source |
| --- | ---: | ---: | --- |
| `Accurate_Retrieval` | 22 | 2000 | `eventqa_*`、`longmemeval_s*`、`ruler_qa1_197K`、`ruler_qa2_421K` |
| `Test_Time_Learning` | 6 | 700 | `icl_*`、`recsys_redial_full` |
| `Long_Range_Understanding` | 110 | 171 | `infbench_sum_eng_shots2`、`detective_qa` |
| `Conflict_Resolution` | 8 | 800 | `factconsolidation_sh_*`、`factconsolidation_mh_*` |
| **合计** | **146** | **3671** | 4 个 split / 多个 source |

这里的 `rows` 就是 MemoryAgentBench 的隔离单元：**1 row = 1 context = 1 个独立 memory
state**。同一 row 下有多个 questions；这些 questions 都只能基于该 row 的 `context`
回答。不同 row/context 之间不能共享记忆。

### 2.2 顶层字段

四个 split 的 parquet 顶层字段一致：

| 字段 | 类型 | evaluation 中的作用 | 是否给 method |
| --- | --- | --- | --- |
| `context` | string | 被切 chunk 后按顺序喂给 agent 记忆构建；是最核心的 public history | 是 |
| `questions` | list[string] | 同一条 context 下要回答的问题列表 | 是，逐题给 |
| `answers` | list[list[string]] | 每个 question 的 gold answer 或 alias 列表 | 否，只给 scorer |
| `metadata` | struct | source、question id、question type、judge 所需 keypoints 等 | 部分给 runner/scorer；默认不直接给 method |

`metadata` 里 evaluation 会用到的字段：

| 字段 | 类型 | 作用 | public/private 判断 |
| --- | --- | --- | --- |
| `source` | string | 决定子任务、prompt 模板和 metric | runner 可见 |
| `qa_pair_ids` | list[string] | 输出 artifact 对齐、resume 和 judge 对齐 | runner/scorer 可见；不作为答案线索 |
| `question_ids` | list[string] | LongMemEval / LLM judge 对齐 | scorer 可见 |
| `question_types` | list[string] | LongMemEval judge prompt 选择、分类聚合 | scorer 可见；一般不直接给 method |
| `question_dates` | list[string] | LongMemEval 问题时间；部分问题文本已包含 current date | 可作为 question metadata；需谨慎确认 |
| `haystack_sessions` | nested list | LongMemEval evidence/haystack session 结构，含 `has_answer` | private evidence，不应直接给 method |
| `previous_events` | list[string] | EventQA 问题相关 previous event；多数已写进 question 文本 | 若 question 已包含则不额外给 method |
| `keypoints` | list[string] | InfBench summary / DetectiveQA judge 或参考要点 | private scorer label |
| `demo` | string | summary / detectiveQA 的示例 prompt 片段 | 有些 question 已内嵌示例；不要额外泄露 private label |

### 2.3 各 split 的真实输入形态

#### Accurate Retrieval

包含四类主要 source：

| source | rows | 输入形态 | questions/answers 形态 | metric |
| --- | ---: | --- | --- | --- |
| `ruler_qa1_197K` | 1 | 多个 `Document N: ...` 拼成的长文档 | 普通 QA，gold answer 可有 alias | Substring exact match |
| `ruler_qa2_421K` | 1 | 更长文档集合，含多跳问题 | 普通 QA / yes-no / multi-hop | Substring exact match |
| `eventqa_full`、`eventqa_65536`、`eventqa_131072` | 15 | 小说/书籍长文本 | question 常包含 previous events 和 candidate events，answer 是正确 event 文本 | 代码里有 EventQA recall/accuracy 风格判断 |
| `longmemeval_s*` | 5 | 字符串化的多 session chat history | 每 row 60 个问题；question 常含 `Current Date` | LLM judge accuracy |

`longmemeval_s*` 的 `context` 看起来像按时间排列的 chat session 列表，session 里有
`role/content`。但官方 MemoryAgentBench 代码并不是直接把 `haystack_sessions` 作为
evidence 喂给 method，而是把完整 `context` 切成 chunks 后按顺序写入 agent memory。

#### Test-Time Learning

包含 ICL 分类和 ReDial 推荐：

| source | rows | 输入形态 | 输出要求 | metric |
| --- | ---: | --- | --- | --- |
| `icl_banking77_5900shot_balance` | 1 | 大量 `sentence + label` 示例 | 输出数字 label | Exact match |
| `icl_clinic150_7050shot_balance` | 1 | 大量分类示例 | 输出数字 label | Exact match |
| `icl_nlu_8296shot_balance` | 1 | 大量分类示例 | 输出数字 label | Exact match |
| `icl_trec_coarse_6600shot_balance` | 1 | 大量分类示例 | 输出数字 label | Exact match |
| `icl_trec_fine_6400shot_balance` | 1 | 大量分类示例 | 输出数字 label | Exact match |
| `recsys_redial_full` | 1 | 多轮 user/recommender 对话历史 | 输出推荐 movie list / ids | Recall@5 |

ReDial 任务依赖 `entity2id.json`。官方 metric 代码默认从
`./processed_data/Recsys_Redial/entity2id.json` 读取；HF 下载后该文件位于
`data/MemoryAgentBench/entity2id.json`。接入时必须显式重定向或复制该文件，否则
Recsys metric 会找不到路径。

#### Long-Range Understanding

| source | rows | 输入形态 | 输出要求 | metric |
| --- | ---: | --- | --- | --- |
| `infbench_sum_eng_shots2` | 100 | 长书籍/长文档 | 1000-1200 words summary | GPT-4o judge F1 |
| `detective_qa` | 10 | 带行号或长篇推理文本 | 按 question 要求输出答案/推理，常见 MCQ/JSON 形式 | Exact match / accuracy |

`infbench_sum_eng_shots2` 的 `metadata.keypoints` 是 summary judge 的关键私有标签，不能给
method。`answers[0]` 是 expert summary。官方 `summarization_evaluate.py` 会同时使用
keypoints 和 expert summary。

#### Conflict Resolution / Selective Forgetting

| source | rows | 输入形态 | 输出要求 | metric |
| --- | ---: | --- | --- | --- |
| `factconsolidation_sh_*` | 4 | 带序号事实流，后出现的事实更新旧事实 | 基于最新事实回答单跳问题 | Substring exact match |
| `factconsolidation_mh_*` | 4 | 带序号事实流，多跳冲突解析 | 基于最新事实回答多跳问题 | Substring exact match |

论文中这类能力常被称为 Selective Forgetting；HF split 名是
`Conflict_Resolution`。对 method 来说，这不是显式 delete API，而是通过按时间/序号写入
相互冲突事实，要求回答时采用最新有效事实。

### 2.4 `context`、`chunk`、`question` 的真实内层结构

MemoryAgentBench 的 `context` 在 parquet 中就是一个超长 `string`，不是嵌套 JSON，也
不是 session/turn 结构。不同 source 的字符串语义差异很大：

| source 类型 | `context` 字符串示例语义 |
| --- | --- |
| `ruler_qa*` | 多个 `Document N: ...` 拼成的长文档 |
| `longmemeval_s*` | 字符串化的 chat sessions，文本中保留 `Chat Time`、`role`、`content` |
| `eventqa_*` | 小说/事件长文本 |
| `recsys_redial_full` | `Dialogue N: System: ... User: ...` 推荐对话串 |
| `icl_*` | 大量 `sentence ... label: N` 示例 |
| `infbench_sum_eng_shots2` / `detective_qa` | 长书籍/长篇推理文本 |
| `factconsolidation_*` | `Here is a list of facts: 0. ...` 的序号事实流 |

`chunk` 不是 dataset 原生字段，而是运行时从 `context` 切出来的 `list[str]`。官方
`utils/eval_other_utils.py::chunk_text_into_sentences` 的逻辑是：按句子切分，再按
`chunk_size` 的 token budget 累加句子，超过预算就开启下一个 chunk。这个策略只保证
尽量不在句子中间硬切；**不保证**保留 LongMemEval session 边界、user/assistant round
边界、文档边界或 evidence 边界。

因此官方实际范式是：

```text
context: str
  -> chunk_0: str
  -> chunk_1: str
  -> ...

for chunk in chunks:
    formatted_memory_input = memorize_template(source).format(context=chunk)
    agent.send_message(formatted_memory_input, memorizing=True)
```

如果原始 source 内部有结构化语义，例如 LongMemEval 的 user/assistant 和时间，它们也只是
作为字符串内容被保留在 chunk 中。官方没有把这些字段重新解析成结构化 message 再传给
method。

`questions` 是绑定在同一个 `context` 下的问题列表：

```text
context_i
  questions[0] -> answers[0] -> metadata.qa_pair_ids[0]
  questions[1] -> answers[1] -> metadata.qa_pair_ids[1]
```

官方 `ConversationCreator` 会逐题用 source-specific query template 格式化。也就是说，
method 看到的 query 也通常不是裸 question，而是“按任务说明包装后的问题”。

## 3. Evaluation 流程

### 3.1 官方统一流程

官方代码把所有子任务统一成以下流程：

1. 读取 dataset config，确定 `dataset`、`sub_dataset`、`chunk_size`、
   `generation_max_length`、`max_test_samples`。
2. `conversation_creator.py` 用 HuggingFace dataset 读取 split，并按
   `metadata.source == sub_dataset` 过滤样本。
3. 对每条样本取出：
   - `context`
   - `questions`
   - `answers`
   - `qa_pair_ids`
4. 用 `chunk_text_into_sentences(context, chunk_size=...)` 把长 context 切成 chunks。
5. 为每个 context 创建一个独立 agent state 目录，例如 `exp_{context_index}`。
6. Memory construction phase：
   - 对每个 chunk 调用 `agent.send_message(chunk, memorizing=True)`。
   - `utils/templates.py` 会按 `sub_dataset` 把 chunk 包成“我读过/学过/看到的上下文”的
     user message。
7. Query execution phase：
   - 对同一 context 下所有 questions 逐题调用
     `agent.send_message(query, memorizing=False, query_id=..., context_id=...)`。
   - agent 用自己的 memory backend 检索/组织上下文，再调用 answer LLM 输出答案。
8. `utils/eval_other_utils.py` 先保存 per-query 结果和轻量 string metrics。
9. LongMemEval 和 InfBench summary 需要额外运行 `llm_based_eval/` 下的 LLM judge 脚本。

一个 dataset row 就是一个独立 context / 独立 memory state。不同 row 之间不能共享记忆。

需要强调：第 6 步不是“一次性把完整 context 放进 method”，而是 **一个 chunk 一个
chunk 写入**。`utils/templates.py` 中的 `{context}` 变量在 memorization 阶段表示当前
chunk，而不是整条 row 的完整 context。

### 3.2 各任务的 evaluation 差异

| 类别 | method 看到的内容 | method 需要输出 | scorer 方式 |
| --- | --- | --- | --- |
| RULER QA | 长文档 chunks | 简短答案 | substring exact match |
| LongMemEval | 长期 chat history chunks + 带 current date 的 question | 自然语言答案 | GPT-4o yes/no judge |
| EventQA | 小说/事件文本 chunks + candidate event question | 被问到的 event 文本 | event recall / substring 类判断 |
| ICL classification | 大量带 label 示例 chunks + 新分类样本 | 数字 label | exact match |
| ReDial recsys | 历史推荐对话 chunks + 新对话/query | movie id/name list | Recall@5 |
| InfBench summary | 长文本 chunks | 长摘要 | GPT-4o fluency/recall/precision judge |
| DetectiveQA | 长篇推理文本 chunks | 指定格式答案/推理 | exact match / accuracy |
| FactConsolidation | 带序号事实流 chunks | 基于最新事实的答案 | substring exact match |

### 3.3 官方对不同 method 的 chunk 写入方式

MemoryAgentBench 官方对各类 method 的写入方式都遵循“formatted chunk as text”的粗粒度
范式，只是后端调用不同：

| method / backend | memorizing=True 时怎么写入 chunk |
| --- | --- |
| Long-context agent | 将 `memorize_template.format(context=chunk)` 追加到 `self.context` 字符串 |
| Mem0 | 构造 `system + user(formatted chunk) + assistant acknowledgement`，调用 `memory.add(..., user_id=context_id)` |
| Letta | formatted chunk 作为 passage 或 user message 写入 |
| Cognee | `cognee.add(formatted_chunk, dataset_name=context_id)` 后 `cognee.cognify(...)` |
| Zep | formatted chunk 写入对应 user/thread/graph |
| BM25 / RAG / GraphRAG 等 | formatted chunk append 到 `self.chunks`，查询时构建索引或检索 |

以 Mem0 为例，官方并不会解析 LongMemEval chunk 里的 `role/content`，而是把
source-specific formatted chunk 包成一段对话消息写入 memory：

```text
system: You are a helpful assistant that can read the context and memorize it...
user: The following context is ...
      {chunk}
assistant: I'll make sure to add the content into the memory.
```

这说明 MemoryAgentBench 默认假设 method 有能力从一段自然语言/字符串化上下文中自行抽取
记忆。它牺牲结构精度，换取跨 documents、books、facts、examples、dialogues 的统一接入。

### 3.4 与当前框架的映射

MemoryAgentBench 可以被临时映射成：

```text
Dataset row -> Conversation
context chunks -> Conversation.messages / Memory stream events
question -> Question
answers/keypoints/question_types -> private labels for scorer
```

但这里的 `Conversation` 不再是“自然对话 session-turn”语义，而是一个更宽泛的
memory stream。当前框架如继续使用 `Conversation`，需要在 metadata 中明确：

- `task_family = "chunk_stream_qa"` 或类似标识。
- 每个 event 的 `metadata.chunk_index`、`metadata.source`、`metadata.sub_dataset`。
- question 的 `metadata.source`、`metadata.qa_pair_id`、`metadata.question_type`、
  `metadata.question_date` 等。

不要把 `answers`、`keypoints`、`haystack_sessions.has_answer`、summary reference 等私有
label 传给 method。

## 4. Metric 计算方式

### 4.1 官方 string metrics

`utils/eval_other_utils.py` 提供通用字符串指标：

| metric | 代码逻辑 |
| --- | --- |
| `exact_match` | normalize 后预测完全等于任一 gold |
| `substring_exact_match` | normalize 后任一 gold 是预测子串，或预测是任一 gold 子串 |
| `f1` | token-level precision/recall/F1，取多个 gold 的最大值 |
| `rougeL_f1` / `rougeL_recall` | Rouge-L |
| `rougeLsum_f1` / `rougeLsum_recall` | Rouge-Lsum |

官方 README / 论文主指标不是统一 F1，而是按 source 选择：

| 任务 | 主指标 |
| --- | --- |
| RULER QA | Accuracy / substring exact match |
| EventQA | Accuracy / event recall 风格判断 |
| ICL classification | Accuracy / exact match |
| FactConsolidation | Accuracy / substring exact match |
| DetectiveQA | Accuracy / exact match |
| ReDial recommendation | Recall@5 |
| LongMemEval | LLM-as-judge accuracy |
| InfBench summary | LLM-as-judge F1 |

### 4.2 ReDial Recall@5

ReDial 会把模型输出解析成 movie candidates，再和 gold movie ids 对齐。主指标是
Recall@5，也就是 top 5 推荐中命中 gold item 的比例。该指标依赖 `entity2id.json`。

注意：这里的 Recall@5 是 **最终推荐结果** 的 Recall@5，不是 memory retrieval recall。
官方没有要求 method 输出 top-k retrieved memories，也没有拿 retrieved memories 和 gold
evidence 计算 Recall@K。MemoryAgentBench 整体仍然是 end-to-end output evaluation。

### 4.3 LongMemEval LLM judge

`llm_based_eval/longmem_qa_evaluate.py` 会按 question type 选择 prompt，并让 GPT-4o
判断回答是否正确。最终指标是：

```text
correct = "yes" in judge_response.lower()
accuracy = correct_count / total_questions
```

它还会按 `question_type` 聚合，例如：

- `single-session-user`
- `single-session-assistant`
- `single-session-preference`
- `multi-session`
- `temporal-reasoning`
- `knowledge-update`

### 4.4 InfBench summary LLM judge

`llm_based_eval/summarization_evaluate.py` 使用三类 judge：

1. Fluency：摘要是否流畅，分数 0 或 1。
2. Recall：摘要覆盖了多少 keypoints。
3. Precision：摘要中的句子有多少被 expert summary 支持。

最终分数：

```text
summary_f1 = fluency * 2 * recall * precision / (recall + precision)
```

如果 recall 和 precision 都为 0，则 F1 为 0。

### 4.5 Artifact-only 复算需求

若要在我们框架中支持 artifact-only evaluation，prediction artifact 至少需要保存：

- `dataset` / `sub_dataset` / `source`
- `context_id` 或 row index
- `question_id` / `qa_pair_id`
- `question`
- `prediction`
- `gold answers` 的私有 evaluator artifact
- LongMemEval 的 `question_type` 和 `question_id`
- Summary 的 `keypoints` 和 expert summary
- Recsys 的 entity/movie id 映射版本

## 5. Answer LLM / Judge LLM 配置和 Prompt

### 5.1 Answer LLM 配置

官方 `agent.py` 中，常规 OpenAI chat completion 调用使用：

```text
model = agent config 中的 model
temperature = agent config 中的 temperature
max_tokens = dataset config 中的 generation_max_length
```

常见配置：

| agent / backend | model | temperature | 其他 |
| --- | --- | ---: | --- |
| long context GPT-4o-mini | `gpt-4o-mini` | 0.7 | `input_length_limit=128000`，buffer 4000 |
| Mem0 baseline | `gpt-4o-mini` | 0.7 | `agent_chunk_size=4096`，`retrieve_num=100` |
| BM25 / embedding RAG | `gpt-4o-mini` | 0.7 | 常见 `retrieve_num=10` |
| text-embedding-3-small RAG | `gpt-4o-mini` | 0.7 | embedding retrieval |

dataset config 中的 `generation_max_length` 控制 max output tokens。论文 Table 14 给出的
典型值：

| 任务 | max output tokens |
| --- | ---: |
| SH-QA / MH-QA | 50 |
| LME(S*) | 100 |
| EventQA | 40 |
| MCC / ICL classification | 20 |
| Movie Recommendation | 300 |
| InfBench-Sum | 1200 |
| DetectiveQA | 500 |
| FactConsolidation | 10 |

注意：本地 YAML / config 与论文表格存在不一致风险。例如 `Detective_QA` 配置里看到过
`generation_max_length=2000`，而论文表格写 500；`longmemeval_s*` 配置也可能与表格 100
不完全一致。复现主表时必须以具体运行脚本和 config override 为准。

### 5.2 Memory construction prompt

`utils/templates.py` 里定义了按 `sub_dataset` 切换的 memorization prompt。核心语义是把
每个 chunk 包成一条“请记住我读过/学过的上下文”的 user message。例如：

- RULER：`The following context is the documents I have read...`
- LongMemEval：`The following context is the conversation between the user and the assistant...`
- EventQA：`The following context is the book excerpt...`
- ICL：`The following context is the examples I have learned...`
- ReDial：`The following context is the dialogues between a user and recommender system...`
- InfBench / DetectiveQA：`The following context is the book I have read...`
- FactConsolidation：`The following context is the facts I have learned...`

这说明 MemoryAgentBench 官方并不是直接把 raw context 原样写入 method，而是通过
sub-dataset-specific prompt 诱导 agent 把 chunk 写入 memory。

这些 prompt 也进一步说明：MemoryAgentBench 的 memory construction 输入是“文本流”，
不是结构化 conversation。对同一个 `context` 切出的每个 chunk，都会使用相同 source 的
memorize prompt 单独写入。

### 5.3 Query / Answer prompt

官方 query prompt 也在 `utils/templates.py`。不同 agent type 有不同模板：

- long context agent：直接把问题作为用户请求。
- RAG agent：先检索 chunks，再把检索结果拼进 prompt。
- agentic memory agent：可能要求 agent 主动搜索 archival memory。

Mem0 baseline 的官方逻辑比较清楚：

1. 写入时把 formatted chunk 包成 `system + user + assistant acknowledgment` messages，
   调 `memory.add(..., user_id=f"context_{context_id}_{sub_dataset}")`。
2. 查询时调 `memory.search(query=question, user_id=..., limit=retrieve_num)`。
3. 将检索出的 memory 拼成 bullet list 放入 system prompt。
4. 再用 OpenAI chat completion 生成最终 answer。

### 5.4 Judge LLM 配置

LongMemEval judge：

| 项 | 配置 |
| --- | --- |
| 文件 | `llm_based_eval/longmem_qa_evaluate.py` |
| 模型 | `gpt-4o` |
| temperature | 0 |
| max_tokens | 10 |
| 输出解析 | judge response 包含 `yes` 即认为正确 |
| prompt | 按 `question_type` 选择 yes/no correctness rubric |

Summary judge：

| 项 | 配置 |
| --- | --- |
| 文件 | `llm_based_eval/summarization_evaluate.py` |
| 模型 | `gpt-4o-2024-05-13` |
| temperature | 0.1 |
| generation_max_length | 4096 |
| prompt | fluency、recall、precision 三类 prompt |
| 输出解析 | XML/标签式解析分数，再计算 F1 |

未发现 RULER、ICL、ReDial、FactConsolidation、EventQA、DetectiveQA 在官方代码中使用独立
LLM judge 作为主流程；这些任务主要使用字符串匹配、Recall@5 或专门解析逻辑。

## 6. Method Adapter 接口需求

### 6.1 最小能力

一个新 method 想完整跑 MemoryAgentBench，最少需要支持：

```text
start isolated context / conversation
for chunk in context_chunks:
    ingest(chunk in original order)
for question in questions:
    answer question using built memory
```

映射到我们当前接口，可以暂定为：

```python
add(conversation)
retrieve(question) -> AnswerPromptResult
```

但这里的 `conversation` 必须允许表示 “chunk stream”，而不是只表示自然对话 session。
`retrieve(question)` 最好返回完整 `prompt_messages`，因为不同 source 的 answer prompt、
输出格式和检索内容拼接方式差异很大。

如果未来为 MemoryAgentBench 单独设计更贴近官方流程的接口，最小语义可以是：

```python
add_text(context_id: str, text: str, metadata: dict | None = None) -> None
retrieve(question) -> AnswerPromptResult
```

这里的 `text` 建议是 framework 已经套好 source-specific memorize prompt 的字符串。
也就是说，普通 method adapter 第一版只需要把这段 text 当作待记忆内容写入自己的记忆库，
不强制解析 chunk 内部结构。`metadata` 可以包含 `source`、`chunk_index`、`split` 等调试
信息，但不是最小 public contract 的核心。

### 6.2 对当前 `BaseMemoryProvider` 的适配判断

| 能力 | 是否需要 | 对当前框架的影响 |
| --- | --- | --- |
| conversation/context 隔离 | 必需 | 每个 dataset row 必须独立 memory state |
| chunked incremental ingest | 必需 | loader/runner 要按 chunk 顺序喂入，不能只假设 turn/round |
| retrieve / answer prompt 构造 | 必需 | method 或 framework 必须知道 source-specific query template |
| answer quality evaluation | 必需 | 多 metric family，需要多个 evaluator profile |
| retrieval recall | 不需要作为主指标 | 不应作为 method 必需接口 |
| delete / explicit forget API | 不需要 | Conflict Resolution 是“新事实覆盖旧事实”，不是显式删除 |
| multimodal | 不需要 | 当前数据是纯文本 |
| tool/environment action | 不需要 | 没有外部动作环境 |
| long summary output | 必需 | InfBench summary max output 很长，runner 要支持长答案 |
| recommendation output | 必需 | ReDial 需要解析 top-k movie recommendation |

### 6.3 普通用户 method 接入会遇到的难点

如果用户只实现最简单的 `add(conversation)` 和 `retrieve(question)`，对 MemoryAgentBench
会遇到几个额外要求：

1. `add()` 必须按 chunk 顺序处理 context，不能打乱顺序。
2. `retrieve()` 需要根据 `question.metadata["source"]` 选择正确输出格式。例如 ICL 要输出
   label，ReDial 要输出 movie list，summary 要输出长摘要。
3. 如果 method 内部没有 answer LLM，只返回 memory context，则框架需要提供
   source-specific answer prompt；否则不同子任务会无法公平运行。
4. `context` 很长，1M token 级别样本不能简单一次性放进 LLM prompt。method 必须有真实的
   memory construction 能力，或框架 loader 必须提供可恢复的分块写入。
5. LLM judge 所需的 `keypoints`、`question_type`、reference summary 等必须留在 scorer
   私有侧，不能泄露给 method。

### 6.4 对 MemoryOS 这类 dialogue-page method 的风险

MemoryAgentBench 的 chunk-stream 范式更适合 Mem0 这类“输入一段 message/dialogue 后由
LLM 抽取 memory”的方法。MemoryOS 则更偏对话页管理：官方设计通常是
`user_input + agent_response` 作为 QA/dialogue page 进入 short-term memory，再由 STM
更新到 MTM/LTM。

因此 MemoryOS 可以做一个兼容版 `add_text`：

```text
user_input = formatted_chunk
agent_response = "I have stored this information for future questions."
```

但这不是 MemoryOS 原生最舒服的输入形态，风险包括：

- 超长 chunk 作为单个 dialogue page 进入 STM，可能破坏 page 粒度。
- MTM summarization 可能把 documents / facts / examples 当成普通对话总结。
- LTM profile / knowledge 更新可能把书籍、事实流或分类样例误认为用户偏好或用户知识。
- 不同 source 全部以同一种 user_input 形式进入 MemoryOS，可能造成语义污染和成本膨胀。

所以如果以后把 MemoryOS 跑在 MemoryAgentBench 上，应在报告中标明这是
`text-stream compatibility adapter`，不是 MemoryOS LoCoMo-style dialogue-page 的原生最优
适配。除非明确要为 MemoryOS 做 source-specific 深度适配，否则第一版应保持官方一致的
formatted chunk 写入范式，避免 benchmark adapter 过度帮某个 method 优化。

### 6.5 对当前架构的结论

MemoryAgentBench 暂时不要求我们立刻推翻 retrieve-first 方向，但它提示当前
conversation-QA 定义过窄：

- 如果把 “Conversation” 扩展为 “method public memory stream”，则当前
  `BaseMemoryProvider.add + retrieve` 可以继续覆盖。
- 如果坚持 “Conversation = session + turn”，则 MemoryAgentBench 应归为新的
  `chunk-stream + QA` task family。
- 后续更稳妥的设计是：保留 `BaseMemoryProvider`，但让 dataset adapter 可以产出
  `MemoryStream` / `Conversation` 两种视图；普通 method 仍只实现 add/retrieve。

## 7. 未确认项

1. README 中示例脚本路径写作 `bash_files/eniac/...`，但本地仓库实际脚本位于
   `bash_files/sh/...`。
2. 论文 Table 14 的 max output tokens 与部分本地 config 不完全一致，例如
   `Detective_QA` 和 `longmemeval_s*`。复现主表前必须锁定具体 shell config 和 override。
3. 论文 Table 15 写部分任务 chunk size 为 512，但本地 YAML 默认常见 4096；shell
   ablation/config 文件又可能传入 512。主实验 profile 需要进一步核对运行命令。
4. ReDial metric 默认查找 `./processed_data/Recsys_Redial/entity2id.json`，而 HF 下载路径是
   `data/MemoryAgentBench/entity2id.json`。接入时必须处理路径差异。
5. `Conflict_Resolution` split 与论文中的 Selective Forgetting 命名需要在 adapter 和报告中
   统一说明，避免误以为是两个不同 benchmark。
6. 部分 shell 脚本硬编码 config line range，不构成完整复现实验矩阵说明。真正复现需要
   明确每个 source 对应的 agent config、data config、chunk size 和 generation length。
7. 需要进一步决定 MemoryAgentBench 在我们框架中是归入扩展后的 conversation-QA，还是作为
   `chunk-stream QA` 新 task family 单独建 loader/evaluator。
8. 当前调研已确认官方 prompt 和 metric 主体，但尚未跑官方代码端到端复现任一子任务；后续
   接入前应先用 1 row / 1 question 做官方脚本 smoke，对照 artifact 字段。

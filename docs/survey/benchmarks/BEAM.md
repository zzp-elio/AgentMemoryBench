# BEAM Benchmark 调研卡片

更新日期：2026-07-11（B4 `frozen-v1`；**现行契约以
`docs/survey/datasets/BEAM.md` + `docs/survey/workflows/BEAM.md` 两张
契约卡与冻结记录
`docs/workstreams/ws02.6-first-smoke-hardening/notes/beam-frozen-v1.md`
为准**；本卡正文为 2026-06-29 调研期材料。要点更正：① 官方有效评测面
零嵌入零 BLEU/ROUGE（均为分发链外死代码），event_ordering 的 alignment
实际走 LLM 判等；② 官方 judge int() 截断是真 bug（prompt 明定 0.5 档），
框架双轨 float+official_int；③ 10M 顶层 chat = list[plan-dict]，10m
variant 已接纳；④ 官方代码 commit 已锁 3e12035。）

调研依据：

- 论文：`third_party/benchmarks/BEAM/beam.pdf`
- 官方仓库：`third_party/benchmarks/BEAM/`
- 本地 HuggingFace 数据：`data/BEAM/beam_dataset`、`data/BEAM/beam_10M_dataset`
- 重点核验代码：
  - `third_party/benchmarks/BEAM/src/answer_probing_questions/answer_generation.py`
  - `third_party/benchmarks/BEAM/src/answer_probing_questions/long_term_memory_methods.py`
  - `third_party/benchmarks/BEAM/src/answer_probing_questions/light.py`
  - `third_party/benchmarks/BEAM/src/evaluation/run_evaluation.py`
  - `third_party/benchmarks/BEAM/src/evaluation/compute_metrics.py`
  - `third_party/benchmarks/BEAM/src/evaluation/report_results.py`
  - `third_party/benchmarks/BEAM/src/prompts.py`

## 1. 一句话结论

BEAM 是一个 **超长 conversation + probing question** benchmark。它的 evaluation 单位是
一个完整 conversation；每个 conversation 后面有 10 类 memory ability 的 probing
questions。method 需要基于 conversation 历史回答 probing question，scorer 再用私有
rubric nuggets 和 LLM judge 评价回答质量。

BEAM 仍然可以暂时归入 conversation-QA 大类，但它比 LoCoMo / LongMemEval 更强地考察
“长期记忆能力矩阵”，而不是单一 QA F1 或 yes/no accuracy。它对当前框架的主要冲击是：

- method 侧第一版仍可维持 `add(conversation) + retrieve(question)`。
- 不需要新增 delete / forget / reset / retrieval-recall 主接口。
- evaluator 需要新增 rubric-nugget LLM judge、ability 级聚合和 event-ordering 特殊指标。
- dataset loader 需要处理 100K/500K/1M/10M 超长 conversation 和 10M 特殊 plan 层级。
- 1M / 10M 会对一次性 `add(conversation)` 造成工程压力，未来可能需要框架内部支持
  streaming / iterator ingest，但这不一定暴露为普通用户必须实现的新接口。

## 2. Dataset 数据结构

### 2.1 Split 和规模

`data/BEAM/beam_dataset`：

| split | 样本数 | 说明 |
| --- | ---: | --- |
| `100K` | 20 | 论文/README 有时称 128K，本地 HF split 名为 `100K` |
| `500K` | 35 | 约 500K token conversation |
| `1M` | 35 | 约 1M token conversation |

`data/BEAM/beam_10M_dataset`：

| split | 样本数 | 说明 |
| --- | ---: | --- |
| `10M` | 10 | 约 10M token conversation |

README 和论文称 BEAM 共 100 个 conversations、2,000 个 validated questions。按设计，
每个 conversation 有 10 类能力、每类 2 个 probing questions。

注意：代码实现和本地数据使用 split 名 `100K`，论文文字中常写 `128K`。后续 adapter /
loader 应保留本地 split 名，不要自行把 `100K` 改成 `128K`。

### 2.2 一个 sample 的顶层字段

普通 split（`100K` / `500K` / `1M`）中，单个 sample 顶层字段如下：

| 字段 | 类型 | evaluation 作用 | 默认是否给 method |
| --- | --- | --- | --- |
| `conversation_id` | string | conversation 级隔离 id | 是 |
| `chat` | list | 真正被 answer generation 使用的对话历史 | 是 |
| `probing_questions` | string | 需要解析成 dict；包含问题文本和私有评分标签 | 只给 `question` 文本 |
| `conversation_seed` | dict | 生成数据用的主题/类别/子主题 | 否 |
| `narratives` | string | 生成 conversation 的叙事标签 | 否 |
| `user_profile` | dict | 生成用户画像和关系 | 默认否；除非 official profile 明确允许 |
| `conversation_plan` | string | 生成用计划/时间线 | 否 |
| `user_questions` | list | 生成用户消息的中间材料 | 否 |

10M split 额外包含：

| 字段 | 类型 | evaluation 作用 |
| --- | --- | --- |
| `plans` | list | 10M conversation 的多 plan 数据；官方转换脚本会逐 plan 生成 `chat.json` |

当前 public/private 边界建议：

- method public input：`conversation_id`、`chat` 中的 `role/content/id/index/time_anchor`、
  probing `question`。
- scorer private labels：`rubric`、`ideal_response`、`ideal_answer`、`answer`、
  `ideal_summary`、`source_chat_ids`、`conversation_references`、`plan_reference`、
  `why_unanswerable`、`tests_for` 等。
- `conversation_seed`、`user_profile`、`conversation_plan`、`user_questions` 暂不默认给
  method，因为官方 answer generation 是围绕 `chat` 构造输入；这些字段更像数据生成
  元信息。后续如要做 profile-aware 特殊 profile，必须显式记录。

### 2.3 `chat` 的真实结构

BEAM 这里有一个容易误判的地方：**本地 HuggingFace Arrow 数据和官方 evaluation 中间
JSON 不是完全同一层级。**

本地 `data/BEAM/beam_dataset` 普通 split 中，抽样看到的原始 `chat` 结构是：

```text
chat
  -> batch_list
    -> message
```

也就是 `chat` 是 batch 列表，每个 batch 内直接是 message list。message 字段包括：

| 字段 | 说明 |
| --- | --- |
| `role` | `user` 或 `assistant` |
| `content` | 消息正文 |
| `id` | message id，可用于 provenance 和 source 对齐 |
| `index` | 生成时索引，例如 `1,1` |
| `question_type` | 例如 `main_question`，可用于官方转换时切 turn |
| `time_anchor` | 可选时间锚点，例如 `March-15-2024` |

官方 `src/beam/download_dataset.py` 会调用 `convert_chats_pickle_to_json(data=chat)`，
把 HF 原始结构转换成 answer generation 使用的中间格式：

```text
chat.json
  -> batch
    -> batch_number
    -> time_anchor
    -> turns
      -> turn
        -> message
```

这个转换规则会用 `question_type == "main_question"` 切分 turn。后续如果我们直接从
`data/BEAM` 加载，需要自己实现等价转换，不能直接照搬
`long_term_memory_methods.py` 对 `batch["turns"]` 的假设。

这里的 `turns` 名字容易误导。官方中间 `chat.json` 中的 `turns` 不是“单条 message
turn”，而是一个 **main-question group** 列表：

```text
batch["turns"]
  -> turn_group_0 = [main_question, assistant_response, optional answer_ai_question/followup, ...]
  -> turn_group_1 = [next main_question, assistant_response, ...]
```

也就是说，遇到新的 `question_type == "main_question"` 时，官方转换脚本就开启一个新的
inner list。这个结构主要服务 BEAM 的数据生成、证据定位和长上下文裁剪；method 侧
evaluation 不应被迫理解这层结构。接入我们框架时建议：

```text
BEAM batch            -> segment / session-like unit
BEAM turn inner list  -> metadata 中的 beam_turn_group_index
BEAM message          -> 真正喂给 method 的 message / turn
```

另一个容易踩坑的字段是 `batch["time_anchor"]`。本地
`third_party/benchmarks/BEAM/chats/100K/1/chat.json` 中 batch 级 `time_anchor` 为 `null`，
但每个 batch 第一条 `main_question` message 通常有真实时间，例如
`March-15-2024`、`April-05-2024`。根因是官方 `convert_chats_pickle_to_json` 只在
`single_turn != []` 时更新 batch `time_anchor`，会跳过 batch 第一条 message 的时间。
因此未来 loader 不应直接信任 batch-level `time_anchor`，而应按如下规则补齐：

```text
segment_time = batch.time_anchor
if segment_time is None:
    segment_time = batch 内第一条非空 message.time_anchor
```

10M split 的 `chat` 结构又多一层 plan。抽样看到：

```text
chat
  -> plan holder
    -> plan-1 / plan-2 / ...
      -> batch
        -> batch_number
        -> time_anchor
        -> turns
          -> turn
            -> message
```

官方 `fix_10m_chats(data=chat)` 会从每个 plan holder 中取出非空的 `plan-*`，再交给
answer generation。10M loader 不能按普通 split 写死。

### 2.4 `probing_questions` 的真实结构

`probing_questions` 在本地数据里是 stringified Python dict，不是标准 JSON。后续 loader
应该用受控解析，例如 `ast.literal_eval`，解析失败要 fail closed。

解析后固定有 10 类 ability：

| ability key | 中文理解 |
| --- | --- |
| `abstention` | 信息缺失时是否拒答/说明无信息 |
| `contradiction_resolution` | 对矛盾信息是否识别并处理 |
| `event_ordering` | 是否恢复事件/话题在对话中出现的顺序 |
| `information_extraction` | 事实、实体、细节抽取 |
| `instruction_following` | 长期遵循用户指令 |
| `knowledge_update` | 新信息出现后是否更新旧事实 |
| `multi_session_reasoning` | 跨多个非相邻片段的推理 |
| `preference_following` | 个性化偏好遵循 |
| `summarization` | 对长期主题进行概括 |
| `temporal_reasoning` | 显式/隐式时间关系推理 |

本地抽样字段如下。只有 `question` 是 method public input；其余默认给 scorer/report。

| ability | public 字段 | scorer/report 私有字段 |
| --- | --- | --- |
| `abstention` | `question` | `ideal_response`, `rubric`, `difficulty`, `abstention_type`, `why_unanswerable`, `plan_reference` |
| `contradiction_resolution` | `question` | `ideal_answer`, `rubric`, `source_chat_ids`, `conversation_references`, `contradiction_type`, `tests_for`, `topic_questioned`, `difficulty` |
| `event_ordering` | `question` | `answer`, `rubric`, `source_chat_ids`, `conversation_references`, `ordering_type`, `ordering_tested`, `total_mentions`, `complexity_factors`, `difficulty` |
| `information_extraction` | `question` | `answer`, `rubric`, `source_chat_ids`, `conversation_reference`, `key_facts_tested`, `question_type`, `extraction_challenge`, `difficulty` |
| `instruction_following` | `question` | `rubric`, `source_chat_ids`, `instruction_being_tested`, `expected_compliance`, `compliance_indicators`, `non_compliance_signs`, `instruction_type`, `difficulty` |
| `knowledge_update` | `question` | `answer`, `rubric`, `source_chat_ids`, `conversation_references`, `tests_retention_of`, `update_type`, `potential_confusion`, `difficulty` |
| `multi_session_reasoning` | `question` | `answer`, `rubric`, `source_chat_ids`, `conversation_references`, `reasoning_steps`, `reasoning_type`, `sessions_required`, `difficulty` |
| `preference_following` | `question` | `rubric`, `source_chat_ids`, `preference_being_tested`, `expected_compliance`, `compliance_indicators`, `non_compliance_signs`, `preference_type`, `difficulty` |
| `summarization` | `question` | `ideal_summary`, `rubric`, `source_chat_ids`, `conversation_sessions`, `bullet_points_covered`, `key_elements_tested`, `summarization_type`, `synthesis_required`, `difficulty` |
| `temporal_reasoning` | `question` | `answer`, `rubric`, `source_chat_ids`, `conversation_references`, `time_points`, `temporal_type`, `calculation_required`, `complexity_factors`, `difficulty` |

10M split 的大多数 ability 额外带 `plan_reference`，用于 scorer/report 定位来源，不应给
method。

## 3. Evaluation 流程

### 3.1 论文定义的抽象流程

论文 Section 2.1 把 probing question 记作对话的下一轮输入。概念流程是：

```text
conversation T
-> probing question x
-> system 基于 T 生成 answer y_hat
-> ability-specific scoring function 计算 score
```

所以 BEAM 对 method 的本质要求仍是：先让 method 接收完整 conversation，再让 method
针对 probing question 提供可用于回答的记忆上下文/answer prompt。

### 3.2 官方 answer generation 的实际流程

官方 `answer_generation.py` 会读取每个 conversation 的 `probing_questions.json`，逐个
ability、逐个 question 调 `probing_question_evaluation(...)`，并把 `llm_response` 写回
结果 JSON。它支持两条主要 evaluation route。

#### Long-context route

配置：`evaluation_type="long-context"`。

代码路径：

- `answer_generation.py`
- `long_term_memory_methods.py::probing_question_evaluation`

流程：

```text
读取 chat.json
-> flatten 所有 user/assistant messages
-> 如果超出 max_tokens，则 prune_from_tail
-> 追加 probing question，要求只输出答案
-> 调用 long-context answer model
-> 保存 llm_response
```

这条路线评的是长上下文模型直接读完整/裁剪历史的能力。论文实验中：

- GPT-4.1-nano 和 Gemini-2.0-flash 作为 1M context proprietary models。
- Qwen2.5-32B-AWQ 在 long-context 实验中按 128K context 评估。
- 10M 场景下，模型无法完整读取 10M，论文描述为使用窗口内能容纳的最近对话片段。

#### RAG / LIGHT route

配置：`evaluation_type="rag"`。

代码路径：

- `answer_generation.py`
- `long_term_memory_methods.py`
- `light.py`

官方支持的 retrieval method：

| `retrieval_method` | 作用 |
| --- | --- |
| `pair_chunk` | 每个 user-assistant pair 当作文档 |
| `turn_chunk` | 每个 turn 当作文档 |
| `kv` | 用 LLM 抽取 key-value / episodic memory |
| `light` | BEAM 论文提出的 LIGHT：episodic memory + working memory + scratchpad |

官方支持的 retriever：

| `retriever` | 作用 |
| --- | --- |
| `bm25` | lexical retrieval |
| `splade` | sparse retrieval |
| `e5` | E5 dense retriever |
| `dense` | FAISS dense retriever；代码中默认用 BAAI/bge-small-en-v1.5 |
| `hybrid` | 组合检索 |

RAG / LIGHT 的共同回答流程：

```text
读取 chat.json
-> create_chunking(...) 构造 chunks / memory
-> create_retriever(...) 按 probing question 检索
-> handling_context(...) 拼出 reader context
-> answer_generation_for_rag 填入 context 和 question
-> reader LLM 生成 llm_response
```

普通 RAG baseline 的论文设置：每个 user-assistant turn pair 作为 document，向量库存
document embedding，推理时取 top-k 文档交给 LLM。论文主文描述 top five，附录 Table 9
额外做了 `K in {5,10,15,20}` 的 retrieval budget sweep。

LIGHT 的流程更复杂：

```text
conversation
-> Qwen2.5-32B-AWQ 对每个 user-assistant turn 抽 key-value 和 summary
-> BAAI/bge-small-en-v1.5 embedding，构成 episodic memory index
-> 保留最近 z 个 turn 作为 working memory
-> Qwen2.5-32B-AWQ 逐 turn 形成 scratchpad
-> scratchpad 超过阈值后由 GPT-4.1-nano 压缩
-> inference 时按 question 检索 episodic memory，并过滤 scratchpad
-> episodic memory + working memory + filtered scratchpad 一起进入 answer prompt
```

### 3.3 各类 probing question 的 evaluation 关注点

BEAM 的 answer generation 对 10 类 question 走同一个“生成答案”入口；差异主要体现在
question 设计和 scorer 的 rubric 上。

| ability | evaluation 关注点 | 对 method 的含义 |
| --- | --- | --- |
| `abstention` | 问题所需信息在对话中缺失时，回答应承认无信息 | method 不能强行幻觉；answer prompt 需要允许“不知道/无信息” |
| `contradiction_resolution` | 历史中存在冲突事实时，回答要识别冲突或请求澄清 | 不需要显式 contradiction API，但记忆检索不能只取单条旧事实 |
| `event_ordering` | 按对话出现顺序列出事件/话题 | 需要保留 message 顺序、turn 顺序和时间/索引 metadata |
| `information_extraction` | 抽取实体、事实、细节 | 基础长期记忆能力 |
| `instruction_following` | 长期遵守用户早先给出的格式/行为约束 | method 要能检索长期指令，不只是事实 |
| `knowledge_update` | 新事实覆盖旧事实 | method 需要处理历史中的更新，不一定需要 public update 接口 |
| `multi_session_reasoning` | 跨多个非相邻片段综合推理 | 检索必须覆盖多证据，而不是只取最近邻一条 |
| `preference_following` | 个性化偏好遵循 | 偏好属于 conversation 内长期记忆 |
| `summarization` | 概括长期主题发展 | 需要综合多个片段，回答可能较长 |
| `temporal_reasoning` | 显式/隐式时间关系推理 | `time_anchor`、message order、date expression 需要保留 |

### 3.4 Smoke / 裁剪注意点

BEAM 的 probing questions 往往引用超长历史中的特定片段。smoke 可以只做 loader 和
scorer 连通性，但如果要声称 answer evaluation 有意义，需要确保裁剪后的 conversation
仍覆盖该 question 的证据。否则很多 question 会被人为变成 unanswerable。

建议未来接入时分三种 smoke：

1. loader smoke：只验证 `chat` 和 `probing_questions` 能解析。
2. scorer smoke：使用人工构造 answer 或已有 artifact 跑 rubric judge。
3. method smoke：只选择证据在裁剪历史内的问题，避免把裁剪误差当成 method 错误。

### 3.5 对 method 可见的历史应是展平后的 message 序列

尽管官方中间 `chat.json` 有 `batch -> turns -> turn_group -> message` 的多层结构，
正式 method evaluation 仍可以理解为：

```text
完整 chat history
+ probing question
-> method answer
```

`main_question` 分组不是 method public protocol 的必需部分。我们应在 loader 内吃掉这层
复杂度：按原始顺序展平 message，保留 `id/index/question_type/batch_index/turn_group_index`
到 metadata，给 method 的核心输入仍然是普通的 user/assistant message 序列。这样可以同时
保留调试和 scorer 对齐信息，又不把 BEAM 的数据生成细节扩散到 method adapter。

## 4. Metric 计算方式

### 4.1 主体指标：rubric-nugget LLM judge

论文说明：每个 probing question 会有一组 rubric nuggets。一个 nugget 是原子、独立的
评分点。系统回答会逐 nugget 交给 LLM judge，judge 输出：

```text
1.0 = 完全满足
0.5 = 部分满足
0.0 = 不满足
```

question score 是该 question 的所有 nuggets 平均分。ability score 是该 ability 下
questions 的平均分。最终报告通常需要按 10 类 ability 展开，再给整体平均。

官方代码路径：

- `compute_metrics.py::evaluate_abstention`
- `evaluate_contradiction_resolution`
- `evaluate_information_extraction`
- `evaluate_instruction_following`
- `evaluate_knowledge_update`
- `evaluate_multi_session_reasoning`
- `evaluate_preference_following`
- `evaluate_summarization`
- `evaluate_temporal_reasoning`

这些函数结构高度一致：对 `rubric` 中每个 item 调 judge prompt，解析 JSON，再平均。

### 4.2 Event ordering 特殊指标

`event_ordering` 不只看答案是否包含事实，还看顺序是否正确。

官方代码路径：

- `compute_metrics.py::evaluate_event_ordering`
- `compute_metrics.py::event_ordering_score`
- `report_results.py`

实现逻辑：

```text
llm_response -> 按行拆成 system event list
rubric -> reference event list
LLM equivalence detector 对齐 reference / system events
计算 precision / recall / F1
计算 Kendall tau-b，并归一化为 tau_norm
```

`report_results.py` 聚合时对 `event_ordering` 使用 `tau_norm`；对其他 ability 使用
`llm_judge_score`。

### 4.3 Artifact-only 复算可行性

BEAM 适合 artifact-only evaluation，只要保存：

- 每个 `conversation_id`
- 每个 probing `ability`
- `question`
- method 生成的 `llm_response`
- scorer private label：`rubric` 和其他 report metadata

就可以在不重新跑 method 的情况下重跑 judge。但如果 judge prompt 或 judge LLM 改变，
metric 结果也会改变，因此 manifest 必须记录 judge model、judge prompt profile、代码版本。

### 4.4 当前官方代码风险

这里必须记录，因为它会影响我们未来是否直接复用官方 scorer：

1. 论文和 prompt 都允许 `0.5` partial credit，但本地 `compute_metrics.py` 多个非
   event-ordering 函数使用 `int(response["score"])`，如果 judge 真返回 `0.5`，会报错或
   丢失 partial credit。后续实现 scorer 前必须决定：严格复刻本地代码，还是按论文语义
   修正为 `float`。
2. `unified_llm_judge_base_prompt` 包含 `<question>`，但本地多个 evaluate 函数只替换
   `<rubric_item>` 和 `<llm_response>`，没有替换 `<question>`。这可能是官方实现 bug，也可能
   是当前仓库未清理的版本差异。后续不能盲目照抄。

## 5. Answer LLM / Judge LLM 配置和 Prompt

### 5.1 官方 answer generation 入口参数

官方脚本：

- `src/answer_probing_questions/answer_generation.sh`
- `src/answer_probing_questions/answer_generation.py`

主要需要三类 LLM：

| LLM | 用途 | 代码配置 |
| --- | --- | --- |
| `reader_llm` | 最终回答 probing question | `--reader_model_url`, `--reader_model_name`, `--reader_model_api_key`, temperature 0 |
| `qwen_llm` | LIGHT/KV 内部抽取、scratchpad、过滤 | `--qwen_model_url`, `--qwen_model_name`, `--qwen_api_key`, temperature 0，带 English-only guided regex |
| `gpt_llm` | LIGHT scratchpad 压缩等辅助步骤 | 代码中固定 `model_name="gpt-4.1-mini"`，temperature 0 |

`long-context` 额外从 CLI 读取：

| 参数 | 作用 |
| --- | --- |
| `--model_name` | long-context answer model |
| `--model_provider` | 例如 OpenAI / Google / Bedrock converse 等 LangChain provider |
| `--api_key` | long-context model API key |
| `--temperature` | 默认 0 |
| `--request_timeout` | 默认 60 |
| `--max_tokens` | 上下文 token 上限 |
| `--sleep_time` | 每题后 sleep，避免 API 压力 |

`rag` 额外从 CLI 读取：

| 参数 | 作用 |
| --- | --- |
| `--retrieval_method` | `kv`, `light`, `pair_chunk`, `turn_chunk` |
| `--retriever` | `bm25`, `splade`, `e5`, `dense`, `hybrid` |
| `--k` | 检索 top-k |

代码默认对象里有 `retrieval_method="light"`, `retriever="dense"`, `k=5`，但实际 CLI
运行时会根据脚本传入参数覆盖。论文主实验文字描述 RAG baseline 取 top five；附录又提供
K sweep（5/10/15/20），所以文档和配置必须记录具体 profile，不能只说“BEAM 的 k 是某个固定值”。

### 5.2 Answer prompt

Long-context route 的 answer prompt 很简单：把完整/裁剪后的 chat messages 作为
chat history，然后追加一个 user message，要求只回答问题、不解释。这个 prompt 由
`long_term_memory_methods.py::probing_question_evaluation` 内联构造。

RAG / LIGHT route 使用 `src/prompts.py::answer_generation_for_rag`。它包含两个变量：

| 变量 | 填入内容 |
| --- | --- |
| `<context>` | 检索或 LIGHT 过滤后的上下文 |
| `<question>` | probing question |

prompt 语义是：只能根据 context 回答，不使用内部知识，输出直接简洁的答案。

LIGHT 论文 Appendix Listing 44 与代码里的 `answer_generation_for_rag` 对齐；LIGHT 只是
把 `<context>` 构造成 episodic memory + working memory + filtered scratchpad 的组合。

### 5.3 LIGHT 内部 prompt / 模型

论文和代码中，LIGHT 内部还用到：

| 组件 | LLM / 模型 | prompt 位置 | 作用 |
| --- | --- | --- | --- |
| episodic memory indexing | Qwen2.5-32B-AWQ | Listing 40 / `kv_creation_prompt` | 从每个 user-assistant turn 抽 key-value 和 summary |
| scratchpad creation | Qwen2.5-32B-AWQ | Listing 41 / `scratchpad_generation_prompt` | 从当前和前序 turn 抽取 salient facts |
| scratchpad compression | GPT-4.1-nano / mini in code | Listing 42 / scratchpad summarizer prompt | 超过阈值后压缩 scratchpad |
| scratchpad filtering | Qwen2.5-32B-AWQ | Listing 43 / filter prompt | 判断 chunk 是否与 question 相关 |
| embedding | BAAI/bge-small-en-v1.5 | 论文主实验；代码部分路径也支持 bge-large | key / query embedding |

论文主文写 scratchpad 超过 30K token 后压缩到 15K token。代码里也有 `reader_max_tokens`
限制：普通 RAG context 大约 29K，LIGHT noise filtering 内部约 14K。

### 5.4 Judge prompt / judge LLM

官方 judge 入口：

- `src/evaluation/run_evaluation.py`
- `src/evaluation/compute_metrics.py`
- `src/prompts.py::unified_llm_judge_base_prompt`

`run_evaluation.py` 默认从 `src.llm import gpt_llm`，而 `src/llm.py` 中 `gpt_llm` 使用
`gpt-4.1-mini`、temperature 0。也就是说，官方仓库当前 evaluation 脚本默认 judge LLM
是 GPT-4.1-mini。

Judge prompt 变量：

| 变量 | 内容 |
| --- | --- |
| `<question>` | probing question |
| `<rubric_item>` | 一个 rubric nugget |
| `<llm_response>` | method answer |

prompt 要求 judge 输出 JSON，字段为 `score` 和 `reason`。论文允许 score 为
`1.0 / 0.5 / 0.0`。Event ordering 还额外使用 Listing 21 的二分类 equivalence prompt，
判断两个 event snippet 是否表示同一事件/话题。

## 6. Method Adapter 接口需求

### 6.1 最小接口

BEAM 第一版可以继续使用当前 retrieve-first 协议：

```python
add(conversation)
retrieve(question) -> AnswerPromptResult
```

其中：

- `add(conversation)` 写入完整 BEAM conversation。
- `retrieve(question)` 返回 method 已经组织好的 answer prompt messages，供 framework
  answer LLM 生成 `llm_response`。
- framework evaluator 再读取 private `rubric`，用 BEAM judge prompt 评分。

### 6.2 `Conversation` 映射建议

普通 split 的一个 BEAM sample 映射成一个 `Conversation`：

| 我们的字段 | BEAM 来源 |
| --- | --- |
| `conversation_id` | `conversation_id` |
| `messages` | 从 `chat` 展开后的所有 messages |
| `Message.sender_name` / `role` | `role` |
| `Message.content` | `content` |
| `Message.timestamp` | 优先用 `time_anchor`；没有则为空 |
| `Message.metadata` | `id`, `index`, `question_type`, `batch_index`, `turn_index`, `plan_id` 等 |

BEAM 的“session”边界不是 LoCoMo 那种天然 session，而是 batch / plan / turn 结构。对当前
框架来说，最稳妥是保留这些字段到 metadata，不急着强行改成 LoCoMo session。

### 6.3 `Question` 映射建议

每个 probing question 映射成一个 `Question`：

| 我们的字段 | BEAM 来源 |
| --- | --- |
| `question_id` | 建议组合 `conversation_id + ability + index` |
| `conversation_id` | 所属 sample id |
| `question` | probing question 的 `question` |
| `category` | ability key，例如 `temporal_reasoning` |
| `metadata` | `difficulty`、公开的 ability 标签；不要放 rubric/source ids |

`rubric`、`ideal_response`、`ideal_answer`、`answer`、`ideal_summary`、`source_chat_ids` 等
只进入 evaluator private labels。

### 6.4 是否需要新增 method 接口

| 接口/能力 | BEAM 是否需要 | 判断 |
| --- | --- | --- |
| `add(conversation)` | 需要 | 每个 sample 是一条完整超长 conversation |
| `retrieve(question)` | 需要 | 当前框架可用 retrieve-first 统一回答 |
| conversation isolation | 需要 | 每个 conversation 独立评测 |
| explicit update API | 不需要 | `knowledge_update` 是评测能力，不要求 public `update()` |
| delete / forget | 不需要 | 无显式删除或遗忘操作 |
| reset | 不需要 | 按 conversation 隔离即可 |
| retrieval recall | 不需要 | BEAM 主评 answer quality |
| multimodal | 不需要 | 当前 BEAM 是纯文本 |
| streaming ingest | 未来可能需要 | 1M/10M 太长；可先作为框架内部实现优化，不急着暴露给用户 |

### 6.5 对当前框架的影响

BEAM 不会立即推翻 `BaseMemoryProvider.add + retrieve`，但会推动我们新增：

- BEAM loader：支持 HF 原始 `chat` 和官方中间 `chat.json` 两种结构。
- rubric judge metric family：与 LoCoMo F1 / LongMemEval yes-no judge 不同。
- ability-level aggregation：固定 10 类能力聚合。
- event-ordering metric：Kendall tau-b + LLM equivalence alignment。
- 超长 conversation 的 smoke 策略：不能随便按前 N turns 截断后还声称能评全部问题。
- 未来 streaming ingest / chunked ingest：先内部支持，是否公开成用户接口等更多 benchmark
  调研后再决定。

### 6.6 2026-07-06 增补：原生粒度与喂入方式

BEAM 的自然单位是 `conversation -> chat size split -> probing question`：普通 split
每条 conversation 有 10 类能力、每类 2 个 probing questions；10M split 额外有 plan
层。本地 HF 数据中，`100K/500K/1M` 的 `chat` 是 batch list，再展开为 message
list；`10M` 的 `chat` 是 plan holder list。官方 inference 脚本则读取生成后的
`chat.json`，普通 split 按 `batch -> turns -> message` 展开，10M 按
`plan -> batch -> turns -> message` 展开。证据：本轮验收命令读取
`data/BEAM/beam_dataset` 与 `data/BEAM/beam_10M_dataset`；官方展开逻辑见
`third_party/benchmarks/BEAM/src/answer_probing_questions/long_term_memory_methods.py:552-574`。

官方喂入顺序是先对一个 conversation 建立可复用上下文或检索结构，再顺序回答该
conversation 下所有 probing questions。`answer_generation.py` 会缓存
`saved_messages`、`saved_retriever`、`saved_chunks`、`saved_short_term_chunks` 和
`saved_scratch_pad`，避免同一 conversation 的每题重复 ingest。证据：
`third_party/benchmarks/BEAM/src/answer_probing_questions/answer_generation.py:45-98`。

对当前 retrieve-first 协议，BEAM 仍可映射为 `add(conversation)` 一次写入完整
conversation，`retrieve(question)` 返回 answer prompt；但 loader 必须保留
`chat_size`、batch、turn、plan、role、message index 等边界信号，否则 event ordering、
multi-session reasoning、knowledge update 与 temporal reasoning 的错误无法回溯。若未来
引入 `add_turn(...)`，BEAM 应按原始生成顺序流式喂入：普通 split 为
batch/turn/message，10M 为 plan/batch/turn/message；method 只能看到 chat 和 question，
不得看到 `rubric`、reference event list、ideal answer 等 judge 私有字段。

### 6.7 2026-07-06 增补：成本画像

完整 BEAM 规模是 100 conversations、2,000 validated questions：`128K/100K` 20
chats，`500K` 35 chats，`1M` 35 chats，`10M` 10 chats；每条 conversation 固定 20
个 probing questions。README 还给出平均 turns：128K 107、500K 416、1M 842、10M
7,757。证据：`third_party/benchmarks/BEAM/README.md:20-39`；本轮验收命令确认
本地 split 行数为 `20/35/35/10`，且每条样本 `probing_questions` 总数为 20。

long-context 路径每个 probing question 至少一次 answer LLM 调用；第一次会把整条
chat 展开、按 `max_tokens` 从尾部裁剪，后续题复用 `saved_messages` 后追加问题。证据：
`third_party/benchmarks/BEAM/src/answer_probing_questions/long_term_memory_methods.py:534-596`。
RAG/LIGHT 路径在每条 conversation 首题构建 chunk、retriever 和可选 scratchpad，随后
每题执行 retrieval、拼接 context、调用 reader LLM。LIGHT 额外为 scratchpad、episodic
memory 和 filtering 调用内部 LLM，并维护最近 100 个 pair 的 working memory。证据：
`third_party/benchmarks/BEAM/src/answer_probing_questions/long_term_memory_methods.py:598-645`、
`third_party/benchmarks/BEAM/src/answer_probing_questions/light.py:402-461`、
`third_party/benchmarks/BEAM/src/answer_probing_questions/light.py:464-542`。

评测成本也不是纯本地指标：`run_evaluation.py` 对每个 answer 读取 private `rubric`，
按 10 类能力分派到 evaluator；大多数类别对每个 rubric item 调用 judge LLM 并平均，
event ordering 还会做 LLM equivalence 对齐和 Kendall tau-b/F1 组合分。官方本地
`gpt_llm` 默认是 `gpt-4.1-mini`、temperature 0。证据：
`third_party/benchmarks/BEAM/src/evaluation/run_evaluation.py:39-78`、
`third_party/benchmarks/BEAM/src/evaluation/compute_metrics.py:270-308`、
`third_party/benchmarks/BEAM/src/evaluation/compute_metrics.py:339-360`、
`third_party/benchmarks/BEAM/src/llm.py:61-68`。

## 7. 未确认项

1. `100K` vs `128K`：论文/README 写 128K，本地 split 和官方目录是 `100K`。当前以本地
   split 名为准。
2. `probing_questions` 是 stringified Python dict，loader 需要安全解析；如果未来 HF 格式
   更新成 JSON，需要兼容。
3. 官方 scorer 代码和论文语义不完全一致：论文允许 `0.5`，但本地多个函数用 `int(score)`；
   后续 scorer 实现前必须决策是复刻代码还是按论文修正。
4. 官方 judge prompt 的 `<question>` 在本地多个 evaluate 函数里未被替换；这可能是官方
   仓库 bug，需要后续单独复核。
5. `conversation_seed`、`user_profile`、`conversation_plan` 是否可作为 method 输入，需要按
   official profile 决定；当前默认不给 method。
6. LIGHT 论文主实验、README 默认脚本和附录 K sweep 的 top-k 口径不同。后续如果复现
   LIGHT/BEAM 表格，必须为每个 profile 写清 `retrieval_method`、`retriever`、`k`、
   embedding 和 reader LLM。
7. 10M split 结构复杂，且部分 plan holder 中只有一个非空 `plan-*`。未来 loader 必须先
   做结构单测，再谈真实运行。
8. BEAM 的 official evaluation 是按本地 `chats/` 目录中生成的 `chat.json`、
   `probing_questions.json` 跑的；我们的 runtime 数据入口是 `data/BEAM`。接入时需要明确
   是否先生成官方中间目录，还是直接写 native HF loader。

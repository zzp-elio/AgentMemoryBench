# PersonaMem Benchmark 调研卡片

更新日期：2026-07-03

## 1. 一句话结论

PersonaMem 是一个面向个性化长期记忆的 **persona-oriented multi-session long-context multiple-choice QA** benchmark。它评测模型是否能从用户长期交互历史中记住静态事实、追踪偏好变化、理解变化原因，并在新场景中选择最符合当前用户状态的回答。

它和 LoCoMo / LongMemEval 的相似点是：都有同一用户/角色范围内的长期历史和后续问题；核心指标也是 answer-level accuracy。关键不同点是：PersonaMem 官方评测并不是先调用 memory method 写入再检索，而是把截断后的完整 OpenAI-style message context 直接喂给 long-context LLM，再追加当前 multiple-choice query。它更像 long-context personalization QA baseline；如果接入我们的 memory 框架，需要额外把 `shared_contexts` 中的 message list 转成可增量写入的 user/persona 级 history，并用 multiple-choice reader 评分。

当前 `BaseMemoryProvider.add(conversation) + retrieve(question)` 可以覆盖一个“memory module 版本”的 PersonaMem，但实现层不能只支持“整段 conversation 一次性写入”。PersonaMem 的关键是同一 `shared_context_id` 下按 `end_index_in_shared_context` 形成多个 checkpoint，因此 loader/runner 至少要能把 `shared_contexts` 中的 **OpenAI-style message** 作为最小历史单元增量写入；也就是在同一 memory namespace 内反复追加 `context[cursor:end_index]` 这类 message delta。除此之外还必须保留 `system` persona message，支持 A/B/C/D 选项和 accuracy scorer；官方发布版没有 gold evidence turn id，因此不能自然计算 retrieval recall。

## 2. Dataset 数据结构

### 2.1 本地材料与路径

| 类型 | 路径 / 来源 | 调研结论 |
| --- | --- | --- |
| 官方仓库 | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/PersonaMem` | 包含论文、README、数据构造脚本、推理脚本和模型运行脚本。 |
| 论文 PDF | `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/PersonaMem/Personmem.pdf` | 论文题为 “Know Me, Respond to Me: Benchmarking LLMs for Dynamic User Profiling and Personalized Responses at Scale”。 |
| 本地数据 | `/Users/wz/Desktop/memoryBenchmark/data/PersonaMem` | 已从用户指定 HuggingFace `bowen-upenn/PersonaMem-v1` 下载。 |
| 官方推理脚本 | `inference_standalone_openai.py`、`inference.py` | 真实 evaluation 主链路：读取 question CSV，按 context id 加载 shared context，切片后追加 question/options，直接调 LLM。 |
| 官方构造脚本 | `prepare_blocks.py` | 说明 `end_index_in_shared_context`、`distance_to_ref_*`、`shared_context` 如何生成。 |

### 2.2 发布版文件和规模

PersonaMem 发布版按 context token length 分三档：

| 版本 | question CSV | shared context JSONL | questions | personas | JSONL context 行数 | 实际被 questions 使用的 context 数 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 32k | `questions_32k.csv` | `shared_contexts_32k.jsonl` | 589 | 20 | 37 | 37 |
| 128k | `questions_128k.csv` | `shared_contexts_128k.jsonl` | 2727 | 20 | 110 | 60 |
| 1M | `questions_1M.csv` | `shared_contexts_1M.jsonl` | 2674 | 20 | 33 | 31 |

注意：128k 和 1M 的 `shared_contexts_*.jsonl` 中存在未被当前 `questions_*.csv` 引用的 context。评测时应以 CSV 的 `shared_context_id` 为准，不要把 JSONL 行数直接当成样本数。

### 2.3 `questions_[SIZE].csv` 字段

每行是一道 multiple-choice personalization question。

| 字段 | 是否给 method / answer reader | 含义 |
| --- | --- | --- |
| `persona_id` | 是 | 用户 persona id。20 个 persona，字符串数字 `0` 到 `19`。 |
| `question_id` | 是 | question 唯一 id。 |
| `question_type` | 是 | 七类 in-situ query 类型之一；本地数据存在新旧命名混用，loader 需要做 normalization。 |
| `topic` | 是 | 当前问题所属任务主题，如 datingConsultation、foodRecommendation、therapy。 |
| `context_length_in_tokens` | 可见 metadata | 到提问位置为止的 context token 数，按 GPT-4o tokenizer 构造。 |
| `context_length_in_letters` | 可见 metadata | 到提问位置为止的 context 字符长度。 |
| `distance_to_ref_in_blocks` | scorer/analysis metadata | question 到最近 reference 信息的 session/block 距离；不是可直接传给 method 的 evidence id。 |
| `distance_to_ref_in_tokens` | scorer/analysis metadata | question 到最近 reference 信息的 token 距离。 |
| `num_irrelevant_tokens` | analysis metadata | 构造 long context 时插入的 irrelevant interaction token 数。 |
| `distance_to_ref_proportion_in_context` | analysis metadata | reference 在当前 context 中的相对位置。 |
| `user_question_or_message` | 是 | 当前用户问题/消息，官方直接追加为最后一条 user message 的开头。 |
| `correct_answer` | 否 | 正确选项字母，形如 `(a)`、`(b)`，只给 scorer。 |
| `all_options` | 是 | 四个候选回答，字符串形式的 Python/JSON list，三档数据都可解析为 4 个选项。 |
| `shared_context_id` | 是 | 到 `shared_contexts_[SIZE].jsonl` 中索引历史 message list 的 key。 |
| `end_index_in_shared_context` | 是 | 截断位置。官方使用 `context[:int(end_index_in_shared_context)]` 作为可见历史。 |

### 2.4 `shared_contexts_[SIZE].jsonl` 结构

每行是单 key JSON object：

```json
{
  "<shared_context_id>": [
    {"role": "system", "content": "Current user persona: ..."},
    {"role": "user", "content": "User: ..."},
    {"role": "assistant", "content": "Assistant: ..."}
  ]
}
```

真实样本中，每个 context 是 OpenAI-style message list：

| 版本 | 被使用 context message 数范围 | 被使用 context 中 system message 数范围 | 解释 |
| --- | ---: | ---: | --- |
| 32k | 116-238 | 4-7 | 约 10 session / 32k token，但发布版实际被截断/过滤后 system block 数不是固定 10。 |
| 128k | 590-846 | 16-20 | 约 20 session / 128k token。 |
| 1M | 3304-3803 | 57-60 | 约 60 session / 1M token。 |

`system` message 并不是普通任务指令，而是 `Current user persona: ...`。官方论文也说明 evaluation 时模型可见用户基本人口统计信息；代码实际会在每个 block/session 前插入 persona system message。因此，如果我们把 PersonaMem 改造成 memory framework benchmark，不能无声删除这些 `system` persona messages；应把它们作为 public input 的一部分处理，或者明确选择一个非官方 profile。

### 2.5 七类 question type

论文和 HuggingFace README 定义七类 in-situ user query：

| 语义类别 | 本地常见字段名 |
| --- | --- |
| Recall user-shared facts | `recall_user_shared_facts`；32k 中还存在 `recalling_facts_mentioned_by_the_user` |
| Suggest new ideas | `suggest_new_ideas` |
| Acknowledge latest user preferences | `acknowledge_latest_user_preferences`；构造代码中也出现 `acknowledge_latest_preferences` |
| Track full preference evolution | `track_full_preference_evolution`；1M 中存在 `track_full_preference_updates` |
| Revisit reasons behind preference updates | `revisit_reasons_behind_preference_updates`；32k 中存在 `recalling_the_reasons_behind_previous_updates` |
| Provide preference-aligned recommendations | `provide_preference_aligned_recommendations` |
| Generalize to new scenarios | `generalize_to_new_scenarios`；32k 中存在 `generalizing_to_new_scenarios` |

本地三档 question type 分布：

| 版本 | 分布 |
| --- | --- |
| 32k | `recall_user_shared_facts`: 129；`track_full_preference_evolution`: 139；`recalling_the_reasons_behind_previous_updates`: 99；`suggest_new_ideas`: 93；`generalizing_to_new_scenarios`: 57；`provide_preference_aligned_recommendations`: 55；`recalling_facts_mentioned_by_the_user`: 17 |
| 128k | `acknowledge_latest_user_preferences`: 866；`suggest_new_ideas`: 518；`provide_preference_aligned_recommendations`: 349；`track_full_preference_evolution`: 341；`revisit_reasons_behind_preference_updates`: 269；`generalize_to_new_scenarios`: 213；`recall_user_shared_facts`: 171 |
| 1M | `acknowledge_latest_user_preferences`: 768；`suggest_new_ideas`: 727；`generalizing_to_new_scenarios`: 295；`provide_preference_aligned_recommendations`: 280；`revisit_reasons_behind_preference_updates`: 235；`track_full_preference_updates`: 225；`recall_user_shared_facts`: 144 |

### 2.6 Public input 与 private label

Public input：

```text
context = shared_contexts[shared_context_id][:end_index_in_shared_context]
current user query = user_question_or_message
answer choices = all_options
```

Private label：

```text
correct_answer
```

Analysis-only metadata：

```text
distance_to_ref_in_blocks
distance_to_ref_in_tokens
num_irrelevant_tokens
distance_to_ref_proportion_in_context
```

发布版 CSV 不包含具体 `reference_turn_id` 或 `reference_message_id`。构造脚本在生成 CSV 前确实用 reference utterance 计算了距离，但最终只保留距离统计和可选 generation 阶段的 `groundtruth_info`；HF `PersonaMem-v1` 发布版没有 `groundtruth_info` 列。因此，官方主评测只能做 answer accuracy 和分组分析，不能直接做 evidence recall。

## 3. Evaluation 流程

### 3.1 官方 long-context evaluation 主流程

官方 `inference_standalone_openai.py` / `inference.py` 的 evaluation 流程：

```python
jsonl_index = build_jsonl_index(context_path)

for row in questions_csv:
    context = load_context_by_id(shared_context_id)
    context = context[:int(end_index_in_shared_context)]

    messages = context + [{
        "role": "user",
        "content": user_question_or_message + "\n\n" + instructions + "\n\n" + all_options
    }]

    model_response = LLM(messages)
    score = extract_answer(model_response, correct_answer)
```

也就是说，官方默认没有：

```text
memory.add()
memory.retrieve()
LLM judge
gold evidence recall
```

它是 direct long-context LLM evaluation。

### 3.2 问题何时被问

每道题不是等完整 shared context 结束后统一提问，而是使用该行自己的：

```text
shared_context_id + end_index_in_shared_context
```

这表示：在同一条长历史的某个位置截断，然后从这个时间点发起新的 in-situ user query。官方会把截断前所有 messages 作为历史，把 `user_question_or_message` 作为新 user message。

### 3.3 Context 的 session/block 语义

构造脚本 `prepare_blocks.py` 把多个 conversation blocks 按时间排序后拼接成 shared context。每个 block 前会插入 `Current user persona` system message；block 内是多轮 user/assistant messages。论文说 32k/128k/1M 大致对应 10/20/60 sessions，每个 session 15-30 conversation turns。真实发布版里，system message 数基本可视为 session/block 数的近似信号。

如果把 PersonaMem 映射到我们当前的 conversation-session-turn 结构，建议：

```text
conversation_id = shared_context_id 或 persona_id + shared_context_id
session = 每个 system persona message 开始到下一个 system message 之前的 message block
turn = user/assistant message
question_id = question_id
question_time = 无显式字段，可从 message content 中的日期或 block 顺序间接获得，但官方不要求 question_time 字段
```

### 3.4 如果接入 memory method 的可行流程

官方论文 §4.4 额外做了 RAG / Mem0 外部 memory module 实验，说明 memory-module 版本是可行的，但发布仓库没有提供完整 RAG/Mem0 adapter 代码。论文描述的外部 memory 流程是：

```text
RAG:
    对历史 messages 做 BGE-M3 dense embedding
    每个问题检索 top-5 most relevant messages
    将检索内容给 GPT-4o / GPT-4o-mini answer reader

Mem0:
    按 turn 迭代构建 memory database
    每个问题检索 top-5 relevant facts
    将检索 facts 给 answer reader
```

因此，我们框架若接入 PersonaMem，可设计两种 profile：

1. `long_context_official`：直接复刻官方，把 sliced message context + question/options 喂给 answer LLM，不评估 memory method。
2. `memory_module`：把 sliced context 转成 session/turn stream 写入 method，然后 `retrieve(question)`，再用 multiple-choice answer reader 输出 `(a)-(d)`。

第二种更符合我们项目目标，但它不是官方默认脚本路径，需要在文档中标注为框架适配口径。

### 3.5 推荐的 memory-module 增量评测流程

如果要把 PersonaMem 作为 memory method benchmark 跑，最合理的流程不是“每道题都从零灌入完整 prefix”，而是按 shared context 分组并增量推进 checkpoint：

```python
for benchmark_size in ["32k", "128k", "1M"]:
    for shared_context_id, rows in groupby_questions(benchmark_size, key="shared_context_id"):
        context = load_shared_context(benchmark_size, shared_context_id)
        rows = sorted(rows, key=lambda r: int(r["end_index_in_shared_context"]))

        method.reset_or_new_namespace(conversation_id=f"{benchmark_size}:{shared_context_id}")
        cursor = 0

        for end_index, questions_at_checkpoint in groupby(rows, key=end_index):
            # context[cursor:end_index] 是 OpenAI-style message delta：
            # [{"role": "system"|"user"|"assistant", "content": "..."}]
            method.add(context[cursor:end_index])
            cursor = end_index

            for q in questions_at_checkpoint:
                retrieved = method.retrieve(q["user_question_or_message"])
                pred = multiple_choice_answer_reader(
                    retrieved_context=retrieved,
                    question=q["user_question_or_message"],
                    options=q["all_options"],
                )
                score(pred, q["correct_answer"])
```

关键约束：

1. 隔离单元应至少是 `(benchmark_size, shared_context_id)`。本地验证显示：每个被使用的 `shared_context_id` 都只对应一个 `persona_id`，且 32k/128k/1M 之间没有重叠的 `shared_context_id`；但不同 size 是不同数据版本，仍应显式隔离。
2. 不能只按 `persona_id` 隔离。一个 persona 可以出现在多个 shared context / context variant 中，把同一 persona 的不同 shared context 混进一个 memory state 会偏离官方 `context[:end_index]` 语义。
3. 同一个 `shared_context_id` 内多道题共享同一历史，但每道题只允许看到该行 `end_index_in_shared_context` 之前的 messages。
4. 多道题可能有相同 `end_index_in_shared_context`。它们应在完全相同的 memory state 上回答；问题和模型回答本身不应写回 memory，否则会污染后续同 checkpoint 或后续 checkpoint 的问题。
5. 增量写入时只写 `context[cursor:end_index]`，不要重复写已经灌入的 prefix，否则 Mem0 / LightMem / A-Mem 这类会真实更新记忆库的方法会出现重复记忆。

这个流程比每题独立重建 memory 更省成本，也更贴近官方 long-context evaluation 的“同一 context prefix 上发起多个 probe”的语义。

### 3.6 可选 stress profile：按 `persona_id` 隔离

也可以设计一个非官方的 `persona_id` 级 stress profile：把同一 persona 下的多个
`shared_context_id` 合并到同一个 memory namespace，让 method 在更嘈杂、更长、更重复的
用户历史中回答问题。但这个 profile 的有效性需要谨慎对待：它不仅会让噪声变多，还可能让
原始 `correct_answer` 标签不再严格成立。因此它最多只能作为探索性 stress test，不能称为
官方 PersonaMem 复现，也不应和官方 accuracy 直接横向比较。

原因是本地数据表明，同一个 persona 会对应多个 shared context，而这些 shared context
更像不同 context variant / 不同长度版本下的历史拼接结果，不是一个明确的单一时间线。
如果按 `persona_id` 混合，会出现三类风险：

1. **跨 variant 污染**：同一 persona 的不同 shared context 可能包含重复、重排或不同噪声的
   历史片段；混合后不再等价于任一官方 `context[:end_index]`。
2. **时间泄漏**：某个 question 只应看到该行 `end_index` 前的 messages；按 persona 合并后，
   method 可能提前看到另一个 context 中更靠后的偏好更新。
3. **标签语义被破坏**：`correct_answer` 是基于单个 `shared_context_id` 的 prefix 设计的。
   如果把其他 shared context 的 B/C 内容混入 A 的 memory state，同一 persona 可能出现
   旧偏好、不同 variant 下的偏好更新或冲突表述，导致 A 的原始正确选项在混合上下文下不再
   唯一正确。
4. **难度方向不稳定**：混合后不一定只会更难。额外历史可能提供重复证据让题目更容易，也
   可能提供旧偏好、冲突偏好或无关信息让题目更难。

因此，官方复现 / 主 benchmark profile 应使用 `(benchmark_size, shared_context_id)` 隔离；
`persona_id` 隔离只能作为额外 robustness/noise stress profile，并且报告中必须单独标注
“不保证原始 multiple-choice label 在混合上下文下仍然严格正确”。

## 4. Metric 计算方式

### 4.1 主指标：Multiple-choice Accuracy

官方主评测是 discriminative multiple-choice selection。模型看到四个选项 `(a)-(d)`，输出包含最终选项。脚本用正则解析：

```text
1. 如果 response 包含 <final_answer>，先取该 token 后面的文本。
2. 查找 `(a)` / `(b)` / `(c)` / `(d)` 或独立字母 a-d。
3. 只有解析结果唯一且等于 correct_answer，score=True。
4. 否则 score=False。
```

总体准确率：

```text
accuracy = correct_count / total_questions
```

官方 result CSV 每行写出：

```text
score
persona_id
question_id
user_question_or_message
question_type
topic
context_length_in_tokens
context_length_in_letters
distance_to_ref_in_blocks
distance_to_ref_in_tokens
num_irrelevant_tokens
distance_to_ref_proportion_in_context
model_response
len_of_model_response
predicted_answer
correct_answer
```

因此 accuracy 可以 artifact-only 复算。

### 4.2 分组分析

论文和官方结果主要按以下维度分析：

| 维度 | 来源字段 | 作用 |
| --- | --- | --- |
| context length | 32k / 128k / 1M 文件版本 | 比较不同上下文长度下模型效果。 |
| question type | `question_type` | 七类 personalization 能力分组。 |
| topic | `topic` | 按任务主题统计。 |
| distance in blocks/sessions | `distance_to_ref_in_blocks` | 分析 lost-in-the-middle / 距离影响。 |
| distance in tokens | `distance_to_ref_in_tokens` | 分析 reference 距离影响。 |
| persona | `persona_id` | 可做用户级分组，但官方主要图表不以 persona 为主。 |

### 4.3 没有 LLM Judge

论文明确说明主评测不使用 LLM judge。原因是 open-ended personalized response 会有多种正确答案且 judge 成本高，所以主评测转成 multiple-choice。附录也提到 generative setting 使用候选项 token log-likelihood，而不是 LLM-as-a-judge。

### 4.4 没有原生 retrieval recall

PersonaMem 发布版没有 gold evidence turn id。虽然 `distance_to_ref_*` 来自构造阶段的 reference utterance 定位，但它只能支持距离/位置分析，不能直接计算 retrieval recall。因此，如果我们对 memory method 做 retrieve，最多可以记录 retrieved messages/facts 做诊断；不能声称复现官方 retrieval metric。

## 5. Answer LLM / Judge LLM 配置和 Prompt

### 5.1 官方 Answer Prompt

官方 answer prompt 不是单独放在 `prompts.py` 里，而是在 `Evaluation.query_llm()` 中动态构造：

```text
{context messages}

role=user:
{user_question_or_message}

Find the most appropriate model response and give your final answer (a), (b), (c), or (d) after the special token <final_answer>.

{all_options}
```

其中 `context messages` 是 `shared_contexts[shared_context_id][:end_index]`。`all_options` 是四个候选回答的 list 字符串。

官方代码要求模型最终在 `<final_answer>` 后输出 `(a)`、`(b)`、`(c)` 或 `(d)`，但 parser 也会在完整 response 中兜底搜索唯一选项。

### 5.2 官方模型和参数

官方 scripts 覆盖多个 long-context LLM：

| Provider / 模型族 | 脚本例子 | 默认 benchmark size |
| --- | --- | --- |
| OpenAI | `scripts/inference_gpt_4o.sh`、`scripts/inference_gpt_4o_mini.sh`、`scripts/inference_gpt_4p5_preview.sh`、`scripts/inference_gpt_o1.sh`、`scripts/inference_gpt_o3_mini.sh` | 128k |
| Gemini | `scripts/inference_gemini_*.sh` | 128k，可改 1M |
| Claude | `scripts/inference_claude_*.sh` | 128k |
| Lambda-hosted Llama/DeepSeek | `scripts/inference_llama*.sh`、`scripts/inference_deepseek_r1_671b.sh` | 128k，可改 1M 的脚本有标注 |

OpenAI standalone 脚本调用：

```python
client.chat.completions.create(
    model=args["models"]["llm_model"],
    messages=messages,
)
```

没有显式设置 `temperature`、`top_p`、`max_tokens`。因此复刻官方脚本时，应记录为“未显式设置，使用 provider 默认值”。Claude 分支显式传 `max_tokens=128000`；其他 provider 分支也没有统一 temperature/top-p 设置。

`config.yaml` 中 `models.llm_model: gpt-4o` 主要是默认模型配置；实际运行脚本会用 `--model` 覆盖。

### 5.3 o-series system role 处理

官方代码对名字中包含 `o` 的 OpenAI 模型调用 `convert_role_system_to_user()`，把 `system` message 前缀合并进后续 user message，因为部分模型不支持 system role。这个逻辑会影响 PersonaMem 的 persona system messages；如果我们复现官方 direct long-context profile，需要保留该兼容行为。

### 5.4 Judge Prompt

PersonaMem 主评测没有 Judge LLM，也没有 judge prompt。评分由 `correct_answer` 精确比较完成。

## 6. Method Adapter 接口需求

### 6.1 官方 direct long-context profile

如果目标是复现 PersonaMem 官方发布仓库的默认 evaluation，它不需要 memory method adapter。它只需要一个 long-context answer LLM：

```python
answer(messages: list[{"role": str, "content": str}]) -> str
```

输入包含：

```text
sliced context messages + current user question/options/instruction
```

输出是自由文本 response，scorer 从中解析 `(a)-(d)`。

### 6.2 我们框架的 memory-module profile

如果目标是把 PersonaMem 纳入我们的 Agent Memory Benchmark 框架，用它评测 memory method，接口语义上仍可归入 `add + retrieve`，但 **add 的有效粒度必须细到 OpenAI-style message / message batch**。原因是同一个 `shared_context_id` 下会在不同 `end_index` 处反复提问，runner 不能每道题都重新写入完整 prefix，也不能把未来 message 提前写入当前 checkpoint。

如果保持当前框架的 `BaseMemoryProvider.add(conversation)` 形式，runner 需要把每个 delta message batch 包装成一个很小的 `Conversation` / `Session` 再多次调用 `add()`；如果未来为 PersonaMem 等 prefix-checkpoint benchmark 设计更清晰的接口，可以抽象成：

```python
class BaseMemoryProvider:
    def add(self, memory_scope_id: str, messages: list[OpenAIStyleMessage]) -> None: ...
    def retrieve(self, question: Question) -> AnswerPromptResult: ...
```

这里 `messages` 的元素就是 PersonaMem `shared_contexts_*.jsonl` 中的原始 message：

```python
{"role": "system" | "user" | "assistant", "content": "..."}
```

若暂时不改父类，概念上等价的当前接口是：

```python
class BaseMemoryProvider:
    def add(self, conversation_delta: Conversation) -> None: ...
    def retrieve(self, question: Question) -> AnswerPromptResult: ...
```

其中 `conversation_delta` 不是完整 shared context，而是 `context[cursor:end_index]` 对应的一小段 message delta。

但 loader/runner 需要做以下映射：

| PersonaMem 字段 | 框架映射 |
| --- | --- |
| `shared_context_id` | `conversation_id`。同一 shared context 下多个 question 可以共享已构建 memory，但每个 question 的 `end_index` 可能不同，需要谨慎处理增量/截断。 |
| `persona_id` | `Conversation.metadata["persona_id"]`。 |
| `shared_contexts[sid][cursor:end_index]` | 要增量写入 method 的 public history delta。最小粒度应是 OpenAI-style message；可以一次写入一个 message，也可以写入一小批连续 messages。 |
| `system: Current user persona` | OpenAI-style system message；可映射为 session-level system/context message，不能默认丢弃。 |
| `user` / `assistant` messages | OpenAI-style user/assistant message。content 中已经带有 `User:` / `Assistant:` 前缀，loader 可以保留原文或标准化 role。 |
| `user_question_or_message` | `Question.question`。 |
| `all_options` | `Question.metadata["choices"]`，answer reader 必须生成 multiple-choice prompt。 |
| `correct_answer` | private label，只给 evaluator。 |
| `distance_to_ref_*` | private/analysis metadata，用于分组，不给 method。 |

### 6.3 需要新增或注意的 runner 能力

PersonaMem 对我们现有 LoCoMo/LongMemEval runner 的冲击主要有：

1. **同一 context 多问题复用**：一个 `shared_context_id` 对应多道题，每道题的 `end_index` 可能不同。推荐按 `(benchmark_size, shared_context_id)` 建独立 memory state，并按 `end_index` 单调递增增量写入 prefix。写入粒度至少要细到 OpenAI-style message，否则无法在多个 checkpoint 之间安全复用已构建 memory state。
2. **multiple-choice answer reader**：当前 LoCoMo/LongMemEval 是 free-form answer + F1/LLM judge；PersonaMem 需要 `(a)-(d)` 选择题 reader 和 exact option accuracy。
3. **system persona message**：官方 public input 包含 persona profile；framework loader 需要决定是否把 system message 写入 method，或放到 answer prompt 里。若目标复现官方，应保留。
4. **evidence 不可直接评估**：没有 `target_turn_id`，只能按 accuracy 和距离分组分析。
5. **history 截断是按 message index**：`end_index_in_shared_context` 是 list index，不是 token offset。loader 必须严格使用 message 切片。
6. **question type 命名需要 normalization**：本地不同版本存在新旧字段名混用。
7. **probe 不回写**：PersonaMem 的 questions 是评测 probe，不是历史对话的一部分；回答问题时不能把 question 或 answer 写回 method memory。

### 6.4 对当前 `add(conversation)` 粒度的判断

PersonaMem 大体仍可转换成 `conversation -> session/block -> turn/message`。但从正确性和效率看，直接把完整 shared context 做一次 `add(conversation)` 并不适合 memory-module profile：它要么泄露当前 question 之后的未来 messages，要么在每道 question 上重复写入大量 prefix。更理想的实现是：

```text
按 shared_context_id 建一个 run-level memory cache
按 end_index 单调递增增量 add 新 OpenAI-style messages
到每道 question 时 retrieve + multiple-choice answer
```

这说明 PersonaMem 暂时不要求新的 memory 能力如 update/delete/forget/multimodal/environment action，但它要求 runner 在超长 shared context 和多 question prefix 上更聪明；否则实验成本会爆炸。

## 7. 未确认项

1. 官方仓库没有发布 RAG / Mem0 外部 memory module 的完整 evaluation adapter；论文只描述 RAG top-5 BGE-M3 messages 和 Mem0 top-5 facts。若后续要复现论文 Figure 5，需要单独实现或寻找作者未公开脚本。
2. `questions_*.csv` 没有 `groundtruth_info` 和 reference message id；构造代码中存在这些中间信息，但 HF `PersonaMem-v1` 发布版没有保留。因此 retrieval recall 无法官方复算。
3. `question_type` 命名在三档数据中不完全一致；需要 loader normalization 表，并在 evaluator 输出时保留原始类型和 normalized 类型。
4. OpenAI / Gemini / Lambda 分支没有显式 temperature、top-p、max_tokens；复现实验时应记录 provider 默认参数，或者由我们框架显式设定一个 profile，但这会偏离官方脚本。
5. 当前调研只下载并审计了用户提供的 `PersonaMem-v1`。官方 README badge 指向 `bowen-upenn/PersonaMem`，仓库还提示 PersonaMem-v2 / ImplicitPersona 已发布；是否调研 v2 需要用户另行确认。
6. 若接入为 memory benchmark，需要决定 official direct long-context profile 与 memory-module profile 是否都保留；前者复现官方，后者才真正评测 method。

# LongMemEval 评测流程参考

1. LongMemEval 里不是“一个 sample 下面多个 session，然后每个 session/turn 都有 question”。
2. 更真实的结构是：**一个 evaluation instance = 一道最终问题 + 一整段历史聊天 sessions**。
3. 每个 instance 只有一个 `question`，问题发生在所有历史 session 之后。
4. `session` 里确实是多个 turn，turn 是 `{"role": "user/assistant", "content": ...}`。
5. `reset` 应该发生在**每个 evaluation instance / question_id 之间**，而不是每个 session 或 turn 之间。

---

## 1. LongMemEval 的真实 dataset 层级

LongMemEval 官方数据包有三个主要文件：`longmemeval_s_cleaned.json`、`longmemeval_m_cleaned.json`、`longmemeval_oracle.json`。README 里说明 S 版本大约 40 个 history sessions，M 版本大约 500 个 sessions，oracle 版本只保留 evidence sessions。每个文件里面有 **500 个 evaluation instances**。

真实层级应该这样理解：

```text
dataset file
└── evaluation instance 1
    ├── question_id
    ├── question_type
    ├── question
    ├── answer
    ├── question_date
    ├── haystack_session_ids: [sid1, sid2, sid3, ...]
    ├── haystack_dates:       [date1, date2, date3, ...]
    ├── haystack_sessions:    [session1, session2, session3, ...]
    └── answer_session_ids: evidence session ids

└── evaluation instance 2
    ├── ...
```

也就是说，**一个 instance 就对应一道问题**。这个 instance 里包含很多历史 session，这些 session 是给这道问题准备的“记忆环境”。

---

## 2. session 和 turn 到底是什么？

你对 session 和 turn 的理解基本对，但要更精确一点：

```json
"haystack_sessions": [
  [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
]
```

这里：

```text
haystack_sessions[i]
```

就是第 i 个 session。

```text
haystack_session_ids[i]
```

是这个 session 的 id。

```text
haystack_dates[i]
```

是这个 session 的时间戳。

三者是按位置对齐的。

README 说得很明确：`haystack_sessions` 是 user-assistant chat history sessions，每个 session 是 turn 的列表，每个 turn 是 `{"role": user/assistant, "content": message content}`。如果某个 turn 包含回答问题所需证据，会额外有 `has_answer: true`，这个标签用于 turn-level memory recall accuracy evaluation。

所以你可以把它理解成：

```text
一个 session = 某一天/某个时间发生的一段对话
一个 turn = session 里面的一条消息
一个 round = 通常可以近似理解为 user turn + assistant turn
```

但代码里真正处理的是 **turn/message 级别**，不是严格的“你一句我一句”round。

---

## 3. question 是放在哪里的？每个 session 都有 question 吗？

不是。

LongMemEval 的设计是：

```text
先给模型一堆历史聊天 session
然后在最后给一个 question
模型需要基于历史记忆回答这个 question
```

README 里直接说：LongMemEval 要求 chat systems 在线解析动态交互进行记忆，并在所有 interaction sessions 之后回答问题。

所以真实流程是：

```text
session 1
session 2
session 3
...
session N
question_date
question
answer
```

不是这样：

```text
session 1 -> question
session 2 -> question
session 3 -> question
```

也不是：

```text
turn 1 -> question
turn 2 -> question
turn 3 -> question
```

`question` 是这个 evaluation instance 的最终测试题。`answer` 是标准答案。`question_date` 是提问时间，用于 temporal reasoning、knowledge update 等任务。

---

## 4. `has_answer` 和 `answer_session_ids` 是干什么的？

这两个字段非常重要，因为它们决定了 LongMemEval 不只是 QA benchmark，也能评估 memory retrieval。

### `answer_session_ids`

这是证据 session 的 id 列表。也就是：哪些历史 session 里包含回答这个 question 所需要的信息。README 明确说它用于 session-level memory recall accuracy evaluation。

如果你的 method 是 memory retriever，那么它 retrieve 出来的 session id 可以和 `answer_session_ids` 对比，计算 retrieval recall。

### `has_answer: true`

这是 turn 级别证据标签。某些 turn 里会有：

```json
{
  "role": "user",
  "content": "...",
  "has_answer": true
}
```

这个不是给模型看的，而是给评测用的。官方 generation 代码在喂给 reader 之前会把 `has_answer` 删除，避免泄漏答案标签。代码里确实会检查并 `pop('has_answer')`。

所以：

```text
answer_session_ids = 哪些 session 是证据
has_answer = 哪些 user turn 是证据
```

---

## 5. LongMemEval 到底要求 method 返回 answer 还是 memory？

这个要分两种评测范式，别混了。

### 范式 A：把你的 method 当完整 chat assistant

这是 README “Testing Your System” 里最直接的方式。

你把 timestamped history 喂给自己的系统，让系统输出最终答案，然后保存成 jsonl：

```json
{"question_id": "...", "hypothesis": "..."}
```

然后用 `evaluate_qa.py` 评测。README 明确说输出文件每行包含两个字段：`question_id` 和 `hypothesis`。

这种情况下：

```text
method 最终必须返回 answer
```

也就是：

```python
answer = method.response(question)
```

然后拿这个 answer 和标准答案做自动评测。

---

### 范式 B：把你的 method 当 memory module / retriever

官方仓库也提供了 memory retrieval 和 RAG generation 两部分代码。README 说代码分布在 `src/retrieval` 和 `src/generation`，分别对应 memory retrieval 和 retrieval-augmented question answering。

这种情况下，流程是：

```text
history sessions
   ↓
memory retriever 检索相关 memory
   ↓
reader LLM 基于 retrieved memory 回答 question
   ↓
evaluate_qa.py 评测最终 answer
```

所以如果你只做 memory method，它可以只返回 memory/retrieval results；但为了 LongMemEval 的最终 QA 分数，你还需要接一个 reader，把 retrieved memory 变成最终 answer。

官方 retrieval 代码就是这么做的：先根据 `entry['question']` 做 retrieval，然后把 ranked items 存到 `retrieval_results` 里。 随后 generation 代码读取 `retrieval_results['ranked_items']`，把 top-k 记忆转成 prompt，调用 reader model 生成最终 `hypothesis`。 

所以最准确的说法是：

```text
LongMemEval 最终评测的是 answer。
但是它也支持单独评测 memory retrieval。
```

你论文里可以这样写：

> LongMemEval can be used in two modes: end-to-end QA evaluation, where the evaluated system directly outputs an answer; and retrieval-augmented evaluation, where a memory module first retrieves relevant historical sessions or turns, and a reader model generates the final answer.

---

## 6. 官方代码里的真实评测流程

### 6.1 Long-context baseline：不做 retrieval，直接塞完整历史

README 给的命令是：

```bash
bash run_generation.sh DATA_FILE MODEL full-history-session TOPK json false con
```

这里的意思是：把完整历史 sessions 放到 prompt 里，让 reader model 直接回答。README 还强调，`longmemeval_s` 和 `longmemeval_oracle` 适合 128k context，`longmemeval_m` 太长，不适合直接 long-context testing。

代码里对应的是：

```bash
full-history-session -> orig-session
```

`run_generation.sh` 里把 `full-history-session` 映射成 `orig-session`。

然后 `run_generation.py` 会遍历所有 sessions，把它们拼进 prompt：

```text
History Chats:
Session 1:
Session Date: ...
Session Content: ...

Session 2:
Session Date: ...
Session Content: ...

Current Date: ...
Question: ...
Answer:
```

代码里 prompt template 就是这个结构。

---

### 6.2 Retrieval baseline：先检索 memory，再回答

官方 retrieval 命令：

```bash
bash run_retrieval.sh IN_FILE RETRIEVER GRANULARITY
```

`RETRIEVER` 可以是 `flat-bm25`、`flat-contriever`、`flat-stella`、`flat-gte`，`GRANULARITY` 可以是 `turn` 或 `session`。

代码里的真实逻辑是：

#### 第一步：对每个 instance 单独建索引

注意，是对每个 `entry` 单独处理。`run_retrieval.py` 里对每个 entry 读取：

```python
entry['haystack_session_ids']
entry['haystack_sessions']
entry['haystack_dates']
```

然后把这些 session/turn 构造成 corpus。

如果 granularity 是 `session`，它把一个 session 里所有 user 消息拼起来作为一个检索单元。注意，它默认只拼 user-side content，不拼 assistant-side content。

如果 granularity 是 `turn`，它把每个 user turn 作为一个检索单元。

这一点很关键：**官方 retrieval baseline 检索时主要索引 user 消息，而不是完整 user-assistant 对话。**

#### 第二步：用 question 当 query 检索

代码里：

```python
query = entry['question']
rankings = retriever_master.run_flat_retrieval(query, args.retriever, corpus)
```

也就是 question 本身作为检索 query。

#### 第三步：保存 retrieval_results

每个检索结果会保存：

```json
{
  "corpus_id": "...",
  "text": "...",
  "timestamp": "..."
}
```

代码里保存到 `retrieval_results.ranked_items`。

#### 第四步：计算 retrieval metrics

官方计算：

```text
recall_any@k
recall_all@k
ndcg_any@k
```

k 包括 1、3、5、10、30、50。

metric 具体定义也很直接：

```text
recall_any@k = top-k 里至少命中一个证据 memory
recall_all@k = top-k 里命中全部证据 memory
ndcg_any@k = 根据证据 memory 的排名位置计算 NDCG
```

代码里 `evaluate_retrieval` 就是这么写的。

另外，retrieval 评测会跳过 abstention instances，因为这些问题通常问的是不存在的信息，没有 ground-truth answer location。README 和代码都说明了这一点。 

---

### 6.3 Retrieval-Augmented Generation：用 retrieved memory 生成答案

有了 retrieval log 之后，官方 generation 脚本会读 `retrieval_results`，把 top-k retrieved memory 找回来，然后交给 reader model 回答。README 说明 `RETRIEVAL_LOG_FILE` 需要包含 retrieval 步骤加入的 `retrieval_results` 字段。([GitHub][1])

代码里对 `flat-session` 的处理是：根据 retrieved `corpus_id` 找回原始 session，然后放入 prompt。

对 `flat-turn` 的处理是：根据 retrieved turn id 找回对应 turn，而且会自动把这个 turn 的下一个 turn 也带上，相当于把一个 user turn 扩展成一个小 round。

然后 generation 代码会：

1. 删除 `has_answer` 标签；
2. 按时间排序 retrieved chunks；
3. 格式化成 `History Chats`;
4. 加上 `Current Date` 和 `Question`;
5. 调用 reader model；
6. 输出 `{question_id, hypothesis}`。  

---

## 7. QA 评测怎么做？

LongMemEval 不是简单 exact match。官方 `evaluate_qa.py` 用另一个 LLM judge 判断模型回答是否正确。

它会读取：

```python
hypotheses = your output
references = dataset reference file
```

然后根据 `question_id` 对齐，把：

```text
question
correct answer
model response
```

喂给 evaluator model，让 evaluator 输出 yes/no。

不同 question type 的判定 prompt 不完全一样：

* 普通 single-session / multi-session：判断 response 是否包含正确答案。
* temporal-reasoning：允许天数类 off-by-one error。
* knowledge-update：只要包含 updated answer，就算对。
* preference：看回答是否满足 rubric，不要求逐点覆盖。
* abstention：看模型是否识别“无法回答”。

最后输出整体 Accuracy 和每个 question type 的 Accuracy。

所以最终 QA metric 是：

```text
LLM-as-a-judge accuracy
```

不是 F1，也不是 EM。

---

## 8. reset 的真实时机

你的直觉里最需要明确的就是这个。

### 正确 reset 时机

```python
for entry in dataset:
    memory.reset()  # 每个 question_id / evaluation instance 开始前 reset

    for session in entry["haystack_sessions"]:
        memory.ingest(session)

    answer_or_memory = method.respond_or_retrieve(entry["question"])

    evaluate(...)

    # 下一个 entry 前必须 reset
```

也就是说：

```text
reset per evaluation instance
```

原因很简单：每个 evaluation instance 是独立构造的一段历史 + 一个问题。如果你不 reset，让 instance A 的记忆污染 instance B，那分数就不干净了。

### 不应该 reset 的地方

不要每个 session reset。因为 LongMemEval 测的是 long-term memory，session 之间的信息积累就是任务核心。

不要每个 turn reset。turn 是 session 内部消息，reset 会直接破坏记忆。

不要在 question 前 reset。question 要依赖前面所有 history sessions。

### 对 oracle 文件的额外提醒

README 说 `longmemeval_s` 和 `longmemeval_m` 的 `haystack_session_ids` 是按 timestamp 排序的，但 `longmemeval_oracle` 不是按 timestamp 排序。

所以如果你要模拟“在线记忆注入”，更稳妥的做法是：

```python
sessions = sorted(
    zip(haystack_dates, haystack_session_ids, haystack_sessions),
    key=lambda x: x[0]
)
```

官方 generation 代码也会把 retrieved chunks 按日期排序后再放进 prompt。

---



##  最终一句话总结

LongMemEval 的真实评测流程是：

```text
对每个 question_id：
    reset memory
    按时间顺序把这个 instance 的所有 haystack sessions 灌入 method
    在 question_date 提出最终 question
    如果 method 是完整系统：直接返回 answer
    如果 method 是 memory module：先 retrieve memory，再由 reader 基于 memory 生成 answer
    保存 {question_id, hypothesis}
最后用 evaluate_qa.py 通过 LLM judge 计算 QA accuracy
同时可选地用 answer_session_ids / has_answer 评估 session-level 或 turn-level retrieval recall
```

你现在最应该记住的结构不是“dataset → sample → session → turn → question”，而是：

```text
dataset
→ evaluation instances
→ 每个 instance = 一段 timestamped multi-session history + 一个最终 question + 一个 answer
→ session = 多条 user/assistant turns
→ evidence labels = answer_session_ids + has_answer
```

这才是 LongMemEval 最真实的评测范式。

# 补充
对，你现在这个理解**基本正确**：

```text
LongMemEval 的一个 evaluation instance
≈ LoCoMo 里的一个 sample / 一个测试样本
≈ 一道最终 question 对应的一整包历史记忆材料
```

更准确一点：

```text
dataset file
→ 多个 evaluation instances
→ 每个 instance 有多个 history sessions
→ 每个 session 有多个 turns
→ 每个 turn 是一条 user 或 assistant message
→ 每个 instance 最后只有一个 question
```

README 里明确说每个数据文件有 500 个 evaluation instances，每个 instance 包含 `question_id`、`question_type`、`question`、`answer`、`question_date`、`haystack_session_ids`、`haystack_dates`、`haystack_sessions`、`answer_session_ids` 这些字段。

---

## 1. `dataset file`

这个就是一个完整的数据文件，比如：

```text
longmemeval_s_cleaned.json
longmemeval_m_cleaned.json
longmemeval_oracle.json
```

它不是一个样本，而是**一整个测试集文件**。

区别是：

```text
longmemeval_s_cleaned.json
→ 每个 instance 大约 40 个 history sessions，约 115k tokens

longmemeval_m_cleaned.json
→ 每个 instance 大约 500 个 history sessions，更长

longmemeval_oracle.json
→ 只保留证据 sessions，相当于 oracle retrieval 后的版本
```

所以可以理解为：

```text
dataset file = 500 道题的集合
```

---

## 2. `evaluation instance`

这是 LongMemEval 里最核心的单位。

一个 `evaluation instance` 可以理解成：

```text
为了考一道 question，专门准备的一整段历史聊天包。
```

它不是单纯一段对话，而是：

```text
一个最终问题
+ 很多历史 sessions
+ 标准答案
+ 证据位置标注
```

所以它和 LoCoMo 里的 sample 类似，但我建议你别直接说“完全等价”。更严谨的说法是：

```text
LongMemEval 的 evaluation instance 是一个 QA-centered sample。
```

也就是它是**围绕一个问题构造出来的测试样本**。

---

## 3. `question_id`

这是每个问题的唯一 ID。

作用类似数据库主键：

```json
"question_id": "knowledge_update_123"
```

它的作用是：

```text
1. 唯一区分每一道题
2. 把模型输出和标准答案对齐
3. 判断是否是 abstention 问题
```

特别注意：如果 `question_id` 以 `_abs` 结尾，说明这是一个 abstention question，也就是**不可回答问题**。README 里说，如果 `question_id` ends with `_abs`，那么这个问题就是 abstention question。

比如：

```text
q_001_abs
```

意思是：这个问题问的是历史里不存在的信息，模型应该回答“不知道 / 信息不足 / 无法从历史中确定”。

---

## 4. `question_type`

这个字段表示问题类型。

LongMemEval 主要有这些类型：

```text
single-session-user
single-session-assistant
single-session-preference
temporal-reasoning
knowledge-update
multi-session
```

README 里明确列出了这些类型。

分别是什么意思？

### `single-session-user`

答案主要来自**某一个 session 里用户说过的信息**。

例如历史里用户说：

```text
user: I moved to Seattle last month.
```

最后问：

```text
Where did the user move last month?
```

这就是从单个 session 的 user 信息中抽取答案。

---

### `single-session-assistant`

答案主要来自**某一个 session 里 assistant 说过的信息**。

比如之前 assistant 给用户推荐过某个方案，后面问：

```text
What restaurant did the assistant recommend to me?
```

这个信息可能不是用户说的，而是 assistant 说的。

这个类型很重要，因为很多 memory system 只存 user facts，容易忽略 assistant-side 信息。

---

### `single-session-preference`

测试用户偏好记忆。

比如用户之前说：

```text
I prefer vegetarian restaurants and quiet places.
```

后面问：

```text
Can you recommend a restaurant for dinner?
```

这类问题不一定有一个非常短的标准答案，而是看模型回答是否体现用户偏好。

所以这里的 `answer` 有时更像一个 rubric，也就是“理想回答应该满足什么条件”。官方 QA 评测代码里，对 `single-session-preference` 会把 `answer` 当成 desired personalized response 的 rubric 来判断，而不是普通 exact answer。

---

### `temporal-reasoning`

测试时间推理。

比如历史里有：

```text
2023-05-01: I started taking the medicine.
2023-05-10: I stopped taking the medicine.
```

最后问：

```text
How many days did I take the medicine?
```

这就不仅要找到信息，还要结合日期计算。

`question_date` 在这类题里尤其重要。

---

### `knowledge-update`

测试知识更新。

比如用户之前说：

```text
2023-01-01: My favorite color is blue.
```

后来又说：

```text
2023-05-01: Actually, now my favorite color is green.
```

最后问：

```text
What is my favorite color?
```

正确答案应该是更新后的 `green`，而不是旧的 `blue`。

这个类型的重点是：

```text
不是找到所有相关记忆就行，而是要知道哪条信息更新、更晚、更有效。
```

官方评测代码里也对 `knowledge-update` 单独处理：如果模型回答里同时提到旧信息和更新后答案，只要更新后答案是需要的答案，也算正确。

---

### `multi-session`

答案需要跨多个 session 推理。

比如：

```text
session 1: 用户说自己姐姐叫 Alice
session 8: 用户说 Alice 住在 Boston
```

最后问：

```text
Where does my sister live?
```

这就需要跨 session 链接信息：

```text
my sister = Alice
Alice lives in Boston
```

所以这类问题比 single-session 更难。

---

### abstention

严格来说，`abstention` 不是直接写在 `question_type` 里的一个普通值，而是通过 `question_id` 是否以 `_abs` 结尾来判断。README 明确说 `question_id` ends with `_abs` 就是 abstention question。

这类问题考的是：

```text
模型能不能在历史中没有答案时承认不知道。
```

---

## 5. `question`

这是最终要问模型的问题。

它不是 session 里的问题，而是**评测阶段的问题**。

结构是：

```text
先有很多 haystack sessions
最后才有 question
```

所以不要理解成：

```text
每个 session 后面都有一个 question
```

而应该理解成：

```text
一个 instance 只有一个最终 question
```

例如：

```json
"question": "What city did I say my sister moved to?"
```

模型需要基于这个 instance 里的历史 sessions 回答。

---

## 6. `answer`

这是标准答案，或者说 expected answer。

普通 QA 类型里，它就是答案：

```json
"answer": "Boston"
```

但是对于 `single-session-preference`，它可能更像一个评价标准/rubric，例如：

```text
The response should recommend a quiet vegetarian-friendly restaurant.
```

对于 abstention，它可能是解释为什么不可回答。

官方评测时不是简单字符串匹配，而是用 evaluator model 判断 `hypothesis` 是否符合 `answer`。代码里会把 `question`、`answer`、模型输出 `hypothesis` 放进评测 prompt，让 evaluator 输出 yes/no。

所以：

```text
answer = 最终 QA 评测的参考答案 / 参考标准
```

不是一定要和模型输出逐字一致。

---

## 7. `question_date`

这是最终 question 发生的日期。

比如：

```json
"question_date": "2023-08-15"
```

它的作用是告诉模型：

```text
当前提问时间是什么时候。
```

为什么重要？

因为 LongMemEval 很多题和时间有关：

```text
1. temporal-reasoning：需要根据日期计算时间差
2. knowledge-update：需要知道哪个记忆更晚
3. abstention：有时需要判断截至当前日期是否有足够信息
```

官方 generation prompt 里也会把它写成：

```text
Current Date: {question_date}
Question: {question}
Answer:
```

代码里就是这么拼 prompt 的。

所以 `question_date` 不是 session 的时间，而是**最终提问的时间**。

---

## 8. `haystack_session_ids`

这是历史 sessions 的 ID 列表。

例如：

```json
"haystack_session_ids": [
  "session_001",
  "session_002",
  "session_003"
]
```

每个 id 对应一个 session。

它和下面两个字段是位置一一对应的：

```text
haystack_session_ids[i]
haystack_dates[i]
haystack_sessions[i]
```

也就是：

```text
第 i 个 session 的 id   = haystack_session_ids[i]
第 i 个 session 的日期 = haystack_dates[i]
第 i 个 session 的内容 = haystack_sessions[i]
```

作用主要有三个：

```text
1. 标识每个 session
2. retrieval 评测时判断你有没有召回正确 session
3. 和 answer_session_ids 对齐
```

如果你的 memory method 返回 session 级别 memory，那么它最好保留这个 session_id。否则你很难和官方 `answer_session_ids` 做 retrieval metric 对齐。

---

## 9. `haystack_dates`

这是每个 history session 的时间戳列表。

例如：

```json
"haystack_dates": [
  "2023-01-10",
  "2023-03-05",
  "2023-06-20"
]
```

它和 `haystack_session_ids`、`haystack_sessions` 一一对应：

```text
session_001 发生在 2023-01-10，内容是 session1
session_002 发生在 2023-03-05，内容是 session2
session_003 发生在 2023-06-20，内容是 session3
```

它的作用：

```text
1. 模拟长期历史聊天的时间顺序
2. 支持 temporal reasoning
3. 支持 knowledge update
4. 帮助 reader 在 prompt 里看到每个 session 的发生时间
```

注意一个坑：README 说 `longmemeval_s` 和 `longmemeval_m` 里的 history sessions 是按时间排序的，但 `longmemeval_oracle` 不是排序的。

所以你自己写 benchmark harness 时，最好主动排序：

```python
sessions = sorted(
    zip(haystack_dates, haystack_session_ids, haystack_sessions),
    key=lambda x: x[0]
)
```

---

## 10. `haystack_sessions`

这是最核心的历史对话内容。

它是一个 list，里面每个元素是一个 session。

例如：

```json
"haystack_sessions": [
  [
    {"role": "user", "content": "I moved to Seattle last month."},
    {"role": "assistant", "content": "That sounds exciting!"}
  ],
  [
    {"role": "user", "content": "My sister Alice lives in Boston."},
    {"role": "assistant", "content": "Thanks for sharing."}
  ]
]
```

所以：

```text
haystack_sessions[0] = 第一个 session
haystack_sessions[0][0] = 第一个 session 的第一个 turn
haystack_sessions[0][0]["role"] = user
haystack_sessions[0][0]["content"] = 具体文本
```

README 说每个 session 是 turns 的列表，每个 turn 是：

```json
{"role": "user/assistant", "content": "message content"}
```

并且包含证据的 turn 会额外有 `has_answer: true`。

这里你要特别注意：

```text
turn 不是“一轮你一句我一句”
turn 是一条 message
```

所以：

```text
user 说一句 = 一个 turn
assistant 回一句 = 另一个 turn
```

你说的“一轮对话”更准确叫 round，通常是：

```text
user turn + assistant turn
```

---

## 11. `answer_session_ids`

这是证据 session 的 ID 列表。

例如：

```json
"answer_session_ids": [
  "session_002",
  "session_008"
]
```

意思是：

```text
回答这个 question 所需要的证据在 session_002 和 session_008 里面。
```

它主要用于 session-level retrieval evaluation。

比如模型/记忆模块 retrieve 出：

```text
top-3 = [session_005, session_002, session_010]
```

如果 `answer_session_ids = [session_002]`，那说明 top-3 命中了证据 session。

所以：

```text
answer_session_ids 不是标准答案
answer_session_ids 是标准答案所在的历史 session 位置
```

这一点非常关键。

---

## 12. `has_answer`

虽然你列的顶层字段里没有它，但必须一起理解。

它出现在 `haystack_sessions` 里面的某些 turn 中：

```json
{
  "role": "user",
  "content": "My sister Alice lives in Boston.",
  "has_answer": true
}
```

意思是：

```text
这个 turn 包含回答最终 question 所需的证据信息。
```

它用于 turn-level retrieval evaluation。

但是它**不能喂给模型**，否则就是泄题。官方 generation 代码在构造 prompt 前会把 `has_answer` 删除。

所以：

```text
answer_session_ids = session 级证据标签
has_answer = turn 级证据标签
```

---

## 13. 三个字段的对齐关系

这是你一定要抓住的核心。

假设：

```json
"haystack_session_ids": ["s1", "s2", "s3"],
"haystack_dates": ["2023-01-01", "2023-02-01", "2023-03-01"],
"haystack_sessions": [session1, session2, session3]
```

那么真实含义是：

```text
s1 发生在 2023-01-01，内容是 session1
s2 发生在 2023-02-01，内容是 session2
s3 发生在 2023-03-01，内容是 session3
```

这三个 list 必须一起看，不能拆开看。

你可以把它们合成一个更好理解的结构：

```json
[
  {
    "session_id": "s1",
    "date": "2023-01-01",
    "turns": session1
  },
  {
    "session_id": "s2",
    "date": "2023-02-01",
    "turns": session2
  },
  {
    "session_id": "s3",
    "date": "2023-03-01",
    "turns": session3
  }
]
```

LongMemEval 原始数据只是为了节省结构，把它拆成了三个并行 list。

---

## 14. 用一个完整小例子串起来

假设一个 instance 是这样：

```json
{
  "question_id": "multi_session_001",
  "question_type": "multi-session",
  "question": "Where does my sister live?",
  "answer": "Boston",
  "question_date": "2023-08-01",
  "haystack_session_ids": ["s1", "s2", "s3"],
  "haystack_dates": ["2023-01-01", "2023-03-01", "2023-06-01"],
  "haystack_sessions": [
    [
      {"role": "user", "content": "My sister's name is Alice.", "has_answer": true},
      {"role": "assistant", "content": "Got it."}
    ],
    [
      {"role": "user", "content": "I like spicy food."},
      {"role": "assistant", "content": "Thanks for telling me."}
    ],
    [
      {"role": "user", "content": "Alice recently moved to Boston.", "has_answer": true},
      {"role": "assistant", "content": "Boston is a great city."}
    ]
  ],
  "answer_session_ids": ["s1", "s3"]
}
```

这个 instance 的含义是：

```text
最终问题：
Where does my sister live?

需要从历史里知道：
1. my sister = Alice
2. Alice moved to Boston

证据在：
s1 和 s3

最终答案：
Boston
```

如果你是 memory method，流程应该是：

```text
reset
ingest s1
ingest s2
ingest s3
retrieve / answer question
```

不能在 s1、s2、s3 之间 reset。

---

## 15. 你现在应该怎么记这个结构？

最推荐你记成这个版本：

```text
LongMemEval dataset file
= 500 个 QA-centered evaluation instances

每个 instance
= 一个最终问题 question
+ 一组带时间戳的历史 sessions
+ 一个标准答案 answer
+ 证据 session/turn 标注

每个 session
= 某个时间点的一段 user-assistant chat

每个 turn
= 一条 user 或 assistant message
```
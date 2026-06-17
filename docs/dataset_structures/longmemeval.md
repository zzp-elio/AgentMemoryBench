下面这版是**只描述 LongMemEval 数据结构、字段含义、字段在测评中的作用**，不指挥 Codex 怎么写代码。

````markdown
# LongMemEval Dataset Structure and Evaluation Semantics

LongMemEval 的基本单位是 `evaluation instance`。一个 dataset file 由多个 evaluation instances 组成。每个 instance 是围绕一个最终 question 构造的多 session 历史对话样本。

整体结构：

```text
dataset file
└── evaluation instance
    ├── question_id
    ├── question_type
    ├── question
    ├── answer
    ├── question_date
    ├── haystack_session_ids
    ├── haystack_dates
    ├── haystack_sessions
    └── answer_session_ids
````

LongMemEval README 中说明，每个数据文件包含 500 个 evaluation instances，并且每个 instance 包含上述字段。

---

## 1. Dataset File

LongMemEval 主要包含三类数据文件：

```text
longmemeval_s_cleaned.json
longmemeval_m_cleaned.json
longmemeval_oracle.json
```

### `longmemeval_s_cleaned.json`

LongMemEval_S。每个 instance 的历史大约包含 40 个 history sessions，拼接后约 115k tokens。

### `longmemeval_m_cleaned.json`

LongMemEval_M。每个 instance 的历史大约包含 500 个 history sessions，比 S 版本更长。

### `longmemeval_oracle.json`

Oracle retrieval 版本。该版本只包含 evidence sessions，也就是与回答问题直接相关的历史 sessions。

---

## 2. Evaluation Instance

一个 evaluation instance 是 LongMemEval 的核心样本单位。

它可以理解为：

```text
一个最终 question
+ 多个带时间戳的 history sessions
+ 一个 reference answer
+ evidence session / turn annotations
```

它和 LoCoMo 里的 sample 类似，但 LongMemEval 的 instance 更明确是 QA-centered sample，即围绕一个最终问题组织历史材料。

一个 instance 内部有多个 sessions；每个 session 内部有多个 turns；每个 turn 是一条 user 或 assistant message。

---

## 3. Field Definitions

## 3.1 `question_id`

类型：`str`

含义：当前 evaluation instance / question 的唯一标识符。

作用：

```text
1. 标识当前测试问题。
2. 用于把模型输出和 reference entry 对齐。
3. 用于识别 abstention question。
```

如果 `question_id` 以 `_abs` 结尾，则该 instance 是 abstention question，即历史中没有足够信息回答该问题。

---

## 3.2 `question_type`

类型：`str`

含义：当前 question 的任务类型。

常见取值：

```text
single-session-user
single-session-assistant
single-session-preference
temporal-reasoning
knowledge-update
multi-session
```

此外，abstention 不是普通的 `question_type` 值，而是通过 `question_id` 是否以 `_abs` 结尾识别。

作用：

```text
1. 表示该问题测试的长期记忆能力类型。
2. 影响 QA correctness 的判断方式。
3. 影响 evidence 的使用方式，例如单 session 抽取、跨 session 推理、时间推理、知识更新、偏好记忆等。
```

---

## 3.3 `question`

类型：`str`

含义：当前 instance 最终要回答的问题。

注意：

```text
每个 evaluation instance 只有一个最终 question。
question 不是每个 session 一个，也不是每个 turn 一个。
```

测评语义：

```text
系统需要基于该 instance 中的 history sessions 回答这个 question。
```

---

## 3.4 `answer`

类型：通常为 `str`，也可能是自然语言形式的 reference / rubric。

含义：当前 question 的参考答案或评测标准。

不同任务中的语义略有不同：

```text
普通 QA 类型：
answer 是 expected answer。

single-session-preference：
answer 更像 personalized response 的 rubric。

abstention：
answer 通常表示为什么该问题不可回答，或者期望模型识别信息不足。
```

测评作用：

```text
answer 用于判断模型输出 hypothesis 是否正确。
```

LongMemEval 的 QA evaluation 不是简单 exact match，而是用 evaluator model 判断 hypothesis 是否满足 reference answer。官方 `evaluate_qa.py` 会读取 `question_id`、`question`、`answer` 和模型输出 `hypothesis`，然后输出 yes/no correctness label。

---

## 3.5 `question_date`

类型：`str`

含义：最终 question 发生的日期，也就是当前提问时间。

作用：

```text
1. temporal-reasoning 任务中用于时间差、时间范围、事件先后关系判断。
2. knowledge-update 任务中用于判断截至提问时间的有效信息。
3. generation prompt 中通常作为 Current Date 出现。
```

字段关系：

```text
haystack_dates 表示历史 sessions 的发生时间。
question_date 表示最终问题提出的时间。
```

---

## 3.6 `haystack_session_ids`

类型：`list[str]`

含义：当前 instance 中所有 history sessions 的稳定 ID 列表。

它与 `haystack_dates`、`haystack_sessions` 按 index 对齐：

```text
haystack_session_ids[i]
haystack_dates[i]
haystack_sessions[i]
```

共同表示第 i 个 session 的 id、date 和原始内容。

作用：

```text
1. 给每个 session 提供稳定标识。
2. 被 answer_session_ids 引用，用于标注 evidence sessions。
3. retrieval evaluation 中用于判断 retrieved session 是否命中 evidence session。
4. retrieval log 中通常作为 corpus_id 的基础。
5. turn-level corpus_id 可以基于 session_id 加 turn index 构造。
```

为什么不只用数组下标：

```text
session 的数组下标依赖当前排列方式。
session_id 是稳定身份。
在排序、过滤、top-k retrieval、oracle subset 等情况下，session_id 更适合作为 evidence 标识。
```

---

## 3.7 `haystack_dates`

类型：`list[str]`

含义：当前 instance 中每个 history session 的时间戳。

它与 `haystack_session_ids`、`haystack_sessions` 按 index 对齐：

```text
haystack_session_ids[i] = 第 i 个 session 的 ID
haystack_dates[i]      = 第 i 个 session 的时间
haystack_sessions[i]   = 第 i 个 session 的内容
```

作用：

```text
1. 表示长期历史对话的时间顺序。
2. 支持 temporal-reasoning。
3. 支持 knowledge-update。
4. 在 generation prompt 或 memory metadata 中标识 Session Date。
5. 在 retrieval results 中可作为 timestamp。
```

README 中说明，`longmemeval_s` 和 `longmemeval_m` 中的 sessions 按 timestamp 排序；`longmemeval_oracle` 中不一定排序。

---

## 3.8 `haystack_sessions`

类型：`list[list[dict]]`

含义：当前 instance 的原始历史对话内容。

结构：

```python
haystack_sessions = [
    session_1,
    session_2,
    ...
]

session_i = [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    ...
]
```

### Session

一个 session 是某个时间点的一段 user-assistant chat history。

### Turn

一个 turn 是一条 message，而不是“一轮 user + assistant”。

例如：

```json
{"role": "user", "content": "..."}
```

是一条 user turn。

```json
{"role": "assistant", "content": "..."}
```

是一条 assistant turn。

两条消息合起来才更接近日常说的“一轮对话”。

### Turn-level evidence annotation

某些 turn 中可能额外包含：

```json
"has_answer": true
```

含义是：该 turn 包含回答当前 question 所需的证据信息。

你上传的示例中，turn 结构包含 `role`、`content`、`has_answer` 字段；其中与答案相关的 user/assistant turn 会出现 `has_answer: true`。

---

## 3.9 `answer_session_ids`

类型：`list[str]`

含义：回答当前 question 所需 evidence sessions 的 session IDs。

它引用的是 `haystack_session_ids` 中的 session id。

作用：

```text
1. 标注 evidence sessions。
2. 用于 session-level memory retrieval evaluation。
3. 支持 multi-session 问题的多 evidence session 标注。
```

注意：

```text
answer_session_ids 不是 answer 本身。
answer_session_ids 表示证据所在 session。
```

对于 single-session 问题，`answer_session_ids` 可能只包含一个 session id。

对于 multi-session 问题，`answer_session_ids` 可能包含多个 session ids。例如：

```text
session A: user's sister is Alice
session B: Alice moved to Boston

question: Where does the user's sister live?
answer: Boston
answer_session_ids: [session A, session B]
```

这里答案字符串 `Boston` 可能只直接出现在 session B，但 session A 也是必要证据，因为它建立了 `sister = Alice` 的关系。

---

## 3.10 `has_answer`

位置：`haystack_sessions` 内部的 turn 上。

类型：`bool`

含义：该 turn 是否包含回答当前 question 所需的证据。

作用：

```text
1. 标注 turn-level evidence。
2. 用于 turn-level memory recall / retrieval evaluation。
3. 比 answer_session_ids 更细粒度。
```

关系：

```text
answer_session_ids = session-level evidence labels
has_answer         = turn-level evidence labels
```

---

# 4. Parallel Alignment of Session Fields

LongMemEval 使用三个并行 list 描述 sessions：

```json
{
  "haystack_session_ids": ["s1", "s2", "s3"],
  "haystack_dates": ["2023-01-01", "2023-02-01", "2023-03-01"],
  "haystack_sessions": [session1, session2, session3]
}
```

语义等价于：

```python
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

这三个字段不能分开理解，必须通过相同 index 对齐。

---

# 5. Task Types and Dataset Field Usage

LongMemEval 的任务类型与字段结构紧密相关。不同任务会依赖不同字段。

---

## 5.1 `single-session-user`

含义：答案主要来自某一个 session 中 user-side 的信息。

示例语义：

```text
user 曾经说过自己的学历、职业、爱好、计划等。
最终 question 询问这些 user-provided facts。
```

相关字段：

```text
question
answer
haystack_sessions
answer_session_ids
has_answer
```

测评关注：

```text
是否能够从历史中定位相关 session，并从 user turn 中抽取正确事实。
```

---

## 5.2 `single-session-assistant`

含义：答案主要来自某一个 session 中 assistant-side 的信息。

示例语义：

```text
assistant 曾经推荐过某个工具、方案、地点、计划等。
最终 question 询问 assistant 当时给出的建议或信息。
```

相关字段：

```text
question
answer
haystack_sessions 中 role == "assistant" 的 turns
answer_session_ids
has_answer
```

测评关注：

```text
系统是否保留并利用 assistant messages，而不只是记住 user facts。
```

---

## 5.3 `single-session-preference`

含义：测试用户偏好记忆和个性化回答。

示例语义：

```text
用户历史中表达了某种偏好。
最终 question 要求系统给出个性化建议或回答。
```

相关字段：

```text
question
answer
haystack_sessions
question_type
```

测评关注：

```text
系统回答是否正确利用用户偏好。
```

在该类型中，`answer` 更像 rubric，不一定是一个短字符串答案。官方 evaluation prompt 对 preference 类型单独处理，会判断模型输出是否满足 desired personalized response。

---

## 5.4 `temporal-reasoning`

含义：测试基于时间的推理能力。

可能涉及：

```text
事件先后顺序
时间间隔计算
某事件是否发生在某个时间范围内
截至 question_date 的状态判断
```

相关字段：

```text
question
answer
question_date
haystack_dates
haystack_sessions
answer_session_ids
has_answer
```

测评关注：

```text
系统是否能结合 session timestamp 和 question_date 进行时间推理。
```

官方 QA evaluation 对 temporal-reasoning 有特殊容错：如果问题询问天数、周数、月数等，轻微 off-by-one error 可以不惩罚。

---

## 5.5 `knowledge-update`

含义：测试长期记忆中的信息更新能力。

示例语义：

```text
早期 session: 用户喜欢 A
后期 session: 用户改为喜欢 B
最终 question: 用户现在喜欢什么？
answer: B
```

相关字段：

```text
question
answer
question_date
haystack_dates
haystack_sessions
answer_session_ids
has_answer
```

测评关注：

```text
系统是否能够区分旧信息和更新后的信息，并使用最终有效信息。
```

官方 QA evaluation 对 knowledge-update 有特殊判断：如果模型回答中同时提到旧信息和更新后答案，只要更新后答案是所需答案，也可以被判定正确。

---

## 5.6 `multi-session`

含义：答案需要跨多个 sessions 联合推理。

示例语义：

```text
session A: 用户的姐姐叫 Alice
session B: Alice 搬到了 Boston
question: 用户的姐姐住在哪里？
answer: Boston
```

相关字段：

```text
question
answer
haystack_sessions
answer_session_ids
has_answer
```

测评关注：

```text
系统是否能召回多个 evidence sessions，并进行跨 session 信息连接或推理。
```

在 retrieval evaluation 中，multi-session 问题通常不仅关注是否命中任意一个 evidence session，也关注是否命中全部 evidence sessions。

---

## 5.7 Abstention

识别方式：

```python
question_id.endswith("_abs")
```

含义：当前 question 在历史中没有足够信息回答。

相关字段：

```text
question_id
question
answer
haystack_sessions
```

测评关注：

```text
系统是否能识别信息不足，而不是编造答案。
```

官方 evaluation 对 abstention 使用单独 prompt，判断模型是否正确识别问题不可回答。

在 retrieval evaluation 中，abstention instances 通常没有 ground-truth answer location，因此官方 retrieval evaluation 会跳过这类 instances。

---

# 6. Evaluation-Related Outputs

## 6.1 QA Evaluation Output

LongMemEval 的 QA evaluation 需要模型输出：

```json
{"question_id": "...", "hypothesis": "..."}
```

含义：

```text
question_id: 对应当前 evaluation instance
hypothesis: 系统生成的最终答案
```

官方 `evaluate_qa.py` 会根据 `question_id` 找到 reference question 和 answer，然后判断 hypothesis 是否正确。

---

## 6.2 Retrieval Evaluation Labels

LongMemEval 中存在两级 evidence labels：

```text
session-level: answer_session_ids
turn-level: has_answer
```

### Session-level retrieval

使用 `answer_session_ids` 判断 retrieved sessions 是否命中 evidence sessions。

相关指标包括：

```text
recall_any@k
recall_all@k
ndcg_any@k
```

官方 retrieval evaluation 中会在多个 k 上计算这些指标，例如 1、3、5、10、30、50。

### Turn-level retrieval

使用 turn 中的 `has_answer` 判断 retrieved turns 是否命中 evidence turns。

turn-level corpus id 通常会基于 session id 和 turn index 构造。

---

# 7. Summary

LongMemEval 的数据结构可以压缩理解为：

```text
dataset file
= 多个 evaluation instances

evaluation instance
= 一个最终 question
+ 多个 timestamped history sessions
+ 一个 reference answer
+ session-level evidence labels
+ turn-level evidence labels

session
= 一段带日期的 user-assistant 对话

turn
= 一条 user 或 assistant message
```

字段之间的核心关系：

```text
question_id:
    当前问题的唯一标识。

question_type:
    当前问题测试的记忆能力类型。

question:
    最终要回答的问题。

answer:
    参考答案或评测标准。

question_date:
    最终问题发生时间。

haystack_session_ids:
    history sessions 的稳定 ID。

haystack_dates:
    history sessions 的时间戳。

haystack_sessions:
    history sessions 的原始对话内容。

answer_session_ids:
    session-level evidence labels。

has_answer:
    turn-level evidence labels。
```

```
```

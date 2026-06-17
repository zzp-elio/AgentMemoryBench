下面是重新整理后的版本，只作为 **HaluMem 数据集结构与字段作用说明**，不包含实现建议。

---

# HaluMem Dataset Structure & Evaluation Field Notes

## 1. Overall Structure

HaluMem 的基本组织单位是 **user**。一个数据集由多个 user record 组成，每个 user record 包含该用户的 persona 信息和按时间排列的多个 dialogue session。README 中说明每个 user JSON object 包含 `uuid`、`persona_info`、`sessions` 三个核心字段；每个 session 包含 dialogue、memory points、questions 等信息。

```text
Dataset
└── UserRecord
    ├── uuid
    ├── persona_info
    └── sessions[]
        └── Session
            ├── start_time
            ├── end_time
            ├── dialogue_turn_num
            ├── dialogue[]
            ├── memory_points[]
            ├── questions[] optional
            └── dialogue_token_length
```

HaluMem 有两个主要版本：

| Dataset       | 含义                                    |
| ------------- | ------------------------------------- |
| `Halu-Medium` | 中等长度上下文，每个 user 平均约 160k tokens。      |
| `Halu-Long`   | 长上下文版本，每个 user 约 1M tokens，并加入更多干扰内容。 |

README 中给出的统计是：两个版本都是 20 个 users，Halu-Medium 约 30,073 dialogues，Halu-Long 约 53,516 dialogues，memory points 和 QA pairs 数量相同，分别为 14,948 和 3,467。

---

# 2. UserRecord

```python
UserRecord = {
    "uuid": str,
    "persona_info": str,
    "sessions": list[Session]
}
```

| Field          | 含义                                       | 测评中的作用                                                                 |
| -------------- | ---------------------------------------- | ---------------------------------------------------------------------- |
| `uuid`         | 用户唯一标识。通常一个 JSONL row 对应一个 user record。  | 用于区分不同用户的数据与结果。                                                        |
| `persona_info` | 用户 persona profile，包含姓名、性别、背景、目标、性格、偏好等。 | 描述该 user 的初始身份信息。官方 Mem0 eval wrapper 会从 `persona_info` 中解析 user name。 |
| `sessions`     | 该 user 的多段对话 session，通常按时间顺序排列。          | HaluMem 的主要评测序列。一个 user 内的多个 session 共同构成长期记忆上下文。                      |

---

# 3. Session

```python
Session = {
    "start_time": str,
    "end_time": str,
    "dialogue_turn_num": int,
    "dialogue": list[DialogueTurn],
    "memory_points": list[MemoryPoint],
    "questions": list[Question],  # optional
    "dialogue_token_length": int
}
```

| Field                   | 含义                                         | 测评中的作用                                                                                          |
| ----------------------- | ------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| `start_time`            | 当前 session 的开始时间。                          | 官方 eval wrapper 将其转换为 timestamp，并作为本 session dialogue 写入 memory system 时的时间信息。                  |
| `end_time`              | 当前 session 的结束时间。                          | 时间元数据，主要用于描述 session 范围。                                                                        |
| `dialogue_turn_num`     | 当前 session 的对话轮数。                          | 元数据，用于描述该 session 的长度。                                                                          |
| `dialogue`              | 当前 session 内的 user-assistant utterance 序列。 | Memory system 的输入内容。官方 wrapper 会把整个 `session["dialogue"]` 转成 message list 后一次性加入 memory system。 |
| `memory_points`         | 当前 session 对应的 gold memory annotations。    | 用于 Memory Extraction、Memory Update、False Memory Resistance 等任务。                                 |
| `questions`             | 当前 session 关联的 QA pairs。不是每个 session 都一定有。 | 用于 Memory Question Answering。官方代码中如果没有 `questions` 字段，就跳过该 session 的 QA 部分。                     |
| `dialogue_token_length` | 当前 session dialogue 的 token 长度。            | 主要用于统计上下文规模。                                                                                    |

---

# 4. DialogueTurn

```python
DialogueTurn = {
    "role": "user" | "assistant",
    "content": str,
    "timestamp": str,
    "dialogue_turn": int
}
```

| Field           | 含义                                          | 测评中的作用                                                          |
| --------------- | ------------------------------------------- | --------------------------------------------------------------- |
| `role`          | 当前 utterance 的说话方，通常为 `user` 或 `assistant`。 | 区分用户陈述和助手陈述。HaluMem 中 assistant utterance 可能包含干扰信息。             |
| `content`       | 当前 utterance 的文本内容。                         | memory extraction / update 的原始文本来源。                             |
| `timestamp`     | 当前 utterance 的时间戳。                          | 可用于细粒度时间判断。官方 memory accuracy 评测会把 dialogue 还原为带 timestamp 的文本。 |
| `dialogue_turn` | 当前 utterance 所属的 turn index。                | 表示对话轮次。user 和 assistant 在同一轮中可能共享同一个 `dialogue_turn`。           |

---

# 5. MemoryPoint

```python
MemoryPoint = {
    "index": int,
    "memory_content": str,
    "memory_type": str,
    "memory_source": str,
    "is_update": "True" | "False",
    "original_memories": list[str],
    "importance": float,
    "timestamp": str
}
```

| Field               | 含义                                                                    | 测评中的作用                                                                               |
| ------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `index`             | 当前 session 内的 memory point 编号。                                        | 局部标识。                                                                                |
| `memory_content`    | 当前 memory point 的文本内容。                                                | gold memory 内容，是 extraction、update、QA evidence 的核心引用。                                |
| `memory_type`       | memory 类型，主要包括 `Persona Memory`、`Event Memory`、`Relationship Memory`。 | 用于 type-wise accuracy 统计。官方 aggregation 会按这三类 memory type 统计表现。                      |
| `memory_source`     | memory 来源类型，包括 `primary`、`secondary`、`interference`、`system`。         | 区分目标记忆、间接记忆和干扰记忆。`interference` 用于测试 false memory resistance。                        |
| `is_update`         | 字符串形式的更新标记，值为 `"True"` 或 `"False"`。                                   | 如果为 `"True"` 且 `original_memories` 非空，该 memory point 会进入 Memory Update 评测。           |
| `original_memories` | 被当前 memory point 更新、替换或修正的旧 memory 内容。                                | 用于判断 memory system 是否正确处理新旧记忆关系。                                                     |
| `importance`        | 当前 memory point 的重要性分数，通常为 0 到 1。                                     | 用于 weighted recall / weighted memory integrity 统计。官方 aggregation 使用 `importance` 加权。 |
| `timestamp`         | 当前 memory point 的创建或更新时间。                                             | 用于时间顺序、动态更新、最新状态判断。                                                                  |

## 5.1 `memory_source` 的作用

| Value          | 含义                                | 测评关联                                             |
| -------------- | --------------------------------- | ------------------------------------------------ |
| `primary`      | 直接来自用户表达的核心事实。                    | 通常是应被系统记住的目标 memory。                             |
| `secondary`    | 间接或推导得到的 memory。                  | 也可能作为 gold memory 或 QA evidence。                 |
| `interference` | 干扰记忆，常来自 assistant 的错误、未确认或误导性内容。 | 用于 False Memory Resistance。理想情况下，系统不应把它当作真实用户记忆。 |
| `system`       | 系统侧来源的 memory。                    | README 中列为可能来源之一，具体使用取决于数据样本。                    |

---

# 6. Question

```python
Question = {
    "question": str,
    "answer": str,
    "evidence": list[EvidenceItem],
    "difficulty": str,
    "question_type": str
}
```

| Field           | 含义                            | 测评中的作用                                                                                                              |
| --------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `question`      | 自然语言问题。                       | 用作 memory retrieval query。官方 wrapper 使用 `qa["question"]` 检索相关 memories。                                             |
| `answer`        | 标准答案。                         | QA judge 用它和 system response 对比。                                                                                    |
| `evidence`      | 支撑该答案的关键 memory points。       | QA judge 使用其中的 `memory_content` 作为关键证据。官方 QA 评测会传入 `question`、`answer`、`evidence memory_content`、`system_response`。 |
| `difficulty`    | 问题难度，例如 easy / medium / hard。 | 主要用于统计分析。                                                                                                           |
| `question_type` | 问题类型，共 6 类。                   | 用于按问题类型统计 QA 表现。                                                                                                    |

## 6.1 EvidenceItem

```python
EvidenceItem = {
    "memory_content": str,
    "memory_type": str
}
```

| Field            | 含义                    | 测评中的作用                         |
| ---------------- | --------------------- | ------------------------------ |
| `memory_content` | 支撑答案的 gold memory 文本。 | QA judge 的关键依据。                |
| `memory_type`    | evidence memory 的类型。  | 可用于分析不同 memory type 在 QA 中的贡献。 |

对于 `Memory Boundary` 类型问题，`evidence` 应为空列表，因为这类问题询问的是数据中未提供的信息。官方 question generation 代码明确要求 Memory Boundary 的 evidence list 为 `[]`。

---

# 7. Evaluation Tasks and Dataset Fields

HaluMem 的主评测任务包括三类：

```text
1. Memory Extraction
2. Memory Updating
3. Memory Question Answering
```

README 中也将 HaluMem 的核心操作拆为 Memory Extraction、Memory Update、Memory Question Answering。

---

## 7.1 Memory Extraction

### 任务含义

Memory Extraction 衡量系统在读取一个 session dialogue 后，是否能准确抽取应该保存的 memories，同时避免生成不受支持或干扰性的 memories。

### 相关字段

```text
session.dialogue
session.memory_points
memory_point.memory_content
memory_point.memory_source
memory_point.importance
memory_point.memory_type
```

### 评测中产生的字段

```text
session.extracted_memories
```

官方 Mem0 wrapper 在 `client.add(...)` 后，从返回结果中取出 `item["memory"]`，保存为 `extracted_memories`。

### 主要子指标

#### 7.1.1 Memory Integrity / Recall

含义：gold memory point 是否被系统抽取出来。

输入关系：

```text
Gold memory:
    memory_point.memory_content

System memories:
    session.extracted_memories
```

官方 judge 会给每个 gold memory point 打分：

```text
2 = 完整覆盖或可推断覆盖
1 = 部分覆盖
0 = 未覆盖或错误
```



`importance` 会参与 weighted recall 计算。

#### 7.1.2 Memory Accuracy / Precision

含义：系统抽取出来的 memory 是否被 dialogue 或 gold memories 支持。

输入关系：

```text
Candidate memory:
    one item from session.extracted_memories

Reference source:
    session.dialogue
    session.memory_points excluding interference memories
```

官方 judge 会给每条 extracted memory 打分：

```text
2 = 所有信息点都被支持
1 = 部分正确，但包含未支持或矛盾内容
0 = 完全不支持或与来源矛盾
```



#### 7.1.3 False Memory Resistance / FMR

含义：系统是否能避免把干扰信息当作真实 memory。

相关字段：

```text
memory_point.memory_source == "interference"
```

官方 aggregation 中，interference memory 的期望效果是没有被系统作为有效 memory 覆盖；也就是对 interference memory，`memory_integrity_score == 0` 反而计为抵抗成功。

---

## 7.2 Memory Updating

### 任务含义

Memory Updating 衡量系统面对新信息时，是否能正确更新、覆盖或修正已有记忆。

### 相关字段

```text
memory_point.is_update
memory_point.memory_content
memory_point.original_memories
memory_point.timestamp
memory_point.memory_type
```

### 触发条件

官方代码中，只有满足以下条件的 memory point 会进入 update evaluation：

```text
memory_point["is_update"] == "True"
and memory_point["original_memories"] is not empty
```



### 评测中产生的字段

```text
memory_point.memories_from_system
```

官方 wrapper 会用 `memory_point.memory_content` 作为 query 检索系统中的相关 memories，并把返回结果保存为 `memories_from_system`。

### Judge 输入

```text
Generated Memories:
    memory_point.memories_from_system

Target Memory for Update:
    memory_point.memory_content

Original Memory Content:
    memory_point.original_memories
```

官方 update judge 输出：

```text
Correct
Hallucination
Omission
Other
```



### 输出类别含义

| 类别              | 含义                                        |
| --------------- | ----------------------------------------- |
| `Correct`       | 系统记忆包含正确的新 memory，并体现了对旧 memory 的替换或过时处理。 |
| `Hallucination` | 系统产生了相关更新，但内容包含事实错误或与目标更新矛盾。              |
| `Omission`      | 系统没有记录目标更新，或只记录了不完整更新。                    |
| `Other`         | 不属于上述三类的其他失败情况。                           |

---

## 7.3 Memory Question Answering

### 任务含义

Memory QA 衡量系统能否基于已有 memory 检索与生成正确答案，并避免 hallucination 或 omission。

### 相关字段

```text
question.question
question.answer
question.evidence
question.difficulty
question.question_type
```

### 评测中产生的字段

```text
question.context
question.system_response
question.result_type
question.search_duration_ms
question.response_duration_ms
```

官方 wrapper 的流程是：

```text
qa["question"]
    -> retrieve memories
    -> format context
    -> LLM answer generation
    -> system_response
```

相关代码中，`search_memory` 使用 `qa["question"]` 检索 memory，之后用 prompt 生成 `system_response`。

### Judge 输入

```text
Question:
    question.question

Reference Answer:
    question.answer

Key Memory Points:
    question.evidence[*].memory_content

Memory System Response:
    question.system_response
```

官方 QA judge 输出：

```text
Correct
Hallucination
Omission
```



### 输出类别含义

| 类别              | 含义                                                                   |
| --------------- | -------------------------------------------------------------------- |
| `Correct`       | response 与 reference answer 语义等价，且不与 evidence 矛盾。                    |
| `Hallucination` | response 包含与 reference answer 或 evidence 冲突的信息，或在 unknown 情况下编造具体事实。 |
| `Omission`      | response 缺失必要信息，或在 evidence 存在时回答不知道。                                |

---

# 8. QA Question Types

`question_type` 是 QA 样本的类型标签。HaluMem 最终 QA judge 仍然统一输出 `Correct / Hallucination / Omission`，但结果可以按 `question_type` 分组统计。

官方 question generation 代码中定义了 6 类问题。

---

## 8.1 Basic Fact Recall

| 项目          | 内容                                                         |
| ----------- | ---------------------------------------------------------- |
| 含义          | 直接询问 dialogue / memory 中显式出现的单个事实或偏好。                      |
| 典型 evidence | 通常是一条 memory point。                                        |
| 主要测试        | 基础事实召回能力。                                                  |
| 字段依赖        | `question.question`、`question.answer`、`question.evidence`。 |

官方定义强调：这类问题不需要 reasoning 或多个信息点整合。

---

## 8.2 Dynamic Update

| 项目          | 内容                                                                                                      |
| ----------- | ------------------------------------------------------------------------------------------------------- |
| 含义          | 测试系统是否能识别同一信息在不同时间点的变化，并返回最新状态。                                                                         |
| 典型 evidence | 更新后的 memory point。                                                                                      |
| 主要测试        | 新旧记忆覆盖、最新状态判断、时间一致性。                                                                                    |
| 字段依赖        | `memory_point.is_update`、`memory_point.original_memories`、`memory_point.timestamp`、`question.evidence`。 |

官方定义要求这类问题涉及同一信息在不同时间点的变化，并通常询问 current/latest status。

---

## 8.3 Multi-hop Inference

| 项目          | 内容                                        |
| ----------- | ----------------------------------------- |
| 含义          | 需要整合多个 memory fragments，通过逻辑、时间或关系推理得到答案。 |
| 典型 evidence | 至少 2 条相关 memory points。                   |
| 主要测试        | 多条 memory 检索覆盖与组合推理。                      |
| 字段依赖        | `question.evidence` 中的多个 memory points。   |

官方定义要求至少涉及 2–3 个不同 memory points，答案不能直接来自单个 memory point。

---

## 8.4 Generalization & Application

| 项目          | 内容                                    |
| ----------- | ------------------------------------- |
| 含义          | 基于已知用户偏好、特征或历史行为，在新场景下做合理判断或应用。       |
| 典型 evidence | Persona / Event 类型 memory points。     |
| 主要测试        | 个性化泛化能力，以及是否避免过度推断。                   |
| 字段依赖        | `question.evidence`、相关 `memory_type`。 |

官方定义强调：不是直接询问已知信息，而是将已知用户属性应用到新场景中，同时避免 over-generalization。

---

## 8.5 Memory Conflict

| 项目          | 内容                                                     |
| ----------- | ------------------------------------------------------ |
| 含义          | 问题中故意包含与已知 memory 冲突的错误前提。                             |
| 典型 evidence | 能直接反驳错误前提的 memory point。                               |
| 主要测试        | 是否能识别并纠正错误前提，而不是顺着问题幻觉。                                |
| 字段依赖        | `question.question` 中的错误前提、`question.evidence` 中的反驳证据。 |

官方定义要求 answer 先纠正错误前提，再基于正确信息回答。

---

## 8.6 Memory Boundary

| 项目          | 内容                                                                       |
| ----------- | ------------------------------------------------------------------------ |
| 含义          | 询问 memory 中没有提供的信息。                                                      |
| 典型 evidence | 空列表 `[]`。                                                                |
| 主要测试        | 系统是否知道边界，能否在信息缺失时拒绝编造。                                                   |
| 字段依赖        | `question.evidence == []`、`question.answer` 通常表示 unknown / not provided。 |

官方定义要求这类问题询问无法在任何 memory point 中找到的信息，且 evidence list 必须为空。

---

# 9. Evaluation-related Output Records

官方 `evaluation.py` 会聚合以下记录类型：

```python
eval_results = {
    "memory_integrity_records": [],
    "memory_accuracy_records": [],
    "memory_update_records": [],
    "question_answering_records": []
}
```



| Record                       | 来源                                                     | 作用                                                    |
| ---------------------------- | ------------------------------------------------------ | ----------------------------------------------------- |
| `memory_integrity_records`   | gold memory points vs extracted memories               | 统计 recall / weighted recall。                          |
| `memory_accuracy_records`    | extracted memories vs dialogue/gold memories           | 统计 memory accuracy / precision。                       |
| `memory_update_records`      | update-type memory points vs retrieved system memories | 统计 update correct / hallucination / omission / other。 |
| `question_answering_records` | QA pairs vs system responses                           | 统计 QA correct / hallucination / omission。             |

最终整体结果包括：

```text
memory_integrity
memory_accuracy
memory_extraction_f1
memory_update
question_answering
memory_type_accuracy
time_consuming
```

官方 aggregation 代码中包含这些 overall score 字段。

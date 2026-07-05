下面这版是**只描述 BEAM 数据结构、字段含义、字段在 benchmark 测评中的作用**，不指挥 Codex 怎么写代码。

# BEAM Dataset Structure and Evaluation Semantics

BEAM 的基本单位是 `conversation`。一个 conversation 是一段完整的多轮长期对话（100K-10M tokens），附带 20 道覆盖 10 种记忆能力的 probing questions。

整体结构：

```text
HF dataset (Mohammadta/BEAM)
└── conversation
    ├── conversation_id
    ├── conversation_seed
    ├── narratives
    ├── user_profile
    ├── conversation_plan
    ├── user_questions
    ├── chat
    └── probing_questions
```

---

## 1. Dataset Splits

BEAM 通过两个 HF 仓库发布：

### `Mohammadta/BEAM`

包含 100K、500K、1M 三个规模的 90 个 conversations：

| Split | 对话数 | 说明 |
|-------|--------|------|
| `100K` | 20 | 每个 conversation ~128K tokens |
| `500K` | 35 | 每个 conversation ~500K tokens |
| `1M` | 35 | 每个 conversation ~1M tokens |

### `Mohammadta/BEAM-10M`

独立仓库。包含 1 个 split `10M`，10 个 conversations，每个 ~10M tokens。数据结构与主仓库有差异（见第 7 节）。

---

## 2. Conversation-level Fields

一个 conversation 是 BEAM 的核心样本单位。可以理解为：

```text
一段完整的多轮 user-assistant 对话
+ 对话主题和人物设定
+ 20 道 probing questions（覆盖 10 种记忆能力）
```

### `conversation_id`

类型：`str`

含义：当前 conversation 的唯一标识符，如 `"1"`。

作用：

```text
1. 标识并区分不同 conversation。
2. 用于结果保存目录命名（如 results/1M/1/）。
```

### `conversation_seed`

类型：`struct`（dict）

含义：对话的主题种子信息。

对于 100K/500K/1M：

```python
conversation_seed = {
    "category":  str,       # 如 "Coding", "General", "Math"
    "id":        int,
    "subtopics": list[str], # 如 ["Using transformer-based LLM APIs", "Building a memory store for context"]
    "theme":     str,       # 如 "Creating a chatbot that remembers past conversations and switches languages dynamically"
    "title":     str,       # 如 "Building a Multi-Language AI Chatbot with Contextual Memory"
}
```

对于 10M，多了 `mode` 和 `timeline` 字段：

```python
conversation_seed = {
    "category":  str,
    "id":        int,
    "mode":      str,       # 如 "coding"
    "subtopics": list[str],
    "theme":     str,
    "timeline":  str,       # 如 "6 month"
    "title":     str,
}
```

作用：

```text
1. 提供对话域（coding / general / math），支持域层面分析。
2. 提供主题信息，非测评必需字段。
```

### `narratives`

类型：`str`

含义：对话叙事标签分类文本，描述对话覆盖的标签类别。

示例内容：

```text
1. LABEL CATEOGRY: Technical Problem-Solving Labels
   LABEL DESCRIPTION: Focus Areas: Debugging Techniques, Troubleshooting Strategies...

2. LABEL CATEOGRY: Learning & Knowledge Labels
   LABEL DESCRIPTION: Focus Areas: Programming Language Fundamentals...
...
```

作用：

```text
1. 数据集生成阶段指导对话内容方向。
2. 评测阶段不读取。
```

### `user_profile`

类型：`struct`

含义：对话中用户的 persona 设定。

```python
user_profile = {
    "user_info":           str,  # 用户基本信息（姓名、年龄、性别、地点、职业、性格描述）
    "user_relationships":  str,  # 用户人际关系描述
}
```

`user_info` 示例：

```text
USER PROFILE:
    • Name: Jamie Perez
    • Age: 25 years old
    • Gender: Female
    • Location: North Ericshire, Turkey
    • Profession: Psychologist, Clinical

PERSONALITY OVERVIEW:
    She approaches her work with a sense of duty and responsibility...
```

作用：

```text
1. 数据集生成阶段用于确保对话一致性。
2. 评测阶段不读取（persona 信息已体现在 chat 内容中）。
```

### `conversation_plan`

类型：`str`

含义：对话生成计划。按 BATCH 组织，每个 BATCH 包含多条 bullet，每条 bullet 关联一个 label 和一个对话要点。

示例：

```text
BATCH 1 PLAN
• **Time Anchor:** March 1, 2024
• **Personal Introduction:** I'm Jamie, a psychologist venturing into AI chatbot development...
• **Architecture & Design Labels:System Architecture:** Planning a microservices architecture...
...
```

作用：

```text
1. 数据集生成阶段的核心输入。
2. 评测阶段不读取。
```

### `user_questions`

类型：`list[dict]`（100K/500K/1M）或 `list[0]`（10M）

含义：对话生成阶段中用户向 AI 提出的原始问题（不是 probing questions）。

100K/500K/1M 中的结构：

```python
user_questions = [
    {
        "time_anchor": str,        # 如 "March-01-2024"
        "messages": [[str, ...]],  # 嵌套消息列表
    },
    ...
]
```

对于 10M，该字段为空（`[]`）。

作用：

```text
1. 数据集生成阶段的中间产物。
2. 评测阶段不读取。
```

---

## 3. `chat` — 核心对话数据

`chat` 是 BEAM 最重要的字段。它包含完整的 user-assistant 多轮对话。

### 3.1 100K/500K/1M 中的 `chat`

类型：`list[list[dict]]`

两层结构：
- **外层 list**：对应 batch（一种时间分组，100K 有 3 个 batch，500K/1M 各有 10 个 batch）
- **内层 list**：该 batch 内的消息序列，每条消息是一个 dict

```python
chat = [
    batch_0,  # list[dict]
    batch_1,
    ...
]
```

每条消息的字段：

| 字段 | 类型 | 含义 | 测评作用 |
|------|------|------|----------|
| `role` | `str` | `"user"` 或 `"assistant"` | 区分发言者身份 |
| `content` | `str` | 消息正文 | 评测的核心输入，所有 probing question 的答案依据 |
| `id` | `int` | 全局递增消息 ID | 唯一标识每条消息；`source_chat_ids` 引用这些 ID |
| `question_type` | `str` 或 `None` | user 消息的类型 | 标识消息在对话中的角色 |
| `time_anchor` | `str` | 时间锚点，如 `"March-01-2024"` | temporal_reasoning 问题可能依赖 |
| `index` | `str` | 如 `"1,1"` | 表示该问题属于第几个 batch、第几个话题（非必需） |

`question_type` 的取值：

| 值 | 含义 |
|----|------|
| `"main_question"` | user 发起的主动提问 |
| `"followup_question"` | user 的追问 |
| `"answer_ai_question"` | user 回答 AI 的提问 |
| `None` | assistant 消息（没有 question_type） |

消息类型分布示例（1M conversation #1）：

```text
assistant 消息:    855 条
user/main_question: 625 条
user/followup_question: 200 条
user/answer_ai_question: 30 条
```

### 3.2 与本地 `chat.json` 的结构差异

HF 数据集中的 `chat` 是扁平的两层结构（`batch → messages`），消息之间没有 turn 分组。

本地 GitHub 仓库中的 `chat.json`（经 `download_dataset.py` 转换后）多了一层 `turns` 嵌套：

```python
# 本地 chat.json 结构
[
    {"batch_number": 1, "turns": [
        [{"role": "user", ...}, {"role": "assistant", ...}],  # turn 1
        [{"role": "user", ...}, {"role": "assistant", ...}],  # turn 2
        ...
    ]},
    ...
]
```

其中每条消息增加了一个 `"index"` 字段之外的相同结构。`turns` 是将相邻消息按 user-assistant 成对分组后的结果。HF 数据集不含此分组。

### 3.3 10M 中的 `chat`

类型：`list[dict]`（10 个元素）

10M 的 `chat` 不是 `list[list[dict]]`，而是 `list[dict]`，每个 dict 以 `"plan-N"` 为键：

```python
chat = [
    {"plan-1": list[list[dict]]},  # batch → message 结构，同普通规模
    {"plan-2": list[list[dict]]},
    ...
    {"plan-10": list[list[dict]]},
]
```

10M 对话是通过 10 个独立 plan 生成后拼接而成的，每个 plan 代表一个时间阶段。在 answer generation 代码中，遍历时会多一层 `for plan in chat: for batch in plan`。

---

## 4. `probing_questions` — 评测问题

`probing_questions` 是 BEAM 评测的核心标注字段。

类型：`str`（需要 `ast.literal_eval()` 解析为 dict）

解析后结构：

```python
probing_questions = {
    "abstention":               list[ProbingQuestion],  # 各 2 题
    "contradiction_resolution": list[ProbingQuestion],
    "event_ordering":           list[ProbingQuestion],
    "information_extraction":   list[ProbingQuestion],
    "instruction_following":    list[ProbingQuestion],
    "knowledge_update":         list[ProbingQuestion],
    "multi_session_reasoning":  list[ProbingQuestion],
    "preference_following":     list[ProbingQuestion],
    "summarization":            list[ProbingQuestion],
    "temporal_reasoning":       list[ProbingQuestion],
}
```

每个 conversation 有 **20 道 probing question**（10 种类型 × 2 题），全部基于这段 conversation 的内容。这些问题是评测流程的输入。

### 4.1 ProbingQuestion 通用字段

不同 question type 的字段不完全相同，下面是各类问题的共有与特有字段。

除 abstention 外，大多数类型包含：

| 字段 | 类型 | 含义 | 测评作用 |
|------|------|------|----------|
| `question` | `str` | 问题文本 | answer generation 的输入 query |
| `difficulty` | `str` | `"easy"` / `"medium"` / `"hard"` | 难度分级，可用于分类评估 |
| `source_chat_ids` | `list[int]` | 答案依据的消息 ID | 对应 `chat` 中的 `id` 字段；可用于验证 retrieval 是否命中证据 |
| `rubric` | `list[str]` | LLM Judge 评分标准 | **评测阶段的核心输入**：每条 rubric 是一个评判维度 |

### 4.2 各类型特有字段

#### `abstention`（拒答）

测试模型在缺少证据时是否能识别并拒答。**没有 `answer` 字段**。

```python
AbstentionQuestion = {
    "question":          str,
    "ideal_response":    str,        # 理想回答（如 "Based on the provided chat, there is no information..."）
    "difficulty":        str,
    "abstention_type":   str,        # 如 "missing_detail"
    "why_unanswerable":  str,        # 解释为什么不可回答
    "plan_reference":    str,        # 如 "Batch 1, Bullet 2"
    "rubric":            list[str],
}
```

测评关注：模型应输出"无法回答"，而非编造。

#### `contradiction_resolution`（矛盾消解）

测试模型是否能检测并调和对话中分散在不同位置的矛盾陈述。

```python
ContradictionQuestion = {
    "question":                str,
    "ideal_answer":            str,         # 期望的回答（指出矛盾并请求澄清）
    "difficulty":              str,
    "contradiction_type":      str,         # 如 "never_statement_violation"
    "topic_questioned":        str,         # 矛盾的议题
    "conversation_references": list[str],   # 引用哪些对话部分
    "tests_for":               str,         # 考察目标描述
    "source_chat_ids":         dict,        # {"first_statement": [...], "second_statement": [...]}
    "rubric":                  list[str],
}
```

测评关注：模型是否识别矛盾并要求澄清，而非给出单一确定答案。

#### `event_ordering`（事件排序）

测试模型是否能识别并重建对话中信息的演进顺序。

```python
EventOrderingQuestion = {
    "question":                str,
    "answer":                  str,         # 正确的事件顺序
    "difficulty":              str,
    "ordering_type":           str,
    "total_mentions":          int,
    "conversation_references": list[str],
    "ordering_tested":         str,
    "complexity_factors":      list[str],
    "source_chat_ids":         list[int],
    "rubric":                  list[str],   # 用于评分 + 用于 Kendall's tau 排序比较
}
```

测评关注：除 LLM Judge 评分外，额外计算 Kendall's tau 系数比较预测顺序和 rubric 中的 gold 顺序。

#### `information_extraction`（信息抽取）

测试模型从长历史中回忆实体和事实细节的能力。

```python
InformationExtractionQuestion = {
    "question":                str,
    "answer":                  str,         # gold answer
    "difficulty":              str,
    "question_type":           str,         # 如 "short_answer"
    "conversation_reference":  str,
    "key_facts_tested":        list[str],   # 考察的关键事实
    "source_chat_ids":         list[int],
    "rubric":                  list[str],
}
```

测评关注：模型输出是否包含正确的事实信息。

#### `instruction_following`（指令遵循）

测试模型在长上下文中是否能持续遵循用户指定的约束。

```python
InstructionFollowingQuestion = {
    "question":                str,
    "instruction_being_tested":  str,
    "expected_compliance":     str,
    "compliance_indicators":   list[str],
    "non_compliance_signs":    list[str],
    "difficulty":              str,
    "instruction_type":        str,
    "source_chat_ids":         list[int],
    "rubric":                  list[str],
}
```

测评关注：输出是否严格遵循对话早期设定的指令/约束。

#### `knowledge_update`（知识更新）

测试模型在收到新信息后是否能修订已存储的事实。

```python
KnowledgeUpdateQuestion = {
    "question":                str,
    "answer":                  str,         # gold answer（更新后的值）
    "difficulty":              str,
    "update_type":             str,
    "tests_retention_of":      str,
    "conversation_references": list[str],
    "potential_confusion":     str,
    "source_chat_ids":         list[int],
    "rubric":                  list[str],
}
```

测评关注：模型应使用最新信息而非旧信息。

#### `multi_session_reasoning`（多段推理）

测试跨越多个非相邻对话片段进行推理的能力。

```python
MultiSessionReasoningQuestion = {
    "question":                str,
    "answer":                  str,
    "difficulty":              str,
    "reasoning_type":          str,
    "sessions_required":       int,
    "conversation_references": list[str],
    "reasoning_steps":         list[str],
    "source_chat_ids":         list[int],
    "rubric":                  list[str],
}
```

测评关注：模型是否能整合分布在多个对话片段中的证据进行推理。

#### `preference_following`（偏好遵循）

测试模型是否能生成适应用户偏好变化的个性化回答。

```python
PreferenceFollowingQuestion = {
    "question":                 str,
    "preference_being_tested":  str,
    "expected_compliance":      str,
    "compliance_indicators":    list[str],
    "non_compliance_signs":     list[str],
    "difficulty":               str,
    "preference_type":          str,
    "source_chat_ids":          list[int],
    "rubric":                   list[str],
}
```

测评关注：回答是否反映了用户的偏好。

#### `summarization`（摘要）

测试对对话内容的抽象和压缩能力。

```python
SummarizationQuestion = {
    "question":               str,
    "ideal_summary":           str,         # 理想摘要
    "difficulty":              str,
    "summarization_type":      str,
    "bullet_points_covered":   int,
    "conversation_sessions":   list[str],
    "key_elements_tested":     list[str],
    "synthesis_required":      bool,
    "source_chat_ids":         list[int],
    "rubric":                  list[str],
}
```

测评关注：摘要的完整性、准确性和简洁性。

#### `temporal_reasoning`（时间推理）

测试对显式和隐式时间关系的推理能力。

```python
TemporalReasoningQuestion = {
    "question":                str,
    "answer":                  str,         # gold 时间答案
    "difficulty":              str,
    "temporal_type":           str,
    "time_points":             list[str],
    "conversation_references": list[str],
    "calculation_required":    bool,
    "source_chat_ids":         list[int],
    "rubric":                  list[str],
}
```

测评关注：时间间隔计算、事件先后判断、截至某时间点的状态。

### 4.3 `rubric` — LLM Judge 评分标准

`rubric` 是 **evaluation 阶段的核心输入**（而非 answer generation 阶段）。它是一系列自然语言评判标准，每条对应一个评分维度。

`information_extraction` 的 rubric 示例：

```json
[
    "LLM response should state the amount: 83% accuracy",
    "LLM response should mention the number of languages: 12",
    "LLM response should state: the initial accuracy was 76%",
    "LLM response should mention: the response speed improved from 250ms to 180ms",
    "LLM response should mention: the system used Node.js 18 for the backend"
]
```

评分流程：对每条 rubric_item，LLM Judge（gpt-4.1-mini）判断模型回答是否满足该标准，输出 0.0 / 0.5 / 1.0，最终分数为所有 rubric item 得分的均值。

### 4.4 `source_chat_ids`

`source_chat_ids` 标注了每个 probing question 的答案所依赖的原始 chat 消息 ID。这些 ID 直接对应 `chat` 中每条消息的 `id` 字段。

作用：

```text
1. 标注 evidence messages，连接 probing question 和原始 chat。
2. 可用于 retrieval evaluation——判断检索结果是否命中 gold evidence。
3. BEAM 官方当前不单独做 retrieval recall 评测，但标注为未来扩展提供了基础。
```

---

## 5. BEAM-10M 的特殊字段

`Mohammadta/BEAM-10M` 多了一个 `plans` 字段。

### `plans`

类型：`list[dict]`（10 个元素）

含义：10M 每个 conversation 的 10 个独立 plan 的详细信息。每个 plan 对象包含：

```python
plan = {
    "plan_id":           str,                    # 如 "plan-0"
    "chat":              list[list[dict]],       # 该 plan 的对话
    "conversation_seed": dict,                   # 该 plan 的主题种子
    "conversation_plan": str,                    # 该 plan 的生成计划
    "narratives":        str,                    # 该 plan 的标签
    "user_profile":      {"user_relationships": str},  # 该 plan 的人物关系
    "user_questions":    list[dict],             # 该 plan 的用户问题
}
```

作用：

```text
1. 数据集生成阶段的中间产物。
2. 评测阶段不读取——顶层的 chat 字段已合并所有 plan 的对话。
```

---

## 6. 字段和测评任务的总映射

| 字段 | QA Answer Generation | QA Evaluation |
|------|:-------------------:|:-------------:|
| `conversation_id` | 定位样本 | — |
| `conversation_seed` | — | — |
| `narratives` | — | — |
| `user_profile` | — | — |
| `conversation_plan` | — | — |
| `user_questions` | — | — |
| `chat` | **核心输入**：全部对话内容，作为回答问题的主要上下文 | —（不读取） |
| `probing_questions.question` | **核心输入**：要回答的问题 | 用于 judge 理解 context |
| `probing_questions.answer` / `ideal_answer` 等 | —（不读取） | 作为 gold reference（部分类型有） |
| `probing_questions.rubric` | — | **核心输入**：LLM Judge 每条 rubric item 打分 |
| `probing_questions.source_chat_ids` | — | 可用于 retrieval evidence 验证 |
| `probing_questions.difficulty` | — | 可用于分类统计 |
| `plans`（仅 10M） | — | — |

---

## 7. 最简结构图

```text
Mohammadta/BEAM
├── split: "100K" (20 conversations)
├── split: "500K" (35 conversations)
└── split: "1M"   (35 conversations)

Mohammadta/BEAM-10M
└── split: "10M"   (10 conversations)

Conversation
├── conversation_id        : str
├── conversation_seed      : {category, id, subtopics, theme, title}
├── narratives             : str
├── user_profile           : {user_info, user_relationships}
├── conversation_plan      : str
├── user_questions         : list[dict]   (10M 中为 [])
├── chat                   : list[list[dict]]   ← 核心：全部对话消息
│   └── batch
│       └── message
│           ├── role           : "user" | "assistant"
│           ├── content        : str
│           ├── id             : int
│           ├── question_type  : "main_question" | "followup_question" | "answer_ai_question" | None
│           ├── time_anchor    : str
│           └── index          : str
├── probing_questions     : str → dict   ← 核心：20 道评测题
│   ├── abstention               : list[{question, ideal_response, rubric, ...}]
│   ├── contradiction_resolution : list[{question, ideal_answer, rubric, ...}]
│   ├── event_ordering           : list[{question, answer, rubric, ...}]
│   ├── information_extraction   : list[{question, answer, rubric, ...}]
│   ├── instruction_following    : list[{question, ...（无 answer）, rubric, ...}]
│   ├── knowledge_update         : list[{question, answer, rubric, ...}]
│   ├── multi_session_reasoning  : list[{question, answer, rubric, ...}]
│   ├── preference_following     : list[{question, ...（无 answer）, rubric, ...}]
│   ├── summarization            : list[{question, ideal_summary, rubric, ...}]
│   └── temporal_reasoning       : list[{question, answer, rubric, ...}]
└── plans (仅 10M)        : list[dict]   ← 生成中间产物
```

---

## 8. 核心语义总结

```text
Conversation:
    一段完整的长期 user-assistant 对话，是 BEAM 的顶层样本单位。
    每个 conversation 有 20 道 probing questions。

chat:
    完整对话内容，是 answer generation 的核心输入。
    100K/500K/1M 为 list[list[dict]]（batch → message），
    10M 为 list[dict]（plan → batch → message）。

message:
    一条 user 或 assistant 消息，包含 role、content、id、time_anchor 等字段。

probing_questions:
    解析后为 dict[str, list[dict]]，按 10 种记忆能力分类。
    是 answer generation 的 query 来源 + evaluation 的 rubric 来源。

rubric:
    probing question 内的评分标准列表。
    evaluation 阶段 LLM Judge 对每条 rubric item 逐项打分。

source_chat_ids:
    连接 probing question 和原始 chat 中 evidence messages 的桥梁。
    标注答案依据的消息 ID。

10M 特殊性:
    chat 最外层是 10 个 plan 的 dict 而非 batch 列表。
    多了 plans 字段（生成细节），评测不读取。
```

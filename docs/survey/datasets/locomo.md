下面是重新整理后的版本。这个版本只描述 **LoCoMo dataset 的数据结构、字段含义、字段在 benchmark 测评中的作用**，不指挥 Codex 怎么写代码。

---

# LoCoMo Dataset Structure and Benchmark Field Semantics

LoCoMo 的 canonical 数据文件是 `data/locomo/locomo10.json`。该 release 包含 10 个 conversations。每个 top-level sample 表示一段完整的长期对话，以及这段对话对应的任务标注。LoCoMo 主要涉及三类任务：question answering、event summarization、multimodal dialog generation。README 中也说明，QA 和 event summarization 有 annotation，dialog 本身还可以用于 multimodal-dialog-generation。

---

## 1. Top-level Structure

整体结构可以理解为：

```python
locomo10: list[Sample]
```

每个 `Sample` 大致包含：

```python
Sample = {
    "sample_id": str,
    "conversation": Conversation,
    "observation": Observation,
    "session_summary": SessionSummary,
    "event_summary": EventSummary,
    "qa": list[QAItem],
}
```

字段含义：

| Field             | 类型            | 含义                                             | 测评中的作用                                                              |
| ----------------- | ------------- | ---------------------------------------------- | ------------------------------------------------------------------- |
| `sample_id`       | `str`         | 当前 sample 的唯一标识                                | 区分不同长期 conversation；记录实验结果时用于定位样本                                   |
| `conversation`    | `dict`        | 原始长期对话数据                                       | QA、RAG QA、event summarization、multimodal dialog generation 的主要上下文来源 |
| `observation`     | `dict`        | 基于 conversation 生成的 session-level observations | 可作为 RAG QA 的一种检索数据库                                                 |
| `session_summary` | `dict`        | 基于 conversation 生成的 session-level summaries    | 可作为 RAG QA 的一种检索数据库                                                 |
| `event_summary`   | `dict / list` | 人工标注的显著事件摘要                                    | event summarization 任务的 ground truth                                |
| `qa`              | `list[dict]`  | 人工标注的问答数据                                      | question answering 任务的测试问题和答案                                       |

注意：**一个 sample 不是一个 QA item，而是一整段长期 conversation。**

---

## 2. `conversation`

`conversation` 是 LoCoMo 最核心的数据字段。它表示两个 speaker 之间跨多个 session 的长期对话。

结构大致如下：

```python
Conversation = {
    "speaker_a": str,
    "speaker_b": str,

    "session_1_date_time": str,
    "session_1": list[Turn],

    "session_2_date_time": str,
    "session_2": list[Turn],

    ...
}
```

字段含义：

| Field                     | 类型           | 含义                            | 测评中的作用                    |
| ------------------------- | ------------ | ----------------------------- | ------------------------- |
| `speaker_a`               | `str`        | conversation 中第一个 speaker 的名字 | 标识长期对话中的参与者               |
| `speaker_b`               | `str`        | conversation 中第二个 speaker 的名字 | 标识长期对话中的参与者               |
| `session_<num>`           | `list[Turn]` | 第 `<num>` 个 session 的对话内容     | 原始对话上下文；`<num>` 表示时间顺序    |
| `session_<num>_date_time` | `str`        | 第 `<num>` 个 session 的时间戳      | 支持 temporal QA；帮助判断事件发生时间 |

`session_<num>` 中的 `<num>` 表示 session 的时间顺序。例如：

```python
session_1
session_2
session_3
```

表示同一段长期 conversation 中按时间排列的多次会话。

---

## 3. `session`

一个 session 是一次具体的对话片段。

```python
Session = list[Turn]
```

语义上：

```text
sample = 一整段长期 conversation
session = 长期 conversation 中某一次有时间戳的聊天片段
turn = session 中某个 speaker 的单条发言
```

session 本身不是 QA 标注单位。LoCoMo 的 QA 标注挂在整个 sample / conversation 下，而不是挂在每个 session 下。

---

## 4. `turn`

普通文本 turn 的结构：

```python
Turn = {
    "speaker": str,
    "dia_id": str,
    "text": str,
}
```

带图片的 multimodal turn 可能是：

```python
Turn = {
    "speaker": str,
    "dia_id": str,
    "text": str,
    "img_url": list[str],
    "blip_caption": str,
    "query": str,
}
```

字段含义：

| Field          | 类型          | 含义                                  | 测评中的作用                                                |
| -------------- | ----------- | ----------------------------------- | ----------------------------------------------------- |
| `speaker`      | `str`       | 当前 turn 是谁说的                        | 保留说话人信息；QA 和记忆检索可能依赖 speaker                          |
| `dia_id`       | `str`       | 当前 dialogue turn 的唯一 id，例如 `D19:15` | QA evidence 会引用这些 id；RAG 检索结果也可用它和 evidence 对齐        |
| `text`         | `str`       | 当前 speaker 的发言文本                    | 原始对话内容，是 QA 和 memory 的主要信息来源                          |
| `img_url`      | `list[str]` | 当前 turn 关联的图片 URL                   | multimodal dialog generation 或 multimodal memory 可能使用 |
| `blip_caption` | `str`       | BLIP 模型生成的图片描述                      | 文本模型可通过 caption 获得图片语义                                |
| `query`        | `str`       | 通过 icrawler 搜图时使用的 search query     | 辅助说明图片主题或检索意图                                         |

例如：

```json
{
  "speaker": "Caroline",
  "img_url": [
    "https://trendgallery.art/cdn/shop/products/IMG_4482.jpg"
  ],
  "blip_caption": "a photo of a painting with the words happiness painted on it",
  "query": "painting vibrant colors happiness self-expression",
  "dia_id": "D19:15",
  "text": "Yeah, that's true! It's so freeing to just be yourself and live honestly. We can really accept who we are and be content."
}
```

这个 turn 的含义是：

```text
Caroline 在 D19:15 这条 turn 中说了一句话；
这条 turn 同时关联了一张图片；
图片本身没有作为本地文件发布；
dataset 中保留了图片 URL、BLIP caption、图片检索 query。
```

README 明确说明，LoCoMo 不发布图片文件本身，只发布图片 URL、caption 和 query。

---

## 5. `qa`

`qa` 是 question answering 任务的标注字段。

结构：

```python
qa: list[QAItem]
```

每个 QA item 大致为：

```python
QAItem = {
    "question": str,
    "answer": str | int | list,
    "evidence": list[str],
    "category": int,
}
```

示例：

```json
{
  "question": "When did Melanie paint a sunrise?",
  "answer": 2022,
  "evidence": ["D1:12"],
  "category": 2
}
```

字段含义：

| Field      | 类型                 | 含义                             | 测评中的作用                           |
| ---------- | ------------------ | ------------------------------ | -------------------------------- |
| `question` | `str`              | 关于当前 sample / conversation 的问题 | QA 任务的输入问题                       |
| `answer`   | `str / int / list` | 标准答案                           | QA 任务的 gold answer，用于和模型预测答案计算指标 |
| `evidence` | `list[str]`        | 包含答案依据的 dialogue turn ids      | 可用于分析检索结果是否命中证据                  |
| `category` | `int`              | 问题类别编号                         | 用于区分不同类型的 QA 题目，并做分类评测           |

`evidence` 中的 `D1:12` 通常可以理解为：

```text
第 1 个 session 中的第 12 条 dialogue turn
```

更精确地说，`D1:12` 是一个 `dia_id`，它对应原始 conversation 中的一条 turn。

---

## 6. QA Task 与字段关系

Question Answering 是 LoCoMo 的核心任务之一。

QA task 的基本数据关系是：

```text
input:
    sample["conversation"]

question:
    sample["qa"][i]["question"]

gold:
    sample["qa"][i]["answer"]

optional evidence:
    sample["qa"][i]["evidence"]

category:
    sample["qa"][i]["category"]
```

也就是说，一个 sample 中的多个 session 共同构成长期对话上下文，`qa` 中的问题是基于整段长期 conversation 提出的。

QA 不是这样的结构：

```text
session_1 -> qa
session_2 -> qa
session_3 -> qa
```

而是更接近：

```text
sample / full conversation
    ├── session_1
    ├── session_2
    ├── session_3
    └── qa list
```

QA 的测评目标是：模型是否能基于长期 conversation 回答问题。

---

## 7. QA `category`

LoCoMo QA 设计上覆盖多类长期记忆问题，包括：

```text
single-hop
multi-hop
temporal
commonsense / world knowledge
adversarial
```

`category` 字段是这些问题类型的编号。它的作用是区分不同问题类型，方便分别统计表现。

在工程记录中，最好保留原始数字编号，因为官方评测代码对不同 category 的处理方式并不完全相同。

常见理解方式：

```python
CATEGORY_MAP = {
    1: "multi_hop",
    2: "temporal",
    3: "open_domain_or_commonsense",
    4: "single_hop",
    5: "adversarial",
}
```

字段语义上：

| Category | 含义                                               |
| -------- | ------------------------------------------------ |
| `1`      | multi-hop 类型问题，需要结合多条信息                          |
| `2`      | temporal 类型问题，通常涉及时间、日期、顺序                       |
| `3`      | open-domain / commonsense / world knowledge 相关问题 |
| `4`      | single-hop 类型问题，通常能从单条或局部对话中找到答案                 |
| `5`      | adversarial / unanswerable 类型问题，可能要求模型识别信息不存在    |

---

## 8. `observation`

`observation` 是 generated 字段，不是人工 gold annotation。

结构大致为：

```python
observation = {
    "session_1_observation": ...,
    "session_2_observation": ...,
    ...
}
```

字段含义：

| Field                       | 类型                    | 含义                           | 测评中的作用             |
| --------------------------- | --------------------- | ---------------------------- | ------------------ |
| `session_<num>_observation` | generated text / list | 从对应 session 生成的 observations | RAG QA 中可作为一种检索数据库 |

它的作用是把原始 session 对话转换成更像“观察事实”或“记忆条目”的形式。

例如原始对话可能是：

```text
Melanie: I painted a sunrise last year.
```

observation 可能表达成：

```text
Melanie painted a sunrise in 2022.
```

它不是 QA 的标准答案，而是 RAG 评测中可选的 database。

---

## 9. `session_summary`

`session_summary` 也是 generated 字段。

结构大致为：

```python
session_summary = {
    "session_1_summary": ...,
    "session_2_summary": ...,
    ...
}
```

字段含义：

| Field                   | 类型                | 含义              | 测评中的作用             |
| ----------------------- | ----------------- | --------------- | ------------------ |
| `session_<num>_summary` | generated summary | 对对应 session 的摘要 | RAG QA 中可作为一种检索数据库 |

它和 `observation` 的区别是粒度不同：

```text
observation:
    更像事实条目，可能更细。

session_summary:
    更像一次 session 的整体摘要，粒度更粗。
```

README 特别区分了 `session_summary` 和 `event_summary`：`session_summary` 只总结单个 session；`event_summary` 是 speaker-specific，并且包含 causal / temporal connections across sessions。

---

## 10. `event_summary`

`event_summary` 是 annotated 字段。

结构大致为：

```python
event_summary = {
    "events_session_1": ...,
    "events_session_2": ...,
    ...
}
```

字段含义：

| Field                  | 类型               | 含义                             | 测评中的作用                               |
| ---------------------- | ---------------- | ------------------------------ | ------------------------------------ |
| `events_session_<num>` | annotated events | 对应 session 中每个 speaker 的重要事件标注 | event summarization 任务的 ground truth |

`event_summary` 和 `session_summary` 的区别：

```text
session_summary:
    generated，单个 session 的普通摘要，可作为 RAG QA database。

event_summary:
    annotated，speaker-specific 的重要事件标注，是 event summarization 的 gold annotation。
```

在任务关系上：

```text
event summarization input:
    conversation

event summarization gold:
    event_summary
```

---

## 11. RAG QA 与字段关系

LoCoMo README 中提到，RAG-based QA 可以使用三类 database：

```text
dialogs
observations
session summaries
```

也就是：

| RAG database mode | 来源字段                                    | 粒度                        |
| ----------------- | --------------------------------------- | ------------------------- |
| dialog            | `conversation.session_<num>[turn]`      | turn-level raw dialogue   |
| observation       | `observation.session_<num>_observation` | generated observation     |
| summary           | `session_summary.session_<num>_summary` | generated session summary |

RAG QA 的数据关系可以表示为：

```text
database:
    conversation dialogs
    or observation
    or session_summary

query:
    qa[i]["question"]

gold answer:
    qa[i]["answer"]

optional retrieval gold:
    qa[i]["evidence"]
```

其中 `evidence` 是 dialogue-level ids，例如 `D1:12`。如果检索库是 raw dialog，则 retrieved item 可以直接带有 `dia_id`，从而和 evidence 对齐。

---

## 12. Event Summarization 与字段关系

Event summarization 任务的数据关系：

```text
input:
    sample["conversation"]

gold:
    sample["event_summary"]
```

任务目标是从长期 conversation 中抽取或生成重要事件摘要。

`event_summary` 的特点：

```text
annotated
speaker-specific
session-related
包含 temporal / causal connections across sessions
```

README 中目前写到 event summarization evaluation code 是 “Coming soon”，但 dataset 中已经包含对应 annotation。

---

## 13. Multimodal Dialog Generation 与字段关系

Multimodal dialog generation 使用的是 conversation 中的 dialog 数据，尤其是带图片字段的 turn。

相关字段：

```text
conversation.session_<num>[turn]["text"]
conversation.session_<num>[turn]["img_url"]
conversation.session_<num>[turn]["blip_caption"]
conversation.session_<num>[turn]["query"]
```

字段作用：

| Field          | 作用                |
| -------------- | ----------------- |
| `text`         | 对话文本上下文           |
| `img_url`      | 与当前 turn 关联的图片地址  |
| `blip_caption` | 图片的文本化语义描述        |
| `query`        | 图片检索 query，体现图片主题 |

README 里说 dialogs can be used for multimodal-dialog-generation task，但 MiniGPT-5 training / evaluation 部分目前也是 “Coming soon”。

---

## 14. 字段和任务的总映射

| 字段                        |             QA |                    RAG QA |       Event Summarization | Multimodal Dialog Generation |
| ------------------------- | -------------: | ------------------------: | ------------------------: | ---------------------------: |
| `sample_id`               |           定位样本 |                      定位样本 |                      定位样本 |                         定位样本 |
| `conversation`            |          主要上下文 |           dialog database |                     输入上下文 |                         输入对话 |
| `speaker_a` / `speaker_b` |     speaker 信息 |                speaker 信息 | speaker-specific event 相关 |                   speaker 信息 |
| `session_<num>`           |         长期对话片段 |        dialog database 来源 |                    事件抽取来源 |                       对话生成来源 |
| `session_<num>_date_time` | temporal QA 相关 |     temporal retrieval 相关 |         temporal event 相关 |                        时间上下文 |
| `turn.speaker`            |          说话人信息 |                     说话人信息 | speaker-specific event 相关 |                        说话人信息 |
| `turn.dia_id`             |    evidence 对齐 |       retrieval recall 对齐 |                    原始事件定位 |                      turn 定位 |
| `turn.text`               |           主要内容 |        raw dialog content |                      事件来源 |                        文本上下文 |
| `turn.img_url`            |          一般非必需 |         multimodal RAG 可用 |                  可能辅助事件理解 |                         图片输入 |
| `turn.blip_caption`       |         图片语义文本 |                 文本 RAG 可用 |                  可能辅助事件理解 |                         图片语义 |
| `turn.query`              |         图片主题辅助 |                    图片主题辅助 |                  可能辅助事件理解 |                         图片主题 |
| `qa.question`             |           输入问题 |           retrieval query |                         无 |                            无 |
| `qa.answer`               |    gold answer |               gold answer |                         无 |                            无 |
| `qa.evidence`             |         答案依据定位 | retrieval gold / analysis |                         无 |                            无 |
| `qa.category`             |           问题类型 |                      问题类型 |                         无 |                            无 |
| `observation`             |          非默认输入 |      observation database |                         无 |                            无 |
| `session_summary`         |          非默认输入 |          summary database |                         无 |                            无 |
| `event_summary`           |              无 |                         无 |           gold annotation |                            无 |

---

## 15. 最简结构图

```text
locomo10.json
└── Sample
    ├── sample_id
    ├── conversation
    │   ├── speaker_a
    │   ├── speaker_b
    │   ├── session_1_date_time
    │   ├── session_1
    │   │   ├── Turn
    │   │   │   ├── speaker
    │   │   │   ├── dia_id
    │   │   │   ├── text
    │   │   │   ├── img_url          optional
    │   │   │   ├── blip_caption     optional
    │   │   │   └── query            optional
    │   │   └── ...
    │   ├── session_2_date_time
    │   ├── session_2
    │   └── ...
    ├── observation
    │   ├── session_1_observation
    │   ├── session_2_observation
    │   └── ...
    ├── session_summary
    │   ├── session_1_summary
    │   ├── session_2_summary
    │   └── ...
    ├── event_summary
    │   ├── events_session_1
    │   ├── events_session_2
    │   └── ...
    └── qa
        ├── QAItem
        │   ├── question
        │   ├── answer
        │   ├── evidence
        │   └── category
        └── ...
```

---

## 16. 核心语义总结

```text
Sample:
    一整段长期 conversation，是 LoCoMo 的顶层样本单位。

Conversation:
    两个 speaker 跨多个 session 的长期对话。

Session:
    有时间戳的一次聊天片段。

Turn:
    session 内某个 speaker 的一条发言，可能带图片信息。

QA:
    挂在整个 sample / conversation 下的问题集合，不是挂在单个 session 或 turn 下。

Observation:
    generated session observations，可作为 RAG database。

Session summary:
    generated session summaries，可作为 RAG database。

Event summary:
    annotated significant events，是 event summarization 的 ground truth。

Evidence:
    QA 中标注的答案依据 dia_id 列表，连接 QA item 和原始 conversation turn。
```

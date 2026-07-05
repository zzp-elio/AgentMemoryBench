下面是**纯资源说明版**，只描述 Mem-Gallery dataset 的数据结构、字段含义、字段在测评中的作用，以及各类任务和字段之间的关系。

---

# Mem-Gallery Dataset 数据结构说明

## 1. 顶层结构

一个 `.json` 文件对应一个 **scenario-level sample**，即一个完整的长期对话场景。

```json
{
  "character_profile": {...},
  "multi_session_dialogues": [...],
  "human-annotated QAs": [...]
}
```

| 字段                        | 类型     | 含义                   | 测评作用                    |
| ------------------------- | ------ | -------------------- | ----------------------- |
| `character_profile`       | object | 当前场景中的用户画像           | 提供用户姓名、背景、性格等元信息        |
| `multi_session_dialogues` | list   | 多个 session 组成的长期对话历史 | memory method 需要写入的记忆来源 |
| `human-annotated QAs`     | list   | 人工标注的问题、答案、证据        | 用于检索、回答和计算指标            |

用户提供的真实样例中，顶层就是这三部分：`character_profile`、`multi_session_dialogues`、`human-annotated QAs`。

---

## 2. `character_profile`

示例：

```json
{
  "name": "Lena",
  "persona_summary": "Lena is a 21-year-old university student majoring in Life Sciences...",
  "traits": ["curious", "caring", "enthusiastic"],
  "conversation_style": "Warm and inquisitive..."
}
```

| 字段                   | 类型           | 含义                | 测评作用          |
| -------------------- | ------------ | ----------------- | ------------- |
| `name`               | string       | 用户/角色姓名，例如 `Lena` | 用于确定对话中的用户身份  |
| `persona_summary`    | string       | 用户整体背景            | 可能包含可被问到的背景信息 |
| `traits`             | list[string] | 用户性格特征            | 用户画像元信息       |
| `conversation_style` | string       | 用户说话风格            | 用户画像元信息       |

官方 runner 会使用 `character_profile.name` 构造 speaker 名称，例如 `user (Lena)`。

---

## 3. `multi_session_dialogues`

`multi_session_dialogues` 是一个 session 列表。

```json
[
  {
    "session_id": "D1",
    "date": "2024-05-12",
    "dialogues": [...]
  },
  {
    "session_id": "D2",
    "date": "2024-05-23",
    "dialogues": [...]
  }
]
```

### Session 字段

| 字段           | 类型     | 含义                      | 测评作用                                     |
| ------------ | ------ | ----------------------- | ---------------------------------------- |
| `session_id` | string | session 编号，例如 `D1`、`D2` | QA 中的 `session_id` 会引用它                  |
| `date`       | string | 当前 session 的日期          | 用于时间推理任务，也会作为 dialogue round 的 timestamp |
| `dialogues`  | list   | 当前 session 内的多轮对话       | 每个 dialogue round 是一个记忆事件来源              |

这里的 `date` 是 **session 级别时间戳**。官方代码在处理时，会把这个 `date` 复制到该 session 下每个 dialogue round 生成的 memory event 里。

---

## 4. `dialogues`：单个 dialogue round

一个 dialogue round 通常表示一次用户输入和一次 assistant 回复。

### 纯文本 round

```json
{
  "round": "D1:1",
  "user": "Hi! I’ve been really enjoying my Life Sciences major classes lately.",
  "assistant": "That sounds wonderful, Lena!"
}
```

### 多模态 round

```json
{
  "round": "D1:5",
  "user": "I’ve been reading about Maltese dogs...",
  "assistant": "Yes, Maltese dogs are fantastic companions!",
  "image_id": ["D1:IMG_001"],
  "input_image": ["../image/Academic_Animal_Pet_Research_Life/D1_IMG_001.jpg"],
  "image_caption": ["Small, fluffy white puppy sitting on a dark wooden chair..."]
}
```

### Dialogue round 字段

| 字段              | 类型           | 含义                                | 测评作用                         |
| --------------- | ------------ | --------------------------------- | ---------------------------- |
| `round`         | string       | 当前 dialogue round 的唯一编号，例如 `D1:5` | 细粒度证据 id；QA 的 `clue` 会引用它    |
| `user`          | string       | 用户发言                              | 记忆内容的一部分                     |
| `assistant`     | string       | assistant 回复                      | 记忆内容的一部分                     |
| `image_id`      | list[string] | 历史对话图片的逻辑 id，例如 `D1:IMG_001`      | 视觉搜索类任务可能要求返回该 id            |
| `input_image`   | list[string] | 历史对话图片路径                          | 多模态记忆和视觉检索的图像来源              |
| `image_caption` | list[string] | 历史对话图片 caption                    | 文本化图像信息；text-only memory 可使用 |

官方处理时，会把一个 dialogue round 转换成一个 memory event，其中 `user` 和 `assistant` 被合并为一段文本；如果有图片，则附带图片路径、caption 和 image id。 

转换后的信息逻辑上类似：

```python
{
  "text": "user (Lena): ...\nassistant: ...",
  "image": {
    "path": ".../D1_IMG_001.jpg",
    "caption": "Small, fluffy white puppy...",
    "img_id": "D1:IMG_001"
  },
  "timestamp": "2024-05-12",
  "dialogue_id": "D1:5"
}
```

其中：

| 生成字段            | 来源                   | 含义              |
| --------------- | -------------------- | --------------- |
| `text`          | `user` + `assistant` | 写入 memory 的文本内容 |
| `image.path`    | `input_image`        | 历史图片路径          |
| `image.caption` | `image_caption`      | 历史图片文本描述        |
| `image.img_id`  | `image_id`           | 历史图片逻辑 id       |
| `timestamp`     | session `date`       | 当前记忆事件的时间       |
| `dialogue_id`   | `round`              | 当前记忆事件的证据 id    |

---

## 5. `human-annotated QAs`

`human-annotated QAs` 是测评问题列表。每个 QA 是一个 evaluation instance。

示例：

```json
{
  "point": "TTL",
  "question": "What breed is the dog in the attached image?",
  "question_image": "../image/Academic_Animal_Pet_Research_Life/QA_IMG_001.jpg",
  "answer": "Maltese",
  "session_id": ["D1", "D2"],
  "clue": ["D1:5", "D1:6", "D1:7", "D1:11", "D2:1"],
  "image_caption": "Small white fluffy dog lying on a tiled floor indoors..."
}
```

### QA 字段

| 字段               | 类型           | 含义                                     | 测评作用                                   |
| ---------------- | ------------ | -------------------------------------- | -------------------------------------- |
| `point`          | string       | 任务类型，例如 `FR`、`TTL`、`TR`、`VR`、`AR`、`CD` | 决定问题类型和部分回答格式                          |
| `question`       | string       | 问题文本                                   | 用于 memory recall 和最终 answer generation |
| `question_image` | string       | QA 自带图片路径                              | 当前问题的视觉输入，不是历史 memory                  |
| `image_caption`  | string       | QA 图片的 caption                         | 当前问题图片的文本描述                            |
| `answer`         | string       | 标准答案                                   | 用于最终回答指标                               |
| `session_id`     | list[string] | 该问题相关的 session                         | 粗粒度证据范围                                |
| `clue`           | list[string] | 该问题相关的 dialogue round id               | 细粒度证据，用于 retrieval metric              |

官方 runner 会读取 `question`、`question_image`、`image_caption`、`answer`、`point`、`session_id` 和 `clue`。其中 `clue` 是检索评测的 ground-truth evidence ids。 

### `session_id` 和 `clue` 的区别

| 字段           | 粒度               | 示例                 | 作用                 |
| ------------ | ---------------- | ------------------ | ------------------ |
| `session_id` | session 级        | `["D1", "D2"]`     | 表示答案大概来自哪些 session |
| `clue`       | dialogue round 级 | `["D1:5", "D2:1"]` | 表示答案具体依赖哪些历史 round |

`clue=[]` 是合法情况，通常出现在 answer refusal 类任务中，表示历史对话中没有支持证据。

---

# 6. 测评流程中的字段使用关系

一个 scenario 的测评逻辑可以概括为：

```text
multi_session_dialogues
    -> dialogue rounds
        -> memory events
            -> memory.store(...)

human-annotated QAs
    -> question / question_image / image_caption
        -> memory.recall(...)
            -> retrieved memory context
                -> answer model generates system_answer

system_answer vs answer
    -> answer metrics

retrieved dialogue ids vs clue
    -> retrieval metrics
```

官方 runner 的执行顺序是：先写入完整历史对话，再遍历 QA。

---

# 7. 各类任务与字段关系

## 7.1 FR — Factual Retrieval

示例：

```json
{
  "point": "FR",
  "question": "What subject is now Lena majoring in at university?",
  "answer": "Life Sciences",
  "session_id": ["D1"],
  "clue": ["D1:1"]
}
```

含义：从历史对话中检索明确事实。

| 相关字段         | 作用                      |
| ------------ | ----------------------- |
| `question`   | 查询目标事实                  |
| `answer`     | 标准事实答案                  |
| `clue`       | 支持该事实的历史 dialogue round |
| `session_id` | 该事实所在的 session 范围       |

该类问题主要测 memory 是否能找到并利用显式事实。

---

## 7.2 TTL — Test-Time Learning

示例：

```json
{
  "point": "TTL",
  "question": "What breed is the dog in the attached image?",
  "question_image": "../image/.../QA_IMG_001.jpg",
  "answer": "Maltese",
  "session_id": ["D1", "D2"],
  "clue": ["D1:5", "D1:6", "D1:7", "D1:11", "D2:1"],
  "image_caption": "Small white fluffy dog lying on a tiled floor..."
}
```

含义：根据历史对话中学到的新实体、新概念或视觉关联，回答当前问题。

| 相关字段             | 作用                         |
| ---------------- | -------------------------- |
| `question`       | 当前要判断的问题                   |
| `question_image` | 当前问题附带的新图片                 |
| `image_caption`  | 当前问题图片的文本描述                |
| `clue`           | 历史中提供学习依据的 dialogue rounds |
| `answer`         | 当前问题的目标答案                  |

TTL 不只是事实检索，往往需要把历史中的视觉/文本信息迁移到当前 query image 上。例如历史中多次出现 Maltese 的描述和图片，问题给出新狗图，答案需要判断其 breed。

---

## 7.3 TR — Temporal Reasoning

示例：

```json
{
  "point": "TR",
  "question": "When did Lena adopt her dog? Return in the format YYYY-MM-DD.",
  "answer": "2024-05-22",
  "session_id": ["D2"],
  "clue": ["D2:1"]
}
```

含义：结合 session 日期和对话中的时间表达进行推理。

| 相关字段                          | 作用                               |
| ----------------------------- | -------------------------------- |
| session `date`                | 时间锚点                             |
| dialogue `user` / `assistant` | 可能包含 yesterday、last week 等相对时间表达 |
| `question`                    | 指定时间问题和输出格式                      |
| `answer`                      | 标准时间答案                           |
| `clue`                        | 支持时间推理的 dialogue round           |

例如 session `D2` 的日期是 `2024-05-23`，对话中说 “adopted ... yesterday”，则答案是 `2024-05-22`。

---

## 7.4 VR — Visual-centric Reasoning

示例：

```json
{
  "point": "VR",
  "question": "Is the dog in the picture more similar to Amy’s Cairn Terrier or to Lena’s Maltese?",
  "question_image": "../image/.../QA_IMG_004.jpg",
  "answer": "It is more similar to Amy’s Cairn Terrier.",
  "session_id": ["D2"],
  "clue": ["D2:3", "D2:4"],
  "image_caption": "Small, shaggy tan dog..."
}
```

含义：基于当前问题图片和历史视觉/文本记忆进行比较、识别或关系判断。

| 相关字段                                     | 作用          |
| ---------------------------------------- | ----------- |
| `question_image`                         | 当前视觉输入      |
| `image_caption`                          | 当前视觉输入的文本描述 |
| dialogue `input_image` / `image_caption` | 历史视觉证据      |
| `clue`                                   | 相关历史视觉记忆    |
| `answer`                                 | 视觉推理结果      |

VR 通常需要比较当前图片和历史对话中提到的人、宠物、物体或场景。

---

## 7.5 AR — Answer Refusal

示例：

```json
{
  "point": "AR",
  "question": "What is the name of Lena's friend Amy's cat?",
  "answer": "Not mentioned.",
  "session_id": ["D2"],
  "clue": []
}
```

含义：测试系统在记忆中没有相关信息时是否拒绝编造答案。

| 相关字段       | 作用                   |
| ---------- | -------------------- |
| `question` | 查询一个历史中未提到的信息        |
| `answer`   | 通常是 `Not mentioned.` |
| `clue`     | 通常为空，表示没有支持证据        |

官方 AR 格式约束是：如果对话中没有相关信息，回答 `Not mentioned.` 

---

## 7.6 CD — Conflict Detection

示例：

```json
{
  "point": "CD",
  "question": "Please determine whether the following information conflicts with the dialogue memory:\nLena’s pet Lumi is a cat.",
  "answer": "Yes.",
  "session_id": ["D2"],
  "clue": ["D2:8"]
}
```

含义：判断问题中的 claim 是否与历史记忆冲突。

| 相关字段       | 作用             |
| ---------- | -------------- |
| `question` | 包含需要判断的 claim  |
| `clue`     | 用来判断冲突的历史证据    |
| `answer`   | `Yes.` 或 `No.` |

官方 CD 格式约束是：严格回答 `Yes.` 或 `No.` 

---

## 7.7 VS — Visual-centric Search

用户片段中没有 VS 样例，但官方 runner 支持 VS 类型。

含义：根据问题从历史记忆中搜索符合条件的图片，并返回图片 id。

| 相关字段                     | 作用                    |
| ------------------------ | --------------------- |
| dialogue `image_id`      | 最终答案需要返回的图片 id        |
| dialogue `input_image`   | 历史图片                  |
| dialogue `image_caption` | 历史图片描述                |
| `question`               | 图片搜索条件                |
| `answer`                 | 标准 image id           |
| `clue`                   | 相关图片所在 dialogue round |

官方 VS 格式约束是：返回 image_id；如果多个图片，升序排列并用逗号分隔。

---

## 7.8 MR — Multi-entity Reasoning

用户片段中没有 MR 样例，但该类任务通常表示多实体推理。

含义：问题需要同时处理多个实体、多个关系或多个证据片段。

| 相关字段                       | 作用                    |
| -------------------------- | --------------------- |
| `question`                 | 包含多个实体或关系             |
| `clue`                     | 通常包含多个 dialogue round |
| `session_id`               | 可能跨多个 session         |
| dialogue text/image fields | 提供实体事实和关系证据           |
| `answer`                   | 多证据合成后的答案             |

MR 关注的是跨实体、跨证据的组合推理，而不是单点事实检索。

---

## 7.9 KR — Knowledge Resolution

用户片段中没有 KR 样例，但该类任务通常表示知识更新或冲突后的解析。

含义：在历史记忆中存在旧信息、新信息、修正信息或冲突信息时，解析当前有效知识。

| 相关字段           | 作用              |
| -------------- | --------------- |
| session `date` | 判断信息新旧          |
| dialogue text  | 包含旧事实、新事实、修正或确认 |
| `clue`         | 可能包含多个相关证据      |
| `answer`       | 当前应采纳的最终信息      |

KR 关注的是 memory 中知识状态的更新和解析。

---

# 8. 指标相关字段

## 8.1 Answer evaluation

答案评测使用：

```text
system_answer vs answer
```

常见指标包括：

| 指标                     | 含义                     |
| ---------------------- | ---------------------- |
| EM                     | exact match            |
| F1                     | token overlap F1       |
| BLEU / BLEU-1 / BLEU-2 | 文本相似度                  |
| LLM Judge              | 用 judge model 判断答案是否正确 |

官方 evaluation 会按 `category` 分组计算 F1、BLEU、EM 等指标。

---

## 8.2 Retrieval evaluation

检索评测使用：

```text
retrieved_ids vs clue
```

| 字段              | 含义                                      |
| --------------- | --------------------------------------- |
| `retrieved_ids` | memory recall 返回的历史 dialogue round ids  |
| `clue`          | QA 标注的 gold evidence dialogue round ids |

常见指标包括：

| 指标          | 含义                        |
| ----------- | ------------------------- |
| Precision@K | 返回的 top-K 中有多少是 gold clue |
| Recall@K    | gold clue 中有多少被返回         |
| HitRate@K   | top-K 中是否至少命中一个 gold clue |

官方代码会将 retrieved ids 和 QA 的 `clue` 做比较，计算 retrieval metrics。

---

# 9. 字段之间的核心关系

```text
scenario json
├── character_profile
│   └── name/persona metadata
│
├── multi_session_dialogues
│   └── session
│       ├── session_id
│       ├── date
│       └── dialogues
│           └── dialogue round
│               ├── round
│               ├── user
│               ├── assistant
│               ├── image_id
│               ├── input_image
│               └── image_caption
│
└── human-annotated QAs
    └── QA item
        ├── point
        ├── question
        ├── question_image
        ├── image_caption
        ├── answer
        ├── session_id
        └── clue
```

最关键的对应关系：

| 数据来源字段              | 对应测评字段          | 关系                            |
| ------------------- | --------------- | ----------------------------- |
| dialogue `round`    | QA `clue`       | `clue` 指向支持答案的 dialogue round |
| dialogue `image_id` | VS answer       | 视觉搜索任务可能返回 image id           |
| session `date`      | TR answer       | 时间推理需要 session 日期             |
| QA `question_image` | TTL / VR        | 当前问题的视觉输入                     |
| QA `image_caption`  | TTL / VR        | 当前问题图片的文本化描述                  |
| QA `answer`         | answer metric   | 标准答案                          |
| QA `point`          | category metric | 任务类别和分组指标                     |

一句话概括：**`multi_session_dialogues` 是记忆来源，`human-annotated QAs` 是测评入口；`answer` 用于答案正确性评测，`clue` 用于检索正确性评测。**

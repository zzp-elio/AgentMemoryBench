下面这版更适合直接给 Codex：只说明 **MemBench 数据集结构、字段含义、字段在测评中的作用、各类任务的含义**，不替 Codex 决定怎么写代码。

---

# MemBench `data2test` 数据结构说明

## 1. 正式测评数据范围

`data2test/` 下有两个正式子目录：

```text
data2test/
├── 0-10k/
└── 100k/
```

每个目录下各有 4 个 JSON 文件，共 8 个正式测评文件：

```text
FirstAgentDataHighLevel_*.json
FirstAgentDataLowLevel_*.json
ThirdAgentDataHighLevel_*.json
ThirdAgentDataLowLevel_*.json
```

四类文件含义如下：

| 文件前缀                      | 视角                         | 记忆类型                   | 含义                     |
| ------------------------- | -------------------------- | ---------------------- | ---------------------- |
| `FirstAgentDataHighLevel` | Participation / FirstAgent | Reflective / HighLevel | 第一人称对话中的高层记忆，如偏好、情绪、推荐 |
| `FirstAgentDataLowLevel`  | Participation / FirstAgent | Factual / LowLevel     | 第一人称对话中的显式事实记忆         |
| `ThirdAgentDataHighLevel` | Observation / ThirdAgent   | Reflective / HighLevel | 第三人称观察消息流中的高层记忆        |
| `ThirdAgentDataLowLevel`  | Observation / ThirdAgent   | Factual / LowLevel     | 第三人称观察消息流中的显式事实记忆      |

`0-10k` 与 `100k` 的主要区别是上下文长度：

| 目录       | 含义                                        |
| -------- | ----------------------------------------- |
| `0-10k/` | 较短 memory flow，标准长度测试                     |
| `100k/`  | 加入大量 noise 后的长 memory flow，用于长上下文/长记忆压力测试 |

`data2test/` 根目录下可能存在额外游离 JSON 文件，但正式结构应以 `0-10k/` 和 `100k/` 两个子目录中的 8 个文件为准。

---

## 2. 顶层 JSON 结构

每个 JSON 的顶层结构是：

```json
{
  "task_type": {
    "subcategory": [
      {
        "tid": 0,
        "message_list": [],
        "QA": {}
      }
    ]
  }
}
```

含义：

| 层级            | 示例                                                       | 含义                   |
| ------------- | -------------------------------------------------------- | -------------------- |
| `task_type`   | `simple`, `comparative`, `highlevel`, `knowledge_update` | 任务类型，表示该样本主要考察哪种记忆能力 |
| `subcategory` | `roles`, `events`, `movie`, `food`, `book`               | 子类别，表示问题所属的信息域       |
| `trajectory`  | `{tid, message_list, QA}`                                | 最小独立评测单元             |

一个 JSON 文件包含多个 `task_type`，每个 `task_type` 下有多个 `subcategory`，每个 `subcategory` 下是若干条 `trajectory`。

---

## 3. Trajectory 结构

每条 trajectory 是一次独立测试样本。

```json
{
  "tid": 0,
  "message_list": [
    ...
  ],
  "QA": {
    "qid": 0,
    "question": "...",
    "answer": "...",
    "time": "...",
    "target_step_id": [3],
    "choices": {
      "A": "...",
      "B": "...",
      "C": "...",
      "D": "..."
    },
    "ground_truth": "B"
  }
}
```

字段含义：

| 字段             | 类型     | 含义                    | 测评中的作用                        |
| -------------- | ------ | --------------------- | ----------------------------- |
| `tid`          | `int`  | trajectory 在当前子类别下的编号 | 用于标识样本；不是全局唯一                 |
| `message_list` | `list` | 按时间顺序排列的记忆输入流         | 评测时逐条输入给 memory method        |
| `QA`           | `dict` | 该 trajectory 对应的最终问题  | 在 `message_list` 全部输入后用于提问和评分 |

注意：`tid` 会在不同文件、不同 `task_type`、不同 `subcategory` 中重复，不能单独作为全局唯一 ID。

---

## 4. `message_list` 字段

`message_list` 是该 trajectory 中需要被记住的信息流。它的元素格式由文件视角决定。

---

### 4.1 FirstAgent 文件中的 `message_list`

适用于：

```text
FirstAgentDataHighLevel
FirstAgentDataLowLevel
```

每个元素是一个 dict：

```json
{
  "user": "I want to tell you about my uncle, Landon Pierce. He's 27 years old. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)",
  "agent": "That's great! Landon is quite young at 27. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
}
```

字段含义：

| 字段      | 类型    | 含义                  | 测评中的作用                  |
| ------- | ----- | ------------------- | ----------------------- |
| `user`  | `str` | 用户在该轮对话中的发言         | 包含需要记住的事实、偏好、情绪或上下文     |
| `agent` | `str` | assistant 在该轮对话中的回复 | 也是对话历史的一部分，可能提供上下文或确认信息 |

在 FirstAgent 场景中，agent 是对话参与者，所以一条 `message_list` 元素表示一轮 user-agent 对话。

---

### 4.2 ThirdAgent 文件中的 `message_list`

适用于：

```text
ThirdAgentDataHighLevel
ThirdAgentDataLowLevel
```

每个元素是字符串：

```json
"I really love Casablanca; the timeless romance and memorable lines always draw me in. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
```

字段含义：

| 类型    | 含义             | 测评中的作用                              |
| ----- | -------------- | ----------------------------------- |
| `str` | 一条被观察到的用户信息或叙述 | 作为单条 memory event 输入给 memory method |

ThirdAgent 场景中没有 `user/agent` 对话角色区分，agent 只是旁观者，接收单向信息流。

---

### 4.3 message 中的时间地点元数据

很多 message 末尾包含类似格式：

```text
(place: Boston, MA; time: '2024-10-01 08:00' Tuesday)
```

含义：

| 元数据     | 含义        |
| ------- | --------- |
| `place` | 事件或对话发生地点 |
| `time`  | 事件或对话发生时间 |

注意：

* `0-10k` 数据中大部分原始 message 带有该后缀。
* `100k` 数据中插入了大量 noise message，很多 noise message 没有标准 `(place/time)` 后缀。
* ThirdAgent 中部分 message 的 `time` 格式可能不完全规整，例如缺少冒号或引号。
* message 内部的时间地点属于可用上下文，但不保证每条 message 都能稳定解析。

---

## 5. `QA` 字段

`QA` 是当前 trajectory 的最终选择题。

```json
{
  "qid": 0,
  "question": "What is the education level of the subordinate?",
  "answer": "Associate Degree",
  "time": "'2024-10-01 12:30' Tuesday",
  "target_step_id": [5],
  "choices": {
    "A": "Bachelor's Degree",
    "B": "Associate Degree",
    "C": "High School Diploma",
    "D": "Master's Degree"
  },
  "ground_truth": "B"
}
```

字段含义：

| 字段               | 类型            | 含义                        | 测评中的作用                                     |
| ---------------- | ------------- | ------------------------- | ------------------------------------------ |
| `qid`            | `int`         | question id               | 当前正式数据中每条 trajectory 基本只有一个 QA，`qid` 通常为 0 |
| `question`       | `str`         | 问题文本                      | 用于查询 memory，并交给回答模块生成选项                    |
| `answer`         | `str \| list` | 自然语言正确答案                  | 表示正确答案内容；不是官方 accuracy 的直接匹配对象             |
| `time`           | `str`         | 问题发生时间                    | 作为问题上下文，常与 question 一起构成查询                 |
| `target_step_id` | `list[int]`   | 支撑答案的 evidence message 索引 | 用于 retrieval recall 或 evidence 分析          |
| `choices`        | `dict`        | A/B/C/D 四个候选选项            | 回答模块需要从中选择一个                               |
| `ground_truth`   | `str`         | 正确选项字母                    | accuracy 的 exact match 标准                  |

---

## 6. `answer` 与 `ground_truth`

`answer` 是正确答案的自然语言内容，`ground_truth` 是正确选项字母。

示例：

```json
{
  "answer": "Associate Degree",
  "ground_truth": "B",
  "choices": {
    "A": "Bachelor's Degree",
    "B": "Associate Degree",
    "C": "High School Diploma",
    "D": "Master's Degree"
  }
}
```

含义：

```text
answer       = Associate Degree
ground_truth = B
choices["B"] = Associate Degree
```

官方选择题准确率通常以 `ground_truth` 为准，即判断模型输出的选项字母是否等于 `ground_truth`。

部分 FirstAgent LowLevel 推荐类任务中，`answer` 可能是 list，但 `ground_truth` 仍然是单个 A/B/C/D 字母。

---

## 7. `target_step_id`

`target_step_id` 是答案证据所在的 `message_list` 索引，从 0 开始。

示例：

```json
{
  "target_step_id": [3, 8]
}
```

含义：

```text
message_list[3] 和 message_list[8] 是回答该问题所需的关键证据。
```

测评作用：

| 用途                 | 说明                                           |
| ------------------ | -------------------------------------------- |
| retrieval recall   | 判断 memory method 检索出的证据 step 是否覆盖真实 evidence |
| error analysis     | 分析模型答错是因为没存住、没检索到，还是 reader 没用对              |
| evidence debugging | 定位某个问题依赖哪些历史 message                         |

已知边界：

* FirstAgentDataLowLevel 的 `comparative/events` 中存在 1 条官方数据异常：`target_step_id == len(message_list)`，即越界。
* 因此 `target_step_id` 不应被假设一定能安全索引 `message_list`。
* 该字段不属于模型可见答案，不应与 `choices` 或 `ground_truth` 混淆。

---

## 8. 四类文件的任务结构

## 8.1 `FirstAgentDataHighLevel`

视角：FirstAgent / Participation
记忆类型：HighLevel / Reflective
`message_list` 元素：`{"user": ..., "agent": ...}`

结构：

```json
{
  "highlevel": {
    "movie": [],
    "food": [],
    "book": [],
    "emotion": []
  },
  "highlevel_rec": {
    "movie": [],
    "food": [],
    "book": []
  }
}
```

任务含义：

| task_type       | subcategory | 含义             |
| --------------- | ----------- | -------------- |
| `highlevel`     | `movie`     | 根据历史对话归纳用户电影偏好 |
| `highlevel`     | `food`      | 根据历史对话归纳用户食物偏好 |
| `highlevel`     | `book`      | 根据历史对话归纳用户阅读偏好 |
| `highlevel`     | `emotion`   | 根据历史对话判断用户情绪状态 |
| `highlevel_rec` | `movie`     | 基于历史偏好进行电影推荐选择 |
| `highlevel_rec` | `food`      | 基于历史偏好进行食物推荐选择 |
| `highlevel_rec` | `book`      | 基于历史偏好进行书籍推荐选择 |

这些任务通常不是简单查找单条事实，而是需要从多条对话中归纳偏好、状态或推荐依据。

---

## 8.2 `ThirdAgentDataHighLevel`

视角：ThirdAgent / Observation
记忆类型：HighLevel / Reflective
`message_list` 元素：字符串

结构：

```json
{
  "highlevel": {
    "movie": [],
    "food": [],
    "book": [],
    "emotion": []
  }
}
```

任务含义：

| task_type   | subcategory | 含义              |
| ----------- | ----------- | --------------- |
| `highlevel` | `movie`     | 根据观察到的信息流归纳电影偏好 |
| `highlevel` | `food`      | 根据观察到的信息流归纳食物偏好 |
| `highlevel` | `book`      | 根据观察到的信息流归纳阅读偏好 |
| `highlevel` | `emotion`   | 根据观察到的信息流判断情绪状态 |

与 FirstAgentDataHighLevel 的主要区别：

```text
FirstAgentDataHighLevel 有 highlevel_rec；
ThirdAgentDataHighLevel 没有 highlevel_rec。

FirstAgent message 是 user-agent 对话 pair；
ThirdAgent message 是单条 observation string。
```

---

## 8.3 `FirstAgentDataLowLevel`

视角：FirstAgent / Participation
记忆类型：LowLevel / Factual
`message_list` 元素：`{"user": ..., "agent": ...}`

结构：

```json
{
  "simple": {
    "roles": [],
    "events": []
  },
  "conditional": {
    "roles": [],
    "events": []
  },
  "comparative": {
    "roles": [],
    "events": []
  },
  "aggregative": {
    "roles": [],
    "events": []
  },
  "post_processing": {
    "roles": [],
    "events": []
  },
  "knowledge_update": {
    "roles": [],
    "events": []
  },
  "noisy": {
    "roles": [],
    "events": []
  },
  "lowlevel_rec": {
    "movie": [],
    "food": [],
    "book": []
  },
  "RecMultiSession": {
    "multi_agent": []
  }
}
```

任务类型含义：

| task_type          | 含义                                     |
| ------------------ | -------------------------------------- |
| `simple`           | 直接事实记忆，例如某人的年龄、学历、职业，某事件的时间地点          |
| `conditional`      | 条件筛选记忆，根据问题中的条件定位对应事实                  |
| `comparative`      | 比较多个对象或事件的属性，例如谁更年长、哪个事件更早             |
| `aggregative`      | 聚合统计，多条事实的数量、总和或计数                     |
| `post_processing`  | 对记忆内容进行加工后回答，例如电话号码后几位求和、生日属于哪个季节、邮箱后缀 |
| `knowledge_update` | 知识更新，新信息覆盖旧信息，回答时依赖最新状态                |
| `noisy`            | 噪声干扰下的事实定位                             |
| `lowlevel_rec`     | 基于显式低层事实的推荐任务                          |
| `RecMultiSession`  | 跨多 session / 多 agent 信息的推荐或综合任务        |

子类别含义：

| subcategory   | 含义                       |
| ------------- | ------------------------ |
| `roles`       | 人物角色信息，如亲友、同事、下属、职业、联系方式 |
| `events`      | 事件信息，如活动时间、地点、规模、持续时间    |
| `movie`       | 电影相关事实或推荐                |
| `food`        | 食物相关事实或推荐                |
| `book`        | 书籍相关事实或推荐                |
| `multi_agent` | 多会话或多对象综合信息              |

特殊情况：

* `lowlevel_rec/movie`
* `lowlevel_rec/food`
* `lowlevel_rec/book`
* `RecMultiSession/multi_agent`

这些任务中的 `QA.answer` 可能是 list，但 `ground_truth` 仍然是 A/B/C/D。

---

## 8.4 `ThirdAgentDataLowLevel`

视角：ThirdAgent / Observation
记忆类型：LowLevel / Factual
`message_list` 元素：字符串

结构：

```json
{
  "simple": {
    "roles": [],
    "events": [],
    "items": [],
    "places": [],
    "hybrid": []
  },
  "conditional": {
    "roles": [],
    "events": [],
    "items": [],
    "places": [],
    "hybrid": []
  },
  "comparative": {
    "roles": [],
    "events": [],
    "hybrid": []
  },
  "aggregative": {
    "roles": [],
    "events": [],
    "hybrid": []
  },
  "post_processing": {
    "roles": [],
    "events": [],
    "items": [],
    "places": [],
    "hybrid": []
  },
  "noisy": {
    "roles": [],
    "events": [],
    "items": [],
    "places": [],
    "hybrid": []
  },
  "knowledge_update": {
    "roles": [],
    "events": []
  }
}
```

任务类型含义与 FirstAgentDataLowLevel 基本一致：

| task_type          | 含义           |
| ------------------ | ------------ |
| `simple`           | 直接事实记忆       |
| `conditional`      | 条件筛选记忆       |
| `comparative`      | 多对象比较        |
| `aggregative`      | 多条事实聚合统计     |
| `post_processing`  | 对记忆内容加工后回答   |
| `noisy`            | 噪声干扰下的事实定位   |
| `knowledge_update` | 信息更新后的最新事实记忆 |

子类别含义：

| subcategory | 含义                                 |
| ----------- | ---------------------------------- |
| `roles`     | 人物角色相关事实                           |
| `events`    | 事件相关事实                             |
| `items`     | 物品相关事实                             |
| `places`    | 地点相关事实                             |
| `hybrid`    | 混合信息，可能跨 roles/events/items/places |

与 FirstAgentDataLowLevel 的主要区别：

```text
ThirdAgentDataLowLevel 没有 lowlevel_rec；
ThirdAgentDataLowLevel 没有 RecMultiSession；
ThirdAgentDataLowLevel 的 message_list 是 observation string；
ThirdAgentDataLowLevel 的子类别包含 items / places / hybrid。
```

---

## 9. 字段与测评过程的关系

一条 trajectory 的测评过程与字段关系如下：

```text
message_list
  ↓
逐条作为历史记忆输入

QA.question + QA.time
  ↓
作为查询问题

QA.choices
  ↓
作为候选答案空间

模型输出 A/B/C/D
  ↓
与 QA.ground_truth 比较，得到 accuracy

memory method 返回的 evidence step ids
  ↓
与 QA.target_step_id 比较，得到 retrieval recall
```

字段作用总结：

| 字段                  | 主要用于                 |
| ------------------- | -------------------- |
| `message_list`      | 构造被记忆的历史信息流          |
| `QA.question`       | 构造查询                 |
| `QA.time`           | 补充查询时间上下文            |
| `QA.choices`        | 限定候选答案               |
| `QA.ground_truth`   | 计算选择题准确率             |
| `QA.answer`         | 表示正确答案内容，辅助理解和分析     |
| `QA.target_step_id` | 计算检索证据召回率            |
| `task_type`         | 分析不同记忆能力上的表现         |
| `subcategory`       | 分析不同内容域上的表现          |
| `tid`               | 标识当前子类别内的 trajectory |

---

## 10. 已知数据边界

| 边界                         | 说明                                                     |
| -------------------------- | ------------------------------------------------------ |
| `tid` 不全局唯一                | 只在当前子类别下有局部意义                                          |
| `qid` 基本固定为 0              | 每条 trajectory 通常只有一个 QA                                |
| FirstAgent message 是 dict  | 结构为 `{"user": ..., "agent": ...}`                      |
| ThirdAgent message 是 str   | 没有 user/agent 角色区分                                     |
| `answer` 可能是 list          | 主要出现在 FirstAgent LowLevel 推荐类任务                        |
| `ground_truth` 是 A/B/C/D   | 选择题 accuracy 的核心标签                                     |
| `target_step_id` 可能越界      | FirstAgentDataLowLevel 的 comparative/events 中有 1 条已知异常 |
| 不是所有 message 都有 place/time | 尤其是 100k 中插入的 noise message                            |
| `100k` message 数量大         | 同 schema，但上下文更长，noise 更多                               |

---

## 11. 数据结构极简总览

```text
JSON file
└── task_type
    └── subcategory
        └── trajectory
            ├── tid
            ├── message_list
            │   ├── FirstAgent: {"user": str, "agent": str}
            │   └── ThirdAgent: str
            └── QA
                ├── qid
                ├── question
                ├── answer
                ├── time
                ├── target_step_id
                ├── choices
                │   ├── A
                │   ├── B
                │   ├── C
                │   └── D
                └── ground_truth
```

核心评测标签：

```text
accuracy label = QA.ground_truth
evidence label = QA.target_step_id
input memory   = message_list
query          = QA.question + QA.time
candidate set  = QA.choices
```

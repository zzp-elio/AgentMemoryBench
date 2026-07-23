# Agent Memory Benchmark 项目进展报告（截至 2026-07-23）

> 汇报区间：2026-07-12 至 2026-07-23。

---

## 目录

1. [**一、当前完成状态**](#s1) —— 首批 5/5 方法已在 5 个 benchmark 上跑通并冻结
2. [**二、本周解决的"阻碍"**](#s2) —— 真跑起来才暴露的隐藏问题，都已写成兜底规则进 adapter
   - [（benchmark 侧）数据本身的异常](#s2b)：LoCoMo / LongMemEval / MemBench / BEAM
   - [（method 侧）接口的陷阱](#s2m)：LightMem 的"伪自由"签名、Mem0 的"伪支持"时间戳
3. [**三、benchmark 拓展与指标拓展**](#s3) —— 让方法能公平参与全部评测的主动工作
4. [**四、小结与下一步**](#s4) —— 剩余方法队列与复工计划

---

<a id="s1"></a>
## 一、当前完成状态

本阶段的核心目标是**把"方法 × benchmark"的小批量真实测试跑通**——即在真实 API 下
完成极小规模的端到端运行

### 1.1 完成状态表

| method | LoCoMo | LongMemEval | MemBench | BEAM | HaluMem | 冻结状态 |
|---|:--:|:--:|:--:|:--:|:--:|---|
| LightMem | ✅ | ✅ | ✅ | ✅ | ✅ | `完成` |
| Mem0 | ✅ | ✅ | ✅ | ✅ | ✅ | `完成` |
| MemoryOS | ✅ | ✅ | ✅ | ✅ | ✅ | `完成` |
| A-Mem | ✅ | ✅ | ✅ | ✅ | ✅ | `完成` |
| SimpleMem | ✅ | ✅ | ✅ | ✅ | ✅ | `完成` |

首批五家已完成 **5 methods × 5 benchmarks = 25 个组合**的极小真实测试。每家都覆盖
单 worker、双 worker、BEAM 100K/10M 与 HaluMem operation-level；A-Mem 和 SimpleMem
各自形成 11 个正式真实 run。全部 run 均对 checkpoint、method state、worker 隔离、
public/private 边界、适用 evaluator 与 token/call observation 做了机器验货后冻结。

### 1.2 推进节奏

五家方法不是齐头并进，而是严格串行推进——而且明显越往后越快。这个节奏本身是本阶段
最重要的方法论结论：

| method | 大致耗时 | 说明 |
|---|---|---|
| LightMem | 约 4 天（07-15 → 07-18） | 第一个真正把 5 个 benchmark 跑穿的方法，第二节列的 benchmark 异常几乎全在这一轮暴露并处理 |
| Mem0 | 约 1-2 天（07-18 → 07-19） | 复用 LightMem 已压实的异常处理层，只需处理 Mem0 接口自身的差量 |
| MemoryOS | 1 天内（07-20） | 同样复用共享异常层，收尾最快 |
| A-Mem | 1 天内（07-23） | 切回官方通用产品仓库，确认 evolution 后检索指标边界并完成五格 11 run |
| SimpleMem | 1 天内（07-23） | 处理窗口顺序、LanceDB FTS 兼容、HaluMem session finalize 后完成五格 11 run |

LightMem 之所以慢，是因为它承担了**用一个方法把 5 个 benchmark 全部"压实"一遍**的
探路成本——所有隐藏在数据里的异常（第二节），都是在拿它逐格跑真实数据时才第一次
暴露出来的。这些异常一旦被发现并固化成共享处理规则，Mem0 和 MemoryOS 就站在现成的
地基上，只需要处理各自接口特有的差量，所以一两天就能收尾。这正是"慢就是快"：第一家
慢，是为了后面每一家都快。

后两家没有重新调查五份 benchmark 数据，而是直接复用已 source-locked 的 benchmark 稳定层，
只审 method-specific 输入、生命周期、readout 与指标资格；这验证了前期“第一家压实、后续摊销”
的推进方式。

---

<a id="s2"></a>
## 二、本周解决的"阻碍"

本阶段最大的时间消耗**不是写适配器代码，而是发现并处置各种隐藏问题**。它们有一个
共同特点：**静态阅读文档、甚至通读官方代码都发现不了，必须真正把 pipeline 跑起来、
逐条对账才会暴露**。而且大多数不会让程序崩溃——程序会"正常"跑完并给出一个看似合理
的分数，而这个分数是错的。这正是它们危险的地方。

我们把每一类都做成了确定性的兜底规则，写进对应的 adapter 与 evaluator，不依赖人工
记忆或事后补救。下面分两侧列出真实阻断过进展的例子；不影响结果、无需修改的合法边界
情况（例如 LongMemEval 中 `question_date` 早于全部 haystack 时间）不在此列。

<a id="s2b"></a>
### （benchmark 侧）数据本身的异常

### 2.1 LoCoMo：gold evidence 本身不可映射，指标上限不是 1.0

LoCoMo 的证据标注形如 `D<session>:<turn>`。Phase 1 排除 category 5 后共 2,355 个 raw
evidence token，其中 **9 个无法精确映射**到同一 conversation 的 canonical turn：

| 真实位置（qa 为零基下标） | raw evidence unit | 异常 |
|---|---|---|
| `conv-26 / qa[37]` | `D8:6; D9:17` | 两个 id 被分号挤进同一个 list 元素 |
| `conv-42 / qa[58]` | `D10:19` | 格式合法，但该 conversation 没有这个 turn |
| `conv-42 / qa[88]` | `D` | 缺 session 与 turn |
| `conv-43 / qa[18]` | `D:11:26` | session 位缺失且多一个冒号 |
| `conv-47 / qa[38]` | `D4:36` | 格式合法，但该 conversation 没有这个 turn |
| `conv-49 / qa[31]` | `D9:1 D4:4 D4:6` | 三个 id 被空格挤进同一元素 |
| `conv-49 / qa[38]` | `D22:1 D22:2 D9:10 D9:11` | 四个 id 被挤进同一元素 |
| `conv-49 / qa[46]` | `D21:18 D21:22 D11:15 D11:19` | 四个 id 被挤进同一元素 |
| `conv-50 / qa[69]` | `D30:05` | 前导零，真实 id 是 `D30:5` |


**隐蔽在哪**：这 9 个 token 混在 2,355 个正常 token 里，格式看起来都"像"合法 id
（`D10:19`、`D4:36` 完全符合正则），只有真正建立起 canonical turn 索引、逐条回查"这个
编号在对应对话里到底存不存在"时才会暴露。任何只做格式校验的检查都会放行它们。

另有两类同源问题：`conv-50 / qa[5]`（问题为 `What are Dave's dreams?`）的证据列表是
`['D4:5', 'D4:5', 'D5:5']`，**同一个 id 重复出现**——同一句话被标了两遍并不构成第二个
独立证据，但官方 raw scorer 会把它在分母里算两份，凭空拉低满分线。还有 4 道 category-3
推理题**有 gold answer 但证据为空**：

| 真实位置 | question | gold answer |
|---|---|---|
| `conv-26 / qa[30]` | `Would Melanie be considered a member of the LGBTQ community?` | `Likely no...` |
| `conv-26 / qa[46]` | `Would Melanie be considered an ally to the transgender community?` | `Yes, she is supportive` |
| `conv-50 / qa[39]` | `Would Dave prefer working on a Dodge Charger or a Subaru Forester?` | `Dodge Charger` |
| `conv-50 / qa[42]` | `Did Calvin and Dave have a Boston meeting in the given interval?` | `No` |

官方 evaluator 对空证据记 Recall=1.0。如果直接照做而不加披露，这 4 个满分会被误读成
"检索成功"，其实它们根本没有可检索的证据。

**框架处置**：不猜拆、不修前导零、不静默删除；不可映射的记 `unmatched` 并保留在分母，
重复 id 稳定去重，空证据题另外单独报 `empty_evidence_question_count` 与 non-empty 均值。
所有 gold 只走 evaluator-private 通道，绝不进入 method。

### 2.2 LongMemEval：对话结构不是标准的"一问一答"，存在部分瑕疵

LongMemEval 的 session 存在大量非交替结构。以下是 source-locked 数据中的真实例子：

```text
S / f8c5f88b / session[0]        # 开头连续两条 assistant
assistant: "Sure, here is an updated comprehensive page structure ... including fie"
assistant: "to restore default settings  8. Help Page: ..."

S / gpt4_2ba83207 / session[34]  # 结构化 role 全是 assistant，但正文里写着 User/Assistant/System
role=assistant, content="User\n\nI would like you to act as a counter..."
role=assistant, content="Assistant\n\nSure! Give me the number."
role=assistant, content="System\n\nThe user input is 2."

S / 352ab8bd / session[24]       # 连续三条 user，没有任何回复
user: "Let's play Dr. Jekyll and Mr. Hyde..."
user: "[Question] Is it okay to..."
user: "[Question] Alternative for Germany..."
```

规模不是个例：S 中有 **1,942 个 assistant 开头的 session**（M 中 19,431 个）、71 个纯
assistant session、1 个纯 user session、32 处相邻同 role 出现。

**为什么这是阻碍**：很多记忆方法默认对话是"用户问一句、助手答一句"交替进行的，并以
这个"对"为单位切分、存储记忆。真实数据大面积不满足这个假设，方法要么直接崩溃，要么
更糟——**静默错配**，把上一轮的 assistant 和下一轮 user 硬凑成一对，导致记忆的来源
归属整个错乱。这直接卡死了 method 侧那个接口陷阱（见 2.5）。

**隐蔽在哪**：`gpt4_2ba83207` 这个例子尤其典型——正文里明明白白写着 `User\n\n`，但
结构化 `role` 字段却是 `assistant`。如果凭正文里的字样去猜角色，就会"修"出一个和官方
评测不一致的数据集；而老老实实信结构化 role，又得接受这种看着别扭的异形。我们的裁决
是**信结构化 role**，把根因记为"待考"。

### 2.3 MemBench：时间戳有两种格式，而且大批量缺失

MemBench 把时间和地点写在 message 正文尾部，存在两种真实格式：

```text
I'm looking for a wonderful movie to watch.
(place: New York, NY; time: '2024-10-01 08:00' Tuesday)     # 有冒号

(place: Boston, MA; time'2024-10-01 08:00' Tuesday)          # 无冒号
```

`0-10k ThirdLow` 的 **19,285 条 message 全部使用第二种无冒号格式**。若 parser 只认
`time:`，这一整批的时间会全部丢失。100k 规模又引入大量**没有时间尾注的噪声消息**：

| source | 无时间 step | 有时间 step |
|---|---:|---:|
| FirstHigh | 42,000 | 3,133 |
| FirstLow | 108,000 | 41,777 |
| ThirdHigh | 24,000 | 1,049 |
| ThirdLow | 84,000 | 3,779 |
| **合计** | **258,000** | **49,738** |

**为什么这是阻碍**：时间是记忆系统回答"什么时候发生了什么"这类问题的核心检索维度。
一整批消息的时间被静默丢掉，程序不会报错，只会让这批记忆在时间相关的问题上永远
检索不到——最后表现成"这个方法在 ThirdLow 上效果差"，而真实原因只是我们的 parser
少认了一种格式。这种"错误伪装成结论"的情况，是最容易得出错误科研结论的。

**隐蔽在哪**：两种格式只差一个冒号，随手抽几条样本大概率抽到有冒号的那种。而且 84%
的 100k 消息本来就没有时间，"很多消息没时间"看起来像是数据集的正常特征，根本不像
bug。我们的处置是：用完整结构正则同时识别两种写法，真缺时的显式保留为 `None`，
**绝不从相邻消息、问题时间或墙钟造一个假时间**——造假时间会让方法拿到一个看似完整、
实则错误的时间轴，比缺时间更糟。

gold 侧还有两类确定性异常。一是 `target_step_id` 越界（target 为 0 基，等于消息总数即越界）：

```text
0-10k FirstLow / comparative/events / tid=4    len(message_list)=111, target_step_id=[98, 111]
100k  FirstLow / comparative/events / tid=4    len(message_list)=411, target_step_id=[398, 411]
```

二是完全缺失检索 gold：

```text
0-10k FirstHigh / highlevel_rec/movie / tid=25
question: According to the movies I mentioned, what kind of movies might I prefer to watch?
target_step_id: []
ground_truth: B (Comedy)
```

这道题能算官方选择题准确率，但没有任何检索 qrel。框架对检索指标写
`score=None / status=n/a`，既不送 1.0 也不记 0.0——它就是不可评，诚实标注，不硬凑。

### 2.4 BEAM：消息 id 会重复，直接用它当身份会覆盖数据

BEAM 的 1M 规模中，有 4 个 conversation 会在后续 session 从 raw `id=0` 重新编号：

| 1M row / conversation | 重复的 distinct raw id 数 | 重复范围 |
|---|---:|---|
| `4 / conversation 5` | 150 | `0–149` |
| `25 / conversation 26` | 424 | `0–423` |
| `32 / conversation 33` | 206 | `0–205` |
| `33 / conversation 34` | 940 | `0–939` |

合计 **1,720 个 raw id 各出现两次**。

**解决办法**：框架改用 `{session_id}:t{turn_index}` 作为身份（10M 用
`pN:sM:tK`），gold 若只给出歧义 raw id，就展开成包含全部候选的 any-of 组，绝不猜一个。

同一批还发现：`conversation=7 / plan-1 / batch 1` 的 244 条 message 时间锚全为 `None`；
10M 有 5 处相邻 session 时间倒退（如 conversation 3 从 `2024-07-15` 回到 `2024-07-02`）；
10M row 5 的 `probing_questions.event_ordering[0].source_chat_ids[6][0]` 是非法字符串
`'--'` 而非消息 id。框架保留倒退顺序不重排、把 `'--'` 建成 unmatched 组并计数。

<a id="s2m"></a>
### （method 侧）接口的陷阱

benchmark 侧异常是"数据不听话"，method 侧问题则是**"接口说的和它实际要的不一样"**。
这类问题比数据异常更隐蔽：官方文档、类型签名、甚至 docstring 都不会告诉你真实约束，
只有真跑真实数据才会暴露。

### 2.5 LightMem：接口看似很"自由"，实际要求严格配对

`add_memory(messages)` 的签名接受 `dict` 或 `list[dict]`，文档描述为
"Add new memory entries from message history"，看起来可以传任意条消息。

**实际约束**：传入的 list 必须是**偶数条、user/assistant 严格交替、且 user 在前**。这个
约束不写在签名、文档或任何校验里，而是硬编码在抽取结果的回写逻辑中——抽取 LLM 返回的
`source_id` 是**第几个 user 消息**（`lightmem.py:369` 按 `role == "user"` 计数），而回查
时间戳与说话人时直接这样用：

```python
sequence_n = source_id * 2        # memory/utils.py:379
time_stamp = timestamps_list[sequence_n]
speaker_info = speaker_list[sequence_n]
```

`× 2` 就是"user 在偶数位、assistant 在奇数位"这个假设的全部依据。

**为什么这是阻碍**：把 2.2 的 LongMemEval 数据（大量 assistant 开头、连续同 role、纯
user session）接到这个接口上，几乎每一类异形都会踩中这个下标假设。更麻烦的是它**大
部分时候不崩溃**——`× 2` 照样能取到某条消息，只是取错了，于是抽出来的事实被安上了
另一条消息的时间和说话人。这是本阶段排查耗时最长的一个问题，因为它给出的是**错误
数据而不是错误信号**：一切看起来都在正常运行。

**隐蔽在哪**：签名说它接受任意 `list[dict]`，docstring 说它处理 message history，没有
任何一处校验会拒绝不配对的输入；真正的约束藏在一个 `× 2` 里。LightMem 官方只在
LoCoMo 上测过，而它处理 LoCoMo 的姿势恰好是每条 utterance 单独配一个空 assistant，
天然满足"偶数配对"，所以上游从来没被这个问题绊倒过——直到我们把它拓展到别的 benchmark。

**框架处置**：在 adapter 层做结构规范化，用**空内容 placeholder** 补齐落单的一侧（末尾
落单 user 补 placeholder assistant，assistant 开头补 placeholder user），placeholder 带
内部标记、镜像同 pair 真实消息的时间与说话人，且**绝不跨 session 配对**。每个真实 turn
恰好出现一次，不重不漏。代价必须诚实披露：这导致 LightMem 的抽取 source id 是 pair 级
而非 turn 级，因此它在 LongMemEval 上的 Recall 与排序指标判为 **N/A**——不可测就是
不可测，不拿近似值充数。

### 2.6 Mem0：时间戳参数"看起来支持，本地版根本不吃"

Mem0 有一套很完整的官方文档，示例代码里能看到给记忆带上时间戳的写法，让人自然以为
"传入对话时间"是一等能力。但真相是**这个能力只在它的付费云平台版生效，我们用的
自托管开源版根本没有这个入口**。三处一手证据：

- 自托管 `Memory.add()` 的完整签名（`mem0/memory/main.py:573`）只有
  `messages / user_id / agent_id / run_id / metadata / infer / memory_type / prompt`
  ——**没有 `timestamp` 参数**；
- 自托管 REST server 的 `MemoryCreate` 请求模型（`server/main.py:178`）里也没有时间字段；
- 只有云平台客户端 `MemoryClient` 那条路径才在文档里出现 `timestamp`。

如果记忆丢掉时间，一大类时间推理题直接没法答。而 Mem0 的开源版会默认把入库时间记成**当前墙钟**（也就是我们跑实验的那一刻），
与对话里真正的历史时间毫无关系——没察觉的话，等于给每条记忆都盖了个错误的时间戳，
而且不报任何错。

**框架处置**：把时间戳拼接在content内容里面。

---

<a id="s3"></a>
## 三、benchmark 拓展与指标拓展

上一节是"被动排障"。这一节是本阶段主动做的工作：**让原本只支持部分 benchmark、部分
指标的方法，能够公平地参与全部评测**。原则是硬的：**只做不改变算法核心流程的最小
改动**，每一处都记录文件、位置与理由；凡是需要绕过方法自身机制才能拿到的指标，一律
不做。

### 3.1 benchmark 拓展：官方大多只测过 1-2 个，我们扩到 5 个

| method | 官方仓库测过的 benchmark | 我们扩展的 |
|---|---|---|
| LightMem | LoCoMo、LongMemEval | MemBench、BEAM、HaluMem |
| Mem0 | LoCoMo、LongMemEval、BEAM | MemBench、HaluMem |
| MemoryOS | LoCoMo | LongMemEval、MemBench、BEAM、HaluMem |
| A-Mem | LoCoMo | LongMemEval、MemBench、BEAM、HaluMem |
| SimpleMem | LoCoMo、LongMemEval、MemBench | BEAM、HaluMem |

五家拓展均已完成真实 smoke 验收。

### 3.2 拓展的隐藏难点：会踩到官方从未跑过的代码路径

把一个方法拓展到它官方没测过的 benchmark，往往不是配置层面加个开关那么简单——benchmark
的新用法会直接激活方法内部**从未被官方评测执行过的代码**，而那些代码可能带着从没被
发现的 bug。下面是拓展 LightMem 到 HaluMem 时的真实例子。

HaluMem 要求在每个 session 结束时强制刷洗缓冲区（`force_segment=True`）。真跑起来时，
**第二个 session 直接崩溃**：

```text
session1_segments= [[('user','u1'),('assistant','a1')], [('user','u2'),('assistant','a2')]]
after_session1_buffer= [('assistant','a1'), ('user','u2'), ('assistant','a2')]   # 应为空
session2_error= IndexError list index out of range
```

定位到上游两处状态记账错误：一是强制刷洗后，清理游标误用了 `boundaries` 的长度而非
buffer 的消息数（`start_idx = len(boundaries)` 应为 `len(self.buffer)`），导致缓冲区
没被清空，上一个 session 的消息泄漏进下一个 session；二是同一次调用中，自动分段的
结果被强制分段的结果**整体覆盖**而不是追加，丢失已产出的段。

**为什么这是阻碍**：这一条直接把 LightMem × HaluMem 阻断了数天。而且第一个问题不止是
崩溃——它是**跨 session 的记忆泄漏**，即使不崩溃也会污染实验隔离性（这个 session 的
记忆里混进了上个 session 的内容）。

### 3.3 指标拓展之一：让方法支持 Recall@K

Recall@K 要回答"这条被检索出来的记忆，来自哪几个原始 turn"。但有的记忆系统会把原文经 LLM
抽取、改写、合并成新的记忆条目，这条"记忆→原始出处"的血缘默认是断的。

我们按各方法的接口能力分别做了最小改造：

| method | 血缘回收方式 | 改动量 |
|---|---|---|
| Mem0 | `add()` 会返回每条记忆的原生 id → adapter 维护 `记忆 id → 原始 turn id` 的 sidecar；`search()` 返回 id 后查表 | 零改动（用官方已有返回值） |
| MemoryOS | 把原始 turn id 直接写进 page 自带的 metadata 字段；检索时从返回 page 的 metadata 里读回（原理同 Mem0，靠 id 不靠文本） | 零改动 |
| LightMem | 上游抽取本就让 LLM 逐条返回 `source_id`，但构造记忆条目时把它丢弃了；改为透传保留 | 最小 diff：多留一个可选字段 |

sidecar 采用原子写入并带 schema 版本，遇到没有血缘的旧状态**直接拒绝续跑**，不静默降级。

**同时诚实标注不可测的格**：LightMem 在 LongMemEval 上因 pair 化处理，抽取 source id
只能定位到 pair 而非具体 turn，Recall 与排序判为 **N/A**；Mem0 在 BEAM 上同理；
SimpleMem 把窗口语义融合成新的 MemoryEntry，没有逐条出处，Recall 全面 N/A；A-Mem
向量检索命中的是 evolution 后的当前 memory，而不是原始 dataset turn，note id/sidecar
只能证明生成 lineage，不能据此把当前 memory 当作原始 evidence。因此 A-Mem 的
Recall@K/Precision@K/NDCG 也判 N/A。N/A 是方法能力边界，不是接入失败，更不能用 0 分代替。

### 3.4 指标拓展之二：让方法支持 HaluMem 的 session 级记忆抽取

HaluMem 要评测"这个 session 里新抽取出了哪些记忆点"，但几乎没有方法提供"本次 session
新增了什么"的查询接口——产品接口通常只能返回记忆库的全量视图。

我们在协议层新增了 `SessionMemoryReport`：方法在 session 边界报告本 session 实际新增的
记忆。各家按自身能力实现：Mem0 复用 `add()` 的返回值；LightMem 在强制刷洗时旁听实际
插入的条目（3.2 的 bug 就是在实现这一条时暴露的）；A-Mem 上报该 session 新增的官方
MemoryNote；SimpleMem 在 session 边界调用 `finalize()`，上报本段新合成 MemoryEntry，只清
下一窗口参考用的 transient `previous_entries`，不清长期 LanceDB。最后两家真实 HaluMem
run 均覆盖 extraction、update、QA、question type 与 Event/Persona/Relationship memory type。

### 3.5 新增的通用指标内核

本阶段还完成了 7 个通用指标内核（公式只做纯计算，不读取具体 benchmark 或 method）：
Normalized Exact Match、Directional Substring EM、Token-F1、Precision@k、Recall@k、
ROUGE-L、BLEU-1。

---

<a id="s4"></a>
## 四、小结与下一步

**本阶段的主要产出不是"跑出了分数"，而是"证明了分数可信"。** 上面每一条异常，如果不
发现、不处置，都足以让最终数字失真而不留任何痕迹——程序照常跑完，报告照常生成，只是
结论是错的。这也是本阶段节奏"先慢后快"的原因：LightMem 用一整轮把 5 个 benchmark 的
异常全部压实，后面的 Mem0、MemoryOS 才能站在现成规则上快速收尾。

**下一步**：

1. 按下面第 4.1 节的方法，产出全量实验的预算估算表（作为与导师讨论全量预算的申请材料）；
2. 接入剩余 5 个尚无适配器的方法，队列如下：

   - MemOS
   - Letta / MemGPT
   - LangMem
   - Supermemory
   - EverOS


### 4.1 关于成本估算

本阶段跑的是 **smoke**——每格被裁剪到 1 个 round + 1 个 question（极小测试），目的只有一个：验证
"方法 × benchmark"这条流水线接线通不通、隔离干不干净、artifact 对不对。它**不能用来
估算成本**：裁得这么小，token 量、检索规模、抽取次数都不具代表性，拿它做线性外推只会
得出一个严重失真的数字，误导预算判断。

成本估算需要另一条专门的路径，等 5×10 的极小测试全部跑通后再进行小规模预算测试：对每个
"方法 × benchmark"完整跑**一整个 conversation**（它全部的 turn 与全部 question，不裁剪），
用效率插桩逐调用采集 build / retrieve / answer 三阶段的真实 token 与调用次数，得到"每对话
真实成本"；再用它乘以该 benchmark 的对话总数外推到全量，汇成全矩阵估算表，配 ohmygpt
实价折算成人民币，并标注外推假设与误差区间。之所以放在极小测试跑通之后，是先确认每格
都能正确跑起来，再花钱测"每格跑一整个对话要多少钱"，避免在有 bug 的流水线上烧成本。

1. **测每对话成本**：对每个"方法 × benchmark"，完整跑**一整个 conversation**（它全部的
   turn 与全部 question，不裁剪），如实记录 build / retrieve / answer 三阶段的真实 token
   与调用次数——效率插桩已经在逐调用采集这些字段，不是估算；
2. **按规模外推**：用"单对话真实成本 × 该 benchmark 的对话总数"推出该格的全量成本，
   再汇总成 5×10 的全矩阵估算表，配上 ohmygpt 实价换算成人民币；

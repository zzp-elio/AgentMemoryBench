# MemBench Dataset 异常情况与处置账

> 状态：dataset 事实已由架构师复核；LightMem pair 投递 R1 已强验收，真实 B11 待跑；复核日期：2026-07-19
> canonical data：`data/membench/Membenchdata/data2test/{0-10k,100k}/` 下 8 个正式文件
> 数据身份：[`membench-source-lock.json`](../../workstreams/ws02.6-first-smoke-hardening/notes/membench-source-lock.json)

本文记录当前 source-locked MemBench 数据的异常、合法 edge case 与框架处置。schema 摘要见
[`datasets/membench.md`](../datasets/membench.md)，统一运行流程见
[`workflows/membench.md`](../workflows/membench.md)。8 个文件的 SHA-256 已于 2026-07-19
独立重算，与 source lock 全部一致；文件身份变化后，本页所有计数自动失效。

## 1. 总览判词

| 编号 | 形态 | 类型 | 规模 | 框架裁决 | LightMem 差分 |
| --- | --- | --- | ---: | --- | --- |
| M-S1 | FirstAgent 一个 step 是 `{user, agent}`；ThirdAgent 一个 step 是 string | 官方 schema | 314,830 / 137,415 steps | FirstAgent 展开成两个 canonical child；ThirdAgent 保持一个 user child | FirstAgent 用一个真实双边 pair；ThirdAgent 用单边 pair + placeholder |
| M-T1 | `time:` 与 `time'` 两种尾注格式 | 官方生成器漂移 | 无冒号仅 0-10k ThirdLow 19,285 条 | 正则兼容两态；原文不改 | typed `time_stamp` 同时填入 |
| M-T2 | 100k noise 无 place/time 尾注 | 设计特性/能力限制 | 258,000/307,738 source steps | `turn_time=None`，不造时间 | `preserve_none`，不丢 noise |
| M-T3 | 相邻带时 step 时间倒序 | 数据时间线异常 | 39 处 | 保留原顺序与各自 source time，不排序/修钟 | 同上；method-derived tie-break 不冒充 source time |
| M-Q1 | `QA.time` 自带前导单引号和 weekday | 官方 schema | 4,260/4,260 questions | 原样映射为 `question_time`，只进 query/answer builder | 不得回填 history turn |
| M-G1 | `target_step_id == len(message_list)` | gold off-by-one | 2 questions | 建 unmatched group、留在分母、恒 miss | gold 私有，无 method 特判 |
| M-G2 | `target_step_id=[]` | gold 缺失 | 1 question | retrieval metric 记 N/A，不伪造 1.0/0.0 | gold 私有，无 method 特判 |
| M-A1 | answer 为 list、极短或长文本 | 合法 answer 形态 | 280 list；17 个长度≤2；224 个长度≥300 | 选项文本统一字符串化；choice accuracy 只判 A-D | 无 |
| M-L1 | 单条 source message 很长 | 合法压力形态 | 最大 7,236 chars | 不截断数据；真实 full 再观测 token/cost | 不作为付费 smoke 必塞异常 |

## 2. 数据身份与全量结构

8 个正式文件的现场总数是 **4,260 trajectories / 452,245 source steps /
767,075 canonical turns**，不是早期草稿写的 5,080 trajectories：

| variant / source | trajectories | source steps | canonical turns |
| --- | ---: | ---: | ---: |
| 0-10k FirstHigh | 700 | 15,450 | 30,900 |
| 0-10k FirstLow | 900 | 104,470 | 208,940 |
| 0-10k ThirdHigh | 400 | 5,302 | 5,302 |
| 0-10k ThirdLow | 1,400 | 19,285 | 19,285 |
| 100k FirstHigh | 140 | 45,133 | 90,266 |
| 100k FirstLow | 360 | 149,777 | 299,554 |
| 100k ThirdHigh | 80 | 25,049 | 25,049 |
| 100k ThirdLow | 280 | 87,779 | 87,779 |

全量 census 还确认：0 个缺 `user`/`agent` key、0 个空或纯空白 message、0 个空
`message_list`、0 个文件内重复 `tid`、0 个 QA 必填字段缺失。canonical adapter 全量复算为
`user=452,245`、`assistant=314,830`，session 内 turn id 零重复，step→child group 映射零缺失。

### M-S1：pair-step 与 string-step 不能混成同一种源单位

**FirstAgent 真实例子**：任一 dict step，例如
`0-10k/FirstAgentDataHighLevel / highlevel/movie / tid=0 / step[0]`，同时有真实 `user` 与
真实 `agent`。canonical 层按源顺序展开为 `1:user`、`1:assistant`，gold 仍把它们视作同一个
官方 step group，命中任一 child 只计一次。

**ThirdAgent 真实例子**：
`0-10k/ThirdAgentDataLowLevel / simple/roles / tid=0 / step[0]` 是一个 string observation，
canonical 层只生成 user turn。连续 string 仍是多个独立 source steps，不能把两个 user
错误拼成一组 user/assistant。

**框架处置**：canonical adapter 维护显式 step→child 映射；下游不得解析 turn-id 字符串反推
源 step。需要 pair 形接口的 method，由事件聚合器把相邻 `user -> assistant` 闭合；连续 user
各自成为 dangling singleton，再由 method 的 structural placeholder 补空 assistant。

## 3. 时间与地点

### M-T1：两种尾注格式

常见格式：

```text
(place: Boston, MA; time: '2024-10-01 08:00' Tuesday)
```

0-10k ThirdLow 的 19,285 条全部是官方生成器留下的无冒号格式：

```text
(place: Boston, MA; time'2024-10-01 08:00' Tuesday)
```

生产正则 `time:?\s*'YYYY-MM-DD HH:MM'` 同时解析两态。**canonical content 原样保留完整
place/time 尾注**；解析只额外产生 typed `turn_time`，不删除、重写或重复前置源文本。
LightMem 等 typed-timestamp method 收到同一原始 content，并把 `turn_time` 写入独立
`time_stamp` 字段。两条通道承载同一 source fact，不得把结构化字段当成删除原文的理由。

### M-T2：100k no-time noise

精确的“有时间”定义是能匹配上述完整尾注正则，不能只查正文里是否出现普通英文单词
`time`。按 source step 统计：

| 100k source | no-time steps | timed steps |
| --- | ---: | ---: |
| FirstHigh | 42,000 | 3,133 |
| FirstLow | 108,000 | 41,777 |
| ThirdHigh | 24,000 | 1,049 |
| ThirdLow | 84,000 | 3,779 |
| **合计** | **258,000** | **49,738** |

因此 no-time 占 100k source steps 的 83.84%；展开 FirstAgent 双侧后，是 408,000/
502,648 canonical turns。早期草稿的 41,983、107,971、23,978、83,949 是把 noise 正文中
自然出现的单词 `time` 误当成 metadata marker，不能作为结构化时间统计。

**框架处置**：no-time message 的 `content` 原样保留，`turn_time=None`，MemBench 没有可用的
session source time，因此 `session_time=None`。不得从兄弟 user/assistant、前后消息、
`QA.time` 或 wall clock 回填；也不得先过滤 noise 再让 method 跑。

### M-T3：39 处 source-step 时间倒序

这里只比较相邻的**带完整时间尾注** source step；中间无时间 noise 不参与伪造比较。独立复算
分布：

| 文件 | 倒序数 | 代表位置 |
| --- | ---: | --- |
| 0-10k FirstHigh | 3 | `highlevel_rec/movie/tid=47 step20→21`：20:53→18:32 |
| 0-10k FirstLow | 7 | `simple/roles/tid=9 step142→143`：19:23→17:34 |
| 0-10k ThirdHigh | 2 | `highlevel/emotion/tid=12 step2→3`：08:02→07:50 |
| 0-10k ThirdLow | 21 | `simple/events/tid=0 step2→3`：20:17→19:06 |
| 100k FirstHigh | 0 | — |
| 100k FirstLow | 3 | `simple/roles/tid=9 step403→422`：19:23→17:34 |
| 100k ThirdHigh | 1 | `highlevel/emotion/tid=12 step224→225`：08:02→07:50 |
| 100k ThirdLow | 2 | `simple/events/tid=0 step8→9`：20:17→19:06 |

**为什么异常**：source list 顺序与文本尾注的时钟顺序不总一致；它会击穿“历史严格按时间递增”
的假设。但没有 owner 证据说明应按时间重排，也不能认定哪一个时刻才是“正确值”。

**框架处置**：保留官方 list 顺序、每条 source time 与 content；不排序、不修钟、不删除。
LightMem normalizer/sequence 产生的 offset 只能解释为 method-derived order time，不能覆盖或冒充
source timestamp。标准 smoke 不保证抽中倒序例；本异常由 census + deterministic regression
锁定，不强塞付费 smoke。

### M-Q1：question time 与 history time 是两条单向通道

4,260 个 QA 全部有类似 `'2024-10-01 08:13' Tuesday` 的 `QA.time`，前导单引号是当前官方
数据的一部分。adapter 原样映射到 `Question.question_time`。

官方 `third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py` 的
`INSTRUCTION_FIRST` 明确包含：

```text
Question: (current time is {time}) {question}
```

框架 unified answer builder 与该模板逐字 parity，并用公开 `question_time` 填 `{time}`。
反方向严格禁止：question time 不进入任何 history turn/session，不给 no-time noise 造时间。

## 4. Evaluator-private gold 异常

本节字段绝不可达 method ingest、retrieve 或 answer prompt。

### M-G1：两例越界 target

| variant / source | 稳定位置 | source steps | 异常 target |
| --- | --- | ---: | ---: |
| 0-10k FirstLow | `comparative/events/tid=4` | 111 | 111 |
| 100k FirstLow | `comparative/events/tid=4` | 411 | 411 |

官方 target 是 0 基，因此 `target == len(message_list)` 恰好越界一格，疑似 1/0 基 off-by-one。
框架不猜它原本想指哪一步：Gold Evidence Group v1 建
`mapping_status="unmatched"`，该 unit **保留在分母并恒 miss**。早期草稿“跳过”会美化分数，
已判定错误。

### M-G2：一例空 target

**位置**：`0-10k FirstHigh / highlevel_rec/movie / tid=25`，35 source steps，
`target_step_id=[]`。

它有正常 MCQ answer，但没有可评分 retrieval qrel。框架将该题的 retrieval metric 记为
`score=None/status=n/a`，仍保留在总问题数与 status count；不得把它记作自动命中 1.0，也不得
记作 method 失败 0.0。answer-level choice accuracy 仍可正常计算。

## 5. 合法但需要保真的 answer/长度形态

- 280 个 `answer` 是 list：0-10k FirstLow 200，100k FirstLow 80。它们是推荐类选项内容，
  不是多标签 ground truth；官方 `ground_truth` 仍是单个 A-D。
- 17 个字符串 answer 长度不超过 2；224 个 answer 的字符串表示长度至少 300，最长 1,438。
  这影响某些自由文本 metric 的适用性，不影响 MemBench 官方 choice accuracy。
- 最长单 message 为 7,236 chars；代表位置包括
  `100k ThirdHigh/highlevel/emotion/tid=13 step304` 与
  `100k ThirdLow/conditional/events/tid=6 step218`。它是压力形态，不是 schema 错误。

框架不截断或改写这些值。真实 full run 的 token/API/latency 只能用完整实验单元的真实
efficiency observation 外推，不能从 step 数或文本长度猜调用次数。

## 6. 四层覆盖：为什么付费 smoke 不必抽中每个异常

“覆盖异常”不是只靠一次 smoke。四层各自回答不同问题：

1. **全量 census**：扫描 8 个文件，证明异常到底有多少、在哪里；适合 39 处倒序、2 个 OOB、
   1 个空 target 这类稀有事实。
2. **deterministic unit/contract test**：用真实例或最小强反例锁住 parser、pair、None、分母和
   隐私边界；它稳定、免费，失败能精确定位。
3. **registered production-path probe**：走真实 adapter → event aggregator → method adapter →
   artifact/evaluator 装配，但用 fake/local backend，专门抓“helper 单测绿、真实接线却错”的 bug。
   本轮正是这一层发现 LightMem × MemBench 被误配成 `turn`。
4. **真实 B11 smoke**：只验证真实模型/Qdrant/API/并发/artifact 链能工作，不承担全库异常抽样、
   效果结论或成本估算。没抽中某个稀有异常，不等于前三层没有覆盖它。

这四层不是“降低验收”，而是把不同风险交给最能稳定证明它的证据层；否则每次付费 smoke 都要
塞遍所有异常，成本高且仍无法证明全库计数。

## 7. LightMem 差分与 smoke 边界

LightMem 的稳定目标契约：

- `messages_use="hybrid"`；FirstAgent 的 user/assistant 两个真实 child 在同一个 pair batch；
- ThirdAgent 每个 user-only source step 独立成单边 pair，补空 assistant placeholder；placeholder
  不进入 extraction prompt/token count，也不制造第二个 source id；
- 每条 message 的原始 place/time content 保留，同时把其自身解析出的时间写入 `time_stamp`；
- no-time noise 写 `time_stamp=None`；question time 只进 answer builder；
- 不跨 source step、session、trajectory 合并 lineage；局部 child id 可在不同 trajectory 重复，
  隔离依靠 run/conversation namespace 与独立 backend state，不靠伪造全局 id。

标准 0-10k smoke 四源各取首条，天然覆盖 First/Third 两种 role shape、colon/no-colon 两种格式、
question-time answer builder 与真实 backend 基本链路。它不覆盖 100k no-time noise、39 处倒序、
OOB/空 gold；这些分别由前三层与 evaluator-private tests 覆盖。pair R1 与本地 None 强反例
现已通过，100k 付费 sentinel 不再是 B11 前置 blocker；100k full 到站时仍需按其独立 variant 运行，
不能把 0-10k 结果冒充 100k。

## 8. 回归锚、原草稿勘误与失效条件

当前回归入口：

- `tests/test_membench_conversation_adapter.py`：pair split、双时间格式、content 保真、None 与
  question/history 单向边界；
- `tests/test_membench_unified_prompt.py`：官方 answer prompt 逐字 parity 与 question time；
- `tests/test_membench_retrieval_recall.py`：OOB unmatched 留分母、empty target=N/A；
- `tests/test_membench_registered_prediction.py`：四源 registered path、artifact 与私有字段隔离；
- LightMem method 差分最终以本次 R1 implementation note 与 `integration/lightmem.md` 为准。

对 OpenCode 初稿的承重勘误：

1. `5,080 trajectories` → **4,260**；
2. OOB target “需跳过” → **unmatched 留分母、恒 miss**；
3. 100k 缺时间的 41,983/107,971/23,978/83,949 → **精确 source-step 计数
   42,000/108,000/24,000/84,000**；旧值误把正文里的普通 `time` 当 marker；
4. 39 处倒序、19,285 条 no-colon、4,260 个 QA.time 前导引号、280 个 list answer、17 个
   极短 answer 与 224 个长 answer，经独立重算成立并保留。

任一数据文件 hash、canonical step→child contract、Gold Evidence Group contract、event pair
aggregator、LightMem timestamp/placeholder 行为或官方 answer prompt 改变时，必须重开本页。
actor 回报或单次 smoke 为绿不能自动改变 dataset 事实状态。

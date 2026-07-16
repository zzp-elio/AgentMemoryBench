# MemBench 100k message / question 时间语义裁决

> 日期：2026-07-15。裁决者：GPT-5 架构师。
> 性质：本地官方仓库 + 真实 100k 四源数据 + 当前生产调用链的一手审计；零 API。

## 1. 结论

**禁止把 `QA.time`、第一条有时间的 message、运行墙钟或人造递增值当成无时间
message 的 timestamp。** 当前代码没有把 `QA.time` 直接写进 Turn，但会把首个可解析
message 时间提升为伪 `session_time`；事件流随后让所有无时间 turn 继承它。这同样是
语义伪造，必须删除。

现行映射采用**公开原文 + 结构化旁路双通道**：

- message 文本内真实存在 `time: 'YYYY-MM-DD HH:MM'` 或 `time'…'`：包含 `place` 与
  `time` 的 content 原文不改，并可额外无损结构化为该 turn 的 `turn_time`；
- message 文本无时间：`turn_time=None`；
- MemBench trajectory 没有原生 session 时间：`session_time=None`；
- `QA.time`：只进入 `Question.question_time`，供官方 retrieval query 与 MCQ prompt。

结构化不是清洗或搬家。即使 method 支持独立 timestamp，它收到的 content 仍保留公开
文本里的 place/time；不支持独立 timestamp 的 method 也因此不会损失信息。这里是“原文
+ typed channel”两个接口通道，不是要求在同一 content 里再拼一遍时间。

## 2. 真实 100k 数据剖面

对 `data/membench/Membenchdata/data2test/100k/*.json` 四个官方采样文件逐 step 计数：

| 源文件 | step 总数 | 独立 `time` 字段 | 文本有 time marker | 文本无 time marker |
|---|---:|---:|---:|---:|
| FirstAgent HighLevel | 45,133 | 0 | 3,133 | 42,000 |
| FirstAgent LowLevel | 149,777 | 0 | 41,777 | 108,000 |
| ThirdAgent HighLevel | 25,049 | 0 | 1,049 | 24,000 |
| ThirdAgent LowLevel | 87,779 | 0 | 3,779 | 84,000 |
| **合计** | **307,738** | **0** | **49,738** | **258,000（83.84%）** |

计数只检查公开 message；未读取/利用 gold answer。timestamp 命中使用与生产 parser
同形的完整结构 `time:?\s*'YYYY-MM-DD HH:MM'`，不能用宽松的单词 `time` 搜索——自然语言正文也会出现
该词并造成假阳性。四份文件首条样本均为无 timestamp 的 noise，而 `QA.time` 非空，
足以构造“不得串字段”的强反例。

## 3. 官方流程

### 3.1 数据生成

官方 `benchmark/load_test_data.py` 会把有源时间的原始 message 格式化成文本：

- message noise：源 message 用 `time{}` 拼进文本（:52-57），noise 只取
  `i['message']`，不补时间（:59-63）；
- session noise：源 pair 用 `time{}` 拼进 user/assistant（:229-240），noise pair 只
  保留 user/assistant 文本（:243-246）。

所以 100k 不是“所有 message 都有时间”，也不是“所有 message 都完全无时间”：它是
有时间源 message 与无时间 noise 的混合流，且 schema 上始终没有独立 message time 字段。
无时间部分确属官方有意插入的 noise：README 将 `NoiseData` 定义为扩展 dialogue / information
flow 的噪声池；生成器只给原始 message 拼 place/time，noise 分支直接追加噪声文本，并只把
原始 `target_step_id` 重定位到新序列。gold evidence 因而不指向 noise；但不应进一步声称
任意噪声文本绝无偶然语义重合，评测契约只是把它们当 distractor。

### 3.2 运行时传参

- `benchmark/env/Membenenv.py:57-67`：历史阶段只返回
  `{'message': message_list[i]}`；到问题阶段才另返回 `QA.question/time/choices`。
- `benchmark/MembenchAgent.py:65-76`：message 原样拼 step 前缀后传给
  `memory.store()`，没有传 `QA.time` 或独立 timestamp。
- 同文件 :81-92：`QA.time` 只用于 `memory.recall(question + time)` 与 answer prompt。

因此官方行为明确支持字段隔离：question time 不是 message time。

## 4. 当前框架为何错

`src/memory_benchmark/benchmark_adapters/membench.py` 的逐 turn 解析本身是诚实的：
`_membench_turn_time()` 只从该 step 文本提取，未命中返回 `None`（:676-719）；
`_question_and_gold_from_qa()` 把 `QA.time` 单独写入 `Question.question_time`（:738-765）。

错误在 `_conversation_from_trajectory()`：:641-646 取“第一个带时间的 turn”作为整个
伪 session 的 `session_time`。随后 `runners/event_stream.py:41` 使用
`turn.turn_time or session.session_time`，使原本无时间的 258,000 个 step 获得了兄弟
turn 的时间。非空不等于真实；“兜底永不落空”是可运行性证据，不是语义正确性证据。

## 5. 架构裁决

1. **保留 lossless parsing 与原 content**：内嵌 place/time 本来就在所有 method 可见的
   公开 content 中；把 time 结构化到同一 Turn 不增加私有信息，也不改变或删减原文，属于
   benchmark-neutral additive normalization。支持独立 timestamp 的 method 也同时收到
   原 content，不做“既然拆字段就从文本删除”的去重。
2. **删除 sibling/session smear**：MemBench 的单 Session 只是统一 schema 包装，不是
   官方时间单元；不存在可供 turn 继承的真实 session time。
3. **question time 单向流动**：只允许 `QA.time → Question.question_time → retrieval
   query / answer prompt`；禁止反向流进 ingest。
4. **缺失保持缺失，但 `None` 能力逐 method 判定**：统一对象只陈述
   `Turn.turn_time=None`。下游 API 若真正接受 unknown/optional timestamp，可传 `None`
   或省略该参数；若硬性要求非空，应由通用输入需求门在 API/写入前拒绝实际不满足的
   数据切片，不能假设“字段存在且值为 None”就等于兼容。
5. **LightMem 100k 暂停**：官方 MessageNormalizer 要求 list 中每条 dict 带
   `time_stamp`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:62-99`）。
   它对 `None`/空值明确 raise，故 `time_stamp=None` 不能解决问题。0-10k 的源文本时间仍可
   无损解析；100k 的无时间 noise 不能诚实满足该契约。当前先修 benchmark 语义，随后另做
   method-neutral fail-fast Phase B；此前不得真实运行该格。
6. **A-Mem 与 LightMem 不可类推**：A-Mem 当前 runtime 的 `add_note(content, time=None)`
   可以调用，但 `MemoryNote` 会把缺失 time 换成本机 ingestion wall clock。这是 method-native
   创建时间，不是 benchmark source time；允许其按产品默认 ingest，但不得回写 Turn、冒充
   source-time parity 或作为 provenance 真值。相关运行披露纳入 Phase B 能力语义。
7. **content-only 单次渲染（2026-07-16 补充裁决）**：Mem0 之类 extraction 不消费独立
   timestamp 时，每条 message 只折入一个 effective timestamp：非空 `turn_time` 优先，只有
   turn 缺失时才 fallback 到真实 `session_time`，两者都缺则不加。MemBench 已内嵌 turn
   time/place 的 message 原样保留，禁止再加相同 `[Turn time]`。实现应由 benchmark adapter
   在公开 `Turn.metadata` 标记 source time 已嵌入，method renderer 读通用标记；禁止
   `if benchmark == "membench"`。BEAM/HaluMem 同时提供 turn/session 时只渲染 turn；LoCoMo/
   LongMemEval 只有 session 时保持现有 session header。

## 6. 施工分期

- **Phase A（已强验收）**：Opus 4.8 `0fbf8e1` 合入主线 `2e6b4d7`；架构师定向
  `31 passed in 3.68s`、主树 `1193 passed`、compileall exit 0。只修 MemBench adapter 的
  `session_time` 与测试，benchmark frozen-v1 已恢复。
- **Phase B（已强验收）**：LightMem `online_soft` preserve-none 主体与 explicit-None R1 已
  合入主线 `915f73c` + `3968373`；consolidated/summary 仍 require。A-Mem 的
  None→ingestion wall clock 只作 method-native 披露。
- **Phase C（当前）**：修复 Mem0 source-time renderer：MemBench 原文已带 time 时不双拼，
  普通 message 只按 turn→session fallback 折入一次；锁 first-person/third-person、带时/无时、
  turn+session、legacy/v3 两路径。局部重开 Mem0×MemBench/BEAM/HaluMem B4 输入形态，不改
  benchmark 时间解析、不改 Mem0 extraction/update/retrieve 算法。
- RetrievalEvidence M0 已于主线 `352ed3c` 起强验收落盘；它只负责 retrieval 事实，与本次
  ingest content 去重正交。

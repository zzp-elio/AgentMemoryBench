# MemBench 100k message / question 时间语义裁决

> 日期：2026-07-15。裁决者：GPT-5 架构师。
> 性质：本地官方仓库 + 真实 100k 四源数据 + 当前生产调用链的一手审计；零 API。

## 1. 结论

**禁止把 `QA.time`、第一条有时间的 message、运行墙钟或人造递增值当成无时间
message 的 timestamp。** 当前代码没有把 `QA.time` 直接写进 Turn，但会把首个可解析
message 时间提升为伪 `session_time`；事件流随后让所有无时间 turn 继承它。这同样是
语义伪造，必须删除。

现行映射：

- message 文本内真实存在 `time: 'YYYY-MM-DD HH:MM'` 或 `time'…'`：原文不改，并可
  无损结构化为该 turn 的 `turn_time`；
- message 文本无时间：`turn_time=None`；
- MemBench trajectory 没有原生 session 时间：`session_time=None`；
- `QA.time`：只进入 `Question.question_time`，供官方 retrieval query 与 MCQ prompt。

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

1. **保留 lossless parsing**：内嵌时间本来就在所有 method 可见的公开 content 中；
   把它结构化到同一 Turn 不增加私有信息，也不改变原文，属于 benchmark-neutral
   normalization。
2. **删除 sibling/session smear**：MemBench 的单 Session 只是统一 schema 包装，不是
   官方时间单元；不存在可供 turn 继承的真实 session time。
3. **question time 单向流动**：只允许 `QA.time → Question.question_time → retrieval
   query / answer prompt`；禁止反向流进 ingest。
4. **缺失保持缺失**：method 若不需要 timestamp，照常接收 `None`；method 若硬性要求
   每条 timestamp，应由通用输入需求门在 API/写入前拒绝实际不满足的数据切片。
5. **LightMem 100k 暂停**：官方 MessageNormalizer 要求 list 中每条 dict 带
   `time_stamp`（`third_party/methods/LightMem/src/lightmem/memory/lightmem.py:62-99`）。
   0-10k 的源文本时间仍可无损解析；100k 的无时间 noise 不能诚实满足该契约。当前先
   修 benchmark 语义，随后另做 method-neutral fail-fast Phase B；此前不得真实运行该格。

## 6. 施工分期

- **Phase A（已发卡）**：只修 MemBench adapter 的 `session_time` 与测试；不改 LightMem、
  registry、runner 或第三方代码。
- **Phase B（Phase A 强验收后再定卡）**：抽象 input requirement/preflight，按实际
  selected dataset 检查，而不是维护 LightMem × MemBench 100k 特判表。
- RetrievalEvidence M0 暂停到上述边界稳定；它负责 retrieval 事实，不负责把不能 ingest
  的 variant 伪装成可运行。

# MemBench 时间语义 Phase A 施工记录

> 日期：2026-07-15。actor：Opus 4.8（本会话为 actor 身份；架构师 GPT5.6 sol）。
> 范围：只恢复 MemBench benchmark 公共对象的真实时间语义 + 定向测试；零真实 API、
> 未跑全量、未 push。裁决依据：`membench-100k-time-ruling.md` §5。

## 1. 最终时间映射（本卡落地后）

```text
message 自身内嵌时间 ('time: '…'' 或无冒号 'time'…'') -> 同一 Turn.turn_time
message 无内嵌时间（含官方 NoiseData distractor）      -> Turn.turn_time = None
MemBench trajectory 无原生 session 时间                 -> Session.session_time = None
QA.time -> Question.question_time -> retrieval query / answer prompt only（单向）
```

- 逐 turn 内嵌时间解析（`_membench_turn_time` + `_MEMBENCH_TURN_TIME_RE`）**未改**：
  仍支持 `time: '…'`（有冒号）与 `time'…'`（无冒号）两种官方文本格式。
- content 原文**未改**：内嵌的 `place` 与 `time` 文字继续原样保留在所有 method 可见的
  公开 content 中；`turn_time` 只是从同一公开内容派生的 additive typed metadata，不做
  “拆字段就从文本删除”的去重。

## 2. 改动文件

| 文件 | 改动 |
|---|---|
| `src/memory_benchmark/benchmark_adapters/membench.py` | `_conversation_from_trajectory()` 删除“取首个带时间戳的 turn 作为伪 `session_time`”的 fallback（原 :641-646），构造 `Session` 时显式 `session_time=None`；改写注释/目标说明，去掉“保证 LightMem 不落空”这类过时目标，指向 ruling note §5。 |
| `tests/test_membench_conversation_adapter.py` | 删除旧 `test_membench_extracts_embedded_turn_time_and_session_fallback`（断言 `session_time == 首个 turn 时间`，已过时）；新增强反例套件 + 双格式解析测试；导入 `build_turn_events`。 |

**未改** LightMem / 其它 method、registry、runner 生产代码（含 `event_stream.py`）、
evaluator、TOML、third_party、README/status/spec/reference 文档、outputs。允许清单里的
`tests/test_membench_registered_prediction.py`、`tests/test_event_stream.py` 经核查
**无需改**（前者断言 per-turn `original_turn_time` 与 question_time-in-prompt，不依赖
session smear；后者测通用 `build_turn_events` 在显式 session_time 下的继承，仍正确）——
按卡要求 `git add` 时删去这两条路径，不制造空白改动。

## 3. 为什么无需改 runner 生产代码

`runners/event_stream.py:41` 是 `timestamp = turn.turn_time or session.session_time`。
一旦 adapter 把 `session_time` 显式置 None，无时间 turn 的 event `timestamp` 与
metadata `original_session_time` 自然变为 None，无需再动 runner。build_turn_events 行为
用 MemBench 测试内直接调用来锁定（见 §4 测试 2），不改 `test_event_stream.py`。

## 4. 定向测试（两种 message shape 的事件字段）

新增 / 保留的关键断言：

1. `test_membench_missing_message_time_stays_none_without_session_smear`（first-person
   dict + third-person str 双覆盖）：首条无时间 noise `turn_time is None` 且 content 逐字
   保留、未被过滤；次条 `turn_time == '2025-06-30 14:00'`（自身内嵌）且原文 place/time
   保留；`session.session_time is None`；`question_time == "'2099-12-31 23:59' Sunday"`
   （QA 未来日期，只进 question_time，与 message 时间明显不同）。
2. `test_membench_build_turn_events_keeps_missing_timestamp_none`：event1
   `timestamp is None`、`original_turn_time is None`；event2 `timestamp == '2025-06-30 14:00'`；
   两条 event `original_session_time is None`；`"2099" not in repr(event)`（QA 未来日期不进
   任何 event 字段）。
3. `test_membench_parses_both_embedded_time_formats_and_keeps_content`：`time: '…'` 与无冒号
   `time'…'` 都解析到 turn_time，且 message/place/time 完整子串逐字保留；`session_time`
   仍为 None（证明结构化是 additive，不触发兜底）。
4. 既有 `test_question_public_fields_and_private_gold_are_split` / 真实 canonical /
   registered offline probe 全链路继续通过（public/private 边界、smoke crop、注册 fake 不退化）。

fixture 刻意让 message time (`2025-06-30 14:00`) 与 question time (`2099-12-31 23:59`) 明显
不同，杜绝“错误串字段也能绿”。

### 自检命令与尾行

```
uv run pytest -q \
  tests/test_membench_conversation_adapter.py \
  tests/test_membench_registered_prediction.py \
  tests/test_event_stream.py
```

尾行：`31 passed in 3.70s`。

> 环境注记：全新 worktree 无 `data/`（`data/` 不入 git）。首跑 5 个 canonical/registered
> 用例因缺真实数据 FileNotFoundError；把主仓 `data/` 软链进 worktree 后 31 passed。软链
> 未 `git add`，不进提交。

## 5. LightMem / 100k 状态（明确不声称已兼容）

**未改 LightMem**。100k 的无时间 message 现为 `turn_time=None`；LightMem 官方
MessageNormalizer 要求每条 dict 带非空 `time_stamp`，对 `None`/空值 raise，故 100k 真实
运行仍被 **Phase B** 门暂停——本卡只恢复 benchmark 公共对象语义，不解决 method 侧输入需求
预检。A-Mem 亦未改（其 `time=None` 会内部生成 ingestion wall clock，属 method-native，
不回写 Turn），相关能力语义留 Phase B。

## 6. 偏差 / 停工点

无停工。唯一偏差是环境层面：为跑真实数据用例给 worktree 软链了主仓 `data/`（不入提交），
不属生产/scope 改动。允许清单内 `test_membench_registered_prediction.py`、
`test_event_stream.py` 实测无需改，按卡从 `git add` 剔除。

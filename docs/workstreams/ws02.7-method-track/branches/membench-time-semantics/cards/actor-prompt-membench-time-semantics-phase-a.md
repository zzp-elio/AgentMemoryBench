# Actor 卡：MemBench 时间语义 Phase A

> 派发日：2026-07-15。状态：**待用户选择跨模型 actor 派发**。
> 本卡本身就是可整份复制的 prompt；单批上限 5h、零真实 API、不 push。
> 白话目标：删掉“拿第一条有时间的 message 给整段无时间 noise 盖同一时间”的兜底；
> question time 继续只服务提问，message 缺时间就诚实保留 None。

## 0. 上工与隔离

按顺序只读以下最小集合：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部“Codex 恢复胶囊”；
3. 本卡全文；
4. `docs/reference/actor-handbook.md` §0-§4、§6-§8；
5. `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/
   membench-100k-time-ruling.md` §1、§3-§6；
6. `src/memory_benchmark/benchmark_adapters/membench.py::_conversation_from_trajectory`、
   `_membench_turn_time`、`_turn_from_step`、`_question_and_gold_from_qa`；
7. `src/memory_benchmark/runners/event_stream.py::build_turn_events`（只读）；
8. `tests/test_membench_conversation_adapter.py` 中现有时间测试。

从届时 `main` 新建；路径/分支已存在就停工，不删、不复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-membench-time \
  -b actor/membench-time-semantics main
cd /Users/wz/Desktop/mb-actor-membench-time
uv sync
```

允许修改：

- `src/memory_benchmark/benchmark_adapters/membench.py`；
- `tests/test_membench_conversation_adapter.py`；
- `tests/test_membench_registered_prediction.py`（只有既有真实路径断言需要同步时）；
- `tests/test_event_stream.py`（只有通用事件字段需要直接锁定时；优先在 MemBench 测试内
  调 `build_turn_events`，不为凑清单改文件）；
- 新建 `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/
  membench-time-semantics-phase-a-implementation.md`。

禁止修改 LightMem/其他 method、registry、runner 生产代码、evaluator、TOML、third_party、
README/status/spec/reference 文档、outputs。真实文件结构若迫使超出允许清单，停工，不自行
扩表。

## 1. 已裁语义

必须保持以下单向数据流：

```text
message 自身内嵌时间 -> 同一个 Turn.turn_time
message 无内嵌时间   -> Turn.turn_time=None
MemBench 原生无 session time -> Session.session_time=None
QA.time -> Question.question_time -> retrieval query / answer prompt only
```

保留 `_membench_turn_time()` 对 `time: '…'` 与 `time'…'` 两种官方文本格式的解析，
content 原文不改：原文本里的 `place` 和 `time` 必须继续一起交给所有 method；结构化
`turn_time` 只是 additive typed metadata，即使 method 支持独立 timestamp 也不得从 content
删掉重复的时间文字。不得把所有 `turn_time` 一刀切为 None；也不得引入 question time、
第一条 turn time、墙钟、文件 mtime、step index 派生时间或固定 epoch。

100k 的无时间 message 是官方 `NoiseData` 生成器有意插入的 distractor；它们保持原始无时间
文本和 `turn_time=None`。不要删除 noise、给 noise 补 place/time，或因 gold target 不指向
noise 就跳过 ingest。

## 2. 生产改动

在 `_conversation_from_trajectory()` 删除“取首个带时间 turn 作为 `session_time`”的
fallback，构造 MemBench `Session` 时显式保持 `session_time=None`。同步修正附近注释和
docstring，不留下“保证 LightMem 不落空”之类过时目标。

不要在本卡解决 LightMem 100k 兼容性，也不要修改 A-Mem。`time_stamp=None` 会被 LightMem
官方 MessageNormalizer 拒绝；A-Mem 虽接受 `time=None`，却会在内部生成 ingestion wall
clock。Phase B 会另设 method-neutral 的输入需求预检并区分这些语义；本卡只恢复 benchmark
公共对象的真实语义。

## 3. 必测反例

至少覆盖：

1. 同一 trajectory 的第一条 message 无时间、第二条有内嵌时间、`QA.time` 使用一个明显
   不同的未来日期：第一条 `turn_time is None`，第二条等于自身文本时间，
   `session_time is None`，`question_time` 只等于 QA 值；
2. 对上例调用 `build_turn_events()`：第一条 event `timestamp is None`，第二条只取自身
   `turn_time`；两条 `metadata["original_session_time"] is None`；任何 event 字段中都
   不得出现 QA 的未来日期；
3. first-person dict step 与 third-person str step 均覆盖，避免只修一类源；
4. 现有 0-10k 两种内嵌时间格式仍能解析；分别断言原 content 中完整的 message、`place`
   与 `time` 子串仍在，不能只断言时间字段；
5. 无时间 noise 的 content 逐字保留且 `turn_time is None`，不得被过滤；
6. question public/private 边界、smoke crop、registered fake 全链路不退化。

测试 fixture 必须让 message time 与 question time 明显不同，禁止二者写同一个值导致
错误串字段也能绿。

所有新增/修改的 Python 模块、类、函数、嵌套 helper 与测试函数都带中文 docstring。

## 4. 施工记录

新 note 记录：最终映射、改动文件、两种 message shape 的事件字段、定向测试尾行、偏差/
停工点。明确写“未改 LightMem，100k 真实运行仍被 Phase B 门暂停”，不得声称该格已兼容。

## 5. 明确不做

- 不改 `Question.question_time`、官方 MCQ prompt 或 retrieval query；
- 不删除逐 turn 的内嵌时间解析；
- 不实现 synthetic timestamp；
- 不改 LightMem、registry、provider protocol、manifest 或 resume；
- 不跑/扫描完整 572MB 100k 数据；架构师的一手计数已在 ruling note，单测用最小强反例；
- 不跑真实 API、全量 pytest 或 compileall。

## 6. 停工条件

- 删除 session fallback 会迫使修改允许清单外生产代码才能让定向测试通过；
- 发现 `QA.time` 在当前生产代码中另有进入 Turn/Session/event 的路径；
- MemBench 官方真实数据与 ruling note 的混合有时/无时结构矛盾；
- 定向测试失败且 15 分钟内不能定位。

命中后在 implementation note 写证据和阻断，提交当前可审材料后停止，不自行扩 scope。

## 7. 唯一自检、commit 与回报

只跑一次：

```bash
uv run pytest -q \
  tests/test_membench_conversation_adapter.py \
  tests/test_membench_registered_prediction.py \
  tests/test_event_stream.py
```

通过后：

```bash
git diff --check
git status --short
git add \
  src/memory_benchmark/benchmark_adapters/membench.py \
  tests/test_membench_conversation_adapter.py \
  tests/test_membench_registered_prediction.py \
  tests/test_event_stream.py \
  docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/membench-time-semantics-phase-a-implementation.md
git commit -m "fix(membench): preserve missing message timestamps"
```

若允许清单内某文件未改，`git add` 必须删去该路径，禁止制造空白改动；仍只显式 add，禁
`-A`/`.`。到此停止，不 push。按 actor-handbook §4 回报 commit、测试尾行原文、实际改动
文件、偏差/停工点；若实质使用了 subagent，再用一句话说明分工。

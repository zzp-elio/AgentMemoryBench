# Actor 卡：Mem0 source-time 单次渲染（MemBench 去重 + turn→session fallback）

> **给当前 actor 的直接执行指令：你就是用户已选中的执行者。**本卡被发送到当前会话即
> 代表用户已经完成选择与授权，请直接施工；不要再选择、派发或等待另一个跨产品 actor。
> 是否使用当前执行环境自己的 subagent 由你判断，实质使用时在回报中说明。单批上限 3h；
> 零真实 API、零下载、不 push。

## 0. 白话目标

MemBench 的 message 原文已经带 `(place: ...; time: '...')`；benchmark adapter 又把同一
公开时间无损抽成 `Turn.turn_time`。这个双通道是正确的：支持 typed timestamp 的 method
得到原文 + typed field。但 Mem0 OSS 不消费独立 timestamp，当前 `_turn_to_message()` 又把
`turn_time` 前置为 `[Turn time: ...]`，造成**同一个 content 内重复一次时间**。
同一 helper 在 `turn_time` 与 `session_time` 同时存在时还会把两行都前置；这不符合项目已裁
“turn 优先、turn 缺失才 fallback 到 session”的 effective timestamp 契约。

本卡要做到：

- MemBench 原 content 的 message/place/time 一个字不删；
- `Turn.turn_time` 继续保留，供 LightMem/A-Mem/MemoryOS 等 typed channel 使用；
- Mem0 看到原文已嵌 source time 时不再前置相同 `[Turn time]`；
- 其他 benchmark 原文没带时间时，每条 Mem0 message 只渲染一个 effective timestamp：
  turn 有值用 `[Turn time]`，否则才用 `[Session time]`；
- LoCoMo/LongMemEval 的 session-only message 字节不变；BEAM/HaluMem 的 turn+session 双前缀
  收敛为单一 `[Turn time]`；
- 不在 Mem0 写 `benchmark == "membench"` 特判，而用公开 Turn metadata 表达输入事实。

不改 Mem0 extraction/update/retrieve 算法，不改 MemBench 时间 parser，不删除 place，不给无时
noise 造时间。

## 1. 上工、隔离与最小读序

```bash
cd /Users/wz/Desktop/memoryBenchmark
git status --short
git worktree add -b actor/mem0-membench-time-dedup \
  /Users/wz/Desktop/mb-actor-mem0-time-dedup main
cd /Users/wz/Desktop/mb-actor-mem0-time-dedup
```

若 branch/worktree 已存在或 main 不是最新，停工回报；不 reset、不删来源不明现场。

按顺序只读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点；
3. 本支线 `README.md`；
4. 本卡全文（它就是当前批次的 plan/prompt）；
5. `docs/reference/actor-handbook.md` §0-§4、§6-§7；
6. `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/
   membench-100k-time-ruling.md` §1、§5-§7；
7. `src/memory_benchmark/benchmark_adapters/membench.py::_turn_from_step`；
8. `src/memory_benchmark/methods/mem0_adapter.py::_turn_from_event/_turn_to_message/
   _observation_time_prompt`；
9. 本卡允许的两个测试文件相关 case。

## 2. 允许修改范围

只允许：

- `src/memory_benchmark/benchmark_adapters/membench.py`；
- `src/memory_benchmark/methods/mem0_adapter.py`；
- `tests/test_membench_conversation_adapter.py`；
- `tests/test_mem0_adapter.py`；
- 新增 `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/
  mem0-membench-time-dedup-implementation.md`。

不得改 registry/runner/TOML/third_party/README/status/frozen note；不得调用真实 API。

## 3. 已裁协议

### 3.1 benchmark 侧公开标记

在 MemBench `_turn_from_step()` 形成的 `Turn.metadata` 写 JSON-safe boolean：

```text
source_timestamp_embedded_in_content
```

- 本 step 的 `turn_time` 确实由其 content 内完整 time marker 解析得到 → `True`；
- 没有 time marker → `False`。

first-person dict 只要 user/agent 任一合法 marker 被解析为该 turn time，就为 True；third-person
string 同理。不要把 QA.time、place-only、自然语言单词 time 或模板占位误标 True。现有正则与
原文保持不变。

### 3.2 method 侧通用 renderer

Mem0 `_turn_to_message()` 读取上述公开 marker：

- 先按非空 `turn.turn_time` → 非空 `session_time` → None 选出唯一 effective timestamp 和来源；
- 来源为 turn 且 marker 严格为 True 时，不追加 header；原文里的 place/time 就是唯一正文表示；
- 来源为 turn 且 marker False/缺失时，只追加 `[Turn time: ...]`；即使 session 同时有值也不加
  `[Session time]`；
- turn 缺失、session 有值时只追加现有 `[Session time: ...]`；
- 无时间时不产生任何前缀；
- speaker name 与 image caption 行为不变。

禁止用字符串包含猜测替代 marker，禁止写 benchmark 名判断。metadata 经过 v3
`TurnEvent.metadata["turn_metadata"]` 往返后必须仍生效。

`_observation_time_prompt()` 是一次 `Memory.add()` batch 的相对时间锚，不是逐 message 的
timestamp channel；本卡不改其 prompt 文本和 batch/session 选取策略。逐 turn source time 已由
每条 message 正文承担。若 actor 发现它会覆盖/抹除正文时间或构成算法矛盾，停工回报，不在
本卡自行扩张 prompt 语义。

### 3.3 实验身份

正文送入 extraction 的字节发生改变，必须把 `MEM0_ADAPTER_VERSION` 从
`conversation-qa-v1` 升为 `conversation-qa-v2`。不改 RetrievalEvidence contract version；
二者不是同一个协议。manifest 严格比较会自然拒绝旧 run resume，不新增兼容删除键。

## 4. 必测强反例

至少锁住：

1. MemBench first-person dict：原文 place/time 均保留，metadata marker=True；
2. third-person string 的有冒号/无冒号两种官方格式均 marker=True；
3. 无 timestamp noise marker=False、turn_time=None；QA.time 不进入 ingest；
4. Mem0 legacy `add()` 或直接 `_turn_to_message()`：embedded content 中具体时间只出现一次，
   不含 `[Turn time:`，place 仍在；
5. v3 `build_turn_events -> Mem0.ingest` 路径同样去重，证明 marker 没在事件层丢失；
6. 普通非 MemBench turn 同时有 typed turn/session：只含一个 `[Turn time]`，不含
   `[Session time]`；分别用 legacy 与 v3 路径锁住（覆盖 BEAM/HaluMem 形态）；
7. turn 缺失、session 有值时 `[Session time]` 字节级保持现状；两者都缺时无 header；
8. `_observation_time_prompt()` 既有 batch/session 语义与文本零变化；
9. adapter manifest 版本为 v2，旧 v1 与新 v2 不应被表述成可 resume 同一 run。

fixture 必须同时有无时间 noise、内嵌时间和明显不同的 QA future time；不得只测一个“看起来
像 MemBench”的手写字符串而绕过真实 adapter mapping。

## 5. note、自检、提交与停工

implementation note 记录：两类根因、公开 marker 契约、唯一 effective timestamp fallback、
legacy/v3 两路径、MemBench/BEAM/HaluMem 受影响面、LoCoMo/LongMemEval session-only 不变、
版本 bump、测试尾行、未改算法声明。

只跑一次定向自检：

```bash
uv run pytest -q \
  tests/test_membench_conversation_adapter.py \
  tests/test_mem0_adapter.py
git diff --check
```

通过后 `git status --short` 过目，只显式 add 实际修改的允许路径，禁止 `git add -A`/`.`：

```bash
git add \
  src/memory_benchmark/benchmark_adapters/membench.py \
  src/memory_benchmark/methods/mem0_adapter.py \
  tests/test_membench_conversation_adapter.py \
  tests/test_mem0_adapter.py \
  docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/mem0-membench-time-dedup-implementation.md
git commit -m "fix(mem0): render one effective source timestamp"
```

到此停止，不 push、不跑全量、不更新状态。按 actor-handbook §4 回报 commit hash、测试尾行、
实际改动文件、偏差/停工点；使用 subagent 时补一句分工。

立即停工条件：必须按 benchmark 名特判才能实现；marker 会进入私有字段；LoCoMo/
LongMemEval session-only 消息字节变化；`_observation_time_prompt()` 必须改语义才能通过；
必须删除原 place/time；必须修改允许清单外生产文件；定向失败 20 分钟无法定位。

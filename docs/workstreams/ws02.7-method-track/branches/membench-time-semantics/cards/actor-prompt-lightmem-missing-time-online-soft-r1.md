# Actor 返工卡：LightMem explicit-None 边界收紧 R1

> **给当前 actor 的执行指令：你就是用户已选中的返工执行者。** 本卡被发送到当前会话即
> 代表用户已完成选择与授权；请直接进入既有 worktree 施工，不要询问“还要派给谁”，
> 不要另派 actor。单批上限 2h、零真实 API、不 push。
>
> 白话目标：首轮实现方向正确，但把“显式 `None`”意外放宽成“字段没写/空字符串也算
> `None`”，并让 `MemoryEntry` 的类型声明落后于真实值。本卡只把这三道边界锁实，不重做
> Phase B，不改变 online-soft 算法。

## 0. 现场与最小读序

继续使用现有 worktree `/Users/wz/Desktop/mb-actor-lightmem-missing-time`、分支
`actor/lightmem-missing-time-online-soft`。先核对：

```bash
cd /Users/wz/Desktop/mb-actor-lightmem-missing-time
git status --short
git rev-parse --short HEAD
```

预期 clean 且 HEAD=`e1cfb75`；任一不符就停工上报，不 reset、不删 worktree、不另建分支。

按顺序只读：

1. `AGENTS.md`；
2. 本卡全文；
3. `docs/reference/actor-handbook.md` §0-§4、§6-§7；
4. 首轮卡 §2-§4 与 implementation note；
5. `third_party/methods/LightMem/src/lightmem/memory/lightmem.py` 的
   `MessageNormalizer.normalize_messages()`；
6. `third_party/methods/LightMem/src/lightmem/memory/utils.py` 的 `MemoryEntry`、
   `_create_memory_entry_from_fact()`；
7. adapter 的 `_turn_timestamp()` 与本轮相关测试。

允许修改且只允许修改：

- `third_party/methods/LightMem/src/lightmem/memory/lightmem.py`；
- `third_party/methods/LightMem/src/lightmem/memory/utils.py`；
- `src/memory_benchmark/methods/lightmem_adapter.py`；
- `tests/test_lightmem_adapter.py`；
- 既有 `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/
  lightmem-missing-time-online-soft-implementation.md`。

## 1. R1-1：只扩展 explicit None

`MessageNormalizer.normalize_messages()` 只对**键存在且值严格为 `None`** 的
`{"time_stamp": None}` 走 preserve 分支。下面两种输入继续保持 upstream 原有拒绝语义：

- dict 根本没有 `time_stamp` 键；
- `time_stamp=""`（以及其它无法解析的非空字符串）。

不要用 `msg.get("time_stamp")` 把“缺键”和“显式 None”混成一种状态。同步改正该函数
docstring 与错误信息：真实接口只接受 dict / list[dict]，现有代码对 str 是拒绝而非接受。
不改变 timestamped 分支的解析、offset 或 deepcopy 行为。

## 2. R1-2：adapter 不把非法空串洗成 None

`_turn_timestamp()` 的 `preserve_none` 只在 `turn.turn_time is None` 且
`session.session_time is None` 时返回 None。保留既有优先级：有非空 turn time 用 turn；
否则有非空 session time 用 session。只要来源字段中出现空字符串且最终没有可用非空
fallback，仍抛 `ConfigurationError`，不得把坏数据静默正规化成缺失值。

`require` 的既有行为和所有合法 timestamp 转换保持不变。

## 3. R1-3：让 MemoryEntry 类型说真话

`MemoryEntry` 现在真实存储 `None`，因此把以下 annotation 改为诚实的 optional：

- `time_stamp: Optional[str]`；
- `float_time_stamp: Optional[float]`；
- `weekday: Optional[str]`。

默认值保持原样，避免改变 upstream 对未显式传参的 runtime 行为；不要顺手重排 import、
清理第三方格式或修改其它字段。

## 4. 必测反例

在既有测试上补最小强反例：

1. real normalizer 接受显式 `time_stamp=None`，但缺键与空字符串分别 raise；
2. `_turn_timestamp(..., "preserve_none")` 对双 None 返回 None；双来源无可用时间但含空串
   时 raise；空 turn + 合法 session 仍按既有 fallback 返回 session；
3. 用 `typing.get_type_hints(MemoryEntry)`（或等价强断言）确认三字段 optional；同时保留
   既有 missing-time lineage 测试，证明 runtime 仍保存 None 与 source id。

测试不得调用真实 API、下载模型或扫描完整数据。

## 5. note、唯一自检与提交

在既有 implementation note 追加“架构师 R1 验收返工”小节，诚实记录三项缺口、修复位置、
测试尾行；不得改写首轮历史尾行。

只跑一次：

```bash
uv run pytest -q \
  tests/test_lightmem_adapter.py \
  tests/test_amem_lightmem_registry.py \
  tests/test_method_registry.py
```

通过后执行 `git diff --check`、`git status --short`；只显式 add 上述实际修改文件，禁止
`git add -A`/`.`。新增一个 follow-up commit，不 amend `e1cfb75`：

```text
fix(lightmem): tighten missing timestamp contract
```

不 push。按 actor-handbook §4 回报 commit hash、测试尾行、实际改动文件、偏差/停工点；
使用了 subagent 才补一句分工。

## 6. 停工条件

- 收紧 explicit-None 会迫使修改允许清单外生产文件；
- timestamped 既有测试因此改变输出；
- 必须引入 sentinel/wall clock、过滤 noise 或触碰 consolidated/summary 才能通过；
- 定向测试失败且 20 分钟内无法定位。

命中后保留证据并停止，不自行扩 scope。

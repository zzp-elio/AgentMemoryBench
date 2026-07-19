# LightMem × MemBench pair 投递与运行身份 R1 卡

本卡被发送到当前 actor 会话即代表用户已完成选择与授权，直接执行；不要再选择、
派发或等待另一个 actor。

## 0. 身份、工作区与目标

你是施工 actor，不是最终架构师。只在：

- worktree：`/Users/wz/Desktop/mb-actor-lightmem-membench-pair-r1`
- branch：`actor/lightmem-membench-pair-r1`

工作。当前 HEAD 已包含 Sonnet 5 的 docs-only 审计 commit `d2c1834`。

目标有两个，必须作为一个原子修复完成：

1. 修正 LightMem × MemBench 的生产投递契约：FirstAgent 的 canonical
   `user -> assistant` child turns 必须作为一个 `TurnPair` 投递；ThirdAgent 的
   user-only turn 保持单边 pair，另一侧只由 LightMem structural placeholder 补齐。
2. 把 method 实际 `consume_granularity` 作为公开、严格的 run/resume 身份写入
   method manifest，不能靠 bump 全局 LightMem adapter version 粗暴使其他 benchmark
   的 run 一起失效，也不能留下旧 `turn` run 被新 `pair` 逻辑误 resume 的漏洞。

零真实 API、零下载、零 push、不要改数据。

## 1. 开工读序

完整阅读：

1. `AGENTS.md`
2. `docs/reference/actor-handbook.md`
3. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与 LightMem 当前断点
4. 本卡全文
5. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/lightmem-membench-anomaly-coverage-preflight.md`
6. `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/membench-canonical-split-implementation.md`
7. 下列生产文件的相关实现：
   - `src/memory_benchmark/benchmark_adapters/membench.py`
   - `src/memory_benchmark/methods/registry.py`
   - `src/memory_benchmark/methods/lightmem_adapter.py`
   - `src/memory_benchmark/runners/event_stream.py`
   - `src/memory_benchmark/runners/prediction.py`
   - `src/memory_benchmark/cli/run_prediction.py`
   - vendored LightMem 的 `memory/lightmem.py`、`sensory_memory.py`、
     `short_term_memory.py`、`factory/memory_manager/openai.py`

## 2. 架构师已裁定事实

这些不是候选菜单：

1. Sonnet 审计发现属实：当前 registry 只给 LongMemEval 配 `pair`，MemBench 落到
   `turn`，因此真实 registered path 会把 FirstAgent 一个源 step 拆成两次
   `add_memory()`，现有 direct-helper 测试没有覆盖到这一连接层。
2. 这推翻了原审计卡 §3.8 的承重前提，按原卡 §10 本应停工。R1 note 必须如实披露
   该停工条件曾被漏报；不能继续写“无偏差/无停工点”。
3. 正确生产契约：
   - MemBench FirstAgent：一个源 dict step 展开为相邻 user、assistant child，聚合成
     一个真实双边 `TurnPair`；两条 child id 共同进入 pair candidate ids。
   - MemBench ThirdAgent：每个 str step 是独立 user turn；连续 user 不能彼此配对，
     aggregator 应产生单边 pair，LightMem 再补空 assistant placeholder。
   - 不跨 session、不跨 conversation 配对，不按 role 猜测或重排。
4. MemBench message 尾部的 `place/time` 是公开源文本：canonical `content` 及送给
   LightMem 的真实 message `content` 必须原样保留，不能删除或重写；同时将每条消息
   自身解析出的 `turn_time` 写入 LightMem `time_stamp`。这是同一源事实进入文本通道与
   typed timestamp 通道，不得拿 question time、session 兄弟 turn、相邻消息或 wall
   clock 回填。
5. 100k noise 无 `place/time` 时，`content` 原样，`time_stamp=None`。不得造 sentinel，
   不得为了通过 upstream 校验过滤 noise。
6. MemBench `QA.time` 是公开 `Question.question_time`，只进入 answer/query 侧。官方
   `third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py` 的
   `INSTRUCTION_FIRST` 明确使用 `Question: (current time is {time}) ...`；当前 unified
   builder 必须继续逐字使用官方模板并填入 question time。它绝不能反向污染任何历史
   turn 的 timestamp。
7. 现有 39 处 source-step 时间倒序属于 dataset-native 顺序异常：保持数据顺序与各自
   source time，不排序、不修钟、不丢 turn。至少核对并在 note 留下八文件分布：
   `3, 7, 2, 21, 0, 3, 1, 2`，合计 39；若当前数据重算不同则停工。
8. Sonnet note 中“两个 conversation 的 external_id 集合完全不交叉”措辞不成立：
   局部 child id 可重复；隔离由不同 backend/storage namespace 与 isolation key 保证。
   R1 必须订正，不能通过伪造全局 id 来迎合旧文字。
9. 不接受“必须先做付费 100k sentinel 才能确认 STM 跨 add 缓冲”的原 BLOCKED 判词。
   vendored buffer 是实例字段，源码可证明跨调用保持；而本次会直接消除 FirstAgent 的
   split 路径。100k `None` 兼容用 production-path + vendored local/fake backend 强反例
   验证，不调用 API。修复与离线验收全绿后，状态应是 B11 smoke 待跑，不是 API sentinel
   blocker。
10. 不 bump `LIGHTMEM_ADAPTER_VERSION`：算法 adapter 没变；真正变化的是按 benchmark
    解析的 ingest/consume contract，必须单独落 manifest。

## 3. 运行身份的最小共享设计

不要给 LightMem 写 benchmark 专用 manifest 特判。按下列边界实现共享契约：

1. `MethodRegistration` 增加一个可解析当前 benchmark `ConsumeGranularity` 的注册级
   resolver/getter（命名自行保持代码风格）。内置 method 的 factory 与 manifest 构造
   必须复用同一组纯 resolver，避免两份 if/else 漂移：
   - A-Mem、SimpleMem：固定 `turn`；
   - Mem0：保留当前 LongMemEval/HaluMem=`session`、BEAM=`pair`、其余=`turn`；
   - LightMem：HaluMem=`session`，LongMemEval/MemBench=`pair`，其余=`turn`；
   - MemoryOS：保留当前 LongMemEval=`pair`、其余=`session`。
2. registered CLI 在构造 method manifest 时写入顶层
   `method.consume_granularity`，值必须是本次 method × benchmark 的 concrete 值。
3. 运行时能拿到真实 `MemoryProvider` 时，声明值与实例值必须交叉校验；不一致
   `ConfigurationError` fail-fast。workers>1 的根进程不能为了校验而提前构造真实 method；
   worker 实例路径仍要使用与 manifest 同源的 resolver/factory。
4. `consume_granularity` 是严格 resume identity：旧 manifest 缺字段、新 manifest 有字段，
   或值变化，都必须双向 mismatch。禁止把它加入历史协议字段的“任一侧缺失就双删”兼容
   列表。
5. unregistered/custom 测试路径若有真实 v3 instance，可从实例补出该字段；不要破坏旧
   `BaseMemoryProvider` bridge 的兼容范围。

如发现上述设计必须破坏 operation-level 或 isolated-worker 的既有公开契约，先停工回报，
不要用全局 version bump 或跳过校验绕过。

## 4. 必测强反例

测试必须走真实的 `build_turn_events -> GranularityAggregator -> LightMem.ingest`
或 registered prediction 装配路径，不能只调用 `_normalize_session_to_pairs()`：

1. MemBench FirstAgent 一个 dict step：runner 只投递一个 `TurnPair`；LightMem backend
   只收到一次 `add_memory()`，该 batch 有两个真实 role，pair ids 为两个 canonical child
   ids，零 placeholder。
2. MemBench ThirdAgent 至少两个连续 str steps：不得互相配成 user+user；每个成为一个
   单边 pair，各自 backend batch 是真实 user + structural placeholder assistant，来源 id
   不串。
3. FirstAgent user/assistant 各自有不同尾部时间：content 逐字保留 `place/time`；各自
   `time_stamp` 等于各自解析值，不跨侧 fallback。
4. 100k-style noise：content 原样、两侧/单侧缺时间分别为 `None`，不读 QA.time。
5. question time：registered answer artifact/prompt 包含当前 `Question.question_time`；历史
   event/message timestamp 不包含该值。继续保留官方 prompt 逐字 parity 测试。
6. 时间倒序：输入顺序不变，各自 timestamp 不变。
7. manifest：LightMem × MemBench=`pair`，LightMem × LoCoMo=`turn`，LightMem ×
   HaluMem=`session`；至少再锁一个其他动态 method，证明共享 resolver 没改坏现状。
8. factory/resolver 故意不一致时运行时 fail-fast。
9. resume：缺 `consume_granularity`、`turn -> pair`、`pair -> turn` 均 mismatch；相同值 match。
10. workers=1 与 isolated workers 路径不因新增 manifest 字段漂移。

不得通过删断言、放宽异常、mock 掉 aggregator、把两个 turn 手工塞成 pair、修改数据或
篡改 expected artifact 来“绿测试”。

## 5. 允许文件

仅允许修改以下路径；不需要的文件不要制造空白 diff：

- `src/memory_benchmark/methods/registry.py`
- `src/memory_benchmark/cli/run_prediction.py`
- `src/memory_benchmark/runners/prediction.py`
- `src/memory_benchmark/runners/operation_level.py`（仅共享校验确有需要时）
- `tests/test_method_registry.py`
- `tests/test_prediction_cli.py`
- `tests/test_prediction_runner.py`
- `tests/test_lightmem_adapter.py`
- `tests/test_lightmem_registered_prediction.py`
- `tests/test_membench_registered_prediction.py`
- `tests/test_membench_unified_prompt.py`
- `docs/reference/integration/lightmem.md`
- `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/lightmem-membench-anomaly-coverage-preflight.md`
- 新建
  `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/lightmem-membench-pair-r1-implementation.md`
- 本卡自身

不得改 TOML、benchmark data、MemBench canonical adapter、LightMem third_party 算法、
metric/evaluator、outputs、父 README/roadmap、其他 method adapter。

## 6. 自检

只跑一次直接相关集合（允许先定向调试失败用例）：

```bash
uv run pytest -q \
  tests/test_method_registry.py \
  tests/test_prediction_cli.py \
  tests/test_prediction_runner.py \
  tests/test_lightmem_adapter.py \
  tests/test_lightmem_registered_prediction.py \
  tests/test_membench_registered_prediction.py \
  tests/test_membench_unified_prompt.py
git diff --check
```

不跑真实 API、不跑 full pytest、不跑 compileall。隔离 worktree 缺 gitignored data/models
时可建只读软链，但不得暂存。

## 7. 提交与回报

1. 新 commit 线性叠在 `d2c1834` 上，不 amend 它。
2. `git add` 只列显式路径，禁止 `-A`/`.`；提交前过目 `git status --short`。
3. 不 push。
4. 按 actor-handbook §4 回报：commit hash、测试尾行原文、实际改动文件、偏差/停工点、
   subagent/模型情况。implementation note 必须记录 manifest/resume 语义、生产 path 强反例、
   question-time 与 history-time 的单向边界，以及 Sonnet audit 的 R1 订正。

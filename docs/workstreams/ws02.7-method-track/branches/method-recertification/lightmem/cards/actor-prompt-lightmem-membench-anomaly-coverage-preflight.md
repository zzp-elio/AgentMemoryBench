# Actor 卡：LightMem × MemBench 分层异常覆盖与 B11 前置审计

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你负责零 API 取证与一份自包含审计 note，不修改生产代码、测试、配置、
数据或现有实验产物。actor 可自行组织 subagent，但不得扩大允许范围；若实质使用，最终报告
披露分工，主 actor 仍对全部结论负责。

## 0. 这张卡解决什么

LightMem 正按五 benchmark 逐格重认证。LoCoMo/LongMemEval 的 current-v7 真实复验由用户在另一
条受控线执行；本卡并行准备下一格 MemBench，但**不提前跑付费 smoke**。

你要回答的不是“默认 smoke 有没有报错”，而是：

1. MemBench 两个 variant、四种 source stream 的公开结构与已知异常是否有完整 census；
2. 每类高风险输入是否至少有一个 production-path 强反例走到 LightMem 的实际 message payload；
3. 哪些只需 evaluator-private 测试，哪些必须另选一个真实 backend sentinel smoke；
4. 当前 main 是 `READY_FOR_MEMBENCH_B11_COMMAND`，还是仍有代码/证据缺口。

唯一总判词只能是：

```text
READY_FOR_MEMBENCH_B11_COMMAND
```

或：

```text
BLOCKED(<最小缺口列表>)
```

发现缺口只记录最小复现、影响层与建议修复边界；不要在本卡顺手改代码。

## 1. 隔离环境与最小读序

- 建议 worktree：`/Users/wz/Desktop/mb-actor-lightmem-membench-preflight`
- 建议 branch：`actor/lightmem-membench-preflight`
- 基线：包含本卡的 latest `main`；开工记录 `git rev-parse --short HEAD` 与
  `git status --short`

严格按顺序读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
4. `docs/reference/method-integration-checklist.md` 的分层异常覆盖门
5. 以下稳定事实页，只读与本卡相关段落：
   - `docs/reference/integration/membench.md`
   - `docs/survey/datasets/membench.md`
   - `docs/survey/workflows/membench.md`
6. 以下已验收施工/裁决 note，只读承重章节：
   - `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/
     membench-canonical-split-implementation.md`
   - `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/
     lightmem-messages-membench-beam-role-audit.md` 的 MemBench/LightMem 段
   - `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/
     membench-100k-time-ruling.md`
   - `docs/workstreams/ws02.7-method-track/branches/membench-time-semantics/notes/
     lightmem-missing-time-online-soft-implementation.md`
7. `docs/reference/actor-handbook.md`
8. 本卡 §4 点名的 current-main 源码与测试

新 worktree 缺 gitignored `data/` / `models/` / `third_party/benchmarks/` 时，可只读软链到主工作区；
不得复制、修改或暂存软链。不得读取、打印 `.env`。所有 probe 使用 fake backend，禁止真实 API、
模型下载与外网请求。

## 2. 四层覆盖的已裁含义

不要把“所有异常都塞进一次付费 smoke”当目标。每个异常类必须至少落到下列合适层，并在交付表
中写明证据：

1. **全量 census / invariant**：零 API 扫 source-locked 数据，证明异常规模、位置与 canonical
   映射不变量；适合发现少见或未知结构形状。
2. **production-path 强反例**：用真实 benchmark adapter、event stream、pair 聚合与 LightMem
   payload helper，加 fake backend，证明该异常不会 crash/drop/改 role/造时间/串 session。
3. **真实 backend sentinel**：只有依赖真实 LightMem/Qdrant/API/process/worker 才能证明的性质，
   才需要在后续付费 smoke 中定点覆盖；本卡只推荐公开样本和规模，不执行。
4. **evaluator-private 强反例**：越界/空/重复 gold 等不能给 method 看的异常，只在私有 evaluator
   通道验证；绝不为了真实 smoke 覆盖它而用 gold 选题或泄漏标签。

一类异常可由多层共同关闭；但 crash、静默丢消息、role/time/place/image 漂移、跨 conversation
污染和 gold 泄漏这类高风险项，不能只写“等 full 自然遇到”。

## 3. 已裁事实：先复核，不要重新发明

以下是 current 文档已接受的事实，需用 current source/data 复核是否漂移：

1. variant 为 `0_10k`（默认认证）与 `100k`；每个正式 variant 都有 First/Third × High/Low
   四个主 source file，不能把根目录额外 20 条文件混入主 variant。
2. FirstAgent 一个 dict step 是真实 `user + agent` pair，canonical 必须拆成
   `<n>:user` 与 `<n>:assistant`；两条 child 各保留自己的 content/place/time/role，不拼成伪 user。
3. ThirdAgent 一个 string step 是一条 user observation；进入 LightMem 时补 empty assistant
   structural placeholder，不凭内容发明 assistant。
4. official `target_step_id` 是 0 基 source step unit。FirstAgent 一个 gold step 映射为两个 child
   的 evaluator-private any-of group，分母仍是一个官方 step；ThirdAgent group 只有一个 child。
5. content 中时间有 `time: '...'` 与 `time'...'` 两种合法格式；place/time 原文字节保留，同时
   可把本 turn 的 time 无损结构化。MemBench 没有真实 session time。
6. 100k 有大量无 time marker 的公开 noise。它们的 `turn_time=None`，`session_time=None`；禁止
   用 QA time、兄弟 turn、首个有时 turn、wall clock 或人造 offset 回填。
7. LightMem 主配置为 `hybrid + online_soft + preserve_none`。explicit None 是 framework-extended
   compatibility，不得写成 upstream native parity；empty string/缺 key 仍需 fail-fast。
8. FirstAgent real-real pair 的两侧共享完整 candidate child ids；ThirdAgent real user + placeholder
   只退化为一个真实 child id。对 MemBench official step group，items 完整时逐题 evidence 可为
   `valid/turn`；任一 hit lineage 缺失则必须 `n_a/none`。
9. 已知 private gold 异常至少包括越界 `target_step_id` 两例与空 target 一例；这些只影响 evaluator
   处置，不可进入 method payload、query、answer prompt 或 smoke 选题。
10. 标准 `0_10k` smoke 按四个 source file 各取一条，按 source step 裁剪并保留 FirstAgent
    完整 pair；它覆盖主路径，不自动覆盖 100k missing-time noise。

若 current 一手证据推翻任一项，写出精确冲突并触发停工；不得为对齐旧文档而修改数据或测试。

## 4. current-main 必须亲读的链路

只读承重点，禁止全文扫仓库：

- `src/memory_benchmark/benchmark_adapters/membench.py`
  - variant/source 表、`load()`、`_build_membench_smoke_dataset()`、
    `_conversation_from_trajectory()`、`_turns_from_step()`、`_build_step_turn()`、
    `_membench_turn_time()`、`_membench_evidence_group_sets()`
- `src/memory_benchmark/runners/event_stream.py`
  - `build_turn_events()`、pair 聚合与 session/conversation flush
- `src/memory_benchmark/methods/registry.py`
  - LightMem factory 与 benchmark identity 注入
- `src/memory_benchmark/methods/lightmem_adapter.py`
  - `LightMemConfig`、`ingest()`、`end_session()`、`end_conversation()`、
    `_native_pair_batch()`、`_normalize_session_to_pairs()`、`_real_message()`、
    `_placeholder_message()`、`_write_native_batch()`、`_turn_timestamp()`、
    `retrieve()`、`_build_retrieval_evidence()`
- `configs/methods/lightmem.toml`
- `src/memory_benchmark/evaluators/membench_recall.py`
- `src/memory_benchmark/evaluators/gold_evidence_groups.py`
- 对应测试：
  `tests/test_membench_conversation_adapter.py`、
  `tests/test_membench_registered_prediction.py`、
  `tests/test_membench_retrieval_recall.py`、
  `tests/test_lightmem_adapter.py`

## 5. 一次全量零 API census

对 8 个正式主文件做一次可复现扫描。可以写临时脚本，但不得提交；note 必须抄入命令/算法摘要、
完整 stdout 和至少一个真实公开位置例子，使 Codex 架构师无需访问 actor scratchpad 也能复验。

### 5.1 public input shape

逐 variant/source 至少统计：

- trajectories、source steps、canonical turns；FirstAgent 必须满足 `turns=steps*2`，ThirdAgent
  必须满足 `turns=steps`；
- dict/string/其它 type，dict 缺 user/agent key，空/纯空白 user/agent/string；
- 两种 time marker、无 time marker、place marker 有/无、time 有但 place 无及反向组合；
- 每个 FirstAgent pair 两侧 timestamp 是否相同/不同/一侧 None；
- duplicate `tid`、空 message_list、极长单 step、最短/最长 trajectory；
- production adapter 构造后的 turn-id 唯一性、step→child 映射完备性、role 计数、
  `session_time is None` 与无时 turn 的 effective timestamp 仍为 None；
- 标准 0_10k smoke 首条四源实际覆盖了哪些 shape，明确列出没有覆盖的 shape。

不要靠宽松搜索单词 `time` 统计 timestamp；必须复用或字节等价于 production regex。极长正文只
记录长度与定位，不把全文倾倒进 note。

### 5.2 evaluator-private shape

只在独立私有小节聚合：empty、duplicate、越界 target step、group child unmatched。复核分母是否
按官方 `len(set(target_step_id))` 和 group any-of；不要展示 answer/ground_truth，不要用这些字段
挑选后续 sentinel。

## 6. production-path 强反例矩阵

必须用 production adapter/helper + event stream + LightMem fake backend 覆盖下列最小矩阵；已有
测试可作为一层证据，但若只测了 helper、没走到 `provider.ingest(...) → actual add_memory batch`，
用临时 probe 补齐：

| 类别 | 必须证明的末端事实 |
|---|---|
| FirstAgent 正常 pair | user/assistant 两条 real message、content 不互串、role 正确、candidate ids 为同一步两个 child、无 placeholder |
| ThirdAgent 单 user | real user + empty assistant placeholder；真实 id 只有一个；placeholder 从 extraction 文本/token count 过滤 |
| `time:` 与 `time'` | 两种均结构化为本 turn timestamp，原 content 中 place/time 不删除、不重复前置 |
| 100k no-time noise | real content 原样；显式 `time_stamp=None` 进入 online-soft；无 sentinel/QA time/session smear/wall clock |
| FirstAgent 一侧有时、一侧无时（若真实存在；否则 synthetic） | 两个 child 各自判 time，不从 peer fallback；pair lineage/role 仍完整 |
| 两个连续 source steps | 不跨 step union candidate ids，不把上一步 assistant 与下一步 user 重组为错误 gold unit |
| zero-hit / complete-hit / malformed lineage | evidence 分别保持 valid/valid/n_a，不能因真实 0 hit 把空 tuple 当 items 缺失 |
| conversation 隔离 | 两个 tid 的 backend namespace、pending batch、retrieved lineage 不串 |

每个反例在 note 中写清：

```text
raw step
→ canonical Turn(s)
→ TurnEvent / TurnPair
→ LightMem [user, assistant] message dict
→ fake backend 实际 add_memory kwargs/batch
→ retrieve items/evidence（适用时）
```

并做负空间检查：`answer`、`ground_truth`、`target_step_id`、gold groups、judge label 不出现在
任何 method-visible object。临时 stdout 全量抄入 note；不得只引用 `/tmp/*.py` 文件名。

## 7. 分层覆盖表与下一次真实 sentinel 建议

交付 note 必须有一张表，每行是一类异常/特殊 shape，列为：

```text
异常类 | 真实位置/规模 | 风险 | census | production-path test/probe |
evaluator-private test | 是否还需真实 sentinel | 当前判词/缺口
```

真实 sentinel 只为下列“离开 fake 就无法证明”的性质提出：真实 LightMem normalizer/extraction、
Qdrant persist/retrieve、worker/process 隔离、真实 None 与 local embedder 的组合。建议时：

- 分开判断默认 `0_10k` 四源 smoke 与一个最小 `100k` missing-time sentinel 是否都需要；
- 只按 public shape、source path 与顺序选样本，给出 conversation id/公开 step 数/turn 数；
- 不按 gold、答案、容易命中与否选题；不估算 LLM call 次数，不从 pair 数推成本；
- 不执行 API、不创建 run directory、不写 command pack。架构师回卡后再裁预算/run id。

如果某异常已经由 census + production path + private evaluator 完整关闭，明确写“不需要塞进
付费 smoke”及理由；不能只写 N/A。

## 8. 唯一交付物

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-membench-anomaly-coverage-preflight.md
```

note 至少包含：

1. baseline、source/config/adapter identity；
2. 8 文件 census 方法、原始输出与公开例子定位；
3. private gold shape 的隔离统计；
4. production-path 强反例逐层 payload；
5. 四层 anomaly coverage 表；
6. 标准 0_10k smoke 的覆盖/盲区；
7. 是否需要 100k real sentinel 与公开候选；
8. metric eligibility（answer 指标、MemBench group Recall valid/N/A 条件、stable ranking 边界）；
9. 唯一总判词与最小剩余缺口。

不得修改 README、integration、survey、src、tests、third_party、configs、data、outputs、policy、
checklist 或 handbook。稳定事实由架构师强验收后回填，避免 actor 同时改证据和权威摘要。

## 9. 自检、commit 与回报

只跑一次直接相关组合，再跑 diff 检查；禁止全量 pytest、compileall、真实 API与下载：

```bash
OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9 \
uv run pytest -q \
  tests/test_membench_conversation_adapter.py \
  tests/test_membench_registered_prediction.py \
  tests/test_membench_retrieval_recall.py \
  tests/test_lightmem_adapter.py \
  tests/test_documentation_standards.py
git diff --check
```

若测试尝试联网，立即中止并报告，不得为过测修改允许清单外文件。只显式 add 唯一 note，禁止
`-A`/`.`；commit 前查看 `git status --short`。建议 commit：

```text
docs(lightmem): audit membench anomaly coverage
```

按 actor-handbook §4 回报：commit hash、自检尾行、实际改动文件、唯一总判词、偏差/停工点、
subagent 分工、实际模型与入口切换。不要 push；到此停止，等待架构师强验收。

## 10. 停工条件

- current source/data 推翻 §3 承重事实；
- canonical turn 有丢失、重复、role 猜测、跨侧 time fallback 或 content/place/time 改写；
- 100k None 被替换为 QA time、session time、wall clock、sentinel 或人造递增值；
- FirstAgent step group 被拆成双重分母，或 private gold 可达 method；
- LightMem pair candidate lineage 跨 source step union，或 malformed hit 仍宣称 valid；
- online-soft 主 profile暗跑全库 consolidation；
- 完成本卡必须修改唯一 note 以外文件；
- 直接相关测试失败，且 15 分钟内确认不是缺 data/models/软链的环境问题。

触发停工仍可提交已完成的唯一 note，保留最小复现；不得自行扩成修复卡。

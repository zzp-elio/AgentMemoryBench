# Actor 卡：LightMem × LongMemEval 输入异常与 timestamp 透明性审计

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是取证 actor，不是架构师；本卡只做离线审计与证据记录，不修改生产
代码，不代替架构师裁算法。

## 0. 这张卡解决什么

LightMem 重认证已经把 Phase 1 五格 unified 主 build 固定为
`messages_use="hybrid"`，并用 placeholder 补齐官方库要求的 user/assistant pair 结构。新一轮
LongMemEval 数据检查又暴露出两类不能混为一谈的问题：

1. benchmark 原始数据存在 assistant-first、同 role 相邻、奇数 turn、空 content，以及
   `question_date` 早于部分甚至全部 haystack session 的记录；
2. LightMem 上游先由 `MessageNormalizer(offset_ms=500)` 改写 `time_stamp`，后续
   `assign_sequence_numbers_with_timestamps(..., offset_ms=500)` 又按 `session_time` 分组赋值；
   framework placeholder 虽从 extraction 文本和 token 计数中滤掉，仍参与这两层结构与时间
   分配。

本卡要把“benchmark-native 数据形状”“benchmark 契约自相矛盾”“method-native 变换”与
“framework extension”逐层拆清，并回答 placeholder 是否会改变真实 turn 最终可见的时间、
sequence、speaker 或 lineage。审计结论将决定 LightMem B4 是只需诚实披露，还是另发一张
最小修复卡。

## 1. 隔离环境与必读顺序

- 建议 worktree：`/Users/wz/Desktop/mb-actor-lightmem-lme-time-audit`
- 建议 branch：`actor/lightmem-lme-time-audit`
- 基线：用户创建 worktree 时的最新 main；先现场记录 `git rev-parse --short HEAD`

严格按顺序读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
4. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
   lightmem-b1-b11-gap-matrix.md`
5. `docs/reference/actor-handbook.md`
6. `docs/workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-b2-audit.md`
7. `docs/survey/datasets/longmemeval.md` 与 `docs/survey/workflows/longmemeval.md`
8. 本卡 §3 点名的一手源码与测试

用户在主工作区有一份**未跟踪、待校验草稿**：
`/Users/wz/Desktop/memoryBenchmark/docs/survey/异常情况/longmemeval.md`。若同机可读，可把它当
待证伪问题清单；不得把草稿本身当一手事实、复制进提交或修改/暂存该文件。全量数据与官方
源码才是事实源。

新 worktree 通常没有 gitignored `data/` 与 `third_party/benchmarks/`。允许建立不入 git 的
只读软链，或直接读取主工作区绝对路径；提交前确认软链未暂存。`longmemeval_m_cleaned.json`
约 2.5GB，必须用 `ijson` 流式扫描，禁止 `json.load`、`read_text` 或 `read_bytes` 整体加载。

## 2. 已裁边界

这些不是本卡待重新设计的问题：

- canonical role 只认 dataset 的结构化 `role` 字段；不得从“This is great”、内嵌
  `User/Assistant/System` 等 content 猜测并改写 role。
- benchmark adapter 保留官方 session/turn 顺序。未来 session、assistant-first、同 role 与
  单 role session 不因“像噪声”而被某个 method 私自删除。
- Phase 1 unified 主 build 使用 `messages_use="hybrid"`；官方 LongMemEval Table 2 的
  `user_only + 开头裁剪 + 非法 pair 跳过`是独立 author-reproduction 口径。两者必须分开命名，
  不得把 framework hybrid 行为冒充官方复现。
- placeholder 只补 LightMem pair 的结构槽，不是 public turn，不增加 source id，不得进入
  extraction 文本或 token 计数。真实空 content 与 placeholder 仍由 marker 严格区分。
- turn 无时间时继承 session time；LongMemEval 每个真实 turn 都只有 session-level source
  timestamp。不得用 question time、墙钟或相邻 session 伪造 turn time。
- `answer`、`answer_session_ids`、`has_answer` 只可用于本次离线质量统计与 evaluator-private
  对表，绝不能进入 method 可见 payload、prompt 或测试 fake backend 输入。
- 本卡不改 500ms 算法、不删 placeholder、不改 pair aggregator、不改 qrel/evaluator，也不跑
  真实 API。先量化和追链，最终裁决交回架构师。

## 3. 必须亲读的一手链路

### 3.1 LongMemEval 官方

- `third_party/benchmarks/LongMemEval-main/README.md`：数据字段与“answer after all interaction
  sessions”契约；若 worktree 没有该 ignored 目录，读主工作区同路径绝对地址。
- `third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py`：history、
  `Current Date` 与 question 的实际构造；确认是否过滤 `date > question_date`。
- `data/longmemeval/longmemeval_s_cleaned.json`
- `data/longmemeval/longmemeval_m_cleaned.json`

### 3.2 LightMem 官方与 framework

- `third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py` 的 config 和
  session/pair 写入循环；Qwen 脚本只用于确认是否同构，不重复全文审计。
- `third_party/methods/LightMem/src/lightmem/memory/lightmem.py`：
  `MessageNormalizer`、`add_memory()` 的 normalizer 构造点与 sequence-assignment 调用点。
- `third_party/methods/LightMem/src/lightmem/memory/utils.py`：
  `assign_sequence_numbers_with_timestamps()` 与 fact→`MemoryEntry` source/time 取值。
- `third_party/methods/LightMem/src/lightmem/factory/memory_manager/openai.py`：
  `concatenate_messages()` 的 marker、role、time 与 `sequence_id // 2` 行为。
- `third_party/methods/LightMem/src/lightmem/factory/memory_buffer/short_term_memory.py` 与
  `sensory_memory.py`：placeholder 在 token、segment/pair 结构中的实际可见面。
- `src/memory_benchmark/benchmark_adapters/longmemeval.py`
- `src/memory_benchmark/runners/event_stream.py` 的 `_aggregate_pairs()`
- `src/memory_benchmark/methods/lightmem_adapter.py` 的
  `_normalize_session_to_pairs()`、`_native_pair_batch()`、`_real_message()`、
  `_placeholder_message()`、`_stamp_pair_ids()`、`_turn_timestamp()`
- `tests/test_lightmem_adapter.py` 中 assistant-first、同 role、dangling、placeholder、timestamp、
  sequence/lineage 相关测试。

主线已把旧名
`test_native_lightmem_longmemeval_assistant_first_skips_orphan_like_official_trim` 更正为
`...preserves_orphan_with_placeholder`，并同步修正 `_native_pair_batch()` 的旧 docstring：官方
author-reproduction 会裁 orphan，unified hybrid 则保留。审计时确认当前源码确已分开两种
口径，并继续搜索是否还有旧“跳过/等价官方裁剪”文字；不得拿历史测试名证明现行行为。

## 4. 数据扫描必须回答的问题

两个 variant 分开报告，定义先写清，再给 exact count 与比例：

1. instance/session/turn/blank turn 总数；answer 的 int、`$` 前缀、`gpt4_` id、session-id
   前缀只判定为格式形状还是算法风险，不把“分布不同”自动叫数据错误。
2. `question_date < max(haystack_dates)`、`question_date < min(haystack_dates)`、至少一个
   `answer_session_id` 在 question date 之后的题数；按 question_type 与 `_abs` 分层。给 3 个
   最小例子，只展示公开 question/id/time，不倾倒整段对话或 gold answer。
3. role 形状采用互斥且可复算的定义：normal user-first alternating、assistant-first、
   pure-assistant、consecutive-same、odd、blank。另报告这些形状与 answer session、
   `has_answer=True` 的交集。
4. 精确模拟官方 LightMem LongMemEval 脚本：删开头非 user、按位置两两切、只接受严格
   user→assistant。报告 accepted/dropped raw source turns、受影响 session，以及被丢弃 turn 中
   `has_answer=True` 的 role/type/是否位于 answer session。
5. 精确模拟当前 framework：blank adapter policy 后，经 user-anchor pair aggregator 与
   placeholder normalizer，报告 real-real pair、orphan-assistant placeholder pair、
   dangling-user placeholder pair；证明每个 retained canonical real turn 恰好出现一次。
6. timestamp 上界：按真实 `session_time` 分组统计 message 数、重复 timestamp group、最大
   组、500ms offset 是否越过下一分钟/小时/日期；区分“单次 normalizer 每 pair”与后续
   extract-list regroup 的实际边界，不把无法证明的 worst-case 写成已发生。报告超 120 slot
   的 group 是否为 answer session/含 target。

架构师预扫得到以下**校验点，不是要求 actor 凑数**：

| 指标 | S | M |
|---|---:|---:|
| instance / session / raw turn | 500 / 23,867 / 246,750 | 500 / 237,655 / 2,446,993 |
| blank turn | 12 | 295 |
| question 早于 latest / 早于 earliest / 有 future gold session | 76 / 1 / 44 | 118 / 0 / 42 |
| 官方 LightMem dropped raw source turn | 2,020 | 20,283 |
| framework placeholder pair | 1,986 | 20,126 |
| 官方 dropped `has_answer=True` | 3（均 assistant） | 3（均 assistant） |

若复算不同，先检查定义、blank policy、原始/清洗 variant 与 session-id 去重口径；仍不同就在
note 明列差异并停工，不能为了匹配表格改代码或筛选条件。

## 5. 必须做的无 API 端到端探针

使用 production helper/真实 vendored 函数与 fake/纯函数边界，至少覆盖四种 batch：

1. 正常 user→assistant，同一个 session timestamp；
2. assistant-first：placeholder user + real assistant；
3. user→user：两个 real user 各自 + placeholder assistant；
4. dangling user；若与 3 的单 batch 行为完全相同，可共用探针但要说明。

对每个 batch 逐层记录：

```text
canonical Turn
→ TurnPair metadata/orphan/dangling
→ LightMem message role/content/marker/source_external_ids/time_stamp
→ MessageNormalizer 后 session_time/time_stamp/weekday
→ assign_sequence_numbers... 后 sequence_number/time_stamp
→ concatenate_messages 实际可见行
→ fact source_id 映射会读取的 slot/time/speaker/external ids
```

探针必须回答：

- placeholder 是否从 prompt/token 中消失，却仍占 sequence slot；
- real assistant 在 assistant-first pair 中是否被赋 `base + 500ms`；正常 pair 的 assistant 是否
  同样如此；
- 第二层 timestamp assignment 会不会覆盖第一层结果；
- 原始 source timestamp 是否仍仅在 `session_time` 可审计，而持久化/检索展示的
  `time_stamp` 已是 method-derived tie-break；
- placeholder 是否改变某个真实 turn 的 source id、speaker 或 plural lineage；
- 任何结论是 production 实测、源码必然结果，还是尚待真实 build 才能观察。

不需要触发 LLM extraction；严禁把假 LLM 输出当 source_id/time 正确性的证据。

## 6. 唯一交付物与写法

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-longmemeval-input-time-audit.md
```

note 至少含：

1. 基线、数据/源码 identity 与完整可复算命令；
2. S/M 数据质量表与定义；
3. 官方 benchmark、官方 LightMem、framework canonical、pair bridge、vendored backend 五层图；
4. 四组探针的逐层结果；
5. 每项发现的分类：
   `benchmark-native shape / benchmark-contract inconsistency /
   method-native transformation / framework extension / stale documentation`；
6. severity（blocker/high/medium/low）、confidence、受影响 metric/profile；
7. 最小后续建议，至少明确区分：
   - 必须修代码；
   - 只需改测试/稳定文档；
   - 只需 manifest/report 披露；
   - 保持原样以维持 author reproduction；
8. 单独列出所有过时文字的当前文件/测试名、为什么已过时、应改成什么事实；不要直接修改
   survey/integration/test。

不要新建第二份“异常大全”，不要把用户草稿整段搬进 note。完整统计和争议留在本 note，后续
经架构师验收后才把稳定摘要回填 `docs/survey/datasets/longmemeval.md` 与
`docs/reference/integration/lightmem.md`。

## 7. 允许与禁止

允许：读取全部上述源码/数据；在 shell heredoc 中运行临时 Python；必要时在系统临时目录放
脚本；新增 §6 唯一 note。

禁止修改：`src/`、`tests/`、`third_party/`、`configs/`、`data/`、`outputs/`、任何 README、
survey、integration、policy、handbook 与用户未跟踪文件。禁止真实 API、下载、全量 pytest、
compileall、自动清洗数据、修改 role、过滤未来 session 或“修正”500ms。

## 8. 唯一定向自检

```bash
uv run pytest -q tests/test_documentation_standards.py
```

另跑 `git diff --check`。数据扫描/探针命令不是测试门，但其原命令与关键 stdout 必须记入 note，
不能只写口头总结。

## 9. 停工条件

- S/M 任一文件无法流式读取，或 source identity 与现行 survey/source-lock 冲突；
- 官方 README、generation 主路径与本卡已裁“完整保留、只披露”发生无法解释的一手冲突；
- production helper 无法在零 API 下追到 placeholder/time/sequence 边界；
- 发现 private label 会进入 method payload/prompt；
- 需要修改 §6 以外文件才能完成审计；
- 定向文档测试失败且 15 分钟内无法定位。

停工时仍把已完成事实、最小复现与冲突点写进唯一 note；不自行发代码修复卡。

## 10. 提交纪律与回报

- `git diff --check`；add 前后各看 `git status --short`；只显式 add 唯一 note，禁
  `git add -A` / `git add .`；本地单 commit，不 amend、不 push。
- commit 建议：`docs(lightmem): audit longmemeval input time semantics`
- Co-Authored-By 只写可核实真实模型；发生换模型按 actor-handbook 披露，不猜身份。
- 按 actor-handbook §4 回报：commit hash、定向测试尾行、实际改动文件、偏差/停工、subagent
  分工与模型切换（如有）。到此停止，等待架构师强验收。

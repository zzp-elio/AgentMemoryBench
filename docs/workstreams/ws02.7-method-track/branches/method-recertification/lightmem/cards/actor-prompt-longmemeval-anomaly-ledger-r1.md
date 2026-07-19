# Actor 卡：LongMemEval source-locked 异常账 R1

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你负责把 LongMemEval 的零散异常调查变成一份 source-locked、可由
Codex/Claude/OpenCode 共同复核的审计 note。不要调用真实 API，不修改 dataset，不直接把主
工作区的 OpenCode 草稿当成结论。actor 可自行组织 subagent，但不得扩大允许范围；如有实质
使用，最终报告须披露分工，主 actor 仍对全部承重结论负责。

## 0. 这张卡解决什么

当前主工作区存在未跟踪草稿：

```text
/Users/wz/Desktop/memoryBenchmark/docs/survey/异常情况/longmemeval.md
```

它包含 OpenCode 的初步扫描、旧行号和若干“异常”定性，但尚未经架构师强验收，不能直接
git add 冒充 canonical 异常账。与此同时，LightMem × LongMemEval 已完成输入/time 审计和
current-v7 B11；这些稳定事实散落在 workstream notes，异常索引仍诚实标为 pending。

本卡要回答：**当前 source-locked LongMemEval S/M 数据里，哪些是真实 schema/annotation
异常，哪些只是合法 edge、来源异质性或 benchmark-native 时间语义；框架与 LightMem 已如何
处置，剩余风险是什么。**只交一份自包含审计 note，架构师验收后再负责把稳定摘要写入
`docs/survey/异常情况/longmemeval.md`，避免与你看见的未跟踪草稿发生覆盖冲突。

## 1. 隔离、必读顺序与事实优先级

- 建议 worktree：`/Users/wz/Desktop/mb-actor-longmemeval-anomaly-ledger`
- 建议 branch：`actor/longmemeval-anomaly-ledger-r1`
- 开工先记录 `git rev-parse --short HEAD` 与 `git status --short`；不得在主工作区施工。
- 新 worktree 缺 gitignored `data/` 或 `third_party/benchmarks/` 时，可建立指向主工作区的只读
  软链；不得复制、修改或暂存这些资产。

按顺序只读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与当前断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
4. `docs/reference/actor-handbook.md`
5. `docs/survey/异常情况/README.md`
6. `docs/workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-source-lock.json`
7. 稳定三联页：
   - `docs/survey/benchmarks/LongMemEval.md`
   - `docs/survey/datasets/longmemeval.md`
   - `docs/survey/workflows/longmemeval.md`
8. 已强验收的差分事实：
   - `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/lightmem-longmemeval-input-time-audit.md`
   - `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/lightmem-longmemeval-latest-main-preflight.md`
   - `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/lightmem-longmemeval-b11-command-pack.md`
9. current source：
   - `src/memory_benchmark/benchmark_adapters/longmemeval.py`
   - `src/memory_benchmark/evaluators/longmemeval_recall.py`
   - `src/memory_benchmark/evaluators/longmemeval_retrieval_rank.py`
   - `src/memory_benchmark/methods/lightmem_adapter.py` 中 LongMemEval 分支
10. 最后只读主工作区草稿，把它当**待逐条证伪的候选清单**，不把文字/行号本身当一手证据。

事实优先级固定为：当前锁定数据与官方源码 > current framework source/tests > 已强验收 notes
> 稳定 survey 页 > 未验收草稿。发现 source lock/hash 与现状不符，立即按 §6 停工。

## 2. 数据范围与取证方式

同时核查 source lock 中的 LongMemEval S 与 M；不能只扫草稿使用的 S 后把结论泛化为两变体。
允许写临时只读 Python 探针到系统临时目录，但不得提交；承重统计的构造方法、语义坐标与完整
stdout 必须抄进 note，使另一个模型不依赖 Claude/OpenCode scratchpad 也能复现。

每个例子优先用：

```text
variant / question_id / question_type / session_id或session index / message index / field
```

JSON 行号仅作辅助。任何“共 N 条”“只有一种”“全部”必须由全量 scan 支撑，并分别报告 S/M
计数；抽样只能写 sample，不得冒充 census。不要打印大段私有 gold；note 中只放证明 shape 所需
的最短节选，method 处置不得接触 answer/has_answer/answer_session_ids。

## 3. 必须逐项裁定的候选

### 3.1 schema 与来源异质性

- answer 的 JSON 类型（包括草稿声称的 int）、金额/逗号/单位等表面格式；确认 current adapter
  是否只在 evaluator-private answer 入口做确定性字符串化，是否改变语义。
- `gpt4_` question id、`answer_` / `answer_sharegpt_` / `answer_ultrachat_` session id 等命名族：
  先查是否违反 schema/唯一性/引用完整性，再决定是异常还是正常来源 provenance；“分布不均”
  本身不是错误。
- duplicate id、missing referenced session、跨 record 泄漏、未知 question_type/role、空 content、
  缺字段、额外字段；分别给 S/M census。

### 3.2 role/session 形状

- assistant-first、user-first、single-user、single-assistant、pure-user、pure-assistant、连续同 role、
  odd retained-turn count、blank message。
- 对草稿中“角色错标”“截断”“内容残留”等主观根因逐条复核：除非一手 metadata/upstream
  代码能证明，不得把 content 看起来像 user 就擅自改 structured role；最多分类为可疑标注。
- 锁定 framework canonical 行为：blank 如何处理；真实 role/content/order 是否原样保留；pair
  如何为 orphan/dangling 补 structural placeholder；是否跨 session 配对；placeholder 是否会
  成为 public turn 或获得伪 source id。
- 锁定 LightMem hybrid 差分：每个 retained real turn 恰一次；官方 user_only 丢失量与当前
  hybrid 保留量；placeholder 不进 extraction 文本但占 method-derived pair/sequence slot。

### 3.3 时间语义

- 分别统计 `question_date < latest/earliest haystack date`、gold session 晚于 question date、同日
  分钟错序；不能把“question 应晚于全部 history”预设为 schema 规则。
- 查 current official generation/evaluation path 是否按 question_date 截掉 future history；若不
  filter，框架必须保留完整 history，不得替 owner 修改 raw timestamp 或创造 corrected time。
- 区分 dataset source time 与 LightMem method-derived tie-break：turn 没独立时间时只继承本
  session raw time；相同 key 的 500ms/sequence 行为、placeholder 影响与 query time 只进 answer
  builder、不进 retrieve filter，都按 current source 写清。
- issue/旧 release 文字只能作历史背景；若无法证明当前 locked release 与评论所述版本同一，
  必须标为 unresolved provenance，不能拿旧评论覆盖当前数据。

### 3.4 gold/evaluator 资格

- 核对官方 user-side `has_answer`/answer-session 规则、当前 canonical denominator、assistant-side
  target 与 no-user-target/abstention 的处置；区分官方主 runner 与辅助 print script 的分母。
- 说明 gold 只进入 evaluator-private group contract；异常 gold 不得因此进入 public Turn、method
  message、retrieve query 或 answer prompt。
- LongMemEval retrieval Recall/rank 对 LightMem 当前应为
  `n_a/pair_source_id_not_turn_exact`；不要为补矩阵硬算。top-k=10 与官方 k30/50、stable ranking
  pending 是独立资格缺口，不得混成 dataset 异常。

## 4. 每条事实的统一分类与处置矩阵

note 中每类候选必须给一行：

| 字段 | 取值要求 |
| --- | --- |
| 分类 | `TRUE_DATA_ERROR` / `LEGAL_EDGE` / `SOURCE_HETEROGENEITY` / `CAPABILITY_LIMIT` / `UNRESOLVED` |
| 稳定坐标与 S/M 计数 | source-locked 语义坐标；没有 census 就明确 sample-only |
| 为什么 | 一手证据，不凭“少见”定罪 |
| canonical adapter | preserve / deterministic normalize / skip blank / fail-fast；不得改 raw data |
| evaluator-private | group、分母、N/A 或披露行为 |
| LightMem 差分 | 已由 pair/hybrid/time 处理，还是仍有真实缺口 |
| 回归锚 | current test/source-lock/note；没有就写 pending |

额外列出“草稿候选 → verified verdict”对照表，逐条指出被证实、改判、需降格或无法复现的内容。
不能用一段总评掩盖草稿中的具体断言。

## 5. 唯一交付物与最小自检

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  longmemeval-anomaly-ledger-audit.md
```

不得修改 `docs/survey/异常情况/longmemeval.md`、README、稳定三联页、src、tests、configs、
third_party、data、outputs、policy 或 handbook。note 必须自包含，至少包含：baseline 与 source
identity、探针复现法/完整 stdout、S/M census、候选逐条裁决、框架/LightMem 处置矩阵、草稿
勘误表、剩余 pending 与唯一总判词：

```text
READY_FOR_ARCHITECT_STABLE_LEDGER_INTEGRATION
```

或：

```text
BLOCKED(<最小矛盾或缺失证据>)
```

只跑：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

提交前只显式 `git add` 唯一 note 路径，禁用 `git add -A` / `git add .`；先看
`git status --short`，本地 commit，不 push、不 amend 其他 commit。

## 6. 停工条件

出现任一项立即停工、写明最小断点并交回架构师：

- current S/M 文件缺失，或 SHA-256/source revision 与 source lock 不符；
- current data/source 与已强验收 note 的承重数字矛盾，且 15 分钟内不能用口径差解释；
- 必须修改 raw data、生产代码、测试或 gold contract 才能继续；
- 需要网络下载、真实 API、`.env`、私有 credential 或输出已有实验资产；
- 唯一交付物不足以诚实表达结论。

## 7. 完成报告

按 `actor-handbook.md §4` 回报：

1. commit hash；
2. 文档标准门尾行与 `git diff --check` 原始结果；
3. 实际改动文件；
4. 偏差/停工点；
5. subagent 分工（如有）；
6. 当前会话真实模型/入口与任何中途切换。

报告最后用三句话分别说明：最重要的 draft 勘误、最重要的 current framework 处置、是否可由
架构师进入 stable ledger 集成。到此停止，等待架构师 full diff 与独立抽锚验收。

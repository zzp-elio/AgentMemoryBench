# Actor 卡：MemoryOS × MemBench current-main 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**本卡只审 MemoryOS × MemBench，不调用真实 API、不修改生产代码、不重做
MemBench 全量异常普查。actor 可自行组织 subagent，但不得扩大范围；主 actor 对结论负责。

## 0. 目标与唯一判词

把 FirstAgent pair-step 与 ThirdAgent singleton/noise 在真实 registered 路径下逐层对表，重点
证明 MemBench message 尾部的 source time 被抽到 MemoryOS typed `timestamp`，同时原 content 的
message/place/time 不删不复制；100k 无时 noise 不被 question time 或 wall clock伪装。

note 最后只能写：

```text
READY_FOR_B11
READY_FOR_B11_WITH_NA(<指标及原因>)
NEEDS_CODE(<最小、可测试的缺口>)
```

本卡不是付费 smoke/冻结授权。

## 1. 隔离与必读

- 建议 worktree：`/Users/wz/Desktop/mb-actor-memoryos-membench`
- 建议 branch：`actor/memoryos-membench-preflight`

依次读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/{README.md,memoryos/README.md}`
4. `docs/reference/actor-handbook.md`
5. `docs/survey/异常情况/membench.md`、`docs/survey/{datasets,workflows}/membench.md`
6. `docs/workstreams/ws02.6-first-smoke-hardening/notes/{membench-source-lock.json,membench-frozen-v1.md}`
7. `docs/reference/integration/memoryos.md` 与点名源码

缺 gitignored data/models 可建只读软链并披露；不联网、不读 `.env`。

## 2. 复用事实

- FirstAgent dict step 已 canonical split 为真实 user child + assistant child；private gold 仍以一个
  step 的 child group any-of 计一次；
- ThirdAgent str step 是单个 user turn，不能编造非空 assistant 回复；
- message 内嵌 `(place: ...; time: 'YYYY-MM-DD HH:MM' ...)` 或无冒号变体时，canonical
  `Turn.turn_time` 逐 turn 解析；原 content 的 message/place/time 全部保留；
- 100k NoiseData 等无合法 time marker 的 turn 保持 `turn_time=None`、`session_time=None`；QA
  `time` 只进 `question_time`；
- source subset、one-to-many ids、smoke step crop 与 evaluator-private group 已冻结。

只轻核 source lock；不得重复全量 census。若为裁单 page timestamp 必须统计“同一 FirstAgent
step 两 child timestamp 是否相同/单侧缺失/双侧不同”，仅做这个有明确决策用途的 source-locked
差量统计，并给脚本/计数/真实坐标。

## 3. 必须亲读的一手链

- MemBench adapter `_turns_from_step()`、`_membench_turn_time()`、metadata marker、smoke crop
- event stream 与 registry `_memoryos_consume_granularity()`
- MemoryOS adapter session ingest、conversation/page converter、event rebuild、timestamp、sidecar、
  retrieve/items/evidence/readout
- product `memoryos.py::add_memory()` 与 `short_term.py::add_qa_pair()` 的 falsy timestamp 分支
- MemBench answer builder（question time）、choice/recall evaluators、registered/adapter tests
- `configs/methods/memoryos.toml`

## 4. production mapping 强反例

用真实 canonical adapter + event stream + fake backend 做 exact-call 探针，至少覆盖：

1. FirstAgent user/assistant 同 timestamp；
2. FirstAgent 仅 user 有 timestamp；
3. FirstAgent 仅 assistant 有 timestamp；
4. 两侧 source timestamp 不同；
5. ThirdAgent singleton 有 timestamp；
6. First/ThirdAgent 无 timestamp noise；
7. 连续 singleton、session 首/尾 placeholder；
8. 原文含 place/time、自然语言单词 time、模板占位但无合法数字 timestamp；
9. question_time 与 message time 明显不同；
10. 两 conversation 同 tid/正文但 isolation 不同。

逐例写：raw step → child Turn(content/turn_time/marker) → TurnEvent → SessionBatch/TurnPair →
`add_memory(user_input, agent_response, timestamp)`。

硬裁决：

- **已知 source time 必须进入产品 typed timestamp 参数**；当前 session converter 若只取
  `session_time=None`，这是确定性 `NEEDS_CODE`，不得以原 content 仍有 time 代替 typed 契约；
- 原 content 继续保留 place/time；typed channel 与正文不是“重复拼前缀”，不得删除正文尾部；
- 缺失 source time 不能用 QA time、兄弟 child、相邻 step/session 或 ingestion wall clock 冒充
  source time。产品若必然把 falsy timestamp 改 wall clock，必须区分“method-derived order time”
  与“source time”，并裁是否需要兼容层/manifest 披露；
- 产品每 page 只有一个 timestamp。两真实 child 不同时间时，不得无声挑一个：实证真实数据
  发生率，再在 note 列“保 pair 取明确 anchor / 拆 singleton page”对算法与 lineage 的影响，
  交架构师裁；
- ThirdAgent 只补 `agent_response=""`，不写任何伪回复；每个 child 恰一次；
- question/private gold 不可达 ingest。

## 5. readout、Recall 与 answer

按 STM/MTM/user knowledge/assistant knowledge 建全层矩阵，检查 formatted memory 是否保留原
place/time，generic benchmark readout 是否误用 LoCoMo speaker map。分别裁：

- MemBench step-group Recall@k 与 turn lineage；
- Precision/F1@k（gold 是否穷尽）；
- stable ranking/NDCG；
- choice accuracy、normalized EM、substring EM 等当前实际注册指标；
- question time 是否只进入 benchmark answer builder。

当前 blanket `valid/turn` 不得免审；`items` 只含部分层时必须 N/A/NEEDS_CODE 或明确子检索语义。

## 6. identity 与 B11 候选

核 registered manifest/resume 的 source、adapter version、consume granularity、evidence 与 track
identity。给出 0-10k 的 FirstHigh+ThirdHigh W1/W2 最小候选，并单列 100k FirstHigh+ThirdHigh
missing-time sentinel；沿用已验收 source-subset CLI 语义。候选按顺序/shape 选，不按 gold 或
效果选；不执行 API、不以 add/page 数估算真实 API calls。

## 7. 唯一交付与自检

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/memoryos/notes/
  memoryos-membench-current-main-preflight.md
```

note 必含 timestamp 差量统计（若需要）、10 类 exact-call、missing-time 与 wall-clock 判词、全层
readout/metric 矩阵、测试盲点、最小补丁蓝图与唯一判词。不得改其它文件。

只运行：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

仅显式 add note，本地 commit 建议 `docs(memoryos): preflight membench current main`；不 push、
不 amend、不跑全量/compileall/真实 API。按 actor-handbook §4 回报后停止。

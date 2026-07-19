# Actor 卡：Mem0 × MemBench current-main 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**只做 Mem0 × MemBench current-main 离线差量审计；不调用真实 API、不改
生产代码、不重做 8 文件全量异常普查。可用 subagent 只读取证，主 actor 负责并披露分工。

## 0. 目标与判词

确认 FirstAgent 一个 source step 展开的真实 user/assistant 两 child、ThirdAgent singleton、原
place/time 文本、100k 无时 noise 与 question time，经 current Mem0 turn ingest 后是否无损、无
重复、无伪造。特别记录 FirstAgent 两 child 当前是一次 pair add 还是两次 turn add；**本卡只
呈现实际行为与影响，不先假定“必须照 LongMemEval pair”或“逐 turn 一定正确”。**

唯一判词：`READY_FOR_JOINT_RULING` 或 `BLOCKED(<最小缺口>)`。

## 1. 环境与必读

- worktree：`/Users/wz/Desktop/mb-actor-mem0-membench`
- branch：`actor/mem0-membench-delta-preflight`
- 记录基线/status，保护所有未跟踪资产。

依次读 `AGENTS.md` → ws02.7 顶部胶囊/断点 → Mem0 子线 README → actor handbook →
`docs/survey/异常情况/membench.md` → MemBench dataset/workflow 稳定页 →
`docs/reference/integration/mem0.md` B2/B4/B5/B9/B11 → 本卡 §3 源码/测试。

缺 data 可只读软链；不联网、不下载、不读 `.env`。

## 2. 稳定事实：禁止重复造轮子

只轻核 source lock：

- FirstAgent dict step 展开为 user/assistant 两 canonical child；private gold 仍以 source step group
  any-of 计一次；ThirdAgent string step 是一个 user child；
- canonical content 原样保留尾部 place/time；typed `turn_time` additive 抽取；
- `source_timestamp_embedded_in_content=True` 仅在真正抽到 source timestamp 时设置；Mem0 因此
  跳过重复 header。100k noise 无尾注时 marker=False、time=None，绝不补 question/sibling/wall
  clock；
- question 自带 `question_time`，只进入 query/官方 answer builder，不进入 history；
- 39 处倒序保持 raw order；off-by-one/empty gold 只由 evaluator-private group处理；
- MemBench turn lineage 对 Mem0 可以是 valid 的前提是每次抽取 memory 的 sidecar 批确为单 turn；
  actor 要核 current 行为，不能只抄旧结论。

source 未漂移就不重扫统计。

## 3. current-main 链

- `benchmark_adapters/membench.py` 的 trajectory/step split、time parser、metadata marker、question builder
- `runners/event_stream.py` 与 granularity aggregator
- `methods/registry.py::_mem0_consume_granularity()` / Mem0 factory
- `methods/mem0_adapter.py` 的 turn/pair/session ingest、`_turn_to_message()`、
  `_effective_time_prefix()`、metadata/provenance/retrieve/evidence
- `configs/methods/mem0.toml`
- MemBench benchmark registration、完整 answer builder、全部 registered evaluators
- `tests/test_membench_conversation_adapter.py`、`test_membench_registered_prediction.py`、
  `test_mem0_adapter.py`、MemBench recall/choice/source tests

Mem0 官方仓库没有 MemBench 专用 harness 时必须明确写“无”，不能拿 LoCoMo/LME 的 chunk size
冒充作者参数；产品 core 形状由并行 core card裁。

## 4. production 调用序列强反例

用 production canonical + runner event + fake Mem0 backend，至少覆盖：

1. 0-10k FirstAgent 一个 dict step；
2. 0-10k ThirdAgent 两个连续 string steps；
3. 两种 `time:` / `time'` 尾注；
4. 100k FirstAgent：有时真实 step + 无时 noise + 下一有时 step；
5. 100k ThirdAgent 同形；
6. 时间倒序但 raw 顺序不变；
7. marker 严格 boolean：True / False / 缺键 / 字符串 `"true"`；
8. session 与 question time 都存在但 history turn time=None。

逐层记录：

```text
source step
→ canonical child turns + private group
→ emitted IngestUnit
→ 每次 Memory.add messages/source_turn_ids/time prefix/metadata
```

必须锁：

- FirstAgent 两 child role/content/place/time 原样；如果当前 consume=`turn`，明确两次 add 的顺序和
  each sidecar；不要用直接调用 pair helper 的测试冒充 registered production；
- ThirdAgent 每 source step singleton，不把两个 user 强配为 conversation pair；
- source content 尾注保留且 content 内 timestamp 只出现原本次数，没有新 `[Turn time]`；
- 100k noise content 不丢、time=None、无 synthetic prefix；下一个有时 turn 不向前/后传播；
- Mem0 content 仍可保留 place（typed channel只抽 time，不删除 place）；
- private answer/target group/question time 不进 add payload。

把“pair 与两次 turn add 的 core 算法差异”作为联合裁决输入；只有 current contract 明确推翻
card 承重事实才 BLOCKED，不为个人偏好改代码。

## 5. readout、metric、identity 与最小 sentinel

核 current：run_id 隔离、formatted memory、unified answer builder 的 question time、MemBench
choice/source/answer metrics 与 retrieval recall、逐题 evidence/granularity/stable ranking、manifest
adapter version/granularity/source identity/resume。

提出无需 API 的 B11 shape：0-10k W1/W2 主烟与 100k FirstHigh+ThirdHigh missing-time sentinel
哪些旧资产可复用、哪些因 Mem0 identity/code变化需重跑。不要直接批准真实 API，不把
zero-extraction 当故障，也不从 LightMem run 代证 Mem0。

## 6. 唯一交付与门

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
  mem0-membench-delta-preflight.md
```

note 要自包含 probe 构造/stdout、八类 mapping、turn-vs-pair 裁决输入、time/place/privacy、metric/
identity与唯一判词。不得改其他文件。

只跑 `uv run pytest -q tests/test_documentation_standards.py` 与 `git diff --check`；显式 add 唯一
note，status 过目，本地 commit 建议 `docs(mem0): preflight membench delta`，不 push/amend/
full pytest/compileall/API。按 actor-handbook §4 回报后停止。

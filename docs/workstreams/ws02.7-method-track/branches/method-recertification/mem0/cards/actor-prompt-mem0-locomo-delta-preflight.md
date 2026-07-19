# Actor 卡：Mem0 × LoCoMo current-main 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**本卡只审 Mem0 × LoCoMo 的 current-main 差量，不调用真实 API、不修改
生产代码、不重新普查整个 LoCoMo。actor 可自行组织 subagent，但不得扩大允许范围；实质使用
须在报告披露，主 actor 对所有结论负责。

## 0. 目标

回答当前 canonical LoCoMo 是否被 Mem0 产品 adapter 忠实地变成 named-speaker message：role、
speaker 前缀、session time、image caption、单 turn add、isolation 与 retrieval evidence 是否都
满足最小 B11 smoke。必须分开旧双 speaker namespace harness 与当前单 namespace harness。

唯一总判词：

```text
READY_FOR_JOINT_RULING
```

或：

```text
BLOCKED(<最小代码/身份缺口>)
```

这不是付费 smoke 授权，也不是直接冻结。

## 1. 隔离环境与必读

- 建议 worktree：`/Users/wz/Desktop/mb-actor-mem0-locomo`
- 建议 branch：`actor/mem0-locomo-delta-preflight`
- 记录基线 hash/status；用户未跟踪资产不得暂存或删除。

依次读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊/最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/README.md`
4. `docs/reference/actor-handbook.md`
5. `docs/survey/异常情况/locomo.md`
6. `docs/survey/{datasets,workflows}/locomo.md`
7. `docs/reference/integration/mem0.md` 的 B2/B4/B5/B9/B11
8. 本卡 §3 点名源码、测试和两条官方 harness

若 worktree 缺 gitignored `data/`，可建只读软链到主工作区；不得联网下载、读 `.env` 或修改
raw data。

## 2. 复用的 benchmark 稳定事实

禁止重算全量 census；只以 source lock 轻量确认身份未漂移，并消费稳定账：

- LoCoMo 是两个 named human speakers，不是天然 user/assistant agent 对话；canonical turn 保留
  speaker、`dia_id`、原 content 与顺序；
- 140/272 session 为奇数 turn，不能丢尾 turn或跨 session 配对；
- 5,882 turn 无独立 timestamp，source time 只回落所属 session time；
- caption/URL/query 已在 canonical `ImageRef` 结构保留；文本 method 的目标语义是原 content
  加共享 `[Sharing image that shows: {caption}]`（有多图则逐个稳定追加），不把 locator/query
  私自写进正文；
- date-only keys、malformed/empty private evidence、重复 occurrence 都由 canonical/private
  evaluator 层处理，method 不得特判；
- smoke 的 rounds/questions 只是预算裁剪，不改 canonical id 或数据。

若当前 source lock 不同才停工；不得因本卡重新扫描得到相同数字而制造一份重复异常账。

## 3. 必须亲读的一手链

- `src/memory_benchmark/benchmark_adapters/locomo.py` 的 session/turn/image 构造与 smoke crop
- `src/memory_benchmark/runners/event_stream.py::build_turn_events()`
- `src/memory_benchmark/methods/registry.py::_mem0_consume_granularity()` 与 Mem0 factory
- `src/memory_benchmark/methods/mem0_adapter.py`
  - `_ingest_native_turn()`、`_turn_from_event()`、`_turn_to_message()`、
    `_effective_time_prefix()`、`_add_with_provenance()`、`_retrieve_native()`、
    `_build_retrieval_evidence()`
- `src/memory_benchmark/methods/image_text.py`
- `configs/methods/mem0.toml`
- current harness：
  `third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py`
- legacy/paper harness：
  `third_party/methods/mem0-main/evaluation/src/memzero/{add,search}.py`
- LoCoMo evaluator registry 与相关 `tests/test_mem0_adapter.py`、
  `tests/test_locomo_registered_prediction.py`、image helper tests

核心 `Memory.add()` 是否要求 role 交替由并行 core card最终裁决；本卡只记录实际调用序列，不能
以模型常识代判。

## 4. 两代官方姿势必须对表

列出至少这些字段：入口年代/用途、调用本地 core 还是 REST、namespace 数量、每个 namespace
收到的 role 视角、speaker 前缀、chunk size、timestamp、image wrapper、search 合并方式。

特别核清：

1. legacy `speaker_a_user_id` / `speaker_b_user_id` 是否真是两次独立写入和两次检索；
2. current `memory-benchmarks` 是否一个 conversation 一个 `user_id`、`CHUNK_SIZE=1`；
3. framework 一个 `run_id` + physical worker isolation 与哪条更接近；
4. legacy 双视角若属于论文复现行为，只能列 future `author_locomo` 候选，不得因“官方”二字
   暗中混入 unified 主轨。

## 5. production 映射与强反例

用 canonical adapter + production event + fake Mem0 backend 做零 API 探针；fake 只记录
`Memory.add()` 收到的 exact arguments，不伪造 core 兼容结论。至少覆盖：

1. Speaker A 与 Speaker B 各一条；
2. 同一 speaker 连续两条；
3. 奇数 session 尾 turn；
4. 跨 session 边界；
5. text-only；
6. text + caption；
7. caption-only；
8. URL/query/caption 同时存在；
9. 多 caption；
10. 空白 caption/无 image。

逐例记录：

```text
raw turn
→ canonical Turn/ImageRef/session_time
→ TurnEvent
→ Memory.add(messages, run_id, metadata, prompt)
```

锁死：

- 每个真实 utterance 恰一次；consume granularity 的真实值与 manifest 一致；
- role 是稳定 speaker 映射，content 必须含 named speaker；不要把 Speaker B 内容误当无事实的
  agent 回复；
- 每条 message 只含一个 effective session time，不能混 question time/wall clock；
- 原 text bytes 不丢；caption wrapper 与共享 helper/官方 blip-only 分支做字节对表。**若当前
  adapter 仍裸拼 caption 或漏 caption，必须判 BLOCKED，不得用“文字大致相同”放行**；
- `img_url`、`query`、private evidence 不进入 content/method metadata；
- source_turn_ids 只含当前 turn，namespace 不串 conversation。

临时脚本不提交；note 必须写清 probe 构造与关键 stdout，不能引用 Claude/Codex 私有 scratchpad。

## 6. retrieve / prompt / metric / identity

核对当前 registered run 的：

- product `Memory.search(filters={run_id})`、top_k、formatted memory 的 time/readout；
- benchmark unified 完整 answer builder 获得 formatted memory、question、question time；不运行
  legacy native/author builder；
- LoCoMo RetrievalEvidence 是否逐题 `valid/turn`，stable ranking 是否仍 pending；Recall/answer
  指标只列当前 registry 实际启用项；
- adapter/source/protocol/track identity 与 resume 字段；
- TOML current smoke 参数只抄 current source，不从旧 frozen note猜。

不得改变 metric 公式、gold group、prompt、TOML 或 top_k。

## 7. 唯一交付、自检与回报

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
  mem0-locomo-delta-preflight.md
```

note 含 source identity、两代 harness 表、10 类映射、caption/time/speaker 裁决输入、metric/identity
矩阵、现有测试盲点与唯一总判词。不得改 README/survey/integration/src/tests/config/third_party/
data/outputs/policy/handbook。

只运行：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

仅显式 add 该 note，检查 status，本地 commit 建议
`docs(mem0): preflight locomo delta`；不 push、不 amend、不跑全量/compileall/真实 API。
按 actor-handbook §4 报 hash、尾行、文件、偏差/停工、subagent 与真实模型/入口；到此停止。

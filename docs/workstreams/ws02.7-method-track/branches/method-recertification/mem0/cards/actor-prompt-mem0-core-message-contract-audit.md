# Actor 卡：Mem0 产品 messages / namespace / time 契约审计

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你只做当前 vendored Mem0 产品 core 的离线一手审计与证据记录，不调用
真实 API，不修改生产代码。actor 可自行组织 subagent，但不得扩大允许范围；若当前 actor 是
Fable 5，**明确允许 Fable 自启 subagent 分包只读取证**，主 actor 仍须亲核所有承重锚并对最终
报告负责。

## 0. 目标与唯一判词

用户要确认 Mem0 虽接受 `str | dict | list[dict]`，其底层是否暗含严格
`user→assistant→user...` 交替假设，以及连续同 role、assistant-first、单侧消息、分批 add
是否改变或破坏抽取。还要把两代官方 LoCoMo 姿势分开：旧
`evaluation/src/memzero/` 使用两个 speaker namespace 并反转 role；当前
`memory-benchmarks/benchmarks/locomo/` 使用一个 conversation `user_id`。不得把两条 harness
揉成一个“官方默认”。

最后只能给出：

```text
CORE_CONTRACT_READY(<可支持形状与明确限制>)
```

或：

```text
CORE_CONTRACT_BLOCKED(<无法由一手源确定的最小问题>)
```

本卡不裁五个 benchmark 应选择何种 consume granularity，也不顺手修代码。

## 1. 隔离环境与必读顺序

- 建议 worktree：`/Users/wz/Desktop/mb-actor-mem0-core-contract`
- 建议 branch：`actor/mem0-core-contract-audit`
- 开工记录 `git rev-parse --short HEAD` 与 `git status --short`；主工作区现有未跟踪资产属于用户，
  不得暂存、删除或搬动。

依次只读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/README.md`
4. `docs/reference/actor-handbook.md`
5. `docs/reference/integration/mem0.md` 的接口调用面、B1、B2、B4、B5、B8、B9
6. `docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
   mem0-provenance-validity-audit.md` 的结论与可达链
7. 本卡 §3 点名的一手源码与测试

不得联网拉新 Mem0、不得把 PyPI/GitHub latest 与当前 source-locked vendored core 混用；版本
drift 是后续独立事项。

## 2. 已验收事实：只查 drift，不重做

1. 当前 framework 调的是 vendored OSS `Memory.add/search` 产品接口，不以 benchmark harness
   代替产品 core。
2. adapter 当前只传 `run_id=isolation_key`，不是 `user_id` 或 `agent_id`；worker 间 backend
   物理隔离，worker 内用 namespace 逻辑隔离。
3. 2026-07-15 current reachable mutation 审计判为 `ADD_ONLY_MUTATION_PROVEN`；sidecar 记录
   ingest 批归属，不自动等于 fact-level turn provenance。本卡只做轻量 drift check，禁止重新
   扫完整 mutation 图。
4. OSS `Memory.add()` 没有独立 timestamp 参数。framework 对 content-only Mem0 使用唯一
   effective time：`turn_time → session_time → None`；MemBench 原文已内嵌 time 时不再重复 header，
   metadata 另存用于审计。
5. 当前 smoke 配置保持 MiniLM/gpt-4o-mini；product-default embedding 与 TOML profile 迁移不在
   本卡。

任何一条被 current source 推翻都立即停工，记录精确锚点，不能把矛盾静默改成新前提。

## 3. 必须亲读的一手链

### 3.1 产品 core

- `third_party/methods/mem0-main/mem0/memory/main.py`
  - `_build_filters_and_metadata()`、`Memory.add()`、`_add_to_vector_store()`；
  - `infer=True` 的 Phase 0–8，尤其 `last_messages`、`parse_messages()`、extraction prompt、
    `save_messages()` 与返回 `results`；
  - `infer=False` 只用于边界对照，不得拿来替代主配置。
- `third_party/methods/mem0-main/mem0/memory/utils.py::parse_messages()`
- `third_party/methods/mem0-main/mem0/memory/storage.py` 的 message schema、
  `save_messages()`、`get_last_messages()`
- `third_party/methods/mem0-main/mem0/configs/prompts.py` 中当前实际被 phased extraction 使用的
  system/user prompt 生成器
- 当前 framework：`src/memory_benchmark/methods/mem0_adapter.py` 的 `ingest()`、三条
  `_ingest_native_*()`、`_turn_to_message()`、`_add_with_provenance()`、`retrieve()`；
  `src/memory_benchmark/methods/registry.py::_mem0_consume_granularity()` 只作调用形状背景。

### 3.2 三条“官方”入口必须分层

1. current product benchmark harness：
   - `memory-benchmarks/benchmarks/locomo/run.py`
   - `memory-benchmarks/benchmarks/longmemeval/run.py`
   - `memory-benchmarks/benchmarks/beam/run.py`
   - `memory-benchmarks/benchmarks/common/mem0_client.py`
2. legacy/paper LoCoMo：
   - `evaluation/src/memzero/add.py`
   - `evaluation/src/memzero/search.py`
3. 普通产品 examples/tests：选最小能证明连续 role、单 message、多 message 与多次 add 的一手
   样例；不要全文扫 examples。

对每条入口写明：调用的是本地 product core、REST client 还是另一版本；namespace 形状、消息
形状、时间参数、chunk size；它能否代表 Phase 1 unified 主轨，还是只能作为
`author_locomo`/历史复现参考。

## 4. role 与 batch 契约必须实证

用 current production helper + hermetic fake LLM/embedder/vector/message-store 或已有 unit tests
做零 API 探针。至少覆盖以下输入，分别测试“同一次 add 的 list”与“连续多次 add”中有意义的
组合：

1. `user→assistant`；
2. `user→user`；
3. `assistant→assistant`；
4. assistant-first `assistant→user`；
5. singleton user；
6. singleton assistant；
7. 三条或五条奇数序列；
8. system 与未知 role 的边界（只说明产品行为，不建议 benchmark 注入未知 role）。

逐层写出：

```text
Memory.add input
→ messages normalization / vision normalization
→ parse_messages exact text
→ last_k_messages scope
→ extraction LLM 实际收到的 system+user payload
→ db.save_messages exact order
→ returned results
```

回答这些承重问题：

- core 是否运行期校验 role 交替、首 role、尾 role、偶数长度；若不校验，是否仍有后续 provider
  或 prompt 隐式改变内容；
- raw roles 是直接交给 extraction model，还是先被序列化进一个 user prompt；连续同 role 会不会
  被合并、丢弃、交换或只保留最后一条；
- 每次 add 的 `last_messages(limit=10)` 是否让上一批进入下一批上下文；一批两条与两批各一条
  是否算法等价，若不等价，差异属于 batch identity 而非“能否运行”；
- 空 content、未知 role、缺 role/content 的确切 fail/skip/silent 行为；
- extraction 失败、零 memory 与正常 ADD 时 raw messages 是否都按相同 scope 保存。

禁止用真实 LLM 输出质量来证明结构契约；fake 必须记录实际 prompt/call/order，关键 stdout 与
探针构造要抄进 note，不能只引用会话 scratchpad 路径。

## 5. namespace / 双 speaker / time 专查

### 5.1 namespace

画出 `user_id`、`agent_id`、`run_id` 如何进入 metadata、search filter、message
`session_scope`。明确：

- 同一 add 是否允许同时给多个实体 id；多个 id 是“两个独立记忆库”还是一个复合 scope；
- legacy LoCoMo 的 `speaker_a_user_id` 与 `speaker_b_user_id` 是两次独立 add/search 还是一次调用
  传两个 user id；它为何要构造 `messages` 与 `messages_reverse`；
- current memory-benchmarks LoCoMo 的单 `user_id` 与 framework 单 `run_id` 在算法/隔离上属于
  `CONFIG_EQUIVALENT`、`BEHAVIOR_VARIANT` 还是无法判定；给出理由，不凭名称判断；
- assistant 内容何时触发 agent-memory extraction：只在 `agent_id` 存在时，还是普通 run/user
  scope 也会由 additive prompt 抽取 named assistant facts。

### 5.2 time

区分三层：benchmark harness REST `timestamp` 参数、product core `Memory.add()` 签名、framework
content+metadata。实证 extraction prompt 真正能看到哪一层；不得看到 metadata 被持久化就推断
LLM 看见它，也不得因为 REST client 接受 timestamp 就给本地 core 发不存在的参数。

### 5.3 speaker/image

确认 named speaker 前缀是否是 current/legacy LoCoMo 两条官方路径的共同语义；确认 current
phased prompt 对 assistant 侧 named speaker fact 的规则。这里只查 core 语义，不代 LoCoMo 卡
裁 caption renderer。

## 6. 唯一交付物与停点

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
  mem0-core-message-contract-audit.md
```

note 至少包含：source identity、三类入口身份表、八种 role/batch 探针、namespace 图、time 可见
链、明确限制、给五张 benchmark 卡的契约输入、唯一总判词。不得修改 README、integration、
survey、src、tests、configs、third_party、data、outputs、policy 或 handbook。

立即停工并报告：current source 与 §2 冲突；必须联网/真实 API 才能判；需要改算法 core；或需写
允许清单外文件。探针无法在 20 分钟内 hermetic 化时，保留静态一手链并把动态点标 pending，
不要伪造“已实测”。

## 7. 自检、commit 与回报

只运行：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

仅显式 `git add` 上述 note，先后查看 `git status --short`；本地 commit 建议
`docs(mem0): audit product message contract`，不 push，不 amend，不跑全量 pytest/compileall，
不读 `.env`。

按 `actor-handbook.md` §4 回报：commit hash、自检尾行、实际改动文件、偏差/停工点、subagent
分工、真实模型/入口及任何切换。到此停止，等待架构师联合裁决。

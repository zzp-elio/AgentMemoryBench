# Actor 卡：LightMem × LongMemEval latest-main B11 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你负责离线差量预检与证据记录，不调用真实 API，不直接修改生产代码。
actor 可自行组织 subagent，但不得扩大本卡允许范围；如有实质使用，最终报告须披露分工，主
actor 仍对所有结论负责。

## 0. 这张卡解决什么

LightMem 的 LoCoMo latest-main v6 已完成真实单/双 worker smoke。用户现决定在离开 LightMem
之前继续逐格压实 LongMemEval。本卡不是重新调查整个 LongMemEval，也不是重新扫描 2.5GB M
数据；它只回答：**当前 main 的 canonical adapter → pair event → LightMem hybrid message →
retrieve/readout → metric eligibility 是否已具备一次最小付费 B11 smoke 的条件。**

完成后必须给出唯一总判词：

```text
READY_FOR_B11_SMOKE
```

或：

```text
BLOCKED(<最小缺口列表>)
```

若发现缺口，只记录最小复现与建议修复边界，不在本卡顺手改代码。

## 1. 隔离环境与必读顺序

- 建议 worktree：`/Users/wz/Desktop/mb-actor-lightmem-lme-preflight`
- 建议 branch：`actor/lightmem-lme-preflight`
- 基线：用户创建 worktree 时包含本卡的最新 `main`；开工先记录
  `git rev-parse --short HEAD` 与 `git status --short`

严格按顺序读最少文件：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
4. 已验收事实源：
   `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
   lightmem-longmemeval-input-time-audit.md` 的 §1、§2、§4、§6、§8
5. `docs/reference/actor-handbook.md`
6. 本卡 §3 点名的源码、配置与测试

用户主工作区有未跟踪草稿
`/Users/wz/Desktop/memoryBenchmark/docs/survey/异常情况/longmemeval.md`。同机可只读，把它当
待证伪例子索引；不得修改、暂存、整段复制或把草稿本身当一手事实。新 worktree 缺
gitignored `data/` / `models/` / `third_party/benchmarks/` 时，允许只读软链到主工作区，提交前
确认未暂存。
不得读取或打印 `.env`；配置型测试需要 key 时使用假值并把 base URL 指向不可达本机端口。

## 2. 已裁事实：禁止重复做大审计

以下结论已经 Opus 4.8 主体 + 架构师 R1 强验收，本卡只检查当前 main 是否仍与之相符：

1. S/M raw turn=`246,750 / 2,446,993`，blank=`12 / 295`；framework 跳过 blank 后，每个
   retained canonical turn 恰好进入一个 pair 一次。
2. assistant-first、pure-assistant、同 role 连续、奇数 turn 都是 benchmark-native shape；
   canonical role 只读结构化 `role`，不得从 content 猜测或重写角色。
3. 正常相邻 `user→assistant` 保持 real-real pair；孤立 user 配 empty assistant
   placeholder；孤立 assistant 配 empty user placeholder；不得跨 session 配对。
4. placeholder 不是 public turn、没有新 source id，从 extraction 文本和 token 计数中过滤，
   但会占 LightMem pair/sequence slot；这是已披露的 framework extension。
5. LongMemEval turn 没有独立时间，每个真实 turn 继承所属 session 的 raw time。相同 raw time
   的 slot 会产生 500ms method-derived tie-break；不得改 raw 数据、不得合成 corrected time。
6. `question_date` 同日分钟错序不作 as-of cutoff；官方主路径保留全部 history。框架原样传
   question time 给 answer builder，但 retrieve 必须保持 `filters=None`。
7. Phase 1 主 build 是 `messages_use="hybrid" + lifecycle_profile="online_soft"`；官方 Table 2
   `user_only` 是 future `author_longmemeval` reproduction，不得冒充主 profile。
8. LightMem 对 LongMemEval 的 pair candidate ids 不能证明事实来自 pair 中哪个 child，故
   semantic retrieval evidence 必须为 `n_a/pair_source_id_not_turn_exact`；rank 也不得硬算。

不得重跑 M 全量统计、重新浏览 issue、下载数据、重新争论 500ms 算法或把上述数字当目标凑数。
若当前一手源码真的冲突，记录冲突并停工。

## 3. 必须亲读的 current-main 链路

只读以下承重点，不全文扫仓库：

- `src/memory_benchmark/benchmark_adapters/longmemeval.py`
  - `_sessions_from_instance()`、`_session_from_raw()`、`_turn_from_raw()`、
    `_public_message_metadata()`
- `src/memory_benchmark/runners/event_stream.py`
  - `build_turn_events()`、`EventStreamAggregator._aggregate_pairs()`
- `src/memory_benchmark/methods/registry.py`
  - `_build_lightmem_system()` 与 LightMem registration
- `src/memory_benchmark/methods/lightmem_adapter.py`
  - `LightMemConfig`、`ingest()`、`end_session()`、`end_conversation()`、
    `_native_pair_batch()`、`_real_message()`、`_placeholder_message()`、
    `_write_native_batch()`、`retrieve()`、`_build_retrieval_evidence()`、
    `_turn_timestamp()`
- `configs/methods/lightmem.toml`
- `src/memory_benchmark/benchmark_adapters/registry.py` 的 LongMemEval prompt/contract 注册
- `src/memory_benchmark/evaluators/registry.py`
- `src/memory_benchmark/evaluators/longmemeval_recall.py`
- `src/memory_benchmark/evaluators/longmemeval_retrieval_rank.py`
- `src/memory_benchmark/methods/config_track.py` 与
  `lightmem_native_prompts.py` 只用于确认 legacy native 是 readout-only，本轮 smoke 仍为 unified
- 对应 `tests/test_*longmemeval*` 与 `tests/test_lightmem_adapter.py` 的相关用例

## 4. 六类输入映射必须逐层实证

用 production adapter/helper + fake backend 做零 API 探针；可从 S 数据取公开例子，也可加最小
synthetic 强反例。至少覆盖：

1. 正常 `user→assistant`；
2. assistant-first；
3. `user→user`；
4. `assistant→assistant`；
5. 单 user；
6. 单 assistant。

每类写出：

```text
raw role/content/session time
→ canonical Turn(turn_id, speaker, normalized_role, content, public metadata)
→ TurnPair(first/second/orphan/dangling)
→ LightMem [user, assistant] message dict
→ 实际 add_memory batch 边界与 force_segment/force_extract
```

并锁死这些不变量：

- 真实 turn 的顺序、次数、content bytes 与 canonical turn id 不变；
- `speaker_id/speaker_name` 来自真实结构化 role（LME 为 user/assistant），不拼 role header；
- 每个 real message 有 `external_id`，pair 两侧 `source_external_ids` 是同一个完整 candidate-id
  list；placeholder 只有严格 boolean marker 才被过滤；
- `messages_use="hybrid"` 时 extraction 可见文本包含 pair 中每条 real user/assistant 恰一次，
  不包含 placeholder；
- 同一 session 的尾 user 与下一 session 的首 assistant 不得组成 real-real pair；
- `has_answer`、answer、answer_session_ids、gold evidence 与 judge label 不得出现在 public Turn、
  message dict、retrieve query、answer prompt 或 method metadata。

若现有 test 只证明 helper 输出、未证明 v3 `TurnPair → ingest → pending batch → final flush`，用临时
fake probe 补证据；临时脚本不得提交。

## 5. 时间、query 与 readout 专查

必须分别回答：

1. source time：turn_time 缺失时是否只回落到本 session time；是否存在 question time、相邻
   session、首个有时 turn或 wall clock 回填；
2. method-derived time：同 raw session time 的 pair slots 如何递增；placeholder 是否只影响已
   披露的派生 slot，不改 source session time；
3. retrieve：当前 registered LightMem × LongMemEval 是否固定
   `embedding_retriever.search(..., filters=None, return_full=True)`；question time 是否只进入 answer
   prompt，不成为检索过滤；
4. unified answer：最终 builder 是否拿到 formatted memory、question、question time，并生成可
   直接调用 answer LLM 的最终 messages；不能只看模板文本；
5. legacy native：只确认 LoCoMo/LME bundle 仍存在且身份为 `readout_only`、
   `build_override_applied=false`；不得运行或建议本轮付费双跑。

## 6. 当前 smoke 配置与 lifecycle 对表

从 TOML → 强类型 config → registry factory → manifest builder 逐项核对，不从旧文档抄值：

- `llm_model`
- embedding path/dimension/distance
- `retrieve_limit`
- `extract_threshold`
- `pre_compress` / `compression_rate`
- `stm_threshold` / `topic_segment` / `text_summary`
- `messages_use`
- `lifecycle_profile`
- `missing_timestamp_policy`
- API timeout/retry 与 method max_workers
- adapter/protocol/source identity

确认 LongMemEval 主 profile不触发 `construct_update_queue_all_entries()` 或
`offline_update_all_entries()`；`force_segment/force_extract` 的最后一批刷洗不等于全库 offline
consolidation。发现文档/TOML/运行身份不同，以源码+TOML为准并报告 drift，不代改。

## 7. metric eligibility 与 smoke 覆盖面

列出 current registry 的全部 LongMemEval evaluator，并分成：

- 付费：官方 parity judge；
- artifact-only answer：token-F1、normalized EM、directional substring EM；
- artifact-only retrieval：LongMemEval recall 与 rank 壳层仍应执行，但 LightMem 的逐题 evidence
  应诚实输出 N/A，不得产生伪分数；rank 另有 stable-ranking pending 与 top-k 10/官方 k30/50
  深度缺口。

通过 fake artifact 或现有强反例确认：`n_a/pair_source_id_not_turn_exact` 能被 recall/rank evaluator
消费并生成 N/A summary，而不是报错、0 分或偷偷回落 run 级 granularity。不要改 evaluator 公式、
gold group、419 分母或 retrieval query depth。

最后提出**不调用 API**的 B11 smoke 建议规模，供架构师回卡后写命令：

- 使用 S variant；
- 至少一个普通 user→assistant instance；
- 至少一个包含 assistant-first / 同 role / 单侧 session 的公开结构异常 instance；
- 选择只按公开输入形状与成本，不用 private answer/evidence 选择“容易命中”的题；
- 报告每个候选的公开 question id、session/retained-turn 数、预计 add pair 数，不展示 gold。

## 8. 唯一交付物

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-longmemeval-latest-main-preflight.md
```

note 至少包含：

1. baseline/source/config identity；
2. 已验收旧事实与本轮差量范围；
3. 六类输入逐层映射表；
4. time/query/readout 结论；
5. config/lifecycle 对表；
6. evaluator 资格矩阵；
7. 现存测试覆盖与临时 probe 输出；
8. `READY_FOR_B11_SMOKE` 或 `BLOCKED(...)`；
9. 若 ready，列公开候选与成本形状；若 blocked，列最小修复卡输入。

不得修改 README、integration、survey、src、tests、third_party、configs、data、outputs、policy 或
handbook。稳定摘要由架构师强验收后回填。

## 9. 自检与报告

数据可读后只跑一次直接相关测试集：

```bash
OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9 \
uv run pytest -q \
  tests/test_lightmem_adapter.py \
  tests/test_lightmem_native_prompts.py \
  tests/test_lightmem_registered_prediction.py \
  tests/test_longmemeval_conversation_adapter.py \
  tests/test_longmemeval_prompt.py \
  tests/test_longmemeval_registered_prediction.py \
  tests/test_longmemeval_retrieval_recall.py \
  tests/test_longmemeval_retrieval_rank.py
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

若测试意外尝试网络，立即中止并报告，不为过测改测试/生产代码。禁止全量 pytest、compileall、
真实 API、下载与 benchmark 全量重扫。

仅显式 add 唯一 note，禁止 `-A`/`.`；commit 前查看 `git status --short`。建议 commit：

```text
docs(lightmem): preflight longmemeval latest main
```

按 actor-handbook §4 回报：commit hash、两条测试尾行、实际改动文件、总判词、偏差/停工点、
subagent 与模型/入口切换。不要 push；到此停止，等待架构师强验收。

## 10. 停工条件

- current-main 一手源码推翻 §2 已裁事实；
- public/private 边界泄漏到 method 可见对象；
- 六类 retained real turn 有丢失、重复、跨 session 配对或 role 猜测；
- LongMemEval retrieve 使用 question time 过滤完整 history；
- online-soft 主 profile 暗跑全库 consolidation；
- LightMem retrieval evaluator 对 N/A 产生数值分数；
- 完成本卡必须修改唯一 note 以外文件；
- 直接相关测试失败且 15 分钟内确认不是缺 data/model/.env 的环境问题。

触发停工仍提交已完成 note，保留最小复现；不得自行扩成修复卡。

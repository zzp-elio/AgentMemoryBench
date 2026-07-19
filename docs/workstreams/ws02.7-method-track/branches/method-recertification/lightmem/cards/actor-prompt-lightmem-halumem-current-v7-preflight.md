# Actor 卡：LightMem × HaluMem current-v7 差量预检

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你负责 source-locked、零 API 的 current-v7 差量预检与自包含证据 note；
不运行真实 smoke，不直接修改生产代码。actor 可自行组织 subagent，但不得扩大本卡允许范围；
如有实质使用，最终报告须披露分工，主 actor 仍对全部承重结论负责。

## 0. 这张卡解决什么

HaluMem benchmark 侧已经 frozen-v1，Medium/Long 全量结构、官方三操作、prompt、metric、固定
smoke 形状与 resume 契约都有 source lock 和测试；LightMem 也在 2026-07-14 跑过历史 smoke。
此后 LightMem 发生了 hybrid role、online-soft、缺时、RetrievalEvidence、readout、embedding
观测与 adapter v7 等改动。**本卡只判断 current main 的 LightMem × HaluMem 差量链是否仍可按
同一固定形状进入一次真实 B11 smoke。**

这不是重新调查 HaluMem，也不是重跑 Medium/Long census。完成后只给一个总判词：

```text
READY_FOR_HALUMEM_B11_COMMAND
```

或：

```text
BLOCKED(<最小缺口列表>)
```

若发现代码缺口，只保存最小复现与建议修复边界，不在本卡顺手施工。

## 1. 隔离环境与开工命令

在主仓最新 `main` 上创建独立 worktree；若目录或分支已存在，不删除、不 reset，先停工报告：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-lightmem-halumem-preflight \
  -b actor/lightmem-halumem-current-v7-preflight main
cd /Users/wz/Desktop/mb-actor-lightmem-halumem-preflight
git rev-parse --short HEAD
git status --short
```

新 worktree 缺 gitignored `data/`、`models/`、`third_party/benchmarks/` 时，可创建指向主工作区
同名资产的只读软链；不得复制、修改或暂存这些资产。不得读取或打印 `.env`。测试若只因配置
需要 key，使用 `OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9`，且任何意外网络尝试都要立即
中止。

## 2. 最少必读顺序

严格按顺序读取，不全文扫描历史：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/README.md`
4. `docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/README.md`
5. `docs/reference/actor-handbook.md`
6. benchmark 稳定事实：
   - `docs/survey/datasets/halumem.md`
   - `docs/survey/workflows/halumem.md`
   - `docs/workstreams/ws02.6-first-smoke-hardening/notes/halumem-frozen-v1.md`
   - `docs/workstreams/ws02.6-first-smoke-hardening/notes/halumem-source-lock.json`
7. method 历史与 current 差量：
   - `docs/reference/integration/lightmem.md` 的 B2、B5、B6、B7、B11 及 HaluMem 小节
   - 本卡 §4 点名的 current source/config/tests

## 3. 继承事实：禁止重做 census

先只重算 `halumem-source-lock.json` 已列 Medium/Long 文件的 SHA-256 与字节数。若逐字匹配，
直接继承以下已强验收事实；**不得再流式全扫两份数据、重算规模、角色、时间或 memory-point
分布**：

1. Medium=`20 user / 1,387 session / 60,146 turn / 3,467 question`；Long 仅额外含
   1,030 个 generated-QA session，总题数同为 3,467。
2. 对话全库严格 `user→assistant` 交替，turn timestamp 与 session start/end 三层齐全；无需
   用 placeholder 修正常规数据。
3. 491 个普通 session 缺 `questions` 键；Long 的 1,030 个 generated-QA session 有空 questions、
   无 memory_points，只 ingest，不生成 probe/QA。
4. `is_update` 是字符串 `"True"/"False"`，不能按 Python truthiness；更新点还须有
   `original_memories`。
5. `evidence` 是 `{memory_content,memory_type}` 列表，没有 turn id，所以 HaluMem retrieval
   Recall/NDCG 必须 N/A，不能做文本猜映射。
6. operation-level 顺序是每 session 的 ingest → session memory report → update probes → QA，
   不是先建完全部 memory 再统一答题。
7. smoke 形状已冻结：Medium 首 conversation，4 session × 每 session 前 2 turn × 1 QA；
   operation-level 只支持单 worker，smoke resume 禁用。
8. 官方 answer builder 不要求 question time；框架不得另造 question time 槽。

只有 source hash/字节漂移、current shared contract 推翻上述事实，或发现新的第一手反证时才停工
重开 benchmark 层。整理稳定异常账不是重开触发器。

## 4. 必须亲读的 current-main 承重点

只读符号邻域，不全文扫仓库：

- `src/memory_benchmark/benchmark_adapters/halumem.py`
  - fixed smoke preparation、session/question/private metadata 构造、unified answer builder
- `src/memory_benchmark/runners/event_stream.py`
  - `build_turn_events()` 与 session aggregator
- `src/memory_benchmark/runners/operation_level.py`
  - session ingest/report、update probe、QA、generated session、resume 与 worker 门
- `src/memory_benchmark/methods/registry.py`
  - `_lightmem_consume_granularity()`、`_build_lightmem_system()`、HaluMem registration identity
- `src/memory_benchmark/methods/lightmem_adapter.py`
  - `ingest()`、`_ingest_halumem_session()`、`_capture_inserted_memories()`、
    `_halumem_session_messages()`、`end_session()`、`retrieve()`、
    `_build_retrieval_evidence()`、embedding/LLM observer 与 readout formatter
- `configs/methods/lightmem.toml`
- `src/memory_benchmark/evaluators/halumem_{extraction,update,qa,memory_type}.py`
- `tests/test_lightmem_adapter.py`、`tests/test_halumem_registered_prediction.py`、
  `tests/test_halumem_adapter.py`、`tests/test_halumem_unified_prompt.py`、
  `tests/test_halumem_evaluators.py`、`tests/test_method_registry.py`

## 5. current-v7 生产链必须逐层证明

用 production adapter/aggregator + fake LightMem backend 做零 API 探针；可读取 frozen Medium smoke
前缀，但不得消费 private gold 来选择样本。至少写清：

```text
raw session/turn
→ canonical Session/Turn
→ operation-level SessionBatch
→ LightMem hybrid message list
→ 单次 add_memory(messages, force_segment=True, force_extract=True)
→ 本 session 增量 session_memory_report
→ update-probe/QA retrieve
→ formatted_memory/answer builder/artifact
```

必须锁定这些不变量：

1. registry 实例身份为 `consume_granularity="session"` 且
   `session_memory_report=True`；manifest/resume identity 如实写 session，不继承旧 turn/pair run。
2. 每个 canonical session 只触发一次 LightMem `add_memory`；该次包含本 session 的全部保留 turn，
   role/content/order/source id/time 各恰一次，不跨 session 拼 pair。
3. current `messages_use="hybrid"` 使 user/assistant 都进入 extraction；HaluMem 正常数据不应出现
   placeholder。另用最小 synthetic irregular session 确认既有 placeholder 兜底不丢 turn，但不得
   把 synthetic shape 冒充数据实况。
4. session 末 `force_segment=True, force_extract=True` 是官方公开旋钮，用于 HaluMem 增量评测；
   它不等于全库 offline consolidation。`online_soft` 下不得调用
   `construct_update_queue_all_entries()` / `offline_update_all_entries()`。
5. `_capture_inserted_memories()` 只旁听当前 session 实际 insert，报告不得累计上个 session、制造
   空记忆或改变 insert 的参数/返回/异常；observer 与 current-v7 embedding 观测不能互相吞掉。
6. empty extraction 必须如实产 `capture_status=empty`；捕获路径不可用时应 `n/a`/fail-fast，不能
   把 retrieval snapshot 猜成新增 memory。
7. update probe 与 QA 只读当前在线状态；retrieve 固定 `filters=None`，不得把 memory point、answer、
   evidence、judge label 或 `original_memories` 暴露给 method。
8. HaluMem `RetrievalEvidence` 必须为 `n_a/halumem_no_turn_qrel/none`；任何 retrieval evaluator
   都不得据此制造 Recall/NDCG 数值。
9. product readout 使用 current-v7 官方格式（完整 ISO time + memory text，zero-hit 有明确 sentinel）；
   memory-build/retrieval embedding observer 的 stage、model id、token 数与真实调用一致。
10. unified answer builder 只消费公开 question + formatted memory；HaluMem 官方 prompt 无
    question-time 槽，不能把 session/turn/question wall clock 偷塞进去。

## 6. config、operation 与 evaluator 对表

从 TOML → 强类型 config → registry factory → manifest 逐项记录 current 值：LLM、embedding
path/dimension/distance、retrieve_limit、extract/compression/STM/topic/summary、messages_use、
lifecycle_profile、missing_timestamp_policy、timeout/retry、adapter version、protocol、consume
granularity 与 source identity。不要从历史 integration 页抄值。

列出三类 evaluator：

- extraction / update / QA：需要 judge API，真实 smoke 时按依赖顺序执行；本卡不调用；
- memory-type：artifact-only，但必须在 extraction+update artifacts 已存在后执行，不能单独抢跑；
- retrieval Recall/NDCG：HaluMem gold 无 turn qrel，N/A，不为填矩阵强算。

用现有 fake 链验证：空 update retrieval 走官方 integrity 路由、不虚增 update 分母；generated-QA
session 只 ingest；session report 缺失时 extraction N/A；operation runner 拒绝 `workers>1`。不要
修改 metric 公式、prompt、固定 smoke 裁剪或 resume policy。

## 7. 唯一交付物

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/lightmem/notes/
  lightmem-halumem-current-v7-preflight.md
```

note 必须自包含，至少包含：

1. baseline、source-lock 与 current config/adapter identity；
2. “继承 benchmark 事实 / 本批 method 差量”分栏，明确没有重跑 census；
3. Medium fixed-smoke 生产链逐层映射与 fake probe stdout；
4. session capture/flush、online-soft、retrieve/readout/observer 结论；
5. public/private 负空间检查；
6. evaluator、依赖顺序、N/A 与 workers/resume 矩阵；
7. 现有测试覆盖与真实 B11 尚缺的 runtime 证据；
8. 唯一总判词 `READY_FOR_HALUMEM_B11_COMMAND` 或 `BLOCKED(...)`。

若 ready，只建议沿用冻结的 Medium `1 conversation / 4 sessions × 2 turns / 1 QA / workers=1`
真实 smoke；不估算 API 次数，不运行命令，不创建 outputs。若 blocked，列最小修复卡输入。

不得修改 README、integration、survey、src、tests、configs、third_party、data、outputs、policy、
handbook 或既有 note。稳定摘要与异常账由架构师强验收后回填。

## 8. 定向自检与提交

只运行一次：

```bash
OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9 \
uv run pytest -q \
  tests/test_halumem_adapter.py \
  tests/test_halumem_unified_prompt.py \
  tests/test_halumem_evaluators.py \
  tests/test_halumem_registered_prediction.py \
  tests/test_lightmem_adapter.py \
  tests/test_method_registry.py
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

若测试意外联网，立即停工；禁止全量 pytest、compileall、真实 API、下载或 benchmark 全量扫描。
仅显式 add 唯一 note，禁止 `git add -A`/`.`；commit 前查看 `git status --short`。建议 commit：

```text
docs(lightmem): preflight halumem current v7
```

按 `actor-handbook.md` §4 回报 commit hash、两条测试尾行、实际改动文件、总判词、偏差/停工点、
subagent 与模型/入口切换；不要 push。到此停止，等待架构师强验收。

## 9. 停工条件

- source hash/字节与 frozen lock 不同；
- current source 推翻 §3 任一已裁 benchmark 事实；
- registered HaluMem 不是 session ingest + session report；
- 真实 turn 丢失、重复、跨 session、role/content/time 被猜改；
- capture wrapper 改变 insert 调用或把累计 snapshot 冒充 session 增量；
- online-soft 暗跑全库 consolidation；
- private memory point/answer/evidence 泄漏到 method/readout/answer prompt；
- HaluMem retrieval evidence 产生数值资格；
- current-v7 observer/readout 无法与 operation-level runner 共存；
- 任何真实 API/下载需求或 15 分钟内无法解释的测试矛盾。

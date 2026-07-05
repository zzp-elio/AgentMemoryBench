# 2026-06-11 Mem0-LoCoMo 并行通用 Runner 交接

> 最新统一 CLI/config 进度请优先读取
> `docs/handoffs/2026-06-12-unified-cli-config.md`。本文件保留 Mem0 adapter、并行 runner、
> source identity 和 smoke/full 实验历史，不再作为统一入口的最新断点。

## 当前状态

用户已确认下一阶段测试本地 OSS Mem0 源码，不使用 Mem0 Platform API。上下文即将压缩，
本轮只固化设计断点，没有修改 runner、Mem0 adapter 或测试代码。

## 已确认结论

1. 不新增 `mem0_locomo_full.py`。
2. `memoryos_locomo_full.py` 是先跑通 MemoryOS-LoCoMo 形成的垂直实现，不应复制成
   method × benchmark 文件矩阵。
3. 下一阶段应把其中通用能力抽到 conversation + QA experiment runner：
   - dataset fingerprint
   - public/private artifact
   - checkpoint/resume
   - Rich progress、run.log、events.jsonl
   - 逐题 evaluator
   - 失败记录和原子写入
4. benchmark adapter、method factory、evaluator 和少量 method hook 作为依赖注入。
5. 并行粒度以 conversation 为主：

```text
conversation worker:
  add(public conversation)
  -> answer this conversation's questions
  -> return records

coordinator:
  validate
  -> schedule workers
  -> serialize artifact/checkpoint writes
  -> aggregate summary
```

6. 不同 conversation 可以并行；同一 conversation 必须保证 add 完成后才能回答。
7. worker 不得直接并发写共享 JSONL 或 summary，避免竞争和截断。
8. 当前只接本地 OSS Mem0。Mem0 Platform API 后续若需要，应作为独立 backend，不污染
   core 和 runner。

## Mem0 当前事实

- 本地源码路径：`third_party/methods/mem0-main/`
- `pyproject.toml` 声明版本：`mem0ai 2.0.4`
- 当前目录不含 `.git` 元数据，因此无法记录 upstream commit SHA。
- 实现前必须生成并保存确定性的 source tree hash。
- OSS `Memory` 支持使用 `user_id`、`agent_id`、`run_id` 进行存储和检索过滤。
- Mem0 仓库自带 LoCoMo evaluation 使用的是托管版 `MemoryClient`，并非本地 OSS
  `Memory`；该脚本的实验结果不能直接宣称为本地 OSS 复现。
- Mem0 仓库的 LoCoMo 脚本按 conversation 并行，并为两个 speaker 分别建立 user namespace；
  这一行为可作为 OSS adapter 设计参考，但不能直接调用官方脚本。
- 当前 `.env` 只有 `OPENAI_KEY` 和 `BASE_URL`，没有 Mem0 Platform 配置；这符合
  OSS-only 决策。

## 必须保持的边界

- runner 只使用 `BaseMemorySystem.add()` 和 `get_answer()`。
- gold answer、evidence、category private label 不进入 Mem0。
- Mem0 原始 add/search 返回结构只能在 Mem0 adapter/backend 内归一化。
- `top_k` 属于 Mem0 配置，不加入统一接口。
- 受保护实验 `outputs/memoryos-locomo-full-20260603/` 不得修改或覆盖。
- 不修改 `third_party/methods/mem0-main/` 内部源码。

## 尚待用户确认

Mem0-LoCoMo 的记忆语义已经确认：

```text
一个 conversation_id -> 一个 Mem0 逻辑 namespace
```

- 不复刻 Mem0 官方 LoCoMo 双 speaker namespace 评测脚本。
- Mem0 adapter 不知道当前 benchmark 是 LoCoMo。
- conversation 的全部 turn 按原始顺序写入同一 namespace。
- 真实 speaker 名称保留在消息 content 和 metadata 中。
- `get_answer(question)` 只能检索 `question.conversation_id` 对应的 namespace。
- 不同 conversation 即使 speaker 同名也不能共享记忆。

尚待确认：本地 vector store、Mem0 实例共享方式、embedding、LLM、top-k 和最大 worker
数。全部确认后再写最终 spec 与 implementation plan。

## 2026-06-11 新增确认

- 第一版使用一个共享 Mem0 OSS `Memory` 实例。
- 使用 `run_id=conversation_id` 做逻辑隔离。
- 初始 conversation 并行度为 `max_workers=2`。
- worker 不写共享产物，协调层串行提交 JSONL/checkpoint/summary。
- 不修改 Mem0 官方源码；OpenAI key、base URL、模型和本地存储配置从本项目 adapter
  传给 Mem0 `Memory.from_config()`。
- embedding 优先使用本地模型，避免 embedding API 成本。
- 真实 API 只允许显式小量 smoke，默认测试禁止触网。
- 小量 smoke 只验证链路，不作为正式 LoCoMo F1。

建议的小量 smoke 数据：

```text
一个真实 LoCoMo conversation
-> 只取少量连续 session/turn
-> 私有侧选择 evidence 完全落在该片段内的一道真实 question
-> method 只收到公开 history 和 question
```

这样可以把真实调用控制在极少量，同时继续验证数据边界。

## 恢复顺序

1. 读 `AGENTS.md`。
2. 读本 handoff。
3. 读 `docs/superpowers/specs/2026-06-11-mem0-locomo-parallel-runner-design.md`。
4. 一次只向用户确认一个实质性问题。
5. 用户确认完整设计后再写 implementation plan，禁止直接编码。

## 2026-06-11 额度中断前最新断点

用户已经确认设计并要求开始执行。当前不再停留在设计阶段。

### 新增事实来源

用户拉取了 Mem0 官方仓库：

```text
third_party/methods/mem0-main/memory-benchmarks/
```

仓库 remote 为 `https://github.com/mem0ai/memory-benchmarks.git`，当前本地 HEAD：

```text
4b61c5d31b9c668a12b4f5e78064248a02c82d2b
```

该仓库明确给出的 OSS benchmark 配置是：

- memory extraction：`gpt-4o-mini`
- embedding：`text-embedding-3-small`，1536 维
- vector store：Qdrant
- LoCoMo ingestion：每个 turn 一个 chunk，`CHUNK_SIZE = 1`
- full retrieval：`top_k=200`
- full conversation workers：`10`
- add 使用 Mem0 推理提取路径，即 `infer=True`

因此此前建议的本地 `bge-m3` 已取消。smoke 可以降低 top-k、范围和并发，但 extraction
与 embedding 仍使用官方模型。全量必须恢复官方 profile。

注意：官方 benchmark 的 Docker requirements 指向已经不存在的
`feat/v3-pipeline` 分支，不能原样安装。只参考其参数、prompt 和数据流；当前项目仍直接
调用 vendored Mem0 `Memory`，不修改第三方源码。

### 已更新文档

- 已确认设计：
  `docs/superpowers/specs/2026-06-11-mem0-locomo-parallel-runner-design.md`
- 已创建实施计划：
  `docs/superpowers/plans/2026-06-11-mem0-generic-prediction-runner.md`

计划锁定两套 profile：

```text
smoke:
  1 conversation + 少量 turn + 1 question
  top_k=10
  max_workers=1
  只生成 answer，不计算 metric

official_full:
  全部 LoCoMo conversation/question
  per-turn add
  top_k=200
  max_workers=10
  只生成 answer，不计算 metric
```

全量启动前仍需用户再次确认 API 成本。回答模型属于框架 reader 配置，必须与 Mem0
extraction/embedder 参数分开记录。

### 已完成代码：通用 prediction runner

新增：

- `src/memory_benchmark/runners/prediction.py`
- `tests/test_prediction_runner.py`

当前接口：

```python
PredictionRunPolicy(...)
run_predictions(
    dataset,
    system,
    run_context,
    policy,
    method_manifest,
    source_paths=(),
)
```

已经实现：

- benchmark/method 无关的 conversation + QA 回复生成。
- evaluator 可完全缺席；当前不产生 metric/scores。
- public questions 与 evaluator-only gold/evidence 分文件。
- conversation 两阶段执行：先并发 ingest 并提交 checkpoint，再并发按 conversation
  串行回答问题。
- worker 只返回 batch，协调线程原子写 predictions/checkpoints。
- conversation/question 范围限制。
- manifest 兼容检查和 resume。
- Rich progress、run.log、events.jsonl、summary。
- 动态私有属性清洗。

TDD 证据：

```text
RED:
uv run pytest tests/test_prediction_runner.py -q
-> ModuleNotFoundError: memory_benchmark.runners.prediction

第一次 GREEN 尝试:
-> 4 passed, 1 failed
-> 合法 resume 因 manifest 包含 resume=False/True 而被错误拒绝

修复后:
uv run pytest tests/test_prediction_runner.py tests/test_conversation_runner.py -q
-> 11 passed

uv run python -m compileall -q \
  src/memory_benchmark/runners/prediction.py \
  tests/test_prediction_runner.py
-> exit 0
```

随后 documentation test 发现内部函数 `walk()` 缺中文 docstring，已补上，但**额度中断前
尚未重新运行 documentation test**。

### 正在进行但尚未验收：Mem0 adapter

已派发 subagent：

```text
agent_id: 019eb704-ef05-7de3-8b58-954c3b2e5357
nickname: Schrodinger
```

写入范围：

- `src/memory_benchmark/methods/mem0_adapter.py`
- `tests/test_mem0_adapter.py`

任务是按 TDD 实现 `Mem0Config`、source identity、真实 OSS `Mem0(BaseMemorySystem)`、
逐 turn add、run_id namespace、search 和 reader。已向 agent 发出紧急停止扩展并保存
当前工作/报告测试结果的指令。

当前主线程最后检查时：

- `mem0_adapter.py` 仍是 34 行旧禁用占位文件。
- `tests/test_mem0_adapter.py` 尚不存在。

因此恢复后必须先检查 subagent 最终状态和共享工作区文件，不能假定 adapter 已完成。

### 恢复后的精确顺序

1. 检查 agent `019eb704-ef05-7de3-8b58-954c3b2e5357` 最终消息；若仍运行，等待一次。
2. 查看 `mem0_adapter.py` 和 `tests/test_mem0_adapter.py` 实际内容。
3. 运行：

```bash
uv run pytest \
  tests/test_mem0_adapter.py \
  tests/test_mem0_source_compatibility.py \
  tests/test_prediction_runner.py \
  tests/test_conversation_runner.py -q
```

4. 运行：

```bash
uv run pytest tests/test_documentation_standards.py -q
```

5. 修复 focused tests 后，才实现通用 CLI 和显式 API smoke。
6. 不要启动 full，不要计算 metric，不要修改 third_party，不要触碰
   `outputs/memoryos-locomo-full-20260603/`。

## 2026-06-12 恢复审计

上次 subagent 最终状态：

```text
agent_id: 019eb704-ef05-7de3-8b58-954c3b2e5357
status: errored
reason: 5h usage limit exhausted
```

共享工作区审计确认：

- `src/memory_benchmark/methods/mem0_adapter.py` 仍是 34 行旧禁用占位。
- `tests/test_mem0_adapter.py` 不存在。
- subagent 没有留下需要判断取舍的半成品。
- `src/memory_benchmark/runners/prediction.py` 和
  `tests/test_prediction_runner.py` 存在且内容完整。

恢复验证：

```bash
uv run pytest \
  tests/test_prediction_runner.py \
  tests/test_conversation_runner.py \
  tests/test_documentation_standards.py -q
```

结果：

```text
16 passed in 1.01s
```

因此当前可信断点为：

1. 设计 spec 已批准。
2. implementation plan 已落盘。
3. 通用 prediction runner 已完成 focused 验证。
4. Mem0 adapter 尚未开始有效实现。
5. CLI、真实 API smoke、full run 均尚未开始。

下一步不要重复设计或重写 runner。直接从实施计划 Task 1 开始，对
`tests/test_mem0_adapter.py` 与 `mem0_adapter.py` 执行 RED-GREEN TDD。真实 API 必须等
fake backend contract 全绿后再显式启动。

## 2026-06-12 Phase E 实施完成断点

本节覆盖上文“adapter 尚未实现”的旧断点。恢复工作时以本节和 `AGENTS.md` 为准。

### 已完成代码

- `src/memory_benchmark/methods/mem0_adapter.py`
  - 直接加载 `third_party/methods/mem0-main/` 的 OSS `Memory`，不重写算法。
  - `Mem0Config.smoke()` / `official_full()` 锁定官方模型、top-k、chunk 和并发参数。
  - 每个 turn 单独 `add(..., run_id=conversation_id, infer=True)`。
  - `get_answer()` 只检索问题所属 conversation namespace。
  - source identity 固定 Mem0 2.0.4 核心源码，当前 SHA-256：
    `e98b4914c6a0716cdd920b2c0491b32ef4c9ed537b44fd8c72199020ce81bae0`。
- `src/memory_benchmark/runners/prediction.py`
  - 通用 conversation-QA prediction runner，不创建 method × benchmark 专用 runner。
  - 公开 prediction 与 evaluator-only gold/evidence 分离。
  - conversation 调度、checkpoint/resume、Rich progress 和 coordinator 串行写入已实现。
- `src/memory_benchmark/cli/run_prediction.py`
  - 当前装配本地 Mem0 + LoCoMo，真实 API 和 official full 均有显式成本确认。
- `tests/test_mem0_adapter.py`
- `tests/test_prediction_cli.py`
- `tests/test_prediction_runner.py`
- `tests/test_mem0_locomo_api.py`
  - 标记为 `api + expensive + integration + mem0`，默认 pytest 不运行。

### 新增运行依赖

已通过 `uv` 加入并验证：

```text
spacy 3.8.14
en_core_web_sm 3.8.0
fastembed 0.8.0
Qdrant/bm25 sparse model（已下载到本地缓存）
```

原因：当前 Mem0 2.0.4 的 Qdrant 混合检索会用 spaCy lemmatization 和 FastEmbed BM25。
缺少它们时 Mem0 会发 warning 并静默退化，不能用于正式实验。

### 时间语义问题与根因

前两次真实 smoke 都成功完成链路，但把 LoCoMo 的 `yesterday` 错误解析为当前日期：

```text
outputs/mem0-locomo-smoke-20260612/
outputs/mem0-locomo-smoke-timefix-20260612/
```

根因不是 reader，而是 Mem0 2.0.4 的本地 V3 extraction：

1. extraction prompt 设计了 `Observation Date`。
2. 本地 `Memory.add()` 没有 timestamp/observation_date 参数。
3. V3 `_add_to_vector_store()` 调用 `generate_additive_extraction_prompt()` 时没有从
   metadata 传入 session time，因此 Observation Date 回退到当前日期。
4. 官方 `memory-benchmarks` LoCoMo runner 虽然发送 timestamp，但其当前 OSS server
   `AddRequest` 不声明 timestamp，且声明的 observation_date 也没有下传给 `Memory.add()`；
   这是官方 benchmark wrapper 与当前 Mem0 源码之间的版本错配。

项目侧没有修改第三方源码。adapter 使用 Mem0 已公开的 `prompt` 扩展点，为每个 session
传入 observation time，并继续把 session time 保留在 message/metadata。该修复有 RED-GREEN
契约测试。

### 成功真实 smoke

命令：

```bash
uv run python -m memory_benchmark.cli.run_prediction \
  --root /Users/wz/Desktop/memoryBenchmark \
  --benchmark locomo \
  --method mem0 \
  --profile smoke \
  --run-id mem0-locomo-smoke-observation-fix-20260612 \
  --smoke-turn-limit 3 \
  --confirm-api
```

范围：

```text
conversation: conv-26
history: 1 session / 3 turns
question: conv-26:q0
gold: 7 May 2023（仅私有 artifact）
```

结果：

```text
extracted memory:
Caroline attended an LGBTQ support group on May 7, 2023...

answer:
Caroline attended the LGBTQ support group on May 7, 2023.
```

产物：

```text
outputs/mem0-locomo-smoke-observation-fix-20260612/
```

该运行只生成回复，不计算 F1 或 LLM judge，不能作为正式 LoCoMo 结果。

### 最新验证

```text
uv run pytest tests/test_mem0_adapter.py tests/test_prediction_cli.py \
  tests/test_prediction_runner.py tests/test_conversation_runner.py \
  tests/test_mem0_source_compatibility.py tests/test_documentation_standards.py -q
-> 31 passed

uv run pytest tests/test_mem0_locomo_api.py --collect-only -q -m "api and mem0"
-> 1 test collected

uv run pytest -q
-> 182 passed, 2 deselected, 4 subtests passed

uv run python -m compileall -q src/memory_benchmark tests
-> exit 0
```

默认回归的唯一 warning 来自未修改的
`third_party/methods/MemoryOS-main/eval/utils.py` SyntaxWarning。

### 下一步

不要直接启动 official full。下一步是：

1. 与用户确认一次低成本真实并发 smoke。
2. TDD 增加 2-conversation fixture，每个 conversation 只保留少量 turn 和 1 question。
3. 使用共享 OSS `Memory`、`run_id=conversation_id`、`max_workers=2`。
4. 验证两个 namespace 的 add/search/prediction/state 没有串写。
5. 通过后再向用户汇报预计调用规模，并单独确认 official full 成本。

2-conversation smoke 会产生真实 extraction、embedding 和 reader API 消耗，未获确认前不要运行。

## 2026-06-12 两 conversation 并发 smoke 完成

### 实现变化

`build_locomo_smoke_dataset()` 现在支持：

```text
conversation_limit=1 或 2
```

CLI 新增仅用于 smoke 诊断的参数：

```text
--smoke-conversation-limit {1,2}
--smoke-max-workers {1,2}
```

默认仍为 1 conversation / 1 worker；official-full 仍使用 profile 固定的 10 workers，
smoke override 不能污染 full 配置。

新增无网络测试验证：

- 两个 conversation 各自独立裁剪 history 和选择一道 evidence 已覆盖的问题。
- 共享 `Mem0` adapter 并发 add/search 时按 `run_id=conversation_id` 隔离。
- 每个答案只包含其 namespace 的 sentinel，不包含另一侧内容。

### Subagent 并发审查

只读 explorer：

```text
agent_id: 019eb95b-4dea-7783-b58e-fb64b47b46cd
model: gpt-5.4-mini
reasoning: high
```

关键发现：

- runner 的 ingest/answer 两阶段确实共享同一个 `Mem0` 实例。
- SQLite history 使用 `check_same_thread=False`，且所有访问有内部 lock。
- Qdrant embedded client 被 Mem0 主 collection/entity collection 共享，避免 RocksDB
  双客户端锁冲突；2-worker smoke 可行，但不能仅凭源码宣称任意并发度形式证明。
- Mem0 2.0.4 的 `entity_store` 是无锁懒加载，首次并发 add 可能重复初始化。

针对最后一项，项目侧 adapter 已在生产 `Memory` 构造完成后、worker 启动前单线程访问
`entity_store` 完成预热。未修改第三方源码，并新增 RED-GREEN 测试：

```text
test_production_backend_prewarms_lazy_entity_store_before_workers
```

无 API 的真实生产构造确认：

```text
backend=Memory
entity_store_initialized=True
main_collection=mem0
entity_collection=mem0_entities
```

### 真实并发命令

```bash
uv run python -m memory_benchmark.cli.run_prediction \
  --root /Users/wz/Desktop/memoryBenchmark \
  --benchmark locomo \
  --method mem0 \
  --profile smoke \
  --run-id mem0-locomo-concurrent-smoke-20260612 \
  --smoke-turn-limit 3 \
  --smoke-conversation-limit 2 \
  --smoke-max-workers 2 \
  --confirm-api
```

结果：

```text
completed_conversations: 2/2
completed_questions: 2/2
total wall time: about 31 seconds
```

回复：

```text
conv-26:q0 -> Caroline attended the LGBTQ support group on May 7, 2023.
conv-30:q0 -> Jon lost his job as a banker on January 19, 2023.
```

两者分别对应私有 gold：

```text
7 May 2023
19 January, 2023
```

Qdrant 审计得到 4 条 memory payload：

```text
conv-26: 1 条，run_id/conversation_id 均为 conv-26
conv-30: 3 条，run_id/conversation_id 均为 conv-30
```

没有发现跨 conversation payload。predictions、private labels、conversation/question
checkpoint 和 events 也全部按 id 对齐。

产物：

```text
outputs/mem0-locomo-concurrent-smoke-20260612/
```

最新验证：

```text
uv run pytest -q
-> 186 passed, 3 deselected, 4 subtests passed

uv run pytest tests/test_documentation_standards.py tests/test_mem0_adapter.py \
  tests/test_prediction_cli.py tests/test_prediction_runner.py \
  tests/test_mem0_source_compatibility.py -q
-> 29 passed

uv run pytest tests/test_mem0_locomo_api.py --collect-only -q -m "api and mem0"
-> 2 tests collected

uv run python -m compileall -q src/memory_benchmark tests
-> exit 0
```

输出目录 secret 扫描无命中。

### 当前 full 前阻塞点

不要直接启动 official-full。当前 conversation checkpoint 粒度不足：

```text
conversation add 处理到中间 turn
-> API/网络失败
-> runner 只知道该 conversation 未完成
-> resume 会从第一个 turn 重新 add
```

这会带来重复 API 成本，也可能使已有 namespace 重复提取或更新记忆。下一阶段必须先和
用户对齐 method lifecycle / per-turn ingest checkpoint 方案，使 Mem0 能从明确的
`next_turn_index` 恢复；不能把 benchmark-specific 逻辑写入通用 core 接口，也不能依赖
Mem0 的概率性 dedup 作为恢复机制。

## 2026-06-12 逐 turn checkpoint 实施断点

### 已确认设计

设计与实施计划：

```text
docs/superpowers/specs/2026-06-12-turn-level-ingest-resume-design.md
docs/superpowers/plans/2026-06-12-turn-level-ingest-resume.md
```

核心状态机：

```text
无文件 -> turn 调用前 in_flight -> 调用成功后 ready(next=i+1)
-> 全部 turn 确认后 completed
```

`in_flight` 表示第三方服务是否处理请求不确定，resume 必须在任何 method/API 调用前拒绝，
不能自动重放。checkpoint 文件按原始 `conversation_id` 的 SHA-256 命名，原始 id 保存在
JSON payload 中。

### 已完成

1. `src/memory_benchmark/core/interfaces.py`
   - 新增可选 `BaseResumableMemorySystem`。
   - 原有 `BaseMemorySystem.add()` 公共契约未改变。
2. `src/memory_benchmark/methods/mem0_adapter.py`
   - `Mem0` 改为实现可选增量接口。
   - 新增 `add_from_turn()`，按原 session/turn 顺序展开，跳过已确认前缀。
   - callback 顺序严格为 `started -> 官方 Memory.add -> completed`。
   - `start_turn_index > 0` 时附着已有 namespace，不清空、不重建。
3. `src/memory_benchmark/storage/experiment_paths.py`
   - 新增 `checkpoints/ingest_turns/` 标准路径。
4. `src/memory_benchmark/runners/ingest_resume.py`
   - 新增冻结 checkpoint 实体和 store。
   - 实现 `ready/in_flight/completed`、原子 JSON、SHA-256 路径和强校验。
5. 测试：
   - `tests/test_mem0_adapter.py` 增加指定 index 跳过与 callback 顺序测试。
   - `tests/test_ingest_resume.py` 增加路径逃逸、三态 round-trip、字段错配、越界和 callback
     错配测试。

当前验证：

```text
uv run pytest tests/test_ingest_resume.py tests/test_mem0_adapter.py -q
-> 19 passed

uv run python -m compileall -q src/memory_benchmark tests
-> exit 0
```

### 2026-06-12 runner 接入与最终验证完成

通用 `prediction.py` 已完成可选增量路径接入：

- 所有 conversation checkpoint 在创建 worker 前统一预检。
- 任一 `in_flight` 会阻止整个 resume，确保不会先启动其它 conversation 的 API 调用。
- `ready` 从 `next_turn_index` 继续，只写未确认 turn。
- `ready(next_turn_index=total_turns)` 仍调用 method 的零 turn 收尾路径，只有 method
  返回成功后才升级 `completed`。
- `completed` 可在 coarse `conversation_status.json` 缺失时补交完成态，不重复 add。
- 普通 `BaseMemorySystem` 不创建逐 turn文件；若发现 partial checkpoint，会明确要求
  `BaseResumableMemorySystem`，而不是从头重灌。
- conversation 并发时，每个 worker 只写自己 SHA-256 命名的独立 checkpoint；
  coordinator 继续独占共享 coarse 状态写入。

CLI 不需要新增参数。部分恢复时 `Mem0.add_from_turn(start_turn_index > 0)` 会附着已有
namespace；已完成 conversation 继续使用现有 `load_completed_conversation_ids()`。

最终验证：

```text
uv run pytest tests/test_ingest_resume.py tests/test_mem0_adapter.py \
  tests/test_prediction_runner.py tests/test_prediction_cli.py \
  tests/test_experiment_storage.py tests/test_documentation_standards.py -q
-> 69 passed, 4 subtests passed

uv run pytest -q
-> 204 passed, 3 deselected, 4 subtests passed

uv run pytest -m api --collect-only -q
-> 3 tests collected, 204 deselected

uv run python -m compileall -q src/memory_benchmark tests
-> exit 0
```

没有执行真实 API 测试，也没有修改第三方 Mem0 源码。

### 下一步

逐 turn resume 可靠性阻塞点已经解除。下一步不是直接无提示启动 full，而是：

1. 对 Mem0 official-full 配置、CLI、manifest、resume 和产物路径做一次最终综合审查。
2. 估算 LoCoMo 全量 extraction、embedding、reader 的调用规模和主要成本风险。
3. 向用户确认余额、正式 `run_id` 和是否立即启动。
4. 获得确认后再运行；运行期间保留 `in_flight` 的保守人工处理原则。

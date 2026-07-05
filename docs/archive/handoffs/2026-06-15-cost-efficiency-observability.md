# 2026-06-15 成本与效率观测交接

## 当前目标

Phase G 优先实现可审计的原始效率 observation。实验只记录 token、latency、模型身份和
计量来源；真实费用在实验结束后按实际 OpenAI-compatible 服务商价格离线计算。

## 已确认设计

- 设计：
  `docs/superpowers/specs/2026-06-15-cost-efficiency-observability-design.md`
- 实施计划：
  `docs/superpowers/plans/2026-06-15-cost-efficiency-observability.md`
- 未运行 LLM Judge 时不生成任何 Judge 估算。
- 无法精确拆分 retrieval 时记录 `null + unsupported_reason`。
- 允许不改变算法行为的第三方纯 observer 插桩。
- 当前不执行真实 API。

## 2026-06-16 续跑更新

本轮完成 Phase G Task 5：

- `LLMCallObservation` 已通过 TDD 允许真实存在的 `EfficiencyStage.RETRIEVAL`。
- registered prediction 已支持可选 `enable_efficiency_observability`，打开时为每个
  child run 创建同 run_id 的 `EfficiencyCollector`，并把 model inventory、
  instrumentation identity、retrieval contract 同时传给 preflight、method factory 和
  generic runner；默认关闭，旧运行路径不变。
- `src/memory_benchmark/methods/registry.py` 已为 Mem0/MemoryOS 注册 efficiency model
  inventory、wrapper instrumentation identity 和 retrieval observation contract。
- Mem0 adapter 已记录：
  - retrieval latency；
  - injected memory context tokens；
  - answer generation latency；
  - extraction/build LLM usage；
  - fixed reader answer LLM usage；
  - build/retrieval embedding input tokens 与 latency。
- MemoryOS adapter 已记录：
  - retrieval latency；
  - injected memory context tokens；
  - answer generation latency；
  - retrieval/answer LLM usage；
  - build/retrieval 本地 SentenceTransformer embedding input tokens 与 latency。
- 未修改第三方核心算法；MemoryOS 暂不进入 `main_loco_parse.py` observer patch，
  因为当前 compact 观测只需要 aggregate injected memory context，不做 component-level
  breakdown。

TDD / 验证证据：

```bash
uv run pytest tests/test_efficiency_entities.py -q
# 先得到 1 failed, 16 passed；修复后相关 efficiency 基础测试 38 passed。

uv run pytest tests/test_prediction_cli.py::test_registered_prediction_wires_efficiency_observability_when_enabled -q
# 先因未知 enable_efficiency_observability 参数失败；修复后 1 passed。

uv run pytest tests/test_mem0_adapter.py::test_get_answer_records_efficiency_observations_when_collector_enabled \
  tests/test_mem0_adapter.py::test_mem0_records_build_llm_and_embedding_observations_when_available -q
# 先 2 failed；修复后 2 passed。

uv run pytest tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_get_answer_records_question_and_llm_efficiency_observations -q
# 先因 question scope 缺 retrieval 失败；修复后 1 passed。

uv run pytest tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_get_embedding_records_local_token_count_and_latency_on_cache_miss -q
# 先因缺 embedding observation 失败；修复后 1 passed。

uv run pytest tests/test_prediction_efficiency_observations.py \
  tests/test_efficiency_entities.py \
  tests/test_efficiency_collector.py \
  tests/test_efficiency_storage.py \
  tests/test_method_efficiency_observations.py \
  tests/test_mem0_adapter.py \
  tests/test_memoryos_adapter.py \
  tests/test_prediction_cli.py::test_registered_prediction_wires_efficiency_observability_when_enabled -q
# 194 passed, 2 subtests passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

下一步：Task 6，接入实际 LLM Judge observation。要求离线 F1 evaluator 不创建 Judge
observation；只有真实运行 LLM judge 时才写 evaluator model inventory 和
`efficiency_observations.<metric>.jsonl`。

## 2026-06-16 Task 6 续跑更新

本轮完成 Phase G Task 6：

- 新增 `tests/test_judge_efficiency_observations.py`。
- 离线 `LoCoMoF1Evaluator` 仍不创建 evaluator efficiency model inventory 或 observation
  文件。
- `LLMJudgeEvaluator` 声明 `supports_efficiency_observability = True`；真实 evaluator
  运行时由 `run_artifact_evaluation()` 自动创建同 run_id 的 `EfficiencyCollector`。
- `LLMJudgeEvaluator` 现在解析 OpenAI Responses API usage，优先使用 API input/output
  token；usage 缺失时使用匹配 tokenizer fallback，并标注来源。
- evaluator runner 为支持 efficiency 的 evaluator 建立 `judge_scope`，写入：
  - `artifacts/model_inventory.<metric_name>.json`
  - `artifacts/efficiency_observations.<metric_name>.jsonl`
- collector 增加 `judge_scope`，该 scope 只收集 judge LLM call，不要求 retrieval 或
  answer latency 聚合，避免把 prediction question 语义套到 evaluator 阶段。
- 未执行真实 API。

TDD / 验证证据：

```bash
uv run pytest tests/test_judge_efficiency_observations.py -q
# 首次 RED：LoCoMoJudgeEvaluator 不接受 efficiency_collector，1 failed, 1 passed。
# 第二次 RED：真实 CLI 风格 evaluator 不自动生成 artifact，1 failed, 1 passed。
# 最终 GREEN：2 passed。

uv run pytest tests/test_judge_efficiency_observations.py \
  tests/test_llm_judge_parsing.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_evaluator_registry.py \
  tests/test_main_cli.py -q
# 48 passed

uv run pytest tests/test_prediction_efficiency_observations.py \
  tests/test_efficiency_entities.py \
  tests/test_efficiency_collector.py \
  tests/test_efficiency_storage.py \
  tests/test_method_efficiency_observations.py \
  tests/test_mem0_adapter.py \
  tests/test_memoryos_adapter.py \
  tests/test_judge_efficiency_observations.py \
  tests/test_llm_judge_parsing.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_evaluator_registry.py \
  tests/test_main_cli.py -q
# 241 passed, 2 subtests passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

## 2026-06-16 Task 7 续跑更新

本轮完成 Phase G Task 7：离线效率聚合与真实价格计算。

新增：

- `src/memory_benchmark/analysis/__init__.py`
- `src/memory_benchmark/analysis/efficiency.py`
- `src/memory_benchmark/analysis/cost.py`
- `tests/test_efficiency_analysis.py`
- `tests/test_cost_analysis.py`

关键行为：

- `aggregate_efficiency()` 聚合 memory build、retrieval、answer latency，
  retrieval supported/unsupported count、`injected_memory_context_tokens`、
  LLM input/output token 和 embedding input token/latency。
- 百分位算法固定为线性插值，并写入 docstring 与测试。
- `calculate_cost()` 使用 `Decimal` 和用户传入的真实价格离线计算费用。
- `injected_memory_context_tokens` 只作为诊断指标，不能重复计入 answer LLM 费用。
- API 模型缺少价格时返回 `complete=False` 和 `missing_price_model_ids`，不静默当作零成本。
- `ModelDescriptor.execution_mode == "local"` 的模型固定零成本且不要求价格。
- 不同币种直接相加会抛 `ConfigurationError`。

TDD 证据：

```bash
uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py -q
# RED: 2 collection errors, ModuleNotFoundError: No module named 'memory_benchmark.analysis'

uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py -q
# GREEN: 7 passed
```

回归验证：

```bash
uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py \
  tests/test_efficiency_entities.py \
  tests/test_efficiency_collector.py \
  tests/test_efficiency_storage.py \
  tests/test_efficiency_token_counting.py \
  tests/test_prediction_efficiency_observations.py \
  tests/test_method_efficiency_observations.py \
  tests/test_judge_efficiency_observations.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_main_cli.py -q
# 95 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

uv run pytest tests/test_documentation_standards.py -q
# 5 passed
```

下一步：Task 8。先判断 MemoryOS 现有 wrapper 是否已经满足 Phase G 必需观测；如果
满足，不要为了“插桩”而强行修改第三方源码。若需要更细粒度 observation，再只加可关闭、
可审计、行为等价的纯 observer。

## 2026-06-16 Task 8 RED 暂停点

用户提示 5h 额度仅剩约 8%，本轮在合适位置暂停。当前没有执行真实 API。

已完成判断：

- 现有 MemoryOS wrapper 已能记录 retrieval latency、answer latency、retrieval/answer
  LLM token、build/retrieval embedding token。
- 但 `injected_memory_context_tokens` 当前只基于 `retrieval_result` 文本计算。
- 官方 `generate_system_response_with_meta()` 最终 prompt 还会注入：
  `history_text`、`retrieval_text`、`background/user_profile_and_knowledge`、
  `assistant_knowledge_text`。
- 因此 Task 8 的纯 observer hook 是必要的；它用于观测最终 prompt 里的 memory context，
  不是改变 MemoryOS 算法。

本轮新增 RED 测试：

- `tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_official_memory_context_observer_does_not_change_generation_result`
- `tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_get_answer_uses_observed_final_memory_context_tokens`

RED 验证：

```bash
uv run pytest tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_official_memory_context_observer_does_not_change_generation_result \
  tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_get_answer_uses_observed_final_memory_context_tokens -q
# 2 failed in 6.93s
```

失败原因符合预期：

- `observed_payloads` 长度为 0：官方 `main_loco_parse.generate_system_response_with_meta()`
  尚未调用 `memory_context_observer`。
- 空 retrieval result 时 `injected_memory_context_tokens == 0`：wrapper 尚未读取最终
  prompt memory context observer payload。

下一步 GREEN 实现建议：

1. 修改 `third_party/methods/MemoryOS-main/eval/main_loco_parse.py`，只增加模块级
   `memory_context_observer = None` 和发送 LLM 前的可选 callback。
2. callback payload 至少包含：
   `history_text`、`retrieval_text`、`user_profile_and_knowledge`、`assistant_knowledge`。
3. callback 异常必须被吞掉或记录为非算法错误，不能改变官方函数返回值、prompt、
   client 调用参数或状态。
4. 修改 `src/memory_benchmark/methods/memoryos_adapter.py`：
   在 `_patch_eval_modules()` 注入当前实例的 observer callback；
   `get_answer()` 优先使用 observer payload 计算 `injected_memory_context_tokens`，
   若 observer 未触发则回退到现有 `_memoryos_retrieved_context_text(retrieval_result)`。
5. 更新 MemoryOS instrumentation/source identity。由于 vendored 官方源码会变化，
   `build_memoryos_source_identity()` 的 vendored hash 会自然变化；wrapper hash 也会随
   adapter 修改变化。
6. 跑新增 RED 测试变 GREEN，再跑：
   `uv run pytest tests/test_memoryos_adapter.py tests/test_method_efficiency_observations.py tests/test_memoryos_registered_prediction.py -q`
   视时间再跑 Phase G focused 回归。

## 2026-06-16 Task 8 GREEN 续跑更新

本轮完成 Phase G Task 8：MemoryOS 最终 prompt memory context 纯 observer。

修改：

- `third_party/methods/MemoryOS-main/eval/main_loco_parse.py`
- `src/memory_benchmark/methods/memoryos_adapter.py`
- `tests/test_memoryos_adapter.py`
- `tests/test_memoryos_registered_prediction.py`

关键行为：

- 官方 `generate_system_response_with_meta()` 增加模块级
  `memory_context_observer = None`，默认关闭。
- 在发送 LLM 前，官方函数把最终 prompt 的 memory context parts 传给 observer：
  `history_text`、`retrieval_text`、`user_profile_and_knowledge`、
  `assistant_knowledge`。
- observer 异常被吞掉，不改变答案、prompt、client 调用参数或 MemoryOS 状态。
- MemoryOS wrapper 在 `_patch_eval_modules()` 注入实例级 callback。
- wrapper 使用 `ContextVar` 保存当前 question 的 observer payload，避免同实例上下文串写。
- `injected_memory_context_tokens` 现在优先基于最终 prompt memory context 计数；
  未触发 observer 时回退到原有 retrieval result 文本。
- `tests/test_memoryos_registered_prediction.py` 的 `_FakeMemoryOS` 已跟随真实 factory
  契约显式接收 `efficiency_collector`。

验证：

```bash
uv run pytest tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_official_memory_context_observer_does_not_change_generation_result \
  tests/test_memoryos_adapter.py::MemoryOSAdapterTests::test_get_answer_uses_observed_final_memory_context_tokens -q
# 2 passed

uv run pytest tests/test_memoryos_adapter.py tests/test_method_efficiency_observations.py tests/test_memoryos_registered_prediction.py -q
# 141 passed, 2 subtests passed

uv run pytest tests/test_efficiency_analysis.py tests/test_cost_analysis.py \
  tests/test_efficiency_entities.py \
  tests/test_efficiency_collector.py \
  tests/test_efficiency_storage.py \
  tests/test_efficiency_token_counting.py \
  tests/test_prediction_efficiency_observations.py \
  tests/test_method_efficiency_observations.py \
  tests/test_judge_efficiency_observations.py \
  tests/test_memoryos_adapter.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_main_cli.py -q
# 232 passed, 2 subtests passed

uv run pytest -m memoryos -q
# 172 passed, 353 deselected, 2 subtests passed

uv run pytest -m api --collect-only -q
# 3/525 tests collected (522 deselected)

uv run pytest -q
# 522 passed, 3 deselected, 6 subtests passed

uv run python -m compileall -q src/memory_benchmark tests third_party/methods/MemoryOS-main/eval/main_loco_parse.py
# exit 0

uv run pytest tests/test_documentation_standards.py -q
# 5 passed
```

受保护实验目录聚合哈希未变化：

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f  -
```

下一步：

- Phase G 阶段级综合 review 与收口文档。
- 不启动真实 API。
- 不进入 Phase H 并行调度，除非 Phase G review 已明确通过。

## 2026-06-16 Phase G 阶段级 review 与收口

Reviewer：Franklin，`gpt-5.5 xhigh`，只读阶段级综合 review。

Review 结论：

- `APPROVED`。
- 无 Critical/Important findings。
- Review 额外无网络验证：
  - `9 passed`：两个 MemoryOS observer tests + efficiency/cost analysis tests。
  - `4 passed`：collector isolation、disabled collector、concurrent runner observations、
    resume dedupe。
  - `3 passed`：MemoryOS source identity 和 resume mismatch preflight。

Reviewer 残余风险：

- handoff 中间历史“当前断点”仍写 Task 6，可能误导恢复。

处理：

- 已将该段改为“历史断点（已完成）”，并注明 Task 6-8 已完成，恢复时读取文件末尾最新
  稳定断点。

Phase G 当前状态：

- 已完成。
- 未执行真实 API。
- 下一步是 Phase H 通用并行调度设计/实施入口；不得启动付费实验，除非用户显式确认
  API 余额、实验规模和正式 run_id。

## 已完成

### Task 1：强类型 observation 与模型清单

新增：

- `src/memory_benchmark/observability/efficiency/entities.py`
- `src/memory_benchmark/observability/efficiency/__init__.py`
- `tests/test_efficiency_entities.py`

修改：

- `src/memory_benchmark/observability/__init__.py`

TDD 证据：

1. RED：`uv run pytest tests/test_efficiency_entities.py -q`
   因 `memory_benchmark.observability.efficiency` 不存在而 collection error。
2. GREEN：同一命令得到 `10 passed in 0.06s`。

已实现：

- `EfficiencyStage`
- `MeasurementSource`
- `ModelDescriptor`
- `ConversationEfficiencyObservation`
- `QuestionEfficiencyObservation`
- `LLMCallObservation`
- `EmbeddingCallObservation`
- `EfficiencyObservation` union

### Task 2：Collector 与 token 计量

新增：

- `src/memory_benchmark/observability/efficiency/collector.py`
- `src/memory_benchmark/observability/efficiency/token_counting.py`
- `tests/test_efficiency_collector.py`
- `tests/test_efficiency_token_counting.py`

TDD 证据：

1. RED：focused tests 因 `EfficiencyCollector` 和 `token_counting` 不存在而 collection
   error。
2. 首次 GREEN 尝试暴露 `efficiency/__init__.py` 导出列表缩进错误；读取 traceback 和
   文件行号后确认根因是补丁把两个名称插在闭合列表外。
3. 最小修复后：
   `uv run pytest tests/test_efficiency_collector.py tests/test_efficiency_token_counting.py tests/test_efficiency_entities.py -q`
   得到 `24 passed in 0.14s`。

已实现：

- conversation/question ContextVar 作用域。
- 多线程 scope 隔离。
- 显式 operation stage。
- 确定性 SHA-256 observation id。
- retrieval 精确值或 `unsupported_reason` 二选一。
- API usage 优先、完整 usage 缺失时统一 tokenizer 回退。

只读 explorer Feynman 已确认：

- Mem0 extraction LLM 可使用官方 `response_callback`，无需修改第三方源码。
- Mem0 embedding 的官方返回值丢弃 usage，适合在实例方法边界做第一方 wrapper。
- MemoryOS LLM 和 embedding 已由第一方 adapter 接管，可直接观测。
- MemoryOS 后续 Task 8 已确认需要最终 prompt memory context，因而采用了最小纯
  observer；本处为早期调查记录，最新状态见文件末尾稳定断点。
- Mem0 callback 无内建同步，必须依赖 ContextVar 隔离；MemoryOS 当前固定单 worker。

## 历史断点（已完成）

以下是 Task 5 完成时的历史断点，Task 6-8 现在均已完成。恢复时不要从这里继续，
应读取文件末尾“最近稳定断点”。

1. 为 LLM Judge evaluator 写 RED：离线 F1 不创建 Judge observation；真实 judge 调用记录
   input/output tokens。
2. 修改 evaluator 与 evaluation runner，写 evaluator-side model inventory 和
   efficiency observations。
3. 保持 prediction artifact 可复用，不重新调用 method。

### Task 3：标准 artifact、模型清单与 resume 身份

新增：

- `src/memory_benchmark/observability/efficiency/storage.py`
- `tests/test_efficiency_storage.py`
- `tests/test_prediction_efficiency_observations.py`

修改：

- `src/memory_benchmark/storage/experiment_paths.py`
- `src/memory_benchmark/runners/prediction.py`
- efficiency package exports

已实现：

- prediction/evaluator 各自独立的 model inventory 与 observation 路径。
- evaluator metric 路径安全校验，并保留 `prediction` 作为禁止覆盖的名称。
- 强类型 observation JSONL round-trip、稳定排序、幂等 merge。
- 相同 observation id 内容冲突和磁盘预存重复 id 均强制报错。
- 观测开启时将 model inventory 与 instrumentation identity 写入 immutable
  prediction manifest；resume 在 method factory 和目录副作用前拒绝不一致。
- 观测关闭时不新增 manifest key 或空 artifact，保持既有 schema v2 运行兼容。

验证：

- Task 3 初始 focused tests：`12 passed`。
- Task 3 + prediction/CLI/MemoryOS 相关回归：`71 passed in 1.06s`。
- reviewer 首轮发现 evaluator `prediction` 路径冲突和磁盘重复 id 静默折叠。
- 两项修复先得到 `3 failed, 8 passed` 的有效 RED，再修复至
  `11 passed in 0.10s`。
- 同一 reviewer 复审结论：`APPROVED`。

### Task 4：通用 runner lifecycle

已实现：

- build 由 runner 使用 `perf_counter_ns()` 统一测量完整 conversation add。
- question worker 建立 ContextVar scope，adapter 在 scope 内上报 retrieval/answer。
- worker 只返回 prediction/observation bundle，协调层串行写 observation artifact。
- 新增 `RetrievalObservationContract`，分别声明 profile 是否要求精确 retrieval、method
  是否支持，以及允许 unsupported 时的稳定原因。
- 不兼容 contract 在运行前报错；声明支持却漏报时 scope finalization 报错，禁止静默
  降级。
- 完整运行后的 resume 跳过 method 调用，observation id 不重复。

验证：

- Task 4 RED：runner 未建立 scope 时 `3 failed, 4 passed`。
- 初始实现后 focused tests：`7 passed`；runner/resume 回归：`40 passed`。
- 首轮 reviewer 指出 unsupported 未受 profile/method 契约约束，结论
  `NOT APPROVED`。
- 按 TDD 增加强契约测试后，直接测试 `26 passed`，相关回归
  `116 passed in 1.43s`，`compileall` 通过。
- 同一 reviewer 复审：`APPROVED`。

非阻塞限制：

- question 仍按 conversation batch 提交；崩溃时可能幂等重放，不保证 exactly-once。
- 非 resumable method 的 add 返回到 coarse checkpoint 写入之间仍有既有重放窗口。

### Task 5 当前部分进展

新增：

- `tests/test_method_efficiency_observations.py`

修改：

- `MethodBuildContext` 增加 `efficiency_collector: EfficiencyCollector | None`。
- Mem0/MemoryOS factory 把同一 collector 原样传给 adapter。
- Mem0/MemoryOS 构造器接收并保存可选 collector；尚未上报 observation。

TDD 证据：

- factory 初始 RED：`4 failed`，原因分别是 build context 不接受 collector，以及
  factory 未显式传递 `None`。
- 最小实现后：`4 passed in 0.85s`。
- factory + Mem0 + MemoryOS adapter 离线回归：
  `142 passed, 2 subtests passed in 11.03s`。
- method 目录和新测试 `compileall` 通过。
- 受保护 MemoryOS-LoCoMo 实验聚合哈希仍为
  `2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f`。

#### Mem0 调查结论

- 不需要修改第三方源码。
- 精确 retrieval 边界是 `search -> normalize -> reader messages`；计时应在最终注入上下文
  构造完成后结束。
- `injected_memory_context_tokens` 只统计实际 memory text；无记忆时记录 0，不统计 fallback
  文本。
- reader response usage 可直接读取；extraction LLM 可复用官方 `response_callback`。
- embedding 返回值不含 API usage，应在 `embedding_model.embed/embed_batch` 实例边界
  计时并用匹配 tokenizer 估算输入 token。
- stage 必须依赖 runner 的 operation scope，不能依赖 Mem0 内部 `memory_action` 字符串，
  因为 build 内也会使用 `search` action。

#### MemoryOS 调查结论

- 旧结论曾认为 Phase G 必需字段不需要第三方 observer patch；该判断已被 Task 8
  修正。最终 prompt memory context 需要纯 observer hook，否则
  `injected_memory_context_tokens` 会漏掉 short-term history、user profile 和
  assistant knowledge。
- `retrieve(...)` 与最终 `generate_system_response_with_meta(...)` 已有清晰第一方边界。
- 所有官方 LLM 调用已汇聚到 `_chat_completion_with_retry()`；response usage 可在丢弃
  response 对象前记录。
- 所有 embedding 已汇聚到 `_get_embedding()`；只在 cache miss 的真实 encode 调用上报。
- aggregate injected memory context 现在由官方函数发送 LLM 前的 observer payload 计算；
  Phase G 不做 component-level breakdown。
- MemoryOS retrieval 内部确实会调用 LLM 做 query keyword extraction；Task 5 已通过 TDD
  允许并记录 retrieval-stage LLM observation。
- 本地 MiniLM input token 当前使用 SentenceTransformer 自带 tokenizer 计数，并标注为
  `method_native`。

## Task 1-2 综合 review

Reviewer：James，`gpt-5.4 medium`，只读综合 review。

首轮发现：

1. `stage` 和 measurement source 只依赖类型注解，运行时可传入非法字符串。
2. token source 与 latency source 没有约束各自允许集合。
3. question scope 可以在缺少 `answer_generation_latency_ms` 时生成不完整记录。

修复采用 TDD：

1. 新增 5 个失败场景，RED 为 `5 failed, 24 passed`。
2. 增加运行时枚举校验、metric/source 兼容集合校验。
3. `QuestionEfficiencyObservation.answer_generation_latency_ms` 改为必填。
4. collector finalization 缺 answer latency 时明确报错。
5. GREEN：
   `uv run pytest tests/test_efficiency_entities.py tests/test_efficiency_collector.py tests/test_efficiency_token_counting.py -q`
   得到 `29 passed in 0.09s`。
6. `uv run python -m compileall -q src/memory_benchmark/observability ...` 通过。
7. 同一 reviewer 复审 `APPROVED`，独立验证为 `29 passed in 0.21s`。

非阻塞残余风险：

- 当前确定性 id 测试验证相同 run/调用顺序得到相同 id；Task 3 artifact/resume 测试应
  再覆盖 run_id 或调用顺序变化时 id 发生变化。

## 最近稳定断点

- Task 1 完成。
- Task 2 完成并通过综合复审。
- Task 3 完成并通过复审。
- Task 4 完成并通过复审。
- Task 5 完成：registered prediction 装配、Mem0 observation 和 MemoryOS observation
  已落地。
- Task 6 完成：实际 LLM Judge observation 已落地，离线 F1 不生成 Judge 估算或空
  artifact。
- Task 7 完成：离线效率聚合与真实价格计算层已落地。
- Task 8 完成：MemoryOS 最终 prompt memory context observer 已落地并通过行为等价
  与 focused/full 离线回归。
- Phase G 阶段级综合 review 完成：Franklin `APPROVED`，无 Critical/Important finding。
- 当前下一步为 Phase H 通用并行调度设计/实施入口。
- 未调用真实 API。
- 已修改 MemoryOS vendored 官方 eval 文件，但只增加默认关闭的纯 observer hook，不改变
  核心算法返回。

暂停前验证：

- Task 7 analysis tests：`7 passed in 0.08s`。
- focused Phase G 回归：`95 passed in 7.27s`。
- compileall：`uv run python -m compileall -q src/memory_benchmark tests` exit 0。
- 文档规范：`5 passed in 0.34s`。
- Task 8 RED：`2 failed in 6.93s`，失败符合预期。
- Task 8 GREEN：新增测试 `2 passed in 11.35s`。
- MemoryOS focused：`141 passed, 2 subtests passed in 9.39s`。
- Phase G focused：`232 passed, 2 subtests passed in 17.48s`。
- MemoryOS marker：`172 passed, 353 deselected, 2 subtests passed in 11.94s`。
- 完整离线回归：`522 passed, 3 deselected, 6 subtests passed in 136.37s`。
- API collect only：`3/525 tests collected (522 deselected) in 2.24s`。
- 受保护实验目录聚合哈希：
  `2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f`。
- `predictions.jsonl` 单文件哈希为历史已知的
  `305841f49159995c874e8d1c5995c91923841e207fbac28af0473d104b8320c9`。
- 新实施计划原先误把聚合哈希写成单文件哈希预期，已修正为目录聚合命令；没有改动
  受保护实验资产。

恢复时不需要重读全部历史，只需：

1. 读 `AGENTS.md` 当前断点。
2. 读本 handoff。
3. 读实施计划 Task 8：
   `docs/superpowers/plans/2026-06-15-cost-efficiency-observability.md`。
4. 从 Phase G 阶段级综合 review 开始，不要重复实现 Task 8。

## 禁止事项

- 不启动付费 API。
- 不修改第三方核心算法。
- 不先写生产代码再补测试。
- 不把 injected memory context token 重复计入 answer 费用。
- 不修改或覆盖 `outputs/memoryos-locomo-full-20260603/`。

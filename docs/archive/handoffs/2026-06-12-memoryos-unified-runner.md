# MemoryOS 统一入口迁移交接

日期：2026-06-12

## 当前状态

长期架构已确认，MemoryOS 迁移实施计划已保存：

- `docs/superpowers/plans/2026-06-12-memoryos-unified-runner-migration.md`

Task 1-7 已全部完成：建立 capability/benchmark registration 契约、method factory/build
context 和通用 registered conversation-QA prediction service；MemoryOS TOML、配置校验、
组合 source identity、论文 top-m 接线、恢复状态文件校验、canonical artifacts 和
artifact-only evaluation 均已完成并通过最终整体 review。

## 已完成调查

并行使用两个 Codex explorer：

- `gpt-5.4-mini high`：调查 MemoryOS adapter、专用 runner、legacy resume/artifact 风险。
- `gpt-5.4-mini high`：调查统一 CLI/config/registry/generic runner 扩展契约。

主线程复核后锁定：

- 不把 MemoryOS 强行实现成逐 turn resume；官方写入单位是 QA page。
- 新 generic run 通过 method factory attach 已完成 conversation 的磁盘状态。
- MemoryOS 初始 `max_workers=1`，线程安全验证另开任务。
- `retrieval_top_m_segments` 当前只命中官方默认值 5；TOML 化时必须显式接线。
- 旧 `memoryos_locomo_full` runner 和正式实验输出保留，不与新 resume 混用。

## 基线验证

```bash
uv run pytest \
  tests/test_memoryos_adapter.py \
  tests/test_memoryos_locomo_smoke.py \
  tests/test_memoryos_locomo_full_runner.py \
  -q
```

结果：`55 passed`。

```bash
uv run pytest \
  tests/test_method_registry.py \
  tests/test_config_profiles.py \
  tests/test_prediction_cli.py \
  tests/test_main_cli.py \
  tests/test_prediction_runner.py \
  -q
```

结果：`50 passed`。

未执行真实 API。

## 下一步

按实施计划执行 Task 5：注册 MemoryOS，并使用 fake adapter/system 验证 generic runner
prediction、成本保护和 resume attach；不要启动真实 API。

## 额度中断与 Task 1 验收

Task 1 worker：

- agent id：`019ebc94-ea58-7fb2-8911-11eb0c068f0b`
- 模型：`gpt-5.4`
- reasoning：`medium`
- 文件所有权：capabilities、benchmark registry、对应测试。

worker 在 2026-06-13 因共享额度耗尽报错，没有返回最终报告，但其修改已经落到共享工作区。
主线程恢复后逐文件检查，没有发现越界修改。worker 的 RED 阶段终端输出无法恢复，因此不能
把 RED 结果作为已核验证据；GREEN 和相邻回归由主线程重新执行。

实际修改：

- 新增 `src/memory_benchmark/core/capabilities.py`
- 更新 `src/memory_benchmark/core/__init__.py`
- 更新 `src/memory_benchmark/benchmark_adapters/registry.py`
- 更新 `src/memory_benchmark/benchmark_adapters/__init__.py`
- 新增 `tests/test_benchmark_registry.py`
- 更新 `tests/test_method_registry.py`

主线程验证：

```bash
uv run pytest tests/test_benchmark_registry.py tests/test_method_registry.py -q
```

结果：`13 passed`。

```bash
uv run pytest \
  tests/test_locomo_conversation_adapter.py \
  tests/test_longmemeval_conversation_adapter.py \
  tests/test_main_cli.py \
  -q
```

结果：`32 passed`。

未运行真实 API。受保护实验
`outputs/memoryos-locomo-full-20260603/` 未修改。

## Task 2 完成记录

LoCoMo smoke 数据裁剪职责已经从 CLI 移入
`src/memory_benchmark/benchmark_adapters/locomo.py`。CLI 只导入调用，同时保留旧导入
路径的兼容 re-export，因此现有 API smoke 不需要同步破坏性修改。

TDD RED：

```bash
uv run pytest tests/test_prediction_cli.py -q
```

结果：收集阶段按预期因 LoCoMo adapter 尚无 `build_locomo_smoke_dataset` 而失败。

GREEN 与回归：

```bash
uv run pytest tests/test_prediction_cli.py tests/test_locomo_conversation_adapter.py -q
```

结果：`17 passed`。

```bash
uv run pytest -m api tests/test_mem0_locomo_api.py --collect-only -q
```

结果：收集 `2 tests`，未执行真实 API。

```bash
uv run pytest tests/test_documentation_standards.py -q
```

结果：`5 passed`。相关文件 `compileall` exit 0。

## Task 3 完成记录

已完成：

- `MethodRegistration` 改为 task family、capability、profile、system factory、source
  identity、model/max-worker getter 契约，不再保存 predictor callback 或 benchmark 白名单。
- 新增 `MethodBuildContext`；Mem0 factory 继续调用官方 OSS adapter。
- `load_completed_conversation_ids()` 移入 `runners/ingest_resume.py`。
- 新增 `run_registered_conversation_qa_prediction()`，统一执行 registration 查询、
  compatibility、成本确认、profile/dataset、RunContext、factory、manifest 和 generic
  runner 装配。
- `execute_predict()` 改用统一 service；旧 `run_mem0_locomo_prediction()` 保留兼容转发。
- CLI prediction benchmark choices 改用 `list_prediction_benchmarks()`，未开放的
  LongMemEval 不再出现在可选项中。

TDD/Review 期间发现并修复一项高风险问题：resume 的 completed conversation 初版把包含
`gold_answers/evidence` 的完整对象传给 method factory。现在先通过
`_make_public_conversation()` 重建公开副本，测试明确断言 `gold_answers == {}`。

综合 reviewer：

- agent id：`019ebca5-cefb-7090-a4cb-e8038b38375d`
- 模型：`gpt-5.4 high`
- 最终结论：`APPROVED`

验证：

```bash
uv run pytest \
  tests/test_method_registry.py \
  tests/test_prediction_cli.py \
  tests/test_main_cli.py \
  tests/test_prediction_runner.py \
  -q
```

结果：`48 passed`。

```bash
uv run pytest -q
```

结果：`255 passed, 3 deselected, 4 subtests passed`。

```bash
uv run pytest -m api --collect-only -q
```

结果：收集 `3 tests`，未执行真实 API。完整 `compileall` exit 0。

未来演进风险：当前统一 service 的 smoke scope 仍直接调用 LoCoMo helper。由于当前只有
LoCoMo `prediction_enabled=True`，它符合本阶段计划且不阻塞 MemoryOS Task 5；开放
LongMemEval 或其它 benchmark prediction 前，应把 run-scope/smoke hook 注册化。

受保护实验 `outputs/memoryos-locomo-full-20260603/` 未修改。

## Task 4 完成记录

已完成：

- 新建 `configs/methods/memoryos.toml`；`smoke` 与 `official_full` 只在自动填充的
  `profile_name` 上不同，算法参数完全一致。
- `MemoryOSPaperConfig` 增加 `max_workers`、`profile_name`、公开 manifest，并对模型名、
  整数容量、finite number、threshold、retry 和 bool 字段进行强校验。
- `build_memoryos_source_identity()` 只哈希 `eval/*.py`、`README.md`、`LICENSE`。
- wrapper 使用 `functools.partial` 把 `retrieval_top_m_segments` 显式绑定到官方
  `search_sessions_by_summary(top_k=...)`，未修改第三方源码。
- resume attach 现在会在官方 loader 前校验状态文件：short-term 必需；mid/long 可缺失，
  但存在时必须是合法 UTF-8 JSON 且符合官方顶层 schema。读取、解码和 JSON 错误统一包装
  为 `ConfigurationError`。

综合 reviewer：

- implementer：`019ebea2-8a2c-7bc3-be0b-8ce9dc2c6a89`
- reviewer：`019ebea8-bf60-75c2-8874-f25231a3c6c0`
- 最终结论：`APPROVED`

验证：

```bash
uv run pytest tests/test_config_profiles.py tests/test_memoryos_adapter.py -q
```

结果：`135 passed, 2 subtests passed`。

```bash
uv run pytest -m memoryos -q
```

结果：`164 passed, 205 deselected`。

```bash
uv run pytest -q
```

结果：`368 passed, 3 deselected, 6 subtests passed`。

API collect 为 3 项，未执行；完整 `compileall` exit 0。受保护实验未修改。

## Task 5 实现断点（2026-06-13）

Task 5 的 TDD 实现和相邻回归修复已经落地，但因用户 5h 额度仅余约 8%，当前主动暂停在
独立综合 review 之前。下次不要重复实现，先 review。

已完成：

- `MethodRegistration` 增加最小通用扩展：
  - `display_name`
  - 可选 `workload_estimator`
  - `allow_smoke_worker_override`
- 注册 `memoryos`：
  - task family：`conversation_qa`
  - capabilities：`CONVERSATION_ADD`、`ANSWER_GENERATION`、`MEMORY_RETRIEVAL`
  - profiles：`smoke`、`official-full`
  - profile 路径：`configs/methods/memoryos.toml`
  - `requires_api=True`
- MemoryOS factory 使用配置层提供的 API key/base URL 和当前 run 独占的
  `method_state_dir` 构造 wrapper；resume 时对 completed public conversations 调用
  `load_existing_conversation_state()`，不重复 add。
- selected smoke dataset 确定后、system factory 构造前，调用
  `MemoryOS.estimate_add_workload()` 聚合 `total_update_batches`，结果写入无 secret 的
  method manifest。
- MemoryOS `max_workers` 固定读取 TOML 配置值 1；`smoke_max_workers=2` 不能覆盖。
  Mem0 原有 smoke 并发覆盖行为继续保留。
- CLI 的 method choices 通过 registry 自动包含 `memoryos`；`main.py` 无需专门特判。
- 新路径调用通用 `run_predictions()`，没有调用 legacy
  `run_memoryos_locomo_full()`。

TDD 初始 RED：

```bash
uv run pytest \
  tests/test_method_registry.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_main_cli.py \
  -q
```

结果：`6 failed, 22 passed`；失败原因是 MemoryOS registration/CLI choice 尚不存在。

主线程随后扩大相邻 suite，发现两项真实回归：

```bash
uv run pytest \
  tests/test_prediction_cli.py \
  tests/test_method_registry.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_main_cli.py \
  tests/test_prediction_runner.py \
  -q
```

初次结果：`2 failed, 51 passed`。

根因：

1. API 成本确认被放到 profile/dataset/workload 读取之后，破坏了“未确认前不读取 profile、
   dataset、settings 或构造 factory”的既有契约。
2. `tests/test_prediction_cli.py` 的 fake registration 未补充新字段。

已修复：

- 在 capability/profile-name 校验后立即执行 `_confirm_prediction_cost()`，然后才读取
  profile、adapter、dataset、settings。
- workload estimate 仍在 selected dataset 产生后、system factory 前执行。
- 更新旧测试 double，并强化 MemoryOS 未确认测试，明确禁止接触 profile 和 adapter。

最新 focused 验证：

```bash
uv run pytest \
  tests/test_prediction_cli.py \
  tests/test_method_registry.py \
  tests/test_memoryos_registered_prediction.py \
  tests/test_main_cli.py \
  tests/test_prediction_runner.py \
  -q
```

结果：`53 passed in 8.42s`，未访问外部 API。

交接文档更新后补跑：

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run pytest tests/test_memoryos_registered_prediction.py -q
```

结果分别为 `5 passed` 和 `3 passed`。期间只补充了新 fake/局部测试函数缺失的中文
docstring，没有改变生产行为。

实现 subagent：

- agent id：`019ebeba-ddee-7f93-a9ab-e52003f24d9b`
- 模型：`gpt-5.4 high`
- 已关闭。

本次涉及文件：

- `src/memory_benchmark/methods/registry.py`
- `src/memory_benchmark/cli/run_prediction.py`
- `tests/test_method_registry.py`
- `tests/test_memoryos_registered_prediction.py`
- `tests/test_main_cli.py`
- `tests/test_prediction_cli.py`

`src/memory_benchmark/cli/main.py` 没有修改，因为它已经动态使用 `list_methods()`。

### 下次精确续接顺序

1. 对 Task 5 做一次独立综合 review，重点检查：
   - 未确认付费前的调用顺序；
   - private data 是否可能进入 workload/factory；
   - resume manifest 中 workload estimate 是否稳定；
   - MemoryOS `smoke_max_workers` 静默忽略是否符合当前计划“不能绕过”的语义；
   - registration 宣称 `MEMORY_RETRIEVAL` 与公共接口能力是否一致。
2. reviewer 有问题时用回归测试修复并复审。
3. 运行完整离线验收：

```bash
uv run pytest -q
uv run pytest -m memoryos -q
uv run pytest -m api --collect-only -q
uv run python -m compileall -q src/memory_benchmark tests
```

4. 更新 `AGENTS.md`、本 handoff 和计划；Task 5 验收后再进入 Task 6。

禁止事项：

- 不执行真实 API。
- 不修改 `third_party/`。
- 不删除或覆盖 `outputs/memoryos-locomo-full-20260603/`。

## Task 5 综合 review 与最终验收（2026-06-13）

独立 reviewer：

- agent id：`019ec006-eb8a-7732-a6ac-27724f166fa2`
- 模型：`gpt-5.5 high`
- 范围：capability、付费确认、private data、resume identity、worker override、
  generic/legacy 边界。
- 最终结论：`APPROVED`

实现/fix subagent：

- agent id：`019ec00a-a7cf-7ec1-91a7-08e45303b1b7`
- 模型：`gpt-5.4 high`
- 最终完成两轮 TDD 修复，已关闭。

review 发现并修复：

1. MemoryOS 初版误声明 `MEMORY_RETRIEVAL`，但没有实现公共 `retrieve()`。
2. registered resume 初版在 immutable manifest 校验前创建目录、构造 MemoryOS 并 attach
   状态。现在使用共享 manifest builder 做只读 preflight；通过后才建目录和 factory，
   `run_predictions()` 内仍二次校验。
3. MemoryOS 不支持的 `--smoke-max-workers` 初版被静默忽略，现在显式报
   `ConfigurationError`；Mem0 smoke override 保持原行为。
4. 复审发现 Mem0 同样没有公共 `retrieve()`，因此也移除未实现的 retrieval capability。
5. `PredictionRunPolicy.conversation_ids` 的 tuple 写入 JSON 后变 list，曾导致完全相同的
   resume 误判 manifest mismatch；现在 manifest 固定序列化为 list/None。
6. 直接调用 `run_predictions()` 时，dataset/public manifest 校验现在先于目录和 logger
   创建，非法输入不会留下空 run。

新增/强化测试覆盖：

- MemoryOS/Mem0 capability 与公共接口一致。
- mismatched resume 在目录、checkpoint、factory、attach 前失败。
- matching selected-conversation resume 不重复 add/get_answer。
- preflight 不写文件。
- MemoryOS worker override 显式拒绝，Mem0 override 保留。
- direct runner 非法输入无目录副作用。

完整离线验收：

```bash
uv run pytest -q
```

结果：`382 passed, 3 deselected, 6 subtests passed in 24.39s`。

```bash
uv run pytest -m memoryos -q
```

结果：`166 passed, 219 deselected, 2 subtests passed in 8.54s`。

```bash
uv run pytest -m api --collect-only -q
```

结果：收集 3 项，未执行。

```bash
uv run python -m compileall -q src/memory_benchmark tests
```

结果：exit 0。

受保护正式实验目录在 Task 5 前后聚合哈希均为：

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

下一步：执行计划 Task 6；不得启动真实 API。

## Task 6 完成记录（2026-06-13）

Task 6 已完成，主要固化新旧运行边界，没有新增 MemoryOS 算法或真实 API 行为。

并行实现：

- canonical artifact/evaluation worker：
  - agent id：`019ec018-a73c-7362-b1a1-12fba211028e`
  - 模型：`gpt-5.4 high`
  - 修改：`tests/test_memoryos_registered_prediction.py`、
    `tests/test_artifact_evaluation_runner.py`
- legacy/docs worker：
  - agent id：`019ec018-dbcc-7670-93b9-5a5c06e2a225`
  - 模型：`gpt-5.4-mini high`
  - 修改：两个 legacy runner docstring、legacy boundary test、`README.md`

综合 reviewer：

- agent id：`019ec01c-ee29-71d1-8c9c-51abdaead219`
- 模型：`gpt-5.4 medium`
- 初审发现 canonical test 漏检查根目录 `summary.json`；补齐后最终 `APPROVED`。

已固化契约：

- 新 registered MemoryOS run 真实调用 generic `run_predictions()`，只写 canonical
  artifacts/checkpoints/summaries。
- 根目录 legacy aliases `predictions.jsonl`、`scores.jsonl`、`summary.json`、
  `conversation_status.json` 均不会由新 generic run 创建。
- canonical `method_predictions.jsonl` 包含 `question_text`，可直接与 public question 和
  private label artifacts 对齐。
- 已有 canonical predictions 可通过 `run_artifact_evaluation()` 离线计算 LoCoMo F1，
  不需要重跑 method 或读取 API secret。
- 旧 full/smoke runner 仍可导入，只用于历史 run 的解释、复查和复现；不得与新 generic
  resume 混用。
- README 已增加 MemoryOS 统一 `predict/evaluate` 命令，并说明 official-full 双重确认、
  当前 conversation 串行和 2026-06-03 旧 run 不自动迁移。

验证：

```bash
uv run pytest \
  tests/test_memoryos_registered_prediction.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_memoryos_locomo_full_runner.py \
  -q
```

结果：`55 passed in 2.54s`。

```bash
uv run pytest -q
```

结果：`385 passed, 3 deselected, 6 subtests passed in 23.29s`。

```bash
uv run pytest -m memoryos -q
```

结果：`167 passed, 221 deselected, 2 subtests passed in 8.02s`。

API collect 为 3 项，文档规范 5 passed，compileall exit 0；均未执行真实 API。

受保护实验目录聚合哈希仍为：

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

下一步：执行计划 Task 7 文档与阶段最终 review。

## Task 7 历史暂停断点（已解决，2026-06-13）

以下内容记录当时的暂停状态，仅用于追溯；其中 blocker 已由后续“Task 7 最终关闭”
章节解决，不再是当前执行指令。

用户当时提示 5h 额度仅余约 4%，因此在最终 reviewer 返回后主动暂停，没有继续修改代码。

本轮已完成：

- Task 5 两轮 TDD 修复与独立 review：
  - Mem0/MemoryOS 移除未实现的 public retrieval capability。
  - registered resume 在建目录、checkpoint 读取、factory 和 attach 前执行只读 immutable
    manifest preflight。
  - MemoryOS 不支持的 worker override 显式报错，Mem0 override 保留。
  - `conversation_ids` manifest 规范化为 JSON-stable list/None。
  - direct `run_predictions()` 非法输入在目录/logger 副作用前失败。
- Task 6：
  - 新 generic MemoryOS run 只写 canonical artifacts。
  - canonical predictions 可 artifact-only 复算 LoCoMo F1。
  - legacy full/smoke runner 明确为历史复现用途。
  - README 增加统一 MemoryOS predict/evaluate 命令。
- Task 7 文档状态：
  - `docs/architecture.md` 和 README 已反映 Mem0/MemoryOS 共用 generic runner。
  - LoCoMo 仍是唯一 prediction-enabled benchmark；LongMemEval 尚未开放统一 prediction。

最新验证：

```text
Task 6 focused: 55 passed
full pytest: 385 passed, 3 deselected, 6 subtests passed
memoryos marker: 167 passed, 221 deselected, 2 subtests passed
API collect-only: 3 tests
documentation standards: 5 passed
compileall: exit 0
```

未调用真实 API。受保护实验目录哈希仍为：

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

最终整体 reviewer：

- agent id：`019ec022-fcc2-71b3-97f7-237a56f5aaec`
- 模型：`gpt-5.5 high`
- 结论：未批准，存在 1 个 Important reproducibility/resume 问题。

当时的阻塞问题：

- `build_memoryos_source_identity()` 当时只哈希
  `third_party/methods/MemoryOS-main/eval/*.py`、README、LICENSE。
- `MEMORYOS_ADAPTER_VERSION` 是手工字符串，不能自动反映
  `src/memory_benchmark/methods/memoryos_adapter.py` 行为变化。
- 因此 wrapper 改变而第三方源码/config 不变时，manifest 可能保持相同，错误允许旧状态
  resume。

当时计划的恢复顺序：

1. 使用 TDD 新增 source identity 测试：
   - identity 包含本项目 wrapper source SHA-256 或等价确定性 revision；
   - wrapper 内容变化会改变最终 source identity；
   - identity 不含 secret、绝对路径和不相关文件。
2. 最小修改 `build_memoryos_source_identity()`：
   - 保留现有 vendored source hash/files；
   - 额外记录 wrapper 相对标识和 SHA-256，或把 wrapper 纳入组合 hash；
   - 不修改第三方源码。
3. 增加 registered resume 测试：wrapper identity 改变时必须在 factory/attach 前报
   manifest mismatch。
4. focused tests + 同一层级最终 reviewer 复审。
5. 通过后勾选 Task 7，运行完整离线回归，更新 AGENTS/handoff，正式关闭
   MemoryOS 统一 runner 迁移计划。

当时暂停期间不要做：

- blocker 修复前，Task 7 保持未完成状态。
- 不启动真实 API。
- 不修改或覆盖受保护实验输出。

## Task 7 最终关闭（2026-06-13）

上节记录的唯一 blocker 已通过 TDD 修复，MemoryOS 统一 runner 迁移计划现已关闭。

最终修复：

- `src/memory_benchmark/methods/memoryos_adapter.py`
  - 保留 vendored 官方 `eval/*.py`、README、LICENSE 的独立 hash。
  - 额外计算当前 `memoryos_adapter.py` wrapper 的 SHA-256。
  - 使用稳定逻辑路径和两个组件 hash 生成组合 `source_sha256`，不记录机器绝对路径。
- `tests/test_memoryos_adapter.py`
  - 证明 wrapper 字节变化只改变 wrapper/组合身份，不改变 vendored 身份。
- `tests/test_memoryos_registered_prediction.py`
  - 证明只有 wrapper 身份变化时，resume 会在 factory、attach、checkpoint 读取和目录
    副作用前 fail-closed。

最终 reviewer：

- agent id：`019ec022-fcc2-71b3-97f7-237a56f5aaec`
- 模型与推理强度：`gpt-5.5 high`
- 结论：`APPROVED`，无 Critical / Important finding。

最终离线验证：

```text
Task 7 focused: 253 passed, 2 subtests passed
full pytest: 386 passed, 3 deselected, 6 subtests passed
memoryos marker: 168 passed, 221 deselected, 2 subtests passed
API collect-only: 3 tests
documentation standards: 5 passed
compileall: exit 0
```

验证没有调用真实 API。受保护实验目录聚合哈希仍为：

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

下一步：

- 不再创建新的 method × benchmark 专用 runner。
- API 恢复且用户确认成本、规模和正式 `run_id` 后，可运行
  Mem0-LoCoMo `official-full` prediction。
- 若继续离线开发，应先为 LongMemEval 的统一 prediction 迁移编写独立 spec/plan，再复用
  当前 registry、registered prediction service、generic runner 和标准 artifacts。

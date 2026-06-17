# Phase F Dataset Variant 与 LongMemEval 交接

更新日期：2026-06-14

## 当前状态

- Phase E 已完成并关闭。
- 用户已确认 Phase F 采用 benchmark registration 管理 variant 和数据准备的方案。
- 已完成两路只读 subagent 调研并关闭 subagent。
- Phase F design spec 已写入：
  `docs/superpowers/specs/2026-06-14-dataset-variant-longmemeval-design.md`。
- spec 自检已完成：
  - 无 `TBD`、`TODO` 或未定义占位要求；
  - variant、scope、batch result 和 manifest v2 命名一致；
  - 明确使用 `RunScope` 强类型；
  - 明确 preflight 前只读 path/TOML/data，全部 child 通过后才读取 `.env`；
  - 明确 `smoke_turn_limit` 仅作为 LoCoMo 现有 CLI 兼容参数，不扩展成通用插件系统。
- 文档规范验证：`5 passed`。
- 用户已确认书面 spec，可以开始实施。
- Phase F 实施计划已写入并通过文档规范检查：
  `docs/superpowers/plans/2026-06-14-dataset-variant-longmemeval.md`。
- Task 1 已完成并由主线程验收：
  benchmark variant contract、registration 校验和 LoCoMo preparation hook。
- Task 1 worker：
  - agent id: `019ec65d-9f5a-7503-93f6-f3b9824ee91c`
  - nickname: `Hume`
  - model/effort: `gpt-5.4-mini high`
  - 限定写集：`contracts.py`、benchmark `registry.py`/`__init__.py`、
    `locomo.py`、`tests/test_benchmark_registry.py`
- Task 1 开始前 focused baseline：
  `tests/test_benchmark_registry.py tests/test_locomo_conversation_adapter.py`
  为 `10 passed`。
- Task 1 review 曾发现 smoke helper 跳过前序 conversation 的规格偏差；已返工恢复为
  “先取前 N 个 conversation，再执行 evidence 覆盖校验”的原语义。
- Task 1 最终验证：
  - focused tests：`23 passed`
  - `compileall`：exit 0
- Task 2 已派发：
  - agent id: `019ec669-8f10-77d1-886a-c65c223f7039`
  - nickname: `Erdos`
  - model/effort: `gpt-5.4-mini high`
  - 范围：LongMemEval S/M adapter、registration 和对应 tests
- 因用户额度只剩约 6%，Task 2 已在安全 TDD RED 点中止并关闭 subagent：
  - 只修改了 `tests/test_longmemeval_conversation_adapter.py` 和
    `tests/test_benchmark_registry.py`；
  - 尚未修改 `longmemeval.py` 或 `registry.py` 的 Task 2 生产实现；
  - focused run：`10 failed, 25 passed`；
  - 10 个失败均为预期新契约缺失：M variant 构造、variant metadata、S/M
    registration、prediction enable 和 M preparation；
  - 未启动 full-M 测试，无后台 pytest/python session。
- 暂停前文档规范检查最初发现 Task 1 测试中的 4 个 nested helper 缺中文 docstring；
  已只补充测试说明，重跑 `tests/test_documentation_standards.py` 为 `5 passed`。
- 当前没有运行中的 subagent、pytest、LongMemEval 解析或 API 进程。
- manifest v2 只读调用点盘点已由 Aristotle 完成并关闭。结论：
  - `prediction.py`、registered CLI、prediction runner tests 和 API smoke call sites
    需要显式传入 variant/run scope；
  - `test_artifact_evaluation_runner.py` 的 schema v1 fixture 必须保留，用于验证 legacy
    artifacts 仍可离线 evaluate；
  - ingest checkpoint 的 schema v1 与 prediction manifest 版本无关，不得误改。
- canonical LongMemEval 文件存在：
  - S: 265M，SHA-256
    `d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`
  - M: 2.5G，SHA-256
    `9d79e5524794a2e6900a3aa9cb7d9152c5a3e8319c9a87c25494ba1eacee495f`
- 2026-06-15 恢复后 Task 2 已完成：
  - 使用成熟依赖 `ijson==3.5.0` 流式解析顶层数组；
  - `limit=1` 不再先解析完整 2.5GB M 文件；
  - S/M concrete variant、source/split/variant metadata、S->M 注册顺序和
    LongMemEval prediction enable 均已实现；
  - smoke 固定读取一个完整 instance，忽略 LoCoMo 专属 smoke limits；
  - limited load 使用 `total_raw_instances=<实际加载数>` 与
    `source_fully_scanned=False`，不伪装成完整源计数；
  - focused non-full-M：`34 passed, 1 deselected`；
  - full-M 500 instances 只运行一次并通过：pytest `94.20s`，real `96.27s`；
  - private-boundary：`25 passed, 1 deselected`；
  - 文档规范：`5 passed`；compileall exit 0；
  - GREEN 后删除了流式迁移遗留的未调用 `_instance_items()`。
- Task 3 已派发：
  - agent id: `019ec921-e594-76c1-b099-476254dfa383`
  - nickname: `Singer`
  - model/effort: `gpt-5.4 medium`
  - 限定写集：`runners/prediction.py`、`tests/test_prediction_runner.py`、
    `tests/test_artifact_evaluation_runner.py`
  - 目标：schema v2、variant/scope resume identity、明确拒绝 v1 resume，同时保留
    schema v1 artifact-only evaluation。
- Task 3 已完成并由主线程验收：
  - RED：`24 failed, 12 passed`，均为新签名尚未实现；
  - GREEN：prediction + artifact evaluation `36 passed`；
  - 文档规范 `5 passed`，compileall exit 0；
  - generic manifest 已升级 schema v2，显式记录 concrete variant/run scope；
  - schema v1 generic artifacts 仍可离线 evaluate，但 v2 service resume 会给出专门错误；
  - legacy MemoryOS runner 与 ingest checkpoint schema 未修改。
- Task 4 已派发：
  - agent id: `019ec926-a7e7-7920-a7de-2ae660bf0d19`
  - nickname: `Herschel`
  - model/effort: `gpt-5.4 high`
  - 限定写集：registered prediction service 及其 Mem0/MemoryOS 装配测试；
  - 目标：batch result、run-id 规则、registration.prepare、全 child 原子 preflight、
    secret 延迟加载和 direct caller 签名迁移。
- Task 4 已完成并由主线程验收：
  - registered prediction service 统一返回 `PredictionBatchResult`；
  - `variant=None` 使用默认 concrete variant，`all` 按 registration 顺序展开；
  - LongMemEval 的显式和自动 child run_id 都包含 concrete variant，LoCoMo 单 variant
    run_id 保持原形式；
  - 任一 child preflight 失败时，不读取 OpenAI secret、不创建输出目录、不构造 method；
  - 所有 child preflight 通过后只读取一次 OpenAI settings，再逐 child 创建独立 method；
  - generic service 不再 import LoCoMo adapter/smoke helper；
  - API tests 仅执行 collect，未触网；
  - worker GREEN：`28 passed`，文档规范 `5 passed`，compileall exit 0；
  - 主线程补充跨 variant 后缀歧义测试，拒绝把 `exp-s-cleaned` 当作
    `m_cleaned` 的 base run_id；
  - 主线程最终 focused：`29 passed`，compileall exit 0。
- Task 5 已派发：
  - agent id: `019ec934-c48c-73c2-ae21-8cc773247f9c`
  - nickname: `Bernoulli`
  - model/effort: `gpt-5.4 medium`
  - 限定写集：统一 CLI/command、evaluator registry、必要 exports 和 Task 5 tests；
  - 目标：自由字符串 `--variant`、batch `run` 结果、逐 child 独立 evaluation、
    LongMemEval judge 注册和不触网 S smoke artifact 装配验证。
- 2026-06-15 Task 5 已完成并由主线程验收：
  - RED：`uv run pytest tests/test_main_cli.py tests/test_prediction_cli.py
    tests/test_evaluator_registry.py tests/test_artifact_evaluation_runner.py -q`
    初次在收集阶段失败，报错为缺少
    `RunVariantResult`：`ImportError: cannot import name 'RunVariantResult' from
    'memory_benchmark.cli.commands'`。
  - GREEN：同一 focused suite 最终 `57 passed`；
  - 文档规范：`5 passed`；
  - `compileall`：exit 0；
  - `PredictCommand` 新增 `variant: str | None`，统一 command service 透传到
    registered prediction；
  - `execute_predict()` 对单 variant 与 `all` 均返回 `PredictionBatchResult`；
  - `execute_run()` 改为按每个 concrete child run 独立执行 evaluation，返回
    `{benchmark, selector, runs}`，不再跨 variant 合并结果；
  - argparse 的 `predict`/`run` 已接受自由字符串 `--variant`，benchmark choices
    通过 registry 暴露 LongMemEval，未知 variant 不在 argparse 层硬编码；
  - evaluator registry 已注册 `longmemeval-judge`，复用现有
    `LongMemEvalJudgeEvaluator` 和 `configs/evaluators/llm_judge.toml`
    的 `compact`/`detailed` profile，并限制只支持 `longmemeval`；
  - 新增离线 LongMemEval-S smoke 装配测试：验证一个完整 instance、manifest v2
    中的 `benchmark_variant=s_cleaned` 与 `run_scope=smoke`、public/private artifacts
    分离，以及不读取真实 `.env`。
- Task 4 阶段只读 reviewer 发现 variant run-id 安全缺口，主线程已按 TDD 修复：
  - RED：`tests/test_benchmark_registry.py` 新增 6 个失败，覆盖 `/`、`..`、空格、
    隐藏路径和 `a_b` / `a-b` 归一化碰撞；
  - production 现在要求 variant 名仅使用字母、数字、下划线和连字符，且首字符必须
    是字母或数字；
  - registration 构造阶段拒绝归一化后相同的 run-id token；
  - 命令层复用 contract 层唯一规范化函数；
  - focused 验证：`tests/test_benchmark_registry.py tests/test_prediction_cli.py`
    为 `46 passed`。
- 当前尚有一个已定位、未修复的小边界，必须作为下次第一项：
  - `run_registered_conversation_qa_prediction()` 无条件调用
    `load_openai_settings()`，即使 method registration 的 `requires_api=False`；
  - Task 5 的离线 LongMemEval smoke 用 monkeypatch 返回假配置，因此证明了不读真实
    `.env`，但没有证明配置加载函数完全不被调用；
  - 下次需先写 RED：offline method 的 `load_openai_settings()` 若被调用就抛错；
  - 最小修复方向：`MethodBuildContext.openai_settings` 支持可选值，registered service
    只在 `requires_api=True` 时加载；Mem0/MemoryOS factory 继续强校验非空；
  - 该修复完成并通过 focused tests 后，才把 Task 5 视为最终关闭并进入 Task 6。
- 2026-06-15 恢复后，该 offline method 边界已按 TDD 修复并关闭：
  - RED：离线 LongMemEval-S smoke 把 `load_openai_settings()` 改为一旦调用就抛错，
    失败堆栈准确落在 registered service 的无条件配置加载；
  - `MethodBuildContext.openai_settings` 现在是可选依赖；
  - registered service 只在 `method_registration.requires_api=True` 时加载 OpenAI
    settings，离线 method 收到 `None`；
  - Mem0/MemoryOS factory 对缺失 OpenAI settings 保持强约束；
  - 单测 GREEN：离线 smoke `1 passed`，registry/CLI/MemoryOS focused `39 passed`；
  - 扩展 Task 5 focused suite 最终 `96 passed`，compileall exit 0。
- Task 6 当前进度：
  - README 已说明 `--profile` 与 `--variant` 的职责、LongMemEval
    `s_cleaned/m_cleaned/all` 和独立 child run 语义；
  - README 文档规范 `5 passed`；
  - 完整默认回归：`441 passed, 3 deselected, 6 subtests passed`；
  - MemoryOS marker：`168 passed, 276 deselected, 2 subtests passed`；
  - API 仅收集：`3/444 tests collected`，未执行；
  - 文档规范：`5 passed`；compileall exit 0；
  - 受保护实验聚合 SHA-256：
    `2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f`；
  - 手工契约扫描：通用 registered service/command/runner 不 import 具体 benchmark
    adapter；`all` 只在 selector 解析层出现，manifest 拒绝非 concrete variant；
  - `gpt-5.5 xhigh` 最终只读 review 正在进行，尚未返回结论。
- `gpt-5.5 xhigh` 阶段级综合 review 已返回 `NOT APPROVED`，5 条 finding 均经主线程
  核验成立：
  1. resume manifest 未纳入 source-file fingerprints；
  2. source SHA-256 使用 `read_bytes()`，M smoke 会把约 2.7GB 文件整体读入内存；
  3. child run 目标路径缺少 canonical outputs 边界与大小写等价碰撞检查；
  4. canonical public artifact 丢失 method-visible `question_time`；
  5. LongMemEval list/dict answer 因缺少 `json` import 触发 `NameError`。
- 首次 review 的 5 项 finding 已全部完成 TDD 修复：
  - source fingerprint 已进入 schema v2 resume identity，源文件变化会拒绝恢复；
  - 源文件 SHA-256 改为固定 1 MiB chunk 的 bounded streaming hash；
  - child run 目标在 prepare/secret/目录/method 前完成 canonical outputs-root、
    symlink escape 和大小写等价碰撞检查；
  - canonical public artifact 显式保存 `question_time`，artifact-only evaluation
    可还原该值，旧 artifact 缺字段时兼容为 `None`；
  - LongMemEval list/dict answer 使用稳定 JSON 序列化。
- Carver 和 Linnaeus 的修改已由主线程验证。Goodall 在执行 source fingerprint 任务时
  卡死且没有产生可采用结果，旧 agent 已废弃；主线程按既有 RED tests 接管并完成修复。
- 修复后 focused 验证：
  - source fingerprint/storage/prediction/evaluation：
    `64 passed, 4 subtests passed`；
  - path/question_time/LongMemEval answer：`84 passed`；
  - Phase F 组合：`170 passed, 4 subtests passed`；
  - 文档规范：`5 passed`；compileall exit 0。
- 修复后完整离线回归：
  - 默认：`450 passed, 3 deselected, 6 subtests passed`；
  - MemoryOS marker：`168 passed, 285 deselected, 2 subtests passed`；
  - API 仅收集：`3/453 tests collected`，未执行真实 API；
  - 受保护实验聚合 SHA-256 仍为
    `2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f`。
- 新的最终只读 reviewer：
  - agent id: `019eca5f-69f3-7f11-9c86-624af8598e06`
  - nickname: `Bernoulli`
  - model/effort: `gpt-5.5 xhigh`
  - 结论：`APPROVED`，无 Critical/Important correctness finding；
  - reviewer focused verification：`20 passed in 2.10s`，未运行 API 或 full-M；
  - 首次 5 项 finding 和 Task 6 高风险契约均验证通过。
- reviewer 记录的非阻塞 residual risks：
  - M variant 的源文件哈希虽然内存有界，仍需顺序读取完整约 2.5 GB 文件；
  - 本地文件系统在 preflight 与 execution 之间仍存在理论 TOCTOU 窗口。
- 未调用真实 API。

## 已确认设计

- `--profile` 只表示 method profile。
- `--variant` 只表示 benchmark 数据版本。
- LongMemEval concrete variants：
  - `s_cleaned`
  - `m_cleaned`
- `all` 是命令层 selector，不进入 adapter、Dataset、manifest 或 evaluator。
- `all` 展开为两个完全独立的 child run。
- 用户基础 run ID `exp1` 展开为：
  - `exp1-s-cleaned`
  - `exp1-m-cleaned`
- LongMemEval 单 concrete variant 同样使用 variant 后缀。
- LoCoMo 是单 variant benchmark，保留现有 run ID 形式。
- LoCoMo smoke 裁剪迁入 benchmark registration hook。
- LongMemEval smoke 只选择一个完整 evaluation instance，不裁剪内部 sessions/turns。
- manifest 升级到 schema v2，显式记录 `benchmark_variant` 和 `run_scope`。
- schema v1 generic artifacts 仍可离线 evaluate，但不能通过 v2 service resume。
- `predict` 和 `run` 的统一 command service 返回 batch 结果。
- Phase F 不实现 retrieval recall、效率指标、跨 run 并行或真实全量实验。

## Subagent 关键发现

### Adapter/Registry 调研

- 当前 variant 选择必须在 adapter 构造前完成，不能放到加载后的
  `validate_benchmark_rules()`。
- variant 属于 benchmark registration，不应进入 method registry/TOML/capability。
- 实际 source path 必须随 concrete variant 变化，否则 fingerprint/resume 身份不完整。

### Runner/Resume 调研

- 历史上 `run_registered_conversation_qa_prediction()` 曾直接 import 和调用 LoCoMo
  smoke helper；Phase F 已通过 benchmark registration preparation hook 消除该耦合。
- `all` 必须在 `RunContext.create()` 和 manifest 写入前展开。
- 全部 child 必须先通过只读 preflight，才能创建任一目录或 method。
- variant、run scope、dataset hash、source fingerprint、policy 和 method 配置共同组成
  resume 身份。

## 精确断点

1. Phase F Task 1-6 已全部关闭，最终 reviewer 明确 `APPROVED`。
2. 下一主线为 Phase G 通用并行调度；编码前先形成并和用户确认独立设计方案。
3. 不要重复执行 full-M 500 instances 测试；真实 API 仍保持关闭。
4. 不要操作或等待旧 Goodall；该 agent 已作为故障实例废弃。

## 恢复顺序

1. `AGENTS.md`
2. `docs/current-roadmap.md`
3. 本 handoff
4. `docs/superpowers/specs/2026-06-12-project-goals-architecture-design.md`
5. 派发 subagent 前读取 `docs/subagent-strategy.md`

Phase F implementation plan/design spec 已完成，只在核验历史决策时按需读取。

## 当前验证基线

Phase F 修复后当前基线：

```text
uv run pytest -q
450 passed, 3 deselected, 6 subtests passed

uv run pytest -m api --collect-only -q
3/453 tests collected

uv run pytest -m memoryos -q
168 passed, 285 deselected, 2 subtests passed

uv run python -m compileall -q src/memory_benchmark tests
exit 0
```

受保护实验聚合 SHA-256：

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

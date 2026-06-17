# Agent Memory Benchmark Framework 入口

本文件是项目级最高优先级续航入口。除系统/developer 指令和用户当前最新指令外，新窗口、新上下文和新 subagent 都应先读本文件，再按链接读取 handoff/spec/plan。

本文件只放关键规则、当前断点和导航链接；详细历史、实验结果、review 过程放在 `docs/handoffs/`。

## 当前项目方向

- 长期目标是可复现、可扩展、可审计的多 task-family Agent Memory Benchmark 框架。
- 当前只实现 **conversation + QA** task family；真实出现第二种 benchmark 形式前不拆
  `core/`、不预先设计新协议。
- Phase 1 只跑纯文本闭环：先以 LoCoMo 打通各个 method，再接入 LongMemEval。
- HaluMem、MemBench、Mem-Gallery 当前不进入主线；能自然适配 conversation + QA 的切片
  可后续接入，不能自然适配的内容必须等真实需求出现后归入新的 task family。
- 多模态字段保留，但 Phase 1 不跑多模态。
- PrefEval 已移除。不要恢复 PrefEval 的仓库、adapter、测试、文档或论文内容。
- 当前已实现 answer 质量评测，不做 retrieval recall。成本与效率原始 observation 底座
  已完成并覆盖 Mem0/MemoryOS；真实费用在实验完成后按实际 API 服务商价格离线计算。
- 当前用户明确要求暂缓通用并行调度，优先接入 A-Mem 与 LightMem adapter。

## 当前断点

- 当前动态主计划：`docs/current-roadmap.md`。已完成项必须立即勾选；后续恢复优先读取
  本文件、动态路线图、当前实施计划和最新 handoff，不重复扫描历史大文档。
- 最新完整回归（2026-06-15）：`uv run pytest -q` 为 450 passed、3 deselected、
  6 subtests passed；MemoryOS marker 为 168 passed、285 deselected、2 subtests passed；
  API collect 为 3 项；文档规范 5 passed；`compileall` exit 0。验证过程未执行付费 API。
- src-layout、pytest、可观测性、标准实验产物、通用 conversation-QA prediction runner、
  turn-level resume、统一 CLI/config 均已完成。
- 正式 MemoryOS-LoCoMo 全量实验
  `outputs/memoryos-locomo-full-20260603/` 是受保护实验资产，不得删除或覆盖。
- Mem0 OSS + LoCoMo 已完成单 conversation 与双 conversation 并发 smoke；统一入口当前
  支持 Mem0 + LoCoMo prediction 和 artifact-only evaluation。具体实现、竞态修复和
  resume 约束按下方 handoff/spec 导航按需读取。
- 最新长期架构方向已固化到
  `docs/superpowers/specs/2026-06-12-project-goals-architecture-design.md`。
- MemoryOS 统一入口迁移计划已写入
  `docs/superpowers/plans/2026-06-12-memoryos-unified-runner-migration.md`。
- MemoryOS 迁移计划 Task 1-7 已全部完成并通过最终整体 review：已建立 capability/benchmark registration、
  method factory/build context 和通用 registered conversation-QA prediction service；
  LoCoMo smoke 数据裁剪已归位 benchmark adapter；MemoryOS TOML、强配置校验、
  deterministic source identity、论文 top-m 接线和恢复状态文件校验已完成。source identity
  同时覆盖 vendored 官方 `eval/` 源码和本项目实际执行的 wrapper 源码。
- Task 5 已完成并通过独立综合 review：MemoryOS 已注册到 generic runner，factory/resume attach、
  update-batch workload manifest、固定单 worker、CLI method choice 和付费确认前置均有
  离线测试。Mem0/MemoryOS 仅声明实际实现的 add/answer capability；registered resume
  在建目录和 method factory 前完成只读 manifest preflight。
- Task 6 已完成并通过综合 review：新 generic MemoryOS run 只写 canonical artifacts，
  可直接 artifact-only 复算 LoCoMo F1；legacy runner/alias 只保留历史复查与复现。
- Task 7 已完成：wrapper 源码变化会改变组合 source identity，并在 factory、resume attach
  和目录副作用前拒绝不兼容旧 run；最终 reviewer 明确 `APPROVED`。
- Phase E 已完成并通过阶段级综合 review。官方仓库现位于
  `third_party/benchmarks/`，runtime 数据现位于 canonical `data/` 子目录，两组参考资料
  已迁入 `docs/`；adapter、registry、legacy runner、测试和当前文档路径均已更新。
  canonical 数据真实性测试为 9 passed，受保护实验哈希未变化。设计和实施计划分别位于
  `docs/superpowers/specs/2026-06-14-project-structure-data-migration-design.md` 和
  `docs/superpowers/plans/2026-06-14-project-structure-data-migration.md`。
- Phase G 成本与效率观测已完成，真实付费实验仍需等待用户确认 API 余额、规模和
  正式 run_id。
  运行阶段只记录原始 token、延迟、调用与模型身份；真实费用不得绑定 OpenAI 官方价格，
  必须在实验结束后按实际 API 服务商价格独立计算。
  当前设计稿位于
  `docs/superpowers/specs/2026-06-15-cost-efficiency-observability-design.md`；用户确认书面
  spec 后已进入实施。实施计划位于
  `docs/superpowers/plans/2026-06-15-cost-efficiency-observability.md`。Task 1-4 已完成：
  强类型 observation、ContextVar collector、token 计量、标准 efficiency artifact、
  模型清单、prediction manifest/resume 身份和通用 runner lifecycle 均已落地。
  retrieval 使用显式 profile/method 强契约；并发/resume 相关回归为 116 passed，
  Task 4 reviewer 复审 `APPROVED`。Task 5 已完成：TDD 允许 retrieval-stage LLM
  observation；registered prediction 已创建并传递 collector、model inventory、
  instrumentation identity 和 retrieval contract；Mem0 已记录 retrieval latency、
  injected memory context tokens、answer latency、build/answer LLM tokens 和
  build/retrieval embedding tokens/latency；MemoryOS 已记录 retrieval latency、
  injected memory context tokens、answer latency、retrieval/answer LLM tokens 和
  build/retrieval 本地 embedding tokens/latency。Task 6 已完成：实际 LLM Judge 自动
  写 evaluator 专属模型清单和 judge LLM token observation；离线 F1 不生成 Judge
  observation、空文件或估算数据。Task 7 已完成：`memory_benchmark.analysis`
  支持离线 efficiency 聚合与 Decimal 真实价格计算，`injected_memory_context_tokens`
  不重复计入 answer LLM 费用，缺 API 价格报告 incomplete，本地模型零成本，跨币种直接
  相加会报错。最新 Phase G focused 回归：analysis tests `7 passed`；Phase G focused
  回归 `95 passed`；文档规范 `5 passed`；`compileall` exit 0。Task 8 已完成：
  MemoryOS 官方 `generate_system_response_with_meta()` 增加可选纯 observer hook，
  wrapper 注入实例级 callback，并用最终 prompt memory context 计算
  `injected_memory_context_tokens`；observer 开关不改变答案、prompt、client 调用和状态。
  最新离线验证：Task 8 新增测试 `2 passed`；MemoryOS focused `141 passed, 2 subtests
  passed`；Phase G focused `232 passed, 2 subtests passed`；MemoryOS marker
  `172 passed, 353 deselected, 2 subtests passed`；完整离线回归 `522 passed,
  3 deselected, 6 subtests passed`；API 仅 collect `3/525 collected`；`compileall`
  exit 0；受保护实验目录聚合哈希未变化。Franklin 只读阶段级综合 review `APPROVED`，
  无 Critical/Important finding。未执行真实 API。
  当前精确断点已从 Phase H 通用并行调度切换到 A-Mem / LightMem adapter 接入；不得启动
  付费实验，除非用户显式确认 API 余额、实验规模和正式 run_id。
- A-Mem / LightMem 接入设计已写入
  `docs/superpowers/specs/2026-06-16-amem-lightmem-adapter-design.md`。实施顺序为：
  先 A-Mem 垂直闭环，再 LightMem；都必须复用通用 conversation-QA runner、标准
  artifact、resume 和 Phase G efficiency observation，不创建 method × benchmark 专用
  runner。
- 2026-06-16 当前分支已初始化为 Git 仓库，当前分支
  `feature/amem-lightmem-adapters`，尚未做 initial commit。`.gitignore` 已保护
  `data/`、`models/`、`outputs/`、`.env`、`.claude/`、`third_party/benchmarks/` 和
  third-party 生成物；不得把大型 dataset/model/output 加入 Git。
- A-Mem 与 LightMem adapter 已完成 config、source identity、registry、question-level
  efficiency observation、fake/offline contract 和 registered runner smoke。LightMem 生产
  backend 已通过测试覆盖官方 `LightMemory.from_config()` 配置注入，但尚未执行真实 API
  smoke。当前已确认 smoke 也必须使用官方 method 参数，成本控制只通过 benchmark 数据规模
  裁剪；资源与参数审计见 `docs/method-resource-parameter-audit.md`。A-Mem smoke
  `retrieve_k=10`，Mem0 smoke `top_k=200`，LightMem smoke `retrieve_limit=60`。
  LightMem 真实运行所需
  `models/all-MiniLM-L6-v2` 和
  `models/llmlingua-2-bert-base-multilingual-cased-meetingbank` 已补齐并通过本地资源
  校验；adapter 仍会在真实 backend 构造前强校验。最新 focused 验证：
  A-Mem/LightMem/profile suite `21 passed,
  2 warnings`；文档规范 `5 passed`；`compileall` exit 0。未执行真实 API。
- A-Mem 官方 robust layer 导入需要 `rank-bm25` 和 `litellm`，已通过 `uv add` 写入
  `pyproject.toml` / `uv.lock`。这是官方 A-Mem requirements 中的正式依赖。
- 本轮精确交接：
  `docs/handoffs/2026-06-16-amem-lightmem-adapters.md`。
- Phase F 已完成并通过 `gpt-5.5 xhigh` 最终只读复审。LongMemEval S/M 使用 `ijson`
  流式加载；full-M 500 instances 已唯一运行一次并通过，不要重复执行该昂贵测试。
  generic prediction manifest 已升级 schema v2，batch registered prediction、
  variant child run_id、统一 CLI/command batch result、LongMemEval judge 注册和
  LongMemEval-S 离线 smoke 装配验证均已完成；`requires_api=False` method 不再加载
  OpenAI settings。Task 6 首次 review 的 5 项 finding 已全部修复：source fingerprint
  resume identity 与分块哈希、canonical child run path 安全、question_time artifact
  round-trip、LongMemEval list/dict answer。修复后完整离线回归和受保护资产哈希均已
  通过；最终 reviewer 明确 `APPROVED`，无 Critical/Important finding。
  精确验证和 legacy schema 保留规则位于
  `docs/handoffs/2026-06-14-dataset-variant-longmemeval.md`。
  后续通用并行调度已顺延到 Phase H；当前不得跳过 Phase G。
  MemoryOS PyPI backend 已降为低优先级，短期不实施。不得擅自启动全量真实 API。
- API 已充值，但未经用户确认 method、benchmark、样本规模和正式 run_id，不得启动真实
  prediction；全量实验仍需额外确认。
- 未经用户确认 API 规模、余额和正式 run_id，不得启动 Mem0 official-full。

恢复工作时按顺序读：

1. `docs/current-roadmap.md`
2. `docs/handoffs/2026-06-16-amem-lightmem-adapters.md`
3. `docs/superpowers/plans/2026-06-16-amem-lightmem-adapter.md`
4. `docs/superpowers/specs/2026-06-16-amem-lightmem-adapter-design.md`
5. 派发 subagent 前读 `docs/subagent-strategy.md`

Phase G 的 plan/spec 已完成，只在核验成本与效率实现细节时按需读取，不作为下一窗口默认输入。

Phase F 的 plan/spec 已完成，只在核验历史决策时按需读取，不作为下一窗口默认输入。

MemoryOS、统一 CLI 和 Mem0 的历史实现细节只在相关任务需要时，按
`docs/handoffs/` 和 `docs/superpowers/` 中对应文件读取，不要默认重复加载。

MemoryOS-LoCoMo 实验细节只在需要时读：

- `docs/handoffs/2026-06-03-memoryos-locomo.md`
- `reports/2026-06-05-memoryos-locomo-category-diagnosis.md`

conversation-QA 重构历史只在需要时读：

- `docs/handoffs/2026-06-02-conversation-qa-refactor.md`

## 核心协议

数据层级：

```text
Dataset -> Conversation -> Session -> Turn
                           -> Question
                           -> GoldAnswerInfo
```

method 侧接口：

```python
class BaseMemorySystem(ABC):
    def add(self, conversations: list[Conversation]) -> AddResult: ...
    def get_answer(self, question: Question) -> AnswerResult: ...

class BaseMemoryRetriever(ABC):
    def retrieve(self, question: Question) -> RetrievalResult: ...
```

规则：

- 依靠 `conversation_id` 做记忆隔离，不做 reset 接口。
- `add()` 接收 `list[Conversation]`，不设计 `add(session)`。
- `get_answer()` 只接收 `Question`，不能接收 gold answer、retrieval result 或 top_k。
- `retrieve()` 是可选能力，只给需要检索模块评测的 benchmark 用；Phase 1 LoCoMo / LongMemEval 不要求它。
- `top_k` 属于 method 自己的配置，不放进统一接口参数。
- method 分为 `end_to_end` 和 `memory_module`；后者必须使用框架固定 reader。
- 自定义 method 当前通过 Python API 传入实现接口的实例；CLI 只运行官方集成。
- 长期兼容判断采用 task family + required/provided capabilities，不维护 method × benchmark 笛卡尔积白名单。

## 私有数据边界

以下内容不能进入 method public input：

- gold answer
- evidence ids
- judge label
- LongMemEval `answer_session_ids`
- LoCoMo `evidence`
- 任何 private metadata

adapter 可以把这些放入 `GoldAnswerInfo` 或 evaluator-only artifact，但 runner 调 method 前必须只传公开对象。

## 目录导航

- `src/memory_benchmark/core/`: conversation-QA 实体、接口、校验、领域异常。
- `src/memory_benchmark/benchmark_adapters/`: 原始 benchmark 数据到统一 `Dataset` 的转换层。
- `src/memory_benchmark/evaluators/`: answer-level metrics 和 LLM judge。
- `src/memory_benchmark/runners/`: 串联 adapter、method、evaluator、artifact/checkpoint 的运行层。
- `src/memory_benchmark/methods/`: 第一方 method wrapper。
- `src/memory_benchmark/observability/`: `RunContext`、事件写入、Rich 进度与 `progress.json`。
- `src/memory_benchmark/storage/`: 标准实验目录、JSONL、数据指纹和 artifact 记录工具。
- `src/memory_benchmark/utils/`: logger、通用工具。
- `third_party/methods/`: 第三方 method 源码，不参与第一方 package 发现或中文文档规范扫描。
- `data/`: adapter 运行时唯一 dataset 入口。
- `third_party/benchmarks/`: 官方 benchmark 仓库当前位置，只用于事实核验、论文和源码参考。
- `outputs/<run_id>/artifacts/`: 可复用实验产物。
- `outputs/<run_id>/logs/`: `run.log`、`events.jsonl` 等运行日志。
- `outputs/<run_id>/checkpoints/`: 断点续跑状态。
- `outputs/<run_id>/summaries/`: 摘要结果。
- `docs/handoffs/`: 长任务和上下文压缩前的精确交接。
- `docs/superpowers/`: 当前设计和实施计划。
- `old/2026-06-02-legacy/`: 历史废纸篓，不作为当前事实来源。

## 事实来源优先级

1. `third_party/benchmarks/` 中的官方仓库真实数据和代码。
2. 本地论文 PDF。
3. Phase E 迁移后的 `docs/dataset_structures/`。
4. Phase E 迁移后的 `docs/evaluation_workflows/`。
5. 每个 benchmark 仓库下同名 `.md` 理解文档。
6. `EVALUATION_ARCHITECTURE.md` 只作参考，不照抄。
7. `old/` 只作历史归档，不作为当前方案事实来源。

材料冲突时必须回到当前官方 benchmark 仓库位置中的原始文件核验。

## 工程规则

- 使用 `uv` 管理和运行 Python。
- 所有 Python 文件顶部必须有中文模块说明；类和函数要有中文 docstring 或注释，解释输入、输出和关键字段。
- 库代码不直接 `print()`；日志通过统一 logger / observability 工具。
- `.env` 只能通过配置层读取，不能打印 secret。
- 强约束优先：缺 required 字段、conversation/question 对不齐、gold 缺失、private 字段泄漏，都应抛项目领域异常。
- 小步快走：每一步都要能单独验证，优先垂直切片。
- 任务按依赖顺序逐步完成，不跳阶段、不提前宣布完成。默认串行；只有任务之间没有
  前置依赖、写入文件不冲突且结果可独立验收时才允许并行。
- 任何实质性架构变化都要先和用户讨论，确认后再改。
- 禁止修改第三方核心算法；wrapper 和配置注入优先放在本项目侧。若 adapter 无法准确
  观测，可在第三方源码加入可关闭、可审计且通过行为等价验证的纯 observer 插桩。
- 长实验 runner 必须写 `logs/run.log`、`logs/events.jsonl` 和 `checkpoints/progress.json`。
- 新 runner 优先写标准 artifacts，只保留迁移所必需的 legacy alias。
- 新增 evaluator 时优先复用已有 `method_predictions.jsonl` 和 `evaluator_private_labels.jsonl`，不要重新调用 method。
- `predict` 与 `evaluate` 必须保持分离；`run` 只做二者的便利组合。
- `run_id` 对应不可变实验；resume 只能继续数据指纹、method、reader 和关键配置完全一致的运行。
- 官方 profile 分为 `official`、`smoke`、`custom`；official 的关键复现参数不可临时覆盖。
- 用户配置采用分层 TOML，禁止为 method × benchmark 创建配置文件笛卡尔积；示例配置必须有详细注释。
- smoke profile 必须使用官方 method 参数；不得为了省钱降低 `top_k`、`retrieve_k`
  或 `retrieve_limit`。成本控制只通过 conversation/question/turn 规模裁剪。
- 效率 observation 未来按逐操作保存。缺少能力时必须在付费运行前报错或标为 unsupported，不能估算冒充实测。
- conversation + QA 全量实验应复用通用 runner；禁止为每个 method × benchmark 组合复制
  `<method>_<benchmark>_full.py`。method、adapter、evaluator 和并发策略通过明确依赖注入。
- conversation 级并行必须保证每个任务按 `add -> 本 conversation questions` 执行，
  worker 不直接并发写共享 JSONL；实验产物由协调层串行提交。
- 当前 Mem0 只接本地 OSS 源码，不接 Mem0 Platform API。实验必须固定 Mem0 版本和源码
  tree hash；升级采用新版本临时验证后再切换，禁止自动跟踪 upstream `main`。
- Mem0 namespace 语义已确认：一个 `conversation_id` 对应一个逻辑 namespace；不复刻
  Mem0 官方 LoCoMo 双 speaker namespace 脚本。speaker 信息保留在 content/metadata，
  `get_answer()` 只检索问题所属 conversation。
- Mem0 并行初版使用共享 OSS `Memory` 实例、`run_id=conversation_id` 和
  `max_workers=2`。OpenAI key/base URL 通过 adapter 配置注入；官方 profile 使用
  `text-embedding-3-small`。真实 API 仅允许显式小量 smoke，默认测试不得触网。
- Phase C src-layout 和 Phase D pytest 迁移须在 Phase A/B 验证后分别制定后续计划。
- Subagent 必须按 `docs/subagent-strategy.md` 动态选择模型和 reasoning effort，
  以满足任务为前提优先节省额度，并根据历史表现升级或降级，禁止所有任务默认使用
  最强模型或高推理强度。
- 默认优先使用 `gpt-5.4-mini medium/high` 或 `gpt-5.4 medium`；只有明确属于
  复杂调试、关键契约或最终整体审查时，才升级到 `gpt-5.5` 或 `high/xhigh`。
- Review 采用风险分级，不再为每个小步骤固定执行 spec review + code-quality review：
  普通局部修改由主线程自检并运行 focused tests；完整功能切片结束后做一次综合 review；
  resume、隐私、指标、公共协议等高风险契约可单独 review；阶段验收前做最终整体 review。
- OpenCode subagent skill 已配置，但当前默认禁用；只有用户明确允许启用后才能调用。

## AGENTS 与 Handoff 维护规则

- `AGENTS.md` 必须保持简洁，作为项目入口和目录，不写长篇历史。
- 阶段目标、当前断点、下一步、长期规则、benchmark 范围、method 接入状态、验证基线或 handoff 索引变化时，必须同步更新 `AGENTS.md`。
- 每个 task 完成、review 发现重要问题、进入/退出长等待、上下文压缩或额度风险前，必须更新 `docs/handoffs/`。
- 关键断点和当前任务索引要同时同步到 `AGENTS.md`。
- 我不能读取用户 5h 额度实时百分比；因此每个小阶段完成后都要主动更新 handoff，降低突然中断风险。

## 常用验证命令

```bash
uv run pytest --collect-only -q
uv run pytest -q
uv run pytest -m memoryos -q
uv run pytest -m api --collect-only -q
uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_llm_judge_parsing.py tests/test_locomo_answer_metrics.py tests/test_documentation_standards.py tests/test_mem0_source_compatibility.py -v
uv run python -m unittest tests/test_conversation_runner.py tests/test_experiment_storage.py tests/test_observability_run_context.py tests/test_observability_progress.py tests/test_run_logger.py tests/test_locomo_conversation_adapter.py tests/test_longmemeval_conversation_adapter.py tests/test_memoryos_adapter.py tests/test_memoryos_locomo_smoke.py tests/test_memoryos_locomo_full_runner.py -v
uv run python -m compileall -q src/memory_benchmark tests
```

当前目录已初始化为 Git 仓库；除非用户明确要求，否则不自动 commit。

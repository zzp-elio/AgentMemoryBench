# 当前动态路线图

更新日期：2026-06-26

本文件只记录当前主线、完成状态和阶段依赖。每完成一个任务必须立即勾选并同步
`AGENTS.md`；逐项 open/closed 状态和历史文档状态以 `docs/task-ledger.md` 为准。
详细实现步骤放在对应 `docs/superpowers/plans/` 文件中。

## 已完成

- [x] conversation + QA 核心实体、公开/私有数据边界和强校验。
- [x] src-layout、pytest、统一日志、Rich 进度和标准实验目录。
- [x] 通用 conversation-QA prediction runner。
- [x] conversation 级线程并行、协调层串行提交 artifact 和断点恢复。
- [x] LoCoMo adapter、官方 F1 和 artifact-only evaluation。
- [x] LongMemEval-S adapter 的结构转换与私有标签隔离。
- [x] Mem0 + LoCoMo 单 conversation 和双 conversation API smoke。
- [x] MemoryOS + LoCoMo 正式历史实验。
- [x] MemoryOS 迁入 method registry、TOML 和通用 runner。
- [x] Mem0/MemoryOS source identity、immutable manifest 和 resume preflight。

## 当前主线

### Phase E：项目结构和数据入口清理

- [x] 核验 `data/` 中 LoCoMo、LongMemEval、HaluMem 和 Mem-Gallery 副本。
- [x] 建立 `data/` 作为运行时 dataset 唯一物理入口。
- [x] 将 `benchmarks/` 整体迁入 `third_party/benchmarks/`。
- [x] 将 `dataset数据结构/` 迁入 `docs/dataset_structures/`。
- [x] 将 `benchmark测评流程参考/` 迁入 `docs/evaluation_workflows/`。
- [x] 统一 dataset 目录名和 Mem-Gallery 内部层级。
- [x] 更新配置、adapter、registry、runner、测试和当前文档中的路径。
- [x] 验证所有 canonical dataset 与官方仓库副本内容一致。
- [x] 完成完整离线回归并确认受保护实验资产未变化。

详细计划：
`docs/superpowers/plans/2026-06-14-project-structure-data-migration.md`

### Phase F：Dataset Variant 和 LongMemEval 闭环（已完成）

本阶段已完成并通过 `gpt-5.5 xhigh` 最终只读复审。设计方案位于
`docs/superpowers/specs/2026-06-14-dataset-variant-longmemeval-design.md`。
实施计划位于
`docs/superpowers/plans/2026-06-14-dataset-variant-longmemeval.md`。

- [x] 增加 benchmark variant 强类型配置。
- [x] LongMemEval adapter 同时支持 `s_cleaned` 和 `m_cleaned`。
- [x] 默认 variant 为 `s_cleaned`；`m_cleaned` 和 `all` 由用户显式选择。
- [x] `all` 展开为多个独立 run，不合并 Dataset、manifest 或指标。
- [x] 把 LoCoMo 专属 smoke/run-scope 逻辑提炼为 benchmark registration hook。
- [x] 在 benchmark registry 中开放 LongMemEval prediction，并完成 batch registered
  prediction 与全 child 原子 preflight。
- [x] 完成统一 CLI/command batch result、LongMemEval judge 注册和离线 LongMemEval-S
  smoke 装配验证。
- [x] 运行不触网 contract/integration 测试。
- [x] 完成 schema v2 source identity、路径安全、`question_time` artifact round-trip
  和 LongMemEval 结构化答案修复。
- [x] 完成完整离线回归、受保护实验哈希校验和阶段级综合 review。

### Phase G：成本与效率观测（已完成）

本阶段先完成原始效率数据的可审计记录，不启动全量付费实验。实验执行与真实费用计算
严格分离：运行时只保存 token、调用、延迟、模型身份和计量来源；实验结束后再按实际
API 服务商价格离线计算费用，不绑定 OpenAI 官方价格。

- [x] 完成成本与效率观测设计方案及实施计划。
- [x] 建立 conversation、question、LLM call 和 embedding call 的强类型原始
  observation、线程隔离 collector、标准 artifact 和模型清单。
- [x] 将 efficiency model inventory、instrumentation identity 纳入 prediction
  manifest/resume 强校验；关闭观测时保持 schema v2 旧运行兼容。
- [x] 通用 runner 已按 conversation/question 建立 observation scope；worker 返回
  observation bundle，协调层串行提交，完成后 resume 不重复 observation。
- [x] 记录 `memory_build_total_latency_ms`。
- [x] 记录可精确拆分的 `retrieval_latency_ms`；无法精确拆分时保存
  `null + unsupported_reason`，禁止估算。
- [x] retrieval observation 使用显式 profile/method 强契约：不兼容组合在运行前
  报错，声明支持却漏报时不允许静默降级。
- [x] 记录 `injected_memory_context_tokens` 和 `answer_generation_latency_ms`。
- [x] 分别记录 memory build 与 answer 阶段的 LLM input/output tokens。
- [x] 记录实际运行 LLM judge 时的 LLM input/output tokens。
- [x] 分别记录 memory build、retrieval 阶段的 embedding input tokens 和 latency。
- [x] 模型清单记录模型名称、local/API 执行方式、版本或本地路径等复现信息。
- [x] token 计量优先使用 API usage 或 method 原生统计；缺失时使用匹配 tokenizer
  估算并标注 `measurement_source`。
- [x] 允许对第三方源码增加经过记录和验证的纯 observer 插桩，但不得改变算法行为。
- [x] 仅在实际运行 LLM judge 时记录 judge input/output tokens；未运行时不生成估算数据。
- [x] 实现独立的离线聚合与价格计算层，价格配置不进入不可变 prediction artifact。
- [x] 先覆盖 MemoryOS、Mem0，再随 adapter 接入覆盖 A-Mem、LightMem。
- [x] Task 5 完成：registered prediction efficiency 装配、Mem0/MemoryOS 精确
  observation、wrapper identity 和 adapter focused 回归均已完成，未执行真实 API。
- [x] Task 6 完成：实际 LLM Judge 自动写 evaluator 专属模型清单和 token
  observation；离线 F1 不创建空文件或估算数据。
- [x] Task 7 完成：`memory_benchmark.analysis` 已支持线性插值效率聚合、
  Decimal API 费用计算、本地模型零成本、缺 API 价格 incomplete 报告和跨币种拒绝。
- [x] Task 8 完成：MemoryOS 最终 prompt memory context observer 已落地并通过
  行为等价测试；wrapper 现在用最终 prompt memory context 计算
  `injected_memory_context_tokens`，未触发 observer 时回退到 retrieval result。
- [x] 完成离线测试、行为等价验证和阶段级综合 review。

### Phase H：A-Mem 与 LightMem Adapter 接入（当前）

用户已明确要求先不做并行调度，优先接入 A-Mem 和 LightMem。设计方案位于
`docs/superpowers/specs/2026-06-16-amem-lightmem-adapter-design.md`。
Method official profile 对齐计划位于
`docs/superpowers/plans/2026-06-17-method-official-profile-alignment.md`。

- [x] 完成 A-Mem / LightMem 接入设计对齐。
- [x] 编写实施计划。
- [x] 接入 A-Mem config、adapter、registry、source identity。
- [x] A-Mem 接入现有 efficiency observation。
- [x] A-Mem 通过 adapter contract、fake/offline 和 registered runner smoke。
- [x] 接入 LightMem config、adapter、registry、source identity。
- [x] LightMem 接入可精确观测的 efficiency observation。
- [x] LightMem 通过 adapter contract、fake/offline 和 registered runner smoke。
- [x] 更新 README、AGENTS 和 handoff 中的 method 接入状态。

说明：A-Mem 与 LightMem 均已完成离线/fake registered runner smoke；未执行真实 API。
LightMem 已通过测试覆盖官方 `LightMemory.from_config()` 生产 backend 配置注入，但真实
API smoke 仍需等待用户确认 API 余额、样本规模和 run_id。2026-06-17 重新审计后确认：
fake/offline runner smoke 只能证明框架链路可运行，不能证明 A-Mem / LightMem 已按论文
Table 级实验设置对齐。

- [x] A-Mem：补齐 Table 1 GPT-4o-mini profile，对齐官方 query keyword generation 和
  Table 8 按类别 `k`。
- [x] A-Mem：真实 API smoke 前确认并修复 ohmygpt base URL 注入；adapter 会在 wrapper
  层替换官方 OpenAI controller client，保持算法、prompt 和调用顺序不变。
- [x] A-Mem：实现 wrapper 层 conversation-level 状态持久化；`add()` 完成后保存
  `memories.pkl`、官方 retriever cache/embeddings 和 `state_manifest.json`，
  resume 时由 registry 对 completed conversations 调 `load_existing_conversation_state()`。
- [x] A-Mem：category 5 adversarial 当前因 gold answer 冲突显式拒绝，不进入普通
  public-input smoke；用户已确认当前不做 LoCoMo adversarial。
- [x] LightMem：补齐当前阶段 Table 2 / Table 3 使用的固定 profile。
  - [x] 用户指定并落实 `(r=0.7, th=512)` official-mini profile。
  - [x] 对齐 LoCoMo / LongMemEval 增量写入粒度。
  - [x] 对齐 LongMemEval `question_time` reader prompt 和 LightMem LoCoMo prompt 布局。
  - [x] LoCoMo 已专门化为 LightMem `search_locomo.py` 风格的 Qdrant payload/vector combined 检索。
  - [x] LoCoMo `add()` 完成后已接入 `construct_update_queue_all_entries()` 和
    `offline_update_all_entries(score_threshold=0.9)`。
  - [x] LightMem：实现 conversation-level resume；resume 时 registry 对 completed
    conversations 调 `load_existing_conversation_state()`，重建对应 backend 用于回答剩余问题。
  - [ ] LightMem 内部算法参数未来可做成 profile/TOML 可配置；当前阶段固定
    `(r=0.7, th=512)`，不把参数 sweep 加入主线。
  - [ ] LongMemEval OP-update 仍是可选 future profile；当前 LongMemEval 保持通用
    `LightMemory.retrieve()` online 路径。
- [x] Mem0：将 `get_answer()` reader 改为 Mem0 memory-benchmarks 官方 LoCoMo /
  LongMemEval prompt，并固定当前阶段 answerer 为 `gpt-4o-mini`。
- [x] Mem0：smoke profile 已恢复官方 `top_k=200`，成本控制只通过 benchmark 规模裁剪。
- [x] Mem0：LoCoMo 仍按官方 `CHUNK_SIZE=1` 在 adapter 内部逐条调用 `Memory.add()`；
  LongMemEval 仍按官方 `CHUNK_SIZE=2` user+assistant pair 写入。2026-06-19 用户新决策后，
  Mem0 不再暴露 runner turn-level resume，LoCoMo / LongMemEval 均使用
  conversation-level resume。
- [x] 完成 `docs/method-interface-inventory.md` 中四个 method 的完整输入输出清单，
  真实 smoke 前不得再依赖未记录假设。

### Phase H.5：Retrieve-first 协议收尾与架构减重（当前）

- [x] 记录 retrieve-first 主协议设计：
  `docs/superpowers/specs/2026-06-20-retrieve-first-memory-module-design.md`。
- [x] 记录 LLM provider / prompt 配置设计：
  `docs/superpowers/specs/2026-06-21-llm-provider-config-design.md`。
- [x] 记录 registry / capability 减重方向：
  `docs/superpowers/specs/2026-06-21-registry-capability-simplification-design.md`。
- [x] 完成 retrieve-first 实施计划 Task 14：framework answer / retrieval efficiency
  observation 收尾。
- [x] 完成 retrieve-first 实施计划 Task 15：answer-level artifact evaluation 默认忽略
  `answer_prompts.prediction.jsonl`，旧 LongMemEval offline 装配测试已迁移到
  retrieve-first fake provider。
- [x] 执行 retrieve-first 实施计划 Task 16：文档与迁移清理，更新 README、
  method interface inventory、handoff 与 legacy `get_answer()` 兼容说明。
- [ ] 在 retrieve-first 主路径稳定后，逐步弱化 `MethodCapability` 推理，把
  conversation-QA method 兼容性收敛到 `BaseMemoryProvider` 继承关系。
- [ ] 保留 `BaseMemorySystem` 作为后备兼容接口；短期只清理或降级
  `BaseResumableMemorySystem`、`BaseMemoryRetriever`、历史 turn-level resume 文档和
  过重 capability 推理。删除任何旧接口前必须保证四个内置 method、fake/offline 测试和
  artifact-only evaluation 不依赖旧主路径。
- [ ] 减重 evaluator registry：F1 / LLM judge 尽量统一为 metric profile + prompt
  profile，不为每个 benchmark 复制过重 evaluator 类。

### Phase H.6：Method 接入轻量化与失败重试干净状态（主体已实现）

用户已明确要求重新区分“普通用户接入新 method”和“开发者深度接入内置 method”：
普通用户路径只应要求 `BaseMemoryProvider.add(conversation)` 和
`BaseMemoryProvider.retrieve(question)`，不应强制理解 TOML、source identity、
efficiency inventory、official profile 或复杂 registry factory。内置 method 的 TOML、
内部 LLM/embedding 参数、深度 efficiency 插桩和 method state 管理属于框架开发者维护的
白盒深度接入路径。

设计草案：
`docs/superpowers/specs/2026-06-24-method-onboarding-simplification-and-clean-retry-design.md`

- [x] 写入初版 spec，明确用户/开发者角色边界、CLI/TOML 边界、outputs 边界。
- [x] 将 failed conversation retry 脏状态风险纳入同一任务：`--retry-failed` 需要重新
  `add()` 时必须先保证 clean state；不能保证时 fail closed。
- [x] 对齐用户自定义 method 并行策略：默认 `workers=1`；若用户显式传
  `--allow-unsafe-custom-parallel`，允许 `workers>1`，但框架不证明用户后端并发安全。
- [x] 对齐用户自定义 method 第一版加载和构造策略：通过
  `--method-class module:ClassName` 加载，要求无参数构造，不向用户 adapter 传
  `state_dir`、`run_id`、`worker_id`、API key、logger 或 observer；状态、配置和并行
  安全先靠清晰软契约。
- [x] 对齐 resume/retry 状态机：`pending`、`ingesting`、`ingested`、`answering`、
  `completed`、`failed_ingest`、`failed_answer`；`failed_answer` 可只补 pending
  questions，`failed_ingest` 默认跳过，只有 clean retry preflight 通过才可重跑。
- [x] 写实施计划，先用 fake user method 锁定“只实现 add/retrieve 即可跑”的 contract：
  `docs/superpowers/plans/2026-06-24-method-onboarding-clean-retry.md`。
- [x] 提供 `--method-class module:ClassName` 轻量加载路径，避免用户路径暴露内置 method
  深度字段；后续再评估 `--method-file` 单文件快速测试形式。
- [x] 实现 custom method 并行 guard：自定义 method `workers>1` 必须传
  `--allow-unsafe-custom-parallel`。
- [x] 实现 failed ingest retry preflight；无法 clean retry 的 method 在
  `--retry-failed` 时明确报错。
- [x] 新增用户自定义 method loader、custom prediction service path 和端到端 fake smoke
  测试，验证无需内置 registry/TOML 也能写出标准 prediction / answer prompt artifact。
- [x] 写入普通用户接入指南：
  `docs/custom-method-onboarding.md`。
- [x] 为四个内置 method 分别补 clean retry hook 或 attempt namespace 证明：
  A-Mem、LightMem、MemoryOS 已声明 conversation 级 clean hook；Mem0 因共享
  Qdrant/history 状态不声明 hook，继续 fail-closed，避免误删其他 conversation state。
- [ ] 后续评估 `--method-file` 单文件快速测试形式。
- [ ] 后续清理 legacy capability 重逻辑、`BaseResumableMemorySystem` 和
  `BaseMemoryRetriever` 时，同步更新老师汇报材料和对外文档；`BaseMemorySystem`
  暂时保留为后备兼容接口。

### Phase I：Conversation 级并行与 Resume（当前边界）

当前已重新对齐：prediction / full run 层只做 **单个 method × 单个 benchmark 内部的
conversation 级并行**。不继续推进 shared method instance、method execution policy
矩阵、method×benchmark 外层 full parallel orchestrator 等更复杂调度。多个 method 或
多个 benchmark 的并行实验，当前可以由用户开多个终端分别运行；框架不为“少开终端”
牺牲主线可调试性和可维护性。

- [x] 明确当前并行边界：只保留 conversation-level parallel / resume；历史
  `shared_thread`、`isolated_process` policy 设计不作为近期实现目标。
- [x] Mem0 不再保留共享 OSS `Memory` 实例线程并行；统一改为框架 isolated
  conversation 并发和 conversation-level resume。
- [x] 完成 isolated worker 并行原型验收与修复：非共享实例 method 可创建独立 method
  instance；Codex 已补齐 completed conversation checkpoint、pending question 过滤和
  turn checkpoint fail-closed。
- [x] 完成并行 resume 与分批运行控制设计：
  `docs/superpowers/specs/2026-06-19-parallel-resume-run-control-design.md`。
- [x] 完成并行 resume 与分批运行控制实施计划：
  `docs/superpowers/plans/2026-06-19-parallel-resume-run-control.md`。
- [x] 实现 generic work plan，让 normal path 和 isolated worker path 共享同一套
  completed conversation / pending question 判断。
- [x] isolated worker 补齐 conversation-level resume 和 question-level resume；已完成
  离线 focused 验证，真实 API/full 仍需用户确认并从小并发 smoke 开始。
- [x] 修正 isolated worker state root 稳定性：当前 `worker_{idx}` 由剩余 work plan
  动态分块得到，partial question resume 时可能把已完成 ingest 的 conversation 映射到
  不同 worker state 目录；Mem0 切 isolated 前必须固定 conversation 到 state root 的映射。
- [x] 新增 `max_new_conversations` 本次运行预算：每次只推进 N 个未完成 conversation，
  后续允许用同一 `run_id` 和不同预算 resume。
- [x] 统一实验裁剪配置：CLI v2 smoke 支持最多 N 个 conversation 与每 conversation
  最多 N 个 rounds；legacy `--smoke-turn-limit` 仍保留旧 turn 语义。
  `--questions-per-conversation` 和 `--conversation-budget` 是本次命令预算，不进入
  resume identity，允许首次运行和后续 resume 分批推进。formal 不随意截断历史，
  保持 official profile 语义。
- [x] 完成 CLI v2 主体整治：
  - `predict smoke`：小样本连通性测试，使用 `--conversations`、`--rounds`、
    `--questions-per-conversation`、`--workers`，不支持 `--resume` /
    `--retry-failed`。
  - `predict formal`：正式 profile 运行，使用 `--conversation-budget`、
    `--workers`、`--resume`、`--retry-failed`，不允许裁剪历史或问题。
  - 新增 `--allow-api` / `--workers` 直观别名，同时保留旧参数兼容。
  - CLI v2 新 run 写入 `outputs/runs/{method}/{benchmark}/{variant?}/{smoke|formal}/{run_id}/`；
    legacy `predict --profile ...` 仍写入 `outputs/{run_id}/`。
  - `evaluate --run-id` 已兼容新旧布局，同名 run_id 在新旧布局或新布局多处出现时会报
    ambiguity。
  Focused 验证：`tests/test_main_cli.py tests/test_prediction_cli.py` 为 `64 passed`；
  `compileall` 通过。
- [ ] 分阶段清理 legacy CLI：当前不要删除 `predict --profile ...` 和旧参数。先完成四个
  method 的 LoCoMo/LongMemEval v2 smoke 稳定验证，再加 deprecated warning；至少完成一次
  v2 formal 小规模 run 后，再从 README 示例中移除旧写法；对外发布前再决定是否彻底删除旧参数。
- [x] 修复 isolated worker 失败可诊断性：记录完整异常 traceback，并能写入具体
  conversation failed checkpoint。该条早期 fail-fast 语义已被下方“局部失败 continue”
  语义替代。
- [x] 将 isolated worker 失败语义升级为 conversation 局部失败 continue：单个
  conversation 失败后标记 failed、记录 traceback，当前 worker 继续后续 conversation，
  其他 worker 不受影响；只有配置、manifest、依赖、source identity 等全局错误才
  fail-fast。
- [x] 增加 API/network retry 与 timeout 兜底，优先覆盖 Mem0 embedding API SSL 断连
  事故路径；Mem0 vendored LLM/embedding OpenAI clients 已通过 `with_options()` 注入
  `api_timeout_seconds=60.0` 和 `api_max_retries=8`。OpenCode 后续已为 A-Mem 和
  LightMem 补齐同类配置与 client 注入；MemoryOS 已有 timeout/retry 配置。四个当前
  OpenAI-compatible method 的基础 timeout/retry 兜底已覆盖，真实断网/限流韧性测试后续再做。
- [x] 增加连续失败熔断，例如 `max_consecutive_failures`，避免全局网络或配置问题导致
  多 worker 批量空烧 API。
- [x] 补齐 `--retry-failed` 同 run 内最多尝试一次的测试：retry-failed 只影响 eligible
  selection，不允许失败 conversation 在同一次 run 内被其他 worker 接手重试。
- [x] 避免 isolated-only method 的根实例副作用：registered runner 在 isolated path
  传 `_UnusedRootSystem` 占位，第三方 method 只在 `worker_*` 内构造，避免额外创建
  顶层 `method_state/qdrant` 或 `history.db`。
- [ ] 后续如需更高并发，只在 conversation-level worker 内优化隔离和资源控制，不重新引入
  method×benchmark full orchestrator 或 shared method instance policy。
- [ ] 证明不同 conversation 状态、日志、checkpoint 和 artifact 不串写。
- [ ] 从 `max_workers=2` 开始做小量 API 并发 smoke，再决定 official 默认值。
- [x] method×benchmark 外层并行降级为低优先级便利能力：`calibrate-smoke` 可继续服务极小
  成本校准和批量 smoke，但不作为 full 实验调度主线；常规实验可用多个终端分别运行。
- [x] 修正 Mem0 并发与 resume 策略：不再使用共享 OSS `Memory` 实例并发，不再保留
  LoCoMo turn-level resume；统一改为框架 isolated conversation 并发和 conversation-level
  resume。
- [x] 历史 resume 分层策略已实现过：Mem0 LoCoMo turn-level、Mem0 LongMemEval
  conversation-level；MemoryOS/A-Mem/LightMem conversation-level。该策略已被 2026-06-19
  用户新决策 supersede，保留此条仅作历史说明。
- [x] A-Mem wrapper 层状态持久化已完成，可支撑 conversation-level resume；仍不做
  turn-level resume。
- [x] LightMem completed conversation backend 恢复已接入；写入完成但问题未答完时，
  resume 可重建 backend 并继续 question-level resume。

说明：Phase J 已实现一个只用于成本校准的极小 smoke 外层 orchestrator。它不是 full
parallel 调度主线；当前不继续扩展 method×benchmark full parallel。若未来真实用户明确需要
统一排队、统一展示或排行榜批处理，再重新设计。

MemoryOS PyPI backend 已降为低优先级，本阶段不实现。

### Phase J：实验与指标

- [ ] 重新完成 Mem0、MemoryOS、A-Mem、LightMem 的论文 Table 级资源与参数审计：
  `docs/method-resource-parameter-audit.md`。
- [x] 确认 smoke 也采用官方 method 参数，成本控制只通过 benchmark 数据规模裁剪。
- [x] 补齐 LightMem 本地模型：
  `models/all-MiniLM-L6-v2` 和
  `models/llmlingua-2-bert-base-multilingual-cased-meetingbank`。
- [x] 实现成本校准 smoke 外层 orchestrator：
  `memory-benchmark calibrate-smoke`。该入口固定 smoke profile、每组合 1 个
  conversation/instance、强制开启 efficiency observation，并通过 `max_parallel_runs`
  限制多个独立 run 的并发。
- [x] 修复 LoCoMo calibrate-smoke 首次运行失败的基础问题：默认不强制 resume；
  CLI 新增显式 `--resume`；manifest secret 检测不再误伤 `llm_tokenizer`，但继续
  拒绝真实 token 字段。
- [x] 确认 Mem0/MemoryOS/A-Mem/LightMem 功能上均已跑通 LoCoMo 极小 smoke；LightMem
  最终成功记录在单独 run `outputs/locomo-lightmem-smoke-obs/`。
- [x] LongMemEval smoke 已改为 instance 内按完整双 turn round 裁剪，避免单个
  instance 仍包含数百条 message。
- [x] LightMem vendored import 已加锁，并在当前进程保留 LightMem `src` 路径，
  避免并发 smoke 时反复插拔 `sys.path`。
- [x] A-Mem / LightMem 补齐 wrapper 层可见 LLM token observation：A-Mem 记录
  query-generation 与 answer LLM；LightMem 记录 answer LLM。当前优先读取真实
  response usage，缺失时回退 `tokenizer_estimate`，不冒充 API usage。
- [x] A-Mem 内部 memory build LLM 调用提升到 `api_usage` 级：
  A-Mem 已在 official runtime 的 `llm_controller.llm.get_completion()` 外围加透明
  observer，并通过 fake/offline focused 验证。
- [x] LightMem memory-build LLM observer 已完成 adapter 级修复并真实复验：真实旧 run
  `lightmem-api-smoke-v2` 只记录了 answer LLM usage，根因是 OP-update 内部
  `ThreadPoolExecutor.map()` 不传播 ContextVar scope；当前已用子线程 usage buffer
  + `add()` 内 flush 方式修复，并通过 fake 线程池 OP-update 离线测试。OpenCode
  后续运行 `lightmem-smoke-4c20t-w4-20260620`，确认 stage=`memory_build`、
  model_id=`lightmem-memory-llm` 的 `llm_call(api_usage)` 已出现。旧 run 仍不能作为
  完整 build LLM 成本依据。
- [x] `calibrate-smoke` 在线程池启动前串行预加载 transformers / sentence-transformers
  相关依赖，规避 LightMem 与其他 method 并行启动时的 lazy import 竞态。
- [x] OpenCode 已新增 `CalibrationProgressMonitor`，并在并行 calibrate-smoke 下禁用
  child run Rich progress、由外层读取 `checkpoints/progress.json` 渲染统一表格；
  Codex 已修正其新增测试的 Rich 宽度问题并验证离线测试通过。
- [x] Codex 已同步审查 `opencode/opencode_result-6.19.md`，恢复
  `opencode/opencode_result.md` 稳定索引，并修复 calibrate-smoke monitor 对
  LongMemEval concrete variant child run 的 progress 路径解析；离线验证
  `tests/test_calibration_progress_monitor.py tests/test_cost_calibration_smoke.py`
  为 `24 passed`。
- [x] 建立当前任务与文档状态总账 `docs/task-ledger.md`，把
  `opencode_result-6.18.md`、`opencode_result-6.19.md` 和近期 handoff 中的 open /
  closed / superseded 状态收敛到一个入口，避免旧文档中的已修问题被重复执行。
- [x] 四 method 并行 LoCoMo 极小 smoke 已跑通：
  `locomo-smoke-20260618-token-rich-v1-{mem0,memoryos,amem,lightmem}-locomo`
  均为 1 conversation / 1 question completed，并全部写出 prediction efficiency
  observation。
- [x] 四 method LoCoMo 4 conversations / 20 turns / 4 workers 真实 smoke 已跑通：
  `mem0-smoke-4c20t-w4-20260620`、`memoryos-smoke-4c20t-w4-20260620`、
  `amem-smoke-4c20t-w4-20260620`、`lightmem-smoke-4c20t-w4-20260620` 均为
  4/4 conversations、4/4 questions completed。该轮验证关闭了 Mem0 isolated
  conversation observation、LightMem OP-update memory-build LLM observation 和四 method
  efficiency 覆盖矩阵。
- [x] 用户已确认不做统一 OpenAI-compatible API gateway；当前只要求每个 method 记录
  可审计 token 消耗量，后续通过离线聚合汇总。
- [x] 新增 prediction 阶段人类可读 efficiency summary artifacts：
  `summaries/efficiency_overall.prediction.json`、
  `summaries/efficiency_by_conversation.prediction.json`、
  `summaries/efficiency_by_question.prediction.json`。raw observation JSONL 仍是事实来源，
  summary 仅作离线聚合视图，便于估算单个 conversation / question 的 token、调用和延迟。
- [x] 新增失败 conversation 默认隔离：`conversation_status.json` 中标记为 `failed`
  的 conversation 在默认 resume 中不再重跑；只有显式 `--retry-failed` 才重新纳入
  work plan。isolated worker 失败现在会写入具体 conversation 的 failed checkpoint。
- [x] OpenCode 已补齐 A-Mem / LightMem / MemoryOS `allow_smoke_worker_override=True`，
  让四个 method 的 smoke worker override 行为一致。
- [x] OpenCode 已修复 isolated worker `add()` 缺少 conversation efficiency scope 的问题；
  Codex 进一步修复 scope 退出前读取 `conv_scope.records` 导致 conversation observation
  未随 worker bundle 返回的问题，并新增 isolated worker conversation observation 测试。
- [x] 修复 LoCoMo smoke 下 `--question-limit-per-conversation > 1` 实际不生效的问题；
  当前 LoCoMo smoke adapter 会保留所有 evidence 完整落在截断历史里的问题，再由
  runner 按 question budget 裁剪。
- [x] 为 Mem0 embedding API 调用增加 retry/timeout 兜底；v3 official-full 失败根因是
  OpenAI-compatible embedding API SSL 断连。当前已在 Mem0 vendored LLM/embedding
  clients 注入 timeout/max_retries，并通过 `mem0-smoke-4c20t-w4-20260620` 极小真实
  API smoke 未复现断连。official-full 仍需新 run_id 重跑后才能关闭。
- [x] LongMemEval-S 极小成本校准 smoke 已由用户真实运行 Mem0/A-Mem/LightMem 三路并行；
  三个 child run 的 `progress.json` 和 `summary.json` 均显示 completed。终端最后仍显示
  pending 的根因是 monitor 使用 base run id 读取 progress，而 LongMemEval 实际写入
  `*-longmemeval-s-cleaned` child 目录；Codex 已用离线红绿测试修复 variant fallback。
- [ ] 自测并修复 Rich 终端输出的剩余显示问题：第三方 warning/tqdm 仍会插入 Rich 区域；
  isolated prediction 进度长时间不动仍是架构问题，不能宣布终端体验完成。
- [ ] 建立框架级 stdout 约束：第三方 method 的 `print()` / warning / tqdm 不能破坏
  Rich 进度区；但也不能全局压掉用户 method 的调试输出。目标是可靠写入
  `logs/run.log`/events，并提供是否在终端显示的开关。
- [x] 初版 prediction artifact 瘦身已由 OpenCode 实现并经 Codex focused 验证：
  conversation 级 `system_prompt` 抽取到 `artifacts/conversation_prompts.jsonl`，
  `method_predictions.jsonl` 中移除重复字段；MemoryOS adapter 不再写入 question 级
  `user_prompt`。
- [x] 初版 evaluator category 聚合已由 OpenCode 实现并经 Codex focused 验证：
  `run_artifact_evaluation()` 对所有带 `category` 的 answer-level metric 写入
  `category_breakdown`。
- [ ] 补充/审查 prediction artifact 瘦身的长期兼容策略：旧 artifact 回读、未来更多
  conversation-level metadata key、evaluator 是否需要引用 `conversation_prompts.jsonl`。
- [x] 修复普通 full/predict 的 efficiency observation 易漏开问题：`predict` / `run`
  现在默认开启 prediction token/latency observation；如需调试关闭，必须显式传
  `--disable-efficiency-observability`。
- [x] A-Mem LoCoMo full-v2 已完成 prediction、F1 和 judge；旧
  `amem-locomo-0619-1303` 因 session time 缺失导致 temporal 结果无效，不再作为整体指标。
  注意：A-Mem full-v2 历史 artifact 没有 efficiency observation，不能作为成本依据；
  当前 A-Mem observation 链路以 `outputs/amem-smoke-4c20t-w4-20260620/` 为证据。
- [x] Mem0-LoCoMo `official-full` prediction 已以 `outputs/mem0-locomo-full-v4/` 跑完：
  10 conversations、1540 questions completed，并生成 F1、Judge 和 efficiency summary。
  OpenCode 发现全局 `reference_date` 只传年份；Codex 已在 2026-06-23 修复后续 run 的
  完整日期传递。full-v4 不自动作废；若最终报告要求最严谨 Mem0 LoCoMo prompt 复现，
  应使用新 run_id 重跑 Mem0 LoCoMo。
- [x] 四个 method 在 LoCoMo 上的 retrieve-first 极小 smoke 已由用户真实运行：
  `retrieve-first-locomo-{mem0,memoryos,amem,lightmem}-smoke-2c20t-20260622` 均完成
  2 conversations / 2 questions，并写出 prediction 与 efficiency observation；但复核发现
  这些 run 进入 isolated worker legacy `get_answer()` path，缺
  `answer_prompts.prediction.jsonl`，不能作为严格 retrieve-first 链路证据。Codex 已修复
  isolated retrieve-first path；用户随后用
  `retrieve-first-strict-locomo-{mem0,memoryos,amem,lightmem}-smoke-2c20t-w2-20260622`
  严格重跑并确认四个 run 均有 `answer_prompts.prediction.jsonl` 和非空
  `prompt_messages`。
- [x] 讨论并确认 LongMemEval-S 最小 smoke 方案的核心适配口径：LongMemEval 的
  `question_time` 必须进入 answer prompt；A-Mem / MemoryOS 可在 retrieve-first 下纳入，
  但必须保留各自 method-specific 检索上下文。A-Mem / MemoryOS 现复用
  LightMem-style LongMemEval reader prompt，并分别保留 A-Mem memory context、query
  keywords、category k，以及 MemoryOS recent context、retrieval queue、user profile、
  long-term knowledge 和 assistant knowledge。MemoryOS 新增可选
  `memoryos_pypi_generic_v1` profile，用于复用 MemoryOS PyPI generic prompt 结构；
  默认仍保持 LightMem-style LongMemEval QA prompt。A-Mem 本地仓库未发现同等级 generic
  answer-reader prompt，当前不新增 generic profile。LongMemEval judge 默认走 LightMem
  LongMemEval 流程：task-specific yes/no prompt、Chat Completions、
  `temperature=0.0`、`top_p=0.8`、`max_tokens=2000`。
- [x] LongMemEval-S `s_cleaned` 四 method official-full 1-conv cost pilot 已完成：
  `outputs/{lightmem,mem0,memoryos,amem}-longmemeval-s-1conv-costpilot-20260622-s-cleaned`
  均为 1/500 conversations、1/500 questions completed，并均通过
  `longmemeval_judge_accuracy` 1/1。OpenCode 给出的美元估算是 OpenAI 官方价参考；
  真实费用需要基于这些 run 的 token/latency observation 按 ohmygpt 价格离线换算。
- [ ] 复用 prediction artifact 计算 LoCoMo F1。
- [x] LoCoMo LLM judge prompt 已由用户/OpenCode 对齐为 LightMem 官方风格，compact
  模式解析 CORRECT/WRONG；evaluator runner 已支持 `--max-eval-workers` 并行 judge，
  LightMem/MemoryOS LoCoMo judge 已真实并行运行。
- [ ] 完成 Mem0/MemoryOS/A-Mem/LightMem × LoCoMo/LongMemEval 的可选实验矩阵；
  retrieve-first 后不再因为缺 method-specific answer prompt 直接排除某 method，但仍需
  审计扩大规模后的稳定性、失败恢复和成本波动。
- [ ] 基于 Phase G 保存的原始 observation 离线计算真实服务商费用；LongMemEval-S
  1-conv cost pilot 已有四 method 原始依据。

### Phase K：Retrieve-First Memory Module 协议重构（当前设计）

设计方案：
`docs/superpowers/specs/2026-06-20-retrieve-first-memory-module-design.md`

实施计划：
`docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`

2026-06-22 最新修订：用户已确认主协议继续叫 retrieve-first，但 `retrieve()` 的核心输出
已从单字符串 `AnswerPromptResult.answer_prompt` 继续升级为
`AnswerPromptResult.prompt_messages`。
method 负责构造完整 answer prompt messages，framework answer LLM 直接使用这些 role
messages；`answer_prompt` 只作为兼容 artifact、日志和 token 估算文本视图；调试信息、
拆出的 `answer_context`、原始检索结果和 prompt profile 放进 `metadata`。

当前已完成核心协议、framework reader、registered runner 接线和四个内置 method adapter
的 `AnswerPromptResult` 主体迁移。核心方向：

```text
add(conversation)
retrieve(question) -> AnswerPromptResult.prompt_messages
framework answer LLM(prompt_messages) -> answer
evaluate
```

- [x] 复核四个现有 method 的 `get_answer()` 实现，确认 Mem0、A-Mem、LightMem、
  MemoryOS 都可拆成写入、检索、prompt 构造和最终 answer LLM 调用。
- [x] 与用户确认 `retrieve()` 输出以完整 `AnswerPromptResult.prompt_messages` 为核心；
  answer prompt messages 设计视为 method 的一部分。
- [x] 与用户确认新基础 `add()` 接收单个 `Conversation`，runner 负责循环、并行和
  resume；method 原生 batch ingest 作为未来可选优化。
- [x] 与用户确认主线只保留 memory-module evaluation，不再要求新 method 实现
  `get_answer()`。
- [x] 与用户确认内置 method 可以在 future 修改第三方 provider/client 适配层以支持更多
  internal LLM provider，但 Phase 1 仍统一默认 `gpt-4o-mini`。
- [x] 写出正式设计 spec。
- [x] 用户审阅 spec。
- [x] 写实施计划。
- [x] 写出 LLM Provider 与 Prompt 配置设计 spec，明确第一版只实现
  OpenAI-compatible provider；Anthropic/Gemini、本地进程内 Hugging Face provider 作为
  future provider；本地开源模型优先通过 OpenAI-compatible local server 接入。
- [x] 新增 `AnswerPromptResult` protocol entity/interface。
- [x] 新增 framework answer reader，并校验 answer prompt 非空、question/conversation id
  严格对齐。
- [x] 修改 prediction runner：支持 fake `BaseMemoryProvider` 的
  retrieve -> framework answer LLM -> prediction 基础路径，并写出
  `answer_prompts.prediction.jsonl`。
- [x] 支持 answer prompt completed / answer pending 的 resume。
- [x] 新增 answer prompt artifact path，避免 `method_predictions.jsonl` 重复写入大段 prompt。
- [x] 新增 OpenAI-compatible framework answer client；当前 prompt 来自 method 返回的完整
  `answer_prompt`。
- [x] 在 registered prediction service 中实际构造 `FrameworkAnswerReader` 并传给
  retrieve-first runner；当前只在 method 声明 `MEMORY_RETRIEVAL` capability 时启用，
  legacy `ANSWER_GENERATION` 路径继续保持旧行为。
- [x] registry capability 已切到 retrieve-first：LoCoMo / LongMemEval conversation-QA
  prediction 现在要求 `CONVERSATION_ADD + MEMORY_RETRIEVAL`；Mem0、A-Mem、LightMem、
  MemoryOS 均声明 `MEMORY_RETRIEVAL`，不再声明 `ANSWER_GENERATION`。
- [x] 共享 mock/fake 测试层已迁移：新增 `MockMemoryProvider`，runner 测试可通过
  `retrieve()` + `FrameworkAnswerReader` 生成 prediction；legacy `MockMemorySystem`
  保留给旧 conversation runner 测试。
- [x] Mem0 adapter 已迁移到 `retrieve(question) -> AnswerPromptResult`：保留 Mem0 search
  和官方 LoCoMo / LongMemEval prompt 构造，旧 `get_answer()` 暂时作为兼容 wrapper。
- [x] A-Mem adapter 已迁移到 `retrieve(question) -> AnswerPromptResult`：保留官方 query
  keyword generation、Table 8 category k、adversarial public-input 拒绝、retrieval
  efficiency observation 和 answer prompt 构造；LongMemEval 分支复用 LightMem-style
  reader prompt，并保留 A-Mem 检索出的完整 memory context；旧 `get_answer()` 暂时作为
  兼容 wrapper。
- [x] LightMem adapter 已迁移到 `retrieve(question) -> AnswerPromptResult`：LoCoMo 继续走
  `search_locomo.py` 风格 Qdrant payload/vector combined 检索，LongMemEval 继续走
  `LightMemory.retrieve()` online 路径，并由 adapter 构造完整 answer prompt；旧
  `get_answer()` 暂时作为兼容 wrapper。
- [x] MemoryOS adapter 已迁移到 `retrieve(question) -> AnswerPromptResult`：调用官方 eval
  `retrieval_system.retrieve(...)`；LoCoMo 按官方 eval prompt 结构构造完整 answer
  prompt，LongMemEval 分支复用 LightMem-style reader prompt，并保留 recent context、
  retrieval queue、user profile、long-term knowledge 和 assistant knowledge；旧
  `get_answer()` 保持原行为，避免破坏 system prompt observer 和历史复查路径。
- [x] Mem0/A-Mem/LightMem/MemoryOS 已继承 `BaseMemoryProvider`，并让 `add()` 在迁移期同时兼容单个
  `Conversation` 和旧 list 输入；普通 runner 可进入 retrieve-first 分支。
- [x] answer-level artifact evaluation 兼容 answer prompt artifact：`run_artifact_evaluation()`
  默认仍只读取 `public_questions.jsonl`、`method_predictions.jsonl` 和
  `evaluator_private_labels.jsonl`；`answer_prompts.prediction.jsonl` 可并存但不会影响
  F1/Judge，除非未来 evaluator 显式声明需要 prompt/context。
- [ ] 后续把当前 `OpenAISettings` 小步实现迁移到统一 `LLMRuntimeConfig` /
  `LLMResponse`。
- [x] 更新 CLI/config/manifest/source identity/observability 主体链路；旧 `get_answer()`
  删除和统一 `LLMRuntimeConfig` 仍为后续任务。
- [x] 完成四个内置 method adapter 的 fake/offline contract 和 focused 回归：四 adapter
  `189 passed, 2 warnings, 2 subtests passed`；runner/registered/evaluation focused
  `146 passed`。
- [x] 完成 AnswerPromptResult 当前状态文档收尾。
- [x] 正式 full 前新增 `AnswerLLMSettings` 或等价配置，把 framework answer LLM 的
  `temperature`、`max_tokens`、`top_p`、timeout、retry 显式写入配置、manifest 和
  model inventory。已按 method × benchmark 解析官方默认参数；当前审计见
  `docs/method-resource-parameter-audit.md`。
- [x] 将 `AnswerPromptResult` 从单字符串 `answer_prompt` 升级为 message role 结构：
  主字段命名为 `prompt_messages`，元素为 `PromptMessage(role, content)`；`answer_prompt`
  仅保留为兼容和 artifact 文本视图。四个内置 method 已返回各自官方 answer LLM 的
  system/user message 结构，runner artifact/resume 已保留 `prompt_messages`。
- [x] 已执行一轮 LoCoMo 2c20t 真实 smoke，但发现 isolated worker 未走 retrieve-first。
  修复已完成；下一步在用户确认 API 预算、规模、新 run_id 和 worker 后重跑严格
  retrieve-first 真实极小 smoke，并检查 `answer_prompts.prediction.jsonl` 的
  `prompt_messages`。严格重跑已完成，见
  `docs/handoffs/2026-06-22-strict-retrieve-first-locomo-smoke-success.md`。

### 当前任务队列（2026-06-23）

本节是从 `docs/task-ledger.md` 抽出的执行队列；若与旧 handoff 冲突，以
`docs/task-ledger.md` 和当前代码为准。

- [x] 复核 OpenCode 6.22 改动：by-question efficiency 聚合、`--max-new-conversations`
  progress/logger、partial prediction artifact evaluation 已通过 Codex focused 验证。
- [x] 修复 Mem0 LoCoMo 全局 `reference_date` 完整日期传递：后续 run 会把公开 history
  中最后一个 session time 写入官方 answer prompt；旧 `mem0-locomo-full-v4` 不自动作废。
- [ ] 基于 LongMemEval-S 1-conv cost pilot 的真实 observation，按 ohmygpt 实际价格整理
  经费/时间估算报告；不要直接使用 OpenAI 官方美元估算作为最终结论。
- [ ] 对当前脏 worktree 做功能边界整理，确认没有 `data/`、`models/`、`outputs/` 入库后
  小步 commit/push。
- [ ] 根据预算决定 LongMemEval-S 扩大规模：建议先 5 或 10 conversations / method，
  保持同一 run_id 可 resume，再决定是否 full 500。
- [ ] 汇总 LoCoMo 已完成 run 的 F1、LLM judge 和 efficiency 表，区分历史 run 与当前
  retrieve-first/AnswerPromptResult 后续 run。
- [ ] 补充用户可读的 smoke/full 参数语义说明：`smoke-conversation-limit`、
  `smoke-turn-limit`、`question-limit-per-conversation`、`max-new-conversations`
  都是上限预算；过小历史导致无完整 evidence 时必须 fail closed。
- [ ] 治理 isolated worker 长时间无中间进度、第三方 warning/tqdm 插入 Rich 终端的问题；
  当前不影响 artifact 正确性。
- [ ] 做 registry/capability 减重实施：保留轻量 registry，逐步删除或降级旧
  `BaseResumableMemorySystem` / `BaseMemoryRetriever` 迁移负担；`BaseMemorySystem`
  暂时保留为后备兼容接口。
- [ ] 将当前 `OpenAISettings` 小步实现迁移到统一 `LLMRuntimeConfig` / `LLMResponse`；
  第一版仍只实现 OpenAI-compatible provider。
- [ ] 定期审计 handoff/spec/plan 状态，把已关闭、已覆盖、仍 active 的文档状态同步到
  `docs/task-ledger.md`。

### Phase L：后续扩展

- [ ] 接入 HaluMem QA-only 的 Medium/Long variants。
- [ ] 评估 MemBench 和 Mem-Gallery 可自然适配的 conversation-QA 切片。
- [ ] tests 按 unit/integration/api/contract 分组。
- [ ] 记录并调研实验监控 AI：读取 progress/events/summary，用自然语言或手机端 IM
  查询实验状态，详见 `docs/future-ideas.md`。
- [ ] 项目成熟后重做新 method 接入 skill，详见 `docs/future-ideas.md`。
- [ ] 项目成熟后再考虑 PyPI 发布、benchmark 自动下载、自定义 method CLI 插件和排行榜。

## 当前约束

- 不启动全量付费 API 实验；小量 smoke 仍需明确控制样本和请求规模。
- smoke profile 必须使用官方 method 参数；不得为了省钱降低 `top_k`、`retrieve_k`
  或 `retrieve_limit`。成本控制只通过 conversation/question/turn 规模裁剪。
- 禁止修改 `third_party/` 内第三方核心算法；允许经过记录、可关闭且通过行为等价验证的
  纯观测插桩。
- 不创建 method × benchmark 专用 runner。
- 不合并不同 dataset variant 的 run。
- `outputs/memoryos-locomo-full-20260603/` 是受保护实验资产。
- 每完成一个任务立即更新本文件、`AGENTS.md` 和最新 handoff。

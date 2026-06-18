# 当前动态路线图

更新日期：2026-06-17

本文件只记录当前主线、完成状态和阶段依赖。每完成一个任务必须立即勾选并同步
`AGENTS.md`；详细实现步骤放在对应 `docs/superpowers/plans/` 文件中。

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
- [ ] A-Mem：category 5 adversarial 当前因 gold answer 冲突显式拒绝，不进入普通
  public-input smoke；如需测 adversarial，必须另行对齐私有 gold 边界。
- [ ] LightMem：补齐 Table 2 / Table 3 profile。
  - [x] 用户指定并落实 `(r=0.7, th=512)` official-mini profile。
  - [x] 对齐 LoCoMo / LongMemEval 增量写入粒度。
  - [x] 对齐 LongMemEval `question_time` reader prompt 和 LightMem LoCoMo prompt 布局。
  - [x] LoCoMo 已专门化为 LightMem `search_locomo.py` 风格的 Qdrant payload/vector combined 检索。
  - [x] LoCoMo `add()` 完成后已接入 `construct_update_queue_all_entries()` 和
    `offline_update_all_entries(score_threshold=0.9)`。
  - [ ] LongMemEval OP-update 仍是可选 future profile；当前 LongMemEval 保持通用
    `LightMemory.retrieve()` online 路径。
- [ ] Mem0：将 `get_answer()` reader 改为 Mem0 memory-benchmarks 官方 LoCoMo /
  LongMemEval prompt，并固定当前阶段 answerer 为 `gpt-4o-mini`。
- [x] 完成 `docs/method-interface-inventory.md` 中四个 method 的完整输入输出清单，
  真实 smoke 前不得再依赖未记录假设。

### Phase I：通用并行调度（顺延）

- [ ] 明确 method execution policy：`serial`、`shared_thread`、`isolated_process`。
- [ ] 保留 Mem0 的共享实例线程并行。
- [ ] 为 MemoryOS `paper_eval` backend 实现独立 runtime 的进程隔离并行。
- [ ] 证明不同 conversation 状态、日志、checkpoint 和 artifact 不串写。
- [ ] 从 `max_workers=2` 开始做小量 API 并发 smoke，再决定 official 默认值。
- [ ] 增加实验级 orchestrator，并通过 `max_parallel_runs` 控制多个独立 run。
- [ ] 限制“实验并发 × conversation 并发”的总请求规模。

说明：Phase J 已实现一个只用于成本校准的极小 smoke 外层 orchestrator。它不是
Phase I 的 full parallel 调度替代品；full parallel 仍需处理更大规模、多 profile、
method execution policy 和进程隔离策略。

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
- [ ] 经用户确认 run_prefix、并发数和 API 预算后运行
  Mem0/A-Mem/MemoryOS/LightMem × LoCoMo/LongMemEval-S 极小成本校准 smoke。
- [ ] API 充值并经用户确认后运行 Mem0/A-Mem/MemoryOS/LightMem + LoCoMo 极小 smoke。
- [ ] API 充值并经用户确认后运行 Mem0-LoCoMo `official-full` prediction。
- [ ] API 条件允许并经用户确认后运行 LongMemEval-S 最小 smoke。
- [ ] 复用 prediction artifact 计算 LoCoMo F1。
- [ ] 需要时单独运行 LoCoMo LLM judge。
- [ ] 完成 Mem0/MemoryOS/A-Mem/LightMem × LoCoMo/LongMemEval 的可选实验矩阵。
- [ ] 基于 Phase G 保存的原始 observation 离线计算真实服务商费用。

### Phase K：后续扩展

- [ ] 接入 HaluMem QA-only 的 Medium/Long variants。
- [ ] 评估 MemBench 和 Mem-Gallery 可自然适配的 conversation-QA 切片。
- [ ] tests 按 unit/integration/api/contract 分组。
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

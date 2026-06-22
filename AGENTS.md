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
- 当前主线已完成 retrieve-first memory-module 架构迁移主体：method 主协议已从
  `add + get_answer` 收敛为 `add(conversation) + retrieve(question)`，framework reader
  统一负责 prompt、answer LLM 和最终回答。设计已写入
  `docs/superpowers/specs/2026-06-20-retrieve-first-memory-module-design.md`；实施计划已写入
  `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`，Task 1-16 已完成。
  旧 `get_answer()` / `BaseMemorySystem` 仍作为迁移期兼容保留；真实 retrieve-first API
  smoke 仍需用户确认规模和 run_id 后再执行。
- Registry / capability 减重方向已记录在
  `docs/superpowers/specs/2026-06-21-registry-capability-simplification-design.md`。
  当前结论：保留轻量 registry 作为 CLI 名称到 factory/config/source identity 的集中映射，
  不回退到分散 `if/else`；但 capability 枚举和旧 `BaseMemorySystem` /
  `BaseResumableMemorySystem` / `BaseMemoryRetriever` 属于迁移期负担，retrieve-first
  全链路稳定后应逐步删除或降级，新 method 接入文档只面向 `BaseMemoryProvider`。
- LLM/provider 灵活配置方向已对齐并写入
  `docs/superpowers/specs/2026-06-21-llm-provider-config-design.md`。当前结论：第一版只实现
  OpenAI-compatible provider；Anthropic/Gemini、本地进程内 Hugging Face provider 作为
  future provider；本地开源模型优先通过 vLLM/Ollama/LM Studio 等 OpenAI-compatible
  server 接入。该设计尚未实现，不能把多 provider 视作当前运行能力。
- 当前阶段所有真实 LLM 调用统一使用 `gpt-4o-mini`；不要临时切换 `gpt-4o`、
  GPT-5 或其他模型，除非用户后续明确改口。

## 当前断点

- 2026-06-22 最新 LongMemEval 适配进展：
  `docs/superpowers/specs/2026-06-22-amem-memoryos-longmemeval-design.md` 和
  `docs/superpowers/plans/2026-06-22-amem-memoryos-longmemeval.md`；交接为
  `docs/handoffs/2026-06-22-amem-memoryos-longmemeval-adapter.md`。A-Mem / MemoryOS
  已完成 LongMemEval retrieve-first 代码主体适配：二者都复用 LightMem-style
  LongMemEval reader prompt（`system: You are a helpful assistant.` +
  `Question time:<date> and question:<question>`），但必须保留各自 method-specific
  记忆上下文。A-Mem 保留官方 query keyword generation、category k、memory
  context 和 metadata；MemoryOS 保留 recent context、retrieval queue、user profile、
  long-term knowledge 和 assistant knowledge。A-Mem / MemoryOS LongMemEval answer LLM
  参数已设为 `temperature=0.0, top_p=0.8, max_tokens=2000`。LongMemEval judge prompt
  已迁移为官方 `evaluate_qa.py` task-specific 规则，并保持本项目 compact/detailed
  parser 兼容。已验证 focused 回归
  `tests/test_amem_adapter.py tests/test_memoryos_adapter.py tests/test_config_profiles.py tests/test_llm_judge_parsing.py`
  为 `176 passed, 1 warning, 2 subtests passed`；尚未执行真实 LongMemEval-S API smoke。
- 2026-06-22 最新 smoke 结论：
  `docs/handoffs/2026-06-22-strict-retrieve-first-locomo-smoke-success.md`。
  用户已用新 run id 严格重跑 LoCoMo retrieve-first 极小真实 smoke：
  `retrieve-first-strict-locomo-{mem0,memoryos,amem,lightmem}-smoke-2c20t-w2-20260622`。
  四个 run 均完成 2 conversations / 2 questions，并均存在
  `artifacts/answer_prompts.prediction.jsonl`、`method_predictions.jsonl`、
  `efficiency_observations.prediction.jsonl` 和 `efficiency_overall.prediction.json`。
  每个 `answer_prompts.prediction.jsonl` 均为 2 行且含非空 `prompt_messages`：A-Mem
  为 system+user，LightMem 为 system，Mem0 为 user，MemoryOS 为 system+user。结构化
  event 均无 failed/error/exception，`run.log` 无 ERROR/WARNING/Traceback/SSL/timeout。
  严格 retrieve-first LoCoMo 极小真实 smoke 已通过。下一步优先讨论并执行
  LongMemEval-S 最小 retrieve-first smoke，或对这四个 smoke 做 artifact-only F1。
- 2026-06-22 最新交接：
  `docs/handoffs/2026-06-22-retrieve-first-locomo-smoke-and-isolated-fix.md`。
  用户已运行四个 LoCoMo retrieve-first 极小真实 smoke：
  `retrieve-first-locomo-{mem0,memoryos,amem,lightmem}-smoke-2c20t-20260622`。
  四个 run 均完成 2 conversations / 2 questions，且写出了 prediction 与 efficiency
  observation；日志无结构化失败事件。但复核发现这些 run 没有
  `artifacts/answer_prompts.prediction.jsonl`，根因是 isolated worker 路径仍调用 legacy
  `get_answer()`，没有进入 `BaseMemoryProvider.retrieve() -> FrameworkAnswerReader`。
  本轮已修复 isolated retrieve-first 路径、answer prompt artifact 合并和 provider
  conversation 级 add 兼容，并新增红绿测试。验证：isolated prompt artifact 单测
  `1 passed`；runner/reader/efficiency focused `80 passed`；四 adapter / registry /
  calibrate-smoke focused `241 passed, 2 warnings, 2 subtests passed`。因此，上述四个
  真实 run 只能作为“小规模真实 API legacy isolated path 可完成 + observation 可写出”的
  证据；严格 retrieve-first smoke 需要用新 run_id 重跑，并确认
  `answer_prompts.prediction.jsonl` 存在且含 `prompt_messages`。该待办已由上方严格
  smoke 交接关闭。
- 2026-06-22 最新 P0 已完成主体：`AnswerPromptResult` 已升级为 message role 结构。
  主类型为 `PromptMessage(role, content)`，主字段为
  `AnswerPromptResult.prompt_messages`，语义是“交给 answer LLM 的完整 prompt
  messages”。`answer_prompt` 仅作为兼容 artifact、日志和 token 估算文本视图保留。
  framework answer reader 会直接把 `prompt_messages` 发给 OpenAI-compatible chat
  completions。四个内置 method adapter 已按官方调用形态返回 role 结构：Mem0
  官方 LoCoMo/LongMemEval 为 user-only，通用 fallback 为 system+user；A-Mem 为
  system+user；LightMem LoCoMo 为 system-only，LongMemEval 为 system+user；
  MemoryOS 为 system+user。runner 已在 `answer_prompts.prediction.jsonl` 写入
  `prompt_messages`，并在 answer 失败后 resume 时复用已落盘 message 结构。最新
  handoff 为 `docs/handoffs/2026-06-22-prompt-messages-implementation.md`。
  已验证：framework reader + 四 adapter + 三个 runner prompt/resume focused 为
  `204 passed, 2 warnings, 2 subtests passed`；完整 runner/protocol/registered/CLI/
  efficiency/artifact focused 为 `188 passed`；文档规范 `5 passed`；`compileall`
  和 `git diff --check` exit 0。2026-06-22 checkpoint 前完整离线回归为
  `669 passed, 3 deselected, 2 warnings, 6 subtests passed`。真实 API smoke 已暴露并修复
  isolated 路径缺口；下一步仍需用户确认新规模、run_id 和预算后重跑严格
  retrieve-first smoke。
- 2026-06-22 answer LLM 参数显式化已完成：当前代码已新增 `AnswerLLMSettings`，
  并在 registered prediction 中按 method × benchmark 解析官方 answer 参数：Mem0
  LoCoMo/LongMemEval `temperature=0,max_tokens=4096`；A-Mem LoCoMo
  `temperature=0.7,max_tokens=1000`；LightMem LoCoMo `temperature=0.0`；
  A-Mem / LightMem / MemoryOS LongMemEval
  `temperature=0.0,top_p=0.8,max_tokens=2000`；MemoryOS LoCoMo
  `temperature=0.7,max_tokens=2000`。OpenAI-compatible answer client
  只传非空参数，manifest 写入 `answer_parameters`，framework answer model
  inventory 使用最终 model。实现交接：
  `docs/handoffs/2026-06-22-answer-llm-settings-implementation.md`。
- 当前动态主计划：`docs/current-roadmap.md`。已完成项必须立即勾选；后续恢复优先读取
  本文件、动态路线图、当前实施计划和最新 handoff，不重复扫描历史大文档。
- 当前任务裁定入口：`docs/task-ledger.md`。OpenCode dated result、旧 handoff 和路线图
  如有冲突，以该总账和当前代码/outputs 为准。
- 当前协议重构设计：
  `docs/superpowers/specs/2026-06-20-retrieve-first-memory-module-design.md`。该设计已获
  用户方向认可；实施计划为
  `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`。2026-06-22 已按用户
  最新决策修订为 `AnswerPromptResult` 语义：`BaseMemoryProvider.retrieve(question)`
  返回 method 构造好的完整 `prompt_messages`，framework answer LLM 直接使用这些
  role messages；`answer_prompt` 只是兼容文本视图；`metadata` 保存
  `answer_context`、原始检索项、prompt profile 和调试信息。Mem0、
  A-Mem、LightMem、MemoryOS 均已继承 `BaseMemoryProvider`，`add()` 在迁移期同时兼容
  单个 `Conversation` 和旧 list 输入，`get_answer()` 暂时仅作为 legacy wrapper。
  runner 已写出 `answer_prompts.prediction.jsonl`，并支持 prompt messages 已落盘、
  answer pending 的 resume；efficiency 中的 `injected_memory_context_tokens` 只在
  `metadata["answer_context"]` 存在时统计。恢复时优先读
  `docs/handoffs/2026-06-22-prompt-messages-implementation.md`。
- 最新完整回归（2026-06-15）：`uv run pytest -q` 为 450 passed、3 deselected、
  6 subtests passed；MemoryOS marker 为 168 passed、285 deselected、2 subtests passed；
  API collect 为 3 项；文档规范 5 passed；`compileall` exit 0。验证过程未执行付费 API。
- src-layout、pytest、可观测性、标准实验产物、通用 conversation-QA prediction runner、
  conversation-level resume、统一 CLI/config 均已完成。历史 turn-level resume 已不作为
  当前能力使用；Mem0/MemoryOS/A-Mem/LightMem 当前统一按 conversation 级 resume 管理。
- 当前 prediction / full run 并行边界已重新对齐：只做单个 method × 单个 benchmark 内部的
  conversation-level parallel / resume。不要继续推进 shared method instance、
  method execution policy 矩阵或 method×benchmark full parallel orchestrator。多个 method
  或 benchmark 的并行实验，当前用多个终端分别运行即可；`calibrate-smoke` 只保留为极小
  成本校准/批量 smoke 便利入口，不作为 full 实验调度主线。
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
- LoCoMo 四路并行极小 smoke 已多轮 4/4 通过（Mem0/MemoryOS/A-Mem/LightMem@locomo），
  验证了首次 API 主体链路和 prediction efficiency observation。最新真实 API smoke
  `*-smoke-4c20t-w4-20260620` 已关闭两个历史 P0 缺口：Mem0 isolated worker 现在有
  conversation-level memory build observation（`memory_build_latency_ms.count=4`）；
  LightMem OP-update 现在有 stage=`memory_build`、model_id=`lightmem-memory-llm` 的
  `llm_call(api_usage)`。旧 run `mem0-locomo-smoke10c-10t-w10-20260620` 和
  `lightmem-api-smoke-v2` 仍是旧事实，不能作为完整成本依据。经费估算必须继续区分
  `api_usage`、`method_native` 和 `tokenizer_estimate`。
- LongMemEval smoke round 裁剪已实现（registry 在 SMOKE 下对单 instance 内部按完整
  双 turn round 裁剪），LightMem 并发导入竞态已修（`threading.Lock` + 不回撤
  `sys.path`）。未重跑真实 LongMemEval API smoke。
- calibrate-smoke 首次运行友好性已修：默认 `resume=False`，CLI 新增显式 `--resume`；
  public manifest secret 检测允许 `llm_tokenizer`/`embedding_tokenizer`/`*_tokens`
  技术字段，继续拒绝真实 token/secret 字段。
- `transformers`、`llmlingua` 已通过 `uv add` 写入 `pyproject.toml`/`uv.lock`。
  LightMem llmlingua 注入 `attn_implementation=eager`，第三方仅透传 `model_config`。
- Rich 并行输出仍需治理：calibrate-smoke monitor 已改为统一表格并修过 LongMemEval
  variant progress，但 isolated prediction 中间进度仍可能长时间不动，第三方 warning/tqdm
  仍可能插入终端。
- 2026-06-20 最新工程断点：`opencode/opencode_result.md` 已成为 OpenCode 最新结果
  索引，当前最新条目是 `opencode_result-6.20-00h-smoke-4c20t-w4.md`、
  `opencode_result-6.20-01h-amem-lightmem-retry-timeout.md` 和
  `opencode_result-6.20-02h-mem0-reference-date-gap.md`。OpenCode 已用真实 API 复验：
  Mem0 / MemoryOS / A-Mem / LightMem 的 LoCoMo 4 conversations、20 turns、4 workers
  smoke 均 completed，并生成 observation 覆盖矩阵。A-Mem/LightMem/MemoryOS
  `allow_smoke_worker_override=True` 已生效；LoCoMo smoke adapter 已改为保留所有
  evidence 完整落在截断历史里的问题，`--question-limit-per-conversation > 1` 由 runner
  正常裁剪。Mem0 official-full v3 的 OpenAI-compatible embedding API SSL 断连路径已补
  timeout/max_retries，并通过新极小 smoke 未复现断连；full 仍需新 run_id 重跑后才能关闭。
  `predict` / `run` 已默认开启 prediction efficiency observation，如需调试关闭必须显式
  传 `--disable-efficiency-observability`。不要在这些 open 问题没有记录/确认前启动新的
  full API 实验。
- OpenCode 已成为用户启用的正式外部推进通道。Codex 每次额度中断后恢复时，必须读取
  `opencode/opencode_result.md`、核对实际 diff 和验证证据，再决定哪些内容写入主线。
  OpenCode 可承担实质开发任务，不再只承担机械任务；但 OpenCode 报告完成不等于任务完成。
- Claude Code 是 Codex 当前工作流里可主动调用的 subagent / 副手，不是 OpenCode 那种
  额度空档期独立推进项目的外部 agent。最小用法记录在 `docs/claude-code-agent.md`；
  用户已授权 Codex 自由使用 Claude Code 并发挥其最大能力。Codex 应根据 Claude Code
  的真实表现动态决定任务难度、上下文规模和是否继续加大使用；调用后仍必须复核输出、
  检查 diff、运行测试，再决定是否采纳。
- A-Mem / LightMem 接入设计已写入
  `docs/superpowers/specs/2026-06-16-amem-lightmem-adapter-design.md`。实施顺序为：
  先 A-Mem 垂直闭环，再 LightMem；都必须复用通用 conversation-QA runner、标准
  artifact、resume 和 Phase G efficiency observation，不创建 method × benchmark 专用
  runner。
- 当前目录是 Git 仓库，当前分支为 `main`。`.gitignore` 已保护
  `data/`、`models/`、`outputs/`、`.env`、`.claude/`、`third_party/benchmarks/` 和
  third-party 生成物；不得把大型 dataset/model/output 加入 Git。
- A-Mem 与 LightMem adapter 已完成 config、source identity、registry、question-level
  efficiency observation、fake/offline contract 和 registered runner smoke。LightMem 生产
  backend 已通过测试覆盖官方 `LightMemory.from_config()` 配置注入，但尚未执行真实 API
  smoke。2026-06-17 重新审计后确认：fake/offline smoke 只能证明框架链路，不代表
  A-Mem / LightMem 已自动按论文 Table 级参数与调用流程对齐。A-Mem 已补齐 Table 1
  GPT-4o-mini profile 中非 adversarial QA 的官方 query keyword generation 和 Table 8
  category k；category 5 adversarial 因官方 prompt 需要 gold answer，当前按 public-input
  规则显式拒绝。A-Mem 已实现 wrapper 层 conversation-level 持久化：每个 completed
  conversation 保存 `memories.pkl`、官方 retriever cache/embeddings 和
  `state_manifest.json`，resume 时由 registry 基于 `completed_conversations` 加载；不做
  turn-level resume，不修改 A-Mem 核心算法流程。LightMem 已落实用户指定
  `(r=0.7, th=512)` official-mini、LoCoMo/LongMemEval 增量写入粒度和
  官方 reader prompt 方向；LoCoMo 已专门化为 LightMem `search_locomo.py` 风格的
  Qdrant payload/vector combined 检索，并在 `add()` 完成后执行
  `construct_update_queue_all_entries()` 与
  `offline_update_all_entries(score_threshold=0.9)`；LongMemEval OP-update 仍是 future
  profile，当前保持 `LightMemory.retrieve()` online 路径。LightMem 已实现
  conversation-level resume，registry 会对 completed conversations 调
  `load_existing_conversation_state()`，用同一 `storage_root+conversation_id` 重建 backend
  供剩余问题回答。A-Mem 的 ohmygpt/OpenAI-compatible
  `base_url` 已在 wrapper 层显式注入官方
  OpenAI controller client；资源与参数审计见
  `docs/method-resource-parameter-audit.md`。
  Mem0 smoke `top_k=200`；Mem0 reader 已按 benchmark 分支调用 vendored
  memory-benchmarks 官方 LoCoMo / LongMemEval `get_answer_generation_prompt(...)`，
  未知 benchmark 保留通用 fallback；Mem0 source identity 已纳入这两个 prompt 文件。
  Mem0 LoCoMo 写入粒度仍按官方 `CHUNK_SIZE=1` 在 adapter 内部逐条调用；
  Mem0 LongMemEval 按官方 `CHUNK_SIZE=2` user+assistant pair 写入。2026-06-19 用户新决策后，
  Mem0 对 LoCoMo/LongMemEval 均不再暴露 runner turn-level resume，统一使用
  conversation-level resume。
  LightMem 真实运行所需
  `models/all-MiniLM-L6-v2` 和
  `models/llmlingua-2-bert-base-multilingual-cased-meetingbank` 已补齐并通过本地资源
  校验；adapter 仍会在真实 backend 构造前强校验。最新 A-Mem 持久化 focused 验证：
  `uv run pytest tests/test_amem_adapter.py -q` 为 `12 passed, 1 warning`；
  `uv run pytest tests/test_amem_registered_prediction.py tests/test_method_registry.py tests/test_config_profiles.py -q`
  为 `22 passed`；更宽 focused 回归
  `uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_amem_lightmem_registry.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py tests/test_method_registry.py tests/test_config_profiles.py -q`
  为 `67 passed, 1 warning`；文档规范 `5 passed`；`compileall` 和 `git diff --check`
  均通过。最新 LightMem focused 验证：
  `uv run pytest tests/test_lightmem_adapter.py -q` 为 `16 passed, 1 warning`；
  `uv run pytest tests/test_amem_lightmem_registry.py -q` 为 `5 passed`。
  最新 Mem0 prompt/top_k/resume focused 验证：
  `uv run pytest tests/test_mem0_adapter.py tests/test_method_registry.py tests/test_config_profiles.py tests/test_documentation_standards.py -q`
  旧结果为 `40 passed`；纠偏后新增验证
  `uv run pytest tests/test_mem0_adapter.py tests/test_prediction_runner.py::test_resumable_system_can_disable_turn_resume_per_conversation tests/test_method_registry.py tests/test_config_profiles.py tests/test_documentation_standards.py -q`
  为 `43 passed`；`uv run python -m compileall -q src/memory_benchmark tests`
  exit 0。宽回归
  `uv run pytest tests/test_mem0_adapter.py tests/test_mem0_source_compatibility.py tests/test_prediction_runner.py tests/test_conversation_runner.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_method_registry.py tests/test_config_profiles.py -q`
  当前为 `99 passed`；`tests/test_documentation_standards.py` 为 `5 passed`；
  `compileall` 和 `git diff --check` 均通过。未执行真实 API。
- A-Mem 官方 robust layer 导入需要 `rank-bm25` 和 `litellm`，已通过 `uv add` 写入
  `pyproject.toml` / `uv.lock`。这是官方 A-Mem requirements 中的正式依赖。
- README 已于 2026-06-17 更新为 GitHub 项目入口，清理本地绝对路径并明确本地资产不入库、
  真实 API 实验需显式确认；交接见 `docs/handoffs/2026-06-17-readme-github-refresh.md`。
- 大型 `data/` 已发布到 Hugging Face public dataset repo
  `BuptZZP/agentmemorybench-data`，当前 revision 为
  `0eb625cd4c7cecca7951c7c7feae4211861f979d`；准备脚本为
  `scripts/prepare_hf_dataset_bundle.py`，操作文档为 `docs/huggingface-datasets.md`。
- 本轮精确交接：
  `docs/handoffs/2026-06-19-opencode-progress-review.md`、
  `docs/handoffs/2026-06-18-longmemeval-smoke-lightmem-import.md` 和
  `docs/handoffs/2026-06-18-token-observation-locomo-smoke.md`。
  上游校准修复登记在
  `docs/handoffs/2026-06-18-calibrate-smoke-bugfix-review.md`。
- 上一轮 LightMem LoCoMo 专门化交接：
  `docs/handoffs/2026-06-17-lightmem-locomo-specialization.md`。
- 上一轮 A-Mem 精确交接：
  `docs/handoffs/2026-06-17-amem-red-tests-handoff.md`。
- 上一轮 method table 参数审计交接：
  `docs/handoffs/2026-06-17-method-table-parameter-audit.md`。
- 当前 LightMem 断点：用户已确认 LightMem + LoCoMo 需要专门化为官方
  `experiments/locomo/search_locomo.py` 逻辑，LongMemEval 保持通用
  `LightMemory.retrieve()` 逻辑。代码已实现 LoCoMo `add()` 后自动执行
  `construct_update_queue_all_entries()` 和
  `offline_update_all_entries(score_threshold=0.9)`，`get_answer()` 已改为 Qdrant
  payload/vector combined search，不再调用 `backend.retrieve()`。LightMem focused
  验证 `uv run pytest tests/test_lightmem_adapter.py -q` 为 `15 passed, 1 warning`；
  更宽 focused 回归
  `uv run pytest tests/test_lightmem_adapter.py tests/test_lightmem_registered_prediction.py tests/test_amem_lightmem_registry.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q`
  为 `49 passed, 1 warning`；文档规范 `5 passed`；`compileall` exit 0。未执行真实 API。
  下一步可继续处理本轮改动提交，或在用户确认 API 预算、样本规模和 run_id 后启动极小
  smoke。
- 当前 A-Mem / LightMem / Mem0 official-profile 断点：上一批 LightMem/成本校准 checkpoint
  已提交并推送到 GitHub `c01559f`；A-Mem/LightMem official-profile 变更已提交为
  `02649ed`。本轮 Mem0 prompt/top_k/resume 变更已完成并通过离线验证；恢复时先读
  `docs/handoffs/2026-06-18-mem0-prompt-resume.md`，不要重复大范围扫描历史文档。
- Method 原生接口清单：
  `docs/method-interface-inventory.md`。新增或重修 method adapter 前必须先更新该文档。
- Method official profile 对齐实施计划：
  `docs/superpowers/plans/2026-06-17-method-official-profile-alignment.md`。下一步应按该计划
  修正 Mem0、A-Mem 和 LightMem，完成前不得启动对应真实 API smoke。
- A-Mem / LightMem adapter 接入完成时的历史交接：
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
- 成本校准 smoke 外层 orchestrator 已实现，且用户/外部 agent 已做过 LoCoMo 极小
  smoke 排查：
  `memory-benchmark calibrate-smoke` 会对多个 method × benchmark 启动独立 smoke
  child run，固定每组合 1 个 conversation/LongMemEval instance，强制开启
  efficiency observation，并用 `--max-parallel-runs` 限制外层并发。该入口只作为极小
  成本校准/批量 smoke 便利能力，不作为 full 实验 method×benchmark 并行调度主线。
  2026-06-18
  首次四路 LoCoMo smoke 暴露两个基础问题：首次运行被错误强制 resume，以及 public
  manifest secret 检测误伤 `llm_tokenizer`。当前已修复：默认 `resume=False`，
  CLI 支持显式 `--resume`，secret 检测允许 tokenizer/tokens 技术字段但继续拒绝真实
  token 字段。实际文件证据显示 Mem0/MemoryOS/A-Mem 已在
  `locomo-smoke-20260618-*` 前缀下完成；LightMem 已在单独
  `outputs/locomo-lightmem-smoke-obs/` 完成，因此四个 method 功能上均已跑通 LoCoMo
  极小 smoke。LongMemEval smoke 已改为 instance 内按完整双 turn round 裁剪，
  避免一个 S instance 仍包含数百条 message；LightMem vendored import 已加锁，
  并在当前进程保留 LightMem `src` 路径，避免并发 smoke 时反复插拔 `sys.path`。
  用户已确认不做统一 OpenAI-compatible API gateway，当前只要求每个 method 记录可
  审计 token 消耗量。A-Mem / LightMem 已补齐 wrapper 层可见 LLM token observation：
  A-Mem 记录 query-generation 与 answer LLM，LightMem 记录 answer LLM；当前优先读取
  response usage，缺失时回退 `tokenizer_estimate`，不冒充 API usage。2026-06-19
  Codex 继续补齐 A-Mem official runtime memory-build `llm_controller.llm.get_completion()`
  与 LightMem backend memory-build `manager.generate_response()` 的透明 API usage observer；
  fake/offline focused 回归已通过。真实旧 run `outputs/lightmem-api-smoke-v2` 只记录了
  LightMem answer LLM 的 `api_usage`，未记录 OP-update 的 memory-build LLM usage；
  Codex 已在 2026-06-20 增加子线程 usage buffer 并通过 fake 线程池 OP-update 测试。
  旧 run 仍不能作为完整成本依据，恢复时先读
  `docs/handoffs/2026-06-20-observability-fixes-mem0-lightmem.md`。
  `calibrate-smoke` 已在启动线程池前串行预加载 transformers / sentence-transformers
  相关依赖，规避 LightMem 与其他 method 并行启动时的 lazy import 竞态。
  四 method 并行 LoCoMo 极小 smoke 已通过：
  `locomo-smoke-20260618-token-rich-v1-{mem0,memoryos,amem,lightmem}-locomo`
  均为 1 conversation / 1 question completed，并全部写出 prediction efficiency
  observation。Rich 终端输出仍有问题：多个 child run 的进度条会顺序/交错显示，
  第三方 warning 可插入进度区，且进度条 elapsed 秒数可能停住但后台实验仍运行。
  OpenCode 已新增 `CalibrationProgressMonitor`，在 `calibrate-smoke` 并行模式禁用
  child run Rich progress，由外层读取各 run 的 `checkpoints/progress.json` 并统一展示
  Rich `Live(Table)`；Codex 已修复其新增测试的 Rich 宽度问题，离线 focused 验证为
  `20 passed`。真实终端体验仍未完成：OpenCode 真实运行仍观察到 elapsed 停住、
  第三方 warning 插入进度区和 isolated prediction 进度长时间不动。
  2026-06-21 复核 `outputs/{mem0,memoryos,amem,lightmem}-smoke-4c20t-w4-20260620/`
  后确认：四个真实 smoke 均有 `artifacts/efficiency_observations.prediction.jsonl`、
  `summaries/efficiency_overall.prediction.json` 和 by-conversation summary。Mem0 raw
  observation 311 行，MemoryOS 171 行，A-Mem 244 行，LightMem 16 行；四者均记录
  memory build latency、retrieval latency、answer latency、injected context tokens 和
  answer LLM tokens。A-Mem full-v2 历史 run 没有 observation，不能拿来做成本依据；应以
  4c20t-w4 smoke 或后续新 run 的 observation 估算成本。
- OpenCode 曾提交 isolated worker 并行原型，早期版本不读取 completed conversation
  checkpoint。该限制已被后续 Codex 并行 resume 与分批运行控制修复；当前以
  `docs/handoffs/2026-06-19-parallel-resume-run-control.md` 和
  `docs/task-ledger.md` 为准。
- 并行 resume 与分批运行控制第一版已完成。设计文档：
  `docs/superpowers/specs/2026-06-19-parallel-resume-run-control-design.md`；实施计划：
  `docs/superpowers/plans/2026-06-19-parallel-resume-run-control.md`。核心决策：
  `max_new_conversations` 是本次命令预算，不是实验 identity，不写入 prediction manifest；
  同一 `run_id` 可用不同预算分批 resume。Mem0 已按用户 2026-06-19 新决策统一改为
  conversation-level resume，不再保留 LoCoMo turn-level resume；isolated worker 第一版
  只支持 conversation-level resume，遇到 turn checkpoint 必须 fail closed。
  当前已实现 generic work plan、normal/isolated 共用 completed conversation 与 pending
  question 判断、isolated worker conversation-level/question-level resume、CLI 与
  calibrate-smoke 的 `--max-new-conversations` 透传。离线 focused 验证：
  `tests/test_prediction_runner.py` 为 `40 passed`；
  `tests/test_main_cli.py tests/test_cost_calibration_smoke.py` 为 `37 passed`；
  合并 focused 回归为 `119 passed`；`compileall` 和 `git diff --check` 已通过。
  本轮交接见 `docs/handoffs/2026-06-19-parallel-resume-run-control.md`。
  低额度暂停交接见 `docs/handoffs/2026-06-19-low-quota-checkpoint.md`。
- 历史并行失败语义曾是：一个 isolated worker 中的某个 conversation 失败后触发整个
  run fail-fast。该语义已在 2026-06-20 被新实现替代：局部 conversation 失败会写
  failed checkpoint 并允许 worker 继续后续 conversation；全局配置/source identity/
  依赖/manifest 错误仍 fail-fast。
- smoke worker 覆盖上限已从 2 放宽到 10：统一入口和旧 Mem0 兼容入口都不再由
  argparse 限死 `{1,2}`；配置层强校验 `1 <= smoke_max_workers <= 10`。如果后续
  LongMemEval 需要超过 10 的 smoke worker，必须先重新评估 API 速率、内存和第三方
  method 并发安全。
- Mem0 + LoCoMo 真实极小 smoke 已按 `run_id=mem0-locomo-smoke10c-10t-w10-20260620`
  跑通：10 conversation、每 conversation 最多 10 turn、10 worker、10 question 全部
  completed，0 failed。输出位于
  `outputs/mem0-locomo-smoke10c-10t-w10-20260620/`。同时发现 P0 观测缺口：
  raw efficiency observation 缺少 conversation-level memory build observation，
  `memory_build_latency_ms.count=0`；不能把该 run 的 memory build efficiency 当作完整
  成本依据。交接见 `docs/handoffs/2026-06-20-mem0-smoke10-worker10.md`。
- Mem0 + LoCoMo full-v4 已完成于 `outputs/mem0-locomo-full-v4/`：10 conversations、
  1540 questions completed，并生成 F1、LLM judge 和 efficiency summary。OpenCode 审计
  发现 Mem0 LoCoMo 全局 `reference_date` 只传年份，但每条检索记忆已带完整日期；
  当前记录为 informational，不判定 full-v4 作废。如未来要修，应在 conversation metadata
  中记录最后 session 的完整日期，并在新 run_id 中复验。
- 2026-06-19 Codex 本轮新增 prediction efficiency 人类可读摘要：
  `summaries/efficiency_overall.prediction.json`、
  `summaries/efficiency_by_conversation.prediction.json`、
  `summaries/efficiency_by_question.prediction.json`；raw observation JSONL 仍是事实来源。
  同时新增失败 conversation 默认隔离：`conversation_status.json` 中 failed conversation
  在默认 resume 中不重跑，只有 CLI `--retry-failed` 才重新纳入；isolated worker 失败会
  写具体 conversation failed checkpoint。Focused 验证
  `tests/test_efficiency_analysis.py tests/test_prediction_efficiency_observations.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py tests/test_prediction_runner.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py`
  为 `133 passed, 2 warnings`，未执行真实 API。本轮低额度交接见
  `docs/handoffs/2026-06-19-efficiency-summary-safe-retry.md`。
- 2026-06-20 用户已重新对齐 API 兜底与并行 worker 失败语义。设计文档：
  `docs/superpowers/specs/2026-06-20-api-retry-worker-failure-design.md`。当前结论：
  `--max-new-conversations` 是本次最多尝试的 eligible conversation 数，不是必须成功数；
  `--retry-failed` 只把历史 failed conversation 重新纳入 eligible 队列，同一次 run 内
  每个 conversation 仍然最多尝试一次；isolated worker 需要从旧 fail-fast 改为
  conversation 局部失败 continue，全局配置/source identity/依赖/manifest 错误仍
  fail-fast；所有 API/network 调用需要 timeout/retry 兜底，优先修 Mem0 embedding
  SSL 断连事故路径。
- 2026-06-20 上述设计的第一批实现已完成并离线验证：Mem0 config 新增
  `api_timeout_seconds=60.0`、`api_max_retries=8`，adapter 会对 vendored Mem0
  LLM/embedding OpenAI clients 调 `with_options()`；isolated worker 已支持
  conversation 局部失败 continue，并写 failed checkpoint / traceback /
  `conversation_failed_isolated` event；`PredictionRunPolicy.max_consecutive_failures`
  默认 3，连续失败达到阈值会停止该 worker 后续 conversation；`--retry-failed` 同 run
  内最多尝试一次的契约已有测试。Focused 验证见
  `docs/handoffs/2026-06-20-api-retry-worker-failure.md`。OpenCode 后续已为 A-Mem 和
  LightMem 补齐同类 `api_timeout_seconds=60.0` / `api_max_retries=8` 配置与 client 注入，
  并跑过 focused/宽回归；四个当前 method 的 OpenAI-compatible API timeout/retry 兜底
  已覆盖。真实断网/限流韧性测试仍属于后续工作。
- OpenCode 已为 MemoryOS eval import 增加全局锁，Codex focused 验证
  `tests/test_memoryos_adapter.py` 为 `131 passed, 2 subtests passed`。stdout、prediction
  artifact 膨胀和 metric category summary 已提升为框架级待办：所有第三方 method 的
  stdout/warning 都不能破坏 Rich 进度区；所有大段 prompt/context 不能逐 question 重复写入
  `method_predictions.jsonl`；所有带 `category` 的 answer-level metric 都必须输出
  overall 与 by-category summary。

恢复工作时按顺序读：

1. `docs/current-roadmap.md`
2. `docs/task-ledger.md`
3. `docs/superpowers/specs/2026-06-20-retrieve-first-memory-module-design.md`
4. `docs/superpowers/specs/2026-06-21-llm-provider-config-design.md`
5. `docs/superpowers/plans/2026-06-20-retrieve-first-memory-module.md`
6. `docs/handoffs/2026-06-20-retrieve-first-task1-core-protocol.md`
7. `docs/handoffs/2026-06-20-retrieve-first-task2-task3-reader-artifacts.md`
8. `docs/handoffs/2026-06-20-retrieve-first-task4-runner-basic.md`
9. `docs/handoffs/2026-06-21-retrieve-first-task5-retrieval-resume.md`
10. `docs/handoffs/2026-06-21-retrieve-first-task6-reader-wiring.md`
11. `docs/handoffs/2026-06-21-retrieve-first-task7-registry-capabilities.md`
12. `docs/handoffs/2026-06-21-retrieve-first-task8-mock-provider.md`
13. `docs/handoffs/2026-06-21-retrieve-first-task9-mem0.md`
14. `docs/handoffs/2026-06-21-retrieve-first-task10-amem.md`
15. `docs/handoffs/2026-06-21-retrieve-first-task11-lightmem.md`
16. `docs/handoffs/2026-06-21-retrieve-first-task12-memoryos.md`
17. `docs/handoffs/2026-06-21-retrieve-first-task13-and-task14-start.md`
18. `docs/handoffs/2026-06-21-retrieve-first-task14-efficiency.md`
19. `docs/handoffs/2026-06-21-retrieve-first-task15-artifact-evaluation.md`
20. `docs/handoffs/2026-06-20-retrieve-first-implementation.md`
21. `docs/handoffs/2026-06-21-low-quota-retrieve-first-task16.md`
22. `docs/handoffs/2026-06-21-retrieve-first-task6-partial-reader-cli.md`
23. `docs/handoffs/2026-06-21-llm-provider-config-design.md`
24. `docs/handoffs/2026-06-20-retrieve-first-design-docs.md`
25. `docs/handoffs/2026-06-20-opencode-6.20-sync.md`
26. `docs/handoffs/2026-06-20-opencode-sync-status-refresh.md`
27. `docs/handoffs/2026-06-20-observability-fixes-mem0-lightmem.md`
23. `docs/handoffs/2026-06-20-locomo-smoke-question-limit.md`
24. `docs/handoffs/2026-06-20-low-quota-opencode-handoff.md`
25. OpenCode 介入后恢复时读 `opencode/opencode_result.md`
26. `opencode/opencode_result-6.20-00h-smoke-4c20t-w4.md`
27. `opencode/opencode_result-6.20-01h-amem-lightmem-retry-timeout.md`
28. `opencode/opencode_result-6.20-02h-mem0-reference-date-gap.md`
29. `opencode/mem0-locomo-run-incidents.md`
30. `docs/handoffs/2026-06-19-efficiency-summary-safe-retry.md`
31. `docs/handoffs/2026-06-19-parallel-resume-run-control.md`
32. `docs/handoffs/2026-06-19-low-quota-checkpoint.md`
33. `docs/handoffs/2026-06-19-opencode-progress-review.md`
34. `docs/superpowers/plans/2026-06-19-efficiency-summary-and-safe-retry.md`
35. `docs/superpowers/specs/2026-06-19-parallel-resume-run-control-design.md`
36. `docs/superpowers/plans/2026-06-19-parallel-resume-run-control.md`
37. `docs/method-interface-inventory.md`
38. `docs/handoffs/2026-06-18-token-observation-locomo-smoke.md`
39. `docs/handoffs/2026-06-18-longmemeval-smoke-lightmem-import.md`
40. `docs/handoffs/2026-06-18-calibrate-smoke-bugfix-review.md`
41. `docs/handoffs/2026-06-18-mem0-prompt-resume.md`
42. `docs/handoffs/2026-06-17-lightmem-locomo-specialization.md`
43. `docs/handoffs/2026-06-17-amem-red-tests-handoff.md`
44. `docs/handoffs/2026-06-17-method-table-parameter-audit.md`
45. `docs/handoffs/2026-06-16-amem-lightmem-adapters.md`
46. `docs/superpowers/plans/2026-06-17-method-official-profile-alignment.md`
47. `docs/superpowers/plans/2026-06-16-amem-lightmem-adapter.md`
48. `docs/superpowers/specs/2026-06-16-amem-lightmem-adapter-design.md`
49. 派发 subagent 前读 `docs/subagent-strategy.md`

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
class BaseMemoryProvider(ABC):
    def add(self, conversation: Conversation) -> AddResult: ...
    def retrieve(self, question: Question) -> AnswerPromptResult: ...
```

规则：

- 新主协议是 `add(conversation)` + `retrieve(question)`。`retrieve()` 返回
  method 内部已经处理好的完整 `AnswerPromptResult.answer_prompt`。
- framework reader 统一负责调用 answer LLM、answer artifact 和最终
  `AnswerResult`。
- 旧 `BaseMemorySystem.add(list[Conversation])` / `get_answer(question)` 只是迁移期兼容；
  删除前必须先完成真实 retrieve-first API smoke 和 legacy 引用清理。
- 依靠 `conversation_id` 做记忆隔离，不做 reset 接口。
- 新 `add()` 接收单个 `Conversation`；runner 负责循环、并行、resume 和失败隔离。
- `retrieve()` 只接收 `Question`，不能接收 gold answer、evidence、top_k 或私有标签。
- `top_k` 属于 method 自己的配置，不放进统一接口参数。
- Phase 1 只做 memory-module evaluation，不再把新 method 当完整 agent system 接入。
- 内置 method 保留深度插桩；用户自定义 method 不强制实现内部 LLM/embedding 观测。
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
- method adapter 必须严格复刻目标 method 的官方/论文算法调用路径；如果论文、README、
  复现实验脚本和当前 adapter 之间存在不一致，必须先记录证据并和用户对齐，禁止凭
  “差不多能跑”擅自选择实现。
- 新增或重修任何 method adapter 前，必须先在 `docs/method-interface-inventory.md`
  记录该第三方仓库原生暴露接口的完整信息：写入、检索、回答/生成、离线更新、配置注入、
  输入参数、输出结构、调用粒度、prompt 来源、LLM/embedding 模型、API key/base URL
  传递位置，以及哪些字段不能进入 method。没有完成接口记录，不得启动真实 API smoke。
- 对任何不懂、犹豫或不确定的实验设置、参数含义、调用粒度和算法步骤，必须先明确告诉
  用户并等待确认；不得把未确认假设写进 official/smoke profile。
- 禁止修改第三方核心算法；wrapper 和配置注入优先放在本项目侧。若 adapter 无法准确
  观测，可在第三方源码加入可关闭、可审计且通过行为等价验证的纯 observer 插桩。
- 长实验 runner 必须写 `logs/run.log`、`logs/events.jsonl` 和 `checkpoints/progress.json`。
- 第三方 method 的 stdout、warning 和长文本调试输出不得直接污染终端进度区；但不能全局
  压掉用户 method 的调试输出。wrapper 应优先把输出可靠写入 `logs/run.log`/events，
  并用配置控制是否同步显示到终端。
- `method_predictions.jsonl` 只保存每题必要字段和轻量 metadata；大段 system prompt、
  reader prompt、injected context 或重复 metadata 必须按 run/conversation 单独记录一次，
  prediction 记录只保留引用。
- 新 runner 优先写标准 artifacts，只保留迁移所必需的 legacy alias。
- 新增 evaluator 时优先复用已有 `method_predictions.jsonl` 和 `evaluator_private_labels.jsonl`，不要重新调用 method。
- 新增 evaluator 时，如果 question 带 `category`，必须同时输出 overall summary 和
  by-category summary；这不是 LoCoMo F1 的特例。
- `predict` 与 `evaluate` 必须保持分离；`run` 只做二者的便利组合。
- `run_id` 对应不可变实验；resume 只能继续数据指纹、method、reader 和关键配置完全一致的运行。
- 分批运行控制属于本次命令预算，不属于不可变实验 identity。实现后
  `max_new_conversations` 可在同一 `run_id` 的多次 resume 中变化；不得把它写入
  prediction manifest 导致误拒绝 resume。
- 官方 profile 分为 `official`、`smoke`、`custom`；official 的关键复现参数不可临时覆盖。
- 用户配置采用分层 TOML，禁止为 method × benchmark 创建配置文件笛卡尔积；示例配置必须有详细注释。
- smoke profile 必须使用官方 method 参数；不得为了省钱降低 `top_k`、`retrieve_k`
  或 `retrieve_limit`。成本控制只通过 conversation/question/turn 规模裁剪。
- 效率 observation 未来按逐操作保存。缺少能力时必须在付费运行前报错或标为 unsupported，不能估算冒充实测。
- conversation + QA 全量实验应复用通用 runner；禁止为每个 method × benchmark 组合复制
  `<method>_<benchmark>_full.py`。method、adapter、evaluator 和并发策略通过明确依赖注入。
- conversation 级并行必须保证每个任务按 `add -> 本 conversation questions` 执行，
  worker 不直接并发写共享 JSONL；实验产物由协调层串行提交。
- 当前只推进 conversation 级 prediction 并行。method×benchmark 外层并行不是近期主线；
  需要同时跑多个 method/benchmark 时，优先用多个终端和不同 `run_id`。
- 当前 Mem0 只接本地 OSS 源码，不接 Mem0 Platform API。实验必须固定 Mem0 版本和源码
  tree hash；升级采用新版本临时验证后再切换，禁止自动跟踪 upstream `main`。
- Mem0 namespace 语义已确认：一个 `conversation_id` 对应一个逻辑 namespace；不复刻
  Mem0 官方 LoCoMo 双 speaker namespace 脚本。speaker 信息保留在 content/metadata，
  当前旧 `get_answer()` 和后续 `retrieve()` 都只能访问问题所属 conversation。
- Mem0 并行不再使用共享 OSS `Memory` 实例；统一走框架 conversation-level worker 和
  conversation-level resume。OpenAI key/base URL 通过 adapter 配置注入；官方 profile 使用
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
- OpenCode 已由用户启用为正式外部推进通道；Codex 不直接信任其结论，必须先读
  `opencode/opencode_result.md`、检查 diff 并跑必要验证。Codex 主动派发 OpenCode
  任务仍需用户明确要求或按用户已授权的任务范围执行；任务可以是实质开发，但必须写清
  边界、验收命令和禁止事项。

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

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
- 当前主线是审查并稳固 OpenCode 推进的并行/进度显示相关改动；A-Mem、LightMem、
  Mem0、MemoryOS adapter 已进入可 smoke 但仍需按 official profile 和 resume 契约验收。
- 当前阶段所有真实 LLM 调用统一使用 `gpt-4o-mini`；不要临时切换 `gpt-4o`、
  GPT-5 或其他模型，除非用户后续明确改口。

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
- LoCoMo 四路并行极小 smoke 已 4/4 通过（Mem0/MemoryOS/A-Mem/LightMem@locomo），
  验证了首次 API 运行的主体链路。A-Mem/LightMem 补齐了 wrapper 层 LLM token
  observation，但来源为 `tokenizer_estimate`（wrapper 只返回文本，不暴露原始 response
  usage），不冒充 `api_usage`。Mem0/MemoryOS 继续提供 `api_usage` 级逐调用明细。
- LongMemEval smoke round 裁剪已实现（registry 在 SMOKE 下对单 instance 内部按完整
  双 turn round 裁剪），LightMem 并发导入竞态已修（`threading.Lock` + 不回撤
  `sys.path`）。未重跑真实 LongMemEval API smoke。
- calibrate-smoke 首次运行友好性已修：默认 `resume=False`，CLI 新增显式 `--resume`；
  public manifest secret 检测允许 `llm_tokenizer`/`embedding_tokenizer`/`*_tokens`
  技术字段，继续拒绝真实 token/secret 字段。
- `transformers`、`llmlingua` 已通过 `uv add` 写入 `pyproject.toml`/`uv.lock`。
  LightMem llmlingua 注入 `attn_implementation=eager`，第三方仅透传 `model_config`。
- Rich 并行输出待修：多个 child run 的进度条会交错，第三方 warning 可插入进度区。
  不影响实验结果，codex 尚未修。
- OpenCode 已成为用户启用的正式外部推进通道。Codex 每次额度中断后恢复时，必须读取
  `opencode/opencode_result.md`、核对实际 diff 和验证证据，再决定哪些内容写入主线。
  OpenCode 可承担实质开发任务，不再只承担机械任务；但 OpenCode 报告完成不等于任务完成。
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
  Mem0 LoCoMo 写入粒度已按官方 `CHUNK_SIZE=1` 对齐，并启用 turn-level resume；
  Mem0 LongMemEval 按官方 `CHUNK_SIZE=2` user+assistant pair 写入，但
  `supports_turn_resume()` 对 LongMemEval 返回 False，因此通用 runner 对该路径使用
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
  efficiency observation，并用 `--max-parallel-runs` 限制外层并发。2026-06-18
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
  A-Mem 记录 query-generation 与 answer LLM，LightMem 记录 answer LLM；因第三方
  wrapper 只返回文本，当前来源为 `tokenizer_estimate`，不冒充 API usage。
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
- OpenCode 已提交 isolated worker 并行原型：非共享实例 method 可为每个 worker 创建独立
  method instance 并处理 conversation chunk；Codex focused 验证
  `tests/test_prediction_runner.py tests/test_config_profiles.py tests/test_method_registry.py`
  为 `56 passed`。但该原型当前不读取 completed conversation checkpoint，`completed_conversations=()`
  写死，因此不满足 conversation-level resume，不能用于 official/full 长实验。
- 并行 resume 与分批运行控制第一版已完成。设计文档：
  `docs/superpowers/specs/2026-06-19-parallel-resume-run-control-design.md`；实施计划：
  `docs/superpowers/plans/2026-06-19-parallel-resume-run-control.md`。核心决策：
  `max_new_conversations` 是本次命令预算，不是实验 identity，不写入 prediction manifest；
  同一 `run_id` 可用不同预算分批 resume。Mem0 LoCoMo 保留 turn-level resume；isolated
  worker 第一版只支持 conversation-level resume，遇到 turn checkpoint 必须 fail closed。
  当前已实现 generic work plan、normal/isolated 共用 completed conversation 与 pending
  question 判断、isolated worker conversation-level/question-level resume、CLI 与
  calibrate-smoke 的 `--max-new-conversations` 透传。离线 focused 验证：
  `tests/test_prediction_runner.py` 为 `40 passed`；
  `tests/test_main_cli.py tests/test_cost_calibration_smoke.py` 为 `37 passed`；
  合并 focused 回归为 `119 passed`；`compileall` 和 `git diff --check` 已通过。
  本轮交接见 `docs/handoffs/2026-06-19-parallel-resume-run-control.md`。
  低额度暂停交接见 `docs/handoffs/2026-06-19-low-quota-checkpoint.md`。
- OpenCode 已为 MemoryOS eval import 增加全局锁，Codex focused 验证
  `tests/test_memoryos_adapter.py` 为 `131 passed, 2 subtests passed`。stdout、prediction
  artifact 膨胀和 metric category summary 已提升为框架级待办：所有第三方 method 的
  stdout/warning 都不能破坏 Rich 进度区；所有大段 prompt/context 不能逐 question 重复写入
  `method_predictions.jsonl`；所有带 `category` 的 answer-level metric 都必须输出
  overall 与 by-category summary。

恢复工作时按顺序读：

1. `docs/current-roadmap.md`
2. `docs/handoffs/2026-06-19-parallel-resume-run-control.md`
3. `docs/handoffs/2026-06-19-low-quota-checkpoint.md`
4. `docs/handoffs/2026-06-19-opencode-progress-review.md`
5. OpenCode 介入后恢复时读 `opencode/opencode_result.md`
6. `docs/superpowers/specs/2026-06-19-parallel-resume-run-control-design.md`
7. `docs/superpowers/plans/2026-06-19-parallel-resume-run-control.md`
6. `docs/method-interface-inventory.md`
7. `docs/handoffs/2026-06-18-token-observation-locomo-smoke.md`
8. `docs/handoffs/2026-06-18-longmemeval-smoke-lightmem-import.md`
9. `docs/handoffs/2026-06-18-calibrate-smoke-bugfix-review.md`
10. `docs/handoffs/2026-06-18-mem0-prompt-resume.md`
11. `docs/handoffs/2026-06-17-lightmem-locomo-specialization.md`
12. `docs/handoffs/2026-06-17-amem-red-tests-handoff.md`
13. `docs/handoffs/2026-06-17-method-table-parameter-audit.md`
14. `docs/handoffs/2026-06-16-amem-lightmem-adapters.md`
15. `docs/superpowers/plans/2026-06-17-method-official-profile-alignment.md`
16. `docs/superpowers/plans/2026-06-16-amem-lightmem-adapter.md`
17. `docs/superpowers/specs/2026-06-16-amem-lightmem-adapter-design.md`
18. 派发 subagent 前读 `docs/subagent-strategy.md`

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

- conversation + QA benchmark 要求框架层的 method adapter 必须提供
  `get_answer(question)`。第三方原始仓库可以没有同名函数，但 adapter 必须用其官方
  answer 接口，或用其官方 benchmark 的 `retrieval/search + prompt + LLM` 流程包装成
  `get_answer()`。
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
- 第三方 method 的 stdout、warning 和长文本调试输出不得直接污染终端进度区；wrapper
  应统一捕获、重定向到日志或按配置静默。
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

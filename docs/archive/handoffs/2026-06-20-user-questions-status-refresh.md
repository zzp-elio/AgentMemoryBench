# 2026-06-20 用户问题状态刷新交接

## 背景

用户在额度恢复后集中提出多个方向：

- LightMem 的观测问题是否解决。
- `smoke-conversation-limit`、`question-limit-per-conversation`、
  `smoke-turn-limit` 等参数是否是“最多多少”，超过真实数据量时是否自动取 min。
- LoCoMo smoke 在 `smoke_turn_limit=10` 时出现
  `LoCoMo smoke history does not cover any complete private evidence set for conv-50`
  的原因。
- Mem0 isolated worker memory build observation 缺失是否也存在于其他 method。
- 观测是否必须深入 method 内部，若只在 adapter/predict 层能观测什么。
- 四个 method 对 LongMemEval 是否都有对应官方策略/prompt。
- 交接文档、spec、plan 是否有状态总账，避免遗留问题丢失。
- 是否应该更频繁 git commit。
- 本地 Claude Code 是否可作为 Codex 可调用的 subagent / 副手使用，并记录用法。

本轮未启动真实 API 实验，只做文档更新和本地只读审计。

## 已记录到任务总账

已更新 `docs/task-ledger.md`，新增或强化以下任务：

- P0: `smoke/run limit 参数语义说明与强校验`
- P0: `四个 method 的 prediction efficiency 覆盖矩阵`
- P2: `method × benchmark 专用 prompt/策略审计`
- P2: `handoff/spec/plan 状态二次审计`
- P2: `git 小步 checkpoint 策略`
- P2: `Claude Code 作为 Codex subagent 的使用说明`

Claude Code 最小用法已写入：

```text
docs/claude-code-agent.md
```

## Efficiency observation 只读审计

扫描命令读取了所有现有：

```text
outputs/*/summaries/efficiency_overall.prediction.json
```

当前发现：

| run_id | method | 结论 |
| --- | --- | --- |
| `amem-api-smoke` | A-Mem | 有 build latency、retrieval、answer、context；LLM keys 包含 `memory_build:amem-memory-build-llm`、`retrieval:amem-query-llm`、`answer:amem-answer-llm`。 |
| `lightmem-api-smoke` | LightMem | 有 build latency、retrieval、answer、context；但 LLM keys 只有 `answer:lightmem-answer-llm`，缺 memory-build LLM token。 |
| `lightmem-api-smoke-v2` | LightMem | 同上，且已在总账里记录 OP-update 内部 `manager.generate_response()` 未被捕获。 |
| `mem0-worker-smoke-v2` | Mem0 | 有 build latency、retrieval、answer、context；LLM keys 包含 `memory_build:mem0-memory-llm` 和 `answer:mem0-answer-llm`；embedding keys 包含 build/retrieval。 |
| `mem0-worker-smoke-v3` | Mem0 | 同 `v2`，有 build LLM 和 build embedding observation。 |
| `mem0-locomo-smoke10c-10t-w10-20260620` | Mem0 | 功能跑通 10/10 conversation，但 `build_count=0`，缺 conversation-level build observation；raw observation 只有 retrieval embedding、answer LLM、question efficiency。 |

阶段结论：

- LightMem 观测问题还没有解决：build latency 有，但 OP-update 内部 LLM token 仍缺。
- Mem0 不是所有路径都缺 build observation：旧 2 worker smoke 有，新的 10 worker run
  缺，说明问题很可能在高并发/isolated worker observation bundle 汇总路径。
- A-Mem 当前已有一条真实 smoke 显示 build/retrieval/answer LLM observation 存在。
- MemoryOS 需要单独查最近可用 run 或补一个小 smoke；本轮没有新的
  `efficiency_overall.prediction.json` 可与三者直接对比。

## 参数语义现状

当前实现不是全部静默取 min：

- `smoke-conversation-limit`
  - LoCoMo preparation 会先 `adapter.load(limit=request.smoke_conversation_limit)`；
  - `build_locomo_smoke_dataset()` 如果实际 conversation 数少于请求数，会抛
    `ConfigurationError`；
  - 因此超过真实数据量时当前是 fail closed，不是自动 min。
- `smoke-turn-limit`
  - 是每个 smoke conversation 最多保留的历史 turn 数；
  - 如果过小导致没有任何 QA 的完整 evidence 被保留，会抛错：
    `LoCoMo smoke history does not cover any complete private evidence set ...`。
- `question-limit-per-conversation`
  - 是 runner 层每个 conversation 最多回答多少问题；
  - 但 LoCoMo smoke adapter 当前每个 conversation 只保留 1 个可回答问题，所以设置大于
    1 目前不会生效，已列 P0。
- `max-new-conversations`
  - 是本次命令预算，不是实验 identity；
  - 用于同一 run_id 分批推进，默认不限制。

建议下一步：

- 写一份用户向的 CLI 参数语义文档。
- 决定 `smoke-conversation-limit` 超过真实数据量时是否改成 min；如果改，需要同步测试。
- LoCoMo smoke question 裁剪需要修复，否则 `question-limit-per-conversation` 容易误导用户。

## LoCoMo evidence 报错来源

该报错来自本项目：

```text
src/memory_benchmark/benchmark_adapters/locomo.py
```

函数：

```python
_build_locomo_smoke_conversation(...)
```

逻辑：

1. 按 session/turn 顺序保留最多 `turn_limit` 条历史。
2. 遍历 QA。
3. 只选择 `gold.evidence` 全部落在保留 turn id 中的问题。
4. 如果没有任何问题满足条件，则报错并提示增加 `--smoke-turn-limit`。

这是我们自己的强约束，目的是避免 smoke 花钱跑一个历史里根本没有答案证据的问题。
用户将 turn limit 从 10 提高到 20 后正常，符合该逻辑。

## 只在 adapter/predict 层能观测什么

不深入第三方 method 内部时，通常可以观测：

- `add(conversation)` 外层总耗时，即 `memory_build_total_latency_ms`。
- `get_answer(question)` 外层总耗时。
- answer 阶段 wrapper 自己调用的 LLM prompt token / output token。
- wrapper 自己拼入 reader prompt 的 memory context token。
- adapter 明确调用的 retrieval 函数耗时。

不深入第三方 method 内部时，通常观测不到或只能估算：

- method 内部 memory build 过程中每次 LLM 调用的真实 API usage。
- method 内部 embedding 调用次数、token 和 latency。
- offline update / consolidation / conflict merge 的内部 LLM 调用。
- 第三方库内部并发线程里的 ContextVar scope，除非显式传递或打 observer。

因此：成本精确估算至少需要在 adapter 层包住 method 暴露接口；若要精确到内部 LLM /
embedding call，必须通过官方 callback、wrapper observer 或轻量 monkeypatch/插桩。

## LongMemEval method 策略现状

根据 `docs/method-interface-inventory.md` 和当前代码：

- Mem0
  - LoCoMo / LongMemEval 都有 memory-benchmarks 官方 prompt 文件；
  - adapter 已按 benchmark 分支调用对应 `get_answer_generation_prompt(...)`。
- LightMem
  - LoCoMo 有 `experiments/locomo/search_locomo.py` 专门路径；
  - LongMemEval 有 `experiments/longmemeval/run_lightmem_gpt.py` 路径；
  - adapter 已区分 LoCoMo 与 LongMemEval。
- MemoryOS
  - 当前 adapter 基于 LoCoMo eval wrapper；
  - LongMemEval 方案仍 open，短期不要默认跑。
- A-Mem
  - 当前官方对齐主要是 LoCoMo Table 1 / robust path；
  - LongMemEval 没有已确认官方策略；
  - 不能默认宣称 A-Mem + LongMemEval 已可严格对齐。

更通用的问题：

- 许多 method 的“算法核心”可以跨 benchmark，但 answer prompt、query rewrite、
  category-specific k、question_time 注入等经常是 benchmark-specific。
- 新 benchmark 如果 method 官方没有策略，框架应让 method adapter 显式声明：
  - supported with official strategy
  - supported with generic fallback reader
  - unsupported
- 不能让 capability 只按 `conversation_qa` 粗粒度匹配后就直接跑所有 method × benchmark。

## Claude Code 入口

本机已确认：

```bash
which claude
# /opt/homebrew/bin/claude

claude --help
# 可用
```

已记录到：

```text
docs/claude-code-agent.md
```

最小用法：

- `claude -p "任务"`：非交互发一次任务并打印结果。
- `claude --continue`：继续当前目录最近会话。
- `claude --resume <session-id>`：按 session id 续会话。
- `claude --resume <session-id> --fork-session`：基于旧会话 fork。

定位纠正：

- Claude Code 是 Codex 当前工作流中可主动调用的 subagent / 副手。
- Claude Code 不是 OpenCode 那种在 Codex 额度空档期独立推进项目的外部 agent。
- Codex 调用 Claude Code 后仍必须复核输出、检查 diff、运行测试，再决定是否采纳。
- 用户已授权 Codex 自由使用 Claude Code，并根据 Claude Code 在本项目中的真实表现
  动态提高或降低任务难度；不预设只能做简单任务。

## Git 状态

当前 worktree 很脏，混有 Codex 和 OpenCode 多批改动。用户倾向更频繁 git commit。
建议下一步先做：

1. `git status --short` 分组。
2. 按功能边界拆 commit：
   - 并行/resume/失败隔离。
   - efficiency summary/observation。
   - Mem0 retry/timeout。
   - smoke worker 上限。
   - 文档总账和 handoff。
3. 提交前跑 focused 离线测试和 `git diff --check`。

不要把 `outputs/`、`data/`、`models/` 或 secret 加入 git。

## 下一步建议顺序

1. 修 Mem0 isolated worker 10 worker run 缺 build observation。
2. 修 LightMem OP-update 内部 build LLM token observation。
3. 写 CLI 参数语义文档，并决定超过数据量时是 min 还是 fail closed。
4. 做 method × benchmark strategy support matrix，特别是 LongMemEval 的 MemoryOS/A-Mem。
5. 整理 git diff，按小功能提交。

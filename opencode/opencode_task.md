# OpenCode 当前任务入口（2026-06-20）

请先读：

1. `AGENTS.md`
2. `docs/task-ledger.md`
3. `docs/current-roadmap.md`
4. `opencode/opencode_result.md`

## 最新事实

- `opencode_result-6.20-00h-smoke-4c20t-w4.md` 已完成四 method LoCoMo 4 conversations /
  20 turns / 4 workers 真实 API smoke：
  Mem0、MemoryOS、A-Mem、LightMem 均 completed，并生成 efficiency observation 覆盖矩阵。
- Mem0 isolated worker conversation-level observation 已复验关闭；不要再用旧 run
  `outputs/mem0-locomo-smoke10c-10t-w10-20260620/` 判断该问题仍存在。
- LightMem OP-update memory-build LLM usage 已复验关闭；不要再用旧 run
  `outputs/lightmem-api-smoke-v2/` 判断该问题仍存在。
- `opencode_result-6.20-01h-amem-lightmem-retry-timeout.md` 已为 A-Mem / LightMem 补齐
  API timeout/retry；Mem0 / MemoryOS 已有同类兜底。四个当前 method 的
  OpenAI-compatible timeout/retry 基础覆盖已关闭。
- `opencode_result-6.20-02h-mem0-reference-date-gap.md` 是 informational；用户决定暂不修。
- 不要启动 full API 实验，不要覆盖受保护历史输出。

## 当前不要做

- 不要重复跑 4c20t-w4 smoke。
- 不要恢复 turn-level resume。
- 不要恢复 PrefEval。
- 不要删除 `outputs/memoryos-locomo-full-20260603/`。
- 不要实现 retrieve-first 架构重构；设计已写入
  `docs/archive/specs/2026-06-20-retrieve-first-memory-module-design.md`，但用户尚未审阅
  并批准实施计划，未批准前不得改接口。

## 可执行任务（仅在用户明确让 OpenCode 继续时）

### 任务 1：只读检查当前文档一致性

目标：确认 `AGENTS.md`、`docs/current-roadmap.md`、`docs/task-ledger.md` 是否都已经写入
OpenCode 6.20 三份结果。

要求：

- 只读检查为主，除非发现明显状态冲突，否则不要改代码。
- 如需记录结果，只写入新的 `opencode/opencode_result-YYYY-MM-DD-HHh-*.md`，并更新
  `opencode/opencode_result.md` 索引。

### 任务 2：等待 Codex 的架构设计结论

用户提出将 method 接口从 `add + get_answer` 重构为
`add(conversation) + retrieve(question) + framework reader`。
这会影响 adapter、runner、observability、prompt、resume 和实验可复现性。

在用户审阅 spec 并确认实施计划之前，OpenCode 不应自行实现该重构。可以做的只有只读调研：

- 阅读 `supermemoryai-memorybench.md`。
- 阅读 `docs/archive/specs/2026-06-20-retrieve-first-memory-module-design.md`。
- 对照当前 `src/memory_benchmark/core/`、`src/memory_benchmark/methods/` 和
  `src/memory_benchmark/runners/prediction.py`，列出需要改动的文件清单。
- 不要提交代码改动。

## 注意事项

- OpenCode 的完成声明不是验收结论；Codex 会复核 diff 和测试。
- 所有真实 API 实验必须有用户明确确认规模和 `run_id`。
- 所有代码改动后至少跑相关 focused pytest、`uv run python -m compileall -q src/memory_benchmark tests`
  和 `git diff --check`。

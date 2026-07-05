# 2026-06-20 交接：OpenCode 最新进展同步与状态文档刷新

## 本次任务

用户要求先不继续写业务代码，优先读取 OpenCode 最新结果并刷新项目状态文档，避免
AGENTS、README、roadmap、task-ledger 中残留旧状态。

本次主要事实来源：

1. `opencode/opencode_result.md`
2. `opencode/opencode_result-6.19-codex-bugfix.md`
3. `opencode/mem0-locomo-run-incidents.md`
4. 用户附带文本：`Turn级别的resume我们暂时抛弃了...`
5. 当前代码和 `outputs/lightmem-api-smoke-v2/` 只读核验

## 已同步的最新事实

### 1. Turn-level resume 当前已弃用

当前主线只按 conversation-level resume 解释和推进。Mem0 / MemoryOS / A-Mem / LightMem
当前文档口径均改为 conversation-level resume。

注意：代码里仍保留历史 `BaseResumableMemorySystem` / `add_from_turn()` 相关实现和测试，
但当前不作为官方 method 的运行能力使用。后续是否清理代码，需要单独讨论。

### 2. OpenCode 已修复两项问题

已记录为 closed：

- A-Mem / LightMem / MemoryOS 补 `allow_smoke_worker_override=True`，与 Mem0 一致。
- isolated worker 的 `add()` 已包在 `conversation_scope` 内，避免 Mem0 isolated add 内部
  embedding observation 因缺 active scope 报错。

OpenCode 记录的验证：

- `uv run python -m compileall -q src/memory_benchmark tests` exit 0
- focused: `90 passed`
- wider focused: `141 passed, 2 warnings`

Codex 本次未重新运行这些测试，只把状态写入当前文档。

### 3. LoCoMo smoke 的 question limit 仍有 gap

`--question-limit-per-conversation` 是 runner 层预算，但 LoCoMo smoke adapter 目前每个
conversation 只保留 1 道 evidence 覆盖题。因此在 LoCoMo smoke 下传
`--question-limit-per-conversation 3` 仍只会回答 1 题。

已在 `docs/task-ledger.md` 和 `docs/current-roadmap.md` 标记为 P0 open。

### 4. LightMem memory-build observer 真实 smoke 未生效

真实输出 `outputs/lightmem-api-smoke-v2/artifacts/efficiency_observations.prediction.jsonl`
只有：

- `conversation_efficiency`：memory build total latency
- `llm_call`：answer LLM，`measurement_source=api_usage`
- `question_efficiency`

没有 LightMem OP-update 内部 memory-build LLM observation。

当前根因判断：LightMem 官方 `offline_update_all_entries()` /
`construct_update_queue_all_entries()` 内部使用 `ThreadPoolExecutor.map()`，没有传播
当前 ContextVar scope，导致 adapter observer 看到的 active scope 为空。

已在 `docs/task-ledger.md` 和 `docs/current-roadmap.md` 标记为 P0 open。

### 5. Mem0 LoCoMo official-full v3 事故

`opencode/mem0-locomo-run-incidents.md` 记录：

- v3 run_id: `mem0-locomo-full-v3`
- conv-30 完成，81 题有效。
- conv-43 在 Mem0 OpenAI embedding API 处发生 SSL `APIConnectionError`。
- failed checkpoint 和 traceback 已可诊断。
- v2 中 worker_7 / conv-48 crash 根因仍未知。

当前 open 任务：

- Mem0 embedder API retry/timeout 兜底。
- isolated worker 已运行线程无法被 Python thread 强杀，失败后其他 worker 可能继续空跑，
  但产物不会进入有效 artifact。

### 6. 参数语义

已写入 README：

- `--smoke-turn-limit`
- `--smoke-conversation-limit`
- `--question-limit-per-conversation`
- `--max-new-conversations`

均按“最多 N 个”理解；超过实际数据量时应取实际可用数量。当前 LoCoMo smoke question
limit 是已知例外，因为 adapter 已提前裁成 1 题。

### 7. Future ideas

新增 `docs/future-ideas.md`，记录：

- 实验监控 AI：读取 progress/events/summary/efficiency summary，支持自然语言查询实验状态，
  未来可接微信、飞书、Telegram 等。
- 新 method 接入 skill：项目成熟后重做，自动审计第三方 method 仓库、生成 adapter
  skeleton、跑 contract/resume/parallel/smoke 测试。

## 本次修改的文档

- `AGENTS.md`
- `README.md`
- `docs/current-roadmap.md`
- `docs/task-ledger.md`
- `docs/method-resource-parameter-audit.md`
- `docs/method-interface-inventory.md`
- `docs/future-ideas.md`
- 本文件

## 验证

本次主要是文档状态同步。已只读检查：

```bash
outputs/lightmem-api-smoke-v2/artifacts/efficiency_observations.prediction.jsonl
outputs/lightmem-api-smoke-v2/summaries/summary.json
```

已运行轻量验证：

```bash
git diff --check
uv run pytest tests/test_documentation_standards.py -q
```

结果：

- `git diff --check` 通过。
- `tests/test_documentation_standards.py`: `5 passed`。

未运行完整 pytest，未运行真实 API。

如要继续修代码，优先顺序：

1. Mem0 embedder retry/timeout。
2. LoCoMo smoke `question_limit_per_conversation` gap。
3. LightMem OP-update memory-build observer。
4. isolated worker 中间进度 / stdout-warning 治理。

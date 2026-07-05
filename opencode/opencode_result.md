# OpenCode 结果索引

本文件是 Codex 与 OpenCode 同步进度的稳定入口。OpenCode 可以把长篇执行记录按日期拆分，
但必须在这里更新最新结果文件，避免 Codex 恢复后读取旧文件或空文件。

记住不要修改任何opencode目录外的其他文件，所有的修改记录都应该写在日期文档（精确到小时）里，并且在这里更新最新结果指向的文件。

在日期文档中讲清楚：
1. 你读了哪些文件。
2. 你认为问题根因是什么。
3. 修改了哪些文件，每个文件改了什么。
4. 跑了哪些测试，完整结果是什么。
5. 还有哪些已知风险或没解决的问题。
6. 如果你无法修复，写清楚卡点、复现步骤和下一步建议。
## 最新结果


## 历史结果
`archive/opencode_result-6.22-longmemeval-costpilot-comparison.md` — 四 Method × LongMemEval-S 1-conv Cost Pilot 横向对比

| Method | Judge | $/conv | 500=$ | Time |
|---|---|---|---|---|
| LightMem | 1/1 | $0.011 | $6 | 5min |
| Mem0 | 1/1 | $0.454 | $227 | 48min |
| MemoryOS | 1/1 | $0.188 | $94 | 72min |
| A-Mem | 1/1 | $0.460 | $230 | 87min |

**四 method × 500 conv 总估算: $557 (GPT-4o-mini)**

`archive/opencode_result-6.22-codex-session-full.md` — 2026-06-22 完整会话记录（efficiency/progress/evaluate 修复，包含下方 bugfix 全部内容）

`archive/opencode_result-6.22-codex-efficiency-byquestion-progress-bugfix.md` — efficiency_by_question LLM token 全 0 + progress 显示修复（已被 session-full supersede）

`archive/opencode_result-6.20-02h-mem0-reference-date-gap.md` — Mem0 reference_date 传递缺口审计
- Mem0 官方 prompt 依赖 reference_date 做时间推理，adapter 从未传入正确值
- fallback 链全部失效：Conversation.metadata 无此字段，DB created_at 是写入时间而非对话时间
- 对照审计四 method 时间传递：MemoryOS/LightMem ✅，A-Mem ⚠️，Mem0 ❌
- 用户决定暂不修复，保留为已知 gap

`archive/opencode_result-6.20-01h-amem-lightmem-retry-timeout.md` — A-Mem / LightMem API retry/timeout 兜底修复
- A-Mem: `_create_openai_compatible_client` 注入 `timeout=60s`、`max_retries=8`
- LightMem: 新增 `_inject_api_retry_timeout()`，backend 创建后对 `manager.client` 调 `with_options()`
- 两 method config 均新增 `api_timeout_seconds`/`api_max_retries` 字段，TOML 均已配置
- 157 passed, 2 warnings，compileall OK

`archive/opencode_result-6.20-00h-smoke-4c20t-w4.md` — 四 method LoCoMo 4c20t-w4 smoke 验证
- 4/4 method 全部通过，conversation/4 question/4 completed
- Mem0 conversation-level observation 修复验证通过
- LightMem memory-build LLM observation 修复验证通过
- 四 method 完整 observation 覆盖矩阵
- `archive/opencode_result-6.19-codex-session.md` (Codex — A-Mem temporal fix + judge 并行 + judge 对齐)
- `archive/opencode_result-6.19-amem-session-time.md` (Codex)
- `archive/opencode_result-6.19.md`
- `archive/opencode_result-6.18.md`
`archive/opencode_result-6.19-codex-bugfix.md` — Codex 变更后 bug 诊断与修复（6 节格式 + 2 附录）
- 修复 1: `allow_smoke_worker_override` 四 method 统一
- 修复 2: isolated worker `add()` efficiency scope
- 附录 1: `--question-limit-per-conversation` smoke 下不生效（未修）
- 附录 2: LightMem memory-build observer 不生效，根因 `executor.map` 不传播 ContextVar（未修，待审阅）

`archive/mem0-locomo-run-incidents.md` — Mem0 LoCoMo official-full v2/v3 两次运行事故完整记录

`archive/session-2026-06-19-codex-bugfix/` — 同上，拆分版

## 协作规则

- OpenCode 完成任务后，应把详细执行记录写入日期文件，并同步更新本索引。
- Codex 恢复后，应先读本索引，再读“最新结果”指向的文件。
- OpenCode 的完成声明不是验收结论；Codex 必须检查 diff 并运行必要验证。
- 当前 open/closed 状态以 `docs/task-ledger.md` 为准。OpenCode 继续推进任务前应先核对
  该总账，避免把已被 Codex 修复或已 superseded 的旧问题重复处理。

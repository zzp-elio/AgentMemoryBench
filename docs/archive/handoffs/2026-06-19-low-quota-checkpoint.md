# 2026-06-19 低额度暂停交接

## 当前状态

用户提示 5h 额度约剩 7%。本轮判断：不要在低额度窗口内强行修
Rich 并行终端展示、框架级 stdout/warning 捕获、prediction artifact 瘦身。
这三项都涉及 runner 输出协议、第三方 stdout 行为和真实终端体验，仓促修改风险较高。

已完成并验证的最近 checkpoint：

- `max_new_conversations` 已实现为本次命令预算，不参与 prediction manifest identity。
- normal path 与 isolated worker path 已共用 `_PredictionWorkPlan`。
- isolated worker 已支持 conversation-level resume 和 question-level resume。
- isolated worker 遇到 turn-level ingest checkpoint 会 fail closed。
- `predict` / `run` / `calibrate-smoke` 均可传递 `--max-new-conversations`。
- 详细交接：`docs/handoffs/2026-06-19-parallel-resume-run-control.md`。

## Fresh 验证

未执行真实 API。

```bash
uv run pytest tests/test_documentation_standards.py tests/test_main_cli.py tests/test_cost_calibration_smoke.py tests/test_prediction_runner.py tests/test_mem0_adapter.py tests/test_method_registry.py tests/test_config_profiles.py -q
# 119 passed in 10.54s

uv run pytest tests/test_documentation_standards.py -q
# 5 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0

git diff --check
# exit 0
```

## Git 准备情况

- 当前分支：`main`
- 远端：`origin https://github.com/buctzzp/AgentMemoryBench.git`
- 大文件检查：未发现待提交的 10MB 以上文件。
- `.gitignore` 已保护 `data/`、`models/`、`outputs/`、`third_party/benchmarks/`、`tmp/` 等大文件目录。
- 针对用户真实 HF token 和 OpenAI-like token 的窄扫描未命中；命中项仅为 README 示例 URL 和测试假 key。

## OpenCode 接手边界

OpenCode 现在是用户启用的正式外部推进通道，可以承担实质开发任务，不再只做机械任务。
但以下三项风险较高，OpenCode 修改后必须完整记录 diff、设计取舍和验证命令，Codex
恢复后必须逐项复核：

- Rich 并行终端展示：必须用离线 fake runner 测试多 child run 统一展示，不能只凭肉眼。
- 第三方 stdout/warning 捕获：必须保证不吞掉错误堆栈，stdout 应进入 run log 或 child log。
- prediction artifact 瘦身：必须保持 evaluator 可复用，不得删除已有 evaluator 依赖字段。

## 下一步建议

1. 先 commit/push 当前已验证 checkpoint，避免长时间不提交导致恢复困难。
2. 之后优先由 Codex 修 Rich 并行展示：
   - 禁用 child run Rich progress。
   - orchestrator 统一读取各 child `checkpoints/progress.json`。
   - 单个 Rich `Live(Table)` 展示 method、benchmark、status、stage、conv、question、elapsed、run_id、error。
   - 第三方 warning/stdout 暂时至少重定向到每个 child run 的 log。
3. artifact 瘦身和 category summary 可作为后续独立小任务。

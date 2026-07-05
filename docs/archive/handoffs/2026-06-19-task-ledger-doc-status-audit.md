# 2026-06-19 任务总账与文档状态审计交接

## 本轮目标

用户要求对 OpenCode 6.18 / 6.19 两份结果文档做二次验证，区分哪些问题已经解决、哪些
仍然打开，并把任务文档、交接文档和入口文档的状态同步到最新。

## 已完成

- 派发两个只读 subagent 分别审计：
  - `opencode/opencode_result-6.18.md`
  - `opencode/opencode_result-6.19.md`
- 主线程用当前代码和真实输出目录交叉核验关键结论：
  - `CalibrationProgressMonitor._resolve_progress_path()` 已支持 LongMemEval concrete
    variant child run。
  - `conversation_prompts.jsonl` 初版 artifact 瘦身代码存在。
  - evaluator `category_breakdown` 初版代码存在。
  - LongMemEval-S 三路 smoke 的 `progress.json` 均为 Completed。
  - LightMem LoCoMo full 已 Completed，1540/1540 questions。
  - A-Mem LoCoMo full 当前仍未完成，最新核验为 5/10 conversations、547/1540 questions。
  - Mem0 LoCoMo full 当前为实质失败，`conv-42` shape mismatch。
- 新增 `docs/task-ledger.md`：
  - 收敛当前 open / partially_closed / closed / superseded 状态。
  - 建立历史 handoff 与 OpenCode 日期文档状态索引。
  - 明确旧 OpenCode 文档不是当前事实来源，必须经过总账裁定。
- 更新：
  - `AGENTS.md`
  - `docs/current-roadmap.md`
  - `README.md`
  - `opencode/opencode_result.md`

## 当前未关闭重点

以 `docs/task-ledger.md` 为准，当前最重要 open 任务是：

1. LoCoMo LLM judge 并行化。
2. Mem0 LoCoMo official-full 并发失败诊断和策略决策。
3. A-Mem LoCoMo official-full 运行状态监控与后续 evaluate/resume。
4. isolated predict 中间进度上报。
5. 第三方 stdout / warning / tqdm 终端治理。
6. OpenCode 6.19 相关改动的完整回归与提交。
7. prediction artifact 瘦身长期兼容策略。
8. evaluator `correct_count` / category summary 语义收尾。

## 本轮验证命令

本轮准备运行：

```bash
uv run pytest tests/test_documentation_standards.py -q
git diff --check
```

如果后续继续编码 LoCoMo judge 并行化，应先补 `run_artifact_evaluation(max_workers=...)`
的离线测试，再改实现；不要直接调用真实 judge API。

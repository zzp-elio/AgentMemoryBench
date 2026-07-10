# 发给 actor：LongMemEval C5

C1-C4 已完成并由架构师验收（commits `dda4487`、`c3c5264`、`7a34087`、
`75eecda`），不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md` 的
**C5：一条离线全链路**；完成后停下——C5 是最后一个 actor 批次，之后由
架构师做最终冻结。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md`
   第 1、2 节和第 3 节的 C5
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **结构模板（照此模式做，几乎可平移）**：LoCoMo A6 的
   `tests/test_locomo_registered_prediction.py`——真实 registry + 真实数据
   切片 + `BenchmarkProbeProvider` + 文件内 fake answer client 的组织方式

不要改任何 src/ 生产代码（C1-C4 已冻；若链路要求改 generic runner 或
adapter，立即停工上报），不要调用真实 API，不要运行全量 pytest/compileall，
不要更新 README/roadmap/survey/frozen 文档。

本批只新增 `tests/test_longmemeval_registered_prediction.py`：

- 用真实 longmemeval benchmark registration、真实
  `data/longmemeval/longmemeval_s_cleaned.json`、真实 smoke policy/事件聚合/
  unified prompt/artifact writer/f1/longmemeval-recall evaluator；
- method 使用现有 `BenchmarkProbeProvider`，answer LLM 用文件内离线 fake，
  judge 不跑真实 API（judge 走 fake client 或只跑 f1+recall 的
  artifact-only 评估，二选一，选后者更省——judge parity 已由 C4 单测锁定）；
- 运行 smoke 默认口径：1 instance × 1 round × 1 question，断言实际为
  1 session/2 turns/1 question（C2 冻结形态）；
- 断言 probe 调用覆盖 ingest → end_session → end_conversation → retrieve；
- 断言 answer prompt 走 LongMemEval unified profile
  （`longmemeval_official_non_cot_rag_v1`），prompt 内含 `Current Date:`
  且 History Chats 槽位为 probe 的 formatted_memory 原文；
- artifact-only 跑 f1 与 longmemeval-recall；分数允许为 0，流程成功不要求
  答对；recall 对 probe 声明的 provenance 粒度给出非 N/A 结果（probe 声明
  什么粒度按 registry 现状断言，不改 probe）；
- 对 public questions、answer prompts 做通用私有键扫描；对 predictions 用
  gold/evidence/judge 窄化扫描（A6 先例）；重点断言
  `answer_session_ids`/`has_answer`/`evidence_turn_ids` 不出现在任何
  public artifact；
- 复跑既有三条 resume 契约测试（见下方命令），不新写 resume 逻辑。

完成后只运行一次：

```bash
uv run pytest -q tests/test_longmemeval_registered_prediction.py \
  tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed \
  tests/test_prediction_runner.py::test_resume_skips_completed_conversations_and_questions \
  tests/test_main_cli.py::test_predict_smoke_rejects_resume_and_retry_failed
```

通过后做一个本地 commit（不 push），只提交本批新测试文件，commit message：
`test(ws02.6): cover LongMemEval offline probe workflow`。

最后只回复：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。
遇到 plan 未覆盖的情况立即停工写断点，交回架构师裁决，不要自行发挥。

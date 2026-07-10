# 发给 actor：LoCoMo A6

T1-T3、A4、A5 已完成并由架构师验收，不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b0-b1-locomo.md` 的 **A6：一条
离线全链路 + 复用既有 resume 契约**；完成后停下。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b0-b1-locomo.md` 的第 1、2、4 节
4. `docs/reference/actor-handbook.md`
5. 现有测试入口：`tests/test_prediction_runner.py:1432-1487,1848-1878`

不要重新跑全量基线/数据扫描，不要启动 reviewer subagent，不要运行全量
pytest/compileall，不要更新 README/roadmap/survey/frozen 文档。

本批只新增 `tests/test_locomo_registered_prediction.py`：

- 用真实 LoCoMo benchmark registration、真实 `data/locomo/locomo10.json`、真实 smoke
  adapter/事件聚合/unified prompt/artifact writer/F1/recall evaluator；
- method 使用现有 `BenchmarkProbeProvider`，answer LLM 使用文件内离线 fake，零 API；
- 运行 1 conversation × 1 round × 1 question，断言实际为 2 turns/1 question；
- 断言 probe 调用覆盖 ingest → end_session → end_conversation → retrieve；
- 断言 answer prompt 是 LoCoMo unified profile，artifact 带
  `retrieval_query_top_k=10`，manifest method provenance=`turn`；
- artifact-only 跑 F1 与 recall；分数允许为 0，流程成功不要求答对；
- 对 public questions、answer prompts、predictions 做私有键扫描；
- 不新增 resume 实现或重复 resume 测试，只复跑 prompt 末尾列出的三条既有契约；
- 不测试/修改 standard runner cleanup；若链路要求修改 generic runner，立即停工上报。

完成后只运行一次：

```bash
uv run pytest -q tests/test_locomo_registered_prediction.py \
  tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed \
  tests/test_prediction_runner.py::test_resume_skips_completed_conversations_and_questions \
  tests/test_main_cli.py::test_predict_smoke_rejects_resume_and_retry_failed
```

通过后做一个本地 commit（不 push），只提交 A6 新测试，不带现有未提交文件，commit
message：`test(ws02.6): cover LoCoMo offline probe workflow`。

最后只回复：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。


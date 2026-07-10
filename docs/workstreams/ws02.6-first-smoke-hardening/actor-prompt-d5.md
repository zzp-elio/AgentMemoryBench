# 发给 actor：MemBench D5

D1-D4 已完成并由架构师验收（commits `a84440e`、`46f21bb`、`b33544d`、
`8fcec2e` + 验收修正），不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md` 的
**D5：离线全链路**；完成后停下——D5 是最后一个 actor 批次，之后由架构师
做最终冻结。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md`
   第 1、2 节（尤其 §2.5 路径覆盖）和第 3 节的 D5
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **结构模板（照此平移）**：`tests/test_longmemeval_registered_prediction.py`
   （B2 C5 已验收版：真实 registry + 真实数据切片 + `BenchmarkProbeProvider`
   + 文件内 fake answer client 的组织方式）

**禁改任何 src/ 生产代码**（D1-D4 已冻；若链路要求改 generic runner 或
adapter，立即停工上报）。不调用真实 API，不跑全量 pytest/compileall，不更新
README/roadmap/survey/frozen 文档。外部事实附"出处文件:行号"；负空间需求
完成报告附测试函数名清单。

本批只新增 `tests/test_membench_registered_prediction.py`：

- 用真实 membench registration、真实
  `data/membench/Membenchdata/data2test/0-10k/` 数据、真实 smoke policy/
  事件聚合/unified MCQ prompt/artifact writer/choice-accuracy +
  membench-recall evaluator；
- method 用现有 `BenchmarkProbeProvider`，answer LLM 用文件内离线 fake
  （fake 返回一个固定选项字母），零真实 API；
- 运行标准 smoke 口径（默认 = 4 源各 1 条 trajectory），断言：
  - **双人称路径都被真实执行**：4 个 conversation 分别来自 4 个源文件；
    第一人称 1 turn（=1 round，dict 合并单 Turn）、第三人称 2 turns；
    第三人称 LowLevel 那条的 turn_time **非空**（无冒号时间格式被 D2
    正则解析成功——这是路径覆盖的关键断言）；
  - probe 调用覆盖 ingest → end_session → end_conversation → retrieve；
  - answer prompt 走 MemBench unified MCQ profile（含四个选项行 +
    "only one corresponding letter"），`{memory}` 槽位 = probe 的
    formatted_memory 原文；
  - prediction_transform 生效（fake 输出被 normalize 成单字母或
    invalid_choice）；
  - artifact-only 跑 choice-accuracy 与 membench-recall；分数允许为 0，
    流程成功不要求答对；recall 对 probe 声明的 provenance 粒度给出
    非 N/A 结果（probe 声明什么按 registry 现状断言，不改 probe）；
  - category_breakdown 出现在 evaluation summary 且按 task_type 分组
    （用户要求：每类分开报告，冻结前必须有全链路证据）；
  - public questions / answer prompts 通用私有键扫描；predictions 用
    gold/evidence/judge 窄化扫描；重点断言 `answer`/`ground_truth`/
    `target_step_id` 不出现在任何 public artifact；
- 复跑三条既有 resume 契约测试（命令尾三条，同 B2 C5），不新写 resume
  逻辑。

完成后只运行一次：

```bash
uv run pytest -q tests/test_membench_registered_prediction.py \
  tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed \
  tests/test_prediction_runner.py::test_resume_skips_completed_conversations_and_questions \
  tests/test_main_cli.py::test_predict_smoke_rejects_resume_and_retry_failed
```

通过后做一个本地 commit（不 push），只提交本批新测试文件，commit message：
`test(ws02.6): cover MemBench offline probe workflow`。

最后只回复：commit hash、测试尾行、实际改动文件、负空间需求对应测试函数
名清单、是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况立即停工写断点，
交回架构师裁决，不要自行发挥。

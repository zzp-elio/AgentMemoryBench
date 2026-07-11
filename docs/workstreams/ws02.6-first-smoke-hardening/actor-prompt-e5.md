# 发给 actor：BEAM E5

E1-E4 已完成并由架构师验收（commits `56ee346`、`1ba7bb3`、`08a1299`、
`772602d` + 验收补强），不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md` 的
**E5：离线全链路**；完成后停下——E5 是最后一个 actor 批次，之后由架构师
做最终冻结。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md`
   第 1、2 节（尤其 §2.5 双结构认证语义）和第 3 节的 E5
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **结构模板（照此平移）**：`tests/test_membench_registered_prediction.py`
   （B3 D5 已验收版：真实 registry + 真实数据切片 + `BenchmarkProbeProvider`
   + 文件内 fake answer client）

**禁改任何 src/ 生产代码**（E1-E4 已冻；链路跑不通立即停工上报）。数据
一律 `data/BEAM/`。不调真实 API（judge/equivalence 全用 fake client），
不跑全量 pytest/compileall，不更新 README/roadmap/survey/frozen 文档。
外部事实附"出处文件:行号"；负空间需求附测试函数名清单。

本批只新增 `tests/test_beam_registered_prediction.py`：

- 用真实 beam registration、真实 arrow 数据、真实 smoke policy/事件聚合/
  unified prompt/artifact writer/beam-rubric-judge(fake client)/
  beam-recall/f1 evaluator；
- **双结构认证 = 两次独立 prepare/run**（架构师裁决）：
  - run A：`variant=100k` smoke（1 conv × 1 round × 1 题实际作答——
    数据集带 20 题、runner 预算裁 1 题，两者都断言）；
  - run B：`variant=10m` smoke（同口径；断言 10m 切片来自
    `p1:s1`、plan metadata 存在）；
- 每 run 断言：probe 生命周期顺序（ingest → end_session →
  end_conversation → retrieve）；answer prompt 走 BEAM unified profile
  且 formatted_memory 原文在 prompt 内；artifact-only 跑
  beam-rubric-judge（fake judge 返回固定 JSON 分数，含一次 0.5 以断言
  float 主分与 official_int 对照分并存）+ beam-recall（probe 声明 turn
  provenance → status=ok）+ f1；分数允许为 0，流程成功不要求答对；
- category_breakdown 出现在 evaluation summary 且按 ability 分组
  （用户要求：每类分开报告的全链路证据）；
- 三层 privacy 扫描：public questions / answer prompts 通用扫描；
  predictions 窄化扫描；重点断言 `rubric`/`ideal_response`/
  `ideal_summary`/`source_chat_ids`/`evidence_turn_ids` 零出现在任何
  public artifact；
- 复跑三条既有 resume 契约测试（同 B3 D5 命令尾）。

完成后只运行一次：

```bash
uv run pytest -q tests/test_beam_registered_prediction.py \
  tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed \
  tests/test_prediction_runner.py::test_resume_skips_completed_conversations_and_questions \
  tests/test_main_cli.py::test_predict_smoke_rejects_resume_and_retry_failed
```

通过后做一个本地 commit（不 push），只提交本批新测试文件，commit message：
`test(ws02.6): cover BEAM offline probe workflow (dual-structure)`。

最后只回复：commit hash、测试尾行、实际改动文件、负空间需求对应测试函数
名清单、是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况立即停工写断点，
交回架构师裁决，不要自行发挥。

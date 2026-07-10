# 发给 actor：LoCoMo A5

T1-T3 与 A4 已完成并由架构师验收，不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b0-b1-locomo.md` 的 **A5：LoCoMo
metric**；完成后停下，不要继续 A6。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b0-b1-locomo.md` 的第 1、2、4 节
4. `docs/reference/actor-handbook.md`
5. 官方 scorer：
   `third_party/benchmarks/locomo-main/task_eval/evaluation.py:75-145,189-241`
   与 `evaluation_stats.py:94-138`

不要重新跑全量基线/数据扫描，不要启动 reviewer subagent，不要运行全量
pytest/compileall，不要更新 README/roadmap/survey/frozen 文档，不要调用 judge API。

本批实现：

- 先用少量 golden vectors 核对现有 `LoCoMoF1Evaluator`；若已与官方一致，不重写它。
- 每条 answer prompt/retrieval artifact 写入实际 query `top_k` 和该次 provider 的
  `provenance_granularity`；不要为此扩写全局 method/benchmark manifest 装配。
- 新增离线 `locomo-recall` artifact evaluator 和 registry：
  - turn：取 top-k retrieved items 的 `source_turn_ids` 并集，对私有 evidence dia_id；
  - session：把 source/evidence 的 `D<n>:<turn>` 向上聚合到 `D<n>`；
  - none/未声明：summary 写结构化 N/A，不记 0 分；
  - 声明 turn/session 却缺 items/source ids/top_k：fail-fast；
  - empty evidence 按官方实现记 1.0，并另报数量与 non-empty-evidence mean；
  - 输出 overall、by-category、scored count、provenance level、requested top-k 分布。
- `locomo-judge` 只增加 `framework_auxiliary` /
  `framework_auxiliary_lightmem_reference_v1` 身份标记和离线测试；不调用 API。
- 不新增 BLEU，不改 smoke、prompt、resume、真实 method adapter 或其他 benchmark。

完成后只运行一次：

```bash
uv run pytest -q tests/test_locomo_answer_metrics.py \
  tests/test_locomo_retrieval_recall.py tests/test_evaluator_registry.py \
  tests/test_artifact_evaluation_runner.py tests/test_prediction_runner.py
```

通过后做一个本地 commit（不 push），只提交 A5 文件，不带现有未提交文档/A4 架构师
retouch，commit message：`feat(ws02.6): add LoCoMo retrieval recall contract`。

最后只回复：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。

# 发给 actor：MemBench D4

D1-D3 已完成并由架构师验收（commits `a84440e`、`46f21bb`、`b33544d` +
验收修正），不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md` 的
**D4：metric parity + conditional recall**；完成后停下，不要开始 D5。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md`
   第 1、2 节和第 3 节的 D4（含本卡末尾的架构师预裁决）
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. 一手事实源：
   - 官方判定路径：`third_party/benchmarks/Membench-main/benchmark/
     MembenchAgent.py:93-115`（json_schema 强制 enum A-D，
     `json.loads(res)['choice']`，与 ground_truth 字母精确比较）
   - 官方 step 基准：0 基（`load_test_data.py` 的 reverse_relocate_dict
     按 enumerate 构建；见 notes/membench-b3-audit.md "基准与越界根源"节）
6. 审计/施工对象：`src/memory_benchmark/evaluators/
   membench_choice_accuracy.py`、`benchmark_adapters/membench.py`
   （`_turn_from_step`:706、gold `evidence=`:779）
7. 结构模板：`evaluators/longmemeval_recall.py` +
   `tests/test_longmemeval_retrieval_recall.py`（conditional 契约平移）

**硬规矩**：外部事实附"出处文件:行号"且现场核实；负空间需求（报错/N/A/
不泄漏）完成报告附测试函数名清单；不碰 prompt/policy（D2/D3 已冻）、不改
其他 benchmark、不调用真实 API、不跑全量 pytest/compileall、不更新
README/roadmap/survey/frozen 文档。

## 架构师预裁决（off-by-one，照此实施，不要自行发挥）

架构师已实锤：公开 turn id = `str(step_index + 1)`（**1 基**，
`membench.py:706`），而 gold `evidence` 现存官方 **0 基** step id 原值
（`:779`）——两者不在同一 id 空间，直接匹配会系统性偏一位。裁决（沿用
LongMemEval C4 先例：匹配键=公开 id 空间，官方 id 只作对照记录）：

- `GoldAnswerInfo.evidence` 改存**公开 turn-id 空间**：
  `[str(step_id + 1) for step_id in target_step_ids]`；
- 官方 0 基原值保留在 `GoldAnswerInfo.metadata["target_step_id"]`
  （现已存在，别动）；
- 越界 step（0 基下 == len(message_list)，全库恰 2 例）映射后无对应公开
  turn → 保留在 evidence 中但 recall 侧记 unmatched-gold，不崩；
- 空 target_step_id（恰 1 例）→ evidence 为空 → recall 记 N/A + 单独计数；
- 断言 first/third 两种人称的 step→turn 映射一致（1 message/str = 1 turn
  = 1 step，+1 平移；若发现 adapter 有跳过空 step 导致错位的路径，停工
  上报）。

## 本批做三件事

1. **choice-accuracy 官方 parity 审计**：官方判定 = 结构化输出的字母与
   `ground_truth` 精确比较（enum 保证合法）。我们的
   `membench-choice-accuracy` 在此之上多了自由文本解析层（D3 已冻，别
   动解析器）；审计判分本体：解析成功 → 字母精确比较；解析失败
   （invalid_choice）→ 判错并在 details 记 `parse_failed=true`（可与
   官方口径分开统计）。按 task_type（category）分报由通用
   category_breakdown 承接（加断言）。
2. **gold evidence 空间修正**（按上方预裁决改 `membench.py:779` 一处 +
   相关测试）。
3. **新增 `membench-recall`**（`evaluators/membench_recall.py`，平移
   longmemeval_recall 的 conditional 契约）：method manifest 未声明
   provenance → N/A；声明却缺来源 → fail-fast；声明 turn 粒度 → 按公开
   turn-id 空间对 evidence 匹配；MemBench 单 session，session 粒度声明
   视同 conversation 级，记 N/A 并注明（数据无 session 结构可召回）。
   registry 注册 `cli_name="membench-recall"`、supported={"membench"}、
   requires_api=False。f1 注册面保持排除 membench（断言已有则不重复）。

完成后只运行一次：

```bash
uv run pytest -q tests/test_membench_choice_accuracy.py \
  tests/test_membench_retrieval_recall.py tests/test_evaluator_registry.py \
  tests/test_artifact_evaluation_runner.py tests/test_membench_conversation_adapter.py
```

（新文件无则新建；现有 choice-accuracy 测试在别的文件里就把该文件加进
命令一起跑。）

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): MemBench choice-accuracy parity + public-space evidence + conditional recall`。

最后只回复：commit hash、测试尾行、实际改动文件、负空间需求对应测试函数
名清单、是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况立即停工写断点，
交回架构师裁决，不要自行发挥。

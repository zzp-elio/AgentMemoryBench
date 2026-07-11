# 发给 actor：BEAM E4

E1-E3 已完成并由架构师验收（commits `56ee346`、`1ba7bb3`、`08a1299`），
不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md` 的
**E4：metric——rubric judge 10 类 parity + event_ordering 复合分 +
conditional recall**；完成后停下，不要开始 E5。本批是 B4 最重的一批，
宁停勿猜。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md`
   第 1、2 节（尤其 §2.3）和第 3 节的 E4（含 E1 裁决块的 id 映射）
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **官方事实源**：
   - `third_party/benchmarks/BEAM/src/evaluation/compute_metrics.py`
     （10 个 `evaluate_*`；`unified_llm_judge_base_prompt` 调用 :347；
     `score += int(response['score'])` :357；event_ordering τ×F1
     :270-308；语义匹配 `all-MiniLM-L6-v2` :85,249；fact-level 用
     `BAAI/bge-large-en-v1.5` :172）
   - `third_party/benchmarks/BEAM/src/prompts.py` 中
     `unified_llm_judge_base_prompt` 本体（逐字对照对象）
   - `third_party/benchmarks/BEAM/src/evaluation/run_evaluation.py:49-77`
     （10 类分发）
6. 审计对象：`src/memory_benchmark/evaluators/beam_rubric_judge.py`
   （364 行，自述"统一用 float 修正官方 int 截断 0.5 的 bug"）
7. 结构模板：conditional recall 平移
   `evaluators/longmemeval_recall.py`/`membench_recall.py`；fixture
   必须经真实 `evaluator_private_label_record`（B3 D5 固化规矩）

**硬规矩**：外部事实附"出处文件:行号"；负空间需求附测试函数名清单；judge
测试全用 fake client 零真实 API；嵌入计算若需真实模型，用项目本地缓存的
all-MiniLM（`models/` 或既有加载路径），测试里可用可控 fake 嵌入；不碰
prompt/policy/variant（E2/E3 已冻）、不改其他 benchmark、不跑全量
pytest/compileall、不更新 README/roadmap/survey/frozen 文档。

本批做四件事：

1. **rubric judge parity 审计**：
   - `unified_llm_judge_base_prompt` 逐字对照（运行时读官方文件断言）；
     确认 10 类是否共用同一 judge prompt、逐条 rubric 打分、
     `score/len(rubric)` 聚合——与现有 evaluator 逐项比对，偏差逐处
     修正或留档；
   - **int 截断裁定（一手核证）**：官方 `:357` 对 response['score'] 取
     int()。读 judge prompt 本体判定官方意图是 0/1 二值还是允许小数：
     若 0/1 二值 → int() 无损，现有 evaluator 的"float 修正"是**对不
     存在的 bug 的修正**，改回与官方一致并删除误导注释；若允许小数 →
     int() 确为截断，float 是合理已声明偏差，留档进冻结记录。**结论
     必须带 prompt 原文引用**，两个方向都不许猜；
   - judge 调用参数（temperature 等）从官方一手抄；judge 模型按项目
     基座 gpt-4o-mini（偏差照 B2 先例记录）。
2. **event_ordering 复合分**：官方 `event_ordering_score`（τ_b 归一化
   × F1，语义阈值 0.65，`:270-308`）在框架侧的实现/审计——若现有
   evaluator 未覆盖该类，新增（嵌入模型用 `all-MiniLM-L6-v2`，与官方
   相同且恰为项目统一基座，注释记录这一巧合；`BAAI/bge-large-en-v1.5`
   仅 fact-level 使用，是否纳入按官方 information_extraction 的实际
   调用链一手判定，不可考/过重则如实记录为已知限制交架构师裁决）；
   requires_api 与嵌入依赖在注册面如实声明。
3. **新增 `beam-recall`**（conditional，平移 B2/B3 契约）：匹配键 =
   gold `metadata["evidence_turn_ids"]`（E1 已收编的公开空间映射，含
   歧义 any-match）；method 声明 turn provenance 即评；未声明 → N/A；
   abstention（无 evidence）→ N/A + 计数；`'--'`/unmatched gold 单独
   计数；fixture 经真实序列化函数。
4. **断言收尾**：category_breakdown 按 10 类分报；`f1` 注册面已含 beam
   （补充指标语义，断言即可）。

完成后只运行一次：

```bash
uv run pytest -q tests/test_beam_rubric_judge.py tests/test_beam_recall.py \
  tests/test_evaluator_registry.py tests/test_artifact_evaluation_runner.py
```

（新文件无则新建；event_ordering 若单独成测试文件则一并加入命令。）

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): BEAM rubric-judge parity + event-ordering composite + conditional recall`。

最后只回复：commit hash、测试尾行、实际改动文件、**int 截断裁定结论
（一句 + prompt 原文关键句）**、负空间需求对应测试函数名清单、是否存在
plan 偏差/停工点。遇到 plan 未覆盖的情况立即停工写断点，交回架构师裁决，
不要自行发挥。

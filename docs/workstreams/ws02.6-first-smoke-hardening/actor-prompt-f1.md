# F1 卡：论文指标两缺口（longmemeval 检索排名指标 + membench 四格聚合）

> B6.1 批次，2026-07-12 架构师（Fable 5）开卡。**全部为加法**：两个新
> evaluator 注册，不改任何既有 evaluator/adapter/runner 行为。若发现
> 必须改冻结行为才能完成，立即停工写断点，不许静默改。

## 你要先读的（最少清单，按序）

1. `AGENTS.md`（硬规则总纲）
2. `docs/reference/actor-handbook.md`（上工流程、红线、停工条件、报告格式）
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b6-horizontal.md` §1
4. 本卡全文

背景一句话：五 benchmark 已全部 frozen-v1（全量基线 1058 passed），本卡
补两个论文报告了、框架还没实现的指标。你是本批唯一施工者；架构师负责
验收、全量回归与冻结，你不用跑全量。

## 施工纪律

- TDD；每个 task 一个 commit（一行英文 `feat:`/`test:` 前缀）；本地
  commit **不 push**。
- 零真实 API：新 evaluator 全部 `requires_api=False`，测试全离线。
- 不改 `third_party/`；不改任何既有 evaluator 的既有输出键；所有
  Python 文件中文 docstring。
- fixture 铁律（D4/D5 判例）：凡断言读取生产 artifact 的测试，fixture
  必须**经真实序列化函数/真实 evaluator 落盘**构造，不许手写 jsonl 字典。
- 遇本卡未覆盖情况：停工，写清证据（文件:行号）与候选方案，交回架构师。

## Task 1：`longmemeval-retrieval-rank`（官方检索排名指标）

### 官方事实（架构师 2026-07-12 一手复核，你开工时现场再核一遍行号）

- 公式源：`third_party/benchmarks/LongMemEval-main/src/retrieval/eval_utils.py`
  （**注意：plan-b6 §1 写的 `src/evaluation/` 是路径笔误，已勘误**）：
  - `dcg`（:4-9）：`rel[0] + Σ rel[i]/log2(i+1)`（1 基位置 2 起折损）；
  - `ndcg`（:12-21）：二值相关性（doc ∈ gold），`ideal_dcg==0 → 0.0`；
  - `evaluate_retrieval`（:24-29）：`recall_any`（任一 gold 命中 top-k）、
    `recall_all`（全部 gold 命中 top-k）、`ndcg_score`。
- 调用点 `src/retrieval/run_retrieval.py:316-321`：
  **k ∈ [1, 3, 5, 10, 30, 50]**，官方指标名逐字
  `recall_any@{k}` / `recall_all@{k}` / `ndcg_any@{k}`。
- abstention（`_abs`）题官方**排除不计**（`run_retrieval.py:389-408`
  `ignored_qs_abstention`）——与框架 C4 冻结的 recall N/A 裁决语义一致。
- `evaluate_retrieval_turn2session`（eval_utils.py:32-46）的 effective_k
  会**越过 top-k 继续向corpus 深处扩张**（:40-44），框架 artifact 只有
  top_k 条 → **artifact 不可算，不实现**，在 evaluator summary 记
  known limitation 字段（`turn2session_view: "not_artifact_computable"`）。

### 实现裁定（架构师已裁，照做）

1. **新文件** `src/memory_benchmark/evaluators/longmemeval_retrieval_rank.py`，
   新注册 `longmemeval-retrieval-rank`（metric_name
   `longmemeval_retrieval_rank`），artifact-only（实现
   `evaluate_run_artifacts`，模式照抄 `longmemeval_recall.py`——
   provenance granularity 读取、公开 id 空间匹配键、N/A payload、
   fail-fast 全部与它同构；**不改 `longmemeval_recall.py` 本体**）。
2. per-question 记录：对每个非 abstention 题，输出
   `{"recall_any@k": …, "recall_all@k": …, "ndcg_any@k": …}`，
   k 只取 `official_k = [1,3,5,10,30,50]` 中 **k ≤ 该题
   retrieval_query_top_k** 的值；k > top_k 的不算不报（官方对全
   corpus 排序，artifact 只有 top_k 条，硬算是下界不是官方口径），
   summary 记 `skipped_k_above_top_k`（列表）与计数。
3. ideal DCG 等价实现（免 corpus）：官方 ideal = 全 corpus 二值相关性
   降序 = `[1]*n_gold` 截断到 k → `ideal_dcg = dcg([1]*min(n_gold,k), k)`。
   在代码注释里写明这条等价推导及官方行号。
4. abstention 题：`score=None` + summary `abstention_excluded_count`
   （官方排除语义，引 run_retrieval.py:389-408）。非 abstention 但
   gold evidence 为空的题：跟随 `longmemeval_recall.py` 既有边界处理
   同款语义（开工时现场读它的实现并在测试锚死；官方 ndcg 此时返回
   0.0，如与既有语义不同，把官方差异记进 summary 字段
   `official_empty_gold_note`，**不改既有 evaluator**）。
5. summary：每个 k 的三指标均值（分母=参与题数）+ 参与/排除计数。
   命名逐字用官方 `recall_any@{k}` 形态。

### Task 1 测试（负空间清单，全部要有）

- `tests/test_longmemeval_retrieval_rank.py`（新文件）：
  - `test_ndcg_matches_official_formula_hand_computed`：合成 3 题
    fixture，**手算期望值写进断言注释**（架构师验收要独立复算）；
    至少覆盖 gold 全命中、部分命中、零命中三形态；
  - `test_recall_all_requires_every_gold_doc`（recall_any=1 而
    recall_all=0 的构造）；
  - `test_k_above_top_k_is_skipped_and_counted`；
  - `test_abstention_questions_excluded_with_count`；
  - `test_missing_provenance_returns_na_payload`（对齐
    longmemeval_recall 的 N/A 语义）；
  - fixture 经真实序列化函数构造（读 `longmemeval_recall.py` 现有
    测试怎么构造 prediction artifact，同款）。

## Task 2：`membench-source-accuracy`（论文四格聚合）

### 事实（架构师一手核证）

- 论文按 First/Third × High/Low 报四格；conversation_id 第一、二段
  就是这两维：`_conversation_id`（`membench.py:817-832`）=
  `{source_stream}-{level}-{question_type}-{scenario}-{tid}`，
  `source_stream ∈ {first, third}`、`level ∈ {high, low}`
  （`_source_profile_from_path`，membench.py:797-815；源文件名
  FirstAgent/ThirdAgent × HighLevel/LowLevel，四文件映射常量
  membench.py:121-124）。
- 既有 `membench-choice-accuracy` 是 per-question evaluator，run 级
  summary 由 `runners/evaluation.py:192-221` 通用生成（category 维度）；
  source 维度是另一维，**不许把 membench 专属解析塞进通用 runner**。

### 实现裁定（架构师已裁，照做）

1. **新文件** `src/memory_benchmark/evaluators/membench_source_accuracy.py`，
   新注册 `membench-source-accuracy`（metric_name
   `membench_source_accuracy`），**合成指标**：走
   `evaluate_run_artifacts` artifact-level 钩子（最新先例
   `halumem_memory_type.py`，8 个既有使用者，`runners/evaluation.py:86-96`），
   `requires_api=False`，读同 run 的 `membench-choice-accuracy`
   score artifact；上游缺失 fail-fast（照 halumem-memory-type 的报错
   形态）。
2. question → 四格键：优先从 score record 里既有的 conversation_id
   取；若 score record 没有该键，从同 run 的 prediction artifact
   （method_predictions.jsonl）join question_id → conversation_id
   （开工时现场核 score record 实形再定，两条路都在本裁定内，选实形
   支持的那条并在 docstring 写明）。四格键 = conversation_id 前两段
   `{source_stream}-{level}`；出现四格之外的前缀 → fail-fast 报
   conversation_id 原文（防静默吞错）。
3. summary：`source_breakdown` 四格各
   `{cell, question_count, correct_count, accuracy}` + 总计；四格
   固定顺序 first-high/first-low/third-high/third-low；某格 0 题时
   accuracy=None + 计数 0（0 分母契约，与 H4 一致）。

### Task 2 测试

- `tests/test_membench_source_accuracy.py`（新文件）：
  - `test_four_cells_aggregate_from_conversation_id_prefix`（fixture
    经真实 membench-choice-accuracy evaluator 跑分落盘，不手写
    score jsonl）；
  - `test_missing_upstream_artifact_fails_fast`；
  - `test_unknown_source_prefix_fails_fast`；
  - `test_empty_cell_reports_none_accuracy_with_zero_count`。

## Task 3：registry 注册 + 清单测试

两个新 metric 注册进 `evaluators/registry.py`，并把
`tests/test_evaluator_registry.py` 的全量 metric 清单断言加上
`longmemeval-retrieval-rank` 与 `membench-source-accuracy`
（H4 教训：新 metric 必撞该清单断言，这次直接一并改）。

## 唯一自检命令（只跑这一条，报告真实输出）

```bash
uv run pytest -q tests/test_longmemeval_retrieval_rank.py \
  tests/test_membench_source_accuracy.py \
  tests/test_evaluator_registry.py \
  tests/test_longmemeval_retrieval_recall.py \
  tests/test_membench_choice_accuracy.py
```

（后两个文件是"没碰坏既有行为"的哨兵。）全量回归由架构师验收时跑。

## 明确不做（防发散）

- 不实现 turn2session 视图（artifact 不可算，理由见 Task 1 官方事实）；
- 不改 `longmemeval_recall.py` / `membench_choice_accuracy.py` /
  通用 evaluation runner 的任何既有行为与输出键；
- 不做 locomo/beam/halumem 的任何事（它们论文指标已覆盖）；
- 不加 CLI 旗标；不动 configs/；不碰 judge（B6.2 已另行收口）。

## 停点

三个 task 完成 + 自检命令通过 + 三个 commit 就停，写报告（实际模型名
自查系统提示，别套池子里的名字），等架构师验收。

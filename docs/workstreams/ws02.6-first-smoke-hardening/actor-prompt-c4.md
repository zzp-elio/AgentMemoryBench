# 发给 actor：LongMemEval C4

C1-C3 已完成并由架构师验收（commits `dda4487`、`c3c5264`、`7a34087`），不要
重做。当前只执行 `docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md`
的 **C4：metric——judge parity 审计 + 通用 f1 + conditional recall**；完成后
停下，不要开始 C5。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md`
   第 1、2 节（尤其 §2.3 judge 契约、§2.5 决策）和第 3 节的 C4
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **官方事实源（prompt/参数必须从这里逐字核对，不许从 plan 转抄）**：
   `third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py`
   第 24-43 行（5 套 judge 模板）、第 101 行（`_abs` abstention 路由）、
   第 102-113 行（调用参数与 `'yes' in lower()` 解析）
6. 审计对象：`src/memory_benchmark/evaluators/longmemeval_judge.py`（已存在，
   现有测试在 `tests/test_llm_judge_parsing.py`、`tests/test_evaluator_registry.py`）
7. **结构模板**：conditional recall 照
   `src/memory_benchmark/evaluators/locomo_recall.py` +
   `tests/test_locomo_retrieval_recall.py`（A5 已验收的契约）；通用 f1 的
   normalize 参照 `evaluators/locomo_f1.py` 的 normalize_qa_answer 但**不含
   stemming、不含任何 category/benchmark 特判**

不要碰 adapter/prompt/policy（C1-C3 已冻），不要改 `locomo_f1.py`（官方
parity scorer 保持原样原名），不要改其他 benchmark 的 evaluator，不要调用
真实 API（judge 测试全用 fake client），不要运行全量 pytest/compileall，
不要更新 README/roadmap/survey/frozen 文档。

本批只做四件事：

1. **longmemeval-judge 官方 parity 审计**：逐字对照官方 5 套模板
   （single-session-user/assistant/multi-session 共用、temporal-reasoning
   容忍 off-by-one、knowledge-update、single-session-preference rubric、
   abstention）；abstention 必须由 `question_id` 含 `_abs` 路由；judge 调用
   role=user、n=1、temperature=0、max_tokens=10；label 解析
   `'yes' in response.lower()`。**与官方一致的部分不重写**；有偏差的逐处
   修正并在测试中钉死逐字断言。metric 聚合按 question_type 分报由通用
   `category_breakdown` 承接（加断言即可，勿新写聚合逻辑）。
2. **新增通用 `f1` evaluator**（新建 `src/memory_benchmark/evaluators/f1.py`）：
   标准 token-F1；normalize = 小写、去标点、去 `a/an/the/and` 冠词、空白
   压缩；**无 stemming、无多答案拆分、无 adversarial 规则、无任何
   benchmark/category 分支**。registry 注册 `cli_name="f1"`、
   `metric_name="f1"`、supported_benchmarks = 全部 conversation-QA 减
   membench（MCQ，B3 再议）、`requires_api=False`；MetricResult details 标
   `"framework_supplementary": true`（非官方口径，报告中不得冒充官方指标）。
3. **新增 artifact-level `longmemeval-recall`**
   （新建 `src/memory_benchmark/evaluators/longmemeval_recall.py`）：复用
   locomo_recall 的 conditional 契约——method manifest 未声明
   provenance → N/A；声明却缺来源 → fail-fast。**双粒度 gold 都提供**：
   session 粒度 gold = 私有 `answer_session_ids`；turn 粒度 gold = evidence
   session 内 `has_answer=True` 的 turn，turn id 用官方 corpus_id 约定
   `{session_id}_{turn_index+1}`（一手来源
   `third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:79`，
   turn index 从 1 起）。method 声明 turn 粒度按 turn 评、声明 session 按
   session 评。gold 数据只从 evaluator 私有 label artifact 读取，绝不进
   public 对象。
4. **abstention 题在 f1/recall 的处理**：`_abs` 题没有可召回的 gold
   evidence 语义（官方只判"是否识别为不可回答"）——recall 对 `_abs` 题记
   N/A 并单独计数；f1 照常计算但 details 标记 `abstention=true`。此处理
   写进测试。

直接相关测试：`tests/test_llm_judge_parsing.py`（judge parity 断言）、
新建 `tests/test_answer_f1.py`、新建 `tests/test_longmemeval_retrieval_recall.py`、
`tests/test_evaluator_registry.py`、`tests/test_artifact_evaluation_runner.py`
（按需最小增改）。

完成后只运行一次：

```bash
uv run pytest -q tests/test_llm_judge_parsing.py tests/test_answer_f1.py \
  tests/test_longmemeval_retrieval_recall.py tests/test_evaluator_registry.py \
  tests/test_artifact_evaluation_runner.py
```

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): LongMemEval judge parity + generic f1 + dual-granularity recall`。

最后只回复：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。
遇到 plan 未覆盖的情况立即停工写断点，交回架构师裁决，不要自行发挥。

# HaluMem 官方评测流程契约卡（frozen-v1，2026-07-11）

> 现行评测契约事实源之一，与 `ws02.6/notes/halumem-frozen-v1.md` 与
> 回归测试互为锚。全部行号 = `third_party/benchmarks/HaluMem-main/`
> 快照内实际调用点（签名默认值不作数）。旧调研版见 git 历史。

## 1. 交错语义（不可 2-phase）

官方 `eval/eval_memzero.py:148-256` `process_user`：ingest session →
提取评测 → 更新探针 → 该 session 的 QA → 下一 session，记忆累积。
框架用专属 operation-level runner 复刻（唯一使用者），scope
`is_generated_qa_session` session 只 ingest（官方评测端
evaluation.py:51-52 整体跳过）。

## 2. 三操作

- **提取探针**：ingest 后取 method 的 session 新增记忆
  （session_memory_reports），对每个 gold memory point 调 integrity
  judge，对每条候选记忆调 accuracy judge。
- **更新探针**：对每个 `is_update=="True"` 且 original_memories 非空
  的 gold point，以新 memory_content 为 query 检索，结果落 update_probe_records。
  canonical Mem0 wrapper 请求 `top_k=10`（eval_memzero.py:210-222），但 **10 不是 shared
  scorer 的硬公式**：Memobase 官方 wrapper 改用 `max_token_size=250`
  （eval_memobase.py:271-283），`evaluation.py:59-70,154-163` 只检查结果非空并拼接内容，
  不校验条目数。框架把 10 作为 Mem0-native 请求；其他 method 按其可证明的原生检索窗口
  运行并声明身份，不能在共享 runner 强截 items 或按行拆 opaque text。
  **路由（evaluation.py:59-70）：检索非空 → update 桶；空 → 归
  integrity、不进 update 分母**（框架同款；曾有双计 bug 已修，
  `skipped_empty_retrieval_count` 诊断）。
- **QA**：unified prompt = PROMPT_MEMZERO 逐字（2,104 字符，运行时
  AST parity 测试；官方五脚本两族语义，MEMZERO 为裁决 canonical，
  MEMOBASE 死代码）；无 question-time 槽（不注入）；answer LLM 官方
  未设采样参数 → API 默认（llms.py:25-34,60-69）。

## 3. metric 面（四 evaluator + 合成指标）

- 四套官方 judge prompt 逐字（integrity 2,568 / accuracy 4,891 /
  update 2,259 / QA 3,834 字符，eval_tools.py:4-283）+ 运行时 parity
  测试；judge LLM 框架统一 gpt-4o-mini（声明偏差）。
- 论文 12 主指标 + 官方 valid 分母/update Other 诊断字段，聚合公式
  与 evaluation.py:214-362 实际调用点一致；0 分母 None+显式计数。
- `halumem-memory-type` 合成指标：官方共享分母
  （evaluation.py:364-383）经 `evaluate_run_artifacts` 钩子读
  extraction+update 两份 scores artifact 合成，零 judge 调用，上游
  缺失 fail-fast；阶段内 per-type breakdown 另报（denominator_scope
  区分两口径）。
- QA category_breakdown 按六 question_type 分报。
- **retrieval recall = N/A**（evidence 无 turn id；冻结限制）。
- **update 检索窗口逐 method 声明**：有原生 top-k/limit 的 adapter 可执行 benchmark 请求；
  只有 token budget 或固定 readout 的保留原生窗口并标 framework-extended；没有可分离 retrieve
  的 method 仅 update=N/A，不能连带抹掉 extraction/QA 资格。

## 4. smoke / resume

固定形状零旋钮 smoke（首 conv 4 session × 2 turn × 1 题；一切 CLI
裁剪参数 fail-fast；验收口径 = 三操作运行时调用 ≥1 非聚合桶非空）；
resume：smoke 禁用、formal conversation 级、artifact-only 评测可
独立重跑。

## 5. 测试锚（关键）

`test_halumem_adapter.py`（真实 Medium 前缀分布锚 4×18/2/5）、
`test_halumem_unified_prompt.py`（MEMZERO AST parity）、
`test_halumem_judge_prompt_parity.py`（四套 judge AST parity）、
`test_halumem_evaluators.py`（聚合/0 分母/空检索路由/合成指标契约）、
`test_halumem_registered_prediction.py`（三操作 e2e/privacy/resume/
generated session 跳过）。

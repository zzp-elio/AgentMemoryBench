# LongMemEval Benchmark 调研卡片

更新日期：2026-07-16（retrieval gold/分母定点解冻；旧冻结记录见
`docs/workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-frozen-v1.md`，
逐文件来源锁见同目录 `longmemeval-source-lock.json`）

## 1. 定位与适用边界

LongMemEval 是面向 chat assistant 长期交互记忆的 conversation-QA benchmark，官方目标是测试信息抽取、多 session 推理、知识更新、时间推理和 abstention 五类长期记忆能力。证据：`third_party/benchmarks/LongMemEval-main/README.md:10`、`third_party/benchmarks/LongMemEval-main/README.md:21`。

每条 evaluation instance 是一个独立问题世界：系统先读完整 timestamped haystack history，再在所有 interaction sessions 之后回答一个问题。证据：`third_party/benchmarks/LongMemEval-main/README.md:30`、`third_party/benchmarks/LongMemEval-main/README.md:79`。

Phase 1 应把 LongMemEval 归入“长期对话问答 + LLM judge accuracy”类 benchmark；官方也提供 retrieval baseline，但主 QA 评分由 GPT-4o yes/no judge 判定 hypothesis 是否正确。证据：`third_party/benchmarks/LongMemEval-main/README.md:92`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:101`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:130`。

## 2. 数据结构与规模

官方数据包包含 `longmemeval_s_cleaned.json`、`longmemeval_m_cleaned.json` 和 `longmemeval_oracle.json`；本项目当前 canonical 数据为 `data/longmemeval/longmemeval_s_cleaned.json` 与 `data/longmemeval/longmemeval_m_cleaned.json`。证据：`third_party/benchmarks/LongMemEval-main/README.md:74`、`src/memory_benchmark/benchmark_adapters/longmemeval.py:32`。

官方 README 说明每个文件 500 个 evaluation instances；本地实测两个 cleaned variant 都是 500 条，字段均为 `question_id`、`question_type`、`question`、`answer`、`question_date`、`haystack_session_ids`、`haystack_dates`、`haystack_sessions`、`answer_session_ids`。证据：`third_party/benchmarks/LongMemEval-main/README.md:79`、本卡验收命令读取 `data/longmemeval/*.json`。

S/M variant 的成本差异主要来自 history 长度：官方称 S 约 115k tokens / 约 40 history sessions，M 约 500 sessions / 约 1.5M tokens；本地实测 S 为 38-62 sessions、396-616 turns，M 为 460-490 sessions、4,586-5,229 turns。证据：`third_party/benchmarks/LongMemEval-main/README.md:75`、论文 PDF `third_party/benchmarks/LongMemEval-main/Wu 等 - 2025 - LongMemEval Benchmarking Chat Assistants on Long-Term Interactive Memory.pdf:p.2`；本卡验收命令。

题型分布在 S/M 中一致：`knowledge-update` 78、`multi-session` 133、`single-session-assistant` 56、`single-session-preference` 30、`single-session-user` 70、`temporal-reasoning` 133；其中 30 条 question_id 以 `_abs` 结尾，对应 abstention。证据：本卡验收命令；官方 README 对 question_type 与 `_abs` 规则的定义见 `third_party/benchmarks/LongMemEval-main/README.md:81`。

私有边界：`answer`、`answer_session_ids` 和 turn 级 `has_answer` 是 evaluator / retrieval-eval 标签；method 不能看到这些私有标签。官方 README 说明 `has_answer` 用于 turn-level memory recall，`answer_session_ids` 用于 session-level memory recall；当前 adapter 已过滤 message metadata 中这些私有键。证据：`third_party/benchmarks/LongMemEval-main/README.md:87`、`third_party/benchmarks/LongMemEval-main/README.md:88`、`src/memory_benchmark/benchmark_adapters/longmemeval.py:47`、`src/memory_benchmark/benchmark_adapters/longmemeval.py:460`。

## 3. 官方评测流程

官方 QA 流程要求被测系统输出 JSONL，每行包含 `question_id` 和 `hypothesis`，再运行 `src/evaluation/evaluate_qa.py metric_model hyp_file ref_file`；脚本将每题写入 `autoeval_label` 并输出 overall accuracy 与按 question_type 的 accuracy。证据：`third_party/benchmarks/LongMemEval-main/README.md:92`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:46`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:114`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:130`。

官方 long-context / generation baseline 支持 `full-history-session`、retrieval log、history format、top-k 和 reading method；生成阶段会按 `question_date`、`question` 和 retrieved / full history 构造 prompt，然后用 reader LLM 生成 hypothesis。证据：`third_party/benchmarks/LongMemEval-main/README.md:170`、`third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:71`、`third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:280`。

官方 retrieval baseline 支持 `flat-bm25`、`flat-contriever`、`flat-stella`、`flat-gte` 和 `oracle`，粒度为 `turn` 或 `session`；retrieval 指标在 k=1/3/5/10/30/50 计算 recall_any、recall_all、ndcg_any。证据：`third_party/benchmarks/LongMemEval-main/README.md:190`、`third_party/benchmarks/LongMemEval-main/src/retrieval/run_retrieval.py:34`、`third_party/benchmarks/LongMemEval-main/src/retrieval/run_retrieval.py:316`。

当前 framework adapter 与官方流程对齐为：每条 instance 映射为一个 `Conversation`、一个公开 `Question`、一个私有 `GoldAnswerInfo`；`question_date` 映射到 `Question.question_time`，`question_type` 映射到 `Question.category`，`answer_session_ids` 只进入 gold evidence。证据：`src/memory_benchmark/benchmark_adapters/longmemeval.py:155`、`src/memory_benchmark/benchmark_adapters/longmemeval.py:179`、`src/memory_benchmark/benchmark_adapters/longmemeval.py:187`。

## 4. 指标与聚合

QA 主指标是 LLM judge accuracy：judge model 对每条 hypothesis 生成 yes/no，`yes` 记 1，`no` 记 0。证据：`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:101`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:113`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:127`。

官方聚合同时给 task-averaged accuracy、overall accuracy 和 abstention accuracy；`print_qa_metrics.py` 固定检查 judge model 为 `gpt-4o-2024-08-06`。证据：`third_party/benchmarks/LongMemEval-main/src/evaluation/print_qa_metrics.py:16`、`third_party/benchmarks/LongMemEval-main/src/evaluation/print_qa_metrics.py:20`、`third_party/benchmarks/LongMemEval-main/src/evaluation/print_qa_metrics.py:31`。

Retrieval 不是 answer 主指标，但已作为有资格门的补充评测接入。官方主 retrieval 路径只把
user-role turn 建入 corpus，并跳过 30 个 abstention + 51 个 non-abs no-user-target instance，
有效分母 419；`print_retrieval_metrics.py` 只剔 abstention 得 470，是已披露的 upstream
辅助脚本矛盾。证据：`third_party/benchmarks/LongMemEval-main/src/retrieval/run_retrieval.py:205-220,389-410`、
`third_party/benchmarks/LongMemEval-main/src/evaluation/print_retrieval_metrics.py:12`。

本项目 metric 注册与 2026-07-16 定点重开目标（`evaluators/registry.py`）：

- `longmemeval-judge`（主指标）：5 套 task 模板 + `_abs` abstention 路由与官方
  `get_anscheck_prompt()` **7/7 逐字 parity**（验收方式：直接 import 官方函数
  对比输出）；调用参数 temperature=0/max_tokens=10/role=user，解析
  `'yes' in lower()`。judge 模型按项目统一基座用 `gpt-4o-mini`，**与论文
  gpt-4o 有已声明偏差**（见 frozen-v1 known limitations）。
- `f1`（framework 补充指标，非官方口径）：跨 benchmark 标准 token F1，零
  特判，details 标 `framework_supplementary`；报告中不得冒充官方指标。
- `longmemeval-recall`（artifact-level conditional）：双粒度 gold 由 benchmark
  私有 evidence group 提供，先消费逐题 RetrievalEvidence；turn gold 只取 user-side
  `has_answer=True`，均无资格 → N/A；abstention/no-user-target 题按主路径 N/A。
  匹配键 = 公开 id 空间（session 公开 id / `{session_id}:t{raw_index}`），
  官方 `answer_session_ids` 与 corpus_id 别名只作对照记录
  （`GoldAnswerInfo.evidence` + `metadata`，通路 `storage/artifacts.py:74`）。

## 5. Answer / Judge Prompt 与运行参数

官方 judge prompt 按 task type 分支：common QA、temporal-reasoning、knowledge-update、single-session-preference 和 abstention 都有不同判定规则；temporal 允许天数 off-by-one，knowledge-update 允许回答包含旧信息但必须给出更新答案。证据：`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:24`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:29`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:32`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:40`。

官方 judge 支持 `gpt-4o-mini`、`gpt-4o` 和本地 `llama-3.1-70b-instruct`，其中官方 meta-evaluation 使用 GPT-4o judge；API 调用参数为 `temperature=0`、`max_tokens=10`。证据：`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:11`、`third_party/benchmarks/LongMemEval-main/src/evaluation/evaluate_qa.py:102`、`third_party/benchmarks/LongMemEval-main/Wu 等 - 2025 - LongMemEval Benchmarking Chat Assistants on Long-Term Interactive Memory.pdf:p.20`。

官方 generation prompt 把 history、`Current Date: {question_date}` 和 `Question: {question}` 放入 prompt；`run_generation.py` 的 reader 调用使用 `temperature=0`，默认 completion 长度为 direct 500 tokens 或 CoT 800 tokens。证据：`third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:55`、`third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:341`、`third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:366`。

【B2 C3 起已统一，上一段"method reader 分两类"的描述作废】现行契约：
LongMemEval 默认 `prompt_track="unified"`，所有 method 走同一 benchmark-owned
prompt（官方非-CoT 模板逐字，`benchmark_adapters/longmemeval_prompt.py`，来源
`run_generation.py:57`）；`formatted_memory` 原样代入 History Chats 槽位（框架
不重排、不截断、不拼 `### Session` 头）；`Current Date` = 公开 `question_date`。
answer LLM 跨 method 固定 `gpt-4o-mini`、role=user、temperature=0、
`max_tokens=500`（`config/settings.py`，来源 `run_generation.py:360-368`）。
native prompt 仅作 `--prompt-track native` 对照。

## 6. Method Adapter 接口需求

原生粒度是 `evaluation instance -> haystack session -> user/assistant turn -> single question`。`add(conversation)` 可以完整承载一个 instance 的历史，要求每个 question_id 对应独立 method state，避免不同用户/世界串扰。证据：`third_party/benchmarks/LongMemEval-main/README.md:79`、`src/memory_benchmark/benchmark_adapters/longmemeval.py:198`。

若未来引入 `add_turn(...)`，建议以 session 内真实 `user+assistant` pair 为最小增量写入粒度；LightMem 官方脚本和 Mem0 memory-benchmarks 都采用 pair-level chunk。证据：`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py:157`、`third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py:161`、`third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/run.py:96`。

必须保留 `session_time` / `question_time` 边界：时间推理和 relative time 都依赖 `question_date`，官方 prompt 明确放入 `Current Date`，当前 adapter 也将 `question_date` 映射到 `Question.question_time`。证据：`third_party/benchmarks/LongMemEval-main/README.md:84`、`third_party/benchmarks/LongMemEval-main/src/generation/run_generation.py:71`、`src/memory_benchmark/benchmark_adapters/longmemeval.py:183`。

成本画像：完整 S variant 是 500 conversation / 500 question；当前框架每题至少 1 次 method retrieve、1 次 framework answer LLM、1 次 LongMemEval judge LLM。method ingest 成本随 S/M history 长度和 method 机制剧烈变化。证据：`third_party/benchmarks/LongMemEval-main/README.md:79`、`src/memory_benchmark/evaluators/longmemeval_judge.py:117`。

本项目 1-conv cost pilot 已验证四个已接入 method 的 S variant official-full 极小运行：Mem0、MemoryOS、A-Mem、LightMem 均 completed 1/500 conversation、1/500 question，judge 均为 1/1 correct；单 conversation efficiency 显示 LightMem memory build 约 315K ms / memory-build 19 LLM calls，Mem0 约 2,876K ms / 277 memory LLM calls / 826 build embedding calls，MemoryOS 约 4,309K ms / 1,361 memory LLM calls / 914 build embedding calls，A-Mem 约 5,207K ms / 1,686 memory-build LLM calls。证据：`outputs/*-longmemeval-s-1conv-costpilot-20260622-s-cleaned/summaries/summary.json`、`outputs/*-longmemeval-s-1conv-costpilot-20260622-s-cleaned/summaries/summary.longmemeval_judge_accuracy.json`、`outputs/*-longmemeval-s-1conv-costpilot-20260622-s-cleaned/summaries/efficiency_overall.prediction.json`。

## 7. 未确认项

LongMemEval README 在 2025/09 标注 cleaned history sessions 更新，本地文件名已经是 cleaned，但 README 的格式说明仍混用 `longmemeval_s.json` / `longmemeval_m.json` 名称；Phase 1 文档应统一称 `s_cleaned` / `m_cleaned`，并保留“官方原名”映射。证据：`third_party/benchmarks/LongMemEval-main/README.md:15`、`third_party/benchmarks/LongMemEval-main/README.md:75`、`src/memory_benchmark/benchmark_adapters/longmemeval.py:34`。

【2026-07-16 定点重开】retrieval recall 的 conditional 方向保留，但旧 adapter
role-agnostic 收集 `has_answer`，多收 54 个 assistant-side target，且未实现 51 题
no-user-target 剔除；必须随 evidence-group/M1 修复后才能恢复 parity。benchmark 双粒度 gold
应为：turn 级 **user-role** `has_answer` → private `evidence_groups`，session 级
`answer_session_ids` → `evidence_session_public_ids`；method 逐题 provenance 资格不成立就记
N/A，无需强制所有 method 支持。官方 recall_all/ndcg_any 及 k30/50 要在 depth 门关闭后再接。
证据：`src/memory_benchmark/evaluators/longmemeval_recall.py`、
`third_party/benchmarks/LongMemEval-main/README.md:87`。

M variant 对全量运行成本影响极高：官方称约 500 sessions / 1.5M tokens，本地实测每条 460-490 sessions；现有 1-conv cost pilot 只覆盖 S variant，不能直接外推 M 的成本。证据：`third_party/benchmarks/LongMemEval-main/README.md:76`、本卡验收命令、`docs/archive/status/2026-07-04-task-ledger.md:52`。

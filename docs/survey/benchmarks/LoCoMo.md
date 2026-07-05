# LoCoMo Benchmark 调研卡片

更新日期：2026-07-05

## 1. 定位与适用边界

LoCoMo 是面向长期双人、多 session、多天跨度对话记忆的 QA benchmark，主任务要求系统先消化整段 conversation，再对每个问题输出短答案；官方仓库同时说明还有 event summarization 和 multimodal-dialog-generation 任务，但当前可运行 QA 代码是 Phase 1 最直接可接入的协议。证据：`third_party/benchmarks/locomo-main/README.MD:8`、`third_party/benchmarks/locomo-main/README.MD:53`、`third_party/benchmarks/locomo-main/task_eval/evaluate_qa.py:67`。

Phase 1 应把 LoCoMo 归入“长期对话问答 + 可选 evidence recall”类 benchmark，而不是纯检索 benchmark：memory method 的输出会进入统一 reader，最终由 answer F1 体现下游 QA 效果；如果 method 能返回 context id，还可对齐官方 RAG 的 evidence recall 口径。证据：`third_party/benchmarks/locomo-main/task_eval/evaluation.py:228`、`third_party/benchmarks/locomo-main/task_eval/evaluate_qa.py:99`、`third_party/benchmarks/locomo-main/task_eval/evaluation_stats.py:127`。

## 2. 数据结构与规模

本地 Phase 1 使用 `data/locomo/locomo10.json`，顶层为 10 个 conversation sample，总计 1,986 个 QA；类别分布为 category 1: 282、category 2: 321、category 3: 96、category 4: 841、category 5: 446。证据：本卡验收命令读取 `data/locomo/locomo10.json` 的 `qa[*].category` 字段；论文附录页列出同样的五类数量和总数：`third_party/benchmarks/locomo-main/static/paper/locomo.pdf:p.15`。

每个 sample 的稳定字段为 `sample_id`、`conversation`、`qa`、`event_summary`、`observation`、`session_summary`；`conversation` 内含 `speaker_a`、`speaker_b`、`session_<n>_date_time` 与 `session_<n>`，turn 内含 `speaker`、`dia_id`、`text`，可选图片字段含 `img_url`、`blip_caption`、`query`。证据：`third_party/benchmarks/locomo-main/README.MD:12`、`third_party/benchmarks/locomo-main/README.MD:17`；本地数据字段由验收命令枚举。

本地 10 个 sample 的 session 数分布为 19、25、28、29、30、31、32，单 conversation turn 数范围为 369-689；示例 `conv-26` 有 19 个 session、419 个 turn，`session_1_date_time` 为 `1:56 pm on 8 May, 2023`。证据：本卡验收命令读取 `conversation.session_*` 与 turn 列表长度。

隐私边界：method 可见 conversation、session 时间、speaker、turn 文本和图片 caption；`qa.answer` 与 `qa.evidence` 必须只给 evaluator。当前 adapter 已把公开 `Question` 与私有 `GoldAnswerInfo` 分离。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:167`、`src/memory_benchmark/benchmark_adapters/locomo.py:216`。

## 3. 官方评测流程

官方 QA 主流程是：读取 `data_file`，按模型生成每个 sample 的 QA prediction，调用 `eval_question_answering` 写回每题 F1 / recall，再调用 `analyze_aggr_acc` 汇总 category 与 overall 分数。证据：`third_party/benchmarks/locomo-main/task_eval/evaluate_qa.py:67`、`third_party/benchmarks/locomo-main/task_eval/evaluate_qa.py:98`、`third_party/benchmarks/locomo-main/task_eval/evaluate_qa.py:112`。

非 RAG GPT 流程把 conversation 拼进上下文窗口，并按 `batch_size` 批量回答；官方脚本对 `gpt-4-turbo` 使用 `--batch-size 20`，对 `gpt-3.5-turbo-*` 使用 `--batch-size 10`。证据：`third_party/benchmarks/locomo-main/scripts/evaluate_gpts.sh:4`、`third_party/benchmarks/locomo-main/scripts/evaluate_gpts.sh:13`。

RAG 流程要求 `batch_size == 1`，先把 dialog / observation / summary 建库并嵌入，再按问题向量取 top-k context；官方脚本对 dialog 和 observation 使用 top-k 5/10/25/50，对 summary 使用 top-k 2/5/10。证据：`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:218`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:266`、`third_party/benchmarks/locomo-main/scripts/evaluate_rag_gpts.sh:7`、`third_party/benchmarks/locomo-main/scripts/evaluate_rag_gpts.sh:23`。

当前 framework adapter 与官方流程的主要形变：当前 `load_dataset` 从 `data/locomo/locomo10.json` 构建统一 `Dataset`；category 5 adversarial 问题被跳过，完整 1,986 QA 在当前 adapter 中会变为 1,540 个非 adversarial QA；smoke 会按 turn 截断并只保留 evidence 被覆盖的问题。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:36`、`src/memory_benchmark/benchmark_adapters/locomo.py:177`、`src/memory_benchmark/benchmark_adapters/locomo.py:259`、`src/memory_benchmark/benchmark_adapters/locomo.py:343`。

## 4. 指标与聚合

LoCoMo QA 官方主指标是 answer prediction F1；论文表格同时报告 RAG 的 recall@k，且说明 QA 结果基于 F1、RAG 结果基于 F1 与 recall@k。证据：`third_party/benchmarks/locomo-main/static/paper/locomo.pdf:p.7`、`third_party/benchmarks/locomo-main/task_eval/evaluate_qa.py:101`。

F1 计算会先去逗号、去标点、转小写、去 `a|an|the|and`，再做 Porter stemming 和 token overlap F1。证据：`third_party/benchmarks/locomo-main/task_eval/evaluation.py:75`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:126`。

category 2 temporal、category 3 open-domain、category 4 single-hop 使用普通 F1；category 3 的 gold answer 会先按分号截断；category 1 multi-hop 先用逗号拆分 prediction 和 gold，再对每个 gold 取最大子答案 F1 的均值；category 5 adversarial 只检查输出是否包含 `no information available` 或 `not mentioned`。证据：`third_party/benchmarks/locomo-main/task_eval/evaluation.py:203`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:209`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:213`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:217`。

官方汇总顺序为 `[4, 1, 2, 3, 5]`，对应 single-hop、multi-hop、temporal、open-domain、adversarial，并输出 overall accuracy；RAG 模式额外输出每类 recall 和 overall recall。证据：`third_party/benchmarks/locomo-main/task_eval/evaluation_stats.py:94`、`third_party/benchmarks/locomo-main/task_eval/evaluation_stats.py:98`、`third_party/benchmarks/locomo-main/task_eval/evaluation_stats.py:127`。

## 5. Answer / Judge Prompt 与运行参数

官方 GPT answer prompt 要求短语式答案，并尽量使用上下文原词；批量 prompt 要求输出 JSON dict。证据：`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:25`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:42`。

category 2 问题会额外追加 “Use DATE of CONVERSATION...” 的日期提示；category 5 会把 gold answer 和 “Not mentioned in the conversation” 随机排列成二选一选项，这与普通 QA 存在协议差异。证据：`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:243`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:245`。

官方 GPT 生成使用 `temperature=0`；单题请求 `num_tokens_request=32`，批量请求按 `batch_size * PER_QA_TOKEN_BUDGET`，其中 `PER_QA_TOKEN_BUDGET = 50`。证据：`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:23`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:286`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:309`。

未在官方 QA 主流程中发现独立 LLM-as-judge：`evaluate_qa.py` 直接调用 deterministic `eval_question_answering`，后者按 token F1 / adversarial 字符串规则计分；event summarization 论文部分使用 FactScore，但 README 标注 event summarization 代码仍为 coming soon。证据：`third_party/benchmarks/locomo-main/task_eval/evaluate_qa.py:99`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:189`、`third_party/benchmarks/locomo-main/README.MD:96`、`third_party/benchmarks/locomo-main/static/paper/locomo.pdf:p.6`。

## 6. Method Adapter 接口需求

原生粒度是 `conversation -> session -> turn -> question`。`add(conversation)` 能一次性传入完整历史，当前 adapter 已按 sample 构造 `Conversation`，并把 session 时间、turn id、speaker、图片 caption/URL 转成统一模型；这适合 retrieve-first 主协议。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:94`、`src/memory_benchmark/benchmark_adapters/locomo.py:134`、`src/memory_benchmark/benchmark_adapters/locomo.py:448`。

若未来引入 `add_turn(...)`，LoCoMo 应按原始 session/turn 时间顺序调用：每个 turn 至少传 `conversation_id`、`session_id`、`session_time`、`turn_id/dia_id`、`speaker`、`text`、可选图片 caption；session 边界需要保留，因为 temporal 题依赖 `session_<n>_date_time`，RAG recall 也可能按 dialog id 或 session id 对齐。证据：`third_party/benchmarks/locomo-main/README.MD:15`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:88`、`third_party/benchmarks/locomo-main/task_eval/evaluation.py:228`。

查询阶段应只传 `Question.question_text` 与公开 metadata；不得把 `answer`、`evidence` 交给 method。官方 category 5 prompt 会使用 gold answer 形成二选一选项，因此当前 adapter 跳过 category 5 是一种防止 reader 侧协议污染 method 接入的形变，但会使 Phase 1 分数不可直接等同官方 1,986 QA 总分。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:181`、`src/memory_benchmark/benchmark_adapters/locomo.py:216`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:245`。

成本画像：完整当前 adapter 口径为 1,540 个非 adversarial 问题，每题至少一次 reader LLM 调用；method 侧成本取决于 `add(conversation)` 的 ingest 和 `retrieve(question)` 的检索。官方 RAG 口径还包含建库 context embeddings、question embeddings 和每题 answer LLM；非 RAG 官方批量模式会减少 answer 调用次数，但把更长上下文塞给 reader。证据：本卡验收命令的 category 5 差值；`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:97`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:122`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:225`。

## 7. 未确认项

官方论文/网页把 LoCoMo 描述为 QA、event summarization、multimodal-dialog-generation 三任务，但仓库 README 对 event summarization 和 multimodal-dialog-generation 仍写 `Coming soon!`；Phase 1 若只接 QA，应在 benchmark variant 名或 README 中明确不覆盖 event summary。证据：`third_party/benchmarks/locomo-main/README.MD:96`、`third_party/benchmarks/locomo-main/README.MD:100`。

B0 plan 要求澄清 “F1 与 LLM judge 两套 metric 的官方定义”，但本次在 QA 主流程只找到 F1 与 RAG recall，没有找到 QA 的独立 LLM judge；FactScore 属于 event summarization 论文指标，不等于 QA judge。需要架构师确认 Phase 1 文档是否应把 LoCoMo QA 的第二指标表述为 `recall@k`，而不是 LLM judge。证据：`third_party/benchmarks/locomo-main/task_eval/evaluation.py:189`、`third_party/benchmarks/locomo-main/task_eval/evaluation_stats.py:127`、`third_party/benchmarks/locomo-main/static/paper/locomo.pdf:p.9`。

当前 adapter 跳过 category 5 是合理的隐私/协议折中，但如果后续要复现官方 adversarial 分数，需要单独设计 reader-only 的 category 5 二选一 prompt，且保证 gold answer 仍不可达 method。证据：`src/memory_benchmark/benchmark_adapters/locomo.py:177`、`third_party/benchmarks/locomo-main/task_eval/gpt_utils.py:245`。

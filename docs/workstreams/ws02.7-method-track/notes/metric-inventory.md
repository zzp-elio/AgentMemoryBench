# MX-1 指标盘点

> 取证日：2026-07-13。范围仅为 `metric-extension-plan.md` §2 的第一步盘点，
> 不包含指标匹配、优先级或新增建议。注册面以 `_REGISTRATIONS` 的完整字典为边界
> （`src/memory_benchmark/evaluators/registry.py:239-402`）。

## 口径说明

- 表 A 的“metric 名”同时列 CLI 名与 artifact `metric_name`，二者都来自注册项
  （`src/memory_benchmark/evaluators/registry.py:239-402`）。
- tier 有三种证据强度：代码显式写 `metric_tier`；artifact 用
  `framework_supplementary=true` 等价标记；或 frozen note 明确把官方 parity 面 / 补充面
  分层。表中会注明证据类型。没有任何一种证据时写“来源待溯”，不从名称猜测
  （`docs/reference/metric-extension-plan.md:8-15`）。
- 表 B 的“已实现”只表示 evaluator 已在统一 registry 注册，不表示任意 method 都有
  provenance 或可得到非 N/A 分数（`src/memory_benchmark/evaluators/registry.py:405-419`）。

## 表 A：框架已注册 evaluator 面

| metric 名（CLI → artifact） | supported_benchmarks | requires_api | metric_tier | 一句话语义 | 实现锚 |
|---|---|---:|---|---|---|
| `beam-recall` → `beam_recall`（`registry.py:240-249`） | `beam`（`registry.py:243`） | false（`registry.py:244`） | `framework_supplementary`（代码明写 supplementary 来源及 artifact 标记，`beam_recall.py:15-19,105-112`） | 有 turn provenance 时按 gold evidence any-match 计算 requested-k recall，否则 N/A（`beam_recall.py:28-38,95-112`） | `src/memory_benchmark/evaluators/beam_recall.py:12-19,21-38` |
| `beam-rubric-judge` → `beam_rubric_judge`（`registry.py:250-259`） | `beam`（`registry.py:253`） | true（`registry.py:254`） | `official_parity`（frozen note 将其列入官方有效面，`beam-frozen-v1.md` §5，`:48-56`；artifact 未显式写 `metric_tier`） | 九类逐 rubric LLM judge；event_ordering 另做语义对齐后的 τ-b×F1（`beam_rubric_judge.py:1-5,144-149`） | `src/memory_benchmark/evaluators/beam_rubric_judge.py:144-149,235-274` |
| `halumem-extraction` → `halumem_extraction`（`registry.py:260-269`） | `halumem`（`registry.py:263`） | true（`registry.py:264`） | `official_parity`（frozen note 明确 12 项全实现，`halumem-frozen-v1.md` §5，`:67-78`；artifact 未显式写 `metric_tier`） | 用 integrity/accuracy 两套 judge 聚合 extraction 的 R、加权 R、P、Accuracy、FMR、F1（`halumem_extraction.py:28-35,277-320`） | `src/memory_benchmark/evaluators/halumem_extraction.py:28-44,277-320` |
| `halumem-memory-type` → `halumem_memory_type`（`registry.py:270-279`） | `halumem`（`registry.py:273`） | false（`registry.py:274`） | `official_parity`（官方共享分母合成面，`halumem-frozen-v1.md` §5，`:75-79`；artifact 未显式写 `metric_tier`） | 从 extraction+update 两份 score artifact 按官方共享分母合成 memory_type 准确率（`halumem_memory_type.py:13-17,28-60`） | `src/memory_benchmark/evaluators/halumem_memory_type.py:13-26,28-60` |
| `halumem-update` → `halumem_update`（`registry.py:280-289`） | `halumem`（`registry.py:283`） | true（`registry.py:284`） | `official_parity`（frozen note 明确 12 项全实现，`halumem-frozen-v1.md` §5，`:67-78`；artifact 未显式写 `metric_tier`） | judge 更新为 Correct/Hallucination/Omission/Other 并按官方空检索路由聚合（`halumem_update.py:24-38,65-101`） | `src/memory_benchmark/evaluators/halumem_update.py:24-38,65-101` |
| `halumem-qa` → `halumem_qa`（`registry.py:290-299`） | `halumem`（`registry.py:293`） | true（`registry.py:294`） | `official_parity`（frozen note 明确 12 项全实现，`halumem-frozen-v1.md` §5，`:67-80`；artifact 未显式写 `metric_tier`） | 用官方 QA judge 分 Correct/Hallucination/Omission，并按六种 question_type 分报（`halumem_qa.py:21-35,64-107`） | `src/memory_benchmark/evaluators/halumem_qa.py:21-35,64-107` |
| `f1` → `f1`（`registry.py:300-311`） | `beam, halumem, locomo, longmemeval`（`registry.py:303-305`） | false（`registry.py:306`） | `framework_supplementary`（artifact 明写 `framework_supplementary=true`，`f1.py:44-64`） | 无 benchmark/category 特判的标准归一化 token-overlap F1（`f1.py:17-28,30-42`） | `src/memory_benchmark/evaluators/f1.py:17-28,30-64` |
| `locomo-f1` → `locomo_f1`（`registry.py:312-321`） | `locomo`（`registry.py:315`） | false（`registry.py:316`） | `official_parity`（frozen note 明写官方 scorer parity，`locomo-frozen-v1.md` §5，`:63`；artifact 未显式写 `metric_tier`） | 复刻 LoCoMo 官方按 category 分支的 answer-level QA F1（`locomo_f1.py:1-6,32-50`） | `src/memory_benchmark/evaluators/locomo_f1.py:1-6,32-50` |
| `locomo-judge` → `locomo_judge_accuracy`（`registry.py:322-331`） | `locomo`（`registry.py:325`） | true（`registry.py:326`） | `framework_auxiliary`（代码字段与 artifact 字段，`locomo_judge.py:58-63,160-181`） | 以 LightMem 的 LoCoMo accuracy prompt 做二元 LLM judge，非 LoCoMo 官方主指标（`locomo_judge.py:52-63`） | `src/memory_benchmark/evaluators/locomo_judge.py:52-63,153-183` |
| `longmemeval-judge` → `longmemeval_judge_accuracy`（`registry.py:332-341`） | `longmemeval`（`registry.py:335`） | true（`registry.py:336`） | `official_parity`（plan 将其列为该 tier 示例，`metric-extension-plan.md:13`；frozen parity 锚 `longmemeval-frozen-v1.md` §5，`:59-61`；artifact 未显式写字段） | 按五类 task/abstention 官方 prompt 路由，把 judge 回答解析为二元正确性（`longmemeval_judge.py:22-54,75-87`） | `src/memory_benchmark/evaluators/longmemeval_judge.py:22-54,75-87` |
| `longmemeval-recall` → `longmemeval_recall`（`registry.py:342-351`） | `longmemeval`（`registry.py:345`） | false（`registry.py:346`） | `framework_supplementary`（artifact summary 明写，`longmemeval_recall.py:303-320`） | 按声明的 turn/session provenance 算单一 requested-k recall，abstention N/A（`longmemeval_recall.py:15-30,61-129`） | `src/memory_benchmark/evaluators/longmemeval_recall.py:15-30,61-129` |
| `longmemeval-retrieval-rank` → `longmemeval_retrieval_rank`（`registry.py:352-361`） | `longmemeval`（`registry.py:355`） | false（`registry.py:356`） | `official_parity`（frozen note 记公式与官方 3000 例零失配，`longmemeval-frozen-v1.md` §7，`:106-117`；artifact 未显式写 `metric_tier`） | 在官方 k=[1,3,5,10,30,50] 上算 recall_any、recall_all、ndcg_any（`longmemeval_retrieval_rank.py:13-19,88-116`） | `src/memory_benchmark/evaluators/longmemeval_retrieval_rank.py:13-28,88-116,153-171` |
| `membench-choice-accuracy` → `membench_choice_accuracy`（`registry.py:362-371`） | `membench`（`registry.py:365`） | false（`registry.py:366`） | `official_parity`（plan 将其列为该 tier 示例，`metric-extension-plan.md:13`；frozen 主指标锚 `membench-frozen-v1.md` §5，`:78-80`；artifact 未显式写字段） | 将解析后的 A-D 与 ground_truth 精确比较，解析失败计错并打标（`membench_choice_accuracy.py:14-25,36-60`） | `src/memory_benchmark/evaluators/membench_choice_accuracy.py:14-25,36-60` |
| `membench-recall` → `membench_recall`（`registry.py:372-381`） | `membench`（`registry.py:375`） | false（`registry.py:376`） | **来源待溯**：实现与 frozen note 均未写 `metric_tier`/supplementary flag（`membench_recall.py:17-33`；`membench-frozen-v1.md` §5，`:81-84`） | turn provenance 下按公开 id 算 conditional recall；session/none 为 N/A（`membench_recall.py:17-33,35-60`） | `src/memory_benchmark/evaluators/membench_recall.py:17-33,35-60` |
| `membench-source-accuracy` → `membench_source_accuracy`（`registry.py:382-391`） | `membench`（`registry.py:385`） | false（`registry.py:386`） | `official_parity`（模块明写论文四格并锚官方聚合源，`membench_source_accuracy.py:1,54-66`；artifact 未显式写 `metric_tier`） | 从 choice score 聚合 First/Third × High/Low 四格及总准确率（`membench_source_accuracy.py:11-26,35-65`） | `src/memory_benchmark/evaluators/membench_source_accuracy.py:11-26,35-65` |
| `locomo-recall` → `locomo_recall`（`registry.py:392-401`） | `locomo`（`registry.py:395`） | false（`registry.py:396`） | `official_parity`（实现明确复刻官方 dia_id recall，`locomo_recall.py:1-7,202-217`；artifact 未显式写 `metric_tier`） | 按 turn/session provenance 对官方 evidence id 算条件式 retrieval recall（`locomo_recall.py:9-16,28-36`） | `src/memory_benchmark/evaluators/locomo_recall.py:1-16,28-36,202-217` |

## 表 B：五 benchmark 官方指标面

“官方死代码 / 不接”只抄 frozen note 已核证结论；没有记载时写“未记载”，不回查猜测。
HaluMem 的 12 项名称来自 frozen note 所指的一手覆盖清单
（`halumem-h1-audit.md` §5，`:96-120`），其 frozen note 确认 12 项全实现
（`halumem-frozen-v1.md` §5，`:67-80`）。

| benchmark | 答案形态 | 官方指标 | 我们是否已实现（表 A 对应） | 官方死代码 / 不接名单 |
|---|---|---|---|---|
| LoCoMo（`locomo-frozen-v1.md` §5，`:58-67`） | short-phrase QA（`locomo-frozen-v1.md` §5，`:60-61`） | QA F1（`locomo-frozen-v1.md` §5，`:63`） | 是：`locomo-f1`（`registry.py:312-321`） | BLEU-1 不属于 LoCoMo QA，不接入（`locomo-frozen-v1.md` §5，`:67`） |
| LoCoMo（`locomo-frozen-v1.md` §5，`:58-67`） | short-phrase QA 的检索证据面（`locomo-frozen-v1.md` §5，`:60-65`） | dia_id retrieval recall（`locomo_recall.py:1-7,202-217`） | 是：`locomo-recall`（`registry.py:392-401`） | BLEU-1 不属于 LoCoMo QA，不接入（`locomo-frozen-v1.md` §5，`:67`） |
| LongMemEval（`longmemeval-frozen-v1.md` §5，`:53-66`） | conversation short-answer QA，含 abstention（`longmemeval-frozen-v1.md` §5，`:55-66`） | 官方 QA judge accuracy（`longmemeval-frozen-v1.md` §5，`:59-61`） | 是：`longmemeval-judge`（`registry.py:332-341`） | frozen §5 未记载官方死代码（`longmemeval-frozen-v1.md` §5，`:53-66`） |
| LongMemEval（`longmemeval-frozen-v1.md` §7，`:106-117`） | conversation QA 的 ranked retrieval 面（`longmemeval-frozen-v1.md` §7，`:106-117`） | recall_any@k / recall_all@k / ndcg_any@k，k=[1,3,5,10,30,50]（`longmemeval-frozen-v1.md` §7，`:106-109`） | 是：`longmemeval-retrieval-rank`（`registry.py:352-361`） | frozen §5/§7 未记载官方死代码（`longmemeval-frozen-v1.md` §5，`:53-66`；§7，`:106-117`） |
| MemBench（`membench-frozen-v1.md` §5，`:69-84`） | 单字母 A-D MCQ（`membench-frozen-v1.md:36`；§5，`:71-80`） | choice accuracy（`membench-frozen-v1.md` §5，`:78-80`） | 是：`membench-choice-accuracy`（`registry.py:362-371`） | `f1` 对 MCQ 不适用且注册面排除（`membench-frozen-v1.md` §5，`:84`） |
| MemBench（`membench_source_accuracy.py:1,11-17`） | 单字母 A-D MCQ 的来源四格聚合（`membench_source_accuracy.py:1,11-17`） | First/Third × High/Low 论文四格 accuracy（`membench_source_accuracy.py:1,51-65`） | 是：`membench-source-accuracy`（`registry.py:382-391`） | `f1` 对 MCQ 不适用且注册面排除（`membench-frozen-v1.md` §5，`:84`） |
| MemBench（`membench-frozen-v1.md` §7，`:117-123`） | 工程容量维度，非答案题（`membench-frozen-v1.md` §7，`:122`） | capacity（`membench-frozen-v1.md` §7，`:122`） | 否：registry 无此项（完整注册面 `registry.py:239-402`） | 不是“死代码”；frozen note 仅记 Phase 1 未纳入（`membench-frozen-v1.md` §7，`:122`） |
| MemBench（`membench-frozen-v1.md` §7，`:117-123`） | 工程效率维度，非答案题（`membench-frozen-v1.md` §7，`:122`） | memory-efficiency（`membench-frozen-v1.md` §7，`:122`） | 否：registry 无此项（完整注册面 `registry.py:239-402`） | 不是“死代码”；frozen note 仅记 Phase 1 未纳入（`membench-frozen-v1.md` §7，`:122`） |
| BEAM（`beam-frozen-v1.md` §5，`:43-60`） | rubric 长答案（九类）+ event ordering 序列答案（`beam-frozen-v1.md` §5，`:45-56`） | 9 类 rubric judge + event_ordering judge+τ-b×F1（`beam-frozen-v1.md` §5，`:48-56`） | 是：`beam-rubric-judge`（`registry.py:250-259`） | 嵌入 / BLEU / ROUGE / fact-level 均为分发链外死代码，不接入（`beam-frozen-v1.md` §5，`:48-50`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | Extraction R（`halumem-h1-audit.md` §5，`:104-107`） | 是：`halumem-extraction`（`registry.py:260-269`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | Extraction Weighted R（`halumem-h1-audit.md` §5，`:107`） | 是：`halumem-extraction`（`registry.py:260-269`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | Target P（`halumem-h1-audit.md` §5，`:108`） | 是：`halumem-extraction`（`registry.py:260-269`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | Accuracy（`halumem-h1-audit.md` §5，`:109`） | 是：`halumem-extraction`（`registry.py:260-269`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | FMR（`halumem-h1-audit.md` §5，`:110`） | 是：`halumem-extraction`（`registry.py:260-269`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | Extraction F1（`halumem-h1-audit.md` §5，`:111`） | 是：`halumem-extraction`（`registry.py:260-269`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | Update Correct（`halumem-h1-audit.md` §5，`:112`） | 是：`halumem-update`（`registry.py:280-289`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | Update Hallucination（`halumem-h1-audit.md` §5，`:113`） | 是：`halumem-update`（`registry.py:280-289`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | Update Omission（`halumem-h1-audit.md` §5，`:114`） | 是：`halumem-update`（`registry.py:280-289`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | QA Correct（`halumem-h1-audit.md` §5，`:115`） | 是：`halumem-qa`（`registry.py:290-299`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | QA Hallucination（`halumem-h1-audit.md` §5，`:116`） | 是：`halumem-qa`（`registry.py:290-299`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-h1-audit.md` §5，`:96-120`） | operation-level extraction/update + QA（`halumem-frozen-v1.md:10-11,70-80`） | QA Omission（`halumem-h1-audit.md` §5，`:117`） | 是：`halumem-qa`（`registry.py:290-299`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |
| HaluMem（`halumem-frozen-v1.md` §5，`:75-79`） | operation-level extraction/update 的 memory_type 聚合（`halumem-frozen-v1.md` §5，`:75-79`） | memory_type 官方共享分母附加分析（`halumem-h1-audit.md` §5，`:123-125`；修复结果 `halumem-frozen-v1.md` §5，`:75-79`） | 是：`halumem-memory-type`（`registry.py:270-279`） | `PROMPT_MEMOBASE` 为官方死代码（prompt 而非 metric，`halumem-frozen-v1.md` §5，`:62-64`） |

## 表 C：通用候选池现状

“实现依赖”只记录现有事实：完整项目依赖表位于 `pyproject.toml:6-33`；registry
完整面位于 `registry.py:239-402`。

| 指标 | 框架内是否已有实现或近亲 | 若无，现有依赖事实 |
|---|---|---|
| EM（候选池定义，`metric-extension-plan.md:22-25`） | 无独立通用 EM；近亲为 MemBench A-D 精确比较 `membench-choice-accuracy`（`membench_choice_accuracy.py:36-50`；完整 registry `registry.py:239-402`） | 精确字符串比较只使用 Python 内建操作；该近亲模块无新增第三方 import（`membench_choice_accuracy.py:7-11,36-50`） |
| token-F1（候选池定义，`metric-extension-plan.md:22-25`） | 有：通用 `f1`，标准归一化 token overlap（`registry.py:300-311`；`f1.py:17-64`） | 已实现，无额外实现依赖待盘点（`f1.py:3-10`） |
| BLEU（候选池定义，`metric-extension-plan.md:22-25`） | 无注册 evaluator（完整 registry `registry.py:239-402`）；BEAM 官方 BLEU 路径已冻结为死代码（`beam-frozen-v1.md` §5，`:48-50`） | `nltk>=3.9.0` 已是直接依赖，因此 BLEU 算法库已存在；未见 `sacrebleu`/`evaluate` 直接依赖（完整依赖表 `pyproject.toml:6-33`） |
| ROUGE-L（候选池定义，`metric-extension-plan.md:22-25`） | 无注册 evaluator（完整 registry `registry.py:239-402`）；BEAM 官方 ROUGE 路径已冻结为死代码（`beam-frozen-v1.md` §5，`:48-50`） | 完整依赖表中无 `rouge-score`/`evaluate` 直接依赖（`pyproject.toml:6-33`）；是否引入新第三方依赖为**来源待溯** |
| LLM-judge（binary；候选池定义，`metric-extension-plan.md:22-25`） | 有近亲：`longmemeval-judge` 官方 yes/no 二元 judge，以及 `locomo-judge` 二元辅助 judge（`registry.py:322-341`；`longmemeval_judge.py:43-55`；`locomo_judge.py:153-181`） | 已有 judge 基座与 API 依赖；两项注册均 `requires_api=true`（`registry.py:322-341`；`pyproject.toml:12,15`） |
| LLM-judge（rubric；候选池定义，`metric-extension-plan.md:22-25`） | 有：`beam-rubric-judge`；HaluMem 三个 judge evaluator 也是 rubric/分类式近亲（`registry.py:250-269,280-299`；`beam_rubric_judge.py:144-149`） | 已有 judge 基座与 API 依赖；相关注册均 `requires_api=true`（`registry.py:250-269,280-299`；`pyproject.toml:12,15`） |
| recall@k（候选池定义，`metric-extension-plan.md:22-25`） | 有：`beam-recall`、`locomo-recall`、`longmemeval-recall`、`membench-recall`，另有 multi-k `longmemeval-retrieval-rank`（`registry.py:240-249,342-360,372-401`） | 已实现为 artifact-only 离线 evaluator，注册均 `requires_api=false`（`registry.py:240-249,342-360,372-401`） |
| NDCG@k（候选池定义，`metric-extension-plan.md:22-25`） | 有：`longmemeval-retrieval-rank` 输出 `ndcg_any@k`（`registry.py:352-361`；`longmemeval_retrieval_rank.py:112-116,153-171`） | 已实现，仅使用标准库 `math.log2` 做 DCG（`longmemeval_retrieval_rank.py:5-7,175-180`） |
| abstention 口径（候选池定义，`metric-extension-plan.md:22-25`） | 有分散近亲、无独立注册 metric：通用 F1 记录 abstention；LongMemEval recall/rank 排除并计数（`f1.py:63-64`；`longmemeval_retrieval_rank.py:53-70,135-136`；完整 registry `registry.py:239-402`） | 现有实现只需 question id / artifact 字段，无独立第三方依赖证据（`f1.py:63-64`；`longmemeval_retrieval_rank.py:53-70`） |
| parse_failed 率（候选池定义，`metric-extension-plan.md:22-25`） | 有字段近亲、无独立“率” evaluator：`membench-choice-accuracy` 每题写 `parse_failed`（`membench_choice_accuracy.py:36-60`；完整 registry `registry.py:239-402`） | 当前字段由字符串规范化与集合判断产生，无第三方依赖（`membench_choice_accuracy.py:36-46,65-75`） |

## 一致性与来源待溯

- registry 与 frozen note 未发现“frozen 说已实现、registry 却缺失”的矛盾：五份
  frozen note 中所有具名已实现 evaluator 均可在 `_REGISTRATIONS` 找到
  （`registry.py:239-402`；各 frozen note §5：`locomo-frozen-v1.md:58-67`、
  `longmemeval-frozen-v1.md:53-66`、`membench-frozen-v1.md:69-84`、
  `beam-frozen-v1.md:43-60`、`halumem-frozen-v1.md:60-80`）。
- **来源待溯 1**：`membench-recall` 的 artifact / frozen note 没有实际 tier 字段或
  supplementary 标记（`membench_recall.py:17-33`；`membench-frozen-v1.md:81-84`）。
- **来源待溯 2**：现有直接依赖中没有 ROUGE 专用包，但仅凭依赖表不能裁定未来实现
  是否必须引入新第三方依赖（`pyproject.toml:6-33`）。

## 施工报告

- 交付物：`docs/workstreams/ws02.7-method-track/notes/metric-inventory.md`。
- 表格完成度：A/B/C 三表完成；全程离线，未调用真实 API，未改代码。
- 来源待溯计数：2。
- 停工事项：无；未发现 evaluator 注册面与 frozen note 的实现状态矛盾。
- commit：本文件所在的本地提交（hash 见 actor 交接报告）。

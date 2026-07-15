# Retrieval metric 资格与排序契约审计

> 日期：2026-07-15
> 身份：Claude Sonnet 5 actor（docs-only、零真实 API、单批 ≤5h）
> 任务卡：`actor-prompt-retrieval-metric-eligibility-audit.md`
> 范围：框架契约取证（registry→factory→runner manifest→evaluator），**不逐一审
> 10 个 method**，不改代码/测试/状态文档，不裁最终 schema。
> worktree：`/Users/wz/Desktop/mb-actor-metric-eligibility`
> （`actor/retrieval-metric-eligibility-audit`，从 `main@eed497b` 新建）。

## 0. 方法论说明（含一处只读跨树读取）

- 本 note 的证据全部来自本 worktree 内 `src/`、`tests/`、`docs/` 的一手代码/文档
  读取，唯一例外：`third_party/benchmarks/`（LongMemEval-main、locomo-main、
  Membench-main 官方源码）按 `AGENTS.md` 硬规则**不入 git**，因此新建的 worktree
  中不存在该目录（`ls` 确认为空）。为满足卡内 §2.1"官方 parity 必须给官方源码 +
  本框架实现双锚"与停工条件"官方 LongMemEval rank/NDCG 源码缺失"的要求，本 actor
  改为**只读**方式打开同一物理磁盘上主工作区的绝对路径
  `/Users/wz/Desktop/memoryBenchmark/third_party/benchmarks/...`
  （未在该路径下做任何写入/编辑，未 `cd` 过去，只用 `Read`/`sed -n` 查看）。判断
  依据：`third_party/benchmarks/` 不入 git 是仓库既定策略而非本次缺失，源码在同一
  物理机上确实存在且可读，停工条件的立意应是"源码不可得或与冻结判例矛盾"而非
  "worktree 机制性地看不到 gitignore 目录"；核实结果见 §2.2，与
  `notes/lightmem-offline-recall-ruling.md` 无矛盾（该 note 未涉及 LongMemEval rank
  细节）。此偏差已在 §3 说明，供架构师复核该判断是否合理。
- 唯一改动文件：本 note。未改 src/tests/third_party/README/status/checklist/
  configs/outputs。

## 1. 核心区分复述（已裁，仅确认理解，不改判）

- transformation-input lineage（改写输入并集）≠ semantic evidence provenance
  （当前 item 实际仍承载的 source facts）；Recall/NDCG 只能用后者。
- 官方不提供无损 output-to-source mapping 时，N/A 是诚实能力声明。
- `consume_granularity`（投递批次）、provenance resolution（来源分辨率）、
  retrieval item granularity（一条 item 是 fact/summary/session/chunk）是三件事，
  本审计全程按此区分描述现状，不改判。

## 2.1 当前 evaluator 资格矩阵

代码位置：`src/memory_benchmark/evaluators/{locomo_recall,longmemeval_recall,
longmemeval_retrieval_rank,membench_recall,beam_recall}.py`；注册表
`src/memory_benchmark/evaluators/registry.py`。除这 5 个，全仓库 grep
`retrieved_items|source_turn_ids|retrieval_query_top_k` 命中的 evaluator 目录下
文件只有这 5 个（另有 `core/provider_protocol.py`、5 个 method adapter、
`runners/{prediction,operation_level}.py`、`audit/benchmark_probe.py`，均非
evaluator）；`membench_source_accuracy.py` 等其余 evaluator 不读这三个字段。

| evaluator | metric_tier（见下方说明） | gold 相关性单位 | provenance 语义 | 允许粒度 | item 顺序要求 | 读 score？ | k 集合 | 空 evidence 规则 | N/A 条件 | fail-fast 条件 |
|---|---|---|---|---|---|---|---|---|---|---|
| `locomo-recall` | 代码未打标；行为对齐 `official_parity` | dia_id（`D<n>:<turn>`） | turn 精确匹配 / session 前缀匹配 | turn、session | 否（求并集，不产出名次） | 否 | 单一 `retrieval_query_top_k`（由 query 决定，非固定常量） | evidence 为空 → score=1.0（官方同款） | `provenance_granularity∈{none,undeclared}` | 声明 turn/session 但 top_k/retrieved_items/source_turn_ids 缺失或空 → `ConfigurationError`；声明值不在 {none,session,turn} → `ConfigurationError` |
| `longmemeval-recall` | 代码自标 `framework_supplementary=True` | 公开 turn id / 公开 session id（官方 corpus id 只进 details 留痕） | turn 精确匹配 / session 前缀匹配 | turn、session | 否（求并集） | 否 | 同上 | 空 → score=1.0（框架自定，非官方，见 §2.2） | 同上 | 同上；另外 `_abs` 问题整题记 `status="n/a", score=None`，不进 mean |
| `longmemeval-retrieval-rank` | 代码未打标；docstring 自称"官方…实现"，意图 `official_parity` | 同上（turn/session） | 同上 | turn、session | **是**：保留 `retrieved_items` 原序展开 source id，首次出现去重 | 否 | `OFFICIAL_K=(1,3,5,10,30,50)`，按 `k<=top_k` 过滤 | 空 gold → 三指标记 1.0（**与官方不一致，见 §2.2**） | 同上 | 同上；`_abs` 问题整题 N/A 不进 mean |
| `membench-recall` | 代码未打标；行为近似 `framework_supplementary`（MemBench 无官方 recall@k 基线可对齐） | 公开 turn-id（1 基，官方 0 基 `target_step_id` 仅留 metadata） | turn 精确匹配 | 仅 turn；**声明 session 时显式记结构化 N/A**（非 fail-fast，理由：MemBench 单 session 无可召回的 session 结构） | 否（求并集） | 否 | 同上 | 空 → score=1.0 | `none/undeclared`；显式 `session`（见前一列） | 声明 turn 但字段缺失/空 → `ConfigurationError`；声明值不在 {none,session,turn} → `ConfigurationError` |
| `beam-recall` | 代码自标 `framework_supplementary=True`（docstring 同款自述） | 公开 turn-id（`evidence_turn_ids` 来自私有 metadata） | turn 精确匹配 | **仅 turn**；声明 `session` **直接 fail-fast**（与 membench 的优雅 N/A 处理不一致，见下） | 否（求并集） | 否 | 同上 | evidence 为空 → 整题记 N/A（`status="n/a"`），**不是 1.0**，与另外四个 evaluator 的"空 evidence=1.0"规则不同 | `none/undeclared` | 声明值 `!= "turn"` 且不在 `{none,undeclared}` → `ConfigurationError`（含 `"session"`，见前列） |

补充说明（表格容纳不下的精确发现）：

1. **`metric_tier` 是已有机制但 5 个评审对象均未采用**。
   `docs/reference/metric-extension-plan.md` §1 已定义
   `official_parity/framework_supplementary/framework_auxiliary` 三层，代码里也
   已有实现——但目前**仅 `locomo_judge.py:62-63,166,181` 一处**真正写了
   `metric_tier` 字段并落进 payload。本审计所列 5 个 retrieval evaluator 全部
   没有这个字段；`longmemeval_recall.py`/`beam_recall.py` 各自用了一个局部布尔
   `"framework_supplementary": True`（同名但不是同一机制，也没有对应的
   `official_parity`/`framework_auxiliary` 用法），`locomo_recall.py`/
   `longmemeval_retrieval_rank.py`/`membench_recall.py` 三个连这个布尔都没有。
   即"哪个 tier"目前只能靠 docstring 措辞和行为倒推（如本表第 2 列），不是可机读
   字段。

2. **"声明 session 但本 evaluator 不支持"时，三种不同处理方式并存**：
   `locomo-recall`/`longmemeval-recall`/`longmemeval-retrieval-rank` 把 session
   当一等公民（正常计分）；`membench-recall` 显式识别 session 并返回**结构化
   N/A**（`membench_recall.py:44-56`，理由写明"MemBench 单 session 无结构可
   召回"）；`beam-recall` 对 session **没有专门分支**，会落进
   `if provenance != "turn": raise ConfigurationError(...)`
   （`beam_recall.py:34-38`），错误文案是"Unknown provenance_granularity
   'session'"——但 `session` 本身是协议合法值（`ProvenanceGranularity =
   Literal["none","session","turn"]`），只是 BEAM 这个 evaluator 选择不支持，
   文案把"合法但不支持"和"值本身非法"混在一起，容易误导排查者。

3. **`longmemeval-retrieval-rank` 的空 gold/no-target 处理与官方不一致，且框架
   自己的免责声明只覆盖了一半**，详细取证见 §2.2 第 5 点，这里只标注结论：
   `official_empty_gold_note` 只披露了 ndcg 的 0.0→1.0 偏离，没有披露
   `recall_any` 同样发生的 0.0→1.0 偏离，也没有披露官方其实是把这类问题整题剔出
   分母（不参与平均），而框架是**保留在分母里并记 1.0**——是三种不同行为
   （剔除 / 记 0 / 记 1），不是一个数字的偏离。

4. **`RetrievedItem.score` 字段全程未被这 5 个 evaluator 读取**
   （`core/provider_protocol.py:242` 定义了 `score: float | None`；对 5 个
   evaluator 源码 grep `item["score"]`/`item.get("score")` 零命中，所有
   `["score"]` 命中都是 evaluator 自己写的分数字段，不是读 provider 的
   相关性分数）。排序/去重全部基于 `retrieved_items` 的**列表位置**，与
   provider 是否附带相关性分数无关。

## 2.2 LongMemEval NDCG/排序链

官方源码（只读，见 §0 说明）：
`third_party/benchmarks/LongMemEval-main/src/retrieval/eval_utils.py` 全文 48 行、
`src/retrieval/run_retrieval.py:290-419`。框架实现：
`src/memory_benchmark/evaluators/longmemeval_retrieval_rank.py`。

1. **DCG 的 relevance 是 binary，来源是 gold 命中判定**。官方
   `eval_utils.py:14`：`relevances = [1 if doc_id in correct_docs else 0 for
   doc_id in corpus_ids]`；框架 `longmemeval_retrieval_rank.py:163`：
   `relevances = [1.0 if item in gold else 0.0 for item in ranked_ids[:k]]`。
   两侧都是 0/1 二值，不是 graded relevance。DCG 折损公式官方
   `eval_utils.py:4-9`（`rel[0] + Σ rel[i]/log2(i)`，i 从 2 起）与框架
   `longmemeval_retrieval_rank.py:175-183` 的 `_dcg` 逐项对齐。ideal DCG
   官方对**全 corpus** 二值相关性降序取前 k（`eval_utils.py:16-17`），框架用等价式
   `[1.0]*min(len(set(gold)),k)`（`:167`，注释已自证等价条件），成立前提是
   gold 均在 corpus 内且不重复——与官方 corpus 语义相符。

2. **rank 取 `retrieved_items` 原顺序，既不按 score 重排也不按 source id 排序**。
   `_ranked_source_ids()`（`longmemeval_retrieval_rank.py:186-201`）只做
   `for item in items[:top_k]: for raw_id in item["source_turn_ids"]:
   若未见过则 append`——严格保留 provider 返回顺序，遇到同一 source id
   在多个 item 中重复出现时按**首次出现位置**去重，不重新排序、不读
   `item["score"]`（见 2.1 补充 4）。

3. **provider→artifact 序列在哪些 helper 可能被排序/去重/截断**：
   - **写入侧（provider→artifact）不排序不去重**：
     `_retrieved_items_payload()`（`runners/prediction.py:2795-2800`）就是
     `[asdict(item) for item in retrieval_result.items]`，逐项直通，保留
     provider 返回的原始顺序与全部条目（不按 `top_k` 截断——`top_k` 只用于
     `retrieval_query_top_k` 字段，不影响这里存多少条）。
   - **读取侧（artifact→evaluator）只截断+去重，不排序**：截断发生在每个
     evaluator 自己的 `items[:top_k]`（如
     `longmemeval_retrieval_rank.py:193`，`top_k` 取自 artifact 里的
     `retrieval_query_top_k`，即当初请求时的 `query.top_k`，与
     `len(retrieved_items)` 无关）；去重只发生在
     `longmemeval_retrieval_rank._ranked_source_ids`（展开 source_turn_ids 为
     扁平排名列表时按首现去重）；其余 4 个 recall 类 evaluator 只求
     `set()` 并集（`_source_turn_ids`/`_source_ids` 系列函数），天然去重但
     不产出、也不需要名次。
   - 结论：全链路没有任何"二次排序"步骤——这与
     `method-integration-checklist.md` B5 最后一条"不能拿…二次排序后的展示
     列表…冒充官方 top-k"的红线不冲突（因为框架自己没有做二次排序），但也
     意味着**排序的忠实性完全依赖 provider 自己返回顺序是否就是其内部真实
     检索名次**，框架没有独立手段验证这一点（即 checklist B5 同一条要求的
     "可解释 rank"目前无代码校验，只能靠逐 method 人工核实其
     `retrieve()`/`provider_protocol.RetrievedItem` 构造代码——这是审计缺口，
     不是本卡范围内可以补的实现）。

4. **method-native answer depth 与 evaluation depth 当前如何共用 `top_k=10`**：
   全仓库唯一构造 `RetrievalQuery` 且被 LongMemEval 走到的位置是
   `runners/prediction.py:2751-2765` 的 `_retrieval_query_from_question`，
   `top_k=10` 硬编码在第 2762 行字面量（不是配置项，不是常量引用）。这一次
   `provider.retrieve(query)` 调用同时产出：(a) `formatted_memory`——method
   自己决定塞多少上下文给 answer LLM（method-native answer depth 由 provider
   内部逻辑决定，但它能看到的检索请求宽度上限已经被这个 10 卡住）；(b)
   `retrieved_items`——之后被 `longmemeval-recall`/`longmemeval-retrieval-rank`
   原样拿去算 Recall/NDCG（evaluation ranking depth）。两者共享同一次调用、
   同一个 `top_k` 标量，没有独立的"只为评测多要 k 条"的第二次检索。
   （补充：`runners/operation_level.py` 是 HaluMem 专用 runner，另有两处
   `RetrievalQuery` 构造，`:383` 的 memory_update_probe 用 `top_k=10`，`:422`
   的 QA 用 `top_k=20`——与 LongMemEval 路径的 10 不是同一个值，说明这个"魔数"
   目前是逐调用点手写字面量，不是全局单一配置，但都不受本卡范围的 LongMemEval
   讨论直接影响，仅供参照。）

5. **官方 k=30/50 在真实 run 是否必然缺失：是，且与 artifact 存多少项无关**。
   `longmemeval_retrieval_rank.py:89-92`：
   `available_k = [k for k in OFFICIAL_K if k <= top_k]`，这里的 `top_k` 来自
   `record.get("retrieval_query_top_k")`（artifact 字段，取值即 `query.top_k`
   =10，见第 4 点），**不是** `len(retrieved_items)`。即使某 method 的
   `retrieved_items` 数组里物理保存了 60 条（如 ruling note §6 提到的
   LightMem `retrieve_limit=60`），`available_k` 依旧被 10 封顶，`k=30/50`
   会被计入 `skipped_k_above_top_k`（`:91`），永远拿不到分。这是硬编码常量
   决定的确定性结论，不是"取决于 run"的概率性缺口。

6. **一个未在 ruling note 出现、本次新核实的官方语义分歧点**：官方
   `run_retrieval.py:389-408` 在汇总平均指标时，**排除两类问题**——
   `_abs` 摈弃题（`ignored_qs_abstention`）和"该题所有 haystack 用户轮次都没有
   `has_answer=True`"的**无目标题**（`ignored_qs_no_target`，`:399-402`）。
   框架的 `evidence_turn_ids` 构造（`benchmark_adapters/longmemeval.py:366-367`：
   `if turn_raw.get("has_answer") is True: evidence_turn_ids.append(turn_id)`）
   与官方判定"有无目标轮次"用的是**同一个** `has_answer` 标签，即官方的
   "无目标题"基本等价于框架的"gold evidence 为空"情形。但框架
   `longmemeval_retrieval_rank.py` 只排除了 `_abs`（`:57-70`），对空 gold 的
   处理是**保留在参与统计的分母里，三项指标都记 1.0**
   （`_evaluate_at_k:156-161`）——不是官方的"整题剔除、不进平均"，也不是
   naive 套用官方公式会得到的"记 0.0"。三者是三个不同的数：**剔除 vs 记 0
   vs 记 1**，框架选的是第三种，且该选择是从
   `longmemeval-recall`/`locomo-recall` 的"空 evidence=1.0"惯例**跨指标平移**
   过来的，不是 LongMemEval rank 指标自己官方语义的一部分（官方这里从不给
   1.0，也不是自己的"跳过"）。`empty_gold_question_count` 字段
   （`:136,313-314` 附近汇总处）如实记了这个人群的数量，但 `overall_metrics`
   均值本身混入了这批"框架自定 1.0"的分数，这一点没有在
   `official_empty_gold_note` 里说清楚（该字段只提了 ndcg 的偏离）。

## 2.3 capability 声明现状

链路：`core/provider_protocol.py`（协议定义）→
`methods/registry.py`（MethodRegistration 静态声明 + 5 个 adapter 类属性）→
`runners/prediction.py` / `runners/operation_level.py` / `cli/run_prediction.py`
（解析成 manifest）→ 5 个 evaluator（读 manifest）。

1. **`provenance_granularity` 当前是"method 静态"，不是实例动态，也不能按
   benchmark 区分**。协议层是单一类属性
   `MemoryProvider.provenance_granularity: ProvenanceGranularity = "none"`
   （`provider_protocol.py:276`，`Literal["none","session","turn"]`，
   `provider_protocol.py:17`）。5 个 adapter 各自在类体里写死一个值：
   `mem0_adapter.py:282`/`lightmem_adapter.py:308`/`memoryos_adapter.py:454`/
   `mock.py:49` 均为 `"turn"`，`amem_adapter.py:239`/`simplemem_adapter.py:163`
   均为 `"none"`；全仓库 grep `self\.provenance_granularity\s*=` **零命中**——
   没有任何 adapter 在 `__init__`/方法体内按参数或 benchmark_name 动态赋值这个
   属性。作为对照，同为 `MemoryProvider` 声明面的 `consume_granularity` **已经
   做到了按 benchmark 动态**：`methods/registry.py:182-188` 的
   `_build_mem0_system` 按 `context.benchmark_name` 在
   `"session"/"pair"/"turn"` 间切换构造参数。这说明"按 benchmark 动态声明"的
   基础设施（`MethodBuildContext.benchmark_name` 已经传到每个 factory）已经
   存在，只是没有被用在 `provenance_granularity` 上——也因此当前**无法表达
   "LightMem 非 LoCoMo=turn、LoCoMo post-update=N/A"**：LightMem 的
   `provenance_granularity` 无论跑哪个 benchmark、处于 ingest 的哪个阶段，都是
   同一个写死的 `"turn"`（registry 级还有一层同值静态覆盖，见第 2 点）。

2. **两级解析，registry 静态声明优先于实例属性**：
   `MethodRegistration.provenance_granularity: str | None = None`
   （`methods/registry.py:129`），仅 `mem0`/`lightmem`/`memoryos` 三个注册项
   显式设为 `"turn"`（`:800,826,857`），`amem`/`simplemem` 未设（缺省
   `None`）。`resolve_registered_factory_provenance_granularity()`
   （`:919-927`）按 `system_factory` 身份查 registry；
   `_method_manifest_with_protocol()`（`runners/prediction.py:1218-1258`）逻辑
   是"registry 值非 None 就用它，否则**才**读 `system.provenance_granularity`
   实例属性"（`:1248-1249`，docstring 原话见 `:1230`）。

3. **isolated workers 路径优先 registry 声明的具体原因**：`max_workers>1` 且
   `system_factory`/`build_context_template` 均非空时（`prediction.py:453-458`
   的 `use_isolated`），`cli/run_prediction.py:642-646` 会给传入
   `run_predictions()`/`_method_manifest_with_protocol()` 的"根 system"参数
   替换成 `_UnusedRootSystem()`——一个继承**旧协议** `BaseMemorySystem`
   （不是 `MemoryProvider`）的占位对象（`cli/run_prediction.py:136-141`，
   docstring："isolated worker path 的根 system 占位对象…避免提前构造第三方
   method"）。由于 `_UnusedRootSystem` 不是 `MemoryProvider` 实例，
   `_method_manifest_with_protocol` 里 `isinstance(system, MemoryProvider)`
   判定为假，**实例属性回退分支永远不会触发**——如果 registry 也没有静态声明
   （即 amem/simplemem 走 isolated 路径时），manifest 里
   `provenance_granularity` 键会被整个跳过不写（`:1250` 的
   `if provenance_granularity is not None` 才 `setdefault`），evaluator 侧的
   `_method_provenance_granularity()` 系列函数读不到键时归类为
   `"undeclared"`，按 N/A 处理（各 evaluator `_na_payload` 分支）。也就是说
   registry 声明不是"优先"这么简单，而是**isolated 路径下唯一可能生效的
   来源**——这一机制已有测试锁定行为（`tests/test_prediction_runner.py:3482-
   3495` 的 `test_parallel_manifest_uses_lightmem_registration_provenance`
   用 `system=None` 复现 isolated 场景下靠 registry 值盖章；
   `tests/test_prediction_runner.py:3203` 附近的
   `test_registered_isolated_prediction_does_not_construct_root_system`
   验证根 system 确实不会被真的构造）。amem/simplemem 目前因为真实类属性
   本来就是 `"none"`，"registry 缺声明→manifest 缺键→归类 undeclared→N/A"
   这条链路的最终效果与"如实声明 none→N/A"一致，**尚未在当前 5 个已注册
   method 上暴露出可观测的错误**；但这是一个结构性的隐藏耦合——如果未来
   注册一个真实提供 turn-level provenance、却忘记在 `MethodRegistration`
   里显式填 `provenance_granularity="turn"` 的新 method，一旦以
   `max_workers>1` 跑，它的真实能力会被静默降级成 `"undeclared"`/N/A，
   而不是报错提醒"你漏填了registry 声明"——目前没有任何校验强制"支持
   isolated 执行的 method 必须有 registry 级静态声明"。

4. **能否按 metric 区分 Recall valid 但 NDCG pending/N/A：目前不能**。
   `longmemeval_recall.py`（Recall）与 `longmemeval_retrieval_rank.py`
   （NDCG/rank）各自独立调用 `_method_provenance_granularity(manifest)`/
   `_provenance_granularity(manifest)`，但两者读的是**同一个** manifest 字段
   `manifest["method"]["provenance_granularity"]`——这是一个 run 级单一标量，
   一旦声明为 `"turn"`，Recall 和 NDCG 会被同时判定为"结构上可评"，没有任何
   字段能表达"这个 method 的 provenance 足够支撑 Recall（集合命中）但不足以
   支撑 NDCG（要求真实保序）"。这正是
   `docs/reference/method-integration-checklist.md` B5 最后一条（"NDCG/检索
   排名另有资格门…禁止要求每个 method 填满所有指标"）和
   `docs/reference/metric-extension-plan.md` §3 第 5 条（"Recall 可评也不
   自动推出 NDCG 可评，后者另需保序和 depth"）已经写明的目标，但**当前代码
   没有实现这个目标**——两份文档都只是原则声明，`provenance_granularity`
   仍是唯一的、跨指标共用的单一闸门。

5. **N/A 是否有机器可读 reason：部分有，但不是统一枚举，也不是 method 侧
   声明的一部分**。5 个 evaluator 的 `_na_payload` 都在 `summary` 里给了
   `"status": "n/a"` + `"reason": "<字符串>"`，`status`/`provenance_granularity`
   两个值可枚举、可机读；但 `reason` 全部是**各 evaluator 各写各的自由文本**
   （如 `beam_recall.py:214` 硬编码 `"provider provenance is unavailable"`，
   `membench_recall.py` 则按分支给两种不同措辞——`:40` 与 `:49-53`），没有
   共享的 reason 枚举/代码表，理论上同一种情形在不同 evaluator 里的文案可能
   漂移而没有任何机制约束一致性。更关键的是：`provenance_granularity`
   （唯一驱动 N/A 判定的信号）本身只是 method 声明的 3 选 1
   静态值（none/session/turn），**不携带"为什么是 N/A"的语义**——method
   没有地方声明"我在这个 benchmark/这个阶段是 N/A，原因是 XXX"，reason 完全是
   evaluator 之后自己编的话术，不是从声明链路带下来的结构化字段。
   全仓库 grep `class.*Reason|reason_code|EligibilityStatus|eligibility`
   零命中，确认目前没有任何专门的资格/原因枚举类型。

6. **resume fingerprint 是否包含该资格：包含，且有专门的向后兼容处理**。
   `runners/prediction.py:1166-1186` 的 `_manifests_match_for_resume` 在比较
   新旧 manifest 前，会对 `method` 子字典的
   `{protocol_version, prompt_track, profile, provenance_granularity}` 四个键
   做"任一侧缺失就双侧都删掉，不参与比较"的处理（`:1183-1185`）——即
   `provenance_granularity` **是**resume 全量 manifest 比较的一部分，但为了
   兼容"这个字段上线前跑的旧 run"，缺失时不会导致 resume 判定为不匹配（测试
   `tests/test_prediction_runner.py:3522-3536` 的
   `test_resume_manifest_compare_accepts_new_provenance_field` 锁定了这个
   行为）。换言之：resume 会阻止"同一 run_id 下 provenance 声明发生变化"（例如
   同一 method 代码升级导致声明从 turn 改成 none），但不会因为老 artifact
   完全没有这个字段就拒绝 resume。

7. **与 `MethodCapability` 现有机制的关系**：`core/capabilities.py` 已有一套
   独立的粗粒度能力声明——`MethodCapability`（`CONVERSATION_ADD`/
   `ANSWER_GENERATION`/`MEMORY_RETRIEVAL`）+ `validate_compatibility()`
   （benchmark 要求的能力集合 vs method 提供的能力集合，缺失即
   `ConfigurationError`）。这套机制处理的是"method 能不能接这个 benchmark"
   的二元判定，与 `provenance_granularity` 处理的"检索结果能不能算
   Recall/NDCG"是两条完全独立的通路，字段、校验函数、失败方式都不共享——
   `provenance_granularity` 目前没有对应的 `MethodCapability` 枚举值，也没有
   走 `validate_compatibility` 这条已有的 fail-fast 路径。

## 2.4 候选最小 schema（仅供架构师裁，不推荐赢家、不写实现）

三个候选均以"状态至少表达 `valid/n_a/pending` + reason"为基本要求；下面按卡内
指定的三条方向逐一给表达能力、改动面、manifest/resume 影响、向后兼容、为何不会
退化成 method×benchmark 专用 runner。

### 候选 1：静态 method 声明继续扩字段

在现有 `MethodRegistration.provenance_granularity: str | None`
（`methods/registry.py:129`）这条已有静态声明的基础上，扩成一个结构化字段，例如
按 `(benchmark_name, metric_name)` 做键的声明表，随 registry 条目一起手写。

- **表达能力**：能表达"同一 method 在不同 benchmark 下 provenance 不同"
  （因为 `MethodBuildContext.benchmark_name` 在构造 factory 前已知，参照
  `consume_granularity` 现成的按 benchmark 分支模式，见 §2.3 第 1 点）。
  **不能**单独表达 LightMem "LoCoMo post-update 才 N/A"这种 benchmark 内部
  按阶段区分的情形——因为 LoCoMo post-update 和 LoCoMo 是同一个
  `benchmark_name`，静态声明在 factory 构造时（远早于任何 ingest/update 发生）
  就要写死，没有"阶段"这个轴。若要连阶段都覆盖，字段还要再加一维，声明表
  会继续膨胀。
- **改动面**：`MethodRegistration` 增加结构化字段类型；
  `resolve_registered_factory_provenance_granularity` 签名要加
  `benchmark_name`（可选 `metric_name`）参数做字典查找；三处调用点
  （`runners/prediction.py`、`runners/operation_level.py`、
  `cli/run_prediction.py`）都已经拿得到 `benchmark_name`，是 plumbing 而非新
  能力；5 个 evaluator 的读取端不用改（仍是读 manifest 里已解析好的单一
  字符串），除非要做到"按 metric 区分"，那样 evaluator 还要把自己的
  `metric_name` 传进解析函数，manifest 解析逻辑要从"存一个值"变成"存一个
  按 metric 索引的小字典"。
- **manifest/resume 影响**：单个 run 只针对一个 benchmark，"按 benchmark 存"
  不需要 manifest 里出现多 benchmark 的值，向后风险小；但若要做"按 metric"，
  manifest 里 `provenance_granularity` 就要从标量变成字典，
  `_manifests_match_for_resume` 现有的"整键缺失就双删"策略需要扩展成对字典做
  同样的宽松比较（机制上是可行的延伸，不是全新模式）。
- **向后兼容**：延续现有"registry 缺声明时读实例属性兜底"的两级模式即可，
  旧 method（未升级声明的自定义 `--method-class` 用户轻量路径，见
  `CLAUDE.md` "用户轻量路径走 `--method-class` 无需 registry")本来就不受
  registry 结构变化影响，只影响走 registry 的 5 个内建 method。
- **为何不会退化成专用 runner**：改动只发生在"声明"这一层的数据结构（还是
  声明式表格，不是新增按 method 名字判断的代码分支），runner/evaluator 代码
  路径本身保持通用；但如果把这条路推到"每个 method×每个 benchmark×每个
  metric"都要人工填一格，手写声明矩阵的规模会趋近于
  `CLAUDE.md`/`AGENTS.md` 明确要避免的"笛卡尔积注册表"反模式，只是把它落在
  数据而不是代码里——这是候选 1 走到细粒度尽头时的真实风险，应如实告知
  架构师。

### 候选 2：factory/实例按 benchmark 返回 capability bundle

把 `provenance_granularity` 从"类属性/registry 静态值"改成由
`system_factory(context)` 在构造实例时按 `context.benchmark_name`（以及未来可能
的其他运行时信息）动态赋值到实例上，复用 `consume_granularity` 已经验证过的
同款模式（`methods/registry.py:182-188`）。进一步地，可以把粒度下放到
"每次 `retrieve()` 调用"级别——这不是从零设计，LightMem adapter 已经有一个
未被消费的雏形：`lightmem_adapter.py:875-905` 的 `_retrieve_native` 在每次检索
后会算 `metadata["provenance_granularity"] = "turn" if items is not None else
"none"`（`:899`），其中 `items` 来自 `_retrieved_items_from_lightmem_memories`
（`:1227-1264`），该函数在**任一条命中缺 `source_external_id`/字段不完整时
整次检索返回 `None`**（docstring 原话："遇到任一此类命中时整次检索回落为无
provenance，而不是返回部分来源制造假 recall"）——即 LightMem 自己已经在
按**每次问答**动态判断这次检索是否有可信 provenance，但这个判断值目前只写进了
`RetrievalResult.metadata`（进而写进 answer prompt artifact 的
`metadata` 字段），**没有任何 evaluator 读取它**；5 个 evaluator 全部只读
manifest 级别的静态声明。也就是说：当某一题 LightMem 内部判定为无 provenance
（`items=None`）时，`_retrieved_items_payload` 会把它序列化成空列表
`retrieved_items=[]`（`runners/prediction.py:2798-2799`），evaluator 侧的字段
校验对空列表不 fail-fast（`isinstance([], list)` 为真），于是这道题被当成
"provider 检索到 0 个相关结果"正常参与计分（大概率贡献一个 0 分），而不是被
识别成"provider 自己说了这题它不确定 provenance、应该整题 N/A"——manifest 级
静态声明的 `"turn"` 掩盖了这个已经存在但未接通的每题级信号。

- **表达能力**：三个候选里最高——理论上可以做到按 benchmark、按运行阶段、
  甚至按单次 `retrieve()` 调用动态声明，且 LightMem 已经证明这种每题级判断
  在 adapter 内部是可计算的，不需要额外一手信息。
- **改动面**：最大。协议层要么给 `MemoryProvider.provenance_granularity`
  换成可被子类动态覆盖的机制（简单：允许实例属性/property，framework 已经
  支持读实例属性，只是当前 5 个 adapter 都没用动态值），要么在
  `RetrievalResult`/`RetrievedItem` 上正式开一个公开字段承载"这次检索的
  provenance 状态"，5 个 evaluator 都要新增"优先读每题级字段，缺失时退回
  manifest 级静态声明"的分支逻辑（不是推倒重来，是加一层更细的判断，各
  evaluator 现有的字段校验、N/A 分支结构可以复用）。isolated worker 路径
  的核心矛盾会被放大：manifest 现在必须在没有真实实例的情况下盖章
  （§2.3 第 3 点），如果权威判断改成"实例/每次调用动态"，manifest 就只能
  继续充当"声明上限/静态兜底"，真正的判断要下放到 evaluator 读 artifact
  逐题记录——这是一个概念上的分层变化，不只是加字段。
- **manifest/resume 影响**：manifest 级字段可以继续保留、含义收窄为"method
  声明的能力上限"（不变），resume 比较逻辑不受影响；新增的每题级信号住在
  answer prompt artifact 里（该 artifact 本来就逐题写，不参与 resume manifest
  比较），所以 resume fingerprint 本身不需要感知这个新字段。
- **向后兼容**：旧 artifact 没有这个每题级字段，evaluator 的"优先读每题级、
  缺失退回 manifest 级"分支天然兼容旧数据，不需要特殊迁移代码。
- **为何不会退化成专用 runner**：因为落点仍是协议里对所有 method 通用的
  `RetrievalResult`/`RetrievedItem` 结构和评审端的通用回退逻辑，不是给
  LightMem 单开分支——是把 LightMem 已经"意外实现"的模式提炼成协议里所有
  method 都能选择性使用的通用机制。风险点在于如果只有一个 method
  会真正用到每题级动态值，容易变成"为了一个 method 通用化"，需要架构师判断
  是否有第二个真实场景验证这不是过度设计。

### 候选 3：evaluator 侧独立 eligibility manifest

不在 `MethodRegistration`/`MemoryProvider` 协议任何一侧加字段，而是新增一张
独立的 `(method_name, benchmark_name, metric_name)→{status, reason}` 声明表
（可以是新模块比如 `evaluators/eligibility.py`，或者一份 TOML，延续项目
"配置一律 TOML"的既有约定——`actor-handbook.md` §5），由架构师/评审方维护，
不依赖 method 自我声明。评估时，evaluator 用 `manifest["method_name"]`、
`manifest["benchmark_name"]`（两者已经是 manifest 顶层既有字段，见
`runners/prediction.py:918-919`）和 `self.metric_name`（5 个 evaluator 已各自
有这个类属性）去查表，而不是像现在这样只读 `manifest["method"]
["provenance_granularity"]` 单一标量。这条思路直接对应
`evaluators/registry.py` 里已经存在的粗粒度先例——`EvaluatorRegistration.
supported_benchmarks: frozenset[str]`（`:57`）本来就是一张独立于 method
声明、由 evaluator 侧维护的兼容表，`create_evaluator()` 里已经在做
"不在表里就 `ConfigurationError`"的 fail-fast（`:449-453`）；候选 3 相当于
给这张表再加两个维度（method_name、更细的 valid/n_a/pending 状态）和一个
reason 字段。

- **表达能力**：可以覆盖 (method, benchmark, metric) 任意组合，包括"同一
  method 在同一 benchmark 下 Recall valid 但 NDCG pending"（§2.3 第 4 点的
  缺口）；因为评估时才查表，还能覆盖"同一 benchmark 下不同运行阶段"这种
  候选 1 覆盖不了的情形——只要判断依据能写进 reason 文本，不要求在
  prediction 阶段就能预知。这也是三个候选里唯一天然贴合"这是架构师/评审方
  裁定的结果，不是 method 自证的能力"这条项目既有原则
  （`AGENTS.md`"指标资格不是 method 的义务"）的设计——LightMem×LoCoMo
  post-update 的 N/A 裁决本来就是架构师读证据后拍板的，候选 3 是把这类
  裁决的落点从"only 写在 note 里"变成"落进一张评估时真正会被读取的表"。
- **改动面**：新增模块/配置，**不改** `MethodRegistration`/
  `MemoryProvider` 协议，不改 5 个 adapter；5 个 evaluator 的
  `_method_provenance_granularity()`/`_provenance_granularity()` 系列私有
  函数替换成查新表（查表用的三个键已经全部存在于当前 manifest/self，无需
  新增 manifest 写入逻辑）。是三个候选里对**现有协议面**改动最小的一个，
  代价是新增一个需要人工维护、独立于代码行为的数据源。
- **manifest/resume 影响**：可以做到**零 manifest schema 改动**——因为
  查表所需的键（method_name、benchmark_name）在 schema_version 2 就已存在，
  eligibility 表可以在评估阶段（`run_artifact_evaluation`，晚于 prediction）
  才生效，甚至可以对已经跑完 prediction 的旧 artifact 重新按新表跑评估，不
  需要重新预测。resume fingerprint（只管 prediction 阶段能否续跑）完全不受
  影响，是三个候选里对 resume 系统最无侵入的一个。
- **向后兼容**：对已有全部 artifact 100% 兼容（键位不变），唯一的新风险是
  "表里没查到的组合该默认什么"——如果默认为 valid 会破坏现在"未声明就 N/A"
  的 fail-closed 姿态，应该默认不可评/需要显式登记，但这属于该由架构师定的
  默认值语义，本 note 不代为决定。
- **为何不会退化成专用 runner**：新表的条目是纯数据（键值对+文本 reason），
  evaluator 和 runner 代码路径对所有 method 保持一致，不出现按 method 名字
  分支的代码；风险在于这张表会成为一个新的、独立于代码行为的"第二事实源"，
  如果表内容与 method 真实行为逐渐脱节（比如 method 代码升级但表没跟着更新）
  ，会出现"表说 valid 但代码其实已经不满足"的静默漂移，需要某种机制（本卡
  不代为设计）保证表和代码不脱钩。

## 3. 停工点

**未触发任何一条列出的停工条件**：

- 官方 LongMemEval rank/NDCG 源码在同一物理机的主工作区路径下可读，内容与
  框架实现、与 `lightmem-offline-recall-ruling.md` 均不矛盾（该 note 范围是
  LoCoMo/LightMem，未涉及 LongMemEval rank 细节，两者结论不重叠也不冲突）；
  §0 已说明为何判断"跨 worktree 只读官方源码"不等同于"源码缺失"，请架构师
  复核此判断是否合理。
- 未发现 private evidence 进入 method/artifact 公开层（本次审计范围内新读的
  代码路径均有 `validate_no_private_keys` 或结构化 metadata 白名单机制，
  未发现绕过点；未做穷尽式隐私审计，仅限本次读到的代码路径）。
- artifact 是否保序已确定（§2.2 第 3 点：写入侧直通不排序，读取侧只截断
  +去重不重排），不是"无法确定"。
- 未修改允许清单外文件，未调用真实 API。
- 未展开为逐一审 10 个 method；除 LightMem 一处（用于说明候选 2 的
  "既有未接通信号"这一具体证据）外，其余描述均落在 registry/runner/evaluator
  的框架契约代码，5 个 adapter 只做了"类属性值是什么"的一行级 grep 核对，
  不构成逐个 method 深度审计。

## 4. 证据索引（关键文件:行号，按小节顺序）

- §2.1：`evaluators/{locomo_recall,longmemeval_recall,longmemeval_retrieval_rank,
  membench_recall,beam_recall}.py` 全文；`evaluators/registry.py` 全文；
  `evaluators/locomo_judge.py:62-63,166,181`；
  `docs/reference/metric-extension-plan.md` §1。
- §2.2：`third_party/benchmarks/LongMemEval-main/src/retrieval/eval_utils.py`
  全文（只读，见 §0）；同目录 `run_retrieval.py:290-419`（只读）；
  `evaluators/longmemeval_retrieval_rank.py` 全文；
  `runners/prediction.py:2622-2800`（含 `_retrieval_query_from_question`、
  `_retrieved_items_payload`）；`runners/operation_level.py:377-395,415-427`；
  `benchmark_adapters/longmemeval.py:360-367`。
- §2.3：`core/provider_protocol.py:16-18,236-276`；`core/capabilities.py` 全文；
  `methods/registry.py:87-150,182-188,772-928`；`methods/{mem0_adapter,
  lightmem_adapter,memoryos_adapter,mock,amem_adapter,simplemem_adapter}.py`
  的 `provenance_granularity` 属性行；`lightmem_adapter.py:875-905,1227-1264`；
  `runners/prediction.py:380-393,1166-1258`；`cli/run_prediction.py:136-151,
  640-689`；`tests/test_prediction_runner.py:3482-3536`；
  `docs/reference/integration/lightmem.md:248`；
  `docs/reference/metric-extension-plan.md` §3 第 5 条。
- §2.4：以上全部 + `evaluators/registry.py:40-63,423-475`（
  `EvaluatorRegistration.supported_benchmarks`/`create_evaluator` fail-fast
  先例）。

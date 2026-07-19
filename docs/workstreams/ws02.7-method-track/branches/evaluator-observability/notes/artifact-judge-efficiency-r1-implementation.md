# Artifact-level judge efficiency 共享修复 R1 — 实现记录

> Actor 实现记录，跨模型自包含。承重结论、生产入口、探针构造与关键 stdout 逐字落盘，
> 不引用会话私有 scratchpad。

## 1. 根因与范围

`run_artifact_evaluation()` 的普通逐题路径（`_evaluate_one_question`）会：解析/注入
`EfficiencyCollector` → per-question `judge_scope` → 退出后把 `scope.records` 汇入
`EfficiencyArtifactStore.for_evaluator(paths, metric)` 写 model inventory + observations。
但带 `evaluate_run_artifacts()` 的路径 `_run_artifact_level_evaluation()` 只写 score/summary，
**完全跳过** collector/scope/store。因此 BEAM rubric judge 与 HaluMem extraction/update/qa
四个真实 LLM judge 会正确出分，却不留 metric 专属 model inventory / efficiency observations。

本批只补“已发生的 judge 调用可审计落盘”，不改任何 score / aggregation / prompt / method /
benchmark adapter / prediction artifact / 既有 run，全程零真实 API、零模型下载、零 outputs 写入、
不读 `.env`。

## 2. 三句话交代（对应卡 §8）

1. **runner 内部 payload 契约**：artifact evaluator 在启用 collector 时，必须在返回的 payload 里
   显式带一个仅供 runner 内部消费的 `efficiency_observations` 字段（`list/tuple[EfficiencyObservation]`，
   零调用则为空 `[]`）；runner 在写盘前用 `payload.pop(...)` 剥离该字段、严格校验元素类型后交
   `EfficiencyArtifactStore.for_evaluator` 落盘，该字段绝不进 score row / summary JSON / CLI summary；
   缺字段、非序列、含非 observation 元素一律 fail-fast，不得静默当零调用；collector 禁用/None 时忽略
   并剥离该字段，离线 evaluator 行为字节级不变。
2. **BEAM equivalence 已纳入**：`_judge_equivalence()` 的真实 Responses 分支不再绕过计量，改走与
   rubric 共用的 `_invoke_judge_model(api_input=messages, tokenizer_prompt_text=...)` 计量外壳并恰好
   调用一次 `_record_judge_llm_call()`；原始官方 role-tagged messages 原样发送、逐字不变，token 回退
   文本只在 API usage 缺失时用于估算，不改变请求内容，也不与 rubric 外壳叠套双计。
3. **HaluMem 三类 scope identity**：QA 用真实公开 `question_id` + 真实 `conversation_id`；extraction 每个
   session 一个 scope，conversation 取 session 私有标签的真实 `conversation_id`，question 用稳定无碰撞
   evaluator-unit id `f"{metric}:{session_id}"`（**非公开 QA id**，仅用于 observation 归属）；update 每个被
   实际 judge 的更新点一个 scope，真实 conversation + evaluator-unit id `f"{metric}:{session_id}:{gold_index}"`，
   空检索被官方路由跳过时零调用、不建立 scope、不造 observation。

## 3. 生产改动（允许清单内）

- `src/memory_benchmark/evaluators/llm_judge.py`
  - 新增 `EvaluatorEfficiencyObservationSink`：artifact-level judge 在自己的循环内用
    `unit_scope(conversation_id, question_id)` 包裹每个真实评测单元；scope 正常退出后把
    `scope.records` 折入 sink，`observations()` 返回累积副本。collector 为 None/disabled 时
    `enabled=False`、`unit_scope` 直接透传不建立 scope，保证离线/禁用路径不变。
  - `LLMJudgeEvaluator` 新增 `_new_efficiency_observation_sink()` 与 `_finalize_artifact_payload()`
    （仅 `sink.enabled` 时把 `efficiency_observations` 折入 payload）。
  - `_call_model_with_usage(prompt)` 拆出底层 `_invoke_judge_model(api_input, tokenizer_prompt_text)`；
    `api_input` 原样传 Responses API（字符串或 role-tagged messages 都不改写），只负责计量、不记录，
    由调用方在 judge scope 内自行 `_record_judge_llm_call`，避免外壳叠套双计。字符串 prompt 路径行为
    与旧实现逐字一致。
- `src/memory_benchmark/evaluators/beam_rubric_judge.py`
  - 每个公开 `question_id` 一个 `sink.unit_scope(conversation_id, question_id)`，覆盖该题全部 rubric-item
    `_judge_json` 与 event-ordering `_judge_equivalence` 调用；同题多次调用靠 collector call index 区分。
  - `_judge_equivalence` 真实分支改走 `_invoke_judge_model` + `_record_judge_llm_call`；新增
    `_equivalence_messages_text()` 提供确定性 tokenizer 回退文本。
  - payload 经 `_finalize_artifact_payload` 折入 observation。
- `src/memory_benchmark/evaluators/halumem_extraction.py`
  - 每个 session 一个 scope，unit id 由新增 `_extraction_scope_unit_id(metric, session_id)` 生成；
    n/a 早退与正常返回都经 `_finalize_artifact_payload`。routed update 的 `continue`、空抽取的零调用
    均不产生 observation。
- `src/memory_benchmark/evaluators/halumem_update.py`
  - 每个被实际 judge 的更新点一个 scope，unit id 由新增 `_update_scope_unit_id(metric, session_id, gold_index)`
    生成；空 `memories_from_system` 在建立 scope 前 `continue`，零 observation。返回经 `_finalize_artifact_payload`。
- `src/memory_benchmark/evaluators/halumem_qa.py`
  - 每个公开 QA 问题一个真实 conversation/question scope，返回经 `_finalize_artifact_payload`。
- `src/memory_benchmark/runners/evaluation.py`
  - `_run_artifact_level_evaluation()` 调用 evaluator 前解析/注入 collector、校验 `run_id`、取强类型
    model inventory；调用后经新增 `_extract_artifact_efficiency_observations()` 剥离并校验内部字段，
    启用时 `EfficiencyArtifactStore.for_evaluator` 写 inventory + `merge_observations`（保留原冲突语义，
    未放宽为覆盖）。未启用/离线路径除 `payload.pop` 空操作外字节级不变。新增哨兵
    `_MISSING_EFFICIENCY_OBSERVATIONS` 区分“未声明字段”与“显式空序列”。

未改 `halumem_common.py`（sink helper 在共同基类 `LLMJudgeEvaluator` 上，HaluMem 基类
`HalumemJudgeEvaluatorBase` 继承即得），不为用满 allowlist 制造空改动。

## 4. 反例覆盖（对应卡 §4，全部经 runner）

- `tests/test_judge_efficiency_observations.py`
  - `test_artifact_level_api_evaluator_writes_inventory_and_exact_observation`（§4.1）：最小
    artifact-level API evaluator 经 runner 写 metric 专属 model inventory 与一条 judge observation，
    run/conversation/question/model/token/stage 全精确（conv-1 / conv-1:q1 / judge-llm / 53+2 /
    stage=judge / api_usage）。
  - `test_artifact_efficiency_observations_do_not_leak_into_score_or_summary`（§4.8）。
  - `test_offline_artifact_evaluator_creates_no_empty_judge_efficiency_files`（§4.3 离线部分）。
- `tests/test_artifact_evaluation_runner.py`
  - `test_support_artifact_evaluator_efficiency_field_contract_fails_fast`（§4.2，参数化：缺字段 /
    字段类型错误 / 元素类型错误）。
  - `test_disabled_collector_writes_no_artifact_efficiency_files`（§4.3 disabled 部分）。
- `tests/test_beam_rubric_judge.py`
  - `test_beam_rubric_two_items_record_two_distinct_observations_same_question`（§4.4）：两 rubric item
    → 同题两条不同 observation id，score=0.5、official_int=0.0 不变。
  - `test_beam_event_ordering_equivalence_records_usage_without_double_count`（§4.5）：2 rubric + 2 判等
    = 4 次调用 → 恰 4 条 observation（`len(observations)==len(client.calls)==4`，不双计）；判等 `input`
    逐字等于 `_equivalence_messages("event A","event A")` / `("event B","event B")`；score=1.0、composite=1.0 不变。
- `tests/test_halumem_evaluators.py`
  - `test_halumem_extraction_records_session_scoped_observations`（§4.6）：4 条 observation，scope
    identity=`user-1` / `halumem_extraction:s1`，`memory_extraction_f1=1.0`、`memory_update_routed_num=1` 不变。
  - `test_halumem_update_records_observation_with_scope_identity`（§4.6）：scope=`user-1` /
    `halumem_update:s1:2`。
  - `test_halumem_update_empty_retrieval_creates_no_observation`（§4.6 跳过分支）：空检索 probe 经真实
    `_update_probe_record` 序列化，零调用、零 observation、`skipped_empty_retrieval_count=1`。
  - `test_halumem_qa_records_question_scoped_observations`（§4.6）：question scope=真实公开 id，
    `correct_qa_ratio(all)=0.5` 不变。
  - `test_halumem_qa_observations_do_not_cross_conversations`（§4.7）：user-1 / user-2 各自归属不串
    conversation，observation 按 id 确定性排序。

fake-Responses 客户端只提供 Responses API `usage`（source=`api_usage`）以锁真实计量路径；fake
`judge_json` / `judge_equivalence` 无 usage 时产生零 observation，不伪造 token。

## 5. 偏差 / 停工点

- **无停工点**，未触碰允许清单外文件，未命中卡 §6 任一停工条件。确认除 BEAM/HaluMem 三 judge 外
  再无“声明 support 且走 artifact-level”的 API evaluator：`grep` 显示带 `evaluate_run_artifacts` 的其余
  evaluator（membench/longmemeval/locomo recall、rank、source-accuracy、halumem-memory-type）均为独立
  类、不继承 `LLMJudgeEvaluator`、`supports_efficiency_observability=False`，collector 恒为 None、行为字节级不变。
- **偏差（已披露）**：`tests/test_halumem_evaluators.py` 中既有 HaluMem judge evaluator 构造补加
  `model="gpt-4o-mini"`。原因：runner 现按普通路径对声明 support 的 judge evaluator 自动建立 enabled
  collector 并取 `efficiency_model_inventory()`；未显式给 model 时该方法会 `load_settings()` 读 `.env`/环境，
  使单元测试依赖环境（无 `OPENAI_KEY` 时全量 `uv run pytest` 会 fail）。补 model 后 inventory 直接用固定模型名，
  测试保持 hermetic、离线、确定，且不改任何分数。这是修复的必然结果，与既有 judge 效率测试（LoCoMo/LongMemEval）
  一致的约定。
- **隔离**：worktree=`/Users/wz/Desktop/mb-actor-artifact-judge-efficiency-r1`，branch
  `actor/artifact-judge-efficiency-r1`，从本地 `main`(23d785f) 建；gitignored 资产
  `third_party/benchmarks`(BEAM prompts) / `data` / `models` / `.venv` 以 symlink 补齐（common
  `.git/info/exclude` 排除，不入 diff）。BEAM prompt 逐字比对门读的是这些 symlink 后的真实官方源码。

## 6. 定向自检（卡 §7，零真实 API）

```
OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9 \
uv run pytest -q \
  tests/test_artifact_evaluation_runner.py \
  tests/test_judge_efficiency_observations.py \
  tests/test_beam_rubric_judge.py \
  tests/test_halumem_evaluators.py \
  tests/test_documentation_standards.py
```

尾行：`79 passed in 4.53s`（基线 65 + 新增 14）。`git diff --check` 干净。
未获架构师验收前不 push、不清 worktree、不改父线状态。

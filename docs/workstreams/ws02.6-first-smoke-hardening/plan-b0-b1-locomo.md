# LoCoMo B0+B1 施工计划 v2（额度友好版）

> 2026-07-10 用户纠正：v1 把 actor 写成“施工 + reviewer subagent + 全量回归 +
> 最终验收”，导致重复核查和额度浪费。v2 明确：**actor 只施工并做一次最小相关
> 自检；架构师负责审读、验收、全量回归和冻结。**“慢下来”指 benchmark/method
> 严格逐个推进，不指把同一证据重复验证多遍。

## 1. 目标和不变边界

把 LoCoMo QA 整治为有官方来源、真实数据契约、统一 answer prompt、官方 metric、
极小 smoke 和明确 resume 语义的 `frozen-v1` benchmark。

不变边界：

- 不调用真实 API，不运行 full，不下载图片；
- 不改真实 method adapter 或第三方算法核心；
- 不开始 LongMemEval；
- 不把 gold/evidence/judge label 交给 provider；
- 不为 smoke 答对而选择 history/question；
- 当前所有真实 LLM 仍为 `gpt-4o-mini`；
- actor 不自行宣布 `frozen-v1`。

## 2. 新协作方式

### Actor 每批只做

1. 阅读派工 prompt 指定的最少文件；
2. 按冻结口径修改代码与直接相关测试；
3. 只运行 prompt 中的一条定向测试命令；
4. 通过后做一次本地 commit（本轮用户已授权），不 push；
5. 回复 commit、定向测试尾行、plan 偏差或停工点。

Actor **不做**：重新跑全量基线、重复扫描全部数据、独立 reviewer subagent、全量
pytest、compileall、最终隐私审计、冻结文档、README/roadmap 状态裁决。除非派工 prompt
单独写明，否则这些都是架构师的验收工作。

### 架构师每批负责

1. 派工前给一段可直接复制的 actor prompt；
2. actor 返回后亲自读关键 diff；
3. 只复跑该批定向测试并处理断点；
4. 到 LoCoMo 最终冻结时才统一跑 compileall + 全量 pytest + artifact/隐私审计；
5. 由架构师更新 workstream 状态和 `frozen-v1` 记录。

## 3. 已完成并由架构师验收

### T1 官方资产与真实数据剖面

- Actor commit：`1341cb1`
- 产物：source lock、B1 audit、adapter source identity/实际计数 metadata。
- 架构师结论：通过。重复读取数据文件是非阻塞性能小项，不在 B1 返工。

### T2 B0 method-neutral probe

- Actor commit：`edefd9a`
- 产物：`BenchmarkProbeProvider`，支持四种 ingest 粒度、生命周期记录、确定性
  retrieval/provenance 和受控失败。
- 架构师结论：通过。重复 Literal 与一条低价值测试不阻塞，不追加额度修饰。

### T3 benchmark-owned smoke/resume policy

- Actor commit：`7600076`
- 架构师直修：
  - benchmark policy 从 `method` manifest 移到 run manifest 顶层；
  - 未接线的 `--turns/--sources` 对其他 benchmark fail-fast；
  - 修正文档注释中“user/assistant 成对、smoke 可回答”的错误理由。
- 架构师验收：

```text
uv run pytest -q tests/test_locomo_conversation_adapter.py \
  tests/test_benchmark_probe_provider.py tests/test_benchmark_registry.py \
  tests/test_main_cli.py tests/test_prediction_cli.py \
  tests/test_prediction_runner.py tests/test_operation_level_runner.py
254 passed in 31.48s
```

T1-T3 不再交给 actor 复查。

## 4. 剩余施工批次

每一批必须等架构师验收后才派下一批。不得一次把 A4-A6 全塞给同一个 actor 会话。

### A4：最小 smoke + unified answer（已验收）

目标：解决当前 LoCoMo 最明显的两个主线缺口；不碰 metric/resume。

改动范围：

- `src/memory_benchmark/benchmark_adapters/locomo.py`
- `src/memory_benchmark/benchmark_adapters/locomo_prompt.py`（新建）
- `src/memory_benchmark/benchmark_adapters/registry.py`
- `src/memory_benchmark/config/settings.py`
- 直接相关测试：
  - `tests/test_prediction_cli.py`
  - `tests/test_event_stream.py`
  - `tests/test_locomo_conversation_adapter.py`
  - `tests/test_benchmark_registry.py`
  - `tests/test_config_profiles.py`

实现口径：

1. 默认 smoke 为首个 conversation、前两个连续 turn、首个 Phase-1 public question；
2. 选择 question 和公开 metadata 均不得读取 evidence；`smoke_context_truncated` 只表示
   公开 history 是否被裁短；
3. round 只是两个连续 turn 的预算，不改变 canonical stream，不影响 full 的 odd turn；
4. turn 无时间时沿用 session 时间；caption 拼一次；URL 不进 content、不下载；
5. LoCoMo registry 默认 `prompt_track="unified"`；
6. answer prompt 使用官方 QA short-phrase 模板，category 2 加官方日期提示；
7. LoCoMo answer LLM 跨 method 固定 role=user、temperature=0、max_tokens=32、top_p=1；
8. 不改 LongMemEval 或其他 benchmark 的 answer 设置。

Actor 最小自检只有：

```bash
uv run pytest -q tests/test_prediction_cli.py tests/test_event_stream.py \
  tests/test_locomo_conversation_adapter.py tests/test_benchmark_registry.py \
  tests/test_config_profiles.py
```

验收记录：

- Actor commit：`3c68c5d`；actor 自检 `139 passed in 24.08s`。
- 架构师发现并直修一处隐私边界：旧实现用私有 evidence 派生 method 可见的
  `smoke_context_truncated`；现改为只由公开 source/retained turn 数计算。
- 架构师复跑同一命令：`139 passed in 25.32s`。
- 真实数据抽查：`conv-26` smoke=2 turns/1 question；`D1:5` 与 caption-only
  `D4:4` 均继承 session 时间、caption 只拼一次、URL 不进入 content。

### A5：LoCoMo metric（已验收）

范围只含：

- 现有 F1 只补必要官方 parity 测试；parity 已满足就不重写；
- 每条 answer prompt/retrieval artifact 记录实际 query `top_k` 和该次 provider
  声明的 `provenance_granularity`，避免为本指标扩写全局 manifest 装配；
- 新增 artifact-level `locomo-recall`，只读 answer prompt/private label artifacts；
- provenance=`none` → N/A，声明支持却缺来源 → fail-fast；
- turn provenance 对 dia_id；session provenance 对 `D<n>`；
- empty evidence 按官方实现记 1.0，同时另报数量与 non-empty-evidence 均值；
- `locomo-judge` 在 evaluator 类/结果 details 标为 framework auxiliary；
- 不新增 BLEU。

本批不做 resume，不做全链路，不运行 judge API。

Actor 只运行：

```bash
uv run pytest -q tests/test_locomo_answer_metrics.py \
  tests/test_locomo_retrieval_recall.py tests/test_evaluator_registry.py \
  tests/test_artifact_evaluation_runner.py tests/test_prediction_runner.py
```

验收记录：

- Actor commit：`64d2651`；actor 自检 `130 passed in 5.38s`。
- 架构师接受 actor 把 run-level provenance 放入 method manifest 的设计：它属于 method
  capability；resume 只在新旧任一方缺字段时兼容，双方都有字段且值变化仍会 mismatch。
- 架构师直修三处 metric 边界：未声明 provenance → N/A；answer/private/public question
  IDs 必须完全一致；声明 provenance 的命中 item 不得给空 `source_turn_ids`。
- 架构师复跑 A5 定向命令：`133 passed in 3.60s`。

### A6：一条离线全链路 + 复用既有 resume 契约（已验收）

范围只含：

- 新建一条真实 registry/真实 LoCoMo 数据的
  `1 conversation × 1 round × 1 question` probe + fake reader 离线链路；
- 验证 ingest → retrieve → unified answer → F1/recall artifact evaluation；
- 验证 public question/answer prompt/prediction artifact 无私有键；
- 直接复跑已存在的 conversation skip、saved retrieval reuse、smoke 禁 resume 三条测试，
  不重写 generic resume 体系。

本批预计只新增 `tests/test_locomo_registered_prediction.py`，不负责 cleanup、全量回归或
冻结文档；若必须改 generic runner 才能通过，停工交回架构师。

Actor 只运行：

```bash
uv run pytest -q tests/test_locomo_registered_prediction.py \
  tests/test_prediction_runner.py::test_resume_reuses_completed_retrieval_when_answer_failed \
  tests/test_prediction_runner.py::test_resume_skips_completed_conversations_and_questions \
  tests/test_main_cli.py::test_predict_smoke_rejects_resume_and_retry_failed
```

验收记录：

- Actor commit：`6f0039f`，唯一新增
  `tests/test_locomo_registered_prediction.py`；actor 自检 `4 passed in 2.37s`。
- 架构师接受注册表路径上的最小替换：真实 `mem0` registration/factory 外壳内换成 B0
  probe，answer client 换成固定 fake；真实 LoCoMo data/adapter/event aggregation/prompt/
  artifact writer/F1/recall evaluator 均不替换，零真实 API。
- prediction artifact 合法包含模型生成的 `answer`，因此对它采用 gold/evidence/judge
  私有键窄化扫描；public questions 与 answer prompts 继续走通用 validator。
- 架构师复跑同一命令：`4 passed in 2.86s`。无需改 resume 或 generic runner。

## 5. 架构师最终冻结（不派 actor）

A4-A6 全部验收后，由架构师一次性完成：

1. 更新 LoCoMo benchmark/dataset/workflow 三张卡；
2. 写 `notes/locomo-frozen-v1.md`，列 source、mapping、prompt、metric、smoke、resume、
   artifact、known limitations；
3. 运行定向总验收、compileall、一次全量 pytest；
4. 抽查 URL+caption、caption-only、odd session、date-only key、empty evidence；
5. 确认零真实 API、零 public 私有泄漏；
6. 通过后才把 README 标为 `frozen-v1` 并开始写 B2 plan。

## 6. 当前断点

- T1-T3 已完成并经架构师验收；
- A4 已经架构师验收；
- A5 已经架构师验收；
- A6 已经架构师验收；
- LoCoMo 已于 2026-07-10 达到 `frozen-v1`，记录见
  `notes/locomo-frozen-v1.md`；
- 当前没有开放 actor 卡。下一步由架构师编写 B2 LongMemEval plan 与可复制 prompt，
  未完成并经用户确认前不派工。

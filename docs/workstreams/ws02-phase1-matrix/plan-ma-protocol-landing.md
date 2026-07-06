---
id: ws02
doc: plan (M-A)
status: approved
created: 2026-07-06
---
# ws02 M-A 实施计划：协议 v3 落地（实体 + 事件流 runner + 兼容桥）

执行者：Codex。设计依据：[spec-protocol-v3.md](spec-protocol-v3.md)（2026-07-06
已批准）。目标：v3 协议在代码中落地，**全程不破坏现有行为**——四个内置 method
经兼容桥零改动运行，回归保持 709 passed 基线。M-B（adapter 原生化）另有 plan。

## 施工纪律

1. 沿用 ws01 全部纪律：逐 task 勾选并附验收命令实际输出；遇 plan 未覆盖情况
   停工写断点；每 task 一个 commit；不改 `third_party/`；零真实 API。
2. **全程 TDD**：每个 task 先写红测试，再实现转绿；测试与实现同 commit。
3. 本 plan 不修改 evaluation 引擎、efficiency observation 语义、CLI 参数面；
   不删除任何现有类（旧 `BaseMemoryProvider` 原位保留，M-B 后再清理）。
4. 中文 docstring 规范照旧（`tests/test_documentation_standards.py` 必须保持通过）。

## T1 协议实体（红测先行）

- [x] 新模块 `src/memory_benchmark/core/provider_protocol.py`：
  `TurnEvent`、`TurnPair`、`SessionBatch`、`ConversationBatch`（联合类型
  `IngestUnit`）、`SessionRef`、`UnitRef`、`IngestResult`（含
  `session_memories: list[str] | None`）、`SessionMemoryReport`、
  `RetrievalQuery`（字段见 spec §2，purpose 枚举三值）、`RetrievedItem`
  （`item_id/content/score/timestamp/source_turn_ids`）、`RetrievalResult`
  （`formatted_memory` 必需 + `prompt_messages/items/metadata` 可选）、
  新 ABC `MemoryProvider`（类属性 `consume_granularity`、
  `session_memory_report=False`、`provenance_granularity="none"`；抽象方法
  仅 `ingest`/`retrieve`；`prepare/cleanup/end_session/end_conversation`
  默认 no-op）。全部 frozen dataclass、中文 docstring。
- [x] 校验规则进实体层：TurnEvent.metadata 禁私有键（复用
  `validate_no_private_keys()`）；RetrievalResult.formatted_memory 非空校验。
- 验收：`uv run pytest tests/test_provider_protocol.py -q` 新测试全绿（≥15 条，
  覆盖各实体构造、粒度-载荷对应、能力声明默认值、私有键拒绝）。

  验收输出（2026-07-06，T1）：

  ```bash
  $ uv run pytest tests/test_provider_protocol.py -q
  ...................                                                      [100%]
  19 passed in 0.04s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 0.48s
  ```

## T2 事件流生成与粒度聚合器

- [x] 新模块 `src/memory_benchmark/runners/event_stream.py`：
  `build_turn_events(conversation, isolation_key) -> Iterator[TurnEvent]`
  （按 session 顺序展开，session_time 继承到无 turn_time 的 turn，turn_id 取
  benchmark 稳定 id 否则 `s{si}t{ti}` 顺序号）；
  `GranularityAggregator`：输入 turn 事件流 + `consume_granularity`，产出
  投递序列（turn→逐个；pair→相邻 user/assistant 配对，落单 turn 单独成对并
  记 metadata；session→SessionBatch；conversation→ConversationBatch），并在
  正确位置产出 session/conversation 边界信号。
- [x] isolation_key 默认发放规则 `f"{run_id}_{conversation_id}"`，实现为可注入
  策略（benchmark registration 未来可覆盖，本 plan 只做默认值）。
- 验收：聚合器单测覆盖四种粒度 × 多 session/单 session/空 session/落单 turn
  边界情况；同一事件流在四种粒度下内容无损（重组后 turn 集合一致）。

  验收输出（2026-07-06，T2）：

  ```bash
  $ uv run pytest tests/test_event_stream.py -q
  ...............                                                          [100%]
  15 passed in 0.11s
  ```

  ```bash
  $ uv run pytest tests/test_provider_protocol.py -q
  ...................                                                      [100%]
  19 passed in 0.03s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 1.04s
  ```

## T3 兼容桥（关键任务：保住现有一切）

**架构师裁定（2026-07-06，解除 T3 断点）**：T1 的非空校验与 T3 的空串 fallback
确为 plan 内部矛盾（架构师撰写失误）。裁定：**实体校验保持严格**——
`formatted_memory` 非空是 unified 口径的基石不变量，不为桥接放宽；桥接层
fallback 链的末端改为**非空 sentinel 常量**，不用空串：

1. 在 `provider_protocol.py` 定义模块常量
   `BRIDGE_EMPTY_MEMORY_SENTINEL = "[bridge] legacy provider exposed no memory context"`。
2. 桥接 fallback 链：`metadata["answer_context"]` → `metadata["retrieved_memories"]`
   content 拼接 → **sentinel 常量** + `metadata["bridge_warning"]` 标记 +
   结构化 warning 日志。
3. runner 统计 sentinel 出现次数写入 summary（warning 级，不 fail）；真实 run 中
   出现 sentinel = 该 adapter 在 unified 口径可用前必须修复的信号。
4. 桥接期 `prompt_track` 固定 `native`（本 plan 既有要求），sentinel 永远不会
   进入任何 answer prompt，只存在于 artifact 数据字段。

理由：空串校验一旦放宽，v3 原生 provider 静默返回空记忆的 bug 将无法在实体层
拦截；sentinel 显式、可 grep、与真实记忆可区分，且桥接是临时态（M-B 原生化后
内置 method 不再走桥）。

- [x] `LegacyProviderBridge(MemoryProvider)`：`consume_granularity="conversation"`；
  `ingest(ConversationBatch)` → 重建旧 `Conversation` 对象调旧 `add()`；
  `retrieve(RetrievalQuery)` → 调旧 `retrieve(question)` 得 `AnswerPromptResult`，
  映射为 `RetrievalResult`：`prompt_messages` 原样、`formatted_memory` 按上方
  裁定的三级 fallback 链（末端 sentinel，绝不空串）。
  `RetrievalQuery.source_question` 还原为旧接口所需 `Question`。
- [x] registered prediction service：构造 provider 时检测其类型——旧式
  `BaseMemoryProvider` 自动包桥，新式 `MemoryProvider` 直用；manifest 新增
  `protocol_version`（bridge 时记 `v2-bridged`，原生记 `v3`）与
  `prompt_track`（当前固定 `native`）、`profile` 字段骨架。
- 验收：四个内置 method 的 fake/offline registered smoke 测试在桥接路径下
  全部通过，artifact 与迁移前语义一致（`method_predictions.jsonl`、
  `answer_prompts.prediction.jsonl` 关键字段对比测试）；
  `tests/test_prediction_runner.py tests/test_prediction_cli.py` 全绿。

  验收输出（2026-07-06，T3）：

  ```bash
  $ uv run pytest tests/test_legacy_provider_bridge.py -q
  ....                                                                     [100%]
  4 passed in 0.02s
  ```

  ```bash
  $ uv run pytest tests/test_prediction_runner.py tests/test_prediction_cli.py -q
  ........................................................................ [ 79%]
  ...................                                                      [100%]
  91 passed in 1.28s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 0.46s
  ```

## T4 runner 主链路切换到事件流

- [x] prediction runner 的 ingest 阶段改为：事件流生成 → 聚合器 → provider
  `ingest`/`end_session`/`end_conversation` 循环（normal path 与 isolated
  worker path 都切换）；conversation 级 resume 判定逻辑不变（unit 完成 =
  end_conversation 成功返回）。
- [x] `end_session` 返回的 SessionMemoryReport 与 `IngestResult.session_memories`
  写入新 artifact `artifacts/session_memory_reports.jsonl`（仅当 method 声明
  `session_memory_report=True`；声明 True 但从不报告 → 运行结束时报错，
  fail-fast 先例照抄 efficiency contract）。
- [x] `RetrievalResult.formatted_memory` 与 `items` 落盘进
  `answer_prompts.prediction.jsonl` 行（新增字段，旧字段不动）。
- 验收：`uv run pytest tests/test_prediction_runner.py -q` 全绿；新增事件流
  路径测试（含 isolated worker）；resume 语义回归（completed/failed/pending
  判定测试不变绿）。

  验收输出（2026-07-06，T4）：

  ```bash
  $ uv run pytest tests/test_prediction_runner.py -q
  ...............................................................          [100%]
  63 passed in 1.05s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 0.46s
  ```

## T5 MockMemoryProvider v3 与端到端离线验证

- [ ] 四种粒度各一个 mock provider（可参数化同一个类），覆盖：声明
  `session_memory_report=True` 并真实返回、`provenance_granularity="turn"`
  并在 items 回报 source_turn_ids。
- [ ] 端到端 fake smoke：mock v3 provider 走完整 registered prediction →
  evaluation 链路，验证新 artifact 字段与占位规范。
- 验收：新增测试全绿；`uv run pytest -q` **≥709 passed**（新增测试只增不减）；
  `uv run python -m compileall -q src/memory_benchmark tests` exit 0。

## T6 收尾

- [ ] 更新 `docs/reference/method-interface-inventory.md` 头部：注明 v3 协议
  已落地、四内置 method 当前经桥接运行、原生化见 M-B。
- [ ] 更新 ws02 README 断点与任务勾选，通知架构师审查。
- 验收：`git status --short` 干净；全部 commit 已按 task 切分。

## 明确不做（防发散）

- 不迁移任何内置 adapter 到原生 v3（M-B 范围）；不实现 unified prompt 口径的
  实际 prompt（三级来源的逐 benchmark 设计属 M-C/adapter spec）；不动
  evaluation 引擎与 efficiency 语义；不删旧接口；不做真实 API smoke；
  不实现 `retrieve_by` evidence recall 指标计算（只落盘 items 数据）。

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

- [ ] 新模块 `src/memory_benchmark/core/provider_protocol.py`：
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
- [ ] 校验规则进实体层：TurnEvent.metadata 禁私有键（复用
  `validate_no_private_keys()`）；RetrievalResult.formatted_memory 非空校验。
- 验收：`uv run pytest tests/test_provider_protocol.py -q` 新测试全绿（≥15 条，
  覆盖各实体构造、粒度-载荷对应、能力声明默认值、私有键拒绝）。

## T2 事件流生成与粒度聚合器

- [ ] 新模块 `src/memory_benchmark/runners/event_stream.py`：
  `build_turn_events(conversation, isolation_key) -> Iterator[TurnEvent]`
  （按 session 顺序展开，session_time 继承到无 turn_time 的 turn，turn_id 取
  benchmark 稳定 id 否则 `s{si}t{ti}` 顺序号）；
  `GranularityAggregator`：输入 turn 事件流 + `consume_granularity`，产出
  投递序列（turn→逐个；pair→相邻 user/assistant 配对，落单 turn 单独成对并
  记 metadata；session→SessionBatch；conversation→ConversationBatch），并在
  正确位置产出 session/conversation 边界信号。
- [ ] isolation_key 默认发放规则 `f"{run_id}_{conversation_id}"`，实现为可注入
  策略（benchmark registration 未来可覆盖，本 plan 只做默认值）。
- 验收：聚合器单测覆盖四种粒度 × 多 session/单 session/空 session/落单 turn
  边界情况；同一事件流在四种粒度下内容无损（重组后 turn 集合一致）。

## T3 兼容桥（关键任务：保住现有一切）

- [ ] `LegacyProviderBridge(MemoryProvider)`：`consume_granularity="conversation"`；
  `ingest(ConversationBatch)` → 重建旧 `Conversation` 对象调旧 `add()`；
  `retrieve(RetrievalQuery)` → 调旧 `retrieve(question)` 得 `AnswerPromptResult`，
  映射为 `RetrievalResult`：`prompt_messages` 原样、`formatted_memory` 取
  `metadata["answer_context"]`，缺失时由 `metadata["retrieved_memories"]` 的
  content 逐条拼接，再缺则空串加 warning metadata（不 fail，桥接期宽容）。
  `RetrievalQuery.source_question` 还原为旧接口所需 `Question`。
- [ ] registered prediction service：构造 provider 时检测其类型——旧式
  `BaseMemoryProvider` 自动包桥，新式 `MemoryProvider` 直用；manifest 新增
  `protocol_version`（bridge 时记 `v2-bridged`，原生记 `v3`）与
  `prompt_track`（当前固定 `native`）、`profile` 字段骨架。
- 验收：四个内置 method 的 fake/offline registered smoke 测试在桥接路径下
  全部通过，artifact 与迁移前语义一致（`method_predictions.jsonl`、
  `answer_prompts.prediction.jsonl` 关键字段对比测试）；
  `tests/test_prediction_runner.py tests/test_prediction_cli.py` 全绿。

## T4 runner 主链路切换到事件流

- [ ] prediction runner 的 ingest 阶段改为：事件流生成 → 聚合器 → provider
  `ingest`/`end_session`/`end_conversation` 循环（normal path 与 isolated
  worker path 都切换）；conversation 级 resume 判定逻辑不变（unit 完成 =
  end_conversation 成功返回）。
- [ ] `end_session` 返回的 SessionMemoryReport 与 `IngestResult.session_memories`
  写入新 artifact `artifacts/session_memory_reports.jsonl`（仅当 method 声明
  `session_memory_report=True`；声明 True 但从不报告 → 运行结束时报错，
  fail-fast 先例照抄 efficiency contract）。
- [ ] `RetrievalResult.formatted_memory` 与 `items` 落盘进
  `answer_prompts.prediction.jsonl` 行（新增字段，旧字段不动）。
- 验收：`uv run pytest tests/test_prediction_runner.py -q` 全绿；新增事件流
  路径测试（含 isolated worker）；resume 语义回归（completed/failed/pending
  判定测试不变绿）。

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

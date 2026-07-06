---
id: ws02
doc: plan (M-B)
status: approved
created: 2026-07-06
---
# ws02 M-B 实施计划：四个内置 adapter 原生化到协议 v3

执行者：Codex。依据：[spec-protocol-v3.md](spec-protocol-v3.md)（含 M-B 修订：
consume_granularity 实例级特化）、M-A 验收记录
（[notes/2026-07-06-ma-acceptance-review.md](notes/2026-07-06-ma-acceptance-review.md)）、
四张机制卡第 7 节形变记录。目标：Mem0 → LightMem → A-Mem → MemoryOS 逐个从
桥接切换为原生 `MemoryProvider`，**每一步用"调用序列等价测试"锁住官方行为**。

## 施工纪律

1. ws01/M-A 全部纪律照旧（TDD、每 task 一 commit、停工写断点、零 API、
   不改 third_party、中文 docstring）。
2. **等价性是本 plan 的灵魂**：每个 method 原生化的验收不是"测试绿"，而是
   "对同一 fake 数据，原生路径与桥接路径向第三方 runtime 发出的调用序列一致"
   （消息内容、顺序、时间戳、force 标志；namespace/隔离键允许按规则映射，
   断言其确定性而非字面相等）。旧 `add()`/`retrieve()` 实现**本 plan 内不删除**，
   保留用于对照（删除属后续清理）。
3. 全量回归基线 **758 passed**（M-A 验收后）；每 task 结束不得低于此值。

## T0 基线与语料补强

- [x] 记录 `uv run pytest -q` 基线（预期 758）。
- [x] 共享 fake 语料补强（M-A 验收遗留项）：给 runner/adapter fake 测试用的
  合成对话增加**含图片 caption 的 turn** 和**连续同 speaker 的 turn**，让
  caption 口径与配对边界进入常规回归。新增用例先证明桥接路径通过。
- 验收：新增语料用例全绿；全量回归 ≥758。

  验收输出（2026-07-06，T0）：

  ```bash
  $ uv run pytest -q
  ........................................................................ [  9%]
  ........................................................................ [ 18%]
  ........................................................................ [ 28%]
  ............................................................ [ 37%]
  ................................................................ [ 46%]
  ........................................................................ [ 56%]
  ...................................................................... [ 65%]
  ........................................................................ [ 75%]
  ........................................................................ [ 84%]
  ........................................................................ [ 94%]
  ............................................                             [100%]
  758 passed, 3 deselected, 2 warnings, 6 subtests passed in 104.15s (0:01:44)
  ```

  ```bash
  $ uv run pytest tests/test_legacy_provider_bridge.py::test_bridge_accepts_shared_fake_corpus_with_caption_and_repeated_speaker -q
  .                                                                        [100%]
  1 passed in 0.05s
  ```

  ```bash
  $ uv run pytest tests/test_legacy_provider_bridge.py tests/test_event_stream.py -q
  .....................                                                    [100%]
  21 passed in 0.07s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 0.51s
  ```

  ```bash
  $ uv run pytest -q
  ........................................................................ [  9%]
  ........................................................................ [ 18%]
  ........................................................................ [ 28%]
  .................................................................... [ 37%]
  ................................................................ [ 46%]
  ........................................................................ [ 56%]
  ...................................................................... [ 65%]
  ........................................................................ [ 75%]
  ........................................................................ [ 84%]
  ........................................................................ [ 94%]
  .............................................                            [100%]
  759 passed, 3 deselected, 2 warnings, 6 subtests passed in 98.55s (0:01:38)
  ```

## T1 等价性测试骨架

- [x] 新建 `tests/equivalence_utils.py`（或 tests 内共享模块）：给定
  recording fake runtime + 同一段公开 Conversation，分别驱动
  (a) 旧 adapter `add()`+`retrieve()`（桥接路径）与 (b) 新原生 provider
  `ingest()` 事件流路径，输出两份调用序列供断言比较。复用各 adapter 测试中
  已有的 recording fakes（如 fake Mem0 Memory、fake LightMemory）。
- 验收：骨架对至少一个现有 fake 跑通自比（桥接 vs 桥接 = 恒等）。

  验收输出（2026-07-06，T1）：

  ```bash
  $ uv run pytest tests/test_equivalence_utils.py -q
  .                                                                        [100%]
  1 passed in 0.06s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 0.50s
  ```

  ```bash
  $ uv run pytest -q
  ........................................................................ [  9%]
  ........................................................................ [ 18%]
  ........................................................................ [ 28%]
  .................................................................... [ 37%]
  ........................................................................ [ 46%]
  ........................................................................ [ 56%]
  ...................................................................... [ 65%]
  ........................................................................ [ 75%]
  ........................................................................ [ 84%]
  ........................................................................ [ 93%]
  ..............................................                           [100%]
  760 passed, 3 deselected, 2 warnings, 6 subtests passed in 102.83s (0:01:42)
  ```

## T2 Mem0 原生化

- [x] `Mem0Provider`（或在现 adapter 类上实现 `MemoryProvider`）：
  - 粒度：LoCoMo profile → `turn`；LongMemEval profile → `pair`
    （factory 按 build context 设实例属性，见 spec M-B 修订）。
  - `ingest(TurnEvent|TurnPair)`：复用现有 message 构造逻辑
    （speaker/时间/caption 拼接、observation-time prompt 注入），逐 unit 调
    `Memory.add(...)`；namespace 由 isolation_key 确定性派生。
  - `retrieve(RetrievalQuery)`：现有 search + 官方 prompt 构造迁移；
    `formatted_memory` = 现 `answer_context` 语义；`prompt_messages` 照旧；
    `provenance_granularity` 维持 `"none"`（Mem0 记忆为抽取事实，无 turn 锚点）。
  - 钩子：无需 `end_session`/`end_conversation`（同步型）。
- [x] 等价测试：LoCoMo fake（含图片 caption turn）与 LongMemEval fake 各一组，
  断言原生 vs 桥接的 `Memory.add` 消息序列与 `search` 调用一致。
- [x] registry factory 切换为原生构造；manifest `protocol_version` 变 `v3`。
- 验收：`tests/test_mem0_adapter.py` + 等价测试 + registered fake smoke 全绿；
  机制卡 mechanism-mem0.md 第 7 节形变逐条核对：因整段输入而生的拆分代码
  已移除或注明保留理由。

  验收输出（2026-07-06，T2）：

  ```bash
  $ uv run pytest tests/test_mem0_adapter.py::test_native_mem0_locomo_matches_bridge_add_and_search_sequence tests/test_mem0_adapter.py::test_native_mem0_longmemeval_matches_bridge_pair_sequence tests/test_mem0_adapter.py::test_mem0_registry_specializes_consume_granularity_by_benchmark -q
  ...                                                                      [100%]
  3 passed in 0.64s
  ```

  ```bash
  $ uv run pytest tests/test_mem0_adapter.py -q
  .......................                                                  [100%]
  23 passed in 1.05s
  ```

  ```bash
  $ uv run pytest tests/test_event_stream.py tests/test_legacy_provider_bridge.py tests/test_equivalence_utils.py -q
  ......................                                                   [100%]
  22 passed in 0.08s
  ```

  ```bash
  $ uv run pytest tests/test_prediction_runner.py::test_runner_ingests_native_v3_provider_with_event_stream_and_reports tests/test_prediction_runner.py::test_runner_bridges_legacy_provider_and_counts_empty_memory_sentinel tests/test_prediction_runner.py::test_isolated_worker_ingests_native_v3_provider_with_event_stream tests/test_prediction_cli.py::test_registered_prediction_builds_system_from_registry_context tests/test_prediction_cli.py::test_registered_prediction_allows_mem0_smoke_worker_override -q
  .....                                                                    [100%]
  5 passed in 0.57s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 0.56s
  ```

  ```bash
  $ uv run pytest -q
  ........................................................................ [  9%]
  ........................................................................ [ 18%]
  ........................................................................ [ 28%]
  .................................................................... [ 37%]
  ........................................................................ [ 46%]
  ........................................................................ [ 56%]
  ...................................................................... [ 65%]
  ........................................................................ [ 74%]
  ........................................................................ [ 84%]
  ........................................................................ [ 93%]
  .................................................                        [100%]
  763 passed, 3 deselected, 2 warnings, 6 subtests passed in 102.76s (0:01:42)
  ```

## T3 LightMem 原生化

- [x] 粒度：LoCoMo → `turn`（官方把每个原始 turn 包装为 user+assistant("")
  两条 message）；LongMemEval → `pair`。
- [x] **延迟一拍缓冲**实现官方"末批 force 标志"：ingest 持有上一 unit，收到
  下一 unit 时以 `force_segment=False, force_extract=False` 写出上一 unit；
  `end_conversation` 时把持有的最后 unit 以
  `force_segment=True, force_extract=True` 写出，LoCoMo 随后在同一钩子内执行
  `construct_update_queue_all_entries()` + `offline_update_all_entries(0.9)`。
- [x] 等价测试断言：批次划分、每批 force 标志、post-build 调用顺序与桥接
  路径完全一致（这是形变最重的 adapter，等价测试必须覆盖"最后一批"边界）。
- 验收：`tests/test_lightmem_adapter.py` + 等价测试 + registered fake smoke
  全绿；resume（completed conversation 重建 backend）行为不变。

  验收输出（2026-07-06，T3）：

  ```bash
  $ uv run pytest tests/test_lightmem_adapter.py::test_native_lightmem_locomo_matches_bridge_force_and_update_sequence tests/test_lightmem_adapter.py::test_native_lightmem_longmemeval_matches_bridge_pair_sequence tests/test_lightmem_adapter.py::test_lightmem_registry_specializes_consume_granularity_by_benchmark -q
  ...                                                                      [100%]
  3 passed in 0.47s
  ```

  ```bash
  $ uv run pytest tests/test_lightmem_adapter.py -q
  ..........................                                               [100%]
  26 passed, 1 warning in 4.14s
  ```

  ```bash
  $ uv run pytest tests/test_event_stream.py tests/test_legacy_provider_bridge.py tests/test_equivalence_utils.py -q
  ......................                                                   [100%]
  22 passed in 0.08s
  ```

  ```bash
  $ uv run pytest tests/test_prediction_runner.py::test_runner_ingests_native_v3_provider_with_event_stream_and_reports tests/test_prediction_runner.py::test_isolated_worker_ingests_native_v3_provider_with_event_stream tests/test_prediction_cli.py::test_registered_prediction_builds_system_from_registry_context -q
  ...                                                                      [100%]
  3 passed in 0.43s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 0.53s
  ```

  ```bash
  $ uv run pytest -q
  ........................................................................ [  9%]
  ........................................................................ [ 18%]
  ........................................................................ [ 28%]
  .................................................................... [ 37%]
  ........................................................................ [ 46%]
  ........................................................................ [ 55%]
  ...................................................................... [ 65%]
  ........................................................................ [ 74%]
  ........................................................................ [ 83%]
  ........................................................................ [ 93%]
  ....................................................                     [100%]
  766 passed, 3 deselected, 2 warnings, 6 subtests passed in 102.10s (0:01:42)
  ```

## T4 A-Mem 原生化

- [x] 粒度：`turn`。`ingest(TurnEvent)` → 拼 `Speaker X says: ...` 调
  `add_note(content, time)`；`end_conversation` → 现有 conversation 级状态
  持久化（memories.pkl / retriever cache / manifest）迁至此钩子。
- [x] `retrieve`：官方 query keyword generation + category k + LightMem-style
  LongMemEval 分支照旧迁移；category 5 拒绝逻辑保留。
- 验收：`tests/test_amem_adapter.py` + 等价测试全绿；持久化文件集与桥接路径
  逐字节语义一致（manifest 中 turn_count 等校验字段不变）。

  验收输出（2026-07-06，T4）：

  ```bash
  $ uv run pytest tests/test_amem_adapter.py::test_native_amem_matches_bridge_add_retrieve_and_state_sequence tests/test_amem_adapter.py::test_amem_registry_builds_native_v3_provider -q
  ..                                                                       [100%]
  2 passed in 0.37s
  ```

  ```bash
  $ uv run pytest tests/test_amem_adapter.py -q
  ...................                                                      [100%]
  19 passed, 1 warning in 7.89s
  ```

  ```bash
  $ uv run pytest tests/test_event_stream.py tests/test_legacy_provider_bridge.py tests/test_equivalence_utils.py -q
  ......................                                                   [100%]
  22 passed in 0.08s
  ```

  ```bash
  $ uv run pytest tests/test_prediction_runner.py::test_runner_ingests_native_v3_provider_with_event_stream_and_reports tests/test_prediction_runner.py::test_isolated_worker_ingests_native_v3_provider_with_event_stream tests/test_prediction_cli.py::test_registered_prediction_builds_system_from_registry_context -q
  ...                                                                      [100%]
  3 passed in 0.41s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 0.58s
  ```

  ```bash
  $ uv run pytest -q
  ........................................................................ [  9%]
  ........................................................................ [ 18%]
  ........................................................................ [ 28%]
  .................................................................... [ 36%]
  ........................................................................ [ 46%]
  ........................................................................ [ 55%]
  ...................................................................... [ 64%]
  ........................................................................ [ 74%]
  ........................................................................ [ 83%]
  ........................................................................ [ 92%]
  ......................................................                   [100%]
  768 passed, 3 deselected, 2 warnings, 6 subtests passed in 107.51s (0:01:47)
  ```

## T5 MemoryOS 原生化

- [x] 粒度：`session`。`ingest(SessionBatch)` → 现有
  `conversation_to_memory_pages()` 的 speaker 配对逻辑按 session 迁移
  （speaker_a→user_input、speaker_b→agent_response，含连续同 speaker 处理），
  逐页 `add_qa_pair()` + 满载迁移 + 热度检查；页时间戳继承 session_time。
- [x] `end_conversation`：无额外收尾（状态已随写入落盘）；确认 no-op 正确。
- [x] 等价测试断言：pages 序列（user_input/agent_response/timestamp）与桥接
  路径一致，含连续同 speaker 语料。
- 验收：`tests/test_memoryos_adapter.py` + 等价测试 + registered fake smoke 全绿。

  验收输出（2026-07-06，T5）：

  ```bash
  $ uv run pytest tests/test_memoryos_adapter.py::test_native_memoryos_session_ingest_matches_bridge_pages tests/test_memoryos_adapter.py::test_native_memoryos_preserves_consecutive_speaker_page_sequence tests/test_memoryos_adapter.py::test_memoryos_registry_builds_native_v3_provider -q
  ...                                                                      [100%]
  3 passed in 5.01s
  ```

  ```bash
  $ uv run pytest tests/test_memoryos_adapter.py -q
  ...................................................................... [ 50%]
  ....................................................................     [100%]
  138 passed, 2 subtests passed in 8.17s
  ```

  ```bash
  $ uv run pytest tests/test_event_stream.py tests/test_legacy_provider_bridge.py tests/test_equivalence_utils.py -q
  ......................                                                   [100%]
  22 passed in 0.08s
  ```

  ```bash
  $ uv run pytest tests/test_prediction_runner.py::test_runner_ingests_native_v3_provider_with_event_stream_and_reports tests/test_prediction_runner.py::test_isolated_worker_ingests_native_v3_provider_with_event_stream tests/test_prediction_cli.py::test_registered_prediction_builds_system_from_registry_context -q
  ...                                                                      [100%]
  3 passed in 0.43s
  ```

  ```bash
  $ uv run pytest tests/test_documentation_standards.py -q
  .....                                                                    [100%]
  5 passed in 0.55s
  ```

  ```bash
  $ uv run pytest -q
  ........................................................................ [  9%]
  ........................................................................ [ 18%]
  ........................................................................ [ 28%]
  .................................................................... [ 36%]
  ........................................................................ [ 46%]
  ........................................................................ [ 55%]
  ...................................................................... [ 64%]
  ........................................................................ [ 73%]
  ........................................................................ [ 83%]
  ........................................................................ [ 92%]
  .........................................................                [100%]
  771 passed, 3 deselected, 2 warnings, 6 subtests passed in 105.47s (0:01:45)
  ```

## T6 收尾

- [ ] 四 method registry 均产出原生 v3 provider；`LegacyProviderBridge` 保留
  （服务未来外部旧式 provider），内置路径不再经过它。
- [ ] 更新 `docs/reference/method-interface-inventory.md`（四 method v3 原生）
  与 ws02 README 断点；机制卡第 7 节各追加"原生化后状态"小节（一句话/条）。
- [ ] 全量回归 + compileall + `git status` 干净。
- 验收：`uv run pytest -q` ≥758；四个 method 的 fake registered smoke 的
  manifest `protocol_version=v3`。

## 明确不做

- 不删除旧 `add()`/`get_answer()`/桥接类（清理属 ws03）；不做真实 API smoke
  （M-B 后由用户确认预算，按 spec §9.2 跑 LoCoMo/LongMemEval 极小对照）；
  不实现 unified prompt；不动 6 个新 method（Track C 范围）。

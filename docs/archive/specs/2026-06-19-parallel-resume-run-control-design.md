# 并行 Resume 与分批运行控制设计

## 目标

让 conversation + QA prediction 在以下场景中都能安全恢复：

- 串行运行。
- conversation 级并行运行。
- 非共享实例 method 的 isolated worker 并行运行。
- 多个 method × benchmark child run 的外层并行运行。

同时新增一个运行控制选项：本次命令只推进指定数量的未完成 conversation，完成后正常退出；
后续可用同一个 `run_id` 和 `--resume` 继续后面的 conversation。

## 术语

### 实验 identity

实验 identity 是决定结果是否可比较、是否允许 resume 的不可变信息，包括：

- dataset fingerprint 与 benchmark variant。
- method 配置、源码 identity 和 reader/prompt identity。
- run scope、question limit、观测契约等会改变 artifact 语义的配置。

这些字段进入 prediction manifest。resume 时只要不同，就必须拒绝。

### 本次运行预算

`max_new_conversations` 是本次命令的运行预算，只限制“这一次最多推进多少个尚未完成的
conversation”。它不定义实验本身，不进入 manifest identity。

例子：

```text
第一次: predict --run-id exp1 --max-new-conversations 2
  处理 conv-1, conv-2 后正常退出

第二次: predict --run-id exp1 --resume --max-new-conversations 5
  从 conv-3 开始继续处理 5 个未完成 conversation

第三次: predict --run-id exp1 --resume
  处理剩余全部 conversation
```

三次仍然属于同一个实验 `exp1`。如果把 `max_new_conversations` 写进 manifest，第二次
把 2 改成 5 会被误判为不兼容，反而破坏分批续跑。

## 当前问题

normal prediction path 已经支持：

- `conversation_status.json` 跳过已完成写入的 conversation。
- `method_predictions.jsonl` 跳过已回答的问题。
- Mem0 LoCoMo 的 turn-level ingest checkpoint。
- method factory 根据 `completed_conversations` 恢复已完成写入的 conversation state。

isolated worker path 当前缺失这些能力：

- worker context 使用 `completed_conversations=()`，method 无法恢复已写入的 conversation。
- 不读取 `conversation_status.json`，会重复 `add()` 已完成 conversation。
- 不过滤 `prediction_records`，会重复 `get_answer()` 已完成 question。
- 没有 turn checkpoint 预检，不能安全支持 turn-level resume。
- progress 计数从 0 开始，resume 时可能重复计数。

## 决策

### 保留 Mem0 LoCoMo turn-level resume

Mem0 LoCoMo turn-level resume 当前是可接受的：

- LoCoMo profile 使用官方 `CHUNK_SIZE=1`。
- checkpoint 对 turn index、turn id、状态迁移做强校验。
- 遇到 `in_flight` 状态 fail closed，不猜测恢复点。

因此不把 Mem0 LoCoMo 降级成 conversation-level resume。Mem0 LongMemEval 继续使用
conversation-level resume，因为官方写入粒度是 user+assistant pair，不适合当前 turn-level
checkpoint 语义。

### isolated worker 只做 conversation-level resume

isolated worker 的第一版目标是服务 MemoryOS、A-Mem、LightMem 这类非共享实例 method。
它们当前不需要 turn-level checkpoint。

如果 isolated worker 发现本 run 中存在 turn-level checkpoint，应直接报错，提示该
run 不能通过 isolated worker 恢复。这样避免错误地重放半个 conversation。

### `max_new_conversations` 按未完成 conversation 计算

未完成 conversation 定义：

- conversation 还没有完成 `add()`；或
- conversation 已完成 `add()`，但还有 selected question 没有 prediction。

预算在 resume 状态加载后计算，并按 dataset conversation 顺序选择前 N 个未完成
conversation。已完全完成的 conversation 不占预算。

## 架构

### 新增工作规划层

在 `src/memory_benchmark/runners/prediction.py` 中新增内部工作规划结构，例如：

```python
@dataclass(frozen=True)
class _ConversationWorkItem:
    conversation: Conversation
    needs_ingest: bool
    pending_questions: tuple[Question, ...]
```

规划函数负责统一计算：

- selected conversation。
- selected question。
- 已完成 ingest 的 conversation id。
- 已完成 prediction 的 question id。
- 本次预算允许的 unfinished conversation。

normal path 和 isolated path 都消费同一个 work plan。

### normal path

normal path 继续复用现有两阶段结构：

```text
ingest pending conversations
answer pending questions
```

区别是输入已经被 work plan 裁剪：

- 超出本次预算的 conversation 不提交给 executor。
- 已完成 prediction 的 question 不再进入 answer 阶段。
- 已完成 ingest 但 question 未答完的 conversation 不再 `add()`，但会进入 answer 阶段。

### isolated worker path

isolated worker 每个 worker 处理一个 work item chunk：

```text
worker context
  completed_conversations = chunk 中已完成 ingest 的 conversation

for item in chunk:
  if item.needs_ingest:
      system.add([public_conversation])
  for question in item.pending_questions:
      system.get_answer(question)
```

协调线程仍然是唯一 artifact writer，负责串行写入：

- `method_predictions.jsonl`
- `question_status.jsonl`
- `conversation_status.json`
- efficiency observations
- progress

### 外层 method × benchmark 并行

`calibrate-smoke` 和未来实验矩阵 orchestrator 只负责启动独立 child run。

- `max_parallel_runs`: 外层同时运行多少个 child run。
- `max_workers`: 每个 child run 内部 conversation 并发。
- `max_new_conversations`: 每个 child run 本次最多推进多少个未完成 conversation。

三者互不替代。总活跃压力约等于：

```text
max_parallel_runs × max_workers
```

命令行和日志必须明确打印这个并发规模。

## Artifact 与状态

`max_new_conversations` 不写入 manifest identity，但应写入可变运行状态，便于审计：

- `logs/events.jsonl`: 记录本次 run control。
- `checkpoints/progress.json`: 记录预算内进度。
- `summaries/summary.json`: 可增加 `metadata.run_control`，记录本次预算和是否预算耗尽。

不需要新建 method-specific artifact。

## 错误处理

- `max_new_conversations < 1` 时报 `ConfigurationError`。
- isolated worker 遇到 turn-level checkpoint 文件时报 `ConfigurationError`。
- resume 时如果 manifest identity 不匹配，继续沿用现有 fail-closed 行为。
- 如果本次没有未完成 conversation，命令应正常退出并写 summary，不调用 method。
- 如果某个 worker 失败，协调线程不得写入该 worker 的部分结果；已完成 worker 的结果可以保留，
  下次 resume 跳过已完成部分。

## 测试策略

优先离线测试，不触发真实 API：

1. normal path：`max_new_conversations=2` 只处理前两个未完成 conversation。
2. normal path resume：第一次处理 2 个，第二次 resume 继续后两个，不重复已答 question。
3. isolated path：已完成 ingest 的 conversation 会传入 worker context 并只答剩余问题。
4. isolated path：已完成 question 不会重复调用 `get_answer()`。
5. isolated path：存在 turn checkpoint 时 fail closed。
6. CLI：`--max-new-conversations` 透传到 `PredictionRunPolicy`。
7. calibrate-smoke：预算按 child run 生效，不改变 `max_parallel_runs`。
8. Mem0 LoCoMo turn-level resume 既有测试继续通过。

## 非目标

- 不在本阶段实现进程级隔离。
- 不把 `max_new_conversations` 写进 method TOML。
- 不为每个 method × benchmark 写专用 runner。
- 不改变 Mem0 LoCoMo turn-level resume 策略。
- 不启动真实 API smoke 或 full 实验。

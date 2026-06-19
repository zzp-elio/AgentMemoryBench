# A-Mem Conversation State Persistence Design

## 背景

A-Mem 当前 adapter 会为每个 `conversation_id` 创建一个官方
`RobustAgenticMemorySystem` runtime。该 runtime 的记忆状态主要保存在进程内：

- `runtime.memories`
- `runtime.retriever`

runner 已能通过 `conversation_status.json` 跳过完成过的 conversation，也能通过
`method_predictions.jsonl` 跳过完成过的 question。但如果 Python 进程重启，A-Mem
内部记忆状态会丢失，导致后续 `get_answer()` 无法继续使用已写入的 conversation。

## 目标

为 A-Mem 增加 wrapper 层 conversation 级状态持久化，使已完成写入的 conversation
可以在 resume 时重新加载到 A-Mem runtime 中。

## 非目标

- 不实现 turn-level resume。
- 不修改 `third_party/methods/A-mem/` 中的核心算法。
- 不改变 A-Mem 的 `add_note()`、evolution、retrieval、query keyword generation 或
  answer prompt 调用顺序。
- 不支持从不可信外部目录加载 pickle 状态。

## 设计

A-Mem adapter 接收当前 run 的 `storage_root`，每个 conversation 使用独立目录：

```text
outputs/<run_id>/method_state/<safe_conversation_id>/
  memories.pkl
  retriever.pkl
  retriever_embeddings.npy
  state_manifest.json
```

`add([conversation])` 完整写入一个 conversation 后立即保存：

- `memories.pkl`: 官方 runtime 的 `memories` dict。
- `retriever.pkl` 与 `retriever_embeddings.npy`: 优先调用官方
  `runtime.retriever.save(...)`。
- `state_manifest.json`: 保存 `conversation_id`、adapter version、source hash、
  profile manifest、turn_count、文件 checksum 和 schema version。

resume 时，registry 把 runner 已确认 completed 的 conversations 传给 A-Mem factory。
factory 创建 `AMem` 后调用：

```python
system.load_existing_conversation_state(conversation)
```

该方法会：

1. 强校验 `state_manifest.json` 存在且 conversation id/profile/source identity 匹配。
2. 校验状态文件 checksum。
3. 创建官方 runtime。
4. 把 `memories` 和 `retriever` 加载回 runtime。
5. 把 runtime 放入 `self._runtimes[conversation_id]`。

## 错误处理

- 状态文件缺失、checksum 不匹配、profile/source identity 不匹配时抛
  `ConfigurationError`。
- 若官方 retriever 没有 `save/load` 能力，保存或加载时显式报错，不静默降级。
- 若 conversation 还没有完成写入，不写 completed manifest，不让 runner 误以为可恢复。

## 测试策略

- fake runtime + fake retriever 验证 `add()` 后写出四个状态文件。
- 新 adapter 实例从同一 `storage_root` 加载已完成 conversation 后，`get_answer()` 能
  使用恢复的 runtime。
- 修改 manifest 的 profile/source identity/checksum 后，加载必须失败。
- registry factory 必须对 `completed_conversations` 调用 A-Mem 的加载路径。

## 成功标准

- A-Mem 可实现 conversation-level resume。
- 不影响现有 A-Mem fake/offline runner smoke。
- 不启动真实 API。

# Turn-Level Ingest Resume Design

状态：已确认，进入实施  
日期：2026-06-12

## 目标

为长 conversation 写入提供逐 turn 断点。已确认成功的 turn 不重复调用 method；
写入结果不确定的 turn 不自动重试，避免重复记忆和额外 API 成本。

## 公共接口边界

`BaseMemorySystem.add()` 和 `get_answer()` 保持不变。新增可选子接口：

```python
class BaseResumableMemorySystem(BaseMemorySystem):
    def add_from_turn(
        self,
        conversation: Conversation,
        start_turn_index: int,
        on_turn_started: Callable[[int, Turn], None],
        on_turn_completed: Callable[[int, Turn], None],
    ) -> AddResult:
        ...
```

runner 只在 `isinstance(system, BaseResumableMemorySystem)` 时启用逐 turn checkpoint。
普通 method 继续按完整 conversation 调用 `add()`。

turn index 是按 `sessions` 原顺序展开后的零基索引。`start_turn_index` 表示下一条尚未确认
成功的 turn。

## Checkpoint 布局

```text
checkpoints/ingest_turns/<sha256(conversation_id)>.json
```

使用 hash 文件名防止 conversation id 包含 `/`、`..` 或其它路径字符。JSON 保存：

```json
{
  "schema_version": 1,
  "conversation_id": "conv-26",
  "status": "ready",
  "next_turn_index": 3,
  "total_turns": 419,
  "current_turn_index": null,
  "current_turn_id": null
}
```

状态机：

- 无文件：从 turn 0 开始。
- `ready`：从 `next_turn_index` 继续。
- `in_flight`：上次已进入 method 调用但没有确认返回，拒绝自动 resume。
- `completed`：全部 turn 已确认成功；若 conversation 总状态尚未提交，runner 只补交完成态。

所有状态使用现有 `atomic_write_json()` 写入。不同 worker 只写各自 conversation 的独立
文件，不并发改共享 JSONL。

## 写入顺序

对于 turn `i`：

1. runner callback 原子写 `status=in_flight`、`next_turn_index=i` 和当前 turn id。
2. Mem0 调用官方 `Memory.add()`。
3. 调用成功返回后，runner callback 原子写 `status=ready`、
   `next_turn_index=i+1`。
4. 全部 turn 完成后写 `status=completed`。
5. 协调线程再更新共享 `conversation_status.json`。

因此：

- API 调用前崩溃：checkpoint 可能是 `in_flight`，保守停止。
- API 调用后、客户端收到响应前超时：`in_flight`，保守停止。
- API 成功且 `ready` 已原子落盘：resume 从下一 turn 开始。
- 全部写完但协调线程未提交：`completed` 可安全补交。

## Mem0 行为

`Mem0.add()` 复用 `add_from_turn(..., start_turn_index=0)`，不改变正常调用语义。

部分恢复时：

- `start_turn_index > 0` 表示 namespace 已存在。
- adapter 将 conversation id 附着到当前实例的已写入集合，不重复清空或创建 namespace。
- 后续 turn 继续使用相同 `run_id=conversation_id`、时间锚点和 metadata。

## 强校验

以下情况立即抛 `ConfigurationError`：

- checkpoint schema/status 非法。
- checkpoint conversation id 不匹配。
- `next_turn_index` 越界。
- checkpoint 的 `total_turns` 与当前 conversation 不一致。
- `in_flight` 状态尝试 resume。
- 存在部分 checkpoint，但 method 不支持 resumable 子接口。
- `start_turn_index > 0` 却没有任何已确认 turn。

`in_flight` 不提供自动覆盖、自动重试或概率性去重兜底。人工处理方案后续单独设计。

## 测试

1. Mem0 从指定 turn index 开始，前序 turn 不调用 backend。
2. 每个 turn 严格执行 started callback -> backend -> completed callback。
3. 第二个 turn 故障后 checkpoint 保持 `in_flight`。
4. `ready` resume 只写剩余 turn。
5. `in_flight` resume 在任何 method/API 调用前失败。
6. `completed` checkpoint 可补齐 conversation 状态。
7. 两 conversation 并发写入不同 checkpoint 文件。
8. 非 resumable method 保持原有行为。
9. 默认全量回归与 API test collect 通过，不重新运行付费 smoke。

## 非目标

- 不自动判断服务端是否已处理超时请求。
- 不修改第三方 Mem0 源码。
- 不把 turn-level add 升格为所有 method 必须实现的公共接口。
- 不为 question 回答新增更细 checkpoint；现有 question 级 artifact 已可恢复。

# API 兜底与并行 Worker 失败语义设计

日期：2026-06-20

## 背景

Mem0 LoCoMo full v3 在 `conv-43` 的 OpenAI-compatible embedding API 调用中发生
SSL `APIConnectionError`。这暴露出两个问题：

1. 长实验不能因为一次网络抖动直接报废。
2. conversation 并行 worker 的失败语义不能简单等同于整个 run 失败。

本设计只覆盖 conversation + QA prediction 阶段，不改变 benchmark adapter、metric
计算或第三方 method 的核心算法。

## 目标

- 所有涉及 API 或网络请求的路径必须有明确 timeout、retry 和错误记录。
- conversation 级并行运行时，一个 conversation 失败不应默认中止所有正常
  conversation。
- `--max-new-conversations` 表示本次命令最多尝试的 eligible conversation 数，不表示
  必须成功完成数。
- `--retry-failed` 只把历史 failed conversation 重新纳入 eligible 队列；同一次 run 内
  每个 conversation 仍然最多尝试一次。
- 默认 resume 不重跑 failed conversation，避免失败项反复空烧 API。

## 非目标

- 不实现 turn-level resume。
- 不让失败 conversation 在同一次 run 内被其他 worker 接手重试。
- 不动态抢任务队列；当前先保留稳定 worker state root 映射。
- 不在本阶段实现跨 method × benchmark 的全局成本调度器。

## Worker 调度语义

runner 先根据 checkpoint 和本次命令参数生成 work plan：

```text
eligible = selected conversations
           - completed conversations
           - failed conversations, unless --retry-failed is set
```

如果设置 `--max-new-conversations=N`，则本次最多从 eligible 中选择 N 个 conversation。
这 N 个 conversation 最终可能成功，也可能失败。

示例：

```text
total conversations = 10
max_workers = 4
max_new_conversations = 4

本次最多尝试 4 个 conversation。
结果可能是 3 completed + 1 failed，而不是必须完成 4 个。
```

每个 conversation 在同一次 run 内只属于一个 worker，且最多尝试一次。`--retry-failed`
不会改变这个规则。

## Worker 数量边界

实际启动 worker 数量必须小于等于本次有工作的 conversation 数：

```text
actual_workers = min(configured_workers, number_of_non_empty_work_chunks)
```

如果 `max_workers=4` 但本次只有 2 个 conversation，则只启动 2 个非空 worker。

## 失败分类

### 全局错误

以下错误应 fail-fast，直接停止整个 run：

- 配置错误，例如缺 API key、base_url 非法、参数类型错误。
- source identity 或 manifest 不兼容。
- dataset 必填字段缺失或 private/public 边界违规。
- 第三方依赖缺失。
- method 构造阶段失败。
- 无法创建标准输出目录、checkpoint 或 artifact。

这些错误通常不是单个 conversation 的问题，继续跑只会批量失败或污染状态。

### Conversation 局部错误

以下错误默认归属于当前 conversation：

- 当前 conversation 的 `add()` 失败。
- 当前 conversation 的某个 `get_answer()` 失败。
- API/network 错误在达到最大 retry 后仍失败。
- 第三方 method 对当前 conversation 数据抛出可定位异常。

处理方式：

```text
标记当前 conversation failed
记录 stage / error_type / error / traceback
当前 worker 继续处理自己后续 conversation
其他 worker 不受影响
```

## Retry 与 Timeout

所有 API/network 调用路径都应有可配置的 timeout 与 retry：

- LLM answer 调用。
- LLM judge 调用。
- method memory-build 内部 LLM 调用。
- embedding API 调用。
- 第三方 method 暴露的 OpenAI-compatible client。

retry 只处理 transient 错误，例如：

- `APIConnectionError`
- SSL EOF / connection reset
- timeout
- 429
- 5xx

以下错误不 retry：

- 配置错误
- schema/validation 错误
- public/private 边界错误
- 4xx 中明显不可恢复的认证、权限或参数错误

## 熔断

为避免全局网络或配置问题导致批量空烧 API，prediction policy 需要支持连续失败熔断：

```text
max_consecutive_failures
```

达到阈值后停止整个 run，并在 summary / events 中记录熔断原因。默认值应保守，建议从
3 开始。

## Resume 语义

默认 resume：

```text
跳过 completed
跳过 failed
继续 unfinished
```

显式 `--retry-failed`：

```text
跳过 completed
把 failed 和 unfinished 一起纳入 eligible
但同一次 run 内每个 conversation 仍然最多尝试一次
```

## Artifact 与日志

conversation 失败时必须写入：

- `checkpoints/conversation_status.json`
- `logs/events.jsonl`
- `checkpoints/progress.json`

字段至少包括：

```json
{
  "status": "failed",
  "stage": "isolated_worker",
  "error_type": "...",
  "error": "...",
  "traceback": "..."
}
```

summary 中应能区分：

- total selected conversations
- attempted conversations
- completed conversations
- failed conversations
- skipped failed conversations
- budget exhausted

## 实施顺序

1. 补 Mem0 embedding / LLM API timeout 与 retry，优先解决已暴露事故。
2. 把 isolated worker failure policy 从全局 fail-fast 改为 conversation 局部失败
   continue。
3. 增加 `max_consecutive_failures` 熔断。
4. 补测试覆盖 `max_new_conversations`、`--retry-failed`、worker > conversation、
   conversation failed 后 worker 继续后续 conversation。
5. 之后再评估是否给其他 method 做更深的第三方内部 API observer / retry hook。

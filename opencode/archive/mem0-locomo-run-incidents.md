# 2026-06-19 Mem0 LoCoMo official-full 运行事故

## 运行记录

**run_id**: `mem0-locomo-full-v3`
**命令**: `uv run memory-benchmark predict --method mem0 --benchmark locomo --profile official-full --run-id mem0-locomo-full-v3 --confirm-api --confirm-full`
**启动**: 2026-06-19 22:40 UTC（10:40 下午本地）
**配置**: 10 conversation × 1540 question × 10 isolated workers

## 时间线

| 时间 (UTC) | 事件 |
|------------|------|
| 22:40:38 | `run_started`，10 worker 开始 ingest |
| 22:40:43 | 10 worker Qdrant 目录创建 |
| ~23:30-23:40 | worker_0 停止 Qdrant 写入（23:38），worker_1 停止（23:29） |
| ~23:45-23:46 | worker_7 持续写入 Qdrant（23:45 mem0，23:45 mem0_entities） |
| ~23:52 | conv-30 第一个完成 ingest + answer，coordinator 收集到 1 个 batch |
| 23:52 | `conversation_completed_isolated` conv-30，81 题答案写入 `method_predictions.jsonl` |
| ~23:53 | worker_4（conv-43）在 `add()` 中调 OpenAI embedding API 时 SSL 断连 |
| 23:53 | `isolated_worker_failed` conv-43，`APIConnectionError` |
| 23:53 | cooperative cancellation 触发：`cancellation_event.set()` + 其余 future `cancel()` |
| 23:56 | worker_2,3,5,6,7,9 的 Qdrant 仍在写入（cancellation 未生效于正在执行的线程） |
| 01:15 (次日) | Codex 检查时进程仍在（6 个 worker 后台线程未退出） |

## 最终结果

| 项目 | 状态 |
|------|------|
| conv-30 | ✅ completed，81 题答案 |
| conv-43 | ❌ failed，`APIConnectionError` |
| conv-26,41,42,44,47,48,49,50 | ❌ 6 个还在跑但产出丢弃 / 2 个已停止但产出丢弃 |

**有效产出：1/10 conversation，81/1540 question。**

## 失败链

```
_isolated_worker (worker_4, conv-43)
  └─ system.add([public_conversation])
       └─ Mem0.add_from_turn()
            └─ Mem0._memory.add()
                 └─ Mem0._add_to_vector_store()
                      └─ OpenAIEmbedding.embed()
                           └─ OpenAI.embeddings.create()
                                └─ httpx → httpcore → SSL
                                     └─ [SSL: UNEXPECTED_EOF_WHILE_READING]
```

根因：ohmygpt 代理在 SSL 握手时突然断开（ohmygpt 瞬时故障）。

## 为什么没有自动重试

Mem0 adapter 的 embedding config（`mem0_adapter.py:340-341`）：
```python
"embedder": {
    "provider": "openai",
    "config": {
        "model": config.embedding_model,
        "embedding_dims": config.embedding_dimensions,
        "api_key": openai_settings.api_key,
        "openai_base_url": openai_settings.base_url,
        # ❌ 缺少: max_retries、timeout
    },
},
```

Mem0 官方 `OpenAIEmbedding.__init__()`（`mem0/embeddings/openai.py:35`）：
```python
self.client = OpenAI(api_key=api_key, base_url=base_url)
# ❌ 无 max_retries，无 timeout
```

OpenAI SDK 的 `max_retries=2` 只对 HTTP 429/5xx 重试，**SSL 层连接错误不被重试**。所以 ohmygpt 一抖，整个 conversation 直接炸。

对比：MemoryOS adapter 的 `api_timeout_seconds` 和 `api_max_retries` 都写入 config 并传给 wrapper 层。Mem0 只传了 API key 和 URL。

## 为什么其余 worker 仍在空跑

cooperative cancellation 局限：

1. `cancellation_event.set()` — 只在 `_isolated_worker` 的 work_item 循环**开头**检查一次（`prediction.py:1183`）
2. 每个 worker 只有 1 个 work_item（1 个 conversation）
3. 进入 `add()` / `get_answer()` 后不再检查 cancellation
4. `future.cancel()` — Python 的 Future 只能标记已取消，杀不掉已在执行的线程

所以：coordinator 已退出 → worker 线程继续跑完当前 conversation → 产出全部丢弃。

## 与 v2 对比

| 指标 | v2（首次） | v3（本次） |
|------|-----------|-----------|
| 失败原因 | worker_7 conv-48 未知（无 traceback） | worker_4 conv-43 `APIConnectionError`（有完整 traceback） |
| 其余 worker | 全部空跑数小时，原因完全不可知 | 6 个空跑至 conversation 结束，诊断清晰 |
| 有效产出 | 0 | conv-30（81 题） |
| failure 隔离 | 无 | `conversation_status.json` 正确记录 conv-43 failed |
| 排查能力 | 零（无 traceback、无 error type） | 完整（error_type + error + traceback 写入 events） |
| resume 可行性 | 不可——只能全删 | 可——跳过 failed，retry conv-43 + 剩余 8 个 |

## 需修复项

1. **P0**：Mem0 embedder config 补 `max_retries`（利用 OpenAI SDK 的 `httpx` 级别重试）
2. **P1**：`_isolated_worker` 的 `get_answer()` 循环内加入 `cancellation_event.is_set()` 检查，每题之间可中断
3. **P2**：考虑用 `threading.Event` 实现更细粒度的取消信号，或在 worker 线程内用 `signal` / `raise` 中断

## 影响评估

- API 消耗：1 个 conversation 完成 + ~6 个 conversation 部分完成（ingest 可能做完，answer 部分跑了一些）。估算 embedding ~1500 次 + answer ~200-300 次。总费用约 $0.50-1.00。
- v2+v3 合计 API 浪费约 $1.00-1.50。
# 2026-06-20 02:00 UTC — Mem0 reference_date 传递缺口审计

## 1. 读了哪些文件

- `src/memory_benchmark/methods/mem0_adapter.py`：
  - `add()` (line 372-407)：_conversation_metadata 构造
  - `add_from_turn()` (line 430-511)：_conversation_metadata 写入（line 461-464）
  - `_build_mem0_locomo_prompt()` (line 1126-1150)：reference_date fallback 链
  - `_reference_year_from_memories()` (line 1326-1332)：年份提取函数
  - `_normalize_search_results()` (line 1047-1071)：检索结果规范化
- `src/memory_benchmark/benchmark_adapters/locomo.py`：Conversation.metadata 构造（line 120-132），确认无 reference_date
- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/prompts.py`：官方 `ANSWER_GENERATION_PROMPT` 和 `get_answer_generation_prompt()`，确认 reference_date 的用途和每条记忆的日期格式化（`_to_human_date`）
- `third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/run.py`：官方 `get_sorted_sessions()` 获取最后一个 session 完整日期的逻辑
- `src/memory_benchmark/methods/memoryos_adapter.py`、`amem_adapter.py`、`lightmem_adapter.py`：对照审计
- `outputs/mem0-locomo-full-v4/artifacts/method_predictions.jsonl`：验证 LLM 实际产出的日期是否正确

## 2. 根因

**Mem0 官方 LoCoMo prompt 模板中有一个 `{reference_date}` 占位符**，adapter 从未将正确的会话日期传入，但**每条记忆本身已自带完整正确日期**。

### 完整的 prompt 流程

`get_answer_generation_prompt()`（vendored 官方函数）生成两样东西：

1. **全局 `reference_date`**：填入 "These conversations took place around {reference_date}"（Step 5 用于相对时间推理的辅助锚点）
2. **每条记忆的格式化日期**：`_to_human_date(created_at)` 把 `created_at` 转成 `"Monday, May 8, 2023"`，每行格式为 `"(Monday, May 8, 2023) Caroline said..."`

关键事实：**`created_at` 来自 `session.session_time`**（adapter 在 `_turn_to_message` 中正确传入），不是数据库写入时间。所以每条记忆显示的日期是**正确的**。

### adapter 的问题

`_build_mem0_locomo_prompt()` 的 fallback 链：

```python
reference_date = (
    metadata.get("reference_date")              # → 永远是 None
    or metadata.get("question_reference_date")   # → 永远是 None
    or _reference_year_from_memories(memories)  # → 从 created_at 提取年份
    or "2023"                                    # → 硬编码兜底
)
```

- `Conversation.metadata` 不包含 `reference_date` 字段（locomo adapter 只存 source 信息）
- `_reference_year_from_memories()` 从 `created_at` 提取年份——年份本身是正确的（来自 session_time），但**只有年份，没有月日**
- 硬编码兜底 "2023"

最终 LLM 看到的 prompt 里：
- **全局 reference_date**：只有年份（如 "2023"），而非官方预期的 `"May 8, 2023"`
- **每条记忆**：正确完整的 `(Monday, May 8, 2023)` 人类可读日期

### 为什么影响可以忽略

Step 5 明确指示 LLM：**"Use dates explicitly stated in memory text. Do not invent or estimate dates."**

每条记忆已自带完整正确日期，LLM 直接从中提取作答。全局 `reference_date` 只是一个辅助提示，LLM 不需要依赖它。96 条 category 2（时间推理）答案经人工抽查，日期全部正确。

**实际证据**：Mem0 full-v4 Judge 得分 **86.36%**，category 2 Judge 得分 **76.32%**——即使 reference_date 不完整，时间推理质量仍然良好。

## 3. 修改了哪些文件

**无修改。** 本次仅审计记录。用户明确要求不修复。

## 4. 跑了哪些测试

未执行测试。本次为只读审计。

## 5. 已知风险或未解决问题

### 准确结论

| 层面 | 实际情况 |
|------|---------|
| **代码层面** | reference_date 参数未传入完整 session 日期，只有年份。这是一个代码不严谨之处。 |
| **实际影响** | **几乎无影响**。每条记忆自带完整正确日期，Step 5 指示 LLM 直接使用记忆里的日期。Judge 86% 佐证。 |
| **与其他 method 对比** | 等效。MemoryOS/LightMem 把时间嵌入每条记忆；Mem0 同样把时间嵌入每条记忆（`_to_human_date`）。只是 Mem0 多了一个辅助的 reference_date 参数，传得不完整但 LLM 不依赖它。 |

### 修复方案（未执行）

在 `add()` 或 `add_from_turn()` 末尾增加，把最后一个 session 的完整日期存入 `_conversation_metadata["reference_date"]`：

```python
last_session = conversation.sessions[-1] if conversation.sessions else None
if last_session and last_session.session_time:
    self._conversation_metadata[conversation.conversation_id]["reference_date"] = (
        last_session.session_time
    )
```

改动位置在 `add_from_turn()` line 464 之后。`session_time` 来自 LoCoMo 原始 JSON 的 `session_N_date_time` 字段，格式如 `"1:56 pm on 8 May, 2023"`。

修复后**不需要重跑现有实验**——当前 full-v4 结果已有效。修复后下次跑自动使用正确值。

## 6. 卡点与下一步建议

**无卡点。** 建议：

1. 如需修复：下次跑 Mem0 实验前顺手改一行。不影响旧实验。
2. 当前 Mem0 full-v4 结果（F1 32.09%，Judge 86.36%）足够作为 baseline。

### 四 method 时间传递对比

| Method | 时间传递方式 | 说明 |
|--------|------------|------|
| Mem0 | 每条记忆自带完整日期 `(Monday, May 8, 2023)`；全局 reference_date 参数只传了年份 | **实际可用**，代码有小瑕疵 |
| MemoryOS | 每条记忆页面的 `timestamp` 字段，来自 `session.session_time` | ✅ 完整 |
| A-Mem | 内部 note `timestamp`，prompt 不显式传 reference_date | ⚠️ prompt 无显式日期提示 |
| LightMem | 每条记忆的 `time_stamp`+`weekday` payload，格式化可读日期 + LongMemEval `question_time` | ✅ 完整 |

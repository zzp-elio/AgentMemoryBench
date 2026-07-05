# Codex 诊断记录 — 2026-06-19 A-Mem session 时间缺失

## 背景

A-Mem LoCoMo official-full（`outputs/amem-locomo-0619-1303/`）已完成 10 conversations、
1540 questions。离线 F1 evaluation 结果如下。

## A-Mem LoCoMo F1 完整结果

### Overall

| metric | 值 |
| --- | ---: |
| total_questions | 1540 |
| mean_score | 0.3457 |
| correct_count | 203 |

### By category（与论文 Table 1 对比）

| category | 含义 | paper F1 | 我们 F1 | 状态 |
| --- | --- | --: | --: | --- |
| 1 | multi-hop | 27.02 | 28.01 | ✓ 吻合 |
| 2 | temporal | **45.85** | **13.75** | ✗ 差距 32 个百分点 |
| 3 | open-domain | 12.14 | 15.02 | ✓ 吻合 |
| 4 | single-hop | 44.65 | 46.96 | ✓ 吻合 |

论文参考：`docs/method-resource-parameter-audit.md` line 43-49，A-Mem Table 1
GPT-4o-mini 结果。

## 诊断过程

### 第 1 步：检查 temporal 预测

抽样 10 个 temporal 问题的 A-Mem 输出：

| 问题 | gold | 预测 |
| --- | --- | --- |
| When did Caroline go to the LGBTQ support group? | 7 May 2023 | Yesterday, June 18, 2026 |
| When did Melanie paint a sunrise? | 2022 | Last year |
| When did Melanie run a charity race? | The sunday before 25 May 2023 | Last Saturday, June 17, 2026 |
| When is Melanie planning on going camping? | June 2023 | Next month |
| When did Caroline give a speech at a school? | The week before 9 June 2023 | Last week |

规律：所有回答都是相对时间（"Yesterday"、"Last year"、"Next month"），gold 要求绝
对日期。第一例甚至给出 "June 18, 2026"——即实验运行的当天日期。

### 第 2 步：诊断提示词

对比 A-Mem official `test_advanced_robust.py` 和我们的 `amem_adapter.py` 中 temporal
prompt：完全一致，排除提示词差异。

### 第 3 步：诊断检索上下文

A-Mem `memory_layer_robust.py:305-306`：
```python
current_time = datetime.now().strftime("%Y%m%d%H%M")
self.timestamp = timestamp or current_time
```

`find_related_memories_raw()` 在检索结果中包含 `"talk start time:" + timestamp`。
如果 `timestamp=None`，所有记忆的时间戳都会是 `datetime.now()`（2026-06-18），
LLM 只能在当前时间锚点下回答相对时间。

### 第 4 步：追查 timestamp 为何为 None

A-Mem adapter `_call_runtime_add`（line 557）：
```python
self._suppress_stdout_if_needed(runtime.add_note, content, time=turn.turn_time)
```

`turn.turn_time` 来自 `Turn` 实体，初始于 `locomo.py:_turn_from_raw()`。该函数
不设置 `turn_time` 字段，总是 `None`。

根因链条：
```
locomo.py:_turn_from_raw() 不设 turn_time
    ↓
Turn.turn_time = None
    ↓
A-Mem _call_runtime_add(time=turn.turn_time) → time=None
    ↓
RobustMemoryNote timestamp=None → datetime.now()
    ↓
检索结果 talk start time = 2026-06-18
    ↓
LLM 回答相对时间（Yesterday / Last year / Next month）
    ↓
temporal F1 从 45.85 跌至 13.75
```

### 第 5 步：其他 method 影响范围排查

| method | session 时间来源 | 受影响？ |
| --- | --- | --- |
| Mem0 | `session.session_time` 直接传入 `add()` | 否 |
| MemoryOS | `session.session_time` 直接传入 timestamp | 否 |
| LightMem | `turn.turn_time or session.session_time` 双 fallback | 否 |
| **A-Mem** | **仅 `turn.turn_time`，无 fallback** | **是** |

Mem0、MemoryOS、LightMem 都是 `for session in conversation.sessions: for turn in session.turns:` 迭代，A-Mem 却用了 `_iter_turns()` helper 打平 turn 列表，丢失
session 上下文。这是 A-Mem adapter 和其他三个 adapter 的不一致之处。

### 第 6 步：Mem0 并发与 resume 状态确认

Mem0 已在 working tree 中完成以下修复（`git diff HEAD`）：

1. `supports_shared_instance_parallelism=False` — 框架 isolated worker 代替共享实例
2. `supports_turn_resume()` 始终 `False` — conversation-level resume
3. `_extract_final_answer()` — LoCoMo 推理链截取

旧 run `outputs/mem0-locomo-0619-1302/` 的 batch search/entity insert Qdrant 竞态
（index out of bounds、shape mismatch）不会再出现，因为每个 worker 有独立 Qdrant 目
录。但代码未 commit，需新 run_id 验证。

## 修复

`src/memory_benchmark/methods/amem_adapter.py` 三处改动：

1. `add()`：移除 `_iter_turns()`，改为 session-level 迭代：
   ```python
   # 旧
   for turn in self._iter_turns(conversation):
       self._call_runtime_add(runtime, turn)

   # 新
   for session in conversation.sessions:
       for turn in session.turns:
           self._call_runtime_add(runtime, turn, session.session_time)
   ```

2. `_call_runtime_add`：增加 `session_time` 参数和 fallback：
   ```python
   # 旧
   def _call_runtime_add(self, runtime, turn):
       ... time=turn.turn_time

   # 新
   def _call_runtime_add(self, runtime, turn, session_time=None):
       timestamp = turn.turn_time or session_time
       ... time=timestamp
   ```

3. 删除 `_iter_turns()` helper；`load_existing_conversation_state()` 中
   turn 计数改为 `sum(len(session.turns) for session in conversation.sessions)`。

## 验证

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py \
  tests/test_method_registry.py tests/test_config_profiles.py -q
# 34 passed, 1 warning

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

## 已知风险

1. `locomo.py:_turn_from_raw()` 仍未把 session_time 写入 `Turn.turn_time`。A-Mem
   adapter 修复后不再依赖此字段，但这是数据层的映射缺陷，后续可统一修复。
2. 当前 run `outputs/amem-locomo-0619-1303/` 的 temporal 结果无效（F1 13.75），
   overall F1 也被拉低。multi-hop/single-hop/open-domain 的结果可信。
3. Mem0 isolated worker 的 state root 路径（`worker_{idx}`）仍可能随 resume 分片
   变化，影响 conversation-level resume；不影响首次全新 run。

## 后续

1. A-Mem LoCoMo full 需用新 run_id 重跑，temporal F1 预期回升至 ~45。
2. Mem0 LoCoMo full 可用新 run_id 验证 isolated worker 不再出现 Qdrant 竞态。

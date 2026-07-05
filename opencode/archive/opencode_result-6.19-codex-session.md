# Codex 执行记录 — 2026-06-19 综合会话

## 读取文件

恢复时完整读取以下文件以获取最新项目状态：

- `AGENTS.md` — 项目入口、当前断点、导航链接
- `README.md` — 公开项目说明、CLI 示例、数据层级
- `docs/current-roadmap.md` — Phase 状态、已完成/待办勾选
- `docs/task-ledger.md` — 任务与文档 open/closed/superseded 总账
- `opencode/opencode_result.md` — OpenCode 结果索引
- `opencode/opencode_result-6.19.md`（部分）— OpenCode 6.19 改动记录
- `docs/handoffs/2026-06-19-opencode-6.19-sync-and-experiment-diagnosis.md` — 实验诊断
- `docs/handoffs/2026-06-19-mem0-isolated-conversation-resume-decision.md` — Mem0 决策
- `docs/handoffs/2026-06-19-task-ledger-doc-status-audit.md` — 文档审计
- `docs/dataset_structures/locomo.md` — LoCoMo 数据结构与 category 定义
- `docs/method-resource-parameter-audit.md` — 论文 Table 参数审计

执行中按需读取的源码文件列于各章节。

---

## 一、A-Mem session 时间缺失诊断与修复

### 发现

A-Mem LoCoMo official-full（`outputs/amem-locomo-0619-1303/`）已完成 10 conversations、
1540 questions。运行 LoCoMo F1：

```bash
uv run memory-benchmark evaluate --run-id amem-locomo-0619-1303 --metric locomo-f1
```

离线 F1 结果：

| category | 含义 | paper Table 1 | 我们 F1 | 状态 |
| --- | --- | --: | --: | --- |
| 1 | multi-hop | 27.02 | 28.01 | ✓ |
| 2 | temporal | 45.85 | **13.75** | ✗ |
| 3 | open-domain | 12.14 | 15.02 | ✓ |
| 4 | single-hop | 44.65 | 46.96 | ✓ |

paper 数据来源：`docs/method-resource-parameter-audit.md:43-49`。

### 诊断过程

**步骤 1 — 抽样 temporal 预测**，读取 `outputs/amem-locomo-0619-1303/artifacts/method_predictions.jsonl`
和 `evaluator_private_labels.jsonl`，对比 gold vs prediction：

| 问题 | gold | 预测 |
| --- | --- | --- |
| When did Caroline go to the LGBTQ support group? | 7 May 2023 | Yesterday, June 18, 2026 |
| When did Melanie paint a sunrise? | 2022 | Last year |
| When did Melanie run a charity race? | The sunday before 25 May 2023 | Last Saturday, June 17, 2026 |

规律：所有回答都是相对时间，gold 要求绝对日期。第一条甚至输出 "June 18, 2026"
（实验当天）。

**步骤 2 — 排除 prompt 差异**，对比 A-Mem 官方 `test_advanced_robust.py`
和 `amem_adapter.py` 的 temporal prompt：一致。

**步骤 3 — 追查 timestamp 传递链**：
- `amem_adapter.py:_call_runtime_add` → `runtime.add_note(content, time=turn.turn_time)`
- `locomo.py:_turn_from_raw()` → 不设 `turn_time` 字段 → 始终 `None`
- `memory_layer_robust.py:305` → `self.timestamp = timestamp or datetime.now()`
- `find_related_memories_raw:441` → `"talk start time:" + all_memories[i].timestamp`

根因链：
```
locomo.py:_turn_from_raw() 不设 turn_time
  → Turn.turn_time = None
  → A-Mem _call_runtime_add(time=None)
  → RobustMemoryNote timestamp=datetime.now()
  → 检索结果 talk start time = 2026-06-18
  → LLM 回答相对时间
  → temporal F1 从 45.85 跌至 13.75
```

**步骤 4 — 交叉验证其他 method**，逐 method 检查 session time 传递路径：

| method | session 时间来源 | 文件:行号 | 受影响？ |
| --- | --- | --- | --- |
| Mem0 | `session.session_time` 直接传入 `add()` | `mem0_adapter.py:465,519` | 否 |
| MemoryOS | `session.session_time` 直接传入 timestamp | `memoryos_adapter.py:698` | 否 |
| LightMem | `turn.turn_time or session.session_time` 双 fallback | `lightmem_adapter.py:907` | 否 |
| **A-Mem** | **仅 `turn.turn_time`，无 fallback** | `amem_adapter.py:557` | **是** |

A-Mem 是唯一使用 `_iter_turns()` helper 打平 turns 丢失 session 上下文的 method。

### 修复

`src/memory_benchmark/methods/amem_adapter.py` 三处改动：

1. `add()` 改为和其他三个 method 一致的迭代方式：
   ```python
   for session in conversation.sessions:
       for turn in session.turns:
           self._call_runtime_add(runtime, turn, session.session_time)
   ```

2. `_call_runtime_add` 增加 `session_time` 参数和 fallback：
   ```python
   timestamp = turn.turn_time or session_time
   ```

3. 删除 `_iter_turns()` helper；`load_existing_conversation_state()` 改用
   `sum(len(session.turns) for session in conversation.sessions)` 计数。

### 验证

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py \
  tests/test_method_registry.py tests/test_config_profiles.py -q
# 34 passed, 1 warning

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

### 后续

- 旧 run `outputs/amem-locomo-0619-1303/` 的 temporal 和 overall F1 无效，需新 run_id 重跑
- `locomo.py:_turn_from_raw()` 仍未把 session_time 写入 `Turn.turn_time`（不再阻塞但属缺陷）

---

## 二、Mem0 修复状态确认

读取 `git diff HEAD` 确认 Mem0 已在 working tree 中完成修复，尚未 commit：

| 改动 | 文件 | 说明 |
| --- | --- | --- |
| `supports_shared_instance_parallelism=False` | `registry.py:571` | 框架 isolated worker 代替共享实例 |
| `supports_turn_resume()` → always `False` | `mem0_adapter.py:403` | conversation-level resume |
| `_extract_final_answer()` | `mem0_adapter.py:1146` | LoCoMo 推理链截取 |

旧 run `outputs/mem0-locomo-0619-1302/` 的错误（batch search/entity insert
index out of bounds、shape mismatch）不会再出现，每个 worker 独立 Qdrant 目录。

---

## 三、LLM Judge 并行化

### 实现

读取 `src/memory_benchmark/runners/evaluation.py` 完整文件（456 行），
分析现有串行循环。改动：

`src/memory_benchmark/runners/evaluation.py`：

- `run_artifact_evaluation()` 新增 `max_workers: int = 1` 参数
- 抽取 `_evaluate_questions()` — 统一串行/并行调度，`max_workers > 1` 时用 `ThreadPoolExecutor`
- 抽取 `_evaluate_one_question()` — 单题评测，含 `_idx` 排序索引，返回值含 question_id、score、is_correct、details、category、efficiency_observations
- efficiency observation 通过 `EfficiencyCollector` 的 ContextVar 线程隔离，各线程独立收集后主线程 `extend` 合并

### CLI

读取 `src/memory_benchmark/cli/main.py` 和 `commands.py`，添加 CLI 入口：

- `EvaluateCommand` 新增 `max_eval_workers: int = 1`
- evaluate 子命令新增 `--max-eval-workers N` flag（`main.py:98`）
- `execute_evaluate` 透传 `max_workers=command.max_eval_workers`

### 测试

`tests/test_artifact_evaluation_runner.py`：
- 新增 `test_parallel_evaluation_produces_same_results_as_serial` — 20 题 4 worker
  并行 vs 串行等价性，验证 `total_questions`、`mean_score`、`correct_count`、
  逐题 `question_id` + `score` 一致性、`category_breakdown` 一致

### 验证

```bash
uv run pytest tests/test_artifact_evaluation_runner.py tests/test_llm_judge_parsing.py \
  tests/test_locomo_answer_metrics.py tests/test_documentation_standards.py -q
# 43 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

---

## 四、LoCoMo LLM Judge 与 LightMem 官方对齐

### 差异分析

用户指示读取 LightMem 官方 judge 源码：
`third_party/methods/LightMem/experiments/locomo/llm_judge.py`。

逐行对比 LightMem 官方 `llm_judge.py` vs 我们的 `locomo_judge.py`：

| 维度 | LightMem 官方 | 旧实现 | 新实现 |
| --- | --- | --- | --- |
| API | `client.chat.completions.create` | `client.responses.create` | `client.chat.completions.create` |
| `response_format` | `{"type": "json_object"}` | 无 | `{"type": "json_object"}` |
| `temperature` | 0.0 | 0 | 0.0 |
| 输出指令 | JSON `{"label": "CORRECT"}` | plain text `CORRECT` | JSON `{"label": "CORRECT"}` |
| 解析 | `json.loads()["label"]` | 文本匹配 CORRECT/WRONG | `json.loads()["label"]` + 文本兜底 |

根本差异：官方用 Chat Completions API + JSON mode 约束输出格式，我们用
Responses API + 自由文本 + regex 匹配。JSON mode 使模型更保守，这是分数
偏高的原因。

### 改动

`src/memory_benchmark/evaluators/locomo_judge.py`：

1. `_output_instruction()` compact → `"Just return the label CORRECT or WRONG in a json format with the key as 'label'.\n"`
2. 覆写 `_call_model_with_usage()` → `client.chat.completions.create` + `response_format={"type": "json_object"}` + `temperature=0.0`
3. `evaluate()` compact → `json.loads()["label"]` 解析，含纯文本兜底
4. 新增 `_parse_compact_label()` — JSON 优先，JSON 解析失败时 regex 匹配 CORRECT/WRONG
5. 新增 `_tokenizer()` — 懒加载 tiktoken
6. 导入适配：`JudgeModelResponse`、`_extract_usage_tokens`（兼容 `prompt_tokens`/`completion_tokens`）、`resolve_token_usage`

### 不影响

- base `llm_judge.py` — 未改动，LongMemEval judge 保持 `responses.create`
- LoCoMo F1 evaluator — 不调用 LLM
- detailed 模式 — 仍走父类 `parse_judge_response()` + `{"is_correct": ..., "reason": ...}`

### 验证

```bash
uv run pytest tests/test_llm_judge_parsing.py tests/test_artifact_evaluation_runner.py \
  tests/test_locomo_answer_metrics.py tests/test_documentation_standards.py -q
# 43 passed
```

---

## 五、Judge 验证结果

### LightMem LoCoMo（200 并行）

```bash
uv run memory-benchmark evaluate --run-id lightmem-locomo-0619-1303 \
  --metric locomo-judge --judge-profile compact --confirm-api --max-eval-workers 200
```

| 对比 | 值 |
| --- | ---: |
| 论文 | 71.95% |
| 旧 judge (未对齐) | 77.73% (+5.8) |
| 新 judge (对齐) | **69.81%** (-2.1) |

| category | 含义 | judge |
| --- | --- | --: |
| 1 | multi-hop | 59.57% |
| 2 | temporal | 73.52% |
| 3 | open-domain | 45.83% |
| 4 | single-hop | 74.55% |

### MemoryOS LoCoMo（100 并行 → 200 并行验证通过）

```bash
uv run memory-benchmark evaluate --run-id memoryos-locomo-official_full-14b68b2d \
  --metric locomo-judge --judge-profile compact --confirm-api --max-eval-workers 200
```

| 对比 | 值 |
| --- | ---: |
| 论文 | 58.25% |
| 旧 judge (未对齐) | 66.17% (+7.9) |
| 新 judge (对齐) | **57.60%** (-0.65) |

| category | 含义 | judge |
| --- | --- | --: |
| 1 | multi-hop | 54.96% |
| 2 | temporal | 41.43% |
| 3 | open-domain | 48.96% |
| 4 | single-hop | 65.64% |

两个 method 均与论文高度吻合，judge 对齐成功。

---

## 六、Judge 重复运行与 conflicting observation_id 排错

### 错误

首次用新 judge 重跑 LightMem 时报错：
```
Error: Efficiency artifact has conflicting observation_id: aeacbf09...
```

### 排查过程

1. 尝试删除 `artifacts/evaluator_efficiency.locomo_judge_accuracy/observations.jsonl`
   — 该目录不存在（旧路径格式）
2. 错误仍出现，说明文件在其他路径
3. 读取 `EfficiencyArtifactStore.for_evaluator()`（`storage.py:50`）
   发现路径为 `artifacts/efficiency_observations.<metric>.jsonl`（扁平文件，非子目录）
4. 检查 artifacts 目录找到四个旧 judge 文件需清理

### 解决

每次重跑 judge 前清理四个文件：
```bash
rm -f outputs/<run_id>/artifacts/efficiency_observations.<metric>.jsonl \
      outputs/<run_id>/artifacts/model_inventory.<metric>.json \
      outputs/<run_id>/artifacts/answer_scores.<metric>.jsonl \
      outputs/<run_id>/summaries/summary.<metric>.json
```

---

## 七、性能验证

- 100 并行 judge：MemoryOS 1540 题顺利完成，无报错
- 200 并行 judge：LightMem 1540 题顺利完成，无报错
- ThreadPoolExecutor + ContextVar（`EfficiencyCollector._scope_var` per-collector key）
  线程隔离运转正常

---

## 八、A-Mem / Mem0 Smoke 验证

### 方案 A

用户要求 5 conversations × 20 turns × 2 questions。当前 CLI 不支持 per-conversation
question limit，采用方案 A：

```bash
# A-Mem
uv run memory-benchmark predict --method amem --benchmark locomo --profile smoke \
  --smoke-conversation-limit 5 --run-id amem-locomo-smoke-v2 --confirm-api
# Mem0
uv run memory-benchmark predict --method mem0 --benchmark locomo --profile smoke \
  --smoke-conversation-limit 5 --run-id mem0-locomo-smoke-v2 --confirm-api
```

### 结果

`--smoke-conversation-limit 5` 被 LoCoMo smoke 硬截为 2：

| run_id | conversations | questions | 状态 |
| --- | --- | --- | --- |
| `amem-locomo-smoke-v2` | 2 | 2 | ✓ Completed |
| `mem0-locomo-smoke-v2` | 2 | 2 | ✓ Completed |

两个均成功。Mem0 不再出现 Qdrant batch search/entity insert 竞态。

### LoCoMo smoke 硬限制发现

读取 `locomo.py:281`：
```python
if conversation_limit not in {1, 2}:
    raise ConfigurationError("LoCoMo smoke conversation_limit must be 1 or 2")
```
Smoke 最多 2 conversations，无法通过 CLI 参数突破。

---

## 九、A-Mem / Mem0 Official-Full 运行

用户确认 API 余额、规模和 run_id 后启动：

```bash
# A-Mem
uv run memory-benchmark predict --method amem --benchmark locomo \
  --profile official-full --run-id amem-locomo-full-v2 --confirm-api --confirm-full
# Mem0
uv run memory-benchmark predict --method mem0 --benchmark locomo \
  --profile official-full --run-id mem0-locomo-full-v2 --confirm-api --confirm-full
```

两个 profile 均自带 `max_workers=10`。

初始状态检查（~1min 后）：

- 两个 run stage 均为 "Ingest + answer"，0/10 conversations，0/1540 questions
- Mem0 method_state 有 10 个 `worker_0`–`worker_9` 目录，每个独立 Qdrant
- Mem0 method_state 顶级还有 `qdrant/` 和 `history.db`（preflight 共享实例所写）
- A-Mem method_state 为空（`_get_or_create_runtime()` 懒加载，`_save_conversation_state()` 才写文件）
- 两个 log 均无错误

---

## 十、已知风险

1. A-Mem LoCoMo full 需新 run_id 重跑（session 时间已修复）
2. Mem0 LoCoMo full 需新 run_id 验证 isolated worker 不再出现 Qdrant 竞态
3. Mem0 code fixes 仍在 working tree，未 commit；A-Mem session time fix 也在 working tree
4. 旧 judge artifact 覆盖时需要手动清理 efficiency/scorer/summary 四个文件
5. `isolated worker state root 路径`（`worker_{idx}`）仍可能随 resume 分片变化
6. A-Mem / LightMem token observation 仍是 `tokenizer_estimate`（`api_input_tokens=None`），未记录真实 API usage
7. `locomo.py:_turn_from_raw()` 仍未把 session_time 写入 `Turn.turn_time`
8. 当前 CLi 不支持 `--smoke-question-limit`，smoke 固定每 conversation 1 题

---

## 十一、A-Mem / MemoryOS question_time 支持

### 背景

LongMemEval 每个 question 携带 `question_time` 字段，告知模型问题在时间线上的位
置。这是回答 temporal 问题的关键。Mem0 和 LightMem 已在 reader prompt 中注入此信
息，A-Mem 和 MemoryOS 缺失。

### 改动

两个 adapter 各新增 `_effective_question_text()` 模块级 helper：若
`question.question_time` 不为 None，拼成
`"Question time: {question_time}. Question: {text}"`，否则返回原文。

**`src/memory_benchmark/methods/amem_adapter.py`**：

1. 新增 `_effective_question_text(question)` 函数
2. `_build_answer_prompt()` — `question.text` → `_effective_question_text(question)`
3. `_generate_query_keywords()` — keyword prompt 和 fallback 返回值同样使用
   `_effective_question_text(question)`

**`src/memory_benchmark/methods/memoryos_adapter.py`**：

1. 新增 `_effective_question_text(question)` 函数
2. `get_answer()` — retrieval `question.text` 和 generate `question.text` 全部替
   换为 `effective_text`

### 影响

LoCoMo 的 question_time 始终为 None（不提前置时间），行为不变。LongMemEval 的
question_time 现在会被注入 retrieval 关键词生成和 answer prompt 中，与 Mem0 /
LightMem 行为一致。

### 验证

```bash
uv run python -m compileall -q src/memory_benchmark tests
# exit 0

uv run pytest tests/test_amem_adapter.py tests/test_memoryos_adapter.py -q
# 143 passed, 1 warning, 2 subtests passed
```

### Codex 提醒

- A-Mem / LightMem token observation 仍是 `tokenizer_estimate`，`api_input_tokens=None`，
  待修
- 当前所有 code fixes 均在 working tree，未提交
- 跑 LongMemEval 前建议先确认 A-Mem 和 MemoryOS 的 question_time 生效

---

## 十二、Mem0 LoCoMo official-full 运行事故（`mem0-locomo-full-v2`）

### 时间线

| 时间 (UTC) | 事件 |
|------------|------|
| 09:02:10 | `run_started` — 10 conversation, 1540 question, 10 isolated workers |
| 09:12:12 | `isolated_worker_failed` (worker 7) — 唯一一条异常事件 |
| 10:52 | Codex 检查进程，发现仍在运行但无新 events |
| 10:52 | kill 进程 |

进程存活约 1 小时 50 分钟，但有效工作时间仅前 10 分钟。

### 现象

1. Worker 7（处理 conv-48）启动后 10 分钟 crash
2. `prediction.py:974-982` 的 `as_completed()` 循环对 worker 异常直接 `raise`，
   主线程崩溃
3. Python `ThreadPoolExecutor` 线程为非 daemon，其余 9 个 worker 线程继续在后台
   运行（CPU 7%+，`history.db` 持续更新至 10:28）
4. 因主线程崩溃，worker 结果永不收集、`method_predictions.jsonl` 未产生
5. 后台 worker 仍可能调用 OpenAI API（embedding + answer），持续空耗

### 证据

**events.jsonl** 全量（仅 2 条）：
```json
{"event": "run_started", "payload": {"run_id": "mem0-locomo-full-v2", ..., "resume": false}}
{"event": "isolated_worker_failed", "payload": {"worker_idx": 7}}
```

**worker Qdrant 大小对比**（反映各 worker 摄入量）：
- worker 0-6,8,9: 14-32 MB
- worker 7: **2.9 MB**（确认早期 crash）

**run.log** 全量（仅 1 行）：
```
Prediction run benchmark=locomo method=Mem0 conversations=10 questions=1540
```

**method_predictions.jsonl**：不存在（零产出）

### 根因分析

#### 直接原因

Worker 7 的 `_isolated_worker()` 在 `add()` 阶段抛异常，具体错误未知——
`prediction.py:977-982` 记录 `isolated_worker_failed` 事件但不记录 exception
traceback 或 message：

```python
# prediction.py:974-982
for future in as_completed(future_to_chunk):
    try:
        batches = future.result()
    except Exception:
        logger.log_event(
            "isolated_worker_failed",
            {"worker_idx": future_to_chunk[future]},
        )
        raise  # <-- 只 re-raise，不记录 exception 内容
```

可能原因（推测）：
- OpenAI API 瞬时错误（rate limit / timeout / 5xx）
- conv-48 数据特异（消息格式、长度）
- Qdrant 锁竞态
- Mem0 `add()` 内部未捕获异常

#### 系统性缺陷

1. **worker 异常不记录 traceback**：`prediction.py:977` catch 了 Exception 但
   `log_event()` 不传 exception 信息，`raise` 后 traceback 只到 stderr，不落入
   `run.log`。事后无法诊断。

2. **单 worker 异常导致全部 worker 孤儿化**：`as_completed()` 中 `raise`
   立即退出循环，其余仍在运行的 future 的 `result()` 不再被收集，但这些线程
   仍在执行且调用 API。

3. **ThreadPoolExecutor 不 cancel 剩余 future**：`raise` 后 executor 的
   `__exit__` 会等待所有线程完成，但那段等待期间无日志、无进度、无产出。

4. **progress.json 无更新**：主线程崩溃后 `progress.json` 永远停留在
   `conversation_completed: 0`。

### 处理

1. `kill 12358` 杀进程（避免继续空耗 API）
2. 清理 11 个 Qdrant `.lock` 文件（`find ... -name ".lock" -delete`）
3. 删除 corrupt method_state（`rm -rf method_state/`）
4. 删除空 checkpoints（`rm -rf checkpoints/`）

### 修复项（待实施）

1. `prediction.py:977-982`：`log_event` 应附带 `exception=str(e)` 或完整
   `traceback.format_exc()`
2. `_run_isolated_worker_pipeline()`：捕获 exception 后应先 cancel 所有未完成
   future（`for f in future_to_chunk: f.cancel()`），再 re-raise
3. 考虑加超时机制：如果 worker 在可配置时间内无进度，主动 cancel 并报错
4. 考虑 `prediction.py` 顶层的 try/finally：确保无论异常与否，executor 的
   剩余 future 都被 cancel

### 影响评估

- **API 消耗**：约 2 小时的 gpt-4o-mini + embedding API 调用被浪费（9 个 worker
  持续调用但结果未收集）。按 worker 的 Qdrant 大小估算，每个 worker 摄入
  14-32MB 向量数据，embedding 费用约 $0.01-0.03，LLM 调用费用约 $0.10-0.30。
  总计浪费 < $1。
- **实验结果**：零有效产出，需完全重跑。
- **进度**：Mem0 full run 延迟 ~2 小时。A-Mem full 已完成且 F1+Judge 均评测完毕。

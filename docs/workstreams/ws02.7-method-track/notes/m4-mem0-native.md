# M4 Mem0 native config-track 取证与停工断点

> 取证日期：2026-07-14。状态：**停工，等待架构师裁决**。本卡没有调用真实
> API，也没有修改生产代码、测试或 `third_party/`。

## 1. Phase A 调用点核证

| benchmark | 官方 answer builder 与实际调用 | 官方 judge builder 与实际调用 | 结论 |
|---|---|---|---|
| LoCoMo | `get_answer_generation_prompt` 定义于 `third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/prompts.py:143-195`，实际由 `run.py:465-466` 构造并作为 user message 调用 | 默认无 evidence 路径使用 `get_judge_prompt`，模板由 `prompts.py:218-270` 构造，调用分支在 `run.py:470-478`；`--with-evidence` 默认关闭，旗标在 `run.py:708` | 实际默认调用点可唯一确定为无 evidence 版本 |
| LongMemEval | `get_answer_generation_prompt` 定义于 `third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/prompts.py:210-258`，实际调用在 `run.py:587-593` | 单一 `JUDGE_PROMPT` 位于 `prompts.py:265-342`，`get_judge_prompt` 位于 `:345-359`，实际调用在 `run.py:606-614` | 实际调用点唯一 |
| BEAM | `get_beam_answer_generation_prompt` 定义于 `third_party/methods/mem0-main/memory-benchmarks/benchmarks/beam/prompts.py:104-158`，实际调用在 `run.py:738-739` | 实际逐 rubric 调用 `get_beam_nugget_judge_prompt`（`prompts.py:170-233`），调用点为 `run.py:555-569` | 实际调用点唯一；但框架 adapter 未供应该 native answer prompt，见下节 |

模型不 native 的拍板与上述模板取证不冲突：三个 harness 的 CLI 默认 judge
model 均为 `gpt-5`（LoCoMo `run.py:683`、LongMemEval `run.py:947`、BEAM
`run.py:902`），本卡应继续使用框架统一 `gpt-4o-mini`，而不是复制榜单模型。

## 2. 阻塞事实：BEAM provider prompt 不是官方 native prompt

**硬结论：按本卡当前允许文件注册 `mem0 × beam × native` 会把框架通用 fallback
错误标记成 Mem0 官方 native answer prompt，不能施工。**

证据链：

1. native config-track 只通过非空 bundle 关闭 benchmark 的 unified builder：
   `src/memory_benchmark/cli/run_prediction.py:343-347,709-713`。runner 在 builder
   为空时直接使用 provider 的 `RetrievalResult.prompt_messages`：
   `src/memory_benchmark/runners/prediction.py:2772-2790`。
2. Mem0 provider 确实在 retrieve 返回 `_reader_messages` 生成的 messages：
   `src/memory_benchmark/methods/mem0_adapter.py:1005-1023`。
3. `_reader_messages` 只为 `locomo` 和 `longmemeval` 调各自官方 builder；其余走
   自研 `generic` system/user prompt：`mem0_adapter.py:1763-1790`。对应官方模块
   加载也仅出现在 LoCoMo `:1816-1840` 与 LongMemEval `:1842-1864`。
4. BEAM `Question` 只有 `category`，没有 `question_time` 或 source metadata：
   `src/memory_benchmark/benchmark_adapters/beam.py:416-423`。`_reader_prompt_kind`
   只识别 LongMemEval、LoCoMo，最后回退 `generic`：
   `mem0_adapter.py:1792-1814`。BEAM 的十类 category 不满足这两组判断，因此
   必然进入 generic 路径。
5. generic prompt（`mem0_adapter.py:1778-1790`）与官方 BEAM prompt
   （`third_party/methods/mem0-main/memory-benchmarks/benchmarks/beam/prompts.py:29-48,104-158`）
   在指令、记忆排序/编号和 abstention 文案上均不是同一模板。

所以，新建静态 `MEM0_NATIVE_ANSWER_PROFILES["beam"]` 也无法改变运行时文本：
现有 `ConfigTrackBundle` 只存 `answer_prompt_source` 与 LLM settings，没有可调用的
answer builder 字段（`src/memory_benchmark/methods/config_track.py:20-28`）；当前
native 路径明确依赖 provider 已经供应正确 messages。

## 3. 待裁决方案

### 方案 A（建议）：定向解冻 Mem0 adapter

允许本卡额外修改 `src/memory_benchmark/methods/mem0_adapter.py`：让 adapter 能从
run/registration 上下文确定 benchmark 为 BEAM，并调用 vendored
`get_beam_answer_generation_prompt`。随后仍沿用现有
`answer_prompt_source="provider_prompt_messages"`，不改共享 bundle 结构。

需要架构师同时裁定 benchmark identity 的传递方式。不能仅靠 BEAM category
猜测，因为 `_reader_prompt_kind` 当前是数据形态启发式而非注册身份。

### 方案 B：扩展 ConfigTrackBundle 的 native answer builder

给 bundle 增加可调用的 answer profile/builder，并让 prediction runner 在 native
轨执行它。这会修改本卡禁止触碰的 runner，且改变共享 config-track 契约，影响面
明显大于方案 A。

## 4. 施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m4mem0`
- branch：`actor/m4-mem0-native`
- 已完成：`uv sync`；三格 answer/judge 实际调用点核证；BEAM native answer
  路径断点取证。
- 未完成：native profile 文件、bundle 注册、parity 测试。
- 未运行 pytest/compileall：停工发生在任何代码改动之前；运行完成门会制造“本卡
  已施工”的错误信号。
- 偏离：无自行变更裁定；按“ConfigTrackBundle 字段与 Mem0 场景不匹配”停工条件
  上报。

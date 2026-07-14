# M4 Mem0 native config-track 取证与停工断点

> 取证日期：2026-07-14。状态：**架构师裁决后已完成**。全程没有调用真实
> API，也没有修改 `third_party/`。

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

## 4. 初次停工施工报告

- worktree：`/Users/wz/Desktop/mb-actor-m4mem0`
- branch：`actor/m4-mem0-native`
- 初次断点提交：`082aa00 docs(ws02.7): record Mem0 native BEAM prompt blocker`。
- 偏离：无自行变更裁定；初次按“ConfigTrackBundle 字段与 Mem0 场景不匹配”
  停工，随后严格按 §5 架构师裁决恢复。

## 5. 架构师裁决后的实现

### 5.1 显式 benchmark identity 与 BEAM reader

- registry 把 `MethodBuildContext.benchmark_name` 显式传给 Mem0：
  `src/memory_benchmark/methods/registry.py:165-190`；失败清理重建路径也保留该
  identity（`:582-597`）。
- adapter 构造参数保存规范化 benchmark identity；reader 路由优先识别
  `locomo/longmemeval/beam`，为空才执行原启发式：
  `src/memory_benchmark/methods/mem0_adapter.py:284-327,1803-1827`。
- BEAM 路由调用 vendored `get_beam_answer_generation_prompt`，不复制其运行时
  排版逻辑：`mem0_adapter.py:1771-1801,1879-1898`。reader 版本升为
  `mem0-memory-benchmarks-reader-v4`（`mem0_adapter.py:70`）。
- unified 防泄漏：BEAM unified builder 仍只使用 `formatted_memory`，测试
  `test_mem0_beam_unified_prompt_ignores_native_provider_messages` 证明 provider
  native messages 改变时 unified answer prompt 字节不变。

### 5.2 三格 profile 与注册面

`src/memory_benchmark/methods/mem0_native_prompts.py` 静态保存三格 answer/judge
模板；测试运行时加载 vendored `prompts.py` 全文比对。answer harness 的实际
调用都省略采样参数，因此采用 `LLMClient.generate` 默认
`temperature=0,max_tokens=4096`（
`memory-benchmarks/benchmarks/common/llm_client.py:136-156`），`top_p` 未传。

`src/memory_benchmark/methods/config_track.py` 注册：

- native：`mem0 × {locomo,longmemeval,beam}`；
- single-track collapse：`mem0 × {membench,halumem}` 继续 fail-fast；
- answer/judge model 均继续使用框架 `gpt-4o-mini`；
- `embedding_ref=mem0.repo_default.openai.text-embedding-3-small`，依据 Mem0
  embedder 默认 provider 与模型：`mem0/configs/embeddings/base.py:6-11`、
  `mem0/embeddings/openai.py:11-19`；
- `hyperparam_ref=mem0.memory-benchmarks.repo_default`。

### 5.3 native judge 与框架现役 judge 差异

| benchmark | Mem0 native | 框架现役 | 差异 |
|---|---|---|---|
| LoCoMo | Mem0 自研统一 JSON rubric（`memory-benchmarks/benchmarks/locomo/prompts.py:202-292`） | LightMem 参考 prompt（`src/memory_benchmark/evaluators/locomo_judge.py:27-63`） | 非逐字相同；Mem0 版新增 partial credit、14 天日期容忍等规则 |
| LongMemEval | Mem0 单一统一 yes/no prompt（`memory-benchmarks/benchmarks/longmemeval/prompts.py:262-359`） | benchmark 官方按 question type/abstention 分派（`src/memory_benchmark/evaluators/longmemeval_judge.py:58-87`） | 非逐字相同；native 是单模板，unified 是官方多模板 |
| BEAM | Mem0 重写的 rubric nugget prompt（`memory-benchmarks/benchmarks/beam/prompts.py:161-233`） | BEAM 官方模板 parity（`src/memory_benchmark/evaluators/beam_rubric_judge.py:20-96`） | 非逐字相同；两者均为 0/0.5/1 rubric，但文案与结构不同 |

### 5.4 完成门实际输出

```text
$ uv run pytest -q tests/test_config_track.py tests/test_mem0_native_prompts.py tests/test_mem0_adapter.py
53 passed in 67.69s (0:01:07)

$ uv run python -m compileall -q src/memory_benchmark tests
(exit 0, no output)
```

真实 native 三格 smoke 未执行，按任务卡留给用户确认 API 预算后运行。

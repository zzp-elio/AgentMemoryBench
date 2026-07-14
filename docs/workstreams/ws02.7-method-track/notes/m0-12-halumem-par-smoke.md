# M0-12 HaluMem 并行 smoke 施工断点

> 日期：2026-07-14  
> actor：Codex  
> 状态：停工，等待架构师裁决

## 1. 前置与开工环境

- M0-11 修复提交 `77ec269` 已进入 `main`，当前开工基点为验收提交
  `f97642c`。
- 独立 worktree：`/Users/wz/Desktop/mb-actor-m12`；分支：
  `actor/m0-12-halumem-par`。
- 已执行 `uv sync`，输出为 `Resolved 160 packages`、`Checked 135 packages`。

## 2. 停工结论

**当前 operation-level runner 实际不支持 `workers > 1`；本卡第 4 节第二项停工条件已触发。**

不能只把 HaluMem smoke 数据集从 1 user 扩成 2 users：运行在进入
operation-level runner 前或 runner 入口就会拒绝 `max_workers > 1`；即使绕过
校验，runner 当前也按 conversation 串行循环。仅扩数据形状不能形成有效并行，
会重复 beam par2 判例中的“第二 worker 空转”问题。

## 3. 证据链

### 3.1 workers 尚未到达 benchmark prepare 请求

- CLI 先从 method 配置和 `--workers` 解析 `max_workers`
  （`src/memory_benchmark/cli/run_prediction.py:411-419`）。
- 随后构造 `BenchmarkLoadRequest` 时只传 variant、scope、turn/conversation/session
  裁剪和 MemBench sources，没有 workers
  （`src/memory_benchmark/cli/run_prediction.py:452-476`）。
- `BenchmarkLoadRequest` 的字段定义同样没有 workers
  （`src/memory_benchmark/benchmark_adapters/contracts.py:176-186`）。
- workers 直到稍后才进入 `PredictionRunPolicy.max_workers`
  （`src/memory_benchmark/cli/run_prediction.py:496-506`）。
- HaluMem smoke prepare 当前固定执行 `adapter.load(limit=1)`
  （`src/memory_benchmark/benchmark_adapters/halumem.py:249-263`）。

因此，在不改变请求契约或引入其他公共传参机制的前提下，
`prepare_halumem_run()` 无法知道本次 workers 值。`contracts.py` 不在本卡允许修改
清单内；自行扩展该公共契约会越权。

### 3.2 prediction 调度明确拒绝 operation-level 多 worker

- registered prediction 在 operation-level 分支中，当多 worker 需要隔离 method
  实例时直接抛出
  `ConfigurationError("operation-level prediction currently requires max_workers=1")`
  （`src/memory_benchmark/cli/run_prediction.py:633-651`）。
- 即使 method 声明共享实例并行、从而未触发上述外层判断，operation-level runner
  入口仍无条件要求 `policy.max_workers == 1`
  （`src/memory_benchmark/runners/operation_level.py:62-100`）。
- runner 的主循环是 `for conversation in selected_conversations`，逐个调用
  `_run_operation_conversation()`，没有 worker pool 或 conversation 分片
  （`src/memory_benchmark/runners/operation_level.py:128-181`）。
- runner 自身 docstring 也明确写明“当前只支持单 worker”
  （`src/memory_benchmark/runners/operation_level.py:78-85`）。

这不是仅调整 adapter smoke 形状能够解决的问题。真正支持并行需要修改
operation-level 调度、provider 实例隔离、artifact 合并与 checkpoint 协调；本卡明确
禁止修改 `runners/`，且这部分语义应由架构师先行设计。

### 3.3 M0-11 未改变并行能力

M0-11 提交 `77ec269` 修复的是 operation-level update probe 在非 question scope
记录 retrieval efficiency 时的容忍行为；其生产改动集中于 method adapter 的
`record_retrieval_result_if_question_scope()` 调用和 collector，不包含
operation-level 并行调度。该提交因此解决了本卡前置 probe-scope bug，但没有解除
上述单 worker 限制。

## 4. 未施工项

因停工发生在实现前，本批未修改 HaluMem adapter、CLI 或测试，也未运行目标测试与
compileall。以下事项等待架构师裁决后再做：

1. HaluMem 的 B11 并行 smoke 是否裁为 N/A；或另立 runner 设计卡实现真实的
   operation-level conversation 并行。
2. 若决定实现并行，workers 应如何进入 benchmark prepare 请求，同时保持公共契约
   与其他 benchmark 行为不变。
3. 多 worker 下 provider 应使用隔离实例还是共享实例，以及 operation-level 的
   session reports、update probes、predictions、效率记录和 checkpoint 如何确定性
   合并。
4. 在真实并行能力落地后，再实现本卡要求的固定 2-user smoke 形状及两形状 resume
   指纹隔离。

## 5. 施工报告

- commit：见本 note 所在分支提交。
- 测试：未运行；停工条件在代码审计阶段触发，未进入完成门。
- 实际改动：仅本 note。
- 偏离：无自行偏离；严格按任务卡第 4 节停工并上报。

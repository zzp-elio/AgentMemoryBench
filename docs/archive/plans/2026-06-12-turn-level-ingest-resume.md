# Turn-Level Ingest Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为支持该能力的 memory system 增加逐 turn ingestion checkpoint，使确定成功的 turn 可安全续跑，不确定 turn 拒绝自动重放。

**Architecture:** 保留 `BaseMemorySystem` 公共契约，新增可选 `BaseResumableMemorySystem` 子接口。通用 runner 通过独立的 checkpoint store 管理每个 conversation 的原子 JSON 状态；Mem0 实现从指定扁平 turn index 继续写入。

**Tech Stack:** Python 3.11+、ABC、dataclass、SHA-256 路径、原子 JSON、pytest、uv。

---

## 文件结构

- Modify: `src/memory_benchmark/core/interfaces.py`
  - 定义可选 `BaseResumableMemorySystem`。
- Create: `src/memory_benchmark/runners/ingest_resume.py`
  - 定义 checkpoint 状态对象、hash 路径和原子读写校验。
- Modify: `src/memory_benchmark/methods/mem0_adapter.py`
  - 实现从扁平 turn index 继续写入与 callback 顺序。
- Modify: `src/memory_benchmark/runners/prediction.py`
  - resumable method 使用逐 turn checkpoint；普通 method 保持原逻辑。
- Modify: `src/memory_benchmark/storage/experiment_paths.py`
  - 增加 `ingest_turn_checkpoints_dir`。
- Test: `tests/test_mem0_adapter.py`
- Test: `tests/test_prediction_runner.py`
- Test: `tests/test_experiment_storage.py`

### Task 1: 可选 resumable 接口与 Mem0 增量写入

- [x] 在 `tests/test_mem0_adapter.py` 写失败测试，验证 `add_from_turn()` 从 index 2 开始时
  只调用第三个 turn，并验证 callback 顺序为 `started -> backend -> completed`。
- [x] 运行：

```bash
uv run pytest tests/test_mem0_adapter.py -q
```

预期：因接口和方法不存在而失败。

- [x] 在 `core/interfaces.py` 增加 `BaseResumableMemorySystem`，在 Mem0 中实现
  `add_from_turn()`；`add()` 委托该方法且保持多 conversation 支持。
- [x] 重跑 Mem0 adapter tests，预期全部通过。

### Task 2: Checkpoint store 与路径安全

- [x] 在独立的 `tests/test_ingest_resume.py` 写失败测试：
  - `../../conv` 只能映射到 checkpoints 目录内的 64 位 hash 文件。
  - `ready/in_flight/completed` round-trip。
  - schema、conversation id、turn 范围不匹配时报错。
- [x] 运行失败测试，确认 `ingest_resume.py` 尚不存在。
- [x] 实现 `TurnIngestCheckpoint` 和 `TurnIngestCheckpointStore`，只使用
  `atomic_write_json()`，并在 `ExperimentPaths` 增加目录属性。
- [x] 重跑 checkpoint 与 Mem0 adapter focused tests。

### Task 3: Runner 故障注入与安全 resume

- [x] 在 `tests/test_prediction_runner.py` 写失败测试：
  - 第二个 turn backend 异常后状态为 `in_flight`、`next_turn_index=1`。
  - 手工构造 `ready(next_turn_index=1)` 后 resume 只写剩余 turn。
  - `in_flight` resume 在调用 method 前抛错。
  - `completed` checkpoint 可补齐 conversation 状态。
  - 普通 `BaseMemorySystem` 不创建逐 turn 文件。
- [x] 运行测试确认 RED。
- [x] 修改 `prediction.py`：
  - `_ingest_one()` 检测 `BaseResumableMemorySystem`。
  - started/completed callbacks 写当前 conversation 独立 checkpoint。
  - `in_flight` 预检在创建 worker 前完成。
  - worker 成功后标记 checkpoint `completed`，协调线程继续提交共享 conversation 状态。
- [x] 重跑 prediction/conversation runner tests。

### Task 4: Resume 装配与验证

- [x] 检查 CLI resume 装配：部分 `ready` checkpoint 由
  `Mem0.add_from_turn(start_turn_index > 0)` 附着已有 namespace；
  `in_flight` 在 worker/API 创建前被 runner 预检拒绝，无需新增 CLI 参数。
- [x] 保持 completed conversation 的现有 namespace 装配，不修改公开 CLI 参数。
- [x] 运行：

```bash
uv run pytest \
  tests/test_mem0_adapter.py \
  tests/test_prediction_cli.py \
  tests/test_prediction_runner.py \
  tests/test_experiment_storage.py \
  tests/test_documentation_standards.py -q
```

- [x] 运行默认全量回归、API collect 和 compileall。
- [x] 更新 `AGENTS.md` 与当前 Mem0 handoff，记录状态机、限制和验证结果。

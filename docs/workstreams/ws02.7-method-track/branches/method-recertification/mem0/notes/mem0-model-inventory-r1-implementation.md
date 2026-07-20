# Mem0 registered model inventory R1

日期：2026-07-20
范围：registered v3 prediction 的效率模型清单；不改 Mem0 算法、输入、检索、answer 或 metric。

## 1. 真实 smoke 发现

Mem0 五格 8 个真实 run 的 `efficiency_observations.prediction.jsonl` 中，answer 阶段实际
调用统一由 framework 记录为 `model_id="gpt-4o-mini"`。没有任何一条 observation 引用
`mem0-answer-llm`；但每个 `model_inventory.prediction.json` 都多声明了该模型。

根因与已关闭的 LightMem 同型：registered v3 主路径只调用 method 的 `ingest()` 与
`retrieve()`，最终回答由 `FrameworkAnswerReader` 执行。Mem0 自带 `get_answer()` 的 reader
只服务直接调用 legacy 兼容接口，不会从 registered 主路径到达。

## 2. 修复

- `src/memory_benchmark/methods/registry.py`：从
  `_mem0_efficiency_model_inventory()` 删除 `mem0-answer-llm`，保留真实可达的
  `mem0-memory-llm` 与 `mem0-embedding`；framework answer model 仍由 CLI 单独追加。
- `tests/test_method_registry.py`：增加强断言，锁定 Mem0 registered inventory 的精确模型 id
  集合，并确认 instrumentation identity getter 未被连带删除。
- `Mem0.get_answer()` 与其 `mem0-answer-llm` observation 代码不删；直接调用 legacy 接口时其
  行为仍由 `tests/test_mem0_adapter.py` 覆盖。

## 3. 重跑边界

该修复只删除 artifact 中一个从未实际调用的预声明条目。五格真实 observation 已直接证明
它不可达；message bytes、memory state、retrieved items、answer、score 与调用次数均不变，
因此不重烧 8 个付费 smoke。当前 run 的旧 inventory 作为当时真实产物保留，并在 frozen note
披露；新 run 将写出收紧后的清单。

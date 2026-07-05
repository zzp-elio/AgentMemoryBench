# 架构说明

长期架构以多 task family 为扩展方向，当前只实现 `conversation_qa`。完整设计以
`docs/archive/specs/2026-06-12-project-goals-architecture-design.md` 为准。

数据结构的细节说明见 `docs/survey/datasets/`，评测流程参考见
`docs/survey/workflows/`。当前运行时数据入口是 `data/`，官方 benchmark 仓库与源码
参考位于 `third_party/benchmarks/`。

整体架构：

```text
CLI / Public Python API
  ↓
Command Service + Config Resolver
  ↓
Registry + Compatibility Resolver
  ↓
BenchmarkAdapter
  ↓
Validated Dataset + Method
  ↓
Prediction Runner
  ↓
Immutable Artifacts
  ↓
Evaluation Runner
```

## Adapter 层

adapter 读取本地原始数据，把 benchmark-specific schema 转成统一 `Dataset`。

职责：

- 定位 `data/` 下的运行时 dataset 文件。
- 保留 conversation、session、turn 的原始顺序。
- 把公开问题写入 `Question`。
- 把标准答案和 evidence 写入 `GoldAnswerInfo`。
- 抛出项目领域异常，而不是静默吞掉结构错误。

## Core 层

core 层只定义公共实体、接口和校验。它不认识具体 benchmark 文件路径，也不调用 method。

核心约束：

- `Question` 是 method public input。
- `GoldAnswerInfo` 是 evaluator private input。
- 公开 metadata 不能包含答案、evidence 或 judge label。

## Registry 与兼容性

benchmark、method、evaluator 分别使用独立 registry。registry 保存静态声明和 factory，
不保存 secret 或运行实例。

长期兼容性依据：

```text
task family
+ benchmark required capabilities
+ method provided capabilities
+ evaluator required observations
```

不维护 method × benchmark 的笛卡尔积白名单。

当前状态：

- MemoryOS 已进入 method registry。
- Mem0 和 MemoryOS 的 LoCoMo 新 run 共享同一个 registered conversation-QA prediction service 和 generic runner。
- 目前只有 LoCoMo 开放 prediction；LongMemEval adapter 可读，但统一 prediction 仍未启用。
- 两个方法当前只声明已公开实现的能力：conversation add 和 answer generation；retrieval 仍是可选能力，未提供 public retrieve 前不主张该能力。
- registered run 会先做只读的 immutable manifest/source/config preflight，再创建目录并 attach method factory / resume。
- MemoryOS 新 run 只写 canonical artifacts；旧 full/smoke runner 与 root alias 仅用于历史复现，不能和新 resume 混用。
- MemoryOS 目前使用 `max_workers=1`，因为共享 wrapper 的线程安全尚未单独验证。

## Runner 层

prediction 与 evaluation 分离：

```text
predict:
  validate
  -> add public Conversation
  -> get_answer public Question
  -> predictions + runtime observations

evaluate:
  existing artifacts
  -> quality / efficiency evaluators
```

`run` 只是二者的便利组合。runner 会重建公开对象，防止私有数据泄漏。

## Method 层

method 通过 wrapper 适配到 `BaseMemorySystem`。第一方 wrapper 位于
`src/memory_benchmark/methods/`，第三方源码位于 `third_party/methods/<name>-main/`，
但 runner 只依赖 wrapper。

method 分为：

- `end_to_end`：直接生成答案。
- `memory_module`：实现写入和检索，由框架 fixed-reader wrapper 组合成完整回答系统。

用户自定义 method 当前通过 Python API 传入；CLI 只运行官方集成。

## Evaluator 层

evaluator 只读取标准 artifacts，不重新调用 method。当前包含：

- LoCoMo token F1。
- LoCoMo / LongMemEval LLM judge accuracy。

当前不计算 retrieval recall。未来效率评测只规划 Retrieval Latency、Memory Context
Tokens 和 Memory Update Cost；prediction 保存逐操作 observation，evaluate 离线聚合。

## 实验不可变性

一个 `run_id` 的 benchmark、数据指纹、method、reader 和关键配置不可改变。`resume`
只能继续完全兼容的运行；新增 evaluator 可以写独立 metric artifact，但不能修改原 prediction。

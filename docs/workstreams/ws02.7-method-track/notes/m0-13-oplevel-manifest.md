# M0-13：operation-level manifest provenance 盖章

> 取证与施工日期：2026-07-14。范围仅为 operation-level manifest 组装、resume
> 比较与离线测试；未调用真实 API。

## 问题链路

- registered CLI 在 operation-level 分支把 `child.method_manifest` 直接传给
  `run_operation_level_predictions`（`src/memory_benchmark/cli/run_prediction.py:669-679`）。
- generic 分支另行调用 `run_predictions`，并向其传注册级 `protocol_version` 与
  `system_factory`（`src/memory_benchmark/cli/run_prediction.py:690-720`）；generic
  runner 由共用 `_method_manifest_with_protocol` 完成协议与 provenance 盖章
  （`src/memory_benchmark/runners/prediction.py:1218-1258`）。
- M0-13 前 operation-level 使用自己的补字段逻辑，只补 `protocol_version` 与
  `prompt_track`，因此没有消费注册级 provenance 声明。Mem0 的注册声明实际为
  `provenance_granularity="turn"`
  （`src/memory_benchmark/methods/registry.py:785-800`）。

## 落地方案

1. CLI 在 operation-level 调用点把 `MethodRegistration.protocol_version` 和
   `MethodRegistration.provenance_granularity` 显式传入 runner
   （`src/memory_benchmark/cli/run_prediction.py:669-689`）。这里只读取静态注册信息，
   没有为盖章额外实例化 provider。
2. operation-level runner 删除自有补章函数，直接复用 generic 路径的
   `_method_manifest_with_protocol`，并固定 `prompt_track="unified"`
   （`src/memory_benchmark/runners/operation_level.py:44-51,64-116`）。注册声明作为
   显式参数优先；未传声明的直接调用仍可按真实 `MemoryProvider` 实例回退，优先级与
   共用函数契约一致（`src/memory_benchmark/runners/prediction.py:1226-1257`）。
3. operation-level resume 不再裸比较两个 manifest，改用 generic 路径同一个
   `_manifests_match_for_resume`（`src/memory_benchmark/runners/operation_level.py:770-786`）。
   该比较器在任一侧缺键时双侧移除 `provenance_granularity`，所以旧 HaluMem run
   可以与新代码生成的 manifest 兼容比较
   （`src/memory_benchmark/runners/prediction.py:1166-1186`）。

## 离线回归证据

- operation-level fake provider 完整跑一遍后，同时断言 manifest 的
  `protocol_version="v3"`、`provenance_granularity="turn"` 与 unified prompt track
  （`tests/test_operation_level_runner.py:306-324,413-417`）。显式注册声明为 `turn`，
  fake provider 自身未覆写 provenance，因而该断言也钉死注册声明优先路径。
- resume 测试先生成新 manifest，再模拟旧 operation-level run 删除 provenance
  与当时同样缺失的 profile 键，随后以新代码 resume；断言已完成 conversation
  不被重跑且比较通过
  （`tests/test_operation_level_runner.py:482-526`）。
- generic 路径未改；同批定向执行其 runner 测试以确认 M0-10 行为不回归。

## 边界

- 未运行真实 HaluMem prediction；下一次真实 run 的 manifest 抽查由架构师执行。
- 未发现分散的第二个 operation-level manifest 组装点，无停工事项。

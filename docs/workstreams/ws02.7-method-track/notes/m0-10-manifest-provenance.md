# M0-10：并行 manifest 的 provenance 盖章

> 施工日期：2026-07-14。纯离线修复；未实例化真实 provider，未调用真实 API。

## 现场事实

任务卡记录 workers>1 协调路径的 `system=None`；当前基点已演进为传入
`_UnusedRootSystem` sentinel，但该对象同样不是 `MemoryProvider`，因此旧逻辑仍无法
从实例读取 provenance。`run_predictions` 原先只把 system 交给盖章函数；并行 worker
才通过 factory 构造真实实例（`src/memory_benchmark/runners/prediction.py:380-393`，
worker 构造不在本卡修改范围）。

旧 manifest 比较逻辑已经把 `provenance_granularity` 纳入缺键兼容集合：任一侧缺键
就双侧移除后比较（`src/memory_benchmark/runners/prediction.py:1166-1186`）。本卡不改
该逻辑，只补测试钉死旧无字段 run 与新有字段代码可 resume。

## 方案

`MethodRegistration` 新增可选 `provenance_granularity`，默认 `None` 保持未声明 method
的原行为（`src/memory_benchmark/methods/registry.py:87-143`）。LightMem 注册行静态
声明 `turn`（`src/memory_benchmark/methods/registry.py:775-804`）；该能力在当前五个
benchmark 间不分叉，未触发停工条件。

为遵守本卡允许文件边界且不在协调进程构造 provider，registry 按现有
`system_factory` 身份提供静态声明解析
（`src/memory_benchmark/methods/registry.py:889-897`）。`run_predictions` 已经从注册
调用方接收同一个 factory；现在先解析声明，再显式传给
`_method_manifest_with_protocol`（`src/memory_benchmark/runners/prediction.py:380-393`）。

盖章函数新增显式 `provenance_granularity` 入参。注册声明优先；未声明且存在真实
`MemoryProvider` 时继续读取实例属性，保持串行与自定义路径兼容。两种来源共用原有
`none/session/turn` 白名单，非法值仍 fail-fast
（`src/memory_benchmark/runners/prediction.py:1218-1258`）。

## 离线测试

- 并行等价路径：`system=None` + LightMem 注册声明盖出 `turn`
  （`tests/test_prediction_runner.py:3482-3495`）。
- 串行实例回退、非法注册值 fail-fast
  （`tests/test_prediction_runner.py:3498-3519`）。
- 旧 manifest 缺字段与新 manifest 有 `turn` 的 resume 比较通过
  （`tests/test_prediction_runner.py:3522-3538`）。
- LightMem registration 与 factory 静态解析均为 `turn`
  （`tests/test_amem_lightmem_registry.py:54-70`）。

真实 workers>1 predict 后的 manifest 抽查留给架构师，未在本卡调用 API。

# Actor 卡 M0-13：operation-level 路径 manifest 不盖 provenance 章（小卡）

> 派发日 2026-07-14。允许修改：`src/memory_benchmark/cli/run_prediction.py`
> 与/或 `src/memory_benchmark/runners/operation_level.py`（仅 manifest 组装
> 处）、tests、新建 `notes/m0-13-oplevel-manifest.md`（ws02.7）。禁真实 API。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m13 -b actor/m0-13-oplevel-manifest
cd /Users/wz/Desktop/mb-actor-m13 && uv sync
```
禁 push;只跑目标测试 + compileall（playbook #18）。

## 1. Bug 实锤（架构师 2026-07-14 开箱取证）

`mem0-halumem-unified-s1-medium` 的 manifest `method` 段**缺
`provenance_granularity`**,而同日四个 generic-runner 的 run 全部盖了
`"turn"`。根因:M0-10 的注册级静态声明修复只接进了 `run_predictions`
（generic 路径,prediction.py 调 `_method_manifest_with_protocol`）;
**operation-level 路径的 manifest 组装没有走同一个盖章函数**（入口
`cli/run_prediction.py` 中 `run_operation_level_predictions(...,
method_manifest=child.method_manifest,...)` :669-683 一带,取证 manifest
从何构造、在哪缺章）。今日影响=0（halumem 无 recall 类指标）,但
manifest 口径必须全路径一致——将来任何按 manifest 读 provenance 的消费
方都不许有路径分叉。

## 2. 施工内容
1. operation-level 路径复用与 generic 路径**同一个**盖章函数
   `_method_manifest_with_protocol`（注册声明优先,禁在协调层实例化真实
   provider——M0-10 的裁决原样适用）;
2. 测试:operation-level 假 provider 跑一遍,manifest 断言含正确
   provenance_granularity 与 protocol_version;generic 路径不回归;
3. resume 兼容:旧 halumem run（无该键）与新代码 manifest 比对可 resume
   （`_manifests_match_for_resume` 已双侧 pop,补一条 operation-level 断言）。

## 3. 完成门
目标测试 + compileall 全绿（报数字）;note 记锚。真实复证=下一次任意
halumem predict 后架构师抽 manifest（不在本卡）。

## 4. 停工条件
- operation-level 的 manifest 组装点分散多处,单一盖章接不进 → 停工给
  方案选项。

## 施工报告（actor 填写）
（待填）

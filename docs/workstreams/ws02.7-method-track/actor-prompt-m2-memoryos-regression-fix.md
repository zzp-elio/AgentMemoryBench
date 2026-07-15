# Actor 返工卡：M2 MemoryOS registry 测试替身契约同步

> 派发日：2026-07-15。单批上限 5h；预计远小于 1h。
> 这是 M2 合入后主树全量回归暴露的定向返工，不扩大生产实现范围。
> 由用户选择 Sonnet 5、GLM-5.2、MiniMax、Codex 或其他 actor 后转发；
> 架构师不得默认自行启动 Codex subagent。

## 0. 上工与 Git 隔离

按顺序只读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部当前断点；
3. 本卡全文；
4. `docs/reference/actor-handbook.md`。

从主树当前 `main` 自建独立 worktree；若路径或分支已存在，立即停工报告，
不得删除或复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-m2fix \
  -b actor/m2-memoryos-regression-fix main
cd /Users/wz/Desktop/mb-actor-m2fix
```

只允许修改：

`tests/test_memoryos_registered_prediction.py`

不得修改生产代码、其他测试、README/roadmap、third_party 或 outputs；不得调用真实
API；不得另开 reviewer/subagent；不得 push。

## 1. 已裁定的根因与修复边界

M2 把 `benchmark_name` 加入真实 `MemoryOS.__init__`，registry factory 必须显式
传入它，供 LoCoMo speaker map/native prompt 出口恢复使用。这个生产契约是已接受的
M2 R1/R4 实现，不得为了迁就测试替身而删掉、弱化或用 `try/except TypeError`
绕开。

合入后主树全量回归实际尾行：

```text
2 failed, 1174 passed, 3 deselected, 2 warnings, 4 subtests passed in 134.21s
```

两处失败均为：

```text
TypeError: _FakeMemoryOS.__init__() got an unexpected keyword argument 'benchmark_name'
```

失败用例：

- `test_memoryos_registered_prediction_uses_generic_runner_with_smoke_crop_resume_and_workload_manifest`
- `test_new_memoryos_run_writes_only_canonical_prediction_artifacts`

## 2. 唯一施工目标

让本文件的 `_FakeMemoryOS` 明确镜像真实 factory 所需的 `benchmark_name` 入参，
保存该值，并在至少一个现有 registry 装配测试中断言 LoCoMo 实际注入
`"locomo"`。不要使用无边界 `**kwargs`，因为那会让未来 factory 契约漂移不再被测试
发现。

若复核后发现失败并非测试替身漏参，或修复必须触碰允许清单外文件，立即停工写报告，
不得自行改判。

## 3. 唯一自检与停点

只跑：

```bash
uv run pytest -q tests/test_memoryos_registered_prediction.py
```

通过后执行：

```bash
git diff --check
git status --short
git add tests/test_memoryos_registered_prediction.py
git commit -m "test(memoryos): mirror registry benchmark identity"
```

到此停止，不跑全量 pytest/compileall，不更新状态文档，不 push。按 actor-handbook
§4 报 commit、测试尾行原文、实际改动文件、偏差/停工点。

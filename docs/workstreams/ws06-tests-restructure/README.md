---
id: ws06
parent: ws01
status: open
created: 2026-07-05
---
# ws06 tests 目录重组

## 目标

把扁平的 51 个测试文件（约 2.5 万行）按 src 分层镜像分组，拆分超大文件，
排查把临时状态固化成断言的过时测试。完成判据：重组前后
`uv run pytest -q` 通过数一致（当前基线 709 passed）；CLAUDE.md 命令示例同步。

## 当前断点

- 2026-07-05：未开工（ws01 spec §6 的 M4，独立排期）。开工前由架构师写 spec，
  方向：`tests/{core,adapters,methods,runners,evaluators,observability,storage,
  cli,analysis}/` 镜像 src 分层 + api marker 目录。

## 任务清单

- [ ] 写重组 spec + plan（含逐文件归属映射、pytest 配置与 marker 调整）。
- [ ] 拆分超大文件：test_prediction_runner.py（3019 行）、
  test_prediction_cli.py（2439 行）、test_memoryos_locomo_full_runner.py（2058 行）等。
- [ ] 排查占位式/过时断言。已知条目：
  - `test_documentation_standards.py::test_archived_log_readme_keeps_naming_convention`
    现在守护的是归档文件的命名规范，已无意义（docs/logs 机制已被 workstream
    notes/ 取代），重组时删除或改为守护新机制。
- [ ] 评估 tests 按 unit/integration/api/contract marker 分组的补充需求
  （旧 roadmap Phase L 遗留意向）。

## 决策记录

- 2026-07-05 架构师：MemBench 空占位测试案例确认了"临时状态固化成断言"
  是需要系统排查的反模式（该案例已单独修复，见 ws01 plan T0 裁定）。

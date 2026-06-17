# Phase C/D Src Layout 与 Pytest 交接

日期: 2026-06-11  
状态: Phase C/D 已完成并经综合 review APPROVED

## 当前目标

在有限额度下完成必要工程化：

1. Phase C: 第一方包迁到 `src/memory_benchmark/`，第三方仓库迁到
   `third_party/methods/`。已完成。
2. Phase D: 引入 pytest 安全默认入口和 markers；保留 unittest 测试实现与扁平目录。
   实现和验证已完成，等待同一 reviewer 复审 findings。

设计文档：

- `docs/superpowers/specs/2026-06-11-src-layout-pytest-design.md`

## 2026-06-11 Phase D 完成并验证

- `uv add --dev pytest` 已执行，`pyproject.toml` 与 `uv.lock` 已更新。
- `pyproject.toml` 已加入 `testpaths = ["tests"]`、默认 `addopts = "-ra -m 'not api'"`，
  并注册 `unit`、`integration`、`memoryos`、`api`、`slow`、`expensive` markers。
- 测试模块已按最小分类加 marker，`OpenAIAPISmokeTests` 仅保留 `api`，默认 pytest 不会执行真实 API smoke。
- 验证结果：
  - `uv run pytest --collect-only -q`: 163/164 tests collected，1 deselected。
  - `uv run pytest -q`: 163 passed，1 deselected，4 subtests passed。
  - `uv run pytest -m memoryos -q`: 55 passed，109 deselected。
  - `uv run pytest -m api --collect-only -q`: 1/164 tests collected，163 deselected。
  - `uv run python -m unittest tests/test_core_conversation_entities.py tests/test_conversation_dataset_validation.py tests/test_llm_judge_parsing.py tests/test_locomo_answer_metrics.py tests/test_documentation_standards.py tests/test_mem0_source_compatibility.py -v`: 40 tests ran，OK。
  - `uv run python -m unittest tests/test_conversation_runner.py tests/test_experiment_storage.py tests/test_observability_run_context.py tests/test_observability_progress.py tests/test_run_logger.py tests/test_locomo_conversation_adapter.py tests/test_longmemeval_conversation_adapter.py tests/test_memoryos_adapter.py tests/test_memoryos_locomo_smoke.py tests/test_memoryos_locomo_full_runner.py -v`: 118 tests ran，OK。
  - `uv run python -m compileall -q src/memory_benchmark tests`: exit 0。

当前断点：无。后续如需继续工作，从新的需求或 review 开始。

## 已完成调查

三个只读 subagent 已完成，未修改文件：

- Euclid，`gpt-5.4-mini high`：第一方 src-layout 与 setuptools/uv 影响。
- Plato，`gpt-5.4 medium`：第三方 method 路径与迁移风险。
- Nietzsche，`gpt-5.4-mini high`：pytest 收集、marker 与默认 API 安全。

关键事实：

- 当前 `pyproject.toml` 已切到 setuptools `src` layout：
  `package-dir = {"" = "src"}`，`where = ["src"]`。
- `uv.lock` 的本项目来源是 editable `"."`，不编码源码目录，通常无需因移动路径重建依赖。
- 第三方 method 源码当前位于 `third_party/methods/MemoryOS-main` 与
  `third_party/methods/mem0-main`。
- `_resolve_project_root()` 已兼容根目录 `memory_benchmark/` 与 `src/memory_benchmark/`
  两种布局。
- `tests/test_documentation_standards.py` 当前按 `src/memory_benchmark/` 与 `tests/`
  扫描第一方 Python 文件，并排除第三方目录。
- `uv run --with pytest python -m pytest --collect-only -q tests` 已验证可收集现有
  161 项 unittest 测试。
- 从仓库根直接 pytest 会误收集第三方 MemoryOS 的 `test_simple.py` 并触发
  `sys.exit(1)`；必须设置 `testpaths = ["tests"]`。
- 当前唯一真实 API 测试是 `tests/test_API.py` 中的 OpenAI smoke。

## 已确认方案

采用分段垂直迁移：

1. C1: `PathSettings` 和第三方 method resolver。
2. C2: 移动 MemoryOS/mem0 到 `third_party/methods/`。
3. C3: 移动第一方 package 到 `src/memory_benchmark/` 并更新 setuptools/root detection。
4. D: pytest dev dependency、配置和 markers；不搬 tests、不重写 unittest。

默认 `uv run pytest` 必须排除 `api`。真实 API 只通过 `uv run pytest -m api` 显式执行。

## 下一步严格顺序

> 以下步骤保留的是实施前计划；当前状态已完成，见上方 “Phase D 完成并验证”。

1. 完成 C3 收尾验证：`uv sync`、导入来源检查、focused/full unittest、compileall。
2. 同步更新当前活跃文档中的 `src/` 与 `third_party/` 路径表述。
3. Phase C 做一次综合 review，确认无旧 flat-layout 假设残留。
4. 再进入 D：
   - 添加 pytest dev dependency/config。
   - 添加模块或类级 markers。
   - 验证默认不执行 API，显式 API 可执行。
5. Phase D 完成后做最终 full verification。

## 额度策略

- 用户报告本次 5h 额度约剩 34%，且上下文即将压缩。
- 不保证当前额度内完成所有 C+D；优先保证 Phase C 完整、可验证。
- Phase D 采用最小范围，若额度不足可在 C 完成后独立续接。
- 不重复上述调查，不再次派 explorer 做相同扫描。
- 实现优先使用 `gpt-5.4-mini high`；关键路径综合 review 使用 `gpt-5.4 medium`，
  最终阶段审查才考虑更高规格。
- OpenCode 继续禁用。

## C3 前基线

- focused: 79/79。
- full unittest: 161/161，含真实 `gpt-4o-mini` API smoke。
- MemoryOS fake runner: 37/37。
- compileall: exit 0。
- Phase A/B 已完成并最终 APPROVED。

## Phase C 完成后状态

- `pyproject.toml` 已切到 setuptools `src` layout，`uv sync` 通过。
- `memory_benchmark.__file__` 当前解析到
  `src/memory_benchmark/__init__.py`。
- 第一方源码当前位于 `src/memory_benchmark/`；根目录 `memory_benchmark/` 与
  `memory_benchmark.egg-info/` 已移除。
- focused verification: 67/67。
- full unittest discover: 164/164。
- `uv run python -m compileall -q src/memory_benchmark tests`: exit 0。

## 2026-06-11 额度 8% 主动暂停

用户报告 5h 额度仅剩约 8%，且上下文即将压缩。本轮在 C3 subagent 返回后立即停止继续
实施，没有启动 Phase D，也没有重复运行耗时测试。

### 精确断点

- C1 第三方路径契约：实现完成。
- C2 第三方源码迁移：实现完成。当前路径为：
  - `third_party/methods/MemoryOS-main`
  - `third_party/methods/mem0-main`
- C3 第一方 src-layout：实现完成。当前包路径为
  `src/memory_benchmark/`，根目录旧包和生成的 `memory_benchmark.egg-info/` 已移除。
- C3 subagent 报告验证：
  - `uv sync` 通过。
  - focused tests 67/67。
  - full unittest discover 164/164，包含真实 `gpt-4o-mini` API smoke。
  - `uv run python -m compileall -q src/memory_benchmark tests` exit 0。
  - `memory_benchmark.__file__` 指向 `src/memory_benchmark/__init__.py`。
- **Phase C 综合 review 尚未执行，所以 Phase C 不能标记为正式验收完成。**
- **Phase D 尚未开始**：不要假定 pytest dev dependency、配置或 markers 已添加。
- 当前没有需要等待的 subagent 或 shell session。

### 下一窗口严格顺序

1. 先读 `AGENTS.md` 和本 handoff，不重复 Phase C explorer 调查。
2. 快速核对目录及 `memory_benchmark.__file__`。
3. 只做一次 Phase C 综合 review，重点检查旧 flat-layout 假设、第三方路径边界、
   packaging/import 与活跃文档路径。
4. 若有发现，修复并运行相关 focused tests；随后正式验收 Phase C。
5. 按既定最小方案执行 Phase D：保留扁平 `tests/` 和 unittest 测试实现，只添加 pytest
   依赖、`testpaths = ["tests"]`、markers，以及默认排除真实 API。
6. Phase D 完成后再做最终 full verification 和一次阶段综合 review。

### 避免无用功

- 不重新派发已经完成的 src-layout、第三方路径或 pytest 收集调查。
- 不在 Phase C review 前启动 Phase D。
- 不移动 tests 子目录，不批量改写 unittest，不顺带重构业务代码。
- OpenCode 保持禁用。

## 2026-06-11 Phase C 正式验收

额度恢复后完成了一次 Phase C 综合 review。reviewer 最初发现两个问题：

1. `resolve_third_party_method_path()` 允许 `method_directory` 使用 `..` 解析到兄弟
   method 仓库。
2. `AGENTS.md` 指向的 MemoryOS 实验 handoff 仍保留迁移前的第三方源码路径。

修复和验证：

- 使用 TDD 增加真实兄弟 method fixture，确认旧实现 RED 后，将 `method_directory`
  强约束为单一、非绝对目录名。
- 将 `docs/handoffs/2026-06-03-memoryos-locomo.md` 中第三方 MemoryOS 路径更新为
  `third_party/methods/MemoryOS-main`。
- `OpenAIConfigTests`、MemoryOS adapter 和文档规范 focused tests 共 25/25 通过，
  主线程没有运行 API smoke。
- 同一 reviewer 复审确认两个 finding 均关闭，结论为 **Phase C APPROVED**。

补充说明：首次综合 review 时 reviewer 误运行了一次真实 `gpt-4o-mini` API smoke，
调用成功。后续 Phase D 默认 pytest 必须通过 marker 排除 API，避免再次误触发。

当前精确断点：Phase C 已正式完成；开始执行 Phase D 最小 pytest 迁移。

## 2026-06-11 Phase D 正式验收

Phase D 按最小范围完成：

- 使用 `uv add --dev pytest` 添加 pytest dev dependency。
- `testpaths = ["tests"]` 阻止 pytest 收集第三方仓库测试。
- 默认 marker 表达式排除 `api`；显式 `-m api` 可以覆盖默认表达式。
- 17 个测试模块按 `unit`、`integration`、`memoryos`、`api` 分类。
- `slow` 和 `expensive` 只注册，未误标当前测试。
- 保留扁平 `tests/` 和原有 unittest 实现，没有进行无收益重写。

Phase D 综合 review 最初发现：

1. README 常规命令仍推荐 `unittest discover`，会绕过 pytest marker 并调用真实 API。
2. AGENTS、handoff、spec 和 plan 在综合 review 前提前声明 Phase D 完成。
3. 复审安全命令时，又发现活跃 plan 的 C1/C2/C3 命令仍有整文件
   `tests/test_API.py` 或 `unittest discover` 残留。

修复后，所有普通验证命令均使用默认安全 pytest 或显式
`tests.test_API.OpenAIConfigTests`。整文件 `tests/test_API.py` 只保留在 README 明确标注
会发起真实调用的 API smoke 章节。同一 reviewer 最终结论为 **Phase D APPROVED**。

最终安全验证基线：

- `uv run pytest --collect-only -q`: 163/164 tests collected，1 deselected。
- `uv run pytest -q`: 163 passed，1 deselected，4 subtests passed。
- `uv run pytest -m memoryos -q`: 55 passed，109 deselected。
- `uv run pytest -m api --collect-only -q`: 1/164 tests collected，163 deselected。
- 两组显式无 API unittest 共 158 tests，均通过。
- `uv run python -m compileall -q src/memory_benchmark tests`: exit 0。

当前精确断点：Phase C/D 均已正式完成。后续不需要重复本轮调查或迁移。

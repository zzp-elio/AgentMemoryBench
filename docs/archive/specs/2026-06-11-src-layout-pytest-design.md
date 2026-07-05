# Phase C/D Src Layout And Pytest Design

状态: 设计已实现；Phase C/D 均经综合 review APPROVED  
日期: 2026-06-11

## 目标

以最少迁移成本完成两项工程化改造：

1. Phase C 将第一方包迁入 `src/memory_benchmark/`，并把第三方 method 源码移出
   Python package，统一放到 `third_party/methods/`。
2. Phase D 引入 pytest 作为默认测试入口，支持安全的 marker 筛选，但不重写现有
   unittest 测试，也不搬动测试文件。

本轮不改变 conversation-QA 协议、benchmark 逻辑、MemoryOS 算法、指标或实验产物格式。

## 目标目录

```text
src/
  memory_benchmark/
    benchmark_adapters/
    cli/
    config/
    core/
    evaluators/
    methods/
    metrics/
    observability/
    runners/
    storage/
    utils/
third_party/
  methods/
    MemoryOS-main/
    mem0-main/
tests/
```

`src/memory_benchmark/methods/` 只保留本项目 wrapper；第三方仓库不参与第一方 package
发现，也不受中文 docstring 规范扫描。

## Phase C 设计

### C1 路径契约

在 `PathSettings` 增加：

- `third_party_root`
- `third_party_methods_root`

第三方 method 路径由配置层统一解析。调用方传 method 目录名和内部相对路径，不再拼接
`memory_benchmark/methods/...`。路径不存在时抛 `ConfigurationError`，错误信息只包含
安全路径，不读取或输出 secret。

项目根探测同时识别迁移前的 `memory_benchmark/` 和迁移后的
`src/memory_benchmark/`，保证移动过程可分步验证；Phase C 完成后仍保留双布局识别，
便于工具从不同工作目录运行。

### C2 第三方源码迁移

当前布局：

```text
third_party/methods/MemoryOS-main
third_party/methods/mem0-main
```

MemoryOS wrapper 继续调用官方 `eval/` 源码，只改变路径来源；临时 `sys.path` 和
`sys.modules` 隔离逻辑保持不变。mem0 当前只保留源码兼容性检查，不恢复已暂停的
benchmark 接入。

### C3 第一方 src-layout

目标/当前布局：

```text
src/memory_benchmark/
```

setuptools 配置改为：

```toml
[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
include = ["memory_benchmark*"]
```

所有项目命令继续使用 `uv run`，由 uv 的 editable project 安装解析 `src/`。不承诺未安装
项目时直接执行系统 Python 能导入 package。

`memory_benchmark.egg-info/` 是旧布局生成物，不作为源码事实来源；迁移后删除旧生成物，
由 uv/setuptools 按需重新生成。

## Phase D 设计

pytest 作为 dev dependency 加入项目。现有 unittest 测试保持原样，由 pytest 直接收集。
测试目录本轮保持扁平，避免只有路径变化、没有行为收益的大规模修改。

pytest 配置必须包含：

- `testpaths = ["tests"]`，阻止收集 benchmark 和第三方仓库测试。
- markers: `unit`、`integration`、`memoryos`、`api`、`slow`、`expensive`。
- 默认排除 `api`，避免普通测试意外消费真实 API。

当前只有真实 `gpt-4o-mini` smoke 标记为 `api`。MemoryOS wrapper、smoke 和 fake full
runner 标记为 `memoryos`；按真实边界给测试模块标记 `unit` 或 `integration`。
`slow` 和 `expensive` 先注册，不给不符合语义的测试滥贴标签。

## 实施结果

- `uv add --dev pytest` 已完成，`pyproject.toml` 与 `uv.lock` 已同步。
- 默认 `uv run pytest` 只收集 `tests/`，并通过 `-m 'not api'` 排除真实 API smoke。
- `tests/test_API.py` 中 `OpenAIConfigTests` 标记为 `unit`，`OpenAIAPISmokeTests` 仅标记为 `api`。
- `memoryos`、`integration` 和 `unit` 模块级分类已落地，`slow` 与 `expensive` 仅注册未使用。
- 验证结果：
  - `uv run pytest --collect-only -q`: 163/164 tests collected，1 deselected。
  - `uv run pytest -q`: 163 passed，1 deselected，4 subtests passed。
  - `uv run pytest -m memoryos -q`: 55 passed，109 deselected。
  - `uv run pytest -m api --collect-only -q`: 1/164 tests collected，163 deselected。
  - `uv run python -m unittest ...` focused suite: 158 tests ran，OK。
  - `uv run python -m compileall -q src/memory_benchmark tests`: exit 0。

推荐命令：

```bash
uv run pytest
uv run pytest -m unit
uv run pytest -m "integration and not api"
uv run pytest -m memoryos
uv run pytest -m api
```

## 实施顺序

严格串行执行 C1 -> C2 -> C3 -> D，因为后一步依赖前一步路径状态。每个阶段完成 focused
验证；Phase C 与 Phase D 各做一次综合 review，最终运行完整 pytest、显式 API smoke、
unittest 兼容基线和 compileall。

可并行的工作仅限只读审计或互不冲突的文档核对，不并行移动共享目录。

## 验收标准

- `uv run python -c "import memory_benchmark; print(memory_benchmark.__file__)"` 指向
  `src/memory_benchmark/`。
- MemoryOS wrapper 从 `third_party/methods/MemoryOS-main/eval` 加载官方源码。
- 第一方 package 发现结果不包含 `MemoryOS-main` 或 `mem0-main`。
- 默认 `uv run pytest` 不发起真实 API 请求。
- `uv run pytest -m api` 可单独运行真实 API smoke。
- `uv run pytest -q` 默认不调用真实 API，并通过 `-m 'not api'` 排除 smoke。
- `uv run pytest -m api --collect-only -q` 只收集真实 API smoke，不实际调用 API。
- 选定的无 API `unittest` focused suite 能通过，且不需要 `discover`。
- `uv run python -m compileall -q src/memory_benchmark tests` 通过。

## 明确不做

- 不把 tests 移到 `unit/integration/e2e` 子目录。
- 不把 unittest 测试重写成 pytest 函数。
- 不新增 CI、coverage、lint 或发布流水线。
- 不修改第三方仓库内部文件。
- 不恢复 PrefEval 或 mem0 benchmark 实验。

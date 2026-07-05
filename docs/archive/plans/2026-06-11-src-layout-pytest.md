# Phase C/D Src Layout And Pytest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将第一方 Python 包迁入 `src/`、把第三方 method 仓库移出 package，并以最小改动引入安全的 pytest 默认入口。

**Architecture:** 严格串行执行 C1 路径契约、C2 第三方源码迁移、C3 第一方 src-layout、D pytest 配置。业务接口和实验逻辑不变；现有 unittest 测试保留，由 pytest 直接收集。

**Tech Stack:** Python 3.11+、setuptools、uv、unittest、pytest。

**Status:** Phase C/D 已完成并经综合 review APPROVED。

---

## 执行约束

- 当前目录不是 git repo，不执行 commit 步骤。
- 不修改第三方仓库内部文件，只移动整个目录。
- 不搬 tests 目录，不把 unittest 重写为 pytest 函数。
- 每个 Task focused verification；Phase C、Phase D 各一次综合 review。
- 若某一步失败，先恢复该切片可运行状态，不叠加下一步改动。

### Task 1: C1 第三方路径契约

**Files:**
- Modify: `memory_benchmark/config/settings.py`
- Modify: `memory_benchmark/config/__init__.py`
- Modify: `tests/test_API.py`

- [ ] **Step 1: 写 PathSettings RED 测试**

在 `test_load_path_settings_reads_project_directories_without_openai_key` 中断言：

```python
self.assertEqual(paths.third_party_root, project_root.resolve() / "third_party")
self.assertEqual(
    paths.third_party_methods_root,
    project_root.resolve() / "third_party" / "methods",
)
```

新增 resolver 测试，临时创建
`third_party/methods/FakeMethod/source.py`，验证：

```python
resolved = paths.resolve_third_party_method_path("FakeMethod", "source.py")
self.assertEqual(resolved, expected.resolve())
```

并验证 method 目录缺失时抛 `ConfigurationError`。

- [ ] **Step 2: 运行 RED**

```bash
uv run python -m unittest tests.test_API.OpenAIConfigTests -v
```

预期：新字段或 resolver 不存在。

- [ ] **Step 3: 实现最小路径契约**

`PathSettings` 墈加：

```python
third_party_root: Path
third_party_methods_root: Path
```

增加实例方法：

```python
def resolve_third_party_method_path(
    self,
    method_directory: str,
    *relative_parts: str,
) -> Path:
    method_root = (self.third_party_methods_root / method_directory).resolve()
    if not method_root.is_dir():
        raise ConfigurationError(
            f"third-party method directory does not exist: {method_root}"
        )
    resolved = method_root.joinpath(*relative_parts).resolve()
    if not resolved.is_relative_to(method_root):
        raise ConfigurationError("third-party method path escapes method directory")
    return resolved
```

`load_path_settings()` 填充两个新目录。保持 `.env` 行为不变。

- [ ] **Step 4: 运行 GREEN**

```bash
uv run python -m unittest \
  tests.test_API.OpenAIConfigTests \
  tests/test_memoryos_adapter.py -v
```

### Task 2: C2 第三方 method 源码迁移

**Files:**
- Modify: `memory_benchmark/methods/memoryos_adapter.py`
- Modify: `tests/test_memoryos_adapter.py`
- Modify: `tests/test_mem0_source_compatibility.py`
- Modify: `tests/test_documentation_standards.py`
- Move: `memory_benchmark/methods/MemoryOS-main/` -> `third_party/methods/MemoryOS-main/`
- Move: `memory_benchmark/methods/mem0-main/` -> `third_party/methods/mem0-main/`

- [ ] **Step 1: 先让 wrapper/tests 使用 resolver**

删除旧 `MEMORYOS_SOURCE_DIR`/`MEMORYOS_EVAL_DIR` 字符串拼接。将 `_load_eval_modules`
改为接收 `PathSettings`，并使用：

```python
eval_dir = path_settings.resolve_third_party_method_path("MemoryOS-main", "eval")
```

mem0 compatibility 测试通过 `load_path_settings(PROJECT_ROOT)` 解析
`mem0-main/mem0/__init__.py`。documentation scanner 的第三方排除范围改为
`third_party/`，同时继续扫描第一方 package。

- [ ] **Step 2: 物理移动目录**

使用非破坏性 `mv`，先创建 `third_party/methods/`。确认目标不存在后移动两个完整目录。
不要复制后再保留双份源码。

- [ ] **Step 3: focused verification**

```bash
uv run python -m unittest \
  tests.test_API.OpenAIConfigTests \
  tests/test_memoryos_adapter.py \
  tests/test_mem0_source_compatibility.py \
  tests/test_memoryos_locomo_smoke.py \
  tests/test_documentation_standards.py -v
```

再验证旧目录不存在、新目录存在，且第一方源码中无旧路径硬编码：

```bash
test ! -e memory_benchmark/methods/MemoryOS-main
test ! -e memory_benchmark/methods/mem0-main
rg -n "memory_benchmark/methods/(MemoryOS-main|mem0-main)" memory_benchmark tests
```

### Task 3: C3 第一方 src-layout

**Files:**
- Modify: `pyproject.toml`
- Modify before/after move: `memory_benchmark/config/settings.py`
- Modify: `tests/test_documentation_standards.py`
- Move: `memory_benchmark/` -> `src/memory_benchmark/`
- Delete generated: `memory_benchmark.egg-info/`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `AGENTS.md`
- Modify: current spec/plan/handoff

- [ ] **Step 1: 添加 src-layout 打包配置**

```toml
[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
include = ["memory_benchmark*"]
exclude = ["benchmarks*", "docs*", "models*", "tests*"]
```

- [ ] **Step 2: 更新根目录探测和文档扫描**

`_resolve_project_root()` 接受：

```python
(candidate / "src" / "memory_benchmark").is_dir()
```

并保留 flat-layout 识别用于迁移兼容。documentation scanner 明确扫描
`src/memory_benchmark` 与 `tests`。

- [ ] **Step 3: 物理移动第一方 package**

创建 `src/` 后移动整个剩余 `memory_benchmark/`。删除旧 `memory_benchmark.egg-info/`。
不修改 import 语句，包名仍为 `memory_benchmark`。

- [ ] **Step 4: 验证安装和导入来源**

```bash
uv sync
uv run python -c \
  "import pathlib, memory_benchmark; print(pathlib.Path(memory_benchmark.__file__).resolve())"
```

输出必须位于 `src/memory_benchmark/`。

- [x] **Step 5: Phase C focused/full verification**

```bash
uv run python -m unittest \
  tests.test_API.OpenAIConfigTests \
  tests/test_documentation_standards.py \
  tests/test_memoryos_adapter.py \
  tests/test_mem0_source_compatibility.py \
  tests/test_memoryos_locomo_smoke.py \
  tests/test_memoryos_locomo_full_runner.py -v
uv run pytest -q
uv run python -m compileall -q src/memory_benchmark tests
```

当前重跑使用默认安全 pytest 代替 `unittest discover`，避免误调用真实 API。Phase C
迁移当时的 full unittest 历史结果记录在 handoff 中。完成后做一次 Phase C 综合 review。

### Task 4: D 最小 pytest 迁移

**Files:**
- Modify: `pyproject.toml`
- Modify: selected `tests/test_*.py` marker declarations
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: current handoff/spec/plan

- [x] **Step 1: 添加 pytest dev dependency**

使用 uv：

```bash
uv add --dev pytest
```

- [x] **Step 2: 添加安全 pytest 配置**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -m 'not api'"
markers = [
  "unit: 纯逻辑与实体测试",
  "integration: adapter、storage、runner 等集成测试",
  "memoryos: MemoryOS wrapper 或 runner 测试",
  "api: 会调用真实外部 API 的测试",
  "slow: 长耗时测试",
  "expensive: 会产生明显外部成本的测试",
]
```

- [x] **Step 3: 添加最小 markers**

使用 `pytestmark = pytest.mark.<name>` 或类级 marker：

- `api`: 仅 `OpenAIAPISmokeTests`。
- `memoryos`: MemoryOS adapter/smoke/full runner。
- `integration`: benchmark adapters、storage、observability、logger 和 runner。
- `unit`: core、validators、metrics、judge parsing、docs、mem0 compatibility。

不为当前测试误加 `slow`/`expensive`。

- [x] **Step 4: 验证默认安全与显式 API**

```bash
uv run pytest --collect-only -q
uv run pytest -q
uv run pytest -m memoryos -q
uv run pytest -m api --collect-only -q
# unittest 兼容性使用 AGENTS.md 中显式列出的两组无 API 模块。
uv run python -m compileall -q src/memory_benchmark tests
```

默认 pytest 必须显示 API smoke 被 deselect；`-m api --collect-only` 只验证显式选择，
不在阶段验收中发起真实 API 请求。

- [x] **Step 5: 文档与最终验收**

README 更新 src-layout、third-party、pytest 命令与 marker 说明。更新 `AGENTS.md` 和 handoff
的真实状态及验证数字。Phase D review findings 已关闭，同一 reviewer 最终 APPROVED。

验证结果：

- `uv run pytest --collect-only -q`: 163/164 tests collected，1 deselected。
- `uv run pytest -q`: 163 passed，1 deselected，4 subtests passed。
- `uv run pytest -m memoryos -q`: 55 passed，109 deselected。
- `uv run pytest -m api --collect-only -q`: 1/164 tests collected，163 deselected。
- `uv run python -m unittest` focused suite: 158 tests ran，OK。
- `uv run python -m compileall -q src/memory_benchmark tests`: exit 0。

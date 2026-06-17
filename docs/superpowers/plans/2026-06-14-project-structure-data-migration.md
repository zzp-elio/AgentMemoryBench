# Project Structure and Data Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `data/` 运行时唯一数据入口，把官方 benchmark 仓库迁入 `third_party/benchmarks/`，并把两组研究参考文档归入 `docs/`。

**Architecture:** `PathSettings` 统一暴露 runtime data、third-party benchmarks 和 third-party methods 三个根路径。adapter/registry/fingerprint 只引用 canonical `data/`；官方仓库保持完整，只用于事实核验、源码和论文参考。迁移分为路径契约、物理移动、引用修复、数据清单验证和完整回归五个可独立验收层次。

**Tech Stack:** Python 3.12、dataclasses、pathlib、pytest、uv、SHA-256、rsync dry-run。

---

### Task 1: 固化迁移前基线

**Files:**
- Update: `docs/handoffs/2026-06-14-project-structure-data-migration.md`
- Verify only: `outputs/memoryos-locomo-full-20260603/`

- [x] **Step 1: 记录完整离线测试基线**

Run:

```bash
uv run pytest -q
uv run pytest -m api --collect-only -q
uv run python -m compileall -q src/memory_benchmark tests
```

Expected:

- 默认测试全部通过且不执行 API。
- API 测试只收集。
- compileall exit 0。

- [x] **Step 2: 记录受保护实验聚合哈希**

Run:

```bash
find outputs/memoryos-locomo-full-20260603 -type f -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 \
  | shasum -a 256
```

Expected:

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

- [x] **Step 3: 创建 handoff 并写入基线**

handoff 必须记录日期、测试数量、哈希、当前物理目录和“不调用 API”约束。

### Task 2: 为新的路径契约编写失败测试

**Files:**
- Modify: `tests/test_config_profiles.py`
- Modify: `tests/test_locomo_conversation_adapter.py`
- Modify: `tests/test_longmemeval_conversation_adapter.py`
- Modify: `tests/test_benchmark_registry.py`

- [x] **Step 1: 增加 PathSettings 根目录测试**

新增断言：

```python
paths = load_path_settings(PROJECT_ROOT)

assert paths.data_root == PROJECT_ROOT / "data"
assert paths.third_party_benchmarks_root == PROJECT_ROOT / "third_party" / "benchmarks"
assert paths.third_party_methods_root == PROJECT_ROOT / "third_party" / "methods"
```

- [x] **Step 2: 更新 LoCoMo canonical path 预期**

```python
assert dataset.metadata["source_path"] == "data/locomo/locomo10.json"
```

- [x] **Step 3: 更新 LongMemEval canonical path 预期**

```python
assert (
    dataset.metadata["source_path"]
    == "data/longmemeval/longmemeval_s_cleaned.json"
)
```

- [x] **Step 4: 更新 registry source path 预期**

```python
assert registration.source_relative_paths == (
    Path("data/locomo/locomo10.json"),
)
```

- [x] **Step 5: 运行 focused tests，确认 RED**

Run:

```bash
uv run pytest \
  tests/test_config_profiles.py \
  tests/test_locomo_conversation_adapter.py \
  tests/test_longmemeval_conversation_adapter.py \
  tests/test_benchmark_registry.py \
  -q
```

Expected: 新路径断言失败，失败原因只与尚未迁移的路径契约有关。

### Task 3: 扩展 PathSettings

**Files:**
- Modify: `src/memory_benchmark/config/settings.py`
- Modify: `src/memory_benchmark/config/__init__.py` if exports require changes
- Test: `tests/test_config_profiles.py`

- [x] **Step 1: 增加明确路径字段**

`PathSettings` 使用：

```python
@dataclass(frozen=True)
class PathSettings:
    project_root: Path
    data_root: Path
    models_root: Path
    outputs_root: Path
    third_party_root: Path
    third_party_benchmarks_root: Path
    third_party_methods_root: Path
```

- [x] **Step 2: 在 load_path_settings() 构造新字段**

```python
return PathSettings(
    project_root=root,
    data_root=root / "data",
    models_root=root / "models",
    outputs_root=root / "outputs",
    third_party_root=root / "third_party",
    third_party_benchmarks_root=root / "third_party" / "benchmarks",
    third_party_methods_root=root / "third_party" / "methods",
)
```

- [x] **Step 3: 删除第一方代码对 benchmarks_root 的依赖**

Run:

```bash
rg -n "benchmarks_root" src tests
```

Expected: 只允许迁移过程中尚待修改的测试引用；Task 7 完成时应为零。

- [x] **Step 4: 运行配置 focused test**

Run:

```bash
uv run pytest tests/test_config_profiles.py -q
```

Expected: PASS。

### Task 4: 迁移参考文档

**Files:**
- Move: `dataset数据结构/` -> `docs/dataset_structures/`
- Move: `benchmark测评流程参考/` -> `docs/evaluation_workflows/`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: current docs that link to these directories

- [x] **Step 1: 执行目录移动**

Run:

```bash
mv dataset数据结构 docs/dataset_structures
mv benchmark测评流程参考 docs/evaluation_workflows
```

- [x] **Step 2: 修复当前事实来源导航**

`AGENTS.md` 的事实优先级改为：

```text
1. third_party/benchmarks/ 官方仓库真实数据和代码
2. 本地论文 PDF
3. docs/dataset_structures/
4. docs/evaluation_workflows/
```

- [x] **Step 3: 检查旧根目录引用**

Run:

```bash
rg -n "dataset数据结构|benchmark测评流程参考" \
  AGENTS.md README.md docs \
  --glob '!docs/handoffs/**'
```

Expected: 当前文档没有旧路径引用；历史 handoff 可保留历史描述。

### Task 5: 规范 runtime data 目录

**Files:**
- Move: `data/HaluMem/` -> `data/halumem/`
- Move: `data/mem-gallery/data/dialog/` -> `data/mem_gallery/dialog/`
- Move: `data/mem-gallery/data/image/` -> `data/mem_gallery/image/`
- Move: `data/mem-gallery/prompt/` -> `data/mem_gallery/prompts/`
- Preserve: `data/locomo/`
- Preserve: `data/longmemeval/`
- Preserve empty semantic location: `data/membench/`

- [x] **Step 1: 记录迁移前文件清单和 hash**

Run a deterministic manifest over canonical source files:

```bash
find data -type f -print0 \
  | sort -z \
  | xargs -0 shasum -a 256 \
  > /tmp/memory-benchmark-data-before.sha256
```

- [x] **Step 2: 执行目录规范化**

使用 `mv` 完成目录移动，不重新编码 JSON/JSONL，不修改图片。macOS 默认文件系统通常
大小写不敏感，`HaluMem -> halumem` 必须经过临时目录名：

```bash
mv data/HaluMem data/__halumem_migration_tmp__
mv data/__halumem_migration_tmp__ data/halumem

mkdir -p data/mem_gallery
mv data/mem-gallery/data/dialog data/mem_gallery/dialog
mv data/mem-gallery/data/image data/mem_gallery/image
mv data/mem-gallery/prompt data/mem_gallery/prompts
rmdir data/mem-gallery/data
rmdir data/mem-gallery
```

- [x] **Step 3: 验证核心文件存在**

```bash
test -f data/locomo/locomo10.json
test -f data/longmemeval/longmemeval_s_cleaned.json
test -f data/longmemeval/longmemeval_m_cleaned.json
test -f data/halumem/HaluMem-Medium.jsonl
test -f data/halumem/HaluMem-Long.jsonl
test -d data/mem_gallery/dialog
test -d data/mem_gallery/image
test -d data/mem_gallery/prompts
```

- [x] **Step 4: 确认旧目录不存在**

```bash
test ! -e data/HaluMem
test ! -e data/mem-gallery
```

Expected: 全部命令 exit 0。

### Task 6: 迁移官方 benchmark 仓库

**Files:**
- Move: `benchmarks/` -> `third_party/benchmarks/`

- [x] **Step 1: 检查目标路径不存在**

```bash
test ! -e third_party/benchmarks
```

- [x] **Step 2: 整体移动仓库目录**

```bash
mv benchmarks third_party/benchmarks
```

- [x] **Step 3: 验证五个官方仓库完整存在**

```bash
test -d third_party/benchmarks/locomo-main
test -d third_party/benchmarks/LongMemEval-main
test -d third_party/benchmarks/HaluMem-main
test -d third_party/benchmarks/Membench-main
test -d third_party/benchmarks/Mem-Gallery-main
```

- [x] **Step 4: 确认旧根目录不存在**

```bash
test ! -e benchmarks
```

Expected: 全部命令 exit 0。

### Task 7: 修改 adapter、registry 和历史兼容 runner 路径

**Files:**
- Modify: `src/memory_benchmark/benchmark_adapters/locomo.py`
- Modify: `src/memory_benchmark/benchmark_adapters/longmemeval.py`
- Modify: `src/memory_benchmark/benchmark_adapters/registry.py`
- Modify: `src/memory_benchmark/runners/memoryos_locomo_full.py`
- Modify: `src/memory_benchmark/cli/main.py`
- Modify: `src/memory_benchmark/cli/dry_run.py`
- Modify affected tests

- [x] **Step 1: 修改 LoCoMo source 常量和读取**

```python
LOCOMO_SOURCE_PATH = "data/locomo/locomo10.json"
```

`load_json()` 使用：

```python
raw_samples = self.load_json("data", "locomo", "locomo10.json")
```

- [x] **Step 2: 修改 LongMemEval-S source 常量和读取**

```python
LONGMEMEVAL_SOURCE_PATH = (
    "data/longmemeval/longmemeval_s_cleaned.json"
)
```

- [x] **Step 3: 修改 legacy MemoryOS runner**

历史 runner 的 dataset source 改为：

```python
project_root / "data" / "locomo" / "locomo10.json"
```

不得修改其受保护历史输出目录。

- [x] **Step 4: 更新 CLI 帮助文本**

项目根描述使用：

```text
Project root containing configs/, data/, third_party/ and outputs/.
```

- [x] **Step 5: 运行 adapter/registry focused tests**

Run:

```bash
uv run pytest \
  tests/test_locomo_conversation_adapter.py \
  tests/test_longmemeval_conversation_adapter.py \
  tests/test_benchmark_registry.py \
  tests/test_memoryos_locomo_full_runner.py \
  -q
```

Expected: PASS。

### Task 8: 更新测试夹具和当前文档路径

**Files:**
- Modify: `tests/test_memoryos_locomo_full_runner.py`
- Modify: `tests/test_prediction_cli.py`
- Modify: `tests/test_experiment_storage.py` only where examples claim real project paths
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/benchmark-scope.md`
- Modify: `docs/current-roadmap.md`
- Modify: `AGENTS.md`

- [x] **Step 1: 区分真实路径和 synthetic fixture**

真实项目路径全部改为 `data/` 或 `third_party/benchmarks/`。仅用于通用测试的
`tmp_path / "benchmarks/fake"` 可以改成中性的 `tmp_path / "sources/fake"`，避免误导。

- [x] **Step 2: 更新项目结构说明**

README 目录树必须体现：

```text
data/
third_party/benchmarks/
third_party/methods/
docs/dataset_structures/
docs/evaluation_workflows/
```

- [x] **Step 3: 扫描第一方旧路径引用**

Run:

```bash
rg -n \
  "benchmarks/|dataset数据结构|benchmark测评流程参考|data/HaluMem|data/mem-gallery" \
  src tests configs README.md AGENTS.md docs \
  --glob '!docs/handoffs/**' \
  --glob '!docs/superpowers/plans/2026-06-14-project-structure-data-migration.md'
```

Expected: 不存在仍代表当前路径的旧引用。计划和历史 handoff 中允许出现迁移说明。

### Task 9: 验证 canonical data 与官方副本一致

**Files:**
- Create: `tests/test_canonical_dataset_sources.py`

- [x] **Step 1: 编写核心文本数据 hash 测试**

测试映射：

```python
DATASET_PAIRS = (
    ("data/locomo/locomo10.json",
     "third_party/benchmarks/locomo-main/data/locomo10.json"),
    ("data/longmemeval/longmemeval_s_cleaned.json",
     "third_party/benchmarks/LongMemEval-main/data/longmemeval_s_cleaned.json"),
    ("data/longmemeval/longmemeval_m_cleaned.json",
     "third_party/benchmarks/LongMemEval-main/data/longmemeval_m_cleaned.json"),
    ("data/halumem/HaluMem-Medium.jsonl",
     "third_party/benchmarks/HaluMem-main/data/HaluMem-Medium.jsonl"),
    ("data/halumem/HaluMem-Long.jsonl",
     "third_party/benchmarks/HaluMem-main/data/HaluMem-Long.jsonl"),
)
```

逐对比较 SHA-256。

- [x] **Step 2: 编写 Mem-Gallery 树清单测试**

分别比较：

```text
data/mem_gallery/dialog
third_party/benchmarks/Mem-Gallery-main/benchmark/data/dialog

data/mem_gallery/image
third_party/benchmarks/Mem-Gallery-main/benchmark/data/image

data/mem_gallery/prompts
third_party/benchmarks/Mem-Gallery-main/benchmark/prompt
```

比较相对路径集合、文件数和逐文件 SHA-256。

- [x] **Step 3: 标记为 integration**

```python
pytestmark = pytest.mark.integration
```

- [x] **Step 4: 运行数据真实性测试**

```bash
uv run pytest tests/test_canonical_dataset_sources.py -q
```

Expected: PASS。

### Task 10: 最终回归和状态收口

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/current-roadmap.md`
- Update: `docs/handoffs/2026-06-14-project-structure-data-migration.md`

- [x] **Step 1: 运行完整离线回归**

```bash
uv run pytest -q
uv run pytest -m api --collect-only -q
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

Expected: 全部 PASS；不执行真实 API。

- [x] **Step 2: 重新计算受保护实验哈希**

Expected:

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

- [x] **Step 3: 综合 review**

重点检查：

- adapter 不再从第三方仓库读取 runtime dataset。
- canonical data 与官方副本一致。
- 第三方仓库内部没有被修改。
- fingerprint 和 manifest 使用新的 canonical 路径。
- 历史 runner 可读取新数据路径，但历史输出未改变。
- 当前文档没有互相矛盾的路径导航。

- [x] **Step 4: 更新动态路线图**

将 Phase E 全部标记完成，把当前精确断点切换到 Phase F：
Dataset Variant 和 LongMemEval 闭环。

本项目当前不是 git repo，因此本计划不包含 commit 步骤。

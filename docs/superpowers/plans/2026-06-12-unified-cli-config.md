# Unified CLI And Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `predict/evaluate/run` 统一入口、TOML 实验 profile、method/evaluator registry，以及可复用已有 prediction 的离线评测 runner。

**Architecture:** `cli/main.py` 只解析和分派；command service 通过 registry 选择 method、benchmark 和 evaluator；prediction 继续复用现有通用 runner，evaluation 只读取标准 artifacts。secret、TOML profile 和单次 CLI 参数分层管理，TOML 最终转换为 owner method 的强类型配置。

**Tech Stack:** Python 3.11+、argparse、tomllib、dataclass、pytest、Rich、uv。

---

## 文件结构

### 配置层

- Create: `configs/methods/mem0.toml`
  - 保存 smoke 和 official-full 的可读键值 profile。
- Create: `configs/evaluators/llm_judge.toml`
  - 保存 compact/detailed judge profile。
- Create: `src/memory_benchmark/config/profiles.py`
  - 安全读取 TOML section、检查未知 section/key，并构造强类型 dataclass。
- Modify: `src/memory_benchmark/config/settings.py`
  - 增加不依赖路径总配置的 `load_openai_settings()`；保留 `load_settings()` 兼容入口。
- Modify: `src/memory_benchmark/config/__init__.py`
  - 导出新 loader。

### Registry 与 command service

- Create: `src/memory_benchmark/methods/registry.py`
  - 定义 method registration 和 Mem0 factory/profile 装配。
- Create: `src/memory_benchmark/evaluators/registry.py`
  - 定义 evaluator registration、兼容矩阵和 factory。
- Create: `src/memory_benchmark/cli/commands.py`
  - 编排 predict/evaluate/run，不解析 argparse。

### Evaluation

- Create: `src/memory_benchmark/runners/evaluation.py`
  - 从标准 artifacts 重建 Question/AnswerResult/GoldAnswerInfo，执行一个或多个 evaluator。
- Modify: `src/memory_benchmark/storage/experiment_paths.py`
  - 增加通用 metric score/summary 路径构造函数。
- Modify: `src/memory_benchmark/runners/__init__.py`
  - 导出 evaluation runner。

### CLI

- Create: `src/memory_benchmark/cli/main.py`
  - `predict/evaluate/run` argparse 子命令和 Rich 错误边界。
- Create: `src/memory_benchmark/__main__.py`
  - 转发到统一 CLI。
- Modify: `pyproject.toml`
  - 注册 `memory-benchmark = "memory_benchmark.cli.main:main"`。
- Modify: `src/memory_benchmark/cli/run_prediction.py`
  - 兼容旧入口，但把 Mem0 profile 来源迁移到 TOML loader。

### 测试与文档

- Create: `tests/test_config_profiles.py`
- Create: `tests/test_method_registry.py`
- Create: `tests/test_evaluator_registry.py`
- Create: `tests/test_artifact_evaluation_runner.py`
- Create: `tests/test_main_cli.py`
- Modify: `tests/test_prediction_cli.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/handoffs/2026-06-11-mem0-locomo-parallel-runner.md`

## Task 1: TOML profile 与延迟 secret 加载

- [x] 在 `tests/test_config_profiles.py` 写 RED tests：
  - `load_typed_profile()` 能从 `[smoke]` 构造 `Mem0Config`。
  - 不存在 section、未知 key、错误字段类型均抛 `ConfigurationError`。
  - `load_openai_settings()` 从指定 `.env` 读取 key/base URL。
  - 只调用 `load_path_settings()` 或读取 TOML 时不要求 API key。
- [x] 运行：

```bash
uv run pytest tests/test_config_profiles.py -q
```

预期：因 `profiles.py` 和 `load_openai_settings()` 不存在而失败。

- [x] 创建 `configs/methods/mem0.toml`，值与当前 `Mem0Config.smoke()` /
  `official_full()` 完全一致；创建 `configs/evaluators/llm_judge.toml`：

```toml
[compact]
mode = "compact"
model = "gpt-4o-mini"

[detailed]
mode = "detailed"
model = "gpt-4o-mini"
```

- [x] 实现：

```python
def load_typed_profile(
    path: str | Path,
    profile_name: str,
    config_type: type[ConfigT],
) -> ConfigT:
    ...
```

要求：

- TOML 顶层必须是 section。
- section 必须存在且是 table。
- key 必须属于 dataclass 字段；未知 key 显式报错。
- 构造 dataclass 时的 `TypeError` 包装为不含 secret 的 `ConfigurationError`。
- 如果 dataclass 有 `profile_name` 字段，loader 自动填入 section 名，并禁止 TOML 重复声明。

- [x] 把 `settings.py` 中 OpenAI 环境读取抽成：

```python
def load_openai_settings(
    project_root: str | Path | None = None,
    env_file: str | Path | None = None,
) -> OpenAISettings:
    ...
```

`load_settings()` 委托 `load_path_settings()` + `load_openai_settings()`，保持原测试兼容。

- [x] 运行配置 focused tests 和原 `tests/test_API.py` 非 API 部分。

## Task 2: Method 与 evaluator registry

- [x] 在 `tests/test_method_registry.py` 写 RED tests：
  - `list_methods()` 返回 `mem0`。
  - `get_method_registration("mem0")` 声明只支持 `locomo`、profile 文件和 API 需求。
  - 未知 method 和不兼容 benchmark 在 method 构造/API 调用前报错。
  - registration 通过 TOML 构造 `Mem0Config`，manifest/source factory 复用现有函数。
- [x] 在 `tests/test_evaluator_registry.py` 写 RED tests：
  - `locomo-f1` 只支持 `locomo` 且不需要 API。
  - `locomo-judge` 只支持 `locomo` 且需要 API。
  - 未知 metric、不兼容 benchmark、未知 judge profile 显式报错。
- [x] 实现冻结 registration dataclass：

```python
@dataclass(frozen=True)
class MethodRegistration:
    name: str
    supported_benchmarks: frozenset[str]
    profile_path: Path
    requires_api: bool
    ...

@dataclass(frozen=True)
class EvaluatorRegistration:
    cli_name: str
    metric_name: str
    supported_benchmarks: frozenset[str]
    requires_api: bool
    ...
```

- [x] registry 不缓存 method/evaluator 实例或 secret；factory 每次运行显式接收配置和依赖。
- [x] 运行 registry tests。

## Task 3: Artifact evaluation runner

- [x] 在 `tests/test_artifact_evaluation_runner.py` 写 RED tests：
  - 使用临时 run 目录中的 manifest、public questions、predictions、private labels 计算
    LoCoMo F1。
  - 完全不构造 method、不读取 `.env`。
  - duplicate id、三方 id 集合不一致、conversation id 不一致、空 prediction、缺 gold
    均抛 `ConfigurationError`。
  - 同一 run 依次执行两个 fake evaluator 时写不同 score/summary 文件。
- [x] 实现：

```python
@dataclass(frozen=True)
class EvaluationRunSummary:
    run_id: str
    benchmark_name: str
    metric_name: str
    total_questions: int
    mean_score: float
    correct_count: int | None
    score_path: str
    summary_path: str

def run_artifact_evaluation(
    run_dir: str | Path,
    evaluator: BaseAnswerEvaluator,
    expected_benchmark: str,
) -> EvaluationRunSummary:
    ...
```

- [x] 从 artifact record 明确重建三个 core 实体，不把原始 dict 直接传给 evaluator。
- [x] score 记录至少包含 question/conversation id、metric name、score、is_correct、details。
- [x] 路径名称只接受 `[a-z0-9_.-]`，避免 metric name 形成路径逃逸。
- [x] 运行 evaluation focused tests 和现有 F1/judge parsing tests。

## Task 4: Command service

- [x] 在 `tests/test_main_cli.py` 先写 command service RED tests：
  - `predict` 编排器复用现有 `run_mem0_locomo_prediction()`，不复制 runner。
  - `evaluate` 根据 manifest benchmark 选择 evaluator registry，并执行 artifact runner。
  - 离线 F1 不加载 OpenAI settings。
  - LLM judge 没有 `confirm_api` 时在 evaluator 构造/API 前报错。
  - `run` 严格先 predict，成功后 evaluate；predict 抛错时 evaluator 不执行。
- [x] 创建 `cli/commands.py`，定义输入 dataclass：

```python
@dataclass(frozen=True)
class PredictCommand:
    ...

@dataclass(frozen=True)
class EvaluateCommand:
    ...

@dataclass(frozen=True)
class RunCommand:
    prediction: PredictCommand
    metrics: tuple[str, ...]
    judge_profile: str = "compact"
```

- [x] command service 负责成本确认、registry 兼容性和依赖装配；不解析 argv、不直接写
  artifact。
- [x] 运行 command tests。

## Task 5: 统一 argparse 入口

- [x] 在 `tests/test_main_cli.py` 增加 CLI RED tests：
  - `main(["--help"])` 显示三个子命令。
  - `predict/evaluate/run` 参数正确映射到 command dataclass。
  - 项目领域异常返回非零 exit code，默认不显示 traceback。
  - `--debug` 时异常不被吞掉。
  - `python -m memory_benchmark --help` 与 console script 可执行。
- [x] 实现 `cli/main.py`：
  - parser 只负责 CLI。
  - Rich 只负责成功摘要和错误展示。
  - 不直接导入 Mem0/MemoryOS adapter 类。
- [x] 实现 `__main__.py` 和 `pyproject.toml` console script。
- [x] 让旧 `cli/run_prediction.py` 继续可运行，但 profile 改为 TOML loader，保持现有函数名和
  测试兼容。
- [x] 运行 CLI/config/registry/evaluation/prediction focused tests。

## Task 6: 文档、综合审查与回归

- [x] README 增加：
  - `predict/evaluate/run` 示例。
  - `.env`、TOML profile、CLI 参数三层配置说明。
  - 离线 F1 不要求 API。
  - 已有 prediction 复算 metric 的流程。
- [x] 更新 `AGENTS.md` 当前断点和入口导航。
- [x] 更新 Mem0 handoff，记录兼容入口、支持矩阵和验证证据。
- [x] 运行：

```bash
uv run pytest \
  tests/test_config_profiles.py \
  tests/test_method_registry.py \
  tests/test_evaluator_registry.py \
  tests/test_artifact_evaluation_runner.py \
  tests/test_main_cli.py \
  tests/test_prediction_cli.py \
  tests/test_documentation_standards.py -q

uv run pytest -q
uv run pytest -m api --collect-only -q
uv run python -m compileall -q src/memory_benchmark tests
uv run memory-benchmark --help
uv run python -m memory_benchmark --help
```

- [x] 做一次最终综合 review，重点检查：
  - secret 是否进入 TOML/manifest/log。
  - `evaluate locomo-f1` 是否在无 `.env` 环境工作。
  - CLI 是否绕过 registry 或强类型配置。
  - 是否误称未迁移的 LongMemEval/MemoryOS 已支持统一入口。
  - 旧 Mem0 CLI 和已有 smoke/full 命令是否兼容。

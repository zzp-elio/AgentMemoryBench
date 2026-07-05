# Unified CLI 与配置分层交接

日期：2026-06-12

## 最新状态（恢复时优先读取）

统一 CLI/config 实现和主线程验证已经完成。最终 review 的 findings 也已完成
RED-GREEN 修复。下文较早的“尚未完成”记录用于保留实施过程，不再代表当前断点。

已完成：

- Mem0 真实 prediction profile 已通过 TDD 从 `Mem0Config.smoke()` /
  `Mem0Config.official_full()` 硬编码迁移到 TOML。
- 用户侧 profile `official-full` 显式映射到
  `configs/methods/mem0.toml` 的 `official_full` section。
- CLI 已补齐 `run` 参数映射、领域异常 stderr 边界、`--debug` 重新抛出，以及 module /
  console script subprocess help 验证。
- README 已增加 `predict/evaluate/run`、三层配置、离线 F1 复用和成本确认说明。
- 文档规范发现的局部 helper 中文 docstring 缺失已修复。
- artifact evaluation 现在拒绝缺失或空的必需 JSONL，不会生成虚假的 0 题成功摘要。
- 损坏 JSONL 会包装为 `ConfigurationError`，默认 CLI 可输出结构化 stderr 错误。
- method registry 现在集中维护公开 profile 名到 TOML section 的映射，并在 predictor
  调用前拒绝未知 profile。

最终验证：

```text
统一 CLI/config focused suite:
57 passed

配置/profile/evaluator/doc focused suite:
39 passed

uv run pytest -q:
247 passed, 3 deselected, 4 subtests passed

uv run pytest -m api --collect-only -q:
3 API tests collected

uv run python -m compileall -q src/memory_benchmark tests:
exit 0

uv run memory-benchmark --help
uv run python -m memory_benchmark --help
两者 exit 0，帮助文本一致
```

没有调用真实 API，没有启动 full experiment。

最终复审：

- 窄范围复审 agent `019ebbb0-ee80-7471-8ad1-2cce61d0b28a` 结论为 **APPROVED**。
- 原 High/Medium findings 均已关闭，profile registry 漂移风险已处理。
- 未发现新的 secret 泄漏路径。
- 唯一非阻塞残余是尚未通过 subprocess 端到端驱动“损坏 artifact -> CLI exit 2”；
  runner 的损坏 JSONL 领域异常测试与 CLI 默认错误边界测试已分别覆盖。

本阶段状态：**完成**。

下一步不是继续修改统一 CLI，而是在用户明确确认 API 余额、预计调用规模和正式
`run_id` 后，使用统一入口启动 Mem0-LoCoMo official-full prediction。

## 目标

建立统一实验入口：

```text
memory-benchmark predict
memory-benchmark evaluate
memory-benchmark run
```

其中 prediction 继续复用通用 conversation + QA runner，evaluation 只读取既有
artifact，不重新调用 method。配置分为 `.env` secret、TOML profile 和单次 CLI 参数，
并在进入 method/evaluator 前转换为强类型配置。

已确认设计：

- `docs/superpowers/specs/2026-06-12-unified-cli-config-design.md`
- `docs/superpowers/plans/2026-06-12-unified-cli-config.md`

## 已完成

### 1. TOML profile 与延迟 secret

新增：

- `configs/methods/mem0.toml`
- `configs/evaluators/llm_judge.toml`
- `src/memory_benchmark/config/profiles.py`
- `tests/test_config_profiles.py`

调整：

- `src/memory_benchmark/config/settings.py`
- `src/memory_benchmark/config/__init__.py`

已实现 `load_typed_profile()`、未知 section/key 检查、强类型 dataclass 构造，以及
独立的 `load_openai_settings()`。读取路径配置或离线 TOML 不要求 API key。

验证：

```text
uv run pytest tests/test_config_profiles.py tests/test_API.py -q -m 'not api'
12 passed, 1 deselected
```

### 2. Method / evaluator registry

新增：

- `src/memory_benchmark/methods/registry.py`
- `src/memory_benchmark/evaluators/registry.py`
- `tests/test_method_registry.py`
- `tests/test_evaluator_registry.py`

当前统一入口有意只声明已经真实装配的组合：

- method：`mem0`
- benchmark：`locomo`
- evaluator：`locomo-f1`、`locomo-judge`

registry 不缓存 method、evaluator 或 secret。Mem0 predictor 采用延迟导入。

### 3. Artifact-only evaluation

新增：

- `src/memory_benchmark/runners/evaluation.py`
- `tests/test_artifact_evaluation_runner.py`

调整：

- `src/memory_benchmark/storage/experiment_paths.py`
- `src/memory_benchmark/runners/__init__.py`

evaluation runner 从标准 public questions、predictions、private labels 重建 core
实体；校验重复 id、三方 id 集合、conversation 对齐、空 prediction 和缺 gold。
不同 metric 写入独立 score/summary 文件，metric 路径名做安全检查。

相关 focused tests 曾单独得到 `27 passed`。

### 4. Command service 与 CLI 骨架

新增：

- `src/memory_benchmark/cli/commands.py`
- `src/memory_benchmark/cli/main.py`
- `src/memory_benchmark/__main__.py`
- `tests/test_main_cli.py`

调整：

- `pyproject.toml` 注册
  `memory-benchmark = "memory_benchmark.cli.main:main"`

CLI 只解析和分派；command service 负责 registry、API 确认与 runner 编排。
离线 F1 不读取 OpenAI secret。`run` 严格先 prediction，再根据真实 run id 评测。

两个入口已人工确认能显示帮助：

```text
uv run memory-benchmark --help
uv run python -m memory_benchmark --help
```

最近 focused 验证：

```text
uv run pytest tests/test_main_cli.py tests/test_method_registry.py \
  tests/test_evaluator_registry.py tests/test_artifact_evaluation_runner.py -q
27 passed
```

最后一次修复是让 CLI 结果序列化兼容测试使用的 `SimpleNamespace`。

## 实施过程中的旧待办（现已完成，保留作审计）

### A. Mem0 profile 仍未真正迁移到 TOML

当前存在一个明确的不一致：

- 用户侧/旧 CLI profile 名是 `official-full`
- `configs/methods/mem0.toml` section 暂为 `official_full`
- `src/memory_benchmark/cli/run_prediction.py::resolve_mem0_profile()` 仍直接调用
  `Mem0Config.smoke()` / `Mem0Config.official_full()`

因此 registry 虽然可以独立加载 TOML，但真实 prediction 仍未使用 TOML。

建议保持用户侧 `official-full`，显式映射到 TOML section，或把 TOML section 改成
`["official-full"]`。必须用 TDD 修改，并保持以下旧函数/测试兼容：

```text
resolve_mem0_profile(profile_name, confirm_api, confirm_full)
tests/test_prediction_cli.py
```

下一步先读：

- `src/memory_benchmark/cli/run_prediction.py`
- `src/memory_benchmark/methods/registry.py`
- `tests/test_prediction_cli.py`

然后先补 RED test，证明修改 TOML 值会影响真实 prediction profile 装配，而不是继续走
硬编码 classmethod。

### B. CLI 契约还需补齐

检查并补测试：

- `run` 参数到 `RunCommand` 的完整映射。
- project domain error 默认返回非零且不显示 traceback。
- `--debug` 时重新抛出项目异常。
- console script 和 `python -m` 的 subprocess/最小执行验证。
- profile 的 argparse choices 或 registry/profile 错误信息是否足够明确。

### C. 文档与最终回归

尚未更新：

- 根目录 `README.md`
- Mem0 主 handoff：
  `docs/handoffs/2026-06-11-mem0-locomo-parallel-runner.md`

尚未执行：

- Task 6 focused suite
- 全量 `uv run pytest -q`
- API collect-only
- `compileall`
- 最终综合 review

## 精确恢复顺序

1. 读本文件。
2. 读设计和实施计划。
3. 检查工作区中上述新增文件均存在。
4. 运行：

```bash
uv run pytest tests/test_main_cli.py tests/test_method_registry.py \
  tests/test_evaluator_registry.py tests/test_artifact_evaluation_runner.py -q
```

期望：`27 passed`。

5. 按“A. Mem0 profile 迁移”先写 RED test，再改实现。
6. 完成 CLI 契约测试、README、handoff 和全量回归。

## 安全与实验状态

- 本阶段没有调用真实 API，没有产生付费请求。
- 不要启动 Mem0 official-full。
- 不要修改 `third_party/methods/`。
- 不要删除或覆盖受保护实验：
  `outputs/memoryos-locomo-full-20260603/`。
- 当前不是 git repo，不要求 commit。

## Subagent 记录

- Bernoulli 完成 TOML/config loader；focused 验证
  `12 passed, 1 deselected`。
- Copernicus 完成 artifact evaluation runner；相关 focused 验证通过。
- 两者写入范围互不冲突，结果已由主线程集成。

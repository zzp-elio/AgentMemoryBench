# 可观测运行体系与 src-layout 工程结构设计草案

状态: Phase A/B 已完成并通过最终整体审查  
日期: 2026-06-05，最近更新于 2026-06-06  
范围: 本文记录已落地的 Phase A/B，以及尚未实施的 Phase C/D 设计边界。

## Phase A/B 实施状态

Phase A/B 实施计划见 [2026-06-05-observability-artifacts-phase-ab.md](../plans/2026-06-05-observability-artifacts-phase-ab.md)。

Task 1-9 的主体实现、最终审查整改和复审均已完成；最终验证为 focused 79/79、full 161/161、fake MemoryOS runner 37/37 和 `compileall` exit 0，最终 reviewer 复审 APPROVED。实现相对早期设计示例有以下调整和强化：

- 数据集指纹实际写入 `artifacts/dataset_fingerprint.json`。
- 进度快照实际写入 `checkpoints/progress.json`。
- 数据集指纹包含完整规范化 `Dataset` 的确定性 SHA-256，不只依赖源文件哈希。
- resume 在复用或改写任何旧状态前强校验 fingerprint；缺少或不匹配时明确失败。
- JSON 覆盖写和 reconciliation JSONL 重写采用同目录临时文件、`fsync` 和原子替换。
- append-only JSONL 默认严格读取；只有 resume alias reconciliation 显式恢复无行终止符的损坏尾行，中间坏行和完整落盘的坏记录仍失败。
- resume prediction/score 必须属于本次 planned question 范围，且记录中的 conversation_id 必须与计划一致。
- 成功终态的 progress 快照会清空 current conversation/question id。
- public/private question artifacts 每次在 fingerprint 校验后确定性重建，失败重试可恢复一致性。

代码中的 `ExperimentPaths` 是输出路径的权威来源。src-layout 与 pytest 迁移不属于本轮 Phase A/B，仍分别保留为后续 Phase C 和 Phase D。

## 背景

当前项目已经能完成 MemoryOS-LoCoMo 的长周期实验，但终端几乎没有过程反馈。开发者可以通过 `outputs/` 文件判断进度，非开发者则很难知道程序是否卡住、正在处理哪个 conversation、当前完成多少 question、是否发生 API retry。

项目未来会继续接入更多 benchmark 和 method，因此需要同时解决三类问题:

1. 长实验运行过程要可观察、可恢复、可追踪。
2. 实验产物要详细保存，避免为了新增 LLM judge、统计报告或错误分析重复跑昂贵 method。
3. 工程结构要面向长期维护，做到低耦合、高内聚、边界清楚。

## 外部标准调研结论

本设计参考以下权威资料:

- PyPA 的 `src layout vs flat layout` 文档: `src` 布局会要求代码先安装后才能 import，能避免从源码根目录意外导入未安装包，也能把 import 行为更接近真实用户环境。链接: https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
- Setuptools 的 package discovery 文档: `src-layout` 是 Python 包发现的标准布局之一，适合把 import package 与项目根目录下的 docs、tests、scripts、benchmarks 等内容隔离。链接: https://setuptools.pypa.io/en/latest/userguide/package_discovery.html
- pytest 的 good integration practices: 对包项目推荐使用可编辑安装，并提到 `src` 布局可以让测试更接近真实安装后的导入行为。链接: https://docs.pytest.org/en/stable/explanation/goodpractices.html
- uv 的项目管理模型: `uv` 可以继续作为依赖和运行入口管理工具，src-layout 不改变 `uv run` 的基本使用方式。链接: https://docs.astral.sh/uv/concepts/projects/layout/
- uv 的项目创建说明: `uv init --package` 使用 `src` 布局以隔离库代码和项目根目录。链接: https://docs.astral.sh/uv/concepts/projects/init/

这些资料的共同点是: 对于小脚本项目，flat layout 足够；对于需要长期维护、安装、测试和多人协作的包项目，src-layout 更稳。

## 设计原则

1. 先解决运行可观测性，再迁工程结构，最后逐步 pytest 化。
2. 不把第三方源码当成我们自己的 package 代码。
3. 不用“万能 utils”承载核心职责；每个模块按业务职责命名。
4. 实验数据采用 append-only 记录，减少中断和重复运行风险。
5. method public input 与 evaluator-only private label 永远隔离。
6. 任何 expensive run 都必须有 run manifest、redacted config、dataset fingerprint、日志、checkpoint 和最终 summary。
7. 新功能要能小步验证，不做一次性大重构。

## 推荐阶段

### Phase A: 运行可观测性标准化

目标: 不改 src-layout，不迁测试框架，只让当前 MemoryOS-LoCoMo 这类长实验在终端和文件中都可观察。

新增或重构模块:

```text
memory_benchmark/
  observability/
    __init__.py
    run_context.py
    logger_factory.py
    progress_reporter.py
    event_writer.py
```

职责:

- `RunContext`: 记录一次运行的稳定信息，例如 `run_id`、benchmark、method、model、output_dir、resume、start_time。
- `logger_factory`: 创建 rich terminal logger 和 file logger。
- `progress_reporter`: 封装 Rich progress，显示当前阶段、conversation 进度、question 进度、当前 question id。
- `event_writer`: 写 append-only `events.jsonl`，记录结构化运行事件。

终端展示目标:

```text
Memory Benchmark Run
run_id: memoryos-locomo-full-20260603
benchmark: locomo
method: MemoryOS
model: gpt-4o-mini
resume: true
output: outputs/memoryos-locomo-full-20260603

[1/6] Load dataset
[2/6] Prepare method state
[3/6] Add conversations      conv-44  6/10
[4/6] Answer questions       conv-44:q87  762/1540
[5/6] Evaluate answers       locomo_f1
[6/6] Write summary
```

文件日志目标:

```text
outputs/<run_id>/
  logs/
    run.log
    events.jsonl
  checkpoints/
    progress.json
```

`run.log` 面向人类阅读，`events.jsonl` 面向恢复、统计和排查，`checkpoints/progress.json` 保存最近状态，便于外部工具查看当前进度。

### Phase B: 实验产物结构标准化

目标: 让一次实验的所有关键数据都能复用，后续新增 LLM judge 或报告时不需要重新调用 method。

推荐输出结构:

```text
outputs/<run_id>/
  manifest.json
  config.redacted.json
  checkpoints/
    conversation_status.json
    question_status.jsonl
    progress.json
  method_state/
    <conversation_id>/
  artifacts/
    dataset_fingerprint.json
    public_questions.jsonl
    method_predictions.jsonl
    evaluator_private_labels.jsonl
    answer_scores.locomo_f1.jsonl
    answer_scores.llm_judge.jsonl
  logs/
    run.log
    events.jsonl
  summaries/
    summary.json
    summary.md
```

这是 Phase B 的推荐目标结构，不等同于当前 runner 已写出的全部文件。其中 `checkpoints/question_status.jsonl`、`artifacts/answer_scores.llm_judge.jsonl` 和 `summaries/summary.md` 为预留/计划产物，`memoryos_locomo_full` 当前不会写入。

关键文件含义:

- `manifest.json`: 运行总说明，包括 run_id、benchmark、method、代码版本信息、开始结束时间、数据路径。
- `config.redacted.json`: 隐去 API key 后的配置快照。
- `artifacts/dataset_fingerprint.json`: 数据文件路径、大小、hash、conversation/question 计数。
- `public_questions.jsonl`: method 可见 question，不含 gold answer。
- `method_predictions.jsonl`: method 输出 answer，可用于后续重算指标。
- `evaluator_private_labels.jsonl`: evaluator-only gold answer、category、可选 evidence。这个文件不能传给 method，但必须保存以支持复算。
- `answer_scores.*.jsonl`: 每种指标单独保存，避免新增指标覆盖旧结果。
- `method_state/`: 每个 conversation 独立保存 method 状态，支持 conversation 隔离和 resume。

这个设计允许:

1. 已经跑完 F1 后，直接基于 `method_predictions.jsonl` 和 `evaluator_private_labels.jsonl` 追加 LLM judge。
2. 某个指标实现改动后，只重算 `answer_scores.*.jsonl`，不重新调用 method。
3. 某次运行中断后，从 checkpoint 继续。
4. 报告系统读取 manifest 和 scores 生成可视化 summary。

### Phase C: src-layout 工程结构迁移

目标: 将我们自己的 import package 与原始 benchmark、第三方 method、实验输出清晰隔离。

推荐结构:

```text
memoryBenchmark/
  pyproject.toml
  README.md
  AGENTS.md
  .env.example
  src/
    memory_benchmark/
      __init__.py
      core/
      benchmark_adapters/
      methods/
      evaluators/
      runners/
      observability/
      storage/
      config/
      cli/
      prompts/
  tests/
    unit/
    integration/
    e2e/
    fixtures/
  benchmarks/
  models/
  third_party/
    methods/
      MemoryOS-main/
      mem0-main/
  outputs/
  reports/
  docs/
  old/
```

模块职责:

- `src/memory_benchmark/core/`: conversation-QA 实体、接口、校验、异常。
- `benchmark_adapters/`: 原始 benchmark 数据到统一 `Dataset` 的转换。
- `methods/`: method wrapper，只放我们写的 adapter，不放第三方完整仓库。
- `evaluators/`: answer-level metric、LLM judge、score 聚合。
- `runners/`: 编排 dataset、method、evaluator、storage、observability。
- `observability/`: rich 日志、进度条、event log。
- `storage/`: 实验产物读写、manifest、checkpoint、fingerprint。
- `config/`: `.env`、模型名、路径、默认参数读取。
- `cli/`: 命令行入口。
- `prompts/`: LLM judge prompt、reader prompt 等可版本化 prompt。
- `third_party/methods/`: 第三方 method 原始源码，不作为我们的 Python package 安装。

迁移原则:

1. 先让当前 flat layout 的可观测性跑通，再迁 src-layout。
2. 迁移时只移动我们自己的 package 和第三方源码位置，不改业务逻辑。
3. 迁移后必须保证 `uv run python -m unittest discover -s tests -v` 或后续 `uv run pytest` 全量通过。
4. MemoryOS adapter 中所有第三方源码路径必须改成从配置层或 path resolver 获取，不能硬编码旧路径。

### Phase D: pytest 渐进迁移

目标: 使用 pytest 提升测试可读性、fixture 复用、慢测试隔离和参数化能力。

不建议一次性重写所有 unittest。推荐策略:

1. 添加 pytest 作为 dev dependency。
2. 配置 pytest markers:

```text
unit: 纯函数和实体测试
integration: adapter、storage、runner 的小规模集成测试
slow: 长耗时测试
api: 真实 API 调用测试
expensive: 会产生明显成本的真实实验
memoryos: MemoryOS method 相关测试
```

3. 现有 unittest 保留，pytest 可以收集运行。
4. 新测试优先写 pytest。
5. 改到旧模块时顺手迁移相关 unittest，不做一次性全量重写。

推荐命令:

```bash
uv run pytest -m "unit"
uv run pytest -m "integration and not api"
uv run pytest -m "memoryos and not expensive"
uv run pytest -m "api"
```

## 数据复用设计

为了支持“跑一次 method，多次评估”，runner 应拆成两个能力:

1. `run_method`: 调用 method，生成 `method_predictions.jsonl`。
2. `run_evaluation`: 从已有 predictions 和 private labels 计算一个或多个 metric。

这样 MemoryOS-LoCoMo 已有预测可以继续追加:

```text
locomo_f1
locomo_llm_judge
bleu_1
error taxonomy
category report
case study report
```

其中 BLEU-1 或 LLM judge 不应该要求重新 add conversations 或重新 get_answer。

## 错误处理

长实验必须区分以下错误:

- `DatasetLoadError`: 数据读取失败。
- `DatasetValidationError`: 数据字段不满足强约束。
- `MethodAddError`: method 写入 conversation 失败。
- `MethodAnswerError`: method 回答失败。
- `EvaluatorError`: metric 计算失败。
- `RunResumeError`: checkpoint 与 artifacts 不一致。
- `ExternalApiRetryableError`: API timeout、connection reset 等可重试错误。
- `ExternalApiFatalError`: API key 错误、模型不可用等不可重试错误。

错误应同时进入:

1. terminal rich log
2. `logs/run.log`
3. `logs/events.jsonl`
4. 必要时写入 `summaries/summary.json` 的 failure metadata

## 用户已确认的决策

1. 分阶段推进: Phase A 可观测性 -> Phase B 实验产物结构 -> Phase C src-layout -> Phase D pytest。
2. 第三方源码后续迁移到 `third_party/methods/`，而 `src/memory_benchmark/methods/` 只保留 wrapper。
3. `evaluator_private_labels.jsonl` 可以保存 gold answer，以便后续不用重跑 method 即可追加指标。该文件明确只给 evaluator，不传入 method。
4. 继续使用 `outputs/<run_id>/` 作为实验输出根目录，避免引入 `runs/` 与现有输出并存的额外认知成本。

## 暂不做

- 不实现异步 runner。
- 不做 token/cost/latency 指标。
- 不做检索召回指标。
- 不一次性迁移全部 unittest。
- 不把 benchmark 原始仓库移入 `src/`。
- 不把第三方 method 源码作为我们 package 的一部分发布。

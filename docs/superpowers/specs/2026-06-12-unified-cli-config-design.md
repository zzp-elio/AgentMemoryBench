# Unified CLI And Configuration Design

状态：用户已确认，实施中  
日期：2026-06-12

## 目标

提供一个清晰、稳定、可扩展的统一实验入口，使用户可以：

1. 选择 benchmark 和 method 生成回答。
2. 基于已有回答独立计算一个或多个 metric。
3. 一次执行 prediction + evaluation。
4. 通过 TOML 键值文件查看和维护 method/evaluator profile，同时保留 Python 强类型校验。

本设计不改 benchmark 数据模型、method 公共接口或第三方源码。

## CLI 入口

标准入口位于：

```text
src/memory_benchmark/cli/main.py
```

同时暴露：

```text
memory-benchmark ...
python -m memory_benchmark ...
```

`pyproject.toml` 注册 console script。`src/memory_benchmark/__main__.py` 只转发到
`cli.main.main()`。

不在根目录建立承载业务逻辑的 `main.py`。如后续确实需要兼容根目录执行，只允许建立几行
转发文件，不能在其中选择 adapter、构造 method 或计算 metric。

## 子命令

### `predict`

只调用 method 生成回答，不计算 metric：

```bash
memory-benchmark predict \
  --method mem0 \
  --benchmark locomo \
  --profile official-full \
  --run-id mem0-locomo-full-20260612 \
  --confirm-api \
  --confirm-full
```

主要参数：

- `--method`: method registry 中的名称。
- `--benchmark`: benchmark registry 中的名称。
- `--profile`: 当前 method 的 TOML profile。
- `--run-id`: 实验目录标识。
- `--resume`: 使用相同 manifest/checkpoint 恢复。
- `--confirm-api`: 明确允许真实 API。
- `--confirm-full`: 明确允许全量实验。

smoke 专用参数仍可保留，但由 method/benchmark 组合装配器声明，不能污染通用 runner。

### `evaluate`

读取已有标准 artifacts，不重新调用 method：

```bash
memory-benchmark evaluate \
  --run-id mem0-locomo-full-20260612 \
  --metric locomo-f1
```

支持重复传入 metric：

```bash
memory-benchmark evaluate \
  --run-id mem0-locomo-full-20260612 \
  --metric locomo-f1 \
  --metric locomo-judge \
  --judge-profile compact \
  --confirm-api
```

规则：

- benchmark、method、dataset fingerprint 从 run manifest 读取，不要求用户重复输入。
- evaluator 只读取 `method_predictions.jsonl`、
  `evaluator_private_labels.jsonl` 和 `public_questions.jsonl`。
- F1 等离线 metric 不加载 `.env`，不要求 API key。
- LLM judge 才延迟加载 API 配置，并要求 `--confirm-api`。
- metric 与 benchmark 不兼容时，在任何评分/API 调用前报错。
- 每个 evaluator 写独立 score artifact，重复评测不能覆盖其它 metric。

### `run`

依次调用 `predict` 和 `evaluate`：

```bash
memory-benchmark run \
  --method mem0 \
  --benchmark locomo \
  --profile official-full \
  --metric locomo-f1 \
  --run-id mem0-locomo-full-20260612 \
  --confirm-api \
  --confirm-full
```

prediction 完成后才进入 evaluation。prediction 失败时不启动 evaluator；已有完整 prediction
且使用 `--resume` 时，只处理剩余 prediction，再执行用户指定 metric。

## 分层职责

```text
cli/main.py
  解析子命令和参数
  ↓
CLI command service
  查询 registry、加载 profile、执行成本保护
  ↓
benchmark adapter + method factory + evaluator factory
  ↓
generic prediction/evaluation runner
  ↓
standard artifacts
```

约束：

- `main.py` 不直接导入 Mem0/MemoryOS 具体类。
- `main.py` 不读取数据集、不调用 OpenAI、不写 JSONL。
- runner 不解析 CLI 参数。
- adapter 不读取 CLI profile。
- evaluator 不重新调用 method。

## Registry

保留现有 `BenchmarkRegistry`，新增两个明确 registry：

### Method Registry

每个 method registration 声明：

- 公共名称，例如 `mem0`。
- 支持的 profile 名称。
- 构造 method 的 factory。
- method manifest/source identity factory。
- 默认并发数。
- 是否需要 API。
- 当前支持的 benchmark 组合。

registry 只保存声明与 factory，不保存 API key 或运行中的 method 实例。

### Evaluator Registry

每个 evaluator registration 声明：

- CLI metric 名称，例如 `locomo-f1`。
- artifact metric 名称，例如 `locomo_f1`。
- 支持的 benchmark。
- evaluator factory。
- 是否需要 API。
- 默认配置 profile。

不通过大量 `if method == ...`、`if metric == ...` 扩展总入口。

## 配置分类

配置分为三类，不能混放。

### 1. Secret 和环境配置

来源：

```text
.env / process environment
```

内容：

- API key。
- base URL。

规则：

- secret 不进入 TOML、CLI 默认值、manifest 或日志。
- 只有确实需要 API 的命令才调用 `load_openai_settings()`。

### 2. 实验 profile

来源：

```text
configs/
  methods/
    mem0.toml
    memoryos.toml
  evaluators/
    llm_judge.toml
```

示例：

```toml
[smoke]
extraction_model = "gpt-4o-mini"
embedding_model = "text-embedding-3-small"
embedding_dimensions = 1536
reader_model = "gpt-4o-mini"
top_k = 10
max_workers = 1
ingestion_chunk_size = 1
infer = true

[official-full]
extraction_model = "gpt-4o-mini"
embedding_model = "text-embedding-3-small"
embedding_dimensions = 1536
reader_model = "gpt-4o-mini"
top_k = 200
max_workers = 10
ingestion_chunk_size = 1
infer = true
```

TOML 是用户可读、可编辑的键值来源。加载后必须转换为 owner 模块的强类型 dataclass，例如
`Mem0Config`，并执行现有范围校验。

method-specific 配置类型继续归 method 所有，不把所有 method 字段塞进一个中央巨型
`models.py`。通用配置层只负责安全读取 TOML、选择 section 和检查未知键。

### 3. 单次运行参数

来源：

```text
CLI
```

内容：

- method、benchmark、metric。
- profile 名称。
- run id、resume。
- 明确成本确认。
- smoke 范围。

CLI 默认不逐字段覆盖 official profile，避免一个实验因临时参数失去官方配置语义。后续若
需要自定义 profile，用户在 TOML 中新增命名 section，例如 `[ablation-topk-50]`。

## 配置代码布局

```text
src/memory_benchmark/config/
  __init__.py
  settings.py          # project paths；不依赖 API key
  secrets.py           # 延迟读取 OpenAI key/base URL
  profiles.py          # 通用 TOML section 加载、未知键检查
```

现有 `PathSettings` 保留。现有 `OpenAISettings` 移到 `secrets.py` 或保持兼容导出。

`load_settings()` 当前同时加载路径和强制 API key，职责过重。迁移后：

```python
load_path_settings(...)
load_openai_settings(...)
load_profile(path, profile_name)
```

为了兼容现有代码，旧 `load_settings()` 可暂时保留并委托新函数，完成迁移后再决定是否
删除；不能一次性破坏 MemoryOS、Mem0 和 LLM judge。

## 配置优先级

固定优先级：

```text
CLI 运行控制参数 > TOML 命名 profile > dataclass 安全默认值
```

其中 CLI 不覆盖 method 算法参数。环境变量只覆盖 secret，不覆盖实验 profile。

每次运行把最终脱敏配置写入：

```text
manifest.json
config.redacted.json
```

resume 继续要求最终配置完全一致。

## Evaluation Runner

新增通用 artifact evaluation runner，其输入是 run directory 和 evaluator 列表。

每题按 `question_id` 对齐：

```text
public question
+ method prediction
+ evaluator private label
-> MetricResult
```

强校验：

- 三类 artifact 的 question id 集合必须满足本次评测范围。
- conversation id 必须一致。
- prediction 不能为空。
- gold answer 缺失时立即报错。
- duplicate question id 立即报错。
- benchmark 与 evaluator 不兼容时立即报错。

输出示例：

```text
artifacts/answer_scores.locomo_f1.jsonl
artifacts/answer_scores.locomo_judge_accuracy.jsonl
summaries/evaluation.locomo_f1.json
summaries/evaluation.locomo_judge_accuracy.json
```

已有 prediction 可重复增加 evaluator，不调用 method。

## 错误处理与帮助信息

CLI 只捕获项目领域异常并以 Rich 输出简洁错误，返回非零 exit code。开发调试时保留
`--debug` 输出 traceback。

帮助信息应动态列出：

- 已注册 method。
- 已注册 benchmark。
- 已注册 metric。
- method/benchmark 支持矩阵。
- metric/benchmark 支持矩阵。

未知名称、非法组合、缺失 profile、未知 TOML key、API 未确认和 resume manifest 不匹配都
应在昂贵操作前失败。

## 迁移策略

### Phase 1

1. 引入配置 profile loader 和 Mem0 TOML。
2. 建立 method/evaluator registry。
3. 建立 artifact evaluation runner。
4. 建立统一 `predict/evaluate/run` CLI。
5. 让现有 `run_prediction.py` 委托新装配层，暂不删除兼容入口。
6. 先支持：
   - Mem0 + LoCoMo prediction。
   - LoCoMo F1。
   - LoCoMo LLM judge。

### Phase 2

1. 接入 LongMemEval prediction 和 judge。
2. 把 MemoryOS 从专用 full runner 逐步迁移到统一入口。
3. 兼容验证完成后再删除专用 CLI/runner 中已经重复的装配逻辑。

不在 Phase 1 为尚未迁移的组合伪造“支持”。

## 测试

- TOML profile 正常加载、未知 section、未知 key、类型错误和范围错误。
- 离线 F1 命令在没有 `.env` 时正常运行。
- LLM judge 未确认 API 时在调用前失败。
- registry 对未知 method/metric 和不兼容组合报错。
- `predict` 仍调用现有通用 prediction runner。
- `evaluate` 只读取 artifacts，不调用 method。
- `run` 按 predict -> evaluate 顺序执行。
- resume 保持 manifest/config 一致性。
- CLI exit code、帮助文本和 secret 扫描。
- 默认测试不触网；真实 API 测试继续使用 `api` marker。

## 非目标

- 不在本阶段设计 Web UI。
- 不提供任意 `--set key=value` 参数覆盖。
- 不把配置退化为无类型 `dict` 在系统中传递。
- 不同时重写 Mem0/MemoryOS adapter 算法。
- 不在统一 CLI 中恢复 PrefEval。

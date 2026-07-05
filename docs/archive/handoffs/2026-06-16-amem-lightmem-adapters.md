# 2026-06-16 A-Mem / LightMem Adapter 接入交接

## 当前目标

用户明确要求暂缓通用并行调度，优先接入 A-Mem 和 LightMem。当前原则：

- 复用现有 conversation-QA 通用 runner、标准 artifact、resume 和 Phase G efficiency
  observation。
- 不创建 method × benchmark 专用 runner。
- 不启动 full run 或真实 API，除非用户显式确认 API 余额、样本规模和正式 `run_id`。
- 不修改第三方核心算法。

设计与计划：

- `docs/superpowers/specs/2026-06-16-amem-lightmem-adapter-design.md`
- `docs/superpowers/plans/2026-06-16-amem-lightmem-adapter.md`

## Git 状态

- 当前已初始化 Git 仓库。
- 当前分支：`feature/amem-lightmem-adapters`
- 尚未做 initial commit。
- `.gitignore` 已保护 `.env`、`.claude/`、`data/`、`models/`、`outputs/`、
  `third_party/benchmarks/` 和 third-party 生成物。
- `third_party/methods/` 不整体忽略，因为项目目标是内置已兼容 method 源码；但其嵌套
  `.git/`、cache、logs、outputs、results、qdrant 等生成物已忽略。

## 本轮完成

### A-Mem

已新增/修改：

- `configs/methods/amem.toml`
- `src/memory_benchmark/methods/amem_adapter.py`
- `tests/test_amem_adapter.py`
- `tests/test_amem_registered_prediction.py`
- `tests/test_amem_lightmem_registry.py`
- `src/memory_benchmark/methods/registry.py`
- `src/memory_benchmark/methods/__init__.py`

已完成能力：

- `AMemConfig` 强配置校验。
- `build_amem_source_identity()` 覆盖 A-Mem 官方核心源码。
- `AMem(BaseMemorySystem)` 包装官方 `RobustAgenticMemorySystem`。
- `add(list[Conversation])` 按公开 turn 写入 A-Mem runtime。
- `get_answer(Question)` 基于公开 question 检索上下文并生成答案。
- 私有标签边界测试：gold answer、private evidence 不进入 runtime content 或 reader prompt。
- OpenAI-compatible `api_key/base_url` 传入官方 runtime。
- question-level efficiency observation：
  - `retrieval_latency_ms`
  - `injected_memory_context_tokens`
  - `answer_generation_latency_ms`
- method registry 接入，支持 `smoke` 和 `official-full` profiles。
- registered prediction runner 离线/fake smoke。

### LightMem

已新增/修改：

- `configs/methods/lightmem.toml`
- `src/memory_benchmark/methods/lightmem_adapter.py`
- `tests/test_lightmem_adapter.py`
- `tests/test_lightmem_registered_prediction.py`
- `tests/test_amem_lightmem_registry.py`
- `src/memory_benchmark/methods/registry.py`
- `src/memory_benchmark/methods/__init__.py`

已完成能力：

- `LightMemConfig` 强配置校验。
- `build_lightmem_source_identity()` 覆盖 LightMem 官方核心源码和 LoCoMo 实验入口。
- `import_lightmem_classes()` 可从 vendored `third_party/methods/LightMem/src` 导入官方
  `LightMemory`。
- `LightMem(BaseMemorySystem)` 包装官方 `LightMemory`。
- `add(list[Conversation])` 将统一 conversation 转成官方消息格式。
- 修复真实兼容字段：官方 `MessageNormalizer` 要求 `time_stamp`，当前 wrapper 已输出
  `time_stamp`，不再输出错误的 `timestamp`。
- LightMem 官方配置通过 `LightMemory.from_config(config)` 构造，配置中注入：
  - OpenAI-compatible `api_key/base_url`
  - memory manager LLM
  - 本地 embedding 模型路径
  - 本地 LLMLingua 模型路径
  - conversation 隔离的 Qdrant collection/path
- 固定 reader 使用 OpenAI-compatible chat completion；fake/offline 测试可注入
  `answer_client`。
- question-level efficiency observation：
  - `retrieval_latency_ms`
  - `injected_memory_context_tokens`
  - `answer_generation_latency_ms`
- method registry 接入，支持 `smoke` 和 `official-full` profiles。
- registered prediction runner 离线/fake smoke。

## 依赖变化

A-Mem 官方 robust layer 导入时暴露缺失依赖，已用 `uv` 安装：

```bash
uv add rank-bm25
uv add litellm
```

原因：

- `rank-bm25` 与 `litellm` 均在 `third_party/methods/A-mem/requirements.txt` 中，是
  A-Mem 官方依赖。
- 当前没有安装 A-Mem requirements 中未触发的其他依赖。

## 已执行验证

未执行真实 API，未启动 full run。

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py \
  tests/test_lightmem_adapter.py tests/test_lightmem_registered_prediction.py \
  tests/test_amem_lightmem_registry.py -q
# 18 passed, 2 warnings
```

两个 warning 均来自第三方源码：

- `third_party/methods/A-mem/memory_layer.py`: `ast.Str` deprecation。
- `third_party/methods/LightMem/src/lightmem/configs/logging/base.py`: Pydantic v2
  class-based config deprecation。

下一步还需要运行：

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

已补充运行：

```bash
uv run pytest tests/test_documentation_standards.py -q
# 5 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

如果时间允许，后续可再运行更大范围离线回归。

## 当前断点

恢复时按顺序读取：

1. `AGENTS.md`
2. `docs/current-roadmap.md`
3. 本 handoff
4. `docs/superpowers/plans/2026-06-16-amem-lightmem-adapter.md`

建议下一步：

1. 按用户决策继续：
   - 等 API 充值后做 A-Mem/LightMem 极小真实 API smoke；或
   - 先接 LongMemEval/其他离线评估链路；或
   - 再做通用并行调度 Phase I。

## 禁止事项

- 不启动真实 API。
- 不启动 full run。
- 不修改 `outputs/memoryos-locomo-full-20260603/`。
- 不恢复 PrefEval。
- 不改第三方核心算法。
- 不把 `data/`、`models/`、`outputs/`、`third_party/benchmarks/` 加入 Git。

## 2026-06-16 资源与官方参数对齐

用户已确认：smoke 也采用官方 method 参数，成本控制只通过局部 benchmark 数据规模裁剪。
原因是后续要用小样本真实 observation 估算全量成本；如果 smoke 降低 `top_k`、
`retrieve_k` 或 `retrieve_limit`，局部成本结构会失真。

已新增文档：

- `docs/method-resource-parameter-audit.md`

已调整配置：

- `configs/methods/amem.toml`
  - smoke `retrieve_k` 从 3 改为 10，与官方 robust 脚本默认一致。
- `configs/methods/mem0.toml`
  - smoke `top_k` 从 10 改为 200，与 Mem0 memory-benchmarks 默认检索深度一致。
- `configs/methods/lightmem.toml`
  - smoke 和 official_full `retrieve_limit` 均改为 60，对齐 LightMem LoCoMo reported
    setting 的 `total-limit=60`。

已新增测试：

- `tests/test_method_official_smoke_profiles.py`
  - 锁定 smoke 使用官方 method 参数。

LightMem 资源状态：

- 当前 `models/` 只有 `BAAI/bge-m3` 和 `nltk`。
- LightMem 真实运行缺：
  - `models/all-MiniLM-L6-v2`
  - `models/llmlingua-2-bert-base-multilingual-cased-meetingbank`
- `src/memory_benchmark/methods/lightmem_adapter.py` 已增加本地模型资源强校验：
  - 配置为 `models/...` 或绝对路径时，真实 backend 构造前必须存在对应目录。
  - fake/offline 测试不要求本地模型存在。
  - 传给官方 `LightMemory.from_config()` 的本地模型路径会解析为绝对路径。

已执行验证：

```bash
uv run pytest tests/test_method_official_smoke_profiles.py -q
# 1 passed

uv run pytest tests/test_lightmem_adapter.py tests/test_lightmem_registered_prediction.py tests/test_method_official_smoke_profiles.py -q
# 10 passed, 1 warning

uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_lightmem_adapter.py tests/test_lightmem_registered_prediction.py tests/test_amem_lightmem_registry.py tests/test_method_official_smoke_profiles.py -q
# 21 passed, 2 warnings

uv run pytest tests/test_documentation_standards.py -q
# 5 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

本次未执行真实 API。

下一步建议：

1. 下载或放置 LightMem 两个本地模型。
2. 确认第一个真实 smoke 的 method、benchmark、样本规模和 run_id。
3. 按 `docs/method-resource-parameter-audit.md` 的顺序执行极小 LoCoMo smoke。

## 2026-06-16 额度风险前暂停点

用户提示 5h 额度即将耗尽，本轮已在合适位置暂停。当前没有运行中的命令或后台 session。

本轮最终改动范围：

- 新增 `docs/method-resource-parameter-audit.md`。
- 新增 `tests/test_method_official_smoke_profiles.py`。
- 修改 `configs/methods/amem.toml`：
  - smoke `retrieve_k=10`。
- 修改 `configs/methods/mem0.toml`：
  - smoke `top_k=200`。
- 修改 `configs/methods/lightmem.toml`：
  - smoke 与 official_full `retrieve_limit=60`。
- 修改 `src/memory_benchmark/methods/lightmem_adapter.py`：
  - 增加 LightMem 本地模型资源强校验。
  - 本地模型引用传给官方 backend 前解析为绝对路径。
  - 缺模型时在真实 backend 构造前抛 `ConfigurationError`。
- 修改 `tests/test_lightmem_adapter.py`：
  - 增加缺模型/模型存在两类资源校验测试。
  - 更新生产 backend 测试，验证官方 config 收到绝对模型路径。
- 更新 `docs/current-roadmap.md`、`AGENTS.md`、`README.md`。
- 在 `docs/superpowers/plans/2026-06-16-amem-lightmem-adapter.md` 顶部补充纠偏说明：
  旧计划中的降参数 smoke 示例已被 `docs/method-resource-parameter-audit.md` 覆盖。

最终验证：

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_lightmem_adapter.py tests/test_lightmem_registered_prediction.py tests/test_amem_lightmem_registry.py tests/test_method_official_smoke_profiles.py -q
# 21 passed, 2 warnings

uv run pytest tests/test_documentation_standards.py -q
# 5 passed

uv run python -m compileall -q src/memory_benchmark tests
# exit 0
```

注意：

- 本轮没有执行真实 API。
- 当前 LightMem 真实 smoke 的唯一已知资源阻塞是缺少两个本地模型目录：
  - `models/all-MiniLM-L6-v2`
  - `models/llmlingua-2-bert-base-multilingual-cased-meetingbank`
- 下一窗口恢复后优先读：
  1. `AGENTS.md`
  2. `docs/current-roadmap.md`
  3. `docs/method-resource-parameter-audit.md`
  4. 本 handoff 的“2026-06-16 资源与官方参数对齐”和“额度风险前暂停点”

## 2026-06-17 LightMem 本地模型资源补齐

用户要求先不跑任何实验，包括 smoke；本轮只补齐资源并暂停，没有执行 prediction、
evaluation、runner 或 OpenAI API 调用。

已通过 Hugging Face CLI 下载：

```bash
hf download sentence-transformers/all-MiniLM-L6-v2 \
  --local-dir models/all-MiniLM-L6-v2 \
  --max-workers 8

hf download microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank \
  --local-dir models/llmlingua-2-bert-base-multilingual-cased-meetingbank \
  --max-workers 8
```

资源位置和体积：

```text
models/all-MiniLM-L6-v2                                         956M
models/llmlingua-2-bert-base-multilingual-cased-meetingbank     680M
models                                                         5.9G
```

已执行轻量本地资源校验，不加载模型、不跑实验：

```bash
uv run python - <<'PY'
from pathlib import Path
from memory_benchmark.config import load_path_settings
from memory_benchmark.methods.registry import load_method_profile

root = Path.cwd()
paths = load_path_settings(root)
config = load_method_profile('lightmem', 'smoke', root)
config.validate_required_local_resources(paths)
print('LightMem local resource validation passed')
print(config.embedding_model_path)
print(config.llmlingua_model_path)
PY
# LightMem local resource validation passed
# models/all-MiniLM-L6-v2
# models/llmlingua-2-bert-base-multilingual-cased-meetingbank
```

已同步：

- `AGENTS.md`
- `docs/current-roadmap.md`
- `docs/method-resource-parameter-audit.md`
- `README.md`

当前暂停点：

- LightMem 本地模型资源已补齐。
- 仍然不启动任何 smoke/full 实验，直到用户重新调整项目后明确确认。
- 下一步应按用户要求“暂停一下重新调整项目”，先讨论项目结构、实验顺序或配置管理，不直接跑实验。

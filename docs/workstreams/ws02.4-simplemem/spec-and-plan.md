---
id: ws02.4
parent: ws02
doc: spec+plan（小型 method 接入合订本）
status: approved (2026-07-07 用户批准；text-only 裁定获认可；Qwen3 emb 已下载)
created: 2026-07-07
---
# ws02.4 SimpleMem Adapter 设计与实施（合订本，已批准）

作者：Claude（架构师）。依据：
[mechanism-simplemem.md](../ws02-phase1-matrix/audits/mechanism-simplemem.md)
（全部机制事实引自该卡）、协议 v3、Track A 审计（难度 M，接入顺序第 1）。
小型 method 接入采用 spec+plan 合订：spec 部分定口径，plan 部分给 task；
用户一次批准即可开工。

## SPEC 部分

### S1 范围与形态

- 接入 **SimpleMemSystem text backend**（机制卡 §6 待决项裁定：不用 auto
  router/EvolveMem/Omni——text path 是 MemoryData 实证口径且无多模态依赖）。
- 目标格子：SimpleMem × LoCoMo、SimpleMem × LongMemEval（既有 benchmark，
  无需新 runner 能力）。
- LLM：官方默认 `gpt-4.1-mini` **显式覆盖为 `gpt-4o-mini`**（项目硬规则），
  经 OpenAI-compatible base_url（ohmygpt）；算法参数保持官方默认
  `WINDOW_SIZE=40 / OVERLAP_SIZE=2 / SEMANTIC_TOP_K=25 / KEYWORD_TOP_K=5 /
  STRUCTURED_TOP_K=5`（机制卡 §4 settings.py:12-40），profile 名
  `official-text-v1`（official=method 官方口径，基座统一按项目规则标注）。
- Embedding：官方默认 `Qwen/Qwen3-Embedding-0.6B` 本地模型——**新增
  `models/Qwen3-Embedding-0.6B` 本地资源前置**（用户需下载，同 LightMem
  models 先例）；adapter 构造前强校验本地路径存在。

### S2 协议 v3 映射

- `consume_granularity="turn"`：`ingest(TurnEvent)` →
  `add_dialogue(speaker=event.speaker_name or role, content=event.content,
  timestamp=转换后时间)`；SimpleMem 内部 window buffer 自行攒批（机制卡 §1）。
- 时间转换：benchmark 原始时间字符串 → ISO（LoCoMo `1:56 pm on 8 May, 2023`
  类格式转换器 + 单测；不可解析时传 None，不猜测）。
- **`end_conversation` → `finalize()`**（残窗抽取；机制卡 §1 finalize 语义），
  finalize 成功返回才算写入完成（R3）。
- `retrieve(RetrievalQuery)`：**绕开 `ask()`**（R1），直接
  `hybrid_retriever.retrieve(query_text)`（planning/reflection 属检索服务型
  LLM，允许并计入 retrieval 成本）；`formatted_memory` = 命中 MemoryEntry 的
  `lossless_restatement` 按 `[timestamp] text` 逐条拼接；`prompt_messages` =
  复刻官方 `AnswerGenerator` prompt 模板（机制卡 §3 answer_generator.py:22-83，
  native 口径，reader 执行 LLM——不调 SimpleMem 自己的 AnswerGenerator）。
- 能力声明：`session_memory_report=False`；`provenance_granularity="none"`
  （MemoryEntry 是 LLM 压缩产物无 turn 锚点，机制卡 §5；不做 sidecar，
  用户占位原则）。
- 隔离与状态：每 isolation_key 独立 LanceDB path/table（state_dir 下）；
  clean retry hook = 删除该 conversation 的 LanceDB 目录后整段重放；
  **buffer 未 finalize 即中断 → 状态不完整，resume 必须整段重 ingest**
  （fail_ingest 语义，机制卡 §4"finalize 前退出 buffer 丢失"）。
- 并行：isolated worker 路径（不共享实例）；`allow_smoke_worker_override=True`。
- 效率观测：builder/retrieval LLM 经 LLMClient 包裹记录 usage（A-Mem wrapper
  先例）；本地 embedding 不产生 API observation；source identity 覆盖
  simplemem 核心源码文件 + 本项目 wrapper。

### S3 未确认项

- Qwen3-Embedding-0.6B 下载由用户执行（下载方式写入 plan T1 验收注记）。
- text-only 依赖集能否不装 multimodal/EvolveMem extras（Track A 卡片 §6 风险）
  ——T1 实测，装不干净则停工上报。

## PLAN 部分（Codex 执行）

纪律：ws 系列全部照旧；基线 771 不得跌破；机制卡是第三方行为唯一事实源，
与实现冲突时停工。

- [x] **T1 依赖与配置**：uv 隔离验证 simplemem text 路径依赖集；
  `configs/methods/simplemem.toml` + 强类型 config（LLM/embedding 路径/
  窗口参数/timeout/retry）；本地模型路径强校验；registry 骨架 +
  source identity。验收：config/registry focused 测试全绿；依赖实测输出留档。

  验收输出：

  ```text
  $ rm -rf /tmp/simplemem-text-venv && uv venv /tmp/simplemem-text-venv && uv pip install --python /tmp/simplemem-text-venv/bin/python openai pydantic lancedb sentence-transformers numpy dateparser pyarrow tantivy rank_bm25 && uv pip install --python /tmp/simplemem-text-venv/bin/python --no-deps -e third_party/methods/SimpleMem
  Using CPython 3.12.8 interpreter at: /Library/Frameworks/Python.framework/Versions/3.12/bin/python3
  Creating virtual environment at: /tmp/simplemem-text-venv
  Activate with: source /tmp/simplemem-text-venv/bin/activate
  Using Python 3.12.8 environment at: /private/tmp/simplemem-text-venv
  Resolved 61 packages in 7.04s
  Prepared 1 package in 207ms
  Installed 61 packages in 886ms
   + annotated-doc==0.0.4
   + annotated-types==0.7.0
   + anyio==4.14.1
   + certifi==2026.6.17
   + click==8.4.2
   + dateparser==1.4.1
   + deprecation==2.1.0
   + distro==1.9.0
   + filelock==3.29.6
   + fsspec==2026.6.0
   + h11==0.16.0
   + hf-xet==1.5.1
   + httpcore==1.0.9
   + httpx==0.28.1
   + huggingface-hub==1.22.0
   + idna==3.18
   + jinja2==3.1.6
   + jiter==0.16.0
   + joblib==1.5.3
   + lance-namespace==0.9.0
   + lance-namespace-urllib3-client==0.9.0
   + lancedb==0.34.0
   + markdown-it-py==4.2.0
   + markupsafe==3.0.3
   + mdurl==0.1.2
   + mpmath==1.3.0
   + narwhals==2.23.0
   + networkx==3.6.1
   + numpy==2.5.1
   + openai==2.44.0
   + packaging==26.2
   + pyarrow==24.0.0
   + pydantic==2.13.4
   + pydantic-core==2.46.4
   + pygments==2.20.0
   + python-dateutil==2.9.0.post0
   + pytz==2026.2
   + pyyaml==6.0.3
   + rank-bm25==0.2.2
   + regex==2026.6.28
   + rich==15.0.0
   + safetensors==0.8.0
   + scikit-learn==1.9.0
   + scipy==1.18.0
   + sentence-transformers==5.6.0
   + setuptools==81.0.0
   + shellingham==1.5.4
   + six==1.17.0
   + sniffio==1.3.1
   + sympy==1.14.0
   + tantivy==0.26.0
   + threadpoolctl==3.6.0
   + tokenizers==0.22.2
   + torch==2.12.1
   + tqdm==4.68.3
   + transformers==5.13.0
   + typer==0.26.8
   + typing-extensions==4.16.0
   + typing-inspection==0.4.2
   + tzlocal==5.4.4
   + urllib3==2.7.0
  Using Python 3.12.8 environment at: /private/tmp/simplemem-text-venv
  Resolved 1 package in 388ms
     Building simplemem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/SimpleMem
        Built simplemem @ file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/SimpleMem
  Prepared 1 package in 154ms
  Installed 1 package in 1ms
   + simplemem==0.3.0 (from file:///Users/wz/Desktop/memoryBenchmark/third_party/methods/SimpleMem)
  ```

  ```text
  $ PYTHONPATH=third_party/methods/SimpleMem /tmp/simplemem-text-venv/bin/python - <<'PY'
  from pathlib import Path
  from main import SimpleMemSystem
  from simplemem.core.settings import settings
  model_path = Path('models/Qwen3-Embedding-0.6B')
  print('SimpleMemSystem', SimpleMemSystem.__name__)
  print('default_window', settings.WINDOW_SIZE)
  print('default_overlap', settings.OVERLAP_SIZE)
  print('model_exists', model_path.exists())
  print('model_files', sorted(path.name for path in model_path.iterdir())[:5])
  PY
  SimpleMemSystem SimpleMemSystem
  default_window 40
  default_overlap 2
  model_exists True
  model_files ['.cache', '.gitattributes', '1_Pooling', 'README.md', 'config.json']
  ```

  ```text
  $ uv run pytest tests/test_simplemem_adapter.py tests/test_method_registry.py -q
  ....................                                                     [100%]
  20 passed in 0.32s
  ```

  ```text
  $ uv run pytest -q
  ........................................................................ [  9%]
  ........................................................................ [ 18%]
  ........................................................................ [ 27%]
  .................................................................... [ 35%]
  ........................................................................ [ 44%]
  ........................................................................ [ 53%]
  ...................................................................... [ 62%]
  ........................................................................ [ 71%]
  ........................................................................ [ 80%]
  ........................................................................ [ 89%]
  ........................................................................ [ 98%]
  ............                                                             [100%]
  =============================== warnings summary ===============================
  tests/test_amem_adapter.py::test_amem_can_import_official_robust_layer_without_calling_api
    /Users/wz/Desktop/memoryBenchmark/third_party/methods/A-mem/memory_layer.py:1: DeprecationWarning: ast.Str is deprecated and will be removed in Python 3.14; use ast.Constant instead
      from ast import Str

  tests/test_lightmem_adapter.py::test_lightmem_can_import_official_lightmemory_class
    /Users/wz/Desktop/memoryBenchmark/third_party/methods/LightMem/src/lightmem/configs/logging/base.py:7: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
      class LoggingConfig(BaseModel):

  -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
  798 passed, 3 deselected, 2 warnings, 6 subtests passed in 94.86s (0:01:34)
  ```
- [x] **T2 写入链路**：`ingest(TurnEvent)` + 时间转换器 + `end_conversation→
  finalize()`；fake SimpleMemSystem 记录调用序列，断言逐 turn add_dialogue
  顺序、timestamp 转换、finalize 恰在末尾一次。验收：adapter ingest focused
  全绿。

  验收输出：

  ```text
  $ uv run pytest tests/test_simplemem_adapter.py -q
  .......                                                                  [100%]
  7 passed in 0.32s
  ```
- [x] **T3 检索链路**：retrieve 绕开 ask、formatted_memory 拼接规则、
  native prompt_messages 复刻 AnswerGenerator 模板（文本摘录注行号）。
  验收：retrieve focused + prompt 结构断言全绿。

  验收输出：

  ```text
  $ uv run pytest tests/test_simplemem_adapter.py -q
  ........                                                                 [100%]
  8 passed in 0.33s
  ```
- [ ] **T4 状态/retry/观测**：LanceDB per-isolation 目录、clean retry hook、
  fail_ingest 语义测试（模拟 finalize 前中断→retry 整段重放）、LLM usage
  observation 接线。验收：状态与观测 focused 全绿。
- [ ] **T5 registered fake 全链路**：LoCoMo + LongMemEval fake smoke 各一，
  artifact/manifest（protocol_version=v3, prompt_track=native）齐全。
  验收：端到端测试全绿；`uv run pytest -q` ≥771；compileall 通过。
- [ ] **T6 收尾**：method-interface-inventory 增 SimpleMem 节、ws02 README
  矩阵表更新、本 README 勾选与断点。验收：git status 干净。

## 明确不做

不接 multimodal/EvolveMem/Omni；不做真实 API smoke（待用户预算）；
不实现 unified prompt（等 LoCoMo/LME unified profile 任务）；不做 provenance
sidecar。

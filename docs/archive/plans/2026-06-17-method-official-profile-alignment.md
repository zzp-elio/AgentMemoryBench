# Method Official Profile Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Mem0、A-Mem、LightMem 的 adapter 从“能跑通框架”修正为“清楚记录并尽量复刻官方/论文 conversation-QA 调用路径”。

**Architecture:** 框架层继续只暴露 `BaseMemorySystem.add(list[Conversation])` 和 `get_answer(Question)`。每个 method adapter 内部负责把 conversation 展开成官方 method 期望的写入粒度，并把官方 answer 接口或官方 `retrieval/search + prompt + gpt-4o-mini` 流程包装成 `get_answer()`。真实 API smoke 在接口清单、配置 profile、离线测试全部完成后再由用户确认 run_id、样本规模和预算。

**Tech Stack:** Python 3.12、uv、pytest、TOML config、OpenAI-compatible API、vendored third-party method source。

---

## 文件职责

- `docs/method-interface-inventory.md`: 记录第三方 method 原生接口、输入输出、调用粒度、prompt 来源和 API 配置传递位置。
- `docs/method-resource-parameter-audit.md`: 记录论文/官方 profile 参数、资源需求、当前 adapter 对齐状态和阻塞项。
- `configs/methods/*.toml`: 保存 method profile，真实 LLM 统一 `gpt-4o-mini`。
- `src/memory_benchmark/methods/mem0_adapter.py`: Mem0 OSS wrapper，需改为官方 memory-benchmarks prompt reader。
- `src/memory_benchmark/methods/amem_adapter.py`: A-Mem wrapper，需补官方 query keyword generation 和 Table 8 类别 `k`。
- `src/memory_benchmark/methods/lightmem_adapter.py`: LightMem wrapper，需补 `(0.7,512)` profile、turn-pair incremental feeding 和官方 reader prompt。
- `tests/test_mem0_adapter.py`: Mem0 adapter contract/fake tests。
- `tests/test_amem_adapter.py`: A-Mem adapter contract/fake tests。
- `tests/test_lightmem_adapter.py`: LightMem adapter contract/fake tests。

## Task 1: 补全 Method 原生接口清单

**Files:**
- Modify: `docs/method-interface-inventory.md`
- Modify: `docs/method-resource-parameter-audit.md`

- [ ] **Step 1: 逐 method 核对原生接口**

  核对 Mem0、A-Mem、LightMem 的原生接口：

  ```text
  add/build memory:
    function name, input type, output type, write granularity
  retrieve/search:
    function name, input type, output type, top_k/limit config location
  answer/generate:
    native answer function exists or not
    if not, official benchmark prompt path
  offline update:
    exists or not
    trigger timing
  model/api:
    LLM model
    embedding model
    API key/base URL injection location
  ```

- [ ] **Step 2: 明确 profile 类型**

  在文档中给每个 method 标记：

  ```text
  official:
    尽量复刻论文/官方 benchmark 调用链
  controlled:
    使用框架统一 reader 或简化设置，只能用于公平对比，不能宣称复现论文
  ```

- [ ] **Step 3: 运行文档测试**

  Run:

  ```bash
  uv run pytest tests/test_documentation_standards.py -q
  ```

  Expected: `5 passed`

## Task 2: 修正 Mem0 official reader

**Files:**
- Modify: `src/memory_benchmark/methods/mem0_adapter.py`
- Modify: `configs/methods/mem0.toml`
- Test: `tests/test_mem0_adapter.py`

- [ ] **Step 1: 写 fake test 验证 LoCoMo prompt 来源**

  测试目标：Mem0 `get_answer()` 不再使用项目简化 prompt，而是使用 Mem0
  `memory-benchmarks/benchmarks/locomo/prompts.py` 等价 prompt。

- [ ] **Step 2: 写 fake test 验证 LongMemEval prompt 来源**

  测试目标：LongMemEval question 带 `question_time` 时，reader prompt 包含官方
  LongMemEval prompt 的 question date 语义。

- [ ] **Step 3: 实现 prompt wrapper**

  从 vendored Mem0 memory-benchmarks 中复制必要 prompt 逻辑到本项目 adapter/helper，
  不在运行时 import 大型 benchmark app 依赖；保留 source identity 指向原始 prompt 文件。

- [ ] **Step 4: 固定 LLM 为 `gpt-4o-mini`**

  配置中 answerer/judge/extraction 真实 LLM 均使用 `gpt-4o-mini`。如果 Mem0 官方模板默认
  `gpt-4o`，在 manifest 中记录为“项目 official-mini profile 覆盖”。

- [ ] **Step 5: 跑 Mem0 focused tests**

  Run:

  ```bash
  uv run pytest tests/test_mem0_adapter.py -q
  ```

## Task 3: 修正 A-Mem official-mini profile

**Files:**
- Modify: `src/memory_benchmark/methods/amem_adapter.py`
- Modify: `configs/methods/amem.toml`
- Test: `tests/test_amem_adapter.py`

- [x] **Step 1: 写 fake test 验证 query keyword generation**

  测试目标：`get_answer()` 调用顺序为：

  ```text
  generate_query_llm(question)
  -> retrieve_memory(generated_keywords, k)
  -> answer LLM
  ```

- [x] **Step 2: 写 fake test 验证类别 `k`**

  测试目标：LoCoMo category 到 Table 8 `k` 的映射生效：

  ```text
  category 1 -> 40
  category 2 -> 40
  category 3 -> 50
  category 4 -> 50
  category 5 -> 40
  ```

- [x] **Step 3: 处理 adversarial 冲突**

  当前普通 conversation-QA public-input profile 不传 gold answer。A-Mem adversarial 需要
  gold answer 的官方特殊逻辑不进入普通 profile；继续跳过或单独标记为 unsupported。

- [x] **Step 4: 实现 official-mini profile**

  adapter 调官方 robust wrapper 的等价步骤，不把 gold answer 传入 method。

- [x] **Step 5: 跑 A-Mem focused tests**

  Run:

  ```bash
  uv run pytest tests/test_amem_adapter.py -q
  ```

## Task 4: 修正 LightMem `(0.7,512)` official-mini profile

**Files:**
- Modify: `src/memory_benchmark/methods/lightmem_adapter.py`
- Modify: `configs/methods/lightmem.toml`
- Test: `tests/test_lightmem_adapter.py`

- [x] **Step 1: 写 fake test 验证 compression rate**

  测试目标：backend config 中 `compress_config.rate == 0.7`。

- [x] **Step 2: 写 fake test 验证 threshold 512**

  测试目标：profile 显式记录 `stm_threshold=512`。由于当前 LightMem 源码硬编码 512，
  adapter 只允许 `(0.7,512)` official-mini，不允许未支持的 `th=768` 静默运行。

- [x] **Step 3: 写 fake test 验证 turn-pair incremental feeding**

  测试目标：conversation 被拆成 user+assistant pair 多次调用 `add_memory()`，只有最后一次
  `force_segment=True, force_extract=True`。

- [x] **Step 4: 写 fake test 验证 reader prompt**

  测试目标：LoCoMo 使用 LightMem 官方 `search_locomo.py` 等价 prompt；LongMemEval 使用
  包含 `question_time` 的官方 prompt。

- [x] **Step 5: 实现 LightMem profile、写入粒度和 LoCoMo 专门化**

  不改第三方核心算法；只在 adapter 中调整传参、profile 校验和 prompt wrapper。
  当前已额外接入 LoCoMo `add_locomo.py` 的 offline update 顺序，以及
  `search_locomo.py` 风格的 Qdrant payload/vector combined 检索。LongMemEval 保持
  `run_lightmem_gpt.py` 的 `LightMemory.retrieve()` online 路径。

- [x] **Step 6: 跑 LightMem focused tests**

  Run:

  ```bash
  uv run pytest tests/test_lightmem_adapter.py -q
  ```

  最新结果：`15 passed, 1 warning`，未执行真实 API。

## Task 5: 小范围离线回归与文档同步

**Files:**
- Modify: `docs/current-roadmap.md`
- Modify: `AGENTS.md`
- Create or Modify: `docs/handoffs/YYYY-MM-DD-method-official-profile-alignment.md`

- [ ] **Step 1: 跑 focused method tests**

  Run:

  ```bash
  uv run pytest tests/test_mem0_adapter.py tests/test_amem_adapter.py tests/test_lightmem_adapter.py -q
  ```

- [ ] **Step 2: 跑文档测试**

  Run:

  ```bash
  uv run pytest tests/test_documentation_standards.py -q
  ```

- [ ] **Step 3: 跑 compileall**

  Run:

  ```bash
  uv run python -m compileall -q src/memory_benchmark tests
  ```

- [ ] **Step 4: 更新 roadmap / AGENTS / handoff**

  记录哪些 method 已完成 official-mini profile，哪些仍阻塞。真实 API smoke 仍需用户确认
  run_id、样本规模、并发数和预算。

## Task 6: 真实 API smoke 准备门禁

**Files:**
- Modify: `docs/current-roadmap.md`
- Modify: `docs/method-resource-parameter-audit.md`

- [ ] **Step 1: 生成 smoke 候选矩阵**

  默认候选：

  ```text
  Mem0 + LoCoMo: 1 conversation, 1 question
  A-Mem + LoCoMo: 1 conversation, 1 question
  LightMem + LoCoMo: 1 conversation, 1 question
  MemoryOS + LoCoMo: 1 conversation, 1 question
  ```

- [ ] **Step 2: 等用户确认**

  真实 API smoke 需要用户明确确认：

  ```text
  run_prefix
  method list
  benchmark list
  sample size
  max_parallel_runs
  budget or token cap
  ```

---

## Self-Review

- Spec coverage: 覆盖了 method 原生接口记录、Mem0 official prompt、A-Mem query rewrite/category k、LightMem `(0.7,512)` 与 incremental feeding、离线验证和真实 API 门禁。
- Placeholder scan: 无 `TBD` / `TODO` / `implement later`。
- Scope check: 本计划只处理 method official profile 对齐，不处理 full parallel、不跑真实 API、不接新 method。

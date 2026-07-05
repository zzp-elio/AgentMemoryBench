# 2026-06-17 A-Mem official-mini RED 测试交接

## 最新状态

本文件前半部分保留 RED 阶段记录，便于追溯 TDD 过程；当前实际状态以本节和文末
“2026-06-17 续做更新”为准。

- A-Mem RED 测试已转 GREEN。
- A-Mem `get_answer()` 已补齐官方 query keyword generation 等价流程和 Table 8
  GPT-4o-mini category k。
- A-Mem category 5/adversarial 因官方 prompt 需要 gold answer，当前显式拒绝，不进入普通
  public-input smoke。
- A-Mem 官方 `RobustOpenAIController` 忽略 `api_base` 的问题已在 wrapper 层修复：
  adapter 会替换官方 controller 的 OpenAI-compatible client，显式传入 `base_url`，不改第三方
  核心算法。
- 已通过 focused 验证：
  `uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_amem_lightmem_registry.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q`
  为 `43 passed, 1 warning`。
- 文档规范为 `5 passed`；`compileall` exit 0。
- 未执行真实 API。

## 当前状态

用户要求先做 A-Mem，LightMem 剩余 search/offline update 后续再讨论。

本轮开始前已经把上一批 checkpoint 提交并推送到 GitHub：

```text
commit: c01559f
message: feat: align LightMem profile and add cost calibration smoke
remote: origin/main
```

提交前验证已通过：

```text
uv run pytest tests/test_lightmem_adapter.py tests/test_amem_lightmem_registry.py tests/test_lightmem_registered_prediction.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q
47 passed, 1 warning

uv run pytest tests/test_documentation_standards.py -q
5 passed

uv run python -m compileall -q src/memory_benchmark tests
exit 0
```

当前工作区只剩 A-Mem RED 测试改动：

```text
M tests/test_amem_adapter.py
```

## 已确认的 A-Mem 官方路径

事实来源：

- `third_party/methods/A-mem/test_advanced_robust.py`
- `third_party/methods/A-mem/memory_layer_robust.py`
- `third_party/methods/A-mem/llm_text_parsers.py`
- `tmp/pdf_text/A-mem.txt`

官方 robust QA 关键路径：

```text
generate_query_llm(question)
-> retrieve_memory(generated_keywords, k)
-> category-specific prompt
-> answer LLM
```

`generate_query_llm()` prompt：

```text
Given the following question, generate several keywords separated by commas.

Question: {question}

Keywords:
```

Table 8 中 GPT-4o-mini 的 LoCoMo category k：

```text
category 1 -> 40
category 2 -> 40
category 3 -> 50
category 4 -> 50
category 5 -> 40
```

注意：A-Mem 官方 category 5 adversarial prompt 会使用 gold answer 构造二选一选项。
本项目 public-input 规则禁止把 gold answer 传给 method，所以普通 profile 应显式拒绝
category 5，或者保持 LoCoMo adapter 跳过 category 5。当前 RED 测试选择显式拒绝。

## 已写 RED 测试

修改文件：

```text
tests/test_amem_adapter.py
```

新增/修改点：

1. `FakeAMemLLM.get_completion()` 现在区分 query generation prompt：
   - prompt 包含 `generate several keywords separated by commas` 时返回
     `generated keywords`
   - 其他 prompt 返回 `fake answer`
2. 更新 `test_amem_add_and_get_answer_never_pass_private_gold_to_method()`：
   - 期望检索 query 为 `generated keywords`
   - 期望 category 1 使用 `k=40`
   - 继续验证 gold/evidence 没进入 method public input
3. 新增 `test_amem_get_answer_uses_table8_category_k_values()`：
   - category 1/2/3/4 分别应使用 40/40/50/50
4. 新增 `test_amem_rejects_adversarial_category_without_gold_answer()`：
   - category 5 应抛 `ConfigurationError`，错误信息包含 `adversarial`

RED 验证命令：

```bash
uv run pytest tests/test_amem_adapter.py -q
```

当前结果符合预期：

```text
3 failed, 5 passed, 1 warning
```

失败点：

1. `test_amem_add_and_get_answer_never_pass_private_gold_to_method`
   - 当前实际：`{"query": "What does Alice like?", "k": 2}`
   - 期望：`{"query": "generated keywords", "k": 40}`
2. `test_amem_get_answer_uses_table8_category_k_values`
   - 当前实际：直接用原始 question 和 `retrieve_k=10`
   - 期望：用 generated keywords 和 Table 8 category k
3. `test_amem_rejects_adversarial_category_without_gold_answer`
   - 当前实际：没有抛错
   - 期望：category 5 抛 `ConfigurationError`

## 下一步实现建议

只改 A-Mem adapter 和必要配置/文档，不运行真实 API。

建议实现顺序：

1. 修改 `src/memory_benchmark/methods/amem_adapter.py`
   - 增加 Table 8 GPT-4o-mini category k 映射。
   - 在 `get_answer()` 里先检查 `question.category == "5"` 并抛
     `ConfigurationError("A-Mem adversarial ...")`。
   - 增加 `_generate_query_keywords(question, runtime)`：
     - 使用 `_answer_llm`，或 fallback 到 `runtime.llm_controller.llm`。
     - prompt 复刻 `test_advanced_robust.py::generate_query_llm()`。
     - 用与 `llm_text_parsers.parse_keywords_response()` 等价的解析逻辑。
   - retrieval 改为：
     `runtime.find_related_memories_raw(generated_keywords, k=_retrieve_k_for_question(question))`
   - answer prompt 保持当前 category-specific prompt，不传 gold answer。
2. 可选增强：
   - `AMemConfig` 增加 `category_retrieve_k` / `query_keyword_generation` 等显式 profile
     字段，但要避免过度复杂。
   - `configs/methods/amem.toml` 可以保留 `retrieve_k=10` 作为 fallback，同时记录
     official-mini 使用 Table 8。
3. 跑验证：

```bash
uv run pytest tests/test_amem_adapter.py -q
uv run pytest tests/test_amem_registered_prediction.py tests/test_amem_lightmem_registry.py -q
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

4. 更新：
   - `docs/method-resource-parameter-audit.md`
   - `docs/method-interface-inventory.md`
   - `docs/current-roadmap.md`
   - `AGENTS.md`

## 注意事项

- 不要运行真实 API。
- 不要把 gold answer 传给 A-Mem。
- 不要修改第三方 A-Mem 核心算法。
- 当前 `RobustLLMController(backend="openai")` 在第三方源码中没有显式使用
  `api_base`；真实 API smoke 前需要再核查 ohmygpt base URL 是否真的进入所有 A-Mem LLM
  调用。这个问题尚未解决。

## 2026-06-17 续做更新：A-Mem RED 已转 GREEN

已修改：

- `src/memory_benchmark/methods/amem_adapter.py`
  - 新增 `AMEM_QUERY_KEYWORD_PROMPT_VERSION`。
  - 新增 GPT-4o-mini Table 8 category k 映射：
    `1 -> 40`、`2 -> 40`、`3 -> 50`、`4 -> 50`、`5 -> 40`。
  - `get_answer()` 现在先执行等价于官方 robust QA 脚本的 query keyword generation，
    再用 generated keywords 检索。
  - `get_answer()` 对 category 5/adversarial 显式抛 `ConfigurationError`，原因是
    官方 adversarial prompt 需要 gold answer，和本项目 public-input 规则冲突。
  - 检索 k 现在按 LoCoMo category 使用 Table 8；缺 category 或非 LoCoMo category 时
    回退到 `AMemConfig.retrieve_k`。
  - metadata 记录实际 `retrieve_k`、`query_keywords`、reader prompt version 和
    keyword prompt version。
  - 新增与官方 `parse_keywords_response()` 等价的轻量解析逻辑。
  - source identity 新增覆盖 `test_advanced_robust.py` 和 `run_k_sweep.sh`，让官方 QA
    wrapper 与 k-sweep 脚本变化能影响 resume 身份。
  - 新增 `_ensure_openai_base_url()`：当配置了 ohmygpt/OpenAI-compatible `base_url` 时，
    替换 official runtime 中 `llm_controller.llm.client`，避免 vendored
    `RobustOpenAIController` 忽略 `api_base`。
- `docs/method-interface-inventory.md`
  - A-Mem 当前状态已从“阻塞”更新为“非 adversarial Table 1 GPT-4o-mini profile 已对齐”。
- `docs/method-resource-parameter-audit.md`
  - A-Mem 当前配置矩阵、调用路径、add 粒度表和 smoke 建议已更新。
- `docs/current-roadmap.md`
  - A-Mem query keyword generation + Table 8 category k 项已勾选。
- `AGENTS.md`
  - 修正当前 Git 分支为 `main`。
  - 同步 A-Mem 当前状态、focused 验证和剩余真实 smoke 风险。

已运行验证：

```bash
uv run pytest tests/test_amem_adapter.py tests/test_amem_registered_prediction.py tests/test_amem_lightmem_registry.py tests/test_cost_calibration_smoke.py tests/test_main_cli.py -q
```

结果：

```text
43 passed, 1 warning
```

收尾验证：

```bash
uv run pytest tests/test_documentation_standards.py -q
uv run python -m compileall -q src/memory_benchmark tests
```

结果：

```text
documentation standards: 5 passed
compileall: exit 0
```

真实 API smoke 前仍未解决：

- A-Mem category 5/adversarial 当前不进入普通 public-input smoke；后续若要测 adversarial，
  必须先和用户讨论“benchmark-private gold 是否可以只给固定 reader/scorer，而不能给
  memory method”的边界方案。

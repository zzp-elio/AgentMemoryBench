# 发给 actor：HaluMem H3（unified prompt parity + answer 归一，轻批）

LoCoMo、LongMemEval、MemBench、BEAM 已 `frozen-v1`，不要碰。H1/H2 已
架构师验收通过。当前只执行 `plan-b5-halumem.md` §3 的 **H3**；完成后
停下，不要开始 H4。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b5-halumem.md`
   §2.2 与 §3 H3
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **parity 测试模式参照**：`tests/test_membench_unified_prompt.py`、
   `tests/test_beam_unified_prompt.py`（运行时现场读官方文件比对的写法）
6. 一手事实源：`third_party/benchmarks/HaluMem-main/eval/prompts.py`
   （PROMPT_MEMZERO，canonical 裁决见 actor-prompt-h1.md 末尾裁决块）、
   `eval/llms.py`、`eval/eval_memzero.py`（QA answer 调用点）
7. 现状代码：`benchmark_adapters/halumem.py` 的
   `HALUMEM_MEMZERO_PROMPT` 常量与 `build_halumem_unified_answer_prompt`

**硬规矩**：官方模板**逐字**（含任何 typo/空白）；不改 metric/evaluator
（H4）、不改 runner、不调真实 API、不跑全量、不动 frozen benchmark；
外部事实附出处行号，查不到写"来源待溯"禁止编造（禁止发明权威——B3
"max_tokens=16 是 MCQ 标准"判例）。

## 架构师已裁定（照此实现，不再停工）

- **canonical = `PROMPT_MEMZERO` 逐字**（H1 裁决块三理由；H1 已证现有
  常量与官方 AST 值 2,104 字符逐字一致——本批把这个事实变成**运行时
  parity 测试**，防未来漂移）。
- **formatted_memory 原样代入**：unified prompt 的 `{context}` 槽填
  method 返回的 `formatted_memory` 原文，框架**不拼装
  `{timestamp}: {memory}` 排版、不重排、不截断**（跨 benchmark 一致
  纪律；官方排版属 method 的 formatted_memory 责任，差异在冻结记录
  声明——plan §3 H3 预留的停工点已由本裁定关闭）。
- **answer LLM 归一**：官方 `llms.py` 无硬编码采样参数，仅从环境变量
  可选注入 `OPENAI_MAX_TOKENS`/`OPENAI_TEMPERATURE`（`llms.py:28,31`）
  → 按"官方未设 = API 默认"处理，如实标注（对齐 membench/beam 先例，
  禁止发明默认值）。actor 需从 `eval_memzero.py` QA answer 实际调用点
  核证再落档（若发现调用点显式传参则停工上报，勿自行取舍）。

## 本批做三件事

1. **运行时 parity 测试**：现场读
   `third_party/benchmarks/HaluMem-main/eval/prompts.py`，AST 提取
   `PROMPT_MEMZERO` 字符串值，断言与 `HALUMEM_MEMZERO_PROMPT` 逐字相等
   （长度+全文），并断言 `build_halumem_unified_answer_prompt` 的
   `{context}`/`{question}` 注入为原样替换（formatted_memory 原文出现、
   无重排/截断/额外拼装）。

2. **answer LLM 配置归一落档**：从官方 QA answer 实际调用点一手核证
   采样参数事实（`eval_memzero.py` + `llms.py`），按 membench/beam
   先例把 halumem 的 answer 归一结论落到相应位置（adapter 常量/
   manifest 声明，以现有 benchmark 的落法为准——先看 membench/beam
   怎么落的再照做），标注出处行号；框架 reader 统一 gpt-4o-mini 的
   既有声明不动。

3. **audit 补录**：在 `notes/halumem-h1-audit.md` 末尾追加 H3 小节：
   parity 测试落点、answer 归一结论表（参数/官方值/框架值/出处）、
   formatted_memory 裁定引用。

自检（按实际测试文件调整并在报告给出实际命令）：

```bash
uv run pytest -q tests/ -k halumem
```

通过后本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): halumem runtime prompt parity + answer normalization`

最后只回复：commit hash、测试尾行、实际改动文件、answer 归一结论
（各参数一行 + 出处行号）、是否存在 plan 偏差/停工点。遇到 plan 未
覆盖的情况立即停工写断点，交回架构师裁决，不要自行发挥。

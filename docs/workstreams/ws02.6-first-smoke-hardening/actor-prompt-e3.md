# 发给 actor：BEAM E3

E1、E2 已完成并由架构师验收（commits `56ee346`、`1ba7bb3` + 验收补强），
不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md` 的
**E3：unified prompt 官方 parity + answer 归一**；完成后停下，不要开始 E4。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md`
   第 1、2 节和第 3 节的 E3
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **官方事实源（逐字对照对象）**：
   - `third_party/benchmarks/BEAM/src/prompts.py:11683-11701`
     （`answer_generation_for_rag` 模板——现有 builder 引用的出处，先
     核实该引用本身是否准确、是否为 RAG/记忆路径应采用的那套；prompts.py
     近 12,000 行，注意还有无其他 answer 模板变体，选择理由写注释）
   - `third_party/benchmarks/BEAM/src/answer_probing_questions/
     answer_generation.py`（实际调用路径：模板如何被填充、LLM 参数）
   - `third_party/benchmarks/BEAM/src/llms_config.json` + `src/llm.py`
     （answer LLM 参数一手抄；不可考项按 ws02.6 规则用 API 默认并如实
     标注——B3 判例：禁止发明"评测标准"之类的权威）
6. 审计对象：`src/memory_benchmark/benchmark_adapters/beam.py` 的
   `build_beam_unified_answer_prompt`（:297 起）；answer 配置在
   `src/memory_benchmark/config/settings.py`
7. 结构模板：B2 C3 / B3 D3 的做法（parity 测试**运行时现场读官方文件**
   比对，参照 `tests/test_membench_unified_prompt.py` 的组织方式）

**硬规矩**：外部事实附"出处文件:行号"；负空间需求附测试函数名清单；
数据一律 `data/BEAM/`；不碰 metric/recall（E4）、policy/variant（E2 已
冻）、不改其他 benchmark、不调真实 API、不跑全量 pytest/compileall、
不更新 README/roadmap/survey/frozen 文档。

本批做三件事：

1. **unified prompt 逐字 parity 审计**：现有 builder 与官方模板逐字对照
   （官方文本有 typo 也原样保留，parity 优先——B3 判例）；formatted_memory
   原样代入记忆槽位（不重排、不截断——官方的 chat 截断机制属 raw-history
   baseline，不进框架，B2 先例）；question 槽位映射断言；若官方模板含
   时间/日期槽位，用公开字段填充并断言。一致则不重写，只补运行时读官方
   文件的逐字断言。
2. **answer LLM 配置按 benchmark 归一**：从 `llms_config.json`/`llm.py`/
   `answer_generation.py` 一手抄官方参数（temperature/max_tokens 等）；
   官方未显式设置的项 → API 默认 + 注释如实标注"框架决定，非官方值"；
   `settings.py` 收敛为 beam 单键，跨 method 一致；不改其他 benchmark。
3. **prediction 侧无需 transform**（BEAM 是自由文本回答，rubric judge
   在 evaluator 层）——确认现状并加一条断言防止误加。

完成后只运行一次：

```bash
uv run pytest -q tests/test_beam_unified_prompt.py \
  tests/test_prediction_cli.py tests/test_benchmark_registry.py \
  tests/test_config_profiles.py
```

（`tests/test_beam_unified_prompt.py` 无则新建；现有 beam prompt 测试在
别的文件里就把该文件加进命令。）

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): freeze BEAM unified answer prompt parity + per-benchmark answer config`。

最后只回复：commit hash、测试尾行、实际改动文件、负空间需求对应测试函数
名清单、是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况立即停工写断点，
交回架构师裁决，不要自行发挥。

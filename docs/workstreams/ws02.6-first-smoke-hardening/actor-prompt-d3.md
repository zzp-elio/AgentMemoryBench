# 发给 actor：MemBench D3

D1、D2 已完成并由架构师验收（commits `a84440e`、`46f21bb` + 验收修正），
不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md` 的
**D3：unified prompt 官方 parity + answer 归一**；完成后停下，不要开始 D4。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md`
   第 1、2 节（尤其 §2.3）和第 3 节的 D3
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **官方事实源（逐字对照对象，不许从 plan 或记忆转抄）**：
   `third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py`
   第 10-30 行（两套 MCQ prompt 模板）与第 80-100 行附近（实际调用：
   observation 的 question/time/choices 如何填入、LLM 调用参数）
6. 审计对象：`src/memory_benchmark/benchmark_adapters/membench.py` 内的
   `MEMBENCH_INSTRUCTION_FIRST`（约 :68）与
   `build_membench_unified_answer_prompt`、
   `normalize_membench_choice_prediction`；answer 配置在
   `src/memory_benchmark/config/settings.py`
7. 结构模板：LongMemEval C3 的做法（`longmemeval_prompt.py` 的
   official_source metadata、`tests/test_longmemeval_prompt.py` 的逐字断言）

**硬规矩**：
- 外部事实（模板文本、行号、参数值）必须附"出处文件:行号"且现场核实；
- **负空间需求必须实现并配测试**：本卡每一条"必须报错/不得出现"的要求，
  完成报告里要列出对应测试函数名；
- 不碰 metric/recall（D4）、不碰 policy/裁剪（D2 已冻）、不改其他
  benchmark、不调用真实 API、不跑全量 pytest/compileall、不更新
  README/roadmap/survey/frozen 文档。

本批做三件事：

1. **unified prompt 逐字 parity 审计**：现有 `MEMBENCH_INSTRUCTION_FIRST`
   与官方 `MembenchAgent.py` 模板逐字对照（注意官方文本若有 typo 也要
   原样保留并注释说明——parity 优先于"改正"）；确认两套官方模板（带/不带
   memory）中我们采用哪套、为何（框架永远有 formatted_memory → 用带
   memory 槽位那套，理由写注释）；`{memory}` 槽位 = formatted_memory
   原样（不重排、不截断）；`{time}` = 公开 question_time；choices 四槽位
   映射断言。一致则不重写，只补逐字断言测试（对照字符串从官方文件
   现场读取比对，参照 LongMemEval C3 验收时的程序化比对法）。
2. **`normalize_membench_choice_prediction` 审计**：对照官方
   `remove_space_and_ent` 的语义（去空白/实体处理）与单字母解析；偏差
   逐处修正 + 断言；坏输出（无字母/多字母/空串）的行为要有明确契约
   （不崩，记为可判错的规范化值），配测试。
3. **answer LLM 配置按 benchmark 归一**：从官方 agent 实际调用一手抄
   参数（temperature 等；官方未显式设置的项用 API 默认并注释记录），
   `settings.py` 里 membench 收敛为 benchmark 单键，跨 method 一致；
   不改其他 benchmark 的配置。

完成后只运行一次：

```bash
uv run pytest -q tests/test_membench_unified_prompt.py \
  tests/test_prediction_cli.py tests/test_benchmark_registry.py \
  tests/test_config_profiles.py
```

（`tests/test_membench_unified_prompt.py` 无则新建；若现有 membench prompt
测试在别的文件里，把该文件加进命令一起跑。）

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): freeze MemBench unified MCQ prompt parity + per-benchmark answer config`。

最后只回复：commit hash、测试尾行、实际改动文件、**负空间需求对应的测试
函数名清单**、是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况立即停工
写断点，交回架构师裁决，不要自行发挥。

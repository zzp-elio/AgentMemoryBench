# 发给 actor：HaluMem H1

LoCoMo、LongMemEval、MemBench、BEAM 已 `frozen-v1`，不要碰。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b5-halumem.md` 的
**H1：来源锁 + 剖面 + 三强制判定 + 论文指标清单**；完成后停下，不要
开始 H2。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b5-halumem.md`
   第 1、2 节和第 3 节的 H1
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. 结构模板：`notes/beam-source-lock.json`、`notes/beam-e1-audit.md`
   （B4 验收版式，含 commit 锁与"来源待溯"的正确写法）
6. 一手事实源：`third_party/benchmarks/HaluMem-main/`（README/论文 PDF/
   `eval/eval_*.py` 五脚本/`eval/prompts.py`）、
   `data/halumem/HaluMem-{Medium,Long}.jsonl`
7. metadata 落法参照 `benchmark_adapters/longmemeval.py`（分块流式哈希）

**硬规矩**：外部事实附"出处文件:行号"且现场核实，查不到写"来源待溯"，
**禁止编造**（B3 有编造判例，验收必查 URL）；数字附可复算脚本，对不上
停工不许凑；**metric 清单必须按实际调用点抄**（签名默认值不作数，B4 有
两次判例）；不改 policy/prompt/metric 代码（H2-H4）、不调真实 API、不跑
全量 pytest/compileall、不更新 README/roadmap/survey/frozen 文档。

本批做五件事：

1. **`notes/halumem-source-lock.json`**：官方 repo URL（README/PDF 一手，
   给出处行号）、arXiv、license；两个 jsonl 现场 SHA-256+字节数；快照若
   带 `.git` 则 rev-parse 锁 commit（照 BEAM 判例），无则如实记录。

2. **`notes/halumem-h1-audit.md`**：双 variant 全量剖面（Medium 直读、
   **Long 必须逐行流式**）——user/session/turn/题数、question_type 分布
   （Medium 预期：Boundary 828/Recall 746/Conflict 769/Generalization
   746/Multi-hop 198/Dynamic Update 180，共 3,467，架构师已扫供自查，
   不一致停工）、**缺 `questions` 键 session 数**（Medium 预期
   491/1,387）、memory_points 字段与 is_update 分布、时间戳三层
   （turn timestamp/session start·end_time）格式清单、evidence 字段
   形态全量统计（空/非空/字面量类型）；附全部脚本。

3. **三个强制判定（各带 文件:行号 证据链，判不了停工）**：
   - **Q1 is_update 语义**：官方 eval 代码如何消费 memory_points 与
     is_update（更新探针的输入是什么？首 session 15/15 全 update 标记
     是否正常语义？）；
   - **Q2 evidence 形态**：questions 的 `evidence` 字符串是什么字面量、
     非空时引用什么（memory_content？turn？）、能否作 retrieval recall
     的 gold；全量解析统计反例；
   - **Q3 canonical QA prompt**：比对 5 个官方 eval 脚本的 QA prompt
     （`PROMPT_MEMZERO/PROMPT_ZEP/…`）：QA 段是否同构？现有
     `build_halumem_unified_answer_prompt` 采用的是哪份、与官方差异
     几处？（只判定不修改——修改属 H3。）异构且无明显 canonical →
     停工列差异表交架构师。

4. **论文指标清单**（spec B6 论文指标覆盖审计在 B5 的落地）：从
   `eval_memzero.py` **实际调用点**+论文抄录三阶段（提取/更新/QA）全部
   指标：名称、公式、分母、聚合维度、judge prompt 出处行号；逐条标注
   现有 evaluator（`evaluators/halumem_*.py`）已覆盖/有偏差/缺失——
   只做清单不改代码。

5. **adapter dataset metadata** 补 source identity + 实际计数（分块
   流式哈希；公私边界不动：answer/evidence/memory_points 不进公开对象，
   如发现现状有泄漏立即停工上报）。

完成后只运行一次（按实际存在的 halumem 测试文件调整并在报告给出实际
命令）：

```bash
uv run pytest -q tests/ -k halumem
```

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): lock HaluMem source identity + real data audit`。

最后只回复：commit hash、测试尾行、实际改动文件、**Q1/Q2/Q3 判定结论
（各一句 + 证据行号）**、论文指标清单的覆盖/缺口统计（几项已覆盖/几项
缺）、是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况立即停工写断点，
交回架构师裁决，不要自行发挥。

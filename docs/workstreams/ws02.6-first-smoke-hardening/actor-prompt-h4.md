# 发给 actor：HaluMem H4（三阶段 metric parity，B5 最重批）

LoCoMo、LongMemEval、MemBench、BEAM 已 `frozen-v1`，不要碰。H1/H2/H3
已架构师验收。当前只执行 `plan-b5-halumem.md` §3 的 **H4**；完成后
停下，不要开始 H5。本批量大，允许分两次 commit（judge prompt parity
一次、聚合/维度/断言一次），每次都跑自检。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b5-halumem.md`
   §2.2、§2.4（0 分母背景）与 §3 H4
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. `notes/halumem-h1-audit.md` §5（论文指标清单——12/12 已实现但 judge
   prompt 全部缩写；分母/公式已按实际调用点核对）
6. 一手事实源：`third_party/benchmarks/HaluMem-main/eval/eval_tools.py`
   （四套官方 judge prompt 本体：`:4-65,68-158,161-215,218-283`）、
   `eval/evaluation.py`（judge 调用点 `:104-197`、聚合公式 `:214-362`、
   memory_type 维度 `:364-383`）
7. 现状代码：`src/memory_benchmark/evaluators/halumem_*.py` 全部文件
8. **parity/契约测试模式参照**：`tests/test_beam_rubric_judge.py`
   （judge prompt 逐字 + 运行时读官方文件断言的写法）、
   `tests/test_halumem_unified_prompt.py`（H3 的 AST 提取先例）

**硬规矩**：官方 judge prompt **逐字**（含 typo/空白）；聚合公式按
**实际调用点**（签名默认值不作数）；**evaluator 契约测试 fixture 必须
经真实序列化函数构造**（D4/D5 假绿判例——先找到生产序列化函数再写
fixture）；不改 runner/adapter/smoke 代码（H2/H3 已冻结口径）、不调
真实 API、不跑全量、judge LLM 统一 gpt-4o-mini 的既有声明不动；数字
对不上停工不许凑。

## 架构师已裁决（照此实现，不再停工）

1. **recall = N/A，声明为冻结限制**：evidence 元素无 turn id（H1
   audit §3），官方 12 指标中无 retrieval recall，**禁止凭文本相似度
   制造 gold 映射**。落法：不新建 halumem recall evaluator；在
   `notes/halumem-h1-audit.md` 追加 H4 小节记录本裁决（引用
   evaluation.py:178-185 官方用途 = QA judge 的 Key Memory Points），
   冻结时进 known limitations。
2. **memory_type 附加维度按官方原样实现**：integrity 与 update 共用
   同一 `total_num` 分母、`memory_acc = integrity_acc + update_acc`
   （evaluation.py:364-383）——公式怪但如实复刻，不"修正"官方；quirks
   已登记。输出进 category/维度 breakdown。
3. **update 聚合 0 分母必须优雅处理**：smoke 裁剪下 update 桶可为空
   （检索空 → 官方语义路由回 integrity，evaluation.py:59-70）。所有
   比率指标分母为 0 时输出 None + 显式计数字段（不抛异常、不硬造 0
   分），契约测试覆盖此边界。
4. **官方代码输出的 `valid` 分母版本与 update `Other` 类**：属官方
   实际评测面（evaluation.py:214-362 实际输出），一并实现，标注为
   官方诊断字段而非论文主指标。

## 本批做五件事

1. **四套 judge prompt 逐字修正**：把现有 evaluator 中的缩写 prompt
   替换为官方 `eval_tools.py` 四段的逐字版本；每套配**运行时 parity
   测试**（现场读官方文件 AST 提取比对，照 H3 先例）；判定解析
   （Correct/Hallucination/Omission 等标签）按官方解析逻辑核对
   （`eval_tools.py`/`evaluation.py` 的 result 消费处）。
2. **聚合公式 parity 复审**：对 H1 audit §5 表逐项复核现有实现与
   `evaluation.py:214-362` 的一致性（分母、加权、interference 排除、
   score==2/0.5*score 折算），修正发现的偏差并逐项列入报告；补
   `valid`/`Other` 诊断字段。
3. **memory_type 维度实现**（裁决 2）+ **per-question_type breakdown
   断言**：QA 六类（Memory Boundary 828/Basic Fact Recall 746/Memory
   Conflict 769/Generalization & Application 746/Multi-hop 198/
   Dynamic Update 180）分开报告，契约测试断言 breakdown 键完整。
4. **0 分母契约**（裁决 3）：update/QA/extraction 全部比率的空分母
   行为统一，测试函数名入报告（负空间清单）。
5. **audit 补录**：`notes/halumem-h1-audit.md` 追加 H4 小节：recall
   N/A 裁决、四套 prompt 修正前后对照（长度即可）、聚合复审结论表、
   0 分母行为表。

自检（按实际测试文件调整并在报告给出实际命令）：

```bash
uv run pytest -q tests/ -k halumem
```

通过后本地 commit（不 push），commit message（若分两次，第二次用
`part 2` 后缀）：
`feat(ws02.6): halumem three-stage metric parity + official judge prompts`

最后只回复：commit hash（们）、测试尾行、实际改动文件、四套 prompt
修正前后长度对照、聚合复审逐项结论（一致/已修正）、0 分母与负空间
测试函数名清单、是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况
立即停工写断点，交回架构师裁决，不要自行发挥。

---

## 架构师裁决（2026-07-11，回应 memory_type 共享分母停工；按此复工）

停工正确：三个候选项否决理由全部成立（评测顺序不是契约、重复 judge
双倍成本且 LLM 非确定性会让同 run 两处判定不一致、半分母违官方
parity）。但存在第四条路，且是既有机制：

**裁决：`memory_type_accuracy` = 合成指标 `halumem-memory-type`，走
既有 `evaluate_run_artifacts` artifact-level 钩子（该钩子已有 8 个
evaluator 使用，runners/evaluation.py:86-96 分发），零 judge 调用。**

实现要点：

1. 新注册 `halumem-memory-type`（`requires_api=False`——纯 artifact
   算术）；`evaluate_run_artifacts` 读同一 run 的
   `answer_scores.halumem_extraction.jsonl` +
   `answer_scores.halumem_update.jsonl`（路径经 `ExperimentPaths`
   的 metric scores 约定 experiment_paths.py:204，不硬编码）。
2. **文件级依赖，不是执行顺序依赖**：用户可任意顺序跑各 metric；
   合成指标在任一上游 artifact 缺失时 `ConfigurationError`，错误信息
   明示"须先运行 halumem-extraction 与 halumem-update"（fail-fast，
   不静默 N/A）。
3. 公式官方原样（evaluation.py:364-383）：per memory_type 共享
   `total_num`（= 该 type 的 integrity 记录数 + update 记录数）、
   `memory_integrity_acc` 与 `memory_update_acc` 同除该分母、
   `memory_acc` = 两者之和（语义 = 该 type 综合记忆准确率的两阶段
   贡献分解，≤1）。0 分母按裁决 3（None+计数）。
4. 上游 per-record 字段：extraction scores 已带 `memory_type`
   （halumem_extraction.py:167）；update scores 若缺该字段则在
   update evaluator 补上（**只加字段，不改判定逻辑**）。
5. 既有的阶段内 per-type breakdown（分母=各自阶段记录数）**保留
   不动**——它与官方共享分母是两个不同口径，都报，summary 里语义
   标注清楚（阶段内 vs 官方共享分母）。
6. 契约测试 fixture 铁律加强版：两份上游 scores artifact 必须由
   真实 extraction/update evaluator（fake judge）跑出后落盘生成，
   **不许手写 jsonl**（D4/D5 假绿判例的直接适用）。

复工范围：按本裁决完成第 3 件事的 memory_type 部分；其余四件事
不受影响照原卡执行。

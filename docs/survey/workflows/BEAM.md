# BEAM 评测流程卡（现行契约）

更新日期：2026-07-19（任务匹配指标勘误；旧冻结记录见
`docs/workstreams/ws02.6-first-smoke-hardening/notes/beam-frozen-v1.md`）

## 1. 官方流程（一手：`third_party/benchmarks/BEAM/src/`）

1. answer 生成：`answer_generation.py` 读单份顶层聚合 chat + 全局
   probing_questions（:154-171）；reader LLM 显式 `temperature=0`
   （:303-307）；模板 = `answer_generation_for_rag`
   （prompts.py:11683-11701）。
2. 评测：`run_evaluation.py:49-77` 按 10 类分发。**官方有效评测面**
   （逐调用点核实，签名默认值不作数——两次被证明的方法论规矩）：
   - 9 类 = 纯 `unified_llm_judge_base_prompt` rubric judge（逐条
     0/0.5/1，官方 `int()` 截断——**prompt 明定 0.5 档，截断是官方真
     bug**）；
   - event_ordering = rubric judge + **τ_b×F1 复合分，alignment 实际走
     LLM**（成对 `llm_equivalence` 贪心 1-1，:407-410）；
     `extract_facts` 被 :405 覆盖（官方死代码），有效行为 =
     `llm_response.split("\n")`；
   - **嵌入（all-MiniLM/bge）、BLEU/ROUGE、semantic_align、fact-level
     全部是分发链之外的死代码**（零调用方），不实现不接入。

## 2. 本框架四步映射（现行契约）

```
ingest：per conversation 按 session（10m 按 plan 顺序展开）注入公开 turn
retrieve：每题一次 RetrievalQuery
answer：unified prompt（官方 answer_generation_for_rag 逐字；
  formatted_memory 原样；官方截断机制不进框架）
  answer LLM 跨 method 固定 gpt-4o-mini / role=user / temperature=0
  （官方一手出处）/ max_tokens=None（框架决定，如实标注）
evaluate：artifact-only
  ├── beam-rubric-judge（主指标；judge/equivalence 双 prompt 逐字；
  │    主分 float【已声明偏差：官方 int() 截断 0.5，prompt 意图为准】
  │    + llm_judge_score_official_int 对照分【供论文数字对比】；
  │    event_ordering 复合分按官方有效行为）
  ├── beam-recall（framework_supplementary；官方 evaluation 不消费 source_chat_ids；
  │    turn provenance 按 evaluator-private raw-id group any-match；1M 歧义 id 可多 child；
  │    未声明 N/A；abstention N/A；session 粒度显式报错
  │    不静默【sN 前缀派生留 Method Track】）
  └── 通用 token-F1 / normalized EM / substring EM：公式组件可复用，但 BEAM
      是 rubric 任务，现行 registry 不启用；不能把“通用公式”误写成“任务通用指标”
```

分类别聚合：category=ability，10 类分开报告（category_breakdown，
离线全链路已断言）。

## 3. Smoke / Resume

- **双结构认证（架构师裁决）**：`--variant 100k smoke` 与
  `--variant 10m smoke` **两次独立 run 都绿**才算 BEAM smoke 认证；
  500k/1m 同构不进认证（variant 旗标照常可选）；不扩展 variant
  selector 子集。
- 每 run：1 conv × 1 round（2 turns）× 1 题实际作答（数据集带 20 题，
  runner smoke 预算裁 1）；10m 切片 = `p1:s1` 前 2 turns；选择不读
  gold；smoke 禁 resume/retry-failed；formal 为 conversation 级。

## 4. 已知边界

- judge 模型按项目基座 gpt-4o-mini（论文 judge 模型见冻结记录）。
- int 截断双轨：论文对比用 official_int，方法评估用 float 主分。
- `'--'` 非法 gold 原子 1 个、1M 4 conv 重复 id：如实计数不修数据。
- 10M 只做 smoke 切片与展开验证，full 成本未测。
- 离线全链路证据：`tests/test_beam_registered_prediction.py`
  （双结构两次 prepare/run + 0.5 双轨断言 + category_breakdown +
  三层 privacy 扫描，零真实 API）。

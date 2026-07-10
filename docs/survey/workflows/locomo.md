# LoCoMo Phase 1 QA 工作流

更新日期：2026-07-10
状态：`frozen-v1`

本文记录框架现行执行语义。字段事实见 [dataset 契约](../datasets/locomo.md)，官方
证据与 metric 细节见 [benchmark 调研卡片](../benchmarks/LoCoMo.md)。

## 1. 冻结的四步主线

```text
1. ingest：按 session number、turn 原顺序注入完整公开 conversation
2. retrieve：每道公开 question 调 method 通用检索接口，得到 formatted_memory
3. answer：框架用 LoCoMo unified prompt + gpt-4o-mini 生成 short answer
4. evaluate：saved artifacts 上离线算 F1 / conditional recall；judge 是可选辅助指标
```

问题只在 conversation ingest 完成并执行 `end_conversation` 后提出。session 之间不
reset；不同 sample/conversation 使用不同 isolation key。QA 阶段不得把 question 或
prediction 写回长期记忆。

## 2. Method 收到什么

公开 ingest 事件包含：conversation/session/turn id、speaker、拼好 caption 的 text、继承
的 session time，以及公开 lifecycle boundary。method 不接收：

- gold answer
- evidence / answer session ids
- event summary
- judge label/rubric
- “该 smoke 问题能否由保留 history 回答”这类私有派生信息

method 可以声明 turn/pair/session/conversation 消费粒度，由通用 aggregator 从 canonical
turn stream 聚合。LoCoMo speaker 是人名，pair method 不能把第一条机械当 user。

## 3. Retrieve 与 unified answer

每题调用通用 `retrieve(query, top_k)`，输出 `RetrievalResult.formatted_memory`；如 method
支持 provenance，可在 item 上提供 `source_turn_ids`。框架统一构造 answer prompt：

- prompt 来源：官方 `task_eval/gpt_utils.py` short-phrase QA 模板
- temporal category 2：追加官方日期提示
- model：`gpt-4o-mini`
- role：`user`
- temperature：0
- max tokens：32
- top-p：1

这些参数按 benchmark 固定，所有 method 一致。native prompt 只保留作 sanity 对照，
不是 LoCoMo Phase 1 主口径。

## 4. Metric

### F1

`locomo-f1` 与官方 scorer 对齐，按 category 处理 normalize、stemming、multi-answer 与
category-3 解释截断；Phase 1 只聚合 category 1/2/3/4。

### Retrieval recall

`locomo-recall` 是 artifact-only evaluator：

- turn provenance 对齐 evidence `dia_id`
- session provenance 将 evidence 映射为 `D<n>` session
- `none` 或旧 run 未声明 provenance：结构化 N/A，不记 0
- 声明 provenance 却缺/空 `source_turn_ids`：fail-fast
- answer prompt、public question、private label question IDs 必须完全一致
- 保存并报告每题实际 `retrieval_query_top_k`
- 4 道 empty-evidence 题按官方记 1，同时另报 non-empty 子集

### Judge / BLEU

LoCoMo 官方 QA 没有 LLM judge。项目 `locomo-judge` 只标记为
`framework_auxiliary_lightmem_reference_v1`；调用前仍需用户明确批准真实 API。
BLEU-1 属于其他 LoCoMo task，不进入 Phase 1 QA。

## 5. Smoke

默认最小 smoke：

```text
1 conversation × 1 round（前 2 个连续 turn）× 1 public question
```

round 只是预算单位，不改变 canonical 数据模型，也不要求完整 speaker pair。question 固定
取第一个 Phase-1 public question，不根据 evidence 选“可回答题”。成功标准是 ingest →
retrieve → unified answer → artifacts → evaluator 全链路跑通，答案可为 0 分。

smoke 禁止 resume 与 `retry_failed`，以免极小运行的旧状态掩盖流程问题。

## 6. Formal resume

- ingest checkpoint：conversation 级；不要求 turn/session 级 resume
- 已完成 conversation：跳过重复 ingest
- answer 失败：复用已保存 retrieval/answer-prompt artifact，不重复调用状态型 retrieve
- 已完成 question：跳过
- evaluation：只读 artifacts 重跑，不构造 method
- manifest identity 不匹配：拒绝 resume；新增 provenance 字段只对缺字段的历史 run 做
  兼容，双方都声明但值变化仍 mismatch

## 7. 必需 artifacts 与隐私门

| Artifact | 作用 | 私有 |
| --- | --- | :---: |
| public questions | method query 输入 | 否 |
| answer prompts / retrieval trace | formatted memory、items、top-k | 否 |
| method predictions | 生成答案 | 否（这里的 `answer` 是 prediction） |
| evaluator private labels | gold/evidence | 是 |
| manifest | source、benchmark policy、method provenance/prompt identity | 否 |
| conversation/question status | resume | 否 |

public question 与 answer prompt 走通用 private-key validator。prediction 合法包含模型生成
的 `answer` 字段，因此检查时只禁止 gold/evidence/judge 等私有键，不能把 prediction
文本本身误判为 gold 泄漏。

## 8. 离线冻结边界

冻结测试使用真实 registry、真实 LoCoMo 数据/adapter/prompt/evaluator，method 算法边界
换成中性 probe，answer LLM 换成固定 fake client；它证明 benchmark 仪器与 artifact
边界可运行，零真实 API。它不证明 Mem0/MemoryOS 等真实 method 的效果、效率、接口保真
或 provenance 已通过；这些留到五个 benchmark 全部冻结后的 Method Track。

# LongMemEval 评测流程卡（现行契约）

更新日期：2026-07-10（B2 `frozen-v1`；冻结记录见
`docs/workstreams/ws02.6-first-smoke-hardening/notes/longmemeval-frozen-v1.md`）

## 1. 官方流程（一手：`third_party/benchmarks/LongMemEval-main/src/`）

1. **generation**（`generation/run_generation.py`）：对每个 instance，把
   history（或 retrieval 结果）+ `Current Date: {question_date}` +
   `Question: {question}` 填入 answer 模板，reader LLM 生成 hypothesis。
   非-CoT 主模板在 `run_generation.py:57`；调用参数 role=user、n=1、
   temperature=0、max_tokens=500（`:360-368`）；官方从 API response 读真实
   usage token（`:372`，api_usage 先例）。
2. **evaluation**（`evaluation/evaluate_qa.py`）：judge LLM 按 question_type
   选 5 套模板之一（`_abs` 后缀走 abstention 模板，`:24-43,101`），
   temperature=0/max_tokens=10，label = `'yes' in response.lower()`（`:113`）；
   输出 overall + per-question_type accuracy（`:130-132`）。
   `print_qa_metrics.py:16` 锁定官方报告 judge = `gpt-4o-2024-08-06`。
3. 官方另有 retrieval（recall_any/recall_all/ndcg_any，turn/session 粒度）与
   index expansion 任务，Phase 1 不进主线。

## 2. 本框架四步映射（现行契约）

```
ingest：per instance（=conversation）按 session 顺序注入公开 turn
  （粒度拆分由 GranularityAggregator 按 method 声明做；异常 role 打
   orphan/dangling 标记不丢弃）
retrieve：该 instance 唯一 question 一次 RetrievalQuery
answer：unified prompt（官方非-CoT 模板逐字，longmemeval_prompt.py）
  History Chats 槽位 = formatted_memory 原样（不重排/不截断/不拼 Session 头）
  Current Date = 公开 question_date；answer LLM 跨 method 固定
  gpt-4o-mini / role=user / temperature=0 / max_tokens=500
evaluate：artifact-only
  ├── longmemeval-judge（主指标；官方 5+1 模板 7/7 逐字 parity；
  │    judge 模型按项目基座 gpt-4o-mini，与论文 gpt-4o 有已声明偏差）
  ├── f1（framework 补充，零特判，framework_supplementary）
  └── longmemeval-recall（conditional：method 声明 turn/session provenance
       即按该粒度评，未声明 N/A；abstention 题 N/A；匹配键=公开 id 空间）
```

分类别聚合由通用 `category_breakdown`（`runners/evaluation.py:219`）承接，
question_type 即 category——**每类分开报告，不只有聚合值**。

## 3. Smoke / Resume（`LONGMEMEVAL_SMOKE_POLICY` / `LONGMEMEVAL_RESUME_POLICY`）

- smoke：1 instance × 1 round（2 turns）× 1 question；轴 = `--rounds`，
  其他轴 fail-fast；选择只按公开顺序，不读 evidence；答对与否不属于
  smoke 成功条件；smoke 禁 resume/retry-failed。
- formal：conversation(=instance) 级 resume；completed question 跳过；
  answer 失败复用 saved retrieval；evaluation 永远 artifact-only。
- policy 声明于 registry 注册块并进 run manifest 顶层
  （`_build_benchmark_policy_manifest`）。

## 4. 已知边界

- `_m`（2.7GB）只做过数据剖面与单 instance 流式加载验证，未做全链路。
- judge 模型 gpt-4o-mini vs 论文 gpt-4o 的偏差在真实运行报告中必须声明。
- 官方 recall_all / ndcg_any 扩展口径未纳入。
- 离线全链路证据：`tests/test_longmemeval_registered_prediction.py`
  （真实 registry + 真实 `_s` 切片 + B0 probe + fake reader，零真实 API）。

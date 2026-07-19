# MemBench 评测流程卡（现行契约）

更新日期：2026-07-19（canonical pair split 已强验收；完整异常处置见
[`异常情况/membench.md`](../异常情况/membench.md)；旧冻结记录见
`docs/workstreams/ws02.6-first-smoke-hardening/notes/membench-frozen-v1.md`）

## 1. 官方流程（一手：`third_party/benchmarks/Membench-main/benchmark/`）

1. env 逐 step 吐 message，agent 写入 memory；最后一步给
   `{question, time, choices}`（`Membenenv.py`）。
2. agent recall 后用 **INSTRUCTION_FIRST** 模板拼 prompt
   （`MembenchAgent.py:21-31`；INSTRUCTION_THIRD 已定义但活跃路径**不
   使用**，只存在于注释代码中；模板含官方 typo `your'conversation`，
   parity 保留）。
3. LLM 调用带 `response_format=json_schema`（enum A-D, strict），
   `json.loads(res)['choice']` 与 `ground_truth` 字母精确比较
   （`MembenchAgent.py:93-115`）。answer LLM 封装在外部依赖
   `benchutils`（不在官方仓库内），参数不可考。

## 2. 本框架四步映射（现行契约）

```
ingest：per trajectory（=conversation）按 step 顺序注入公开 turn
  （第一人称 1 dict step = user turn + assistant turn；第三人称 1 str step = 1 user turn；
   place/time 原文逐侧保留，无时间 noise=None）
retrieve：该 trajectory 唯一 question 一次 RetrievalQuery
answer：unified MCQ prompt（官方 INSTRUCTION_FIRST 逐字，含 typo；
  {memory} = formatted_memory 原样；{time} = 公开 question_time；四选项
  槽位映射）+ prediction_transform 归一化为单字母或 invalid_choice。
  answer LLM 跨 method 固定 gpt-4o-mini / role=user / temperature=0 /
  max_tokens=None（官方参数不可考 → 框架决定并如实标注；已知偏差：官方
  json_schema 结构化输出 vs 框架自由文本+健壮解析，见冻结记录）
evaluate：artifact-only
  ├── membench-choice-accuracy（主指标；解析成功 → 字母精确比较；解析
  │    失败 → 判错 + details 记 parse_failed=true 分开统计）
  └── membench-recall（conditional：method 声明 turn provenance 后，evaluator 私有
       step group 对 retrieved child turn ids 做 any-of；一个官方 step 只计一次；
       session 粒度 → N/A（单 session 无
       结构可召回）；未声明 → N/A；越界 gold 记 unmatched + 单独计数；
       空 evidence → N/A + 计数）
  f1 不适用（MCQ，注册面排除）
```

分类别聚合由通用 `category_breakdown` 承接（category = task_type：
simple/conditional/comparative/aggregative/post_processing/
knowledge_update/lowlevel_rec/RecMultiSession/noisy/highlevel…）——
**每类分开报告，不只有聚合值**（离线全链路已断言）。

## 3. Smoke / Resume（`MEMBENCH_SMOKE_POLICY` / `MEMBENCH_RESUME_POLICY`）

- **标准 smoke（认证口径）= 0_10k 的 4 个源文件各 1 条 trajectory**：
  第一人称 1 step（=2 canonical turns）、第三人称 2 turns，各 1 题。依据 = 路径
  覆盖原则（spec §6.7）：冒号 bug 实证数据形态差异按**文件**分布，每个
  full 会加载的源文件必须至少过一次 parser；边际成本 2 条 trajectory。
- `--membench-sources first_high,first_low,third_high,third_low`
  命名选择轴 = 调试旋钮，非认证口径；非 membench 传入 fail-fast；
  formal 传入 fail-fast（防"部分源被误当全量"）。
- smoke 禁 resume/retry-failed；formal 为 conversation(=tid) 级 resume；
  FULL 加载永远全量 4 源（不受 sources 过滤影响）。

## 4. 已知边界

- 官方 json_schema 结构化输出 vs 框架自由文本解析：偏差已记冻结清单。
- answer LLM 参数官方不可考（benchutils 外部依赖），框架取值如实标注。
- 官方 capacity/efficiency 维度未纳入 Phase 1。
- canonical split 与 private evidence-group schema 已在 ws02.7 关闭：FirstAgent 一个
  dict step 是 user/assistant 两个 canonical turn，但 evaluator-private any-of group 仍只计
  一个官方 step；主线 `ce1a9a8` + `d852fff` + `68b674b`。旧“1 dict step=1 turn”产物
  不得继续证明 Recall 或 LightMem B4。
- 离线全链路证据：`tests/test_membench_registered_prediction.py`
  （4 源双人称路径 + 无冒号 turn_time 非空 + category_breakdown +
  privacy 扫描，零真实 API）。
- 完整施工/强验收证据：
  `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/
  membench-canonical-split-implementation.md`（8 个正式数据文件 4,260 trajectories，
  step→child 映射零缺陷）。
- 100k no-time noise 保持 `turn_time/session_time=None`；39 处 source-step 时间倒序保持
  官方 list 顺序与各自 source time。`QA.time` 只填官方 answer prompt 的 `{time}`，不得
  回填 history。稀有异常由全量 census + deterministic test + registered probe 覆盖，
  不要求付费 smoke 恰好抽中每一例。

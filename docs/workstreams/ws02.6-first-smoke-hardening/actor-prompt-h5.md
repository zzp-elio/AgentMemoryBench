# 发给 actor：HaluMem H5（三操作离线全链路，禁改生产代码）

LoCoMo、LongMemEval、MemBench、BEAM 已 `frozen-v1`，不要碰。H1-H4 已
架构师验收（全量基线 **1054 passed**）。当前只执行
`plan-b5-halumem.md` §3 的 **H5**；完成后停下——H5 之后是架构师冻结包，
不是 actor 批次。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b5-halumem.md`
   §2.4（smoke 固定形状与验收口径）与 §3 H5
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **e2e 模式参照**：其他 benchmark 的离线全链路测试（如
   membench/beam 的 registered_prediction / e2e 测试文件——先
   `ls tests/ | grep -E "e2e|registered"` 找到现行惯例再照做）+
   现有 `test_halumem_operation_level_*` 测试
6. 现状代码：operation-level runner（`runners/` 内 halumem 使用的
   路径）、`prepare_halumem_run`（H2 固定形状）、四个 halumem
   evaluator（H4 后）

**硬规矩**：**本批禁改任何生产代码**（src/ 只读；发现生产 bug 立即
停工上报，不许顺手修）；不调真实 API（judge/answer 全部 fake）；不动
frozen benchmark；数据只从 `data/` 读；负空间清单入报告。

## 本批做一件事：一条真实链路的离线 e2e（Medium smoke 切片）

用真实 registry 的 `prepare_halumem_run`（SMOKE scope，H2 固定形状
4 session×8 turn×1 题）+ probe method + fake judge/answer LLM，跑通
ingest → 三操作探针 → QA → artifact → 四个 evaluator（含
halumem-memory-type 合成链），断言：

1. **三操作运行时调用各 ≥1 次**（提取探针/更新检索探针/QA 的调用
   记录——注意验收口径是"调用发生过"，**不是聚合桶非空**：probe
   method 检索可控非空时 update 桶应非空；另加一个检索返回空的
   fake 变体，断言 update 点被路由回 integrity、update 聚合 0 分母
   时 evaluator 输出 None+计数不崩，plan §2.4 v2 边界）；
2. **operation-level 效率观测存在**（scope_discriminator 与 S1-S4
   观测记录，照现有 `test_halumem_operation_level_records_efficiency_
   observations` 的断言面）；
3. **四 evaluator 全链**：extraction/update/qa 各自跑出 scores
   artifact；`halumem-memory-type` 从两份真实上游 artifact 合成
   （文件级依赖顺畅）；QA `category_breakdown` 覆盖切片内实际
   question_type；
4. **三层 privacy 扫描**：method_predictions / answer_prompts /
   公开 conversation 序列化中 `memory_points`/`answer`/`evidence`
   零泄漏（用现有 `validate_no_private_keys` 或既有扫描测试的写法）；
5. **resume 三契约复跑**（照 B2-B4 冻结前的同款断言）：smoke 禁
   resume（policy 断言）、formal conversation 级 checkpoint 语义、
   artifact-only evaluation 可独立重跑且结果与首跑一致；
6. **`is_generated_qa_session` runner 级锚**（H1 验收新发现的官方
   跳过语义 evaluation.py:51-52；H2 已锚 adapter 层）：合成 Long 式
   切片中带该 flag 的 session **只 ingest、不产生任何探针/QA**，
   断言运行时调用记录为零。

自检（两条都必须跑，第二条是 H4 的教训——新 metric 动过 registry
清单）：

```bash
uv run pytest -q tests/ -k halumem
uv run pytest -q tests/test_evaluator_registry.py tests/test_benchmark_registry.py
```

通过后本地 commit（不 push），只提交本批测试文件，commit message：
`test(ws02.6): halumem three-operation offline e2e`

最后只回复：commit hash、两条测试尾行、实际改动文件、六项断言各自
对应的测试函数名、是否存在 plan 偏差/停工点（发现生产 bug = 立即
停工，这是 H5 存在的意义）。

---

## 架构师裁决（2026-07-11，回应"空 update 检索"停工；生产缺口已由架构师直修，按此复工）

停工正确——H5 禁改生产代码下发现生产缺口即停，正是本批的设计目的。
但三条引证经架构师一手核证后**只有一半成立**：

- **extraction 论断是误诊**：`_update_memory_keys`
  （halumem_extraction.py:350-360）本就有 `if not memories_from_system:
  continue` 非空过滤（docstring "返回有检索结果的 update memory key"），
  空检索的 update point **已经**留在 integrity——extraction 侧无 bug。
- **update 论断成立，是真 parity bug**：update evaluator 对空
  `memories_from_system` 照常拼空串调 judge 并计入分母，与官方
  evaluation.py:59-70（只把非空者放进 update inputs）分歧；后果 =
  空检索 point 被**双计**（integrity 评了它、update 也评了它）+
  update 分母虚增。**不只影响 smoke**：真实 method 检索空时生产评测
  同样错分桶。
- **runner 无错不动**：官方同样无条件探针并记录
  （eval_memzero.py:210-222），路由判定在评测端；probe record 是
  "运行时调用发生过"的证据，正好支撑本卡断言 1。

**架构师已直修**（D5 先例；H5 的禁改是给 actor 的）：
`halumem_update.py` 在 gold 定位后跳过空 `memories_from_system`
（不 judge、不进分母），summary 加 `skipped_empty_retrieval_count`
诊断计数；契约测试
`test_halumem_update_skips_empty_retrieval_per_official_routing`
（probe record 经 runner 真实 `_update_probe_record` 序列化构造，
断言全空时 `update_memory_num==0`、ratio None、skipped==1）。
定向 54 / registry 13 / 全量 **1055 passed**。

**复工范围**：按原卡六项断言复工，零障碍——断言 1 的"检索返回空的
fake 变体"现在能得到官方路由语义（update 桶空 → None+count=0，
extraction 侧该 point 照常进 integrity）。e2e 里可顺带断言
`skipped_empty_retrieval_count` 与空变体探针数一致。

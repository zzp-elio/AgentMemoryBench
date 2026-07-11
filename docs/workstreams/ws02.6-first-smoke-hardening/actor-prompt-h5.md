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

# 发给 actor：BEAM E2

E1 已完成并由架构师验收（commit `56ee346` + 验收补强），不要重做——注意
**E1 已提前实现 evidence→公开 turn-id 映射**（`_map_evidence_turn_ids`，
架构师内容级验证收编），E2 不要再碰它。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md` 的
**E2：10M variant 接纳 + 声明式 smoke/resume policy**；完成后停下，不要
开始 E3。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md`
   第 1、2 节和第 3 节的 E2（含 E1 裁决块）
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. 一手事实源：`notes/beam-e1-audit.md`（E1 验收版——10M 形态、三种
   evidence 结构、全类型字段清单都在里面）
6. 结构模板：B3 的 `MEMBENCH_SMOKE_POLICY` 落法 + registry policy 注册块

**硬规矩**：外部事实附"出处文件:行号"；负空间需求附测试函数名清单；
不碰 prompt/metric（E3/E4）、不调真实 API、不跑全量 pytest/compileall、
不更新 README/roadmap/survey/frozen 文档。**数据一律从 `data/BEAM/` 加载，
禁止加载 `third_party/benchmarks/BEAM/` 内任何数据文件**（用户 2026-07-11
指令；third_party 只作代码/prompt 事实源引用）。

本批做四件事：

1. **注册 `10m` variant**：独立数据目录 `data/BEAM/beam_10M_dataset`；
   顶层 `chat` 是 `list[dict]`（10 个 `{plan-N: …}`），按官方消费顺序
   `chat[i]['plan-{i+1}']`（`ten_milion_pipeline.py:1436-1440`）依序展开
   为 canonical sessions（plan 边界信息留 session metadata，如
   `plan_id`）；probing_questions 全局一份（Q1 判定）。公开 turn id 沿用
   现行 `{session_id}:t{turn_index}` 方案；session id 全 conversation 唯一
   （跨 plan 不冲突——命名方案自定但必须确定性，写注释）。
   evidence 映射复用 E1 已收编的 `_map_evidence_turn_ids`（`'--'` 原子
   按 E1 裁决：不进匹配键、保留官方记录、不崩——加一条针对 10M 位置 5
   event_ordering 题 0 的真实数据回归断言）。
2. **私有键黑名单按 E1 全类型字段清单补全**：`rubric`、`answer`、
   `ideal_response`、`ideal_summary`、`ideal_answer`、
   `expected_compliance`、`compliance_indicators`、`non_compliance_signs`、
   `why_unanswerable`、`key_facts_tested`、`source_chat_ids`、
   `evidence_turn_ids` 等（以 audit "全类型字段清单"节为准逐一核对）；
   公开对象泄漏反例断言（`to_public_dict()` 序列化扫描）。
3. **声明式 `BEAM_SMOKE_POLICY` / `BEAM_RESUME_POLICY`**（对齐 B3 模式）：
   - **标准 smoke（认证口径）= 100k 取 1 conv + 10m 取 1 conv**（双结构
     路径覆盖，plan §2.5/用户拍板），各裁 1 round（2 turns）× 1 题；
     10m 的切片 = 第 1 个 plan 的第 1 个 session 前 2 turns；选择只按
     公开顺序，不读 gold；
   - smoke 禁 resume/retry-failed；formal 为 conversation 级 resume；
   - 未接线裁剪轴对 beam fail-fast；500k/1m 不进认证 smoke（同构），
     variant 旗标照常可选。
   - ⚠️ 若现行 smoke/policy 机制不支持"一次 smoke 跨两个 variant 数据
     目录"，**停工上报**给架构师裁决（可能的落法：smoke 口径定义为
     "各 variant 分别 smoke，认证=100k+10m 两次运行都绿"——但这个语义
     变化必须架构师拍板，不要自行发挥）。
4. metadata/manifest：policy 进 run manifest 顶层（对齐既有
   `_build_benchmark_policy_manifest` 链路）。

完成后只运行一次：

```bash
uv run pytest -q tests/test_beam_adapter.py tests/test_benchmark_registry.py \
  tests/test_main_cli.py tests/test_prediction_cli.py
```

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): adopt BEAM 10M variant + declared smoke/resume policy`。

最后只回复：commit hash、测试尾行、实际改动文件、负空间需求对应测试函数
名清单、是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况立即停工写断点，
交回架构师裁决，不要自行发挥。

---

## 架构师裁决（2026-07-11，回应预埋断点：跨 variant smoke）

停工正确（这是卡里预埋的断点，触发即停是预期行为）。四条证据属实。

**裁决：采用"两次独立 smoke 均通过"语义，不扩展 variant selector。**

理由（复杂度铁律：新机制必须回答"它挡住什么事故"）：

1. variant = 独立数据集 = 独立 manifest/数据指纹/run 身份。一次 run 混
   两个数据集会模糊 run 身份，与"身份=内容"设计冲突；
2. 认证是人层面的陈述："BEAM smoke 绿" ≝ `--variant 100k smoke` 与
   `--variant 10m smoke` **两条命令都绿**。成本 = 多敲一条命令；
3. selector 子集扩展（`--variant 100k,10m`）挡不住任何事故，只增加
   CLI 面——不做。`--variant all` 保持现状（调试用，跑全部 4 个）。

**按此复工，落法调整**：

- `BEAM_SMOKE_POLICY` 保持**单 run 语义**（1 conv × 1 round × 1 题，
  对当前 variant 生效）；不需要任何跨 variant 机制；
- 10m variant 注册后，smoke 默认 variant 仍为 `100k`（default_variant
  不变）；10m smoke 由 `--variant 10m` 显式触发；
- **双结构认证定义落文档不落代码**：在本批 adapter/policy 注释与
  （架构师冻结时的）frozen-v1 记录里写明"BEAM smoke 认证 = 100k 与
  10m 两次独立 smoke 均通过"；
- 其余四件事按原卡执行；e2e 双结构覆盖由 E5 的测试用两次 prepare/run
  实现（E5 卡届时按此写）。

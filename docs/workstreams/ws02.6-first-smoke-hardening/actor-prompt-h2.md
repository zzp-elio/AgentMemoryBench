# 发给 actor：HaluMem H2（固定形状 smoke + 声明式 policy）

> 2026-07-11 v2：用户二次拍板推翻旧口径（"session 内不裁 turn"作废），
> smoke 改为**固定形状硬裁剪**。以本版为准。

LoCoMo、LongMemEval、MemBench、BEAM 已 `frozen-v1`，不要碰。H1 已架构师
验收通过。当前只执行 `plan-b5-halumem.md` §3 的 **H2**；完成后停下，
不要开始 H3。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b5-halumem.md`
   §2.4（smoke 口径 v2，用户拍板）与 §3 H2
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **模式参照**：`benchmark_adapters/membench.py:91-130,365-380`
   （声明式 policy 注册与 metadata 落法）、
   `benchmark_adapters/contracts.py:62-150`（policy 契约）
6. 现状代码：`benchmark_adapters/halumem.py:220-260`（prepare_halumem_run）
   与 `:477-545`（`_build_halumem_smoke_dataset`，本批改造对象）
7. `docs/reference/dataset-quirks.md` HaluMem 表

**硬规矩**：不改 operation-level runner 交错语义、不改 prompt/metric/
evaluator 代码（H3/H4）、不调真实 API、不跑全量 pytest、不动 frozen
benchmark、数据只从 `data/` 读；负空间需求完成报告附**测试函数名清单**；
数字对不上**停工**不许凑。

## 架构师裁定：smoke 固定形状（零旋钮）

**smoke = 首 conversation 的固定极小切片**，形状由规则一次性确定，
不接受任何 CLI 裁剪参数（HaluMem 是 operation-level 交错评测，
"每 conversation 题数"这类通用旋钮语义不通——用户拍板标准化）：

1. **session 前缀 = 三操作最小前缀**（规则：提取探针 ≥1 个 gold
   memory_point；更新探针 ≥1 个 `is_update=="True"` 且
   `original_memories` 非空——注意 is_update 是**字符串**；QA ≥1 题。
   前缀 = 三者首现 session 序号的最大值）。
2. **每个保留 session 的 dialogue 只留前 2 turn**（= 首个 user 锚定
   round；若 session 非 user 开头或不足 2 turn，照取前 2/全部并在
   conversation metadata 标记 `smoke_round_anomaly`——不报错不伪造）。
3. **gold memory_points/questions 结构不裁**（评测面完整；judge 用
   gpt-4o-mini 成本可忽略，ingest 的 method 侧 LLM 调用才是大头，
   已由第 2 条解决）——但 **QA 全 smoke 只保留 1 题**（前缀内首个有
   questions 的 session 的第 1 题，其余题剔除并计数入 metadata）。
4. smoke 分数无意义、update 聚合桶可能为空（检索空 → 官方语义路由到
   integrity）——**smoke 的验收口径 = 三操作运行时调用各 ≥1 次，
   不是聚合桶非空**（H5 会按此断言；本批 metadata 记下形状即可）。

架构师已核事实基线（actor 必须独立复算，不一致停工）：

- Medium 首 conversation（uuid 2f1f897e…）前 5 session 形态：
  turns=12/8/32/60/52，gold_mp=15/11/74/12/11，update_probe=0/0/0/**7**/1，
  questions=3/3/3/**缺 questions 键**/3，dialogue 全部严格 user/assistant
  交替 → 规则前缀 = **4**（s0-s3），且 s3 天然覆盖"缺 questions 键"
  健壮读取路径；
- 20 user 规则前缀分布 = **4×18 / 2×1 / 5×1**；
- smoke 最终形状：4 session × 每 session 2 turn = **8 turn ingest +
  112 个提取 judge 探针 + 7 个更新检索探针 + 1 题 QA**。

## 本批做四件事

1. **改造 `_build_halumem_smoke_dataset`**：实现上述固定形状（规则
   前缀 + 每 session 前 2 turn + QA 1 题）；删除 `session_limit_per_user`
   参数化裁剪；per-conversation 与 dataset metadata 记录完整 smoke
   形状（`smoke_prefix_rule` 三操作首现序号、最终前缀、每 session
   原始/保留 turn 数、QA 保留/剔除数、round anomaly 标记）；某
   conversation 全 session 凑不齐三操作 → 全保留 + 标记
   `smoke_prefix_incomplete=true`（首 conversation 在真实数据上必然
   凑齐，此兜底只为规则完备）。

2. **零旋钮 fail-fast**：`prepare_halumem_run` 在 SMOKE scope 下收到
   任何显式 smoke 裁剪参数（`smoke_session_limit` / `smoke_turn_limit` /
   `smoke_conversation_limit` / question 数类参数——以
   `BenchmarkLoadRequest` 实际字段为准逐一核对）一律
   `ConfigurationError`，错误信息说明"halumem smoke 为固定形状，
   不接受裁剪参数"；负空间测试函数名入报告。

3. **声明式 policy 注册**（照 membench 模式）：
   `HALUMEM_SMOKE_POLICY = BenchmarkSmokePolicy(history_axis="sessions",
   default_history_limit=4, default_isolation_limit=1,
   default_question_limit=1)`（其中 4 是首 conversation 的规则计算值，
   由真实数据锚测试钉住；session 内 round 裁剪是 halumem 专属附加，
   契约无此字段，落 dataset metadata + 契约测试，**不改共享
   contracts.py**）+ `HALUMEM_RESUME_POLICY(smoke_enabled=False,
   ingest_checkpoint="conversation", answer_checkpoint="question",
   reuse_saved_retrieval/evaluation_artifact_only 按 membench 同款值
   抄并核实语义适用)`；两者 `to_dict()` 落 dataset metadata。

4. **测试锚**（真实数据 + 合成 fixture 双层）：
   - 真实 Medium 锚（逐行流式，按现有真实数据测试惯例标记）：规则
     前缀函数对 20 user 的分布 == 4×18/2/5；首 conversation 前缀 == 4
     且 s3 缺 questions 键、update_probe 数 == 7；smoke 数据集最终
     形状 == 4 session/8 turn/1 题；
   - 合成 fixture：三操作分散不同 session 时前缀取最大值；非 user
     开头 session 的 round 裁剪兜底 + anomaly 标记；QA 只留 1 题且
     剔除计数正确；`is_generated_qa_session=True` 的 session 被规则
     忽略（无 gold 天然不满足三操作）且 flag 保留进公开 session
     metadata（若现在 adapter 丢弃该 flag 则补上——官方评测端跳过
     语义的 runner 级断言归 H5，本批只锚 adapter 层）；
   - 顺手全库统计（一行脚本入报告即可，不必进测试）：两 variant
     dialogue 非严格 user/assistant 交替的 session 数——若非 0，
     登记为 quirk 候选交架构师。

自检（按实际测试文件调整并在报告给出实际命令）：

```bash
uv run pytest -q tests/ -k halumem
```

通过后本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): halumem fixed-shape smoke + declarative policies`

最后只回复：commit hash、测试尾行、实际改动文件、前缀分布与首
conversation 形态复算值、交替性统计数字、负空间测试函数名清单、
是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况立即停工写断点，
交回架构师裁决，不要自行发挥。

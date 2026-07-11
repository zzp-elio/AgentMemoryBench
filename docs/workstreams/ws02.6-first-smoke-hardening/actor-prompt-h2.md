# 发给 actor：HaluMem H2（声明式 smoke/resume policy）

LoCoMo、LongMemEval、MemBench、BEAM 已 `frozen-v1`，不要碰。H1 已架构师
验收通过。当前只执行 `plan-b5-halumem.md` §3 的 **H2**；完成后停下，
不要开始 H3。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b5-halumem.md`
   §2.4（smoke 口径，用户拍板）与 §3 H2
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **模式参照**：`benchmark_adapters/membench.py:91-130,365-380`
   （B3 的声明式 policy 注册与 metadata 落法）、
   `benchmark_adapters/contracts.py:62-150`
   （BenchmarkSmokePolicy/BenchmarkResumePolicy 契约）
6. 现状代码：`benchmark_adapters/halumem.py:220-260`（prepare_halumem_run）
   与 `:477-545`（`_build_halumem_smoke_dataset`，现为"每 user 前 M 个
   session"旧式裁剪，本批改造对象）
7. `docs/reference/dataset-quirks.md` HaluMem 表（含验收新发现：
   `is_generated_qa_session` 官方评测端跳过，evaluation.py:51-52）

**硬规矩**：不改 operation-level runner 交错语义、不改 prompt/metric
代码（H3/H4）、不调真实 API、不跑全量 pytest、不动 frozen benchmark、
数据只从 `data/` 读；负空间需求（该报错的必须报错）完成报告附**测试
函数名清单**；数字对不上**停工**不许凑。

## 架构师裁定（本批设计，照此实现）

**标准 smoke = 首 conversation 的最小 session 前缀，使三操作各 ≥1 次**：
① 提取探针（前缀内 ≥1 个 memory_point）；② 更新探针（≥1 个
`is_update=="True"` 且 `original_memories` 非空的 memory_point——注意
is_update 是**字符串**，quirks 有判例）；③ QA（前缀内 ≥1 题）。前缀 =
三者首次出现 session 序号的最大值。**不伪造探针、session 内不裁 turn**。

动态规则与声明式常量的关系：**运行时默认走规则**（逐 conversation 计算
最小前缀）；`HALUMEM_SMOKE_POLICY = BenchmarkSmokePolicy(history_axis=
"sessions", default_history_limit=4, default_isolation_limit=1,
default_question_limit=1)` 中的 4 是**首 conversation 在 Medium 上的
规则计算值**，由真实数据锚测试钉住（数据若变，锚测试红 → 人工复核
更新常量）。显式 `smoke_session_limit` 保留为调试旋钮（覆盖规则，
metadata 如实记录 override）；默认口径 = 规则 = 唯一认证口径
（spec §6.7）。

架构师已核基线（actor 必须独立复算，不一致停工）：Medium 20 user 的
规则前缀分布 = **前缀 4×18 user / 2×1 user / 5×1 user**；首
conversation 前缀 = 4。

## 本批做四件事

1. **改造 `_build_halumem_smoke_dataset`**：默认规则前缀（无显式 limit
   时），显式 limit 为调试 override；QA 按 `default_question_limit=1`
   只保留前缀内第一题（剔除数记 metadata）；per-conversation metadata
   记录 `smoke_prefix_rule` 三操作各自的首现 session 序号与最终前缀；
   规则在某 conversation 全 session 内都凑不齐三操作 → 该 conversation
   以全部 session 保留并 metadata 标记 `smoke_prefix_incomplete=true`
   （不报错不伪造——smoke 只看路径覆盖，首 conversation 在真实数据上
   必然凑齐）。

2. **声明式 policy 注册**（照 membench 模式）：`HALUMEM_SMOKE_POLICY` +
   `HALUMEM_RESUME_POLICY(smoke_enabled=False, ingest_checkpoint=
   "conversation", answer_checkpoint="question", reuse_saved_retrieval/
   evaluation_artifact_only 按 membench 同款值抄并核实其语义适用)`，
   `prepare_halumem_run` 把两者 `to_dict()` 落进 dataset metadata。

3. **未接线裁剪轴 fail-fast**：halumem 的 history_axis="sessions"，
   传入 `smoke_turn_limit` 等非本轴参数必须 ConfigurationError（核对
   CLI/service 的通用轴校验是否已覆盖 halumem，没接就接上）；负空间
   测试函数名入报告。

4. **测试锚**（真实数据 + 合成 fixture 双层）：
   - 真实 Medium 锚：规则计算首 conversation 前缀 == 4；20 user 分布
     == 4×18/2/5（用 `data/halumem/HaluMem-Medium.jsonl`，逐行流式，
     标 `@pytest.mark.` 按现有真实数据测试惯例）；
   - 合成 fixture：三操作分散在不同 session 时前缀取最大值；显式
     override 生效且 metadata 记录；QA 只留 1 题；
   - **`is_generated_qa_session` 锚**：合成 Long 式 fixture 中带该
     flag 的 session，adapter 保留 flag（进 session metadata，若现在
     丢弃则补上）且规则前缀计算不依赖生成 session（它们无 gold，天然
     不满足三操作）；官方跳过语义的 runner 级断言归 H5，本批只锚
     adapter 层。

自检（按实际测试文件调整并在报告给出实际命令）：

```bash
uv run pytest -q tests/ -k halumem
```

通过后本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): halumem declarative smoke prefix + resume policy`

最后只回复：commit hash、测试尾行、实际改动文件、20 user 前缀分布
复算值、负空间测试函数名清单、是否存在 plan 偏差/停工点。遇到 plan
未覆盖的情况立即停工写断点，交回架构师裁决，不要自行发挥。

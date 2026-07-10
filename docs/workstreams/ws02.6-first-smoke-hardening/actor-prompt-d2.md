# 发给 actor：MemBench D2

D1 已完成并由架构师验收（commit `a84440e` + 验收修正），不要重做。当前只
执行 `docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md` 的
**D2：时间戳修复 + 空 evidence 修复 + 声明式 smoke/resume policy**；完成后
停下，不要开始 D3。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md`
   第 1、2 节（尤其 §2.2、§2.5）和第 3 节的 D2
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. 一手事实源：
   `docs/workstreams/ws02.6-first-smoke-hardening/notes/membench-b3-audit.md`
   （D1 验收版，含时间戳格式官方根源与 0 基裁定）
6. **结构模板（照此模式做）**：`benchmark_adapters/registry.py` 里
   LONGMEMEVAL/LOCOMO 的 `*_SMOKE_POLICY`/`*_RESUME_POLICY` 与带 policy
   metadata 的 prepare 钩子；`cli/main.py` 的 `_validate_smoke_axis_args`
   各 benchmark 分支
7. 施工对象：`src/memory_benchmark/benchmark_adapters/membench.py`
   （`_MEMBENCH_TURN_TIME_RE`:498、`_target_step_ids`、
   `_build_membench_smoke_dataset`:359）、registry.py membench 注册块、
   `cli/main.py`

**硬规矩（本卡专属强调）**：任何写进代码注释/文档的外部事实（URL、行号、
官方出处）必须附"出处文件:行号"且现场核实存在；查不到就写"来源待溯"，
禁止凭记忆填。不要调用真实 API，不要运行全量 pytest/compileall，不要更新
README/roadmap/survey/frozen 文档，不要碰 prompt/metric（D3/D4）。

本批做五件事：

1. **时间戳正则修复**：`_MEMBENCH_TURN_TIME_RE` 改为接受可选冒号
   （`time:?\s*'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})'`），注释注明官方根源
   （加噪代码 `load_test_data.py:57` 的 `time{}` 格式串）；用测试锁死
   三种真实形态：带冒号、无冒号、无后缀（None）；session_time 兜底不变。
2. **空 evidence 修复**：`_target_step_ids` 接受空列表（返回空 tuple，
   不抛错）；非 list、含非 int 仍报错。断言 FirstHigh 0-10k 全量 load
   不再崩（真实数据回归：`highlevel_rec/movie` tid=25）。
3. **声明式 policy**：`MEMBENCH_SMOKE_POLICY`（history_axis 按人称——
   声明用 `rounds`，实施细则：第一人称 1 round=1 个 {user,agent} dict；
   第三人称按 2 turns 预算截断；`default_isolation_limit=1`（每源文件
   1 条 trajectory，共 4 条）、`default_question_limit=1`）+
   `MEMBENCH_RESUME_POLICY`（smoke_enabled=False、conversation(=tid) 级
   ingest checkpoint、question 级 answer checkpoint、reuse_saved_retrieval、
   evaluation_artifact_only），经带 policy metadata 的 prepare 钩子进
   dataset metadata（对齐 longmemeval 落法）。现有 per-source 遍历保留
   （这是路径覆盖的载体，plan §2.5）。
4. **命名源选择轴**：CLI `--membench-sources`，值域
   `first_high,first_low,third_high,third_low`（逗号分隔多选），只对
   membench 接线；其他 benchmark 传入 → fail-fast；membench 传
   `--turns/--sessions` 等未注册轴 → fail-fast（对齐
   `_validate_smoke_axis_args` 现有分支模式）。默认（全 4 源）是唯一
   认证口径，该轴属调试旋钮——注释写明。
5. **smoke 内部裁剪**：`_build_membench_smoke_dataset` 在 per-source
   基础上补人称内部裁剪（第一人称 1 round / 第三人称 2 turns），选择只按
   公开顺序，不读 `answer`/`ground_truth`/`target_step_id`；metadata 记录
   original/retained 规模（沿用现有字段命名风格）。

直接相关测试更新/新增后，完成只运行一次：

```bash
uv run pytest -q tests/test_membench_conversation_adapter.py \
  tests/test_benchmark_registry.py tests/test_main_cli.py \
  tests/test_prediction_cli.py
```

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): make MemBench smoke/resume a declared benchmark policy`。

最后只回复：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。
遇到 plan 未覆盖的情况立即停工写断点，交回架构师裁决，不要自行发挥。

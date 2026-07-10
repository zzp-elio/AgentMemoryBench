# 发给 actor：LongMemEval C2

C1 已完成并由架构师验收（commit `dda4487` + 架构师直修），不要重做。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md` 的
**C2：benchmark-owned smoke/resume policy**；完成后停下，不要开始 C3。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md`
   第 1、2 节和第 3 节的 C2
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. **结构模板（照此模式做）**：LoCoMo 的声明式 policy 落法——
   `src/memory_benchmark/benchmark_adapters/registry.py` 里的
   `LOCOMO_SMOKE_POLICY` / `LOCOMO_RESUME_POLICY` 及
   `_prepare_locomo_run_with_policy_metadata`
6. 施工对象：registry.py 的 `_build_longmemeval_smoke_dataset`（行 87 起，
   round 裁剪逻辑可复用）与 `_prepare_longmemeval_run`、longmemeval 注册块

不要重新扫数据（C1 的 audit 是事实源），不要启动 reviewer subagent，不要运行
全量 pytest/compileall，不要更新 README/roadmap/survey/frozen 文档，不要碰
prompt/metric/answer 配置（那些是 C3/C4），不要改其他 benchmark 的 policy，
不要调用真实 API。

本批只做四件事：

1. **声明 `LONGMEMEVAL_SMOKE_POLICY` / `LONGMEMEVAL_RESUME_POLICY`**（对齐
   LoCoMo 模式），旧 `_build_longmemeval_smoke_dataset` 的 round 裁剪迁入
   policy 路径，policy 进 run manifest 顶层（同 LoCoMo T3 架构师修正后的
   落位，不放 method manifest）。
2. **默认 smoke 口径**：第 1 个 instance（公开顺序）、第 1 个 haystack
   session 的前 1 个 round（2 turns）、该 instance 唯一的 question。
   - 选择逻辑不得读取 `answer_session_ids`/`has_answer`/`answer`；
   - 答对与否不属于 smoke 成功条件；
   - 奇数/assistant-first session 按"前 2 个 turn"预算截断即可，不强配对
     （orphan/dangling 标记由框架聚合层负责，本批不实现新标记逻辑）；
   - smoke 的 metadata 记录 original/retained 规模（沿用现有字段命名）。
3. **resume 语义**：smoke 禁 resume/retry-failed（复用现有 CLI 校验，若
   longmemeval 未接到该校验则接上）；formal 为 conversation(=instance) 级
   resume，不引入任何 turn/session 级 resume。
4. **fail-fast**：未接线的裁剪轴（如 `--sources`、membench 专用轴）对
   longmemeval 明确报 ConfigurationError（同 T3 对 LoCoMo 的做法）。

完成后只运行一次：

```bash
uv run pytest -q tests/test_longmemeval_conversation_adapter.py \
  tests/test_benchmark_registry.py tests/test_main_cli.py \
  tests/test_prediction_cli.py
```

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): make LongMemEval smoke/resume a declared benchmark policy`。

最后只回复：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。
遇到 plan 未覆盖的情况立即停工写断点，交回架构师裁决，不要自行发挥。

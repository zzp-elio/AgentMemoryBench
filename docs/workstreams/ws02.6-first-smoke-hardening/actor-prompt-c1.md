# 发给 actor：LongMemEval C1

LoCoMo 已 `frozen-v1`，不要碰。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md` 的
**C1：官方资产锁定 + 真实数据剖面**；完成后停下，不要开始 C2。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b2-longmemeval.md`
   第 1、2 节和第 3 节的 C1
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. 结构模板：`notes/locomo-source-lock.json`、`notes/locomo-b1-audit.md`
6. 施工对象：`src/memory_benchmark/benchmark_adapters/longmemeval.py`
   （metadata 做法参照 `locomo.py` 的 source identity/实际计数字段）

不要重新跑全量基线，不要启动 reviewer subagent，不要运行全量
pytest/compileall，不要更新 README/roadmap/survey/frozen 文档，不要改
registry/prompt/metric/smoke（那些是 C2-C4），不要调用真实 API。

本批只做三件事：

1. **新建 `notes/longmemeval-source-lock.json`**（结构对齐 locomo 版）：
   - 官方仓库 URL、论文信息**必须从
     `third_party/benchmarks/LongMemEval-main/README.md` 与 LICENSE 一手抄**，
     不许凭记忆填；
   - 本地快照路径、两个数据文件
     `data/longmemeval/longmemeval_s_cleaned.json` / `longmemeval_m_cleaned.json`
     的**现场重算 SHA-256** 和字节数、bundled 论文 PDF 的现场 SHA-256
     （不声称与官方发布字节一致）；
   - `_cleaned` 变体与官方发布数据（README 里的 HuggingFace/Drive 链接）的
     对应关系：只根据 README 文字一手判断；**离线查不到确切对应就在
     `verification_method` 里如实写"来源待溯"，禁止编造**。

2. **新建 `notes/longmemeval-b2-audit.md`**：两个变体的现场剖面。
   - `_m` 是 2.7GB，**必须流式扫描（ijson），禁止一次性 json.load**；
   - 每个变体记录：instance 数、session 总数、turn 总数、question_type
     分布、`_abs` abstention 题数、异常 role 序列分布（assistant-first /
     纯 assistant / 连续同 role / 连续 user）、奇数长度 session 数、
     `has_answer` 键出现次数与 True 数、turn 字段键形态清单；
   - 附上你实际使用的扫描代码块，保证数字可复算；
   - `_s` 的预期量级（架构师已扫，供自查）：500 instances / 23,867
     sessions / 246,750 turns / abstention 30 / has_answer 键 10,960 其中
     True 896。你的数字与此不一致时优先查自己的脚本，仍不一致就如实
     记录差异并停工上报，不许改数凑对。

3. **adapter dataset metadata 补 source identity + 实际计数**：
   `LongMemEvalAdapter.load_dataset` 返回的 Dataset.metadata 补充官方来源
   身份与本次加载的实际 conversation/question 计数（做法对齐 `locomo.py`
   T1 落法）；不改变公开/私有字段边界，`answer`、`answer_session_ids`、
   `has_answer` 仍绝不进入公开对象。

完成后只运行一次：

```bash
uv run pytest -q tests/test_longmemeval_conversation_adapter.py
```

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): lock LongMemEval source identity + real data audit`。

最后只回复：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。
遇到 plan 未覆盖的情况立即停工写断点，交回架构师裁决，不要自行发挥。

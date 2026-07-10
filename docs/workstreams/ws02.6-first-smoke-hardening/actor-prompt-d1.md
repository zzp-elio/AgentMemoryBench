# 发给 actor：MemBench D1

LoCoMo、LongMemEval 已 `frozen-v1`，不要碰。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md` 的
**D1：官方资产锁定 + 真实数据剖面**；完成后停下，不要开始 D2。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b3-membench.md`
   第 1、2 节和第 3 节的 D1
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. 结构模板：`notes/longmemeval-source-lock.json`、`notes/longmemeval-b2-audit.md`
   （B2 验收版式，照此做）
6. 施工对象：`src/memory_benchmark/benchmark_adapters/membench.py`
   （metadata 做法参照 `longmemeval.py` 的 source identity/实际计数落法，
   含分块流式哈希）
7. 二手剖面（**逐项复核对象，不是事实源**）：
   `data/membench/Membenchdata/data2test/数据集结构说明.md`

不要改 smoke/policy/prompt/metric（D2-D4），不要动
`_MEMBENCH_TURN_TIME_RE`（时间戳修复属 D2），不要调用真实 API，不要运行
全量 pytest/compileall，不要更新 README/roadmap/survey/frozen 文档。

本批只做三件事：

1. **新建 `notes/membench-source-lock.json`**（对齐 longmemeval 版结构）：
   - 官方仓库 URL、论文、license **从
     `third_party/benchmarks/Membench-main/README.md` 与 LICENSE（如有）
     一手抄**，不许凭记忆填；无 LICENSE 文件就如实记录；
   - `data2test/{0-10k,100k}/` 全部 8 个正式 JSON + 根目录游离文件
     `ThirdAgentDataHighLevel_multiple_100.json` 的现场 SHA-256 + 字节数；
     bundled 论文 PDF 现场哈希（不声称与 arXiv 字节一致）；
   - `data2test` 与官方仓库 `MemData/`（FirstAgent 11 文件/ThirdAgent
     8 文件）的对应关系一手判断；离线查不到确切生成关系就在
     `verification_method` 写"来源待溯"，禁止编造；本地快照无 git 身份
     同样如实记录。

2. **新建 `notes/membench-b3-audit.md`**：8 个正式文件全量剖面，**逐项复核
   `数据集结构说明.md` 的数字**（trajectory 数 700/900/400/1400/140/360/
   80/280、task_type 分布、answer str/list 两态、越界 target_step_id、
   100k 无时间后缀 noise 占比、游离文件结构），并补架构师已实锤但需全 8
   文件量化的**时间戳格式分布**（`time:'…'` 带冒号 vs `time'…'` 无冒号 vs
   无时间后缀，逐文件三列计数；已知 0-10k ThirdLow 19,285 全无冒号、
   ThirdHigh 5,302 全有冒号）。每个数字附可复算脚本。与二手文档或 plan
   不一致时如实记录差异并停工上报，不许改数凑对。

3. **adapter dataset metadata 补 source identity + 实际计数**（对齐
   longmemeval 落法：official_repo_url/paper/license/source_sha256 分块
   流式现算/实际 conversation/question 计数）；同时在
   `tests/test_membench_conversation_adapter.py` 补公私边界加固断言：
   `answer`/`ground_truth`/`target_step_id` 不出现在任何公开对象
   （`to_public_dict()` 序列化扫描）。

完成后只运行一次：

```bash
uv run pytest -q tests/test_membench_conversation_adapter.py
```

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): lock MemBench source identity + real data audit`。

最后只回复：commit hash、测试尾行、实际改动文件、是否存在 plan 偏差/停工点。
遇到 plan 未覆盖的情况立即停工写断点，交回架构师裁决，不要自行发挥。

# 发给 actor：BEAM E1

LoCoMo、LongMemEval、MemBench 已 `frozen-v1`，不要碰。当前只执行
`docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md` 的
**E1：官方资产锁定 + 真实数据剖面 + 两个强制判定**；完成后停下，不要
开始 E2。

开工只需阅读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.6-first-smoke-hardening/README.md` 当前断点
3. `docs/workstreams/ws02.6-first-smoke-hardening/plan-b4-beam.md`
   第 1、2 节和第 3 节的 E1
4. `docs/reference/actor-handbook.md`（规矩全文，必读）
5. 结构模板：`notes/membench-source-lock.json`、`notes/membench-b3-audit.md`
   （B3 验收版式）
6. 一手事实源：`third_party/benchmarks/BEAM/`（README/LICENSE/beam.pdf/
   src/）、`data/BEAM/{beam_dataset,beam_10M_dataset}/`（HuggingFace
   arrow，`datasets.load_from_disk`；**`probing_questions` 字段必须
   `ast.literal_eval`，json.loads 会炸**）
7. metadata 落法参照：`src/memory_benchmark/benchmark_adapters/
   longmemeval.py` 的 source identity 模式 + `storage/fingerprint.py`
   的目录聚合哈希

**硬规矩**：
- 外部事实（URL/license/行号）必须附"出处文件:行号"且现场核实；官方
  repo URL 从本地 README 或论文 PDF 一手取，**查不到写"来源待溯"，禁止
  编造**（B3 D1 有编造判例，验收必查）；
- 数字全部附可复算脚本；与 plan §2 或二手材料不一致时如实记录并停工，
  不许改数凑对；
- 不改 registry/policy/prompt/metric（E2-E4），不调真实 API，不跑全量
  pytest/compileall，不更新 README/roadmap/survey/frozen 文档。

本批做四件事：

1. **新建 `notes/beam-source-lock.json`**：官方 repo/论文（arXiv id）/
   LICENSE 一手抄；`data/BEAM/beam_dataset/` 与 `beam_10M_dataset/` 两个
   目录内**全部文件**（*.arrow / dataset_info.json / state.json /
   dataset_dict.json / README.md）逐文件现场 SHA-256 + 字节数；本地
   arrow 与官方 HuggingFace 发布（`Mohammadta/BEAM`，dataset README 有
   载）的对应关系离线可判部分如实写，判不了写"来源待溯"。

2. **新建 `notes/beam-e1-audit.md`**：四 split（100K/500K/1M/10M）全量
   剖面——
   - conv 数、每 conv 的 session 数 / turn 数分布、turn 字段键形态；
   - 10 类 × 每类题数（预期每 conv 每类 2 题，验证是否恒成立）、rubric
     条数分布、difficulty 值域；
   - **全 10 类的 gold/私有字段清单**（逐类列出 question 之外的所有键，
     这是 E2 私有键黑名单的依据，一个都不能漏）；
   - `source_chat_ids` 的空缺统计（abstention 是否恒无、其他类是否
     恒有）；
   - time_anchor 格式清单（chat turn 级 + user_questions 级）；
   - 10M 专项：每 plan 的 chat 规模、顶层 chat 与 plans[].chat 的关系
     **实测**（长度对比/id 重叠/内容抽样比对）；
   - 附全部扫描脚本。

3. **强制判定 Q1（10M 消费方式）**：读
   `third_party/benchmarks/BEAM/src/beam/ten_milion_pipeline.py` 与
   `src/answer_probing_questions/answer_generation.py`，一手判定官方评测
   把 10M 的哪份 chat 喂给被测系统（顶层 chat？plans 逐个顺序拼接？），
   probing_questions 是全局一份还是 per-plan；结论必须带 文件:行号
   证据链。判定不了 → 停工写断点。

4. **强制判定 Q2（evidence id 空间）**：`source_chat_ids` 的值对应 chat
   turn 的哪个字段（`id`？`index`？0/1 基？跨 session 是否唯一？）；
   全量验证 source_chat_ids ⊆ 该字段值域，反例数量与样例如实记录
   （B3 有官方 off-by-one 判例，出现类似情况不要"修数据"，记录并停工
   交架构师）。

adapter dataset metadata 补 source identity + 实际计数（大文件分块流式；
若 `tests/` 下已有 beam adapter 测试文件则更新其断言，没有则本批不新建
测试文件，metadata 改动由 E2 的测试覆盖——在报告中说明走了哪条）。

完成后只运行一次（按实际存在的 beam 测试文件调整，报告中给出实际命令）：

```bash
uv run pytest -q tests/ -k beam
```

通过后做一个本地 commit（不 push），只提交本批文件，commit message：
`feat(ws02.6): lock BEAM source identity + real data audit`。

最后只回复：commit hash、测试尾行、实际改动文件、Q1/Q2 判定结论（各一句
+ 证据 文件:行号）、是否存在 plan 偏差/停工点。遇到 plan 未覆盖的情况
立即停工写断点，交回架构师裁决，不要自行发挥。

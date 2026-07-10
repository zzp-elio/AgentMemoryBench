# LoCoMo benchmark frozen-v1

冻结日期：2026-07-10  
冻结范围：Phase 1 LoCoMo conversation-QA benchmark 侧  
状态：通过架构师验收；未调用真实 API

## 1. 冻结结论

LoCoMo 已具备可复验的官方来源身份、真实数据映射、公私边界、benchmark-owned smoke/
resume/prompt/metric 契约，以及一条 method-neutral 离线注册链路。它现在可以作为后续
Method Track 的稳定测量仪器。

本结论不表示 Mem0、MemoryOS、A-Mem、LightMem 或其他真实 method 的 LoCoMo 效果、
效率、接口保真、provenance 已通过；也不授权真实 smoke/full API 运行。

## 2. 来源锁

- 官方仓库：`https://github.com/snap-research/locomo`
- 锁定 commit：`3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`
- 本地快照：`third_party/benchmarks/locomo-main/`
- canonical dataset：`data/locomo/locomo10.json`
- dataset SHA-256：`79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`
- license：CC BY-NC 4.0
- 逐文件身份：[locomo-source-lock.json](locomo-source-lock.json)

冻结门发现 Task 1 报告中的 `static/paper/locomo.pdf` 本地路径不存在。当前实际 bundled
PDF 是
`third_party/benchmarks/locomo-main/Maharana 等 - 2024 - Evaluating Very Long-Term Conversational Memory of LLM Agents.pdf`，
现场 SHA-256 为 `218188e1d66a553afe324491e3e5e5d0af107196c9ff32c65bb3640ebf638539`。
官方 README 所链路径仍是 `static/paper/locomo.pdf`；两者不声称字节一致。

## 3. 数据与映射

现场全量扫描：10 conversations、272 sessions、5,882 turns、1,986 QA；category 分布
`{1: 282, 2: 321, 3: 96, 4: 841, 5: 446}`。Phase 1 排除 category 5，故为 1,540 题。

- hierarchy：conversation → ordered sessions → ordered single-speaker turns
- turn 无独立时间，继承 session time
- speaker 保留人名；`dia_id` 映射为 turn id/provenance key
- caption 拼入文本一次；URL 不下载、不进入文本
- answer/evidence/event summary/judge label evaluator-only
- 140 个 odd-turn sessions 必须保留；不能强配成完整 round
- `conv-26` 的 16 个 date-only keys 不构造 phantom sessions
- 4 个 empty-evidence QA 保留官方 recall 特例

## 4. Smoke 与 resume

默认 smoke：第一个 conversation、前两个连续 turns（1 round）、第一个 Phase-1 public
question。选择 question 和 method-visible metadata 都不读取 evidence；是否答对不属于
smoke 成功条件。

- smoke：禁 resume/retry-failed
- formal ingest：conversation-level resume
- completed question：跳过
- answer failure after retrieval：复用 saved retrieval，不重复状态型 retrieve
- evaluation：artifact-only，不构造 method

## 5. Answer 与 metric

Unified answer 使用官方 short-phrase QA 模板；category 2 加日期提示。LoCoMo 下所有
method 固定 `gpt-4o-mini`、role=user、temperature=0、max_tokens=32、top_p=1。

- `locomo-f1`：官方 scorer parity，Phase 1 聚合 categories 1/2/3/4
- `locomo-recall`：turn/session provenance 条件式 artifact evaluator；none/undeclared=N/A，
  声明 capability 却缺 provenance fail-fast，另报 empty/non-empty evidence 口径
- `locomo-judge`：`framework_auxiliary_lightmem_reference_v1`，不是官方主指标
- BLEU-1：不属于 LoCoMo QA，不接入

## 6. Artifact 与隐私

冻结 artifact 包含 manifest、public questions、answer prompts/retrieval trace、method
predictions、private labels、conversation/question status。answer prompt 保存实际 top-k；
method manifest 声明 provenance granularity；resume identity 同时保留历史缺字段兼容。

A6 离线链路使用真实 registry、dataset、adapter、event aggregation、unified prompt、artifact
writer、F1/recall evaluator；只在 method 算法边界使用 B0 probe、在外部 answer LLM 边界
使用固定 fake。public questions/answer prompts 通过通用私有键扫描；prediction 的
`answer` 是公开模型输出，使用只禁止 gold/evidence/judge 类键的扫描。

## 7. 实现与验收证据

Actor commits：

- `1341cb1`：source/data identity
- `edefd9a`：method-neutral benchmark probe
- `7600076`：benchmark-owned smoke/resume policy
- `3c68c5d`：minimal smoke + unified answer
- `64d2651`：conditional retrieval recall contract
- `6f0039f`：offline registered probe workflow

架构师验收：

```text
A6 exact command: 4 passed in 2.86s
LoCoMo targeted aggregate: 326 passed in 31.80s
compileall: exit 0
full regression: 890 passed, 3 deselected, 2 warnings, 4 subtests passed in 143.70s
```

首次 full regression 暴露一条 2026-06 的 MemoryOS 注册测试仍期待旧 LoCoMo method-specific
answer 参数（0.7/2000/None）。生产代码与冻结口径正确；只把该历史断言更新为
0/32/1，相关复验 `7 passed in 0.43s`，随后全量通过。

## 8. 已知限制与解冻规则

1. category 5 仍排除；恢复前需 reader-only 私有 prompt spec。
2. 真实 method 是否能返回可靠 turn/session provenance 留到 Method Track；没有时 recall=N/A。
3. 真正的 API 成本、效率观测完整性和回答效果尚未测量。
4. 本地 bundled PDF 与 README 链接路径的字节关系未确认，但不影响以 code/data 为最高
   操作事实源的 QA 契约。
5. 若官方源码/数据、prompt、metric 或公私边界有新一手证据推翻本记录，必须版本化为
   `frozen-v2`（或撤销冻结），写影响分析并重跑本页验收门；不得在 method adapter 内
   悄悄加 LoCoMo 专用补丁。


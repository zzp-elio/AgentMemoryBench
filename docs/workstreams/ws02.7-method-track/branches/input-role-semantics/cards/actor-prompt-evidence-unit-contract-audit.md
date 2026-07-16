# Actor 卡：canonical turn 与 gold evidence unit 通用契约审计

> **给当前 actor 的直接执行指令：你就是用户已选中的执行者。**本卡被发送到当前 actor
> 会话即代表用户已完成选择与授权，直接执行；不要再选择、派发或等待另一个 actor。
> 单批上限 5h；全程离线、docs-only、零真实 API、零下载、不 push。
>
> **明确允许 Fable 5 自启 subagent 分包。**subagent 可并行核不同 benchmark 的 qrel/
> source-id 语义，但不得扩大允许范围；Fable 5 必须亲自复核承重锚、整合矛盾并对最终 note
> 与回报负责，实质使用时披露分工。

## 0. 白话目标与已定边界

MemBench FirstAgent 的一个官方 step 同时含 user 和 agent 两条发言。框架目前把两条发言拼成
一个伪 user `Turn`，这已经由架构师裁定为错误；后续必须拆成两条 canonical turn。难点是
官方 `target_step_id` 指向整个 pair 级 step：拆完后，Recall 的一个 gold 单元不能被机械
翻成两个都必须命中的 turn，否则指标含义和分母都会改变。

本卡要解决的不是“要不要拆 role”——**一条 canonical `Turn` 只表示一个 speaker 的一次
utterance，这一点已经裁定，不再投票。**本卡要高判断地审计：框架应如何同时表达
canonical turn、provider provenance 与 benchmark 的 gold evidence unit，使 MemBench、BEAM、
LoCoMo、LongMemEval、HaluMem 共用一个诚实契约，并为 RetrievalEvidence M1 提供可消费的
判据。只产出证据与推荐，不改代码，也不替架构师最终拍板。

## 1. 上工、隔离与最小读序

先在主树确认状态，再建立隔离 worktree：

```bash
cd /Users/wz/Desktop/memoryBenchmark
git status --short
git worktree add -b actor/evidence-unit-contract-audit \
  /Users/wz/Desktop/mb-actor-evidence-unit-contract main
cd /Users/wz/Desktop/mb-actor-evidence-unit-contract
```

若分支或 worktree 已存在，或 main 与用户刚给你的最新提交不一致，停工回报；不要 reset、
删除或复用来源不明的现场。

按顺序只读完成任务所需集合：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点；
3. `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/README.md`；
4. `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/
   lightmem-messages-membench-beam-role-audit.md`；
5. 本卡全文；
6. `docs/reference/actor-handbook.md` §0-§4、§6-§7；
7. `src/memory_benchmark/core/entities.py`、`core/provider_protocol.py`、五 benchmark adapter、
   `runners/event_stream.py` 与相关 evaluator/runner；
8. 五 benchmark 的官方 adapter/evaluator/qrel 源码及本地真实数据 schema。`data/` 与
   `third_party/benchmarks/` 不入 git；只读可用，禁止复制私有 gold 到 note。

旧 note 与测试只作导航。每个承重结论必须回到当前源码或真实 schema 复核，不能把现有测试
当成 gold standard。

## 2. 唯一交付物与允许范围

只允许新增：

`docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/
evidence-unit-contract-audit.md`

不得修改任何 README、policy、checklist、代码、TOML、tests、third_party、data、outputs 或
既有 note。不得运行真实 API、下载模型/数据、生成付费结果或为完成审计顺手施工。

## 3. 必须先拆开的三个概念

note 开头必须分别定义，且全篇不得混用：

1. `consume_granularity`：框架把多少 canonical turns 聚合后交给 method；
2. `provenance_granularity`：method 返回的 memory 能把来源定位到多细；
3. `gold_evidence_unit`：benchmark 的一个 relevance/qrel 项究竟指 turn、pair-step、session、
   chat id、memory fact 还是 group。

要明确论证：method 消费 pair/session 不等于 gold 就是 pair/session；provider 报出参与过生成的
turn ids，也不等于当前 memory 对每个 gold fact 都语义相关。

## 4. 五 benchmark 一手资格表

逐 benchmark 给出一张表，至少回答：官方 gold 字段、它指向的原始容器、canonical 映射、
一个 gold unit 是否可能展开为多个 child turn、是否存在 any-of/group 语义、重复/缺失/模糊 id、
当前 evaluator 如何构造分母、公开 artifact 最少能保存什么且不泄漏私有答案。

必核反例：

- **MemBench**：FirstAgent `target_step_id` 对 `{user, agent}` pair；ThirdAgent string step；
  一个 pair 拆成两条 turn 后，“命中 user、assistant 或任一 child”分别会怎样改变 Recall；
- **BEAM**：`source_chat_ids` 的真实指向、assistant-only/mixed evidence、raw id 是否跨 session
  重复或需要复合 namespace；10M 连续同 role/缺 anchor 不得被 pair 假设吞掉；
- **LoCoMo**：`dia_id`、命名 speaker 与一问多 evidence 的官方 scorer 语义；
- **LongMemEval**：turn/session 证据、无目标轮次题的官方分母与框架当前差异；
- **HaluMem**：若没有 turn-level 完整 qrel，必须诚实标 N/A/undetermined，禁止从答案或私有
  evidence 反推给 method。

只可在 note 写统计量、公开字段名与脱敏/最小例子；不得粘贴私有 gold answer、judge label 或
可让 method 还原答案的 evidence 正文。

## 5. 四类候选方案的对表与推荐

至少比较以下四类，不得只描述一个喜欢的方案：

1. **gold qrel/evidence group**：一个官方 unit 映射多个 canonical child ids，按 group/any-of
   或显式 relevance rule 计一次；
2. **独立 `source_unit_id`**：provider 同时报 canonical `source_turn_ids` 与 benchmark-unit id；
3. **canonical `TurnPair` 实体**：把 pair 提升进公共数据模型；
4. **从 turn-id 前缀解析 parent step**：不新增协议，只靠命名约定回推。

每类逐项评价：五 benchmark 表达力、是否把 benchmark 知识泄入 method、对
`RetrievalResult`/`RetrievalEvidence`/artifact schema 的改动、resume/manifest version、旧产物
兼容、Recall/NDCG/Precision 的分母与 rank 语义、method adapter 是否被迫 benchmark 特判、
迁移风险与强反例。尤其要回答：gold group 是 evaluator 私有 qrel，还是 provider 可见字段；
若 provider 不应看到 gold，如何只用公开 source unit 建映射。

最终必须给出**唯一首选推荐**、不选其余方案的理由、最小协议草图与分阶段迁移顺序；但标明
这是给架构师的裁决输入，不自行更改现行协议。

## 6. 对后续施工的可执行交接

推荐方案后列出：

- 预计需要修改的生产/测试/文档文件清单（只列，不改）；
- schema/contract/version 是否必须升级，旧 artifact/resume 如何 fail-fast 或迁移；
- MemBench canonical split 最少强反例：user/assistant 分离、时间/place 原文无损、noise None、
  pair gold 分母不翻倍、ThirdAgent 不被误拆；
- BEAM 强反例：assistant-only gold、跨 session id、10M 同 role adjacency；
- RetrievalEvidence M1 应读取什么运行时事实，哪些 metric 必须 N/A/pending；
- 哪些旧测试/文档会因现行错误语义而必须更新，禁止用兼容代码保住过时断言。

## 7. 停工条件

以下任一命中就记录断点并停止对应部分，不猜：关键官方源码/真实 schema 不可得；同一官方
字段在两个一手入口含义冲突且 5h 内无法消解；结论需要真实 API/下载/泄露私有 gold；必须改
允许清单外文件才能继续；发现与“一 speaker utterance = 一 Turn”硬裁决直接冲突。可继续完成
不受影响的 benchmark，但必须把未知项标 `UNDETERMINED`，不能为了填表代裁。

## 8. 最小自检、提交与回报

只跑一次最小自检：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

随后 `git status --short` 过目，只显式 add 唯一 note，禁止 `git add -A`/`.`：

```bash
git add docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/evidence-unit-contract-audit.md
git commit -m "docs(ws02.7): audit gold evidence unit contract"
```

到此停止，不 push、不 amend、不更新状态。按 `actor-handbook.md` §4 回报 commit hash、测试尾行
原文、实际改动文件、偏差/停工点；实质使用 subagent 时补充分工与由 Fable 亲自复核的承重锚。

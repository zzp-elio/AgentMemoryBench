# Actor 返工卡：LightMem offline-update 传递血缘修复

> **状态：已执行但被后续架构裁决终止，禁止再次派发。**Sonnet 5 commit
> `3e2d957` 忠实完成本卡且定向测试通过；用户随后指出 transformation-input lineage
> 不等于更新后 memory 的 semantic evidence provenance，架构师复核成立，故该 commit
> 不合入。现行裁决见 `notes/lightmem-offline-recall-ruling.md` 顶部与 §3、§7。
>
> 派发日：2026-07-15。单批上限 5h；零真实 API；不得另开 reviewer/subagent。
> 由用户选择 Sonnet 5、GLM-5.2、MiniMax、Codex 或其他 actor 后转发。
> 架构裁决原文：`notes/lightmem-offline-recall-ruling.md`，不得自行改判。

## 0. 上工与 Git 隔离

按顺序只读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部当前断点；
3. 本卡全文；
4. `docs/reference/actor-handbook.md`；
5. `notes/lightmem-offline-recall-ruling.md` §1-§3、§7；
6. `notes/lightmem-offline-recall-validity-audit.md` §2-§3。

从届时主树 `main` 创建独立 worktree；路径或分支已存在就停工报告，不删除、不复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-lm-lineage \
  -b actor/lightmem-lineage-repair main
cd /Users/wz/Desktop/mb-actor-lm-lineage
```

允许修改：

- `third_party/methods/LightMem/src/lightmem/memory/lightmem.py`；
- `src/memory_benchmark/methods/lightmem_adapter.py`；
- `tests/test_lightmem_adapter.py`；
- 新建 `docs/workstreams/ws02.7-method-track/notes/lightmem-lineage-repair.md`。

不得修改 prompt、manager、embedding/retriever 实现、registry、evaluator、TOML、其他
测试/文档、outputs；不得 push。

## 1. 已裁定的问题

LoCoMo 官方报告路径在 insert 后执行：

```text
construct_update_queue_all_entries()
→ offline_update_all_entries()
→ post-update retrieve
```

action=`update` 会把 candidate 文本整合进 target memory，却只保留 target 的旧
`source_external_id`；当前 adapter 因而把多来源的新文本误报成单来源。修复必须补
“变换输入血缘”，不得改变算法。

血缘语义：参与生成当前 memory 的 target/candidate entries 的公开 turn ids 稳定
去重并集；不是逐 token entailment 标签。

## 2. 实现边界

### 2.1 初次 insert

在 `LightMemory.offline_update()` 构造 Qdrant payload 时：

- 既有 `source_external_id` 写入行为原样保留；
- 当它是非空字符串时，额外写
  `source_external_ids=[source_external_id]`；
- `None`/未附 id 的官方调用路径不得凭空产生 plural 字段；
- plural 字段不得进入 memory 文本、embedding 输入或任何 LLM prompt。

### 2.2 action=`update`

在 `offline_update_all_entries()` 的 update 分支，用本轮 `get_all()` 快照中实际传给
当前 update LLM 的 target + `candidate_sources` payload 构造 lineage：

1. 依次取 target，再按 `candidate_sources` 现有顺序取各自
   `source_external_ids`；
2. 稳定去重、过滤空值；
3. 非空时写回 target 新 payload 的 `source_external_ids`；
4. 保留 target 既有 singular `source_external_id`，不得改成 candidate id；
5. 继续复用官方旧 vector；不得重算 embedding；
6. 不改变 candidate selection、score threshold、LLM 调用、action、并行方式和其他
   payload 字段。

当前 target 操作不写 candidate；但 candidate 可能在另一并行任务中作为 target。
禁止写“candidate 整轮永远不变”的测试或注释。

action=`delete` 与 `ignore` 完全保持官方语义：delete 只删 target；不得把被删 target
血缘挂到其他 entry。

如需新增 helper，必须有中文 docstring；不得把项目异常类型或 benchmark 概念侵入
third_party 算法层。

### 2.3 adapter 消费

`_retrieved_items_from_lightmem_memories()` 改为只从非空、全为非空字符串的
`payload["source_external_ids"]` 生成 `RetrievedItem.source_turn_ids`，保持列表顺序。

- 不得用 singular fallback 继续声称完整 provenance：旧状态可能已经发生过 update，
  singular 无法证明完整血缘。
- 命中条目缺 plural、类型错误或含空/非字符串值时，必须 fail-fast 并在错误信息中
  明确旧状态需重新 ingest；不得返回部分 items、空 tuple 或静默 0 分。
- 空检索结果仍是合法空 tuple，不得误报旧状态。
- 保留 singular 字段只是 third_party/旧工具兼容，不是 evaluator 的权威来源。

## 3. 必测反例

在现有测试风格内至少覆盖：

1. 初次 insert：singular=`D1:1` 时 plural=`["D1:1"]`，embedding 输入不含 id；
2. 无 external id 的官方路径：singular/plural 都不新增，旧行为不变；
3. update：target `[D1:1]` + candidates `[D1:2]`、`[D1:2,D1:3]` → target plural
   稳定为 `[D1:1,D1:2,D1:3]`，旧 vector、singular、其他 payload 不变；
4. delete：仍只调用 target delete，不伪造 lineage；
5. adapter：一个 retrieved item 的 plural 多 id 原顺序进入
   `source_turn_ids`；
6. adapter：只有旧 singular、plural 缺失时 fail-fast；plural malformed 同样
   fail-fast；合法空检索不报错。

测试不得联网、不得调用真实 LLM/embedding/Qdrant 服务。可按本文件既有 fake 风格
构造 manager/retriever；不要为测试改变生产并行语义。

## 4. note 交付

`notes/lightmem-lineage-repair.md` 必须列：

- third_party 精确 diff 位置与“为何不改变算法核心”的逐项论证；
- plural schema 与 legacy fail-fast 语义；
- update/delete/ignore 三分支；
- 实际测试尾行；
- ~~仍需用户批准的真实 LoCoMo provenance smoke 门~~（二次裁决已取消，不得执行）。

不得更新 README、integration-status、frozen note；这些由架构师验收后处理。

## 5. 停工条件

- 需要把 id 放进 memory 文本、embedding、UPDATE_PROMPT 或 LLM user prompt；
- 需要重算 update 后 embedding、改变 action/阈值/候选/并行顺序；
- 无法在不触碰允许清单外文件的情况下区分旧 singular 与完整 plural 状态；
- 定向测试失败且 15 分钟无法定位；
- 需要真实 API、下载模型/数据。

命中即把已查证事实写入 note 的“停工点”，提交允许范围内的 note 后停止，不猜。

## 6. 唯一自检与停点

只跑：

```bash
uv run pytest -q tests/test_lightmem_adapter.py
```

通过后：

```bash
git diff --check
git status --short
git add \
  third_party/methods/LightMem/src/lightmem/memory/lightmem.py \
  src/memory_benchmark/methods/lightmem_adapter.py \
  tests/test_lightmem_adapter.py \
  docs/workstreams/ws02.7-method-track/notes/lightmem-lineage-repair.md
git commit -m "fix(lightmem): preserve offline update lineage"
```

到此停止，不跑全量/compileall，不更新冻结状态，不 push。按 actor-handbook §4 回报
commit、测试尾行、实际改动文件、偏差/停工点。

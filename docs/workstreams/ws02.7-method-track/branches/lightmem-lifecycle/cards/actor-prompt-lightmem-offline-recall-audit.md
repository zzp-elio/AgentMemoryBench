# Actor 卡：LightMem offline update × Recall@k 有效性纯取证

> 派发日：2026-07-15。目标是给架构师提供一手证据，不替架构师裁决。
> 单批上限 5h；零真实 API；零生产代码改动；不得另开 reviewer/subagent。

## 0. 上工与 Git 隔离

按顺序只读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部当前断点；
3. 本卡全文；
4. `docs/reference/actor-handbook.md`。

然后创建独立 worktree：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-lm-recall \
  -b actor/lightmem-offline-recall-audit main
cd /Users/wz/Desktop/mb-actor-lm-recall
```

若目标路径或分支已存在，立即停工报告，不删除、不复用。只允许新增：

`docs/workstreams/ws02.7-method-track/branches/lightmem-lifecycle/notes/
lightmem-offline-recall-validity-audit.md`

不得修改 `src/`、`tests/`、`third_party/`、现有文档或实验产物；不得 push。

## 1. 要回答的事实问题

逐条给 `文件:行号`，把“官方 LightMem”“本框架 adapter/evaluator”“MemoryData
参考框架”分开，禁止混成一个口径。

### 1.1 官方算法时序与对象变化

一手读：

- `third_party/methods/LightMem/src/lightmem/memory/lightmem.py`；
- 同目录被它实际调用的 entry/storage/retriever 实现；
- `third_party/methods/LightMem/experiments/locomo/add_locomo.py`；
- `third_party/methods/LightMem/experiments/locomo/search_locomo.py`；
- `third_party/methods/LightMem/experiments/locomo/readme.md`。

画出 LoCoMo 的实际调用序列：add/segment/extract → update queue →
`offline_update(_all_entries)` → 持久化/索引 → retrieve。明确回答：

1. offline update 的输入、候选选择与输出对象分别是什么；
2. 哪些操作会 add/update/delete/merge，旧 entry 是否保留；
3. update 前后用于 embedding retrieval 的 rank 单元是什么；
4. `source_id`、`sequence_number`、`external_id` 等来源字段在每个转换点如何变化；
5. LoCoMo 官方脚本是在 offline update 前还是后答题/检索。

不要只读函数签名；必须追到实际调用点与持久化写点。

### 1.2 本框架实际时序与 provenance

一手读：

- `src/memory_benchmark/methods/lightmem_adapter.py`；
- 当前 vendored LightMem 中与 provenance 透传有关的本项目 diff；
- `docs/workstreams/ws02.7-method-track/notes/m0-7-lightmem-provenance.md`；
- `docs/workstreams/ws02.7-method-track/notes/m0-9-provenance-breadth.md`；
- `src/memory_benchmark/evaluators/locomo_recall.py`；
- `src/memory_benchmark/evaluators/longmemeval_recall.py`；
- `src/memory_benchmark/evaluators/longmemeval_retrieval_rank.py`。

列出 adapter 从公开 turn id 到最终 `RetrievedItem.source_turn_ids` 的完整链，特别核：

- offline update 产生的新/改 entry 是否仍携带全部原来源；
- merge/delete 后一个 retrieved item 对多个来源的语义是否明确；
- `retrieved_items[:retrieval_query_top_k]` 的 top-k 单元是否与 LightMem 返回排序一致；
- 当前强校验检查的是“声明/字段存在”，还是还验证了
  `consume_granularity`、`provenance_granularity` 与 gold id 空间的语义相容性。

### 1.3 MemoryData 只作对照，不作权威

一手读主树本地只读目录（独立 worktree 可能没有该 gitignored 资产，禁止复制）：

- `/Users/wz/Desktop/memoryBenchmark/第三方框架参考/MemoryData/config/hybrid_lightmem.yaml`；
- `/Users/wz/Desktop/memoryBenchmark/第三方框架参考/MemoryData/` 下该配置实际加载的
  LightMem adapter/runtime；
- `/Users/wz/Desktop/memoryBenchmark/第三方框架参考/MemoryData/evaluation/` 下
  LoCoMo/LongMemEval recall 实现。

回答它为了 Recall@k 做了什么：走原算法最终检索、绕过更新阶段、另建 raw-turn
索引、in-band header、sidecar，还是文本/ID 后处理。指出任何会让不同 method
“被评的对象不同”的不公平点。现有二手导航
`docs/workstreams/ws02.7-method-track/notes/memorydata-recall-retrofit-survey.md`
只能帮助定位，结论必须回源码复核。

## 2. 交付格式

新增 note 必须含五节：

1. **结论摘要（只写事实，不作最终裁决）**；
2. **官方 LightMem 时序表**（阶段、输入对象、输出对象、写副作用、来源字段）；
3. **本框架 provenance/Recall@k 链表**；
4. **MemoryData 对照表**；
5. **待架构师裁决的候选风险**，至少分别列：
   - offline update 后来源合并/删除是否导致 Recall@k 失真；
   - rank 单元与 gold 单元是否可比；
   - 当前粒度强校验是必要 fail-fast、过强，还是只强在结构不强在语义。

每个风险写“支持证据 + 反证/未知”，不要替架构师写 ACCEPT/REJECT。

## 3. 停工条件

- 官方 LoCoMo 活跃脚本存在两条互斥 update 时序且无法从默认 CLI/README 判定主线；
- vendored 本项目 diff 与 note 声称的 provenance 链不一致；
- MemoryData 配置指向的实现缺失或无法定位；
- 需要真实 API、下载数据/模型或修改允许清单外文件。

观察到任一项就把已取证内容写入 note 的“停工点”，提交该 note 后停止，不猜。

## 4. 唯一自检与停点

只跑：

```bash
git diff --check
```

然后执行：

```bash
git status --short
git add docs/workstreams/ws02.7-method-track/branches/lightmem-lifecycle/notes/lightmem-offline-recall-validity-audit.md
git commit -m "docs(ws02.7): audit lightmem offline recall semantics"
```

到此停止，不更新 README/roadmap/checklist，不跑 pytest/compileall，不 push。
按 actor-handbook §4 报 commit、`git diff --check` 实际输出、改动文件、偏差/停工点。

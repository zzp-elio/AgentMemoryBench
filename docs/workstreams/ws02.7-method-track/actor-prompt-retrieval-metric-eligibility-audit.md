# Actor 取证卡：retrieval metric 资格与排序契约审计

> 派发日：2026-07-15。docs-only、零真实 API、单批上限 5h；不得另开
> reviewer/subagent。可与 Mem0 provenance 审计并行。actor 只列一手契约与候选缺口，
> 不替架构师设计最终 schema。

## 0. 上工与隔离

按顺序只读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊；
3. 本卡全文；
4. `docs/reference/actor-handbook.md` §0-§4；
5. `docs/reference/method-integration-checklist.md` B5/B5+；
6. `notes/lightmem-offline-recall-ruling.md` §1、§3、§5-§7。

从届时 `main` 新建；路径/分支已存在即停工，不删不复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-metric-eligibility \
  -b actor/retrieval-metric-eligibility-audit main
cd /Users/wz/Desktop/mb-actor-metric-eligibility
```

唯一允许改动：新建
`docs/workstreams/ws02.7-method-track/notes/retrieval-metric-eligibility-audit.md`。
禁止改 src/、tests/、third_party/、README/status/checklist、configs、outputs；不得 push。

## 1. 核心区分（已裁，不得改判）

- transformation-input lineage：哪些输入参与 summary/merge/update；只作审计。
- semantic evidence provenance：当前 retrieved item 实际仍承载哪些 source facts；
  provenance-based Recall/NDCG 只能使用这一层。
- method 官方不提供无损 output-to-source mapping 时，N/A 是正确能力声明；不得增加
  LLM 反向归因、文本 header 或 benchmark 专用旁路来点亮指标。
- `consume_granularity`、provenance resolution、retrieval item granularity 是三件事。

## 2. 必答取证

### 2.1 当前 evaluator 资格矩阵

逐个核生产注册与实现，至少覆盖：

- `locomo-recall`；
- `longmemeval-recall`；
- `longmemeval-retrieval-rank` 的 recall_any/all 与 NDCG@k；
- `membench-recall`；
- `beam-recall`；
- 代码中其他读取 `retrieved_items/source_turn_ids/retrieval_query_top_k` 的 evaluator。

每项输出一行：official/supplementary tier、gold 相关性单位、所需 provenance 语义、允许
turn/session 粒度、是否要求 item 顺序、是否读取 score、k 集合、空 evidence 规则、N/A
条件与 fail-fast 条件。官方 parity 必须给官方源码 + 本框架实现双锚。

### 2.2 NDCG/排序链

对 LongMemEval 特别回答：

- DCG 的 relevance 是 binary 还是 graded，来源是什么；
- rank 取 `retrieved_items` 原顺序、score 重排还是 source id 顺序；
- provider→artifact 序列在哪些 helper 中可能被排序/去重/截断；
- method-native answer depth 与 evaluation depth 当前如何共用 `top_k=10`；
- 官方 k=30/50 在真实 run 是否必然缺失，以及 artifact 保存 60 项能否改变这个结论。

### 2.3 capability 声明现状

从 registry→factory→runner manifest→evaluator 走完整链：

- `provenance_granularity` 当前是 method 静态、实例动态还是可按 benchmark；
- isolated workers 路径为何优先 registry 声明；
- 能否表达“LightMem 非 LoCoMo=turn、LoCoMo post-update=N/A”；
- 能否按 metric 区分 Recall valid 但 NDCG pending/N/A；
- N/A 是否有机器可读 reason，resume fingerprint 是否包含该资格。

只描述现状与缺口，不写实现。

### 2.4 候选最小 schema（供架构师裁，不得自行定案）

给 2-3 个候选，每个必须包含：表达能力、改动面、manifest/resume 影响、向后兼容、为何
不会退化成 method × benchmark 专用 runner。至少比较：

1. 静态 method 声明继续扩字段；
2. factory/实例按 benchmark 返回 capability bundle；
3. evaluator 侧独立 eligibility manifest。

状态至少能表达 `valid / n_a / pending` 与 reason；不要写代码或推荐最终赢家。

## 3. 停工条件

- 官方 LongMemEval rank/NDCG 源码缺失或与 frozen note 互相矛盾；
- 发现 private evidence 进入 method/artifact 公开层；
- 无法确定 artifact 是否保序；
- 需要改允许清单外文件或跑真实 API；
- 工作量将扩成逐一审完 10 个 method（本卡只审框架契约，不替 method 卡）。

命中即在 note 写“停工点”，提交 note 后停止。

## 4. 唯一自检与回报

```bash
git diff --check
git status --short
git add docs/workstreams/ws02.7-method-track/notes/retrieval-metric-eligibility-audit.md
git commit -m "docs(ws02.7): audit retrieval metric eligibility"
```

到此停止。按 actor-handbook §4 回报 commit、`git diff --check` 原始结果、实际改动文件、
偏差/停工点；不跑 pytest/compileall，不更新 status/checklist，不 push。

## 5. 可直接转发给 actor 的 prompt

```text
你是本批 docs-only 框架契约取证 actor。请完整执行
/Users/wz/Desktop/memoryBenchmark/docs/workstreams/ws02.7-method-track/actor-prompt-retrieval-metric-eligibility-audit.md。
严格按卡内顺序先读 AGENTS.md → ws02.7 README 顶部恢复胶囊 → 本卡全文 →
actor-handbook.md §0-§4 → method-integration-checklist.md B5/B5+ →
lightmem-offline-recall-ruling.md §1/§3/§5-§7，再新建卡内指定 worktree/branch。唯一允许
产出是 notes/retrieval-metric-eligibility-audit.md；不得改代码/测试/状态文档，不得真实
API，不得另开 subagent/reviewer，不得替架构师定最终 schema。命中停工条件就记录并
提交 note 后停止。最后只按卡 §4 回报 commit、git diff --check 原始结果、实际文件和
偏差/停工点，不 push。
```

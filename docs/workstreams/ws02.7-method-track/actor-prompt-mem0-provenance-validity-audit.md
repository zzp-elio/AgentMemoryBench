# Actor 取证卡：Mem0 ADD-only 路径与 provenance 有效性审计

> 派发日：2026-07-15。docs-only、零真实 API、单批上限 5h；不得另开
> reviewer/subagent。由用户选择 Sonnet 5、GLM-5.2、MiniMax、Codex 或其他 actor。
> 本卡只交一手证据与风险分级，最终 metric 资格由架构师裁决。

## 0. 上工与隔离

按顺序只读：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊；
3. 本卡全文；
4. `docs/reference/actor-handbook.md` §0-§4；
5. `docs/reference/integration/mem0.md` 的 B2/B5/B8；
6. `notes/mem0-frozen-v1.md` §2-§3。

从届时 `main` 新建；路径/分支已存在即停工，不删不复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-mem0-prov-audit \
  -b actor/mem0-provenance-validity-audit main
cd /Users/wz/Desktop/mb-actor-mem0-prov-audit
```

唯一允许改动：新建
`docs/workstreams/ws02.7-method-track/notes/mem0-provenance-validity-audit.md`。
禁止改 src/、tests/、third_party/、README/status/checklist、configs、outputs；不得 push。

## 1. 背景与禁止偷换

用户判断当前 Mem0 版本可能只做 ADD；架构师曾因 `rg` 看到类中存在公开
`update/delete` 方法，过早推断 add 路径会突变，随后通读当前 phased add pipeline
发现返回记录看似全为 ADD并已撤回。你的任务是完成负空间证明，不能把：

- “类提供 update/delete API”偷换成“adapter 实际调用”；
- “返回 event=ADD”偷换成“内部绝无覆盖/删除”；
- “smoke 没报错”偷换成“sidecar 与当前 memory 语义一致”。

## 2. 必答取证

### 2.1 adapter 可达调用图

从 `methods/registry.py::_build_mem0_system` 出发，逐 benchmark/track 记录：

- 实际 `Mem0Config.infer`、`session_memory_report`、`consume_granularity`、memory type；
- `TurnEvent`/`TurnPair`/`SessionBatch` 分别落到哪个 adapter helper；
- 最终只调用 `Memory.add`，还是存在 `update/delete/reset`、graph/procedural 等旁路；
- native/unified 是否复用同一 build 路径。

用“调用点 file:line + 被调定义 file:line”成对给锚；必须做负空间 `rg`，列检索词和
零命中范围，不能只写“未发现”。

### 2.2 当前 vendored `Memory.add` 全分支

通读同步生产路径，不审 async 未调用路径；至少覆盖：

- `infer=False`；
- `infer=True` 的 V3 phased batch pipeline；
- vision parse 前置；
- procedural/graph/agent-scoped 等分支是否由本项目可达；
- duplicate/hash skip、空抽取、异常降级；
- 返回 `results[*].event` 的全集；
- 是否有任何路径复用已有 memory id 并改变/删除其当前文本。

不要因为文件里存在旧/async/公开 CRUD 实现就算进 adapter 可达集合；若有版本并存，
说明当前类绑定和调用的是哪一个。

### 2.3 sidecar 语义

逐行核 `_add_with_provenance`、`_memory_ids_from_add_result` 与检索反查：

- 每个返回 event/id 如何写 sidecar；重复 id 会覆盖还是合并；
- ADD-only 成立时 source ids 是否对应生成该 memory 的本批公开 turns；
- 若任何 mutation 可达，现 sidecar 会产生假阳性/假阴性/旧映射中的哪一种；
- DELETE/skip/空 results 是否留下不可检索或孤儿映射（区分 metric 正确性与清理债）。

### 2.4 结论三选一

note 顶部必须只选一个，并给最短充分证据：

1. `ADD_ONLY_PROVEN`：当前五 benchmark + 双轨所有 adapter 可达路径只新增 immutable
   memory id，现 turn provenance 机制上成立；
2. `MUTATION_REACHABLE`：列精确路径、event/id/text 变化和受影响 metric；
3. `UNDETERMINED`：指出缺哪项一手证据，不猜。

再单列：该结论是否足以维持 Mem0 frozen-v1 B5/B11；不要裁决，只写影响候选。

## 3. note 结构

必须包含：版本/commit 身份、adapter 可达调用图、add 分支表、返回 event 表、sidecar
状态转移表、负空间搜索、三选一结论、未知项。所有外部/官方事实给 file:line；禁止真实
API、禁止用测试 fixture 代替生产源码。

## 4. 停工条件

- adapter 实际绑定的 Mem0 类/版本无法确定；
- 当前配置值无法从 registry/TOML/manifest 链闭合；
- 需要运行真实 LLM 才能判断代码控制流；
- 需要改允许清单外文件；
- 发现相互矛盾的一手实现且 15 分钟无法消解。

命中即在 note 写“停工点”，提交 note 后停止，不自行修代码。

## 5. 唯一自检与回报

```bash
git diff --check
git status --short
git add docs/workstreams/ws02.7-method-track/notes/mem0-provenance-validity-audit.md
git commit -m "docs(ws02.7): audit mem0 provenance mutation semantics"
```

到此停止。按 actor-handbook §4 回报 commit、`git diff --check` 原始结果、实际改动文件、
偏差/停工点；不跑 pytest/compileall，不更新冻结状态，不 push。

## 6. 可直接转发给 actor 的 prompt

```text
你是本批 docs-only 取证 actor。请完整执行
/Users/wz/Desktop/memoryBenchmark/docs/workstreams/ws02.7-method-track/actor-prompt-mem0-provenance-validity-audit.md。
严格按卡内顺序先读 AGENTS.md → ws02.7 README 顶部恢复胶囊 → 本卡全文 →
actor-handbook.md §0-§4 → integration/mem0.md B2/B5/B8 → mem0-frozen-v1.md §2-§3，
再新建卡内指定 worktree/branch。唯一允许产出是
notes/mem0-provenance-validity-audit.md；不得改代码/测试/状态文档，不得真实 API，
不得另开 subagent/reviewer。命中停工条件就记录并提交 note 后停止。最后只按卡 §5
回报 commit、git diff --check 原始结果、实际文件和偏差/停工点，不 push。
```

# Actor 卡：LightMem paper online-soft 主 profile

> 派发日：2026-07-15。状态：**已完成并强验收合入；禁止重复派发**。
> Actor：Claude Sonnet 5，commit `19a0934`；主线：`825132f`；架构师复跑
> `78 passed, 1 warning in 8.10s`，主树全量 `1191 passed, 3 deselected, 2 warnings,
> 4 subtests passed in 142.37s`，compileall exit 0。
> 本卡本身就是可整份复制的 prompt；单批上限 5h、零真实 API、不 push。
> 白话目标：让五个 benchmark 都停在 LightMem 论文定义的“抽取后直接入库”时点；
> LoCoMo 不再默认追加会改写/删除旧记忆的全库 consolidation，但保留显式 opt-in 补充轨。

## 0. 上工与隔离

按顺序只读以下最小集合：

1. `AGENTS.md`；
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部“Codex 恢复胶囊”；
3. 本卡全文；
4. `docs/reference/actor-handbook.md` §0-§4；
5. `docs/workstreams/ws02.7-method-track/branches/lightmem-lifecycle/notes/
   lightmem-update-lifecycle-ruling.md` §1-§5、§7；
6. `src/memory_benchmark/methods/lightmem_adapter.py` 的 `LightMemConfig`、
   `build_backend_config()`、`add()`、`end_conversation()`、
   `_run_locomo_offline_update()`；
7. `src/memory_benchmark/methods/registry.py::_build_lightmem_system`；
8. `configs/methods/lightmem.toml`。

从届时 `main` 新建；路径/分支已存在就停工，不删、不复用：

```bash
git -C /Users/wz/Desktop/memoryBenchmark worktree add \
  /Users/wz/Desktop/mb-actor-lightmem-online-soft \
  -b actor/lightmem-online-soft-profile main
cd /Users/wz/Desktop/mb-actor-lightmem-online-soft
uv sync
```

允许修改：

- `src/memory_benchmark/methods/lightmem_adapter.py`；
- `src/memory_benchmark/methods/registry.py`；
- `configs/methods/lightmem.toml`；
- `tests/test_lightmem_adapter.py`；
- `tests/test_amem_lightmem_registry.py`；
- `tests/test_method_registry.py`（仅当现有 profile/manifest 测试的真实落点在此）；
- `docs/reference/integration/lightmem.md`；
- 新建 `docs/workstreams/ws02.7-method-track/branches/lightmem-lifecycle/notes/
  lightmem-online-soft-profile-implementation.md`。

禁止修改 third_party、runner、evaluator、其他 method、ws02.7/支线 README、frozen note、
outputs；不得下载模型或调用真实 API。真实文件结构若迫使你超出允许清单，停工，不自行
扩表。

## 1. 已裁术语（不得按函数名反推）

项目的 `online_soft` 行为必须是：

```text
add_memory()
  -> upstream config.update == "offline"
  -> offline_update(memory_entries)
  -> embedding + insert only
  -> 不调用 construct_update_queue_all_entries/offline_update_all_entries
```

vendored `online_update()` 当前是 `return None`。**禁止**为了 profile 名字把 backend
config 改成 `update="online"`；这会导致 memory 不入库。真正的 offline consolidation
是 conversation 末尾另行调用 queue construction + `offline_update_all_entries()`。

## 2. 强类型 lifecycle profile

在 `LightMemConfig` 增加：

```python
lifecycle_profile: str = "online_soft"
```

只接受两个值：

- `online_soft`：五格 Phase 1 主 profile，direct insert only；
- `locomo_offline_consolidated`：仅用于以后复现 LoCoMo post-build 补充轨。

两个 TOML section（`smoke`、`official_full`）都显式写
`lifecycle_profile = "online_soft"`，不能只依赖 dataclass 默认。`to_manifest()` 已基于
`asdict()`，必须锁测试证明 lifecycle 字段进入公开 config manifest；同时把
`LIGHTMEM_ADAPTER_VERSION` 从 `conversation-qa-v1` 升为 `conversation-qa-v2`，确保旧
post-update run 不能 resume 到新 soft profile。

不要新建第三个公开 registry profile；`smoke`/`official-full` 是规模与并发 profile，
update lifecycle 是其中的显式语义字段。

## 3. 显式 benchmark identity 与执行门

给 `LightMem.__init__` 增加可选 `benchmark_name: str | None = None` 并保存；registry
factory 必须显式传 `context.benchmark_name`。这项提前完成后，后续 RetrievalEvidence M0
只复用，不再重复改构造器。

执行规则：

1. `online_soft`：legacy `add()` 与 v3 `end_conversation()` 都不得调用
   `_run_locomo_offline_update()`；LoCoMo 与其余四格一样只保留 direct insert。
2. `locomo_offline_consolidated`：仅当显式 `benchmark_name == "locomo"` 时，保持当前
   LoCoMo conversation 最后一批写完后 queue + all-entry update 各一次的行为。
3. 该补充 profile 用于非 LoCoMo、或 benchmark identity 缺失时，在发生任何全库
   mutation 前 fail-fast `ConfigurationError`；不得从数据形态、路径名或 question 字段猜。
4. HaluMem session ingest 不新增 consolidation；session report 捕获 direct insert 的
   现行语义保持不变。

可以抽一个有中文 docstring 的小 helper 统一 legacy/native 判断，避免两处条件漂移；
不得重写 LightMem 核心抽取、insert、retrieve 或 update 算法。

## 4. 必测反例

至少锁定：

1. 非法 `lifecycle_profile` 在 config 构造时 fail-fast；两个合法值通过；
2. 两种 lifecycle 构造的官方 backend config 都仍为 `update="offline"`；
3. 默认/显式 `online_soft` 的 LoCoMo legacy 路径只写 add，不出现 queue/all-entry update；
4. `online_soft` 的 LoCoMo v3 路径与 legacy 路径调用序列等价；
5. 显式 `locomo_offline_consolidated` 的两条路径仍在最后一批后各调用 queue/update 一次，
   既有 offline score threshold 不变；
6. 非 LoCoMo 或缺 benchmark identity 使用补充 profile 时在全库 mutation 前 fail-fast；
7. registry factory 把 `benchmark_name` 原样传进 LightMem；
8. `LightMemConfig.to_manifest()` 含 lifecycle，adapter version 是 v2；现有旧 manifest
   identity 测试若因此变化，更新期望但不得放宽 resume 比较；
9. HaluMem session capture、LongMemEval pair、BEAM/MemBench turn 的既有定向测试不退化。

现有测试若默认期待 LoCoMo offline update，必须把“主 profile 期望”改为 online-soft；
另用显式 `locomo_offline_consolidated` case 保住旧补充轨。不得直接删掉旧行为测试。

所有新增/修改的 Python 模块、类、函数、嵌套 helper 与测试函数都带中文 docstring。

## 5. 文档施工记录

更新 `docs/reference/integration/lightmem.md` 中把 direct insert 叫“不是 online 模式”、
“LoCoMo 主线必须 post-update”的过时段落。必须明确：

- 论文行为名与上游函数名的映射；
- 五格主 profile=`online_soft`；
- 补充 profile 的适用范围与 provenance N/A；
- 未运行任何新真实 API，不能把代码切换写成已有新实验数字。

新 note 记录最终字段名、全部改动文件、bridge/native 调用序列、测试尾行、偏差/停工点。

## 6. 明确不做

- 不实现 `RetrievalEvidence`，不改 M0 卡；
- 不改 Recall/NDCG evaluator、top_k 或 LongMemEval 分母；
- 不为 offline consolidation 修 lineage/embedding；
- 不让 offline profile 扩到 LongMemEval/BEAM/MemBench/HaluMem；
- 不跑 smoke、compileall、全量 pytest；最终强验收由架构师负责。

## 7. 停工条件

- direct insert 在当前生产路径无法与全库 consolidation 分开而必须改 third_party；
- lifecycle 字段无法进入现有 manifest/resume identity；
- registry 无法把 benchmark identity 显式传入而必须用启发式猜；
- 现有 HaluMem session capture 依赖 LoCoMo all-entry update（与当前证据矛盾）；
- 定向测试失败且 15 分钟内不能定位；
- 需要允许清单外文件才能保持既有公开行为。

命中后在 implementation note 写证据和阻断，提交当前可审材料后停止，不自行扩 scope。

## 8. 唯一自检、commit 与回报

只跑一次：

```bash
uv run pytest -q \
  tests/test_lightmem_adapter.py \
  tests/test_amem_lightmem_registry.py \
  tests/test_method_registry.py
```

若 `tests/test_method_registry.py` 实际无相关改动且未修改，可仍运行但不要为凑允许清单
触碰它。通过后：

```bash
git diff --check
git status --short
git add \
  src/memory_benchmark/methods/lightmem_adapter.py \
  src/memory_benchmark/methods/registry.py \
  configs/methods/lightmem.toml \
  tests/test_lightmem_adapter.py \
  tests/test_amem_lightmem_registry.py \
  tests/test_method_registry.py \
  docs/reference/integration/lightmem.md \
  docs/workstreams/ws02.7-method-track/branches/lightmem-lifecycle/notes/lightmem-online-soft-profile-implementation.md
git commit -m "feat(lightmem): make online soft update the main profile"
```

若允许清单内某文件未改，`git add` 必须删去该路径，禁止为了让命令成功制造空白改动；
仍只显式 add，禁 `-A`/`.`。到此停止，不 push。按 actor-handbook §4 回报 commit、测试
尾行原文、实际改动文件、偏差/停工点；若实质使用了 subagent，再用一句话说明分工。

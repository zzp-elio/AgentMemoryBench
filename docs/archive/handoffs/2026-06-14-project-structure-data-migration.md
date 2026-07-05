# Phase E 项目结构与数据入口迁移交接

更新日期：2026-06-14

## 当前状态

- 用户已确认并要求开始执行 Phase E。
- 已完成迁移方案、逐任务实施计划、迁移前离线基线和物理目录移动。
- 当前物理目录为：
  - 官方 benchmark 仓库：`third_party/benchmarks/`
  - runtime dataset：`data/`
  - 数据结构说明：`docs/dataset_structures/`
  - 测评流程说明：`docs/evaluation_workflows/`
- 本阶段只做路径和目录迁移，不改变 adapter 的数据语义，不启用新的 benchmark variant，
  不运行任何真实 API。

## 权威文档

- 设计：
  `docs/superpowers/specs/2026-06-14-project-structure-data-migration-design.md`
- 实施计划：
  `docs/superpowers/plans/2026-06-14-project-structure-data-migration.md`
- 动态路线图：`docs/current-roadmap.md`

## 已核验事实

- `data/locomo/locomo10.json` 与官方仓库副本内容一致。
- LongMemEval S/M 两个 JSON 与官方仓库副本内容一致。
- HaluMem Medium/Long 两个 JSONL 与官方仓库副本内容一致。
- Mem-Gallery 的 1511 个数据文件和 4 个 prompt 与官方仓库副本内容一致。
- `data/membench/` 当前为空，Phase E 只保留语义目录，不补造数据。

## 受保护资产

不得删除、覆盖或修改：

```text
outputs/memoryos-locomo-full-20260603/
```

迁移前已知聚合 SHA-256：

```text
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

## 迁移前验证基线

2026-06-14 实际执行结果：

```text
uv run pytest -q
386 passed, 3 deselected, 6 subtests passed in 29.10s

uv run pytest -m api --collect-only -q
3/389 tests collected (386 deselected)

uv run python -m compileall -q src/memory_benchmark tests
exit 0

受保护实验聚合 SHA-256
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

以上命令没有执行真实 API。

## 精确断点

实施计划 Task 1-10 已完成，Phase E 已关闭：

- Task 2 RED：`4 failed, 28 passed`，失败只来自新路径尚未实现。
- 扩展全部直接 PathSettings 测试后的 RED：`5 failed, 124 passed, 2 subtests passed`。
- Task 3 GREEN：`129 passed, 2 subtests passed`。
- 旧 `benchmarks_root` 字段已删除；新增 `data_root` 和
  `third_party_benchmarks_root`。
- runtime data 迁移前清单共 1520 个文件；清单 SHA-256 为
  `44c7b3586fad1d23ae60433056c0568693671ea26cb12a803ac4eab2a1bd6fd9`。
- runtime data 迁移后仍为 1520 个文件；按文件内容哈希排序后的 multiset digest
  迁移前后均为
  `a749b323ccba039de1cfbbd6f266b7edf29a2eb3ca6bed2b3d431a121c85f38e`。
- canonical runtime 目录现为：
  `data/halumem/`、`data/locomo/`、`data/longmemeval/`、
  `data/mem_gallery/`、`data/membench/`。
- macOS 当前文件系统大小写不敏感，`test ! -e data/HaluMem` 会把现有
  `data/halumem` 视为同一路径；实际目录项已通过 `Path.iterdir()` 确认为小写
  `halumem`，不要把该 shell 检查的非零结果误判为旧目录残留。
- 五个官方仓库已整体迁入 `third_party/benchmarks/`，仓库内部未修改。
- 受保护实验迁移后聚合哈希仍为
  `2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f`。
- LoCoMo/LongMemEval adapter、registry、legacy MemoryOS runner 和 CLI 已切换到
  canonical `data/` 路径；Task 7 focused suite 为 `60 passed`。
- synthetic 测试 fixture 已从误导性的 `benchmarks/fake` 改为 `sources/fake`；
  对应测试与文档规范组合验证为 `41 passed, 4 subtests passed`。
- 新增 `tests/test_canonical_dataset_sources.py`，核心文本数据和 Mem-Gallery 三棵目录树
  的真实性验证为 `8 passed`。
- README、`docs/architecture.md`、`docs/benchmark-scope.md`、`AGENTS.md` 和动态路线图
  已更新到新目录导航。

## 最终验收

Task 10 已取得的实际验证证据：

```text
uv run pytest -q
396 passed, 3 deselected, 6 subtests passed in 41.58s

uv run pytest -m api --collect-only -q
3/399 tests collected (396 deselected)

uv run pytest tests/test_documentation_standards.py -q
5 passed

uv run pytest -m memoryos -q
168 passed, 230 deselected, 2 subtests passed

uv run python -m compileall -q src/memory_benchmark tests
exit 0

受保护实验聚合 SHA-256
2bf09d4109396feb7af4eb174d21bff791afc1c03b5a8ba62180da1315df642f
```

loader-only dry-run 已从新路径成功读取：

- LoCoMo：1 conversation、19 sessions、419 turns、152 questions。
- LongMemEval：1 conversation、53 sessions、550 turns、1 question。

活跃第一方源码、测试和当前文档的旧根路径扫描无匹配；canonical 数据真实性测试中
指向 `third_party/benchmarks/` 的官方路径是有意保留。

阶段级 reviewer 首轮发现并已修复：

- Phase E spec 中两个迁移前 runtime 路径。
- `docs/dataset_structures/locomo.md` 中旧 LoCoMo 路径。
- canonical 测试缺少 `data/membench/` 存在且为空的契约。

Membench 空目录测试使用临时 sentinel 验证过 RED，清理后 canonical suite 为
`9 passed`。同一 reviewer 复审后明确 `APPROVED`，无剩余发现。

## 下一步

主线切换到 Phase F：Dataset Variant + LongMemEval 闭环。开始代码前先编写独立
spec 和实施计划；不得直接跳入实现或启动真实 API。

本轮使用两个 Codex subagent：

- `gpt-5.4-mini medium`：只更新 README 和两个当前架构文档，主线程复核后通过。
- `gpt-5.4-mini high`：只新增 canonical 数据真实性测试，主线程重跑为 `8 passed`。

## 强约束

- 不调用付费 API，不读取或打印 `.env` secret。
- 不修改第三方仓库内部文件。
- `benchmarks/` 只能在计划对应步骤整体移动到 `third_party/benchmarks/`。
- runtime adapter 最终只能从 `data/` 读取数据。
- 迁移前后必须使用内容哈希验证 canonical dataset 和受保护实验。
- 每完成一个 Task，立即更新实施计划、`docs/current-roadmap.md`、`AGENTS.md` 和本 handoff。

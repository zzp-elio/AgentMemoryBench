---
id: ws02
doc: plan (Track 0 收尾：vendor 裁剪评估)
status: approved
created: 2026-07-07
---
# ws02 Track 0 收尾：third_party 全仓 vendor 裁剪评估

执行者：Codex。目的：回答 ws02 Track 0 最后一个未勾选项——"third_party 全仓
vendor 是否改为裁剪式引入"。**本 plan 是纯调研，不移动/删除任何文件**，产出
一张决策卡片供架构师与用户裁定。

## 施工纪律

1. 零真实 API；不修改 `third_party/` 与主环境依赖；结论必须带
   `文件:行号` 或实测命令输出证据。
2. 唯一产出：`docs/workstreams/ws02-phase1-matrix/audits/vendor-trim-evaluation.md`
   + 更新 ws02 README 断点。完成后一次 commit
   （`docs: add vendor trim evaluation card`）。

## 调研问题（卡片按此分节）

1. **实际 import 面**：对已 git 跟踪的 4 个 vendored method
   （A-mem、LightMem、MemoryOS-main、mem0-main），用 grep 统计
   `src/memory_benchmark/` 与 `tests/` 实际 import/引用了哪些子路径
   （含 source identity fingerprint 引用的文件清单：查
   `methods/registry.py` 与各 adapter 的 source_identity 配置）；
   给出"每仓库被引用文件数 / 仓库总文件数"对比表。
2. **体积画像**：4 个已跟踪仓库在 git 中的体积占比（`git count-objects`
   或按目录 `du -sh` + `git ls-files | wc -l`）；6 个 local-only 仓库维持
   MANIFEST 管理不变，仅列现状。
3. **参考做法**：MemoryData（`第三方框架参考/MemoryData/methods/*/source/`）
   与 EverOS/memorybench 分别怎么引入第三方（全仓 vendor / pip / HTTP API），
   各自代价一小段。
4. **裁剪风险清单**：若只保留被 import 的子树，哪些东西会丢
   （官方 eval 脚本作为 prompt/参数事实源、论文 PDF、requirements、
   未来扩展 benchmark 时要用的其他 experiments 目录）；source identity
   fingerprint 是否会因裁剪而变化（这会作废 resume 兼容性——重点核实）。
5. **方案建议**：A 维持现状 / B 裁剪已跟踪 4 仓 / C 全部转 MANIFEST+脚本。
   给出推荐与理由，**不执行**。

## 验收

- 卡片五节齐全，import 面表格有实测命令输出佐证；
- `git status --short` 除新卡片与 README 外无其他变更；
- `uv run pytest -q` 不需运行（无代码改动），但 `git diff --check` 通过。

## 明确不做

不移动/删除任何 third_party 文件；不改 .gitignore；不改 fingerprint 逻辑。

---
id: ws01
doc: plan
status: approved
created: 2026-07-05
---
# ws01 实施计划：M1 git 收干净 + M2 目录迁移 + M3 入口重写

执行者：Codex（M1、M2 全部；M3 仅机械操作，内容由 Claude 起草）。
设计依据：[spec.md](spec.md)。用户已于 2026-07-05 批准 spec 与三项决策。

## 施工纪律（先读）

1. 逐 task 顺序执行，每个 task 完成后立即勾选本文件对应项，并把验收命令的
   **实际输出**（passed 数、行数等）追记在该 task 末尾。
2. 所有已跟踪文件的移动必须用 `git mv`，保留历史。未跟踪的新文件直接 `mv`。
3. 遇到 plan 未覆盖的情况（文件缺失、冲突、意料外引用），**停止当前 task**，
   把情况写入 [README.md](README.md) 的"当前断点"，等架构师处理，不自行发散。
4. 不修改 `src/`、`tests/` 下任何代码内容（M2-T4 中允许的纯文本路径替换除外，
   本 plan 已确认 src/tests 无旧 docs 路径引用，正常情况下无需改动）。
5. 不触碰 `outputs/`、`data/`、`models/`、`third_party/benchmarks/`、
   `docs/调研资料/.obsidian/`。
6. commit message 遵循现有风格（`docs:` / `chore:` 前缀，一行英文），
   不使用 `git commit -a`，逐路径 `git add`。

## M0 基线记录

### T0 记录迁移前基线

- [x] 运行并记录：
  ```bash
  uv run pytest -q 2>&1 | tail -3          # 记录 passed/deselected 数（预期 ≈669 passed）
  git status --short | wc -l               # 记录脏条目数
  git log --oneline | head -1              # 记录起始 commit
  ```
- 验收：三个数字已追记到本 task 下方。后续所有 task 的 pytest 结果必须与基线一致。

实际输出（2026-07-05，Codex T0）：

```text
$ uv run pytest -q 2>&1 | tail -3
=========================== short test summary info ============================
FAILED tests/test_canonical_dataset_sources.py::test_membench_placeholder_directory_exists_and_is_empty
1 failed, 708 passed, 3 deselected, 2 warnings, 6 subtests passed in 98.49s (0:01:38)

$ git status --short | wc -l
      32

$ git log --oneline | head -1
47ec538 feat: add clean retry hooks for built-in methods
```

断点：T0 pytest 基线未全绿，失败原因为 `data/membench` 下存在
`Membenchdata/`，而测试仍要求 `data/membench` 为空占位；`data/` 属于施工纪律禁止触碰
范围，当前 task 停止等待架构师处理。

**架构师裁定（2026-07-05，Claude）**：该测试把"MemBench 数据尚未收集"的临时状态
固化成了空目录断言，属于测试过时，数据落位本身合法（MemBench 是 Phase 1 锁定
benchmark）。已由架构师直接修改
`tests/test_canonical_dataset_sources.py`：测试更名为
`test_membench_semantic_directory_exists`，只保留目录存在断言，docstring 注明
canonical 结构核验留给 MemBench adapter 接入任务。修复后复跑：
`tests/test_canonical_dataset_sources.py` 为 `9 passed`；完整
`uv run pytest -q` 为 `709 passed, 3 deselected, 2 warnings, 6 subtests passed`。

**正式基线由此更新为 709 passed。** Codex 恢复施工时：

- [x] T0.5 先单独提交测试修复：`git add tests/test_canonical_dataset_sources.py`
  → `fix: allow membench data directory to hold landed dataset`
- 然后按原顺序从 T1 继续；T6/T9 验收中的"与基线一致"以 709 passed 为准。

T0.5 实际输出（2026-07-05，Codex）：

```text
$ uv run pytest tests/test_canonical_dataset_sources.py -q
.........                                                                [100%]
9 passed in 5.09s

$ git commit -m "fix: allow membench data directory to hold landed dataset"
[main 73a8064] fix: allow membench data directory to hold landed dataset
 1 file changed, 9 insertions(+), 6 deletions(-)
```

## M1 git 收干净（6 个 commit，顺序固定）

### T1 vendored methods 管理策略落地（commit 1）

- [x] `.gitignore` 的 vendored 段追加 6 行（放在现有 methods 忽略规则附近）：
  `third_party/methods/MemOS/`、`third_party/methods/SimpleMem/`、
  `third_party/methods/cognee/`、`third_party/methods/langmem/`、
  `third_party/methods/letta/`、`third_party/methods/supermemory/`；
  另在 OS/editor 段追加 `**/.obsidian/`。
- [x] 新建 `third_party/methods/MANIFEST.md`：10 个 method 一张表，列
  `目录名 | upstream URL | 版本锚点 | 管理方式`。6 个新仓库的 URL 和 hash 用
  `git -C third_party/methods/<dir> remote get-url origin` 和 `rev-parse HEAD` 读取
  （已确认 6 个都有本地 .git：MemOS b051e638、SimpleMem 60a48e8、cognee f7e2267cf、
  langmem c01e273、letta b76da9092、supermemory acd2fea9，写入完整 hash）；
  已跟踪的 4 个（A-mem、LightMem、MemoryOS-main、mem0-main）管理方式写
  `git-tracked（随本仓库提交）`，版本锚点写"以本仓库提交历史为准"。
- [x] 新建 `scripts/fetch_third_party_methods.sh`：对 6 个 local-only 仓库
  `git clone <url> && git -C <dir> checkout <hash>`；目录已存在时跳过并提示。
  脚本头部加中文用途注释。
- [x] 提交：`git add .gitignore third_party/methods/MANIFEST.md scripts/fetch_third_party_methods.sh`
  → `chore: manage heavy vendored methods via manifest`
- 验收：`git status --short | grep third_party` 输出为空；
  `bash -n scripts/fetch_third_party_methods.sh` exit 0。

T1 实际输出（2026-07-05，Codex）：

```text
$ git commit -m "chore: manage heavy vendored methods via manifest"
[main 1d9b76e] chore: manage heavy vendored methods via manifest
 3 files changed, 51 insertions(+), 1 deletion(-)
 create mode 100644 scripts/fetch_third_party_methods.sh
 create mode 100644 third_party/methods/MANIFEST.md

$ git status --short | grep third_party || true

$ bash -n scripts/fetch_third_party_methods.sh; printf 'exit %s\n' $?
exit 0
```

### T2 opencode 归档目录规范化（commit 2）

- [x] `mv opencode/旧文档 opencode/archive`。
- [x] `grep -n "旧文档" opencode/*.md`，把 `opencode_result.md` 等索引中的
  `旧文档/` 引用改为 `archive/`。
- [x] 提交：`git add -A opencode/` → `docs: archive dated opencode records`
- 验收：`grep -rn "旧文档" opencode/` 输出为空；git status 中 opencode 相关
  D/?? 条目全部消失。

T2 实际输出（2026-07-05，Codex）：

```text
$ git commit -m "docs: archive dated opencode records"
[main 3426e7f] docs: archive dated opencode records
 15 files changed, 16 insertions(+), 14 deletions(-)

$ grep -rn "旧文档" opencode/ || true

$ git status --short | grep opencode || true
```

### T3 状态文档与已删文档同步（commit 3）

- [x] 提交现有修改与删除（内容不动，只提交）：
  `git add AGENTS.md README.md docs/current-roadmap.md docs/task-ledger.md`
  `git add docs/claude-code-agent.md`（确认其为 D 状态）
  → `docs: sync status docs and retire claude-code-agent notes`
- 验收：`git status --short | grep -E "AGENTS|README.md|roadmap|ledger|claude-code"` 为空。

T3 实际输出（2026-07-05，Codex）：

```text
$ git commit -m "docs: sync status docs and retire claude-code-agent notes"
[main 566e913] docs: sync status docs and retire claude-code-agent notes
 5 files changed, 213 insertions(+), 106 deletions(-)
 delete mode 100644 docs/claude-code-agent.md

$ git status --short | grep -E "AGENTS|README.md|roadmap|ledger|claude-code" || true
```

### T4 调研文档入库（commit 4）

- [x] `git add docs/benchmark-survey/ docs/architecture-execution-flow.md`
- [x] `git add docs/调研资料/`（.obsidian 已被 T1 的 gitignore 排除，确认
  `git status --ignored docs/调研资料/ | grep obsidian` 显示 ignored）
- [x] 提交 → `docs: add benchmark survey cards and research notes`
- 验收：git status 中 docs/ 相关 ?? 条目仅剩 workstreams/（留给 T6）。

T4 实际输出（2026-07-05，Codex）：

```text
$ git status --ignored docs/调研资料/ | grep obsidian || true
	"docs/\350\260\203\347\240\224\350\265\204\346\226\231/.obsidian/"

$ git commit -m "docs: add benchmark survey cards and research notes"
[main db1f686] docs: add benchmark survey cards and research notes
 14 files changed, 7389 insertions(+)

$ git status --short docs | grep '^??' || true
?? docs/workstreams/
```

### T5 reports 规范化（commit 5）

- [x] `mkdir -p reports/assets`，
  `mv "reports/ChatGPT Image 2026年6月25日 00_21_08.png" reports/assets/2026-06-25-framework-architecture.png`
- [x] `grep -rn "ChatGPT Image" reports/` 若 briefing 引用了该图，同步改路径。
- [x] 提交：`git add -A reports/` → `docs: add teacher progress briefing`
- 验收：`git status --short | grep reports` 为空；reports/ 下无含空格/中文的文件名。

T5 实际输出（2026-07-05，Codex）：

```text
$ grep -rn "ChatGPT Image" reports/ || true

$ git commit -m "docs: add teacher progress briefing"
[main 41a363b] docs: add teacher progress briefing
 4 files changed, 724 insertions(+), 340 deletions(-)

$ git status --short | grep reports || true

$ find reports -type f | LC_ALL=C grep -E '[^ -~]| ' || true
```

### T6 ws01 workstream 入库（commit 6）

- [x] `git add docs/workstreams/` → `docs: bootstrap ws01 docs-governance workstream`
- 验收：`git status --short` **完全为空**；`uv run pytest -q` 与 T0 基线一致。

T6 实际输出（2026-07-05，Codex）：

```text
$ git commit -m "docs: bootstrap ws01 docs-governance workstream"
[main 6fa87a4] docs: bootstrap ws01 docs-governance workstream
 3 files changed, 632 insertions(+)
 create mode 100644 docs/workstreams/ws01-docs-governance/README.md
 create mode 100644 docs/workstreams/ws01-docs-governance/plan.md
 create mode 100644 docs/workstreams/ws01-docs-governance/spec.md

$ git status --short

$ uv run pytest -q
709 passed, 3 deselected, 2 warnings, 6 subtests passed in 99.57s (0:01:39)
```

## M2 目录迁移（3 个 commit，全部 git mv）

### T7 归档过程文档（commit 7）

**架构师勘误（2026-07-05，Claude）**：plan 初稿中的 60/22/24 是盘点时的目测估数，
未经命令清点，属架构师失误；Codex T7 预检数字正确。经复核，正确数量为：
handoffs = **72**、plans = **21**、specs = **23**（其中 2 份留用 ws03，归档 21）、
opencode-suggestions = 3。下方步骤与验收数字已按此修正。通用原则：迁移类验收
以"源目录清空 + 目标目录数量等于迁移前 `ls | wc -l` 实测值"为准，plan 中的
绝对数字仅作参考，与实测冲突时以实测为准并在 task 下追记。

- [x] 建目录：`docs/archive/{specs,plans,handoffs,opencode-suggestions,logs,status,reference}`
- [x] `git mv docs/handoffs/*.md docs/archive/handoffs/`（72 份，全部）
- [x] `git mv docs/superpowers/plans/*.md docs/archive/plans/`（21 份，全部）
- [x] `git mv docs/superpowers/specs/*.md docs/archive/specs/`，**除以下 2 份**：
  - `2026-06-21-registry-capability-simplification-design.md`
  - `2026-06-21-llm-provider-config-design.md`
  这 2 份 `git mv` 到新建的 `docs/workstreams/ws03-architecture-slimming/`
  （对应任务仍 open，M3 会为 ws03 补 README）。
- [x] `git mv docs/opencode-suggestions/* docs/archive/opencode-suggestions/`
- [x] `git mv docs/logs/README.md docs/archive/logs/README.md`
- [x] `git mv docs/method-interface.md docs/archive/reference/method-interface.md`
  （内容描述旧 BaseMemorySystem 协议，已被 retrieve-first 取代；现行事实源是
  method-interface-inventory.md）
- [x] 删除空目录 `docs/superpowers/ docs/handoffs/ docs/opencode-suggestions/ docs/logs/`
- [x] 新建 `docs/archive/README.md`（≤15 行）：说明本目录为只读历史档案，
  文内相对链接可能失效，状态裁定以各 workstream README 为准。
- [x] 提交 → `docs: archive completed specs, plans and handoffs`
- 验收：`ls docs/handoffs docs/superpowers 2>&1` 均报 No such file；
  `ls docs/archive/handoffs | wc -l` = 72；`ls docs/archive/plans | wc -l` = 21；
  `ls docs/archive/specs | wc -l` = 21（23 − 2 份留用）；
  `ls docs/archive/opencode-suggestions | wc -l` = 3。

T7 实际输出（2026-07-05，Codex）：

```text
$ printf 'handoffs '; ls docs/handoffs/*.md | wc -l
handoffs       72
$ printf 'plans '; ls docs/superpowers/plans/*.md | wc -l
plans       21
$ printf 'specs '; ls docs/superpowers/specs/*.md | wc -l
specs       23
$ printf 'opencode-suggestions '; find docs/opencode-suggestions -mindepth 1 -maxdepth 1 | wc -l
opencode-suggestions        3

$ git mv docs/logs/README.md docs/archive/logs/README.md
fatal: not under version control, source=docs/logs/README.md, destination=docs/archive/logs/README.md

$ mv docs/logs/README.md docs/archive/logs/README.md

$ ls docs/handoffs docs/superpowers 2>&1 || true
ls: docs/handoffs: No such file or directory
ls: docs/superpowers: No such file or directory

$ printf 'handoffs '; ls docs/archive/handoffs | wc -l
handoffs       72
$ printf 'plans '; ls docs/archive/plans | wc -l
plans       21
$ printf 'specs '; ls docs/archive/specs | wc -l
specs       21
$ printf 'opencode-suggestions '; ls docs/archive/opencode-suggestions | wc -l
opencode-suggestions        3
$ printf 'archive-readme-lines '; wc -l < docs/archive/README.md
archive-readme-lines        9
$ printf 'ws03 '; ls docs/workstreams/ws03-architecture-slimming | wc -l
ws03        2
```

### T8 reference 与 survey 分区（commit 8）

- [ ] 建 `docs/reference/`，`git mv` 以下 10 份进入：
  architecture.md、architecture-execution-flow.md、benchmark-scope.md、
  data-model.md、method-interface-inventory.md、method-resource-parameter-audit.md、
  custom-method-onboarding.md、huggingface-datasets.md、subagent-strategy.md、
  future-ideas.md
- [ ] 建 `docs/survey/`：
  `git mv docs/benchmark-survey docs/survey/benchmarks`
  `git mv docs/dataset_structures docs/survey/datasets`
  `git mv docs/evaluation_workflows docs/survey/workflows`
- [ ] 提交 → `docs: split reference and survey doc sections`
- 验收：`ls docs/` 仅含：README.md（M3 建，此时可无）、current-roadmap.md、
  task-ledger.md、reference/、survey/、workstreams/、archive/、调研资料/。

### T9 修复存活文档中的旧路径（commit 9）

- [ ] 在 **archive/ 与 调研资料/ 之外** 的全部文件中查找旧路径并改为新路径：
  ```bash
  grep -rn --include="*.md" -e "docs/superpowers" -e "docs/handoffs" \
    -e "docs/benchmark-survey" -e "docs/dataset_structures" \
    -e "docs/evaluation_workflows" -e "docs/opencode-suggestions" \
    -e "docs/method-interface.md" \
    . --exclude-dir=archive --exclude-dir=调研资料 --exclude-dir=third_party \
    --exclude-dir=outputs --exclude-dir=.venv --exclude-dir=old \
    --exclude-dir=paper-make --exclude-dir=tmp
  ```
  需要改的典型文件：README.md、CLAUDE.md、docs/current-roadmap.md、
  docs/task-ledger.md、docs/reference/ 与 docs/survey/ 内部互链、
  opencode/ 索引、docs/workstreams/ws01-docs-governance/spec.md。
  替换规则：superpowers/specs 与 plans 指向 archive/specs、archive/plans
  （留用的 2 份指向 ws03）；handoffs → archive/handoffs；其余按 T8 新位置。
- [ ] 提交 → `docs: update links to restructured doc paths`
- 验收：上述 grep 命令输出为空；`uv run pytest -q` 与基线一致；
  `uv run python -m compileall -q src/memory_benchmark tests` exit 0。

## M3 入口重写（Claude 起草内容，Codex 执行与校验）

### T10 新入口文档落位（Claude 提供文本后执行）

- [ ] 等待 Claude 提交以下文件内容（Codex 不自拟）：
  新 `AGENTS.md`（≤100 行）、`docs/README.md`、`docs/roadmap.md`、
  seed workstream README（ws02-phase1-matrix、ws03-architecture-slimming、
  ws04-terminal-observability、ws05-experiment-reporting、ws06-tests-restructure）。
- [ ] 归档旧状态文档：
  `git mv docs/current-roadmap.md docs/archive/status/2026-07-04-current-roadmap.md`
  `git mv docs/task-ledger.md docs/archive/status/2026-07-04-task-ledger.md`
  旧 AGENTS.md 全文另存 `docs/archive/status/2026-07-04-agents-log.md` 后，
  工作区 AGENTS.md 替换为新文本。
- [ ] 更新 CLAUDE.md 中涉及的路径表述（Claude 提供 diff）。
- [ ] 提交 → `docs: rewrite entry docs around workstream model`
- 验收：`wc -l AGENTS.md` ≤100；
  `cat AGENTS.md docs/README.md docs/roadmap.md | wc -l` ≤300；
  三个入口互链与 workstream 链接全部可解析（逐一 `test -f` 校验）；
  `uv run pytest -q` 与基线一致；`git status` 干净。

### T11 收尾

- [ ] 更新本 README 任务清单与"当前断点"，通知架构师进行 spec §8 终验。
- [ ] 架构师终验通过后，由用户决定是否 push。

## 明确不做（防发散）

- 不重组 tests/（ws06 另立）。
- 不合并/改写任何归档文档的内容。
- 不动 docs/调研资料/ 的文件名与内部结构。
- 不删除 legacy CLI、旧协议兼容代码（属 ws03 范围）。
- 不执行任何真实 API 调用。

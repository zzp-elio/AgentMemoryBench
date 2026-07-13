# Actor 卡 M0-1c：track-aware run 路径层（`.../{mode}/{track}/{run_id}`）

> 派发日 2026-07-13。自包含卡：读完本卡即可施工，不需要读会话历史。
> 遵守 `AGENTS.md` 全部硬规则；本卡只允许离线工作，**禁止调用任何真实 API**。

## 0. Git 纪律（先读，违反即停工）

- 你在**独立 worktree + 独立分支 `actor/m0-1c-track-paths`** 上工作（用户已建好）。
- 只 commit 到本分支；**禁止 push、禁止 merge/rebase main、禁止碰其他分支/worktree**。
- 首次开工先 `uv sync`（worktree 有独立 .venv）。
- 收尾交付：分支上的 commit 序列 + 本卡末尾"施工报告"节（写在你的分支里）。

## 1. 背景与目标

双轨政策（`docs/reference/dual-track-config-policy.md` §8）要求 track 从一开始进
命名空间：`{method}/{benchmark}/{mode}/{track}/{run_id}`，两轨产物物理隔离、可分别
resume。M0-1b 已落 `--config-track`（CLI）与运行时机制；**本卡补路径层**。

现状（一手锚）：
- predict 侧 run 目录构造：`cli/run_prediction.py:1289` `_resolve_child_output_root`
  → `outputs/runs/{method}/{benchmark}[/{variant}]/{mode}`，`RunContext.run_dir` =
  该目录 `/ run_id`（:1299-1302 docstring）。
- evaluate 侧解析：`cli/commands.py:263-299` `_resolve_run_dir`——legacy flat
  `outputs/{run_id}` + CLI v2 `outputs/runs/**/manifest.json` glob（parent.name==run_id），
  多命中已有 ambiguity 报错（:289-299）。
- config_track 值来源：`cli/main.py:188-192`（`--config-track`，默认 unified）。

## 2. 要求（架构师已裁决，不要重新设计）

1. **新布局**：`outputs/runs/{method}/{benchmark}[/{variant}]/{mode}/{track}/{run_id}`，
   `track ∈ {unified, native}`，取值 = 本次 run 的 config_track。**unified 也带 track 段**
   （新 run 一律有，不做"unified 省略"的特殊分支）。
2. **不迁移旧目录**。旧布局 run 保持原地：
   - evaluate：`**` glob 天然兼容任意深度——用测试**证明**旧/新两布局都能被
     `_resolve_run_dir` 找到；同 run_id 同时存在于旧+新布局 → 必须落进现有
     ambiguity 报错路径（加测试钉死）。
   - resume：新代码只在**新布局**路径下找 checkpoint；旧布局 run 不再可 resume
     ——在 `_resolve_child_output_root` docstring 里写明这一条，并加一个测试断言
     "旧布局目录存在时，新 predict 不会误认/误续它"。
3. **manifest 字节纪律不变**：unified 轨 manifest **不得**新增 config_track 键
   （M0-1b 的字节零回归约束）；native manifest 已带 config_track，维持。
   路径变化不进 manifest 内容。
4. 效率产物、logs/method.log、checkpoint 等全部随 run_dir 走，不需要逐个改——
   但要有一个端到端离线测试证明新布局下 predict(离线 probe method)→evaluate(f1)
   全链路通。
5. 禁改 third_party；禁删既有断言；禁 skip/xfail。

## 3. 交付物

- 代码：`_resolve_child_output_root` 加 track 段（含 variant 情形）；涉及的类型/
  调用点同步。
- 测试：① 新布局路径构造（unified/native × 有无 variant）；② evaluate 旧/新布局
  各自可解析；③ 旧+新同 run_id ambiguity 报错；④ 新布局离线 e2e（predict→evaluate）；
  ⑤ resume 在新布局下的 roundtrip（模式照抄现有 resume 测试的离线做法）。
- `uv run pytest -q` 全绿 + `uv run python -m compileall -q src/memory_benchmark tests`
  通过；把两个数字写进施工报告。

## 4. 停工条件

发现以下任一情况 → 停工，把发现写进施工报告，不要自行裁决：
- 存在第二处独立构造 run 路径的代码（除 :1289 与 evaluate 解析外）导致布局分叉；
- unified manifest 字节一致性因路径改动被破坏（有测试红）；
- resume 语义除"查找路径"外还需改 checkpoint 内容才能工作。

## 施工报告（actor 填写）
（待填：commit 列表 / 测试数字 / 发现与偏离）

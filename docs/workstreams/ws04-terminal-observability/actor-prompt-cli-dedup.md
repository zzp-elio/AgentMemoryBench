# 卡 X：CLI 别名去重（留新去旧 5 对）+ smoke 默认问题帽=1

> 2026-07-13 架构师（Opus 4.8）开卡。cost-safety 前置：跑 5×10 真实 smoke 前,
> 把混乱的旧/新别名去重、给 smoke 一个"默认只评 1 个问题"的帽,防误烧钱。
> **纯离线、零真实 API、不碰 benchmark adapter 冻结行为、不碰 method 算法。**
> 这是 ws03/ws04 CLI 整治的**最小前置子集**,不做全量 CLI 重构。

## 先读（按序）
1. `AGENTS.md`
2. `docs/reference/actor-handbook.md`
3. `src/memory_benchmark/cli/main.py`（`_add_prediction_arguments` + `_normalize_legacy_prediction_args`）
4. `tests/test_main_cli.py`
5. 本卡

## 背景（架构师一手核过的现状，`文件:行号`）
CLI 现有 **5 对新/旧别名并存**（各带互斥冲突守卫，main.py:691-695）：

| 保留（新，简洁） | 删除（旧） | 解析点 |
|---|---|---|
| `--rounds` | `--smoke-turn-limit` | main.py:525 |
| `--conversations` | `--smoke-conversation-limit` | main.py:530-534 |
| `--workers` | `--smoke-max-workers` | main.py:543-544 |
| `--conversation-budget` | `--max-new-conversations` | main.py:547-552 |
| `--questions-per-conversation` | `--question-limit-per-conversation` | main.py:555-559 |

轴 flag `--turns` / `--sessions` / `--sources` **保留不动**。positional `prediction_mode`
与 `--profile` 的冗余**本卡不碰**（留 ws03）。

**smoke 默认问题数现状 = 无上限（None → 全部问题）**（main.py:555 `_positive_or_none`）。
locomo 一个 conversation ~200 问题全跑 = 隐形烧钱口。用户拍板：**默认 smoke 只评 1 个
问题**（longmemeval/membench 每隔离空间本就 1 问题；1 问题足以验证四步链路，smoke 不看答对率）。

## 施工纪律
- TDD；每 task 一 commit（一行英文）；本地 commit 不 push。
- **零真实 API**；中文 docstring；不改 third_party、不改 benchmark adapter 冻结语义、
  不改 method 算法。
- **行为变更只允许一处**：smoke 默认问题数 None→1。其余（formal/official-full 路径、
  非 smoke 行为、各 benchmark adapter）**字节级零回归**。
- 遇本卡未覆盖 → 停工写断点。

## Task 1：删 5 个旧别名，保留新名
- `_add_prediction_arguments`：删除 `--smoke-turn-limit`/`--smoke-conversation-limit`/
  `--smoke-max-workers`/`--max-new-conversations`/`--question-limit-per-conversation`
  五个 `add_argument`。
- `_normalize_legacy_prediction_args`：把 `args.rounds if ... else args.smoke_turn_limit`
  之类的"新 else 旧"归并成只读新 flag（旧 attr 不再存在）。
- `_reject_conflicting_aliases`（main.py:691-695 附近）：删掉这 5 对的互斥检查（旧 flag
  没了，冲突不可能发生）；若该函数还守着别的，保留其余。
- 更新所有 `--help` / docstring / 注释里对旧 flag 的引用。

## Task 2：smoke 默认问题帽 = 1
- 在 CLI 归一层（`_normalize_legacy_prediction_args` / 对应 predict+run 归一处）：
  **当 `profile`（或 prediction_mode）解析为 `smoke` 且用户未显式传
  `--questions-per-conversation` 时，`question_limit_per_conversation` 默认取 1**。
- 显式传值仍覆盖默认。**formal/official-full 路径默认仍为 None（不设帽）**——只 smoke 设帽。
- 该默认是 **CLI/runner 层**，不进 benchmark adapter、不碰冻结 smoke_policy 的 history 语义。

## Task 3：更新受影响测试（先 grep 全找出来）
- `grep -rn "smoke.turn.limit\|smoke.conversation.limit\|smoke.max.workers\|max.new.conversations\|question.limit.per.conversation" tests/` 找所有用旧 flag 的测试 → 改用新 flag。
- 找所有"smoke 跑多问题"的断言（依赖旧默认=全部问题的）→ 按新默认=1 更新预期，或显式传
  `--questions-per-conversation N` 保持原意图。
- 加断言：`predict smoke`（不传 questions）→ `question_limit_per_conversation == 1`；
  `predict formal` → 仍为 None。
- 加断言：旧 flag 已删（传 `--smoke-turn-limit` 应报 unrecognized argument）。

## Task 4：零回归确认
- 全量 pytest 绿（当前基线 1093）；非 smoke / formal 路径行为不变。

## 唯一自检命令
```bash
uv run pytest -q tests/test_main_cli.py && uv run pytest -q
```

## 明确不做
- 不碰 positional `prediction_mode` vs `--profile` 冗余（ws03）。
- 不碰 `--turns/--sessions/--sources`。
- 不改 benchmark adapter、smoke_policy 的 history 剪裁语义、method 算法、third_party。
- 不做真实 API。

## 停点
Task 1-4 完成 + 全量零回归 + 各 commit 就停，报告（实际模型名自查系统提示）。

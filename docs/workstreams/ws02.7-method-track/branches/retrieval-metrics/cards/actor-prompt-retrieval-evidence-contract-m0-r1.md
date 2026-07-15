# Actor 返工卡：RetrievalEvidence M0 R1（拒绝非法 status）

> **给当前 actor 的执行指令：你就是用户已选中的执行者。** 本卡被发送到当前会话即代表
> 用户已经完成选择与授权，请直接在首轮 worktree 上施工，不要再把自己当成调度者询问由谁
> 派发。是否使用当前执行环境自己的 subagent 由 actor 判断，本卡不作禁止；实质使用则在
> 回报中说明。只补一个 follow-up commit，不 amend 首轮 `5fd5ac1`，零真实 API。

## 0. 目标与验收缺口

首轮 `5fd5ac1` 的 M0 plumbing、三家 adapter 矩阵和 artifact/manifest 逻辑保留。架构师已
独立在数据齐备的 worktree 中复跑原七文件套件：

```text
297 passed, 1 warning in 12.35s
```

但协议层还有一个现有测试未覆盖的运行时缺口：

```python
EvidenceAssertion(status="bogus", reason_code="x", reason="y")
```

当前会成功构造。`Literal["valid", "n_a", "pending"]` 只约束静态类型检查，不会在
Python runtime 拒绝非法值；而该 status 会进入公开 artifact 并成为后续 evaluator 的契约
输入，不能接受未定义第四态。

本卡只把这道边界锁死，不重做 M0，不改其他裁决。

## 1. 上工与隔离

按顺序只读最小集合：

1. `AGENTS.md`；
2. 本卡全文；
3. `docs/reference/actor-handbook.md` §0-§4；
4. `src/memory_benchmark/core/provider_protocol.py::EvidenceAssertion`；
5. `tests/test_provider_protocol.py` 中本批 M0 evidence 测试；
6. 首轮 note `docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/
   retrieval-evidence-contract-m0.md`。

继续使用现有隔离现场：

```bash
cd /Users/wz/Desktop/mb-actor-retrieval-evidence-m0
git status --short
git log -2 --oneline
```

预期分支 `actor/retrieval-evidence-contract-m0`、HEAD=`5fd5ac1`、worktree clean。任一不符
就停工回报，不 reset、不删除、不切到主树重做。

允许修改且只允许修改：

- `src/memory_benchmark/core/provider_protocol.py`；
- `tests/test_provider_protocol.py`；
- 既有首轮 note（只追加 R1 小节，不改写首轮历史）。

不得改 adapter、runner、registry、README/status、TOML、third_party；不得 push。

## 2. 已裁修复

在 `EvidenceAssertion.__post_init__()` 的语义分支之前，显式校验 `status` 必须严格属于：

```text
valid / n_a / pending
```

非法值统一 `ValueError` fail-fast。不要把未知值当作“任意 non-valid”；不要自动正规化大小写、
空格或别名；不要引入 enum/Pydantic，也不要改变三种合法值现有的 reason 规则。

测试至少覆盖：

1. 带完整 reason 的 `"bogus"` 仍拒绝——这是首轮会真实漏过的强反例；
2. 空字符串、`None` 或非字符串中的至少两类也拒绝，证明不是只特判 `"bogus"`；
3. 错误应先指向非法 status，而不是误报 reason 缺失；
4. 既有 `valid / n_a / pending` 测试继续通过。

测试可用 `cast(Any, ...)` 或局部 `# type: ignore[arg-type]` 表达故意越过静态类型的 runtime
反例；不要放宽生产 annotation。

## 3. 唯一自检、commit 与回报

只跑本次直接相关的最小自检：

```bash
uv run pytest -q tests/test_provider_protocol.py
git diff --check
```

然后显式暂存三条允许路径并提交 follow-up：

```bash
git status --short
git add \
  src/memory_benchmark/core/provider_protocol.py \
  tests/test_provider_protocol.py \
  docs/workstreams/ws02.7-method-track/branches/retrieval-metrics/notes/retrieval-evidence-contract-m0.md
git commit -m "fix(metrics): reject invalid evidence status"
```

到此停止，不 push。按 actor-handbook §4 回报：follow-up commit hash、测试尾行原文、实际
改动文件、偏差/停工点；若实质使用了 subagent，再说明分工。

# Actor 卡 M0-10：workers>1 路径 manifest 丢失 provenance_granularity（小卡）

> 派发日 2026-07-13。自包含代码卡。允许修改：
> `src/memory_benchmark/runners/prediction.py`、`src/memory_benchmark/methods/
> registry.py`（如需注册级声明）、tests、新建 `notes/m0-10-manifest-provenance.md`
> （ws02.7）。禁真实 API。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m10 -b actor/m0-10-manifest
cd /Users/wz/Desktop/mb-actor-m10 && uv sync
```
禁 push；只跑目标测试 + compileall（playbook #18）。

## 1. Bug 实锤（架构师一手取证 2026-07-13）

`_method_manifest_with_protocol`（prediction.py:1209-1246）只在
`isinstance(system, MemoryProvider)` 时 stamp `provenance_granularity`；
**workers>1 协调路径 system=None**（该函数 docstring 自述"不需要真实 method
实例也能正确盖章"，但只对 protocol_version 成立）→ 并行 run 的 manifest 缺
该字段 → recall 类 conditional evaluator（按 manifest['method'] 读粒度，如
longmemeval_recall.py:36）把整个 run 判为无 provenance。
实证对照：`lm-locomo-unified-prov1`（workers=1）manifest 有 `"turn"`、recall
n=1；`lm-lme-unified-par2-s-cleaned`（workers=2）manifest 无该键、recall n=0
**尽管 artifacts 里 retrieved_items 带合法 source_turn_ids**。

## 2. 施工内容
1. 让并行路径与串行路径盖同一个章。方向参考 protocol_version 的解法（注册表
   声明优先）：给盖章函数加显式 `provenance_granularity` 入参，由调用方从
   MethodRegistration（如需新增可选字段，默认空=维持现行为）或等价静态来源
   传入；LightMem 注册行声明 `"turn"`。**不许**在协调进程实例化真实 provider。
2. 校验语义保持：非法值仍 fail-fast（prediction.py:1239-1244 现有分支）。
3. resume 兼容确认：`_manifest_equals_for_resume`（prediction.py:1160-1177）
   已对缺失键做双侧 pop——补测试钉死"旧无字段 run × 新有字段代码"可 resume
   比对通过。
4. 测试：并行路径（system=None + 注册声明）manifest 含正确粒度；串行路径
   行为不回归。

## 3. 完成门
目标测试 + compileall 全绿（报数字）；note 记录方案与锚。真实验证 = 下一次
任意 workers>1 predict 后 manifest 抽查（架构师做，不在本卡）。

## 4. 停工条件
- provenance 粒度未来需要 per-benchmark 分叉导致注册级静态声明不成立 →
  停工给方案选项。

## 施工报告（actor 填写）
（待填）

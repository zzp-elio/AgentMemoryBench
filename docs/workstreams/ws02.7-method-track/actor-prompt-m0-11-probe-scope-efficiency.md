# Actor 卡 M0-11：update probe 在 conversation scope 触发 question 效率断言（跨 method 通用陷阱）

> 派发日 2026-07-14。自包含代码卡。允许修改：
> `src/memory_benchmark/observability/efficiency/collector.py`、
> `src/memory_benchmark/methods/lightmem_adapter.py`、`mem0_adapter.py`、
> `memoryos_adapter.py`、`amem_adapter.py`（各仅限效率记录调用处的机械替换）、
> tests、新建 `docs/workstreams/ws02.7-method-track/notes/m0-11-probe-scope.md`。
> 禁改 third_party、禁改 runners/（operation_level.py 的 scope 编排是对的）、
> 禁真实 API。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m11 -b actor/m0-11-probe-scope
cd /Users/wz/Desktop/mb-actor-m11 && uv sync
```
禁 push；只跑目标测试 + compileall（playbook #18）。

## 1. Bug 实锤（架构师一手取证 2026-07-14）

真实现场：`lm-halumem-unified-s1` predict 启动即失败
`Error: question efficiency requires a question scope`。链路：

1. HaluMem 走 operation-level runner，**update probe 在 conversation scope 内**
   调 `provider.retrieve(purpose="memory_update_probe")`
   （`runners/operation_level.py:238-252` conversation_scope 包住
   `_ingest_and_probe_session`，probe 在 :364-374）。scope 编排本身正确：
   probe 属记忆构建阶段观测，其时延已单独记入
   `update_probe_records.duration_ms`（:380）。
2. LightMem adapter 的 `_retrieve_question` 在 collector 启用时**无条件**
   `record_retrieval_result`（`lightmem_adapter.py:844-851`）——该方法经
   `_require_question_state` 硬断言必须在 question scope
   （`observability/efficiency/collector.py:198,437-441`）→ 炸。
3. **不是 LightMem 独有**：`amem_adapter.py:490`、`memoryos_adapter.py:790`、
   `mem0_adapter.py:902,981` 同一姿势自记 `record_retrieval_result`——任何
   method 上 halumem 都会在第一个 update probe 处崩。必须系统级修。

## 2. 架构师裁决（方案不可自行变更）

**collector 侧新增 scope 容忍变体，adapter 侧机械替换**：

1. `EfficiencyCollector` 新增 `record_retrieval_result_if_question_scope(...)`
   （签名同 `record_retrieval_result`）：当前 scope 是 question → 行为与现方法
   逐字节一致（含 `_ensure_retrieval_not_recorded` 重复声明拒绝）；当前 scope
   是 conversation/judge → **静默 no-op**（probe 时延另有归宿，见 §1.1）；
   无 scope / collector 关闭 → 维持现有各自语义（`_active_state_or_none`）。
2. 五个 adapter 调用点（lightmem:845、amem:490、memoryos:790、mem0:902,981）
   换成新变体。**不改动任何 adapter 的检索/计时/token 统计逻辑本身。**
3. `record_retrieval_result` 原方法保持 fail-fast 不动（runner 侧误用仍要炸）；
   `record_answer_generation` 不动（probe 不产生答案，get_answer 不会在
   conversation scope 被调；若你发现反例=停工上报，不许顺手改）。
4. 已知语义留档（写进 note，不改代码）：probe 期间 adapter 内部的
   embedding/LLM 调用经 `operation_stage(RETRIEVAL)` 记在 conversation scope
   下、stage=RETRIEVAL——成本归属为"构建期探针"，D3 口径下可接受，声明即可。

## 3. 测试
- collector 单测：question scope 内新变体 = 原方法等价行为（含重复声明拒绝）；
  conversation scope / judge scope 内 = no-op 无记录无异常；无 scope 时语义
  与原方法一致。
- 回归复现测试：构造自记效率的 provider stub 走
  `run_operation_level_predictions` 的 update probe 路径（或最小等价单元），
  修前炸/修后过（钉死本 bug 不复发）。
- 既有全部效率相关测试不回归（question_efficiency 记录数、observation id
  序列不变）。

## 4. 完成门
目标测试 + compileall 全绿（报数字）；note = 实锤链路 + 五处替换清单
（文件:行号）+ §2.4 归属声明。真实验证 = 架构师合并后用户重跑
halumem smoke s1（不在本卡）。

## 5. 停工条件
- 发现 `record_answer_generation` 也会在非 question scope 被触发；
- 新变体导致任何既有 observation id/记录数变化。

## 施工报告（actor 填写）
（待填）

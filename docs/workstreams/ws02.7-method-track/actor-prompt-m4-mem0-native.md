# Actor 卡 M4-mem0：native config-track bundle 注册（locomo/lme/beam 三格）

> 派发日 2026-07-14。允许修改：`src/memory_benchmark/methods/config_track.py`、
> 新建 `src/memory_benchmark/methods/mem0_native_prompts.py`、tests（mem0/
> config_track 相关）、新建 `docs/workstreams/ws02.7-method-track/notes/
> m4-mem0-native.md`。禁改 third_party、禁真实 API。

## 0. Git 纪律
```
git -C /Users/wz/Desktop/memoryBenchmark worktree add ../mb-actor-m4mem0 -b actor/m4-mem0-native
cd /Users/wz/Desktop/mb-actor-m4mem0 && uv sync
```
禁 push;只跑目标测试 + compileall（playbook #18）。所有新增函数/类/嵌套
helper 都要中文 docstring（含测试文件,主树全量会查,已有三例盲点教训）。

## 1. 背景与现状（架构师 2026-07-14 取证）

- checklist B10/B11 要求双轨 smoke;R2 裁决 mem0 native 注册面=
  **locomo/longmemeval/beam 三格**（memory-benchmarks harness 有官方复现;
  membench/halumem 无 native 格=单轨 collapse,不注册）。
- 现状:`methods/config_track.py` 的 `_NATIVE_CONFIG_TRACK_BUNDLES` **只有
  lightmem 条目**（:50-54),mem0 走 `--config-track native` 会 fail-fast。
- adapter 侧已供货:mem0 retrieve 已产 `prompt_messages`（官方 reader
  builder 排版,mem0_adapter.py:943,1023）,native 轨 answer prompt 无需
  adapter 改动。
- 模型口径拍板（R3,2026-07-14）:**第一阶段模型不 native**——bundle 的
  answer/judge **模型仍走框架统一 gpt-4o-mini**;native 化的只有 prompt
  文本与超参引用（官方 harness 默认 gpt-5 的榜单校准明确不做）。

## 2. 施工内容

镜像 lightmem 样板（`_lightmem_bundle` + `lightmem_native_prompts.py`）：

1. **Phase A 取证（写进 note）**：逐格锚 memory-benchmarks 三个 benchmark
   的官方 answer prompt builder 与 judge prompt 调用点（locomo/longmemeval/
   beam 的 `prompts.py` + `run.py`,M1 note §1.2 有锚表可作起点;M3 note
   §1 已锚 answer builder）。judge prompt 逐字一手抄,注明与框架现役
   judge 的差异点（若逐字相同,写"零偏差"并给对比锚）。
2. `mem0_native_prompts.py`：`MEM0_NATIVE_ANSWER_PROFILES` /
   `MEM0_NATIVE_JUDGE_PROFILES`（仅 locomo/longmemeval/beam 三键）,prompt
   文本自带 parity 锁测试（逐字断言,防漂移）。
3. `config_track.py`：`_mem0_bundle(benchmark)` 加入
   `_NATIVE_CONFIG_TRACK_BUNDLES`;`embedding_ref`/`hyperparam_ref` 按
   mem0 repo 默认写引用串（模型名统一不变,见 §1 拍板）。
4. 测试：① `resolve_config_track("mem0", <三格>)` 返回 bundle 且字段
   齐;② membench/halumem 仍 fail-fast(注册面不扩大);③ lightmem 既有
   bundle 不回归;④ prompt parity 锁。

## 3. 完成门
目标测试 + compileall 全绿（报数字）;note = Phase A 锚表 + 注册面声明。
真实 native 三格 smoke 由用户跑（不在本卡）。

## 4. 停工条件
- 官方 judge prompt 在 harness 里按 benchmark 分叉出多版本、无法确定
  实际调用点（签名默认值不作数,须核实际调用,playbook 陷阱#1）→ 停工
  给选项。
- ConfigTrackBundle 字段与 mem0 场景不匹配（如 judge_profile 结构装不下）
  → 停工给方案,禁自行改框架结构。

## 施工报告（actor 填写）
（待填）

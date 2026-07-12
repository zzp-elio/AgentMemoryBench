# M0-1b 卡：LightMem 双轨运行时 config-track 机制（unified 默认字节级零回归）

> ws02.7 M0 第二个 actor 批次，2026-07-12 架构师（Opus 4.8）开卡。**这是核心
> 管线改动，最高风险区**。铁律：**config_track=unified 时全链路字节级零回归**
> （现有 1069 测试全绿、manifest/prompt/settings 逐字不变）。任何做不到零回归
> 的接法 → **停工上报**，不许为 native 冒险改动 unified 路径。

## 先读（按序）
1. `AGENTS.md`
2. `docs/reference/actor-handbook.md`
3. `docs/reference/dual-track-config-policy.md`（§2 build/readout、§6 collapse、§8 与
   现有 `prompt_track` 正交）
4. `docs/workstreams/ws02.7-method-track/README.md` 断点（含本卡由来 + M0-1 验收
   发现的 longmemeval fidelity gap）
5. 本卡

## 背景与设计（架构师一手核过的 seam，照此实现）

M0-1 已交付离线 native 资产：`methods/lightmem_native_prompts.py` 的
`LIGHTMEM_NATIVE_ANSWER_PROFILES` / `LIGHTMEM_NATIVE_JUDGE_PROFILES`（已验收）。
本卡把它们接上运行时。

**关键事实（架构师已一手核，别重复怀疑）**：
- LightMem `provided_capabilities` 含 `MEMORY_RETRIEVAL`（registry.py:774）→
  `use_framework_answer_reader=True` → **框架 reader 生成答案**，答案 prompt 由
  `prompt_track` 决定（`run_prediction.py:411`）。所以 native 轨的接入点是
  **框架 reader 路径**（prompt 源 + answer_llm_settings），不是 method 自答。
- 现有 `answer_llm_settings`（`run_prediction.py:416` → `resolve_answer_llm_settings`）
  模型 pin 在 `DEFAULT_OPENAI_MODEL=gpt-4o-mini`；LightMem paper headline backbone
  **也是 gpt-4o-mini**（`experiments/locomo/readme.md:115`）→ **native 轨模型不变，
  只 sampling 参数变**（temp=0/max_tokens=2000/top_p=0.8，来自 M0-1 已抽的
  `LIGHTMEM_NATIVE_ANSWER_SETTINGS`）。
- 现有 `prompt_track` 是 **benchmark 级**（registry 由有无 `unified_prompt_builder`
  决定，五 benchmark 全 "unified"）。本卡的 `config_track` 是 **run 级 + method 驱动**，
  与 `prompt_track` **正交**：config_track=native 时**强制 reader 用 provider 的
  `prompt_messages`**（method 自己的 paper prompt），覆盖 benchmark 的 unified builder。

**设计（run 级 `config_track ∈ {unified, native}`，默认 unified）**：
- **unified**：resolver 返回 `None`（哨兵=无覆盖）→ 走现有全部默认 → **字节级零回归**。
- **native**：查 `(method, benchmark)` native bundle：
  - answer prompt 源 = **provider `prompt_messages` 透传**；
  - answer_llm_settings = native（0/2000/0.8，模型仍 gpt-4o-mini）；
  - judge = `LIGHTMEM_NATIVE_JUDGE_PROFILES[benchmark]`（locomo=native ACCURACY_PROMPT
    evaluator + cat5 跳过；longmemeval=复用现有官方 evaluator）；
  - embedding/超参 = native（LightMem locomo：embedding=all-MiniLM，与 unified 同；
    **本卡不改 embedding/超参**，只把 bundle 里留出字段，值等于 unified，M0.2 再核）。
  - `(method,benchmark)` 无 native bundle → **fail-fast** `ConfigurationError`（引用
    policy §6 collapse：native 只在官方实验格存在）。

**本卡不做**（划清边界，防 scope 膨胀）：
- **不做** track-aware 路径层 `.../{mode}/{track}/{run_id}`（下一卡 M0-1c）。本卡
  native 与 unified 靠**显式不同 run_id** 区分（架构师跑 smoke 时手给）。
- **不碰真实 API**、不改 method 算法、不改 third_party、不改 embedding/超参数值。
- 不接 LightMem 以外 method 的 native bundle（本卡只注册 lightmem 的 locomo+longmemeval）。

## 施工纪律
- TDD；每 task 一 commit（一行英文）；本地 commit 不 push。
- **零真实 API**；中文 docstring；不改 third_party。
- **零回归铁律**：任一步做完先跑全量确认 unified 不变；破了就回退+停工。
- 遇本卡未覆盖 / 零回归做不到 → **停工写断点**，不猜、不硬推。

## Task 1：longmemeval native builder pass-through 修复（先做，闭合 M0-1 fidelity gap）
M0-1 验收发现：`build_lightmem_longmemeval_native_answer_prompt` 从
`formatted_memory` 重建，而 `formatted_memory`（=adapter `answer_context`）走
`_format_lightmem_memory`（reader 布局，`lightmem_adapter.py:1532`），**官方**
longmemeval 用 `_format_lightmem_memory_as_official_retrieve`（`:1572`，docstring
明写对齐 `run_lightmem_gpt.py:186`）→ 运行时 memory 呈现会与官方分叉。
- **改** longmemeval native builder：**透传 `retrieval_result.prompt_messages`**
  （与 locomo builder 同款），不再从 formatted_memory 重建。守卫：`prompt_messages`
  必须是官方 2 段 `[system, user]` 形状，否则 `ConfigurationError`。
- 保留 `LIGHTMEM_LONGMEMEVAL_NATIVE_*` 常量作 parity 锚（现有测试不动）。
- **加端到端 parity 测试**：用 fake backend / 合成 memories 驱动**真实 adapter
  `retrieve(RetrievalQuery)`** → native builder → 断言产出的 user prompt 内存段
  用的是 `_format_lightmem_memory_as_official_retrieve` 口径（即与 adapter 自身
  `prompt_messages` 逐字一致）。这是 M0-1 离线测试覆盖不到的真源链路。
- locomo 侧同加一条端到端断言（adapter prompt_messages == native builder 透传结果），
  证明"透传"确实拿到官方 ANSWER_PROMPT。

## Task 2：config_track resolver + native bundle 注册（离线）
新文件 `src/memory_benchmark/methods/config_track.py`（或就近合适位置）：
- `ConfigTrackBundle` dataclass：`{answer_prompt_source, answer_llm_settings,
  judge_profile, embedding_ref, hyperparam_ref}`。
- `resolve_config_track(method, benchmark, config_track) -> ConfigTrackBundle | None`：
  unified→None；native→查注册表；无则 fail-fast。
- 注册 lightmem 的 (locomo)/(longmemeval) native bundle，复用 M0-1 的 profile 常量。
- 单测：unified→None；native locomo/longmemeval→正确 bundle；native 未注册格→raise。

## Task 3：接 native answer 进 reader 路径（零回归）
`run_prediction.py`：引入 `config_track` 参数（一路透传，默认 "unified"）。
- config_track=native 时：
  - 强制 reader 用 provider `prompt_messages`（native prompt 源），覆盖 unified builder；
  - `answer_llm_settings` 用 native settings（改 sampling 参数，模型不变）。
- config_track=unified 时：**这两处一行都不走**（走现有默认）。
- manifest 加 `config_track` 字段（参照现有 `prompt_track` 字段 `:1060`），进身份
  比较（unified/native 不互相 resume）。
- **零回归断言**：加测试——config_track 缺省/"unified" 时，method_manifest、prompt、
  answer_settings 与改动前逐字相同。

## Task 4：接 native judge 进评测路径（零回归）
`evaluation.py`（+ evaluator 解析处）：config_track=native 时用 native judge profile
（locomo=native ACCURACY_PROMPT + cat5 跳过语义；longmemeval=复用现有官方 evaluator，
**不新建**）。unified 时不变。
- 零回归断言：unified 时 evaluator 解析与现状逐字相同。

## Task 5：native 轨 flow-through 假测试（无真实 API）
用 fake reader/judge 跑一条 (lightmem, locomo, native) 与 (lightmem, longmemeval,
native) 的 flow-through：断言走的是 native prompt 源 + native answer settings +
native judge，且 manifest.config_track=="native"。验收口径 = 调用发生（不看答对）。

## 唯一自检命令
```bash
uv run pytest -q  # 全量：必须 ≥1069 passed 且零回归（unified 路径全绿）
```
（本卡动核心管线，只跑定向不够；但**不跑任何 `-m api`**。）

## 停点
Task 1-5 完成 + 全量零回归通过 + 各 commit 就停，报告（实际模型名自查系统提示）。
**零回归破了、或 native 接入必须改动 unified 字节 → 立即停工写断点交架构师，不硬推。**

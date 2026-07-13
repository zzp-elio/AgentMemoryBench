# LightMem 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 状态：**M0 进行中**（当前唯一在走 method-frozen-v1 流程的 method）。
> 更新纪律：每过一项 B 判据 / 发现特殊情况，更新本文对应节。2026-07-13 建。

- adapter：`src/memory_benchmark/methods/lightmem_adapter.py`（1,716 行）
- 算法源：vendored `third_party/methods/LightMem`（`src/lightmem/memory/lightmem.py`）
- native 格：**locomo、longmemeval**（官方 experiments 目录；其余格单轨 collapse）

## 0. 接口调用面（黑盒拆解）

| 框架钩子 | adapter 行为 | 落到 LightMem 官方接口 |
|---|---|---|
| `ingest(unit)` | 按 conversation 缓冲、攒批（`_convert_conversation_to_batches`，adapter:1107） | `LightMemory.add_memory(messages, force_segment=…, force_extract=…)`；**最后一批传 force=True 强制刷洗**（adapter:491-494） |
| `end_conversation` | 早退保护后写残余批（adapter:556 起；`_write_native_batch` force=is_final，adapter:579-580） | 同上 `add_memory(force_*=True)` |
| `retrieve(query)` | adapter:699；结果经 `_format_lightmem_memory`（adapter:1532，reader 版式）或 native 轨 `_format_lightmem_memory_as_official_retrieve`（adapter:1572，官方 retrieve 版式） | `LightMemory.retrieve()`（返回格式化字符串时不保留 payload，adapter:1497 注释） |
| `cleanup` / clean-retry | `clean_lightmem_conversation_state`（adapter:1660-1664 删 qdrant/logs 目录）；registry 挂 `_clean_lightmem_failed_ingest_state`（registry.py:796） | 文件系统级清理，不走官方 API |

**关键机理（一手，2026-07-13 定论）**：`online_update()` 是 `return None` 空壳
（lightmem.py:394-395）→ **offline 是唯一可用模式**（adapter config `update="offline"`）；
`offline_update()` 才做 embed+插入向量库（lightmem.py:407-434）；`force_segment`
（lightmem.py:313）强制切段、`force_extract` 经 `add_segments`（lightmem.py:323）强制抽取。

## B1-B11 逐项

- **B1 来源锁与接口选择 ✅**：vendored 路径如上；只用 `retrieve+add_memory`，不用其
  chat 入口（公平性）。审查记录 `docs/workstreams/ws02.7-method-track/notes/lightmem-m0-audit.md`。
- **B2 注入粒度 🟡**：locomo=turn/batch、longmemeval=pair；**HaluMem memory_point
  支持待核**（add_memory 返回值有无本次产出条目——M0-3 卡取证中）。**注册面缺口
  （2026-07-13 一手）**：LightMem 注册 `task_families={CONVERSATION_QA}`
  （registry.py:770），**HaluMem（operation-level）当前在 registry 层就进不去**——
  待 M0-3 证据回来后走 checklist B5+ 无损改造评估（可改造/不可改造→N-A）。
- **B3 隔离 ✅ 物理**：per-conversation Qdrant collection + 独立路径（adapter:388-390，
  summary 库另置 :390）；clean-retry = 删目录（:1660-1664），干净。并行安全。
- **B4 formatted_memory+时间戳 🟡**：locomo 官方 speaker 分组 + `_format_lightmem_memory`；
  longmemeval native 已透传 `prompt_messages` 对齐官方（M0-1b）。时间戳覆盖度待逐
  benchmark 核。
- **B5 provenance ✅ = none**（adapter:304）→ recall/ndcg 类指标对 LightMem **全 N/A**。
- **B6 flush ✅**：offline + force 已接（见 §0）；不 flush 检索到空记忆的判例即出自本
  method（checklist B6 引用）。
- **B7 效率插桩 ✅**：build/answer/judge 三角色 api_usage 真 token（2026-07-12 效率审计
  无拦截缺口）；LightMem add_memory 自带 token/api_call_nums 返回值可做交叉参照（待留档）。
- **B8 副作用/clean-retry 🟡**：物理隔离 + 删目录清理已具备；「检索是否改内部状态」
  待 M 阶段核（LightMem 检索为向量查询，预期无写副作用，未锚死）。
- **B9 模型口径 ✅（M0.2 三方取证 + 架构师裁决，2026-07-13）**：证据全表
  `ws02.7/notes/lightmem-native-config-threeway.md`。**build 轴两轨分叉实锤**：
  extract_threshold unified=0.5（repo 默认，ws02.5 方案 B）vs native=0.1（复现目录）；
  compression rate 0.7 vs 0.6(locomo)/0.8(lme)；offline score 0.8 vs 0.9(locomo)。
  embedding 两轨同为 all-MiniLM-L6-v2。→ **LightMem 两个 native 格记忆不可复用，
  构建成本 ×2**（进成本表）。裁决：native 配置源=复现目录 README reported 命令
  （作者当前背书）；paper (r,th) 网格与脚本单值的出入已留痕、不标 DISPUTED，
  R0 校准达不到论文数字再升级。repo schema 默认**不可运行**（text_embedder=None、
  compressor/topic 顶层 OFF），故"repo 默认超参"操作化以 toml 注释留痕为准。
- **B10 双轨 ✅**：config-track 机制 M0-1b 验收（`methods/config_track.py`；unified 轨
  字节零回归）；native locomo answer=`ANSWER_PROMPT`（Task1 裁决，summary OFF 是
  headline）；native 格注册 `{("lightmem","locomo"),("lightmem","longmemeval")}`。
- **B11 smoke+冻结 🟡**：**locomo 格双轨 smoke 全通（2026-07-13）**。
  ① unified：空库悬案已关闭（diag-log1 复跑：1 round → force 刷洗 → 抽取 2 条
  记忆 → 检索命中，sentinel=0；此前空库判为抽取 LLM 单次返 0 波动，非结构性 bug）。
  ② native（lm-locomo-native-smoke1）：**产物级实锤读出分叉**——answer 用官方
  ANSWER_PROMPT 经 prompt_messages（与 unified 模板逐字不同）、judge 用
  `lightmem_locomo_paper_native_judge_v1` 返回官方 JSON 契约；manifest
  config_track=native；且是 **M0-1c 新路径 `smoke/native/` 的首个实战验证**。
  剩余：longmemeval 双轨 smoke → membench/beam unified smoke（先离线核 adapter
  对第三人称/10M 形态的兼容）→ halumem（待 B5+ 改造评估）→ cost-probe →
  method-frozen-v1。

## 特殊情况
1. **StructMem（`--enable-summary`）是另一个实验**：换 build+检索+embedding
   （text-embedding-3-small），非 paper headline，不接（政策判例锚
   `dual-track-config-policy.md` §10）。
2. 双轨政策全文 `dual-track-config-policy.md`；native prompt 资产
   `methods/lightmem_native_prompts.py`（longmemeval builder 透传 prompt_messages，
   2-message 守卫）。track-aware 路径层已生效（M0-1c，2026-07-13）：新 run 落
   `…/{mode}/{track}/{run_id}`，旧布局仅可 evaluate 不可 resume。
3. **日志已知限制**：LightMem 内部诊断走 `self.logger`（`Created N`=INFO :372、
   `No entries found`=WARNING :474/:554），INFO 级连它自己的内部日志文件都不落
   （实测 0 字节）；框架 `logs/method.log` 亦未捕获。真需要内部 INFO 时再查其
   logger 配置，当前不阻塞。

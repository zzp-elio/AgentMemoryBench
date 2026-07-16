# M0 spec+plan：Method Track 双轨接入 + LightMem 首接

> **现行政策覆盖（2026-07-16）：**本文保留 2026-07-12 的施工历史与当时配置，不再作为
> unified/native 定义的当前判据。旧 §3.1 “unified 统一 embedding”是当时有效的控制变量政策，
> 不是历史错误；2026-07-16 起主轨改为 pinned product default，旧 all-MiniLM 资产保留为
> `controlled_embedding_v1`。同时“native=paper 全套”已被六轴 coverage 取代，算法分叉另列
> `reproduction_variant`。执行新工作必须先读现行 policy，不得从本历史 plan 复活旧口径。

> 2026-07-12 架构师（Opus 4.8）起草。小型合订本（spec+plan），一次用户
> 批准即开工（playbook §9.5 允许）。前置：benchmark 五家 frozen-v1 + B6
> 完成。标准判据见 `docs/reference/method-integration-checklist.md`。

## 1. 目标与非目标

**目标**：把 method 侧从"能跑通"推进到"双轨可信接入 + 极小 smoke"。
LightMem 首接（外部校准器）。产出可复用的 config-track 机制，让后续
method 复用。

**非目标**：全量实验（等 R0 预算）；真实 API 大规模跑；method 算法改动；
一次接多个 method（严格逐个，原则 §9.6）。

## 2. native 配置矩阵证据出处（一手，更正先验错误）

架构师此前凭训练先验报的矩阵有错（Mem0/SimpleMem 漏报），已逐仓库更正
（矩阵见 README）。出处：
- Mem0 `mem0-main/memory-benchmarks/benchmarks/{locomo,beam,longmemeval}/`
  （各含 prompts.py+run.py）。
- SimpleMem `SimpleMem/EvolveMem/evolvemem/benchmarks/{locomo,longmemeval,
  membench}.py`（membench.py 261 行非空）。
- MemoryOS `eval/evalution_loco.py`（仅 locomo）；A-Mem `data/locomo10.json`
  （仅 locomo）；MemOS `evaluation/scripts/{locomo,longmemeval}`；EverOS
  `benchmarks/config.toml`（"comparable to published LoCoMo"）。
- HaluMem 全员皆无（2511 新 benchmark）；MemBench 仅 SimpleMem；BEAM 仅 Mem0。
- **教训固化**：method 能力/配置必须逐仓库一手核，不凭先验（playbook
  原则 #11 新判例）。

## 3. 双轨 config-track 设计（架构师裁定）

### 3.1 两轨定义
- **unified 轨（默认，现状不变）**：框架统一 embedding + 统一 answer
  （per-benchmark unified prompt + `resolve_answer_llm_settings`）+ 统一
  judge（per-benchmark evaluator + llm_judge.toml）。所有格子都有。
- **native 轨**：method paper 的 embedding + answer + judge。仅 README
  矩阵 ✓ 格存在。

### 3.2 两轨差异与记忆复用（关键裁定；完整政策见 dual-track-config-policy.md §2）
差异共 **7 轴**，按影响面二分：
- **readout 轴**（answer LLM/prompt、judge LLM/prompt、judge 语义）改了**不用重建记忆**，
  同一记忆库跑两次读出即可——**便宜**。
- **build 轴**（embedding、method 内部超参）改了**必须重建记忆**——**成本 ×2**。
- **记忆复用是有条件的**：仅当两轨 build 轴**全同**才成立（改正此前"native 只重跑
  answer+judge"的无条件口径）。
- **LightMem×locomo 具体核**：headline=LightMem 模式（summary OFF），embedding 两轨都
  all-MiniLM（`experiments/locomo/readme.md:58`）→ embedding 轴相同；**但内部超参
  （chunk/threshold，如 paper 的 (768,0.8)）是否 == `add_locomo.py` repo 默认，M0.2 须核**
  ——不等则 build 分叉、仍是两次构建。StructMem 是独立实验（换 build+检索+embedding
  text-embedding-3-small），非 headline，不接（Task1 裁决见 §3.5）。

### 3.3 双 embedding 同建两库——否决（用户 2026-07-12 提议 + 架构师否决）
省不了钱：① method 内部 embedding 藏在其库内，只能黑盒 `ingest()` 驱动，
无法分叉写两库（改算法核心=硬规则禁止）；② 检索耦合构建（LightMem
offline_update 读回向量库）下 embedding 变会令记忆**文本**分叉，非仅向量；
③ 纯前馈 method 的 embedding 也在库内同样分叉不出。按用户"不省则不做"否决。

### 3.4 实现形态
- config-track = TOML 捆绑 `{embedding_ref, answer_profile_ref,
  judge_profile_ref}`，一旗标 `--config-track unified|native` 选择；
  `unified` 为默认，**track 缺省时行为与现状字节级一致**（零回归）。
- **track-aware run_id/artifact 路径**：`{method}/{benchmark}/{mode}/{track}/
  {run_id}`——从一开始带 track 维度，避免以后加 native 撞车/作废 unified。
- native prompt 从 method 仓库**一手抄**成注册 profile；不发明。

### 3.5 Task 1 裁决（LightMem locomo answer prompt：ANSWER_PROMPT vs StructMem）
2026-07-12 actor（Codex/GPT-5.6）Task 1 停工上报：两 prompt 都是活跃分支、
`--enable-summary` 切换、默认 False（证据 `search_locomo.py:258-280/441-447/566-570/
616-620`）。**架构师裁决 = native locomo answer = `ANSWER_PROMPT`（标准）**，依据：
- `--enable-summary` **不是纯 answer 开关**，而是 build+检索+embedding 三处都变：build
  `add_locomo.py --extraction_mode event --enable_summary --summary_time_window 3600
  --summary_top_k 15`；检索 `--summary-limit 5`；embedding `text-embedding-3-small`。
- LightMem paper **headline locomo 数字（71.95–72.99）= LightMem 模式 = summary OFF =
  标准 ANSWER_PROMPT**（`experiments/locomo/readme.md:49-97` "for our reported results"
  指非-summary 表；StructMem 是 `:183-196` 独立小 ablation）。
- 故 native locomo = ANSWER_PROMPT；**StructMem 是另一套完整实验，不属 M0-1 answer-
  profile 卡范围**。日后若要该 ablation 数字，另立 build 变体卡。
- **actor 解冻续 Task 2-4**：native locomo answer 锁 ANSWER_PROMPT，删去 StructMem 分支。

## 4. 施工分批（actor 卡逐个开，架构师逐批验收）

- **M0-1（首卡，已开 actor-prompt-m0-lightmem-config.md；Task1 已裁决 §3.5）**：
  **纯离线**抽取 LightMem **locomo** native answer/judge profile（一手抄 + 逐字
  parity + 注册）。**不含运行时 config-track 切换机制**（重新 scope：那是架构师
  设计后的 M0-1b，不丢欠规格机制给 actor）。**不碰真实 API/算法**。
- **M0-1b（卡已开 `actor-prompt-m0-1b-config-track.md`）**：运行时 config-track
  机制——`config_track ∈ {unified,native}` run 级选择器 + native bundle 注册 +
  接 native answer/judge 进框架 reader/评测路径，**unified 默认字节级零回归**；
  含 **longmemeval pass-through 修复**（闭合 M0-1 验收发现的 fidelity gap）。
  与 benchmark 级 `prompt_track` **正交**（policy §8）。**不含**路径层 track 段
  （M0-1c）——本卡 native/unified 靠显式 run_id 区分。
- **M0-1c（M0-1b 验收后）**：track-aware 路径 `.../{mode}/{track}/{run_id}` +
  resume；这样 native/unified 产物物理隔离、自动不撞。
- **M0-eff（预算关键，卡已开 `actor-prompt-m0-eff-cost-report.md`，与 M0-1b 并行）**：
  效率**采集层已审计无缺口**（`notes/lightmem-efficiency-audit.md`：build/answer/judge
  三角色都记真实 api_usage）。本卡只做**聚合层**——per-run 成本报告原语：合并
  prediction+evaluation 两个效率 store + ohmygpt 计价（价格值用户后填）+ 角色/
  token-source/track 拆分。**纯离线、与 M0-1b 文件不重叠**（M0-eff 动 `analysis/`+
  `configs/pricing/`；M0-1b 动 reader/评测 wiring）。是 ws05 成本表的单元格来源
  （本卡只做 per-run 原语，不做 5×10 组装=ws05）。
- **M0-2**：LightMem **longmemeval** native profile（补 audit 待抽取项：
  embedding + answer/judge params）+ 测试。
- **M0-3（架构师跑）**：真实 unified smoke，measure-first——先 LightMem×
  LoCoMo 一个，读效率 artifact 成本，再决定 $0.7 够不够铺开其余 4 +
  native 两格。
- **M0-4**：成本观测汇总 + method-frozen-v1 记录。

## 5. 验收门（每批架构师亲自）
- 定向测试 + 全量回归（只升不降，当前基线 1069）+ compileall。
- config-track=unified 时字节级零回归（现有测试全绿）。
- native profile 的 answer/judge prompt 与 method 仓库**逐字核**（运行时或
  AST）；locomo answer = ANSWER_PROMPT（Task1 已裁决 §3.5，StructMem 不接）。
- run_id/artifact 路径 track 维度断言。
- fixture 经真实序列化（D4/D5）。

## 6. 当前断点
- 2026-07-12：spec+plan+audit+标准清单+**双轨政策 `dual-track-config-policy.md`**
  落盘。首 actor 卡 M0-1 已派 → **Task1 停工**（ANSWER_PROMPT vs StructMem）→
  **架构师裁决**：native locomo answer=ANSWER_PROMPT、StructMem 不接（§3.5）；
  **actor 可解冻续 Task2-4**。运行时 config-track 机制（M0-1b）待架构师设计。
  真实 smoke 待 M0-3。执行者 = 用户轮换 actor 池；架构师验收 + 跑真实 smoke。

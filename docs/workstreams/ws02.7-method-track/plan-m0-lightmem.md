# M0 spec+plan：Method Track 双轨接入 + LightMem 首接

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

### 3.2 两轨差异与记忆复用（关键裁定）
差异 = answer 配置 + judge 配置 +（可能）embedding。
- **embedding 相同**（如 LightMem×locomo 两轨都 all-MiniLM）→ 记忆构建一次、
  两轨复用检索、只重跑 answer+judge。
- **embedding 不同**（如 Mem0 native=OpenAI embedding vs unified=all-MiniLM）
  → 两次独立构建（成本 ×2）。切 embedding = 整轮重建，非答题期廉价 swap。

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

## 4. 施工分批（actor 卡逐个开，架构师逐批验收）

- **M0-1（首卡，已开 actor-prompt-m0-lightmem-config.md）**：config-track
  机制骨架（track 解析 + track-aware 路径，unified 默认零回归）+ LightMem
  **locomo** native profile（answer/judge/embedding 一手抄 + gate 到
  (lightmem,locomo)）+ 离线测试。**不碰真实 API**。
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
  AST）；locomo ANSWER_PROMPT vs StructMem 变体核实际调用点（原则 #2）。
- run_id/artifact 路径 track 维度断言。
- fixture 经真实序列化（D4/D5）。

## 6. 当前断点
- 2026-07-12：spec+plan+audit+标准清单落盘，首 actor 卡已开待用户派发。
  **未开始实现**。执行者 = 用户轮换 actor 池；架构师验收 + 跑真实 smoke。

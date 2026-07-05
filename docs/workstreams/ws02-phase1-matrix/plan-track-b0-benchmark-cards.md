---
id: ws02
doc: plan (Track B0)
status: approved
created: 2026-07-06
---
# ws02 Track B0 实施计划：benchmark 调研卡片补全（5/5）

执行者：Codex。目的：把 benchmark 侧调研资产补齐到 5 张统一深度的卡片。
LoCoMo 和 LongMemEval 虽已接入代码，但**从未有过调研卡片**——它们的评测知识
散落在 adapter 实现和旧 handoff 里；HaluMem/BEAM/MemBench 三张卡片是旧模板
产出，缺协议设计需要的两节。与 Track A2 并列，共同支撑架构师的粒度需求矩阵。

## 施工纪律

1. 零真实 API；结论必须有 paper/code/dataset 三方交叉验证，冲突记入"未确认项"。
2. 使用 `/Users/wz/.codex/skills/benchmark-survey/SKILL.md`（2026-07-05 已更新：
   输出路径 `docs/survey/benchmarks/`、第 5/6 节协议中立口径、成本画像要求）。
3. 每完成一张立即 commit（`docs: add locomo survey card` 等）。
4. 遇模板与本 plan 冲突以本 plan 为准；遇 plan 未覆盖情况停工写断点。

## 任务清单

### 新做两张（完整 7 节，按 skill 模板）

- [ ] `docs/survey/benchmarks/LoCoMo.md`。材料：
  `third_party/benchmarks/` 下 LoCoMo 官方仓库、`data/locomo/locomo10.json`、
  论文 PDF（若 third_party 内无 PDF，停工问用户要）。额外要求：
  - 我们已有实现可作"用法实证"：`src/memory_benchmark/benchmark_adapters/`
    的 LoCoMo adapter 与 4 个 method 的官方 LoCoMo eval 脚本；卡片中注明
    "官方口径 vs 我们当前实现"的差异（如 category 5 adversarial 处理、
    smoke 裁剪语义）。
  - 重点写清：session/turn 结构与时间字段、双真人说话者形态、evidence 标注、
    F1 与 LLM judge 两套 metric 的官方定义、每 method 官方 prompt 差异。
- [ ] `docs/survey/benchmarks/LongMemEval.md`。材料：官方仓库、
  `data/longmemeval/`（s_cleaned/m_cleaned variants）、论文 PDF。额外要求：
  - 写清 haystack session 结构、`question_time` 语义、variant 差异、
    500 instance 规模与成本含义（对照我们 1-conv cost pilot 实测）、
    官方 yes/no judge 流程（我们已按 LightMem 流程实现，注明对齐情况）。

### 增补三张（不重写，只补节）

- [ ] `HaluMem.md`、`BEAM.md`、`MemBench.md` 各做一次增补 pass：对照更新后
  skill 的第 5/6 节要求检查，若缺则补：
  - **原生粒度与喂入方式**：数据的自然单位（message/turn/session/operation/
    trajectory）、官方评测按什么顺序什么粒度喂给被测系统、需要哪些边界信号。
  - **成本画像**：官方流程每 sample 的 LLM/embedding/judge 调用量级。
  增补内容追加为独立小节并标注"2026-07-06 增补"，不改动原有结论。

### 收尾

- [ ] 在 `docs/survey/benchmarks/README.md` 索引中登记两张新卡片。
- [ ] 更新 ws02 README 断点，通知架构师做粒度矩阵。

## 验收

- `ls docs/survey/benchmarks/*.md` 含 LoCoMo、LongMemEval 且 5 张目标 benchmark
  卡片全部具备"原生粒度与喂入方式 + 成本画像"内容。
- 新卡片每个结论有 文件/行号 或 dataset 字段证据；paper/code/dataset 冲突
  如实记录。
- 全程零 API；`git status` 干净（逐张 commit）。

## 明确不做

- 不改 adapter 代码；不重写三张已有卡片的既有结论；
- 不调研 Phase 1 之外的 benchmark（PersonaMem/MemoryArena 卡片已存在，不动）。

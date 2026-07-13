# BEAM 接入实例（A1-A8 逐项）

> 判据模板：`../method-integration-checklist.md` §A；勾选总表：`../integration-status.md`。
> **frozen-v1（2026-07-11）**；证据主库 =
> `docs/workstreams/ws02.6-first-smoke-hardening/notes/beam-frozen-v1.md`。

## A1-A8 逐项

- **A1 来源锁 ✅**：repo `mohammadtavakoli78/BEAM`；**代码 commit `3e12035` 已锁**
  （五 benchmark 中唯一可锁 commit 的快照）；arXiv 2510.27246；license 三层
  （code MIT / dataset CC-BY-SA-4.0 / paper CC-BY-4.0）；17 数据文件 SHA-256 已锁；
  HF revision 待溯。
- **A2 数据契约 ✅**：100 conv / 2,000 题 / 10 类 × 2 题；`probing_questions` 须
  ast.literal_eval；**10M variant 异构**：顶层 chat=list[plan-dict] 按官方顺序展开
  （session id `pN:sM`）；evidence 三形态 10,534 原子 + 1 个 `'--'` + 1M 4 conv
  重复 id（any-match + 歧义计数裁决）。
- **A3 公私边界 ✅**：gold 字段进全局私有键黑名单（core/validators.py）；CLEAN。
- **A4 canonical/GC-1 ✅**：evidence 映射到公开 turn 空间（内容级对照验证
  raw 28→s1:t29）。
- **A5 prompt/metric parity ✅**：官方 `answer_generation_for_rag` 逐字；
  **官方有效评测面**（逐调用点核实）：9 类纯 rubric judge + event_ordering 的
  judge+τ_b×F1；嵌入/BLEU/ROUGE/fact-level 均为死代码不接；`beam-rubric-judge`
  主分 float + `llm_judge_score_official_int` 对照（官方 int() 截断实锤）；
  temperature=0 有官方一手出处（answer_generation.py:303-307）。
- **A6 smoke/resume ✅**：**双结构认证** = `--variant 100k smoke` + `--variant 10m
  smoke` 两次独立 run 均绿（variant=独立 run 身份，不扩 selector）；500k/1m 同构
  不进认证；formal conversation 级 checkpoint。
- **A7 artifact/efficiency ✅**：int 截断对照字段随 scores artifact 落盘。
- **A8 冻结门 ✅**：全量 1025 passed 时点通过。

## 对 method 接入的含义

1. **smoke 是两次 run**：100k + 10m 各一次才算 BEAM smoke 认证——排 smoke 计划时
   BEAM 占两个 run 名额（5×10 流通计划里别漏）。
2. **与论文对比必须用 `llm_judge_score_official_int`**（主分 float 是已声明偏差）。
3. event_ordering 类走 judge+τ_b×F1 特殊通道，category_breakdown 里单独看。
4. recall：turn provenance any-match；当前全 method provenance=none → N/A。
5. **native 格**：仅 Mem0。其余 method 在 BEAM 全部单轨 collapse。
6. 10M full 成本未测——成本探针阶段 BEAM 10M 单独立项，不并入常规外推。
7. **环境依赖**：BEAM 测试需 `datasets` 模块，缺失 = 18 项环境性 fail 非回归
   （2026-07-13 判例，勿误判）。

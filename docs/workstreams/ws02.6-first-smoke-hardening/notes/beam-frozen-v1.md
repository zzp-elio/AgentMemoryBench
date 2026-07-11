# BEAM benchmark frozen-v1

冻结日期：2026-07-11
冻结范围：Phase 1 BEAM conversation-QA benchmark 侧（B4，含 10M variant）
状态：通过架构师验收；未调用真实 API

## 1. 冻结结论

BEAM 已具备可复验的官方来源身份（含代码 commit）、四 variant 真实数据
契约（10M 异构结构已接纳）、官方 answer/rubric-judge/equivalence 三
prompt 逐字 parity、双结构路径覆盖 smoke 与 conversation 级 resume。
可作为 Method Track 的稳定测量仪器。不授权真实 API 运行。

## 2. 来源锁

- 官方仓库 `https://github.com/mohammadtavakoli78/BEAM`（一手来源
  `.git/config` + 论文 PDF）；**代码 commit `3e12035`（2026-02-02）已锁**
  ——五个 benchmark 中首个可锁 commit 的快照；arXiv 2510.27246；license
  三层（code MIT / dataset CC-BY-SA-4.0 / paper CC-BY-4.0，均带出处）
- 数据：`data/BEAM/beam_dataset`（100K/500K/1M）+ `beam_10M_dataset`
  （10M），17 文件逐一 SHA-256（架构师抽验一致）；HF revision 来源待溯
  （如实记录）；**框架只加载 `data/BEAM/`，third_party 数据不加载**
  （用户 2026-07-11 指令）
- 逐文件身份：[beam-source-lock.json](beam-source-lock.json)

## 3. 数据与映射（详见 [beam-e1-audit.md](beam-e1-audit.md) 与 datasets 契约卡）

100 conv / 2,000 题 / 10 类 × 2 题；`probing_questions` 须
ast.literal_eval；10M 顶层 chat = list[plan-dict] 按官方顺序展开
（session id `pN:sM`）；evidence 三形态 10,534 原子、1 个 `'--'`、1M
4 conv 重复 id（any-match + 歧义计数裁决）；全部 gold 字段进全局私有键
黑名单（core/validators.py）。

## 4. Smoke 与 resume

- **双结构认证**：`--variant 100k smoke` + `--variant 10m smoke` 两次
  独立 run 均绿 = BEAM smoke 认证（架构师裁决：不扩展 variant selector，
  variant=独立 run 身份）；500k/1m 同构不进认证
- 每 run 1 conv × 1 round × 1 题实际作答（数据集带 20 题，runner smoke
  预算裁 1——语义等效，e2e 已断言）；smoke 禁 resume/retry-failed；
  formal 为 conversation 级

## 5. Answer 与 metric

- unified prompt：官方 `answer_generation_for_rag` 逐字；answer LLM
  temperature=0（官方一手出处 `answer_generation.py:303-307`）、
  role=user、max_tokens=None（框架决定，如实标注）
- **官方有效评测面**（逐调用点核实）：9 类纯 rubric judge +
  event_ordering 的 judge+τ_b×F1（LLM alignment）；嵌入/BLEU/ROUGE/
  fact-level 均为分发链外死代码，不接入
- `beam-rubric-judge`：judge + equivalence 双 prompt 逐字（运行时读
  官方文件断言 + 架构师独立比对）；**主分 float + 
  `llm_judge_score_official_int` 对照**（官方 int() 截断实锤：judge
  prompt 明定 0.5 Partial Compliance 档，截断行号 357/385/454/483/512/
  541）；event_ordering 有效行为 = split("\n") + LLM 贪心 1-1 + τ×F1
  （extract_facts 死代码 quirk 留档）；category_breakdown 按 10 类分报
- `beam-recall`：conditional（turn provenance 公开空间 any-match；
  未声明/abstention N/A；`'--'`/越界 unmatched 计数；session 粒度显式
  报错不静默）
- `f1`：framework 补充指标（非官方）

## 6. 实现与验收证据

Actor commits（E1-E4 codex+GPT-5.6，E5 cc+MiniMax M3）：

- `56ee346` E1 source lock + 剖面 + Q1/Q2 判定（一次 Q2 停工裁决；架构
  师补锁 commit + 收编提前实现的 evidence 映射【内容级对照验证】）
- `1ba7bb3` E2 10M variant + 声明式 policy + 全局私有键加固（一次预埋
  断点停工 → 双结构认证裁决；零修正）
- `08a1299` E3 unified prompt parity + answer 归一（零修正）
- `772602d` E4 judge/equivalence parity + τ×F1 + recall（一次口径停工
  【架构师卡错：签名默认值≠实际调用点】→ 有效评测面裁决；零修正）
- `ecff84d` E5 双结构离线全链路（重写 pre-E1 legacy 测试；零修正）

架构师验收（全部亲自复跑）：

```text
E1 定向 50 + 全量 1002；E2 定向 171 + 全量 1007；E3 定向 126 +
全量 1017；E4 定向 59 + 全量 1026；E5 精确复验 6 passed
冻结门：全量 1025 passed（E5 重写吸收 legacy 测试净 -1）+ compileall
真实数据验证：10m 展开（100 sessions/plan 顺序/pN:sM 唯一/19,895
turns）、evidence 映射内容级对照（raw 28→s1:t29）、abstention 空
evidence、重复 conv 歧义计数 8/3、双 smoke 形态、'--' 保留
公开泄漏扫描 CLEAN；全程零真实 API
```

三次停工全部停对（Q2 反例、预埋断点、E4 卡口径错——其中一次纠正的是
架构师自己的错误）。

## 7. 已知限制与解冻规则

1. **int 截断双轨**：主分 float（prompt 意图）为已声明偏差；与论文数字
   对比必须用 `llm_judge_score_official_int`。
2. judge/equivalence 模型按项目基座 gpt-4o-mini，与官方评测所用模型的
   差异在真实运行报告中声明。
3. `'--'` 非法 gold 原子 1 个、1M 4 conv 重复 id：官方数据事实，如实
   计数不修数据。
4. session 粒度 recall 未实现（gold 为 turn 级官方字段；`sN` 前缀派生
   留 Method Track 按需扩展）。
5. 10M 只验证展开与 smoke 切片，full 成本未测；HF revision 来源待溯。
6. 新一手证据推翻本记录 → `frozen-v2` 版本化 + 影响分析 + 重跑验收门；
   不得在 method adapter 内加 BEAM 专用补丁。

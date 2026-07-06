---
id: ws02.1
parent: ws02
doc: plan
status: approved
created: 2026-07-07
---
# ws02.1 实施计划：MemBench Adapter（spec 已获用户批准 2026-07-07）

执行者：Codex。依据：[spec.md](spec.md)（approved）、协议 v3、
[MemBench 卡片](../../survey/benchmarks/MemBench.md)。

## 施工纪律

ws01/M-A/M-B 全部纪律照旧（TDD、每 task 一 commit、停工写断点、零真实 API、
不改 third_party、中文 docstring、基线 **771 passed** 不得跌破）。
prompt 文本必须从官方源码摘录并注明行号，不许改写措辞。

## T1 Loader 与数据映射

- [ ] 新 `src/memory_benchmark/benchmark_adapters/membench.py`：按 spec §2/§3
  实现 data2test 展开（question_type → scenario → trajectory）；
  conversation_id 构造规则、tid 全局唯一断言（冲突 fail-fast）；单 Session；
  PS dict step → 官方合并文本 `'user': ...; 'agent': ...`（metadata 留
  ps_user/ps_agent 分字段）、OS string step 原样；turn_id=str(step_id) 1-based；
  QA 公开/私有切分照 spec §2.3 表。
- [ ] 测试：迷你合成 fixture（复刻 §2.3 JSON 结构，含 PS/OS 各一、含
  target_step_id）+ canonical 抽样测试（读真实 `data/membench/.../0-10k` 一个
  文件首条 trajectory，核对 step_id 与 target_step_id 指向内容对齐——
  spec §8 off-by-one 风险的实证测试）+ 私有键隔离测试。
- 验收：`uv run pytest tests/test_membench_conversation_adapter.py -q` 全绿。

## T2 Registry 注册与 variant/smoke

- [ ] benchmark registry 注册 `membench`：variant `0_10k`（默认，4 主文件）/
  `100k`（4 主文件）；根目录 20 条补充样本排除；`prediction_enabled=True`。
- [ ] smoke 裁剪：每文件前 N 条 trajectory（`--conversations N`），不裁
  message_list；formal 不裁剪。
- 验收：registry/smoke focused 测试全绿；`uv run memory-benchmark predict
  smoke --help` 可见 membench 选项（离线断言 choices 列表即可）。

## T3 Unified reader（本项目第一条 unified prompt 链路）

- [ ] 新 benchmark 级 prompt profile `membench_instruction_first_v1`：
  文本照抄官方 `third_party/benchmarks/Membench-main/benchmark/MembenchAgent.py`
  的 INSTRUCTION_FIRST 与 question/time/choices 拼接形态（plan 执行时注明
  精确行号）；输入 = `RetrievalResult.formatted_memory` + question +
  question_time + choices。
- [ ] runner/registered service：membench 声明 `prompt_track="unified"`——
  reader 不再取 `prompt_messages`，改用 formatted_memory + 上述 profile 构造
  messages；manifest `prompt_track` 记 `unified`。实现为**最小机制**：
  benchmark registration 可携带 unified prompt builder，未携带的 benchmark
  维持现状 native 路径，不要顺手改 LoCoMo/LongMemEval。
- [ ] 答案解析：输出提取 A/B/C/D（容忍大小写/句号/前后缀文本）；解析失败记
  prediction=`invalid_choice`（计错不重试）。
- 验收：reader/prompt focused 测试全绿（含解析容错表格测试）；
  fake provider 下 membench answer prompt 的 messages 结构断言。

## T4 Evaluator

- [ ] `membench_choice_accuracy`：deterministic exact match
  （prediction letter == ground_truth），`requires_api=False`；复用
  `category_breakdown` 按 question_type 聚合；evaluator registry 注册。
- 验收：evaluator focused 测试全绿（正确/错误/invalid_choice 三态 +
  category 聚合断言）。

## T5 Fake 全链路

- [ ] Mock v3 provider（turn 粒度）跑通 membench registered prediction →
  evaluation：artifact 齐全（predictions/answer_prompts 含 formatted_memory/
  private labels/summary + `membench_choice_accuracy` summary）；
  manifest `prompt_track=unified`、`protocol_version=v3`。
- [ ] resume 语义：trajectory 级 completed/pending 回归测试（复用既有机制，
  membench 无特殊 resume 需求）。
- 验收：端到端 fake 测试全绿；`uv run pytest -q` ≥771；compileall 通过。

## T6 收尾

- [ ] 更新 ws02.1 README 断点与勾选、ws02 README 矩阵现状表（MemBench 列
  标注"adapter 就绪待 smoke"）、`docs/reference/method-interface-inventory.md`
  不涉及（method 侧无改动）。
- 验收：`git status` 干净；全部 commit 按 task 切分。

## 明确不做

- 不实现 evidence recall metric（turn_id 落盘即可）；不做 capacity/efficiency
  模式；不动 LoCoMo/LongMemEval 的 prompt_track；不跑真实 API；
  根目录 20 条补充样本不进 loader。

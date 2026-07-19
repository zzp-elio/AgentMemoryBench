# Dataset 异常情况索引

本目录是 Phase 1 dataset **详细异常账**：记录异常的真实位置、为什么判为异常、框架如何
处置，以及各 method 是否还需要差分适配。它不替代 benchmark/dataset/workflow 三联页：三联页
保留稳定摘要，本目录保存可复核例子与处置矩阵。

## 1. 每份异常账必须包含什么

1. **数据身份**：canonical path、SHA-256/source revision、复核日期；数据身份改变后旧计数自动
   失效，不能直接沿用。
2. **稳定位置**：优先使用 `sample/question/session/turn` 的语义坐标，例如
   `conv-26 / qa[37] / evidence[0]` 或 `conv-26 / session_1 / D1:5`。当前 JSON 行号只作辅助，
   因为重新格式化文件会让行号漂移。
3. **异常理由**：区分真正的 schema/标注错误、合法但稀有的 edge case、数据能力限制，以及
   upstream script 与当前 release 的漂移。不能因为“少见”就擅自判错。
4. **统一处置**：明确 canonical adapter 是保留、忽略、fail-fast 还是映射为 unmatched；
   evaluator 的分母、N/A 与披露行为也必须写清。
5. **method 差分**：只记录 benchmark 层不能完全吸收的差异。已被 canonical/evaluator 层处理的
   异常写“无 method 特判”，不向十个 integration 页复制整张异常表。
6. **回归锚**：给出锁定事实/行为的测试或 source-lock；没有测试时明确标为 pending，不拿文档
   自证正确。

## 2. 红线

- 不改原始 dataset 来“修好”异常，除非 owner 发布新版本并重新锁 source identity。
- gold answer/evidence 异常只在 evaluator-private 通道处理，绝不可因此向 method 暴露 gold。
- 不把 malformed token 猜拆、纠错或静默删除；任何 normalization 都必须说明与官方 raw
  implementation 的分叉。
- 不只写聊天观察或不稳定行号；也不把未经架构师复核的用户/actor 草稿冒充 canonical 结论。

## 3. Phase 1 状态

| Dataset | 详细异常账 | 状态 | 下一次重开条件 |
| --- | --- | --- | --- |
| LoCoMo | [locomo.md](locomo.md) | dataset 事实 **verified**；LightMem caption v6 差分已强验收（2026-07-17） | source hash、gold group contract、caption renderer 或 smoke policy 改变 |
| LongMemEval | [longmemeval.md](longmemeval.md) | dataset 事实 **verified**（2026-07-19）；S/M evidence-id 集合等价但 124 题 raw 顺序不同，草稿 role 根因已降格 | source hash、canonical role/session-id、gold group、answer builder 或 retrieval evaluator 改变；或 owner 给出新一手反证 |
| HaluMem | — | pending | LightMem 压到 HaluMem 时建立 |
| BEAM | [beam.md](beam.md) | dataset 事实 **verified**（2026-07-19）；LightMem pair 差量已强验收，100K/10M 真实 B11 待跑 | Arrow/source lock、10M 展开、positional id/gold group、pair 或时间契约变化 |
| MemBench | [membench.md](membench.md) | dataset 事实 **verified**（2026-07-19）；LightMem pair/current-v7 `0_10k` W1/W2 与 100k missing-time zero-extraction 哨兵均已强验收 | 任一文件 hash、step→child/gold group、timestamp/parser、pair aggregator 或 answer prompt 改变 |

权威施工状态仍看对应 workstream README；本页只回答“异常事实已经调查到什么程度”。

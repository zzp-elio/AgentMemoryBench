# Actor 卡 M0-4：MemBench / BEAM × LightMem 离线兼容核查

> 派发日 2026-07-13。自包含卡。**纯取证卡：只允许新建
> `docs/workstreams/ws02.7-method-track/notes/m0-4-membench-beam-lightmem-compat.md`
> 一个文件**；禁改任何代码；禁真实 API（全部核查必须零成本离线完成）。

## 0. Git 纪律
独立 worktree + 分支 `actor/m0-4-membench-beam-compat`（用户建）。只 commit 本
分支、禁 push、禁碰其他分支。worktree 有独立 .venv，先 `uv sync`；worktree 不含
gitignored 资产（data/ 若缺按下方路径从主树读，只读不拷）。引用的每个行号现场
打开文件核实，禁编造。

## 1. 背景

LightMem 深耕制（一个 method 查透 + 5 benchmark 全 smoke 才进下一个）。当前
locomo 格五件套全齐、lme 格差⑤；下两格 = membench、beam。真实 smoke 要花钱，
所以先做**离线兼容核查**：确认数据形态进 LightMem adapter 全链路不炸、无静默
失真，架构师验收后才给用户 smoke 命令。两 benchmark 已 frozen-v1，特殊形态
已有档案——本卡是"形态 × LightMem ingest/retrieve 路径"的交叉核查。

## 2. 必读档案（先读再查）
- `docs/reference/integration/membench.md`（4 源文件形态分叉、1 trajectory=1conv=1q、
  第三人称 turn）
- `docs/reference/integration/beam.md`（100k/10m 双结构、10m chat=list[plan-dict]、
  smoke=两次 run）
- `docs/reference/integration/lightmem.md` §0/§0.5（adapter 调用面 + API 契约）
- adapter 本体：`src/memory_benchmark/methods/lightmem_adapter.py`

## 3. 施工内容（逐项硬答案）

产出 note 按下列问题组织，每问一节，结论行加粗：

1. **MemBench 4 源文件 × ingest 路径**：4 类源文件的 turn 文本形态（第三人称
   str、有无 speaker/role/时间戳）逐一列出（`benchmark_adapters/membench.py`
   一手锚 + `data/` 真实数据抽样），对照 LightMem adapter ingest 期望的输入
   （messages 的 role/time_stamp/speaker_id 字段怎么构造、缺省时落什么值）。
   **硬答案：每类源文件进 adapter 会不会炸 / 会不会静默失真（如全部 turn 同
   一时间戳、speaker 全 unknown）？**
2. **BEAM 100k/10m 双结构 × ingest 路径**：同上口径。特别核：10m 的
   plan-dict 展开后 turn 数量级、LightMem 分段/缓冲逻辑（segment/buffer 相关
   超参）在超长 conversation 下的离线行为（只析代码路径与数量级，不跑 LLM）。
   **硬答案：两 variant 各自会不会触发 adapter 或 LightMem 离线层的边界条件
   （空 turn、超长单 turn、消息数上限）？**
3. **时间戳覆盖（B4 前提）**：两 benchmark 的 dataset 有没有真实时间戳？没有
   的话 adapter 落的缺省时间戳是什么、formatted_memory 里会呈现成什么样？
   **硬答案：membench/beam 格的 B4 时间戳项应记"有/无/伪时间戳"哪种？**
4. **retrieve/formatted_memory 路径**：两 benchmark 的 question 形态（选择题
   normalize 等）与 LightMem 检索返回拼装是否有格式冲突（如 membench 的
   choice normalize 对 formatted_memory 无要求即写明"无冲突"）。
5. **可离线验证的部分直接验证**：能用现有测试设施（mock LLM、pytest 已有
   fixture、`build_turn_events`/GranularityAggregator 单元级调用）零成本跑通的
   形态转换，写最小验证脚本跑一次，结果贴进 note（脚本内容贴 note 不落库）。
6. **blocker 清单**：若有致炸/失真项，列"现象 + 根因锚 + 修复建议"（**不施工**，
   架构师裁决）。若全绿，明确写"**可以进入真实 smoke**"。

## 4. 硬规则
- 每个陈述带 `文件:行号`；数据形态结论必须来自 `data/` 真实文件抽样（命令与
  样本贴 note），不许从文档转抄当一手。
- 禁真实 API；禁改 src/tests/third_party；只新建那一个 note 文件。

## 5. 停工条件
- 发现 membench/beam adapter 与 frozen-v1 档案描述不符（形态档案过期）→ 停工，
  在施工报告列出出入，等架构师。

## 施工报告（actor 填写）
（待填）

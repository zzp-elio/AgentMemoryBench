# Actor 卡：HaluMem operation runner top-10 与 clean retry R1

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；按本卡已经裁定的共享 runner 语义施工，
遇到停工条件交回。actor 可自行组织 subagent，但不得扩大 scope；主 actor 对最终 diff、测试
和报告负责。

## 0. 这张卡解决什么

Mem0 × HaluMem 联合审计发现两个 method-neutral 的 operation-level 缺口：

1. HaluMem update probe 构造 `RetrievalQuery(top_k=10)`，但 provider 可按自己的产品 profile
   over-retrieve（当前 Mem0=20、LightMem 可更多），runner 把所有返回 memory 都写进
   `memories_from_system`，导致官方 update scorer 实际看见超过 10 条；
2. CLI 已为内置 method 绑定 `clean_failed_ingest_conversation`，却只传给标准 prediction runner。
   operation runner 中途失败不写 `failed_ingest`，resume 会从 session 1 重放并可能重复写长期
   memory。

本卡在共享 HaluMem operation runner 修复 scorer 输入与失败状态机；**不改 Mem0/LightMem/
任何 method adapter，不改变 provider 底层 ANN/profile top_k，不改 evaluator prompt 或公式**。
权威裁决：
`docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
mem0-joint-ruling.md` §4。

## 1. 隔离环境与必读顺序

建议 worktree：`/Users/wz/Desktop/mb-actor-halumem-operation-r1`
建议 branch：`actor/halumem-operation-retry-topk-r1`

先记录 `git rev-parse --short HEAD`，然后按顺序只读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/README.md`
4. `docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
   mem0-joint-ruling.md` §4
5. `docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
   mem0-halumem-delta-preflight.md` §6
6. `docs/survey/benchmarks/HaluMem.md` 中 update top-10 / QA top-20 的一手锚
7. `docs/reference/actor-handbook.md`
8. 本卡允许清单内生产代码与测试

不得读 `.env`、调用真实 API、下载模型、重扫 HaluMem 数据、写 outputs 或改第三方源码。测试
用 hermetic fake provider；若既有 registered 测试需要 gitignored data，可只读软链并披露，
不得暂存。

## 2. 已裁 top-k 语义

1. 定义一个语义清楚的 module constant（值 10），同时用于：
   - update probe 的 `RetrievalQuery.top_k`；
   - 写 `memories_from_system` 前的有序截断。
   禁止保留两处裸 `10` 让它们以后漂移。
2. `retrieval.items is not None` 时，按 provider 返回顺序取前 10 个 `item.content`；真实 0 hit
   的 `items=()` 仍为 `[]`，不能回落到 formatted sentinel。
3. 兼容 `items is None` 的 provider 时，沿用现有 formatted-memory 非空行路径，但最多取前 10
   个条目；不要解析/重排/去重内容。
4. QA 的 `RetrievalQuery.top_k=20` 与 formatted memory 完全不变；session extraction report
   也不受 cap 影响。
5. 不把 Mem0/LightMem adapter 改为读取 `query.top_k`，不改 TOML。这里对齐的是**官方 update
   scorer 可见输入 top-10**，不是谎称 provider 底层只检索 10。
6. update artifact 必须显式记录本次 scorer limit（稳定键名如
   `retrieval_query_top_k: 10`）；若记录 provider 返回数，只能用公开 item/list 的真实计数，
   不能从 metadata 猜。新增字段不得含 gold/private 信息。
7. `formatted_memory` 可保留 provider 完整 readout 作审计；evaluator 只消费截断后的
   `memories_from_system`。测试要锁住两者用途，防未来误把完整 formatted text送进 scorer。

## 3. 已裁 clean-failed-ingest 语义

### 3.1 接线

- `run_operation_level_predictions()` 增加与标准 runner 同型的可选
  `clean_failed_ingest_conversation: Callable[[Conversation, dict[str, Any]], None] | None`。
- registered CLI operation-level 分支必须把已经由
  `_bind_clean_failed_ingest_conversation()` 生成的 callback 传入；标准 runner 分支保持原样。
- 复用 `runners.prediction` 已有 `_prepare_clean_failed_ingest_retries()`、
  `_conversation_state_status()`、状态常量和 `_make_public_conversation()` 语义；本项目已经允许
  runner 之间复用 private helper。不要复制出一套名字相近但行为不同的状态机。若为避免 private
  import 确实必须做极小公共化，停工交回，不自行扩大到全 runner 重构。

### 3.2 运行与失败

1. 创建 `RunLogger(paths.logs_dir)`；读完 `conversation_status` 后、生成本轮循环前，调用标准
   clean helper。callback 只能收到 public conversation + failed state，gold/evidence 不可达。
2. `completed` 继续跳过。
3. `failed_ingest` 且 `retry_failed_conversations=False`：跳过，不触发 provider 调用。
4. `failed_ingest` 且显式 retry：
   - 有 clean hook：helper 先清 namespace、写回 pending，然后允许从 session 1 重跑；
   - 无 clean hook：`ConfigurationError` fail-closed，绝不直接重放。
5. `_run_operation_conversation()` 任一阶段抛错时，在 re-raise 前原子写：
   `status="failed_ingest"`、可定位 `stage`、`error_type`、`error`、`ingested=False`，并写一条
   structured log event。这里即使错误发生在 QA/end_conversation 也按 failed_ingest 处理：
   operation artifacts 只在整个 conversation 成功后提交，安全恢复单元是“清 namespace 后整段
   重建”，不是猜哪些 session 已经完成。
6. 失败 conversation 产生的进程内 partial session report/update probe/prediction/prompt list 不得
   写到公开 artifact。已完成的其他 conversation 既有 artifact 不得丢失或重复。
7. clean 成功后状态要保留 `retry_cleaned=True`/previous status 等标准 helper 证据；成功运行再
   写 completed。clean hook 恰调用一次。
8. 不在本卡扩展 operation-level 到多 worker，也不改 `max_workers==1` 硬门。

## 4. 允许修改文件

```text
src/memory_benchmark/runners/operation_level.py
src/memory_benchmark/cli/run_prediction.py
tests/test_operation_level_runner.py
tests/test_halumem_registered_prediction.py
tests/test_prediction_cli.py
docs/workstreams/ws02.7-method-track/branches/method-recertification/mem0/notes/
  halumem-operation-runner-retry-topk-r1-implementation.md
```

允许清单文件无需为凑数修改。禁止改 `runners/prediction.py`、任何 method adapter/registry、
provider protocol、HaluMem evaluator/prompt、TOML、benchmark adapter、integration 稳定页、父/支线
README、联合裁决、third_party/data/models/outputs。

如果现有 shared helper 无法在不改 `prediction.py` 的前提下安全复用，触发停工；不要复制逻辑
绕过边界，也不要偷偷扩大允许清单。

## 5. 必测强反例

### 5.1 top-10

- fake provider 返回 12 个有序 `RetrievedItem`：artifact 的 `memories_from_system` 精确为前 10，
  顺序/重复项不变；`formatted_memory` 仍保留原完整 readout；limit 字段=10。
- 返回恰 10、少于 10、`items=()`、`items=None + 12 个非空 formatted lines` 四个边界。
- QA top_k 仍 20 且 QA readout 不截；extraction report 不截。
- 同一常量同时驱动 query 与 cap，测试不得只断言列表长度而漏 query 实参。

### 5.2 retry

- fake provider 在第二 session 抛错：状态原子落 `failed_ingest`，只写已完成 conversation 的
  artifacts，当前失败 conversation 的 partial report/probe/answer 不落盘。
- `--resume` 默认跳过 failed conversation，provider 零新调用。
- `--resume --retry-failed-conversations` + clean hook：先 clean 恰一次，再从 session 1 重跑，
  最终单份 artifacts/completed；用调用序列断言 clean 严格早于新 ingest。
- 显式 retry 无 hook：在任何新 ingest 前 fail-fast。
- clean callback 收到的 Conversation 不含 gold_answers/private metadata/evidence。
- completed conversation resume 行为保持原样；legacy `status="failed" + ingested=False` 也按
  failed_ingest 兼容。
- CLI registered HaluMem 生产分支有一个断言证明 callback 真正传到 operation runner；不能只
  单测 helper 或用 monkeypatch 跳过调用点。

## 6. 唯一定向自检

```bash
uv run pytest -q \
  tests/test_operation_level_runner.py \
  tests/test_halumem_registered_prediction.py \
  tests/test_prediction_cli.py
```

只跑这一组；不得跑全量 pytest、compileall、真实 API、付费 smoke 或模型下载。必须保留原有
operation-level 顺序、efficiency observation、manifest/resume 与 HaluMem 四 artifact 测试，不能
为通过新增测试删旧断言。

## 7. 停工条件

- 安全实现必须修改 `runners/prediction.py` 或公共协议；
- operation runner 事实上会在 conversation 成功前写 partial artifacts，导致已裁恢复单元不成立；
- clean hook 必须接触 private/gold 数据；
- top-10 截断无法在 provider-neutral 层表达，或 evaluator 实际不消费
  `memories_from_system`；
- 新失败暴露并发、多 variant、method adapter 或 evaluator 的真实缺陷，不能在允许清单内诚实
  修复；
- 15 分钟内无法证明失败状态先于 re-raise 持久化、或 retry 在新 ingest 前完成清理。

停工时把最小复现、源码锚、已完成安全部分和建议裁决写进 implementation note；不要吞异常、
把 failed 标 completed、删断言或默认直接重放。

## 8. 提交与完成报告

- `git diff --check`；add 前后各看 `git status --short`；只显式 add，禁 `-A`/`.`。
- 本地线性单 commit，不 amend、不 push；建议 message：
  `fix(halumem): bound update readout and clean retries`。
- implementation note 必须列出：失败/恢复时序、top-10 的 provider-over-retrieve 边界、公开
  artifact schema变化、定向测试尾行、零 method adapter diff、任何偏差。
- Co-Authored-By 只写可核实真实模型；发生模型切换且无法核实时不猜。
- 按 actor-handbook §4 回报：commit hash、测试尾行原文、实际改动文件、偏差/停工点、subagent
  分工与模型/入口切换。到此停止，等待架构师 full diff 与强验收。

# Actor 卡：Gold Evidence Group Contract M0（私有 qrel 端到端）

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；按本卡裁决实现，遇到停工条件交回。

## 0. 这张卡解决什么

五个 benchmark 的官方 gold unit 不同于公共 `Turn`：MemBench 是 pair-step，BEAM 的坏 raw
id 可能一对多，LoCoMo 是 utterance，LongMemEval 同时有 user-turn/session，HaluMem 的 fact
没有 turn 回指。现有 evaluator 把它们压成扁平字符串列表，会翻倍分母、丢失歧义或误记
空 gold。

本卡建立 **evaluator-only、绝不让 method 看见** 的强类型 gold group v1，并把四个 retrieval
benchmark 的 adapter + evaluator 一次迁到该契约。它只修 qrel 表达与计分，不做 MemBench
canonical role split，不做 RetrievalEvidence M1 资格门，也不改 top-k depth。

## 1. 隔离环境与必读顺序

- worktree：`/Users/wz/Desktop/mb-actor-gold-evidence-m0`
- branch：`actor/gold-evidence-group-m0`
- 基线：用户创建 worktree 时的 main HEAD；先现场记录 `git rev-parse --short HEAD`

只按下列顺序读最小集合：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/README.md`
4. `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/evidence-unit-contract-audit.md`
   的 §0、§2、§4、§5、§6、§8
5. `docs/reference/actor-handbook.md`
6. 本卡点名的一手 adapter/evaluator/test；不要重扫全部 docs 或重新设计方案

## 2. 已裁契约（不得改判）

### 2.1 强类型私有对象

在 `core/entities.py` 增加并从 `core/__init__.py` 导出：

```text
GoldEvidenceGroup
  unit_id: str
  child_ids: tuple[str, ...]
  mapping_status: Literal["mapped", "unmatched"]

GoldEvidenceGroupSet
  provenance_granularity: Literal["turn", "session"]
  unit_kind: str
  groups: tuple[GoldEvidenceGroup, ...]
```

运行时必须 fail-fast，不能只靠 annotation：

- `unit_id`/`unit_kind`/child id 必须是未 strip 前后等价的非空字符串；不做宽松正规化；
- `child_ids`/`groups` 必须是 tuple，元素类型严格；每个 group 的 child ids 不重复，同一
  set 的 unit ids 不重复（`unit_id` 与其同名 canonical child 相等是合法退化）；
- `mapped` 必须至少一个 child；`unmatched` 必须零 child；未知状态拒绝；
- set 的 granularity 只接受 `turn/session`；`groups=()` 合法，表示该 view 确实没有 gold；
- 同一 `GoldAnswerInfo` 内 `(provenance_granularity, unit_kind)` 不得重复。

`GoldAnswerInfo` 新增：

```text
gold_evidence_contract_version: str | None = None
evidence_group_sets: tuple[GoldEvidenceGroupSet, ...] = ()
```

只有 `None` 或严格 `"v1"` 合法；有 group sets 时必须是 v1。旧 `evidence` 字段保留作答案/
历史兼容，但迁移后的 retrieval evaluator **不得再读它或 metadata 扁平列表作为 qrel**。

### 2.2 序列化、隐私与 manifest identity

- `evaluator_private_label_record()`：v1 label 顶层写
  `gold_evidence_contract_version="v1"` 与 JSON list 形态的 `evidence_group_sets`；旧无版本
  label 保持旧 shape，不凭空加字段。
- `BenchmarkRegistration` 增 `gold_evidence_contract_version: str | None`，Phase 1 五家都
  显式声明 `v1`；未知/空白值构造期拒绝。
- `_build_benchmark_policy_manifest()` 把版本放在 `benchmark_policy`，**禁止放 method
  manifest**。它自然参与严格 resume 比较；旧缺 v1 与新 v1 必须 mismatch，不能加入任何
  “任一侧缺失就双删”的兼容集合。
- runner 在创建目录、factory/API 之前交叉校验：registration/benchmark policy 声明 v1 时，
  本次 dataset 每个有公开 question 的 gold label 都必须存在且声明 v1；反之 fail-fast。
- public dataset/question/turn/answer prompt/method payload/manifest 中不得出现 group、unit_id、
  raw qrel。manifest 只出现版本字符串，不出现私有内容。

### 2.3 四家 adapter 的 v1 group

保持 legacy `evidence`/metadata 供历史审计，但权威 qrel 写 group sets：

1. **LoCoMo**
   - turn view：`unit_kind="locomo_utterance"`；官方 evidence dia_id 稳定去重，每个 mapped
     group 的 child 是同名 canonical turn id；无法映射则 unmatched。
   - session view：`unit_kind="locomo_utterance_session_projection"`；每个官方 dia_id 仍是一个
     unit，child 是其 `D<n>` session 前缀；保持现有 session-level 分母语义。
   - 空 evidence 保留空 groups；LoCoMo evaluator 继续同时报告官方 empty=1 与 non-empty mean，
     不把它泛化成其它 benchmark 的政策。
2. **LongMemEval**
   - turn view：`unit_kind="longmemeval_user_target_turn"`；只收 `role=="user" &&
     has_answer is True`，不能再收 54 个 assistant-side target。
   - session view：`unit_kind="longmemeval_answer_session"`；每个官方 answer_session_id 为 unit，
     child 为公开 session id；找不到则 unmatched，不能静默删分母。
   - `_abs` 全部不评分；non-abs 且 turn groups 为空的 51 题在 turn 主路径不评分。以
     `run_retrieval.py` 的 419 为 canonical；470 只保留 upstream 冲突说明。
3. **BEAM**
   - `unit_kind="beam_source_message"`，每个稳定去重后的官方 raw source id 是一个 unit；
   - canonical turn id 继续使用现有 session/position namespace（如 `s1:t1`、
     `p1:s1:t1`），**不得改成 raw id，也不得重命名整套 ID**；raw id 只作私有 `unit_id`；
   - 一个 raw id 映射一个位置 → singleton mapped；1M 四个异常 conversation 的重复 raw id
     → multi-child mapped any-of；找不到（含 10M `'--'`）→ unmatched；`None` → empty groups；
   - 当前全量强反例必须锁：41 个含歧义题、逐题累计 198 个歧义 raw-id 原子；官方不评分
     source ids，metric 永久 `framework_supplementary`。
4. **MemBench（本卡不拆 turn）**
   - `unit_kind="membench_step"`；官方 `target_step_id` 按首次出现顺序去重，一个 step 一个
     group；当前 composite turn 下合法 target 暂退化 singleton child；
   - 两个 `target_step_id == len(message_list)` 建 unmatched group，不能制造不存在的 child；
     空 target → empty groups；
   - 下一卡拆 FirstAgent 后才把同一 unit 改成 `{user_child, assistant_child}`，本卡不得提前
     改 `Turn` 数、role、content、time、smoke limit 或 public id。
5. **HaluMem**
   - gold label/benchmark policy 声明 v1，但 `evidence_group_sets=()`；memory-point fact 无
     turn 回指，禁止合成 qrel。

### 2.4 evaluator 计分

新增一个共享、中文 docstring 的私有 qrel parser/scoring helper，五个 retrieval evaluator
统一调用；不得复制五套宽松解析。每次 evaluate 必须交叉校验：manifest benchmark policy
version、label version、所需 `(granularity, unit_kind)` view 均严格存在；旧无版本或混版
fail-fast。

- recall：每个 mapped group 只要任一 child 出现在 top-k source ids 就命中一次；unmatched
  永远 miss；分母是 group 数，不是 child 数；empty view 按各 benchmark 已裁政策处理。
- rank/NDCG：一个 group 的 rank 是其任一 child 首次出现的最小 rank；同 group 多 child 与
  同 child 重复命中都只计一次；unmatched 留在 ideal gold 数中但永远不命中。
- 保持现有 metric tier、available-k、requested-k、分类聚合与 details；本卡不把 prediction
  top_k=10 改成 30/50，不消费逐题 `RetrievalEvidence`，不声称 stable ranking 已关闭。
- MemBench empty gold 从错误的 1.0 改为 N/A；BEAM empty/abstention N/A；LME 按 419 资格集；
  LoCoMo 的官方 empty=1 历史口径与 non-empty mean 都保留并清楚标注。

## 3. 实施顺序

1. 先写实体 runtime 强反例和 JSON round-trip，再实现实体。
2. 写 private label/公开泄漏/registration/manifest/resume/preflight 强反例，再接序列化身份。
3. 按 LoCoMo → LME → BEAM → MemBench 顺序迁 adapter；每家先锁 group shape，再动 evaluator。
4. 新共享 helper 后迁五 evaluator，删除它们对 legacy 扁平 qrel 的读取。
5. 写施工 note，运行唯一一次定向自检，diff-check，显式 add，commit，不 push。

## 4. 允许修改文件

只允许下列生产路径、对应测试和一份新 note；文件存在但核实无需改时不要制造空白 diff：

```text
src/memory_benchmark/core/entities.py
src/memory_benchmark/core/__init__.py
src/memory_benchmark/storage/artifacts.py
src/memory_benchmark/benchmark_adapters/registry.py
src/memory_benchmark/benchmark_adapters/locomo.py
src/memory_benchmark/benchmark_adapters/longmemeval.py
src/memory_benchmark/benchmark_adapters/beam.py
src/memory_benchmark/benchmark_adapters/membench.py
src/memory_benchmark/benchmark_adapters/halumem.py
src/memory_benchmark/cli/run_prediction.py
src/memory_benchmark/runners/prediction.py
src/memory_benchmark/evaluators/gold_evidence_groups.py
src/memory_benchmark/evaluators/locomo_recall.py
src/memory_benchmark/evaluators/longmemeval_recall.py
src/memory_benchmark/evaluators/longmemeval_retrieval_rank.py
src/memory_benchmark/evaluators/beam_recall.py
src/memory_benchmark/evaluators/membench_recall.py
tests/test_conversation_dataset_validation.py
tests/test_experiment_storage.py
tests/test_benchmark_registry.py
tests/test_prediction_cli.py
tests/test_prediction_runner.py
tests/test_locomo_conversation_adapter.py
tests/test_longmemeval_conversation_adapter.py
tests/test_beam_adapter.py
tests/test_membench_conversation_adapter.py
tests/test_halumem_adapter.py
tests/test_locomo_retrieval_recall.py
tests/test_longmemeval_retrieval_recall.py
tests/test_longmemeval_retrieval_rank.py
tests/test_beam_recall.py
tests/test_membench_retrieval_recall.py
docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/gold-evidence-contract-m0-implementation.md
```

不要改父/支线 README、survey、policy、method adapter/TOML、third_party、outputs、data、
roadmap 或 frozen note。若正确实现必需的生产/测试文件不在清单，立即停工列出路径与理由，
不要自行扩 scope。

## 5. 必测强反例

- 实体：未知 mapping status、空/带首尾空格 id、list 冒充 tuple、mapped 空 child、unmatched
  非空 child、重复 child/unit/view、未知 granularity/version 全拒绝；empty group set 合法。
- 隐私：group/raw unit id 只在 evaluator private label；递归扫描所有 public artifact 与
  method 输入均不存在；manifest 只含 v1 字符串。
- resume/preflight：新 v1 首跑成功；同 v1 resume 成功；旧缺 v1→新 v1、manifest v1/label
  缺失或 bogus、注册 v1/dataset label None 均在 factory/API/目录写入前拒绝。
- MemBench：FirstAgent 当前仍一 step 一 composite turn；重复 target 去重；空=N/A；两个
  OOB 是 unmatched 且记 0，不被删分母。
- BEAM：正常 singleton；synthetic 同 raw id 两位置只算一个 group、任一 child 命中即 1；
  unmatched group 得 0；跨 conversation 相同 raw id 不串线；真实数据可得时锁 41/198，若隔离 worktree
  缺 ignored Arrow，使用主树只读软链后复跑，软链不得暂存。
- LME：assistant `has_answer=True` 不入 turn groups；51 non-abs no-user-target + 30 abs 不进主
  turn 分母；有效 419；session group 独立；group rank 取最小 child rank且不重复增益。
- LoCoMo：turn/session view 独立选择；同一 session 多 evidence 仍按官方 utterance unit 分母；
  empty=1 的 official overall 与 non-empty mean 均保留。
- HaluMem：v1 + zero group sets，不能因此注册/计算 turn recall。

## 6. 唯一定向自检

只跑一次：

```bash
uv run pytest -q \
  tests/test_conversation_dataset_validation.py \
  tests/test_experiment_storage.py \
  tests/test_benchmark_registry.py \
  tests/test_prediction_cli.py \
  tests/test_prediction_runner.py \
  tests/test_locomo_conversation_adapter.py \
  tests/test_longmemeval_conversation_adapter.py \
  tests/test_beam_adapter.py \
  tests/test_membench_conversation_adapter.py \
  tests/test_halumem_adapter.py \
  tests/test_locomo_retrieval_recall.py \
  tests/test_longmemeval_retrieval_recall.py \
  tests/test_longmemeval_retrieval_rank.py \
  tests/test_beam_recall.py \
  tests/test_membench_retrieval_recall.py
```

不跑全量、compileall、真实 API、模型下载或付费 smoke。架构师合入后负责全量门。

## 7. 停工条件

- 一手 source 表明本卡某 benchmark 的 unit/分母裁决错误或无法无损表示；
- BEAM 41/198 与相同数据/相同 adapter 的现场值不一致且 15 分钟内不能解释；
- 要让 group 或 raw qrel 进入公开 payload/method 才能实现；
- 必须先拆 MemBench canonical role、改 provider 协议或改 third_party 才能继续；
- 需要真实 API/下载/清单外文件；定向测试失败且 15 分钟内无法定位。

停工时不要硬绕；把已完成内容、冲突锚和最小二选一写入 implementation note，commit 已完成
的安全部分（若可独立成立）后停止。

## 8. 提交纪律与完成报告

- `git diff --check`；`git status --short` 在 add 前后各过目；只显式 `git add <路径>`，禁
  `-A`/`.`；本地单 commit，不 amend、不 push。
- commit 建议：`feat(evaluation): add gold evidence group contract`
- Co-Authored-By 只写当前会话可核实的真实模型；混合/切换无法核实时不猜。
- 按 actor-handbook §4 回报：commit hash、定向测试尾行原文、实际改动文件、偏差/停工点、
  实质 subagent 分工（如有）和模型切换史（如有）。到此停止，等待架构师强验收。

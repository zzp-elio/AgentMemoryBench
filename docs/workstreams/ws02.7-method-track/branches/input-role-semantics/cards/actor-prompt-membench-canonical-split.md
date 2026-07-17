# Actor 卡：MemBench FirstAgent canonical pair split

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；按本卡裁决实现，遇到停工条件交回。

## 0. 这张卡解决什么

MemBench FirstAgent 的一个官方 `message_list` step 是
`{"user": <原文>, "agent": <原文>}`。框架目前把两侧拼成一个伪 user turn，导致所有 method
收到错误 role；同时官方 `target_step_id` 仍然只指这一个 pair-step，不能因拆成两条 turn
就把 Recall 分母翻倍。

Gold Evidence Group v1 已经在主线支持“一个官方 unit → 多个 canonical child”。本卡只做
这个已解锁的下游闭环：

1. FirstAgent 一个 dict step 拆成真实 user + assistant 两条 canonical `Turn`；
2. 一个 `membench_step` gold group 同时指向这两个 child，any-of 命中但只计一个分母；
3. ThirdAgent string step、时间/place 原文、空时间 noise、越界/空 target 语义保持；
4. smoke 按**源 step**裁剪，不能从 canonical turn 列表中截掉半个 pair；
5. 删除 LightMem 已经过时的 `membench_canonical_split_pending` 运行时判词，为下一门
   RetrievalEvidence M1 提供真实事实。

本卡不实现 RetrievalEvidence M1 evaluator gate，不改 top-k/NDCG/其它 benchmark，不跑真实
API，也不做付费 smoke。

## 1. 隔离环境与必读顺序

- worktree：`/Users/wz/Desktop/mb-actor-membench-canonical-split`
- branch：`actor/membench-canonical-split`
- 基线：用户派发时的 `main` HEAD；先现场记录 `git rev-parse --short HEAD`

若上述 worktree 尚不存在，从主树当前 `main` 新建；若路径/分支已存在但 HEAD 或工作区状态
与本卡不符，立即停工，不 reset/checkout/覆盖未知改动。只在该隔离 worktree 写文件。

只按下列顺序读最小集合：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与最新断点
3. `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/README.md`
4. `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/
   evidence-unit-contract-audit.md` 的 §0、§2.1、§5、§6、§8
5. `docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/
   lightmem-messages-membench-beam-role-audit.md` 的 §1、§3、§4、§9、§10
6. `docs/reference/actor-handbook.md`
7. 本卡点名的生产文件与测试；不要重扫全部 docs/数据或重新设计已裁契约

## 2. 已裁实现契约（不得改判）

### 2.1 canonical Turn 与稳定 ID

把现有 singular `_turn_from_step()` 改成明确返回一到两条 turn 的 helper，并在
`_conversation_from_trajectory()` 中按原 step 顺序 flatten。禁止先拼字符串再二次解析。

对 0 基 `step_index`，令 `n = step_index + 1`：

| 官方 step | canonical child | `turn_id` | `speaker` | `normalized_role` |
|---|---|---|---|---|
| dict.user | user 原文 | `f"{n}:user"` | `"user"` | `"user"` |
| dict.agent | agent 原文 | `f"{n}:assistant"` | `"agent"` | `"assistant"` |
| string | string 原文 | `str(n)` | `"user"` | `"user"` |

理由：`speaker` 保留 MemBench 原始键名，`normalized_role` 才是框架标准角色；ID suffix 使用
canonical role，且 gold 映射通过显式 step→child 表完成，**任何 evaluator/method 都不得靠
解析冒号或 suffix 反推 parent step**。

每个 child metadata 至少保留：

- `source_step_index`（0 基）与 `source_step_number`（1 基）；
- `source_step_role`：dict child 为 `user|agent`，string 为 `observation`；
- dict user child 只保留 `ps_user=<原 user_text>`，不得复制 `ps_agent`；
- dict assistant child 只保留 `ps_agent=<原 agent_text>`，不得复制 `ps_user`。

这样既能逐字节审计，又不会让 peer 原文通过公开 metadata 在另一条 turn 中重复出现。

### 2.2 content、place/time 与缺失时间

- 每个 child `content` 必须与对应源字符串逐字节相同；禁止保留旧
  `"'user': ...; 'agent': ..."` composite，也禁止删除/重写尾部 place/time。
- user 与 assistant **各自**从自己的 content 调 `_membench_turn_time()`；不得沿用旧
  `user_time or agent_time` 跨侧 fallback。
- `source_timestamp_embedded_in_content` 按 child 自身重算：只有自身 content 内解析出完整
  数字 timestamp 时才是严格 JSON boolean `True`；否则 `False`。
- 无时间 noise 保持 `turn_time=None`；session_time 仍为 None；禁止用 peer、QA.time、首个
  有时 turn、wall clock 或递增 synthetic time 填充。
- `build_turn_events()` 后 role、turn id、原文、turn_time 与 marker 必须原样可见。

### 2.3 显式 step→child map 与 gold group

`_conversation_from_trajectory()` 在转换每个源 step 时同时构造稳定、按源顺序排列的
`step_child_ids: tuple[tuple[str, ...], ...]`（或等价强类型局部结构），并把它显式传给 gold
构造。禁止再用 `public_turn_count` 判断官方 step 是否越界；拆分后 canonical turn 数与源 step
数不再相等。

`membench_step` turn view 按以下规则生成：

- `target_step_id` 按首次出现顺序稳定去重；
- 合法 FirstAgent target → 一个 mapped group，`child_ids=("n:user", "n:assistant")`；
- 合法 ThirdAgent target → 一个 mapped singleton group，`child_ids=("n",)`；
- target `>= len(step_child_ids)` → unmatched group、空 child；
- 空 target → empty groups；
- group 分母始终是去重后的官方 step 数，不是 child 数。

现有 `GoldAnswerInfo.evidence=[str(step_id + 1), ...]` 是历史审计字段，**原样保留为 legacy
step alias，不展开 child，也不再宣称它是 canonical turn-id 列表**；权威 qrel 只有 v1 group。
现有 retrieval evaluator 已禁止读 legacy evidence，本卡不得恢复该读取。

Gold Evidence Contract 仍是 `v1`：它从第一天就支持 multi-child，本卡不是 schema 变更。
Dataset 内容 hash 会因 canonical turns 改变，旧预测 run 必须自然 resume mismatch；不得为旧
产物写兼容分支或放宽 manifest。

### 2.4 smoke 必须按源 step 裁剪

现有 `_build_membench_smoke_dataset()` 在 load 后直接 slice canonical turns；拆分后会把
FirstAgent 的 assistant child 截掉。改为按公开 `source_step_index` 选择完整 step：

- FirstAgent source：保留前 `history_limit` 个源 step；dict step 的两个 child 必须同进同出；
- ThirdAgent source：沿用既有口径，保留前 `history_limit * 2` 个 string step；
- standard `history_limit=1` 的四源 smoke：两个 FirstAgent conversation 各 2 turn，两个
  ThirdAgent conversation 各 2 turn，合计 8 个 canonical turns、4 题；
- 不按文件名假设每条 trajectory 的 step shape；选择依据是每条 turn 已落的
  `source_step_index`，不得切出半个 step。

保留 `smoke_original_turn_count/smoke_retained_turn_count` 表示 canonical turn 数；另在
conversation 与 dataset metadata 增加并断言
`smoke_original_step_count/smoke_retained_step_count`，明确两种单位，避免以后再次混用。
选择过程仍只读公开顺序/shape，不读 target/gold。

### 2.5 MemBench recall 的 OOB 诊断

`membench_recall.py` 当前用 answer artifact 的 `public_turn_count` 推断越界；该字段既不是
可靠生产单事实源，拆分后数值也不再等于 source step count。改为以权威 group 为准：

- unmatched `membench_step` group 的整数 `unit_id` 与私有 `target_step_id` 对齐后，计入
  `out_of_bounds_target_step_ids`；
- mapped multi-child 绝不能被误报 OOB；
- OOB 仍留在 gold 分母并永远 miss；empty view 仍 N/A。

禁止把私有 target/group 搬到 answer prompt 或其它公开 artifact 来解决诊断。

### 2.6 LightMem 的直接下游事实

LightMem hybrid normalizer 已经为一个真实 user→assistant pair 把两个 real child ids 稳定
写入 `source_external_ids`；在线 soft profile 不做全库 merge。MemBench 官方 qrel 正好是
pair-step，v1 group 对两个 child 做 any-of。因此 canonical split 后：

- `benchmark_name="membench"` + `online_soft` + `items is not None`（含真实 0-hit 的空 tuple）
  → `semantic_provenance=valid`、`provenance_granularity="turn"`；
- `items is None`（任一 retrieval hit lineage 缺失）→ `n_a/none`，reason 使用现有
  `retrieval_hit_lineage_incomplete` 语义；
- 该 valid 只表示 **MemBench pair-step group 可评**，不声称能判断事实来自 user 还是
  assistant child；LongMemEval/BEAM/HaluMem 判词不变；
- stable ranking 仍 `pending`，本卡不碰 NDCG 资格；
- 删除 `membench_canonical_split_pending` 代码/测试/docstring；`LIGHTMEM_ADAPTER_VERSION`
  从 `conversation-qa-v4` 升到 `conversation-qa-v5`，使这一运行时事实变化进入 method
  manifest/resume identity。

不要在 LightMem 内识别 MemBench composite 文本；canonical role 只能来自 benchmark adapter。

## 3. 实施顺序

1. 先把现有“1 dict step=1 composite turn”的测试改成会在旧实现上失败的 canonical role/
   byte-exact/time/group 强反例。
2. 实现一-to-many step conversion 与显式 step→child map；先让 adapter 测试通过。
3. 修 smoke 的 step-unit 裁剪与 metadata，更新 registry/registered offline probe 期望。
4. 修 MemBench OOB evaluator 诊断，锁 multi-child any-of 与单分母。
5. 更新 LightMem MemBench evidence 判词与版本，只改直接下游；锁 pair ids + items
   available/missing 两态。
6. 写施工 note，运行唯一一次定向自检，diff-check，显式 add，commit，不 push。

## 4. 允许修改文件

只允许下列路径；存在但核实无需改时不要制造空白 diff：

```text
src/memory_benchmark/benchmark_adapters/membench.py
src/memory_benchmark/evaluators/membench_recall.py
src/memory_benchmark/methods/lightmem_adapter.py
tests/test_membench_conversation_adapter.py
tests/test_membench_registered_prediction.py
tests/test_membench_retrieval_recall.py
tests/test_benchmark_registry.py
tests/test_lightmem_adapter.py
tests/test_mem0_adapter.py
docs/workstreams/ws02.7-method-track/branches/input-role-semantics/notes/membench-canonical-split-implementation.md
```

`tests/test_mem0_adapter.py` 只作 content-only timestamp renderer 定向回归；生产 Mem0 代码不应
因 canonical split 修改。不要改父/支线 README、survey、policy/checklist、其它 method、shared
gold entity/helper、runner/manifest、third_party、data、outputs、TOML 或 roadmap。若正确实现
确实需要清单外生产文件，立即停工列出路径与原因，不自行扩 scope。

## 5. 必测强反例

### 5.1 adapter / event stream

- 一个 dict step 恰拆两条，ID/`speaker`/`normalized_role` 严格等于 §2.1；两段 content 与
  `ps_user`/`ps_agent` 分侧逐字节相等，peer 原文不复制进另一 child metadata；旧 composite
  字符串不存在。
- user/agent 时间不同、只一侧有时间、两侧都无时间三态：各 child 只取自身时间，place/time
  原文不删，marker 严格 boolean；QA.time 与 session/peer 不串入。
- event stream 顺序为 user→assistant，`original_turn_id/time/content` 和 turn metadata 保真。
- ThirdAgent string 仍一 step 一 turn、ID=`str(n)`、role=user、singleton group。
- 同一 conversation 混合 dict/string 的合成强反例也不碰撞、不乱序；source step index 可重复
  两次（pair children）但按 step 分组后必须是连续 `0..N-1`。

### 5.2 gold / recall

- 一个 FirstAgent target group 真正含两个 child，不得用两个 singleton 冒充；命中 user-only、
  assistant-only 或两者都命中都只得 1.0。
- 三个 target step 的分母仍为 3；只命中其中一个 step 的任一 child得 `1/3`，不能得 `1/6`。
- 重复 target 稳定去重；OOB unmatched 留分母且 details 正确；empty 仍 N/A。
- legacy evidence 保持一个 step 一个 alias，但 evaluator 测试故意放无关 legacy 值，证明它不
  参与权威计分。

### 5.3 smoke / method boundary

- standard 四源 smoke 实际 ingest 8 turns；两个 FirstAgent 各 user+assistant 完整一 pair，
  两个 ThirdAgent 各 2 turns；4 conversation/4 question 不变。
- step/turn 两套 count metadata 各自准确；任何 history limit 都不产出半 pair。
- LightMem 对 canonical MemBench user+assistant 不解析 content，pair candidate ids 恰为两个
  child ids；`items=()` 为 valid/turn，`items=None` 为 n_a/none；v5 进入 config manifest。
- Mem0 已有“原文含 timestamp 则不加重复 header”测试继续通过；不得为拆分新增 benchmark
  名特判。

## 6. 唯一定向自检

只跑一次：

```bash
uv run pytest -q \
  tests/test_membench_conversation_adapter.py \
  tests/test_membench_registered_prediction.py \
  tests/test_membench_retrieval_recall.py \
  tests/test_benchmark_registry.py \
  tests/test_lightmem_adapter.py \
  tests/test_mem0_adapter.py
```

若隔离 worktree 缺 gitignored `data/`，可建立指向主树 `data/` 的只读本地软链后重跑；软链
不得暂存。不要跑全量、compileall、真实 API、模型下载或付费 smoke；最终全量门由架构师负责。

## 7. 停工条件

- 真实 MemBench 数据表明 FirstAgent dict 缺 user/agent、空侧或同一 trajectory 混合 shape，且
  本卡规则无法无损表达；
- Gold v1 的现行 production helper 无法表达一个 group 两 child，或 evaluator 仍读取 legacy
  evidence 才能工作；
- canonical split 必须修改 shared `Turn`/provider 协议、其它 benchmark 或 third_party；
- LightMem source lineage 现场表明一个 online-soft entry 会跨多个官方 MemBench step 合并，
  从而推翻 §2.6 的 pair-step 可评判词；
- 需要真实 API/下载/清单外文件，或定向测试失败且 15 分钟内无法定位。

停工时不要用兼容 shim 保住旧 composite 测试；把冲突一手锚、已完成内容与最小二选一写进
implementation note，安全部分可独立提交时才 commit，然后停止。

## 8. 提交纪律与完成报告

- `git diff --check`；`git status --short` 在 add 前后各过目；只显式
  `git add <本卡实际改动路径>`，禁 `-A`/`.`；本地单 commit，不 amend、不 push。
- commit 建议：`fix(membench): split first-agent canonical turns`
- Co-Authored-By 只写当前会话可核实的真实模型；切换/混合无法核实时不猜。
- 按 actor-handbook §4 回报：commit hash、定向测试尾行原文、实际改动文件、偏差/停工点、
  实质 subagent 分工（如有）和模型切换史（如有）。到此停止，等待架构师强验收。

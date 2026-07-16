# gold evidence group contract M0 施工笔记

> 日期：2026-07-16。actor：Claude Opus 4.8 起始、DeepSeek V4 Pro 接力。卡：
> [`cards/actor-prompt-gold-evidence-contract-m0.md`](../cards/actor-prompt-gold-evidence-contract-m0.md)
> 零真实 API、零下载。

## 实现摘要

按卡 §3 实施顺序完成，全部生产文件都在 allowlist 内；其中共享 helper
`gold_evidence_groups.py` 已由原卡 §4 显式列入允许清单。

### 1. 实体（§2.1）

`core/entities.py` 新增：

- `GoldEvidenceGroup(unit_id, child_ids, mapping_status)` — frozen dataclass，
  运行期逐字段强反例：str 非空未 strip、tuple 非 list、mapped 至少一 child、
  unmatched 零 child、未知状态拒绝、child/unit id 不重复
- `GoldEvidenceGroupSet(provenance_granularity, unit_kind, groups)` — frozen
  dataclass，只接受 `turn|session`，groups 为 GoldEvidenceGroup tuple
- `GoldAnswerInfo` 增 `gold_evidence_contract_version` 与 `evidence_group_sets`
  — None/v1 严格版本约束、group sets 非空必 v1、同 (granularity, unit_kind)
  view 禁止重复
- 导出常量 `GOLD_EVIDENCE_CONTRACT_V1 = "v1"`，供全仓单事实源引用

### 2. 序列化、注册表、manifest、resume/preflight（§2.2）

- `storage/artifacts.py`：v1 label 顶层写 `gold_evidence_contract_version` 与
  JSON-list 形态的 `evidence_group_sets`；旧无版 label 不变
- `benchmark_adapters/registry.py`：`BenchmarkRegistration` 增
  `gold_evidence_contract_version`（None/"v1"），五家声明全部显式 "v1"
- `cli/run_prediction.py`：`_build_benchmark_policy_manifest` 携带版本；
  版本只进 benchmark_policy/manifest 顶层，**不入 method manifest**
- `runners/prediction.py`：新增 `validate_gold_evidence_contract_alignment`
  交叉校验 registration/benchmark_policy version 与 dataset 每条 gold label 的
  version，任一缺失或非法即 fail-fast（在创建目录、构造 factory、调用 API 之前）
- 隐私：`validate_no_private_keys` 的 `PRIVATE_KEY_NAMES` 已覆盖相关键名（
  `unmatched_gold_id_count`、`ambiguous_gold_id_count`、`evidence_turn_ids` 等已
  在黑名单），新增 group/unit_id 词不会在公开 payload 中出现

### 3. 四家 retrieval adapter group sets（§2.3）

每家在保持 legacy `evidence`/metadata 的同时，为 `GoldAnswerInfo` 新增 v1
`evidence_group_sets`，除 HaluMem（v1+空 group sets）：

| benchmark | turn view unit_kind | session view unit_kind |
|---|---|---|
| LoCoMo | `locomo_utterance` | `locomo_utterance_session_projection` |
| LongMemEval | `longmemeval_user_target_turn` | `longmemeval_answer_session` |
| BEAM | `beam_source_message` | — |
| MemBench | `membench_step` | — |
| HaluMem | — | — |

#### LoCoMo

- turn view：官方 dia_id 稳定去重，mapped child 是同名 canonical turn id；
  不可映射 dia_id 记 unmatched；空 evidence 保留空 groups
- session view：每个 dia_id 仍是一个 unit，child 为其 `D<n>` session 前缀

#### LongMemEval

- turn view：**只收 role=='user' 的 has_answer turn**（官方 `run_retrieval.py:214`），
  assistant 侧 54 个 has_answer turn 不入组；空内容被跳过的 target turn 记
  unmatched（不制造伪 child）
- session view：官方 answer_session_id 为 unit，child 为公开 session id（含
  重复 occurrence suffix）；找不到公开 session 记 unmatched

#### BEAM

- 唯一 turn view：raw id 稳定去重后建 group；单一位置→singleton mapped、
  异常 raw id→multi-child mapped any-of、`--`/找不到→unmatched、None→空 groups
- canonical turn id 保持现状 namespace（s1:t1 / p1:s1:t1），raw id 仅私有 unit_id

#### MemBench

- 唯一 turn view：官方 target_step_id 按首次出现顺序去重；有效 step 退化
  singleton child（1基公开 turn id）；越界 `>=len(message_list)` 建
  unmatched group（不造伪 child）；空 target→空 groups
- 本卡**未拆 FirstAgent**：一 step 仍一个 composite Turn，group 仍是单 child

#### HaluMem

- 声明 v1 但 `evidence_group_sets=()`：memory-point fact 无 turn 回指，禁止
  合成 turn-level qrel

### 4. evaluator 计分（§2.4）

新增 `evaluators/gold_evidence_groups.py` 共享模块，提供：

- `require_manifest_gold_evidence_contract_v1()` — manifest 级 contract 门
- `parse_evidence_group_sets()` — private label → 强类型 group sets
- `select_group_set()` — 严格选择指标所需 (granularity, unit_kind) view
- `group_recall_score()` — 按 group any-of 计算 recall（分母=group 数）
- `group_first_hit_rank()` — 单 group 的最优名次

五个 evaluator 统一调用，删除对 legacy 扁平 qrel 的读取：

- `locomo_recall.py`：turn view 读 `locomo_utterance`，session view 读
  `locomo_utterance_session_projection`；空 groups 仍记 1.0（官方 parity）；
  contract v1 在 none/undeclared 门之后执行
- `longmemeval_recall.py`：turn view 读 `longmemeval_user_target_turn`（分母
  从 role-agnostic 修正为 user-only 419），session view 独立；无 group 题记
  `official_no_target` N/A；contract v1 校验
- `longmemeval_retrieval_rank.py`：`_evaluate_groups_at_k` 按 group rank
  semantics 计算 NDCG（各 group 取其最优 child 命中 rank，unmatched 留 ideal
  分母不命中）；无 target 题同剔除
- `beam_recall.py`：读 `beam_source_message` turn view；空 groups（abstention）
  记 N/A；contract v1 校验
- `membench_recall.py`：读 `membench_step` turn view；空 groups 记 N/A（不再
  错误记 1.0）；unmatched 留在分母永远 miss；contract v1 校验

### 5. 测试覆盖

卡 §5 全部强反例已覆盖：

- **实体**：未知 mapping status、空白/首尾空格 id、list 冒充 tuple、mapped
  空 child、unmatched 非空 child、重复 child/unit/view、未知 granularity/version
  全部拒绝；空 group set 合法（`test_conversation_dataset_validation.py`）
- **隐私**：group/unit_id 只在 evaluator private label 序列化
  （`test_experiment_storage.py`）；公开 payload 递归扫描不含相关键
- **resume/preflight**：v1 首跑成功、同 v1 resume 成功、旧缺 v1→新 v1 mismatch、
  policy/label 版本不一致 fail-fast（`test_prediction_runner.py`）
- **registration**：五家显式声明 v1；非法版本构造期拒绝
  （`test_benchmark_registry.py`）
- **MemBench adapter**：重复 target 去重、越界 unmatched、空 target 空 groups、
  一 step 一 composite turn（未拆）（`test_membench_conversation_adapter.py`）
- **BEAM adapter**：正常 singleton、同 raw id 两位置 multi-child group、abstention
  None 空 groups、跨 conversation 不串线；真实 1M 锁定 41 题/198 歧义原子
  （`test_beam_adapter.py`）
- **LME adapter**：assistant has_answer 不入 turn group；无 user target 得空
  turn groups；blank turn 记 unmatched；session 重复 occurrence 映射
  （`test_longmemeval_conversation_adapter.py`）
- **HaluMem adapter**：v1 + 零 group sets（`test_halumem_adapter.py`）
- **evaluator 计分**：any-of 语义、unmatched 记 0 保留分母、session 聚合、
  空 groups/empty=1（LoCoMo N/A）、N/A 题不评（`test_*_recall.py`、
  `test_*_rank.py`）

### 6. 实质 subagent 使用

无。首轮由 Claude Opus 4.8 开始施工，额度耗尽后由 DeepSeek V4 Pro 在同一
worktree/branch 接力并完成首轮 commit；没有把混合执行错误归功给单一模型。

### 7. 定向自检结果

```text
422 passed, 29 subtests passed in 110.07s (0:01:50)
```

零失败。文件范围 = 卡 §6 的全部 15 个测试文件。

### 8. 偏差/停工点

无。全部裁决按卡 §2 执行，无偏离。

### 9. 后续卡已知依赖

- MemBench canonical split（拆 FirstAgent 为 user/assistant 双 turn，此时
  gold group 从 singleton child 升级为 {user_child, assistant_child}）
- RetrievalEvidence M1（evaluator 消费逐题 evidence 事实）
- LME k30/50 depth 拆分

### 10. 架构师 R1 强验收返工

架构师未把首轮 `422 passed` 当作验收结论，逐读生产 diff 与测试 fixture 后发现
五类 false-green，并裁定线性追加 R1，不 amend 首轮历史：

1. LongMemEval NDCG 的 ideal DCG 错按 `mapped_count` 构造，导致 unmatched unit
   从理想 gold 数中消失；R1 改为全部 `groups` 计入 ideal，新增“一 mapped 命中 +
   一 unmatched”应为 0.5，以及 multi-child 最小 rank/重复 child 不重复增益强反例。
2. BEAM 所谓“歧义任一位置命中”测试实际构造了两个 singleton group 并期望 0.5；
   R1 改为一个 raw unit 对两个 canonical child，任一命中为 1.0，并把 empty=N/A 与
   unmatched=0 两条语义彻底拆开。
3. runner 在 `benchmark_policy=None` 时无条件跳过，使 v1 label 可混入无版本 run；
   R1 只保留“policy=None + 全部 label unversioned”的 legacy 兼容，任一版本化 label
   均 fail-fast。
4. 五个 evaluator 原先先按 method provenance 返回 N/A，旧/非法 benchmark manifest
   会被掩盖；R1 统一改为 manifest v1 identity-first。method 本身 N/A 时仍不读取
   evaluator-private label/view，保持“不消费 qrel 就不强读私有 artifact”的裁决边界。
5. MemBench evaluator fixture 用 `zip(target_step_ids, legacy evidence)` 建 group，既会
   被 legacy 长度截断，又使用了不存在于生产 adapter 的复合 id。R1 改为稳定去重的
   target step 单事实源，合法 child=`str(step_id + 1)`、OOB=unmatched；legacy evidence
   只保留历史字段。真实 LongMemEval S split 同时锁定 500=30 abstention + 51 non-abs
   no-user-target + 419 scored，禁止靠过滤数据迎合分母。

R1 最终定向自检结果见下方追加记录；首轮 §7 的历史尾行保持原样，不回写覆盖。

```text
436 passed, 29 subtests passed in 142.45s (0:02:22)
```

文件范围仍为原卡 §6 的全部 15 个测试文件；零真实 API、零下载，worktree 中现有
`data` / `third_party/benchmarks` 只读软链未进入暂存区。
